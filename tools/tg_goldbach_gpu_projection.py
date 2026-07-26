#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Emit a checked source-height sensitivity table from benchmark timings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.goldbach_gpu_projection import (  # noqa: E402
    GoldbachGPUProjectionError,
    median_seconds,
    project_source_height,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-even-count", type=int, required=True)
    parser.add_argument(
        "--sample-seconds",
        action="append",
        required=True,
        help="repeat for multiple runs; the exact decimal median is used",
    )
    parser.add_argument("--cluster-gpus", type=int, default=8)
    parser.add_argument(
        "--speedup", action="append", help="explicit factor versus measured GPU"
    )
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        median = median_seconds(args.sample_seconds)
        keyword = {}
        if args.speedup is not None:
            keyword["speedups"] = args.speedup
        report = project_source_height(
            sample_even_count=args.sample_even_count,
            sample_seconds=median,
            cluster_gpu_count=args.cluster_gpus,
            **keyword,
        )
        report["sample_seconds_all"] = args.sample_seconds
        report["sample_seconds_statistic"] = "exact_decimal_median"
    except GoldbachGPUProjectionError as exc:
        print(f"GoldbachGPU projection error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
