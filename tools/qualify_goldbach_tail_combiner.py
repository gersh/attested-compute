#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build, run, and fail-closed validate the Goldbach tail combiner.

The executable is qualification-only.  This runner is the sole repository
entry point that defines its opt-in macro; no production source identity or
default build target is changed.
"""

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
    "h100_tg_goldbach_tail_combiner_qualification.cu"
)
INCLUDE = ROOT / "gpu/include"
KIND = "sparkinterval.goldbach-tail-combiner-qualification.v1"
REPORT_KIND = (
    "sparkinterval.goldbach-tail-combiner-qualification-report.v1"
)
EXPECTED_CASES = {
    "prime-square-activation": {
        "cpu_event_count": 2,
        "output_sha256": (
            "c174dfb0cb9860fbcf93b4241fa0252f9a09e16c70d00677c"
            "bc89595f4a0a67e"
        ),
        "patterned_initial_words": False,
        "q_high": "1074200583",
        "q_low": "1073676297",
        "set_bits": 262_142,
        "table_slots": 512,
    },
    "source-height-normal": {
        "cpu_event_count": 13_217,
        "output_sha256": (
            "e20b6c10dc6120d6f472f0b867223c8e342c1b93a64837ed0e"
            "0ab9db37b92eb0"
        ),
        "patterned_initial_words": False,
        "q_high": "31249998799524289",
        "q_low": "31249998799000003",
        "set_bits": 250_053,
        "table_slots": 512,
    },
    "forced-collision": {
        "cpu_event_count": 13_217,
        "output_sha256": (
            "064ae7ae298ff1d13feede4ae154b41e9a66387508ce3d93102"
            "77835d13d6774"
        ),
        "patterned_initial_words": True,
        "q_high": "31249998799524289",
        "q_low": "31249998799000003",
        "set_bits": 246_143,
        "table_slots": 512,
    },
    "forced-full-table-fallback": {
        "cpu_event_count": 13_217,
        "output_sha256": (
            "064ae7ae298ff1d13feede4ae154b41e9a66387508ce3d93102"
            "77835d13d6774"
        ),
        "patterned_initial_words": True,
        "q_high": "31249998799524289",
        "q_low": "31249998799000003",
        "set_bits": 246_143,
        "table_slots": 8,
    },
    "uint64-overflow-edge": {
        "cpu_event_count": 13_408,
        "output_sha256": (
            "9015dd82bc4d04f3abee6f21ac8bcd60861b6a12d9ae83b1a7"
            "58b0ceb9869a39"
        ),
        "patterned_initial_words": False,
        "q_high": "18446744073709551615",
        "q_low": "18446744073709027329",
        "set_bits": 249_936,
        "table_slots": 512,
    },
}


class QualificationError(RuntimeError):
    """The exact tail-combiner qualification contract failed."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _exact_keys(value: object, keys: set[str], what: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise QualificationError(f"{what} has wrong fields")
    return value


