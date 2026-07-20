#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for supervised complete external replay execution."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tg_verifier.evidence import CDEM_REQUIRED_FIELDS, CDEM_U_TARGET, CDEM_V_TARGET
from tg_verifier.execution import (
    ExecutionReplayError,
    build_and_run_cdem_abel,
    run_cdem_abel,
)


def fake_producer(fields: dict[str, int]) -> str:
    transcript = "".join(f"{key}={value}\n" for key, value in fields.items())
    return "#!/usr/bin/env python3\nimport sys\nsys.stdout.write(" + repr(transcript) + ")\n"


class CompleteExecutionReplayTests(unittest.TestCase):
    def test_supervisor_hashes_and_repeats_exact_proof_fields(self) -> None:
        fields = dict(CDEM_REQUIRED_FIELDS)
        fields["U_INC_UPPER_NUM"] = CDEM_U_TARGET
        fields["V_INC_UPPER_NUM"] = CDEM_V_TARGET
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "producer.py"
            executable.write_text(fake_producer(fields), encoding="utf-8")
            executable.chmod(0o755)
            receipt, transcript = run_cdem_abel(
                executable,
                source=executable,
                block_size=17,
                threads=2,
                max_seconds=10,
                repeats=2,
            )
        self.assertTrue(receipt["accepted"])
        self.assertFalse(receipt["complete_range_execution_verified"])
        self.assertEqual(
            receipt["verification_class"], "producer_output_contract_only"
        )
        self.assertTrue(receipt["cross_run_mathematical_fields_identical"])
        self.assertFalse(receipt["lean_atom_discharged"])
        self.assertEqual(len(receipt["transcript_sha256"]), 2)
        self.assertIn("K=199330\n", transcript)

    def test_supervisor_fails_closed_on_wrong_terminal_field(self) -> None:
        fields = dict(CDEM_REQUIRED_FIELDS)
        fields["FINAL_G"] += 1
        fields["U_INC_UPPER_NUM"] = CDEM_U_TARGET
        fields["V_INC_UPPER_NUM"] = CDEM_V_TARGET
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "producer.py"
            executable.write_text(fake_producer(fields), encoding="utf-8")
            executable.chmod(0o755)
            with self.assertRaisesRegex(ExecutionReplayError, "FINAL_G"):
                run_cdem_abel(executable, max_seconds=10)

    def test_reviewed_source_runner_rejects_unpinned_printer_source(self) -> None:
        fields = dict(CDEM_REQUIRED_FIELDS)
        fields["U_INC_UPPER_NUM"] = CDEM_U_TARGET
        fields["V_INC_UPPER_NUM"] = CDEM_V_TARGET
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "fake.cpp"
            source.write_text(fake_producer(fields), encoding="utf-8")
            with self.assertRaisesRegex(ExecutionReplayError, "reviewed SHA-256"):
                build_and_run_cdem_abel(source, max_seconds=10)


if __name__ == "__main__":
    unittest.main()
