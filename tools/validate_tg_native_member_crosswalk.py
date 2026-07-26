#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed validation for the TG native-root member crosswalk.

The default check is self-contained and production-data-free.  Optional
arguments pin the crosswalk to the retained authoritative manifest, the exact
static diagnostic used to generate it, and the two source trees containing
the referenced declarations.  This tool never invokes Lean or Lake.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = (
    REPOSITORY_ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_NATIVE_MEMBER_CROSSWALK.json"
)

CHANGED = "source_selection_changed_or_removed"
UNREACHABLE = "source_selection_unchanged_import_unreachable"
REACHABLE = "source_selection_unchanged_import_reachable"
STATIC_STATES = {CHANGED, UNREACHABLE, REACHABLE}
STAGES = {
    "catalogued_only",
    "source_selection_changed",
    "staged_replacement_target_mapped",
    "live_provider_integrated",
    "fresh_print_retired",
}
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
EXPECTED_CURRENT = {
    CHANGED: 1085,
    UNREACHABLE: 5,
    REACHABLE: 281,
}
EXPECTED_PINNED = {
    CHANGED: 1081,
    UNREACHABLE: 1,
    REACHABLE: 289,
}
EXPECTED_MAPPED = 1371
EXPECTED_UNMAPPED = 0


class CrosswalkError(ValueError):
    """The crosswalk is inconsistent or overstates its assurance."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CrosswalkError(message)


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _walk_strings(item)


def _status_by_name(report: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for status, grouping in report["baseline_comparison"]["statuses"].items():
        for family in grouping["families"]:
            for source_file in family["files"]:
                for origin in source_file["origin_declarations"]:
                    for name in origin["native_axiom_names"]:
                        _require(
                            name not in result,
                            f"static report repeats member {name}",
                        )
                        result[name] = status
    return result


def _declaration_tail(name: str) -> str:
    return name.rsplit(".", 1)[-1]


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


def load_and_validate(path: Path = DEFAULT_CATALOG) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    _require(data.get("schema_version") == 1, "unsupported schema_version")
    _require(
        data.get("kind")
        == "sparkinterval.ternary-goldbach.native-member-crosswalk.v1",
        "unexpected catalog kind",
    )
    _require(
        data.get("classification")
        == (
            "production-data-free-member-audit-not-a-proof-"
            "or-current-axiom-print"
        ),
        "catalog classification must remain fail closed",
    )

    policy = data["policy"]
    _require(
        policy["expanded_propositions_included"] is False,
        "expanded propositions are forbidden",
    )
    _require(
        policy["production_data_included"] is False,
        "production data are forbidden",
    )
    for key in (
        "mapping_implies_statement_identity",
        "mapping_implies_live_integration",
        "mapping_implies_retirement",
    ):
        _require(policy[key] is False, f"{key} must remain false")

    for text in _walk_strings(data):
        _require("/home/" not in text, "private absolute path found")
        _require("file://" not in text, "file URI found")

    snapshots = data["snapshots"]
    authority = snapshots["last_fresh_capstone_authority"]
    _require(
        authority["status"] == "authoritative_for_that_completed_build_only",
        "last-fresh authority scope was weakened",
    )
    _require(
        authority["native_generated_atoms"] == 1371,
        "last-fresh native count drifted",
    )
    _require(
        SHA256_RE.fullmatch(authority["manifest_sha256"]) is not None,
        "malformed manifest digest",
    )
    _require(
        SHA256_RE.fullmatch(authority["root_type_digest"]) is not None,
        "malformed root type digest",
    )

    pinned = snapshots["pinned_static_projection_2026_07_23"]
    _require(
        pinned["status"] == "static_projection_not_authoritative",
        "pinned projection cannot be authoritative",
    )
    _require(
        pinned["member_rows_in_this_crosswalk"] is False,
        "pinned aggregate must remain separate from current member rows",
    )
    _require(
        {state: pinned[state] for state in STATIC_STATES}
        == EXPECTED_PINNED,
        "pinned 1081/1/289 snapshot drifted",
    )

    current = snapshots["current_static_diagnostic_2026_07_24"]
    _require(
        current["status"] == "static_projection_not_authoritative",
        "current diagnostic cannot be authoritative",
    )
    _require(
        {state: current[state] for state in STATIC_STATES}
        == EXPECTED_CURRENT,
        "current 1085/5/281 diagnostic drifted",
    )
    for digest_key in ("static_report_sha256", "member_status_digest"):
        _require(
            SHA256_RE.fullmatch(current[digest_key]) is not None,
            f"malformed {digest_key}",
        )

    members = data["members"]
    _require(len(members) == 1371, "crosswalk must have 1371 members")
    names = [member["name"] for member in members]
    _require(names == sorted(names), "member rows must be name-sorted")
    _require(len(set(names)) == len(names), "member names must be unique")

    evidence_rows = data["replacement_evidence"]
    evidence_ids = [row["evidence_id"] for row in evidence_rows]
    _require(
        evidence_ids == sorted(evidence_ids),
        "replacement evidence must be id-sorted",
    )
    _require(
        len(set(evidence_ids)) == len(evidence_ids),
        "replacement evidence ids must be unique",
    )
    evidence_by_id = {row["evidence_id"]: row for row in evidence_rows}
    for row in evidence_rows:
        _require(
            row["repository"] in {"claude_math", "gpu_prover"},
            f"{row['evidence_id']}: unknown repository",
        )
        relative = Path(row["path"])
        _require(
            not relative.is_absolute() and ".." not in relative.parts,
            f"{row['evidence_id']}: path is not repository-relative",
        )
        _require(
            row["assurance"] == "target_location_only",
            f"{row['evidence_id']}: mapping assurance was overstated",
        )
        _require(
            isinstance(row["declaration"], str) and row["declaration"],
            f"{row['evidence_id']}: declaration is empty",
        )

    projection_counts: Counter[str] = Counter()
    stage_counts: Counter[str] = Counter()
    mapped = 0
    ramare_mapped: list[dict[str, Any]] = []
    vinogradov_mapped: list[dict[str, Any]] = []
    helfgott_private_lemma37_mapped: list[dict[str, Any]] = []
    for member in members:
        _require(
            set(member)
            == {
                "name",
                "type_digest",
                "family",
                "source_path",
                "origin_declaration",
                "current_static_projection",
                "stage",
                "replacement_evidence_ref",
            },
            f"{member.get('name')}: unexpected member fields",
        )
        _require(
            SHA256_RE.fullmatch(member["type_digest"]) is not None,
            f"{member['name']}: malformed type digest",
        )
        static = member["current_static_projection"]
        stage = member["stage"]
        _require(static in STATIC_STATES, f"{member['name']}: bad static state")
        _require(stage in STAGES, f"{member['name']}: bad stage")
        projection_counts[static] += 1
        stage_counts[stage] += 1
        evidence_ref = member["replacement_evidence_ref"]
        if stage == "staged_replacement_target_mapped":
            _require(
                evidence_ref in evidence_by_id,
                f"{member['name']}: mapped member lacks evidence",
            )
            mapped += 1
            if member["family"] == "TGNativeCertificates.Ramare":
                ramare_mapped.append(evidence_by_id[evidence_ref])
            if member["family"] == "MathExtras.NumberTheory.Vinogradov":
                vinogradov_mapped.append(evidence_by_id[evidence_ref])
            if (
                member["family"] == "MathExtras.NumberTheory.Helfgott"
                and "Lemma37HighQLargeSharpBShape"
                in member["origin_declaration"]
            ):
                helfgott_private_lemma37_mapped.append(
                    evidence_by_id[evidence_ref]
                )
        else:
            _require(
                evidence_ref is None,
                f"{member['name']}: non-mapped stage has evidence",
            )
        _require(
            stage not in {"live_provider_integrated", "fresh_print_retired"},
            f"{member['name']}: no fresh build supports {stage}",
        )
        if static == CHANGED:
            _require(
                stage
                in {
                    "source_selection_changed",
                    "staged_replacement_target_mapped",
                },
                f"{member['name']}: changed selection lost its status",
            )

    _require(
        dict(projection_counts) == EXPECTED_CURRENT,
        "member projection counts do not equal 1085/5/281",
    )
    _require(mapped == EXPECTED_MAPPED, "mapped member count drifted")
    _require(
        len(members) - mapped == EXPECTED_UNMAPPED,
        "unmapped member count drifted",
    )
    _require(
        len(ramare_mapped) == 3,
        "all three Ramaré roots need the exact compact mapping",
    )
    for evidence in ramare_mapped:
        _require(
            evidence["repository"] == "gpu_prover"
            and evidence["kind"] == "compact_family_fallback"
            and evidence["path"]
            == (
                "SparkInterval/TernaryGoldbach/"
                "RamareNativeFoldsCompactChecker.lean"
            )
            and evidence["declaration"]
            == (
                "SparkInterval.TernaryGoldbach."
                "RamareNativeFoldsCompactChecker."
                "sourceClaims_of_compactRun"
            ),
            "Ramaré compact mapping drifted",
        )
    _require(
        len(vinogradov_mapped) == 55,
        "all 55 Vinogradov roots need the exact conditional family bundle",
    )
    for evidence in vinogradov_mapped:
        _require(
            evidence["repository"] == "claude_math"
            and evidence["kind"]
            == "conditional_attested_source_shaped_family_bundle"
            and evidence["path"]
            == (
                "Math/Problems/TernaryGoldbach/"
                "CompactVinogradovNativeInputs.lean"
            )
            and evidence["declaration"]
            == (
                "Math.Problems.TernaryGoldbach."
                "CompactVinogradovNativeInputs."
                "sourceClaims_of_registeredPhysicalOutcome"
            ),
            "Vinogradov conditional family mapping drifted",
        )
    _require(
        len(helfgott_private_lemma37_mapped) == 6,
        "all six private Lemma-3.7 roots need semantic target locations",
    )
    for evidence in helfgott_private_lemma37_mapped:
        _require(
            evidence["repository"] == "claude_math"
            and evidence["kind"]
            == "conditional_attested_source_shaped_family_bundle"
            and evidence["path"]
            == (
                "Math/Problems/TernaryGoldbach/"
                "CompactHelfgottAnalyticIntervalsNativeInputs.lean"
            )
            and evidence["declaration"]
            == (
                "Math.Problems.TernaryGoldbach."
                "CompactHelfgottAnalyticIntervalsNativeInputs."
                "sourceClaims_of_registeredPhysicalOutcome"
            )
            and evidence["assurance"] == "target_location_only",
            "private Lemma-3.7 semantic mapping was overstated or drifted",
        )

    status_digest_text = "\n".join(
        f"{member['name']}\t{member['current_static_projection']}"
        for member in members
    )
    _require(
        current["member_status_digest"]
        == _sha256_bytes(status_digest_text.encode("utf-8")),
        "member status digest mismatch",
    )

    summary = data["summary"]
    _require(
        summary["authoritative_native_members"] == len(members),
        "summary authoritative count mismatch",
    )
    _require(
        summary["staged_replacement_target_mapped"] == mapped
        and summary["without_replacement_target"] == len(members) - mapped,
        "summary mapping counts mismatch",
    )
    _require(
        summary["live_provider_integrated"] == 0
        and summary["fresh_print_retired"] == 0,
        "summary overclaims integration or retirement",
    )
    _require(
        summary["stage_counts"]
        == {stage: stage_counts.get(stage, 0) for stage in sorted(STAGES)},
        "summary stage counts mismatch",
    )
    _require(
        summary["current_static_projection_counts"]
        == {state: projection_counts[state] for state in sorted(STATIC_STATES)},
        "summary projection counts mismatch",
    )
    return data


def validate_against_authoritative_manifest(
    data: Mapping[str, Any], manifest_path: Path
) -> None:
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    _require(
        data["snapshots"]["last_fresh_capstone_authority"][
            "manifest_sha256"
        ]
        == _sha256_bytes(manifest_bytes),
        "authoritative manifest byte digest mismatch",
    )
    entries = {row["name"]: row for row in manifest["native_entries"]}
    _require(len(entries) == 1371, "manifest does not contain 1371 roots")
    for member in data["members"]:
        entry = entries.get(member["name"])
        _require(entry is not None, f"manifest lacks {member['name']}")
        expected = {
            "type_digest": entry["type_digest"],
            "family": entry["family"],
            "source_path": entry["source_witness"]["path"],
            "origin_declaration": entry["origin_declaration"],
        }
        for key, value in expected.items():
            _require(
                member[key] == value,
                f"{member['name']}: manifest {key} mismatch",
            )


def validate_against_static_report(
    data: Mapping[str, Any], report_path: Path
) -> None:
    report_bytes = report_path.read_bytes()
    report = json.loads(report_bytes)
    current = data["snapshots"]["current_static_diagnostic_2026_07_24"]
    _require(
        current["static_report_sha256"] == _sha256_bytes(report_bytes),
        "static report byte digest mismatch",
    )
    statuses = _status_by_name(report)
    for member in data["members"]:
        _require(
            statuses.get(member["name"])
            == member["current_static_projection"],
            f"{member['name']}: static projection mismatch",
        )


def validate_evidence_paths(
    data: Mapping[str, Any], claude_root: Path, gpu_root: Path
) -> None:
    roots = {
        "claude_math": claude_root,
        "gpu_prover": gpu_root,
    }
    for evidence in data["replacement_evidence"]:
        target = roots[evidence["repository"]] / evidence["path"]
        _require(
            target.is_file(),
            f"{evidence['evidence_id']}: target file is absent",
        )
        _require(
            _has_declaration(target, evidence["declaration"]),
            f"{evidence['evidence_id']}: target declaration is absent",
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--static-report", type=Path)
    parser.add_argument("--claude-root", type=Path)
    parser.add_argument("--gpu-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = load_and_validate(args.catalog)
        if args.manifest is not None:
            validate_against_authoritative_manifest(data, args.manifest)
        if args.static_report is not None:
            validate_against_static_report(data, args.static_report)
        if args.claude_root is not None:
            validate_evidence_paths(
                data, args.claude_root.resolve(), args.gpu_root.resolve()
            )
    except (OSError, KeyError, json.JSONDecodeError, CrosswalkError) as exc:
        print(f"validate_tg_native_member_crosswalk.py: {exc}", file=sys.stderr)
        return 1
    summary = data["summary"]
    result = {
        "members": summary["authoritative_native_members"],
        "mapped": summary["staged_replacement_target_mapped"],
        "unmapped": summary["without_replacement_target"],
        "live_provider_integrated": summary["live_provider_integrated"],
        "fresh_print_retired": summary["fresh_print_retired"],
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "native member crosswalk: "
            f"{result['members']} members, {result['mapped']} staged mappings, "
            f"{result['unmapped']} without a target, "
            "0 live-integrated, 0 fresh-print-retired"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
