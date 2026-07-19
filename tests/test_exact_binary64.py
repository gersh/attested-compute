#!/usr/bin/env python3
"""Boundary, oracle, and property tests for the exact binary64 reference."""

from __future__ import annotations

import ast
from fractions import Fraction
from pathlib import Path
import random
import unittest

from reference import exact_binary64 as exact


ONE = 0x3FF0000000000000
TWO = 0x4000000000000000
THREE = 0x4008000000000000
HALF = 0x3FE0000000000000
NEGATIVE_ONE = 0xBFF0000000000000


class ClassificationAndDecodeTests(unittest.TestCase):
    def test_all_encoding_classes(self) -> None:
        cases = {
            exact.POSITIVE_ZERO: exact.Binary64Class.POSITIVE_ZERO,
            exact.NEGATIVE_ZERO: exact.Binary64Class.NEGATIVE_ZERO,
            exact.MIN_POSITIVE_SUBNORMAL: exact.Binary64Class.POSITIVE_SUBNORMAL,
            exact.SIGN_MASK | exact.MIN_POSITIVE_SUBNORMAL:
                exact.Binary64Class.NEGATIVE_SUBNORMAL,
            exact.MIN_POSITIVE_NORMAL: exact.Binary64Class.POSITIVE_NORMAL,
            exact.SIGN_MASK | exact.MIN_POSITIVE_NORMAL:
                exact.Binary64Class.NEGATIVE_NORMAL,
            exact.POSITIVE_INFINITY: exact.Binary64Class.POSITIVE_INFINITY,
            exact.NEGATIVE_INFINITY: exact.Binary64Class.NEGATIVE_INFINITY,
            0x7FF0000000000001: exact.Binary64Class.NAN,
            0xFFFFFFFFFFFFFFFF: exact.Binary64Class.NAN,
        }
        for bits, expected in cases.items():
            with self.subTest(bits=f"{bits:016x}"):
                self.assertIs(exact.classify(bits), expected)

    def test_strict_word_validation(self) -> None:
        for value in (-1, 1 << 64, True, False, "0", None):
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    exact.classify(value)  # type: ignore[arg-type]

    def test_decode_distinguished_values_exactly(self) -> None:
        self.assertEqual(exact.decode_finite(exact.POSITIVE_ZERO), 0)
        self.assertEqual(exact.decode_finite(exact.NEGATIVE_ZERO), 0)
        self.assertEqual(
            exact.decode_finite(exact.MIN_POSITIVE_SUBNORMAL),
            Fraction(1, 1 << 1074),
        )
        self.assertEqual(
            exact.decode_finite(exact.MAX_POSITIVE_SUBNORMAL),
            Fraction((1 << 52) - 1, 1 << 1074),
        )
        self.assertEqual(
            exact.decode_finite(exact.MIN_POSITIVE_NORMAL),
            Fraction(1, 1 << 1022),
        )
        self.assertEqual(exact.decode_finite(ONE), 1)
        self.assertEqual(
            exact.decode_finite(ONE + 1), Fraction((1 << 52) + 1, 1 << 52)
        )
        self.assertEqual(
            exact.decode_finite(exact.MAX_FINITE),
            Fraction(((1 << 53) - 1) << 971),
        )
        self.assertEqual(
            exact.decode_finite(exact.MIN_FINITE),
            -Fraction(((1 << 53) - 1) << 971),
        )

    def test_decode_rejects_every_nonfinite_class(self) -> None:
        for bits in (
            exact.POSITIVE_INFINITY,
            exact.NEGATIVE_INFINITY,
            0x7FF0000000000001,
            0xFFF8000000000000,
        ):
            with self.subTest(bits=f"{bits:016x}"):
                with self.assertRaises(exact.NonFiniteBinary64Error):
                    exact.decode_finite(bits)

    def test_reference_source_has_no_native_float_constructs(self) -> None:
        source_path = Path(exact.__file__)
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        float_literals = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        ]
        float_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "float"
        ]
        self.assertEqual(float_literals, [])
        self.assertEqual(float_calls, [])


