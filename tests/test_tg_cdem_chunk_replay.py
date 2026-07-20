#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Known-answer and fail-closed tests for the independent CDEM chunk replay."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tg_verifier.cdem_chunk_replay import (
    CDEM_CHUNK_REPLAYER_DEFAULT_SOURCE,
    CdemChunkRecord,
    CdemChunkReplayError,
    build_and_replay_cdem_chunk_records,
    verify_cdem_chunk_output,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = CDEM_CHUNK_REPLAYER_DEFAULT_SOURCE
FIRST = CdemChunkRecord(1, 7, 0, 1, 0, 0, 0)
SECOND = CdemChunkRecord(
    8,
    14,
    1,
    2,
    96_403_596_403_596_406,
    846_122_684_602_802_570,
    3,
)


FIRST_OUTPUT = """SCHEMA=CDEM_ABEL_CHUNK_REPLAY_V1
K=10
LOW=1
HIGH=7
BEFORE=0
DELTA_SUM=1
AFTER=1
U_INC_UPPER_NUM=0
V_INC_UPPER_NUM=0
TOTAL_VARIATION=0
WEIGHT_SCALE=1000000000000000000
"""


class CdemChunkSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compiler = shutil.which("g++")
        if compiler is None:
            raise unittest.SkipTest("g++ is required for the CDEM chunk test")
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.executable = Path(cls.temporary_directory.name) / "chunk-replay"
        compiled = subprocess.run(
            [
                compiler,
                "-O2",
                "-std=c++20",
                "-Wall",
                "-Wextra",
                "-Werror",
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
                "failed to compile independent CDEM chunk source:\n"
                + compiled.stdout
                + compiled.stderr
            )

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "temporary_directory"):
            cls.temporary_directory.cleanup()

    def run_chunk(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.executable), *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    def test_first_chunk_known_answer_including_gseq_zero_override(self) -> None:
        completed = self.run_chunk("10", "1", "7", "0")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        self.assertEqual(completed.stdout, FIRST_OUTPUT)
        self.assertEqual(
            len(verify_cdem_chunk_output(completed.stdout, K=10, expected=FIRST)),
            64,
        )

    def test_noninitial_chunk_known_answer_uses_incoming_prefix(self) -> None:
        completed = self.run_chunk("10", "8", "14", "1")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        verify_cdem_chunk_output(completed.stdout, K=10, expected=SECOND)

    def test_invalid_or_noncanonical_arguments_fail_before_output(self) -> None:
        invalid = (
            (),
            ("0", "1", "7", "0"),
            ("10", "0", "7", "0"),
            ("10", "8", "7", "0"),
            ("10", "01", "7", "0"),
            ("10", "1", "7", "-0"),
            (str(1 << 31), "1", "7", "0"),
            ("10", "1", "7", str(1 << 63)),
        )
        for arguments in invalid:
            with self.subTest(arguments=arguments):
                completed = self.run_chunk(*arguments)
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(completed.stdout, "")
                self.assertNotEqual(completed.stderr, "")

    def test_source_states_provenance_and_external_trust_boundary(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertTrue(
            source.startswith(
                "// Copyright (c) 2026 Gershon Bialer. All rights reserved.\n"
                "// SPDX-License-Identifier: MIT"
            )
        )
        self.assertIn("Independent, bounded-memory replayer", source)
        self.assertIn("Lean-kernel proof", source)
        self.assertNotIn("#include <omp.h>", source)
        self.assertNotIn("std::sqrt", source)


class CdemChunkSupervisorTests(unittest.TestCase):
    def test_supervisor_pins_compiles_and_replays_two_known_rows(self) -> None:
        receipt = build_and_replay_cdem_chunk_records(
            (FIRST, SECOND), K=10, workers=2, chunk_max_seconds=30
        )
        self.assertTrue(receipt["accepted"])
        self.assertTrue(receipt["reviewed_source_hash_matched"])
        self.assertTrue(receipt["compiled_source_was_exact_captured_bytes"])
        self.assertTrue(receipt["fixed_known_answer_preflight"])
        self.assertTrue(receipt["all_supplied_chunks_recomputed"])
        self.assertEqual(receipt["replayed_chunk_count"], 2)
        self.assertEqual(receipt["actual_workers"], 2)
        self.assertFalse(receipt["complete_range_execution_verified"])
        self.assertFalse(receipt["lean_atom_discharged"])

    def test_output_tampering_is_rejected(self) -> None:
        tampered = FIRST_OUTPUT.replace("AFTER=1\n", "AFTER=2\n")
        with self.assertRaisesRegex(CdemChunkReplayError, "AFTER differs"):
            verify_cdem_chunk_output(tampered, K=10, expected=FIRST)
        extra = FIRST_OUTPUT + "UNREVIEWED=1\n"
        with self.assertRaisesRegex(CdemChunkReplayError, "output keys differ"):
            verify_cdem_chunk_output(extra, K=10, expected=FIRST)

    def test_expected_record_tampering_is_rejected_by_recomputation(self) -> None:
        tampered = CdemChunkRecord(1, 7, 0, 2, 0, 0, 0)
        with self.assertRaisesRegex(CdemChunkReplayError, "DELTA_SUM differs|AFTER differs"):
            build_and_replay_cdem_chunk_records(
                (tampered,), K=10, workers=1, chunk_max_seconds=30
            )

    def test_unpinned_source_is_rejected_before_compilation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / "chunk.cpp"
            altered.write_bytes(SOURCE.read_bytes() + b"\n// altered\n")
            with self.assertRaisesRegex(CdemChunkReplayError, "reviewed SHA-256"):
                build_and_replay_cdem_chunk_records(
                    (FIRST,), K=10, source=altered, workers=1
                )


if __name__ == "__main__":
    unittest.main()
