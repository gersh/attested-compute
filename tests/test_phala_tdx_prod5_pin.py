# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""The committed prod5 pin is what the retained TDX evidence says it is.

`SparkInterval/Execution/PhalaTdxProd5Evidence.lean` carries a 130-character
public key, a 128-character signature and eighteen signed fields from a real
Intel TDX run.  If any one of those characters is wrong, Lean will happily
verify signatures against the wrong enclave forever.  So none of them is
trusted to a human's eyes:

* `tools/tg_phala_tdx_pin_from_evidence.py` re-derives every literal from
  `tests/data/phala_tdx_prod5/` and refuses unless the signature verifies, the
  report data commits to that key, and the deployment coordinates agree across
  four independent evidence files;
* this test runs it in `--check` mode, so the committed module must be exactly
  what the evidence produces;
* `Execution/PhalaTdxProd5Evidence.lean` additionally proves by `decide` that
  the hand-written pin case in `Execution/PhalaTdxAttestation.lean` equals the
  generated record, which is where a mistyped digit becomes a build failure.

The tamper cases below are the Python side of the Lean negative tests in
`SparkInterval/Tests/PhalaTdxProd5RunTest.lean`: the generator must refuse an
evidence directory whose signature, key, statement or exit status has been
disturbed.  A generator that emitted a pin anyway would be as bad as a
verifier that accepted anything.
"""

from __future__ import annotations

import hashlib
import json
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

from tg_verifier.phala_tdx_receipt import (  # noqa: E402
    statement_digest,
    verify_digest_hex,
)
from tools.tg_phala_tdx_pin_from_evidence import (  # noqa: E402
    PinError,
    load_evidence,
    render_module,
)

EVIDENCE = ROOT / "tests/data/phala_tdx_prod5"
RETAINED = EVIDENCE / "retained-evidence"
GENERATOR = ROOT / "tools/tg_phala_tdx_pin_from_evidence.py"
LEAN_GENERATED = ROOT / "SparkInterval/Execution/PhalaTdxProd5Evidence.lean"
LEAN_PIN = ROOT / "SparkInterval/Execution/PhalaTdxAttestation.lean"
LEAN_RUN_TEST = ROOT / "SparkInterval/Tests/PhalaTdxProd5RunTest.lean"

RECEIPT = json.loads(
    (RETAINED / "output/enclave-receipt.json").read_text(encoding="utf-8")
)


def _writable_copy(source: Path, destination: Path) -> None:
    """Copy the evidence tree, dropping the read-only bits it may carry."""

    shutil.copytree(source, destination)
    for path in destination.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)


def _repair_manifest(retained: Path, relative: str) -> None:
    """Re-stamp one manifest entry, so a mutation is not caught too early.

    The manifest digests are a transport-integrity check.  Repairing them is
    what makes the tamper tests below reach the checks that matter -- the
    signature, the report-data commitment, the cross-file agreement -- instead
    of stopping at "the transcript was altered".  A forger who edits a receipt
    would of course re-stamp the manifest too.
    """

    path = retained / "evidence-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    digest = hashlib.sha256((retained / relative).read_bytes()).hexdigest()
    root, _, name = relative.partition("/")
    for entry in manifest["files"]:
        if entry["root"] == root and entry["name"] == name:
            entry["sha256"] = digest
            entry["bytes"] = (retained / relative).stat().st_size
            break
    else:  # pragma: no cover - the fixture always lists these files
        raise AssertionError(f"{relative} is not in the manifest")
    path.write_text(json.dumps(manifest), encoding="utf-8")


def _mutated_json(tmp: Path, relative: str, mutate) -> Path:
    """Copy the evidence, mutate one JSON file, and re-stamp the manifest."""

    destination = tmp / "evidence"
    _writable_copy(EVIDENCE, destination)
    retained = destination / "retained-evidence"
    path = retained / relative
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    _repair_manifest(retained, relative)
    return destination


def _mutated_evidence(tmp: Path, mutate) -> Path:
    """Copy the evidence directory and apply `mutate` to the receipt dict."""

    return _mutated_json(tmp, "output/enclave-receipt.json", mutate)


class EvidenceIsAVerifiedRunTests(unittest.TestCase):
    """The retained evidence really is a verified TDX run, independently."""

    def test_the_evidence_directory_is_committed(self) -> None:
        for relative in (
            "run-scope.txt",
            "retained-evidence/evidence-manifest.json",
            "retained-evidence/output/enclave-receipt.json",
            "retained-evidence/output/registered-result.txt",
            "retained-evidence/input/tdx-quote.bin",
            "retained-evidence/input/dcap-qvl-appraisal.json",
            "retained-evidence/input/dcap-qvl-policy.json",
            "retained-evidence/evidence/prelude-summary.json",
            "retained-evidence/evidence/rtmr-replay.json",
            "retained-evidence/evidence/dcap-qvl-verify.stderr",
        ):
            self.assertTrue(
                (EVIDENCE / relative).is_file(), f"missing evidence {relative}"
            )

    def test_the_enclave_signature_verifies(self) -> None:
        digest = statement_digest(RECEIPT["signed_fields"])
        self.assertEqual(digest, RECEIPT["statement_sha256"])
        self.assertTrue(
            verify_digest_hex(
                RECEIPT["enclave_public_key"], digest, RECEIPT["signature"]
            ),
            "the retained enclave signature does not verify",
        )

    def test_an_independent_verifier_agrees(self) -> None:
        """Cross-check against OpenSSL, not just our own two verifiers.

        `tg_verifier/phala_tdx_receipt.py` and
        `SparkInterval/Certificate/P256.lean` were written to the same spec by
        the same author, so agreeing with each other is weak evidence.  This
        checks the same signature with a third implementation, and checks that
        it *refuses* the same two tamper cases the Lean kernel refuses in
        `prod5Signature_rejectsAlteredSignature` and
        `prod5Signature_rejectsAlteredStatement`.
        """

        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import ec, utils
        except ImportError:  # pragma: no cover - optional dependency
            self.skipTest("the `cryptography` package is not installed")

        key = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), bytes.fromhex(RECEIPT["enclave_public_key"])
        )
        algorithm = ec.ECDSA(utils.Prehashed(hashes.SHA256()))

        def verify(digest: bytes, signature: bytes) -> bool:
            der = utils.encode_dss_signature(
                int.from_bytes(signature[:32], "big"),
                int.from_bytes(signature[32:], "big"),
            )
            try:
                key.verify(der, digest, algorithm)
            except InvalidSignature:
                return False
            return True

        digest = bytes.fromhex(RECEIPT["statement_sha256"])
        signature = bytes.fromhex(RECEIPT["signature"])
        self.assertTrue(verify(digest, signature))

        altered_digest = bytearray(digest)
        altered_digest[-1] ^= 1
        self.assertFalse(verify(bytes(altered_digest), signature))

        altered_signature = bytearray(signature)
        altered_signature[-1] ^= 1
        self.assertFalse(verify(digest, bytes(altered_signature)))

    def test_no_signing_key_was_retained(self) -> None:
        """The evidence must carry the public key and nothing more."""

        for path in EVIDENCE.rglob("*"):
            if not path.is_file():
                continue
            name = path.name.lower()
            for forbidden in ("signing-key", "enclave-key", "private", "secret"):
                self.assertNotIn(forbidden, name, f"{path} looks like key material")


class GeneratorAgreementTests(unittest.TestCase):
    """The committed Lean module is the generator's output, byte for byte."""

    def test_committed_module_matches_the_generator(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(GENERATOR),
                "--evidence-dir",
                str(EVIDENCE),
                "--out",
                str(LEAN_GENERATED),
                "--check",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            completed.returncode,
            0,
            "SparkInterval/Execution/PhalaTdxProd5Evidence.lean does not match "
            "tests/data/phala_tdx_prod5; regenerate it with "
            "tools/tg_phala_tdx_pin_from_evidence.py\n"
            + completed.stdout
            + completed.stderr,
        )

    def test_generation_is_deterministic(self) -> None:
        first = render_module(load_evidence(EVIDENCE))
        second = render_module(load_evidence(EVIDENCE))
        self.assertEqual(first, second)
        self.assertEqual(
            first, LEAN_GENERATED.read_text(encoding="utf-8")
        )

    def test_the_hand_written_pin_case_carries_the_same_literals(self) -> None:
        """The literals in the trust-boundary edit are the derived ones.

        Lean proves this too (`phalaTdxProd5_pin_eq_generated`, by `decide`);
        this is the cheap source-level echo of it, so a mistake is visible
        without a build.
        """

        data = load_evidence(EVIDENCE)
        pin_text = LEAN_PIN.read_text(encoding="utf-8")
        block = pin_text[
            pin_text.index("ch25A7BoundaryPhalaProd5V1 =>"): pin_text.index(
                "ch25A7BoundaryPhalaProd5TamperedKeyV1 =>"
            )
        ]
        self.assertIn(data["app_id"], block)
        self.assertIn(data["compose_hash"], block)
        self.assertIn(data["image_digest"], block)
        self.assertIn(data["policy_hash"], block)
        self.assertIn(data["artifact_hash"], block)
        self.assertIn(data["public_key"][:64], block)
        self.assertIn(data["public_key"][64:], block)
        self.assertIn("attestationAuthority := true", block)

    def test_the_negative_test_pin_never_carries_authority(self) -> None:
        pin_text = LEAN_PIN.read_text(encoding="utf-8")
        block = pin_text[
            pin_text.index("ch25A7BoundaryPhalaProd5TamperedKeyV1 =>"):
        ]
        self.assertIn("attestationAuthority := false", block)
        self.assertNotIn("attestationAuthority := true", block)

    def test_only_the_prod5_identity_gained_authority(self) -> None:
        """Exactly one enclave pin in the closed set is a new authority.

        `ch25A7BoundaryProductionV1` has carried `attestationAuthority := true`
        with an empty key since the module was written -- it fails closed.  The
        prod5 identity is the only one whose authority is backed by a real key.
        """

        pin_text = LEAN_PIN.read_text(encoding="utf-8")
        self.assertIn('enclavePublicKeyHex := ""', pin_text)
        assignments = re.findall(
            r"^\s*attestationAuthority := (true|false)\s*\}?\s*$",
            pin_text,
            re.MULTILINE,
        )
        self.assertEqual(assignments.count("true"), 2, assignments)
        self.assertEqual(assignments.count("false"), 2, assignments)

    def test_the_lean_run_test_uses_the_generated_names(self) -> None:
        text = LEAN_RUN_TEST.read_text(encoding="utf-8")
        for name in (
            "prod5Signature_kernelChecked",
            "prod5OutcomeAccepted",
            "prod5Outcome_rejectsAlteredKey",
            "prod5Outcome_rejectsAlteredSignature",
            "prod5Outcome_rejectsAlteredStatement",
            "prod5Outcome_rejectsAlteredComposeHash",
            "prod5Outcome_rejectsAlteredAppId",
            "prod5Campaign",
        ):
            self.assertIn(name, text, f"the Lean run test lost {name}")


