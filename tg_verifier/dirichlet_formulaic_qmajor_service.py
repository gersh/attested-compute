# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Descriptor-free bounded wire for the compiled formulaic q-major service.

One header and lane table replace a JSON control record for every formulaic
target.  Each target frame contains at most 64 authenticated t-major lattice
rows plus factor and Taylor-tail sidecars.  Canonical CRT descriptors never
occur on the wire: the CUDA service reconstructs and uploads them only when q
changes, then emits the existing ``TGDAFFI1`` stream.

This module builds and independently replays bounded integration artifacts.
It does not validate the analytic origin of the lattice, sidecars, or recovery
seeds; run the full source campaign; attest execution; establish zero
completeness or a Turing count; or discharge Platt's Theorem 7.1.
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
from typing import Any, BinaryIO, Callable, NoReturn, Sequence

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
    FormulaicQMajorCursor,
    FormulaicTarget,
    LaneRange,
    MAXIMUM_BATCH_COUNT,
    PINNED_SOURCE_ROWS,
    plan_identity,
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
from tg_verifier import dirichlet_tmajor_cuda_arithmetic_replay as arithmetic


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-dirichlet-formulaic-qmajor-seeded-cuda-v1"
STREAM_SCHEMA = (
    "sparkinterval.tg.dirichlet_formulaic_qmajor_service.stream.v1"
)
SUMMARY_SCHEMA = (
    "sparkinterval.tg.dirichlet_formulaic_qmajor_cuda.summary.v1"
)
REPLAY_SCHEMA = (
    "sparkinterval.tg.dirichlet_formulaic_qmajor_cuda.replay.v1"
)

FORMAT_VERSION = 1
TMAJOR_ROW_FORMAT_VERSION = 2
SCHEDULE_CLASSIFICATION_BOUNDED = 0
HEADER_MAGIC = b"TGDQMSH1"
FRAME_MAGIC = b"TGDQMSQ1"
FOOTER_MAGIC = b"TGDQMSF1"
ROW_BINDING_DOMAIN = (
    b"sparkinterval/tg/dirichlet-formulaic-qmajor/frame-rows/v1\0"
)
SIDECAR_DOMAIN = (
    b"sparkinterval/tg/dirichlet-formulaic-qmajor/frame-sidecar/v1\0"
)
# The trailing NULs are deliberate: the C++ service hashes sizeof(char[])
# for these two domains.  Target and cursor-chain domains instead use
# sizeof(domain) - 1 and therefore retain their existing non-NUL encoding.

# Header: fixed geometry, six external/source identities.
SERVICE_HEADER = struct.Struct(
    "<8sIIIIQQQQQQQQQ32s32s32s32s32s32s"
)
LANE_RECORD = struct.Struct("<IIII")
FRAME_HEADER = struct.Struct(
    "<8sIIQIIIIIIQQQQQqQQ32s32s32s"
)
SERVICE_FOOTER = struct.Struct("<8sIIQQQQQQQ32s32s32s")

assert SERVICE_HEADER.size == 288
assert LANE_RECORD.size == 16
assert FRAME_HEADER.size == 208
assert SERVICE_FOOTER.size == 168
assert ROW_HEADER.size == 64
assert ROW_PAYLOAD_BYTES == 1_048_576
assert FRAME_FACTOR.size == 32

MAXIMUM_LANE_COUNT = 64
DEFAULT_MAXIMUM_STREAM_BYTES = 256 * 1024 * 1024
DEFAULT_MAXIMUM_OUTPUT_BYTES = 256 * 1024 * 1024
MAXIMUM_JSON_BYTES = 4 * 1024 * 1024
HEX = frozenset("0123456789abcdef")

RowProvider = Callable[[FormulaicTarget, int], bytes]
SidecarProvider = Callable[[FormulaicTarget], tuple[bytes, bytes]]


