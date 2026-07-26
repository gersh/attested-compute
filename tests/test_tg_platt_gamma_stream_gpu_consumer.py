#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Mutation and FLINT KAT checks for the bounded CUDA Gamma consumer.

Set ``TG_PLATT_GAMMA_GPU_CONSUMER`` and
``TG_PLATT_GAMMA_TAYLOR_PRODUCER`` to exercise the optional CUDA test.  The
test never treats a numerical comparison as a proof of the analytic
FLINT-to-Mathlib realization; it checks the finite serialization and CUDA
enclosure dataflow only.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
HEADER_BYTES = 320
CHUNK_HEADER_BYTES = 72


def executable(environment: str, candidates: list[Path]) -> Path | None:
    configured = os.environ.get(environment)
    if configured:
        path = Path(configured)
        return path if path.is_file() else None
    return next((path for path in candidates if path.is_file()), None)


def one_json(completed: subprocess.CompletedProcess[str], *, stderr: bool = False) -> dict[str, object]:
    text = completed.stderr if stderr else completed.stdout
    rows = [line for line in text.splitlines() if line.strip()]
    if len(rows) != 1:
        raise AssertionError(f"expected one JSON row, received {len(rows)}: {text}")
    return json.loads(rows[0])


class PlattGammaStreamGpuConsumerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.consumer = executable(
            "TG_PLATT_GAMMA_GPU_CONSUMER",
            [Path("/tmp/tg-gamma-gpu-build/h100-tg-platt-gamma-stream-consumer")],
        )
        cls.producer = executable(
            "TG_PLATT_GAMMA_TAYLOR_PRODUCER",
            [
                REPOSITORY
                / "build/platt-windowed-semantic-kat/sparkinterval-tg-platt-gamma-taylor",
                REPOSITORY
                / "build/tg-production-kat/sparkinterval-tg-platt-gamma-taylor",
            ],
        )
        if cls.consumer is None or cls.producer is None:
            raise unittest.SkipTest(
                "CUDA Gamma consumer and FLINT Gamma producer are required"
            )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.stream = Path(self.temporary.name) / "gamma-stream.bin"
        completed = subprocess.run(
            [
                str(self.producer),
                "--stream-first-block",
                "0",
                "--stream-blocks",
                "5",
                "--stream-chunk-records",
                "2",
                "--stream-audit-stride",
                "1",
                "--stream-output",
                str(self.stream),
            ],
            cwd=REPOSITORY,
            check=True,
            capture_output=True,
            text=True,
        )
        self.producer_report = one_json(completed)

    def invoke(
        self,
        path: Path | None = None,
        first_block: int = 0,
        block_count: int = 5,
        extra: tuple[str, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(self.consumer),
                str(path or self.stream),
                str(first_block),
                str(block_count),
                "--microbatch-records=2",
                "--max-chunk-records=2",
                *extra,
            ],
            cwd=REPOSITORY,
            check=False,
            capture_output=True,
            text=True,
        )

    def mutated(self, name: str, offset: int) -> Path:
        data = bytearray(self.stream.read_bytes())
        data[offset] ^= 0x40
        path = Path(self.temporary.name) / name
        path.write_bytes(data)
        return path

    def test_valid_stream_is_complete_deterministic_and_fail_honest(self) -> None:
        first = self.invoke(
            extra=(
                f"--expected-stream-sha256={self.producer_report['stream_sha256']}",
            )
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        first_report = one_json(first)
        second = self.invoke()
        self.assertEqual(second.returncode, 0, second.stderr)
        second_report = one_json(second)
        self.assertTrue(first_report["accepted"])
        self.assertEqual(first_report["records_consumed"], 5)
        self.assertEqual(first_report["invalid_intervals"], 0)
        self.assertEqual(first_report["per_window_host_launches"], 0)
        self.assertTrue(first_report["all_chunks_authenticated_before_gpu_use"])
        self.assertTrue(
            first_report["footer_and_global_digest_checked_before_acceptance"]
        )
        self.assertFalse(first_report["flint_to_mathlib_realization_proved"])
        self.assertFalse(first_report["pt21_source_claim_discharged"])
        self.assertFalse(first_report["trusted_run_receipt_emitted"])
        self.assertEqual(
            first_report["row_audit_summary_sha256"],
            second_report["row_audit_summary_sha256"],
        )

    def test_first_record_gpu_intervals_enclose_fresh_flint_probes(self) -> None:
        gpu_completed = self.invoke()
        self.assertEqual(gpu_completed.returncode, 0, gpu_completed.stderr)
        gpu = one_json(gpu_completed)
        flint_completed = subprocess.run(
            [
                str(self.producer),
                "--height",
                "10000000504",
                "--precision",
                "256",
                "--degree",
                "6",
                "--repeat",
                "1",
                "--audit-samples",
                "17",
            ],
            cwd=REPOSITORY,
            check=True,
            capture_output=True,
            text=True,
        )
        flint = one_json(flint_completed)
        gpu_probes = gpu["first_record_probes"]
        flint_probes = flint["source_value_probes"]
        self.assertEqual(len(gpu_probes), len(flint_probes))
        for gpu_probe, flint_probe in zip(gpu_probes, flint_probes, strict=True):
            self.assertEqual(gpu_probe["index"], flint_probe["index"])
            for component in ("re", "im"):
                gpu_lo = float.fromhex(gpu_probe[f"{component}_lo_hex"])
                gpu_hi = float.fromhex(gpu_probe[f"{component}_hi_hex"])
                flint_lo = float.fromhex(flint_probe[component]["lo_hex"])
                flint_hi = float.fromhex(flint_probe[component]["hi_hex"])
                self.assertLessEqual(gpu_lo, flint_lo)
                self.assertLessEqual(flint_lo, flint_hi)
                self.assertLessEqual(flint_hi, gpu_hi)
        self.assertEqual(gpu["invalid_disks"], 0)
        disk_probes = gpu["first_record_disk_probes"]
        self.assertEqual(len(disk_probes), len(gpu_probes))
        for interval, disk in zip(gpu_probes, disk_probes, strict=True):
            self.assertEqual(interval["index"], disk["index"])
            center_re = float.fromhex(disk["re_hi_hex"]) + float.fromhex(
                disk["re_lo_hex"]
            )
            center_im = float.fromhex(disk["im_hi_hex"]) + float.fromhex(
                disk["im_lo_hex"]
            )
            radius = float.fromhex(disk["radius_hex"])
            for re in (
                float.fromhex(interval["re_lo_hex"]),
                float.fromhex(interval["re_hi_hex"]),
            ):
                for im in (
                    float.fromhex(interval["im_lo_hex"]),
                    float.fromhex(interval["im_hi_hex"]),
                ):
                    self.assertLessEqual(
                        math.hypot(re - center_re, im - center_im),
                        math.nextafter(radius, math.inf),
                    )

    def test_single_record_chunks_are_coalesced_before_cuda_launch(self) -> None:
        stream = Path(self.temporary.name) / "one-record-chunks.bin"
        subprocess.run(
            [
                str(self.producer),
                "--stream-first-block",
                "0",
                "--stream-blocks",
                "5",
                "--stream-chunk-records",
                "1",
                "--stream-audit-stride",
                "0",
                "--stream-output",
                str(stream),
            ],
            cwd=REPOSITORY,
            check=True,
            capture_output=True,
            text=True,
        )
        completed = self.invoke(stream)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = one_json(completed)
        self.assertEqual(report["chunk_count"], 5)
        self.assertEqual(report["microbatch_count"], 3)
        self.assertEqual(report["cuda_graph_launches"], 2)
        self.assertEqual(report["tail_batched_launches"], 1)
        self.assertEqual(report["final_tail_records"], 1)
        self.assertEqual(report["per_window_host_launches"], 0)

    def assert_rejected(self, completed: subprocess.CompletedProcess[str], pattern: str) -> None:
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        report = one_json(completed, stderr=True)
        self.assertFalse(report["accepted"])
        self.assertIn(pattern, report["error"])
        self.assertFalse(report["flint_to_mathlib_realization_proved"])
        self.assertFalse(report["pt21_source_claim_discharged"])
        self.assertFalse(report["trusted_run_receipt_emitted"])

    def test_payload_mutation_is_rejected_before_use(self) -> None:
        path = self.mutated(
            "payload-mutated.bin", HEADER_BYTES + CHUNK_HEADER_BYTES + 13
        )
        self.assert_rejected(self.invoke(path), "payload digest differs")

    def test_header_and_exact_shard_range_mutations_are_rejected(self) -> None:
        header_path = self.mutated("header-mutated.bin", 0)
        self.assert_rejected(self.invoke(header_path), "fixed header differs")
        self.assert_rejected(self.invoke(first_block=1), "first block differs")
        self.assert_rejected(self.invoke(block_count=4), "block count differs")

    def test_footer_mutation_and_truncated_prefix_are_rejected(self) -> None:
        footer_path = self.mutated("footer-mutated.bin", -1)
        self.assert_rejected(self.invoke(footer_path), "footer differs")
        prefix = Path(self.temporary.name) / "prefix.bin"
        prefix.write_bytes(self.stream.read_bytes()[:-128])
        self.assert_rejected(self.invoke(prefix), "footer is truncated")


if __name__ == "__main__":
    unittest.main()
