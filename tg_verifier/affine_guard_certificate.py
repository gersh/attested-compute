# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact certificates for ordered shards with affine guarded state updates.

Many finite verification campaigns have the same small sequential boundary:
each row updates an integer state by a fixed additive delta, and is valid only
when its incoming state lies between coordinate-wise integer guards.  A shard
can summarize those rows by the transition

``S = (delta, lower_guard, upper_guard)``.

If ``A`` runs before ``B``, their exact composition is

``delta = A.delta + B.delta``
``lower = max(A.lower, B.lower - A.delta)``
``upper = min(A.upper, B.upper - A.delta)``.

This module checks that algebra, derives all shard inputs by an exclusive scan
from one trusted root state, and commits the ordered leaves with
domain-separated SHA-256 Merkle hashing.  It deliberately does *not* infer
that a row root was honestly computed.  An algorithm-specific replay checker
must recompute the rows, guards, witnesses, and exception root.  The generic
layer prevents that replay result from being reordered, omitted, duplicated,
or attached to a different campaign plan.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cached_property
import hashlib
import re
from typing import Any

from .campaign_io import canonical_json_bytes


PLAN_SCHEMA = "sparkinterval.affine-guard-plan.v1"
LEAF_SCHEMA = "sparkinterval.affine-guard-leaf.v1"
CERTIFICATE_SCHEMA = "sparkinterval.affine-guard-certificate.v1"

_PLAN_DOMAIN = b"sparkinterval/affine-guard/plan/v1\x00"
_LEAF_DOMAIN = b"sparkinterval/affine-guard/leaf/v1\x00"
_MERKLE_NODE_DOMAIN = b"sparkinterval/affine-guard/merkle-node/v1\x00"
_MERKLE_ODD_DOMAIN = b"sparkinterval/affine-guard/merkle-odd/v1\x00"
_MERKLE_EMPTY_DOMAIN = b"sparkinterval/affine-guard/merkle-empty/v1\x00"
_CERTIFICATE_ROOT_DOMAIN = b"sparkinterval/affine-guard/certificate-root/v1\x00"
_EXCEPTION_LEAF_DOMAIN = b"sparkinterval/affine-guard/exception-leaf/v1\x00"
_EXCEPTION_NODE_DOMAIN = b"sparkinterval/affine-guard/exception-node/v1\x00"
_EXCEPTION_ODD_DOMAIN = b"sparkinterval/affine-guard/exception-odd/v1\x00"
_EXCEPTION_EMPTY_DOMAIN = b"sparkinterval/affine-guard/exception-empty/v1\x00"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class AffineGuardCertificateError(ValueError):
    """An affine transition, shard plan, or certificate is malformed."""


