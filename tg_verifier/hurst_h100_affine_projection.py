# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Auditable GB10-derived sizing for the exact eight-worker Hurst route.

The retained measurement is complete device work for one production-shaped
100-million-row shard: sieve, packed finalization, and exact affine scan.  No
number returned here is an H100 measurement.  The optional H100 factor is an
explicit sensitivity parameter and cannot satisfy a target-SKU calibration
or production-release gate.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .hurst_h100_affine_cluster import (
    ALGORITHM as AFFINE_CLUSTER_ALGORITHM,
    PRODUCTION_WORKER_COUNT,
)
from .hurst_hybrid_source import H100_LOWER, SOURCE_UPPER_EXCLUSIVE


SCHEMA = "sparkinterval.tg.hurst-h100-affine-sizing.v1"
MEASURED_DEVICE = "NVIDIA GB10"
MEASURED_ROWS = 100_000_000
MEASURED_COMPLETE_DEVICE_WORK_MILLISECONDS = Decimal("191.737")
DEFAULT_GB10_TO_H100_SENSITIVITY = Decimal("12.3")
REQUIRED_WORKER_COUNT = 8


class HurstH100AffineProjectionError(ValueError):
    """A Hurst projection input or exact production geometry was malformed."""


def project_hurst_h100_affine(
    *,
    gb10_to_h100_sensitivity: Decimal = DEFAULT_GB10_TO_H100_SENSITIVITY,
) -> dict[str, Any]:
    """Project the exact eight-way terminal range from the retained GB10 rate.

    The function deliberately emits both the equal-GB10-throughput baseline
    and the requested H100 sensitivity.  It always leaves target measurement
    and production readiness false.
    """

    factor = gb10_to_h100_sensitivity
    if (
        not isinstance(factor, Decimal)
        or not factor.is_finite()
        or factor <= 0
    ):
        raise HurstH100AffineProjectionError(
            "GB10-to-H100 sensitivity must be a positive finite Decimal"
        )
    if PRODUCTION_WORKER_COUNT != REQUIRED_WORKER_COUNT:
        raise HurstH100AffineProjectionError(
            "production Hurst composition is not exactly eight workers"
        )
    source_rows = SOURCE_UPPER_EXCLUSIVE - H100_LOWER
    if source_rows <= 0 or source_rows % PRODUCTION_WORKER_COUNT != 0:
        raise HurstH100AffineProjectionError(
            "production Hurst range does not partition equally over eight workers"
        )

    measured_seconds = (
        MEASURED_COMPLETE_DEVICE_WORK_MILLISECONDS / Decimal(1000)
    )
    measured_rows_per_second = Decimal(MEASURED_ROWS) / measured_seconds
    rows_per_worker = source_rows // PRODUCTION_WORKER_COUNT
    equal_gb10_wall_hours = (
        Decimal(rows_per_worker) / measured_rows_per_second / Decimal(3600)
    )
    sensitivity_wall_hours = equal_gb10_wall_hours / factor
    sensitivity_node_hours = (
        sensitivity_wall_hours * Decimal(PRODUCTION_WORKER_COUNT)
    )

    return {
        "schema": SCHEMA,
        "classification": (
            "gb10_complete_device_work_linear_extrapolation_"
            "not_target_h100_measurement_budget_evidence_or_execution"
        ),
        "measurement": {
            "device": MEASURED_DEVICE,
            "rows": MEASURED_ROWS,
            "complete_device_work_milliseconds": str(
                MEASURED_COMPLETE_DEVICE_WORK_MILLISECONDS
            ),
            "complete_device_work_seconds": str(measured_seconds),
            "rows_per_second": str(measured_rows_per_second),
            "included_stages": [
                "split-square segmented sieve",
                "packed support finalization",
                "exact affine prefix scan and reduction",
            ],
            "excluded_stages": [
                "target-H100 calibration",
                "CPU summary and verification prefix through 10^12 and handoff",
                "startup and roster handling",
                "receipt serialization and replay",
                "checkpointing and retries",
                "confidential-compute attestation",
            ],
        },
        "exact_affine_composition": {
            "algorithm": AFFINE_CLUSTER_ALGORITHM,
            "worker_count": PRODUCTION_WORKER_COUNT,
            "source_lower": H100_LOWER,
            "source_upper_exclusive": SOURCE_UPPER_EXCLUSIVE,
            "source_rows": source_rows,
            "rows_per_worker": rows_per_worker,
            "equal_partition": True,
            "topology": "eight_independent_one_h100_workers_then_exact_offline_scan",
            "lean_theorem": (
                "SparkInterval.TernaryGoldbach."
                "HurstAffineClusterComposition."
                "eightWorkerComposition_eq_single"
            ),
        },
        "equal_gb10_throughput_baseline": {
            "eight_worker_wall_hours": str(equal_gb10_wall_hours),
            "eight_worker_wall_days": str(
                equal_gb10_wall_hours / Decimal(24)
            ),
        },
        "h100_sensitivity": {
            "throughput_factor_vs_measured_gb10": str(factor),
            "per_worker_rows_per_second": str(
                measured_rows_per_second * factor
            ),
            "eight_worker_wall_hours": str(sensitivity_wall_hours),
            "eight_worker_wall_days": str(
                sensitivity_wall_hours / Decimal(24)
            ),
            "eight_worker_node_hours": str(sensitivity_node_hours),
            "target_h100_measured": False,
            "production_budget_gate_passed": False,
        },
        "production_gate": {
            "projection_scope": "terminal_h100_stage_only",
            "complete_hybrid_campaign_eta_available": False,
            "target_h100_measurement_required": True,
            "target_h100_measurement_available": False,
            "source_scale_execution_complete": False,
            "production_receipts_present": False,
            "production_ready": False,
            "reason": (
                "the 12.3x factor is an unmeasured planning sensitivity; "
                "arithmetic time or cost below a release limit cannot promote it"
            ),
        },
    }


__all__ = [
    "AFFINE_CLUSTER_ALGORITHM",
    "DEFAULT_GB10_TO_H100_SENSITIVITY",
    "HurstH100AffineProjectionError",
    "MEASURED_COMPLETE_DEVICE_WORK_MILLISECONDS",
    "MEASURED_DEVICE",
    "MEASURED_ROWS",
    "REQUIRED_WORKER_COUNT",
    "SCHEMA",
    "project_hurst_h100_affine",
]
