#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Known-answer and forgery tests for the independent MPFR replay."""

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

from tests.tg_dirichlet_residue_composition_fixture import write_job  # type: ignore  # noqa: E402
from tg_verifier.dirichlet_allchars_stage import INPUT_HEADER  # noqa: E402
from tg_verifier.dirichlet_residue_composition import CompositionEngine  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checker", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        job, frames = write_job(root, t_indices=(127, 128, 129))
        output = root / "allchars-input.bin"
        receipt = CompositionEngine().compose(
            job, output, allow_synthetic_kat=True
        )
        if receipt["batch_count"] != 3 or receipt["group_order"] != 9792:
            raise RuntimeError("synthetic KAT work identity changed")
        command = [
            str(args.checker.resolve()),
            "verify",
            str(output),
            "384",
        ]
        for frame in frames:
            command.extend(
                [str(frame["lattice_output"]), str(frame["finite_recovery"])]
            )
        subprocess.run(command, check=True)

        forged = root / "forged.bin"
        shutil.copyfile(output, forged)
        with forged.open("r+b") as target:
            target.seek(INPUT_HEADER.size)
            target.write(struct.pack("<d", math.inf))
        forged_command = list(command)
        forged_command[2] = str(forged)
        rejected = subprocess.run(
            forged_command,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if rejected.returncode == 0:
            raise RuntimeError("independent MPFR replay accepted a forged interval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
