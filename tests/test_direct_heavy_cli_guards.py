# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-before-path tests for direct heavy-work command-line routes."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tg_verifier.campaign_io import AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS
from tg_verifier.goldbach_campaign import (
    GENERAL_REQUEST_KIND,
    canonical_json_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


class DirectHeavyCLIGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.environment = dict(os.environ)
        for key in AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS:
            self.environment.pop(key, None)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _run(self, script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(ROOT / "tools" / script), *arguments],
            cwd=ROOT,
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def _assert_cloud_only(
        self, script: str, *arguments: str
    ) -> subprocess.CompletedProcess[str]:
        completed = self._run(script, *arguments)
        diagnostic = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 2, completed)
        self.assertIn("production arithmetic/replay is cloud-only", diagnostic)
        return completed

    def test_generic_full_campaign_run_stops_before_workspace_creation(self) -> None:
        workspace = self.root / "must-not-be-created"
        self._assert_cloud_only("tg_campaign.py", "run", str(workspace))
        self.assertFalse(workspace.exists())

    def test_goldbach_binary_checker_stops_before_request_read(self) -> None:
        self._assert_cloud_only(
            "tg_goldbach_gpu_binary_checker.py",
            "--request",
            str(self.root / "absent-request"),
            "--artifact",
            str(self.root / "absent-aggregate"),
        )

    def test_pt21_production_replay_stops_before_archive_read(self) -> None:
        self._assert_cloud_only(
            "tg_platt_pt21_native_finalizer.py",
            "replay-shard",
            str(self.root / "absent-archive"),
        )

    def test_pt21_non_tiny_bounded_replay_is_cloud_only(self) -> None:
        self._assert_cloud_only(
            "tg_platt_pt21_native_finalizer.py",
            "replay-shard",
            str(self.root / "absent-archive"),
            "--allow-bounded-test",
            "--max-kat-records",
            "65",
        )

    def test_lmfdb_target_stream_stops_before_inventory_read(self) -> None:
        self._assert_cloud_only(
            "tg_lmfdb_zeta_prefix.py",
            str(self.root / "absent-filelist"),
            str(self.root / "absent-md5"),
            "--target-file",
            str(self.root / "absent-target"),
        )

    def test_stationary_trace_replay_stops_before_trace_read(self) -> None:
        self._assert_cloud_only(
            "tg_platt_stationary_trace.py",
            str(self.root / "absent-trace"),
        )

    def test_gamma_stream_replay_stops_before_stream_read(self) -> None:
        self._assert_cloud_only(
            "tg_platt_gamma_taylor_stream.py",
            str(self.root / "absent-stream"),
        )

    def test_h100_cluster_execute_stops_before_manifest_read(self) -> None:
        self._assert_cloud_only(
            "tg_h100_cluster.py",
            "execute",
            str(self.root / "absent-manifest"),
            "--atom",
            "ch25-a7-boundary",
        )

    def test_platt_h100_block_replay_stops_before_artifact_read(self) -> None:
        self._assert_cloud_only(
            "tg_platt_h100_campaign.py",
            "validate-block",
            str(self.root / "absent-block"),
        )

    def test_non_tiny_fused_dirichlet_input_stops_before_output(self) -> None:
        output = self.root / "must-not-create-dirichlet-input"
        self._assert_cloud_only(
            "tg_dirichlet_fused_stage.py",
            "synthetic-input",
            str(output),
            "--q",
            "65",
            "--all-characters",
        )
        self.assertFalse(output.exists())

    def test_non_tiny_pt21_record_adaptation_stops_before_manifest(self) -> None:
        self._assert_cloud_only(
            "tg_platt_pt21_native_record_adapter.py",
            "shard",
            "--manifest",
            str(self.root / "absent-manifest"),
            "--worker",
            str(self.root / "absent-worker"),
            "--output",
            str(self.root / "must-not-create-native-shard"),
            "--first-block",
            "0",
            "--block-count",
            "65",
        )

    def test_non_tiny_pt21_streamed_shard_stops_before_inputs(self) -> None:
        self._assert_cloud_only(
            "tg_platt_pt21_native_record_adapter.py",
            "shard-archive",
            "--manifest",
            str(self.root / "absent-manifest"),
            "--expected-manifest-sha256",
            "11" * 32,
            "--worker",
            str(self.root / "absent-worker"),
            "--finalizer",
            str(self.root / "absent-finalizer"),
            "--expected-finalizer-sha256",
            "22" * 32,
            "--output",
            str(self.root / "must-not-create-native-shard"),
            "--first-block",
            "0",
            "--block-count",
            "65",
            "--plan-sha256",
            "33" * 32,
            "--prefix-evidence-sha256",
            "44" * 32,
            "--bounded-test",
        )

    def test_pt21_production_fused_shard_stops_before_artifact_read(self) -> None:
        self._assert_cloud_only(
            "tg_platt_pt21_fused_artifact.py",
            "shard",
            "--first-block",
            "0",
            str(self.root / "absent-block"),
        )

    def test_non_tiny_pocklington_search_stops_before_search_or_output(self) -> None:
        request = self.root / "pocklington-request.json"
        output = self.root / "must-not-create-pocklington-output"
        request.write_bytes(
            canonical_json_bytes(
                {
                    "kind": GENERAL_REQUEST_KIND,
                    "lower_exclusive": "100",
                    # There are 65 candidate integers in this interval.
                    "upper_exclusive": "166",
                }
            )
        )
        self._assert_cloud_only(
            "tg_pocklington_producer.py",
            "--request",
            str(request),
            "--output",
            str(output),
        )
        self.assertFalse(output.exists())

    def test_large_planning_benchmark_stops_before_executable_read(self) -> None:
        self._assert_cloud_only(
            "benchmark_tg_verifiers.py",
            "--gpu-executable",
            str(self.root / "absent-runner"),
        )

    def test_large_primitive_conformance_stops_before_runner_read(self) -> None:
        self._assert_cloud_only(
            "run_primitive_conformance.py",
            "--count",
            "65",
            "--executable",
            str(self.root / "absent-runner"),
        )

    def test_large_expression_conformance_stops_before_runner_read(self) -> None:
        self._assert_cloud_only(
            "run_expression_conformance.py",
            "--count",
            "65",
            "--executable",
            str(self.root / "absent-runner"),
        )

    def test_64_row_conformance_kats_reach_normal_path_validation(self) -> None:
        for script in (
            "run_primitive_conformance.py",
            "run_expression_conformance.py",
        ):
            with self.subTest(script=script):
                completed = self._run(
                    script,
                    "--count",
                    "64",
                    "--executable",
                    str(self.root / f"absent-{script}"),
                )
                diagnostic = completed.stdout + completed.stderr
                self.assertEqual(completed.returncode, 2, completed)
                self.assertNotIn("cloud-only", diagnostic)
                self.assertIn("does not exist", diagnostic)

    def test_make_convenience_workloads_are_bounded_kats(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("run_primitive_conformance.py --count 64", makefile)
        self.assertIn("run_expression_conformance.py --count 64", makefile)
        self.assertIn("--mobius-limit 64 --exact-fraction-limit 64", makefile)
        self.assertIn("--psi-limit 64", makefile)
        self.assertIn("\ntg-benchmark:\n", makefile)
        self.assertNotIn("\ntg-benchmark: probe\n", makefile)
        self.assertNotIn("run_primitive_conformance.py --count 10000", makefile)
        self.assertNotIn("run_expression_conformance.py --count 10000", makefile)
        self.assertNotIn("--psi-limit 100000", makefile)


if __name__ == "__main__":
    unittest.main()
