# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest

from tg_verifier.goldbach_tile_sieve_projection import (
    GoldbachTileProjectionError,
    project_source_campaign,
)


class GoldbachTileSieveProjectionTests(unittest.TestCase):
    def test_source_projection_preserves_host_floor(self) -> None:
        projection = project_source_campaign(
            measured_candidates=2_147_483_648,
            measured_pipeline_seconds=4.404619220,
            measured_host_seconds=3.738536204,
            measured_gpu_seconds=0.632244415,
        )
        self.assertGreater(
            projection["gpu_only_scaled_fleet_hours"],
            projection["full_pipeline_scaled_fleet_hours"],
        )
        self.assertGreater(
            projection["required_devices_at_gpu_only_scaled_rate"],
            projection["required_devices_at_full_pipeline_scaled_rate"],
        )
        self.assertGreater(
            projection["required_devices_at_full_pipeline_scaled_rate"],
            projection["required_devices_at_zero_host_gpu_scaled_rate"],
        )
        self.assertFalse(projection["h100_measurement_present"])
        self.assertFalse(projection["projection_is_certificate"])

    def test_invalid_component_accounting_fails(self) -> None:
        with self.assertRaises(GoldbachTileProjectionError):
            project_source_campaign(
                measured_candidates=100,
                measured_pipeline_seconds=1,
                measured_host_seconds=0.75,
                measured_gpu_seconds=0.5,
            )


if __name__ == "__main__":
    unittest.main()
