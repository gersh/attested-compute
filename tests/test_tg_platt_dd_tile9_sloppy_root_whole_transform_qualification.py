# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
BINARY = os.environ.get(
    "TG_PLATT_DD_TILE9_SLOPPY_ROOT_WHOLE_TRANSFORM_QUALIFICATION"
)
STRICT_BINARY = os.environ.get(
    "TG_PLATT_DD_TILE9_SLOPPY_ROOT_WHOLE_TRANSFORM_H100_QUALIFICATION"
)
PACKET = os.environ.get("TG_PLATT_DD_FULL_V2_PACKET")
PACKET_SHA256 = (
    "caecf8faee55a1c969062bb5d85cbd50"
    "ff70b0f461778e3fcb7fd0d561a058b7"
)
ORDINARY_GENUINE_SHA256 = (
    "81e54dc8806211ecc5c69b484076cd28"
    "ba1a0ab56a62a6fc8158ec84972b5a3e"
)
ORDINARY_EDGE_SHA256 = (
    "72ba9bacc3a312ae18c5d423388beae5"
    "2a621f3c81e37a1a006d91acc6d6a713"
)
SLOPPY_GENUINE_SHA256 = (
    "7d24ab69c3f2851809e13ab6d9a59434"
    "5c75f26423ca5a9fea136e7a1b861a0e"
)
SLOPPY_EDGE_SHA256 = (
    "adc7cfb2cdd84556b051d4037cc52afc"
    "93b3e44b1ce7024c8bdae8e635ea12cc"
)


def target_slice(cmake: str, target: str) -> str:
    marker = f"add_executable(\n    {target}"
    begin = cmake.index(marker)
    end = cmake.find("add_executable(", begin + len(marker))
    if end == -1:
        end = len(cmake)
    return cmake[begin:end]


def extract_braced_body(source: str, needle: str) -> str:
    start = source.index(needle)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening : index + 1]
    raise AssertionError(f"unterminated function body after {needle!r}")


