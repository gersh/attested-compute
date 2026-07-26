#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Inspect and resume the local fail-closed Azure TG portfolio control plane.

This command never creates, starts, stops, or deletes an Azure resource.  It
only verifies pinned inputs, writes local portfolio state, and prepares or
records one isolated shard handoff at a time.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.azure_portfolio import (  # noqa: E402
    PortfolioError,
    completion_profile_inventory,
    initialize,
    inspect,
    load_portfolio_spec,
    prepare_shard,
    record_verified_receipt,
    status,
)
from tg_verifier.campaign_io import CampaignIOError  # noqa: E402


def _emit(value: object, *, pretty: bool) -> None:
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser(
        "profiles",
        help=(
            "list source-owned exact campaign sets, including the minimal "
            "lowered-10^27 theorem route"
        ),
    )

    for command, help_text in (
        ("validate", "verify all pinned inputs and report production gaps"),
        ("plan", "emit the deterministic portfolio DAG and backend routes"),
        ("init", "persist a source-closed local plan and resumable state"),
        ("status", "verify immutable records and summarize progress"),
    ):
        child = commands.add_parser(command, help=help_text)
        child.add_argument("spec", type=Path)

    prepare = commands.add_parser(
        "prepare-shard",
        help="create or resume one isolated off-VM challenge/config handoff",
    )
    prepare.add_argument("spec", type=Path)
    prepare.add_argument("--group", required=True)
    prepare.add_argument("--shard-index", type=int, required=True)

    receipt = commands.add_parser(
        "record-receipt",
        help="verify and snapshot a signed receipt for one prepared shard",
    )
    receipt.add_argument("spec", type=Path)
    receipt.add_argument("--group", required=True)
    receipt.add_argument("--shard-index", type=int, required=True)
    receipt.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "profiles":
            payload: object = completion_profile_inventory()
        else:
            context = load_portfolio_spec(args.spec)
        if args.command == "validate":
            payload: object = {
                "accepted": False,
                "classification": "validated_inputs_not_execution_evidence",
                "gap_count": len(context.plan["gaps"]),
                "gaps": context.plan["gaps"],
                "plan_sha256": context.plan_sha256,
                "readiness": context.plan["readiness"],
                "ready_for_local_preparation": context.plan[
                    "ready_for_local_preparation"
                ],
                "valid": True,
            }
        elif args.command == "plan":
            payload = inspect(context)
        elif args.command == "init":
            payload = initialize(context)
        elif args.command == "status":
            payload = status(context)
        elif args.command == "prepare-shard":
            payload = prepare_shard(context, args.group, args.shard_index)
        elif args.command == "record-receipt":
            payload = record_verified_receipt(
                context, args.group, args.shard_index, args.receipt
            )
        _emit(payload, pretty=args.pretty)
        return 0
    except (
        CampaignIOError,
        PortfolioError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        _emit(
            {
                "accepted": False,
                "classification": "azure_tg_portfolio_failed_closed",
                "error": str(error),
                "lean_atoms_discharged": 0,
            },
            pretty=args.pretty,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
