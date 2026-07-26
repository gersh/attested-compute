# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded, read-only Azure launch preflight for the ten source campaigns.

This module audits source packaging.  It does not read Azure credentials,
materialize a measured job, create a cloud resource, run campaign arithmetic,
or grant a receipt theorem authority.  In particular, a schema-valid redacted
example is reported as ``site-pin-needed`` rather than as a deployable site
configuration.
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable, Mapping

try:
    import jsonschema
except ImportError:  # pragma: no cover - exercised by the explicit error path.
    jsonschema = None

from tg_verifier import azure_portfolio
from tg_verifier.h100_cluster import WORKLOADS, build_manifest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from generate_trusted_compute_lean import (  # noqa: E402
    registered_invocation_backend,
    registered_invocation_expected,
)


SCHEMA_VERSION = 1
KIND = "sparkinterval.azure.tg.launch-preflight.v1"
READINESS_PATH = (
    REPOSITORY_ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_EXTERNAL_ATOM_READINESS.json"
)
PROGRAM_READINESS_PATH = (
    REPOSITORY_ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_EXTERNAL_PROGRAM_READINESS.json"
)
SEMANTIC_BINDINGS_PATH = (
    REPOSITORY_ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_AZURE_SEMANTIC_BINDINGS.json"
)

SITE_SCHEMA_BY_EXAMPLE = {
    "azure_cpu_a7_materializer_site.redacted.json":
        "azure-cpu-a7-materializer-site.schema.json",
    "azure_cpu_cdem_artifact_terminal_materializer_site.redacted.json":
        "azure-cpu-cdem-artifact-terminal-materializer-site.schema.json",
    "azure_cpu_dirichlet_materializer_site.redacted.json":
        "azure-cpu-dirichlet-materializer-site.schema.json",
    "azure_cpu_dirichlet_postcheck_materializer_site.redacted.json":
        "azure-cpu-dirichlet-postcheck-materializer-site.schema.json",
    "azure_cpu_goldbach_historical_operational_materializer_site.redacted.json":
        "azure-cpu-goldbach-historical-operational-materializer-site.schema.json",
    "azure_cpu_goldbach_historical_terminal_materializer_site.redacted.json":
        "azure-cpu-goldbach-historical-terminal-materializer-site.schema.json",
    "azure_cpu_hurst_materializer_site.redacted.json":
        "azure-cpu-hurst-portfolio-materializer-site.schema.json",
    "azure_cpu_platt_head_materializer_site.redacted.json":
        "azure-cpu-platt-head-materializer-site.schema.json",
    "azure_cpu_platt_pt21_materializer_site.redacted.json":
        "azure-cpu-platt-pt21-materializer-site.schema.json",
    "azure_cpu_portfolio_materializer_site.redacted.json":
        "azure-cpu-portfolio-materializer-site.schema.json",
    "azure_cpu_prop1224_materializer_site.redacted.json":
        "azure-cpu-prop1224-materializer-site.schema.json",
    "azure_cpu_psi_portfolio_materializer_site.redacted.json":
        "azure-cpu-psi-portfolio-materializer-site.schema.json",
    "azure_h100_dirichlet_packed_materializer_site.redacted.json":
        "azure-h100-dirichlet-packed-materializer-site.schema.json",
    "azure_h100_goldbach_historical_materializer_site.redacted.json":
        "azure-h100-goldbach-historical-materializer-site.schema.json",
    "azure_h100_r2star_materializer_site.redacted.json":
        "azure-h100-r2star-materializer-site.schema.json",
}

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_REDACTION_TEXT = re.compile(
    r"(?:REPLACE(?:-|_)|replace\.|redacted)", re.IGNORECASE
)


class AzureLaunchPreflightError(RuntimeError):
    """The source launch inventory could not be audited exactly."""


