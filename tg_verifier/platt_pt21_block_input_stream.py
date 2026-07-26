# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independent decoder and adapter driver for the ``PT21WB`` block-input wire.

The fused source worker's block stage now produces all three record-adapter
inputs inside one ordered fail-closed loop:

* the ``PT21SGN1`` required-sign packet rebuilt from the replay-owned disks;
* the independently replayed stationary trace bound by ``PT21STJ1``; and
* the block-bound directed-Arb Turing inputs.

This module is the second, independent implementation of that wire.  It
re-derives every digest, re-validates each nested payload with the existing
checkers, and can drive the exact-rational record adapter and the pinned native
shard finalizer directly from the stream.  That removes the standalone assembly
channel in which a separate process retained three files per block and an
operator wrote a manifest naming them.

Nothing here is terminal.  The wire carries no ``PT21BLK1``, no count
telescoping, and no analytic realization.  Hardy-Z endpoint realization,
multiplicity realization, the analytic Turing theorem, and the PT21 source
claim all remain false.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
from typing import Any, BinaryIO, Iterator

from tg_verifier.platt_pt21_event_record import (
    PT21EventRecordError,
    parse_record as parse_event_record,
)
from tg_verifier.platt_pt21_native_finalizer import BLOCK_RECORD
from tg_verifier.platt_pt21_native_record_adapter import (
    PT21NativeRecordAdapterError,
    STREAM_AUTH_FOOTER,
    STREAM_AUTH_MAGIC,
    WorkerIdentity,
    _hash_retained_archive,
    _native_summary,
    _pinned_executable,
    _sha256_hex,
    _write_all,
    adapt_block,
    worker_identity,
)
from tg_verifier.platt_pt21_stationary_junction import (
    PT21StationaryJunctionError,
    parse_record as parse_junction_record,
)
from tg_verifier.platt_pt21_turing_inputs import (
    MAX_BYTES as TURING_MAXIMUM_BYTES,
    PT21TuringInputsError,
    validate as validate_turing_inputs,
)
from tg_verifier.platt_required_sign_packet import (
    PlattRequiredSignPacketError,
    SOURCE_LOWER_CENTER,
    SOURCE_STEP,
    load_required_sign_packet,
)
from tg_verifier.platt_stationary_trace import (
    MAXIMUM_BYTES as STATIONARY_MAXIMUM_BYTES,
)


VERSION = 1
FINITE_QUALIFICATION_ONLY_FLAG = 1
SOURCE_BLOCK_COUNT = 2_966_443_783
REQUIRED_SIGN_PACKET_BYTES = 621_202
EVENT_RECORD_BYTES = 192
JUNCTION_RECORD_BYTES = 400
HEADER_BYTES = 256
HEADER_DIGEST_OFFSET = 224
FRAME_PREFIX_BYTES = 208
FRAME_DIGEST_BYTES = 32
FOOTER_BYTES = 192
FOOTER_DIGEST_OFFSET = 160
MAXIMUM_TRACE_BYTES = STATIONARY_MAXIMUM_BYTES
# The wire cap is deliberately tighter than the Turing decoder's 64 KiB cap so
# a malformed producer cannot inflate one frame.
MAXIMUM_TURING_BYTES = 16 * 1024
MAXIMUM_FRAME_BYTES = (
    FRAME_PREFIX_BYTES
    + REQUIRED_SIGN_PACKET_BYTES
    + EVENT_RECORD_BYTES
    + JUNCTION_RECORD_BYTES
    + MAXIMUM_TRACE_BYTES
    + MAXIMUM_TURING_BYTES
    + FRAME_DIGEST_BYTES
)
MAXIMUM_FINALIZER_STDOUT = 64 * 1024

HEADER_MAGIC = b"PT21WBH1"
FRAME_MAGIC = b"PT21WBF1"
FOOTER_MAGIC = b"PT21WBT1"
ALGORITHM_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-worker-block-input-stream/v1\0"
)
HEADER_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-worker-block-input-header/v1\0"
)
FRAME_DOMAIN = b"sparkinterval/tg/platt-pt21-worker-block-input-frame/v1\0"
FOOTER_DOMAIN = b"sparkinterval/tg/platt-pt21-worker-block-input-footer/v1\0"

SCHEMA = "sparkinterval.tg.platt-pt21-block-input-stream.v1"
SHARD_REPORT_SCHEMA = (
    "sparkinterval.tg.platt-pt21-block-input-streamed-shard.v1"
)
NATIVE_SHARD_SUMMARY_SCHEMA = (
    "sparkinterval.tg.platt-pt21-native-shard-summary.v1"
)

ALGORITHM_SHA256 = hashlib.sha256(ALGORITHM_DOMAIN).hexdigest()


class PT21BlockInputStreamError(RuntimeError):
    """A block-input frame, digest, identity, or nested payload differs."""


@dataclass(frozen=True)
class StreamHeader:
    first_block: int
    block_count: int
    gamma_stream_sha256: str
    producer_sha256: str
    resolver_sha256: str
    flint_sha256: str
    header_sha256: str


