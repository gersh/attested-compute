# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Assemble validated PT21 finite outputs into canonical ``PT21BLK1`` records.

The source-scale CUDA worker, stationary resolver, and Arb Turing-input
producer deliberately expose separate finite boundaries.  This module joins
those boundaries without upgrading them to analytic facts:

* the required-region packet is decoded and every DD sign is rechecked;
* the stationary trace is independently validated and must be complete;
* the Turing-input artifact is bound to the same block and packet;
* the fused source trace and exact-rational block artifact are rebuilt; and
* the resulting counts and commitments are encoded as one fixed-width native
  record accepted by the production-scale finalizer.

The retained record still has no Hardy-Z, multiplicity, analytic Turing, or
Lean source semantics.  A measured all-window worker must stream these inputs
into this adapter (or implement the same wire directly) before the optimized
Azure route can be enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import struct
import subprocess
import tempfile
from typing import Any, BinaryIO, Callable

from tg_verifier.platt_pt21_fused_artifact import (
    INTERPOLATION_PATCH_SHA256,
    PT21FusedArtifactError,
    SOURCE_HEIGHT,
    TRACE_SCHEMA,
    UPSTREAM_COMMIT,
    build_block_artifact_from_packet,
    build_block_artifact_from_prevalidated_scan,
)
from tg_verifier.platt_pt21_lean_artifact import (
    SOURCE_HALF_STEP,
    SOURCE_LOWER,
    SOURCE_SPACING,
    SOURCE_STEP,
)
from tg_verifier.platt_pt21_native_finalizer import (
    BLOCK_RECORD,
    SOURCE_HEIGHT_BLOCK,
    PT21NativeFinalizerError,
    encode_block_record,
    parse_block_record,
)
from tg_verifier.platt_pt21_turing_inputs import (
    MAX_BYTES as TURING_MAXIMUM_BYTES,
    PT21TuringInputsError,
    validate as validate_turing_inputs,
)
from tg_verifier.platt_required_sign_packet import (
    PlattRequiredSignPacketError,
    REQUIRED_COUNT,
    load_required_sign_packet,
)
from tg_verifier.platt_stationary_trace import (
    MAXIMUM_BYTES as STATIONARY_MAXIMUM_BYTES,
    PT21StationaryTraceError,
    validate as validate_stationary_trace,
)
from tg_verifier.platt_pt21_native_scan_fastpath import (
    NativePacketScan,
    NativeScanSession,
    PT21NativeScanFastpathError,
    scan_required_sign_packet,
    scan_required_sign_packet_with_session,
)


MANIFEST_SCHEMA = "sparkinterval.tg.platt-pt21-native-record-manifest-row.v1"
REPORT_SCHEMA = "sparkinterval.tg.platt-pt21-native-record-adapter.v1"
SHARD_REPORT_SCHEMA = (
    "sparkinterval.tg.platt-pt21-native-record-streamed-shard.v1"
)
MANIFEST_ROW_MAXIMUM_BYTES = 64 * 1024
STREAM_AUTH_FOOTER = struct.Struct("<8sII32s")
STREAM_AUTH_MAGIC = b"PT21END1"
NATIVE_SHARD_SUMMARY_SCHEMA = (
    "sparkinterval.tg.platt-pt21-native-shard-summary.v1"
)
NATIVE_SHARD_SUMMARY_FIELDS = {
    "archive_sha256",
    "archive_size_bytes",
    "block_count",
    "first_block",
    "first_count",
    "last_count",
    "mode",
    "schema",
    "source_claim_ready",
    "source_height_count",
    "total_main_slots",
    "total_sparse_refinements",
    "total_stationary_resolutions",
    "upper_block_exclusive",
}


class PT21NativeRecordAdapterError(RuntimeError):
    """A finite input, path, count, or native-record relationship failed."""


@dataclass(frozen=True)
class WorkerIdentity:
    path: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class AdaptedBlock:
    block: int
    record: bytes
    record_sha256: str
    required_packet_sha256: str
    stationary_trace_sha256: str
    turing_inputs_sha256: str
    source_trace: bytes
    source_trace_sha256: str
    block_artifact: bytes
    block_artifact_sha256: str
    lower_count: int
    upper_count: int
    main_slots: int
    stationary_resolution_count: int
    sparse_refinement_count: int
    source_height_count: int | None
    worker: WorkerIdentity


