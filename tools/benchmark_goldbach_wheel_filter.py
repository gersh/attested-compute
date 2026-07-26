#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark the exact 15015-wheel Goldbach sieve-tail post-transform."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier.goldbach_shifted_coverage_optimizer import (
    GoldbachShiftedCoverageOptimizerError,
    rewrite_shifted_phase1,
)
from tg_verifier.goldbach_warp_tail_optimizer import (
    GoldbachWarpTailOptimizerError,
    rewrite_warp_parallel_tail,
)
from tg_verifier.goldbach_wheel_filtered_tail_optimizer import (
    GoldbachWheelFilteredTailOptimizerError,
    rewrite_wheel_filtered_sieve,
    rewrite_wheel_filtered_sieve_crosscheck,
)
from tg_verifier.goldbach_word_owner_optimizer import (
    GoldbachWordOwnerOptimizerError,
    inspect_word_owner_source,
)
from tools.benchmark_goldbach_word_owner import (
    BenchmarkError,
    _benchmark,
    _build,
    sha256,
)


def _combined_source(source: str, warp_limit: int) -> str:
    return rewrite_shifted_phase1(
        rewrite_warp_parallel_tail(source, warp_limit)
    )


def benchmark(
    source_root: Path,
    *,
    control_warp_limit: int,
    wheel_warp_limits: list[int],
    filter_limits: list[int],
    include_crosscheck: bool,
    nvcc: Path,
    host_cxx: Path,
    arch: str,
    warmups: int,
    repetitions: int,
    timeout: int,
    retain_best: Path | None = None,
) -> dict[str, object]:
    source_file = source_root / "src/goldbach.cu"
    if not source_file.is_file():
        raise BenchmarkError("prepared GoldbachGPU source is missing")
    source = source_file.read_text(encoding="utf-8")
    inspected = inspect_word_owner_source(source)
    limits = list(dict.fromkeys(wheel_warp_limits))
    filters = list(dict.fromkeys(filter_limits))
    if not limits:
        raise BenchmarkError("at least one wheel-filter warp cutoff is required")
    if not filters:
        raise BenchmarkError("at least one cofactor filter limit is required")
    if repetitions < 1 or repetitions > 25:
        raise BenchmarkError("repetitions must be in [1,25]")
    if warmups < 0 or warmups > 10:
        raise BenchmarkError("warmups must be in [0,10]")
    if timeout < 10 or timeout > 3600:
        raise BenchmarkError("per-command timeout must be in [10,3600]")
    if not re.fullmatch(r"(?:native|sm_[0-9]{2,3})", arch):
        raise BenchmarkError("architecture must be native or sm_NN")
    if not nvcc.is_file() or not host_cxx.is_file():
        raise BenchmarkError("compiler paths must name regular files")

    variants: list[tuple[str, int, int | None, str]] = [
        (
            "word-owner-warp-tail-shifted-control",
            control_warp_limit,
            None,
            _combined_source(source, control_warp_limit),
        )
    ]
    candidate_indices: list[int] = []
    for limit in limits:
        combined = _combined_source(source, limit)
        for filter_limit in filters:
            candidate_indices.append(len(variants))
            variants.append(
                (
                    "wheel-filtered-word-owner-warp-tail-shifted",
                    limit,
                    filter_limit,
                    rewrite_wheel_filtered_sieve(combined, filter_limit),
                )
            )
            if include_crosscheck:
                variants.append(
                    (
                        "full-word-crosscheck-wheel-filtered-sieve",
                        limit,
                        filter_limit,
                        rewrite_wheel_filtered_sieve_crosscheck(
                            combined, filter_limit
                        ),
                    )
                )

    rows: list[dict[str, object]] = []
    retained_best_path: str | None = None
    with tempfile.TemporaryDirectory(
        prefix="tg-goldbach-wheel-filter-"
    ) as temporary:
        root = Path(temporary)
        paths: dict[int, Path] = {}
        for index, (
            kind,
            limit,
            filter_limit,
            variant_source,
        ) in enumerate(variants):
            variant = root / (
                f"{index}-{kind}-warp-{limit}-filter-{filter_limit}"
            )
            paths[index] = variant
            shutil.copytree(source_root, variant)
            (variant / "src/goldbach.cu").write_text(
                variant_source, encoding="utf-8", newline=""
            )
            executable = variant / "goldbach"
            built = _build(
                variant,
                executable,
                nvcc=nvcc,
                host_cxx=host_cxx,
                arch=arch,
                timeout=timeout,
            )
            measured = _benchmark(
                executable,
                warmups=warmups,
                repetitions=repetitions,
                timeout=timeout,
            )
            rows.append(
                {
                    "candidate_index": index,
                    "cofactor_filter_limit": filter_limit,
                    "kind": kind,
                    "source_sha256": sha256(variant / "src/goldbach.cu"),
                    "warp_parallel_cutoff": limit,
                    "build": built,
                    "benchmark": measured,
                }
            )

        control_seconds = float(rows[0]["benchmark"]["median_seconds"])
        for row in rows:
            seconds = float(row["benchmark"]["median_seconds"])
            row["relative_rate_vs_control"] = (
                f"{control_seconds / seconds:.9f}"
            )
        best = min(
            (rows[index] for index in candidate_indices),
            key=lambda row: float(row["benchmark"]["median_seconds"]),
        )
        if retain_best is not None:
            if float(best["benchmark"]["median_seconds"]) >= control_seconds:
                raise BenchmarkError(
                    "wheel-filter prototype did not beat the control; "
                    "refusing to retain it"
                )
            if retain_best.exists():
                raise BenchmarkError("retained-best destination already exists")
            retain_best.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                paths[int(best["candidate_index"])], retain_best
            )
            retained_best_path = str(retain_best.resolve())

    return {
        "accepted": True,
        "architecture": arch,
        "best_observed_kind": best["kind"],
        "best_observed_median_seconds": best["benchmark"]["median_seconds"],
        "best_observed_filter_limit": best["cofactor_filter_limit"],
        "best_observed_warp_cutoff": best["warp_parallel_cutoff"],
        "candidates": rows,
        "classification": "bounded-diagnostic-not-production-evidence",
        "control_warp_cutoff": control_warp_limit,
        "input_source_sha256": sha256(source_file),
        "kind": "sparkinterval.goldbach-wheel-filter-benchmark.v1",
        "production_identity_changed": False,
        "retained_best_path": retained_best_path,
        "wheel_modulus": 15_015,
        "word_owner_cutoff": inspected.cutoff,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--control-warp-limit", type=int, default=32_749)
    parser.add_argument(
        "--wheel-warp-limit", type=int, action="append", required=True
    )
    parser.add_argument(
        "--filter-limit", type=int, action="append", default=None
    )
    parser.add_argument("--include-crosscheck", action="store_true")
    parser.add_argument(
        "--nvcc", type=Path, default=Path("/usr/local/cuda/bin/nvcc")
    )
    parser.add_argument("--host-cxx", type=Path, default=Path("/usr/bin/g++"))
    parser.add_argument("--arch", default="native")
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--retain-best", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    try:
        report = benchmark(
            arguments.source_root,
            control_warp_limit=arguments.control_warp_limit,
            wheel_warp_limits=arguments.wheel_warp_limit,
            filter_limits=arguments.filter_limit or [13],
            include_crosscheck=arguments.include_crosscheck,
            nvcc=arguments.nvcc,
            host_cxx=arguments.host_cxx,
            arch=arguments.arch,
            warmups=arguments.warmups,
            repetitions=arguments.repetitions,
            timeout=arguments.timeout,
            retain_best=arguments.retain_best,
        )
        encoded = (
            json.dumps(report, indent=2, sort_keys=True).encode("utf-8")
            + b"\n"
            if arguments.pretty
            else canonical_json_bytes(report)
        )
        if arguments.out is not None:
            arguments.out.parent.mkdir(parents=True, exist_ok=True)
            arguments.out.write_bytes(encoded)
        sys.stdout.buffer.write(encoded)
    except (
        BenchmarkError,
        GoldbachShiftedCoverageOptimizerError,
        GoldbachWarpTailOptimizerError,
        GoldbachWheelFilteredTailOptimizerError,
        GoldbachWordOwnerOptimizerError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
