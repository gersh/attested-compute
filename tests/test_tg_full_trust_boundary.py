# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.audit_tg_full_trust_boundary import (
    DEFAULT_SPECIFICATION,
    FullTrustBoundaryError,
    REPOSITORY_ROOT,
    audit,
)


CLAUDE_MATH_ROOT = Path(
    os.environ.get("CLAUDE_MATH_ROOT", REPOSITORY_ROOT.parent / "claude_math")
)


class FullTrustBoundaryTest(unittest.TestCase):
    def test_checked_in_catalog_partition(self) -> None:
        summary = audit()
        self.assertEqual(summary["total_roots"], 1387)
        self.assertEqual(summary["foundations"], 3)
        self.assertEqual(summary["named_external_or_source"], 13)
        self.assertEqual(summary["native_generated"], 1371)
        self.assertEqual(summary["native_families"], 15)
        self.assertEqual(summary["native_members_statused"], 1371)
        self.assertEqual(summary["native_members_target_mapped"], 1371)
        self.assertEqual(summary["native_members_unmapped"], 0)
        self.assertEqual(
            summary["native_roots_with_aggregate_invocation_route"], 1371
        )
        self.assertEqual(
            summary["native_source_decisions_with_aggregate_invocation_route"],
            1214,
        )
        self.assertEqual(summary["native_aggregate_physical_campaigns"], 1)
        self.assertEqual(summary["native_aggregate_fixed_checker_bundles"], 15)
        self.assertEqual(summary["native_aggregate_fixed_checker_roots"], 1371)
        self.assertEqual(
            summary[
                "physical_campaigns_with_deterministic_program_obligation"
            ],
            12,
        )
        self.assertEqual(
            summary["closed_source_program_audited_campaigns"], 11
        )
        self.assertEqual(summary["closed_source_program_required_gaps"], 10)
        self.assertEqual(
            summary["closed_source_program_concrete_campaigns"], 1
        )
        self.assertEqual(
            summary["native_aggregate_source_program_catalogued"], 1
        )
        self.assertEqual(
            summary["native_aggregate_static_cpu_compilations"], 0
        )
        self.assertEqual(
            summary["physical_campaigns_with_concrete_program_certificate"],
            1,
        )
        self.assertEqual(summary["proof_authorizing_campaigns"], 11)
        self.assertEqual(summary["closed_receipt_slots"], 11)
        self.assertEqual(summary["imported_receipts"], 0)
        self.assertEqual(summary["accepted_receipts"], 0)
        self.assertEqual(
            summary["external_roots_registered_physical_mapped"], 13
        )
        self.assertEqual(summary["external_physical_campaigns"], 10)
        self.assertFalse(summary["authoritative_snapshot_checked"])

    def test_pinned_authoritative_snapshot_when_available(self) -> None:
        trace = (
            CLAUDE_MATH_ROOT
            / ".lake/build/lib/lean/Math/Problems/TernaryGoldbach/Statement.trace"
        )
        if not trace.is_file():
            self.skipTest("pinned claude_math Statement.trace is unavailable")
        summary = audit(claude_math_root=CLAUDE_MATH_ROOT)
        self.assertTrue(summary["authoritative_snapshot_checked"])
        self.assertTrue(
            summary["downstream_aggregate_source_program_checked"]
        )

    def test_weakened_no_replay_policy_fails(self) -> None:
        document = json.loads(DEFAULT_SPECIFICATION.read_text(encoding="utf-8"))
        document["policy"][
            "routine_local_build_may_replay_production_computation"
        ] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                FullTrustBoundaryError, "policy.*was widened"
            ):
                audit(path)

    def test_aggregate_route_cannot_be_claimed_as_mathematics(self) -> None:
        document = json.loads(DEFAULT_SPECIFICATION.read_text(encoding="utf-8"))
        document["policy"][
            "aggregate_invocation_alone_implies_a_mathematical_claim"
        ] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                FullTrustBoundaryError, "policy.*was widened"
            ):
                audit(path)

    def test_inner_boolean_cannot_be_claimed_as_concrete_program(self) -> None:
        document = json.loads(DEFAULT_SPECIFICATION.read_text(encoding="utf-8"))
        document["policy"][
            "inner_boolean_kernel_alone_counts_as_a_concrete_program"
        ] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                FullTrustBoundaryError, "policy.*was widened"
            ):
                audit(path)

    def test_closed_source_program_roster_must_be_exact(self) -> None:
        document = json.loads(DEFAULT_SPECIFICATION.read_text(encoding="utf-8"))
        catalog_path = (
            REPOSITORY_ROOT
            / document["local_catalogs"]["closed_source_program_catalog"]
        )
        catalog = catalog_path.read_text(encoding="utf-8")
        catalog = catalog.replace(
            ".plattDirichletTheorem71, .ramareProductionFolds]",
            ".plattDirichletTheorem71]",
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad_catalog = root / "BadClosedSourceProgramCatalog.lean"
            bad_catalog.write_text(catalog, encoding="utf-8")
            document["local_catalogs"][
                "closed_source_program_catalog"
            ] = str(bad_catalog)
            path = root / "bad-full-boundary.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                FullTrustBoundaryError,
                "exact ordered eleven-campaign roster",
            ):
                audit(path)

    def test_closed_source_program_concrete_count_stays_one(self) -> None:
        document = json.loads(DEFAULT_SPECIFICATION.read_text(encoding="utf-8"))
        document["program_boundary"][
            "closed_catalog_concrete_program_count"
        ] = 0
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                FullTrustBoundaryError,
                "concrete count must remain exactly one",
            ):
                audit(path)

    def test_complete_cdem_artifact_program_cannot_be_substituted(self) -> None:
        document = json.loads(DEFAULT_SPECIFICATION.read_text(encoding="utf-8"))
        catalog_path = (
            REPOSITORY_ROOT
            / document["local_catalogs"]["closed_source_program_catalog"]
        )
        catalog = catalog_path.read_text(encoding="utf-8").replace(
            "| .cdemTableAbel => .artifactConcrete cdemAbelConcrete",
            "| .cdemTableAbel => .missing a7Missing",
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad_catalog = root / "BadClosedSourceProgramCatalog.lean"
            bad_catalog.write_text(catalog, encoding="utf-8")
            document["local_catalogs"][
                "closed_source_program_catalog"
            ] = str(bad_catalog)
            path = root / "bad-full-boundary.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                FullTrustBoundaryError,
                "exactly one complete CDEM artifact program",
            ):
                audit(path)

    def test_aggregate_source_program_is_not_source_compilation(self) -> None:
        document = json.loads(DEFAULT_SPECIFICATION.read_text(encoding="utf-8"))
        document["program_boundary"]["downstream_native_aggregate"][
            "static_cpu_compilation_present"
        ] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                FullTrustBoundaryError,
                "advanced without compiler evidence",
            ):
                audit(path)

    def test_closed_receipt_roster_must_be_exact(self) -> None:
        document = json.loads(DEFAULT_SPECIFICATION.read_text(encoding="utf-8"))
        roster_path = (
            REPOSITORY_ROOT
            / document["local_catalogs"]["closed_accepted_receipt_roster"]
        )
        roster = roster_path.read_text(encoding="utf-8")
        roster = roster.replace(
            "  nativeGeneratedAggregate :\n"
            "    ImportedOutcome .nativeGeneratedAggregateProductionV1\n",
            "",
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad_roster = root / "BadClosedAcceptedReceiptRoster.lean"
            bad_roster.write_text(roster, encoding="utf-8")
            document["local_catalogs"][
                "closed_accepted_receipt_roster"
            ] = str(bad_roster)
            path = root / "bad-full-boundary.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                FullTrustBoundaryError,
                "exact ordered eleven-campaign roster",
            ):
                audit(path)

    def test_closed_receipt_projection_is_required(self) -> None:
        document = json.loads(DEFAULT_SPECIFICATION.read_text(encoding="utf-8"))
        roster_path = (
            REPOSITORY_ROOT
            / document["local_catalogs"]["closed_accepted_receipt_roster"]
        )
        roster = roster_path.read_text(encoding="utf-8")
        roster = roster.replace(
            "theorem nativeAggregatePhysicalOutcome",
            "theorem renamedNativeAggregatePhysicalOutcome",
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad_roster = root / "BadClosedAcceptedReceiptRoster.lean"
            bad_roster.write_text(roster, encoding="utf-8")
            document["local_catalogs"][
                "closed_accepted_receipt_roster"
            ] = str(bad_roster)
            path = root / "bad-full-boundary.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                FullTrustBoundaryError,
                "nativeAggregatePhysicalOutcome theorem",
            ):
                audit(path)

    def test_current_closed_receipt_roster_must_be_uninhabited(self) -> None:
        document = json.loads(DEFAULT_SPECIFICATION.read_text(encoding="utf-8"))
        roster_path = (
            REPOSITORY_ROOT
            / document["local_catalogs"]["closed_accepted_receipt_roster"]
        )
        roster = roster_path.read_text(encoding="utf-8")
        roster = roster.replace(
            "theorem no_current_requiredRoster",
            "theorem renamed_no_current_requiredRoster",
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad_roster = root / "BadClosedAcceptedReceiptRoster.lean"
            bad_roster.write_text(roster, encoding="utf-8")
            document["local_catalogs"][
                "closed_accepted_receipt_roster"
            ] = str(bad_roster)
            path = root / "bad-full-boundary.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                FullTrustBoundaryError,
                "no_current_requiredRoster theorem",
            ):
                audit(path)

    def test_closed_receipt_counts_cannot_claim_acceptance(self) -> None:
        document = json.loads(DEFAULT_SPECIFICATION.read_text(encoding="utf-8"))
        document["receipt_boundary"]["accepted_receipt_count"] = 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                FullTrustBoundaryError,
                "accepted_receipt_count cannot advance",
            ):
                audit(path)

    def test_missing_registered_physical_mapping_fails(self) -> None:
        document = json.loads(DEFAULT_SPECIFICATION.read_text(encoding="utf-8"))
        bridge_path = (
            REPOSITORY_ROOT
            / document["local_catalogs"]["external_bridge_status"]
        )
        bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
        bridge["atoms"][0]["stages"][
            "registered_physical_outcome_mapped"
        ] = False
        bridge["summary"]["registered_physical_outcome_mapped"] = 12
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad_bridge = root / "bad-bridge.json"
            bad_bridge.write_text(json.dumps(bridge), encoding="utf-8")
            document["local_catalogs"][
                "external_bridge_status"
            ] = str(bad_bridge)
            path = root / "bad-full-boundary.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                FullTrustBoundaryError,
                "registered_physical_outcome_mapped.*incomplete",
            ):
                audit(path)


if __name__ == "__main__":
    unittest.main()
