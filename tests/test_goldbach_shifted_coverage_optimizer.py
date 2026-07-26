#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
import unittest

from tg_verifier.goldbach_shifted_coverage_optimizer import (
    GoldbachShiftedCoverageOptimizerError,
    rewrite_packed_count_crosscheck,
    rewrite_packed_shifted_unverified_count,
    rewrite_shifted_phase1,
    rewrite_shifted_phase1_crosscheck,
)


class GoldbachShiftedCoverageOptimizerTests(unittest.TestCase):
    def test_active_prepared_source_has_unique_checked_rewrite_when_available(
        self,
    ) -> None:
        path = Path("/tmp/tg-goldbach-prepared-v2/src/goldbach.cu")
        if not path.is_file():
            self.skipTest("prepared pinned GoldbachGPU tree is not installed")
        source = path.read_text(encoding="utf-8")
        changed = rewrite_shifted_phase1(source)
        self.assertIn(
            "__global__ void shifted_or_phase1_coverage_kernel", changed
        )
        self.assertIn("expand_coverage_words_kernel<<<", changed)
        self.assertIn("d_seg_bits + segment_words", changed)
        self.assertIn(
            "Segment size exceeds the exact uint32_t",
            changed,
        )
        with self.assertRaises(GoldbachShiftedCoverageOptimizerError):
            rewrite_shifted_phase1(changed)

        crosscheck = rewrite_shifted_phase1_crosscheck(source)
        self.assertIn(
            "__global__ void compare_phase1_verified_kernel", crosscheck
        )
        self.assertIn("phase1_mismatch_count", crosscheck)
        self.assertIn("d_shifted_verified", crosscheck)

        packed_count = rewrite_packed_shifted_unverified_count(changed)
        self.assertIn(
            "__global__ void count_uncovered_coverage_words_kernel",
            packed_count,
        )
        self.assertIn("__popcll(missing)", packed_count)
        self.assertIn(
            "Materialize bytes only for the exceptional CPU replay.",
            packed_count,
        )
        with self.assertRaises(GoldbachShiftedCoverageOptimizerError):
            rewrite_packed_shifted_unverified_count(packed_count)
        with self.assertRaises(GoldbachShiftedCoverageOptimizerError):
            rewrite_packed_shifted_unverified_count(source)
        with self.assertRaises(GoldbachShiftedCoverageOptimizerError):
            rewrite_packed_shifted_unverified_count(crosscheck)

        packed_crosscheck = rewrite_packed_count_crosscheck(crosscheck)
        self.assertIn("d_packed_unverified_count", packed_crosscheck)
        self.assertIn(
            "packed missing-bit count differs from byte count",
            packed_crosscheck,
        )
        self.assertIn("2 * sizeof(uint32_t)", packed_crosscheck)
        with self.assertRaises(GoldbachShiftedCoverageOptimizerError):
            rewrite_packed_count_crosscheck(packed_crosscheck)
        with self.assertRaises(GoldbachShiftedCoverageOptimizerError):
            rewrite_packed_count_crosscheck(changed)


if __name__ == "__main__":
    unittest.main()
