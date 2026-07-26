#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed static validation for the TG native-family closure catalog.

This validates catalog accounting and policy.  It deliberately does not run
Lean, inspect a sibling checkout, replay a computation, or grant theorem
authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = (
    REPOSITORY_ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_NATIVE_FAMILY_CLOSURE.json"
)
SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")

EXPECTED_FAMILIES: dict[str, tuple[int, int, int, int]] = {
    # authoritative atoms, changed/removed, unchanged unreachable,
    # unchanged reachable in the recorded 2026-07-23 static projection
    "AnalyticNT.Chebyshev": (3, 0, 0, 3),
    "AnalyticNT.LargeSieve": (18, 0, 0, 18),
    "HelfgottCertificates": (4, 4, 0, 0),
    "Math.Problems.TernaryGoldbach.Certs": (7, 0, 0, 7),
    "Math.Problems.TernaryGoldbach.MinorArcs.Chapter14": (34, 34, 0, 0),
    "MathExtras.NumberTheory.Analysis": (3, 3, 0, 0),
    "MathExtras.NumberTheory.Certs": (2, 0, 0, 2),
    "MathExtras.NumberTheory.Helfgott": (202, 14, 0, 188),
    "MathExtras.NumberTheory.Helfgott.Certs": (1, 0, 1, 0),
    "MathExtras.NumberTheory.LSeries": (2, 0, 0, 2),
    "MathExtras.NumberTheory.Mertens": (1, 0, 0, 1),
    "MathExtras.NumberTheory.Vinogradov": (55, 0, 0, 55),
    "Rs62Certificates": (1025, 1025, 0, 0),
    "TGNativeCertificates": (11, 1, 0, 10),
    "TGNativeCertificates.Ramare": (3, 0, 0, 3),
}

LOCAL_MODE = "local_kernel_or_leancert_certificate"
COMPACT_MODE = "compact_trusted_run"

EXPECTED_RAMARE_BOOLEAN_LEAVES = [
    {
        "declaration": (
            "TGNativeCertificates.Ramare.Finite100M."
            "check_first_mertens_100m_full"
        ),
        "proposition_digest": (
            "sha256:"
            "b37e6955b0a72dab27d1f1bef629d9e2f9dbcbc41bc4c768842f89d8bb82e001"
        ),
    },
    {
        "declaration": (
            "TGNativeCertificates.Ramare.Lemma71.check_lemma71_100m_full"
        ),
        "proposition_digest": (
            "sha256:"
            "7c221d68aa489c14c94cb2ce762410b4a8894f8d0c4c77bf5f2bfed325002f39"
        ),
    },
    {
        "declaration": "TGNativeCertificates.Ramare.MStar140MCert.full_run",
        "proposition_digest": (
            "sha256:"
            "7e40b6de7113b12c788ddc30b3559743df47047808b8f93a21d75f7708a4b20b"
        ),
    },
]