@dataclass(frozen=True)
class NativeFastpathAdaptation:
    """Explicit qualification result; never selected by manifest production."""

    adapted: AdaptedBlock
    scan: NativePacketScan


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PT21NativeRecordAdapterError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _open_regular(path: Path, label: str) -> tuple[BinaryIO, int]:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as error:
        raise PT21NativeRecordAdapterError(
            f"cannot open {label} without following links: {path}: {error}"
        ) from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size < 1:
            raise PT21NativeRecordAdapterError(
                f"{label} is not a nonempty regular file: {path}"
            )
        return os.fdopen(descriptor, "rb", closefd=True), metadata.st_size
    except Exception:
        os.close(descriptor)
        raise


def _load_canonical_json_once(
    path: Path, *, maximum: int, label: str
) -> tuple[dict[str, Any], bytes]:
    stream, size = _open_regular(path, label)
    with stream:
        if size > maximum:
            raise PT21NativeRecordAdapterError(f"{label} exceeds its byte cap")
        raw = stream.read(maximum + 1)
    if len(raw) != size:
        raise PT21NativeRecordAdapterError(f"{label} changed while being read")
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PT21NativeRecordAdapterError(
            f"{label} is not strict JSON: {error}"
        ) from error
    if not isinstance(value, dict) or raw != _canonical(value) + b"\n":
        raise PT21NativeRecordAdapterError(
            f"{label} is not one canonical JSON object with one newline"
        )
    return value, raw


def worker_identity(path: Path) -> WorkerIdentity:
    """Hash one non-symlink worker executable from a single open descriptor."""

    stream, size = _open_regular(path, "measured worker")
    if os.fstat(stream.fileno()).st_mode & 0o111 == 0:
        stream.close()
        raise PT21NativeRecordAdapterError(
            "measured worker is not executable"
        )
    digest = hashlib.sha256()
    consumed = 0
    with stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            consumed += len(chunk)
        final_size = os.fstat(stream.fileno()).st_size
    if consumed != size or final_size != size:
        raise PT21NativeRecordAdapterError(
            "measured worker changed while being hashed"
        )
    return WorkerIdentity(path=path, sha256=digest.hexdigest(), size_bytes=size)


def _sha256_hex(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PT21NativeRecordAdapterError(
            f"{label} is not lowercase SHA-256"
        )
    return value


def _pinned_executable(
    path: Path, *, expected_sha256: str, label: str
) -> tuple[int, WorkerIdentity]:
    """Open, hash, and retain one executable descriptor through ``execve``."""

    expected = _sha256_hex(expected_sha256, f"expected {label} SHA-256")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as error:
        raise PT21NativeRecordAdapterError(
            f"cannot open {label} without following links: {path}: {error}"
        ) from error
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size < 1
            or metadata.st_mode & 0o111 == 0
        ):
            raise PT21NativeRecordAdapterError(
                f"{label} is not a nonempty executable regular file"
            )
        digest = hashlib.sha256()
        consumed = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            consumed += len(chunk)
        final = os.fstat(descriptor)
        actual = digest.hexdigest()
        if (
            consumed != metadata.st_size
            or final.st_size != metadata.st_size
            or actual != expected
        ):
            raise PT21NativeRecordAdapterError(
                f"{label} bytes differ from the pinned executable"
            )
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor, WorkerIdentity(
            path=path,
            sha256=actual,
            size_bytes=metadata.st_size,
        )
    except Exception:
        os.close(descriptor)
        raise


def _fraction(value: dict[str, int]) -> Fraction:
    return Fraction(value["numerator"], value["denominator"])


def _source_height_count(
    artifact: dict[str, object], *, block: int
) -> int | None:
    if block != SOURCE_HEIGHT_BLOCK:
        return None
    lower_count = int(artifact["turing"]["lower"]["count"])
    center = Fraction(int(artifact["window_center"]))
    target = Fraction(SOURCE_HEIGHT)
    below = 0
    for index, bracket in enumerate(artifact["streams"]["main"]["brackets"]):
        lower = center + _fraction(bracket["lower_offset"]) * SOURCE_SPACING
        upper = center + _fraction(bracket["upper_offset"]) * SOURCE_SPACING
        if upper <= target:
            below += 1
        elif lower >= target:
            continue
        else:
            raise PT21NativeRecordAdapterError(
                f"main bracket {index} straddles the exact PT21 source height"
            )
    return lower_count + below


