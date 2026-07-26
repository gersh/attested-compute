# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed checks for compact CH25 psi affine receipts."""

from __future__ import annotations

from copy import deepcopy
import unittest

from tools import benchmark_tg_psi_affine_guard as benchmark
from tg_verifier import psi_affine_guard_qualification as qualification


def fixture() -> dict[str, object]:
    return {
        "algorithm": "ch25-psi-prime-power-affine-guard-v1",
        "mode": "affine",
        "classification": "source-scale-shard-not-lean-proof",
        "atom": "ch25-psi-1e13",
        "lower": 2,
        "upper_exclusive": 101,
        "accepted": True,
        "execution_attested": False,
        "lean_atom_discharged": False,
        "prime_power_events": 35,
        "prime_events": 25,
        "higher_power_events": 10,
        "event_sha256": (
            "6a39e9a90d7c9bead2b83dd3b4acb890a81fc9ab4faa3728c0a065da4e9720c0"
        ),
        "row_sha256": (
            "ca6eca43ef27a1eaf09e53e91ed6e19e34f8348eb808eec28464b03f69979288"
        ),
        "delta": [
            1_734_829_787_580_318_666_752,
            1_734_829_787_580_318_957_568,
        ],
        "guard_encoding": (
            "independent-q64-rectangle-with-lower-le-upper-v1"
        ),
        "allowed_incoming_q64": {
            "lower_min": 0,
            "upper_max": 44_731_675_089_009_430_431,
            "predicate": "lower_min<=lower<=upper<=upper_max",
        },
        "guard_witnesses": {
            "lower_min": {
                "event_index": 0,
                "value": 2,
                "prefix_delta_q64": 0,
                "radius_q64": 36_893_488_147_419_103_232,
                "strict": False,
                "kind": "lower_left_limit",
            },
            "upper_max": {
                "event_index": 0,
                "value": 2,
                "prefix_delta_q64": 12_786_308_645_202_657_280,
                "radius_q64": 20_624_495_586_792_984_479,
                "kind": "upper_post_jump",
            },
        },
        "terminal_strict_lower_constrained": False,
    }


def semantic_fixture() -> dict[str, object]:
    report = fixture()
    return {
        "lower": 2,
        "upper_exclusive": 101,
        "prime_power_events": report["prime_power_events"],
        "prime_events": report["prime_events"],
        "higher_power_events": report["higher_power_events"],
        "unique_primes": report["prime_events"],
        "event_sha256": report["event_sha256"],
        "row_sha256": report["row_sha256"],
        "delta": report["delta"],
        "allowed_incoming_q64": report["allowed_incoming_q64"],
        "guard_witnesses": report["guard_witnesses"],
        "terminal_strict_lower_constrained": False,
    }


class PsiAffineGuardReceiptTests(unittest.TestCase):
    def assert_rejected(self, changed: dict[str, object], pattern: str) -> None:
        with self.assertRaisesRegex(benchmark.BenchmarkError, pattern):
            benchmark.check_affine_witnesses(changed)

    def test_literal_fixture_is_accepted(self) -> None:
        benchmark.check_affine_witnesses(fixture())

    def test_lower_radius_mutation_is_rejected(self) -> None:
        changed = deepcopy(fixture())
        changed["guard_witnesses"]["lower_min"]["radius_q64"] += 1
        self.assert_rejected(changed, "lower affine Q16 radius")

    def test_upper_radius_mutation_is_rejected(self) -> None:
        changed = deepcopy(fixture())
        changed["guard_witnesses"]["upper_max"]["radius_q64"] -= 1
        self.assert_rejected(changed, "upper affine Q16 radius")

    def test_extremum_mutation_is_rejected(self) -> None:
        changed = deepcopy(fixture())
        changed["allowed_incoming_q64"]["upper_max"] += 1
        self.assert_rejected(changed, "upper witness does not attain")

    def test_missing_witness_is_rejected(self) -> None:
        changed = deepcopy(fixture())
        del changed["guard_witnesses"]["upper_max"]
        self.assert_rejected(changed, "extremum witnesses")

    def test_out_of_range_witness_index_is_rejected(self) -> None:
        changed = deepcopy(fixture())
        changed["guard_witnesses"]["lower_min"]["event_index"] = 35
        self.assert_rejected(changed, "ordinary lower witness")

    def test_overflowing_admitted_state_is_rejected(self) -> None:
        changed = deepcopy(fixture())
        changed["allowed_incoming_q64"]["upper_max"] = (1 << 128) - 1
        self.assert_rejected(changed, "upper witness does not attain|overflow")

    def test_claimed_attestation_is_rejected(self) -> None:
        changed = deepcopy(fixture())
        changed["execution_attested"] = True
        self.assert_rejected(changed, "identity or trust flags")

    def test_structural_oracle_fixture_is_accepted(self) -> None:
        qualification._validate_semantics(semantic_fixture(), 2, 101)

    def test_unreported_tighter_bound_mutation_requires_fresh_fold(self) -> None:
        changed = deepcopy(semantic_fixture())
        changed["allowed_incoming_q64"]["lower_min"] += 1
        with self.assertRaisesRegex(
            qualification.PsiAffineQualificationError,
            "does not attain minimum",
        ):
            qualification._validate_semantics(changed, 2, 101)

    def test_oracle_extra_field_is_rejected(self) -> None:
        changed = deepcopy(semantic_fixture())
        changed["unreviewed"] = True
        with self.assertRaisesRegex(
            qualification.PsiAffineQualificationError,
            "semantic fields changed",
        ):
            qualification._validate_semantics(changed, 2, 101)


if __name__ == "__main__":
    unittest.main()
