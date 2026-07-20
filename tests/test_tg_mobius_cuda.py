#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Pure-Python invariants for the CUDA Moebius receipt boundary."""

from __future__ import annotations

from fractions import Fraction
import unittest

from tg_verifier import arithmetic
from tg_verifier.mobius_cuda import MobiusReceiptError, verify_mobius_receipt


class MobiusCudaBoundaryTests(unittest.TestCase):
    def test_coarse_density_interval_contains_machin_enclosure(self) -> None:
        lower = Fraction(607_927_101_854_026_628, 10**18)
        upper = Fraction(607_927_101_854_026_629, 10**18)
        self.assertLessEqual(lower, arithmetic.SQUAREFREE_DENSITY_LOWER)
        self.assertLessEqual(arithmetic.SQUAREFREE_DENSITY_UPPER, upper)

    def test_exact_hurst_real_slab_reduction(self) -> None:
        # If the squared inequality holds at n, the same fixed M(n) is bounded
        # on [n,n+1) because sqrt is increasing.  This pins the integer form
        # used by the CUDA runner.
        self.assertEqual(arithmetic.hurst_squared_slack(199, -8), 882_159)
        self.assertTrue(arithmetic.check_hurst_squared(199, -8))

    def test_receipt_cannot_claim_more_rows_than_the_runner_accepts(self) -> None:
        fabricated = {
            "schema_version": 1,
            "algorithm": "tg_mobius_segment_v1",
            "classification": "bounded_exact_transition_not_external_atom_proof",
            "canonical_transition_format": "tg_mobius_transition_lines_v1",
            "lower": 1,
            "upper": 10**16,
            "record_count": 10**16,
            "hurst_first_failure": None,
            "hurst_minimum_squared_slack": 0,
            "hurst_minimum_squared_slack_at": 33,
            "cdem_b1_first_not_proved_safe": None,
            "cdem_b2_first_not_proved_safe": None,
        }
        with self.assertRaisesRegex(MobiusReceiptError, "range is malformed"):
            verify_mobius_receipt(fabricated)


if __name__ == "__main__":
    unittest.main()
