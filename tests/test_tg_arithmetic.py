#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Small exact-reference tests for ternary-Goldbach arithmetic jobs."""

from __future__ import annotations

import ast
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import unittest

from tg_verifier import arithmetic as tg


class MobiusReferenceTests(unittest.TestCase):
    def test_six_atom_ids_match_the_checked_catalog(self) -> None:
        self.assertEqual(
            tg.ARITHMETIC_ATOMS,
            (
                "cdem-squarefree",
                "cdem-table-abel",
                "mertens-hurst",
                "ramare-zuniga-lemma-6-2",
                "platt-little-mertens-2-11",
                "platt-little-mertens-stronger",
            ),
        )

    def test_linear_sieve_known_values(self) -> None:
        self.assertEqual(
            tg.mobius_linear(20),
            [
                0,
                1,
                -1,
                -1,
                0,
                -1,
                1,
                -1,
                0,
                0,
                1,
                -1,
                0,
                -1,
                1,
                1,
                0,
                -1,
                0,
                -1,
                0,
            ],
        )

    def test_segmented_sieve_matches_linear_slices(self) -> None:
        whole = tg.mobius_linear(1_000)
        for start, stop in ((1, 2), (1, 100), (97, 257), (900, 1_001)):
            with self.subTest(start=start, stop=stop):
                self.assertEqual(tg.mobius_segment(start, stop), whole[start:stop])

    def test_segmented_sieve_rejects_zero_and_reversed_ranges(self) -> None:
        with self.assertRaises(ValueError):
            tg.mobius_segment(0, 10)
        with self.assertRaises(ValueError):
            tg.mobius_segment(10, 9)
        self.assertEqual(tg.mobius_segment(7, 7), [])


class ExactMertensTests(unittest.TestCase):
    def test_hurst_predicate_is_the_literal_squared_integer_check(self) -> None:
        self.assertEqual(tg.hurst_squared_slack(1, 0), 571 * 571)
        self.assertEqual(
            tg.hurst_squared_slack(1, 1), 571 * 571 - 1_000 * 1_000
        )
        self.assertTrue(tg.check_hurst_squared(100, 5))
        self.assertFalse(tg.check_hurst_squared(100, 6))

    def test_small_hurst_sample_tracks_the_signed_prefix(self) -> None:
        result = tg.check_hurst_sample(tg.mobius_linear(100), 33, 100)
        self.assertTrue(result.passed)
        self.assertEqual(result.checks, 68)
        self.assertEqual(result.final_mertens, 1)
        self.assertGreaterEqual(result.minimum_slack, 0)

    def test_little_mertens_prefixes_and_both_exact_slacks(self) -> None:
        prefixes = tg.little_mertens_prefix_sums(tg.mobius_linear(6))
        self.assertEqual(prefixes[1], Fraction(1))
        self.assertEqual(prefixes[2], Fraction(1, 2))
        self.assertEqual(prefixes[3], Fraction(1, 6))
        self.assertEqual(prefixes[6], Fraction(2, 15))

        self.assertEqual(
            tg.little_mertens_interval_slack(
                Fraction(1, 6),
                4,
                tg.LittleMertensBound.SQRT_TWO_OVER_X,
            ),
            Fraction(17, 9),
        )
        self.assertEqual(
            tg.little_mertens_interval_slack(
                Fraction(1, 6),
                4,
                tg.LittleMertensBound.ONE_OVER_TWO_SQRT_X,
            ),
            Fraction(5, 9),
        )

    def test_real_interval_scans_use_the_decreasing_bound_at_right_limits(self) -> None:
        mu = tg.mobius_linear(100)
        equation_211 = tg.check_little_mertens_sample(
            mu, 1, 100, tg.LittleMertensBound.SQRT_TWO_OVER_X
        )
        stronger = tg.check_little_mertens_sample(
            mu, 3, 100, tg.LittleMertensBound.ONE_OVER_TWO_SQRT_X
        )
        self.assertTrue(equation_211.passed)
        self.assertTrue(stronger.passed)
        self.assertEqual(equation_211.slabs_checked, 100)
        self.assertEqual(stronger.slabs_checked, 98)

        # For a constant value 1/2, equation (2.11) is exactly tight as x
        # tends to 8 and fails if the slab is extended any farther.
        self.assertTrue(
            tg.check_little_mertens_interval(
                Fraction(1, 2), 8, tg.LittleMertensBound.SQRT_TWO_OVER_X
            )
        )
        self.assertFalse(
            tg.check_little_mertens_interval(
                Fraction(1, 2), 9, tg.LittleMertensBound.SQRT_TWO_OVER_X
            )
        )

    def test_exact_interfaces_reject_native_float_inputs(self) -> None:
        with self.assertRaises(TypeError):
            tg.little_mertens_interval_slack(
                0.5,  # type: ignore[arg-type]
                8,
                tg.LittleMertensBound.SQRT_TWO_OVER_X,
            )
        with self.assertRaises(TypeError):
            tg.classify_squarefree_endpoint(1, 1, 0.1)  # type: ignore[arg-type]


