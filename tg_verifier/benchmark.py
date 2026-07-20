# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Measured microbenchmarks and conservative full-campaign planning ranges."""

from __future__ import annotations

from fractions import Fraction
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import time
from typing import Any, Callable

from .arithmetic import (
    LittleMertensBound,
    check_hurst_sample,
    check_little_mertens_sample,
    check_squarefree_sample,
    mobius_linear,
)
from .catalog import ATOMS
from .finite_campaigns import (
    create_psi_certificate,
    fixed_log_bounds,
    verify_psi_chain,
)


H100_SXM_MEMORY_BANDWIDTH_BYTES_PER_SECOND = 3_350_000_000_000
GB10_SPEC_MEMORY_BANDWIDTH_BYTES_PER_SECOND = 273_000_000_000
NVIDIA_H100_SPEC_URL = "https://www.nvidia.com/en-us/data-center/h100/"
NVIDIA_GB10_SPEC_URL = (
    "https://www.nvidia.com/en-sg/products/workstations/dgx-spark/"
)


class BenchmarkError(RuntimeError):
    """A benchmark executable or report failed closed."""


def _measure(
    function: Callable[..., Any], *arguments: Any, **keywords: Any
) -> tuple[Any, float]:
    start = time.perf_counter()
    result = function(*arguments, **keywords)
    return result, time.perf_counter() - start


def run_gpu_integer_microbenchmark(
    executable: Path, *, count: int, repetitions: int
) -> dict[str, Any]:
    """Run the repository's exact-integer planning microbenchmark."""

    if count <= 0 or repetitions <= 0:
        raise ValueError("count and repetitions must be positive")
    try:
        completed = subprocess.run(
            [
                str(executable),
                "--count",
                str(count),
                "--repetitions",
                str(repetitions),
            ],
            check=False,
            text=True,
            capture_output=True,
        )
    except OSError as exc:
        raise BenchmarkError(f"cannot run GPU benchmark: {exc}") from exc
    if completed.returncode != 0:
        raise BenchmarkError(
            f"GPU benchmark exited {completed.returncode}: {completed.stderr.strip()}"
        )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise BenchmarkError("GPU benchmark did not return JSON") from exc
    if not isinstance(report, dict):
        raise BenchmarkError("GPU benchmark report is not an object")
    if report.get("benchmark") != "tg_integer_work_item_microbenchmark":
        raise BenchmarkError("unexpected GPU benchmark kind")
    if report.get("classification") != "planning_microbenchmark_not_verification":
        raise BenchmarkError("GPU benchmark scope classification changed")
    if report.get("endpoint_check") is not True:
        raise BenchmarkError("GPU benchmark endpoint cross-check failed")
    if report.get("proves_any_external_atom") is not False:
        raise BenchmarkError("GPU benchmark made an invalid proof claim")
    if report.get("count_per_repetition") != count:
        raise BenchmarkError("GPU benchmark report count differs from the request")
    if report.get("repetitions") != repetitions:
        raise BenchmarkError("GPU benchmark report repetitions differ from the request")
    device_name = report.get("device_name")
    capability = report.get("compute_capability")
    if not isinstance(device_name, str) or not device_name.strip():
        raise BenchmarkError("GPU benchmark report has no device identity")
    if not isinstance(capability, str) or re.fullmatch(r"[0-9]+\.[0-9]+", capability) is None:
        raise BenchmarkError("GPU benchmark report has invalid compute capability")
    for field in (
        "kernel_milliseconds",
        "work_items_per_second",
        "minimum_output_bytes_per_second",
    ):
        value = report.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise BenchmarkError(f"GPU benchmark report has invalid {field}")
    return report


