# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed tests for the exact external-campaign completion contract."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.validate_tg_external_completion import (  # noqa: E402
    CompletionAuditError,
    validate_completion_audit,
)


AUDIT = (
    ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_EXTERNAL_COMPLETION_AUDIT.json"
)
CLAUDE_MATH = ROOT.parent / "claude_math"


class ExternalCompletionAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = json.loads(AUDIT.read_text(encoding="utf-8"))

    def _write_changed(self, value: object) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "audit.json"
        path.write_text(
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return path

    def test_authoritative_audit_validates_against_live_source(self) -> None:
        result = validate_completion_audit(
            AUDIT,
            claude_math_root=CLAUDE_MATH if CLAUDE_MATH.is_dir() else None,
            require_claude_math=CLAUDE_MATH.is_dir(),
        )
        self.assertEqual(result["campaign_count"], 10)
        self.assertEqual(result["logical_atom_count"], 13)
        self.assertEqual(result["campaigns_complete"], 0)

    def test_cli_validator_is_green(self) -> None:
        command = [
            sys.executable,
            str(ROOT / "tools" / "validate_tg_external_completion.py"),
        ]
        if CLAUDE_MATH.is_dir():
            command.extend(
                [
                    "--claude-math-root",
                    str(CLAUDE_MATH),
                    "--require-claude-math",
                ]
            )
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["campaigns_complete"], 0)

    def test_only_cdem_has_complete_lean_artifact_chain(self) -> None:
        rows = self.audit["campaigns"]
        for gate in (
            "complete_source_artifact",
            "lean_parser",
            "lean_total_checker",
            "lean_soundness",
        ):
            complete = [
                row["campaign_id"]
                for row in rows
                if row["gates"][gate]["satisfied"]
            ]
            self.assertEqual(complete, ["cdem-table-abel"])

    def test_no_projection_is_promoted_to_target_measurement(self) -> None:
        for row in self.audit["campaigns"]:
            gate = row["gates"]["target_sku_budget_gate"]
            self.assertFalse(gate["target_sku_measured"])
            self.assertFalse(gate["satisfied"])
            self.assertIsNone(gate["target_measured_wall_hours_high"])
            self.assertIsNone(gate["target_measured_cost_usd_high"])

    def test_target_measurement_tampering_fails_crosscheck(self) -> None:
        changed = copy.deepcopy(self.audit)
        gate = changed["campaigns"][0]["gates"]["target_sku_budget_gate"]
        gate["target_sku_measured"] = True
        gate["target_measured_wall_hours_high"] = "1"
        gate["target_measured_cost_usd_high"] = "1"
        gate["satisfied"] = True
        changed["summary"]["satisfied_gate_counts"][
            "target_sku_budget_gate"
        ] = 1
        with self.assertRaisesRegex(
            CompletionAuditError, "target-SKU measurement flag differs"
        ):
            validate_completion_audit(self._write_changed(changed))

    def test_production_integration_requires_a_receipt(self) -> None:
        changed = copy.deepcopy(self.audit)
        gate = changed["campaigns"][0]["gates"][
            "claude_math_production_integration"
        ]
        gate["satisfied"] = True
        changed["summary"]["satisfied_gate_counts"][
            "claude_math_production_integration"
        ] = 1
        with self.assertRaisesRegex(
            CompletionAuditError,
            "production integration without a receipt",
        ):
            validate_completion_audit(self._write_changed(changed))

    def test_cdem_architecture_to_source_bridge_is_explicit(self) -> None:
        source = (
            ROOT
            / "SparkInterval"
            / "TernaryGoldbach"
            / "CDEMAbelArtifactProgram.lean"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "theorem sourceClaim_of_opaqueNativeAcceptance", source
        )
        self.assertIn(
            "exact sourceClaim_of_artifact_acceptance sourceAccepted", source
        )


if __name__ == "__main__":
    unittest.main()
