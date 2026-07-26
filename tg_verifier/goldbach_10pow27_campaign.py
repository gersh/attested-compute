# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed finite Goldbach campaign below the 10^27 crossover.

This is a new, versioned campaign.  It reuses the reviewed GoldbachGPU and
prime-ladder checkers, but it never relabels its smaller domain as the
historical Helfgott--Platt computation through 8.875e30.

The schedule is capable of producing the two finite semantic premises.  It is
currently UNRUN: no aggregate or attested Azure finalizer receipt ships here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .campaign_io import CampaignIOError, canonical_json_bytes, load_json, write_immutable_json
from .goldbach_campaign import (
    ANALYTIC_10POW27_ENDPOINT,
    ANALYTIC_10POW27_TARGET,
    CampaignError,
    analytic_10pow27_parameters,
    initialize_campaign,
    load_campaign,
    validate_independent_aggregate,
)
from .goldbach_gpu_campaign import (
    AGGREGATE_SCHEMA,
    ANALYTIC_10POW27_ALGORITHM,
    ANALYTIC_10POW27_OPTIMIZED_ALGORITHM,
    ANALYTIC_10POW27_EVEN_COUNT,
    ANALYTIC_10POW27_EVEN_LIMIT,
    ANALYTIC_10POW27_EVEN_START,
    EXPECTED_OPTIMIZED_SOURCE_IDENTITY_SHA256,
    GoldbachGPUCampaignError,
    GoldbachPlan,
    load_plan as load_binary_plan,
    load_receipt as load_binary_receipt,
    make_analytic_10pow27_production_plan,
    make_optimized_analytic_10pow27_production_plan,
    receipt_paths as binary_receipt_paths,
    validate_aggregate as validate_binary_aggregate,
)


CAMPAIGN_ID = "ternary-goldbach-finite-below-10pow27-v1"
SCHEDULE_SCHEMA = "sparkinterval.goldbach-10pow27-schedule.v1"
COMBINED_SCHEMA = "sparkinterval.goldbach-10pow27-combined.v1"
COMBINED_KIND = "tg_goldbach_10pow27_gpu_plus_ladder_result_v1"
STATUS = "UNRUN"
_COMBINED_DOMAIN = b"sparkinterval/tg/goldbach-10pow27/combined/v1\x00"


class Goldbach10Pow27CampaignError(RuntimeError):
    """The lowered production schedule or one of its artifacts failed closed."""


def schedule_summary() -> dict[str, object]:
    """Return the exact reviewed schedule without fabricating run evidence."""

    parameters = analytic_10pow27_parameters()
    return {
        "schema": SCHEDULE_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "status": STATUS,
        "semantic_target_inclusive": str(ANALYTIC_10POW27_TARGET),
        "binary_goldbach": {
            "algorithm": ANALYTIC_10POW27_ALGORITHM,
            "even_start_inclusive": str(ANALYTIC_10POW27_EVEN_START),
            "even_limit_inclusive": str(ANALYTIC_10POW27_EVEN_LIMIT),
            "even_count": str(ANALYTIC_10POW27_EVEN_COUNT),
            "shard_count": 65_536,
            "production_nodes": 8,
        },
        "optimized_binary_goldbach_route": {
            "algorithm": ANALYTIC_10POW27_OPTIMIZED_ALGORITHM,
            "source_identity_sha256": (
                EXPECTED_OPTIMIZED_SOURCE_IDENTITY_SHA256
            ),
            "status": (
                "implemented-full-range-plan-run-aggregate-and-combine-"
                "route-unrun-unregistered"
            ),
        },
        "prime_ladder": {
            "parameters": parameters.to_json(),
            "scheduled_endpoint": str(ANALYTIC_10POW27_ENDPOINT),
            "range_count": parameters.range_count,
            "range_width": str(parameters.range_width),
            "proth_exponent": parameters.proth_exponent,
            "maximum_gap": str(parameters.maximum_gap),
            "endpoint_tolerance": str(parameters.endpoint_tolerance),
        },
        "execution_attested": False,
        "lean_atom_discharged": False,
        "verification_note": (
            "UNRUN: success requires every binary shard, every ladder range, "
            "both exact reducers, and the measured finalizer."
        ),
    }


def make_binary_plan(*, executable_sha256: str) -> GoldbachPlan:
    """Create the exact binary branch plan for this campaign."""

    return make_analytic_10pow27_production_plan(
        executable_sha256=executable_sha256
    )


