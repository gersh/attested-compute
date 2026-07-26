#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build and inspect receipt-bound primitive-V2 q-order manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_allchars_q_scheduler import (  # noqa: E402
    DirichletAllCharsQSchedulerError,
    ScheduleRecord,
    parse_schedule_manifest,
    source_schedule_inventory,
    write_bounded_schedule_manifest,
    write_source_schedule_manifest,
)


def _record(value: str) -> ScheduleRecord:
    fields = value.split(":")
    if len(fields) != 2:
        raise argparse.ArgumentTypeError("q row record must be Q:T_ROWS")
    try:
        return ScheduleRecord(int(fields[0]), int(fields[1]))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "q row record must contain decimal integers"
        ) from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    source = commands.add_parser("source-manifest")
    source.add_argument("path", type=Path)
    bounded = commands.add_parser("bounded-manifest")
    bounded.add_argument("path", type=Path)
    bounded.add_argument(
        "--q-row",
        type=_record,
        action="append",
        required=True,
        help="bounded record Q:T_ROWS; repeat once for each q",
    )
    inspect = commands.add_parser("inspect-manifest")
    inspect.add_argument("path", type=Path)
    commands.add_parser("source-inventory")
    args = parser.parse_args()
    try:
        if args.command == "source-manifest":
            result = write_source_schedule_manifest(args.path)
        elif args.command == "bounded-manifest":
            result = write_bounded_schedule_manifest(args.path, args.q_row)
        elif args.command == "inspect-manifest":
            result = parse_schedule_manifest(args.path).report()
        else:
            result = source_schedule_inventory()
    except DirichletAllCharsQSchedulerError as error:
        print(f"tg_dirichlet_allchars_q_scheduler: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            result, sort_keys=True, indent=2 if args.pretty else None
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
