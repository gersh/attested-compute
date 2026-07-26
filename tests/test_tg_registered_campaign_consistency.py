# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for the bounded TG registered-campaign identity audit."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import audit_tg_registered_campaigns as audit  # noqa: E402


class TGRegisteredCampaignConsistencyTests(unittest.TestCase):
    def test_all_eleven_terminal_registration_chains_match(self) -> None:
        report = audit.build_report()
        self.assertEqual(
            report["summary"],
            {
                "named_physical_campaigns": 10,
                "named_physical_terminal_result_contracts": 10,
                "all_named_physical_terminal_result_contracts_reviewed": True,
                "lowered_goldbach_alternates": 1,
                "semantic_bindings_enabled": 1,
                "semantic_bindings_staged_disabled": 10,
                "semantic_bindings_null_disabled": 0,
                "mismatch_count": 0,
                "all_registration_layers_consistent": True,
                "analytic_realizations_established": 0,
                "production_runs_established": 0,
            },
        )
        self.assertEqual(report["global_mismatches"], [])
        self.assertTrue(
            all(row["status"] == "consistent" for row in report["campaigns"])
        )
        self.assertTrue(
            all(
                row["analytic_realization_claimed_by_this_report"] is False
                for row in report["campaigns"]
            )
        )

    def test_disabled_semantic_binding_cannot_be_enabled_silently(self) -> None:
        semantic = json.loads(
            audit.SEMANTIC_BINDINGS.read_text(encoding="utf-8")
        )
        row = next(
            item
            for item in semantic["bindings"]
            if item["campaign_id"] == "ch25-a7-boundary"
        )
        row["enabled"] = True
        with tempfile.TemporaryDirectory(
            prefix=".tg-registered-audit-", dir=ROOT
        ) as temporary:
            path = Path(temporary) / "semantic-bindings.json"
            path.write_text(
                json.dumps(semantic, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            report = audit.build_report(semantic_bindings_path=path)
        a7 = next(
            item
            for item in report["campaigns"]
            if item["campaign_id"] == "ch25-a7-boundary"
        )
        self.assertEqual(a7["status"], "mismatch")
        self.assertIn(
            {
                "layer": "semantic_binding_inventory",
                "check": "state",
                "expected": "staged_disabled",
                "actual": "enabled",
            },
            a7["mismatches"],
        )

    def test_cli_check_is_machine_readable_and_clean(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOLS / "audit_tg_registered_campaigns.py"),
                "--check",
            ],
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        report = json.loads(completed.stdout)
        self.assertEqual(report["summary"]["mismatch_count"], 0)
        self.assertTrue(report["summary"]["all_registration_layers_consistent"])


if __name__ == "__main__":
    unittest.main()
