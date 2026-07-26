# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Strict decoder for the PT21 required-region DD/sign handoff.

The packet is small enough for independent replay of one window.  Production
workers stream the same 25,741 DD disks ephemerally into interpolation and
zero isolation; retaining this payload for all 2.97 billion windows would be
impractical.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re
import struct


MAGIC = b"PT21SGN1"
VERSION = 1
ENDIAN_TAG = 0x01020304
SAMPLE_ENCODING = 1
SIGN_ENCODING = 1
SOURCE_TERMS = 768_000
SOURCE_LOWER_CENTER = 10_000_000_504
SOURCE_STEP = 1_008
FULL_BLOCK_COUNT = 2_966_443_783
REQUIRED_BEGIN = 52_666
REQUIRED_END = 78_406
REQUIRED_COUNT = 25_741
UPSTREAM_COMMIT = b"42b21426718e542daa2b006dc05ea2d7f26426e6"
HEADER = struct.Struct("<8s10I6Q64s40s")
SAMPLE = struct.Struct("<ddd")
FNV_OFFSET = 1_469_598_103_934_665_603
FNV_PRIME = 1_099_511_628_211


class PlattRequiredSignPacketError(RuntimeError):
    """The binary handoff failed a structural or arithmetic check."""


@dataclass(frozen=True)
class RequiredSample:
    center_hi: float
    center_lo: float
    radius: float
    positive: bool


@dataclass(frozen=True)
class RequiredSignPacket:
    path: Path
    sha256: str
    window_center: int
    source_packet_sha256: str
    source_packet_bytes: int
    sample_fnv1a64: int
    sign_fnv1a64: int
    samples: tuple[RequiredSample, ...]


def _fnv1a(raw: bytes) -> int:
    """Return the historical PT21SGN1 v1 wire checksum.

    The field name predates this checker.  Its offset
    ``0x14650fb0739d0383`` is not the standard FNV-1a-64 offset basis, so this
    is a versioned FNV-family recurrence rather than standard FNV-1a.  SHA-256
    is the cryptographic integrity boundary.
    """

    value = FNV_OFFSET
    for byte in raw:
        value ^= byte
        value = (value * FNV_PRIME) & ((1 << 64) - 1)
    return value


def _regular_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise PlattRequiredSignPacketError(f"not a regular file: {path}")
    try:
        return path.read_bytes()
    except OSError as error:
        raise PlattRequiredSignPacketError(f"cannot read {path}: {error}") from error


