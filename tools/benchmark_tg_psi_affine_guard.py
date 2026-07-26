#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark the one-pass CH25 psi guard against the two-pass oracle."""

from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
from math import isqrt
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import canonical_json_bytes  # noqa: E402


SCALE = 1 << 64
SOURCE_EVENT_COUNT = 346_065_767_406
SOURCE_UPPER_EXCLUSIVE = 10_000_000_000_001
COMMON_FIELDS = (
    "delta",
    "event_sha256",
    "row_sha256",
    "prime_power_events",
    "prime_events",
    "higher_power_events",
)


class BenchmarkError(RuntimeError):
    """The bounded affine benchmark failed closed."""


def decimal_text(value: Decimal) -> str:
    if not value.is_finite() or value < 0:
        raise BenchmarkError("timing must be finite and nonnegative")
    return format(value, "f")


def median(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(values)
    if not ordered:
        raise BenchmarkError("cannot take an empty median")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def invoke(
    runner: Path,
    mode: str,
    lower: int,
    upper_exclusive: int,
    sieve_size_kib: int,
    incoming: tuple[int, int] | None,
) -> tuple[dict[str, Any], Decimal]:
    command = [
        os.fspath(runner.resolve()),
        "--mode",
        mode,
        "--lower",
        str(lower),
        "--upper",
        str(upper_exclusive - 1),
        "--sieve-size-kib",
        str(sieve_size_kib),
    ]
    if incoming is not None:
        command += [
            "--incoming-lower",
            str(incoming[0]),
            "--incoming-upper",
            str(incoming[1]),
        ]
    started = time.monotonic_ns()
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    wall = Decimal(time.monotonic_ns() - started) / Decimal(1_000_000_000)
    if completed.returncode != 0:
        raise BenchmarkError(
            f"{mode} worker failed ({completed.returncode}): "
            f"{completed.stderr.decode('utf-8', errors='replace').strip()}"
        )
    try:
        report = json.loads(
            completed.stdout.decode("utf-8"), parse_float=Decimal
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"{mode} receipt is not one JSON object") from exc
    if not isinstance(report, dict):
        raise BenchmarkError(f"{mode} receipt is not an object")
    return report, wall


def without_elapsed(report: dict[str, Any]) -> dict[str, Any]:
    result = dict(report)
    result.pop("elapsed_seconds", None)
    return result


def wire_report(report: dict[str, Any]) -> dict[str, Any]:
    result = dict(report)
    elapsed = result.get("elapsed_seconds")
    if not isinstance(elapsed, Decimal):
        raise BenchmarkError("receipt elapsed time is not numeric")
    result["elapsed_seconds_decimal"] = decimal_text(elapsed)
    del result["elapsed_seconds"]
    return result


def check_affine_witnesses(report: dict[str, Any]) -> None:
    if (
        report.get("algorithm") != "ch25-psi-prime-power-affine-guard-v1"
        or report.get("mode") != "affine"
        or report.get("classification") != "source-scale-shard-not-lean-proof"
        or report.get("atom") != "ch25-psi-1e13"
        or report.get("accepted") is not True
        or report.get("execution_attested") is not False
        or report.get("lean_atom_discharged") is not False
    ):
        raise BenchmarkError("affine receipt identity or trust flags changed")
    if report.get("guard_encoding") != (
        "independent-q64-rectangle-with-lower-le-upper-v1"
    ):
        raise BenchmarkError("affine guard encoding changed")
    bounds = report.get("allowed_incoming_q64")
    witnesses = report.get("guard_witnesses")
    if not isinstance(bounds, dict) or not isinstance(witnesses, dict):
        raise BenchmarkError("affine bounds or witnesses are missing")
    if bounds.get("predicate") != "lower_min<=lower<=upper<=upper_max":
        raise BenchmarkError("affine containment predicate changed")
    minimum_lower = bounds.get("lower_min")
    maximum_upper = bounds.get("upper_max")
    if (
        isinstance(minimum_lower, bool)
        or not isinstance(minimum_lower, int)
        or isinstance(maximum_upper, bool)
        or not isinstance(maximum_upper, int)
        or not 0 <= minimum_lower <= maximum_upper < (1 << 128)
    ):
        raise BenchmarkError("affine incoming rectangle is malformed")
    lower = witnesses.get("lower_min")
    upper = witnesses.get("upper_max")
    if not isinstance(lower, dict) or not isinstance(upper, dict):
        raise BenchmarkError("affine extremum witnesses are missing")

    lower_value = lower.get("value")
    lower_delta = lower.get("prefix_delta_q64")
    lower_radius = lower.get("radius_q64")
    strict = lower.get("strict")
    if (
        isinstance(lower_value, bool)
        or not isinstance(lower_value, int)
        or isinstance(lower_delta, bool)
        or not isinstance(lower_delta, int)
        or isinstance(lower_radius, bool)
        or not isinstance(lower_radius, int)
        or not isinstance(strict, bool)
    ):
        raise BenchmarkError("lower affine witness is malformed")
    event_count = report.get("prime_power_events")
    prime_count = report.get("prime_events")
    higher_count = report.get("higher_power_events")
    lower_index = lower.get("event_index")
    lower_kind = lower.get("kind")
    upper_index = upper.get("event_index")
    if (
        isinstance(event_count, bool)
        or not isinstance(event_count, int)
        or event_count < 1
        or isinstance(prime_count, bool)
        or not isinstance(prime_count, int)
        or isinstance(higher_count, bool)
        or not isinstance(higher_count, int)
        or event_count != prime_count + higher_count
        or isinstance(lower_index, bool)
        or not isinstance(lower_index, int)
        or isinstance(upper_index, bool)
        or not isinstance(upper_index, int)
    ):
        raise BenchmarkError("affine event counts or witness indices changed")
    terminal = report.get("terminal_strict_lower_constrained")
    expected_terminal = report.get("upper_exclusive") == SOURCE_UPPER_EXCLUSIVE
    if terminal is not expected_terminal:
        raise BenchmarkError("affine terminal classification changed")
    if lower_kind == "terminal_strict_lower":
        if (
            not terminal
            or not strict
            or lower_value != SOURCE_UPPER_EXCLUSIVE - 1
            or lower_index != event_count
        ):
            raise BenchmarkError("terminal lower witness is inconsistent")
    elif lower_kind == "lower_left_limit":
        if strict or not 0 <= lower_index < event_count:
            raise BenchmarkError("ordinary lower witness is inconsistent")
    else:
        raise BenchmarkError("lower witness kind changed")
    radicand = (2 * lower_value) << 32
    root = isqrt(radicand)
    expected_radius = root << 48
    if strict and root * root == radicand:
        expected_radius -= 1
    if lower_radius != expected_radius:
        raise BenchmarkError("lower affine Q16 radius changed")
    lower_square = lower_radius * lower_radius
    lower_bound = 2 * lower_value * SCALE * SCALE
    if (strict and not lower_square < lower_bound) or (
        not strict and not lower_square <= lower_bound
    ):
        raise BenchmarkError("lower affine radius square is unsafe")
    expected_minimum = max(
        0, lower_value * SCALE - lower_radius - lower_delta
    )
    if bounds.get("lower_min") != expected_minimum:
        raise BenchmarkError("lower witness does not attain retained minimum")

    upper_value = upper.get("value")
    upper_delta = upper.get("prefix_delta_q64")
    upper_radius = upper.get("radius_q64")
    if (
        isinstance(upper_value, bool)
        or not isinstance(upper_value, int)
        or isinstance(upper_delta, bool)
        or not isinstance(upper_delta, int)
        or isinstance(upper_radius, bool)
        or not isinstance(upper_radius, int)
        or upper.get("kind") != "upper_post_jump"
        or not 0 <= upper_index < event_count
    ):
        raise BenchmarkError("upper affine witness is malformed")
    root = isqrt(upper_value << 32)
    expected_radius = (19_764_819 * root * (1 << 48)) // 25_000_000
    if upper_radius != expected_radius:
        raise BenchmarkError("upper affine Q16 radius changed")
    if (
        upper_radius * upper_radius * 25_000_000 * 25_000_000
        > 19_764_819
        * 19_764_819
        * upper_value
        * SCALE
        * SCALE
    ):
        raise BenchmarkError("upper affine radius square is unsafe")
    expected_maximum = upper_value * SCALE + upper_radius - upper_delta
    if bounds.get("upper_max") != expected_maximum:
        raise BenchmarkError("upper witness does not attain retained maximum")
    delta = report.get("delta")
    if (
        not isinstance(delta, list)
        or len(delta) != 2
        or any(isinstance(item, bool) or not isinstance(item, int) for item in delta)
        or not 0 <= delta[0] <= delta[1] < (1 << 128)
        or maximum_upper + delta[0] >= (1 << 128)
        or maximum_upper + delta[1] >= (1 << 128)
    ):
        raise BenchmarkError("affine transition is malformed or can overflow")
    for field in ("event_sha256", "row_sha256"):
        digest = report.get(field)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or digest != digest.lower()
        ):
            raise BenchmarkError(f"affine {field} is malformed")
        try:
            if len(bytes.fromhex(digest)) != 32:
                raise ValueError
        except ValueError as exc:
            raise BenchmarkError(f"affine {field} is malformed") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--affine-runner", required=True, type=Path)
    parser.add_argument("--two-pass-runner", required=True, type=Path)
    parser.add_argument("--affine-source", required=True, type=Path)
    parser.add_argument("--two-pass-source", required=True, type=Path)
    parser.add_argument("--lower", required=True, type=int)
    parser.add_argument("--upper-exclusive", required=True, type=int)
    parser.add_argument("--sieve-size-kib", type=int, default=384)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.output.exists():
        raise BenchmarkError(f"refusing to overwrite {arguments.output}")
    if not 2 <= arguments.lower < arguments.upper_exclusive:
        raise BenchmarkError("benchmark range is empty or below two")
    if arguments.upper_exclusive > SOURCE_UPPER_EXCLUSIVE:
        raise BenchmarkError("benchmark range exceeds the source domain")
    if not 16 <= arguments.sieve_size_kib <= 8192:
        raise BenchmarkError("sieve size is outside [16,8192]")
    if arguments.repeats < 1:
        raise BenchmarkError("repeat count must be positive")
    incoming_value = (arguments.lower - 1) * SCALE
    incoming = (incoming_value, incoming_value)
    records: dict[str, list[dict[str, Any]]] = {
        "affine": [],
        "summary": [],
        "verify": [],
    }
    elapsed: dict[str, list[Decimal]] = {key: [] for key in records}
    wall: dict[str, list[Decimal]] = {key: [] for key in records}
    semantic: dict[str, dict[str, Any] | None] = {
        key: None for key in records
    }
    for repeat in range(arguments.repeats):
        order = (
            ("affine", "summary", "verify")
            if repeat % 2 == 0
            else ("verify", "summary", "affine")
        )
        for mode in order:
            runner = (
                arguments.affine_runner
                if mode == "affine"
                else arguments.two_pass_runner
            )
            report, process_wall = invoke(
                runner,
                mode,
                arguments.lower,
                arguments.upper_exclusive,
                arguments.sieve_size_kib,
                incoming if mode == "verify" else None,
            )
            if mode == "affine":
                check_affine_witnesses(report)
            candidate = without_elapsed(report)
            if semantic[mode] is None:
                semantic[mode] = candidate
            elif semantic[mode] != candidate:
                raise BenchmarkError(f"{mode} semantic output changed")
            elapsed[mode].append(Decimal(report["elapsed_seconds"]))
            wall[mode].append(process_wall)
            records[mode].append(wire_report(report))
    assert all(value is not None for value in semantic.values())
    for field in COMMON_FIELDS:
        values = {json.dumps(semantic[mode][field], sort_keys=True)
                  for mode in semantic}
        if len(values) != 1:
            raise BenchmarkError(f"affine/two-pass {field} differs")
    affine_bounds = semantic["affine"]["allowed_incoming_q64"]
    if not (
        affine_bounds["lower_min"]
        <= incoming[0]
        <= incoming[1]
        <= affine_bounds["upper_max"]
    ):
        raise BenchmarkError("synthetic benchmark input is outside affine guard")
    medians = {
        f"{mode}_{kind}_median_seconds_decimal": decimal_text(median(values))
        for mode in records
        for kind, values in (("elapsed", elapsed[mode]), ("wall", wall[mode]))
    }
    two_pass_wall = median(wall["summary"]) + median(wall["verify"])
    affine_wall = median(wall["affine"])
    speedup = two_pass_wall / affine_wall
    events = semantic["affine"]["prime_power_events"]
    source_seconds = Decimal(SOURCE_EVENT_COUNT) * affine_wall / Decimal(events)
    artifact = {
        "schema": "sparkinterval.tg.psi-affine-bounded-benchmark.v1",
        "classification": (
            "bounded_synthetic_state_performance_not_source_evidence_or_proof"
        ),
        "identity": {
            "affine_runner_sha256": sha256_file(arguments.affine_runner),
            "two_pass_runner_sha256": sha256_file(arguments.two_pass_runner),
            "affine_source_sha256": sha256_file(arguments.affine_source),
            "two_pass_source_sha256": sha256_file(arguments.two_pass_source),
        },
        "configuration": {
            "lower": arguments.lower,
            "upper_exclusive": arguments.upper_exclusive,
            "sieve_size_kib": arguments.sieve_size_kib,
            "repeats": arguments.repeats,
            "incoming_state": list(incoming),
            "incoming_state_is_root_derived": False,
        },
        "retained_reports": records,
        "checks": {
            "affine_extremum_witness_formulas_replayed": True,
            "affine_radius_square_bounds_replayed": True,
            "incoming_state_inside_retained_rectangle": True,
            "event_and_row_commitments_match_two_pass": True,
            "delta_and_event_counts_match_two_pass": True,
            "repeats_match_ignoring_timing": True,
        },
        "measurement": {
            **medians,
            "affine_vs_two_pass_wall_speedup": decimal_text(speedup),
            "prime_power_events": events,
            "linear_source_affine_seconds": decimal_text(source_seconds),
            "linear_source_affine_hours": decimal_text(
                source_seconds / Decimal(3600)
            ),
            "linear_projection_is_proof": False,
        },
        "capabilities": {
            "full_source_range": False,
            "root_derived_source_prefix": False,
            "primesieve_to_mathlib_realization_proved": False,
            "crlibm_to_mathlib_realization_proved": False,
            "compiler_or_cpu_refinement_proved": False,
            "source_run_completed": False,
            "execution_attested": False,
            "receipt_admitted": False,
            "lean_atom_discharged": False,
        },
    }
    rendered = canonical_json_bytes(artifact)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("xb") as stream:
        if stream.write(rendered) != len(rendered):
            raise BenchmarkError("short benchmark artifact write")
    print(
        json.dumps(
            {
                "artifact_sha256": hashlib.sha256(rendered).hexdigest(),
                "measurement": artifact["measurement"],
                "capabilities": artifact["capabilities"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
