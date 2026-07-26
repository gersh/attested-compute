# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Canonical binary artifact consumed by the closed Lean CDEM finalizer.

The format is intentionally small and fixed-width.  It mirrors
``CDEMAbelArtifactProgram.lean`` byte for byte; this module is a producer and
cross-language audit aid, while the ordinary Lean parser/checker theorem is
the proof boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import NoReturn

from .cdem_chunk_replay import CDEM_PRODUCTION_N, CdemChunkRecord
from .cdem_recurrence_certificate import (
    CdemRecurrenceCertificate,
    certificate_from_production_transcript,
)
from .evidence import CDEM_U_TARGET, CDEM_V_TARGET


INVOCATION_ID = "cdem-table-abel-production-v2"
CANONICAL_JOB = (
    '{"K":199330,"N":5000000000,'
    '"weight_scale":1000000000000000000}'
)
ARTIFACT_HEADER = (
    "TG-CDEM-ABEL-ARTIFACT-V1\n"
    f"invocation={INVOCATION_ID}\n"
    "terminal=azure-sev-snp-cpu\n"
    f"job={CANONICAL_JOB}\n"
).encode("ascii")
NATURAL_BYTES = 32
INTEGER_BYTES = 33
FIXED_BYTES = NATURAL_BYTES * 2 + 4
CHUNK_BYTES = (
    NATURAL_BYTES * 3 + INTEGER_BYTES * 3
)
MAXIMUM_CHUNKS = 100_000


class CdemAbelArtifactError(RuntimeError):
    """The canonical CDEM artifact is malformed or inconsistent."""


def _fail(message: str) -> NoReturn:
    raise CdemAbelArtifactError(message)


def _natural(value: int, label: str, *, width: int = NATURAL_BYTES) -> bytes:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value >= 1 << (8 * width)
    ):
        _fail(f"{label} does not fit the canonical unsigned field")
    return value.to_bytes(width, "little")


def _integer(value: int, label: str) -> bytes:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{label} is not an integer")
    magnitude = abs(value)
    if magnitude >= 1 << (8 * NATURAL_BYTES):
        _fail(f"{label} magnitude does not fit the canonical signed field")
    return bytes((1 if value < 0 else 0,)) + _natural(
        magnitude, f"{label} magnitude"
    )


def _read_natural(raw: bytes, offset: int, label: str, *, width: int = NATURAL_BYTES) -> int:
    end = offset + width
    if offset < 0 or end > len(raw):
        _fail(f"{label} is truncated")
    return int.from_bytes(raw[offset:end], "little")


def _read_integer(raw: bytes, offset: int, label: str) -> int:
    if offset < 0 or offset + INTEGER_BYTES > len(raw):
        _fail(f"{label} is truncated")
    sign = raw[offset]
    magnitude = _read_natural(raw, offset + 1, f"{label} magnitude")
    if sign == 0:
        return magnitude
    if sign == 1 and magnitude != 0:
        return -magnitude
    _fail(f"{label} has an invalid sign or negative zero")


@dataclass(frozen=True)
class CdemAbelWireCertificate:
    signed_numerator: int
    absolute_numerator: int
    chunks: tuple[CdemChunkRecord, ...]


def encode_certificate(certificate: CdemRecurrenceCertificate) -> bytes:
    """Encode one already validated production recurrence certificate."""

    chunks = certificate.chunks
    if len(chunks) > MAXIMUM_CHUNKS:
        _fail("chunk count exceeds the fixed parser cap")
    payload = bytearray(ARTIFACT_HEADER)
    payload.extend(_natural(certificate.signed_numerator, "signed numerator"))
    payload.extend(_natural(certificate.absolute_numerator, "absolute numerator"))
    payload.extend(_natural(len(chunks), "chunk count", width=4))
    for index, chunk in enumerate(chunks):
        payload.extend(_natural(chunk.low, f"chunk {index} low"))
        payload.extend(_natural(chunk.high, f"chunk {index} high"))
        payload.extend(_integer(chunk.before, f"chunk {index} before"))
        payload.extend(_integer(chunk.after, f"chunk {index} after"))
        payload.extend(
            _integer(chunk.u_increment_upper, f"chunk {index} signed upper")
        )
        payload.extend(
            _natural(chunk.v_increment_upper, f"chunk {index} absolute upper")
        )
    return bytes(payload)


def artifact_from_production_transcript(transcript: bytes | str) -> bytes:
    """Validate the exact production transcript and encode its Lean artifact."""

    return encode_certificate(certificate_from_production_transcript(transcript))


