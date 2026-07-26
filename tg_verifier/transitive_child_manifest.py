# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Canonical TGCHLD01 child-DAG manifests for confidential CPU finalizers.

This module mirrors
``SparkInterval.Execution.TransitiveChildManifest`` byte for byte.  It checks
only topology, coverage, digest framing, and predecessor chaining.  Receipt
signature verification and independent arithmetic replay remain mandatory
separate finalizer phases.

The numeric coverage interval is campaign-defined.  R2Star uses its actual
source interval, while branched campaigns use a canonical flattened child
coordinate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import struct
from typing import Iterable, Sequence


MAGIC = b"TGCHLD01"
SCHEMA_VERSION = 1
HEADER = struct.Struct("<8sBBIQQ32s")
CHILD = struct.Struct("<IQQB32s32s32s32s")
ZERO_DIGEST = b"\x00" * 32


class ManifestError(ValueError):
    """A child manifest was malformed or differed from its exact spec."""


class Backend(IntEnum):
    AZURE_SEVSNP_CPU = 1
    AZURE_NCCADS_H100_V5 = 2


@dataclass(frozen=True)
class ChildEntry:
    ordinal: int
    lower: int
    upper: int
    backend: Backend
    receipt_digest: bytes
    artifact_digest: bytes
    result_digest: bytes
    predecessor_digest: bytes


@dataclass(frozen=True)
class Manifest:
    campaign_tag: int
    source_lower: int
    source_upper: int
    root_digest: bytes
    children: tuple[ChildEntry, ...]
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class Spec:
    campaign_tag: int
    source_lower: int
    source_upper: int
    root_digest: bytes
    expected_backends: tuple[Backend, ...]


def _uint(value: object, bits: int, what: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value >= 1 << bits
    ):
        raise ManifestError(f"{what} must be an unsigned {bits}-bit integer")
    return value


def _digest(value: object, what: str, *, nonzero: bool = True) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        raise ManifestError(f"{what} must be exactly 32 bytes")
    if nonzero and value == ZERO_DIGEST:
        raise ManifestError(f"{what} must be nonzero")
    return value


def _backend(value: object, what: str) -> Backend:
    if not isinstance(value, Backend):
        raise ManifestError(f"{what} must be a Backend")
    return value


def validate(manifest: Manifest, spec: Spec) -> Manifest:
    """Check exact topology, coverage, and the transitive digest chain."""

    _uint(spec.campaign_tag, 8, "spec campaign tag")
    _uint(spec.source_lower, 64, "spec source lower")
    _uint(spec.source_upper, 64, "spec source upper")
    root = _digest(spec.root_digest, "spec root digest")
    if spec.source_lower >= spec.source_upper:
        raise ManifestError("spec source range must be nonempty")
    expected_backends = tuple(
        _backend(value, f"spec backend {index}")
        for index, value in enumerate(spec.expected_backends)
    )

    if (
        manifest.schema_version != SCHEMA_VERSION
        or manifest.campaign_tag != spec.campaign_tag
        or manifest.source_lower != spec.source_lower
        or manifest.source_upper != spec.source_upper
        or manifest.root_digest != root
        or len(manifest.children) != len(expected_backends)
    ):
        raise ManifestError("manifest header or exact child count differs")

    predecessor = root
    next_lower = spec.source_lower
    checked: list[ChildEntry] = []
    for ordinal, (entry, expected_backend) in enumerate(
        zip(manifest.children, expected_backends, strict=True)
    ):
        _uint(entry.ordinal, 32, f"child {ordinal} ordinal")
        _uint(entry.lower, 64, f"child {ordinal} lower")
        _uint(entry.upper, 64, f"child {ordinal} upper")
        backend = _backend(entry.backend, f"child {ordinal} backend")
        receipt = _digest(
            entry.receipt_digest, f"child {ordinal} receipt digest"
        )
        artifact = _digest(
            entry.artifact_digest, f"child {ordinal} artifact digest"
        )
        result = _digest(
            entry.result_digest, f"child {ordinal} result digest"
        )
        previous = _digest(
            entry.predecessor_digest,
            f"child {ordinal} predecessor digest",
        )
        if (
            entry.ordinal != ordinal
            or entry.lower != next_lower
            or entry.lower >= entry.upper
            or backend is not expected_backend
            or previous != predecessor
        ):
            raise ManifestError(
                f"child {ordinal} breaks topology, coverage, or digest chain"
            )
        checked.append(
            ChildEntry(
                ordinal=ordinal,
                lower=entry.lower,
                upper=entry.upper,
                backend=backend,
                receipt_digest=receipt,
                artifact_digest=artifact,
                result_digest=result,
                predecessor_digest=previous,
            )
        )
        predecessor = receipt
        next_lower = entry.upper
    if next_lower != spec.source_upper:
        raise ManifestError("child ranges do not reach the exact source upper")
    return Manifest(
        schema_version=SCHEMA_VERSION,
        campaign_tag=spec.campaign_tag,
        source_lower=spec.source_lower,
        source_upper=spec.source_upper,
        root_digest=root,
        children=tuple(checked),
    )