class DirectedRoundingTests(unittest.TestCase):
    def test_signed_zero_policy(self) -> None:
        self.assertEqual(exact.round_down(Fraction()), exact.NEGATIVE_ZERO)
        self.assertEqual(exact.round_up(Fraction()), exact.POSITIVE_ZERO)
        self.assertEqual(exact.round_nearest_even(Fraction()), exact.POSITIVE_ZERO)

    def test_rounding_input_must_be_exact(self) -> None:
        # A decimal string is intentionally used so this test itself introduces
        # no native binary floating-point value.
        with self.assertRaises(TypeError):
            exact.round_down("1.5")  # type: ignore[arg-type]

    def test_subnormal_underflow_and_ties(self) -> None:
        half_min = Fraction(1, 1 << 1075)
        three_halves_min = Fraction(3, 1 << 1075)
        self.assertEqual(exact.round_down(half_min), exact.POSITIVE_ZERO)
        self.assertEqual(exact.round_up(half_min), exact.MIN_POSITIVE_SUBNORMAL)
        self.assertEqual(exact.round_nearest_even(half_min), exact.POSITIVE_ZERO)
        self.assertEqual(
            exact.round_nearest_even(three_halves_min),
            exact.MIN_POSITIVE_SUBNORMAL + 1,
        )
        self.assertEqual(
            exact.round_down(-half_min),
            exact.SIGN_MASK | exact.MIN_POSITIVE_SUBNORMAL,
        )
        self.assertEqual(exact.round_up(-half_min), exact.NEGATIVE_ZERO)
        self.assertEqual(exact.round_nearest_even(-half_min), exact.NEGATIVE_ZERO)

    def test_largest_subnormal_to_smallest_normal_boundary(self) -> None:
        lower = exact.decode_finite(exact.MAX_POSITIVE_SUBNORMAL)
        upper = exact.decode_finite(exact.MIN_POSITIVE_NORMAL)
        midpoint = (lower + upper) / 2
        self.assertEqual(exact.round_down(midpoint), exact.MAX_POSITIVE_SUBNORMAL)
        self.assertEqual(exact.round_up(midpoint), exact.MIN_POSITIVE_NORMAL)
        # Smallest normal has an even low significand bit.
        self.assertEqual(exact.round_nearest_even(midpoint), exact.MIN_POSITIVE_NORMAL)

    def test_adjacent_values_and_power_of_two_boundary(self) -> None:
        previous_one = ONE - 1
        midpoint_below_one = (
            exact.decode_finite(previous_one) + exact.decode_finite(ONE)
        ) / 2
        midpoint_above_one = (
            exact.decode_finite(ONE) + exact.decode_finite(ONE + 1)
        ) / 2
        self.assertEqual(exact.round_down(midpoint_below_one), previous_one)
        self.assertEqual(exact.round_up(midpoint_below_one), ONE)
        self.assertEqual(exact.round_nearest_even(midpoint_below_one), ONE)
        self.assertEqual(exact.round_nearest_even(midpoint_above_one), ONE)

    def test_overflow_in_all_rounding_directions(self) -> None:
        beyond = exact.MAX_FINITE_VALUE * 2
        self.assertEqual(exact.round_down(beyond), exact.MAX_FINITE)
        self.assertEqual(exact.round_up(beyond), exact.POSITIVE_INFINITY)
        self.assertEqual(exact.round_down(-beyond), exact.NEGATIVE_INFINITY)
        self.assertEqual(exact.round_up(-beyond), exact.MIN_FINITE)
        self.assertEqual(
            exact.round_nearest_even(exact.RNE_OVERFLOW_THRESHOLD),
            exact.POSITIVE_INFINITY,
        )
        self.assertEqual(
            exact.round_nearest_even(-exact.RNE_OVERFLOW_THRESHOLD),
            exact.NEGATIVE_INFINITY,
        )
        just_below = exact.RNE_OVERFLOW_THRESHOLD - Fraction(1)
        self.assertEqual(exact.round_nearest_even(just_below), exact.MAX_FINITE)

    def test_next_up_and_down_distinguished_values(self) -> None:
        self.assertEqual(
            exact.next_up_bits(exact.NEGATIVE_INFINITY), exact.MIN_FINITE
        )
        self.assertEqual(exact.next_up_bits(exact.NEGATIVE_ZERO), 1)
        self.assertEqual(exact.next_up_bits(exact.POSITIVE_ZERO), 1)
        self.assertEqual(exact.next_up_bits(exact.MAX_FINITE), exact.POSITIVE_INFINITY)
        self.assertEqual(
            exact.next_down_bits(exact.POSITIVE_INFINITY), exact.MAX_FINITE
        )
        self.assertEqual(
            exact.next_down_bits(exact.POSITIVE_ZERO),
            exact.SIGN_MASK | exact.MIN_POSITIVE_SUBNORMAL,
        )

    def test_random_adjacent_interval_rounding_properties(self) -> None:
        rng = random.Random(0x5A17C0DE)
        for _ in range(200):
            lower_bits = rng.randrange(0, exact.MAX_FINITE)
            upper_bits = lower_bits + 1
            lower = exact.decode_finite(lower_bits)
            upper = exact.decode_finite(upper_bits)
            interior = (2 * lower + upper) / 3
            midpoint = (lower + upper) / 2
            self.assertEqual(exact.round_down(interior), lower_bits)
            self.assertEqual(exact.round_up(interior), upper_bits)
            self.assertEqual(exact.round_nearest_even(interior), lower_bits)
            expected_tie = lower_bits if lower_bits % 2 == 0 else upper_bits
            self.assertEqual(exact.round_nearest_even(midpoint), expected_tie)

            self.assertEqual(
                exact.round_down(-interior), upper_bits | exact.SIGN_MASK
            )
            self.assertEqual(
                exact.round_up(-interior), lower_bits | exact.SIGN_MASK
            )

    def test_random_exact_values_round_to_themselves(self) -> None:
        rng = random.Random(0xB164)
        for _ in range(200):
            magnitude_bits = rng.randrange(1, exact.MAX_FINITE + 1)
            for bits in (magnitude_bits, magnitude_bits | exact.SIGN_MASK):
                value = exact.decode_finite(bits)
                self.assertEqual(exact.round_down(value), bits)
                self.assertEqual(exact.round_up(value), bits)
                self.assertEqual(exact.round_nearest_even(value), bits)


