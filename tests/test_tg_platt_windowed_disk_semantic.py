#!/usr/bin/env python3
"""Static and optional runtime checks for the Platt complex-disk prototype."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.tg_platt_disk_endpoint_certificate import inspect


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "gpu/platform/h100/h100_tg_platt_windowed_disk_semantic.cu"


class PlattWindowedDiskSemanticTest(unittest.TestCase):
    def test_source_declares_fail_honest_scope_and_formal_boundary(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("physical_trace_refinement_proved\\\":false", text)
        self.assertIn("SparkInterval.Certified.ComplexDisk.AddCertificate+MulCertificate", text)
        self.assertIn("source_core_packet_to_disk_transform_candidate_not_a_zeta_certificate", text)
        self.assertIn("SparkInterval.Zeta.PlattDiskPipeline.Wire.checkBytes", text)

    def test_source_contains_every_transform_stage(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        stages = (
            "disk_build_gamma_rows",
            "disk_postprocess_G",
            "disk_pointwise_products",
            "disk_normalize_and_taylor_sum",
            "disk_initialize_half_spectrum",
            "disk_hermidft_preprocess",
            "disk_extract_samples",
        )
        for stage in stages:
            self.assertIn(stage, text)
        self.assertEqual(text.count("disk_transform("), 6)

    def test_runtime_small_kat_when_binary_is_supplied(self) -> None:
        binary = os.environ.get("TG_PLATT_DISK_BINARY")
        if not binary:
            self.skipTest("set TG_PLATT_DISK_BINARY to exercise the CUDA KAT")
        with tempfile.TemporaryDirectory() as directory:
            certificate = Path(directory) / "endpoint.bin"
            completed = subprocess.run(
                [binary, "--length=8", "--stages=3", "--no-source-errors",
                 f"--endpoint-certificate={certificate}"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            checked = inspect(certificate)
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual(result["schema"], "sparkinterval.tg.platt-windowed-disk-semantic.v2")
        self.assertTrue(result["all_output_disks_finite"])
        self.assertTrue(result["small_long_double_kat_contained"])
        self.assertFalse(result["physical_trace_refinement_proved"])
        self.assertTrue(result["endpoint_certificate_exported"])
        self.assertEqual(checked["sha256"], result["endpoint_certificate_sha256"])


if __name__ == "__main__":
    unittest.main()
