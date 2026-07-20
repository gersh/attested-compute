# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from fractions import Fraction
import hashlib
from math import gcd
from pathlib import Path
import tempfile
import unittest

from tg_verifier.finite_campaigns import (
    PROP1224_Q_END,
    mobius_linear,
    prop1224_first_extension_q,
    prop1224_source_q_count,
    ramare_g_prefixes,
)
from tg_verifier.campaign_io import canonical_json_bytes, load_json
from tg_verifier.prop1224_campaign import (
    CampaignState,
    Prop1224CampaignError,
    _advance_q,
    _expected_config,
    _process_chunk,
    _q_at_rank,
    _q_rank,
    iter_totient_squarefree_segment,
    replay_campaign,
    run_campaign,
    verify_campaign,
)


class Prop1224FullCampaignTests(unittest.TestCase):
    def test_rank_scheduler_has_exact_source_cardinality(self) -> None:
        dense = 3_300_000_000 - 1
        first_extension = prop1224_first_extension_q()
        self.assertEqual(_q_at_rank(0), 1)
        self.assertEqual(_q_at_rank(dense - 1), 3_300_000_000 - 1)
        self.assertEqual(_q_at_rank(dense), first_extension)
        self.assertEqual(_q_rank(first_extension), dense)
        self.assertEqual(
            _q_at_rank(prop1224_source_q_count()), PROP1224_Q_END
        )
        self.assertEqual(_q_rank(PROP1224_Q_END), prop1224_source_q_count())
        self.assertEqual(_advance_q(1, prop1224_source_q_count()), PROP1224_Q_END)

    def test_segmented_phi_and_squarefree_rows_are_exact(self) -> None:
        rows = list(iter_totient_squarefree_segment(1, 101, segment_size=17))
        mu = mobius_linear(100)
        for r, phi_r, squarefree in rows:
            expected_phi = sum(1 for candidate in range(1, r + 1) if gcd(candidate, r) == 1)
            self.assertEqual(phi_r, expected_phi)
            self.assertEqual(squarefree, mu[r] != 0)

        scale = 1 << 64
        lower = 0
        upper = 0
        for r, phi_r, squarefree in rows[:80]:
            if squarefree and gcd(r, 30) == 1:
                lower += scale // phi_r
                upper += (scale + phi_r - 1) // phi_r
        exact = ramare_g_prefixes(30, (80,))[80]
        self.assertLessEqual(Fraction(lower, scale), exact)
        self.assertLessEqual(exact, Fraction(upper, scale))

    def test_q1_window_is_streamed_across_a_real_k_boundary(self) -> None:
        config = _expected_config(
            precision_bits=64,
            log_series_terms=32,
            r_steps_per_chunk=71_580,
            q_rows_per_chunk=1,
            sieve_segment_size=20_000,
        )
        receipt = _process_chunk(
            CampaignState(1, 1, 0, 0),
            previous_receipt_hash="0" * 64,
            config=config,
        )
        self.assertEqual(receipt["incoming_q"], 1)
        self.assertEqual(receipt["outgoing_q"], 1)
        self.assertEqual(receipt["outgoing_next_r"], 71_581)
        self.assertEqual(receipt["r_steps"], 71_580)
        self.assertEqual(receipt["conservative_k_rows_checked"], 6)
        self.assertIsNotNone(receipt["minimum_margin_lower"])

    def test_completed_q_transition_uses_compact_receipt(self) -> None:
        config = _expected_config(
            precision_bits=64,
            log_series_terms=32,
            r_steps_per_chunk=1_000,
            q_rows_per_chunk=1,
            sieve_segment_size=64,
        )
        receipt = _process_chunk(
            CampaignState(1_000, 1, 0, 0),
            previous_receipt_hash="0" * 64,
            config=config,
        )
        self.assertEqual(receipt["q_rows_completed"], 1)
        self.assertEqual(receipt["outgoing_q"], 1_001)
        self.assertEqual(receipt["outgoing_next_r"], 1)
        self.assertEqual(receipt["conservative_k_rows_checked"], 190)
        self.assertGreaterEqual(Fraction(*receipt["minimum_margin_lower"]), 0)

    def test_run_resume_verify_and_independent_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = run_campaign(
                root,
                precision_bits=64,
                log_series_terms=32,
                r_steps_per_chunk=40,
                q_rows_per_chunk=3,
                sieve_segment_size=13,
                max_chunks=1,
            )
            self.assertFalse(first.complete)
            self.assertEqual(first.receipts, 1)
            self.assertEqual(first.next_q, 1)
            self.assertEqual(first.next_r, 41)
            structural = verify_campaign(root)
            self.assertTrue(structural.compact_chain_verified)
            self.assertFalse(structural.fresh_arithmetic_replay)
            replayed = replay_campaign(root)
            self.assertTrue(replayed.fresh_arithmetic_replay)
            second = run_campaign(
                root,
                precision_bits=64,
                log_series_terms=32,
                r_steps_per_chunk=40,
                q_rows_per_chunk=3,
                sieve_segment_size=13,
                max_chunks=1,
            )
            self.assertEqual(second.receipts, 2)
            self.assertEqual(second.next_r, 81)

    def test_resume_rejects_changed_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_campaign(
                root,
                precision_bits=64,
                log_series_terms=32,
                r_steps_per_chunk=20,
                q_rows_per_chunk=2,
                sieve_segment_size=11,
                max_chunks=1,
            )
            with self.assertRaisesRegex(Prop1224CampaignError, "configuration"):
                run_campaign(
                    root,
                    precision_bits=64,
                    log_series_terms=32,
                    r_steps_per_chunk=21,
                    q_rows_per_chunk=2,
                    sieve_segment_size=11,
                    max_chunks=1,
                )

    def test_rehashed_arithmetic_tampering_fails_independent_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_campaign(
                root,
                precision_bits=64,
                log_series_terms=32,
                r_steps_per_chunk=20,
                q_rows_per_chunk=2,
                sieve_segment_size=11,
                max_chunks=1,
            )
            path = root / "receipt-0000000000.json"
            receipt = load_json(path, require_canonical=True)
            receipt["arithmetic_digest"] = "f" * 64
            body = {key: value for key, value in receipt.items() if key != "receipt_hash"}
            receipt["receipt_hash"] = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
            path.write_bytes(canonical_json_bytes(receipt))
            self.assertTrue(verify_campaign(root).compact_chain_verified)
            with self.assertRaisesRegex(
                Prop1224CampaignError, "fresh arithmetic replay differs"
            ):
                replay_campaign(root)


if __name__ == "__main__":
    unittest.main()