def _load_json(path: Path, what: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AzureLaunchPreflightError(f"cannot load {what}: {error}") from error
    if not isinstance(value, dict):
        raise AzureLaunchPreflightError(f"{what} must be a JSON object")
    return value


def _rows_by_campaign(
    value: Mapping[str, Any], what: str
) -> dict[str, dict[str, Any]]:
    rows = value.get("physical_campaigns")
    if not isinstance(rows, list):
        raise AzureLaunchPreflightError(f"{what} has no physical_campaigns list")
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("campaign_id"), str):
            raise AzureLaunchPreflightError(
                f"{what} campaign row {index} is malformed"
            )
        campaign_id = row["campaign_id"]
        if campaign_id in result:
            raise AzureLaunchPreflightError(
                f"{what} repeats campaign {campaign_id}"
            )
        result[campaign_id] = row
    return result


def _direct_cluster_paths() -> list[str]:
    """Return the exact direct paths required by the topology manifest."""

    paths = {
        "reference/tg_cdem_abel.cpp",
        "tg_verifier/h100_cluster.py",
        "tools/tg_h100_cluster.py",
    }
    prefix = "${TG_REPOSITORY}/"
    for workload in WORKLOADS:
        phase_tokens = tuple(
            token for phase in workload.phase_dag for token in phase.command
        )
        paths.update(
            token[len(prefix):]
            for token in (*workload.command, *workload.postcheck, *phase_tokens)
            if token.startswith(prefix)
        )
    return sorted(paths)


def _prototype_cluster() -> dict[str, Any]:
    """Build topology with conspicuously non-evidentiary placeholder pins."""

    files = [
        {"path": path, "sha256": "0" * 64, "size_bytes": 0}
        for path in _direct_cluster_paths()
    ]
    return build_manifest(
        {
            "clean_worktree": True,
            "coverage": "all_git_tracked_regular_files",
            "file_count": len(files),
            "files": files,
            "git_commit_oid": "0" * 40,
            "git_object_format": "sha1",
            "git_tree_oid": "0" * 40,
            "kind": "sparkinterval.tg.clean_git_repository_closure.v1",
            "untracked_files_absent": True,
        }
    )


def _prototype_plan(semantic_bindings: Mapping[str, Any]) -> dict[str, Any]:
    """Expand source topology while neutralizing only the dynamic budget input."""

    required = azure_portfolio.COMPLETION_PROFILES[
        azure_portfolio.SOURCE_RETIREMENT_PROFILE
    ].required_campaign_ids
    spec = {
        "challenge_ttl_seconds": 3600,
        "cluster_manifest": {"sha256": "0" * 64},
        "completion_profile": azure_portfolio.SOURCE_RETIREMENT_PROFILE,
        "portfolio_id": "read-only-source-preflight",
        "production_price_class": "pay_as_you_go",
        "run_root": "/preflight-does-not-write",
        "semantic_bindings": {"sha256": "0" * 64},
        "verifier_key_manifest": {"sha256": "0" * 64},
    }
    # This synthetic gate is not emitted as evidence.  It lets the preflight
    # inspect operator/materializer and semantic gaps independently of current
    # pricing.  The returned campaign rows still report calibration as blocked
    # from the authoritative readiness inventory.
    budget_gate = {
        "blocking_campaign_ids": [],
        "covered_campaign_ids": list(required),
        "hard_max_cost_usd": "10000",
        "hard_max_wall_hours": "168",
        "high_endpoints_control": True,
        "portfolio_high_cost_usd": "0",
        "portfolio_high_wall_hours": "0",
        "price_class": "pay_as_you_go",
        "production_ready": True,
        "report_schema": "read-only-source-preflight",
        "snapshot_date": "1970-01-01",
    }
    return azure_portfolio.build_plan(
        spec,
        _prototype_cluster(),
        semantic_bindings,
        production_budget_gate=budget_gate,
    )


