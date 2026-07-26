# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Focused tests for independent Proposition 12.2.4 q-rank leaves."""

from __future__ import annotations

from dataclasses import replace
import unittest

from tg_verifier.affine_guard_certificate import AffineGuardCertificateError
from tg_verifier.finite_campaigns import prop1224_first_extension_q
from tg_verifier.prop1224_factor_plan import (
    PRODUCTION_DENSE_RANK_END,
    PRODUCTION_RANK_END,
    production_factor_plan,
    q_at_rank,
)
from tg_verifier.prop1224_parallel_campaign import (
    Prop1224ParallelCampaignError,
    leaf_from_directed_report,
    make_directed_plan,
    run_directed_shard,
    verify_directed_leaves,
)


class Prop1224ParallelCampaignTests(unittest.TestCase):
    def test_production_shape_is_literal_and_isolates_q_one(self) -> None:
        plan = production_factor_plan()
        self.assertEqual((plan.domain_lower, plan.domain_upper), (0, PRODUCTION_RANK_END))
        self.assertEqual((plan.shards[0].lower, plan.shards[0].upper), (0, 1))
        self.assertTrue(
            any(shard.upper == PRODUCTION_DENSE_RANK_END for shard in plan.shards)
        )
        self.assertEqual(q_at_rank(PRODUCTION_RANK_END), 22_000_000_000)

    def test_representative_complete_row_matches_directed_reference(self) -> None:
        q = 6_469_693_230
        rank = PRODUCTION_DENSE_RANK_END + (
            q - prop1224_first_extension_q()
        ) // 210
        plan = make_directed_plan(rank_lower=rank, rank_upper=rank + 1, leaf_rows=1)
        report = run_directed_shard(
            plan=plan,
            shard_index=0,
            precision_bits=96,
            log_series_terms=32,
            sieve_segment_size=1_000,
        )
        self.assertEqual(report.first_q, q)
        self.assertEqual(report.r_steps, 721)
        self.assertEqual(report.conservative_k_rows_checked, 136)
        self.assertGreater(report.minimum_margin_lower[0], report.minimum_margin_lower[1])
        leaf = leaf_from_directed_report(plan=plan, report=report)
        result = verify_directed_leaves(plan=plan, leaves=(leaf,))
        self.assertEqual(result.final_state, (rank + 1,))

        with self.assertRaisesRegex(Prop1224ParallelCampaignError, "plan range"):
            leaf_from_directed_report(
                plan=plan,
                report=replace(report, q_rows_completed=0),
            )
        with self.assertRaisesRegex(Prop1224ParallelCampaignError, "unsafe"):
            leaf_from_directed_report(
                plan=plan,
                report=replace(report, lean_atom_discharged=True),
            )

    def test_missing_or_reordered_leaf_fails_closed(self) -> None:
        lower = PRODUCTION_DENSE_RANK_END + 1_000
        plan = make_directed_plan(
            rank_lower=lower,
            rank_upper=lower + 2,
            leaf_rows=1,
        )
        reports = tuple(
            run_directed_shard(
                plan=plan,
                shard_index=index,
                precision_bits=96,
                log_series_terms=32,
                sieve_segment_size=1_000,
            )
            for index in range(2)
        )
        leaves = tuple(
            leaf_from_directed_report(plan=plan, report=report)
            for report in reports
        )
        verify_directed_leaves(plan=plan, leaves=leaves)
        with self.assertRaises(AffineGuardCertificateError):
            verify_directed_leaves(plan=plan, leaves=leaves[:1])
        with self.assertRaises(AffineGuardCertificateError):
            verify_directed_leaves(plan=plan, leaves=tuple(reversed(leaves)))


if __name__ == "__main__":
    unittest.main()