class SquarefreeReferenceTests(unittest.TestCase):
    def test_squarefree_prefix_counts(self) -> None:
        counts = tg.squarefree_prefix_counts(tg.mobius_linear(10))
        self.assertEqual(counts, [0, 1, 2, 3, 3, 4, 5, 6, 6, 6, 7])

    def test_machin_enclosure_and_endpoint_classification_are_exact(self) -> None:
        self.assertLess(tg.PI_LOWER, Fraction(22, 7))
        self.assertGreater(tg.PI_UPPER, Fraction(333, 106))
        self.assertLess(
            tg.PI_UPPER - tg.PI_LOWER,
            Fraction(1, 10**30),
        )

        self.assertIs(
            tg.classify_squarefree_endpoint(1, 1, Fraction(1)),
            tg.SquarefreeEndpointClassification.SAFE,
        )
        self.assertIs(
            tg.classify_squarefree_endpoint(1, 1, Fraction(0)),
            tg.SquarefreeEndpointClassification.VIOLATION,
        )

    def test_squarefree_sample_checks_integers_and_left_limits(self) -> None:
        result = tg.check_squarefree_sample(
            tg.mobius_linear(100), 1, 100, Fraction(1)
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.final_squarefree_count, 61)
        self.assertEqual(result.endpoints_checked, 199)
        self.assertEqual(result.safe_endpoints, 199)


class ChunkChainTests(unittest.TestCase):
    def _chain(self) -> tuple[list[tg.ChunkRecord], list[bytes]]:
        constants = b"tile-size=16;scale=2^128"
        payloads = [b"rows 0 through 15", b"rows 16 through 31"]
        first = tg.create_chunk_record(
            algorithm=tg.PLATT_2_11_ALGORITHM,
            lo=0,
            hi=16,
            incoming_state=(0, 1),
            outgoing_state=(7, 30),
            summary=(3, 17, 9),
            constants=constants,
            payload=payloads[0],
        )
        second = tg.create_chunk_record(
            algorithm=tg.PLATT_2_11_ALGORITHM,
            lo=16,
            hi=32,
            incoming_state=(7, 30),
            outgoing_state=(-1, 42),
            summary=(20, 5, 11),
            constants=constants,
            payload=payloads[1],
            previous_hash=first.record_hash,
        )
        return [first, second], payloads

    def test_deterministic_chain_checks_all_links(self) -> None:
        records, payloads = self._chain()
        duplicate, _ = self._chain()
        self.assertEqual(records, duplicate)
        result = tg.verify_chunk_chain(
            records,
            payloads=payloads,
            expected_algorithm=tg.PLATT_2_11_ALGORITHM,
            expected_constants_digest=records[0].constants_digest,
            expected_lo=0,
            expected_hi=32,
            expected_initial_state=(0, 1),
            expected_final_state=(-1, 42),
        )
        self.assertEqual(result.chunks, 2)
        self.assertEqual(result.final_hash, records[-1].record_hash)
        self.assertEqual(result.final_state, (-1, 42))

    def test_tampered_record_payload_and_links_are_rejected(self) -> None:
        records, payloads = self._chain()

        tampered_body = [records[0], replace(records[1], outgoing_state=(0, 1))]
        self.assertFalse(tg.check_chunk_chain(tampered_body, payloads=payloads))

        tampered_payloads = [payloads[0], payloads[1] + b"!"]
        self.assertFalse(tg.check_chunk_chain(records, payloads=tampered_payloads))

        relinked = [
            records[0],
            tg.create_chunk_record(
                algorithm=records[1].algorithm,
                lo=17,
                hi=32,
                incoming_state=records[0].outgoing_state,
                outgoing_state=records[1].outgoing_state,
                constants=b"tile-size=16;scale=2^128",
                payload=payloads[1],
                previous_hash=records[0].record_hash,
            ),
        ]
        self.assertFalse(tg.check_chunk_chain(relinked, payloads=payloads))

        broken_state = [
            records[0],
            tg.create_chunk_record(
                algorithm=records[1].algorithm,
                lo=16,
                hi=32,
                incoming_state=(999, 1),
                outgoing_state=records[1].outgoing_state,
                constants=b"tile-size=16;scale=2^128",
                payload=payloads[1],
                previous_hash=records[0].record_hash,
            ),
        ]
        self.assertFalse(tg.check_chunk_chain(broken_state, payloads=payloads))


class SourceExactnessTests(unittest.TestCase):
    def test_arithmetic_reference_contains_no_float_literals_or_calls(self) -> None:
        source = Path(tg.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertEqual(
            [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, float)
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


if __name__ == "__main__":
    unittest.main()
