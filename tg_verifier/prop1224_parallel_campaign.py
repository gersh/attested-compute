# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independent q-rank shards for the full Proposition 12.2.4 computation.

Unlike the historical linear receipt chain, every complete ``q`` row starts
with ``G_q(0)=0`` and can be checked independently.  This module binds the
literal source-rank partition to exact directed row replays, allowing CPU
workers on separate H100 nodes to process leaves in any wall-clock order.  A
certificate is accepted only after leaves are restored to the fixed source
order and the generic affine/Merkle verifier proves exact coverage.

The exceptional q=1 row is isolated as leaf zero.  Splitting its internal
23-million-step prefix requires the separate two-pass r-prefix transition;
the q-level worker here intentionally keeps that row whole.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from fractions import Fraction
import hashlib
from math import gcd
from pathlib import Path
import time
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
from .campaign_io import hash_file_once
from .finite_campaigns import PROP1224_ATOM
from .prop1224_campaign import (
    _hash_q_header,
    _window,
    iter_totient_squarefree_segment,
)
from . import prop1224_directed
from .prop1224_directed import (
    DEFAULT_BITS,
    DEFAULT_LOG_TERMS,
    prop1224_directed_margin_lower_from_g_upper,
    prop1224_directed_parameters,
)
from .prop1224_factor_plan import (
    PRODUCTION_RANK_END,
    make_factor_plan,
    q_at_rank,
)


DIRECTED_PLAN_ALGORITHM = "prop1224-directed-q-rank-fixed-plan-v1"
DIRECTED_BOUNDED_PLAN_ALGORITHM = "prop1224-directed-q-rank-bounded-plan-v1"
DIRECTED_SHARD_ALGORITHM = "prop1224-directed-independent-q-shard-v1"
DIRECTED_ROW_ENCODING = "prop1224-directed-independent-q-lines-v1"
_ROW_DOMAIN = b"sparkinterval/tg/prop1224/directed-q-rows/v1\0"


class Prop1224ParallelCampaignError(RuntimeError):
    """A source range, directed row, report, or plan binding failed."""


