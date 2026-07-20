from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
TOOLS = REPOSITORY / "tools"
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from reference import evaluator  # noqa: E402
from reference import format as wire  # noqa: E402
import create_dgx_generated_cubin_bundle as packager  # noqa: E402
import create_run_bundle as bundle_format  # noqa: E402
import verify_run_bundle as bundle_verify  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


class GeneratedCubinBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.work = self.root / "retained"
        self.bin = self.root / "bin"
        self.work.mkdir()
        self.bin.mkdir()
        self.generator = self.executable("sparkinterval-gen", b"generator-v1")
        self.driver = self.executable("generated-driver", b"driver-v1")
        self.phase4 = self.executable("phase4-runner", b"phase4-v1")
        self.ptxas = self.executable("ptxas", b"ptxas-test-v1")
        self.nvdisasm = self.executable("nvdisasm", b"nvdisasm-test-v1")
        self.make_retained_run()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def executable(self, name: str, marker: bytes) -> Path:
        path = self.bin / name
        path.write_bytes(b"#!/bin/sh\n# " + marker + b"\nexit 0\n")
        path.chmod(0o755)
        return path

    @staticmethod
    def main_batch() -> dict:
        return wire.validate_batch(
            {
                "schema_version": wire.SCHEMA_VERSION,
                "kind": wire.BATCH_KIND,
                "algorithm": wire.ALGORITHM_ID,
                "variable_count": 2,
                "expression": {
                    "op": "mul",
                    "left": {"op": "var", "index": 0},
                    "right": {"op": "var", "index": 1},
                },
                "rows": [
                    [
                        {"lo": "3ff0000000000000", "hi": "3ff0000000000000"},
                        {"lo": "4000000000000000", "hi": "4000000000000000"},
                    ],
                    [
                        {"lo": "4008000000000000", "hi": "4008000000000000"},
                        {"lo": "4010000000000000", "hi": "4010000000000000"},
                    ],
                ],
            }
        )

    @staticmethod
    def hardware(
        row_count: int,
        *,
        module: Path,
        rows: Path,
        results: Path,
        challenge_nonce: str | None,
    ) -> dict:
        encoded_rows = rows.read_bytes()
        input_payload = encoded_rows[packager.GENERATED_HEADER.size :]
        return {
            "schema_version": 1,
            "kind": "sparkinterval_generated_driver_run",
            "byte_binding_schema_version": 1,
            "challenge_nonce": challenge_nonce,
            "module_kind": "offline_cubin",
            "module_sha256": sha256(module),
            "module_size_bytes": module.stat().st_size,
            "input_payload_sha256": hashlib.sha256(input_payload).hexdigest(),
            "input_payload_size_bytes": len(input_payload),
            "output_file_sha256": sha256(results),
            "output_file_size_bytes": results.stat().st_size,
            "device_count": 1,
            "device_index": 0,
            "device_name": "NVIDIA GB10",
            "device_uuid": "12" * 16,
            "compute_capability": "12.1",
            "cuda_driver_version": 13000,
            "allow_other_device": False,
            "row_count": row_count,
            "target": "sm_121",
            "target_device_policy": "exact-NVIDIA-GB10-compute-capability-12.1",
        }

    @staticmethod
    def lowering_model() -> dict:
        return {
            "schema_version": 1,
            "analysis_kind": "generated_ptx_demand_and_value_numbering_v1",
            "passed": True,
            "errors": [],
            "expected_sass_counts": {
                key: 0 for key in sorted(packager.EXPECTED_SASS_COUNT_KEYS)
            },
        }

    def write_rows(self, name: str, batch: dict) -> Path:
        encoded = bytearray(
            packager.GENERATED_HEADER.pack(
                packager.INPUT_MAGIC,
                1,
                batch["variable_count"],
                len(batch["rows"]),
            )
        )
        for row in batch["rows"]:
            for interval in row:
                encoded += packager.INTERVAL.pack(
                    int(interval["lo"], 16), int(interval["hi"], 16)
                )
        path = self.work / name
        path.write_bytes(encoded)
        return path

    def result_bytes(self, batch: dict) -> bytes:
        exact = evaluator.evaluate_batch(batch)
        encoded = bytearray(
            packager.GENERATED_HEADER.pack(
                packager.OUTPUT_MAGIC,
                1,
                batch["variable_count"],
                len(batch["rows"]),
            )
        )
        for interval in exact["rows"]:
            encoded += packager.OUTPUT.pack(
                int(interval["lo"], 16),
                int(interval["hi"], 16),
                0,
                b"\0" * 7,
            )
        return bytes(encoded)

    def write_ptx_audit(self, name: str, ptx: Path) -> Path:
        path = self.work / name
        write_json(
            path,
            {
                "schema_version": 1,
                "passed": True,
                "target": "sm_121",
                "input_sha256": sha256(ptx),
                "lowering_model": self.lowering_model(),
            },
        )
        return path

    def write_sass_audit(
        self,
        name: str,
        *,
        ptx: Path,
        cubin: Path,
        sass: Path,
        ptx_audit: Path,
    ) -> Path:
        ptx_audit_value = json.loads(ptx_audit.read_text(encoding="utf-8"))
        lowering_sha256 = hashlib.sha256(
            bundle_format.canonical_json_bytes(ptx_audit_value["lowering_model"])
        ).hexdigest()
        path = self.work / name
        write_json(
            path,
            {
                "schema_version": 1,
                "passed": True,
                "target": "sm_121",
                "target_binding_valid": True,
                "targets": ["sm_121"],
                "ptx_sha256": sha256(ptx),
                "cubin_sha256": sha256(cubin),
                "sass_sha256": sha256(sass),
                "ptx_audit_sha256": sha256(ptx_audit),
                "lowering_model_valid": True,
                "lowering_model_sha256": lowering_sha256,
            },
        )
        return path

    def make_retained_run(self) -> None:
        batch = self.main_batch()
        zero_batch = packager._expected_signed_zero_batch()
        wire.write_canonical_json(self.work / "batch.json", batch)
        wire.write_canonical_json(self.work / "signed-zero-batch.json", zero_batch)
        self.write_rows("rows.bin", batch)
        self.write_rows("signed-zero-rows.bin", zero_batch)

        results = self.result_bytes(batch)
        zero_results = self.result_bytes(zero_batch)
        (self.work / "results.bin").write_bytes(results)
        (self.work / "results.replay.bin").write_bytes(results)
        (self.work / "signed-zero-results.bin").write_bytes(zero_results)
        (self.work / "signed-zero-results.replay.bin").write_bytes(zero_results)

        ptx_text = b".version 9.0\n.target sm_121\n.address_size 64\n"
        for name in ("kernel.ptx", "kernel.replay.ptx"):
            (self.work / name).write_bytes(ptx_text)
        zero_ptx_text = ptx_text + b"// exact signed-zero suite\n"
        for name in ("signed-zero-kernel.ptx", "signed-zero-kernel.replay.ptx"):
            (self.work / name).write_bytes(zero_ptx_text)

        cubin = b"\x7fELFmain-cubin-sm121"
        zero_cubin = b"\x7fELFsigned-zero-cubin-sm121"
        for name in ("kernel.sm_121.cubin", "kernel.reassembled.sm_121.cubin"):
            (self.work / name).write_bytes(cubin)
        for name in (
            "signed-zero-kernel.sm_121.cubin",
            "signed-zero-kernel.reassembled.sm_121.cubin",
        ):
            (self.work / name).write_bytes(zero_cubin)

        for name, contents in (
            ("kernel.sm_121.sass.txt", "main sass\n"),
            ("kernel.closure.sm_121.sass.txt", "main closure sass\n"),
            ("signed-zero-kernel.sm_121.sass.txt", "zero sass\n"),
            ("signed-zero-kernel.closure.sm_121.sass.txt", "zero closure sass\n"),
        ):
            (self.work / name).write_text(contents, encoding="utf-8")

        main_ptx = self.work / "kernel.ptx"
        zero_ptx = self.work / "signed-zero-kernel.ptx"
        main_cubin = self.work / "kernel.sm_121.cubin"
        zero_cubin_path = self.work / "signed-zero-kernel.sm_121.cubin"
        ptx_audit = self.write_ptx_audit("ptx-audit.json", main_ptx)
        zero_ptx_audit = self.write_ptx_audit(
            "signed-zero-ptx-audit.json", zero_ptx
        )
        self.write_sass_audit(
            "sass-audit.json",
            ptx=main_ptx,
            cubin=main_cubin,
            sass=self.work / "kernel.sm_121.sass.txt",
            ptx_audit=ptx_audit,
        )
        self.write_sass_audit(
            "signed-zero-sass-audit.json",
            ptx=zero_ptx,
            cubin=zero_cubin_path,
            sass=self.work / "signed-zero-kernel.sm_121.sass.txt",
            ptx_audit=zero_ptx_audit,
        )

        closure_ptx_audit = self.write_ptx_audit(
            "ptx-audit.closure.json", self.work / "kernel.replay.ptx"
        )
        zero_closure_ptx_audit = self.write_ptx_audit(
            "signed-zero-ptx-audit.closure.json",
            self.work / "signed-zero-kernel.replay.ptx",
        )
        self.write_sass_audit(
            "sass-audit.closure.json",
            ptx=self.work / "kernel.replay.ptx",
            cubin=main_cubin,
            sass=self.work / "kernel.closure.sm_121.sass.txt",
            ptx_audit=closure_ptx_audit,
        )
        self.write_sass_audit(
            "signed-zero-sass-audit.closure.json",
            ptx=self.work / "signed-zero-kernel.replay.ptx",
            cubin=zero_cubin_path,
            sass=self.work / "signed-zero-kernel.closure.sm_121.sass.txt",
            ptx_audit=zero_closure_ptx_audit,
        )

        (self.work / "phase4-expression-input.bin").write_bytes(b"phase4-input")
        phase4_payload = results[packager.GENERATED_HEADER.size :]
        (self.work / "phase4-expression-results.bin").write_bytes(
            packager.PHASE4_HEADER.pack(
                packager.PHASE4_OUTPUT_MAGIC, 1, 3, 2, 2, len(batch["rows"])
            )
            + phase4_payload
        )

        hardware = self.hardware(
            len(batch["rows"]),
            module=main_cubin,
            rows=self.work / "rows.bin",
            results=self.work / "results.bin",
            challenge_nonce="11" * 32,
        )
        zero_hardware = self.hardware(
            9,
            module=zero_cubin_path,
            rows=self.work / "signed-zero-rows.bin",
            results=self.work / "signed-zero-results.bin",
            challenge_nonce="22" * 32,
        )
        replay_hardware = self.hardware(
            len(batch["rows"]),
            module=main_cubin,
            rows=self.work / "rows.bin",
            results=self.work / "results.replay.bin",
            challenge_nonce="33" * 32,
        )
        zero_replay_hardware = self.hardware(
            9,
            module=zero_cubin_path,
            rows=self.work / "signed-zero-rows.bin",
            results=self.work / "signed-zero-results.replay.bin",
            challenge_nonce="44" * 32,
        )
        write_json(self.work / "driver-run.json", hardware)
        write_json(self.work / "signed-zero-driver-run.json", zero_hardware)

        strong_files = {
            key: self.work / filename for key, filename in packager.STRONG_FILES.items()
        }
        strong_sha = {key: sha256(path) for key, path in strong_files.items()}
        strong_sha.update(
            {
                "cubin": sha256(main_cubin),
                "signed_zero_cubin": sha256(zero_cubin_path),
                "generator_executable": sha256(self.generator),
                "generated_driver_executable": sha256(self.driver),
                "phase4_expression_runner": sha256(self.phase4),
                "ptxas_executable": sha256(self.ptxas),
                "nvdisasm_executable": sha256(self.nvdisasm),
                "generated_result_payload": hashlib.sha256(phase4_payload).hexdigest(),
                "phase4_result_payload": hashlib.sha256(phase4_payload).hexdigest(),
                **{key: sha256(path) for key, path in packager.SOURCE_HASHES.items()},
            }
        )
        exact_main = {
            "passed": True,
            "row_count": len(batch["rows"]),
            "mismatch_count": 0,
            "mismatches_capped": [],
            "status_counts": {"0": len(batch["rows"])},
        }
        exact_zero = {
            "passed": True,
            "row_count": 9,
            "mismatch_count": 0,
            "mismatches_capped": [],
            "status_counts": {"0": 9},
        }
        strong = {
            "passed": True,
            "row_count": len(batch["rows"]),
            "phase4_instruction_count": 3,
            "phase4_max_stack_depth": 2,
            "deterministic_generation": True,
            "deterministic_cubin_reassembly": True,
            "deterministic_execution_replay": True,
            "replay_hardware_execution": replay_hardware,
            "exact_reference_recomputed": exact_main,
            "signed_zero_exact_reference_recomputed": exact_zero,
            "signed_zero_deterministic_generation": True,
            "signed_zero_deterministic_cubin_reassembly": True,
            "signed_zero_deterministic_execution_replay": True,
            "signed_zero_replay_hardware_execution": zero_replay_hardware,
            "phase4_generated_payload_equal": True,
            "sass_audit_passed": True,
            "signed_zero_sass_audit_passed": True,
            "sha256": strong_sha,
        }

        base_files = {
            key: self.work / filename for key, filename in packager.BASE_FILES.items()
        }
        top_sha = {key: sha256(path) for key, path in base_files.items()}
        top_sha.update(
            {
                "generator_executable": sha256(self.generator),
                "generated_driver_executable": sha256(self.driver),
                **{
                    key: sha256(path)
                    for key, path in packager.SOURCE_HASHES.items()
                    if key != "acceptance_closure_tool"
                },
            }
        )
        report = {
            "schema_version": 1,
            "kind": "sparkinterval_generated_ptx_conformance",
            "accepted": True,
            "target": "sm_121",
            "execution_module": {
                "kind": "offline_ptxas_cubin",
                "development_ptx_jit_used": False,
                "target": "sm_121",
                "cubin_sha256": sha256(main_cubin),
                "sass_audit_passed_before_execution": True,
            },
            "hardware_execution": hardware,
            "signed_zero_hardware_execution": zero_hardware,
            "toolchain": {
                "ptxas": {
                    "path": str(self.ptxas.resolve()),
                    "sha256": sha256(self.ptxas),
                    "version": "ptxas synthetic 1",
                },
                "nvdisasm": {
                    "path": str(self.nvdisasm.resolve()),
                    "sha256": sha256(self.nvdisasm),
                    "version": "nvdisasm synthetic 1",
                },
            },
            "seed": 7,
            "row_count": len(batch["rows"]),
            "status_counts": {"0": len(batch["rows"])},
            "signed_zero_mul_probe": {
                "row_count": 9,
                "mismatch_count": 0,
                "covers_pairwise": ["+0", "-0", "[-0,+0]"],
            },
            "mismatch_count_capped": 0,
            "mismatches": [],
            "sha256": top_sha,
            "strong_acceptance": strong,
        }
        write_json(self.work / "report.json", report)

    def report(self) -> dict:
        return json.loads((self.work / "report.json").read_text(encoding="utf-8"))

    def replace_report(self, value: dict) -> None:
        write_json(self.work / "report.json", value)

    def package(self) -> tuple[dict, dict, Path]:
        return packager.package_retained_run(
            work_dir=self.work,
            generator=self.generator,
            driver=self.driver,
            phase4=self.phase4,
            output_root=self.root / "bundle",
            start_time_utc="2026-07-19T12:00:00Z",
            end_time_utc="2026-07-19T12:00:01Z",
            nonce="34" * 32,
        )

    def test_packages_canonical_local_bundle_and_preserves_toolchain(self) -> None:
        bundle, verification, manifest = self.package()

        self.assertEqual(bundle["evidence"]["evidence_class"], "local_unattested")
        self.assertIsNone(bundle["evidence"]["hardware_attestation"])
        self.assertFalse(verification["hardware_evidence"])
        self.assertEqual(
            verification["assurance"], "local_record_not_hardware_evidence"
        )
        self.assertEqual(manifest.read_bytes(), bundle_format.canonical_json_bytes(bundle))
        self.assertEqual(
            (manifest.parent / "input/batch.json").read_bytes(),
            (self.work / "batch.json").read_bytes(),
        )
        self.assertEqual(
            (manifest.parent / "output/results.bin").read_bytes(),
            (self.work / "results.bin").read_bytes(),
        )
        self.assertEqual(
            bundle["statement"]["algorithm"]["definition_sha256"],
            sha256(self.work / "kernel.sm_121.cubin"),
        )
        hardware = self.report()["hardware_execution"]
        self.assertEqual(
            hardware["input_payload_size_bytes"],
            (self.work / "rows.bin").stat().st_size
            - packager.GENERATED_HEADER.size,
        )
        self.assertEqual(
            hardware["output_file_sha256"], sha256(self.work / "results.bin")
        )
        self.assertNotEqual(
            hardware["challenge_nonce"],
            self.report()["strong_acceptance"]["replay_hardware_execution"][
                "challenge_nonce"
            ],
        )
        roles = {item["role"]: item for item in bundle["statement"]["build_artifacts"]}
        for role, original in (
            ("gpu_cubin", self.work / "kernel.sm_121.cubin"),
            ("gpu_ptx", self.work / "kernel.ptx"),
            ("acceptance_report", self.work / "report.json"),
            ("host_executable", self.driver),
            ("generator_executable", self.generator),
            ("ptxas_executable", self.ptxas),
            ("nvdisasm_executable", self.nvdisasm),
        ):
            self.assertEqual(roles[role]["sha256"], sha256(original))
        checked = bundle_verify.verify_bundle_file(
            manifest, artifact_root=manifest.parent
        )
        self.assertTrue(checked["accepted"])

    def test_rejects_nonliteral_signed_zero_batch(self) -> None:
        changed = packager._expected_signed_zero_batch()
        changed["rows"] = list(reversed(changed["rows"]))
        wire.write_canonical_json(self.work / "signed-zero-batch.json", changed)
        with self.assertRaisesRegex(
            bundle_format.BundleError, "exact 3x3 multiplication probe"
        ):
            self.package()

    def test_rejects_failed_strong_acceptance(self) -> None:
        report = self.report()
        report["strong_acceptance"]["passed"] = False
        self.replace_report(report)
        with self.assertRaisesRegex(bundle_format.BundleError, "passed must be true"):
            self.package()

    def test_rejects_strong_reference_status_count_mismatch(self) -> None:
        report = self.report()
        report["strong_acceptance"]["exact_reference_recomputed"][
            "status_counts"
        ] = {"0": 1}
        self.replace_report(report)
        with self.assertRaisesRegex(bundle_format.BundleError, "status_counts"):
            self.package()

    def test_rejects_failed_strong_reference_recomputation(self) -> None:
        report = self.report()
        report["strong_acceptance"]["exact_reference_recomputed"][
            "passed"
        ] = False
        self.replace_report(report)
        with self.assertRaisesRegex(bundle_format.BundleError, "did not pass exactly"):
            self.package()

    def test_rejects_development_hardware_override(self) -> None:
        report = self.report()
        report["hardware_execution"]["allow_other_device"] = True
        self.replace_report(report)
        with self.assertRaisesRegex(bundle_format.BundleError, "development device override"):
            self.package()

    def test_rejects_driver_input_payload_binding_mismatch(self) -> None:
        report = self.report()
        report["hardware_execution"]["input_payload_sha256"] = "00" * 32
        write_json(
            self.work / "driver-run.json", report["hardware_execution"]
        )
        self.replace_report(report)
        with self.assertRaisesRegex(
            bundle_format.BundleError, "input_payload_sha256 does not bind"
        ):
            self.package()

    def test_rejects_replay_output_binding_mismatch(self) -> None:
        report = self.report()
        report["strong_acceptance"]["replay_hardware_execution"][
            "output_file_sha256"
        ] = "00" * 32
        self.replace_report(report)
        with self.assertRaisesRegex(
            bundle_format.BundleError, "output_file_sha256 does not bind"
        ):
            self.package()

    def test_rejects_cubin_tampering(self) -> None:
        with (self.work / "kernel.sm_121.cubin").open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaisesRegex(bundle_format.BundleError, "SASS chain"):
            self.package()

    def test_rejects_unpreserved_lowering_model(self) -> None:
        audit_path = self.work / "ptx-audit.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["lowering_model"]["passed"] = False
        write_json(audit_path, audit)
        with self.assertRaisesRegex(bundle_format.BundleError, "lowering model"):
            self.package()


if __name__ == "__main__":
    unittest.main()
