#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Print an auditable source projection for the tile-compacted sieve."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.goldbach_tile_sieve_projection import (  # noqa: E402
    project_source_campaign,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measured-candidates", type=int, default=2_147_483_648)
    parser.add_argument("--pipeline-seconds", type=float, default=4.404619220)
    parser.add_argument("--host-seconds", type=float, default=3.738536204)
    parser.add_argument("--gpu-seconds", type=float, default=0.632244415)
    parser.add_argument("--devices", type=int, default=8)
    parser.add_argument("--gpu-speedup", type=float, default=12.3)
    parser.add_argument("--full-pipeline-speedup", type=float, default=12.3)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = project_source_campaign(
        measured_candidates=args.measured_candidates,
        measured_pipeline_seconds=args.pipeline_seconds,
        measured_host_seconds=args.host_seconds,
        measured_gpu_seconds=args.gpu_seconds,
        devices=args.devices,
        gpu_speedup=args.gpu_speedup,
        full_pipeline_speedup=args.full_pipeline_speedup,
    )
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

