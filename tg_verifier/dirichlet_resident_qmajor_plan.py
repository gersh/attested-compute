# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact planning model for resident q-major Dirichlet lattice phases.

The source Hurwitz lattice has 127,988 one-MiB rows.  A q-major execution
order preserves the all-character transform's component-plan locality, but a
naive q-major wire rereads the same lattice row for every active modulus.
This module models a different boundary: load one contiguous t shard into an
H100, run every active q against that resident shard in canonical q-major
order, and then retire the shard.

The eight work-balanced source lanes are retained.  Their last lane is too
large for one 80-GiB H100, so it is split into three batch-aligned pieces at
ordinates 49,088 and 88,512.  The resulting phases execute sequentially in
slot 7.  Thus ten resident phases cover the lattice once while eight slots
retain the original work balance.  The maximum payload is deliberately
smaller than the largest nominally fitting two-way split, leaving room for
the transform workspace, CUDA context, downstream state, and fragmentation.

This is an exact resource and finite-coverage projection.  It is not yet a
wire, executable, source-scale run, completed-L/zero certificate, attested
execution, or discharge of Platt's Theorem 7.1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, NoReturn, Sequence

from tg_verifier.dirichlet_allchars_q_scheduler import (
    ScheduleRecord,
    source_schedule_records,
)
from tg_verifier.dirichlet_allchars_stage import canonical_component_orders


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-dirichlet-resident-qmajor-ten-phase-plan-v2"
SCHEMA = "sparkinterval.tg.dirichlet_resident_qmajor_plan.v1"

BATCH_COUNT = 64
ROW_PAYLOAD_BYTES = 1_048_576
ROW_HEADER_BYTES = 64
SOURCE_T_INDEX_STOP = 127_988
GPU_SLOT_COUNT = 8
MAXIMUM_RESIDENT_ROWS = 39_488


@dataclass(frozen=True)
class ResidentPhase:
    phase_index: int
    gpu_slot: int
    first_t_index: int
    t_index_stop_exclusive: int

    @property
    def resident_row_count(self) -> int:
        return self.t_index_stop_exclusive - self.first_t_index


@dataclass(frozen=True)
class _ModulusWork:
    """One factored q and its exact affine batched-transform cost."""

    record: ScheduleRecord
    group_order: int
    butterfly_setup_per_target: int
    butterfly_per_row: int


PINNED_PHASES = (
    ResidentPhase(0, 0, 0, 768),
    ResidentPhase(1, 1, 768, 1_600),
    ResidentPhase(2, 2, 1_600, 2_368),
    ResidentPhase(3, 3, 2_368, 3_200),
    ResidentPhase(4, 4, 3_200, 4_032),
    ResidentPhase(5, 5, 4_032, 5_568),
    ResidentPhase(6, 6, 5_568, 9_600),
    ResidentPhase(7, 7, 9_600, 49_088),
    ResidentPhase(8, 7, 49_088, 88_512),
    ResidentPhase(9, 7, 88_512, SOURCE_T_INDEX_STOP),
)

PINNED_PHASE_ACTIVE_Q_COUNTS = (
    292_500,
    292_500,
    292_500,
    292_500,
    292_500,
    255_543,
    187_230,
    93_257,
    12_056,
    3_346,
)
PINNED_PHASE_TARGET_COUNTS = (
    3_510_000,
    3_802_500,
    3_510_000,
    3_802_500,
    3_736_394,
    5_380_665,
    8_210_666,
    19_894_223,
    4_226_917,
    907_235,
)
PINNED_PHASE_ROW_COUNTS = (
    224_640_000,
    243_360_000,
    224_640_000,
    243_360_000,
    238_010_582,
    342_217_786,
    522_510_272,
    1_270_668_873,
    270_247_283,
    57_958_371,
)
PINNED_PHASE_VALUE_COUNTS = (
    31_106_430_951_936,
    33_698_633_531_264,
    31_106_430_951_936,
    33_698_633_531_264,
    32_074_488_194_502,
    34_172_695_117_846,
    33_836_944_916_080,
    33_790_142_451_440,
    2_767_101_939_488,
    446_236_179_092,
)
PINNED_PHASE_BATCHED_BUTTERFLIES = (
    1_844_926_924_725_312,
    1_998_670_835_119_088,
    1_844_926_924_725_312,
    1_998_670_835_119_088,
    1_899_471_145_527_012,
    1_967_010_083_383_448,
    1_886_569_668_387_388,
    1_745_552_940_214_384,
    129_013_705_688_052,
    20_152_819_356_972,
)

PINNED_SOURCE_TARGET_COUNT = 56_981_100
PINNED_SOURCE_ROW_COUNT = 3_637_613_167
PINNED_SOURCE_VALUE_COUNT = 266_697_737_764_848
PINNED_SOURCE_BATCHED_BUTTERFLIES = 15_334_965_882_246_056


