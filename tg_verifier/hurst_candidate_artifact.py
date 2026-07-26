# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact Python codec for ``HurstCandidateArtifact.lean``.

The candidate is the small four-state affine chain already present in a
replayed Hurst campaign.  It is not the missing primitive Möbius/Q96 row
certificate, and the manifest produced here says so explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from .affine_guard_certificate import FixedShardPlan
from .campaign_io import canonical_json_bytes, load_json
from .hurst_residual_campaign import (
    DERIVED_NAME,
    PLAN_NAME,
    SOURCE_LOWER,
    SOURCE_UPPER_EXCLUSIVE,
    verify_campaign,
)


INVOCATION_ID = "hurst-shared-four-residual-production-v2"
TERMINAL = "azure-sev-snp-cpu"
JOB_BYTES = (
    b'{"campaign":"hurst-shared-four-residual-v2","source_lower":1,'
    b'"source_upper_exclusive":10000000000000001}'
)
ARTIFACT_HEADER = (
    b"TG-HURST-SHARED-CANDIDATE-V1\n"
    + b"invocation="
    + INVOCATION_ID.encode("ascii")
    + b"\nterminal="
    + TERMINAL.encode("ascii")
    + b"\njob="
    + JOB_BYTES
    + b"\n"
)
NATURAL_WIDTH = 32
INTEGER_WIDTH = 33
COUNT_WIDTH = 4
NATURAL_LIMIT = 1 << (8 * NATURAL_WIDTH)
COUNT_LIMIT = 1 << (8 * COUNT_WIDTH)
MAXIMUM_BLOCK_COUNT = 1_000_000
STATE_BYTE_SIZE = 4 * INTEGER_WIDTH
GUARD_BYTE_SIZE = 2 * STATE_BYTE_SIZE
BLOCK_BYTE_SIZE = 2 * NATURAL_WIDTH + STATE_BYTE_SIZE + GUARD_BYTE_SIZE
FIXED_BYTE_SIZE = (
    2 * NATURAL_WIDTH + 2 * STATE_BYTE_SIZE + COUNT_WIDTH
)
MANIFEST_KIND = "sparkinterval.tg.hurst-candidate-artifact-manifest.v1"
SEMANTIC_STATUS = "arithmetic-chain-only-missing-primitive-row-replay"
MISSING_REALIZATION_FIELDS = (
    "per-row Möbius increments and squarefree increments",
    "per-row directed lower and upper Q96 little-Mertens increments",
    "local prefix recurrence records within every block",
    "integer guard decisions for every retained source row",
    "ordinary Lean row-soundness and exact block-coverage proofs",
)


class HurstCandidateArtifactError(ValueError):
    """The candidate artifact or replayed campaign is not exact V1 data."""


def _plain_nat(value: object, what: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value >= NATURAL_LIMIT
    ):
        raise HurstCandidateArtifactError(
            f"{what} must be an unsigned 256-bit integer"
        )
    return value


def _plain_int(value: object, what: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or abs(value) >= NATURAL_LIMIT
    ):
        raise HurstCandidateArtifactError(
            f"{what} must have magnitude below 2^256"
        )
    return value


def _nat_bytes(value: object, what: str) -> bytes:
    return _plain_nat(value, what).to_bytes(NATURAL_WIDTH, "little")


def _int_bytes(value: object, what: str) -> bytes:
    integer = _plain_int(value, what)
    sign = b"\x01" if integer < 0 else b"\x00"
    return sign + abs(integer).to_bytes(NATURAL_WIDTH, "little")


def _read_nat(raw: bytes, offset: int, what: str) -> int:
    end = offset + NATURAL_WIDTH
    if end > len(raw):
        raise HurstCandidateArtifactError(f"truncated {what}")
    return int.from_bytes(raw[offset:end], "little")


def _read_int(raw: bytes, offset: int, what: str) -> int:
    end = offset + INTEGER_WIDTH
    if end > len(raw):
        raise HurstCandidateArtifactError(f"truncated {what}")
    sign = raw[offset]
    magnitude = int.from_bytes(raw[offset + 1 : end], "little")
    if sign == 0:
        return magnitude
    if sign == 1 and magnitude != 0:
        return -magnitude
    raise HurstCandidateArtifactError(
        f"{what} uses negative zero or an unknown sign byte"
    )


@dataclass(frozen=True)
class HurstCandidateState:
    mertens: int
    squarefree: int
    little_lower_q96: int
    little_upper_q96: int

    def __post_init__(self) -> None:
        for name in (
            "mertens",
            "squarefree",
            "little_lower_q96",
            "little_upper_q96",
        ):
            object.__setattr__(self, name, _plain_int(getattr(self, name), name))

    def __add__(self, other: object) -> "HurstCandidateState":
        if not isinstance(other, HurstCandidateState):
            return NotImplemented
        return HurstCandidateState(
            self.mertens + other.mertens,
            self.squarefree + other.squarefree,
            self.little_lower_q96 + other.little_lower_q96,
            self.little_upper_q96 + other.little_upper_q96,
        )


