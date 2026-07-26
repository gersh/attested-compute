#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build, audit, differentially test, or revalidate the Goldbach candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import canonical_json_bytes  # noqa: E402
from tg_verifier.goldbach_gpu_campaign import (  # noqa: E402
    GoldbachGPUCampaignError,
)
from tg_verifier.goldbach_optimized_candidate import (  # noqa: E402
    DEFAULT_BOUNDED_EVEN_LIMIT,
    DEFAULT_BOUNDED_EVEN_START,
    GoldbachOptimizedCandidateError,
    bounded_full_differential,
    build_candidate_package,
    validate_candidate_package,
)
from tg_verifier.goldbach_optimized_source import (  # noqa: E402
    GoldbachOptimizedSourceError,
)
from tg_verifier.goldbach_shifted_coverage_optimizer import (  # noqa: E402
    GoldbachShiftedCoverageOptimizerError,
)
from tg_verifier.goldbach_warp_tail_optimizer import (  # noqa: E402
    GoldbachWarpTailOptimizerError,
)
from tg_verifier.goldbach_wheel_filtered_tail_optimizer import (  # noqa: E402
    GoldbachWheelFilteredTailOptimizerError,
)


def _emit(value: object, pretty: bool) -> None:
    if pretty:
        sys.stdout.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.buffer.write(canonical_json_bytes(value))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="mode", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("hardened_source_root", type=Path)
    build.add_argument("destination", type=Path)
    build.add_argument(
        "--nvcc", type=Path, default=Path("/usr/local/cuda/bin/nvcc")
    )
    build.add_argument("--host-cxx", type=Path, default=Path("/usr/bin/g++"))
    build.add_argument("--bounded-arch", default="native")
    build.add_argument(
        "--bounded-even-start",
        type=int,
        default=DEFAULT_BOUNDED_EVEN_START,
    )
    build.add_argument(
        "--bounded-even-limit",
        type=int,
        default=DEFAULT_BOUNDED_EVEN_LIMIT,
    )
    build.add_argument("--timeout", type=int, default=900)
    build.add_argument("--pretty", action="store_true")

    differential = subparsers.add_parser("bounded-differential")
    differential.add_argument("hardened_source_root", type=Path)
    differential.add_argument(
        "--nvcc", type=Path, default=Path("/usr/local/cuda/bin/nvcc")
    )
    differential.add_argument(
        "--host-cxx", type=Path, default=Path("/usr/bin/g++")
    )
    differential.add_argument("--arch", default="native")
    differential.add_argument(
        "--even-start", type=int, default=DEFAULT_BOUNDED_EVEN_START
    )
    differential.add_argument(
        "--even-limit", type=int, default=DEFAULT_BOUNDED_EVEN_LIMIT
    )
    differential.add_argument("--timeout", type=int, default=900)
    differential.add_argument("--pretty", action="store_true")

    validate = subparsers.add_parser("validate")
    validate.add_argument("package_root", type=Path)
    validate.add_argument("--pretty", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.mode == "build":
            value = build_candidate_package(
                arguments.hardened_source_root,
                arguments.destination,
                nvcc=arguments.nvcc,
                host_cxx=arguments.host_cxx,
                bounded_arch=arguments.bounded_arch,
                bounded_even_start=arguments.bounded_even_start,
                bounded_even_limit=arguments.bounded_even_limit,
                timeout=arguments.timeout,
            )
        elif arguments.mode == "bounded-differential":
            value = bounded_full_differential(
                arguments.hardened_source_root,
                nvcc=arguments.nvcc,
                host_cxx=arguments.host_cxx,
                arch=arguments.arch,
                even_start=arguments.even_start,
                even_limit=arguments.even_limit,
                timeout=arguments.timeout,
            )
        else:
            value = validate_candidate_package(arguments.package_root)
        _emit(value, arguments.pretty)
        return 0
    except (
        GoldbachGPUCampaignError,
        GoldbachOptimizedCandidateError,
        GoldbachOptimizedSourceError,
        GoldbachShiftedCoverageOptimizerError,
        GoldbachWarpTailOptimizerError,
        GoldbachWheelFilteredTailOptimizerError,
        OSError,
        ValueError,
    ) as error:
        print(f"optimized Goldbach qualification failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
