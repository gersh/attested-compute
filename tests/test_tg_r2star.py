#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact-reference tests for the Ramaré--Zúñiga R2Star campaign."""

from __future__ import annotations

import ast
from dataclasses import replace
from fractions import Fraction
import inspect
import unittest

from tg_verifier import r2star


class R2StarExactReferenceTests(unittest.TestCase):
    def test_elementary_euler_gamma_interval_contains_known_decimal(self) -> None:
        lower, upper = r2star.euler_gamma_fixed_bounds(
            scale_bits=128, series_terms=48, harmonic_terms=100_000
        )
        scale = 1 << 128
        known = Fraction(5_772_156_649, 10_000_000_000)
        self.assertLess(lower * known.denominator, known.numerator * scale)
        self.assertLess(known.numerator * scale, upper * known.denominator)
        self.assertLess(upper - lower, scale // 99_000)

    def test_segmented_factor_support_handles_prime_powers_and_two_primes(self) -> None:
        rows = r2star._factor_block(1, 31, r2star._primes_upto(6))
        self.assertEqual(rows[1], (2,))  # 2
        self.assertEqual(rows[7], (2,))  # 8
        self.assertEqual(rows[11], (2, 3))  # 12
        self.assertEqual(rows[29], (2, 3, 5))  # 30

    def test_exact_sample_is_block_partition_invariant(self) -> None:
        first = r2star.verify_r2star_sample(
            2_000, harmonic_terms=10_000, block_size=137
        )
        second = r2star.verify_r2star_sample(
            2_000, harmonic_terms=10_000, block_size=509
        )
        self.assertEqual(first.final_lower, second.final_lower)
        self.assertEqual(first.final_upper, second.final_upper)
        self.assertEqual(first.minimum_squared_slack, second.minimum_squared_slack)
        self.assertTrue(first.exact_squared_envelope_verified)
        self.assertFalse(first.full_source_range)
        self.assertFalse(first.lean_atom_discharged)

    def test_reference_uses_no_native_float_arithmetic(self) -> None:
        source = inspect.getsource(r2star)
        tree = ast.parse(source)
        self.assertEqual(
            [
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, float)
            ],
            [],
        )
        self.assertEqual(
            [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "float"
            ],
            [],
        )


