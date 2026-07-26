# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tg_verifier.platt_gamma_taylor_stream import (
    CHUNK_HEADER,
    FOOTER,
    HEADER,
    PlattGammaTaylorStreamError,
    RECORD,
    inspect_gamma_taylor_stream,
    open_gamma_taylor_chunk_stream,
)


RUNNER_ENV = "SPARKINTERVAL_TG_PLATT_GAMMA_TAYLOR_RUNNER"
EXPECTED_HEADER_SHA256 = (
    "78af4aa0aff1fc15e896e9ab6304358461c46f777f26197f92ae1ac0811fee73"
)
EXPECTED_STREAM_SHA256 = (
    "f55539cf8f83d8f9358aeb12e79e06f2e8e442b8ced9de4e29230cbf67405c15"
)
EXPECTED_ARTIFACT_SHA256 = (
    "289dd7d3c90080ed988f2dc5e806179e73b18f576f7fb97eae2b7cfc8a7b6b59"
)
FINAL_EIGHT_FIRST_BLOCK = 2_966_443_775
EXPECTED_FINAL_EIGHT_STREAM_SHA256 = (
    "195bd83f04d530c817c6b560d447d9db0e1db1785202d558dc8e550cdea0803b"
)


def _runner() -> Path:
    value = os.environ.get(RUNNER_ENV)
    if not value:
        raise unittest.SkipTest(f"set {RUNNER_ENV} to run producer KAT")
    path = Path(value)
    if not path.is_file():
        raise unittest.SkipTest(f"Gamma Taylor runner is missing: {path}")
    return path


def _producer_command(
    runner: Path, output: Path | None, *, first_block: int = 0
) -> list[str]:
    command = [
        str(runner),
        "--stream-first-block",
        str(first_block),
        "--stream-blocks",
        "8",
        "--stream-chunk-records",
        "3",
        "--stream-audit-stride",
        "4",
        "--audit-samples",
        "9",
    ]
    if output is None:
        command.append("--stream-hash-only")
    else:
        command.extend(("--stream-output", str(output)))
    return command


def _produce(
    runner: Path, output: Path | None, *, first_block: int = 0
) -> dict[str, object]:
    command = _producer_command(runner, output, first_block=first_block)
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    rows = [row for row in completed.stdout.splitlines() if row.strip()]
    if len(rows) != 1:
        raise AssertionError(f"expected one producer JSON row, got {len(rows)}")
    return json.loads(rows[0])


