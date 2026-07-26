#!/usr/bin/env python3
"""Independently replay one Platt hermidft endpoint disk certificate.

The CUDA producer emits a fixed 320-byte little-endian frame.  This checker
uses Python integers and ``Fraction`` only; it does not evaluate binary64
arithmetic.  Its equations mirror ``ComplexDisk`` and
``PlattDiskPipeline.Wire`` so malformed, non-finite, unlinked, or
radius-insufficient candidates fail closed before Lean ingestion.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct
import sys


BYTE_SIZE = 320
NEGATIVE_ZERO = 1 << 63
EXPONENT_MASK = 0x7FF
FRACTION_MASK = (1 << 52) - 1


class CertificateError(ValueError):
    """The candidate is not the fixed valid endpoint-certificate format."""


def decode_word(word: int) -> Fraction:
    if word == NEGATIVE_ZERO:
        raise CertificateError("negative zero is not canonical")
    sign = -1 if word >> 63 else 1
    exponent = (word >> 52) & EXPONENT_MASK
    fraction = word & FRACTION_MASK
    if exponent == EXPONENT_MASK:
        raise CertificateError("NaN or infinity is not a finite rational")
    if exponent == 0:
        significand = fraction
        shift = -1074
    else:
        significand = (1 << 52) + fraction
        shift = exponent - 1023 - 52
    value = Fraction(sign * significand)
    return value * (1 << shift) if shift >= 0 else value / (1 << -shift)


@dataclass(frozen=True)
class Disk:
    re: Fraction
    im: Fraction
    radius: Fraction


@dataclass(frozen=True)
class Mul:
    left: Disk
    right: Disk
    output: Disk
    center_error: Fraction
    left_norm: Fraction
    right_norm: Fraction


@dataclass(frozen=True)
class Add:
    left: Disk
    right: Disk
    output: Disk
    center_error: Fraction


class Reader:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.offset = 0

    def word(self) -> tuple[int, Fraction]:
        if self.offset + 8 > len(self.raw):
            raise CertificateError("certificate is truncated")
        word = struct.unpack_from("<Q", self.raw, self.offset)[0]
        self.offset += 8
        return word, decode_word(word)

    def disk(self) -> Disk:
        return Disk(self.word()[1], self.word()[1], self.word()[1])

    def mul(self) -> Mul:
        return Mul(
            self.disk(), self.disk(), self.disk(),
            self.word()[1], self.word()[1], self.word()[1],
        )

    def add(self) -> Add:
        return Add(self.disk(), self.disk(), self.disk(), self.word()[1])


def disk_ok(value: Disk) -> bool:
    return value.radius >= 0


def mul_ok(value: Mul) -> bool:
    left, right, output = value.left, value.right, value.output
    error_re = left.re * right.re - left.im * right.im - output.re
    error_im = left.re * right.im + left.im * right.re - output.im
    return (
        disk_ok(left)
        and disk_ok(right)
        and disk_ok(output)
        and value.center_error >= 0
        and value.left_norm >= 0
        and value.right_norm >= 0
        and error_re * error_re + error_im * error_im
        <= value.center_error * value.center_error
        and left.re * left.re + left.im * left.im
        <= value.left_norm * value.left_norm
        and right.re * right.re + right.im * right.im
        <= value.right_norm * value.right_norm
        and value.center_error
        + value.left_norm * right.radius
        + value.right_norm * left.radius
        + left.radius * right.radius
        <= output.radius
    )


def add_ok(value: Add) -> bool:
    left, right, output = value.left, value.right, value.output
    error_re = left.re + right.re - output.re
    error_im = left.im + right.im - output.im
    return (
        disk_ok(left)
        and disk_ok(right)
        and disk_ok(output)
        and value.center_error >= 0
        and error_re * error_re + error_im * error_im
        <= value.center_error * value.center_error
        and value.center_error + left.radius + right.radius <= output.radius
    )


def inspect(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) != BYTE_SIZE:
        raise CertificateError(
            f"endpoint certificate must be exactly {BYTE_SIZE} bytes"
        )
    reader = Reader(raw)
    left_input = reader.disk()
    right_input = reader.disk()
    left_mul = reader.mul()
    right_mul = reader.mul()
    output_add = reader.add()
    if reader.offset != len(raw):
        raise CertificateError("endpoint certificate has trailing bytes")
    plus_i = Disk(Fraction(1), Fraction(1), Fraction(0))
    minus_i = Disk(Fraction(1), Fraction(-1), Fraction(0))
    left_projection = Disk(left_input.re, Fraction(0), left_input.radius)
    right_projection = Disk(right_input.re, Fraction(0), right_input.radius)
    links = (
        left_mul.left == left_projection
        and left_mul.right == plus_i
        and right_mul.left == right_projection
        and right_mul.right == minus_i
        and output_add.left == left_mul.output
        and output_add.right == right_mul.output
    )
    checks = {
        "left_mul": mul_ok(left_mul),
        "right_mul": mul_ok(right_mul),
        "output_add": add_ok(output_add),
        "pipeline_links": links,
    }
    if not all(checks.values()):
        failed = ", ".join(name for name, value in checks.items() if not value)
        raise CertificateError(f"exact endpoint checks failed: {failed}")
    return {
        "accepted": True,
        "byte_size": len(raw),
        "checks": checks,
        "kind": "sparkinterval.platt-hermidft-endpoint-wire.v1",
        "lean_checker": "SparkInterval.Zeta.PlattDiskPipeline.Wire.checkBytes",
        "physical_cuda_to_bytes_refinement_proved": False,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "whole_transform_trace": False,
    }


def lean_source(path: Path, declaration: str) -> str:
    raw = path.read_bytes()
    if len(raw) != BYTE_SIZE:
        raise CertificateError(
            f"endpoint certificate must be exactly {BYTE_SIZE} bytes"
        )
    rows = []
    for start in range(0, len(raw), 16):
        rows.append("  " + ", ".join(f"0x{byte:02x}" for byte in raw[start:start + 16]))
    body = ",\n".join(rows)
    return (
        "import SparkInterval.Zeta.PlattDiskPipelineWire\n\n"
        "open SparkInterval.Zeta.PlattDiskPipeline.Wire\n\n"
        f"def {declaration} : List UInt8 := [\n{body}\n]\n\n"
        f"#guard checkBytes {declaration}\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check")
    check.add_argument("path", type=Path)
    emit = commands.add_parser("emit-lean")
    emit.add_argument("path", type=Path)
    emit.add_argument("--declaration", default="plattHermidftEndpointBytes")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            print(json.dumps(inspect(args.path), sort_keys=True, separators=(",", ":")))
        else:
            print(lean_source(args.path, args.declaration), end="")
    except (CertificateError, OSError) as error:
        print(json.dumps({"accepted": False, "error": str(error)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
