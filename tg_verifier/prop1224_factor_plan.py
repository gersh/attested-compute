# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fixed q-rank plan for the Proposition 12.2.4 factorization stage.

The final directed inequality is independent for every admissible ``q`` once
its complete row is started.  The historical campaign serialized those rows
through one receipt chain.  This module instead fixes a literal partition of
the 3,389,047,618 source ranks.  It binds exact segmented-factor runner output
to that plan and uses the generic affine/Merkle certificate layer to reject a
missing, duplicated, reordered, or range-substituted shard.

This is deliberately classified as a structural prefilter.  A factor leaf is
not evidence that the Proposition 12.2.4 margin was checked.  A later directed
row checker must consume the committed factors, recompute the transcendental
intervals and every retained ``G_q(k)`` margin, and give its output a distinct
domain and algorithm identifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isqrt
import re
from typing import Any, Mapping, Sequence

from .affine_guard_certificate import (
    EMPTY_EXCEPTION_ROOT_SHA256,
    AffineGuardLeaf,
    AffineGuardTransition,
    AffineGuardVerification,
    FixedShardPlan,
    TightGuardWitness,
    make_affine_guard_leaf,
    verify_affine_guard_certificate,
)
from .finite_campaigns import (
    PROP1224_DIVISOR,
    PROP1224_Q_END,
    PROP1224_Q_SPLIT,
    prop1224_first_extension_q,
    prop1224_source_q_count,
)


PRODUCTION_ALGORITHM = "prop1224-exact-factor-fixed-plan-v1"
BOUNDED_ALGORITHM = "prop1224-exact-factor-bounded-plan-v1"
RUNNER_ALGORITHM = "prop1224-exact-segmented-factor-shard-v1"
RUNNER_CLASSIFICATION = "exact-structural-prefilter-not-final-inequality"
RUNNER_ROW_ENCODING = "Q:rank:q:phi:sorted-distinct-primes\n"
PRODUCTION_LEAF_ROWS = 262_144
PRODUCTION_DENSE_RANK_END = PROP1224_Q_SPLIT - 1
PRODUCTION_RANK_END = prop1224_source_q_count()

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL_RE = re.compile(r"^(0|[1-9][0-9]*)$")
_RUNNER_KEYS = frozenset(
    {
        "algorithm",
        "classification",
        "rank_lower",
        "rank_upper",
        "work_count",
        "first_q",
        "next_q",
        "row_encoding",
        "row_root_sha256",
        "phi_sum",
        "max_distinct_factor_count",
        "prime_table_limit",
        "block_rows",
        "elapsed_seconds",
        "rows_per_second",
    }
)


class Prop1224FactorPlanError(ValueError):
    """A fixed plan or exact-factor runner report failed closed."""


