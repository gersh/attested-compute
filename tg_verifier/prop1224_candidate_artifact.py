# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact Python codec for ``Prop1224CandidateArtifact.lean``.

The wire carries only the gap-free arithmetic shard chain.  It deliberately
does not carry the directed MPFR/GMP row realizations needed by
``Prop1224SourceSemantics.SourceRowClaim``.  Consequently an artifact produced
here is useful for cross-language format and coverage audit, but is not a
successful Lean source certificate.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from .affine_guard_certificate import FixedShardPlan
from .campaign_io import canonical_json_bytes


INVOCATION_ID = "helfgott-prop-12-2-4-production-v1"
TERMINAL = "azure-sev-snp-cpu"
JOB_BYTES = (
    b'{"campaign":"helfgott-prop-12-2-4-mpfr-v1",'
    b'"rank_lower":0,"rank_upper":3389047618}'
)
ARTIFACT_HEADER = (
    b"TG-PROP1224-CANDIDATE-V1\n"
    + b"invocation="
    + INVOCATION_ID.encode("ascii")
    + b"\nterminal="
    + TERMINAL.encode("ascii")
    + b"\njob="
    + JOB_BYTES
    + b"\n"
)
NATURAL_WIDTH = 32
COUNT_WIDTH = 4
MAXIMUM_SHARD_COUNT = 1_000_000
NATURAL_LIMIT = 1 << (8 * NATURAL_WIDTH)
COUNT_LIMIT = 1 << (8 * COUNT_WIDTH)
SOURCE_LOWER = 0
SOURCE_UPPER = 3_389_047_618
SHARD_BYTE_SIZE = 2 * NATURAL_WIDTH
FIXED_BYTE_SIZE = 2 * NATURAL_WIDTH + COUNT_WIDTH
MANIFEST_KIND = "sparkinterval.tg.prop1224-candidate-artifact-manifest.v1"
SEMANTIC_STATUS = "arithmetic-chain-only-missing-mpfr-gmp-row-realization"
MISSING_REALIZATION_FIELDS = (
    "per-rank factorization and Euler-totient realization",
    "outward MPFR log/exp/real-power intervals including Euler gamma and c_E",
    "exact directed GMP G_q accumulator values",
    "conservative integer-window endpoint decisions",
    "ordinary Lean row-soundness proof from those data-only records",
)


class Prop1224CandidateArtifactError(ValueError):
    """The candidate artifact or replay report is not the exact V1 format."""


def _plain_nat(value: object, what: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value >= NATURAL_LIMIT
    ):
        raise Prop1224CandidateArtifactError(
            f"{what} must be an unsigned 256-bit integer"
        )
    return value


def _nat_bytes(value: object, what: str) -> bytes:
    return _plain_nat(value, what).to_bytes(NATURAL_WIDTH, "little")


def _read_nat(raw: bytes, offset: int, what: str) -> int:
    end = offset + NATURAL_WIDTH
    if end > len(raw):
        raise Prop1224CandidateArtifactError(f"truncated {what}")
    return int.from_bytes(raw[offset:end], "little")


@dataclass(frozen=True)
class Prop1224CandidateShard:
    lower: int
    upper: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "lower", _plain_nat(self.lower, "shard lower"))
        object.__setattr__(self, "upper", _plain_nat(self.upper, "shard upper"))


@dataclass(frozen=True)
class Prop1224CandidateCertificate:
    source_lower: int
    source_upper: int
    shards: tuple[Prop1224CandidateShard, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_lower", _plain_nat(self.source_lower, "source lower")
        )
        object.__setattr__(
            self, "source_upper", _plain_nat(self.source_upper, "source upper")
        )
        if isinstance(self.shards, (str, bytes)) or not isinstance(
            self.shards, Sequence
        ):
            raise Prop1224CandidateArtifactError("shards must be an ordered sequence")
        shards = tuple(self.shards)
        if any(not isinstance(shard, Prop1224CandidateShard) for shard in shards):
            raise Prop1224CandidateArtifactError(
                "every shard must be a Prop1224CandidateShard"
            )
        if len(shards) > MAXIMUM_SHARD_COUNT or len(shards) >= COUNT_LIMIT:
            raise Prop1224CandidateArtifactError("candidate has too many shards")
        object.__setattr__(self, "shards", shards)


def encode_candidate(certificate: Prop1224CandidateCertificate) -> bytes:
    """Return the unique byte spelling accepted by the Lean V1 decoder."""

    if not isinstance(certificate, Prop1224CandidateCertificate):
        raise Prop1224CandidateArtifactError(
            "certificate must be a Prop1224CandidateCertificate"
        )
    body = bytearray(ARTIFACT_HEADER)
    body.extend(_nat_bytes(certificate.source_lower, "source lower"))
    body.extend(_nat_bytes(certificate.source_upper, "source upper"))
    body.extend(len(certificate.shards).to_bytes(COUNT_WIDTH, "little"))
    for index, shard in enumerate(certificate.shards):
        body.extend(_nat_bytes(shard.lower, f"shards[{index}].lower"))
        body.extend(_nat_bytes(shard.upper, f"shards[{index}].upper"))
    return bytes(body)


