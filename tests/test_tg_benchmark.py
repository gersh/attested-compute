# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
import stat
import tempfile
import unittest

from tg_verifier.benchmark import (
    BenchmarkError,
    build_benchmark_report,
    full_campaign_estimates,
    run_gpu_integer_microbenchmark,
)


class TernaryGoldbachBenchmarkTests(unittest.TestCase):
    def test_all_thirteen_have_server_and_h100_classifications(self) -> None:
        estimates = full_campaign_estimates()
        self.assertEqual(len(estimates), 13)
        self.assertEqual(len({row["id"] for row in estimates}), 13)
        for row in estimates:
            self.assertIn("status", row["server"])
            self.assertIn("basis", row["server"])
            self.assertIn("status", row["h100_sxm"])
            self.assertIn("basis", row["h100_sxm"])

    def test_gpu_report_scope_is_checked(self) -> None:
        fixture = {
            "benchmark": "tg_integer_work_item_microbenchmark",
            "classification": "planning_microbenchmark_not_verification",
            "endpoint_check": True,
            "proves_any_external_atom": False,
            "count_per_repetition": 4,
            "repetitions": 2,
            "device_name": "test device",
            "compute_capability": "9.0",
            "kernel_milliseconds": 1.0,
            "work_items_per_second": 8.0,
            "minimum_output_bytes_per_second": 64.0,
        }
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "fixture.py"
            executable.write_text(
                "#!/usr/bin/env python3\nimport json\nprint(json.dumps("
                + repr(fixture)
                + "))\n",
                encoding="utf-8",
            )
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
            self.assertEqual(
                run_gpu_integer_microbenchmark(
                    executable, count=4, repetitions=2
                )["endpoint_check"],
                True,
            )

            fixture["count_per_repetition"] = 5
            executable.write_text(
                "#!/usr/bin/env python3\nimport json\nprint(json.dumps("
                + repr(fixture)
                + "))\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(BenchmarkError, "count differs"):
                run_gpu_integer_microbenchmark(executable, count=4, repetitions=2)

    def test_small_report_discloses_all_nonclaims(self) -> None:
        report = build_benchmark_report(
            gpu_executable=None,
            gpu_count=4,
            gpu_repetitions=2,
            mobius_limit=100,
            exact_fraction_limit=20,
        )
        self.assertEqual(
            report["classification"],
            "measured_samples_plus_explicit_planning_ranges",
        )
        self.assertEqual(report["gpu_microbenchmark"]["status"], "not_run")
        self.assertEqual(
            report["cpu_reference"]["squarefree_b1"]["status"], "not_run"
        )
        self.assertTrue(
            any("not an H100 measurement" in item for item in report["nonclaims"])
        )
        # Ensure the report remains clean JSON.
        json.dumps(report)


if __name__ == "__main__":
    unittest.main()
