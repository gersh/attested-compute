# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import random
import unittest

from tg_verifier.goldbach_shifted_bitset import (
    WORD_MASK,
    ShiftedBitsetError,
    alignment_offset,
    coverage_word,
    extract_shifted_word,
    replay_live_bits,
)


class GoldbachShiftedBitsetTests(unittest.TestCase):
    def test_exact_alignment_equation(self) -> None:
        offset = alignment_offset(even_low=10, q_low=3, prime=3)
        self.assertEqual(offset, 2)
        for bit in range(64):
            self.assertEqual(10 + 2 * bit, 3 + (3 + 2 * (offset + bit)))

    def test_alignment_rejects_underflow_and_wrong_parity(self) -> None:
        with self.assertRaises(ShiftedBitsetError):
            alignment_offset(even_low=4, q_low=3, prime=3)
        with self.assertRaises(ShiftedBitsetError):
            alignment_offset(even_low=11, q_low=3, prime=3)

    def test_two_word_extraction(self) -> None:
        words = [0x0123456789ABCDEF, 0xFEDCBA9876543210, 0]
        self.assertEqual(extract_shifted_word(words, 0), words[0])
        expected = ((words[0] >> 13) | (words[1] << 51)) & WORD_MASK
        self.assertEqual(extract_shifted_word(words, 13), expected)

    def test_packed_or_matches_bit_at_a_time_replay(self) -> None:
        generator = random.Random(0xC0FFEE)
        words = [generator.getrandbits(64) for _ in range(40)]
        offsets = [0, 7, 65, 131, 257, 389]
        for output_word in range(16):
            result = coverage_word(words, offsets, output_word=output_word)
            expected = 0
            for offset in offsets:
                expected |= extract_shifted_word(words, offset + 64 * output_word)
                if expected == WORD_MASK:
                    break
            self.assertEqual(result.covered, expected)
            self.assertEqual(replay_live_bits(words, offsets, output_word=output_word), result.accepted)

    def test_tail_mask_does_not_require_dead_bits(self) -> None:
        words = [0b10101, 0]
        result = coverage_word(words, [0], output_word=0, live_mask=0b10101)
        self.assertTrue(result.accepted)
        self.assertFalse(coverage_word(words, [0], output_word=0, live_mask=0b11111).accepted)

    def test_missing_carry_word_fails_closed(self) -> None:
        with self.assertRaises(ShiftedBitsetError):
            extract_shifted_word([1], 1)


if __name__ == "__main__":
    unittest.main()