class PrimitiveOperationTests(unittest.TestCase):
    def test_native_dgx_spark_probe_oracle_vectors(self) -> None:
        # These eight bit patterns were observed independently from the native
        # GB10 probe (gpu/src/probe_kernel.cu), not generated by this module.
        half_ulp_at_one = 0x3CA0000000000000
        quarter_ulp_at_one = 0x3C90000000000000
        next_after_one = 0x3FF0000000000001
        self.assertEqual(exact.add_down(ONE, half_ulp_at_one), ONE)
        self.assertEqual(exact.add_up(ONE, half_ulp_at_one), ONE + 1)
        self.assertEqual(exact.sub_down(ONE, quarter_ulp_at_one), ONE - 1)
        self.assertEqual(exact.sub_up(ONE, quarter_ulp_at_one), ONE)
        self.assertEqual(exact.mul_down(next_after_one, next_after_one), ONE + 2)
        self.assertEqual(exact.mul_up(next_after_one, next_after_one), ONE + 3)
        self.assertEqual(exact.div_down(ONE, THREE), 0x3FD5555555555555)
        self.assertEqual(exact.div_up(ONE, THREE), 0x3FD5555555555556)

    def test_primitive_results_enclose_exact_fraction(self) -> None:
        cases = (
            (exact.add_down, exact.add_up, ONE, ONE + 1, lambda a, b: a + b),
            (exact.sub_down, exact.sub_up, ONE, ONE + 1, lambda a, b: a - b),
            (exact.mul_down, exact.mul_up, ONE + 1, ONE + 2, lambda a, b: a * b),
            (exact.div_down, exact.div_up, ONE, THREE, lambda a, b: a / b),
        )
        for down, up, a_bits, b_bits, operation in cases:
            value = operation(
                exact.decode_finite(a_bits), exact.decode_finite(b_bits)
            )
            down_bits = down(a_bits, b_bits)
            up_bits = up(a_bits, b_bits)
            self.assertLessEqual(exact.decode_finite(down_bits), value)
            self.assertLessEqual(value, exact.decode_finite(up_bits))

    def test_overflow_primitives(self) -> None:
        self.assertEqual(
            exact.add_down(exact.MAX_FINITE, exact.MAX_FINITE), exact.MAX_FINITE
        )
        self.assertEqual(
            exact.add_up(exact.MAX_FINITE, exact.MAX_FINITE),
            exact.POSITIVE_INFINITY,
        )
        self.assertEqual(
            exact.add_down(exact.MIN_FINITE, exact.MIN_FINITE),
            exact.NEGATIVE_INFINITY,
        )
        self.assertEqual(
            exact.add_up(exact.MIN_FINITE, exact.MIN_FINITE), exact.MIN_FINITE
        )

    def test_operation_specific_signed_zero_rules(self) -> None:
        pz = exact.POSITIVE_ZERO
        nz = exact.NEGATIVE_ZERO
        self.assertEqual(exact.add_down(pz, nz), nz)
        self.assertEqual(exact.add_up(pz, nz), pz)
        self.assertEqual(exact.add_rne(pz, nz), pz)
        self.assertEqual(exact.add_up(nz, nz), nz)
        self.assertEqual(exact.sub_down(pz, pz), nz)
        self.assertEqual(exact.sub_up(nz, pz), nz)
        self.assertEqual(exact.sub_up(pz, nz), pz)
        self.assertEqual(exact.mul_down(nz, ONE), nz)
        self.assertEqual(exact.mul_up(nz, NEGATIVE_ONE), pz)
        self.assertEqual(exact.div_rne(nz, NEGATIVE_ONE), pz)

    def test_nonzero_cancellation_in_every_rounding_mode(self) -> None:
        self.assertEqual(exact.add_down(ONE, NEGATIVE_ONE), exact.NEGATIVE_ZERO)
        self.assertEqual(exact.add_up(ONE, NEGATIVE_ONE), exact.POSITIVE_ZERO)
        self.assertEqual(exact.add_rne(ONE, NEGATIVE_ONE), exact.POSITIVE_ZERO)
        self.assertEqual(exact.sub_down(ONE, ONE), exact.NEGATIVE_ZERO)
        self.assertEqual(exact.sub_up(ONE, ONE), exact.POSITIVE_ZERO)
        self.assertEqual(exact.sub_rne(ONE, ONE), exact.POSITIVE_ZERO)

    def test_division_by_least_subnormal_overflows_with_sign(self) -> None:
        least = exact.MIN_POSITIVE_SUBNORMAL
        negative_least = least | exact.SIGN_MASK
        self.assertEqual(exact.div_down(ONE, least), exact.MAX_FINITE)
        self.assertEqual(exact.div_up(ONE, least), exact.POSITIVE_INFINITY)
        self.assertEqual(exact.div_down(NEGATIVE_ONE, least), exact.NEGATIVE_INFINITY)
        self.assertEqual(exact.div_up(NEGATIVE_ONE, least), exact.MIN_FINITE)
        self.assertEqual(exact.div_down(ONE, negative_least), exact.NEGATIVE_INFINITY)
        self.assertEqual(exact.div_up(ONE, negative_least), exact.MIN_FINITE)

    def test_multiplication_all_primitive_sign_combinations(self) -> None:
        six = 0x4018000000000000
        negative_two = TWO | exact.SIGN_MASK
        negative_three = THREE | exact.SIGN_MASK
        for lhs, rhs, expected in (
            (TWO, THREE, six),
            (negative_two, THREE, six | exact.SIGN_MASK),
            (TWO, negative_three, six | exact.SIGN_MASK),
            (negative_two, negative_three, six),
        ):
            with self.subTest(lhs=f"{lhs:016x}", rhs=f"{rhs:016x}"):
                self.assertEqual(exact.mul_down(lhs, rhs), expected)
                self.assertEqual(exact.mul_up(lhs, rhs), expected)
                self.assertEqual(exact.mul_rne(lhs, rhs), expected)

    def test_division_by_either_zero_and_nonfinite_inputs_are_rejected(self) -> None:
        for zero in (exact.POSITIVE_ZERO, exact.NEGATIVE_ZERO):
            with self.subTest(zero=f"{zero:016x}"):
                with self.assertRaises(exact.InvalidBinary64Operation):
                    exact.div_down(ONE, zero)
        for bad in (
            exact.POSITIVE_INFINITY,
            exact.NEGATIVE_INFINITY,
            0x7FF8000000000000,
        ):
            with self.subTest(bad=f"{bad:016x}"):
                with self.assertRaises(exact.NonFiniteBinary64Error):
                    exact.add_down(ONE, bad)


