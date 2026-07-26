# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed decoder for the PT21 all-window Gamma/Taylor stream.

The stream carries one fixed 264-byte outward binary64 projection for every
logical height window.  It is intentionally chunked: a production GPU worker
can authenticate each bounded payload before use without retaining the full
roughly 783 GB campaign stream.  This module checks the finite framing and
arithmetic projection invariants.  It does not identify FLINT ``acb_lgamma``
with Mathlib's complex Gamma function.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import stat
import struct


MAGIC = b"PT21GTS1"
CHUNK_MAGIC = b"PT21GTC1"
FOOTER_MAGIC = b"PT21GTF1"
VERSION = 1
ENDIAN_TAG = 0x01020304
RECORD_ENCODING = 1
DEGREE = 6
PRECISION_BITS = 256
SOURCE_LOWER = 10_000_000_000
SOURCE_STEP = 1_008
FULL_BLOCK_COUNT = 2_966_443_783
FULL_COVERAGE_UPPER = 3_000_175_333_264
UPSTREAM_COMMIT = b"42b21426718e542daa2b006dc05ea2d7f26426e6"
FLINT_COMMIT = b"8d5454b96761fafe4d5a9da76a369a602f500f49"
REVIEWED_SOURCE_SHA256 = bytes.fromhex(
    "9a748490b327b102d53506e390a42afac796a5b42b42060fe82aa8f5744bb152"
)
CONTRACT_ID = b"sparkinterval/pt21-gamma-taylor-stream/v1"
STREAM_HASH_DOMAIN = b"sparkinterval/pt21-gamma-taylor-stream/v1"

HEADER = struct.Struct("<8s8I5QqQqQQ40s40s32s48s40s")
CHUNK_HEADER = struct.Struct("<8sIIQIIQ32s")
RECORD = struct.Struct("<24d6Q3d")
FOOTER = struct.Struct("<8sII5Q32s32s8s")


class PlattGammaTaylorStreamError(RuntimeError):
    """The Gamma/Taylor stream failed a framing, hash, or interval check."""


@dataclass(frozen=True)
class GammaTaylorStreamInspection:
    path: Path
    artifact_sha256: str
    header_sha256: str
    stream_sha256: str
    first_block: int
    block_count: int
    chunk_count: int
    record_payload_bytes: int
    artifact_bytes: int
    first_window_center: int
    last_window_center: int


@dataclass(frozen=True)
class GammaTaylorChunk:
    """One locally authenticated, structurally checked bounded payload."""

    first_block: int
    record_count: int
    payload_sha256: str
    payload: bytes


def _read_exact(handle: object, size: int, label: str) -> bytes:
    raw = handle.read(size)  # type: ignore[attr-defined]
    if len(raw) != size:
        raise PlattGammaTaylorStreamError(f"{label} is truncated")
    return raw


def _decode_fixed_ascii(raw: bytes, label: str) -> bytes:
    value = raw.rstrip(b"\0")
    if b"\0" in value:
        raise PlattGammaTaylorStreamError(f"{label} contains embedded NUL")
    return value


def _validate_records(raw: bytes, *, first_block: int) -> None:
    if len(raw) % RECORD.size:
        raise PlattGammaTaylorStreamError("chunk payload is not whole records")
    for local, values in enumerate(RECORD.iter_unpack(raw)):
        # The first 24 doubles are twelve [lo, hi] intervals: six real and
        # six imaginary coefficients.  The last three doubles are absolute
        # angular/angular/logarithmic error bounds.
        for offset in range(0, 24, 2):
            lower = values[offset]
            upper = values[offset + 1]
            if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
                raise PlattGammaTaylorStreamError(
                    f"invalid coefficient interval at block {first_block + local}"
                )
        for error in values[-3:]:
            if not math.isfinite(error) or error < 0.0:
                raise PlattGammaTaylorStreamError(
                    f"invalid projection error at block {first_block + local}"
                )


