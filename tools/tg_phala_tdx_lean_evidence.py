#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Emit the Lean literals a TDX quote or statement needs.

`SparkInterval/Execution/TdxQuoteV4.lean` reads quotes as
`SHA256.PackedBytes`: one big-endian natural number plus a byte count.  This
tool turns a file into that literal, and optionally into the chunked
compression witnesses a kernel-checked digest theorem needs.

Nothing here is trusted.  Every literal it emits is re-derived by the Lean
kernel; a wrong one is a build failure, not a silent acceptance.

    tools/tg_phala_tdx_lean_evidence.py packed FILE
    tools/tg_phala_tdx_lean_evidence.py digest-witnesses FILE [--chunk N] \\
        [--prefix-bytes HEX] [--source-expr EXPR] [--name NAME]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
from pathlib import Path


TOOLS = Path(__file__).resolve().parent


def _witness_module():
    spec = importlib.util.spec_from_file_location(
        "tg_sha256_chunk_witnesses", TOOLS / "tg_sha256_chunk_witnesses.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def packed_literal(data: bytes) -> str:
    return "{ packed := 0x%s\n  byteCount := %d }" % (data.hex(), len(data))


def emit_packed(path: Path) -> int:
    data = path.read_bytes()
    print(f"-- {path}: {len(data)} bytes, "
          f"sha256 {hashlib.sha256(data).hexdigest()}")
    print(packed_literal(data))
    return 0


def emit_digest_witnesses(path: Path, chunk: int, prefix: bytes,
                          source_expr: str, name: str) -> int:
    module = _witness_module()
    message = prefix + path.read_bytes()
    padded = module.pad(message)
    blocks = len(padded) // 64

    state = list(module.INITIAL)
    offset = 0
    index = 0
    counts = []
    print(f"-- {path}: {len(message)} message bytes, {blocks} padded blocks")
    print(f"-- digest {hashlib.sha256(message).hexdigest()}")
    while offset < blocks:
        width = min(chunk, blocks - offset)
        before = module.state_literal(state)
        for step in range(width):
            state = module.compress(
                state, padded[(offset + step) * 64:(offset + step + 1) * 64])
        after = module.state_literal(state)
        print()
        print(f"/-- Chunk {index}: blocks {offset} to {offset + width}. -/")
        print(f"private theorem {name}_chunk{index} :")
        print(f"    foldSourceBlocks (sourceBlockStep {source_expr}) "
              f"{width} {offset * 64}")
        print(f"        {before} =")
        print(f"      {after} := by")
        print("  rfl")
        counts.append(width)
        offset += width
        index += 1

    chain = f"{name}_chunk{index - 1}"
    for back in range(index - 2, -1, -1):
        chain = f"foldSourceBlocks_of_split _ {name}_chunk{back} ({chain})"
    grouped = counts[-1]
    for width in reversed(counts[:-1]):
        grouped = f"{width} + ({grouped})"
    print()
    print(f"-- block count: {grouped}")
    print(f"-- chain: {chain}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    packed = sub.add_parser("packed", help="emit a PackedBytes literal")
    packed.add_argument("file")

    witnesses = sub.add_parser("digest-witnesses",
                               help="emit chunked compression witnesses")
    witnesses.add_argument("file")
    witnesses.add_argument("--chunk", type=int, default=6)
    witnesses.add_argument("--prefix-bytes", default="")
    witnesses.add_argument("--source-expr", default="source")
    witnesses.add_argument("--name", default="evidence")

    arguments = parser.parse_args(argv)
    if arguments.command == "packed":
        return emit_packed(Path(arguments.file))
    return emit_digest_witnesses(
        Path(arguments.file), arguments.chunk,
        bytes.fromhex(arguments.prefix_bytes),
        arguments.source_expr, arguments.name)


if __name__ == "__main__":
    sys.set_int_max_str_digits(1000000)
    sys.exit(main(sys.argv[1:]))
