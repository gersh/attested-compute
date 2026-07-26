#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark one fused large-q batch and project its exact residue workload."""

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

from tg_verifier.dirichlet_largeq_batch import source_work  # noqa: E402


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--repetitions", type=_positive, default=20)
    parser.add_argument("--production-gpus", type=_positive, default=8)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "output.bin"
        process = subprocess.run(
            [
                str(args.runner.resolve()),
                str(args.input.resolve()),
                str(output),
                str(args.device),
                str(args.repetitions),
            ],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
    runner = json.loads(process.stdout)
    rate = float(runner["values_per_second"])
    work = source_work(batch_size=64)
    count = int(work["residue_compositions"])
    equal_gpu_hours = count / rate / 3600 / args.production_gpus
    report = {
        "classification": "local_kernel_sample_and_engineering_sensitivity_not_atom_eta",
        "runner": runner,
        "exact_source_residue_values": count,
        "production_gpus": args.production_gpus,
        "equal_local_gpu_wall_hours": equal_gpu_hours,
        "h100_speedup_sensitivity": [
            {
                "speedup_over_local_kernel": factor,
                "wall_hours": equal_gpu_hours / factor,
            }
            for factor in (5, 10)
        ],
        "certified_input_bytes": work["input_bytes"]["total"],
        "aggregate_input_bandwidth_sensitivity": [
            {
                "aggregate_GB_per_second": bandwidth,
                "wall_hours": work["input_bytes"]["total"] / (bandwidth * 1e9) / 3600,
            }
            for bandwidth in (40, 80, 200)
        ],
        "excludes": [
            "Arb/FLINT lattice and finite-recovery generation/replay",
            "all-character transform",
            "completed-L phase and zero closure",
            "Azure orchestration, attestation, retries, and storage",
        ],
        "external_atom_discharged": False,
    }
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
