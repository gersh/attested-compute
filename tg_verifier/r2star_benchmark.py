# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Local component benchmark for the exact R2Star producer and CPU replay.

The result is calibration data only.  It deliberately uses the native
replayer's bounded benchmark plan, whose wire header and output status cannot
be accepted by the source-scale registered-result finalizer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time
from typing import Any

from .evidence import EvidenceError, load_decimal_json_bytes
from .r2star import R2STAR_MAX_CHUNK_SPAN, R2STAR_SOURCE_LIMIT
from .r2star_campaign import (
    MAX_ARITHMETIC_REPLAY_OUTPUT_BYTES,
    MAX_RECEIPT_BYTES,
    R2StarCampaignError,
    arithmetic_replay_benchmark_plan,
    verify_runner_receipt,
)


class R2StarBenchmarkError(RuntimeError):
    """A local benchmark input or exact component execution failed closed."""


@dataclass(frozen=True)
class R2StarBenchmarkSample:
    producer_wall_nanoseconds: int
    replay_wall_nanoseconds: int
    receipt_sha256: str


def _regular_executable(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as error:
        raise R2StarBenchmarkError(f"cannot resolve {label}: {error}") from error
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not os.access(resolved, os.X_OK)
    ):
        raise R2StarBenchmarkError(
            f"{label} must be one executable, non-linked regular file"
        )
    return resolved


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _run_bounded(
    argv: list[str],
    *,
    timeout_seconds: int,
    maximum_stdout: int,
    label: str,
) -> tuple[subprocess.CompletedProcess[bytes], int]:
    started = time.perf_counter_ns()
    try:
        completed = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
            env={"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise R2StarBenchmarkError(f"{label} failed: {error}") from error
    elapsed = time.perf_counter_ns() - started
    if completed.returncode != 0:
        diagnostic = completed.stderr[-4000:].decode("utf-8", "replace")
        raise R2StarBenchmarkError(
            f"{label} exited {completed.returncode}: {diagnostic}"
        )
    if len(completed.stdout) > maximum_stdout:
        raise R2StarBenchmarkError(f"{label} emitted oversized output")
    return completed, elapsed


def _median_integer(values: list[int]) -> int:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) // 2


