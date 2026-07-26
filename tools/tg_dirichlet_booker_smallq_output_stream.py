#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Reduce concatenated TGDBSQO3 frames from stdin, a FIFO, or a file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_booker_smallq_output_stream import (  # noqa: E402
    DEFAULT_CHUNK_ITEMS,
    SmallQOutputStreamError,
    reduce_factored_service_output_stream,
)
from tg_verifier.dirichlet_booker_smallq_factored import (  # noqa: E402
    FactoredSmallQError,
)
from tg_verifier.campaign_io import (  # noqa: E402
    MeasuredWorkerScopeError,
    require_azure_measured_worker_for_workload,
)


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("plan", type=Path)
    result.add_argument("batch_directory", type=Path)
    result.add_argument("receipt", type=Path)
    result.add_argument(
        "--input",
        type=Path,
        help="concatenated stream path/FIFO; omit to read standard input",
    )
    result.add_argument("--chunk-items", type=_positive, default=DEFAULT_CHUNK_ITEMS)
    result.add_argument("--backend", choices=("auto", "numpy", "scalar"), default="auto")
    result.add_argument("--pretty", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        require_azure_measured_worker_for_workload(
            exact_production=True,
            work_bounds=(),
        )
        batches = sorted(args.batch_directory.glob("batch-*.bin"))
        if args.input is None:
            value = reduce_factored_service_output_stream(
                args.plan,
                batches,
                sys.stdin.buffer,
                receipt_path=args.receipt,
                chunk_items=args.chunk_items,
                backend=args.backend,
            )
        else:
            with args.input.open("rb", buffering=0) as stream:
                value = reduce_factored_service_output_stream(
                    args.plan,
                    batches,
                    stream,
                    receipt_path=args.receipt,
                    chunk_items=args.chunk_items,
                    backend=args.backend,
                )
    except (
        OSError,
        FactoredSmallQError,
        SmallQOutputStreamError,
        MeasuredWorkerScopeError,
    ) as error:
        print(f"tg_dirichlet_booker_smallq_output_stream: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            value,
            indent=2 if args.pretty else None,
            sort_keys=True,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