class CatalogError(ValueError):
    """The catalog is internally inconsistent or weakens its policy."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CatalogError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_and_validate(path: Path = DEFAULT_CATALOG) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    _require(data.get("schema_version") == 1, "unsupported schema_version")
    _require(
        data.get("kind")
        == "sparkinterval.ternary-goldbach.native-family-closure.v1",
        "unexpected catalog kind",
    )
    _require(
        data["snapshots"]["recorded_static_projection_2026_07_23"]["status"]
        == "static_projection_not_authoritative",
        "the 289-atom projection must remain explicitly non-authoritative",
    )
    _require(
        data["snapshots"]["last_fresh_capstone"]["raw_statement_trace_vendored_here"]
        is False,
        "catalog must not pretend that the raw authoritative trace is vendored",
    )
    _require(
        data["policy"]["new_per_family_axioms_allowed"] is False,
        "per-family axioms are forbidden",
    )
    _require(
        data["policy"]["production_literals_or_traces_in_this_catalog"] is False,
        "catalog must remain production-data-free",
    )
    _require(
        data["summary"]["contains_production_data"] is False,
        "catalog must remain production-data-free",
    )

    rows = data["families"]
    _require(len(rows) == 15, "catalog must contain exactly 15 families")
    ids = [row["family_id"] for row in rows]
    _require(len(ids) == len(set(ids)), "family_id values must be unique")
    by_family = {row["lean_family"]: row for row in rows}
    _require(
        set(by_family) == set(EXPECTED_FAMILIES),
        "catalog family set differs from the last fresh manifest",
    )

    authoritative_total = 0
    changed_total = 0
    unreachable_total = 0
    reachable_total = 0
    local_total = 0
    compact_total = 0
    compact_families: list[str] = []
    for family, expected in EXPECTED_FAMILIES.items():
        row = by_family[family]
        authoritative = row["authoritative_snapshot"]
        projection = row["recorded_static_projection"]
        observed = (
            authoritative["native_atom_count"],
            projection["source_selection_changed_or_removed"],
            projection["source_selection_unchanged_import_unreachable"],
            projection["source_selection_unchanged_import_reachable"],
        )
        _require(
            observed == expected,
            f"{family}: counts {observed!r} do not match {expected!r}",
        )
        _require(
            sum(observed[1:]) == observed[0],
            f"{family}: projection does not partition authoritative atoms",
        )
        _require(
            authoritative["module_count"] > 0,
            f"{family}: module_count must be positive",
        )
        _require(
            SHA256_RE.fullmatch(authoritative["member_digest"]) is not None,
            f"{family}: malformed member_digest",
        )
        _require(
            row["authoritative_retirement_proven"] is False,
            f"{family}: retirement cannot be claimed without a fresh build",
        )

        discharge = row["preferred_discharge"]
        mode = discharge["mode"]
        _require(
            mode in {LOCAL_MODE, COMPACT_MODE},
            f"{family}: unsupported discharge mode {mode!r}",
        )
        _require(
            "production" not in discharge["routine_local_build_behavior"],
            f"{family}: routine local build must not replay production work",
        )
        if mode == LOCAL_MODE:
            _require(
                discharge["compact_trusted_run_allowed"] is False,
                f"{family}: compact fallback is not justified",
            )
            _require(
                discharge["prohibitive_reason"] is None,
                f"{family}: local family must not advertise a prohibitive reason",
            )
            _require(
                "compact_contract" not in row,
                f"{family}: local family must not install a compact contract",
            )
            local_total += observed[0]
        else:
            _require(
                discharge["compact_trusted_run_allowed"] is True,
                f"{family}: compact mode must be explicitly allowed",
            )
            _require(
                isinstance(discharge["prohibitive_reason"], str)
                and len(discharge["prohibitive_reason"]) >= 80,
                f"{family}: compact fallback needs a concrete prohibitive reason",
            )
            compact_total += observed[0]
            compact_families.append(family)

            contract = row.get("compact_contract")
            _require(
                isinstance(contract, dict),
                f"{family}: compact mode needs a closed Lean contract",
            )
            _require(
                contract["registry_invocation"]
                == "ramareProductionFoldsCompactV1",
                f"{family}: unexpected compact registry invocation",
            )
            _require(
                contract["claim_kind"] == "native_family_fallback"
                and contract["external_atom_campaign"] is False,
                f"{family}: fallback must remain outside the external atoms",
            )
            _require(
                contract["acceptance_evidence"]
                == (
                    "SparkInterval.TernaryGoldbach."
                    "RamareNativeFoldContracts.FiniteFoldEvidence"
                ),
                f"{family}: acceptance must carry low-level fold evidence",
            )
            _require(
                contract["evidence_to_claims_theorem"]
                == (
                    "SparkInterval.TernaryGoldbach.RamareNativeFoldContracts."
                    "sourceClaims_of_finiteFoldEvidence"
                ),
                f"{family}: missing ordinary evidence-to-claims theorem",
            )
            _require(
                contract["compact_composition_theorem"]
                == (
                    "SparkInterval.TernaryGoldbach."
                    "RamareNativeFoldsCompactChecker.sourceClaims_of_compactRun"
                ),
                f"{family}: unexpected compact composition theorem",
            )
            _require(
                contract["reviewed_run_installed"] is False
                and contract["exact_executable_refinement_proved"] is False
                and contract[
                    "exact_claude_math_provider_replacement_proved"
                ]
                is False,
                f"{family}: staged fallback must not overclaim retirement",
            )
            _require(
                contract["historical_boolean_leaves"]
                == EXPECTED_RAMARE_BOOLEAN_LEAVES,
                f"{family}: exact historical Boolean leaves drifted",
            )
            for module_key in (
                "source_contract_module",
                "compact_checker_module",
            ):
                module_path = (
                    REPOSITORY_ROOT
                    / (contract[module_key].replace(".", "/") + ".lean")
                )
                _require(
                    module_path.is_file(),
                    f"{family}: missing {module_key} at {module_path}",
                )

        authoritative_total += observed[0]
        changed_total += observed[1]
        unreachable_total += observed[2]
        reachable_total += observed[3]

    _require(
        compact_families == ["TGNativeCertificates.Ramare"],
        "only the measured 100M/140M Ramaré family may use compact fallback",
    )
    expected_totals = (1371, 1081, 1, 289, 1368, 3)
    observed_totals = (
        authoritative_total,
        changed_total,
        unreachable_total,
        reachable_total,
        local_total,
        compact_total,
    )
    _require(
        observed_totals == expected_totals,
        f"catalog totals {observed_totals!r} do not match {expected_totals!r}",
    )

    summary = data["summary"]
    summary_observed = (
        summary["authoritative_native_atoms"],
        summary["recorded_projection_changed_or_removed"],
        summary["recorded_projection_unchanged_import_unreachable"],
        summary["recorded_projection_unchanged_import_reachable"],
        summary["authoritative_atoms_assigned_local_kernel_or_leancert"],
        summary["authoritative_atoms_assigned_compact_trusted_run_fallback"],
    )
    _require(
        summary_observed == expected_totals,
        "summary does not match per-family accounting",
    )
    _require(
        summary["families_authoritatively_retired_by_a_fresh_capstone_print"] == 0,
        "no staged family may be called authoritatively retired",
    )

    last_fresh = data["snapshots"]["last_fresh_capstone"]
    _require(
        last_fresh["native_generated_atoms"] == authoritative_total,
        "last-fresh native total differs from family accounting",
    )
    _require(
        last_fresh["native_family_count"] == len(rows),
        "last-fresh family total differs from family accounting",
    )
    _require(
        last_fresh["total_axioms"]
        == last_fresh["foundation_atoms"]
        + last_fresh["named_external_or_source_atoms"]
        + last_fresh["native_generated_atoms"],
        "last-fresh total axiom accounting is inconsistent",
    )
    _require(
        SHA256_RE.fullmatch(last_fresh["retained_manifest_sha256"]) is not None,
        "malformed retained manifest SHA-256",
    )

    projection = data["snapshots"]["recorded_static_projection_2026_07_23"]
    projection_observed = (
        projection["baseline_native_atoms"],
        projection["source_selection_changed_or_removed"],
        projection["source_selection_unchanged_import_unreachable"],
        projection["source_selection_unchanged_import_reachable"],
    )
    _require(
        projection_observed == (1371, 1081, 1, 289),
        "recorded projection snapshot was altered",
    )
    _require(
        SHA256_RE.fullmatch(projection["document_sha256"]) is not None,
        "malformed static projection SHA-256",
    )
    _require(
        len(data["zero_native_completion_gate"]) >= 6,
        "zero-native completion gate is incomplete",
    )
    return data


def validate_against_authoritative_manifest(
    data: dict[str, Any],
    manifest_path: Path,
) -> None:
    """Optionally bind the family matrix to the retained claude_math manifest."""

    fresh = data["snapshots"]["last_fresh_capstone"]
    _require(
        _sha256(manifest_path) == fresh["retained_manifest_sha256"],
        "authoritative manifest bytes do not match the catalog pin",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require(
        manifest["root"]["declaration"] == fresh["root_declaration"],
        "authoritative manifest has a different root declaration",
    )
    _require(
        manifest["root"]["type_digest"] == fresh["root_type_digest"],
        "authoritative manifest has a different root type",
    )
    expected_summary = (
        fresh["foundation_atoms"],
        fresh["named_external_or_source_atoms"],
        fresh["native_family_count"],
        fresh["native_generated_atoms"],
        fresh["total_axioms"],
    )
    observed_summary = (
        manifest["summary"]["foundations"],
        manifest["summary"]["named_external_or_source"],
        manifest["summary"]["native_families"],
        manifest["summary"]["native_generated"],
        manifest["summary"]["total_axioms"],
    )
    _require(
        observed_summary == expected_summary,
        "authoritative manifest summary differs from the catalog",
    )
    catalog_rows = {row["lean_family"]: row for row in data["families"]}
    manifest_rows = {
        row["family"]: row for row in manifest["native_families"]
    }
    _require(
        set(manifest_rows) == set(catalog_rows),
        "authoritative manifest family set differs from the catalog",
    )
    for family, row in catalog_rows.items():
        source = manifest_rows[family]
        authoritative = row["authoritative_snapshot"]
        observed = (
            source["count"],
            len(source["modules"]),
            source["member_digest"],
            source["review"]["range"],
        )
        expected = (
            authoritative["native_atom_count"],
            authoritative["module_count"],
            authoritative["member_digest"],
            authoritative["range"],
        )
        _require(
            observed == expected,
            f"{family}: authoritative manifest metadata differs from catalog",
        )


def validate_projection_document_pin(
    data: dict[str, Any],
    document_path: Path,
) -> None:
    projection = data["snapshots"]["recorded_static_projection_2026_07_23"]
    _require(
        _sha256(document_path) == projection["document_sha256"],
        "static projection document bytes do not match the catalog pin",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "catalog",
        nargs="?",
        type=Path,
        default=DEFAULT_CATALOG,
    )
    parser.add_argument(
        "--authoritative-manifest",
        type=Path,
        help="optionally cross-check the retained claude_math native manifest",
    )
    parser.add_argument(
        "--projection-document",
        type=Path,
        help="optionally cross-check the recorded static-projection document",
    )
    args = parser.parse_args()
    data = load_and_validate(args.catalog)
    if args.authoritative_manifest is not None:
        validate_against_authoritative_manifest(
            data,
            args.authoritative_manifest,
        )
    if args.projection_document is not None:
        validate_projection_document_pin(
            data,
            args.projection_document,
        )
    print(
        "validated "
        f"{data['summary']['family_count']} families / "
        f"{data['summary']['authoritative_native_atoms']} authoritative atoms; "
        "289 remains a non-authoritative static projection"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