def _fused_trace(
    *,
    block: int,
    packet_sha256: str,
    stationary: dict[str, Any],
    turing: dict[str, object],
    worker: WorkerIdentity,
) -> tuple[dict[str, object], bytes]:
    value: dict[str, object] = {
        "schema": TRACE_SCHEMA,
        "upstream_commit": UPSTREAM_COMMIT,
        "interpolation_patch_sha256": INTERPOLATION_PATCH_SHA256,
        "block": block,
        "required_sign_packet_sha256": packet_sha256,
        "producer": {
            "worker_sha256": worker.sha256,
            "worker_size_bytes": worker.size_bytes,
            "precision_bits": 128,
            "all_required_samples_certified": True,
            "all_stationary_queries_resolved": True,
        },
        "stationary_resolutions": stationary["stationary_resolutions"],
        "turing_inputs": turing["turing_inputs"],
        "semantic_status": {
            "hardy_z_endpoint_realization_proved": False,
            "main_multiplicity_realization_proved": False,
            "analytic_turing_realization_proved": False,
        },
    }
    return value, _canonical(value) + b"\n"


def adapt_block(
    *,
    required_sign_packet: Path,
    stationary_trace: Path,
    turing_inputs: Path,
    worker: Path | WorkerIdentity,
) -> AdaptedBlock:
    """Rebuild one complete finite block and return its canonical record."""

    identity = (
        worker
        if isinstance(worker, WorkerIdentity)
        else worker_identity(worker)
    )
    try:
        packet = load_required_sign_packet(required_sign_packet)
    except (OSError, PlattRequiredSignPacketError) as error:
        raise PT21NativeRecordAdapterError(
            f"required-sign packet failed: {error}"
        ) from error
    return _adapt_validated_packet(
        packet_sha256=packet.sha256,
        window_center=packet.window_center,
        stationary_trace=stationary_trace,
        turing_inputs=turing_inputs,
        worker=identity,
        artifact_builder=lambda trace_path: build_block_artifact_from_packet(
            packet, trace_path
        ),
    )


def _adapt_validated_packet(
    *,
    packet_sha256: str,
    window_center: int,
    stationary_trace: Path,
    turing_inputs: Path,
    worker: WorkerIdentity,
    artifact_builder: Callable[[Path], dict[str, object]],
) -> AdaptedBlock:
    """Shared exact Turing/artifact/record tail after packet scan replay."""

    block_delta = window_center - (SOURCE_LOWER + SOURCE_HALF_STEP)
    if block_delta < 0 or block_delta % SOURCE_STEP:
        raise PT21NativeRecordAdapterError(
            "required-sign packet center is off the PT21 source grid"
        )
    block = block_delta // SOURCE_STEP

    stationary_value, stationary_raw = _load_canonical_json_once(
        stationary_trace,
        maximum=STATIONARY_MAXIMUM_BYTES,
        label="stationary trace",
    )
    try:
        stationary = validate_stationary_trace(stationary_value)
    except PT21StationaryTraceError as error:
        raise PT21NativeRecordAdapterError(
            f"stationary trace failed: {error}"
        ) from error
    if (
        stationary["accepted"] is not True
        or stationary["replay_accepted"] is not True
    ):
        raise PT21NativeRecordAdapterError(
            "stationary trace did not complete independent replay"
        )

    turing_value, turing_raw = _load_canonical_json_once(
        turing_inputs,
        maximum=TURING_MAXIMUM_BYTES,
        label="Turing input artifact",
    )
    try:
        turing = validate_turing_inputs(
            turing_value,
            expected_block=block,
            expected_packet_sha256=packet_sha256,
        )
    except PT21TuringInputsError as error:
        raise PT21NativeRecordAdapterError(
            f"Turing input artifact failed: {error}"
        ) from error

    _trace_value, trace_raw = _fused_trace(
        block=block,
        packet_sha256=packet_sha256,
        stationary=stationary,
        turing=turing,
        worker=worker,
    )
    # The existing fused finalizer accepts a path so that its ordinary CLI can
    # share the same strict decoder.  Keep this internal file ephemeral: only
    # its canonical digest enters the retained 320-byte record.
    with tempfile.TemporaryDirectory(prefix="pt21-native-record-") as temporary:
        trace_path = Path(temporary) / "source-trace.json"
        trace_path.write_bytes(trace_raw)
        try:
            artifact = artifact_builder(trace_path)
        except (OSError, PT21FusedArtifactError) as error:
            raise PT21NativeRecordAdapterError(
                f"fused block reconstruction failed: {error}"
            ) from error
    if (
        artifact["block"] != block
        or artifact["required_sign_packet_sha256"] != packet_sha256
        or artifact["source_trace_sha256"] != hashlib.sha256(trace_raw).hexdigest()
    ):
        raise PT21NativeRecordAdapterError(
            "fused block reconstruction changed its bound identities"
        )

    artifact_raw = _canonical(artifact) + b"\n"
    lower_count = int(artifact["turing"]["lower"]["count"])
    upper_count = int(artifact["turing"]["upper"]["count"])
    main_slots = len(artifact["streams"]["main"]["brackets"])
    stationary_count = int(stationary["candidate_count"])
    sparse_count = int(stationary["refinements_applied"])
    ambiguous_count = int(stationary["ambiguous_input_disks"])
    source_count = _source_height_count(artifact, block=block)
    stationary_sha256 = hashlib.sha256(stationary_raw).hexdigest()
    try:
        record = encode_block_record(
            block=block,
            lower_count=lower_count,
            upper_count=upper_count,
            main_slots=main_slots,
            stationary_resolution_count=stationary_count,
            sparse_refinement_count=sparse_count,
            initial_ambiguous_count=ambiguous_count,
            invalid_disk_count=0,
            unresolved_disk_count=0,
            unresolved_stationary_count=0,
            turing_failure_count=0,
            replay_failure_count=0,
            source_height_count=source_count,
            source_height_slots_from_lower=(
                0 if source_count is None else source_count - lower_count
            ),
            required_packet_sha256=packet_sha256,
            source_trace_sha256=hashlib.sha256(trace_raw).hexdigest(),
            block_artifact_sha256=hashlib.sha256(artifact_raw).hexdigest(),
            stationary_trace_sha256=(
                stationary_sha256 if stationary_count else None
            ),
            sparse_refinement_sha256=(
                stationary_sha256 if sparse_count else None
            ),
            producer_commitment_sha256=worker.sha256,
        )
        parsed = parse_block_record(record, expected_block=block)
    except PT21NativeFinalizerError as error:
        raise PT21NativeRecordAdapterError(
            f"native block encoding failed: {error}"
        ) from error
    if parsed.required_packet_sha256.hex() != packet_sha256:
        raise PT21NativeRecordAdapterError(
            "native record lost the required-packet commitment"
        )
    return AdaptedBlock(
        block=block,
        record=record,
        record_sha256=parsed.record_sha256.hex(),
        required_packet_sha256=packet_sha256,
        stationary_trace_sha256=stationary_sha256,
        turing_inputs_sha256=hashlib.sha256(turing_raw).hexdigest(),
        source_trace=trace_raw,
        source_trace_sha256=hashlib.sha256(trace_raw).hexdigest(),
        block_artifact=artifact_raw,
        block_artifact_sha256=hashlib.sha256(artifact_raw).hexdigest(),
        lower_count=lower_count,
        upper_count=upper_count,
        main_slots=main_slots,
        stationary_resolution_count=stationary_count,
        sparse_refinement_count=sparse_count,
        source_height_count=source_count,
        worker=worker,
    )


