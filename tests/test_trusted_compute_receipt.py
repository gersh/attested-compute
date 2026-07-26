# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import concurrent.futures
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

try:
    import jsonschema
except ImportError:
    jsonschema = None


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import create_run_bundle as bundles  # noqa: E402
import trusted_compute_receipt as receipts  # noqa: E402
from tg_verifier.campaign_io import (  # noqa: E402
    canonical_json_bytes as corpus_canonical_json_bytes,
)


FIXTURE = ROOT / "tests/fixtures/trusted_compute_cpu_receipt.json"


class TrustedComputeReceiptTests(unittest.TestCase):
    def fixture(self) -> dict:
        return bundles.parse_json_bytes(FIXTURE.read_bytes(), str(FIXTURE))

    def numeric_corpus_pin(self) -> dict:
        return {
            "expected": {
                "claim_id": "test.numeric.claim",
                "claim_version": 3,
                "corpus_id": "test.numeric.corpus",
                "corpus_version": 5,
                "payload_file_count": 7,
                "payload_root_sha256": "11" * 32,
                "payload_total_size_bytes": 123456,
                "source_root_sha256": "22" * 32,
                "statement_sha256": "33" * 32,
            },
            "kind": "sparkinterval.pinned_numeric_corpus.v1",
            "pin_id": "test.numeric.pin",
            "repository": {
                "commit": "4" * 40,
                "manifest_path": "corpus/manifest.json",
                "manifest_sha256": "55" * 32,
                "manifest_size_bytes": 4096,
                "url": "https://example.com/test/numeric-corpus.git",
            },
            "schema_version": 1,
        }

    def test_signed_cpu_fixture_is_valid(self) -> None:
        receipt = receipts.validate_receipt(self.fixture())
        receipts.verify_signature(receipt)
        self.assertEqual(receipt["backend"], "azure_sevsnp_cpu")
        self.assertEqual(
            receipts.sha256_bytes(receipts.canonical_signed_payload(receipt)),
            "fe1a134e494d27e6b880eb470b3e66f21089beb4db2d9f3725aedcc2780d8a51",
        )

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_receipt_schema_enforces_backend_and_placeholder_separation(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/trusted-compute-receipt.schema.json").read_text()
        )
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(self.fixture())

        wrong_backend = self.fixture()
        wrong_backend["backend"] = "azure_ncc40ads_h100_v5"
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(wrong_backend)

        placeholder = self.fixture()
        placeholder["claim"]["input_hash"] = "0" * 64
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(placeholder)

    def test_nonbootstrap_key_requires_an_explicit_public_key(self) -> None:
        receipt = self.fixture()
        receipt["verifier"]["key_id"] = "production-hsm-key-2026-07"
        receipt["signature"]["key_id"] = "production-hsm-key-2026-07"
        core = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        receipt["receipt_sha256"] = receipts.canonical_sha256(core)
        receipts.validate_receipt(receipt)
        with self.assertRaisesRegex(receipts.ReceiptError, "no public key"):
            receipts.verify_signature(receipt)

    def test_public_key_cli_default_cannot_alias_the_bootstrap_key(self) -> None:
        args = receipts._parser().parse_args(["verify", str(FIXTURE)])
        self.assertIsNone(args.public_key)

    def test_standalone_verify_does_not_claim_lean_acceptance(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = receipts.main(["verify", str(FIXTURE)])
        self.assertEqual(status, 0)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary["signature_valid"], True)
        self.assertEqual(summary["accepted_for_lean"], False)
        self.assertNotIn("accepted", summary)

    def test_malformed_sqrt218_reviewed_pins_fail_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pins = Path(temporary) / "reviewed-pins.json"
            pins.write_bytes(b"{}")
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                status = receipts.main(
                    [
                        "verify",
                        str(FIXTURE),
                        "--sqrt218-fixed-v2-reviewed-pins",
                        str(pins),
                    ]
                )
        self.assertEqual(status, 2)
        self.assertIn("fixed-V2 reviewed pins has wrong fields", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())

    def test_issuer_rejects_nonbootstrap_key_without_explicit_public_key(self) -> None:
        args = SimpleNamespace(
            backend="azure_sevsnp_cpu",
            verifier_key_id="production-hsm-key-2026-07",
            public_key=None,
        )
        with self.assertRaisesRegex(receipts.ReceiptError, "explicit --public-key"):
            receipts.issue(args)

    def test_production_key_id_cannot_use_development_private_key_mode(self) -> None:
        args = SimpleNamespace(
            backend="azure_sevsnp_cpu",
            verifier_key_id="production-hsm-key-2026-07",
            public_key="production.pem",
            private_key="forbidden.pem",
        )
        with self.assertRaisesRegex(receipts.ReceiptError, "signer-command"):
            receipts.issue(args)

    def test_external_signer_uses_private_snapshot_and_sanitized_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            signer = Path(temporary) / "signer"
            source = b"#!/bin/sh\nexit 0\n"
            signer.write_bytes(source)
            signer.chmod(0o700)

            def inspect(command, **kwargs):
                snapshot = Path(command[0])
                self.assertNotEqual(snapshot, signer)
                self.assertEqual(snapshot.read_bytes(), source)
                self.assertEqual(snapshot.stat().st_mode & 0o777, 0o500)
                self.assertEqual(snapshot.parent.stat().st_mode & 0o777, 0o700)
                signer.write_bytes(b"replacement")
                self.assertEqual(snapshot.read_bytes(), source)
                for name in (
                    "LD_LIBRARY_PATH",
                    "LD_PRELOAD",
                    "PYTHONHOME",
                    "PYTHONPATH",
                ):
                    self.assertNotIn(name, kwargs["env"])
                return mock.Mock(returncode=0, stdout=b"S" * 384, stderr=b"")

            with mock.patch.dict(
                os.environ,
                {
                    "LD_LIBRARY_PATH": "/attacker",
                    "LD_PRELOAD": "/attacker/preload.so",
                    "PYTHONHOME": "/attacker/python",
                    "PYTHONPATH": "/attacker/modules",
                },
            ), mock.patch.object(
                receipts.subprocess, "run", side_effect=inspect
            ):
                signature = receipts._sign_external(b"payload", signer, ["--fixed"])
            self.assertEqual(signature, (b"S" * 384).hex())

    def test_issue_cli_requires_replay_database(self) -> None:
        issue = next(
            action
            for action in receipts._parser()._actions
            if action.dest == "command"
        ).choices["issue"]
        replay = next(action for action in issue._actions if action.dest == "replay_db")
        self.assertTrue(replay.required)

    def test_receipt_issuer_passes_the_exact_retained_challenge(self) -> None:
        start = "11" * 32
        binding = "22" * 32
        digest = "33" * 32
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            policy = root / "policy.json"
            policy.write_bytes(b"{}\n")
            retained_challenge = root / "retained.challenge.json"
            retained_challenge.write_bytes(b"{}\n")
            result = {
                "accepted": True,
                "appraised_at_utc": "2026-07-21T12:00:00Z",
                "backend": "azure_sevsnp_cpu",
                "evidence_hashes": {
                    "amd_snp_report_sha256": digest,
                    "azure_maa_token_sha256": digest,
                    "nvidia_eat_sha256": receipts.NOT_APPLICABLE_DIGEST,
                    "nvidia_evidence_sha256": receipts.NOT_APPLICABLE_DIGEST,
                    "platform_evidence_sha256": digest,
                    "tpm_event_log_sha256": digest,
                    "tpm_quote_sha256": digest,
                },
                "kind": "sparkinterval_evidence_appraisal",
                "not_after_utc": "2026-07-21T13:00:00Z",
                "not_before_utc": "2026-07-21T11:00:00Z",
                "policy_sha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
                "result_binding_sha256": binding,
                "schema_version": 1,
                "start_challenge_sha256": start,
            }
            completed = mock.Mock(
                returncode=0,
                stdout=json.dumps(result).encode("utf-8"),
                stderr=b"",
            )
            with mock.patch.dict(
                os.environ,
                {
                    "LD_LIBRARY_PATH": "/attacker",
                    "LD_PRELOAD": "/attacker/preload.so",
                    "PYTHONHOME": "/attacker/python",
                    "PYTHONPATH": "/attacker/modules",
                },
            ), mock.patch.object(
                receipts.subprocess, "run", return_value=completed
            ) as run:
                receipts._run_evidence_verifier(
                    Path("/reviewed/verifier"),
                    Path("/returned/evidence"),
                    policy,
                    retained_challenge,
                    "azure_sevsnp_cpu",
                    start,
                    binding,
                )
            command = run.call_args.args[0]
            challenge_index = command.index("--expected-challenge-file")
            self.assertEqual(command[challenge_index + 1], str(retained_challenge))
            self.assertEqual(command.count("--expected-start-challenge-sha256"), 1)
            self.assertEqual(command.count(start), 1)
            self.assertEqual(command.count("--expected-result-binding-sha256"), 1)
            self.assertEqual(command.count(binding), 1)
            environment = run.call_args.kwargs["env"]
            for name in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH"):
                self.assertNotIn(name, environment)
            self.assertEqual(environment["PATH"], "/usr/sbin:/usr/bin:/sbin:/bin")

    def test_snapshotted_official_verifier_is_directly_runnable(self) -> None:
        executable = ROOT / "attestation/verify_azure_ncc_evidence.py"
        digest, _size = receipts.hash_file(executable)
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = receipts._snapshot_evidence_verifier(
                executable, Path(temporary) / "verifier", digest
            )
            completed = subprocess.run(
                [str(snapshot), "--help"],
                check=False,
                capture_output=True,
                text=True,
                env=receipts._subprocess_environment(),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("--expected-result-binding-sha256", completed.stdout)

    def test_snapshotted_official_verifier_rejects_imported_module_mutation(self) -> None:
        executable = ROOT / "attestation/verify_azure_ncc_evidence.py"
        digest, _size = receipts.hash_file(executable)
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = receipts._snapshot_evidence_verifier(
                executable, Path(temporary) / "verifier", digest
            )
            module = snapshot.with_name("measured_runner.py")
            module.chmod(0o600)
            module.write_bytes(module.read_bytes() + b"\n# substituted\n")
            completed = subprocess.run(
                [str(snapshot), "--help"],
                check=False,
                capture_output=True,
                text=True,
                env=receipts._subprocess_environment(),
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("differs from verifier source pin", completed.stderr)

    def test_result_tampering_fails_signature_even_after_receipt_rehash(self) -> None:
        receipt = self.fixture()
        receipt["claim"]["result"] = "forged-result"
        receipt["claim"]["output_hash"] = receipts.sha256_bytes(b"forged-result")
        core = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        receipts.validate_receipt(receipt)
        with self.assertRaisesRegex(receipts.ReceiptError, "signature is invalid"):
            receipts.verify_signature(receipt)

    def test_receipt_signature_countersigns_quote_and_platform_evidence_roots(self) -> None:
        fixture = self.fixture()
        payload = receipts.canonical_signed_payload(fixture).decode("utf-8")
        self.assertIn(
            "tpm_quote_sha256="
            + fixture["evidence_hashes"]["tpm_quote_sha256"]
            + "\n",
            payload,
        )
        self.assertIn(
            "platform_evidence_sha256="
            + fixture["evidence_hashes"]["platform_evidence_sha256"]
            + "\n",
            payload,
        )
        self.assertIn(
            "result_binding_sha256="
            + fixture["bindings"]["result_binding_sha256"]
            + "\n",
            payload,
        )

        for field in ("tpm_quote_sha256", "platform_evidence_sha256"):
            with self.subTest(field=field):
                receipt = self.fixture()
                receipt["evidence_hashes"][field] = "12" * 32
                core = {
                    key: value
                    for key, value in receipt.items()
                    if key != "receipt_sha256"
                }
                receipt["receipt_sha256"] = bundles.canonical_sha256(core)
                receipts.validate_receipt(receipt)
                with self.assertRaisesRegex(
                    receipts.ReceiptError, "signature is invalid"
                ):
                    receipts.verify_signature(receipt)

    def test_result_bytes_must_match_output_hash_before_signature_check(self) -> None:
        receipt = self.fixture()
        receipt["claim"]["result"] = "substituted-result"
        core = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        with self.assertRaisesRegex(receipts.ReceiptError, "result bytes"):
            receipts.validate_receipt(receipt)

    def test_backend_target_and_accelerator_evidence_are_consistent(self) -> None:
        mutations = (
            (
                lambda receipt: receipt["claim"].update(
                    {
                        "target": "nvidia_h100_sm90",
                        "trust": "nvidia_h100_confidential_compute",
                    }
                ),
                "target/trust",
            ),
            (
                lambda receipt: receipt["claim"]["artifacts"].update(
                    {"device_cubin_hash": "66" * 32}
                ),
                "device image",
            ),
            (
                lambda receipt: receipt["evidence_hashes"].update(
                    {"nvidia_eat_sha256": "77" * 32}
                ),
                "NVIDIA evidence",
            ),
        )
        for mutate, message in mutations:
            with self.subTest(message=message):
                receipt = self.fixture()
                mutate(receipt)
                core = {
                    key: value
                    for key, value in receipt.items()
                    if key != "receipt_sha256"
                }
                receipt["receipt_sha256"] = bundles.canonical_sha256(core)
                with self.assertRaisesRegex(receipts.ReceiptError, message):
                    receipts.validate_receipt(receipt)

    def test_numeric_corpus_pin_is_projected_from_exact_signed_input_bytes(self) -> None:
        pin = self.numeric_corpus_pin()
        raw = corpus_canonical_json_bytes(pin)
        digest = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pin_path = root / "input-pin.json"
            pin_path.write_bytes(raw)
            binding = receipts.numeric_corpus_pin_binding(
                pin_path,
                expected_input_hash=digest,
                expected_input_size=len(raw),
            )
            self.assertEqual(binding["claim_id"], "test.numeric.claim")
            self.assertEqual(binding["payload_root_sha256"], "11" * 32)
            self.assertEqual(binding["source_root_sha256"], "22" * 32)
            self.assertEqual(binding["manifest_sha256"], "55" * 32)
            self.assertEqual(binding["repository_commit"], "4" * 40)
            self.assertEqual(binding["pin_sha256"], digest)

            bundle = {
                "statement": {
                    "input_artifact": {
                        "path": pin_path.name,
                        "sha256": digest,
                        "size_bytes": len(raw),
                    }
                }
            }
            self.assertEqual(
                receipts._numeric_corpus_binding_for_bundle_input(
                    bundle, root, expected_input_hash=digest
                ),
                binding,
            )
            linked_path = root / "linked-pin.json"
            linked_path.symlink_to(pin_path.name)
            linked_bundle = copy.deepcopy(bundle)
            linked_bundle["statement"]["input_artifact"]["path"] = linked_path.name
            with self.assertRaisesRegex(receipts.ReceiptError, "must not be a symlink"):
                receipts._numeric_corpus_binding_for_bundle_input(
                    linked_bundle, root, expected_input_hash=digest
                )

            with self.assertRaisesRegex(receipts.ReceiptError, "signed claim input"):
                receipts.numeric_corpus_pin_binding(
                    pin_path,
                    expected_input_hash="88" * 32,
                )
            pin_path.write_bytes(json.dumps(pin, indent=2).encode("utf-8"))
            with self.assertRaisesRegex(receipts.ReceiptError, "canonical"):
                receipts.numeric_corpus_pin_binding(
                    pin_path,
                    expected_input_hash=hashlib.sha256(
                        pin_path.read_bytes()
                    ).hexdigest(),
                )

    def test_signature_hex_must_be_fixed_width_lowercase(self) -> None:
        for mutate in (
            lambda value: value[:-1],
            lambda value: value[:10] + "A" + value[11:],
            lambda value: value[:10] + " " + value[11:],
        ):
            with self.subTest(mutate=mutate):
                receipt = self.fixture()
                receipt["signature"]["value_hex"] = mutate(
                    receipt["signature"]["value_hex"]
                )
                core = {
                    key: value
                    for key, value in receipt.items()
                    if key != "receipt_sha256"
                }
                receipt["receipt_sha256"] = bundles.canonical_sha256(core)
                with self.assertRaisesRegex(
                    receipts.ReceiptError, "lowercase hexadecimal"
                ):
                    receipts.validate_receipt(receipt)

    def test_backend_cannot_be_resigned_by_relabelling_all_gpu_fields(self) -> None:
        receipt = self.fixture()
        receipt["backend"] = "azure_ncc40ads_h100_v5"
        receipt["claim"]["target"] = "nvidia_h100_sm90"
        receipt["claim"]["trust"] = "nvidia_h100_confidential_compute"
        receipt["claim"]["artifacts"]["device_cubin_hash"] = "12" * 32
        receipt["evidence_hashes"]["nvidia_eat_sha256"] = "13" * 32
        receipt["evidence_hashes"]["nvidia_evidence_sha256"] = "14" * 32
        core = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        receipts.validate_receipt(receipt)
        with self.assertRaisesRegex(receipts.ReceiptError, "signature is invalid"):
            receipts.verify_signature(receipt)

    def test_start_and_result_bindings_are_not_self_asserted(self) -> None:
        receipt = copy.deepcopy(self.fixture())
        receipt["bindings"]["result_binding_sha256"] = "12" * 32
        core = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        with self.assertRaisesRegex(receipts.ReceiptError, "result binding digest"):
            receipts.validate_receipt(receipt)

    def test_claim_rechecks_exact_output_bytes_after_bundle_verification(self) -> None:
        digest = lambda value: hashlib.sha256(value).hexdigest()
        original = b"accepted-output"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "result.txt").write_bytes(b"substituted-output")
            bundle = {
                "statement": {
                    "algorithm": {
                        "algorithm_id": "test",
                        "definition_sha256": digest(b"algorithm"),
                    },
                    "input_artifact": {"sha256": digest(b"input")},
                    "parameters": {"canonical_sha256": digest(b"parameters")},
                    "domain_coverage": {"canonical_sha256": digest(b"domain")},
                    "output_artifact": {
                        "path": "result.txt",
                        "sha256": digest(original),
                        "size_bytes": len(original),
                    },
                    "nonce": digest(b"challenge"),
                    "target_profile": {
                        "profile_id": "azure_sevsnp_cpu",
                        "sha256": digest(b"target-profile"),
                    },
                    "trust_profile": {
                        "profile_id": "azure_sevsnp_hardware_attested",
                        "sha256": digest(b"trust-profile"),
                    },
                    "build_artifacts": [
                        {"role": "source_tree", "sha256": digest(b"source")},
                        {
                            "role": "host_executable",
                            "sha256": digest(b"executable"),
                        },
                        {
                            "role": "execution_manifest",
                            "sha256": digest(b"manifest"),
                        },
                    ],
                }
            }
            with self.assertRaisesRegex(
                receipts.ReceiptError, "changed after run-bundle verification"
            ):
                receipts.claim_from_bundle(bundle, root, "azure_sevsnp_cpu")

    def test_replay_reservation_is_atomic_under_concurrency(self) -> None:
        nonce = "11" * 32
        challenge = "22" * 32
        statement = "33" * 32
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "state" / "spent.sqlite3"

            def reserve() -> str:
                try:
                    receipts._reserve_challenge(
                        database,
                        nonce=nonce,
                        challenge_sha256=challenge,
                        wire_statement_sha256=statement,
                        backend="azure_sevsnp_cpu",
                    )
                    return "reserved"
                except receipts.ReceiptError as error:
                    return str(error)

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                outcomes = list(pool.map(lambda _index: reserve(), range(8)))
            self.assertEqual(outcomes.count("reserved"), 1)
            self.assertEqual(
                outcomes.count("retained challenge is already spent"), 7
            )
            with sqlite3.connect(database) as connection:
                row = connection.execute(
                    "SELECT nonce, challenge_sha256, wire_statement_sha256, "
                    "backend, status, signed_at_utc, receipt_sha256 "
                    "FROM trusted_compute_spent_challenges"
                ).fetchone()
            self.assertEqual(
                row,
                (
                    nonce,
                    challenge,
                    statement,
                    "azure_sevsnp_cpu",
                    "reserved",
                    None,
                    None,
                ),
            )

    def test_replay_database_rejects_insecure_parent_file_and_hardlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "issuer"
            parent.mkdir(mode=0o700)
            database = parent / "spent.sqlite3"
            parent.chmod(0o755)
            with self.assertRaisesRegex(receipts.ReceiptError, "exactly 0700"):
                receipts._open_replay_database(database)
            parent.chmod(0o700)
            database.write_bytes(b"")
            database.chmod(0o644)
            with self.assertRaisesRegex(receipts.ReceiptError, "exactly 0600"):
                receipts._open_replay_database(database)
            database.chmod(0o600)
            alias = parent / "rollback-alias.sqlite3"
            alias.hardlink_to(database)
            with self.assertRaisesRegex(receipts.ReceiptError, "exactly one hard link"):
                receipts._open_replay_database(database)

    def test_replay_database_detects_inode_change_during_sqlite_connect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "issuer" / "spent.sqlite3"
            real_connect = sqlite3.connect

            def replace_then_connect(path, *args, **kwargs):
                selected = Path(path)
                displaced = selected.with_name("displaced.sqlite3")
                selected.rename(displaced)
                selected.write_bytes(b"")
                selected.chmod(0o600)
                return real_connect(selected, *args, **kwargs)

            with mock.patch.object(
                receipts.sqlite3, "connect", side_effect=replace_then_connect
            ):
                with self.assertRaisesRegex(receipts.ReceiptError, "inode changed"):
                    receipts._open_replay_database(database)

    def test_replay_database_limitations_are_explicitly_documented(self) -> None:
        documentation = (ROOT / "docs/AZURE_CONFIDENTIAL_COMPUTE.md").read_text()
        self.assertIn("do **not** turn local SQLite into a rollback-resistant", documentation)
        self.assertIn("issuers pointed at different databases", documentation)
        self.assertIn("one strongly consistent durable ledger", documentation)

    def test_failed_appraisal_leaves_challenge_spent(self) -> None:
        fixture = self.fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            policy = root / "policy.json"
            policy.write_bytes(b"{}\n")
            challenge = root / "challenge.json"
            challenge.write_bytes(b"{}\n")
            evidence = root / "evidence"
            evidence.mkdir()
            output = root / "receipt.json"
            database = root / "issuer" / "spent.sqlite3"
            args = SimpleNamespace(
                backend="azure_sevsnp_cpu",
                verifier_key_id=receipts.BOOTSTRAP_KEY_ID,
                public_key=None,
                private_key="development.pem",
                bundle="bundle.json",
                artifact_root=str(root),
                evidence_verifier="/bin/true",
                evidence_policy=str(policy),
                evidence_pack=str(evidence),
                retained_challenge=str(challenge),
                replay_db=str(database),
                signer_command=None,
                signer_arg=[],
                openssl="openssl",
                out=str(output),
            )
            verified = {
                "bundle_sha256": fixture["bindings"]["run_bundle_sha256"],
                "statement_sha256": fixture["bindings"]["wire_statement_sha256"],
            }
            with mock.patch.object(
                receipts, "load_canonical_json", return_value={}
            ), mock.patch.object(
                receipts.verify_run_bundle, "verify_bundle", return_value=verified
            ), mock.patch.object(
                receipts, "claim_from_bundle", return_value=fixture["claim"]
            ), mock.patch.object(
                receipts,
                "_run_evidence_verifier",
                side_effect=receipts.ReceiptError("appraisal failed closed"),
            ) as appraise:
                with self.assertRaisesRegex(receipts.ReceiptError, "appraisal failed"):
                    receipts.issue(args)
                with self.assertRaisesRegex(receipts.ReceiptError, "already spent"):
                    receipts.issue(args)
            self.assertEqual(appraise.call_count, 1)
            self.assertFalse(output.exists())
            with sqlite3.connect(database) as connection:
                status = connection.execute(
                    "SELECT status FROM trusted_compute_spent_challenges"
                ).fetchone()[0]
            self.assertEqual(status, "reserved")

    def test_outer_verifier_policy_and_challenge_are_private_snapshots(self) -> None:
        fixture = self.fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            verifier = root / "verifier"
            verifier.write_bytes(b"#!/bin/sh\nexit 0\n")
            verifier.chmod(0o700)
            policy = root / "policy.json"
            policy.write_bytes(b"{}\n")
            challenge = root / "challenge.json"
            challenge.write_bytes(b"{}\n")
            evidence = root / "evidence"
            evidence.mkdir()
            args = SimpleNamespace(
                backend="azure_sevsnp_cpu",
                verifier_key_id=receipts.BOOTSTRAP_KEY_ID,
                public_key=None,
                private_key="development.pem",
                bundle="bundle.json",
                artifact_root=str(root),
                evidence_verifier=str(verifier),
                evidence_policy=str(policy),
                evidence_pack=str(evidence),
                retained_challenge=str(challenge),
                replay_db=str(root / "issuer" / "spent.sqlite3"),
                signer_command=None,
                signer_arg=[],
                openssl="openssl",
                out=str(root / "receipt.json"),
            )
            verified = {
                "bundle_sha256": fixture["bindings"]["run_bundle_sha256"],
                "statement_sha256": fixture["bindings"]["wire_statement_sha256"],
            }

            def inspect_snapshots(
                invoked_verifier, _pack, invoked_policy, invoked_challenge, *_args
            ):
                self.assertNotEqual(invoked_verifier, verifier)
                self.assertNotEqual(invoked_policy, policy)
                self.assertNotEqual(invoked_challenge, challenge)
                self.assertEqual(invoked_verifier.read_bytes(), verifier.read_bytes())
                self.assertEqual(invoked_policy.read_bytes(), policy.read_bytes())
                self.assertEqual(invoked_challenge.read_bytes(), challenge.read_bytes())
                self.assertEqual(invoked_verifier.stat().st_mode & 0o777, 0o500)
                self.assertEqual(invoked_policy.stat().st_mode & 0o777, 0o400)
                self.assertEqual(invoked_challenge.stat().st_mode & 0o777, 0o400)
                self.assertEqual(invoked_verifier.parents[1].stat().st_mode & 0o777, 0o700)
                verifier.write_bytes(b"replacement verifier")
                policy.write_bytes(b"replacement policy")
                challenge.write_bytes(b"replacement challenge")
                self.assertEqual(invoked_verifier.read_bytes(), b"#!/bin/sh\nexit 0\n")
                self.assertEqual(invoked_policy.read_bytes(), b"{}\n")
                self.assertEqual(invoked_challenge.read_bytes(), b"{}\n")
                raise receipts.ReceiptError("snapshot audit complete")

            with mock.patch.object(
                receipts, "load_canonical_json", return_value={}
            ), mock.patch.object(
                receipts.verify_run_bundle, "verify_bundle", return_value=verified
            ), mock.patch.object(
                receipts, "claim_from_bundle", return_value=fixture["claim"]
            ), mock.patch.object(
                receipts,
                "_run_evidence_verifier",
                side_effect=inspect_snapshots,
            ):
                with self.assertRaisesRegex(
                    receipts.ReceiptError, "snapshot audit complete"
                ):
                    receipts.issue(args)

    def test_signed_transition_and_receipt_output_are_exact_and_no_overwrite(self) -> None:
        nonce = "11" * 32
        challenge = "22" * 32
        statement = "33" * 32
        receipt_hash = "44" * 32
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "state" / "spent.sqlite3"
            output = root / "receipt.json"
            receipts._reserve_challenge(
                database,
                nonce=nonce,
                challenge_sha256=challenge,
                wire_statement_sha256=statement,
                backend="azure_sevsnp_cpu",
            )
            receipts._install_new_receipt(output, b"first")
            with self.assertRaisesRegex(receipts.ReceiptError, "refusing to replace"):
                receipts._install_new_receipt(output, b"second")
            self.assertEqual(output.read_bytes(), b"first")
            receipts._mark_challenge_signed(
                database,
                nonce=nonce,
                challenge_sha256=challenge,
                wire_statement_sha256=statement,
                backend="azure_sevsnp_cpu",
                receipt_sha256=receipt_hash,
            )
            with sqlite3.connect(database) as connection:
                row = connection.execute(
                    "SELECT status, signed_at_utc, receipt_sha256 "
                    "FROM trusted_compute_spent_challenges"
                ).fetchone()
            self.assertEqual(row[0], "signed")
            self.assertRegex(row[1], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
            self.assertEqual(row[2], receipt_hash)

if __name__ == "__main__":
    unittest.main()
