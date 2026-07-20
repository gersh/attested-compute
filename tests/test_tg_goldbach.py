#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for exact bounded Goldbach certificate primitives."""

from __future__ import annotations

from dataclasses import replace
import unittest

from tg_verifier import goldbach as tg


class BoundedPrimalityTests(unittest.TestCase):
    @staticmethod
    def _trial_division_is_prime(number: int) -> bool:
        if number < 2:
            return False
        divisor = 2
        while divisor * divisor <= number:
            if number % divisor == 0:
                return False
            divisor += 1
        return True

    def test_small_values_are_decided_exactly(self) -> None:
        for prime in (2, 3, 5, 7, 11, 97, 65_537):
            with self.subTest(prime=prime):
                self.assertTrue(tg.is_prime_bounded(prime))
        for composite in (0, 1, 4, 9, 25, 91, 3_215_031_751):
            with self.subTest(composite=composite):
                self.assertFalse(tg.is_prime_bounded(composite))

    def test_bounded_predicate_matches_trial_division_on_a_dense_sample(self) -> None:
        for number in range(10_000):
            self.assertEqual(
                tg.is_prime_bounded(number),
                self._trial_division_is_prime(number),
                number,
            )

    def test_deterministic_64_bit_boundary_and_pseudoprime(self) -> None:
        # A strong pseudoprime to many smaller base sets must still be rejected.
        self.assertFalse(tg.is_prime_bounded(341_550_071_728_321))
        # Largest prime below 2**64.
        self.assertTrue(tg.is_prime_bounded(18_446_744_073_709_551_557))
        self.assertFalse(tg.is_prime_bounded(1 << 64))

    def test_non_integer_and_boolean_inputs_fail_closed(self) -> None:
        self.assertFalse(tg.is_prime_bounded(True))  # type: ignore[arg-type]
        self.assertFalse(tg.is_prime_bounded(13.0))  # type: ignore[arg-type]
        self.assertFalse(tg.is_prime_bounded(-13))


class ProthCertificateTests(unittest.TestCase):
    def setUp(self) -> None:
        # 13 = 3 * 2**2 + 1, Jacobi(2, 13) = -1, and 2**6 = -1 mod 13.
        self.valid = tg.ProthCertificate(
            number=13,
            k=3,
            exponent=2,
            witness=2,
        )

    def test_jacobi_symbol_and_valid_proth_certificate(self) -> None:
        self.assertEqual(tg.jacobi_symbol(2, 13), -1)
        self.assertEqual(tg.jacobi_symbol(5, 13), -1)
        self.assertEqual(tg.jacobi_symbol(3, 13), 1)
        self.assertTrue(tg.check_proth_certificate(self.valid))

    def test_every_proth_field_is_bound_to_the_certificate(self) -> None:
        for tampered in (
            replace(self.valid, number=17),
            replace(self.valid, k=1),
            replace(self.valid, exponent=3),
            replace(self.valid, witness=3),
        ):
            with self.subTest(tampered=tampered):
                self.assertFalse(tg.check_proth_certificate(tampered))

    def test_shape_and_resource_guards_fail_closed(self) -> None:
        self.assertFalse(
            tg.check_proth_certificate(
                tg.ProthCertificate(number=9, k=2, exponent=2, witness=2)
            )
        )
        self.assertFalse(
            tg.check_proth_certificate(
                tg.ProthCertificate(number=21, k=5, exponent=2, witness=2)
            )
        )
        self.assertFalse(
            tg.check_proth_certificate(
                tg.ProthCertificate(
                    number=3,
                    k=1,
                    exponent=tg.MAX_PROTH_EXPONENT + 1,
                    witness=2,
                )
            )
        )
        self.assertFalse(
            tg.check_proth_certificate(
                tg.ProthCertificate(
                    number=13, k=True, exponent=2, witness=2  # type: ignore[arg-type]
                )
            )
        )

    def test_low_level_jacobi_rejects_invalid_denominators(self) -> None:
        with self.assertRaises(ValueError):
            tg.jacobi_symbol(2, 0)
        with self.assertRaises(ValueError):
            tg.jacobi_symbol(2, 12)


class TernaryGoldbachWitnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.witnesses = (
            tg.TernaryGoldbachWitness(7, 2, 2, 3),
            tg.TernaryGoldbachWitness(9, 2, 2, 5),
            tg.TernaryGoldbachWitness(11, 3, 3, 5),
            tg.TernaryGoldbachWitness(13, 3, 3, 7),
            tg.TernaryGoldbachWitness(15, 3, 5, 7),
            tg.TernaryGoldbachWitness(17, 3, 7, 7),
            tg.TernaryGoldbachWitness(19, 3, 5, 11),
            tg.TernaryGoldbachWitness(21, 3, 5, 13),
        )

    def test_contiguous_inclusive_odd_interval(self) -> None:
        self.assertTrue(
            tg.check_ternary_goldbach_interval(7, 21, self.witnesses)
        )
        self.assertTrue(tg.check_ternary_goldbach_witness(self.witnesses[-1]))

    def test_omitted_reordered_and_truncated_coverage_is_rejected(self) -> None:
        self.assertFalse(
            tg.check_ternary_goldbach_interval(7, 21, self.witnesses[:-1])
        )
        reordered = list(self.witnesses)
        reordered[2], reordered[3] = reordered[3], reordered[2]
        self.assertFalse(tg.check_ternary_goldbach_interval(7, 21, reordered))
        self.assertFalse(
            tg.check_ternary_goldbach_interval(9, 21, self.witnesses)
        )

    def test_bad_sum_composite_and_bad_interval_shape_are_rejected(self) -> None:
        bad_sum = replace(self.witnesses[0], r=5)
        composite_terms = tg.TernaryGoldbachWitness(21, 4, 4, 13)
        self.assertFalse(tg.check_ternary_goldbach_witness(bad_sum))
        self.assertFalse(tg.check_ternary_goldbach_witness(composite_terms))
        self.assertFalse(tg.check_ternary_goldbach_interval(8, 21, ()))
        self.assertFalse(tg.check_ternary_goldbach_interval(21, 7, ()))


class PrimeLadderTests(unittest.TestCase):
    def setUp(self) -> None:
        proth_13 = tg.ProthCertificate(13, 3, 2, 2)
        self.rungs = (
            tg.PrimeCertificate(11),
            tg.PrimeCertificate(13, proth_13),
            tg.PrimeCertificate(17),
            tg.PrimeCertificate(19),
            tg.PrimeCertificate(23),
            tg.PrimeCertificate(29),
        )
        self.ladder = tg.PrimeLadderCertificate(
            interval_start=13,
            interval_end=23,
            maximum_gap=6,
            rungs=self.rungs,
        )

    def test_ordered_prime_ladder_brackets_the_claimed_interval(self) -> None:
        self.assertTrue(tg.check_prime_ladder(self.ladder))

    def test_composite_duplicate_reordered_and_large_gap_rungs_fail(self) -> None:
        composite = self.rungs[:3] + (tg.PrimeCertificate(21),) + self.rungs[4:]
        duplicate = self.rungs[:3] + (self.rungs[2],) + self.rungs[3:]
        reordered = list(self.rungs)
        reordered[2], reordered[3] = reordered[3], reordered[2]
        large_gap = self.rungs[:2] + self.rungs[4:]
        for rungs in (composite, duplicate, tuple(reordered), large_gap):
            with self.subTest(rungs=rungs):
                self.assertFalse(
                    tg.check_prime_ladder(replace(self.ladder, rungs=rungs))
                )

    def test_left_and_right_coverage_cannot_be_truncated(self) -> None:
        self.assertFalse(
            tg.check_prime_ladder(replace(self.ladder, rungs=self.rungs[2:]))
        )
        self.assertFalse(
            tg.check_prime_ladder(replace(self.ladder, rungs=self.rungs[:4]))
        )

    def test_embedded_prime_certificates_and_gap_are_checked(self) -> None:
        bad_proth = replace(self.rungs[1].proth, witness=3)
        bad_rung = replace(self.rungs[1], proth=bad_proth)
        bad_rungs = (self.rungs[0], bad_rung) + self.rungs[2:]
        self.assertFalse(
            tg.check_prime_ladder(replace(self.ladder, rungs=bad_rungs))
        )
        self.assertFalse(
            tg.check_prime_ladder(replace(self.ladder, maximum_gap=0))
        )


class ScopeTests(unittest.TestCase):
    def test_module_disclaims_the_full_external_computations(self) -> None:
        documentation = (tg.__doc__ or "").lower()
        self.assertIn("does **not** verify helfgott--platt theorem 4.1", documentation)
        self.assertIn("binary-goldbach", documentation)
        self.assertIn("successful sample", documentation)


if __name__ == "__main__":
    unittest.main()
