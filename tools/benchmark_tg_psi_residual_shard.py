#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run a parallel source-height throughput pilot for the CH25 psi runner.

Verify jobs deliberately use ``(lower - 1) * 2^64`` as a synthetic local
state.  This keeps the endpoint predicates in their normal fast path without
pretending that a short high-range pilot has the root-derived production
prefix.  The output is a benchmark report, never a verification certificate.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time
from typing import Any


SOURCE_EVENT_COUNT = 346_065_767_406
SOURCE_LIMIT = 10**13


class BenchmarkError(RuntimeError):
    """The benchmark runner failed or changed its receipt contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _invoke(
    runner: Path,
    mode: str,
    bounds: tuple[int, int],
    sieve_size_kib: int,
) -> dict[str, Any]:
    lower, upper = bounds
    command = [
        os.fspath(runner),
        "--mode",
        mode,
        "--lower",
        str(lower),
        "--upper",
        str(upper),
        "--sieve-size-kib",
        str(sieve_size_kib),
    ]
    if mode == "verify":
        synthetic = (lower - 1) << 64
        command += [
            "--incoming-lower",
            str(synthetic),
            "--incoming-upper",
            str(synthetic),
        ]
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        raise BenchmarkError(
            f"{mode} shard [{lower}, {upper}] failed: {completed.stderr.strip()}"
        )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise BenchmarkError("runner output is not JSON") from exc
    if (
        not isinstance(report, dict)
        or report.get("algorithm") != "ch25-psi-prime-power-two-pass-v1"
        or report.get("mode") != mode
        or report.get("lower") != lower
        or report.get("upper_exclusive") != upper + 1
        or report.get("accepted") is not True
    ):
        raise BenchmarkError("runner receipt changed or reported the wrong shard")
    return report


def _ranges(upper: int, shard_span: int, shards: int) -> list[tuple[int, int]]:
    lower = upper - shard_span * shards + 1
    if lower < 2:
        raise BenchmarkError("requested pilot extends below the psi source domain")
    return [
        (lower + index * shard_span, lower + (index + 1) * shard_span - 1)
        for index in range(shards)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--shards", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--shard-span", type=int, default=100_000_000)
    parser.add_argument("--upper", type=int, default=SOURCE_LIMIT)
    parser.add_argument("--sieve-size-kib", type=int, default=384)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()

    runner = arguments.runner.resolve()
    if not runner.is_file() or not os.access(runner, os.X_OK):
        raise BenchmarkError(f"runner is not executable: {runner}")
    for value, name in (
        (arguments.workers, "workers"),
        (arguments.shards, "shards"),
        (arguments.shard_span, "shard span"),
    ):
        if value < 1:
            raise BenchmarkError(f"{name} must be positive")
    if not 2 <= arguments.upper <= SOURCE_LIMIT:
        raise BenchmarkError("upper is outside the psi source domain")
    if not 16 <= arguments.sieve_size_kib <= 8192:
        raise BenchmarkError("sieve size must lie in [16, 8192] KiB")
    ranges = _ranges(arguments.upper, arguments.shard_span, arguments.shards)

    phase_reports: dict[str, list[dict[str, Any]]] = {}
    phase_seconds: dict[str, float] = {}
    for mode in ("summary", "verify"):
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=arguments.workers) as executor:
            reports = list(
                executor.map(
                    lambda bounds: _invoke(
                        runner, mode, bounds, arguments.sieve_size_kib
                    ),
                    ranges,
                )
            )
        phase_seconds[mode] = time.monotonic() - started
        phase_reports[mode] = reports

    for summary, verification in zip(
        phase_reports["summary"], phase_reports["verify"], strict=True
    ):
        for field in ("delta", "event_sha256", "row_sha256"):
            if summary.get(field) != verification.get(field):
                raise BenchmarkError(f"summary/verify mismatch in {field}")
    events = sum(row["prime_power_events"] for row in phase_reports["summary"])
    if events < 1:
        raise BenchmarkError("benchmark processed no prime-power events")
    two_pass_seconds = phase_seconds["summary"] + phase_seconds["verify"]
    event_passes_per_second = 2 * events / two_pass_seconds
    report = {
        "schema": "sparkinterval.tg.psi-throughput-benchmark.v1",
        "classification": "bounded_performance_pilot_not_verification_evidence",
        "algorithm": "ch25-psi-prime-power-two-pass-v1",
        "runner_sha256": _sha256(runner),
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
        },
        "configuration": {
            "workers": arguments.workers,
            "shards": arguments.shards,
            "shard_span": arguments.shard_span,
            "domain_lower": ranges[0][0],
            "domain_upper_exclusive": ranges[-1][1] + 1,
            "sieve_size_kib": arguments.sieve_size_kib,
            "verify_incoming_state": "synthetic_(shard_lower_minus_one)_times_2^64",
            "root_derived_production_prefix": False,
        },
        "measurement": {
            "prime_power_events_per_pass": events,
            "summary_wall_seconds": phase_seconds["summary"],
            "verify_wall_seconds": phase_seconds["verify"],
            "two_pass_wall_seconds": two_pass_seconds,
            "event_passes_per_second": event_passes_per_second,
            "source_event_count_per_pass": SOURCE_EVENT_COUNT,
            "linear_source_two_pass_seconds":
                2 * SOURCE_EVENT_COUNT / event_passes_per_second,
            "linear_source_two_pass_hours":
                2 * SOURCE_EVENT_COUNT / event_passes_per_second / 3600,
        },
        "upstreams": {
            "primesieve_commit": phase_reports["summary"][0][
                "primesieve_commit"
            ],
            "crlibm_commit": phase_reports["summary"][0]["crlibm_commit"],
        },
        "accepted": True,
    }
    rendered = json.dumps(
        report,
        indent=2 if arguments.pretty else None,
        sort_keys=True,
        separators=None if arguments.pretty else (",", ":"),
    ) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