@dataclass(frozen=True)
class BlockInputFrame:
    block: int
    required_sign_packet: bytes
    event_record: bytes
    junction_record: bytes
    stationary_trace: bytes
    turing_inputs: bytes
    frame_sha256: str


@dataclass(frozen=True)
class StreamFooter:
    first_block: int
    block_count: int
    total_frames: int
    total_packet_bytes: int
    total_trace_bytes: int
    total_turing_bytes: int
    frame_stream_sha256: str
    header_sha256: str
    gamma_stream_sha256: str
    footer_sha256: str


def _u32(raw: bytes, offset: int) -> int:
    return int.from_bytes(raw[offset : offset + 4], "little")


def _u64(raw: bytes, offset: int) -> int:
    return int.from_bytes(raw[offset : offset + 8], "little")


def _digest(raw: bytes, offset: int) -> bytes:
    return raw[offset : offset + 32]


def _nonzero(raw: bytes, label: str) -> None:
    if raw == bytes(32):
        raise PT21BlockInputStreamError(f"{label} identity is zero")


def _geometry(first_block: int, block_count: int) -> None:
    if (
        block_count < 1
        or first_block < 0
        or first_block >= SOURCE_BLOCK_COUNT
        or block_count > SOURCE_BLOCK_COUNT - first_block
    ):
        raise PT21BlockInputStreamError(
            "block-input stream geometry is outside PT21"
        )


def _read_exact(stream: BinaryIO, size: int, label: str) -> bytes:
    result = bytearray()
    while len(result) < size:
        chunk = stream.read(size - len(result))
        if not chunk:
            raise PT21BlockInputStreamError(f"{label} is truncated")
        result.extend(chunk)
    return bytes(result)


def _open_regular(path: Path) -> tuple[BinaryIO, int]:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as error:
        raise PT21BlockInputStreamError(
            f"cannot open block-input stream without following links: {error}"
        ) from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size < 1:
            raise PT21BlockInputStreamError(
                "block-input stream is not a nonempty regular file"
            )
        return os.fdopen(descriptor, "rb", closefd=True), metadata.st_size
    except Exception:
        os.close(descriptor)
        raise


def decode_header(
    raw: bytes,
    *,
    expected_first_block: int | None = None,
    expected_block_count: int | None = None,
    expected_gamma_stream_sha256: str | None = None,
    expected_producer_sha256: str | None = None,
    expected_resolver_sha256: str | None = None,
    expected_flint_sha256: str | None = None,
) -> StreamHeader:
    if (
        len(raw) != HEADER_BYTES
        or raw[:8] != HEADER_MAGIC
        or _u32(raw, 8) != VERSION
        or _u32(raw, 12) != HEADER_BYTES
        or _u32(raw, 16) != FRAME_PREFIX_BYTES
        or _u32(raw, 20) != FOOTER_BYTES
        or _u32(raw, 200) != FINITE_QUALIFICATION_ONLY_FLAG
        or _u32(raw, 204) != REQUIRED_SIGN_PACKET_BYTES
    ):
        raise PT21BlockInputStreamError(
            "block-input stream fixed header differs"
        )
    if raw[208:HEADER_DIGEST_OFFSET] != bytes(
        HEADER_DIGEST_OFFSET - 208
    ):
        raise PT21BlockInputStreamError(
            "block-input stream header reserved bytes differ"
        )
    digest = hashlib.sha256(
        HEADER_DOMAIN + raw[:HEADER_DIGEST_OFFSET]
    ).digest()
    if _digest(raw, HEADER_DIGEST_OFFSET) != digest:
        raise PT21BlockInputStreamError(
            "block-input stream header digest differs"
        )
    if _digest(raw, 168).hex() != ALGORITHM_SHA256:
        raise PT21BlockInputStreamError(
            "block-input stream algorithm domain differs"
        )
    first_block = _u64(raw, 24)
    block_count = _u64(raw, 32)
    _geometry(first_block, block_count)
    gamma = _digest(raw, 40)
    producer = _digest(raw, 72)
    resolver = _digest(raw, 104)
    flint = _digest(raw, 136)
    _nonzero(gamma, "Gamma stream")
    _nonzero(producer, "producer")
    _nonzero(resolver, "resolver")
    _nonzero(flint, "FLINT")
    header = StreamHeader(
        first_block=first_block,
        block_count=block_count,
        gamma_stream_sha256=gamma.hex(),
        producer_sha256=producer.hex(),
        resolver_sha256=resolver.hex(),
        flint_sha256=flint.hex(),
        header_sha256=digest.hex(),
    )
    pins = (
        (expected_first_block, header.first_block, "first block"),
        (expected_block_count, header.block_count, "block count"),
        (
            expected_gamma_stream_sha256,
            header.gamma_stream_sha256,
            "Gamma stream SHA-256",
        ),
        (
            expected_producer_sha256,
            header.producer_sha256,
            "producer SHA-256",
        ),
        (
            expected_resolver_sha256,
            header.resolver_sha256,
            "resolver SHA-256",
        ),
        (expected_flint_sha256, header.flint_sha256, "FLINT SHA-256"),
    )
    for expected, actual, label in pins:
        if expected is not None and expected != actual:
            raise PT21BlockInputStreamError(
                f"block-input stream {label} differs from its pin"
            )
    return header


