#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Validate the staged bridge crosswalk for all 13 named TG source atoms.

This is a static audit.  It never runs a production computation and it never
promotes a conditional theorem, reviewed receipt, or provider migration.
Passing ``--claude-math-root`` additionally checks the pinned last-fresh
``Statement.trace``, citation inventory, and the exact claude_math bridge
source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.catalog import ATOMS  # noqa: E402
from tools.audit_tg_full_trust_boundary import (  # noqa: E402
    FullTrustBoundaryError,
    audit as audit_full_boundary,
)


DEFAULT_SPECIFICATION = (
    REPOSITORY_ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_EXTERNAL_ATOM_BRIDGE_STATUS.json"
)
READINESS_PATH = (
    REPOSITORY_ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_EXTERNAL_ATOM_READINESS.json"
)

STAGES = (
    "source_theorem_mapped",
    "checker_acceptance_mapped",
    "registered_physical_outcome_mapped",
    "exact_executable_refinement_present",
    "reviewed_receipt_present",
    "live_provider_switched",
    "fresh_retirement_confirmed",
)

EXPECTED_BINDINGS = {
    "ch25-a7-boundary": (
        "ch25A7Boundary",
        "ch25A7Boundary",
        "ch25A7BoundaryProductionV1",
    ),
    "ch25-psi-1e13": (
        "ch25Psi1e13",
        "ch25Psi1e13",
        "ch25PsiLemma92ProductionV1",
    ),
    "platt-head-2e4": (
        "plattHead2e4",
        "plattHead2e4",
        "plattHead2e4ProductionV1",
    ),
    "platt-trudgian-rh-3e12": (
        "plattTrudgianRH3e12",
        "plattTrudgianRH3e12",
        "plattTrudgianFiniteRHProductionV1",
    ),
    "helfgott-prop-12-2-4": (
        "helfgottProp1224",
        "helfgottProp1224",
        "helfgottProp1224ProductionV1",
    ),
    "cdem-squarefree": (
        "cdemSquarefree",
        "cdemSquarefree",
        "hurstSharedFourResidualProductionV2",
    ),
    "cdem-table-abel": (
        "cdemTableAbel",
        "cdemTableAbel",
        "cdemTableAbelProductionV2",
    ),
    "mertens-hurst": (
        "mertensHurst",
        "mertensHurst",
        "hurstSharedFourResidualProductionV2",
    ),
    "ramare-zuniga-lemma-6-2": (
        "ramareZunigaLemma62",
        "ramareZunigaLemma62",
        "ramareZunigaLemma62ProductionV1",
    ),
    "helfgott-platt-theorem-4-1": (
        "helfgottPlattTheorem41",
        "helfgottPlattTheorem41",
        "helfgottPlattGoldbachProductionV1",
    ),
    "platt-dirichlet-theorem-7-1": (
        "plattDirichletTheorem71",
        "plattDirichletTheorem71",
        "plattDirichletTheorem71ProductionV1",
    ),
    "platt-little-mertens-2-11": (
        "plattLittleMertens211",
        "plattLittleMertens211",
        "hurstSharedFourResidualProductionV2",
    ),
    "platt-little-mertens-stronger": (
        "plattLittleMertensStronger",
        "plattLittleMertensStronger",
        "hurstSharedFourResidualProductionV2",
    ),
}


