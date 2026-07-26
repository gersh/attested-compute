#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build and fail-closed qualify the Goldbach wheel-gap tail experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "gpu/platform/h100/"
    "h100_tg_goldbach_wheel_gap_tail_qualification.cu"
)
INCLUDE = ROOT / "gpu/include"
CURRENT_WHEEL_TRANSFORM = (
    ROOT / "tg_verifier/goldbach_wheel_filtered_tail_optimizer.py"
)
OPTIMIZED_SOURCE_MODULE = (
    ROOT / "tg_verifier/goldbach_optimized_source.py"
)
KIND = "sparkinterval.goldbach-wheel-gap-tail-qualification.v1"
REPORT_KIND = (
    "sparkinterval.goldbach-wheel-gap-tail-qualification-report.v1"
)
EXPECTED_SOURCE_SHA256 = (
    "87ddcf9219e8965aa9626c0f6dc42ce9f01a5dc33f119b25725a9ec9ac855152"
)
EXPECTED_CURRENT_WHEEL_TRANSFORM_SHA256 = (
    "b55f048db020430698f4c03b1d82c1f4e02a647e70ca44a20cf84ed2d8c914df"
)
EXPECTED_OPTIMIZED_SOURCE_MODULE_SHA256 = (
    "78883b3d18c6b7cac080ee97e430bd464793b832e53637fa4a459e2c1dad2914"
)
EXPECTED_OPTIMIZED_SOURCE_IDENTITY_SHA256 = (
    "8c19bf2825ff8a34ef9413f35620487f2062868f723b158228a071a5cf021359"
)
EXPECTED_CURRENT_GOLDBACH_SOURCE_SHA256 = (
    "2e4eedcf9d301c454c3e0174cccbe0f7a7a11350475ec8d681515d2a7ded333c"
)
EXPECTED_WHEEL_TABLE_SHA256 = (
    "8ce0f65ef7925ef7a01e56205d17ee8ce37989d7344f3f10aff0b43f23c8d9ae"
)
EXPECTED_CASES = {
    "low-inactive": {
        "counts": (0, 0, 0),
        "odd_count": 131_072,
        "output_sha256": (
            "9bbe647ca0591677b39c06a10f217194f076019f7e6aec1bd3e"
            "c8161443b6030"
        ),
        "q_high": "4262143",
        "q_low": "4000001",
        "set_bits": 17_240,
    },
    "prime-square-activation": {
        "counts": (2, 1, 1),
        "odd_count": 131_072,
        "output_sha256": (
            "c500d8de987c489e2c8de5ce5b1e2a1edc4a53b8f8bb06b42"
            "edf38ad2053eedd"
        ),
        "q_high": "1074069511",
        "q_low": "1073807369",
        "set_bits": 19_477,
    },
    "source-height": {
        "counts": (47_718, 18_279, 13_217),
        "odd_count": 262_144,
        "output_sha256": (
            "6d3d36b22ecec1fc80d897cd7a0c9f03e3d97eb15f5f11b74e"
            "9221c9602fe0bc"
        ),
        "q_high": "31249998799524289",
        "q_low": "31249998799000003",
        "set_bits": 32_093,
    },
    "non-word-aligned-end": {
        "counts": (47_719, 18_280, 13_217),
        "odd_count": 262_147,
        "output_sha256": (
            "a3764db98d0f1c637bcfb1e8daad50360e1adebbdebe7a770da"
            "63ef976ef0b14"
        ),
        "q_high": "31249998799524295",
        "q_low": "31249998799000003",
        "set_bits": 32_093,
    },
    "uint64-overflow-edge": {
        "counts": (47_701, 18_355, 13_408),
        "odd_count": 262_144,
        "output_sha256": (
            "31fe43fc8c5f80b08a2fcf2292380f2bd7a2406a09a75f112d"
            "2df00524f53d23"
        ),
        "q_high": "18446744073709551615",
        "q_low": "18446744073709027329",
        "set_bits": 32_051,
    },
}
EXPECTED_BENCHMARKS = {
    "bounded": {
        "counts": (349_114, 133_841, 97_023),
        "output_sha256": (
            "47e1e4ecfb918f21e9411f32d8904573935c64bca9e720aa2b"
            "50e052c1de6076"
        ),
        "prime_limit": 2_000_003,
        "rounds": 7,
        "tail_prime_count": 145_422,
        "total_odd_count": 1_048_576,
        "window_count": 1,
    },
    "source-segment": {
        "counts": (120_704_837, 46_303_329, 33_478_814),
        "output_sha256": (
            "211dc4345fa32379b434e5e3036ea48cb534a17da285865c758"
            "b4732886fafe7"
        ),
        "prime_limit": 176_776_695,
        "rounds": 9,
        "tail_prime_count": 9_856_924,
        "total_odd_count": 200_500_000,
        "window_count": 1,
    },
    "terminal-600m": {
        "counts": (362_115_104, 138_910_143, 100_446_929),
        "output_sha256": (
            "6424c3b4aaba11b1dc7a6bc534f81bc676f749b61c2893a62b"
            "353ea385910567"
        ),
        "prime_limit": 176_776_695,
        "rounds": 9,
        "tail_prime_count": 9_856_924,
        "total_odd_count": 601_500_000,
        "window_count": 3,
    },
}


