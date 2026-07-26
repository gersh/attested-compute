# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Unit-checked projection for an unpromoted optimized Goldbach prototype.

This model deliberately separates work proportional to the number of evens
from initialization repeated once per immutable checkpoint leaf.  It is an
engineering envelope, not an H100 calibration or production admission.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext

from .goldbach_gpu_campaign import (
    ANALYTIC_10POW27_EVEN_COUNT,
    ANALYTIC_10POW27_SHARDS,
)


SECONDS_PER_HOUR = Decimal(3600)
DEFAULT_CLUSTER_GPUS = 8
DEFAULT_DEADLINE_HOURS = Decimal(168)
DEFAULT_BUDGET_USD = Decimal(10_000)
DEFAULT_ON_DEMAND_CLUSTER_HOUR_USD = Decimal("55.84")
DEFAULT_SPOT_CLUSTER_HOUR_USD = Decimal("11.352272")


class GoldbachOptimizedProjectionError(ValueError):
    """A prototype timing or projection parameter is malformed."""


def _positive_decimal(name: str, value: str | Decimal) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise GoldbachOptimizedProjectionError(
            f"{name} must be a decimal"
        ) from exc
    if not result.is_finite() or result <= 0:
        raise GoldbachOptimizedProjectionError(
            f"{name} must be finite and positive"
        )
    return result


def _nonnegative_decimal(name: str, value: str | Decimal) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise GoldbachOptimizedProjectionError(
            f"{name} must be a decimal"
        ) from exc
    if not result.is_finite() or result < 0:
        raise GoldbachOptimizedProjectionError(
            f"{name} must be finite and nonnegative"
        )
    return result


def _positive_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GoldbachOptimizedProjectionError(
            f"{name} must be a positive integer"
        )
    return value


def _text(value: Decimal) -> str:
    result = format(value, ".12f").rstrip("0").rstrip(".")
    return result or "0"


