#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Compile and independently audit the bounded CDEM Abel reference producer."""

from __future__ import annotations

import math
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reference" / "tg_cdem_abel.cpp"
COEFFICIENT_SCALE = 10**30
WEIGHT_SCALE = 10**18


def naive_mobius(number: int) -> int:
    """Compute one small Mobius value by trial factorization."""

    remaining = number
    factors = 0
    prime = 2
    while prime * prime <= remaining:
        if remaining % prime == 0:
            remaining //= prime
            factors += 1
            if remaining % prime == 0:
                return 0
        prime += 1
    if remaining > 1:
        factors += 1
    return -1 if factors % 2 else 1


def ceil_div(numerator: int, denominator: int) -> int:
    return (numerator + denominator - 1) // denominator


def ceil_scaled_reciprocal_sqrt(number: int) -> int:
    """Least q satisfying q**2 * number >= WEIGHT_SCALE**2."""

    required_square = ceil_div(WEIGHT_SCALE * WEIGHT_SCALE, number)
    result = math.isqrt(required_square)
    return result if result * result == required_square else result + 1


def independent_fields(K: int, N: int, block_size: int) -> dict[str, int]:
    """Recompute output fields without using the C++ sieve/block algorithm."""

    mu = [0] + [naive_mobius(number) for number in range(1, K + 1)]
    reciprocal_lower = 0
    reciprocal_upper = 0
    for denominator in range(1, K + 1):
        coefficient = mu[denominator]
        floor_term = COEFFICIENT_SCALE // denominator
        ceil_term = ceil_div(COEFFICIENT_SCALE, denominator)
        if coefficient > 0:
            reciprocal_lower += floor_term
            reciprocal_upper += ceil_term
        elif coefficient < 0:
            reciprocal_lower -= ceil_term
            reciprocal_upper -= floor_term

    floor_sum = 0
    previous_error = 0  # CDEM's explicit Gseq(0) override.
    u_upper = 0
    v_upper = 0
    total_variation = 0
    for number in range(1, N + 1):
        delta = sum(
            mu[divisor]
            for divisor in range(1, K + 1)
            if number % divisor == 0
        )
        floor_sum += delta
        error = abs(1 - floor_sum)
        increment = error - previous_error
        if increment > 0:
            u_upper += increment * ceil_div(WEIGHT_SCALE, number)
        elif increment < 0:
            u_upper += increment * (WEIGHT_SCALE // number)
        total_variation += abs(increment)
        v_upper += abs(increment) * ceil_scaled_reciprocal_sqrt(number)
        previous_error = error

    return {
        "K": K,
        "N": N,
        "A": N + 1,
        "MOBIUS_M": sum(mu),
        "MOBIUS_Q": sum(abs(value) for value in mu),
        "COEFF_SCALE": COEFFICIENT_SCALE,
        "S_LOWER_NUM": reciprocal_lower,
        "S_UPPER_NUM": reciprocal_upper,
        "FINAL_F": floor_sum,
        "FINAL_G": abs(1 - floor_sum),
        "TOTAL_VARIATION": total_variation,
        "WEIGHT_SCALE": WEIGHT_SCALE,
        "U_INC_UPPER_NUM": u_upper,
        "V_INC_UPPER_NUM": v_upper,
        "ENDPOINT_RSQRT_UPPER_NUM": ceil_scaled_reciprocal_sqrt(N + 1),
        "BLOCK_SIZE": block_size,
    }


class CdemAbelSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compiler = shutil.which("g++")
        if compiler is None:
            raise unittest.SkipTest("g++ is required for the CDEM source test")
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.executable = Path(cls.temporary_directory.name) / "tg_cdem_abel"
        compiled = subprocess.run(
            [
                compiler,
                "-O2",
                "-std=c++20",
                "-fopenmp",
                "-I",
                str(ROOT / "gpu" / "include"),
                str(SOURCE),
                "-o",
                str(cls.executable),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if compiled.returncode != 0:
            raise AssertionError(
                "failed to compile tg_cdem_abel.cpp:\n"
                + compiled.stdout
                + compiled.stderr
            )

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "temporary_directory"):
            cls.temporary_directory.cleanup()

    def run_producer(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["OMP_NUM_THREADS"] = "2"
        return subprocess.run(
            [str(self.executable), *arguments],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    @staticmethod
    def parse_output(stdout: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        for line in stdout.splitlines():
            key, separator, value = line.partition("=")
            if not separator:
                raise AssertionError(f"malformed output line: {line!r}")
            if key in fields:
                raise AssertionError(f"duplicate output field: {key}")
            fields[key] = value
        return fields

    def test_small_run_matches_independent_integer_recurrence(self) -> None:
        K, N, block_size = 10, 40, 7
        completed = self.run_producer(str(K), str(N), str(block_size))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        actual = self.parse_output(completed.stdout)
        expected = independent_fields(K, N, block_size)
        for field, value in expected.items():
            with self.subTest(field=field):
                self.assertIn(field, actual)
                self.assertEqual(int(actual[field]), value)
        chunk_count = int(actual["CHUNK_COUNT"])
        self.assertEqual(chunk_count, math.ceil(N / block_size))
        manifest = "".join(
            f"CHUNK_{index}={actual[f'CHUNK_{index}']}\n"
            for index in range(chunk_count)
        ).encode("ascii")
        self.assertEqual(
            hashlib.sha256(manifest).hexdigest(),
            actual["CHUNK_MANIFEST_SHA256"],
        )
        records = [
            tuple(map(int, actual[f"CHUNK_{index}"].split(",")))
            for index in range(chunk_count)
        ]
        self.assertEqual(records[0][2], 0)
        self.assertTrue(
            all(left[3] == right[2] for left, right in zip(records, records[1:]))
        )
        self.assertEqual(records[-1][3], expected["FINAL_F"])
        self.assertEqual(sum(record[4] for record in records), expected["U_INC_UPPER_NUM"])
        self.assertEqual(sum(record[5] for record in records), expected["V_INC_UPPER_NUM"])
        self.assertEqual(sum(record[6] for record in records), expected["TOTAL_VARIATION"])

    def test_exact_fields_are_invariant_under_block_partition(self) -> None:
        deterministic_fields = set(independent_fields(12, 53, 1)) - {"BLOCK_SIZE"}
        outputs = []
        for block_size in (1, 8, 100):
            completed = self.run_producer("12", "53", str(block_size))
            self.assertEqual(completed.returncode, 0, completed.stderr)
            parsed = self.parse_output(completed.stdout)
            outputs.append(
                {field: parsed[field] for field in deterministic_fields}
            )
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], outputs[2])

    def test_invalid_arguments_are_rejected_before_computation(self) -> None:
        invalid_argument_lists = (
            ("0", "20", "4"),
            ("10", "9", "4"),
            ("10", "20", "0"),
            ("not-a-number", "20", "4"),
            (str(1 << 31), "20", "4"),
            ("1", str((1 << 64) - 1), "1"),
            ("10", "20", "4", "unexpected"),
        )
        for arguments in invalid_argument_lists:
            with self.subTest(arguments=arguments):
                completed = self.run_producer(*arguments)
                self.assertEqual(completed.returncode, 2)
                self.assertNotEqual(completed.stderr, "")
                self.assertEqual(completed.stdout, "")

    def test_source_preserves_provenance_and_external_scope(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertTrue(
            source.startswith(
                "// Copyright (c) 2026 Gershon Bialer. All rights reserved.\n"
                "// SPDX-License-Identifier: MIT"
            )
        )
        self.assertIn("directed fixed-point upper bounds", source)
        self.assertIn("does not turn that evidence into a Lean-kernel-checked", source)
        self.assertIn("DEFAULT_K = 199330", source)
        self.assertIn("DEFAULT_N = 5000000000ULL", source)


if __name__ == "__main__":
    unittest.main()