def decode_frame(raw: bytes, expected_block: int) -> BlockInputFrame:
    """Decode and fully validate one frame, including every nested payload."""

    if (
        len(raw) < FRAME_PREFIX_BYTES
        + REQUIRED_SIGN_PACKET_BYTES
        + EVENT_RECORD_BYTES
        + JUNCTION_RECORD_BYTES
        + 2
        + FRAME_DIGEST_BYTES
        or raw[:8] != FRAME_MAGIC
        or _u32(raw, 8) != VERSION
        or _u32(raw, 12) != len(raw)
        or _u64(raw, 16) != expected_block
        or _u32(raw, 24) != REQUIRED_SIGN_PACKET_BYTES
        or _u32(raw, 28) != EVENT_RECORD_BYTES
        or _u32(raw, 32) != JUNCTION_RECORD_BYTES
        or _u32(raw, 44) != 0
    ):
        raise PT21BlockInputStreamError("block-input frame fixed fields differ")
    trace_bytes = _u32(raw, 36)
    turing_bytes = _u32(raw, 40)
    if (
        trace_bytes < 1
        or trace_bytes > MAXIMUM_TRACE_BYTES
        or turing_bytes < 1
        or turing_bytes > MAXIMUM_TURING_BYTES
        or len(raw)
        != FRAME_PREFIX_BYTES
        + REQUIRED_SIGN_PACKET_BYTES
        + EVENT_RECORD_BYTES
        + JUNCTION_RECORD_BYTES
        + trace_bytes
        + turing_bytes
        + FRAME_DIGEST_BYTES
    ):
        raise PT21BlockInputStreamError("block-input frame lengths differ")
    frame_digest = hashlib.sha256(
        FRAME_DOMAIN + raw[: len(raw) - FRAME_DIGEST_BYTES]
    ).digest()
    if raw[len(raw) - FRAME_DIGEST_BYTES :] != frame_digest:
        raise PT21BlockInputStreamError("block-input frame digest differs")

    offset = FRAME_PREFIX_BYTES
    packet = raw[offset : offset + REQUIRED_SIGN_PACKET_BYTES]
    offset += REQUIRED_SIGN_PACKET_BYTES
    event_record = raw[offset : offset + EVENT_RECORD_BYTES]
    offset += EVENT_RECORD_BYTES
    junction_record = raw[offset : offset + JUNCTION_RECORD_BYTES]
    offset += JUNCTION_RECORD_BYTES
    stationary_trace = raw[offset : offset + trace_bytes]
    offset += trace_bytes
    turing_inputs = raw[offset : offset + turing_bytes]

    payload_digests = (
        (48, packet, "required-sign packet"),
        (80, event_record, "event record"),
        (112, junction_record, "stationary junction record"),
        (144, stationary_trace, "stationary trace"),
        (176, turing_inputs, "Turing input artifact"),
    )
    for position, payload, label in payload_digests:
        if _digest(raw, position) != hashlib.sha256(payload).digest():
            raise PT21BlockInputStreamError(
                f"block-input frame {label} digest differs"
            )

    try:
        event = parse_event_record(event_record, expected_block=expected_block)
    except PT21EventRecordError as error:
        raise PT21BlockInputStreamError(
            f"block-input frame PT21EVT1 failed: {error}"
        ) from error
    try:
        junction = parse_junction_record(junction_record)
    except PT21StationaryJunctionError as error:
        raise PT21BlockInputStreamError(
            f"block-input frame PT21STJ1 failed: {error}"
        ) from error
    if (
        int(junction["block"]) != expected_block
        or junction["event_record_sha256"] != event["record_sha256"]
        or junction["event_artifact_sha256"] != event["event_artifact_sha256"]
        or bytes.fromhex(str(junction["stationary_trace_sha256"]))
        != hashlib.sha256(stationary_trace).digest()
    ):
        raise PT21BlockInputStreamError(
            "block-input frame event/junction/trace linkage differs"
        )
    if (
        packet[:8] != b"PT21SGN1"
        or _u64(packet, 48)
        != SOURCE_LOWER_CENTER + expected_block * SOURCE_STEP
    ):
        raise PT21BlockInputStreamError(
            "block-input frame packet centre is off the block's source grid"
        )
    return BlockInputFrame(
        block=expected_block,
        required_sign_packet=packet,
        event_record=event_record,
        junction_record=junction_record,
        stationary_trace=stationary_trace,
        turing_inputs=turing_inputs,
        frame_sha256=frame_digest.hex(),
    )


