#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run the bounded Goldbach v1/v2 prime-prefix differential benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.goldbach_prime_prefix_reuse_benchmark import (  # noqa: E402
    DEFAULT_EVEN_LIMIT,
    DEFAULT_EVEN_START,
    benchmark_prime_prefix_reuse,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("v1_executable", type=Path)
    parser.add_argument("v2_executable", type=Path)
    parser.add_argument("crosscheck_executable", type=Path)
    parser.add_argument("--even-start", type=int, default=DEFAULT_EVEN_START)
    parser.add_argument("--even-limit", type=int, default=DEFAULT_EVEN_LIMIT)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = benchmark_prime_prefix_reuse(
        v1_executable=args.v1_executable,
        v2_executable=args.v2_executable,
        crosscheck_executable=args.crosscheck_executable,
        even_start=args.even_start,
        even_limit=args.even_limit,
        rounds=args.rounds,
        warmups=args.warmups,
        timeout=args.timeout,
    )
    print(
        json.dumps(
            result,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
