#!/usr/bin/env python3
"""Exact bit-for-bit conformance for the CUDA interval-expression batch.

Each invocation creates several deterministic bounded postfix programs and a
batch of independently generated finite interval rows for each program.  The
GPU output for every program/row case is compared with operations from
``reference.exact_binary64``; Python native floating point is never used to
decide an expected endpoint.

``--count`` counts randomized program/row cases across the randomized program
suite.  Curated edge rows are additional and reported separately.  The default
is a development-sized run.  The Phase 4 acceptance-scale path is explicit:

    python3 tools/run_expression_conformance.py --count 1000000

That command still performs exact-reference evaluation of all cases, so host
reference time is expected to dominate GPU kernel time.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import time
from typing import BinaryIO, Iterable, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from reference import exact_binary64 as exact  # noqa: E402
from tools import inspect_expression_ptx  # noqa: E402
from tg_verifier.campaign_io import (  # noqa: E402
    MeasuredWorkerScopeError,
    require_azure_measured_worker_for_workload,
)


FORMAT_VERSION = 1
INPUT_MAGIC = b"SIE64I01"
OUTPUT_MAGIC = b"SIE64O01"
HEADER = struct.Struct("<8sIIIIQ")
INSTRUCTION = struct.Struct("<BBHIQQ")
INTERVAL = struct.Struct("<QQ")
OUTPUT = struct.Struct("<QQB7s")
MAX_INSTRUCTIONS = 256
MAX_VARIABLES = 64
MAX_STACK_DEPTH = 32
MAX_POW_EXPONENT = 64
MAX_ROWS = 1_000_000
MAX_INPUT_FILE_BYTES = 1 << 28
STATUS_VALID = 0
STATUS_DIVISOR_CONTAINS_ZERO = 1
STATUS_NONFINITE_INTERMEDIATE_WIDENING = 2
MAX_REPORTED_MISMATCHES = 20

OPCODES = {
    "const": 1,
    "var": 2,
    "neg": 3,
    "add": 4,
    "sub": 5,
    "mul": 6,
    "div": 7,
    "abs": 8,
    "min": 9,
    "max": 10,
    "pow_nat": 11,
}
UNARY_OPERATIONS = {"neg", "abs", "pow_nat"}
BINARY_OPERATIONS = {"add", "sub", "mul", "div", "min", "max"}


@dataclass(frozen=True, slots=True)
class Instruction:
    op: str
    argument: int = 0
    lo_bits: int = 0
    hi_bits: int = 0


@dataclass(frozen=True, slots=True)
class Program:
    name: str
    variable_count: int
    instructions: tuple[Instruction, ...]


IntervalValue = exact.Binary64Interval
Row = tuple[IntervalValue, ...]


SPECIAL_INTERVALS: tuple[IntervalValue, ...] = (
    IntervalValue(exact.POSITIVE_ZERO, exact.POSITIVE_ZERO),
    IntervalValue(exact.NEGATIVE_ZERO, exact.NEGATIVE_ZERO),
    IntervalValue(exact.NEGATIVE_ZERO, exact.POSITIVE_ZERO),
    IntervalValue(0x8000000000000001, 0x0000000000000001),
    IntervalValue(0x800FFFFFFFFFFFFF, 0x000FFFFFFFFFFFFF),
    IntervalValue(0xBFF0000000000000, 0x3FF0000000000000),
    IntervalValue(0x3FF0000000000000, 0x3FF0000000000001),
    IntervalValue(0xBFF0000000000001, 0xBFF0000000000000),
    IntervalValue(exact.MAX_FINITE, exact.MAX_FINITE),
    IntervalValue(exact.MIN_FINITE, exact.MIN_FINITE),
    IntervalValue(0x0010000000000000, 0x0010000000000001),
    IntervalValue(0x8010000000000001, 0x8010000000000000),
)
CARTESIAN_POINT_INTERVALS: tuple[IntervalValue, ...] = (
    IntervalValue(exact.POSITIVE_ZERO, exact.POSITIVE_ZERO),
    IntervalValue(exact.NEGATIVE_ZERO, exact.NEGATIVE_ZERO),
    IntervalValue(exact.MIN_POSITIVE_SUBNORMAL, exact.MIN_POSITIVE_SUBNORMAL),
    IntervalValue(
        exact.SIGN_MASK | exact.MIN_POSITIVE_SUBNORMAL,
        exact.SIGN_MASK | exact.MIN_POSITIVE_SUBNORMAL,
    ),
    IntervalValue(exact.MAX_FINITE, exact.MAX_FINITE),
    IntervalValue(exact.MIN_FINITE, exact.MIN_FINITE),
)
CARTESIAN_PROGRAM_NAMES = {"add", "sub", "mul", "div", "min", "max"}


def const(lo_bits: int, hi_bits: int | None = None) -> Instruction:
    if hi_bits is None:
        hi_bits = lo_bits
    # Construction also checks non-NaN ordering.
    IntervalValue(lo_bits, hi_bits)
    if not exact.is_finite(lo_bits) or not exact.is_finite(hi_bits):
        raise ValueError("wire constants require finite endpoints")
    return Instruction("const", lo_bits=lo_bits, hi_bits=hi_bits)


def var(index: int) -> Instruction:
    return Instruction("var", argument=index)


def op(name: str, argument: int = 0) -> Instruction:
    if name not in UNARY_OPERATIONS | BINARY_OPERATIONS:
        raise ValueError(f"unsupported operation {name!r}")
    return Instruction(name, argument=argument)


def validated_max_stack(program: Program) -> int:
    if not 0 <= program.variable_count <= MAX_VARIABLES:
        raise ValueError("variable_count is outside the wire limit")
    if not 1 <= len(program.instructions) <= MAX_INSTRUCTIONS:
        raise ValueError("instruction count is outside the wire limit")
    depth = 0
    maximum = 0
    for pc, instruction in enumerate(program.instructions):
        if instruction.op not in OPCODES:
            raise ValueError(f"instruction {pc} has unsupported opcode")
        if instruction.op == "const":
            if instruction.argument != 0:
                raise ValueError(f"instruction {pc} has a constant argument")
            if not exact.is_finite(instruction.lo_bits) or not exact.is_finite(
                instruction.hi_bits
            ):
                raise ValueError(f"instruction {pc} constant is nonfinite")
            IntervalValue(instruction.lo_bits, instruction.hi_bits)
            depth += 1
        elif instruction.op == "var":
            if instruction.lo_bits != 0 or instruction.hi_bits != 0:
                raise ValueError(f"instruction {pc} variable has endpoint payload")
            if not 0 <= instruction.argument < program.variable_count:
                raise ValueError(f"instruction {pc} variable index is out of range")
            depth += 1
        elif instruction.op in UNARY_OPERATIONS:
            if instruction.lo_bits != 0 or instruction.hi_bits != 0:
                raise ValueError(f"instruction {pc} unary has endpoint payload")
            if instruction.op != "pow_nat" and instruction.argument != 0:
                raise ValueError(f"instruction {pc} unary has an argument")
            if instruction.op == "pow_nat" and not (
                0 <= instruction.argument <= MAX_POW_EXPONENT
            ):
                raise ValueError(f"instruction {pc} exponent is out of range")
            if depth < 1:
                raise ValueError(f"instruction {pc} underflows the stack")
        else:
            if (
                instruction.argument != 0
                or instruction.lo_bits != 0
                or instruction.hi_bits != 0
            ):
                raise ValueError(f"instruction {pc} binary has a payload")
            if depth < 2:
                raise ValueError(f"instruction {pc} underflows the stack")
            depth -= 1
        maximum = max(maximum, depth)
        if maximum > MAX_STACK_DEPTH:
            raise ValueError("program exceeds the fixed stack")
    if depth != 1:
        raise ValueError("program does not finish with one stack value")
    return maximum


def instruction_bytes(instruction: Instruction) -> bytes:
    return INSTRUCTION.pack(
        OPCODES[instruction.op],
        0,
        0,
        instruction.argument,
        instruction.lo_bits,
        instruction.hi_bits,
    )


def encoded_program(program: Program) -> bytes:
    validated_max_stack(program)
    return b"".join(instruction_bytes(instruction) for instruction in program.instructions)


def write_input(path: Path, program: Program, rows: Sequence[Row]) -> None:
    if not rows:
        raise ValueError("row batch must not be empty")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"row batch exceeds the {MAX_ROWS}-row wire limit")
    maximum_stack = validated_max_stack(program)
    encoded_size = (
        HEADER.size
        + len(program.instructions) * INSTRUCTION.size
        + len(rows) * program.variable_count * INTERVAL.size
    )
    if encoded_size > MAX_INPUT_FILE_BYTES:
        raise ValueError("encoded input exceeds the 256 MiB resource limit")
    with path.open("wb") as output:
        output.write(
            HEADER.pack(
                INPUT_MAGIC,
                FORMAT_VERSION,
                len(program.instructions),
                program.variable_count,
                maximum_stack,
                len(rows),
            )
        )
        for instruction in program.instructions:
            output.write(instruction_bytes(instruction))
        chunk = bytearray()
        for row_index, row in enumerate(rows):
            if len(row) != program.variable_count:
                raise ValueError(
                    f"row {row_index} has {len(row)} variables; "
                    f"expected {program.variable_count}"
                )
            for interval in row:
                if not interval.has_finite_endpoints:
                    raise ValueError("input rows require finite endpoints")
                chunk += INTERVAL.pack(interval.lo, interval.hi)
                if len(chunk) >= 1 << 20:
                    output.write(chunk)
                    chunk.clear()
        output.write(chunk)


def _read_header(
    stream: BinaryIO, expected_magic: bytes
) -> tuple[int, int, int, int]:
    encoded = stream.read(HEADER.size)
    if len(encoded) != HEADER.size:
        raise ValueError("file is shorter than its header")
    magic, version, instruction_count, variable_count, max_stack, row_count = (
        HEADER.unpack(encoded)
    )
    if magic != expected_magic:
        raise ValueError(f"wrong magic {magic!r}")
    if version != FORMAT_VERSION:
        raise ValueError(f"unsupported format version {version}")
    return instruction_count, variable_count, max_stack, row_count


def evaluate_program(program: Program, row: Row) -> tuple[int, int, int]:
    """Evaluate using only the exact binary64 reference operations."""

    stack: list[IntervalValue] = []
    try:
        for instruction in program.instructions:
            operation = instruction.op
            if operation == "const":
                stack.append(IntervalValue(instruction.lo_bits, instruction.hi_bits))
            elif operation == "var":
                stack.append(row[instruction.argument])
            elif operation == "neg":
                stack.append(exact.interval_neg(stack.pop()))
            elif operation == "abs":
                stack.append(exact.interval_abs(stack.pop()))
            elif operation == "pow_nat":
                value = stack.pop()
                one = IntervalValue(0x3FF0000000000000, 0x3FF0000000000000)
                result = one
                for _ in range(instruction.argument):
                    if not result.has_finite_endpoints or not value.has_finite_endpoints:
                        return (
                            exact.NEGATIVE_INFINITY,
                            exact.POSITIVE_INFINITY,
                            STATUS_NONFINITE_INTERMEDIATE_WIDENING,
                        )
                    result = exact.interval_mul(result, value)
                stack.append(result)
            else:
                right = stack.pop()
                left = stack.pop()
                if operation == "div" and right.contains_zero():
                    return 0, 0, STATUS_DIVISOR_CONTAINS_ZERO
                if operation in {"add", "sub", "mul", "div"} and (
                    not left.has_finite_endpoints or not right.has_finite_endpoints
                ):
                    return (
                        exact.NEGATIVE_INFINITY,
                        exact.POSITIVE_INFINITY,
                        STATUS_NONFINITE_INTERMEDIATE_WIDENING,
                    )
                function = {
                    "add": exact.interval_add,
                    "sub": exact.interval_sub,
                    "mul": exact.interval_mul,
                    "div": exact.interval_div,
                    "min": exact.interval_min,
                    "max": exact.interval_max,
                }[operation]
                stack.append(function(left, right))
    except exact.InvalidBinary64Operation:
        return 0, 0, STATUS_DIVISOR_CONTAINS_ZERO
    if len(stack) != 1:
        raise AssertionError("validated program produced the wrong stack depth")
    return stack[0].lo, stack[0].hi, STATUS_VALID


def curated_programs() -> list[Program]:
    one = 0x3FF0000000000000
    min_subnormal = exact.MIN_POSITIVE_SUBNORMAL
    return [
        Program("constant", 0, (const(exact.NEGATIVE_ZERO, exact.POSITIVE_ZERO),)),
        Program("identity", 1, (var(0),)),
        Program("neg", 1, (var(0), op("neg"))),
        Program("abs", 1, (var(0), op("abs"))),
        Program("add", 2, (var(0), var(1), op("add"))),
        Program("sub", 2, (var(0), var(1), op("sub"))),
        Program("mul", 2, (var(0), var(1), op("mul"))),
        Program("div", 2, (var(0), var(1), op("div"))),
        Program("min", 2, (var(0), var(1), op("min"))),
        Program("max", 2, (var(0), var(1), op("max"))),
        Program("pow_zero", 1, (var(0), op("pow_nat", 0))),
        Program("pow_three", 1, (var(0), op("pow_nat", 3))),
        Program("pow_64_boundary", 1, (var(0), op("pow_nat", 64))),
        Program(
            "stack_32_boundary",
            32,
            tuple(var(index) for index in range(32))
            + tuple(op("add") for _ in range(31)),
        ),
        Program(
            "overflow_final",
            0,
            (const(exact.MAX_FINITE), const(exact.MAX_FINITE), op("add")),
        ),
        Program(
            "overflow_then_add",
            0,
            (
                const(exact.MAX_FINITE),
                const(exact.MAX_FINITE),
                op("add"),
                const(one),
                op("add"),
            ),
        ),
        Program(
            "pow_overflow_widening",
            0,
            (const(exact.MAX_FINITE), op("pow_nat", 3)),
        ),
        Program(
            "mixed",
            3,
            (
                var(0),
                var(1),
                op("sub"),
                op("abs"),
                var(2),
                const(min_subnormal, one),
                op("max"),
                op("div"),
                var(0),
                op("neg"),
                op("add"),
            ),
        ),
    ]


def _random_leaf(generator: random.Random, variable_count: int) -> list[Instruction]:
    if generator.random() < 0.78:
        return [var(generator.randrange(variable_count))]
    interval = SPECIAL_INTERVALS[generator.randrange(len(SPECIAL_INTERVALS))]
    return [const(interval.lo, interval.hi)]


def _random_expression(
    generator: random.Random, variable_count: int, depth: int
) -> list[Instruction]:
    if depth <= 0 or generator.random() < 0.22:
        return _random_leaf(generator, variable_count)
    choice = generator.random()
    if choice < 0.20:
        unary = generator.choice(("neg", "abs", "pow_nat"))
        result = _random_expression(generator, variable_count, depth - 1)
        exponent = generator.choice((0, 1, 2, 3, 4)) if unary == "pow_nat" else 0
        result.append(op(unary, exponent))
        return result
    binary = generator.choice(tuple(sorted(BINARY_OPERATIONS)))
    return (
        _random_expression(generator, variable_count, depth - 1)
        + _random_expression(generator, variable_count, depth - 1)
        + [op(binary)]
    )


def randomized_programs(count: int, seed: int) -> list[Program]:
    programs: list[Program] = []
    for index in range(count):
        generator = random.Random(seed ^ 0xE7A0_0000_0000_0000 ^ index)
        variable_count = generator.randint(1, 4)
        depth = generator.randint(2, 5)
        instructions = tuple(_random_expression(generator, variable_count, depth))
        program = Program(f"random_{index:03d}", variable_count, instructions)
        validated_max_stack(program)
        programs.append(program)
    return programs


def _finite_random_bits(generator: random.Random) -> int:
    if generator.random() < 0.18:
        interval = SPECIAL_INTERVALS[generator.randrange(len(SPECIAL_INTERVALS))]
        return generator.choice((interval.lo, interval.hi))
    bits = generator.getrandbits(64)
    if not exact.is_finite(bits):
        bits ^= 0x0010000000000000
    return bits


def _ordered_interval(left: int, right: int) -> IntervalValue:
    try:
        return IntervalValue(left, right)
    except ValueError:
        return IntervalValue(right, left)


def _random_interval(generator: random.Random) -> IntervalValue:
    first = _finite_random_bits(generator)
    mode = generator.randrange(5)
    if mode == 0:
        return IntervalValue(first, first)
    if mode == 1:
        adjacent = exact.next_up_bits(first)
        if not exact.is_finite(adjacent):
            adjacent = first
        return _ordered_interval(first, adjacent)
    if mode == 2:
        return SPECIAL_INTERVALS[generator.randrange(len(SPECIAL_INTERVALS))]
    second = _finite_random_bits(generator)
    return _ordered_interval(first, second)


def rows_for_program(program: Program, random_count: int, seed: int) -> list[Row]:
    rows: list[Row] = []
    # Fixed rows rotate the edge interval catalog through each variable column.
    for row_index in range(len(SPECIAL_INTERVALS)):
        rows.append(
            tuple(
                SPECIAL_INTERVALS[(row_index + 3 * column) % len(SPECIAL_INTERVALS)]
                for column in range(program.variable_count)
            )
        )
    if program.name in CARTESIAN_PROGRAM_NAMES:
        if program.variable_count != 2:
            raise AssertionError("Cartesian boundary program must have two variables")
        rows.extend(
            (left, right)
            for left in CARTESIAN_POINT_INTERVALS
            for right in CARTESIAN_POINT_INTERVALS
        )
    generator = random.Random(seed ^ 0xB47C_0000_0000_0000 ^ hash_name(program.name))
    for _ in range(random_count):
        rows.append(
            tuple(_random_interval(generator) for _ in range(program.variable_count))
        )
    return rows


def hash_name(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode("ascii")).digest()[:8], "little")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_report_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def audit_device_artifacts(
    executable: Path, work_dir: Path, expected_target: str = "sm_121"
) -> dict[str, object]:
    """Bind conformance to the executable, extracted PTX, and audited SASS."""

    ptx_report = inspect_expression_ptx.audit_binary(
        executable, expected_target=expected_target
    )
    if not ptx_report["passed"]:
        raise RuntimeError(
            "strict expression PTX audit failed: "
            + json.dumps(ptx_report, sort_keys=True)
        )

    sass_path = work_dir / "expression-device.sass"
    sass_audit_path = work_dir / "expression-sass-audit.json"
    extracted = subprocess.run(
        ["cuobjdump", "--dump-sass", str(executable)],
        capture_output=True,
        check=False,
    )
    if extracted.returncode != 0 or not extracted.stdout:
        message = extracted.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"cuobjdump --dump-sass failed with exit {extracted.returncode}: {message}"
        )
    sass_path.write_bytes(extracted.stdout)
    inspected = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "tools/inspect_sass.py"),
            str(sass_path),
            str(sass_audit_path),
            "--allow-division-lowering",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if inspected.returncode != 0:
        raise RuntimeError(
            f"SASS inspection failed with exit {inspected.returncode}: "
            f"{inspected.stderr.strip()}"
        )
    sass_report = json.loads(sass_audit_path.read_text(encoding="utf-8"))
    if not sass_report["passed"]:
        raise RuntimeError("SASS inspection returned a non-passing report")
    return {
        "executable_sha256": sha256_file(executable),
        "ptx": {
            "extracted_ptx_sha256": ptx_report["input_sha256"],
            "audit_report_sha256": _canonical_report_sha256(ptx_report),
            "passed": ptx_report["passed"],
            "targets": ptx_report["targets"],
            "entries": ptx_report["entries"],
            "instruction_count": ptx_report["instruction_count"],
            "required_directed_rounding_counts": ptx_report[
                "required_directed_rounding_counts"
            ],
            "local_stack_bytes": ptx_report["local_stack_bytes"],
        },
        "sass": {
            "extracted_sass_sha256": hashlib.sha256(extracted.stdout).hexdigest(),
            "audit_report_sha256": _canonical_report_sha256(sass_report),
            "passed": sass_report["passed"],
            "targets": sass_report["targets"],
            "functions": sass_report["functions"],
            "instruction_count": sass_report["instruction_count"],
            "findings": sass_report["findings"],
            "permitted_compiler_division_lowering": sass_report[
                "permitted_compiler_division_lowering"
            ],
        },
    }


def validate_device_identity(
    report: dict[str, object], expected_target: str
) -> None:
    name = report.get("device_name")
    capability = report.get("compute_capability")
    if expected_target == "sm_121":
        accepted = name == "NVIDIA GB10" and capability == "12.1"
    elif expected_target == "sm_90":
        accepted = (
            isinstance(name, str) and "H100" in name and capability == "9.0"
        )
    else:
        raise RuntimeError(f"unsupported expression target {expected_target!r}")
    if not accepted:
        raise RuntimeError(
            "CUDA runner device identity does not match target "
            f"{expected_target}: name={name!r}, capability={capability!r}"
        )


def compare_output(
    output_path: Path, program: Program, rows: Sequence[Row]
) -> dict[str, object]:
    mismatches: list[dict[str, object]] = []
    mismatch_count = 0
    valid_rows = 0
    divisor_rows = 0
    widening_rows = 0
    start = time.perf_counter()
    with output_path.open("rb") as output:
        metadata = _read_header(output, OUTPUT_MAGIC)
        expected_metadata = (
            len(program.instructions),
            program.variable_count,
            validated_max_stack(program),
            len(rows),
        )
        if metadata != expected_metadata:
            raise ValueError(
                f"output metadata {metadata} differs from expected {expected_metadata}"
            )
        for index, row in enumerate(rows):
            encoded = output.read(OUTPUT.size)
            if len(encoded) != OUTPUT.size:
                raise ValueError(f"output truncated at row {index}")
            actual_lo, actual_hi, actual_status, reserved = OUTPUT.unpack(encoded)
            expected_lo, expected_hi, expected_status = evaluate_program(program, row)
            if expected_status == STATUS_VALID:
                valid_rows += 1
            elif expected_status == STATUS_DIVISOR_CONTAINS_ZERO:
                divisor_rows += 1
            else:
                widening_rows += 1
            row_mismatch = (
                actual_lo != expected_lo
                or actual_hi != expected_hi
                or actual_status != expected_status
                or reserved != bytes(7)
            )
            if row_mismatch:
                mismatch_count += 1
                if len(mismatches) < MAX_REPORTED_MISMATCHES:
                    mismatches.append(
                        {
                            "row": index,
                            "expected_lo": f"{expected_lo:016x}",
                            "actual_lo": f"{actual_lo:016x}",
                            "expected_hi": f"{expected_hi:016x}",
                            "actual_hi": f"{actual_hi:016x}",
                            "expected_status": expected_status,
                            "actual_status": actual_status,
                            "reserved_zero": reserved == bytes(7),
                        }
                    )
        if output.read(1):
            raise ValueError("output has trailing data")
    elapsed = time.perf_counter() - start
    return {
        "rows": len(rows),
        "valid_rows_compared": valid_rows,
        "zero_divisor_rows_checked": divisor_rows,
        "nonfinite_widening_rows_checked": widening_rows,
        "reference_comparison_seconds": elapsed,
        "reference_rows_per_second": len(rows) / elapsed if elapsed else 0.0,
        "mismatch_count": mismatch_count,
        "mismatch_details_capped_at": MAX_REPORTED_MISMATCHES,
        "mismatches": mismatches,
        "passed": mismatch_count == 0,
    }


def run_one(
    executable: Path,
    work_dir: Path,
    program: Program,
    rows: Sequence[Row],
    device: int,
    allow_other_device: bool,
) -> dict[str, object]:
    input_path = work_dir / f"{program.name}.input.bin"
    output_path = work_dir / f"{program.name}.output.bin"
    write_input(input_path, program, rows)
    command = [
        str(executable),
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--device",
        str(device),
    ]
    if allow_other_device:
        command.append("--allow-other-device")
    host_start = time.perf_counter()
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    host_elapsed = time.perf_counter() - host_start
    if completed.returncode != 0:
        raise RuntimeError(
            f"CUDA runner failed for {program.name} with exit "
            f"{completed.returncode}: {completed.stderr.strip()}"
        )
    try:
        device_report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"CUDA runner emitted invalid JSON: {exc}") from exc
    comparison = compare_output(output_path, program, rows)
    expected_counts = {
        "valid_row_count": comparison["valid_rows_compared"],
        "zero_divisor_row_count": comparison["zero_divisor_rows_checked"],
        "nonfinite_widening_row_count": comparison[
            "nonfinite_widening_rows_checked"
        ],
    }
    for field, expected_count in expected_counts.items():
        if device_report.get(field) != expected_count:
            raise RuntimeError(
                f"CUDA runner {field}={device_report.get(field)!r}, "
                f"exact comparison requires {expected_count}"
            )
    return {
        "instruction_count": len(program.instructions),
        "variable_count": program.variable_count,
        "max_stack_depth": validated_max_stack(program),
        "program_sha256": hashlib.sha256(encoded_program(program)).hexdigest(),
        "input_sha256": sha256_file(input_path),
        "output_sha256": sha256_file(output_path),
        "host_gpu_run_seconds": host_elapsed,
        "host_gpu_rows_per_second": len(rows) / host_elapsed if host_elapsed else 0.0,
        "device_report": device_report,
        "comparison": comparison,
    }


def verify_output_determinism(
    executable: Path,
    work_dir: Path,
    program: Program,
    device: int,
    allow_other_device: bool,
    first_output_sha256: str,
    expected_target: str = "sm_121",
) -> dict[str, object]:
    """Replay one identical binary input and compare the raw output bytes."""

    input_path = work_dir / f"{program.name}.input.bin"
    replay_path = work_dir / f"{program.name}.replay.output.bin"
    command = [
        str(executable),
        "--input",
        str(input_path),
        "--output",
        str(replay_path),
        "--device",
        str(device),
    ]
    if allow_other_device:
        command.append("--allow-other-device")
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"determinism replay failed for {program.name} with exit "
            f"{completed.returncode}: {completed.stderr.strip()}"
        )
    try:
        device_report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"determinism replay emitted invalid JSON: {exc}"
        ) from exc
    if not isinstance(device_report, dict):
        raise RuntimeError("determinism replay emitted a non-object JSON report")
    validate_device_identity(device_report, expected_target)
    replay_sha256 = sha256_file(replay_path)
    passed = replay_sha256 == first_output_sha256
    return {
        "program": program.name,
        "input_sha256": sha256_file(input_path),
        "first_output_sha256": first_output_sha256,
        "replay_output_sha256": replay_sha256,
        "passed": passed,
    }


def _raw_input(
    path: Path,
    instructions: bytes,
    *,
    instruction_count: int,
    variable_count: int,
    max_stack: int,
    row_count: int = 1,
    row_payload: bytes = b"",
) -> None:
    path.write_bytes(
        HEADER.pack(
            INPUT_MAGIC,
            FORMAT_VERSION,
            instruction_count,
            variable_count,
            max_stack,
            row_count,
        )
        + instructions
        + row_payload
    )


def verify_host_rejections(executable: Path, work_dir: Path) -> dict[str, object]:
    """Require malformed programs to fail before CUDA device initialization."""

    zero_instruction = INSTRUCTION.pack(OPCODES["const"], 0, 0, 0, 0, 0)
    malformed: list[tuple[str, bytes, int, int, int, bytes]] = [
        (
            "unknown_opcode",
            INSTRUCTION.pack(255, 0, 0, 0, 0, 0),
            1,
            0,
            1,
            b"",
        ),
        (
            "stack_underflow",
            INSTRUCTION.pack(OPCODES["add"], 0, 0, 0, 0, 0),
            1,
            0,
            1,
            b"",
        ),
        (
            "nonzero_reserved",
            INSTRUCTION.pack(OPCODES["const"], 1, 0, 0, 0, 0),
            1,
            0,
            1,
            b"",
        ),
        (
            "wrong_stack_metadata",
            zero_instruction,
            1,
            0,
            2,
            b"",
        ),
        (
            "nonfinite_constant",
            INSTRUCTION.pack(
                OPCODES["const"], 0, 0, 0, exact.POSITIVE_INFINITY, exact.POSITIVE_INFINITY
            ),
            1,
            0,
            1,
            b"",
        ),
        (
            "decreasing_row_interval",
            INSTRUCTION.pack(OPCODES["var"], 0, 0, 0, 0, 0),
            1,
            1,
            1,
            INTERVAL.pack(0x3FF0000000000000, 0xBFF0000000000000),
        ),
        (
            "trailing_data",
            zero_instruction,
            1,
            0,
            1,
            b"\x00",
        ),
        (
            "row_count_limit",
            zero_instruction,
            1,
            0,
            1,
            b"",
        ),
    ]
    rejected: list[str] = []
    for name, instructions, count, variables, stack, row_payload in malformed:
        input_path = work_dir / f"malformed-{name}.bin"
        output_path = work_dir / f"malformed-{name}.output.bin"
        _raw_input(
            input_path,
            instructions,
            instruction_count=count,
            variable_count=variables,
            max_stack=stack,
            row_count=MAX_ROWS + 1 if name == "row_count_limit" else 1,
            row_payload=row_payload,
        )
        completed = subprocess.run(
            [
                str(executable),
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 2:
            raise RuntimeError(
                f"malformed case {name} returned {completed.returncode}, expected 2; "
                f"stderr={completed.stderr.strip()!r}"
            )
        if output_path.exists():
            raise RuntimeError(f"malformed case {name} created an output file")
        rejected.append(name)
    return {"count": len(rejected), "cases": rejected, "passed": True}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--executable",
        type=Path,
        default=REPOSITORY_ROOT / "build/dgx-spark/sparkinterval-expression-batch",
    )
    parser.add_argument(
        "--target",
        choices=("sm_121", "sm_90"),
        default="sm_121",
        help="required device-code and hardware target (default: sm_121)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10_000,
        help="randomized expression/row cases in total (use 1000000 for acceptance scale)",
    )
    parser.add_argument(
        "--program-count",
        type=int,
        default=8,
        help="number of deterministic randomized shared programs",
    )
    parser.add_argument("--seed", type=int, default=0x71E5A17)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--allow-other-device", action="store_true")
    parser.add_argument(
        "--work-dir", type=Path, help="retain deterministic input/output files"
    )
    args = parser.parse_args(argv)
    if args.count < 0:
        parser.error("--count must be nonnegative")
    if args.program_count <= 0:
        parser.error("--program-count must be positive")
    if args.device < 0:
        parser.error("--device must be nonnegative")
    if args.target == "sm_90" and args.allow_other_device:
        parser.error("--allow-other-device is forbidden for the strict sm_90 path")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        require_azure_measured_worker_for_workload(
            exact_production=False,
            work_bounds=(args.count,),
        )
    except MeasuredWorkerScopeError as error:
        print(error, file=sys.stderr)
        return 2
    executable = args.executable.resolve()
    if not executable.is_file():
        print(f"CUDA runner does not exist: {executable}", file=sys.stderr)
        return 2

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.work_dir is None:
        temporary = tempfile.TemporaryDirectory(prefix="sparkinterval-expression-")
        work_dir = Path(temporary.name)
    else:
        work_dir = args.work_dir.resolve()
        work_dir.mkdir(parents=True, exist_ok=True)

    try:
        device_artifacts = audit_device_artifacts(
            executable, work_dir, args.target
        )
        host_validation = verify_host_rejections(executable, work_dir)
        curated = curated_programs()
        randomized = randomized_programs(args.program_count, args.seed)
        cases: list[tuple[Program, int]] = [(program, 0) for program in curated]
        quotient, remainder = divmod(args.count, len(randomized))
        cases.extend(
            (program, quotient + (1 if index < remainder else 0))
            for index, program in enumerate(randomized)
        )

        reports: dict[str, object] = {}
        accepted = True
        total_rows = 0
        total_kernel_milliseconds = 0.0
        total_reference_seconds = 0.0
        for index, (program, random_rows) in enumerate(cases):
            rows = rows_for_program(program, random_rows, args.seed)
            print(
                f"[{index + 1}/{len(cases)}] {program.name}: "
                f"{len(program.instructions)} instructions, {len(rows)} rows",
                file=sys.stderr,
            )
            report = run_one(
                executable,
                work_dir,
                program,
                rows,
                args.device,
                args.allow_other_device,
            )
            reports[program.name] = report
            comparison = report["comparison"]
            device_report = report["device_report"]
            assert isinstance(comparison, dict)
            assert isinstance(device_report, dict)
            validate_device_identity(device_report, args.target)
            accepted = accepted and bool(comparison["passed"])
            total_rows += int(comparison["rows"])
            total_reference_seconds += float(comparison["reference_comparison_seconds"])
            total_kernel_milliseconds += float(device_report["kernel_milliseconds"])

        replay_program = randomized[0]
        replay_report = reports[replay_program.name]
        assert isinstance(replay_report, dict)
        determinism = verify_output_determinism(
            executable,
            work_dir,
            replay_program,
            args.device,
            args.allow_other_device,
            str(replay_report["output_sha256"]),
            args.target,
        )
        accepted = accepted and bool(determinism["passed"])

        report: dict[str, object] = {
            "schema_version": 1,
            "kind": "sparkinterval_cuda_expression_conformance",
            "target": args.target,
            "seed": args.seed,
            "requested_random_expression_rows": args.count,
            "randomized_program_count": len(randomized),
            "curated_program_count": len(curated),
            "curated_base_rows_per_program": len(SPECIAL_INTERVALS),
            "cartesian_boundary_rows_per_basic_binary_program": len(
                CARTESIAN_POINT_INTERVALS
            )
            ** 2,
            "total_program_row_cases": total_rows,
            "host_validation": host_validation,
            "device_artifacts": device_artifacts,
            "determinism_replay": determinism,
            "aggregate": {
                "kernel_milliseconds_sum_across_launches": total_kernel_milliseconds,
                "kernel_rows_per_second_from_summed_times": (
                    total_rows * 1000.0 / total_kernel_milliseconds
                    if total_kernel_milliseconds
                    else 0.0
                ),
                "exact_reference_seconds": total_reference_seconds,
                "exact_reference_rows_per_second": (
                    total_rows / total_reference_seconds
                    if total_reference_seconds
                    else 0.0
                ),
            },
            "programs": reports,
            "accepted": accepted,
            "acceptance_basis": (
                "bit-for-bit exact_binary64 comparison of every valid endpoint, "
                "dynamic zero-divisor status checks, zeroed reserved bytes, and "
                "host-side rejection of malformed postfix programs; one identical "
                "binary input is also replayed for byte-identical raw output"
            ),
        }
        if args.work_dir is not None:
            report["work_dir"] = str(work_dir)
        print(json.dumps(report, sort_keys=True, indent=2))
        return 0 if accepted else 1
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
