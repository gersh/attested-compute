#!/usr/bin/env python3
"""Bounded host-side microbenchmark for high-bound proof foundations.

This benchmark measures two deliberately narrow pieces of infrastructure:

* generation and validation of the left-to-right binary power schedule used by
  ``SparkInterval.PTX.PowSchedule``; and
* generation, streaming decode, and exact integer validation of a synthetic
  fixed-width rational endpoint-bracket format.

It does *not* evaluate the Riemann zeta function, locate or count zeros,
elaborate or kernel-check Lean proofs, execute a GPU kernel, or measure a real
SparkInterval certificate format.  The synthetic format exists only to make
the streaming byte and memory measurements concrete and reproducible.

Only Python's standard library is used.  Defaults are intentionally small
enough for a development-machine smoke benchmark; larger runs must be
requested explicitly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys
import time
import tracemalloc
from collections.abc import Iterator, Sequence
from typing import Any


SCHEMA_VERSION = 1
BENCHMARK_NAME = "sparkinterval-zeta-foundations-host-microbenchmark"
DEFAULT_MAX_EXPONENT = 32_768
DEFAULT_TOTAL_BRACKETS = 100_000
DEFAULT_CHUNK_SIZE = 4_096

SQUARE = "square"
MUL_BASE = "mul_base"

# This is a benchmark-only fixed-width encoding of the fields in Lean's
# `RationalBracket`; it is not yet a production SparkInterval wire schema.
SYNTHETIC_MAGIC = b"SIZFND01"
SYNTHETIC_FORMAT_VERSION = 1
SYNTHETIC_HEADER = struct.Struct("<8sIIQ")
SYNTHETIC_BRACKET = struct.Struct("<qQqQqQqQqQqQ")
UINT64_MASK = (1 << 64) - 1

RationalBracket = tuple[
    int, int,  # bracket lower numerator/denominator
    int, int,  # bracket upper numerator/denominator
    int, int,  # lower-endpoint result interval lower numerator/denominator
    int, int,  # lower-endpoint result interval upper numerator/denominator
    int, int,  # upper-endpoint result interval lower numerator/denominator
    int, int,  # upper-endpoint result interval upper numerator/denominator
]


def binary_power_schedule(exponent: int) -> Iterator[str]:
    """Yield the proved left-to-right schedule for one natural exponent.

    The accumulator begins at exponent zero.  A nonzero schedule first
    multiplies by the base, then processes every remaining binary digit with a
    square and, for a one digit, another base multiplication.
    """

    if exponent < 0:
        raise ValueError("exponent must be nonnegative")
    if exponent == 0:
        return
    yield MUL_BASE
    if exponent == 1:
        return
    bit = 1 << (exponent.bit_length() - 2)
    while bit:
        yield SQUARE
        if exponent & bit:
            yield MUL_BASE
        bit >>= 1


def binary_power_step_count(exponent: int) -> int:
    """Return the binary schedule's multiplication count in closed form."""

    if exponent < 0:
        raise ValueError("exponent must be nonnegative")
    if exponent == 0:
        return 0
    return exponent.bit_length() + exponent.bit_count() - 1


def _run_binary_power_schedule(exponent: int) -> tuple[int, int]:
    represented_exponent = 0
    observed_steps = 0
    for step in binary_power_schedule(exponent):
        if step == SQUARE:
            represented_exponent += represented_exponent
        elif step == MUL_BASE:
            represented_exponent += 1
        else:  # Defensive: schedule generation is local, but fail closed.
            raise AssertionError(f"unknown power step {step!r}")
        observed_steps += 1
    return represented_exponent, observed_steps