def project_optimized_prototype(
    *,
    sample_even_count: int,
    sample_seconds: str | Decimal,
    initialization_seconds_per_leaf: str | Decimal,
    fixed_seconds_per_leaf: str | Decimal = Decimal(0),
    production_even_count: int = ANALYTIC_10POW27_EVEN_COUNT,
    checkpoint_leaf_count: int = ANALYTIC_10POW27_SHARDS,
    cluster_gpu_count: int = DEFAULT_CLUSTER_GPUS,
    deadline_hours: str | Decimal = DEFAULT_DEADLINE_HOURS,
    budget_usd: str | Decimal = DEFAULT_BUDGET_USD,
    on_demand_cluster_hour_usd: str | Decimal = (
        DEFAULT_ON_DEMAND_CLUSTER_HOUR_USD
    ),
    spot_cluster_hour_usd: str | Decimal = (
        DEFAULT_SPOT_CLUSTER_HOUR_USD
    ),
) -> dict[str, object]:
    """Project exact source work under explicit equal-throughput assumptions."""

    sample_even_count = _positive_int("sample_even_count", sample_even_count)
    production_even_count = _positive_int(
        "production_even_count", production_even_count
    )
    checkpoint_leaf_count = _positive_int(
        "checkpoint_leaf_count", checkpoint_leaf_count
    )
    cluster_gpu_count = _positive_int("cluster_gpu_count", cluster_gpu_count)
    seconds = _positive_decimal("sample_seconds", sample_seconds)
    initialization = _positive_decimal(
        "initialization_seconds_per_leaf",
        initialization_seconds_per_leaf,
    )
    fixed = _nonnegative_decimal(
        "fixed_seconds_per_leaf", fixed_seconds_per_leaf
    )
    deadline = _positive_decimal("deadline_hours", deadline_hours)
    budget = _positive_decimal("budget_usd", budget_usd)
    demand_rate = _positive_decimal(
        "on_demand_cluster_hour_usd", on_demand_cluster_hour_usd
    )
    spot_rate = _positive_decimal(
        "spot_cluster_hour_usd", spot_cluster_hour_usd
    )

    with localcontext() as context:
        context.prec = 60
        sample_count = Decimal(sample_even_count)
        source_count = Decimal(production_even_count)
        leaf_count = Decimal(checkpoint_leaf_count)
        gpu_count = Decimal(cluster_gpu_count)
        measured_rate = sample_count / seconds
        compute_hours = (
            source_count / measured_rate / gpu_count / SECONDS_PER_HOUR
        )
        repeated_initialization_hours = (
            leaf_count
            * initialization
            / gpu_count
            / SECONDS_PER_HOUR
        )
        repeated_fixed_hours = (
            leaf_count * fixed / gpu_count / SECONDS_PER_HOUR
        )
        projected_hours = (
            compute_hours
            + repeated_initialization_hours
            + repeated_fixed_hours
        )
        demand_cost = projected_hours * demand_rate
        spot_cost = projected_hours * spot_rate
        maximum_leaf_even_count = (
            production_even_count
            + checkpoint_leaf_count
            - 1
        ) // checkpoint_leaf_count

        return {
            "schema": (
                "sparkinterval.goldbach-optimized-prototype-projection.v1"
            ),
            "classification": (
                "bounded-gb10-prototype-envelope-not-production-evidence"
            ),
            "production_gate_passed": False,
            "target_h100_measured": False,
            "source_identity_promoted": False,
            "inputs": {
                "sample_even_count": str(sample_even_count),
                "sample_seconds": _text(seconds),
                "initialization_seconds_per_leaf": _text(initialization),
                "fixed_seconds_per_leaf": _text(fixed),
                "production_even_count": str(production_even_count),
                "checkpoint_leaf_count": checkpoint_leaf_count,
                "maximum_checkpoint_leaf_even_count": str(
                    maximum_leaf_even_count
                ),
                "cluster_gpu_count": cluster_gpu_count,
                "deadline_hours": _text(deadline),
                "budget_usd": _text(budget),
                "on_demand_cluster_hour_usd": _text(demand_rate),
                "spot_cluster_hour_usd": _text(spot_rate),
            },
            "projection": {
                "measured_even_per_second": _text(measured_rate),
                "proportional_compute_wall_hours": _text(compute_hours),
                "repeated_initialization_wall_hours": _text(
                    repeated_initialization_hours
                ),
                "repeated_fixed_overhead_wall_hours": _text(
                    repeated_fixed_hours
                ),
                "total_wall_hours": _text(projected_hours),
                "total_wall_days": _text(projected_hours / Decimal(24)),
                "on_demand_cost_usd": _text(demand_cost),
                "spot_cost_usd": _text(spot_cost),
                "deadline_margin_hours": _text(deadline - projected_hours),
                "on_demand_budget_margin_usd": _text(budget - demand_cost),
                "arithmetic_within_deadline": projected_hours <= deadline,
                "arithmetic_within_on_demand_budget": demand_cost <= budget,
                "arithmetic_within_spot_budget": spot_cost <= budget,
            },
            "assumptions": [
                "the bounded GB10 per-even rate remains stable over every leaf",
                "eight GPUs have equal GB10 throughput and divide leaves ideally",
                "the measured initialization cost is paid once for every leaf",
                "the supplied fixed process overhead is paid once for every leaf",
                "no H100 speedup is assumed",
                (
                    "scheduler, confidential-attestation, retry, storage, and "
                    "final-replay overhead are excluded"
                ),
                (
                    "arithmetic target booleans do not admit a source, "
                    "executable, receipt, or theorem"
                ),
            ],
        }


