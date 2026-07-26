#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""GPU/CPU KAT for compact CRT generation and fused character sums."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_fused_stage import (  # noqa: E402
    CHARACTER_REQUEST,
    CYCLIC_COMPONENT,
    INPUT_HEADER,
    LOCAL_FACTOR,
    MODULUS_TASK,
    OUTPUT_HEADER,
    write_synthetic_compact_input,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--device", type=int, default=0)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        input_path = root / "input.bin"
        gpu_output = root / "gpu-output.bin"
        cpu_output = root / "cpu-output.bin"
        report = write_synthetic_compact_input(
            input_path,
            q_values=[5, 8, 15],
            t_index=127,
            characters_per_q=None,
        )
        # U(5), U(8), U(15) exercise a cyclic C4 factor, the C2 x C2
        # decomposition of a 2-power, and a two-prime CRT product.  Their roots
        # of unity are exactly representable, so this KAT makes no libm claim.
        if report["total_selected_characters"] != 16:
            raise RuntimeError("unexpected KAT character count")
        subprocess.run(
            [str(args.runner.resolve()), str(input_path), str(gpu_output),
             str(args.device), "1"],
            check=True,
        )
        subprocess.run(
            [str(args.checker.resolve()), "verify", str(input_path),
             str(gpu_output)],
            check=True,
        )
        subprocess.run(
            [str(args.checker.resolve()), "compute", str(input_path),
             str(cpu_output)],
            check=True,
        )
        subprocess.run(
            [str(args.checker.resolve()), "verify", str(input_path),
             str(cpu_output)],
            check=True,
        )

        # The first rectangle begins after the output header and its 16-byte
        # identity.  A forged non-finite endpoint must fail closed.
        with gpu_output.open("r+b") as output:
            output.seek(OUTPUT_HEADER.size + 16)
            output.write(struct.pack("<d", math.inf))
        forged = subprocess.run(
            [str(args.checker.resolve()), "verify", str(input_path),
             str(gpu_output)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if forged.returncode == 0:
            raise RuntimeError("exact checker accepted forged fused output")

        # The character ID is redundant with its frequency tuple. Corrupting
        # that identity must be rejected before either implementation computes.
        forged_input = root / "forged-input.bin"
        shutil.copyfile(input_path, forged_input)
        first_character_offset = (
            INPUT_HEADER.size
            + 3 * MODULUS_TASK.size
            + 4 * LOCAL_FACTOR.size
            + 5 * CYCLIC_COMPONENT.size
        )
        if first_character_offset != 616 or CHARACTER_REQUEST.size != 40:
            raise RuntimeError("KAT format-size invariant changed")
        with forged_input.open("r+b") as output:
            output.seek(first_character_offset)
            output.write(struct.pack("<I", 1))
        rejected = subprocess.run(
            [str(args.runner.resolve()), str(forged_input),
             str(root / "forged-input-output.bin"), str(args.device), "1"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if rejected.returncode == 0:
            raise RuntimeError("GPU runner accepted a forged character identity")
        exact_rejected = subprocess.run(
            [str(args.checker.resolve()), "compute", str(forged_input),
             str(root / "forged-exact-output.bin")],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if exact_rejected.returncode == 0:
            raise RuntimeError("exact checker accepted a forged character identity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
