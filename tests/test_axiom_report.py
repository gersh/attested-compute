from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "check_axiom_report.py"
SPEC = importlib.util.spec_from_file_location("check_axiom_report", SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
check_axiom_report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_axiom_report)


class AxiomReportTests(unittest.TestCase):
    def test_parses_wrapped_and_empty_reports(self) -> None:
        reports = check_axiom_report.parse_reports(
            """
'First' depends on axioms: [propext,
 Classical.choice,
 Quot.sound]
'Second' does not depend on any axioms
"""
        )
        self.assertEqual(
            reports,
            [{"propext", "Classical.choice", "Quot.sound"}, set()],
        )

    def test_exposes_unexpected_dependency_to_caller(self) -> None:
        reports = check_axiom_report.parse_reports(
            "'Theorem' depends on axioms: [native_decide]"
        )
        self.assertEqual(reports, [{"native_decide"}])


if __name__ == "__main__":
    unittest.main()
