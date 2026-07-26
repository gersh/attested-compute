#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark the conditional Dirichlet Taylor kernel on a labeled input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_lattice_stage import (  # noqa: E402
    ALGORITHM_ID,
    benchmark_projection,
    write_synthetic_input,
)


def positive(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--checker", type=Path)
    parser.add_argument("--q-start", type=positive, default=10_001)
    parser.add_argument("--q-stop", type=positive, default=10_250)
    parser.add_argument("--t-index", type=int, default=0)
    parser.add_argument("--items", type=positive, default=1_000_000)
    parser.add_argument("--iterations", type=positive, default=100)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    if args.t_index < 0 or args.device < 0:
        parser.error("t-index and device must be nonnegative")

    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        input_path = directory / "input.bin"
        output_path = directory / "output.bin"
        input_report = write_synthetic_input(
            input_path,
            q_start=args.q_start,
            q_stop=args.q_stop,
            t_index=args.t_index,
            max_items=args.items,
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
            raise RuntimeError(f"kernel benchmark failed: {completed.stderr[:4096]}")
        try:
            kernel = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("runner stdout is not one JSON object") from error
        if (
            kernel.get("algorithm") != ALGORITHM_ID
            or kernel.get("conditional_stage_only") is not True
            or kernel.get("item_count") != input_report["item_count"]
            or kernel.get("iterations") != args.iterations
            or kernel.get("status_or") != 0
        ):
            raise RuntimeError("runner benchmark report does not bind the request")

        exact_replay = None
        if args.checker is not None:
            replay = subprocess.run(
                [str(args.checker.resolve()), "verify", str(input_path),
                 str(output_path)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if replay.returncode != 0 or replay.stderr:
                raise RuntimeError(f"exact replay failed: {replay.stderr[:4096]}")
            exact_replay = json.loads(replay.stdout)

        report = {
            "schema": "sparkinterval.tg.dirichlet_lattice_stage.benchmark.v1",
            "classification": "synthetic_kernel_measurement_not_atom_verification",
            "input": input_report,
            "kernel": kernel,
            "exact_replay": exact_replay,
            "eight_h100_projection": benchmark_projection(
                items_per_second=float(kernel["items_per_second"])
            ),
            "exclusions": [
                "host input and output transfer",
                "certified lattice seed and Taylor-tail generation",
                "compact request generation and DFT fusion",
                "small-q FFT, upsampling, exceptional cases, and Turing completeness",
            ],
        }
    raw = json.dumps(
        report,
        sort_keys=True,
        indent=2 if args.pretty else None,
        separators=None if args.pretty else (",", ":"),
    ) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw, encoding="ascii")
    sys.stdout.write(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
