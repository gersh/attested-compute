# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

import unittest

from tg_verifier.goldbach_prime_prefix_reuse_benchmark import (
    DEFAULT_EVEN_LIMIT,
    DEFAULT_EVEN_START,
    EXACT_CPU_PRIME_PREFIX_COUNT,
    GoldbachPrimePrefixBenchmarkError,
    parse_bounded_stdout,
)


def _stdout(role: str) -> bytes:
    if role == "v1":
        table = "Pre-generating CPU primes up to 100000000...\n"
    else:
        table = "Reusing CPU-prime prefix through 100000000...\n"
    if role == "crosscheck":
        table += (
            "CPU-prime prefix exact-vector crosscheck: "
            f"{EXACT_CPU_PRIME_PREFIX_COUNT} entries matched.\n"
        )
    return (
        "[Hardware] GPU 0: NVIDIA GB10 (122566 MB VRAM)\n"
        "Building small primes bitset up to 176776697...\n"
        f"{table}"
        "Initialization completed in 171.588 ms.\n\n"
        "--- Launching Multi-GPU Verifier ---\n"
        f"Checking range : [{DEFAULT_EVEN_START}, {DEFAULT_EVEN_LIMIT}]\n"
        "Total numbers  : 600000000\n\n\n"
        "--- Verification Complete ---\n"
        f"All even numbers from {DEFAULT_EVEN_START} up to "
        f"{DEFAULT_EVEN_LIMIT} satisfy Goldbach. ✓\n"
        "Total computation time : 0.261106 seconds\n"
        "Phase 2 fallbacks      : 0\n"
    ).encode()


class GoldbachPrimePrefixReuseBenchmarkTests(unittest.TestCase):
    def test_three_transcript_roles_parse(self) -> None:
        for role in ("v1", "v2", "crosscheck"):
            with self.subTest(role=role):
                parsed = parse_bounded_stdout(
                    _stdout(role),
                    role=role,
                    even_start=DEFAULT_EVEN_START,
                    even_limit=DEFAULT_EVEN_LIMIT,
                )
                self.assertEqual(parsed["phase2_fallbacks"], 0)
                if role == "crosscheck":
                    self.assertEqual(
                        parsed["exact_vector_crosscheck_entries"],
                        EXACT_CPU_PRIME_PREFIX_COUNT,
                    )

    def test_rejects_role_substitution_and_nonexact_vector_count(self) -> None:
        with self.assertRaises(GoldbachPrimePrefixBenchmarkError):
            parse_bounded_stdout(
                _stdout("v2"),
                role="v1",
                even_start=DEFAULT_EVEN_START,
                even_limit=DEFAULT_EVEN_LIMIT,
            )
        malformed = _stdout("crosscheck").replace(
            str(EXACT_CPU_PRIME_PREFIX_COUNT).encode(),
            str(EXACT_CPU_PRIME_PREFIX_COUNT - 1).encode(),
        )
        with self.assertRaises(GoldbachPrimePrefixBenchmarkError):
            parse_bounded_stdout(
                malformed,
                role="crosscheck",
                even_start=DEFAULT_EVEN_START,
                even_limit=DEFAULT_EVEN_LIMIT,
            )


if __name__ == "__main__":
    unittest.main()
