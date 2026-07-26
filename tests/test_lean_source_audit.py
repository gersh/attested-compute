# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import audit_lean_source as audit  # noqa: E402


class LeanSourceAuditTests(unittest.TestCase):
    def declarations(self, source: str) -> list[tuple[str, str]]:
        stripped = audit.strip_comments_and_strings(source)
        return [match.groups() for match in audit.TRUST_DECLARATION.finditer(stripped)]

    def test_axiom_and_constant_are_both_trust_declarations(self) -> None:
        self.assertEqual(
            self.declarations("axiom accepted : True\nconstant hidden : False\n"),
            [("axiom", "accepted"), ("constant", "hidden")],
        )

    def test_comments_and_strings_do_not_create_false_positives(self) -> None:
        self.assertEqual(
            self.declarations(
                '/- constant commented : False -/\n'
                'def text := "axiom quoted : False"\n'
                '-- axiom lineCommented : False\n'
            ),
            [],
        )

    def test_native_decide_is_detected_only_as_code(self) -> None:
        source = (
            "example : True := by native_decide\n"
            '/- native_decide -/\n'
            'def text := "native_decide"\n'
        )
        stripped = audit.strip_comments_and_strings(source)
        self.assertEqual(
            [match.group(0) for match in audit.NATIVE_DECIDE.finditer(stripped)],
            ["native_decide"],
        )


if __name__ == "__main__":
    unittest.main()
