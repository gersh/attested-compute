# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Constant-memory q-major target cursor for the Dirichlet source campaign.

``TGDQORD1`` fixes the exact primitive-modulus execution order and the exact
number of ordinates for each modulus.  The source Hurwitz lattice is stored
once in contiguous t-major lane archives.  This module joins those two
objects formulaically: it emits bounded targets

    (execution-q-index, q, lane, first-t, stop-t)

without serializing one JSON control object per target.

The cursor is deliberately an execution-plan component.  It proves/checks
exact discrete q/t coverage and supplies a streaming commitment, but it does
not read a lattice archive, execute interval arithmetic, validate zeros,
attest a process, or discharge Platt's Theorem 7.1.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct
from typing import Any, Mapping, NoReturn, Sequence

from tg_verifier.dirichlet_allchars_q_scheduler import (
    FULL_SOURCE_CLASSIFICATION,
    ParsedScheduleManifest,
)
from tg_verifier.dirichlet_lattice_cache import (
    ROW_PAYLOAD_BYTES,
    canonical_json_bytes,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-dirichlet-formulaic-qmajor-target-cursor-v1"
ACCOUNTING_SCHEMA = (
    "sparkinterval.tg.dirichlet_formulaic_qmajor.accounting.v1"
)
SESSION_SCHEMA = "sparkinterval.tg.dirichlet_formulaic_qmajor.session.v1"

MAXIMUM_BATCH_COUNT = 64
TARGET_DOMAIN = b"TG_DIRICHLET_FORMULAIC_QMAJOR_TARGET_V1"
CHAIN_DOMAIN = b"TG_DIRICHLET_FORMULAIC_QMAJOR_CHAIN_V1"

# execution q index, q, lane, first t, exclusive t stop, batch count.
TARGET_RECORD = struct.Struct("<QIIIII")
assert TARGET_RECORD.size == 28

# Exact t-major lane partition in the source contract.  Every internal
# boundary is divisible by 64, so source q groups retain the minimal
# ceil(row_count / 64) target count while switching archive files.
PINNED_SOURCE_LANES = (
    (0, 0, 896),
    (1, 896, 1_664),
    (2, 1_664, 2_560),
    (3, 2_560, 3_328),
    (4, 3_328, 4_352),
    (5, 4_352, 5_888),
    (6, 5_888, 10_240),
    (7, 10_240, 127_988),
)
PINNED_SOURCE_TARGETS = 56_981_100
PINNED_SOURCE_ROWS = 3_637_613_167
PINNED_SOURCE_LANE_TARGETS = (
    4_095_000,
    3_510_000,
    4_095_000,
    3_510_000,
    4_387_802,
    5_051_668,
    8_203_438,
    24_128_192,
)
PINNED_SOURCE_LANE_ROWS = (
    262_080_000,
    224_640_000,
    262_080_000,
    224_640_000,
    279_192_643,
    321_229_090,
    522_267_482,
    1_541_483_952,
)


class DirichletFormulaicQMajorError(RuntimeError):
    """A formulaic target or exact-coverage invariant failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletFormulaicQMajorError(message)


def _integer(
    value: object,
    label: str,
    *,
    minimum: int = 0,
    maximum: int = (1 << 63) - 1,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        _fail(f"{label} is outside [{minimum},{maximum}]")
    return value


@dataclass(frozen=True, order=True)
class LaneRange:
    lane_index: int
    first_t_index: int
    t_index_stop_exclusive: int

    @property
    def row_count(self) -> int:
        return self.t_index_stop_exclusive - self.first_t_index

    def report(self) -> dict[str, int]:
        return {
            "lane_index": self.lane_index,
            "first_t_index": self.first_t_index,
            "t_index_stop_exclusive": self.t_index_stop_exclusive,
            "row_count": self.row_count,
        }


@dataclass(frozen=True)
class FormulaicTarget:
    execution_q_index: int
    q: int
    lane_index: int
    first_t_index: int
    t_index_stop_exclusive: int

    @property
    def batch_count(self) -> int:
        return self.t_index_stop_exclusive - self.first_t_index

    def packed(self) -> bytes:
        return TARGET_RECORD.pack(
            self.execution_q_index,
            self.q,
            self.lane_index,
            self.first_t_index,
            self.t_index_stop_exclusive,
            self.batch_count,
        )

    def digest(self) -> str:
        digest = hashlib.sha256(TARGET_DOMAIN)
        digest.update(self.packed())
        return digest.hexdigest()

    def report(self) -> dict[str, Any]:
        return {
            "execution_q_index": self.execution_q_index,
            "q": self.q,
            "lane_index": self.lane_index,
            "first_t_index": self.first_t_index,
            "t_index_stop_exclusive": self.t_index_stop_exclusive,
            "batch_count": self.batch_count,
            "target_sha256": self.digest(),
        }


def source_lanes() -> tuple[LaneRange, ...]:
    return tuple(LaneRange(*lane) for lane in PINNED_SOURCE_LANES)


def validate_lanes(
    lanes: Sequence[LaneRange],
    *,
    required_t_stop: int,
    maximum_batch_count: int = MAXIMUM_BATCH_COUNT,
) -> tuple[LaneRange, ...]:
    """Require one gap-free partition whose boundaries preserve batching."""

    required_t_stop = _integer(required_t_stop, "required t stop", minimum=1)
    maximum_batch_count = _integer(
        maximum_batch_count,
        "maximum batch count",
        minimum=1,
        maximum=MAXIMUM_BATCH_COUNT,
    )
    result = tuple(lanes)
    if not result:
        _fail("formulaic cursor has no t-major lanes")
    expected_start = 0
    for expected_index, lane in enumerate(result):
        if not isinstance(lane, LaneRange):
            _fail("formulaic lane has the wrong type")
        lane_index = _integer(lane.lane_index, "lane index")
        first_t = _integer(lane.first_t_index, "lane first t")
        stop_t = _integer(
            lane.t_index_stop_exclusive, "lane t stop", minimum=1
        )
        if (
            lane_index != expected_index
            or first_t != expected_start
            or stop_t <= first_t
        ):
            _fail("formulaic lanes are skipped, reordered, overlapping, or empty")
        if (
            expected_index + 1 < len(result)
            and stop_t % maximum_batch_count
        ):
            _fail("internal lane boundary splits a canonical target batch")
        expected_start = stop_t
    if expected_start < required_t_stop:
        _fail("formulaic lanes do not cover the exact required t range")
    return result


def _slice_bounds(
    schedule: ParsedScheduleManifest,
    start_execution_q_index: int,
    stop_execution_q_index: int | None,
) -> tuple[int, int]:
    count = len(schedule.execution_records)
    start = _integer(
        start_execution_q_index,
        "start execution q index",
        maximum=count,
    )
    stop = (
        count
        if stop_execution_q_index is None
        else _integer(
            stop_execution_q_index,
            "stop execution q index",
            maximum=count,
        )
    )
    if start >= stop:
        _fail("formulaic q slice is empty or reversed")
    return start, stop


def plan_identity(
    schedule: ParsedScheduleManifest,
    lanes: Sequence[LaneRange],
    *,
    start_execution_q_index: int = 0,
    stop_execution_q_index: int | None = None,
    maximum_batch_count: int = MAXIMUM_BATCH_COUNT,
) -> dict[str, Any]:
    start, stop = _slice_bounds(
        schedule, start_execution_q_index, stop_execution_q_index
    )
    required_stop = max(
        record.t_index_count
        for record in schedule.execution_records[start:stop]
    )
    checked_lanes = validate_lanes(
        lanes,
        required_t_stop=required_stop,
        maximum_batch_count=maximum_batch_count,
    )
    body: dict[str, Any] = {
        "algorithm_id": ALGORITHM_ID,
        "schedule_manifest_sha256": schedule.manifest_sha256,
        "schedule_classification": schedule.classification,
        "schedule_execution_order_sha256": schedule.execution_order_sha256,
        "start_execution_q_index": start,
        "stop_execution_q_index": stop,
        "maximum_batch_count": maximum_batch_count,
        "lanes": [lane.report() for lane in checked_lanes],
    }
    body["plan_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return body


def formulaic_accounting(
    schedule: ParsedScheduleManifest,
    lanes: Sequence[LaneRange],
    *,
    start_execution_q_index: int = 0,
    stop_execution_q_index: int | None = None,
    maximum_batch_count: int = MAXIMUM_BATCH_COUNT,
) -> dict[str, Any]:
    """Compute exact target/row totals without expanding target records."""

    plan = plan_identity(
        schedule,
        lanes,
        start_execution_q_index=start_execution_q_index,
        stop_execution_q_index=stop_execution_q_index,
        maximum_batch_count=maximum_batch_count,
    )
    start = plan["start_execution_q_index"]
    stop = plan["stop_execution_q_index"]
    checked_lanes = tuple(
        LaneRange(
            lane["lane_index"],
            lane["first_t_index"],
            lane["t_index_stop_exclusive"],
        )
        for lane in plan["lanes"]
    )
    target_counts = [0] * len(checked_lanes)
    row_counts = [0] * len(checked_lanes)
    for record in schedule.execution_records[start:stop]:
        for lane in checked_lanes:
            active_rows = max(
                0,
                min(record.t_index_count, lane.t_index_stop_exclusive)
                - lane.first_t_index,
            )
            if active_rows:
                row_counts[lane.lane_index] += active_rows
                target_counts[lane.lane_index] += (
                    active_rows + maximum_batch_count - 1
                ) // maximum_batch_count
    target_count = sum(target_counts)
    row_count = sum(row_counts)
    source_pins_matched = False
    if (
        schedule.classification == FULL_SOURCE_CLASSIFICATION
        and start == 0
        and stop == len(schedule.execution_records)
        and tuple(checked_lanes) == source_lanes()
        and maximum_batch_count == MAXIMUM_BATCH_COUNT
    ):
        if (
            target_count != PINNED_SOURCE_TARGETS
            or row_count != PINNED_SOURCE_ROWS
            or tuple(target_counts) != PINNED_SOURCE_LANE_TARGETS
            or tuple(row_counts) != PINNED_SOURCE_LANE_ROWS
        ):
            _fail("formulaic full-source accounting differs from independent pins")
        source_pins_matched = True
    result: dict[str, Any] = {
        "schema": ACCOUNTING_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        **plan,
        "q_count": stop - start,
        "target_count": target_count,
        "row_reference_count": row_count,
        "per_lane_target_counts": target_counts,
        "per_lane_row_reference_counts": row_counts,
        "constant_memory_target_generation": True,
        "serialized_control_records_required": 0,
        "source_scale_pins_matched": source_pins_matched,
        "lattice_rows_read_or_validated": False,
        "cuda_executed": False,
        "completed_l_zero_state_validated": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }
    result["accounting_sha256"] = hashlib.sha256(
        canonical_json_bytes(result)
    ).hexdigest()
    return result


class FormulaicQMajorCursor:
    """Stateful fail-closed target generator with O(q-count + lane-count) state."""

    def __init__(
        self,
        schedule: ParsedScheduleManifest,
        lanes: Sequence[LaneRange],
        *,
        start_execution_q_index: int = 0,
        stop_execution_q_index: int | None = None,
        maximum_batch_count: int = MAXIMUM_BATCH_COUNT,
    ) -> None:
        self.schedule = schedule
        self.accounting = formulaic_accounting(
            schedule,
            lanes,
            start_execution_q_index=start_execution_q_index,
            stop_execution_q_index=stop_execution_q_index,
            maximum_batch_count=maximum_batch_count,
        )
        self.lanes = tuple(
            LaneRange(
                lane["lane_index"],
                lane["first_t_index"],
                lane["t_index_stop_exclusive"],
            )
            for lane in self.accounting["lanes"]
        )
        self.start_q_index = self.accounting["start_execution_q_index"]
        self.stop_q_index = self.accounting["stop_execution_q_index"]
        self.maximum_batch_count = maximum_batch_count
        self._q_index = self.start_q_index
        self._lane_index = 0
        self._next_t = 0
        self.target_count = 0
        self.row_reference_count = 0
        self.per_lane_target_counts = [0] * len(self.lanes)
        self.per_lane_row_counts = [0] * len(self.lanes)
        initial = hashlib.sha256(CHAIN_DOMAIN)
        initial.update(bytes.fromhex(self.accounting["plan_sha256"]))
        self.target_chain_sha256 = initial.hexdigest()
        self._finished = False

    def _advance_empty_lanes_or_q(self) -> None:
        while self._q_index < self.stop_q_index:
            row_stop = self.schedule.execution_records[
                self._q_index
            ].t_index_count
            while (
                self._lane_index < len(self.lanes)
                and self._next_t >= min(
                    row_stop,
                    self.lanes[self._lane_index].t_index_stop_exclusive,
                )
            ):
                self._lane_index += 1
                if self._lane_index < len(self.lanes):
                    self._next_t = self.lanes[
                        self._lane_index
                    ].first_t_index
            if self._next_t < row_stop:
                return
            self._q_index += 1
            self._lane_index = 0
            self._next_t = 0

    def expected_target(self) -> FormulaicTarget | None:
        if self._finished:
            _fail("formulaic cursor is already finalized")
        self._advance_empty_lanes_or_q()
        if self._q_index == self.stop_q_index:
            return None
        if not 0 <= self._lane_index < len(self.lanes):
            _fail("formulaic lane cursor escaped its exact partition")
        record = self.schedule.execution_records[self._q_index]
        lane = self.lanes[self._lane_index]
        stop = min(
            record.t_index_count,
            lane.t_index_stop_exclusive,
            self._next_t + self.maximum_batch_count,
        )
        if not self._next_t < stop:
            _fail("formulaic cursor generated an empty target")
        return FormulaicTarget(
            execution_q_index=self._q_index,
            q=record.q,
            lane_index=lane.lane_index,
            first_t_index=self._next_t,
            t_index_stop_exclusive=stop,
        )

    def accept(self, target: FormulaicTarget | Mapping[str, Any]) -> None:
        expected = self.expected_target()
        if expected is None:
            _fail("formulaic target supplied after exact coverage")
        if isinstance(target, Mapping):
            if set(target) != {
                "execution_q_index",
                "q",
                "lane_index",
                "first_t_index",
                "t_index_stop_exclusive",
                "batch_count",
                "target_sha256",
            }:
                _fail("formulaic target mapping fields differ")
            try:
                observed = FormulaicTarget(
                    execution_q_index=_integer(
                        target.get("execution_q_index"),
                        "target execution q index",
                    ),
                    q=_integer(target.get("q"), "target q"),
                    lane_index=_integer(
                        target.get("lane_index"), "target lane index"
                    ),
                    first_t_index=_integer(
                        target.get("first_t_index"), "target first t"
                    ),
                    t_index_stop_exclusive=_integer(
                        target.get("t_index_stop_exclusive"),
                        "target t stop",
                    ),
                )
            except AttributeError as error:  # defensive Mapping implementation
                raise DirichletFormulaicQMajorError(
                    "formulaic target mapping is malformed"
                ) from error
            if (
                target.get("batch_count") != observed.batch_count
                or target.get("target_sha256") != observed.digest()
            ):
                _fail("formulaic target mapping digest or batch count differs")
        elif isinstance(target, FormulaicTarget):
            observed = target
        else:
            _fail("formulaic target has the wrong type")
        if observed != expected:
            _fail("formulaic target was skipped, substituted, or reordered")
        digest = hashlib.sha256(CHAIN_DOMAIN)
        digest.update(bytes.fromhex(self.target_chain_sha256))
        digest.update(expected.packed())
        self.target_chain_sha256 = digest.hexdigest()
        self.target_count += 1
        self.row_reference_count += expected.batch_count
        self.per_lane_target_counts[expected.lane_index] += 1
        self.per_lane_row_counts[expected.lane_index] += expected.batch_count
        self._next_t = expected.t_index_stop_exclusive

    def finish(self) -> dict[str, Any]:
        if self._finished:
            _fail("formulaic cursor was already finalized")
        if self.expected_target() is not None:
            _fail("formulaic cursor is truncated")
        if (
            self.target_count != self.accounting["target_count"]
            or self.row_reference_count
            != self.accounting["row_reference_count"]
            or self.per_lane_target_counts
            != self.accounting["per_lane_target_counts"]
            or self.per_lane_row_counts
            != self.accounting["per_lane_row_reference_counts"]
        ):
            _fail("formulaic cursor totals differ from compressed accounting")
        body: dict[str, Any] = {
            "schema": SESSION_SCHEMA,
            "schema_version": 1,
            "author": AUTHOR,
            "atom_id": ATOM_ID,
            "algorithm_id": ALGORITHM_ID,
            "plan_sha256": self.accounting["plan_sha256"],
            "accounting_sha256": self.accounting["accounting_sha256"],
            "start_execution_q_index": self.start_q_index,
            "stop_execution_q_index": self.stop_q_index,
            "target_count": self.target_count,
            "row_reference_count": self.row_reference_count,
            "per_lane_target_counts": self.per_lane_target_counts,
            "per_lane_row_reference_counts": self.per_lane_row_counts,
            "target_chain_sha256": self.target_chain_sha256,
            "decisions": {
                "exact_formulaic_q_t_coverage_consumed": True,
                "no_serialized_per_target_control_roster": True,
                "lattice_rows_read_or_validated": False,
                "cuda_executed": False,
                "completed_l_zero_state_validated": False,
                "trusted_execution_attested": False,
                "external_atom_discharged": False,
            },
        }
        result = dict(body)
        result["session_sha256"] = hashlib.sha256(
            canonical_json_bytes(body)
        ).hexdigest()
        self._finished = True
        return result


def capability() -> dict[str, Any]:
    source_raw_lattice_bytes = PINNED_SOURCE_ROWS * ROW_PAYLOAD_BYTES
    return {
        "schema": "sparkinterval.tg.dirichlet_formulaic_qmajor.capability.v1",
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "constant_memory_target_cursor_implemented": True,
        "compressed_exact_accounting_implemented": True,
        "source_target_count_pinned": PINNED_SOURCE_TARGETS,
        "source_row_reference_count_pinned": PINNED_SOURCE_ROWS,
        "serialized_source_control_records_required": 0,
        "cuda_executor_consumes_cursor_directly": True,
        "descriptor_free_bounded_binary_service_implemented": True,
        "bounded_real_cuda_kat_implemented": True,
        "cuda_executor_accepts_full_source_schedule": False,
        "source_lattice_spools_populated": False,
        "source_formulaic_lattice_rows_reread_and_uploaded_if_executed": (
            PINNED_SOURCE_ROWS
        ),
        "source_formulaic_raw_lattice_transfer_bytes_if_executed": (
            source_raw_lattice_bytes
        ),
        "preserves_tmajor_one_upload_per_physical_row": False,
        "economical_production_storage_solution": False,
        "candidate_resident_t_shard_cuts": [
            0,
            768,
            1_600,
            2_368,
            3_200,
            4_032,
            5_568,
            9_600,
            49_088,
            88_512,
            127_988,
        ],
        "candidate_resident_t_shard_phase_count": 10,
        "candidate_resident_t_shard_maximum_rows": 39_488,
        "candidate_resident_t_shard_report_sha256": (
            "eae086771356cc3e2cc26780012686f"
            "dbc3a8097aa76a3417056fe74f5a32eb6"
        ),
        "candidate_resident_t_shard_executor_implemented": False,
        "production_run_completed": False,
        "source_scale_run_completed": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ACCOUNTING_SCHEMA",
    "ALGORITHM_ID",
    "DirichletFormulaicQMajorError",
    "FormulaicQMajorCursor",
    "FormulaicTarget",
    "LaneRange",
    "MAXIMUM_BATCH_COUNT",
    "PINNED_SOURCE_LANE_ROWS",
    "PINNED_SOURCE_LANE_TARGETS",
    "PINNED_SOURCE_ROWS",
    "PINNED_SOURCE_TARGETS",
    "SESSION_SCHEMA",
    "capability",
    "formulaic_accounting",
    "plan_identity",
    "source_lanes",
    "validate_lanes",
]
