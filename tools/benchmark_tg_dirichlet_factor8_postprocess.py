#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Benchmark the fused factor-eight CUDA reducer against its four-corner form."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier import dirichlet_factor8_postprocess as factor8  # noqa: E402


def _periodic_input(coefficient_raw: bytes, base_count: int) -> bytes:
    period = 4096
    rows = bytearray()
    for index in range(period):
        center = math.sin(index * 0.071) + 0.2 * math.cos(index * 0.017)
        rows.extend(
            factor8.INTERVAL.pack(
                math.nextafter(center - 1e-12, -math.inf),
                math.nextafter(center + 1e-12, math.inf),
            )
        )
    period_raw = bytes(rows)
    payload = (
        period_raw * (base_count // period)
        + period_raw[: (base_count % period) * factor8.INTERVAL.size]
    )
    output_count = (base_count - 40) * factor8.UPSAMPLE_FACTOR
    header = factor8.INPUT_HEADER.pack(
        factor8.INPUT_MAGIC,
        factor8.FORMAT_VERSION,
        10001,
        3,
        1,
        0,
        base_count,
        20 * factor8.UPSAMPLE_FACTOR,
        output_count,
        math.nextafter(8.6e-8, math.inf),
        hashlib.sha256(coefficient_raw).digest(),
        bytes.fromhex("ab" * 32),
        hashlib.sha256(payload).digest(),
    )
    raw = header + payload
    factor8.read_input_artifact(raw)
    return raw


def _run(
    runner: Path,
    coefficients: Path,
    input_path: Path,
    output: Path,
    repeats: int,
    *,
    four_corner: bool,
) -> dict[str, object]:
    command = [
        str(runner),
        str(coefficients),
        str(input_path),
        str(output),
        str(repeats),
    ]
    if four_corner:
        command.append("--four-corner")
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runner", type=Path)
    parser.add_argument("--base-count", type=int, default=1 << 20)
    parser.add_argument("--repeats", type=int, default=100)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        if (
            args.base_count < 128
            or args.base_count > factor8.MAX_ITEMS
            or args.repeats < 1
            or args.repeats > 10_000
            or args.trials < 1
            or args.trials > 20
        ):
            raise factor8.Factor8PostprocessError("benchmark bounds differ")
        coefficient_raw = factor8.generate_coefficient_artifact()
        input_raw = _periodic_input(coefficient_raw, args.base_count)
        optimized_rates: list[float] = []
        reference_rates: list[float] = []
        pair_speedups: list[float] = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            coefficient_path = root / "coefficients.bin"
            input_path = root / "input.bin"
            optimized_path = root / "optimized.bin"
            reference_path = root / "four-corner.bin"
            coefficient_path.write_bytes(coefficient_raw)
            input_path.write_bytes(input_raw)
            for _ in range(args.trials):
                reference = _run(
                    args.runner,
                    coefficient_path,
                    input_path,
                    reference_path,
                    args.repeats,
                    four_corner=True,
                )
                optimized = _run(
                    args.runner,
                    coefficient_path,
                    input_path,
                    optimized_path,
                    args.repeats,
                    four_corner=False,
                )
                if reference_path.read_bytes() != optimized_path.read_bytes():
                    raise factor8.Factor8PostprocessError(
                        "optimized and four-corner artifacts differ"
                    )
                reference_rate = float(reference["target_samples_per_second"])
                optimized_rate = float(optimized["target_samples_per_second"])
                reference_rates.append(reference_rate)
                optimized_rates.append(optimized_rate)
                pair_speedups.append(optimized_rate / reference_rate)

            # A small independently replayable shard verifies more than device
            # differential equality: strict codes are checked from exact
            # rational endpoint products.
            small_intervals = [
                (
                    math.nextafter(math.sin(index * 0.071) - 1e-12, -math.inf),
                    math.nextafter(math.sin(index * 0.071) + 1e-12, math.inf),
                )
                for index in range(128)
            ]
            small_raw = factor8.make_input_artifact(
                q=10001,
                conrey_number=3,
                parity=1,
                first_base_index=0,
                intervals=small_intervals,
                first_fine_index=20 * 8,
                output_count=(128 - 40) * 8,
                interpolation_error_upper=math.nextafter(8.6e-8, math.inf),
                coefficient_artifact_sha256=hashlib.sha256(
                    coefficient_raw
                ).digest(),
                upstream_sha256=b"\xab" * 32,
            )
            small_input = root / "small.bin"
            small_output = root / "small-output.bin"
            small_input.write_bytes(small_raw)
            _run(
                args.runner,
                coefficient_path,
                small_input,
                small_output,
                1,
                four_corner=False,
            )
            independent = factor8.verify_output_artifact(
                coefficient_path, small_input, small_output
            )

        median_rate = statistics.median(optimized_rates)
        source_gpu_hours = (
            factor8.FACTOR8_TARGET_SAMPLES / median_rate / 3600
        )
        report = {
            "algorithm_id": factor8.ALGORITHM_ID,
            "base_completed_intervals_per_trial": args.base_count,
            "classification": (
                "synthetic_gb10_kernel_benchmark_not_h100_or_source_execution"
            ),
            "exact_work_audit": factor8.work_audit(),
            "four_corner_target_rates_per_second": reference_rates,
            "independent_exact_rational_kat": independent,
            "median_four_corner_target_samples_per_second": statistics.median(
                reference_rates
            ),
            "median_optimized_target_samples_per_second": median_rate,
            "median_paired_signed_coefficient_speedup": statistics.median(
                pair_speedups
            ),
            "optimized_target_rates_per_second": optimized_rates,
            "output_artifacts_byte_identical_every_trial": True,
            "pair_speedups": pair_speedups,
            "physical_cuda_refinement_proved": False,
            "projected_ideal_eight_equal_gb10_wall_hours": source_gpu_hours / 8,
            "projected_single_equal_gb10_gpu_hours": source_gpu_hours,
            "source_projection_excludes": [
                "upstream completed-L construction",
                "input generation and transfer",
                "boundary padding and exceptions",
                "uniform interpolation-error proof",
                "zero multiplicity and Turing closure",
                "attestation and independent source replay",
            ],
            "trials": args.trials,
        }
        print(json.dumps(report, sort_keys=True, indent=2 if args.pretty else None))
        return 0
    except (
        factor8.Factor8PostprocessError,
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as error:
        print(
            f"benchmark_tg_dirichlet_factor8_postprocess: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
