# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from validate_tg_native_family_closure import (  # noqa: E402
    CatalogError,
    load_and_validate,
    validate_against_authoritative_manifest,
    validate_projection_document_pin,
)


class TernaryGoldbachNativeFamilyClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_and_validate()

    def _validate_mutation(self, data: dict) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "catalog.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            load_and_validate(path)

    def test_authoritative_and_projection_counts_are_distinct(self) -> None:
        fresh = self.catalog["snapshots"]["last_fresh_capstone"]
        projection = self.catalog["snapshots"][
            "recorded_static_projection_2026_07_23"
        ]
        self.assertEqual(fresh["native_generated_atoms"], 1371)
        self.assertEqual(projection["source_selection_unchanged_import_reachable"], 289)
        self.assertEqual(projection["status"], "static_projection_not_authoritative")
        self.assertFalse(fresh["raw_statement_trace_vendored_here"])

    def test_all_families_remain_fail_closed(self) -> None:
        self.assertEqual(len(self.catalog["families"]), 15)
        self.assertTrue(
            all(
                not row["authoritative_retirement_proven"]
                for row in self.catalog["families"]
            )
        )
        self.assertEqual(
            self.catalog["summary"][
                "families_authoritatively_retired_by_a_fresh_capstone_print"
            ],
            0,
        )

    def test_compact_fallback_is_only_the_prohibitive_ramare_family(self) -> None:
        compact = [
            row
            for row in self.catalog["families"]
            if row["preferred_discharge"]["mode"] == "compact_trusted_run"
        ]
        self.assertEqual(
            [row["lean_family"] for row in compact],
            ["TGNativeCertificates.Ramare"],
        )
        self.assertEqual(
            sum(row["authoritative_snapshot"]["native_atom_count"] for row in compact),
            3,
        )

    def test_ramare_compact_contract_is_separate_and_fail_closed(self) -> None:
        ramare = next(
            row
            for row in self.catalog["families"]
            if row["lean_family"] == "TGNativeCertificates.Ramare"
        )
        contract = ramare["compact_contract"]
        self.assertEqual(
            contract["registry_invocation"],
            "ramareProductionFoldsCompactV1",
        )
        self.assertEqual(contract["claim_kind"], "native_family_fallback")
        self.assertFalse(contract["external_atom_campaign"])
        self.assertFalse(contract["reviewed_run_installed"])
        self.assertFalse(contract["exact_executable_refinement_proved"])
        self.assertFalse(
            contract["exact_claude_math_provider_replacement_proved"]
        )
        self.assertEqual(len(contract["historical_boolean_leaves"]), 3)

    def test_validator_rejects_promoting_289_to_authority(self) -> None:
        altered = copy.deepcopy(self.catalog)
        altered["snapshots"]["recorded_static_projection_2026_07_23"][
            "status"
        ] = "authoritative"
        with self.assertRaises(CatalogError):
            self._validate_mutation(altered)

    def test_validator_rejects_unjustified_compact_fallback(self) -> None:
        altered = copy.deepcopy(self.catalog)
        row = next(
            row
            for row in altered["families"]
            if row["lean_family"] == "AnalyticNT.Chebyshev"
        )
        row["preferred_discharge"].update(
            {
                "mode": "compact_trusted_run",
                "compact_trusted_run_allowed": True,
                "prohibitive_reason": (
                    "This deliberately long fake explanation attempts to move a "
                    "small local family across the trusted-run boundary without "
                    "evidence."
                ),
            }
        )
        with self.assertRaises(CatalogError):
            self._validate_mutation(altered)

    def test_validator_rejects_claimed_retirement(self) -> None:
        altered = copy.deepcopy(self.catalog)
        altered["families"][0]["authoritative_retirement_proven"] = True
        with self.assertRaises(CatalogError):
            self._validate_mutation(altered)

    def test_optional_snapshot_checks_fail_closed_on_wrong_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wrong = Path(temporary) / "wrong.json"
            wrong.write_text("{}", encoding="utf-8")
            with self.assertRaises(CatalogError):
                validate_against_authoritative_manifest(self.catalog, wrong)
            with self.assertRaises(CatalogError):
                validate_projection_document_pin(self.catalog, wrong)


if __name__ == "__main__":
    unittest.main()
