#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import unittest

from tools.run_goldbach_warp_tail_kat import KATError, KIND, validate_result


def fixture() -> dict[str, object]:
    width = 2 * ((1 << 18) - 1)
    starts = [
        4_000_001,
        4_156_001,
        31_249_998_799_000_003,
        (1 << 64) - 1 - width,
    ]
    return {
        "accepted": True,
        "compute_capability": "12.1",
        "kind": KIND,
        "odd_count_per_window": 1 << 18,
        "prime_limit": 131_071,
        "tail_prime_count": 12_000,
        "warp_parallel_cutoff": 32_749,
        "warp_prime_count": 3_000,
        "window_count": 4,
        "windows": [
            {
                "fnv1a64": f"{index + 1:016x}",
                "q_high": str(start + width),
                "q_low": str(start),
                "set_bits": 100_000 + index,
            }
            for index, start in enumerate(starts)
        ],
        "word_owner_cutoff": 2_039,
    }


class GoldbachWarpTailKATTests(unittest.TestCase):
    def test_exact_result_contract(self) -> None:
        value = fixture()
        self.assertIs(validate_result(value), value)

    def test_mutations_fail_closed(self) -> None:
        mutations = []
        changed = copy.deepcopy(fixture())
        changed["accepted"] = False
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["warp_parallel_cutoff"] = 32_751
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["windows"][0]["q_high"] = str(
            int(changed["windows"][0]["q_high"]) - 2
        )
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["windows"][-1]["q_high"] = str((1 << 64) - 3)
        mutations.append(changed)
        changed = copy.deepcopy(fixture())
        changed["unexpected"] = True
        mutations.append(changed)
        for value in mutations:
            with self.subTest(value=value):
                with self.assertRaises(KATError):
                    validate_result(value)


if __name__ == "__main__":
    unittest.main()
