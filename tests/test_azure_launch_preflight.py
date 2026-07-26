# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest

from tg_verifier.azure_launch_preflight import build_preflight_report


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/tg_azure_launch_preflight.py"


class AzureLaunchPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = build_preflight_report(run_cli_help=True)
        cls.rows = {
            row["campaign_id"]: row for row in cls.report["campaigns"]
        }

    def test_exact_ten_source_campaigns_are_mechanically_packaged(self) -> None:
        summary = self.report["summary"]
        self.assertEqual(summary["physical_campaigns"], 10)
        self.assertEqual(summary["portfolio_group_count"], 33)
        self.assertEqual(summary["materializer_cli_count"], 14)
        self.assertEqual(summary["site_example_count"], 15)
        self.assertEqual(summary["registered_invocation_count"], 10)
        self.assertEqual(summary["reviewed_terminal_result_contracts"], 10)
        self.assertEqual(
            summary["source_materialization_ready_campaigns"], 10
        )
        self.assertEqual(summary["cloud_launch_ready_campaigns"], 0)
        self.assertEqual(summary["theorem_admission_complete_campaigns"], 0)
        for row in self.rows.values():
            with self.subTest(campaign=row["campaign_id"]):
                self.assertTrue(row["source_materialization_ready"])
                self.assertIn("source-ready", row["readiness_classes"])
                self.assertTrue(row["group_count_exact"])
                self.assertTrue(row["route_materializers_reviewed"])
                self.assertTrue(row["invocation"]["known"])
                self.assertTrue(
                    row["invocation"]["backend_matches_terminal"]
                )

    def test_every_routed_cli_and_site_schema_is_discoverable(self) -> None:
        for row in self.rows.values():
            for check in row["cli_checks"]:
                with self.subTest(cli=check["cli"]):
                    self.assertTrue(check["discovered"])
                    self.assertTrue(check["help_checked"])
                    self.assertEqual(check["help_exit_code"], 0)
            for check in row["site_checks"]:
                with self.subTest(example=check["example"]):
                    self.assertTrue(check["schema_valid"])
                    self.assertGreater(check["redaction_marker_count"], 0)
                    self.assertFalse(
                        check["usable_as_production_site_configuration"]
                    )

    def test_current_blockers_are_classified_without_enabling_them(self) -> None:
        summary = self.report["summary"]
        self.assertEqual(summary["site_pin_needed_campaigns"], 10)
        self.assertEqual(summary["calibration_blocked_campaigns"], 10)
        self.assertEqual(
            summary["semantic_admission_blocked_campaigns"], 10
        )
        self.assertEqual(summary["algorithm_incomplete_campaigns"], 2)
        incomplete = {
            row["campaign_id"]
            for row in self.rows.values()
            if row["algorithm_incomplete"]
        }
        self.assertEqual(
            incomplete,
            {
                "platt-dirichlet-theorem-7-1",
                "platt-trudgian-rh-3e12",
            },
        )

    def test_semantic_shapes_are_one_enabled_nine_staged_none_absent(self) -> None:
        counts: dict[str, int] = {}
        for row in self.rows.values():
            shape = row["semantic_shape"]
            counts[shape] = counts.get(shape, 0) + 1
        self.assertEqual(
            counts,
            {
                "enabled_source_shape_without_run_authority": 1,
                "staged_pending_not_authoritative": 9,
            },
        )
        self.assertTrue(
            all(row["semantic_admission_blocked"] for row in self.rows.values())
        )
        self.assertTrue(
            all(
                not row["theorem_admission_complete"]
                for row in self.rows.values()
            )
        )
        reviewed_terminals = [
            row
            for row in self.rows.values()
            if row["invocation"]["terminal_result_contract_reviewed"]
        ]
        self.assertEqual(len(reviewed_terminals), 10)
        self.assertTrue(
            all(
                row["invocation"]["terminal_result_contract_exact"]
                for row in reviewed_terminals
            )
        )

    def test_cli_emits_report_and_does_not_claim_acceptance(self) -> None:
        completed = subprocess.run(
            [str(TOOL), "--no-cli-help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertFalse(report["accepted"])
        self.assertEqual(report["summary"]["physical_campaigns"], 10)
        self.assertIn("not_execution_evidence", report["classification"])


if __name__ == "__main__":
    unittest.main()
