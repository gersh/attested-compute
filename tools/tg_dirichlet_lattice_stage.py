#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Plan, exercise, and receipt Platt's conditional large-q Taylor stage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_lattice_stage import (  # noqa: E402
    DirichletLatticeStageError,
    LATTICE_ROWS,
    TAYLOR_COLUMNS,
    benchmark_projection,
    inspect_input,
    run_batch,
    source_plan,
    write_synthetic_input,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


def _positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def _nonnegative(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return value


def _emit(value: object, pretty: bool) -> None:
    print(
        json.dumps(
            value,
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser("plan", help="emit the exact fixed source plan")
    plan.add_argument("--shards", type=_positive, default=8)

    synthetic = commands.add_parser(
        "synthetic-input", help="write a labeled non-zeta conformance input"
    )
    synthetic.add_argument("output", type=Path)
    synthetic.add_argument("--q-start", type=_positive, required=True)
    synthetic.add_argument("--q-stop", type=_positive, required=True)
    synthetic.add_argument("--t-index", type=_nonnegative, default=0)
    synthetic.add_argument("--max-items", type=_positive)

    inspect = commands.add_parser("inspect-input")
    inspect.add_argument("input", type=Path)

    run = commands.add_parser(
        "run-batch", help="run one immutable conditional arithmetic batch"
    )
    run.add_argument("root", type=Path)
    run.add_argument("--input", type=Path, required=True)
    run.add_argument("--runner", type=Path, required=True)
    run.add_argument("--checker", type=Path, required=True)
    run.add_argument("--device", type=_nonnegative, default=0)
    choice = run.add_mutually_exclusive_group(required=True)
    choice.add_argument("--synthetic-lattice", action="store_true")
    choice.add_argument("--lattice-certificate", type=Path)
    run.add_argument("--timeout", type=float)

    projection = commands.add_parser(
        "project", help="project only the measured Taylor stage to H100s"
    )
    projection.add_argument("--items-per-second", type=float, required=True)
    projection.add_argument("--h100-speedup-low", type=float, default=1.0)
    projection.add_argument("--h100-speedup-high", type=float, default=14.3)
    projection.add_argument("--h100-count", type=_positive, default=8)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = source_plan(shard_count=args.shards)
        elif args.command == "synthetic-input":
            require_azure_measured_worker_for_workload(
                exact_production=args.max_items is None,
                work_bounds=(
                    ()
                    if args.max_items is None
                    else (
                        args.max_items
                        * LATTICE_ROWS
                        * TAYLOR_COLUMNS,
                    )
                ),
            )
            result = write_synthetic_input(
                args.output,
                q_start=args.q_start,
                q_stop=args.q_stop,
                t_index=args.t_index,
                max_items=args.max_items,
            )
        elif args.command == "inspect-input":
            result = inspect_input(args.input)
        elif args.command == "run-batch":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            result = run_batch(
                args.root,
                input_path=args.input,
                runner=args.runner,
                checker=args.checker,
                device=args.device,
                lattice_certificate=args.lattice_certificate,
                synthetic_lattice=args.synthetic_lattice,
                timeout=args.timeout,
            )
        elif args.command == "project":
            result = benchmark_projection(
                items_per_second=args.items_per_second,
                h100_speedup_low=args.h100_speedup_low,
                h100_speedup_high=args.h100_speedup_high,
                h100_count=args.h100_count,
            )
        else:  # pragma: no cover
            parser.error("unknown command")
        _emit(result, args.pretty)
        return 0
    except (DirichletLatticeStageError, OSError, ValueError) as error:
        print(f"tg_dirichlet_lattice_stage: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
