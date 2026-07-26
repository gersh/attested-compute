#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run, replay, and merge rigorous MPFR Proposition 12.2.4 shards."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
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
from tg_verifier.prop1224_mpfr_campaign import (  # noqa: E402
    Prop1224MpfrCampaignError,
    make_mpfr_plan,
    run_mpfr_shard,
    validate_receipt,
    verify_receipts,
)


RECEIPT_PATTERN = re.compile(r"mpfr-shard-([0-9]{5})\.json\Z")


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
    parser.add_argument("--precision-bits", type=positive, default=192)
    parser.add_argument("--mpfr-version", default="4.2.1")
    parser.add_argument("--rank-lower", type=nonnegative, default=0)
    parser.add_argument("--rank-upper", type=positive, default=PRODUCTION_RANK_END)
    parser.add_argument("--leaf-rows", type=positive, default=PRODUCTION_LEAF_ROWS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="print the immutable campaign identity")
    add_plan_options(plan)

    run = commands.add_parser("run-shard", help="run one plan leaf")
    run.add_argument("runner", type=Path)
    run.add_argument("output_dir", type=Path)
    run.add_argument("shard_index", type=nonnegative)
    run.add_argument("--segment-size", type=positive, default=250_000)
    add_plan_options(run)

    group = commands.add_parser(
        "run-worker-group", help="run one balanced group of fixed-plan leaves"
    )
    group.add_argument("runner", type=Path)
    group.add_argument("output_dir", type=Path)
    group.add_argument("worker_group_index", type=nonnegative)
    group.add_argument("--worker-group-count", type=positive, required=True)
    group.add_argument("--workers", type=positive, required=True)
    group.add_argument("--segment-size", type=positive, default=250_000)
    add_plan_options(group)

    verify = commands.add_parser("verify", help="verify and merge every receipt")
    verify.add_argument("output_dir", type=Path)
    verify.add_argument("--registered-result-output", type=Path)
    add_plan_options(verify)
    return parser


def make_plan(args: argparse.Namespace):
    return make_mpfr_plan(
        precision_bits=args.precision_bits,
        mpfr_version=args.mpfr_version,
        rank_lower=args.rank_lower,
        rank_upper=args.rank_upper,
        leaf_rows=args.leaf_rows,
    )


def guard_finite_work(args: argparse.Namespace, plan) -> None:
    """Keep the q=1 leaf and all non-tiny rank work on measured Azure."""

    if args.command == "plan":
        return
    if args.command == "run-shard":
        if args.shard_index >= len(plan.shards):
            raise Prop1224MpfrCampaignError(
                "shard index is outside the fixed MPFR plan"
            )
        selected = (plan.shards[args.shard_index],)
    elif args.command == "run-worker-group":
        if args.worker_group_index >= args.worker_group_count:
            raise Prop1224MpfrCampaignError(
                "worker-group index is outside its count"
            )
        selected = tuple(
            plan.shards[index]
            for index in range(
                args.worker_group_index,
                len(plan.shards),
                args.worker_group_count,
            )
        )
    else:
        selected = tuple(plan.shards)
    selected_rows = sum(shard.upper - shard.lower for shard in selected)
    contains_q_one_leaf = any(
        shard.lower == 0 and shard.upper >= 1 for shard in selected
    )
    require_azure_measured_worker_for_workload(
        exact_production=(
            (
                plan.domain_lower == 0
                and plan.domain_upper == PRODUCTION_RANK_END
            )
            or contains_q_one_leaf
        ),
        work_bounds=(selected_rows,),
    )


def load_receipts(output_dir: Path) -> list[dict[str, object]]:
    indexed: list[tuple[int, Path]] = []
    for path in output_dir.glob("mpfr-shard-*.json"):
        match = RECEIPT_PATTERN.fullmatch(path.name)
        if match is None:
            raise Prop1224MpfrCampaignError(f"malformed receipt name {path.name!r}")
        indexed.append((int(match.group(1)), path))
    indexed.sort()
    if [index for index, _ in indexed] != list(range(len(indexed))):
        raise Prop1224MpfrCampaignError("receipt indices are not consecutive")
    receipts: list[dict[str, object]] = []
    for _, path in indexed:
        value = load_json(path, require_canonical=True)
        if not isinstance(value, dict):
            raise Prop1224MpfrCampaignError(f"{path.name} is not an object")
        receipts.append(value)
    return receipts


