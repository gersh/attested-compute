# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tiny fail-before-read tests for legacy production campaign CLIs."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tg_verifier import binary_goldbach_campaign
from tg_verifier.campaign_io import (
    AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS,
    MeasuredWorkerScopeError,
    azure_measured_worker_environment,
    canonical_json_bytes,
    require_azure_measured_worker_for_workload,
)
from tg_verifier.goldbach_gpu_campaign import make_bounded_sample_plan
from tg_verifier.prop1224_parallel_campaign import make_directed_plan
from tg_verifier.platt_zeta_campaign import create_plan as create_platt_plan
from tools.tg_goldbach_gpu_campaign import _guard_shards
from tools.tg_prop1224_parallel import guard_directed_shard
from tg_verifier.platt_windowed_campaign import (
    FULL_BLOCK_COUNT as PLATT_WINDOWED_FULL_BLOCK_COUNT,
    create_plan as create_platt_windowed_plan,
)


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


class WorkloadSizeGuardTests(unittest.TestCase):
    def test_local_kat_bounds_through_64_do_not_require_cloud(self) -> None:
        self.assertIsNone(
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(0, 1, 64),
                environment={},
            )
        )

    def test_non_tiny_bound_requires_cloud(self) -> None:
        with self.assertRaisesRegex(
            MeasuredWorkerScopeError, "cloud-only"
        ):
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(65,),
                environment={},
            )

    def test_empty_nonproduction_bounds_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            MeasuredWorkerScopeError, "at least one finite workload bound"
        ):
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(),
                environment={},
            )

    def test_runner_bound_production_work_is_accepted(self) -> None:
        environment = azure_measured_worker_environment(
            {},
            backend="azure_sevsnp_cpu",
            challenge_nonce="1" * 64,
            job_binding="2" * 64,
        )
        self.assertEqual(
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
                environment=environment,
            ),
            "azure_sevsnp_cpu",
        )


class LegacyProductionCLIGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.environment = dict(os.environ)
        for key in AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS:
            self.environment.pop(key, None)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_control(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(value))

    def _assert_cloud_only(self, command: list[str]) -> None:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(completed.returncode, 2, completed)
        self.assertIn("cloud-only", completed.stderr + completed.stdout)

    def test_psi_source_run_stops_after_config_metadata(self) -> None:
        campaign = self.root / "psi"
        self._write_control(
            campaign / "campaign-config.json",
            {
                "mode": "full_source",
                "domain_lower": 2,
                "domain_upper_exclusive": 10_000_000_000_001,
                "shard_span": 100_000_000,
            },
        )
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_psi_residual_campaign.py"),
                "run",
                str(campaign),
                "summary",
                "--shard",
                "0",
                "--workers",
                "1",
            ]
        )
        self.assertFalse((campaign / "captured-psi-residual-runner").exists())

    def test_hurst_source_run_stops_after_config_metadata(self) -> None:
        campaign = self.root / "hurst"
        self._write_control(
            campaign / "campaign-config.json",
            {
                "mode": "full_source",
                "domain_lower": 1,
                "domain_upper_exclusive": 10_000_000_000_000_001,
                "shard_span": 1_000_000_000_000,
            },
        )
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_hurst_residual_campaign.py"),
                "run",
                str(campaign),
                "summary",
                "--shard",
                "0",
            ]
        )
        self.assertFalse((campaign / "captured-hurst-residual-runner").exists())

    def test_prop1224_exact_plan_stops_before_runner_or_output(self) -> None:
        output = self.root / "prop1224-output"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_prop1224_mpfr_campaign.py"),
                "run-shard",
                str(self.root / "absent-prop1224-runner"),
                str(output),
                "0",
            ]
        )
        self.assertFalse(output.exists())

    def test_r2star_full_run_stops_before_runner_or_output(self) -> None:
        output = self.root / "r2star-output"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_r2star_campaign.py"),
                "run",
                "--runner",
                str(self.root / "absent-r2star-runner"),
                "--output-dir",
                str(output),
            ]
        )
        self.assertFalse(output.exists())

    def test_platt_source_shard_stops_before_captured_runner(self) -> None:
        campaign = self.root / "platt"
        plan = create_platt_plan(
            runner_sha256="0" * 64,
            runner_size=1,
            source_sha256="1" * 64,
            source_size=1,
            upstream_sha256="2" * 64,
        )
        self._write_control(campaign / "campaign.json", plan)
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_platt_zeta_campaign.py"),
                "run-shard",
                str(campaign),
                "0",
            ]
        )
        self.assertFalse((campaign / "captured-platt-zeta-shard").exists())

    def test_goldbach_full_stops_before_workspace_creation(self) -> None:
        workspace = self.root / "goldbach-full"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_goldbach_campaign.py"),
                "full",
                str(workspace),
            ]
        )
        self.assertFalse(workspace.exists())

    def test_binary_goldbach_run_stops_before_chunk_replay(self) -> None:
        campaign = self.root / "binary-goldbach"
        binary_goldbach_campaign.initialize(campaign)
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_binary_goldbach_campaign.py"),
                "run",
                str(campaign),
                "--max-new-chunks",
                "1",
            ]
        )
        self.assertEqual(list((campaign / "chunks").iterdir()), [])

    def test_binary_goldbach_64_even_kat_remains_local(self) -> None:
        campaign = self.root / "binary-goldbach-kat"
        binary_goldbach_campaign.initialize(
            campaign,
            binary_goldbach_campaign.Parameters(
                first_even=4,
                last_even=130,
                # The configured capacity is large, but the actual sole chunk
                # contains exactly 64 evens.
                evens_per_chunk=10**13,
                mode="bounded_test",
            ),
        )
        completed = subprocess.run(
            [
                PYTHON,
                str(ROOT / "tools/tg_binary_goldbach_campaign.py"),
                "run",
                str(campaign),
                "--max-new-chunks",
                "1",
            ],
            cwd=ROOT,
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("cloud-only", completed.stderr)

    def test_legacy_prop1224_source_run_stops_before_output(self) -> None:
        output = self.root / "legacy-prop1224"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_prop1224_campaign.py"),
                "run",
                str(output),
                "--max-chunks",
                "1",
            ]
        )
        self.assertFalse(output.exists())

    def test_legacy_prop1224_replay_stops_before_campaign_read(self) -> None:
        absent = self.root / "absent-legacy-prop1224"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_prop1224_campaign.py"),
                "replay",
                str(absent),
                "--max-chunks",
                "1",
            ]
        )
        self.assertFalse(absent.exists())

    def test_prop1224_parallel_source_shard_stops_before_output(self) -> None:
        output = self.root / "parallel-prop1224"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_prop1224_parallel.py"),
                "run-shard",
                str(output),
                "0",
            ]
        )
        self.assertFalse(output.exists())

    def test_prop1224_parallel_64_row_non_q1_kat_remains_local(self) -> None:
        plan = make_directed_plan(
            rank_lower=1,
            rank_upper=65,
            leaf_rows=64,
        )
        self.assertIsNone(guard_directed_shard(plan, 0))

    def test_prop1224_parallel_q1_is_not_misclassified_as_one_work_item(self) -> None:
        plan = make_directed_plan(
            rank_lower=0,
            rank_upper=1,
            leaf_rows=1,
        )
        with self.assertRaisesRegex(MeasuredWorkerScopeError, "cloud-only"):
            guard_directed_shard(plan, 0)

    def test_legacy_psi_source_run_stops_before_output(self) -> None:
        output = self.root / "legacy-psi"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_psi_campaign.py"),
                "run",
                str(output),
                "--max-chunks",
                "1",
            ]
        )
        self.assertFalse(output.exists())

    def test_legacy_psi_replay_stops_before_campaign_read(self) -> None:
        absent = self.root / "absent-legacy-psi"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_psi_campaign.py"),
                "replay",
                str(absent),
                "--max-chunks",
                "1",
            ]
        )
        self.assertFalse(absent.exists())

    def test_structural_receipt_inspection_is_not_cloud_gated(self) -> None:
        for tool, label in (
            ("tg_prop1224_campaign.py", "Proposition 12.2.4 campaign error"),
            ("tg_psi_campaign.py", "psi campaign error"),
            ("tg_r2star_campaign.py", "R2Star campaign error"),
        ):
            with self.subTest(tool=tool):
                completed = subprocess.run(
                    [
                        PYTHON,
                        str(ROOT / f"tools/{tool}"),
                        "verify",
                        str(self.root / f"absent-{tool}"),
                    ],
                    cwd=ROOT,
                    env=self.environment,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                diagnostic = completed.stderr + completed.stdout
                self.assertEqual(completed.returncode, 2, completed)
                self.assertNotIn("cloud-only", diagnostic)
                self.assertIn(label, diagnostic)

    def test_goldbach_gpu_non_tiny_shard_stops_before_source_or_executable(self) -> None:
        plan = make_bounded_sample_plan(
            even_start=4,
            even_limit=132,
            shard_count=1,
            executable_sha256="0" * 64,
        )
        plan_path = self.root / "goldbach-gpu-plan.json"
        self._write_control(plan_path, plan.to_dict())
        output = self.root / "goldbach-gpu-output"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_goldbach_gpu_campaign.py"),
                "run-shard",
                str(plan_path),
                "0",
                "--source-root",
                str(self.root / "absent-source"),
                "--executable",
                str(self.root / "absent-executable"),
                "--output-dir",
                str(output),
            ]
        )
        self.assertFalse(output.exists())

    def test_goldbach_gpu_64_even_kat_remains_local(self) -> None:
        plan = make_bounded_sample_plan(
            even_start=4,
            even_limit=130,
            shard_count=1,
            executable_sha256="0" * 64,
        )
        self.assertIsNone(_guard_shards(plan, (0,)))

    def test_r2star_non_tiny_benchmark_stops_before_executable_read(self) -> None:
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_r2star_benchmark.py"),
                "--runner",
                str(self.root / "absent-r2star-runner"),
                "--arithmetic-replayer",
                str(self.root / "absent-r2star-replayer"),
                "--lower",
                "1",
                "--count",
                "65",
            ]
        )

    def test_r2star_64_row_benchmark_reaches_normal_input_validation(self) -> None:
        completed = subprocess.run(
            [
                PYTHON,
                str(ROOT / "tools/tg_r2star_benchmark.py"),
                "--runner",
                str(self.root / "absent-r2star-runner"),
                "--arithmetic-replayer",
                str(self.root / "absent-r2star-replayer"),
                "--lower",
                "1",
                "--count",
                "64",
            ],
            cwd=ROOT,
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(completed.returncode, 2, completed)
        self.assertNotIn("cloud-only", completed.stderr + completed.stdout)
        self.assertIn("cannot resolve", completed.stderr + completed.stdout)

    def test_direct_reference_ranges_above_64_are_cloud_only(self) -> None:
        for command in (
            ["sample-arithmetic", "--limit", "65"],
            ["verify-psi-range", "--limit", "65"],
            [
                "verify-r2star-range",
                "--limit",
                "65",
                "--harmonic-terms",
                "64",
            ],
            [
                "verify-prop1224-sample",
                "--q",
                "100000",
                "--log-terms",
                "32",
                "--max-pairs",
                "65",
            ],
        ):
            with self.subTest(command=command[0]):
                self._assert_cloud_only(
                    [PYTHON, str(ROOT / "tools/tg_verify.py"), *command]
                )

    def test_goldbach_10pow27_combine_stops_before_artifact_read(self) -> None:
        output = self.root / "combined-10pow27.json"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_goldbach_10pow27_campaign.py"),
                "combine",
                str(self.root / "absent-ladder"),
                "--ladder-aggregate",
                str(self.root / "absent-ladder-aggregate"),
                "--binary-plan",
                str(self.root / "absent-binary-plan"),
                "--binary-receipts-dir",
                str(self.root / "absent-binary-receipts"),
                "--binary-aggregate",
                str(self.root / "absent-binary-aggregate"),
                "--out",
                str(output),
            ]
        )
        self.assertFalse(output.exists())

    def test_goldbach_10pow27_finalizer_stops_before_artifact_read(self) -> None:
        output = self.root / "finalized-10pow27.json"
        registered = self.root / "registered-10pow27.txt"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_goldbach_10pow27_finalizer.py"),
                str(self.root / "absent-ladder"),
                "--ladder-aggregate",
                str(self.root / "absent-ladder-aggregate"),
                "--binary-plan",
                str(self.root / "absent-binary-plan"),
                "--binary-receipts-dir",
                str(self.root / "absent-binary-receipts"),
                "--binary-aggregate",
                str(self.root / "absent-binary-aggregate"),
                "--combined-out",
                str(output),
                "--registered-result-output",
                str(registered),
            ]
        )
        self.assertFalse(output.exists())
        self.assertFalse(registered.exists())

    def test_historical_finalizer_stops_before_artifact_read(self) -> None:
        output = self.root / "combined-historical.json"
        registered = self.root / "registered-historical.txt"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_goldbach_historical_finalizer.py"),
                str(self.root / "absent-ladder"),
                "--ladder-aggregate",
                str(self.root / "absent-ladder-aggregate"),
                "--binary-plan",
                str(self.root / "absent-binary-plan"),
                "--binary-receipts-dir",
                str(self.root / "absent-binary-receipts"),
                "--binary-aggregate",
                str(self.root / "absent-binary-aggregate"),
                "--combined-out",
                str(output),
                "--registered-result-output",
                str(registered),
            ]
        )
        self.assertFalse(output.exists())
        self.assertFalse(registered.exists())

    def test_native_goldbach_range_stops_before_campaign_or_runner_read(self) -> None:
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_goldbach_ladder_native.py"),
                "produce-range",
                str(self.root / "absent-native-ladder"),
                "0",
                "--runner",
                str(self.root / "absent-native-runner"),
            ]
        )

    def test_native_goldbach_non_tiny_segment_stops_before_runner_read(self) -> None:
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_goldbach_ladder_native.py"),
                "segment",
                "--runner",
                str(self.root / "absent-native-runner"),
                "--anchor-number",
                "3",
                "--target-number",
                "68",
            ]
        )

    def test_native_goldbach_64_candidate_segment_remains_local(self) -> None:
        completed = subprocess.run(
            [
                PYTHON,
                str(ROOT / "tools/tg_goldbach_ladder_native.py"),
                "segment",
                "--runner",
                str(self.root / "absent-native-runner"),
                "--anchor-number",
                "3",
                "--target-number",
                "67",
            ],
            cwd=ROOT,
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        diagnostic = completed.stderr + completed.stdout
        self.assertEqual(completed.returncode, 2, completed)
        self.assertNotIn("cloud-only", diagnostic)
        self.assertIn("runner must be an executable", diagnostic)

    def test_full_a7_replay_stops_before_artifact_read(self) -> None:
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_verify.py"),
                "replay-a7-flint",
                str(self.root / "absent-a7.json"),
            ]
        )

    def test_full_cdem_producer_stops_before_source_read(self) -> None:
        transcript = self.root / "cdem-transcript.txt"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_verify.py"),
                "run-cdem-abel",
                str(self.root / "absent-cdem.cpp"),
                "--transcript-output",
                str(transcript),
            ]
        )
        self.assertFalse(transcript.exists())

    def test_cdem_chunk_replay_stops_before_transcript_read(self) -> None:
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_verify.py"),
                "replay-cdem-abel-chunks",
                str(self.root / "absent-cdem-transcript.txt"),
                "--index",
                "0",
            ]
        )

    def test_zeta_count_above_kat_limit_stops_before_flint_load(self) -> None:
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_zeta_campaign.py"),
                "count",
                "--height",
                "65",
            ]
        )

    def test_zeta_full_stops_before_workspace_creation(self) -> None:
        campaign = self.root / "zeta-full"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_zeta_campaign.py"),
                "full",
                str(campaign),
                "--profile",
                "platt-head-2e4",
            ]
        )
        self.assertFalse(campaign.exists())

    def test_platt_windowed_init_stops_before_runner_read(self) -> None:
        campaign = self.root / "platt-windowed-full"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_platt_windowed_campaign.py"),
                "init",
                str(campaign),
                "--runner",
                str(self.root / "absent-platt-windowed-runner"),
            ]
        )
        self.assertFalse(campaign.exists())

    def test_platt_windowed_block_is_not_misclassified_as_tiny(self) -> None:
        campaign = self.root / "platt-windowed-kat"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_platt_windowed_campaign.py"),
                "init",
                str(campaign),
                "--runner",
                str(self.root / "absent-platt-windowed-runner"),
                "--blocks-per-shard",
                "1",
                "--block-count",
                "1",
                "--allow-bounded-test",
            ]
        )
        self.assertFalse(campaign.exists())

    def test_platt_windowed_shard_stops_after_plan_before_runner_read(self) -> None:
        campaign = self.root / "platt-windowed-run"
        plan = create_platt_windowed_plan(
            runner_sha256="0" * 64,
            runner_size=1,
            source_manifest_sha256="1" * 64,
            source_manifest_size=1,
            block_count=PLATT_WINDOWED_FULL_BLOCK_COUNT,
        )
        self._write_control(campaign / "campaign.json", plan)
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_platt_windowed_campaign.py"),
                "run-shard",
                str(campaign),
                "0",
                "--runner",
                str(self.root / "absent-platt-windowed-runner"),
            ]
        )
        self.assertFalse((campaign / "receipts").exists())

    def test_lmfdb_shard_audit_stops_before_plan_or_data_read(self) -> None:
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_lmfdb_zeta_prefix_campaign.py"),
                "audit-shard",
                str(self.root / "absent-lmfdb-campaign"),
                "0",
                "--data-directory",
                str(self.root / "absent-lmfdb-data"),
            ]
        )

    def test_mobius_full_run_stops_before_runner_or_output_read(self) -> None:
        campaign = self.root / "mobius-full"
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_mobius_campaign.py"),
                "run",
                "--runner",
                str(self.root / "absent-mobius-runner"),
                "--output-dir",
                str(campaign),
                "--target",
                "stronger",
            ]
        )
        self.assertFalse(campaign.exists())

    def test_mobius_verify_stops_before_campaign_artifact_read(self) -> None:
        self._assert_cloud_only(
            [
                PYTHON,
                str(ROOT / "tools/tg_mobius_campaign.py"),
                "verify",
                str(self.root / "absent-mobius-campaign"),
            ]
        )

    def test_mobius_explicit_64_item_kat_reaches_runner_validation(self) -> None:
        campaign = self.root / "mobius-kat"
        completed = subprocess.run(
            [
                PYTHON,
                str(ROOT / "tools/tg_mobius_campaign.py"),
                "run",
                "--runner",
                str(self.root / "absent-mobius-runner"),
                "--output-dir",
                str(campaign),
                "--target",
                "stronger",
                "--segment-count",
                "64",
                "--max-chunks",
                "1",
                "--allow-bounded-test",
            ],
            cwd=ROOT,
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(completed.returncode, 2, completed)
        self.assertNotIn("cloud-only", completed.stderr + completed.stdout)


if __name__ == "__main__":
    unittest.main()
