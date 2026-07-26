#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run or inspect the persistent large-q Dirichlet component pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_largeq_pipeline import (  # noqa: E402
    DirichletLargeQPipelineError,
    capability,
    run_pipeline,
    validate_control_alignment,
)
from tg_verifier.dirichlet_stream_zero_consumer import (  # noqa: E402
    COMPACT_EVENT_STORAGE_MODE,
    RAW_EVENT_STORAGE_MODE,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)


def _positive(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pretty", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("capability")

    preflight = commands.add_parser("preflight")
    preflight.add_argument("composition_controls", type=Path)
    preflight.add_argument("consumer_controls", type=Path)
    preflight.add_argument("--base", type=Path, default=Path.cwd())
    preflight.add_argument("--max-batch-count", type=_positive, default=64)
    preflight.add_argument("--allow-synthetic-kat", action="store_true")

    run = commands.add_parser("run")
    run.add_argument("composition_controls", type=Path)
    run.add_argument("consumer_controls", type=Path)
    run.add_argument("root_artifact", type=Path)
    run.add_argument("root_receipt", type=Path)
    run.add_argument("output_directory", type=Path)
    run.add_argument("pipeline_receipt", type=Path)
    run.add_argument("--base", type=Path, default=Path.cwd())
    run.add_argument("--composer-python", type=Path, default=Path(sys.executable))
    run.add_argument(
        "--composer-tool",
        type=Path,
        default=ROOT / "tools/tg_dirichlet_residue_composition.py",
    )
    run.add_argument("--allchars-runner", type=Path, required=True)
    run.add_argument("--consumer-python", type=Path, required=True)
    run.add_argument(
        "--consumer-tool",
        type=Path,
        default=ROOT / "tools/tg_dirichlet_stream_zero_consumer.py",
    )
    run.add_argument("--max-batch-count", type=_positive, default=64)
    run.add_argument("--device", type=int, default=0)
    run.add_argument("--precision", type=_positive, default=192)
    run.add_argument("--maximum-event-bytes", type=_positive)
    run.add_argument(
        "--event-storage-mode",
        choices=(RAW_EVENT_STORAGE_MODE, COMPACT_EVENT_STORAGE_MODE),
        default=RAW_EVENT_STORAGE_MODE,
    )
    run.add_argument("--allow-synthetic-kat", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "capability":
            answer = capability()
        elif args.command == "preflight":
            answer = validate_control_alignment(
                args.composition_controls,
                args.consumer_controls,
                base=args.base,
                maximum_batch_count=args.max_batch_count,
                allow_synthetic_kat=args.allow_synthetic_kat,
            ).__dict__
        elif args.command == "run":
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            if args.device < 0:
                raise DirichletLargeQPipelineError("device must be nonnegative")
            answer = run_pipeline(
                composition_controls=args.composition_controls,
                consumer_controls=args.consumer_controls,
                control_base=args.base,
                composer_python=args.composer_python,
                composer_tool=args.composer_tool,
                allchars_runner=args.allchars_runner,
                consumer_python=args.consumer_python,
                consumer_tool=args.consumer_tool,
                root_artifact=args.root_artifact,
                root_receipt=args.root_receipt,
                output_directory=args.output_directory,
                pipeline_receipt=args.pipeline_receipt,
                maximum_batch_count=args.max_batch_count,
                device=args.device,
                precision=args.precision,
                allow_synthetic_kat=args.allow_synthetic_kat,
                maximum_event_bytes=args.maximum_event_bytes,
                event_storage_mode=args.event_storage_mode,
            )
        else:  # pragma: no cover
            raise AssertionError(args.command)
    except (DirichletLargeQPipelineError, OSError, ValueError) as error:
        print(f"Dirichlet large-q pipeline error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(answer, sort_keys=True, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
