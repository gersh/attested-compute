#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded cross-layer audit of the eleven TG registered campaign terminals.

This command imports source definitions and reads small source/JSON files.  It
does not materialize an Azure job and never runs a mathematical campaign.
Its output is registration-topology evidence only: it is not execution
evidence, theorem authority, or an analytic realization.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import generate_trusted_compute_lean as lean_generator  # noqa: E402
from tg_verifier.h100_cluster import WORKLOADS  # noqa: E402


DEFAULT_MATRIX = (
    ROOT / "specifications/TERNARY_GOLDBACH_REGISTERED_CAMPAIGN_MATRIX.json"
)
SEMANTIC_BINDINGS = (
    ROOT / "specifications/TERNARY_GOLDBACH_AZURE_SEMANTIC_BINDINGS.json"
)
REGISTERED_ALGORITHM = ROOT / "SparkInterval/Execution/RegisteredAlgorithm.lean"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
BACKEND_FROM_CLASS = {
    "cpu_exact_sidecar": "azure_sevsnp_cpu",
    "cpu_flint_sidecar": "azure_sevsnp_cpu",
    "h100_cuda": "azure_ncc40ads_h100_v5",
}
MATRIX_FIELDS = {
    "scope",
    "campaign_id",
    "owner_atom_id",
    "registered_algorithm",
    "registered_invocation",
    "factory_module",
    "factory_attribute",
    "factory_arguments",
    "materializer_module",
    "terminal_receipt_backend",
    "semantic_binding_state",
    "registered_result_output",
}


class AuditError(ValueError):
    """The source-owned audit matrix itself is malformed."""


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def compact_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AuditError(f"cannot read {path}: {error}") from error


def load_matrix(path: Path = DEFAULT_MATRIX) -> list[dict[str, Any]]:
    value = _load_json(path)
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "kind", "classification", "campaigns"}
        or value["schema_version"] != 1
        or value["kind"]
        != "sparkinterval.ternary-goldbach.registered-campaign-matrix.v1"
        or value["classification"]
        != (
            "source-registration-consistency-only-not-execution-evidence-or-"
            "analytic-realization"
        )
        or not isinstance(value["campaigns"], list)
        or len(value["campaigns"]) != 11
    ):
        raise AuditError("registered campaign matrix header or campaign count differs")
    campaigns: list[dict[str, Any]] = []
    ids: list[str] = []
    invocations: list[str] = []
    scopes: list[str] = []
    for index, row in enumerate(value["campaigns"]):
        if not isinstance(row, dict) or set(row) != MATRIX_FIELDS:
            raise AuditError(f"campaign matrix row {index} fields differ")
        if row["scope"] not in {
            "named_physical_campaign",
            "lowered_goldbach_alternate",
        }:
            raise AuditError(f"campaign matrix row {index} scope differs")
        for field in (
            "campaign_id",
            "owner_atom_id",
            "factory_module",
            "factory_attribute",
            "materializer_module",
            "terminal_receipt_backend",
        ):
            if not isinstance(row[field], str) or not row[field]:
                raise AuditError(f"campaign matrix row {index} {field} is invalid")
        for field in ("registered_algorithm", "registered_invocation"):
            if (
                not isinstance(row[field], str)
                or IDENTIFIER_RE.fullmatch(row[field]) is None
            ):
                raise AuditError(f"campaign matrix row {index} {field} is invalid")
        if (
            not isinstance(row["factory_arguments"], list)
            or row["semantic_binding_state"]
            not in {"enabled", "staged_disabled", "null_disabled"}
            or (
                row["registered_result_output"] is not None
                and (
                    not isinstance(row["registered_result_output"], str)
                    or not row["registered_result_output"]
                )
            )
        ):
            raise AuditError(f"campaign matrix row {index} payload is invalid")
        ids.append(row["campaign_id"])
        invocations.append(row["registered_invocation"])
        scopes.append(row["scope"])
        campaigns.append(dict(row))
    if len(ids) != len(set(ids)) or len(invocations) != len(set(invocations)):
        raise AuditError("campaign ids and registered invocations must be unique")
    if scopes.count("named_physical_campaign") != 10:
        raise AuditError("matrix must contain exactly ten named physical campaigns")
    if scopes.count("lowered_goldbach_alternate") != 1:
        raise AuditError("matrix must contain exactly one lowered Goldbach alternate")
    return campaigns


