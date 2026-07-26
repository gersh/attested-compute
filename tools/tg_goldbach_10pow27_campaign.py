#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Operate the distinct finite Goldbach campaign below the 10^27 crossover."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    canonical_json_bytes,
    require_azure_measured_worker_for_workload,
)
from tg_verifier.goldbach_10pow27_campaign import (  # noqa: E402
    Goldbach10Pow27CampaignError,
    combine_branches,
    combine_optimized_branches,
    initialize_ladder,
    schedule_summary,
)
from tg_verifier.goldbach_campaign import CampaignError  # noqa: E402


def _emit(value: object, pretty: bool) -> None:
    if pretty:
        print(json.dumps(value, indent=2, sort_keys=True))
    else:
        sys.stdout.buffer.write(canonical_json_bytes(value))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan", help="print the exact UNRUN production schedule")

    initialize = commands.add_parser(
        "init-ladder", help="initialize the exact 7,106-range n=45 ladder"
    )
    initialize.add_argument("directory", type=Path)

    combine = commands.add_parser(
        "combine", help="replay and bind the complete binary and ladder aggregates"
    )
    optimized = commands.add_parser(
        "combine-optimized",
        help=(
            "replay the distinct optimized binary route and exact ladder "
            "without promoting it to the registered finalizer"
        ),
    )
    for command in (combine, optimized):
        command.add_argument("ladder_directory", type=Path)
        command.add_argument("--ladder-aggregate", type=Path, required=True)
        command.add_argument("--binary-plan", type=Path, required=True)
        command.add_argument("--binary-receipts-dir", type=Path, required=True)
        command.add_argument("--binary-aggregate", type=Path, required=True)
        command.add_argument("--general-prime-checker", type=Path)
        command.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "plan":
            result = schedule_summary()
        elif args.command == "init-ladder":
            initialize_ladder(args.directory)
            result = schedule_summary()
        else:
            # Plan and initialization are control-plane operations.  Combining
            # the terminal branches replays the source-scale ladder and binary
            # campaign, so reject it before opening any supplied artifact.
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            combiner = (
                combine_optimized_branches
                if args.command == "combine-optimized"
                else combine_branches
            )
            result = combiner(
                args.ladder_directory,
                ladder_aggregate_path=args.ladder_aggregate,
                binary_plan_path=args.binary_plan,
                binary_receipts_directory=args.binary_receipts_dir,
                binary_aggregate_path=args.binary_aggregate,
                output_path=args.out,
                external_prime_checker=args.general_prime_checker,
            )
        _emit(result, args.pretty)
        return 0
    except (
        CampaignIOError,
        Goldbach10Pow27CampaignError,
        CampaignError,
        OSError,
    ) as exc:
        print(f"Goldbach 10^27 campaign error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
