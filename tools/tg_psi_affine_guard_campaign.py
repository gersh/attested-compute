#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Operate the fail-closed one-pass CH25 psi affine campaign."""

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
from tg_verifier.psi_affine_guard_campaign import (  # noqa: E402
    CONFIG_NAME,
    DEFAULT_SHARD_SPAN,
    DEFAULT_SIEVE_SIZE_KIB,
    DEFAULT_WORKERS,
    SOURCE_UPPER_EXCLUSIVE,
    PsiAffineCampaignError,
    command_for_shard,
    finalize_campaign,
    grouped_shard_indices,
    ingest_receipt,
    initialize_campaign,
    run_campaign,
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


def _directory(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("output_directory", type=Path)


def _guard_finite_work(output_directory: Path) -> None:
    config = load_json(
        output_directory / CONFIG_NAME, require_canonical=True
    )
    if not isinstance(config, dict):
        raise PsiAffineCampaignError("campaign config must be an object")
    lower = config.get("domain_lower")
    upper = config.get("domain_upper_exclusive")
    span = config.get("shard_span")
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in (lower, upper, span)
    ):
        raise PsiAffineCampaignError("campaign work bounds are malformed")
    assert isinstance(lower, int)
    assert isinstance(upper, int)
    assert isinstance(span, int)
    if upper <= lower or span < 1:
        raise PsiAffineCampaignError("campaign work bounds are invalid")
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
            "Run or ingest independent affine psi shards, exclusive-scan "
            "their deltas from [0,0], enforce every guard rectangle, and "
            "commit the ordered children."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser(
        "init", help="capture identities and write the fixed shard plan"
    )
    init.add_argument("--runner", type=Path, required=True)
    init.add_argument("--runner-source", type=Path, required=True)
    init.add_argument("--upstream-manifest", type=Path, required=True)
    init.add_argument("--output-dir", type=Path, required=True)
    init.add_argument(
        "--shard-span", type=positive, default=DEFAULT_SHARD_SPAN
    )
    init.add_argument(
        "--sieve-size-kib", type=positive, default=DEFAULT_SIEVE_SIZE_KIB
    )
    init.add_argument(
        "--bounded-test-upper-exclusive",
        type=positive,
        help=(
            "explicitly create a bounded-test plan instead of [2,10^13+1); "
            "it can never be labeled full-source"
        ),
    )

    command = commands.add_parser(
        "command", help="print one cluster worker argv as JSON"
    )
    _directory(command)
    command.add_argument("shard_index", type=nonnegative)

    run = commands.add_parser(
        "run", help="run and checkpoint missing affine shards"
    )
    _directory(run)
    run.add_argument("--shard", type=nonnegative, action="append", dest="shards")
    run.add_argument("--worker-group-index", type=nonnegative)
    run.add_argument("--worker-group-count", type=positive)
    run.add_argument("--max-shards", type=positive)
    run.add_argument("--workers", type=positive, default=DEFAULT_WORKERS)
    run.add_argument("--timeout-seconds", type=positive)

    ingest = commands.add_parser(
        "ingest", help="validate and retain one external shard receipt"
    )
    _directory(ingest)
    ingest.add_argument("shard_index", type=nonnegative)
    ingest.add_argument("receipt", type=Path)

    finalize = commands.add_parser(
        "finalize", help="exclusive-scan and materialize the certificate"
    )
    _directory(finalize)

    verify = commands.add_parser(
        "verify", help="audit the plan, receipts, scan, and commitments"
    )
    _directory(verify)
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        if arguments.command == "init":
            bounded = arguments.bounded_test_upper_exclusive
            result: object = initialize_campaign(
                runner=arguments.runner,
                runner_source=arguments.runner_source,
                upstream_manifest=arguments.upstream_manifest,
                output_directory=arguments.output_dir,
                shard_span=arguments.shard_span,
                sieve_size_kib=arguments.sieve_size_kib,
                domain_upper_exclusive=(
                    SOURCE_UPPER_EXCLUSIVE if bounded is None else bounded
                ),
                allow_bounded_test=bounded is not None,
            ).as_json()
        elif arguments.command == "command":
            result = {
                "argv": list(
                    command_for_shard(
                        arguments.output_directory, arguments.shard_index
                    )
                )
            }
        elif arguments.command == "ingest":
            ingest_receipt(
                arguments.output_directory,
                arguments.shard_index,
                arguments.receipt,
            )
            result = verify_campaign(
                arguments.output_directory
            ).as_json()
        else:
            _guard_finite_work(arguments.output_directory)
            if arguments.command == "run":
                grouped = (
                    arguments.worker_group_index is not None
                    or arguments.worker_group_count is not None
                )
                if grouped and (
                    arguments.worker_group_index is None
                    or arguments.worker_group_count is None
                ):
                    raise PsiAffineCampaignError(
                        "worker group index and count must be supplied together"
                    )
                if grouped and arguments.shards:
                    raise PsiAffineCampaignError(
                        "choose explicit shards or one worker group, not both"
                    )
                if grouped and arguments.max_shards is not None:
                    raise PsiAffineCampaignError(
                        "a worker group cannot be truncated with --max-shards"
                    )
                selected = arguments.shards
                if grouped:
                    selected = grouped_shard_indices(
                        arguments.output_directory,
                        group_index=arguments.worker_group_index,
                        group_count=arguments.worker_group_count,
                    )
                result = run_campaign(
                    arguments.output_directory,
                    shard_indices=selected,
                    workers=arguments.workers,
                    max_shards=arguments.max_shards,
                    timeout_seconds=arguments.timeout_seconds,
                ).as_json()
            elif arguments.command == "finalize":
                result = finalize_campaign(
                    arguments.output_directory
                ).as_json()
            else:
                result = verify_campaign(
                    arguments.output_directory
                ).as_json()
    except (CampaignIOError, PsiAffineCampaignError) as exc:
        print(f"psi affine campaign error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