class GammaTaylorChunkStream:
    """Bounded-memory authenticated iterator over Gamma/Taylor chunks.

    A chunk is yielded only after its framing, payload SHA-256, and every
    finite interval/error invariant pass.  Chunk acceptance is provisional
    until iteration reaches EOF and validates the footer/global digest.  A
    normal context-manager exit before that point fails closed; a production
    consumer must iterate to exhaustion or call :meth:`finish` before using
    the GPU result as final evidence.
    """

    def __init__(
        self,
        path: Path,
        *,
        expected_first_block: int | None = None,
        expected_block_count: int | None = None,
        expected_chunk_records: int | None = None,
        expected_stream_sha256: str | None = None,
        max_chunk_records: int = 1 << 20,
        allow_fifo: bool = False,
    ) -> None:
        try:
            metadata = path.lstat()
        except OSError as error:
            raise PlattGammaTaylorStreamError(
                f"cannot stat Gamma Taylor stream {path}: {error}"
            ) from error
        mode = metadata.st_mode
        if stat.S_ISLNK(mode):
            raise PlattGammaTaylorStreamError(f"stream path is a symlink: {path}")
        if not stat.S_ISREG(mode) and not (allow_fifo and stat.S_ISFIFO(mode)):
            raise PlattGammaTaylorStreamError(
                f"stream path is not an accepted regular file/FIFO: {path}"
            )
        if max_chunk_records < 1 or max_chunk_records > 1 << 20:
            raise PlattGammaTaylorStreamError("invalid maximum chunk-record bound")
        self.path = path
        self._expected_stream_sha256 = expected_stream_sha256
        self._handle = None
        self._authenticated = False
        self._inspection: GammaTaylorStreamInspection | None = None
        self._artifact_hasher = hashlib.sha256()
        self._stream_hasher = hashlib.sha256(STREAM_HASH_DOMAIN)
        self._consumed = 0
        self._chunk_count = 0
        self._record_payload_bytes = 0
        self._authenticated_stream_bytes = HEADER.size
        try:
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
                os, "O_NOFOLLOW", 0
            )
            descriptor = os.open(path, flags)
            try:
                self._handle = os.fdopen(descriptor, "rb")
            except BaseException:
                os.close(descriptor)
                raise
            opened = os.fstat(self._handle.fileno())
            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise PlattGammaTaylorStreamError(
                    "stream path changed between validation and open"
                )
            self._header_raw = _read_exact(
                self._handle, HEADER.size, "Gamma Taylor header"
            )
            self._artifact_hasher.update(self._header_raw)
            self._stream_hasher.update(self._header_raw)
            fields = HEADER.unpack(self._header_raw)
            (
                magic,
                version,
                header_bytes,
                endian_tag,
                record_encoding,
                record_bytes,
                self.chunk_records,
                degree,
                precision_bits,
                source_lower,
                source_step,
                full_block_count,
                self.first_block,
                self.block_count,
                radius_numerator,
                radius_denominator,
                grid_step_numerator,
                grid_step_denominator,
                gaussian_h,
                upstream_commit,
                flint_commit,
                reviewed_source_sha256,
                contract_id,
                reserved_zero,
            ) = fields
            fixed = (
                magic == MAGIC
                and version == VERSION
                and header_bytes == HEADER.size
                and endian_tag == ENDIAN_TAG
                and record_encoding == RECORD_ENCODING
                and record_bytes == RECORD.size
                and 1 <= self.chunk_records <= max_chunk_records
                and degree == DEGREE
                and precision_bits == PRECISION_BITS
                and source_lower == SOURCE_LOWER
                and source_step == SOURCE_STEP
                and full_block_count == FULL_BLOCK_COUNT
                and radius_numerator == 2_688
                and radius_denominator == 1
                and grid_step_numerator == 21
                and grid_step_denominator == 128
                and gaussian_h == 116
                and upstream_commit == UPSTREAM_COMMIT
                and flint_commit == FLINT_COMMIT
                and reviewed_source_sha256 == REVIEWED_SOURCE_SHA256
                and _decode_fixed_ascii(contract_id, "contract id") == CONTRACT_ID
                and reserved_zero == bytes(len(reserved_zero))
            )
            if not fixed:
                raise PlattGammaTaylorStreamError("Gamma Taylor fixed header differs")
            if SOURCE_LOWER + SOURCE_STEP * FULL_BLOCK_COUNT != FULL_COVERAGE_UPPER:
                raise AssertionError("internal PT21 campaign geometry changed")
            if self.block_count <= 0 or self.first_block >= FULL_BLOCK_COUNT:
                raise PlattGammaTaylorStreamError(
                    "stream range is empty or out of bounds"
                )
            if self.block_count > FULL_BLOCK_COUNT - self.first_block:
                raise PlattGammaTaylorStreamError(
                    "stream range exceeds full campaign"
                )
            if (
                expected_first_block is not None
                and self.first_block != expected_first_block
            ):
                raise PlattGammaTaylorStreamError(
                    "stream first block differs from invocation"
                )
            if (
                expected_block_count is not None
                and self.block_count != expected_block_count
            ):
                raise PlattGammaTaylorStreamError(
                    "stream block count differs from invocation"
                )
            if (
                expected_chunk_records is not None
                and self.chunk_records != expected_chunk_records
            ):
                raise PlattGammaTaylorStreamError(
                    "stream chunk size differs from invocation"
                )
            self.header_sha256 = hashlib.sha256(self._header_raw).hexdigest()
        except BaseException:
            self.close()
            raise

    @property
    def authenticated(self) -> bool:
        """Whether the terminal footer/global digest has passed."""

        return self._authenticated

    @property
    def inspection(self) -> GammaTaylorStreamInspection:
        if self._inspection is None:
            raise PlattGammaTaylorStreamError(
                "stream footer/global digest has not been authenticated"
            )
        return self._inspection

    def __iter__(self) -> GammaTaylorChunkStream:
        return self

    def __next__(self) -> GammaTaylorChunk:
        if self._authenticated:
            raise StopIteration
        if self._handle is None:
            raise PlattGammaTaylorStreamError("Gamma Taylor stream is closed")
        try:
            if self._consumed == self.block_count:
                self._authenticate_footer()
                raise StopIteration
            chunk_raw = _read_exact(
                self._handle, CHUNK_HEADER.size, "Gamma Taylor chunk header"
            )
            (
                chunk_magic,
                chunk_version,
                chunk_header_bytes,
                chunk_first_block,
                chunk_record_count,
                chunk_reserved_zero,
                payload_bytes,
                payload_sha256,
            ) = CHUNK_HEADER.unpack(chunk_raw)
            expected_count = min(
                self.chunk_records, self.block_count - self._consumed
            )
            if (
                chunk_magic != CHUNK_MAGIC
                or chunk_version != VERSION
                or chunk_header_bytes != CHUNK_HEADER.size
                or chunk_first_block != self.first_block + self._consumed
                or chunk_record_count != expected_count
                or chunk_reserved_zero != 0
                or payload_bytes != chunk_record_count * RECORD.size
            ):
                raise PlattGammaTaylorStreamError(
                    f"chunk {self._chunk_count} framing differs"
                )
            payload = _read_exact(
                self._handle, payload_bytes, "Gamma Taylor chunk payload"
            )
            if hashlib.sha256(payload).digest() != payload_sha256:
                raise PlattGammaTaylorStreamError(
                    f"chunk {self._chunk_count} payload digest differs"
                )
            _validate_records(payload, first_block=chunk_first_block)
            # Update the global state only after all local checks pass, and do
            # not expose the payload to the caller before this point.
            self._artifact_hasher.update(chunk_raw)
            self._artifact_hasher.update(payload)
            self._stream_hasher.update(chunk_raw)
            self._stream_hasher.update(payload)
            self._consumed += chunk_record_count
            self._record_payload_bytes += payload_bytes
            self._authenticated_stream_bytes += CHUNK_HEADER.size + payload_bytes
            self._chunk_count += 1
            return GammaTaylorChunk(
                first_block=chunk_first_block,
                record_count=chunk_record_count,
                payload_sha256=payload_sha256.hex(),
                payload=payload,
            )
        except StopIteration:
            raise
        except BaseException:
            self.close()
            raise

    def _authenticate_footer(self) -> None:
        if self._handle is None:
            raise PlattGammaTaylorStreamError("Gamma Taylor stream is closed")
        footer_raw = _read_exact(self._handle, FOOTER.size, "Gamma Taylor footer")
        (
            footer_magic,
            footer_version,
            footer_bytes,
            footer_first_block,
            footer_block_count,
            footer_chunk_count,
            footer_record_payload_bytes,
            footer_authenticated_stream_bytes,
            footer_header_sha256,
            footer_stream_sha256,
            footer_reserved_zero,
        ) = FOOTER.unpack(footer_raw)
        calculated_header_sha256 = hashlib.sha256(self._header_raw).digest()
        calculated_stream_sha256 = self._stream_hasher.digest()
        if (
            footer_magic != FOOTER_MAGIC
            or footer_version != VERSION
            or footer_bytes != FOOTER.size
            or footer_first_block != self.first_block
            or footer_block_count != self.block_count
            or footer_chunk_count != self._chunk_count
            or footer_record_payload_bytes != self._record_payload_bytes
            or footer_authenticated_stream_bytes != self._authenticated_stream_bytes
            or footer_header_sha256 != calculated_header_sha256
            or footer_stream_sha256 != calculated_stream_sha256
            or footer_reserved_zero != bytes(len(footer_reserved_zero))
        ):
            raise PlattGammaTaylorStreamError("Gamma Taylor footer differs")
        if self._handle.read(1):
            raise PlattGammaTaylorStreamError("trailing bytes follow stream footer")
        stream_sha256 = calculated_stream_sha256.hex()
        if (
            self._expected_stream_sha256 is not None
            and stream_sha256 != self._expected_stream_sha256
        ):
            raise PlattGammaTaylorStreamError("stream digest differs from invocation")
        self._artifact_hasher.update(footer_raw)
        first_window_center = (
            SOURCE_LOWER + SOURCE_STEP // 2 + self.first_block * SOURCE_STEP
        )
        last_window_center = (
            first_window_center + (self.block_count - 1) * SOURCE_STEP
        )
        self._inspection = GammaTaylorStreamInspection(
            path=self.path,
            artifact_sha256=self._artifact_hasher.hexdigest(),
            header_sha256=calculated_header_sha256.hex(),
            stream_sha256=stream_sha256,
            first_block=self.first_block,
            block_count=self.block_count,
            chunk_count=self._chunk_count,
            record_payload_bytes=self._record_payload_bytes,
            artifact_bytes=self._authenticated_stream_bytes + FOOTER.size,
            first_window_center=first_window_center,
            last_window_center=last_window_center,
        )
        self._authenticated = True
        self.close()

    def finish(self) -> GammaTaylorStreamInspection:
        """Consume remaining chunks and require the footer/global digest."""

        while not self._authenticated:
            try:
                next(self)
            except StopIteration:
                break
        return self.inspection

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> GammaTaylorChunkStream:
        return self

    def __exit__(self, exception_type: object, _exception: object, _traceback: object) -> bool:
        incomplete = exception_type is None and not self._authenticated
        self.close()
        if incomplete:
            raise PlattGammaTaylorStreamError(
                "stream consumption stopped before authenticated footer"
            )
        return False


