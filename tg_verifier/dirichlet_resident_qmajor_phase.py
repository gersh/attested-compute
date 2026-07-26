# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded resident-row phase for formulaic q-major seeded CUDA execution.

One phase carries at most 64 contiguous t-major lattice rows exactly once,
followed by sidecars for at most 64 active scheduled q targets.  The compiled
worker uploads the row shard once, reconstructs clipped formulaic targets in
the authenticated nonmonotone q order, caches descriptors by actual q, and
emits ordinary TGDAFFI1 frames.

This is a bounded implementation/KAT seam.  It does not populate a source
spool, execute the proposed multi-H100 source shards, attest execution,
validate completed-L zeros or a Turing count, or discharge an external atom.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import tempfile
from typing import Any, BinaryIO, Callable, NoReturn

from tg_verifier.dirichlet_allchars_q_scheduler import (
    BOUNDED_CLASSIFICATION,
    ParsedScheduleManifest,
)
from tg_verifier.dirichlet_allchars_stage import (
    COMPLEX_INTERVAL,
    FORMAT_VERSION as TGDAFFI_FORMAT_VERSION,
    INPUT_HEADER as TGDAFFI_HEADER,
    INPUT_MAGIC as TGDAFFI_MAGIC,
    canonical_component_orders,
    canonical_residue_order,
)
from tg_verifier.dirichlet_formulaic_qmajor_cursor import (
    FormulaicTarget,
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
from tg_verifier.dirichlet_largeq_batch import FRAME_FACTOR
from tg_verifier.dirichlet_tmajor_cuda_block import (
    ROW_HEADER,
    ROW_MAGIC,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-dirichlet-resident-qmajor-phase-input-v1"
CUDA_ALGORITHM_ID = "platt-dirichlet-resident-qmajor-phase-seeded-cuda-v1"
STREAM_SCHEMA = (
    "sparkinterval.tg.dirichlet_resident_qmajor_phase.stream.v1"
)
SUMMARY_SCHEMA = (
    "sparkinterval.tg.dirichlet_resident_qmajor_phase_cuda.summary.v1"
)
COMPARISON_SCHEMA = (
    "sparkinterval.tg.dirichlet_resident_qmajor_phase.comparison.v1"
)

FORMAT_VERSION = 1
SCHEDULE_CLASSIFICATION_BOUNDED = 0
MAXIMUM_ROWS = 64
MAXIMUM_TARGETS = 64
MAXIMUM_VALUES = 1 << 24
MAXIMUM_INPUT_BYTES = 80 * 1024 * 1024
MAXIMUM_OUTPUT_BYTES = (
    MAXIMUM_VALUES * COMPLEX_INTERVAL.size
    + MAXIMUM_TARGETS * TGDAFFI_HEADER.size
)
MAXIMUM_SCHEDULE_RECORDS = 256
DEVICE_MEMORY_SAFETY_RESERVE_BYTES = 512 * 1024 * 1024
MAXIMUM_JSON_BYTES = 4 * 1024 * 1024
TMAJOR_ROW_FORMAT_VERSION = 2

HEADER_MAGIC = b"TGDQRPH1"
TARGET_MAGIC = b"TGDQRPQ1"
FOOTER_MAGIC = b"TGDQRPF1"
PLAN_DOMAIN = b"TG_DIRICHLET_RESIDENT_QMAJOR_PHASE_PLAN_V1"
CHAIN_DOMAIN = b"TG_DIRICHLET_RESIDENT_QMAJOR_PHASE_CHAIN_V1"
ROW_BINDING_DOMAIN = (
    b"sparkinterval/tg/dirichlet-resident-qmajor-phase/rows/v1\0"
)
SIDECAR_DOMAIN = (
    b"sparkinterval/tg/dirichlet-resident-qmajor-phase/sidecar/v1\0"
)
# The two transport-binding domains include the NUL because C++ hashes
# sizeof(char[]).  The binary plan/chain domains deliberately exclude it.

PHASE_HEADER = struct.Struct(
    "<8sIIIIIIIIQQQQQQQQQQQ"
    "32s32s32s32s32s32s32s32s"
)
PHASE_TARGET = struct.Struct(
    "<8sIIQIIIIIIQQQQ32s32s"
)
PHASE_FOOTER = struct.Struct(
    "<8sIIQQQQQQQQQ32s32s32s32s"
)

assert PHASE_HEADER.size == 384
assert PHASE_TARGET.size == 144
assert PHASE_FOOTER.size == 216
assert ROW_HEADER.size == 64
assert ROW_PAYLOAD_BYTES == 1_048_576
assert FRAME_FACTOR.size == 32

HEX = frozenset("0123456789abcdef")
RowProvider = Callable[[int], bytes]
SidecarProvider = Callable[[FormulaicTarget], tuple[bytes, bytes]]


class DirichletResidentQMajorPhaseError(RuntimeError):
    """A resident phase, execution summary, or comparison failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletResidentQMajorPhaseError(message)


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


def _open_regular(path: Path, *, label: str) -> BinaryIO:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as error:
        raise DirichletResidentQMajorPhaseError(
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


def _bounded_read(path: Path, maximum: int, *, label: str) -> bytes:
    maximum = _integer(maximum, f"{label} bound", minimum=1, maximum=1 << 32)
    with _open_regular(path, label=label) as source:
        before = os.fstat(source.fileno())
        if not 1 <= before.st_size <= maximum:
            _fail(f"{label} size is outside [1,{maximum}]")
        raw = source.read(maximum + 1)
        after = os.fstat(source.fileno())
    if len(raw) != before.st_size or _identity(before) != _identity(after):
        _fail(f"{label} changed while it was read")
    return raw


def _atomic_write(
    path: Path, write: Callable[[BinaryIO], dict[str, Any]]
) -> dict[str, Any]:
    if path.exists() or path.is_symlink():
        _fail(f"refusing to replace immutable output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            result = write(output)
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
    input_digest: Any,
    stream_digest: Any | None = None,
) -> None:
    written = output.write(raw)
    if written != len(raw):
        _fail("cannot write resident q-major phase")
    input_digest.update(raw)
    if stream_digest is not None:
        stream_digest.update(raw)


def phase_plan_digest(
    schedule: ParsedScheduleManifest,
    *,
    start_execution_q_index: int,
    stop_execution_q_index: int,
    phase_index: int,
    first_t_index: int,
    t_index_stop_exclusive: int,
) -> str:
    """Return the exact Python/C++ binary phase-plan identity."""

    if schedule.classification != BOUNDED_CLASSIFICATION:
        _fail("resident q-major phase currently requires a bounded schedule")
    count = len(schedule.execution_records)
    start = _integer(
        start_execution_q_index,
        "start execution q index",
        maximum=count,
    )
    stop = _integer(
        stop_execution_q_index,
        "stop execution q index",
        maximum=count,
    )
    phase_index = _integer(
        phase_index, "phase index", maximum=(1 << 32) - 1
    )
    first_t = _integer(
        first_t_index, "phase first t", maximum=(1 << 32) - 1
    )
    stop_t = _integer(
        t_index_stop_exclusive,
        "phase t stop",
        minimum=1,
        maximum=(1 << 32) - 1,
    )
    if (
        start >= stop
        or stop - start > MAXIMUM_SCHEDULE_RECORDS
        or first_t >= stop_t
        or stop_t - first_t > MAXIMUM_ROWS
    ):
        _fail("resident q-major phase plan is outside its fixed bound")
    digest = hashlib.sha256(PLAN_DOMAIN)
    digest.update(bytes.fromhex(schedule.manifest_sha256))
    digest.update(bytes.fromhex(schedule.execution_order_sha256))
    digest.update(
        struct.pack(
            "<QQIIIII",
            start,
            stop,
            phase_index,
            first_t,
            stop_t,
            MAXIMUM_ROWS,
            MAXIMUM_TARGETS,
        )
    )
    return digest.hexdigest()


def active_phase_targets(
    schedule: ParsedScheduleManifest,
    *,
    start_execution_q_index: int,
    stop_execution_q_index: int,
    phase_index: int,
    first_t_index: int,
    t_index_stop_exclusive: int,
) -> tuple[FormulaicTarget, ...]:
    """Reconstruct active q targets and clip their exclusive t stops."""

    phase_plan_digest(
        schedule,
        start_execution_q_index=start_execution_q_index,
        stop_execution_q_index=stop_execution_q_index,
        phase_index=phase_index,
        first_t_index=first_t_index,
        t_index_stop_exclusive=t_index_stop_exclusive,
    )
    records = schedule.execution_records[
        start_execution_q_index:stop_execution_q_index
    ]
    if max(record.t_index_count for record in records) < t_index_stop_exclusive:
        _fail("resident phase contains a row unused by every scheduled q")
    targets: list[FormulaicTarget] = []
    for execution_q_index in range(
        start_execution_q_index, stop_execution_q_index
    ):
        record = schedule.execution_records[execution_q_index]
        active_stop = min(
            record.t_index_count, t_index_stop_exclusive
        )
        if active_stop <= first_t_index:
            continue
        targets.append(
            FormulaicTarget(
                execution_q_index=execution_q_index,
                q=record.q,
                lane_index=phase_index,
                first_t_index=first_t_index,
                t_index_stop_exclusive=active_stop,
            )
        )
    if not 1 <= len(targets) <= MAXIMUM_TARGETS:
        _fail("resident phase active target count is outside its bound")
    return tuple(targets)


def _validate_sidecars(
    target: FormulaicTarget, factors: bytes, tails: bytes
) -> None:
    if (
        len(factors) != target.batch_count * FRAME_FACTOR.size
        or len(tails) != target.batch_count * 8
    ):
        _fail("resident phase factor or tail length differs")
    for factor in FRAME_FACTOR.iter_unpack(factors):
        if (
            not all(math.isfinite(value) for value in factor)
            or factor[0] > factor[1]
            or factor[2] > factor[3]
        ):
            _fail("resident phase factor is malformed")
    for (tail,) in struct.iter_unpack("<d", tails):
        if not math.isfinite(tail) or tail < 0:
            _fail("resident phase Taylor tail is malformed")


def _row_binding(
    *,
    lattice_source_sha256: str,
    phase_plan_sha256: str,
    rows: tuple[tuple[int, bytes, bytes], ...],
) -> bytes:
    digest = hashlib.sha256(ROW_BINDING_DOMAIN)
    digest.update(bytes.fromhex(lattice_source_sha256))
    digest.update(bytes.fromhex(phase_plan_sha256))
    for t_index, _payload, payload_sha256 in rows:
        digest.update(struct.pack("<Q", t_index))
        digest.update(payload_sha256)
    return digest.digest()


def _sidecar_binding(
    *,
    sidecar_source_sha256: str,
    phase_plan_sha256: str,
    target: FormulaicTarget,
    factors: bytes,
    tails: bytes,
) -> bytes:
    digest = hashlib.sha256(SIDECAR_DOMAIN)
    digest.update(bytes.fromhex(sidecar_source_sha256))
    digest.update(bytes.fromhex(phase_plan_sha256))
    digest.update(target.packed())
    digest.update(factors)
    digest.update(tails)
    return digest.digest()


def _initial_chain(phase_plan_sha256: str) -> bytes:
    digest = hashlib.sha256(CHAIN_DOMAIN)
    digest.update(bytes.fromhex(phase_plan_sha256))
    return digest.digest()


def _advance_chain(previous: bytes, target: FormulaicTarget) -> bytes:
    digest = hashlib.sha256(CHAIN_DOMAIN)
    digest.update(previous)
    digest.update(target.packed())
    return digest.digest()


@dataclass(frozen=True)
class ResidentPhaseFrame:
    target: FormulaicTarget
    component_count: int
    group_order: int
    value_count: int
    factors: bytes
    tails: bytes


@dataclass(frozen=True)
class ParsedResidentPhase:
    path: Path
    schedule_manifest_sha256: str
    schedule_source_roster_sha256: str
    schedule_execution_order_sha256: str
    phase_plan_sha256: str
    source_contract_sha256: str
    lattice_source_sha256: str
    recovery_seed_sha256: str
    sidecar_source_sha256: str
    phase_index: int
    start_execution_q_index: int
    stop_execution_q_index: int
    first_t_index: int
    t_index_stop_exclusive: int
    rows: tuple[bytes, ...]
    frames: tuple[ResidentPhaseFrame, ...]
    target_chain_sha256: str
    row_stream_sha256: str
    target_stream_sha256: str
    input_sha256: str
    input_size_bytes: int
    target_row_reference_count: int
    value_count: int


def write_resident_qmajor_phase(
    path: Path,
    schedule: ParsedScheduleManifest,
    *,
    phase_index: int,
    first_t_index: int,
    t_index_stop_exclusive: int,
    recovery_seed_sha256: str,
    source_contract_sha256: str,
    lattice_source_sha256: str,
    sidecar_source_sha256: str,
    row_provider: RowProvider,
    sidecar_provider: SidecarProvider,
    start_execution_q_index: int = 0,
    stop_execution_q_index: int | None = None,
) -> dict[str, Any]:
    """Build one immutable, explicitly bounded resident phase artifact."""

    stop = (
        len(schedule.execution_records)
        if stop_execution_q_index is None
        else stop_execution_q_index
    )
    plan_sha256 = phase_plan_digest(
        schedule,
        start_execution_q_index=start_execution_q_index,
        stop_execution_q_index=stop,
        phase_index=phase_index,
        first_t_index=first_t_index,
        t_index_stop_exclusive=t_index_stop_exclusive,
    )
    targets = active_phase_targets(
        schedule,
        start_execution_q_index=start_execution_q_index,
        stop_execution_q_index=stop,
        phase_index=phase_index,
        first_t_index=first_t_index,
        t_index_stop_exclusive=t_index_stop_exclusive,
    )
    for value, label in (
        (recovery_seed_sha256, "recovery seed"),
        (source_contract_sha256, "source contract"),
        (lattice_source_sha256, "lattice source"),
        (sidecar_source_sha256, "sidecar source"),
    ):
        _digest(value, label)

    rows: list[tuple[int, bytes, bytes]] = []
    for t_index in range(first_t_index, t_index_stop_exclusive):
        payload = row_provider(t_index)
        if not isinstance(payload, bytes):
            _fail("resident phase row provider did not return bytes")
        validate_lattice_row(payload)
        rows.append((t_index, payload, hashlib.sha256(payload).digest()))
    checked_rows = tuple(rows)
    row_bindings_sha256 = _row_binding(
        lattice_source_sha256=lattice_source_sha256,
        phase_plan_sha256=plan_sha256,
        rows=checked_rows,
    )

    prepared_targets: list[
        tuple[
            FormulaicTarget,
            int,
            int,
            int,
            bytes,
            bytes,
            bytes,
        ]
    ] = []
    value_count = 0
    sidecar_bytes = 0
    target_rows = 0
    for target in targets:
        factors, tails = sidecar_provider(target)
        if not isinstance(factors, bytes) or not isinstance(tails, bytes):
            _fail("resident phase sidecar provider did not return bytes")
        _validate_sidecars(target, factors, tails)
        component_count = len(canonical_component_orders(target.q))
        group_order = len(canonical_residue_order(target.q))
        values = target.batch_count * group_order
        value_count += values
        sidecar_bytes += len(factors) + len(tails)
        target_rows += target.batch_count
        prepared_targets.append(
            (
                target,
                component_count,
                group_order,
                values,
                factors,
                tails,
                _sidecar_binding(
                    sidecar_source_sha256=sidecar_source_sha256,
                    phase_plan_sha256=plan_sha256,
                    target=target,
                    factors=factors,
                    tails=tails,
                ),
            )
        )
    if value_count > MAXIMUM_VALUES:
        _fail("resident phase value count exceeds its fixed bound")
    input_size = (
        PHASE_HEADER.size
        + len(checked_rows) * (ROW_HEADER.size + ROW_PAYLOAD_BYTES)
        + len(prepared_targets) * PHASE_TARGET.size
        + sidecar_bytes
        + PHASE_FOOTER.size
    )
    if input_size > MAXIMUM_INPUT_BYTES:
        _fail("resident phase input exceeds its fixed byte bound")

    def write(output: BinaryIO) -> dict[str, Any]:
        input_digest = hashlib.sha256()
        row_stream = hashlib.sha256()
        target_stream = hashlib.sha256()
        header = PHASE_HEADER.pack(
            HEADER_MAGIC,
            FORMAT_VERSION,
            SCHEDULE_CLASSIFICATION_BOUNDED,
            MAXIMUM_ROWS,
            MAXIMUM_TARGETS,
            phase_index,
            len(checked_rows),
            len(prepared_targets),
            0,
            start_execution_q_index,
            stop,
            first_t_index,
            t_index_stop_exclusive,
            value_count,
            ROW_HEADER.size,
            ROW_PAYLOAD_BYTES,
            PHASE_TARGET.size,
            FRAME_FACTOR.size,
            8,
            input_size,
            bytes.fromhex(schedule.manifest_sha256),
            bytes.fromhex(schedule.execution_order_sha256),
            bytes.fromhex(plan_sha256),
            bytes.fromhex(source_contract_sha256),
            bytes.fromhex(lattice_source_sha256),
            bytes.fromhex(recovery_seed_sha256),
            bytes.fromhex(sidecar_source_sha256),
            row_bindings_sha256,
        )
        _emit(output, header, input_digest=input_digest)
        for t_index, payload, payload_sha256 in checked_rows:
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
                input_digest=input_digest,
                stream_digest=row_stream,
            )
            _emit(
                output,
                payload,
                input_digest=input_digest,
                stream_digest=row_stream,
            )

        chain = _initial_chain(plan_sha256)
        for (
            target,
            component_count,
            group_order,
            values,
            factors,
            tails,
            sidecar_sha256,
        ) in prepared_targets:
            target_header = PHASE_TARGET.pack(
                TARGET_MAGIC,
                FORMAT_VERSION,
                0,
                target.execution_q_index,
                target.q,
                target.lane_index,
                target.first_t_index,
                target.t_index_stop_exclusive,
                target.batch_count,
                component_count,
                group_order,
                values,
                len(factors),
                len(tails),
                bytes.fromhex(target.digest()),
                sidecar_sha256,
            )
            _emit(
                output,
                target_header,
                input_digest=input_digest,
                stream_digest=target_stream,
            )
            _emit(
                output,
                factors,
                input_digest=input_digest,
                stream_digest=target_stream,
            )
            _emit(
                output,
                tails,
                input_digest=input_digest,
                stream_digest=target_stream,
            )
            chain = _advance_chain(chain, target)

        bytes_before_footer = output.tell()
        footer = PHASE_FOOTER.pack(
            FOOTER_MAGIC,
            FORMAT_VERSION,
            0,
            len(checked_rows),
            len(prepared_targets),
            target_rows,
            value_count,
            sidecar_bytes,
            bytes_before_footer,
            len(prepared_targets),
            len(prepared_targets),
            1,
            chain,
            row_stream.digest(),
            target_stream.digest(),
            b"\0" * 32,
        )
        _emit(output, footer, input_digest=input_digest)
        return {
            "target_chain_sha256": chain.hex(),
            "row_stream_sha256": row_stream.hexdigest(),
            "target_stream_sha256": target_stream.hexdigest(),
            "input_sha256": input_digest.hexdigest(),
            "input_size_bytes": input_size,
            "row_count": len(checked_rows),
            "target_count": len(prepared_targets),
            "target_row_reference_count": target_rows,
            "value_count": value_count,
            "sidecar_bytes": sidecar_bytes,
        }

    streamed = _atomic_write(path, write)
    body: dict[str, Any] = {
        "schema": STREAM_SCHEMA,
        "schema_version": FORMAT_VERSION,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "bounded_resident_qmajor_phase_input_not_source_execution"
        ),
        "schedule_manifest_sha256": schedule.manifest_sha256,
        "schedule_execution_order_sha256": (
            schedule.execution_order_sha256
        ),
        "phase_plan_sha256": plan_sha256,
        "source_contract_sha256": source_contract_sha256,
        "lattice_source_sha256": lattice_source_sha256,
        "recovery_seed_artifact_sha256": recovery_seed_sha256,
        "sidecar_source_sha256": sidecar_source_sha256,
        "phase_index": phase_index,
        "start_execution_q_index": start_execution_q_index,
        "stop_execution_q_index": stop,
        "first_t_index": first_t_index,
        "t_index_stop_exclusive": t_index_stop_exclusive,
        **streamed,
        "lattice_rows_serialized_once": True,
        "canonical_descriptor_input_bytes": 0,
        "serialized_control_records_required": 0,
        "bounded_real_cuda_kat_completed": False,
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


def replay_resident_qmajor_phase(
    path: Path,
    schedule: ParsedScheduleManifest,
    *,
    expected_input_sha256: str | None = None,
) -> ParsedResidentPhase:
    """Independently authenticate every byte and reconstruct every target."""

    raw = _bounded_read(
        path, MAXIMUM_INPUT_BYTES, label="resident q-major phase"
    )
    input_sha256 = hashlib.sha256(raw).hexdigest()
    if (
        expected_input_sha256 is not None
        and input_sha256
        != _digest(expected_input_sha256, "resident phase input")
    ):
        _fail("resident phase differs from its external input pin")
    if len(raw) < PHASE_HEADER.size + PHASE_FOOTER.size:
        _fail("resident phase is too short")
    fields = PHASE_HEADER.unpack_from(raw)
    (
        magic,
        version,
        classification,
        maximum_rows,
        maximum_targets,
        phase_index,
        row_count,
        target_count,
        reserved,
        start_q,
        stop_q,
        first_t,
        stop_t,
        value_count,
        row_header_bytes,
        row_payload_bytes,
        target_header_bytes,
        factor_record_bytes,
        tail_record_bytes,
        input_size,
        schedule_sha256,
        execution_sha256,
        plan_sha256,
        source_contract_sha256,
        lattice_source_sha256,
        recovery_seed_sha256,
        sidecar_source_sha256,
        row_bindings_sha256,
    ) = fields
    if (
        magic != HEADER_MAGIC
        or version != FORMAT_VERSION
        or classification != SCHEDULE_CLASSIFICATION_BOUNDED
        or schedule.classification != BOUNDED_CLASSIFICATION
        or maximum_rows != MAXIMUM_ROWS
        or maximum_targets != MAXIMUM_TARGETS
        or reserved != 0
        or not 1 <= row_count <= MAXIMUM_ROWS
        or not 1 <= target_count <= MAXIMUM_TARGETS
        or stop_q - start_q > MAXIMUM_SCHEDULE_RECORDS
        or row_count != stop_t - first_t
        or row_header_bytes != ROW_HEADER.size
        or row_payload_bytes != ROW_PAYLOAD_BYTES
        or target_header_bytes != PHASE_TARGET.size
        or factor_record_bytes != FRAME_FACTOR.size
        or tail_record_bytes != 8
        or input_size != len(raw)
        or input_size > MAXIMUM_INPUT_BYTES
        or schedule_sha256.hex() != schedule.manifest_sha256
        or execution_sha256.hex() != schedule.execution_order_sha256
    ):
        _fail("resident phase header or explicit bound differs")
    expected_plan = phase_plan_digest(
        schedule,
        start_execution_q_index=start_q,
        stop_execution_q_index=stop_q,
        phase_index=phase_index,
        first_t_index=first_t,
        t_index_stop_exclusive=stop_t,
    )
    if plan_sha256.hex() != expected_plan:
        _fail("resident phase plan digest differs")
    targets = active_phase_targets(
        schedule,
        start_execution_q_index=start_q,
        stop_execution_q_index=stop_q,
        phase_index=phase_index,
        first_t_index=first_t,
        t_index_stop_exclusive=stop_t,
    )
    if target_count != len(targets):
        _fail("resident phase active target count differs")

    offset = PHASE_HEADER.size
    row_stream = hashlib.sha256()
    parsed_rows: list[tuple[int, bytes, bytes]] = []
    for row_offset in range(row_count):
        if offset + ROW_HEADER.size + ROW_PAYLOAD_BYTES > len(raw):
            _fail("resident phase row stream is truncated")
        row_header_raw = raw[offset : offset + ROW_HEADER.size]
        offset += ROW_HEADER.size
        payload = raw[offset : offset + ROW_PAYLOAD_BYTES]
        offset += ROW_PAYLOAD_BYTES
        row_stream.update(row_header_raw)
        row_stream.update(payload)
        (
            row_magic,
            row_version,
            row_reserved,
            t_index,
            payload_bytes,
            payload_sha256,
        ) = ROW_HEADER.unpack(row_header_raw)
        if (
            row_magic != ROW_MAGIC
            or row_version != TMAJOR_ROW_FORMAT_VERSION
            or row_reserved != 0
            or t_index != first_t + row_offset
            or payload_bytes != ROW_PAYLOAD_BYTES
            or hashlib.sha256(payload).digest() != payload_sha256
        ):
            _fail("resident phase row is substituted or malformed")
        validate_lattice_row(payload)
        parsed_rows.append((t_index, payload, payload_sha256))
    if (
        _row_binding(
            lattice_source_sha256=lattice_source_sha256.hex(),
            phase_plan_sha256=expected_plan,
            rows=tuple(parsed_rows),
        )
        != row_bindings_sha256
    ):
        _fail("resident phase row binding differs")

    target_stream = hashlib.sha256()
    chain = _initial_chain(expected_plan)
    frames: list[ResidentPhaseFrame] = []
    rows_referenced = 0
    values_seen = 0
    sidecar_bytes_seen = 0
    for target_number, expected in enumerate(targets):
        if offset + PHASE_TARGET.size > len(raw):
            _fail("resident phase target stream is truncated")
        target_raw = raw[offset : offset + PHASE_TARGET.size]
        offset += PHASE_TARGET.size
        target_stream.update(target_raw)
        (
            target_magic,
            target_version,
            target_reserved,
            execution_q_index,
            q,
            target_phase_index,
            target_first_t,
            target_stop_t,
            batch_count,
            component_count,
            group_order,
            target_values,
            factor_bytes,
            tail_bytes,
            target_sha256,
            sidecar_sha256,
        ) = PHASE_TARGET.unpack(target_raw)
        expected_components = len(canonical_component_orders(expected.q))
        expected_order = len(canonical_residue_order(expected.q))
        if (
            target_magic != TARGET_MAGIC
            or target_version != FORMAT_VERSION
            or target_reserved != 0
            or execution_q_index != expected.execution_q_index
            or q != expected.q
            or target_phase_index != expected.lane_index
            or target_first_t != expected.first_t_index
            or target_stop_t != expected.t_index_stop_exclusive
            or batch_count != expected.batch_count
            or component_count != expected_components
            or group_order != expected_order
            or target_values != expected.batch_count * expected_order
            or factor_bytes != expected.batch_count * FRAME_FACTOR.size
            or tail_bytes != expected.batch_count * 8
            or target_sha256.hex() != expected.digest()
        ):
            _fail(
                f"resident phase target {target_number} is substituted"
            )
        if offset + factor_bytes + tail_bytes > len(raw):
            _fail("resident phase sidecar is truncated")
        factors = raw[offset : offset + factor_bytes]
        offset += factor_bytes
        tails = raw[offset : offset + tail_bytes]
        offset += tail_bytes
        target_stream.update(factors)
        target_stream.update(tails)
        _validate_sidecars(expected, factors, tails)
        if (
            _sidecar_binding(
                sidecar_source_sha256=sidecar_source_sha256.hex(),
                phase_plan_sha256=expected_plan,
                target=expected,
                factors=factors,
                tails=tails,
            )
            != sidecar_sha256
        ):
            _fail("resident phase sidecar binding differs")
        frames.append(
            ResidentPhaseFrame(
                target=expected,
                component_count=component_count,
                group_order=group_order,
                value_count=target_values,
                factors=factors,
                tails=tails,
            )
        )
        chain = _advance_chain(chain, expected)
        rows_referenced += expected.batch_count
        values_seen += target_values
        sidecar_bytes_seen += factor_bytes + tail_bytes
    if values_seen != value_count or values_seen > MAXIMUM_VALUES:
        _fail("resident phase value accounting differs")

    bytes_before_footer = offset
    if offset + PHASE_FOOTER.size != len(raw):
        _fail("resident phase footer is truncated or has trailing bytes")
    (
        footer_magic,
        footer_version,
        footer_reserved,
        footer_rows,
        footer_targets,
        footer_row_references,
        footer_values,
        footer_sidecar_bytes,
        footer_input_before,
        descriptor_reconstructions,
        descriptor_uploads,
        lattice_uploads,
        footer_chain,
        footer_row_stream,
        footer_target_stream,
        footer_reserved_sha256,
    ) = PHASE_FOOTER.unpack_from(raw, offset)
    if (
        footer_magic != FOOTER_MAGIC
        or footer_version != FORMAT_VERSION
        or footer_reserved != 0
        or footer_rows != row_count
        or footer_targets != target_count
        or footer_row_references != rows_referenced
        or footer_values != values_seen
        or footer_sidecar_bytes != sidecar_bytes_seen
        or footer_input_before != bytes_before_footer
        or descriptor_reconstructions != target_count
        or descriptor_uploads != target_count
        or lattice_uploads != 1
        or footer_chain != chain
        or footer_row_stream != row_stream.digest()
        or footer_target_stream != target_stream.digest()
        or footer_reserved_sha256 != b"\0" * 32
    ):
        _fail("resident phase footer or execution accounting differs")
    return ParsedResidentPhase(
        path=path.resolve(),
        schedule_manifest_sha256=schedule.manifest_sha256,
        schedule_source_roster_sha256=schedule.source_roster_sha256,
        schedule_execution_order_sha256=(
            schedule.execution_order_sha256
        ),
        phase_plan_sha256=expected_plan,
        source_contract_sha256=source_contract_sha256.hex(),
        lattice_source_sha256=lattice_source_sha256.hex(),
        recovery_seed_sha256=recovery_seed_sha256.hex(),
        sidecar_source_sha256=sidecar_source_sha256.hex(),
        phase_index=phase_index,
        start_execution_q_index=start_q,
        stop_execution_q_index=stop_q,
        first_t_index=first_t,
        t_index_stop_exclusive=stop_t,
        rows=tuple(payload for _t, payload, _sha in parsed_rows),
        frames=tuple(frames),
        target_chain_sha256=chain.hex(),
        row_stream_sha256=row_stream.hexdigest(),
        target_stream_sha256=target_stream.hexdigest(),
        input_sha256=input_sha256,
        input_size_bytes=len(raw),
        target_row_reference_count=rows_referenced,
        value_count=values_seen,
    )


def _canonical_json(path: Path, *, label: str) -> dict[str, Any]:
    raw = _bounded_read(path, MAXIMUM_JSON_BYTES, label=label)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletResidentQMajorPhaseError(
            f"invalid {label}"
        ) from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail(f"{label} is not canonical JSON")
    return value


def _validate_output(
    raw: bytes, parsed: ParsedResidentPhase
) -> None:
    offset = 0
    for frame in parsed.frames:
        if offset + TGDAFFI_HEADER.size > len(raw):
            _fail("resident TGDAFFI1 header is truncated")
        header = TGDAFFI_HEADER.unpack_from(raw, offset)
        offset += TGDAFFI_HEADER.size
        target = frame.target
        if header != (
            TGDAFFI_MAGIC,
            TGDAFFI_FORMAT_VERSION,
            target.q,
            frame.component_count,
            target.batch_count,
            frame.group_order,
            target.first_t_index * SOURCE_SAMPLE_NUMERATOR,
            SOURCE_SAMPLE_DENOMINATOR,
            SOURCE_SAMPLE_NUMERATOR,
            frame.value_count,
            0,
        ):
            _fail("resident TGDAFFI1 header differs from its phase target")
        payload_bytes = frame.value_count * COMPLEX_INTERVAL.size
        if offset + payload_bytes > len(raw):
            _fail("resident TGDAFFI1 values are truncated")
        for values in COMPLEX_INTERVAL.iter_unpack(
            raw[offset : offset + payload_bytes]
        ):
            if (
                not all(math.isfinite(endpoint) for endpoint in values)
                or values[0] > values[1]
                or values[2] > values[3]
            ):
                _fail("resident TGDAFFI1 interval is malformed")
        offset += payload_bytes
    if offset != len(raw):
        _fail("resident TGDAFFI1 stream has trailing bytes")


def validate_resident_phase_cuda_summary(
    summary_path: Path,
    parsed: ParsedResidentPhase,
    output_path: Path,
) -> dict[str, Any]:
    value = _canonical_json(
        summary_path, label="resident phase CUDA summary"
    )
    output = _bounded_read(
        output_path,
        MAXIMUM_OUTPUT_BYTES,
        label="resident phase TGDAFFI1 output",
    )
    _validate_output(output, parsed)
    expected: dict[str, Any] = {
        "algorithm_id": CUDA_ALGORITHM_ID,
        "canonical_descriptor_input_bytes": 0,
        "classification": (
            "bounded_resident_qmajor_phase_cuda_not_source_or_zero_closure"
        ),
        "completed_l_zero_state_validated": False,
        "descriptor_h2d_upload_count": len(parsed.frames),
        "descriptor_reconstruction_count": len(parsed.frames),
        "device_memory_preflight_passed": True,
        "device_memory_safety_reserve_bytes": (
            DEVICE_MEMORY_SAFETY_RESERVE_BYTES
        ),
        "external_atom_discharged": False,
        "first_t_index": parsed.first_t_index,
        "h100_source_phase_completed": False,
        "input_sha256": parsed.input_sha256,
        "input_size_bytes": parsed.input_size_bytes,
        "lattice_h2d_upload_count": 1,
        "lattice_source_sha256": parsed.lattice_source_sha256,
        "output_sha256": hashlib.sha256(output).hexdigest(),
        "output_size_bytes": len(output),
        "phase_index": parsed.phase_index,
        "phase_plan_sha256": parsed.phase_plan_sha256,
        "production_run_completed": False,
        "recovery_seed_artifact_sha256": parsed.recovery_seed_sha256,
        "row_count": len(parsed.rows),
        "row_payload_h2d_bytes": len(parsed.rows) * ROW_PAYLOAD_BYTES,
        "schedule_execution_order_sha256": (
            parsed.schedule_execution_order_sha256
        ),
        "schedule_manifest_sha256": parsed.schedule_manifest_sha256,
        "schedule_source_roster_sha256": (
            parsed.schedule_source_roster_sha256
        ),
        "schema": SUMMARY_SCHEMA,
        "schema_version": FORMAT_VERSION,
        "sidecar_source_sha256": parsed.sidecar_source_sha256,
        "source_contract_sha256": parsed.source_contract_sha256,
        "source_scale_run": False,
        "start_execution_q_index": parsed.start_execution_q_index,
        "stop_execution_q_index": parsed.stop_execution_q_index,
        "t_index_stop_exclusive": parsed.t_index_stop_exclusive,
        "target_chain_sha256": parsed.target_chain_sha256,
        "target_count": len(parsed.frames),
        "target_row_reference_count": (
            parsed.target_row_reference_count
        ),
        "transcendental_device_calls": 0,
        "trusted_execution_attested": False,
        "value_count": parsed.value_count,
        "zero_completeness_claimed": False,
    }
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            _fail(f"resident phase CUDA summary field differs: {key}")
    elapsed = value.get("elapsed_kernel_nanoseconds")
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, int)
        or elapsed < 0
    ):
        _fail("resident phase CUDA elapsed time is malformed")
    for key in (
        "device_memory_free_bytes_before_allocations",
        "device_memory_known_allocation_bytes",
    ):
        memory_value = value.get(key)
        if (
            isinstance(memory_value, bool)
            or not isinstance(memory_value, int)
            or memory_value <= 0
        ):
            _fail(f"resident phase CUDA memory field differs: {key}")
    if (
        value["device_memory_known_allocation_bytes"]
        + DEVICE_MEMORY_SAFETY_RESERVE_BYTES
        > value["device_memory_free_bytes_before_allocations"]
    ):
        _fail("resident phase CUDA memory preflight accounting differs")
    if set(value) != set(expected) | {
        "elapsed_kernel_nanoseconds",
        "device_memory_free_bytes_before_allocations",
        "device_memory_known_allocation_bytes",
    }:
        _fail("resident phase CUDA summary fields differ")
    return value


def compare_with_row_repeated_baseline(
    parsed: ParsedResidentPhase,
    resident_summary: dict[str, Any],
    *,
    baseline_input_size_bytes: int,
    baseline_kernel_nanoseconds: int,
    baseline_output_sha256: str,
) -> dict[str, Any]:
    """Return exact byte and observed-kernel comparisons for one bounded KAT."""

    baseline_bytes = _integer(
        baseline_input_size_bytes,
        "row-repeated baseline input bytes",
        minimum=1,
    )
    baseline_runtime = _integer(
        baseline_kernel_nanoseconds,
        "row-repeated baseline kernel runtime",
    )
    baseline_output = _digest(
        baseline_output_sha256, "row-repeated baseline output"
    )
    if (
        resident_summary.get("output_sha256") != baseline_output
        or resident_summary.get("input_size_bytes")
        != parsed.input_size_bytes
        or resident_summary.get("elapsed_kernel_nanoseconds") is None
    ):
        _fail("resident/baseline comparison identities differ")
    resident_runtime = _integer(
        resident_summary["elapsed_kernel_nanoseconds"],
        "resident phase kernel runtime",
    )
    if baseline_bytes <= parsed.input_size_bytes:
        _fail("resident phase did not reduce the row-repeated input")
    return {
        "schema": COMPARISON_SCHEMA,
        "schema_version": FORMAT_VERSION,
        "algorithm_id": CUDA_ALGORITHM_ID,
        "target_count": len(parsed.frames),
        "unique_row_count": len(parsed.rows),
        "target_row_reference_count": (
            parsed.target_row_reference_count
        ),
        "resident_input_size_bytes": parsed.input_size_bytes,
        "row_repeated_input_size_bytes": baseline_bytes,
        "input_bytes_saved": baseline_bytes - parsed.input_size_bytes,
        "input_size_ratio_resident_over_row_repeated": (
            parsed.input_size_bytes / baseline_bytes
        ),
        "resident_elapsed_kernel_nanoseconds": resident_runtime,
        "row_repeated_elapsed_kernel_nanoseconds": baseline_runtime,
        "kernel_runtime_ratio_resident_over_row_repeated": (
            resident_runtime / baseline_runtime
            if baseline_runtime
            else None
        ),
        "exact_output_sha256": baseline_output,
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
            "sparkinterval.tg.dirichlet_resident_qmajor_phase."
            "capability.v1"
        ),
        "algorithm_id": ALGORITHM_ID,
        "bounded_resident_qmajor_phase_implemented": True,
        "bounded_real_cuda_kat_implemented": True,
        "bounded_real_cuda_kat_completed": False,
        "maximum_rows_per_phase": MAXIMUM_ROWS,
        "maximum_targets_per_phase": MAXIMUM_TARGETS,
        "maximum_schedule_records_per_phase": MAXIMUM_SCHEDULE_RECORDS,
        "maximum_values_per_phase": MAXIMUM_VALUES,
        "maximum_input_bytes": MAXIMUM_INPUT_BYTES,
        "maximum_output_bytes": MAXIMUM_OUTPUT_BYTES,
        "device_memory_safety_reserve_bytes": (
            DEVICE_MEMORY_SAFETY_RESERVE_BYTES
        ),
        "fail_closed_device_memory_preflight": True,
        "lattice_rows_serialized_and_uploaded_once": True,
        "formulaic_active_q_and_clipped_t_reconstruction": True,
        "descriptors_cached_by_actual_q": True,
        "canonical_descriptor_input_bytes": 0,
        "serialized_control_records_required": 0,
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
        "candidate_source_resident_phase_executor_implemented": False,
        "candidate_source_resident_phase_fit_claimed": False,
        "source_schedule_accepted": False,
        "source_lattice_spools_populated": False,
        "source_scale_run_completed": False,
        "h100_source_phase_completed": False,
        "production_run_completed": False,
        "trusted_execution_attested": False,
        "completed_l_zero_state_validated": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "DirichletResidentQMajorPhaseError",
    "FOOTER_MAGIC",
    "HEADER_MAGIC",
    "MAXIMUM_INPUT_BYTES",
    "MAXIMUM_OUTPUT_BYTES",
    "MAXIMUM_ROWS",
    "MAXIMUM_TARGETS",
    "MAXIMUM_VALUES",
    "PHASE_FOOTER",
    "PHASE_HEADER",
    "PHASE_TARGET",
    "ParsedResidentPhase",
    "ResidentPhaseFrame",
    "TARGET_MAGIC",
    "active_phase_targets",
    "capability",
    "compare_with_row_repeated_baseline",
    "phase_plan_digest",
    "replay_resident_qmajor_phase",
    "validate_resident_phase_cuda_summary",
    "write_resident_qmajor_phase",
]
