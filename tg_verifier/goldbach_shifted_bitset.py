# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact replay model for the word-oriented binary-Goldbach coverage stage.

This module checks packed-bit indexing and OR semantics.  It does not decide
primality: a production caller must obtain ``q_words`` from the separately
verified exact segmented sieve.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


WORD_BITS = 64
WORD_MASK = (1 << WORD_BITS) - 1


class ShiftedBitsetError(ValueError):
    """Packed dimensions, alignment, or a live-mask check failed closed."""


def _word(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= WORD_MASK:
        raise ShiftedBitsetError(f"{what} is not an unsigned 64-bit word")
    return value


def alignment_offset(*, even_low: int, q_low: int, prime: int) -> int:
    """Return the unique offset in ``even_low = q_low + prime + 2*offset``."""

    for name, value in (("even_low", even_low), ("q_low", q_low), ("prime", prime)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ShiftedBitsetError(f"{name} must be a natural number")
    difference = even_low - q_low - prime
    if difference < 0 or difference % 2 != 0:
        raise ShiftedBitsetError("small-prime shift has no exact nonnegative alignment")
    return difference // 2


def extract_shifted_word(q_words: Sequence[int], first_bit: int) -> int:
    """Extract 64 consecutive bits using the CUDA kernel's two-load equation."""

    if isinstance(first_bit, bool) or not isinstance(first_bit, int) or first_bit < 0:
        raise ShiftedBitsetError("first_bit must be a natural number")
    word_index, shift = divmod(first_bit, WORD_BITS)
    if word_index >= len(q_words):
        raise ShiftedBitsetError("shifted word starts outside the q bitset")
    low = _word(q_words[word_index], f"q word {word_index}") >> shift
    if shift == 0:
        return low
    if word_index + 1 >= len(q_words):
        raise ShiftedBitsetError("unaligned shifted word lacks its carry word")
    high = _word(q_words[word_index + 1], f"q word {word_index + 1}")
    return (low | (high << (WORD_BITS - shift))) & WORD_MASK


@dataclass(frozen=True)
class CoverageWord:
    covered: int
    rounds: int
    live_mask: int

    @property
    def accepted(self) -> bool:
        return self.covered & self.live_mask == self.live_mask


def coverage_word(
    q_words: Sequence[int],
    base_offsets: Sequence[int],
    *,
    output_word: int,
    live_mask: int = WORD_MASK,
) -> CoverageWord:
    """Replay one thread of ``shifted_or_coverage_kernel`` exactly."""

    if isinstance(output_word, bool) or not isinstance(output_word, int) or output_word < 0:
        raise ShiftedBitsetError("output_word must be a natural number")
    live_mask = _word(live_mask, "live_mask")
    if live_mask == 0:
        raise ShiftedBitsetError("live_mask must select at least one output bit")
    if not base_offsets:
        raise ShiftedBitsetError("at least one aligned small-prime offset is required")
    covered = 0
    rounds = 0
    for index, offset in enumerate(base_offsets):
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ShiftedBitsetError(f"base offset {index} is not a natural number")
        covered |= extract_shifted_word(q_words, offset + WORD_BITS * output_word)
        rounds += 1
        if covered & live_mask == live_mask:
            break
    return CoverageWord(covered=covered & WORD_MASK, rounds=rounds, live_mask=live_mask)


def replay_live_bits(
    q_words: Sequence[int],
    base_offsets: Sequence[int],
    *,
    output_word: int,
    live_mask: int = WORD_MASK,
) -> bool:
    """Independent bit-at-a-time form of the same finite equation."""

    result = coverage_word(
        q_words, base_offsets, output_word=output_word, live_mask=live_mask
    )
    for bit in range(WORD_BITS):
        if not (live_mask >> bit) & 1:
            continue
        expected = any(
            (extract_shifted_word(q_words, offset + WORD_BITS * output_word) >> bit) & 1
            for offset in base_offsets
        )
        if bool((result.covered >> bit) & 1) != expected:
            return False
    return result.accepted

