#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run or structurally audit the resumable full-source R2Star campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.r2star_campaign import (  # noqa: E402
    R2StarCampaignError,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="start or resume the full campaign")
    run.add_argument("--runner", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--segment-count", type=positive, default=1_000_000)
    run.add_argument("--device", type=nonnegative, default=0)
    run.add_argument("--allow-other-device", action="store_true")
    run.add_argument("--cross-check-serial", action="store_true")
    run.add_argument("--max-chunks", type=positive)
    run.add_argument("--chunk-timeout-seconds", type=positive)
    verify = subcommands.add_parser("verify", help="audit a retained campaign")
    verify.add_argument("output_dir", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "run":
            result = run_campaign(
                runner=args.runner,
                output_directory=args.output_dir,
                segment_count=args.segment_count,
                device=args.device,
                allow_other_device=args.allow_other_device,
                cross_check_serial=args.cross_check_serial,
                max_chunks=args.max_chunks,
                chunk_timeout_seconds=args.chunk_timeout_seconds,
            )
        else:
            result = verify_campaign(args.output_dir)
    except R2StarCampaignError as exc:
        print(f"R2Star campaign error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.as_json(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
