#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Operate the fixed-index FLINT Platt zeta-RH campaign."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.platt_zeta_campaign import (  # noqa: E402
    COUNT_NAME,
    DEFAULT_FLINT_THREADS,
    DEFAULT_MICRO_BATCH,
    DEFAULT_PRECISION_BITS,
    DEFAULT_SHARD_SPAN,
    FINAL_NAME,
    PLAN_NAME,
    PLATT_FIRST_INDEX,
    PREFIX_NAME,
    SHARD_DIRECTORY,
    SOURCE_UPPER_EXCLUSIVE,
    PlattZetaCampaignError,
    campaign_status,
    finalize_campaign,
    initialize_campaign,
    replay_shard,
    run_count,
    run_prefix,
    run_shard,
    shard_range,
    validate_plan,
)
from tg_verifier.campaign_io import (  # noqa: E402
    load_json,
    require_azure_measured_worker_for_workload,
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


def _write_registered_result(path: Path) -> None:
    """Create literal ``true`` once, after source-scale finalization succeeds."""

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    for optional in ("O_CLOEXEC", "O_NOFOLLOW"):
        flags |= getattr(os, optional, 0)
    descriptor = os.open(path, flags, 0o400)
    try:
        raw = b"true"
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short registered-result write")
            view = view[written:]
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def _load_plan_metadata(directory: Path) -> dict[str, object]:
    value = load_json(directory / PLAN_NAME, require_canonical=True)
    if not isinstance(value, dict):
        raise PlattZetaCampaignError("campaign plan must be an object")
    return validate_plan(value)


def _guard_finite_work(args: argparse.Namespace) -> None:
    """Guard arithmetic/replay after reading only the immutable plan."""

    if args.command in ("init", "range"):
        return
    plan = _load_plan_metadata(args.directory)
    source = plan["source"]
    assert isinstance(source, dict)
    upper = source["source_upper_exclusive"]
    assert isinstance(upper, int)
    total_work = upper - PLATT_FIRST_INDEX

    if args.command == "status":
        retained = (
            (args.directory / COUNT_NAME).exists()
            or (args.directory / PREFIX_NAME).exists()
            or (args.directory / FINAL_NAME).exists()
            or any(
                (args.directory / SHARD_DIRECTORY).glob("receipt-*.json")
            )
        )
        if not retained:
            return
        work_bounds = (total_work,)
    elif args.command in ("run-shard", "replay-shard"):
        lower, shard_upper = shard_range(plan, args.index)
        work_bounds = (shard_upper - lower,)
    else:
        work_bounds = (total_work,)
    require_azure_measured_worker_for_workload(
        exact_production=plan.get("mode") == "full_source",
        work_bounds=work_bounds,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("directory", type=Path)
    init.add_argument("--runner", type=Path, required=True)
    init.add_argument(
        "--runner-source",
        type=Path,
        default=ROOT / "reference" / "tg_platt_zeta_shard.cpp",
    )
    init.add_argument(
        "--upstream-manifest",
        type=Path,
        default=ROOT / "specifications" / "FLINT_3_6_PLATT_UPSTREAM.json",
    )
    init.add_argument("--shard-span", type=positive, default=DEFAULT_SHARD_SPAN)
    init.add_argument("--micro-batch", type=positive, default=DEFAULT_MICRO_BATCH)
    init.add_argument("--precision-bits", type=positive, default=DEFAULT_PRECISION_BITS)
    init.add_argument("--flint-threads", type=positive, default=DEFAULT_FLINT_THREADS)
    init.add_argument(
        "--source-upper-exclusive", type=positive, default=SOURCE_UPPER_EXCLUSIVE
    )
    init.add_argument("--allow-bounded-test", action="store_true")

    for name in ("count", "prefix", "status", "finalize"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
        if name == "finalize":
            command.add_argument(
                "--registered-result-output",
                type=Path,
                help=(
                    "exclusively create literal `true` after the complete "
                    "fixed-index campaign has finalized"
                ),
            )

    run = commands.add_parser("run-shard")
    run.add_argument("directory", type=Path)
    run.add_argument("index", type=nonnegative)

    replay = commands.add_parser("replay-shard")
    replay.add_argument("directory", type=Path)
    replay.add_argument("index", type=nonnegative)
    replay.add_argument(
        "--refined",
        action="store_true",
        help="audit up to 100 rows with acb_dirichlet_platt_zeta_zeros",
    )

    range_command = commands.add_parser("range")
    range_command.add_argument("directory", type=Path)
    range_command.add_argument("index", type=nonnegative)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _guard_finite_work(args)
        if args.command == "init":
            result = initialize_campaign(
                runner=args.runner,
                runner_source=args.runner_source,
                upstream_manifest=args.upstream_manifest,
                output_directory=args.directory,
                shard_span=args.shard_span,
                micro_batch=args.micro_batch,
                precision_bits=args.precision_bits,
                flint_threads=args.flint_threads,
                source_upper_exclusive=args.source_upper_exclusive,
                allow_bounded_test=args.allow_bounded_test,
            )
        elif args.command == "count":
            result = run_count(args.directory)
        elif args.command == "prefix":
            result = run_prefix(args.directory)
        elif args.command == "run-shard":
            result = run_shard(args.directory, args.index)
        elif args.command == "replay-shard":
            result = replay_shard(args.directory, args.index, refined=args.refined)
        elif args.command == "status":
            result = campaign_status(args.directory)
        elif args.command == "finalize":
            result = finalize_campaign(args.directory)
            if args.registered_result_output is not None:
                if (
                    result.get("mode") != "full_source"
                    or result.get("shard_count") != 1_236_316
                    or result.get("retained_shards") != 1_236_316
                    or result.get("count_ready") is not True
                    or result.get("prefix_ready") is not True
                    or result.get("complete") is not True
                    or result.get("final_ready") is not True
                ):
                    raise PlattZetaCampaignError(
                        "registered PT21 output requires the exact complete "
                        "full-source campaign"
                    )
                _write_registered_result(args.registered_result_output)
        elif args.command == "range":
            plan = _load_plan_metadata(args.directory)
            lower, upper = shard_range(plan, args.index)
            result = {
                "index": args.index,
                "first_index": lower,
                "upper_exclusive": upper,
                "record_count": upper - lower,
            }
        else:
            raise AssertionError("unreachable command")
    except (PlattZetaCampaignError, OSError, ValueError) as error:
        emit(
            {
                "accepted": False,
                "classification": "platt-zeta-campaign-failed-closed",
                "error": str(error),
                "lean_atom_discharged": False,
            },
            args.pretty,
        )
        return 2
    emit(result, args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
