#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Generate and independently check bounded factor-eight sign artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier import dirichlet_factor8_postprocess as factor8  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("work")
    coefficients = commands.add_parser("coefficients")
    coefficients.add_argument("output", type=Path)
    coefficients.add_argument("--precision", type=int, default=256)
    verify_coefficients = commands.add_parser("verify-coefficients")
    verify_coefficients.add_argument("artifact", type=Path)
    verify_coefficients.add_argument("--precision", type=int, default=320)
    verify = commands.add_parser("verify")
    verify.add_argument("coefficients", type=Path)
    verify.add_argument("input", type=Path)
    verify.add_argument("output", type=Path)
    verify.add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "work":
            result = factor8.work_audit()
        elif args.command == "coefficients":
            result = factor8.write_coefficient_artifact(
                args.output, precision=args.precision
            )
        elif args.command == "verify-coefficients":
            result = factor8.verify_coefficient_artifact(
                args.artifact, precision=args.precision
            )
        else:
            result = factor8.verify_output_artifact(
                args.coefficients, args.input, args.output
            )
            factor8._atomic_write(
                args.receipt, factor8.canonical_json_bytes(result)
            )
        print(json.dumps(result, sort_keys=True, indent=2 if args.pretty else None))
        return 0
    except (factor8.Factor8PostprocessError, OSError) as error:
        print(f"tg_dirichlet_factor8_postprocess: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
