#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Audit the ten TG Azure launch routes without cloud or campaign execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.azure_launch_preflight import (  # noqa: E402
    AzureLaunchPreflightError,
    build_preflight_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-cli-help",
        action="store_true",
        help=(
            "skip bounded materializer --help subprocesses; skipped CLIs are "
            "checked for path, executable bit, and shebang only"
        ),
    )
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = build_preflight_report(
            run_cli_help=not args.no_cli_help
        )
    except (AzureLaunchPreflightError, OSError, ValueError) as error:
        report = {
            "accepted": False,
            "classification": "azure_tg_launch_preflight_failed_closed",
            "error": str(error),
            "lean_atoms_discharged": 0,
        }
        exit_code = 2
    else:
        exit_code = 0
    print(
        json.dumps(
            report,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
