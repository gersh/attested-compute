# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BINARY = os.environ.get("TG_PLATT_DD_TILE9_QUALIFICATION")


@unittest.skipUnless(BINARY, "TG_PLATT_DD_TILE9_QUALIFICATION is not set")
class PlattDDTile9QualificationTests(unittest.TestCase):
    def run_binary(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [BINARY, *arguments],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
            timeout=120,
        )

    def test_synthetic_outputs_and_event_artifacts_are_byte_identical(
        self,
    ) -> None:
        completed = self.run_binary("--repetitions=1")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(
            report["schema"],
            "sparkinterval.tg.platt-dd-tile9-qualification.v1",
        )
        self.assertTrue(report["accepted"])
        self.assertEqual(
            report["accepted_semantics"], "byte_identity_qualification"
        )
        self.assertEqual(report["genuine_source_case_count"], 0)
        self.assertEqual(report["accepted_genuine_source_case_count"], 0)
        self.assertFalse(report["useful_source_acceptance_observed"])
        self.assertEqual(
            report["performance_evidence_eligible_case_count"], 0
        )
        self.assertTrue(report["qualification_only"])
        self.assertEqual(
            set(report["build_profile"]),
            {
                "cmake_build_config",
                "ndebug_defined",
                "release_performance_build",
            },
        )
        self.assertEqual(set(report["device_profile"]), {"name", "major", "minor"})
        self.assertIsInstance(report["device_profile"]["name"], str)
        self.assertGreaterEqual(report["device_profile"]["major"], 1)
        self.assertGreaterEqual(report["device_profile"]["minor"], 0)
        self.assertFalse(report["strict_h100_target"])
        self.assertFalse(report["target_h100_measured"])
        self.assertEqual(report["early_stages_fused"], 9)
        self.assertEqual(report["shared_tile_values"], 512)
        self.assertEqual(report["shared_tile_bytes"], 20_480)
        self.assertEqual(report["shared_root_cache_bytes"], 12_288)
        self.assertEqual(report["declared_shared_bytes_per_block"], 32_768)
        self.assertEqual(report["ordinary_stages_begin"], 10)
        self.assertEqual(report["sample_disk_count"], 131_072)
        self.assertEqual(
            [case["label"] for case in report["cases"]],
            ["synthetic-zero", "synthetic-finite-edge"],
        )
        for case in report["cases"]:
            self.assertTrue(case["all_131072_sample_disks_byte_equal"])
            self.assertEqual(case["disk_byte_mismatch_count"], 0)
            self.assertTrue(case["event_artifact_compared"])
            self.assertTrue(case["event_artifact_byte_equal"])
            self.assertTrue(case["ordinary_device_matches_host_replay"])
            self.assertTrue(case["tile9_device_matches_host_replay"])
            self.assertEqual(
                case["ordinary_output_fnv1a64"],
                case["tile9_output_fnv1a64"],
            )
            self.assertFalse(case["performance_evidence_eligible"])
        self.assertFalse(report["source_claim_ready"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["pt21_atom_discharged"])

    def test_malformed_source_packet_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            packet = Path(directory) / "not-pt21src2.bin"
            packet.write_bytes(b"not a source packet")
            completed = self.run_binary(
                f"--source-packet={packet}", "--repetitions=1"
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("source packet", completed.stderr)
        self.assertEqual(completed.stdout, "")


class PlattDDTile9SourceBoundaryTests(unittest.TestCase):
    def test_default_entry_point_does_not_call_qualification_entry_point(
        self,
    ) -> None:
        source = (
            ROOT
            / "gpu/platform/h100/h100_tg_platt_windowed_dd_disk_semantic.cu"
        ).read_text(encoding="utf-8")
        default_begin = source.index("void run_source_window(")
        qualification_begin = source.index(
            "void run_source_window_tile9_qualification("
        )
        default_body = source[default_begin:qualification_begin]
        self.assertNotIn("dd_transform_tile9_qualification", default_body)
        self.assertIn("dd_transform(", default_body)

    def test_header_marks_alternative_as_qualification_only(self) -> None:
        header = (
            ROOT / "gpu/include/sparkinterval/tg_platt_dd_transform.hpp"
        ).read_text(encoding="utf-8")
        self.assertIn("Qualification-only alternative", header)
        self.assertIn("run_source_window_tile9_qualification", header)
        self.assertIn("Qualification consumers must", header)
        self.assertIn("closed on any difference", header)

    def test_runner_has_device_profile_and_strict_h100_guard(self) -> None:
        source = (
            ROOT / "reference/tg_platt_dd_tile9_qualification.cu"
        ).read_text(encoding="utf-8")
        self.assertIn("require_and_read_device_profile", source)
        self.assertIn("properties.major == 9", source)
        self.assertIn("properties.minor == 0", source)
        self.assertIn('find("H100")', source)
        self.assertIn("SPARKINTERVAL_REQUIRE_H100_SM90", source)
        self.assertIn("device_profile", source)
        self.assertIn("strict_h100_target", source)
        self.assertIn("target_h100_measured", source)
        eligibility_begin = source.index(
            "result.performance_evidence_eligible ="
        )
        eligibility_end = source.index("return result;", eligibility_begin)
        self.assertNotIn(
            "target_h100_measured",
            source[eligibility_begin:eligibility_end],
        )

    def test_cmake_has_default_and_strict_h100_targets(self) -> None:
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn(
            "add_executable(sparkinterval-tg-platt-dd-tile9-qualification",
            cmake,
        )
        strict_name = (
            "sparkinterval-h100-tg-platt-dd-tile9-qualification"
        )
        strict_begin = cmake.index(f"add_executable({strict_name}")
        strict_end = cmake.index(
            "add_executable(", strict_begin + len("add_executable(")
        )
        strict_block = cmake[strict_begin:strict_end]
        self.assertIn(
            f"sparkinterval_configure_h100_kernel(\n    {strict_name}",
            strict_block,
        )
        self.assertIn("SPARKINTERVAL_REQUIRE_H100_SM90=1", strict_block)
        self.assertIn(
            "sparkinterval-h100-tg-platt-dd-transform", strict_block
        )
        self.assertIn(
            "sparkinterval-h100-tg-platt-event-scan", strict_block
        )


if __name__ == "__main__":
    unittest.main()
