#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize or run the bounded CPU/H100 shared-Hurst source pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.hurst_hybrid_source import (
    CPU_UPPER_EXCLUSIVE,
    DEFAULT_H100_SUPER_SHARD_ROWS,
    SOURCE_UPPER_EXCLUSIVE,
    HurstHybridSourceError,
    materialize,
    run,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser(
        "materialize", help="capture an immutable hybrid execution plan"
    )
    create.add_argument("--cpu-runner", required=True, type=Path)
    create.add_argument("--h100-runner", required=True, type=Path)
    create.add_argument("--prime-roster", required=True, type=Path)
    create.add_argument("--output-dir", required=True, type=Path)
    create.add_argument("--cpu-segment-rows", type=int, default=110_880_000)
    create.add_argument("--h100-leaf-rows", type=int, default=100_000_000)
    create.add_argument(
        "--h100-super-shard-rows",
        type=int,
        default=DEFAULT_H100_SUPER_SHARD_ROWS,
        help=(
            "rows per fused H100 sieve (default: 100000000); calibrate "
            "100m, 200m, and 400m on the production H100 before launch"
        ),
    )
    create.add_argument("--split", type=int, default=CPU_UPPER_EXCLUSIVE)
    create.add_argument(
        "--upper-exclusive", type=int, default=SOURCE_UPPER_EXCLUSIVE
    )
    create.add_argument("--allow-bounded-test", action="store_true")

    execute = subparsers.add_parser(
        "run", help="execute a captured plan and publish its receipt chain"
    )
    execute.add_argument("materialization", type=Path)
    execute.add_argument("--output-dir", required=True, type=Path)
    execute.add_argument(
        "--cpu-timeout-seconds", type=int, default=7 * 24 * 3600
    )
    execute.add_argument(
        "--h100-timeout-seconds", type=int, default=7 * 24 * 3600
    )
    execute.add_argument("--h100-device", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "materialize":
            result = materialize(
                cpu_runner=arguments.cpu_runner,
                h100_runner=arguments.h100_runner,
                prime_roster=arguments.prime_roster,
                output_directory=arguments.output_dir,
                cpu_segment_rows=arguments.cpu_segment_rows,
                h100_leaf_rows=arguments.h100_leaf_rows,
                h100_super_shard_rows=arguments.h100_super_shard_rows,
                split=arguments.split,
                upper_exclusive=arguments.upper_exclusive,
                allow_bounded_test=arguments.allow_bounded_test,
            )
        else:
            result = run(
                materialization_directory=arguments.materialization,
                output_directory=arguments.output_dir,
                cpu_timeout_seconds=arguments.cpu_timeout_seconds,
                h100_timeout_seconds=arguments.h100_timeout_seconds,
                h100_device=arguments.h100_device,
            )
    except HurstHybridSourceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