def validate_binary_power_schedules(max_exponent: int) -> dict[str, Any]:
    """Validate every schedule from zero through ``max_exponent``."""

    if max_exponent < 0:
        raise ValueError("max_exponent must be nonnegative")

    total_steps = 0
    max_steps = 0
    max_steps_exponent = 0
    checksum = 0
    for exponent in range(max_exponent + 1):
        represented, observed_steps = _run_binary_power_schedule(exponent)
        expected_steps = binary_power_step_count(exponent)
        if represented != exponent:
            raise AssertionError(
                f"schedule for {exponent} represents {represented}"
            )
        if observed_steps != expected_steps:
            raise AssertionError(
                f"schedule for {exponent} has {observed_steps} steps; "
                f"closed form says {expected_steps}"
            )
        total_steps += observed_steps
        if observed_steps > max_steps:
            max_steps = observed_steps
            max_steps_exponent = exponent
        checksum = (
            (checksum * 0x9E3779B185EBCA87)
            ^ exponent
            ^ (observed_steps << 32)
        ) & UINT64_MASK

    return {
        "validated": True,
        "exponents_validated": max_exponent + 1,
        "max_exponent": max_exponent,
        "schedule_steps_validated": total_steps,
        "largest_step_count": max_steps,
        "largest_step_count_exponent": max_steps_exponent,
        "deterministic_checksum_u64": f"{checksum:016x}",
    }


def synthetic_bracket(index: int) -> RationalBracket:
    """Return one ordered bracket with a strict certified sign change."""

    if index < 0:
        raise ValueError("bracket index must be nonnegative")
    # [2i, 2i+1], leaving a unit gap before the next bracket.  Varying
    # denominators exercises exact cross-products without changing ordering.
    endpoint_den = 2 + index % 17
    lower_num = 2 * index * endpoint_den
    upper_num = (2 * index + 1) * endpoint_den
    magnitude_den = 3 + index % 19
    return (
        lower_num,
        endpoint_den,
        upper_num,
        endpoint_den,
        -2,
        magnitude_den,
        -1,
        magnitude_den,
        1,
        magnitude_den,
        2,
        magnitude_den,
    )


def _rat_lt(left_num: int, left_den: int, right_num: int, right_den: int) -> bool:
    return left_num * right_den < right_num * left_den


def _rat_le(left_num: int, left_den: int, right_num: int, right_den: int) -> bool:
    return left_num * right_den <= right_num * left_den


def rational_bracket_is_locally_valid(bracket: RationalBracket) -> bool:
    """Mirror `RationalBracket.IsValid` with exact cross-multiplication."""

    (
        lower_num,
        lower_den,
        upper_num,
        upper_den,
        lower_value_lo_num,
        lower_value_lo_den,
        lower_value_hi_num,
        lower_value_hi_den,
        upper_value_lo_num,
        upper_value_lo_den,
        upper_value_hi_num,
        upper_value_hi_den,
    ) = bracket
    denominators = bracket[1::2]
    if any(denominator <= 0 for denominator in denominators):
        return False
    endpoints_ordered = _rat_lt(
        lower_num, lower_den, upper_num, upper_den
    )
    lower_interval_valid = _rat_le(
        lower_value_lo_num,
        lower_value_lo_den,
        lower_value_hi_num,
        lower_value_hi_den,
    )
    upper_interval_valid = _rat_le(
        upper_value_lo_num,
        upper_value_lo_den,
        upper_value_hi_num,
        upper_value_hi_den,
    )
    negative_then_positive = (
        lower_value_hi_num < 0 and upper_value_lo_num > 0
    )
    positive_then_negative = (
        upper_value_hi_num < 0 and lower_value_lo_num > 0
    )
    return (
        endpoints_ordered
        and lower_interval_valid
        and upper_interval_valid
        and (negative_then_positive or positive_then_negative)
    )


def rational_brackets_are_adjacent_ordered(
    previous: RationalBracket, current: RationalBracket
) -> bool:
    """Mirror the linear family check: previous.upper < current.lower."""

    return _rat_lt(previous[2], previous[3], current[0], current[1])


def _update_bracket_checksum(checksum: int, bracket: RationalBracket) -> int:
    for value in bracket:
        checksum = (
            (checksum * 0xD6E8FEB86659FD93) ^ (value & UINT64_MASK)
        ) & UINT64_MASK
    return checksum


