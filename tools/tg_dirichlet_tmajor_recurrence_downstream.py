#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run the bounded direct-vs-recurrence downstream qualification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_tmajor_recurrence_downstream import (  # noqa: E402
    DEFAULT_FACTOR_COUNT,
    DEFAULT_FIRST_T_INDEX,
    DEFAULT_QS,
    DirichletTMajorRecurrenceDownstreamError,
    run_qualification,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a bounded real-CUDA/MPFR/Arb downstream comparison of "
            "direct MPFR and certified t-major recurrence factors."
        )
    )
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--composition-runner",
        type=Path,
        default=(
            ROOT
            / "build/tg-production-kat/"
            "sparkinterval-tg-dirichlet-largeq-seeded"
        ),
    )
    parser.add_argument(
        "--allchars-runner",
        type=Path,
        default=(
            ROOT
            / "build/tg-production-kat/"
            "sparkinterval-tg-dirichlet-allchars"
        ),
    )
    parser.add_argument(
        "--allchars-checker",
        type=Path,
        default=(
            ROOT
            / "build/tg-production-kat/"
            "sparkinterval-tg-dirichlet-allchars-mpfr"
        ),
    )
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument(
        "--q",
        action="append",
        type=int,
        dest="qs",
        help="bounded consecutive-active modulus roster (at most two)",
    )
    parser.add_argument(
        "--first-t-index", type=int, default=DEFAULT_FIRST_T_INDEX
    )
    parser.add_argument("--count", type=int, default=DEFAULT_FACTOR_COUNT)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument(
        "--skip-arb-consumer",
        action="store_true",
        help=(
            "run only through CUDA plus independent MPFR transform replay; "
            "the report records that the Arb/FLINT consumer was skipped"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        report = run_qualification(
            arguments.output,
            composition_runner=arguments.composition_runner,
            allchars_runner=arguments.allchars_runner,
            allchars_checker=arguments.allchars_checker,
            device=arguments.device,
            qs=DEFAULT_QS if arguments.qs is None else tuple(arguments.qs),
            first_t_index=arguments.first_t_index,
            factor_count=arguments.count,
            run_arb_consumer=not arguments.skip_arb_consumer,
            timeout_seconds=arguments.timeout_seconds,
        )
    except (
        DirichletTMajorRecurrenceDownstreamError,
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        ValueError,
    ) as error:
        parser.error(str(error))
    print(
        json.dumps(
            report,
            sort_keys=True,
            indent=2 if arguments.pretty else None,
            separators=None if arguments.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