def load_required_sign_packet(
    path: Path, *, source_packet: Path | None = None
) -> RequiredSignPacket:
    raw = _regular_bytes(path)
    if len(raw) < HEADER.size:
        raise PlattRequiredSignPacketError("required-sign header is truncated")
    fields = HEADER.unpack_from(raw)
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
        source_packet_bytes,
        source_packet_sha_raw,
        upstream_commit,
    ) = fields
    fixed = (
        magic == MAGIC
        and version == VERSION
        and header_bytes == HEADER.size
        and endian_tag == ENDIAN_TAG
        and sample_encoding == SAMPLE_ENCODING
        and sign_encoding == SIGN_ENCODING
        and source_terms == SOURCE_TERMS
        and required_begin == REQUIRED_BEGIN
        and required_end == REQUIRED_END
        and required_count == REQUIRED_COUNT
        and reserved_zero == 0
        and upstream_commit == UPSTREAM_COMMIT
    )
    if not fixed:
        raise PlattRequiredSignPacketError("required-sign fixed header differs")
    block_delta = window_center - SOURCE_LOWER_CENTER
    if (
        block_delta < 0
        or block_delta % SOURCE_STEP != 0
        or block_delta // SOURCE_STEP >= FULL_BLOCK_COUNT
    ):
        raise PlattRequiredSignPacketError("window center is outside the fixed campaign grid")
    expected_sample_bytes = REQUIRED_COUNT * SAMPLE.size
    expected_sign_bytes = (REQUIRED_COUNT + 7) // 8
    if sample_bytes != expected_sample_bytes or sign_bytes != expected_sign_bytes:
        raise PlattRequiredSignPacketError("required-sign payload lengths differ")
    if len(raw) != HEADER.size + sample_bytes + sign_bytes:
        raise PlattRequiredSignPacketError("required-sign file length is not exact")
    sample_raw = raw[HEADER.size : HEADER.size + sample_bytes]
    sign_raw = raw[HEADER.size + sample_bytes :]
    if _fnv1a(sample_raw) != sample_fnv1a64 or _fnv1a(sign_raw) != sign_fnv1a64:
        raise PlattRequiredSignPacketError("required-sign payload checksum differs")
    unused = 8 - (REQUIRED_COUNT % 8)
    if unused != 8 and sign_raw[-1] >> (8 - unused) != 0:
        raise PlattRequiredSignPacketError("unused high sign bits are nonzero")

    samples: list[RequiredSample] = []
    for index, (hi, lo, radius) in enumerate(SAMPLE.iter_unpack(sample_raw)):
        if not all(math.isfinite(value) for value in (hi, lo, radius)) or radius < 0.0:
            raise PlattRequiredSignPacketError(f"invalid DD disk at retained index {index}")
        center_lower = max(0.0, abs(hi) - abs(lo))
        if not center_lower > radius or hi == 0.0:
            raise PlattRequiredSignPacketError(
                f"ambiguous DD disk at retained index {index}"
            )
        encoded_positive = bool(sign_raw[index // 8] & (1 << (index % 8)))
        if encoded_positive != (hi > 0.0):
            raise PlattRequiredSignPacketError(
                f"sign bit differs from DD disk at retained index {index}"
            )
        samples.append(RequiredSample(hi, lo, radius, encoded_positive))

    try:
        source_packet_sha256 = source_packet_sha_raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise PlattRequiredSignPacketError("source SHA-256 is not ASCII") from error
    if not re.fullmatch(r"[0-9a-f]{64}", source_packet_sha256):
        raise PlattRequiredSignPacketError("source SHA-256 is malformed")
    if source_packet is not None:
        source_raw = _regular_bytes(source_packet)
        if len(source_raw) != source_packet_bytes:
            raise PlattRequiredSignPacketError("bound source packet size differs")
        if hashlib.sha256(source_raw).hexdigest() != source_packet_sha256:
            raise PlattRequiredSignPacketError("bound source packet digest differs")
    return RequiredSignPacket(
        path=path,
        sha256=hashlib.sha256(raw).hexdigest(),
        window_center=window_center,
        source_packet_sha256=source_packet_sha256,
        source_packet_bytes=source_packet_bytes,
        sample_fnv1a64=sample_fnv1a64,
        sign_fnv1a64=sign_fnv1a64,
        samples=tuple(samples),
    )


def inspect_required_sign_packet(
    path: Path, *, source_packet: Path | None = None
) -> dict[str, object]:
    packet = load_required_sign_packet(path, source_packet=source_packet)
    positive = sum(sample.positive for sample in packet.samples)
    return {
        "schema": "sparkinterval.tg.platt-required-sign-packet-inspection.v1",
        "accepted": True,
        "packet_sha256": packet.sha256,
        "window_center": packet.window_center,
        "required_begin": REQUIRED_BEGIN,
        "required_end": REQUIRED_END,
        "required_count": REQUIRED_COUNT,
        "positive_count": positive,
        "negative_count": REQUIRED_COUNT - positive,
        "all_signs_recomputed": True,
        "source_packet_sha256": packet.source_packet_sha256,
        "source_packet_bytes": packet.source_packet_bytes,
        "source_packet_rechecked": source_packet is not None,
        "interpolation_payload_available": True,
        "zero_isolation_events_constructed": False,
        "turing_event_stream_constructed": False,
        "global_zero_count_constructed": False,
        "lean_source_claim_ready": False,
    }


__all__ = [
    "PlattRequiredSignPacketError",
    "RequiredSample",
    "RequiredSignPacket",
    "inspect_required_sign_packet",
    "load_required_sign_packet",
]
