#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independent full-word known answer for the CUDA tile-compacted sieve."""

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
TILE_ODDS = 1024
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
            f"--tile-odds={TILE_ODDS}",
            f"--replay-segments={SEGMENTS}",
            f"--base-limit={BASE_LIMIT}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    expected_fields = {
        "algorithm": "sparkinterval.goldbach-tile-compacted-sieve.v1",
        "source_scale_completed": False,
        "receipt_eligible": False,
        "shared_clear_mode": "atomic-and-64",
        "one_global_writer_per_word": True,
        "unsynchronized_shared_word_clears": False,
        "odd_low": ODD_LOW,
        "segment_odds": SEGMENT_ODDS,
        "segments": SEGMENTS,
        "tile_odds": TILE_ODDS,
        "replay_segments": SEGMENTS,
        "base_limit": BASE_LIMIT,
        "base_prime_count": len(primes),
        "scheduled_base_prime_count": len(primes) - 5,
        "active_dense_prime_count": 558,
        "sparse_prime_count": len(primes) - 5 - 558,
        "bucket_ring_size": 2688,
        "activated_prime_count": len(primes) - 5,
        "sparse_composite_events": 12661,
        "compacted_tile_events": 34486,
        "replayed_prime_bits": 4771,
        "replay_words_sha256_le": expected_digest,
    }
    for field, expected in expected_fields.items():
        if result.get(field) != expected:
            raise AssertionError(
                f"CUDA KAT field {field!r} differs: "
                f"{result.get(field)!r} != {expected!r}"
            )

    incomplete = subprocess.run(
        [
            str(args.runner.resolve()),
            f"--odd-low={ODD_LOW}",
            f"--segment-odds={SEGMENT_ODDS}",
            "--segments=1",
            f"--tile-odds={TILE_ODDS}",
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
        "Goldbach tile-sieve CUDA known answer passed "
        f"({SEGMENTS} full segments, sha256={expected_digest})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
