# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""The PoC site-pin inventory tracks the launch preflight exactly."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier import azure_launch_preflight  # noqa: E402
from tg_verifier.azure_poc_site_pin import (  # noqa: E402
    PIN_CLASSES,
    POC_CAMPAIGNS,
    REVIEWED_PINS,
    SILENT_REQUIREMENTS,
    build_inventory,
)


class PocSitePinInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = build_inventory()
        # The preflight is the authority on which campaigns are site-pin
        # blocked; running it without the bounded --help subprocesses keeps
        # this test fast while checking the same flags.
        cls.preflight = azure_launch_preflight.build_preflight_report(
            run_cli_help=False
        )

    def preflight_row(self, campaign_id: str) -> dict:
        rows = [
            row
            for row in self.preflight["campaigns"]
            if row["campaign_id"] == campaign_id
        ]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_both_poc_campaigns_are_covered(self) -> None:
        self.assertEqual(
            {row["campaign_id"] for row in self.report["campaigns"]},
            set(POC_CAMPAIGNS),
        )

    def test_pin_count_matches_the_preflight_marker_count(self) -> None:
        for campaign in self.report["campaigns"]:
            row = self.preflight_row(campaign["campaign_id"])
            expected = sum(
                check["redaction_marker_count"] for check in row["site_checks"]
            )
            self.assertEqual(campaign["pin_count"], expected, campaign["campaign_id"])

    def test_every_pin_location_matches_a_preflight_marker(self) -> None:
        for campaign in self.report["campaigns"]:
            row = self.preflight_row(campaign["campaign_id"])
            markers = {
                marker.rsplit("=", 1)[0]
                for check in row["site_checks"]
                for marker in check["redaction_markers"]
            }
            locations = {
                pin["location"]
                for site in campaign["site_examples"]
                for pin in site["pins"]
            }
            self.assertEqual(locations, markers, campaign["campaign_id"])

    def test_the_inventory_does_not_flip_any_readiness_flag(self) -> None:
        # Building the inventory is read-only; both PoC campaigns must still
        # be reported by the preflight exactly as they were.
        for campaign_id in POC_CAMPAIGNS:
            row = self.preflight_row(campaign_id)
            self.assertTrue(row["site_pin_needed"], campaign_id)
            self.assertFalse(row["cloud_launch_ready"], campaign_id)
            self.assertFalse(row["theorem_admission_complete"], campaign_id)
        self.assertFalse(self.report["accepted"])
        self.assertFalse(self.preflight["accepted"])

    def test_every_pin_has_a_reviewed_class(self) -> None:
        for pin in REVIEWED_PINS:
            self.assertIn(pin["pin_class"], PIN_CLASSES)
            self.assertEqual(
                pin["obtainable_before_subscription"],
                PIN_CLASSES[pin["pin_class"]]["obtainable_before_subscription"],
            )

    def test_chained_pins_name_a_dependency_that_exists(self) -> None:
        locations = {pin["location"] for pin in REVIEWED_PINS}
        for pin in REVIEWED_PINS:
            if pin["pin_class"] == "chained_after":
                self.assertIn(pin["depends_on"], locations, pin["location"])
            else:
                self.assertIsNone(pin["depends_on"], pin["location"])

    def test_chained_dependencies_are_acyclic(self) -> None:
        parent = {
            pin["location"]: pin["depends_on"]
            for pin in REVIEWED_PINS
            if pin["depends_on"] is not None
        }
        for start in parent:
            seen = set()
            node = start
            while node is not None:
                self.assertNotIn(node, seen, f"cycle reachable from {start}")
                seen.add(node)
                node = parent.get(node)

    def test_repository_derivable_values_are_real_digests(self) -> None:
        values = self.report["repository_derivable_values"]
        for key in (
            "cdem_table_abel_reviewed_source_closure",
            "ramare_zuniga_reviewed_source_closure",
        ):
            closure = values[key]
            self.assertGreater(closure["file_count"], 0)
            self.assertEqual(closure["file_count"], len(closure["files"]))
            self.assertGreater(closure["total_bytes"], 0)
            self.assertRegex(closure["rows_sha256"], r"\A[0-9a-f]{64}\Z")
            for row in closure["files"]:
                self.assertRegex(row["sha256"], r"\A[0-9a-f]{64}\Z")
                self.assertTrue((REPOSITORY_ROOT / row["path"]).is_file())

    def test_silent_requirements_name_a_poc_campaign(self) -> None:
        self.assertTrue(SILENT_REQUIREMENTS)
        for row in SILENT_REQUIREMENTS:
            self.assertIn(row["campaign_id"], POC_CAMPAIGNS)
            self.assertIn(row["owner"], {"operator_action", "repository_work"})

    def test_the_missing_production_policy_artifacts_really_are_missing(self) -> None:
        # If any of these ever appears, the classification below must change.
        self.assertFalse(
            (REPOSITORY_ROOT / "profiles/measured_runner/production.json").exists()
        )
        candidates = list(
            (REPOSITORY_ROOT / "profiles").rglob("*azure-cpu-composite*")
        )
        self.assertEqual(candidates, [])
        self.assertEqual(
            list(REPOSITORY_ROOT.rglob("verify-azure-cpu-evidence")), []
        )
        missing = {
            pin["location"]
            for pin in REVIEWED_PINS
            if pin["pin_class"] == "repository_work_missing_artifact"
        }
        self.assertEqual(
            missing,
            {
                "$.policies.composite_appraisal.sha256",
                "$.policies.evidence_verifier.sha256",
                "$.policies.runner.sha256",
            },
        )


if __name__ == "__main__":
    unittest.main()
