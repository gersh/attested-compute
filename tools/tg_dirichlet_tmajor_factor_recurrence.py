#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""CLI for the bounded t-major factor-recurrence qualification artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_tmajor_factor_recurrence import (
    DirichletTMajorFactorRecurrenceError,
    benchmark,
    verify_artifact,
    verify_artifact_file_with_arb,
    write_artifact,
)


def _render(value: object, *, pretty: bool) -> None:
    print(
        json.dumps(
            value,
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build and replay bounded TGDFREC1 q^(-1/2-it) "
            "factor-recurrence qualification artifacts."
        )
    )
    parser.add_argument("--pretty", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("output", type=Path)
    build.add_argument("--q", type=int, required=True)
    build.add_argument("--first-t-index", type=int, required=True)
    build.add_argument("--count", type=int, default=64)

    verify = subparsers.add_parser("verify")
    verify.add_argument("artifact", type=Path)
    verify.add_argument("--expected-sha256")
    verify.add_argument("--full-direct-mpfr", action="store_true")

    arb = subparsers.add_parser("verify-arb")
    arb.add_argument("artifact", type=Path)
    arb.add_argument("--expected-sha256")
    arb.add_argument("--precision-bits", type=int, default=384)
    arb.add_argument(
        "--frame",
        action="append",
        type=int,
        dest="frames",
        help=(
            "check this zero-based frame; repeat for a sorted unique spot "
            "set, or omit to check every bounded frame"
        ),
    )

    timing = subparsers.add_parser("benchmark")
    timing.add_argument("--q", type=int, default=10_001)
    timing.add_argument("--first-t-index", type=int, default=0)
    timing.add_argument("--count", type=int, default=64)
    timing.add_argument("--repetitions", type=int, default=8)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "build":
            report = write_artifact(
                arguments.output,
                q=arguments.q,
                first_t_index=arguments.first_t_index,
                count=arguments.count,
            )
        elif arguments.command == "verify":
            report = verify_artifact(
                arguments.artifact,
                expected_sha256=arguments.expected_sha256,
                full_direct_mpfr=arguments.full_direct_mpfr,
            )
        elif arguments.command == "verify-arb":
            report = verify_artifact_file_with_arb(
                arguments.artifact,
                expected_sha256=arguments.expected_sha256,
                precision_bits=arguments.precision_bits,
                frame_indices=(
                    None
                    if arguments.frames is None
                    else tuple(arguments.frames)
                ),
            )
        else:
            report = benchmark(
                q=arguments.q,
                first_t_index=arguments.first_t_index,
                count=arguments.count,
                repetitions=arguments.repetitions,
            )
    except (
        DirichletTMajorFactorRecurrenceError,
        OSError,
        ValueError,
    ) as error:
        parser.error(str(error))
    _render(report, pretty=arguments.pretty)
    return 0


if __name__ == "__main__":
    sys.exit(main())