class IntervalTests(unittest.TestCase):
    def test_interval_validation_rejects_nan_and_reversal(self) -> None:
        with self.assertRaises(ValueError):
            exact.Binary64Interval(0x7FF8000000000000, exact.POSITIVE_INFINITY)
        with self.assertRaises(ValueError):
            exact.Binary64Interval(TWO, ONE)
        self.assertEqual(
            exact.Binary64Interval(exact.POSITIVE_ZERO, exact.NEGATIVE_ZERO).lo,
            exact.POSITIVE_ZERO,
        )

    def test_interval_add_and_sub(self) -> None:
        a = exact.Binary64Interval(ONE, TWO)
        b = exact.Binary64Interval(HALF, ONE)
        self.assertEqual(
            exact.interval_add(a, b),
            exact.Binary64Interval(0x3FF8000000000000, 0x4008000000000000),
        )
        self.assertEqual(
            exact.interval_sub(a, b),
            exact.Binary64Interval(exact.NEGATIVE_ZERO, 0x3FF8000000000000),
        )

    def test_interval_multiplication_all_sign_combinations(self) -> None:
        positive = exact.Binary64Interval(ONE, TWO)
        negative = exact.Binary64Interval(0xC000000000000000, NEGATIVE_ONE)
        crossing = exact.Binary64Interval(NEGATIVE_ONE, TWO)
        self.assertEqual(
            exact.interval_mul(positive, positive),
            exact.Binary64Interval(ONE, 0x4010000000000000),
        )
        self.assertEqual(
            exact.interval_mul(negative, positive),
            exact.Binary64Interval(0xC010000000000000, NEGATIVE_ONE),
        )
        self.assertEqual(
            exact.interval_mul(negative, negative),
            exact.Binary64Interval(ONE, 0x4010000000000000),
        )
        self.assertEqual(
            exact.interval_mul(crossing, crossing),
            exact.Binary64Interval(0xC000000000000000, 0x4010000000000000),
        )

    def test_multiplication_zero_endpoint_ties_preserve_available_signs(self) -> None:
        positive_zero = exact.Binary64Interval(
            exact.POSITIVE_ZERO, exact.POSITIVE_ZERO
        )
        negative_zero = exact.Binary64Interval(
            exact.NEGATIVE_ZERO, exact.NEGATIVE_ZERO
        )
        positive = exact.Binary64Interval(ONE, TWO)
        self.assertEqual(exact.interval_mul(positive_zero, positive), positive_zero)
        self.assertEqual(exact.interval_mul(negative_zero, positive), negative_zero)

    def test_interval_division_and_zero_rejection(self) -> None:
        numerator = exact.Binary64Interval(ONE, TWO)
        denominator = exact.Binary64Interval(TWO, 0x4010000000000000)
        self.assertEqual(
            exact.interval_div(numerator, denominator),
            exact.Binary64Interval(0x3FD0000000000000, ONE),
        )
        zero_divisors = (
            exact.Binary64Interval(exact.POSITIVE_ZERO, ONE),
            exact.Binary64Interval(NEGATIVE_ONE, exact.NEGATIVE_ZERO),
            exact.Binary64Interval(NEGATIVE_ONE, ONE),
        )
        for divisor in zero_divisors:
            with self.subTest(divisor=divisor):
                with self.assertRaises(exact.InvalidBinary64Operation):
                    exact.interval_div(numerator, divisor)

    def test_overflow_and_conservative_infinite_chaining(self) -> None:
        maximum = exact.Binary64Interval(exact.MAX_FINITE, exact.MAX_FINITE)
        overflow = exact.interval_add(maximum, maximum)
        self.assertEqual(overflow.lo, exact.MAX_FINITE)
        self.assertEqual(overflow.hi, exact.POSITIVE_INFINITY)
        self.assertEqual(exact.interval_add(overflow, maximum), exact.WHOLE_INTERVAL)

    def test_neg_abs_min_max_and_powers(self) -> None:
        crossing = exact.Binary64Interval(0xC000000000000000, ONE)
        self.assertEqual(
            exact.interval_neg(crossing),
            exact.Binary64Interval(NEGATIVE_ONE, TWO),
        )
        self.assertEqual(
            exact.interval_abs(crossing),
            exact.Binary64Interval(exact.POSITIVE_ZERO, TWO),
        )
        other = exact.Binary64Interval(HALF, 0x4008000000000000)
        self.assertEqual(
            exact.interval_min(crossing, other),
            exact.Binary64Interval(0xC000000000000000, ONE),
        )
        self.assertEqual(
            exact.interval_max(crossing, other),
            exact.Binary64Interval(HALF, 0x4008000000000000),
        )
        self.assertEqual(
            exact.interval_pow_nat(crossing, 2),
            exact.Binary64Interval(0xC000000000000000, 0x4010000000000000),
        )
        self.assertEqual(
            exact.interval_pow_nat(crossing, 3),
            exact.Binary64Interval(0xC020000000000000, 0x4010000000000000),
        )
        self.assertEqual(
            exact.interval_pow_nat(crossing, 0),
            exact.Binary64Interval(ONE, ONE),
        )

    def test_min_max_signed_zero_endpoint_ties(self) -> None:
        positive = exact.Binary64Interval(
            exact.POSITIVE_ZERO, exact.POSITIVE_ZERO
        )
        negative = exact.Binary64Interval(
            exact.NEGATIVE_ZERO, exact.NEGATIVE_ZERO
        )
        self.assertEqual(exact.interval_min(positive, negative), negative)
        self.assertEqual(exact.interval_min(negative, positive), negative)
        self.assertEqual(exact.interval_max(positive, negative), positive)
        self.assertEqual(exact.interval_max(negative, positive), positive)

    def test_metaproperties_on_random_singletons(self) -> None:
        rng = random.Random(0x1A7E2A1)
        zero = exact.Binary64Interval(exact.POSITIVE_ZERO, exact.POSITIVE_ZERO)
        one = exact.Binary64Interval(ONE, ONE)
        for _ in range(100):
            bits = rng.randrange(1, exact.MAX_FINITE + 1)
            if rng.randrange(2):
                bits |= exact.SIGN_MASK
            value = exact.Binary64Interval(bits, bits)
            add_zero = exact.interval_add(value, zero)
            mul_one = exact.interval_mul(value, one)
            decoded = exact.decode_finite(bits)
            self.assertLessEqual(exact.decode_finite(add_zero.lo), decoded)
            self.assertLessEqual(decoded, exact.decode_finite(add_zero.hi))
            self.assertLessEqual(exact.decode_finite(mul_one.lo), decoded)
            self.assertLessEqual(decoded, exact.decode_finite(mul_one.hi))
            self.assertEqual(
                exact.interval_mul(value, one), exact.interval_mul(one, value)
            )


if __name__ == "__main__":
    unittest.main()
