# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tests.test_tg_r2star_campaign import exact_small_receipt
from tg_verifier.r2star_benchmark import (
    R2StarBenchmarkError,
    benchmark_exact_pair,
)


def completed(stdout: bytes) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess([], 0, stdout, b"")


class R2StarBenchmarkTests(unittest.TestCase):
    def test_pair_benchmark_is_explicitly_nonadmissible(self) -> None:
        receipt = json.dumps(
            exact_small_receipt(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        replay = (
            b'{"checked_chunks":1,"checked_rows":500,'
            b'"classification":"bounded_cpu_r2star_arithmetic_replay_benchmark_v1",'
            b'"source_lower":1,"source_upper_exclusive":501,'
            b'"status":"BENCHMARK_ONLY"}\n'
        )
        with tempfile.TemporaryDirectory() as temporary:
            runner = Path(temporary) / "runner"
            replayer = Path(temporary) / "replayer"
            for path in (runner, replayer):
                path.write_bytes(b"test executable")
                path.chmod(0o700)
            with mock.patch(
                "tg_verifier.r2star_benchmark._run_bounded",
                side_effect=[
                    (completed(receipt), 1_000_000_000),
                    (completed(replay), 500_000_000),
                ],
            ):
                report = benchmark_exact_pair(
                    runner=runner,
                    arithmetic_replayer=replayer,
                    lower=1,
                    count=500,
                )
        self.assertFalse(report["admissible_as_external_atom_evidence"])
        self.assertFalse(report["target_sku_measurement"])
        self.assertEqual(report["producer_median_rows_per_second_floor"], 500)
        self.assertEqual(report["replay_median_rows_per_second_floor"], 1000)

    def test_production_pass_spelling_is_rejected_in_benchmark_mode(self) -> None:
        receipt = json.dumps(
            exact_small_receipt(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        wrong = (
            b'{"checked_chunks":1,"checked_rows":500,'
            b'"classification":"independent_cpu_full_row_arithmetic_replay_v1",'
            b'"expected_limit":500,"status":"PASS"}\n'
        )
        with tempfile.TemporaryDirectory() as temporary:
            runner = Path(temporary) / "runner"
            replayer = Path(temporary) / "replayer"
            for path in (runner, replayer):
                path.write_bytes(b"test executable")
                path.chmod(0o700)
            with mock.patch(
                "tg_verifier.r2star_benchmark._run_bounded",
                side_effect=[
                    (completed(receipt), 1),
                    (completed(wrong), 1),
                ],
            ):
                with self.assertRaisesRegex(
                    R2StarBenchmarkError, "benchmark-only report"
                ):
                    benchmark_exact_pair(
                        runner=runner,
                        arithmetic_replayer=replayer,
                        lower=1,
                        count=500,
                    )


if __name__ == "__main__":
    unittest.main()
