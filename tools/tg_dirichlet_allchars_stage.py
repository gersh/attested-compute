#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Inspect and generate Platt all-character Bluestein stage artifacts."""

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

from tg_verifier.dirichlet_allchars_stage import (  # noqa: E402
    capability,
    group_order,
    preparation_inventory,
    read_input_header,
    read_output_header,
    source_work,
    write_synthetic_input,
)
from tg_verifier.campaign_io import (  # noqa: E402
    MeasuredWorkerScopeError,
    require_azure_measured_worker_for_workload,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("capability")
    work = commands.add_parser("source-work")
    work.add_argument("--batch-size", type=int, default=64)
    commands.add_parser("preparation-inventory")
    synthetic = commands.add_parser("synthetic-input")
    synthetic.add_argument("path", type=Path)
    synthetic.add_argument("--q", type=int, required=True)
    synthetic.add_argument("--t-index", type=int, default=0)
    synthetic.add_argument("--batch-count", type=int, default=1)
    inspect_input = commands.add_parser("inspect-input")
    inspect_input.add_argument("path", type=Path)
    inspect_output = commands.add_parser("inspect-output")
    inspect_output.add_argument("path", type=Path)
    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--runner", type=Path, required=True)
    benchmark.add_argument("--q", type=int, default=400_000)
    benchmark.add_argument("--batch-count", type=int, default=64)
    benchmark.add_argument("--iterations", type=int, default=3)
    benchmark.add_argument("--device", type=int, default=0)
    kat = commands.add_parser("kat")
    kat.add_argument("--runner", type=Path, required=True)
    kat.add_argument("--checker", type=Path, required=True)
    kat.add_argument("--device", type=int, default=0)
    args = parser.parse_args()

    try:
        if args.command == "synthetic-input":
            value_count = args.batch_count * group_order(args.q)
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(value_count,),
            )
        elif args.command == "benchmark":
            value_count = (
                args.batch_count * group_order(args.q) * args.iterations
            )
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(value_count,),
            )
        elif args.command == "kat":
            # This command has a fixed, repository-owned known-answer roster.
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(1,),
            )
    except MeasuredWorkerScopeError as error:
        print(f"tg_dirichlet_allchars_stage: {error}", file=sys.stderr)
        return 2

    if args.command == "capability":
        result = capability()
    elif args.command == "preparation-inventory":
        result = preparation_inventory()
    elif args.command == "source-work":
        result = source_work(batch_size=args.batch_size)
    elif args.command == "synthetic-input":
        result = write_synthetic_input(
            args.path,
            q=args.q,
            t_index=args.t_index,
            batch_count=args.batch_count,
        )
    elif args.command == "inspect-input":
        result = read_input_header(args.path)
    elif args.command == "inspect-output":
        result = read_output_header(args.path)
    elif args.command == "benchmark":
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "input.bin"
            output_path = root / "output.bin"
            write_synthetic_input(
                input_path,
                q=args.q,
                t_index=4_000,
                batch_count=args.batch_count,
            )
            completed = subprocess.run(
                [
                    str(args.runner.resolve()),
                    str(input_path),
                    str(output_path),
                    str(args.device),
                    str(args.iterations),
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            runner = json.loads(completed.stdout.strip().splitlines()[-1])
            seconds = runner["elapsed_nanoseconds"] / 1_000_000_000
            preparation_seconds = (
                runner["preparation_nanoseconds"] / 1_000_000_000
            )
            result = {
                "kind": "sparkinterval.tg.dirichlet_allchars.benchmark.v1",
                "measurement_scope": (
                    "q-specific synthetic interval transform; transform rate "
                    "excludes separately reported one-time persistent-q MPFR "
                    "twiddle construction and CUDA allocation"
                ),
                "q": args.q,
                "batch_count": args.batch_count,
                "iterations": args.iterations,
                "group_values": runner["value_count"],
                "radix2_butterflies": runner["radix2_butterflies"],
                "elapsed_seconds": seconds,
                "persistent_q_preparation_seconds": preparation_seconds,
                "cold_effective_seconds_per_iteration": (
                    seconds + preparation_seconds / args.iterations
                ),
                "group_values_per_second": runner["value_count"] / seconds,
                "radix2_butterflies_per_second": (
                    runner["radix2_butterflies"] / seconds
                ),
                "runner": runner,
            }
    else:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "tests" / "tg_dirichlet_allchars_known_answers.py"),
                "--runner",
                str(args.runner.resolve()),
                "--checker",
                str(args.checker.resolve()),
                "--device",
                str(args.device),
            ],
            check=True,
        )
        result = {
            "kind": "sparkinterval.tg.dirichlet_allchars.kat.v1",
            "status": "pass",
        }
    print(json.dumps(result, sort_keys=True, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
