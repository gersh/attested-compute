# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BINARY = os.environ.get(
    "TG_PLATT_PT21_LIVE_TRANSFORM_CANDIDATE_QUALIFICATION"
)
STRICT_BINARY = os.environ.get(
    "TG_PLATT_PT21_LIVE_TRANSFORM_CANDIDATE_H100_QUALIFICATION"
)
STREAM = os.environ.get("TG_PLATT_GAMMA_V2_BLOCK0_STREAM")
STREAM_SHA256 = (
    "d484eb1f0d382ffcf3683e18cd0c9570"
    "c5a215efaa595cb9bb677e3c2ebfbdbc"
)
STREAM_FILE_SHA256 = (
    "b1269afd7d15842fb15a86301627280ac"
    "ddd190de9a7e2d961510a555f14f391"
)
ORDINARY_ARTIFACT_SHA256 = (
    "583a257079353e8efb334f1be2d7c415"
    "14a8f9759898f1dc1b2220fbda2dae60"
)
ORDINARY_ALL_SAMPLE_SHA256 = (
    "f11156870b9681147f3b48d70bd9bdc3"
    "613f015fa9a8783230fc731f49564224"
)
ORDINARY_REQUIRED_SAMPLE_SHA256 = (
    "3a12d63c8545aaf98ce6585994412a7e"
    "96c817a4b3d93e40da671c58883a97e4"
)
CANDIDATE_ALL_SAMPLE_SHA256 = (
    "06e55d44a684548c93f4ac48996fdca0"
    "6bca00e1ab4ba493d02f84d03bc16c19"
)
CANDIDATE_REQUIRED_SAMPLE_SHA256 = (
    "46ceeae8f719f85bf747a9b660f26c42"
    "6016859293e22bb0e653041365f60c57"
)
CANDIDATE_ARTIFACT_SHA256 = (
    "65292e38a013baa83abc61bd5cdcd8c2"
    "e014032d9bceabe08d6fd5578d06ef89"
)
CONTAINMENT_FRAME_ARTIFACT_SHA256 = (
    "a4379093cd52ab0b90ed73cf60f61700"
    "3490eefd2a1379115d9a3b1bdf5125d7"
)


