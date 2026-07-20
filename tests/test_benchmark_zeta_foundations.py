#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import benchmark_zeta_foundations as benchmark


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "benchmark_zeta_foundations.py"


class BinaryPowerScheduleTests(unittest.TestCase):
    def test_known_step_counts_match_lean_schedule_examples(self) -> None:
        expected = {
            0: 0,
            1: 1,
            2: 2,
            3: 3,
            4: 3,
            8: 4,
            16: 5,
            32: 6,
            63: 11,
            64: 7,
        }
        self.assertEqual(
            {value: benchmark.binary_power_step_count(value) for value in expected},
            expected,
        )

    def test_generated_schedules_reconstruct_every_exponent(self) -> None:
        result = benchmark.validate_binary_power_schedules(1_024)
        self.assertTrue(result["validated"])
        self.assertEqual(result["exponents_validated"], 1_025)
        self.assertEqual(result["max_exponent"], 1_024)
        self.assertEqual(
            result["schedule_steps_validated"],
            sum(benchmark.binary_power_step_count(n) for n in range(1_025)),
        )
        self.assertEqual(result["deterministic_checksum_u64"], "0a7a6f632af94c00")

    def test_negative_exponents_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            list(benchmark.binary_power_schedule(-1))
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            benchmark.binary_power_step_count(-1)
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            benchmark.validate_binary_power_schedules(-1)


class SyntheticStreamingBracketTests(unittest.TestCase):
    def test_records_match_local_and_adjacent_lean_checks(self) -> None:
        first = [benchmark.synthetic_bracket(i) for i in range(100)]
        second = [benchmark.synthetic_bracket(i) for i in range(100)]
        self.assertEqual(first, second)
        self.assertTrue(
            all(map(benchmark.rational_bracket_is_locally_valid, first))
        )
        self.assertTrue(
            all(
                benchmark.rational_brackets_are_adjacent_ordered(left, right)
                for left, right in zip(first, first[1:])
            )
        )

        invalid_denominator = list(first[0])
        invalid_denominator[11] = 0
        self.assertFalse(
            benchmark.rational_bracket_is_locally_valid(
                tuple(invalid_denominator)
            )
        )
        missing_strict_sign = list(first[0])
        missing_strict_sign[6] = 0
        self.assertFalse(
            benchmark.rational_bracket_is_locally_valid(tuple(missing_strict_sign))
        )
        self.assertFalse(
            benchmark.rational_brackets_are_adjacent_ordered(first[1], first[0])
        )

    def test_streaming_counts_exact_bytes_and_is_chunk_invariant(self) -> None:
        total = 257
        small_chunks = benchmark.validate_streaming_rational_brackets(total, 7)
        large_chunks = benchmark.validate_streaming_rational_brackets(total, 128)
        expected_bytes = (
            benchmark.SYNTHETIC_HEADER.size
            + total * benchmark.SYNTHETIC_BRACKET.size
        )
        self.assertEqual(small_chunks["synthetic_certificate_bytes"], expected_bytes)
        self.assertEqual(large_chunks["synthetic_certificate_bytes"], expected_bytes)
        self.assertEqual(
            small_chunks["deterministic_checksum_u64"],
            large_chunks["deterministic_checksum_u64"],
        )
        self.assertEqual(
            small_chunks["deterministic_checksum_u64"], "c0cf4147f209b493"
        )
        self.assertEqual(small_chunks["largest_chunk_brackets"], 7)
        self.assertEqual(large_chunks["largest_chunk_brackets"], 128)
        self.assertFalse(small_chunks["complete_certificate_materialized"])

    def test_zero_records_and_invalid_configuration(self) -> None:
        empty = benchmark.validate_streaming_rational_brackets(0, 8)
        self.assertEqual(empty["brackets_validated"], 0)
        self.assertEqual(empty["chunks_processed"], 0)
        self.assertEqual(
            empty["synthetic_certificate_bytes"], benchmark.SYNTHETIC_HEADER.size
        )
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            benchmark.validate_streaming_rational_brackets(-1, 8)
        with self.assertRaisesRegex(ValueError, "positive"):
            benchmark.validate_streaming_rational_brackets(1, 0)


class BenchmarkReportTests(unittest.TestCase):
    def test_report_is_json_serializable_and_explicitly_scoped(self) -> None:
        report = benchmark.run_benchmark(
            max_exponent=64, total_brackets=257, chunk_size=32
        )
        json.dumps(report)
        self.assertEqual(report["classification"], "host_side_foundation_microbenchmark")
        exclusions = " ".join(report["scope"]["not_measured"])
        self.assertIn("Riemann-zeta analytic", exclusions)
        self.assertIn("Lean elaboration", exclusions)
        self.assertIn("GPU execution", exclusions)

        for result in report["results"].values():
            self.assertTrue(result["validated"])
            self.assertGreaterEqual(result["elapsed_seconds"], 0.0)
            self.assertGreaterEqual(result["peak_memory_bytes"], 0)
            self.assertIn("throughput", result)
        brackets = report["results"]["synthetic_streaming_rational_brackets"]
        self.assertEqual(brackets["brackets_validated"], 257)
        self.assertGreater(brackets["synthetic_certificate_bytes"], 0)

    def test_cli_prints_clean_json_and_honors_configuration(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--max-exponent",
                "64",
                "--total-brackets",
                "257",
                "--chunk-size",
                "17",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(
            report["configuration"],
            {"chunk_size": 17, "max_exponent": 64, "total_brackets": 257},
        )
        self.assertEqual(completed.stderr, "")

    def test_cli_can_write_pretty_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--max-exponent",
                    "8",
                    "--total-brackets",
                    "9",
                    "--chunk-size",
                    "4",
                    "--pretty",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "")
            self.assertIn("\n  \"benchmark\"", output.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(output.read_text())["schema_version"], 1)

    def test_defaults_are_bounded_development_sizes(self) -> None:
        self.assertLessEqual(benchmark.DEFAULT_MAX_EXPONENT, 100_000)
        self.assertLessEqual(benchmark.DEFAULT_TOTAL_BRACKETS, 250_000)
        self.assertLessEqual(benchmark.DEFAULT_CHUNK_SIZE, 16_384)


if __name__ == "__main__":
    unittest.main()
