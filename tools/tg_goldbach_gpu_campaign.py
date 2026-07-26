#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Create, run, and verify hardened GoldbachGPU fixed-plan campaigns."""

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
from tg_verifier.goldbach_gpu_campaign import (  # noqa: E402
    GoldbachGPUCampaignError,
    aggregate_directory,
    load_plan,
    load_receipt,
    make_bounded_sample_plan,
    make_analytic_10pow27_production_plan,
    make_optimized_analytic_10pow27_production_plan,
    make_optimized_production_plan,
    make_production_plan,
    production_group_leaf_indices,
    receipt_paths,
    run_group,
    run_shard,
    validate_aggregate,
    verify_executable,
    verify_source_tree_for_algorithm,
    write_plan,
)
from tg_verifier.goldbach_optimized_candidate import (  # noqa: E402
    GoldbachOptimizedCandidateError,
    validate_candidate_package,
)


def nonnegative(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return parsed


def positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _plan_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--executable-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)


def _guard_shards(plan, indices: tuple[int, ...]) -> None:
    """Keep source-scale sieve execution in a measured Azure worker."""

    if not indices or any(
        isinstance(index, bool)
        or not isinstance(index, int)
        or index < 0
        or index >= len(plan.shards)
        for index in indices
    ):
        raise GoldbachGPUCampaignError("shard index lies outside the plan")
    require_azure_measured_worker_for_workload(
        exact_production=plan.production,
        work_bounds=(
            len(indices),
            sum(plan.shards[index].even_count for index in indices),
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Operate the exact hardened GoldbachGPU plan. Successful local "
            "receipts remain unattested and do not discharge a Lean atom."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    production = commands.add_parser(
        "create-production-plan",
        help="write the immutable 65,536-leaf [4,4e18] production plan",
    )
    _plan_arguments(production)

    analytic_10pow27 = commands.add_parser(
        "create-analytic-10pow27-plan",
        help=(
            "write the immutable 65,536-leaf [4,31250000000000000] "
            "production plan used below the 10^27 analytic crossover"
        ),
    )
    _plan_arguments(analytic_10pow27)

    optimized_production = commands.add_parser(
        "create-optimized-production-plan",
        help=(
            "write the distinct optimized 65,536-leaf [4,4e18] "
            "source-scale plan"
        ),
    )
    _plan_arguments(optimized_production)
    optimized_production.add_argument(
        "--candidate-package-root", type=Path, required=True
    )
    optimized_production.add_argument(
        "--candidate-manifest-file-sha256", required=True
    )

    optimized_analytic_10pow27 = commands.add_parser(
        "create-optimized-analytic-10pow27-plan",
        help=(
            "write the distinct optimized 65,536-leaf "
            "[4,31250000000000000] source-scale plan"
        ),
    )
    _plan_arguments(optimized_analytic_10pow27)
    optimized_analytic_10pow27.add_argument(
        "--candidate-package-root", type=Path, required=True
    )
    optimized_analytic_10pow27.add_argument(
        "--candidate-manifest-file-sha256", required=True
    )

    bounded = commands.add_parser(
        "create-bounded-plan",
        help="write an explicitly nonproduction bounded sample plan",
    )
    _plan_arguments(bounded)
    bounded.add_argument("--even-start", type=positive, required=True)
    bounded.add_argument("--even-limit", type=positive, required=True)
    bounded.add_argument("--shards", type=positive, default=1)

    command = commands.add_parser("command", help="print one fixed worker argv")
    command.add_argument("plan", type=Path)
    command.add_argument("shard_index", type=nonnegative)
    command.add_argument("--executable", type=Path, required=True)

    run = commands.add_parser("run-shard", help="run and retain one immutable receipt")
    run.add_argument("plan", type=Path)
    run.add_argument("shard_index", type=nonnegative)
    run.add_argument("--source-root", type=Path, required=True)
    run.add_argument("--executable", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--cuda-visible-device", type=nonnegative, default=0)
    run.add_argument("--timeout-seconds", type=positive)

    group = commands.add_parser(
        "run-group",
        help="run or validate one fixed eight-leaf production scheduler group",
    )
    group.add_argument("plan", type=Path)
    group.add_argument("group_index", type=nonnegative)
    group.add_argument("--source-root", type=Path, required=True)
    group.add_argument("--executable", type=Path, required=True)
    group.add_argument("--output-dir", type=Path, required=True)
    group.add_argument("--cuda-visible-device", type=nonnegative, default=0)
    group.add_argument("--timeout-seconds", type=positive)

    aggregate = commands.add_parser(
        "aggregate", help="check exact coverage and write the receipt Merkle aggregate"
    )
    aggregate.add_argument("plan", type=Path)
    aggregate.add_argument("--receipts-dir", type=Path, required=True)
    aggregate.add_argument("--out", type=Path, required=True)

    verify = commands.add_parser(
        "verify", help="revalidate the plan, every receipt, and an aggregate"
    )
    verify.add_argument("plan", type=Path)
    verify.add_argument("aggregate", type=Path)
    verify.add_argument("--receipts-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command in {
            "create-production-plan",
            "create-analytic-10pow27-plan",
            "create-optimized-production-plan",
            "create-optimized-analytic-10pow27-plan",
            "create-bounded-plan",
        }:
            executable_identity = verify_executable(
                args.executable, args.executable_sha256
            )
            if args.command == "create-production-plan":
                plan = make_production_plan(executable_sha256=executable_identity)
            elif args.command == "create-analytic-10pow27-plan":
                plan = make_analytic_10pow27_production_plan(
                    executable_sha256=executable_identity
                )
            elif args.command == "create-optimized-production-plan":
                plan = make_optimized_production_plan(
                    executable_sha256=executable_identity
                )
            elif (
                args.command
                == "create-optimized-analytic-10pow27-plan"
            ):
                plan = make_optimized_analytic_10pow27_production_plan(
                    executable_sha256=executable_identity
                )
            else:
                plan = make_bounded_sample_plan(
                    even_start=args.even_start,
                    even_limit=args.even_limit,
                    shard_count=args.shards,
                    executable_sha256=executable_identity,
                )
            source_identity = verify_source_tree_for_algorithm(
                args.source_root, plan.algorithm
            )
            if args.command in {
                "create-optimized-production-plan",
                "create-optimized-analytic-10pow27-plan",
            }:
                package_root = args.candidate_package_root.resolve()
                if (
                    args.source_root.resolve()
                    != (package_root / "source").resolve()
                    or args.executable.resolve()
                    != (
                        package_root / "artifacts/goldbach-gpu"
                    ).resolve()
                ):
                    raise GoldbachGPUCampaignError(
                        "optimized source and executable must be the exact "
                        "candidate-package entries"
                    )
                package = validate_candidate_package(
                    package_root,
                    expected_manifest_file_sha256=(
                        args.candidate_manifest_file_sha256
                    ),
                    require_reviewed_production=True,
                )
                if (
                    package["optimized_source"][
                        "source_identity_sha256"
                    ]
                    != source_identity
                    or package["artifacts"]["executable"]["sha256"]
                    != executable_identity
                ):
                    raise GoldbachGPUCampaignError(
                        "optimized candidate package does not bind the "
                        "selected source and executable"
                    )
            write_plan(args.out, plan)
            result: object = {
                "accepted": True,
                "source_identity_sha256": source_identity,
                "plan": plan.to_dict(),
            }
        elif args.command == "command":
            from tg_verifier.goldbach_gpu_campaign import runner_arguments

            plan = load_plan(args.plan)
            verify_executable(args.executable, plan.executable_sha256)
            if args.shard_index >= len(plan.shards):
                raise GoldbachGPUCampaignError("shard index lies outside the plan")
            result = {
                "executable_sha256": plan.executable_sha256,
                "argv": [
                    str(args.executable.resolve()),
                    *runner_arguments(plan.shards[args.shard_index]),
                ],
                "execution_attested": False,
                "lean_atom_discharged": False,
            }
        elif args.command == "run-shard":
            plan = load_plan(args.plan)
            _guard_shards(plan, (args.shard_index,))
            result = run_shard(
                plan=plan,
                shard_index=args.shard_index,
                executable=args.executable,
                source_root=args.source_root,
                output_directory=args.output_dir,
                cuda_visible_device=args.cuda_visible_device,
                timeout_seconds=args.timeout_seconds,
            )
        elif args.command == "run-group":
            plan = load_plan(args.plan)
            _guard_shards(
                plan,
                production_group_leaf_indices(plan, args.group_index),
            )
            result = run_group(
                plan=plan,
                group_index=args.group_index,
                executable=args.executable,
                source_root=args.source_root,
                output_directory=args.output_dir,
                cuda_visible_device=args.cuda_visible_device,
                timeout_seconds=args.timeout_seconds,
            )
        elif args.command == "aggregate":
            plan = load_plan(args.plan)
            result = aggregate_directory(
                plan=plan,
                output_directory=args.receipts_dir,
                aggregate_path=args.out,
            )
        else:
            plan = load_plan(args.plan)
            paths = receipt_paths(args.receipts_dir)
            receipts = [load_receipt(path, plan=plan) for path in paths]
            value = load_json(args.aggregate, require_canonical=True)
            result = validate_aggregate(value, plan=plan, receipts=receipts)
    except (
        GoldbachGPUCampaignError,
        GoldbachOptimizedCandidateError,
        CampaignIOError,
        OSError,
    ) as exc:
        print(f"GoldbachGPU campaign error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
