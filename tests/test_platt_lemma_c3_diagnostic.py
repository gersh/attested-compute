# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audit_platt_lemma_c3_bound",
    ROOT / "tools" / "audit_platt_lemma_c3_bound.py",
)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class PlattLemmaC3DiagnosticTests(unittest.TestCase):
    def test_known_source_targets_and_binary64_direction(self) -> None:
        report = AUDIT.report(
            [10_000_000_000, AUDIT.SOURCE_HEIGHT, AUDIT.PARAMETER_MAXIMUM], 80
        )
        self.assertEqual(report["proof_status"], "diagnostic_only")
        self.assertFalse(
            report["binary64_audit"]["source_decimal_at_least_exact_budget"]
        )
        self.assertTrue(
            report["binary64_audit"]["patched_upward_at_least_exact_budget"]
        )
        bounds = [float(row["bound"]) for row in report["targets"]]
        self.assertGreater(bounds[0], 4.20e-41)
        self.assertLess(bounds[0], 4.21e-41)
        self.assertGreater(bounds[1], 1.35e-40)
        self.assertLess(bounds[1], 1.36e-40)
        self.assertGreater(bounds[2], bounds[1])


if __name__ == "__main__":
    unittest.main()
