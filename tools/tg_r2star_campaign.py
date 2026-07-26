#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run, structurally audit, or independently replay an R2Star campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.r2star_campaign import (  # noqa: E402
    DEFAULT_ARITHMETIC_REPLAY_SEGMENT_ROWS,
    R2StarCampaignError,
    run_campaign,
    verify_campaign,
    verify_campaign_arithmetic,
    write_registered_result,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    require_azure_measured_worker_for_workload,
)


def positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def nonnegative(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="start or resume the full campaign")
    run.add_argument("--runner", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--segment-count", type=positive, default=1_000_000)
    run.add_argument("--device", type=nonnegative, default=0)
    run.add_argument("--allow-other-device", action="store_true")
    run.add_argument("--cross-check-serial", action="store_true")
    run.add_argument("--max-chunks", type=positive)
    run.add_argument("--chunk-timeout-seconds", type=positive)
    run.add_argument("--arithmetic-replayer", type=Path)
    run.add_argument("--replay-threads", type=positive, default=32)
    run.add_argument(
        "--replay-segment-rows",
        type=nonnegative,
        default=DEFAULT_ARITHMETIC_REPLAY_SEGMENT_ROWS,
        help="parallel replay segment rows; use 0 for the serial reference",
    )
    run.add_argument("--replay-timeout-seconds", type=positive)
    run.add_argument("--registered-result-output", type=Path)
    verify = subcommands.add_parser("verify", help="audit a retained campaign")
    verify.add_argument("output_dir", type=Path)
    arithmetic = subcommands.add_parser(
        "verify-arithmetic",
        help="recompute every retained row with the CPU-only checker",
    )
    arithmetic.add_argument("output_dir", type=Path)
    arithmetic.add_argument(
        "--arithmetic-replayer", type=Path, required=True
    )
    arithmetic.add_argument("--replay-threads", type=positive, default=32)
    arithmetic.add_argument(
        "--replay-segment-rows",
        type=nonnegative,
        default=DEFAULT_ARITHMETIC_REPLAY_SEGMENT_ROWS,
        help="parallel replay segment rows; use 0 for the serial reference",
    )
    arithmetic.add_argument("--replay-timeout-seconds", type=positive)
    arithmetic.add_argument("--registered-result-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            if (args.arithmetic_replayer is None) != (
                args.registered_result_output is None
            ):
                raise R2StarCampaignError(
                    "run requires both --arithmetic-replayer and "
                    "--registered-result-output, or neither"
                )
            require_azure_measured_worker_for_workload(
                exact_production=(
                    args.max_chunks is None
                    or args.registered_result_output is not None
                ),
                work_bounds=(
                    args.segment_count,
                    0 if args.max_chunks is None else args.max_chunks,
                ),
            )
            result = run_campaign(
                runner=args.runner,
                output_directory=args.output_dir,
                segment_count=args.segment_count,
                device=args.device,
                allow_other_device=args.allow_other_device,
                cross_check_serial=args.cross_check_serial,
                max_chunks=args.max_chunks,
                chunk_timeout_seconds=args.chunk_timeout_seconds,
            )
            output_directory = args.output_dir
        elif args.command == "verify":
            result = verify_campaign(args.output_dir)
            output_directory = args.output_dir
        else:
            # This command recomputes every retained source row.  Tiny
            # arithmetic KATs use the replay program's explicit <=64
            # benchmark mode instead of this unbounded campaign entry point.
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            output_directory = args.output_dir
            if args.registered_result_output is None:
                result = verify_campaign_arithmetic(
                    args.output_dir,
                    arithmetic_replayer=args.arithmetic_replayer,
                    replay_threads=args.replay_threads,
                    replay_segment_rows=(
                        None
                        if args.replay_segment_rows == 0
                        else args.replay_segment_rows
                    ),
                    replay_timeout_seconds=args.replay_timeout_seconds,
                )
            else:
                result, artifact = write_registered_result(
                    output_directory,
                    args.registered_result_output,
                    arithmetic_replayer=args.arithmetic_replayer,
                    replay_threads=args.replay_threads,
                    replay_segment_rows=(
                        None
                        if args.replay_segment_rows == 0
                        else args.replay_segment_rows
                    ),
                    replay_timeout_seconds=args.replay_timeout_seconds,
                )
        payload = result.as_json()
        if args.command == "run" and args.registered_result_output is not None:
            checked, artifact = write_registered_result(
                output_directory,
                args.registered_result_output,
                arithmetic_replayer=args.arithmetic_replayer,
                replay_threads=args.replay_threads,
                replay_segment_rows=(
                    None
                    if args.replay_segment_rows == 0
                    else args.replay_segment_rows
                ),
                replay_timeout_seconds=args.replay_timeout_seconds,
            )
            payload = checked.as_json()
            payload["registered_result_artifact"] = artifact
        elif (
            args.command == "verify-arithmetic"
            and args.registered_result_output is not None
        ):
            payload["registered_result_artifact"] = artifact
    except (CampaignIOError, R2StarCampaignError) as exc:
        print(f"R2Star campaign error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
