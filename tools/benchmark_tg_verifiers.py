#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark bounded TG verifier primitives and print honest full ETAs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.benchmark import BenchmarkError, build_benchmark_report  # noqa: E402
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


def positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gpu-executable",
        type=Path,
        default=Path("build/dgx-spark/sparkinterval-tg-workload-benchmark"),
    )
    parser.add_argument("--no-gpu", action="store_true")
    parser.add_argument("--gpu-count", type=positive, default=1 << 24)
    parser.add_argument("--gpu-repetitions", type=positive, default=10)
    parser.add_argument("--mobius-limit", type=positive, default=1_000_000)
    parser.add_argument("--exact-fraction-limit", type=positive, default=20_000)
    parser.add_argument(
        "--psi-limit",
        type=positive,
        help="also benchmark the exact bounded prime-power/log checker",
    )
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        bounds = [args.mobius_limit, args.exact_fraction_limit]
        if args.psi_limit is not None:
            bounds.append(args.psi_limit)
        if not args.no_gpu:
            bounds.append(args.gpu_count * args.gpu_repetitions)
        require_azure_measured_worker_for_workload(
            exact_production=False,
            work_bounds=tuple(bounds),
        )
        executable = None if args.no_gpu else args.gpu_executable
        report = build_benchmark_report(
            gpu_executable=executable,
            gpu_count=args.gpu_count,
            gpu_repetitions=args.gpu_repetitions,
            mobius_limit=args.mobius_limit,
            exact_fraction_limit=args.exact_fraction_limit,
            psi_limit=args.psi_limit,
        )
    except (BenchmarkError, OSError, ValueError) as exc:
        print(json.dumps({"accepted": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(
        json.dumps(
            report,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
