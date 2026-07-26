#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Generate or audit the packed segmented-sieve roster certificate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.mobius_segmented_sieve_roster import (  # noqa: E402
    DEFAULT_CHUNK_ROWS,
    PRODUCTION_BOUND,
    generate,
    report_dict,
    verify,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation", choices=("generate", "check")
    )
    parser.add_argument("factor_codes", type=Path)
    parser.add_argument("roster", type=Path)
    parser.add_argument("--bound", type=int, default=PRODUCTION_BOUND)
    parser.add_argument(
        "--chunk-rows", type=int, default=DEFAULT_CHUNK_ROWS
    )
    parser.add_argument(
        "--require-production-identity", action="store_true"
    )
    arguments = parser.parse_args()

    if arguments.operation == "generate":
        report = generate(
            arguments.bound,
            arguments.factor_codes,
            arguments.roster,
            chunk_rows=arguments.chunk_rows,
        )
        if arguments.require_production_identity:
            report = verify(
                arguments.bound,
                arguments.factor_codes,
                arguments.roster,
                chunk_rows=arguments.chunk_rows,
                require_production_identity=True,
            )
    else:
        report = verify(
            arguments.bound,
            arguments.factor_codes,
            arguments.roster,
            chunk_rows=arguments.chunk_rows,
            require_production_identity=(
                arguments.require_production_identity
            ),
        )
    print(json.dumps(report_dict(report), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
