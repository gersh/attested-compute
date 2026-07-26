# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed local orchestration for the Azure TG campaign portfolio.

This module compiles the reviewed ``h100_cluster`` manifest into a stable DAG
of phase groups and lazily materializes one isolated challenge/configuration
per shard.  It deliberately has no Azure mutation command.  A shard config is
an operator handoff into a backend-specific one-VM state machine, not evidence
that the shard ran and not a Lean theorem.

The production gate is intentionally strict, but it separates three different
states.  A reviewed staged invocation/result contract is enough to initialize
local state and, once the hard cost gate passes, prepare an operator handoff.
It is not a Lean realization and cannot grant theorem authority.  CPU work
also needs both the stateful CPU production operator and a campaign-specific
closed measured-job materializer.  None of these requirements can be bypassed
with a manual completion bit.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import re
import secrets
import sys
from typing import Any, Mapping

from tg_verifier.campaign_io import (
    CampaignIOError,
    advisory_lock,
    atomic_write_json,
    canonical_json_bytes,
    hash_file_once,
    load_json,
    read_bytes_once,
    sha256_bytes,
    write_immutable_json,
)
from tg_verifier.h100_cluster import (
    ClusterPlanError,
    GOLDBACH_10POW27_CAMPAIGN,
    load_manifest as load_cluster_manifest,
    verify_repository_binding,
)
from tg_verifier.azure_backend_optimizer import (
    CampaignRoute,
    ResourceDemand,
    optimize_backend_catalog,
)
from tg_verifier.azure_cpu_workload_factory import (
    PENDING_FACTORY_GAPS as CPU_MATERIALIZER_GAPS,
    source_reviewed_materializer_available as cdem_materializer_available,
)
from tg_verifier.azure_cpu_psi_workload_factory import (
    source_reviewed_materializer_available as psi_materializer_available,
)
from tg_verifier.azure_cpu_hurst_workload_factory import (
    source_reviewed_materializer_available as hurst_materializer_available,
)
from tg_verifier.azure_cpu_hurst_affine_workload_factory import (
    source_reviewed_materializer_available as hurst_affine_materializer_available,
)
from tg_verifier.azure_cpu_platt_head_workload_factory import (
    source_reviewed_materializer_available as platt_head_materializer_available,
)
from tg_verifier.azure_cpu_platt_pt21_workload_factory import (
    source_reviewed_materializer_available as platt_pt21_materializer_available,
)
from tg_verifier.azure_cpu_a7_workload_factory import (
    source_reviewed_materializer_available as a7_materializer_available,
)
from tg_verifier.azure_cpu_prop1224_workload_factory import (
    source_reviewed_materializer_available as prop1224_materializer_available,
)
from tg_verifier.azure_cpu_goldbach_10pow27_workload_factory import (
    source_reviewed_materializer_available as goldbach10pow27_materializer_available,
)
from tg_verifier.azure_cpu_goldbach_historical_workload_factory import (
    source_reviewed_materializer_available as historical_goldbach_materializer_available,
)
from tg_verifier.azure_cpu_goldbach_historical_operational_workload_factory import (
    source_reviewed_materializer_available
    as historical_goldbach_operational_materializer_available,
)
from tg_verifier.azure_cpu_dirichlet_workload_factory import (
    postcheck_materializer_blocker as dirichlet_postcheck_materializer_blocker,
    source_reviewed_materializer_available as dirichlet_materializer_available,
)
from tg_verifier.azure_h100_goldbach_10pow27_workload_factory import (
    portfolio_group_shape_matches
    as goldbach10pow27_h100_materializer_shape_available,
)
from tg_verifier.azure_h100_goldbach_historical_workload_factory import (
    portfolio_group_shape_matches
    as historical_goldbach_h100_materializer_shape_available,
)
from tg_verifier.azure_h100_r2star_workload_factory import (
    CAMPAIGN_ID as R2STAR_CAMPAIGN_ID,
    source_reviewed_materializer_available as r2star_h100_materializer_available,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for import_root in (REPOSITORY_ROOT / "azure", REPOSITORY_ROOT / "tools"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from create_attestation_challenges import (  # noqa: E402
    KIND as CHALLENGE_KIND,
    MAX_TTL_SECONDS,
    SCHEMA_VERSION as CHALLENGE_SCHEMA_VERSION,
)
from generate_trusted_compute_lean import (  # noqa: E402
    load_verified_receipt,
    registered_invocation_backend,
    registered_invocation_expected,
    validate_registered_invocation,
)
from trusted_compute_receipt import ReceiptError  # noqa: E402


SCHEMA_VERSION = 1
SPEC_KIND = "sparkinterval.azure.tg.portfolio-spec.v1"
SEMANTIC_REGISTRY_KIND = "sparkinterval.azure.tg.semantic-bindings.v1"
PLAN_KIND = "sparkinterval.azure.tg.portfolio-plan.v1"
STATE_KIND = "sparkinterval.azure.tg.portfolio-state.v1"
SHARD_CONFIG_KIND = "sparkinterval.azure.tg.portfolio-shard-config.v1"

NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
LEAN_DECL_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*\Z")
GROUP_RE = re.compile(r"[a-z0-9][a-z0-9.-]*(?:::[a-z0-9][a-z0-9.-]*)\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
PLACEHOLDER_RE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")

SPEC_FIELDS = {
    "challenge_ttl_seconds",
    "cluster_manifest",
    "completion_profile",
    "kind",
    "portfolio_id",
    "production_price_class",
    "repository_root",
    "run_root",
    "schema_version",
    "semantic_bindings",
    "verifier_key_manifest",
}
ABSOLUTE_PIN_FIELDS = {"path", "sha256", "size_bytes"}
REPOSITORY_PIN_FIELDS = {"path", "sha256", "size_bytes"}
SEMANTIC_FIELDS = {"bindings", "kind", "schema_version"}
SEMANTIC_BINDING_FIELDS = {
    "campaign_id",
    "enabled",
    "lean_theorem",
    "realization_id",
    "registered_invocation",
}
STATE_FIELDS = {
    "accepted",
    "created_at_utc",
    "kind",
    "plan_sha256",
    "portfolio_id",
    "records",
    "schema_version",
}
TASK_RECORD_FIELDS = {
    "challenge_sha256",
    "config_sha256",
    "group_id",
    "receipt_file_sha256",
    "receipt_sha256",
    "shard_index",
    "stage",
}
CHALLENGE_FIELDS = {
    "campaign_id",
    "expires_at_utc",
    "issued_at_utc",
    "kind",
    "nonce",
    "schema_version",
    "shard_index",
}


CAPABILITY_INVENTORY_PROFILE = "capability-inventory-v1"
SOURCE_RETIREMENT_PROFILE = "all-source-retirement-v1"
LOWERED_10POW27_COMPLETION_PROFILE = (
    "lowered-10pow27-theorem-completion-v1"
)

# This is deliberately independent of the editable deployment manifest.  A
# profile is a theorem-route claim, not an arbitrary campaign allow-list.  The
# manifest may describe all source and alternate capabilities, but a planner
# accepts a profile only after every physical campaign and logical-claim
# membership below agrees exactly.  Adding, removing, or reassigning a
# campaign therefore requires source review here before it can affect a run.
CAPABILITY_CAMPAIGN_LOGICAL_CLAIMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ch25-a7-boundary", ("ch25-a7-boundary",)),
    ("ch25-psi-two-pass-v1", ("ch25-psi-1e13",)),
    ("platt-head-2e4", ("platt-head-2e4",)),
    ("platt-trudgian-rh-3e12", ("platt-trudgian-rh-3e12",)),
    ("helfgott-prop-12-2-4-mpfr-v1", ("helfgott-prop-12-2-4",)),
    (
        "hurst-four-residuals-v1",
        (
            "cdem-squarefree",
            "mertens-hurst",
            "platt-little-mertens-2-11",
            "platt-little-mertens-stronger",
        ),
    ),
    ("cdem-table-abel", ("cdem-table-abel",)),
    ("ramare-zuniga-lemma-6-2", ("ramare-zuniga-lemma-6-2",)),
    (
        "helfgott-platt-goldbach-gpu-v1",
        ("helfgott-platt-theorem-4-1",),
    ),
    (
        "platt-dirichlet-theorem-7-1",
        ("platt-dirichlet-theorem-7-1",),
    ),
    (
        GOLDBACH_10POW27_CAMPAIGN,
        ("goldbach-finite-below-10pow27",),
    ),
)
CAPABILITY_CAMPAIGN_IDS = tuple(
    campaign_id for campaign_id, _claims in CAPABILITY_CAMPAIGN_LOGICAL_CLAIMS
)
HISTORICAL_GOLDBACH_CAMPAIGN = "helfgott-platt-goldbach-gpu-v1"


@dataclass(frozen=True)
class CompletionProfile:
    """A source-owned exact set of campaigns sufficient for one proof route."""

    profile_id: str
    purpose: str
    required_campaign_ids: tuple[str, ...]
    excluded_campaign_reasons: tuple[tuple[str, str], ...]


COMPLETION_PROFILES: dict[str, CompletionProfile] = {
    CAPABILITY_INVENTORY_PROFILE: CompletionProfile(
        profile_id=CAPABILITY_INVENTORY_PROFILE,
        purpose=(
            "audit and exercise every source-retirement campaign plus the "
            "distinct lowered finite endpoint; this intentionally schedules "
            "both Goldbach routes"
        ),
        required_campaign_ids=CAPABILITY_CAMPAIGN_IDS,
        excluded_campaign_reasons=(),
    ),
    SOURCE_RETIREMENT_PROFILE: CompletionProfile(
        profile_id=SOURCE_RETIREMENT_PROFILE,
        purpose=(
            "retire all thirteen named source atoms using the historical "
            "Helfgott--Platt finite computation"
        ),
        required_campaign_ids=tuple(
            campaign_id
            for campaign_id in CAPABILITY_CAMPAIGN_IDS
            if campaign_id != GOLDBACH_10POW27_CAMPAIGN
        ),
        excluded_campaign_reasons=(
            (
                GOLDBACH_10POW27_CAMPAIGN,
                "alternate lowered endpoint is not used by the all-source retirement route",
            ),
        ),
    ),
    LOWERED_10POW27_COMPLETION_PROFILE: CompletionProfile(
        profile_id=LOWERED_10POW27_COMPLETION_PROFILE,
        purpose=(
            "complete ternary Goldbach through the proved analytic crossover "
            "at 10^27 and the distinct finite-below-10^27 certificate"
        ),
        required_campaign_ids=tuple(
            campaign_id
            for campaign_id in CAPABILITY_CAMPAIGN_IDS
            if campaign_id != HISTORICAL_GOLDBACH_CAMPAIGN
        ),
        excluded_campaign_reasons=(
            (
                HISTORICAL_GOLDBACH_CAMPAIGN,
                "replaced only by the source-distinct lowered 10^27 theorem route",
            ),
        ),
    ),
}


class PortfolioError(RuntimeError):
    """A portfolio input or transition did not meet the production contract."""


@dataclass(frozen=True)
class BackendRoute:
    receipt_backend: str
    operator_adapter: str | None
    production_operator_available: bool
    reason: str | None


@dataclass(frozen=True)
class TerminalResultBinding:
    """Exact argv pair which materializes a registered invocation result."""

    argument: str
    artifact_template: str


# The H100 route hands one isolated shard to the existing challenge-first
# operator.  CPU availability is narrower than a backend class: the operator
# consumes a measured-job campaign, so a group is available only when the
# complete group shape is recognized by a closed source-reviewed materializer.
# CDEM is the first such group.  Keeping the class-level CPU routes false makes
# adding an unrelated CPU phase fail closed until its own factory is reviewed.
BACKEND_ROUTES: dict[str, BackendRoute] = {
    "h100_cuda": BackendRoute(
        receipt_backend="azure_ncc40ads_h100_v5",
        operator_adapter="azure/h100_production_orchestrator.py",
        production_operator_available=True,
        reason=None,
    ),
    "cpu_flint_sidecar": BackendRoute(
        receipt_backend="azure_sevsnp_cpu",
        operator_adapter="azure/cpu_production_orchestrator.py",
        production_operator_available=False,
        reason=(
            "the CPU operator requires a campaign-specific source-reviewed "
            "no-shell measured-job materializer"
        ),
    ),
    "cpu_exact_sidecar": BackendRoute(
        receipt_backend="azure_sevsnp_cpu",
        operator_adapter="azure/cpu_production_orchestrator.py",
        production_operator_available=False,
        reason=(
            "the CPU operator requires a campaign-specific source-reviewed "
            "no-shell measured-job materializer"
        ),
    ),
}


# A realization entry means that a concrete receipt-level Lean theorem turns
# the exact registered invocation into the named gpu_prover campaign result.
# A JSON assertion alone is not authority for it. CDEM is the enabled vertical
# slice. claude_math imports that exact source proposition and proves it
# definitionally equivalent to its live ReproducibleTableAbelVerifierOutput.
SOURCE_TG_REALIZATIONS: dict[str, dict[str, str]] = {
    "cdemTableAbelReceiptSourceClaimV2": {
        "campaign_id": "cdem-table-abel",
        "lean_theorem": (
            "SparkInterval.Execution.SignedResultCertificate."
            "certifyCDEMTableAbel"
        ),
        "registered_invocation": "cdemTableAbelProductionV2",
    },
}

# Downstream scope is separate from the source-owned invocation catalog.  A
# source-shaped gpu_prover theorem is not automatically a live claude_math
# provider.  List a stronger scope only after the downstream repository has a
# compiled definition-by-definition theorem for the exact proposition.
SOURCE_TG_DOWNSTREAM_REALIZATION_SCOPES: dict[str, str] = {
    "cdemTableAbelReceiptSourceClaimV2": (
        "claude_math_live_ReproducibleTableAbelVerifierOutput_via_"
        "definition_checked_bridge"
    ),
    "ch25PsiLemma92SourceClaimV1": (
        "claude_math_live_ChirreHelfgottLemma92PsiSource_via_"
        "definition_checked_bridge"
    ),
    "goldbach10Pow27SourceClaimV1": (
        "claude_math_live_FiniteOdd10Pow27Input_via_"
        "definition_checked_bridge"
    ),
    "helfgottPlattGoldbachSourceClaimV1": (
        "claude_math_live_Helfgott_Platt_Theorem_4_1_source_via_"
        "definition_checked_bridge"
    ),
    "helfgottProp1224SourceClaimV1": (
        "claude_math_live_Helfgott_Proposition_12_2_4_source_via_"
        "definition_checked_bridge"
    ),
    "hurstSharedFourResidualRealClaimsV2": (
        "claude_math_live_four_Hurst_Mobius_source_atoms_via_"
        "definition_checked_bridge"
    ),
    "ramareZunigaLemma62SourceClaimV1": (
        "claude_math_live_ramare_zuniga_2024_lemma_6_2_source_via_"
        "definition_checked_bridge"
    ),
    "plattHead2e4SourceClaimV1": (
        "gpu_prover_named_Q128_table_and_conditional_zeta_head_source_claim"
    ),
    "plattTrudgianFiniteRHSourceClaimV1": (
        "gpu_prover_conditional_positive_height_open_strip_zeta_source_claim"
    ),
    "plattDirichletTheorem71SourceClaimV1": (
        "gpu_prover_conditional_Platt_Theorem_7_1_two_branch_source_claim"
    ),
}

# A receipt importer can only bind bytes which the measured terminal job
# actually emitted.  This source-reviewed argument/path contract is separate
# from the editable semantic inventory and from receipt result validation.
# Those execution boundaries may prepare and validate a staged terminal, but
# all boundaries plus separately reviewed receipt admission must agree before
# the result can become theorem authority.
SOURCE_TG_TERMINAL_RESULTS: dict[str, TerminalResultBinding] = {
    "cdemTableAbelReceiptSourceClaimV2": TerminalResultBinding(
        argument="--registered-result-output",
        artifact_template=(
            "${TG_RUN_ROOT}/cdem-table-abel/registered-result.txt"
        ),
    ),
    "ch25PsiLemma92SourceClaimV1": TerminalResultBinding(
        argument="--registered-result-output",
        artifact_template=(
            "${TG_RUN_ROOT}/ch25-psi-1e13/registered-result.txt"
        ),
    ),
    "ch25A7BoundarySourceClaimV1": TerminalResultBinding(
        argument="--registered-result-output",
        artifact_template=(
            "${TG_RUN_ROOT}/ch25-a7-boundary/registered-result.txt"
        ),
    ),
    "helfgottProp1224SourceClaimV1": TerminalResultBinding(
        argument="--registered-result-output",
        artifact_template=(
            "${TG_RUN_ROOT}/helfgott-prop-12-2-4/registered-result.txt"
        ),
    ),
    "goldbach10Pow27SourceClaimV1": TerminalResultBinding(
        argument="--registered-result-output",
        artifact_template=(
            "${TG_RUN_ROOT}/goldbach-finite-below-10pow27/registered-result.txt"
        ),
    ),
    "helfgottPlattGoldbachSourceClaimV1": TerminalResultBinding(
        argument="--registered-result-output",
        artifact_template=(
            "${TG_RUN_ROOT}/helfgott-platt-theorem-4-1/registered-result.txt"
        ),
    ),
    "ramareZunigaLemma62SourceClaimV1": TerminalResultBinding(
        argument="--registered-result-output",
        artifact_template=(
            "${TG_RUN_ROOT}/ramare-zuniga-lemma-6-2/registered-result.txt"
        ),
    ),
    "hurstSharedFourResidualRealClaimsV2": TerminalResultBinding(
        argument="--registered-result-output",
        artifact_template=(
            "${TG_RUN_ROOT}/mertens-hurst/registered-result.txt"
        ),
    ),
    "plattHead2e4SourceClaimV1": TerminalResultBinding(
        argument="--registered-result-output",
        artifact_template=(
            "${TG_RUN_ROOT}/platt-head-2e4/registered-result.txt"
        ),
    ),
    "plattTrudgianFiniteRHSourceClaimV1": TerminalResultBinding(
        argument="--registered-result-output",
        artifact_template=(
            "${TG_RUN_ROOT}/platt-trudgian-rh-3e12/registered-result.txt"
        ),
    ),
    "plattDirichletTheorem71SourceClaimV1": TerminalResultBinding(
        argument="--registered-result-output",
        artifact_template=(
            "${TG_RUN_ROOT}/platt-dirichlet-theorem-7-1/"
            "registered-result.txt"
        ),
    ),
}

# Reviewed execution shape only: this catalog may authorize the exact
# invocation/result contract used to prepare a terminal and validate its
# returned receipt, but it is deliberately never theorem authority. Every
# disabled row below has a closed theorem/import identity and an exact terminal
# command which emits its registered result; none is thereby an analytic
# realization or a completed production run. Only after retained physical
# evidence is reviewed against the formal ``Runs`` premise may an unchanged
# entry move into ``SOURCE_TG_REALIZATIONS`` and its inventory row be flipped.
PENDING_TG_REALIZATIONS: dict[str, dict[str, str]] = {
    "ch25A7BoundarySourceClaimV1": {
        "campaign_id": "ch25-a7-boundary",
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "ch25A7BoundaryProductionV1_sourceClaim"
        ),
        "registered_invocation": "ch25A7BoundaryProductionV1",
    },
    "ramareZunigaLemma62SourceClaimV1": {
        "campaign_id": "ramare-zuniga-lemma-6-2",
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "ramareZunigaLemma62ProductionV1_sourceClaim"
        ),
        "registered_invocation": "ramareZunigaLemma62ProductionV1",
    },
    "ch25PsiLemma92SourceClaimV1": {
        "campaign_id": "ch25-psi-two-pass-v1",
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "ch25PsiLemma92ProductionV1_sourceClaim"
        ),
        "registered_invocation": "ch25PsiLemma92ProductionV1",
    },
    "hurstSharedFourResidualRealClaimsV2": {
        "campaign_id": "hurst-four-residuals-v1",
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "hurstSharedFourResidualProductionV2_realClaims"
        ),
        "registered_invocation": "hurstSharedFourResidualProductionV2",
    },
    "helfgottProp1224SourceClaimV1": {
        "campaign_id": "helfgott-prop-12-2-4-mpfr-v1",
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "helfgottProp1224ProductionV1_sourceClaim"
        ),
        "registered_invocation": "helfgottProp1224ProductionV1",
    },
    "goldbach10Pow27SourceClaimV1": {
        "campaign_id": GOLDBACH_10POW27_CAMPAIGN,
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "goldbach10Pow27ProductionV1_sourceClaim"
        ),
        "registered_invocation": "goldbach10Pow27ProductionV1",
    },
    "helfgottPlattGoldbachSourceClaimV1": {
        "campaign_id": HISTORICAL_GOLDBACH_CAMPAIGN,
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "helfgottPlattGoldbachProductionV1_sourceClaim"
        ),
        "registered_invocation": "helfgottPlattGoldbachProductionV1",
    },
    "plattHead2e4SourceClaimV1": {
        "campaign_id": "platt-head-2e4",
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "plattHead2e4ProductionV1_sourceClaim"
        ),
        "registered_invocation": "plattHead2e4ProductionV1",
    },
    "plattTrudgianFiniteRHSourceClaimV1": {
        "campaign_id": "platt-trudgian-rh-3e12",
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "plattTrudgianFiniteRHProductionV1_sourceClaim"
        ),
        "registered_invocation": "plattTrudgianFiniteRHProductionV1",
    },
    "plattDirichletTheorem71SourceClaimV1": {
        "campaign_id": "platt-dirichlet-theorem-7-1",
        "lean_theorem": (
            "SparkInterval.Execution.RegisteredInvocation."
            "plattDirichletTheorem71ProductionV1_sourceClaim"
        ),
        "registered_invocation": "plattDirichletTheorem71ProductionV1",
    },
}