def validate_streaming_rational_brackets(
    total_brackets: int, chunk_size: int
) -> dict[str, Any]:
    """Generate, decode, and validate a synthetic certificate by chunks.

    No complete certificate byte string or complete record list is retained.
    The reported byte count is exact for the benchmark-only fixed-width format.
    """

    if total_brackets < 0:
        raise ValueError("total_brackets must be nonnegative")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    encoded_header = SYNTHETIC_HEADER.pack(
        SYNTHETIC_MAGIC,
        SYNTHETIC_FORMAT_VERSION,
        SYNTHETIC_BRACKET.size,
        total_brackets,
    )
    magic, version, record_bytes, encoded_total = SYNTHETIC_HEADER.unpack(
        encoded_header
    )
    if (
        magic != SYNTHETIC_MAGIC
        or version != SYNTHETIC_FORMAT_VERSION
        or record_bytes != SYNTHETIC_BRACKET.size
        or encoded_total != total_brackets
    ):
        raise AssertionError("synthetic certificate header did not round-trip")

    checked = 0
    chunks = 0
    peak_chunk_brackets = 0
    certificate_bytes = len(encoded_header)
    checksum = 0
    previous_bracket: RationalBracket | None = None
    while checked < total_brackets:
        records_in_chunk = min(chunk_size, total_brackets - checked)
        payload = bytearray(records_in_chunk * SYNTHETIC_BRACKET.size)
        for local_index in range(records_in_chunk):
            bracket = synthetic_bracket(checked + local_index)
            SYNTHETIC_BRACKET.pack_into(
                payload, local_index * SYNTHETIC_BRACKET.size, *bracket
            )

        decoded_in_chunk = 0
        for decoded in SYNTHETIC_BRACKET.iter_unpack(payload):
            bracket = tuple(decoded)
            if not rational_bracket_is_locally_valid(bracket):
                raise AssertionError(
                    f"invalid synthetic rational bracket at index "
                    f"{checked + decoded_in_chunk}"
                )
            if previous_bracket is not None and not (
                rational_brackets_are_adjacent_ordered(previous_bracket, bracket)
            ):
                raise AssertionError(
                    f"misordered synthetic rational bracket at index "
                    f"{checked + decoded_in_chunk}"
                )
            checksum = _update_bracket_checksum(checksum, bracket)
            previous_bracket = bracket
            decoded_in_chunk += 1
        if decoded_in_chunk != records_in_chunk:
            raise AssertionError("synthetic chunk decoded the wrong record count")

        certificate_bytes += len(payload)
        checked += records_in_chunk
        chunks += 1
        peak_chunk_brackets = max(peak_chunk_brackets, records_in_chunk)

    expected_bytes = (
        SYNTHETIC_HEADER.size + total_brackets * SYNTHETIC_BRACKET.size
    )
    if certificate_bytes != expected_bytes:
        raise AssertionError(
            f"processed {certificate_bytes} bytes, expected {expected_bytes}"
        )

    return {
        "validated": True,
        "brackets_validated": checked,
        "chunks_processed": chunks,
        "configured_chunk_brackets": chunk_size,
        "largest_chunk_brackets": peak_chunk_brackets,
        "synthetic_certificate_bytes": certificate_bytes,
        "synthetic_header_bytes": SYNTHETIC_HEADER.size,
        "synthetic_bytes_per_bracket": SYNTHETIC_BRACKET.size,
        "complete_certificate_materialized": False,
        "deterministic_checksum_u64": f"{checksum:016x}",
    }


def _rate(count: int, elapsed_seconds: float) -> float | None:
    if count == 0:
        return 0.0
    if elapsed_seconds <= 0.0:
        return None
    return count / elapsed_seconds


def _measure(function: Any, *arguments: int) -> tuple[dict[str, Any], float, int]:
    if tracemalloc.is_tracing():
        raise RuntimeError("benchmark requires ownership of tracemalloc")
    tracemalloc.start()
    start = time.perf_counter()
    try:
        result = function(*arguments)
        elapsed_seconds = time.perf_counter() - start
        _current_bytes, peak_memory_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, elapsed_seconds, peak_memory_bytes


