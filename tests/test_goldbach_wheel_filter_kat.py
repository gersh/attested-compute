# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

import unittest

from tools.run_goldbach_wheel_filter_kat import KATError, validate_result


def result() -> dict[str, object]:
    maximum = (1 << 64) - 1
    width = 2 * ((1 << 18) - 1)
    starts = [4_000_001, 4_156_001, 31_249_998_799_000_003, maximum - width]
    return {
        "accepted": True,
        "cofactor_filter_limit": 47,
        "compute_capability": "12.1",
        "kind": "sparkinterval.goldbach-wheel-filter-kat.v1",
        "odd_count_per_window": 1 << 18,
        "prime_limit": 131_071,
        "tail_prime_count": 11_942,
        "warp_parallel_cutoff": 32_749,
        "warp_prime_count": 3_203,
        "wheel_modulus": 15_015,
        "window_count": 4,
        "windows": [
            {
                "fnv1a64": f"{index + 1:016x}",
                "q_high": str(start + width),
                "q_low": str(start),
                "set_bits": 100 + index,
            }
            for index, start in enumerate(starts)
        ],
        "word_owner_cutoff": 2_039,
    }


class GoldbachWheelFilterKATTests(unittest.TestCase):
    def test_accepts_exact_contract(self) -> None:
        self.assertEqual(validate_result(result()), result())

    def test_rejects_changed_wheel(self) -> None:
        changed = result()
        changed["wheel_modulus"] = 105
        with self.assertRaises(KATError):
            validate_result(changed)

    def test_rejects_nonterminal_last_window(self) -> None:
        changed = result()
        changed["windows"][-1]["q_high"] = str((1 << 64) - 3)
        with self.assertRaises(KATError):
            validate_result(changed)


if __name__ == "__main__":
    unittest.main()