class PT21DDTile9SloppyRootSourceTests(unittest.TestCase):
    def test_entry_kernel_and_resource_boundary_are_guarded(self) -> None:
        header = (
            ROOT
            / "gpu"
            / "include"
            / "sparkinterval"
            / "tg_platt_dd_transform.hpp"
        ).read_text(encoding="utf-8")
        source = (
            ROOT
            / "gpu"
            / "platform"
            / "h100"
            / "h100_tg_platt_windowed_dd_disk_semantic.cu"
        ).read_text(encoding="utf-8")

        self.assertIn("#include <cstddef>", header)
        self.assertIn(
            "SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1",
            header,
        )
        self.assertIn(
            "run_source_window_tile9_sloppy_root_qualification", header
        )
        self.assertIn(
            "QualificationTile9SloppyRootKernelResources", header
        )
        self.assertIn(
            "kQualificationTile9SloppyRootStaticSharedBytes = 32'768U",
            header,
        )
        self.assertIn(
            "tile9 sloppy-root qualification requires the sloppy-root guard",
            source,
        )
        self.assertIn(
            "dd_radix2_stages_1_through_9_tile_sloppy_root_qualification",
            source,
        )
        self.assertIn(
            "const std::uint32_t root_slot = "
            "offset << (9U - stage_log)",
            source,
        )
        self.assertIn(
            "dd_radix2_butterfly_sloppy_root_qualification(", source
        )
        self.assertIn(
            "dd_transform_tile9_sloppy_root_qualification(", source
        )
        self.assertIn(
            "dd_radix2_stage_sloppy_root_qualification<<<", source
        )
        self.assertIn("cudaFuncGetAttributes(", source)
        self.assertIn(
            "cudaOccupancyMaxActiveBlocksPerMultiprocessor(", source
        )
        pinned_bodies = {
            "dd_radix2_stages_1_through_9_tile_sloppy_root_"
            "qualification(": (
                "dacb8219d1c23886714f3f73e5445165"
                "f6f1e4cf4a6a72ca07127fa8d2d31b4a"
            ),
            "void dd_transform_tile9_sloppy_root_qualification(": (
                "00fe0a5b5624d9f92414a7fe21496010"
                "8c974121fc82ad8ceff78f9134028fba"
            ),
            "void run_source_window_tile9_sloppy_root_qualification(": (
                "bf410776e232281d9e4f6aa6c1fe597"
                "d1d0b8591c7c4692008109073ae7b7d15"
            ),
            "tile9_sloppy_root_kernel_resources_qualification()": (
                "9b37e6423aec20d2e12881d791642e4a"
                "a7bfb4f96fbf22dce7f2ecd54958eac3"
            ),
        }
        for needle, expected_sha256 in pinned_bodies.items():
            body = extract_braced_body(source, needle)
            self.assertEqual(
                hashlib.sha256(body.encode()).hexdigest(), expected_sha256
            )

    def test_production_entry_is_unchanged_and_macro_off(self) -> None:
        source = (
            ROOT
            / "gpu"
            / "platform"
            / "h100"
            / "h100_tg_platt_windowed_dd_disk_semantic.cu"
        ).read_text(encoding="utf-8")
        ordinary_body = source[
            source.index("void run_source_window(\n") :
            source.index("void run_source_window_tile9_qualification(")
        ]
        self.assertNotIn("sloppy_root", ordinary_body)
        self.assertEqual(
            hashlib.sha256(ordinary_body.encode()).hexdigest(),
            "89c15418506d386e2b678aef8cae3787"
            "a1934cfdf94831b1010df3b826b9ecd1",
        )

        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        production_begin = cmake.index(
            "add_library(sparkinterval-tg-platt-dd-transform STATIC"
        )
        production_end = cmake.index(
            "add_executable(sparkinterval-tg-platt-dd-transform-api-smoke",
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

    def test_separate_portable_and_strict_targets_pin_contracts(self) -> None:
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn(
            "sparkinterval-tg-platt-dd-tile9-sloppy-root-transform-"
            "qualification STATIC",
            cmake,
        )
        portable = target_slice(
            cmake,
            "sparkinterval-tg-platt-dd-tile9-sloppy-root-whole-transform-"
            "qualification",
        )
        self.assertIn("--fmad=false", portable)
        self.assertIn("--ftz=false", portable)
        self.assertIn("SPARKINTERVAL_CUDA_FTZ_DISABLED=1", portable)
        self.assertIn(
            "sparkinterval-tg-platt-dd-tile9-sloppy-root-transform-"
            "qualification",
            portable,
        )
        self.assertNotIn(
            "\n      sparkinterval-tg-platt-dd-transform\n", portable
        )

        strict_target = (
            "sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-whole-"
            "transform-qualification"
        )
        strict = target_slice(cmake, strict_target)
        self.assertIn(
            f"sparkinterval_configure_h100_kernel(\n    {strict_target}",
            strict,
        )
        self.assertIn("SPARKINTERVAL_REQUIRE_H100_SM90=1", strict)
        self.assertIn(
            "sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-transform-"
            "qualification",
            strict,
        )

    def test_runner_requires_all_semantic_gates_and_disclaims_claims(
        self,
    ) -> None:
        source = (
            ROOT
            / "reference"
            / "tg_platt_dd_sloppy_root_whole_transform_qualification.cu"
        ).read_text(encoding="utf-8")
        compact = source.replace('"\n    "', "")
        self.assertIn(SLOPPY_GENUINE_SHA256, compact)
        self.assertIn(SLOPPY_EDGE_SHA256, compact)
        self.assertIn(
            "run_source_window_tile9_sloppy_root_qualification(", source
        )
        self.assertIn("run_source_window_sloppy_root_qualification(", source)
        self.assertIn("disk_byte_mismatch_count(", source)
        self.assertIn(
            "candidate_settled_sloppy_all_sample_bytes_equal", source
        )
        self.assertIn("exact_all_sample_containment(", source)
        self.assertIn("replay_reports_byte_equal(", source)
        self.assertIn("qualify_overflow_negative_control(", source)
        self.assertIn("kernel_resources.local_bytes_per_thread == 0U", source)
        self.assertIn("runtime_instrumentation_status", source)
        self.assertIn("not-inspected-by-runner", source)
        self.assertIn("performance_evidence_eligible\\\":false", source)
        self.assertIn("cuda_to_lean_refinement_proved\\\":false", source)
        self.assertIn("source_claim_ready\\\":false", source)
        self.assertIn("production_ready\\\":false", source)
        self.assertIn("pt21_atom_discharged\\\":false", source)


@unittest.skipUnless(BINARY, "joint qualification executable is not configured")
class PT21DDTile9SloppyRootArgumentTests(unittest.TestCase):
    def run_binary(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [BINARY, *arguments],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_packet_and_sha_pin_are_mandatory(self) -> None:
        completed = self.run_binary("--repetitions=1")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("mandatory", completed.stderr)

    def test_wrong_sha_is_rejected_before_packet_open(self) -> None:
        completed = self.run_binary(
            "--source-packet=/does/not/exist",
            f"--expected-source-packet-sha256={'0' * 64}",
            "--repetitions=1",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("not the qualified", completed.stderr)


@unittest.skipUnless(BINARY, "joint qualification executable is required")
class PT21DDTile9SloppyRootKnownAnswerTests(unittest.TestCase):
    def test_authenticated_joint_qualification(self) -> None:
        if not PACKET:
            self.fail(
                "TG_PLATT_DD_FULL_V2_PACKET is mandatory when the joint "
                "qualification binary is configured"
            )
        completed = subprocess.run(
            [
                BINARY,
                f"--source-packet={PACKET}",
                f"--expected-source-packet-sha256={PACKET_SHA256}",
                "--repetitions=1",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(
            report["schema"],
            "sparkinterval.tg.platt-dd-tile9-sloppy-root-whole-transform-"
            "qualification.v1",
        )
        self.assertTrue(report["accepted"])
        self.assertTrue(report["qualification_only"])
        self.assertTrue(report["authenticated_fixture_required"])
        self.assertFalse(report["fixture_is_production_source_claim"])
        self.assertFalse(report["strict_h100_target"])
        self.assertFalse(report["target_h100_measured"])
        self.assertFalse(report["h100_runtime_claimed"])
        self.assertEqual(report["sample_disk_count"], 131_072)
        self.assertEqual(report["required_sample_count"], 25_741)
        self.assertEqual(
            report["ordinary_expected_genuine_output_sha256"],
            ORDINARY_GENUINE_SHA256,
        )
        self.assertEqual(
            report["ordinary_expected_finite_edge_output_sha256"],
            ORDINARY_EDGE_SHA256,
        )
        self.assertEqual(
            report["settled_sloppy_expected_genuine_output_sha256"],
            SLOPPY_GENUINE_SHA256,
        )
        self.assertEqual(
            report["settled_sloppy_expected_finite_edge_output_sha256"],
            SLOPPY_EDGE_SHA256,
        )

        resources = report["joint_kernel_resources"]
        self.assertTrue(resources["accepted"])
        self.assertGreater(resources["registers_per_thread"], 0)
        self.assertLessEqual(resources["registers_per_thread"], 255)
        self.assertEqual(resources["static_shared_bytes"], 32_768)
        self.assertEqual(resources["expected_static_shared_bytes"], 32_768)
        self.assertEqual(resources["local_bytes_per_thread"], 0)
        self.assertGreaterEqual(resources["maximum_threads_per_block"], 256)
        self.assertEqual(resources["required_threads_per_block"], 256)
        self.assertGreaterEqual(
            resources["active_blocks_per_multiprocessor"], 1
        )

        roots = report["root_table_audit"]
        self.assertTrue(roots["accepted"])
        self.assertTrue(roots["ordinary_candidate_table_byte_equal"])
        self.assertTrue(roots["candidate_settled_sloppy_table_byte_equal"])
        self.assertEqual(roots["count"], 32_768)
        self.assertEqual(roots["center_norm_bound_failure_count"], 0)
        self.assertTrue(roots["bad_norm_mutation_rejected"])

        overflow = report["candidate_overflow_negative_control"]
        self.assertTrue(overflow["accepted"])
        self.assertEqual(overflow["candidate_transform_failure_flags"], 4)
        self.assertEqual(
            overflow["settled_sloppy_transform_failure_flags"], 4
        )
        self.assertEqual(
            overflow["canonical_malformed_output_count"], 131_072
        )
        self.assertEqual(
            overflow["settled_sloppy_canonical_malformed_output_count"],
            131_072,
        )
        self.assertEqual(overflow["noncanonical_output_count"], 0)
        self.assertEqual(
            overflow["settled_sloppy_noncanonical_output_count"], 0
        )
        self.assertTrue(
            overflow["candidate_settled_sloppy_output_byte_equal"]
        )

        edge, genuine = report["cases"]
        self.assertEqual(edge["label"], "synthetic-finite-edge-overlap-only")
        self.assertEqual(genuine["label"], "genuine-complete-block0")
        for case, expected_sloppy in (
            (edge, SLOPPY_EDGE_SHA256),
            (genuine, SLOPPY_GENUINE_SHA256),
        ):
            self.assertTrue(case["accepted"])
            self.assertEqual(
                case["candidate_output_sha256"], expected_sloppy
            )
            self.assertEqual(
                case["settled_sloppy_output_sha256"], expected_sloppy
            )
            self.assertTrue(case["settled_sloppy_output_known_answer"])
            self.assertTrue(case["candidate_matches_settled_sloppy_sha_pin"])
            self.assertEqual(
                case[
                    "candidate_settled_sloppy_disk_byte_mismatch_count"
                ],
                0,
            )
            self.assertTrue(
                case["candidate_settled_sloppy_all_sample_bytes_equal"]
            )
            self.assertEqual(case["candidate_transform_failure_flags"], 0)
            self.assertEqual(
                case["settled_sloppy_transform_failure_flags"], 0
            )
            self.assertEqual(
                case["exact_containment"]["sample_count"], 131_072
            )
            self.assertTrue(case["exact_overlap"]["accepted"])

        self.assertFalse(edge["containment_required_for_acceptance"])
        self.assertFalse(edge["exact_containment"]["accepted"])
        self.assertEqual(
            edge["exact_containment"]["squared_distance_failure_count"],
            130_065,
        )
        self.assertTrue(genuine["containment_required_for_acceptance"])
        self.assertTrue(genuine["exact_containment"]["accepted"])
        self.assertEqual(
            genuine["exact_containment"][
                "squared_distance_failure_count"
            ],
            0,
        )
        self.assertEqual(genuine["source_packet_sha256"], PACKET_SHA256)
        self.assertEqual(genuine["source_packet_bytes"], 31_457_408)
        event = genuine["event_scan"]
        self.assertTrue(event["accepted"])
        self.assertTrue(
            event["candidate_settled_sloppy_replay_artifact_byte_equal"]
        )
        self.assertTrue(event["settled_sloppy_accepted"])
        self.assertTrue(event["settled_sloppy_device_matches_host"])
        self.assertTrue(event["settled_sloppy_shared_endpoints_agree"])
        self.assertEqual(event["candidate_failure_flags"], 0)
        self.assertEqual(event["settled_sloppy_failure_flags"], 0)
        self.assertEqual(event["candidate_direct_count"], 3_539)
        self.assertEqual(event["settled_sloppy_direct_count"], 3_539)
        self.assertEqual(event["candidate_stationary_count"], 1)
        self.assertEqual(event["settled_sloppy_stationary_count"], 1)

        timing = genuine["interleaved_timing_ms"]
        self.assertGreater(timing["ordinary_median"], 0.0)
        self.assertGreater(timing["candidate_median"], 0.0)
        self.assertGreater(timing["settled_sloppy_median"], 0.0)
        self.assertGreater(timing["median_speedup"], 0.0)
        self.assertGreater(
            timing["candidate_speedup_over_settled_sloppy"], 0.0
        )
        self.assertTrue(report["settled_sloppy_entry_replayed_in_this_run"])
        self.assertTrue(report["joint_schedule_only"])
        self.assertFalse(report["optimization_selected_for_production"])
        self.assertEqual(
            report["selection_status"],
            "qualification-only-local-gain-too-small-no-h100-measurement",
        )
        self.assertEqual(
            report["runtime_instrumentation_status"],
            "not-inspected-by-runner",
        )
        self.assertFalse(report["performance_evidence_eligible"])
        self.assertFalse(report["cuda_to_lean_refinement_proved"])
        self.assertFalse(report["source_claim_ready"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["pt21_atom_discharged"])


@unittest.skipUnless(
    STRICT_BINARY,
    "strict sm90 joint qualification executable is not configured",
)
class PT21DDTile9SloppyRootStrictTargetTests(unittest.TestCase):
    def test_non_h100_is_rejected_before_fixture_open(self) -> None:
        completed = subprocess.run(
            [
                STRICT_BINARY,
                "--source-packet=/does/not/exist",
                f"--expected-source-packet-sha256={PACKET_SHA256}",
                "--repetitions=1",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("requires NVIDIA H100 sm_90", completed.stderr)


if __name__ == "__main__":
    unittest.main()
