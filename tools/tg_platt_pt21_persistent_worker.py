#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark the bounded persistent CUDA/FLINT/Arb PT21 finite chain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.platt_pt21_persistent_worker import (  # noqa: E402
    MAXIMUM_REQUESTS,
    PT21PersistentWorkerError,
    run_persistent_bounded_batch,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junction-executable", type=Path, required=True)
    parser.add_argument("--turing-executable", type=Path, required=True)
    parser.add_argument("--flint-library", type=Path, required=True)
    parser.add_argument("--finalizer-executable", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument(
        "--requests",
        type=int,
        default=3,
        choices=range(1, MAXIMUM_REQUESTS + 1),
    )
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    try:
        result = run_persistent_bounded_batch(
            junction_executable=arguments.junction_executable,
            turing_executable=arguments.turing_executable,
            flint_library=arguments.flint_library,
            finalizer_executable=arguments.finalizer_executable,
            output_directory=arguments.output_directory,
            request_count=arguments.requests,
        )
    except (
        OSError,
        ValueError,
        PT21PersistentWorkerError,
    ) as error:
        print(f"tg_platt_pt21_persistent_worker: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            result.report,
            sort_keys=True,
            indent=2 if arguments.pretty else None,
            separators=None if arguments.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
