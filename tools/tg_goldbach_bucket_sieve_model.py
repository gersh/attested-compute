#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Print the persistent Goldbach sieve source-work and ETA sensitivity model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.goldbach_bucket_sieve import (  # noqa: E402
    GoldbachBucketSieveError,
    source_scale_eta_model,
    source_scale_work_model,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment-odds", type=int, default=1 << 26)
    parser.add_argument("--measured-candidates", type=int, default=(1 << 26) * 32)
    parser.add_argument("--pipeline-seconds", type=float, default=7.04413534)
    parser.add_argument("--host-seconds", type=float, default=3.645192892)
    parser.add_argument("--gpu-seconds", type=float, default=3.378619338)
    parser.add_argument("--gpu-count", type=int, default=8)
    parser.add_argument(
        "--gpu-speedup",
        type=float,
        action="append",
        default=None,
        help="GPU-only sensitivity; may be repeated (default: 1, 6, 12.3)",
    )
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    speedups = args.gpu_speedup or [1.0, 6.0, 12.3]
    try:
        result = {
            "schema": "tg_goldbach_persistent_bucket_sieve_model_v1",
            "work": source_scale_work_model(segment_odds=args.segment_odds),
            "eta_sensitivities": [
                source_scale_eta_model(
                    measured_candidates=args.measured_candidates,
                    measured_pipeline_seconds=args.pipeline_seconds,
                    measured_host_seconds=args.host_seconds,
                    measured_gpu_seconds=args.gpu_seconds,
                    gpu_count=args.gpu_count,
                    gpu_speedup=speedup,
                )
                for speedup in speedups
            ],
        }
    except GoldbachBucketSieveError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