def adapt_block_native_scan_fastpath(
    *,
    required_sign_packet: Path,
    stationary_trace: Path,
    turing_inputs: Path,
    worker: Path | WorkerIdentity,
    native_scanner: Path,
    expected_native_scanner_sha256: str,
) -> NativeFastpathAdaptation:
    """Qualification-only pinned native scan plus exact reference tail.

    This function is intentionally absent from the manifest/shard production
    API.  The returned ``PT21BLK1`` must be byte-identical to :func:`adapt_block`
    in differential qualification; the native scanner identity and its
    nonterminal certificate remain explicit in the wrapper result.
    """

    identity = (
        worker
        if isinstance(worker, WorkerIdentity)
        else worker_identity(worker)
    )
    try:
        scan = scan_required_sign_packet(
            required_sign_packet,
            scanner=native_scanner,
            expected_scanner_sha256=expected_native_scanner_sha256,
        )
    except (OSError, PT21NativeScanFastpathError) as error:
        raise PT21NativeRecordAdapterError(
            f"qualification-only native packet scan failed: {error}"
        ) from error
    return _adapt_block_from_validated_native_scan(
        scan=scan,
        stationary_trace=stationary_trace,
        turing_inputs=turing_inputs,
        worker=identity,
    )


def _adapt_block_from_validated_native_scan(
    *,
    scan: NativePacketScan,
    stationary_trace: Path,
    turing_inputs: Path,
    worker: Path | WorkerIdentity,
) -> NativeFastpathAdaptation:
    """Run the exact adapter tail from one independently validated scan."""

    identity = (
        worker
        if isinstance(worker, WorkerIdentity)
        else worker_identity(worker)
    )
    adapted = _adapt_validated_packet(
        packet_sha256=scan.packet_sha256,
        window_center=scan.window_center,
        stationary_trace=stationary_trace,
        turing_inputs=turing_inputs,
        worker=identity,
        artifact_builder=lambda trace_path: (
            build_block_artifact_from_prevalidated_scan(
                packet_sha256=scan.packet_sha256,
                window_center=scan.window_center,
                sample_count=REQUIRED_COUNT,
                direct_offsets=scan.direct_offsets,
                stationary_offsets=scan.stationary_offsets,
                positive_at=scan.positive_at,
                interval_at=scan.interval_at,
                source_trace=trace_path,
            )
        ),
    )
    return NativeFastpathAdaptation(adapted=adapted, scan=scan)