def decode_footer(raw: bytes) -> StreamFooter:
    if (
        len(raw) != FOOTER_BYTES
        or raw[:8] != FOOTER_MAGIC
        or _u32(raw, 8) != VERSION
        or _u32(raw, 12) != FOOTER_BYTES
    ):
        raise PT21BlockInputStreamError("block-input footer fixed fields differ")
    digest = hashlib.sha256(
        FOOTER_DOMAIN + raw[:FOOTER_DIGEST_OFFSET]
    ).digest()
    if _digest(raw, FOOTER_DIGEST_OFFSET) != digest:
        raise PT21BlockInputStreamError("block-input footer digest differs")
    first_block = _u64(raw, 16)
    block_count = _u64(raw, 24)
    _geometry(first_block, block_count)
    total_frames = _u64(raw, 32)
    total_packet_bytes = _u64(raw, 40)
    if (
        total_frames != block_count
        or total_packet_bytes != block_count * REQUIRED_SIGN_PACKET_BYTES
    ):
        raise PT21BlockInputStreamError("block-input footer totals differ")
    frame_stream = _digest(raw, 64)
    header = _digest(raw, 96)
    gamma = _digest(raw, 128)
    _nonzero(frame_stream, "frame stream")
    _nonzero(header, "header")
    _nonzero(gamma, "Gamma stream")
    return StreamFooter(
        first_block=first_block,
        block_count=block_count,
        total_frames=total_frames,
        total_packet_bytes=total_packet_bytes,
        total_trace_bytes=_u64(raw, 48),
        total_turing_bytes=_u64(raw, 56),
        frame_stream_sha256=frame_stream.hex(),
        header_sha256=header.hex(),
        gamma_stream_sha256=gamma.hex(),
        footer_sha256=digest.hex(),
    )


class BlockInputStreamReader:
    """Bounded-memory ordered reader; nothing is accepted before the footer."""

    def __init__(
        self,
        stream: BinaryIO,
        size: int,
        *,
        expected_first_block: int | None = None,
        expected_block_count: int | None = None,
        expected_gamma_stream_sha256: str | None = None,
        expected_producer_sha256: str | None = None,
        expected_resolver_sha256: str | None = None,
        expected_flint_sha256: str | None = None,
    ) -> None:
        self._stream = stream
        self._size = size
        raw_header = _read_exact(stream, HEADER_BYTES, "block-input header")
        self.header = decode_header(
            raw_header,
            expected_first_block=expected_first_block,
            expected_block_count=expected_block_count,
            expected_gamma_stream_sha256=expected_gamma_stream_sha256,
            expected_producer_sha256=expected_producer_sha256,
            expected_resolver_sha256=expected_resolver_sha256,
            expected_flint_sha256=expected_flint_sha256,
        )
        self._whole = hashlib.sha256()
        self._frames = hashlib.sha256()
        self._whole.update(raw_header)
        self._consumed = HEADER_BYTES
        self._produced = 0
        self.total_trace_bytes = 0
        self.total_turing_bytes = 0
        self.footer: StreamFooter | None = None
        self.stream_sha256: str | None = None

    def __iter__(self) -> Iterator[BlockInputFrame]:
        while self._produced < self.header.block_count:
            prefix = _read_exact(
                self._stream, FRAME_PREFIX_BYTES, "block-input frame prefix"
            )
            frame_bytes = _u32(prefix, 12)
            if (
                frame_bytes <= FRAME_PREFIX_BYTES
                or frame_bytes > MAXIMUM_FRAME_BYTES
            ):
                raise PT21BlockInputStreamError(
                    "block-input frame length is outside its bound"
                )
            remainder = _read_exact(
                self._stream,
                frame_bytes - FRAME_PREFIX_BYTES,
                "block-input frame payload",
            )
            raw = prefix + remainder
            block = self.header.first_block + self._produced
            frame = decode_frame(raw, block)
            self._whole.update(raw)
            self._frames.update(raw)
            self._consumed += len(raw)
            self._produced += 1
            self.total_trace_bytes += len(frame.stationary_trace)
            self.total_turing_bytes += len(frame.turing_inputs)
            yield frame
        raw_footer = _read_exact(self._stream, FOOTER_BYTES, "block-input footer")
        footer = decode_footer(raw_footer)
        self._whole.update(raw_footer)
        self._consumed += FOOTER_BYTES
        if self._stream.read(1):
            raise PT21BlockInputStreamError(
                "block-input stream has trailing bytes"
            )
        if self._consumed != self._size:
            raise PT21BlockInputStreamError(
                "block-input stream length is not exact"
            )
        if (
            footer.first_block != self.header.first_block
            or footer.block_count != self.header.block_count
            or footer.total_frames != self._produced
            or footer.total_trace_bytes != self.total_trace_bytes
            or footer.total_turing_bytes != self.total_turing_bytes
            or footer.frame_stream_sha256 != self._frames.hexdigest()
            or footer.header_sha256 != self.header.header_sha256
            or footer.gamma_stream_sha256 != self.header.gamma_stream_sha256
        ):
            raise PT21BlockInputStreamError(
                "block-input footer differs from the streamed frames"
            )
        self.footer = footer
        self.stream_sha256 = self._whole.hexdigest()