def run_benchmark(
    *, max_exponent: int, total_brackets: int, chunk_size: int
) -> dict[str, Any]:
    """Run both host microbenchmarks and return a JSON-serializable report."""

    power, power_seconds, power_peak_bytes = _measure(
        validate_binary_power_schedules, max_exponent
    )
    power["elapsed_seconds"] = power_seconds
    power["peak_memory_bytes"] = power_peak_bytes
    power["throughput"] = {
        "exponents_per_second": _rate(
            power["exponents_validated"], power_seconds
        ),
        "schedule_steps_per_second": _rate(
            power["schedule_steps_validated"], power_seconds
        ),
    }

    brackets, bracket_seconds, bracket_peak_bytes = _measure(
        validate_streaming_rational_brackets, total_brackets, chunk_size
    )
    brackets["elapsed_seconds"] = bracket_seconds
    brackets["peak_memory_bytes"] = bracket_peak_bytes
    brackets["throughput"] = {
        "brackets_per_second": _rate(total_brackets, bracket_seconds),
        "certificate_bytes_per_second": _rate(
            brackets["synthetic_certificate_bytes"], bracket_seconds
        ),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "benchmark": BENCHMARK_NAME,
        "classification": "host_side_foundation_microbenchmark",
        "scope": {
            "measured": [
                "Python binary-power schedule generation and validation",
                "Python synthetic fixed-width bracket generation and decode",
                (
                    "exact Python-integer local interval/sign and adjacent "
                    "bracket comparisons"
                ),
            ],
            "not_measured": [
                "Riemann-zeta analytic evaluation or zero verification",
                "Lean elaboration or Lean kernel checking",
                "GPU execution, GPU memory use, or GPU throughput",
                "production SparkInterval certificate parsing or size",
            ],
        },
        "configuration": {
            "max_exponent": max_exponent,
            "total_brackets": total_brackets,
            "chunk_size": chunk_size,
        },
        "results": {
            "binary_power_schedule": power,
            "synthetic_streaming_rational_brackets": brackets,
        },
        "measurement_notes": {
            "clock": "time.perf_counter wall time",
            "peak_memory_bytes": (
                "peak Python allocation bytes observed by tracemalloc for each "
                "phase; not process RSS, GPU memory, or certificate storage"
            ),
            "timing_overhead": (
                "tracemalloc remains enabled during timed work, so throughput "
                "includes tracing overhead"
            ),
            "certificate_bytes": (
                "exact bytes processed in the benchmark-only fixed-width "
                "synthetic RationalBracket field encoding; not a production "
                "certificate-size estimate"
            ),
            "data": "deterministic; timings remain machine- and load-dependent",
        },
    }


def _nonnegative(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return parsed


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-exponent",
        type=_nonnegative,
        default=DEFAULT_MAX_EXPONENT,
        help="validate every binary schedule from zero through this exponent",
    )
    parser.add_argument(
        "--total-brackets",
        type=_nonnegative,
        default=DEFAULT_TOTAL_BRACKETS,
        help="total synthetic rational brackets to stream and check",
    )
    parser.add_argument(
        "--chunk-size",
        type=_positive,
        default=DEFAULT_CHUNK_SIZE,
        help="maximum synthetic bracket records retained in one byte chunk",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write JSON to this path instead of standard output",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="indent the JSON report",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    report = run_benchmark(
        max_exponent=args.max_exponent,
        total_brackets=args.total_brackets,
        chunk_size=args.chunk_size,
    )
    encoded = json.dumps(
        report,
        indent=2 if args.pretty else None,
        sort_keys=True,
        separators=None if args.pretty else (",", ":"),
    ) + "\n"
    if args.output is None:
        sys.stdout.write(encoded)
    else:
        args.output.write_text(encoded, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