def adapt_block_native_scan_session(
    *,
    required_sign_packet: Path,
    stationary_trace: Path,
    turing_inputs: Path,
    worker: Path | WorkerIdentity,
    session: NativeScanSession,
) -> NativeFastpathAdaptation:
    """Qualification-only adapter through one already pinned scan session."""

    identity = (
        worker
        if isinstance(worker, WorkerIdentity)
        else worker_identity(worker)
    )
    try:
        scan = scan_required_sign_packet_with_session(
            required_sign_packet,
            session=session,
        )
    except (OSError, PT21NativeScanFastpathError) as error:
        raise PT21NativeRecordAdapterError(
            f"qualification-only persistent packet scan failed: {error}"
        ) from error
    return _adapt_block_from_validated_native_scan(
        scan=scan,
        stationary_trace=stationary_trace,
        turing_inputs=turing_inputs,
        worker=identity,
    )


def _safe_manifest_path(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str):
        raise PT21NativeRecordAdapterError(f"{label} path is not a string")
    pure = PurePosixPath(value)
    if (
        not value
        or pure.is_absolute()
        or value != pure.as_posix()
        or any(part in ("", ".", "..") for part in pure.parts)
    ):
        raise PT21NativeRecordAdapterError(
            f"{label} is not a safe relative POSIX path"
        )
    candidate = root
    for part in pure.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise PT21NativeRecordAdapterError(
                f"{label} traverses a symbolic link"
            )
    return candidate


def _write_all(stream: BinaryIO, raw: bytes) -> None:
    view = memoryview(raw)
    while view:
        written = stream.write(view)
        if written is None or written <= 0:
            raise PT21NativeRecordAdapterError("short native-record write")
        view = view[written:]


def write_exclusive(path: Path, raw: bytes) -> None:
    """Write a retained output once, never following or replacing a path."""

    descriptor = -1
    created = False
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_CLOEXEC
            | getattr(os, "O_NOFOLLOW", 0),
            0o400,
        )
        created = True
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            _write_all(stream, raw)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        if created:
            path.unlink(missing_ok=True)
        raise


