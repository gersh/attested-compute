# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from decimal import Decimal
import unittest

from tg_verifier.goldbach_gpu_campaign import PRODUCTION_EVEN_COUNT
from tg_verifier.goldbach_gpu_projection import (
    GoldbachGPUProjectionError,
    median_seconds,
    project_source_height,
)


class GoldbachGPUProjectionTests(unittest.TestCase):
    def test_literal_count_and_units_are_not_rounded(self) -> None:
        report = project_source_height(
            sample_even_count=600_000_000,
            sample_seconds="1.03465",
            speedups=("1", "14.3"),
            cluster_gpu_count=8,
        )
        self.assertEqual(
            report["production_even_count"], str(PRODUCTION_EVEN_COUNT)
        )
        rate = Decimal(600_000_000) / Decimal("1.03465")
        seconds = Decimal(PRODUCTION_EVEN_COUNT) / rate
        expected_hours = seconds / Decimal(3600)
        one_x = report["rows"][0]
        self.assertEqual(
            Decimal(one_x["one_gpu_source_hours"]),
            expected_hours.quantize(Decimal("0.000000000001")),
        )
        self.assertEqual(
            Decimal(one_x["cluster_wall_hours"]),
            (expected_hours / 8).quantize(Decimal("0.000000000001")),
        )

    def test_median_is_decimal_and_input_fails_closed(self) -> None:
        self.assertEqual(median_seconds(("3", "1", "2")), Decimal(2))
        self.assertEqual(median_seconds(("1", "2")), Decimal("1.5"))
        for value in ((), ("0",), ("NaN",)):
            with self.subTest(value=value):
                with self.assertRaises(GoldbachGPUProjectionError):
                    median_seconds(value)

    def test_distinct_production_count_is_explicit(self) -> None:
        report = project_source_height(
            sample_even_count=100,
            sample_seconds="1",
            speedups=("1",),
            cluster_gpu_count=2,
            production_even_count=1_000,
            production_shards=10,
            leaves_per_group=2,
        )
        self.assertEqual(report["production_even_count"], "1000")
        self.assertEqual(report["production_checkpoint_leaf_count"], 10)
        self.assertEqual(report["maximum_checkpoint_leaf_even_count"], "100")
        self.assertEqual(report["rows"][0]["cluster_wall_hours"], "0.001388888889")


if __name__ == "__main__":
    unittest.main()