def validate(
    path: Path,
    *,
    expected_stream_sha256: str | None = None,
    expected_first_block: int | None = None,
    expected_block_count: int | None = None,
    expected_gamma_stream_sha256: str | None = None,
    expected_producer_sha256: str | None = None,
    expected_resolver_sha256: str | None = None,
    expected_flint_sha256: str | None = None,
) -> dict[str, object]:
    """Independently replay every frame, digest, and nested finite payload."""

    stream, size = _open_regular(path)
    with stream:
        reader = BlockInputStreamReader(
            stream,
            size,
            expected_first_block=expected_first_block,
            expected_block_count=expected_block_count,
            expected_gamma_stream_sha256=expected_gamma_stream_sha256,
            expected_producer_sha256=expected_producer_sha256,
            expected_resolver_sha256=expected_resolver_sha256,
            expected_flint_sha256=expected_flint_sha256,
        )
        packets = 0
        for frame in reader:
            _validate_frame_payloads(frame)
            packets += 1
    assert reader.footer is not None
    assert reader.stream_sha256 is not None
    if (
        expected_stream_sha256 is not None
        and reader.stream_sha256
        != _sha256_hex(expected_stream_sha256, "expected stream SHA-256")
    ):
        raise PT21BlockInputStreamError(
            "block-input stream SHA-256 differs from its pin"
        )
    return {
        "schema": SCHEMA,
        "accepted": True,
        "first_block": reader.header.first_block,
        "block_count": reader.header.block_count,
        "frames_validated": packets,
        "stream_bytes": size,
        "stream_sha256": reader.stream_sha256,
        "header_sha256": reader.header.header_sha256,
        "footer_sha256": reader.footer.footer_sha256,
        "frame_stream_sha256": reader.footer.frame_stream_sha256,
        "gamma_stream_sha256": reader.header.gamma_stream_sha256,
        "producer_sha256": reader.header.producer_sha256,
        "resolver_sha256": reader.header.resolver_sha256,
        "flint_sha256": reader.header.flint_sha256,
        "total_required_sign_packet_bytes": reader.footer.total_packet_bytes,
        "total_stationary_trace_bytes": reader.footer.total_trace_bytes,
        "total_turing_artifact_bytes": reader.footer.total_turing_bytes,
        "three_adapter_inputs_present": True,
        "producer_identity_self_verified": False,
        "pt21blk1_present": False,
        "count_telescoping_checked": False,
        "hardy_z_endpoint_realization_proved": False,
        "main_multiplicity_realization_proved": False,
        "analytic_turing_realization_proved": False,
        "source_claim_ready": False,
    }


