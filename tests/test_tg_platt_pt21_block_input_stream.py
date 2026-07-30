# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Known answers for the PT21 worker block-input stream.

The load-bearing check is byte identity: the ``PT21BLK1`` records produced by
streaming one authenticated ``PT21WB`` stream through the exact record adapter
must equal, byte for byte, the records the existing standalone file/manifest
assembly path produces from the same three inputs.  Every framing, digest,
linkage, ordering, truncation, and trailing-byte mutation must fail closed.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

from tests.test_tg_platt_pt21_native_record_adapter import (
    required_packet,
    stationary_trace,
    turing_inputs,
    worker,
)
from tg_verifier.platt_pt21_block_input_stream import (
    ALGORITHM_SHA256,
    FRAME_PREFIX_BYTES,
    HEADER_BYTES,
    BlockInputStreamReader,
    PT21BlockInputStreamError,
    REQUIRED_SIGN_PACKET_BYTES,
    SCHEMA,
    SHARD_REPORT_SCHEMA,
    adapt_stream,
    decode_frame,
    encode_footer,
    encode_frame,
    encode_header,
    stream_shard_archive,
    validate,
)
from tg_verifier.platt_pt21_event_record import (
    RECORD as EVENT_RECORD,
    RECORD_DOMAIN as EVENT_RECORD_DOMAIN,
    REQUIRED_SAMPLE_COUNT,
)
from tg_verifier.platt_pt21_native_finalizer import (
    BLOCK_RECORD,
    replay_shard,
)
from tg_verifier.platt_pt21_native_record_adapter import (
    adapt_block,
    worker_identity,
)
from tg_verifier.platt_pt21_stationary_junction import (
    PREFIX as JUNCTION_PREFIX,
    RECORD_BYTES as JUNCTION_RECORD_BYTES,
    RECORD_DIGEST_OFFSET as JUNCTION_RECORD_DIGEST_OFFSET,
    RECORD_DOMAIN as JUNCTION_RECORD_DOMAIN,
)


ROOT = Path(__file__).resolve().parents[1]
GAMMA_STREAM_SHA256 = "11" * 32
PRODUCER_SHA256 = "22" * 32
RESOLVER_SHA256 = "33" * 32
FLINT_SHA256 = "44" * 32
PLAN_SHA256 = "55" * 32
PREFIX_EVIDENCE_SHA256 = "66" * 32


def event_record(block: int) -> bytes:
    """One valid all-zero-count PT21EVT1 record for the given block."""

    raw = bytearray(
        EVENT_RECORD.pack(
            b"PT21EVT1",
            1,
            EVENT_RECORD.size,
            block,
            0,
            REQUIRED_SAMPLE_COUNT,
            1,
            0,
            *(0, 0, 0),  # direct event counts
            *(0, 0, 0),  # stationary candidate counts
            *(0, 0, 0),  # certified direct slots
            0,  # unresolved stationary total
            *(0, 0, 0),  # signed nleft unit sums
            *(0, 0, 0),  # signed nright unit sums
            hashlib.sha256(f"event-artifact-{block}".encode()).digest(),
            bytes(32),
        )
    )
    raw[160:192] = hashlib.sha256(
        EVENT_RECORD_DOMAIN + bytes(raw[:160])
    ).digest()
    return bytes(raw)


def junction_record(block: int, event: bytes, trace: bytes) -> bytes:
    """One valid zero-candidate PT21STJ1 record linked to `event`/`trace`."""

    raw = bytearray(JUNCTION_RECORD_BYTES)
    JUNCTION_PREFIX.pack_into(
        raw,
        0,
        b"PT21STJ1",
        1,
        JUNCTION_RECORD_BYTES,
        block,
        0,
        0,
        0,
        0,
        0,
        0,
        128,
        64,
        64,
        30_600,
        0,
        1,
        1,
    )
    digests = (
        event[160:192],
        hashlib.sha256(f"event-artifact-{block}".encode()).digest(),
        hashlib.sha256(b"candidate-list").digest(),
        hashlib.sha256(b"resolver-input").digest(),
        hashlib.sha256(b"refinement-trace").digest(),
        hashlib.sha256(b"resolution").digest(),
        hashlib.sha256(trace).digest(),
        bytes.fromhex(RESOLVER_SHA256),
        bytes.fromhex(FLINT_SHA256),
    )
    for index, digest in enumerate(digests):
        raw[80 + 32 * index : 112 + 32 * index] = digest
    raw[JUNCTION_RECORD_DIGEST_OFFSET:] = hashlib.sha256(
        JUNCTION_RECORD_DOMAIN + bytes(raw[:JUNCTION_RECORD_DIGEST_OFFSET])
    ).digest()
    return bytes(raw)


class BlockInputStreamTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        supplied = os.environ.get("TG_PLATT_PT21_NATIVE_FINALIZER")
        cls._build = None
        if supplied:
            cls.finalizer = Path(supplied)
            if not cls.finalizer.is_file() or not os.access(
                cls.finalizer, os.X_OK
            ):
                raise unittest.SkipTest(
                    "TG_PLATT_PT21_NATIVE_FINALIZER is not executable"
                )
            return
        compiler = shutil.which("g++")
        if compiler is None:
            raise unittest.SkipTest(
                "g++ is required for the streamed block-input shard test"
            )
        cls._build = tempfile.TemporaryDirectory()
        cls.finalizer = (
            Path(cls._build.name) / "tg-platt-pt21-native-finalizer"
        )
        subprocess.run(
            [
                compiler,
                "-std=c++20",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-Werror",
                f"-I{ROOT / 'gpu/include'}",
                str(ROOT / "reference/tg_platt_pt21_native_finalizer.cpp"),
                "-o",
                str(cls.finalizer),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._build is not None:
            cls._build.cleanup()

    def build_stream(
        self, directory: Path, blocks: tuple[int, ...], lower_counts: tuple[int, ...]
    ) -> tuple[Path, list[tuple[Path, Path, Path]]]:
        """Return one authenticated stream plus the same inputs as files."""

        inputs: list[tuple[Path, Path, Path]] = []
        frames: list[bytes] = []
        for block, lower_count in zip(blocks, lower_counts, strict=True):
            packet = required_packet(directory, block)
            trace = stationary_trace(directory, block)
            turing = turing_inputs(directory, packet, block, lower_count)
            inputs.append((packet, trace, turing))
            event = event_record(block)
            trace_raw = trace.read_bytes()
            frames.append(
                encode_frame(
                    block=block,
                    required_sign_packet=packet.read_bytes(),
                    event_record=event,
                    junction_record=junction_record(
                        block, event, trace_raw
                    ),
                    stationary_trace=trace_raw,
                    turing_inputs=turing.read_bytes(),
                )
            )
        header = encode_header(
            first_block=blocks[0],
            block_count=len(blocks),
            gamma_stream_sha256=GAMMA_STREAM_SHA256,
            producer_sha256=PRODUCER_SHA256,
            resolver_sha256=RESOLVER_SHA256,
            flint_sha256=FLINT_SHA256,
        )
        footer = encode_footer(
            first_block=blocks[0],
            block_count=len(blocks),
            total_frames=len(blocks),
            total_packet_bytes=len(blocks) * REQUIRED_SIGN_PACKET_BYTES,
            total_trace_bytes=sum(
                len(trace.read_bytes()) for _packet, trace, _turing in inputs
            ),
            total_turing_bytes=sum(
                len(turing.read_bytes())
                for _packet, _trace, turing in inputs
            ),
            frame_stream_sha256=hashlib.sha256(b"".join(frames)).digest(),
            header_sha256=header[224:256],
            gamma_stream_sha256=bytes.fromhex(GAMMA_STREAM_SHA256),
        )
        path = directory / "block-inputs.pt21wb"
        path.write_bytes(header + b"".join(frames) + footer)
        return path, inputs

    def test_independent_validation_accepts_and_claims_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path, _inputs = self.build_stream(directory, (0, 1), (1, 3))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result = validate(
                path,
                expected_stream_sha256=digest,
                expected_first_block=0,
                expected_block_count=2,
                expected_gamma_stream_sha256=GAMMA_STREAM_SHA256,
                expected_producer_sha256=PRODUCER_SHA256,
                expected_resolver_sha256=RESOLVER_SHA256,
                expected_flint_sha256=FLINT_SHA256,
            )
            self.assertEqual(result["schema"], SCHEMA)
            self.assertTrue(result["accepted"])
            self.assertEqual(result["frames_validated"], 2)
            self.assertTrue(result["three_adapter_inputs_present"])
            self.assertEqual(
                result["total_required_sign_packet_bytes"],
                2 * REQUIRED_SIGN_PACKET_BYTES,
            )
            for name in (
                "pt21blk1_present",
                "count_telescoping_checked",
                "producer_identity_self_verified",
                "hardy_z_endpoint_realization_proved",
                "main_multiplicity_realization_proved",
                "analytic_turing_realization_proved",
                "source_claim_ready",
            ):
                self.assertFalse(result[name], name)

    def test_streamed_records_are_byte_identical_to_the_file_channel(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path, inputs = self.build_stream(directory, (0, 1), (1, 3))
            measured = worker(directory)
            identity = worker_identity(measured)
            expected = b"".join(
                adapt_block(
                    required_sign_packet=packet,
                    stationary_trace=trace,
                    turing_inputs=turing,
                    worker=identity,
                ).record
                for packet, trace, turing in inputs
            )
            sink = directory / "streamed.records"
            with sink.open("wb") as destination:
                report = adapt_stream(
                    path,
                    destination=destination,
                    worker=identity,
                    first_block=0,
                    block_count=2,
                    expected_stream_sha256=hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest(),
                )
            self.assertEqual(sink.read_bytes(), expected)
            self.assertEqual(len(expected), 2 * BLOCK_RECORD.size)
            self.assertEqual(
                report["record_stream_sha256"],
                hashlib.sha256(expected).hexdigest(),
            )
            self.assertFalse(report["manifest_channel_used"])
            self.assertFalse(report["per_block_artifacts_retained"])
            self.assertFalse(report["source_claim_ready"])

    def test_stream_drives_the_pinned_native_shard_finalizer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path, _inputs = self.build_stream(directory, (0, 1), (1, 3))
            measured = worker(directory)
            output = directory / "shard.pt21"
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            finalizer_sha256 = hashlib.sha256(
                self.finalizer.read_bytes()
            ).hexdigest()
            result = stream_shard_archive(
                path,
                expected_stream_sha256=digest,
                worker=measured,
                finalizer=self.finalizer,
                expected_finalizer_sha256=finalizer_sha256,
                output=output,
                first_block=0,
                block_count=2,
                plan_sha256=PLAN_SHA256,
                prefix_evidence_sha256=PREFIX_EVIDENCE_SHA256,
                bounded_test=True,
            )
            self.assertEqual(result["schema"], SHARD_REPORT_SCHEMA)
            self.assertTrue(result["accepted"])
            self.assertFalse(result["manifest_channel_used"])
            self.assertFalse(result["source_claim_ready"])
            replayed = replay_shard(
                output,
                expected_worker_sha256=worker_identity(measured).sha256,
                expected_plan_sha256=PLAN_SHA256,
                expected_prefix_sha256=PREFIX_EVIDENCE_SHA256,
                allow_bounded_test=True,
            )
            self.assertEqual(replayed.block_count, 2)

    def test_cli_validate_matches_the_module(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path, _inputs = self.build_stream(directory, (0,), (1,))
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/tg_platt_pt21_block_input_stream.py"),
                    "validate",
                    str(path),
                    "--expected-stream-sha256",
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=300,
            )
            self.assertEqual(completed.stderr, b"")
            value = json.loads(completed.stdout)
            self.assertEqual(value["schema"], SCHEMA)
            self.assertEqual(value["frames_validated"], 1)
            self.assertFalse(value["source_claim_ready"])

    def test_native_producer_bytes_match_the_python_encoder(self) -> None:
        """Cross-implementation byte identity of the authenticated wire.

        The native side is the exact header the fused worker uses plus the
        shared exact-rational Arb Turing core.  The disks are synthetic, so
        this checks the wire and the nested payload checkers, not a source
        block: the real Arb counts deliberately do not close against synthetic
        sign changes, which is why the PT21BLK1 byte-identity known answer
        above uses the engineered adapter fixture instead.
        """

        supplied = os.environ.get("TG_PLATT_PT21_BLOCK_INPUT_STREAM_KAT")
        if not supplied:
            raise unittest.SkipTest(
                "TG_PLATT_PT21_BLOCK_INPUT_STREAM_KAT is not set"
            )
        kat = Path(supplied)
        if not kat.is_file() or not os.access(kat, os.X_OK):
            raise unittest.SkipTest(
                "TG_PLATT_PT21_BLOCK_INPUT_STREAM_KAT is not executable"
            )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / "native.pt21wb"
            completed = subprocess.run(
                [str(kat), str(path)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=300,
            )
            self.assertEqual(completed.stderr, b"")
            native = json.loads(completed.stdout)
            self.assertTrue(native["accepted"])
            self.assertFalse(native["source_block"])
            self.assertFalse(native["source_claim_ready"])
            raw = path.read_bytes()
            self.assertEqual(
                native["stream_sha256"], hashlib.sha256(raw).hexdigest()
            )
            result = validate(
                path, expected_stream_sha256=native["stream_sha256"]
            )
            self.assertEqual(result["frames_validated"], native["block_count"])

            with path.open("rb") as stream:
                reader = BlockInputStreamReader(stream, len(raw))
                rebuilt = bytearray(
                    encode_header(
                        first_block=reader.header.first_block,
                        block_count=reader.header.block_count,
                        gamma_stream_sha256=reader.header.gamma_stream_sha256,
                        producer_sha256=reader.header.producer_sha256,
                        resolver_sha256=reader.header.resolver_sha256,
                        flint_sha256=reader.header.flint_sha256,
                    )
                )
                frames = bytearray()
                for frame in reader:
                    encoded = encode_frame(
                        block=frame.block,
                        required_sign_packet=frame.required_sign_packet,
                        event_record=frame.event_record,
                        junction_record=frame.junction_record,
                        stationary_trace=frame.stationary_trace,
                        turing_inputs=frame.turing_inputs,
                    )
                    frames.extend(encoded)
                footer = reader.footer
            assert footer is not None
            rebuilt.extend(frames)
            rebuilt.extend(
                encode_footer(
                    first_block=footer.first_block,
                    block_count=footer.block_count,
                    total_frames=footer.total_frames,
                    total_packet_bytes=footer.total_packet_bytes,
                    total_trace_bytes=footer.total_trace_bytes,
                    total_turing_bytes=footer.total_turing_bytes,
                    frame_stream_sha256=hashlib.sha256(bytes(frames)).digest(),
                    header_sha256=bytes.fromhex(footer.header_sha256),
                    gamma_stream_sha256=bytes.fromhex(
                        footer.gamma_stream_sha256
                    ),
                )
            )
            self.assertEqual(bytes(rebuilt), raw)

    def test_algorithm_domain_digest_is_pinned(self) -> None:
        self.assertEqual(
            ALGORITHM_SHA256,
            hashlib.sha256(
                b"sparkinterval/tg/platt-pt21-worker-block-input-stream/v1\0"
            ).hexdigest(),
        )

    def mutations(self, raw: bytes, frame_offset: int) -> list[tuple[str, bytes]]:
        def flip(position: int) -> bytes:
            changed = bytearray(raw)
            changed[position] ^= 0x01
            return bytes(changed)

        return [
            ("header magic", flip(0)),
            ("header block count", flip(32)),
            ("header producer identity", flip(72)),
            ("header digest", flip(HEADER_BYTES - 1)),
            ("frame magic", flip(frame_offset)),
            ("frame block", flip(frame_offset + 16)),
            ("frame packet digest", flip(frame_offset + 48)),
            ("frame turing digest", flip(frame_offset + 176)),
            (
                "frame packet payload",
                flip(frame_offset + FRAME_PREFIX_BYTES + 200),
            ),
            ("footer totals", flip(len(raw) - FOOTER_TOTALS_OFFSET)),
            ("footer digest", flip(len(raw) - 1)),
            ("truncated footer", raw[:-1]),
            ("trailing byte", raw + b"\x00"),
        ]

    def test_every_mutation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path, _inputs = self.build_stream(directory, (0,), (1,))
            raw = path.read_bytes()
            for index, (label, mutated) in enumerate(
                self.mutations(raw, HEADER_BYTES)
            ):
                candidate = directory / f"mutation-{index}.pt21wb"
                candidate.write_bytes(mutated)
                with self.subTest(mutation=label):
                    with self.assertRaises(PT21BlockInputStreamError):
                        validate(candidate)

    def test_relabelled_frame_block_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet = required_packet(directory, 0)
            trace = stationary_trace(directory, 0)
            turing = turing_inputs(directory, packet, 0, 1)
            event = event_record(0)
            trace_raw = trace.read_bytes()
            frame = encode_frame(
                block=0,
                required_sign_packet=packet.read_bytes(),
                event_record=event,
                junction_record=junction_record(0, event, trace_raw),
                stationary_trace=trace_raw,
                turing_inputs=turing.read_bytes(),
            )
            with self.assertRaises(PT21BlockInputStreamError):
                decode_frame(frame, 1)

    def test_packet_from_another_block_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet = required_packet(directory, 7)
            trace = stationary_trace(directory, 0)
            turing = turing_inputs(directory, packet, 0, 1)
            event = event_record(0)
            trace_raw = trace.read_bytes()
            frame = encode_frame(
                block=0,
                required_sign_packet=packet.read_bytes(),
                event_record=event,
                junction_record=junction_record(0, event, trace_raw),
                stationary_trace=trace_raw,
                turing_inputs=turing.read_bytes(),
            )
            with self.assertRaises(PT21BlockInputStreamError):
                decode_frame(frame, 0)


FOOTER_TOTALS_OFFSET = 192 - 32 - 8


if __name__ == "__main__":
    unittest.main()