def encode(manifest: Manifest) -> bytes:
    """Encode one manifest with canonical little-endian framing."""

    _uint(manifest.schema_version, 8, "schema version")
    _uint(manifest.campaign_tag, 8, "campaign tag")
    _uint(manifest.source_lower, 64, "source lower")
    _uint(manifest.source_upper, 64, "source upper")
    _uint(len(manifest.children), 32, "child count")
    root = _digest(manifest.root_digest, "root digest")
    pieces = [
        HEADER.pack(
            MAGIC,
            manifest.schema_version,
            manifest.campaign_tag,
            len(manifest.children),
            manifest.source_lower,
            manifest.source_upper,
            root,
        )
    ]
    for position, entry in enumerate(manifest.children):
        pieces.append(
            CHILD.pack(
                _uint(entry.ordinal, 32, f"child {position} ordinal"),
                _uint(entry.lower, 64, f"child {position} lower"),
                _uint(entry.upper, 64, f"child {position} upper"),
                int(_backend(entry.backend, f"child {position} backend")),
                _digest(
                    entry.receipt_digest,
                    f"child {position} receipt digest",
                ),
                _digest(
                    entry.artifact_digest,
                    f"child {position} artifact digest",
                ),
                _digest(
                    entry.result_digest,
                    f"child {position} result digest",
                ),
                _digest(
                    entry.predecessor_digest,
                    f"child {position} predecessor digest",
                ),
            )
        )
    return b"".join(pieces)


def decode(raw: bytes) -> Manifest:
    """Decode one exact frame, rejecting truncation and trailing bytes."""

    if not isinstance(raw, bytes) or len(raw) < HEADER.size:
        raise ManifestError("manifest is shorter than its fixed header")
    (
        magic,
        schema_version,
        campaign_tag,
        child_count,
        source_lower,
        source_upper,
        root_digest,
    ) = HEADER.unpack_from(raw)
    expected_size = HEADER.size + child_count * CHILD.size
    if magic != MAGIC or len(raw) != expected_size:
        raise ManifestError("manifest magic, child count, or exact size differs")
    children: list[ChildEntry] = []
    offset = HEADER.size
    for position in range(child_count):
        (
            ordinal,
            lower,
            upper,
            backend_tag,
            receipt_digest,
            artifact_digest,
            result_digest,
            predecessor_digest,
        ) = CHILD.unpack_from(raw, offset)
        try:
            backend = Backend(backend_tag)
        except ValueError as error:
            raise ManifestError(
                f"child {position} has an unknown backend tag"
            ) from error
        children.append(
            ChildEntry(
                ordinal=ordinal,
                lower=lower,
                upper=upper,
                backend=backend,
                receipt_digest=receipt_digest,
                artifact_digest=artifact_digest,
                result_digest=result_digest,
                predecessor_digest=predecessor_digest,
            )
        )
        offset += CHILD.size
    return Manifest(
        schema_version=schema_version,
        campaign_tag=campaign_tag,
        source_lower=source_lower,
        source_upper=source_upper,
        root_digest=root_digest,
        children=tuple(children),
    )


def root_digest(tag: int) -> bytes:
    """The exact source-level domain root used by the current three specs."""

    return bytes([_uint(tag, 8, "root tag")]) * 32


R2STAR_SPEC = Spec(
    campaign_tag=1,
    source_lower=1,
    source_upper=21_000_000_001,
    root_digest=root_digest(1),
    expected_backends=(Backend.AZURE_NCCADS_H100_V5,),
)

HISTORICAL_GOLDBACH_SPEC = Spec(
    campaign_tag=2,
    source_lower=0,
    source_upper=8_512,
    root_digest=root_digest(2),
    expected_backends=(
        *((Backend.AZURE_NCCADS_H100_V5,) * 8_192),
        *((Backend.AZURE_SEVSNP_CPU,) * 320),
    ),
)

PLATT_DIRICHLET_SPEC = Spec(
    campaign_tag=3,
    source_lower=0,
    source_upper=2,
    root_digest=root_digest(3),
    expected_backends=(
        Backend.AZURE_SEVSNP_CPU,
        Backend.AZURE_SEVSNP_CPU,
    ),
)


__all__ = [
    "Backend",
    "CHILD",
    "ChildEntry",
    "HEADER",
    "HISTORICAL_GOLDBACH_SPEC",
    "MAGIC",
    "Manifest",
    "ManifestError",
    "PLATT_DIRICHLET_SPEC",
    "R2STAR_SPEC",
    "SCHEMA_VERSION",
    "Spec",
    "decode",
    "encode",
    "root_digest",
    "validate",
]
