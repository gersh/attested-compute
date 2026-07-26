#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded GoldbachGPU/CPU-oracle comparison for a prepared build.

This is an executable integration test, not evidence for the production
``4 * 10^18`` endpoint.  It requires both reviewed upstream targets from the
same build and checks their exact successful range/count claims.  The GPU is
always invoked with the production segment, p-search, batch and MR settings.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.goldbach_gpu_campaign import (  # noqa: E402
    GoldbachGPUCampaignError,
    make_bounded_sample_plan,
    parse_runner_stdout,
    runner_arguments,
)


def _run(argv: list[str], label: str) -> bytes:
    completed = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=1800,
    )
    if completed.returncode != 0 or completed.stderr:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise GoldbachGPUCampaignError(
            f"{label} failed with status {completed.returncode}: {detail}"
        )
    return completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu-runner", type=Path, required=True)
    parser.add_argument("--cpu-runner", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100_000_000)
    args = parser.parse_args()
    try:
        if args.limit < 4 or args.limit % 2:
            raise GoldbachGPUCampaignError("bounded comparison limit must be even and >= 4")
        executable_sha256 = hashlib.sha256(args.gpu_runner.read_bytes()).hexdigest()
        plan = make_bounded_sample_plan(
            even_start=4,
            even_limit=args.limit,
            shard_count=1,
            executable_sha256=executable_sha256,
        )
        shard = plan.shards[0]
        gpu_raw = _run(
            [str(args.gpu_runner.resolve()), *runner_arguments(shard)],
            "GoldbachGPU",
        )
        gpu = parse_runner_stdout(gpu_raw, shard)

        cpu_raw = _run(
            [str(args.cpu_runner.resolve()), str(args.limit)], "CPU oracle"
        )
        cpu_text = cpu_raw.decode("utf-8")
        count_matches = re.findall(r"^Even numbers checked : ([0-9]+)$", cpu_text, re.M)
        failure_matches = re.findall(r"^Failures found       : ([0-9]+)$", cpu_text, re.M)
        final_line = f"All even numbers up to {args.limit} satisfy Goldbach. ✓"
        if (
            count_matches != [str(shard.even_count)]
            or failure_matches != ["0"]
            or cpu_text.count(final_line) != 1
        ):
            raise GoldbachGPUCampaignError("CPU oracle summary is malformed or disagrees")
        print(
            "goldbach_gpu_known_answers: "
            f"PASS limit={args.limit} evens={shard.even_count} "
            f"gpu_fallbacks={gpu['phase2_fallbacks']}"
        )
        return 0
    except (GoldbachGPUCampaignError, OSError, UnicodeError) as exc:
        print(f"goldbach_gpu_known_answers: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
