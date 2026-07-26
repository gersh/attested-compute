#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Operate the one-pass exact affine-guard Hurst campaign."""

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
    load_json,
    require_azure_measured_worker_for_workload,
)
from tg_verifier.hurst_affine_campaign import (  # noqa: E402
    CONFIG_NAME,
    DEFAULT_LOCAL_WORKERS,
    DEFAULT_SEGMENT_SIZE,
    DEFAULT_SHARD_SPAN,
    DEFAULT_WORKER_GROUPS,
    HurstAffineCampaignError,
    SOURCE_UPPER_EXCLUSIVE,
    command_for_shard,
    finalize_campaign,
    grouped_shard_indices,
    ingest_receipt,
    initialize_campaign,
    run_shards,
    verify_campaign,
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


def _guard_finite_work(output_directory: Path) -> None:
    config = load_json(
        output_directory / CONFIG_NAME, require_canonical=True
    )
    if not isinstance(config, dict):
        raise HurstAffineCampaignError("campaign config must be an object")
    lower = config.get("domain_lower")
    upper = config.get("domain_upper_exclusive")
    span = config.get("shard_span")
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in (lower, upper, span)
    ):
        raise HurstAffineCampaignError("campaign work bounds are malformed")
    assert isinstance(lower, int)
    assert isinstance(upper, int)
    assert isinstance(span, int)
    if upper <= lower or span < 1:
        raise HurstAffineCampaignError("campaign work bounds are invalid")
    require_azure_measured_worker_for_workload(
        exact_production=(
            config.get("mode") == "full_source"
            and upper == SOURCE_UPPER_EXCLUSIVE
        ),
        work_bounds=(upper - lower, min(span, upper - lower)),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one exact affine shard pass, derive all boundary states from "
            "zero, and build a conditional plan-bound certificate."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser(
        "init", help="capture identities and write the fixed affine plan"
    )
    init.add_argument("--runner", type=Path, required=True)
    init.add_argument("--runner-source", type=Path, required=True)
    init.add_argument("--upstream-manifest", type=Path, required=True)
    init.add_argument("--output-dir", type=Path, required=True)
    init.add_argument("--shard-span", type=positive, default=DEFAULT_SHARD_SPAN)
    init.add_argument(
        "--segment-size", type=positive, default=DEFAULT_SEGMENT_SIZE
    )
    init.add_argument(
        "--bounded-test-upper-exclusive",
        type=positive,
        help=(
            "explicitly create a bounded-test plan; it can never be labeled "
            "full-source"
        ),
    )

    command = commands.add_parser(
        "command", help="print one affine worker argv as JSON"
    )
    command.add_argument("output_directory", type=Path)
    command.add_argument("shard_index", type=nonnegative)

    run = commands.add_parser("run", help="run missing affine shards")
    run.add_argument("output_directory", type=Path)
    run.add_argument("--shard", type=nonnegative, action="append", dest="shards")
    run.add_argument("--worker-group-index", type=nonnegative)
    run.add_argument(
        "--worker-group-count",
        type=positive,
        default=None,
        help=(
            "partition fixed leaves into this many groups "
            f"(production: {DEFAULT_WORKER_GROUPS})"
        ),
    )
    run.add_argument("--max-shards", type=positive)
    run.add_argument("--workers", type=positive, default=DEFAULT_LOCAL_WORKERS)
    run.add_argument("--runner-threads", type=positive)
    run.add_argument("--timeout-seconds", type=positive)

    ingest = commands.add_parser(
        "ingest", help="strictly retain one externally produced affine receipt"
    )
    ingest.add_argument("output_directory", type=Path)
    ingest.add_argument("shard_index", type=nonnegative)
    ingest.add_argument("receipt", type=Path)

    finalize = commands.add_parser(
        "finalize", help="derive/replay the source-wide conditional certificate"
    )
    finalize.add_argument("output_directory", type=Path)

    verify = commands.add_parser(
        "verify", help="independently replay every retained relationship"
    )
    verify.add_argument("output_directory", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "init":
            bounded = args.bounded_test_upper_exclusive
            result: object = initialize_campaign(
                runner=args.runner,
                runner_source=args.runner_source,
                upstream_manifest=args.upstream_manifest,
                output_directory=args.output_dir,
                shard_span=args.shard_span,
                segment_size=args.segment_size,
                domain_upper_exclusive=(
                    SOURCE_UPPER_EXCLUSIVE if bounded is None else bounded
                ),
                allow_bounded_test=bounded is not None,
            ).as_json()
        elif args.command == "command":
            result = {
                "argv": list(
                    command_for_shard(
                        args.output_directory,
                        shard_index=args.shard_index,
                    )
                )
            }
        elif args.command == "run":
            _guard_finite_work(args.output_directory)
            grouped = (
                args.worker_group_index is not None
                or args.worker_group_count is not None
            )
            if grouped and (
                args.worker_group_index is None
                or args.worker_group_count is None
            ):
                raise HurstAffineCampaignError(
                    "worker group index and count must be supplied together"
                )
            if grouped and args.shards:
                raise HurstAffineCampaignError(
                    "choose explicit shards or one worker group, not both"
                )
            if grouped and args.max_shards is not None:
                raise HurstAffineCampaignError(
                    "a worker group cannot be truncated"
                )
            selected = args.shards
            if grouped:
                selected = grouped_shard_indices(
                    args.output_directory,
                    group_index=args.worker_group_index,
                    group_count=args.worker_group_count,
                )
            result = run_shards(
                args.output_directory,
                shard_indices=selected,
                max_shards=args.max_shards,
                workers=args.workers,
                runner_threads=args.runner_threads,
                timeout_seconds=args.timeout_seconds,
            ).as_json()
        elif args.command == "ingest":
            result = ingest_receipt(
                args.output_directory,
                shard_index=args.shard_index,
                receipt_path=args.receipt,
            ).as_json()
        elif args.command == "finalize":
            result = finalize_campaign(args.output_directory).as_json()
        elif args.command == "verify":
            result = verify_campaign(args.output_directory).as_json()
        else:  # pragma: no cover - argparse keeps this unreachable.
            raise AssertionError(args.command)
    except (
        CampaignIOError,
        HurstAffineCampaignError,
        OSError,
        ValueError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
