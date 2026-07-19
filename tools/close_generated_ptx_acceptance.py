#!/usr/bin/env python3
"""Close replay, cross-backend, and SASS checks for a retained Phase 5 run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reference import evaluator  # noqa: E402
from reference import exact_binary64 as exact  # noqa: E402
from reference import format as wire  # noqa: E402


GENERATED_HEADER = struct.Struct("<8sIIQ")
PHASE4_HEADER = struct.Struct("<8sIIIIQ")
PHASE4_INSTRUCTION = struct.Struct("<BBHIQQ")
OUTPUT = struct.Struct("<QQB7s")
GENERATED_INPUT_MAGIC = b"SIG64I01"
GENERATED_OUTPUT_MAGIC = b"SIG64O01"
PHASE4_INPUT_MAGIC = b"SIE64I01"
PHASE4_OUTPUT_MAGIC = b"SIE64O01"
OPCODES = {
    "const": 1,
    "var": 2,
    "neg": 3,
    "add": 4,
    "sub": 5,
    "mul": 6,
    "pow_nat": 11,
}
WHOLE = exact.Binary64Interval(exact.NEGATIVE_INFINITY, exact.POSITIVE_INFINITY)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generated_input_payload_binding(path: Path) -> tuple[str, int]:
    raw = path.read_bytes()
    if len(raw) < GENERATED_HEADER.size:
        raise ValueError("generated row input is truncated")
    payload = raw[GENERATED_HEADER.size :]
    return hashlib.sha256(payload).hexdigest(), len(payload)


def run(command: list[str]) -> float:
    started = time.perf_counter()
    completed = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, check=False
    )
    elapsed = time.perf_counter() - started
    if completed.returncode != 0:
        if completed.stdout:
            print(completed.stdout, file=sys.stderr, end="")
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        raise RuntimeError(
            f"command failed with exit {completed.returncode}: {' '.join(command)}"
        )
    return elapsed


def run_json(command: list[str]) -> tuple[float, dict[str, Any]]:
    started = time.perf_counter()
    completed = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, check=False
    )
    elapsed = time.perf_counter() - started
    if completed.returncode != 0:
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        raise RuntimeError(
            f"command failed with exit {completed.returncode}: {' '.join(command)}"
        )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("command did not emit one JSON object") from error
    if not isinstance(value, dict):
        raise RuntimeError("command metadata is not a JSON object")
    return elapsed, value


def compile_expression(node: dict[str, Any]) -> list[tuple[int, int, int, int]]:
    op = node["op"]
    if op == "const":
        value = node["value"]
        return [(OPCODES[op], 0, int(value["lo"], 16), int(value["hi"], 16))]
    if op == "var":
        return [(OPCODES[op], node["index"], 0, 0)]
    if op == "neg":
        return compile_expression(node["arg"]) + [(OPCODES[op], 0, 0, 0)]
    if op == "pow_nat":
        return compile_expression(node["arg"]) + [
            (OPCODES[op], node["exponent"], 0, 0)
        ]
    if op in {"add", "sub", "mul"}:
        return (
            compile_expression(node["left"])
            + compile_expression(node["right"])
            + [(OPCODES[op], 0, 0, 0)]
        )
    raise ValueError(f"expression operation is outside Phase 5 slice: {op}")


def maximum_stack(instructions: list[tuple[int, int, int, int]]) -> int:
    depth = 0
    maximum = 0
    for opcode, _, _, _ in instructions:
        if opcode in {1, 2}:
            depth += 1
        elif opcode in {3, 11}:
            if depth < 1:
                raise ValueError("postfix unary stack underflow")
        else:
            if depth < 2:
                raise ValueError("postfix binary stack underflow")
            depth -= 1
        maximum = max(maximum, depth)
    if depth != 1:
        raise ValueError("postfix expression does not finish with one value")
    return maximum


def make_phase4_input(
    batch: dict[str, Any], generated_rows: Path, output: Path
) -> tuple[int, int, int]:
    raw = generated_rows.read_bytes()
    if len(raw) < GENERATED_HEADER.size:
        raise ValueError("generated row input is truncated")
    magic, version, variable_count, row_count = GENERATED_HEADER.unpack_from(raw)
    if (
        magic != GENERATED_INPUT_MAGIC
        or version != 1
        or variable_count != batch["variable_count"]
        or row_count != len(batch["rows"])
    ):
        raise ValueError("generated row input is not bound to the canonical batch")
    expected_size = GENERATED_HEADER.size + row_count * variable_count * 16
    if len(raw) != expected_size:
        raise ValueError("generated row input length mismatch")
    payload_offset = GENERATED_HEADER.size
    for row_index, row in enumerate(batch["rows"]):
        for column, interval in enumerate(row):
            lo, hi = struct.unpack_from("<QQ", raw, payload_offset)
            expected_lo = int(interval["lo"], 16)
            expected_hi = int(interval["hi"], 16)
            if (lo, hi) != (expected_lo, expected_hi):
                raise ValueError(
                    f"generated row payload differs from batch at "
                    f"row {row_index}, column {column}"
                )
            payload_offset += 16
    instructions = compile_expression(batch["expression"])
    stack = maximum_stack(instructions)
    encoded = bytearray(
        PHASE4_HEADER.pack(
            PHASE4_INPUT_MAGIC,
            1,
            len(instructions),
            variable_count,
            stack,
            row_count,
        )
    )
    for opcode, argument, lo, hi in instructions:
        encoded += PHASE4_INSTRUCTION.pack(opcode, 0, 0, argument, lo, hi)
    encoded += raw[GENERATED_HEADER.size :]
    output.write_bytes(encoded)
    return len(instructions), stack, row_count


def output_payload(
    path: Path,
    *,
    phase4: bool,
    instruction_count: int,
    variable_count: int,
    stack: int,
    row_count: int,
) -> bytes:
    raw = path.read_bytes()
    if phase4:
        if len(raw) < PHASE4_HEADER.size:
            raise ValueError("Phase 4 output is truncated")
        header = PHASE4_HEADER.unpack_from(raw)
        if header != (
            PHASE4_OUTPUT_MAGIC,
            1,
            instruction_count,
            variable_count,
            stack,
            row_count,
        ):
            raise ValueError("Phase 4 output header mismatch")
        payload = raw[PHASE4_HEADER.size :]
    else:
        if len(raw) < GENERATED_HEADER.size:
            raise ValueError("generated output is truncated")
        header = GENERATED_HEADER.unpack_from(raw)
        if header != (GENERATED_OUTPUT_MAGIC, 1, variable_count, row_count):
            raise ValueError("generated output header mismatch")
        payload = raw[GENERATED_HEADER.size :]
    if len(payload) != row_count * OUTPUT.size:
        raise ValueError("output payload length mismatch")
    return payload


def batch_rows(
    batch: dict[str, Any],
) -> list[tuple[exact.Binary64Interval, ...]]:
    return [
        tuple(
            exact.Binary64Interval(int(interval["lo"], 16), int(interval["hi"], 16))
            for interval in row
        )
        for row in batch["rows"]
    ]


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
    }.get(op)
    if operation is None:
        raise ValueError(f"expression operation is outside Phase 5 slice: {op}")
    return operation(left, right), 0


def verify_exact_reference(
    batch: dict[str, Any], results_path: Path
) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    rows = batch_rows(batch)
    reference = evaluator.evaluate_batch(batch)
    payload = output_payload(
        results_path,
        phase4=False,
        instruction_count=0,
        variable_count=batch["variable_count"],
        stack=0,
        row_count=len(rows),
    )
    mismatches: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    mismatch_count = 0
    for index, (row, encoded) in enumerate(zip(rows, reference["rows"])):
        lo, hi, status, reserved = OUTPUT.unpack_from(payload, index * OUTPUT.size)
        if reserved != b"\0" * 7:
            raise ValueError(f"generated result row {index} has nonzero reserved bytes")
        key = str(status)
        status_counts[key] = status_counts.get(key, 0) + 1
        _, expected_status = expected_with_status(batch["expression"], row)
        expected = (int(encoded["lo"], 16), int(encoded["hi"], 16), expected_status)
        if (lo, hi, status) != expected:
            mismatch_count += 1
            if len(mismatches) < 20:
                mismatches.append(
                    {
                        "row": index,
                        "actual": [f"{lo:016x}", f"{hi:016x}", status],
                        "expected": [
                            f"{expected[0]:016x}",
                            f"{expected[1]:016x}",
                            expected[2],
                        ],
                    }
                )
    elapsed = time.perf_counter() - started
    return {
        "passed": mismatch_count == 0,
        "row_count": len(rows),
        "mismatch_count": mismatch_count,
        "mismatches_capped": mismatches,
        "status_counts": status_counts,
    }, elapsed


def validate_generated_rows(batch: dict[str, Any], path: Path) -> None:
    raw = path.read_bytes()
    if len(raw) < GENERATED_HEADER.size:
        raise ValueError("generated row input is truncated")
    header = GENERATED_HEADER.unpack_from(raw)
    expected_header = (
        GENERATED_INPUT_MAGIC,
        1,
        batch["variable_count"],
        len(batch["rows"]),
    )
    if header != expected_header:
        raise ValueError("generated row input is not bound to its canonical batch")
    expected_size = (
        GENERATED_HEADER.size
        + len(batch["rows"]) * batch["variable_count"] * 16
    )
    if len(raw) != expected_size:
        raise ValueError("generated row input length mismatch")
    offset = GENERATED_HEADER.size
    for row_index, row in enumerate(batch["rows"]):
        for column, interval in enumerate(row):
            actual = struct.unpack_from("<QQ", raw, offset)
            expected = (int(interval["lo"], 16), int(interval["hi"], 16))
            if actual != expected:
                raise ValueError(
                    f"generated row payload differs from batch at "
                    f"row {row_index}, column {column}"
                )
            offset += 16


def expected_signed_zero_batch() -> dict[str, Any]:
    positive_zero = {"lo": "0000000000000000", "hi": "0000000000000000"}
    negative_zero = {"lo": "8000000000000000", "hi": "8000000000000000"}
    both_zeros = {"lo": "8000000000000000", "hi": "0000000000000000"}
    probes = (positive_zero, negative_zero, both_zeros)
    return wire.validate_batch(
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
            "rows": [
                [dict(left), dict(right)] for left in probes for right in probes
            ],
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--generator", type=Path, required=True)
    parser.add_argument("--driver", type=Path, required=True)
    expression_runner = parser.add_mutually_exclusive_group(required=True)
    expression_runner.add_argument(
        "--expression-runner",
        dest="phase4",
        type=Path,
        metavar="PATH",
    )
    expression_runner.add_argument(
        "--phase4",
        dest="phase4",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--allow-other-device", action="store_true")
    args = parser.parse_args()
    work = args.work_dir.resolve()
    batch_path = work / "batch.json"
    ptx_path = work / "kernel.ptx"
    cubin_path = work / "kernel.sm_121.cubin"
    ptx_audit_path = work / "ptx-audit.json"
    rows_path = work / "rows.bin"
    results_path = work / "results.bin"
    report_path = work / "report.json"
    for required in (
        batch_path,
        ptx_path,
        cubin_path,
        ptx_audit_path,
        rows_path,
        results_path,
        report_path,
        args.generator,
        args.driver,
        args.phase4,
    ):
        if not required.is_file():
            parser.error(f"required artifact does not exist: {required}")
    batch = wire.load_batch(batch_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("accepted") is not True:
        raise ValueError("base conformance report is not accepted")
    if report.get("execution_module", {}).get("kind") != "offline_ptxas_cubin":
        raise ValueError("base report did not execute the offline-audited cubin")
    if report["execution_module"].get("cubin_sha256") != sha256(cubin_path):
        raise ValueError("base execution-module binding does not match retained cubin")
    hardware = report.get("hardware_execution", {})
    rows_payload_sha256, rows_payload_size = generated_input_payload_binding(
        rows_path
    )
    if (
        hardware.get("module_kind") != "offline_cubin"
        or hardware.get("allow_other_device") != args.allow_other_device
        or hardware.get("byte_binding_schema_version") != 1
        or hardware.get("module_sha256") != sha256(cubin_path)
        or hardware.get("module_size_bytes") != cubin_path.stat().st_size
        or hardware.get("input_payload_sha256") != rows_payload_sha256
        or hardware.get("input_payload_size_bytes") != rows_payload_size
        or hardware.get("output_file_sha256") != sha256(results_path)
        or hardware.get("output_file_size_bytes") != results_path.stat().st_size
        or (
            not args.allow_other_device
            and (
                hardware.get("device_name") != "NVIDIA GB10"
                or hardware.get("compute_capability") != "12.1"
            )
        )
    ):
        raise ValueError("base hardware metadata does not match closure policy")
    zero_hardware = report.get("signed_zero_hardware_execution", {})
    zero_rows_candidate = work / "signed-zero-rows.bin"
    zero_results_candidate = work / "signed-zero-results.bin"
    zero_cubin_candidate = work / "signed-zero-kernel.sm_121.cubin"
    zero_payload_sha256, zero_payload_size = generated_input_payload_binding(
        zero_rows_candidate
    )
    if (
        zero_hardware.get("module_kind") != "offline_cubin"
        or zero_hardware.get("allow_other_device") != args.allow_other_device
        or zero_hardware.get("row_count") != 9
        or zero_hardware.get("byte_binding_schema_version") != 1
        or zero_hardware.get("module_sha256") != sha256(zero_cubin_candidate)
        or zero_hardware.get("module_size_bytes")
        != zero_cubin_candidate.stat().st_size
        or zero_hardware.get("input_payload_sha256") != zero_payload_sha256
        or zero_hardware.get("input_payload_size_bytes") != zero_payload_size
        or zero_hardware.get("output_file_sha256")
        != sha256(zero_results_candidate)
        or zero_hardware.get("output_file_size_bytes")
        != zero_results_candidate.stat().st_size
        or (
            not args.allow_other_device
            and (
                zero_hardware.get("device_name") != "NVIDIA GB10"
                or zero_hardware.get("compute_capability") != "12.1"
            )
        )
    ):
        raise ValueError("signed-zero hardware metadata does not match closure policy")
    if report.get("row_count") != len(batch["rows"]):
        raise ValueError("base report row count differs from canonical batch")
    retained_artifacts = {
        "batch": batch_path,
        "ptx": ptx_path,
        "cubin": cubin_path,
        "rows": rows_path,
        "results": results_path,
        "driver_report": work / "driver-run.json",
        "ptx_audit": ptx_audit_path,
        "sass": work / "kernel.sm_121.sass.txt",
        "sass_audit": work / "sass-audit.json",
        "signed_zero_batch": work / "signed-zero-batch.json",
        "signed_zero_ptx": work / "signed-zero-kernel.ptx",
        "signed_zero_cubin": work / "signed-zero-kernel.sm_121.cubin",
        "signed_zero_rows": work / "signed-zero-rows.bin",
        "signed_zero_results": work / "signed-zero-results.bin",
        "signed_zero_driver_report": work / "signed-zero-driver-run.json",
        "signed_zero_ptx_audit": work / "signed-zero-ptx-audit.json",
        "signed_zero_sass": work / "signed-zero-kernel.sm_121.sass.txt",
        "signed_zero_sass_audit": work / "signed-zero-sass-audit.json",
    }
    recorded_hashes = report.get("sha256", {})
    for name, path in retained_artifacts.items():
        if not path.is_file():
            raise ValueError(f"retained artifact is missing: {name}")
        recorded = recorded_hashes.get(name)
        actual = sha256(path)
        if recorded != actual:
            raise ValueError(
                f"retained artifact hash mismatch for {name}: "
                f"recorded={recorded}, actual={actual}"
            )
    implementation_artifacts = {
        "generator_executable": args.generator.resolve(),
        "generated_driver_executable": args.driver.resolve(),
        "conformance_harness": ROOT / "tools/run_generated_ptx_conformance.py",
        "ptx_audit_tool": ROOT / "tools/inspect_generated_ptx.py",
        "sass_audit_tool": ROOT / "tools/inspect_generated_sass.py",
        "reference_evaluator": ROOT / "reference/evaluator.py",
        "reference_binary64": ROOT / "reference/exact_binary64.py",
        "reference_format": ROOT / "reference/format.py",
    }
    for name, path in implementation_artifacts.items():
        if recorded_hashes.get(name) != sha256(path):
            raise ValueError(f"base report implementation hash mismatch for {name}")
    if json.loads((work / "driver-run.json").read_text(encoding="utf-8")) != hardware:
        raise ValueError("driver metadata artifact differs from base report")
    if json.loads(
        (work / "signed-zero-driver-run.json").read_text(encoding="utf-8")
    ) != report.get("signed_zero_hardware_execution"):
        raise ValueError("signed-zero driver metadata artifact differs from base report")
    retained_ptx_audit = json.loads(ptx_audit_path.read_text(encoding="utf-8"))
    if (
        retained_ptx_audit.get("passed") is not True
        or retained_ptx_audit.get("input_sha256") != sha256(ptx_path)
    ):
        raise ValueError("retained PTX audit is not bound to retained PTX")
    retained_sass_audit_path = work / "sass-audit.json"
    retained_sass_audit = json.loads(
        retained_sass_audit_path.read_text(encoding="utf-8")
    )
    if (
        retained_sass_audit.get("passed") is not True
        or retained_sass_audit.get("ptx_sha256") != sha256(ptx_path)
        or retained_sass_audit.get("sass_sha256")
        != sha256(work / "kernel.sm_121.sass.txt")
        or retained_sass_audit.get("cubin_sha256") != sha256(cubin_path)
    ):
        raise ValueError("retained SASS audit has a mixed artifact binding")
    zero_ptx = work / "signed-zero-kernel.ptx"
    zero_cubin = work / "signed-zero-kernel.sm_121.cubin"
    zero_sass = work / "signed-zero-kernel.sm_121.sass.txt"
    zero_batch_path = work / "signed-zero-batch.json"
    zero_rows_path = work / "signed-zero-rows.bin"
    zero_results_path = work / "signed-zero-results.bin"
    zero_ptx_audit_path = work / "signed-zero-ptx-audit.json"
    zero_sass_audit_path = work / "signed-zero-sass-audit.json"
    zero_ptx_audit = json.loads(zero_ptx_audit_path.read_text(encoding="utf-8"))
    zero_sass_audit = json.loads(zero_sass_audit_path.read_text(encoding="utf-8"))
    if (
        zero_ptx_audit.get("passed") is not True
        or zero_ptx_audit.get("input_sha256") != sha256(zero_ptx)
        or zero_sass_audit.get("passed") is not True
        or zero_sass_audit.get("ptx_sha256") != sha256(zero_ptx)
        or zero_sass_audit.get("sass_sha256") != sha256(zero_sass)
        or zero_sass_audit.get("cubin_sha256") != sha256(zero_cubin)
    ):
        raise ValueError("retained signed-zero artifacts have a mixed binding")
    validate_generated_rows(batch, rows_path)
    zero_batch = wire.load_batch(zero_batch_path)
    if zero_batch != expected_signed_zero_batch():
        raise ValueError("signed-zero batch is not the required exact 3x3 probe")
    validate_generated_rows(zero_batch, zero_rows_path)
    exact_reference, exact_reference_seconds = verify_exact_reference(
        batch, results_path
    )
    zero_exact_reference, zero_exact_reference_seconds = verify_exact_reference(
        zero_batch, zero_results_path
    )
    if report.get("status_counts") != exact_reference["status_counts"]:
        raise ValueError("base report status counts differ from exact replay")

    replay_ptx = work / "kernel.replay.ptx"
    generation_replay_seconds = run(
        [
            str(args.generator.resolve()),
            "--input",
            str(batch_path),
            "--output",
            str(replay_ptx),
        ]
    )
    generation_deterministic = replay_ptx.read_bytes() == ptx_path.read_bytes()
    closure_ptx_audit = work / "ptx-audit.closure.json"
    ptx_audit_seconds = run(
        [
            sys.executable,
            str(ROOT / "tools/inspect_generated_ptx.py"),
            str(replay_ptx),
            str(closure_ptx_audit),
        ]
    )
    ptxas = shutil.which("ptxas")
    if ptxas is None:
        raise RuntimeError("ptxas is required")
    reassembled_cubin = work / "kernel.reassembled.sm_121.cubin"
    reassembly_seconds = run(
        [ptxas, "-arch=sm_121", str(replay_ptx), "-o", str(reassembled_cubin)]
    )
    cubin_deterministic = reassembled_cubin.read_bytes() == cubin_path.read_bytes()

    zero_replay_ptx = work / "signed-zero-kernel.replay.ptx"
    zero_generation_replay_seconds = run(
        [
            str(args.generator.resolve()),
            "--input",
            str(zero_batch_path),
            "--output",
            str(zero_replay_ptx),
        ]
    )
    zero_generation_deterministic = (
        zero_replay_ptx.read_bytes() == zero_ptx.read_bytes()
    )
    zero_closure_ptx_audit = work / "signed-zero-ptx-audit.closure.json"
    zero_ptx_audit_seconds = run(
        [
            sys.executable,
            str(ROOT / "tools/inspect_generated_ptx.py"),
            str(zero_replay_ptx),
            str(zero_closure_ptx_audit),
        ]
    )
    zero_reassembled_cubin = work / "signed-zero-kernel.reassembled.sm_121.cubin"
    zero_reassembly_seconds = run(
        [
            ptxas,
            "-arch=sm_121",
            str(zero_replay_ptx),
            "-o",
            str(zero_reassembled_cubin),
        ]
    )
    zero_cubin_deterministic = (
        zero_reassembled_cubin.read_bytes() == zero_cubin.read_bytes()
    )

    replay_results = work / "results.replay.bin"
    replay_command = [
        str(args.driver.resolve()),
        "--cubin",
        str(cubin_path),
        "--input",
        str(rows_path),
        "--output",
        str(replay_results),
        "--expected-module-sha256",
        sha256(cubin_path),
        "--expected-input-sha256",
        generated_input_payload_binding(rows_path)[0],
    ]
    if args.allow_other_device:
        replay_command.append("--allow-other-device")
    execution_replay_seconds, replay_hardware = run_json(replay_command)
    expected_replay_hardware = dict(hardware)
    if replay_hardware != expected_replay_hardware:
        raise ValueError("replay hardware metadata differs from the base execution")
    execution_deterministic = replay_results.read_bytes() == results_path.read_bytes()

    zero_replay_results = work / "signed-zero-results.replay.bin"
    zero_replay_command = [
        str(args.driver.resolve()),
        "--cubin",
        str(zero_cubin),
        "--input",
        str(zero_rows_path),
        "--output",
        str(zero_replay_results),
        "--expected-module-sha256",
        sha256(zero_cubin),
        "--expected-input-sha256",
        generated_input_payload_binding(zero_rows_path)[0],
    ]
    if args.allow_other_device:
        zero_replay_command.append("--allow-other-device")
    zero_execution_replay_seconds, zero_replay_hardware = run_json(
        zero_replay_command
    )
    if zero_replay_hardware != zero_hardware:
        raise ValueError("signed-zero replay hardware metadata differs from base")
    zero_execution_deterministic = (
        zero_replay_results.read_bytes() == zero_results_path.read_bytes()
    )

    phase4_input = work / "phase4-expression-input.bin"
    phase4_output = work / "phase4-expression-results.bin"
    instruction_count, stack, row_count = make_phase4_input(
        batch, rows_path, phase4_input
    )
    phase4_command = [
        str(args.phase4.resolve()),
        "--input",
        str(phase4_input),
        "--output",
        str(phase4_output),
    ]
    if args.allow_other_device:
        phase4_command.append("--allow-other-device")
    phase4_seconds = run(phase4_command)
    generated_payload = output_payload(
        results_path,
        phase4=False,
        instruction_count=instruction_count,
        variable_count=batch["variable_count"],
        stack=stack,
        row_count=row_count,
    )
    retained_status_counts: dict[str, int] = {}
    for offset in range(0, len(generated_payload), OUTPUT.size):
        _, _, status, reserved = OUTPUT.unpack_from(generated_payload, offset)
        if reserved != b"\0" * 7:
            raise ValueError("generated result has nonzero reserved output bytes")
        key = str(status)
        retained_status_counts[key] = retained_status_counts.get(key, 0) + 1
    if report.get("status_counts") != retained_status_counts:
        raise ValueError("base report status counts differ from retained results")
    phase4_payload = output_payload(
        phase4_output,
        phase4=True,
        instruction_count=instruction_count,
        variable_count=batch["variable_count"],
        stack=stack,
        row_count=row_count,
    )
    cross_backend_equal = phase4_payload == generated_payload

    nvdisasm = shutil.which("nvdisasm")
    if nvdisasm is None:
        raise RuntimeError("nvdisasm is required")
    sass_started = time.perf_counter()
    disassembly = subprocess.run(
        [nvdisasm, str(cubin_path)], capture_output=True, check=False
    )
    sass_seconds = time.perf_counter() - sass_started
    if disassembly.returncode != 0 or not disassembly.stdout:
        raise RuntimeError("nvdisasm failed to produce generated-kernel SASS")
    sass_path = work / "kernel.closure.sm_121.sass.txt"
    sass_path.write_bytes(disassembly.stdout)
    sass_audit_path = work / "sass-audit.closure.json"
    sass_audit_seconds = run(
        [
            sys.executable,
            str(ROOT / "tools/inspect_generated_sass.py"),
            str(sass_path),
            str(closure_ptx_audit),
            str(sass_audit_path),
            "--cubin",
            str(cubin_path),
        ]
    )
    sass_audit = json.loads(sass_audit_path.read_text(encoding="utf-8"))

    zero_sass_started = time.perf_counter()
    zero_disassembly = subprocess.run(
        [nvdisasm, str(zero_cubin)], capture_output=True, check=False
    )
    zero_sass_seconds = time.perf_counter() - zero_sass_started
    if zero_disassembly.returncode != 0 or not zero_disassembly.stdout:
        raise RuntimeError("nvdisasm failed to produce signed-zero SASS")
    zero_closure_sass = work / "signed-zero-kernel.closure.sm_121.sass.txt"
    zero_closure_sass.write_bytes(zero_disassembly.stdout)
    zero_closure_sass_audit = work / "signed-zero-sass-audit.closure.json"
    zero_sass_audit_seconds = run(
        [
            sys.executable,
            str(ROOT / "tools/inspect_generated_sass.py"),
            str(zero_closure_sass),
            str(zero_closure_ptx_audit),
            str(zero_closure_sass_audit),
            "--cubin",
            str(zero_cubin),
        ]
    )
    zero_sass_audit = json.loads(
        zero_closure_sass_audit.read_text(encoding="utf-8")
    )

    passed = (
        exact_reference["passed"]
        and zero_exact_reference["passed"]
        and generation_deterministic
        and cubin_deterministic
        and execution_deterministic
        and zero_generation_deterministic
        and zero_cubin_deterministic
        and zero_execution_deterministic
        and cross_backend_equal
        and sass_audit.get("passed") is True
        and zero_sass_audit.get("passed") is True
    )
    closure = {
        "passed": passed,
        "row_count": row_count,
        "phase4_instruction_count": instruction_count,
        "phase4_max_stack_depth": stack,
        "deterministic_generation": generation_deterministic,
        "deterministic_cubin_reassembly": cubin_deterministic,
        "deterministic_execution_replay": execution_deterministic,
        "replay_hardware_execution": replay_hardware,
        "exact_reference_recomputed": exact_reference,
        "signed_zero_exact_reference_recomputed": zero_exact_reference,
        "signed_zero_deterministic_generation": zero_generation_deterministic,
        "signed_zero_deterministic_cubin_reassembly": zero_cubin_deterministic,
        "signed_zero_deterministic_execution_replay": zero_execution_deterministic,
        "signed_zero_replay_hardware_execution": zero_replay_hardware,
        "phase4_generated_payload_equal": cross_backend_equal,
        "sass_audit_passed": sass_audit.get("passed") is True,
        "signed_zero_sass_audit_passed": zero_sass_audit.get("passed") is True,
        "timing_seconds": {
            "exact_reference_recomputation": exact_reference_seconds,
            "signed_zero_exact_reference_recomputation": zero_exact_reference_seconds,
            "generation_replay": generation_replay_seconds,
            "ptx_audit_replay": ptx_audit_seconds,
            "cubin_reassembly": reassembly_seconds,
            "execution_replay_driver_total": execution_replay_seconds,
            "signed_zero_generation_replay": zero_generation_replay_seconds,
            "signed_zero_ptx_audit_replay": zero_ptx_audit_seconds,
            "signed_zero_cubin_reassembly": zero_reassembly_seconds,
            "signed_zero_execution_replay_driver_total": zero_execution_replay_seconds,
            "phase4_expression_driver_total": phase4_seconds,
            "nvdisasm": sass_seconds,
            "sass_audit": sass_audit_seconds,
            "signed_zero_nvdisasm": zero_sass_seconds,
            "signed_zero_sass_audit": zero_sass_audit_seconds,
        },
        "sha256": {
            "replayed_ptx": sha256(replay_ptx),
            "reassembled_cubin": sha256(reassembled_cubin),
            "replayed_results": sha256(replay_results),
            "signed_zero_replayed_ptx": sha256(zero_replay_ptx),
            "signed_zero_reassembled_cubin": sha256(zero_reassembled_cubin),
            "signed_zero_replayed_results": sha256(zero_replay_results),
            "phase4_input": sha256(phase4_input),
            "phase4_results": sha256(phase4_output),
            "generated_result_payload": hashlib.sha256(generated_payload).hexdigest(),
            "phase4_result_payload": hashlib.sha256(phase4_payload).hexdigest(),
            "sass": sha256(sass_path),
            "sass_audit": sha256(sass_audit_path),
            "signed_zero_sass": sha256(zero_closure_sass),
            "signed_zero_sass_audit": sha256(zero_closure_sass_audit),
            "ptx_audit": sha256(closure_ptx_audit),
            "signed_zero_ptx_audit": sha256(zero_closure_ptx_audit),
            "cubin": sha256(cubin_path),
            "signed_zero_cubin": sha256(zero_cubin),
            "generator_executable": sha256(args.generator.resolve()),
            "generated_driver_executable": sha256(args.driver.resolve()),
            "phase4_expression_runner": sha256(args.phase4.resolve()),
            "nvdisasm_executable": sha256(Path(nvdisasm).resolve()),
            "ptxas_executable": sha256(Path(ptxas).resolve()),
            "conformance_harness": sha256(
                ROOT / "tools/run_generated_ptx_conformance.py"
            ),
            "acceptance_closure_tool": sha256(
                ROOT / "tools/close_generated_ptx_acceptance.py"
            ),
            "ptx_audit_tool": sha256(ROOT / "tools/inspect_generated_ptx.py"),
            "sass_audit_tool": sha256(ROOT / "tools/inspect_generated_sass.py"),
            "reference_evaluator": sha256(ROOT / "reference/evaluator.py"),
            "reference_binary64": sha256(ROOT / "reference/exact_binary64.py"),
            "reference_format": sha256(ROOT / "reference/format.py"),
        },
    }
    report["strong_acceptance"] = closure
    report["accepted"] = report["accepted"] and passed
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(closure, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, wire.FormatError) as error:
        print(f"generated PTX acceptance closure failed: {error}", file=sys.stderr)
        raise SystemExit(1)
