#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Replay both historical source branches and emit the registered result."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.goldbach_campaign import (  # noqa: E402
    CampaignError,
    combine_with_hardened_binary_goldbach,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    require_azure_measured_worker_for_workload,
)


def write_registered_result(path: Path) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o400,
    )
    try:
        if os.write(descriptor, b"true") != 4:
            raise OSError("short registered-result write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("ladder", type=Path)
    result.add_argument("--ladder-aggregate", type=Path, required=True)
    result.add_argument("--binary-plan", type=Path, required=True)
    result.add_argument("--binary-receipts-dir", type=Path, required=True)
    result.add_argument("--binary-aggregate", type=Path, required=True)
    result.add_argument("--combined-out", type=Path, required=True)
    result.add_argument("--registered-result-output", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        # Replaying both complete historical branches is production work, not
        # ordinary receipt inspection.  Refuse it before opening artifacts.
        require_azure_measured_worker_for_workload(
            exact_production=True,
            work_bounds=(),
        )
        combine_with_hardened_binary_goldbach(
            args.ladder,
            ladder_aggregate_path=args.ladder_aggregate,
            binary_plan_path=args.binary_plan,
            binary_receipts_directory=args.binary_receipts_dir,
            binary_aggregate_path=args.binary_aggregate,
            output_path=args.combined_out,
        )
        write_registered_result(args.registered_result_output)
        return 0
    except (CampaignIOError, CampaignError, OSError, ValueError) as error:
        print(f"historical Goldbach finalizer error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
