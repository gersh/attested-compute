#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build or independently replay a typed Dirichlet FFT pipeline bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_fft_pipeline_bundle import (  # noqa: E402
    DirichletFFTPipelineBundleError,
    build_bundle,
    capability,
    replay_bundle,
)


def _nonnegative(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return value


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

    build = commands.add_parser("build")
    build.add_argument("contract", type=Path)
    build.add_argument("pipeline_receipt", type=Path)
    build.add_argument("output", type=Path)
    build.add_argument("--lane-index", type=_nonnegative, required=True)
    build.add_argument("--q", type=_positive, required=True)
    build.add_argument("--first-t-index", type=_nonnegative, required=True)
    build.add_argument("--control-base", type=Path)
    build.add_argument("--expected-contract-sha256")
    build.add_argument("--expected-pipeline-file-sha256")
    build.add_argument("--allow-structural-kat", action="store_true")

    replay = commands.add_parser("replay")
    replay.add_argument("contract", type=Path)
    replay.add_argument("bundle", type=Path)
    replay.add_argument("--control-base", type=Path)
    replay.add_argument("--expected-bundle-sha256")
    replay.add_argument("--expected-contract-sha256")
    replay.add_argument("--allow-structural-kat", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "capability":
            answer = capability()
        elif args.command == "build":
            answer = build_bundle(
                args.output,
                contract_path=args.contract,
                lane_index=args.lane_index,
                q=args.q,
                first_t_index=args.first_t_index,
                pipeline_receipt_path=args.pipeline_receipt,
                control_base=args.control_base,
                allow_structural_kat=args.allow_structural_kat,
                expected_contract_sha256=args.expected_contract_sha256,
                expected_pipeline_file_sha256=(
                    args.expected_pipeline_file_sha256
                ),
            )
        elif args.command == "replay":
            answer = replay_bundle(
                args.bundle,
                contract_path=args.contract,
                control_base=args.control_base,
                allow_structural_kat=args.allow_structural_kat,
                expected_bundle_sha256=args.expected_bundle_sha256,
                expected_contract_sha256=args.expected_contract_sha256,
            )
        else:  # pragma: no cover
            raise AssertionError(args.command)
    except (DirichletFFTPipelineBundleError, OSError, ValueError) as error:
        print(f"Dirichlet typed FFT bundle error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            answer,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
