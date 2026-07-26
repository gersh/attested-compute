# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from pathlib import Path
import unittest

from tg_verifier.goldbach_shifted_coverage_optimizer import (
    rewrite_packed_count_crosscheck,
    rewrite_packed_shifted_unverified_count,
    rewrite_shifted_phase1,
    rewrite_shifted_phase1_crosscheck,
)
from tg_verifier.goldbach_warp_tail_optimizer import rewrite_warp_parallel_tail
from tg_verifier.goldbach_wheel_filtered_tail_optimizer import (
    GoldbachWheelFilteredTailOptimizerError,
    rewrite_wheel_filtered_sieve,
    rewrite_wheel_filtered_sieve_crosscheck,
)


class GoldbachWheelFilteredTailOptimizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path("/tmp/tg-goldbach-prepared-v2/src/goldbach.cu")
        if not path.is_file():
            raise unittest.SkipTest("prepared GoldbachGPU source is absent")
        cls.source = path.read_text(encoding="utf-8")

    def test_rewrite_tracks_exact_cofactor(self) -> None:
        combined = rewrite_shifted_phase1(
            rewrite_warp_parallel_tail(self.source, 32_749)
        )
        changed = rewrite_wheel_filtered_sieve(combined)
        self.assertIn("cofactor % 15015ULL", changed)
        self.assertIn("COFACTOR_FILTER_LIMIT = 13;", changed)
        self.assertEqual(
            changed.count("cofactor_survives_word_owner_wheel(cofactor)"), 2
        )
        self.assertEqual(changed.count("quotient = p;"), 2)
        self.assertIn("cofactor += 64", changed)
        self.assertIn("cofactor += 2", changed)
        with self.assertRaises(GoldbachWheelFilteredTailOptimizerError):
            rewrite_wheel_filtered_sieve(changed)

    def test_extended_filter_is_bounded_by_word_owner_prefix(self) -> None:
        combined = rewrite_shifted_phase1(
            rewrite_warp_parallel_tail(self.source, 32_749)
        )
        changed = rewrite_wheel_filtered_sieve(combined, 31)
        self.assertIn("COFACTOR_FILTER_LIMIT = 31;", changed)
        for prime in (17, 19, 23, 29, 31):
            self.assertIn(f"cofactor % {prime}U != 0U", changed)
        with self.assertRaises(GoldbachWheelFilteredTailOptimizerError):
            rewrite_wheel_filtered_sieve(combined, 17)

    def test_requires_warp_source(self) -> None:
        with self.assertRaises(GoldbachWheelFilteredTailOptimizerError):
            rewrite_wheel_filtered_sieve(self.source)

    def test_crosscheck_duplicates_reference_and_compares_every_word(
        self,
    ) -> None:
        combined = rewrite_shifted_phase1(
            rewrite_warp_parallel_tail(self.source, 32_749)
        )
        changed = rewrite_wheel_filtered_sieve_crosscheck(combined)
        self.assertIn(
            "reference_sieve_segment_warp_per_prime_kernel<<<", changed
        )
        self.assertIn("reference_sieve_segment_kernel<<<", changed)
        self.assertIn(
            "d_reference_seg_bits, d_seg_bits, segment_words", changed
        )
        self.assertIn(
            "wheel-filtered sieve differs from unfiltered sieve", changed
        )

    def test_commutes_with_packed_unverified_count_post_transform(
        self,
    ) -> None:
        combined = rewrite_shifted_phase1(
            rewrite_warp_parallel_tail(self.source, 32_749)
        )
        packed_then_wheel = rewrite_wheel_filtered_sieve(
            rewrite_packed_shifted_unverified_count(combined), 47
        )
        wheel_then_packed = rewrite_packed_shifted_unverified_count(
            rewrite_wheel_filtered_sieve(combined, 47)
        )
        self.assertEqual(packed_then_wheel, wheel_then_packed)

    def test_crosscheck_composes_with_phase_and_count_crosschecks(
        self,
    ) -> None:
        warp = rewrite_warp_parallel_tail(self.source, 32_749)
        phase_and_count = rewrite_packed_count_crosscheck(
            rewrite_shifted_phase1_crosscheck(warp)
        )
        changed = rewrite_wheel_filtered_sieve_crosscheck(
            phase_and_count, 47
        )
        self.assertIn(
            "wheel-filtered sieve differs from unfiltered sieve", changed
        )
        self.assertIn(
            "shifted phase 1 differs from original phase 1", changed
        )
        self.assertIn(
            "packed missing-bit count differs from byte count", changed
        )
        self.assertIn(
            "2 * seg_bytes + 2 * sizeof(uint64_t) + "
            "2 * sizeof(uint32_t)",
            changed,
        )


if __name__ == "__main__":
    unittest.main()
