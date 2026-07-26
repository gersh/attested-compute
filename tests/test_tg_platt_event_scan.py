# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "gpu/include/sparkinterval/tg_platt_event_scan.hpp"
SOURCE = ROOT / "gpu/platform/h100/h100_tg_platt_event_scan.cu"
BENCHMARK = ROOT / "reference/tg_platt_event_scan_benchmark.cu"
RUNNER_ENV = "TG_PLATT_EVENT_SCAN_BENCHMARK"


class PlattEventScanTest(unittest.TestCase):
    def test_source_geometry_and_fail_closed_contract_are_explicit(self) -> None:
        header = HEADER.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        benchmark = BENCHMARK.read_text(encoding="utf-8")
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        for token in (
            "kRequiredLower = -12'870",
            "kRequiredUpper = 12'870",
            "kLeftFlankLower = -12'800",
            "kLeftFlankUpper = -12'288",
            "kMainLower = -12'288",
            "kMainUpper = 12'288",
            "kRightFlankLower = 12'288",
            "kRightFlankUpper = 12'800",
            "kLatticeNumerator = 21",
            "kLatticeDenominator = 512",
            "certified_multiplicity_slots",
            "requires_adaptive_resolution",
            "scan_source_required_samples",
            "replay_and_check",
            "create_replay_capture",
            "enqueue_replay_capture",
            "replay_captured",
        ):
            self.assertIn(token, header)
        for token in (
            "certify_disk",
            "exact_sum_sign",
            "disk_strict_gt",
            "exact_stat_pt",
            "kFailureAmbiguousDisk",
            "kFailureDirectOverflow",
            "kFailureStationaryOverflow",
            "merkle_leaf_kernel",
            "merkle_node_kernel",
            "shared_endpoints_agree",
        ):
            self.assertIn(token, source)
        self.assertIn("direct.source_nleft_units = -static_cast<int>(edge)", source)
        self.assertIn("edge_count - edge - 1U", source)
        self.assertIn("stationary.certified_multiplicity_slots = 0U", source)
        for token in (
            "SPARKINTERVAL_CMAKE_BUILD_CONFIG",
            "kNdebugDefined",
            "kReleasePerformanceBuild",
            '\\"build_profile\\"',
            '\\"cmake_build_config\\"',
            '\\"ndebug_defined\\"',
            '\\"release_performance_build\\"',
        ):
            self.assertIn(token, benchmark)
        benchmark_target = cmake[
            cmake.index(
                "add_executable(sparkinterval-tg-platt-event-scan-benchmark"
            ) :
            cmake.index(
                "add_executable(sparkinterval-tg-platt-event-record-kat"
            )
        ]
        self.assertIn(
            'SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"',
            benchmark_target,
        )

    def _assert_build_profile(self, result: dict[str, object]) -> None:
        profile = result["build_profile"]
        self.assertIsInstance(profile, dict)
        assert isinstance(profile, dict)
        config = profile["cmake_build_config"]
        ndebug = profile["ndebug_defined"]
        release = profile["release_performance_build"]
        self.assertIsInstance(config, str)
        self.assertIsInstance(ndebug, bool)
        self.assertIsInstance(release, bool)
        self.assertEqual(release, ndebug and config == "Release")

    def _runner(self) -> Path:
        value = os.environ.get(RUNNER_ENV)
        if not value:
            self.skipTest(f"set {RUNNER_ENV} to exercise the CUDA scanner")
        runner = Path(value)
        if not runner.is_file():
            self.skipTest(f"event scanner runner is missing: {runner}")
        return runner

    def _run(
        self, mode: str, *, asynchronous_capture: bool = False
    ) -> dict[str, object]:
        arguments = [
            str(self._runner()),
            "--mode",
            mode,
            "--iterations",
            "2",
        ]
        if asynchronous_capture:
            arguments.append("--async-capture")
        completed = subprocess.run(
            arguments,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_optional_cuda_valid_replay_and_geometry(self) -> None:
        result = self._run("valid")
        self._assert_build_profile(result)
        self.assertTrue(result["test_success"])
        self.assertTrue(result["accepted"])
        self.assertTrue(result["all_required_samples_certified"])
        self.assertEqual(result["required_sample_count"], 25_741)
        self.assertEqual(
            result["stream_ranges"],
            {
                "left_flank": [-12_800, -12_288],
                "main": [-12_288, 12_288],
                "right_flank": [12_288, 12_800],
            },
        )
        self.assertTrue(result["shared_endpoints_explicit"])
        self.assertTrue(result["shared_endpoints_agree"])
        self.assertTrue(result["device_matches_host_replay"])
        self.assertEqual(result["stationary_certified_multiplicity_slots"], 0)
        self.assertFalse(result["stationary_candidates_claim_two_zeros"])
        self.assertFalse(result["adaptive_resolve_stat_point_implemented"])
        self.assertFalse(result["hardy_z_realization_proved"])
        self.assertFalse(result["turing_analytic_bounds_proved"])
        self.assertFalse(result["pt21_source_claim_discharged"])

    def test_optional_cuda_ambiguous_and_malformed_fail_closed(self) -> None:
        ambiguous = self._run("ambiguous")
        malformed = self._run("malformed")
        for result, expected in ((ambiguous, 2), (malformed, 1)):
            self.assertTrue(result["test_success"])
            self.assertFalse(result["accepted"])
            self.assertEqual(result["failure_flags"], expected)
            self.assertTrue(result["expected_failure_observed"])
            self.assertTrue(result["device_matches_host_replay"])
            self.assertFalse(result["digest_valid"])

    def test_optional_cuda_stat_pt_is_strict(self) -> None:
        result = self._run("strict")
        self.assertTrue(result["test_success"])
        self.assertTrue(result["accepted"])
        self.assertTrue(result["strict_predicate_test_passed"])
        self.assertEqual(result["certified_direct_multiplicity_slots"], 0)
        self.assertEqual(result["streams"][1]["stationary_candidates"], 1)

    def test_optional_cuda_binary64_edges_match_exact_host_replay(
        self,
    ) -> None:
        result = self._run("edge")
        self.assertTrue(result["test_success"])
        self.assertTrue(result["accepted"])
        self.assertTrue(result["device_matches_host_replay"])
        self.assertTrue(result["all_required_samples_certified"])

    def test_optional_cuda_pinned_capture_preserves_exact_replay(
        self,
    ) -> None:
        result = self._run("edge", asynchronous_capture=True)
        synchronous = self._run("edge")
        self.assertTrue(result["test_success"])
        self.assertTrue(result["accepted"])
        self.assertTrue(result["asynchronous_capture"])
        self.assertTrue(result["device_matches_host_replay"])
        self.assertEqual(result["replay_capture_pinned_bytes"], 2_051_576)
        self.assertTrue(result["replay_capture_lifecycle_guarded"])
        self.assertEqual(
            result["artifact_sha256"], synchronous["artifact_sha256"]
        )
        self.assertEqual(result["streams"], synchronous["streams"])

    def test_optional_cuda_bounded_overflow_fails_closed(self) -> None:
        result = self._run("overflow")
        self.assertTrue(result["test_success"])
        self.assertFalse(result["accepted"])
        self.assertEqual(result["failure_flags"], 24)
        self.assertTrue(result["expected_failure_observed"])
        self.assertTrue(result["device_matches_host_replay"])
        self.assertFalse(result["digest_valid"])

    def test_optional_cuda_rejects_noncanonical_iteration_count(self) -> None:
        completed = subprocess.run(
            [str(self._runner()), "--iterations", "2junk"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("--iterations is outside", completed.stderr)


if __name__ == "__main__":
    unittest.main()
