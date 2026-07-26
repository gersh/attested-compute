# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "gpu/include/sparkinterval/tg_platt_dd_accumulator.hpp"
ACCUMULATOR = (
    ROOT / "gpu/platform/h100/h100_tg_platt_windowed_core.cu"
)
ACCUMULATOR_SMOKE = (
    ROOT / "reference/tg_platt_dd_accumulator_api_smoke.cu"
)
QUALIFICATION = (
    ROOT / "reference/tg_platt_pt21_recentered_pipeline_qualification.cu"
)
PRODUCTION_WORKER = (
    ROOT / "gpu/platform/h100/h100_tg_platt_fused_source_worker_v2.cu"
)
RUNNER_ENV = "TG_PLATT_PT21_RECENTERED_PIPELINE"
STREAM_ENV = "TG_PLATT_PT21_RECENTERED_PIPELINE_STREAM"
STREAM_SHA_ENV = "TG_PLATT_PT21_RECENTERED_PIPELINE_STREAM_SHA256"


class PlattPT21RecenteredPipelineTest(unittest.TestCase):
    def test_contract_is_additive_bounded_and_nonproduction(self) -> None:
        header = HEADER.read_text(encoding="utf-8")
        accumulator = ACCUMULATOR.read_text(encoding="utf-8")
        accumulator_smoke = ACCUMULATOR_SMOKE.read_text(
            encoding="utf-8"
        )
        qualification = QUALIFICATION.read_text(encoding="utf-8")
        production = PRODUCTION_WORKER.read_text(encoding="utf-8")
        for token in (
            "create_source_workspace_with_output_slots_qualification",
            "run_next_source_window_to_slot_qualification",
            "output_slot_count",
            "output_slots < 2U || output_slots > 4U",
            "output_slot >= workspace->output_slots",
        ):
            self.assertIn(token, header + accumulator)
        for token in (
            "Resources(const Resources&) = delete",
            "cudaStreamSynchronize(producer)",
            "cudaStreamSynchronize(consumer)",
            "ordinary_center_per_logical_block",
            "shifted_view_reuse",
            "byte_identical_required_samples",
            "byte_identical_event_artifacts",
            "independent_fixed_integer_replay_complete",
            "first_category_blocks",
            "interior_category_blocks",
            "reanchor_category_blocks",
            "terminal_category_blocks",
            "build_profile",
            "cmake_build_config",
            "release_performance_build",
            "production_worker_changed",
            "production_ready",
            "pt21_atom_discharged",
        ):
            self.assertIn(token, qualification)
        self.assertNotIn(
            "run_next_source_window_to_slot_qualification", production
        )
        self.assertNotIn(
            "create_source_workspace_with_output_slots_qualification",
            production,
        )
        for token in (
            "CUDA_CHECK(cudaMemset(workspace->output, 0",
            "output_cells * output_slots",
            "inactive cell",
        ):
            self.assertIn(token, accumulator)
        for token in (
            "count_nonzero_inactive",
            "device_bucket_offsets_qualification",
            "device_active_buckets_qualification",
            "active_bucket_count_qualification",
            "kExpectedActiveBuckets = 6'674U",
            "audit_active_roster",
            "poison_active_cells",
            "count_poisoned_active_cells",
            "active_roster_matches_nonempty_offsets",
            "every_active_stage_cell_overwritten",
            "one_slot_inactive_cells_exact_zero",
            "qualification_inactive_cells_exact_zero",
            "inactive_cells_audited_per_slot",
        ):
            self.assertIn(token, accumulator_smoke)
        destructor = qualification.split("~Resources()", 1)[1].split(
            "};", 1
        )[0]
        self.assertLess(
            destructor.index("cudaStreamSynchronize(producer)"),
            destructor.index("for (pes::ReplayCapture* capture"),
        )
        self.assertLess(
            destructor.index("cudaStreamSynchronize(consumer)"),
            destructor.index("for (pes::ReplayCapture* capture"),
        )

    def test_optional_genuine_stream_byte_identity(self) -> None:
        runner = os.environ.get(RUNNER_ENV)
        stream = os.environ.get(STREAM_ENV)
        stream_sha = os.environ.get(STREAM_SHA_ENV)
        if not runner or not stream or not stream_sha:
            self.skipTest(
                f"set {RUNNER_ENV}, {STREAM_ENV}, and {STREAM_SHA_ENV}"
            )
        completed = subprocess.run(
            [
                runner,
                stream,
                f"--expected-stream-sha256={stream_sha}",
                "--reanchor-blocks=2",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0)
        self.assertTrue(result["accepted"])
        self.assertTrue(result["qualification_only"])
        self.assertEqual(result["pipeline_slots"], 2)
        self.assertTrue(result["ordinary_center_per_logical_block"])
        self.assertFalse(result["shifted_view_reuse"])
        self.assertEqual(result["sample_mismatch_blocks"], 0)
        self.assertEqual(result["artifact_mismatch_blocks"], 0)
        self.assertEqual(result["replay_failure_blocks"], 0)
        self.assertTrue(result["byte_identical_required_samples"])
        self.assertTrue(result["byte_identical_event_artifacts"])
        self.assertTrue(result["independent_fixed_integer_replay_complete"])
        self.assertTrue(result["categories_complete"])
        self.assertGreater(result["first_category_blocks"], 0)
        self.assertGreater(result["interior_category_blocks"], 0)
        self.assertGreater(result["reanchor_category_blocks"], 0)
        self.assertGreater(result["terminal_category_blocks"], 0)
        self.assertEqual(
            result["extra_accumulator_output_bytes"], 30_146_560
        )
        self.assertEqual(result["extra_gamma_row_bytes"], 1_310_720)
        profile = result["build_profile"]
        self.assertIn("cmake_build_config", profile)
        self.assertIn("ndebug_defined", profile)
        self.assertIn("release_performance_build", profile)
        self.assertFalse(result["production_worker_changed"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["pt21_atom_discharged"])


if __name__ == "__main__":
    unittest.main()