class QualificationError(RuntimeError):
    """The wheel-gap qualification contract failed."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def make_wheel_table() -> bytes:
    table = bytearray()
    small_primes = (3, 5, 7, 11, 13)
    for index in range(15_015):
        residue = 2 * index + 1
        survives = all(residue % prime for prime in small_primes)
        gap = 2
        while not all(
            (residue + gap) % prime for prime in small_primes
        ):
            gap += 2
        if gap > 31:
            raise QualificationError("wheel gap does not fit encoding")
        table.append((0x80 if survives else 0) | gap)
    return bytes(table)


def _exact_keys(value: object, keys: set[str], what: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise QualificationError(f"{what} has wrong fields")
    return value


def _integer(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise QualificationError(f"{what} must be a nonnegative integer")
    return value


def _validate_counts(
    value: object, expected: tuple[int, int, int], what: str
) -> dict[str, object]:
    row = _exact_keys(
        value,
        {
            "final_event_count",
            "raw_visit_count",
            "small_wheel_survivor_count",
        },
        what,
    )
    actual = (
        _integer(row["raw_visit_count"], f"{what}.raw"),
        _integer(row["small_wheel_survivor_count"], f"{what}.small"),
        _integer(row["final_event_count"], f"{what}.final"),
    )
    if actual != expected or not actual[2] <= actual[1] <= actual[0]:
        raise QualificationError(f"{what} event counts differ")
    return row


def _validate_case(value: object, name: str) -> dict[str, object]:
    row = _exact_keys(
        value,
        {
            "counts",
            "name",
            "odd_count",
            "output_sha256",
            "q_high",
            "q_low",
            "set_bits",
        },
        f"case {name}",
    )
    if row["name"] != name:
        raise QualificationError("bounded cases are not in canonical order")
    expected = EXPECTED_CASES[name]
    _validate_counts(row["counts"], expected["counts"], f"case {name}")
    for key in (
        "odd_count",
        "output_sha256",
        "q_high",
        "q_low",
        "set_bits",
    ):
        if row[key] != expected[key]:
            raise QualificationError(f"case {name}.{key} differs")
    return row


def _timing_array(value: object, rounds: int, what: str) -> list[float]:
    if not isinstance(value, list) or len(value) != rounds:
        raise QualificationError(f"{what} has wrong length")
    result: list[float] = []
    for entry in value:
        if (
            isinstance(entry, bool)
            or not isinstance(entry, (int, float))
            or not 0.0 < float(entry) < 60_000.0
        ):
            raise QualificationError(f"{what} has an invalid entry")
        result.append(float(entry))
    return result


def _validate_benchmark(
    value: object, mode: str
) -> dict[str, object]:
    row = _exact_keys(
        value,
        {
            "counts",
            "current_over_gap_rate_ratio",
            "current_over_gap_remainders_rate_ratio",
            "geometry",
            "output_sha256",
            "prime_limit",
            "rounds",
            "tail_prime_count",
            "timings",
            "total_odd_count",
            "window_count",
        },
        "benchmark",
    )
    if row["geometry"] != mode:
        raise QualificationError("benchmark mode differs")
    expected = EXPECTED_BENCHMARKS[mode]
    _validate_counts(row["counts"], expected["counts"], "benchmark")
    for key in (
        "output_sha256",
        "prime_limit",
        "rounds",
        "tail_prime_count",
        "total_odd_count",
        "window_count",
    ):
        if row[key] != expected[key]:
            raise QualificationError(f"benchmark.{key} differs")
    timings = _exact_keys(
        row["timings"],
        {
            "current_wheel47_median_ms",
            "current_wheel47_ms",
            "ordinary_raw_median_ms",
            "ordinary_raw_ms",
            "wheel_gap_median_ms",
            "wheel_gap_ms",
            "wheel_gap_remainders_median_ms",
            "wheel_gap_remainders_ms",
        },
        "benchmark.timings",
    )
    rounds = int(row["rounds"])
    names = (
        "ordinary_raw",
        "current_wheel47",
        "wheel_gap",
        "wheel_gap_remainders",
    )
    medians: dict[str, float] = {}
    for name in names:
        values = _timing_array(
            timings[f"{name}_ms"], rounds, f"benchmark.{name}_ms"
        )
        median = float(timings[f"{name}_median_ms"])
        if abs(median - sorted(values)[rounds // 2]) > 1e-5:
            raise QualificationError(f"benchmark.{name} median differs")
        medians[name] = median
    ratio = float(row["current_over_gap_rate_ratio"])
    remainder_ratio = float(
        row["current_over_gap_remainders_rate_ratio"]
    )
    if (
        abs(
            ratio
            - medians["current_wheel47"] / medians["wheel_gap"]
        )
        > 1e-6
        or abs(
            remainder_ratio
            - medians["current_wheel47"]
            / medians["wheel_gap_remainders"]
        )
        > 1e-6
    ):
        raise QualificationError("benchmark rate accounting differs")
    return row


def _validate_resources(value: object, what: str) -> dict[str, object]:
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
    for key, entry in row.items():
        _integer(entry, f"{what}.{key}")
    if (
        row["local_bytes_per_thread"] != 0
        or row["max_threads_per_block"] < 256
        or not 0 < row["registers_per_thread"] <= 64
        or row["static_constant_bytes"] != 0
        or row["static_shared_bytes"] != 0
    ):
        raise QualificationError(f"{what} fails resource admission")
    return row


def validate_result(
    value: object, *, mode: str
) -> dict[str, object]:
    row = _exact_keys(
        value,
        {
            "accepted",
            "benchmark",
            "bounded_case_count",
            "bounded_cases",
            "compute_capability",
            "current_wheel47_resources",
            "kind",
            "lean_bridge_complete",
            "ordinary_raw_resources",
            "performance_evidence_eligible",
            "production_identity_promoted",
            "production_ready",
            "release_build_profile_eligible",
            "resource_gate_passed",
            "runtime_instrumentation_status",
            "wheel_gap_remainder_resources",
            "wheel_gap_resources",
            "wheel_table",
            "word_owner_cutoff",
            "warp_parallel_cutoff",
        },
        "qualification result",
    )
    fixed = {
        "accepted": True,
        "bounded_case_count": 5,
        "kind": KIND,
        "lean_bridge_complete": False,
        "performance_evidence_eligible": False,
        "production_identity_promoted": False,
        "production_ready": False,
        "release_build_profile_eligible": True,
        "resource_gate_passed": True,
        "runtime_instrumentation_status": "not-inspected-by-runner",
        "word_owner_cutoff": 2_039,
        "warp_parallel_cutoff": 32_749,
    }
    for key, expected in fixed.items():
        if row[key] != expected:
            raise QualificationError(f"qualification.{key} differs")
    if not isinstance(row["compute_capability"], str) or not re.fullmatch(
        r"[0-9]{1,2}\.[0-9]", row["compute_capability"]
    ):
        raise QualificationError("compute capability is malformed")
    table = _exact_keys(
        row["wheel_table"],
        {
            "encoded_entry_count",
            "maximum_even_gap",
            "modulus",
            "sha256",
            "surviving_residue_count",
        },
        "wheel table",
    )
    expected_table = {
        "encoded_entry_count": 15_015,
        "maximum_even_gap": 22,
        "modulus": 30_030,
        "sha256": EXPECTED_WHEEL_TABLE_SHA256,
        "surviving_residue_count": 5_760,
    }
    if table != expected_table:
        raise QualificationError("wheel table contract differs")
    cases = row["bounded_cases"]
    if not isinstance(cases, list) or len(cases) != len(EXPECTED_CASES):
        raise QualificationError("bounded case roster differs")
    for case, name in zip(cases, EXPECTED_CASES, strict=True):
        _validate_case(case, name)
    _validate_benchmark(row["benchmark"], mode)
    for field in (
        "ordinary_raw_resources",
        "current_wheel47_resources",
        "wheel_gap_resources",
        "wheel_gap_remainder_resources",
    ):
        _validate_resources(row[field], field)
    return row


def audit_sm90(
    *, nvcc: Path, cuobjdump: Path, temporary: Path, timeout: int
) -> dict[str, object]:
    executable = temporary / "wheel-gap-sm90"
    build_argv = [
        str(nvcc),
        "-O3",
        "-std=c++20",
        "-arch=sm_90",
        "-lineinfo",
        "-Xptxas=-v",
        "-DSPARKINTERVAL_ENABLE_GOLDBACH_WHEEL_GAP_QUALIFICATION=1",
        "-I",
        str(INCLUDE),
        str(SOURCE),
        "-o",
        str(executable),
    ]
    built = subprocess.run(
        build_argv,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if built.returncode != 0:
        raise QualificationError(
            "strict SM90 compilation failed: "
            + (built.stderr.strip() or built.stdout.strip())
        )
    elf = subprocess.run(
        [str(cuobjdump), "-lelf", str(executable)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if elf.returncode != 0:
        raise QualificationError("cuobjdump -lelf failed")
    elf_lines = [
        line.strip() for line in elf.stdout.splitlines() if line.strip()
    ]
    if (
        len(elf_lines) != 2
        or any(".sm_90.cubin" not in line for line in elf_lines)
        or any(
            re.search(r"\.sm_(?!90)", line) is not None
            for line in elf_lines
        )
    ):
        raise QualificationError("strict artifact is not SM90-only")
    sass_result = subprocess.run(
        [str(cuobjdump), "-sass", str(executable)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if sass_result.returncode != 0:
        raise QualificationError("cuobjdump -sass failed")
    sass = sass_result.stdout
    functions = re.findall(r"Function : (\S+)", sass)
    if (
        len(functions) != 8
        or sum("ordinary_raw_tail_kernel" in item for item in functions)
        != 2
        or sum("current_wheel47_tail_kernel" in item for item in functions)
        != 2
        or sum(
            "wheel_gap_tail_kernel" in item
            and "remainder" not in item
            for item in functions
        )
        != 2
        or sum(
            "wheel_gap_remainder_tail_kernel" in item
            for item in functions
        )
        != 2
        or sass.count("REDG.E.AND.64.STRONG.GPU") != 8
        or sass.count("REDG.E.ADD.64.STRONG.GPU") != 10
        or sass.count("LDG.E.U8.CONSTANT") != 12
        or "REDG.E.AND.32" in sass
        or "ATOM." in sass
        or re.search(r"\b(?:LDL|STL)\.", sass) is not None
    ):
        raise QualificationError("strict SM90 SASS audit differs")
    ptxas = built.stderr
    entries = re.findall(
        r"Compiling entry function '([^']+)'.*?"
        r"Function properties for \1\s*\n"
        r"\s*(\d+) bytes stack frame, (\d+) bytes spill stores, "
        r"(\d+) bytes spill loads\s*\n"
        r"\s*ptxas info\s*: Used (\d+) registers, used (\d+) barriers",
        ptxas,
        flags=re.DOTALL,
    )
    if len(entries) != 8:
        raise QualificationError("strict SM90 ptxas kernel roster differs")
    resources = []
    for name, stack, stores, loads, registers, barriers in entries:
        parsed = {
            "barriers": int(barriers),
            "kernel": name,
            "registers": int(registers),
            "spill_load_bytes": int(loads),
            "spill_store_bytes": int(stores),
            "stack_bytes": int(stack),
        }
        if (
            parsed["stack_bytes"] != 0
            or parsed["spill_store_bytes"] != 0
            or parsed["spill_load_bytes"] != 0
            or parsed["barriers"] != 0
            or not 0 < parsed["registers"] <= 64
        ):
            raise QualificationError("strict SM90 resource gate failed")
        resources.append(parsed)
    sass_path = temporary / "wheel-gap-sm90.sass"
    sass_path.write_text(sass, encoding="utf-8")
    return {
        "accepted": True,
        "build_argv": build_argv,
        "cubin_arches": ["sm_90", "sm_90"],
        "executable_sha256": sha256(executable),
        "kernel_resources": resources,
        "sass_global_atomic_add64_count": 10,
        "sass_global_atomic_and64_count": 8,
        "sass_kernel_count": 8,
        "sass_readonly_u8_load_count": 12,
        "sass_sha256": sha256(sass_path),
        "stack_or_spill_present": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
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
        choices=tuple(EXPECTED_BENCHMARKS),
        default="bounded",
    )
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    try:
        for path in (
            SOURCE,
            INCLUDE,
            CURRENT_WHEEL_TRANSFORM,
            OPTIMIZED_SOURCE_MODULE,
            arguments.nvcc,
            arguments.cuobjdump,
        ):
            if not path.exists():
                raise QualificationError(f"required path is absent: {path}")
        if sha256(SOURCE) != EXPECTED_SOURCE_SHA256:
            raise QualificationError("qualification source pin differs")
        if (
            sha256(CURRENT_WHEEL_TRANSFORM)
            != EXPECTED_CURRENT_WHEEL_TRANSFORM_SHA256
        ):
            raise QualificationError("current wheel-47 transform pin differs")
        if (
            sha256(OPTIMIZED_SOURCE_MODULE)
            != EXPECTED_OPTIMIZED_SOURCE_MODULE_SHA256
        ):
            raise QualificationError("optimized source module pin differs")
        table = make_wheel_table()
        if (
            len(table) != 15_015
            or sum(bool(entry & 0x80) for entry in table) != 5_760
            or max(entry & 0x1F for entry in table) != 22
            or hashlib.sha256(table).hexdigest()
            != EXPECTED_WHEEL_TABLE_SHA256
        ):
            raise QualificationError("independent wheel table differs")
        with tempfile.TemporaryDirectory(
            prefix="tg-goldbach-wheel-gap-"
        ) as temporary_name:
            temporary = Path(temporary_name)
            executable = temporary / "wheel-gap-native"
            build_argv = [
                str(arguments.nvcc),
                "-O3",
                "-std=c++20",
                "-arch=native",
                "-lineinfo",
                (
                    "-DSPARKINTERVAL_ENABLE_GOLDBACH_"
                    "WHEEL_GAP_QUALIFICATION=1"
                ),
                "-I",
                str(INCLUDE),
                str(SOURCE),
                "-o",
                str(executable),
            ]
            built = subprocess.run(
                build_argv,
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=arguments.timeout,
                check=False,
            )
            if built.returncode != 0:
                raise QualificationError(
                    "native qualification compilation failed: "
                    + (built.stderr.strip() or built.stdout.strip())
                )
            run_argv = [str(executable)]
            if arguments.mode != "bounded":
                run_argv.append("--" + arguments.mode)
            ran = subprocess.run(
                run_argv,
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=arguments.timeout,
                check=False,
            )
            if ran.returncode != 0:
                raise QualificationError(
                    "native qualification failed: "
                    + (ran.stderr.strip() or ran.stdout.strip())
                )
            try:
                result = validate_result(
                    json.loads(ran.stdout), mode=arguments.mode
                )
            except json.JSONDecodeError as error:
                raise QualificationError(
                    "qualification stdout is not one JSON value"
                ) from error
            strict_sm90 = audit_sm90(
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
                "current_goldbach_source_sha256": (
                    EXPECTED_CURRENT_GOLDBACH_SOURCE_SHA256
                ),
                "current_wheel_transform_sha256": sha256(
                    CURRENT_WHEEL_TRANSFORM
                ),
                "executable_sha256": sha256(executable),
                "kind": REPORT_KIND,
                "nvcc_sha256": sha256(arguments.nvcc),
                "optimized_source_identity_sha256": (
                    EXPECTED_OPTIMIZED_SOURCE_IDENTITY_SHA256
                ),
                "result": result,
                "run_argv": run_argv,
                "source_sha256": sha256(SOURCE),
                "strict_sm90": strict_sm90,
                "wheel_table_sha256": hashlib.sha256(table).hexdigest(),
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
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
