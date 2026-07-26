# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from decimal import Decimal
import unittest

from tg_verifier.hurst_h100_affine_projection import (
    HurstH100AffineProjectionError,
    project_hurst_h100_affine,
)


class HurstH100AffineProjectionTests(unittest.TestCase):
    def test_current_complete_device_work_and_exact_composition(self) -> None:
        report = project_hurst_h100_affine()
        self.assertEqual(
            report["classification"],
            "gb10_complete_device_work_linear_extrapolation_"
            "not_target_h100_measurement_budget_evidence_or_execution",
        )
        measurement = report["measurement"]
        self.assertEqual(measurement["device"], "NVIDIA GB10")
        self.assertEqual(measurement["rows"], 100_000_000)
        self.assertEqual(
            measurement["complete_device_work_milliseconds"], "191.737"
        )
        self.assertEqual(
            measurement["included_stages"],
            [
                "split-square segmented sieve",
                "packed support finalization",
                "exact affine prefix scan and reduction",
            ],
        )
        self.assertIn(
            "CPU summary and verification prefix through 10^12 and handoff",
            measurement["excluded_stages"],
        )

        composition = report["exact_affine_composition"]
        self.assertEqual(composition["worker_count"], 8)
        self.assertEqual(
            composition["algorithm"],
            "hurst-h100-eight-way-independent-affine-scan-v1",
        )
        self.assertEqual(composition["source_rows"], 9_999_000_000_000_000)
        self.assertEqual(
            composition["rows_per_worker"], 1_249_875_000_000_000
        )
        self.assertTrue(composition["equal_partition"])
        self.assertTrue(
            composition["lean_theorem"].endswith(
                "eightWorkerComposition_eq_single"
            )
        )

    def test_sensitivity_arithmetic_is_exact_but_not_a_budget_gate(self) -> None:
        report = project_hurst_h100_affine()
        baseline = report["equal_gb10_throughput_baseline"]
        sensitivity = report["h100_sensitivity"]
        self.assertEqual(
            Decimal(baseline["eight_worker_wall_hours"]),
            Decimal("665.686896875"),
        )
        self.assertEqual(
            sensitivity["throughput_factor_vs_measured_gb10"], "12.3"
        )
        self.assertEqual(
            sensitivity["eight_worker_wall_hours"],
            "54.12088592479674796747967480",
        )
        self.assertEqual(
            sensitivity["eight_worker_node_hours"],
            "432.9670873983739837398373984",
        )
        self.assertFalse(sensitivity["target_h100_measured"])
        self.assertFalse(sensitivity["production_budget_gate_passed"])
        self.assertFalse(report["production_gate"]["production_ready"])
        self.assertEqual(
            report["production_gate"]["projection_scope"],
            "terminal_h100_stage_only",
        )
        self.assertFalse(
            report["production_gate"][
                "complete_hybrid_campaign_eta_available"
            ]
        )
        self.assertTrue(
            report["production_gate"]["target_h100_measurement_required"]
        )

    def test_factor_is_explicit_and_must_be_positive_finite_decimal(self) -> None:
        report = project_hurst_h100_affine(
            gb10_to_h100_sensitivity=Decimal("1")
        )
        self.assertEqual(
            report["h100_sensitivity"]["eight_worker_wall_hours"],
            report["equal_gb10_throughput_baseline"][
                "eight_worker_wall_hours"
            ],
        )
        for bad in (
            Decimal("0"),
            Decimal("-1"),
            Decimal("NaN"),
            Decimal("Infinity"),
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(HurstH100AffineProjectionError):
                    project_hurst_h100_affine(
                        gb10_to_h100_sensitivity=bad
                    )
        with self.assertRaises(HurstH100AffineProjectionError):
            project_hurst_h100_affine(  # type: ignore[arg-type]
                gb10_to_h100_sensitivity=12.3
            )


if __name__ == "__main__":
    unittest.main()
