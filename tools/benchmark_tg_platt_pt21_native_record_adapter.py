#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark the finite PT21BLK1 assembly adapter on one retained block."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.platt_pt21_native_record_adapter import (  # noqa: E402
    PT21NativeRecordAdapterError,
    adapt_block,
    worker_identity,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--required-sign-packet", type=Path, required=True)
    parser.add_argument("--stationary-trace", type=Path, required=True)
    parser.add_argument("--turing-inputs", type=Path, required=True)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=5)
    arguments = parser.parse_args()
    if not 1 <= arguments.iterations <= 10_000:
        parser.error("--iterations must be in 1..10000")
    try:
        identity = worker_identity(arguments.worker)
        warm = adapt_block(
            required_sign_packet=arguments.required_sign_packet,
            stationary_trace=arguments.stationary_trace,
            turing_inputs=arguments.turing_inputs,
            worker=identity,
        )
        timings: list[float] = []
        for _ in range(arguments.iterations):
            started = time.perf_counter()
            current = adapt_block(
                required_sign_packet=arguments.required_sign_packet,
                stationary_trace=arguments.stationary_trace,
                turing_inputs=arguments.turing_inputs,
                worker=identity,
            )
            timings.append(time.perf_counter() - started)
            if current.record != warm.record:
                raise PT21NativeRecordAdapterError(
                    "repeated adapter result is not deterministic"
                )
    except (OSError, ValueError, PT21NativeRecordAdapterError) as error:
        print(
            f"benchmark_tg_platt_pt21_native_record_adapter: {error}",
            file=sys.stderr,
        )
        return 2
    median = statistics.median(timings)
    result = {
        "schema": (
            "sparkinterval.tg.platt-pt21-native-record-adapter-benchmark.v1"
        ),
        "accepted": True,
        "block": warm.block,
        "iterations": len(timings),
        "minimum_seconds_per_block": min(timings),
        "median_seconds_per_block": median,
        "maximum_seconds_per_block": max(timings),
        "median_blocks_per_second": 1.0 / median,
        "record_sha256": warm.record_sha256,
        "worker_sha256": identity.sha256,
        "benchmark_scope": (
            "cpu finite packet/trace/turing validation, exact-rational block "
            "rebuild, and PT21BLK1 encoding only"
        ),
        "h100_worker_measured": False,
        "source_scale_projection_validated": False,
        "hardy_z_endpoint_realization_proved": False,
        "analytic_turing_realization_proved": False,
        "source_claim_ready": False,
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