def _nonnegative_int(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise QualificationError(f"{what} must be a nonnegative integer")
    return value


def _positive_finite_list(value: object, length: int, what: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise QualificationError(f"{what} has wrong length")
    result: list[float] = []
    for entry in value:
        if (
            isinstance(entry, bool)
            or not isinstance(entry, (int, float))
            or not 0.0 < float(entry) < 60_000.0
        ):
            raise QualificationError(f"{what} contains an invalid timing")
        result.append(float(entry))
    return result


def _validate_counters(
    value: object, cpu_event_count: int, what: str
) -> dict[str, object]:
    counters = _exact_keys(
        value,
        {
            "collision_probe_count",
            "combined_event_count",
            "eligible_event_count",
            "fallback_event_count",
            "flushed_entry_count",
        },
        what,
    )
    parsed = {
        key: _nonnegative_int(entry, f"{what}.{key}")
        for key, entry in counters.items()
    }
    if (
        parsed["eligible_event_count"] != cpu_event_count
        or parsed["combined_event_count"]
        + parsed["fallback_event_count"]
        != parsed["eligible_event_count"]
        or parsed["flushed_entry_count"]
        > parsed["combined_event_count"]
    ):
        raise QualificationError(f"{what} violates exact event partitioning")
    return counters


def _validate_case(value: object, expected_name: str) -> dict[str, object]:
    row = _exact_keys(
        value,
        {
            "counters",
            "cpu_event_count",
            "force_hash_collision",
            "name",
            "odd_count",
            "output_sha256",
            "patterned_initial_words",
            "q_high",
            "q_low",
            "set_bits",
            "table_slots",
        },
        f"case {expected_name}",
    )
    if row["name"] != expected_name:
        raise QualificationError("bounded cases are not in canonical order")
    expected = EXPECTED_CASES[expected_name]
    for key, wanted in expected.items():
        if row.get(key) != wanted:
            raise QualificationError(
                f"case {expected_name}.{key} differs from its known answer"
            )
    if row["odd_count"] != 1 << 18:
        raise QualificationError(f"case {expected_name} has wrong width")
    if row["force_hash_collision"] is not (
        expected_name in {"forced-collision", "forced-full-table-fallback"}
    ):
        raise QualificationError(
            f"case {expected_name} has wrong collision mode"
        )
    counters = _validate_counters(
        row["counters"], int(row["cpu_event_count"]), f"case {expected_name}"
    )
    if expected_name == "forced-collision":
        if (
            counters["collision_probe_count"] <= 0
            or counters["fallback_event_count"] != 0
        ):
            raise QualificationError(
                "forced-collision case did not isolate collision handling"
            )
    if expected_name == "forced-full-table-fallback":
        if (
            counters["collision_probe_count"] <= 0
            or counters["combined_event_count"] <= 0
            or counters["fallback_event_count"] <= 0
        ):
            raise QualificationError(
                "forced-full-table case did not exercise both routes"
            )
    return row


def _validate_resources(value: object, candidate: bool) -> dict[str, object]:
    row = _exact_keys(
        value,
        {
            "local_bytes_per_thread",
            "max_threads_per_block",
            "registers_per_thread",
            "static_shared_bytes",
        },
        "candidate resources" if candidate else "ordinary resources",
    )
    for key, entry in row.items():
        _nonnegative_int(entry, f"resources.{key}")
    if (
        row["local_bytes_per_thread"] != 0
        or row["max_threads_per_block"] < 256
        or not 0 < row["registers_per_thread"] <= 255
        or row["static_shared_bytes"] != (8192 if candidate else 0)
    ):
        raise QualificationError("compiler-resource admission gate differs")
    return row


def _validate_benchmark(
    value: object, source_segment: bool
) -> dict[str, object]:
    row = _exact_keys(
        value,
        {
            "candidate_ms",
            "candidate_median_ms",
            "cpu_event_count",
            "eliminated_global_atomic_count",
            "emitted_global_atomic_count",
            "geometry",
            "observed_ordinary_over_candidate_rate_ratio",
            "odd_count",
            "ordinary_ms",
            "ordinary_median_ms",
            "output_sha256",
            "prime_limit",
            "q_high",
            "q_low",
            "rounds",
            "routing_counters",
            "tail_prime_count",
        },
        "benchmark",
    )
    expected = (
        {
            "geometry": "one-historical-terminal-segment",
            "odd_count": 200_500_000,
            "output_sha256": (
                "38d96197eced197c443261c23f35fd2c37ede59e2add9d5c82"
                "e15d0d2e4e0428"
            ),
            "prime_limit": 176_776_695,
            "q_high": "31250000000000001",
            "q_low": "31249999599000003",
            "rounds": 9,
            "tail_prime_count": 9_856_924,
            "cpu_event_count": 33_478_814,
            "emitted_global_atomic_count": 33_423_230,
            "eliminated_global_atomic_count": 55_584,
        }
        if source_segment
        else {
            "geometry": "bounded-source-height-tail-subset",
            "odd_count": 4_194_304,
            "output_sha256": (
                "83d5a979e1591662006976e86368d62de674b874c32ec00b9db"
                "0ddbd3ae86f61"
            ),
            "prime_limit": 2_000_003,
            "q_high": "31249998807388609",
            "q_low": "31249998799000003",
            "rounds": 7,
            "tail_prime_count": 145_422,
            "cpu_event_count": 387_620,
            "emitted_global_atomic_count": 382_557,
            "eliminated_global_atomic_count": 5_063,
        }
    )
    for key, wanted in expected.items():
        if row[key] != wanted:
            raise QualificationError(f"benchmark.{key} differs")
    cpu_events = _nonnegative_int(
        row["cpu_event_count"], "benchmark.cpu_event_count"
    )
    counters = _validate_counters(
        row["routing_counters"], cpu_events, "benchmark routing"
    )
    emitted = _nonnegative_int(
        row["emitted_global_atomic_count"],
        "benchmark.emitted_global_atomic_count",
    )
    eliminated = _nonnegative_int(
        row["eliminated_global_atomic_count"],
        "benchmark.eliminated_global_atomic_count",
    )
    if (
        emitted
        != counters["flushed_entry_count"] + counters["fallback_event_count"]
        or eliminated != cpu_events - emitted
        or counters["fallback_event_count"] != 0
        or eliminated <= 0
    ):
        raise QualificationError("benchmark locality accounting differs")
    rounds = int(row["rounds"])
    ordinary = _positive_finite_list(
        row["ordinary_ms"], rounds, "benchmark.ordinary_ms"
    )
    candidate = _positive_finite_list(
        row["candidate_ms"], rounds, "benchmark.candidate_ms"
    )
    ordinary_median = float(row["ordinary_median_ms"])
    candidate_median = float(row["candidate_median_ms"])
    ratio = float(row["observed_ordinary_over_candidate_rate_ratio"])
    if (
        ordinary_median != sorted(ordinary)[rounds // 2]
        or candidate_median != sorted(candidate)[rounds // 2]
        or abs(ratio - ordinary_median / candidate_median) > 1e-6
    ):
        raise QualificationError("benchmark median/rate accounting differs")
    return row


def validate_result(
    value: object, *, source_segment: bool
) -> dict[str, object]:
    row = _exact_keys(
        value,
        {
            "accepted",
            "benchmark",
            "bounded_case_count",
            "bounded_cases",
            "bounded_prime_limit",
            "bounded_tail_prime_count",
            "candidate_resources",
            "compute_capability",
            "events_per_epoch",
            "kind",
            "lean_bridge_complete",
            "maximum_table_slots",
            "ordinary_resources",
            "performance_evidence_eligible",
            "production_identity_promoted",
            "production_ready",
            "release_build_profile_eligible",
            "resource_gate_passed",
            "runtime_instrumentation_status",
            "source_segment_mode",
            "threads_per_block",
            "word_owner_cutoff",
            "warp_parallel_cutoff",
        },
        "qualification result",
    )
    if row["accepted"] is not True or row["kind"] != KIND:
        raise QualificationError("qualification did not accept exact kind")
    fixed = {
        "bounded_case_count": 5,
        "bounded_prime_limit": 262_147,
        "bounded_tail_prime_count": 19_489,
        "events_per_epoch": 2,
        "lean_bridge_complete": False,
        "maximum_table_slots": 512,
        "performance_evidence_eligible": False,
        "production_identity_promoted": False,
        "production_ready": False,
        "release_build_profile_eligible": True,
        "resource_gate_passed": True,
        "runtime_instrumentation_status": "not-inspected-by-runner",
        "source_segment_mode": source_segment,
        "threads_per_block": 256,
        "word_owner_cutoff": 2_039,
        "warp_parallel_cutoff": 32_749,
    }
    for key, wanted in fixed.items():
        if row[key] != wanted:
            raise QualificationError(f"qualification.{key} differs")
    if not isinstance(row["compute_capability"], str) or not re.fullmatch(
        r"[0-9]{1,2}\.[0-9]", row["compute_capability"]
    ):
        raise QualificationError("compute capability is malformed")
    cases = row["bounded_cases"]
    if not isinstance(cases, list) or len(cases) != len(EXPECTED_CASES):
        raise QualificationError("bounded case roster differs")
    for value_case, name in zip(cases, EXPECTED_CASES, strict=True):
        _validate_case(value_case, name)
    _validate_resources(row["ordinary_resources"], False)
    _validate_resources(row["candidate_resources"], True)
    _validate_benchmark(row["benchmark"], source_segment)
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--nvcc", type=Path, default=Path("/usr/local/cuda/bin/nvcc")
    )
    parser.add_argument("--arch", default="native")
    parser.add_argument("--source-segment", action="store_true")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--pretty", action="store_true")
    arguments = parser.parse_args()
    if not re.fullmatch(r"(?:native|sm_[0-9]{2,3})", arguments.arch):
        print("architecture must be native or sm_NN", file=sys.stderr)
        return 2
    if not SOURCE.is_file() or not arguments.nvcc.is_file():
        print("qualification source or nvcc is missing", file=sys.stderr)
        return 2
    try:
        with tempfile.TemporaryDirectory(
            prefix="tg-goldbach-tail-combiner-"
        ) as temporary:
            executable = Path(temporary) / "qualifier"
            build_argv = [
                str(arguments.nvcc),
                "-O3",
                "-std=c++20",
                f"-arch={arguments.arch}",
                "-lineinfo",
                (
                    "-DSPARKINTERVAL_ENABLE_GOLDBACH_"
                    "TAIL_COMBINER_QUALIFICATION=1"
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
                    "qualification compilation failed: "
                    + (built.stderr.strip() or built.stdout.strip())
                )
            run_argv = [str(executable)]
            if arguments.source_segment:
                run_argv.append("--source-segment")
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
                    "qualification execution failed: "
                    + (ran.stderr.strip() or ran.stdout.strip())
                )
            try:
                result = validate_result(
                    json.loads(ran.stdout),
                    source_segment=arguments.source_segment,
                )
            except json.JSONDecodeError as error:
                raise QualificationError(
                    "qualification stdout is not one JSON value"
                ) from error
            report = {
                "accepted": True,
                "arch": arguments.arch,
                "build_argv": build_argv,
                "classification": (
                    "qualification-only-unpromoted-candidate"
                ),
                "executable_sha256": sha256(executable),
                "kind": REPORT_KIND,
                "nvcc_sha256": sha256(arguments.nvcc),
                "result": result,
                "run_argv": run_argv,
                "source_sha256": sha256(SOURCE),
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
