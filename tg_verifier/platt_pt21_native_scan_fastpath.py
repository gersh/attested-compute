# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Qualification-only native scan certificate for PT21 required packets.

``PT21FSC1`` is a compact, nonterminal certificate.  A pinned native GMP
scanner recomputes the expensive byte-wise FNV checks, validates every DD
disk, and emits the complete direct-event and stationary-candidate lists.
This module then independently revalidates the packet and both lists with
NumPy, using the same outward-binary64 filter and exact ``Fraction`` fallback
as the reference adapter.

The fast path is deliberately separate from the production/reference path:
it does not establish Hardy-Z semantics, Turing semantics, or source
completion, and it cannot be selected implicitly.  Its executable must be
identified by an expected SHA-256 on every invocation.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import fcntl
import hashlib
import os
from pathlib import Path
import stat
import struct
import subprocess
import time
from typing import BinaryIO

try:
    import numpy as np
except ImportError:  # pragma: no cover - exercised on minimal installations
    np = None  # type: ignore[assignment]

from tg_verifier.platt_required_sign_packet import (
    ENDIAN_TAG,
    FULL_BLOCK_COUNT,
    HEADER,
    MAGIC,
    REQUIRED_BEGIN,
    REQUIRED_COUNT,
    REQUIRED_END,
    SAMPLE,
    SAMPLE_ENCODING,
    SIGN_ENCODING,
    SOURCE_LOWER_CENTER,
    SOURCE_STEP,
    SOURCE_TERMS,
    UPSTREAM_COMMIT,
    _fnv1a,
)


CERTIFICATE_MAGIC = b"PT21FSC1"
CERTIFICATE_VERSION = 1
CERTIFICATE_HEADER = struct.Struct("<8sIIIIQQII3I3IQQQ32s32s32s")
CERTIFICATE_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-native-scan-certificate/v1\0"
)
STREAM_REQUEST_MAGIC = b"PT21FSQ1"
STREAM_RESPONSE_MAGIC = b"PT21FSR1"
STREAM_REQUEST_HEADER = struct.Struct("<8sIIQQ32s")
STREAM_RESPONSE_HEADER = struct.Struct("<8sIIQQ32s32s")
STREAM_RANGES = (
    (-12_288, 12_288),  # main
    (-12_800, -12_288),  # left flank
    (12_288, 12_800),  # right flank
)
EXPECTED_PACKET_BYTES = (
    HEADER.size + REQUIRED_COUNT * SAMPLE.size + (REQUIRED_COUNT + 7) // 8
)
MAXIMUM_CERTIFICATE_BYTES = CERTIFICATE_HEADER.size + 4 * (
    sum(upper - lower for lower, upper in STREAM_RANGES)
    + sum(upper - lower - 1 for lower, upper in STREAM_RANGES)
)
MAXIMUM_SCANNER_BYTES = 64 * 1024 * 1024

assert CERTIFICATE_HEADER.size == 192
assert STREAM_REQUEST_HEADER.size == 64
assert STREAM_RESPONSE_HEADER.size == 96


class PT21NativeScanFastpathError(RuntimeError):
    """The pinned scanner, packet, or compact certificate failed closed."""


@dataclass(frozen=True)
class NativeScannerIdentity:
    path: Path
    sha256: str
    size_bytes: int
    source_path_sha256: str
    sealed_image_sha256: str
    sealed_memfd_execution: bool


