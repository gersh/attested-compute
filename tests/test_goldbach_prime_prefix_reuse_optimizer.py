# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

import hashlib
from pathlib import Path
import unittest

from tg_verifier.goldbach_prime_prefix_reuse_optimizer import (
    GoldbachPrimePrefixReuseError,
    V1_OPTIMIZED_SOURCE_BYTES,
    V1_OPTIMIZED_SOURCE_SHA256,
    rewrite_prime_prefix_reuse,
    rewrite_prime_prefix_reuse_crosscheck,
)


class GoldbachPrimePrefixReuseOptimizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_path = Path(
            "/tmp/tg-goldbach-qualified-0725-e/source/src/goldbach.cu"
        )
        if not cls.source_path.is_file():
            raise unittest.SkipTest("qualified Goldbach v1 source is absent")
        cls.source = cls.source_path.read_text(encoding="utf-8")

    def test_fixture_is_exact_qualified_v1(self) -> None:
        encoded = self.source.encode("utf-8")
        self.assertEqual(len(encoded), V1_OPTIMIZED_SOURCE_BYTES)
        self.assertEqual(
            hashlib.sha256(encoded).hexdigest(),
            V1_OPTIMIZED_SOURCE_SHA256,
        )

    def test_productive_rewrite_retains_safe_fallback(self) -> None:
        rewritten = rewrite_prime_prefix_reuse(self.source)
        self.assertIn(
            "cpu_primes.assign(small_primes.begin(), cpu_prime_end);",
            rewritten,
        )
        self.assertIn(
            "cpu_primes = generate_cpu_primes(PHASE2_SIEVE_LIMIT);",
            rewritten,
        )
        self.assertNotIn(
            "CPU-prime prefix exact-vector crosscheck: ", rewritten
        )

    def test_crosscheck_requires_ordered_vector_equality(self) -> None:
        rewritten = rewrite_prime_prefix_reuse_crosscheck(self.source)
        self.assertIn(
            "if (cpu_primes != reference_cpu_primes)", rewritten
        )
        self.assertIn(
            "reused CPU-prime prefix differs from independent sieve",
            rewritten,
        )

    def test_rejects_substitution_truncation_and_reapplication(self) -> None:
        for malformed in (
            self.source + "\n",
            self.source[:-1],
            self.source.replace(
                "PHASE2_SIEVE_LIMIT = 100'000'000ULL",
                "PHASE2_SIEVE_LIMIT = 99'999'999ULL",
                1,
            ),
            rewrite_prime_prefix_reuse(self.source),
        ):
            with self.subTest(digest=hashlib.sha256(malformed.encode()).hexdigest()):
                with self.assertRaises(GoldbachPrimePrefixReuseError):
                    rewrite_prime_prefix_reuse(malformed)


if __name__ == "__main__":
    unittest.main()
