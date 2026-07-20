# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CLI = REPOSITORY_ROOT / "tools" / "tg_verify.py"


class TernaryGoldbachCliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *arguments],
            cwd=REPOSITORY_ROOT,
            check=False,
            text=True,
            capture_output=True,
        )

    def test_catalog_is_clean_json_with_thirteen_atoms(self) -> None:
        completed = self.run_cli("catalog")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(completed.stdout)
        self.assertEqual(value["atom_count"], 13)
        self.assertEqual(len(value["atoms"]), 13)

    def test_bounded_sample_discloses_scope(self) -> None:
        completed = self.run_cli("sample-arithmetic", "--limit", "100")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(completed.stdout)
        self.assertEqual(
            value["classification"], "bounded_exact_sample_not_full_verification"
        )
        self.assertEqual(value["sample_limit"], 100)
        self.assertIn("mertens-hurst", value["results"])

    def test_missing_artifact_fails_closed(self) -> None:
        completed = self.run_cli("verify-a7", "/definitely/missing.json")
        self.assertEqual(completed.returncode, 2)
        value = json.loads(completed.stdout)
        self.assertFalse(value["accepted"])

    def test_missing_cdem_source_fails_closed(self) -> None:
        completed = self.run_cli("run-cdem-abel", "/definitely/missing")
        self.assertEqual(completed.returncode, 2)
        value = json.loads(completed.stdout)
        self.assertFalse(value["accepted"])

    def test_independent_cdem_chunk_replay_command_is_exposed(self) -> None:
        completed = self.run_cli("replay-cdem-abel-chunks", "--help")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("separately reviewed bounded-memory", completed.stdout)
        self.assertIn("all 1,000 chunks by default", completed.stdout)

    def test_missing_cdem_chunk_transcript_fails_closed(self) -> None:
        completed = self.run_cli(
            "replay-cdem-abel-chunks", "/definitely/missing.txt", "--index", "0"
        )
        self.assertEqual(completed.returncode, 2)
        value = json.loads(completed.stdout)
        self.assertFalse(value["accepted"])

    def test_mobius_receipt_loader_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "duplicate.json"
            receipt.write_text('{"schema_version":1,"schema_version":1}\n')
            completed = self.run_cli("verify-mobius-receipts", str(receipt))
        self.assertEqual(completed.returncode, 2)
        value = json.loads(completed.stdout)
        self.assertFalse(value["accepted"])
        self.assertIn("duplicate JSON key", value["error"])

    def test_full_a7_replay_command_is_exposed(self) -> None:
        completed = self.run_cli("replay-a7-flint", "--help")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("pinned FLINT/Arb", completed.stdout)

    def test_bounded_psi_command_checks_exact_stream(self) -> None:
        completed = self.run_cli("verify-psi-range", "--limit", "1000")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(completed.stdout)
        self.assertEqual(
            value["classification"],
            "bounded_exact_sample_not_full_verification",
        )
        self.assertEqual(value["result"]["events"], 193)
        self.assertFalse(value["result"]["lean_atom_discharged"])

    def test_prop1224_scheduler_reports_semantic_gap(self) -> None:
        completed = self.run_cli("prop1224-scheduler")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(completed.stdout)
        self.assertEqual(value["admissible_q_rows"], 3_389_047_618)
        self.assertTrue(value["bounded_directed_rational_producer_available"])
        self.assertFalse(value["transcendental_window_semantics_verified"])

    def test_prop1224_directed_sample_recomputes_one_complete_window(self) -> None:
        completed = self.run_cli(
            "verify-prop1224-sample",
            "--q",
            "6469693230",
            "--bits",
            "96",
            "--log-terms",
            "32",
            "--max-pairs",
            "1000",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(completed.stdout)
        self.assertEqual(
            value["classification"],
            "bounded_directed_rational_sample_not_full_verification",
        )
        self.assertEqual(value["checked_pairs"], 136)
        self.assertEqual(
            (value["conservative_first_k"], value["conservative_last_k"]),
            (586, 721),
        )
        self.assertTrue(value["endpoint_enclosures_recomputed"])
        self.assertTrue(value["margin_enclosures_recomputed"])
        self.assertTrue(value["exact_gq_recomputed"])
        self.assertFalse(value["native_float_used_in_decisions"])
        self.assertEqual(value["source_q_rows_checked"], 1)
        self.assertEqual(value["source_q_rows_total"], 3_389_047_618)
        self.assertFalse(value["full_source_campaign"])
        self.assertFalse(value["lean_atom_discharged"])

    def test_r2star_command_runs_exact_bounded_reference(self) -> None:
        completed = self.run_cli(
            "verify-r2star-range",
            "--limit",
            "100",
            "--harmonic-terms",
            "1000",
            "--block-size",
            "31",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(completed.stdout)
        self.assertEqual(
            value["classification"], "bounded_exact_sample_not_full_verification"
        )
        self.assertTrue(value["result"]["exact_squared_envelope_verified"])
        self.assertTrue(
            value["result"]["gap_free_hash_and_state_chain_verified"]
        )
        self.assertTrue(value["result"]["exact_factor_support_verified"])
        self.assertFalse(value["result"]["lean_atom_discharged"])


if __name__ == "__main__":
    unittest.main()