def open_gamma_taylor_chunk_stream(
    path: Path,
    *,
    expected_first_block: int | None = None,
    expected_block_count: int | None = None,
    expected_chunk_records: int | None = None,
    expected_stream_sha256: str | None = None,
    max_chunk_records: int = 1 << 20,
    allow_fifo: bool = False,
) -> GammaTaylorChunkStream:
    """Open a strict bounded-memory stream for online chunk consumption.

    Retained artifacts must be regular files.  A measured colocated producer
    may instead use an explicitly authorized named pipe with ``allow_fifo``;
    symlinks and every other file type remain rejected.
    """

    return GammaTaylorChunkStream(
        path,
        expected_first_block=expected_first_block,
        expected_block_count=expected_block_count,
        expected_chunk_records=expected_chunk_records,
        expected_stream_sha256=expected_stream_sha256,
        max_chunk_records=max_chunk_records,
        allow_fifo=allow_fifo,
    )


def inspect_gamma_taylor_stream(
    path: Path,
    *,
    expected_first_block: int | None = None,
    expected_block_count: int | None = None,
    expected_stream_sha256: str | None = None,
) -> GammaTaylorStreamInspection:
    """Authenticate and structurally replay a complete stream artifact."""

    with open_gamma_taylor_chunk_stream(
        path,
        expected_first_block=expected_first_block,
        expected_block_count=expected_block_count,
        expected_stream_sha256=expected_stream_sha256,
    ) as chunks:
        return chunks.finish()


