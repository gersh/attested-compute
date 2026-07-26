#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Authenticated DD Gamma stream, CUDA enclosure, and regression tests.

The optional fused test is intentionally explicit because constructing the
768000-term workspace takes roughly forty seconds on the local GB10.  None of
these finite KATs asserts the missing FLINT-to-Mathlib analytic realization.
"""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import struct
import tempfile
import unittest

from tg_verifier.platt_pt21_event_record import validate_stream


ROOT = Path(__file__).resolve().parents[1]
HEADER_BYTES = 336
CHUNK_HEADER_BYTES = 72
FULL_BLOCK_COUNT = 2_966_443_783
TERMINAL_BLOCK = FULL_BLOCK_COUNT - 1


def executable(environment: str, candidates: list[Path]) -> Path | None:
    configured = os.environ.get(environment)
    if configured:
        path = Path(configured)
        return path if path.is_file() else None
    return next((path for path in candidates if path.is_file()), None)


def one_json(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    rows = [row for row in completed.stdout.splitlines() if row.strip()]
    if len(rows) != 1:
        raise AssertionError(
            f"expected one JSON row, received {len(rows)}: {completed.stdout}"
        )
    return json.loads(rows[0])


class PlattGammaV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.producer = executable(
            "TG_PLATT_GAMMA_TAYLOR_V2_PRODUCER",
            [ROOT / "build/tg-production-kat/sparkinterval-tg-platt-gamma-taylor-v2"],
        )
        cls.consumer = executable(
            "TG_PLATT_GAMMA_V2_GPU_CONSUMER",
            [ROOT / "build/platt-fused/sparkinterval-tg-platt-gamma-v2-gpu-consumer"],
        )
        cls.direct_producer = executable(
            "TG_PLATT_GAMMA_TAYLOR_PRODUCER",
            [ROOT / "build/tg-production-kat/sparkinterval-tg-platt-gamma-taylor"],
        )
        if cls.producer is None or cls.consumer is None:
            raise unittest.SkipTest("V2 FLINT producer and CUDA consumer are required")

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.stream = Path(self.temporary.name) / "gamma-v2.bin"
        completed = subprocess.run(
            [
                str(self.producer),
                "--stream-first-block",
                "0",
                "--stream-blocks",
                "2",
                "--stream-chunk-records",
                "2",
                "--stream-audit-stride",
                "0",
                "--audit-samples",
                "1",
                "--stream-output",
                str(self.stream),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.producer_report = one_json(completed)

    def invoke(
        self,
        path: Path | None = None,
        *,
        first_block: int = 0,
        block_count: int = 2,
        extra: tuple[str, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        if not any(
            argument.startswith("--expected-stream-sha256=")
            for argument in extra
        ):
            extra = (
                f"--expected-stream-sha256={self.producer_report['stream_sha256']}",
                *extra,
            )
        return subprocess.run(
            [
                str(self.consumer),
                str(path or self.stream),
                str(first_block),
                str(block_count),
                "--max-chunk-records=2",
                *extra,
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def mutated(self, name: str, offset: int) -> Path:
        raw = bytearray(self.stream.read_bytes())
        raw[offset] ^= 0x40
        path = Path(self.temporary.name) / name
        path.write_bytes(raw)
        return path

    def test_valid_stream_is_complete_bounded_and_fail_honest(self) -> None:
        completed = self.invoke()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = one_json(completed)
        self.assertTrue(report["accepted"])
        self.assertEqual(report["records"], 2)
        self.assertEqual(report["gamma_values"], 2 * 32_768)
        self.assertEqual(report["invalid_disks"], 0)
        self.assertTrue(report["bounded_authenticated_input"])
        self.assertTrue(report["stream_sha256_pinned"])
        self.assertFalse(report["flint_to_mathlib_proved"])
        self.assertFalse(report["pt21_atom_discharged"])
        self.assertEqual(
            report["stream_sha256"], self.producer_report["stream_sha256"]
        )

        unpinned = subprocess.run(
            [str(self.consumer), str(self.stream), "0", "2"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(unpinned.returncode, 0)
        self.assertEqual(unpinned.stdout, "")
        self.assertIn("requires --expected-stream-sha256", unpinned.stderr)

    def test_payload_footer_and_exact_range_mutations_fail_closed(self) -> None:
        payload = self.mutated(
            "payload-mutated.bin", HEADER_BYTES + CHUNK_HEADER_BYTES + 17
        )
        completed = self.invoke(payload)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("payload digest differs", completed.stderr)

        footer = self.mutated("footer-mutated.bin", len(self.stream.read_bytes()) - 1)
        rejected_export = Path(self.temporary.name) / "must-not-exist.dd"
        completed = self.invoke(
            footer, extra=(f"--export-first-row={rejected_export}",)
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("footer differs", completed.stderr)
        self.assertFalse(rejected_export.exists())

        completed = self.invoke(first_block=1)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("first block differs", completed.stderr)

        completed = self.invoke(extra=(f"--expected-stream-sha256={'00' * 32}",))
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("stream digest differs", completed.stderr)

    def test_invalid_dd_record_is_rejected_after_fresh_chunk_hash(self) -> None:
        raw = bytearray(self.stream.read_bytes())
        payload_offset = HEADER_BYTES + CHUNK_HEADER_BYTES
        struct.pack_into("<d", raw, payload_offset, float("nan"))
        payload_bytes = 2 * 312
        digest = hashlib.sha256(
            raw[payload_offset : payload_offset + payload_bytes]
        ).digest()
        chunk_hash_offset = HEADER_BYTES + 40
        raw[chunk_hash_offset : chunk_hash_offset + 32] = digest
        path = Path(self.temporary.name) / "invalid-record-fresh-hash.bin"
        path.write_bytes(raw)
        completed = self.invoke(path)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("invalid coefficient disk", completed.stderr)

    def direct_row(self, block: int, path: Path) -> None:
        if self.direct_producer is None:
            self.skipTest("direct FLINT DD-row producer is required")
        height = 10_000_000_000 + 504 + block * 1008
        subprocess.run(
            [
                str(self.direct_producer),
                "--height",
                str(height),
                "--precision",
                "256",
                "--degree",
                "6",
                "--repeat",
                "1",
                "--audit-samples",
                "9",
                "--export-dd-gamma-row",
                str(path),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    def one_block_stream(self, block: int, path: Path) -> str:
        completed = subprocess.run(
            [
                str(self.producer),
                "--stream-first-block",
                str(block),
                "--stream-blocks",
                "1",
                "--stream-chunk-records",
                "1",
                "--stream-audit-stride",
                "0",
                "--audit-samples",
                "9",
                "--stream-output",
                str(path),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return str(one_json(completed)["stream_sha256"])

    def test_full_first_and_terminal_rows_enclose_direct_flint_v2(self) -> None:
        for label, block in (("first", 0), ("terminal", TERMINAL_BLOCK)):
            stream = Path(self.temporary.name) / f"{label}.bin"
            direct = Path(self.temporary.name) / f"{label}.dd"
            stream_sha256 = self.one_block_stream(block, stream)
            self.direct_row(block, direct)
            completed = self.invoke(
                stream,
                first_block=block,
                block_count=1,
                extra=(
                    f"--direct-first-row={direct}",
                    f"--expected-stream-sha256={stream_sha256}",
                ),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = one_json(completed)
            self.assertTrue(report["first_full_row_compared"])
            self.assertEqual(report["first_containment_failures"], 0)
            self.assertLess(report["first_maximum_required_to_outer_ratio"], 1)

    def test_truncated_direct_row_is_rejected_before_comparison(self) -> None:
        stream = Path(self.temporary.name) / "direct-truncation.bin"
        direct = Path(self.temporary.name) / "direct-truncation.dd"
        stream_sha256 = self.one_block_stream(0, stream)
        self.direct_row(0, direct)
        direct.write_bytes(direct.read_bytes()[:-1])
        completed = self.invoke(
            stream,
            block_count=1,
            extra=(
                f"--direct-first-row={direct}",
                f"--expected-stream-sha256={stream_sha256}",
            ),
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("payload is truncated", completed.stderr)

    def test_optional_real_fused_endpoint_regression(self) -> None:
        fused = executable("TG_PLATT_FUSED_SOURCE_V2", [])
        if fused is None:
            self.skipTest("set TG_PLATT_FUSED_SOURCE_V2 for the slow fused KAT")
        event_stream = Path(self.temporary.name) / "events.bin"
        completed = subprocess.run(
            [
                str(fused),
                str(self.stream),
                "0",
                "2",
                "--max-chunk-records=2",
                f"--expected-stream-sha256={self.producer_report['stream_sha256']}",
                f"--event-stream-output={event_stream}",
                f"--producer-sha256={'aa' * 32}",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = one_json(completed)
        profile = report["build_profile"]
        self.assertIsInstance(profile, dict)
        self.assertEqual(
            profile["release_performance_build"],
            profile["ndebug_defined"]
            and profile["cmake_build_config"] == "Release",
        )
        self.assertEqual(report["ambiguous_required_disks"], 0)
        self.assertEqual(report["invalid_required_disks"], 0)
        self.assertTrue(report["three_stream_event_scan_complete"])
        self.assertTrue(report["compact_event_records_emitted"])
        event_report = validate_stream(
            event_stream,
            expected_gamma_stream_sha256=str(
                self.producer_report["stream_sha256"]
            ),
            expected_producer_sha256="aa" * 32,
        )
        self.assertEqual(event_report["block_count"], 2)
        self.assertEqual(
            event_report["total_direct_events"],
            report["total_direct_events"],
        )
        self.assertEqual(
            event_report["total_stationary_candidates"],
            report["total_stationary_candidates"],
        )
        self.assertFalse(event_report["source_claim_ready"])
        self.assertFalse(report["flint_to_mathlib_proved"])
        self.assertFalse(report["pt21_atom_discharged"])


if __name__ == "__main__":
    unittest.main()