def _redaction_markers(
    value: Any, *, location: str = "$"
) -> list[str]:
    """Find conspicuous redacted/example-only values without resolving paths."""

    markers: list[str] = []
    if isinstance(value, dict):
        if value.get("status") == "unconfigured":
            markers.append(f"{location}.status=unconfigured")
        for key, child in value.items():
            markers.extend(
                _redaction_markers(child, location=f"{location}.{key}")
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            markers.extend(
                _redaction_markers(child, location=f"{location}[{index}]")
            )
    elif isinstance(value, str):
        if _REDACTION_TEXT.search(value):
            markers.append(f"{location}=redacted-text")
        elif _SHA256_RE.fullmatch(value) and len(set(value)) == 1:
            markers.append(f"{location}=placeholder-sha256")
    return sorted(set(markers))


def _check_site_example(relative: str) -> dict[str, Any]:
    path = REPOSITORY_ROOT / relative
    schema_name = SITE_SCHEMA_BY_EXAMPLE.get(path.name)
    if schema_name is None:
        raise AzureLaunchPreflightError(
            f"no reviewed schema mapping for site example {relative}"
        )
    value = _load_json(path, f"site example {relative}")
    schema_path = REPOSITORY_ROOT / "schemas" / schema_name
    schema = _load_json(schema_path, f"site schema {schema_name}")
    if jsonschema is None:
        raise AzureLaunchPreflightError(
            "jsonschema is required for Azure launch preflight"
        )
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(value, schema)
    except jsonschema.exceptions.ValidationError as error:
        raise AzureLaunchPreflightError(
            f"site example {relative} is not schema-valid: {error.message}"
        ) from error
    except jsonschema.exceptions.SchemaError as error:
        raise AzureLaunchPreflightError(
            f"site schema {schema_name} is invalid: {error.message}"
        ) from error
    markers = _redaction_markers(value)
    return {
        "example": relative,
        "redaction_marker_count": len(markers),
        "redaction_markers": markers,
        "schema": f"schemas/{schema_name}",
        "schema_valid": True,
        "usable_as_production_site_configuration": not markers,
    }


def _check_cli(relative: str, *, run_help: bool) -> dict[str, Any]:
    path = REPOSITORY_ROOT / relative
    exists = path.is_file()
    executable = exists and bool(path.stat().st_mode & 0o111)
    shebang = exists and path.read_bytes().splitlines()[:1] == [
        b"#!/usr/bin/env python3"
    ]
    help_checked = False
    help_exit_code: int | None = None
    help_error: str | None = None
    if run_help and exists and executable:
        help_checked = True
        try:
            completed = subprocess.run(
                [str(path), "--help"],
                cwd=REPOSITORY_ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            help_exit_code = completed.returncode
            if completed.returncode != 0:
                help_error = (
                    completed.stderr.strip()
                    or completed.stdout.strip()
                    or "nonzero --help exit"
                )
        except (OSError, subprocess.TimeoutExpired) as error:
            help_error = str(error)
    discovered = (
        exists
        and executable
        and shebang
        and (not run_help or (help_exit_code == 0 and help_error is None))
    )
    return {
        "cli": relative,
        "directly_executable": executable,
        "discovered": discovered,
        "exists": exists,
        "help_checked": help_checked,
        "help_error": help_error,
        "help_exit_code": help_exit_code,
        "python3_shebang": shebang,
    }


def _algorithm_incomplete(row: Mapping[str, Any]) -> bool:
    status = row["algorithm"]["optimized_route_status"]
    return isinstance(status, str) and "incomplete" in status


def _semantic_shape(
    campaign_id: str,
    binding: Mapping[str, Any],
) -> str:
    if binding.get("enabled") is True:
        return "enabled_source_shape_without_run_authority"
    realization_id = binding.get("realization_id")
    if isinstance(realization_id, str):
        pending = azure_portfolio.PENDING_TG_REALIZATIONS.get(realization_id)
        expected = {
            "campaign_id": campaign_id,
            "lean_theorem": binding.get("lean_theorem"),
            "registered_invocation": binding.get("registered_invocation"),
        }
        if pending == expected:
            return "staged_pending_not_authoritative"
        return "disabled_unreviewed_shape"
    return "absent"


def build_preflight_report(*, run_cli_help: bool = True) -> dict[str, Any]:
    """Return a bounded source audit; never perform cloud or campaign work."""

    readiness = _load_json(READINESS_PATH, "external-atom readiness inventory")
    program_readiness = _load_json(
        PROGRAM_READINESS_PATH, "external-program readiness inventory"
    )
    semantic = _load_json(
        SEMANTIC_BINDINGS_PATH, "Azure semantic binding inventory"
    )
    readiness_rows = _rows_by_campaign(readiness, "external-atom readiness")
    program_rows = _rows_by_campaign(
        program_readiness, "external-program readiness"
    )
    bindings_raw = semantic.get("bindings")
    if not isinstance(bindings_raw, list):
        raise AzureLaunchPreflightError(
            "Azure semantic binding inventory has no bindings list"
        )
    bindings = {
        row["campaign_id"]: row
        for row in bindings_raw
        if isinstance(row, dict) and isinstance(row.get("campaign_id"), str)
    }

    required = azure_portfolio.COMPLETION_PROFILES[
        azure_portfolio.SOURCE_RETIREMENT_PROFILE
    ].required_campaign_ids
    required_set = set(required)
    if (
        set(readiness_rows) != required_set
        or set(program_rows) != required_set
        or not required_set.issubset(bindings)
    ):
        raise AzureLaunchPreflightError(
            "the ten-campaign source-retirement crosswalk is inconsistent"
        )

    plan = _prototype_plan(semantic)
    groups_by_campaign: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for group in plan["groups"]:
        groups_by_campaign[group["campaign_id"]].append(group)
    if set(groups_by_campaign) != required_set:
        raise AzureLaunchPreflightError(
            "portfolio topology does not contain exactly the ten source campaigns"
        )

    materializer_paths = sorted(
        {
            path
            for campaign_id in required
            for path in program_rows[campaign_id]["azure"]["materializers"]
        }
    )
    cli_checks = {
        relative: _check_cli(relative, run_help=run_cli_help)
        for relative in materializer_paths
    }
    site_paths = sorted(
        {
            path
            for campaign_id in required
            for path in program_rows[campaign_id]["azure"]["site_examples"]
        }
    )
    expected_site_paths = {
        f"examples/trusted-compute/{name}"
        for name in SITE_SCHEMA_BY_EXAMPLE
    }
    if set(site_paths) != expected_site_paths:
        raise AzureLaunchPreflightError(
            "campaign site examples differ from the reviewed schema crosswalk"
        )
    site_checks = {
        relative: _check_site_example(relative)
        for relative in site_paths
    }

    campaign_reports: list[dict[str, Any]] = []
    for campaign_id in required:
        row = readiness_rows[campaign_id]
        program_row = program_rows[campaign_id]
        groups = groups_by_campaign[campaign_id]
        expected_materializers = set(
            program_row["azure"]["materializers"]
        )
        routed_materializers = {
            group["materializer_adapter"]
            for group in groups
            if group["materializer_adapter"] is not None
        }
        route_materializers_reviewed = routed_materializers.issubset(
            expected_materializers
        )
        all_groups_routed = all(
            group["production_operator_available"]
            and group["operator_adapter"] is not None
            and group["materializer_adapter"] is not None
            for group in groups
        )
        declared_group_count = row["deployment"]["portfolio_group_count"]
        group_count_exact = declared_group_count == len(groups)

        invocation = row["semantic_output"]["registered_invocation"]
        invocation_known = False
        invocation_error: str | None = None
        invocation_backend: str | None = None
        try:
            registered_invocation_expected(invocation)
            invocation_backend = registered_invocation_backend(invocation)
            invocation_known = True
        except (OSError, ValueError, RuntimeError) as error:
            invocation_error = str(error)
        terminals = [group for group in groups if group["terminal"]]
        terminal_backend = (
            terminals[0]["receipt_backend"] if len(terminals) == 1 else None
        )
        invocation_backend_exact = (
            invocation_known
            and len(terminals) == 1
            and invocation_backend == terminal_backend
        )
        binding = bindings[campaign_id]
        realization_id = binding.get("realization_id")
        result_binding = (
            azure_portfolio.SOURCE_TG_TERMINAL_RESULTS.get(realization_id)
            if isinstance(realization_id, str)
            else None
        )
        terminal_result_contract_exact = False
        if result_binding is not None and len(terminals) == 1:
            command = terminals[0]["command_template"]
            positions = [
                index
                for index, token in enumerate(command)
                if token == result_binding.argument
            ]
            terminal_result_contract_exact = (
                len(positions) == 1
                and positions[0] + 1 < len(command)
                and command[positions[0] + 1]
                == result_binding.artifact_template
            )

        campaign_cli_paths = program_row["azure"]["materializers"]
        campaign_site_paths = program_row["azure"]["site_examples"]
        clis_discovered = all(
            cli_checks[path]["discovered"] for path in campaign_cli_paths
        )
        schemas_valid = all(
            site_checks[path]["schema_valid"] for path in campaign_site_paths
        )
        site_pin_needed = any(
            not site_checks[path]["usable_as_production_site_configuration"]
            for path in campaign_site_paths
        )
        full_range_capable = row["algorithm"]["full_range_capable"] is True
        source_ready = all(
            (
                full_range_capable,
                all_groups_routed,
                group_count_exact,
                route_materializers_reviewed,
                clis_discovered,
                schemas_valid,
                invocation_known,
                invocation_backend_exact,
            )
        )
        calibration_blocked = (
            row["benchmark"]["target_azure_sku_measured"] is not True
        )
        semantic_shape = _semantic_shape(campaign_id, binding)
        catalog = program_row.get("catalog")
        if not isinstance(catalog, dict):
            raise AzureLaunchPreflightError(
                f"{campaign_id} has no external-program catalog status"
            )
        semantic_admission_blocked = not (
            binding.get("enabled") is True
            and catalog.get("production_artifact_installed") is True
            and catalog.get("reviewed_receipt_installed") is True
        )
        algorithm_incomplete = _algorithm_incomplete(row)
        cloud_launch_ready = (
            source_ready
            and not site_pin_needed
            and not calibration_blocked
            and not algorithm_incomplete
        )
        theorem_admission_complete = not semantic_admission_blocked
        classes = []
        if source_ready:
            classes.append("source-ready")
        if site_pin_needed:
            classes.append("site-pin-needed")
        if calibration_blocked:
            classes.append("calibration-blocked")
        if semantic_admission_blocked:
            classes.append("semantic-admission-blocked")
        if algorithm_incomplete:
            classes.append("algorithm-incomplete")
        campaign_reports.append(
            {
                "algorithm": {
                    "full_range_capable": full_range_capable,
                    "optimized_route_status": row["algorithm"][
                        "optimized_route_status"
                    ],
                },
                "algorithm_incomplete": algorithm_incomplete,
                "calibration_blocked": calibration_blocked,
                "campaign_id": campaign_id,
                "cli_checks": [
                    cli_checks[path] for path in campaign_cli_paths
                ],
                "group_count": len(groups),
                "group_count_exact": group_count_exact,
                "invocation": {
                    "backend": invocation_backend,
                    "backend_matches_terminal": invocation_backend_exact,
                    "error": invocation_error,
                    "known": invocation_known,
                    "name": invocation,
                    "terminal_result_contract_exact": (
                        terminal_result_contract_exact
                    ),
                    "terminal_result_contract_reviewed": (
                        result_binding is not None
                    ),
                },
                "portfolio_groups": [
                    {
                        "backend_class": group["backend_class"],
                        "command_template": group["command_template"],
                        "group_id": group["group_id"],
                        "materializer_adapter": group[
                            "materializer_adapter"
                        ],
                        "operator_adapter": group["operator_adapter"],
                        "receipt_backend": group["receipt_backend"],
                        "shard_count": group["shard_count"],
                        "terminal": group["terminal"],
                    }
                    for group in groups
                ],
                "cloud_launch_ready": cloud_launch_ready,
                "readiness_classes": classes,
                "route_materializers_reviewed": route_materializers_reviewed,
                "semantic_admission_blocked": semantic_admission_blocked,
                "semantic_shape": semantic_shape,
                "site_checks": [
                    site_checks[path] for path in campaign_site_paths
                ],
                "site_pin_needed": site_pin_needed,
                "source_materialization_ready": source_ready,
                "theorem_admission_complete": theorem_admission_complete,
            }
        )

    def count(field: str) -> int:
        return sum(row[field] is True for row in campaign_reports)

    return {
        "accepted": False,
        "campaigns": campaign_reports,
        "category_definitions": {
            "algorithm-incomplete": (
                "a literal full-range source route exists, but the optimized "
                "end-to-end route needed for a practical production campaign "
                "is explicitly incomplete"
            ),
            "calibration-blocked": (
                "no retained measurement from the exact target Azure SKU is "
                "installed; the hard budget gate therefore remains closed"
            ),
            "semantic-admission-blocked": (
                "post-run theorem admission is incomplete: no reviewed "
                "production deployment artifact plus signed receipt is "
                "source-admitted as theorem authority; this is deliberately "
                "not a prerequisite for starting the cloud computation"
            ),
            "site-pin-needed": (
                "the schema-valid checked-in site file contains redacted or "
                "placeholder deployment identities and must not be launched"
            ),
            "source-ready": (
                "the literal full-range route, exact argv topology, registered "
                "invocation, materializer CLI, and redacted template schema are "
                "mechanically present; this is not production or theorem readiness"
            ),
        },
        "classification": (
            "bounded_read_only_source_preflight_not_execution_evidence_"
            "or_production_authority"
        ),
        "kind": KIND,
        "nonclaims": [
            "No Azure resource was inspected, created, started, or changed.",
            "No source-scale arithmetic was executed.",
            "Schema-valid redacted examples are not production site pins.",
            "A known registered invocation is not a reviewed receipt.",
            "No campaign in this report supplies Lean theorem authority.",
        ],
        "schema_version": SCHEMA_VERSION,
        "summary": {
            "algorithm_incomplete_campaigns": count("algorithm_incomplete"),
            "calibration_blocked_campaigns": count("calibration_blocked"),
            "materializer_cli_count": len(cli_checks),
            "physical_campaigns": len(campaign_reports),
            "portfolio_group_count": sum(
                row["group_count"] for row in campaign_reports
            ),
            "cloud_launch_ready_campaigns": count("cloud_launch_ready"),
            "registered_invocation_count": sum(
                row["invocation"]["known"] is True
                for row in campaign_reports
            ),
            "reviewed_terminal_result_contracts": sum(
                row["invocation"]["terminal_result_contract_reviewed"] is True
                for row in campaign_reports
            ),
            "semantic_admission_blocked_campaigns": count(
                "semantic_admission_blocked"
            ),
            "site_example_count": len(site_checks),
            "site_pin_needed_campaigns": count("site_pin_needed"),
            "source_materialization_ready_campaigns": count(
                "source_materialization_ready"
            ),
            "theorem_admission_complete_campaigns": count(
                "theorem_admission_complete"
            ),
        },
    }


__all__ = [
    "AzureLaunchPreflightError",
    "KIND",
    "SCHEMA_VERSION",
    "SITE_SCHEMA_BY_EXAMPLE",
    "build_preflight_report",
]
