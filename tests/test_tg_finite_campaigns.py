#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Focused exact tests for CH25 psi and Proposition 12.2.4 streams."""

from __future__ import annotations

import ast
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import unittest

from tg_verifier import finite_campaigns as tg
from tg_verifier.catalog import ATOMS_BY_ID


class CatalogLinkageTests(unittest.TestCase):
    def test_atom_and_algorithm_ids_match_the_checked_catalog(self) -> None:
        self.assertEqual(
            ATOMS_BY_ID[tg.PSI_ATOM].verifier, tg.PSI_ALGORITHM
        )
        self.assertEqual(
            ATOMS_BY_ID[tg.PROP1224_ATOM].verifier,
            tg.PROP1224_ALGORITHM,
        )

    def test_exact_reference_source_contains_no_float_literals(self) -> None:
        source = Path(tg.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        floats = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        ]
        self.assertEqual(floats, [])


class PrimePowerCoverageTests(unittest.TestCase):
    def test_segmented_prime_iterator_matches_known_interval(self) -> None:
        self.assertEqual(
            list(tg.iter_primes_segmented(90, 121, segment_size=7)),
            [97, 101, 103, 107, 109, 113],
        )

    def test_exact_prime_power_events_through_twenty(self) -> None:
        self.assertEqual(
            tg.prime_power_events(2, 21, segment_size=5),
            (
                tg.PrimePower(2, 2, 1),
                tg.PrimePower(3, 3, 1),
                tg.PrimePower(4, 2, 2),
                tg.PrimePower(5, 5, 1),
                tg.PrimePower(7, 7, 1),
                tg.PrimePower(8, 2, 3),
                tg.PrimePower(9, 3, 2),
                tg.PrimePower(11, 11, 1),
                tg.PrimePower(13, 13, 1),
                tg.PrimePower(16, 2, 4),
                tg.PrimePower(17, 17, 1),
                tg.PrimePower(19, 19, 1),
            ),
        )

    def test_chunk_boundaries_do_not_lose_higher_prime_powers(self) -> None:
        combined = (
            tg.prime_power_events(2, 10, segment_size=3)
            + tg.prime_power_events(10, 17, segment_size=3)
            + tg.prime_power_events(17, 33, segment_size=3)
        )
        self.assertEqual(combined, tg.prime_power_events(2, 33, segment_size=4))


class RationalLogTests(unittest.TestCase):
    def test_log_two_enclosure_is_exact_rational_and_narrow(self) -> None:
        lower, upper = tg.fixed_log_bounds(2, 96, 40)
        scale = 1 << 96
        self.assertLessEqual(lower, upper)
        self.assertGreater(Fraction(lower, scale), Fraction(2, 3))
        self.assertLess(Fraction(upper, scale), Fraction(3, 4))
        self.assertLessEqual(upper - lower, 1)

    def test_more_terms_nest_before_fixed_point_rounding(self) -> None:
        low_short, high_short = tg._positive_log_series_bounds(19, 16, 4)
        low_long, high_long = tg._positive_log_series_bounds(19, 16, 12)
        self.assertLessEqual(low_short, low_long)
        self.assertLessEqual(high_long, high_short)
        self.assertLess(high_long - low_long, high_short - low_short)

    def test_exact_interfaces_reject_floats_and_booleans(self) -> None:
        with self.assertRaises(tg.FiniteCampaignError):
            tg.fixed_log_bounds(2, 64.0, 32)  # type: ignore[arg-type]
        with self.assertRaises(tg.FiniteCampaignError):
            tuple(tg.iter_primes_segmented(True, 10))


class PsiCertificateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.chunks = tg.create_psi_certificate(
            1_000,
            chunk_span=137,
            scale_bits=96,
            series_terms=40,
            segment_size=53,
        )

    def test_bounded_chain_recomputes_all_three_layers(self) -> None:
        result = tg.verify_psi_chain(
            self.chunks, expected_limit=1_000, segment_size=47
        )
        self.assertEqual(result.events, 193)
        self.assertTrue(result.exact_prime_power_coverage_verified)
        self.assertTrue(result.rational_log_enclosures_verified)
        self.assertTrue(result.exact_envelope_inequalities_verified)
        self.assertFalse(result.full_source_range)
        self.assertFalse(result.lean_atom_discharged)

    def test_generator_path_is_consumed_as_a_bounded_stream(self) -> None:
        stream = tg.iter_psi_certificate(
            1_000,
            chunk_span=137,
            scale_bits=96,
            series_terms=40,
            segment_size=53,
        )
        result = tg.verify_psi_chain(
            stream, expected_limit=1_000, segment_size=47
        )
        self.assertEqual((result.chunks, result.events), (8, 193))

    def test_valid_hash_cannot_hide_a_spurious_event(self) -> None:
        first = self.chunks[0]
        changed_event = replace(first.events[0], prime=3)
        changed = replace(
            first, events=(changed_event,) + first.events[1:]
        )
        changed = tg.rehash_psi_chunk(changed)
        with self.assertRaisesRegex(tg.FiniteCampaignError, "spurious|missing"):
            tg.verify_psi_chunk(changed, segment_size=50)

    def test_valid_hash_cannot_hide_a_wrong_log_interval(self) -> None:
        first = self.chunks[0]
        changed_event = replace(
            first.events[0], log_upper=first.events[0].log_upper + 1
        )
        changed = tg.rehash_psi_chunk(
            replace(first, events=(changed_event,) + first.events[1:])
        )
        with self.assertRaisesRegex(tg.FiniteCampaignError, "log bounds"):
            tg.verify_psi_chunk(changed)

    def test_chain_rejects_range_hash_and_state_gaps(self) -> None:
        with self.assertRaisesRegex(tg.FiniteCampaignError, "range coverage"):
            tg.verify_psi_chain(
                (self.chunks[0],) + self.chunks[2:], expected_limit=1_000
            )
        broken = replace(self.chunks[1], previous_hash=tg.ZERO_SHA256)
        broken = tg.rehash_psi_chunk(broken)
        with self.assertRaisesRegex(tg.FiniteCampaignError, "hash chain"):
            tg.verify_psi_chain(
                (self.chunks[0], broken) + self.chunks[2:],
                expected_limit=1_000,
            )

    def test_wrong_terminal_range_is_not_reported_as_coverage(self) -> None:
        with self.assertRaisesRegex(tg.FiniteCampaignError, "does not end"):
            tg.verify_psi_chain(self.chunks, expected_limit=999)

    def test_chain_type_guards_fail_closed_before_field_access(self) -> None:
        with self.assertRaisesRegex(tg.FiniteCampaignError, "entry 0"):
            tg.verify_psi_chain(iter((object(),)), expected_limit=100)  # type: ignore[arg-type]
        malformed = replace(self.chunks[0], events=list(self.chunks[0].events))
        with self.assertRaisesRegex(tg.FiniteCampaignError, "stored as a tuple"):
            tg.verify_psi_chunk(malformed)  # type: ignore[arg-type]


class Prop1224SchedulerTests(unittest.TestCase):
    def test_exact_transition_between_source_range_branches(self) -> None:
        first_extension = tg.prop1224_first_extension_q()
        self.assertEqual(first_extension, 3_300_000_060)
        self.assertEqual(
            tg.prop1224_next_q(tg.PROP1224_Q_SPLIT - 1), first_extension
        )
        self.assertTrue(tg.prop1224_q_is_admissible(first_extension))
        self.assertFalse(tg.prop1224_q_is_admissible(tg.PROP1224_Q_SPLIT))

    def test_last_extension_value_transitions_to_terminal_sentinel(self) -> None:
        first = tg.prop1224_first_extension_q()
        last = first + (
            (tg.PROP1224_Q_END - 1 - first) // tg.PROP1224_DIVISOR
        ) * tg.PROP1224_DIVISOR
        self.assertTrue(tg.prop1224_q_is_admissible(last))
        self.assertEqual(tg.prop1224_next_q(last), tg.PROP1224_Q_END)
        self.assertEqual(tg.prop1224_source_q_count(), 3_389_047_618)


