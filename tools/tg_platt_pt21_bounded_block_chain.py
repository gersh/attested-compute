#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run one explicitly synthetic CUDA/FLINT PT21 finite block chain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.platt_pt21_bounded_block_chain import (  # noqa: E402
    PT21BoundedBlockChainError,
    run_bounded_block_chain,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junction-executable", type=Path, required=True)
    parser.add_argument("--turing-executable", type=Path, required=True)
    parser.add_argument("--flint-library", type=Path, required=True)
    parser.add_argument("--finalizer-executable", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    try:
        result = run_bounded_block_chain(
            junction_executable=arguments.junction_executable,
            turing_executable=arguments.turing_executable,
            flint_library=arguments.flint_library,
            finalizer_executable=arguments.finalizer_executable,
            output_directory=arguments.output_directory,
        )
    except (
        OSError,
        ValueError,
        PT21BoundedBlockChainError,
    ) as error:
        print(f"tg_platt_pt21_bounded_block_chain: {error}", file=sys.stderr)
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
