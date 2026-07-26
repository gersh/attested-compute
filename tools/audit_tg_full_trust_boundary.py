#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Audit one closed inventory for every ternary-Goldbach trust root.

The default mode joins the checked-in compact external-claim catalog and the
native-family catalog.  ``--claude-math-root`` additionally checks the exact
last-fresh ``Statement.trace``, native manifest, and citation inventory.  It
does not build Lean, replay a finite computation, or claim that staged
replacements have reached the current capstone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.compact_receipt_closure import (  # noqa: E402
    CompactReceiptClosureError,
    load_and_validate_closure,
)
from tools.validate_tg_native_family_closure import (  # noqa: E402
    CatalogError,
    load_and_validate as load_and_validate_native_catalog,
)
from tools.validate_tg_native_member_crosswalk import (  # noqa: E402
    CrosswalkError,
    load_and_validate as load_and_validate_native_members,
    validate_against_authoritative_manifest as validate_native_members_manifest,
    validate_evidence_paths as validate_native_member_evidence_paths,
)
from tools.validate_tg_native_architecture_bridge_status import (  # noqa: E402
    NativeArchitectureStatusError,
    load_and_validate as load_and_validate_native_architecture_status,
)


DEFAULT_SPECIFICATION = (
    REPOSITORY_ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_FULL_TRUST_BOUNDARY.json"
)


class FullTrustBoundaryError(ValueError):
    """The trust-root catalogs do not form the required closed partition."""


EXPECTED_CLOSED_SOURCE_PROGRAM_CAMPAIGNS = [
    ("ch25A7Boundary", "ch25A7BoundaryProductionV1", "a7Missing"),
    ("ch25PsiLemma92", "ch25PsiLemma92ProductionV1", "psiMissing"),
    ("plattHead2e4", "plattHead2e4ProductionV1", "zetaHeadMissing"),
    (
        "plattTrudgianRH3e12",
        "plattTrudgianFiniteRHProductionV1",
        "zetaRHMissing",
    ),
    ("helfgottProp1224", "helfgottProp1224ProductionV1", "prop1224Missing"),
    (
        "hurstSharedFourResidual",
        "hurstSharedFourResidualProductionV2",
        "hurstMissing",
    ),
    ("cdemTableAbel", "cdemTableAbelProductionV2", None),
    (
        "ramareZunigaLemma62",
        "ramareZunigaLemma62ProductionV1",
        "r2StarMissing",
    ),
    (
        "helfgottPlattTheorem41",
        "helfgottPlattGoldbachProductionV1",
        "goldbachMissing",
    ),
    (
        "plattDirichletTheorem71",
        "plattDirichletTheorem71ProductionV1",
        "plattDirichletMissing",
    ),
    (
        "ramareProductionFolds",
        "ramareProductionFoldsCompactV1",
        "ramareFoldsMissing",
    ),
]