def make_optimized_binary_plan(*, executable_sha256: str) -> GoldbachPlan:
    """Create the distinct, unregistered optimized lowered binary plan."""

    return make_optimized_analytic_10pow27_production_plan(
        executable_sha256=executable_sha256
    )


def initialize_ladder(directory: Path) -> None:
    """Initialize exactly 7,106 independent n=45 ladder ranges."""

    initialize_campaign(directory, analytic_10pow27_parameters())


def _load_binary_branch(
    *,
    plan_path: Path,
    receipts_directory: Path,
    aggregate_path: Path,
    expected_algorithm: str = ANALYTIC_10POW27_ALGORITHM,
) -> tuple[GoldbachPlan, dict[str, object]]:
    plan = load_binary_plan(plan_path)
    if (
        not plan.production
        or plan.algorithm != expected_algorithm
        or (plan.even_start, plan.even_limit)
        != (ANALYTIC_10POW27_EVEN_START, ANALYTIC_10POW27_EVEN_LIMIT)
    ):
        raise Goldbach10Pow27CampaignError(
            "binary plan is not the exact analytic-10pow27 production profile"
        )
    receipts = [
        load_binary_receipt(path, plan=plan)
        for path in binary_receipt_paths(receipts_directory)
    ]
    aggregate_value = load_json(aggregate_path, require_canonical=True)
    aggregate = validate_binary_aggregate(
        aggregate_value, plan=plan, receipts=receipts
    )
    expected_domain = {
        "even_start_inclusive": ANALYTIC_10POW27_EVEN_START,
        "even_limit_inclusive": ANALYTIC_10POW27_EVEN_LIMIT,
        "even_count": ANALYTIC_10POW27_EVEN_COUNT,
    }
    if (
        aggregate["schema"] != AGGREGATE_SCHEMA
        or aggregate["domain"] != expected_domain
        or aggregate["production_campaign_complete"] is not True
        or aggregate["coverage_structurally_complete"] is not True
    ):
        raise Goldbach10Pow27CampaignError(
            "binary aggregate does not prove the exact lowered prerequisite"
        )
    return plan, aggregate


def combine_branches(
    ladder_directory: Path,
    *,
    ladder_aggregate_path: Path,
    binary_plan_path: Path,
    binary_receipts_directory: Path,
    binary_aggregate_path: Path,
    output_path: Path | None = None,
    external_prime_checker: Path | None = None,
) -> dict[str, object]:
    """Replay both complete branches and bind their exact finite claim.

    This function remains an external verifier.  Its result intentionally says
    neither ``execution_attested`` nor ``lean_atom_discharged``.
    """

    try:
        binary_plan, binary = _load_binary_branch(
            plan_path=binary_plan_path,
            receipts_directory=binary_receipts_directory,
            aggregate_path=binary_aggregate_path,
        )
        parameters = load_campaign(ladder_directory)
        if parameters != analytic_10pow27_parameters():
            raise Goldbach10Pow27CampaignError(
                "ladder manifest is not the exact analytic-10pow27 profile"
            )
        ladder_value = load_json(ladder_aggregate_path, require_canonical=True)
        ladder = validate_independent_aggregate(
            ladder_directory,
            ladder_value,
            external_prime_checker=external_prime_checker,
        )
    except (CampaignError, GoldbachGPUCampaignError, CampaignIOError) as exc:
        raise Goldbach10Pow27CampaignError(str(exc)) from exc

    expected_last_odd = ANALYTIC_10POW27_ENDPOINT - 1
    if ladder["coverage"] != {
        "first_odd": "7",
        "last_odd": str(expected_last_odd),
    }:
        raise Goldbach10Pow27CampaignError(
            "ladder aggregate does not cover its exact scheduled endpoint"
        )
    core: dict[str, object] = {
        "schema": COMBINED_SCHEMA,
        "kind": COMBINED_KIND,
        "campaign_id": CAMPAIGN_ID,
        "classification": "production-external-computations-replayed-unattested",
        "semantic_claim": {
            "first_odd_inclusive": "7",
            "last_odd_inclusive": str(ANALYTIC_10POW27_TARGET - 1),
            "target_upper_bound_inclusive": str(ANALYTIC_10POW27_TARGET),
        },
        "binary_goldbach": {
            "algorithm": binary_plan.algorithm,
            "plan_sha256": binary_plan.plan_sha256,
            "aggregate_sha256": binary["aggregate_sha256"],
            "receipt_merkle_root_sha256": binary[
                "receipt_merkle_root_sha256"
            ],
        },
        "prime_ladder": {
            "scheduled_endpoint": str(ANALYTIC_10POW27_ENDPOINT),
            "aggregate_sha256": ladder["aggregate_sha256"],
            "range_receipt_merkle_root_sha256": ladder[
                "range_receipt_merkle_root_sha256"
            ],
            "range_count": ladder["range_count"],
        },
        "execution_attested": False,
        "lean_atom_discharged": False,
    }
    result = dict(core)
    result["combined_sha256"] = hashlib.sha256(
        _COMBINED_DOMAIN + canonical_json_bytes(core)
    ).hexdigest()
    if output_path is not None:
        try:
            write_immutable_json(output_path, result)
        except CampaignIOError as exc:
            raise Goldbach10Pow27CampaignError(str(exc)) from exc
    return result