ZERO_STATE = HurstCandidateState(0, 0, 0, 0)


@dataclass(frozen=True)
class HurstCandidateGuard:
    lower: HurstCandidateState
    upper: HurstCandidateState

    def __post_init__(self) -> None:
        if not isinstance(self.lower, HurstCandidateState) or not isinstance(
            self.upper, HurstCandidateState
        ):
            raise HurstCandidateArtifactError("guard endpoints must be states")


@dataclass(frozen=True)
class HurstCandidateBlock:
    lower: int
    upper: int
    delta: HurstCandidateState
    guard: HurstCandidateGuard

    def __post_init__(self) -> None:
        object.__setattr__(self, "lower", _plain_nat(self.lower, "block lower"))
        object.__setattr__(self, "upper", _plain_nat(self.upper, "block upper"))
        if not isinstance(self.delta, HurstCandidateState):
            raise HurstCandidateArtifactError("block delta must be a state")
        if not isinstance(self.guard, HurstCandidateGuard):
            raise HurstCandidateArtifactError("block guard must be a guard")


@dataclass(frozen=True)
class HurstCandidateCertificate:
    source_lower: int
    source_upper: int
    root_state: HurstCandidateState
    final_state: HurstCandidateState
    blocks: tuple[HurstCandidateBlock, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_lower", _plain_nat(self.source_lower, "source lower")
        )
        object.__setattr__(
            self, "source_upper", _plain_nat(self.source_upper, "source upper")
        )
        if not isinstance(self.root_state, HurstCandidateState) or not isinstance(
            self.final_state, HurstCandidateState
        ):
            raise HurstCandidateArtifactError("root/final values must be states")
        if isinstance(self.blocks, (str, bytes)) or not isinstance(
            self.blocks, Sequence
        ):
            raise HurstCandidateArtifactError("blocks must be an ordered sequence")
        blocks = tuple(self.blocks)
        if any(not isinstance(block, HurstCandidateBlock) for block in blocks):
            raise HurstCandidateArtifactError(
                "every block must be a HurstCandidateBlock"
            )
        if len(blocks) > MAXIMUM_BLOCK_COUNT or len(blocks) >= COUNT_LIMIT:
            raise HurstCandidateArtifactError("candidate has too many blocks")
        object.__setattr__(self, "blocks", blocks)


def _state_bytes(state: HurstCandidateState) -> bytes:
    return b"".join(
        (
            _int_bytes(state.mertens, "state.mertens"),
            _int_bytes(state.squarefree, "state.squarefree"),
            _int_bytes(state.little_lower_q96, "state.little_lower_q96"),
            _int_bytes(state.little_upper_q96, "state.little_upper_q96"),
        )
    )


def _read_state(raw: bytes, offset: int, what: str) -> HurstCandidateState:
    return HurstCandidateState(
        _read_int(raw, offset, f"{what}.mertens"),
        _read_int(raw, offset + INTEGER_WIDTH, f"{what}.squarefree"),
        _read_int(raw, offset + 2 * INTEGER_WIDTH, f"{what}.little_lower_q96"),
        _read_int(raw, offset + 3 * INTEGER_WIDTH, f"{what}.little_upper_q96"),
    )


def encode_candidate(certificate: HurstCandidateCertificate) -> bytes:
    """Return the unique byte spelling accepted by the Lean V1 decoder."""

    if not isinstance(certificate, HurstCandidateCertificate):
        raise HurstCandidateArtifactError(
            "certificate must be a HurstCandidateCertificate"
        )
    body = bytearray(ARTIFACT_HEADER)
    body.extend(_nat_bytes(certificate.source_lower, "source lower"))
    body.extend(_nat_bytes(certificate.source_upper, "source upper"))
    body.extend(_state_bytes(certificate.root_state))
    body.extend(_state_bytes(certificate.final_state))
    body.extend(len(certificate.blocks).to_bytes(COUNT_WIDTH, "little"))
    for block in certificate.blocks:
        body.extend(_nat_bytes(block.lower, "block lower"))
        body.extend(_nat_bytes(block.upper, "block upper"))
        body.extend(_state_bytes(block.delta))
        body.extend(_state_bytes(block.guard.lower))
        body.extend(_state_bytes(block.guard.upper))
    return bytes(body)


