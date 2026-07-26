# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import asdict
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tg_verifier.r2star import create_r2star_chunk
from tg_verifier.r2star_campaign import (
    DEFAULT_ARITHMETIC_REPLAY_SEGMENT_ROWS,
    R2StarCampaignError,
    R2StarCampaignResult,
    REGISTERED_RESULT_SHA256,
    verify_runner_receipt,
    write_registered_result,
)
from tg_verifier.azure_portfolio import (
    PENDING_TG_REALIZATIONS,
    SOURCE_TG_TERMINAL_RESULTS,
    _validate_semantic_bindings,
)
from tg_verifier.h100_cluster import WORKLOADS_BY_ID
from tools import tg_r2star_campaign as campaign_cli


ROOT = Path(__file__).resolve().parents[1]


def exact_small_receipt() -> dict[str, object]:
    chunk = create_r2star_chunk(
        lower=1,
        upper=501,
        scale_bits=32,
        series_terms=20,
        harmonic_terms=100_000,
        incoming_lower=0,
        incoming_upper=0,
    )
    return {
        "receipt_schema": "sparkinterval.r2star-bounded-chunk.v1",
        "classification": "bounded_exact_python_contract_chunk_not_full_atom_proof",
        "chunk": asdict(chunk),
        "factor_support_encoding": "r2star-distinct-prime-support-u64be-v1",
        "factor_support_digest_producer": "independent_host_segmented_exact_factorization_v1",
        "gpu_capped_factor_support_matches_host": True,
        "directed_rows_sha256_le_v1": "1" * 64,
        "ambiguous_log_rows": 0,
        "exact_rational_fallback_rows": 0,
        "integer_overflow_rows": 0,
        "log_algorithm": "q64_directed_atanh_with_exact_rational_host_fallback_v1",
        "prefix_implementation": "deterministic_blocked_exact_scan_v1",
        "serial_cross_check_performed": False,
        "device_name": "test device",
        "compute_capability": "0.0",
        "cuda_driver_api_version": 0,
        "cuda_runtime_version": 0,
        "kernel_milliseconds": 1,
        "factor_kernel_milliseconds": 1,
        "directed_row_kernel_milliseconds": 1,
        "parallel_transition_kernel_milliseconds": 1,
        "serial_reference_kernel_milliseconds": 0,
        "independent_factor_check_milliseconds": 1,
        "full_source_range": False,
        "python_contract_replay_required": True,
        "hash_chain_is_integrity_not_authentication": True,
        "lean_atom_discharged": False,
        "proves_any_external_atom": False,
    }