def benchmark_exact_pair(
    *,
    runner: Path,
    arithmetic_replayer: Path,
    lower: int,
    count: int,
    device: int = 0,
    repetitions: int = 1,
    replay_threads: int = 1,
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    """Benchmark one bounded exact CUDA chunk and its independent CPU replay."""

    if isinstance(lower, bool) or not isinstance(lower, int) or lower < 1:
        raise R2StarBenchmarkError("lower must be a positive integer")
    if isinstance(count, bool) or not (
        isinstance(count, int)
        and 3 <= count <= R2STAR_MAX_CHUNK_SPAN
        and lower + count - 1 <= R2STAR_SOURCE_LIMIT
    ):
        raise R2StarBenchmarkError(
            "count/range must describe 3..1000000 rows inside the source domain"
        )
    if isinstance(device, bool) or not isinstance(device, int) or device < 0:
        raise R2StarBenchmarkError("device must be a nonnegative integer")
    if isinstance(repetitions, bool) or not (
        isinstance(repetitions, int) and 1 <= repetitions <= 20
    ):
        raise R2StarBenchmarkError("repetitions must lie in [1,20]")
    if isinstance(replay_threads, bool) or not (
        isinstance(replay_threads, int) and 1 <= replay_threads <= 64
    ):
        raise R2StarBenchmarkError("replay_threads must lie in [1,64]")
    if isinstance(timeout_seconds, bool) or not (
        isinstance(timeout_seconds, int) and timeout_seconds >= 1
    ):
        raise R2StarBenchmarkError("timeout_seconds must be positive")

    runner = _regular_executable(runner, "R2Star producer")
    arithmetic_replayer = _regular_executable(
        arithmetic_replayer, "R2Star arithmetic replayer"
    )
    samples: list[R2StarBenchmarkSample] = []
    semantic_identity: tuple[Any, ...] | None = None
    device_identity: tuple[str, str] | None = None
    kernel_timings: list[dict[str, str]] = []
    for _index in range(repetitions):
        produced, producer_ns = _run_bounded(
            [
                str(runner),
                "--lower",
                str(lower),
                "--count",
                str(count),
                "--device",
                str(device),
            ],
            timeout_seconds=timeout_seconds,
            maximum_stdout=MAX_RECEIPT_BYTES,
            label="R2Star bounded producer",
        )
        try:
            report = load_decimal_json_bytes(
                produced.stdout, label="R2Star benchmark receipt"
            )
            chunk = verify_runner_receipt(report)
        except (EvidenceError, R2StarCampaignError) as error:
            raise R2StarBenchmarkError(str(error)) from error
        if (chunk.lower, chunk.upper) != (lower, lower + count):
            raise R2StarBenchmarkError(
                "producer receipt range differs from the benchmark request"
            )
        identity = (
            chunk,
            report["directed_rows_sha256_le_v1"],
            report["exact_rational_fallback_rows"],
        )
        if semantic_identity is None:
            semantic_identity = identity
        elif identity != semantic_identity:
            raise R2StarBenchmarkError(
                "repeated producer runs changed a semantic commitment"
            )
        current_device = (report["device_name"], report["compute_capability"])
        if device_identity is None:
            device_identity = current_device
        elif current_device != device_identity:
            raise R2StarBenchmarkError(
                "repeated producer runs changed device identity"
            )

        plan = arithmetic_replay_benchmark_plan([report])
        with tempfile.TemporaryDirectory(
            prefix=".r2star-benchmark-"
        ) as temporary:
            plan_path = Path(temporary) / "bounded-plan.tsv"
            plan_path.write_bytes(plan)
            replayed, replay_ns = _run_bounded(
                [
                    str(arithmetic_replayer),
                    "--plan",
                    str(plan_path),
                    "--threads",
                    str(replay_threads),
                ],
                timeout_seconds=timeout_seconds,
                maximum_stdout=MAX_ARITHMETIC_REPLAY_OUTPUT_BYTES,
                label="R2Star bounded arithmetic replay",
            )
        try:
            replay_report = json.loads(replayed.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise R2StarBenchmarkError(
                "arithmetic replay emitted malformed JSON"
            ) from error
        expected_replay = {
            "checked_chunks": 1,
            "checked_rows": count,
            "classification": (
                "bounded_cpu_r2star_arithmetic_replay_benchmark_v1"
            ),
            "source_lower": lower,
            "source_upper_exclusive": lower + count,
            "status": "BENCHMARK_ONLY",
        }
        if replay_report != expected_replay:
            raise R2StarBenchmarkError(
                "arithmetic replay did not emit the exact benchmark-only report"
            )
        samples.append(
            R2StarBenchmarkSample(
                producer_wall_nanoseconds=producer_ns,
                replay_wall_nanoseconds=replay_ns,
                receipt_sha256=hashlib.sha256(produced.stdout).hexdigest(),
            )
        )
        kernel_timings.append(
            {
                field: str(report[field])
                for field in (
                    "directed_row_kernel_milliseconds",
                    "factor_kernel_milliseconds",
                    "independent_factor_check_milliseconds",
                    "kernel_milliseconds",
                    "parallel_transition_kernel_milliseconds",
                )
            }
        )

    assert semantic_identity is not None and device_identity is not None
    producer_median = _median_integer(
        [sample.producer_wall_nanoseconds for sample in samples]
    )
    replay_median = _median_integer(
        [sample.replay_wall_nanoseconds for sample in samples]
    )
    return {
        "admissible_as_external_atom_evidence": False,
        "arithmetic_replayer_sha256": _sha256_file(arithmetic_replayer),
        "classification": (
            "local_bounded_r2star_component_benchmark_not_target_sku_evidence_v1"
        ),
        "compute_capability": device_identity[1],
        "count": count,
        "device_name": device_identity[0],
        "exact_rational_fallback_rows": int(semantic_identity[2]),
        "kernel_timings_milliseconds": kernel_timings,
        "lower": lower,
        "producer_median_rows_per_second_floor": (
            count * 1_000_000_000 // producer_median
        ),
        "repetitions": repetitions,
        "replay_median_rows_per_second_floor": (
            count * 1_000_000_000 // replay_median
        ),
        "replay_threads": replay_threads,
        "runner_sha256": _sha256_file(runner),
        "samples": [asdict(sample) for sample in samples],
        "source_scale_projection_is_linear_sensitivity_only": True,
        "target_sku_measurement": False,
        "upper_exclusive": lower + count,
    }


__all__ = [
    "R2StarBenchmarkError",
    "R2StarBenchmarkSample",
    "benchmark_exact_pair",
]