def _lean_block(source: str, start: str, end: str) -> str:
    try:
        return source.split(start, 1)[1].split(end, 1)[0]
    except IndexError as error:
        raise AuditError(f"cannot locate Lean block {start!r} .. {end!r}") from error


def _lean_case_string(block: str, constructor: str) -> str | None:
    match = re.search(
        rf"\|\s+\.{re.escape(constructor)}\s*=>\s*"
        rf'"([0-9a-zA-Z._-]+)"',
        block,
    )
    return None if match is None else match.group(1)


def _lean_identity_tables(source: str) -> dict[str, dict[str, str | None]]:
    algorithm_map = _lean_block(
        source,
        "def algorithm : RegisteredInvocation → RegisteredAlgorithm",
        "/-- Exact canonical input selected by a closed invocation.",
    )
    algorithm_id = _lean_block(
        source,
        "def algorithmId : RegisteredAlgorithm → String",
        "`RunStatement.algorithmHash`.",
    )
    algorithm_hash = _lean_block(
        source,
        "def algorithmHash (algorithm : RegisteredAlgorithm) : Digest :=",
        "/-- Executable audit check for the source-reviewed algorithm digest.",
    )
    parameters_hash = _lean_block(
        source,
        "def canonicalParametersHash : RegisteredAlgorithm → Digest",
        "/-- Source-reviewed SHA-256 of the canonical source domain bytes.",
    )
    domain_hash = _lean_block(
        source,
        "def canonicalDomainHash : RegisteredAlgorithm → Digest",
        "/-- Executable audit check for the source-reviewed metadata digests.",
    )
    input_hash = _lean_block(
        source,
        "def canonicalInputHash : RegisteredInvocation → Digest",
        "/-- Executable audit check for the source-reviewed input digest.",
    )
    invocation_to_algorithm = {
        match.group(1): match.group(2)
        for match in re.finditer(
            r"\|\s+\.([A-Za-z_][A-Za-z0-9_]*)\s*=>\s*"
            r"\.([A-Za-z_][A-Za-z0-9_]*)",
            algorithm_map,
        )
    }
    algorithms = set(invocation_to_algorithm.values())
    return {
        invocation: {
            "registered_algorithm": algorithm,
            "algorithm_id": _lean_case_string(algorithm_id, algorithm),
            "algorithm_hash": _lean_case_string(algorithm_hash, algorithm),
            "parameters_hash": _lean_case_string(parameters_hash, algorithm),
            "domain_hash": _lean_case_string(domain_hash, algorithm),
            "input_hash": _lean_case_string(input_hash, invocation),
        }
        for invocation, algorithm in invocation_to_algorithm.items()
        if algorithm in algorithms
    }


def _factory(row: Mapping[str, Any]) -> object:
    module = importlib.import_module(row["factory_module"])
    selected = getattr(module, row["factory_attribute"])
    arguments = row["factory_arguments"]
    return selected(*arguments) if callable(selected) else selected


def _terminal_workload(row: Mapping[str, Any]) -> tuple[object | None, tuple[str, ...], str | None]:
    matches = [
        workload
        for workload in WORKLOADS
        if workload.campaign_id == row["campaign_id"]
        and workload.shared_owner_atom is None
    ]
    if len(matches) != 1:
        return None, (), None
    workload = matches[0]
    if workload.postcheck:
        return workload, tuple(workload.postcheck), "cpu_exact_sidecar"
    if workload.execution_mode == "manual_phase_dag":
        if not workload.phase_dag:
            return workload, (), None
        phase = workload.phase_dag[-1]
        return (
            workload,
            tuple(phase.command),
            phase.backend_class or workload.backend_class,
        )
    return workload, tuple(workload.command), workload.backend_class


