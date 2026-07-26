#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independent known answers for the exact Prop. 12.2.4 factor shard."""

from __future__ import annotations

import argparse
import hashlib
import json
from math import isqrt
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.prop1224_factor_plan import (  # noqa: E402
    leaf_from_runner_report,
    make_factor_plan,
    q_at_rank,
    verify_factor_leaves,
)


DOMAIN = b"sparkinterval/tg/prop1224/factor-rows/v1\0"


def distinct_factors(value: int) -> tuple[int, ...]:
    factors: list[int] = []
    remainder = value
    divisor = 2
    while divisor * divisor <= remainder:
        if remainder % divisor == 0:
            factors.append(divisor)
            while remainder % divisor == 0:
                remainder //= divisor
        divisor = 3 if divisor == 2 else divisor + 2
    if remainder > 1:
        factors.append(remainder)
    return tuple(factors)


def expected_report_fields(lower: int, upper: int) -> tuple[str, int]:
    digest = hashlib.sha256(DOMAIN)
    phi_sum = 0
    for rank in range(lower, upper):
        q = q_at_rank(rank)
        factors = distinct_factors(q)
        phi = q
        for prime in factors:
            phi -= phi // prime
        phi_sum += phi
        encoded = ",".join(str(prime) for prime in factors)
        digest.update(f"Q:{rank}:{q}:{phi}:{encoded}\n".encode("ascii"))
    return digest.hexdigest(), phi_sum


def run(runner: Path, lower: int, upper: int, block_rows: int) -> dict[str, object]:
    completed = subprocess.run(
        [
            str(runner),
            "--rank-lower",
            str(lower),
            "--rank-upper",
            str(upper),
            "--block-rows",
            str(block_rows),
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    report = json.loads(completed.stdout)
    if not isinstance(report, dict):
        raise AssertionError("runner did not emit a JSON object")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", required=True, type=Path)
    args = parser.parse_args()

    # Covers q=1, repeated prime powers, the dense/210 scheduler transition,
    # and the final source rows.  Different block sizes must commit to the
    # same row stream.
    ranges = (
        (0, 64),
        (3_299_999_990, 3_300_000_012),
        (3_389_047_600, 3_389_047_618),
    )
    for lower, upper in ranges:
        expected_digest, expected_phi_sum = expected_report_fields(lower, upper)
        first = run(args.runner, lower, upper, 7)
        second = run(args.runner, lower, upper, max(1, upper - lower))
        if first["row_root_sha256"] != expected_digest:
            raise AssertionError(f"wrong row digest for [{lower},{upper})")
        if int(first["phi_sum"]) != expected_phi_sum:
            raise AssertionError(f"wrong phi sum for [{lower},{upper})")
        if second["row_root_sha256"] != expected_digest:
            raise AssertionError("row digest changed with block size")

        plan = make_factor_plan(
            rank_lower=lower,
            rank_upper=upper,
            leaf_rows=upper - lower,
        )
        leaves = tuple(
            leaf_from_runner_report(
                plan=plan,
                shard_index=shard.index,
                report=run(args.runner, shard.lower, shard.upper, 7),
            )
            for shard in plan.shards
        )
        verification = verify_factor_leaves(plan=plan, leaves=leaves)
        if verification.final_state != (upper,):
            raise AssertionError("fixed-plan final rank is wrong")

    rejected = subprocess.run(
        [str(args.runner), "--rank-lower", "4", "--rank-upper", "4"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if rejected.returncode == 0 or "require" not in rejected.stderr:
        raise AssertionError("runner accepted an empty source-rank range")

    # Independent sanity check on the exact scheduler endpoint.
    if q_at_rank(3_389_047_618) != 22_000_000_000:
        raise AssertionError("terminal source scheduler value changed")
    if isqrt(q_at_rank(3_299_999_998)) != 57_445:
        raise AssertionError("dense prime-table limit known answer changed")
    print("Proposition 12.2.4 exact factor shard known answers passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
