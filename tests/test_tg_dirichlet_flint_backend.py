# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools import tg_dirichlet_flint_backend as backend  # noqa: E402


PINNED_FLINT_AVAILABLE = (
    backend.FLINT_IMPORT_ERROR is None
    and backend.flint.__version__ == backend.EXPECTED_PYTHON_FLINT
    and backend.flint.__FLINT_VERSION__ == backend.EXPECTED_FLINT
    and backend.flint.__FLINT_RELEASE__ == backend.EXPECTED_FLINT_RELEASE
)


@unittest.skipUnless(
    PINNED_FLINT_AVAILABLE,
    "requires pinned python-flint 0.9.0 / FLINT 3.6.0",
)
class DirichletFlintReferenceTests(unittest.TestCase):
    def test_q3_and_q4_contour_counts_match_hardy_brackets(self) -> None:
        for q, conrey in ((3, 2), (4, 3)):
            with self.subTest(q=q):
                result = backend.verify_character(q, conrey, Fraction(10))
                self.assertEqual(
                    result["contour"]["zero_count_with_trivial_zeros"], 2
                )
                self.assertEqual(result["known_trivial_zeros_in_contour"], 0)
                self.assertEqual(result["multiplicity_counted_nontrivial_zeros"], 2)
                self.assertEqual(
                    result["hardy_z"]["strict_sign_change_brackets"], 2
                )
                self.assertTrue(result["all_nontrivial_zeros_on_critical_line"])

    def test_even_character_contour_accounts_for_s_zero(self) -> None:
        # No nontrivial zero of the real even character modulo 5 occurs below
        # height 5. The contour winds once, exactly around the simple trivial
        # zero at s=0, so the corrected Hardy count is zero.
        result = backend.verify_character(5, 4, Fraction(5))
        self.assertEqual(result["parity"], 0)
        self.assertEqual(result["contour"]["zero_count_with_trivial_zeros"], 1)
        self.assertEqual(result["known_trivial_zeros_in_contour"], 1)
        self.assertEqual(result["multiplicity_counted_nontrivial_zeros"], 0)
        self.assertEqual(result["hardy_z"]["strict_sign_change_brackets"], 0)


if __name__ == "__main__":
    unittest.main()