def decode_artifact(raw: bytes) -> CdemAbelWireCertificate:
    """Strictly decode the same frame accepted by the Lean parser."""

    if not isinstance(raw, bytes):
        _fail("artifact must be a byte string")
    if not raw.startswith(ARTIFACT_HEADER):
        _fail("artifact header differs")
    offset = len(ARTIFACT_HEADER)
    signed = _read_natural(raw, offset, "signed numerator")
    absolute = _read_natural(raw, offset + NATURAL_BYTES, "absolute numerator")
    count = _read_natural(
        raw, offset + NATURAL_BYTES * 2, "chunk count", width=4
    )
    if count > MAXIMUM_CHUNKS:
        _fail("chunk count exceeds the fixed parser cap")
    expected = offset + FIXED_BYTES + count * CHUNK_BYTES
    if len(raw) != expected:
        _fail("artifact frame length differs")
    cursor = offset + FIXED_BYTES
    chunks: list[CdemChunkRecord] = []
    for index in range(count):
        low = _read_natural(raw, cursor, f"chunk {index} low")
        cursor += NATURAL_BYTES
        high = _read_natural(raw, cursor, f"chunk {index} high")
        cursor += NATURAL_BYTES
        before = _read_integer(raw, cursor, f"chunk {index} before")
        cursor += INTEGER_BYTES
        after = _read_integer(raw, cursor, f"chunk {index} after")
        cursor += INTEGER_BYTES
        signed_upper = _read_integer(raw, cursor, f"chunk {index} signed upper")
        cursor += INTEGER_BYTES
        absolute_upper = _read_natural(raw, cursor, f"chunk {index} absolute upper")
        cursor += NATURAL_BYTES
        chunks.append(
            CdemChunkRecord(
                low=low,
                high=high,
                before=before,
                after=after,
                u_increment_upper=signed_upper,
                v_increment_upper=absolute_upper,
                # The Lean artifact intentionally omits this diagnostic-only
                # producer field.
                variation=0,
            )
        )
    return CdemAbelWireCertificate(signed, absolute, tuple(chunks))


def validate_production_artifact(raw: bytes) -> CdemAbelWireCertificate:
    """Check the fixed targets and complete production chunk topology."""

    certificate = decode_artifact(raw)
    if certificate.signed_numerator != CDEM_U_TARGET:
        _fail("signed target differs")
    if certificate.absolute_numerator != CDEM_V_TARGET:
        _fail("absolute target differs")
    if len(certificate.chunks) != 1_000:
        _fail("production artifact must contain exactly 1,000 chunks")
    next_low = 1
    next_before = 0
    signed_total = 0
    absolute_total = 0
    for index, chunk in enumerate(certificate.chunks):
        if chunk.low != next_low or chunk.high < chunk.low:
            _fail(f"chunk {index} range is not gap-free")
        if chunk.before != next_before:
            _fail(f"chunk {index} state is discontinuous")
        if chunk.v_increment_upper < 0:
            _fail(f"chunk {index} absolute upper is negative")
        next_low = chunk.high + 1
        next_before = chunk.after
        signed_total += chunk.u_increment_upper
        absolute_total += chunk.v_increment_upper
    if next_low != CDEM_PRODUCTION_N + 1:
        _fail("chunk chain does not cover the complete production endpoint")
    if signed_total > certificate.signed_numerator:
        _fail("signed chunk reduction exceeds the target")
    if absolute_total > certificate.absolute_numerator:
        _fail("absolute chunk reduction exceeds the target")
    return certificate


def write_artifact_exclusive(
    transcript: bytes | str,
    output: Path,
) -> dict[str, int | str]:
    """Write a fresh canonical artifact; never replace an existing file."""

    payload = artifact_from_production_transcript(transcript)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream:
            stream.write(payload)
    except FileExistsError as error:
        raise CdemAbelArtifactError(
            f"refusing to overwrite an existing CDEM artifact: {output}"
        ) from error
    output.chmod(0o400)
    import hashlib

    return {
        "path": str(output.resolve()),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


__all__ = [
    "ARTIFACT_HEADER",
    "CANONICAL_JOB",
    "CHUNK_BYTES",
    "CdemAbelArtifactError",
    "CdemAbelWireCertificate",
    "artifact_from_production_transcript",
    "decode_artifact",
    "encode_certificate",
    "validate_production_artifact",
    "write_artifact_exclusive",
]