def combine_optimized_branches(
    ladder_directory: Path,
    *,
    ladder_aggregate_path: Path,
    binary_plan_path: Path,
    binary_receipts_directory: Path,
    binary_aggregate_path: Path,
    output_path: Path | None = None,
    external_prime_checker: Path | None = None,
) -> dict[str, object]:
    """Replay the optimized binary route and the exact lowered ladder.

    The result is a complete external source artifact but is deliberately not
    accepted by the currently registered v1 finalizer, whose canonical input
    still pins the prepared base source.  Production promotion therefore
    remains a separate identity and attestation review.
    """

    try:
        binary_plan, binary = _load_binary_branch(
            plan_path=binary_plan_path,
            receipts_directory=binary_receipts_directory,
            aggregate_path=binary_aggregate_path,
            expected_algorithm=ANALYTIC_10POW27_OPTIMIZED_ALGORITHM,
        )
        parameters = load_campaign(ladder_directory)
        if parameters != analytic_10pow27_parameters():
            raise Goldbach10Pow27CampaignError(
                "ladder manifest is not the exact analytic-10pow27 profile"
            )
        ladder_value = load_json(
            ladder_aggregate_path, require_canonical=True
        )
        ladder = validate_independent_aggregate(
            ladder_directory,
            ladder_value,
            external_prime_checker=external_prime_checker,
        )
    except (CampaignError, GoldbachGPUCampaignError, CampaignIOError) as exc:
        raise Goldbach10Pow27CampaignError(str(exc)) from exc

    expected_last_odd = ANALYTIC_10POW27_ENDPOINT - 1
    if ladder["coverage"] != {
        "first_odd": "7",
        "last_odd": str(expected_last_odd),
    }:
        raise Goldbach10Pow27CampaignError(
            "ladder aggregate does not cover its exact scheduled endpoint"
        )
    core: dict[str, object] = {
        "schema": COMBINED_SCHEMA,
        "kind": COMBINED_KIND,
        "campaign_id": CAMPAIGN_ID,
        "classification": (
            "optimized-source-external-computations-replayed-unattested-"
            "not-registered"
        ),
        "semantic_claim": {
            "first_odd_inclusive": "7",
            "last_odd_inclusive": str(ANALYTIC_10POW27_TARGET - 1),
            "target_upper_bound_inclusive": str(
                ANALYTIC_10POW27_TARGET
            ),
        },
        "binary_goldbach": {
            "algorithm": binary_plan.algorithm,
            "plan_sha256": binary_plan.plan_sha256,
            "aggregate_sha256": binary["aggregate_sha256"],
            "receipt_merkle_root_sha256": binary[
                "receipt_merkle_root_sha256"
            ],
        },
        "prime_ladder": {
            "scheduled_endpoint": str(ANALYTIC_10POW27_ENDPOINT),
            "aggregate_sha256": ladder["aggregate_sha256"],
            "range_receipt_merkle_root_sha256": ladder[
                "range_receipt_merkle_root_sha256"
            ],
            "range_count": ladder["range_count"],
        },
        "execution_attested": False,
        "lean_atom_discharged": False,
    }
    result = dict(core)
    result["combined_sha256"] = hashlib.sha256(
        _COMBINED_DOMAIN + canonical_json_bytes(core)
    ).hexdigest()
    if output_path is not None:
        try:
            write_immutable_json(output_path, result)
        except CampaignIOError as exc:
            raise Goldbach10Pow27CampaignError(str(exc)) from exc
    return result


__all__ = [
    "CAMPAIGN_ID",
    "COMBINED_KIND",
    "COMBINED_SCHEMA",
    "Goldbach10Pow27CampaignError",
    "STATUS",
    "combine_branches",
    "combine_optimized_branches",
    "initialize_ladder",
    "make_binary_plan",
    "make_optimized_binary_plan",
    "schedule_summary",
]
