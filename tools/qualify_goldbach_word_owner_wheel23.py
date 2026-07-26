#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed qualification for the Goldbach through-23 word-owner wheel.

This tool builds and runs the standalone differential harness.  It also
cross-compiles the same pinned source for sm_90 and rejects stack, spill,
resource, or architecture drift.  It does not modify, build, or select the
production Goldbach source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.goldbach_word_owner_optimizer import (
    inspect_word_owner_source,
)


SOURCE = (
    ROOT
    / "gpu/platform/h100/"
    "h100_tg_goldbach_word_owner_wheel23_qualification.cu"
)
INCLUDE = ROOT / "gpu/include"
KIND = "sparkinterval.goldbach-word-owner-wheel23-qualification.v1"
REPORT_KIND = (
    "sparkinterval.goldbach-word-owner-wheel23-qualification-report.v1"
)

EXPECTED_SOURCE_SHA256 = (
    "c7a43e1839ab46c31c7d1f7d22baa7359e7927df36e70a66fbd819405d0510ef"
)
EXPECTED_CURRENT_GOLDBACH_SOURCE_SHA256 = (
    "2e4eedcf9d301c454c3e0174cccbe0f7a7a11350475ec8d681515d2a7ded333c"
)
EXPECTED_TABLE_SHA256 = (
    "18dab40449926ec6b691b5052aaaf7f16528827bfcb8371eb78e4fcfa02b1faa"
)
EXPECTED_P2_SHA256 = (
    "1ea5fd5c3498ec7914892f90c15ec4c0081f3348e2c55a73121c488c94c3f0aa"
)
EXPECTED_CASES: tuple[dict[str, object], ...] = (
    {
        "name": "low-prime-restoration",
        "odd_count": 256,
        "output_sha256": (
            "98a48380edf9293dfc45e644ca7ebd6637edab6342e955de4d6ec2730571d35f"
        ),
        "padding_bits": 0,
        "q_low": "3",
        "full_word_q_high": "513",
        "set_bits": 96,
        "word_count": 4,
    },
    {
        "name": "wheel-period-carry",
        "odd_count": 256,
        "output_sha256": (
            "79543ba9e14f6856ae97e620f134a1bd43cba91c2df753428a78925b35586aba"
        ),
        "padding_bits": 0,
        "q_low": "223092807",
        "full_word_q_high": "223093317",
        "set_bits": 33,
        "word_count": 4,
    },
    {
        "name": "source-height",
        "odd_count": 262_147,
        "output_sha256": (
            "215cc8aebd0ea6f8424cc62ccae0944154150c8e4b2bbd04370a9709d85f6041"
        ),
        "padding_bits": 61,
        "q_low": "31249998799000003",
        "full_word_q_high": "31249998799524417",
        "set_bits": 38_444,
        "word_count": 4_097,
    },
    {
        "name": "uint64-max-edge",
        "odd_count": 262_144,
        "output_sha256": (
            "58c15a92591ed0ecc04b399e0b212e30b113691e60974013efdc5a74f6ff0073"
        ),
        "padding_bits": 0,
        "q_low": "18446744073709027329",
        "full_word_q_high": "18446744073709551615",
        "set_bits": 38_564,
        "word_count": 4_096,
    },
)
EXPECTED_TERMINAL = {
    "name": "historical-terminal-segment",
    "odd_count": 200_500_000,
    "output_sha256": (
        "2a643ef55c59f4d3eb4bc8884737a208233116178aff81e2ebd007478564dd24"
    ),
    "padding_bits": 32,
    "q_low": "31249999599000003",
    "full_word_q_high": "31250000000000065",
    "set_bits": 29_453_809,
    "word_count": 3_132_813,
}
EXPECTED_PHASE_REDUCTION = {
    "conditional_subtractions": 2,
    "launch_guard_passed": True,
    "maximum_phase_numerator": 312_046_402,
    "maximum_qualified_word_count": 3_132_813,
    "maximum_scaled_word_index": 200_499_968,
    "maximum_word_index": 3_132_812,
    "oversized_launch_rejected": True,
    "q_half_mod_hoisted": True,
    "three_moduli": 334_639_305,
    "uint32_max": 4_294_967_295,
    "word_index_modulus_elided": True,
}


