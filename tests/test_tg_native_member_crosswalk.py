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

from validate_tg_native_member_crosswalk import (  # noqa: E402
    CrosswalkError,
    load_and_validate,
)


class TernaryGoldbachNativeMemberCrosswalkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_and_validate()

    def _validate_mutation(self, data: dict) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "crosswalk.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            load_and_validate(path)

    def test_exact_member_and_stage_counts(self) -> None:
        summary = self.catalog["summary"]
        self.assertEqual(summary["authoritative_native_members"], 1371)
        self.assertEqual(summary["staged_replacement_target_mapped"], 1371)
        self.assertEqual(summary["without_replacement_target"], 0)
        self.assertEqual(summary["live_provider_integrated"], 0)
        self.assertEqual(summary["fresh_print_retired"], 0)

    def test_pinned_and_current_static_snapshots_are_separate(self) -> None:
        snapshots = self.catalog["snapshots"]
        pinned = snapshots["pinned_static_projection_2026_07_23"]
        current = snapshots["current_static_diagnostic_2026_07_24"]
        self.assertEqual(
            (
                pinned["source_selection_changed_or_removed"],
                pinned["source_selection_unchanged_import_unreachable"],
                pinned["source_selection_unchanged_import_reachable"],
            ),
            (1081, 1, 289),
        )
        self.assertEqual(
            (
                current["source_selection_changed_or_removed"],
                current["source_selection_unchanged_import_unreachable"],
                current["source_selection_unchanged_import_reachable"],
            ),
            (1085, 5, 281),
        )
        self.assertFalse(pinned["member_rows_in_this_crosswalk"])

    def test_member_rows_are_compact_and_do_not_embed_propositions(self) -> None:
        expected = {
            "name",
            "type_digest",
            "family",
            "source_path",
            "origin_declaration",
            "current_static_projection",
            "stage",
            "replacement_evidence_ref",
        }
        self.assertTrue(
            all(set(member) == expected for member in self.catalog["members"])
        )
        self.assertTrue(
            all("proposition" not in member for member in self.catalog["members"])
        )

    def test_mapping_is_only_a_staged_target_location(self) -> None:
        policy = self.catalog["policy"]
        self.assertFalse(policy["mapping_implies_statement_identity"])
        self.assertFalse(policy["mapping_implies_live_integration"])
        self.assertFalse(policy["mapping_implies_retirement"])
        self.assertTrue(
            all(
                evidence["assurance"] == "target_location_only"
                for evidence in self.catalog["replacement_evidence"]
            )
        )

    def test_three_ramare_members_have_the_same_exact_compact_mapping(self) -> None:
        evidence = {
            row["evidence_id"]: row
            for row in self.catalog["replacement_evidence"]
        }
        ramare = [
            member
            for member in self.catalog["members"]
            if member["family"] == "TGNativeCertificates.Ramare"
        ]
        self.assertEqual(len(ramare), 3)
        targets = {
            (
                evidence[member["replacement_evidence_ref"]]["path"],
                evidence[member["replacement_evidence_ref"]]["declaration"],
            )
            for member in ramare
        }
        self.assertEqual(
            targets,
            {
                (
                    "SparkInterval/TernaryGoldbach/"
                    "RamareNativeFoldsCompactChecker.lean",
                    "SparkInterval.TernaryGoldbach."
                    "RamareNativeFoldsCompactChecker."
                    "sourceClaims_of_compactRun",
                )
            },
        )

    def test_six_private_lemma37_roots_are_only_semantic_targets(self) -> None:
        evidence = {
            row["evidence_id"]: row
            for row in self.catalog["replacement_evidence"]
        }
        private_roots = [
            member
            for member in self.catalog["members"]
            if "Lemma37HighQLargeSharpBShape"
            in member["origin_declaration"]
        ]
        self.assertEqual(len(private_roots), 6)
        targets = {
            (
                evidence[member["replacement_evidence_ref"]]["kind"],
                evidence[member["replacement_evidence_ref"]]["path"],
                evidence[member["replacement_evidence_ref"]]["declaration"],
                evidence[member["replacement_evidence_ref"]]["assurance"],
            )
            for member in private_roots
        }
        self.assertEqual(
            targets,
            {
                (
                    "conditional_attested_source_shaped_family_bundle",
                    "Math/Problems/TernaryGoldbach/"
                    "CompactHelfgottAnalyticIntervalsNativeInputs.lean",
                    "Math.Problems.TernaryGoldbach."
                    "CompactHelfgottAnalyticIntervalsNativeInputs."
                    "sourceClaims_of_registeredPhysicalOutcome",
                    "target_location_only",
                )
            },
        )

    def test_seven_bounded_capstone_roots_have_exact_ordinary_contracts(
        self,
    ) -> None:
        evidence = {
            row["evidence_id"]: row
            for row in self.catalog["replacement_evidence"]
        }
        expected = {
            "oddMertensLoAcc_ge": (
                "OddSquarefreeCombinedOrdinaryContract.lean",
                "oddMertensLoAcc_ge_of_certificate",
            ),
            "oddMertensHiAcc_le": (
                "OddSquarefreeCombinedOrdinaryContract.lean",
                "oddMertensHiAcc_le_of_certificate",
            ),
            "gcdMertensHiAcc_le": (
                "OddSquarefreeCombinedOrdinaryContract.lean",
                "gcdMertensHiAcc_le_of_certificate",
            ),
            "phiSqHiAcc_le": (
                "OddSquarefreeCombinedOrdinaryContract.lean",
                "phiSqHiAcc_le_of_certificate",
            ),
            "phiSqDiscHiAcc_le": (
                "OddSquarefreeCombinedOrdinaryContract.lean",
                "phiSqDiscHiAcc_le_of_certificate",
            ),
            "quinticMertensHiAcc_le": (
                "OddSquarefreeCombinedOrdinaryContract.lean",
                "quinticMertensHiAcc_le_of_certificate",
            ),
            "deficitCertAcc_ge": (
                "SingularSeriesDeficitOrdinaryContract.lean",
                "deficitCertAcc_ge_of_certificate",
            ),
        }
        mapped = {
            member["origin_declaration"].rsplit(".", 1)[-1]:
                evidence[member["replacement_evidence_ref"]]
            for member in self.catalog["members"]
            if member["origin_declaration"].rsplit(".", 1)[-1]
            in expected
        }
        self.assertEqual(set(mapped), set(expected))
        for origin_tail, (filename, declaration_tail) in expected.items():
            row = mapped[origin_tail]
            self.assertEqual(
                row["kind"], "exact_ordinary_certificate_contract"
            )
            self.assertEqual(
                row["path"],
                "Math/Problems/TernaryGoldbach/Certs/" + filename,
            )
            self.assertEqual(
                row["declaration"].rsplit(".", 1)[-1],
                declaration_tail,
            )

    def test_validator_rejects_fresh_retirement_without_fresh_print(self) -> None:
        altered = copy.deepcopy(self.catalog)
        altered["members"][0]["stage"] = "fresh_print_retired"
        with self.assertRaises(CrosswalkError):
            self._validate_mutation(altered)

    def test_validator_rejects_mapping_without_evidence(self) -> None:
        altered = copy.deepcopy(self.catalog)
        mapped = next(
            member
            for member in altered["members"]
            if member["stage"] == "staged_replacement_target_mapped"
        )
        mapped["replacement_evidence_ref"] = None
        with self.assertRaises(CrosswalkError):
            self._validate_mutation(altered)


if __name__ == "__main__":
    unittest.main()
