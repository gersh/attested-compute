# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Transparent source projection for the exact tile-compacted Goldbach sieve.

This is a throughput sensitivity model, not an Azure or completion claim.  It
scales a measured contiguous source-height sample linearly and keeps the host
schedule fixed when only the GPU stage is accelerated.
"""

from __future__ import annotations

import math


SOURCE_ODD_CANDIDATES = 2_000_000_000_000_000_000
ONE_WEEK_SECONDS = 7 * 24 * 60 * 60


class GoldbachTileProjectionError(ValueError):
    """A projection input was non-finite or outside its physical domain."""


def _positive(value: float | int, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GoldbachTileProjectionError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise GoldbachTileProjectionError(f"{name} must be positive and finite")
    return result


def project_source_campaign(
    *,
    measured_candidates: int,
    measured_pipeline_seconds: float,
    measured_host_seconds: float,
    measured_gpu_seconds: float,
    devices: int = 8,
    gpu_speedup: float = 12.3,
    full_pipeline_speedup: float = 12.3,
) -> dict[str, int | float | bool]:
    """Project the full odd-candidate scan from one measured sample."""

    candidates = _positive(measured_candidates, "measured_candidates")
    pipeline = _positive(measured_pipeline_seconds, "measured_pipeline_seconds")
    host = _positive(measured_host_seconds, "measured_host_seconds")
    gpu = _positive(measured_gpu_seconds, "measured_gpu_seconds")
    device_count = _positive(devices, "devices")
    gpu_factor = _positive(gpu_speedup, "gpu_speedup")
    pipeline_factor = _positive(full_pipeline_speedup, "full_pipeline_speedup")
    if host + gpu > pipeline * (1 + 1e-12):
        raise GoldbachTileProjectionError(
            "measured host plus GPU time exceeds the measured pipeline"
        )

    other = max(0.0, pipeline - host - gpu)
    measured_rate = candidates / pipeline
    measured_gpu_stage_rate = candidates / gpu
    gpu_only_seconds = host + other + gpu / gpu_factor
    gpu_only_rate = candidates / gpu_only_seconds
    zero_host_gpu_scaled_rate = measured_gpu_stage_rate * gpu_factor
    full_speedup_rate = measured_rate * pipeline_factor
    per_device_week_target = SOURCE_ODD_CANDIDATES / (
        device_count * ONE_WEEK_SECONDS
    )

    def fleet_hours(rate: float, count: float = device_count) -> float:
        return SOURCE_ODD_CANDIDATES / (rate * count) / 3600

    return {
        "source_odd_candidates": SOURCE_ODD_CANDIDATES,
        "devices": int(devices),
        "one_week_seconds": ONE_WEEK_SECONDS,
        "measured_candidates": int(measured_candidates),
        "measured_pipeline_seconds": pipeline,
        "measured_host_seconds": host,
        "measured_gpu_seconds": gpu,
        "measured_other_seconds": other,
        "measured_pipeline_candidates_per_second": measured_rate,
        "measured_gpu_stage_candidates_per_second": measured_gpu_stage_rate,
        "same_device_fleet_hours": fleet_hours(measured_rate),
        "gpu_speedup": gpu_factor,
        "gpu_only_scaled_candidates_per_second": gpu_only_rate,
        "gpu_only_scaled_fleet_hours": fleet_hours(gpu_only_rate),
        "zero_host_gpu_scaled_candidates_per_second": zero_host_gpu_scaled_rate,
        "zero_host_gpu_scaled_fleet_hours": fleet_hours(
            zero_host_gpu_scaled_rate
        ),
        "full_pipeline_speedup": pipeline_factor,
        "full_pipeline_scaled_candidates_per_second": full_speedup_rate,
        "full_pipeline_scaled_fleet_hours": fleet_hours(full_speedup_rate),
        "required_candidates_per_second_per_device_for_one_week": (
            per_device_week_target
        ),
        "required_speedup_over_measured_for_one_week": (
            per_device_week_target / measured_rate
        ),
        "required_devices_at_gpu_only_scaled_rate": math.ceil(
            SOURCE_ODD_CANDIDATES / (gpu_only_rate * ONE_WEEK_SECONDS)
        ),
        "required_devices_at_zero_host_gpu_scaled_rate": math.ceil(
            SOURCE_ODD_CANDIDATES /
            (zero_host_gpu_scaled_rate * ONE_WEEK_SECONDS)
        ),
        "required_devices_at_full_pipeline_scaled_rate": math.ceil(
            SOURCE_ODD_CANDIDATES / (full_speedup_rate * ONE_WEEK_SECONDS)
        ),
        "h100_measurement_present": False,
        "projection_is_certificate": False,
    }
