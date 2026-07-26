#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Cross-check the CUDA Taylor stage against the exact dyadic CPU checker."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import subprocess
import struct
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_lattice_stage import write_synthetic_input  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--device", type=int, default=0)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        input_path = root / "input.bin"
        output_path = root / "output.bin"
        write_synthetic_input(
            input_path,
            q_start=10_001,
            q_stop=10_004,
            t_index=127,
            max_items=257,
        )
        subprocess.run(
            [str(args.runner.resolve()), str(input_path), str(output_path),
             str(args.device), "1"],
            check=True,
        )
        subprocess.run(
            [str(args.checker.resolve()), "verify", str(input_path), str(output_path)],
            check=True,
        )

        # Exercise the upper q boundary, clipped nearest rows, both delta
        # signs, and t=0.  The exact dyadic checker evaluates the mathematical
        # interval expression independently of the CUDA sign-quadrant
        # multiplication fast path.
        edge_input = root / "edge-input.bin"
        edge_output = root / "edge-output.bin"
        write_synthetic_input(
            edge_input,
            q_start=399_989,
            q_stop=400_000,
            t_index=0,
            max_items=257,
        )
        subprocess.run(
            [
                str(args.runner.resolve()),
                str(edge_input),
                str(edge_output),
                str(args.device),
                "1",
            ],
            check=True,
        )
        subprocess.run(
            [
                str(args.checker.resolve()),
                "verify",
                str(edge_input),
                str(edge_output),
            ],
            check=True,
        )

        # A negative tail radius is outside the arithmetic contract and must
        # be rejected by the runner before a kernel result is published.
        malformed_input = root / "negative-tail-input.bin"
        malformed_input.write_bytes(edge_input.read_bytes())
        with malformed_input.open("r+b") as target:
            # 64-byte header + 2048*16 32-byte lattice cells, then the first
            # InputItem's 16-byte identity and 8-byte tail radius.
            target.seek(64 + 2048 * 16 * 32 + 16)
            target.write(struct.pack("<d", -math.ldexp(1.0, -42)))
        rejected_input = subprocess.run(
            [
                str(args.runner.resolve()),
                str(malformed_input),
                str(root / "negative-tail-output.bin"),
                str(args.device),
                "1",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if rejected_input.returncode == 0:
            raise RuntimeError("runner accepted a negative Taylor radius")

        # The first output rectangle starts after the 48-byte header and its
        # 16-byte identity. A non-finite forged lower endpoint must fail closed.
        with output_path.open("r+b") as output:
            output.seek(48 + 16)
            output.write(struct.pack("<d", math.inf))
        forged = subprocess.run(
            [str(args.checker.resolve()), "verify", str(input_path), str(output_path)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if forged.returncode == 0:
            raise RuntimeError("exact checker accepted forged non-finite output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