def decode_candidate(raw: bytes) -> Prop1224CandidateCertificate:
    """Strictly decode one exact frame; suffixes and alternate headers fail."""

    if not isinstance(raw, bytes):
        raise Prop1224CandidateArtifactError("candidate artifact must be bytes")
    if not raw.startswith(ARTIFACT_HEADER):
        raise Prop1224CandidateArtifactError("candidate artifact header differs")
    offset = len(ARTIFACT_HEADER)
    minimum = offset + FIXED_BYTE_SIZE
    if len(raw) < minimum:
        raise Prop1224CandidateArtifactError("candidate artifact is truncated")
    source_lower = _read_nat(raw, offset, "source lower")
    source_upper = _read_nat(raw, offset + NATURAL_WIDTH, "source upper")
    count_offset = offset + 2 * NATURAL_WIDTH
    shard_count = int.from_bytes(raw[count_offset : count_offset + COUNT_WIDTH], "little")
    if shard_count > MAXIMUM_SHARD_COUNT:
        raise Prop1224CandidateArtifactError("candidate shard count exceeds V1 limit")
    expected_size = minimum + shard_count * SHARD_BYTE_SIZE
    if len(raw) != expected_size:
        raise Prop1224CandidateArtifactError(
            "candidate frame length does not match its shard count"
        )
    cursor = minimum
    shards: list[Prop1224CandidateShard] = []
    for index in range(shard_count):
        shards.append(
            Prop1224CandidateShard(
                _read_nat(raw, cursor, f"shards[{index}].lower"),
                _read_nat(
                    raw, cursor + NATURAL_WIDTH, f"shards[{index}].upper"
                ),
            )
        )
        cursor += SHARD_BYTE_SIZE
    return Prop1224CandidateCertificate(source_lower, source_upper, tuple(shards))


def arithmetic_check(certificate: Prop1224CandidateCertificate) -> bool:
    """Mirror ``Prop1224CandidateArtifact.arithmeticCheck`` exactly."""

    if not isinstance(certificate, Prop1224CandidateCertificate):
        return False
    if certificate.source_lower >= certificate.source_upper:
        return False
    expected = certificate.source_lower
    for shard in certificate.shards:
        if shard.lower != expected or shard.lower >= shard.upper:
            return False
        expected = shard.upper
    return (
        expected == certificate.source_upper
        and certificate.source_lower == SOURCE_LOWER
        and certificate.source_upper == SOURCE_UPPER
    )


def candidate_from_verified_report(
    report: Mapping[str, Any], *, plan: FixedShardPlan
) -> Prop1224CandidateCertificate:
    """Convert the terminal merge result after its independent receipt replay.

    The report is intentionally required to contain the exact fixed-plan
    verification summary.  This conversion does not infer any MPFR/GMP row
    theorem from hashes or minimum margins.
    """

    if not isinstance(report, Mapping):
        raise Prop1224CandidateArtifactError("verified report must be an object")
    required = {
        "all_fixed_plan_receipts_present": True,
        "kind": "sparkinterval.azure.prop1224-full-merge-report.v1",
        "schema_version": 1,
        "plan_sha256": plan.plan_sha256,
        "root_state": [SOURCE_LOWER],
        "final_state": [SOURCE_UPPER],
        "leaf_count": len(plan.shards),
    }
    for name, expected in required.items():
        if report.get(name) != expected:
            raise Prop1224CandidateArtifactError(
                f"verified report field {name!r} differs"
            )
    if (
        plan.domain_lower != SOURCE_LOWER
        or plan.domain_upper != SOURCE_UPPER
        or plan.state_dimension != 1
    ):
        raise Prop1224CandidateArtifactError(
            "verified plan is not the literal Proposition 12.2.4 source plan"
        )
    certificate = Prop1224CandidateCertificate(
        plan.domain_lower,
        plan.domain_upper,
        tuple(
            Prop1224CandidateShard(shard.lower, shard.upper)
            for shard in plan.shards
        ),
    )
    if not arithmetic_check(certificate):
        raise Prop1224CandidateArtifactError(
            "verified plan did not produce a valid Lean arithmetic candidate"
        )
    return certificate


def candidate_manifest(relative_path: str, raw: bytes) -> dict[str, Any]:
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or relative_path.startswith("/")
        or ".." in Path(relative_path).parts
    ):
        raise Prop1224CandidateArtifactError(
            "candidate manifest path must be safe and relative"
        )
    certificate = decode_candidate(raw)
    if not arithmetic_check(certificate):
        raise Prop1224CandidateArtifactError(
            "manifest refuses an arithmetically invalid candidate"
        )
    return {
        "artifact": {
            "path": relative_path,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        },
        "kind": MANIFEST_KIND,
        "lean_decoder": (
            "SparkInterval.TernaryGoldbach.Prop1224CandidateArtifact.decode"
        ),
        "missing_realization_fields": list(MISSING_REALIZATION_FIELDS),
        "schema_version": 1,
        "semantic_closure": False,
        "status": SEMANTIC_STATUS,
    }


def manifest_bytes(relative_path: str, raw: bytes) -> bytes:
    return canonical_json_bytes(candidate_manifest(relative_path, raw))


def require_semantic_realization(_raw: bytes) -> None:
    """Fail closed: V1 has no fields from which source rows can be proved."""

    raise Prop1224CandidateArtifactError(
        "candidate cannot be promoted: missing " + "; ".join(MISSING_REALIZATION_FIELDS)
    )


__all__ = [
    "ARTIFACT_HEADER",
    "MANIFEST_KIND",
    "MISSING_REALIZATION_FIELDS",
    "Prop1224CandidateArtifactError",
    "Prop1224CandidateCertificate",
    "Prop1224CandidateShard",
    "SEMANTIC_STATUS",
    "arithmetic_check",
    "candidate_from_verified_report",
    "candidate_manifest",
    "decode_candidate",
    "encode_candidate",
    "manifest_bytes",
    "require_semantic_realization",
]