class Prop1224StructuralCertificateTests(unittest.TestCase):
    @staticmethod
    def _window(q: int, margin: Fraction = Fraction(1, 10)) -> tg.Prop1224Window:
        return tg.create_prop1224_window(
            q=q,
            varpi_lower=Fraction(3, 2),
            varpi_upper=Fraction(8, 5),
            lambda_lower=Fraction(4),
            lambda_upper=Fraction(9, 2),
            margin_lower=lambda _k: margin,
        )

    def test_conservative_window_uses_outward_endpoints(self) -> None:
        window = self._window(1)
        self.assertEqual(tg.prop1224_conservative_ks(window), (2, 3, 4))
        self.assertEqual(
            [Fraction(pair.g_numerator, pair.g_denominator) for pair in window.pairs],
            [Fraction(2), Fraction(5, 2), Fraction(5, 2)],
        )
        self.assertEqual(tg.verify_prop1224_window(window), 3)

    def test_exact_gq_respects_coprimality(self) -> None:
        self.assertEqual(
            tg.ramare_g_prefixes(2, (1, 2, 3, 4)),
            {
                1: Fraction(1),
                2: Fraction(1),
                3: Fraction(3, 2),
                4: Fraction(3, 2),
            },
        )
        with self.assertRaisesRegex(tg.FiniteCampaignError, "safety limit"):
            tg.ramare_g_prefixes(1, (tg._MAX_HASHED_ROWS + 1,))

    def test_partial_chain_is_explicitly_not_an_analytic_verification(self) -> None:
        first = tg.create_prop1224_chunk((self._window(1),))
        second = tg.create_prop1224_chunk(
            (self._window(2),), previous_hash=first.record_hash
        )
        result = tg.verify_prop1224_chain(
            (first, second), expected_next_q=3
        )
        self.assertEqual((result.q_rows, result.pairs), (2, 6))
        self.assertTrue(result.exact_q_scheduler_coverage_verified)
        self.assertTrue(result.conservative_k_coverage_verified)
        self.assertTrue(result.exact_gq_arithmetic_verified)
        self.assertFalse(result.transcendental_enclosure_semantics_verified)
        self.assertFalse(result.full_source_q_coverage)
        self.assertFalse(result.lean_atom_discharged)

    def test_chain_accepts_one_pass_iterators(self) -> None:
        first = tg.create_prop1224_chunk((self._window(1),))
        second = tg.create_prop1224_chunk(
            (self._window(2),), previous_hash=first.record_hash
        )
        result = tg.verify_prop1224_chain(
            iter((first, second)), expected_next_q=3
        )
        self.assertEqual(result.chunks, 2)

    def test_rehashed_missing_k_is_rejected(self) -> None:
        window = self._window(1)
        changed_window = replace(window, pairs=window.pairs[:-1])
        chunk = tg.create_prop1224_chunk((window,))
        changed = tg.rehash_prop1224_chunk(
            replace(chunk, windows=(changed_window,))
        )
        with self.assertRaisesRegex(tg.FiniteCampaignError, "complete conservative"):
            tg.verify_prop1224_chunk(changed)

    def test_rehashed_wrong_gq_is_rejected(self) -> None:
        window = self._window(1)
        pair = replace(window.pairs[0], g_numerator=3)
        changed_window = replace(window, pairs=(pair,) + window.pairs[1:])
        chunk = tg.create_prop1224_chunk((window,))
        changed = tg.rehash_prop1224_chunk(
            replace(chunk, windows=(changed_window,))
        )
        with self.assertRaisesRegex(tg.FiniteCampaignError, "incorrect exact"):
            tg.verify_prop1224_chunk(changed)

    def test_negative_supplied_margin_fails_closed(self) -> None:
        window = self._window(1, Fraction(-1, 10))
        with self.assertRaisesRegex(tg.FiniteCampaignError, "negative supplied"):
            tg.verify_prop1224_window(window)

    def test_noncanonical_rationals_and_q_gaps_fail_closed(self) -> None:
        window = self._window(1)
        bad_fraction = replace(
            window,
            varpi_lower_numerator=6,
            varpi_lower_denominator=4,
        )
        with self.assertRaisesRegex(tg.FiniteCampaignError, "lowest terms"):
            tg.verify_prop1224_window(bad_fraction)
        with self.assertRaisesRegex(tg.FiniteCampaignError, "ordering"):
            tg.create_prop1224_chunk((self._window(1), self._window(3)))

    def test_missing_margin_and_oversized_window_fail_before_materialization(self) -> None:
        with self.assertRaisesRegex(tg.FiniteCampaignError, "missing.*k=3"):
            tg.create_prop1224_window(
                q=1,
                varpi_lower=Fraction(2),
                varpi_upper=Fraction(2),
                lambda_lower=Fraction(4),
                lambda_upper=Fraction(4),
                margin_lower={2: Fraction(1)},
            )

        oversized = tg.Prop1224Window(
            q=1,
            varpi_lower_numerator=1,
            varpi_lower_denominator=1,
            varpi_upper_numerator=1,
            varpi_upper_denominator=1,
            lambda_lower_numerator=30_000_002,
            lambda_lower_denominator=1,
            lambda_upper_numerator=30_000_002,
            lambda_upper_denominator=1,
            pairs=(),
        )
        with self.assertRaisesRegex(tg.FiniteCampaignError, "row safety limit"):
            tg.prop1224_conservative_ks(oversized)

    def test_prop_chain_type_guards_fail_closed(self) -> None:
        with self.assertRaisesRegex(tg.FiniteCampaignError, "entry 0"):
            tg.verify_prop1224_chain(iter((object(),)))  # type: ignore[arg-type]
        window = self._window(1)
        chunk = tg.create_prop1224_chunk((window,))
        malformed = replace(chunk, windows=list(chunk.windows))
        with self.assertRaisesRegex(tg.FiniteCampaignError, "stored as a tuple"):
            tg.verify_prop1224_chunk(malformed)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