def _current_production_budget_gate(
    price_class: str, required_campaign_ids: tuple[str, ...]
) -> dict[str, Any]:
    """Re-evaluate the hard gate for exactly one completion profile.

    The sizing report intentionally inventories every physical capability.
    Reusing its aggregate gate would make the lowered profile depend on the
    deliberately excluded historical Goldbach campaign.  Instead, this
    function reconstructs the source route records, filters them to the exact
    source-owned profile, and invokes the same fail-closed optimizer again.
    """

    if price_class not in {"pay_as_you_go", "spot"}:
        raise PortfolioError("production price class must be pay_as_you_go or spot")
    from tg_verifier.azure_production_sizing import (  # Local to avoid an import cycle.
        build_sizing_report,
    )

    report = build_sizing_report()
    try:
        optimizer = report["backend_optimizer"]
        capability_ids = optimizer["physical_campaign_ids"]
        budget = optimizer["production_budget"]
        max_wall = Decimal(budget["hard_max_wall_hours"])
        max_cost = Decimal(budget["hard_max_cost_usd"])
        high_control = budget["high_endpoints_control"]
        deadline_raw = optimizer["deadline_hours"]
        resource_caps = optimizer["resource_caps"]
        route_rows = optimizer["route_matrix"]
        price_snapshot = optimizer["price_snapshot"]
        report_schema = report["schema"]
        snapshot_date = price_snapshot["date"]
    except (KeyError, TypeError, InvalidOperation, ValueError) as error:
        raise PortfolioError(
            "Azure sizing report does not expose the reviewed production gate"
        ) from error
    if (
        not isinstance(capability_ids, list)
        or tuple(capability_ids) != CAPABILITY_CAMPAIGN_IDS
        or not isinstance(required_campaign_ids, tuple)
        or not required_campaign_ids
        or len(required_campaign_ids) != len(set(required_campaign_ids))
        or any(item not in CAPABILITY_CAMPAIGN_IDS for item in required_campaign_ids)
        or max_wall <= 0
        or max_wall > Decimal("168")
        or max_cost <= 0
        or max_cost > Decimal("10000")
        or high_control is not True
        or not isinstance(route_rows, list)
        or not isinstance(resource_caps, dict)
        or not isinstance(price_snapshot, dict)
    ):
        raise PortfolioError("Azure sizing production gate weakens the hard release limits")

    route_fields = {
        "basis",
        "campaign_id",
        "configuration_class",
        "cost_usd",
        "deadline_feasible",
        "demands",
        "optimizer_eligible",
        "production_gate",
        "readiness",
        "route_id",
        "schedule",
        "unavailable_reason",
    }
    demand_fields = {
        "basis",
        "calibrated",
        "calibration_scope",
        "default_nodes",
        "evidence_id",
        "node_hours_high",
        "node_hours_low",
        "parallelism_cap",
        "resource_class",
        "target_sku_measured",
    }

    def decimal_string(value: Any, what: str) -> Decimal:
        if not isinstance(value, str):
            raise PortfolioError(f"{what} must be a decimal string")
        try:
            result = Decimal(value)
        except InvalidOperation as error:
            raise PortfolioError(f"{what} is not a decimal string") from error
        if not result.is_finite():
            raise PortfolioError(f"{what} must be finite")
        return result

    routes: list[CampaignRoute] = []
    selected = set(required_campaign_ids)
    for index, raw_route in enumerate(route_rows):
        row = _exact(raw_route, route_fields, f"sizing route {index}")
        campaign_id = _name(row["campaign_id"], f"sizing route {index} campaign")
        if campaign_id not in selected:
            continue
        raw_demands = row["demands"]
        if not isinstance(raw_demands, list):
            raise PortfolioError(f"sizing route {index} demands are not a list")
        demands: list[ResourceDemand] = []
        for demand_index, raw_demand in enumerate(raw_demands):
            demand = _exact(
                raw_demand,
                demand_fields,
                f"sizing route {index} demand {demand_index}",
            )
            if (
                not isinstance(demand["basis"], str)
                or not isinstance(demand["calibrated"], bool)
                or not isinstance(demand["calibration_scope"], str)
                or not isinstance(demand["evidence_id"], str)
                or not isinstance(demand["resource_class"], str)
                or not isinstance(demand["target_sku_measured"], bool)
            ):
                raise PortfolioError(
                    f"sizing route {index} demand {demand_index} has malformed metadata"
                )
            demands.append(
                ResourceDemand(
                    resource_class=demand["resource_class"],
                    node_hours_low=decimal_string(
                        demand["node_hours_low"], "sizing demand low node-hours"
                    ),
                    node_hours_high=decimal_string(
                        demand["node_hours_high"], "sizing demand high node-hours"
                    ),
                    default_nodes=_integer(
                        demand["default_nodes"],
                        "sizing demand default nodes",
                        minimum=1,
                        maximum=10**6,
                    ),
                    parallelism_cap=_integer(
                        demand["parallelism_cap"],
                        "sizing demand parallelism cap",
                        minimum=1,
                        maximum=10**6,
                    ),
                    evidence_id=demand["evidence_id"],
                    calibrated=demand["calibrated"],
                    calibration_scope=demand["calibration_scope"],
                    target_sku_measured=demand["target_sku_measured"],
                    basis=demand["basis"],
                )
            )
        unavailable_reason = row["unavailable_reason"]
        if unavailable_reason is not None and not isinstance(unavailable_reason, str):
            raise PortfolioError(f"sizing route {index} unavailable reason is malformed")
        for field in ("basis", "configuration_class", "readiness", "route_id"):
            if not isinstance(row[field], str):
                raise PortfolioError(f"sizing route {index} {field} is malformed")
        routes.append(
            CampaignRoute(
                campaign_id=campaign_id,
                route_id=row["route_id"],
                configuration_class=row["configuration_class"],
                readiness=row["readiness"],
                demands=tuple(demands),
                basis=row["basis"],
                unavailable_reason=unavailable_reason,
            )
        )

    try:
        deadline = (
            None
            if deadline_raw is None
            else decimal_string(deadline_raw, "sizing deadline")
        )
        profile_optimizer = optimize_backend_catalog(
            physical_campaign_ids=required_campaign_ids,
            routes=tuple(routes),
            h100_prices={
                name: decimal_string(value, f"H100 {name} price")
                for name, value in price_snapshot[
                    "ncc40ads_h100_v5_usd_per_node_hour"
                ].items()
            },
            cpu_prices={
                name: decimal_string(value, f"CPU {name} price")
                for name, value in price_snapshot[
                    "dc96as_v6_usd_per_node_hour"
                ].items()
            },
            deadline_hours=deadline,
            max_cpu_nodes=_integer(
                resource_caps["dc96_cpu_nodes"],
                "sizing CPU node cap",
                minimum=1,
                maximum=10**6,
            ),
            max_h100_nodes=_integer(
                resource_caps["ncc_h100_nodes"],
                "sizing H100 node cap",
                minimum=1,
                maximum=10**6,
            ),
            production_max_wall_hours=max_wall,
            production_max_cost_usd=max_cost,
        )
        gate = profile_optimizer["configuration_comparison"]["mixed_flexible"][
            price_class
        ]["production_gate"]
        ready = gate["production_ready"]
        blockers = gate["campaign_blockers"]
        portfolio_cost = gate["portfolio_high_cost_usd"]
        portfolio_wall = gate["portfolio_high_wall_hours"]
    except (KeyError, TypeError, ValueError) as error:
        raise PortfolioError(
            "Azure sizing routes cannot be re-evaluated for the selected profile"
        ) from error
    if not isinstance(ready, bool) or not isinstance(blockers, list):
        raise PortfolioError("profile sizing gate is internally malformed")
    blocker_ids = sorted(
        {
            row.get("campaign_id")
            for row in blockers
            if isinstance(row, dict) and isinstance(row.get("campaign_id"), str)
        }
    )
    if ready and blockers:
        raise PortfolioError("Azure sizing gate is internally inconsistent")
    return {
        "blocking_campaign_ids": blocker_ids,
        "covered_campaign_ids": list(required_campaign_ids),
        "hard_max_cost_usd": str(max_cost),
        "hard_max_wall_hours": str(max_wall),
        "high_endpoints_control": True,
        "portfolio_high_cost_usd": portfolio_cost,
        "portfolio_high_wall_hours": portfolio_wall,
        "price_class": price_class,
        "production_ready": ready,
        "report_schema": report_schema,
        "snapshot_date": snapshot_date,
    }


