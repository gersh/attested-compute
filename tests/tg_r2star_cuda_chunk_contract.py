#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independent Python-contract checks for bounded CUDA R2Star chunks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
from tg_verifier import r2star


def invoke(
    runner: Path,
    *,
    lower: int,
    count: int,
    incoming_lower: int,
    incoming_upper: int,
    previous_hash: str,
) -> tuple[r2star.R2StarChunk, dict[str, object]]:
    command = [
        str(runner),
        "--lower",
        str(lower),
        "--count",
        str(count),
        "--incoming-lower",
        str(incoming_lower),
        "--incoming-upper",
        str(incoming_upper),
        "--previous-hash",
        previous_hash,
        "--allow-other-device",
        "--cross-check-serial",
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(
            f"{command!r} failed with {completed.returncode}: "
            f"stdout={completed.stdout!r}, stderr={completed.stderr!r}"
        )
    report = json.loads(completed.stdout)
    if report["classification"] != (
        "bounded_exact_python_contract_chunk_not_full_atom_proof"
    ):
        raise AssertionError("runner overstates or changes its evidence class")
    for field in (
        "full_source_range",
        "lean_atom_discharged",
        "proves_any_external_atom",
    ):
        if report[field] is not False:
            raise AssertionError(f"runner incorrectly sets {field}")
    if report["python_contract_replay_required"] is not True:
        raise AssertionError("runner omits the independent replay requirement")
    if report["hash_chain_is_integrity_not_authentication"] is not True:
        raise AssertionError("runner misclassifies its unauthenticated hash chain")
    if report["prefix_implementation"] != "deterministic_blocked_exact_scan_v1":
        raise AssertionError("runner did not use the blocked exact transition")
    if report["serial_cross_check_performed"] is not True:
        raise AssertionError("runner omitted the retained serial cross-check")
    chunk = r2star.R2StarChunk(**report["chunk"])
    # This recomputes arbitrary-precision rational log bounds, all factor rows,
    # every prefix transition, the minimum slack, and the canonical JSON hash.
    r2star.verify_r2star_chunk(chunk)
    return chunk, report


def produce_partition(
    runner: Path, spans: tuple[int, ...]
) -> tuple[tuple[r2star.R2StarChunk, ...], r2star.R2StarChainVerification]:
    lower = 1
    incoming_lower = 0
    incoming_upper = 0
    previous_hash = r2star.ZERO_SHA256
    chunks: list[r2star.R2StarChunk] = []
    for span in spans:
        chunk, _report = invoke(
            runner,
            lower=lower,
            count=span,
            incoming_lower=incoming_lower,
            incoming_upper=incoming_upper,
            previous_hash=previous_hash,
        )
        chunks.append(chunk)
        lower = chunk.upper
        incoming_lower = chunk.outgoing_lower
        incoming_upper = chunk.outgoing_upper
        previous_hash = chunk.record_hash
    return tuple(chunks), r2star.verify_r2star_chain(
        chunks, expected_limit=lower - 1
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", type=Path, required=True)
    args = parser.parse_args()
    if not args.runner.is_file():
        raise AssertionError(f"missing CUDA R2Star chunk runner: {args.runner}")

    malformed = subprocess.run(
        [str(args.runner), "--count", "0"],
        text=True,
        capture_output=True,
        check=False,
    )
    if malformed.returncode != 2 or "--count must lie" not in malformed.stderr:
        raise AssertionError("zero-span chunk did not fail before CUDA execution")

    # This row's rigorous Q64 interval straddles a scale-2^32 rounding
    # boundary.  The runner must replace it with the arbitrary-precision
    # rational result, feed that row back to both transitions, and still match
    # the independent Python contract.
    ambiguous_chunk, ambiguous_report = invoke(
        args.runner,
        lower=1_364_328,
        count=5,
        incoming_lower=0,
        incoming_upper=0,
        previous_hash=r2star.ZERO_SHA256,
    )
    expected_ambiguous = r2star.create_r2star_chunk(
        lower=1_364_328,
        upper=1_364_333,
        scale_bits=32,
        series_terms=20,
        harmonic_terms=100_000,
        incoming_lower=0,
        incoming_upper=0,
    )
    if ambiguous_chunk != expected_ambiguous:
        raise AssertionError("exact fallback differs from the Python contract")
    if ambiguous_report["exact_rational_fallback_rows"] < 1:
        raise AssertionError("known Q64 ambiguity did not use exact fallback")

    prefix_overflow = subprocess.run(
        [
            str(args.runner),
            "--lower",
            "1",
            "--count",
            "3",
            "--incoming-lower",
            str(2**63 - 1),
            "--incoming-upper",
            str(2**63 - 1),
            "--allow-other-device",
            "--cross-check-serial",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if prefix_overflow.returncode != 5 or "status=2" not in prefix_overflow.stderr:
        raise AssertionError("signed prefix overflow did not fail closed")

    squared_overflow = subprocess.run(
        [
            str(args.runner),
            "--lower",
            "3",
            "--count",
            "1",
            "--incoming-lower",
            "200000000000000000",
            "--incoming-upper",
            "200000000000000000",
            "--allow-other-device",
            "--cross-check-serial",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if (
        squared_overflow.returncode != 5
        or "status=3" not in squared_overflow.stderr
    ):
        raise AssertionError("u128 squared-envelope guard did not fail closed")

    first_chunks, first = produce_partition(args.runner, (113, 127, 260))
    second_chunks, second = produce_partition(args.runner, (500,))
    direct = r2star.verify_r2star_sample(
        500,
        scale_bits=32,
        series_terms=20,
        harmonic_terms=100_000,
        block_size=79,
    )
    expected = (
        direct.final_lower,
        direct.final_upper,
        direct.minimum_squared_slack,
        direct.minimum_slack_index,
    )
    for label, result in (("three chunks", first), ("one chunk", second)):
        actual = (
            result.final_lower,
            result.final_upper,
            result.minimum_squared_slack,
            result.minimum_slack_index,
        )
        if actual != expected:
            raise AssertionError(f"{label} differs from exact direct reference")
    if first_chunks[-1].record_hash == second_chunks[-1].record_hash:
        raise AssertionError("different chunk partitions unexpectedly share a hash")

    # Cross both the 1,024-row transition boundary and several 256-thread row
    # grids.  The retained serial transition must agree field-for-field, while
    # the independent Python replay checks signed carry propagation and the
    # globally earliest minimum-slack witness.
    signed_chunk, signed_report = invoke(
        args.runner,
        lower=5_001,
        count=2_051,
        incoming_lower=-1_234_567_890_123,
        incoming_upper=-1_234_567_000_000,
        previous_hash=r2star.ZERO_SHA256,
    )
    expected_signed = r2star.create_r2star_chunk(
        lower=5_001,
        upper=7_052,
        scale_bits=32,
        series_terms=20,
        harmonic_terms=100_000,
        incoming_lower=-1_234_567_890_123,
        incoming_upper=-1_234_567_000_000,
    )
    if signed_chunk != expected_signed:
        raise AssertionError("blocked CUDA transition differs after signed carry")
    if signed_report["serial_reference_kernel_milliseconds"] <= 0:
        raise AssertionError("serial reference was not timed")

    cross_block_chunks, cross_block = produce_partition(
        args.runner, (1_023, 1, 1, 1_024, 451)
    )
    one_cross_block_chunks, one_cross_block = produce_partition(
        args.runner, (2_500,)
    )
    direct_cross_block = r2star.verify_r2star_sample(
        2_500,
        scale_bits=32,
        series_terms=20,
        harmonic_terms=100_000,
        block_size=701,
    )
    expected_cross_block = (
        direct_cross_block.final_lower,
        direct_cross_block.final_upper,
        direct_cross_block.minimum_squared_slack,
        direct_cross_block.minimum_slack_index,
    )
    for label, result in (
        ("cross-boundary partition", cross_block),
        ("one cross-boundary chunk", one_cross_block),
    ):
        actual = (
            result.final_lower,
            result.final_upper,
            result.minimum_squared_slack,
            result.minimum_slack_index,
        )
        if actual != expected_cross_block:
            raise AssertionError(f"{label} differs from exact direct reference")
    if direct_cross_block.minimum_slack_index != 3:
        raise AssertionError("earliest global minimum-slack witness changed")
    if (
        cross_block_chunks[-1].record_hash
        == one_cross_block_chunks[-1].record_hash
    ):
        raise AssertionError("cross-boundary partitions unexpectedly share a hash")

    # Exercise log/factor/coefficient generation around the worst index in the
    # retained 21-billion report.  Incoming zero is intentional: this is an
    # exact local transition comparison, not a claim about the historical
    # full-prefix state at that index.
    worst = 110_102_617
    worst_chunk, worst_report = invoke(
        args.runner,
        lower=worst - 2,
        count=5,
        incoming_lower=0,
        incoming_upper=0,
        previous_hash=r2star.ZERO_SHA256,
    )
    expected_worst = r2star.create_r2star_chunk(
        lower=worst - 2,
        upper=worst + 3,
        scale_bits=32,
        series_terms=20,
        harmonic_terms=100_000,
        incoming_lower=0,
        incoming_upper=0,
    )
    if worst_chunk != expected_worst:
        raise AssertionError("CUDA chunk differs at retained worst-index probe")
    if worst_report["ambiguous_log_rows"] != 0:
        raise AssertionError("worst-index probe contains an unresolved log row")

    endpoint_chunk, _endpoint_report = invoke(
        args.runner,
        lower=20_999_999_996,
        count=5,
        incoming_lower=0,
        incoming_upper=0,
        previous_hash=r2star.ZERO_SHA256,
    )
    expected_endpoint = r2star.create_r2star_chunk(
        lower=20_999_999_996,
        upper=21_000_000_001,
        scale_bits=32,
        series_terms=20,
        harmonic_terms=100_000,
        incoming_lower=0,
        incoming_upper=0,
    )
    if endpoint_chunk != expected_endpoint:
        raise AssertionError("CUDA chunk differs at the 21-billion endpoint")

    print(
        "CUDA R2Star chunks match the arbitrary-precision Python contract "
        "across partitions and the retained worst-index probe."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
