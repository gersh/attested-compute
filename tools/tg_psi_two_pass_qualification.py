#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run or independently replay the bounded CH25 psi qualification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.psi_two_pass_qualification import (  # noqa: E402
    PsiTwoPassQualificationError,
    qualification_summary,
    run_qualification,
    verify_qualification,
)


def positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--candidate-runner", required=True, type=Path)
    common.add_argument("--baseline-runner", required=True, type=Path)
    common.add_argument("--runner-source", required=True, type=Path)
    common.add_argument("--upstream-manifest", required=True, type=Path)
    common.add_argument("--crlibm-shared", required=True, type=Path)

    result = argparse.ArgumentParser(
        description=(
            "Qualify CH25 psi summary/verify against the literal Python "
            "prime-power and directed-log oracle without claiming a source run."
        )
    )
    commands = result.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", parents=[common])
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--domain-upper-exclusive", required=True, type=positive)
    run.add_argument("--shard-span", required=True, type=positive)
    run.add_argument("--sieve-size-kib", type=positive, default=384)
    run.add_argument("--series-terms", type=positive, default=32)
    run.add_argument("--oracle-segment-size", type=positive, default=100_000)
    run.add_argument("--repeat-count", type=positive, default=3)
    run.add_argument("--performance-lower", required=True, type=positive)
    run.add_argument(
        "--performance-upper-exclusive", required=True, type=positive
    )
    run.add_argument("--performance-repeat-count", type=positive, default=3)
    run.add_argument("--timeout-seconds", type=positive)

    verify = commands.add_parser("verify", parents=[common])
    verify.add_argument("artifact", type=Path)
    verify.add_argument(
        "--no-regenerate-oracle",
        action="store_true",
        help="replay structure only; normal independent audit regenerates it",
    )
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.command == "run":
            artifact = run_qualification(
                candidate_runner=arguments.candidate_runner,
                baseline_runner=arguments.baseline_runner,
                runner_source=arguments.runner_source,
                upstream_manifest=arguments.upstream_manifest,
                crlibm_shared=arguments.crlibm_shared,
                output=arguments.output,
                domain_upper_exclusive=arguments.domain_upper_exclusive,
                shard_span=arguments.shard_span,
                sieve_size_kib=arguments.sieve_size_kib,
                series_terms=arguments.series_terms,
                oracle_segment_size=arguments.oracle_segment_size,
                repeat_count=arguments.repeat_count,
                performance_lower=arguments.performance_lower,
                performance_upper_exclusive=(
                    arguments.performance_upper_exclusive
                ),
                performance_repeat_count=arguments.performance_repeat_count,
                timeout_seconds=arguments.timeout_seconds,
            )
        else:
            artifact = verify_qualification(
                arguments.artifact,
                candidate_runner=arguments.candidate_runner,
                baseline_runner=arguments.baseline_runner,
                runner_source=arguments.runner_source,
                upstream_manifest=arguments.upstream_manifest,
                crlibm_shared=arguments.crlibm_shared,
                regenerate_oracle=not arguments.no_regenerate_oracle,
            )
    except PsiTwoPassQualificationError as exc:
        parser().error(str(exc))
    print(json.dumps(qualification_summary(artifact), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