class PlattGammaTaylorStreamTest(unittest.TestCase):
    def test_producer_stream_matches_independent_decoder_and_kat(self) -> None:
        runner = _runner()
        with tempfile.TemporaryDirectory() as temporary:
            stream = Path(temporary) / "gamma-stream.bin"
            produced = _produce(runner, stream)
            inspected = inspect_gamma_taylor_stream(
                stream,
                expected_first_block=0,
                expected_block_count=8,
                expected_stream_sha256=EXPECTED_STREAM_SHA256,
            )
            self.assertEqual(produced["header_sha256"], EXPECTED_HEADER_SHA256)
            self.assertEqual(produced["stream_sha256"], EXPECTED_STREAM_SHA256)
            self.assertEqual(inspected.header_sha256, EXPECTED_HEADER_SHA256)
            self.assertEqual(inspected.stream_sha256, EXPECTED_STREAM_SHA256)
            self.assertEqual(inspected.artifact_sha256, EXPECTED_ARTIFACT_SHA256)
            self.assertEqual(inspected.block_count, 8)
            self.assertEqual(inspected.chunk_count, 3)
            self.assertEqual(inspected.record_payload_bytes, 8 * 264)

    def test_hash_only_and_written_stream_have_identical_identity(self) -> None:
        runner = _runner()
        with tempfile.TemporaryDirectory() as temporary:
            stream = Path(temporary) / "gamma-stream.bin"
            hash_only = _produce(runner, None)
            written = _produce(runner, stream)
            for field in (
                "header_sha256",
                "stream_sha256",
                "first_record_sha256",
                "last_record_sha256",
                "artifact_bytes",
            ):
                self.assertEqual(hash_only[field], written[field])

    def test_final_campaign_record_is_total_and_has_fixed_identity(self) -> None:
        runner = _runner()
        produced = _produce(runner, None, first_block=FINAL_EIGHT_FIRST_BLOCK)
        self.assertEqual(produced["first_block"], FINAL_EIGHT_FIRST_BLOCK)
        self.assertEqual(produced["last_window_center"], 3_000_175_332_760)
        self.assertEqual(
            produced["stream_sha256"], EXPECTED_FINAL_EIGHT_STREAM_SHA256
        )

    def test_decoder_rejects_payload_tampering_before_interval_use(self) -> None:
        runner = _runner()
        with tempfile.TemporaryDirectory() as temporary:
            stream = Path(temporary) / "gamma-stream.bin"
            _produce(runner, stream)
            raw = bytearray(stream.read_bytes())
            raw[HEADER.size + CHUNK_HEADER.size + 7] ^= 1
            stream.write_bytes(raw)
            with self.assertRaisesRegex(
                PlattGammaTaylorStreamError, "payload digest differs"
            ):
                with open_gamma_taylor_chunk_stream(stream) as chunks:
                    next(chunks)

    def test_iterator_yields_only_checked_bounded_chunks_and_finishes(self) -> None:
        runner = _runner()
        with tempfile.TemporaryDirectory() as temporary:
            stream = Path(temporary) / "gamma-stream.bin"
            _produce(runner, stream)
            with open_gamma_taylor_chunk_stream(
                stream,
                expected_first_block=0,
                expected_block_count=8,
                expected_chunk_records=3,
                expected_stream_sha256=EXPECTED_STREAM_SHA256,
                max_chunk_records=3,
            ) as chunks:
                yielded = list(chunks)
                self.assertTrue(chunks.authenticated)
                self.assertEqual(chunks.inspection.stream_sha256, EXPECTED_STREAM_SHA256)
            self.assertEqual([chunk.first_block for chunk in yielded], [0, 3, 6])
            self.assertEqual([chunk.record_count for chunk in yielded], [3, 3, 2])
            self.assertEqual([len(chunk.payload) for chunk in yielded], [792, 792, 528])

    def test_invalid_interval_is_rejected_before_yield_even_with_fresh_chunk_hash(self) -> None:
        runner = _runner()
        with tempfile.TemporaryDirectory() as temporary:
            stream = Path(temporary) / "gamma-stream.bin"
            _produce(runner, stream)
            raw = bytearray(stream.read_bytes())
            chunk_offset = HEADER.size
            fields = list(CHUNK_HEADER.unpack_from(raw, chunk_offset))
            payload_offset = chunk_offset + CHUNK_HEADER.size
            payload_bytes = fields[6]
            self.assertEqual(payload_bytes, 3 * RECORD.size)
            struct.pack_into("<d", raw, payload_offset, float("nan"))
            payload = bytes(raw[payload_offset : payload_offset + payload_bytes])
            fields[7] = hashlib.sha256(payload).digest()
            CHUNK_HEADER.pack_into(raw, chunk_offset, *fields)
            stream.write_bytes(raw)
            with self.assertRaisesRegex(
                PlattGammaTaylorStreamError, "invalid coefficient interval"
            ):
                with open_gamma_taylor_chunk_stream(stream) as chunks:
                    next(chunks)

    def test_normal_early_exit_is_rejected_without_global_footer(self) -> None:
        runner = _runner()
        with tempfile.TemporaryDirectory() as temporary:
            stream = Path(temporary) / "gamma-stream.bin"
            _produce(runner, stream)
            with self.assertRaisesRegex(
                PlattGammaTaylorStreamError,
                "stopped before authenticated footer",
            ):
                with open_gamma_taylor_chunk_stream(stream) as chunks:
                    first = next(chunks)
                    self.assertEqual(first.first_block, 0)
                    self.assertFalse(chunks.authenticated)

    def test_named_pipe_supports_retention_free_online_consumption(self) -> None:
        runner = _runner()
        with tempfile.TemporaryDirectory() as temporary:
            fifo = Path(temporary) / "gamma-stream.fifo"
            os.mkfifo(fifo, 0o600)
            producer = subprocess.Popen(
                _producer_command(runner, fifo),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                with open_gamma_taylor_chunk_stream(
                    fifo,
                    expected_first_block=0,
                    expected_block_count=8,
                    expected_chunk_records=3,
                    expected_stream_sha256=EXPECTED_STREAM_SHA256,
                    max_chunk_records=3,
                    allow_fifo=True,
                ) as chunks:
                    yielded = list(chunks)
                    self.assertTrue(chunks.authenticated)
                stdout, stderr = producer.communicate(timeout=10)
            finally:
                if producer.poll() is None:
                    producer.kill()
                    producer.wait(timeout=10)
            self.assertEqual(producer.returncode, 0, stderr)
            self.assertEqual(len(yielded), 3)
            produced = json.loads(stdout)
            self.assertEqual(produced["stream_sha256"], EXPECTED_STREAM_SHA256)
            self.assertFalse(fifo.is_file())

    def test_footer_mutation_is_rejected_after_local_chunks(self) -> None:
        runner = _runner()
        with tempfile.TemporaryDirectory() as temporary:
            stream = Path(temporary) / "gamma-stream.bin"
            _produce(runner, stream)
            raw = bytearray(stream.read_bytes())
            # stream_sha256 starts 88 bytes into the 128-byte footer.
            raw[len(raw) - FOOTER.size + 88] ^= 1
            stream.write_bytes(raw)
            yielded = 0
            with self.assertRaisesRegex(PlattGammaTaylorStreamError, "footer differs"):
                with open_gamma_taylor_chunk_stream(stream) as chunks:
                    for _chunk in chunks:
                        yielded += 1
            self.assertEqual(yielded, 3)

    def test_declared_chunk_size_must_fit_consumer_memory_policy(self) -> None:
        runner = _runner()
        with tempfile.TemporaryDirectory() as temporary:
            stream = Path(temporary) / "gamma-stream.bin"
            _produce(runner, stream)
            with self.assertRaisesRegex(
                PlattGammaTaylorStreamError, "fixed header differs"
            ):
                open_gamma_taylor_chunk_stream(stream, max_chunk_records=2)

    def test_decoder_binds_invocation_range(self) -> None:
        runner = _runner()
        with tempfile.TemporaryDirectory() as temporary:
            stream = Path(temporary) / "gamma-stream.bin"
            _produce(runner, stream)
            with self.assertRaisesRegex(
                PlattGammaTaylorStreamError, "block count differs"
            ):
                inspect_gamma_taylor_stream(stream, expected_block_count=9)


if __name__ == "__main__":
    unittest.main()