@dataclass(frozen=True)
class NativePacketScan:
    raw_packet: bytes
    packet_sha256: str
    window_center: int
    direct_offsets: tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]
    stationary_offsets: tuple[
        tuple[int, ...], tuple[int, ...], tuple[int, ...]
    ]
    same_sign_triple_count: int
    exact_fraction_fallback_count: int
    certificate: bytes
    certificate_sha256: str
    scanner: NativeScannerIdentity
    native_certificate_seconds: float
    python_validation_seconds: float

    def positive_at(self, offset: int) -> bool:
        index = offset + 12_870
        if not 0 <= index < REQUIRED_COUNT:
            raise PT21NativeScanFastpathError(
                "sample offset is outside the required packet"
            )
        sign_start = HEADER.size + REQUIRED_COUNT * SAMPLE.size
        return bool(
            self.raw_packet[sign_start + index // 8]
            & (1 << (index % 8))
        )

    def interval_at(self, offset: int) -> tuple[Fraction, Fraction]:
        index = offset + 12_870
        if not 0 <= index < REQUIRED_COUNT:
            raise PT21NativeScanFastpathError(
                "sample offset is outside the required packet"
            )
        high, low, radius = SAMPLE.unpack_from(
            self.raw_packet, HEADER.size + index * SAMPLE.size
        )
        center = Fraction.from_float(high) + Fraction.from_float(low)
        exact_radius = Fraction.from_float(radius)
        result = (center - exact_radius, center + exact_radius)
        if (self.positive_at(offset) and result[0] <= 0) or (
            not self.positive_at(offset) and result[1] >= 0
        ):
            raise PT21NativeScanFastpathError(
                "native scan retained a sample whose exact disk contains zero"
            )
        return result


@dataclass(frozen=True)
class _PacketFields:
    window_center: int
    sample_raw: bytes
    sign_raw: bytes
    sample_fnv1a64: int
    sign_fnv1a64: int


def _write_all(stream: BinaryIO, raw: bytes) -> None:
    view = memoryview(raw)
    while view:
        wrote = stream.write(view)
        if wrote is None or wrote <= 0:
            raise PT21NativeScanFastpathError(
                "short write to persistent native scanner"
            )
        view = view[wrote:]


def _read_exact(stream: BinaryIO, size: int, label: str) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise PT21NativeScanFastpathError(f"{label} is truncated")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class NativeScanSession:
    """One identity-pinned, ordered scanner process for many block packets."""

    def __init__(
        self,
        *,
        scanner: Path,
        expected_scanner_sha256: str,
    ) -> None:
        descriptor = -1
        try:
            descriptor, self.scanner = _pinned_scanner(
                scanner, expected_scanner_sha256
            )
            executable = f"/proc/self/fd/{descriptor}"
            self._process = subprocess.Popen(
                [executable, "--stream"],
                executable=executable,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                pass_fds=(descriptor,),
                bufsize=0,
            )
        except (OSError, ValueError) as error:
            raise PT21NativeScanFastpathError(
                f"cannot start persistent pinned native scanner: {error}"
            ) from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        self._request_id = 0
        self._closed = False

    def __enter__(self) -> "NativeScanSession":
        return self

    def __exit__(self, *_error: object) -> None:
        self.close()

    def _failure(self, message: str) -> PT21NativeScanFastpathError:
        if self._process.poll() is None:
            self._process.kill()
        _stdout, stderr = self._process.communicate()
        diagnostic = stderr.decode("utf-8", errors="replace").strip()
        self._closed = True
        return PT21NativeScanFastpathError(
            message + (f": {diagnostic}" if diagnostic else "")
        )

    def certificate(self, raw_packet: bytes) -> tuple[bytes, float]:
        """Return one ordered framed response without process startup."""

        if self._closed or self._process.poll() is not None:
            raise PT21NativeScanFastpathError(
                "persistent native scanner is not running"
            )
        if len(raw_packet) != EXPECTED_PACKET_BYTES:
            raise PT21NativeScanFastpathError(
                "persistent native scanner packet length differs"
            )
        if self._request_id >= 1 << 64:
            raise PT21NativeScanFastpathError(
                "persistent native scanner request id overflows uint64"
            )
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        packet_digest = hashlib.sha256(raw_packet).digest()
        request = STREAM_REQUEST_HEADER.pack(
            STREAM_REQUEST_MAGIC,
            1,
            STREAM_REQUEST_HEADER.size,
            self._request_id,
            len(raw_packet),
            packet_digest,
        )
        started = time.perf_counter()
        try:
            _write_all(self._process.stdin, request)
            _write_all(self._process.stdin, raw_packet)
            self._process.stdin.flush()
            response = _read_exact(
                self._process.stdout,
                STREAM_RESPONSE_HEADER.size,
                "persistent native scan response header",
            )
            (
                magic,
                version,
                header_bytes,
                request_id,
                certificate_bytes,
                response_packet_sha256,
                response_certificate_sha256,
            ) = STREAM_RESPONSE_HEADER.unpack(response)
            if (
                magic != STREAM_RESPONSE_MAGIC
                or version != 1
                or header_bytes != STREAM_RESPONSE_HEADER.size
                or request_id != self._request_id
                or certificate_bytes < CERTIFICATE_HEADER.size
                or certificate_bytes > MAXIMUM_CERTIFICATE_BYTES
                or response_packet_sha256 != packet_digest
            ):
                raise self._failure(
                    "persistent native scan response framing differs"
                )
            certificate = _read_exact(
                self._process.stdout,
                certificate_bytes,
                "persistent native scan certificate",
            )
        except (
            BrokenPipeError,
            OSError,
            PT21NativeScanFastpathError,
        ) as error:
            if self._closed:
                raise
            raise self._failure(
                f"persistent native scanner pipe failed: {error}"
            ) from error
        if (
            hashlib.sha256(certificate).digest()
            != response_certificate_sha256
        ):
            raise self._failure(
                "persistent native scan response digest differs"
            )
        self._request_id += 1
        return certificate, time.perf_counter() - started

    def close(self) -> None:
        if self._closed:
            return
        assert self._process.stdin is not None
        try:
            self._process.stdin.close()
            self._process.stdin = None
            stdout, stderr = self._process.communicate(timeout=30)
        except subprocess.TimeoutExpired as error:
            self._process.kill()
            self._process.communicate()
            self._closed = True
            raise PT21NativeScanFastpathError(
                "persistent native scanner did not stop at framed EOF"
            ) from error
        self._closed = True
        diagnostic = stderr.decode("utf-8", errors="replace").strip()
        if self._process.returncode != 0 or stdout or diagnostic:
            raise PT21NativeScanFastpathError(
                "persistent native scanner rejected terminal EOF"
                + (f": {diagnostic}" if diagnostic else "")
            )


def _open_regular(path: Path, label: str) -> tuple[BinaryIO, int]:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as error:
        raise PT21NativeScanFastpathError(
            f"cannot open {label} without following links: {path}: {error}"
        ) from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size < 1:
            raise PT21NativeScanFastpathError(
                f"{label} is not a nonempty regular file"
            )
        return os.fdopen(descriptor, "rb", closefd=True), metadata.st_size
    except Exception:
        os.close(descriptor)
        raise


def _regular_bytes(path: Path, label: str, *, exact_size: int) -> bytes:
    stream, size = _open_regular(path, label)
    with stream:
        if size != exact_size:
            raise PT21NativeScanFastpathError(
                f"{label} byte length differs"
            )
        raw = stream.read(exact_size + 1)
        final_size = os.fstat(stream.fileno()).st_size
    if len(raw) != exact_size or final_size != exact_size:
        raise PT21NativeScanFastpathError(
            f"{label} changed while being read"
        )
    return raw


def _lower_sha256(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PT21NativeScanFastpathError(
            f"{label} is not lowercase SHA-256"
        )
    return value


def _pinned_scanner(
    path: Path, expected_sha256: str
) -> tuple[int, NativeScannerIdentity]:
    expected = _lower_sha256(
        expected_sha256, "expected native scanner SHA-256"
    )
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as error:
        raise PT21NativeScanFastpathError(
            f"cannot open native scanner without following links: {error}"
        ) from error
    sealed_descriptor = -1
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size < 1
            or metadata.st_size > MAXIMUM_SCANNER_BYTES
            or metadata.st_mode & 0o111 == 0
        ):
            raise PT21NativeScanFastpathError(
                "native scanner is not a nonempty executable regular file"
            )
        digest = hashlib.sha256()
        source_bytes = bytearray()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            source_bytes.extend(chunk)
        final = os.fstat(descriptor)
        source_sha256 = digest.hexdigest()
        if (
            len(source_bytes) != metadata.st_size
            or final.st_size != metadata.st_size
            or source_sha256 != expected
        ):
            raise PT21NativeScanFastpathError(
                "native scanner bytes differ from the pinned executable"
            )
        if not hasattr(os, "memfd_create"):
            raise PT21NativeScanFastpathError(
                "sealed memfd execution is unavailable on this platform"
            )
        sealed_descriptor = os.memfd_create(
            "sparkinterval-pt21-native-scan",
            os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
        )
        view = memoryview(source_bytes)
        while view:
            wrote = os.write(sealed_descriptor, view)
            if wrote <= 0:
                raise PT21NativeScanFastpathError(
                    "short write while copying scanner into sealed memfd"
                )
            view = view[wrote:]
        os.fchmod(sealed_descriptor, 0o500)
        os.lseek(sealed_descriptor, 0, os.SEEK_SET)
        sealed_digest = hashlib.sha256()
        sealed_size = 0
        while True:
            chunk = os.read(sealed_descriptor, 1024 * 1024)
            if not chunk:
                break
            sealed_digest.update(chunk)
            sealed_size += len(chunk)
        sealed_sha256 = sealed_digest.hexdigest()
        if (
            sealed_size != len(source_bytes)
            or sealed_sha256 != source_sha256
            or sealed_sha256 != expected
        ):
            raise PT21NativeScanFastpathError(
                "copied scanner image differs before sealing"
            )
        required_seals = (
            fcntl.F_SEAL_WRITE
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_SEAL
        )
        fcntl.fcntl(
            sealed_descriptor, fcntl.F_ADD_SEALS, required_seals
        )
        if (
            fcntl.fcntl(sealed_descriptor, fcntl.F_GET_SEALS)
            & required_seals
        ) != required_seals:
            raise PT21NativeScanFastpathError(
                "native scanner memfd did not retain all required seals"
            )
        os.lseek(sealed_descriptor, 0, os.SEEK_SET)
        identity = NativeScannerIdentity(
            path=path,
            sha256=sealed_sha256,
            size_bytes=sealed_size,
            source_path_sha256=source_sha256,
            sealed_image_sha256=sealed_sha256,
            sealed_memfd_execution=True,
        )
    except Exception:
        if sealed_descriptor >= 0:
            os.close(sealed_descriptor)
        raise
    finally:
        os.close(descriptor)
    return sealed_descriptor, identity


def _packet_fields(raw: bytes) -> _PacketFields:
    if len(raw) != EXPECTED_PACKET_BYTES:
        raise PT21NativeScanFastpathError(
            "required-sign packet byte length differs"
        )
    (
        magic,
        version,
        header_bytes,
        endian_tag,
        sample_encoding,
        sign_encoding,
        source_terms,
        required_begin,
        required_end,
        required_count,
        reserved_zero,
        window_center,
        sample_bytes,
        sign_bytes,
        sample_fnv1a64,
        sign_fnv1a64,
        _source_packet_bytes,
        source_packet_sha_raw,
        upstream_commit,
    ) = HEADER.unpack_from(raw)
    if (
        magic != MAGIC
        or version != 1
        or header_bytes != HEADER.size
        or endian_tag != ENDIAN_TAG
        or sample_encoding != SAMPLE_ENCODING
        or sign_encoding != SIGN_ENCODING
        or source_terms != SOURCE_TERMS
        or required_begin != REQUIRED_BEGIN
        or required_end != REQUIRED_END
        or required_count != REQUIRED_COUNT
        or reserved_zero != 0
        or sample_bytes != REQUIRED_COUNT * SAMPLE.size
        or sign_bytes != (REQUIRED_COUNT + 7) // 8
        or upstream_commit != UPSTREAM_COMMIT
    ):
        raise PT21NativeScanFastpathError(
            "required-sign fixed header differs"
        )
    delta = window_center - SOURCE_LOWER_CENTER
    if (
        delta < 0
        or delta % SOURCE_STEP
        or delta // SOURCE_STEP >= FULL_BLOCK_COUNT
    ):
        raise PT21NativeScanFastpathError(
            "required-sign center is outside the source grid"
        )
    try:
        source_packet_sha = source_packet_sha_raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise PT21NativeScanFastpathError(
            "required-sign source SHA-256 is not ASCII"
        ) from error
    _lower_sha256(source_packet_sha, "required-sign source SHA-256")
    sample_start = HEADER.size
    sign_start = sample_start + sample_bytes
    return _PacketFields(
        window_center=window_center,
        sample_raw=raw[sample_start:sign_start],
        sign_raw=raw[sign_start:],
        sample_fnv1a64=sample_fnv1a64,
        sign_fnv1a64=sign_fnv1a64,
    )


def run_native_scan_certificate(
    raw_packet: bytes,
    *,
    scanner: Path,
    expected_scanner_sha256: str,
    timeout_seconds: int = 30,
) -> tuple[bytes, NativeScannerIdentity, float]:
    """Run exactly the pinned scanner and return its bounded stdout."""

    if (
        isinstance(timeout_seconds, bool)
        or not 1 <= timeout_seconds <= 300
    ):
        raise PT21NativeScanFastpathError(
            "native scanner timeout is outside 1..300 seconds"
        )
    descriptor = -1
    started = time.perf_counter()
    try:
        descriptor, identity = _pinned_scanner(
            scanner, expected_scanner_sha256
        )
        executable = f"/proc/self/fd/{descriptor}"
        completed = subprocess.run(
            [executable],
            executable=executable,
            input=raw_packet,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(descriptor,),
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        raise PT21NativeScanFastpathError(
            f"cannot execute pinned native scanner: {error}"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    elapsed = time.perf_counter() - started
    diagnostic = completed.stderr.decode("utf-8", errors="replace").strip()
    if completed.returncode != 0 or diagnostic:
        raise PT21NativeScanFastpathError(
            "native scanner rejected the required-sign packet"
            + (f": {diagnostic}" if diagnostic else "")
        )
    if not CERTIFICATE_HEADER.size <= len(
        completed.stdout
    ) <= MAXIMUM_CERTIFICATE_BYTES:
        raise PT21NativeScanFastpathError(
            "native scan certificate has an invalid byte length"
        )
    return completed.stdout, identity, elapsed


def _fraction_interval(
    rows: "np.ndarray", index: int
) -> tuple[Fraction, Fraction]:
    high = float(rows[index, 0])
    low = float(rows[index, 1])
    radius = Fraction.from_float(float(rows[index, 2]))
    center = Fraction.from_float(high) + Fraction.from_float(low)
    return (center - radius, center + radius)


def _numpy_replay(
    fields: _PacketFields,
) -> tuple[
    tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]],
    tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]],
    int,
    int,
]:
    if np is None:
        raise PT21NativeScanFastpathError(
            "NumPy is required for the qualification-only fast path"
        )
    rows = np.frombuffer(fields.sample_raw, dtype="<f8").reshape(
        REQUIRED_COUNT, 3
    )
    high = rows[:, 0]
    low = rows[:, 1]
    radius = rows[:, 2]
    if (
        not bool(np.isfinite(rows).all())
        or bool(np.any(radius < 0.0))
    ):
        raise PT21NativeScanFastpathError(
            "required-sign packet contains an invalid DD disk"
        )
    with np.errstate(over="ignore", invalid="ignore"):
        center_lower = np.maximum(0.0, np.abs(high) - np.abs(low))
    if bool(np.any(center_lower <= radius)) or bool(np.any(high == 0.0)):
        raise PT21NativeScanFastpathError(
            "required-sign packet contains an ambiguous DD disk"
        )
    sign_octets = np.frombuffer(fields.sign_raw, dtype=np.uint8)
    sign_bits = np.unpackbits(sign_octets, bitorder="little")[:REQUIRED_COUNT]
    positive = sign_bits.astype(np.bool_)
    if not bool(np.array_equal(positive, high > 0.0)):
        raise PT21NativeScanFastpathError(
            "required-sign bit differs from its DD disk"
        )
    used_final_bits = REQUIRED_COUNT % 8
    if used_final_bits and fields.sign_raw[-1] >> used_final_bits:
        raise PT21NativeScanFastpathError(
            "required-sign unused high sign bits are nonzero"
        )

    with np.errstate(over="ignore", invalid="ignore"):
        center = high + low
        center_lo = np.nextafter(center, -np.inf)
        center_hi = np.nextafter(center, np.inf)
        directed_lo = np.nextafter(center_lo - radius, -np.inf)
        directed_hi = np.nextafter(center_hi + radius, np.inf)
    unusable = (
        ~np.isfinite(center)
        | ~np.isfinite(directed_lo)
        | ~np.isfinite(directed_hi)
    )
    directed_lo = directed_lo.copy()
    directed_hi = directed_hi.copy()
    directed_lo[unusable] = -np.inf
    directed_hi[unusable] = np.inf

    direct_result: list[tuple[int, ...]] = []
    stationary_result: list[tuple[int, ...]] = []
    same_sign_count = 0
    exact_fallback_count = 0
    for lower_offset, upper_offset in STREAM_RANGES:
        lower_index = lower_offset + 12_870
        upper_index = upper_offset + 12_870
        transition_indices = np.flatnonzero(
            positive[lower_index:upper_index]
            != positive[lower_index + 1 : upper_index + 1]
        )
        direct_result.append(
            tuple(
                int(lower_offset + index)
                for index in transition_indices.tolist()
            )
        )

        first_slice = slice(lower_index, upper_index - 1)
        middle_slice = slice(lower_index + 1, upper_index)
        right_slice = slice(lower_index + 2, upper_index + 1)
        first_positive = positive[first_slice]
        middle_positive = positive[middle_slice]
        right_positive = positive[right_slice]
        same = (
            (first_positive == middle_positive)
            & (middle_positive == right_positive)
        )
        same_sign_count += int(np.count_nonzero(same))
        positive_candidate = (
            same
            & middle_positive
            & (directed_lo[first_slice] > directed_hi[middle_slice])
            & (directed_lo[right_slice] > directed_hi[middle_slice])
        )
        negative_candidate = (
            same
            & ~middle_positive
            & (directed_lo[middle_slice] > directed_hi[first_slice])
            & (directed_lo[middle_slice] > directed_hi[right_slice])
        )
        row_equal_left = np.all(
            rows[first_slice] == rows[middle_slice], axis=1
        )
        row_equal_right = np.all(
            rows[right_slice] == rows[middle_slice], axis=1
        )
        positive_rejected = (
            same
            & middle_positive
            & (
                row_equal_left
                | row_equal_right
                | (directed_hi[first_slice] <= directed_lo[middle_slice])
                | (directed_hi[right_slice] <= directed_lo[middle_slice])
            )
        )
        negative_rejected = (
            same
            & ~middle_positive
            & (
                row_equal_left
                | row_equal_right
                | (directed_hi[middle_slice] <= directed_lo[first_slice])
                | (directed_hi[middle_slice] <= directed_lo[right_slice])
            )
        )
        candidate = positive_candidate | negative_candidate
        undecided = same & ~candidate & ~positive_rejected & ~negative_rejected
        fallback_indices = np.flatnonzero(undecided)
        exact_fallback_count += int(fallback_indices.size)
        for local in fallback_indices.tolist():
            first = lower_index + int(local)
            middle = first + 1
            right = first + 2
            first_interval = _fraction_interval(rows, first)
            middle_interval = _fraction_interval(rows, middle)
            right_interval = _fraction_interval(rows, right)
            if bool(middle_positive[int(local)]):
                accepted = (
                    first_interval[0] > middle_interval[1]
                    and right_interval[0] > middle_interval[1]
                )
            else:
                accepted = (
                    middle_interval[0] > first_interval[1]
                    and middle_interval[0] > right_interval[1]
                )
            candidate[int(local)] = accepted
        stationary_indices = np.flatnonzero(candidate)
        stationary_result.append(
            tuple(
                int(lower_offset + index)
                for index in stationary_indices.tolist()
            )
        )
    return (
        (direct_result[0], direct_result[1], direct_result[2]),
        (
            stationary_result[0],
            stationary_result[1],
            stationary_result[2],
        ),
        same_sign_count,
        exact_fallback_count,
    )


