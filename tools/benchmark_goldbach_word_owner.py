#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""A/B benchmark checked GoldbachGPU word-owner cutoff candidates.

This is a bounded optimizer, not production evidence.  It rebuilds each
candidate from a previously prepared, source-pinned GoldbachGPU tree and runs
the same 600-million-even terminal range used by the retained GB10 profile.
Every timed run must report the exact range, exact count, successful theorem
sentence, and zero CPU fallbacks.  Candidate binaries and timings do not alter
the reviewed production source identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier.goldbach_word_owner_optimizer import (
    GoldbachWordOwnerOptimizerError,
    inspect_word_owner_source,
    rewrite_word_owner_cutoff,
)


SAMPLE_EVEN_START = 31_249_998_800_000_002
SAMPLE_EVEN_LIMIT = 31_250_000_000_000_000
SAMPLE_EVEN_COUNT = 600_000_000
SAMPLE_SEGMENT_SIZE = 200_000_000
SAMPLE_P_SMALL = 1_000_000
SAMPLE_BATCH_SIZE = 2_000_000
_TIME_RE = re.compile(
    r"^Total computation time\s*:\s*"
    r"(?P<seconds>[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?) seconds$",
    re.MULTILINE,
)


class BenchmarkError(RuntimeError):
    """A candidate could not be built or did not satisfy the output contract."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_successful_run(stdout: str) -> float:
    """Validate the complete bounded-run contract and return its kernel time."""

    required = (
        "Checking range : "
        f"[{SAMPLE_EVEN_START}, {SAMPLE_EVEN_LIMIT}]",
        f"Total numbers  : {SAMPLE_EVEN_COUNT}",
        "All even numbers from "
        f"{SAMPLE_EVEN_START} up to {SAMPLE_EVEN_LIMIT} "
        "satisfy Goldbach.",
        "Phase 2 fallbacks      : 0",
    )
    for text in required:
        if text not in stdout:
            raise BenchmarkError(f"runner output is missing exact contract: {text}")
    times = list(_TIME_RE.finditer(stdout))
    if len(times) != 1:
        raise BenchmarkError("runner output does not contain one computation time")
    seconds = float(times[0].group("seconds"))
    if not (seconds > 0.0):
        raise BenchmarkError("runner reported a nonpositive computation time")
    return seconds


def _run(argv: list[str], *, cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
        env={
            "HOME": "/nonexistent",
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": "/usr/local/cuda/bin:/usr/bin:/bin",
            "TZ": "UTC",
        },
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise BenchmarkError(
            f"command failed with exit {completed.returncode}: {detail}"
        )
    return completed


def _copy_variant(source_root: Path, destination: Path, cutoff: int) -> Path:
    source_file = source_root / "src/goldbach.cu"
    required = (
        source_file,
        source_root / "src/prime_bitset.cpp",
        source_root / "src/segmented_sieve.cpp",
        source_root / "include/prime_bitset.hpp",
    )
    if not all(path.is_file() for path in required):
        raise BenchmarkError("prepared source tree is incomplete")
    source = source_file.read_text(encoding="utf-8")
    inspect_word_owner_source(source)
    shutil.copytree(source_root, destination)
    (destination / "src/goldbach.cu").write_text(
        rewrite_word_owner_cutoff(source, cutoff),
        encoding="utf-8",
        newline="",
    )
    return destination / "src/goldbach.cu"


def _host_flags() -> str:
    machine = platform.machine()
    if machine == "x86_64":
        return "-O3,-march=x86-64-v2,-mtune=generic,-fopenmp"
    if machine in {"aarch64", "arm64"}:
        return "-O3,-march=armv8-a,-mtune=generic,-fopenmp"
    raise BenchmarkError(f"unsupported benchmark host architecture: {machine}")


def _build(
    source_root: Path,
    executable: Path,
    *,
    nvcc: Path,
    host_cxx: Path,
    arch: str,
    timeout: int,
) -> dict[str, object]:
    argv = [
        str(nvcc),
        "-O3",
        "-std=c++17",
        f"-arch={arch}",
        "-ccbin",
        str(host_cxx),
        "--threads",
        "1",
        "-I",
        str(source_root / "include"),
        f"-Xcompiler={_host_flags()}",
        str(source_root / "src/goldbach.cu"),
        str(source_root / "src/prime_bitset.cpp"),
        str(source_root / "src/segmented_sieve.cpp"),
        "-lgomp",
        "-o",
        str(executable),
    ]
    started = time.monotonic()
    _run(argv, cwd=source_root, timeout=timeout)
    return {
        "argv": argv,
        "elapsed_seconds": f"{time.monotonic() - started:.6f}",
        "executable_sha256": sha256(executable),
        "executable_size_bytes": executable.stat().st_size,
    }


def _benchmark(
    executable: Path, *, warmups: int, repetitions: int, timeout: int
) -> dict[str, object]:
    argv = [
        str(executable),
        str(SAMPLE_EVEN_LIMIT),
        f"--start={SAMPLE_EVEN_START}",
        f"--seg-size={SAMPLE_SEGMENT_SIZE}",
        f"--p-small={SAMPLE_P_SMALL}",
        f"--batch-size={SAMPLE_BATCH_SIZE}",
        "--gpus=1",
        "--primetest=mr",
    ]
    values: list[float] = []
    for index in range(warmups + repetitions):
        completed = _run(argv, cwd=executable.parent, timeout=timeout)
        seconds = parse_successful_run(completed.stdout)
        if index >= warmups:
            values.append(seconds)
    median = statistics.median(values)
    return {
        "argv": argv,
        "all_seconds": [f"{value:.9f}" for value in values],
        "median_seconds": f"{median:.9f}",
        "median_evens_per_second": f"{SAMPLE_EVEN_COUNT / median:.3f}",
        "repetitions": repetitions,
        "warmups": warmups,
        "validated_contract": {
            "even_start": str(SAMPLE_EVEN_START),
            "even_limit": str(SAMPLE_EVEN_LIMIT),
            "even_count": str(SAMPLE_EVEN_COUNT),
            "phase2_fallbacks": 0,
            "primality_mode": "mr",
        },
    }


def benchmark_candidates(
    source_root: Path,
    cutoffs: list[int],
    *,
    nvcc: Path,
    host_cxx: Path,
    arch: str,
    warmups: int,
    repetitions: int,
    timeout: int,
) -> dict[str, object]:
    if repetitions < 1 or repetitions > 25:
        raise BenchmarkError("repetitions must be in [1,25]")
    if warmups < 0 or warmups > 10:
        raise BenchmarkError("warmups must be in [0,10]")
    if timeout < 10 or timeout > 3600:
        raise BenchmarkError("per-command timeout must be in [10,3600] seconds")
    if not re.fullmatch(r"(?:native|sm_[0-9]{2,3})", arch):
        raise BenchmarkError("architecture must be native or sm_NN")
    if not nvcc.is_file() or not host_cxx.is_file():
        raise BenchmarkError("compiler paths must name regular files")
    source_file = source_root / "src/goldbach.cu"
    if not source_file.is_file():
        raise BenchmarkError("prepared GoldbachGPU source is missing")
    inspected = inspect_word_owner_source(source_file.read_text(encoding="utf-8"))
    ordered = list(dict.fromkeys([inspected.cutoff, *cutoffs]))
    if any(cutoff < 3 or cutoff > 65_535 for cutoff in ordered):
        raise BenchmarkError("candidate cutoffs must be in [3,65535]")

    rows = []
    with tempfile.TemporaryDirectory(prefix="tg-goldbach-cutoff-") as temporary:
        root = Path(temporary)
        for cutoff in ordered:
            variant = root / f"cutoff-{cutoff}"
            variant_source = _copy_variant(source_root, variant, cutoff)
            executable = variant / "goldbach"
            build = _build(
                variant,
                executable,
                nvcc=nvcc,
                host_cxx=host_cxx,
                arch=arch,
                timeout=timeout,
            )
            benchmark = _benchmark(
                executable,
                warmups=warmups,
                repetitions=repetitions,
                timeout=timeout,
            )
            rows.append(
                {
                    "cutoff": cutoff,
                    "source_sha256": sha256(variant_source),
                    "build": build,
                    "benchmark": benchmark,
                }
            )

    baseline = float(rows[0]["benchmark"]["median_seconds"])
    for row in rows:
        seconds = float(row["benchmark"]["median_seconds"])
        row["relative_rate_vs_baseline"] = f"{baseline / seconds:.9f}"
    best = min(rows, key=lambda row: float(row["benchmark"]["median_seconds"]))
    return {
        "accepted": True,
        "classification": "bounded-diagnostic-not-production-evidence",
        "kind": "sparkinterval.goldbach-word-owner-cutoff-benchmark.v1",
        "source_root": str(source_root.resolve()),
        "input_source_sha256": sha256(source_file),
        "baseline_cutoff": inspected.cutoff,
        "architecture": arch,
        "nvcc_sha256": sha256(nvcc),
        "host_cxx_sha256": sha256(host_cxx),
        "candidates": rows,
        "best_observed_cutoff": best["cutoff"],
        "best_observed_median_seconds": best["benchmark"]["median_seconds"],
        "production_identity_changed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument(
        "--cutoff",
        type=int,
        action="append",
        required=True,
        help="candidate cutoff; the source cutoff is always benchmarked first",
    )
    parser.add_argument("--nvcc", type=Path, default=Path("/usr/local/cuda/bin/nvcc"))
    parser.add_argument("--host-cxx", type=Path, default=Path("/usr/bin/g++"))
    parser.add_argument("--arch", default="native")
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    try:
        report = benchmark_candidates(
            arguments.source_root,
            arguments.cutoff,
            nvcc=arguments.nvcc,
            host_cxx=arguments.host_cxx,
            arch=arguments.arch,
            warmups=arguments.warmups,
            repetitions=arguments.repetitions,
            timeout=arguments.timeout,
        )
        encoded = (
            json.dumps(report, indent=2, sort_keys=True).encode("utf-8") + b"\n"
            if arguments.pretty
            else canonical_json_bytes(report)
        )
        if arguments.out is not None:
            arguments.out.parent.mkdir(parents=True, exist_ok=True)
            arguments.out.write_bytes(encoded)
        sys.stdout.buffer.write(encoded)
    except (
        BenchmarkError,
        GoldbachWordOwnerOptimizerError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
