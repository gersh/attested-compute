#!/usr/bin/env python3
"""Exact tests for the directed Proposition 12.2.4 sample producer.

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import ast
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import unittest

from tg_verifier import prop1224_directed as directed
from tg_verifier.finite_campaigns import (
    FiniteCampaignError,
    rehash_prop1224_chunk,
)


class RationalElementaryFunctionTests(unittest.TestCase):
    def test_module_contains_no_native_float_literals(self) -> None:
        source = Path(directed.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        floats = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        ]
        self.assertEqual(floats, [])

    def test_log_and_exp_bounds_are_rational_and_directed(self) -> None:
        log_two = directed.log_interval(
            directed.RationalInterval.exact(2), bits=96, terms=32
        )
        self.assertLess(log_two.lower, Fraction(693_148, 10**6))
        self.assertGreater(log_two.upper, Fraction(693_147, 10**6))
        self.assertLess(log_two.upper - log_two.lower, Fraction(1, 10**20))

        exp_one = directed.exp_interval(
            directed.RationalInterval.exact(1), bits=96, terms=32
        )
        self.assertLess(Fraction(2_718, 1_000), exp_one.lower)
        self.assertLess(exp_one.upper, Fraction(2_719, 1_000))
        self.assertLess(exp_one.upper - exp_one.lower, Fraction(1, 10**20))

    def test_integer_cube_root_is_outward_and_exact_on_cubes(self) -> None:
        exact = directed.integer_cube_root_interval(27, 80)
        self.assertEqual(exact, directed.RationalInterval.exact(3))
        noncube = directed.integer_cube_root_interval(2, 80)
        self.assertLess(noncube.lower**3, 2)
        self.assertGreater(noncube.upper**3, 2)
        self.assertEqual(
            noncube.upper - noncube.lower, Fraction(1, 1 << 80)
        )


class DirectedProp1224Tests(unittest.TestCase):
    Q = 6_469_693_230

    def test_parameters_reconstruct_source_window_without_supplied_values(self) -> None:
        parameters = directed.prop1224_directed_parameters(
            self.Q, bits=96, log_terms=32
        )
        self.assertEqual(
            parameters.prime_factors,
            (2, 3, 5, 7, 11, 13, 17, 19, 23, 29),
        )
        self.assertLess(parameters.varpi.lower, parameters.varpi.upper)
        self.assertLess(Fraction(585), parameters.varpi.lower)
        self.assertLess(parameters.varpi.upper, Fraction(586))
        self.assertLess(parameters.lambda_.lower, parameters.lambda_.upper)
        self.assertLess(Fraction(720), parameters.lambda_.lower)
        self.assertLess(parameters.lambda_.lower, Fraction(721))
        self.assertLess(Fraction(721), parameters.lambda_.upper)
        self.assertLess(parameters.lambda_.upper, Fraction(722))
        self.assertLess(
            parameters.varpi.upper - parameters.varpi.lower,
            Fraction(3, 1_000),
        )

    def test_complete_bounded_window_has_directed_positive_margins(self) -> None:
        sample = directed.create_directed_prop1224_sample(
            self.Q, bits=96, log_terms=32, max_pairs=1_000
        )
        self.assertEqual(
            (sample.window.pairs[0].k, sample.window.pairs[-1].k),
            (586, 721),
        )
        self.assertEqual(len(sample.window.pairs), 136)
        self.assertTrue(
            all(
                Fraction(
                    pair.margin_lower_numerator,
                    pair.margin_lower_denominator,
                )
                > 1
                for pair in sample.window.pairs
            )
        )
        self.assertFalse(sample.native_float_used_in_decisions)
        self.assertFalse(sample.full_source_campaign)
        self.assertFalse(sample.lean_realization_proved)
        first_margin = directed.prop1224_directed_margin(
            self.Q, 586, bits=96, log_terms=32
        )
        self.assertEqual(
            first_margin.lower,
            Fraction(
                sample.window.pairs[0].margin_lower_numerator,
                sample.window.pairs[0].margin_lower_denominator,
            ),
        )
        self.assertEqual(directed.verify_directed_prop1224_sample(sample), 136)

    def test_resource_guard_never_truncates_and_tampering_fails_replay(self) -> None:
        with self.assertRaisesRegex(FiniteCampaignError, "bounded-sample guard"):
            directed.create_directed_prop1224_sample(
                self.Q, bits=96, log_terms=32, max_pairs=100
            )

        sample = directed.create_directed_prop1224_sample(
            self.Q, bits=96, log_terms=32, max_pairs=1_000
        )
        changed_pair = replace(
            sample.window.pairs[0],
            margin_lower_numerator=sample.window.pairs[0].margin_lower_numerator + 1,
        )
        changed_window = replace(
            sample.window,
            pairs=(changed_pair,) + sample.window.pairs[1:],
        )
        with self.assertRaisesRegex(FiniteCampaignError, "replay differs"):
            directed.verify_directed_prop1224_sample(
                replace(sample, window=changed_window)
            )

    def test_directed_rows_use_and_strengthen_existing_hash_chunks(self) -> None:
        chunk = directed.create_directed_prop1224_chunk(
            (self.Q, self.Q + 210),
            bits=96,
            log_terms=32,
            max_pairs_per_q=1_000,
            previous_hash="0" * 64,
        )
        result = directed.verify_directed_prop1224_chunk(
            chunk,
            bits=96,
            log_terms=32,
            max_pairs_per_q=1_000,
        )
        self.assertEqual((result.q_rows, result.pairs), (2, 136))
        self.assertTrue(result.structural_hash_and_scheduler_verified)
        self.assertTrue(result.endpoint_enclosures_recomputed)
        self.assertTrue(result.margin_enclosures_recomputed)
        self.assertFalse(result.full_source_campaign)
        self.assertFalse(result.lean_atom_discharged)

        first_window = chunk.windows[0]
        changed_pair = replace(
            first_window.pairs[0],
            margin_lower_numerator=0,
            margin_lower_denominator=1,
        )
        changed_window = replace(
            first_window,
            pairs=(changed_pair,) + first_window.pairs[1:],
        )
        changed_chunk = rehash_prop1224_chunk(
            replace(chunk, windows=(changed_window,) + chunk.windows[1:])
        )
        with self.assertRaisesRegex(FiniteCampaignError, "differs on replay"):
            directed.verify_directed_prop1224_chunk(
                changed_chunk,
                bits=96,
                log_terms=32,
                max_pairs_per_q=1_000,
            )


if __name__ == "__main__":
    unittest.main()
