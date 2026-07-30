#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Operate the preemption-tolerant Platt PT21 windowed work-unit schedule."""

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
from tg_verifier.platt_windowed_scheduler import (  # noqa: E402
    DEFAULT_BLOCKS_PER_UNIT,
    DEFAULT_CHECKPOINT_BLOCKS,
    DEFAULT_LEASE_SECONDS,
    DEFAULT_UNITS_PER_SHARD,
    PlattWindowedPreempted,
    PlattWindowedScheduleError,
    default_worker_id,
    finalize,
    height_of_block,
    initialize_schedule,
    load_schedule,
    next_unit,
    release_unit,
    replay_unit,
    run_unit,
    seal_shard,
    shard_unit_range,
    status,
    unit_block_range,
)
from tg_verifier.platt_windowed_campaign import FULL_BLOCK_COUNT  # noqa: E402


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
    init.add_argument("--blocks-per-unit", type=positive, default=DEFAULT_BLOCKS_PER_UNIT)
    init.add_argument("--units-per-shard", type=positive, default=DEFAULT_UNITS_PER_SHARD)
    init.add_argument("--block-count", type=positive, default=FULL_BLOCK_COUNT)
    init.add_argument("--allow-bounded-test", action="store_true")

    run = commands.add_parser("run-unit")
    run.add_argument("directory", type=Path)
    run.add_argument("index", type=nonnegative)
    run.add_argument("--runner", type=Path, required=True)
    run.add_argument("--checkpoint-blocks", type=positive, default=DEFAULT_CHECKPOINT_BLOCKS)
    run.add_argument("--retain-log", action="store_true")
    run.add_argument("--no-resume", action="store_true")
    run.add_argument("--timeout-seconds", type=positive)

    work = commands.add_parser("work")
    work.add_argument("directory", type=Path)
    work.add_argument("--runner", type=Path, required=True)
    work.add_argument("--worker-id", default=None)
    work.add_argument("--max-units", type=positive, default=1)
    work.add_argument("--from-shard", type=nonnegative, default=0)
    work.add_argument("--stride", type=positive, default=1)
    work.add_argument("--offset", type=nonnegative, default=0)
    work.add_argument("--lease-seconds", type=positive, default=DEFAULT_LEASE_SECONDS)
    work.add_argument("--checkpoint-blocks", type=positive, default=DEFAULT_CHECKPOINT_BLOCKS)
    work.add_argument("--retain-log", action="store_true")
    work.add_argument("--seal-when-complete", action="store_true")

    replay = commands.add_parser("replay-unit")
    replay.add_argument("directory", type=Path)
    replay.add_argument("index", type=nonnegative)
    replay.add_argument("--runner", type=Path, required=True)
    replay.add_argument("--timeout-seconds", type=positive)

    seal = commands.add_parser("seal-shard")
    seal.add_argument("directory", type=Path)
    seal.add_argument("index", type=nonnegative)
    seal.add_argument("--prune-units", action="store_true")

    final = commands.add_parser("finalize")
    final.add_argument("directory", type=Path)
    final.add_argument("--prefix-receipt", type=Path)

    state = commands.add_parser("status")
    state.add_argument("directory", type=Path)
    state.add_argument("--sample-shards", type=positive)

    where = commands.add_parser("range")
    where.add_argument("directory", type=Path)
    where.add_argument("index", type=nonnegative)
    where.add_argument("--shard", action="store_true")
    return result


