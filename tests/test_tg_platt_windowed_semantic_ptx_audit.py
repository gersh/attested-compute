# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUDITOR = ROOT / "gpu/platform/h100/h100_tg_platt_windowed_semantic_ptx_audit.py"
SPEC = importlib.util.spec_from_file_location("platt_semantic_ptx_audit", AUDITOR)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PlattWindowedSemanticPtxAuditTest(unittest.TestCase):
    def test_accepts_only_symmetric_directed_arithmetic(self) -> None:
        report = MODULE.audit_text(
            "\n".join(
                (
                    "add.rm.f64 %a, %b, %c;",
                    "add.rp.f64 %d, %e, %f;",
                    "sub.rm.f64 %a, %b, %c;",
                    "sub.rp.f64 %d, %e, %f;",
                    "mul.rm.f64 %a, %b, %c;",
                    "mul.rp.f64 %d, %e, %f;",
                    "min.f64 %a, %b, %c;",
                    "max.f64 %a, %b, %c;",
                    "ld.global.f64 %a, [%rd1];",
                    "st.global.f64 [%rd1], %a;",
                )
            )
        )
        self.assertTrue(report["passed"])
        self.assertEqual(report["forbidden_f64_opcodes"], {})

    def test_rejects_nearest_division_fma_and_asymmetry(self) -> None:
        report = MODULE.audit_text(
            "\n".join(
                (
                    "add.rn.f64 %a, %b, %c;",
                    "sub.rm.f64 %a, %b, %c;",
                    "mul.rm.f64 %a, %b, %c;",
                    "mul.rp.f64 %d, %e, %f;",
                    "div.rn.f64 %a, %b, %c;",
                    "fma.rn.f64 %a, %b, %c, %d;",
                )
            )
        )
        self.assertFalse(report["passed"])
        self.assertIn("add.rn.f64", report["unexpected_f64_opcodes"])
        self.assertIn("div.rn.f64", report["forbidden_f64_opcodes"])
        self.assertIn("fma.rn.f64", report["forbidden_f64_opcodes"])
        self.assertIn("add", report["asymmetric_or_missing_directed_pairs"])
        self.assertIn("sub", report["asymmetric_or_missing_directed_pairs"])


if __name__ == "__main__":
    unittest.main()