class BridgeStatusError(ValueError):
    """The checked-in bridge status overclaims or has drifted."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BridgeStatusError(message)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BridgeStatusError(f"cannot load {path}: {error}") from error
    _require(isinstance(value, dict), f"{path}: expected a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise BridgeStatusError(f"cannot hash {path}: {error}") from error
    return digest.hexdigest()


def _check_pin(path: Path, expected: str, label: str) -> None:
    observed = _sha256(path)
    _require(
        observed == expected,
        f"{label} digest drifted: expected {expected}, observed {observed}",
    )


def load_and_validate(
    path: Path = DEFAULT_SPECIFICATION,
    *,
    claude_math_root: Path | None = None,
) -> dict[str, Any]:
    """Load and fail-closed validate the atom-level bridge status."""

    document = _load(path)
    _require(document.get("schema_version") == 1, "unsupported schema version")
    _require(
        document.get("kind")
        == "sparkinterval.ternary-goldbach.external-atom-bridge-status.v1",
        "unexpected bridge-status kind",
    )
    _require(
        document.get("classification")
        == "conditional-bridge-stage-crosswalk-not-proof-receipt-or-retirement",
        "bridge classification was widened",
    )

    authority = document.get("authority")
    _require(isinstance(authority, dict), "authority must be an object")
    _require(
        authority.get("root_declaration")
        == "Math.Problems.TernaryGoldbach.ternary_goldbach",
        "unexpected root declaration",
    )
    for key in (
        "external_catalog",
        "compact_registry",
        "compact_capstone",
        "registered_capstone",
    ):
        relative = authority.get(key)
        digest = authority.get(key + "_sha256")
        _require(
            isinstance(relative, str) and relative,
            f"missing authority path {key}",
        )
        _require(
            isinstance(digest, str) and len(digest) == 64,
            f"missing authority digest {key}_sha256",
        )
        _check_pin(REPOSITORY_ROOT / relative, digest, key)

    try:
        boundary = audit_full_boundary(claude_math_root=claude_math_root)
    except FullTrustBoundaryError as error:
        raise BridgeStatusError(
            f"full trust-boundary audit failed: {error}"
        ) from error
    _require(
        boundary["named_external_or_source"] == 13,
        "full boundary does not contain exactly thirteen source atoms",
    )
    _require(
        boundary["exact_executable_refinements"] == 0,
        "crosswalk must be reviewed before promoting executable refinements",
    )
    _require(
        boundary["installed_receipt_authorities"] == 0,
        "crosswalk must be reviewed before promoting receipt authority",
    )
    _require(
        boundary["freshly_retired_roots"] == 0,
        "crosswalk must be reviewed before promoting retired roots",
    )

    readiness = _load(READINESS_PATH)
    readiness_by_id = {
        row["atom_id"]: row for row in readiness.get("atoms", [])
    }
    _require(len(readiness_by_id) == 13, "readiness catalog is not 13-way")

    rows = document.get("atoms")
    _require(isinstance(rows, list), "atoms must be an array")
    _require(len(rows) == 13, "bridge status must have thirteen atom rows")
    catalog_ids = [atom.atom_id for atom in ATOMS]
    catalog_names = [atom.lean_name for atom in ATOMS]
    _require(
        [row.get("atom_id") for row in rows] == catalog_ids,
        "bridge rows differ from external catalog order",
    )
    _require(
        [row.get("lean_declaration") for row in rows] == catalog_names,
        "bridge declarations differ from the exact external catalog",
    )

    required_row_keys = {
        "atom_id",
        "lean_declaration",
        "gpu_constructor",
        "source_inputs_field",
        "physical_campaign_id",
        "registry_invocation",
        "source_specific_obligations",
        "stages",
    }
    for row in rows:
        atom_id = row["atom_id"]
        _require(
            set(row) == required_row_keys,
            f"{atom_id}: row keys differ from the closed schema",
        )
        expected_constructor, expected_field, expected_invocation = (
            EXPECTED_BINDINGS[atom_id]
        )
        _require(
            row["gpu_constructor"] == expected_constructor,
            f"{atom_id}: wrong GPU atom constructor",
        )
        _require(
            row["source_inputs_field"] == expected_field,
            f"{atom_id}: wrong claude_math SourceInputs field",
        )
        _require(
            row["registry_invocation"] == expected_invocation,
            f"{atom_id}: wrong closed physical invocation",
        )
        _require(
            row["physical_campaign_id"]
            == readiness_by_id[atom_id]["physical_campaign_id"],
            f"{atom_id}: physical campaign differs from readiness catalog",
        )
        _require(
            isinstance(row["source_specific_obligations"], list)
            and all(
                isinstance(item, str) and item
                for item in row["source_specific_obligations"]
            ),
            f"{atom_id}: malformed source-specific obligations",
        )
        stages = row["stages"]
        _require(
            isinstance(stages, dict) and tuple(stages) == STAGES,
            f"{atom_id}: stages differ from the closed stage sequence",
        )
        _require(
            all(isinstance(stages[stage], bool) for stage in STAGES),
            f"{atom_id}: every stage must be Boolean",
        )
        _require(
            stages["source_theorem_mapped"],
            f"{atom_id}: exact source theorem mapping regressed",
        )
        _require(
            stages["checker_acceptance_mapped"],
            f"{atom_id}: checker acceptance mapping regressed",
        )
        _require(
            stages["registered_physical_outcome_mapped"],
            f"{atom_id}: registered physical mapping regressed",
        )
        for stage in STAGES[3:]:
            _require(
                not stages[stage],
                f"{atom_id}: {stage} was promoted without updating this audit",
            )

    summary = document.get("summary")
    _require(isinstance(summary, dict), "summary must be an object")
    expected_summary = {
        "atom_count": len(rows),
        "physical_campaign_count": len(
            {row["physical_campaign_id"] for row in rows}
        ),
        **{
            stage: sum(bool(row["stages"][stage]) for row in rows)
            for stage in STAGES
        },
    }
    _require(summary == expected_summary, "summary does not match atom stages")
    _require(
        expected_summary["physical_campaign_count"] == 10,
        "external atoms no longer partition into ten physical campaigns",
    )

    witnesses = document.get("shared_witnesses")
    _require(isinstance(witnesses, dict), "shared_witnesses must be an object")
    base_trio = ["propext", "Classical.choice", "Quot.sound"]
    _require(
        witnesses.get("source_mapping_public_axioms") == base_trio,
        "source bridge axiom report is not the recorded base trio",
    )
    _require(
        witnesses.get("checker_mapping_public_axioms") == base_trio,
        "checker bridge axiom report is not the recorded base trio",
    )
    _require(
        witnesses.get("registered_physical_mapping_public_axioms") == base_trio,
        "registered physical bridge axiom report is not the recorded base trio",
    )

    capstone = (
        REPOSITORY_ROOT / authority["compact_capstone"]
    ).read_text(encoding="utf-8")
    registered_capstone = (
        REPOSITORY_ROOT / authority["registered_capstone"]
    ).read_text(encoding="utf-8")
    registry = (
        REPOSITORY_ROOT / authority["compact_registry"]
    ).read_text(encoding="utf-8")
    for theorem in (
        "checkerDerivedClaim_of_canonicalAcceptances",
        "exactTableDownstreamClaim_of_checkerDerivedClaim",
        "exactTableDownstreamClaim_of_canonicalAcceptances",
    ):
        _require(
            f"theorem {theorem}" in capstone,
            f"missing compact capstone theorem {theorem}",
        )
    for row in rows:
        _require(
            row["gpu_constructor"] in capstone,
            f"{row['atom_id']}: constructor absent from compact capstone",
        )
        _require(
            row["gpu_constructor"] in registry
            and row["registry_invocation"] in registry,
            f"{row['atom_id']}: closed registry mapping token absent",
        )
    reviewed_start = registry.index("def reviewedRun")
    reviewed_end = registry.index("/-- Closed statement/receipt selector", reviewed_start)
    reviewed_block = registry[reviewed_start:reviewed_end]
    _require(
        reviewed_block.count("=> none") == 12,
        "reviewed architecture selector is no longer entirely fail closed",
    )
    _require(
        "theorem reviewedRun_currently_none" in registry,
        "registry lost its universal Lean proof that every selector is closed",
    )
    for theorem in (
        "checkerDerivedClaim_of_registeredPhysicalOutcomes",
        "exactTableDownstreamClaim_of_registeredPhysicalOutcomes",
    ):
        _require(
            f"theorem {theorem}" in registered_capstone,
            f"missing registered physical capstone theorem {theorem}",
        )
    _require(
        "structure RegisteredPhysicalOutcomes" in registered_capstone
        and "structure ClosedExecutableRefinements" in registered_capstone,
        "registered physical capstone lost a closed outcome/refinement bundle",
    )

    authoritative_snapshot_checked = False
    if claude_math_root is not None:
        bridge_path = claude_math_root / authority["claude_math_bridge"]
        trace_path = (
            claude_math_root
            / authority["statement_trace_relative_to_claude_math"]
        )
        citation_path = (
            claude_math_root
            / authority["citation_inventory_relative_to_claude_math"]
        )
        for file_path, digest_key, label in (
            (bridge_path, "claude_math_bridge_sha256", "claude_math bridge"),
            (trace_path, "statement_trace_sha256", "Statement.trace"),
            (
                citation_path,
                "citation_inventory_sha256",
                "citation inventory",
            ),
        ):
            _check_pin(file_path, authority[digest_key], label)
        bridge = bridge_path.read_text(encoding="utf-8")
        for theorem in (
            "sourceInputs_of_exactTableDownstreamClaims",
            "sourceInputs_of_canonicalAcceptances",
            "sourceInputs_of_registeredPhysicalOutcomes",
        ):
            _require(
                f"theorem {theorem}" in bridge,
                f"missing claude_math bridge theorem {theorem}",
            )
        for row in rows:
            _require(
                row["source_inputs_field"] in bridge,
                f"{row['atom_id']}: SourceInputs field absent from bridge",
            )
        statement_source = (
            claude_math_root
            / "Math/Problems/TernaryGoldbach/Statement.lean"
        ).read_text(encoding="utf-8")
        _require(
            "CompactExternalAtomSourceInputs" not in statement_source,
            "live Statement now imports the bridge but status was not promoted",
        )
        authoritative_snapshot_checked = True

    return {
        "atom_count": expected_summary["atom_count"],
        "physical_campaign_count": expected_summary[
            "physical_campaign_count"
        ],
        **{stage: expected_summary[stage] for stage in STAGES},
        "authoritative_snapshot_checked": authoritative_snapshot_checked,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--specification",
        type=Path,
        default=DEFAULT_SPECIFICATION,
    )
    parser.add_argument("--claude-math-root", type=Path)
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        summary = load_and_validate(
            arguments.specification,
            claude_math_root=arguments.claude_math_root,
        )
    except BridgeStatusError as error:
        parser.error(str(error))
    if arguments.json:
        print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    else:
        print(
            "validated "
            f"{summary['atom_count']} external atoms across "
            f"{summary['physical_campaign_count']} physical campaigns; "
            f"source/checker mapped="
            f"{summary['source_theorem_mapped']}/"
            f"{summary['checker_acceptance_mapped']}, "
            "registered/refined/reviewed/live/retired="
            f"{summary['registered_physical_outcome_mapped']}/"
            f"{summary['exact_executable_refinement_present']}/"
            f"{summary['reviewed_receipt_present']}/"
            f"{summary['live_provider_switched']}/"
            f"{summary['fresh_retirement_confirmed']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
