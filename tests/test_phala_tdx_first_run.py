# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Local end-to-end dry run of the Phala/dstack TDX campaign path.

This is the test that says whether the repository is ready for a first real
Phala run.  It exercises, locally, everything except the TEE itself:

* the separately named TDX acceptance route in ``tg_verifier/campaign_io.py``,
  including that it and the Azure route reject each other's environments;
* the canonical signed payload, in Python and in Lean, byte for byte;
* the deterministic P-256 signer, against the RFC 6979 test vector;
* the campaign image: built from ``proof_build/ch25_a7_phala_tdx/Dockerfile``
  and actually run, executing the real CH25 Lemma A.7 FLINT/Arb replay and
  emitting the registered result plus an enclave-signed receipt; and
* that the receipt the container produced is exactly the one pinned in
  ``SparkInterval/Tests/PhalaTdxDryRunTest.lean``, which drives it to the Lean
  campaign theorem.

The Docker stage is skipped when Docker is unavailable or cannot run
``linux/amd64``; the rest always runs.  Set
``SPARKINTERVAL_PHALA_TDX_RUN_DOCKER=0`` to skip it explicitly.

Nothing here is attested and nothing here is a production claim: the signing
key is the committed stand-in, the A.7 artifact is a freshly generated fixture
rather than the retained production artifact, and the quote/appraisal files
are labelled placeholders.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import (  # noqa: E402
    AZURE_MEASURED_WORKER_BACKEND_ENV,
    AZURE_MEASURED_WORKER_CHALLENGE_ENV,
    AZURE_MEASURED_WORKER_JOB_BINDING_ENV,
    AZURE_MEASURED_WORKER_SCOPE,
    AZURE_MEASURED_WORKER_SCOPE_ENV,
    MeasuredWorkerScopeError,
    PhalaTdxWorkerScopeError,
    phala_tdx_worker_environment,
    require_azure_measured_worker_for_workload,
    require_phala_tdx_worker_for_workload,
)
from tg_verifier.phala_tdx_receipt import (  # noqa: E402
    SIGNED_FIELDS,
    canonical_signed_payload,
    public_key_hex,
    report_data_hash,
    sign_digest_hex,
    statement_digest,
    verify_digest_hex,
    verify_receipt,
)

DATA = ROOT / "tests/data/phala_tdx_dry_run"
LEAN_DRY_RUN = ROOT / "SparkInterval/Tests/PhalaTdxDryRunTest.lean"
LEAN_PIN = ROOT / "SparkInterval/Execution/PhalaTdxAttestation.lean"
LEAN_REGISTRY = ROOT / "SparkInterval/Execution/RegisteredAlgorithm.lean"
DOCKERFILE = ROOT / "proof_build/ch25_a7_phala_tdx/Dockerfile"
IMAGE_TAG = "sparkinterval-ch25-a7-phala-tdx:dryrun"

REGISTERED_INPUT = (
    b'{"campaign":"ch25-a7-boundary-v1","retained_artifact_sha256":'
    b'"ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29"}'
)

# The dry-run job identity.  These are also the literals in the Lean dry-run
# enclave pin; the tests below assert the two agree.
DRY_RUN_CHALLENGE = "11" * 32
DRY_RUN_JOB_BINDING = "22" * 32
DRY_RUN_APP_ID = "327d84eaf0cfb23bfc4260453516a9afc0287705"
DRY_RUN_COMPOSE_HASH = (
    "44c2baa7f7fbf92c08d9800071ec0d3d21404c07af1db8254ebd77c717b8e35c"
)
DRY_RUN_IMAGE_DIGEST = (
    "sha256:43233eef77b7ad2463aa6b352a7459ffd42b0d1f8b9373858889d8f1bc0c073c"
)
DRY_RUN_ISSUED_AT = "2026-07-26T00:00:00Z"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lean_string_literals(text: str, name: str) -> str:
    """Extract a Lean `def name : String := "…" ++ "…"` value."""

    match = re.search(
        rf"def\s+{re.escape(name)}\s*:\s*String\s*:=\s*((?:\s*\"[^\"]*\"\s*(?:\+\+)?)+)",
        text,
    )
    assert match, f"cannot find Lean definition {name}"
    return "".join(re.findall(r'"([^"]*)"', match.group(1)))


