#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest

from tg_verifier.goldbach_warp_tail_optimizer import (
    GoldbachWarpTailOptimizerError,
    _KERNEL_MARKER,
    _ORIGINAL_LAUNCH,
    rewrite_warp_parallel_tail,
)
from tests.test_goldbach_word_owner_optimizer import SOURCE


PROTOTYPE_SOURCE = SOURCE + "\n" + _KERNEL_MARKER + "\n" + _ORIGINAL_LAUNCH


class GoldbachWarpTailOptimizerTests(unittest.TestCase):
    def test_unique_checked_rewrite(self) -> None:
        changed = rewrite_warp_parallel_tail(PROTOTYPE_SOURCE, 65_535)
        self.assertIn("WARP_PARALLEL_SIEVE_LIMIT = 65535;", changed)
        self.assertIn(
            "__global__ void sieve_segment_warp_per_prime_kernel", changed
        )
        self.assertIn("warp_parallel_prime_count * 32", changed)
        self.assertIn("d_small_primes + warp_sieved_prime_count", changed)
        self.assertIn(
            "if (warp_step > q_high - composite) break;", changed
        )
        self.assertNotIn(_ORIGINAL_LAUNCH, changed)
        with self.assertRaises(GoldbachWarpTailOptimizerError):
            rewrite_warp_parallel_tail(changed, 131_071)

    def test_rejects_overlap_missing_marker_and_excessive_cutoff(self) -> None:
        for source, limit in (
            (PROTOTYPE_SOURCE, 7),
            (PROTOTYPE_SOURCE, 1_000_001),
            (PROTOTYPE_SOURCE.replace(_KERNEL_MARKER, ""), 65_535),
            (PROTOTYPE_SOURCE.replace(_ORIGINAL_LAUNCH, ""), 65_535),
        ):
            with self.subTest(limit=limit):
                with self.assertRaises(GoldbachWarpTailOptimizerError):
                    rewrite_warp_parallel_tail(source, limit)


if __name__ == "__main__":
    unittest.main()
