#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark the checked warp-per-prime GoldbachGPU sieve prototype."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier.goldbach_warp_tail_optimizer import (
    GoldbachWarpTailOptimizerError,
    rewrite_warp_parallel_tail,
)
from tg_verifier.goldbach_word_owner_optimizer import (
    GoldbachWordOwnerOptimizerError,
    inspect_word_owner_source,
    rewrite_word_owner_cutoff,
)
from tools.benchmark_goldbach_word_owner import (
    BenchmarkError,
    _benchmark,
    _build,
    sha256,
)


def benchmark_warp_limits(
    source_root: Path,
    warp_limits: list[int],
    *,
    word_owner_cutoffs: list[int] | None,
    nvcc: Path,
    host_cxx: Path,
    arch: str,
    warmups: int,
    repetitions: int,
    timeout: int,
    retain_best: Path | None = None,
) -> dict[str, object]:
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
    inspected = inspect_word_owner_source(source)
    limits = list(dict.fromkeys(warp_limits))
    owners = list(
        dict.fromkeys(word_owner_cutoffs or [inspected.cutoff])
    )
    if not limits:
        raise BenchmarkError("at least one warp cutoff is required")
    if any(owner < 3 or owner > 65_535 for owner in owners):
        raise BenchmarkError("word-owner cutoffs must be in [3,65535]")
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

    rows: list[dict[str, object]] = []
    retained_best_path: str | None = None
    with tempfile.TemporaryDirectory(prefix="tg-goldbach-warp-tail-") as temporary:
        root = Path(temporary)
        variant_paths: dict[int, Path] = {}
        combined: list[tuple[str, int | None, int, str]] = [
            ("baseline", None, inspected.cutoff, source)
        ]
        for owner in owners:
            owner_source = rewrite_word_owner_cutoff(source, owner)
            for limit in limits:
                combined.append(
                    (
                        "word-owner-plus-warp-per-prime",
                        limit,
                        owner,
                        rewrite_warp_parallel_tail(owner_source, limit),
                    )
                )
        for index, (kind, limit, owner, variant_source) in enumerate(combined):
            variant = root / (
                "baseline"
                if limit is None
                else f"owner-{owner}-warp-{limit}"
            )
            variant_paths[index] = variant
            shutil.copytree(source_root, variant)
            (variant / "src/goldbach.cu").write_text(
                variant_source, encoding="utf-8", newline=""
            )
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
                    "candidate_index": index,
                    "kind": kind,
                    "word_owner_cutoff": owner,
                    "warp_parallel_cutoff": limit,
                    "source_sha256": sha256(variant / "src/goldbach.cu"),
                    "build": build,
                    "benchmark": benchmark,
                }
            )

        baseline = float(rows[0]["benchmark"]["median_seconds"])
        for row in rows:
            seconds = float(row["benchmark"]["median_seconds"])
            row["relative_rate_vs_baseline"] = f"{baseline / seconds:.9f}"
        best = min(
            rows, key=lambda row: float(row["benchmark"]["median_seconds"])
        )
        if retain_best is not None:
            if retain_best.exists():
                raise BenchmarkError("retained-best destination already exists")
            retain_best.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                variant_paths[int(best["candidate_index"])], retain_best
            )
            retained_best_path = str(retain_best.resolve())

    return {
        "accepted": True,
        "classification": "bounded-diagnostic-not-production-evidence",
        "kind": "sparkinterval.goldbach-warp-tail-benchmark.v1",
        "source_root": str(source_root.resolve()),
        "input_source_sha256": sha256(source_file),
        "input_word_owner_cutoff": inspected.cutoff,
        "architecture": arch,
        "candidates": rows,
        "best_observed_kind": best["kind"],
        "best_observed_word_owner_cutoff": best["word_owner_cutoff"],
        "best_observed_warp_cutoff": best["warp_parallel_cutoff"],
        "best_observed_median_seconds": best["benchmark"]["median_seconds"],
        "median_of_candidate_medians": f"{statistics.median(float(row['benchmark']['median_seconds']) for row in rows):.9f}",
        "production_identity_changed": False,
        "retained_best_path": retained_best_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument(
        "--warp-limit", type=int, action="append", required=True
    )
    parser.add_argument(
        "--word-owner-cutoff",
        type=int,
        action="append",
        help="candidate prefix cutoff; defaults to the prepared source cutoff",
    )
    parser.add_argument("--nvcc", type=Path, default=Path("/usr/local/cuda/bin/nvcc"))
    parser.add_argument("--host-cxx", type=Path, default=Path("/usr/bin/g++"))
    parser.add_argument("--arch", default="native")
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument(
        "--retain-best",
        type=Path,
        help="copy the best diagnostic source tree and binary to this new path",
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    try:
        report = benchmark_warp_limits(
            arguments.source_root,
            arguments.warp_limit,
            word_owner_cutoffs=arguments.word_owner_cutoff,
            nvcc=arguments.nvcc,
            host_cxx=arguments.host_cxx,
            arch=arguments.arch,
            warmups=arguments.warmups,
            repetitions=arguments.repetitions,
            timeout=arguments.timeout,
            retain_best=arguments.retain_best,
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
        GoldbachWarpTailOptimizerError,
        GoldbachWordOwnerOptimizerError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
