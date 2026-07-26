# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_zero_closure import (  # noqa: E402
    ALGORITHM_ID,
    RESULT_SCHEMA,
    DirichletZeroClosureError,
    capability_report,
    fraction_json,
    make_known_answer_request,
    request_from_campaign,
    validate_request,
    validate_result,
)


def _synthetic_result(request: dict[str, object]) -> dict[str, object]:
    rows = []
    for source in request["characters"]:  # type: ignore[index]
        count = source.get("known_answer_multiplicity_count", 0)
        height = Fraction(
            source["absolute_height"]["numerator"],
            source["absolute_height"]["denominator"],
        )
        rows.append(
            {
                "q": source["q"],
                "conrey_number": source["conrey_number"],
                "parity": source["parity"],
                "absolute_height": source["absolute_height"],
                "stronger_certified_height": fraction_json(height + Fraction(1, 64)),
                "completed_hardy_reconstruction": {},
                "multiplicity_counted_nontrivial_zeros": count,
                "argument_principle": {},
                "zero_isolation": {
                    "strict_sign_change_brackets": count,
                    "bracket_digest_sha256": "0" * 64,
                },
                "exception_handling": {},
                "all_nontrivial_zeros_on_critical_line": True,
            }
        )
    return {
        "kind": RESULT_SCHEMA,
        "schema_version": 1,
        "algorithm_id": ALGORITHM_ID,
        "classification": "test",
        "request_sha256": request["request_sha256"],
        "character_count": request["character_count"],
        "versions": {},
        "characters": rows,
        "completed": True,
        "paper_turing_method_executed": False,
        "external_atom_discharged": False,
    }


class DirichletZeroClosureTests(unittest.TestCase):
    def test_known_answers_cover_q3_q4_q5_and_conjugation(self) -> None:
        request = make_known_answer_request()
        validate_request(request)
        self.assertEqual(request["character_count"], 5)
        self.assertEqual(
            [(row["q"], row["conrey_number"]) for row in request["characters"]],
            [(3, 2), (4, 3), (5, 2), (5, 3), (5, 4)],
        )
        self.assertEqual(request["characters"][2]["conjugate_conrey_number"], 3)
        self.assertEqual(request["characters"][3]["conjugate_conrey_number"], 2)
        self.assertEqual(
            request["source_algorithm"]["upsample_factors"], [1, 8, 32, 128, 512]
        )

    def test_request_self_hash_and_result_count_fail_closed(self) -> None:
        request = make_known_answer_request()
        forged = copy.deepcopy(request)
        forged["configuration"]["maximum_precision_bits"] += 1
        with self.assertRaises(DirichletZeroClosureError):
            validate_request(forged)
        result = _synthetic_result(request)
        validate_result(request, result)
        result["characters"][0]["zero_isolation"][
            "strict_sign_change_brackets"
        ] += 1
        with self.assertRaises(DirichletZeroClosureError):
            validate_result(request, result)

    def test_campaign_adapter_expands_only_the_chunk(self) -> None:
        campaign = {
            "kind": "sparkinterval.tg.dirichlet_campaign.request.v1",
            "character_count": 2,
            "segments": [
                {
                    "q": 5,
                    "character_ordinal_start": 0,
                    "character_ordinal_stop": 2,
                    "absolute_height": fraction_json(Fraction(100_000_000, 5)),
                }
            ],
        }
        request = request_from_campaign(campaign)
        self.assertEqual(request["profile"], "platt_theorem_7_1_source_chunk")
        self.assertEqual(
            [row["conrey_number"] for row in request["characters"]], [2, 4]
        )

    def test_capability_does_not_claim_the_paper_turing_closure(self) -> None:
        report = capability_report()
        self.assertTrue(report["implemented"]["multiplicity_preserving_argument_principle_count"])
        self.assertFalse(report["paper_turing_method_executed"])
        self.assertFalse(report["external_atom_discharged"])
        self.assertIn(
            "Platt Theorem 3.2 conjugate-paired Turing integral and Theorem 3.3/Trudgian bounds",
            report["not_implemented"],
        )

    def test_cli_emits_canonical_known_answer_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "request.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/tg_dirichlet_zero_closure.py",
                    "known-answer-request",
                    str(output),
                ],
                cwd=ROOT,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
            emitted = json.loads(completed.stdout)
            self.assertEqual(emitted["character_count"], 5)
            self.assertEqual(output.read_bytes()[-1:], b"\n")


if __name__ == "__main__":
    unittest.main()
