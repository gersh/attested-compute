#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Inspect the constant-memory Dirichlet q-major target cursor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_allchars_q_scheduler import (  # noqa: E402
    build_schedule_manifest_bytes,
    parse_schedule_manifest,
    source_schedule_records,
)
from tg_verifier.dirichlet_formulaic_qmajor_cursor import (  # noqa: E402
    DirichletFormulaicQMajorError,
    capability,
    formulaic_accounting,
    source_lanes,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("capability")
    commands.add_parser(
        "source-accounting",
        help="reconstruct exact source counts without expanding 56,981,100 targets",
    )
    manifest = commands.add_parser("manifest-accounting")
    manifest.add_argument("schedule_manifest", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "capability":
            result = capability()
        elif args.command == "source-accounting":
            schedule = parse_schedule_manifest(
                build_schedule_manifest_bytes(
                    source_schedule_records(), full_source=True
                )
            )
            result = formulaic_accounting(schedule, source_lanes())
        else:
            schedule = parse_schedule_manifest(args.schedule_manifest)
            maximum_t = max(
                record.t_index_count for record in schedule.execution_records
            )
            lanes = tuple(
                lane
                for lane in source_lanes()
                if lane.first_t_index < maximum_t
            )
            if lanes[-1].t_index_stop_exclusive != maximum_t:
                # This command is for the exact source geometry or a bounded
                # prefix ending on an existing source lane boundary.
                raise DirichletFormulaicQMajorError(
                    "bounded manifest maximum t is not a source lane boundary"
                )
            result = formulaic_accounting(schedule, lanes)
        print(
            json.dumps(
                result,
                sort_keys=True,
                indent=2 if args.pretty else None,
                separators=None if args.pretty else (",", ":"),
            )
        )
        return 0
    except (DirichletFormulaicQMajorError, OSError) as error:
        print(f"tg_dirichlet_formulaic_qmajor_cursor: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