class DirichletFormulaicQMajorServiceError(RuntimeError):
    """A compact formulaic stream, CUDA summary, or replay failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletFormulaicQMajorServiceError(message)


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in HEX for character in value)
    ):
        _fail(f"{label} is not lowercase SHA-256")
    return value


def _positive_integer(value: object, label: str, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        _fail(f"{label} is outside [1,{maximum}]")
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
        raise DirichletFormulaicQMajorServiceError(
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
    maximum = _positive_integer(maximum, f"{label} bound", 1 << 32)
    with _open_regular(path, label=label) as source:
        before = os.fstat(source.fileno())
        if not 1 <= before.st_size <= maximum:
            _fail(f"{label} size is outside [1,{maximum}]")
        raw = source.read(maximum + 1)
        after = os.fstat(source.fileno())
    if len(raw) != before.st_size or _identity(before) != _identity(after):
        _fail(f"{label} changed while it was read")
    return raw


def _atomic_stream(
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
            report = write(output)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)
        temporary.unlink()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return report


def _write_and_hash(
    output: BinaryIO,
    raw: bytes,
    *,
    input_digest: Any,
    frame_digest: Any | None = None,
) -> None:
    written = output.write(raw)
    if written != len(raw):
        _fail("cannot write formulaic q-major stream")
    input_digest.update(raw)
    if frame_digest is not None:
        frame_digest.update(raw)


def _validate_sidecars(
    target: FormulaicTarget, factors: bytes, tails: bytes
) -> None:
    if (
        len(factors) != target.batch_count * FRAME_FACTOR.size
        or len(tails) != target.batch_count * 8
    ):
        _fail("formulaic factor or tail sidecar length differs")
    for factor in FRAME_FACTOR.iter_unpack(factors):
        if (
            not all(math.isfinite(value) for value in factor)
            or factor[0] > factor[1]
            or factor[2] > factor[3]
        ):
            _fail("formulaic factor sidecar is malformed")
    for (tail,) in struct.iter_unpack("<d", tails):
        if not math.isfinite(tail) or tail < 0:
            _fail("formulaic Taylor-tail sidecar is malformed")


def _row_binding(
    *,
    lattice_source_sha256: str,
    target: FormulaicTarget,
    rows: Sequence[tuple[int, bytes, bytes]],
) -> bytes:
    digest = hashlib.sha256(ROW_BINDING_DOMAIN)
    digest.update(bytes.fromhex(lattice_source_sha256))
    digest.update(target.packed())
    for t_index, _payload, payload_sha256 in rows:
        digest.update(struct.pack("<Q", t_index))
        digest.update(payload_sha256)
    return digest.digest()


def _sidecar_binding(
    *,
    sidecar_source_sha256: str,
    target: FormulaicTarget,
    factors: bytes,
    tails: bytes,
) -> bytes:
    digest = hashlib.sha256(SIDECAR_DOMAIN)
    digest.update(bytes.fromhex(sidecar_source_sha256))
    digest.update(target.packed())
    digest.update(factors)
    digest.update(tails)
    return digest.digest()


def write_formulaic_service_stream(
    path: Path,
    schedule: ParsedScheduleManifest,
    lanes: Sequence[LaneRange],
    *,
    recovery_seed_sha256: str,
    source_contract_sha256: str,
    lattice_source_sha256: str,
    sidecar_source_sha256: str,
    row_provider: RowProvider,
    sidecar_provider: SidecarProvider,
    start_execution_q_index: int = 0,
    stop_execution_q_index: int | None = None,
    maximum_batch_count: int = MAXIMUM_BATCH_COUNT,
) -> dict[str, Any]:
    """Write one bounded, descriptor-free cursor stream atomically."""

    if schedule.classification != BOUNDED_CLASSIFICATION:
        _fail("compiled formulaic stream is currently bounded-only")
    maximum_batch_count = _positive_integer(
        maximum_batch_count,
        "maximum batch count",
        MAXIMUM_BATCH_COUNT,
    )
    for value, label in (
        (recovery_seed_sha256, "recovery seed"),
        (source_contract_sha256, "source contract"),
        (lattice_source_sha256, "lattice source"),
        (sidecar_source_sha256, "sidecar source"),
    ):
        _digest(value, label)
    plan = plan_identity(
        schedule,
        lanes,
        start_execution_q_index=start_execution_q_index,
        stop_execution_q_index=stop_execution_q_index,
        maximum_batch_count=maximum_batch_count,
    )
    checked_lanes = tuple(
        LaneRange(
            value["lane_index"],
            value["first_t_index"],
            value["t_index_stop_exclusive"],
        )
        for value in plan["lanes"]
    )
    if not 1 <= len(checked_lanes) <= MAXIMUM_LANE_COUNT:
        _fail("formulaic lane count is outside its compiled bound")
    cursor = FormulaicQMajorCursor(
        schedule,
        checked_lanes,
        start_execution_q_index=plan["start_execution_q_index"],
        stop_execution_q_index=plan["stop_execution_q_index"],
        maximum_batch_count=maximum_batch_count,
    )
    accounting = cursor.accounting

    def write(output: BinaryIO) -> dict[str, Any]:
        input_digest = hashlib.sha256()
        frame_digest = hashlib.sha256()
        header = SERVICE_HEADER.pack(
            HEADER_MAGIC,
            FORMAT_VERSION,
            SCHEDULE_CLASSIFICATION_BOUNDED,
            maximum_batch_count,
            len(checked_lanes),
            plan["start_execution_q_index"],
            plan["stop_execution_q_index"],
            accounting["target_count"],
            accounting["row_reference_count"],
            FRAME_HEADER.size,
            ROW_HEADER.size,
            ROW_PAYLOAD_BYTES,
            FRAME_FACTOR.size,
            8,
            bytes.fromhex(schedule.manifest_sha256),
            bytes.fromhex(plan["plan_sha256"]),
            bytes.fromhex(source_contract_sha256),
            bytes.fromhex(lattice_source_sha256),
            bytes.fromhex(recovery_seed_sha256),
            bytes.fromhex(sidecar_source_sha256),
        )
        _write_and_hash(output, header, input_digest=input_digest)
        for lane in checked_lanes:
            raw = LANE_RECORD.pack(
                lane.lane_index,
                lane.first_t_index,
                lane.t_index_stop_exclusive,
                0,
            )
            _write_and_hash(output, raw, input_digest=input_digest)

        target_count = 0
        row_count = 0
        value_count = 0
        q_transitions = 0
        current_q: int | None = None
        while (target := cursor.expected_target()) is not None:
            if target.q != current_q:
                current_q = target.q
                q_transitions += 1
            rows: list[tuple[int, bytes, bytes]] = []
            for t_index in range(
                target.first_t_index,
                target.t_index_stop_exclusive,
            ):
                payload = row_provider(target, t_index)
                if not isinstance(payload, bytes):
                    _fail("formulaic row provider did not return bytes")
                validate_lattice_row(payload)
                rows.append(
                    (t_index, payload, hashlib.sha256(payload).digest())
                )
            factors, tails = sidecar_provider(target)
            if not isinstance(factors, bytes) or not isinstance(tails, bytes):
                _fail("formulaic sidecar provider did not return bytes")
            _validate_sidecars(target, factors, tails)
            orders = canonical_component_orders(target.q)
            group_order = len(canonical_residue_order(target.q))
            values = target.batch_count * group_order
            row_sha256 = _row_binding(
                lattice_source_sha256=lattice_source_sha256,
                target=target,
                rows=rows,
            )
            sidecar_sha256 = _sidecar_binding(
                sidecar_source_sha256=sidecar_source_sha256,
                target=target,
                factors=factors,
                tails=tails,
            )
            raw_header = FRAME_HEADER.pack(
                FRAME_MAGIC,
                FORMAT_VERSION,
                0,
                target.execution_q_index,
                target.q,
                target.lane_index,
                target.first_t_index,
                target.t_index_stop_exclusive,
                target.batch_count,
                len(orders),
                group_order,
                values,
                target.batch_count * ROW_PAYLOAD_BYTES,
                len(factors),
                len(tails),
                target.first_t_index * SOURCE_SAMPLE_NUMERATOR,
                SOURCE_SAMPLE_DENOMINATOR,
                SOURCE_SAMPLE_NUMERATOR,
                bytes.fromhex(target.digest()),
                row_sha256,
                sidecar_sha256,
            )
            _write_and_hash(
                output,
                raw_header,
                input_digest=input_digest,
                frame_digest=frame_digest,
            )
            for t_index, payload, payload_sha256 in rows:
                row_header = ROW_HEADER.pack(
                    ROW_MAGIC,
                    TMAJOR_ROW_FORMAT_VERSION,
                    0,
                    t_index,
                    ROW_PAYLOAD_BYTES,
                    payload_sha256,
                )
                _write_and_hash(
                    output,
                    row_header,
                    input_digest=input_digest,
                    frame_digest=frame_digest,
                )
                _write_and_hash(
                    output,
                    payload,
                    input_digest=input_digest,
                    frame_digest=frame_digest,
                )
            _write_and_hash(
                output,
                factors,
                input_digest=input_digest,
                frame_digest=frame_digest,
            )
            _write_and_hash(
                output,
                tails,
                input_digest=input_digest,
                frame_digest=frame_digest,
            )
            cursor.accept(target)
            target_count += 1
            row_count += target.batch_count
            value_count += values

        session = cursor.finish()
        input_bytes_before_footer = output.tell()
        footer = SERVICE_FOOTER.pack(
            FOOTER_MAGIC,
            FORMAT_VERSION,
            0,
            target_count,
            row_count,
            value_count,
            q_transitions,
            q_transitions,
            target_count,
            input_bytes_before_footer,
            bytes.fromhex(session["target_chain_sha256"]),
            frame_digest.digest(),
            b"\0" * 32,
        )
        _write_and_hash(output, footer, input_digest=input_digest)
        return {
            "target_count": target_count,
            "row_reference_count": row_count,
            "value_count": value_count,
            "q_transition_count": q_transitions,
            "target_chain_sha256": session["target_chain_sha256"],
            "frame_stream_sha256": frame_digest.hexdigest(),
            "input_stream_sha256": input_digest.hexdigest(),
            "input_stream_size_bytes": input_bytes_before_footer + len(footer),
        }

    streamed = _atomic_stream(path, write)
    body: dict[str, Any] = {
        "schema": STREAM_SCHEMA,
        "schema_version": FORMAT_VERSION,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "bounded_descriptor_free_formulaic_stream_not_source_evidence"
        ),
        "schedule_manifest_sha256": schedule.manifest_sha256,
        "schedule_execution_order_sha256": (
            schedule.execution_order_sha256
        ),
        "plan_sha256": plan["plan_sha256"],
        "source_contract_sha256": source_contract_sha256,
        "lattice_source_sha256": lattice_source_sha256,
        "recovery_seed_artifact_sha256": recovery_seed_sha256,
        "sidecar_source_sha256": sidecar_source_sha256,
        "artifact": {
            "path": str(path.resolve()),
            "sha256": streamed["input_stream_sha256"],
            "size_bytes": streamed["input_stream_size_bytes"],
        },
        "maximum_batch_count": maximum_batch_count,
        "lane_count": len(checked_lanes),
        "start_execution_q_index": plan["start_execution_q_index"],
        "stop_execution_q_index": plan["stop_execution_q_index"],
        **streamed,
        "serialized_control_records_required": 0,
        "canonical_descriptor_input_bytes": 0,
        "production_run_completed": False,
        "source_scale_run": False,
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
class FormulaicServiceFrame:
    target: FormulaicTarget
    component_count: int
    group_order: int
    value_count: int
    rows: tuple[bytes, ...]
    factors: bytes
    tails: bytes


@dataclass(frozen=True)
class ParsedFormulaicServiceStream:
    path: Path
    schedule_manifest_sha256: str
    schedule_source_roster_sha256: str
    schedule_execution_order_sha256: str
    plan_sha256: str
    source_contract_sha256: str
    lattice_source_sha256: str
    recovery_seed_sha256: str
    sidecar_source_sha256: str
    maximum_batch_count: int
    lanes: tuple[LaneRange, ...]
    start_execution_q_index: int
    stop_execution_q_index: int
    frames: tuple[FormulaicServiceFrame, ...]
    target_chain_sha256: str
    frame_stream_sha256: str
    input_stream_sha256: str
    input_stream_size_bytes: int
    row_reference_count: int
    value_count: int
    descriptor_reconstruction_count: int


def replay_formulaic_service_stream(
    path: Path,
    schedule: ParsedScheduleManifest,
    *,
    expected_stream_sha256: str | None = None,
    maximum_stream_bytes: int = DEFAULT_MAXIMUM_STREAM_BYTES,
) -> ParsedFormulaicServiceStream:
    """Independently parse every byte and replay the exact cursor."""

    raw = _bounded_read(
        path, maximum_stream_bytes, label="formulaic service stream"
    )
    observed_stream_sha256 = hashlib.sha256(raw).hexdigest()
    if (
        expected_stream_sha256 is not None
        and observed_stream_sha256
        != _digest(
            expected_stream_sha256, "expected formulaic service stream"
        )
    ):
        _fail("formulaic service stream differs from its external pin")
    if len(raw) < SERVICE_HEADER.size + LANE_RECORD.size + SERVICE_FOOTER.size:
        _fail("formulaic service stream is too short")
    fields = SERVICE_HEADER.unpack_from(raw)
    (
        magic,
        version,
        schedule_classification,
        maximum_batch_count,
        lane_count,
        start_index,
        stop_index,
        target_count,
        row_reference_count,
        frame_header_bytes,
        row_header_bytes,
        row_payload_bytes,
        factor_record_bytes,
        tail_record_bytes,
        schedule_sha256,
        plan_sha256,
        source_contract_sha256,
        lattice_source_sha256,
        recovery_seed_sha256,
        sidecar_source_sha256,
    ) = fields
    if (
        magic != HEADER_MAGIC
        or version != FORMAT_VERSION
        or schedule_classification != SCHEDULE_CLASSIFICATION_BOUNDED
        or schedule.classification != BOUNDED_CLASSIFICATION
        or not 1 <= maximum_batch_count <= MAXIMUM_BATCH_COUNT
        or not 1 <= lane_count <= MAXIMUM_LANE_COUNT
        or not 0 <= start_index < stop_index
        <= len(schedule.execution_records)
        or frame_header_bytes != FRAME_HEADER.size
        or row_header_bytes != ROW_HEADER.size
        or row_payload_bytes != ROW_PAYLOAD_BYTES
        or factor_record_bytes != FRAME_FACTOR.size
        or tail_record_bytes != 8
        or schedule_sha256.hex() != schedule.manifest_sha256
    ):
        _fail("formulaic service header or bounded geometry differs")
    offset = SERVICE_HEADER.size
    lanes: list[LaneRange] = []
    for expected_lane in range(lane_count):
        if offset + LANE_RECORD.size > len(raw):
            _fail("truncated formulaic lane table")
        lane_index, first_t, stop_t, reserved = LANE_RECORD.unpack_from(
            raw, offset
        )
        offset += LANE_RECORD.size
        if lane_index != expected_lane or reserved != 0:
            _fail("formulaic lane table is reordered or malformed")
        lanes.append(LaneRange(lane_index, first_t, stop_t))
    plan = plan_identity(
        schedule,
        lanes,
        start_execution_q_index=start_index,
        stop_execution_q_index=stop_index,
        maximum_batch_count=maximum_batch_count,
    )
    if plan_sha256.hex() != plan["plan_sha256"]:
        _fail("formulaic service plan digest differs")
    cursor = FormulaicQMajorCursor(
        schedule,
        lanes,
        start_execution_q_index=start_index,
        stop_execution_q_index=stop_index,
        maximum_batch_count=maximum_batch_count,
    )
    if (
        target_count != cursor.accounting["target_count"]
        or row_reference_count != cursor.accounting["row_reference_count"]
    ):
        _fail("formulaic service compressed accounting differs")

    frame_digest = hashlib.sha256()
    frames: list[FormulaicServiceFrame] = []
    values = 0
    rows_seen = 0
    q_transitions = 0
    current_q: int | None = None
    for frame_index in range(target_count):
        target = cursor.expected_target()
        if target is None:
            _fail("formulaic stream has frames after exact coverage")
        if offset + FRAME_HEADER.size > len(raw):
            _fail("truncated formulaic frame header")
        header_raw = raw[offset : offset + FRAME_HEADER.size]
        offset += FRAME_HEADER.size
        frame_digest.update(header_raw)
        frame = FRAME_HEADER.unpack(header_raw)
        (
            frame_magic,
            frame_version,
            frame_reserved,
            execution_q_index,
            q,
            lane_index,
            first_t,
            stop_t,
            batch_count,
            component_count,
            group_order,
            value_count,
            lattice_payload_bytes,
            factor_bytes,
            tail_bytes,
            first_t_numerator,
            t_denominator,
            t_step_numerator,
            target_sha256,
            row_bindings_sha256,
            sidecar_sha256,
        ) = frame
        orders = canonical_component_orders(target.q)
        residues = canonical_residue_order(target.q)
        if (
            frame_magic != FRAME_MAGIC
            or frame_version != FORMAT_VERSION
            or frame_reserved != 0
            or execution_q_index != target.execution_q_index
            or q != target.q
            or lane_index != target.lane_index
            or first_t != target.first_t_index
            or stop_t != target.t_index_stop_exclusive
            or batch_count != target.batch_count
            or component_count != len(orders)
            or group_order != len(residues)
            or value_count != target.batch_count * group_order
            or lattice_payload_bytes
            != target.batch_count * ROW_PAYLOAD_BYTES
            or factor_bytes != target.batch_count * FRAME_FACTOR.size
            or tail_bytes != target.batch_count * 8
            or first_t_numerator
            != target.first_t_index * SOURCE_SAMPLE_NUMERATOR
            or t_denominator != SOURCE_SAMPLE_DENOMINATOR
            or t_step_numerator != SOURCE_SAMPLE_NUMERATOR
            or target_sha256.hex() != target.digest()
        ):
            _fail(
                f"formulaic frame {frame_index} is substituted or malformed"
            )
        parsed_rows: list[tuple[int, bytes, bytes]] = []
        for row_index in range(target.batch_count):
            needed = ROW_HEADER.size + ROW_PAYLOAD_BYTES
            if offset + needed > len(raw):
                _fail("truncated formulaic row record")
            row_header_raw = raw[offset : offset + ROW_HEADER.size]
            offset += ROW_HEADER.size
            payload = raw[offset : offset + ROW_PAYLOAD_BYTES]
            offset += ROW_PAYLOAD_BYTES
            frame_digest.update(row_header_raw)
            frame_digest.update(payload)
            (
                row_magic,
                row_version,
                row_reserved,
                t_index,
                payload_bytes,
                payload_sha256,
            ) = ROW_HEADER.unpack(row_header_raw)
            expected_t = target.first_t_index + row_index
            if (
                row_magic != ROW_MAGIC
                or row_version != TMAJOR_ROW_FORMAT_VERSION
                or row_reserved != 0
                or t_index != expected_t
                or payload_bytes != ROW_PAYLOAD_BYTES
                or hashlib.sha256(payload).digest() != payload_sha256
            ):
                _fail("formulaic row is substituted or malformed")
            validate_lattice_row(payload)
            parsed_rows.append((t_index, payload, payload_sha256))
        if (
            _row_binding(
                lattice_source_sha256=lattice_source_sha256.hex(),
                target=target,
                rows=parsed_rows,
            )
            != row_bindings_sha256
        ):
            _fail("formulaic row binding differs")
        if offset + factor_bytes + tail_bytes > len(raw):
            _fail("truncated formulaic sidecar")
        factors = raw[offset : offset + factor_bytes]
        offset += factor_bytes
        tails = raw[offset : offset + tail_bytes]
        offset += tail_bytes
        frame_digest.update(factors)
        frame_digest.update(tails)
        _validate_sidecars(target, factors, tails)
        if (
            _sidecar_binding(
                sidecar_source_sha256=sidecar_source_sha256.hex(),
                target=target,
                factors=factors,
                tails=tails,
            )
            != sidecar_sha256
        ):
            _fail("formulaic sidecar binding differs")
        frames.append(
            FormulaicServiceFrame(
                target=target,
                component_count=component_count,
                group_order=group_order,
                value_count=value_count,
                rows=tuple(payload for _t, payload, _sha in parsed_rows),
                factors=factors,
                tails=tails,
            )
        )
        cursor.accept(target)
        rows_seen += target.batch_count
        values += value_count
        if current_q != target.q:
            current_q = target.q
            q_transitions += 1

    bytes_before_footer = offset
    if offset + SERVICE_FOOTER.size != len(raw):
        _fail("formulaic service footer is truncated or has trailing bytes")
    footer = SERVICE_FOOTER.unpack_from(raw, offset)
    (
        footer_magic,
        footer_version,
        footer_reserved,
        footer_targets,
        footer_rows,
        footer_values,
        descriptor_reconstructions,
        descriptor_uploads,
        lattice_uploads,
        claimed_bytes_before_footer,
        target_chain_sha256,
        frame_stream_sha256,
        reserved_sha256,
    ) = footer
    session = cursor.finish()
    if (
        footer_magic != FOOTER_MAGIC
        or footer_version != FORMAT_VERSION
        or footer_reserved != 0
        or footer_targets != target_count
        or footer_rows != rows_seen
        or footer_values != values
        or descriptor_reconstructions != q_transitions
        or descriptor_uploads != q_transitions
        or lattice_uploads != target_count
        or claimed_bytes_before_footer != bytes_before_footer
        or target_chain_sha256.hex() != session["target_chain_sha256"]
        or frame_stream_sha256 != frame_digest.digest()
        or reserved_sha256 != b"\0" * 32
    ):
        _fail("formulaic footer or exact cursor accounting differs")
    return ParsedFormulaicServiceStream(
        path=path.resolve(),
        schedule_manifest_sha256=schedule.manifest_sha256,
        schedule_source_roster_sha256=schedule.source_roster_sha256,
        schedule_execution_order_sha256=schedule.execution_order_sha256,
        plan_sha256=plan["plan_sha256"],
        source_contract_sha256=source_contract_sha256.hex(),
        lattice_source_sha256=lattice_source_sha256.hex(),
        recovery_seed_sha256=recovery_seed_sha256.hex(),
        sidecar_source_sha256=sidecar_source_sha256.hex(),
        maximum_batch_count=maximum_batch_count,
        lanes=tuple(lanes),
        start_execution_q_index=start_index,
        stop_execution_q_index=stop_index,
        frames=tuple(frames),
        target_chain_sha256=session["target_chain_sha256"],
        frame_stream_sha256=frame_digest.hexdigest(),
        input_stream_sha256=observed_stream_sha256,
        input_stream_size_bytes=len(raw),
        row_reference_count=rows_seen,
        value_count=values,
        descriptor_reconstruction_count=q_transitions,
    )


def _canonical_json_object(path: Path, *, label: str) -> dict[str, Any]:
    raw = _bounded_read(path, MAXIMUM_JSON_BYTES, label=label)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletFormulaicQMajorServiceError(
            f"invalid {label}"
        ) from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail(f"{label} is not canonical JSON")
    return value


def validate_formulaic_cuda_summary(
    summary_path: Path,
    parsed: ParsedFormulaicServiceStream,
    output_stream_path: Path,
) -> dict[str, Any]:
    """Bind a compiled execution summary to independently replayed bytes."""

    value = _canonical_json_object(
        summary_path, label="formulaic CUDA summary"
    )
    output = _bounded_read(
        output_stream_path,
        DEFAULT_MAXIMUM_OUTPUT_BYTES,
        label="formulaic TGDAFFI1 output",
    )
    expected_fixed: dict[str, Any] = {
        "algorithm_id": ALGORITHM_ID,
        "all_character_fft_executed": False,
        "canonical_descriptor_input_bytes": 0,
        "classification": (
            "bounded_formulaic_qmajor_cuda_component_not_source_or_"
            "zero_closure"
        ),
        "completed_l_zero_state_validated": False,
        "descriptor_h2d_upload_count": (
            parsed.descriptor_reconstruction_count
        ),
        "descriptor_reconstruction_count": (
            parsed.descriptor_reconstruction_count
        ),
        "external_atom_discharged": False,
        "first_execution_q": parsed.frames[0].target.q,
        "formulaic_cursor_consumed_directly": True,
        "frame_stream_sha256": parsed.frame_stream_sha256,
        "input_stream_sha256": parsed.input_stream_sha256,
        "input_stream_size_bytes": parsed.input_stream_size_bytes,
        "last_execution_q": parsed.frames[-1].target.q,
        "lattice_h2d_upload_count": len(parsed.frames),
        "lattice_source_sha256": parsed.lattice_source_sha256,
        "maximum_batch_count": parsed.maximum_batch_count,
        "output_stream_sha256": hashlib.sha256(output).hexdigest(),
        "plan_sha256": parsed.plan_sha256,
        "production_run_completed": False,
        "recovery_seed_artifact_sha256": parsed.recovery_seed_sha256,
        "row_reference_count": parsed.row_reference_count,
        "schedule_manifest_sha256": parsed.schedule_manifest_sha256,
        "schedule_execution_order_sha256": (
            parsed.schedule_execution_order_sha256
        ),
        "schedule_source_roster_sha256": (
            parsed.schedule_source_roster_sha256
        ),
        "schema": SUMMARY_SCHEMA,
        "schema_version": FORMAT_VERSION,
        "serialized_control_records_consumed": 0,
        "sidecar_source_sha256": parsed.sidecar_source_sha256,
        "source_contract_sha256": parsed.source_contract_sha256,
        "source_scale_run": False,
        "start_execution_q_index": parsed.start_execution_q_index,
        "stop_execution_q_index": parsed.stop_execution_q_index,
        "target_chain_sha256": parsed.target_chain_sha256,
        "target_count": len(parsed.frames),
        "transcendental_device_calls": 0,
        "trusted_execution_attested": False,
        "value_count": parsed.value_count,
        "zero_completeness_claimed": False,
    }
    for key, expected in expected_fixed.items():
        if value.get(key) != expected:
            _fail(f"formulaic CUDA summary field differs: {key}")
    elapsed = value.get("elapsed_kernel_nanoseconds")
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, int)
        or elapsed < 0
    ):
        _fail("formulaic CUDA elapsed time is malformed")
    if set(value) != set(expected_fixed) | {"elapsed_kernel_nanoseconds"}:
        _fail("formulaic CUDA summary fields differ")
    return value


def _factor_intervals(raw: bytes) -> tuple[arithmetic.ComplexInterval, ...]:
    return tuple(
        ((re_lo, re_hi), (im_lo, im_hi))
        for re_lo, re_hi, im_lo, im_hi in FRAME_FACTOR.iter_unpack(raw)
    )


def replay_formulaic_cuda_arithmetic(
    parsed: ParsedFormulaicServiceStream,
    seed_artifact_path: Path,
    output_stream_path: Path,
    *,
    expected_output_sha256: str,
    maximum_values_per_frame: int = 4,
    maximum_output_bytes: int = DEFAULT_MAXIMUM_OUTPUT_BYTES,
    independent_arb_factor_precision_bits: int | None = None,
) -> dict[str, Any]:
    """Exactly replay a bounded sample of directed CUDA binary64 arithmetic."""

    maximum_values_per_frame = _positive_integer(
        maximum_values_per_frame,
        "maximum values per frame",
        64,
    )
    output_raw = _bounded_read(
        output_stream_path,
        maximum_output_bytes,
        label="formulaic TGDAFFI1 arithmetic output",
    )
    expected_output_sha256 = _digest(
        expected_output_sha256, "expected formulaic TGDAFFI1 output"
    )
    if hashlib.sha256(output_raw).hexdigest() != expected_output_sha256:
        _fail("formulaic TGDAFFI1 output digest differs")

    offset = 0
    observations: dict[tuple[int, int], tuple[float, float, float, float]] = {}
    blocks: list[Any] = []
    for frame_index, frame in enumerate(parsed.frames):
        if offset + TGDAFFI_HEADER.size > len(output_raw):
            _fail("truncated formulaic TGDAFFI1 header")
        header = TGDAFFI_HEADER.unpack_from(output_raw, offset)
        offset += TGDAFFI_HEADER.size
        target = frame.target
        expected_header = (
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
        )
        if header != expected_header:
            _fail("formulaic TGDAFFI1 header differs from its target")
        selected = arithmetic._sample_indices(
            frame.value_count, maximum_values_per_frame
        )
        selected_set = set(selected)
        for flat in range(frame.value_count):
            if offset + COMPLEX_INTERVAL.size > len(output_raw):
                _fail("truncated formulaic TGDAFFI1 values")
            value = COMPLEX_INTERVAL.unpack_from(output_raw, offset)
            offset += COMPLEX_INTERVAL.size
            if (
                not all(math.isfinite(endpoint) for endpoint in value)
                or value[0] > value[1]
                or value[2] > value[3]
            ):
                _fail("formulaic TGDAFFI1 interval is malformed")
            if flat in selected_set:
                observations[(frame_index, flat)] = tuple(value)
        target_model = arithmetic._Target(
            q=target.q,
            component_count=frame.component_count,
            batch_count=target.batch_count,
            group_order=frame.group_order,
            first_t_numerator=(
                target.first_t_index * SOURCE_SAMPLE_NUMERATOR
            ),
            t_denominator=SOURCE_SAMPLE_DENOMINATOR,
            t_step_numerator=SOURCE_SAMPLE_NUMERATOR,
            value_count=frame.value_count,
            factors=_factor_intervals(frame.factors),
            tails=tuple(
                value[0] for value in struct.iter_unpack("<d", frame.tails)
            ),
        )
        blocks.append(
            arithmetic._Block(
                lane_index=target.lane_index,
                first_t_index=target.first_t_index,
                rows=frame.rows,
                targets=(target_model,),
                artifact_sha256=parsed.input_stream_sha256,
                artifact_size=parsed.input_stream_size_bytes,
                sidecar_mode=-1,
            )
        )
    if offset != len(output_raw):
        _fail("formulaic TGDAFFI1 output has trailing bytes")

    required_x: set[int] = set()
    residue_orders: list[tuple[int, ...]] = []
    for frame, block in zip(parsed.frames, blocks, strict=True):
        residues = canonical_residue_order(frame.target.q)
        residue_orders.append(residues)
        for flat in arithmetic._sample_indices(
            frame.value_count, maximum_values_per_frame
        ):
            _ordinate, position = divmod(flat, frame.group_order)
            a = residues[position]
            for n in range(arithmetic.seed_format.SOURCE_M + 1):
                required_x.add(frame.target.q * n + a)
    seed_lookup, seed_bytes = arithmetic._load_seed_lookup(
        seed_artifact_path,
        frozenset(required_x),
        expected_sha256=parsed.recovery_seed_sha256,
    )

    roster_digest = hashlib.sha256()
    sampled = 0
    for frame_index, (frame, block, residues) in enumerate(
        zip(parsed.frames, blocks, residue_orders, strict=True)
    ):
        target_model = block.targets[0]
        for flat in arithmetic._sample_indices(
            frame.value_count, maximum_values_per_frame
        ):
            expected = arithmetic._flatten(
                arithmetic._recompute_value(
                    block,
                    target_model,
                    flat=flat,
                    residues=residues,
                    seeds=seed_lookup,
                )
            )
            observed = observations[(frame_index, flat)]
            if expected != observed:
                _fail(
                    "exact formulaic CUDA arithmetic differs at "
                    f"q={frame.target.q}, flat={flat}"
                )
            roster_digest.update(
                struct.pack(
                    "<QIQ",
                    frame.target.execution_q_index,
                    frame.target.q,
                    flat,
                )
            )
            roster_digest.update(COMPLEX_INTERVAL.pack(*observed))
            sampled += 1

    arb_count = 0
    arb_runtime: dict[str, Any] | None = None
    if independent_arb_factor_precision_bits is not None:
        runtimes: list[dict[str, Any]] = []
        for block in blocks:
            count, runtime = arithmetic._independent_arb_factor_replay(
                block,
                precision_bits=independent_arb_factor_precision_bits,
            )
            arb_count += count
            runtimes.append(runtime)
        if runtimes:
            if any(runtime != runtimes[0] for runtime in runtimes[1:]):
                _fail("independent Arb runtime changed during replay")
            arb_runtime = runtimes[0]

    body: dict[str, Any] = {
        "schema": REPLAY_SCHEMA,
        "schema_version": FORMAT_VERSION,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "bounded_exact_fraction_cuda_replay_not_source_or_zero_closure"
        ),
        "input_stream_sha256": parsed.input_stream_sha256,
        "output_stream_sha256": expected_output_sha256,
        "output_stream_size_bytes": len(output_raw),
        "recovery_seed_artifact_sha256": parsed.recovery_seed_sha256,
        "recovery_seed_artifact_size_bytes": seed_bytes,
        "target_count": len(parsed.frames),
        "sampled_output_value_count": sampled,
        "sample_roster_and_values_sha256": roster_digest.hexdigest(),
        "exact_fraction_intermediate_rounding_used": True,
        "directed_binary64_cuda_endpoints_matched": True,
        "independent_Arb_factor_containment_count": arb_count,
        "independent_Arb_factor_runtime": arb_runtime,
        "production_run_completed": False,
        "source_scale_run": False,
        "trusted_execution_attested": False,
        "recovery_seed_analytic_containment_replayed": False,
        "completed_l_zero_state_validated": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }
    body["replay_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return body


def capability() -> dict[str, Any]:
    source_raw_lattice_bytes = PINNED_SOURCE_ROWS * ROW_PAYLOAD_BYTES
    return {
        "algorithm_id": ALGORITHM_ID,
        "descriptor_free_formulaic_binary_service_implemented": True,
        "maximum_rows_per_frame": MAXIMUM_BATCH_COUNT,
        "serialized_control_records_required": 0,
        "canonical_descriptor_input_bytes": 0,
        "descriptor_reconstruction_cached_by_actual_q": True,
        "TGDAFFI1_stream_output": True,
        "bounded_exact_fraction_arithmetic_replay": True,
        "bounded_real_cuda_kat_implemented": True,
        "bounded_real_cuda_kat_completed": False,
        "full_source_schedule_accepted": False,
        "source_lattice_spools_populated": False,
        "source_formulaic_lattice_rows_reread_and_uploaded_if_executed": (
            PINNED_SOURCE_ROWS
        ),
        "source_formulaic_raw_lattice_transfer_bytes_if_executed": (
            source_raw_lattice_bytes
        ),
        "preserves_tmajor_one_upload_per_physical_row": False,
        "economical_production_storage_solution": False,
        "next_required_scaling_seam": (
            "t-major-one-upload-per-row-with-keyed-persistent-downstream-"
            "fft-sign-state"
        ),
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
        "completed_l_zero_state_validated": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "DEFAULT_MAXIMUM_OUTPUT_BYTES",
    "DEFAULT_MAXIMUM_STREAM_BYTES",
    "DirichletFormulaicQMajorServiceError",
    "FRAME_HEADER",
    "FormulaicServiceFrame",
    "HEADER_MAGIC",
    "LANE_RECORD",
    "ParsedFormulaicServiceStream",
    "SERVICE_FOOTER",
    "SERVICE_HEADER",
    "SUMMARY_SCHEMA",
    "capability",
    "replay_formulaic_cuda_arithmetic",
    "replay_formulaic_service_stream",
    "validate_formulaic_cuda_summary",
    "write_formulaic_service_stream",
]
