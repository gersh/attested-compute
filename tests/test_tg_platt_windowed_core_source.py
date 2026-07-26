# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Static and optional CUDA checks for the PT21 source phase stream."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "gpu/platform/h100/h100_tg_platt_windowed_core.cu"


class PlattWindowedCoreSourceStreamTest(unittest.TestCase):
    def test_periodic_phase_recurrence_is_directed_and_fail_closed(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        for required in (
            "source_dd_complex_mul",
            "source_dd_construct_phase_steps",
            "source_dd_advance_phase",
            "block % options.reanchor_blocks == 0U",
            "source_dd_required_truth_radius",
            "periodic Q192 phase recurrence failed its final-height MPFR KAT",
            'source_dd_phase_physical_refinement_proved\\\":false',
        ):
            self.assertIn(required, source)
        self.assertIn("__dadd_ru", source)
        self.assertIn("__dmul_ru", source)

    def test_fast_dd_accumulator_keeps_a_directed_differential_gate(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        for required in (
            "source_dd_fast_add_center",
            "source_dd_fast_mul_center",
            "kSourceDDRnRelativeError",
            "source_dd_accumulate_all_stages_legacy",
            "source_dd_accumulator_required_radius",
            "legacy/compressed accumulator failed directed MPFR differential KAT",
            'source_dd_accumulator_algorithm\\\":\\\"bounded-fast-dd-center-l1-radius-v1',
            'source_dd_accumulator_compressed_kat_failures\\\":',
        ):
            self.assertIn(required, source)
        self.assertIn("kSourceDDAccumulatorWarps * 32U", source)

    def test_optional_cuda_recurrence_kat(self) -> None:
        binary = os.environ.get("TG_PLATT_WINDOWED_CORE_BINARY")
        if not binary:
            self.skipTest(
                "set TG_PLATT_WINDOWED_CORE_BINARY to exercise the CUDA recurrence KAT"
            )
        completed = subprocess.run(
            [
                binary,
                "--terms=256",
                "--stages=3",
                "--blocks=1",
                "--repetitions=1",
                "--fft-passes=0",
                "--source-geometry",
                "--reanchor-blocks=4",
                "--dd-source-blocks=9",
                "--dd-source-start-block=17",
            ],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertTrue(result["source_dd_phase_recurrence_enabled"])
        self.assertFalse(result["source_dd_q192_reanchor_every_block"])
        self.assertEqual(result["source_dd_phase_reanchor_blocks"], 4)
        self.assertGreater(result["source_dd_recurrence_kat_samples"], 0)
        self.assertEqual(result["source_dd_recurrence_kat_failures"], 0)
        self.assertEqual(
            result["source_dd_accumulator_algorithm"],
            "bounded-fast-dd-center-l1-radius-v1",
        )
        self.assertGreater(result["source_dd_accumulator_mpfr_kat_samples"], 0)
        self.assertEqual(result["source_dd_accumulator_legacy_kat_failures"], 0)
        self.assertEqual(
            result["source_dd_accumulator_compressed_kat_failures"], 0
        )
        self.assertFalse(result["source_dd_phase_physical_refinement_proved"])


if __name__ == "__main__":
    unittest.main()
