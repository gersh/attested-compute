#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Print a fail-closed engineering projection for a Goldbach prototype."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier.goldbach_optimized_projection import (
    GoldbachOptimizedProjectionError,
    project_optimized_prototype,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-even-count", type=int, required=True)
    parser.add_argument("--sample-seconds", required=True)
    parser.add_argument(
        "--initialization-seconds-per-leaf",
        required=True,
    )
    parser.add_argument(
        "--fixed-seconds-per-leaf",
        default="0",
        help=(
            "nonnegative process/launch overhead charged once for every "
            "checkpoint leaf"
        ),
    )
    parser.add_argument("--production-even-count", type=int)
    parser.add_argument("--checkpoint-leaf-count", type=int)
    parser.add_argument("--cluster-gpu-count", type=int, default=8)
    parser.add_argument("--deadline-hours", default="168")
    parser.add_argument("--budget-usd", default="10000")
    parser.add_argument("--on-demand-cluster-hour-usd", default="55.84")
    parser.add_argument("--spot-cluster-hour-usd", default="11.352272")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    keywords: dict[str, object] = {
        "sample_even_count": arguments.sample_even_count,
        "sample_seconds": arguments.sample_seconds,
        "initialization_seconds_per_leaf": (
            arguments.initialization_seconds_per_leaf
        ),
        "fixed_seconds_per_leaf": arguments.fixed_seconds_per_leaf,
        "cluster_gpu_count": arguments.cluster_gpu_count,
        "deadline_hours": arguments.deadline_hours,
        "budget_usd": arguments.budget_usd,
        "on_demand_cluster_hour_usd": (
            arguments.on_demand_cluster_hour_usd
        ),
        "spot_cluster_hour_usd": arguments.spot_cluster_hour_usd,
    }
    if arguments.production_even_count is not None:
        keywords["production_even_count"] = arguments.production_even_count
    if arguments.checkpoint_leaf_count is not None:
        keywords["checkpoint_leaf_count"] = arguments.checkpoint_leaf_count
    try:
        result = project_optimized_prototype(**keywords)
        encoded = (
            json.dumps(result, indent=2, sort_keys=True).encode() + b"\n"
            if arguments.pretty
            else canonical_json_bytes(result)
        )
        if arguments.out is not None:
            arguments.out.parent.mkdir(parents=True, exist_ok=True)
            arguments.out.write_bytes(encoded)
        sys.stdout.buffer.write(encoded)
    except (GoldbachOptimizedProjectionError, OSError) as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