def _integer(name: str, value: object, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Prop1224ParallelCampaignError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise Prop1224ParallelCampaignError(f"{name} must be at least {minimum}")
    return value


def make_directed_plan(
    *, rank_lower: int = 0, rank_upper: int = PRODUCTION_RANK_END,
    leaf_rows: int = 262_144
) -> FixedShardPlan:
    """Return the q partition with a distinct final-inequality algorithm id."""

    factor_shape = make_factor_plan(
        rank_lower=rank_lower,
        rank_upper=rank_upper,
        leaf_rows=leaf_rows,
    )
    algorithm = (
        DIRECTED_PLAN_ALGORITHM
        if rank_lower == 0 and rank_upper == PRODUCTION_RANK_END
        else DIRECTED_BOUNDED_PLAN_ALGORITHM
    )
    return FixedShardPlan.from_ranges(
        algorithm=algorithm,
        state_dimension=1,
        ranges=[(shard.lower, shard.upper) for shard in factor_shape.shards],
    )


@dataclass(frozen=True)
class DirectedShardReport:
    schema_version: int
    algorithm: str
    classification: str
    atom_id: str
    plan_sha256: str
    shard_index: int
    rank_lower: int
    rank_upper: int
    work_count: int
    first_q: int
    next_q: int
    precision_bits: int
    log_series_terms: int
    sieve_segment_size: int
    q_rows_completed: int
    r_steps: int
    conservative_k_rows_checked: int
    minimum_margin_lower: list[int] | None
    row_encoding: str
    row_root_sha256: str
    directed_source_sha256: str
    campaign_source_sha256: str
    elapsed_milliseconds: int
    all_retained_margin_lower_bounds_nonnegative: bool = True
    complete_q_rows_only: bool = True
    full_source_campaign: bool = False
    execution_attested: bool = False
    lean_realization_proved: bool = False
    lean_atom_discharged: bool = False

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def run_directed_shard(
    *,
    plan: FixedShardPlan,
    shard_index: int,
    precision_bits: int = DEFAULT_BITS,
    log_series_terms: int = DEFAULT_LOG_TERMS,
    sieve_segment_size: int = 250_000,
) -> DirectedShardReport:
    """Recompute every directed margin for one immutable complete-q leaf."""

    shard_index = _integer("shard_index", shard_index, minimum=0)
    precision_bits = _integer("precision_bits", precision_bits, minimum=32)
    log_series_terms = _integer("log_series_terms", log_series_terms, minimum=8)
    sieve_segment_size = _integer(
        "sieve_segment_size", sieve_segment_size, minimum=1
    )
    if shard_index >= len(plan.shards):
        raise Prop1224ParallelCampaignError("shard_index is outside the fixed plan")
    if plan.algorithm not in {
        DIRECTED_PLAN_ALGORITHM,
        DIRECTED_BOUNDED_PLAN_ALGORITHM,
    }:
        raise Prop1224ParallelCampaignError("plan is not a directed q-rank plan")
    shard = plan.shards[shard_index]
    scale = 1 << precision_bits
    digest = hashlib.sha256(_ROW_DOMAIN)
    digest.update(bytes.fromhex(plan.plan_sha256))
    digest.update(shard.index.to_bytes(8, "big"))
    q_rows = 0
    r_steps = 0
    k_rows = 0
    minimum_margin: Fraction | None = None
    started = time.perf_counter()

    for rank in range(shard.lower, shard.upper):
        q = q_at_rank(rank)
        parameters = prop1224_directed_parameters(
            q,
            bits=precision_bits,
            log_terms=log_series_terms,
        )
        first, last = _window(parameters)
        _hash_q_header(digest, parameters, first, last)
        if last < first:
            digest.update(f"C:{rank}:{q}:{first}:{last}:0\n".encode("ascii"))
            q_rows += 1
            continue

        g_lower = 0
        g_upper = 0
        for r, phi_r, squarefree in iter_totient_squarefree_segment(
            1, last + 1, segment_size=sieve_segment_size
        ):
            coprime = gcd(r, q) == 1
            if squarefree and coprime:
                g_lower += scale // phi_r
                g_upper += (scale + phi_r - 1) // phi_r
            digest.update(
                f"R:{rank}:{q}:{r}:{phi_r}:{int(squarefree)}:{int(coprime)}:"
                f"{g_lower}:{g_upper}\n".encode("ascii")
            )
            r_steps += 1
            if r < first:
                continue
            margin = prop1224_directed_margin_lower_from_g_upper(
                parameters,
                r,
                Fraction(g_upper, scale),
            )
            if margin < 0:
                raise Prop1224ParallelCampaignError(
                    f"source margin is not proved nonnegative at rank={rank}, "
                    f"q={q}, k={r}"
                )
            if minimum_margin is None or margin < minimum_margin:
                minimum_margin = margin
            k_rows += 1
            digest.update(
                f"K:{rank}:{q}:{r}:{g_lower}:{g_upper}:"
                f"{margin.numerator}/{margin.denominator}\n".encode("ascii")
            )
        digest.update(f"C:{rank}:{q}:{first}:{last}:{last}\n".encode("ascii"))
        q_rows += 1

    elapsed = time.perf_counter() - started
    directed_path = Path(prop1224_directed.__file__).resolve()
    campaign_path = Path(__file__).resolve()
    return DirectedShardReport(
        schema_version=1,
        algorithm=DIRECTED_SHARD_ALGORITHM,
        classification="directed-external-computation-not-lean-proof",
        atom_id=PROP1224_ATOM,
        plan_sha256=plan.plan_sha256,
        shard_index=shard.index,
        rank_lower=shard.lower,
        rank_upper=shard.upper,
        work_count=shard.work_count,
        first_q=q_at_rank(shard.lower),
        next_q=q_at_rank(shard.upper),
        precision_bits=precision_bits,
        log_series_terms=log_series_terms,
        sieve_segment_size=sieve_segment_size,
        q_rows_completed=q_rows,
        r_steps=r_steps,
        conservative_k_rows_checked=k_rows,
        minimum_margin_lower=(
            None
            if minimum_margin is None
            else [minimum_margin.numerator, minimum_margin.denominator]
        ),
        row_encoding=DIRECTED_ROW_ENCODING,
        row_root_sha256=digest.hexdigest(),
        directed_source_sha256=hash_file_once(directed_path)[0],
        campaign_source_sha256=hash_file_once(campaign_path)[0],
        elapsed_milliseconds=max(0, int(elapsed * 1_000)),
    )


def leaf_from_directed_report(
    *, plan: FixedShardPlan, report: DirectedShardReport
) -> AffineGuardLeaf:
    """Validate assurance fields and bind a completed directed report to its leaf."""

    if not isinstance(report, DirectedShardReport):
        raise Prop1224ParallelCampaignError("report has the wrong type")
    if report.algorithm != DIRECTED_SHARD_ALGORITHM or report.schema_version != 1:
        raise Prop1224ParallelCampaignError("directed shard algorithm changed")
    if report.classification != "directed-external-computation-not-lean-proof":
        raise Prop1224ParallelCampaignError("directed shard classification changed")
    if report.atom_id != PROP1224_ATOM:
        raise Prop1224ParallelCampaignError("directed shard atom changed")
    if report.shard_index >= len(plan.shards):
        raise Prop1224ParallelCampaignError("report shard index is outside the plan")
    shard = plan.shards[report.shard_index]
    expected = (
        plan.plan_sha256,
        shard.lower,
        shard.upper,
        shard.work_count,
        q_at_rank(shard.lower),
        q_at_rank(shard.upper),
    )
    actual = (
        report.plan_sha256,
        report.rank_lower,
        report.rank_upper,
        report.work_count,
        report.first_q,
        report.next_q,
    )
    if actual != expected or report.q_rows_completed != shard.work_count:
        raise Prop1224ParallelCampaignError("directed report changed its plan range")
    if not report.all_retained_margin_lower_bounds_nonnegative:
        raise Prop1224ParallelCampaignError("directed report lacks its margin assertion")
    if not report.complete_q_rows_only or report.full_source_campaign:
        raise Prop1224ParallelCampaignError("directed report misstates its coverage")
    if report.execution_attested or report.lean_realization_proved or report.lean_atom_discharged:
        raise Prop1224ParallelCampaignError("directed report makes an unsafe trust claim")
    if report.conservative_k_rows_checked == 0:
        if report.minimum_margin_lower is not None:
            raise Prop1224ParallelCampaignError("empty margin report has a minimum")
    else:
        if (
            not isinstance(report.minimum_margin_lower, list)
            or len(report.minimum_margin_lower) != 2
            or Fraction(*report.minimum_margin_lower) < 0
        ):
            raise Prop1224ParallelCampaignError("minimum margin is malformed or negative")
    transition = AffineGuardTransition(
        delta=(shard.work_count,),
        lower_guard=(shard.lower,),
        upper_guard=(shard.lower,),
    )
    witness = TightGuardWitness(shard.lower, 0, shard.lower)
    return make_affine_guard_leaf(
        plan=plan,
        shard_index=shard.index,
        row_root_sha256=report.row_root_sha256,
        transition=transition,
        lower_tight_witnesses=(witness,),
        upper_tight_witnesses=(witness,),
        exception_root_sha256=EMPTY_EXCEPTION_ROOT_SHA256,
    )


def verify_directed_leaves(
    *, plan: FixedShardPlan, leaves: Sequence[AffineGuardLeaf]
) -> AffineGuardVerification:
    verification = verify_affine_guard_certificate(
        plan=plan,
        root_state=(plan.domain_lower,),
        leaves=leaves,
    )
    if verification.final_state != (plan.domain_upper,):
        raise Prop1224ParallelCampaignError("directed certificate has the wrong final rank")
    return verification


__all__ = [
    "DIRECTED_PLAN_ALGORITHM",
    "DIRECTED_SHARD_ALGORITHM",
    "DirectedShardReport",
    "Prop1224ParallelCampaignError",
    "leaf_from_directed_report",
    "make_directed_plan",
    "run_directed_shard",
    "verify_directed_leaves",
]
