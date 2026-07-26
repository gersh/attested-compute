# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.validate_tg_native_architecture_bridge_status import (
    DEFAULT_STATUS,
    NativeArchitectureStatusError,
    REPOSITORY_ROOT,
    load_and_validate,
)


CLAUDE_MATH_ROOT = REPOSITORY_ROOT.parent / "claude_math"


class NativeArchitectureBridgeStatusTest(unittest.TestCase):
    def test_complete_closed_routing(self) -> None:
        status = load_and_validate(claude_math_root=CLAUDE_MATH_ROOT)
        summary = status["summary"]
        self.assertEqual(summary["family_count"], 15)
        self.assertEqual(summary["generated_roots"], 1371)
        self.assertEqual(summary["source_decisions"], 1214)
        self.assertEqual(summary["aggregate_invocation_mapped_families"], 15)
        self.assertEqual(summary["aggregate_invocation_mapped_roots"], 1371)
        self.assertEqual(
            summary["exact_fixed_checker_bundle_mapped_families"], 15
        )
        self.assertEqual(
            summary["exact_fixed_checker_bundle_mapped_roots"], 1371
        )
        self.assertEqual(
            summary["exact_fixed_checker_bundle_mapped_source_decisions"],
            1214,
        )
        self.assertEqual(summary["exact_executable_refinement_present"], 0)
        self.assertEqual(summary["reviewed_receipt_present"], 0)
        families = {
            row["family_id"]: row["aggregate_adapter"]
            for row in status["families"]
        }
        self.assertEqual(
            families["helfgott-analytic-intervals"]["claim_bundle_path"],
            "Math/Problems/TernaryGoldbach/"
            "CompactHelfgottAnalyticIntervalsNativeSourceClaims.lean",
        )
        self.assertEqual(
            families["rosser-schoenfeld"]["claim_bundle_path"],
            "Math/Problems/TernaryGoldbach/"
            "CompactRS62NativeSourceClaims.lean",
        )

    def test_missing_family_route_fails(self) -> None:
        document = json.loads(DEFAULT_STATUS.read_text(encoding="utf-8"))
        document["families"][0]["stages"][
            "aggregate_invocation_mapped"
        ] = False
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                NativeArchitectureStatusError, "aggregate route is missing"
            ):
                load_and_validate(path)

    def test_unproved_receipt_fails_closed(self) -> None:
        document = json.loads(DEFAULT_STATUS.read_text(encoding="utf-8"))
        document["families"][0]["stages"]["reviewed_receipt_present"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                NativeArchitectureStatusError,
                "reviewed_receipt_present advanced",
            ):
                load_and_validate(path)


if __name__ == "__main__":
    unittest.main()
