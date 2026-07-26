#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run, inspect, or independently replay the exact CH25 psi campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.psi_campaign import (  # noqa: E402
    PsiCampaignError,
    replay_campaign,
    run_campaign,
    verify_campaign,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    require_azure_measured_worker_for_workload,
)


def positive(value: str) -> int:
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="start or resume the full-source job")
    run.add_argument("output_dir", type=Path)
    run.add_argument("--chunk-span", type=positive, default=1_000_000)
    run.add_argument("--scale-bits", type=positive, default=128)
    run.add_argument("--series-terms", type=positive, default=48)
    run.add_argument("--segment-size", type=positive, default=1_000_000)
    run.add_argument("--max-chunks", type=positive)
    verify = subcommands.add_parser("verify", help="check compact chain structure")
    verify.add_argument("output_dir", type=Path)
    replay = subcommands.add_parser("replay", help="regenerate exact source events")
    replay.add_argument("output_dir", type=Path)
    replay.add_argument("--max-chunks", type=positive)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "run":
            # --max-chunks only pauses the exact 10^13 source campaign; it
            # does not turn a million-wide source chunk into a local sample.
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(
                    args.chunk_span,
                    args.segment_size,
                    0 if args.max_chunks is None else args.max_chunks,
                ),
            )
            result = run_campaign(
                args.output_dir,
                chunk_span=args.chunk_span,
                scale_bits=args.scale_bits,
                series_terms=args.series_terms,
                segment_size=args.segment_size,
                max_chunks=args.max_chunks,
            )
        elif args.command == "verify":
            result = verify_campaign(args.output_dir)
        else:
            # Keep compact chain inspection local, but require measured scope
            # before opening a campaign for fresh prime-power regeneration.
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(
                    0 if args.max_chunks is None else args.max_chunks,
                ),
            )
            result = replay_campaign(args.output_dir, max_chunks=args.max_chunks)
    except (CampaignIOError, PsiCampaignError) as exc:
        print(f"psi campaign error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.as_json(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