def _validate_frame_payloads(frame: BlockInputFrame) -> None:
    """Re-run the existing independent checkers on the three adapter inputs."""

    with tempfile.TemporaryDirectory(prefix="pt21-block-input-") as temporary:
        packet_path = Path(temporary) / "required-sign-packet.bin"
        packet_path.write_bytes(frame.required_sign_packet)
        try:
            packet = load_required_sign_packet(packet_path)
        except (OSError, PlattRequiredSignPacketError) as error:
            raise PT21BlockInputStreamError(
                f"block {frame.block} required-sign packet failed: {error}"
            ) from error
    try:
        turing_value = json.loads(frame.turing_inputs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PT21BlockInputStreamError(
            f"block {frame.block} Turing artifact is not strict JSON: {error}"
        ) from error
    canonical = (
        json.dumps(
            turing_value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    if canonical != frame.turing_inputs:
        raise PT21BlockInputStreamError(
            f"block {frame.block} Turing artifact is not canonical"
        )
    try:
        validate_turing_inputs(
            turing_value,
            expected_block=frame.block,
            expected_packet_sha256=packet.sha256,
        )
    except PT21TuringInputsError as error:
        raise PT21BlockInputStreamError(
            f"block {frame.block} Turing artifact failed: {error}"
        ) from error


@dataclass(frozen=True)
class MaterializedBlock:
    required_sign_packet: Path
    stationary_trace: Path
    turing_inputs: Path


def _materialize(frame: BlockInputFrame, root: Path) -> MaterializedBlock:
    """Write the frame's three inputs into one ephemeral private directory."""

    packet = root / "required-sign-packet.bin"
    trace = root / "stationary-trace.json"
    turing = root / "turing-inputs.json"
    packet.write_bytes(frame.required_sign_packet)
    trace.write_bytes(frame.stationary_trace)
    turing.write_bytes(frame.turing_inputs)
    return MaterializedBlock(
        required_sign_packet=packet,
        stationary_trace=trace,
        turing_inputs=turing,
    )


def stream_shard_archive(
    path: Path,
    *,
    expected_stream_sha256: str,
    worker: Path | WorkerIdentity,
    finalizer: Path,
    expected_finalizer_sha256: str,
    output: Path,
    first_block: int,
    block_count: int,
    plan_sha256: str,
    prefix_evidence_sha256: str,
    bounded_test: bool,
    finalizer_exit_timeout_seconds: int = 300,
) -> dict[str, object]:
    """Drive the exact record adapter and native finalizer from one stream.

    No per-block artifact is retained and no manifest is written: every frame is
    decoded, independently validated, adapted into one canonical ``PT21BLK1``,
    and written straight into the pinned native finalizer's pipe.  The terminal
    ``PT21END1`` commitment is released only after the complete stream digest
    matches its external pin, so a late mismatch cannot publish an already
    written prefix.
    """

    if (
        isinstance(finalizer_exit_timeout_seconds, bool)
        or not 1 <= finalizer_exit_timeout_seconds <= 3600
    ):
        raise PT21BlockInputStreamError(
            "native finalizer exit timeout is outside 1..3600 seconds"
        )
    if not isinstance(bounded_test, bool):
        raise PT21BlockInputStreamError("bounded_test must be Boolean")
    if output.exists() or output.is_symlink():
        raise PT21BlockInputStreamError("native shard output already exists")
    expected_stream = _sha256_hex(
        expected_stream_sha256, "expected block-input stream SHA-256"
    )
    plan = _sha256_hex(plan_sha256, "plan SHA-256")
    prefix = _sha256_hex(prefix_evidence_sha256, "prefix-evidence SHA-256")
    identity = (
        worker
        if isinstance(worker, WorkerIdentity)
        else worker_identity(worker)
    )

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
            expected_stream,
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
    except (OSError, ValueError, PT21NativeRecordAdapterError) as error:
        raise PT21BlockInputStreamError(
            f"cannot start pinned native finalizer: {error}"
        ) from error
    finally:
        if executable_descriptor >= 0:
            os.close(executable_descriptor)
    assert process is not None
    assert process.stdin is not None

    try:
        adapter_report = _adapt_stream_to_pipe(
            path,
            destination=process.stdin,
            worker=identity,
            first_block=first_block,
            block_count=block_count,
            expected_stream_sha256=expected_stream,
        )
        _write_all(
            process.stdin,
            STREAM_AUTH_FOOTER.pack(
                STREAM_AUTH_MAGIC,
                1,
                STREAM_AUTH_FOOTER.size,
                bytes.fromhex(expected_stream),
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
            raise PT21BlockInputStreamError(
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
        if isinstance(error, PT21BlockInputStreamError):
            if diagnostic:
                raise PT21BlockInputStreamError(
                    f"{error}; native finalizer: {diagnostic}"
                ) from error
            raise
        raise PT21BlockInputStreamError(
            "block-input stream or native finalizer pipe failed"
            + (f": {diagnostic}" if diagnostic else "")
        ) from error

    if process.returncode != 0 or stderr:
        diagnostic = stderr.decode("utf-8", errors="replace").strip()
        raise PT21BlockInputStreamError(
            "native finalizer rejected the streamed record chain"
            + (f": {diagnostic}" if diagnostic else "")
        )
    if len(stdout) > MAXIMUM_FINALIZER_STDOUT:
        raise PT21BlockInputStreamError("native finalizer summary is too large")
    try:
        summary = _native_summary(stdout)
    except PT21NativeRecordAdapterError as error:
        raise PT21BlockInputStreamError(str(error)) from error
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
        "total_sparse_refinements": adapter_report["total_sparse_refinements"],
        "total_stationary_resolutions": adapter_report[
            "total_stationary_resolutions"
        ],
        "upper_block_exclusive": adapter_report["upper_block_exclusive"],
    }
    if any(summary[key] != value for key, value in relationships.items()):
        raise PT21BlockInputStreamError(
            "native finalizer summary differs from the streamed adapter result"
        )
    try:
        archive_sha256, archive_size = _hash_retained_archive(output)
    except PT21NativeRecordAdapterError as error:
        raise PT21BlockInputStreamError(str(error)) from error
    if (
        summary["archive_sha256"] != archive_sha256
        or summary["archive_size_bytes"] != archive_size
    ):
        raise PT21BlockInputStreamError(
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
        "block_input_stream_sha256": expected_stream,
        "block_input_stream_sha256_authenticated": True,
        "block_input_frames_consumed": adapter_report["block_count"],
        "record_stream_bytes": adapter_report["record_stream_bytes"],
        "record_stream_sha256": adapter_report["record_stream_sha256"],
        "native_archive_sha256": archive_sha256,
        "native_archive_size_bytes": archive_size,
        "native_finalizer_sha256": finalizer_identity.sha256,
        "worker_sha256": identity.sha256,
        "plan_sha256": plan,
        "prefix_evidence_sha256": prefix,
        "manifest_channel_used": False,
        "per_block_artifacts_retained": False,
        "streamed_without_intermediate_record_file": True,
        "terminal_stream_authentication_required": True,
        "total_main_slots": adapter_report["total_main_slots"],
        "total_stationary_resolutions": adapter_report[
            "total_stationary_resolutions"
        ],
        "total_sparse_refinements": adapter_report["total_sparse_refinements"],
        "source_height_count": adapter_report["source_height_count"],
        "finite_record_wire_ready": True,
        "hardy_z_endpoint_realization_proved": False,
        "main_multiplicity_realization_proved": False,
        "analytic_turing_realization_proved": False,
        "lean_source_claim_ready": False,
        "source_claim_ready": False,
    }


def adapt_stream(
    path: Path,
    *,
    destination: BinaryIO,
    worker: Path | WorkerIdentity,
    first_block: int,
    block_count: int,
    expected_stream_sha256: str,
) -> dict[str, object]:
    """Write ``PT21BLK1`` records for one authenticated block-input stream."""

    identity = (
        worker
        if isinstance(worker, WorkerIdentity)
        else worker_identity(worker)
    )
    return _adapt_stream_to_pipe(
        path,
        destination=destination,
        worker=identity,
        first_block=first_block,
        block_count=block_count,
        expected_stream_sha256=_sha256_hex(
            expected_stream_sha256, "expected block-input stream SHA-256"
        ),
    )


def _adapt_stream_to_pipe(
    path: Path,
    *,
    destination: BinaryIO,
    worker: WorkerIdentity,
    first_block: int,
    block_count: int,
    expected_stream_sha256: str,
) -> dict[str, object]:
    if first_block < 0 or block_count < 1:
        raise PT21BlockInputStreamError(
            "streamed shard geometry must be nonempty"
        )
    records_sha256 = hashlib.sha256()
    produced = 0
    total_slots = 0
    total_stationary = 0
    total_sparse = 0
    source_height_count: int | None = None
    first_count: int | None = None
    previous_upper_count: int | None = None

    stream, size = _open_regular(path)
    with stream:
        reader = BlockInputStreamReader(
            stream,
            size,
            expected_first_block=first_block,
            expected_block_count=block_count,
        )
        for frame in reader:
            _validate_frame_payloads(frame)
            with tempfile.TemporaryDirectory(
                prefix="pt21-block-input-adapt-"
            ) as temporary:
                inputs = _materialize(frame, Path(temporary))
                try:
                    adapted = adapt_block(
                        required_sign_packet=inputs.required_sign_packet,
                        stationary_trace=inputs.stationary_trace,
                        turing_inputs=inputs.turing_inputs,
                        worker=worker,
                    )
                except PT21NativeRecordAdapterError as error:
                    raise PT21BlockInputStreamError(
                        f"block {frame.block} record adaptation failed: {error}"
                    ) from error
            if adapted.block != first_block + produced:
                raise PT21BlockInputStreamError(
                    "streamed block records are not gap-free and ordered"
                )
            if (
                previous_upper_count is not None
                and adapted.lower_count != previous_upper_count
            ):
                raise PT21BlockInputStreamError(
                    "streamed block counts do not telescope"
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
                    raise PT21BlockInputStreamError(
                        "stream repeats the unique source-height count"
                    )
                source_height_count = adapted.source_height_count
            previous_upper_count = adapted.upper_count
            if produced > block_count:
                raise PT21BlockInputStreamError(
                    "stream contains more frames than its declared shard"
                )
    if produced != block_count:
        raise PT21BlockInputStreamError(
            "block-input stream is a strict prefix of its declared shard"
        )
    assert reader.stream_sha256 is not None
    if reader.stream_sha256 != expected_stream_sha256:
        raise PT21BlockInputStreamError(
            "block-input stream SHA-256 differs from the pinned stream"
        )
    assert first_count is not None
    assert previous_upper_count is not None
    return {
        "schema": SCHEMA,
        "accepted": True,
        "block_input_stream_sha256": reader.stream_sha256,
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
        "manifest_channel_used": False,
        "per_block_artifacts_retained": False,
        "finite_record_wire_ready": True,
        "hardy_z_endpoint_realization_proved": False,
        "main_multiplicity_realization_proved": False,
        "analytic_turing_realization_proved": False,
        "lean_source_claim_ready": False,
        "source_claim_ready": False,
    }


def encode_header(
    *,
    first_block: int,
    block_count: int,
    gamma_stream_sha256: str,
    producer_sha256: str,
    resolver_sha256: str,
    flint_sha256: str,
) -> bytes:
    """Second implementation of the producer header, used by known answers."""

    _geometry(first_block, block_count)
    raw = bytearray(HEADER_BYTES)
    raw[0:8] = HEADER_MAGIC
    struct.pack_into(
        "<3I", raw, 8, VERSION, HEADER_BYTES, FRAME_PREFIX_BYTES
    )
    struct.pack_into("<I", raw, 20, FOOTER_BYTES)
    struct.pack_into("<2Q", raw, 24, first_block, block_count)
    for offset, value, label in (
        (40, gamma_stream_sha256, "Gamma stream"),
        (72, producer_sha256, "producer"),
        (104, resolver_sha256, "resolver"),
        (136, flint_sha256, "FLINT"),
    ):
        digest = bytes.fromhex(_sha256_hex(value, label))
        _nonzero(digest, label)
        raw[offset : offset + 32] = digest
    raw[168:200] = bytes.fromhex(ALGORITHM_SHA256)
    struct.pack_into(
        "<2I",
        raw,
        200,
        FINITE_QUALIFICATION_ONLY_FLAG,
        REQUIRED_SIGN_PACKET_BYTES,
    )
    raw[HEADER_DIGEST_OFFSET:HEADER_BYTES] = hashlib.sha256(
        HEADER_DOMAIN + bytes(raw[:HEADER_DIGEST_OFFSET])
    ).digest()
    return bytes(raw)


def encode_frame(
    *,
    block: int,
    required_sign_packet: bytes,
    event_record: bytes,
    junction_record: bytes,
    stationary_trace: bytes,
    turing_inputs: bytes,
) -> bytes:
    """Second implementation of the producer frame, used by known answers."""

    if (
        len(required_sign_packet) != REQUIRED_SIGN_PACKET_BYTES
        or len(event_record) != EVENT_RECORD_BYTES
        or len(junction_record) != JUNCTION_RECORD_BYTES
        or not 1 <= len(stationary_trace) <= MAXIMUM_TRACE_BYTES
        or not 1 <= len(turing_inputs) <= MAXIMUM_TURING_BYTES
    ):
        raise PT21BlockInputStreamError("block-input frame payloads differ")
    total = (
        FRAME_PREFIX_BYTES
        + len(required_sign_packet)
        + len(event_record)
        + len(junction_record)
        + len(stationary_trace)
        + len(turing_inputs)
        + FRAME_DIGEST_BYTES
    )
    raw = bytearray(total)
    raw[0:8] = FRAME_MAGIC
    struct.pack_into("<2I", raw, 8, VERSION, total)
    struct.pack_into("<Q", raw, 16, block)
    struct.pack_into(
        "<6I",
        raw,
        24,
        len(required_sign_packet),
        len(event_record),
        len(junction_record),
        len(stationary_trace),
        len(turing_inputs),
        0,
    )
    payloads = (
        required_sign_packet,
        event_record,
        junction_record,
        stationary_trace,
        turing_inputs,
    )
    for index, payload in enumerate(payloads):
        position = 48 + 32 * index
        raw[position : position + 32] = hashlib.sha256(payload).digest()
    offset = FRAME_PREFIX_BYTES
    for payload in payloads:
        raw[offset : offset + len(payload)] = payload
        offset += len(payload)
    raw[total - FRAME_DIGEST_BYTES :] = hashlib.sha256(
        FRAME_DOMAIN + bytes(raw[: total - FRAME_DIGEST_BYTES])
    ).digest()
    return bytes(raw)


def encode_footer(
    *,
    first_block: int,
    block_count: int,
    total_frames: int,
    total_packet_bytes: int,
    total_trace_bytes: int,
    total_turing_bytes: int,
    frame_stream_sha256: bytes,
    header_sha256: bytes,
    gamma_stream_sha256: bytes,
) -> bytes:
    """Second implementation of the producer footer, used by known answers."""

    _geometry(first_block, block_count)
    if (
        total_frames != block_count
        or total_packet_bytes != block_count * REQUIRED_SIGN_PACKET_BYTES
    ):
        raise PT21BlockInputStreamError("block-input footer totals differ")
    raw = bytearray(FOOTER_BYTES)
    raw[0:8] = FOOTER_MAGIC
    struct.pack_into("<2I", raw, 8, VERSION, FOOTER_BYTES)
    struct.pack_into(
        "<6Q",
        raw,
        16,
        first_block,
        block_count,
        total_frames,
        total_packet_bytes,
        total_trace_bytes,
        total_turing_bytes,
    )
    for offset, digest, label in (
        (64, frame_stream_sha256, "frame stream"),
        (96, header_sha256, "header"),
        (128, gamma_stream_sha256, "Gamma stream"),
    ):
        _nonzero(digest, label)
        raw[offset : offset + 32] = digest
    raw[FOOTER_DIGEST_OFFSET:FOOTER_BYTES] = hashlib.sha256(
        FOOTER_DOMAIN + bytes(raw[:FOOTER_DIGEST_OFFSET])
    ).digest()
    return bytes(raw)


def report(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


__all__ = [
    "ALGORITHM_SHA256",
    "BlockInputFrame",
    "BlockInputStreamReader",
    "FOOTER_BYTES",
    "FRAME_PREFIX_BYTES",
    "HEADER_BYTES",
    "PT21BlockInputStreamError",
    "REQUIRED_SIGN_PACKET_BYTES",
    "SCHEMA",
    "SHARD_REPORT_SCHEMA",
    "StreamFooter",
    "StreamHeader",
    "adapt_stream",
    "decode_footer",
    "decode_frame",
    "decode_header",
    "encode_footer",
    "encode_frame",
    "encode_header",
    "report",
    "stream_shard_archive",
    "validate",
]