class R2StarCampaignTests(unittest.TestCase):
    def test_structural_receipt_accepts_exact_python_chunk(self) -> None:
        report = exact_small_receipt()
        chunk = verify_runner_receipt(report)
        self.assertEqual((chunk.lower, chunk.upper), (1, 501))

    def test_structural_receipt_rejects_changed_transition(self) -> None:
        report = exact_small_receipt()
        report["chunk"]["outgoing_lower"] += 1  # type: ignore[index]
        with self.assertRaisesRegex(R2StarCampaignError, "canonical hash"):
            verify_runner_receipt(report)

    def test_structural_receipt_requires_segmented_factor_digest(self) -> None:
        report = exact_small_receipt()
        report["factor_support_digest_producer"] = "trial_division"
        with self.assertRaisesRegex(R2StarCampaignError, "segmented"):
            verify_runner_receipt(report)

    def test_registered_result_is_exclusive_and_source_complete(self) -> None:
        completed = R2StarCampaignResult(
            endpoint=21_000_000_000,
            completed_upper=21_000_000_000,
            receipts=21_000,
            complete=True,
            runner_sha256="1" * 64,
            final_record_hash="2" * 64,
            minimum_squared_slack=1,
            minimum_slack_index=3,
            exact_fallback_rows=0,
            locally_supervised_execution=False,
            independent_rows_replayed=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "registered-result.txt"
            with mock.patch(
                "tg_verifier.r2star_campaign._verify_campaign_arithmetic_unlocked",
                return_value=completed,
            ):
                checked, artifact = write_registered_result(
                    root,
                    output,
                    arithmetic_replayer=Path("/reviewed/replayer"),
                )
                self.assertEqual(checked, completed)
                self.assertEqual(output.read_bytes(), b"true")
                self.assertEqual(artifact["sha256"], REGISTERED_RESULT_SHA256)
                with self.assertRaisesRegex(R2StarCampaignError, "overwrite"):
                    write_registered_result(
                        root,
                        output,
                        arithmetic_replayer=Path("/reviewed/replayer"),
                    )

    def test_registered_result_rejects_incomplete_prefix(self) -> None:
        incomplete = R2StarCampaignResult(
            endpoint=21_000_000_000,
            completed_upper=1_000_000,
            receipts=1,
            complete=False,
            runner_sha256="1" * 64,
            final_record_hash="2" * 64,
            minimum_squared_slack=1,
            minimum_slack_index=3,
            exact_fallback_rows=0,
            locally_supervised_execution=False,
            independent_rows_replayed=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "registered-result.txt"
            with mock.patch(
                "tg_verifier.r2star_campaign._verify_campaign_arithmetic_unlocked",
                return_value=incomplete,
            ):
                with self.assertRaisesRegex(R2StarCampaignError, "complete literal"):
                    write_registered_result(
                        root,
                        output,
                        arithmetic_replayer=Path("/reviewed/replayer"),
                    )
            self.assertFalse(output.exists())

    def test_production_result_requires_and_records_independent_replay(
        self,
    ) -> None:
        completed = R2StarCampaignResult(
            endpoint=21_000_000_000,
            completed_upper=21_000_000_000,
            receipts=21_000,
            complete=True,
            runner_sha256="1" * 64,
            final_record_hash="2" * 64,
            minimum_squared_slack=1,
            minimum_slack_index=3,
            exact_fallback_rows=0,
            locally_supervised_execution=False,
            independent_rows_replayed=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(
                R2StarCampaignError, "requires the independent full-row"
            ):
                write_registered_result(root, root / "missing.txt")
            output = root / "registered-result.txt"
            with mock.patch(
                "tg_verifier.r2star_campaign._verify_campaign_arithmetic_unlocked",
                return_value=completed,
            ) as replay:
                checked, artifact = write_registered_result(
                    root,
                    output,
                    arithmetic_replayer=Path("/reviewed/replayer"),
                )
            self.assertTrue(checked.independent_rows_replayed)
            self.assertEqual(
                artifact["refinement_scope"],
                "independent_cpu_full_row_arithmetic_replay_v1",
            )
            self.assertIsNone(artifact["arithmetic_replayer_sha256"])
            replay.assert_called_once()

    def test_generic_cli_cannot_emit_registered_true_without_row_replay(
        self,
    ) -> None:
        commands = (
            (
                (
                    "run",
                    "--runner",
                    "/does/not/matter",
                    "--output-dir",
                    "/does/not/matter",
                ),
                "requires both --arithmetic-replayer",
            ),
            (("verify", "/does/not/matter"), "unrecognized arguments"),
        )
        for command, expected_error in commands:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/tg_r2star_campaign.py"),
                    *command,
                    "--registered-result-output",
                    "/tmp/forbidden-r2star-result",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn(expected_error, completed.stderr)

    def test_verify_arithmetic_result_replays_exactly_once(self) -> None:
        completed = R2StarCampaignResult(
            endpoint=21_000_000_000,
            completed_upper=21_000_000_000,
            receipts=21_000,
            complete=True,
            runner_sha256="1" * 64,
            final_record_hash="2" * 64,
            minimum_squared_slack=1,
            minimum_slack_index=3,
            exact_fallback_rows=0,
            locally_supervised_execution=False,
            independent_rows_replayed=True,
        )
        artifact = {
            "path": "/retained/result",
            "sha256": REGISTERED_RESULT_SHA256,
        }
        with mock.patch.object(
            campaign_cli,
            "write_registered_result",
            return_value=(completed, artifact),
        ) as write, mock.patch.object(
            campaign_cli, "verify_campaign_arithmetic"
        ) as replay, mock.patch.object(
            campaign_cli, "require_azure_measured_worker_for_workload"
        ), contextlib.redirect_stdout(io.StringIO()):
            status = campaign_cli.main(
                [
                    "verify-arithmetic",
                    "/retained/campaign",
                    "--arithmetic-replayer",
                    "/reviewed/replayer",
                    "--registered-result-output",
                    "/retained/result",
                ]
            )
        self.assertEqual(status, 0)
        write.assert_called_once()
        replay.assert_not_called()

    def test_verify_arithmetic_cli_defaults_segmented_and_zero_is_serial(
        self,
    ) -> None:
        completed = R2StarCampaignResult(
            endpoint=21_000_000_000,
            completed_upper=21_000_000_000,
            receipts=21_000,
            complete=True,
            runner_sha256="1" * 64,
            final_record_hash="2" * 64,
            minimum_squared_slack=1,
            minimum_slack_index=3,
            exact_fallback_rows=0,
            locally_supervised_execution=False,
            independent_rows_replayed=True,
        )
        cases = (
            ((), DEFAULT_ARITHMETIC_REPLAY_SEGMENT_ROWS),
            (("--replay-segment-rows", "0"), None),
        )
        for extra_arguments, expected_segment_rows in cases:
            with mock.patch.object(
                campaign_cli,
                "verify_campaign_arithmetic",
                return_value=completed,
            ) as replay, mock.patch.object(
                campaign_cli, "require_azure_measured_worker_for_workload"
            ), contextlib.redirect_stdout(io.StringIO()):
                status = campaign_cli.main(
                    [
                        "verify-arithmetic",
                        "/retained/campaign",
                        "--arithmetic-replayer",
                        "/reviewed/replayer",
                        *extra_arguments,
                    ]
                )
            self.assertEqual(status, 0)
            replay.assert_called_once()
            self.assertEqual(
                replay.call_args.kwargs["replay_segment_rows"],
                expected_segment_rows,
            )

    def test_registered_result_is_wired_to_the_exact_h100_invocation(self) -> None:
        registry = _validate_semantic_bindings(
            json.loads(
                (
                    ROOT
                    / "specifications/TERNARY_GOLDBACH_AZURE_SEMANTIC_BINDINGS.json"
                ).read_text(encoding="utf-8")
            )
        )
        row = next(
            item
            for item in registry["bindings"]
            if item["campaign_id"] == "ramare-zuniga-lemma-6-2"
        )
        self.assertFalse(row["enabled"])
        self.assertEqual(
            PENDING_TG_REALIZATIONS[row["realization_id"]],
            {
                "campaign_id": "ramare-zuniga-lemma-6-2",
                "lean_theorem": row["lean_theorem"],
                "registered_invocation": "ramareZunigaLemma62ProductionV1",
            },
        )
        terminal = SOURCE_TG_TERMINAL_RESULTS[row["realization_id"]]
        command = WORKLOADS_BY_ID["ramare-zuniga-lemma-6-2"].command
        index = command.index(terminal.argument)
        self.assertEqual(command[index + 1], terminal.artifact_template)


if __name__ == "__main__":
    unittest.main()
