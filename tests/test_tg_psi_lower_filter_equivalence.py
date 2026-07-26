#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact model check for the optimized CH25 psi lower-endpoint filter."""

from __future__ import annotations

from math import isqrt
import random
import unittest


SCALE = 1 << 64
U64_MAX = (1 << 64) - 1


def old_classification(
    value: int, difference: int, strict: bool
) -> str:
    """Return the old C++ fast-path decision or ``fallback``."""

    quotient, remainder = divmod(difference, SCALE)
    has_remainder = remainder != 0
    if has_remainder and quotient == U64_MAX:
        return "reject"
    ceiling = quotient + int(has_remainder)
    root = isqrt(2 * value)
    if ceiling <= root and (
        not strict
        or ceiling < root
        or has_remainder
        or root * root < 2 * value
    ):
        return "accept"
    if quotient > root:
        return "reject"
    return "fallback"


def square_classification(
    value: int, difference: int, strict: bool
) -> str:
    """Return the optimized direct-square fast-path decision."""

    quotient, remainder = divmod(difference, SCALE)
    has_remainder = remainder != 0
    if has_remainder and quotient == U64_MAX:
        return "reject"
    ceiling = quotient + int(has_remainder)
    bound = 2 * value
    ceiling_squared = ceiling * ceiling
    if (
        not strict
        and ceiling_squared <= bound
    ) or (
        strict
        and (
            ceiling_squared < bound
            or (has_remainder and ceiling_squared <= bound)
        )
    ):
        return "accept"
    if quotient * quotient > bound:
        return "reject"
    return "fallback"


class PsiLowerFilterEquivalenceTests(unittest.TestCase):
    def assert_equivalent(
        self, value: int, difference: int, strict: bool
    ) -> None:
        self.assertEqual(
            square_classification(value, difference, strict),
            old_classification(value, difference, strict),
            (value, difference, strict),
        )

    def test_every_near_boundary_cell_through_one_hundred_thousand(self) -> None:
        remainders = (0, 1, SCALE // 2, SCALE - 1)
        for value in range(1, 100_001):
            root = isqrt(2 * value)
            for quotient in range(max(0, root - 2), root + 3):
                for remainder in remainders:
                    difference = quotient * SCALE + remainder
                    for strict in (False, True):
                        self.assert_equivalent(value, difference, strict)

    def test_source_endpoint_and_u64_extremes(self) -> None:
        values = (
            1,
            2,
            3,
            10**6,
            10**12,
            10**13 - 1,
            10**13,
            (1 << 63) - 1,
        )
        for value in values:
            root = isqrt(2 * value)
            quotients = {
                0,
                1,
                max(0, root - 1),
                root,
                root + 1,
                U64_MAX - 1,
                U64_MAX,
            }
            for quotient in quotients:
                for remainder in (0, 1, SCALE - 1):
                    difference = quotient * SCALE + remainder
                    if difference >= 1 << 128:
                        continue
                    for strict in (False, True):
                        self.assert_equivalent(value, difference, strict)

    def test_deterministic_random_u128_inputs(self) -> None:
        generator = random.Random(0xC825092)
        for _ in range(100_000):
            value = generator.randrange(1, 10**13 + 1)
            difference = generator.randrange(0, 1 << 128)
            self.assert_equivalent(value, difference, False)
            self.assert_equivalent(value, difference, True)


if __name__ == "__main__":
    unittest.main()