def decode_candidate(raw: bytes) -> HurstCandidateCertificate:
    """Strictly decode one exact frame and reject every alternate Int spelling."""

    if not isinstance(raw, bytes):
        raise HurstCandidateArtifactError("candidate artifact must be bytes")
    if not raw.startswith(ARTIFACT_HEADER):
        raise HurstCandidateArtifactError("candidate artifact header differs")
    offset = len(ARTIFACT_HEADER)
    minimum = offset + FIXED_BYTE_SIZE
    if len(raw) < minimum:
        raise HurstCandidateArtifactError("candidate artifact is truncated")
    source_lower = _read_nat(raw, offset, "source lower")
    source_upper = _read_nat(raw, offset + NATURAL_WIDTH, "source upper")
    root_offset = offset + 2 * NATURAL_WIDTH
    root_state = _read_state(raw, root_offset, "root state")
    final_offset = root_offset + STATE_BYTE_SIZE
    final_state = _read_state(raw, final_offset, "final state")
    count_offset = final_offset + STATE_BYTE_SIZE
    block_count = int.from_bytes(
        raw[count_offset : count_offset + COUNT_WIDTH], "little"
    )
    if block_count > MAXIMUM_BLOCK_COUNT:
        raise HurstCandidateArtifactError("candidate block count exceeds V1 limit")
    expected_size = minimum + block_count * BLOCK_BYTE_SIZE
    if len(raw) != expected_size:
        raise HurstCandidateArtifactError(
            "candidate frame length does not match its block count"
        )
    cursor = minimum
    blocks: list[HurstCandidateBlock] = []
    for index in range(block_count):
        lower = _read_nat(raw, cursor, f"blocks[{index}].lower")
        upper = _read_nat(
            raw, cursor + NATURAL_WIDTH, f"blocks[{index}].upper"
        )
        delta_offset = cursor + 2 * NATURAL_WIDTH
        delta = _read_state(raw, delta_offset, f"blocks[{index}].delta")
        guard_lower = _read_state(
            raw, delta_offset + STATE_BYTE_SIZE, f"blocks[{index}].guard.lower"
        )
        guard_upper = _read_state(
            raw,
            delta_offset + 2 * STATE_BYTE_SIZE,
            f"blocks[{index}].guard.upper",
        )
        blocks.append(
            HurstCandidateBlock(
                lower,
                upper,
                delta,
                HurstCandidateGuard(guard_lower, guard_upper),
            )
        )
        cursor += BLOCK_BYTE_SIZE
    return HurstCandidateCertificate(
        source_lower, source_upper, root_state, final_state, tuple(blocks)
    )


def _state_coordinates(state: HurstCandidateState) -> tuple[int, int, int, int]:
    return (
        state.mertens,
        state.squarefree,
        state.little_lower_q96,
        state.little_upper_q96,
    )


def _guard_well_formed(guard: HurstCandidateGuard) -> bool:
    return all(
        lower <= upper
        for lower, upper in zip(
            _state_coordinates(guard.lower),
            _state_coordinates(guard.upper),
            strict=True,
        )
    )


def _guard_contains(
    guard: HurstCandidateGuard, state: HurstCandidateState
) -> bool:
    return all(
        lower <= value <= upper
        for lower, value, upper in zip(
            _state_coordinates(guard.lower),
            _state_coordinates(state),
            _state_coordinates(guard.upper),
            strict=True,
        )
    )


def arithmetic_check(certificate: HurstCandidateCertificate) -> bool:
    """Mirror ``HurstCandidateArtifact.arithmeticCheck`` exactly."""

    if not isinstance(certificate, HurstCandidateCertificate):
        return False
    if certificate.source_lower >= certificate.source_upper:
        return False
    expected_lower = certificate.source_lower
    current = certificate.root_state
    for block in certificate.blocks:
        row_count = block.upper - block.lower if block.upper >= block.lower else 0
        if (
            block.lower != expected_lower
            or block.lower >= block.upper
            or not -row_count <= block.delta.mertens <= row_count
            or not 0 <= block.delta.squarefree <= row_count
            or block.delta.little_lower_q96 > block.delta.little_upper_q96
            or not _guard_well_formed(block.guard)
            or not _guard_contains(block.guard, current)
        ):
            return False
        current = current + block.delta
        expected_lower = block.upper
    return (
        expected_lower == certificate.source_upper
        and current == certificate.final_state
        and certificate.source_lower == SOURCE_LOWER
        and certificate.source_upper == SOURCE_UPPER_EXCLUSIVE
        and certificate.root_state == ZERO_STATE
    )


def _state_from_sequence(value: object, what: str) -> HurstCandidateState:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or len(value) != 4
    ):
        raise HurstCandidateArtifactError(f"{what} must be a four-integer array")
    return HurstCandidateState(
        _plain_int(value[0], f"{what}[0]"),
        _plain_int(value[1], f"{what}[1]"),
        _plain_int(value[2], f"{what}[2]"),
        _plain_int(value[3], f"{what}[3]"),
    )


