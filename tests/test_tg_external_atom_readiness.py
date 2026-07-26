# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from generate_trusted_compute_lean import REGISTERED_INVOCATIONS  # noqa: E402
from tg_verifier import azure_portfolio, h100_cluster  # noqa: E402
from tg_verifier.campaign import load_registry  # noqa: E402
from tg_verifier.catalog import ATOMS  # noqa: E402


REPORT_PATH = (
    REPOSITORY_ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_EXTERNAL_ATOM_READINESS.json"
)
SEMANTIC_PATH = (
    REPOSITORY_ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_AZURE_SEMANTIC_BINDINGS.json"
)


def _cluster_view() -> dict:
    return {
        "jobs": [
            h100_cluster._job_record(workload)
            for workload in h100_cluster.WORKLOADS
        ],
        "physical_campaigns": h100_cluster._physical_campaign_records(),
        "dependency_edges": [
            {
                "from": h100_cluster.ZETA_Q1_ATOM,
                "to": h100_cluster.DIRICHLET_ATOM,
            },
            *[
                {
                    "from": h100_cluster.HURST_PRIMARY_ATOM,
                    "to": atom_id,
                }
                for atom_id in h100_cluster.HURST_ATOMS
                if atom_id != h100_cluster.HURST_PRIMARY_ATOM
            ],
        ],
    }


class ExternalAtomReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        cls.semantic = json.loads(SEMANTIC_PATH.read_text(encoding="utf-8"))

    def test_profile_registry_is_bound_to_the_current_catalog(self) -> None:
        registry = load_registry()
        self.assertEqual(
            [profile.atom_id for profile in registry.profiles],
            [atom.atom_id for atom in ATOMS],
        )

    def test_report_covers_the_exact_thirteen_atoms_in_catalog_order(self) -> None:
        rows = self.report["atoms"]
        self.assertEqual(
            [row["atom_id"] for row in rows],
            [atom.atom_id for atom in ATOMS],
        )
        self.assertEqual(len(rows), 13)
        self.assertTrue(all(row["full_range_capable"] for row in rows))
        self.assertFalse(any(row["only_sample_or_prototype"] for row in rows))
        self.assertFalse(any(row["theorem_authority_ready"] for row in rows))

    def test_physical_campaign_partition_matches_cluster_source(self) -> None:
        reported = {
            row["campaign_id"]: row["logical_atom_ids"]
            for row in self.report["physical_campaigns"]
        }
        expected = {
            row["campaign_id"]: row["logical_atom_ids"]
            for row in h100_cluster._physical_campaign_records()
            if h100_cluster.GOLDBACH_10POW27_ATOM
            not in row["logical_atom_ids"]
        }
        self.assertEqual(reported, expected)
        self.assertEqual(len(reported), 10)

        by_atom = {row["atom_id"]: row for row in self.report["atoms"]}
        for campaign_id, atom_ids in expected.items():
            for atom_id in atom_ids:
                self.assertEqual(
                    by_atom[atom_id]["physical_campaign_id"], campaign_id
                )

    def test_every_reported_group_has_the_claimed_closed_materializer_shape(self) -> None:
        groups = azure_portfolio._phase_groups(_cluster_view())
        for group in groups:
            azure_portfolio._bind_group_operator_capability(group)
        by_campaign: dict[str, list[dict]] = {}
        for group in groups:
            by_campaign.setdefault(group["campaign_id"], []).append(group)

        for campaign in self.report["physical_campaigns"]:
            rows = by_campaign[campaign["campaign_id"]]
            self.assertEqual(
                len(rows), campaign["deployment"]["portfolio_group_count"]
            )
            self.assertTrue(
                all(row["production_operator_available"] for row in rows)
            )
            self.assertTrue(
                campaign["deployment"]["all_group_materializers_recognized"]
            )
            self.assertEqual(
                {
                    row["materializer_adapter"]
                    for row in rows
                    if row["materializer_adapter"] is not None
                },
                set(campaign["deployment"]["materializers"]),
            )

    def test_semantic_inventory_and_realization_classification_match_source(self) -> None:
        bindings = {
            row["campaign_id"]: row for row in self.semantic["bindings"]
        }
        for campaign in self.report["physical_campaigns"]:
            semantic = campaign["semantic_output"]
            invocation = semantic["registered_invocation"]
            self.assertIn(invocation, REGISTERED_INVOCATIONS)
            certificate = REPOSITORY_ROOT / semantic["registered_certificate"]
            self.assertTrue(certificate.is_file())
            self.assertIn(invocation, certificate.read_text(encoding="utf-8"))

            binding = bindings[campaign["campaign_id"]]
            inventory = semantic["semantic_inventory"]
            realization = semantic["source_realization_catalog"]
            if binding["enabled"]:
                self.assertEqual(inventory, "enabled")
                self.assertEqual(
                    azure_portfolio.SOURCE_TG_REALIZATIONS[
                        binding["realization_id"]
                    ]["registered_invocation"],
                    invocation,
                )
                self.assertEqual(
                    realization, "registered_but_no_run_authority"
                )
            elif binding["registered_invocation"] is not None:
                self.assertEqual(inventory, "disabled_with_staged_identity")
                self.assertEqual(
                    azure_portfolio.PENDING_TG_REALIZATIONS[
                        binding["realization_id"]
                    ]["registered_invocation"],
                    invocation,
                )
                self.assertEqual(realization, "pending_not_authoritative")
            else:
                self.assertEqual(inventory, "disabled_null")
                self.assertNotIn(
                    invocation,
                    {
                        row["registered_invocation"]
                        for row in azure_portfolio.SOURCE_TG_REALIZATIONS.values()
                    },
                )
                self.assertNotIn(
                    invocation,
                    {
                        row["registered_invocation"]
                        for row in azure_portfolio.PENDING_TG_REALIZATIONS.values()
                    },
                )
                self.assertEqual(realization, "absent")

    def test_all_report_evidence_paths_exist(self) -> None:
        for campaign in self.report["physical_campaigns"]:
            paths = [
                *campaign["algorithm"]["sources"],
                campaign["semantic_output"]["registered_certificate"],
                *campaign["deployment"]["materializers"],
                campaign["deployment"]["cli"],
                campaign["benchmark"]["source"],
            ]
            for relative in paths:
                self.assertTrue(
                    (REPOSITORY_ROOT / relative).is_file(),
                    f"{campaign['campaign_id']} references missing {relative}",
                )

    def test_report_remains_fail_closed_while_pins_and_registry_are_empty(self) -> None:
        pins = (
            REPOSITORY_ROOT
            / self.report["global_trust_state"][
                "production_deployment_pin_file"
            ]
        ).read_text(encoding="utf-8")
        registry = (
            REPOSITORY_ROOT
            / self.report["global_trust_state"]["trusted_compute_registry_file"]
        ).read_text(encoding="utf-8")
        self.assertEqual(pins.count("Option ReviewedProductionDeployment := none"), 12)
        self.assertIn(
            "def importedTrustedComputeRuns : List TrustedComputeEvidence := []",
            registry,
        )
        self.assertEqual(
            self.report["summary"]["installed_production_deployment_pins"], 0
        )
        self.assertEqual(
            self.report["summary"]["source_admitted_trusted_compute_receipts"],
            0,
        )
        self.assertEqual(
            self.report["summary"]["logical_atoms_with_current_theorem_authority"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
