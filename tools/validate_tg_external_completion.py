#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed validator for the 13-atom/10-campaign completion audit.

This validator checks the audit against the live gpu_prover inventories and
source tree.  If a sibling claude_math checkout is available, it also checks
every claimed downstream bridge path and marker.  It never executes a
source-scale campaign or treats a planning estimate as a target-SKU
measurement.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any, NoReturn


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT = (
    ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_EXTERNAL_COMPLETION_AUDIT.json"
)
ATOM_INVENTORY = (
    ROOT / "specifications" / "TERNARY_GOLDBACH_EXTERNAL_ATOMS.json"
)
PHYSICAL_INVENTORY = (
    ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_EXTERNAL_ATOM_READINESS.json"
)
PROGRAM_INVENTORY = (
    ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_EXTERNAL_PROGRAM_READINESS.json"
)


class CompletionAuditError(RuntimeError):
    """The completion audit or one of its source cross-checks failed."""


def _fail(message: str) -> NoReturn:
    raise CompletionAuditError(message)


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object,
            parse_constant=lambda token: _fail(
                f"non-finite JSON constant in {path}: {token}"
            ),
        )
    except (OSError, json.JSONDecodeError) as error:
        raise CompletionAuditError(f"cannot load {path}: {error}") from error
    if not isinstance(value, dict):
        _fail(f"{path} must contain one JSON object")
    return value


