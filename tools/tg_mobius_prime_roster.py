#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Generate/check the canonical u32le prime roster through 10^8."""

from __future__ import annotations

import argparse
from array import array
import hashlib
from pathlib import Path
import sys


LIMIT = 100_000_000
EXPECTED_COUNT = 5_761_455
EXPECTED_LAST = 99_999_989
EXPECTED_SHA256 = (
    "0feea6e7805b8bae663ecadd180f8ea94061ff0b16d6f9da2472fbe2e6d5cbb5"
)


def _require_u32_array() -> None:
    if array("I").itemsize != 4:
        raise RuntimeError("this platform's unsigned-int array is not 32 bits")


def generate() -> bytes:
    _require_u32_array()
    sieve = bytearray(b"\x01") * (LIMIT + 1)
    sieve[0:2] = b"\x00\x00"
    for prime in range(2, int(LIMIT**0.5) + 1):
        if sieve[prime]:
            start = prime * prime
            sieve[start::prime] = b"\x00" * (
                (LIMIT - start) // prime + 1
            )
    primes = array("I", (index for index, flag in enumerate(sieve) if flag))
    if sys.byteorder != "little":
        primes.byteswap()
    raw = primes.tobytes()
    validate(raw)
    return raw


def validate(raw: bytes) -> None:
    _require_u32_array()
    if len(raw) != EXPECTED_COUNT * 4:
        raise ValueError("prime roster has the wrong byte length")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError(f"prime roster digest changed: {digest}")
    values = array("I")
    values.frombytes(raw)
    if sys.byteorder != "little":
        values.byteswap()
    if (
        len(values) != EXPECTED_COUNT
        or values[0] != 2
        or values[-1] != EXPECTED_LAST
        or any(left >= right for left, right in zip(values, values[1:]))
    ):
        raise ValueError("prime roster ordering or endpoints changed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--check", action="store_true", help="check an existing roster"
    )
    arguments = parser.parse_args()
    if arguments.check:
        validate(arguments.path.read_bytes())
    else:
        raw = generate()
        arguments.path.parent.mkdir(parents=True, exist_ok=True)
        arguments.path.write_bytes(raw)
    print(
        f"count={EXPECTED_COUNT} last={EXPECTED_LAST} "
        f"sha256={EXPECTED_SHA256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
