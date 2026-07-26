#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independent full-word known answer for the CUDA persistent bucket sieve."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.goldbach_bucket_sieve import (  # noqa: E402
    PersistentBucketOddSieve,
    odd_primes_through,
    words_sha256_le,
)


ODD_LOW = 1_000_000_000_001
SEGMENT_ODDS = 4096
SEGMENTS = 16
BASE_LIMIT = 1_000_000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    args = parser.parse_args()

    primes = odd_primes_through(BASE_LIMIT)
    model = PersistentBucketOddSieve(
        odd_low=ODD_LOW,
        odd_count=SEGMENT_ODDS,
        segments=SEGMENTS,
        odd_primes=primes,
    )
    expected_digest = words_sha256_le(
        model.next_segment().words for _ in range(SEGMENTS)
    )
    completed = subprocess.run(
        [
            str(args.runner.resolve()),
            f"--odd-low={ODD_LOW}",
            f"--segment-odds={SEGMENT_ODDS}",
            f"--segments={SEGMENTS}",
            f"--replay-segments={SEGMENTS}",
            f"--base-limit={BASE_LIMIT}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    expected_fields = {
        "algorithm": "sparkinterval.goldbach-persistent-bucket-sieve.v1",
        "source_scale_completed": False,
        "receipt_eligible": False,
        "marking_mode": "idempotent-byte-store",
        "same_value_write_collisions": True,
        "odd_low": ODD_LOW,
        "segment_odds": SEGMENT_ODDS,
        "segments": SEGMENTS,
        "replay_segments": SEGMENTS,
        "base_limit": BASE_LIMIT,
        "base_prime_count": len(primes),
        "scheduled_base_prime_count": len(primes) - 5,
        "active_dense_prime_count": 558,
        "bucket_ring_size": 2688,
        "activated_prime_count": len(primes) - 5,
        "sparse_composite_events": 12661,
        "replayed_prime_bits": 4771,
        "dense_offset_state_replayed": False,
        "replay_words_sha256_le": expected_digest,
    }
    for field, expected in expected_fields.items():
        if result.get(field) != expected:
            raise AssertionError(
                f"CUDA KAT field {field!r} differs: {result.get(field)!r} != {expected!r}"
            )

    atomic_completed = subprocess.run(
        [
            str(args.runner.resolve()),
            f"--odd-low={ODD_LOW}",
            f"--segment-odds={SEGMENT_ODDS}",
            f"--segments={SEGMENTS}",
            f"--replay-segments={SEGMENTS}",
            f"--base-limit={BASE_LIMIT}",
            "--atomic-words",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    atomic_result = json.loads(atomic_completed.stdout)
    if (
        atomic_result.get("marking_mode") != "packed-atomic-and"
        or atomic_result.get("same_value_write_collisions") is not False
        or atomic_result.get("replay_words_sha256_le") != expected_digest
        or atomic_result.get("replayed_prime_bits") != 4771
    ):
        raise AssertionError("packed-atomic comparison path differs from exact KAT")

    incomplete = subprocess.run(
        [
            str(args.runner.resolve()),
            f"--odd-low={ODD_LOW}",
            f"--segment-odds={SEGMENT_ODDS}",
            "--segments=1",
            "--replay-segments=1",
            "--base-limit=999999",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if incomplete.returncode == 0:
        raise AssertionError("CUDA runner accepted an incomplete base-prime bound")

    print(
        "Goldbach bucket-sieve CUDA known answer passed "
        f"({SEGMENTS} full segments, sha256={expected_digest})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
