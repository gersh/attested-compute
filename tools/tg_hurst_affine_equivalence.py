#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run or replay the bounded Hurst affine/two-pass qualification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.hurst_affine_equivalence import (  # noqa: E402
    HurstAffineEquivalenceError,
    qualification_summary,
    run_qualification,
    verify_qualification,
)


def positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def root_state(value: str) -> tuple[int, int, int, int]:
    pieces = value.split(",")
    if len(pieces) != 4:
        raise argparse.ArgumentTypeError(
            "root state must contain four comma-separated integers"
        )
    try:
        return tuple(int(piece) for piece in pieces)  # type: ignore[return-value]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "root state contains a non-integer coordinate"
        ) from exc


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--runner", required=True, type=Path)
    common.add_argument("--runner-source", required=True, type=Path)
    common.add_argument("--upstream-manifest", required=True, type=Path)

    result = argparse.ArgumentParser(
        description=(
            "Cross-check bounded Hurst summary, verify, and affine outputs. "
            "This command never claims source-scale completion."
        )
    )
    commands = result.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", parents=[common])
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--domain-lower", required=True, type=positive)
    run.add_argument("--domain-upper-exclusive", required=True, type=positive)
    run.add_argument("--shard-span", required=True, type=positive)
    run.add_argument("--segment-size", required=True, type=positive)
    run.add_argument("--repeat-count", type=positive, default=3)
    run.add_argument("--runner-threads", type=positive, default=1)
    run.add_argument("--timeout-seconds", type=positive)
    run.add_argument(
        "--root-state",
        type=root_state,
        help=(
            "explicit M,Q,little-lower,little-upper root; by default zero is "
            "clamped into the exact translated affine-guard intersection"
        ),
    )

    verify = commands.add_parser("verify", parents=[common])
    verify.add_argument("artifact", type=Path)
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.command == "run":
            artifact = run_qualification(
                runner=arguments.runner,
                runner_source=arguments.runner_source,
                upstream_manifest=arguments.upstream_manifest,
                output=arguments.output,
                domain_lower=arguments.domain_lower,
                domain_upper_exclusive=arguments.domain_upper_exclusive,
                shard_span=arguments.shard_span,
                segment_size=arguments.segment_size,
                repeat_count=arguments.repeat_count,
                runner_threads=arguments.runner_threads,
                timeout_seconds=arguments.timeout_seconds,
                root_state=arguments.root_state,
            )
        else:
            artifact = verify_qualification(
                arguments.artifact,
                runner=arguments.runner,
                runner_source=arguments.runner_source,
                upstream_manifest=arguments.upstream_manifest,
            )
    except HurstAffineEquivalenceError as exc:
        parser().error(str(exc))
    print(json.dumps(qualification_summary(artifact), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
