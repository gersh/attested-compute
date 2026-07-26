# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import replace
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests.test_tg_dirichlet_booker_smallq_compact_v3 import (
    _write_fixture,
)
from tg_verifier import dirichlet_booker_smallq_certified as v2
from tg_verifier import dirichlet_booker_smallq_compact_v3 as adapter
from tg_verifier import dirichlet_booker_smallq as base
from tg_verifier import dirichlet_compact_state_streaming_v3 as compact
from tg_verifier.dirichlet_booker_smallq_factored import (
    SERVICE_OUTPUT_BINDING,
)
from tg_verifier.dirichlet_booker_smallq_output_stream import (
    _preflight_batches,
)
from tg_verifier.dirichlet_booker_smallq_packed_stream_v1 import (
    FRAME_BATCH_BINDING,
    FRAME_DIGESTS,
    FRAME_DOMAIN,
    FRAME_PREFIX,
    FRAME_TRAILER,
    STREAM_END,
    TRAILER_MAGIC,
    FORMAT_VERSION_V1,
    SmallQPackedStreamV1Error,
    pack_factored_service_stream_v1,
    reduce_packed_stream_to_compact_v3,
)


class SmallQPackedStreamV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_temporary = tempfile.TemporaryDirectory()
        cls.fixture_root = Path(cls.fixture_temporary.name)
        (
            cls.plan,
            cls.batches,
            cls.control,
            cls.control_receipt,
            cls.raw_stream,
            cls.pins,
            cls.expected,
        ) = _write_fixture(cls.fixture_root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture_temporary.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _pack(self, raw: bytes | None = None) -> tuple[dict[str, object], bytes]:
        output = io.BytesIO()
        result = pack_factored_service_stream_v1(
            self.plan,
            self.batches,
            self.control,
            self.control_receipt,
            io.BytesIO(self.raw_stream if raw is None else raw),
            output,
            pins=self.pins,
            chunk_items=37,
            backend="scalar",
        )
        return result, output.getvalue()

    def _reduce(self, packed: bytes) -> tuple[dict[str, object], Path]:
        state = self.root / "state.bin"
        receipt = self.root / "receipt.json"
        result = reduce_packed_stream_to_compact_v3(
            self.plan,
            self.batches,
            self.control,
            self.control_receipt,
            io.BytesIO(packed),
            state,
            pins=self.pins,
            receipt_path=receipt,
            chunk_items=29,
        )
        return result, state

    @staticmethod
    def _layout(raw: bytes) -> tuple[int, int, int, int]:
        payload_offset = (
            FRAME_PREFIX.size
            + FRAME_BATCH_BINDING.size
            + FRAME_DIGESTS.size
        )
        prefix = FRAME_PREFIX.unpack(raw[: FRAME_PREFIX.size])
        payload_bytes = int(prefix[10])
        trailer_offset = payload_offset + payload_bytes
        end_offset = trailer_offset + FRAME_TRAILER.size
        return payload_offset, payload_bytes, trailer_offset, end_offset

    @staticmethod
    def _resign_one_frame(raw: bytes) -> bytes:
        changed = bytearray(raw)
        payload_offset, payload_bytes, trailer_offset, end_offset = (
            SmallQPackedStreamV1Tests._layout(changed)
        )
        frame_without_trailer = bytes(changed[:trailer_offset])
        payload = bytes(
            changed[payload_offset : payload_offset + payload_bytes]
        )
        frame_sha256 = hashlib.sha256(
            FRAME_DOMAIN + frame_without_trailer
        ).digest()
        changed[trailer_offset:end_offset] = FRAME_TRAILER.pack(
            TRAILER_MAGIC,
            FORMAT_VERSION_V1,
            0,
            0,
            payload_bytes,
            hashlib.sha256(payload).digest(),
            frame_sha256,
        )
        body = bytes(changed[:end_offset])
        old_end = STREAM_END.unpack(
            changed[end_offset : end_offset + STREAM_END.size]
        )
        changed[end_offset : end_offset + STREAM_END.size] = STREAM_END.pack(
            old_end[0],
            old_end[1],
            old_end[2],
            old_end[3],
            old_end[4],
            frame_sha256,
            hashlib.sha256(body).digest(),
        )
        return bytes(changed)

    def test_cpu_reference_packs_exact_nextafter_rule(self) -> None:
        raw = bytearray(self.raw_stream)
        _plan, batches = _preflight_batches(self.plan, self.batches)
        first_parity = batches[0].characters[0].parity
        threshold = 0.25 if first_parity == 0 else 2.0
        boundary = math.nextafter(0.1 + threshold, math.inf)
        item_offset = v2.OUTPUT_HEADER.size + SERVICE_OUTPUT_BINDING.size
        rows = list(v2.OUTPUT_ITEM.iter_unpack(raw[item_offset:]))
        exact = list(rows[0])
        exact[2] = boundary
        just_positive = list(rows[1])
        just_positive[2] = math.nextafter(boundary, math.inf)
        just_negative = list(rows[2])
        just_negative[2] = -math.nextafter(boundary, math.inf)
        for index, row in enumerate((exact, just_positive, just_negative)):
            start = item_offset + index * v2.OUTPUT_ITEM.size
            raw[start : start + v2.OUTPUT_ITEM.size] = v2.OUTPUT_ITEM.pack(
                *row
            )

        result, packed = self._pack(bytes(raw))
        payload_offset, _payload_bytes, _trailer, _end = self._layout(packed)
        first_byte = packed[payload_offset]
        self.assertEqual(first_byte & 3, 0)
        self.assertEqual((first_byte >> 2) & 3, 2)
        self.assertEqual((first_byte >> 4) & 3, 1)
        self.assertEqual(result["strict_boundary_rule"], (
            "nextafter(radius + threshold, +infinity)"
        ))
        self.assertEqual(
            result["packed_stream_sha256"], hashlib.sha256(packed).hexdigest()
        )
        self.assertFalse(result["source_admission_enabled"])
        self.assertFalse(result["dft_arithmetic_containment_replayed"])
        self.assertFalse(result["production_ready"])

    def test_packed_transport_matches_direct_compact_state(self) -> None:
        packed_result, packed = self._pack()
        result, state = self._reduce(packed)
        replayed = compact.replay_compact_state_v3(
            state, expected_record=result["compact_state_artifact"]
        )
        rows = list(compact.iter_compact_state_v3(state))
        self.assertEqual(
            [row["ambiguity_count"] for row in rows],
            [row["ambiguities"] for row in self.expected],
        )
        self.assertEqual(
            [row["internal_sign_change_count"] for row in rows],
            [row["transitions"] for row in self.expected],
        )
        self.assertEqual(
            result["packed_stream_sha256_receipt_only"],
            hashlib.sha256(packed).hexdigest(),
        )
        self.assertEqual(
            replayed["upstream_source_binding_sha256"],
            result["compact_source_binding_sha256"],
        )
        self.assertLess(
            packed_result["packed_stream_bytes_emitted"],
            packed_result["raw_disk_stream_bytes_consumed"] // 10,
        )
        self.assertTrue(
            result[
                "exact_plan_batch_control_roster_span_mode_bindings_checked"
            ]
        )
        self.assertTrue(result["reserved_code_and_padding_checked"])
        self.assertTrue(result["terminal_coverage_and_eof_checked"])
        self.assertFalse(result["runner_strict_sign_arithmetic_replayed_by_reducer"])
        self.assertFalse(result["analytic_seed_values_replayed"])
        self.assertFalse(result["zero_multiplicity_realized"])
        self.assertFalse(result["turing_closure_realized"])
        self.assertFalse(result["source_admission_enabled"])
        self.assertFalse(result["external_atom_discharged"])
        self.assertFalse(result["production_ready"])

    def test_frame_payload_tamper_fails_digest(self) -> None:
        _result, packed = self._pack()
        changed = bytearray(packed)
        payload_offset, _size, _trailer, _end = self._layout(changed)
        changed[payload_offset] ^= 1
        with self.assertRaisesRegex(
            SmallQPackedStreamV1Error, "trailer or payload digest"
        ):
            self._reduce(bytes(changed))

    def test_reserved_code_fails_even_with_consistent_transport_hashes(self) -> None:
        _result, packed = self._pack()
        changed = bytearray(packed)
        payload_offset, _size, _trailer, _end = self._layout(changed)
        changed[payload_offset] = (changed[payload_offset] & ~3) | 3
        changed = self._resign_one_frame(bytes(changed))
        with self.assertRaisesRegex(
            SmallQPackedStreamV1Error, "reserved sign code 3"
        ):
            self._reduce(changed)

    def test_nonzero_padding_fails_even_with_consistent_transport_hashes(self) -> None:
        _result, packed = self._pack()
        changed = bytearray(packed)
        payload_offset, payload_bytes, _trailer, _end = self._layout(changed)
        # The fixture has 165 characters * 6 samples = 990 codes, leaving
        # the high four bits of its final payload byte unused.
        changed[payload_offset + payload_bytes - 1] |= 0x40
        changed = self._resign_one_frame(bytes(changed))
        with self.assertRaisesRegex(
            SmallQPackedStreamV1Error, "nonzero unused padding bits"
        ):
            self._reduce(changed)

    def test_mode_and_control_binding_cannot_be_relabelled(self) -> None:
        _result, packed = self._pack()
        changed_mode = bytearray(packed)
        fields = list(FRAME_PREFIX.unpack(changed_mode[: FRAME_PREFIX.size]))
        fields[2] = 1
        changed_mode[: FRAME_PREFIX.size] = FRAME_PREFIX.pack(*fields)
        changed_mode = self._resign_one_frame(bytes(changed_mode))
        with self.assertRaisesRegex(
            SmallQPackedStreamV1Error, "identity, mode, span"
        ):
            self._reduce(changed_mode)

        changed_control = bytearray(packed)
        digest_offset = FRAME_PREFIX.size + FRAME_BATCH_BINDING.size
        control_offset = digest_offset + 2 * 32
        changed_control[control_offset] ^= 1
        changed_control = self._resign_one_frame(bytes(changed_control))
        with self.assertRaisesRegex(
            SmallQPackedStreamV1Error, "digest binding differs"
        ):
            self._reduce(changed_control)

    def test_truncation_trailing_bytes_and_terminal_replay_fail(self) -> None:
        _result, packed = self._pack()
        with self.assertRaisesRegex(
            SmallQPackedStreamV1Error, "truncated"
        ):
            self._reduce(packed[:-1])
        with self.assertRaisesRegex(
            SmallQPackedStreamV1Error, "trailing bytes"
        ):
            self._reduce(packed + b"\x00")
        changed = bytearray(packed)
        _payload, _size, _trailer, end_offset = self._layout(changed)
        end = list(
            STREAM_END.unpack(
                changed[end_offset : end_offset + STREAM_END.size]
            )
        )
        end[3] += 1
        changed[end_offset : end_offset + STREAM_END.size] = STREAM_END.pack(
            *end
        )
        with self.assertRaisesRegex(
            SmallQPackedStreamV1Error, "terminal coverage"
        ):
            self._reduce(bytes(changed))

    @unittest.skipUnless(
        os.environ.get("TG_SMALLQ_CERTIFIED_RUNNER"),
        "set TG_SMALLQ_CERTIFIED_RUNNER for the CUDA runner protocol KAT",
    )
    def test_cuda_runner_host_device_payload_and_state_are_identical(self) -> None:
        parameters = base.transform_parameters(self.pins.q)
        production_pins = replace(
            self.pins,
            stop_t_numerator=(
                parameters.sample_count * compact.SOURCE_SAMPLE_NUMERATOR
            ),
            structural_bounded_span_kat=False,
        )
        receipt = json.loads(self.control_receipt.read_text())
        def run(option: str) -> subprocess.CompletedProcess[bytes]:
            command = [
                os.environ["TG_SMALLQ_CERTIFIED_RUNNER"],
                "--source-samples-only",
                option,
                str(self.control),
                receipt["receipt_sha256"],
                production_pins.compact_complete_roster_sha256,
                adapter.pinset_sha256(production_pins),
                adapter._source_binding_sha256(production_pins),
                "--factored-service",
                str(self.plan),
                str(self.batches[0]),
                "-",
            ]
            return subprocess.run(command, check=True, capture_output=True)

        host = run("--strict-sign-packed")
        device = run("--strict-sign-packed-device")
        host_payload, host_payload_bytes, _host_trailer, _host_end = (
            self._layout(host.stdout)
        )
        device_payload, device_payload_bytes, _device_trailer, _device_end = (
            self._layout(device.stdout)
        )
        self.assertEqual(host_payload_bytes, device_payload_bytes)
        self.assertEqual(
            host.stdout[host_payload : host_payload + host_payload_bytes],
            device.stdout[
                device_payload : device_payload + device_payload_bytes
            ],
        )

        host_state = self.root / "cuda-host-state.bin"
        device_state = self.root / "cuda-device-state.bin"
        host_result = reduce_packed_stream_to_compact_v3(
            self.plan,
            self.batches,
            self.control,
            self.control_receipt,
            io.BytesIO(host.stdout),
            host_state,
            pins=production_pins,
            chunk_items=1 << 16,
            expected_packing_location="host",
        )
        result = reduce_packed_stream_to_compact_v3(
            self.plan,
            self.batches,
            self.control,
            self.control_receipt,
            io.BytesIO(device.stdout),
            device_state,
            pins=production_pins,
            chunk_items=1 << 16,
            expected_packing_location="device",
        )
        self.assertEqual(host_state.read_bytes(), device_state.read_bytes())
        self.assertEqual(
            host_result["compact_source_binding_sha256"],
            result["compact_source_binding_sha256"],
        )
        self.assertEqual(
            result["packed_stream_sha256_receipt_only"],
            hashlib.sha256(device.stdout).hexdigest(),
        )
        self.assertEqual(
            result["item_count"],
            len(self.expected) * parameters.sample_count,
        )
        self.assertEqual(
            result["ambiguous_sample_count"], result["item_count"]
        )
        self.assertEqual(result["negative_sample_count"], 0)
        self.assertEqual(result["positive_sample_count"], 0)
        self.assertEqual(result["expected_packing_location"], "device")
        self.assertFalse(result["source_admission_enabled"])
        self.assertIn(
            b'"algorithm":"platt-booker-smallq-runner-strict-sign-pack-device-v1"',
            device.stderr,
        )
        self.assertIn(b'"packing_location":"device"', device.stderr)

        with self.assertRaisesRegex(
            SmallQPackedStreamV1Error, "identity, mode, span"
        ):
            reduce_packed_stream_to_compact_v3(
                self.plan,
                self.batches,
                self.control,
                self.control_receipt,
                io.BytesIO(device.stdout),
                self.root / "wrong-location-state.bin",
                pins=production_pins,
                expected_packing_location="host",
            )

        tampered = bytearray(device.stdout)
        tampered[device_payload] ^= 1
        with self.assertRaisesRegex(
            SmallQPackedStreamV1Error, "trailer or payload digest"
        ):
            reduce_packed_stream_to_compact_v3(
                self.plan,
                self.batches,
                self.control,
                self.control_receipt,
                io.BytesIO(tampered),
                self.root / "tampered-device-state.bin",
                pins=production_pins,
                expected_packing_location="device",
            )

        reserved = bytearray(device.stdout)
        reserved[device_payload] = (reserved[device_payload] & ~3) | 3
        reserved = self._resign_one_frame(bytes(reserved))
        with self.assertRaisesRegex(
            SmallQPackedStreamV1Error, "reserved sign code 3"
        ):
            reduce_packed_stream_to_compact_v3(
                self.plan,
                self.batches,
                self.control,
                self.control_receipt,
                io.BytesIO(reserved),
                self.root / "reserved-device-state.bin",
                pins=production_pins,
                expected_packing_location="device",
            )

        padding = bytearray(device.stdout)
        padding[device_payload + device_payload_bytes - 1] |= 0x40
        padding = self._resign_one_frame(bytes(padding))
        with self.assertRaisesRegex(
            SmallQPackedStreamV1Error, "nonzero unused padding bits"
        ):
            reduce_packed_stream_to_compact_v3(
                self.plan,
                self.batches,
                self.control,
                self.control_receipt,
                io.BytesIO(padding),
                self.root / "padding-device-state.bin",
                pins=production_pins,
                expected_packing_location="device",
            )


if __name__ == "__main__":
    unittest.main()
