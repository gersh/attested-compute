#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build the fail-closed native-family architecture bridge status.

This is a small production-data-free join of the authoritative family
catalog, the exact member crosswalk, and reviewed source adapter locations.
It never runs Lean or a production computation.  A mapped checker bundle is
only a conditional theorem target; executable refinement, receipt
installation, live provider wiring, and fresh retirement remain separate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FAMILIES = (
    REPOSITORY_ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_NATIVE_FAMILY_CLOSURE.json"
)
DEFAULT_MEMBERS = (
    REPOSITORY_ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_NATIVE_MEMBER_CROSSWALK.json"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_NATIVE_ARCHITECTURE_BRIDGE_STATUS.json"
)


AGGREGATE_ADAPTERS: dict[str, dict[str, str]] = {
    "analyticnt-chebyshev": {
        "repository": "claude_math",
        "path": (
            "Math/Problems/TernaryGoldbach/"
            "CompactChebyshevNativeInputs.lean"
        ),
        "claim_bundle": (
            "Math.Problems.TernaryGoldbach."
            "CompactChebyshevNativeInputs.SourceClaims"
        ),
        "checker": (
            "Math.Problems.TernaryGoldbach."
            "CompactChebyshevNativeInputs.nativeChecker"
        ),
        "registered_physical_outcome_to_claim": (
            "Math.Problems.TernaryGoldbach."
            "CompactChebyshevNativeInputs."
            "sourceClaims_of_registeredPhysicalOutcome"
        ),
    },
    "analyticnt-large-sieve": {
        "repository": "claude_math",
        "path": (
            "Math/Problems/TernaryGoldbach/"
            "CompactLargeSieveNativeInputs.lean"
        ),
        "claim_bundle": (
            "Math.Problems.TernaryGoldbach."
            "CompactLargeSieveNativeInputs.SourceClaims"
        ),
        "checker": (
            "Math.Problems.TernaryGoldbach."
            "CompactLargeSieveNativeInputs.nativeChecker"
        ),
        "registered_physical_outcome_to_claim": (
            "Math.Problems.TernaryGoldbach."
            "CompactLargeSieveNativeInputs."
            "sourceClaims_of_registeredPhysicalOutcome"
        ),
    },
    "helfgott-certificates": {
        "repository": "claude_math",
        "path": (
            "Math/Problems/TernaryGoldbach/"
            "CompactHelfgottCertificatesNativeInputs.lean"
        ),
        "claim_bundle": (
            "Math.Problems.TernaryGoldbach."
            "CompactHelfgottCertificatesNativeInputs.SourceClaims"
        ),
        "checker": (
            "Math.Problems.TernaryGoldbach."
            "CompactHelfgottCertificatesNativeInputs.nativeChecker"
        ),
        "registered_physical_outcome_to_claim": (
            "Math.Problems.TernaryGoldbach."
            "CompactHelfgottCertificatesNativeInputs."
            "sourceClaims_of_registeredPhysicalOutcome"
        ),
    },
    "ternary-goldbach-arithmetic-certs": {
        "repository": "claude_math",
        "path": (
            "Math/Problems/TernaryGoldbach/"
            "CompactArithmeticNativeInputs.lean"
        ),
        "claim_bundle": (
            "Math.Problems.TernaryGoldbach."
            "CompactArithmeticNativeInputs.SourceClaims"
        ),
        "checker": (
            "Math.Problems.TernaryGoldbach."
            "CompactArithmeticNativeInputs.nativeChecker"
        ),
        "registered_physical_outcome_to_claim": (
            "Math.Problems.TernaryGoldbach."
            "CompactArithmeticNativeInputs."
            "sourceClaims_of_registeredPhysicalOutcome"
        ),
    },
    "chapter14-minor-arcs": {
        "repository": "claude_math",
        "path": (
            "Math/Problems/TernaryGoldbach/"
            "CompactChapter14NativeInputs.lean"
        ),
        "claim_bundle": (
            "Math.Problems.TernaryGoldbach."
            "CompactChapter14NativeInputs.SourceClaims"
        ),
        "checker": (
            "Math.Problems.TernaryGoldbach."
            "CompactChapter14NativeInputs.nativeChecker"
        ),
        "registered_physical_outcome_to_claim": (
            "Math.Problems.TernaryGoldbach."
            "CompactChapter14NativeInputs."
            "sourceClaims_of_registeredPhysicalOutcome"
        ),
    },
    "standalone-tg-native": {
        "repository": "claude_math",
        "path": (
            "Math/Problems/TernaryGoldbach/"
            "CompactTGNativeInputs.lean"
        ),
        "claim_bundle": (
            "Math.Problems.TernaryGoldbach."
            "CompactTGNativeInputs.SourceClaims"
        ),
        "checker": (
            "Math.Problems.TernaryGoldbach."
            "CompactTGNativeInputs.nativeChecker"
        ),
        "registered_physical_outcome_to_claim": (
            "Math.Problems.TernaryGoldbach."
            "CompactTGNativeInputs."
            "sourceClaims_of_registeredPhysicalOutcome"
        ),
    },
    "mean-value-floor-grid": {
        "repository": "claude_math",
        "path": (
            "Math/Problems/TernaryGoldbach/"
            "CompactNumberTheoryAnalysisNativeInputs.lean"
        ),
        "claim_bundle": (
            "Math.Problems.TernaryGoldbach."
            "CompactNumberTheoryAnalysisNativeInputs.SourceClaims"
        ),
        "checker": (
            "Math.Problems.TernaryGoldbach."
            "CompactNumberTheoryAnalysisNativeInputs.nativeChecker"
        ),
        "registered_physical_outcome_to_claim": (
            "Math.Problems.TernaryGoldbach."
            "CompactNumberTheoryAnalysisNativeInputs."
            "sourceClaims_of_registeredPhysicalOutcome"
        ),
    },
    "little-mertens-liouville": {
        "repository": "claude_math",
        "path": (
            "Math/Problems/TernaryGoldbach/"
            "CompactNumberTheoryCertsNativeInputs.lean"
        ),
        "claim_bundle": (
            "Math.Problems.TernaryGoldbach."
            "CompactNumberTheoryCertsNativeInputs.SourceClaims"
        ),
        "checker": (
            "Math.Problems.TernaryGoldbach."
            "CompactNumberTheoryCertsNativeInputs.nativeChecker"
        ),
        "registered_physical_outcome_to_claim": (
            "Math.Problems.TernaryGoldbach."
            "CompactNumberTheoryCertsNativeInputs."
            "sourceClaims_of_registeredPhysicalOutcome"
        ),
    },
    "helfgott-analytic-intervals": {
        "repository": "claude_math",
        "path": (
            "Math/Problems/TernaryGoldbach/"
            "CompactHelfgottAnalyticIntervalsNativeInputs.lean"
        ),
        "claim_bundle_path": (
            "Math/Problems/TernaryGoldbach/"
            "CompactHelfgottAnalyticIntervalsNativeSourceClaims.lean"
        ),
        "claim_bundle": (
            "Math.Problems.TernaryGoldbach."
            "CompactHelfgottAnalyticIntervalsNativeInputs.SourceClaims"
        ),
        "checker": (
            "Math.Problems.TernaryGoldbach."
            "CompactHelfgottAnalyticIntervalsNativeInputs.nativeChecker"
        ),
        "registered_physical_outcome_to_claim": (
            "Math.Problems.TernaryGoldbach."
            "CompactHelfgottAnalyticIntervalsNativeInputs."
            "sourceClaims_of_registeredPhysicalOutcome"
        ),
    },
    "helfgott-section24-head": {
        "repository": "claude_math",
        "path": (
            "Math/Problems/TernaryGoldbach/"
            "CompactNumberTheoryHelfgottCertsNativeInputs.lean"
        ),
        "claim_bundle": (
            "Math.Problems.TernaryGoldbach."
            "CompactNumberTheoryHelfgottCertsNativeInputs.SourceClaims"
        ),
        "checker": (
            "Math.Problems.TernaryGoldbach."
            "CompactNumberTheoryHelfgottCertsNativeInputs.nativeChecker"
        ),
        "registered_physical_outcome_to_claim": (
            "Math.Problems.TernaryGoldbach."
            "CompactNumberTheoryHelfgottCertsNativeInputs."
            "sourceClaims_of_registeredPhysicalOutcome"
        ),
    },
    "chirre-helfgott-a6": {
        "repository": "claude_math",
        "path": (
            "Math/Problems/TernaryGoldbach/"
            "CompactNumberTheoryLSeriesNativeInputs.lean"
        ),
        "claim_bundle": (
            "Math.Problems.TernaryGoldbach."
            "CompactNumberTheoryLSeriesNativeInputs.SourceClaims"
        ),
        "checker": (
            "Math.Problems.TernaryGoldbach."
            "CompactNumberTheoryLSeriesNativeInputs.nativeChecker"
        ),
        "registered_physical_outcome_to_claim": (
            "Math.Problems.TernaryGoldbach."
            "CompactNumberTheoryLSeriesNativeInputs."
            "sourceClaims_of_registeredPhysicalOutcome"
        ),
    },
    "ramare-little-mertens": {
        "repository": "claude_math",
        "path": (
            "Math/Problems/TernaryGoldbach/"
            "CompactNumberTheoryMertensNativeInputs.lean"
        ),
        "claim_bundle": (
            "Math.Problems.TernaryGoldbach."
            "CompactNumberTheoryMertensNativeInputs.SourceClaims"
        ),
        "checker": (
            "Math.Problems.TernaryGoldbach."
            "CompactNumberTheoryMertensNativeInputs.nativeChecker"
        ),
        "registered_physical_outcome_to_claim": (
            "Math.Problems.TernaryGoldbach."
            "CompactNumberTheoryMertensNativeInputs."
            "sourceClaims_of_registeredPhysicalOutcome"
        ),
    },
    "vinogradov-finite-intervals": {
        "repository": "claude_math",
        "path": (
            "Math/Problems/TernaryGoldbach/"
            "CompactVinogradovNativeInputs.lean"
        ),
        "claim_bundle": (
            "Math.Problems.TernaryGoldbach."
            "CompactVinogradovNativeInputs.SourceClaims"
        ),
        "checker": (
            "Math.Problems.TernaryGoldbach."
            "CompactVinogradovNativeInputs.nativeChecker"
        ),
        "registered_physical_outcome_to_claim": (
            "Math.Problems.TernaryGoldbach."
            "CompactVinogradovNativeInputs."
            "sourceClaims_of_registeredPhysicalOutcome"
        ),
    },
    "rosser-schoenfeld": {
        "repository": "claude_math",
        "path": (
            "Math/Problems/TernaryGoldbach/"
            "CompactRS62NativeInputs.lean"
        ),
        "claim_bundle_path": (
            "Math/Problems/TernaryGoldbach/"
            "CompactRS62NativeSourceClaims.lean"
        ),
        "claim_bundle": (
            "Math.Problems.TernaryGoldbach."
            "CompactRS62NativeInputs.SourceClaims"
        ),
        "checker": (
            "Math.Problems.TernaryGoldbach."
            "CompactRS62NativeInputs.nativeChecker"
        ),
        "registered_physical_outcome_to_claim": (
            "Math.Problems.TernaryGoldbach."
            "CompactRS62NativeInputs."
            "sourceClaims_of_registeredPhysicalOutcome"
        ),
    },
    "ramare-production-folds": {
        "repository": "gpu_prover",
        "path": (
            "SparkInterval/TernaryGoldbach/"
            "RamareNativeFoldsCompactChecker.lean"
        ),
        "claim_bundle": (
            "SparkInterval.TernaryGoldbach."
            "RamareNativeFoldContracts.SourceClaims"
        ),
        "checker": (
            "SparkInterval.TernaryGoldbach."
            "RamareNativeFoldsCompactChecker.nativeChecker"
        ),
        "registered_physical_outcome_to_claim": (
            "SparkInterval.TernaryGoldbach."
            "RamareNativeFoldsCompactChecker."
            "sourceClaims_of_aggregatePhysicalOutcome"
        ),
    },
}


