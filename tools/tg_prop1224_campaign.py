#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run, inspect, or replay the full-source Proposition 12.2.4 campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.prop1224_campaign import (  # noqa: E402
    Prop1224CampaignError,
    replay_campaign,
    run_campaign,
    verify_campaign,
)


def positive(value: str) -> int:
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="start or resume the literal source domain")
    run.add_argument("output_dir", type=Path)
    run.add_argument("--precision-bits", type=positive, default=144)
    run.add_argument("--log-series-terms", type=positive, default=48)
    run.add_argument("--r-steps-per-chunk", type=positive, default=250_000)
    run.add_argument("--q-rows-per-chunk", type=positive, default=100_000)
    run.add_argument("--sieve-segment-size", type=positive, default=250_000)
    run.add_argument(
        "--max-chunks",
        type=positive,
        help="pause after this many new chunks; this does not create a sample profile",
    )

    verify = commands.add_parser("verify", help="check the compact receipt chain")
    verify.add_argument("output_dir", type=Path)

    replay = commands.add_parser(
        "replay", help="independently regenerate arithmetic from the source root"
    )
    replay.add_argument("output_dir", type=Path)
    replay.add_argument("--max-chunks", type=positive)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "run":
            result = run_campaign(
                args.output_dir,
                precision_bits=args.precision_bits,
                log_series_terms=args.log_series_terms,
                r_steps_per_chunk=args.r_steps_per_chunk,
                q_rows_per_chunk=args.q_rows_per_chunk,
                sieve_segment_size=args.sieve_segment_size,
                max_chunks=args.max_chunks,
            )
        elif args.command == "verify":
            result = verify_campaign(args.output_dir)
        else:
            result = replay_campaign(args.output_dir, max_chunks=args.max_chunks)
    except Prop1224CampaignError as exc:
        print(f"Proposition 12.2.4 campaign error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.as_json(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
