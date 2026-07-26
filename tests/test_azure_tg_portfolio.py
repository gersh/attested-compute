# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

try:
    import jsonschema
except ImportError:  # The repository has no mandatory third-party dependency.
    jsonschema = None

from tg_verifier import azure_portfolio as portfolio
from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier.h100_cluster import (
    WORKLOADS,
    build_manifest,
    inspect_clean_repository,
)


ROOT = Path(__file__).resolve().parents[1]
SPEC_SCHEMA = ROOT / "schemas/azure-tg-portfolio.schema.json"
PLAN_SCHEMA = ROOT / "schemas/azure-tg-portfolio-plan.schema.json"
SEMANTIC_SCHEMA = ROOT / "schemas/azure-tg-semantic-bindings.schema.json"
PRODUCTION_SEMANTICS = (
    ROOT / "specifications/TERNARY_GOLDBACH_AZURE_SEMANTIC_BINDINGS.json"
)
REDACTED_SPEC = (
    ROOT / "examples/trusted-compute/azure_tg_portfolio.redacted.json"
)


def direct_cluster_paths() -> list[str]:
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
            token[len(prefix) :]
            for token in (*workload.command, *workload.postcheck, *phase_tokens)
            if token.startswith(prefix)
        )
    return sorted(paths)


def pin(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def ready_budget_gate(
    price_class: str = "pay_as_you_go",
    campaign_ids: tuple[str, ...] = portfolio.CAPABILITY_CAMPAIGN_IDS,
) -> dict[str, object]:
    return {
        "blocking_campaign_ids": [],
        "covered_campaign_ids": list(campaign_ids),
        "hard_max_cost_usd": "10000",
        "hard_max_wall_hours": "168",
        "high_endpoints_control": True,
        "portfolio_high_cost_usd": "9999.00",
        "portfolio_high_wall_hours": "167",
        "price_class": price_class,
        "production_ready": True,
        "report_schema": "sparkinterval.tg.azure-production-sizing.v2",
        "snapshot_date": "2026-07-22",
    }


class PortfolioFixture:
    def __init__(
        self,
        root: Path,
        *,
        complete_semantics: bool,
        completion_profile: str = portfolio.CAPABILITY_INVENTORY_PROFILE,
        production_semantics: bool = False,
    ):
        self.root = root
        self.repository = root / "repository"
        self.run_root = root / "run"
        self.repository.mkdir()
        for relative in direct_cluster_paths():
            path = self.repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"")

        # Derive terminal routes from the reviewed topology before binding this
        # fixture's eventual clean repository closure.
        fake_files = [
            {"path": path, "sha256": "0" * 64, "size_bytes": 0}
            for path in direct_cluster_paths()
        ]
        fake_binding = {
            "clean_worktree": True,
            "coverage": "all_git_tracked_regular_files",
            "file_count": len(fake_files),
            "files": fake_files,
            "git_commit_oid": "a" * 40,
            "git_object_format": "sha1",
            "git_tree_oid": "b" * 40,
            "kind": "sparkinterval.tg.clean_git_repository_closure.v1",
            "untracked_files_absent": True,
        }
        prototype_cluster = build_manifest(fake_binding)
        empty_semantics = {
            "bindings": [],
            "kind": portfolio.SEMANTIC_REGISTRY_KIND,
            "schema_version": 1,
        }
        prototype_spec = {
            "challenge_ttl_seconds": 3600,
            "cluster_manifest": {"sha256": "1" * 64},
            "completion_profile": portfolio.CAPABILITY_INVENTORY_PROFILE,
            "portfolio_id": "fixture-portfolio",
            "production_price_class": "pay_as_you_go",
            "run_root": str(self.run_root),
            "semantic_bindings": {"sha256": "2" * 64},
            "verifier_key_manifest": {"sha256": "3" * 64},
        }
        prototype_plan = portfolio.build_plan(
            prototype_spec,
            prototype_cluster,
            empty_semantics,
            production_budget_gate=ready_budget_gate(),
        )
        terminals = {
            group["campaign_id"]: group
            for group in prototype_plan["groups"]
            if group["terminal"]
        }
        bindings = []
        self.realizations: dict[str, dict[str, str]] = {}
        self.terminal_results: dict[str, portfolio.TerminalResultBinding] = {}
        for campaign_id in sorted(terminals):
            group = terminals[campaign_id]
            if complete_semantics:
                invocation = (
                    "h100FormalPtxConstantOneV1"
                    if group["receipt_backend"] == "azure_ncc40ads_h100_v5"
                    else "cubicSumDivThree20000V1"
                )
                realization_id = "fixture.realization." + hashlib.sha256(
                    campaign_id.encode("utf-8")
                ).hexdigest()[:20]
                lean_theorem = "Fixture.Realization.r" + hashlib.sha256(
                    ("theorem:" + campaign_id).encode("utf-8")
                ).hexdigest()[:20]
                self.realizations[realization_id] = {
                    "campaign_id": campaign_id,
                    "lean_theorem": lean_theorem,
                    "registered_invocation": invocation,
                }
                command = group["command_template"]
                position = next(
                    index
                    for index in range(len(command) - 1)
                    if command.count(command[index]) == 1
                )
                self.terminal_results[realization_id] = (
                    portfolio.TerminalResultBinding(
                        argument=command[position],
                        artifact_template=command[position + 1],
                    )
                )
            else:
                invocation = None
                realization_id = None
                lean_theorem = None
            bindings.append(
                {
                    "campaign_id": campaign_id,
                    "enabled": complete_semantics,
                    "lean_theorem": lean_theorem,
                    "realization_id": realization_id,
                    "registered_invocation": invocation,
                }
            )
        self.semantic = (
            json.loads(PRODUCTION_SEMANTICS.read_text(encoding="utf-8"))
            if production_semantics
            else {
                "bindings": bindings,
                "kind": portfolio.SEMANTIC_REGISTRY_KIND,
                "schema_version": 1,
            }
        )
        semantic_path = (
            self.repository
            / "specifications/TERNARY_GOLDBACH_AZURE_SEMANTIC_BINDINGS.json"
        )
        semantic_path.parent.mkdir(parents=True, exist_ok=True)
        semantic_path.write_bytes(canonical_json_bytes(self.semantic))
        key_path = self.repository / "profiles/verifier_keys/trusted_compute_keys.json"
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(canonical_json_bytes({"keys": [], "schema_version": 1}))

        subprocess.run(["git", "init", "-q", str(self.repository)], check=True)
        subprocess.run(["git", "-C", str(self.repository), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repository),
                "-c",
                "user.name=Portfolio Test",
                "-c",
                "user.email=portfolio@example.invalid",
                "commit",
                "-q",
                "-m",
                "fixture",
            ],
            check=True,
        )
        repository_binding = inspect_clean_repository(self.repository)
        self.cluster = build_manifest(repository_binding)
        self.cluster_path = root / "cluster-manifest.json"
        self.cluster_path.write_bytes(canonical_json_bytes(self.cluster))
        rows = {row["path"]: row for row in repository_binding["files"]}
        self.spec = {
            "challenge_ttl_seconds": 3600,
            "cluster_manifest": pin(self.cluster_path),
            "completion_profile": completion_profile,
            "kind": portfolio.SPEC_KIND,
            "portfolio_id": "fixture-portfolio",
            "production_price_class": "pay_as_you_go",
            "repository_root": str(self.repository),
            "run_root": str(self.run_root),
            "schema_version": 1,
            "semantic_bindings": rows[
                "specifications/TERNARY_GOLDBACH_AZURE_SEMANTIC_BINDINGS.json"
            ],
            "verifier_key_manifest": rows[
                "profiles/verifier_keys/trusted_compute_keys.json"
            ],
        }
        self.spec_path = root / "portfolio-spec.json"
        self.spec_path.write_bytes(canonical_json_bytes(self.spec))

    def load_ready_context(self) -> portfolio.PortfolioContext:
        routes = {
            key: portfolio.BackendRoute(
                receipt_backend=value.receipt_backend,
                operator_adapter=(
                    value.operator_adapter or "fixture/cpu-production-operator.py"
                ),
                production_operator_available=True,
                reason=None,
            )
            for key, value in portfolio.BACKEND_ROUTES.items()
        }
        with mock.patch.dict(portfolio.BACKEND_ROUTES, routes, clear=True), mock.patch.dict(
            portfolio.SOURCE_TG_REALIZATIONS, self.realizations, clear=True
        ), mock.patch.dict(
            portfolio.SOURCE_TG_TERMINAL_RESULTS,
            self.terminal_results,
            clear=True,
        ), mock.patch.object(
            portfolio,
            "_current_production_budget_gate",
            return_value=ready_budget_gate(),
        ):
            return portfolio.load_portfolio_spec(self.spec_path)

    def load_production_semantics_context(
        self, budget_gate: dict[str, object]
    ) -> portfolio.PortfolioContext:
        with mock.patch.object(
            portfolio,
            "_current_production_budget_gate",
            return_value=budget_gate,
        ):
            return portfolio.load_portfolio_spec(self.spec_path)


