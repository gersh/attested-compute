# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded differential benchmark for Goldbach prime-prefix reuse.

The benchmark runs an exact-vector crosscheck once, then compares separately
built v1 and v2 binaries in an interleaved ABBA order.  Timing fields are not
used as correctness evidence: every non-timing semantic transcript field must
match exactly and every run must report zero phase-2 fallbacks.
"""

from __future__ import annotations

from decimal import Decimal
import hashlib
from pathlib import Path
import re
import statistics
import subprocess
import time
from typing import Literal

from .goldbach_gpu_campaign import BATCH_SIZE, P_SMALL, SEGMENT_SIZE
from .goldbach_prime_prefix_reuse_candidate import (
    EXPECTED_CROSSCHECK_SOURCE_SHA256,
    EXPECTED_GOLDBACH_SOURCE_SHA256,
    EXPECTED_SOURCE_IDENTITY_SHA256,
)
from .goldbach_prime_prefix_reuse_optimizer import (
    V1_OPTIMIZED_SOURCE_SHA256,
    V2_ALGORITHM_CANDIDATE_ID,
)


DEFAULT_EVEN_START = 31_249_998_800_000_002
DEFAULT_EVEN_LIMIT = 31_250_000_000_000_000
MAX_EVEN_COUNT = 600_000_000
EXACT_CPU_PRIME_PREFIX_COUNT = 5_761_455
MAX_STDOUT_BYTES = 16 * 1024
CHECKPOINT_LEAF_COUNT = 65_536
DEFAULT_CLUSTER_GPU_COUNT = 8
CLASSIFICATION = (
    "bounded-local-gb10-differential-benchmark-not-production-evidence"
)
_NUMBER = r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
_TRANSCRIPT = re.compile(
    r"\A\[Hardware\] GPU 0: (?P<gpu>[^\r\n\[\]]+) "
    r"\((?P<vram>[1-9][0-9]*) MB VRAM\)\n"
    r"Building small primes bitset up to (?P<small>[1-9][0-9]*)\.\.\.\n"
    r"(?P<table>"
    r"Pre-generating CPU primes up to 100000000\.\.\.|"
    r"Reusing CPU-prime prefix through 100000000\.\.\.)\n"
    r"(?:(?P<cross>CPU-prime prefix exact-vector crosscheck: "
    r"(?P<cross_count>[1-9][0-9]*) entries matched\.)\n)?"
    rf"Initialization completed in (?P<init>{_NUMBER}) ms\.\n\n"
    r"--- Launching Multi-GPU Verifier ---\n"
    r"Checking range : \[(?P<start>[0-9]+), (?P<limit>[0-9]+)\]\n"
    r"Total numbers  : (?P<count>[0-9]+)\n\n\n"
    r"--- Verification Complete ---\n"
    r"All even numbers from (?P<success_start>[0-9]+) up to "
    r"(?P<success_limit>[0-9]+) satisfy Goldbach\. ✓\n"
    rf"Total computation time : (?P<seconds>{_NUMBER}) seconds\n"
    r"Phase 2 fallbacks      : (?P<fallbacks>[0-9]+)\n\Z"
)


class GoldbachPrimePrefixBenchmarkError(RuntimeError):
    """A bounded executable, transcript, or differential check failed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _pin(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise GoldbachPrimePrefixBenchmarkError(
            f"benchmark executable is absent or linked: {path}"
        )
    return {
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _expected_small_high(limit: int) -> int:
    from math import isqrt

    result = max(isqrt(limit) + 1, min(P_SMALL, limit))
    return result if result % 2 else result + 1


def parse_bounded_stdout(
    raw: bytes,
    *,
    role: Literal["v1", "v2", "crosscheck"],
    even_start: int,
    even_limit: int,
) -> dict[str, object]:
    """Strictly parse one candidate transcript for the selected role."""

    if len(raw) > MAX_STDOUT_BYTES:
        raise GoldbachPrimePrefixBenchmarkError(
            "bounded benchmark stdout exceeds limit"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise GoldbachPrimePrefixBenchmarkError(
            "bounded benchmark stdout is not UTF-8"
        ) from error
    match = _TRANSCRIPT.fullmatch(text)
    if match is None:
        raise GoldbachPrimePrefixBenchmarkError(
            "bounded benchmark stdout grammar differs"
        )
    values = match.groupdict()
    even_count = (even_limit - even_start) // 2 + 1
    expected = {
        "small": _expected_small_high(even_limit),
        "start": even_start,
        "limit": even_limit,
        "count": even_count,
        "success_start": even_start,
        "success_limit": even_limit,
        "fallbacks": 0,
    }
    if any(int(values[name]) != wanted for name, wanted in expected.items()):
        raise GoldbachPrimePrefixBenchmarkError(
            "bounded benchmark semantic transcript differs"
        )
    reused = values["table"].startswith("Reusing")
    cross_count = (
        int(values["cross_count"])
        if values["cross_count"] is not None
        else None
    )
    if role == "v1" and (reused or cross_count is not None):
        raise GoldbachPrimePrefixBenchmarkError(
            "v1 transcript used the prefix-reuse path"
        )
    if role == "v2" and (not reused or cross_count is not None):
        raise GoldbachPrimePrefixBenchmarkError(
            "v2 transcript did not use only the productive reuse path"
        )
    if role == "crosscheck" and (
        not reused or cross_count != EXACT_CPU_PRIME_PREFIX_COUNT
    ):
        raise GoldbachPrimePrefixBenchmarkError(
            "crosscheck did not compare the exact complete ordered vector"
        )
    return {
        "role": role,
        "gpu_name": values["gpu"],
        "gpu_vram_mb": int(values["vram"]),
        "small_prime_bitset_limit": int(values["small"]),
        "even_start": int(values["start"]),
        "even_limit": int(values["limit"]),
        "even_count": int(values["count"]),
        "all_even_numbers_reported_satisfied": True,
        "phase2_fallbacks": int(values["fallbacks"]),
        "cpu_prime_table_mode": (
            "reused-complete-prefix" if reused else "independent-sieve"
        ),
        "exact_vector_crosscheck_entries": cross_count,
        "initialization_milliseconds": values["init"],
        "reported_computation_seconds": values["seconds"],
    }


def _semantic_projection(parsed: dict[str, object]) -> dict[str, object]:
    return {
        name: parsed[name]
        for name in (
            "gpu_name",
            "gpu_vram_mb",
            "small_prime_bitset_limit",
            "even_start",
            "even_limit",
            "even_count",
            "all_even_numbers_reported_satisfied",
            "phase2_fallbacks",
        )
    }


def _run(
    executable: Path,
    *,
    role: Literal["v1", "v2", "crosscheck"],
    even_start: int,
    even_limit: int,
    timeout: int,
) -> dict[str, object]:
    argv = [
        str(executable.resolve(strict=True)),
        str(even_limit),
        f"--start={even_start}",
        f"--seg-size={SEGMENT_SIZE}",
        f"--p-small={P_SMALL}",
        f"--batch-size={BATCH_SIZE}",
        "--gpus=1",
        "--primetest=mr",
    ]
    started = time.monotonic_ns()
    try:
        completed = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise GoldbachPrimePrefixBenchmarkError(
            f"{role} bounded execution did not complete"
        ) from error
    elapsed = time.monotonic_ns() - started
    if completed.returncode != 0 or completed.stderr:
        raise GoldbachPrimePrefixBenchmarkError(
            f"{role} bounded execution failed or wrote stderr"
        )
    parsed = parse_bounded_stdout(
        completed.stdout,
        role=role,
        even_start=even_start,
        even_limit=even_limit,
    )
    return {
        "wall_nanoseconds": elapsed,
        "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
        "parsed": parsed,
    }


def benchmark_prime_prefix_reuse(
    *,
    v1_executable: Path,
    v2_executable: Path,
    crosscheck_executable: Path,
    even_start: int = DEFAULT_EVEN_START,
    even_limit: int = DEFAULT_EVEN_LIMIT,
    rounds: int = 3,
    warmups: int = 1,
    timeout: int = 30,
) -> dict[str, object]:
    """Run an exact-vector check and an interleaved bounded timing comparison."""

    if (
        isinstance(even_start, bool)
        or not isinstance(even_start, int)
        or isinstance(even_limit, bool)
        or not isinstance(even_limit, int)
        or even_start < 4
        or even_start % 2
        or even_limit < even_start
        or even_limit % 2
    ):
        raise GoldbachPrimePrefixBenchmarkError(
            "benchmark range must be nonempty and even"
        )
    even_count = (even_limit - even_start) // 2 + 1
    if even_count > MAX_EVEN_COUNT:
        raise GoldbachPrimePrefixBenchmarkError(
            "benchmark range exceeds the 600-million-even cap"
        )
    if (
        isinstance(rounds, bool)
        or not isinstance(rounds, int)
        or not 1 <= rounds <= 20
        or isinstance(warmups, bool)
        or not isinstance(warmups, int)
        or not 0 <= warmups <= 3
        or isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or timeout <= 0
    ):
        raise GoldbachPrimePrefixBenchmarkError(
            "benchmark repetition/timeout parameters differ"
        )
    pins = {
        "v1": _pin(v1_executable),
        "v2": _pin(v2_executable),
        "crosscheck": _pin(crosscheck_executable),
    }
    crosscheck = _run(
        crosscheck_executable,
        role="crosscheck",
        even_start=even_start,
        even_limit=even_limit,
        timeout=timeout,
    )
    warmup_rows: list[dict[str, object]] = []
    for _ in range(warmups):
        for role, executable in (
            ("v1", v1_executable),
            ("v2", v2_executable),
        ):
            warmup_rows.append(
                _run(
                    executable,
                    role=role,
                    even_start=even_start,
                    even_limit=even_limit,
                    timeout=timeout,
                )
            )
    rows: dict[str, list[dict[str, object]]] = {"v1": [], "v2": []}
    # Two observations of each role per round, with reversed adjacent order.
    for role in ("v1", "v2", "v2", "v1") * rounds:
        executable = v1_executable if role == "v1" else v2_executable
        row = _run(
            executable,
            role=role,
            even_start=even_start,
            even_limit=even_limit,
            timeout=timeout,
        )
        rows[role].append(row)
    semantic = _semantic_projection(crosscheck["parsed"])
    for row in [*warmup_rows, *rows["v1"], *rows["v2"]]:
        if _semantic_projection(row["parsed"]) != semantic:
            raise GoldbachPrimePrefixBenchmarkError(
                "v1/v2/crosscheck semantic transcript projections differ"
            )

    def medians(role: str) -> dict[str, str]:
        selected = rows[role]
        init = [
            Decimal(str(row["parsed"]["initialization_milliseconds"]))
            for row in selected
        ]
        compute = [
            Decimal(str(row["parsed"]["reported_computation_seconds"]))
            for row in selected
        ]
        wall = [
            Decimal(int(row["wall_nanoseconds"])) / Decimal(1_000_000_000)
            for row in selected
        ]
        return {
            "initialization_milliseconds": str(statistics.median(init)),
            "reported_computation_seconds": str(statistics.median(compute)),
            "whole_process_wall_seconds": str(statistics.median(wall)),
        }

    v1_median = medians("v1")
    v2_median = medians("v2")
    saved_ms = (
        Decimal(v1_median["initialization_milliseconds"])
        - Decimal(v2_median["initialization_milliseconds"])
    )
    saved_cluster_hours = (
        saved_ms
        * Decimal(CHECKPOINT_LEAF_COUNT)
        / Decimal(DEFAULT_CLUSTER_GPU_COUNT)
        / Decimal(3_600_000)
    )
    return {
        "accepted": True,
        "schema": (
            "sparkinterval.goldbach-prime-prefix-reuse-benchmark.v2"
        ),
        "classification": CLASSIFICATION,
        "algorithm_candidate_id": V2_ALGORITHM_CANDIDATE_ID,
        "source_identity": {
            "v1_goldbach_source_sha256": V1_OPTIMIZED_SOURCE_SHA256,
            "v2_goldbach_source_sha256": EXPECTED_GOLDBACH_SOURCE_SHA256,
            "v2_complete_source_identity_sha256": (
                EXPECTED_SOURCE_IDENTITY_SHA256
            ),
            "crosscheck_goldbach_source_sha256": (
                EXPECTED_CROSSCHECK_SOURCE_SHA256
            ),
        },
        "executables": pins,
        "domain": {
            "even_start": even_start,
            "even_limit": even_limit,
            "even_count": even_count,
        },
        "exact_vector_crosscheck": crosscheck,
        "warmups_per_role": warmups,
        "rounds": rounds,
        "timed_runs_per_role": 2 * rounds,
        "semantic_projection": semantic,
        "runs": rows,
        "medians": {"v1": v1_median, "v2": v2_median},
        "comparison": {
            "initialization_saved_milliseconds_per_leaf": str(saved_ms),
            "initialization_speedup": str(
                Decimal(v1_median["initialization_milliseconds"])
                / Decimal(v2_median["initialization_milliseconds"])
            ),
            "whole_process_speedup": str(
                Decimal(v1_median["whole_process_wall_seconds"])
                / Decimal(v2_median["whole_process_wall_seconds"])
            ),
            "projected_saved_wall_hours_at_65536_leaves_8_gpus": str(
                saved_cluster_hours
            ),
        },
        "confidential_attestation_completed": False,
        "lean_atom_discharged": False,
        "production_identity_promoted": False,
        "source_scale_completion": False,
        "target_h100_measured": False,
    }


__all__ = [
    "CLASSIFICATION",
    "DEFAULT_EVEN_LIMIT",
    "DEFAULT_EVEN_START",
    "EXACT_CPU_PRIME_PREFIX_COUNT",
    "GoldbachPrimePrefixBenchmarkError",
    "benchmark_prime_prefix_reuse",
    "parse_bounded_stdout",
]