@dataclass(frozen=True)
class PortfolioContext:
    spec_path: Path
    spec: dict[str, Any]
    spec_sha256: str
    repository_root: Path
    run_root: Path
    cluster_manifest: dict[str, Any]
    semantic_bindings: dict[str, Any]
    verifier_key_manifest: Path
    plan: dict[str, Any]

    @property
    def plan_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.plan))


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise PortfolioError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, unexpected={sorted(actual - fields)})"
        )
    return value


def _name(value: Any, what: str) -> str:
    if not isinstance(value, str) or NAME_RE.fullmatch(value) is None:
        raise PortfolioError(f"{what} is not a canonical identifier")
    return value


def _sha256(value: Any, what: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise PortfolioError(f"{what} is not lowercase SHA-256")
    return value


def _integer(value: Any, what: str, *, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise PortfolioError(f"{what} must be in [{minimum}, {maximum}]")
    return value


def _absolute_path(value: Any, what: str, *, may_not_exist: bool) -> Path:
    if not isinstance(value, str) or not value:
        raise PortfolioError(f"{what} must be a nonempty absolute path")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise PortfolioError(f"{what} must be absolute and contain no '..'")
    try:
        return path.resolve(strict=not may_not_exist)
    except OSError as error:
        raise PortfolioError(f"cannot resolve {what}: {error}") from error


def _relative_repository_path(value: Any, what: str) -> Path:
    if not isinstance(value, str) or not value:
        raise PortfolioError(f"{what} must be a nonempty repository-relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise PortfolioError(f"{what} escapes or is not canonical")
    return path


def _canonical_file(path: Path, what: str) -> tuple[Any, bytes]:
    try:
        raw = read_bytes_once(path)
        value = load_json(path, require_canonical=True)
    except (CampaignIOError, OSError, ValueError) as error:
        raise PortfolioError(f"cannot load canonical {what}: {error}") from error
    return value, raw


def _absolute_pin(value: Any, what: str) -> tuple[dict[str, Any], Path]:
    pin = _exact(value, ABSOLUTE_PIN_FIELDS, what)
    declared_path = Path(pin["path"]) if isinstance(pin["path"], str) else Path()
    if declared_path.is_symlink():
        raise PortfolioError(f"{what} must not be a symlink")
    path = _absolute_path(pin["path"], f"{what} path", may_not_exist=False)
    expected_hash = _sha256(pin["sha256"], f"{what} SHA-256")
    expected_size = _integer(
        pin["size_bytes"], f"{what} size", minimum=0, maximum=2**63 - 1
    )
    try:
        actual_hash, actual_size = hash_file_once(path)
    except CampaignIOError as error:
        raise PortfolioError(str(error)) from error
    if (actual_hash, actual_size) != (expected_hash, expected_size):
        raise PortfolioError(f"{what} differs from its exact file pin")
    return pin, path


def _repository_pin(
    value: Any,
    what: str,
    *,
    repository_root: Path,
    repository_binding: Mapping[str, Any],
) -> tuple[dict[str, Any], Path]:
    pin = _exact(value, REPOSITORY_PIN_FIELDS, what)
    relative = _relative_repository_path(pin["path"], f"{what} path")
    expected_hash = _sha256(pin["sha256"], f"{what} SHA-256")
    expected_size = _integer(
        pin["size_bytes"], f"{what} size", minimum=0, maximum=2**63 - 1
    )
    rows = {
        row["path"]: row
        for row in repository_binding["files"]
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    row = rows.get(relative.as_posix())
    if row != {
        "path": relative.as_posix(),
        "sha256": expected_hash,
        "size_bytes": expected_size,
    }:
        raise PortfolioError(
            f"{what} is not pinned by the cluster manifest's complete clean-repository closure"
        )
    declared_path = repository_root / relative
    if declared_path.is_symlink():
        raise PortfolioError(f"{what} must not be a symlink")
    path = declared_path.resolve(strict=True)
    try:
        path.relative_to(repository_root)
    except ValueError as error:
        raise PortfolioError(f"{what} escapes through a symlink") from error
    actual_hash, actual_size = hash_file_once(path)
    if (actual_hash, actual_size) != (expected_hash, expected_size):
        raise PortfolioError(f"{what} bytes differ from the repository closure")
    return pin, path


def _validate_semantic_bindings(value: Any) -> dict[str, Any]:
    registry = _exact(value, SEMANTIC_FIELDS, "semantic binding registry")
    if (
        registry["kind"] != SEMANTIC_REGISTRY_KIND
        or registry["schema_version"] != SCHEMA_VERSION
        or not isinstance(registry["bindings"], list)
    ):
        raise PortfolioError("unsupported semantic binding registry")
    campaign_ids: list[str] = []
    for index, raw in enumerate(registry["bindings"]):
        row = _exact(raw, SEMANTIC_BINDING_FIELDS, f"semantic binding {index}")
        campaign_ids.append(_name(row["campaign_id"], f"semantic binding {index} campaign"))
        if not isinstance(row["enabled"], bool):
            raise PortfolioError(f"semantic binding {index} enabled must be Boolean")
        for field in ("registered_invocation", "realization_id"):
            item = row[field]
            if item is not None:
                _name(item, f"semantic binding {index} {field}")
        theorem = row["lean_theorem"]
        if theorem is not None and (
            not isinstance(theorem, str) or LEAN_DECL_RE.fullmatch(theorem) is None
        ):
            raise PortfolioError(
                f"semantic binding {index} lean_theorem is not a qualified Lean name"
            )
        if row["enabled"] and any(
            row[field] is None
            for field in ("registered_invocation", "realization_id", "lean_theorem")
        ):
            raise PortfolioError(
                f"enabled semantic binding {index} is not fully populated"
            )
        populated = [
            row[field] is not None
            for field in ("registered_invocation", "realization_id", "lean_theorem")
        ]
        if not row["enabled"] and any(populated) and not all(populated):
            raise PortfolioError(
                f"disabled semantic binding {index} must stage all identity fields or none"
            )
    if campaign_ids != sorted(campaign_ids) or len(campaign_ids) != len(set(campaign_ids)):
        raise PortfolioError("semantic bindings must be sorted by unique campaign id")
    return registry


def completion_profile_inventory() -> dict[str, Any]:
    """Return the immutable source-owned theorem-route inventory."""

    return {
        "accepted": False,
        "classification": "source_owned_portfolio_profiles_not_execution_evidence",
        "profiles": [
            {
                "excluded_campaigns": [
                    {"campaign_id": campaign_id, "reason": reason}
                    for campaign_id, reason in profile.excluded_campaign_reasons
                ],
                "profile_id": profile.profile_id,
                "purpose": profile.purpose,
                "required_campaign_ids": list(profile.required_campaign_ids),
            }
            for profile in COMPLETION_PROFILES.values()
        ],
        "schema_version": SCHEMA_VERSION,
    }


def _select_completion_profile(
    cluster: Mapping[str, Any], profile_id: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate and select one exact theorem route from the full manifest.

    This does not trust the manifest to say which campaigns suffice.  It first
    checks the manifest's entire campaign-to-claim partition against the
    source-owned inventory above, then checks that every dependency of a
    selected campaign is also selected.  Only afterward is a compact cluster
    view constructed for DAG expansion.
    """

    identifier = _name(profile_id, "completion profile")
    try:
        profile = COMPLETION_PROFILES[identifier]
    except KeyError as error:
        raise PortfolioError(
            "unknown completion profile; choose one of "
            + ", ".join(COMPLETION_PROFILES)
        ) from error

    campaigns = cluster.get("physical_campaigns")
    if not isinstance(campaigns, list):
        raise PortfolioError("cluster manifest has no physical campaign inventory")
    actual_ids = tuple(
        row.get("campaign_id") if isinstance(row, dict) else None
        for row in campaigns
    )
    if actual_ids != CAPABILITY_CAMPAIGN_IDS:
        raise PortfolioError(
            "cluster physical campaign inventory differs from the independently "
            "reviewed completion-profile inventory"
        )
    expected_claims = dict(CAPABILITY_CAMPAIGN_LOGICAL_CLAIMS)
    atom_campaign: dict[str, str] = {}
    for campaign in campaigns:
        campaign_id = campaign["campaign_id"]
        actual_claims = campaign.get("logical_atom_ids")
        if actual_claims != list(expected_claims[campaign_id]):
            raise PortfolioError(
                f"{campaign_id} logical claims differ from the reviewed profile boundary"
            )
        for claim_id in actual_claims:
            if claim_id in atom_campaign:
                raise PortfolioError(
                    f"logical claim {claim_id} belongs to multiple physical campaigns"
                )
            atom_campaign[claim_id] = campaign_id

    required = set(profile.required_campaign_ids)
    expected_excluded = set(CAPABILITY_CAMPAIGN_IDS) - required
    declared_excluded = {
        campaign_id for campaign_id, _reason in profile.excluded_campaign_reasons
    }
    if (
        len(required) != len(profile.required_campaign_ids)
        or declared_excluded != expected_excluded
        or len(declared_excluded) != len(profile.excluded_campaign_reasons)
    ):
        raise PortfolioError("source completion profile is internally inconsistent")

    selected_edges: list[dict[str, Any]] = []
    edges = cluster.get("dependency_edges")
    if not isinstance(edges, list):
        raise PortfolioError("cluster manifest has no dependency edge inventory")
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            raise PortfolioError(f"cluster dependency edge {index} is not an object")
        source_claim = edge.get("from")
        target_claim = edge.get("to")
        if source_claim not in atom_campaign or target_claim not in atom_campaign:
            raise PortfolioError(
                f"cluster dependency edge {index} names an unreviewed logical claim"
            )
        source_campaign = atom_campaign[source_claim]
        target_campaign = atom_campaign[target_claim]
        if target_campaign in required and source_campaign not in required:
            raise PortfolioError(
                f"completion profile {identifier} omits prerequisite campaign "
                f"{source_campaign} required by {target_campaign}"
            )
        if source_campaign in required and target_campaign in required:
            selected_edges.append(edge)

    selected_campaigns = [
        campaign for campaign in campaigns if campaign["campaign_id"] in required
    ]
    selected_claims = [
        claim_id
        for campaign_id, claims in CAPABILITY_CAMPAIGN_LOGICAL_CLAIMS
        if campaign_id in required
        for claim_id in claims
    ]
    selected_cluster = dict(cluster)
    selected_cluster["physical_campaigns"] = selected_campaigns
    selected_cluster["dependency_edges"] = selected_edges
    profile_record = {
        "excluded_campaigns": [
            {"campaign_id": campaign_id, "reason": reason}
            for campaign_id, reason in profile.excluded_campaign_reasons
        ],
        "profile_id": profile.profile_id,
        "purpose": profile.purpose,
        "required_campaign_ids": list(profile.required_campaign_ids),
        "required_logical_claim_ids": selected_claims,
        "selection_authority": "source_owned_exact_profile_not_manifest_allow_list",
    }
    return profile_record, selected_cluster


def _phase_groups(cluster: Mapping[str, Any]) -> list[dict[str, Any]]:
    jobs = {job["atom_id"]: job for job in cluster["jobs"]}
    groups: list[dict[str, Any]] = []
    campaign_groups: dict[str, list[str]] = {}
    local_dependencies: dict[str, list[str]] = {}

    for campaign in cluster["physical_campaigns"]:
        campaign_id = campaign["campaign_id"]
        owner_atom = campaign["owner_atom_id"]
        owner = jobs[owner_atom]
        phases = list(campaign["phase_dag"])
        if not phases:
            phases = [
                {
                    "phase_id": "single-job",
                    "command": owner["command"],
                    "depends_on": [],
                    "array_size": 1,
                    "backend_class": owner["backend_class"],
                    "resources": owner["resources"],
                }
            ]
        if owner["postcheck_command"]:
            phase_ids = {phase["phase_id"] for phase in phases}
            depended = {
                item for phase in phases for item in phase.get("depends_on", [])
            }
            leaves = sorted(phase_ids - depended)
            phases.append(
                {
                    "phase_id": "postcheck",
                    "command": owner["postcheck_command"],
                    "depends_on": leaves,
                    "array_size": 1,
                    "backend_class": "cpu_exact_sidecar",
                    "resources": {
                        "cpus_per_task": owner["resources"]["cpus_per_task"],
                        "h100_gpus": 0,
                    },
                }
            )

        identifiers: list[str] = []
        for phase in phases:
            phase_id = phase["phase_id"]
            group_id = f"{campaign_id}::{phase_id}"
            if GROUP_RE.fullmatch(group_id) is None:
                raise PortfolioError(f"derived group id is not canonical: {group_id}")
            backend_class = phase["backend_class"]
            try:
                route = BACKEND_ROUTES[backend_class]
            except KeyError as error:
                raise PortfolioError(f"no Azure backend route for {backend_class}") from error
            command = phase["command"]
            if not isinstance(command, list) or not command or not all(
                isinstance(token, str) and token for token in command
            ):
                raise PortfolioError(f"{group_id} has no exact argv template")
            shard_count = _integer(
                phase.get("array_size", 1),
                f"{group_id} shard count",
                minimum=1,
                maximum=10**9,
            )
            if shard_count > 1 and not any(
                "${TG_ARRAY_INDEX}" in token for token in command
            ):
                raise PortfolioError(
                    f"{group_id} is an array but its argv does not bind TG_ARRAY_INDEX"
                )
            groups.append(
                {
                    "backend_class": backend_class,
                    "campaign_id": campaign_id,
                    "command_template": command,
                    "depends_on": [],
                    "group_id": group_id,
                    "operator_adapter": route.operator_adapter,
                    "owner_atom_id": owner_atom,
                    "phase_id": phase_id,
                    "receipt_backend": route.receipt_backend,
                    "shard_count": shard_count,
                    "terminal": False,
                }
            )
            identifiers.append(group_id)
            local_dependencies[group_id] = [
                f"{campaign_id}::{dependency}"
                for dependency in phase.get("depends_on", [])
            ]
        campaign_groups[campaign_id] = identifiers

    group_by_id = {group["group_id"]: group for group in groups}
    if len(group_by_id) != len(groups):
        raise PortfolioError("derived portfolio contains duplicate group ids")
    for group_id, dependencies in local_dependencies.items():
        if any(dependency not in group_by_id for dependency in dependencies):
            raise PortfolioError(f"{group_id} has an unknown phase dependency")
        group_by_id[group_id]["depends_on"] = sorted(set(dependencies))

    terminal_by_campaign: dict[str, str] = {}
    roots_by_campaign: dict[str, list[str]] = {}
    for campaign_id, identifiers in campaign_groups.items():
        depended = {
            dependency
            for identifier in identifiers
            for dependency in group_by_id[identifier]["depends_on"]
        }
        leaves = sorted(set(identifiers) - depended)
        roots = sorted(
            identifier
            for identifier in identifiers
            if not group_by_id[identifier]["depends_on"]
        )
        if len(leaves) != 1 or not roots:
            raise PortfolioError(
                f"physical campaign {campaign_id} must have one terminal and at least one root group"
            )
        terminal_by_campaign[campaign_id] = leaves[0]
        roots_by_campaign[campaign_id] = roots
        group_by_id[leaves[0]]["terminal"] = True

    atom_campaign = {
        atom_id: campaign["campaign_id"]
        for campaign in cluster["physical_campaigns"]
        for atom_id in campaign["logical_atom_ids"]
    }
    for edge in cluster["dependency_edges"]:
        source_campaign = atom_campaign[edge["from"]]
        target_campaign = atom_campaign[edge["to"]]
        if source_campaign == target_campaign:
            continue
        source = terminal_by_campaign[source_campaign]
        for target in roots_by_campaign[target_campaign]:
            group_by_id[target]["depends_on"] = sorted(
                set(group_by_id[target]["depends_on"] + [source])
            )

    return _topological_groups(list(group_by_id.values()))


def _topological_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {group["group_id"]: group for group in groups}
    remaining = {
        identifier: set(group["depends_on"]) for identifier, group in by_id.items()
    }
    ordered: list[dict[str, Any]] = []
    while remaining:
        ready = sorted(identifier for identifier, deps in remaining.items() if not deps)
        if not ready:
            raise PortfolioError("portfolio dependency graph contains a cycle")
        for identifier in ready:
            ordered.append(by_id[identifier])
            del remaining[identifier]
        for dependencies in remaining.values():
            dependencies.difference_update(ready)
    return ordered


def _bind_group_operator_capability(group: dict[str, Any]) -> None:
    """Attach the exact direct/operator+materializer route for one group."""

    route = BACKEND_ROUTES[group["backend_class"]]
    if route.receipt_backend == "azure_ncc40ads_h100_v5":
        if group["campaign_id"] == GOLDBACH_10POW27_CAMPAIGN:
            if goldbach10pow27_h100_materializer_shape_available(group):
                group["materializer_adapter"] = (
                    "tools/tg_azure_h100_goldbach_10pow27_materializer.py"
                )
                group["production_operator_available"] = True
                group["production_route_reason"] = None
            else:
                group["materializer_adapter"] = None
                group["production_operator_available"] = False
                group["production_route_reason"] = (
                    "the lowered Goldbach H100 phase must match its exact "
                    "source-reviewed materializer contract"
                )
            return
        if group["campaign_id"] == HISTORICAL_GOLDBACH_CAMPAIGN:
            if historical_goldbach_h100_materializer_shape_available(group):
                group["materializer_adapter"] = (
                    "tools/tg_azure_h100_goldbach_historical_materializer.py"
                )
                group["production_operator_available"] = True
                group["production_route_reason"] = None
            else:
                group["materializer_adapter"] = None
                group["production_operator_available"] = False
                group["production_route_reason"] = (
                    "the source-height historical Goldbach H100 phase must "
                    "match its exact source-reviewed materializer contract"
                )
            return
        if group["campaign_id"] == R2STAR_CAMPAIGN_ID:
            if r2star_h100_materializer_available(group):
                group["materializer_adapter"] = (
                    "tools/tg_azure_h100_r2star_materializer.py"
                )
                group["production_operator_available"] = True
                group["production_route_reason"] = None
            else:
                group["materializer_adapter"] = None
                group["production_operator_available"] = False
                group["production_route_reason"] = (
                    "the Ramaré--Zúñiga H100 terminal must match its exact "
                    "fresh-workspace source-reviewed materializer contract"
                )
            return
    if route.production_operator_available:
        group["materializer_adapter"] = None
        group["production_operator_available"] = True
        group["production_route_reason"] = None
        return
    materializer = None
    if route.receipt_backend == "azure_sevsnp_cpu":
        if cdem_materializer_available(group):
            materializer = "tools/tg_azure_cpu_portfolio_materializer.py"
        elif psi_materializer_available(group):
            materializer = "tools/tg_azure_cpu_psi_materializer.py"
        elif (
            hurst_materializer_available(group)
            or hurst_affine_materializer_available(group)
        ):
            materializer = "tools/tg_azure_cpu_hurst_materializer.py"
        elif platt_head_materializer_available(group):
            materializer = "tools/tg_azure_cpu_platt_head_materializer.py"
        elif platt_pt21_materializer_available(group):
            materializer = "tools/tg_azure_cpu_platt_pt21_materializer.py"
        elif a7_materializer_available(group):
            materializer = "tools/tg_azure_cpu_a7_materializer.py"
        elif prop1224_materializer_available(group):
            materializer = "tools/tg_azure_cpu_prop1224_materializer.py"
        elif goldbach10pow27_materializer_available(group):
            materializer = "tools/tg_azure_cpu_goldbach_10pow27_materializer.py"
        elif historical_goldbach_materializer_available(group):
            materializer = (
                "tools/tg_azure_cpu_goldbach_historical_materializer.py"
            )
        elif historical_goldbach_operational_materializer_available(group):
            materializer = (
                "tools/tg_azure_cpu_goldbach_historical_operational_materializer.py"
            )
        elif dirichlet_materializer_available(group):
            materializer = "tools/tg_azure_cpu_dirichlet_materializer.py"
    if materializer is not None:
        group["materializer_adapter"] = materializer
        group["production_operator_available"] = True
        group["production_route_reason"] = None
        return
    group["materializer_adapter"] = None
    group["production_operator_available"] = False
    group["production_route_reason"] = (
        dirichlet_postcheck_materializer_blocker(group)
        or CPU_MATERIALIZER_GAPS.get(group["campaign_id"], route.reason)
    )


def build_plan(
    spec: Mapping[str, Any],
    cluster: Mapping[str, Any],
    semantic_registry: Mapping[str, Any],
    *,
    realization_catalog: Mapping[str, Mapping[str, str]] | None = None,
    terminal_result_catalog: Mapping[str, TerminalResultBinding] | None = None,
    production_budget_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the deterministic local portfolio plan and enumerate all gaps."""

    profile_record, selected_cluster = _select_completion_profile(
        cluster, spec["completion_profile"]
    )
    selected_campaign_ids = tuple(profile_record["required_campaign_ids"])
    catalog = (
        SOURCE_TG_REALIZATIONS
        if realization_catalog is None
        else realization_catalog
    )
    result_catalog = (
        SOURCE_TG_TERMINAL_RESULTS
        if terminal_result_catalog is None
        else terminal_result_catalog
    )
    budget_gate = dict(
        _current_production_budget_gate(
            spec["production_price_class"], selected_campaign_ids
        )
        if production_budget_gate is None
        else production_budget_gate
    )
    expected_budget_fields = {
        "blocking_campaign_ids",
        "covered_campaign_ids",
        "hard_max_cost_usd",
        "hard_max_wall_hours",
        "high_endpoints_control",
        "portfolio_high_cost_usd",
        "portfolio_high_wall_hours",
        "price_class",
        "production_ready",
        "report_schema",
        "snapshot_date",
    }
    _exact(budget_gate, expected_budget_fields, "production budget gate")
    try:
        hard_wall = Decimal(budget_gate["hard_max_wall_hours"])
        hard_cost = Decimal(budget_gate["hard_max_cost_usd"])
    except (InvalidOperation, TypeError, ValueError) as error:
        raise PortfolioError("production budget gate limits are not decimal strings") from error
    if (
        budget_gate["price_class"] != spec["production_price_class"]
        or budget_gate["high_endpoints_control"] is not True
        or not Decimal("0") < hard_wall <= Decimal("168")
        or not Decimal("0") < hard_cost <= Decimal("10000")
        or not isinstance(budget_gate["production_ready"], bool)
        or not isinstance(budget_gate["blocking_campaign_ids"], list)
        or not isinstance(budget_gate["covered_campaign_ids"], list)
        or not all(
            isinstance(campaign_id, str) and NAME_RE.fullmatch(campaign_id)
            for campaign_id in budget_gate["covered_campaign_ids"]
        )
        or len(budget_gate["covered_campaign_ids"])
        != len(set(budget_gate["covered_campaign_ids"]))
    ):
        raise PortfolioError("production budget gate is not the requested hard gate")
    groups = _phase_groups(selected_cluster)
    for group in groups:
        _bind_group_operator_capability(group)
    bindings = {row["campaign_id"]: row for row in semantic_registry["bindings"]}
    campaign_ids = list(selected_campaign_ids)
    gaps: list[dict[str, Any]] = []

    sizing_ids = set(budget_gate["covered_campaign_ids"])
    for missing in sorted(set(campaign_ids) - sizing_ids):
        gaps.append(
            {
                "campaign_id": missing,
                "code": "production_sizing_absent",
                "detail": (
                    "the hard one-week/$10k sizing model does not classify this "
                    "versioned physical campaign"
                ),
            }
        )
    for stale in sorted(sizing_ids - set(campaign_ids)):
        gaps.append(
            {
                "campaign_id": stale,
                "code": "production_sizing_stale_campaign",
                "detail": "the sizing model names no physical campaign in this manifest",
            }
        )

    if not budget_gate["production_ready"]:
        gaps.append(
            {
                "campaign_id": "portfolio",
                "code": "production_budget_gate_failed",
                "detail": (
                    f"price_class={budget_gate['price_class']}; "
                    f"blocking_campaign_ids={budget_gate['blocking_campaign_ids']}; "
                    f"high_wall_hours={budget_gate['portfolio_high_wall_hours']}; "
                    f"high_cost_usd={budget_gate['portfolio_high_cost_usd']}"
                ),
            }
        )

    for campaign_id in campaign_ids:
        unavailable_groups = [
            group["group_id"]
            for group in groups
            if group["campaign_id"] == campaign_id
            and not group["production_operator_available"]
        ]
        if unavailable_groups:
            reasons = sorted(
                {
                    group["production_route_reason"]
                    for group in groups
                    if group["group_id"] in unavailable_groups
                }
            )
            gaps.append(
                {
                    "campaign_id": campaign_id,
                    "code": "production_backend_operator_absent",
                    "detail": (
                        f"groups={unavailable_groups}; reasons={reasons}"
                    ),
                }
            )

    capability_ids = set(CAPABILITY_CAMPAIGN_IDS)
    for extra in sorted(set(bindings) - capability_ids):
        gaps.append(
            {
                "campaign_id": extra,
                "code": "unknown_semantic_binding",
                "detail": "binding names no physical campaign in the reviewed capability inventory",
            }
        )

    excluded_ids = capability_ids - set(campaign_ids)
    for excluded in sorted(excluded_ids):
        binding = bindings.get(excluded)
        if binding is None:
            gaps.append(
                {
                    "campaign_id": excluded,
                    "code": "profile_excluded_semantic_binding_absent",
                    "detail": (
                        "the semantic registry must explicitly retain a disabled row "
                        "for every campaign excluded by the selected theorem profile"
                    ),
                }
            )
        elif binding["enabled"] is not False:
            gaps.append(
                {
                    "campaign_id": excluded,
                    "code": "profile_excluded_semantic_binding_enabled",
                    "detail": (
                        "an excluded campaign must be explicitly disabled so the "
                        "selected theorem route cannot silently ignore an active binding"
                    ),
                }
            )

    for campaign in selected_cluster["physical_campaigns"]:
        campaign_id = campaign["campaign_id"]
        binding = bindings.get(campaign_id)
        if binding is None:
            gaps.append(
                {
                    "campaign_id": campaign_id,
                    "code": "semantic_binding_absent",
                    "detail": "no source-pinned terminal trusted-compute binding exists",
                }
            )
            continue
        semantic_enabled = binding["enabled"] is True
        if not semantic_enabled:
            staged = {
                field: binding[field]
                for field in (
                    "registered_invocation",
                    "realization_id",
                    "lean_theorem",
                )
                if binding[field] is not None
            }
            gaps.append(
                {
                    "campaign_id": campaign_id,
                    "code": "semantic_binding_disabled",
                    "detail": f"source inventory row is disabled; staged={staged}",
                }
            )
            if not staged:
                gaps.append(
                    {
                        "campaign_id": campaign_id,
                        "code": "terminal_receipt_contract_absent",
                        "detail": (
                            "disabled semantic row has no reviewed staged "
                            "invocation/result identity"
                        ),
                    }
                )
                continue
            pending = PENDING_TG_REALIZATIONS.get(binding["realization_id"])
            if pending != {
                "campaign_id": campaign_id,
                "lean_theorem": binding["lean_theorem"],
                "registered_invocation": binding["registered_invocation"],
            }:
                gaps.append(
                    {
                        "campaign_id": campaign_id,
                        "code": "disabled_semantic_shape_unreviewed",
                        "detail": f"staged={staged}",
                    }
                )
                continue
        invocation = binding["registered_invocation"]
        realization_id = binding["realization_id"]
        lean_theorem = binding["lean_theorem"]
        if invocation is None or realization_id is None or lean_theorem is None:
            gaps.append(
                {
                    "campaign_id": campaign_id,
                    "code": "semantic_binding_incomplete",
                    "detail": (
                        "both a registered invocation and a concrete Lean realization are required"
                    ),
                }
            )
            continue
        try:
            registered_invocation_expected(invocation)
            required_backend = registered_invocation_backend(invocation)
        except (ReceiptError, OSError, ValueError) as error:
            gaps.append(
                {
                    "campaign_id": campaign_id,
                    "code": "registered_invocation_unknown",
                    "detail": str(error),
                }
            )
            continue
        terminal = next(
            group for group in groups
            if group["campaign_id"] == campaign_id and group["terminal"]
        )
        if required_backend is not None and required_backend != terminal["receipt_backend"]:
            gaps.append(
                {
                    "campaign_id": campaign_id,
                    "code": "registered_invocation_backend_mismatch",
                    "detail": (
                        f"{invocation} requires {required_backend}, but the terminal routes to "
                        f"{terminal['receipt_backend']}"
                    ),
                }
            )
            continue
        if semantic_enabled:
            expected_realization = catalog.get(realization_id)
            if expected_realization != {
                "campaign_id": campaign_id,
                "lean_theorem": lean_theorem,
                "registered_invocation": invocation,
            }:
                gaps.append(
                    {
                        "campaign_id": campaign_id,
                        "code": "lean_realization_unregistered",
                        "detail": (
                            "the source-known realization catalog has no exact "
                            "campaign/invocation pair"
                        ),
                    }
                )
                continue
        result_binding = result_catalog.get(realization_id)
        if result_binding is None:
            gaps.append(
                {
                    "campaign_id": campaign_id,
                    "code": "terminal_registered_result_unbound",
                    "detail": (
                        "the source-known realization has no reviewed terminal "
                        "registered-result output contract"
                    ),
                }
            )
            continue
        command = terminal["command_template"]
        positions = [
            index
            for index, token in enumerate(command)
            if token == result_binding.argument
        ]
        if (
            len(positions) != 1
            or positions[0] + 1 >= len(command)
            or command[positions[0] + 1] != result_binding.artifact_template
        ):
            gaps.append(
                {
                    "campaign_id": campaign_id,
                    "code": "terminal_registered_result_command_mismatch",
                    "detail": (
                        "terminal argv must contain exactly one adjacent reviewed "
                        f"pair {result_binding.argument!r}, "
                        f"{result_binding.artifact_template!r}"
                    ),
                }
            )
            continue
        terminal["terminal_receipt_contract"] = {
            "classification": (
                "registered_invocation_and_result_contract_not_theorem_authority"
            ),
            "registered_invocation": invocation,
            "registered_result_argument": result_binding.argument,
            "registered_result_artifact_template": (
                result_binding.artifact_template
            ),
            "semantic_admission_enabled": False,
        }
        if semantic_enabled:
            terminal["semantic_binding"] = {
                "lean_theorem": lean_theorem,
                "registered_result_artifact_template": (
                    result_binding.artifact_template
                ),
                "realization_scope": SOURCE_TG_DOWNSTREAM_REALIZATION_SCOPES.get(
                    realization_id,
                    "gpu_prover_receipt_campaign_result_not_claude_math_atom",
                ),
                "realization_id": realization_id,
                "registered_invocation": invocation,
            }

    for group in groups:
        group.setdefault("semantic_binding", None)
        group.setdefault("terminal_receipt_contract", None)

    edges = sorted(
        (
            {
                "condition": "all_shards_have_verified_receipts",
                "from": dependency,
                "to": group["group_id"],
            }
            for group in groups
            for dependency in group["depends_on"]
        ),
        key=lambda edge: (edge["to"], edge["from"]),
    )
    gap_order = sorted(
        gaps,
        key=lambda gap: (gap["campaign_id"], gap["code"], str(gap["detail"])),
    )
    # Disabled-but-reviewed terminal shapes are post-run theorem-admission
    # gaps, not execution gaps.  Budget/sizing gaps remain absolute blockers
    # for creating an operator handoff, but they do not prevent persisting a
    # bounded local plan.  This distinction keeps local initialization useful
    # without turning it into permission to spend cloud resources.
    semantic_only_gap_codes = {"semantic_binding_disabled"}
    local_initialization_nonblocking_codes = semantic_only_gap_codes | {
        "production_budget_gate_failed",
        "production_sizing_absent",
        "production_sizing_stale_campaign",
    }
    local_initialization_blockers = sorted(
        {
            gap["code"]
            for gap in gap_order
            if gap["code"] not in local_initialization_nonblocking_codes
        }
    )
    operator_handoff_blockers = sorted(
        {
            gap["code"]
            for gap in gap_order
            if gap["code"] not in semantic_only_gap_codes
        }
    )
    local_initialization_ready = not local_initialization_blockers
    operator_handoff_ready = not operator_handoff_blockers
    return {
        "accepted": False,
        "backend_assignments": [
            {
                "backend_class": backend_class,
                "operator_adapter": route.operator_adapter,
                "production_operator_available": route.production_operator_available,
                "receipt_backend": route.receipt_backend,
            }
            for backend_class, route in sorted(BACKEND_ROUTES.items())
        ],
        "challenge_ttl_seconds": spec["challenge_ttl_seconds"],
        "classification": "deterministic_local_plan_not_execution_evidence",
        "completion_profile": profile_record,
        "edges": edges,
        "gaps": gap_order,
        "groups": groups,
        "kind": PLAN_KIND,
        "portfolio_id": spec["portfolio_id"],
        "promotion_policy": {
            "manual_completion_accepted": False,
            "process_exit_accepted": False,
            "receipt_realization_discharges_claude_math_atom": False,
            "receipt_signature_required_for_every_shard": True,
            "staged_contract_grants_theorem_authority": False,
            "terminal_registered_invocation_required": True,
            "terminal_realization_required": True,
        },
        "production_budget_gate": budget_gate,
        "readiness": {
            "local_initialization_blocking_gap_codes": (
                local_initialization_blockers
            ),
            "local_initialization_ready": local_initialization_ready,
            "operator_handoff_blocking_gap_codes": operator_handoff_blockers,
            "operator_handoff_ready": operator_handoff_ready,
            "semantic_admission_complete": False,
            "semantic_admission_policy": (
                "reviewed_terminal_receipts_and_separate_source_admission_required"
            ),
        },
        # Compatibility summary: shard preparation creates an operator
        # handoff, so it deliberately remains behind the hard budget gate.
        "ready_for_local_preparation": operator_handoff_ready,
        "run_root": spec["run_root"],
        "schema_version": SCHEMA_VERSION,
        "source": {
            "cluster_manifest_sha256": spec["cluster_manifest"]["sha256"],
            "repository_commit_oid": cluster["repository_binding"]["git_commit_oid"],
            "repository_tree_oid": cluster["repository_binding"]["git_tree_oid"],
            "semantic_bindings_sha256": spec["semantic_bindings"]["sha256"],
            "verifier_key_manifest_sha256": spec["verifier_key_manifest"]["sha256"],
        },
    }


def load_portfolio_spec(path: Path) -> PortfolioContext:
    if path.is_symlink():
        raise PortfolioError("portfolio specification must not be a symlink")
    spec_path = path.resolve(strict=True)
    raw_spec_value, raw = _canonical_file(spec_path, "portfolio specification")
    spec = _exact(raw_spec_value, SPEC_FIELDS, "portfolio specification")
    if spec["kind"] != SPEC_KIND or spec["schema_version"] != SCHEMA_VERSION:
        raise PortfolioError("unsupported portfolio specification")
    _name(spec["portfolio_id"], "portfolio id")
    profile_id = _name(spec["completion_profile"], "completion profile")
    if profile_id not in COMPLETION_PROFILES:
        raise PortfolioError(
            "unknown completion profile; choose one of "
            + ", ".join(COMPLETION_PROFILES)
        )
    if spec["production_price_class"] not in {"pay_as_you_go", "spot"}:
        raise PortfolioError("production price class must be pay_as_you_go or spot")
    _integer(
        spec["challenge_ttl_seconds"],
        "challenge TTL",
        minimum=1,
        maximum=MAX_TTL_SECONDS,
    )
    repository_root = _absolute_path(
        spec["repository_root"], "repository root", may_not_exist=False
    )
    if not repository_root.is_dir() or repository_root.is_symlink():
        raise PortfolioError("repository root must be a regular directory, not a symlink")
    run_root = _absolute_path(spec["run_root"], "run root", may_not_exist=True)
    try:
        run_root.relative_to(repository_root)
    except ValueError:
        pass
    else:
        raise PortfolioError("run root must stay outside the reviewed source repository")
    if run_root.exists() and (run_root.is_symlink() or not run_root.is_dir()):
        raise PortfolioError("existing run root must be a non-symlink directory")

    _cluster_pin, cluster_path = _absolute_pin(
        spec["cluster_manifest"], "cluster manifest"
    )
    try:
        cluster = load_cluster_manifest(cluster_path)
        verify_repository_binding(repository_root, cluster["repository_binding"])
    except (ClusterPlanError, OSError, ValueError) as error:
        raise PortfolioError(f"cluster/repository verification failed: {error}") from error

    _semantic_pin, semantic_path = _repository_pin(
        spec["semantic_bindings"],
        "semantic bindings",
        repository_root=repository_root,
        repository_binding=cluster["repository_binding"],
    )
    semantic_value, _semantic_raw = _canonical_file(
        semantic_path, "semantic bindings"
    )
    semantic = _validate_semantic_bindings(semantic_value)

    _key_pin, key_manifest = _repository_pin(
        spec["verifier_key_manifest"],
        "verifier key manifest",
        repository_root=repository_root,
        repository_binding=cluster["repository_binding"],
    )
    plan = build_plan(spec, cluster, semantic)
    return PortfolioContext(
        spec_path=spec_path,
        spec=spec,
        spec_sha256=sha256_bytes(raw),
        repository_root=repository_root,
        run_root=run_root,
        cluster_manifest=cluster,
        semantic_bindings=semantic,
        verifier_key_manifest=key_manifest,
        plan=plan,
    )


def _plan_path(context: PortfolioContext) -> Path:
    return context.run_root / "portfolio-plan.json"


def _state_path(context: PortfolioContext) -> Path:
    return context.run_root / "portfolio-state.json"


def _portfolio_lock(context: PortfolioContext) -> Path:
    return context.run_root / ".portfolio.lock"


def _utc(now: dt.datetime | None = None) -> dt.datetime:
    value = now or dt.datetime.now(dt.timezone.utc)
    if value.tzinfo is None:
        raise PortfolioError("time must be timezone-aware")
    return value.astimezone(dt.timezone.utc).replace(microsecond=0)


def _timestamp(value: dt.datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_timestamp(value: Any, what: str) -> dt.datetime:
    if not isinstance(value, str):
        raise PortfolioError(f"{what} is not a canonical UTC timestamp")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise PortfolioError(f"{what} is not a canonical UTC timestamp") from error
    return parsed.replace(tzinfo=dt.timezone.utc)


def initialize(context: PortfolioContext, *, now: dt.datetime | None = None) -> dict[str, Any]:
    """Persist a source-closed local plan; this never authorizes an operator."""

    readiness = context.plan["readiness"]
    if not readiness["local_initialization_ready"]:
        codes = readiness["local_initialization_blocking_gap_codes"]
        raise PortfolioError(
            "portfolio initialization refused because source-contract gaps remain: "
            + ", ".join(codes)
        )
    context.run_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with advisory_lock(_portfolio_lock(context)):
        write_immutable_json(_plan_path(context), context.plan)
        state = {
            "accepted": False,
            "created_at_utc": _timestamp(_utc(now)),
            "kind": STATE_KIND,
            "plan_sha256": context.plan_sha256,
            "portfolio_id": context.spec["portfolio_id"],
            "records": {},
            "schema_version": SCHEMA_VERSION,
        }
        if _state_path(context).exists():
            existing = _load_state_unlocked(context)
            return _status_from_state(context, existing)
        write_immutable_json(_state_path(context), state)
        return _status_from_state(context, state)


def _task_paths(context: PortfolioContext, group_id: str, shard_index: int) -> dict[str, Path]:
    group_digest = hashlib.sha256(group_id.encode("utf-8")).hexdigest()
    task_id = f"{group_digest[:24]}-{shard_index:09d}"
    root = context.run_root / "shards" / group_digest / f"{shard_index:09d}"
    return {
        "root": root,
        "challenge": root / "challenge.json",
        "config": root / "shard-config.json",
        "receipt": root / "receipt.json",
        "workspace": root / "workspace",
        "task_id": Path(task_id),
    }


def _group(context: PortfolioContext, group_id: str) -> dict[str, Any]:
    matches = [group for group in context.plan["groups"] if group["group_id"] == group_id]
    if len(matches) != 1:
        raise PortfolioError(f"unknown portfolio group: {group_id}")
    return matches[0]


def _task_id(context: PortfolioContext, group_id: str, shard_index: int) -> str:
    return _task_paths(context, group_id, shard_index)["task_id"].name


def _validate_task_record(
    context: PortfolioContext, task_id: str, value: Any
) -> dict[str, Any]:
    record = _exact(value, TASK_RECORD_FIELDS, f"task record {task_id}")
    group = _group(context, record["group_id"])
    index = _integer(
        record["shard_index"],
        f"task {task_id} shard index",
        minimum=0,
        maximum=group["shard_count"] - 1,
    )
    if _task_id(context, group["group_id"], index) != task_id:
        raise PortfolioError(f"task record {task_id} identity differs")
    if record["stage"] not in {"challenge_created", "verified_receipt_recorded"}:
        raise PortfolioError(f"task record {task_id} has an unsupported stage")
    paths = _task_paths(context, group["group_id"], index)
    for field, path_key in (
        ("challenge_sha256", "challenge"),
        ("config_sha256", "config"),
    ):
        expected = _sha256(record[field], f"task {task_id} {field}")
        actual, _size = hash_file_once(paths[path_key])
        if actual != expected:
            raise PortfolioError(f"task {task_id} immutable {path_key} changed")
    challenge_value = load_json(paths["challenge"], require_canonical=True)
    challenge = _exact(challenge_value, CHALLENGE_FIELDS, f"task {task_id} challenge")
    if (
        challenge["kind"] != CHALLENGE_KIND
        or challenge["schema_version"] != CHALLENGE_SCHEMA_VERSION
        or challenge["shard_index"] != index
        or not isinstance(challenge["campaign_id"], str)
        or NAME_RE.fullmatch(challenge["campaign_id"]) is None
    ):
        raise PortfolioError(f"task {task_id} challenge identity is invalid")
    _sha256(challenge["nonce"], f"task {task_id} challenge nonce")
    issued = _parse_timestamp(challenge["issued_at_utc"], "challenge issue time")
    expires = _parse_timestamp(challenge["expires_at_utc"], "challenge expiry")
    if expires - issued != dt.timedelta(seconds=context.spec["challenge_ttl_seconds"]):
        raise PortfolioError(f"task {task_id} challenge TTL differs from the plan")
    config_value = load_json(paths["config"], require_canonical=True)
    expected_config = _shard_config(
        context,
        group,
        index,
        challenge,
        record["challenge_sha256"],
    )
    if config_value != expected_config:
        raise PortfolioError(f"task {task_id} shard config differs from the exact plan")
    if record["stage"] == "challenge_created":
        if record["receipt_sha256"] is not None or record["receipt_file_sha256"] is not None:
            raise PortfolioError(f"task {task_id} has a receipt before completion")
    else:
        _sha256(record["receipt_sha256"], f"task {task_id} receipt identity")
        expected_file = _sha256(
            record["receipt_file_sha256"], f"task {task_id} receipt file hash"
        )
        actual_file, _size = hash_file_once(paths["receipt"])
        if actual_file != expected_file:
            raise PortfolioError(f"task {task_id} immutable receipt changed")
        try:
            receipt = load_verified_receipt(
                paths["receipt"], key_manifest=context.verifier_key_manifest
            )
        except (ReceiptError, OSError, ValueError) as error:
            raise PortfolioError(
                f"task {task_id} recorded receipt no longer verifies: {error}"
            ) from error
        if (
            receipt["receipt_sha256"] != record["receipt_sha256"]
            or receipt["backend"] != group["receipt_backend"]
            or receipt["claim"]["nonce"] != challenge["nonce"]
        ):
            raise PortfolioError(f"task {task_id} recorded receipt bindings differ")
        if group["terminal"]:
            contract = group["terminal_receipt_contract"]
            if contract is None:
                raise PortfolioError(
                    f"task {task_id} terminal receipt contract disappeared"
                )
            try:
                validate_registered_invocation(
                    receipt, contract["registered_invocation"]
                )
            except ReceiptError as error:
                raise PortfolioError(
                    f"task {task_id} terminal receipt result differs: {error}"
                ) from error
    return record


def _load_state_unlocked(context: PortfolioContext) -> dict[str, Any]:
    plan_value, plan_raw = _canonical_file(_plan_path(context), "portfolio plan")
    if plan_value != context.plan or sha256_bytes(plan_raw) != context.plan_sha256:
        raise PortfolioError("persisted portfolio plan differs from current pinned inputs")
    state_value, _state_raw = _canonical_file(_state_path(context), "portfolio state")
    state = _exact(state_value, STATE_FIELDS, "portfolio state")
    if (
        state["kind"] != STATE_KIND
        or state["schema_version"] != SCHEMA_VERSION
        or state["accepted"] is not False
        or state["portfolio_id"] != context.spec["portfolio_id"]
        or state["plan_sha256"] != context.plan_sha256
        or not isinstance(state["records"], dict)
    ):
        raise PortfolioError("portfolio state does not belong to the exact current plan")
    _parse_timestamp(state["created_at_utc"], "state creation time")
    for task_id in sorted(state["records"]):
        if not isinstance(task_id, str):
            raise PortfolioError("portfolio state task ids must be strings")
        _validate_task_record(context, task_id, state["records"][task_id])
    return state


def load_state(context: PortfolioContext) -> dict[str, Any]:
    with advisory_lock(_portfolio_lock(context)):
        return _load_state_unlocked(context)


def _group_completed_counts(
    context: PortfolioContext, state: Mapping[str, Any]
) -> dict[str, int]:
    counts = {group["group_id"]: 0 for group in context.plan["groups"]}
    for record in state["records"].values():
        if record["stage"] == "verified_receipt_recorded":
            counts[record["group_id"]] += 1
    return counts


def _status_from_state(
    context: PortfolioContext, state: Mapping[str, Any], *, now: dt.datetime | None = None
) -> dict[str, Any]:
    counts = _group_completed_counts(context, state)
    now_utc = _utc(now)
    summaries: list[dict[str, Any]] = []
    expired = 0
    for group in context.plan["groups"]:
        dependencies_complete = all(
            counts[dependency] == _group(context, dependency)["shard_count"]
            for dependency in group["depends_on"]
        )
        claimed = sum(
            1 for record in state["records"].values()
            if record["group_id"] == group["group_id"]
        )
        complete = counts[group["group_id"]]
        summaries.append(
            {
                "claimed_shards": claimed,
                "completed_shards": complete,
                "dependencies_complete": dependencies_complete,
                "group_id": group["group_id"],
                "ready_unclaimed_shards": (
                    group["shard_count"] - claimed if dependencies_complete else 0
                ),
                "shard_count": group["shard_count"],
            }
        )
    for record in state["records"].values():
        if record["stage"] != "challenge_created":
            continue
        group = _group(context, record["group_id"])
        challenge_path = _task_paths(
            context, group["group_id"], record["shard_index"]
        )["challenge"]
        challenge = load_json(challenge_path, require_canonical=True)
        if _parse_timestamp(challenge.get("expires_at_utc"), "challenge expiry") <= now_utc:
            expired += 1
    terminal_complete = sum(
        1
        for group in context.plan["groups"]
        if group["terminal"] and counts[group["group_id"]] == group["shard_count"]
    )
    return {
        "accepted": False,
        "classification": "portfolio_progress_not_execution_or_theorem_acceptance",
        "completion_profile": context.plan["completion_profile"]["profile_id"],
        "expired_unfinished_challenges": expired,
        "groups": summaries,
        "lean_atoms_discharged": 0,
        "operator_handoff_ready": context.plan["readiness"][
            "operator_handoff_ready"
        ],
        "plan_sha256": context.plan_sha256,
        "portfolio_id": context.spec["portfolio_id"],
        "semantic_admission_complete": False,
        "terminal_campaigns_with_verified_receipts": terminal_complete,
        "total_campaigns": sum(1 for group in context.plan["groups"] if group["terminal"]),
    }


def status(context: PortfolioContext, *, now: dt.datetime | None = None) -> dict[str, Any]:
    with advisory_lock(_portfolio_lock(context)):
        return _status_from_state(context, _load_state_unlocked(context), now=now)


def _resolved_argv(group: Mapping[str, Any], shard_index: int) -> list[str]:
    result = [
        token.replace("${TG_ARRAY_INDEX}", str(shard_index))
        for token in group["command_template"]
    ]
    if any("${TG_ARRAY_INDEX}" in token for token in result):
        raise PortfolioError("array-index placeholder remained after shard binding")
    return result


def _challenge(
    context: PortfolioContext,
    group: Mapping[str, Any],
    shard_index: int,
    *,
    now: dt.datetime,
    nonce: str | None,
) -> dict[str, Any]:
    nonce_value = nonce or secrets.token_hex(32)
    _sha256(nonce_value, "challenge nonce")
    group_hash = hashlib.sha256(group["group_id"].encode("utf-8")).hexdigest()[:16]
    portfolio_hash = hashlib.sha256(
        context.spec["portfolio_id"].encode("utf-8")
    ).hexdigest()[:16]
    return {
        "campaign_id": f"tgp:{portfolio_hash}:{group_hash}:{shard_index}",
        "expires_at_utc": _timestamp(
            now + dt.timedelta(seconds=context.spec["challenge_ttl_seconds"])
        ),
        "issued_at_utc": _timestamp(now),
        "kind": CHALLENGE_KIND,
        "nonce": nonce_value,
        "schema_version": CHALLENGE_SCHEMA_VERSION,
        "shard_index": shard_index,
    }


def _shard_config(
    context: PortfolioContext,
    group: Mapping[str, Any],
    shard_index: int,
    challenge: Mapping[str, Any],
    challenge_sha256: str,
) -> dict[str, Any]:
    paths = _task_paths(context, group["group_id"], shard_index)
    argv = _resolved_argv(group, shard_index)
    required_environment = sorted(
        {
            match.group(1)
            for token in argv
            for match in PLACEHOLDER_RE.finditer(token)
        }
    )
    return {
        "accepted": False,
        "argv": argv,
        "backend_class": group["backend_class"],
        "campaign_id": group["campaign_id"],
        "challenge": {
            "expires_at_utc": challenge["expires_at_utc"],
            "nonce": challenge["nonce"],
            "path": str(paths["challenge"]),
            "sha256": challenge_sha256,
        },
        "classification": "isolated_shard_handoff_not_execution_evidence",
        "completion_profile": context.plan["completion_profile"]["profile_id"],
        "depends_on_groups": group["depends_on"],
        "group_id": group["group_id"],
        "kind": SHARD_CONFIG_KIND,
        "materializer_adapter": group["materializer_adapter"],
        "operator_adapter": group["operator_adapter"],
        "phase_id": group["phase_id"],
        "plan_sha256": context.plan_sha256,
        "portfolio_id": context.spec["portfolio_id"],
        "receipt_backend": group["receipt_backend"],
        "required_environment": required_environment,
        "schema_version": SCHEMA_VERSION,
        "semantic_admission_enabled": False,
        "semantic_binding": group["semantic_binding"],
        "shard_count": group["shard_count"],
        "shard_index": shard_index,
        "task_id": paths["task_id"].name,
        "terminal": group["terminal"],
        "terminal_receipt_contract": group["terminal_receipt_contract"],
        "workspace": str(paths["workspace"]),
    }


def prepare_shard(
    context: PortfolioContext,
    group_id: str,
    shard_index: int,
    *,
    now: dt.datetime | None = None,
    nonce: str | None = None,
) -> dict[str, Any]:
    """Create or resume one local isolated challenge/config; never call Azure."""

    readiness = context.plan["readiness"]
    if not readiness["operator_handoff_ready"]:
        raise PortfolioError(
            "cannot prepare an operator handoff while production launch gaps remain: "
            + ", ".join(readiness["operator_handoff_blocking_gap_codes"])
        )
    group = _group(context, group_id)
    index = _integer(
        shard_index,
        "shard index",
        minimum=0,
        maximum=group["shard_count"] - 1,
    )
    now_utc = _utc(now)
    paths = _task_paths(context, group_id, index)
    task_id = paths["task_id"].name
    with advisory_lock(_portfolio_lock(context)):
        state = _load_state_unlocked(context)
        counts = _group_completed_counts(context, state)
        incomplete = [
            dependency
            for dependency in group["depends_on"]
            if counts[dependency] != _group(context, dependency)["shard_count"]
        ]
        if incomplete:
            raise PortfolioError(
                f"cannot prepare {task_id}; predecessor groups are incomplete: {incomplete}"
            )
        if task_id in state["records"]:
            record = _validate_task_record(context, task_id, state["records"][task_id])
            challenge = load_json(paths["challenge"], require_canonical=True)
            if (
                record["stage"] == "challenge_created"
                and _parse_timestamp(challenge["expires_at_utc"], "challenge expiry")
                <= now_utc
            ):
                raise PortfolioError(
                    "existing challenge expired; automatic retry is forbidden because the "
                    "attempt may have run and requires operator reconciliation"
                )
            config = load_json(paths["config"], require_canonical=True)
            return {
                "accepted": False,
                "classification": "resumed_existing_isolated_shard_handoff",
                "config": config,
                "record": record,
            }

        # A crash after immutable handoff creation but before the atomic state
        # replacement can leave a complete orphan directory.  Re-adopt only
        # the exact recomputed bytes; never rotate or overwrite its nonce.
        if paths["root"].exists():
            if paths["root"].is_symlink() or not paths["root"].is_dir():
                raise PortfolioError("orphan shard path is not a safe directory")
            try:
                challenge_hash, _ = hash_file_once(paths["challenge"])
                config_hash, _ = hash_file_once(paths["config"])
            except CampaignIOError as error:
                raise PortfolioError(
                    "partial orphan shard handoff requires operator reconciliation"
                ) from error
            recovered = {
                "challenge_sha256": challenge_hash,
                "config_sha256": config_hash,
                "group_id": group_id,
                "receipt_file_sha256": None,
                "receipt_sha256": None,
                "shard_index": index,
                "stage": "challenge_created",
            }
            recovered = _validate_task_record(context, task_id, recovered)
            state["records"][task_id] = recovered
            atomic_write_json(_state_path(context), state)
            challenge = load_json(paths["challenge"], require_canonical=True)
            if _parse_timestamp(challenge["expires_at_utc"], "challenge expiry") <= now_utc:
                raise PortfolioError(
                    "recovered challenge expired; the orphan attempt requires operator reconciliation"
                )
            return {
                "accepted": False,
                "classification": "recovered_exact_orphan_shard_handoff",
                "config": load_json(paths["config"], require_canonical=True),
                "record": recovered,
            }

        paths["root"].mkdir(mode=0o700, parents=True, exist_ok=False)
        challenge = _challenge(context, group, index, now=now_utc, nonce=nonce)
        challenge_hash = write_immutable_json(paths["challenge"], challenge)
        config = _shard_config(
            context, group, index, challenge, challenge_hash
        )
        config_hash = write_immutable_json(paths["config"], config)
        record = {
            "challenge_sha256": challenge_hash,
            "config_sha256": config_hash,
            "group_id": group_id,
            "receipt_file_sha256": None,
            "receipt_sha256": None,
            "shard_index": index,
            "stage": "challenge_created",
        }
        state["records"][task_id] = record
        atomic_write_json(_state_path(context), state)
        return {
            "accepted": False,
            "classification": "new_isolated_shard_handoff_not_execution_evidence",
            "config": config,
            "record": record,
        }


def record_verified_receipt(
    context: PortfolioContext,
    group_id: str,
    shard_index: int,
    receipt_path: Path,
) -> dict[str, Any]:
    """Record one signed receipt; no process exit or manual flag can substitute."""

    group = _group(context, group_id)
    index = _integer(
        shard_index,
        "shard index",
        minimum=0,
        maximum=group["shard_count"] - 1,
    )
    paths = _task_paths(context, group_id, index)
    task_id = paths["task_id"].name
    with advisory_lock(_portfolio_lock(context)):
        state = _load_state_unlocked(context)
        record = state["records"].get(task_id)
        if record is None:
            raise PortfolioError("receipt has no prior off-VM challenge/config record")
        record = _validate_task_record(context, task_id, record)
        if record["stage"] == "verified_receipt_recorded":
            return {
                "accepted": False,
                "classification": "resumed_existing_verified_receipt_record",
                "record": record,
            }
        try:
            receipt = load_verified_receipt(
                receipt_path.resolve(strict=True),
                key_manifest=context.verifier_key_manifest,
            )
        except (ReceiptError, OSError, ValueError) as error:
            raise PortfolioError(f"receipt verification failed: {error}") from error
        challenge = load_json(paths["challenge"], require_canonical=True)
        if receipt["backend"] != group["receipt_backend"]:
            raise PortfolioError("receipt backend differs from the deterministic route")
        if receipt["claim"]["nonce"] != challenge["nonce"]:
            raise PortfolioError("receipt is not bound to this shard's retained challenge")
        if group["terminal"]:
            contract = group["terminal_receipt_contract"]
            if contract is None:
                raise PortfolioError(
                    "terminal shard lacks a reviewed receipt-validation contract"
                )
            try:
                validate_registered_invocation(
                    receipt, contract["registered_invocation"]
                )
            except ReceiptError as error:
                raise PortfolioError(
                    f"terminal receipt does not realize its registered invocation: {error}"
                ) from error
        receipt_file_hash = write_immutable_json(paths["receipt"], receipt)
        record = dict(record)
        record.update(
            {
                "receipt_file_sha256": receipt_file_hash,
                "receipt_sha256": receipt["receipt_sha256"],
                "stage": "verified_receipt_recorded",
            }
        )
        state["records"][task_id] = record
        atomic_write_json(_state_path(context), state)
        return {
            "accepted": False,
            "classification": "signed_receipt_recorded_not_lean_theorem_acceptance",
            "record": record,
        }


def inspect(context: PortfolioContext) -> dict[str, Any]:
    """Return the canonical deterministic plan, including production gaps."""

    return context.plan


__all__ = [
    "BACKEND_ROUTES",
    "CAPABILITY_CAMPAIGN_IDS",
    "CAPABILITY_INVENTORY_PROFILE",
    "COMPLETION_PROFILES",
    "LOWERED_10POW27_COMPLETION_PROFILE",
    "PENDING_TG_REALIZATIONS",
    "PLAN_KIND",
    "PortfolioContext",
    "PortfolioError",
    "SEMANTIC_REGISTRY_KIND",
    "SOURCE_TG_REALIZATIONS",
    "SOURCE_TG_TERMINAL_RESULTS",
    "SOURCE_RETIREMENT_PROFILE",
    "SPEC_KIND",
    "TerminalResultBinding",
    "build_plan",
    "completion_profile_inventory",
    "initialize",
    "inspect",
    "load_portfolio_spec",
    "load_state",
    "prepare_shard",
    "record_verified_receipt",
    "status",
]
