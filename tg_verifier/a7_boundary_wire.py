# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Compact, transcript-shaped wire for the finite CH25 A.7 leaf replay.

The retained JSON artifact uses base64url only to transport positive integer
mantissas.  ``TGA7WIR1`` keeps the same seven semantic fields per leaf in a
fixed-width binary record:

``edge_id, depth, index, norm_mantissa, norm_exponent,
zeta_mantissa, zeta_exponent``.

The encoder accepts bytes only after the authoritative JSON validator in
``tg_verifier.analytic`` has accepted them.  The decoder below is deliberately
independent of that JSON parser: it rechecks framing, hashes, exact dyadic
arithmetic, and four gap-free edge covers directly from the binary bytes.

This module proves no analytic enclosure fact.  In particular, neither this
wire nor its Lean counterpart identifies a FLINT/Arb value with Mathlib's
zeta, derivative, or regularized logarithmic derivative.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import struct
from typing import NoReturn

from .a7_lean_certificate import (
    A7LeanCertificate,
    A7LeanLeaf,
    certificate_from_transcript_bytes,
    validate_certificate,
)


WIRE_MAGIC = b"TGA7WIR1"
WIRE_VERSION = 1
WIRE_HEADER_BYTES = 144
WIRE_RECORD_BYTES = 88
WIRE_MAX_LEAVES = 2_000_000
WIRE_MAX_DEPTH = 64
WIRE_MAX_TRANSCRIPT_BYTES = 64 * 1024 * 1024
WIRE_MANTISSA_BYTES = 32
WIRE_MAX_ABS_EXPONENT = 16_384

_HEADER = struct.Struct("<8sIIIIIIQ32s32s32sQ")
_RECORD_PREFIX = struct.Struct("<IIQ")
_SIGNED_I32 = struct.Struct("<i")
_TARGET_SQ = Fraction(121_801, 62_500)

# Exact identity of the retained source JSON.  The binary payload/full-wire
# pins are filled from the deterministic encoder and are checked by both the
# Python and Lean retained-identity entry points.
RETAINED_TRANSCRIPT_SHA256 = (
    "ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29"
)
RETAINED_TRANSCRIPT_SIZE_BYTES = 1_494_999
RETAINED_LEAF_COUNT = 16_191
RETAINED_MAX_DEPTH = 24
RETAINED_LEAVES_SHA256 = (
    "abac27f61cb8ce53f649cb0c2111c123c761a37793a1bc536033981c215cabef"
)
# These two constants are deterministic consequences of the five values
# above and the seven-field record encoding.  Keep them synchronized with the
# same named constants in ``A7BoundaryWire.lean``.
RETAINED_PAYLOAD_SHA256 = (
    "f2893e9488df7353c31f7d647948b697eb2c88f331b7ea4405c9e328f974148c"
)
RETAINED_WIRE_SHA256 = (
    "1ea01e78e29143ecfef926faac7b788c2d4dc9dd6240b7d0b401e7f62fa9de4c"
)


class A7BoundaryWireError(ValueError):
    """A compact A.7 wire failed a finite, fail-closed check."""