class DirichletResidentQMajorPlanError(RuntimeError):
    """A resident q-major resource or coverage invariant failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletResidentQMajorPlanError(message)


def validate_phases(
    phases: Sequence[ResidentPhase],
    *,
    required_t_stop: int = SOURCE_T_INDEX_STOP,
    maximum_resident_rows: int = MAXIMUM_RESIDENT_ROWS,
) -> tuple[ResidentPhase, ...]:
    """Require a gap-free, batch-aligned, memory-bounded partition."""

    result = tuple(phases)
    if (
        isinstance(required_t_stop, bool)
        or not isinstance(required_t_stop, int)
        or required_t_stop <= 0
        or isinstance(maximum_resident_rows, bool)
        or not isinstance(maximum_resident_rows, int)
        or maximum_resident_rows <= 0
    ):
        _fail("resident q-major phase bounds are invalid")
    expected_t = 0
    for expected_index, phase in enumerate(result):
        if not isinstance(phase, ResidentPhase):
            _fail("resident q-major phase has the wrong type")
        if (
            phase.phase_index != expected_index
            or not 0 <= phase.gpu_slot < GPU_SLOT_COUNT
            or phase.first_t_index != expected_t
            or phase.t_index_stop_exclusive <= phase.first_t_index
            or phase.resident_row_count > maximum_resident_rows
            or phase.first_t_index % BATCH_COUNT != 0
        ):
            _fail(
                "resident phases are skipped, reordered, misaligned, "
                "or exceed memory"
            )
        if (
            expected_index + 1 < len(result)
            and phase.t_index_stop_exclusive % BATCH_COUNT != 0
        ):
            _fail("resident phase boundary splits a canonical batch")
        expected_t = phase.t_index_stop_exclusive
    if expected_t != required_t_stop:
        _fail("resident phases do not cover the exact source t range")
    if tuple(phase.gpu_slot for phase in result) != (
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        7,
        7,
    ):
        _fail("resident phase-to-GPU assignment differs")
    return result


def _precompute_modulus_work(
    records: Sequence[ScheduleRecord],
) -> tuple[_ModulusWork, ...]:
    """Factor every q once and derive its affine batch-cost coefficients."""

    result: list[_ModulusWork] = []
    for record in records:
        orders = canonical_component_orders(record.q)
        order_product = math.prod(orders)
        setup = 0
        per_row = 0
        for component_order in orders:
            convolution = 1 << (2 * component_order - 2).bit_length()
            transform_butterflies = (
                (convolution // 2)
                * (convolution.bit_length() - 1)
            )
            setup += transform_butterflies
            per_row += (
                2
                * (order_product // component_order)
                * transform_butterflies
            )
        result.append(
            _ModulusWork(
                record=record,
                group_order=order_product,
                butterfly_setup_per_target=setup,
                butterfly_per_row=per_row,
            )
        )
    return tuple(result)


def _phase_accounting(
    modulus_work: Sequence[_ModulusWork],
    phase: ResidentPhase,
) -> dict[str, int]:
    active_q_count = 0
    target_count = 0
    row_count = 0
    value_count = 0
    batched_butterflies = 0
    for work in modulus_work:
        active_rows = max(
            0,
            min(work.record.t_index_count, phase.t_index_stop_exclusive)
            - phase.first_t_index,
        )
        if active_rows == 0:
            continue
        active_q_count += 1
        full_batches, remainder = divmod(active_rows, BATCH_COUNT)
        modulus_target_count = full_batches + int(remainder != 0)
        target_count += modulus_target_count
        row_count += active_rows
        value_count += active_rows * work.group_order
        batched_butterflies += (
            modulus_target_count * work.butterfly_setup_per_target
            + active_rows * work.butterfly_per_row
        )
    return {
        "active_q_count": active_q_count,
        "target_count": target_count,
        "row_reference_count": row_count,
        "group_value_count": value_count,
        "batched_radix2_butterflies": batched_butterflies,
    }


@lru_cache(maxsize=1)
def source_projection() -> dict[str, Any]:
    """Recompute and pin the exact ten-phase source accounting."""

    phases = validate_phases(PINNED_PHASES)
    records = source_schedule_records()
    modulus_work = _precompute_modulus_work(records)
    accounting = tuple(
        _phase_accounting(modulus_work, phase) for phase in phases
    )
    observed_columns = (
        tuple(item["active_q_count"] for item in accounting),
        tuple(item["target_count"] for item in accounting),
        tuple(item["row_reference_count"] for item in accounting),
        tuple(item["group_value_count"] for item in accounting),
        tuple(item["batched_radix2_butterflies"] for item in accounting),
    )
    expected_columns = (
        PINNED_PHASE_ACTIVE_Q_COUNTS,
        PINNED_PHASE_TARGET_COUNTS,
        PINNED_PHASE_ROW_COUNTS,
        PINNED_PHASE_VALUE_COUNTS,
        PINNED_PHASE_BATCHED_BUTTERFLIES,
    )
    if observed_columns != expected_columns:
        _fail("resident q-major source accounting differs from its pins")
    totals = {
        "target_count": sum(item["target_count"] for item in accounting),
        "row_reference_count": sum(
            item["row_reference_count"] for item in accounting
        ),
        "group_value_count": sum(
            item["group_value_count"] for item in accounting
        ),
        "batched_radix2_butterflies": sum(
            item["batched_radix2_butterflies"] for item in accounting
        ),
    }
    if totals != {
        "target_count": PINNED_SOURCE_TARGET_COUNT,
        "row_reference_count": PINNED_SOURCE_ROW_COUNT,
        "group_value_count": PINNED_SOURCE_VALUE_COUNT,
        "batched_radix2_butterflies": (
            PINNED_SOURCE_BATCHED_BUTTERFLIES
        ),
    }:
        _fail("resident q-major totals differ from the source contract")
    slot_butterflies = [0] * GPU_SLOT_COUNT
    for phase, item in zip(phases, accounting, strict=True):
        slot_butterflies[phase.gpu_slot] += item[
            "batched_radix2_butterflies"
        ]
    phase_reports = []
    for phase, item in zip(phases, accounting, strict=True):
        phase_reports.append(
            {
                "phase_index": phase.phase_index,
                "gpu_slot": phase.gpu_slot,
                "first_t_index": phase.first_t_index,
                "t_index_stop_exclusive": phase.t_index_stop_exclusive,
                "resident_row_count": phase.resident_row_count,
                "resident_lattice_payload_bytes": (
                    phase.resident_row_count * ROW_PAYLOAD_BYTES
                ),
                **item,
            }
        )
    return {
        "schema": SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "exact_resident_resource_plan_not_implemented_execution"
        ),
        "phase_count": len(phases),
        "gpu_slot_count": GPU_SLOT_COUNT,
        "phases": phase_reports,
        "totals": totals,
        "slot_batched_radix2_butterflies": slot_butterflies,
        "maximum_slot_batched_radix2_butterflies": max(slot_butterflies),
        "minimum_slot_batched_radix2_butterflies": min(slot_butterflies),
        "unique_lattice_row_count": SOURCE_T_INDEX_STOP,
        "unique_lattice_payload_bytes": (
            SOURCE_T_INDEX_STOP * ROW_PAYLOAD_BYTES
        ),
        "unique_lattice_bytes_with_row_headers": (
            SOURCE_T_INDEX_STOP
            * (ROW_PAYLOAD_BYTES + ROW_HEADER_BYTES)
        ),
        "maximum_resident_row_count": max(
            phase.resident_row_count for phase in phases
        ),
        "maximum_resident_lattice_payload_bytes": (
            max(phase.resident_row_count for phase in phases)
            * ROW_PAYLOAD_BYTES
        ),
        "naive_qmajor_row_payload_bytes": (
            PINNED_SOURCE_ROW_COUNT * ROW_PAYLOAD_BYTES
        ),
        "row_payload_reduction_factor": (
            PINNED_SOURCE_ROW_COUNT / SOURCE_T_INDEX_STOP
        ),
        "resident_shard_wire_implemented": False,
        "resident_cuda_executor_implemented": False,
        "persistent_downstream_transform_integrated": False,
        "source_scale_run_completed": False,
        "target_h100_measured": False,
        "trusted_execution_attested": False,
        "completed_l_zero_state_validated": False,
        "external_atom_discharged": False,
    }


def capability() -> dict[str, Any]:
    projection = source_projection()
    return {
        "algorithm_id": ALGORITHM_ID,
        "exact_source_partition_planned": True,
        "phase_count": projection["phase_count"],
        "gpu_slot_count": projection["gpu_slot_count"],
        "maximum_resident_lattice_payload_bytes": projection[
            "maximum_resident_lattice_payload_bytes"
        ],
        "resident_shard_wire_implemented": True,
        "resident_cuda_executor_implemented": True,
        "bounded_cuda_kat_completed": True,
        "persistent_downstream_transform_integrated": False,
        "source_phase_execution_completed": False,
        "source_h100_fit_claimed": False,
        "source_scale_run_completed": False,
        "target_h100_measured": False,
        "trusted_execution_attested": False,
        "completed_l_zero_state_validated": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "BATCH_COUNT",
    "DirichletResidentQMajorPlanError",
    "MAXIMUM_RESIDENT_ROWS",
    "PINNED_PHASES",
    "ResidentPhase",
    "SOURCE_T_INDEX_STOP",
    "capability",
    "source_projection",
    "validate_phases",
]