def _unit_workload(directory: Path, index: int) -> tuple[int, ...]:
    """Finite workload declared to the measured-worker scope guard.

    The bound is a count of logical blocks, matching the guard's documented
    "counts or spans, never absolute mathematical endpoints" contract.  A
    bounded local known-answer schedule of at most 64 blocks therefore runs
    without a measured Azure child; anything larger does not.
    """

    schedule = load_schedule(directory)
    first, upper = unit_block_range(schedule, index)
    return (upper - first,)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            require_azure_measured_worker_for_workload(
                exact_production=not args.allow_bounded_test,
                work_bounds=(args.block_count,),
            )
            value = initialize_schedule(
                output_directory=args.directory,
                runner=args.runner,
                source_manifest=args.source_manifest,
                blocks_per_unit=args.blocks_per_unit,
                units_per_shard=args.units_per_shard,
                block_count=args.block_count,
                allow_bounded_test=args.allow_bounded_test,
            )
        elif args.command == "run-unit":
            schedule = load_schedule(args.directory)
            require_azure_measured_worker_for_workload(
                exact_production=schedule["mode"] != "bounded_test",
                work_bounds=_unit_workload(args.directory, args.index),
            )
            value = run_unit(
                args.directory,
                args.runner,
                args.index,
                checkpoint_blocks=args.checkpoint_blocks,
                retain_log=args.retain_log,
                timeout_seconds=args.timeout_seconds,
                resume=not args.no_resume,
            )
        elif args.command == "work":
            schedule = load_schedule(args.directory)
            worker_id = args.worker_id or default_worker_id()
            completed: list[dict[str, object]] = []
            sealed: list[int] = []
            while len(completed) < args.max_units:
                unit = next_unit(
                    args.directory,
                    schedule,
                    worker_id=worker_id,
                    lease_seconds=args.lease_seconds,
                    from_shard=args.from_shard,
                    stride=args.stride,
                    offset=args.offset,
                )
                if unit is None:
                    break
                require_azure_measured_worker_for_workload(
                    exact_production=schedule["mode"] != "bounded_test",
                    work_bounds=_unit_workload(args.directory, unit),
                )
                try:
                    receipt = run_unit(
                        args.directory,
                        args.runner,
                        unit,
                        checkpoint_blocks=args.checkpoint_blocks,
                        retain_log=args.retain_log,
                    )
                except PlattWindowedPreempted as preemption:
                    release_unit(args.directory, unit)
                    emit(
                        {
                            "accepted": False,
                            "classification": "platt-pt21-windowed-unit-preempted",
                            "worker_id": worker_id,
                            "unit_index": unit,
                            "detail": str(preemption),
                            "completed_units": [
                                row["unit_index"] for row in completed
                            ],
                            "resume_supported": True,
                        },
                        args.pretty,
                    )
                    return 3
                completed.append(
                    {
                        "unit_index": receipt["unit_index"],
                        "unit_sha256": receipt["unit_sha256"],
                        "total_zero_count": receipt["total_zero_count"],
                    }
                )
            if args.seal_when_complete:
                shards = sorted({int(row["unit_index"]) for row in completed})
                seen: set[int] = set()
                for unit_index in shards:
                    shard = unit_index // schedule["configuration"]["units_per_shard"]
                    if shard in seen:
                        continue
                    seen.add(shard)
                    try:
                        seal_shard(args.directory, shard)
                        sealed.append(shard)
                    except PlattWindowedScheduleError:
                        pass
            value = {
                "accepted": True,
                "worker_id": worker_id,
                "completed_units": completed,
                "sealed_shards": sealed,
                "exhausted": len(completed) < args.max_units,
                "execution_attested": False,
                "lean_atom_discharged": False,
            }
        elif args.command == "replay-unit":
            schedule = load_schedule(args.directory)
            require_azure_measured_worker_for_workload(
                exact_production=schedule["mode"] != "bounded_test",
                work_bounds=_unit_workload(args.directory, args.index),
            )
            value = replay_unit(
                args.directory,
                args.runner,
                args.index,
                timeout_seconds=args.timeout_seconds,
            )
        elif args.command == "seal-shard":
            value = seal_shard(
                args.directory, args.index, prune_units=args.prune_units
            )
        elif args.command == "finalize":
            value = finalize(args.directory, prefix_receipt=args.prefix_receipt)
        elif args.command == "status":
            value = status(args.directory, sample_shards=args.sample_shards)
        elif args.command == "range":
            schedule = load_schedule(args.directory)
            if args.shard:
                first_unit, upper_unit = shard_unit_range(schedule, args.index)
                first_block, _ = unit_block_range(schedule, first_unit)
                _, upper_block = unit_block_range(schedule, upper_unit - 1)
                value = {
                    "accepted": True,
                    "shard_index": args.index,
                    "first_unit": first_unit,
                    "upper_unit_exclusive": upper_unit,
                    "first_block": first_block,
                    "upper_block_exclusive": upper_block,
                    "height_lower": height_of_block(first_block),
                    "height_upper": height_of_block(upper_block),
                }
            else:
                first, upper = unit_block_range(schedule, args.index)
                value = {
                    "accepted": True,
                    "unit_index": args.index,
                    "shard_index": (
                        args.index // schedule["configuration"]["units_per_shard"]
                    ),
                    "first_block": first,
                    "upper_block_exclusive": upper,
                    "block_count": upper - first,
                    "height_lower": height_of_block(first),
                    "height_upper": height_of_block(upper),
                }
        else:
            raise AssertionError("unreachable command")
    except PlattWindowedPreempted as preemption:
        emit(
            {
                "accepted": False,
                "classification": "platt-pt21-windowed-unit-preempted",
                "detail": str(preemption),
                "resume_supported": True,
                "execution_attested": False,
                "lean_atom_discharged": False,
            },
            args.pretty,
        )
        return 3
    except (OSError, ValueError, PlattWindowedScheduleError) as error:
        emit(
            {
                "accepted": False,
                "classification": "platt-pt21-windowed-schedule-failed-closed",
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
