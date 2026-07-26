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
    "TG_PLATT_DD_SLOPPY_ROOT_WHOLE_TRANSFORM_QUALIFICATION"
)
PACKET = os.environ.get("TG_PLATT_DD_FULL_V2_PACKET")
PACKET_SHA256 = (
    "caecf8faee55a1c969062bb5d85cbd50"
    "ff70b0f461778e3fcb7fd0d561a058b7"
)


class PT21DDSloppyRootWholeTransformSourceTests(unittest.TestCase):
    def test_runner_has_fail_closed_authentication_and_exact_checks(
        self,
    ) -> None:
        source = (
            ROOT
            / "reference"
            / "tg_platt_dd_sloppy_root_whole_transform_qualification.cu"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "#if !defined("
            "SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION)",
            source,
        )
        self.assertIn(
            "SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION != 1",
            source,
        )
        self.assertIn(
            "!defined(SPARKINTERVAL_CUDA_FTZ_DISABLED)", source
        )
        self.assertIn("SPARKINTERVAL_CUDA_FTZ_DISABLED != 1", source)
        self.assertIn(PACKET_SHA256, source.replace('"\n    "', ""))
        self.assertIn("kRequiredPacketBytes = 31'457'408ULL", source)
        self.assertIn(
            "kRequiredPacketLegacyChecksum64", source
        )
        self.assertIn("0x39d3821666d7af35ULL", source)
        self.assertIn("legacy_pt21_checksum", source)
        self.assertIn(
            "81e54dc8806211ecc5c69b484076cd28"
            "ba1a0ab56a62a6fc8158ec84972b5a3e",
            source.replace('"\n    "', ""),
        )
        self.assertIn("header.gamma_fnv1a64", source)
        self.assertIn("header.skn_fnv1a64", source)
        self.assertIn("header.source_terms != pw::kSourceTerms", source)
        self.assertIn("header.window_center", source)
        self.assertIn("the exact source packet", source)

        self.assertIn("boost::multiprecision::cpp_rational", source)
        self.assertIn("exact_all_sample_containment", source)
        self.assertIn("exact_all_sample_overlap", source)
        self.assertIn("radius_difference < 0", source)
        self.assertIn(
            "center_difference * center_difference", source
        )
        self.assertIn(
            "radius_difference * radius_difference", source
        )
        self.assertIn("device_root_table_qualification", source)
        self.assertIn("exact_root_table_audit", source)
        self.assertIn("ordinary_candidate_table_byte_equal", source)
        self.assertIn("norms[result.mutated_index] = 0.0", source)
        self.assertIn("bad_norm_mutation_rejected", source)
        self.assertIn("exact_sign_counts", source)
        self.assertIn("host_replay_integer_bits", source)
        self.assertIn("2176", source)
        self.assertIn("benchmark_interleaved", source)
        self.assertIn(
            "device_input_failure_flags_qualification", source
        )
        self.assertIn(
            r'json_escape(std::string_view("\x01", 1U)) == "\\u0001"',
            source,
        )
        self.assertIn("qualify_overflow_negative_control", source)
        self.assertIn("canonical_malformed_disk", source)
        self.assertIn("kQualificationArithmeticFailure", source)

    def test_candidate_is_an_explicit_guarded_entry_point(self) -> None:
        source = (
            ROOT
            / "reference"
            / "tg_platt_dd_sloppy_root_whole_transform_qualification.cu"
        ).read_text(encoding="utf-8")
        self.assertIn("pdt::run_source_window(", source)
        self.assertIn(
            "pdt::run_source_window_sloppy_root_qualification(", source
        )
        self.assertIn("ordinary_run_source_window_api_unchanged", source)
        self.assertIn("candidate_selected_by_compile_time_guard", source)
        self.assertIn("h100_runtime_claimed", source)
        self.assertIn("fixture_is_production_source_claim", source)
        self.assertIn("release_build_profile_eligible", source)
        self.assertIn("runtime_instrumentation_status", source)
        self.assertIn("not-inspected-by-runner", source)
        self.assertIn(
            r'<< ",\"performance_evidence_eligible\":false"',
            source,
        )
        self.assertIn("cuda_to_lean_refinement_proved", source)
        self.assertIn("production_ready", source)

    def test_build_and_production_symbol_isolation(self) -> None:
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        production = (
            ROOT
            / "gpu"
            / "platform"
            / "h100"
            / "h100_tg_platt_windowed_dd_disk_semantic.cu"
        ).read_text(encoding="utf-8")
        ordinary_body = production[
            production.index("void run_source_window(\n") :
            production.index("void run_source_window_tile9_qualification(")
        ]
        self.assertNotIn("sloppy_root", ordinary_body)
        self.assertEqual(
            hashlib.sha256(ordinary_body.encode()).hexdigest(),
            "89c15418506d386e2b678aef8cae3787"
            "a1934cfdf94831b1010df3b826b9ecd1",
        )

        portable_begin = cmake.index(
            "add_executable(\n"
            "    sparkinterval-tg-platt-dd-sloppy-root-whole-transform-"
            "qualification"
        )
        portable_end = cmake.index(
            "add_executable(", portable_begin + len("add_executable(")
        )
        portable = cmake[portable_begin:portable_end]
        self.assertIn("--fmad=false", portable)
        self.assertIn("--ftz=false", portable)
        self.assertIn("SPARKINTERVAL_CUDA_FTZ_DISABLED=1", portable)
        self.assertIn(
            "sparkinterval-tg-platt-dd-sloppy-root-transform-qualification",
            portable,
        )
        self.assertIn("sparkinterval-tg-platt-event-scan", portable)
        self.assertNotIn(
            "\n      sparkinterval-tg-platt-dd-transform\n", portable
        )

        strict_begin = cmake.index(
            "add_executable(\n"
            "    sparkinterval-h100-tg-platt-dd-sloppy-root-whole-"
            "transform-qualification"
        )
        strict_end = cmake.index(
            "add_executable(", strict_begin + len("add_executable(")
        )
        strict = cmake[strict_begin:strict_end]
        self.assertIn(
            "sparkinterval_configure_h100_kernel(\n"
            "    sparkinterval-h100-tg-platt-dd-sloppy-root-whole-"
            "transform-qualification",
            strict,
        )
        self.assertIn("SPARKINTERVAL_REQUIRE_H100_SM90=1", strict)
        self.assertIn(
            "sparkinterval-h100-tg-platt-dd-sloppy-root-transform-"
            "qualification",
            strict,
        )


