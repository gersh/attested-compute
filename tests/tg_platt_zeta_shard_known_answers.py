#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Small and source-height known answers for tg_platt_zeta_shard."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def run(runner: Path, *arguments: str) -> dict[str, object]:
    result = subprocess.run(
        [str(runner), *arguments],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=dict(os.environ),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "runner failed")
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runner", type=Path)
    args = parser.parse_args()
    try:
        count = run(
            args.runner,
            "--engine", "count",
            "--height", "3000175332800",
            "--expected-count", "12363153437138",
            "--precision", "96",
            "--threads", "1",
        )
        if count["multiplicity_count"] != 12_363_153_437_138:
            raise RuntimeError("source-height multiplicity count changed")
        isolate = run(
            args.runner,
            "--engine", "platt-isolate",
            "--first-index", "10000",
            "--count", "3",
            "--micro-batch", "4096",
            "--precision", "96",
            "--threads", "1",
        )
        if isolate["record_count"] != 3 or isolate["simplicity_assumed"] is not False:
            raise RuntimeError("small Platt isolation changed")
        refined = run(
            args.runner,
            "--engine", "platt-zeta-replay",
            "--first-index", "10000",
            "--count", "3",
            "--micro-batch", "4096",
            "--precision", "96",
            "--threads", "1",
        )
        if refined["record_count"] != 3 or refined["critical_line_certified"] is not True:
            raise RuntimeError("named Platt API replay changed")
    except (OSError, RuntimeError, json.JSONDecodeError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "accepted": True,
                "source_height_count": count["multiplicity_count"],
                "small_isolation_sha256": isolate["interval_rows_sha256"],
                "small_refined_sha256": refined["interval_rows_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