def _docker_available() -> bool:
    if os.environ.get("SPARKINTERVAL_PHALA_TDX_RUN_DOCKER") == "0":
        return False
    if shutil.which("docker") is None:
        return False
    probe = subprocess.run(
        ["docker", "run", "--rm", "--platform", "linux/amd64",
         DOCKER_PROBE_IMAGE, "true"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    return probe.returncode == 0


DOCKER_PROBE_IMAGE = "debian:bookworm-slim"


class GuardSeparationTests(unittest.TestCase):
    """The two acceptance routes must not be able to admit each other."""

    def test_tdx_route_rejects_an_azure_environment(self) -> None:
        azure = {
            AZURE_MEASURED_WORKER_SCOPE_ENV: AZURE_MEASURED_WORKER_SCOPE,
            AZURE_MEASURED_WORKER_BACKEND_ENV: "azure_sevsnp_cpu",
            AZURE_MEASURED_WORKER_CHALLENGE_ENV: "aa" * 32,
            AZURE_MEASURED_WORKER_JOB_BINDING_ENV: "bb" * 32,
        }
        with self.assertRaises(PhalaTdxWorkerScopeError):
            require_phala_tdx_worker_for_workload(
                exact_production=True, work_bounds=(), environment=azure
            )

    def test_azure_route_rejects_a_tdx_environment(self) -> None:
        tdx = phala_tdx_worker_environment(
            {},
            backend="phala_dstack_tdx_cpu",
            challenge_nonce=DRY_RUN_CHALLENGE,
            job_binding=DRY_RUN_JOB_BINDING,
            app_id=DRY_RUN_APP_ID,
            compose_hash=DRY_RUN_COMPOSE_HASH,
        )
        with self.assertRaises(MeasuredWorkerScopeError):
            require_azure_measured_worker_for_workload(
                exact_production=True, work_bounds=(), environment=tdx
            )

    def test_tdx_route_rejects_a_mixed_scope_environment(self) -> None:
        mixed = phala_tdx_worker_environment(
            {},
            backend="phala_dstack_tdx_cpu",
            challenge_nonce=DRY_RUN_CHALLENGE,
            job_binding=DRY_RUN_JOB_BINDING,
            app_id=DRY_RUN_APP_ID,
            compose_hash=DRY_RUN_COMPOSE_HASH,
        )
        mixed[AZURE_MEASURED_WORKER_SCOPE_ENV] = AZURE_MEASURED_WORKER_SCOPE
        with self.assertRaises(PhalaTdxWorkerScopeError):
            require_phala_tdx_worker_for_workload(
                exact_production=True, work_bounds=(), environment=mixed
            )

    def test_tdx_route_accepts_only_its_own_binding(self) -> None:
        tdx = phala_tdx_worker_environment(
            {},
            backend="phala_dstack_tdx_cpu",
            challenge_nonce=DRY_RUN_CHALLENGE,
            job_binding=DRY_RUN_JOB_BINDING,
            app_id=DRY_RUN_APP_ID,
            compose_hash=DRY_RUN_COMPOSE_HASH,
        )
        job = require_phala_tdx_worker_for_workload(
            exact_production=True, work_bounds=(), environment=tdx
        )
        self.assertEqual(job["backend"], "phala_dstack_tdx_cpu")
        self.assertEqual(job["app_id"], DRY_RUN_APP_ID)
        self.assertEqual(job["compose_hash"], DRY_RUN_COMPOSE_HASH)

    def test_azure_guard_source_is_unchanged_by_the_tdx_route(self) -> None:
        """The Azure functions must not reference anything TDX."""

        text = (ROOT / "tg_verifier/campaign_io.py").read_text(encoding="utf-8")
        azure_block = text[
            text.index("def require_azure_measured_worker(") : text.index(
                "# Phala/dstack Intel TDX acceptance route"
            )
        ]
        for token in ("phala", "PHALA", "PhalaTdx", "tdx"):
            self.assertNotIn(token, azure_block)


class SignerTests(unittest.TestCase):
    def test_rfc6979_nonce_matches_the_published_vector(self) -> None:
        # RFC 6979 A.2.5, P-256/SHA-256, message "sample".  Our signer
        # additionally normalizes to low `s`, so `r` must match exactly and
        # `s` must be the published value negated modulo the group order.
        private = int(
            "C9AFA9D845BA75166B5C215767B1D6934E50C3DB36E89B127B8A622B120F6721",
            16,
        )
        order = int(
            "FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551",
            16,
        )
        digest = hashlib.sha256(b"sample").hexdigest()
        signature = sign_digest_hex(private, digest)
        self.assertEqual(
            signature[:64],
            "efd48b2aacb6a8fd1140dd9cd45e81d69d2c877b56aaf991c34d0ea84eaf3716",
        )
        published_s = int(
            "F7CB1C942D657C41D436C7A1B6E29F65F3E900DBB9AFF4064DC4AB2F843ACDA8",
            16,
        )
        self.assertEqual(int(signature[64:], 16), order - published_s)
        self.assertTrue(
            verify_digest_hex(public_key_hex(private), digest, signature)
        )

    def test_signing_is_deterministic(self) -> None:
        private = int(DATA_KEY_HEX, 16)
        digest = hashlib.sha256(b"determinism").hexdigest()
        self.assertEqual(
            sign_digest_hex(private, digest), sign_digest_hex(private, digest)
        )

    def test_canonical_payload_rejects_missing_and_extra_fields(self) -> None:
        fields = {name: "x" for name in SIGNED_FIELDS}
        canonical_signed_payload(fields)
        with self.assertRaises(Exception):
            canonical_signed_payload({k: v for k, v in list(fields.items())[:-1]})
        with self.assertRaises(Exception):
            canonical_signed_payload({**fields, "extra": "x"})


DATA_KEY_HEX = (
    DATA / "enclave-signing-key.NOT-SECRET.hex"
).read_text(encoding="ascii").strip()


class LeanPinAgreementTests(unittest.TestCase):
    """The Python and Lean sides must pin the same literals."""

    def setUp(self) -> None:
        self.pin_text = LEAN_PIN.read_text(encoding="utf-8")
        self.dry_run_text = LEAN_DRY_RUN.read_text(encoding="utf-8")
        self.registry_text = LEAN_REGISTRY.read_text(encoding="utf-8")

    def test_dry_run_public_key_is_the_lean_pin(self) -> None:
        expected = public_key_hex(int(DATA_KEY_HEX, 16))
        self.assertIn(expected[:64], self.pin_text)
        self.assertIn(expected[64:], self.pin_text)
        self.assertEqual(
            expected, _lean_string_literals(self.dry_run_text, "dryRunPinnedKey")
        )

    def test_dry_run_pin_records_the_placeholder_evidence_hashes(self) -> None:
        self.assertIn(
            _sha256_file(DATA / "dcap-qvl-policy.json"), self.pin_text
        )
        self.assertIn(
            _sha256_file(DATA / "dcap-qvl-artifact.sha256"), self.pin_text
        )
        self.assertIn(DRY_RUN_APP_ID, self.pin_text)
        self.assertIn(DRY_RUN_COMPOSE_HASH, self.pin_text)
        self.assertIn(DRY_RUN_IMAGE_DIGEST.split(":", 1)[1], self.pin_text)

    def test_dry_run_pin_has_no_attestation_authority(self) -> None:
        block = self.pin_text[
            self.pin_text.index("ch25A7BoundaryLocalDryRunV1 =>") :
        ]
        self.assertIn("attestationAuthority := false", block)

    def test_production_pin_is_not_installed(self) -> None:
        block = self.pin_text[
            self.pin_text.index("ch25A7BoundaryProductionV1 =>") : self.pin_text.index(
                "ch25A7BoundaryLocalDryRunV1 =>"
            )
        ]
        self.assertIn('enclavePublicKeyHex := ""', block)

    def test_registered_algorithm_literals_match_the_producer(self) -> None:
        workload = (
            ROOT / "tools/tg_a7_phala_tdx_workload.py"
        ).read_text(encoding="utf-8")
        for literal in (
            "sparkinterval.ternary-goldbach.ch25-lemma-a7-boundary.v1",
            "340dc36f2ceb992ab16e34c534cd97b786d348ba057e159c295b3abd1328cdfa",
            "4e45410d2d26467dbd5f78f8ea536b1a8bbf44f1cd5248e234b985bd1f595674",
            "f377fb7b8c8d8d033083a0759841411d9bb955e919041f2a5b5be830ed69212e",
            "629d9c7b3c084ef33f69d92abbe22b5120bac210fc963191c4b1e8289ff1dea5",
        ):
            self.assertIn(literal, workload)
            self.assertIn(literal, self.registry_text)

    def test_canonical_payload_field_order_matches_lean(self) -> None:
        lean = LEAN_PIN.read_text(encoding="utf-8")
        body = lean[lean.index("def PhalaTdxReceipt.canonicalSignedPayload") :]
        body = body[: body.index("/-- SHA-256 of the canonical signed payload")]
        found = re.findall(r'phalaTdxCommittedField\s+"([a-z0-9_]+)"', body)
        self.assertEqual(tuple(found), SIGNED_FIELDS)


class DryRunReceiptTests(unittest.TestCase):
    """The receipt pinned in Lean is self-consistent and verifies."""

    def setUp(self) -> None:
        self.fields = self._lean_receipt_fields()

    @staticmethod
    def _lean_receipt_fields() -> dict[str, str]:
        text = LEAN_DRY_RUN.read_text(encoding="utf-8")
        body = text[text.index("def dryRunReceipt") : text.index(
            "def dryRunStatementDigest"
        )]
        lean_to_wire = {
            "algorithmId": "algorithm_id",
            "algorithmHash": "algorithm_hash",
            "inputHash": "input_hash",
            "parametersHash": "parameters_hash",
            "domainHash": "domain_hash",
            "result": "result",
            "outputHash": "output_hash",
            "challengeNonce": "challenge_nonce",
            "jobBindingHash": "job_binding_sha256",
            "appId": "app_id",
            "composeHash": "compose_hash",
            "imageDigest": "image_digest",
            "quoteHash": "tdx_quote_sha256",
            "quoteAppraisalHash": "dcap_qvl_output_sha256",
            "quoteAppraisalPolicyHash": "dcap_qvl_policy_sha256",
            "quoteAppraisalArtifactHash": "dcap_qvl_artifact_sha256",
            "reportDataHash": "report_data_sha256",
            "issuedAt": "issued_at",
        }
        fields: dict[str, str] = {}
        for lean_name, wire_name in lean_to_wire.items():
            match = re.search(
                rf"\b{lean_name}\s*:=\s*((?:\s*\"[^\"]*\"\s*(?:\+\+)?)+)", body
            )
            assert match, f"cannot find receipt field {lean_name}"
            fields[wire_name] = "".join(re.findall(r'"([^"]*)"', match.group(1)))
        return fields

    def test_lean_receipt_digest_matches_python(self) -> None:
        text = LEAN_DRY_RUN.read_text(encoding="utf-8")
        pinned = _lean_string_literals(text, "dryRunStatementDigest")
        self.assertEqual(statement_digest(self.fields), pinned)

    def test_lean_receipt_signature_verifies(self) -> None:
        text = LEAN_DRY_RUN.read_text(encoding="utf-8")
        body = text[text.index("def dryRunReceipt") :]
        match = re.search(
            r'signatureHex\s*:=\s*((?:\s*"[^"]*"\s*(?:\+\+)?)+)', body
        )
        assert match
        signature = "".join(re.findall(r'"([^"]*)"', match.group(1)))
        key = public_key_hex(int(DATA_KEY_HEX, 16))
        self.assertTrue(
            verify_digest_hex(key, statement_digest(self.fields), signature)
        )

    def test_report_data_binds_the_key_to_the_challenge(self) -> None:
        key = public_key_hex(int(DATA_KEY_HEX, 16))
        self.assertEqual(
            self.fields["report_data_sha256"],
            report_data_hash(
                enclave_public_key_hex=key,
                challenge_nonce=self.fields["challenge_nonce"],
                job_binding=self.fields["job_binding_sha256"],
            ),
        )

    def test_output_hash_binds_the_result(self) -> None:
        self.assertEqual(
            self.fields["output_hash"],
            hashlib.sha256(self.fields["result"].encode("ascii")).hexdigest(),
        )

    def test_placeholder_evidence_hashes_match_the_committed_files(
        self,
    ) -> None:
        self.assertEqual(
            self.fields["tdx_quote_sha256"],
            _sha256_file(DATA / "tdx-quote.NOT-A-QUOTE.bin"),
        )
        self.assertEqual(
            self.fields["dcap_qvl_output_sha256"],
            _sha256_file(DATA / "dcap-qvl-appraisal.NOT-AN-APPRAISAL.json"),
        )


class ContainerDryRunTests(unittest.TestCase):
    """Build and run the campaign image; compare with the Lean literals."""

    def test_container_reproduces_the_pinned_receipt(self) -> None:
        if not _docker_available():
            self.skipTest("docker cannot run linux/amd64 here")

        build = subprocess.run(
            [
                "docker", "build", "--platform", "linux/amd64",
                "-f", str(DOCKERFILE), "-t", IMAGE_TAG, str(ROOT),
            ],
            capture_output=True,
            text=True,
            timeout=3600,
        )
        self.assertEqual(
            build.returncode, 0, f"image build failed:\n{build.stderr[-4000:]}"
        )

        with tempfile.TemporaryDirectory() as workspace:
            work = Path(workspace)
            inputs = work / "input"
            outputs = work / "out"
            inputs.mkdir()
            outputs.mkdir()
            (inputs / "registered-input.json").write_bytes(REGISTERED_INPUT)
            with gzip.open(
                DATA / "a7_boundary.fixture.json.gz", "rb"
            ) as source:
                (inputs / "a7_boundary.json").write_bytes(source.read())
            shutil.copyfile(
                DATA / "enclave-signing-key.NOT-SECRET.hex",
                inputs / "enclave-signing-key.hex",
            )
            shutil.copyfile(
                DATA / "tdx-quote.NOT-A-QUOTE.bin", inputs / "tdx-quote.bin"
            )
            shutil.copyfile(
                DATA / "dcap-qvl-appraisal.NOT-AN-APPRAISAL.json",
                inputs / "dcap-qvl-appraisal.json",
            )
            shutil.copyfile(
                DATA / "dcap-qvl-policy.json", inputs / "dcap-qvl-policy.json"
            )
            shutil.copyfile(
                DATA / "dcap-qvl-artifact.sha256",
                inputs / "dcap-qvl-artifact.sha256",
            )
            for path in inputs.rglob("*"):
                os.chmod(path, 0o444)
            os.chmod(inputs, 0o555)

            uid, gid = os.getuid(), os.getgid()
            run = subprocess.run(
                [
                    "docker", "run", "--rm", "--platform", "linux/amd64",
                    "--user", f"{uid}:{gid}",
                    "--network", "none", "--read-only",
                    "-v", f"{inputs}:/workspace/input:ro",
                    "-v", f"{outputs}:/workspace/outroot",
                    "--tmpfs",
                    f"/workspace/runtime:exec,size=64m,uid={uid},gid={gid}",
                    "-e", "TG_OUTPUT_ROOT=/workspace/outroot/output",
                    "-e", f"TG_FINAL_IMAGE_REFERENCE={DRY_RUN_IMAGE_DIGEST}",
                    "-e", f"TG_ISSUED_AT={DRY_RUN_ISSUED_AT}",
                    "-e",
                    "SPARKINTERVAL_PHALA_TDX_WORKER_SCOPE="
                    "sparkinterval.phala-tdx-measured-worker.v1",
                    "-e",
                    "SPARKINTERVAL_PHALA_TDX_WORKER_BACKEND="
                    "phala_dstack_tdx_cpu",
                    "-e",
                    "SPARKINTERVAL_PHALA_TDX_WORKER_CHALLENGE_NONCE="
                    + DRY_RUN_CHALLENGE,
                    "-e",
                    "SPARKINTERVAL_PHALA_TDX_WORKER_JOB_BINDING_SHA256="
                    + DRY_RUN_JOB_BINDING,
                    "-e",
                    "SPARKINTERVAL_PHALA_TDX_WORKER_APP_ID=" + DRY_RUN_APP_ID,
                    "-e",
                    "SPARKINTERVAL_PHALA_TDX_WORKER_COMPOSE_HASH="
                    + DRY_RUN_COMPOSE_HASH,
                    "-e", "SPARKINTERVAL_PHALA_TDX_LOCAL_DRY_RUN=1",
                    IMAGE_TAG,
                ],
                capture_output=True,
                text=True,
                timeout=7200,
            )
            self.assertEqual(
                run.returncode,
                0,
                f"campaign run failed:\n{run.stdout[-4000:]}\n{run.stderr[-4000:]}",
            )

            produced = outputs / "output"
            self.assertEqual(
                (produced / "registered-result.txt").read_bytes(), b"true"
            )
            replay = json.loads(
                (produced / "work" / "a7-replay.json").read_text("utf-8")
            )
            self.assertIs(replay["accepted"], True)
            self.assertIs(
                replay["external_analytic_verification_complete"], True
            )
            self.assertIs(replay["lean_atom_discharged"], False)
            # The fixture is deliberately not the retained artifact.
            self.assertIs(replay["artifact_bytes_match_pinned_sha256"], False)

            receipt = json.loads(
                (produced / "enclave-receipt.json").read_text("utf-8")
            )
            self.assertIs(receipt["local_dry_run"], True)
            key = public_key_hex(int(DATA_KEY_HEX, 16))
            self.assertTrue(verify_receipt(receipt, enclave_public_key=key))

            pinned = DryRunReceiptTests._lean_receipt_fields()
            self.assertEqual(
                receipt["signed_fields"],
                pinned,
                "the container's receipt no longer matches the Lean dry-run "
                "literals; regenerate SparkInterval/Tests/PhalaTdxDryRunTest.lean",
            )
            text = LEAN_DRY_RUN.read_text(encoding="utf-8")
            self.assertEqual(
                receipt["statement_sha256"],
                _lean_string_literals(text, "dryRunStatementDigest"),
            )
            body = text[text.index("def dryRunReceipt") :]
            match = re.search(
                r'signatureHex\s*:=\s*((?:\s*"[^"]*"\s*(?:\+\+)?)+)', body
            )
            assert match
            self.assertEqual(
                receipt["signature"],
                "".join(re.findall(r'"([^"]*)"', match.group(1))),
            )


if __name__ == "__main__":
    unittest.main()
