#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Known answers for the rigorous MPFR Proposition 12.2.4 q shard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.prop1224_mpfr_campaign import (  # noqa: E402
    Prop1224MpfrCampaignError,
    make_mpfr_plan,
    run_mpfr_shard,
    validate_receipt,
    verify_receipts,
)


REPRESENTATIVE_RANK = 3_315_093_776


def run(
    runner: Path, lower: int, upper: int, *, segment: int = 1_000,
    precision: int = 192
) -> dict[str, object]:
    completed = subprocess.run(
        [
            str(runner),
            "--rank-lower",
            str(lower),
            "--rank-upper",
            str(upper),
            "--precision-bits",
            str(precision),
            "--segment-size",
            str(segment),
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    report = json.loads(completed.stdout)
    if not isinstance(report, dict):
        raise AssertionError("MPFR runner did not emit an object")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", type=Path, required=True)
    args = parser.parse_args()

    representative = run(
        args.runner, REPRESENTATIVE_RANK, REPRESENTATIVE_RANK + 1
    )
    if representative["first_q"] != 6_469_693_230:
        raise AssertionError("representative source rank mapped to the wrong q")
    if (representative["r_steps"], representative["conservative_k_rows_checked"]) != (
        721,
        136,
    ):
        raise AssertionError("representative complete directed window changed")
    minimum = representative["minimum_margin_lower_hex"]
    if not isinstance(minimum, str) or float.fromhex(minimum) <= 1.0:
        raise AssertionError("representative margin no longer proves the >1 known answer")
    if representative["nonempty_q_rows"] != 1 or representative["empty_q_rows"] != 0:
        raise AssertionError("representative row was not classified as nonempty")

    plan = make_mpfr_plan(
        rank_lower=REPRESENTATIVE_RANK,
        rank_upper=REPRESENTATIVE_RANK + 1,
        leaf_rows=1,
    )
    receipt = run_mpfr_shard(
        runner=args.runner,
        plan=plan,
        shard_index=0,
        segment_size=97,
    )
    validate_receipt(receipt, plan=plan, precision_bits=192, mpfr_version="4.2.1")
    verification = verify_receipts((receipt,), plan=plan)
    if verification.final_state != (REPRESENTATIVE_RANK + 1,):
        raise AssertionError("plan-bound MPFR receipt has the wrong final rank")
    changed = dict(receipt)
    changed["plan_sha256"] = "0" * 64
    try:
        validate_receipt(changed, plan=plan, precision_bits=192, mpfr_version="4.2.1")
    except Prop1224MpfrCampaignError:
        pass
    else:
        raise AssertionError("receipt validator accepted a substituted plan")

    # Segment boundaries are a resource choice, never part of the arithmetic
    # result.  The exact row commitment must therefore be invariant.
    split = run(
        args.runner,
        REPRESENTATIVE_RANK,
        REPRESENTATIVE_RANK + 1,
        segment=97,
    )
    for name in (
        "r_steps",
        "conservative_k_rows_checked",
        "minimum_margin_lower_hex",
        "row_root_sha256",
    ):
        if split[name] != representative[name]:
            raise AssertionError(f"directed output {name} changed with segment size")

    dense_empty = run(args.runner, 1_000_000_000, 1_000_000_100)
    if dense_empty["empty_q_rows"] != 100 or dense_empty["r_steps"] != 0:
        raise AssertionError("dense empty-window known answer changed")
    extension = run(args.runner, 3_300_000_000, 3_300_000_100)
    if extension["empty_q_rows"] + extension["nonempty_q_rows"] != 100:
        raise AssertionError("extension scheduler did not cover every source row")

    rejected = subprocess.run(
        [
            str(args.runner),
            "--rank-lower",
            "4",
            "--rank-upper",
            "4",
            "--precision-bits",
            "192",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if rejected.returncode == 0 or "nonempty" not in rejected.stderr:
        raise AssertionError("MPFR runner accepted an empty rank range")
    print("Proposition 12.2.4 MPFR shard known answers passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
