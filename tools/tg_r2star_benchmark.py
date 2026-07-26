#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark one exact R2Star producer chunk and its CPU arithmetic replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.r2star_benchmark import (  # noqa: E402
    R2StarBenchmarkError,
    benchmark_exact_pair,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    require_azure_measured_worker_for_workload,
)


def positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def nonnegative(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return parsed


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--runner", type=Path, required=True)
    result.add_argument("--arithmetic-replayer", type=Path, required=True)
    result.add_argument("--lower", type=positive, required=True)
    result.add_argument("--count", type=positive, default=1_000_000)
    result.add_argument("--device", type=nonnegative, default=0)
    result.add_argument("--repetitions", type=positive, default=1)
    result.add_argument("--replay-threads", type=positive, default=1)
    result.add_argument("--timeout-seconds", type=positive, default=900)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        # Keep this useful locally for explicit tiny KATs, while preventing
        # the default million-row producer/replayer pair from being launched
        # outside an attested measured worker.
        require_azure_measured_worker_for_workload(
            exact_production=False,
            work_bounds=(arguments.count, arguments.repetitions),
        )
        report = benchmark_exact_pair(
            runner=arguments.runner,
            arithmetic_replayer=arguments.arithmetic_replayer,
            lower=arguments.lower,
            count=arguments.count,
            device=arguments.device,
            repetitions=arguments.repetitions,
            replay_threads=arguments.replay_threads,
            timeout_seconds=arguments.timeout_seconds,
        )
    except (
        CampaignIOError,
        OSError,
        R2StarBenchmarkError,
        ValueError,
    ) as error:
        print(f"R2Star benchmark error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
