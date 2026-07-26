#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Inspect readiness or emit immutable PT21 H100 Azure shard geometry."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.platt_h100_campaign import (  # noqa: E402
    DEFAULT_BLOCKS_PER_SHARD,
    FULL_BLOCK_COUNT,
    PlattH100CampaignError,
    create_plan,
    current_readiness,
    shard_task,
    validate_block_artifact,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


def _positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def _worker_identity(path: Path) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise PlattH100CampaignError("worker must be a regular file")
    raw = path.read_bytes()
    if not raw:
        raise PlattH100CampaignError("worker must be nonempty")
    return hashlib.sha256(raw).hexdigest(), len(raw)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pretty", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("readiness")
    plan = commands.add_parser("plan")
    plan.add_argument("--worker", type=Path, required=True)
    plan.add_argument("--blocks-per-shard", type=_positive, default=DEFAULT_BLOCKS_PER_SHARD)
    plan.add_argument("--block-count", type=_positive, default=FULL_BLOCK_COUNT)
    plan.add_argument("--allow-bounded-test", action="store_true")
    task = commands.add_parser("task")
    task.add_argument("plan", type=Path)
    task.add_argument("index", type=int)
    block = commands.add_parser("validate-block")
    block.add_argument("artifact", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "readiness":
            value = current_readiness()
        elif args.command == "plan":
            sha256, size = _worker_identity(args.worker)
            value = create_plan(
                worker_sha256=sha256,
                worker_size=size,
                blocks_per_shard=args.blocks_per_shard,
                block_count=args.block_count,
                allow_bounded_test=args.allow_bounded_test,
            )
        elif args.command == "task":
            value = shard_task(json.loads(args.plan.read_text()), args.index)
        elif args.command == "validate-block":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            value = validate_block_artifact(json.loads(args.artifact.read_text()))
        else:
            raise AssertionError("unreachable command")
    except (OSError, ValueError, json.JSONDecodeError, PlattH100CampaignError) as error:
        value = {
            "accepted": False,
            "classification": "platt-pt21-h100-campaign-failed-closed",
            "error": str(error),
            "azure_proof_execution_ready": False,
            "lean_source_claim_ready": False,
        }
        print(json.dumps(value, sort_keys=True, indent=2 if args.pretty else None))
        return 2
    print(json.dumps(value, sort_keys=True, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