def _ordered_offsets(
    values: tuple[int, ...],
    *,
    lower: int,
    upper_exclusive: int,
    label: str,
) -> None:
    previous: int | None = None
    for value in values:
        if not lower <= value < upper_exclusive:
            raise PT21NativeScanFastpathError(
                f"{label} offset leaves its fixed stream"
            )
        if previous is not None and value <= previous:
            raise PT21NativeScanFastpathError(
                f"{label} offsets are not strictly increasing"
            )
        previous = value


def _validate_native_scan_certificate_core(
    raw_packet: bytes,
    certificate: bytes,
    *,
    scanner: NativeScannerIdentity,
    recompute_packet_wire_checksums: bool,
    native_certificate_seconds: float = 0.0,
) -> NativePacketScan:
    """Validate framing, packet samples, and complete lists.

    ``recompute_packet_wire_checksums=False`` is reserved for the private call
    path that has just received the certificate from an identity-pinned,
    sealed scanner.  The historical, nonstandard FNV-family wire fields are
    redundant with the complete packet SHA-256 and semantic replay, but remain
    part of the strict public packet format.
    """

    started = time.perf_counter()
    fields = _packet_fields(raw_packet)
    if not CERTIFICATE_HEADER.size <= len(
        certificate
    ) <= MAXIMUM_CERTIFICATE_BYTES:
        raise PT21NativeScanFastpathError(
            "native scan certificate has an invalid byte length"
        )
    (
        magic,
        version,
        header_bytes,
        endian_tag,
        native_exact_fallback_count,
        packet_bytes,
        window_center,
        sample_count,
        same_sign_triple_count,
        direct_main_count,
        direct_left_count,
        direct_right_count,
        stationary_main_count,
        stationary_left_count,
        stationary_right_count,
        body_bytes,
        sample_fnv1a64,
        sign_fnv1a64,
        packet_sha256,
        body_sha256,
        certificate_sha256,
    ) = CERTIFICATE_HEADER.unpack_from(certificate)
    direct_counts = (
        direct_main_count,
        direct_left_count,
        direct_right_count,
    )
    stationary_counts = (
        stationary_main_count,
        stationary_left_count,
        stationary_right_count,
    )
    expected_body_bytes = 4 * (sum(direct_counts) + sum(stationary_counts))
    if (
        magic != CERTIFICATE_MAGIC
        or version != CERTIFICATE_VERSION
        or header_bytes != CERTIFICATE_HEADER.size
        or endian_tag != ENDIAN_TAG
        or packet_bytes != len(raw_packet)
        or window_center != fields.window_center
        or sample_count != REQUIRED_COUNT
        or body_bytes != expected_body_bytes
        or len(certificate) != CERTIFICATE_HEADER.size + body_bytes
        or sample_fnv1a64 != fields.sample_fnv1a64
        or sign_fnv1a64 != fields.sign_fnv1a64
    ):
        raise PT21NativeScanFastpathError(
            "native scan certificate framing differs"
        )
    if recompute_packet_wire_checksums and (
        _fnv1a(fields.sample_raw) != sample_fnv1a64
        or _fnv1a(fields.sign_raw) != sign_fnv1a64
    ):
        raise PT21NativeScanFastpathError(
            "native scan version-1 wire checksum differs from the scalar reference"
        )
    if packet_sha256 != hashlib.sha256(raw_packet).digest():
        raise PT21NativeScanFastpathError(
            "native scan packet digest differs"
        )
    body = certificate[CERTIFICATE_HEADER.size :]
    if body_sha256 != hashlib.sha256(body).digest():
        raise PT21NativeScanFastpathError(
            "native scan body digest differs"
        )
    if certificate_sha256 != hashlib.sha256(
        CERTIFICATE_DOMAIN + certificate[:160] + body
    ).digest():
        raise PT21NativeScanFastpathError(
            "native scan certificate digest differs"
        )
    values = struct.unpack(f"<{len(body) // 4}i", body) if body else ()
    position = 0
    direct: list[tuple[int, ...]] = []
    stationary: list[tuple[int, ...]] = []
    for count in direct_counts:
        direct.append(tuple(values[position : position + count]))
        position += count
    for count in stationary_counts:
        stationary.append(tuple(values[position : position + count]))
        position += count
    if position != len(values):
        raise PT21NativeScanFastpathError(
            "native scan body count does not consume the wire"
        )
    for index, (lower, upper) in enumerate(STREAM_RANGES):
        _ordered_offsets(
            direct[index],
            lower=lower,
            upper_exclusive=upper,
            label=f"direct[{index}]",
        )
        _ordered_offsets(
            stationary[index],
            lower=lower,
            upper_exclusive=upper - 1,
            label=f"stationary[{index}]",
        )

    replay_direct, replay_stationary, replay_same, fallback_count = (
        _numpy_replay(fields)
    )
    native_direct = (direct[0], direct[1], direct[2])
    native_stationary = (stationary[0], stationary[1], stationary[2])
    if (
        native_direct != replay_direct
        or native_stationary != replay_stationary
        or same_sign_triple_count != replay_same
        or native_exact_fallback_count != fallback_count
    ):
        raise PT21NativeScanFastpathError(
            "native scan lists differ from independent NumPy/Fraction replay"
        )
    elapsed = time.perf_counter() - started
    return NativePacketScan(
        raw_packet=raw_packet,
        packet_sha256=packet_sha256.hex(),
        window_center=window_center,
        direct_offsets=native_direct,
        stationary_offsets=native_stationary,
        same_sign_triple_count=same_sign_triple_count,
        exact_fraction_fallback_count=fallback_count,
        certificate=certificate,
        certificate_sha256=hashlib.sha256(certificate).hexdigest(),
        scanner=scanner,
        native_certificate_seconds=native_certificate_seconds,
        python_validation_seconds=elapsed,
    )