def run_cpu_reference_benchmarks(
    *,
    mobius_limit: int,
    exact_fraction_limit: int,
    psi_limit: int | None = None,
) -> dict[str, Any]:
    """Measure bounded exact CPU reference routines, never full claims."""

    if mobius_limit < 33:
        raise ValueError("mobius_limit must be at least 33")
    if exact_fraction_limit < 3 or exact_fraction_limit > mobius_limit:
        raise ValueError("exact_fraction_limit must lie in [3, mobius_limit]")

    mu, sieve_seconds = _measure(mobius_linear, mobius_limit)
    hurst, hurst_seconds = _measure(check_hurst_sample, mu, 33, mobius_limit)
    little_mu = mu[: exact_fraction_limit + 1]
    little_211, little_211_seconds = _measure(
        check_little_mertens_sample,
        little_mu,
        1,
        exact_fraction_limit,
        LittleMertensBound.SQRT_TWO_OVER_X,
    )
    little_strong, little_strong_seconds = _measure(
        check_little_mertens_sample,
        little_mu,
        3,
        exact_fraction_limit,
        LittleMertensBound.ONE_OVER_TWO_SQRT_X,
    )
    report: dict[str, Any] = {
        "classification": "bounded_exact_cpu_reference_not_full_verification",
        "mobius": {
            "limit": mobius_limit,
            "elapsed_seconds": sieve_seconds,
            "indices_per_second": mobius_limit / sieve_seconds,
        },
        "hurst": {
            "limit": mobius_limit,
            "elapsed_seconds": hurst_seconds,
            "indices_per_second": hurst.checks / hurst_seconds,
            "sample_passed": hurst.passed,
        },
        "little_mertens_2_11": {
            "limit": exact_fraction_limit,
            "elapsed_seconds": little_211_seconds,
            "indices_per_second": little_211.slabs_checked / little_211_seconds,
            "sample_passed": little_211.passed,
        },
        "little_mertens_stronger": {
            "limit": exact_fraction_limit,
            "elapsed_seconds": little_strong_seconds,
            "indices_per_second": little_strong.slabs_checked
            / little_strong_seconds,
            "sample_passed": little_strong.passed,
        },
    }
    if exact_fraction_limit >= 9_243:
        squarefree, squarefree_seconds = _measure(
            check_squarefree_sample,
            little_mu,
            9_243,
            exact_fraction_limit,
            Fraction(151, 2_000),
        )
        report["squarefree_b1"] = {
            "range_start": 9_243,
            "range_end": exact_fraction_limit,
            "elapsed_seconds": squarefree_seconds,
            "endpoints_per_second": squarefree.endpoints_checked
            / squarefree_seconds,
            "sample_passed": squarefree.passed,
        }
    else:
        report["squarefree_b1"] = {
            "status": "not_run",
            "reason": "exact_fraction_limit is below the strict threshold 9243",
        }
    if psi_limit is not None:
        if psi_limit < 2:
            raise ValueError("psi_limit must be at least 2")
        chunks, produce_seconds = _measure(
            create_psi_certificate,
            psi_limit,
        )
        # An independent checker process does not inherit the producer's log
        # cache.  Clear it so this timing includes rational-log recomputation.
        fixed_log_bounds.cache_clear()
        psi, verify_seconds = _measure(
            verify_psi_chain,
            chunks,
            expected_limit=psi_limit,
        )
        report["psi_prime_power"] = {
            "limit": psi_limit,
            "events": psi.events,
            "produce_seconds": produce_seconds,
            "cold_verify_seconds": verify_seconds,
            "produce_events_per_second": psi.events / produce_seconds,
            "cold_verify_events_per_second": psi.events / verify_seconds,
            "sample_passed": (
                psi.exact_prime_power_coverage_verified
                and psi.rational_log_enclosures_verified
                and psi.exact_envelope_inequalities_verified
            ),
        }
    return report


def _range(
    status: str,
    basis: str,
    low_seconds: int | float | None = None,
    high_seconds: int | float | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"status": status, "basis": basis}
    if low_seconds is not None:
        result["seconds_low"] = low_seconds
    if high_seconds is not None:
        result["seconds_high"] = high_seconds
    return result