class GeneratorRefusalTests(unittest.TestCase):
    """A disturbed evidence directory must produce no pin at all."""

    def _refuses(self, mutate, fragment: str) -> None:
        with tempfile.TemporaryDirectory(prefix="phala-prod5-") as raw:
            directory = _mutated_evidence(Path(raw), mutate)
            with self.assertRaises(PinError) as caught:
                load_evidence(directory)
            self.assertIn(fragment, str(caught.exception).lower())

    def test_refuses_an_altered_signature(self) -> None:
        def mutate(receipt: dict) -> None:
            signature = receipt["signature"]
            receipt["signature"] = signature[:-1] + (
                "0" if signature[-1] != "0" else "1"
            )

        self._refuses(mutate, "signature does not verify")

    def test_refuses_an_altered_public_key(self) -> None:
        def mutate(receipt: dict) -> None:
            key = receipt["enclave_public_key"]
            receipt["enclave_public_key"] = key[:-1] + (
                "0" if key[-1] != "0" else "1"
            )

        # Two guards refuse it: the signature no longer verifies under the
        # altered key, and the report-data commitment -- which is a digest of
        # the key -- no longer matches what the quote attests.  The signature
        # check is simply the one reached first.
        self._refuses(mutate, "signature does not verify")

    def test_refuses_an_altered_statement(self) -> None:
        def mutate(receipt: dict) -> None:
            receipt["signed_fields"]["issued_at"] = "2026-07-27T21:48:10Z"

        self._refuses(mutate, "canonical payload hashes to")

    def test_refuses_an_altered_compose_hash(self) -> None:
        def mutate(receipt: dict) -> None:
            compose = receipt["signed_fields"]["compose_hash"]
            receipt["signed_fields"]["compose_hash"] = compose[:-1] + "0"

        self._refuses(mutate, "canonical payload hashes to")

    def test_refuses_a_dry_run_receipt(self) -> None:
        def mutate(receipt: dict) -> None:
            receipt["local_dry_run"] = True

        self._refuses(mutate, "local dry run")

    def test_refuses_a_failed_campaign(self) -> None:
        with tempfile.TemporaryDirectory(prefix="phala-prod5-") as raw:
            directory = Path(raw) / "evidence"
            _writable_copy(EVIDENCE, directory)
            path = directory / "retained-evidence/evidence-manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["campaign_exit_status"] = 1
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(PinError) as caught:
                load_evidence(directory)
            self.assertIn("exit 0", str(caught.exception))

    def test_refuses_a_tampered_retained_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="phala-prod5-") as raw:
            directory = Path(raw) / "evidence"
            _writable_copy(EVIDENCE, directory)
            quote = directory / "retained-evidence/input/tdx-quote.bin"
            raw_bytes = bytearray(quote.read_bytes())
            raw_bytes[0] ^= 0xFF
            quote.write_bytes(bytes(raw_bytes))
            with self.assertRaises(PinError) as caught:
                load_evidence(directory)
            self.assertIn("manifest states", str(caught.exception))

    def test_refuses_an_unpinned_measurement_run(self) -> None:
        def mutate(summary: dict) -> None:
            summary["measurements_pinned"] = False

        with tempfile.TemporaryDirectory(prefix="phala-prod5-") as raw:
            directory = _mutated_json(
                Path(raw), "evidence/prelude-summary.json", mutate
            )
            with self.assertRaises(PinError) as caught:
                load_evidence(directory)
            self.assertIn("unpinned measurements", str(caught.exception))

    def test_refuses_a_prelude_that_names_another_key(self) -> None:
        """The prelude and the receipt must agree about the enclave key."""

        def mutate(summary: dict) -> None:
            key = summary["enclave_public_key"]
            summary["enclave_public_key"] = key[:-1] + "0"

        with tempfile.TemporaryDirectory(prefix="phala-prod5-") as raw:
            directory = _mutated_json(
                Path(raw), "evidence/prelude-summary.json", mutate
            )
            with self.assertRaises(PinError) as caught:
                load_evidence(directory)
            self.assertIn("enclave public key", str(caught.exception))

    def test_refuses_an_rtmr_replay_that_names_another_app(self) -> None:
        """The measured boot chain must bind the app id the receipt signed."""

        def mutate(replay: dict) -> None:
            app = replay["rtmr3_bindings"]["app-id"]
            replay["rtmr3_bindings"]["app-id"] = app[:-1] + "0"

        with tempfile.TemporaryDirectory(prefix="phala-prod5-") as raw:
            directory = _mutated_json(
                Path(raw), "evidence/rtmr-replay.json", mutate
            )
            with self.assertRaises(PinError) as caught:
                load_evidence(directory)
            self.assertIn("reports app id", str(caught.exception))

    def test_refuses_a_run_scope_that_does_not_match(self) -> None:
        with tempfile.TemporaryDirectory(prefix="phala-prod5-") as raw:
            directory = Path(raw) / "evidence"
            _writable_copy(EVIDENCE, directory)
            scope = directory / "run-scope.txt"
            scope.write_text(
                "challenge=" + "00" * 32 + "\n"
                "job_binding=" + "11" * 32 + "\n"
                "issued_at=2026-07-27T21:48:16Z\n",
                encoding="utf-8",
            )
            with self.assertRaises(PinError) as caught:
                load_evidence(directory)
            self.assertIn("run scope challenge", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