def _exact_keys(name: str, value: object, expected: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{name} must be an object")
    actual = set(value)
    if actual != expected:
        _fail(
            f"{name} keys differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    return value


def _decimal(name: str, value: object) -> Decimal:
    if not isinstance(value, str):
        _fail(f"{name} must be a decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise CompletionAuditError(f"{name} is not decimal: {value}") from error
    if not result.is_finite():
        _fail(f"{name} must be finite")
    return result


def _relative_path(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{name} must be a nonempty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        _fail(f"{name} is not a repository-relative path: {value}")
    return value


def _validate_evidence(
    campaign_id: str,
    gate_name: str,
    evidence: object,
    *,
    claude_math_root: Path | None,
    require_claude_math: bool,
) -> None:
    if not isinstance(evidence, list) or not evidence:
        _fail(f"{campaign_id}.{gate_name}.evidence must be nonempty")
    for index, raw in enumerate(evidence):
        name = f"{campaign_id}.{gate_name}.evidence[{index}]"
        if not isinstance(raw, dict):
            _fail(f"{name} must be an object")
        if set(raw) not in ({"repository", "path"}, {"repository", "path", "contains"}):
            _fail(f"{name} has unknown or missing fields")
        repository = raw["repository"]
        if repository not in {"gpu_prover", "claude_math"}:
            _fail(f"{name}.repository is not recognized: {repository}")
        relative = _relative_path(f"{name}.path", raw["path"])
        marker = raw.get("contains")
        if marker is not None and (not isinstance(marker, str) or not marker):
            _fail(f"{name}.contains must be a nonempty string")
        if repository == "gpu_prover":
            root = ROOT
        elif claude_math_root is not None:
            root = claude_math_root
        elif require_claude_math:
            _fail("claude_math evidence was required but no checkout was found")
        else:
            continue
        path = root / relative
        if not path.is_file():
            _fail(f"{name} does not exist: {path}")
        if marker is not None:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as error:
                raise CompletionAuditError(
                    f"cannot inspect marker in {path}: {error}"
                ) from error
            if marker not in text:
                _fail(f"{name} marker is absent from {path}: {marker!r}")


def validate_completion_audit(
    audit_path: Path = DEFAULT_AUDIT,
    *,
    claude_math_root: Path | None = None,
    require_claude_math: bool = False,
) -> dict[str, Any]:
    """Validate and return a compact audit result."""

    if claude_math_root is None:
        sibling = ROOT.parent / "claude_math"
        if sibling.is_dir():
            claude_math_root = sibling
    if claude_math_root is not None:
        claude_math_root = claude_math_root.resolve()
        if not claude_math_root.is_dir():
            _fail(f"claude_math root is not a directory: {claude_math_root}")

    audit = _load(audit_path)
    atoms = _load(ATOM_INVENTORY)
    physical = _load(PHYSICAL_INVENTORY)
    programs = _load(PROGRAM_INVENTORY)

    if audit.get("schema_version") != 1:
        _fail("unsupported completion-audit schema_version")
    if (
        audit.get("kind")
        != "sparkinterval.ternary-goldbach.external-completion-audit.v1"
    ):
        _fail("unsupported completion-audit kind")
    if (
        audit.get("classification")
        != "fail-closed-source-audit-not-production-evidence-or-theorem-authority"
    ):
        _fail("completion audit lost its non-authoritative classification")

    policy = audit.get("policy")
    if not isinstance(policy, dict):
        _fail("policy must be an object")
    gates = policy.get("required_gates")
    if not isinstance(gates, list) or not gates or not all(
        isinstance(gate, str) and gate for gate in gates
    ):
        _fail("policy.required_gates must be a nonempty string list")
    if len(gates) != len(set(gates)):
        _fail("policy.required_gates contains duplicates")
    required_gates = set(gates)
    expected_gates = {
        "optimized_full_range_executable",
        "complete_source_artifact",
        "independent_checker",
        "lean_parser",
        "lean_total_checker",
        "lean_soundness",
        "execution_refinement_or_single_trusted_compute_axiom",
        "confidential_azure_path",
        "target_sku_budget_gate",
        "production_receipt",
        "claude_math_production_integration",
    }
    if required_gates != expected_gates:
        _fail("policy.required_gates is not the fixed completion contract")
    if policy.get("completion_requires_every_gate") is not True:
        _fail("completion must require every gate")
    allowed_statuses = policy.get("allowed_statuses")
    if not isinstance(allowed_statuses, list):
        _fail("policy.allowed_statuses must be a list")
    status_set = set(allowed_statuses)

    budget = policy.get("target_sku_budget")
    if not isinstance(budget, dict):
        _fail("policy.target_sku_budget must be an object")
    max_hours = _decimal(
        "target_sku_budget.maximum_wall_hours_exclusive",
        budget.get("maximum_wall_hours_exclusive"),
    )
    max_cost = _decimal(
        "target_sku_budget.maximum_cost_usd_exclusive",
        budget.get("maximum_cost_usd_exclusive"),
    )
    if max_hours != Decimal("168") or max_cost != Decimal("10000"):
        _fail("target-SKU hard limits changed")
    if budget.get("high_endpoints_control") is not True:
        _fail("target-SKU high endpoints must control")

    axiom_spec = policy.get("single_trusted_compute_axiom")
    if not isinstance(axiom_spec, dict):
        _fail("single_trusted_compute_axiom must be an object")
    axiom_path = ROOT / _relative_path(
        "single_trusted_compute_axiom.path", axiom_spec.get("path")
    )
    if axiom_spec.get("repository") != "gpu_prover" or not axiom_path.is_file():
        _fail("the sole trusted-compute axiom source is unavailable")
    axiom_marker = axiom_spec.get("contains")
    if not isinstance(axiom_marker, str) or (
        axiom_path.read_text(encoding="utf-8").count(axiom_marker) != 1
    ):
        _fail("the sole trusted-compute axiom declaration marker is not unique")

    registry_spec = policy.get("production_registry")
    if not isinstance(registry_spec, dict):
        _fail("production_registry must be an object")
    registry_path = ROOT / _relative_path(
        "production_registry.path", registry_spec.get("path")
    )
    registry_marker = registry_spec.get("contains")
    if (
        registry_spec.get("repository") != "gpu_prover"
        or not registry_path.is_file()
        or not isinstance(registry_marker, str)
        or registry_marker not in registry_path.read_text(encoding="utf-8")
    ):
        _fail("production registry is not the audited empty registry")

    expected_atom_ids = {row["id"] for row in atoms["atoms"]}
    physical_rows = {
        row["campaign_id"]: row for row in physical["physical_campaigns"]
    }
    program_rows = {
        row["campaign_id"]: row for row in programs["physical_campaigns"]
    }
    rows = audit.get("campaigns")
    if not isinstance(rows, list) or len(rows) != 10:
        _fail("completion audit must contain exactly ten campaigns")
    row_ids = [row.get("campaign_id") for row in rows if isinstance(row, dict)]
    if len(row_ids) != 10 or len(set(row_ids)) != 10:
        _fail("completion audit campaign ids are malformed or duplicated")
    if set(row_ids) != set(physical_rows) or set(row_ids) != set(program_rows):
        _fail("completion audit campaign roster differs from live inventories")

    seen_atoms: list[str] = []
    computed_gate_counts = {gate: 0 for gate in gates}
    completed = 0
    conditional_bridges = 0
    optimized_complete_statuses = {
        "not_needed_for_this_small_replay",
        "implemented_run_pending",
        "implemented_full_artifact_not_admitted",
        "implemented_and_locally_exercised",
        "implemented_target_sku_calibration_and_run_pending",
    }

    for row in rows:
        campaign_id = row["campaign_id"]
        if set(row) != {"campaign_id", "logical_atom_ids", "gates", "complete"}:
            _fail(f"{campaign_id} has unknown or missing top-level fields")
        atom_ids = row["logical_atom_ids"]
        if (
            not isinstance(atom_ids, list)
            or not atom_ids
            or not all(isinstance(atom, str) for atom in atom_ids)
        ):
            _fail(f"{campaign_id}.logical_atom_ids must be a string list")
        expected_atom_crosswalk = physical_rows[campaign_id]["logical_atom_ids"]
        if atom_ids != expected_atom_crosswalk:
            _fail(f"{campaign_id} logical-atom crosswalk differs")
        seen_atoms.extend(atom_ids)

        row_gates = row["gates"]
        if not isinstance(row_gates, dict) or set(row_gates) != required_gates:
            _fail(f"{campaign_id} gate roster differs from policy")
        satisfied: dict[str, bool] = {}
        for gate_name in gates:
            gate = row_gates[gate_name]
            if not isinstance(gate, dict):
                _fail(f"{campaign_id}.{gate_name} must be an object")
            value = gate.get("satisfied")
            status = gate.get("status")
            detail = gate.get("detail")
            if not isinstance(value, bool):
                _fail(f"{campaign_id}.{gate_name}.satisfied must be Boolean")
            if status not in status_set:
                _fail(f"{campaign_id}.{gate_name}.status is not controlled")
            if not isinstance(detail, str) or not detail:
                _fail(f"{campaign_id}.{gate_name}.detail must be nonempty")
            _validate_evidence(
                campaign_id,
                gate_name,
                gate.get("evidence"),
                claude_math_root=claude_math_root,
                require_claude_math=require_claude_math,
            )
            satisfied[gate_name] = value
            computed_gate_counts[gate_name] += int(value)

        algorithm = physical_rows[campaign_id]["algorithm"]
        optimized_expected = (
            algorithm["full_range_capable"] is True
            and algorithm["optimized_route_status"] in optimized_complete_statuses
        )
        if (
            satisfied["optimized_full_range_executable"]
            is not optimized_expected
        ):
            _fail(
                f"{campaign_id} optimized gate differs from the live "
                "optimized-route status"
            )

        program = program_rows[campaign_id]
        artifact_expected = (
            program["complete_artifact_output"]["lean_source_artifact"]
            == "complete"
        )
        parser_expected = program["strict_parser"]["status"] == (
            "external_and_lean_complete"
        )
        checker_expected = program["total_checker"]["status"].startswith(
            "complete_total_lean_bool"
        )
        soundness_expected = program["lean_soundness"]["status"] == (
            "complete_artifact_acceptance_to_exact_source_claim"
        )
        if satisfied["complete_source_artifact"] is not artifact_expected:
            _fail(f"{campaign_id} complete-source-artifact gate differs")
        if satisfied["lean_parser"] is not parser_expected:
            _fail(f"{campaign_id} Lean-parser gate differs")
        if satisfied["lean_total_checker"] is not checker_expected:
            _fail(f"{campaign_id} Lean-total-checker gate differs")
        if satisfied["lean_soundness"] is not soundness_expected:
            _fail(f"{campaign_id} Lean-soundness gate differs")
        if satisfied["confidential_azure_path"] is not bool(
            physical_rows[campaign_id]["deployment"]["materializers"]
        ):
            _fail(f"{campaign_id} Azure-path gate differs")
        machine_gate = row_gates[
            "execution_refinement_or_single_trusted_compute_axiom"
        ]
        if (
            not satisfied[
                "execution_refinement_or_single_trusted_compute_axiom"
            ]
            or machine_gate["status"] != "single_trusted_compute_axiom"
        ):
            _fail(f"{campaign_id} lost its closed single-axiom registration")
        machine_evidence = {
            item["path"] for item in machine_gate["evidence"]
        }
        registered_certificate = physical_rows[campaign_id][
            "semantic_output"
        ]["registered_certificate"]
        if registered_certificate not in machine_evidence:
            _fail(
                f"{campaign_id} machine-trust gate does not cite its exact "
                "registered certificate"
            )
        azure_evidence = {
            item["path"]
            for item in row_gates["confidential_azure_path"]["evidence"]
        }
        missing_materializers = set(
            physical_rows[campaign_id]["deployment"]["materializers"]
        ) - azure_evidence
        if missing_materializers:
            _fail(
                f"{campaign_id} Azure gate omits materializers: "
                f"{sorted(missing_materializers)}"
            )

        benchmark = physical_rows[campaign_id]["benchmark"]
        target_gate = row_gates["target_sku_budget_gate"]
        if (
            target_gate.get("target_sku_measured")
            is not benchmark["target_azure_sku_measured"]
        ):
            _fail(f"{campaign_id} target-SKU measurement flag differs")
        if (
            target_gate.get("planning_wall_hours_high")
            != benchmark["projected_wall_hours_high"]
        ):
            _fail(f"{campaign_id} planning high wall endpoint differs")
        target_hours = target_gate.get("target_measured_wall_hours_high")
        target_cost = target_gate.get("target_measured_cost_usd_high")
        target_expected = False
        if benchmark["target_azure_sku_measured"]:
            if target_hours is None or target_cost is None:
                _fail(
                    f"{campaign_id} measured target route lacks high endpoints"
                )
            target_expected = (
                _decimal(f"{campaign_id}.target hours", target_hours)
                < max_hours
                and _decimal(f"{campaign_id}.target cost", target_cost)
                < max_cost
            )
        elif target_hours is not None or target_cost is not None:
            _fail(
                f"{campaign_id} advertises target endpoints without a "
                "target-SKU measurement"
            )
        if satisfied["target_sku_budget_gate"] is not target_expected:
            _fail(f"{campaign_id} target-SKU budget gate is inconsistent")

        receipt_expected = (
            program["catalog"]["production_artifact_installed"]
            and program["catalog"]["reviewed_receipt_installed"]
        )
        if satisfied["production_receipt"] is not receipt_expected:
            _fail(f"{campaign_id} production-receipt gate differs")
        claude_gate = row_gates["claude_math_production_integration"]
        if claude_gate.get("conditional_source_bridge_present") is not True:
            _fail(f"{campaign_id} lacks its conditional claude_math bridge")
        conditional_bridges += 1
        if satisfied["claude_math_production_integration"] and not satisfied[
            "production_receipt"
        ]:
            _fail(
                f"{campaign_id} claims production integration without a receipt"
            )

        row_complete = all(satisfied.values())
        if row["complete"] is not row_complete:
            _fail(f"{campaign_id}.complete is not the conjunction of its gates")
        completed += int(row_complete)

    if len(seen_atoms) != 13 or len(set(seen_atoms)) != 13:
        _fail("completion audit does not map exactly thirteen unique atoms")
    if set(seen_atoms) != expected_atom_ids:
        _fail("completion audit atom roster differs from the live inventory")

    summary = audit.get("summary")
    if not isinstance(summary, dict):
        _fail("summary must be an object")
    if summary.get("campaigns_complete") != completed:
        _fail("summary.campaigns_complete differs from the rows")
    if (
        summary.get("conditional_claude_math_source_bridges")
        != conditional_bridges
    ):
        _fail("summary conditional-bridge count differs from the rows")
    if summary.get("satisfied_gate_counts") != computed_gate_counts:
        _fail("summary.satisfied_gate_counts differs from the rows")
    if completed != 0:
        _fail(
            "this source snapshot unexpectedly claims a production-complete "
            "campaign; re-audit pins, receipts, target measurements, and "
            "claude_math integration before changing the validator"
        )

    return {
        "schema": "sparkinterval.tg.external-completion-audit-validation.v1",
        "audit": str(audit_path),
        "campaign_count": len(rows),
        "logical_atom_count": len(seen_atoms),
        "campaigns_complete": completed,
        "satisfied_gate_counts": computed_gate_counts,
        "claude_math_checked": claude_math_root is not None,
        "classification": "validated-source-audit-not-production-evidence",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--claude-math-root", type=Path)
    parser.add_argument("--require-claude-math", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate_completion_audit(
            args.audit,
            claude_math_root=args.claude_math_root,
            require_claude_math=args.require_claude_math,
        )
    except CompletionAuditError as error:
        print(f"external completion audit error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            result,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
