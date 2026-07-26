#!/usr/bin/env python3
"""Bit-for-bit CUDA primitive conformance and throughput harness.

The GPU receives raw binary64 words through the fixed-width little-endian
protocol documented in ``gpu/include/interval_batch.h``.  Every valid output
is compared with ``reference.exact_binary64``; invalid input statuses are also
checked.  No Python native floating-point arithmetic participates in expected
result generation.

``--count`` is the number of pseudorandom finite rows *per operation*.  The
default is suitable for a quick development check.  A five-million-row run is
requested explicitly with ``--count 5000000``; it still performs the full
exact-reference comparison and can therefore take much longer than the GPU
kernel itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import time
from typing import BinaryIO, Iterable, Iterator


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from reference import exact_binary64 as exact  # noqa: E402
from tg_verifier.campaign_io import (  # noqa: E402
    MeasuredWorkerScopeError,
    require_azure_measured_worker_for_workload,
)


FORMAT_VERSION = 1
INPUT_MAGIC = b"SIB64I01"
OUTPUT_MAGIC = b"SIB64O01"
HEADER = struct.Struct("<8sIIQ")
INPUT_ROW = struct.Struct("<QQ")
OUTPUT_ROW = struct.Struct("<QQB7s")
OPERATIONS = {"add": 1, "sub": 2, "mul": 3, "div": 4}
STATUS_VALID = 0
STATUS_NONFINITE = 1
STATUS_DIVISION_BY_ZERO = 2
MAX_REPORTED_MISMATCHES = 20


CURATED_FINITE_PAIRS: tuple[tuple[int, int], ...] = (
    (0x0000000000000000, 0x0000000000000000),
    (0x8000000000000000, 0x8000000000000000),
    (0x0000000000000000, 0x8000000000000000),
    (0x8000000000000000, 0x0000000000000000),
    (0x3FF0000000000000, 0x3CA0000000000000),  # 1 and 2^-53
    (0x3FF0000000000000, 0x3C90000000000000),  # 1 and 2^-54
    (0xBFF0000000000000, 0xBCA0000000000000),
    (0x3FF0000000000001, 0x3FF0000000000001),
    (0x3FF0000000000000, 0x4008000000000000),  # 1 and 3
    (0xBFF0000000000000, 0x4008000000000000),
    (0x0000000000000001, 0x0000000000000001),
    (0x8000000000000001, 0x0000000000000001),
    (0x000FFFFFFFFFFFFF, 0x0000000000000001),
    (0x0010000000000000, 0x000FFFFFFFFFFFFF),
    (0x7FEFFFFFFFFFFFFF, 0x4000000000000000),
    (0xFFEFFFFFFFFFFFFF, 0x4000000000000000),
    (0x7FEFFFFFFFFFFFFF, 0x7FEFFFFFFFFFFFFF),
    (0xFFEFFFFFFFFFFFFF, 0x7FEFFFFFFFFFFFFF),
    (0x0010000000000000, 0x4000000000000000),
    (0x8010000000000000, 0x4000000000000000),
)

INVALID_PAIRS: tuple[tuple[int, int], ...] = (
    (exact.POSITIVE_INFINITY, 0x3FF0000000000000),
    (exact.NEGATIVE_INFINITY, 0x3FF0000000000000),
    (0x7FF8000000000000, 0x3FF0000000000000),
    (0x7FF0000000000001, 0x3FF0000000000000),
    (0x3FF0000000000000, exact.POSITIVE_INFINITY),
    (0x3FF0000000000000, 0xFFF8000000000000),
)

REFERENCE_FUNCTIONS = {
    "add": (exact.add_down, exact.add_up),
    "sub": (exact.sub_down, exact.sub_up),
    "mul": (exact.mul_down, exact.mul_up),
    "div": (exact.div_down, exact.div_up),
}


def _finite_random_bits(generator: random.Random) -> int:
    bits = generator.getrandbits(64)
    if (bits & 0x7FF0000000000000) == 0x7FF0000000000000:
        bits ^= 0x0010000000000000
    return bits


def _random_pairs(count: int, seed: int, operation: str) -> Iterator[tuple[int, int]]:
    generator = random.Random(seed ^ (OPERATIONS[operation] << 56))
    for _ in range(count):
        lhs = _finite_random_bits(generator)
        rhs = _finite_random_bits(generator)
        if operation == "div" and exact.is_zero(rhs):
            rhs ^= 1
        yield lhs, rhs


def rows_for_operation(
    operation: str, count: int, seed: int
) -> Iterable[tuple[int, int]]:
    for lhs, rhs in CURATED_FINITE_PAIRS:
        if operation == "div" and exact.is_zero(rhs):
            rhs ^= 1
        yield lhs, rhs
    yield from _random_pairs(count, seed, operation)
    yield from INVALID_PAIRS
    if operation == "div":
        yield 0x3FF0000000000000, exact.POSITIVE_ZERO
        yield 0xBFF0000000000000, exact.NEGATIVE_ZERO


def row_count(operation: str, random_count: int) -> int:
    return (
        len(CURATED_FINITE_PAIRS)
        + random_count
        + len(INVALID_PAIRS)
        + (2 if operation == "div" else 0)
    )


def write_input(
    path: Path, operation: str, random_count: int, seed: int
) -> None:
    total = row_count(operation, random_count)
    with path.open("wb") as output:
        output.write(HEADER.pack(INPUT_MAGIC, FORMAT_VERSION, OPERATIONS[operation], total))
        chunk = bytearray()
        written = 0
        for lhs, rhs in rows_for_operation(operation, random_count, seed):
            chunk += INPUT_ROW.pack(lhs, rhs)
            written += 1
            if len(chunk) >= 1 << 20:
                output.write(chunk)
                chunk.clear()
        output.write(chunk)
    if written != total:
        raise AssertionError(f"generated {written} rows, expected {total}")


def _read_header(stream: BinaryIO, expected_magic: bytes, operation: str) -> int:
    encoded = stream.read(HEADER.size)
    if len(encoded) != HEADER.size:
        raise ValueError("file is shorter than its header")
    magic, version, operation_code, count = HEADER.unpack(encoded)
    if magic != expected_magic:
        raise ValueError(f"wrong magic {magic!r}")
    if version != FORMAT_VERSION:
        raise ValueError(f"unsupported format version {version}")
    if operation_code != OPERATIONS[operation]:
        raise ValueError("operation code does not match requested operation")
    return count


def expected_status(operation: str, lhs: int, rhs: int) -> int:
    if not exact.is_finite(lhs) or not exact.is_finite(rhs):
        return STATUS_NONFINITE
    if operation == "div" and exact.is_zero(rhs):
        return STATUS_DIVISION_BY_ZERO
    return STATUS_VALID


def compare_output(input_path: Path, output_path: Path, operation: str) -> dict[str, object]:
    down_reference, up_reference = REFERENCE_FUNCTIONS[operation]
    mismatches: list[dict[str, object]] = []
    mismatch_count = 0
    valid_rows = 0
    invalid_rows = 0
    start = time.perf_counter()
    with input_path.open("rb") as inputs, output_path.open("rb") as outputs:
        input_count = _read_header(inputs, INPUT_MAGIC, operation)
        output_count = _read_header(outputs, OUTPUT_MAGIC, operation)
        if input_count != output_count:
            raise ValueError(
                f"output row_count {output_count} differs from input {input_count}"
            )
        for index in range(input_count):
            encoded_input = inputs.read(INPUT_ROW.size)
            encoded_output = outputs.read(OUTPUT_ROW.size)
            if len(encoded_input) != INPUT_ROW.size:
                raise ValueError(f"input truncated at row {index}")
            if len(encoded_output) != OUTPUT_ROW.size:
                raise ValueError(f"output truncated at row {index}")
            lhs, rhs = INPUT_ROW.unpack(encoded_input)
            actual_down, actual_up, actual_status, reserved = OUTPUT_ROW.unpack(
                encoded_output
            )
            status = expected_status(operation, lhs, rhs)
            if status == STATUS_VALID:
                valid_rows += 1
                expected_down = down_reference(lhs, rhs)
                expected_up = up_reference(lhs, rhs)
            else:
                invalid_rows += 1
                expected_down = 0
                expected_up = 0
            row_mismatch = (
                actual_status != status
                or actual_down != expected_down
                or actual_up != expected_up
                or reserved != bytes(7)
            )
            if row_mismatch:
                mismatch_count += 1
            if row_mismatch and len(mismatches) < MAX_REPORTED_MISMATCHES:
                mismatches.append(
                    {
                        "row": index,
                        "lhs": f"{lhs:016x}",
                        "rhs": f"{rhs:016x}",
                        "expected_down": f"{expected_down:016x}",
                        "actual_down": f"{actual_down:016x}",
                        "expected_up": f"{expected_up:016x}",
                        "actual_up": f"{actual_up:016x}",
                        "expected_status": status,
                        "actual_status": actual_status,
                        "reserved_zero": reserved == bytes(7),
                    }
                )
        if inputs.read(1):
            raise ValueError("input has trailing data")
        if outputs.read(1):
            raise ValueError("output has trailing data")
    elapsed = time.perf_counter() - start
    return {
        "rows": input_count,
        "valid_rows_compared": valid_rows,
        "invalid_rows_checked": invalid_rows,
        "reference_comparison_seconds": elapsed,
        "reference_rows_per_second": input_count / elapsed if elapsed else 0.0,
        "mismatch_count": mismatch_count,
        "mismatch_details_capped_at": MAX_REPORTED_MISMATCHES,
        "mismatches": mismatches,
        "passed": mismatch_count == 0,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def run_one(
    executable: Path,
    work_dir: Path,
    operation: str,
    random_count: int,
    seed: int,
    device: int,
    allow_other_device: bool,
) -> dict[str, object]:
    input_path = work_dir / f"{operation}.input.bin"
    output_path = work_dir / f"{operation}.output.bin"
    print(f"[{operation}] generating {random_count} random rows", file=sys.stderr)
    write_input(input_path, operation, random_count, seed)
    command = [
        str(executable),
        "--op",
        operation,
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--device",
        str(device),
    ]
    if allow_other_device:
        command.append("--allow-other-device")
    print(f"[{operation}] launching CUDA batch", file=sys.stderr)
    host_start = time.perf_counter()
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    host_elapsed = time.perf_counter() - host_start
    if completed.returncode != 0:
        raise RuntimeError(
            f"CUDA runner failed for {operation} with exit {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    try:
        device_report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"CUDA runner emitted invalid JSON: {exc}") from exc
    print(f"[{operation}] comparing every row with exact reference", file=sys.stderr)
    comparison = compare_output(input_path, output_path, operation)
    total_rows = int(comparison["rows"])
    return {
        "input_sha256": sha256_file(input_path),
        "output_sha256": sha256_file(output_path),
        "host_gpu_run_seconds": host_elapsed,
        "host_gpu_rows_per_second": total_rows / host_elapsed if host_elapsed else 0.0,
        "device_report": device_report,
        "comparison": comparison,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--executable",
        type=Path,
        default=REPOSITORY_ROOT / "build/dgx-spark/sparkinterval-interval-batch",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10_000,
        help="pseudorandom finite rows per operation (use 5000000 for the acceptance-scale path)",
    )
    parser.add_argument("--seed", type=int, default=0x5A17C0DE)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--allow-other-device", action="store_true")
    parser.add_argument(
        "--op",
        dest="operations",
        action="append",
        choices=tuple(OPERATIONS),
        help="operation to run; repeat as needed (default: all four)",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="retain deterministic input/output files in this directory",
    )
    args = parser.parse_args(argv)
    if args.count < 0:
        parser.error("--count must be nonnegative")
    if args.device < 0:
        parser.error("--device must be nonnegative")
    if args.operations is None:
        args.operations = list(OPERATIONS)
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
        temporary = tempfile.TemporaryDirectory(prefix="sparkinterval-conformance-")
        work_dir = Path(temporary.name)
    else:
        work_dir = args.work_dir.resolve()
        work_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, object] = {
        "schema_version": 1,
        "kind": "sparkinterval_cuda_primitive_conformance",
        "seed": args.seed,
        "random_rows_per_operation": args.count,
        "operations": {},
    }
    accepted = True
    try:
        operations_report: dict[str, object] = {}
        for operation in args.operations:
            operation_report = run_one(
                executable,
                work_dir,
                operation,
                args.count,
                args.seed,
                args.device,
                args.allow_other_device,
            )
            operations_report[operation] = operation_report
            comparison = operation_report["comparison"]
            assert isinstance(comparison, dict)
            accepted = accepted and bool(comparison["passed"])
        report["operations"] = operations_report
        report["accepted"] = accepted
        report["acceptance_basis"] = (
            "bit-for-bit comparison of every valid row against "
            "reference.exact_binary64 plus invalid-status checks"
        )
        if args.work_dir is not None:
            report["work_dir"] = str(work_dir)
        print(json.dumps(report, sort_keys=True, indent=2))
        return 0 if accepted else 1
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
