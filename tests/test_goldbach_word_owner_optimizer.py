#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest

from tg_verifier.goldbach_word_owner_optimizer import (
    GoldbachWordOwnerOptimizerError,
    inspect_word_owner_source,
    primes_through,
    rewrite_word_owner_cutoff,
)
from tools.benchmark_goldbach_word_owner import (
    BenchmarkError,
    SAMPLE_EVEN_COUNT,
    SAMPLE_EVEN_LIMIT,
    SAMPLE_EVEN_START,
    parse_successful_run,
)


SOURCE = """\
static const uint64_t WORD_OWNER_SIEVE_LIMIT = 7;
__global__ void initialize_small_prime_words_kernel(
    uint64_t q_low,
    uint64_t word_count,
    uint64_t* __restrict__ segment_bits)
{
    uint64_t word_index = blockIdx.x * blockDim.x + threadIdx.x;
    if (word_index >= word_count) return;
    uint64_t word_low = q_low + 128 * word_index;
    uint64_t word = ~0ULL;
    clear_small_prime_from_word<3>(word_low, word);
    clear_small_prime_from_word<5>(word_low, word);
    clear_small_prime_from_word<7>(word_low, word);
    segment_bits[word_index] = word;
}
"""


class GoldbachWordOwnerOptimizerTests(unittest.TestCase):
    def test_exact_integer_prime_list(self) -> None:
        self.assertEqual(primes_through(3), (3,))
        self.assertEqual(primes_through(20), (3, 5, 7, 11, 13, 17, 19))

    def test_rewrite_moves_constant_and_calls_together(self) -> None:
        changed = rewrite_word_owner_cutoff(SOURCE, 13)
        inspected = inspect_word_owner_source(changed)
        self.assertEqual(inspected.cutoff, 13)
        self.assertEqual(inspected.primes, (3, 5, 7, 11, 13))
        self.assertEqual(rewrite_word_owner_cutoff(SOURCE, 7), SOURCE)

    def test_inspection_rejects_missing_duplicate_or_out_of_order_prime(self) -> None:
        mutations = (
            SOURCE.replace(
                "    clear_small_prime_from_word<5>(word_low, word);\n", ""
            ),
            SOURCE.replace(
                "    clear_small_prime_from_word<7>(word_low, word);",
                "    clear_small_prime_from_word<5>(word_low, word);\n"
                "    clear_small_prime_from_word<7>(word_low, word);",
            ),
            SOURCE.replace(
                "    clear_small_prime_from_word<5>(word_low, word);\n"
                "    clear_small_prime_from_word<7>(word_low, word);",
                "    clear_small_prime_from_word<7>(word_low, word);\n"
                "    clear_small_prime_from_word<5>(word_low, word);",
            ),
        )
        for source in mutations:
            with self.subTest(source=source):
                with self.assertRaises(GoldbachWordOwnerOptimizerError):
                    inspect_word_owner_source(source)

    def test_output_parser_requires_exact_range_count_success_and_no_fallback(self) -> None:
        output = f"""\
Checking range : [{SAMPLE_EVEN_START}, {SAMPLE_EVEN_LIMIT}]
Total numbers  : {SAMPLE_EVEN_COUNT}
All even numbers from {SAMPLE_EVEN_START} up to {SAMPLE_EVEN_LIMIT} satisfy Goldbach. ✓
Total computation time : 0.625 seconds
Phase 2 fallbacks      : 0
"""
        self.assertEqual(parse_successful_run(output), 0.625)
        for changed in (
            output.replace(str(SAMPLE_EVEN_COUNT), str(SAMPLE_EVEN_COUNT - 1)),
            output.replace("fallbacks      : 0", "fallbacks      : 1"),
            output.replace("satisfy Goldbach.", "were sampled."),
            output.replace("0.625 seconds", "0 seconds"),
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(BenchmarkError):
                    parse_successful_run(changed)


if __name__ == "__main__":
    unittest.main()
