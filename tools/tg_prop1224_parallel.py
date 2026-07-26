#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run and merge fixed Proposition 12.2.4 q-rank leaves."""

from __future__ import annotations

import argparse
from dataclasses import fields
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    atomic_write_json,
    load_json,
    require_azure_measured_worker_for_workload,
)
from tg_verifier.prop1224_factor_plan import (  # noqa: E402
    PRODUCTION_LEAF_ROWS,
    PRODUCTION_RANK_END,
)
from tg_verifier.prop1224_parallel_campaign import (  # noqa: E402
    DirectedShardReport,
    Prop1224ParallelCampaignError,
    leaf_from_directed_report,
    make_directed_plan,
    run_directed_shard,
    verify_directed_leaves,
)


SHARD_PATTERN = re.compile(r"directed-shard-([0-9]{5})\.json\Z")


def positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def nonnegative(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return value


def add_plan_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--rank-lower", type=nonnegative, default=0)
    parser.add_argument("--rank-upper", type=positive, default=PRODUCTION_RANK_END)
    parser.add_argument("--leaf-rows", type=positive, default=PRODUCTION_LEAF_ROWS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="print the immutable plan identity")
    add_plan_options(plan)

    run = commands.add_parser("run-shard", help="recompute one complete-q leaf")
    run.add_argument("output_dir", type=Path)
    run.add_argument("shard_index", type=nonnegative)
    add_plan_options(run)
    run.add_argument("--precision-bits", type=positive, default=144)
    run.add_argument("--log-series-terms", type=positive, default=48)
    run.add_argument("--sieve-segment-size", type=positive, default=250_000)

    verify = commands.add_parser(
        "verify", help="bind all retained reports to the fixed Merkle plan"
    )
    verify.add_argument("output_dir", type=Path)
    add_plan_options(verify)
    return parser


def plan_from_args(args: argparse.Namespace):
    return make_directed_plan(
        rank_lower=args.rank_lower,
        rank_upper=args.rank_upper,
        leaf_rows=args.leaf_rows,
    )


def load_report(path: Path) -> DirectedShardReport:
    raw = load_json(path, require_canonical=True)
    if not isinstance(raw, dict):
        raise Prop1224ParallelCampaignError(f"{path.name} is not a JSON object")
    wanted = {field.name for field in fields(DirectedShardReport)}
    if set(raw) != wanted:
        raise Prop1224ParallelCampaignError(f"{path.name} has the wrong fields")
    try:
        return DirectedShardReport(**raw)
    except TypeError as exc:
        raise Prop1224ParallelCampaignError(
            f"{path.name} cannot be decoded as a directed report"
        ) from exc


def guard_directed_shard(plan, shard_index: int) -> None:
    """Allow only a genuinely tiny bounded q-leaf outside measured Azure."""

    if (
        isinstance(shard_index, bool)
        or not isinstance(shard_index, int)
        or shard_index < 0
        or shard_index >= len(plan.shards)
    ):
        raise Prop1224ParallelCampaignError(
            "shard_index is outside the fixed plan"
        )
    shard = plan.shards[shard_index]
    contains_q_one = shard.lower == 0 and shard.upper >= 1
    require_azure_measured_worker_for_workload(
        exact_production=(
            (
                plan.domain_lower == 0
                and plan.domain_upper == PRODUCTION_RANK_END
            )
            # One q=1 row expands to a 23,207,009-step r-prefix, so its q-row
            # count is not a truthful tiny-KAT bound.
            or contains_q_one
        ),
        work_bounds=(shard.work_count,),
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        if (
            args.command == "run-shard"
            and args.rank_lower == 0
            and args.rank_upper == PRODUCTION_RANK_END
        ):
            # Fail before materializing the 12,930-leaf production plan.
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(PRODUCTION_RANK_END,),
            )
        plan = plan_from_args(args)
        if args.command == "plan":
            result = {
                "algorithm": plan.algorithm,
                "plan_sha256": plan.plan_sha256,
                "rank_lower": plan.domain_lower,
                "rank_upper": plan.domain_upper,
                "source_q_rows": PRODUCTION_RANK_END,
                "leaf_rows": args.leaf_rows,
                "leaf_count": len(plan.shards),
                "q_one_isolated": plan.shards[0].lower == 0
                and plan.shards[0].upper == 1,
                "classification": "fixed-plan-only-not-completed-computation",
            }
        elif args.command == "run-shard":
            guard_directed_shard(plan, args.shard_index)
            report = run_directed_shard(
                plan=plan,
                shard_index=args.shard_index,
                precision_bits=args.precision_bits,
                log_series_terms=args.log_series_terms,
                sieve_segment_size=args.sieve_segment_size,
            )
            # Validate before persisting; this also binds the row root to the
            # exact plan range.  Existing files are replaced atomically, so a
            # preempted Azure worker can rerun the same deterministic shard.
            leaf_from_directed_report(plan=plan, report=report)
            args.output_dir.mkdir(parents=True, exist_ok=True)
            path = args.output_dir / f"directed-shard-{args.shard_index:05d}.json"
            atomic_write_json(path, report.as_json())
            result = {**report.as_json(), "output_path": str(path)}
        else:
            indexed: list[tuple[int, Path]] = []
            for path in args.output_dir.glob("directed-shard-*.json"):
                match = SHARD_PATTERN.fullmatch(path.name)
                if match is None:
                    raise Prop1224ParallelCampaignError(
                        f"malformed shard filename {path.name!r}"
                    )
                indexed.append((int(match.group(1)), path))
            indexed.sort()
            if [index for index, _ in indexed] != list(range(len(plan.shards))):
                raise Prop1224ParallelCampaignError(
                    "shard directory is missing, duplicates, or exceeds the fixed plan"
                )
            reports = [load_report(path) for _, path in indexed]
            leaves = tuple(
                leaf_from_directed_report(plan=plan, report=report)
                for report in reports
            )
            verification = verify_directed_leaves(plan=plan, leaves=leaves)
            result = {
                **verification.to_dict(),
                "classification": "complete-external-computation-not-lean-proof",
                "all_directed_shard_reports_present": True,
                "execution_attested": False,
                "lean_realization_proved": False,
                "lean_atom_discharged": False,
            }
    except (CampaignIOError, Prop1224ParallelCampaignError, ValueError) as exc:
        print(f"Proposition 12.2.4 parallel campaign error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
