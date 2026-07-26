#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact tests for generic affine-guard shard certificates."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from tg_verifier.affine_guard_certificate import (
    AffineGuardCertificateError,
    AffineGuardLeaf,
    AffineGuardTransition,
    EMPTY_EXCEPTION_ROOT_SHA256,
    FixedShardPlan,
    ShardRange,
    TightGuardWitness,
    affine_guard_leaf_merkle_root,
    compose_affine_guards,
    exception_merkle_root,
    exclusive_scan_from_root,
    make_affine_guard_leaf,
    verify_affine_guard_certificate,
)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def witness(row: int, guard: int) -> TightGuardWitness:
    return TightGuardWitness(row_index=row, prefix_delta=0, row_guard=guard)


class AffineTransitionTests(unittest.TestCase):
    def test_composition_is_the_exact_affine_guard_formula(self) -> None:
        first = AffineGuardTransition(
            delta=(2, -1), lower_guard=(0, -5), upper_guard=(10, 5)
        )
        second = AffineGuardTransition(
            delta=(-3, 4), lower_guard=(3, -6), upper_guard=(12, 10)
        )
        composed = compose_affine_guards(first, second)
        self.assertEqual(composed.delta, (-1, 3))
        self.assertEqual(composed.lower_guard, (1, -5))
        self.assertEqual(composed.upper_guard, (10, 5))

        # Exhaustively check the semantic equivalence on a surrounding box.
        for x in range(-3, 15):
            for y in range(-9, 14):
                state = (x, y)
                sequential = first.accepts(state)
                if sequential:
                    sequential = second.accepts(first.apply(state))
                self.assertEqual(composed.accepts(state), sequential)
                if sequential:
                    self.assertEqual(
                        composed.apply(state), second.apply(first.apply(state))
                    )

    def test_composition_is_associative(self) -> None:
        transitions = (
            AffineGuardTransition((2, -1), (-20, -20), (20, 20)),
            AffineGuardTransition((-3, 4), (-15, -18), (22, 19)),
            AffineGuardTransition((5, 2), (-12, -14), (17, 23)),
        )
        left = compose_affine_guards(
            compose_affine_guards(transitions[0], transitions[1]), transitions[2]
        )
        right = compose_affine_guards(
            transitions[0], compose_affine_guards(transitions[1], transitions[2])
        )
        self.assertEqual(left, right)

    def test_invalid_and_incompatible_transitions_are_rejected(self) -> None:
        with self.assertRaisesRegex(AffineGuardCertificateError, "empty guard"):
            AffineGuardTransition((0,), (2,), (1,))
        with self.assertRaisesRegex(AffineGuardCertificateError, "same dimension"):
            AffineGuardTransition((0, 1), (0,), (1,))
        with self.assertRaisesRegex(AffineGuardCertificateError, "must be an integer"):
            AffineGuardTransition((True,), (0,), (1,))  # type: ignore[arg-type]

        first = AffineGuardTransition((10,), (0,), (0,))
        second = AffineGuardTransition((0,), (0,), (0,))
        with self.assertRaisesRegex(AffineGuardCertificateError, "no admissible"):
            compose_affine_guards(first, second)

    def test_exclusive_scan_derives_inputs_from_one_root(self) -> None:
        transitions = (
            AffineGuardTransition((2,), (0,), (10,)),
            AffineGuardTransition((-1,), (1,), (12,)),
            AffineGuardTransition((3,), (-1,), (9,)),
        )
        scan = exclusive_scan_from_root((2,), transitions)
        self.assertEqual(scan.incoming_states, ((2,), (4,), (3,)))
        self.assertEqual(scan.final_state, (6,))
        self.assertEqual(scan.aggregate_transition.delta, (4,))  # type: ignore[union-attr]
        self.assertEqual(scan.aggregate_transition.lower_guard, (0,))  # type: ignore[union-attr]
        self.assertEqual(scan.aggregate_transition.upper_guard, (8,))  # type: ignore[union-attr]

        with self.assertRaisesRegex(AffineGuardCertificateError, "shard 0 guard"):
            exclusive_scan_from_root((99,), transitions)