@unittest.skipUnless(
    BINARY,
    "whole-transform sloppy-root qualification executable is not configured",
)
class PT21DDSloppyRootWholeTransformArgumentTests(unittest.TestCase):
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

    def test_unqualified_sha_pin_is_rejected_before_packet_open(self) -> None:
        completed = self.run_binary(
            "--source-packet=/does/not/exist",
            f"--expected-source-packet-sha256={'0' * 64}",
            "--repetitions=1",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("not the qualified", completed.stderr)


@unittest.skipUnless(BINARY, "qualification executable is required")
class PT21DDSloppyRootWholeTransformKnownAnswerTests(unittest.TestCase):
    def test_genuine_block_and_finite_edge_qualification(self) -> None:
        if not PACKET:
            self.fail(
                "TG_PLATT_DD_FULL_V2_PACKET is mandatory when the "
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
            "sparkinterval.tg.platt-dd-sloppy-root-whole-transform-"
            "qualification.v1",
        )
        self.assertTrue(report["accepted"])
        self.assertTrue(report["qualification_only"])
        self.assertTrue(report["json_escape_control_character_kat"])
        self.assertTrue(report["authenticated_fixture_required"])
        self.assertFalse(report["fixture_is_production_source_claim"])
        self.assertEqual(report["sample_disk_count"], 131_072)
        self.assertEqual(report["required_sample_count"], 25_741)
        self.assertEqual(
            report["ordinary_expected_output_legacy_checksum64"],
            "a7b7b42ab245b042",
        )
        self.assertEqual(
            report["legacy_checksum_algorithm"],
            "historical-pt21-fnv1a64-label-nonstandard-offset",
        )
        self.assertEqual(
            report["ordinary_expected_genuine_output_sha256"],
            "81e54dc8806211ecc5c69b484076cd28"
            "ba1a0ab56a62a6fc8158ec84972b5a3e",
        )
        self.assertEqual(
            report["ordinary_expected_finite_edge_output_sha256"],
            "72ba9bacc3a312ae18c5d423388beae5"
            "2a621f3c81e37a1a006d91acc6d6a713",
        )
        self.assertFalse(report["strict_h100_target"])
        self.assertFalse(report["target_h100_measured"])
        self.assertFalse(report["h100_runtime_claimed"])

        roots = report["root_table_audit"]
        self.assertTrue(roots["accepted"])
        self.assertEqual(roots["count"], 32_768)
        self.assertEqual(roots["malformed_root_count"], 0)
        self.assertEqual(roots["malformed_norm_count"], 0)
        self.assertEqual(roots["center_norm_bound_failure_count"], 0)
        self.assertTrue(roots["ordinary_candidate_table_byte_equal"])
        self.assertTrue(roots["bad_norm_mutation_rejected"])
        self.assertEqual(roots["bad_norm_mutation_failure_count"], 1)
        overflow = report["candidate_overflow_negative_control"]
        self.assertTrue(overflow["accepted"])
        self.assertTrue(overflow["finite_input"])
        self.assertEqual(overflow["expected_failure_flag"], 4)
        self.assertEqual(
            overflow["candidate_transform_failure_flags"], 4
        )
        self.assertEqual(
            overflow["canonical_malformed_output_count"], 131_072
        )
        self.assertEqual(overflow["noncanonical_output_count"], 0)

        self.assertEqual(
            [case["label"] for case in report["cases"]],
            [
                "synthetic-finite-edge-overlap-only",
                "genuine-complete-block0",
            ],
        )
        edge, genuine = report["cases"]
        self.assertEqual(
            edge["ordinary_output_legacy_checksum64"],
            "f581990198bdc555",
        )
        self.assertEqual(
            genuine["ordinary_output_legacy_checksum64"],
            "a7b7b42ab245b042",
        )
        self.assertEqual(
            edge["ordinary_output_sha256"],
            "72ba9bacc3a312ae18c5d423388beae5"
            "2a621f3c81e37a1a006d91acc6d6a713",
        )
        self.assertEqual(
            genuine["ordinary_output_sha256"],
            "81e54dc8806211ecc5c69b484076cd28"
            "ba1a0ab56a62a6fc8158ec84972b5a3e",
        )
        for case in report["cases"]:
            self.assertTrue(
                case["ordinary_legacy_checksum_matches_diagnostic"]
            )
            self.assertTrue(case["ordinary_output_known_answer"])
            self.assertEqual(len(case["candidate_output_sha256"]), 64)
            int(case["candidate_output_sha256"], 16)
            self.assertEqual(
                case["exact_containment"]["sample_count"], 131_072
            )
            self.assertEqual(
                case["exact_containment"]["malformed_count"], 0
            )
            self.assertEqual(
                case["exact_containment"]["radius_order_failure_count"], 0
            )
            self.assertEqual(case["ordinary_transform_failure_flags"], 0)
            self.assertEqual(case["candidate_transform_failure_flags"], 0)
            self.assertTrue(case["exact_overlap"]["accepted"])
            self.assertEqual(case["exact_overlap"]["sample_count"], 131_072)
            self.assertEqual(case["exact_overlap"]["malformed_count"], 0)
            self.assertEqual(
                case["exact_overlap"]["squared_distance_failure_count"], 0
            )
            ratios = case["radius_inflation"]
            if ratios["finite_ratio_count"]:
                self.assertGreaterEqual(ratios["median"], 1.0)
                self.assertGreaterEqual(ratios["p90"], ratios["median"])
                self.assertGreaterEqual(ratios["p99"], ratios["p90"])
                self.assertGreaterEqual(ratios["maximum"], ratios["p99"])
            self.assertEqual(
                case["ordinary_all_sample_signs"]["malformed"], 0
            )
            self.assertEqual(
                case["candidate_all_sample_signs"]["malformed"], 0
            )
            self.assertTrue(case["accepted"])

        self.assertFalse(edge["containment_required_for_acceptance"])
        self.assertTrue(edge["overlap_required_for_acceptance"])
        self.assertFalse(edge["exact_containment"]["accepted"])
        self.assertEqual(
            edge["exact_containment"]["squared_distance_failure_count"],
            130_065,
        )
        self.assertEqual(edge["all_sample_exact_sign_mismatch_count"], 0)
        self.assertEqual(
            edge["required_sample_exact_sign_mismatch_count"], 0
        )
        self.assertTrue(genuine["containment_required_for_acceptance"])
        self.assertFalse(genuine["overlap_required_for_acceptance"])
        self.assertTrue(genuine["exact_containment"]["accepted"])
        self.assertEqual(
            genuine["exact_containment"][
                "squared_distance_failure_count"
            ],
            0,
        )
        self.assertEqual(genuine["source_packet_bytes"], 31_457_408)
        self.assertEqual(genuine["source_packet_sha256"], PACKET_SHA256)
        self.assertEqual(
            genuine["source_packet_legacy_checksum64"],
            "39d3821666d7af35",
        )
        self.assertEqual(
            genuine["candidate_required_sample_signs"]["ambiguous"], 0
        )
        self.assertEqual(
            genuine["required_sample_exact_sign_mismatch_count"], 0
        )
        event = genuine["event_scan"]
        self.assertTrue(event["accepted"])
        self.assertEqual(event["host_replay_integer_bits"], 2176)
        self.assertTrue(event["ordinary_accepted"])
        self.assertTrue(event["candidate_accepted"])
        self.assertTrue(event["ordinary_device_matches_host"])
        self.assertTrue(event["candidate_device_matches_host"])
        self.assertTrue(event["ordinary_shared_endpoints_agree"])
        self.assertTrue(event["candidate_shared_endpoints_agree"])
        self.assertEqual(event["ordinary_failure_flags"], 0)
        self.assertEqual(event["candidate_failure_flags"], 0)
        self.assertEqual(event["ordinary_direct_count"], 3_539)
        self.assertEqual(event["candidate_direct_count"], 3_539)
        self.assertEqual(event["ordinary_stationary_count"], 1)
        self.assertEqual(event["candidate_stationary_count"], 1)
        self.assertGreater(
            genuine["interleaved_timing_ms"]["ordinary_median"], 0.0
        )
        self.assertGreater(
            genuine["interleaved_timing_ms"]["candidate_median"], 0.0
        )
        self.assertGreater(
            genuine["interleaved_timing_ms"]["median_speedup"], 0.0
        )
        self.assertTrue(report["release_build_profile_eligible"])
        self.assertEqual(
            report["runtime_instrumentation_status"],
            "not-inspected-by-runner",
        )
        self.assertFalse(report["performance_evidence_eligible"])
        self.assertFalse(report["cuda_to_lean_refinement_proved"])
        self.assertFalse(report["source_claim_ready"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["pt21_atom_discharged"])
        self.assertFalse(report["arithmetic_corpus_replayed_in_this_run"])


if __name__ == "__main__":
    unittest.main()
