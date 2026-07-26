#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Operate the pinned Platt PT21 high-range windowed zeta campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)
from tg_verifier.platt_windowed_campaign import (  # noqa: E402
    DEFAULT_BLOCKS_PER_SHARD,
    FULL_BLOCK_COUNT,
    STEP,
    PlattWindowedCampaignError,
    campaign_status,
    finalize_campaign,
    initialize_campaign,
    load_plan,
    replay_shard,
    run_shard,
    shard_block_range,
)


def positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def nonnegative(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return value


def emit(value: object, pretty: bool) -> None:
    print(json.dumps(value, sort_keys=True, indent=2 if pretty else None))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pretty", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("directory", type=Path)
    init.add_argument("--runner", type=Path, required=True)
    init.add_argument(
        "--source-manifest",
        type=Path,
        default=ROOT / "specifications" / "PLATT_PT21_WINDOWED_UPSTREAM.json",
    )
    init.add_argument(
        "--blocks-per-shard", type=positive, default=DEFAULT_BLOCKS_PER_SHARD
    )
    init.add_argument("--block-count", type=positive, default=FULL_BLOCK_COUNT)
    init.add_argument("--allow-bounded-test", action="store_true")

    for name in ("run-shard", "replay-shard"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
        command.add_argument("index", type=nonnegative)
        command.add_argument("--runner", type=Path, required=True)
        command.add_argument("--timeout-seconds", type=positive)

    for name in ("status", "finalize"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)

    range_command = commands.add_parser("range")
    range_command.add_argument("directory", type=Path)
    range_command.add_argument("index", type=nonnegative)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            require_azure_measured_worker_for_workload(
                exact_production=not args.allow_bounded_test,
                work_bounds=(args.block_count * STEP,),
            )
            value = initialize_campaign(
                output_directory=args.directory,
                runner=args.runner,
                source_manifest=args.source_manifest,
                blocks_per_shard=args.blocks_per_shard,
                block_count=args.block_count,
                allow_bounded_test=args.allow_bounded_test,
            )
        elif args.command == "run-shard":
            plan = load_plan(args.directory)
            first, upper = shard_block_range(plan, args.index)
            require_azure_measured_worker_for_workload(
                exact_production=plan["mode"] != "bounded_test",
                work_bounds=(
                    (upper - first) * plan["configuration"]["step"],
                ),
            )
            value = run_shard(
                args.directory,
                args.runner,
                args.index,
                timeout_seconds=args.timeout_seconds,
            )
        elif args.command == "replay-shard":
            plan = load_plan(args.directory)
            first, upper = shard_block_range(plan, args.index)
            require_azure_measured_worker_for_workload(
                exact_production=plan["mode"] != "bounded_test",
                work_bounds=(
                    (upper - first) * plan["configuration"]["step"],
                ),
            )
            value = replay_shard(
                args.directory,
                args.runner,
                args.index,
                timeout_seconds=args.timeout_seconds,
            )
        elif args.command == "status":
            value = campaign_status(args.directory)
        elif args.command == "finalize":
            plan = load_plan(args.directory)
            require_azure_measured_worker_for_workload(
                exact_production=plan["mode"] != "bounded_test",
                work_bounds=(
                    plan["geometry"]["block_count"]
                    * plan["configuration"]["step"],
                ),
            )
            value = finalize_campaign(args.directory)
        elif args.command == "range":
            plan = load_plan(args.directory)
            first, upper = shard_block_range(plan, args.index)
            value = {
                "accepted": True,
                "shard_index": args.index,
                "first_block": first,
                "upper_block_exclusive": upper,
                "block_count": upper - first,
                "height_lower": plan["claim"]["windowed_lower"]
                + first * plan["configuration"]["step"],
                "height_upper": plan["claim"]["windowed_lower"]
                + upper * plan["configuration"]["step"],
            }
        else:
            raise AssertionError("unreachable command")
    except (OSError, ValueError, PlattWindowedCampaignError) as error:
        emit(
            {
                "accepted": False,
                "classification": "platt-pt21-windowed-campaign-failed-closed",
                "error": str(error),
                "execution_attested": False,
                "lean_atom_discharged": False,
            },
            args.pretty,
        )
        return 2
    emit(value, args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
