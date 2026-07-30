#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Emit the intermediate SHA-256 states a chunked Lean reduction needs.

`SparkInterval/Certificate/SHA256Chunked.lean` splits a whole-message
`hashSource` fold into fixed-size pieces so that each individual kernel
reduction stays inside the build's memory cap.  Each piece needs its starting
and ending compression state written out as an explicit eight-word literal.

This tool computes those states.  It is a *witness* generator, not a trusted
component: every literal it prints is re-derived by the Lean kernel when the
chunk lemmas are checked, and a wrong literal is a build failure.

Usage:

    tools/tg_sha256_chunk_witnesses.py FILE [--prefix-bytes HEX] [--chunk N]
    tools/tg_sha256_chunk_witnesses.py --text STRING [--chunk N]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


INITIAL = [
    0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
    0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19,
]

ROUND_CONSTANTS = [
    0x428A2F98, 0x71374491, 0xB5C0FBCF, 0xE9B5DBA5, 0x3956C25B, 0x59F111F1,
    0x923F82A4, 0xAB1C5ED5, 0xD807AA98, 0x12835B01, 0x243185BE, 0x550C7DC3,
    0x72BE5D74, 0x80DEB1FE, 0x9BDC06A7, 0xC19BF174, 0xE49B69C1, 0xEFBE4786,
    0x0FC19DC6, 0x240CA1CC, 0x2DE92C6F, 0x4A7484AA, 0x5CB0A9DC, 0x76F988DA,
    0x983E5152, 0xA831C66D, 0xB00327C8, 0xBF597FC7, 0xC6E00BF3, 0xD5A79147,
    0x06CA6351, 0x14292967, 0x27B70A85, 0x2E1B2138, 0x4D2C6DFC, 0x53380D13,
    0x650A7354, 0x766A0ABB, 0x81C2C92E, 0x92722C85, 0xA2BFE8A1, 0xA81A664B,
    0xC24B8B70, 0xC76C51A3, 0xD192E819, 0xD6990624, 0xF40E3585, 0x106AA070,
    0x19A4C116, 0x1E376C08, 0x2748774C, 0x34B0BCB5, 0x391C0CB3, 0x4ED8AA4A,
    0x5B9CCA4F, 0x682E6FF3, 0x748F82EE, 0x78A5636F, 0x84C87814, 0x8CC70208,
    0x90BEFFFA, 0xA4506CEB, 0xBEF9A3F7, 0xC67178F2,
]

MASK = 0xFFFFFFFF


def rotr(value: int, count: int) -> int:
    return ((value >> count) | (value << (32 - count))) & MASK


def compress(state: list[int], block: bytes) -> list[int]:
    schedule = [int.from_bytes(block[i * 4:i * 4 + 4], "big") for i in range(16)]
    for index in range(16, 64):
        s0 = rotr(schedule[index - 15], 7) ^ rotr(schedule[index - 15], 18) \
            ^ (schedule[index - 15] >> 3)
        s1 = rotr(schedule[index - 2], 17) ^ rotr(schedule[index - 2], 19) \
            ^ (schedule[index - 2] >> 10)
        schedule.append(
            (schedule[index - 16] + s0 + schedule[index - 7] + s1) & MASK)
    a, b, c, d, e, f, g, h = state
    for index in range(64):
        big1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)
        choose = (e & f) ^ ((~e & MASK) & g)
        t1 = (h + big1 + choose + ROUND_CONSTANTS[index] + schedule[index]) & MASK
        big0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)
        majority = (a & b) ^ (a & c) ^ (b & c)
        t2 = (big0 + majority) & MASK
        h, g, f, e, d, c, b, a = g, f, e, (d + t1) & MASK, c, b, a, (t1 + t2) & MASK
    return [(x + y) & MASK for x, y in zip(state, [a, b, c, d, e, f, g, h])]


def pad(message: bytes) -> bytes:
    zero_count = (56 + 64 - ((len(message) + 1) % 64)) % 64
    return (message + b"\x80" + b"\x00" * zero_count
            + (len(message) * 8).to_bytes(8, "big"))


def state_literal(state: list[int]) -> str:
    names = "abcdefgh"
    fields = ", ".join(
        f"{name} := 0x{value:08x}" for name, value in zip(names, state))
    return "{ " + fields + " }"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", help="file whose bytes are hashed")
    parser.add_argument("--text", help="hash this UTF-8 string instead")
    parser.add_argument("--prefix-bytes", default="",
                        help="hexadecimal domain prefix prepended to the input")
    parser.add_argument("--chunk", type=int, default=6,
                        help="blocks per kernel-sized chunk (default 6)")
    arguments = parser.parse_args(argv)

    if arguments.text is not None:
        message = arguments.text.encode()
    elif arguments.file is not None:
        message = Path(arguments.file).read_bytes()
    else:
        parser.error("give a file or --text")
        return 2

    message = bytes.fromhex(arguments.prefix_bytes) + message
    padded = pad(message)
    blocks = len(padded) // 64

    print(f"-- message bytes: {len(message)}")
    print(f"-- padded blocks: {blocks}")
    print(f"-- digest:        {hashlib.sha256(message).hexdigest()}")

    state = list(INITIAL)
    offset = 0
    index = 0
    while offset < blocks:
        width = min(arguments.chunk, blocks - offset)
        for step in range(width):
            state = compress(state, padded[(offset + step) * 64:
                                           (offset + step + 1) * 64])
        print(f"-- chunk {index}: blocks {offset}..{offset + width} "
              f"(offset {offset * 64})")
        print(f"--   {state_literal(state)}")
        offset += width
        index += 1

    digest = "".join(f"{word:08x}" for word in state)
    assert digest == hashlib.sha256(message).hexdigest(), "internal mismatch"
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
