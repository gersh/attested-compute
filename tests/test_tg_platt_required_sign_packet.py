# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from tg_verifier.platt_required_sign_packet import (
    HEADER,
    REQUIRED_BEGIN,
    REQUIRED_COUNT,
    REQUIRED_END,
    SAMPLE,
    SOURCE_LOWER_CENTER,
    UPSTREAM_COMMIT,
    PlattRequiredSignPacketError,
    inspect_required_sign_packet,
    load_required_sign_packet,
)


def fnv1a(raw: bytes) -> int:
    value = 1_469_598_103_934_665_603
    for byte in raw:
        value ^= byte
        value = (value * 1_099_511_628_211) & ((1 << 64) - 1)
    return value


def build_packet(directory: Path) -> tuple[Path, Path]:
    source = directory / "source.bin"
    source.write_bytes(b"bound source packet")
    source_raw = source.read_bytes()
    samples = bytearray()
    signs = bytearray((REQUIRED_COUNT + 7) // 8)
    for index in range(REQUIRED_COUNT):
        hi = 1.0 if index % 3 else -1.0
        samples.extend(SAMPLE.pack(hi, 0.0, 0.25))
        if hi > 0.0:
            signs[index // 8] |= 1 << (index % 8)
    source_sha = hashlib.sha256(source_raw).hexdigest().encode("ascii")
    header = HEADER.pack(
        b"PT21SGN1",
        1,
        HEADER.size,
        0x01020304,
        1,
        1,
        768_000,
        REQUIRED_BEGIN,
        REQUIRED_END,
        REQUIRED_COUNT,
        0,
        SOURCE_LOWER_CENTER,
        len(samples),
        len(signs),
        fnv1a(samples),
        fnv1a(signs),
        len(source_raw),
        source_sha,
        UPSTREAM_COMMIT,
    )
    packet = directory / "required-sign.bin"
    packet.write_bytes(header + samples + signs)
    return packet, source


class PlattRequiredSignPacketTest(unittest.TestCase):
    def test_required_sign_packet_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, source = build_packet(Path(temporary))
            decoded = load_required_sign_packet(packet, source_packet=source)
            self.assertEqual(len(decoded.samples), REQUIRED_COUNT)
            self.assertFalse(decoded.samples[0].positive)
            self.assertTrue(decoded.samples[1].positive)
            report = inspect_required_sign_packet(packet, source_packet=source)
            self.assertTrue(report["accepted"])
            self.assertTrue(report["all_signs_recomputed"])
            self.assertTrue(report["source_packet_rechecked"])
            self.assertFalse(report["zero_isolation_events_constructed"])
            self.assertFalse(report["lean_source_claim_ready"])

    def test_required_sign_packet_rejects_sign_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, _source = build_packet(Path(temporary))
            raw = bytearray(packet.read_bytes())
            raw[HEADER.size + REQUIRED_COUNT * SAMPLE.size] ^= 1
            # Keep the transport checksum valid so the arithmetic check runs.
            sign_raw = bytes(raw[HEADER.size + REQUIRED_COUNT * SAMPLE.size :])
            fields = list(HEADER.unpack_from(raw))
            fields[15] = fnv1a(sign_raw)
            raw[: HEADER.size] = HEADER.pack(*fields)
            packet.write_bytes(raw)
            with self.assertRaisesRegex(
                PlattRequiredSignPacketError, "sign bit differs"
            ):
                load_required_sign_packet(packet)

    def test_required_sign_packet_rejects_unbound_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, source = build_packet(Path(temporary))
            source.write_bytes(b"different source")
            with self.assertRaisesRegex(
                PlattRequiredSignPacketError, "source packet size differs"
            ):
                load_required_sign_packet(packet, source_packet=source)


if __name__ == "__main__":
    unittest.main()
