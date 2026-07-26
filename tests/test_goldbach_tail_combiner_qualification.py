#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import unittest

from tools.qualify_goldbach_tail_combiner import (
    EXPECTED_CASES,
    KIND,
    QualificationError,
    ROOT,
    SOURCE,
    validate_result,
)


def counters(events: int, flushes: int | None = None) -> dict[str, int]:
    return {
        "collision_probe_count": 1,
        "combined_event_count": events,
        "eligible_event_count": events,
        "fallback_event_count": 0,
        "flushed_entry_count": events if flushes is None else flushes,
    }


def fixture() -> dict[str, object]:
    cases = []
    for name, expected in EXPECTED_CASES.items():
        event_count = int(expected["cpu_event_count"])
        row_counters = counters(event_count, max(1, event_count - 1))
        if name == "forced-full-table-fallback":
            row_counters = {
                "collision_probe_count": 10,
                "combined_event_count": 1_000,
                "eligible_event_count": event_count,
                "fallback_event_count": event_count - 1_000,
                "flushed_entry_count": 900,
            }
        cases.append(
            {
                "counters": row_counters,
                "cpu_event_count": event_count,
                "force_hash_collision": name
                in {"forced-collision", "forced-full-table-fallback"},
                "name": name,
                "odd_count": 1 << 18,
                "output_sha256": expected["output_sha256"],
                "patterned_initial_words": expected[
                    "patterned_initial_words"
                ],
                "q_high": expected["q_high"],
                "q_low": expected["q_low"],
                "set_bits": expected["set_bits"],
                "table_slots": expected["table_slots"],
            }
        )
    benchmark_events = 387_620
    benchmark_flushes = 382_557
    return {
        "accepted": True,
        "benchmark": {
            "candidate_ms": [2.0] * 7,
            "candidate_median_ms": 2.0,
            "cpu_event_count": benchmark_events,
            "eliminated_global_atomic_count": (
                benchmark_events - benchmark_flushes
            ),
            "emitted_global_atomic_count": benchmark_flushes,
            "geometry": "bounded-source-height-tail-subset",
            "observed_ordinary_over_candidate_rate_ratio": 0.5,
            "odd_count": 4_194_304,
            "ordinary_ms": [1.0] * 7,
            "ordinary_median_ms": 1.0,
            "output_sha256": (
                "83d5a979e1591662006976e86368d62de674b874c32ec00b9db"
                "0ddbd3ae86f61"
            ),
            "prime_limit": 2_000_003,
            "q_high": "31249998807388609",
            "q_low": "31249998799000003",
            "rounds": 7,
            "routing_counters": counters(
                benchmark_events, benchmark_flushes
            ),
            "tail_prime_count": 145_422,
        },
        "bounded_case_count": 5,
        "bounded_cases": cases,
        "bounded_prime_limit": 262_147,
        "bounded_tail_prime_count": 19_489,
        "candidate_resources": {
            "local_bytes_per_thread": 0,
            "max_threads_per_block": 1024,
            "registers_per_thread": 40,
            "static_shared_bytes": 8192,
        },
        "compute_capability": "12.1",
        "events_per_epoch": 2,
        "kind": KIND,
        "lean_bridge_complete": False,
        "maximum_table_slots": 512,
        "ordinary_resources": {
            "local_bytes_per_thread": 0,
            "max_threads_per_block": 1024,
            "registers_per_thread": 38,
            "static_shared_bytes": 0,
        },
        "performance_evidence_eligible": False,
        "production_identity_promoted": False,
        "production_ready": False,
        "release_build_profile_eligible": True,
        "resource_gate_passed": True,
        "runtime_instrumentation_status": "not-inspected-by-runner",
        "source_segment_mode": False,
        "threads_per_block": 256,
        "word_owner_cutoff": 2_039,
        "warp_parallel_cutoff": 32_749,
    }


class GoldbachTailCombinerQualificationTests(unittest.TestCase):
    def test_exact_result_contract(self) -> None:
        value = fixture()
        self.assertIs(validate_result(value, source_segment=False), value)

    def test_mutations_fail_closed(self) -> None:
        mutations: list[dict[str, object]] = []
        changed = copy.deepcopy(fixture())
        changed["production_ready"] = True
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["candidate_resources"]["local_bytes_per_thread"] = 8
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["bounded_cases"][1]["output_sha256"] = "0" * 64
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["bounded_cases"][2]["counters"]["collision_probe_count"] = 0
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["bounded_cases"][3]["counters"]["fallback_event_count"] = 0
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["benchmark"]["routing_counters"][
            "eligible_event_count"
        ] += 1
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["benchmark"][
            "observed_ordinary_over_candidate_rate_ratio"
        ] = 2.0
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["unexpected"] = True
        mutations.append(changed)
        for value in mutations:
            with self.subTest(value=value):
                with self.assertRaises(QualificationError):
                    validate_result(value, source_segment=False)

    def test_source_is_explicitly_macro_guarded_and_exact_keyed(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn(
            "#ifndef "
            "SPARKINTERVAL_ENABLE_GOLDBACH_TAIL_COMBINER_QUALIFICATION",
            source,
        )
        self.assertIn(
            "atomicCAS(keys + slot, kEmptyKey, word)", source
        )
        self.assertIn("atomicAnd(masks + slot, clear_mask)", source)
        self.assertIn("if (!combined)", source)
        self.assertIn("atomicAnd(words + word, clear_mask)", source)
        self.assertIn("atomicAnd(words + key, masks[slot])", source)
        self.assertNotIn(
            "SPARKINTERVAL_ENABLE_GOLDBACH_TAIL_COMBINER_QUALIFICATION",
            (ROOT / "CMakeLists.txt").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