def _adapt_manifest_to_stream(
    manifest: Path,
    *,
    destination: BinaryIO,
    worker: WorkerIdentity,
    first_block: int,
    block_count: int,
    expected_manifest_sha256: str | None,
) -> dict[str, object]:
    if first_block < 0 or block_count < 1:
        raise PT21NativeRecordAdapterError(
            "manifest shard geometry must be nonempty"
        )
    expected_manifest = (
        None
        if expected_manifest_sha256 is None
        else _sha256_hex(
            expected_manifest_sha256, "expected record-adapter manifest SHA-256"
        )
    )
    source, source_size = _open_regular(manifest, "record-adapter manifest")
    records_sha256 = hashlib.sha256()
    manifest_sha256 = hashlib.sha256()
    produced = 0
    total_slots = 0
    total_stationary = 0
    total_sparse = 0
    source_height_count: int | None = None
    first_count: int | None = None
    previous_upper_count: int | None = None
    with source:
        consumed = 0
        for line_number, raw in enumerate(source, start=1):
            consumed += len(raw)
            manifest_sha256.update(raw)
            if len(raw) > MANIFEST_ROW_MAXIMUM_BYTES:
                raise PT21NativeRecordAdapterError(
                    f"manifest row {line_number} exceeds its byte cap"
                )
            try:
                row = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise PT21NativeRecordAdapterError(
                    f"manifest row {line_number} is not strict JSON: {error}"
                ) from error
            if (
                not isinstance(row, dict)
                or set(row)
                != {
                    "required_sign_packet",
                    "schema",
                    "stationary_trace",
                    "turing_inputs",
                }
                or row["schema"] != MANIFEST_SCHEMA
                or raw != _canonical(row) + b"\n"
            ):
                raise PT21NativeRecordAdapterError(
                    f"manifest row {line_number} is not canonical or has wrong fields"
                )
            root = manifest.parent
            adapted = adapt_block(
                required_sign_packet=_safe_manifest_path(
                    root, row["required_sign_packet"], "required_sign_packet"
                ),
                stationary_trace=_safe_manifest_path(
                    root, row["stationary_trace"], "stationary_trace"
                ),
                turing_inputs=_safe_manifest_path(
                    root, row["turing_inputs"], "turing_inputs"
                ),
                worker=worker,
            )
            expected = first_block + produced
            if adapted.block != expected:
                raise PT21NativeRecordAdapterError(
                    "manifest block records are not gap-free and ordered"
                )
            if (
                previous_upper_count is not None
                and adapted.lower_count != previous_upper_count
            ):
                raise PT21NativeRecordAdapterError(
                    "manifest block counts do not telescope"
                )
            _write_all(destination, adapted.record)
            records_sha256.update(adapted.record)
            produced += 1
            if first_count is None:
                first_count = adapted.lower_count
            total_slots += adapted.main_slots
            total_stationary += adapted.stationary_resolution_count
            total_sparse += adapted.sparse_refinement_count
            if adapted.source_height_count is not None:
                if source_height_count is not None:
                    raise PT21NativeRecordAdapterError(
                        "manifest repeats the unique source-height count"
                    )
                source_height_count = adapted.source_height_count
            previous_upper_count = adapted.upper_count
            if produced > block_count:
                raise PT21NativeRecordAdapterError(
                    "manifest contains more records than its declared shard"
                )
        final_size = os.fstat(source.fileno()).st_size
        if consumed != source_size or final_size != source_size:
            raise PT21NativeRecordAdapterError(
                "record-adapter manifest changed while being read"
            )
        if produced != block_count:
            raise PT21NativeRecordAdapterError(
                "record-adapter manifest is a strict prefix"
            )
    actual_manifest = manifest_sha256.hexdigest()
    if expected_manifest is not None and actual_manifest != expected_manifest:
        raise PT21NativeRecordAdapterError(
            "record-adapter manifest SHA-256 differs from the pinned stream"
        )
    assert first_count is not None
    assert previous_upper_count is not None
    return {
        "schema": REPORT_SCHEMA,
        "accepted": True,
        "manifest_sha256": actual_manifest,
        "manifest_sha256_authenticated": expected_manifest is not None,
        "first_block": first_block,
        "upper_block_exclusive": first_block + produced,
        "block_count": produced,
        "first_count": first_count,
        "last_count": previous_upper_count,
        "record_bytes": BLOCK_RECORD.size,
        "record_stream_bytes": produced * BLOCK_RECORD.size,
        "record_stream_sha256": records_sha256.hexdigest(),
        "total_main_slots": total_slots,
        "total_stationary_resolutions": total_stationary,
        "total_sparse_refinements": total_sparse,
        "source_height_count": source_height_count,
        "worker_sha256": worker.sha256,
        "finite_record_wire_ready": True,
        "hardy_z_endpoint_realization_proved": False,
        "main_multiplicity_realization_proved": False,
        "analytic_turing_realization_proved": False,
        "lean_source_claim_ready": False,
        "source_claim_ready": False,
    }


def adapt_manifest_stream(
    manifest: Path,
    *,
    destination: BinaryIO,
    worker: Path | WorkerIdentity,
    first_block: int,
    block_count: int,
    expected_manifest_sha256: str,
) -> dict[str, object]:
    """Write records online, authenticating the complete manifest before success."""

    identity = (
        worker
        if isinstance(worker, WorkerIdentity)
        else worker_identity(worker)
    )
    return _adapt_manifest_to_stream(
        manifest,
        destination=destination,
        worker=identity,
        first_block=first_block,
        block_count=block_count,
        expected_manifest_sha256=expected_manifest_sha256,
    )


def adapt_manifest(
    manifest: Path,
    *,
    output: Path,
    worker: Path,
    first_block: int,
    block_count: int,
    expected_manifest_sha256: str | None = None,
) -> dict[str, object]:
    """Stream a strict JSON-lines shard manifest into native block records."""

    identity = worker_identity(worker)
    descriptor = -1
    created = False
    try:
        descriptor = os.open(
            output,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_CLOEXEC
            | getattr(os, "O_NOFOLLOW", 0),
            0o400,
        )
        created = True
        with os.fdopen(descriptor, "wb", closefd=True) as destination:
            descriptor = -1
            report = _adapt_manifest_to_stream(
                manifest,
                destination=destination,
                worker=identity,
                first_block=first_block,
                block_count=block_count,
                expected_manifest_sha256=expected_manifest_sha256,
            )
            destination.flush()
            os.fsync(destination.fileno())
        return report
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        if created:
            output.unlink(missing_ok=True)
        raise