def full_campaign_estimates() -> list[dict[str, Any]]:
    """Return explicit planning ranges; unknown algorithms stay unestimated."""

    # These are deliberately broad engineering ranges.  They are not obtained
    # by multiplying the microbenchmark rate by the mathematical endpoint.
    estimates: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
        "ch25-a7-boundary": (
            _range(
                "retained_measurement",
                "SparkInterval full 16191-leaf FLINT/Arb replay on this GB10 host",
                1.56,
                1.56,
            ),
            _range("not_needed", "CPU replay is already 1.56 s; Lean semantics are the bottleneck"),
        ),
        "ch25-psi-1e13": (
            _range(
                "prohibitive_reference",
                "current exact Python rational-log producer plus cold replay; "
                "10^6 benchmark implies a multi-year source-range run",
                120_000_000,
                320_000_000,
            ),
            _range("not_estimated", "no matching H100 producer benchmark"),
        ),
        "platt-head-2e4": (
            _range(
                "retained_measurement",
                "FLINT isolation/count replay; LMFDB fold adds 0.35 s",
                123.79,
                124.14,
            ),
            _range("not_estimated", "no H100 Hardy-Z/Turing implementation"),
        ),
        "platt-trudgian-rh-3e12": (
            _range("blocked", "PT21 database and production zero verifier are absent"),
            _range("blocked", "offline sm_90 build is not a zero-verifier benchmark"),
        ),
        "helfgott-prop-12-2-4": (
            _range(
                "not_estimated",
                "exact scheduler and directed-rational row producer exist; the 3.39-billion-q campaign is unmeasured",
            ),
            _range("not_estimated", "no target-kernel measurement"),
        ),
        "cdem-squarefree": (
            _range("prohibitive_naive", "10^16 unit intervals; even 10^9/s is 116 days", 10_000_000, None),
            _range("prohibitive_naive", "even 10^10/s is 11.6 days before sieve/check overhead", 1_000_000, None),
        ),
        "cdem-table-abel": (
            _range(
                "retained_measurement",
                "reviewed-source 8-thread full producer on this server; the independent 1000-chunk replay was 45.85 s",
                86.8,
                86.8,
            ),
            _range("planning_range", "single H100; memory/reduction/I/O dominated", 30, 180),
        ),
        "mertens-hurst": (
            _range("prohibitive_naive", "10^16 prefixes; Hurst's faster artifacts are absent", 10_000_000, None),
            _range("prohibitive_naive", "requires Hurst-style compressed algorithm", 1_000_000, None),
        ),
        "ramare-zuniga-lemma-6-2": (
            _range(
                "retained_measurement",
                "runtime stored in the checked 21-billion NumPy/libm report; not the new exact reference",
                9173.397177397972,
                9173.397177397972,
            ),
            _range("planning_range", "one H100 exact segmented implementation", 300, 2700),
        ),
        "helfgott-platt-theorem-4-1": (
            _range("blocked", "deleted ladder corpus; historical campaign about 40000 core-hours"),
            _range("not_estimated", "trillion-rung producer and independent checker do not exist"),
        ),
        "platt-dirichlet-theorem-7-1": (
            _range("blocked", "character/zero database and algorithm are absent"),
            _range("blocked", "no completed-L/Turing target kernel"),
        ),
        "platt-little-mertens-2-11": (
            _range("planning_range", "exact segmented Mobius/fixed-point design", 3 * 86_400, 14 * 86_400),
            _range("planning_range", "one H100; requires target implementation", 12 * 3_600, 72 * 3_600),
        ),
        "platt-little-mertens-stronger": (
            _range("planning_range", "exact segmented Mobius/fixed-point design", 30 * 60, 3 * 3_600),
            _range("planning_range", "one H100; requires target implementation", 5 * 60, 30 * 60),
        ),
    }
    return [
        {
            "id": atom.atom_id,
            "server": estimates[atom.atom_id][0],
            "h100_sxm": estimates[atom.atom_id][1],
        }
        for atom in ATOMS
    ]


def build_benchmark_report(
    *,
    gpu_executable: Path | None,
    gpu_count: int,
    gpu_repetitions: int,
    mobius_limit: int,
    exact_fraction_limit: int,
    psi_limit: int | None = None,
) -> dict[str, Any]:
    cpu = run_cpu_reference_benchmarks(
        mobius_limit=mobius_limit,
        exact_fraction_limit=exact_fraction_limit,
        psi_limit=psi_limit,
    )
    gpu: dict[str, Any]
    if gpu_executable is None:
        gpu = {"status": "not_run", "reason": "no executable supplied"}
    else:
        gpu = run_gpu_integer_microbenchmark(
            gpu_executable, count=gpu_count, repetitions=gpu_repetitions
        )
    return {
        "schema_version": 1,
        "benchmark": "ternary_goldbach_external_atom_feasibility",
        "classification": "measured_samples_plus_explicit_planning_ranges",
        "host": {
            "machine": platform.machine(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "logical_cpu_count": os.cpu_count(),
        },
        "hardware_model": {
            "gb10_spec_memory_bandwidth_bytes_per_second": (
                GB10_SPEC_MEMORY_BANDWIDTH_BYTES_PER_SECOND
            ),
            "h100_sxm_spec_memory_bandwidth_bytes_per_second": (
                H100_SXM_MEMORY_BANDWIDTH_BYTES_PER_SECOND
            ),
            "spec_bandwidth_ratio_h100_over_gb10": (
                H100_SXM_MEMORY_BANDWIDTH_BYTES_PER_SECOND
                / GB10_SPEC_MEMORY_BANDWIDTH_BYTES_PER_SECOND
            ),
            "gb10_official_source": NVIDIA_GB10_SPEC_URL,
            "h100_official_source": NVIDIA_H100_SPEC_URL,
            "warning": (
                "Bandwidth ratio is a roofline input, not a runtime multiplier; "
                "integer division, sieving, divergence, host work, and I/O differ."
            ),
        },
        "cpu_reference": cpu,
        "gpu_microbenchmark": gpu,
        "full_campaign_estimates": full_campaign_estimates(),
        "nonclaims": [
            "A bounded sample does not verify an unsampled range.",
            "The GPU microbenchmark is not a sieve, zeta, or certificate checker.",
            "An H100 estimate is not an H100 measurement.",
            "No estimate closes a missing analytic semantic theorem.",
        ],
    }
