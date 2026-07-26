# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Unit-checked source-height projections for GoldbachGPU benchmarks.

The output is a sensitivity table, not an H100 benchmark.  It deliberately
keeps the measured-device multiplier explicit and computes from the literal
production even count rather than from a rounded endpoint.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from typing import Iterable

from .goldbach_gpu_campaign import (
    PRODUCTION_EVEN_COUNT,
    PRODUCTION_LEAVES_PER_GROUP,
    PRODUCTION_SHARDS,
)


SECONDS_PER_HOUR = Decimal(3600)
HOURS_PER_DAY = Decimal(24)
DAYS_PER_YEAR = Decimal("365.25")
SECONDS_PER_YEAR = SECONDS_PER_HOUR * HOURS_PER_DAY * DAYS_PER_YEAR
DEFAULT_SPEEDUPS = (Decimal(1), Decimal(2), Decimal(5), Decimal(10), Decimal("14.3"))


class GoldbachGPUProjectionError(ValueError):
    """A benchmark sample or scaling assumption was malformed."""


def _positive_decimal(name: str, value: str | Decimal) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise GoldbachGPUProjectionError(f"{name} must be a decimal") from exc
    if not result.is_finite() or result <= 0:
        raise GoldbachGPUProjectionError(f"{name} must be finite and positive")
    return result


def _text(value: Decimal) -> str:
    # Fixed-point output prevents a unit-bearing result from silently changing
    # interpretation through exponent notation.
    result = format(value, ".12f").rstrip("0").rstrip(".")
    return result or "0"


def median_seconds(values: Iterable[str | Decimal]) -> Decimal:
    samples = sorted(_positive_decimal("sample seconds", value) for value in values)
    if not samples:
        raise GoldbachGPUProjectionError("at least one timing sample is required")
    middle = len(samples) // 2
    if len(samples) % 2:
        return samples[middle]
    return (samples[middle - 1] + samples[middle]) / 2


def project_source_height(
    *,
    sample_even_count: int,
    sample_seconds: str | Decimal,
    speedups: Iterable[str | Decimal] = DEFAULT_SPEEDUPS,
    cluster_gpu_count: int = 8,
    production_even_count: int = PRODUCTION_EVEN_COUNT,
    production_shards: int = PRODUCTION_SHARDS,
    leaves_per_group: int = PRODUCTION_LEAVES_PER_GROUP,
) -> dict[str, object]:
    """Project the full literal range under explicit equal-throughput factors."""

    if isinstance(sample_even_count, bool) or sample_even_count <= 0:
        raise GoldbachGPUProjectionError("sample_even_count must be positive")
    if isinstance(cluster_gpu_count, bool) or cluster_gpu_count <= 0:
        raise GoldbachGPUProjectionError("cluster_gpu_count must be positive")
    if isinstance(production_even_count, bool) or production_even_count <= 0:
        raise GoldbachGPUProjectionError("production_even_count must be positive")
    if isinstance(production_shards, bool) or production_shards <= 0:
        raise GoldbachGPUProjectionError("production_shards must be positive")
    if isinstance(leaves_per_group, bool) or leaves_per_group <= 0:
        raise GoldbachGPUProjectionError("leaves_per_group must be positive")
    seconds = _positive_decimal("sample_seconds", sample_seconds)
    factors = tuple(_positive_decimal("speedup", value) for value in speedups)
    if not factors or len(set(factors)) != len(factors):
        raise GoldbachGPUProjectionError("speedups must be nonempty and distinct")

    with localcontext() as context:
        context.prec = 50
        sample_count = Decimal(sample_even_count)
        source_count = Decimal(production_even_count)
        measured_rate = sample_count / seconds
        measured_source_seconds = source_count / measured_rate
        maximum_leaf_count = (
            production_even_count + production_shards - 1
        ) // production_shards
        rows = []
        for factor in factors:
            one_gpu_seconds = measured_source_seconds / factor
            cluster_seconds = one_gpu_seconds / Decimal(cluster_gpu_count)
            leaf_seconds = Decimal(maximum_leaf_count) / (measured_rate * factor)
            rows.append(
                {
                    "equal_throughput_factor_vs_measured_gpu": _text(factor),
                    "one_gpu_source_hours": _text(one_gpu_seconds / SECONDS_PER_HOUR),
                    "one_gpu_source_years": _text(one_gpu_seconds / SECONDS_PER_YEAR),
                    "cluster_wall_hours": _text(cluster_seconds / SECONDS_PER_HOUR),
                    "cluster_wall_years": _text(cluster_seconds / SECONDS_PER_YEAR),
                    "maximum_checkpoint_leaf_hours": _text(
                        leaf_seconds / SECONDS_PER_HOUR
                    ),
                    "maximum_scheduler_group_hours": _text(
                        leaf_seconds
                        * Decimal(leaves_per_group)
                        / SECONDS_PER_HOUR
                    ),
                }
            )

        return {
            "schema": "sparkinterval.goldbach-gpu-source-projection.v1",
            "classification": "sensitivity-only-not-an-h100-benchmark",
            "production_even_count": str(production_even_count),
            "production_checkpoint_leaf_count": production_shards,
            "maximum_checkpoint_leaf_even_count": str(maximum_leaf_count),
            "sample_even_count": str(sample_even_count),
            "sample_seconds": _text(seconds),
            "measured_even_per_second": _text(measured_rate),
            "cluster_gpu_count": cluster_gpu_count,
            "year_definition_days": _text(DAYS_PER_YEAR),
            "rows": rows,
            "assumptions": [
                "equal throughput across GPUs",
                "ideal division of source work across cluster GPUs",
                "sample main-loop rate extrapolates across the source range",
                "startup, scheduling, attestation, retry, and storage overhead excluded",
            ],
        }


__all__ = [
    "DEFAULT_SPEEDUPS",
    "GoldbachGPUProjectionError",
    "median_seconds",
    "project_source_height",
]
