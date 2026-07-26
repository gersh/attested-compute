#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independent bounded contracts for the pinned Hurst Möbius adapter.

The production runner is deliberately able to start a sieve at an arbitrary
shard boundary.  These tests compare its four transition components with the
repository's independent linear sieve, require summary/verification replay to
commit the same rows, and exercise a non-root incoming prefix.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tg_verifier.arithmetic import mobius_linear


SCALE = 1 << 96


def run(
    runner: Path,
    mode: str,
    lower: int,
    upper: int,
    incoming=None,
    *,
    threads: int | None = None,
) -> dict:
    command = [
        str(runner),
        "--mode",
        mode,
        "--lower",
        str(lower),
        "--upper",
        str(upper),
        "--segment-size",
        str(upper - lower + 1),
    ]
    if incoming is not None:
        names = (
            "--incoming-mertens",
            "--incoming-squarefree",
            "--incoming-little-lower",
            "--incoming-little-upper",
        )
        for name, value in zip(names, incoming, strict=True):
            command.extend((name, str(value)))
    environment = os.environ.copy()
    if threads is not None:
        environment["OMP_NUM_THREADS"] = str(threads)
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"runner failed ({completed.returncode}): {completed.stderr!r}"
        )
    value = json.loads(completed.stdout)
    if value.get("accepted") is not True:
        raise AssertionError("runner did not return an accepted exact shard")
    if value.get("algorithm") != "hurst-segmented-mobius-two-pass-v2":
        raise AssertionError("runner does not use the reviewed V2 Hurst semantics")
    if (
        value.get("squarefree_threshold_endpoint_policy")
        != "inclusive-value-and-right-limit-v2"
    ):
        raise AssertionError(
            "runner does not check both squarefree threshold endpoints"
        )
    return value


def independent_deltas(mu: list[int], lower: int, upper: int) -> list[int]:
    mertens = squarefree = little_lower = little_upper = 0
    for n in range(lower, upper + 1):
        row = mu[n]
        mertens += row
        squarefree += abs(row)
        floor = SCALE // n
        ceil = floor + int(SCALE % n != 0)
        if row > 0:
            little_lower += floor
            little_upper += ceil
        elif row < 0:
            little_lower -= ceil
            little_upper -= floor
    return [mertens, squarefree, little_lower, little_upper]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", required=True, type=Path)
    arguments = parser.parse_args()
    if not arguments.runner.is_file():
        raise AssertionError(f"missing Hurst adapter: {arguments.runner}")

    limit = 500_000
    split = 250_000
    mu = mobius_linear(limit)
    expected = independent_deltas(mu, 1, limit)
    expected_left = independent_deltas(mu, 1, split)
    expected_right = independent_deltas(mu, split + 1, limit)

    whole_summary = run(arguments.runner, "summary", 1, limit)
    whole_verify = run(arguments.runner, "verify", 1, limit)
    if whole_summary["delta"] != expected or whole_verify["delta"] != expected:
        raise AssertionError("Hurst adapter differs from the independent linear sieve")
    if whole_summary["row_sha256"] != whole_verify["row_sha256"]:
        raise AssertionError("summary and verification passes commit different rows")

    left = run(arguments.runner, "summary", 1, split)
    right = run(arguments.runner, "summary", split + 1, limit)
    right_verify = run(
        arguments.runner, "verify", split + 1, limit, incoming=expected_left
    )
    right_affine = run(arguments.runner, "affine", split + 1, limit)
    if left["delta"] != expected_left or right["delta"] != expected_right:
        raise AssertionError("independent shard summaries have incorrect transitions")
    if right_verify["delta"] != expected_right:
        raise AssertionError("non-root verification changed the shard transition")
    if right_affine["delta"] != expected_right:
        raise AssertionError("affine mode changed the independent shard transition")
    if right_verify["row_sha256"] != right["row_sha256"]:
        raise AssertionError("non-root replay commits a different Möbius shard")
    if right_affine["row_sha256"] != right["row_sha256"]:
        raise AssertionError("affine mode commits a different Möbius shard")
    for atom, guard in right_affine["guards"].items():
        if not all(
            lower <= value <= upper
            for value, lower, upper in zip(
                expected_left, guard["lower"], guard["upper"], strict=True
            )
        ):
            raise AssertionError(
                f"independent root-derived input is outside the {atom} affine guard"
            )
    if [a + b for a, b in zip(left["delta"], right["delta"], strict=True)] != expected:
        raise AssertionError("split transition composition differs from the whole range")

    # This incoming state is safe at the right limit 438430 but not at the
    # strict-real threshold value 438429.  The old V1 worker accepted it;
    # V2 must reject it, which makes the endpoint-policy regression semantic
    # rather than merely a check of a self-reported receipt string.
    threshold_command = [
        str(arguments.runner),
        "--mode",
        "verify",
        "--lower",
        "438429",
        "--upper",
        "438429",
        "--segment-size",
        "13860",
        "--incoming-mertens",
        "0",
        "--incoming-squarefree",
        "266551",
        "--incoming-little-lower",
        "0",
        "--incoming-little-upper",
        "0",
    ]
    threshold_result = subprocess.run(
        threshold_command, text=True, capture_output=True, check=False
    )
    if threshold_result.returncode == 0:
        raise AssertionError("runner skipped the squarefree threshold value")
    if "cdem-squarefree failed at n=438429" not in threshold_result.stderr:
        raise AssertionError("runner rejected the V2 boundary fixture unexpectedly")

    # Affine guards are reduced over fixed 2^20-row blocks.  Cross that
    # boundary and require canonical block-order reduction to be exactly
    # independent of the OpenMP worker count.  The production two-pass
    # supervisor intentionally rejects affine-mode receipts; this is a
    # deterministic capability test for the source-shaped one-pass path.
    affine_upper = (1 << 20) + 32_768
    affine_serial = run(
        arguments.runner, "affine", 1, affine_upper, threads=1
    )
    affine_parallel = run(
        arguments.runner, "affine", 1, affine_upper, threads=4
    )
    for receipt in (affine_serial, affine_parallel):
        receipt.pop("elapsed_seconds", None)
    if affine_serial != affine_parallel:
        raise AssertionError("affine guard certificate depends on OpenMP scheduling")
    for atom, guard in affine_serial["guards"].items():
        if not all(
            lower <= 0 <= upper
            for lower, upper in zip(guard["lower"], guard["upper"], strict=True)
        ):
            raise AssertionError(f"zero root state is outside the {atom} affine guard")

    print("Pinned Hurst residual adapter known-answer tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