SPECIALIZED_FALLBACKS: dict[str, dict[str, str]] = {
    "ramare-production-folds": {
        "repository": "gpu_prover",
        "path": (
            "SparkInterval/TernaryGoldbach/"
            "RamareNativeFoldsCompactChecker.lean"
        ),
        "registry_invocation": "ramareProductionFoldsCompactV1",
        "claim_bundle": (
            "SparkInterval.TernaryGoldbach."
            "RamareNativeFoldContracts.SourceClaims"
        ),
        "registered_physical_outcome_to_claim": (
            "SparkInterval.TernaryGoldbach."
            "RamareNativeFoldsCompactChecker."
            "sourceClaims_of_registeredPhysicalOutcome"
        ),
    },
}


def build(families_path: Path, members_path: Path) -> dict[str, Any]:
    families = json.loads(families_path.read_text(encoding="utf-8"))
    members = json.loads(members_path.read_text(encoding="utf-8"))
    member_rows = members["members"]

    rows: list[dict[str, Any]] = []
    for family in families["families"]:
        family_id = family["family_id"]
        lean_family = family["lean_family"]
        generated_roots = family["authoritative_snapshot"]["native_atom_count"]
        source_decisions = len(
            {
                member["origin_declaration"]
                for member in member_rows
                if member["family"] == lean_family
            }
        )
        adapter = AGGREGATE_ADAPTERS.get(family_id)
        specialized = SPECIALIZED_FALLBACKS.get(family_id)
        rows.append(
            {
                "family_id": family_id,
                "lean_family": lean_family,
                "generated_roots": generated_roots,
                "source_decisions": source_decisions,
                "aggregate_invocation":
                    "nativeGeneratedAggregateProductionV1",
                "aggregate_adapter": adapter,
                "specialized_fallback": specialized,
                "stages": {
                    "aggregate_invocation_mapped": True,
                    "exact_fixed_checker_bundle_mapped": adapter is not None,
                    "exact_executable_refinement_present": False,
                    "reviewed_receipt_present": False,
                    "live_provider_switched": False,
                    "fresh_retirement_confirmed": False,
                },
            }
        )

    fixed = [
        row for row in rows
        if row["stages"]["exact_fixed_checker_bundle_mapped"]
    ]
    return {
        "schema_version": 1,
        "kind": (
            "sparkinterval.ternary-goldbach."
            "native-architecture-bridge-status.v1"
        ),
        "assessment_date": "2026-07-24",
        "classification": (
            "production-data-free-conditional-bridge-status-"
            "not-a-current-axiom-print"
        ),
        "scope": (
            "all 15 native-generated families, 1371 generated roots, "
            "and 1214 source decisions in the pinned capstone snapshot"
        ),
        "aggregate_invocation":
            "nativeGeneratedAggregateProductionV1",
        "families": rows,
        "summary": {
            "family_count": len(rows),
            "generated_roots": sum(row["generated_roots"] for row in rows),
            "source_decisions": sum(row["source_decisions"] for row in rows),
            "aggregate_invocation_mapped_families": len(rows),
            "aggregate_invocation_mapped_roots": sum(
                row["generated_roots"] for row in rows
            ),
            "exact_fixed_checker_bundle_mapped_families": len(fixed),
            "exact_fixed_checker_bundle_mapped_roots": sum(
                row["generated_roots"] for row in fixed
            ),
            "exact_fixed_checker_bundle_mapped_source_decisions": sum(
                row["source_decisions"] for row in fixed
            ),
            "specialized_fallback_families": sum(
                row["specialized_fallback"] is not None for row in rows
            ),
            "exact_executable_refinement_present": 0,
            "reviewed_receipt_present": 0,
            "live_provider_switched": 0,
            "fresh_retirement_confirmed": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--families", type=Path, default=DEFAULT_FAMILIES)
    parser.add_argument("--members", type=Path, default=DEFAULT_MEMBERS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    document = build(arguments.families, arguments.members)
    arguments.output.write_text(
        json.dumps(document, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