def run_worker_group(
    args: argparse.Namespace, plan,
) -> dict[str, object]:
    if args.worker_group_index >= args.worker_group_count:
        raise Prop1224MpfrCampaignError("worker-group index is outside its count")
    indices = range(
        args.worker_group_index, len(plan.shards), args.worker_group_count
    )
    if not indices:
        raise Prop1224MpfrCampaignError("worker group has no fixed-plan leaves")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    def run_one(shard_index: int) -> tuple[int, dict[str, object]]:
        receipt = run_mpfr_shard(
            runner=args.runner,
            plan=plan,
            shard_index=shard_index,
            precision_bits=args.precision_bits,
            mpfr_version=args.mpfr_version,
            segment_size=args.segment_size,
        )
        validate_receipt(
            receipt,
            plan=plan,
            precision_bits=args.precision_bits,
            mpfr_version=args.mpfr_version,
        )
        path = args.output_dir / f"mpfr-shard-{shard_index:05d}.json"
        atomic_write_json(path, receipt)
        return shard_index, receipt

    completed: list[tuple[int, dict[str, object]]] = []
    with ThreadPoolExecutor(max_workers=min(args.workers, len(indices))) as pool:
        futures = {pool.submit(run_one, index): index for index in indices}
        for future in as_completed(futures):
            completed.append(future.result())
    completed.sort(key=lambda item: item[0])
    runner_hashes = {
        str(receipt["runner_executable_sha256"]) for _, receipt in completed
    }
    if len(runner_hashes) != 1:
        raise Prop1224MpfrCampaignError("worker group mixed runner executables")
    return {
        "classification": "completed-external-worker-group-not-lean-proof",
        "first_shard_index": indices.start,
        "last_shard_index_inclusive": indices[-1],
        "leaf_count": len(indices),
        "plan_sha256": plan.plan_sha256,
        "runner_executable_sha256": next(iter(runner_hashes)),
        "worker_group_count": args.worker_group_count,
        "worker_group_index": args.worker_group_index,
        "workers": min(args.workers, len(indices)),
    }


def write_registered_result(path: Path) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o400,
    )
    try:
        if os.write(descriptor, b"true") != 4:
            raise Prop1224MpfrCampaignError("short registered-result write")
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def main() -> int:
    args = build_parser().parse_args()
    try:
        if (
            args.command != "plan"
            and args.rank_lower == 0
            and args.rank_upper == PRODUCTION_RANK_END
        ):
            # Fail before hashing the adapter source or materializing the
            # 12,930-leaf production plan.
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(PRODUCTION_RANK_END,),
            )
        plan = make_plan(args)
        guard_finite_work(args, plan)
        if args.command == "plan":
            result = {
                "algorithm": plan.algorithm,
                "plan_sha256": plan.plan_sha256,
                "rank_lower": plan.domain_lower,
                "rank_upper": plan.domain_upper,
                "leaf_count": len(plan.shards),
                "q_one_isolated": plan.shards[0].lower == 0
                and plan.shards[0].upper == 1,
                "classification": "fixed-plan-only-not-completed-computation",
            }
        elif args.command == "run-shard":
            receipt = run_mpfr_shard(
                runner=args.runner,
                plan=plan,
                shard_index=args.shard_index,
                precision_bits=args.precision_bits,
                mpfr_version=args.mpfr_version,
                segment_size=args.segment_size,
            )
            validate_receipt(
                receipt,
                plan=plan,
                precision_bits=args.precision_bits,
                mpfr_version=args.mpfr_version,
            )
            args.output_dir.mkdir(parents=True, exist_ok=True)
            path = args.output_dir / f"mpfr-shard-{args.shard_index:05d}.json"
            atomic_write_json(path, receipt)
            result = {
                **receipt,
                "output_path": str(path),
                "classification": "completed-external-shard-not-lean-proof",
            }
        elif args.command == "run-worker-group":
            result = run_worker_group(args, plan)
        else:
            receipts = load_receipts(args.output_dir)
            verification = verify_receipts(
                receipts,
                plan=plan,
                precision_bits=args.precision_bits,
                mpfr_version=args.mpfr_version,
            )
            result = {
                **verification.to_dict(),
                "classification": "complete-external-computation-not-lean-proof",
                "all_fixed_plan_receipts_present": True,
                "execution_attested": False,
                "lean_realization_proved": False,
                "lean_atom_discharged": False,
            }
            if args.registered_result_output is not None:
                if (
                    plan.domain_lower != 0
                    or plan.domain_upper != PRODUCTION_RANK_END
                    or len(plan.shards) != 12_930
                    or verification.root_state != (0,)
                    or verification.final_state != (PRODUCTION_RANK_END,)
                ):
                    raise Prop1224MpfrCampaignError(
                        "registered result requires the exact full-source plan"
                    )
                write_registered_result(args.registered_result_output)
                result["registered_result"] = {
                    "path": str(args.registered_result_output.resolve()),
                    "sha256": (
                        "b5bea41b6c623f7c09f1bf24dcae58e"
                        "bab3c0cdd90ad966bc43a45b44867e12b"
                    ),
                    "size_bytes": 4,
                }
    except (CampaignIOError, OSError, Prop1224MpfrCampaignError, ValueError) as exc:
        print(f"Proposition 12.2.4 MPFR campaign error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