def _integer(name: str, value: object, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Prop1224FactorPlanError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise Prop1224FactorPlanError(f"{name} must be at least {minimum}")
    return value


def q_at_rank(rank: int) -> int:
    """Return the exact source q at ``rank``, including the terminal sentinel."""

    rank = _integer("rank", rank, minimum=0)
    if rank > PRODUCTION_RANK_END:
        raise Prop1224FactorPlanError("rank exceeds the source scheduler")
    if rank == PRODUCTION_RANK_END:
        return PROP1224_Q_END
    if rank < PRODUCTION_DENSE_RANK_END:
        return rank + 1
    return prop1224_first_extension_q() + (
        rank - PRODUCTION_DENSE_RANK_END
    ) * PROP1224_DIVISOR


def _split_interval(lower: int, upper: int, leaf_rows: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    while lower < upper:
        following = min(upper, lower + leaf_rows)
        ranges.append((lower, following))
        lower = following
    return ranges


def make_factor_plan(
    *, rank_lower: int = 0, rank_upper: int = PRODUCTION_RANK_END,
    leaf_rows: int = PRODUCTION_LEAF_ROWS
) -> FixedShardPlan:
    """Make a fixed plan, preserving the q=1 and scheduler-regime boundaries."""

    rank_lower = _integer("rank_lower", rank_lower, minimum=0)
    rank_upper = _integer("rank_upper", rank_upper, minimum=1)
    leaf_rows = _integer("leaf_rows", leaf_rows, minimum=1)
    if rank_lower >= rank_upper or rank_upper > PRODUCTION_RANK_END:
        raise Prop1224FactorPlanError(
            "require 0 <= rank_lower < rank_upper <= 3389047618"
        )
    if leaf_rows > 100_000_000:
        raise Prop1224FactorPlanError("leaf_rows exceeds the campaign guard")

    boundaries = [rank_lower]
    for boundary in (1, PRODUCTION_DENSE_RANK_END):
        if rank_lower < boundary < rank_upper:
            boundaries.append(boundary)
    boundaries.append(rank_upper)
    ranges: list[tuple[int, int]] = []
    for lower, upper in zip(boundaries, boundaries[1:]):
        # The q=1 row is always isolated.  Its 23,207,009-value k window needs
        # a separate two-pass r-prefix plan rather than q-level load balancing.
        if lower == 0 and upper >= 1:
            ranges.append((0, 1))
            lower = 1
        if lower < upper:
            ranges.extend(_split_interval(lower, upper, leaf_rows))
    algorithm = (
        PRODUCTION_ALGORITHM
        if rank_lower == 0 and rank_upper == PRODUCTION_RANK_END
        else BOUNDED_ALGORITHM
    )
    return FixedShardPlan.from_ranges(
        algorithm=algorithm,
        state_dimension=1,
        ranges=ranges,
    )


def production_factor_plan() -> FixedShardPlan:
    """Return the immutable production plan (12,930 modest q-rank leaves)."""

    return make_factor_plan()


def _expected_prime_limit(lower: int, upper: int) -> int:
    maximum = 0
    if lower < PRODUCTION_DENSE_RANK_END:
        dense_last = min(upper, PRODUCTION_DENSE_RANK_END) - 1
        if dense_last >= lower:
            maximum = max(maximum, q_at_rank(dense_last))
    if upper > PRODUCTION_DENSE_RANK_END:
        extension_first = max(lower, PRODUCTION_DENSE_RANK_END)
        if extension_first < upper:
            maximum = max(maximum, q_at_rank(upper - 1) // PROP1224_DIVISOR)
    return isqrt(maximum)


def validate_runner_report(
    report: Mapping[str, Any], *, lower: int, upper: int
) -> None:
    """Validate all non-timing fields of one exact C++ factor-stage report."""

    if not isinstance(report, Mapping) or set(report) != _RUNNER_KEYS:
        raise Prop1224FactorPlanError("factor runner report has the wrong fields")
    if report.get("algorithm") != RUNNER_ALGORITHM:
        raise Prop1224FactorPlanError("factor runner algorithm changed")
    if report.get("classification") != RUNNER_CLASSIFICATION:
        raise Prop1224FactorPlanError("factor runner classification changed")
    expected_count = upper - lower
    expected = {
        "rank_lower": lower,
        "rank_upper": upper,
        "work_count": expected_count,
        "first_q": q_at_rank(lower),
        "next_q": q_at_rank(upper),
        "row_encoding": RUNNER_ROW_ENCODING,
        "prime_table_limit": _expected_prime_limit(lower, upper),
    }
    for name, wanted in expected.items():
        if report.get(name) != wanted:
            raise Prop1224FactorPlanError(
                f"factor runner {name} differs: expected {wanted!r}, "
                f"found {report.get(name)!r}"
            )
    row_root = report.get("row_root_sha256")
    if not isinstance(row_root, str) or _SHA256_RE.fullmatch(row_root) is None:
        raise Prop1224FactorPlanError("row_root_sha256 is malformed")
    phi_sum = report.get("phi_sum")
    if not isinstance(phi_sum, str) or _DECIMAL_RE.fullmatch(phi_sum) is None:
        raise Prop1224FactorPlanError("phi_sum is not canonical unsigned decimal")
    if int(phi_sum) < expected_count:
        raise Prop1224FactorPlanError("phi_sum is below the exact positive-row bound")
    factor_count = _integer(
        "max_distinct_factor_count",
        report.get("max_distinct_factor_count"),
        minimum=0,
    )
    if factor_count > 16:
        raise Prop1224FactorPlanError("factor runner exceeded its packed capacity")
    _integer("block_rows", report.get("block_rows"), minimum=1)
    for name in ("elapsed_seconds", "rows_per_second"):
        value = report.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise Prop1224FactorPlanError(f"{name} must be a nonnegative number")


def leaf_from_runner_report(
    *, plan: FixedShardPlan, shard_index: int, report: Mapping[str, Any]
) -> AffineGuardLeaf:
    """Bind a checked runner report to one literal plan leaf."""

    shard_index = _integer("shard_index", shard_index, minimum=0)
    if shard_index >= len(plan.shards):
        raise Prop1224FactorPlanError("shard_index is outside the fixed plan")
    shard = plan.shards[shard_index]
    validate_runner_report(report, lower=shard.lower, upper=shard.upper)
    # The one-dimensional affine state is the completed source-rank count.
    # Requiring incoming==lower makes the exclusive scan reject every
    # reordering even before Merkle commitments are considered.
    transition = AffineGuardTransition(
        delta=(shard.work_count,),
        lower_guard=(shard.lower,),
        upper_guard=(shard.lower,),
    )
    witness = TightGuardWitness(
        row_index=shard.lower,
        prefix_delta=0,
        row_guard=shard.lower,
    )
    return make_affine_guard_leaf(
        plan=plan,
        shard_index=shard_index,
        row_root_sha256=report["row_root_sha256"],
        transition=transition,
        lower_tight_witnesses=(witness,),
        upper_tight_witnesses=(witness,),
        exception_root_sha256=EMPTY_EXCEPTION_ROOT_SHA256,
    )


def verify_factor_leaves(
    *, plan: FixedShardPlan, leaves: Sequence[AffineGuardLeaf]
) -> AffineGuardVerification:
    """Check total plan coverage and ordered Merkle/affine commitments."""

    verification = verify_affine_guard_certificate(
        plan=plan,
        root_state=(plan.domain_lower,),
        leaves=leaves,
    )
    if verification.final_state != (plan.domain_upper,):
        raise Prop1224FactorPlanError("factor certificate has the wrong final rank")
    return verification


@dataclass(frozen=True)
class Prop1224FactorCapability:
    """Machine-readable statement of what this stage does and does not prove."""

    source_q_rows: int = PRODUCTION_RANK_END
    final_margin_rows_checked: int = 0
    full_source_scheduler_partitioned: bool = True
    exact_factorization_replay_required: bool = True
    final_directed_inequality_proved: bool = False
    lean_realization_proved: bool = False


__all__ = [
    "BOUNDED_ALGORITHM",
    "PRODUCTION_ALGORITHM",
    "PRODUCTION_LEAF_ROWS",
    "PRODUCTION_RANK_END",
    "Prop1224FactorCapability",
    "Prop1224FactorPlanError",
    "RUNNER_ALGORITHM",
    "leaf_from_runner_report",
    "make_factor_plan",
    "production_factor_plan",
    "q_at_rank",
    "validate_runner_report",
    "verify_factor_leaves",
]