class R2StarChunkCertificateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.chunks = r2star.create_r2star_certificate(
            500,
            chunk_span=113,
            scale_bits=96,
            series_terms=40,
            harmonic_terms=2_000,
        )

    def test_chain_recomputes_factor_rows_states_and_minimum_witness(self) -> None:
        result = r2star.verify_r2star_chain(
            self.chunks, expected_limit=500
        )
        direct = r2star.verify_r2star_sample(
            500,
            scale_bits=96,
            series_terms=40,
            harmonic_terms=2_000,
            block_size=79,
        )
        self.assertEqual(result.checked_integers, 498)
        self.assertEqual(result.final_lower, direct.final_lower)
        self.assertEqual(result.final_upper, direct.final_upper)
        self.assertEqual(
            (result.minimum_squared_slack, result.minimum_slack_index),
            (direct.minimum_squared_slack, direct.minimum_slack_index),
        )
        self.assertTrue(result.exact_factor_support_verified)
        self.assertTrue(result.gap_free_hash_and_state_chain_verified)
        self.assertFalse(result.full_source_range)
        self.assertFalse(result.lean_atom_discharged)

    def test_factor_support_digest_consumes_rows_once(self) -> None:
        class OnePassRows:
            def __init__(self) -> None:
                self.used = False

            def __iter__(self):  # type: ignore[no-untyped-def]
                if self.used:
                    raise AssertionError("factor rows were consumed twice")
                self.used = True
                return iter(((), (2,), (3,), (2,), (5,), (2, 3)))

        rows = OnePassRows()
        digest = r2star.factor_support_rows_digest(1, rows)
        self.assertTrue(rows.used)
        self.assertEqual(len(digest), 64)
        self.assertEqual(
            digest,
            r2star.factor_support_rows_digest(
                1, ((), (2,), (3,), (2,), (5,), (2, 3))
            ),
        )

    def test_rehashed_tampering_cannot_hide_factor_or_witness_errors(self) -> None:
        first = self.chunks[0]
        wrong_rows = r2star.rehash_r2star_chunk(
            replace(first, factor_support_digest="1" * 64)
        )
        with self.assertRaisesRegex(
            r2star.R2StarReferenceError, "factor-support digest"
        ):
            r2star.verify_r2star_chunk(wrong_rows)

        wrong_witness = r2star.rehash_r2star_chunk(
            replace(first, minimum_squared_slack=first.minimum_squared_slack + 1)
        )
        with self.assertRaisesRegex(
            r2star.R2StarReferenceError, "minimum-slack witness"
        ):
            r2star.verify_r2star_chunk(wrong_witness)

    def test_raw_tampering_is_rejected_by_record_hash(self) -> None:
        changed = replace(
            self.chunks[0], outgoing_upper=self.chunks[0].outgoing_upper + 1
        )
        with self.assertRaisesRegex(
            r2star.R2StarReferenceError, "canonical body"
        ):
            r2star.verify_r2star_chunk(changed)

    def test_chain_rejects_range_hash_and_state_gaps(self) -> None:
        with self.assertRaisesRegex(
            r2star.R2StarReferenceError, "range coverage"
        ):
            r2star.verify_r2star_chain(
                (self.chunks[0],) + self.chunks[2:], expected_limit=500
            )

        second = self.chunks[1]
        wrong_hash = r2star.rehash_r2star_chunk(
            replace(second, previous_hash=r2star.ZERO_SHA256)
        )
        with self.assertRaisesRegex(r2star.R2StarReferenceError, "hash chain"):
            r2star.verify_r2star_chain(
                (self.chunks[0], wrong_hash) + self.chunks[2:],
                expected_limit=500,
            )

        wrong_state = r2star.rehash_r2star_chunk(
            replace(second, incoming_lower=second.incoming_lower + 1)
        )
        with self.assertRaisesRegex(
            r2star.R2StarReferenceError, "directed-state chain"
        ):
            r2star.verify_r2star_chain(
                (self.chunks[0], wrong_state) + self.chunks[2:],
                expected_limit=500,
            )

    def test_chain_rejects_incorrect_gamma_and_changed_configuration(self) -> None:
        first = self.chunks[0]
        wrong_gamma = r2star.rehash_r2star_chunk(
            replace(first, gamma_upper=first.gamma_upper + 1)
        )
        with self.assertRaisesRegex(
            r2star.R2StarReferenceError, "Euler-gamma bounds"
        ):
            r2star.verify_r2star_chunk(wrong_gamma)

        second = r2star.rehash_r2star_chunk(
            replace(self.chunks[1], series_terms=self.chunks[1].series_terms + 1)
        )
        with self.assertRaisesRegex(
            r2star.R2StarReferenceError, "configuration"
        ):
            r2star.verify_r2star_chain(
                (self.chunks[0], second) + self.chunks[2:],
                expected_limit=500,
            )

    def test_chain_accepts_a_one_pass_iterable(self) -> None:
        class OnePassChunks:
            def __init__(self, chunks: tuple[r2star.R2StarChunk, ...]) -> None:
                self.chunks = chunks
                self.used = False

            def __iter__(self):  # type: ignore[no-untyped-def]
                if self.used:
                    raise AssertionError("certificate iterable was consumed twice")
                self.used = True
                return iter(self.chunks)

        stream = OnePassChunks(self.chunks)
        result = r2star.verify_r2star_chain(stream, expected_limit=500)
        self.assertTrue(stream.used)
        self.assertEqual(result.chunks, len(self.chunks))


if __name__ == "__main__":
    unittest.main()
