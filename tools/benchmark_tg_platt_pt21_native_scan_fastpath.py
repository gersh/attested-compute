#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark the qualification-only PT21 native packet-scan fast path."""

from __future__ import annotations

import argparse
import hashlib
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
    adapt_block_native_scan_fastpath,
    adapt_block_native_scan_session,
    worker_identity,
)
from tg_verifier.platt_pt21_native_scan_fastpath import (  # noqa: E402
    NativeScanSession,
    PT21NativeScanFastpathError,
    run_native_scan_certificate,
    validate_native_scan_certificate,
)


def _summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    p95_index = min(
        len(ordered) - 1, max(0, (95 * len(ordered) + 99) // 100 - 1)
    )
    return {
        "minimum_seconds": min(values),
        "median_seconds": statistics.median(values),
        "p95_seconds": ordered[p95_index],
        "maximum_seconds": max(values),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--required-sign-packet", type=Path, required=True)
    parser.add_argument("--stationary-trace", type=Path, required=True)
    parser.add_argument("--turing-inputs", type=Path, required=True)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--native-scanner", type=Path, required=True)
    parser.add_argument(
        "--expected-native-scanner-sha256", required=True
    )
    parser.add_argument("--iterations", type=int, default=9)
    arguments = parser.parse_args()
    if not 1 <= arguments.iterations <= 1_000:
        parser.error("--iterations must be in 1..1000")

    try:
        worker = worker_identity(arguments.worker)
        raw_packet = arguments.required_sign_packet.read_bytes()

        cold_started = time.perf_counter()
        cold = adapt_block_native_scan_fastpath(
            required_sign_packet=arguments.required_sign_packet,
            stationary_trace=arguments.stationary_trace,
            turing_inputs=arguments.turing_inputs,
            worker=worker,
            native_scanner=arguments.native_scanner,
            expected_native_scanner_sha256=(
                arguments.expected_native_scanner_sha256
            ),
        )
        cold_seconds = time.perf_counter() - cold_started
        reference_warm = adapt_block(
            required_sign_packet=arguments.required_sign_packet,
            stationary_trace=arguments.stationary_trace,
            turing_inputs=arguments.turing_inputs,
            worker=worker,
        )
        if cold.adapted.record != reference_warm.record:
            raise PT21NativeRecordAdapterError(
                "cold native fast path differs from the Fraction reference"
            )

        certificate, scanner_identity, _creation_seconds = (
            run_native_scan_certificate(
                raw_packet,
                scanner=arguments.native_scanner,
                expected_scanner_sha256=(
                    arguments.expected_native_scanner_sha256
                ),
            )
        )
        validate_native_scan_certificate(
            raw_packet, certificate, scanner=scanner_identity
        )

        reference_timings: list[float] = []
        fast_timings: list[float] = []
        creation_timings: list[float] = []
        validation_timings: list[float] = []
        for iteration in range(arguments.iterations):
            # Alternate order so thermal/cache drift does not systematically
            # favor one complete adapter.
            order = ("reference", "fast") if iteration % 2 == 0 else (
                "fast",
                "reference",
            )
            current_reference = None
            current_fast = None
            for name in order:
                started = time.perf_counter()
                if name == "reference":
                    current_reference = adapt_block(
                        required_sign_packet=arguments.required_sign_packet,
                        stationary_trace=arguments.stationary_trace,
                        turing_inputs=arguments.turing_inputs,
                        worker=worker,
                    )
                    reference_timings.append(time.perf_counter() - started)
                else:
                    current_fast = adapt_block_native_scan_fastpath(
                        required_sign_packet=arguments.required_sign_packet,
                        stationary_trace=arguments.stationary_trace,
                        turing_inputs=arguments.turing_inputs,
                        worker=worker,
                        native_scanner=arguments.native_scanner,
                        expected_native_scanner_sha256=(
                            arguments.expected_native_scanner_sha256
                        ),
                    )
                    fast_timings.append(time.perf_counter() - started)
            assert current_reference is not None
            assert current_fast is not None
            if current_reference.record != current_fast.adapted.record:
                raise PT21NativeRecordAdapterError(
                    "warm native fast path differs from Fraction reference"
                )

            started = time.perf_counter()
            current_certificate, current_identity, _elapsed = (
                run_native_scan_certificate(
                    raw_packet,
                    scanner=arguments.native_scanner,
                    expected_scanner_sha256=(
                        arguments.expected_native_scanner_sha256
                    ),
                )
            )
            creation_timings.append(time.perf_counter() - started)
            if current_certificate != certificate:
                raise PT21NativeScanFastpathError(
                    "native scan certificate is nondeterministic"
                )
            started = time.perf_counter()
            validated = validate_native_scan_certificate(
                raw_packet,
                current_certificate,
                scanner=current_identity,
            )
            validation_timings.append(time.perf_counter() - started)
            if validated.certificate_sha256 != cold.scan.certificate_sha256:
                raise PT21NativeScanFastpathError(
                    "validated scan certificate identity changed"
                )

        persistent_start = time.perf_counter()
        persistent = NativeScanSession(
            scanner=arguments.native_scanner,
            expected_scanner_sha256=(
                arguments.expected_native_scanner_sha256
            ),
        )
        persistent_start_seconds = time.perf_counter() - persistent_start
        persistent_native_timings: list[float] = []
        persistent_validation_timings: list[float] = []
        persistent_end_to_end_timings: list[float] = []
        try:
            warm_persistent = adapt_block_native_scan_session(
                required_sign_packet=arguments.required_sign_packet,
                stationary_trace=arguments.stationary_trace,
                turing_inputs=arguments.turing_inputs,
                worker=worker,
                session=persistent,
            )
            if warm_persistent.adapted.record != reference_warm.record:
                raise PT21NativeRecordAdapterError(
                    "persistent warm-up differs from Fraction reference"
                )
            for _ in range(arguments.iterations):
                started = time.perf_counter()
                current_adapted = adapt_block_native_scan_session(
                    required_sign_packet=arguments.required_sign_packet,
                    stationary_trace=arguments.stationary_trace,
                    turing_inputs=arguments.turing_inputs,
                    worker=worker,
                    session=persistent,
                )
                persistent_end_to_end_timings.append(
                    time.perf_counter() - started
                )
                persistent_native_timings.append(
                    current_adapted.scan.native_certificate_seconds
                )
                persistent_validation_timings.append(
                    current_adapted.scan.python_validation_seconds
                )
                if current_adapted.adapted.record != reference_warm.record:
                    raise PT21NativeRecordAdapterError(
                        "persistent native fast path differs from "
                        "Fraction reference"
                    )
        finally:
            persistent.close()
    except (
        OSError,
        ValueError,
        PT21NativeRecordAdapterError,
        PT21NativeScanFastpathError,
    ) as error:
        print(
            f"benchmark_tg_platt_pt21_native_scan_fastpath: {error}",
            file=sys.stderr,
        )
        return 2

    reference_summary = _summary(reference_timings)
    fast_summary = _summary(fast_timings)
    result = {
        "schema": (
            "sparkinterval.tg.platt-pt21-native-scan-fastpath-benchmark.v1"
        ),
        "accepted": True,
        "block": cold.adapted.block,
        "iterations": arguments.iterations,
        "cold_fastpath_seconds": cold_seconds,
        "reference_end_to_end": reference_summary,
        "native_fastpath_end_to_end": fast_summary,
        "isolated_one_shot_native_certificate_creation": _summary(
            creation_timings
        ),
        "isolated_strict_standalone_python_certificate_validation": _summary(
            validation_timings
        ),
        "persistent_session_start_seconds": persistent_start_seconds,
        "isolated_persistent_native_certificate_roundtrip": _summary(
            persistent_native_timings
        ),
        "isolated_persistent_trusted_scanner_python_semantic_replay": _summary(
            persistent_validation_timings
        ),
        "persistent_native_fastpath_end_to_end": _summary(
            persistent_end_to_end_timings
        ),
        "median_end_to_end_speedup": (
            reference_summary["median_seconds"]
            / fast_summary["median_seconds"]
        ),
        "record_sha256": hashlib.sha256(cold.adapted.record).hexdigest(),
        "byte_identical_to_fraction_reference": True,
        "scanner_sha256": scanner_identity.sha256,
        "scanner_source_path_sha256": (
            scanner_identity.source_path_sha256
        ),
        "scanner_sealed_image_sha256": (
            scanner_identity.sealed_image_sha256
        ),
        "scanner_size_bytes": scanner_identity.size_bytes,
        "scanner_identity_pinned_before_exec": True,
        "scanner_executed_from_sealed_memfd": (
            scanner_identity.sealed_memfd_execution
        ),
        "independent_numpy_fraction_replay": True,
        "standalone_validator_recomputes_versioned_wire_checksums": True,
        "private_pinned_scanner_path_skips_only_redundant_python_checksums": (
            True
        ),
        "reference_path_remains_default": True,
        "benchmark_scope": (
            "bounded CPU finite PT21SGN1 scan, exact artifact/Turing replay, "
            "and PT21BLK1 encoding"
        ),
        "h100_worker_measured": False,
        "analytic_realization_proved": False,
        "source_scale_projection_validated": False,
        "source_claim_ready": False,
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
