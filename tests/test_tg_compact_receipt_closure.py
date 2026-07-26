# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/tg-compact-receipt-closure.schema.json"
MANIFEST = (
    ROOT
    / "specifications"
    / "TERNARY_GOLDBACH_COMPACT_RECEIPT_CLOSURE.json"
)
CLI = ROOT / "tools/audit_tg_compact_receipt_closure.py"

from tg_verifier.compact_receipt_closure import (  # noqa: E402
    CompactReceiptClosureError,
    load_and_validate_closure,
    validate_closure_document,
)

try:
    import jsonschema
except ImportError:  # pragma: no cover - optional developer dependency
    jsonschema = None


class CompactReceiptClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = load_and_validate_closure()

    def test_schema_and_static_cross_layer_audit(self) -> None:
        self.assertEqual(len(self.document["claims"]), 14)
        self.assertEqual(len(self.document["campaigns"]), 11)
        if jsonschema is not None:
            schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.Draft202012Validator(schema).validate(self.document)

    def test_hurst_is_exactly_one_campaign_for_four_claims(self) -> None:
        hurst = next(
            row
            for row in self.document["campaigns"]
            if row["campaign_id"] == "hurst-four-residuals-v1"
        )
        self.assertEqual(
            hurst["logical_claim_ids"],
            [
                "cdem-squarefree",
                "mertens-hurst",
                "platt-little-mertens-2-11",
                "platt-little-mertens-stronger",
            ],
        )

    def test_no_campaign_overclaims_current_receipt_authority(self) -> None:
        for campaign in self.document["campaigns"]:
            with self.subTest(campaign=campaign["campaign_id"]):
                self.assertFalse(
                    campaign["machine_refinement"][
                        "exact_executable_refinement"
                    ]
                )
                self.assertIsNone(
                    campaign["lean_soundness"][
                        "native_bytes_to_evidence_theorem"
                    ]
                )
                self.assertFalse(
                    campaign["receipt_closure"][
                        "can_one_receipt_yield_claim_now"
                    ]
                )
                self.assertIsInstance(
                    campaign["receipt_closure"]["per_campaign_adapter"],
                    str,
                )

    def test_manual_dags_require_transitive_execution_closure(self) -> None:
        for campaign in self.document["campaigns"]:
            if campaign["execution_mode"] != "manual_phase_dag":
                continue
            with self.subTest(campaign=campaign["campaign_id"]):
                closure = campaign["receipt_closure"]
                self.assertEqual(
                    closure["receipt_scope"], "transitive_campaign_graph"
                )
                self.assertFalse(
                    closure["one_ordinary_process_receipt_sufficient"]
                )
                self.assertIn(
                    "transitive_child_execution_closure",
                    closure["missing_proofs"],
                )

    def test_identity_substitution_is_rejected(self) -> None:
        changed = deepcopy(self.document)
        changed["campaigns"][0]["registered_identity"]["algorithm_hash"] = "0" * 64
        with self.assertRaisesRegex(
            CompactReceiptClosureError, "algorithm_hash differs"
        ):
            validate_closure_document(changed, repository_root=ROOT)

    def test_result_substitution_is_rejected(self) -> None:
        changed = deepcopy(self.document)
        changed["campaigns"][0]["registered_identity"]["success_result"][
            "bytes_utf8"
        ] = "false"
        with self.assertRaisesRegex(
            CompactReceiptClosureError, "result pin differs"
        ):
            validate_closure_document(changed, repository_root=ROOT)

    def test_machine_refinement_overclaim_is_rejected(self) -> None:
        changed = deepcopy(self.document)
        changed["campaigns"][0]["machine_refinement"][
            "exact_executable_refinement"
        ] = True
        with self.assertRaisesRegex(
            CompactReceiptClosureError, "overclaims exact executable"
        ):
            validate_closure_document(changed, repository_root=ROOT)

    def test_dag_cannot_be_collapsed_to_one_ordinary_receipt(self) -> None:
        changed = deepcopy(self.document)
        psi = next(
            row
            for row in changed["campaigns"]
            if row["campaign_id"] == "ch25-psi-two-pass-v1"
        )
        psi["receipt_closure"]["one_ordinary_process_receipt_sufficient"] = True
        with self.assertRaisesRegex(
            CompactReceiptClosureError,
            "cannot use one ordinary process receipt",
        ):
            validate_closure_document(changed, repository_root=ROOT)

    def test_cli_is_static_and_reports_exact_scope(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(CLI), "--json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["claims"], 14)
        self.assertEqual(result["campaigns"], 11)
        self.assertEqual(result["exact_executable_refinements"], 0)
        self.assertEqual(result["one_receipt_claim_authorities"], 0)


if __name__ == "__main__":
    unittest.main()
