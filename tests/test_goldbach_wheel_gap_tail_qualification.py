#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import unittest

from tools.qualify_goldbach_wheel_gap_tail import (
    EXPECTED_BENCHMARKS,
    EXPECTED_CASES,
    EXPECTED_WHEEL_TABLE_SHA256,
    KIND,
    QualificationError,
    ROOT,
    SOURCE,
    make_wheel_table,
    validate_result,
)


def counts(values: tuple[int, int, int]) -> dict[str, int]:
    raw, small, final = values
    return {
        "final_event_count": final,
        "raw_visit_count": raw,
        "small_wheel_survivor_count": small,
    }


def fixture() -> dict[str, object]:
    cases = []
    for name, expected in EXPECTED_CASES.items():
        cases.append(
            {
                "counts": counts(expected["counts"]),
                "name": name,
                "odd_count": expected["odd_count"],
                "output_sha256": expected["output_sha256"],
                "q_high": expected["q_high"],
                "q_low": expected["q_low"],
                "set_bits": expected["set_bits"],
            }
        )
    benchmark = EXPECTED_BENCHMARKS["bounded"]
    timings = {
        "current_wheel47_median_ms": 2.0,
        "current_wheel47_ms": [2.0] * 7,
        "ordinary_raw_median_ms": 3.0,
        "ordinary_raw_ms": [3.0] * 7,
        "wheel_gap_median_ms": 2.0,
        "wheel_gap_ms": [2.0] * 7,
        "wheel_gap_remainders_median_ms": 2.0,
        "wheel_gap_remainders_ms": [2.0] * 7,
    }
    resource = {
        "local_bytes_per_thread": 0,
        "max_threads_per_block": 1024,
        "registers_per_thread": 32,
        "static_constant_bytes": 0,
        "static_shared_bytes": 0,
    }
    return {
        "accepted": True,
        "benchmark": {
            "counts": counts(benchmark["counts"]),
            "current_over_gap_rate_ratio": 1.0,
            "current_over_gap_remainders_rate_ratio": 1.0,
            "geometry": "bounded",
            "output_sha256": benchmark["output_sha256"],
            "prime_limit": benchmark["prime_limit"],
            "rounds": benchmark["rounds"],
            "tail_prime_count": benchmark["tail_prime_count"],
            "timings": timings,
            "total_odd_count": benchmark["total_odd_count"],
            "window_count": benchmark["window_count"],
        },
        "bounded_case_count": 5,
        "bounded_cases": cases,
        "compute_capability": "12.1",
        "current_wheel47_resources": copy.deepcopy(resource),
        "kind": KIND,
        "lean_bridge_complete": False,
        "ordinary_raw_resources": copy.deepcopy(resource),
        "performance_evidence_eligible": False,
        "production_identity_promoted": False,
        "production_ready": False,
        "release_build_profile_eligible": True,
        "resource_gate_passed": True,
        "runtime_instrumentation_status": "not-inspected-by-runner",
        "wheel_gap_remainder_resources": copy.deepcopy(resource),
        "wheel_gap_resources": copy.deepcopy(resource),
        "wheel_table": {
            "encoded_entry_count": 15_015,
            "maximum_even_gap": 22,
            "modulus": 30_030,
            "sha256": EXPECTED_WHEEL_TABLE_SHA256,
            "surviving_residue_count": 5_760,
        },
        "word_owner_cutoff": 2_039,
        "warp_parallel_cutoff": 32_749,
    }


class GoldbachWheelGapTailQualificationTests(unittest.TestCase):
    def test_exact_result_contract(self) -> None:
        value = fixture()
        self.assertIs(validate_result(value, mode="bounded"), value)

    def test_independent_table_generation(self) -> None:
        table = make_wheel_table()
        self.assertEqual(len(table), 15_015)
        self.assertEqual(
            hashlib.sha256(table).hexdigest(),
            EXPECTED_WHEEL_TABLE_SHA256,
        )
        self.assertEqual(sum(bool(value & 0x80) for value in table), 5_760)
        self.assertEqual(max(value & 0x1F for value in table), 22)
        for index, value in enumerate(table):
            residue = 2 * index + 1
            gap = value & 0x1F
            self.assertEqual(
                bool(value & 0x80),
                all(residue % prime for prime in (3, 5, 7, 11, 13)),
            )
            self.assertTrue(
                all(
                    (residue + gap) % prime
                    for prime in (3, 5, 7, 11, 13)
                )
            )
            for prior in range(2, gap, 2):
                self.assertFalse(
                    all(
                        (residue + prior) % prime
                        for prime in (3, 5, 7, 11, 13)
                    )
                )

    def test_mutations_fail_closed(self) -> None:
        mutations: list[dict[str, object]] = []
        changed = copy.deepcopy(fixture())
        changed["production_ready"] = True
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["wheel_table"]["maximum_even_gap"] = 20
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["bounded_cases"][1]["counts"]["raw_visit_count"] = 1
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["bounded_cases"][4]["q_high"] = str((1 << 64) - 2)
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["benchmark"]["counts"]["final_event_count"] -= 1
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["benchmark"]["current_over_gap_rate_ratio"] = 2.0
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["wheel_gap_remainder_resources"][
            "local_bytes_per_thread"
        ] = 8
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["unexpected"] = True
        mutations.append(changed)
        for value in mutations:
            with self.subTest(value=value):
                with self.assertRaises(QualificationError):
                    validate_result(value, mode="bounded")

    def test_source_is_macro_only_and_not_in_production_paths(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn(
            "#ifndef "
            "SPARKINTERVAL_ENABLE_GOLDBACH_WHEEL_GAP_QUALIFICATION",
            source,
        )
        self.assertIn("kWheelModulus = 30'030", source)
        self.assertIn("kExpectedMaximumGap = 22", source)
        self.assertIn("advance_wheel_index", source)
        for path in (
            ROOT / "CMakeLists.txt",
            ROOT / "tg_verifier/goldbach_optimized_source.py",
        ):
            self.assertNotIn(
                "GOLDBACH_WHEEL_GAP_QUALIFICATION",
                path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
