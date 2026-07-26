# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tg_verifier.platt_gamma_taylor_stream import CHUNK_HEADER, FOOTER, HEADER


PRODUCER_ENV = "SPARKINTERVAL_TG_PLATT_GAMMA_TAYLOR_RUNNER"
CONSUMER_ENV = "SPARKINTERVAL_TG_PLATT_GAMMA_STREAM_CONSUMER"
EXPECTED_STREAM_SHA256 = (
    "f55539cf8f83d8f9358aeb12e79e06f2e8e442b8ced9de4e29230cbf67405c15"
)


def _runner(variable: str, label: str) -> Path:
    value = os.environ.get(variable)
    if not value:
        raise unittest.SkipTest(f"set {variable} to run the {label} KAT")
    path = Path(value)
    if not path.is_file():
        raise unittest.SkipTest(f"{label} runner is missing: {path}")
    return path


def _produce(path: Path) -> dict[str, object]:
    completed = subprocess.run(
        [
            str(_runner(PRODUCER_ENV, "Gamma stream producer")),
            "--stream-first-block",
            "0",
            "--stream-blocks",
            "8",
            "--stream-chunk-records",
            "3",
            "--stream-audit-stride",
            "4",
            "--audit-samples",
            "9",
            "--stream-output",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _consume(path: Path, first_block: int = 0, block_count: int = 8):
    return subprocess.run(
        [
            str(_runner(CONSUMER_ENV, "Gamma stream consumer")),
            str(path),
            str(first_block),
            str(block_count),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


class PlattGammaStreamConsumerTest(unittest.TestCase):
    def test_cpp_consumer_authenticates_complete_stream(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stream = Path(temporary) / "gamma-stream.bin"
            produced = _produce(stream)
            completed = _consume(stream)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertTrue(result["accepted"])
            self.assertEqual(result["records_consumed"], 8)
            self.assertEqual(result["chunk_count"], 3)
            self.assertEqual(result["maximum_chunk_records"], 3)
            self.assertEqual(result["stream_sha256"], EXPECTED_STREAM_SHA256)
            self.assertEqual(result["stream_sha256"], produced["stream_sha256"])
            self.assertTrue(result["all_chunks_authenticated_before_use"])
            self.assertTrue(result["footer_and_global_digest_checked"])
            self.assertFalse(result["flint_to_mathlib_realization_proved"])
            self.assertFalse(result["pt21_source_claim_discharged"])

    def test_cpp_consumer_rejects_payload_tampering_without_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stream = Path(temporary) / "gamma-stream.bin"
            _produce(stream)
            raw = bytearray(stream.read_bytes())
            raw[HEADER.size + CHUNK_HEADER.size + 7] ^= 1
            stream.write_bytes(raw)
            completed = _consume(stream)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(completed.stdout, "")
            self.assertIn("payload digest differs", completed.stderr)

    def test_cpp_consumer_rejects_footer_and_global_digest_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stream = Path(temporary) / "gamma-stream.bin"
            _produce(stream)
            raw = bytearray(stream.read_bytes())
            raw[len(raw) - FOOTER.size + 88] ^= 1
            stream.write_bytes(raw)
            completed = _consume(stream)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(completed.stdout, "")
            self.assertIn("footer differs", completed.stderr)

    def test_cpp_consumer_rejects_wrong_expected_range(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stream = Path(temporary) / "gamma-stream.bin"
            _produce(stream)
            completed = _consume(stream, first_block=1)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(completed.stdout, "")
            self.assertIn("first block differs", completed.stderr)


if __name__ == "__main__":
    unittest.main()
