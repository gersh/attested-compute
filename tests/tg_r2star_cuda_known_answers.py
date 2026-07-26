#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Known-answer execution tests for the CUDA R2Star factor-support primitive.

The fixed digests below encode each record as little-endian ``u64, u64, u32,
u32``.  They were independently generated from integer trial factorization;
the runner also performs its own per-record host comparison before emitting a
passing receipt.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
from tg_verifier.campaign_io import (
    MeasuredWorkerScopeError,
    require_azure_measured_worker_for_workload,
)


KNOWN_ANSWERS = (
    (
        1,
        512,
        "3b5efd1ace12ab8e4c6b05a65358bca64bc4af9dc8b232591817e87e99fe72c4",
    ),
    (
        72,
        193,
        "9f1122515eff8bc7f099e281983e6cd2be1f87e99f5a53f6375335f5ceeb261e",
    ),
    (
        999_900,
        512,
        "40faa4d604a6ecf68430b9d754a56c7f6de15f5c99f25df56fb7a22d91303ceb",
    ),
    (
        20_999_995_000,
        257,
        "bcbf5cf94227cd2ca1369c5419beccf765c4c759dc24ea19ed63576a748441c2",
    ),
)


def run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(
            f"{command!r} returned {completed.returncode}: "
            f"stdout={completed.stdout!r}, stderr={completed.stderr!r}"
        )
    return completed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", type=Path, required=True)
    args = parser.parse_args()
    if not args.runner.is_file():
        raise AssertionError(f"missing CUDA factor-support runner: {args.runner}")
    try:
        require_azure_measured_worker_for_workload(
            exact_production=True,
            work_bounds=(),
        )
    except MeasuredWorkerScopeError:
        print("SKIP: extended R2Star factor-support vectors are cloud-only")
        return 77

    help_result = run_checked([str(args.runner), "--help"])
    if "bounded factor-support segment" not in help_result.stdout:
        raise AssertionError("runner help omits its bounded verification scope")

    malformed = subprocess.run(
        [str(args.runner), "--count", "0"],
        text=True,
        capture_output=True,
        check=False,
    )
    if malformed.returncode != 2 or "--count must lie" not in malformed.stderr:
        raise AssertionError("runner did not reject a zero-length range before CUDA use")

    for lower, count, expected_digest in KNOWN_ANSWERS:
        completed = run_checked(
            [
                str(args.runner),
                "--lower",
                str(lower),
                "--count",
                str(count),
                "--allow-other-device",
            ]
        )
        report = json.loads(completed.stdout)
        expected_fields = {
            "algorithm": "r2star_distinct_prime_factor_support_v1",
            "classification": (
                "bounded_factor_support_primitive_not_r2star_atom_proof"
            ),
            "lower": lower,
            "upper": lower + count - 1,
            "record_count": count,
            "gpu_record_sha256_le_v1": expected_digest,
            "cpu_record_sha256_le_v1": expected_digest,
            "all_records_compared_with_independent_cpu_factorization": True,
            "mismatch_count": 0,
            "first_mismatch": None,
            "full_ramare_source_range": False,
            "checks_logarithm_enclosures": False,
            "checks_r2star_accumulation": False,
            "checks_ramare_inequality": False,
            "proves_ramare_zuniga_lemma_6_2": False,
            "proves_any_external_atom": False,
        }
        for key, expected in expected_fields.items():
            if report.get(key) != expected:
                raise AssertionError(
                    f"range [{lower}, {lower + count}) field {key!r}: "
                    f"expected {expected!r}, got {report.get(key)!r}"
                )
        if sum(report["support_count_histogram"].values()) != count:
            raise AssertionError("factor-support histogram does not cover every row")

    print("CUDA R2Star factor-support known-answer tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