def _require_int(name: str, value: object, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AffineGuardCertificateError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise AffineGuardCertificateError(f"{name} must be at least {minimum}")
    return value


def _require_label(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise AffineGuardCertificateError(f"{name} must be a nonempty string")
    if any(ord(character) < 0x20 for character in value):
        raise AffineGuardCertificateError(f"{name} must not contain control characters")
    return value


def _require_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise AffineGuardCertificateError(
            f"{name} must be a lowercase 64-digit SHA-256 hex string"
        )
    return value


def _require_vector(name: str, value: object) -> tuple[int, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise AffineGuardCertificateError(f"{name} must be an integer vector")
    result = tuple(
        _require_int(f"{name}[{index}]", coordinate)
        for index, coordinate in enumerate(value)
    )
    if not result:
        raise AffineGuardCertificateError(f"{name} must not be empty")
    return result


def _require_object_keys(
    name: str, value: object, required: frozenset[str]
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AffineGuardCertificateError(f"{name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise AffineGuardCertificateError(f"{name} keys must be strings")
    keys = set(value)
    if keys != required:
        missing = sorted(required - keys)
        extra = sorted(keys - required)
        raise AffineGuardCertificateError(
            f"{name} has wrong keys (missing={missing}, extra={extra})"
        )
    return value


def _hash_json(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + canonical_json_bytes(value)).hexdigest()


@dataclass(frozen=True)
class AffineGuardTransition:
    """An integer-vector update and its inclusive incoming-state guards."""

    delta: tuple[int, ...]
    lower_guard: tuple[int, ...]
    upper_guard: tuple[int, ...]

    def __post_init__(self) -> None:
        delta = _require_vector("delta", self.delta)
        lower = _require_vector("lower_guard", self.lower_guard)
        upper = _require_vector("upper_guard", self.upper_guard)
        if len(lower) != len(delta) or len(upper) != len(delta):
            raise AffineGuardCertificateError(
                "delta and guard vectors must have the same dimension"
            )
        for coordinate, (lo, hi) in enumerate(zip(lower, upper, strict=True)):
            if lo > hi:
                raise AffineGuardCertificateError(
                    f"empty guard at coordinate {coordinate}: {lo} > {hi}"
                )
        object.__setattr__(self, "delta", delta)
        object.__setattr__(self, "lower_guard", lower)
        object.__setattr__(self, "upper_guard", upper)

    @property
    def dimension(self) -> int:
        return len(self.delta)

    def accepts(self, state: Sequence[int]) -> bool:
        candidate = _require_vector("state", state)
        if len(candidate) != self.dimension:
            raise AffineGuardCertificateError(
                "state and transition dimensions do not match"
            )
        return all(
            lo <= value <= hi
            for value, lo, hi in zip(
                candidate, self.lower_guard, self.upper_guard, strict=True
            )
        )

    def apply(self, state: Sequence[int]) -> tuple[int, ...]:
        candidate = _require_vector("state", state)
        if len(candidate) != self.dimension:
            raise AffineGuardCertificateError(
                "state and transition dimensions do not match"
            )
        if not self.accepts(candidate):
            raise AffineGuardCertificateError("incoming state violates transition guard")
        return tuple(
            value + change
            for value, change in zip(candidate, self.delta, strict=True)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "delta": list(self.delta),
            "lower_guard": list(self.lower_guard),
            "upper_guard": list(self.upper_guard),
        }

    @classmethod
    def from_dict(cls, value: object) -> "AffineGuardTransition":
        item = _require_object_keys(
            "transition", value, frozenset({"delta", "lower_guard", "upper_guard"})
        )
        return cls(
            delta=item["delta"],  # type: ignore[arg-type]
            lower_guard=item["lower_guard"],  # type: ignore[arg-type]
            upper_guard=item["upper_guard"],  # type: ignore[arg-type]
        )


def compose_affine_guards(
    first: AffineGuardTransition, second: AffineGuardTransition
) -> AffineGuardTransition:
    """Return the transition for running ``first`` and then ``second``."""

    if first.dimension != second.dimension:
        raise AffineGuardCertificateError(
            "cannot compose transitions with different dimensions"
        )
    delta = tuple(
        left + right for left, right in zip(first.delta, second.delta, strict=True)
    )
    lower = tuple(
        max(left, right - change)
        for left, right, change in zip(
            first.lower_guard, second.lower_guard, first.delta, strict=True
        )
    )
    upper = tuple(
        min(left, right - change)
        for left, right, change in zip(
            first.upper_guard, second.upper_guard, first.delta, strict=True
        )
    )
    try:
        return AffineGuardTransition(delta, lower, upper)
    except AffineGuardCertificateError as exc:
        raise AffineGuardCertificateError(
            "composed transition has no admissible incoming state"
        ) from exc


@dataclass(frozen=True)
class ExclusiveScanResult:
    """Inputs derived for each shard and the exact composed transition."""

    incoming_states: tuple[tuple[int, ...], ...]
    final_state: tuple[int, ...]
    aggregate_transition: AffineGuardTransition | None


def exclusive_scan_from_root(
    root_state: Sequence[int], transitions: Sequence[AffineGuardTransition]
) -> ExclusiveScanResult:
    """Derive every shard input from one root, rejecting any guard failure.

    ``incoming_states[i]`` is the root plus the deltas of shards strictly
    before ``i``.  No incoming state supplied by a shard producer is trusted.
    """

    root = _require_vector("root_state", root_state)
    incoming: list[tuple[int, ...]] = []
    current = root
    aggregate: AffineGuardTransition | None = None
    for index, transition in enumerate(transitions):
        if not isinstance(transition, AffineGuardTransition):
            raise AffineGuardCertificateError(
                f"transitions[{index}] must be an AffineGuardTransition"
            )
        if transition.dimension != len(root):
            raise AffineGuardCertificateError(
                f"transition {index} has the wrong state dimension"
            )
        if not transition.accepts(current):
            raise AffineGuardCertificateError(
                f"root-derived incoming state violates shard {index} guard"
            )
        incoming.append(current)
        current = transition.apply(current)
        aggregate = (
            transition
            if aggregate is None
            else compose_affine_guards(aggregate, transition)
        )

    if aggregate is not None:
        if not aggregate.accepts(root):
            raise AffineGuardCertificateError(
                "aggregate transition unexpectedly rejects the root state"
            )
        if aggregate.apply(root) != current:
            raise AffineGuardCertificateError(
                "aggregate transition disagrees with the exclusive scan"
            )
    return ExclusiveScanResult(tuple(incoming), current, aggregate)


@dataclass(frozen=True)
class ShardRange:
    """One literal, nonempty half-open work range in a fixed plan."""

    index: int
    lower: int
    upper: int
    work_count: int

    def __post_init__(self) -> None:
        index = _require_int("shard index", self.index, minimum=0)
        lower = _require_int("shard lower", self.lower)
        upper = _require_int("shard upper", self.upper)
        work_count = _require_int("shard work_count", self.work_count, minimum=1)
        if lower >= upper:
            raise AffineGuardCertificateError(
                "shard range must be a nonempty half-open interval"
            )
        if work_count != upper - lower:
            raise AffineGuardCertificateError(
                "shard work_count must equal upper - lower"
            )
        object.__setattr__(self, "index", index)
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)
        object.__setattr__(self, "work_count", work_count)

    def to_dict(self) -> dict[str, int]:
        return {
            "index": self.index,
            "lower": self.lower,
            "upper": self.upper,
            "work_count": self.work_count,
        }

    @classmethod
    def from_dict(cls, value: object) -> "ShardRange":
        item = _require_object_keys(
            "shard range",
            value,
            frozenset({"index", "lower", "upper", "work_count"}),
        )
        return cls(
            index=item["index"],  # type: ignore[arg-type]
            lower=item["lower"],  # type: ignore[arg-type]
            upper=item["upper"],  # type: ignore[arg-type]
            work_count=item["work_count"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class FixedShardPlan:
    """The only accepted ordering and coverage of a campaign's work domain."""

    algorithm: str
    state_dimension: int
    domain_lower: int
    domain_upper: int
    shards: tuple[ShardRange, ...]

    def __post_init__(self) -> None:
        algorithm = _require_label("algorithm", self.algorithm)
        dimension = _require_int("state_dimension", self.state_dimension, minimum=1)
        domain_lower = _require_int("domain_lower", self.domain_lower)
        domain_upper = _require_int("domain_upper", self.domain_upper)
        if domain_lower >= domain_upper:
            raise AffineGuardCertificateError(
                "plan domain must be a nonempty half-open interval"
            )
        if isinstance(self.shards, (str, bytes)) or not isinstance(
            self.shards, Sequence
        ):
            raise AffineGuardCertificateError("shards must be an ordered sequence")
        shards = tuple(self.shards)
        if not shards:
            raise AffineGuardCertificateError("plan must contain at least one shard")
        if any(not isinstance(shard, ShardRange) for shard in shards):
            raise AffineGuardCertificateError("every plan shard must be a ShardRange")

        indices = [shard.index for shard in shards]
        if len(set(indices)) != len(indices):
            raise AffineGuardCertificateError("plan contains a duplicate shard index")
        ranges = [(shard.lower, shard.upper) for shard in shards]
        if len(set(ranges)) != len(ranges):
            raise AffineGuardCertificateError("plan contains a duplicate shard range")

        expected_lower = domain_lower
        for expected_index, shard in enumerate(shards):
            if shard.index != expected_index:
                raise AffineGuardCertificateError(
                    "plan shard indices must be exactly 0, 1, ..., n-1 in order"
                )
            if shard.lower > expected_lower:
                raise AffineGuardCertificateError(
                    f"gap before shard {shard.index}: "
                    f"expected {expected_lower}, found {shard.lower}"
                )
            if shard.lower < expected_lower:
                raise AffineGuardCertificateError(
                    f"overlap before shard {shard.index}: "
                    f"expected {expected_lower}, found {shard.lower}"
                )
            expected_lower = shard.upper
        if expected_lower < domain_upper:
            raise AffineGuardCertificateError(
                f"gap after final shard: expected endpoint {domain_upper}, "
                f"found {expected_lower}"
            )
        if expected_lower > domain_upper:
            raise AffineGuardCertificateError(
                f"final shard exceeds plan domain endpoint {domain_upper}"
            )

        object.__setattr__(self, "algorithm", algorithm)
        object.__setattr__(self, "state_dimension", dimension)
        object.__setattr__(self, "domain_lower", domain_lower)
        object.__setattr__(self, "domain_upper", domain_upper)
        object.__setattr__(self, "shards", shards)

    @classmethod
    def from_ranges(
        cls,
        *,
        algorithm: str,
        state_dimension: int,
        ranges: Sequence[tuple[int, int]],
    ) -> "FixedShardPlan":
        if not ranges:
            raise AffineGuardCertificateError("ranges must not be empty")
        shards = tuple(
            ShardRange(index, lower, upper, upper - lower)
            for index, (lower, upper) in enumerate(ranges)
        )
        return cls(
            algorithm=algorithm,
            state_dimension=state_dimension,
            domain_lower=shards[0].lower,
            domain_upper=shards[-1].upper,
            shards=shards,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_schema": PLAN_SCHEMA,
            "algorithm": self.algorithm,
            "state_dimension": self.state_dimension,
            "domain": {"lower": self.domain_lower, "upper": self.domain_upper},
            "shards": [shard.to_dict() for shard in self.shards],
        }

    @cached_property
    def plan_sha256(self) -> str:
        return _hash_json(_PLAN_DOMAIN, self.to_dict())

    @classmethod
    def from_dict(cls, value: object) -> "FixedShardPlan":
        item = _require_object_keys(
            "plan",
            value,
            frozenset(
                {"plan_schema", "algorithm", "state_dimension", "domain", "shards"}
            ),
        )
        if item["plan_schema"] != PLAN_SCHEMA:
            raise AffineGuardCertificateError("unsupported affine-guard plan schema")
        domain = _require_object_keys(
            "plan domain", item["domain"], frozenset({"lower", "upper"})
        )
        raw_shards = item["shards"]
        if isinstance(raw_shards, (str, bytes)) or not isinstance(
            raw_shards, Sequence
        ):
            raise AffineGuardCertificateError("plan shards must be an array")
        return cls(
            algorithm=item["algorithm"],  # type: ignore[arg-type]
            state_dimension=item["state_dimension"],  # type: ignore[arg-type]
            domain_lower=domain["lower"],  # type: ignore[arg-type]
            domain_upper=domain["upper"],  # type: ignore[arg-type]
            shards=tuple(ShardRange.from_dict(shard) for shard in raw_shards),
        )


@dataclass(frozen=True)
class TightGuardWitness:
    """A row claim attaining one aggregate guard coordinate.

    If the state delta before this row is ``prefix_delta`` and the row guard
    is ``row_guard``, then the corresponding shard-input guard is
    ``row_guard - prefix_delta``.  The generic verifier checks that equation
    and the row range.  The algorithm-specific replay must check the claimed
    row facts against the row commitment.
    """

    row_index: int
    prefix_delta: int
    row_guard: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_index", _require_int("row_index", self.row_index))
        object.__setattr__(
            self, "prefix_delta", _require_int("prefix_delta", self.prefix_delta)
        )
        object.__setattr__(self, "row_guard", _require_int("row_guard", self.row_guard))

    @property
    def derived_guard(self) -> int:
        return self.row_guard - self.prefix_delta

    def to_dict(self) -> dict[str, int]:
        return {
            "row_index": self.row_index,
            "prefix_delta": self.prefix_delta,
            "row_guard": self.row_guard,
        }

    @classmethod
    def from_dict(cls, value: object) -> "TightGuardWitness":
        item = _require_object_keys(
            "tight guard witness",
            value,
            frozenset({"row_index", "prefix_delta", "row_guard"}),
        )
        return cls(
            row_index=item["row_index"],  # type: ignore[arg-type]
            prefix_delta=item["prefix_delta"],  # type: ignore[arg-type]
            row_guard=item["row_guard"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class AffineGuardLeaf:
    """A plan-bound shard summary committed as one Merkle leaf."""

    plan_sha256: str
    shard_index: int
    lower: int
    upper: int
    work_count: int
    row_root_sha256: str
    transition: AffineGuardTransition
    lower_tight_witnesses: tuple[TightGuardWitness, ...]
    upper_tight_witnesses: tuple[TightGuardWitness, ...]
    exception_root_sha256: str

    def __post_init__(self) -> None:
        plan_sha = _require_sha256("plan_sha256", self.plan_sha256)
        shard_index = _require_int("shard_index", self.shard_index, minimum=0)
        lower = _require_int("lower", self.lower)
        upper = _require_int("upper", self.upper)
        work_count = _require_int("work_count", self.work_count, minimum=1)
        if lower >= upper:
            raise AffineGuardCertificateError(
                "leaf range must be a nonempty half-open interval"
            )
        if work_count != upper - lower:
            raise AffineGuardCertificateError(
                "leaf work_count must equal upper - lower"
            )
        row_root = _require_sha256("row_root_sha256", self.row_root_sha256)
        exception_root = _require_sha256(
            "exception_root_sha256", self.exception_root_sha256
        )
        if not isinstance(self.transition, AffineGuardTransition):
            raise AffineGuardCertificateError(
                "transition must be an AffineGuardTransition"
            )
        lower_witnesses = tuple(self.lower_tight_witnesses)
        upper_witnesses = tuple(self.upper_tight_witnesses)
        dimension = self.transition.dimension
        if len(lower_witnesses) != dimension or len(upper_witnesses) != dimension:
            raise AffineGuardCertificateError(
                "each transition coordinate needs one lower and one upper tight witness"
            )
        for side, witnesses, guards in (
            ("lower", lower_witnesses, self.transition.lower_guard),
            ("upper", upper_witnesses, self.transition.upper_guard),
        ):
            for coordinate, (witness, guard) in enumerate(
                zip(witnesses, guards, strict=True)
            ):
                if not isinstance(witness, TightGuardWitness):
                    raise AffineGuardCertificateError(
                        f"{side} witness {coordinate} has the wrong type"
                    )
                if not lower <= witness.row_index < upper:
                    raise AffineGuardCertificateError(
                        f"{side} witness {coordinate} lies outside the shard range"
                    )
                if witness.derived_guard != guard:
                    raise AffineGuardCertificateError(
                        f"{side} witness {coordinate} is not tight: "
                        f"derived {witness.derived_guard}, expected {guard}"
                    )

        object.__setattr__(self, "plan_sha256", plan_sha)
        object.__setattr__(self, "shard_index", shard_index)
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)
        object.__setattr__(self, "work_count", work_count)
        object.__setattr__(self, "row_root_sha256", row_root)
        object.__setattr__(self, "lower_tight_witnesses", lower_witnesses)
        object.__setattr__(self, "upper_tight_witnesses", upper_witnesses)
        object.__setattr__(self, "exception_root_sha256", exception_root)

    def validate_against(self, plan: FixedShardPlan) -> None:
        if self.plan_sha256 != plan.plan_sha256:
            raise AffineGuardCertificateError("leaf is bound to a different plan SHA")
        if self.shard_index >= len(plan.shards):
            raise AffineGuardCertificateError("leaf shard index is not in the plan")
        expected = plan.shards[self.shard_index]
        actual = (self.shard_index, self.lower, self.upper, self.work_count)
        wanted = (expected.index, expected.lower, expected.upper, expected.work_count)
        if actual != wanted:
            raise AffineGuardCertificateError(
                "leaf index, bounds, or work_count do not match the fixed plan"
            )
        if self.transition.dimension != plan.state_dimension:
            raise AffineGuardCertificateError(
                "leaf transition dimension does not match the fixed plan"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "leaf_schema": LEAF_SCHEMA,
            "plan_sha256": self.plan_sha256,
            "shard": {
                "index": self.shard_index,
                "lower": self.lower,
                "upper": self.upper,
                "work_count": self.work_count,
            },
            "row_root_sha256": self.row_root_sha256,
            "transition": self.transition.to_dict(),
            "tight_witnesses": {
                "lower": [witness.to_dict() for witness in self.lower_tight_witnesses],
                "upper": [witness.to_dict() for witness in self.upper_tight_witnesses],
            },
            "exception_root_sha256": self.exception_root_sha256,
        }

    @cached_property
    def leaf_sha256(self) -> str:
        return _hash_json(_LEAF_DOMAIN, self.to_dict())

    @classmethod
    def from_dict(cls, value: object) -> "AffineGuardLeaf":
        item = _require_object_keys(
            "leaf",
            value,
            frozenset(
                {
                    "leaf_schema",
                    "plan_sha256",
                    "shard",
                    "row_root_sha256",
                    "transition",
                    "tight_witnesses",
                    "exception_root_sha256",
                }
            ),
        )
        if item["leaf_schema"] != LEAF_SCHEMA:
            raise AffineGuardCertificateError("unsupported affine-guard leaf schema")
        shard = _require_object_keys(
            "leaf shard",
            item["shard"],
            frozenset({"index", "lower", "upper", "work_count"}),
        )
        witnesses = _require_object_keys(
            "tight_witnesses",
            item["tight_witnesses"],
            frozenset({"lower", "upper"}),
        )
        lower_witnesses = witnesses["lower"]
        upper_witnesses = witnesses["upper"]
        if isinstance(lower_witnesses, (str, bytes)) or not isinstance(
            lower_witnesses, Sequence
        ):
            raise AffineGuardCertificateError("lower tight witnesses must be an array")
        if isinstance(upper_witnesses, (str, bytes)) or not isinstance(
            upper_witnesses, Sequence
        ):
            raise AffineGuardCertificateError("upper tight witnesses must be an array")
        return cls(
            plan_sha256=item["plan_sha256"],  # type: ignore[arg-type]
            shard_index=shard["index"],  # type: ignore[arg-type]
            lower=shard["lower"],  # type: ignore[arg-type]
            upper=shard["upper"],  # type: ignore[arg-type]
            work_count=shard["work_count"],  # type: ignore[arg-type]
            row_root_sha256=item["row_root_sha256"],  # type: ignore[arg-type]
            transition=AffineGuardTransition.from_dict(item["transition"]),
            lower_tight_witnesses=tuple(
                TightGuardWitness.from_dict(witness) for witness in lower_witnesses
            ),
            upper_tight_witnesses=tuple(
                TightGuardWitness.from_dict(witness) for witness in upper_witnesses
            ),
            exception_root_sha256=item["exception_root_sha256"],  # type: ignore[arg-type]
        )


def make_affine_guard_leaf(
    *,
    plan: FixedShardPlan,
    shard_index: int,
    row_root_sha256: str,
    transition: AffineGuardTransition,
    lower_tight_witnesses: Sequence[TightGuardWitness],
    upper_tight_witnesses: Sequence[TightGuardWitness],
    exception_root_sha256: str,
) -> AffineGuardLeaf:
    """Construct a leaf using bounds and work count copied from ``plan``."""

    index = _require_int("shard_index", shard_index, minimum=0)
    if index >= len(plan.shards):
        raise AffineGuardCertificateError("shard_index is not in the plan")
    shard = plan.shards[index]
    leaf = AffineGuardLeaf(
        plan_sha256=plan.plan_sha256,
        shard_index=index,
        lower=shard.lower,
        upper=shard.upper,
        work_count=shard.work_count,
        row_root_sha256=row_root_sha256,
        transition=transition,
        lower_tight_witnesses=tuple(lower_tight_witnesses),
        upper_tight_witnesses=tuple(upper_tight_witnesses),
        exception_root_sha256=exception_root_sha256,
    )
    leaf.validate_against(plan)
    return leaf


def _merkle_reduce(
    digests: Sequence[str], *, node_domain: bytes, odd_domain: bytes, empty_domain: bytes
) -> str:
    for index, digest in enumerate(digests):
        _require_sha256(f"digest[{index}]", digest)
    if not digests:
        return hashlib.sha256(empty_domain).hexdigest()
    level = [bytes.fromhex(digest) for digest in digests]
    while len(level) > 1:
        following: list[bytes] = []
        for index in range(0, len(level), 2):
            left = level[index]
            if index + 1 == len(level):
                following.append(hashlib.sha256(odd_domain + left).digest())
            else:
                right = level[index + 1]
                following.append(hashlib.sha256(node_domain + left + right).digest())
        level = following
    return level[0].hex()


def affine_guard_leaf_merkle_root(leaves: Sequence[AffineGuardLeaf]) -> str:
    """Commit an ordered leaf sequence with distinct leaf/node/odd domains."""

    for index, leaf in enumerate(leaves):
        if not isinstance(leaf, AffineGuardLeaf):
            raise AffineGuardCertificateError(
                f"leaves[{index}] must be an AffineGuardLeaf"
            )
    return _merkle_reduce(
        [leaf.leaf_sha256 for leaf in leaves],
        node_domain=_MERKLE_NODE_DOMAIN,
        odd_domain=_MERKLE_ODD_DOMAIN,
        empty_domain=_MERKLE_EMPTY_DOMAIN,
    )


def exception_merkle_root(exceptions: Sequence[object]) -> str:
    """Return a canonical, domain-separated commitment to exception records."""

    if isinstance(exceptions, (str, bytes)) or not isinstance(exceptions, Sequence):
        raise AffineGuardCertificateError("exceptions must be an ordered sequence")
    digests = [_hash_json(_EXCEPTION_LEAF_DOMAIN, item) for item in exceptions]
    return _merkle_reduce(
        digests,
        node_domain=_EXCEPTION_NODE_DOMAIN,
        odd_domain=_EXCEPTION_ODD_DOMAIN,
        empty_domain=_EXCEPTION_EMPTY_DOMAIN,
    )


EMPTY_EXCEPTION_ROOT_SHA256 = exception_merkle_root(())


@dataclass(frozen=True)
class AffineGuardVerification:
    """The checked boundary state and content commitments of one campaign."""

    plan_sha256: str
    root_state: tuple[int, ...]
    incoming_states: tuple[tuple[int, ...], ...]
    final_state: tuple[int, ...]
    aggregate_transition: AffineGuardTransition
    leaf_merkle_root_sha256: str
    certificate_root_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "certificate_schema": CERTIFICATE_SCHEMA,
            "plan_sha256": self.plan_sha256,
            "root_state": list(self.root_state),
            "final_state": list(self.final_state),
            "leaf_count": len(self.incoming_states),
            "leaf_merkle_root_sha256": self.leaf_merkle_root_sha256,
            "certificate_root_sha256": self.certificate_root_sha256,
        }


def verify_affine_guard_certificate(
    *,
    plan: FixedShardPlan,
    root_state: Sequence[int],
    leaves: Sequence[AffineGuardLeaf],
    expected_certificate_root_sha256: str | None = None,
) -> AffineGuardVerification:
    """Check plan coverage, leaf bindings, guard scan, and the Merkle root."""

    root = _require_vector("root_state", root_state)
    if len(root) != plan.state_dimension:
        raise AffineGuardCertificateError("root state dimension does not match the plan")
    if isinstance(leaves, (str, bytes)) or not isinstance(leaves, Sequence):
        raise AffineGuardCertificateError("leaves must be an ordered sequence")
    ordered = tuple(leaves)
    for index, leaf in enumerate(ordered):
        if not isinstance(leaf, AffineGuardLeaf):
            raise AffineGuardCertificateError(
                f"leaves[{index}] must be an AffineGuardLeaf"
            )

    leaf_indices = [leaf.shard_index for leaf in ordered]
    if len(set(leaf_indices)) != len(leaf_indices):
        raise AffineGuardCertificateError("certificate contains a duplicate shard leaf")
    leaf_ranges = [(leaf.lower, leaf.upper) for leaf in ordered]
    if len(set(leaf_ranges)) != len(leaf_ranges):
        raise AffineGuardCertificateError("certificate contains a duplicate shard range")
    if len(ordered) != len(plan.shards):
        raise AffineGuardCertificateError(
            f"certificate has {len(ordered)} leaves, plan requires {len(plan.shards)}"
        )
    for expected_index, leaf in enumerate(ordered):
        if leaf.shard_index != expected_index:
            raise AffineGuardCertificateError(
                "certificate leaves are missing or not in fixed plan order"
            )
        leaf.validate_against(plan)

    scan = exclusive_scan_from_root(root, [leaf.transition for leaf in ordered])
    if scan.aggregate_transition is None:
        raise AffineGuardCertificateError("a fixed nonempty plan produced no transition")
    leaf_root = affine_guard_leaf_merkle_root(ordered)
    root_payload = {
        "certificate_schema": CERTIFICATE_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "root_state": list(root),
        "final_state": list(scan.final_state),
        "leaf_count": len(ordered),
        "leaf_merkle_root_sha256": leaf_root,
    }
    certificate_root = _hash_json(_CERTIFICATE_ROOT_DOMAIN, root_payload)
    if expected_certificate_root_sha256 is not None:
        expected = _require_sha256(
            "expected_certificate_root_sha256", expected_certificate_root_sha256
        )
        if certificate_root != expected:
            raise AffineGuardCertificateError(
                "certificate root does not match the expected commitment"
            )
    return AffineGuardVerification(
        plan_sha256=plan.plan_sha256,
        root_state=root,
        incoming_states=scan.incoming_states,
        final_state=scan.final_state,
        aggregate_transition=scan.aggregate_transition,
        leaf_merkle_root_sha256=leaf_root,
        certificate_root_sha256=certificate_root,
    )


__all__ = [
    "AffineGuardCertificateError",
    "AffineGuardLeaf",
    "AffineGuardTransition",
    "AffineGuardVerification",
    "CERTIFICATE_SCHEMA",
    "EMPTY_EXCEPTION_ROOT_SHA256",
    "ExclusiveScanResult",
    "FixedShardPlan",
    "LEAF_SCHEMA",
    "PLAN_SCHEMA",
    "ShardRange",
    "TightGuardWitness",
    "affine_guard_leaf_merkle_root",
    "compose_affine_guards",
    "exception_merkle_root",
    "exclusive_scan_from_root",
    "make_affine_guard_leaf",
    "verify_affine_guard_certificate",
]