class QualificationError(RuntimeError):
    """The qualification contract was not met."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _exact_keys(
    value: object, keys: set[str], what: str
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise QualificationError(f"{what} has wrong fields")
    return value


def _integer(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise QualificationError(f"{what} must be a nonnegative integer")
    return value


def _positive_float(value: object, what: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 < float(value) < 60_000.0
    ):
        raise QualificationError(f"{what} must be finite and positive")
    return float(value)


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=2e-6, abs_tol=2e-6)


def _validate_resources(
    value: object, what: str
) -> dict[str, object]:
    row = _exact_keys(
        value,
        {
            "local_bytes_per_thread",
            "max_threads_per_block",
            "registers_per_thread",
            "static_constant_bytes",
            "static_shared_bytes",
        },
        what,
    )
    for key in row:
        _integer(row[key], f"{what}.{key}")
    if (
        row["local_bytes_per_thread"] != 0
        or row["static_shared_bytes"] != 0
        or not 1 <= row["registers_per_thread"] <= 64
        or row["max_threads_per_block"] < 256
    ):
        raise QualificationError(f"{what} exceeds the resource gate")
    return row


def _validate_case(
    value: object, expected: dict[str, object], what: str
) -> dict[str, object]:
    row = _exact_keys(value, set(expected), what)
    if row != expected:
        raise QualificationError(f"{what} differs from its known answer")
    return row


def _validate_benchmark(
    value: object, mode: str
) -> dict[str, object]:
    row = _exact_keys(
        value,
        {
            "candidate_median_ms",
            "candidate_ms",
            "current_median_ms",
            "current_ms",
            "current_over_candidate_rate_ratio",
            "integrated_equivalent_even_count",
            "integrated_equivalent_odd_word_inputs",
            "integrated_equivalent_segment_count",
            "integrated_equivalent_measured",
            "integrated_current_initializer_ms",
            "integrated_candidate_initializer_plus_table_ms",
            "rounds",
        },
        "benchmark",
    )
    rounds = 101 if mode == "source-segment" else 9
    if row["rounds"] != rounds:
        raise QualificationError("benchmark round count differs")
    current = row["current_ms"]
    candidate = row["candidate_ms"]
    if (
        not isinstance(current, list)
        or not isinstance(candidate, list)
        or len(current) != rounds
        or len(candidate) != rounds
    ):
        raise QualificationError("benchmark timing arrays differ")
    current_values = [
        _positive_float(value, "benchmark.current_ms") for value in current
    ]
    candidate_values = [
        _positive_float(value, "benchmark.candidate_ms")
        for value in candidate
    ]
    current_median = _positive_float(
        row["current_median_ms"], "benchmark.current_median_ms"
    )
    candidate_median = _positive_float(
        row["candidate_median_ms"], "benchmark.candidate_median_ms"
    )
    ratio = _positive_float(
        row["current_over_candidate_rate_ratio"],
        "benchmark.current_over_candidate_rate_ratio",
    )
    if (
        not _close(current_median, statistics.median(current_values))
        or not _close(candidate_median, statistics.median(candidate_values))
        or not _close(ratio, current_median / candidate_median)
    ):
        raise QualificationError("benchmark summaries are inconsistent")
    if (
        row["integrated_equivalent_even_count"] != "20000000000"
        or row["integrated_equivalent_odd_word_inputs"]
        != "20050000000"
        or row["integrated_equivalent_segment_count"] != 100
    ):
        raise QualificationError("integrated-equivalent geometry differs")
    if mode == "bounded":
        if (
            row["integrated_equivalent_measured"] is not False
            or row["integrated_current_initializer_ms"] != 0
            or row["integrated_candidate_initializer_plus_table_ms"] != 0
        ):
            raise QualificationError("bounded run claimed integrated timing")
    else:
        if row["integrated_equivalent_measured"] is not True:
            raise QualificationError("source run omitted integrated timing")
        current_total = _positive_float(
            row["integrated_current_initializer_ms"],
            "benchmark.integrated_current_initializer_ms",
        )
        candidate_total = _positive_float(
            row["integrated_candidate_initializer_plus_table_ms"],
            "benchmark.integrated_candidate_initializer_plus_table_ms",
        )
        if not _close(current_total, sum(current_values[:100])):
            raise QualificationError("current integrated timing is inconsistent")
        # The candidate total also includes the separately reported table
        # initialization; validate_result checks that relation below.
        if candidate_total <= sum(candidate_values[:100]):
            raise QualificationError("candidate integrated timing omits table")
    return row


def validate_result(
    value: object, *, mode: str
) -> dict[str, object]:
    """Validate one harness result without trusting omitted/default fields."""

    if mode not in {"bounded", "source-segment"}:
        raise QualificationError("unknown qualification mode")
    row = _exact_keys(
        value,
        {
            "accepted",
            "algorithm_equivalence_scope",
            "all_word_equality",
            "benchmark",
            "bounded_cases",
            "build_profile",
            "candidate_resources",
            "candidate_selected_in_production",
            "classification",
            "compute_capability",
            "cuda_to_lean_refinement_proved",
            "current_resources",
            "h100_measured",
            "kind",
            "lean_bridge_complete",
            "mode",
            "performance_evidence_eligible",
            "phase_reduction",
            "prime_square_audit",
            "production_identity_changed",
            "production_ready",
            "release_build_profile_eligible",
            "receipt_emitted",
            "resource_gate_passed",
            "runtime_instrumentation_status",
            "source_pins",
            "strict_h100_target",
            "table_initializer_resources",
            "terminal_case",
            "theorem_claimed",
            "wheel_table",
            "word_owner_cutoff",
        },
        "qualification result",
    )
    exact = {
        "accepted": True,
        "algorithm_equivalence_scope": (
            "cpu-vs-current-vs-phase-hoisted-wheel23-all-output-words"
        ),
        "all_word_equality": True,
        "candidate_selected_in_production": False,
        "classification": "qualification-only-unpromoted-candidate",
        "cuda_to_lean_refinement_proved": False,
        "h100_measured": False,
        "kind": KIND,
        "lean_bridge_complete": False,
        "mode": mode,
        "performance_evidence_eligible": False,
        "production_identity_changed": False,
        "production_ready": False,
        "release_build_profile_eligible": True,
        "receipt_emitted": False,
        "resource_gate_passed": True,
        "runtime_instrumentation_status": "not-inspected-by-runner",
        "strict_h100_target": False,
        "theorem_claimed": False,
        "word_owner_cutoff": 2_039,
    }
    for key, expected in exact.items():
        if row[key] != expected:
            raise QualificationError(f"{key} differs")
    if (
        not isinstance(row["compute_capability"], str)
        or re.fullmatch(r"[0-9]+\.[0-9]+", row["compute_capability"])
        is None
    ):
        raise QualificationError("compute capability is malformed")
    profile = _exact_keys(
        row["build_profile"],
        {"cmake_build_config", "ndebug_defined"},
        "build profile",
    )
    if (
        profile["cmake_build_config"] != "Release"
        or profile["ndebug_defined"] is not True
    ):
        raise QualificationError("qualification is not a Release build")
    benchmark = _validate_benchmark(row["benchmark"], mode)
    cases = row["bounded_cases"]
    if not isinstance(cases, list) or len(cases) != len(EXPECTED_CASES):
        raise QualificationError("bounded case list differs")
    for actual, expected in zip(cases, EXPECTED_CASES, strict=True):
        _validate_case(actual, expected, f"case {expected['name']}")
    phase = _exact_keys(
        row["phase_reduction"],
        set(EXPECTED_PHASE_REDUCTION),
        "phase reduction",
    )
    for key, expected in EXPECTED_PHASE_REDUCTION.items():
        if type(phase[key]) is not type(expected) or phase[key] != expected:
            raise QualificationError(f"phase_reduction.{key} differs")
    p2 = _exact_keys(
        row["prime_square_audit"],
        {"prime_count", "sha256"},
        "prime-square audit",
    )
    if p2 != {"prime_count": 308, "sha256": EXPECTED_P2_SHA256}:
        raise QualificationError("prime-square audit differs")
    pins = _exact_keys(
        row["source_pins"],
        {"current_goldbach_source_sha256"},
        "source pins",
    )
    if pins != {
        "current_goldbach_source_sha256": (
            EXPECTED_CURRENT_GOLDBACH_SOURCE_SHA256
        ),
    }:
        raise QualificationError("emitted source pins differ")
    table = _exact_keys(
        row["wheel_table"],
        {
            "carry_bits",
            "carry_mismatches",
            "device_bytes",
            "initialization_ms",
            "logical_bits",
            "mismatched_words",
            "odd_modulus",
            "padding_nonzero_bits",
            "sha256",
            "surviving_residues",
            "word_count",
        },
        "wheel table",
    )
    exact_table = {
        "carry_bits": 64,
        "carry_mismatches": 0,
        "device_bytes": 13_943_320,
        "logical_bits": 111_546_499,
        "mismatched_words": 0,
        "odd_modulus": 111_546_435,
        "padding_nonzero_bits": 0,
        "sha256": EXPECTED_TABLE_SHA256,
        "surviving_residues": 36_495_360,
        "word_count": 1_742_915,
    }
    for key, expected in exact_table.items():
        if table[key] != expected:
            raise QualificationError(f"wheel_table.{key} differs")
    table_ms = _positive_float(
        table["initialization_ms"], "wheel_table.initialization_ms"
    )
    if mode == "source-segment":
        candidate = [
            float(entry) for entry in benchmark["candidate_ms"]
        ]
        integrated = float(
            benchmark["integrated_candidate_initializer_plus_table_ms"]
        )
        if not _close(integrated, table_ms + sum(candidate[:100])):
            raise QualificationError(
                "candidate integrated timing/table relation differs"
            )
    expected_terminal: object = (
        EXPECTED_TERMINAL if mode == "source-segment" else None
    )
    if row["terminal_case"] != expected_terminal:
        raise QualificationError("terminal case differs")
    _validate_resources(row["table_initializer_resources"], "table resources")
    _validate_resources(row["current_resources"], "current resources")
    _validate_resources(row["candidate_resources"], "candidate resources")
    return row


def verify_current_source(path: Path) -> dict[str, object]:
    """Bind the external generated source and its exact prime prefix."""

    if not path.is_file() or path.is_symlink():
        raise QualificationError(
            "current Goldbach source must be a regular nonsymlink file"
        )
    digest = sha256(path)
    if digest != EXPECTED_CURRENT_GOLDBACH_SOURCE_SHA256:
        raise QualificationError("current Goldbach source pin differs")
    inspected = inspect_word_owner_source(path.read_text(encoding="utf-8"))
    if (
        inspected.cutoff != 2_039
        or len(inspected.primes) != 308
        or inspected.primes[:8] != (3, 5, 7, 11, 13, 17, 19, 23)
        or inspected.primes[8] != 29
        or inspected.primes[-1] != 2_039
    ):
        raise QualificationError("current word-owner roster differs")
    return {
        "cutoff": inspected.cutoff,
        "prime_count": len(inspected.primes),
        "sha256": digest,
    }


def _run_checked(
    argv: list[str], *, timeout: int, what: str
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        argv,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise QualificationError(f"{what} failed: {detail}")
    return completed


def audit_sm90(
    *, nvcc: Path, cuobjdump: Path, temporary: Path, timeout: int
) -> dict[str, object]:
    """Cross-compile and reject non-sm90, stack, spill, or resource drift."""

    executable = temporary / "wheel23-sm90"
    build_argv = [
        str(nvcc),
        "-O3",
        "-std=c++20",
        "-arch=sm_90",
        "-DNDEBUG",
        '-DSPARKINTERVAL_CMAKE_BUILD_CONFIG="Release"',
        (
            "-DSPARKINTERVAL_ENABLE_GOLDBACH_"
            "WORD_OWNER_WHEEL23_QUALIFICATION=1"
        ),
        "-DSPARKINTERVAL_REQUIRE_H100_SM90=1",
        "--fmad=false",
        "-lineinfo",
        "-Xptxas=-v",
        "-I",
        str(INCLUDE),
        str(SOURCE),
        "-o",
        str(executable),
    ]
    built = _run_checked(
        build_argv, timeout=timeout, what="strict sm_90 compilation"
    )
    ptxas = built.stderr
    kernel_suffixes = (
        "candidate_wheel23_word_owner_kernel",
        "initialize_word_owner_wheel23_kernel",
        "current_literal_word_owner_kernel",
    )
    for suffix in kernel_suffixes:
        if suffix not in ptxas:
            raise QualificationError(
                f"ptxas report omitted {suffix}"
            )
    if (
        ptxas.count("0 bytes stack frame") != 3
        or ptxas.count("0 bytes spill stores") != 3
        or ptxas.count("0 bytes spill loads") != 3
    ):
        raise QualificationError("strict sm_90 build has stack or spills")
    registers = [
        int(value)
        for value in re.findall(r"Used ([0-9]+) registers", ptxas)
    ]
    if len(registers) != 3 or any(
        value < 1 or value > 64 for value in registers
    ):
        raise QualificationError("strict sm_90 register use differs")
    listed = _run_checked(
        [str(cuobjdump), "--list-elf", str(executable)],
        timeout=timeout,
        what="strict sm_90 ELF inventory",
    ).stdout
    arches = re.findall(r"\.([a-z]+_[0-9]+)\.cubin", listed)
    if not arches or set(arches) != {"sm_90"}:
        raise QualificationError("strict binary contains non-sm90 SASS")
    sass = _run_checked(
        [str(cuobjdump), "--dump-sass", str(executable)],
        timeout=timeout,
        what="strict sm_90 SASS dump",
    ).stdout
    for suffix in kernel_suffixes:
        if suffix not in sass:
            raise QualificationError(f"SASS omitted {suffix}")
    sass_path = temporary / "wheel23-sm90.sass"
    sass_path.write_text(sass, encoding="utf-8")
    return {
        "build_argv": build_argv,
        "cubin_arches": arches,
        "executable_sha256": sha256(executable),
        "kernel_count": 3,
        "ptxas_registers": sorted(registers),
        "sass_sha256": sha256(sass_path),
        "stack_or_spill_present": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-source", type=Path, required=True)
    parser.add_argument(
        "--nvcc", type=Path, default=Path("/usr/local/cuda/bin/nvcc")
    )
    parser.add_argument(
        "--cuobjdump",
        type=Path,
        default=Path("/usr/local/cuda/bin/cuobjdump"),
    )
    parser.add_argument(
        "--mode",
        choices=("bounded", "source-segment"),
        default="bounded",
    )
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.timeout < 1:
            raise QualificationError("timeout must be positive")
        for path in (
            SOURCE,
            INCLUDE,
            arguments.nvcc,
            arguments.cuobjdump,
        ):
            if not path.exists():
                raise QualificationError(f"required path is absent: {path}")
        if sha256(SOURCE) != EXPECTED_SOURCE_SHA256:
            raise QualificationError("qualification source pin differs")
        current_source = verify_current_source(arguments.current_source)
        with tempfile.TemporaryDirectory(
            prefix="tg-goldbach-word-owner-wheel23-"
        ) as temporary_name:
            temporary = Path(temporary_name)
            executable = temporary / "wheel23-native"
            build_argv = [
                str(arguments.nvcc),
                "-O3",
                "-std=c++20",
                "-arch=native",
                "-DNDEBUG",
                '-DSPARKINTERVAL_CMAKE_BUILD_CONFIG="Release"',
                (
                    "-DSPARKINTERVAL_ENABLE_GOLDBACH_"
                    "WORD_OWNER_WHEEL23_QUALIFICATION=1"
                ),
                "--fmad=false",
                "-lineinfo",
                "-I",
                str(INCLUDE),
                str(SOURCE),
                "-o",
                str(executable),
            ]
            _run_checked(
                build_argv,
                timeout=arguments.timeout,
                what="native qualification compilation",
            )
            run_argv = [str(executable)]
            if arguments.mode == "source-segment":
                run_argv.append("--source-segment")
            ran = _run_checked(
                run_argv,
                timeout=arguments.timeout,
                what="native qualification",
            )
            try:
                result = validate_result(
                    json.loads(ran.stdout), mode=arguments.mode
                )
            except json.JSONDecodeError as error:
                raise QualificationError(
                    "qualification stdout is not one JSON value"
                ) from error
            strict = audit_sm90(
                nvcc=arguments.nvcc,
                cuobjdump=arguments.cuobjdump,
                temporary=temporary,
                timeout=arguments.timeout,
            )
            report = {
                "accepted": True,
                "build_argv": build_argv,
                "classification": (
                    "qualification-only-unpromoted-candidate"
                ),
                "current_source": current_source,
                "executable_sha256": sha256(executable),
                "kind": REPORT_KIND,
                "nvcc_sha256": sha256(arguments.nvcc),
                "production_identity_changed": False,
                "receipt_emitted": False,
                "result": result,
                "run_argv": run_argv,
                "source_sha256": sha256(SOURCE),
                "strict_sm90": strict,
                "theorem_claimed": False,
            }
        encoded = (
            json.dumps(report, indent=2, sort_keys=True) + "\n"
            if arguments.pretty
            else json.dumps(
                report, separators=(",", ":"), sort_keys=True
            )
            + "\n"
        )
        if arguments.out is not None:
            arguments.out.parent.mkdir(parents=True, exist_ok=True)
            arguments.out.write_text(encoded, encoding="utf-8")
        print(encoded, end="")
    except (
        QualificationError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        print(
            f"goldbach-word-owner-wheel23-qualification: {error}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