def candidate_from_replayed_campaign(
    campaign: Path,
) -> HurstCandidateCertificate:
    """Replay a complete full-source campaign, then convert its exact chain."""

    checked = verify_campaign(campaign)
    if (
        checked.mode != "full_source"
        or not checked.complete
        or not checked.full_source_range
        or not checked.source_residuals_replayed
        or checked.final_state is None
        or checked.certificate_root_sha256 is None
    ):
        raise HurstCandidateArtifactError(
            "candidate emission requires a complete replayed full-source campaign"
        )
    plan = FixedShardPlan.from_dict(
        load_json(campaign / PLAN_NAME, require_canonical=True)
    )
    derived = load_json(campaign / DERIVED_NAME, require_canonical=True)
    if not isinstance(derived, Mapping):
        raise HurstCandidateArtifactError("derived input table must be an object")
    if (
        plan.domain_lower != SOURCE_LOWER
        or plan.domain_upper != SOURCE_UPPER_EXCLUSIVE
        or plan.state_dimension != 4
        or derived.get("plan_sha256") != plan.plan_sha256
        or derived.get("root_state") != [0, 0, 0, 0]
        or derived.get("final_state") != list(checked.final_state)
    ):
        raise HurstCandidateArtifactError(
            "replayed campaign chain is not the literal Hurst V2 source geometry"
        )
    entries = derived.get("entries")
    if not isinstance(entries, list) or len(entries) != len(plan.shards):
        raise HurstCandidateArtifactError(
            "derived table does not contain exactly one entry per plan block"
        )
    blocks: list[HurstCandidateBlock] = []
    for index, (shard, entry) in enumerate(zip(plan.shards, entries, strict=True)):
        if not isinstance(entry, Mapping):
            raise HurstCandidateArtifactError(
                f"derived entries[{index}] must be an object"
            )
        if (
            entry.get("index") != index
            or entry.get("lower") != shard.lower
            or entry.get("upper") != shard.upper
        ):
            raise HurstCandidateArtifactError(
                f"derived entries[{index}] differs from the replayed plan"
            )
        incoming = _state_from_sequence(
            entry.get("incoming"), f"derived entries[{index}].incoming"
        )
        delta = _state_from_sequence(
            entry.get("delta"), f"derived entries[{index}].delta"
        )
        outgoing = _state_from_sequence(
            entry.get("outgoing"), f"derived entries[{index}].outgoing"
        )
        if incoming + delta != outgoing:
            raise HurstCandidateArtifactError(
                f"derived entries[{index}] has an inconsistent outgoing state"
            )
        blocks.append(
            HurstCandidateBlock(
                shard.lower,
                shard.upper,
                delta,
                HurstCandidateGuard(incoming, incoming),
            )
        )
    certificate = HurstCandidateCertificate(
        plan.domain_lower,
        plan.domain_upper,
        ZERO_STATE,
        _state_from_sequence(checked.final_state, "checked final state"),
        tuple(blocks),
    )
    if not arithmetic_check(certificate):
        raise HurstCandidateArtifactError(
            "replayed campaign did not produce a valid Lean arithmetic candidate"
        )
    return certificate


def candidate_manifest(relative_path: str, raw: bytes) -> dict[str, Any]:
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or relative_path.startswith("/")
        or ".." in Path(relative_path).parts
    ):
        raise HurstCandidateArtifactError(
            "candidate manifest path must be safe and relative"
        )
    certificate = decode_candidate(raw)
    if not arithmetic_check(certificate):
        raise HurstCandidateArtifactError(
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
            "SparkInterval.TernaryGoldbach.HurstCandidateArtifact.decode"
        ),
        "missing_realization_fields": list(MISSING_REALIZATION_FIELDS),
        "schema_version": 1,
        "semantic_closure": False,
        "status": SEMANTIC_STATUS,
    }


def manifest_bytes(relative_path: str, raw: bytes) -> bytes:
    return canonical_json_bytes(candidate_manifest(relative_path, raw))


def require_semantic_realization(_raw: bytes) -> None:
    """Fail closed: V1 has no fields from which primitive rows can be proved."""

    raise HurstCandidateArtifactError(
        "candidate cannot be promoted: missing " + "; ".join(MISSING_REALIZATION_FIELDS)
    )


__all__ = [
    "ARTIFACT_HEADER",
    "HurstCandidateArtifactError",
    "HurstCandidateBlock",
    "HurstCandidateCertificate",
    "HurstCandidateGuard",
    "HurstCandidateState",
    "MANIFEST_KIND",
    "MISSING_REALIZATION_FIELDS",
    "SEMANTIC_STATUS",
    "ZERO_STATE",
    "arithmetic_check",
    "candidate_from_replayed_campaign",
    "candidate_manifest",
    "decode_candidate",
    "encode_candidate",
    "manifest_bytes",
    "require_semantic_realization",
]