def project_from_h100_calibration(
    calibration_result: dict[str, object],
    **projection_overrides: object,
) -> dict[str, object]:
    """Project conservatively from a replayed bounded calibration result.

    The proportional rate uses the reported-kernel median.  Repeated
    initialization and fixed process overhead use the maximum measured value,
    and both are charged once for every immutable checkpoint leaf.
    """

    try:
        domain = calibration_result["domain"]
        measured = calibration_result["measured_runs"]
        warmups = calibration_result["warmup_runs"]
        sample_even_count = domain["even_count"]
    except (KeyError, TypeError) as exc:
        raise GoldbachOptimizedProjectionError(
            "calibration result structure is malformed"
        ) from exc
    if (
        not isinstance(domain, dict)
        or not isinstance(measured, list)
        or not measured
        or not isinstance(warmups, list)
        or not isinstance(sample_even_count, int)
        or isinstance(sample_even_count, bool)
        or sample_even_count <= 0
    ):
        raise GoldbachOptimizedProjectionError(
            "calibration result geometry is malformed"
        )
    compute_ns: list[int] = []
    initialization: list[Decimal] = []
    fixed: list[Decimal] = []
    for index, raw in enumerate([*warmups, *measured]):
        if not isinstance(raw, dict):
            raise GoldbachOptimizedProjectionError(
                f"calibration run {index} is malformed"
            )
        parsed = raw.get("parsed")
        wall_ns = raw.get("wall_nanoseconds")
        reported_ns = raw.get("reported_computation_nanoseconds")
        if (
            not isinstance(parsed, dict)
            or isinstance(wall_ns, bool)
            or not isinstance(wall_ns, int)
            or isinstance(reported_ns, bool)
            or not isinstance(reported_ns, int)
            or reported_ns <= 0
            or wall_ns < reported_ns
        ):
            raise GoldbachOptimizedProjectionError(
                f"calibration run {index} timing is malformed"
            )
        try:
            initialization_seconds = (
                Decimal(str(parsed["initialization_milliseconds"]))
                / Decimal(1000)
            )
        except (KeyError, InvalidOperation, ValueError) as exc:
            raise GoldbachOptimizedProjectionError(
                f"calibration run {index} initialization is malformed"
            ) from exc
        if (
            not initialization_seconds.is_finite()
            or initialization_seconds < 0
        ):
            raise GoldbachOptimizedProjectionError(
                f"calibration run {index} initialization is negative"
            )
        compute_seconds = Decimal(reported_ns) / Decimal(1_000_000_000)
        wall_seconds = Decimal(wall_ns) / Decimal(1_000_000_000)
        fixed_seconds = wall_seconds - compute_seconds - initialization_seconds
        if index >= len(warmups):
            compute_ns.append(reported_ns)
        initialization.append(initialization_seconds)
        fixed.append(max(Decimal(0), fixed_seconds))
    ordered = sorted(compute_ns)
    median_ns = ordered[len(ordered) // 2]
    expected_median = calibration_result.get(
        "median_reported_computation_nanoseconds"
    )
    if expected_median != median_ns:
        raise GoldbachOptimizedProjectionError(
            "calibration result median is inconsistent"
        )
    arguments: dict[str, object] = {
        "sample_even_count": sample_even_count,
        "sample_seconds": Decimal(median_ns) / Decimal(1_000_000_000),
        "initialization_seconds_per_leaf": max(initialization),
        "fixed_seconds_per_leaf": max(fixed),
    }
    arguments.update(projection_overrides)
    result = project_optimized_prototype(**arguments)
    result["schema"] = (
        "sparkinterval.goldbach-optimized-h100-calibration-projection.v1"
    )
    result["classification"] = (
        "bounded-h100-calibration-envelope-not-production-evidence"
    )
    result["bounded_target_sku_sample_present"] = True
    result["target_h100_source_scale_measured"] = False
    result["assumptions"] = [
        item
        for item in result["assumptions"]
        if item != "no H100 speedup is assumed"
    ] + [
        (
            "the bounded H100 median rate remains stable over every "
            "source checkpoint leaf"
        ),
        (
            "the maximum observed initialization and residual process "
            "overheads are each charged once per leaf"
        ),
    ]
    return result


__all__ = [
    "DEFAULT_BUDGET_USD",
    "DEFAULT_CLUSTER_GPUS",
    "DEFAULT_DEADLINE_HOURS",
    "DEFAULT_ON_DEMAND_CLUSTER_HOUR_USD",
    "DEFAULT_SPOT_CLUSTER_HOUR_USD",
    "GoldbachOptimizedProjectionError",
    "project_from_h100_calibration",
    "project_optimized_prototype",
]