def _fail(message: str) -> NoReturn:
    raise A7BoundaryWireError(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest_bytes(value: str, *, label: str) -> bytes:
    if len(value) != 64:
        _fail(f"{label} must be lowercase SHA-256 hex")
    try:
        raw = bytes.fromhex(value)
    except ValueError as error:
        raise A7BoundaryWireError(
            f"{label} must be lowercase SHA-256 hex"
        ) from error
    if value != raw.hex():
        _fail(f"{label} must be lowercase SHA-256 hex")
    return raw


def _mantissa_bytes(value: int, *, label: str) -> bytes:
    if type(value) is not int or not 0 < value < 1 << 256:
        _fail(f"{label} must be a positive integer of at most 256 bits")
    return value.to_bytes(WIRE_MANTISSA_BYTES, "big")


def _encode_leaf(leaf: A7LeanLeaf, *, position: int) -> bytes:
    label = f"leaves[{position}]"
    if not 0 <= leaf.edge_id < 4:
        _fail(f"{label}.edge_id is outside [0,4)")
    if not 0 <= leaf.depth <= WIRE_MAX_DEPTH:
        _fail(f"{label}.depth is outside the compact wire range")
    if not 0 <= leaf.index < 1 << 64:
        _fail(f"{label}.index does not fit the compact wire")
    for name, exponent in (
        ("norm_sq_upper", leaf.norm_sq_upper.exponent),
        ("zeta_abs_lower", leaf.zeta_abs_lower.exponent),
    ):
        if (
            type(exponent) is not int
            or not -WIRE_MAX_ABS_EXPONENT
            <= exponent
            <= WIRE_MAX_ABS_EXPONENT
        ):
            _fail(f"{label}.{name}.exponent is outside the bounded range")
    return b"".join(
        (
            _RECORD_PREFIX.pack(leaf.edge_id, leaf.depth, leaf.index),
            _mantissa_bytes(
                leaf.norm_sq_upper.mantissa,
                label=f"{label}.norm_sq_upper.mantissa",
            ),
            _SIGNED_I32.pack(leaf.norm_sq_upper.exponent),
            _mantissa_bytes(
                leaf.zeta_abs_lower.mantissa,
                label=f"{label}.zeta_abs_lower.mantissa",
            ),
            _SIGNED_I32.pack(leaf.zeta_abs_lower.exponent),
        )
    )


def encode_a7_boundary_wire(certificate: A7LeanCertificate) -> bytes:
    """Encode one already-authoritatively-validated seven-field certificate."""

    certificate = validate_certificate(certificate)
    if not 4 <= len(certificate.leaves) <= WIRE_MAX_LEAVES:
        _fail("leaf count is outside the compact wire range")
    if not 0 <= certificate.max_depth <= WIRE_MAX_DEPTH:
        _fail("max_depth is outside the compact wire range")
    if not 0 < certificate.transcript_size_bytes <= WIRE_MAX_TRANSCRIPT_BYTES:
        _fail("transcript_size_bytes is outside the compact wire range")
    payload = b"".join(
        _encode_leaf(leaf, position=position)
        for position, leaf in enumerate(certificate.leaves)
    )
    payload_sha256 = hashlib.sha256(payload).digest()
    header = _HEADER.pack(
        WIRE_MAGIC,
        WIRE_VERSION,
        WIRE_HEADER_BYTES,
        WIRE_RECORD_BYTES,
        0,
        certificate.max_depth,
        len(certificate.leaves),
        certificate.transcript_size_bytes,
        _digest_bytes(
            certificate.transcript_sha256, label="transcript_sha256"
        ),
        _digest_bytes(certificate.leaves_sha256, label="leaves_sha256"),
        payload_sha256,
        0,
    )
    if len(header) != WIRE_HEADER_BYTES:
        raise AssertionError("internal A.7 header layout mismatch")
    return header + payload


def wire_from_transcript_bytes(
    raw: bytes, *, require_retained_identity: bool = True
) -> bytes:
    """Authoritatively validate immutable JSON bytes, then encode the wire."""

    certificate = certificate_from_transcript_bytes(
        raw, require_retained_identity=require_retained_identity
    )
    wire = encode_a7_boundary_wire(certificate)
    # Decode through the independent binary path before returning producer
    # output.  For a retained input this also enforces the exact binary pins.
    decode_a7_boundary_wire(
        wire, require_retained_identity=require_retained_identity
    )
    return wire


@dataclass(frozen=True)
class A7WireLeaf:
    edge_id: int
    depth: int
    index: int
    norm_sq_upper_mantissa: int
    norm_sq_upper_exponent: int
    zeta_abs_lower_mantissa: int
    zeta_abs_lower_exponent: int

    @property
    def lower(self) -> Fraction:
        return Fraction(self.index, 1 << self.depth)

    @property
    def upper(self) -> Fraction:
        return Fraction(self.index + 1, 1 << self.depth)

    @staticmethod
    def _dyadic(mantissa: int, exponent: int) -> Fraction:
        if exponent >= 0:
            return Fraction(mantissa << exponent)
        return Fraction(mantissa, 1 << -exponent)

    @property
    def norm_sq_upper(self) -> Fraction:
        return self._dyadic(
            self.norm_sq_upper_mantissa, self.norm_sq_upper_exponent
        )

    @property
    def zeta_abs_lower(self) -> Fraction:
        return self._dyadic(
            self.zeta_abs_lower_mantissa, self.zeta_abs_lower_exponent
        )


@dataclass(frozen=True)
class A7BoundaryWire:
    max_depth: int
    transcript_size_bytes: int
    transcript_sha256: str
    leaves_sha256: str
    payload_sha256: str
    wire_sha256: str
    leaves: tuple[A7WireLeaf, ...]


def _decode_leaf(raw: bytes, *, offset: int, position: int) -> A7WireLeaf:
    label = f"records[{position}]"
    edge_id, depth, index = _RECORD_PREFIX.unpack_from(raw, offset)
    norm_offset = offset + _RECORD_PREFIX.size
    norm_mantissa = int.from_bytes(
        raw[norm_offset : norm_offset + WIRE_MANTISSA_BYTES], "big"
    )
    norm_exponent = _SIGNED_I32.unpack_from(
        raw, norm_offset + WIRE_MANTISSA_BYTES
    )[0]
    zeta_offset = norm_offset + WIRE_MANTISSA_BYTES + _SIGNED_I32.size
    zeta_mantissa = int.from_bytes(
        raw[zeta_offset : zeta_offset + WIRE_MANTISSA_BYTES], "big"
    )
    zeta_exponent = _SIGNED_I32.unpack_from(
        raw, zeta_offset + WIRE_MANTISSA_BYTES
    )[0]
    leaf = A7WireLeaf(
        edge_id,
        depth,
        index,
        norm_mantissa,
        norm_exponent,
        zeta_mantissa,
        zeta_exponent,
    )
    if not 0 <= leaf.edge_id < 4:
        _fail(f"{label}.edge_id is outside [0,4)")
    if not 0 <= leaf.depth <= WIRE_MAX_DEPTH:
        _fail(f"{label}.depth is outside the compact wire range")
    if leaf.index >= 1 << leaf.depth:
        _fail(f"{label}.index is outside its dyadic depth")
    if leaf.norm_sq_upper_mantissa <= 0:
        _fail(f"{label}.norm_sq_upper mantissa is not positive")
    if leaf.zeta_abs_lower_mantissa <= 0:
        _fail(f"{label}.zeta_abs_lower mantissa is not positive")
    if not (
        -WIRE_MAX_ABS_EXPONENT
        <= leaf.norm_sq_upper_exponent
        <= WIRE_MAX_ABS_EXPONENT
    ):
        _fail(f"{label}.norm_sq_upper exponent is outside the bounded range")
    if not (
        -WIRE_MAX_ABS_EXPONENT
        <= leaf.zeta_abs_lower_exponent
        <= WIRE_MAX_ABS_EXPONENT
    ):
        _fail(f"{label}.zeta_abs_lower exponent is outside the bounded range")
    if not Fraction(0) < leaf.norm_sq_upper < _TARGET_SQ:
        _fail(f"{label}.norm_sq_upper fails the strict source bound")
    if leaf.zeta_abs_lower <= 0:
        _fail(f"{label}.zeta_abs_lower is not positive")
    return leaf


def _check_cover(leaves: tuple[A7WireLeaf, ...]) -> None:
    keys = [(leaf.edge_id, leaf.lower, leaf.upper) for leaf in leaves]
    if keys != sorted(keys):
        _fail("records are not in canonical edge/coordinate order")
    for edge_id in range(4):
        cursor = Fraction(0)
        found = False
        for current_edge, lower, upper in keys:
            if current_edge != edge_id:
                continue
            found = True
            if lower != cursor:
                relation = "overlap" if lower < cursor else "gap"
                _fail(f"edge {edge_id} has a dyadic {relation} at {cursor}")
            cursor = upper
        if not found or cursor != 1:
            _fail(f"edge {edge_id} is not completely covered")


def decode_a7_boundary_wire(
    raw: bytes, *, require_retained_identity: bool = False
) -> A7BoundaryWire:
    """Independently decode and check all finite binary-wire obligations."""

    if type(raw) is not bytes:
        _fail("wire must be immutable bytes")
    if len(raw) < WIRE_HEADER_BYTES:
        _fail("wire is truncated before the fixed header")
    (
        magic,
        version,
        header_bytes,
        record_bytes,
        reserved,
        max_depth,
        leaf_count,
        transcript_size,
        transcript_sha256_raw,
        leaves_sha256_raw,
        payload_sha256_raw,
        reserved_tail,
    ) = _HEADER.unpack_from(raw)
    if magic != WIRE_MAGIC:
        _fail("wire magic mismatch")
    if version != WIRE_VERSION:
        _fail("wire version mismatch")
    if header_bytes != WIRE_HEADER_BYTES or record_bytes != WIRE_RECORD_BYTES:
        _fail("wire layout widths mismatch")
    if reserved != 0 or reserved_tail != 0:
        _fail("wire reserved fields must be zero")
    if not 0 <= max_depth <= WIRE_MAX_DEPTH:
        _fail("wire max_depth is outside the accepted range")
    if not 4 <= leaf_count <= WIRE_MAX_LEAVES:
        _fail("wire leaf_count is outside the accepted range")
    if not 0 < transcript_size <= WIRE_MAX_TRANSCRIPT_BYTES:
        _fail("wire transcript_size is outside the accepted range")
    expected_size = WIRE_HEADER_BYTES + leaf_count * WIRE_RECORD_BYTES
    if len(raw) != expected_size:
        _fail("wire length does not exactly match leaf_count")

    payload = raw[WIRE_HEADER_BYTES:]
    payload_sha256 = _sha256(payload)
    if payload_sha256 != payload_sha256_raw.hex():
        _fail("wire payload SHA-256 mismatch")

    leaves = tuple(
        _decode_leaf(
            raw,
            offset=WIRE_HEADER_BYTES + position * WIRE_RECORD_BYTES,
            position=position,
        )
        for position in range(leaf_count)
    )
    if any(leaf.depth > max_depth for leaf in leaves):
        _fail("a wire leaf depth exceeds max_depth")
    _check_cover(leaves)

    artifact = A7BoundaryWire(
        max_depth=max_depth,
        transcript_size_bytes=transcript_size,
        transcript_sha256=transcript_sha256_raw.hex(),
        leaves_sha256=leaves_sha256_raw.hex(),
        payload_sha256=payload_sha256,
        wire_sha256=_sha256(raw),
        leaves=leaves,
    )
    if require_retained_identity:
        expected = (
            (artifact.max_depth, RETAINED_MAX_DEPTH, "max_depth"),
            (len(artifact.leaves), RETAINED_LEAF_COUNT, "leaf_count"),
            (
                artifact.transcript_size_bytes,
                RETAINED_TRANSCRIPT_SIZE_BYTES,
                "transcript_size_bytes",
            ),
            (
                artifact.transcript_sha256,
                RETAINED_TRANSCRIPT_SHA256,
                "transcript_sha256",
            ),
            (
                artifact.leaves_sha256,
                RETAINED_LEAVES_SHA256,
                "leaves_sha256",
            ),
            (
                artifact.payload_sha256,
                RETAINED_PAYLOAD_SHA256,
                "payload_sha256",
            ),
            (artifact.wire_sha256, RETAINED_WIRE_SHA256, "wire_sha256"),
        )
        for observed, wanted, label in expected:
            if observed != wanted:
                _fail(f"retained {label} mismatch")
    return artifact


__all__ = [
    "A7BoundaryWire",
    "A7BoundaryWireError",
    "A7WireLeaf",
    "RETAINED_LEAF_COUNT",
    "RETAINED_LEAVES_SHA256",
    "RETAINED_MAX_DEPTH",
    "RETAINED_PAYLOAD_SHA256",
    "RETAINED_TRANSCRIPT_SHA256",
    "RETAINED_TRANSCRIPT_SIZE_BYTES",
    "RETAINED_WIRE_SHA256",
    "WIRE_HEADER_BYTES",
    "WIRE_MAGIC",
    "WIRE_MAX_ABS_EXPONENT",
    "WIRE_MAX_DEPTH",
    "WIRE_MAX_LEAVES",
    "WIRE_RECORD_BYTES",
    "WIRE_VERSION",
    "decode_a7_boundary_wire",
    "encode_a7_boundary_wire",
    "wire_from_transcript_bytes",
]
