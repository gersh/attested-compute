#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import unittest

from tg_verifier.goldbach_word_owner_optimizer import primes_through
from tools.qualify_goldbach_word_owner_wheel23 import (
    EXPECTED_CASES,
    EXPECTED_CURRENT_GOLDBACH_SOURCE_SHA256,
    EXPECTED_P2_SHA256,
    EXPECTED_PHASE_REDUCTION,
    EXPECTED_SOURCE_SHA256,
    EXPECTED_TABLE_SHA256,
    KIND,
    QualificationError,
    ROOT,
    SOURCE,
    sha256,
    validate_result,
)


def resources(registers: int) -> dict[str, int]:
    return {
        "local_bytes_per_thread": 0,
        "max_threads_per_block": 1024,
        "registers_per_thread": registers,
        "static_constant_bytes": 0,
        "static_shared_bytes": 0,
    }


def fixture(mode: str = "bounded") -> dict[str, object]:
    rounds = 101 if mode == "source-segment" else 9
    current = [3.0] * rounds
    candidate = [2.0] * rounds
    source_mode = mode == "source-segment"
    return {
        "accepted": True,
        "algorithm_equivalence_scope": (
            "cpu-vs-current-vs-phase-hoisted-wheel23-all-output-words"
        ),
        "all_word_equality": True,
        "benchmark": {
            "candidate_median_ms": 2.0,
            "candidate_ms": candidate,
            "current_median_ms": 3.0,
            "current_ms": current,
            "current_over_candidate_rate_ratio": 1.5,
            "integrated_equivalent_even_count": "20000000000",
            "integrated_equivalent_odd_word_inputs": "20050000000",
            "integrated_equivalent_segment_count": 100,
            "integrated_equivalent_measured": source_mode,
            "integrated_current_initializer_ms": (
                300.0 if source_mode else 0.0
            ),
            "integrated_candidate_initializer_plus_table_ms": (
                201.0 if source_mode else 0.0
            ),
            "rounds": rounds,
        },
        "bounded_cases": [dict(value) for value in EXPECTED_CASES],
        "build_profile": {
            "cmake_build_config": "Release",
            "ndebug_defined": True,
        },
        "candidate_resources": resources(34),
        "candidate_selected_in_production": False,
        "classification": "qualification-only-unpromoted-candidate",
        "compute_capability": "12.1",
        "cuda_to_lean_refinement_proved": False,
        "current_resources": resources(34),
        "h100_measured": False,
        "kind": KIND,
        "lean_bridge_complete": False,
        "mode": mode,
        "performance_evidence_eligible": False,
        "phase_reduction": dict(EXPECTED_PHASE_REDUCTION),
        "prime_square_audit": {
            "prime_count": 308,
            "sha256": EXPECTED_P2_SHA256,
        },
        "production_identity_changed": False,
        "production_ready": False,
        "release_build_profile_eligible": True,
        "receipt_emitted": False,
        "resource_gate_passed": True,
        "source_pins": {
            "current_goldbach_source_sha256": (
                EXPECTED_CURRENT_GOLDBACH_SOURCE_SHA256
            ),
        },
        "strict_h100_target": False,
        "table_initializer_resources": resources(25),
        "terminal_case": (
            {
                "name": "historical-terminal-segment",
                "odd_count": 200_500_000,
                "output_sha256": (
                    "2a643ef55c59f4d3eb4bc8884737a208"
                    "233116178aff81e2ebd007478564dd24"
                ),
                "padding_bits": 32,
                "q_low": "31249999599000003",
                "full_word_q_high": "31250000000000065",
                "set_bits": 29_453_809,
                "word_count": 3_132_813,
            }
            if source_mode
            else None
        ),
        "runtime_instrumentation_status": "not-inspected-by-runner",
        "theorem_claimed": False,
        "wheel_table": {
            "carry_bits": 64,
            "carry_mismatches": 0,
            "device_bytes": 13_943_320,
            "initialization_ms": 1.0,
            "logical_bits": 111_546_499,
            "mismatched_words": 0,
            "odd_modulus": 111_546_435,
            "padding_nonzero_bits": 0,
            "sha256": EXPECTED_TABLE_SHA256,
            "surviving_residues": 36_495_360,
            "word_count": 1_742_915,
        },
        "word_owner_cutoff": 2_039,
    }


