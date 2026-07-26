#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build the production-data-free member crosswalk for TG native roots.

The inputs are the last-fresh ``native_decide_manifest.json`` and one output
of ``scripts/tg_native_static_inventory.py`` from ``claude_math``.  The
result deliberately keeps only declaration identities, digests, static
selection states, and small source references.  It does not copy expanded
propositions, generated certificates, production rows, or traces.

A replacement mapping means only that a concrete target declaration or
artifact has been located.  It does *not* mean that statement identity, a
live provider build, or capstone retirement has been established.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from build_tg_native_architecture_bridge_status import AGGREGATE_ADAPTERS


CHANGED = "source_selection_changed_or_removed"
UNREACHABLE = "source_selection_unchanged_import_unreachable"
REACHABLE = "source_selection_unchanged_import_reachable"


LEAN_FAMILY_TO_CLOSURE_ID: dict[str, str] = {
    "AnalyticNT.Chebyshev": "analyticnt-chebyshev",
    "AnalyticNT.LargeSieve": "analyticnt-large-sieve",
    "HelfgottCertificates": "helfgott-certificates",
    "Math.Problems.TernaryGoldbach.Certs":
        "ternary-goldbach-arithmetic-certs",
    "Math.Problems.TernaryGoldbach.MinorArcs.Chapter14":
        "chapter14-minor-arcs",
    "MathExtras.NumberTheory.Analysis": "mean-value-floor-grid",
    "MathExtras.NumberTheory.Certs": "little-mertens-liouville",
    "MathExtras.NumberTheory.Helfgott": "helfgott-analytic-intervals",
    "MathExtras.NumberTheory.Helfgott.Certs": "helfgott-section24-head",
    "MathExtras.NumberTheory.LSeries": "chirre-helfgott-a6",
    "MathExtras.NumberTheory.Mertens": "ramare-little-mertens",
    "MathExtras.NumberTheory.Vinogradov": "vinogradov-finite-intervals",
    "Rs62Certificates": "rosser-schoenfeld",
    "TGNativeCertificates": "standalone-tg-native",
    "TGNativeCertificates.Ramare": "ramare-production-folds",
}


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _declaration_tail(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def _requires_semantic_aggregate_target(entry: Mapping[str, Any]) -> bool:
    """Select roots whose old private name is not the replacement boundary.

    The six Lemma-3.7 roots are replaced by public Q96 rectangle decisions
    and ordinary soundness theorems in the aggregate family adapter.  A
    same-named private theorem still exists in its historical consumer file,
    but treating that private implementation detail as the replacement would
    lose the explicit source-semantic Q96 boundary.
    """

    return (
        entry["family"] == "MathExtras.NumberTheory.Helfgott"
        and "Lemma37HighQLargeSharpBShape"
        in str(entry["origin_declaration"])
    )


def _has_declaration(path: Path, declaration: str) -> bool:
    if not path.is_file():
        return False
    tail = re.escape(_declaration_tail(declaration))
    pattern = re.compile(
        r"(?m)^\s*"
        r"(?:(?:private|protected|noncomputable)\s+)*"
        r"(?:theorem|lemma|def|abbrev|structure)\s+"
        + tail
        + r"(?=[\s(:])"
    )
    return pattern.search(path.read_text(encoding="utf-8")) is not None


def _status_by_name(report: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    statuses = report["baseline_comparison"]["statuses"]
    for status, grouping in statuses.items():
        for family in grouping["families"]:
            for source_file in family["files"]:
                for origin in source_file["origin_declarations"]:
                    for name in origin["native_axiom_names"]:
                        if name in result:
                            raise ValueError(f"duplicate static member {name}")
                        result[name] = status
    return result


def _platt_split_target(tail: str) -> tuple[str, str] | None:
    stems = {
        "endpointHighInitialCertificate_holds": "HighInitialTrace.lean",
        "endpointHighMiddleCertificate_holds": "HighMiddleTrace.lean",
        "endpointHighNearCertificate_holds": "HighNearTrace.lean",
        "endpointHighTailCertificate_holds": "HighTailTrace.lean",
        "endpointLowNearCertificate_holds": "LowNearTrace.lean",
        "endpointLowTailCertificate_holds": "LowTailTrace.lean",
        "endpointMidNearCertificate_holds": "MidNearTrace.lean",
        "endpointMidTailCertificate_holds": "MidTailTrace.lean",
        "endpointMidTransitionCertificate_holds": "MidTransitionTrace.lean",
        "endpointSafeBundle_holds": "Safe.lean",
    }
    filename = stems.get(tail)
    if filename is None:
        return None
    path = (
        "Math/Problems/TernaryGoldbach/MinorArcs/Chapter14/"
        "PaperEq1314SmallQHighCrossoverPlattSplitOrdinary/"
        + filename
    )
    declaration = (
        "Math.Problems.TernaryGoldbach."
        "Eq1314SmallQHighCrossoverPlattSplit."
        + tail
    )
    return path, declaration


def _manual_claude_target(
    entry: Mapping[str, Any],
) -> tuple[str, str, str] | None:
    """Return ``(kind, path, declaration)`` for moved/grouped replacements."""

    origin = str(entry["origin_declaration"])
    tail = _declaration_tail(origin)
    source = str(entry["source_witness"]["path"])

    if entry["family"] == "MathExtras.NumberTheory.Vinogradov":
        return (
            "conditional_attested_source_shaped_family_bundle",
            "Math/Problems/TernaryGoldbach/"
            "CompactVinogradovNativeInputs.lean",
            "Math.Problems.TernaryGoldbach."
            "CompactVinogradovNativeInputs."
            "sourceClaims_of_registeredPhysicalOutcome",
        )

    platt = _platt_split_target(tail)
    if platt is not None and "PlattSplit" in source:
        return ("moved_source_shaped_theorem", platt[0], platt[1])

    exact: dict[str, tuple[str, str, str]] = {
        "AnalyticNT.ChebyshevPsi.checkAll_1e7_sharp": (
            "compact_event_contract_bridge",
            "ext/analytic_nt/AnalyticNT/Chebyshev/"
            "PsiCompactCertificateContracts.lean",
            "AnalyticNT.ChebyshevPsi.checkAll_1e7_sharp_of_compact",
        ),
        "AnalyticNT.ChebyshevPsi.checkAll_psiSubTheta_1e6": (
            "compact_event_contract_bridge",
            "ext/analytic_nt/AnalyticNT/Chebyshev/"
            "PsiCompactCertificateContracts.lean",
            "AnalyticNT.ChebyshevPsi.checkAll_psiSubTheta_1e6_of_compact",
        ),
        "AnalyticNT.ChebyshevPsi.checkFrom_2e6_4e6_rr14": (
            "compact_event_contract_bridge",
            "ext/analytic_nt/AnalyticNT/Chebyshev/"
            "PsiCompactCertificateContracts.lean",
            "AnalyticNT.ChebyshevPsi.checkFrom_2e6_4e6_rr14_of_compact",
        ),
        "Math.Problems.TernaryGoldbach.Eq1315HighRepairPrefixCost."
        "prefixCostCertificate_holds": (
            "moved_source_shaped_theorem",
            "Math/Problems/TernaryGoldbach/MinorArcs/Chapter14/"
            "PaperEq1315HighRepairPrefixCostOrdinary.lean",
            "Math.Problems.TernaryGoldbach.Eq1315HighRepairPrefixCost."
            "prefixCostCertificate_holds",
        ),
        "Math.Problems.TernaryGoldbach.Eq1315HighRepairPrefixCost."
        "prefixCostSafe_holds": (
            "moved_source_shaped_theorem",
            "Math/Problems/TernaryGoldbach/MinorArcs/Chapter14/"
            "PaperEq1315HighRepairPrefixCostOrdinary.lean",
            "Math.Problems.TernaryGoldbach.Eq1315HighRepairPrefixCost."
            "prefixCostSafe_holds",
        ),
        "Math.Problems.TernaryGoldbach.HEnvFloorCert.seg_certs": (
            "moved_source_shaped_theorem",
            "Math/Problems/TernaryGoldbach/MinorArcs/Chapter14/"
            "PaperEq1314HEnvelopeFloorOrdinary.lean",
            "Math.Problems.TernaryGoldbach.HEnvFloorCert.seg_certs",
        ),
        "MathExtras.Helfgott.H1Margin.h1Margin_cert": (
            "candidate_stronger_ordinary_declaration",
            "MathExtras/NumberTheory/Helfgott/H1MarginOrdinary.lean",
            "MathExtras.Helfgott.H1MarginOrdinary.h1MarginReal_nonneg",
        ),
        "MathExtras.Helfgott.SIIMargin.mkA_cert": (
            "candidate_stronger_ordinary_declaration",
            "ext/helfgott_certificates/HelfgottCertificates/"
            "SIIMarginFixed/CertificateA.lean",
            "HelfgottCertificates.SIIMarginFixed.marginA_nonneg",
        ),
        "MathExtras.Helfgott.SIIMargin.mkB_cert": (
            "candidate_stronger_ordinary_declaration",
            "ext/helfgott_certificates/HelfgottCertificates/"
            "SIIMarginFixed/CertificateB.lean",
            "HelfgottCertificates.SIIMarginFixed.marginB_nonneg",
        ),
        "MathExtras.Helfgott.SIIMargin.mkC_cert": (
            "candidate_stronger_ordinary_declaration",
            "ext/helfgott_certificates/HelfgottCertificates/"
            "SIIMarginFixed/CertificateC.lean",
            "HelfgottCertificates.SIIMarginFixed.marginC_nonneg",
        ),
        "MathExtras.RS62Ladder.s410_prodN": (
            "grouped_replay_instantiation",
            "ext/rs62_certificates/Rs62Certificates/"
            "RS62LongFoldFull.lean",
            "MathExtras.RS62Ladder.s410_prodN",
        ),
        "MathExtras.RS62Ladder.s410_prodD": (
            "grouped_replay_instantiation",
            "ext/rs62_certificates/Rs62Certificates/"
            "RS62LongFoldFull.lean",
            "MathExtras.RS62Ladder.s410_prodD",
        ),
        "TGNativeCertificates.PrimeLogSquare219."
        "check_prime_log_square_2_19_full": (
            "candidate_stronger_ordinary_declaration",
            "ext/tg_native_certificates/TGNativeCertificates/"
            "PrimeLogSquare219Cert.lean",
            "TGNativeCertificates.PrimeLogSquare219."
            "finite_check_prime_log_square_2_19",
        ),
        "MathExtras.Helfgott.Section24.Head30000.scan_ok_cert": (
            "ordinary_source_bridge",
            "MathExtras/NumberTheory/Helfgott/Certs/"
            "LogWeightedMertensHead30000OrdinaryBridge.lean",
            "MathExtras.Helfgott.Section24."
            "logWeightedMertensHead30000_holds_ordinary",
        ),
        "MathExtras.ChirreHelfgottLem85.EndpointCert."
        "vmHead_1e6_cert": (
            "ordinary_source_contract",
            "MathExtras/NumberTheory/LSeries/"
            "ChirreHelfgottLem85TgEndpointOrdinary.lean",
            "MathExtras.ChirreHelfgottLem85."
            "Lem85FiniteProvider.Ordinary.endpointPrefixContract",
        ),
        "MathExtras.ChirreHelfgottLem85.TgCert."
        "lowerKernel_mid_cert": (
            "ordinary_source_contract",
            "MathExtras/NumberTheory/LSeries/"
            "ChirreHelfgottLem85TgMiddleOrdinaryProvider.lean",
            "MathExtras.ChirreHelfgottLem85."
            "Lem85FiniteProvider.OrdinaryMiddle.middleContract",
        ),
        "Math.Problems.TernaryGoldbach.oddMertensLoAcc_ge": (
            "exact_ordinary_certificate_contract",
            "Math/Problems/TernaryGoldbach/Certs/"
            "OddSquarefreeCombinedOrdinaryContract.lean",
            "Math.Problems.TernaryGoldbach.OddSquarefreeCombinedOrdinary."
            "oddMertensLoAcc_ge_of_certificate",
        ),
        "Math.Problems.TernaryGoldbach.oddMertensHiAcc_le": (
            "exact_ordinary_certificate_contract",
            "Math/Problems/TernaryGoldbach/Certs/"
            "OddSquarefreeCombinedOrdinaryContract.lean",
            "Math.Problems.TernaryGoldbach.OddSquarefreeCombinedOrdinary."
            "oddMertensHiAcc_le_of_certificate",
        ),
        "Math.Problems.TernaryGoldbach.gcdMertensHiAcc_le": (
            "exact_ordinary_certificate_contract",
            "Math/Problems/TernaryGoldbach/Certs/"
            "OddSquarefreeCombinedOrdinaryContract.lean",
            "Math.Problems.TernaryGoldbach.OddSquarefreeCombinedOrdinary."
            "gcdMertensHiAcc_le_of_certificate",
        ),
        "Math.Problems.TernaryGoldbach.phiSqHiAcc_le": (
            "exact_ordinary_certificate_contract",
            "Math/Problems/TernaryGoldbach/Certs/"
            "OddSquarefreeCombinedOrdinaryContract.lean",
            "Math.Problems.TernaryGoldbach.OddSquarefreeCombinedOrdinary."
            "phiSqHiAcc_le_of_certificate",
        ),
        "Math.Problems.TernaryGoldbach.phiSqDiscHiAcc_le": (
            "exact_ordinary_certificate_contract",
            "Math/Problems/TernaryGoldbach/Certs/"
            "OddSquarefreeCombinedOrdinaryContract.lean",
            "Math.Problems.TernaryGoldbach.OddSquarefreeCombinedOrdinary."
            "phiSqDiscHiAcc_le_of_certificate",
        ),
        "Math.Problems.TernaryGoldbach.quinticMertensHiAcc_le": (
            "exact_ordinary_certificate_contract",
            "Math/Problems/TernaryGoldbach/Certs/"
            "OddSquarefreeCombinedOrdinaryContract.lean",
            "Math.Problems.TernaryGoldbach.OddSquarefreeCombinedOrdinary."
            "quinticMertensHiAcc_le_of_certificate",
        ),
        "Math.Problems.TernaryGoldbach.deficitCertAcc_ge": (
            "exact_ordinary_certificate_contract",
            "Math/Problems/TernaryGoldbach/Certs/"
            "SingularSeriesDeficitOrdinaryContract.lean",
            "Math.Problems.TernaryGoldbach.SingularSeriesDeficitOrdinary."
            "deficitCertAcc_ge_of_certificate",
        ),
    }
    if origin in exact:
        return exact[origin]

    if source.startswith(
        "ext/rs62_certificates/Rs62Certificates/RS62AnchorLeaves"
    ):
        return (
            "grouped_replay_artifact",
            "ext/rs62_certificates/Rs62Certificates/RS62LongFoldFull.lean",
            "MathExtras.RS62Ladder.anchor_run",
        )
    if source.endswith("/RS62Ladder314Leaves.lean"):
        return (
            "grouped_replay_artifact",
            "ext/rs62_certificates/Rs62Certificates/RS62LongFoldFull.lean",
            "MathExtras.RS62Ladder.run314_full",
        )
    if "RS62Ladder410Leaves" in source:
        return (
            "grouped_replay_artifact",
            "ext/rs62_certificates/Rs62Certificates/RS62LongFoldFull.lean",
            "MathExtras.RS62Ladder.run410_full",
        )
    if "RS62LadderRangeLeaves" in source and tail.startswith("cR_"):
        index = int(tail.removeprefix("cR_")) + 1
        target = f"runR_{index:03d}"
        return (
            "grouped_prefix_replay_artifact",
            "ext/rs62_certificates/Rs62Certificates/RS62LongFoldFull.lean",
            f"MathExtras.RS62Ladder.{target}",
        )
    return None


def _ramare_gpu_target(
    entry: Mapping[str, Any],
) -> tuple[str, str, str] | None:
    if entry["family"] != "TGNativeCertificates.Ramare":
        return None
    return (
        "compact_family_fallback",
        "SparkInterval/TernaryGoldbach/"
        "RamareNativeFoldsCompactChecker.lean",
        "SparkInterval.TernaryGoldbach.RamareNativeFoldsCompactChecker."
        "sourceClaims_of_compactRun",
    )


def _aggregate_family_target(
    entry: Mapping[str, Any],
) -> tuple[str, str, str, str] | None:
    """Return the fixed conditional aggregate target for a native family.

    This is deliberately a fallback behind any more specific ordinary target.
    It records only that the historical member has a source-shaped family
    bundle and registered-physical-outcome theorem.  The resulting evidence
    remains ``target_location_only``; it does not assert statement identity,
    executable refinement, receipt installation, live wiring, or retirement.
    This distinction matters for semantic consumer replacements of
    inaccessible private historical declarations.
    """

    family_id = LEAN_FAMILY_TO_CLOSURE_ID.get(str(entry["family"]))
    if family_id is None:
        return None
    adapter = AGGREGATE_ADAPTERS.get(family_id)
    if adapter is None:
        return None
    return (
        str(adapter["repository"]),
        "conditional_attested_source_shaped_family_bundle",
        str(adapter["path"]),
        str(adapter["registered_physical_outcome_to_claim"]),
    )


def _make_evidence(
    *,
    repository: str,
    kind: str,
    path: str,
    declaration: str,
) -> dict[str, Any]:
    identity = "\n".join((repository, kind, path, declaration))
    evidence_id = "replacement-" + hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:20]
    return {
        "evidence_id": evidence_id,
        "repository": repository,
        "kind": kind,
        "path": path,
        "declaration": declaration,
        "assurance": "target_location_only",
    }


def build_crosswalk(
    manifest_path: Path,
    static_report_path: Path | None,
    claude_root: Path,
    gpu_root: Path,
    *,
    static_report_bytes: bytes | None = None,
) -> dict[str, Any]:
    manifest_bytes = manifest_path.read_bytes()
    if static_report_bytes is None:
        if static_report_path is None:
            raise ValueError(
                "static_report_path is required unless bytes are supplied"
            )
        report_bytes = static_report_path.read_bytes()
    else:
        report_bytes = static_report_bytes
    manifest = json.loads(manifest_bytes)
    report = json.loads(report_bytes)
    entries = manifest["native_entries"]
    statuses = _status_by_name(report)
    if set(statuses) != {entry["name"] for entry in entries}:
        raise ValueError("static report member set differs from manifest")

    evidences: dict[str, dict[str, Any]] = {}
    members: list[dict[str, Any]] = []
    for entry in sorted(entries, key=lambda row: row["name"]):
        name = str(entry["name"])
        status = statuses[name]
        evidence: dict[str, Any] | None = None

        if status == CHANGED:
            source = str(entry["source_witness"]["path"])
            origin = str(entry["origin_declaration"])
            if (
                not _requires_semantic_aggregate_target(entry)
                and _has_declaration(claude_root / source, origin)
            ):
                evidence = _make_evidence(
                    repository="claude_math",
                    kind="same_origin_declaration_colocated",
                    path=source,
                    declaration=origin,
                )
            else:
                target = _manual_claude_target(entry)
                if target is not None:
                    kind, path, declaration = target
                    if not _has_declaration(claude_root / path, declaration):
                        raise ValueError(
                            f"{name}: target declaration is absent: "
                            f"{path}:{declaration}"
                        )
                    evidence = _make_evidence(
                        repository="claude_math",
                        kind=kind,
                        path=path,
                        declaration=declaration,
                    )
        elif status == UNREACHABLE:
            target = _manual_claude_target(entry)
            if target is not None:
                kind, path, declaration = target
                if not _has_declaration(claude_root / path, declaration):
                    raise ValueError(
                        f"{name}: target declaration is absent: "
                        f"{path}:{declaration}"
                    )
                evidence = _make_evidence(
                    repository="claude_math",
                    kind=kind,
                    path=path,
                    declaration=declaration,
                )
        elif status == REACHABLE:
            target = _manual_claude_target(entry)
            if target is not None:
                kind, path, declaration = target
                if not _has_declaration(claude_root / path, declaration):
                    raise ValueError(
                        f"{name}: target declaration is absent: "
                        f"{path}:{declaration}"
                    )
                evidence = _make_evidence(
                    repository="claude_math",
                    kind=kind,
                    path=path,
                    declaration=declaration,
                )

        gpu_target = _ramare_gpu_target(entry)
        if evidence is None and gpu_target is not None:
            kind, path, declaration = gpu_target
            if not _has_declaration(gpu_root / path, declaration):
                raise ValueError(
                    f"{name}: gpu target declaration is absent: "
                    f"{path}:{declaration}"
                )
            evidence = _make_evidence(
                repository="gpu_prover",
                kind=kind,
                path=path,
                declaration=declaration,
            )

        aggregate_target = _aggregate_family_target(entry)
        if evidence is None and aggregate_target is not None:
            repository, kind, path, declaration = aggregate_target
            root = claude_root if repository == "claude_math" else gpu_root
            if not _has_declaration(root / path, declaration):
                raise ValueError(
                    f"{name}: aggregate target declaration is absent: "
                    f"{repository}:{path}:{declaration}"
                )
            evidence = _make_evidence(
                repository=repository,
                kind=kind,
                path=path,
                declaration=declaration,
            )

        if evidence is None:
            stage = "catalogued_only" if status != CHANGED else (
                "source_selection_changed"
            )
            evidence_ref = None
        else:
            stage = "staged_replacement_target_mapped"
            evidence_ref = evidence["evidence_id"]
            evidences[evidence_ref] = evidence

        members.append(
            {
                "name": name,
                "type_digest": entry["type_digest"],
                "family": entry["family"],
                "source_path": entry["source_witness"]["path"],
                "origin_declaration": entry["origin_declaration"],
                "current_static_projection": status,
                "stage": stage,
                "replacement_evidence_ref": evidence_ref,
            }
        )

    projection_counts = {
        status: sum(
            member["current_static_projection"] == status
            for member in members
        )
        for status in (CHANGED, UNREACHABLE, REACHABLE)
    }
    stage_counts = {
        stage: sum(member["stage"] == stage for member in members)
        for stage in (
            "catalogued_only",
            "source_selection_changed",
            "staged_replacement_target_mapped",
            "live_provider_integrated",
            "fresh_print_retired",
        )
    }
    status_digest_text = "\n".join(
        f"{member['name']}\t{member['current_static_projection']}"
        for member in members
    )

    return {
        "schema_version": 1,
        "kind": (
            "sparkinterval.ternary-goldbach."
            "native-member-crosswalk.v1"
        ),
        "assessment_date": "2026-07-24",
        "classification": (
            "production-data-free-member-audit-not-a-proof-"
            "or-current-axiom-print"
        ),
        "scope": (
            "all 1371 native-generated roots in the last-fresh "
            "ternary_goldbach manifest"
        ),
        "snapshots": {
            "last_fresh_capstone_authority": {
                "status": "authoritative_for_that_completed_build_only",
                "manifest_sha256": _sha256_bytes(manifest_bytes),
                "root_declaration": manifest["root"]["declaration"],
                "root_type_digest": manifest["root"]["type_digest"],
                "native_generated_atoms": 1371,
            },
            "pinned_static_projection_2026_07_23": {
                "status": "static_projection_not_authoritative",
                "member_rows_in_this_crosswalk": False,
                "document_sha256": (
                    "sha256:"
                    "453658b9845829400b18bfbfb94311d302738fc99efe543251"
                    "6761625ba31898"
                ),
                "source_selection_changed_or_removed": 1081,
                "source_selection_unchanged_import_unreachable": 1,
                "source_selection_unchanged_import_reachable": 289,
                "warning": (
                    "the 1081/1/289 snapshot is pinned history and must not "
                    "be merged with the later worktree diagnostic"
                ),
            },
            "current_static_diagnostic_2026_07_24": {
                "status": "static_projection_not_authoritative",
                "static_report_sha256": _sha256_bytes(report_bytes),
                "claude_math_head_commit": report["baseline"]["HEAD_commit"],
                **projection_counts,
                "member_status_digest": _sha256_bytes(
                    status_digest_text.encode("utf-8")
                ),
                "warning": (
                    f"the {projection_counts[CHANGED]}/"
                    f"{projection_counts[UNREACHABLE]}/"
                    f"{projection_counts[REACHABLE]} partition describes "
                    "one dirty source snapshot; it is not a current axiom "
                    "count"
                ),
            },
        },
        "stage_vocabulary": {
            "catalogued_only": (
                "authoritative old root identified; no exact replacement "
                "target is recorded"
            ),
            "source_selection_changed": (
                "the source selection changed, but no exact replacement "
                "target has been located"
            ),
            "staged_replacement_target_mapped": (
                "an exact file and declaration/artifact target is recorded; "
                "statement identity and integration remain unverified"
            ),
            "live_provider_integrated": (
                "reserved for a directly built live consumer using the "
                "replacement"
            ),
            "fresh_print_retired": (
                "reserved for a fresh capstone #print axioms omitting the "
                "old root"
            ),
        },
        "policy": {
            "expanded_propositions_included": False,
            "production_data_included": False,
            "mapping_implies_statement_identity": False,
            "mapping_implies_live_integration": False,
            "mapping_implies_retirement": False,
            "retirement_authority": (
                "fresh source build and #print axioms "
                "Math.Problems.TernaryGoldbach.ternary_goldbach"
            ),
        },
        "summary": {
            "authoritative_native_members": len(members),
            "staged_replacement_target_mapped": stage_counts[
                "staged_replacement_target_mapped"
            ],
            "without_replacement_target": (
                len(members)
                - stage_counts["staged_replacement_target_mapped"]
            ),
            "live_provider_integrated": 0,
            "fresh_print_retired": 0,
            "stage_counts": stage_counts,
            "current_static_projection_counts": projection_counts,
        },
        "replacement_evidence": sorted(
            evidences.values(), key=lambda row: row["evidence_id"]
        ),
        "members": members,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--static-report",
        required=True,
        help="static inventory JSON path, or '-' to read it from stdin",
    )
    parser.add_argument("--claude-root", required=True, type=Path)
    parser.add_argument(
        "--gpu-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        static_report_path: Path | None
        static_report_bytes: bytes | None
        if args.static_report == "-":
            static_report_path = None
            static_report_bytes = sys.stdin.buffer.read()
        else:
            static_report_path = Path(args.static_report).resolve()
            static_report_bytes = None
        result = build_crosswalk(
            args.manifest.resolve(),
            static_report_path,
            args.claude_root.resolve(),
            args.gpu_root.resolve(),
            static_report_bytes=static_report_bytes,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