class FixedPlanTests(unittest.TestCase):
    def test_plan_has_literal_ranges_and_stable_content_hash(self) -> None:
        plan = FixedShardPlan.from_ranges(
            algorithm="test_affine_stream_v1",
            state_dimension=1,
            ranges=((100, 103), (103, 106), (106, 108)),
        )
        self.assertEqual(
            [(item.index, item.lower, item.upper, item.work_count) for item in plan.shards],
            [(0, 100, 103, 3), (1, 103, 106, 3), (2, 106, 108, 2)],
        )
        self.assertEqual(plan, FixedShardPlan.from_dict(plan.to_dict()))
        self.assertEqual(
            plan.plan_sha256,
            "2f99cebd590ee51c9fc43ad5e4f07738f08558775c5d6595afb256513396c208",
        )

    def test_gap_overlap_duplicate_and_bad_work_count_are_rejected(self) -> None:
        with self.assertRaisesRegex(AffineGuardCertificateError, "gap before"):
            FixedShardPlan(
                "algorithm",
                1,
                0,
                9,
                (ShardRange(0, 0, 4, 4), ShardRange(1, 5, 9, 4)),
            )
        with self.assertRaisesRegex(AffineGuardCertificateError, "overlap before"):
            FixedShardPlan(
                "algorithm",
                1,
                0,
                9,
                (ShardRange(0, 0, 5, 5), ShardRange(1, 4, 9, 5)),
            )
        with self.assertRaisesRegex(AffineGuardCertificateError, "duplicate shard index"):
            FixedShardPlan(
                "algorithm",
                1,
                0,
                8,
                (ShardRange(0, 0, 4, 4), ShardRange(0, 4, 8, 4)),
            )
        with self.assertRaisesRegex(AffineGuardCertificateError, "duplicate shard range"):
            FixedShardPlan(
                "algorithm",
                1,
                0,
                4,
                (ShardRange(0, 0, 4, 4), ShardRange(1, 0, 4, 4)),
            )
        with self.assertRaisesRegex(AffineGuardCertificateError, "work_count"):
            ShardRange(0, 0, 4, 3)


class ShardCertificateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = FixedShardPlan.from_ranges(
            algorithm="test_affine_stream_v1",
            state_dimension=1,
            ranges=((100, 103), (103, 106), (106, 108)),
        )
        transitions = (
            AffineGuardTransition((2,), (0,), (10,)),
            AffineGuardTransition((-1,), (1,), (12,)),
            AffineGuardTransition((3,), (-1,), (9,)),
        )
        self.leaves = tuple(
            make_affine_guard_leaf(
                plan=self.plan,
                shard_index=index,
                row_root_sha256=digest(f"rows-{index}"),
                transition=transition,
                lower_tight_witnesses=(
                    witness(self.plan.shards[index].lower, transition.lower_guard[0]),
                ),
                upper_tight_witnesses=(
                    witness(self.plan.shards[index].upper - 1, transition.upper_guard[0]),
                ),
                exception_root_sha256=EMPTY_EXCEPTION_ROOT_SHA256,
            )
            for index, transition in enumerate(transitions)
        )

    def test_full_verification_binds_plan_scan_rows_witnesses_and_exceptions(self) -> None:
        result = verify_affine_guard_certificate(
            plan=self.plan, root_state=(2,), leaves=self.leaves
        )
        self.assertEqual(
            self.leaves,
            tuple(AffineGuardLeaf.from_dict(leaf.to_dict()) for leaf in self.leaves),
        )
        self.assertEqual(result.incoming_states, ((2,), (4,), (3,)))
        self.assertEqual(result.final_state, (6,))
        self.assertEqual(result.aggregate_transition.delta, (4,))
        self.assertEqual(
            result.leaf_merkle_root_sha256,
            affine_guard_leaf_merkle_root(self.leaves),
        )
        self.assertEqual(
            result.certificate_root_sha256,
            "4655ffefd61add2021b9275c9f1cf04af9c7192b6a6952c3206d5a16d21211c7",
        )
        verify_affine_guard_certificate(
            plan=self.plan,
            root_state=(2,),
            leaves=self.leaves,
            expected_certificate_root_sha256=result.certificate_root_sha256,
        )
        with self.assertRaisesRegex(AffineGuardCertificateError, "expected commitment"):
            verify_affine_guard_certificate(
                plan=self.plan,
                root_state=(2,),
                leaves=self.leaves,
                expected_certificate_root_sha256="0" * 64,
            )

        # Each field named in the certificate contract affects the leaf hash.
        leaf = self.leaves[0]
        mutations = (
            replace(leaf, row_root_sha256=digest("different rows")),
            replace(leaf, exception_root_sha256=digest("one exception")),
            replace(
                leaf,
                lower_tight_witnesses=(
                    TightGuardWitness(100, 7, 7),  # still derives guard 0
                ),
            ),
        )
        for changed in mutations:
            with self.subTest(changed=changed):
                self.assertNotEqual(changed.leaf_sha256, leaf.leaf_sha256)

    def test_plan_and_leaf_metadata_cannot_be_substituted(self) -> None:
        other_plan = FixedShardPlan.from_ranges(
            algorithm="different_algorithm_v1",
            state_dimension=1,
            ranges=((100, 103), (103, 106), (106, 108)),
        )
        with self.assertRaisesRegex(AffineGuardCertificateError, "different plan SHA"):
            self.leaves[0].validate_against(other_plan)

        wrong_bounds = replace(self.leaves[0], lower=99, work_count=4)
        with self.assertRaisesRegex(AffineGuardCertificateError, "do not match"):
            wrong_bounds.validate_against(self.plan)

    def test_missing_reordered_and_duplicate_leaves_are_rejected(self) -> None:
        with self.assertRaisesRegex(AffineGuardCertificateError, "plan requires"):
            verify_affine_guard_certificate(
                plan=self.plan, root_state=(2,), leaves=self.leaves[:-1]
            )
        with self.assertRaisesRegex(AffineGuardCertificateError, "fixed plan order"):
            verify_affine_guard_certificate(
                plan=self.plan,
                root_state=(2,),
                leaves=(self.leaves[1], self.leaves[0], self.leaves[2]),
            )
        with self.assertRaisesRegex(AffineGuardCertificateError, "duplicate shard leaf"):
            verify_affine_guard_certificate(
                plan=self.plan,
                root_state=(2,),
                leaves=(self.leaves[0], self.leaves[0], self.leaves[2]),
            )

    def test_tight_witnesses_are_checked_algebraically_and_by_row_range(self) -> None:
        with self.assertRaisesRegex(AffineGuardCertificateError, "not tight"):
            replace(
                self.leaves[0],
                lower_tight_witnesses=(TightGuardWitness(100, 0, 1),),
            )
        with self.assertRaisesRegex(AffineGuardCertificateError, "outside"):
            replace(
                self.leaves[0],
                upper_tight_witnesses=(TightGuardWitness(103, 0, 10),),
            )

    def test_strict_json_parsers_reject_unsigned_extra_fields(self) -> None:
        plan_json = self.plan.to_dict()
        plan_json["ignored"] = "dangerous"
        with self.assertRaisesRegex(AffineGuardCertificateError, "extra"):
            FixedShardPlan.from_dict(plan_json)

        leaf_json = self.leaves[0].to_dict()
        leaf_json["ignored"] = "dangerous"
        with self.assertRaisesRegex(AffineGuardCertificateError, "extra"):
            AffineGuardLeaf.from_dict(leaf_json)

    def test_exception_root_is_domain_separated_and_order_sensitive(self) -> None:
        self.assertEqual(EMPTY_EXCEPTION_ROOT_SHA256, exception_merkle_root(()))
        first = exception_merkle_root(({"row": 101, "kind": "fallback"},))
        second = exception_merkle_root(
            ({"row": 101, "kind": "fallback"}, {"row": 102, "kind": "overflow"})
        )
        reversed_root = exception_merkle_root(
            ({"row": 102, "kind": "overflow"}, {"row": 101, "kind": "fallback"})
        )
        self.assertNotEqual(first, second)
        self.assertNotEqual(second, reversed_root)


if __name__ == "__main__":
    unittest.main()
