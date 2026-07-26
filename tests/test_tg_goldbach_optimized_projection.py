#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest

from tg_verifier.goldbach_optimized_projection import (
    GoldbachOptimizedProjectionError,
    project_optimized_prototype,
)


class GoldbachOptimizedProjectionTests(unittest.TestCase):
    def test_100_segment_gb10_envelope_is_exact_and_nonterminal(self) -> None:
        result = project_optimized_prototype(
            sample_even_count=20_000_000_000,
            sample_seconds="5.22129",
            initialization_seconds_per_leaf="0.423583",
        )
        self.assertEqual(
            result["classification"],
            "bounded-gb10-prototype-envelope-not-production-evidence",
        )
        self.assertFalse(result["production_gate_passed"])
        self.assertFalse(result["target_h100_measured"])
        self.assertFalse(result["source_identity_promoted"])
        projection = result["projection"]
        self.assertEqual(
            projection["measured_even_per_second"],
            "3830471013.86822030571",
        )
        self.assertEqual(
            projection["proportional_compute_wall_hours"],
            "141.636555989583",
        )
        self.assertEqual(
            projection["repeated_initialization_wall_hours"],
            "0.963886648889",
        )
        self.assertEqual(
            projection["total_wall_hours"],
            "142.600442638472",
        )
        self.assertEqual(
            projection["on_demand_cost_usd"],
            "7962.808716932288",
        )
        self.assertTrue(projection["arithmetic_within_deadline"])
        self.assertTrue(
            projection["arithmetic_within_on_demand_budget"]
        )

    def test_invalid_parameters_fail_closed(self) -> None:
        cases = (
            {"sample_even_count": 0},
            {"sample_even_count": True},
            {"sample_seconds": "0"},
            {"sample_seconds": "nan"},
            {"initialization_seconds_per_leaf": "-1"},
            {"cluster_gpu_count": 0},
            {"checkpoint_leaf_count": False},
        )
        base: dict[str, object] = {
            "sample_even_count": 20_000_000_000,
            "sample_seconds": "5.22129",
            "initialization_seconds_per_leaf": "0.423583",
        }
        for changed in cases:
            with self.subTest(changed=changed):
                arguments = dict(base)
                arguments.update(changed)
                with self.assertRaises(GoldbachOptimizedProjectionError):
                    project_optimized_prototype(**arguments)

    def test_wheel_filtered_packed_100_segment_envelope(self) -> None:
        result = project_optimized_prototype(
            sample_even_count=20_000_000_000,
            sample_seconds="2.35908",
            initialization_seconds_per_leaf="0.427747",
        )
        projection = result["projection"]
        self.assertEqual(
            projection["measured_even_per_second"],
            "8477881207.928514505655",
        )
        self.assertEqual(
            projection["proportional_compute_wall_hours"],
            "63.994140625",
        )
        self.assertEqual(
            projection["total_wall_hours"],
            "64.967502687222",
        )
        self.assertEqual(
            projection["on_demand_cost_usd"],
            "3627.785350054489",
        )
        self.assertTrue(projection["arithmetic_within_deadline"])
        self.assertTrue(
            projection["arithmetic_within_on_demand_budget"]
        )
        self.assertFalse(result["production_gate_passed"])
        self.assertFalse(result["target_h100_measured"])
        self.assertFalse(result["source_identity_promoted"])


if __name__ == "__main__":
    unittest.main()