class GoldbachWordOwnerWheel23QualificationTests(unittest.TestCase):
    def test_exact_bounded_and_source_contracts(self) -> None:
        for mode in ("bounded", "source-segment"):
            with self.subTest(mode=mode):
                value = fixture(mode)
                self.assertIs(validate_result(value, mode=mode), value)

    def test_mutations_fail_closed(self) -> None:
        mutations: list[tuple[dict[str, object], str]] = []
        for key, changed_value in (
            ("all_word_equality", False),
            ("candidate_selected_in_production", True),
            ("production_identity_changed", True),
            ("production_ready", True),
            ("release_build_profile_eligible", False),
            ("receipt_emitted", True),
            ("theorem_claimed", True),
        ):
            changed = copy.deepcopy(fixture())
            changed[key] = changed_value
            mutations.append((changed, key))
        changed = copy.deepcopy(fixture())
        changed["runtime_instrumentation_status"] = "compute-sanitizer-passed"
        mutations.append((changed, "runtime instrumentation"))
        changed = copy.deepcopy(fixture())
        changed["bounded_cases"][1]["output_sha256"] = "0" * 64
        mutations.append((changed, "case digest"))
        changed = copy.deepcopy(fixture())
        changed["prime_square_audit"]["prime_count"] = 307
        mutations.append((changed, "prime squares"))
        changed = copy.deepcopy(fixture())
        changed["wheel_table"]["carry_mismatches"] = 1
        mutations.append((changed, "carry"))
        changed = copy.deepcopy(fixture())
        changed["wheel_table"]["sha256"] = "0" * 64
        mutations.append((changed, "table digest"))
        changed = copy.deepcopy(fixture())
        changed["phase_reduction"]["maximum_phase_numerator"] += 1
        mutations.append((changed, "phase bound"))
        changed = copy.deepcopy(fixture())
        changed["phase_reduction"]["q_half_mod_hoisted"] = 1
        mutations.append((changed, "phase boolean type"))
        changed = copy.deepcopy(fixture())
        changed["phase_reduction"]["oversized_launch_rejected"] = False
        mutations.append((changed, "oversized launch guard"))
        changed = copy.deepcopy(fixture())
        changed["candidate_resources"]["local_bytes_per_thread"] = 8
        mutations.append((changed, "local memory"))
        changed = copy.deepcopy(fixture())
        changed["benchmark"]["integrated_equivalent_odd_word_inputs"] = (
            "20000000000"
        )
        mutations.append((changed, "integrated geometry"))
        changed = copy.deepcopy(fixture("source-segment"))
        changed["benchmark"][
            "integrated_candidate_initializer_plus_table_ms"
        ] = 200.0
        mutations.append((changed, "table amortization"))
        changed = copy.deepcopy(fixture())
        changed["unexpected"] = True
        mutations.append((changed, "unexpected field"))
        for value, label in mutations:
            with self.subTest(label=label):
                with self.assertRaises(QualificationError):
                    validate_result(
                        value, mode=str(value.get("mode", "bounded"))
                    )

    def test_source_pin_guard_and_exact_prime_roster(self) -> None:
        self.assertEqual(sha256(SOURCE), EXPECTED_SOURCE_SHA256)
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn(
            "SPARKINTERVAL_ENABLE_GOLDBACH_"
            "WORD_OWNER_WHEEL23_QUALIFICATION",
            source,
        )
        self.assertIn("#error", source)
        self.assertIn("kWheelOddModulus == 111'546'435U", source)
        self.assertIn("kWheelCarryBits = 64U", source)
        self.assertIn(
            "kMaximumQualifiedWordCount == 3'132'813ULL", source
        )
        self.assertIn(
            "(q_low >> 1U) % kWheelOddModulus", source
        )
        self.assertIn(
            "q_half_mod + 64U * static_cast<std::uint32_t>(word_index)",
            source,
        )
        self.assertEqual(
            source.count(
                "if (phase >= kWheelOddModulus) "
                "phase -= kWheelOddModulus;"
            ),
            2,
        )
        self.assertIn(
            "word_count > kMaximumQualifiedWordCount", source
        )
        self.assertIn("restore_wheel_prime<3>", source)
        self.assertIn("restore_wheel_prime<23>", source)
        macro_start = source.index(
            "#define SPARKINTERVAL_GOLDBACH_WORD_OWNER_PRIMES_29_TO_2039"
        )
        macro_end = source.index("\n\nvoid cuda_check", macro_start)
        roster = tuple(
            int(value)
            for value in re.findall(
                r"X\(([0-9]+)\)", source[macro_start:macro_end]
            )
        )
        self.assertEqual(roster, primes_through(2_039)[8:])
        self.assertEqual(len(roster), 300)

    def test_default_build_does_not_select_candidate(self) -> None:
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        option = (
            "SPARKINTERVAL_BUILD_TG_GOLDBACH_"
            "WORD_OWNER_WHEEL23_QUALIFICATION"
        )
        declaration = re.search(
            rf"option\(\s*{option}\s*"
            rf'"[^"]*"\s*(ON|OFF)\s*\)',
            cmake,
        )
        self.assertIsNotNone(declaration)
        self.assertEqual(declaration.group(1), "OFF")
        self.assertIn(
            "sparkinterval-tg-goldbach-word-owner-wheel23-qualification",
            cmake,
        )
        self.assertIn(
            "sparkinterval-h100-tg-goldbach-word-owner-wheel23-qualification",
            cmake,
        )
        production_modules = (
            ROOT / "tg_verifier/goldbach_optimized_source.py",
            ROOT / "tg_verifier/goldbach_gpu_campaign.py",
        )
        for path in production_modules:
            self.assertNotIn(option, path.read_text(encoding="utf-8"))

    def test_optional_bounded_runtime(self) -> None:
        executable = os.environ.get(
            "TG_GOLDBACH_WORD_OWNER_WHEEL23_QUALIFICATION"
        )
        if executable is None:
            self.skipTest("qualification executable was not provided")
        completed = subprocess.run(
            [executable],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        validate_result(json.loads(completed.stdout), mode="bounded")


if __name__ == "__main__":
    unittest.main()
