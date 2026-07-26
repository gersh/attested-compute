#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark the compact selected-character oracle without claiming an atom ETA."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_fused_stage import (  # noqa: E402
    SOURCE_DIRECT_ALL_CHARACTER_GROUP_POINTS,
    write_synthetic_compact_input,
)
from tg_verifier.dirichlet_lattice_stage import maximum_t_index  # noqa: E402


def _positive(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--q", type=_positive, default=400_000)
    parser.add_argument("--t-index", type=int, default=4_000)
    parser.add_argument("--characters", type=_positive, default=256)
    parser.add_argument("--iterations", type=_positive, default=10)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    if args.t_index < 0 or args.device < 0:
        parser.error("t-index and device must be nonnegative")
    if not 10_001 <= args.q <= 400_000 or args.t_index > maximum_t_index(args.q):
        parser.error("benchmark q/t-index is outside the large-q source grid")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        input_path = root / "input.bin"
        output_path = root / "output.bin"
        input_report = write_synthetic_compact_input(
            input_path,
            q_values=[args.q],
            t_index=args.t_index,
            characters_per_q=args.characters,
        )
        completed = subprocess.run(
            [str(args.runner.resolve()), str(input_path), str(output_path),
             str(args.device), str(args.iterations)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if completed.returncode != 0 or completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
            return 1
        measured = json.loads(completed.stdout)
    rate = float(measured["group_points_per_second"])
    if not math.isfinite(rate) or rate <= 0:
        raise RuntimeError("runner returned an invalid throughput")
    result = {
        "classification": "synthetic_selected_character_stage_benchmark_not_atom_eta",
        "input": input_report,
        "runner": measured,
        "arithmetic_warning": {
            "source_direct_all_character_group_points": (
                SOURCE_DIRECT_ALL_CHARACTER_GROUP_POINTS
            ),
            "projected_direct_all_character_years_at_measured_rate": (
                SOURCE_DIRECT_ALL_CHARACTER_GROUP_POINTS
                / rate / (365.25 * 24 * 3600)
            ),
            "why_not_an_eta": (
                "the production main path must replace this quadratic direct "
                "oracle with an all-character interval FFT"
            ),
        },
        "h100_measured": False,
        "external_atom_runtime_estimated": False,
        "external_atom_discharged": False,
    }
    print(json.dumps(result, sort_keys=True, indent=2 if args.pretty else None,
                     separators=None if args.pretty else (",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
