# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import math
import unittest

from tg_verifier.goldbach_bucket_sieve import (
    GoldbachBucketSieveError,
    PersistentBucketOddSieve,
    odd_primes_through,
    source_scale_eta_model,
    source_scale_work_model,
    stateless_odd_prime_words,
    trial_division_odd_prime_words,
    words_sha256_le,
)


class GoldbachBucketSieveTests(unittest.TestCase):
    def test_persistent_activation_matches_trial_division(self) -> None:
        odd_low = 1
        odd_count = 129
        segments = 5
        high = odd_low + 2 * odd_count * segments
        primes = odd_primes_through(math.isqrt(high - 1))
        sieve = PersistentBucketOddSieve(
            odd_low=odd_low,
            odd_count=odd_count,
            segments=segments,
            odd_primes=primes,
        )
        outputs = []
        activation_counts = []
        for _ in range(segments):
            segment = sieve.next_segment()
            outputs.append(segment.words)
            activation_counts.append(segment.newly_activated_primes)
            self.assertEqual(
                segment.words,
                trial_division_odd_prime_words(segment.odd_low, odd_count),
            )
        self.assertGreater(sum(count > 0 for count in activation_counts), 1)
        self.assertEqual(
            words_sha256_le(outputs),
            "31183081b5fa76330800f5b0ea068c42a333902e71df6858b9d3d08ad2a91f99",
        )

    def test_sparse_buckets_match_stateless_replay(self) -> None:
        odd_low = 1_000_000_001
        odd_count = 257
        segments = 12
        high = odd_low + 2 * odd_count * segments
        primes = odd_primes_through(math.isqrt(high - 1))
        sieve = PersistentBucketOddSieve(
            odd_low=odd_low,
            odd_count=odd_count,
            segments=segments,
            odd_primes=primes,
        )
        outputs = []
        event_counts = []
        for _ in range(segments):
            segment = sieve.next_segment()
            outputs.append(segment.words)
            event_counts.append(segment.sparse_events)
            self.assertEqual(
                segment.words,
                stateless_odd_prime_words(segment.odd_low, odd_count, primes),
            )
        self.assertEqual(sieve.activated_prime_count, len(primes))
        self.assertEqual(sieve.sparse_event_count, 1863)
        self.assertEqual(
            event_counts,
            [153, 153, 139, 162, 168, 155, 148, 149, 172, 157, 161, 146],
        )
        self.assertEqual(
            words_sha256_le(outputs),
            "2e1b7df7d8d75abc3799f2c0c1ee1d8d686eaa875923d7ad95b21f57f8dfd897",
        )

    def test_cuda_cross_language_known_answer(self) -> None:
        # The reviewed CUDA command in the documentation uses this exact case.
        # Its full replay must emit the same digest and sparse-event count.
        odd_low = 1_000_000_000_001
        odd_count = 4096
        segments = 16
        high = odd_low + 2 * odd_count * segments
        primes = odd_primes_through(math.isqrt(high - 1))
        sieve = PersistentBucketOddSieve(
            odd_low=odd_low,
            odd_count=odd_count,
            segments=segments,
            odd_primes=primes,
        )
        outputs = [sieve.next_segment().words for _ in range(segments)]
        self.assertEqual(sieve.sparse_event_count, 33075)
        self.assertEqual(
            words_sha256_le(outputs),
            "80a8f7b33e6f9f95c9bb953d30b79cbc6e5de3817fd0dc4dce0a8a69dfb63e4d",
        )

    def test_source_model_exposes_cost_and_no_certificate_claim(self) -> None:
        model = source_scale_work_model(segment_odds=1 << 26)
        self.assertEqual(model["base_odd_prime_count"], 98_222_286)
        self.assertEqual(model["segment_count"], 29_802_322_388)
        self.assertEqual(model["dense_scheduled_prime_count"], 3_957_803)
        self.assertGreater(model["estimated_total_composite_marks"], 3e18)
        self.assertFalse(model["model_is_certificate"])
        eta = source_scale_eta_model(
            measured_candidates=(1 << 26) * 32,
            measured_pipeline_seconds=7.04413534,
            measured_host_seconds=3.645192892,
            measured_gpu_seconds=3.378619338,
            gpu_count=8,
            gpu_speedup=12.3,
        )
        self.assertGreater(eta["projected_wall_years"], 14)
        self.assertGreater(eta["one_week_rate_shortfall_factor"], 700)
        self.assertFalse(eta["projection_is_certificate"])

    def test_invalid_or_incomplete_inputs_fail_closed(self) -> None:
        with self.assertRaises(GoldbachBucketSieveError):
            PersistentBucketOddSieve(
                odd_low=2, odd_count=64, segments=1, odd_primes=(3, 5)
            )
        with self.assertRaises(GoldbachBucketSieveError):
            PersistentBucketOddSieve(
                odd_low=3, odd_count=64, segments=1, odd_primes=(3, 3)
            )
        sieve = PersistentBucketOddSieve(
            odd_low=3, odd_count=64, segments=1, odd_primes=(3, 5, 7)
        )
        sieve.next_segment()
        with self.assertRaises(GoldbachBucketSieveError):
            sieve.next_segment()


if __name__ == "__main__":
    unittest.main()