def _semantic_state(row: Mapping[str, Any]) -> str:
    if row.get("enabled") is True:
        return "enabled"
    if row.get("enabled") is not False:
        return "invalid"
    payload = (
        row.get("lean_theorem"),
        row.get("realization_id"),
        row.get("registered_invocation"),
    )
    if all(value is None for value in payload):
        return "null_disabled"
    if all(isinstance(value, str) and value for value in payload):
        return "staged_disabled"
    return "invalid"


def _argv_value(argv: Sequence[str], option: str) -> tuple[str | None, int]:
    positions = [index for index, token in enumerate(argv) if token == option]
    if len(positions) != 1:
        return None, len(positions)
    position = positions[0]
    if position + 1 >= len(argv):
        return None, 1
    return argv[position + 1], 1


def _mismatch(
    mismatches: list[dict[str, Any]],
    *,
    layer: str,
    check: str,
    expected: Any,
    actual: Any,
) -> None:
    if actual != expected:
        mismatches.append(
            {
                "layer": layer,
                "check": check,
                "expected": expected,
                "actual": actual,
            }
        )


def build_report(
    matrix_path: Path = DEFAULT_MATRIX,
    *,
    semantic_bindings_path: Path = SEMANTIC_BINDINGS,
    registered_algorithm_path: Path = REGISTERED_ALGORITHM,
) -> dict[str, Any]:
    matrix = load_matrix(matrix_path)
    semantic_document = _load_json(semantic_bindings_path)
    if (
        not isinstance(semantic_document, dict)
        or not isinstance(semantic_document.get("bindings"), list)
    ):
        raise AuditError("semantic binding inventory is malformed")
    semantic_rows = {
        row.get("campaign_id"): row
        for row in semantic_document["bindings"]
        if isinstance(row, dict)
    }
    lean_source = registered_algorithm_path.read_text(encoding="utf-8")
    lean_tables = _lean_identity_tables(lean_source)
    theorem_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "SparkInterval/Execution").glob("*.lean"))
    )
    matrix_ids = {row["campaign_id"] for row in matrix}
    inventory_ids = set(semantic_rows)
    global_mismatches: list[dict[str, Any]] = []
    _mismatch(
        global_mismatches,
        layer="semantic_binding_inventory",
        check="campaign_id_roster",
        expected=sorted(matrix_ids),
        actual=sorted(inventory_ids),
    )
    rows: list[dict[str, Any]] = []
    for matrix_row in matrix:
        campaign_id = matrix_row["campaign_id"]
        invocation = matrix_row["registered_invocation"]
        algorithm = matrix_row["registered_algorithm"]
        mismatches: list[dict[str, Any]] = []

        expected = lean_generator.registered_invocation_expected(invocation)
        expected_backend = lean_generator.registered_invocation_backend(invocation)
        _mismatch(
            mismatches,
            layer="python_generator_registry",
            check="registered_invocation_member",
            expected=True,
            actual=invocation in lean_generator.REGISTERED_INVOCATIONS,
        )
        _mismatch(
            mismatches,
            layer="python_generator_registry",
            check="backend",
            expected=matrix_row["terminal_receipt_backend"],
            actual=expected_backend,
        )

        lean = lean_tables.get(invocation, {})
        _mismatch(
            mismatches,
            layer="lean_registry",
            check="registered_algorithm",
            expected=algorithm,
            actual=lean.get("registered_algorithm"),
        )
        for field in (
            "algorithm_id",
            "algorithm_hash",
            "input_hash",
            "parameters_hash",
            "domain_hash",
        ):
            _mismatch(
                mismatches,
                layer="lean_registry",
                check=field,
                expected=expected[field],
                actual=lean.get(field),
            )

        factory = _factory(matrix_row)
        factory_identity = {
            "registered_invocation": getattr(factory, "registered_invocation", None),
            "algorithm_id": getattr(factory, "algorithm_id", None),
            "algorithm_hash": sha256(
                getattr(factory, "algorithm_definition", "").encode("utf-8")
            ),
            "input_hash": sha256(getattr(factory, "input_bytes", b"")),
            "parameters_hash": sha256(
                compact_json_bytes(getattr(factory, "parameters", None))
            ),
            "domain_hash": sha256(compact_json_bytes(getattr(factory, "domain", None))),
        }
        _mismatch(
            mismatches,
            layer="terminal_workload_factory",
            check="registered_invocation",
            expected=invocation,
            actual=factory_identity["registered_invocation"],
        )
        for field in (
            "algorithm_id",
            "algorithm_hash",
            "input_hash",
            "parameters_hash",
            "domain_hash",
        ):
            _mismatch(
                mismatches,
                layer="terminal_workload_factory",
                check=field,
                expected=expected[field],
                actual=factory_identity[field],
            )

        workload, terminal_argv, terminal_backend_class = _terminal_workload(
            matrix_row
        )
        _mismatch(
            mismatches,
            layer="cluster_campaign",
            check="owner_atom_id",
            expected=matrix_row["owner_atom_id"],
            actual=None if workload is None else workload.atom_id,
        )
        factory_portfolio_argv = tuple(getattr(factory, "portfolio_argv", ()))
        _mismatch(
            mismatches,
            layer="cluster_campaign",
            check="terminal_argv",
            expected=list(factory_portfolio_argv),
            actual=list(terminal_argv),
        )
        cluster_backend = BACKEND_FROM_CLASS.get(terminal_backend_class)
        _mismatch(
            mismatches,
            layer="cluster_campaign",
            check="terminal_receipt_backend",
            expected=matrix_row["terminal_receipt_backend"],
            actual=cluster_backend,
        )

        registered_result, result_option_count = _argv_value(
            factory_portfolio_argv, "--registered-result-output"
        )
        _mismatch(
            mismatches,
            layer="terminal_result_artifact",
            check="registered_result_option_count",
            expected=0 if matrix_row["registered_result_output"] is None else 1,
            actual=result_option_count,
        )
        _mismatch(
            mismatches,
            layer="terminal_result_artifact",
            check="registered_result_output",
            expected=matrix_row["registered_result_output"],
            actual=registered_result,
        )
        command_output, command_output_count = _argv_value(
            tuple(getattr(factory, "command_argv", ())), "--output"
        )
        replay_output, replay_output_count = _argv_value(
            tuple(getattr(factory, "trace_verifier_argv", ())), "--output"
        )
        _mismatch(
            mismatches,
            layer="terminal_result_artifact",
            check="measured_command_output",
            expected=("@output@", 1),
            actual=(command_output, command_output_count),
        )
        _mismatch(
            mismatches,
            layer="terminal_result_artifact",
            check="trace_replay_output",
            expected=("@output@", 1),
            actual=(replay_output, replay_output_count),
        )

        materializer = importlib.import_module(matrix_row["materializer_module"])
        materializer_source_path = ROOT / (
            matrix_row["materializer_module"].replace(".", "/") + ".py"
        )
        materializer_source = materializer_source_path.read_text(encoding="utf-8")
        operator = getattr(materializer, "cpu_operator", None)
        if operator is None:
            operator = getattr(materializer, "h100_operator", None)
        materializer_backend = None if operator is None else getattr(operator, "BACKEND", None)
        _mismatch(
            mismatches,
            layer="azure_materializer",
            check="imports_terminal_factory_module",
            expected=True,
            actual=(
                f"from {matrix_row['factory_module']} import" in materializer_source
            ),
        )
        _mismatch(
            mismatches,
            layer="azure_materializer",
            check="terminal_receipt_backend",
            expected=matrix_row["terminal_receipt_backend"],
            actual=materializer_backend,
        )
        _mismatch(
            mismatches,
            layer="azure_materializer",
            check="registered_result_output_contract",
            expected=True,
            actual='"output/registered-result.txt"' in materializer_source,
        )

        semantic = semantic_rows.get(campaign_id, {})
        actual_semantic_state = _semantic_state(semantic)
        _mismatch(
            mismatches,
            layer="semantic_binding_inventory",
            check="state",
            expected=matrix_row["semantic_binding_state"],
            actual=actual_semantic_state,
        )
        expected_semantic_invocation = (
            None
            if matrix_row["semantic_binding_state"] == "null_disabled"
            else invocation
        )
        _mismatch(
            mismatches,
            layer="semantic_binding_inventory",
            check="registered_invocation",
            expected=expected_semantic_invocation,
            actual=semantic.get("registered_invocation"),
        )
        theorem = semantic.get("lean_theorem")
        theorem_leaf = (
            theorem.rsplit(".", 1)[-1] if isinstance(theorem, str) else None
        )
        theorem_present = (
            theorem_leaf is not None
            and re.search(
                rf"\btheorem\s+{re.escape(theorem_leaf)}\b", theorem_sources
            )
            is not None
        )
        _mismatch(
            mismatches,
            layer="semantic_binding_inventory",
            check="staged_theorem_exists",
            expected=matrix_row["semantic_binding_state"] != "null_disabled",
            actual=theorem_present,
        )

        rows.append(
            {
                "scope": matrix_row["scope"],
                "campaign_id": campaign_id,
                "owner_atom_id": matrix_row["owner_atom_id"],
                "registered_algorithm": algorithm,
                "registered_invocation": invocation,
                "algorithm_id": expected["algorithm_id"],
                "algorithm_hash": expected["algorithm_hash"],
                "input_hash": expected["input_hash"],
                "parameters_hash": expected["parameters_hash"],
                "domain_hash": expected["domain_hash"],
                "terminal_factory": {
                    "module": matrix_row["factory_module"],
                    "attribute": matrix_row["factory_attribute"],
                    "arguments": matrix_row["factory_arguments"],
                },
                "terminal_materializer": matrix_row["materializer_module"],
                "terminal_receipt_backend": matrix_row["terminal_receipt_backend"],
                "registered_result_output": matrix_row["registered_result_output"],
                "semantic_binding": {
                    "state": actual_semantic_state,
                    "enabled": semantic.get("enabled"),
                    "registered_invocation": semantic.get("registered_invocation"),
                    "realization_id": semantic.get("realization_id"),
                    "lean_theorem": theorem,
                },
                "analytic_realization_claimed_by_this_report": False,
                "status": "consistent" if not mismatches else "mismatch",
                "mismatches": mismatches,
            }
        )

    mismatch_count = len(global_mismatches) + sum(
        len(row["mismatches"]) for row in rows
    )
    return {
        "schema_version": 1,
        "kind": "sparkinterval.ternary-goldbach.registered-campaign-audit.v1",
        "classification": (
            "bounded-source-consistency-report-not-execution-evidence-"
            "theorem-authority-or-analytic-realization"
        ),
        "matrix": matrix_path.relative_to(ROOT).as_posix(),
        "summary": {
            "named_physical_campaigns": sum(
                row["scope"] == "named_physical_campaign" for row in rows
            ),
            "named_physical_terminal_result_contracts": sum(
                row["scope"] == "named_physical_campaign"
                and row["registered_result_output"] is not None
                for row in rows
            ),
            "all_named_physical_terminal_result_contracts_reviewed": all(
                row["registered_result_output"] is not None
                for row in rows
                if row["scope"] == "named_physical_campaign"
            ),
            "lowered_goldbach_alternates": sum(
                row["scope"] == "lowered_goldbach_alternate" for row in rows
            ),
            "semantic_bindings_enabled": sum(
                row["semantic_binding"]["state"] == "enabled" for row in rows
            ),
            "semantic_bindings_staged_disabled": sum(
                row["semantic_binding"]["state"] == "staged_disabled"
                for row in rows
            ),
            "semantic_bindings_null_disabled": sum(
                row["semantic_binding"]["state"] == "null_disabled"
                for row in rows
            ),
            "mismatch_count": mismatch_count,
            "all_registration_layers_consistent": mismatch_count == 0,
            "analytic_realizations_established": 0,
            "production_runs_established": 0,
        },
        "global_mismatches": global_mismatches,
        "campaigns": rows,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument(
        "--check",
        action="store_true",
        help="return nonzero when any exact cross-layer mismatch is found",
    )
    arguments = parser.parse_args(argv)
    try:
        report = build_report(arguments.matrix)
    except (AuditError, OSError, AttributeError, TypeError, ValueError) as error:
        parser.error(str(error))
    sys.stdout.buffer.write(canonical_json_bytes(report))
    return (
        1
        if arguments.check and report["summary"]["mismatch_count"] != 0
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
