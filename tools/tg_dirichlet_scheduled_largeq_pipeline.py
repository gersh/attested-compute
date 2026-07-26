#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run or replay the TGDQORD1 Dirichlet producer/FFT/consumer graph."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_scheduled_largeq_pipeline import (  # noqa: E402
    DEFAULT_KAT_CAPTURE_BYTES,
    DEFAULT_REPLAY_PROCESS_TIMEOUT_SECONDS,
    DirichletScheduledPipelineError,
    capability,
    replay_scheduled_pipeline,
    run_scheduled_pipeline,
)


def positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def positive_seconds(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return parsed


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pretty", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("capability")
    run = commands.add_parser("run")
    run.add_argument("composition_controls", type=Path)
    run.add_argument("consumer_controls", type=Path)
    run.add_argument("schedule_manifest", type=Path)
    run.add_argument("control_base", type=Path)
    run.add_argument("composer_python", type=Path)
    run.add_argument("composer_tool", type=Path)
    run.add_argument("allchars_runner", type=Path)
    run.add_argument("consumer_python", type=Path)
    run.add_argument("consumer_tool", type=Path)
    run.add_argument("root_catalog", type=Path)
    run.add_argument("root_catalog_sha256")
    run.add_argument("root_catalog_directory", type=Path)
    run.add_argument("output_directory", type=Path)
    run.add_argument("pipeline_receipt", type=Path)
    run.add_argument("--maximum-batch-count", type=positive, default=64)
    run.add_argument("--device", type=int, default=0)
    run.add_argument("--precision", type=positive, default=192)
    run.add_argument("--require-full-source", action="store_true")
    run.add_argument("--allow-synthetic-kat", action="store_true")
    run.add_argument("--no-retained-bounded-streams", action="store_true")
    run.add_argument(
        "--maximum-capture-bytes",
        type=positive,
        default=DEFAULT_KAT_CAPTURE_BYTES,
    )
    run.add_argument("--process-timeout-seconds", type=positive_seconds)

    replay = commands.add_parser("replay")
    replay.add_argument("pipeline_receipt", type=Path)
    replay.add_argument("composer_python", type=Path)
    replay.add_argument("composer_tool", type=Path)
    replay.add_argument("allchars_checker", type=Path)
    replay.add_argument("consumer_python", type=Path)
    replay.add_argument("consumer_tool", type=Path)
    replay.add_argument("control_base", type=Path)
    replay.add_argument("--precision", type=positive, default=192)
    replay.add_argument("--allow-synthetic-kat", action="store_true")
    replay.add_argument(
        "--process-timeout-seconds",
        type=positive_seconds,
        default=DEFAULT_REPLAY_PROCESS_TIMEOUT_SECONDS,
    )
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "capability":
            answer = capability()
        elif args.command == "run":
            answer = run_scheduled_pipeline(
                composition_controls=args.composition_controls,
                consumer_controls=args.consumer_controls,
                schedule_manifest=args.schedule_manifest,
                control_base=args.control_base,
                composer_python=args.composer_python,
                composer_tool=args.composer_tool,
                allchars_runner=args.allchars_runner,
                consumer_python=args.consumer_python,
                consumer_tool=args.consumer_tool,
                root_catalog=args.root_catalog,
                root_catalog_sha256=args.root_catalog_sha256,
                root_catalog_directory=args.root_catalog_directory,
                output_directory=args.output_directory,
                pipeline_receipt=args.pipeline_receipt,
                maximum_batch_count=args.maximum_batch_count,
                device=args.device,
                precision=args.precision,
                require_full_source=args.require_full_source,
                allow_synthetic_kat=args.allow_synthetic_kat,
                retain_bounded_streams=(
                    not args.no_retained_bounded_streams
                ),
                maximum_capture_bytes=args.maximum_capture_bytes,
                process_timeout_seconds=args.process_timeout_seconds,
            )
        elif args.command == "replay":
            answer = replay_scheduled_pipeline(
                args.pipeline_receipt,
                composer_python=args.composer_python,
                composer_tool=args.composer_tool,
                allchars_checker=args.allchars_checker,
                consumer_python=args.consumer_python,
                consumer_tool=args.consumer_tool,
                control_base=args.control_base,
                precision=args.precision,
                allow_synthetic_kat=args.allow_synthetic_kat,
                process_timeout_seconds=args.process_timeout_seconds,
            )
        else:  # pragma: no cover
            raise AssertionError(args.command)
    except (DirichletScheduledPipelineError, OSError, ValueError) as error:
        print(f"tg_dirichlet_scheduled_largeq_pipeline: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            answer,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
