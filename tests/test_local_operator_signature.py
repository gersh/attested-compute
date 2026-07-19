from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
TOOLS = REPOSITORY / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import create_run_bundle as create  # noqa: E402
import local_operator_signature as signing  # noqa: E402
import verify_run_bundle as verify  # noqa: E402


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL is required")
class LocalOperatorSignatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.input_path = self.root / "data/input.bin"
        self.output_path = self.root / "data/output.bin"
        self.runner_path = self.root / "bin/runner"
        self.kernel_path = self.root / "gpu/kernel.cubin"
        for path, contents in (
            (self.input_path, b"zeta-input-v1"),
            (self.output_path, b"zeta-output-v1"),
            (self.runner_path, b"host-runner-v1"),
            (self.kernel_path, b"gpu-cubin-v1"),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)

        self.private_key = self.root / "keys/operator-private.pem"
        self.public_key = self.root / "keys/operator-public.pem"
        signing.generate_keypair(
            self.private_key,
            self.public_key,
            allow_unencrypted_private_key=True,
        )
        self.bundle = self._make_bundle()
        self.bundle_path = self.root / "run-bundle.json"
        create.write_bundle(self.bundle, self.bundle_path)
        self.signature_path = self.root / "run-bundle.signature.json"
        self.envelope, _ = signing.sign_bundle_file(
            self.bundle_path,
            self.private_key,
            self.signature_path,
            artifact_root=self.root,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _profile(kind: str, profile_id: str) -> dict:
        directory = "targets" if kind == "target" else "trust"
        return create.load_profile(
            REPOSITORY / "profiles" / directory / f"{profile_id}.json", kind
        )

    def _make_bundle(self, target: str = "dgx_spark_sm121") -> dict:
        return create.create_bundle(
            root=self.root,
            target_profile=self._profile("target", target),
            trust_profile=self._profile("trust", "local_unattested"),
            algorithm_id="RiemannZeta.POC.v1",
            algorithm_definition_sha256="ab" * 32,
            input_path=self.input_path,
            parameters={"working_precision_bits": 256, "zeta_method_version": 1},
            domain_coverage={
                "variable": "t",
                "lower_numerator": 0,
                "lower_denominator": 1,
                "upper_numerator": 100,
                "upper_denominator": 1,
                "endpoint_policy": "closed",
            },
            output_path=self.output_path,
            nonce="42" * 32,
            build_artifacts=[
                ("host_executable", self.runner_path),
                ("gpu_cubin", self.kernel_path),
            ],
            execution_environment={
                "device_name": "NVIDIA GB10",
                "compute_capability": "12.1",
                "hardware_attestation": None,
            },
            completion={
                "status": "success",
                "exit_code": 0,
                "expected_output_count": 17,
                "written_output_count": 17,
                "cuda_errors": [],
                "start_time_utc": "2026-07-19T12:00:00Z",
                "end_time_utc": "2026-07-19T12:00:01Z",
            },
        )

    def _verify_signed(self, **changes: object) -> dict:
        arguments: dict[str, object] = {
            "artifact_root": self.root,
            "policy": verify.DGX_OPERATOR_SIGNED_POLICY,
            "seen_nonces": set(),
            "operator_signature": self.envelope,
            "trusted_operator_public_key": self.public_key,
        }
        arguments.update(changes)
        return verify.verify_bundle(self.bundle, **arguments)

    def test_keygen_sign_and_pinned_policy_accept_without_hardware_claim(self) -> None:
        result = self._verify_signed()

        self.assertTrue(result["accepted"])
        self.assertTrue(result["artifacts_verified"])
        self.assertTrue(result["operator_signature_valid"])
        self.assertEqual(result["operator_key_id"], self.envelope["key_id"])
        self.assertFalse(result["hardware_evidence"])
        self.assertEqual(
            result["assurance"],
            "operator_signed_local_record_not_hardware_evidence",
        )
        self.assertEqual(self.bundle["evidence"]["evidence_class"], "local_unattested")
        self.assertIsNone(self.bundle["evidence"]["hardware_attestation"])
        self.assertEqual(
            self.signature_path.read_bytes(), create.canonical_json_bytes(self.envelope)
        )
        self.assertEqual(stat.S_IMODE(self.private_key.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.public_key.stat().st_mode), 0o644)

    def test_policy_requires_artifacts_replay_signature_and_pinned_key(self) -> None:
        with self.assertRaisesRegex(verify.VerificationError, "all artifact bytes"):
            self._verify_signed(artifact_root=None)
        with self.assertRaisesRegex(verify.VerificationError, "replay protection"):
            self._verify_signed(seen_nonces=None)
        with self.assertRaisesRegex(verify.VerificationError, "detached operator signature"):
            self._verify_signed(operator_signature=None)
        with self.assertRaisesRegex(verify.VerificationError, "pinned operator public key"):
            self._verify_signed(trusted_operator_public_key=None)

    def test_signature_and_payload_tampering_are_rejected(self) -> None:
        bad_signature = copy.deepcopy(self.envelope)
        raw = bytearray(base64.b64decode(bad_signature["signature_base64"]))
        raw[0] ^= 1
        bad_signature["signature_base64"] = base64.b64encode(raw).decode("ascii")
        with self.assertRaisesRegex(verify.VerificationError, "OpenSSL rejected"):
            self._verify_signed(operator_signature=bad_signature)

        bad_payload = copy.deepcopy(self.envelope)
        bad_payload["signed_payload"]["bundle_file_sha256"] = "00" * 32
        with self.assertRaisesRegex(verify.VerificationError, "exact run bundle"):
            self._verify_signed(operator_signature=bad_payload)

        unknown_field = copy.deepcopy(self.envelope)
        unknown_field["claims_hardware"] = False
        with self.assertRaisesRegex(verify.VerificationError, "wrong fields"):
            self._verify_signed(operator_signature=unknown_field)

    def test_embedded_key_does_not_replace_out_of_band_key_pinning(self) -> None:
        other_private = self.root / "keys/other-private.pem"
        other_public = self.root / "keys/other-public.pem"
        signing.generate_keypair(
            other_private,
            other_public,
            allow_unencrypted_private_key=True,
        )
        with self.assertRaisesRegex(verify.VerificationError, "pinned trusted public key"):
            self._verify_signed(trusted_operator_public_key=other_public)

    def test_artifact_tampering_is_rejected_before_signature_acceptance(self) -> None:
        self.output_path.write_bytes(b"tampered result")
        with self.assertRaisesRegex(verify.VerificationError, "output artifact"):
            self._verify_signed()

    def test_nonce_is_recorded_only_after_signature_acceptance(self) -> None:
        seen: set[str] = set()
        self._verify_signed(seen_nonces=seen)
        self.assertEqual(seen, {"42" * 32})
        with self.assertRaisesRegex(verify.VerificationError, "replayed nonce"):
            self._verify_signed(seen_nonces=seen)

        rejected_seen: set[str] = set()
        bad = copy.deepcopy(self.envelope)
        bad["warning"] = "not the required warning"
        with self.assertRaises(verify.VerificationError):
            self._verify_signed(seen_nonces=rejected_seen, operator_signature=bad)
        self.assertEqual(rejected_seen, set())

    def test_integrity_policy_rejects_unused_signature_inputs(self) -> None:
        with self.assertRaisesRegex(
            verify.VerificationError, "require policy dgx_operator_signed"
        ):
            verify.verify_bundle(
                self.bundle,
                artifact_root=self.root,
                operator_signature=self.envelope,
                trusted_operator_public_key=self.public_key,
            )

    def test_signer_rejects_non_dgx_bundle_and_noncanonical_envelope(self) -> None:
        h100_bundle = self._make_bundle("h100_sm90")
        h100_path = self.root / "h100-run-bundle.json"
        create.write_bundle(h100_bundle, h100_path)
        with self.assertRaisesRegex(signing.LocalSignatureError, "restricted to DGX"):
            signing.sign_bundle_file(
                h100_path,
                self.private_key,
                self.root / "h100.signature.json",
                artifact_root=self.root,
            )

        pretty = self.root / "pretty-signature.json"
        pretty.write_text(json.dumps(self.envelope, indent=2), encoding="utf-8")
        with self.assertRaisesRegex(signing.LocalSignatureError, "not canonical JSON"):
            signing.load_signature(pretty)

    def test_key_generation_requires_explicit_secret_handling_and_no_overwrite(self) -> None:
        private = self.root / "keys/new-private.pem"
        public = self.root / "keys/new-public.pem"
        with self.assertRaisesRegex(signing.LocalSignatureError, "choose exactly one"):
            signing.generate_keypair(private, public)

        signing.generate_keypair(
            private,
            public,
            allow_unencrypted_private_key=True,
        )
        original = private.read_bytes()
        with self.assertRaisesRegex(signing.LocalSignatureError, "refusing to overwrite"):
            signing.generate_keypair(
                private,
                self.root / "keys/unused-public.pem",
                allow_unencrypted_private_key=True,
            )
        self.assertEqual(private.read_bytes(), original)

        os.chmod(private, 0o644)
        with self.assertRaisesRegex(signing.LocalSignatureError, "group or other"):
            signing.create_signature_envelope(
                self.bundle_path.read_bytes(), self.bundle, private
            )

    def test_encrypted_private_key_is_supported_with_0600_passphrase_file(self) -> None:
        passphrase = self.root / "keys/passphrase.txt"
        passphrase.write_text("correct horse battery staple\n", encoding="utf-8")
        os.chmod(passphrase, 0o600)
        private = self.root / "keys/encrypted-private.pem"
        public = self.root / "keys/encrypted-public.pem"
        info = signing.generate_keypair(
            private,
            public,
            passphrase_file=passphrase,
        )
        self.assertTrue(info["private_key_encrypted"])
        envelope = signing.create_signature_envelope(
            self.bundle_path.read_bytes(),
            self.bundle,
            private,
            passphrase_file=passphrase,
        )
        checked = signing.verify_signature(self.bundle, envelope, public)
        self.assertTrue(checked["signature_valid"])

    def test_cli_policy_is_fail_closed_and_replay_protected(self) -> None:
        database = self.root / "state/replay.sqlite3"
        command = [
            sys.executable,
            str(TOOLS / "verify_run_bundle.py"),
            str(self.bundle_path),
            "--artifact-root",
            str(self.root),
            "--policy",
            verify.DGX_OPERATOR_SIGNED_POLICY,
            "--replay-db",
            str(database),
            "--operator-signature",
            str(self.signature_path),
            "--trusted-operator-key",
            str(self.public_key),
        ]
        first = subprocess.run(command, check=False, capture_output=True, text=True)
        second = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 2)
        self.assertIn("replayed nonce", second.stderr)
        result = json.loads(first.stdout)
        self.assertTrue(result["operator_signature_valid"])
        self.assertFalse(result["hardware_evidence"])
        with sqlite3.connect(database) as connection:
            count = connection.execute("SELECT COUNT(*) FROM accepted_nonces").fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
