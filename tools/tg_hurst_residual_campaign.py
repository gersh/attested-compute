#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Operate the two-pass source-scale Hurst residual campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.hurst_residual_campaign import (  # noqa: E402
    CONFIG_NAME,
    DEFAULT_LOCAL_WORKERS,
    DEFAULT_SEGMENT_SIZE,
    DEFAULT_SHARD_SPAN,
    DEFAULT_WORKER_GROUPS,
    HurstResidualCampaignError,
    SOURCE_UPPER_EXCLUSIVE,
    command_for_shard,
    finalize_campaign,
    grouped_shard_indices,
    ingest_receipt,
    initialize_campaign,
    reduce_summaries,
    run_phase,
    verify_campaign,
    write_registered_result,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    load_json,
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


def _add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("output_directory", type=Path)


def _guard_finite_work(output_directory: Path) -> None:
    """Reject source-scale arithmetic before opening runner or receipt data."""

    config = load_json(output_directory / CONFIG_NAME, require_canonical=True)
    if not isinstance(config, dict):
        raise HurstResidualCampaignError("campaign config must be an object")
    lower = config.get("domain_lower")
    upper = config.get("domain_upper_exclusive")
    span = config.get("shard_span")
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in (lower, upper, span)
    ):
        raise HurstResidualCampaignError("campaign work bounds are malformed")
    assert isinstance(lower, int) and isinstance(upper, int)
    assert isinstance(span, int)
    if upper <= lower or span < 1:
        raise HurstResidualCampaignError("campaign work bounds are invalid")
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
            "Run/ingest exact summary shards, derive the four prefix states, "
            "rerun verify shards, and build a plan-bound affine/Merkle certificate."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="capture identities and write the fixed plan")
    init.add_argument("--runner", type=Path, required=True)
    init.add_argument("--runner-source", type=Path, required=True)
    init.add_argument("--upstream-manifest", type=Path, required=True)
    init.add_argument("--output-dir", type=Path, required=True)
    init.add_argument("--shard-span", type=positive, default=DEFAULT_SHARD_SPAN)
    init.add_argument("--segment-size", type=positive, default=DEFAULT_SEGMENT_SIZE)
    init.add_argument(
        "--bounded-test-upper-exclusive",
        type=positive,
        help=(
            "explicitly create a bounded-test plan instead of [1,10^16+1); "
            "its certificate can never be labeled full-source"
        ),
    )

    command = commands.add_parser("command", help="print one worker argv as JSON")
    _add_output(command)
    command.add_argument("phase", choices=("summary", "verify"))
    command.add_argument("shard_index", type=nonnegative)

    run = commands.add_parser("run", help="locally run missing shards in one phase")
    _add_output(run)
    run.add_argument("phase", choices=("summary", "verify"))
    run.add_argument("--shard", type=nonnegative, action="append", dest="shards")
    run.add_argument("--worker-group-index", type=nonnegative)
    run.add_argument(
        "--worker-group-count",
        type=positive,
        default=None,
        help=f"partition the fixed leaf plan into this many groups (production: {DEFAULT_WORKER_GROUPS})",
    )
    run.add_argument("--max-shards", type=positive)
    run.add_argument(
        "--workers",
        type=positive,
        default=DEFAULT_LOCAL_WORKERS,
        help=(
            "maximum concurrent shard processes; each concurrent child "
            "defaults to one OpenMP thread"
        ),
    )
    run.add_argument(
        "--runner-threads",
        type=positive,
        help=(
            "OpenMP threads per shard process (default: inherit for one "
            "worker, one thread per child for multiple workers)"
        ),
    )
    run.add_argument("--timeout-seconds", type=positive)

    ingest = commands.add_parser("ingest", help="check and retain one cluster receipt")
    _add_output(ingest)
    ingest.add_argument("phase", choices=("summary", "verify"))
    ingest.add_argument("shard_index", type=nonnegative)
    ingest.add_argument("receipt", type=Path)

    reduce = commands.add_parser("reduce", help="derive all phase-two prefix inputs")
    _add_output(reduce)

    finalize = commands.add_parser("finalize", help="build and replay the final certificate")
    _add_output(finalize)

    verify = commands.add_parser("verify", help="audit every retained relationship")
    _add_output(verify)
    verify.add_argument(
        "--registered-result-output",
        type=Path,
        help=(
            "exclusively write the closed-registry literal true only after a "
            "complete full-source replay"
        ),
    )
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
                        phase=args.phase,
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
                raise HurstResidualCampaignError(
                    "worker group index and count must be supplied together"
                )
            if grouped and args.shards:
                raise HurstResidualCampaignError(
                    "choose explicit shards or one worker group, not both"
                )
            if grouped and args.max_shards is not None:
                raise HurstResidualCampaignError(
                    "a worker group cannot be truncated with --max-shards"
                )
            selected = args.shards
            if grouped:
                selected = grouped_shard_indices(
                    args.output_directory,
                    group_index=args.worker_group_index,
                    group_count=args.worker_group_count,
                )
            result = run_phase(
                args.output_directory,
                phase=args.phase,
                shard_indices=selected,
                max_shards=args.max_shards,
                workers=args.workers,
                runner_threads=args.runner_threads,
                timeout_seconds=args.timeout_seconds,
            ).as_json()
        elif args.command == "ingest":
            result = ingest_receipt(
                args.output_directory,
                phase=args.phase,
                shard_index=args.shard_index,
                receipt_path=args.receipt,
            ).as_json()
        elif args.command == "reduce":
            _guard_finite_work(args.output_directory)
            result = reduce_summaries(args.output_directory)
        elif args.command == "finalize":
            _guard_finite_work(args.output_directory)
            result = finalize_campaign(args.output_directory).as_json()
        else:
            _guard_finite_work(args.output_directory)
            if args.registered_result_output is None:
                result = verify_campaign(args.output_directory).as_json()
            else:
                checked, artifact = write_registered_result(
                    args.output_directory,
                    args.registered_result_output,
                )
                result = checked.as_json()
                result["registered_result_artifact"] = artifact
    except (CampaignIOError, HurstResidualCampaignError) as exc:
        print(f"Hurst residual campaign error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
