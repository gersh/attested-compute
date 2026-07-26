#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build or finalize source-bound PT21 compact artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.platt_pt21_fused_artifact import (  # noqa: E402
    PT21FusedArtifactError,
    build_block_artifact,
    finalize_campaign,
    finalize_shard,
    write_block_artifact,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pretty", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)
    block = commands.add_parser("block")
    block.add_argument("--required-sign-packet", type=Path, required=True)
    block.add_argument("--source-trace", type=Path, required=True)
    block.add_argument("--output", type=Path)
    shard = commands.add_parser("shard")
    shard.add_argument("--first-block", type=int, required=True)
    shard.add_argument("--allow-bounded-test", action="store_true")
    shard.add_argument("artifacts", type=Path, nargs="+")
    campaign = commands.add_parser("campaign")
    campaign.add_argument("--allow-bounded-test", action="store_true")
    campaign.add_argument("receipts", type=Path, nargs="+")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "block":
            if args.output is None:
                value = build_block_artifact(
                    args.required_sign_packet, args.source_trace
                )
            else:
                value = write_block_artifact(
                    args.required_sign_packet, args.source_trace, args.output
                )
        elif args.command == "shard":
            require_azure_measured_worker_for_workload(
                exact_production=not args.allow_bounded_test,
                work_bounds=(len(args.artifacts),),
            )
            value = finalize_shard(
                args.artifacts,
                first_block=args.first_block,
                allow_bounded_test=args.allow_bounded_test,
            )
        elif args.command == "campaign":
            require_azure_measured_worker_for_workload(
                exact_production=not args.allow_bounded_test,
                work_bounds=(len(args.receipts),),
            )
            value = finalize_campaign(
                args.receipts, allow_bounded_test=args.allow_bounded_test
            )
        else:  # pragma: no cover
            raise AssertionError("unreachable command")
    except (OSError, ValueError, PT21FusedArtifactError) as error:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "classification": "platt-pt21-fused-artifact-failed-closed",
                    "error": str(error),
                    "source_claim_ready": False,
                },
                sort_keys=True,
                indent=2 if args.pretty else None,
            )
        )
        return 2
    print(json.dumps(value, sort_keys=True, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