def validate_native_scan_certificate(
    raw_packet: bytes,
    certificate: bytes,
    *,
    scanner: NativeScannerIdentity,
    native_certificate_seconds: float = 0.0,
) -> NativePacketScan:
    """Strictly validate one standalone certificate and complete packet.

    Unlike the private pinned-execution path, this exported validator always
    recomputes both redundant version-1 wire checksums.  A self-consistent
    certificate digest is not evidence that the certificate actually came
    from the native scanner, so standalone validation must enforce the entire
    packet format.
    """

    return _validate_native_scan_certificate_core(
        raw_packet,
        certificate,
        scanner=scanner,
        recompute_packet_wire_checksums=True,
        native_certificate_seconds=native_certificate_seconds,
    )


def _validate_certificate_from_pinned_sealed_scanner(
    raw_packet: bytes,
    certificate: bytes,
    *,
    scanner: NativeScannerIdentity,
    native_certificate_seconds: float,
) -> NativePacketScan:
    """Replay output received directly from the pinned sealed scanner.

    The native scanner has already recomputed both historical wire checksums
    before emitting the packet-bound certificate.  The independent Python side
    still checks the complete packet SHA-256, every DD/sign relationship, all
    offsets, and every candidate list.  Skipping only the redundant scalar
    Python checksum pass keeps the qualification fast path useful without
    weakening the standalone validator.
    """

    if (
        not isinstance(scanner, NativeScannerIdentity)
        or scanner.sealed_memfd_execution is not True
        or type(scanner.size_bytes) is not int
        or not 1 <= scanner.size_bytes <= MAXIMUM_SCANNER_BYTES
        or _lower_sha256(scanner.sha256, "sealed scanner SHA-256")
        != _lower_sha256(
            scanner.source_path_sha256, "scanner source-path SHA-256"
        )
        or scanner.sha256
        != _lower_sha256(
            scanner.sealed_image_sha256, "scanner sealed-image SHA-256"
        )
    ):
        raise PT21NativeScanFastpathError(
            "trusted native scan path lacks one pinned sealed scanner identity"
        )
    return _validate_native_scan_certificate_core(
        raw_packet,
        certificate,
        scanner=scanner,
        recompute_packet_wire_checksums=False,
        native_certificate_seconds=native_certificate_seconds,
    )


