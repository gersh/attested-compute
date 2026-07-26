# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tg_verifier.evidence import (
    CDEM_REGISTERED_RESULT,
    CDEM_REGISTERED_RESULT_SHA256,
    CDEM_REQUIRED_FIELDS,
    CDEM_U_TARGET,
    CDEM_V_TARGET,
    EvidenceError,
)
from tools import tg_verify
from tools.tg_verify import _write_cdem_registered_result


def accepted_transcript() -> str:
    fields = dict(CDEM_REQUIRED_FIELDS)
    fields["U_INC_UPPER_NUM"] = CDEM_U_TARGET
    fields["V_INC_UPPER_NUM"] = CDEM_V_TARGET
    return "".join(f"{name}={value}\n" for name, value in fields.items())


class CdemRegisteredResultArtifactTests(unittest.TestCase):
    def test_checked_transcript_writes_exact_newline_free_registry_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result" / "cdem.txt"
            record = _write_cdem_registered_result(accepted_transcript(), output)

            self.assertEqual(output.read_bytes(), CDEM_REGISTERED_RESULT.encode("ascii"))
            self.assertEqual(record["sha256"], CDEM_REGISTERED_RESULT_SHA256)
            self.assertEqual(
                record["format"], "canonical_decimal_natural_no_newline_v1"
            )
            self.assertEqual(record["bytes"], len(CDEM_REGISTERED_RESULT))

    def test_tampered_transcript_cannot_create_a_result_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.txt"
            transcript = accepted_transcript().replace(
                f"U_INC_UPPER_NUM={CDEM_U_TARGET}",
                f"U_INC_UPPER_NUM={CDEM_U_TARGET - 1}",
            )
            with self.assertRaisesRegex(EvidenceError, "signed Abel output"):
                _write_cdem_registered_result(transcript, output)
            self.assertFalse(output.exists())

    def test_existing_result_artifact_is_not_reused_or_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.txt"
            output.write_bytes(b"preexisting")
            with self.assertRaisesRegex(EvidenceError, "refusing to overwrite"):
                _write_cdem_registered_result(accepted_transcript(), output)
            self.assertEqual(output.read_bytes(), b"preexisting")

    def test_full_command_does_not_write_result_before_independent_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            arguments = tg_verify.build_parser().parse_args(
                [
                    "run-cdem-abel-full",
                    str(root / "producer.cpp"),
                    "--replay-source",
                    str(root / "replay.cpp"),
                    "--transcript-output",
                    str(root / "transcript.txt"),
                    "--artifact-output",
                    str(root / "artifact.bin"),
                    "--registered-result-output",
                    str(root / "result.txt"),
                ]
            )
            with mock.patch.object(
                tg_verify,
                "build_and_run_cdem_abel",
                return_value=({"accepted": True}, accepted_transcript()),
            ), mock.patch.object(
                tg_verify,
                "replay_cdem_production_transcript",
                side_effect=RuntimeError("independent replay failed"),
            ), mock.patch.object(
                tg_verify,
                "require_azure_measured_worker_for_workload",
                return_value="azure_sevsnp_cpu",
            ):
                with self.assertRaisesRegex(RuntimeError, "independent replay failed"):
                    tg_verify.command_run_cdem_full(arguments)
            self.assertFalse((root / "artifact.bin").exists())
            self.assertFalse((root / "result.txt").exists())

    def test_full_command_finalizes_artifact_and_result_only_after_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact.bin"
            result = root / "result.txt"
            arguments = tg_verify.build_parser().parse_args(
                [
                    "run-cdem-abel-full",
                    str(root / "producer.cpp"),
                    "--replay-source",
                    str(root / "replay.cpp"),
                    "--transcript-output",
                    str(root / "transcript.txt"),
                    "--artifact-output",
                    str(artifact),
                    "--registered-result-output",
                    str(result),
                ]
            )
            events: list[str] = []

            def replay(*_args, **_kwargs):
                events.append("replay")
                return {"accepted": True}

            def write_artifact(_transcript, output):
                self.assertEqual(events, ["replay"])
                events.append("artifact")
                output.write_bytes(b"closed-artifact")
                return {"path": str(output), "sha256": "00" * 32, "size_bytes": 15}

            def write_result(_transcript, output):
                self.assertEqual(events, ["replay", "artifact"])
                events.append("result")
                output.write_bytes(CDEM_REGISTERED_RESULT.encode("ascii"))
                return {
                    "path": str(output),
                    "sha256": CDEM_REGISTERED_RESULT_SHA256,
                    "bytes": len(CDEM_REGISTERED_RESULT),
                    "format": "canonical_decimal_natural_no_newline_v1",
                }

            with mock.patch.object(
                tg_verify,
                "build_and_run_cdem_abel",
                return_value=({"accepted": True}, accepted_transcript()),
            ), mock.patch.object(
                tg_verify,
                "replay_cdem_production_transcript",
                side_effect=replay,
            ), mock.patch.object(
                tg_verify,
                "write_artifact_exclusive",
                side_effect=write_artifact,
            ), mock.patch.object(
                tg_verify,
                "_write_cdem_registered_result",
                side_effect=write_result,
            ), mock.patch.object(
                tg_verify,
                "require_azure_measured_worker_for_workload",
                return_value="azure_sevsnp_cpu",
            ), mock.patch.object(tg_verify, "_emit"):
                tg_verify.command_run_cdem_full(arguments)
            self.assertEqual(events, ["replay", "artifact", "result"])
            self.assertEqual(artifact.read_bytes(), b"closed-artifact")
            self.assertEqual(
                result.read_bytes(), CDEM_REGISTERED_RESULT.encode("ascii")
            )


if __name__ == "__main__":
    unittest.main()