EXPECTED_CLOSED_RECEIPT_ROSTER_CAMPAIGNS = [
    ("ch25A7Boundary", "ch25A7BoundaryProductionV1"),
    ("ch25PsiLemma92", "ch25PsiLemma92ProductionV1"),
    ("plattHead2e4", "plattHead2e4ProductionV1"),
    (
        "plattTrudgianRH3e12",
        "plattTrudgianFiniteRHProductionV1",
    ),
    ("helfgottProp1224", "helfgottProp1224ProductionV1"),
    (
        "hurstSharedFourResidual",
        "hurstSharedFourResidualProductionV2",
    ),
    ("cdemTableAbel", "cdemTableAbelProductionV2"),
    (
        "ramareZunigaLemma62",
        "ramareZunigaLemma62ProductionV1",
    ),
    (
        "helfgottPlattTheorem41",
        "helfgottPlattGoldbachProductionV1",
    ),
    (
        "plattDirichletTheorem71",
        "plattDirichletTheorem71ProductionV1",
    ),
    (
        "nativeGeneratedAggregate",
        "nativeGeneratedAggregateProductionV1",
    ),
]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FullTrustBoundaryError(message)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FullTrustBoundaryError(f"cannot load {path}: {error}") from error
    _require(isinstance(value, dict), f"{path}: expected a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise FullTrustBoundaryError(f"cannot hash {path}: {error}") from error
    return digest.hexdigest()


def _prefixed_sha256(path: Path) -> str:
    return "sha256:" + _sha256(path)


def _one_match(pattern: str, source: str, label: str) -> re.Match[str]:
    matches = list(re.finditer(pattern, source, flags=re.MULTILINE | re.DOTALL))
    _require(
        len(matches) == 1,
        f"Lean trust catalog must contain exactly one {label}; "
        f"found {len(matches)}",
    )
    return matches[0]


def _audit_closed_source_program_catalog(source: str) -> dict[str, int]:
    """Parse the closed Lean audit catalog without evaluating any campaign.

    The Lean test separately elaborates the declarations.  This static pass
    makes the JSON trust-boundary audit fail closed if the exact eleven-member
    roster, invocation map, missing classifications, or the sole complete
    CDEM artifact program changes without an explicit specification update.
    """

    all_match = _one_match(
        r"def all : List Campaign :=\s*\[(?P<body>.*?)\]\s*\n\n/--",
        source,
        "Campaign.all definition",
    )
    roster = re.findall(r"\.([A-Za-z0-9_]+)", all_match.group("body"))
    expected_roster = [
        campaign for campaign, _invocation, _missing
        in EXPECTED_CLOSED_SOURCE_PROGRAM_CAMPAIGNS
    ]
    _require(
        roster == expected_roster,
        "closed source-program Campaign.all is not the exact ordered "
        "eleven-campaign roster",
    )

    invocation_match = _one_match(
        r"def invocation : Campaign → RegisteredArchitectureInvocation"
        r"(?P<body>.*?)(?=\n\n/-- Fixed checker)",
        source,
        "Campaign.invocation definition",
    )
    invocation_rows = re.findall(
        r"^\s*\|\s*\.([A-Za-z0-9_]+)\s*=>\s*\.([A-Za-z0-9_]+)\s*$",
        invocation_match.group("body"),
        flags=re.MULTILINE,
    )
    expected_invocations = [
        (campaign, invocation)
        for campaign, invocation, _missing
        in EXPECTED_CLOSED_SOURCE_PROGRAM_CAMPAIGNS
    ]
    _require(
        invocation_rows == expected_invocations,
        "closed source-program invocation map differs from the exact "
        "external-plus-fallback registry roster",
    )

    expected_classifications = [
        (campaign, missing)
        for campaign, _invocation, missing
        in EXPECTED_CLOSED_SOURCE_PROGRAM_CAMPAIGNS
        if missing is not None
    ]
    classification_names = re.findall(
        r"^def ([A-Za-z0-9_]+) : MissingProgramClassification where$",
        source,
        flags=re.MULTILINE,
    )
    _require(
        classification_names
        == [missing for _campaign, missing in expected_classifications],
        "closed source-program missing classifications are not the exact "
        "ordered ten-campaign roster",
    )

    required_fields = (
        "existingPieces",
        "requiredGenerator",
        "requiredParser",
        "requiredTotalCheck",
        "requiredSoundness",
    )
    for _campaign, _invocation, missing_name in (
        EXPECTED_CLOSED_SOURCE_PROGRAM_CAMPAIGNS
    ):
        if missing_name is None:
            continue
        block = _one_match(
            rf"def {re.escape(missing_name)} : "
            rf"MissingProgramClassification where"
            rf"(?P<body>.*?)(?=\n\n/--|\n\n/-!)",
            source,
            f"{missing_name} definition",
        ).group("body")
        for field in required_fields:
            _require(
                len(re.findall(rf"^\s*{field}\s*:=", block, re.MULTILINE))
                == 1,
                f"{missing_name} must specify exactly one {field}",
            )
        _require(
            re.search(r"existingPieces\s*:=\s*\[\s*\]", block) is None,
            f"{missing_name} must name its existing partial proof surface",
        )

    concrete_block = _one_match(
        r"def cdemAbelConcrete :\s*"
        r"ArtifactConcreteProgram Campaign\.cdemTableAbel where"
        r"(?P<body>.*?)(?=\n\n/-- Current closed catalog)",
        source,
        "CDEM complete artifact program",
    ).group("body")
    for required in (
        "CertificateData :=",
        "artifactChecker :=",
        "decode :=",
        "check :=",
        "successResult :=",
        "sound :=",
        "legacyAcceptance :=",
    ):
        _require(
            concrete_block.count(required) == 1,
            "CDEM complete artifact program must specify exactly one "
            f"{required.removesuffix(' :=')}",
        )

    status_match = _one_match(
        r"def status : \(campaign : Campaign\) → ProgramStatus campaign"
        r"(?P<body>.*?)(?=\n\n/-- Decidable projection)",
        source,
        "status definition",
    )
    status_rows = re.findall(
        r"^\s*\|\s*\.([A-Za-z0-9_]+)\s*=>\s*"
        r"\.(missing|artifactConcrete)\s+([A-Za-z0-9_]+)\s*$",
        status_match.group("body"),
        flags=re.MULTILINE,
    )
    expected_status_rows = [
        (
            campaign,
            "artifactConcrete" if missing is None else "missing",
            "cdemAbelConcrete" if missing is None else missing,
        )
        for campaign, _invocation, missing
        in EXPECTED_CLOSED_SOURCE_PROGRAM_CAMPAIGNS
    ]
    _require(
        status_rows == expected_status_rows,
        "closed source-program status must contain exactly one complete CDEM "
        "artifact program and ten fail-closed campaigns",
    )
    _one_match(
        r"theorem auditedCampaignCount : Campaign\.all\.length = 11 :=\s*"
        r"by\s*rfl",
        source,
        "eleven-campaign count theorem",
    )
    _one_match(
        r"theorem concreteCampaignCount :\s*"
        r"\(Campaign\.all\.filter isConcrete\)\.length = 1 :=\s*by\s*rfl",
        source,
        "one-concrete count theorem",
    )
    return {
        "campaigns": len(roster),
        "required_proof_program_gaps": len(classification_names),
        "concrete_programs": 1,
    }


def _audit_closed_accepted_receipt_roster(source: str) -> dict[str, int]:
    """Audit the production-data-free, proof-authorizing receipt slots.

    This pass does not accept a receipt.  It fixes the exact eleven
    architecture invocations which may eventually authorize the ten external
    campaigns and the all-native aggregate, checks both ordinary projection
    theorems, and requires the current roster to remain provably uninhabited.
    """

    outcome_match = _one_match(
        r"structure ReceiptOutcome"
        r"\s*\(invocation : RegisteredArchitectureInvocation\)"
        r"\s*\(receiptHash : Digest\) : Type where"
        r"(?P<body>.*?)(?=\n\nnamespace ReceiptOutcome)",
        source,
        "ReceiptOutcome structure",
    )
    outcome_body = " ".join(outcome_match.group("body").split())
    _require(
        outcome_body
        == (
            "statement : RunStatement "
            "selected : invocation.ReceiptSelected statement receiptHash "
            "architectureOutcomes : "
            "RegisteredArchitectureOutcomes statement receiptHash"
        ),
        "ReceiptOutcome must retain exactly the statement, reviewed-run "
        "selection, and registered architecture outcomes",
    )

    physical_projection = _one_match(
        r"theorem physicalOutcome"
        r"(?P<body>.*?)(?=\n\nend ReceiptOutcome)",
        source,
        "ReceiptOutcome.physicalOutcome theorem",
    ).group("body")
    for required in (
        "invocation.PhysicalOutcome receipt.statement receiptHash",
        "receipt.architectureOutcomes.physicalOutcome "
        "invocation receipt.selected",
    ):
        _require(
            required in " ".join(physical_projection.split()),
            "ReceiptOutcome.physicalOutcome does not use the exact "
            "registered-architecture projection",
        )
    _require(
        "receipt.registered" not in physical_projection,
        "ReceiptOutcome.physicalOutcome must not use the legacy "
        "application-level registered projection",
    )

    imported_match = _one_match(
        r"def ImportedOutcome"
        r"\s*\(invocation : RegisteredArchitectureInvocation\) : Prop :="
        r"(?P<body>.*?)(?=\n\n/-- The eleven receipts)",
        source,
        "ImportedOutcome definition",
    )
    _require(
        " ".join(imported_match.group("body").split())
        == (
            "∃ receiptHash : Digest, "
            "Nonempty (ReceiptOutcome invocation receiptHash)"
        ),
        "ImportedOutcome may existentially hide only the literal receipt hash",
    )

    roster_match = _one_match(
        r"structure RequiredRoster : Prop where"
        r"(?P<body>.*?)(?=\n\nnamespace RequiredRoster)",
        source,
        "RequiredRoster structure",
    )
    roster_rows = re.findall(
        r"^[ \t]{2}([A-Za-z0-9_]+)[ \t]*:[ \t]*\n"
        r"[ \t]+ImportedOutcome \.([A-Za-z0-9_]+)[ \t]*$",
        roster_match.group("body"),
        flags=re.MULTILINE,
    )
    all_roster_fields = re.findall(
        r"^[ \t]{2}([A-Za-z0-9_]+)[ \t]*:",
        roster_match.group("body"),
        flags=re.MULTILINE,
    )
    expected_roster_fields = [
        field
        for field, _invocation in EXPECTED_CLOSED_RECEIPT_ROSTER_CAMPAIGNS
    ]
    _require(
        all_roster_fields == expected_roster_fields
        and roster_rows == EXPECTED_CLOSED_RECEIPT_ROSTER_CAMPAIGNS,
        "closed accepted-receipt RequiredRoster is not the exact ordered "
        "eleven-campaign roster (ten external plus native aggregate)",
    )

    external_projection = _one_match(
        r"theorem externalPhysicalOutcomes"
        r"(?P<body>.*?)(?=\n\n/-- Exact aggregate physical outcome)",
        source,
        "RequiredRoster.externalPhysicalOutcomes theorem",
    ).group("body")
    normalized_external_projection = " ".join(external_projection.split())
    _require(
        "CompactExternalAtomRegisteredCapstone.RegisteredPhysicalOutcomes"
        in normalized_external_projection,
        "externalPhysicalOutcomes must target the exact registered external "
        "capstone outcome",
    )
    expected_external = EXPECTED_CLOSED_RECEIPT_ROSTER_CAMPAIGNS[:-1]
    projected_fields = re.findall(
        r"^[ \t]{2}([A-Za-z0-9_]+)[ \t]*:=[ \t]*by[ \t]*$",
        external_projection,
        flags=re.MULTILINE,
    )
    _require(
        projected_fields == [field for field, _invocation in expected_external],
        "externalPhysicalOutcomes does not project exactly the ten external "
        "receipt fields",
    )
    for field, _invocation in expected_external:
        _require(
            f"roster.{field}" in external_projection,
            f"externalPhysicalOutcomes does not consume roster.{field}",
        )
    _require(
        external_projection.count("receipt.physicalOutcome") == 10,
        "externalPhysicalOutcomes must use the preferred physical projection "
        "exactly ten times",
    )

    native_projection = _one_match(
        r"theorem nativeAggregatePhysicalOutcome"
        r"(?P<body>.*?)(?=\n\nend RequiredRoster)",
        source,
        "RequiredRoster.nativeAggregatePhysicalOutcome theorem",
    ).group("body")
    normalized_native_projection = " ".join(native_projection.split())
    for required in (
        "RegisteredArchitectureInvocation."
        "nativeGeneratedAggregateProductionV1.PhysicalOutcome",
        "roster.nativeGeneratedAggregate",
        "receipt.physicalOutcome",
    ):
        _require(
            required in normalized_native_projection,
            "nativeAggregatePhysicalOutcome does not project the exact "
            "aggregate receipt field",
        )

    fallback_match = _one_match(
        r"def RamareFallbackOutcome : Prop :="
        r"(?P<body>.*?)(?=\n\n/-- Before registration)",
        source,
        "separate optional Ramaré fallback",
    )
    _require(
        " ".join(fallback_match.group("body").split())
        == "ImportedOutcome .ramareProductionFoldsCompactV1",
        "the optional Ramaré fallback must remain separate from the "
        "proof-authorizing eleven-field roster",
    )

    no_imported = _one_match(
        r"theorem no_current_importedOutcome"
        r"(?P<body>.*?)(?=\n\n/-- Consequently)",
        source,
        "no_current_importedOutcome theorem",
    ).group("body")
    normalized_no_imported = " ".join(no_imported.split())
    for required in (
        "¬ ImportedOutcome invocation",
        "reviewedRun_currently_none invocation",
        "receipt.selected",
    ):
        _require(
            required in normalized_no_imported,
            "no_current_importedOutcome must derive impossibility from the "
            "closed registry's absent reviewed run",
        )

    no_roster = _one_match(
        r"theorem no_current_requiredRoster"
        r"(?P<body>.*?)(?=\n\nend "
        r"SparkInterval\.TernaryGoldbach\.ClosedAcceptedReceiptRoster)",
        source,
        "no_current_requiredRoster theorem",
    ).group("body")
    normalized_no_roster = " ".join(no_roster.split())
    for required in (
        "¬ RequiredRoster",
        "no_current_importedOutcome",
        "roster.ch25A7Boundary",
    ):
        _require(
            required in normalized_no_roster,
            "no_current_requiredRoster must rule out the complete roster "
            "through a fixed required field",
        )

    return {
        "proof_authorizing_campaigns": len(roster_rows),
        "external_campaigns": len(expected_external),
        "native_aggregate_campaigns": 1,
        "closed_receipt_slots": len(roster_rows),
        "imported_receipts": 0,
        "accepted_receipts": 0,
    }


def _trace_axiom_names(
    trace: dict[str, Any], root_declaration: str
) -> list[str]:
    needle = f"'{root_declaration}' depends on axioms: ["
    messages = [
        row.get("message", "")
        for row in trace.get("log", [])
        if needle in row.get("message", "")
    ]
    _require(
        len(messages) == 1,
        f"Statement.trace must contain exactly one axiom report for "
        f"{root_declaration}; found {len(messages)}",
    )
    marker = "depends on axioms: ["
    body = messages[0].split(marker, 1)[1]
    _require(body.endswith("]"), "malformed Statement.trace axiom report")
    names = [
        item.strip().removesuffix("✝")
        for item in body[:-1].split(",")
        if item.strip()
    ]
    _require(len(names) == len(set(names)), "duplicate names in trace report")
    return names


def _resolve_trace_names(
    trace_names: list[str], manifest_names: list[str]
) -> dict[str, str]:
    """Resolve Lean's namespace-elided pretty names by unique suffix.

    Lean's report elides the current namespace for some roots and decorates
    private names with ``✝``.  Exact matching is tried first.  A suffix match
    is accepted only when it is unique, and the final map must be a bijection.
    """

    manifest_set = set(manifest_names)
    _require(
        len(manifest_set) == len(manifest_names),
        "duplicate full names in native trust manifest",
    )
    resolved: dict[str, str] = {}
    for displayed in trace_names:
        candidates = [displayed] if displayed in manifest_set else [
            full for full in manifest_names if full.endswith("." + displayed)
        ]
        _require(
            len(candidates) == 1,
            f"trace root {displayed!r} resolves to {len(candidates)} "
            "manifest roots",
        )
        full = candidates[0]
        _require(
            full not in resolved,
            f"two trace roots resolve to manifest root {full!r}",
        )
        resolved[full] = displayed
    _require(
        set(resolved) == manifest_set,
        "Statement.trace and native manifest roots are not a bijection",
    )
    return resolved


def _recompute_native_family_digest(
    entries: list[dict[str, Any]], family: str
) -> str:
    members = sorted(
        (entry["name"], entry["type_digest"])
        for entry in entries
        if entry["family"] == family
    )
    payload = "".join(f"{name}\0{type_digest}\n" for name, type_digest in members)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def audit(
    specification_path: Path = DEFAULT_SPECIFICATION,
    *,
    claude_math_root: Path | None = None,
) -> dict[str, Any]:
    specification = _load(specification_path)
    _require(
        specification.get("schema_version") == 1,
        "unsupported full-trust-boundary schema",
    )
    _require(
        specification.get("kind")
        == "sparkinterval.ternary-goldbach.full-trust-boundary.v1",
        "unexpected full-trust-boundary kind",
    )
    policy = specification["policy"]
    for key in (
        "foundations_are_not_physical_campaigns",
        "every_named_external_atom_must_have_a_compact_claim_projection",
        "every_native_generated_atom_must_belong_to_one_closed_family",
        "every_native_generated_atom_must_have_the_closed_aggregate_invocation_route",
        "every_physical_campaign_must_have_a_deterministic_program_obligation",
        "fresh_build_required_to_claim_retirement",
    ):
        _require(policy.get(key) is True, f"required policy {key!r} was weakened")
    for key in (
        "new_per_claim_or_per_family_axioms_allowed",
        "routine_local_build_may_replay_production_computation",
        "aggregate_invocation_alone_implies_a_mathematical_claim",
        "inner_boolean_kernel_alone_counts_as_a_concrete_program",
        "downstream_source_program_alone_counts_as_static_cpu_compilation",
        "closed_receipt_slot_alone_counts_as_an_accepted_receipt",
    ):
        _require(policy.get(key) is False, f"required policy {key!r} was widened")

    local_catalogs = specification["local_catalogs"]
    for key in (
        "external_claims",
        "external_bridge_status",
        "native_families",
        "native_members",
        "native_architecture_bridge_status",
        "native_architecture_catalog",
        "native_aggregate_capstone",
        "deterministic_program_obligation_roster",
        "closed_source_program_catalog",
        "closed_accepted_receipt_roster",
        "fixed_decision_program",
    ):
        _require(
            isinstance(local_catalogs.get(key), str)
            and bool(local_catalogs[key]),
            f"required local catalog path {key!r} is missing",
        )
    external_path = REPOSITORY_ROOT / local_catalogs["external_claims"]
    external_bridge_path = (
        REPOSITORY_ROOT / local_catalogs["external_bridge_status"]
    )
    native_path = REPOSITORY_ROOT / local_catalogs["native_families"]
    native_members_path = REPOSITORY_ROOT / local_catalogs["native_members"]
    native_architecture_status_path = (
        REPOSITORY_ROOT
        / local_catalogs["native_architecture_bridge_status"]
    )
    native_architecture_catalog_path = (
        REPOSITORY_ROOT / local_catalogs["native_architecture_catalog"]
    )
    native_aggregate_capstone_path = (
        REPOSITORY_ROOT / local_catalogs["native_aggregate_capstone"]
    )
    deterministic_program_roster_path = (
        REPOSITORY_ROOT
        / local_catalogs["deterministic_program_obligation_roster"]
    )
    closed_source_program_catalog_path = (
        REPOSITORY_ROOT / local_catalogs["closed_source_program_catalog"]
    )
    closed_accepted_receipt_roster_path = (
        REPOSITORY_ROOT / local_catalogs["closed_accepted_receipt_roster"]
    )
    fixed_decision_program_path = (
        REPOSITORY_ROOT / local_catalogs["fixed_decision_program"]
    )
    try:
        external = load_and_validate_closure(
            external_path, repository_root=REPOSITORY_ROOT
        )
        external_bridge = _load(external_bridge_path)
        native = load_and_validate_native_catalog(native_path)
        native_members = load_and_validate_native_members(native_members_path)
        native_architecture_status = (
            load_and_validate_native_architecture_status(
                native_architecture_status_path,
                native_path,
                native_members_path,
                claude_math_root=claude_math_root,
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
        CompactReceiptClosureError,
        CatalogError,
        CrosswalkError,
        NativeArchitectureStatusError,
    ) as error:
        raise FullTrustBoundaryError(
            f"component trust catalog is invalid: {error}"
        ) from error

    try:
        native_architecture_catalog_source = (
            native_architecture_catalog_path.read_text(encoding="utf-8")
        )
        native_aggregate_capstone_source = (
            native_aggregate_capstone_path.read_text(encoding="utf-8")
        )
        deterministic_program_roster_source = (
            deterministic_program_roster_path.read_text(encoding="utf-8")
        )
        closed_source_program_catalog_source = (
            closed_source_program_catalog_path.read_text(encoding="utf-8")
        )
        closed_accepted_receipt_roster_source = (
            closed_accepted_receipt_roster_path.read_text(encoding="utf-8")
        )
        fixed_decision_program_source = (
            fixed_decision_program_path.read_text(encoding="utf-8")
        )
    except OSError as error:
        raise FullTrustBoundaryError(
            f"cannot read a required local Lean trust catalog: {error}"
        ) from error
    for required in (
        "inductive NativeFamily where",
        "def aggregateInvocation",
        ".nativeGeneratedAggregateProductionV1",
        "theorem generatedRootCount_sum",
        "(all.map generatedRootCount).sum = 1371",
        "theorem sourceDecisionCount_sum",
        "(all.map sourceDecisionCount).sum = 1214",
        "theorem aggregateInvocation_currently_uninstalled",
    ):
        _require(
            required in native_architecture_catalog_source,
            f"native architecture catalog lacks {required!r}",
        )
    for required in (
        "def PhysicalOutcome : Prop",
        "def ClosedDecisionRefinement",
        "theorem claim_of_physicalOutcome",
        "FixedDecisionChecker.claim_of_compactRun",
        "theorem no_current_physicalOutcome",
    ):
        _require(
            required in native_aggregate_capstone_source,
            f"native aggregate capstone lacks {required!r}",
        )
    for required in (
        "structure ClosedRoster",
        "def obligation",
        "theorem sourceToChecker",
        "theorem registeredCampaignCount",
        "RegisteredArchitectureInvocation.all.length = 12",
    ):
        _require(
            required in deterministic_program_roster_source,
            f"deterministic program roster lacks {required!r}",
        )
    closed_source_program_audit = _audit_closed_source_program_catalog(
        closed_source_program_catalog_source
    )
    closed_receipt_roster_audit = _audit_closed_accepted_receipt_roster(
        closed_accepted_receipt_roster_source
    )
    for required in (
        "def run",
        "def program",
        "theorem refinesNativeChecker",
        "def certificate",
        "FixedDecisionChecker.nativeChecker",
    ):
        _require(
            required in fixed_decision_program_source,
            f"fixed decision source program lacks {required!r}",
        )

    program_boundary = specification.get("program_boundary")
    _require(
        isinstance(program_boundary, dict),
        "full-boundary specification lacks program_boundary",
    )
    _require(
        program_boundary.get("closed_catalog_campaign_count")
        == closed_source_program_audit["campaigns"]
        == 11,
        "closed source-program campaign count differs from the exact Lean "
        "catalog",
    )
    _require(
        program_boundary.get("closed_catalog_required_proof_program_gaps")
        == closed_source_program_audit["required_proof_program_gaps"]
        == 10,
        "closed source-program proof-gap count differs from the exact Lean "
        "catalog",
    )
    _require(
        program_boundary.get("closed_catalog_concrete_program_count")
        == closed_source_program_audit["concrete_programs"]
        == 1,
        "closed source-program concrete count must remain exactly one",
    )
    receipt_boundary = specification.get("receipt_boundary")
    _require(
        isinstance(receipt_boundary, dict),
        "full-boundary specification lacks receipt_boundary",
    )
    _require(
        receipt_boundary.get("proof_authorizing_campaign_count")
        == closed_receipt_roster_audit["proof_authorizing_campaigns"]
        == 11,
        "closed receipt roster must have exactly eleven proof-authorizing "
        "campaigns",
    )
    _require(
        receipt_boundary.get("external_campaign_count")
        == closed_receipt_roster_audit["external_campaigns"]
        == 10,
        "closed receipt roster must have exactly ten external campaigns",
    )
    _require(
        receipt_boundary.get("native_aggregate_campaign_count")
        == closed_receipt_roster_audit["native_aggregate_campaigns"]
        == 1,
        "closed receipt roster must have exactly one native aggregate campaign",
    )
    _require(
        receipt_boundary.get("closed_receipt_slot_count")
        == closed_receipt_roster_audit["closed_receipt_slots"]
        == 11,
        "closed receipt-slot count differs from the exact Lean roster",
    )
    for key, audited_key in (
        ("imported_receipt_count", "imported_receipts"),
        ("accepted_receipt_count", "accepted_receipts"),
    ):
        _require(
            receipt_boundary.get(key)
            == closed_receipt_roster_audit[audited_key]
            == 0,
            f"{key} cannot advance while no_current_requiredRoster holds",
        )
    aggregate_program = program_boundary.get("downstream_native_aggregate")
    _require(
        isinstance(aggregate_program, dict),
        "program boundary lacks downstream_native_aggregate",
    )
    for key in (
        "source_program_relative_path",
        "source_program_declaration",
        "remaining_roster_relative_path",
        "remaining_roster_declaration",
    ):
        _require(
            isinstance(aggregate_program.get(key), str)
            and bool(aggregate_program[key]),
            f"downstream native aggregate lacks {key!r}",
        )
    _require(
        aggregate_program.get("repository") == "claude_math",
        "downstream aggregate program must remain in the application package",
    )
    _require(
        aggregate_program.get("source_program_defined") is True,
        "downstream aggregate source program must remain explicitly catalogued",
    )
    for key in (
        "static_cpu_compilation_present",
        "exact_executable_refinement_present",
    ):
        _require(
            aggregate_program.get(key) is False,
            f"downstream aggregate {key} advanced without compiler evidence",
        )

    external_names = [
        row["lean_claim"]
        for row in external["claims"]
        if row["catalog_kind"] == "external_atom"
    ]
    _require(
        len(external_names) == len(set(external_names)),
        "duplicate external Lean claims in compact closure catalog",
    )
    _require(
        external_bridge.get("schema_version") == 1
        and external_bridge.get("kind")
        == "sparkinterval.ternary-goldbach.external-atom-bridge-status.v1",
        "unexpected external bridge-status catalog",
    )
    external_bridge_rows = external_bridge.get("atoms")
    _require(
        isinstance(external_bridge_rows, list)
        and len(external_bridge_rows) == len(external_names),
        "external bridge-status rows do not cover the closed inventory",
    )
    _require(
        [row.get("lean_declaration") for row in external_bridge_rows]
        == external_names,
        "external bridge-status declarations differ from the closed inventory",
    )
    external_bridge_summary = external_bridge.get("summary")
    _require(
        isinstance(external_bridge_summary, dict),
        "external bridge-status summary is missing",
    )
    for stage in (
        "source_theorem_mapped",
        "checker_acceptance_mapped",
        "registered_physical_outcome_mapped",
    ):
        _require(
            external_bridge_summary.get(stage) == len(external_names)
            and all(row.get("stages", {}).get(stage) is True
                    for row in external_bridge_rows),
            f"external bridge stage {stage!r} is incomplete",
        )
    for stage in (
        "exact_executable_refinement_present",
        "reviewed_receipt_present",
        "live_provider_switched",
        "fresh_retirement_confirmed",
    ):
        _require(
            external_bridge_summary.get(stage) == 0
            and all(row.get("stages", {}).get(stage) is False
                    for row in external_bridge_rows),
            f"external bridge stage {stage!r} advanced without evidence",
        )
    external_physical_campaign_count = external_bridge_summary.get(
        "physical_campaign_count"
    )
    _require(
        external_physical_campaign_count == 10,
        "external bridge-status must use exactly ten physical campaigns",
    )
    native_rows = native["families"]
    native_architecture_summary = native_architecture_status["summary"]
    family_names = [row["lean_family"] for row in native_rows]
    _require(
        len(family_names) == len(set(family_names)),
        "duplicate native family in closure catalog",
    )
    native_atom_count = sum(
        row["authoritative_snapshot"]["native_atom_count"]
        for row in native_rows
    )
    member_rows = native_members["members"]
    member_summary = native_members["summary"]
    _require(
        len(member_rows) == native_atom_count,
        "native member crosswalk does not cover the family inventory",
    )
    for row in native_rows:
        family = row["lean_family"]
        family_members = [
            member for member in member_rows if member["family"] == family
        ]
        _require(
            len(family_members)
            == row["authoritative_snapshot"]["native_atom_count"],
            f"{family}: member crosswalk count differs from family catalog",
        )
        _require(
            _recompute_native_family_digest(family_members, family)
            == row["authoritative_snapshot"]["member_digest"],
            f"{family}: member crosswalk digest differs from family catalog",
        )

    expected = specification["expected"]
    foundations = expected["foundation_names"]
    observed_counts = {
        "foundations": len(foundations),
        "named_external_or_source": len(external_names),
        "native_generated": native_atom_count,
        "native_families": len(native_rows),
    }
    _require(
        observed_counts["foundations"] == expected["foundation_count"],
        "foundation count differs from full-boundary specification",
    )
    _require(
        observed_counts["named_external_or_source"]
        == expected["named_external_or_source_count"],
        "external claim count differs from full-boundary specification",
    )
    _require(
        observed_counts["native_generated"] == expected["native_generated_count"],
        "native atom count differs from full-boundary specification",
    )
    _require(
        observed_counts["native_families"] == expected["native_family_count"],
        "native family count differs from full-boundary specification",
    )
    total = (
        observed_counts["foundations"]
        + observed_counts["named_external_or_source"]
        + observed_counts["native_generated"]
    )
    _require(total == expected["total_axiom_count"], "total axiom count mismatch")
    _require(
        total - observed_counts["foundations"]
        == expected["computational_or_source_count"],
        "non-foundational trust-root count mismatch",
    )

    completion = specification["completion_state"]
    _require(
        completion["classification"] == "staged-not-live",
        "completion state must remain staged until a fresh capstone build",
    )
    _require(
        completion["external_roots_catalogued"] == len(external_names),
        "external catalogued count differs from the closed inventory",
    )
    _require(
        completion[
            "external_roots_with_conditional_checker_to_claim_theorem"
        ]
        == len(external_names),
        "conditional external theorem count differs from the closed inventory",
    )
    _require(
        completion[
            "external_roots_with_conditional_registered_physical_outcome_to_claim_theorem"
        ]
        == external_bridge_summary["registered_physical_outcome_mapped"],
        "registered physical-outcome theorem count differs from bridge status",
    )
    _require(
        completion[
            "external_physical_campaigns_with_closed_refinement_obligation"
        ]
        == external_physical_campaign_count,
        "closed external refinement-obligation count differs from bridge status",
    )
    _require(
        completion["native_roots_assigned_a_family_route"] == native_atom_count,
        "native route-assignment count differs from the family inventory",
    )
    _require(
        completion["native_roots_with_member_level_status_rows"]
        == len(member_rows),
        "native member-status count differs from the member crosswalk",
    )
    _require(
        completion["native_roots_with_closed_aggregate_invocation_route"]
        == native_atom_count,
        "native aggregate route does not cover every generated root",
    )
    source_decision_count = len(
        {member["origin_declaration"] for member in member_rows}
    )
    _require(
        completion[
            "native_source_decisions_with_closed_aggregate_invocation_route"
        ]
        == source_decision_count
        == 1214,
        "native aggregate route does not cover every source decision",
    )
    _require(
        completion["native_families_with_closed_aggregate_invocation_route"]
        == len(native_rows),
        "native aggregate route does not cover every family",
    )
    _require(
        completion["native_aggregate_physical_campaigns"] == 1,
        "native aggregate route must use one closed physical campaign",
    )
    _require(
        completion[
            "native_aggregate_families_with_exact_fixed_checker_bundle"
        ]
        == native_architecture_summary[
            "exact_fixed_checker_bundle_mapped_families"
        ],
        "native fixed-checker family count differs from bridge status",
    )
    _require(
        completion[
            "native_aggregate_roots_with_exact_fixed_checker_bundle"
        ]
        == native_architecture_summary[
            "exact_fixed_checker_bundle_mapped_roots"
        ],
        "native fixed-checker root count differs from bridge status",
    )
    _require(
        completion[
            "native_aggregate_source_decisions_with_exact_fixed_checker_bundle"
        ]
        == native_architecture_summary[
            "exact_fixed_checker_bundle_mapped_source_decisions"
        ],
        "native fixed-checker source-decision count differs from bridge status",
    )
    _require(
        completion["native_roots_with_target_location_mapped"]
        == member_summary["staged_replacement_target_mapped"],
        "native target-location count differs from the member crosswalk",
    )
    _require(
        completion["native_roots_without_target_location"]
        == member_summary["without_replacement_target"],
        "native missing-target count differs from the member crosswalk",
    )
    _require(
        completion[
            "native_compact_fallback_roots_with_conditional_fold_to_claim_theorem"
        ]
        == 3,
        "the Ramaré compact fallback must account for exactly three roots",
    )
    _require(
        completion[
            "physical_campaigns_with_deterministic_program_obligation"
        ]
        == 12,
        "the deterministic program roster must cover all twelve campaigns",
    )
    _require(
        completion[
            "external_or_fallback_campaigns_audited_for_closed_source_program"
        ]
        == closed_source_program_audit["campaigns"]
        == 11,
        "the closed source-program audit must cover ten external campaigns "
        "plus the Ramaré fallback",
    )
    _require(
        completion[
            "external_or_fallback_campaigns_with_required_proof_program_gap"
        ]
        == closed_source_program_audit["required_proof_program_gaps"]
        == 10,
        "exactly ten non-aggregate campaigns must retain explicit "
        "proof-program gaps",
    )
    _require(
        completion["native_aggregate_source_program_defined_downstream"] == 1,
        "the exact downstream all-native source program must be distinguished "
        "from the ten local gaps and complete CDEM artifact program",
    )
    _require(
        completion[
            "proof_authorizing_campaigns_with_closed_receipt_slot"
        ]
        == closed_receipt_roster_audit["closed_receipt_slots"]
        == 11,
        "the closed receipt roster must expose exactly eleven typed slots",
    )
    _require(
        completion[
            "external_or_fallback_campaigns_with_concrete_program_certificate"
        ]
        == closed_source_program_audit["concrete_programs"]
        == 1,
        "the closed source-program audit must expose exactly the complete "
        "CDEM artifact program",
    )
    _require(
        completion["physical_campaigns_with_concrete_program_certificate"]
        == closed_source_program_audit["concrete_programs"]
        == 1,
        "exactly one physical campaign may have a concrete program "
        "certificate",
    )
    for key in (
        "external_campaigns_with_exact_executable_refinement",
        "external_campaigns_with_installed_receipt_authority",
        "native_roots_with_member_level_replacement_mapped_by_this_catalog",
        "native_compact_fallback_campaigns_with_exact_executable_refinement",
        "native_compact_fallback_campaigns_with_installed_receipt_authority",
        "native_aggregate_campaigns_with_exact_executable_refinement",
        "native_aggregate_campaigns_with_installed_receipt_authority",
        "native_aggregate_source_program_with_static_cpu_compilation",
        "proof_authorizing_campaigns_with_imported_receipt",
        "proof_authorizing_campaigns_with_accepted_receipt",
        "live_provider_integrations_established_by_this_catalog",
        "roots_retired_by_a_fresh_post_migration_axiom_print",
    ):
        _require(
            completion[key] == 0,
            f"{key} cannot be advanced without its separate completion evidence",
        )

    authoritative_checked = False
    downstream_aggregate_program_checked = False
    if claude_math_root is not None:
        authority = specification["authority"]
        trace_path = claude_math_root / authority["statement_trace_relative_path"]
        manifest_path = claude_math_root / authority["native_manifest_relative_path"]
        citation_path = (
            claude_math_root / authority["citation_inventory_relative_path"]
        )
        for path, expected_hash in (
            (trace_path, authority["statement_trace_sha256"]),
            (manifest_path, authority["native_manifest_sha256"]),
            (citation_path, authority["citation_inventory_sha256"]),
        ):
            _require(
                _sha256(path) == expected_hash,
                f"{path}: SHA-256 differs from authoritative snapshot",
            )

        aggregate_source_path = (
            claude_math_root
            / aggregate_program["source_program_relative_path"]
        )
        aggregate_roster_path = (
            claude_math_root
            / aggregate_program["remaining_roster_relative_path"]
        )
        try:
            aggregate_source = aggregate_source_path.read_text(
                encoding="utf-8"
            )
            aggregate_roster = aggregate_roster_path.read_text(
                encoding="utf-8"
            )
        except OSError as error:
            raise FullTrustBoundaryError(
                "cannot read downstream all-native source-program boundary: "
                f"{error}"
            ) from error
        for required in (
            "def deterministicProgramCertificate",
            "FixedDecisionProgram.certificate",
            "theorem deterministicProgramRefinesNativeChecker",
        ):
            _require(
                required in aggregate_source,
                f"downstream aggregate source program lacks {required!r}",
            )
        remaining_match = _one_match(
            r"structure RemainingPrograms : Type where"
            r"(?P<body>.*?)(?=\n\n/-- The exact closed twelve-campaign)",
            aggregate_roster,
            "downstream RemainingPrograms structure",
        )
        remaining_fields = re.findall(
            r"^\s{2}([A-Za-z0-9_]+)\s*:",
            remaining_match.group("body"),
            flags=re.MULTILINE,
        )
        _require(
            remaining_fields
            == [
                campaign for campaign, _invocation, _missing
                in EXPECTED_CLOSED_SOURCE_PROGRAM_CAMPAIGNS
            ],
            "downstream RemainingPrograms is not the same exact eleven "
            "campaigns as the closed source-program catalog",
        )
        for required in (
            "def closedRoster",
            "nativeGeneratedAggregate :=\n    deterministicProgramCertificate",
            "theorem aggregateProgram_is_fixedDecision",
        ):
            _require(
                required in aggregate_roster,
                f"downstream deterministic roster lacks {required!r}",
            )
        downstream_aggregate_program_checked = True

        manifest = _load(manifest_path)
        citation = _load(citation_path)
        try:
            validate_native_members_manifest(native_members, manifest_path)
            validate_native_member_evidence_paths(
                native_members,
                claude_math_root.resolve(),
                REPOSITORY_ROOT.resolve(),
            )
        except (
            OSError,
            KeyError,
            json.JSONDecodeError,
            CrosswalkError,
        ) as error:
            raise FullTrustBoundaryError(
                f"native member crosswalk differs from authority: {error}"
            ) from error
        manifest_foundations = [row["name"] for row in manifest["foundations"]]
        manifest_external = [
            row["name"] for row in manifest["named_external_or_source"]
        ]
        manifest_native = [row["name"] for row in manifest["native_entries"]]
        _require(
            set(manifest_foundations) == set(foundations),
            "foundation names differ from authoritative manifest",
        )
        _require(
            set(manifest_external) == set(external_names),
            "compact external catalog differs from authoritative manifest",
        )
        citation_names = [row["axiom"] for row in citation["entries"]]
        _require(
            set(citation_names) == set(manifest_external)
            and len(citation_names) == len(manifest_external),
            "citation inventory is not a bijection with named source atoms",
        )

        manifest_family_rows = {
            row["family"]: row for row in manifest["native_families"]
        }
        _require(
            set(manifest_family_rows) == set(family_names),
            "native closure family set differs from authoritative manifest",
        )
        for row in native_rows:
            family = row["lean_family"]
            authoritative_row = manifest_family_rows[family]
            _require(
                authoritative_row["count"]
                == row["authoritative_snapshot"]["native_atom_count"],
                f"{family}: native family count differs",
            )
            recomputed = _recompute_native_family_digest(
                manifest["native_entries"], family
            )
            _require(
                authoritative_row["member_digest"] == recomputed,
                f"{family}: authoritative member digest does not recompute",
            )
            _require(
                row["authoritative_snapshot"]["member_digest"] == recomputed,
                f"{family}: local member digest differs from authority",
            )

        manifest_names = (
            manifest_foundations + manifest_external + manifest_native
        )
        trace_names = _trace_axiom_names(
            _load(trace_path), specification["root_declaration"]
        )
        _require(
            len(trace_names) == expected["total_axiom_count"],
            "Statement.trace axiom count differs from snapshot",
        )
        _resolve_trace_names(trace_names, manifest_names)
        authoritative_checked = True

    return {
        "authoritative_snapshot_checked": authoritative_checked,
        "downstream_aggregate_source_program_checked":
            downstream_aggregate_program_checked,
        "foundations": observed_counts["foundations"],
        "named_external_or_source": observed_counts[
            "named_external_or_source"
        ],
        "native_families": observed_counts["native_families"],
        "native_generated": observed_counts["native_generated"],
        "native_members_statused": len(member_rows),
        "native_members_target_mapped": member_summary[
            "staged_replacement_target_mapped"
        ],
        "native_members_unmapped": member_summary[
            "without_replacement_target"
        ],
        "native_roots_with_aggregate_invocation_route": native_atom_count,
        "native_source_decisions_with_aggregate_invocation_route":
            source_decision_count,
        "native_aggregate_physical_campaigns": 1,
        "native_aggregate_fixed_checker_bundles":
            native_architecture_summary[
                "exact_fixed_checker_bundle_mapped_families"
            ],
        "native_aggregate_fixed_checker_roots":
            native_architecture_summary[
                "exact_fixed_checker_bundle_mapped_roots"
            ],
        "physical_campaigns_with_deterministic_program_obligation": 12,
        "closed_source_program_audited_campaigns":
            closed_source_program_audit["campaigns"],
        "closed_source_program_required_gaps":
            closed_source_program_audit["required_proof_program_gaps"],
        "closed_source_program_concrete_campaigns":
            closed_source_program_audit["concrete_programs"],
        "native_aggregate_source_program_catalogued": 1,
        "native_aggregate_static_cpu_compilations": 0,
        "physical_campaigns_with_concrete_program_certificate":
            closed_source_program_audit["concrete_programs"],
        "proof_authorizing_campaigns":
            closed_receipt_roster_audit["proof_authorizing_campaigns"],
        "closed_receipt_slots":
            closed_receipt_roster_audit["closed_receipt_slots"],
        "imported_receipts":
            closed_receipt_roster_audit["imported_receipts"],
        "accepted_receipts":
            closed_receipt_roster_audit["accepted_receipts"],
        "external_roots_registered_physical_mapped":
            external_bridge_summary["registered_physical_outcome_mapped"],
        "external_physical_campaigns":
            external_physical_campaign_count,
        "non_foundational_roots": expected["computational_or_source_count"],
        "exact_executable_refinements": 0,
        "installed_receipt_authorities": 0,
        "freshly_retired_roots": 0,
        "total_roots": total,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="audit every trust root in the last fresh TG capstone"
    )
    parser.add_argument(
        "--specification", type=Path, default=DEFAULT_SPECIFICATION
    )
    parser.add_argument(
        "--claude-math-root",
        type=Path,
        help="optionally verify the pinned authoritative sibling artifacts",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        summary = audit(
            arguments.specification,
            claude_math_root=arguments.claude_math_root,
        )
    except FullTrustBoundaryError as error:
        print(f"full trust-boundary audit failed: {error}")
        return 1
    if arguments.json:
        print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    else:
        authority = (
            "including pinned Statement.trace"
            if summary["authoritative_snapshot_checked"]
            else "checked-in catalogs only"
        )
        print(
            "full TG trust-boundary audit passed: "
            f"{summary['total_roots']} roots = "
            f"{summary['foundations']} foundations + "
            f"{summary['named_external_or_source']} named source atoms + "
            f"{summary['native_generated']} native atoms in "
            f"{summary['native_families']} families ({authority}); "
            f"{summary['closed_source_program_required_gaps']} "
            "external/fallback proof-program gaps / "
            f"{summary['closed_source_program_concrete_campaigns']} concrete "
            "catalog programs; downstream aggregate source program catalogued "
            "but 0 static-CPU compilations; "
            f"{summary['closed_receipt_slots']} closed receipt slots / "
            f"{summary['imported_receipts']} imported receipts / "
            f"{summary['accepted_receipts']} accepted receipts; "
            "0 exact executable refinements / 0 installed receipts / "
            "0 fresh-print retirements"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
