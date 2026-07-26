#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Materialize the exact qualified optimized GoldbachGPU source candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.goldbach_gpu_campaign import GoldbachGPUCampaignError
from tg_verifier.goldbach_optimized_source import (
    GoldbachOptimizedSourceError,
    prepare_optimized_source,
)
from tg_verifier.goldbach_shifted_coverage_optimizer import (
    GoldbachShiftedCoverageOptimizerError,
)
from tg_verifier.goldbach_warp_tail_optimizer import (
    GoldbachWarpTailOptimizerError,
)
from tg_verifier.goldbach_wheel_filtered_tail_optimizer import (
    GoldbachWheelFilteredTailOptimizerError,
)
from tg_verifier.goldbach_word_owner_optimizer import (
    GoldbachWordOwnerOptimizerError,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("hardened_source_root", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    try:
        result = prepare_optimized_source(
            arguments.hardened_source_root, arguments.destination
        )
    except (
        GoldbachGPUCampaignError,
        GoldbachOptimizedSourceError,
        GoldbachShiftedCoverageOptimizerError,
        GoldbachWarpTailOptimizerError,
        GoldbachWheelFilteredTailOptimizerError,
        GoldbachWordOwnerOptimizerError,
        OSError,
        UnicodeError,
    ) as error:
        print(error, file=sys.stderr)
        return 2
    print(
        json.dumps(
            result,
            indent=2 if arguments.pretty else None,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