class AzureTGPortfolioTests(unittest.TestCase):
    def test_production_inventory_routes_cdem_psi_and_platt_head(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PortfolioFixture(Path(temporary), complete_semantics=False)
            semantics = portfolio._validate_semantic_bindings(
                json.loads(PRODUCTION_SEMANTICS.read_text(encoding="utf-8"))
            )
            plan = portfolio.build_plan(
                fixture.spec,
                fixture.cluster,
                semantics,
                production_budget_gate=ready_budget_gate(),
            )
            groups = {group["group_id"]: group for group in plan["groups"]}
            self.assertEqual(
                groups["cdem-table-abel::single-job"]["semantic_binding"],
                {
                    "lean_theorem": (
                        "SparkInterval.Execution.SignedResultCertificate."
                        "certifyCDEMTableAbel"
                    ),
                    "registered_result_artifact_template": (
                        "${TG_RUN_ROOT}/cdem-table-abel/registered-result.txt"
                    ),
                    "realization_scope": (
                        "claude_math_live_ReproducibleTableAbelVerifierOutput_"
                        "via_definition_checked_bridge"
                    ),
                    "realization_id": "cdemTableAbelReceiptSourceClaimV2",
                    "registered_invocation": "cdemTableAbelProductionV2",
                },
            )
            self.assertTrue(
                groups["cdem-table-abel::single-job"][
                    "production_operator_available"
                ]
            )
            self.assertEqual(
                groups["cdem-table-abel::single-job"]["materializer_adapter"],
                "tools/tg_azure_cpu_portfolio_materializer.py",
            )
            hurst_groups = [
                group for group in groups.values()
                if group["campaign_id"] == "hurst-four-residuals-v1"
            ]
            self.assertEqual(len(hurst_groups), 6)
            self.assertTrue(
                all(group["production_operator_available"] for group in hurst_groups)
            )
            self.assertEqual(
                {group["materializer_adapter"] for group in hurst_groups},
                {"tools/tg_azure_cpu_hurst_materializer.py"},
            )
            cdem_semantic_gaps = [
                gap for gap in plan["gaps"]
                if gap["campaign_id"] == "cdem-table-abel"
                and "semantic" in gap["code"]
            ]
            self.assertEqual(cdem_semantic_gaps, [])
            self.assertNotIn(
                "production_backend_operator_absent",
                {
                    gap["code"]
                    for gap in plan["gaps"]
                    if gap["campaign_id"] == "cdem-table-abel"
                },
            )
            hurst = next(
                row for row in semantics["bindings"]
                if row["campaign_id"] == "hurst-four-residuals-v1"
            )
            self.assertFalse(hurst["enabled"])
            self.assertEqual(
                hurst["registered_invocation"],
                "hurstSharedFourResidualProductionV2",
            )
            self.assertEqual(
                portfolio.PENDING_TG_REALIZATIONS[
                    "hurstSharedFourResidualRealClaimsV2"
                ],
                {
                    "campaign_id": "hurst-four-residuals-v1",
                    "lean_theorem": (
                        "SparkInterval.Execution.RegisteredInvocation."
                        "hurstSharedFourResidualProductionV2_realClaims"
                    ),
                    "registered_invocation": (
                        "hurstSharedFourResidualProductionV2"
                    ),
                },
            )
            self.assertEqual(
                portfolio.SOURCE_TG_TERMINAL_RESULTS[
                    "ch25PsiLemma92SourceClaimV1"
                ],
                portfolio.TerminalResultBinding(
                    argument="--registered-result-output",
                    artifact_template=(
                        "${TG_RUN_ROOT}/ch25-psi-1e13/registered-result.txt"
                    ),
                ),
            )
            self.assertEqual(
                portfolio.SOURCE_TG_TERMINAL_RESULTS[
                    "hurstSharedFourResidualRealClaimsV2"
                ],
                portfolio.TerminalResultBinding(
                    argument="--registered-result-output",
                    artifact_template=(
                        "${TG_RUN_ROOT}/mertens-hurst/registered-result.txt"
                    ),
                ),
            )
            self.assertNotIn(
                "production_backend_operator_absent",
                {
                    gap["code"] for gap in plan["gaps"]
                    if gap["campaign_id"] == "hurst-four-residuals-v1"
                },
            )
            self.assertEqual(
                [
                    gap["code"] for gap in plan["gaps"]
                    if gap["campaign_id"] == "hurst-four-residuals-v1"
                    and "semantic" in gap["code"]
                ],
                ["semantic_binding_disabled"],
            )
            psi = next(
                row for row in semantics["bindings"]
                if row["campaign_id"] == "ch25-psi-two-pass-v1"
            )
            self.assertFalse(psi["enabled"])
            self.assertEqual(
                psi["registered_invocation"],
                "ch25PsiLemma92ProductionV1",
            )
            self.assertEqual(
                portfolio.PENDING_TG_REALIZATIONS[
                    "ch25PsiLemma92SourceClaimV1"
                ],
                {
                    "campaign_id": "ch25-psi-two-pass-v1",
                    "lean_theorem": (
                        "SparkInterval.Execution.RegisteredInvocation."
                        "ch25PsiLemma92ProductionV1_sourceClaim"
                    ),
                    "registered_invocation": "ch25PsiLemma92ProductionV1",
                },
            )
            self.assertEqual(
                [
                    gap["code"] for gap in plan["gaps"]
                    if gap["campaign_id"] == "ch25-psi-two-pass-v1"
                    and "semantic" in gap["code"]
                ],
                ["semantic_binding_disabled"],
            )
            psi_groups = [
                group for group in groups.values()
                if group["campaign_id"] == "ch25-psi-two-pass-v1"
            ]
            self.assertEqual(len(psi_groups), 6)
            self.assertTrue(
                all(group["production_operator_available"] for group in psi_groups)
            )
            self.assertEqual(
                {group["materializer_adapter"] for group in psi_groups},
                {"tools/tg_azure_cpu_psi_materializer.py"},
            )
            self.assertNotIn(
                "production_backend_operator_absent",
                {
                    gap["code"] for gap in plan["gaps"]
                    if gap["campaign_id"] == "ch25-psi-two-pass-v1"
                },
            )
            head = groups["platt-head-2e4::single-job"]
            self.assertIsNone(head["semantic_binding"])
            self.assertTrue(head["production_operator_available"])
            self.assertEqual(
                head["materializer_adapter"],
                "tools/tg_azure_cpu_platt_head_materializer.py",
            )
            self.assertNotIn(
                "production_backend_operator_absent",
                {
                    gap["code"] for gap in plan["gaps"]
                    if gap["campaign_id"] == "platt-head-2e4"
                },
            )
            pt21_groups = [
                group
                for group in groups.values()
                if group["campaign_id"] == "platt-trudgian-rh-3e12"
            ]
            self.assertEqual(
                [
                    (group["phase_id"], group["shard_count"])
                    for group in pt21_groups
                ],
                [
                    ("initialize", 1),
                    ("exact-multiplicity-count", 1),
                    ("ordinary-low-index-prefix", 1),
                    ("platt-turing-index-shards", 1_236_316),
                    ("finalize-merkle-certificate", 1),
                ],
            )
            self.assertTrue(
                all(
                    group["production_operator_available"]
                    for group in pt21_groups
                )
            )
            self.assertEqual(
                {group["materializer_adapter"] for group in pt21_groups},
                {"tools/tg_azure_cpu_platt_pt21_materializer.py"},
            )
            self.assertNotIn(
                "production_backend_operator_absent",
                {
                    gap["code"]
                    for gap in plan["gaps"]
                    if gap["campaign_id"] == "platt-trudgian-rh-3e12"
                },
            )
            a7 = groups["ch25-a7-boundary::single-job"]
            self.assertIsNone(a7["semantic_binding"])
            a7_row = next(
                row for row in semantics["bindings"]
                if row["campaign_id"] == "ch25-a7-boundary"
            )
            self.assertEqual(
                a7_row,
                {
                    "campaign_id": "ch25-a7-boundary",
                    "enabled": False,
                    "lean_theorem": (
                        "SparkInterval.Execution.RegisteredInvocation."
                        "ch25A7BoundaryProductionV1_sourceClaim"
                    ),
                    "realization_id": "ch25A7BoundarySourceClaimV1",
                    "registered_invocation": "ch25A7BoundaryProductionV1",
                },
            )
            self.assertEqual(
                portfolio.PENDING_TG_REALIZATIONS[
                    "ch25A7BoundarySourceClaimV1"
                ],
                {
                    "campaign_id": "ch25-a7-boundary",
                    "lean_theorem": (
                        "SparkInterval.Execution.RegisteredInvocation."
                        "ch25A7BoundaryProductionV1_sourceClaim"
                    ),
                    "registered_invocation": "ch25A7BoundaryProductionV1",
                },
            )
            self.assertEqual(
                portfolio.SOURCE_TG_TERMINAL_RESULTS[
                    "ch25A7BoundarySourceClaimV1"
                ],
                portfolio.TerminalResultBinding(
                    argument="--registered-result-output",
                    artifact_template=(
                        "${TG_RUN_ROOT}/ch25-a7-boundary/"
                        "registered-result.txt"
                    ),
                ),
            )
            self.assertTrue(a7["production_operator_available"])
            self.assertEqual(
                a7["materializer_adapter"],
                "tools/tg_azure_cpu_a7_materializer.py",
            )
            self.assertNotIn(
                "production_backend_operator_absent",
                {
                    gap["code"] for gap in plan["gaps"]
                    if gap["campaign_id"] == "ch25-a7-boundary"
                },
            )
            self.assertEqual(
                [
                    gap["code"] for gap in plan["gaps"]
                    if gap["campaign_id"] == "ch25-a7-boundary"
                    and "semantic" in gap["code"]
                ],
                ["semantic_binding_disabled"],
            )
            dirichlet_source = groups[
                "platt-dirichlet-theorem-7-1::single-job"
            ]
            self.assertTrue(dirichlet_source["production_operator_available"])
            self.assertEqual(
                dirichlet_source["materializer_adapter"],
                "tools/tg_azure_cpu_dirichlet_materializer.py",
            )
            dirichlet_postcheck = groups[
                "platt-dirichlet-theorem-7-1::postcheck"
            ]
            self.assertTrue(
                dirichlet_postcheck["production_operator_available"]
            )
            self.assertEqual(
                dirichlet_postcheck["materializer_adapter"],
                "tools/tg_azure_cpu_dirichlet_materializer.py",
            )
            self.assertIsNone(
                dirichlet_postcheck["production_route_reason"]
            )
            lowered_campaign = "ternary-goldbach-finite-below-10pow27-v1"
            lowered = next(
                row for row in semantics["bindings"]
                if row["campaign_id"] == lowered_campaign
            )
            self.assertEqual(
                lowered,
                {
                    "campaign_id": lowered_campaign,
                    "enabled": False,
                    "lean_theorem": (
                        "SparkInterval.Execution.RegisteredInvocation."
                        "goldbach10Pow27ProductionV1_sourceClaim"
                    ),
                    "realization_id": "goldbach10Pow27SourceClaimV1",
                    "registered_invocation": "goldbach10Pow27ProductionV1",
                },
            )
            self.assertEqual(
                portfolio.PENDING_TG_REALIZATIONS[
                    "goldbach10Pow27SourceClaimV1"
                ],
                {
                    "campaign_id": lowered_campaign,
                    "lean_theorem": (
                        "SparkInterval.Execution.RegisteredInvocation."
                        "goldbach10Pow27ProductionV1_sourceClaim"
                    ),
                    "registered_invocation": "goldbach10Pow27ProductionV1",
                },
            )
            self.assertEqual(
                portfolio.SOURCE_TG_TERMINAL_RESULTS[
                    "goldbach10Pow27SourceClaimV1"
                ],
                portfolio.TerminalResultBinding(
                    argument="--registered-result-output",
                    artifact_template=(
                        "${TG_RUN_ROOT}/goldbach-finite-below-10pow27/"
                        "registered-result.txt"
                    ),
                ),
            )
            lowered_groups = [
                group for group in groups.values()
                if group["campaign_id"] == lowered_campaign
            ]
            self.assertEqual(len(lowered_groups), 8)
            lowered_terminal = next(
                group for group in lowered_groups if group["terminal"]
            )
            self.assertEqual(
                lowered_terminal["phase_id"],
                "measured-finalize-lowered-source-claim",
            )
            self.assertIsNone(lowered_terminal["semantic_binding"])
            self.assertTrue(
                lowered_terminal["production_operator_available"]
            )
            self.assertIsNone(lowered_terminal["production_route_reason"])
            self.assertEqual(
                lowered_terminal["materializer_adapter"],
                "tools/tg_azure_cpu_goldbach_10pow27_materializer.py",
            )
            lowered_cpu = [
                group for group in lowered_groups
                if group["backend_class"] == "cpu_exact_sidecar"
            ]
            self.assertEqual(len(lowered_cpu), 7)
            self.assertTrue(
                all(group["production_operator_available"] for group in lowered_cpu)
            )
            self.assertNotIn(
                "production_backend_operator_absent",
                {
                    gap["code"] for gap in plan["gaps"]
                    if gap["campaign_id"] == lowered_campaign
                },
            )
            self.assertEqual(
                [
                    gap["code"] for gap in plan["gaps"]
                    if gap["campaign_id"] == lowered_campaign
                    and "semantic" in gap["code"]
                ],
                ["semantic_binding_disabled"],
            )
            self.assertEqual(
                lowered_terminal["terminal_receipt_contract"],
                {
                    "classification": (
                        "registered_invocation_and_result_contract_not_"
                        "theorem_authority"
                    ),
                    "registered_invocation": "goldbach10Pow27ProductionV1",
                    "registered_result_argument": "--registered-result-output",
                    "registered_result_artifact_template": (
                        "${TG_RUN_ROOT}/goldbach-finite-below-10pow27/"
                        "registered-result.txt"
                    ),
                    "semantic_admission_enabled": False,
                },
            )

    def test_cdem_semantics_require_the_exact_registered_result_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PortfolioFixture(Path(temporary), complete_semantics=False)
            changed = json.loads(json.dumps(fixture.cluster))
            job = next(
                row for row in changed["jobs"]
                if row["atom_id"] == "cdem-table-abel"
            )
            position = job["command"].index("--registered-result-output")
            del job["command"][position : position + 2]
            semantics = portfolio._validate_semantic_bindings(
                json.loads(PRODUCTION_SEMANTICS.read_text(encoding="utf-8"))
            )
            plan = portfolio.build_plan(
                fixture.spec,
                changed,
                semantics,
                production_budget_gate=ready_budget_gate(),
            )
            cdem_codes = [
                gap["code"] for gap in plan["gaps"]
                if gap["campaign_id"] == "cdem-table-abel"
            ]
            self.assertIn(
                "terminal_registered_result_command_mismatch", cdem_codes
            )
            cdem_terminal = next(
                group for group in plan["groups"]
                if group["group_id"] == "cdem-table-abel::single-job"
            )
            self.assertIsNone(cdem_terminal["semantic_binding"])

    def test_lowered_goldbach_staging_binds_only_the_exact_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PortfolioFixture(Path(temporary), complete_semantics=False)
            campaign_id = "ternary-goldbach-finite-below-10pow27-v1"
            realization_id = "goldbach10Pow27SourceClaimV1"
            semantics = json.loads(PRODUCTION_SEMANTICS.read_text(encoding="utf-8"))
            row = next(
                item for item in semantics["bindings"]
                if item["campaign_id"] == campaign_id
            )
            self.assertFalse(row["enabled"])
            row["enabled"] = True
            catalog = dict(portfolio.SOURCE_TG_REALIZATIONS)
            catalog[realization_id] = dict(
                portfolio.PENDING_TG_REALIZATIONS[realization_id]
            )
            plan = portfolio.build_plan(
                fixture.spec,
                fixture.cluster,
                portfolio._validate_semantic_bindings(semantics),
                realization_catalog=catalog,
                production_budget_gate=ready_budget_gate(),
            )
            terminal = next(
                group for group in plan["groups"]
                if group["campaign_id"] == campaign_id and group["terminal"]
            )
            self.assertEqual(
                terminal["semantic_binding"],
                {
                    "lean_theorem": (
                        "SparkInterval.Execution.RegisteredInvocation."
                        "goldbach10Pow27ProductionV1_sourceClaim"
                    ),
                    "registered_result_artifact_template": (
                        "${TG_RUN_ROOT}/goldbach-finite-below-10pow27/"
                        "registered-result.txt"
                    ),
                    "realization_scope": (
                        "claude_math_live_FiniteOdd10Pow27Input_via_"
                        "definition_checked_bridge"
                    ),
                    "realization_id": realization_id,
                    "registered_invocation": "goldbach10Pow27ProductionV1",
                },
            )

            changed = json.loads(json.dumps(fixture.cluster))
            campaign = next(
                item for item in changed["physical_campaigns"]
                if item["campaign_id"] == campaign_id
            )
            command = campaign["phase_dag"][-1]["command"]
            result_position = command.index("--registered-result-output") + 1
            command[result_position] = "${TG_RUN_ROOT}/attacker-result.txt"
            rejected = portfolio.build_plan(
                fixture.spec,
                changed,
                portfolio._validate_semantic_bindings(semantics),
                realization_catalog=catalog,
                production_budget_gate=ready_budget_gate(),
            )
            codes = {
                gap["code"] for gap in rejected["gaps"]
                if gap["campaign_id"] == campaign_id
            }
            self.assertIn("terminal_registered_result_command_mismatch", codes)
            rejected_terminal = next(
                group for group in rejected["groups"]
                if group["campaign_id"] == campaign_id and group["terminal"]
            )
            self.assertIsNone(rejected_terminal["semantic_binding"])

    def test_plan_expands_phase_arrays_and_cross_campaign_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PortfolioFixture(Path(temporary), complete_semantics=True)
            context = fixture.load_ready_context()
            plan = context.plan
            self.assertTrue(plan["ready_for_local_preparation"])
            self.assertEqual(plan["gaps"], [])
            self.assertEqual(len(plan["groups"]), 41)
            groups = {group["group_id"]: group for group in plan["groups"]}
            self.assertEqual(
                groups[
                    "platt-trudgian-rh-3e12::platt-turing-index-shards"
                ]["shard_count"],
                1_236_316,
            )
            self.assertEqual(
                groups[
                    "helfgott-platt-goldbach-gpu-v1::h100-8192-groups-of-eight-checkpoint-leaves"
                ]["receipt_backend"],
                "azure_ncc40ads_h100_v5",
            )
            self.assertEqual(
                groups[
                    "helfgott-platt-goldbach-gpu-v1::native-prime-ladder-range-groups"
                ]["receipt_backend"],
                "azure_sevsnp_cpu",
            )
            self.assertEqual(
                groups[
                    "ternary-goldbach-finite-below-10pow27-v1::"
                    "h100-8192-groups-of-eight-lowered-checkpoint-leaves"
                ]["receipt_backend"],
                "azure_ncc40ads_h100_v5",
            )
            self.assertEqual(
                groups[
                    "ternary-goldbach-finite-below-10pow27-v1::"
                    "h100-8192-groups-of-eight-lowered-checkpoint-leaves"
                ]["materializer_adapter"],
                "tools/tg_azure_h100_goldbach_10pow27_materializer.py",
            )
            self.assertEqual(
                groups[
                    "ramare-zuniga-lemma-6-2::single-job"
                ]["materializer_adapter"],
                "tools/tg_azure_h100_r2star_materializer.py",
            )
            changed_r2star = dict(
                groups["ramare-zuniga-lemma-6-2::single-job"]
            )
            changed_r2star["command_template"] = [
                *changed_r2star["command_template"],
                "--unsafe-resume",
            ]
            portfolio._bind_group_operator_capability(changed_r2star)
            self.assertFalse(changed_r2star["production_operator_available"])
            self.assertIsNone(changed_r2star["materializer_adapter"])

            changed_lowered = dict(
                groups[
                    "ternary-goldbach-finite-below-10pow27-v1::"
                    "h100-8192-groups-of-eight-lowered-checkpoint-leaves"
                ]
            )
            changed_lowered["shard_count"] += 1
            portfolio._bind_group_operator_capability(changed_lowered)
            self.assertFalse(changed_lowered["production_operator_available"])
            self.assertIsNone(changed_lowered["materializer_adapter"])
            self.assertEqual(
                groups[
                    "ternary-goldbach-finite-below-10pow27-v1::"
                    "measured-finalize-lowered-source-claim"
                ]["receipt_backend"],
                "azure_sevsnp_cpu",
            )
            self.assertIn(
                "platt-trudgian-rh-3e12::finalize-merkle-certificate",
                groups["platt-dirichlet-theorem-7-1::single-job"]["depends_on"],
            )
            self.assertEqual(plan, fixture.load_ready_context().plan)

    def test_lowered_completion_profile_selects_exact_minimal_theorem_route(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PortfolioFixture(Path(temporary), complete_semantics=True)
            spec = dict(fixture.spec)
            spec["completion_profile"] = (
                portfolio.LOWERED_10POW27_COMPLETION_PROFILE
            )
            semantics = json.loads(json.dumps(fixture.semantic))
            historical = next(
                row for row in semantics["bindings"]
                if row["campaign_id"] == portfolio.HISTORICAL_GOLDBACH_CAMPAIGN
            )
            historical["enabled"] = False
            routes = {
                key: portfolio.BackendRoute(
                    receipt_backend=value.receipt_backend,
                    operator_adapter=value.operator_adapter or "fixture/cpu.py",
                    production_operator_available=True,
                    reason=None,
                )
                for key, value in portfolio.BACKEND_ROUTES.items()
            }
            required = portfolio.COMPLETION_PROFILES[
                portfolio.LOWERED_10POW27_COMPLETION_PROFILE
            ].required_campaign_ids
            with mock.patch.dict(
                portfolio.BACKEND_ROUTES, routes, clear=True
            ):
                plan = portfolio.build_plan(
                    spec,
                    fixture.cluster,
                    portfolio._validate_semantic_bindings(semantics),
                    realization_catalog=fixture.realizations,
                    terminal_result_catalog=fixture.terminal_results,
                    production_budget_gate=ready_budget_gate(
                        campaign_ids=required
                    ),
                )
            campaign_ids = {
                group["campaign_id"] for group in plan["groups"]
            }
            self.assertEqual(campaign_ids, set(required))
            self.assertNotIn(
                portfolio.HISTORICAL_GOLDBACH_CAMPAIGN, campaign_ids
            )
            self.assertIn(portfolio.GOLDBACH_10POW27_CAMPAIGN, campaign_ids)
            self.assertEqual(plan["gaps"], [])
            self.assertTrue(plan["ready_for_local_preparation"])
            self.assertEqual(len(plan["groups"]), 33)
            self.assertEqual(
                plan["completion_profile"]["profile_id"],
                portfolio.LOWERED_10POW27_COMPLETION_PROFILE,
            )
            self.assertEqual(
                len(plan["completion_profile"]["required_logical_claim_ids"]),
                13,
            )
            self.assertNotIn(
                "helfgott-platt-theorem-4-1",
                plan["completion_profile"]["required_logical_claim_ids"],
            )
            self.assertIn(
                "goldbach-finite-below-10pow27",
                plan["completion_profile"]["required_logical_claim_ids"],
            )
            self.assertEqual(
                plan["completion_profile"]["excluded_campaigns"],
                [
                    {
                        "campaign_id": portfolio.HISTORICAL_GOLDBACH_CAMPAIGN,
                        "reason": (
                            "replaced only by the source-distinct lowered 10^27 "
                            "theorem route"
                        ),
                    }
                ],
            )
            self.assertIn(
                "platt-trudgian-rh-3e12::finalize-merkle-certificate",
                next(
                    group for group in plan["groups"]
                    if group["campaign_id"]
                    == "platt-dirichlet-theorem-7-1"
                )["depends_on"],
            )

    def test_lowered_profile_fails_closed_on_active_excluded_binding_or_omitted_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PortfolioFixture(Path(temporary), complete_semantics=True)
            spec = dict(fixture.spec)
            spec["completion_profile"] = (
                portfolio.LOWERED_10POW27_COMPLETION_PROFILE
            )
            required = portfolio.COMPLETION_PROFILES[
                portfolio.LOWERED_10POW27_COMPLETION_PROFILE
            ].required_campaign_ids
            plan = portfolio.build_plan(
                spec,
                fixture.cluster,
                fixture.semantic,
                realization_catalog=fixture.realizations,
                terminal_result_catalog=fixture.terminal_results,
                production_budget_gate=ready_budget_gate(campaign_ids=required),
            )
            self.assertIn(
                "profile_excluded_semantic_binding_enabled",
                {gap["code"] for gap in plan["gaps"]},
            )

            changed = json.loads(json.dumps(fixture.cluster))
            changed["dependency_edges"].append(
                {
                    "artifact": "reviewed-test-artifact",
                    "from": "helfgott-platt-theorem-4-1",
                    "meaning": "test an omitted prerequisite",
                    "scheduler_condition": "afterok",
                    "to": "platt-dirichlet-theorem-7-1",
                }
            )
            with self.assertRaisesRegex(
                portfolio.PortfolioError, "omits prerequisite campaign"
            ):
                portfolio.build_plan(
                    spec,
                    changed,
                    fixture.semantic,
                    realization_catalog=fixture.realizations,
                    terminal_result_catalog=fixture.terminal_results,
                    production_budget_gate=ready_budget_gate(
                        campaign_ids=required
                    ),
                )

    def test_source_retirement_and_lowered_profiles_are_independent(self) -> None:
        inventory = portfolio.completion_profile_inventory()
        rows = {row["profile_id"]: row for row in inventory["profiles"]}
        source = rows[portfolio.SOURCE_RETIREMENT_PROFILE]
        lowered = rows[portfolio.LOWERED_10POW27_COMPLETION_PROFILE]
        self.assertIn(
            portfolio.HISTORICAL_GOLDBACH_CAMPAIGN,
            source["required_campaign_ids"],
        )
        self.assertNotIn(
            portfolio.GOLDBACH_10POW27_CAMPAIGN,
            source["required_campaign_ids"],
        )
        self.assertNotIn(
            portfolio.HISTORICAL_GOLDBACH_CAMPAIGN,
            lowered["required_campaign_ids"],
        )
        self.assertIn(
            portfolio.GOLDBACH_10POW27_CAMPAIGN,
            lowered["required_campaign_ids"],
        )
        self.assertEqual(
            set(source["required_campaign_ids"])
            - {portfolio.HISTORICAL_GOLDBACH_CAMPAIGN},
            set(lowered["required_campaign_ids"])
            - {portfolio.GOLDBACH_10POW27_CAMPAIGN},
        )

    def test_lowered_profile_recomputes_sizing_without_historical_campaign(self) -> None:
        required = portfolio.COMPLETION_PROFILES[
            portfolio.LOWERED_10POW27_COMPLETION_PROFILE
        ].required_campaign_ids
        gate = portfolio._current_production_budget_gate("spot", required)
        self.assertEqual(gate["covered_campaign_ids"], list(required))
        self.assertNotIn(
            portfolio.HISTORICAL_GOLDBACH_CAMPAIGN,
            gate["blocking_campaign_ids"],
        )
        self.assertIn(
            portfolio.GOLDBACH_10POW27_CAMPAIGN,
            gate["blocking_campaign_ids"],
        )
        self.assertFalse(gate["production_ready"])

    def test_current_semantics_and_budget_still_block_init(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PortfolioFixture(Path(temporary), complete_semantics=False)
            context = portfolio.load_portfolio_spec(fixture.spec_path)
            self.assertFalse(context.plan["ready_for_local_preparation"])
            codes = {gap["code"] for gap in context.plan["gaps"]}
            self.assertIn("semantic_binding_disabled", codes)
            self.assertNotIn("production_backend_operator_absent", codes)
            self.assertIn("production_budget_gate_failed", codes)
            self.assertNotIn("production_sizing_absent", codes)
            with self.assertRaisesRegex(portfolio.PortfolioError, "gaps remain"):
                portfolio.initialize(context)
            self.assertFalse(fixture.run_root.exists())

    def test_staged_terminal_contracts_initialize_but_budget_blocks_handoff(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            required = portfolio.COMPLETION_PROFILES[
                portfolio.SOURCE_RETIREMENT_PROFILE
            ].required_campaign_ids
            fixture = PortfolioFixture(
                Path(temporary),
                complete_semantics=False,
                completion_profile=portfolio.SOURCE_RETIREMENT_PROFILE,
                production_semantics=True,
            )
            blocked_budget = ready_budget_gate(campaign_ids=required)
            blocked_budget.update(
                {
                    "blocking_campaign_ids": list(required),
                    "portfolio_high_cost_usd": "0.00",
                    "portfolio_high_wall_hours": "0",
                    "production_ready": False,
                }
            )
            context = fixture.load_production_semantics_context(blocked_budget)
            readiness = context.plan["readiness"]
            self.assertTrue(readiness["local_initialization_ready"])
            self.assertFalse(readiness["operator_handoff_ready"])
            self.assertFalse(readiness["semantic_admission_complete"])
            self.assertEqual(
                readiness["operator_handoff_blocking_gap_codes"],
                ["production_budget_gate_failed"],
            )
            self.assertEqual(
                {
                    gap["code"] for gap in context.plan["gaps"]
                    if gap["campaign_id"] != "portfolio"
                },
                {"semantic_binding_disabled"},
            )

            initialized = portfolio.initialize(
                context,
                now=dt.datetime(
                    2026, 7, 22, 12, 0, tzinfo=dt.timezone.utc
                ),
            )
            self.assertFalse(initialized["accepted"])
            self.assertFalse(initialized["operator_handoff_ready"])
            self.assertFalse(initialized["semantic_admission_complete"])
            with self.assertRaisesRegex(
                portfolio.PortfolioError, "production launch gaps remain"
            ):
                portfolio.prepare_shard(
                    context,
                    "ch25-a7-boundary::single-job",
                    0,
                    nonce="a" * 64,
                )
            self.assertFalse((fixture.run_root / "shards").exists())

    def test_staged_contract_drives_handoff_and_receipt_validation_not_admission(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            required = portfolio.COMPLETION_PROFILES[
                portfolio.SOURCE_RETIREMENT_PROFILE
            ].required_campaign_ids
            fixture = PortfolioFixture(
                Path(temporary),
                complete_semantics=False,
                completion_profile=portfolio.SOURCE_RETIREMENT_PROFILE,
                production_semantics=True,
            )
            context = fixture.load_production_semantics_context(
                ready_budget_gate(campaign_ids=required)
            )
            self.assertTrue(context.plan["readiness"]["operator_handoff_ready"])
            self.assertFalse(
                context.plan["readiness"]["semantic_admission_complete"]
            )
            self.assertEqual(
                {gap["code"] for gap in context.plan["gaps"]},
                {"semantic_binding_disabled"},
            )
            instant = dt.datetime(
                2026, 7, 22, 12, 0, tzinfo=dt.timezone.utc
            )
            portfolio.initialize(context, now=instant)
            prepared = portfolio.prepare_shard(
                context,
                "ch25-a7-boundary::single-job",
                0,
                now=instant,
                nonce="b" * 64,
            )
            config = prepared["config"]
            self.assertIsNone(config["semantic_binding"])
            self.assertFalse(config["semantic_admission_enabled"])
            self.assertEqual(
                config["terminal_receipt_contract"],
                {
                    "classification": (
                        "registered_invocation_and_result_contract_not_"
                        "theorem_authority"
                    ),
                    "registered_invocation": "ch25A7BoundaryProductionV1",
                    "registered_result_argument": "--registered-result-output",
                    "registered_result_artifact_template": (
                        "${TG_RUN_ROOT}/ch25-a7-boundary/"
                        "registered-result.txt"
                    ),
                    "semantic_admission_enabled": False,
                },
            )

            returned_path = Path(temporary) / "returned-receipt.json"
            returned_path.write_bytes(b"{}\n")
            receipt = {
                "backend": "azure_sevsnp_cpu",
                "claim": {"nonce": "b" * 64},
                "receipt_sha256": "c" * 64,
            }
            with mock.patch.object(
                portfolio, "load_verified_receipt", return_value=receipt
            ) as load_receipt, mock.patch.object(
                portfolio, "validate_registered_invocation"
            ) as validate_invocation:
                recorded = portfolio.record_verified_receipt(
                    context,
                    "ch25-a7-boundary::single-job",
                    0,
                    returned_path,
                )
                current = portfolio.status(context, now=instant)
            self.assertFalse(recorded["accepted"])
            self.assertEqual(
                recorded["classification"],
                "signed_receipt_recorded_not_lean_theorem_acceptance",
            )
            self.assertGreaterEqual(load_receipt.call_count, 2)
            self.assertTrue(
                all(
                    call.args[1] == "ch25A7BoundaryProductionV1"
                    for call in validate_invocation.call_args_list
                )
            )
            self.assertFalse(current["semantic_admission_complete"])
            self.assertEqual(current["lean_atoms_discharged"], 0)

    def test_staged_terminal_result_validation_failure_is_not_recorded(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            required = portfolio.COMPLETION_PROFILES[
                portfolio.SOURCE_RETIREMENT_PROFILE
            ].required_campaign_ids
            fixture = PortfolioFixture(
                Path(temporary),
                complete_semantics=False,
                completion_profile=portfolio.SOURCE_RETIREMENT_PROFILE,
                production_semantics=True,
            )
            context = fixture.load_production_semantics_context(
                ready_budget_gate(campaign_ids=required)
            )
            instant = dt.datetime(
                2026, 7, 22, 12, 0, tzinfo=dt.timezone.utc
            )
            portfolio.initialize(context, now=instant)
            portfolio.prepare_shard(
                context,
                "ch25-a7-boundary::single-job",
                0,
                now=instant,
                nonce="d" * 64,
            )
            returned_path = Path(temporary) / "bad-receipt.json"
            returned_path.write_bytes(b"{}\n")
            receipt = {
                "backend": "azure_sevsnp_cpu",
                "claim": {"nonce": "d" * 64},
                "receipt_sha256": "e" * 64,
            }
            with mock.patch.object(
                portfolio, "load_verified_receipt", return_value=receipt
            ), mock.patch.object(
                portfolio,
                "validate_registered_invocation",
                side_effect=portfolio.ReceiptError("registered result mismatch"),
            ):
                with self.assertRaisesRegex(
                    portfolio.PortfolioError, "does not realize"
                ):
                    portfolio.record_verified_receipt(
                        context,
                        "ch25-a7-boundary::single-job",
                        0,
                        returned_path,
                    )
            state = json.loads(
                (fixture.run_root / "portfolio-state.json").read_text(
                    encoding="utf-8"
                )
            )
            record = next(iter(state["records"].values()))
            self.assertEqual(record["stage"], "challenge_created")
            self.assertIsNone(record["receipt_sha256"])

    def test_json_binding_cannot_assert_a_lean_realization_by_itself(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PortfolioFixture(Path(temporary), complete_semantics=True)
            routes = {
                key: portfolio.BackendRoute(
                    receipt_backend=value.receipt_backend,
                    operator_adapter=value.operator_adapter or "fixture/cpu.py",
                    production_operator_available=True,
                    reason=None,
                )
                for key, value in portfolio.BACKEND_ROUTES.items()
            }
            with mock.patch.dict(
                portfolio.BACKEND_ROUTES, routes, clear=True
            ), mock.patch.object(
                portfolio,
                "_current_production_budget_gate",
                return_value=ready_budget_gate(),
            ):
                context = portfolio.load_portfolio_spec(fixture.spec_path)
            self.assertFalse(context.plan["ready_for_local_preparation"])
            self.assertEqual(
                {gap["code"] for gap in context.plan["gaps"]},
                {"lean_realization_unregistered"},
            )

    def test_portfolio_budget_limits_cannot_be_relaxed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PortfolioFixture(Path(temporary), complete_semantics=True)
            weakened = ready_budget_gate()
            weakened["hard_max_wall_hours"] = "169"
            with self.assertRaisesRegex(portfolio.PortfolioError, "hard gate"):
                portfolio.build_plan(
                    fixture.spec,
                    fixture.cluster,
                    fixture.semantic,
                    realization_catalog=fixture.realizations,
                    production_budget_gate=weakened,
                )

    def test_isolated_shards_have_unique_configs_challenges_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PortfolioFixture(Path(temporary), complete_semantics=True)
            context = fixture.load_ready_context()
            instant = dt.datetime(2026, 7, 22, 12, 0, tzinfo=dt.timezone.utc)
            portfolio.initialize(context, now=instant)
            group = "helfgott-prop-12-2-4-mpfr-v1::mpfr-shards"
            first = portfolio.prepare_shard(
                context, group, 0, now=instant, nonce="1" * 64
            )
            second = portfolio.prepare_shard(
                context, group, 1, now=instant, nonce="2" * 64
            )
            self.assertNotEqual(
                first["config"]["task_id"], second["config"]["task_id"]
            )
            self.assertNotEqual(
                first["config"]["challenge"]["path"],
                second["config"]["challenge"]["path"],
            )
            index_position = first["config"]["argv"].index("run-worker-group") + 3
            self.assertEqual(first["config"]["argv"][index_position], "0")
            self.assertEqual(second["config"]["argv"][index_position], "1")
            resumed = portfolio.prepare_shard(
                context,
                group,
                0,
                now=instant + dt.timedelta(minutes=1),
                nonce="f" * 64,
            )
            self.assertEqual(
                resumed["classification"],
                "resumed_existing_isolated_shard_handoff",
            )
            self.assertEqual(resumed["config"], first["config"])
            status = portfolio.status(context, now=instant + dt.timedelta(minutes=1))
            row = next(item for item in status["groups"] if item["group_id"] == group)
            self.assertEqual(row["claimed_shards"], 2)
            self.assertEqual(row["completed_shards"], 0)
            self.assertEqual(row["ready_unclaimed_shards"], 2)

    def test_dependencies_cannot_be_manually_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PortfolioFixture(Path(temporary), complete_semantics=True)
            context = fixture.load_ready_context()
            instant = dt.datetime(2026, 7, 22, 12, 0, tzinfo=dt.timezone.utc)
            portfolio.initialize(context, now=instant)
            with self.assertRaisesRegex(portfolio.PortfolioError, "predecessor groups"):
                portfolio.prepare_shard(
                    context,
                    "ch25-psi-two-pass-v1::summary-shards",
                    0,
                    now=instant,
                    nonce="3" * 64,
                )
            self.assertFalse(
                hasattr(portfolio, "record_manual_completion"),
                "manual completion must not exist as an orchestration API",
            )

    def test_expired_attempt_requires_manual_reconciliation_not_reissue(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PortfolioFixture(Path(temporary), complete_semantics=True)
            context = fixture.load_ready_context()
            instant = dt.datetime(2026, 7, 22, 12, 0, tzinfo=dt.timezone.utc)
            portfolio.initialize(context, now=instant)
            group = "helfgott-prop-12-2-4-mpfr-v1::mpfr-shards"
            portfolio.prepare_shard(
                context, group, 3, now=instant, nonce="4" * 64
            )
            with self.assertRaisesRegex(portfolio.PortfolioError, "expired"):
                portfolio.prepare_shard(
                    context,
                    group,
                    3,
                    now=instant + dt.timedelta(hours=2),
                    nonce="5" * 64,
                )

    def test_exact_orphan_handoff_is_recovered_without_nonce_rotation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PortfolioFixture(Path(temporary), complete_semantics=True)
            context = fixture.load_ready_context()
            instant = dt.datetime(2026, 7, 22, 12, 0, tzinfo=dt.timezone.utc)
            portfolio.initialize(context, now=instant)
            group = "helfgott-prop-12-2-4-mpfr-v1::mpfr-shards"
            created = portfolio.prepare_shard(
                context, group, 3, now=instant, nonce="8" * 64
            )
            # Model a crash window: immutable files reached disk, while the
            # subsequent state replacement did not.
            state_path = fixture.run_root / "portfolio-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["records"] = {}
            state_path.write_bytes(canonical_json_bytes(state))
            recovered = portfolio.prepare_shard(
                context,
                group,
                3,
                now=instant + dt.timedelta(minutes=1),
                nonce="9" * 64,
            )
            self.assertEqual(
                recovered["classification"],
                "recovered_exact_orphan_shard_handoff",
            )
            self.assertEqual(
                recovered["config"]["challenge"]["nonce"],
                created["config"]["challenge"]["nonce"],
            )

    def test_tampering_with_retained_challenge_fails_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PortfolioFixture(Path(temporary), complete_semantics=True)
            context = fixture.load_ready_context()
            instant = dt.datetime(2026, 7, 22, 12, 0, tzinfo=dt.timezone.utc)
            portfolio.initialize(context, now=instant)
            group = "helfgott-prop-12-2-4-mpfr-v1::mpfr-shards"
            created = portfolio.prepare_shard(
                context, group, 2, now=instant, nonce="6" * 64
            )
            challenge_path = Path(created["config"]["challenge"]["path"])
            value = json.loads(challenge_path.read_text(encoding="utf-8"))
            value["nonce"] = "7" * 64
            challenge_path.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(portfolio.PortfolioError, "challenge changed"):
                portfolio.status(context, now=instant)

    def test_repository_or_semantic_pin_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PortfolioFixture(Path(temporary), complete_semantics=True)
            semantic_path = (
                fixture.repository
                / "specifications/TERNARY_GOLDBACH_AZURE_SEMANTIC_BINDINGS.json"
            )
            semantic_path.write_bytes(b"{}\n")
            with self.assertRaisesRegex(portfolio.PortfolioError, "repository"):
                fixture.load_ready_context()

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_json_schemas_cover_spec_semantics_and_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PortfolioFixture(Path(temporary), complete_semantics=True)
            context = fixture.load_ready_context()
            jsonschema.Draft202012Validator(
                json.loads(SPEC_SCHEMA.read_text(encoding="utf-8"))
            ).validate(fixture.spec)
            jsonschema.Draft202012Validator(
                json.loads(SEMANTIC_SCHEMA.read_text(encoding="utf-8"))
            ).validate(fixture.semantic)
            production_semantics = json.loads(
                PRODUCTION_SEMANTICS.read_text(encoding="utf-8")
            )
            self.assertEqual(
                PRODUCTION_SEMANTICS.read_bytes(),
                canonical_json_bytes(production_semantics),
            )
            jsonschema.Draft202012Validator(
                json.loads(SEMANTIC_SCHEMA.read_text(encoding="utf-8"))
            ).validate(production_semantics)
            jsonschema.Draft202012Validator(
                json.loads(PLAN_SCHEMA.read_text(encoding="utf-8"))
            ).validate(context.plan)
            redacted = json.loads(REDACTED_SPEC.read_text(encoding="utf-8"))
            self.assertEqual(REDACTED_SPEC.read_bytes(), canonical_json_bytes(redacted))
            jsonschema.Draft202012Validator(
                json.loads(SPEC_SCHEMA.read_text(encoding="utf-8"))
            ).validate(redacted)


if __name__ == "__main__":
    unittest.main()
