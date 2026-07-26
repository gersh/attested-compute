# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "gpu/include/sparkinterval/tg_platt_dd_transform.hpp"
SOURCE = ROOT / "gpu/platform/h100/h100_tg_platt_windowed_dd_disk_semantic.cu"
RUNNER_ENV = "TG_PLATT_DD_TRANSFORM_API_SMOKE"


class PlattDDTransformAPITest(unittest.TestCase):
    def test_api_is_fixed_source_geometry_and_device_to_device(self) -> None:
        header = HEADER.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        for token in (
            "kSourceSampleCount",
            "kSourceRequiredBegin",
            "kSourceRequiredEnd",
            "kSourceRequiredCount",
            "run_source_window",
            "device_required_samples",
            "device_input_failure_flags_qualification",
            "workspace_device_bytes",
        ):
            self.assertIn(token, header)
        self.assertIn("static_assert(kSourceRequiredCount == 25'741U)", source)
        self.assertIn("dd_build_gamma_rows", source)
        self.assertIn("dd_extract_samples", source)
        self.assertIn("dd_disk_input_well_formed", source)
        self.assertIn("cudaMemsetAsync(workspace->input_failure_flags", source)
        self.assertIn("kQualificationInputFailureGamma", source)
        self.assertIn("kQualificationInputFailureSkn", source)
        self.assertIn("__longlong_as_double(0x7ff0000000000000LL)", source)
        self.assertIn("kGTruncationError", source)
        self.assertIn("kTaylorError", source)

    def test_optional_cuda_smoke(self) -> None:
        value = os.environ.get(RUNNER_ENV)
        if not value:
            self.skipTest(f"set {RUNNER_ENV} to exercise the device API")
        runner = Path(value)
        if not runner.is_file():
            self.skipTest(f"DD transform API smoke runner is missing: {runner}")
        completed = subprocess.run(
            [str(runner)], check=True, capture_output=True, text=True
        )
        result = json.loads(completed.stdout)
        self.assertTrue(result["accepted"])
        self.assertTrue(result["source_geometry"])
        self.assertTrue(result["device_to_device_api"])
        self.assertEqual(result["required_sample_count"], 25_741)
        self.assertEqual(result["workspace_device_bytes"], 195_429_316)
        self.assertTrue(result["all_required_disks_finite"])
        self.assertTrue(result["synthetic_zero_input_only"])
        self.assertTrue(result["valid_input_failure_flags_zero"])
        self.assertTrue(result["valid_ordinary_tile9_byte_identical"])
        self.assertEqual(result["forgery_cases"], 20)
        self.assertEqual(result["ordinary_forgery_cases"], 10)
        self.assertEqual(result["tile9_forgery_cases"], 10)
        self.assertTrue(result["gamma_failure_bits_exact"])
        self.assertTrue(result["skn_failure_bits_exact"])
        self.assertTrue(result["canonical_malformed_output_complete"])
        self.assertTrue(result["event_scanner_fail_closed_complete"])
        self.assertFalse(result["physical_trace_refinement_proved"])
        self.assertFalse(result["pt21_source_claim_discharged"])


if __name__ == "__main__":
    unittest.main()
