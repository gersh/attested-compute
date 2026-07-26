# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Static consistency checks for the external-program readiness audit."""

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROGRAM_READINESS = (
    ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_EXTERNAL_PROGRAM_READINESS.json"
)
ATOM_INVENTORY = (
    ROOT / "specifications" / "TERNARY_GOLDBACH_EXTERNAL_ATOMS.json"
)
PHYSICAL_INVENTORY = (
    ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_EXTERNAL_ATOM_READINESS.json"
)
MARKDOWN = (
    ROOT
    / "docs"
    / "algorithms"
    / "TERNARY_GOLDBACH_EXTERNAL_PROGRAM_READINESS.md"
)
SOURCE_PROGRAM_CATALOG = (
    ROOT
    / "SparkInterval"
    / "TernaryGoldbach"
    / "ClosedSourceProgramCatalog.lean"
)
DEPLOYMENT_PINS = (
    ROOT / "SparkInterval" / "Execution" / "ProductionDeploymentPins.lean"
)
TRUSTED_COMPUTE_REGISTRY = (
    ROOT / "SparkInterval" / "Execution" / "TrustedComputeRegistry.lean"
)


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


class ExternalProgramReadinessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = _load(PROGRAM_READINESS)
        cls.atom_inventory = _load(ATOM_INVENTORY)
        cls.physical_inventory = _load(PHYSICAL_INVENTORY)
        cls.rows = cls.audit["physical_campaigns"]

    def test_exact_ten_to_thirteen_crosswalk(self) -> None:
        expected_atoms = {
            row["id"] for row in self.atom_inventory["atoms"]
        }
        audited_atoms = [
            atom
            for row in self.rows
            for atom in row["logical_atom_ids"]
        ]
        self.assertEqual(len(self.rows), 10)
        self.assertEqual(len(audited_atoms), 13)
        self.assertEqual(len(audited_atoms), len(set(audited_atoms)))
        self.assertEqual(set(audited_atoms), expected_atoms)

        authoritative_map = {
            row["campaign_id"]: tuple(row["logical_atom_ids"])
            for row in self.physical_inventory["physical_campaigns"]
        }
        audited_map = {
            row["campaign_id"]: tuple(row["logical_atom_ids"])
            for row in self.rows
        }
        self.assertEqual(audited_map, authoritative_map)

    def test_every_referenced_source_path_exists(self) -> None:
        for row in self.rows:
            paths: list[str] = []
            paths.extend(row["generator_runtime"]["files"])
            paths.extend(row["complete_artifact_output"]["files"])
            paths.extend(row["strict_parser"]["files"])
            paths.extend(row["total_checker"]["files"])
            paths.extend(row["lean_soundness"]["files"])
            paths.extend(row["azure"]["materializers"])
            paths.extend(row["azure"]["site_examples"])
            for relative in paths:
                with self.subTest(
                    campaign=row["campaign_id"], path=relative
                ):
                    self.assertTrue((ROOT / relative).is_file())

    def test_summary_matches_rows(self) -> None:
        summary = self.audit["summary"]
        lean_artifact_statuses = [
            row["complete_artifact_output"]["lean_source_artifact"]
            for row in self.rows
        ]
        catalog_statuses = [row["catalog"]["status"] for row in self.rows]
        self.assertEqual(
            summary["complete_lean_source_artifact_programs"],
            lean_artifact_statuses.count("complete"),
        )
        self.assertEqual(
            summary["partial_lean_artifact_boundaries"],
            lean_artifact_statuses.count("partial"),
        )
        self.assertEqual(
            summary["absent_complete_lean_artifact_boundaries"],
            lean_artifact_statuses.count("absent"),
        )
        self.assertEqual(summary["catalog_concrete_campaigns"], 1)
        self.assertEqual(
            catalog_statuses.count("artifact_concrete_source_only"), 1
        )
        self.assertTrue(
            all(
                not row["catalog"]["production_artifact_installed"]
                and not row["catalog"]["reviewed_receipt_installed"]
                for row in self.rows
            )
        )

    def test_cdem_is_the_only_complete_lean_artifact_program(self) -> None:
        complete = [
            row["campaign_id"]
            for row in self.rows
            if row["complete_artifact_output"]["lean_source_artifact"]
            == "complete"
        ]
        self.assertEqual(complete, ["cdem-table-abel"])
        cdem = next(
            row
            for row in self.rows
            if row["campaign_id"] == "cdem-table-abel"
        )
        self.assertEqual(
            cdem["strict_parser"]["status"],
            "external_and_lean_complete",
        )
        self.assertEqual(
            cdem["lean_soundness"]["status"],
            "complete_artifact_acceptance_to_exact_source_claim",
        )
        self.assertEqual(
            cdem["catalog"]["status"],
            "artifact_concrete_source_only",
        )

    def test_catalog_and_post_run_trust_state_match_source(self) -> None:
        catalog = SOURCE_PROGRAM_CATALOG.read_text(encoding="utf-8")
        self.assertIn(
            "| .cdemTableAbel => .artifactConcrete cdemAbelConcrete",
            catalog,
        )
        self.assertIn(
            "Campaign.all.filter isConcrete = [.cdemTableAbel]",
            catalog,
        )

        pins = DEPLOYMENT_PINS.read_text(encoding="utf-8")
        for row in self.rows:
            self.assertFalse(row["catalog"]["production_artifact_installed"])
        self.assertNotIn(
            "Option ReviewedProductionDeployment := some", pins
        )

        registry = TRUSTED_COMPUTE_REGISTRY.read_text(encoding="utf-8")
        self.assertIn(
            "def importedTrustedComputeRuns : List TrustedComputeEvidence := []",
            registry,
        )

    def test_all_azure_routes_are_packaged_but_not_run(self) -> None:
        for row in self.rows:
            with self.subTest(campaign=row["campaign_id"]):
                self.assertTrue(row["azure"]["materializers"])
                self.assertIn("not_run", row["azure"]["status"])
                self.assertFalse(
                    row["catalog"]["reviewed_receipt_installed"]
                )

    def test_markdown_covers_every_campaign_and_trust_warning(self) -> None:
        text = MARKDOWN.read_text(encoding="utf-8")
        for row in self.rows:
            self.assertIn(f"`{row['campaign_id']}`", text)
        self.assertIn("no campaign currently receives theorem authority", text)
        self.assertIn(
            "CDEM Abel is the sole complete Lean source-artifact program",
            text,
        )


if __name__ == "__main__":
    unittest.main()
