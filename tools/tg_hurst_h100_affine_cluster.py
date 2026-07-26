#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run or replay the independent eight-H100 Hurst affine computation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.hurst_h100_affine_cluster import (  # noqa: E402
    HurstH100AffineClusterError,
    PRODUCTION_WORKER_COUNT,
    prepare_distributed,
    reduce_distributed,
    run,
    run_distributed_worker,
    verify,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    execute = commands.add_parser(
        "run",
        help="bounded/local multi-GPU harness (not Azure production)",
    )
    execute.add_argument("materialization", type=Path)
    execute.add_argument("--output-dir", required=True, type=Path)
    execute.add_argument(
        "--worker-count", type=int, default=PRODUCTION_WORKER_COUNT
    )
    execute.add_argument(
        "--device-selectors",
        default=None,
        help="comma-separated CUDA_VISIBLE_DEVICES routing indices",
    )
    execute.add_argument(
        "--cpu-timeout-seconds", type=int, default=7 * 24 * 3600
    )
    execute.add_argument(
        "--h100-timeout-seconds", type=int, default=7 * 24 * 3600
    )

    prepare = commands.add_parser(
        "prepare",
        help="prepare CPU handoff and one-H100-per-node worker commands",
    )
    prepare.add_argument("materialization", type=Path)
    prepare.add_argument("--output-dir", required=True, type=Path)
    prepare.add_argument(
        "--worker-count", type=int, default=PRODUCTION_WORKER_COUNT
    )
    prepare.add_argument(
        "--cpu-timeout-seconds", type=int, default=7 * 24 * 3600
    )

    worker = commands.add_parser(
        "run-worker", help="run one prepared shard on one H100 node"
    )
    worker.add_argument("materialization", type=Path)
    worker.add_argument("prepared", type=Path)
    worker.add_argument("--worker-index", required=True, type=int)
    worker.add_argument("--output-dir", required=True, type=Path)
    worker.add_argument(
        "--h100-timeout-seconds", type=int, default=7 * 24 * 3600
    )

    reduce = commands.add_parser(
        "reduce", help="replay worker bundles and compose exact M/Q extrema"
    )
    reduce.add_argument("materialization", type=Path)
    reduce.add_argument("prepared", type=Path)
    reduce.add_argument("--worker-dir", action="append", required=True, type=Path)
    reduce.add_argument("--output-dir", required=True, type=Path)

    replay = commands.add_parser(
        "verify", help="replay retained CPU controls and H100 JSONL streams"
    )
    replay.add_argument("materialization", type=Path)
    replay.add_argument("output", type=Path)
    replay.add_argument(
        "--skip-stream-replay",
        action="store_true",
        help="check pins and affine controls without rereading every leaf",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "run":
            selectors = (
                None
                if arguments.device_selectors is None
                else tuple(arguments.device_selectors.split(","))
            )
            result = run(
                materialization_directory=arguments.materialization,
                output_directory=arguments.output_dir,
                worker_count=arguments.worker_count,
                device_selectors=selectors,
                cpu_timeout_seconds=arguments.cpu_timeout_seconds,
                h100_timeout_seconds=arguments.h100_timeout_seconds,
            )
        elif arguments.command == "prepare":
            result = prepare_distributed(
                materialization_directory=arguments.materialization,
                output_directory=arguments.output_dir,
                worker_count=arguments.worker_count,
                cpu_timeout_seconds=arguments.cpu_timeout_seconds,
            )
        elif arguments.command == "run-worker":
            result = run_distributed_worker(
                materialization_directory=arguments.materialization,
                prepared_directory=arguments.prepared,
                worker_index=arguments.worker_index,
                output_directory=arguments.output_dir,
                h100_timeout_seconds=arguments.h100_timeout_seconds,
            )
        elif arguments.command == "reduce":
            result = reduce_distributed(
                materialization_directory=arguments.materialization,
                prepared_directory=arguments.prepared,
                worker_directories=arguments.worker_dir,
                output_directory=arguments.output_dir,
            )
        else:
            result = verify(
                materialization_directory=arguments.materialization,
                output_directory=arguments.output,
                replay_streams=not arguments.skip_stream_replay,
            )
    except HurstH100AffineClusterError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
