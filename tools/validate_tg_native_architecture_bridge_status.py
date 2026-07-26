#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed validation for native-family architecture bridge status."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATUS = (
    REPOSITORY_ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_NATIVE_ARCHITECTURE_BRIDGE_STATUS.json"
)
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


class NativeArchitectureStatusError(ValueError):
    """The native architecture status is incomplete or overstates progress."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NativeArchitectureStatusError(message)


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


def _tail(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def _has_declaration(source: str, declaration: str) -> bool:
    tail = re.escape(_tail(declaration))
    return (
        re.search(
            r"(?m)^\s*(?:(?:private|protected|noncomputable)\s+)*"
            r"(?:theorem|lemma|def|abbrev|structure)\s+"
            + tail
            + r"(?=[\s(:])",
            source,
        )
        is not None
    )


def load_and_validate(
    status_path: Path = DEFAULT_STATUS,
    families_path: Path = DEFAULT_FAMILIES,
    members_path: Path = DEFAULT_MEMBERS,
    *,
    claude_math_root: Path | None = None,
) -> dict[str, Any]:
    status = json.loads(status_path.read_text(encoding="utf-8"))
    families = json.loads(families_path.read_text(encoding="utf-8"))
    members = json.loads(members_path.read_text(encoding="utf-8"))

    _require(status.get("schema_version") == 1, "unsupported schema_version")
    _require(
        status.get("kind")
        == (
            "sparkinterval.ternary-goldbach."
            "native-architecture-bridge-status.v1"
        ),
        "unexpected status kind",
    )
    _require(
        status.get("classification")
        == (
            "production-data-free-conditional-bridge-status-"
            "not-a-current-axiom-print"
        ),
        "status classification was weakened",
    )
    _require(
        status.get("aggregate_invocation")
        == "nativeGeneratedAggregateProductionV1",
        "aggregate invocation drifted",
    )
    for text in _walk_strings(status):
        _require("/home/" not in text, "private absolute path found")
        _require("file://" not in text, "file URI found")

    member_rows = members["members"]
    expected_rows = families["families"]
    rows = status["families"]
    _require(len(rows) == len(expected_rows) == 15, "family count drifted")
    _require(
        [row["family_id"] for row in rows]
        == [row["family_id"] for row in expected_rows],
        "family order or identity differs from closure catalog",
    )

    fixed_rows: list[dict[str, Any]] = []
    specialized_rows: list[dict[str, Any]] = []
    for row, expected in zip(rows, expected_rows, strict=True):
        family_id = expected["family_id"]
        lean_family = expected["lean_family"]
        expected_generated = expected["authoritative_snapshot"][
            "native_atom_count"
        ]
        expected_decisions = len(
            {
                member["origin_declaration"]
                for member in member_rows
                if member["family"] == lean_family
            }
        )
        _require(row["lean_family"] == lean_family, f"{family_id}: family drift")
        _require(
            row["generated_roots"] == expected_generated,
            f"{family_id}: generated-root count drifted",
        )
        _require(
            row["source_decisions"] == expected_decisions,
            f"{family_id}: source-decision count drifted",
        )
        _require(
            row["aggregate_invocation"]
            == "nativeGeneratedAggregateProductionV1",
            f"{family_id}: aggregate invocation drifted",
        )
        stages = row["stages"]
        _require(
            stages["aggregate_invocation_mapped"] is True,
            f"{family_id}: aggregate route is missing",
        )
        for stage in (
            "exact_executable_refinement_present",
            "reviewed_receipt_present",
            "live_provider_switched",
            "fresh_retirement_confirmed",
        ):
            _require(
                stages[stage] is False,
                f"{family_id}: {stage} advanced without completion evidence",
            )

        adapter = row["aggregate_adapter"]
        if stages["exact_fixed_checker_bundle_mapped"]:
            _require(isinstance(adapter, dict), f"{family_id}: adapter missing")
            base_adapter_fields = {
                "repository",
                "path",
                "claim_bundle",
                "checker",
                "registered_physical_outcome_to_claim",
            }
            _require(
                frozenset(adapter)
                in {
                    frozenset(base_adapter_fields),
                    frozenset(base_adapter_fields | {"claim_bundle_path"}),
                },
                f"{family_id}: unexpected adapter fields",
            )
            _require(
                adapter["repository"] in {"claude_math", "gpu_prover"},
                f"{family_id}: unknown aggregate adapter repository",
            )
            fixed_rows.append(row)
        else:
            _require(adapter is None, f"{family_id}: unmapped adapter retained")

        specialized = row["specialized_fallback"]
        if specialized is not None:
            _require(
                family_id == "ramare-production-folds"
                and specialized["repository"] == "gpu_prover"
                and specialized["registry_invocation"]
                == "ramareProductionFoldsCompactV1",
                f"{family_id}: unexpected specialized fallback",
            )
            specialized_rows.append(row)

        for adapter_row in (adapter, specialized):
            if adapter_row is None:
                continue
            relative = Path(adapter_row["path"])
            _require(
                not relative.is_absolute() and ".." not in relative.parts,
                f"{family_id}: adapter path is not repository-relative",
            )
            if adapter_row["repository"] == "gpu_prover":
                root = REPOSITORY_ROOT
            else:
                root = claude_math_root
            if root is not None:
                path = root / relative
                _require(path.is_file(), f"{family_id}: missing {path}")
                source = path.read_text(encoding="utf-8")
                claim_relative = Path(
                    adapter_row.get("claim_bundle_path", adapter_row["path"])
                )
                _require(
                    not claim_relative.is_absolute()
                    and ".." not in claim_relative.parts,
                    f"{family_id}: claim-bundle path is not repository-relative",
                )
                claim_path = root / claim_relative
                _require(
                    claim_path.is_file(),
                    f"{family_id}: missing {claim_path}",
                )
                claim_source = claim_path.read_text(encoding="utf-8")
                _require(
                    _has_declaration(
                        claim_source, adapter_row["claim_bundle"]
                    ),
                    f"{family_id}: missing declaration "
                    f"{adapter_row['claim_bundle']}",
                )
                _require(
                    _has_declaration(
                        source,
                        adapter_row[
                            "registered_physical_outcome_to_claim"
                        ],
                    ),
                    f"{family_id}: missing declaration "
                    f"{adapter_row['registered_physical_outcome_to_claim']}",
                )
                checker = adapter_row.get("checker")
                if checker is not None:
                    _require(
                        _has_declaration(source, checker),
                        f"{family_id}: missing checker {checker}",
                    )

    summary = status["summary"]
    expected_summary = {
        "family_count": len(rows),
        "generated_roots": sum(row["generated_roots"] for row in rows),
        "source_decisions": sum(row["source_decisions"] for row in rows),
        "aggregate_invocation_mapped_families": len(rows),
        "aggregate_invocation_mapped_roots": sum(
            row["generated_roots"] for row in rows
        ),
        "exact_fixed_checker_bundle_mapped_families": len(fixed_rows),
        "exact_fixed_checker_bundle_mapped_roots": sum(
            row["generated_roots"] for row in fixed_rows
        ),
        "exact_fixed_checker_bundle_mapped_source_decisions": sum(
            row["source_decisions"] for row in fixed_rows
        ),
        "specialized_fallback_families": len(specialized_rows),
        "exact_executable_refinement_present": 0,
        "reviewed_receipt_present": 0,
        "live_provider_switched": 0,
        "fresh_retirement_confirmed": 0,
    }
    _require(summary == expected_summary, "summary does not recompute")
    _require(
        summary["generated_roots"] == 1371
        and summary["source_decisions"] == 1214,
        "authoritative native scope drifted",
    )
    return status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--families", type=Path, default=DEFAULT_FAMILIES)
    parser.add_argument("--members", type=Path, default=DEFAULT_MEMBERS)
    parser.add_argument("--claude-math-root", type=Path)
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    try:
        status = load_and_validate(
            arguments.status,
            arguments.families,
            arguments.members,
            claude_math_root=arguments.claude_math_root,
        )
    except (OSError, KeyError, json.JSONDecodeError,
            NativeArchitectureStatusError) as error:
        print(f"native architecture status validation failed: {error}")
        return 1
    summary = status["summary"]
    if arguments.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            "validated "
            f"{summary['family_count']} aggregate-routed families / "
            f"{summary['generated_roots']} roots; "
            f"{summary['exact_fixed_checker_bundle_mapped_families']} "
            "exact fixed checker bundles; 0 executable refinements / "
            "0 receipts / 0 fresh retirements"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
