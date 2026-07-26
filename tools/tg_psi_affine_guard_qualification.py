#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run or replay the all-event CH25 psi affine qualification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.psi_affine_guard_qualification import (  # noqa: E402
    PsiAffineQualificationError,
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
    common.add_argument("--affine-runner", required=True, type=Path)
    common.add_argument("--two-pass-runner", required=True, type=Path)
    common.add_argument("--affine-source", required=True, type=Path)
    common.add_argument("--two-pass-source", required=True, type=Path)
    common.add_argument("--crlibm-shared", required=True, type=Path)
    common.add_argument("--upstream-manifest", required=True, type=Path)
    common.add_argument("--build-manifest", required=True, type=Path)

    result = argparse.ArgumentParser(
        description=(
            "Qualify every event in a bounded one-pass CH25 psi affine guard."
        )
    )
    commands = result.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", parents=[common])
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--lower", required=True, type=positive)
    run.add_argument("--upper-exclusive", required=True, type=positive)
    run.add_argument("--sieve-size-kib", type=positive, default=384)
    run.add_argument("--segment-size", type=positive, default=100_000)
    run.add_argument("--repeat-count", type=positive, default=2)
    run.add_argument("--timeout-seconds", type=positive, default=120)

    verify = commands.add_parser("verify", parents=[common])
    verify.add_argument("artifact", type=Path)
    verify.add_argument(
        "--no-regenerate-oracle",
        action="store_true",
        help="check retained structure only; normal replay folds every event",
    )
    return result


def main() -> int:
    arguments = parser().parse_args()
    common = {
        "affine_runner": arguments.affine_runner,
        "two_pass_runner": arguments.two_pass_runner,
        "affine_source": arguments.affine_source,
        "two_pass_source": arguments.two_pass_source,
        "crlibm_shared": arguments.crlibm_shared,
        "upstream_manifest": arguments.upstream_manifest,
        "build_manifest": arguments.build_manifest,
    }
    try:
        if arguments.command == "run":
            artifact = run_qualification(
                **common,
                output=arguments.output,
                lower=arguments.lower,
                upper_exclusive=arguments.upper_exclusive,
                sieve_size_kib=arguments.sieve_size_kib,
                segment_size=arguments.segment_size,
                repeat_count=arguments.repeat_count,
                timeout_seconds=arguments.timeout_seconds,
            )
        else:
            artifact = verify_qualification(
                arguments.artifact,
                **common,
                regenerate_oracle=not arguments.no_regenerate_oracle,
            )
    except PsiAffineQualificationError as exc:
        parser().error(str(exc))
    print(json.dumps(qualification_summary(artifact), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