def one_json(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise AssertionError(f"expected one JSON line, got {completed.stdout!r}")
    value = json.loads(lines[0])
    if not isinstance(value, dict):
        raise AssertionError("runner JSON is not an object")
    return value


def exact_finite_binary64(bits: int) -> Fraction:
    sign = -1 if bits >> 63 else 1
    exponent = (bits >> 52) & 0x7FF
    fraction = bits & ((1 << 52) - 1)
    if exponent == 0x7FF:
        raise AssertionError("containment artifact contains nonfinite data")
    if exponent == 0:
        return sign * Fraction(fraction, 1 << 1074)
    significand = (1 << 52) | fraction
    shift = exponent - 1023 - 52
    if shift >= 0:
        return sign * Fraction(significand << shift)
    return sign * Fraction(significand, 1 << (-shift))


def target_slice(cmake: str, target: str) -> str:
    target_position = cmake.index(target)
    begin = cmake.rfind("add_executable(", 0, target_position)
    if begin == -1:
        raise AssertionError(f"cannot find add_executable for {target}")
    end = cmake.find("add_executable(", target_position + len(target))
    if end == -1:
        end = len(cmake)
    return cmake[begin:end]


class PT21LiveTransformCandidateSourceTests(unittest.TestCase):
    def test_runner_uses_live_boundaries_and_one_workspace_each(self) -> None:
        source = (
            ROOT
            / "reference"
            / "tg_platt_pt21_live_transform_candidate_qualification.cu"
        ).read_text(encoding="utf-8")
        compact = source.replace('"\n    "', "")
        self.assertIn(STREAM_SHA256, compact)
        self.assertIn(STREAM_FILE_SHA256, compact)
        self.assertIn(ORDINARY_ARTIFACT_SHA256, compact)
        for digest in (
            ORDINARY_ALL_SAMPLE_SHA256,
            ORDINARY_REQUIRED_SAMPLE_SHA256,
            CANDIDATE_ALL_SAMPLE_SHA256,
            CANDIDATE_REQUIRED_SAMPLE_SHA256,
            CANDIDATE_ARTIFACT_SHA256,
            CONTAINMENT_FRAME_ARTIFACT_SHA256,
        ):
            self.assertIn(digest, compact)
        self.assertIn("pg2::Reader reader(", source)
        self.assertIn("reader.finish();", source)
        run_body = source[source.index("int run(const Options& options)") :]
        self.assertLess(
            run_body.index("authenticate_input(options)"),
            run_body.index("require_and_read_device_profile()"),
        )
        self.assertEqual(
            source.count("pda::create_source_workspace(0U, 1U, 256U)"), 1
        )
        self.assertEqual(source.count("pdt::create_source_workspace()"), 1)
        self.assertEqual(source.count("pes::create_workspace()"), 1)
        self.assertIn("pgd::launch_synthesize(", source)
        self.assertIn("pgd::launch_summarize(", source)
        self.assertIn("pda::run_next_source_window(", source)
        self.assertIn("pdt::run_source_window(", source)
        self.assertIn(
            "pdt::run_source_window_sloppy_root_qualification(", source
        )
        self.assertIn(
            "pdt::run_source_window_tile9_sloppy_root_qualification(",
            source,
        )
        self.assertIn("pdt::device_samples(", source)
        self.assertIn("exact_containment(ordinary.samples, sloppy.samples)", source)
        self.assertIn("replay_reports_byte_equal(sloppy.replay, tile.replay)", source)
        self.assertIn("append_real_disk106_le(bytes, ordinary[index])", source)
        self.assertIn("append_real_disk106_le(bytes, candidate[index])", source)
        self.assertIn("O_CREAT | O_EXCL | O_NOFOLLOW", source)
        self.assertIn("::fsync(descriptor.get())", source)
        self.assertGreaterEqual(source.count("::fstat(descriptor.get()"), 2)
        self.assertNotIn("std::ios::trunc", source)
        self.assertIn("containment artifact write-back differs", source)

    def test_fail_closed_fallback_and_claim_boundaries_are_explicit(self) -> None:
        source = (
            ROOT
            / "reference"
            / "tg_platt_pt21_live_transform_candidate_qualification.cu"
        ).read_text(encoding="utf-8")
        compact = "".join(source.split())
        self.assertIn('selected_implementation', source)
        self.assertIn('"ordinary-fallback"', source)
        self.assertIn("if (!candidate_qualified)", source)
        self.assertIn(
            "run_variant(&resources, skn, Variant::kOrdinary)", source
        )
        for field_name in (
            "candidate_selected_in_production",
            "receipt_emitted",
            "secure_enclave_attested",
            "cuda_to_lean_refinement_proved",
            "ordinary_hardy_z_realization_proved",
            "flint_to_mathlib_proved",
            "all_window_coverage_complete",
            "stationary_turing_closure_complete",
            "source_claim_ready",
            "production_ready",
            "pt21_atom_discharged",
        ):
            self.assertIn(f'\\"{field_name}\\":false', compact)
        self.assertIn('\\"runtime_instrumentation_status\\":', compact)
        self.assertIn('\\"not-inspected-by-runner\\"', compact)
        self.assertIn('\\"performance_evidence_eligible\\":false', compact)

    def test_containment_artifact_contract_is_cross_language_pinned(
        self,
    ) -> None:
        source = (
            ROOT
            / "reference"
            / "tg_platt_pt21_live_transform_candidate_qualification.cu"
        ).read_text(encoding="utf-8")
        cli = (
            ROOT
            / "SparkInterval"
            / "Certified"
            / "ComplexDiskContainmentArtifactCLI.lean"
        ).read_text(encoding="utf-8")
        wire = (
            ROOT
            / "SparkInterval"
            / "Certified"
            / "ComplexDiskContainmentWire.lean"
        ).read_text(encoding="utf-8")
        documentation = (
            ROOT
            / "docs"
            / "algorithms"
            / "PLATT_PT21_LIVE_TRANSFORM_CANDIDATE_QUALIFICATION.md"
        ).read_text(encoding="utf-8")
        compact_source = source.replace('"\n    "', "")
        for text in (compact_source, cli, documentation):
            self.assertIn(CONTAINMENT_FRAME_ARTIFACT_SHA256, text)
        self.assertIn("block0FrameCount : Nat := 131072", cli)
        self.assertIn(
            "block0FrameCount * rawContainmentPairByteSize", cli
        )
        self.assertIn("rawContainmentPairByteSize : Nat := 48", wire)
        self.assertIn(
            "checkRawContainmentArtifactBytes block0FrameCount raw.toList",
            cli,
        )
        self.assertIn("131,072 frames (6,291,456 bytes)", documentation)
        lakefile = (ROOT / "lakefile.toml").read_text(encoding="utf-8")
        self.assertIn(
            'name = "sparkinterval-check-pt21-containment"', lakefile
        )
        self.assertIn(
            'root = "SparkInterval.Certified.'
            'ComplexDiskContainmentArtifactCLI"',
            lakefile,
        )

    def test_portable_and_strict_targets_are_isolated(self) -> None:
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        portable_name = (
            "sparkinterval-tg-platt-pt21-live-transform-candidate-"
            "qualification"
        )
        portable = target_slice(cmake, portable_name)
        self.assertIn("--fmad=false", portable)
        self.assertIn("--ftz=false", portable)
        self.assertIn("SPARKINTERVAL_CUDA_FTZ_DISABLED=1", portable)
        self.assertIn(
            "sparkinterval-tg-platt-dd-accumulator", portable
        )
        self.assertIn(
            "sparkinterval-tg-platt-dd-tile9-sloppy-root-transform-"
            "qualification",
            portable,
        )
        self.assertIn("sparkinterval-tg-platt-event-scan", portable)
        self.assertNotIn(
            "\n      sparkinterval-tg-platt-dd-transform\n", portable
        )

        strict_name = (
            "sparkinterval-h100-tg-platt-pt21-live-transform-candidate-"
            "qualification"
        )
        strict = target_slice(cmake, strict_name)
        self.assertIn(
            f"sparkinterval_configure_h100_kernel(\n    {strict_name}",
            strict,
        )
        self.assertIn("SPARKINTERVAL_REQUIRE_H100_SM90=1", strict)
        self.assertIn(
            "sparkinterval-h100-tg-platt-dd-accumulator", strict
        )
        self.assertIn(
            "sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-transform-"
            "qualification",
            strict,
        )
        self.assertIn("sparkinterval-h100-tg-platt-event-scan", strict)

        production_begin = cmake.index(
            "add_executable(sparkinterval-tg-platt-fused-source-worker-v2"
        )
        production_end = cmake.index(
            "# Qualification-only producer/consumer overlap",
            production_begin,
        )
        production = cmake[production_begin:production_end]
        self.assertNotIn(
            "SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION",
            production,
        )
        self.assertNotIn(
            "SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION", production
        )


@unittest.skipUnless(
    BINARY and STREAM,
    "set live candidate executable and exact block-0 V2 stream",
)
class PT21LiveTransformCandidateRuntimeTests(unittest.TestCase):
    def invoke(
        self, digest: str = STREAM_SHA256, *extra: str
    ) -> subprocess.CompletedProcess[str]:
        assert BINARY is not None
        assert STREAM is not None
        return subprocess.run(
            [
                BINARY,
                STREAM,
                f"--expected-stream-sha256={digest}",
                "--repetitions=1",
                *extra,
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_live_block0_candidate_and_fallback_boundary(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="tg-pt21-containment-"
        ) as temporary:
            artifact_path = Path(temporary) / "frames.bin"
            completed = self.invoke(
                STREAM_SHA256,
                f"--containment-frames-out={artifact_path}",
            )
            self.assertTrue(artifact_path.is_file(), completed.stderr)
            artifact = artifact_path.read_bytes()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = one_json(completed)
        self.assertTrue(report["accepted"])
        self.assertTrue(report["candidate_semantic_gates_accepted"])
        self.assertTrue(report["candidate_qualified"])
        self.assertFalse(report["candidate_rejection_forced_for_test"])
        self.assertEqual(report["selected_implementation"], "tile9-sloppy-root")
        self.assertEqual(report["gamma_stream_file_bytes"], 848)
        self.assertEqual(report["gamma_stream_file_sha256"], STREAM_FILE_SHA256)
        self.assertEqual(report["gamma_stream_logical_sha256"], STREAM_SHA256)
        self.assertTrue(report["gamma_stream_authenticated_before_gpu_allocation"])
        self.assertTrue(report["single_accumulator_workspace"])
        self.assertTrue(report["single_transform_workspace"])
        self.assertTrue(report["single_event_scanner_workspace"])
        self.assertEqual(report["accumulator_workspace_device_bytes"], 570_977_292)
        self.assertEqual(report["transform_workspace_device_bytes"], 195_429_316)
        self.assertEqual(report["event_scanner_workspace_device_bytes"], 7_750_989)
        self.assertTrue(report["source_geometry_accepted"])
        self.assertTrue(report["accumulator_audit"]["accepted"])
        self.assertEqual(
            report["accumulator_audit"]["geometry_sha256"],
            "67dc2eda921762f6ad1eaf046188b9500"
            "b1b19c87b46e60facf30cfb3bf28ad4",
        )
        self.assertTrue(report["root_table_audit"]["accepted"])
        self.assertTrue(report["root_table_audit"]["immutable"])
        self.assertEqual(
            report["root_table_audit"]["before_sha256"],
            "0b4e51572104edf59d096d680ca010a5"
            "15157208c6cdba14be867d9c22d52040",
        )
        self.assertTrue(report["kernel_resources"]["accepted"])
        self.assertTrue(report["ordinary_known_answer"])
        self.assertTrue(report["settled_sloppy_known_answer"])
        self.assertTrue(report["tile9_sloppy_known_answer"])
        self.assertTrue(report["exact_all_sample_containment"]["accepted"])
        self.assertEqual(
            report["exact_all_sample_containment"]["sample_count"], 131_072
        )
        self.assertTrue(report["containment_frame_artifact_emitted"])
        self.assertFalse(report["containment_frame_artifact_authenticated"])
        self.assertTrue(
            report["containment_frame_artifact_written_bytes_rehashed"]
        )
        self.assertEqual(
            report["containment_frame_artifact_frame_count"], 131_072
        )
        self.assertEqual(
            report["containment_frame_artifact_bytes"], 6_291_456
        )
        self.assertEqual(
            report["containment_frame_artifact_sha256"],
            CONTAINMENT_FRAME_ARTIFACT_SHA256,
        )
        self.assertFalse(
            report["containment_frame_artifact_lean_check_executed"]
        )
        self.assertEqual(len(artifact), 6_291_456)
        self.assertEqual(
            hashlib.sha256(artifact).hexdigest(),
            CONTAINMENT_FRAME_ARTIFACT_SHA256,
        )
        first_bad_frame = None
        for index, words in enumerate(struct.iter_unpack("<6Q", artifact)):
            (
                ordinary_hi,
                ordinary_lo,
                ordinary_radius,
                candidate_hi,
                candidate_lo,
                candidate_radius,
            ) = map(exact_finite_binary64, words)
            radius_margin = candidate_radius - ordinary_radius
            center_distance = (
                candidate_hi
                + candidate_lo
                - ordinary_hi
                - ordinary_lo
            )
            if (
                ordinary_radius < 0
                or radius_margin < 0
                or abs(center_distance) > radius_margin
            ):
                first_bad_frame = index
                break
        self.assertIsNone(first_bad_frame)
        self.assertEqual(
            report["prospective_containment_frame_count"], 131_072
        )
        self.assertEqual(report["prospective_containment_frame_bytes"], 48)
        self.assertEqual(
            report["prospective_containment_artifact_bytes"], 6_291_456
        )
        self.assertTrue(report["required_sign_comparison"]["accepted"])
        self.assertTrue(report["ordinary_sloppy_event_topology_identical"])
        self.assertTrue(report["tile_settled_all_sample_bytes_identical"])
        self.assertTrue(report["tile_settled_replay_artifact_identical"])
        self.assertFalse(report["fallback_exercised"])
        self.assertTrue(report["release_build_profile_eligible"])
        self.assertEqual(
            report["runtime_instrumentation_status"],
            "not-inspected-by-runner",
        )
        self.assertFalse(report["performance_evidence_eligible"])
        variants = report["variants"]
        self.assertEqual(len(variants), 3)
        self.assertEqual(
            variants[0]["scanner_artifact_sha256"],
            ORDINARY_ARTIFACT_SHA256,
        )
        self.assertEqual(variants[0]["required_digest_xor"], "55c2a006ce805986")
        self.assertEqual(
            variants[0]["all_sample_sha256"], ORDINARY_ALL_SAMPLE_SHA256
        )
        self.assertEqual(
            variants[0]["required_sample_sha256"],
            ORDINARY_REQUIRED_SAMPLE_SHA256,
        )
        self.assertEqual(
            variants[0]["streams"],
            [
                {
                    "stream": 0,
                    "direct_event_count": 71,
                    "stationary_candidate_count": 0,
                    "certified_direct_multiplicity_slots": 71,
                    "direct_nleft_units": -18_200,
                    "direct_nright_units": 18_081,
                },
                {
                    "stream": 1,
                    "direct_event_count": 3_397,
                    "stationary_candidate_count": 1,
                    "certified_direct_multiplicity_slots": 3_397,
                    "direct_nleft_units": -41_749_543,
                    "direct_nright_units": 41_731_732,
                },
                {
                    "stream": 2,
                    "direct_event_count": 71,
                    "stationary_candidate_count": 0,
                    "certified_direct_multiplicity_slots": 71,
                    "direct_nleft_units": -18_240,
                    "direct_nright_units": 18_041,
                },
            ],
        )
        for candidate in variants[1:]:
            self.assertEqual(
                candidate["all_sample_sha256"],
                CANDIDATE_ALL_SAMPLE_SHA256,
            )
            self.assertEqual(
                candidate["required_sample_sha256"],
                CANDIDATE_REQUIRED_SAMPLE_SHA256,
            )
            self.assertEqual(
                candidate["scanner_artifact_sha256"],
                CANDIDATE_ARTIFACT_SHA256,
            )
            self.assertEqual(
                candidate["required_digest_xor"], "094f3182295e6c3f"
            )
        self.assertFalse(report["candidate_selected_in_production"])
        self.assertFalse(report["receipt_emitted"])
        self.assertFalse(report["secure_enclave_attested"])
        self.assertFalse(report["cuda_to_lean_refinement_proved"])
        self.assertFalse(report["source_claim_ready"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["pt21_atom_discharged"])

    def test_forced_rejection_exercises_exact_ordinary_fallback(self) -> None:
        completed = self.invoke(
            STREAM_SHA256, "--force-candidate-rejection-for-test"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = one_json(completed)
        self.assertTrue(report["accepted"])
        self.assertTrue(report["candidate_semantic_gates_accepted"])
        self.assertFalse(report["candidate_qualified"])
        self.assertTrue(report["candidate_rejection_forced_for_test"])
        self.assertEqual(
            report["selected_implementation"], "ordinary-fallback"
        )
        self.assertTrue(report["fallback_exercised"])
        self.assertTrue(report["fallback_reproduced_ordinary"])
        self.assertFalse(report["performance_evidence_eligible"])
        self.assertFalse(report["candidate_selected_in_production"])
        self.assertFalse(report["source_claim_ready"])
        self.assertFalse(report["pt21_atom_discharged"])

    def test_wrong_logical_stream_pin_rejects_before_output(self) -> None:
        completed = self.invoke("00" * 32)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("must pin", completed.stderr)

    def test_existing_containment_output_rejects_without_truncation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="tg-pt21-existing-artifact-"
        ) as temporary:
            output = Path(temporary) / "guard.bin"
            guard = b"must-not-be-truncated"
            output.write_bytes(guard)
            completed = self.invoke(
                STREAM_SHA256,
                f"--containment-frames-out={output}",
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout, "")
            self.assertIn("already exists", completed.stderr)
            self.assertEqual(output.read_bytes(), guard)

    def test_dangling_containment_symlink_rejects_before_gpu_work(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="tg-pt21-dangling-artifact-"
        ) as temporary:
            target = Path(temporary) / "must-not-be-created.bin"
            output = Path(temporary) / "dangling.bin"
            output.symlink_to(target)
            completed = self.invoke(
                STREAM_SHA256,
                f"--containment-frames-out={output}",
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout, "")
            self.assertIn("already exists", completed.stderr)
            self.assertTrue(output.is_symlink())
            self.assertFalse(target.exists())


@unittest.skipUnless(
    STRICT_BINARY and STREAM,
    "set strict H100 live candidate executable and exact stream",
)
class PT21LiveTransformCandidateStrictTests(unittest.TestCase):
    def test_strict_target_rejects_non_h100(self) -> None:
        assert STRICT_BINARY is not None
        assert STREAM is not None
        completed = subprocess.run(
            [
                STRICT_BINARY,
                STREAM,
                f"--expected-stream-sha256={STREAM_SHA256}",
                "--repetitions=1",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            report = one_json(completed)
            self.assertTrue(report["strict_h100_target"])
            self.assertTrue(report["target_h100_measured"])
        else:
            self.assertEqual(completed.stdout, "")
            self.assertIn("H100", completed.stderr)


if __name__ == "__main__":
    unittest.main()
