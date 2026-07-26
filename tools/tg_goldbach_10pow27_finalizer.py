#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Measured CPU finalizer for the registered Goldbach-below-10^27 run.

Success writes exactly ``true`` plus a newline to stdout.  Every branch is
replayed before that byte is emitted; all failures are nonzero and write only
to stderr.  The retained combined JSON binds the two exact aggregates.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.goldbach_10pow27_campaign import (  # noqa: E402
    Goldbach10Pow27CampaignError,
    combine_branches,
)
from tg_verifier.goldbach_campaign import CampaignError  # noqa: E402
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    require_azure_measured_worker_for_workload,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ladder_directory", type=Path)
    parser.add_argument("--ladder-aggregate", type=Path, required=True)
    parser.add_argument("--binary-plan", type=Path, required=True)
    parser.add_argument("--binary-receipts-dir", type=Path, required=True)
    parser.add_argument("--binary-aggregate", type=Path, required=True)
    parser.add_argument("--general-prime-checker", type=Path)
    parser.add_argument("--combined-out", type=Path, required=True)
    parser.add_argument(
        "--registered-result-output",
        type=Path,
        help=(
            "immutably write the closed registered-invocation literal true "
            "only after both complete branches replay"
        ),
    )
    return parser


def write_registered_result(path: Path) -> None:
    """Install the exact registered result without following an existing link."""

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o400,
        )
    except FileExistsError:
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        except OSError as exc:
            raise Goldbach10Pow27CampaignError(
                "existing registered-result output is unsafe"
            ) from exc
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or stat.S_IMODE(metadata.st_mode) != 0o400
                or metadata.st_size != 4
                or os.read(descriptor, 5) != b"true"
                or os.read(descriptor, 1)
            ):
                raise Goldbach10Pow27CampaignError(
                    "existing registered-result output differs"
                )
        finally:
            os.close(descriptor)
        return
    try:
        if os.write(descriptor, b"true") != 4:
            raise Goldbach10Pow27CampaignError("short registered-result write")
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        # This finalizer performs both complete arithmetic replays.  Require
        # measured scope before reading either predecessor or writing output.
        require_azure_measured_worker_for_workload(
            exact_production=True,
            work_bounds=(),
        )
        combine_branches(
            args.ladder_directory,
            ladder_aggregate_path=args.ladder_aggregate,
            binary_plan_path=args.binary_plan,
            binary_receipts_directory=args.binary_receipts_dir,
            binary_aggregate_path=args.binary_aggregate,
            output_path=args.combined_out,
            external_prime_checker=args.general_prime_checker,
        )
        if args.registered_result_output is not None:
            write_registered_result(args.registered_result_output)
    except (
        CampaignIOError,
        Goldbach10Pow27CampaignError,
        CampaignError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"Goldbach 10^27 finalizer error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write("true\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
