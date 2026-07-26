# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import tg_verify as tg_verify_cli


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
        completed = self.run_cli("sample-arithmetic", "--limit", "64")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(completed.stdout)
        self.assertEqual(
            value["classification"], "bounded_exact_sample_not_full_verification"
        )
        self.assertEqual(value["sample_limit"], 64)
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
        self.assertIn("--registered-result-output", completed.stdout)

    def test_a7_registered_result_writer_is_exact_and_exclusive(self) -> None:
        report = {
            "accepted": True,
            "artifact_kind": "ch25_a7_boundary",
            "verification_class": "complete_external_flint_arb_leaf_replay",
            "artifact_sha256": tg_verify_cli._A7_RETAINED_ARTIFACT_SHA256,
            "artifact_bytes_match_pinned_sha256": True,
            "python_flint_version": "0.9.0",
            "flint_version": "3.6.0",
            "flint_release": 30_600,
            "leaf_count": 16_191,
            "four_edge_dyadic_cover_verified": True,
            "every_leaf_flint_box_recomputed": True,
            "every_exact_leaf_endpoint_matched": True,
            "all_denominator_and_zeta_nonvanishing_guards_checked": True,
            "strict_norm_square_bound_verified_under_flint_semantics": True,
            "external_analytic_verification_complete": True,
            "ordinary_kernel_lean_proof": False,
            "mathlib_zeta_realization_theorem_present": False,
            "lean_atom_discharged": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested/registered-result.txt"
            metadata = tg_verify_cli._write_a7_registered_result(report, output)
            self.assertEqual(output.read_bytes(), b"true")
            self.assertEqual(
                metadata,
                {
                    "path": str(output.resolve()),
                    "sha256": (
                        "b5bea41b6c623f7c09f1bf24dcae58e"
                        "bab3c0cdd90ad966bc43a45b44867e12b"
                    ),
                    "bytes": 4,
                    "format": "literal_ascii_true_no_newline_v1",
                },
            )
            with self.assertRaisesRegex(
                tg_verify_cli.EvidenceError, "refusing to overwrite"
            ):
                tg_verify_cli._write_a7_registered_result(report, output)

            attacker = dict(report)
            attacker["artifact_bytes_match_pinned_sha256"] = False
            with self.assertRaisesRegex(
                tg_verify_cli.EvidenceError, "closed registered invocation"
            ):
                tg_verify_cli._write_a7_registered_result(
                    attacker, Path(directory) / "attacker.txt"
                )

    def test_bounded_psi_command_checks_exact_stream(self) -> None:
        completed = self.run_cli("verify-psi-range", "--limit", "64")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(completed.stdout)
        self.assertEqual(
            value["classification"],
            "bounded_exact_sample_not_full_verification",
        )
        self.assertEqual(value["result"]["events"], 27)
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
            "100000",
            "--bits",
            "64",
            "--log-terms",
            "32",
            "--max-pairs",
            "64",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(completed.stdout)
        self.assertEqual(
            value["classification"],
            "bounded_directed_rational_sample_not_full_verification",
        )
        self.assertEqual(value["checked_pairs"], 37)
        self.assertEqual(
            (value["conservative_first_k"], value["conservative_last_k"]),
            (1, 37),
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
            "64",
            "--harmonic-terms",
            "64",
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