def _native_summary(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PT21NativeRecordAdapterError(
            f"native finalizer summary is not strict JSON: {error}"
        ) from error
    if (
        not isinstance(value, dict)
        or set(value) != NATIVE_SHARD_SUMMARY_FIELDS
        or value["schema"] != NATIVE_SHARD_SUMMARY_SCHEMA
        or raw != _canonical(value) + b"\n"
    ):
        raise PT21NativeRecordAdapterError(
            "native finalizer summary is noncanonical or has wrong fields"
        )
    return value


def _hash_retained_archive(path: Path) -> tuple[str, int]:
    stream, size = _open_regular(path, "native shard archive")
    digest = hashlib.sha256()
    consumed = 0
    with stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            consumed += len(chunk)
        final_size = os.fstat(stream.fileno()).st_size
    if consumed != size or final_size != size:
        raise PT21NativeRecordAdapterError(
            "native shard archive changed while being hashed"
        )
    return digest.hexdigest(), size


def adapt_manifest_to_native_shard(
    manifest: Path,
    *,
    worker: Path,
    finalizer: Path,
    expected_finalizer_sha256: str,
    expected_manifest_sha256: str,
    output: Path,
    first_block: int,
    block_count: int,
    plan_sha256: str,
    prefix_evidence_sha256: str,
    bounded_test: bool,
    finalizer_exit_timeout_seconds: int = 300,
) -> dict[str, object]:
    """Adapt and finalize a shard without retaining an intermediate record file."""

    if (
        isinstance(finalizer_exit_timeout_seconds, bool)
        or not 1 <= finalizer_exit_timeout_seconds <= 3600
    ):
        raise PT21NativeRecordAdapterError(
            "native finalizer exit timeout is outside 1..3600 seconds"
        )
    if not isinstance(bounded_test, bool):
        raise PT21NativeRecordAdapterError(
            "bounded_test must be Boolean"
        )
    if output.exists() or output.is_symlink():
        raise PT21NativeRecordAdapterError(
            "native shard output already exists"
        )
    expected_manifest = _sha256_hex(
        expected_manifest_sha256, "expected record-adapter manifest SHA-256"
    )
    plan = _sha256_hex(plan_sha256, "plan SHA-256")
    prefix = _sha256_hex(
        prefix_evidence_sha256, "prefix-evidence SHA-256"
    )
    identity = worker_identity(worker)
    executable_descriptor = -1
    process: subprocess.Popen[bytes] | None = None
    try:
        executable_descriptor, finalizer_identity = _pinned_executable(
            finalizer,
            expected_sha256=expected_finalizer_sha256,
            label="native finalizer",
        )
        executable = f"/proc/self/fd/{executable_descriptor}"
        command = [
            executable,
            "shard",
            "--input",
            "-",
            "--stream-auth-sha256",
            expected_manifest,
            "--output",
            str(output),
            "--first-block",
            str(first_block),
            "--block-count",
            str(block_count),
            "--worker-sha256",
            identity.sha256,
            "--plan-sha256",
            plan,
            "--prefix-evidence-sha256",
            prefix,
        ]
        if bounded_test:
            command.append("--bounded-test")
        process = subprocess.Popen(
            command,
            executable=executable,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(executable_descriptor,),
        )
    except (OSError, ValueError) as error:
        raise PT21NativeRecordAdapterError(
            f"cannot start pinned native finalizer: {error}"
        ) from error
    finally:
        if executable_descriptor >= 0:
            os.close(executable_descriptor)
    assert process is not None
    assert process.stdin is not None
    try:
        adapter_report = adapt_manifest_stream(
            manifest,
            destination=process.stdin,
            worker=identity,
            first_block=first_block,
            block_count=block_count,
            expected_manifest_sha256=expected_manifest,
        )
        _write_all(
            process.stdin,
            STREAM_AUTH_FOOTER.pack(
                STREAM_AUTH_MAGIC,
                1,
                STREAM_AUTH_FOOTER.size,
                bytes.fromhex(expected_manifest),
            ),
        )
        process.stdin.flush()
        process.stdin.close()
        process.stdin = None
        try:
            stdout, stderr = process.communicate(
                timeout=finalizer_exit_timeout_seconds
            )
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.communicate()
            raise PT21NativeRecordAdapterError(
                "native finalizer did not terminate after authenticated EOF"
            ) from error
    except Exception as error:
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
            process.stdin = None
        try:
            _stdout, stderr = process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            _stdout, stderr = process.communicate()
        diagnostic = stderr.decode("utf-8", errors="replace").strip()
        if isinstance(error, PT21NativeRecordAdapterError):
            if diagnostic:
                raise PT21NativeRecordAdapterError(
                    f"{error}; native finalizer: {diagnostic}"
                ) from error
            raise
        raise PT21NativeRecordAdapterError(
            "record stream or native finalizer pipe failed"
            + (f": {diagnostic}" if diagnostic else "")
        ) from error
    if process.returncode != 0 or stderr:
        diagnostic = stderr.decode("utf-8", errors="replace").strip()
        raise PT21NativeRecordAdapterError(
            "native finalizer rejected the authenticated record stream"
            + (f": {diagnostic}" if diagnostic else "")
        )
    summary = _native_summary(stdout)
    expected_mode = "bounded_test" if bounded_test else "production"
    relationships = {
        "block_count": adapter_report["block_count"],
        "first_block": adapter_report["first_block"],
        "first_count": adapter_report["first_count"],
        "last_count": adapter_report["last_count"],
        "mode": expected_mode,
        "source_claim_ready": False,
        "source_height_count": adapter_report["source_height_count"],
        "total_main_slots": adapter_report["total_main_slots"],
        "total_sparse_refinements": adapter_report[
            "total_sparse_refinements"
        ],
        "total_stationary_resolutions": adapter_report[
            "total_stationary_resolutions"
        ],
        "upper_block_exclusive": adapter_report["upper_block_exclusive"],
    }
    if any(summary[key] != value for key, value in relationships.items()):
        raise PT21NativeRecordAdapterError(
            "native finalizer summary differs from the streamed adapter result"
        )
    archive_sha256, archive_size = _hash_retained_archive(output)
    if (
        summary["archive_sha256"] != archive_sha256
        or summary["archive_size_bytes"] != archive_size
    ):
        raise PT21NativeRecordAdapterError(
            "native shard archive differs from the finalizer summary"
        )
    return {
        "schema": SHARD_REPORT_SCHEMA,
        "accepted": True,
        "first_block": first_block,
        "upper_block_exclusive": first_block + block_count,
        "block_count": block_count,
        "first_count": adapter_report["first_count"],
        "last_count": adapter_report["last_count"],
        "manifest_sha256": expected_manifest,
        "manifest_sha256_authenticated": True,
        "record_stream_bytes": adapter_report["record_stream_bytes"],
        "record_stream_sha256": adapter_report["record_stream_sha256"],
        "native_archive_sha256": archive_sha256,
        "native_archive_size_bytes": archive_size,
        "native_finalizer_sha256": finalizer_identity.sha256,
        "worker_sha256": identity.sha256,
        "plan_sha256": plan,
        "prefix_evidence_sha256": prefix,
        "streamed_without_intermediate_record_file": True,
        "terminal_stream_authentication_required": True,
        "total_main_slots": adapter_report["total_main_slots"],
        "total_stationary_resolutions": adapter_report[
            "total_stationary_resolutions"
        ],
        "total_sparse_refinements": adapter_report[
            "total_sparse_refinements"
        ],
        "source_height_count": adapter_report["source_height_count"],
        "finite_record_wire_ready": True,
        "hardy_z_endpoint_realization_proved": False,
        "main_multiplicity_realization_proved": False,
        "analytic_turing_realization_proved": False,
        "lean_source_claim_ready": False,
        "source_claim_ready": False,
    }


def block_report(value: AdaptedBlock) -> dict[str, object]:
    return {
        "schema": REPORT_SCHEMA,
        "accepted": True,
        "block": value.block,
        "record_bytes": len(value.record),
        "record_sha256": value.record_sha256,
        "required_packet_sha256": value.required_packet_sha256,
        "stationary_trace_sha256": value.stationary_trace_sha256,
        "turing_inputs_sha256": value.turing_inputs_sha256,
        "source_trace_sha256": value.source_trace_sha256,
        "block_artifact_sha256": value.block_artifact_sha256,
        "lower_count": value.lower_count,
        "upper_count": value.upper_count,
        "main_slots": value.main_slots,
        "stationary_resolution_count": value.stationary_resolution_count,
        "sparse_refinement_count": value.sparse_refinement_count,
        "source_height_count": value.source_height_count,
        "worker_sha256": value.worker.sha256,
        "finite_record_wire_ready": True,
        "hardy_z_endpoint_realization_proved": False,
        "main_multiplicity_realization_proved": False,
        "analytic_turing_realization_proved": False,
        "lean_source_claim_ready": False,
        "source_claim_ready": False,
    }


__all__ = [
    "AdaptedBlock",
    "MANIFEST_SCHEMA",
    "NativeFastpathAdaptation",
    "PT21NativeRecordAdapterError",
    "REPORT_SCHEMA",
    "SHARD_REPORT_SCHEMA",
    "WorkerIdentity",
    "adapt_block",
    "adapt_block_native_scan_fastpath",
    "adapt_block_native_scan_session",
    "adapt_manifest",
    "adapt_manifest_stream",
    "adapt_manifest_to_native_shard",
    "block_report",
    "worker_identity",
    "write_exclusive",
]
