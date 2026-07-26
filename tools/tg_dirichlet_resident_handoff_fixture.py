#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Prepare or run the bounded resident allchars/completed-L CUDA fixture."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_resident_handoff_fixture import (  # noqa: E402
    prepare_fixture,
    run_fixture,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--directory", type=Path, required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--directory", type=Path, required=True)
    run.add_argument("--runner", type=Path, required=True)
    run.add_argument("--device", type=int, default=0)
    run.add_argument(
        "--sanitizer-tool",
        choices=("memcheck", "initcheck", "racecheck", "synccheck"),
    )
    run.add_argument("--compute-sanitizer", type=Path)
    args = parser.parse_args()

    fixture = prepare_fixture(args.directory)
    if args.command == "run":
        run_fixture(
            fixture,
            args.runner,
            args.device,
            compute_sanitizer=args.compute_sanitizer,
            sanitizer_tool=args.sanitizer_tool,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
