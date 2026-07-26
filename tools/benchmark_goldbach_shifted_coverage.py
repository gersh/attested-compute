#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark integrated real-sieve shifted-word Goldbach coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
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
    rewrite_packed_count_crosscheck,
    rewrite_packed_shifted_unverified_count,
    rewrite_shifted_phase1,
    rewrite_shifted_phase1_crosscheck,
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


def benchmark(
    source_root: Path,
    *,
    warp_limit: int,
    cofactor_filter_limit: int,
    nvcc: Path,
    host_cxx: Path,
    arch: str,
    warmups: int,
    repetitions: int,
    timeout: int,
    retain_combined: Path | None = None,
    retain_crosscheck: Path | None = None,
) -> dict[str, object]:
    source_file = source_root / "src/goldbach.cu"
    source = source_file.read_text(encoding="utf-8")
    inspected = inspect_word_owner_source(source)
    warp_source = rewrite_warp_parallel_tail(source, warp_limit)
    shifted_warp_source = rewrite_shifted_phase1(warp_source)
    wheel_shifted_warp_source = rewrite_wheel_filtered_sieve(
        shifted_warp_source, cofactor_filter_limit
    )
    variants = (
        ("baseline", source),
        ("shifted-phase1", rewrite_shifted_phase1(source)),
        (
            "warp-tail-plus-shifted-phase1",
            shifted_warp_source,
        ),
        (
            "packed-count-warp-tail-plus-shifted-phase1",
            rewrite_packed_shifted_unverified_count(
                shifted_warp_source
            ),
        ),
        (
            "packed-count-wheel-filtered-warp-tail-plus-shifted-phase1",
            rewrite_packed_shifted_unverified_count(
                wheel_shifted_warp_source
            ),
        ),
        (
            "full-sieve-phase-bit-and-packed-count-crosscheck",
            rewrite_wheel_filtered_sieve_crosscheck(
                rewrite_packed_count_crosscheck(
                    rewrite_shifted_phase1_crosscheck(warp_source)
                ),
                cofactor_filter_limit,
            ),
        ),
    )
    rows = []
    with tempfile.TemporaryDirectory(
        prefix="tg-goldbach-shifted-coverage-"
    ) as temporary:
        root = Path(temporary)
        for index, (kind, variant_source) in enumerate(variants):
            variant = root / f"{index}-{kind}"
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
            measured = _benchmark(
                executable,
                warmups=warmups,
                repetitions=repetitions,
                timeout=timeout,
            )
            rows.append(
                {
                    "candidate_index": index,
                    "kind": kind,
                    "source_sha256": sha256(variant / "src/goldbach.cu"),
                    "build": build,
                    "benchmark": measured,
                }
            )
            if (
                kind
                == "packed-count-wheel-filtered-warp-tail-plus-shifted-phase1"
                and retain_combined is not None
            ):
                if retain_combined.exists():
                    raise BenchmarkError(
                        "retained-combined destination already exists"
                    )
                retain_combined.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(variant, retain_combined)
            if (
                kind
                == "full-sieve-phase-bit-and-packed-count-crosscheck"
                and retain_crosscheck is not None
            ):
                if retain_crosscheck.exists():
                    raise BenchmarkError(
                        "retained-crosscheck destination already exists"
                    )
                retain_crosscheck.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(variant, retain_crosscheck)
    baseline = float(rows[0]["benchmark"]["median_seconds"])
    for row in rows:
        seconds = float(row["benchmark"]["median_seconds"])
        row["relative_rate_vs_baseline"] = f"{baseline / seconds:.9f}"
    best = min(rows, key=lambda row: float(row["benchmark"]["median_seconds"]))
    return {
        "accepted": True,
        "classification": "bounded-diagnostic-not-production-evidence",
        "kind": "sparkinterval.goldbach-shifted-coverage-benchmark.v1",
        "input_source_sha256": sha256(source_file),
        "word_owner_cutoff": inspected.cutoff,
        "warp_parallel_cutoff": warp_limit,
        "cofactor_filter_limit": cofactor_filter_limit,
        "candidates": rows,
        "best_observed_kind": best["kind"],
        "best_observed_median_seconds": best["benchmark"]["median_seconds"],
        "production_identity_changed": False,
        "retained_combined_path": (
            str(retain_combined.resolve())
            if retain_combined is not None
            else None
        ),
        "retained_crosscheck_path": (
            str(retain_crosscheck.resolve())
            if retain_crosscheck is not None
            else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--warp-limit", type=int, default=32_749)
    parser.add_argument("--cofactor-filter-limit", type=int, default=47)
    parser.add_argument("--nvcc", type=Path, default=Path("/usr/local/cuda/bin/nvcc"))
    parser.add_argument("--host-cxx", type=Path, default=Path("/usr/bin/g++"))
    parser.add_argument("--arch", default="native")
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument(
        "--retain-combined",
        type=Path,
        help="copy the combined diagnostic source tree and binary here",
    )
    parser.add_argument(
        "--retain-crosscheck",
        type=Path,
        help="copy the full-bit crosscheck source tree and binary here",
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    try:
        report = benchmark(
            arguments.source_root,
            warp_limit=arguments.warp_limit,
            cofactor_filter_limit=arguments.cofactor_filter_limit,
            nvcc=arguments.nvcc,
            host_cxx=arguments.host_cxx,
            arch=arguments.arch,
            warmups=arguments.warmups,
            repetitions=arguments.repetitions,
            timeout=arguments.timeout,
            retain_combined=arguments.retain_combined,
            retain_crosscheck=arguments.retain_crosscheck,
        )
        encoded = (
            json.dumps(report, indent=2, sort_keys=True).encode() + b"\n"
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
