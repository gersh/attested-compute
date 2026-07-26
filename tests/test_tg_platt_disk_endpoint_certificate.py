#!/usr/bin/env python3
"""Exact independent checks for the 320-byte Platt endpoint frame."""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path
import unittest

from tools.tg_platt_disk_endpoint_certificate import (
    BYTE_SIZE,
    CertificateError,
    inspect,
    lean_source,
)


def disk(re: float, im: float, radius: float) -> bytes:
    return struct.pack("<ddd", re, im, radius)


def mul(
    left: bytes,
    right: bytes,
    output: bytes,
    error: float,
    left_norm: float,
    right_norm: float,
) -> bytes:
    return left + right + output + struct.pack("<ddd", error, left_norm, right_norm)


def add(left: bytes, right: bytes, output: bytes, error: float) -> bytes:
    return left + right + output + struct.pack("<d", error)


def valid_frame() -> bytes:
    zero = 0.0
    left_input = disk(1.0, 2.0, zero)
    right_input = disk(3.0, 4.0, zero)
    left_projection = disk(1.0, zero, zero)
    right_projection = disk(3.0, zero, zero)
    plus_i = disk(1.0, 1.0, zero)
    minus_i = disk(1.0, -1.0, zero)
    left_product = disk(1.0, 1.0, zero)
    right_product = disk(3.0, -3.0, zero)
    output = disk(4.0, -2.0, zero)
    frame = (
        left_input
        + right_input
        + mul(left_projection, plus_i, left_product, zero, 1.0, 2.0)
        + mul(right_projection, minus_i, right_product, zero, 3.0, 2.0)
        + add(left_product, right_product, output, zero)
    )
    assert len(frame) == BYTE_SIZE
    return frame


class PlattDiskEndpointCertificateTest(unittest.TestCase):
    def write(self, raw: bytes) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "endpoint.bin"
        path.write_bytes(raw)
        return path

    def test_exact_valid_frame(self) -> None:
        result = inspect(self.write(valid_frame()))
        self.assertTrue(result["accepted"])
        self.assertEqual(result["byte_size"], BYTE_SIZE)
        self.assertTrue(all(result["checks"].values()))
        self.assertFalse(result["physical_cuda_to_bytes_refinement_proved"])

    def test_truncation_fails(self) -> None:
        with self.assertRaises(CertificateError):
            inspect(self.write(valid_frame()[:-1]))

    def test_negative_zero_fails(self) -> None:
        forged = bytearray(valid_frame())
        struct.pack_into("<Q", forged, 0, 1 << 63)
        with self.assertRaises(CertificateError):
            inspect(self.write(bytes(forged)))

    def test_insufficient_add_witness_fails(self) -> None:
        forged = bytearray(valid_frame())
        struct.pack_into("<d", forged, 288, 5.0)
        with self.assertRaises(CertificateError):
            inspect(self.write(bytes(forged)))

    def test_lean_emission_targets_kernel_checker(self) -> None:
        source = lean_source(self.write(valid_frame()), "fixtureBytes")
        self.assertIn("import SparkInterval.Zeta.PlattDiskPipelineWire", source)
        self.assertIn("#guard checkBytes fixtureBytes", source)


if __name__ == "__main__":
    unittest.main()