def inspection_report(inspection: GammaTaylorStreamInspection) -> dict[str, object]:
    return {
        "schema": "sparkinterval.tg.platt-gamma-taylor-stream-inspection.v1",
        "accepted": True,
        "artifact_sha256": inspection.artifact_sha256,
        "header_sha256": inspection.header_sha256,
        "stream_sha256": inspection.stream_sha256,
        "first_block": inspection.first_block,
        "block_count": inspection.block_count,
        "chunk_count": inspection.chunk_count,
        "record_bytes": RECORD.size,
        "record_payload_bytes": inspection.record_payload_bytes,
        "artifact_bytes": inspection.artifact_bytes,
        "first_window_center": inspection.first_window_center,
        "last_window_center": inspection.last_window_center,
        "all_chunk_hashes_checked": True,
        "all_projection_intervals_checked": True,
        "source_geometry_checked": True,
        "flint_to_mathlib_realization_proved": False,
        "pt21_source_claim_discharged": False,
    }


__all__ = [
    "CHUNK_HEADER",
    "FOOTER",
    "FULL_BLOCK_COUNT",
    "GammaTaylorChunk",
    "GammaTaylorChunkStream",
    "GammaTaylorStreamInspection",
    "HEADER",
    "PlattGammaTaylorStreamError",
    "RECORD",
    "inspect_gamma_taylor_stream",
    "inspection_report",
    "open_gamma_taylor_chunk_stream",
]