def scan_required_sign_packet(
    path: Path,
    *,
    scanner: Path,
    expected_scanner_sha256: str,
) -> NativePacketScan:
    """Create and independently replay one pinned native scan certificate."""

    raw = _regular_bytes(
        path, "required-sign packet", exact_size=EXPECTED_PACKET_BYTES
    )
    certificate, identity, native_seconds = run_native_scan_certificate(
        raw,
        scanner=scanner,
        expected_scanner_sha256=expected_scanner_sha256,
    )
    return _validate_certificate_from_pinned_sealed_scanner(
        raw,
        certificate,
        scanner=identity,
        native_certificate_seconds=native_seconds,
    )


def scan_required_sign_packet_with_session(
    path: Path,
    *,
    session: NativeScanSession,
) -> NativePacketScan:
    """Scan one packet through an already identity-pinned ordered process."""

    raw = _regular_bytes(
        path, "required-sign packet", exact_size=EXPECTED_PACKET_BYTES
    )
    certificate, native_seconds = session.certificate(raw)
    return _validate_certificate_from_pinned_sealed_scanner(
        raw,
        certificate,
        scanner=session.scanner,
        native_certificate_seconds=native_seconds,
    )


def arithmetic_range_report() -> dict[str, object]:
    """Machine-readable reason fixed-width arithmetic is insufficient."""

    smallest = Fraction.from_float(float.fromhex("0x0.0000000000001p-1022"))
    largest = Fraction.from_float(float.fromhex("0x1.fffffffffffffp+1023"))
    return {
        "schema": (
            "sparkinterval.tg.platt-pt21-native-scan-arithmetic-range.v1"
        ),
        "accepted": True,
        "minimum_subnormal_denominator_bits": (
            smallest.denominator.bit_length()
        ),
        "maximum_finite_integer_bits": largest.numerator.bit_length(),
        "int128_sufficient_for_all_accepted_binary64": False,
        "native_exact_backend": "gmp-mpq",
        "python_independent_backend": (
            "numpy-directed-binary64-with-fraction-fallback"
        ),
        "turing_rationals_handled_by_native_scanner": False,
        "analytic_realization_proved": False,
        "source_claim_ready": False,
    }


__all__ = [
    "CERTIFICATE_DOMAIN",
    "CERTIFICATE_HEADER",
    "CERTIFICATE_MAGIC",
    "NativePacketScan",
    "NativeScanSession",
    "NativeScannerIdentity",
    "PT21NativeScanFastpathError",
    "arithmetic_range_report",
    "run_native_scan_certificate",
    "scan_required_sign_packet",
    "scan_required_sign_packet_with_session",
    "validate_native_scan_certificate",
]
