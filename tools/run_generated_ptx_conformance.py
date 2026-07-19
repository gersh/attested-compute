#!/usr/bin/env python3
"""End-to-end conformance for Lean-generated sm_121 polynomial PTX.

The harness writes one canonical Phase 3 reference batch, invokes the Lean
generator, audits and assembles the PTX, audits the resulting cubin SASS, runs
that exact cubin through the strict CUDA Driver API host, and compares endpoints and Phase 4-compatible statuses against exact
integer/rational reference evaluation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reference import evaluator  # noqa: E402
from reference import exact_binary64 as exact  # noqa: E402
from reference import format as wire  # noqa: E402


INPUT_HEADER = struct.Struct("<8sIIQ")
OUTPUT_HEADER = struct.Struct("<8sIIQ")
INTERVAL = struct.Struct("<QQ")
OUTPUT = struct.Struct("<QQB7s")
INPUT_MAGIC = b"SIG64I01"
OUTPUT_MAGIC = b"SIG64O01"
FORMAT_VERSION = 1
VARIABLE_COUNT = 3
WHOLE = exact.Binary64Interval(exact.NEGATIVE_INFINITY, exact.POSITIVE_INFINITY)


def endpoint(value: exact.Binary64Interval) -> dict[str, str]:
    return {"lo": wire.binary64_hex(value.lo), "hi": wire.binary64_hex(value.hi)}


def expression() -> dict[str, Any]:
    # ((x * y) + -(z^3)) - [-min_subnormal, +min_subnormal]
    return {
        "op": "sub",
        "left": {
            "op": "add",
            "left": {
                "op": "mul",
                "left": {"op": "var", "index": 0},
                "right": {"op": "var", "index": 1},
            },
            "right": {
                "op": "neg",
                "arg": {
                    "op": "pow_nat",
                    "arg": {"op": "var", "index": 2},
                    "exponent": 3,
                },
            },
        },
        "right": {
            "op": "const",
            "value": {"lo": "8000000000000001", "hi": "0000000000000001"},
        },
    }


SPECIAL: tuple[exact.Binary64Interval, ...] = (
    exact.Binary64Interval(exact.POSITIVE_ZERO, exact.POSITIVE_ZERO),
    exact.Binary64Interval(exact.NEGATIVE_ZERO, exact.NEGATIVE_ZERO),
    exact.Binary64Interval(exact.NEGATIVE_ZERO, exact.POSITIVE_ZERO),
    exact.Binary64Interval(0x8000000000000001, 0x0000000000000001),
    exact.Binary64Interval(0xBFF0000000000000, 0x3FF0000000000000),
    exact.Binary64Interval(0x3FF0000000000000, 0x3FF0000000000001),
    exact.Binary64Interval(0xBFF0000000000001, 0xBFF0000000000000),
    exact.Binary64Interval(exact.MAX_FINITE, exact.MAX_FINITE),
    exact.Binary64Interval(exact.MIN_FINITE, exact.MIN_FINITE),
    exact.Binary64Interval(0x4000000000000000, 0x4000000000000000),
    exact.Binary64Interval(0xC000000000000000, 0xC000000000000000),
    exact.Binary64Interval(0x0010000000000000, 0x0010000000000001),
)


def random_finite_word(rng: random.Random) -> int:
    while True:
        bits = rng.getrandbits(64)
        if exact.is_finite(bits):
            return bits


def random_interval(rng: random.Random) -> exact.Binary64Interval:
    if rng.randrange(5) == 0:
        return rng.choice(SPECIAL)
    left = random_finite_word(rng)
    right = random_finite_word(rng)
    try:
        return exact.Binary64Interval(left, right)
    except ValueError:
        return exact.Binary64Interval(right, left)


def rows(count: int, seed: int) -> list[tuple[exact.Binary64Interval, ...]]:
    rng = random.Random(seed)
    curated: list[tuple[exact.Binary64Interval, ...]] = []
    zeros = SPECIAL[:3]
    for left in zeros:
        for right in zeros:
            curated.append((left, right, exact.Binary64Interval(0, 0)))
    curated.extend(
        [
            (SPECIAL[7], SPECIAL[9], SPECIAL[0]),
            (SPECIAL[8], SPECIAL[9], SPECIAL[1]),
            (SPECIAL[5], SPECIAL[6], SPECIAL[7]),
            (SPECIAL[3], SPECIAL[3], SPECIAL[3]),
        ]
    )
    result = curated[:count]
    while len(result) < count:
        result.append(tuple(random_interval(rng) for _ in range(VARIABLE_COUNT)))
    return result


def make_batch(values: list[tuple[exact.Binary64Interval, ...]]) -> dict[str, Any]:
    batch: dict[str, Any] = {
        "schema_version": wire.SCHEMA_VERSION,
        "kind": wire.BATCH_KIND,
        "algorithm": wire.ALGORITHM_ID,
        "variable_count": VARIABLE_COUNT,
        "expression": expression(),
        "rows": [[endpoint(value) for value in row] for row in values],
    }
    return wire.validate_batch(batch)


def write_driver_input(
    path: Path, values: list[tuple[exact.Binary64Interval, ...]], variable_count: int
) -> None:
    with path.open("wb") as output:
        output.write(
            INPUT_HEADER.pack(INPUT_MAGIC, FORMAT_VERSION, variable_count, len(values))
        )
        for row in values:
            for value in row:
                output.write(INTERVAL.pack(value.lo, value.hi))


def read_driver_output(
    path: Path, row_count: int, variable_count: int
) -> list[tuple[int, int, int]]:
    raw = path.read_bytes()
    expected_bytes = OUTPUT_HEADER.size + row_count * OUTPUT.size
    if len(raw) != expected_bytes:
        raise ValueError("driver output length mismatch")
    magic, version, encoded_variable_count, encoded_rows = OUTPUT_HEADER.unpack_from(raw)
    if (
        magic != OUTPUT_MAGIC
        or version != FORMAT_VERSION
        or encoded_variable_count != variable_count
        or encoded_rows != row_count
    ):
        raise ValueError("driver output header mismatch")
    result: list[tuple[int, int, int]] = []
    for row in range(row_count):
        lo, hi, status, reserved = OUTPUT.unpack_from(
            raw, OUTPUT_HEADER.size + row * OUTPUT.size
        )
        if reserved != b"\0" * 7:
            raise ValueError(f"driver output row {row} has nonzero reserved bytes")
        result.append((lo, hi, status))
    return result


def has_finite_endpoints(value: exact.Binary64Interval) -> bool:
    return exact.is_finite(value.lo) and exact.is_finite(value.hi)


def expected_with_status(
    node: dict[str, Any], row: tuple[exact.Binary64Interval, ...]
) -> tuple[exact.Binary64Interval, int]:
    op = node["op"]
    if op == "const":
        raw = node["value"]
        return exact.Binary64Interval(int(raw["lo"], 16), int(raw["hi"], 16)), 0
    if op == "var":
        return row[node["index"]], 0
    if op == "neg":
        value, status = expected_with_status(node["arg"], row)
        return (WHOLE, status) if status != 0 else (exact.interval_neg(value), 0)
    if op == "pow_nat":
        base, status = expected_with_status(node["arg"], row)
        if status != 0:
            return WHOLE, status
        result = exact.Binary64Interval(0x3FF0000000000000, 0x3FF0000000000000)
        for _ in range(node["exponent"]):
            if not has_finite_endpoints(result) or not has_finite_endpoints(base):
                return WHOLE, 2
            result = exact.interval_mul(result, base)
        return result, 0
    left, left_status = expected_with_status(node["left"], row)
    if left_status != 0:
        return WHOLE, left_status
    right, right_status = expected_with_status(node["right"], row)
    if right_status != 0:
        return WHOLE, right_status
    if not has_finite_endpoints(left) or not has_finite_endpoints(right):
        return WHOLE, 2
    operation = {
        "add": exact.interval_add,
        "sub": exact.interval_sub,
        "mul": exact.interval_mul,
    }[op]
    return operation(left, right), 0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tool_identity(path: Path) -> dict[str, str]:
    resolved = path.resolve()
    completed = subprocess.run(
        [str(resolved), "--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"cannot obtain tool version from {resolved}")
    version = (completed.stdout + completed.stderr).strip()
    if not version:
        raise RuntimeError(f"tool emitted an empty version string: {resolved}")
    return {
        "path": str(resolved),
        "sha256": sha256(resolved),
        "version": version,
    }


def run_checked(command: list[str], cwd: Path = ROOT) -> float:
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=cwd, check=False)
    elapsed = time.perf_counter() - started
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed with exit {completed.returncode}: {' '.join(command)}"
        )
    return elapsed


def run_driver(
    command: list[str], report_path: Path, *, row_count: int,
    allow_other_device: bool
) -> tuple[float, dict[str, Any]]:
    started = time.perf_counter()
    completed = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, check=False
    )
    elapsed = time.perf_counter() - started
    if completed.returncode != 0:
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        raise RuntimeError(
            f"driver failed with exit {completed.returncode}: {' '.join(command)}"
        )
    try:
        metadata = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("driver did not emit one valid JSON metadata object") from error
    expected = {
        "schema_version": 1,
        "kind": "sparkinterval_generated_driver_run",
        "module_kind": "offline_cubin",
        "allow_other_device": allow_other_device,
        "row_count": row_count,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise RuntimeError(f"driver metadata mismatch for {key}")
    if not allow_other_device and (
        metadata.get("device_name") != "NVIDIA GB10"
        or metadata.get("compute_capability") != "12.1"
    ):
        raise RuntimeError("driver metadata does not identify the required DGX Spark GPU")
    report_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return elapsed, metadata


def extract_and_audit_sass(
    cubin: Path, ptx_audit: Path, sass: Path, sass_audit: Path
) -> tuple[float, float]:
    nvdisasm = shutil.which("nvdisasm")
    if nvdisasm is None:
        raise RuntimeError("nvdisasm is required for the cubin SASS audit")
    started = time.perf_counter()
    completed = subprocess.run(
        [nvdisasm, str(cubin)], capture_output=True, cwd=ROOT, check=False
    )
    extraction_seconds = time.perf_counter() - started
    if completed.returncode != 0 or not completed.stdout:
        raise RuntimeError("nvdisasm failed to produce cubin SASS")
    sass.write_bytes(completed.stdout)
    audit_seconds = run_checked(
        [
            sys.executable,
            str(ROOT / "tools/inspect_generated_sass.py"),
            str(sass),
            str(ptx_audit),
            str(sass_audit),
            "--cubin",
            str(cubin),
        ]
    )
    return extraction_seconds, audit_seconds


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--generator", type=Path, default=ROOT / ".lake/build/bin/sparkinterval-gen"
    )
    parser.add_argument(
        "--driver", type=Path, default=ROOT / "build/dgx-spark/sparkinterval-generated-driver"
    )
    parser.add_argument("--count", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=0x51A5E005)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--allow-other-device", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.count <= wire.MAX_BATCH_ROWS:
        parser.error(f"--count must be in [1, {wire.MAX_BATCH_ROWS}]")
    generator = args.generator.resolve()
    driver = args.driver.resolve()
    if not generator.is_file() or not driver.is_file():
        parser.error("--generator and --driver must name existing executables")
    ptxas = shutil.which("ptxas")
    if ptxas is None:
        parser.error("ptxas is required for the offline assembly check")
    nvdisasm = shutil.which("nvdisasm")
    if nvdisasm is None:
        parser.error("nvdisasm is required for the offline SASS audit")

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.work_dir is None:
        temporary = tempfile.TemporaryDirectory(prefix="sparkinterval-generated-")
        work_dir = Path(temporary.name)
    else:
        work_dir = args.work_dir.resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
    batch_path = work_dir / "batch.json"
    input_path = work_dir / "rows.bin"
    ptx_path = work_dir / "kernel.ptx"
    cubin_path = work_dir / "kernel.sm_121.cubin"
    audit_path = work_dir / "ptx-audit.json"
    sass_path = work_dir / "kernel.sm_121.sass.txt"
    sass_audit_path = work_dir / "sass-audit.json"
    output_path = work_dir / "results.bin"
    driver_report_path = work_dir / "driver-run.json"

    values = rows(args.count, args.seed)
    batch = make_batch(values)
    wire.write_canonical_json(batch_path, batch)
    write_driver_input(input_path, values, VARIABLE_COUNT)
    generation_seconds = run_checked(
        [str(generator), "--input", str(batch_path), "--output", str(ptx_path)]
    )
    audit_seconds = run_checked(
        [
            sys.executable,
            str(ROOT / "tools/inspect_generated_ptx.py"),
            str(ptx_path),
            str(audit_path),
        ]
    )
    assembly_seconds = run_checked(
        [ptxas, "-arch=sm_121", str(ptx_path), "-o", str(cubin_path)]
    )
    sass_extraction_seconds, sass_audit_seconds = extract_and_audit_sass(
        cubin_path, audit_path, sass_path, sass_audit_path
    )
    driver_command = [
        str(driver),
        "--cubin",
        str(cubin_path),
        "--input",
        str(input_path),
        "--output",
        str(output_path),
    ]
    if args.allow_other_device:
        driver_command.append("--allow-other-device")
    gpu_seconds, driver_metadata = run_driver(
        driver_command,
        driver_report_path,
        row_count=len(values),
        allow_other_device=args.allow_other_device,
    )

    actual = read_driver_output(output_path, len(values), VARIABLE_COUNT)
    reference_started = time.perf_counter()
    reference_result = evaluator.evaluate_batch(batch)
    expected_status = [
        expected_with_status(batch["expression"], row) for row in values
    ]
    reference_seconds = time.perf_counter() - reference_started
    mismatches: list[dict[str, Any]] = []
    for index, ((lo, hi, status), encoded, (value, expected_status_value)) in enumerate(
        zip(actual, reference_result["rows"], expected_status)
    ):
        expected_lo = int(encoded["lo"], 16)
        expected_hi = int(encoded["hi"], 16)
        if (lo, hi, status) != (expected_lo, expected_hi, expected_status_value):
            mismatches.append(
                {
                    "suite": "polynomial",
                    "row": index,
                    "actual": [f"{lo:016x}", f"{hi:016x}", status],
                    "expected": [
                        f"{expected_lo:016x}",
                        f"{expected_hi:016x}",
                        expected_status_value,
                    ],
                    "status_model_interval": [
                        f"{value.lo:016x}",
                        f"{value.hi:016x}",
                    ],
                }
            )
            if len(mismatches) >= 20:
                break
    status_counts = {
        str(status): sum(1 for _, _, actual_status in actual if actual_status == status)
        for status in sorted({actual_status for _, _, actual_status in actual})
    }

    # A separate multiplication-only suite prevents later polynomial nodes
    # from masking a signed-zero tie error in PTX min.f64/max.f64 corner
    # reduction.  It exercises (+0,+0), (-0,-0), and [-0,+0] pairwise.
    zero_values = [
        (left, right) for left in SPECIAL[:3] for right in SPECIAL[:3]
    ]
    zero_batch: dict[str, Any] = wire.validate_batch(
        {
            "schema_version": wire.SCHEMA_VERSION,
            "kind": wire.BATCH_KIND,
            "algorithm": wire.ALGORITHM_ID,
            "variable_count": 2,
            "expression": {
                "op": "mul",
                "left": {"op": "var", "index": 0},
                "right": {"op": "var", "index": 1},
            },
            "rows": [[endpoint(value) for value in row] for row in zero_values],
        }
    )
    zero_batch_path = work_dir / "signed-zero-batch.json"
    zero_input_path = work_dir / "signed-zero-rows.bin"
    zero_ptx_path = work_dir / "signed-zero-kernel.ptx"
    zero_cubin_path = work_dir / "signed-zero-kernel.sm_121.cubin"
    zero_audit_path = work_dir / "signed-zero-ptx-audit.json"
    zero_sass_path = work_dir / "signed-zero-kernel.sm_121.sass.txt"
    zero_sass_audit_path = work_dir / "signed-zero-sass-audit.json"
    zero_output_path = work_dir / "signed-zero-results.bin"
    zero_driver_report_path = work_dir / "signed-zero-driver-run.json"
    wire.write_canonical_json(zero_batch_path, zero_batch)
    write_driver_input(zero_input_path, zero_values, 2)
    signed_zero_generation_seconds = run_checked(
        [
            str(generator),
            "--input",
            str(zero_batch_path),
            "--output",
            str(zero_ptx_path),
        ]
    )
    signed_zero_audit_seconds = run_checked(
        [
            sys.executable,
            str(ROOT / "tools/inspect_generated_ptx.py"),
            str(zero_ptx_path),
            str(zero_audit_path),
        ]
    )
    signed_zero_assembly_seconds = run_checked(
        [
            ptxas,
            "-arch=sm_121",
            str(zero_ptx_path),
            "-o",
            str(zero_cubin_path),
        ]
    )
    (
        signed_zero_sass_extraction_seconds,
        signed_zero_sass_audit_seconds,
    ) = extract_and_audit_sass(
        zero_cubin_path,
        zero_audit_path,
        zero_sass_path,
        zero_sass_audit_path,
    )
    zero_driver_command = [
        str(driver),
        "--cubin",
        str(zero_cubin_path),
        "--input",
        str(zero_input_path),
        "--output",
        str(zero_output_path),
    ]
    if args.allow_other_device:
        zero_driver_command.append("--allow-other-device")
    signed_zero_gpu_seconds, zero_driver_metadata = run_driver(
        zero_driver_command,
        zero_driver_report_path,
        row_count=len(zero_values),
        allow_other_device=args.allow_other_device,
    )
    zero_actual = read_driver_output(zero_output_path, len(zero_values), 2)
    zero_reference = evaluator.evaluate_batch(zero_batch)
    signed_zero_mismatch_count = 0
    for index, ((lo, hi, status), encoded) in enumerate(
        zip(zero_actual, zero_reference["rows"])
    ):
        expected_lo = int(encoded["lo"], 16)
        expected_hi = int(encoded["hi"], 16)
        if (lo, hi, status) != (expected_lo, expected_hi, 0):
            signed_zero_mismatch_count += 1
            if len(mismatches) < 20:
                mismatches.append(
                    {
                        "suite": "signed_zero_mul_corner_reduction",
                        "row": index,
                        "actual": [f"{lo:016x}", f"{hi:016x}", status],
                        "expected": [f"{expected_lo:016x}", f"{expected_hi:016x}", 0],
                    }
                )
    report = {
        "schema_version": 1,
        "kind": "sparkinterval_generated_ptx_conformance",
        "accepted": not mismatches,
        "target": "sm_121",
        "execution_module": {
            "kind": "offline_ptxas_cubin",
            "development_ptx_jit_used": False,
            "cubin_sha256": sha256(cubin_path),
            "sass_audit_passed_before_execution": True,
        },
        "hardware_execution": driver_metadata,
        "signed_zero_hardware_execution": zero_driver_metadata,
        "toolchain": {
            "ptxas": tool_identity(Path(ptxas)),
            "nvdisasm": tool_identity(Path(nvdisasm)),
        },
        "seed": args.seed,
        "row_count": len(values),
        "status_counts": status_counts,
        "signed_zero_mul_probe": {
            "row_count": len(zero_values),
            "mismatch_count": signed_zero_mismatch_count,
            "covers_pairwise": ["+0", "-0", "[-0,+0]"],
        },
        "mismatch_count_capped": len(mismatches),
        "mismatches": mismatches,
        "timing_seconds": {
            "generation": generation_seconds,
            "ptx_audit": audit_seconds,
            "ptxas": assembly_seconds,
            "nvdisasm": sass_extraction_seconds,
            "sass_audit": sass_audit_seconds,
            "gpu_driver_total": gpu_seconds,
            "exact_reference": reference_seconds,
            "signed_zero_generation": signed_zero_generation_seconds,
            "signed_zero_ptx_audit": signed_zero_audit_seconds,
            "signed_zero_ptxas": signed_zero_assembly_seconds,
            "signed_zero_nvdisasm": signed_zero_sass_extraction_seconds,
            "signed_zero_sass_audit": signed_zero_sass_audit_seconds,
            "signed_zero_gpu_driver_total": signed_zero_gpu_seconds,
        },
        "sha256": {
            "batch": sha256(batch_path),
            "ptx": sha256(ptx_path),
            "cubin": sha256(cubin_path),
            "rows": sha256(input_path),
            "results": sha256(output_path),
            "driver_report": sha256(driver_report_path),
            "ptx_audit": sha256(audit_path),
            "sass": sha256(sass_path),
            "sass_audit": sha256(sass_audit_path),
            "signed_zero_batch": sha256(zero_batch_path),
            "signed_zero_ptx": sha256(zero_ptx_path),
            "signed_zero_cubin": sha256(zero_cubin_path),
            "signed_zero_rows": sha256(zero_input_path),
            "signed_zero_results": sha256(zero_output_path),
            "signed_zero_driver_report": sha256(zero_driver_report_path),
            "signed_zero_ptx_audit": sha256(zero_audit_path),
            "signed_zero_sass": sha256(zero_sass_path),
            "signed_zero_sass_audit": sha256(zero_sass_audit_path),
            "generator_executable": sha256(generator),
            "generated_driver_executable": sha256(driver),
            "conformance_harness": sha256(Path(__file__).resolve()),
            "ptx_audit_tool": sha256(ROOT / "tools/inspect_generated_ptx.py"),
            "sass_audit_tool": sha256(ROOT / "tools/inspect_generated_sass.py"),
            "reference_evaluator": sha256(ROOT / "reference/evaluator.py"),
            "reference_binary64": sha256(ROOT / "reference/exact_binary64.py"),
            "reference_format": sha256(ROOT / "reference/format.py"),
        },
    }
    report_path = work_dir / "report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    if temporary is not None:
        temporary.cleanup()
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
