# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Source-shaped, bounded-lane resident q-major stream candidate.

The ten-phase geometry is exact, but bounded KAT projections may load a
contiguous subrange of one phase.  Rows and sidecars are separate immutable
artifacts.  Both writers and both independent replayers use bounded working
memory: rows are handled one at a time and sidecars one target at a time.

The matching CUDA worker preallocates one device lattice buffer, uploads each
authenticated row directly through a one-row host staging buffer, and then
streams q-major target sidecars and TGDAFFI1 outputs.  This module does not
claim a source run, H100 fit, production completion, attestation, completed-L
zero validation, zero completeness, or an external-atom discharge.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import tempfile
from typing import Any, BinaryIO, Callable, Iterator, NoReturn, Sequence

from tg_verifier.dirichlet_allchars_q_scheduler import (
    BOUNDED_CLASSIFICATION,
    FULL_SOURCE_CLASSIFICATION,
    ParsedScheduleManifest,
)
from tg_verifier.dirichlet_allchars_stage import (
    COMPLEX_INTERVAL,
    FORMAT_VERSION as TGDAFFI_FORMAT_VERSION,
    INPUT_HEADER as TGDAFFI_HEADER,
    INPUT_MAGIC as TGDAFFI_MAGIC,
    canonical_component_orders,
)
from tg_verifier.dirichlet_lattice_cache import (
    ROW_PAYLOAD_BYTES,
    canonical_json_bytes,
    validate_lattice_row,
)
from tg_verifier.dirichlet_lattice_stage import (
    SOURCE_SAMPLE_DENOMINATOR,
    SOURCE_SAMPLE_NUMERATOR,
)
from tg_verifier.dirichlet_largeq_batch import (
    FRAME_FACTOR,
    RESIDUE_DESCRIPTOR,
)
from tg_verifier.dirichlet_recovery_seeds import SEED_RECORD
from tg_verifier.dirichlet_tmajor_cuda_block import (
    ROW_HEADER,
    ROW_MAGIC,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-dirichlet-resident-qmajor-stream-input-v1"
CUDA_ALGORITHM_ID = (
    "platt-dirichlet-resident-qmajor-stream-seeded-cuda-v1"
)
ROW_SCHEMA = (
    "sparkinterval.tg.dirichlet_resident_qmajor_stream.rows.v1"
)
SIDECAR_SCHEMA = (
    "sparkinterval.tg.dirichlet_resident_qmajor_stream.sidecars.v1"
)
SUMMARY_SCHEMA = (
    "sparkinterval.tg.dirichlet_resident_qmajor_stream_cuda.summary.v1"
)
COMPARISON_SCHEMA = (
    "sparkinterval.tg.dirichlet_resident_qmajor_stream.comparison.v1"
)

FORMAT_VERSION = 1
SCHEDULE_CLASSIFICATION_BOUNDED = 0
SCHEDULE_CLASSIFICATION_FULL_SOURCE = 1
BOUNDED_PROJECTION_COVERAGE = 0
EXACT_CANDIDATE_PHASE_COVERAGE = 1
PHASE_CUTS = (
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
)
CANDIDATE_REPORT_SHA256 = (
    "eae086771356cc3e2cc26780012686f"
    "dbc3a8097aa76a3417056fe74f5a32eb6"
)
MAXIMUM_ROWS = 39_488
MAXIMUM_Q_PER_LANE = 64
MAXIMUM_TARGETS_PER_LANE = 39_488
MAXIMUM_LANES = 8_192
MAXIMUM_BATCH_COUNT = 64
MAXIMUM_GROUP_ORDER = 400_000
MAXIMUM_TARGET_VALUES = MAXIMUM_BATCH_COUNT * MAXIMUM_GROUP_ORDER
MAXIMUM_PHASE_TARGETS = 56_981_100
MAXIMUM_PHASE_ROW_REFERENCES = 1_270_668_873
MAXIMUM_PHASE_VALUES = 34_172_695_117_846
MAXIMUM_OUTPUT_PHASE_TARGETS = 5_380_665
MAXIMUM_PROJECTED_PHASE_OUTPUT_BYTES = (
    MAXIMUM_OUTPUT_PHASE_TARGETS * TGDAFFI_HEADER.size
    + MAXIMUM_PHASE_VALUES * COMPLEX_INTERVAL.size
)
MAXIMUM_LANE_INPUT_BYTES = 128 * 1024 * 1024
MAXIMUM_SIDECAR_INPUT_BYTES = 64 * 1024 * 1024 * 1024
DEVICE_MEMORY_SAFETY_RESERVE_BYTES = 512 * 1024 * 1024
MAXIMUM_JSON_BYTES = 4 * 1024 * 1024
TMAJOR_ROW_FORMAT_VERSION = 2

ROW_HEADER_MAGIC = b"TGDQSRH1"
ROW_FOOTER_MAGIC = b"TGDQSRF1"
STREAM_HEADER_MAGIC = b"TGDQSSH1"
LANE_HEADER_MAGIC = b"TGDQSLH1"
TARGET_MAGIC = b"TGDQSTG1"
LANE_FOOTER_MAGIC = b"TGDQSLF1"
STREAM_FOOTER_MAGIC = b"TGDQSSF1"

PLAN_DOMAIN = b"TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_PLAN_V1"
LANE_PARTITION_DOMAIN = b"TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_LANES_V1"
TARGET_DOMAIN = b"TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_TARGET_V1"
TARGET_CHAIN_DOMAIN = (
    b"TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_TARGET_CHAIN_V1"
)
LANE_TARGET_CHAIN_DOMAIN = (
    b"TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_LANE_TARGET_CHAIN_V1"
)
LANE_PLAN_DOMAIN = b"TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_LANE_PLAN_V1"
LANE_CHAIN_DOMAIN = b"TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_LANE_CHAIN_V1"
ROW_CHAIN_DOMAIN = b"TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_ROW_CHAIN_V1"
SIDECAR_DOMAIN = b"TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_SIDECAR_V1"

ROW_ARTIFACT_HEADER = struct.Struct(
    "<8sIIIIIIQQQQQQQQQ" + "32s" * 8
)
ROW_ARTIFACT_FOOTER = struct.Struct("<8sIIQQQ32s32s32s")
STREAM_HEADER = struct.Struct(
    "<8sIIIIIIIIII" + "Q" * 12 + "32s" * 9
)
LANE_HEADER = struct.Struct("<8sIIII" + "Q" * 8 + "32s32s")
TARGET_HEADER = struct.Struct(
    "<8sIIQIIIIIIIIQQQQ32s32s"
)
LANE_FOOTER = struct.Struct(
    "<8sIIII" + "Q" * 6 + "32s32s32s32s"
)
STREAM_FOOTER = struct.Struct(
    "<8sII" + "Q" * 7 + "32s32s32s32s"
)

assert ROW_ARTIFACT_HEADER.size == 360
assert ROW_ARTIFACT_FOOTER.size == 136
assert STREAM_HEADER.size == 432
assert LANE_HEADER.size == 152
assert TARGET_HEADER.size == 152
assert LANE_FOOTER.size == 200
assert STREAM_FOOTER.size == 200
assert ROW_HEADER.size == 64
assert ROW_PAYLOAD_BYTES == 1_048_576
assert FRAME_FACTOR.size == 32
assert RESIDUE_DESCRIPTOR.size == 8
assert SEED_RECORD.size == 48
assert COMPLEX_INTERVAL.size == 32
assert TGDAFFI_HEADER.size == 72

MAXIMUM_ROW_ARTIFACT_BYTES = (
    ROW_ARTIFACT_HEADER.size
    + MAXIMUM_ROWS * (ROW_HEADER.size + ROW_PAYLOAD_BYTES)
    + ROW_ARTIFACT_FOOTER.size
)

HEX = frozenset("0123456789abcdef")
RowProvider = Callable[[int], bytes]
RowProviderFinalizer = Callable[[], None]
SidecarProvider = Callable[["StreamTarget"], tuple[bytes, bytes]]


class DirichletResidentQMajorStreamError(RuntimeError):
    """A source-shaped resident stream invariant failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletResidentQMajorStreamError(message)


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


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in HEX for character in value)
    ):
        _fail(f"{label} is not lowercase SHA-256")
    return value


def _schedule_classification_id(schedule: ParsedScheduleManifest) -> int:
    if schedule.classification == BOUNDED_CLASSIFICATION:
        return SCHEDULE_CLASSIFICATION_BOUNDED
    if schedule.classification == FULL_SOURCE_CLASSIFICATION:
        return SCHEDULE_CLASSIFICATION_FULL_SOURCE
    _fail("resident stream schedule classification differs")


def _open_regular(path: Path, *, label: str) -> BinaryIO:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as error:
        raise DirichletResidentQMajorStreamError(
            f"cannot safely open {label}"
        ) from error
    source = os.fdopen(descriptor, "rb")
    if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
        source.close()
        _fail(f"{label} is not a regular file")
    return source


def _identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _read_exact(source: BinaryIO, count: int, label: str) -> bytes:
    raw = source.read(count)
    if len(raw) != count:
        _fail(f"{label} is truncated")
    return raw


def _atomic_stream(
    path: Path, writer: Callable[[BinaryIO], dict[str, Any]]
) -> dict[str, Any]:
    if path.exists() or path.is_symlink():
        _fail(f"refusing to replace immutable output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w+b") as output:
            result = writer(output)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)
        temporary.unlink()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return result


def _emit(
    output: BinaryIO,
    raw: bytes,
    *,
    whole: Any,
    secondary: Any | None = None,
) -> None:
    if output.write(raw) != len(raw):
        _fail("cannot write resident q-major stream artifact")
    whole.update(raw)
    if secondary is not None:
        secondary.update(raw)


@dataclass(frozen=True)
class QLane:
    lane_index: int
    start_execution_q_index: int
    stop_execution_q_index: int

    @property
    def q_count(self) -> int:
        return self.stop_execution_q_index - self.start_execution_q_index


@dataclass(frozen=True)
class StreamTarget:
    execution_q_index: int
    q: int
    phase_index: int
    lane_index: int
    first_t_index: int
    t_index_stop_exclusive: int

    @property
    def batch_count(self) -> int:
        return self.t_index_stop_exclusive - self.first_t_index

    def packed(self) -> bytes:
        return struct.pack(
            "<QIIIIII",
            self.execution_q_index,
            self.q,
            self.phase_index,
            self.lane_index,
            self.first_t_index,
            self.t_index_stop_exclusive,
            self.batch_count,
        )

    def digest(self) -> str:
        digest = hashlib.sha256(TARGET_DOMAIN)
        digest.update(self.packed())
        return digest.hexdigest()


@dataclass(frozen=True)
class LaneAccounting:
    lane: QLane
    active_q_count: int
    target_count: int
    target_row_reference_count: int
    value_count: int
    sidecar_bytes: int
    lane_input_bytes: int
    maximum_group_order: int


@dataclass(frozen=True)
class StreamPlan:
    schedule_classification: int
    phase_index: int
    coverage_mode: int
    canonical_first_t_index: int
    canonical_t_index_stop_exclusive: int
    loaded_first_t_index: int
    loaded_t_index_stop_exclusive: int
    start_execution_q_index: int
    stop_execution_q_index: int
    lanes: tuple[QLane, ...]
    lane_accounting: tuple[LaneAccounting, ...]
    lane_partition_sha256: str
    phase_plan_sha256: str
    active_q_count: int
    target_count: int
    target_row_reference_count: int
    value_count: int
    sidecar_bytes: int
    sidecar_input_size_bytes: int
    maximum_group_order: int
    maximum_target_batch_count: int
    maximum_target_value_count: int

    @property
    def row_count(self) -> int:
        return (
            self.loaded_t_index_stop_exclusive
            - self.loaded_first_t_index
        )

    @property
    def row_input_size_bytes(self) -> int:
        return (
            ROW_ARTIFACT_HEADER.size
            + self.row_count * (ROW_HEADER.size + ROW_PAYLOAD_BYTES)
            + ROW_ARTIFACT_FOOTER.size
        )


@lru_cache(maxsize=4096)
def _group_order(q: int) -> int:
    return math.prod(canonical_component_orders(q))


def phase_bounds(phase_index: int) -> tuple[int, int]:
    index = _integer(
        phase_index, "phase index", maximum=len(PHASE_CUTS) - 2
    )
    return PHASE_CUTS[index], PHASE_CUTS[index + 1]


def canonical_q_lanes(
    start_execution_q_index: int,
    stop_execution_q_index: int,
    *,
    maximum_q_per_lane: int = MAXIMUM_Q_PER_LANE,
) -> tuple[QLane, ...]:
    start = _integer(
        start_execution_q_index,
        "start execution q index",
        maximum=(1 << 32) - 1,
    )
    stop = _integer(
        stop_execution_q_index,
        "stop execution q index",
        minimum=1,
        maximum=(1 << 32) - 1,
    )
    bound = _integer(
        maximum_q_per_lane,
        "maximum q per lane",
        minimum=1,
        maximum=MAXIMUM_Q_PER_LANE,
    )
    if start >= stop:
        _fail("resident stream q range is empty")
    lanes = tuple(
        QLane(
            lane_index=index,
            start_execution_q_index=first,
            stop_execution_q_index=min(first + bound, stop),
        )
        for index, first in enumerate(range(start, stop, bound))
    )
    if len(lanes) > MAXIMUM_LANES:
        _fail("resident stream lane count exceeds its bound")
    return lanes


def _validate_lanes(
    lanes: Sequence[QLane], *, start: int, stop: int
) -> tuple[QLane, ...]:
    result = tuple(lanes)
    if not 1 <= len(result) <= MAXIMUM_LANES:
        _fail("resident stream lane count is outside its bound")
    expected = start
    for index, lane in enumerate(result):
        if (
            not isinstance(lane, QLane)
            or lane.lane_index != index
            or lane.start_execution_q_index != expected
            or lane.stop_execution_q_index <= expected
            or lane.q_count > MAXIMUM_Q_PER_LANE
        ):
            _fail("resident stream lane partition is malformed")
        expected = lane.stop_execution_q_index
    if expected != stop:
        _fail("resident stream lanes do not cover the exact q range")
    return result


def lane_partition_digest(
    schedule: ParsedScheduleManifest,
    lanes: Sequence[QLane],
    *,
    start_execution_q_index: int,
    stop_execution_q_index: int,
) -> str:
    checked = _validate_lanes(
        lanes,
        start=start_execution_q_index,
        stop=stop_execution_q_index,
    )
    digest = hashlib.sha256(LANE_PARTITION_DOMAIN)
    digest.update(bytes.fromhex(schedule.manifest_sha256))
    digest.update(bytes.fromhex(schedule.execution_order_sha256))
    digest.update(
        struct.pack(
            "<QQII",
            start_execution_q_index,
            stop_execution_q_index,
            len(checked),
            MAXIMUM_Q_PER_LANE,
        )
    )
    for lane in checked:
        digest.update(
            struct.pack(
                "<IQQ",
                lane.lane_index,
                lane.start_execution_q_index,
                lane.stop_execution_q_index,
            )
        )
    return digest.hexdigest()


def phase_plan_digest(
    schedule: ParsedScheduleManifest,
    *,
    phase_index: int,
    coverage_mode: int,
    loaded_first_t_index: int,
    loaded_t_index_stop_exclusive: int,
    start_execution_q_index: int,
    stop_execution_q_index: int,
    lane_partition_sha256: str,
) -> str:
    classification = _schedule_classification_id(schedule)
    canonical_first, canonical_stop = phase_bounds(phase_index)
    first = _integer(
        loaded_first_t_index,
        "loaded first t index",
        maximum=(1 << 32) - 1,
    )
    stop_t = _integer(
        loaded_t_index_stop_exclusive,
        "loaded t stop",
        minimum=1,
        maximum=(1 << 32) - 1,
    )
    start_q = _integer(
        start_execution_q_index,
        "start execution q index",
        maximum=len(schedule.execution_records),
    )
    stop_q = _integer(
        stop_execution_q_index,
        "stop execution q index",
        minimum=1,
        maximum=len(schedule.execution_records),
    )
    mode = _integer(coverage_mode, "coverage mode", maximum=1)
    if (
        start_q >= stop_q
        or first < canonical_first
        or stop_t > canonical_stop
        or first >= stop_t
        or stop_t - first > MAXIMUM_ROWS
        or (
            mode == BOUNDED_PROJECTION_COVERAGE
            and classification != SCHEDULE_CLASSIFICATION_BOUNDED
        )
        or (
            mode == EXACT_CANDIDATE_PHASE_COVERAGE
            and (
                classification
                != SCHEDULE_CLASSIFICATION_FULL_SOURCE
                or (first, stop_t)
                != (canonical_first, canonical_stop)
            )
        )
    ):
        _fail("resident stream plan geometry is malformed")
    partition = _digest(
        lane_partition_sha256, "lane partition"
    )
    digest = hashlib.sha256(PLAN_DOMAIN)
    digest.update(bytes.fromhex(schedule.manifest_sha256))
    digest.update(bytes.fromhex(schedule.execution_order_sha256))
    digest.update(bytes.fromhex(partition))
    digest.update(bytes.fromhex(CANDIDATE_REPORT_SHA256))
    digest.update(
        struct.pack(
            "<IIIIIIIQQIIII",
            classification,
            mode,
            phase_index,
            canonical_first,
            canonical_stop,
            first,
            stop_t,
            start_q,
            stop_q,
            MAXIMUM_ROWS,
            MAXIMUM_Q_PER_LANE,
            MAXIMUM_TARGETS_PER_LANE,
            MAXIMUM_BATCH_COUNT,
        )
    )
    return digest.hexdigest()


def _iter_lane_targets(
    schedule: ParsedScheduleManifest,
    plan: StreamPlan,
    lane: QLane,
) -> Iterator[StreamTarget]:
    for execution_q_index in range(
        lane.start_execution_q_index,
        lane.stop_execution_q_index,
    ):
        record = schedule.execution_records[execution_q_index]
        active_stop = min(
            record.t_index_count,
            plan.loaded_t_index_stop_exclusive,
        )
        for first_t in range(
            plan.loaded_first_t_index,
            active_stop,
            MAXIMUM_BATCH_COUNT,
        ):
            yield StreamTarget(
                execution_q_index=execution_q_index,
                q=record.q,
                phase_index=plan.phase_index,
                lane_index=lane.lane_index,
                first_t_index=first_t,
                t_index_stop_exclusive=min(
                    first_t + MAXIMUM_BATCH_COUNT,
                    active_stop,
                ),
            )


def iter_stream_targets(
    schedule: ParsedScheduleManifest,
    plan: StreamPlan,
) -> Iterator[StreamTarget]:
    for lane in plan.lanes:
        yield from _iter_lane_targets(schedule, plan, lane)


def build_stream_plan(
    schedule: ParsedScheduleManifest,
    *,
    phase_index: int,
    coverage_mode: int,
    loaded_first_t_index: int | None = None,
    loaded_t_index_stop_exclusive: int | None = None,
    start_execution_q_index: int = 0,
    stop_execution_q_index: int | None = None,
    lanes: Sequence[QLane] | None = None,
) -> StreamPlan:
    canonical_first, canonical_stop = phase_bounds(phase_index)
    first = (
        canonical_first
        if loaded_first_t_index is None
        else loaded_first_t_index
    )
    stop_t = (
        canonical_stop
        if loaded_t_index_stop_exclusive is None
        else loaded_t_index_stop_exclusive
    )
    stop_q = (
        len(schedule.execution_records)
        if stop_execution_q_index is None
        else stop_execution_q_index
    )
    selected_lanes = (
        canonical_q_lanes(start_execution_q_index, stop_q)
        if lanes is None
        else _validate_lanes(
            lanes,
            start=start_execution_q_index,
            stop=stop_q,
        )
    )
    partition_sha256 = lane_partition_digest(
        schedule,
        selected_lanes,
        start_execution_q_index=start_execution_q_index,
        stop_execution_q_index=stop_q,
    )
    plan_sha256 = phase_plan_digest(
        schedule,
        phase_index=phase_index,
        coverage_mode=coverage_mode,
        loaded_first_t_index=first,
        loaded_t_index_stop_exclusive=stop_t,
        start_execution_q_index=start_execution_q_index,
        stop_execution_q_index=stop_q,
        lane_partition_sha256=partition_sha256,
    )
    records = schedule.execution_records[
        start_execution_q_index:stop_q
    ]
    if max(record.t_index_count for record in records) < stop_t:
        _fail("resident stream contains a row unused by every selected q")

    lane_reports: list[LaneAccounting] = []
    totals = {
        "active_q_count": 0,
        "target_count": 0,
        "target_row_reference_count": 0,
        "value_count": 0,
        "sidecar_bytes": 0,
    }
    maximum_group_order = 0
    maximum_batch = 0
    maximum_target_values = 0
    for lane in selected_lanes:
        active_q = 0
        targets = 0
        rows = 0
        values = 0
        lane_maximum_group_order = 0
        for execution_q_index in range(
            lane.start_execution_q_index,
            lane.stop_execution_q_index,
        ):
            record = schedule.execution_records[execution_q_index]
            active_rows = max(
                0,
                min(record.t_index_count, stop_t) - first,
            )
            if active_rows == 0:
                continue
            group_order = _group_order(record.q)
            active_q += 1
            targets += (
                active_rows + MAXIMUM_BATCH_COUNT - 1
            ) // MAXIMUM_BATCH_COUNT
            rows += active_rows
            values += active_rows * group_order
            lane_maximum_group_order = max(
                lane_maximum_group_order, group_order
            )
            maximum_group_order = max(maximum_group_order, group_order)
            batch = min(active_rows, MAXIMUM_BATCH_COUNT)
            maximum_batch = max(maximum_batch, batch)
            maximum_target_values = max(
                maximum_target_values, batch * group_order
            )
        sidecar_bytes = rows * (FRAME_FACTOR.size + 8)
        lane_input_bytes = (
            LANE_HEADER.size
            + targets * TARGET_HEADER.size
            + sidecar_bytes
            + LANE_FOOTER.size
        )
        if (
            targets > MAXIMUM_TARGETS_PER_LANE
            or lane_input_bytes > MAXIMUM_LANE_INPUT_BYTES
        ):
            _fail("resident stream lane exceeds its exact bound")
        report = LaneAccounting(
            lane=lane,
            active_q_count=active_q,
            target_count=targets,
            target_row_reference_count=rows,
            value_count=values,
            sidecar_bytes=sidecar_bytes,
            lane_input_bytes=lane_input_bytes,
            maximum_group_order=lane_maximum_group_order,
        )
        lane_reports.append(report)
        totals["active_q_count"] += active_q
        totals["target_count"] += targets
        totals["target_row_reference_count"] += rows
        totals["value_count"] += values
        totals["sidecar_bytes"] += sidecar_bytes

    sidecar_input_size = (
        STREAM_HEADER.size
        + sum(item.lane_input_bytes for item in lane_reports)
        + STREAM_FOOTER.size
    )
    if (
        totals["active_q_count"] == 0
        or totals["target_count"] == 0
        or totals["target_count"] > MAXIMUM_PHASE_TARGETS
        or totals["target_row_reference_count"]
        > MAXIMUM_PHASE_ROW_REFERENCES
        or totals["value_count"] > MAXIMUM_PHASE_VALUES
        or maximum_group_order > MAXIMUM_GROUP_ORDER
        or maximum_target_values > MAXIMUM_TARGET_VALUES
        or sidecar_input_size > MAXIMUM_SIDECAR_INPUT_BYTES
    ):
        _fail("resident stream phase accounting exceeds its fixed bound")
    return StreamPlan(
        schedule_classification=_schedule_classification_id(schedule),
        phase_index=phase_index,
        coverage_mode=coverage_mode,
        canonical_first_t_index=canonical_first,
        canonical_t_index_stop_exclusive=canonical_stop,
        loaded_first_t_index=first,
        loaded_t_index_stop_exclusive=stop_t,
        start_execution_q_index=start_execution_q_index,
        stop_execution_q_index=stop_q,
        lanes=tuple(selected_lanes),
        lane_accounting=tuple(lane_reports),
        lane_partition_sha256=partition_sha256,
        phase_plan_sha256=plan_sha256,
        active_q_count=totals["active_q_count"],
        target_count=totals["target_count"],
        target_row_reference_count=(
            totals["target_row_reference_count"]
        ),
        value_count=totals["value_count"],
        sidecar_bytes=totals["sidecar_bytes"],
        sidecar_input_size_bytes=sidecar_input_size,
        maximum_group_order=maximum_group_order,
        maximum_target_batch_count=maximum_batch,
        maximum_target_value_count=maximum_target_values,
    )


def _initial_row_chain(plan_sha256: str) -> bytes:
    digest = hashlib.sha256(ROW_CHAIN_DOMAIN)
    digest.update(bytes.fromhex(plan_sha256))
    return digest.digest()


def _advance_row_chain(
    previous: bytes, t_index: int, payload_sha256: bytes
) -> bytes:
    digest = hashlib.sha256(ROW_CHAIN_DOMAIN)
    digest.update(previous)
    digest.update(struct.pack("<Q", t_index))
    digest.update(payload_sha256)
    return digest.digest()


def _initial_target_chain(plan_sha256: str) -> bytes:
    digest = hashlib.sha256(TARGET_CHAIN_DOMAIN)
    digest.update(bytes.fromhex(plan_sha256))
    return digest.digest()


def _initial_lane_target_chain(
    plan_sha256: str, lane_index: int
) -> bytes:
    digest = hashlib.sha256(LANE_TARGET_CHAIN_DOMAIN)
    digest.update(bytes.fromhex(plan_sha256))
    digest.update(struct.pack("<I", lane_index))
    return digest.digest()


def _advance_target_chain(
    previous: bytes, target: StreamTarget, *, lane: bool
) -> bytes:
    digest = hashlib.sha256(
        LANE_TARGET_CHAIN_DOMAIN if lane else TARGET_CHAIN_DOMAIN
    )
    digest.update(previous)
    digest.update(target.packed())
    return digest.digest()


def _lane_plan_digest(
    plan_sha256: str, accounting: LaneAccounting
) -> bytes:
    digest = hashlib.sha256(LANE_PLAN_DOMAIN)
    digest.update(bytes.fromhex(plan_sha256))
    digest.update(
        struct.pack(
            "<IIQQQQQQQQ",
            accounting.lane.lane_index,
            accounting.lane.q_count,
            accounting.lane.start_execution_q_index,
            accounting.lane.stop_execution_q_index,
            accounting.target_count,
            accounting.target_row_reference_count,
            accounting.value_count,
            accounting.sidecar_bytes,
            accounting.lane_input_bytes,
            accounting.maximum_group_order,
        )
    )
    return digest.digest()


def _initial_lane_chain(
    plan_sha256: str, partition_sha256: str
) -> bytes:
    digest = hashlib.sha256(LANE_CHAIN_DOMAIN)
    digest.update(bytes.fromhex(plan_sha256))
    digest.update(bytes.fromhex(partition_sha256))
    return digest.digest()


def _advance_lane_chain(
    previous: bytes,
    lane_plan_sha256: bytes,
    target_chain_sha256: bytes,
    lane_stream_sha256: bytes,
) -> bytes:
    digest = hashlib.sha256(LANE_CHAIN_DOMAIN)
    digest.update(previous)
    digest.update(lane_plan_sha256)
    digest.update(target_chain_sha256)
    digest.update(lane_stream_sha256)
    return digest.digest()


def _sidecar_digest(
    *,
    sidecar_source_sha256: str,
    plan_sha256: str,
    target: StreamTarget,
    factors: bytes,
    tails: bytes,
) -> bytes:
    digest = hashlib.sha256(SIDECAR_DOMAIN)
    digest.update(bytes.fromhex(sidecar_source_sha256))
    digest.update(bytes.fromhex(plan_sha256))
    digest.update(target.packed())
    digest.update(factors)
    digest.update(tails)
    return digest.digest()


def _validate_sidecars(
    target: StreamTarget, factors: bytes, tails: bytes
) -> None:
    if (
        len(factors) != target.batch_count * FRAME_FACTOR.size
        or len(tails) != target.batch_count * 8
    ):
        _fail("resident stream factor or tail length differs")
    for factor in FRAME_FACTOR.iter_unpack(factors):
        if (
            not all(math.isfinite(value) for value in factor)
            or factor[0] > factor[1]
            or factor[2] > factor[3]
        ):
            _fail("resident stream factor is malformed")
    for (tail,) in struct.iter_unpack("<d", tails):
        if not math.isfinite(tail) or tail < 0:
            _fail("resident stream Taylor tail is malformed")


def write_row_artifact(
    path: Path,
    schedule: ParsedScheduleManifest,
    plan: StreamPlan,
    *,
    recovery_seed_sha256: str,
    source_contract_sha256: str,
    lattice_source_sha256: str,
    row_provider: RowProvider,
    row_provider_finalizer: RowProviderFinalizer | None = None,
) -> dict[str, Any]:
    """Write one immutable row artifact without retaining the phase in RAM."""

    if plan.schedule_classification != _schedule_classification_id(schedule):
        _fail("resident row plan schedule classification differs")
    expected = build_stream_plan(
        schedule,
        phase_index=plan.phase_index,
        coverage_mode=plan.coverage_mode,
        loaded_first_t_index=plan.loaded_first_t_index,
        loaded_t_index_stop_exclusive=(
            plan.loaded_t_index_stop_exclusive
        ),
        start_execution_q_index=plan.start_execution_q_index,
        stop_execution_q_index=plan.stop_execution_q_index,
        lanes=plan.lanes,
    )
    if expected != plan:
        _fail("resident row plan differs from canonical reconstruction")
    for value, label in (
        (recovery_seed_sha256, "recovery seed"),
        (source_contract_sha256, "source contract"),
        (lattice_source_sha256, "lattice source"),
    ):
        _digest(value, label)

    def write(output: BinaryIO) -> dict[str, Any]:
        whole = hashlib.sha256()
        row_stream = hashlib.sha256()
        header = ROW_ARTIFACT_HEADER.pack(
            ROW_HEADER_MAGIC,
            FORMAT_VERSION,
            plan.schedule_classification,
            plan.coverage_mode,
            plan.phase_index,
            plan.row_count,
            0,
            plan.start_execution_q_index,
            plan.stop_execution_q_index,
            plan.canonical_first_t_index,
            plan.canonical_t_index_stop_exclusive,
            plan.loaded_first_t_index,
            plan.loaded_t_index_stop_exclusive,
            ROW_HEADER.size,
            ROW_PAYLOAD_BYTES,
            plan.row_input_size_bytes,
            bytes.fromhex(schedule.manifest_sha256),
            bytes.fromhex(schedule.execution_order_sha256),
            bytes.fromhex(plan.phase_plan_sha256),
            bytes.fromhex(CANDIDATE_REPORT_SHA256),
            bytes.fromhex(source_contract_sha256),
            bytes.fromhex(lattice_source_sha256),
            bytes.fromhex(recovery_seed_sha256),
            bytes.fromhex(plan.lane_partition_sha256),
        )
        _emit(output, header, whole=whole)
        chain = _initial_row_chain(plan.phase_plan_sha256)
        for t_index in range(
            plan.loaded_first_t_index,
            plan.loaded_t_index_stop_exclusive,
        ):
            payload = row_provider(t_index)
            if not isinstance(payload, bytes):
                _fail("resident row provider did not return bytes")
            validate_lattice_row(payload)
            payload_sha256 = hashlib.sha256(payload).digest()
            row_header = ROW_HEADER.pack(
                ROW_MAGIC,
                TMAJOR_ROW_FORMAT_VERSION,
                0,
                t_index,
                ROW_PAYLOAD_BYTES,
                payload_sha256,
            )
            _emit(
                output,
                row_header,
                whole=whole,
                secondary=row_stream,
            )
            _emit(
                output,
                payload,
                whole=whole,
                secondary=row_stream,
            )
            chain = _advance_row_chain(
                chain, t_index, payload_sha256
            )
        # A cache-backed provider can expose the requested rows before the
        # footer of its final intersecting storage shard has been reached.
        # Force that bounded source iterator to authenticate every touched
        # shard completely before this derived artifact is published.
        if row_provider_finalizer is not None:
            row_provider_finalizer()
        bytes_before_footer = output.tell()
        footer = ROW_ARTIFACT_FOOTER.pack(
            ROW_FOOTER_MAGIC,
            FORMAT_VERSION,
            0,
            plan.row_count,
            bytes_before_footer,
            plan.row_count * ROW_PAYLOAD_BYTES,
            chain,
            row_stream.digest(),
            b"\0" * 32,
        )
        _emit(output, footer, whole=whole)
        if output.tell() != plan.row_input_size_bytes:
            _fail("resident row writer byte accounting differs")
        return {
            "input_sha256": whole.hexdigest(),
            "input_size_bytes": plan.row_input_size_bytes,
            "row_chain_sha256": chain.hex(),
            "row_stream_sha256": row_stream.hexdigest(),
        }

    streamed = _atomic_stream(path, write)
    body: dict[str, Any] = {
        "schema": ROW_SCHEMA,
        "schema_version": FORMAT_VERSION,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "source_shaped_incremental_row_artifact_not_source_execution"
        ),
        "schedule_manifest_sha256": schedule.manifest_sha256,
        "schedule_execution_order_sha256": (
            schedule.execution_order_sha256
        ),
        "phase_plan_sha256": plan.phase_plan_sha256,
        "candidate_report_sha256": CANDIDATE_REPORT_SHA256,
        "lane_partition_sha256": plan.lane_partition_sha256,
        "source_contract_sha256": source_contract_sha256,
        "lattice_source_sha256": lattice_source_sha256,
        "recovery_seed_artifact_sha256": recovery_seed_sha256,
        "phase_index": plan.phase_index,
        "coverage_mode": plan.coverage_mode,
        "canonical_first_t_index": plan.canonical_first_t_index,
        "canonical_t_index_stop_exclusive": (
            plan.canonical_t_index_stop_exclusive
        ),
        "loaded_first_t_index": plan.loaded_first_t_index,
        "loaded_t_index_stop_exclusive": (
            plan.loaded_t_index_stop_exclusive
        ),
        "row_count": plan.row_count,
        "maximum_row_count": MAXIMUM_ROWS,
        "row_staging_bytes_required": ROW_PAYLOAD_BYTES,
        "full_phase_host_duplicate_required": False,
        **streamed,
        "source_scale_run": False,
        "h100_source_phase_completed": False,
        "production_run_completed": False,
        "trusted_execution_attested": False,
        "completed_l_zero_state_validated": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }
    body["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return body


def write_sidecar_artifact(
    path: Path,
    schedule: ParsedScheduleManifest,
    plan: StreamPlan,
    *,
    row_artifact_sha256: str,
    recovery_seed_sha256: str,
    source_contract_sha256: str,
    sidecar_source_sha256: str,
    sidecar_provider: SidecarProvider,
) -> dict[str, Any]:
    """Write bounded q-lanes while retaining at most one target sidecar."""

    expected = build_stream_plan(
        schedule,
        phase_index=plan.phase_index,
        coverage_mode=plan.coverage_mode,
        loaded_first_t_index=plan.loaded_first_t_index,
        loaded_t_index_stop_exclusive=(
            plan.loaded_t_index_stop_exclusive
        ),
        start_execution_q_index=plan.start_execution_q_index,
        stop_execution_q_index=plan.stop_execution_q_index,
        lanes=plan.lanes,
    )
    if expected != plan:
        _fail("resident sidecar plan differs from canonical reconstruction")
    for value, label in (
        (row_artifact_sha256, "row artifact"),
        (recovery_seed_sha256, "recovery seed"),
        (source_contract_sha256, "source contract"),
        (sidecar_source_sha256, "sidecar source"),
    ):
        _digest(value, label)

    def write(output: BinaryIO) -> dict[str, Any]:
        whole = hashlib.sha256()
        body_stream = hashlib.sha256()
        header = STREAM_HEADER.pack(
            STREAM_HEADER_MAGIC,
            FORMAT_VERSION,
            plan.schedule_classification,
            plan.coverage_mode,
            plan.phase_index,
            len(plan.lanes),
            MAXIMUM_Q_PER_LANE,
            MAXIMUM_TARGETS_PER_LANE,
            MAXIMUM_BATCH_COUNT,
            0,
            0,
            plan.start_execution_q_index,
            plan.stop_execution_q_index,
            plan.canonical_first_t_index,
            plan.canonical_t_index_stop_exclusive,
            plan.loaded_first_t_index,
            plan.loaded_t_index_stop_exclusive,
            plan.active_q_count,
            plan.target_count,
            plan.target_row_reference_count,
            plan.value_count,
            plan.sidecar_input_size_bytes,
            plan.maximum_group_order,
            bytes.fromhex(schedule.manifest_sha256),
            bytes.fromhex(schedule.execution_order_sha256),
            bytes.fromhex(plan.phase_plan_sha256),
            bytes.fromhex(CANDIDATE_REPORT_SHA256),
            bytes.fromhex(source_contract_sha256),
            bytes.fromhex(row_artifact_sha256),
            bytes.fromhex(recovery_seed_sha256),
            bytes.fromhex(sidecar_source_sha256),
            bytes.fromhex(plan.lane_partition_sha256),
        )
        _emit(output, header, whole=whole)
        lane_chain = _initial_lane_chain(
            plan.phase_plan_sha256,
            plan.lane_partition_sha256,
        )
        global_target_chain = _initial_target_chain(
            plan.phase_plan_sha256
        )
        target_count = 0
        row_references = 0
        value_count = 0
        sidecar_bytes = 0
        for accounting in plan.lane_accounting:
            lane_start = output.tell()
            lane_plan_sha256 = _lane_plan_digest(
                plan.phase_plan_sha256, accounting
            )
            lane_header = LANE_HEADER.pack(
                LANE_HEADER_MAGIC,
                FORMAT_VERSION,
                0,
                accounting.lane.lane_index,
                accounting.lane.q_count,
                accounting.lane.start_execution_q_index,
                accounting.lane.stop_execution_q_index,
                accounting.target_count,
                accounting.target_row_reference_count,
                accounting.value_count,
                accounting.sidecar_bytes,
                accounting.lane_input_bytes,
                accounting.maximum_group_order,
                lane_chain,
                lane_plan_sha256,
            )
            lane_stream = hashlib.sha256()
            _emit(
                output,
                lane_header,
                whole=whole,
                secondary=lane_stream,
            )
            body_stream.update(lane_header)
            lane_target_chain = _initial_lane_target_chain(
                plan.phase_plan_sha256,
                accounting.lane.lane_index,
            )
            lane_targets = 0
            lane_rows = 0
            lane_values = 0
            lane_sidecars = 0
            for target in _iter_lane_targets(
                schedule, plan, accounting.lane
            ):
                factors, tails = sidecar_provider(target)
                if (
                    not isinstance(factors, bytes)
                    or not isinstance(tails, bytes)
                ):
                    _fail(
                        "resident sidecar provider did not return bytes"
                    )
                _validate_sidecars(target, factors, tails)
                component_count = len(
                    canonical_component_orders(target.q)
                )
                group_order = _group_order(target.q)
                target_values = target.batch_count * group_order
                target_header = TARGET_HEADER.pack(
                    TARGET_MAGIC,
                    FORMAT_VERSION,
                    0,
                    target.execution_q_index,
                    target.q,
                    target.phase_index,
                    target.lane_index,
                    target.first_t_index,
                    target.t_index_stop_exclusive,
                    target.batch_count,
                    component_count,
                    0,
                    group_order,
                    target_values,
                    len(factors),
                    len(tails),
                    bytes.fromhex(target.digest()),
                    _sidecar_digest(
                        sidecar_source_sha256=sidecar_source_sha256,
                        plan_sha256=plan.phase_plan_sha256,
                        target=target,
                        factors=factors,
                        tails=tails,
                    ),
                )
                for raw in (target_header, factors, tails):
                    _emit(
                        output,
                        raw,
                        whole=whole,
                        secondary=lane_stream,
                    )
                    body_stream.update(raw)
                lane_target_chain = _advance_target_chain(
                    lane_target_chain, target, lane=True
                )
                global_target_chain = _advance_target_chain(
                    global_target_chain, target, lane=False
                )
                lane_targets += 1
                lane_rows += target.batch_count
                lane_values += target_values
                lane_sidecars += len(factors) + len(tails)
            if (
                lane_targets != accounting.target_count
                or lane_rows
                != accounting.target_row_reference_count
                or lane_values != accounting.value_count
                or lane_sidecars != accounting.sidecar_bytes
            ):
                _fail("resident lane writer accounting differs")
            bytes_before_footer = output.tell() - lane_start
            lane_stream_sha256 = lane_stream.digest()
            lane_chain = _advance_lane_chain(
                lane_chain,
                lane_plan_sha256,
                lane_target_chain,
                lane_stream_sha256,
            )
            lane_footer = LANE_FOOTER.pack(
                LANE_FOOTER_MAGIC,
                FORMAT_VERSION,
                0,
                accounting.lane.lane_index,
                0,
                accounting.lane.q_count,
                lane_targets,
                lane_rows,
                lane_values,
                lane_sidecars,
                bytes_before_footer,
                lane_target_chain,
                lane_stream_sha256,
                lane_chain,
                b"\0" * 32,
            )
            _emit(output, lane_footer, whole=whole)
            body_stream.update(lane_footer)
            if output.tell() - lane_start != accounting.lane_input_bytes:
                _fail("resident lane byte accounting differs")
            target_count += lane_targets
            row_references += lane_rows
            value_count += lane_values
            sidecar_bytes += lane_sidecars
        bytes_before_footer = output.tell()
        footer = STREAM_FOOTER.pack(
            STREAM_FOOTER_MAGIC,
            FORMAT_VERSION,
            0,
            len(plan.lanes),
            plan.active_q_count,
            target_count,
            row_references,
            value_count,
            sidecar_bytes,
            bytes_before_footer,
            lane_chain,
            global_target_chain,
            body_stream.digest(),
            b"\0" * 32,
        )
        _emit(output, footer, whole=whole)
        if (
            target_count != plan.target_count
            or row_references != plan.target_row_reference_count
            or value_count != plan.value_count
            or sidecar_bytes != plan.sidecar_bytes
            or output.tell() != plan.sidecar_input_size_bytes
        ):
            _fail("resident sidecar writer totals differ")
        return {
            "input_sha256": whole.hexdigest(),
            "input_size_bytes": plan.sidecar_input_size_bytes,
            "lane_chain_sha256": lane_chain.hex(),
            "target_chain_sha256": global_target_chain.hex(),
            "body_stream_sha256": body_stream.hexdigest(),
        }

    streamed = _atomic_stream(path, write)
    body: dict[str, Any] = {
        "schema": SIDECAR_SCHEMA,
        "schema_version": FORMAT_VERSION,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "source_shaped_bounded_lane_sidecars_not_source_execution"
        ),
        "schedule_manifest_sha256": schedule.manifest_sha256,
        "schedule_execution_order_sha256": (
            schedule.execution_order_sha256
        ),
        "phase_plan_sha256": plan.phase_plan_sha256,
        "candidate_report_sha256": CANDIDATE_REPORT_SHA256,
        "lane_partition_sha256": plan.lane_partition_sha256,
        "source_contract_sha256": source_contract_sha256,
        "row_artifact_sha256": row_artifact_sha256,
        "recovery_seed_artifact_sha256": recovery_seed_sha256,
        "sidecar_source_sha256": sidecar_source_sha256,
        "phase_index": plan.phase_index,
        "coverage_mode": plan.coverage_mode,
        "lane_count": len(plan.lanes),
        "active_q_count": plan.active_q_count,
        "target_count": plan.target_count,
        "target_row_reference_count": (
            plan.target_row_reference_count
        ),
        "value_count": plan.value_count,
        "sidecar_bytes": plan.sidecar_bytes,
        "maximum_q_per_lane": MAXIMUM_Q_PER_LANE,
        "maximum_targets_per_lane": MAXIMUM_TARGETS_PER_LANE,
        "maximum_batch_count": MAXIMUM_BATCH_COUNT,
        "maximum_group_order": plan.maximum_group_order,
        **streamed,
        "source_scale_run": False,
        "h100_source_phase_completed": False,
        "production_run_completed": False,
        "trusted_execution_attested": False,
        "completed_l_zero_state_validated": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }
    body["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return body


@dataclass(frozen=True)
class ParsedRowArtifact:
    path: Path
    plan: StreamPlan
    source_contract_sha256: str
    lattice_source_sha256: str
    recovery_seed_sha256: str
    row_chain_sha256: str
    row_stream_sha256: str
    input_sha256: str
    input_size_bytes: int
    captured_rows: tuple[bytes, ...]


@dataclass(frozen=True)
class ParsedStreamFrame:
    target: StreamTarget
    component_count: int
    group_order: int
    value_count: int
    factors: bytes
    tails: bytes


@dataclass(frozen=True)
class ParsedSidecarArtifact:
    path: Path
    plan: StreamPlan
    source_contract_sha256: str
    row_artifact_sha256: str
    recovery_seed_sha256: str
    sidecar_source_sha256: str
    lane_chain_sha256: str
    target_chain_sha256: str
    body_stream_sha256: str
    input_sha256: str
    input_size_bytes: int
    captured_frames: tuple[ParsedStreamFrame, ...]


def _rebuild_plan(
    schedule: ParsedScheduleManifest, plan: StreamPlan
) -> StreamPlan:
    rebuilt = build_stream_plan(
        schedule,
        phase_index=plan.phase_index,
        coverage_mode=plan.coverage_mode,
        loaded_first_t_index=plan.loaded_first_t_index,
        loaded_t_index_stop_exclusive=(
            plan.loaded_t_index_stop_exclusive
        ),
        start_execution_q_index=plan.start_execution_q_index,
        stop_execution_q_index=plan.stop_execution_q_index,
        lanes=plan.lanes,
    )
    if rebuilt != plan:
        _fail("resident stream plan differs from reconstruction")
    return rebuilt


def replay_row_artifact(
    path: Path,
    schedule: ParsedScheduleManifest,
    plan: StreamPlan,
    *,
    expected_input_sha256: str | None = None,
    capture_rows: bool = False,
) -> ParsedRowArtifact:
    """Replay the row file with one payload of working memory."""

    if not isinstance(capture_rows, bool):
        _fail("capture rows flag is malformed")
    _rebuild_plan(schedule, plan)
    with _open_regular(path, label="resident stream row artifact") as source:
        before = os.fstat(source.fileno())
        if (
            before.st_size != plan.row_input_size_bytes
            or not 1 <= before.st_size <= MAXIMUM_ROW_ARTIFACT_BYTES
        ):
            _fail("resident row artifact size differs")
        whole = hashlib.sha256()
        row_stream = hashlib.sha256()
        raw_header = _read_exact(
            source, ROW_ARTIFACT_HEADER.size, "resident row header"
        )
        whole.update(raw_header)
        (
            magic,
            version,
            schedule_classification,
            coverage_mode,
            phase_index,
            row_count,
            reserved,
            start_q,
            stop_q,
            canonical_first,
            canonical_stop,
            loaded_first,
            loaded_stop,
            row_header_bytes,
            row_payload_bytes,
            input_size,
            schedule_sha256,
            execution_sha256,
            plan_sha256,
            candidate_sha256,
            source_contract_sha256,
            lattice_source_sha256,
            recovery_seed_sha256,
            lane_partition_sha256,
        ) = ROW_ARTIFACT_HEADER.unpack(raw_header)
        if (
            magic != ROW_HEADER_MAGIC
            or version != FORMAT_VERSION
            or schedule_classification != plan.schedule_classification
            or coverage_mode != plan.coverage_mode
            or phase_index != plan.phase_index
            or row_count != plan.row_count
            or reserved != 0
            or start_q != plan.start_execution_q_index
            or stop_q != plan.stop_execution_q_index
            or canonical_first != plan.canonical_first_t_index
            or canonical_stop
            != plan.canonical_t_index_stop_exclusive
            or loaded_first != plan.loaded_first_t_index
            or loaded_stop != plan.loaded_t_index_stop_exclusive
            or row_header_bytes != ROW_HEADER.size
            or row_payload_bytes != ROW_PAYLOAD_BYTES
            or input_size != before.st_size
            or schedule_sha256.hex() != schedule.manifest_sha256
            or execution_sha256.hex()
            != schedule.execution_order_sha256
            or plan_sha256.hex() != plan.phase_plan_sha256
            or candidate_sha256.hex() != CANDIDATE_REPORT_SHA256
            or lane_partition_sha256.hex()
            != plan.lane_partition_sha256
        ):
            _fail("resident row header or plan binding differs")
        chain = _initial_row_chain(plan.phase_plan_sha256)
        captured: list[bytes] = []
        if capture_rows and row_count > 64:
            _fail("resident row capture exceeds its KAT bound")
        for row_offset in range(row_count):
            raw_row = _read_exact(
                source, ROW_HEADER.size, "resident row record"
            )
            payload = _read_exact(
                source, ROW_PAYLOAD_BYTES, "resident row payload"
            )
            whole.update(raw_row)
            whole.update(payload)
            row_stream.update(raw_row)
            row_stream.update(payload)
            (
                row_magic,
                row_version,
                row_reserved,
                t_index,
                payload_bytes,
                payload_sha256,
            ) = ROW_HEADER.unpack(raw_row)
            if (
                row_magic != ROW_MAGIC
                or row_version != TMAJOR_ROW_FORMAT_VERSION
                or row_reserved != 0
                or t_index != loaded_first + row_offset
                or payload_bytes != ROW_PAYLOAD_BYTES
                or hashlib.sha256(payload).digest() != payload_sha256
            ):
                _fail("resident stream row is substituted or malformed")
            validate_lattice_row(payload)
            chain = _advance_row_chain(
                chain, t_index, payload_sha256
            )
            if capture_rows:
                captured.append(payload)
        bytes_before_footer = source.tell()
        raw_footer = _read_exact(
            source, ROW_ARTIFACT_FOOTER.size, "resident row footer"
        )
        whole.update(raw_footer)
        (
            footer_magic,
            footer_version,
            footer_reserved,
            footer_rows,
            footer_input_before,
            footer_payload_bytes,
            footer_chain,
            footer_stream,
            footer_reserved_sha256,
        ) = ROW_ARTIFACT_FOOTER.unpack(raw_footer)
        if (
            footer_magic != ROW_FOOTER_MAGIC
            or footer_version != FORMAT_VERSION
            or footer_reserved != 0
            or footer_rows != row_count
            or footer_input_before != bytes_before_footer
            or footer_payload_bytes != row_count * ROW_PAYLOAD_BYTES
            or footer_chain != chain
            or footer_stream != row_stream.digest()
            or footer_reserved_sha256 != b"\0" * 32
            or source.read(1) != b""
        ):
            _fail("resident row footer or ordered commitment differs")
        after = os.fstat(source.fileno())
    input_sha256 = whole.hexdigest()
    if _identity(before) != _identity(after):
        _fail("resident row artifact changed while replayed")
    if (
        expected_input_sha256 is not None
        and input_sha256
        != _digest(expected_input_sha256, "resident row input")
    ):
        _fail("resident row artifact differs from its external pin")
    return ParsedRowArtifact(
        path=path.resolve(),
        plan=plan,
        source_contract_sha256=source_contract_sha256.hex(),
        lattice_source_sha256=lattice_source_sha256.hex(),
        recovery_seed_sha256=recovery_seed_sha256.hex(),
        row_chain_sha256=chain.hex(),
        row_stream_sha256=row_stream.hexdigest(),
        input_sha256=input_sha256,
        input_size_bytes=before.st_size,
        captured_rows=tuple(captured),
    )


def replay_sidecar_artifact(
    path: Path,
    schedule: ParsedScheduleManifest,
    plan: StreamPlan,
    rows: ParsedRowArtifact,
    *,
    expected_input_sha256: str | None = None,
    capture_frames: bool = False,
) -> ParsedSidecarArtifact:
    """Replay every bounded q lane while retaining at most one sidecar."""

    if not isinstance(capture_frames, bool):
        _fail("capture frames flag is malformed")
    _rebuild_plan(schedule, plan)
    if rows.plan != plan:
        _fail("resident row and sidecar plans differ")
    if capture_frames and plan.target_count > 64:
        _fail("resident sidecar capture exceeds its KAT bound")

    with _open_regular(
        path, label="resident stream sidecar artifact"
    ) as source:
        before = os.fstat(source.fileno())
        if (
            before.st_size != plan.sidecar_input_size_bytes
            or not 1 <= before.st_size <= MAXIMUM_SIDECAR_INPUT_BYTES
        ):
            _fail("resident sidecar artifact size differs")
        whole = hashlib.sha256()
        body_stream = hashlib.sha256()
        raw_header = _read_exact(
            source, STREAM_HEADER.size, "resident stream header"
        )
        whole.update(raw_header)
        (
            magic,
            version,
            schedule_classification,
            coverage_mode,
            phase_index,
            lane_count,
            maximum_q_per_lane,
            maximum_targets_per_lane,
            maximum_batch_count,
            reserved0,
            reserved1,
            start_q,
            stop_q,
            canonical_first,
            canonical_stop,
            loaded_first,
            loaded_stop,
            active_q_count,
            target_count,
            target_row_references,
            value_count,
            input_size,
            maximum_group_order,
            schedule_sha256,
            execution_sha256,
            plan_sha256,
            candidate_sha256,
            source_contract_sha256,
            row_artifact_sha256,
            recovery_seed_sha256,
            sidecar_source_sha256,
            lane_partition_sha256,
        ) = STREAM_HEADER.unpack(raw_header)
        if (
            magic != STREAM_HEADER_MAGIC
            or version != FORMAT_VERSION
            or schedule_classification != plan.schedule_classification
            or coverage_mode != plan.coverage_mode
            or phase_index != plan.phase_index
            or lane_count != len(plan.lanes)
            or maximum_q_per_lane != MAXIMUM_Q_PER_LANE
            or maximum_targets_per_lane
            != MAXIMUM_TARGETS_PER_LANE
            or maximum_batch_count != MAXIMUM_BATCH_COUNT
            or reserved0 != 0
            or reserved1 != 0
            or start_q != plan.start_execution_q_index
            or stop_q != plan.stop_execution_q_index
            or canonical_first != plan.canonical_first_t_index
            or canonical_stop
            != plan.canonical_t_index_stop_exclusive
            or loaded_first != plan.loaded_first_t_index
            or loaded_stop != plan.loaded_t_index_stop_exclusive
            or active_q_count != plan.active_q_count
            or target_count != plan.target_count
            or target_row_references
            != plan.target_row_reference_count
            or value_count != plan.value_count
            or input_size != before.st_size
            or maximum_group_order != plan.maximum_group_order
            or schedule_sha256.hex() != schedule.manifest_sha256
            or execution_sha256.hex()
            != schedule.execution_order_sha256
            or plan_sha256.hex() != plan.phase_plan_sha256
            or candidate_sha256.hex() != CANDIDATE_REPORT_SHA256
            or source_contract_sha256.hex()
            != rows.source_contract_sha256
            or row_artifact_sha256.hex() != rows.input_sha256
            or recovery_seed_sha256.hex()
            != rows.recovery_seed_sha256
            or lane_partition_sha256.hex()
            != plan.lane_partition_sha256
        ):
            _fail("resident sidecar header or artifact binding differs")

        lane_chain = _initial_lane_chain(
            plan.phase_plan_sha256,
            plan.lane_partition_sha256,
        )
        global_target_chain = _initial_target_chain(
            plan.phase_plan_sha256
        )
        captured: list[ParsedStreamFrame] = []
        total_targets = 0
        total_rows = 0
        total_values = 0
        total_sidecars = 0
        for accounting in plan.lane_accounting:
            lane_start = source.tell()
            raw_lane_header = _read_exact(
                source, LANE_HEADER.size, "resident lane header"
            )
            whole.update(raw_lane_header)
            body_stream.update(raw_lane_header)
            lane_stream = hashlib.sha256(raw_lane_header)
            (
                lane_magic,
                lane_version,
                lane_reserved,
                lane_index,
                lane_q_count,
                lane_start_q,
                lane_stop_q,
                lane_target_count,
                lane_row_references,
                lane_value_count,
                lane_sidecar_bytes,
                lane_input_bytes,
                lane_maximum_group_order,
                previous_lane_chain,
                lane_plan_sha256,
            ) = LANE_HEADER.unpack(raw_lane_header)
            expected_lane_plan = _lane_plan_digest(
                plan.phase_plan_sha256, accounting
            )
            if (
                lane_magic != LANE_HEADER_MAGIC
                or lane_version != FORMAT_VERSION
                or lane_reserved != 0
                or lane_index != accounting.lane.lane_index
                or lane_q_count != accounting.lane.q_count
                or lane_start_q
                != accounting.lane.start_execution_q_index
                or lane_stop_q
                != accounting.lane.stop_execution_q_index
                or lane_target_count != accounting.target_count
                or lane_row_references
                != accounting.target_row_reference_count
                or lane_value_count != accounting.value_count
                or lane_sidecar_bytes != accounting.sidecar_bytes
                or lane_input_bytes != accounting.lane_input_bytes
                or lane_maximum_group_order
                != accounting.maximum_group_order
                or previous_lane_chain != lane_chain
                or lane_plan_sha256 != expected_lane_plan
            ):
                _fail("resident lane header or ordered partition differs")
            lane_target_chain = _initial_lane_target_chain(
                plan.phase_plan_sha256,
                accounting.lane.lane_index,
            )
            observed_targets = 0
            observed_rows = 0
            observed_values = 0
            observed_sidecars = 0
            for target_number, expected_target in enumerate(
                _iter_lane_targets(schedule, plan, accounting.lane)
            ):
                raw_target = _read_exact(
                    source, TARGET_HEADER.size, "resident target header"
                )
                whole.update(raw_target)
                body_stream.update(raw_target)
                lane_stream.update(raw_target)
                (
                    target_magic,
                    target_version,
                    target_reserved,
                    execution_q_index,
                    q,
                    target_phase_index,
                    target_lane_index,
                    target_first,
                    target_stop,
                    batch_count,
                    component_count,
                    target_reserved2,
                    group_order,
                    target_values,
                    factor_bytes,
                    tail_bytes,
                    target_sha256,
                    sidecar_sha256,
                ) = TARGET_HEADER.unpack(raw_target)
                expected_group_order = _group_order(expected_target.q)
                expected_components = len(
                    canonical_component_orders(expected_target.q)
                )
                if (
                    target_magic != TARGET_MAGIC
                    or target_version != FORMAT_VERSION
                    or target_reserved != 0
                    or execution_q_index
                    != expected_target.execution_q_index
                    or q != expected_target.q
                    or target_phase_index != expected_target.phase_index
                    or target_lane_index != expected_target.lane_index
                    or target_first != expected_target.first_t_index
                    or target_stop
                    != expected_target.t_index_stop_exclusive
                    or batch_count != expected_target.batch_count
                    or component_count != expected_components
                    or target_reserved2 != 0
                    or group_order != expected_group_order
                    or target_values
                    != expected_target.batch_count
                    * expected_group_order
                    or factor_bytes
                    != expected_target.batch_count * FRAME_FACTOR.size
                    or tail_bytes != expected_target.batch_count * 8
                    or target_sha256.hex()
                    != expected_target.digest()
                ):
                    _fail(
                        "resident stream target "
                        f"{target_number} is substituted or reordered"
                    )
                factors = _read_exact(
                    source, factor_bytes, "resident target factors"
                )
                tails = _read_exact(
                    source, tail_bytes, "resident target tails"
                )
                for raw in (factors, tails):
                    whole.update(raw)
                    body_stream.update(raw)
                    lane_stream.update(raw)
                _validate_sidecars(expected_target, factors, tails)
                if (
                    _sidecar_digest(
                        sidecar_source_sha256=(
                            sidecar_source_sha256.hex()
                        ),
                        plan_sha256=plan.phase_plan_sha256,
                        target=expected_target,
                        factors=factors,
                        tails=tails,
                    )
                    != sidecar_sha256
                ):
                    _fail("resident stream sidecar binding differs")
                lane_target_chain = _advance_target_chain(
                    lane_target_chain,
                    expected_target,
                    lane=True,
                )
                global_target_chain = _advance_target_chain(
                    global_target_chain,
                    expected_target,
                    lane=False,
                )
                observed_targets += 1
                observed_rows += expected_target.batch_count
                observed_values += target_values
                observed_sidecars += factor_bytes + tail_bytes
                if capture_frames:
                    captured.append(
                        ParsedStreamFrame(
                            target=expected_target,
                            component_count=component_count,
                            group_order=group_order,
                            value_count=target_values,
                            factors=factors,
                            tails=tails,
                        )
                    )
            bytes_before_lane_footer = source.tell() - lane_start
            lane_stream_sha256 = lane_stream.digest()
            expected_lane_chain = _advance_lane_chain(
                lane_chain,
                expected_lane_plan,
                lane_target_chain,
                lane_stream_sha256,
            )
            raw_lane_footer = _read_exact(
                source, LANE_FOOTER.size, "resident lane footer"
            )
            whole.update(raw_lane_footer)
            body_stream.update(raw_lane_footer)
            (
                footer_magic,
                footer_version,
                footer_reserved,
                footer_lane_index,
                footer_reserved2,
                footer_q_count,
                footer_targets,
                footer_rows,
                footer_values,
                footer_sidecars,
                footer_input_before,
                footer_target_chain,
                footer_lane_stream,
                footer_lane_chain,
                footer_reserved_sha256,
            ) = LANE_FOOTER.unpack(raw_lane_footer)
            if (
                footer_magic != LANE_FOOTER_MAGIC
                or footer_version != FORMAT_VERSION
                or footer_reserved != 0
                or footer_lane_index != accounting.lane.lane_index
                or footer_reserved2 != 0
                or footer_q_count != accounting.lane.q_count
                or footer_targets != observed_targets
                or footer_rows != observed_rows
                or footer_values != observed_values
                or footer_sidecars != observed_sidecars
                or footer_input_before != bytes_before_lane_footer
                or footer_target_chain != lane_target_chain
                or footer_lane_stream != lane_stream_sha256
                or footer_lane_chain != expected_lane_chain
                or footer_reserved_sha256 != b"\0" * 32
                or source.tell() - lane_start
                != accounting.lane_input_bytes
            ):
                _fail("resident lane footer or commitment differs")
            lane_chain = expected_lane_chain
            total_targets += observed_targets
            total_rows += observed_rows
            total_values += observed_values
            total_sidecars += observed_sidecars

        bytes_before_footer = source.tell()
        raw_footer = _read_exact(
            source, STREAM_FOOTER.size, "resident stream footer"
        )
        whole.update(raw_footer)
        (
            footer_magic,
            footer_version,
            footer_reserved,
            footer_lanes,
            footer_active_q,
            footer_targets,
            footer_rows,
            footer_values,
            footer_sidecars,
            footer_input_before,
            footer_lane_chain,
            footer_target_chain,
            footer_body_stream,
            footer_reserved_sha256,
        ) = STREAM_FOOTER.unpack(raw_footer)
        if (
            footer_magic != STREAM_FOOTER_MAGIC
            or footer_version != FORMAT_VERSION
            or footer_reserved != 0
            or footer_lanes != len(plan.lanes)
            or footer_active_q != plan.active_q_count
            or footer_targets != total_targets
            or footer_rows != total_rows
            or footer_values != total_values
            or footer_sidecars != total_sidecars
            or footer_input_before != bytes_before_footer
            or footer_lane_chain != lane_chain
            or footer_target_chain != global_target_chain
            or footer_body_stream != body_stream.digest()
            or footer_reserved_sha256 != b"\0" * 32
            or source.read(1) != b""
        ):
            _fail("resident stream footer or global commitment differs")
        after = os.fstat(source.fileno())
    input_sha256 = whole.hexdigest()
    if _identity(before) != _identity(after):
        _fail("resident sidecar artifact changed while replayed")
    if (
        expected_input_sha256 is not None
        and input_sha256
        != _digest(expected_input_sha256, "resident sidecar input")
    ):
        _fail("resident sidecar artifact differs from its external pin")
    return ParsedSidecarArtifact(
        path=path.resolve(),
        plan=plan,
        source_contract_sha256=source_contract_sha256.hex(),
        row_artifact_sha256=row_artifact_sha256.hex(),
        recovery_seed_sha256=recovery_seed_sha256.hex(),
        sidecar_source_sha256=sidecar_source_sha256.hex(),
        lane_chain_sha256=lane_chain.hex(),
        target_chain_sha256=global_target_chain.hex(),
        body_stream_sha256=body_stream.hexdigest(),
        input_sha256=input_sha256,
        input_size_bytes=before.st_size,
        captured_frames=tuple(captured),
    )


def explicit_device_memory_formula(
    plan: StreamPlan, *, seed_record_count: int
) -> dict[str, Any]:
    """Return the exact explicit cudaMalloc peak for this executor.

    CUDA context, event implementation details, allocator fragmentation, and
    future downstream state are deliberately outside the explicit formula and
    are covered only by the separately reported 512-MiB reserve.
    """

    seed_count = _integer(
        seed_record_count,
        "seed record count",
        minimum=1,
        maximum=1 << 32,
    )
    components = {
        "seed_records_bytes": seed_count * SEED_RECORD.size,
        "resident_lattice_bytes": plan.row_count * ROW_PAYLOAD_BYTES,
        "maximum_descriptor_bytes": (
            plan.maximum_group_order * RESIDUE_DESCRIPTOR.size
        ),
        "maximum_factor_bytes": (
            plan.maximum_target_batch_count * FRAME_FACTOR.size
        ),
        "maximum_tail_bytes": plan.maximum_target_batch_count * 8,
        "maximum_output_bytes": (
            plan.maximum_target_value_count * COMPLEX_INTERVAL.size
        ),
    }
    total = sum(components.values())
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_resident_qmajor_stream."
            "device_memory_formula.v1"
        ),
        "schema_version": FORMAT_VERSION,
        "algorithm_id": CUDA_ALGORITHM_ID,
        "seed_record_count": seed_count,
        **components,
        "known_allocation_bytes": total,
        "device_memory_safety_reserve_bytes": (
            DEVICE_MEMORY_SAFETY_RESERVE_BYTES
        ),
        "required_free_device_bytes": (
            total + DEVICE_MEMORY_SAFETY_RESERVE_BYTES
        ),
        "formula_exact_for_explicit_cuda_allocations": True,
        "cuda_context_event_and_fragmentation_bytes_in_formula": False,
        "source_h100_fit_claimed": False,
    }


def explicit_executor_buffer_formula(
    plan: StreamPlan, *, seed_record_count: int
) -> dict[str, Any]:
    """Separate bounded host, explicit device, disk, and stream sizes.

    The host total covers payload staging owned by this executor, not Python
    or C++ container metadata.  Row staging is released before target
    execution; descriptors, one target's sidecars, and one target's output
    may coexist.  Output bytes are projected transport volume, not a required
    resident or regular-file buffer.
    """

    device = explicit_device_memory_formula(
        plan, seed_record_count=seed_record_count
    )
    host_descriptor = device["maximum_descriptor_bytes"]
    host_sidecar = (
        device["maximum_factor_bytes"]
        + device["maximum_tail_bytes"]
    )
    host_output = device["maximum_output_bytes"]
    host_row = ROW_PAYLOAD_BYTES
    host_payload = max(
        host_row,
        host_descriptor + host_sidecar + host_output,
    )
    projected_output = (
        plan.target_count * TGDAFFI_HEADER.size
        + plan.value_count * COMPLEX_INTERVAL.size
    )
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_resident_qmajor_stream."
            "executor_buffer_formula.v1"
        ),
        "schema_version": FORMAT_VERSION,
        "algorithm_id": CUDA_ALGORITHM_ID,
        "host_row_staging_bytes": host_row,
        "host_descriptor_staging_bytes": host_descriptor,
        "host_sidecar_staging_bytes": host_sidecar,
        "host_output_staging_bytes": host_output,
        "host_payload_staging_bound_bytes": host_payload,
        "device_known_allocation_bytes": device[
            "known_allocation_bytes"
        ],
        "device_safety_reserve_bytes": (
            DEVICE_MEMORY_SAFETY_RESERVE_BYTES
        ),
        "disk_row_artifact_bytes": plan.row_input_size_bytes,
        "disk_sidecar_artifact_bytes": (
            plan.sidecar_input_size_bytes
        ),
        "disk_total_input_artifact_bytes": (
            plan.row_input_size_bytes
            + plan.sidecar_input_size_bytes
        ),
        "projected_output_stream_bytes": projected_output,
        "maximum_source_phase_projected_output_stream_bytes": (
            MAXIMUM_PROJECTED_PHASE_OUTPUT_BYTES
        ),
        "output_streamed_with_target_backpressure": True,
        "full_output_retained_in_host_or_device_memory": False,
        "full_source_regular_file_output_supported": False,
        "source_output_materialization_feasible_claimed": False,
    }


def _canonical_json(path: Path, *, label: str) -> dict[str, Any]:
    with _open_regular(path, label=label) as source:
        before = os.fstat(source.fileno())
        if not 1 <= before.st_size <= MAXIMUM_JSON_BYTES:
            _fail(f"{label} size is outside its bound")
        raw = source.read(MAXIMUM_JSON_BYTES + 1)
        after = os.fstat(source.fileno())
    if len(raw) != before.st_size or _identity(before) != _identity(after):
        _fail(f"{label} changed while it was read")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletResidentQMajorStreamError(
            f"invalid {label}"
        ) from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail(f"{label} is not canonical JSON")
    return value


def _validate_output_stream(
    path: Path,
    schedule: ParsedScheduleManifest,
    plan: StreamPlan,
) -> tuple[str, int]:
    if (
        plan.schedule_classification
        == SCHEDULE_CLASSIFICATION_FULL_SOURCE
    ):
        _fail(
            "full-source output requires a back-pressured semantic/sign "
            "consumer, not regular-file validation"
        )
    expected_size = (
        plan.target_count * TGDAFFI_HEADER.size
        + plan.value_count * COMPLEX_INTERVAL.size
    )
    with _open_regular(
        path, label="resident stream TGDAFFI1 output"
    ) as source:
        before = os.fstat(source.fileno())
        if before.st_size != expected_size:
            _fail("resident stream output size differs")
        digest = hashlib.sha256()
        for target in iter_stream_targets(schedule, plan):
            raw_header = _read_exact(
                source, TGDAFFI_HEADER.size, "resident output header"
            )
            digest.update(raw_header)
            header = TGDAFFI_HEADER.unpack(raw_header)
            component_count = len(canonical_component_orders(target.q))
            group_order = _group_order(target.q)
            value_count = target.batch_count * group_order
            if header != (
                TGDAFFI_MAGIC,
                TGDAFFI_FORMAT_VERSION,
                target.q,
                component_count,
                target.batch_count,
                group_order,
                target.first_t_index * SOURCE_SAMPLE_NUMERATOR,
                SOURCE_SAMPLE_DENOMINATOR,
                SOURCE_SAMPLE_NUMERATOR,
                value_count,
                0,
            ):
                _fail("resident output header differs from its target")
            remaining = value_count
            while remaining:
                take = min(remaining, 32_768)
                raw_values = _read_exact(
                    source,
                    take * COMPLEX_INTERVAL.size,
                    "resident output values",
                )
                digest.update(raw_values)
                for values in COMPLEX_INTERVAL.iter_unpack(raw_values):
                    if (
                        not all(
                            math.isfinite(endpoint)
                            for endpoint in values
                        )
                        or values[0] > values[1]
                        or values[2] > values[3]
                    ):
                        _fail("resident output interval is malformed")
                remaining -= take
        if source.read(1) != b"":
            _fail("resident output has trailing bytes")
        after = os.fstat(source.fileno())
    if _identity(before) != _identity(after):
        _fail("resident output changed while replayed")
    return digest.hexdigest(), before.st_size


def validate_streamed_cuda_summary(
    summary_path: Path,
    schedule: ParsedScheduleManifest,
    rows: ParsedRowArtifact,
    sidecars: ParsedSidecarArtifact,
    *,
    output_sha256: str,
    output_size_bytes: int,
) -> dict[str, Any]:
    """Bind a piped CUDA run to both independent input-artifact replays.

    The downstream process that actually consumed stdout supplies its observed
    input digest.  This is the source-scale validation path: unlike
    :func:`validate_cuda_summary`, it never asks the supervisor to materialize
    the TGDAFFI1 stream in a regular file.
    """

    if rows.plan != sidecars.plan:
        _fail("resident summary inputs use different plans")
    plan = rows.plan
    checked_output_sha256 = _digest(
        output_sha256, "resident streamed output"
    )
    checked_output_size = _integer(
        output_size_bytes,
        "resident streamed output size",
    )
    expected_output_size = (
        plan.target_count * TGDAFFI_HEADER.size
        + plan.value_count * COMPLEX_INTERVAL.size
    )
    if checked_output_size != expected_output_size:
        _fail("resident streamed output size differs from its exact plan")
    value = _canonical_json(
        summary_path, label="resident stream CUDA summary"
    )
    seed_record_count = value.get("seed_record_count")
    if (
        isinstance(seed_record_count, bool)
        or not isinstance(seed_record_count, int)
        or seed_record_count <= 0
    ):
        _fail("resident stream summary seed count is malformed")
    memory = explicit_device_memory_formula(
        plan, seed_record_count=seed_record_count
    )
    buffers = explicit_executor_buffer_formula(
        plan, seed_record_count=seed_record_count
    )
    expected: dict[str, Any] = {
        "algorithm_id": CUDA_ALGORITHM_ID,
        "candidate_report_sha256": CANDIDATE_REPORT_SHA256,
        "canonical_descriptor_input_bytes": 0,
        "classification": (
            "source_shaped_resident_qmajor_stream_cuda_"
            "not_source_or_zero_closure"
        ),
        "completed_l_zero_state_validated": False,
        "coverage_mode": plan.coverage_mode,
        "cuda_event_create_count": 2,
        "cuda_event_reuse_count": plan.target_count,
        "descriptor_h2d_upload_count": plan.active_q_count,
        "descriptor_reconstruction_count": plan.active_q_count,
        "device_memory_formula_exact_for_explicit_allocations": True,
        "device_memory_known_allocation_bytes": memory[
            "known_allocation_bytes"
        ],
        "device_memory_maximum_descriptor_bytes": memory[
            "maximum_descriptor_bytes"
        ],
        "device_memory_maximum_factor_bytes": memory[
            "maximum_factor_bytes"
        ],
        "device_memory_maximum_output_bytes": memory[
            "maximum_output_bytes"
        ],
        "device_memory_maximum_tail_bytes": memory[
            "maximum_tail_bytes"
        ],
        "device_memory_preflight_passed": True,
        "device_memory_resident_lattice_bytes": memory[
            "resident_lattice_bytes"
        ],
        "device_memory_safety_reserve_bytes": (
            DEVICE_MEMORY_SAFETY_RESERVE_BYTES
        ),
        "device_memory_seed_bytes": memory["seed_records_bytes"],
        "disk_row_artifact_bytes": rows.input_size_bytes,
        "disk_sidecar_artifact_bytes": sidecars.input_size_bytes,
        "disk_total_input_artifact_bytes": (
            rows.input_size_bytes + sidecars.input_size_bytes
        ),
        "external_atom_discharged": False,
        "full_source_pipe_or_socket_output_required": True,
        "full_source_regular_file_output_refused": True,
        "full_source_semantic_sign_reducer_integrated": False,
        "full_phase_host_duplicate_required": False,
        "h100_source_phase_completed": False,
        "lane_chain_sha256": sidecars.lane_chain_sha256,
        "lane_count": len(plan.lanes),
        "lane_partition_sha256": plan.lane_partition_sha256,
        "lattice_device_allocation_count": 1,
        "lattice_h2d_upload_bytes": plan.row_count * ROW_PAYLOAD_BYTES,
        "lattice_h2d_upload_call_count": plan.row_count,
        "loaded_first_t_index": plan.loaded_first_t_index,
        "loaded_t_index_stop_exclusive": (
            plan.loaded_t_index_stop_exclusive
        ),
        "maximum_host_descriptor_staging_bytes": buffers[
            "host_descriptor_staging_bytes"
        ],
        "maximum_host_output_staging_bytes": buffers[
            "host_output_staging_bytes"
        ],
        "maximum_host_payload_staging_bytes": buffers[
            "host_payload_staging_bound_bytes"
        ],
        "maximum_host_row_staging_bytes": ROW_PAYLOAD_BYTES,
        "maximum_host_sidecar_staging_bytes": buffers[
            "host_sidecar_staging_bytes"
        ],
        "maximum_source_phase_projected_output_stream_bytes": (
            MAXIMUM_PROJECTED_PHASE_OUTPUT_BYTES
        ),
        "output_sha256": checked_output_sha256,
        "output_size_bytes": checked_output_size,
        "output_transport": "stdout_backpressured_target_stream",
        "phase_index": plan.phase_index,
        "phase_plan_sha256": plan.phase_plan_sha256,
        "production_run_completed": False,
        "projected_output_stream_bytes": checked_output_size,
        "recovery_seed_artifact_sha256": rows.recovery_seed_sha256,
        "row_artifact_sha256": rows.input_sha256,
        "row_artifact_size_bytes": rows.input_size_bytes,
        "row_chain_sha256": rows.row_chain_sha256,
        "row_count": plan.row_count,
        "schedule_classification": plan.schedule_classification,
        "schedule_execution_order_sha256": (
            schedule.execution_order_sha256
        ),
        "schedule_manifest_sha256": schedule.manifest_sha256,
        "schema": SUMMARY_SCHEMA,
        "schema_version": FORMAT_VERSION,
        "sidecar_artifact_sha256": sidecars.input_sha256,
        "sidecar_artifact_size_bytes": sidecars.input_size_bytes,
        "sidecar_source_sha256": sidecars.sidecar_source_sha256,
        "source_contract_sha256": rows.source_contract_sha256,
        "source_h100_fit_claimed": False,
        "source_output_materialization_feasible_claimed": False,
        "source_scale_run": False,
        "stdout_backpressure_supported": True,
        "target_chain_sha256": sidecars.target_chain_sha256,
        "target_count": plan.target_count,
        "target_row_reference_count": (
            plan.target_row_reference_count
        ),
        "transcendental_device_calls": 0,
        "trusted_execution_attested": False,
        "value_count": plan.value_count,
        "zero_completeness_claimed": False,
    }
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            _fail(f"resident stream CUDA summary field differs: {key}")
    for key in (
        "device_memory_free_bytes_before_allocations",
        "elapsed_kernel_nanoseconds",
    ):
        observed = value.get(key)
        if (
            isinstance(observed, bool)
            or not isinstance(observed, int)
            or observed < 0
        ):
            _fail(f"resident stream CUDA summary field differs: {key}")
    if (
        memory["required_free_device_bytes"]
        > value["device_memory_free_bytes_before_allocations"]
    ):
        _fail("resident stream CUDA memory preflight differs")
    if set(value) != set(expected) | {
        "device_memory_free_bytes_before_allocations",
        "elapsed_kernel_nanoseconds",
        "seed_record_count",
    }:
        _fail("resident stream CUDA summary fields differ")
    return value


def validate_cuda_summary(
    summary_path: Path,
    schedule: ParsedScheduleManifest,
    rows: ParsedRowArtifact,
    sidecars: ParsedSidecarArtifact,
    output_path: Path,
) -> dict[str, Any]:
    """Bind a bounded regular-file KAT to the independent stream replay."""

    if rows.plan != sidecars.plan:
        _fail("resident summary inputs use different plans")
    output_sha256, output_size = _validate_output_stream(
        output_path, schedule, rows.plan
    )
    return validate_streamed_cuda_summary(
        summary_path,
        schedule,
        rows,
        sidecars,
        output_sha256=output_sha256,
        output_size_bytes=output_size,
    )


def compare_bounded_equivalence(
    plan: StreamPlan,
    stream_summary: dict[str, Any],
    *,
    current_resident_input_bytes: int,
    formulaic_input_bytes: int,
    current_resident_kernel_nanoseconds: int,
    formulaic_kernel_nanoseconds: int,
    expected_output_sha256: str,
) -> dict[str, Any]:
    """Compare the source-shaped seam with both bounded predecessors."""

    resident_bytes = _integer(
        current_resident_input_bytes,
        "current resident input bytes",
        minimum=1,
    )
    formulaic_bytes = _integer(
        formulaic_input_bytes,
        "formulaic input bytes",
        minimum=1,
    )
    resident_runtime = _integer(
        current_resident_kernel_nanoseconds,
        "current resident runtime",
    )
    formulaic_runtime = _integer(
        formulaic_kernel_nanoseconds,
        "formulaic runtime",
    )
    output_sha256 = _digest(
        expected_output_sha256, "equivalent output"
    )
    stream_bytes = (
        plan.row_input_size_bytes + plan.sidecar_input_size_bytes
    )
    if (
        stream_summary.get("output_sha256") != output_sha256
        or stream_summary.get("row_artifact_size_bytes")
        != plan.row_input_size_bytes
        or stream_summary.get("sidecar_artifact_size_bytes")
        != plan.sidecar_input_size_bytes
    ):
        _fail("resident stream comparison identities differ")
    stream_runtime = _integer(
        stream_summary.get("elapsed_kernel_nanoseconds"),
        "resident stream runtime",
    )
    return {
        "schema": COMPARISON_SCHEMA,
        "schema_version": FORMAT_VERSION,
        "algorithm_id": CUDA_ALGORITHM_ID,
        "target_count": plan.target_count,
        "unique_row_count": plan.row_count,
        "target_row_reference_count": plan.target_row_reference_count,
        "stream_row_artifact_bytes": plan.row_input_size_bytes,
        "stream_sidecar_artifact_bytes": plan.sidecar_input_size_bytes,
        "stream_total_input_bytes": stream_bytes,
        "current_resident_input_bytes": resident_bytes,
        "formulaic_row_repeated_input_bytes": formulaic_bytes,
        "stream_minus_current_resident_input_bytes": (
            stream_bytes - resident_bytes
        ),
        "bytes_saved_vs_formulaic": formulaic_bytes - stream_bytes,
        "stream_elapsed_kernel_nanoseconds": stream_runtime,
        "current_resident_elapsed_kernel_nanoseconds": (
            resident_runtime
        ),
        "formulaic_elapsed_kernel_nanoseconds": formulaic_runtime,
        "stream_runtime_ratio_over_current_resident": (
            stream_runtime / resident_runtime
            if resident_runtime
            else None
        ),
        "stream_runtime_ratio_over_formulaic": (
            stream_runtime / formulaic_runtime
            if formulaic_runtime
            else None
        ),
        "exact_output_sha256": output_sha256,
        "exact_output_bytes_equal": True,
        "source_scale_run": False,
        "h100_source_phase_completed": False,
        "production_run_completed": False,
        "trusted_execution_attested": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }


def capability() -> dict[str, Any]:
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_resident_qmajor_stream."
            "capability.v1"
        ),
        "algorithm_id": ALGORITHM_ID,
        "source_shaped_ten_phase_geometry_implemented": True,
        "full_source_schedule_parser_accepted": True,
        "bounded_projection_cuda_kat_implemented": True,
        "bounded_projection_cuda_kat_completed": True,
        "incremental_one_row_host_staging_implemented": True,
        "single_preallocated_device_lattice_buffer_implemented": True,
        "bounded_q_lane_sidecar_stream_implemented": True,
        "descriptor_reuse_by_actual_q_implemented": True,
        "cuda_event_reuse_implemented": True,
        "exact_ordered_commitments_implemented": True,
        "exact_explicit_device_memory_formula_implemented": True,
        "separate_host_device_disk_buffer_formula_implemented": True,
        "phase_cuts": list(PHASE_CUTS),
        "phase_count": len(PHASE_CUTS) - 1,
        "maximum_rows_per_phase": MAXIMUM_ROWS,
        "maximum_q_per_lane": MAXIMUM_Q_PER_LANE,
        "maximum_targets_per_lane": MAXIMUM_TARGETS_PER_LANE,
        "maximum_lanes": MAXIMUM_LANES,
        "maximum_batch_count": MAXIMUM_BATCH_COUNT,
        "maximum_row_artifact_bytes": MAXIMUM_ROW_ARTIFACT_BYTES,
        "maximum_sidecar_artifact_bytes": (
            MAXIMUM_SIDECAR_INPUT_BYTES
        ),
        "maximum_source_phase_projected_output_stream_bytes": (
            MAXIMUM_PROJECTED_PHASE_OUTPUT_BYTES
        ),
        "candidate_report_sha256": CANDIDATE_REPORT_SHA256,
        "device_memory_safety_reserve_bytes": (
            DEVICE_MEMORY_SAFETY_RESERVE_BYTES
        ),
        "source_phase_execution_completed": False,
        "source_scale_run_completed": False,
        "source_h100_fit_claimed": False,
        "source_output_materialization_feasible_claimed": False,
        "full_source_regular_file_output_supported": False,
        "full_source_pipe_or_socket_output_required": True,
        "full_source_semantic_sign_reducer_integrated": False,
        "stdout_backpressured_target_stream_implemented": True,
        "h100_source_phase_completed": False,
        "production_run_completed": False,
        "trusted_execution_attested": False,
        "completed_l_zero_state_validated": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "BOUNDED_PROJECTION_COVERAGE",
    "CANDIDATE_REPORT_SHA256",
    "DEVICE_MEMORY_SAFETY_RESERVE_BYTES",
    "DirichletResidentQMajorStreamError",
    "EXACT_CANDIDATE_PHASE_COVERAGE",
    "LANE_FOOTER",
    "LANE_HEADER",
    "MAXIMUM_BATCH_COUNT",
    "MAXIMUM_LANES",
    "MAXIMUM_OUTPUT_PHASE_TARGETS",
    "MAXIMUM_Q_PER_LANE",
    "MAXIMUM_ROW_ARTIFACT_BYTES",
    "MAXIMUM_ROWS",
    "MAXIMUM_SIDECAR_INPUT_BYTES",
    "MAXIMUM_PROJECTED_PHASE_OUTPUT_BYTES",
    "MAXIMUM_TARGETS_PER_LANE",
    "PHASE_CUTS",
    "QLane",
    "ROW_ARTIFACT_FOOTER",
    "ROW_ARTIFACT_HEADER",
    "STREAM_FOOTER",
    "STREAM_HEADER",
    "StreamPlan",
    "StreamTarget",
    "TARGET_HEADER",
    "build_stream_plan",
    "canonical_q_lanes",
    "capability",
    "compare_bounded_equivalence",
    "explicit_device_memory_formula",
    "explicit_executor_buffer_formula",
    "iter_stream_targets",
    "lane_partition_digest",
    "phase_bounds",
    "phase_plan_digest",
    "replay_row_artifact",
    "replay_sidecar_artifact",
    "validate_cuda_summary",
    "validate_streamed_cuda_summary",
    "write_row_artifact",
    "write_sidecar_artifact",
]
