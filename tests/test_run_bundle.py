from __future__ import annotations

import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
TOOLS = REPOSITORY / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import create_run_bundle as create  # noqa: E402
import verify_run_bundle as verify  # noqa: E402


class RunBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.input_path = self.root / "data" / "input.bin"
        self.output_path = self.root / "data" / "output.bin"
        self.runner_path = self.root / "bin" / "runner"
        self.kernel_path = self.root / "gpu" / "kernel.cubin"
        self.attestation_path = self.root / "evidence" / "attestation.bin"
        for path, contents in (
            (self.input_path, b"input-v1\x00\x01"),
            (self.output_path, b"output-v1\x02\x03"),
            (self.runner_path, b"host executable"),
            (self.kernel_path, b"gpu executable"),
            (self.attestation_path, b"placeholder NVIDIA evidence"),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)

        self.parameters = {
            "algorithm_version": 1,
            "working_precision_bits": 256,
        }
        self.coverage = {
            "variable": "t",
            "lower_numerator": 0,
            "lower_denominator": 1,
            "upper_numerator": 1000000,
            "upper_denominator": 1,
            "endpoint_policy": "closed",
        }
        self.environment = {
            "device_uuid": "GPU-test",
            "driver_version": "test-only",
            "gpu_architecture": "sm_test",
        }
        self.completion = {
            "status": "success",
            "exit_code": 0,
            "expected_output_count": 17,
            "written_output_count": 17,
            "cuda_errors": [],
            "start_time_utc": "2026-07-18T12:00:00Z",
            "end_time_utc": "2026-07-18T12:00:01.125Z",
        }
        self.nonce = "12" * 32

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def profile(self, kind: str, profile_id: str) -> dict:
        directory = "targets" if kind == "target" else "trust"
        return create.load_profile(
            REPOSITORY / "profiles" / directory / f"{profile_id}.json", kind
        )

    def make_bundle(
        self,
        target: str = "dgx_spark_sm121",
        trust: str = "local_unattested",
    ) -> dict:
        hardware_path = None
        hardware_format = None
        if trust == "h100_hardware_attested":
            hardware_path = self.attestation_path
            hardware_format = "nvidia_cc_evidence"
        return create.create_bundle(
            root=self.root,
            target_profile=self.profile("target", target),
            trust_profile=self.profile("trust", trust),
            algorithm_id="RiemannZeta.verify.v1",
            algorithm_definition_sha256="ab" * 32,
            input_path=self.input_path,
            parameters=self.parameters,
            domain_coverage=self.coverage,
            output_path=self.output_path,
            nonce=self.nonce,
            build_artifacts=[
                ("host_executable", self.runner_path),
                ("gpu_executable", self.kernel_path),
            ],
            execution_environment=self.environment,
            completion=self.completion,
            hardware_attestation_path=hardware_path,
            hardware_attestation_format=hardware_format,
        )

    @staticmethod
    def rehash(bundle: dict) -> None:
        bundle["statement_sha256"] = create.canonical_sha256(bundle["statement"])
        evidence = bundle["evidence"]
        if evidence["mock_attestation"] is not None:
            evidence["mock_attestation"]["expected_report_data_sha256"] = bundle[
                "statement_sha256"
            ]
        if evidence["hardware_attestation"] is not None:
            evidence["hardware_attestation"][
                "expected_report_data_sha256"
            ] = bundle["statement_sha256"]
        core = {key: bundle[key] for key in (
            "schema_version",
            "bundle_kind",
            "statement",
            "statement_sha256",
            "evidence",
        )}
        bundle["bundle_sha256"] = create.canonical_sha256(core)

    def test_dgx_bundle_is_canonical_local_and_binds_run(self) -> None:
        bundle = self.make_bundle()
        manifest = self.root / "run-bundle.json"
        create.write_bundle(bundle, manifest)

        self.assertEqual(manifest.read_bytes(), create.canonical_json_bytes(bundle))
        self.assertEqual(bundle["evidence"]["evidence_class"], "local_unattested")
        self.assertIsNone(bundle["evidence"]["hardware_attestation"])
        self.assertEqual(bundle["statement"]["nonce"], self.nonce)
        self.assertEqual(
            bundle["statement"]["algorithm"]["definition_sha256"], "ab" * 32
        )
        self.assertEqual(
            bundle["statement"]["parameters"]["canonical_sha256"],
            create.canonical_sha256(self.parameters),
        )
        self.assertEqual(
            bundle["statement"]["domain_coverage"]["canonical_sha256"],
            create.canonical_sha256(self.coverage),
        )

        result = verify.verify_bundle_file(manifest, artifact_root=self.root)
        self.assertTrue(result["accepted"])
        self.assertTrue(result["artifacts_verified"])
        self.assertFalse(result["hardware_evidence"])
        self.assertEqual(result["assurance"], "local_record_not_hardware_evidence")

    def test_json_floats_constants_and_duplicate_keys_are_rejected(self) -> None:
        with self.assertRaises(create.BundleError):
            create.canonical_json_bytes({"precision": 1.0})
        for data in (b'{"x":1.0}', b'{"x":NaN}', b'{"x":1,"x":2}'):
            with self.subTest(data=data):
                with self.assertRaises(create.BundleError):
                    create.parse_json_bytes(data)

    def test_noncanonical_bundle_file_is_rejected(self) -> None:
        bundle = self.make_bundle()
        manifest = self.root / "pretty.json"
        manifest.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
        with self.assertRaisesRegex(verify.VerificationError, "not canonical JSON"):
            verify.verify_bundle_file(manifest)

    def test_manifest_corruption_is_detected(self) -> None:
        bundle = self.make_bundle()
        corrupted = copy.deepcopy(bundle)
        corrupted["statement"]["completion"]["written_output_count"] = 16
        with self.assertRaisesRegex(verify.VerificationError, "statement SHA-256"):
            verify.verify_bundle(corrupted)

    def test_artifact_corruption_is_detected(self) -> None:
        bundle = self.make_bundle()
        self.output_path.write_bytes(b"tampered output")
        with self.assertRaisesRegex(verify.VerificationError, "output artifact"):
            verify.verify_bundle(bundle, artifact_root=self.root)

    def test_replay_nonce_is_rejected(self) -> None:
        bundle = self.make_bundle()
        seen: set[str] = set()
        verify.verify_bundle(bundle, artifact_root=self.root, seen_nonces=seen)
        self.assertIn(self.nonce, seen)
        with self.assertRaisesRegex(verify.VerificationError, "replayed nonce"):
            verify.verify_bundle(bundle, artifact_root=self.root, seen_nonces=seen)

    def test_wrong_profile_hash_is_rejected_even_after_rehash(self) -> None:
        bundle = self.make_bundle()
        wrong = copy.deepcopy(bundle)
        wrong["statement"]["target_profile"]["profile_id"] = "h100_sm90"
        self.rehash(wrong)
        with self.assertRaisesRegex(verify.VerificationError, "profile hash"):
            verify.verify_bundle(wrong)

    def test_dgx_cannot_be_created_with_mock_trust(self) -> None:
        with self.assertRaisesRegex(create.BundleError, "does not allow mock_attested"):
            self.make_bundle("dgx_spark_sm121", "mock_attested")

    def test_h100_local_record_is_rejected_as_production_hardware_evidence(self) -> None:
        bundle = self.make_bundle("h100_sm90", "local_unattested")
        with self.assertRaisesRegex(
            verify.VerificationError, "rejects local and mock trust profiles"
        ):
            verify.verify_bundle(
                bundle,
                artifact_root=self.root,
                policy=verify.H100_PRODUCTION_POLICY,
                seen_nonces=set(),
                attestation_validator=lambda path, fmt, digest: True,
            )

    def test_mock_is_separate_and_rejected_as_production_hardware_evidence(self) -> None:
        bundle = self.make_bundle("h100_sm90", "mock_attested")
        self.assertIsNone(bundle["evidence"]["hardware_attestation"])
        local_result = verify.verify_bundle(bundle, artifact_root=self.root)
        self.assertFalse(local_result["hardware_evidence"])
        self.assertEqual(local_result["assurance"], "mock_only_not_hardware_evidence")

        with self.assertRaisesRegex(
            verify.VerificationError, "rejects local and mock trust profiles"
        ):
            verify.verify_bundle(
                bundle,
                artifact_root=self.root,
                policy=verify.H100_PRODUCTION_POLICY,
                seen_nonces=set(),
                attestation_validator=lambda path, fmt, digest: True,
            )

    def test_h100_production_fails_closed_without_attestation_verifier(self) -> None:
        bundle = self.make_bundle("h100_sm90", "h100_hardware_attested")
        with self.assertRaisesRegex(
            verify.VerificationError, "no trusted H100 attestation verifier"
        ):
            verify.verify_bundle(
                bundle,
                artifact_root=self.root,
                policy=verify.H100_PRODUCTION_POLICY,
                seen_nonces=set(),
            )

    def test_h100_production_accepts_only_explicit_trusted_verifier_result(self) -> None:
        bundle = self.make_bundle("h100_sm90", "h100_hardware_attested")
        calls: list[tuple[Path, str, str]] = []

        def validator(path: Path, evidence_format: str, digest: str) -> bool:
            calls.append((path, evidence_format, digest))
            return True

        result = verify.verify_bundle(
            bundle,
            artifact_root=self.root,
            policy=verify.H100_PRODUCTION_POLICY,
            seen_nonces=set(),
            attestation_validator=validator,
        )
        self.assertTrue(result["hardware_evidence"])
        self.assertEqual(result["assurance"], "h100_hardware_attested")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], "nvidia_cc_evidence")
        self.assertEqual(calls[0][2], bundle["statement_sha256"])

    def test_cli_replay_database_rejects_second_acceptance(self) -> None:
        bundle = self.make_bundle()
        manifest = self.root / "run-bundle.json"
        database = self.root / "state" / "replay.sqlite3"
        create.write_bundle(bundle, manifest)
        command = [
            sys.executable,
            str(TOOLS / "verify_run_bundle.py"),
            str(manifest),
            "--artifact-root",
            str(self.root),
            "--replay-db",
            str(database),
        ]
        first = subprocess.run(command, check=False, capture_output=True, text=True)
        second = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 2)
        self.assertIn("replayed nonce", second.stderr)
        with sqlite3.connect(database) as connection:
            count = connection.execute("SELECT COUNT(*) FROM accepted_nonces").fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
