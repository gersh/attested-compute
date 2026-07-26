# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact schedule and immutable receipts for Platt's large-q Taylor stage.

This module intentionally stops at one conditional identity: given certified
intervals for the D=2048, c=0..15 Hurwitz lattice and a certified remainder
radius, reconstruct the requested ``zeta_M(s,a/q)`` interval by Lemma 4.2 of
arXiv:1305.3087v1.  It does not turn that conditional stage into a GRH proof.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import tempfile
from typing import Any, Iterable, NoReturn


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
SOURCE_URL = "https://arxiv.org/abs/1305.3087v1"
ALGORITHM_ID = "platt-dirichlet-large-q-lattice-taylor-stage-v1"
CHECKER_ID = "cpu-exact-rational-natural-interval-v1"
PLAN_SCHEMA = "sparkinterval.tg.dirichlet_lattice_stage.plan.v1"
RECEIPT_SCHEMA = "sparkinterval.tg.dirichlet_lattice_stage.receipt.v1"

SOURCE_Q_START = 10_001
SOURCE_Q_STOP = 400_000
SOURCE_SAMPLE_NUMERATOR = 5
SOURCE_SAMPLE_DENOMINATOR = 64
LATTICE_ROWS = 2_048
TAYLOR_DEGREE = 15
TAYLOR_COLUMNS = TAYLOR_DEGREE + 1
FIXED_SOURCE_SHARDS = 8

# These pinned counts are independently reproducible from the exact formulas
# below.  They are stage-work counts, not the paper's primitive-character or
# zero counts.
SOURCE_MAX_T_INDEX = 127_987
SOURCE_Q_T_ROWS = 4_901_051_274
SOURCE_RESIDUE_INTERPOLATIONS = 327_089_206_283_008
SOURCE_TAYLOR_TERMS = 5_233_427_300_528_128

INPUT_MAGIC = b"TGDLATI1"
OUTPUT_MAGIC = b"TGDLATO1"
FORMAT_VERSION = 1
INPUT_HEADER = struct.Struct("<8sIIIIqQQQQ")
LATTICE_CELL = struct.Struct("<dddd")
INPUT_ITEM = struct.Struct("<IIIId")
OUTPUT_HEADER = struct.Struct("<8sIIIIQQQ")
OUTPUT_ITEM = struct.Struct("<IIIIdddd")


class DirichletLatticeStageError(RuntimeError):
    """A source plan, batch, runner, or exact replay failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletLatticeStageError(message)


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _totients(limit: int) -> list[int]:
    values = list(range(limit + 1))
    for prime in range(2, limit + 1):
        if values[prime] != prime:
            continue
        for multiple in range(prime, limit + 1, prime):
            values[multiple] -= values[multiple] // prime
    return values


def source_height(q: int) -> Fraction:
    if not SOURCE_Q_START <= q <= SOURCE_Q_STOP:
        _fail("q is outside the large-q source stage")
    additive = 75_000_000 if q % 2 == 0 else 37_500_000
    return Fraction(max(100_000_000, 200 * q + additive), q)


def maximum_t_index(q: int) -> int:
    height = source_height(q)
    return (
        height.numerator * SOURCE_SAMPLE_DENOMINATOR
        // (height.denominator * SOURCE_SAMPLE_NUMERATOR)
    )


def canonical_lattice_row(q: int, a: int) -> int:
    if q < 3 or not 1 <= a < q:
        _fail("invalid residue")
    row = (2 * LATTICE_ROWS * a + q - 1) // (2 * q)
    return min(LATTICE_ROWS, max(1, row))


@dataclass(frozen=True)
class SourceWork:
    active_residue_counts: tuple[int, ...]
    prefix_residue_counts: tuple[int, ...]
    q_t_rows: int
    residue_interpolations: int


def source_work() -> SourceWork:
    phi = _totients(SOURCE_Q_STOP)
    maxima: list[tuple[int, int]] = []
    q_t_rows = 0
    maximum = 0
    residue_interpolations = 0
    for q in range(SOURCE_Q_START, SOURCE_Q_STOP + 1):
        last = maximum_t_index(q)
        maximum = max(maximum, last)
        q_t_rows += last + 1
        residue_interpolations += phi[q] * (last + 1)
        maxima.append((last, phi[q]))
    active = [0] * (maximum + 2)
    for last, count in maxima:
        active[0] += count
        active[last + 1] -= count
    for index in range(1, len(active)):
        active[index] += active[index - 1]
    active.pop()
    prefix = [0]
    for count in active:
        prefix.append(prefix[-1] + count)
    if (
        maximum != SOURCE_MAX_T_INDEX
        or q_t_rows != SOURCE_Q_T_ROWS
        or residue_interpolations != SOURCE_RESIDUE_INTERPOLATIONS
        or prefix[-1] != SOURCE_RESIDUE_INTERPOLATIONS
    ):
        _fail("pinned large-q source-work invariant failed")
    return SourceWork(tuple(active), tuple(prefix), q_t_rows, residue_interpolations)


def _balanced_boundaries(prefix: tuple[int, ...], shard_count: int) -> list[int]:
    if shard_count <= 0:
        _fail("shard_count must be positive")
    total = prefix[-1]
    boundaries = [0]
    for shard in range(1, shard_count):
        target = total * shard // shard_count
        insertion = bisect_left(prefix, target)
        choices = [
            value
            for value in (insertion - 1, insertion)
            if boundaries[-1] < value < len(prefix) - 1
        ]
        if not choices:
            _fail("cannot construct nonempty source shards")
        boundaries.append(min(choices, key=lambda value: abs(prefix[value] - target)))
    boundaries.append(len(prefix) - 1)
    return boundaries


def source_plan(*, shard_count: int = FIXED_SOURCE_SHARDS) -> dict[str, Any]:
    work = source_work()
    boundaries = _balanced_boundaries(work.prefix_residue_counts, shard_count)
    shards = []
    for index, (start, stop) in enumerate(zip(boundaries, boundaries[1:])):
        count = (
            work.prefix_residue_counts[stop]
            - work.prefix_residue_counts[start]
        )
        shards.append(
            {
                "shard_index": index,
                "t_index_start_inclusive": start,
                "t_index_stop_exclusive": stop,
                "t_lower": {
                    "numerator": SOURCE_SAMPLE_NUMERATOR * start,
                    "denominator": SOURCE_SAMPLE_DENOMINATOR,
                },
                "t_last": {
                    "numerator": SOURCE_SAMPLE_NUMERATOR * (stop - 1),
                    "denominator": SOURCE_SAMPLE_DENOMINATOR,
                },
                "residue_interpolations": count,
                "taylor_complex_terms": count * TAYLOR_COLUMNS,
            }
        )
    body: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "source": SOURCE_URL,
        "classification": "conditional_large_q_taylor_stage_not_grh_verification",
        "paper_parameters": {
            "large_q_cutover_used_by_this_plan": SOURCE_Q_START,
            "q_stop_inclusive": SOURCE_Q_STOP,
            "sample_step": {
                "numerator": SOURCE_SAMPLE_NUMERATOR,
                "denominator": SOURCE_SAMPLE_DENOMINATOR,
            },
            "hurwitz_lattice_rows_D": LATTICE_ROWS,
            "taylor_degree_N": TAYLOR_DEGREE,
            "taylor_columns_c_0_through_N": TAYLOR_COLUMNS,
        },
        "work": {
            "positive_t_indices": len(work.active_residue_counts),
            "q_t_rows": work.q_t_rows,
            "residue_interpolations": work.residue_interpolations,
            "taylor_complex_terms": work.residue_interpolations * TAYLOR_COLUMNS,
            "explicit_request_bytes_if_fully_materialized": (
                work.residue_interpolations * INPUT_ITEM.size
            ),
            "standalone_output_bytes_if_fully_materialized": (
                work.residue_interpolations * OUTPUT_ITEM.size
            ),
            "counting_note": (
                "The DFT requires one reconstructed residue value for every unit "
                "modulo q, including outputs later discarded as imprimitive."
            ),
            "grid_scope_note": (
                "This counts the main positive 5/64 grid within T_q only; "
                "upsampling, endpoint padding, and Turing windows are excluded."
            ),
        },
        "fixed_shards": shards,
        "conditional_input_contract": [
            "Each binary64 lattice rectangle encloses zeta_M(1/2+it+c,r/D).",
            "Each tail_radius_hi bounds the omitted complex Taylor tail.",
            "The choice of M and recovery of removed Dirichlet terms are external.",
        ],
        "not_implemented_by_this_stage": [
            "high-precision certified Hurwitz-lattice seed generation",
            "a proved numerical tail bound specialized to every request",
            "recovery of the removed finite Dirichlet terms",
            "compact on-device request enumeration and streaming fusion into the DFT",
            "CRT/Bluestein unit-group interval DFT and completed-L phase",
            "Booker small-q FFT path for q at most about 10000",
            "rigorous upsampling and exceptional-case recomputation",
            "multiplicity-preserving Turing completeness",
            "Lean realization of the external analytic computation",
        ],
        "atom_discharged": False,
        "production_ready_for_full_atom": False,
    }
    body["plan_sha256"] = sha256_bytes(canonical_json_bytes(body))
    return body


def _write_atomic(path: Path, raw: bytes, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive and path.exists():
        _fail(f"refusing to replace immutable artifact: {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        if exclusive and path.exists():
            _fail(f"refusing to replace immutable artifact: {path}")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _synthetic_cell(row: int, column: int) -> tuple[float, float, float, float]:
    # Exactly representable dyadic benchmark values. These are not zeta values.
    real = (((row * 17 + column * 13) % 101) - 50) / 64.0
    imag = (((row * 29 + column * 7) % 103) - 51) / 64.0
    width = math.ldexp(1.0, -40)
    return real - width, real + width, imag - width, imag + width


def write_synthetic_input(
    path: Path,
    *,
    q_start: int,
    q_stop: int,
    t_index: int,
    max_items: int | None = None,
) -> dict[str, Any]:
    if not SOURCE_Q_START <= q_start <= q_stop <= SOURCE_Q_STOP:
        _fail("synthetic q range is outside the large-q source stage")
    if not 0 <= t_index <= SOURCE_MAX_T_INDEX:
        _fail("t_index is outside the source grid")
    if max_items is not None and max_items <= 0:
        _fail("max_items must be positive")
    item_count = 0
    for q in range(q_start, q_stop + 1):
        if t_index > maximum_t_index(q):
            continue
        for a in range(1, q):
            if math.gcd(a, q) == 1:
                item_count += 1
                if max_items is not None and item_count == max_items:
                    break
        if max_items is not None and item_count == max_items:
            break
    if item_count == 0:
        _fail("synthetic batch has no active unit residues")

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    emitted = 0
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(
                INPUT_HEADER.pack(
                    INPUT_MAGIC,
                    FORMAT_VERSION,
                    LATTICE_ROWS,
                    TAYLOR_DEGREE,
                    0,
                    SOURCE_SAMPLE_NUMERATOR * t_index,
                    SOURCE_SAMPLE_DENOMINATOR,
                    item_count,
                    LATTICE_ROWS * TAYLOR_COLUMNS,
                    0,
                )
            )
            for row in range(1, LATTICE_ROWS + 1):
                for column in range(TAYLOR_COLUMNS):
                    output.write(LATTICE_CELL.pack(*_synthetic_cell(row, column)))
            tail = math.ldexp(1.0, -42)
            stop = False
            for q in range(q_start, q_stop + 1):
                if t_index > maximum_t_index(q):
                    continue
                for a in range(1, q):
                    if math.gcd(a, q) != 1:
                        continue
                    output.write(
                        INPUT_ITEM.pack(q, a, canonical_lattice_row(q, a), 0, tail)
                    )
                    emitted += 1
                    if emitted == item_count:
                        stop = True
                        break
                if stop:
                    break
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    if emitted != item_count:
        _fail("synthetic request count invariant failed")
    digest, size = sha256_file(path)
    return {
        "classification": "synthetic_throughput_and_arithmetic_conformance_only",
        "q_start": q_start,
        "q_stop": q_stop,
        "t_index": t_index,
        "item_count": item_count,
        "truncated_by_max_items": max_items is not None,
        "sha256": digest,
        "size_bytes": size,
    }


def inspect_input(path: Path) -> dict[str, Any]:
    digest, size = sha256_file(path)
    with path.open("rb") as source:
        raw = source.read(INPUT_HEADER.size)
        if len(raw) != INPUT_HEADER.size:
            _fail("short lattice input header")
        (
            magic,
            version,
            rows,
            degree,
            reserved0,
            t_numerator,
            t_denominator,
            item_count,
            lattice_count,
            reserved1,
        ) = INPUT_HEADER.unpack(raw)
        if (
            magic != INPUT_MAGIC
            or version != FORMAT_VERSION
            or rows != LATTICE_ROWS
            or degree != TAYLOR_DEGREE
            or reserved0 != 0
            or reserved1 != 0
            or t_numerator < 0
            or t_denominator == 0
            or item_count == 0
            or lattice_count != LATTICE_ROWS * TAYLOR_COLUMNS
        ):
            _fail("invalid lattice input header")
        expected = (
            INPUT_HEADER.size
            + lattice_count * LATTICE_CELL.size
            + item_count * INPUT_ITEM.size
        )
        if size != expected:
            _fail("lattice input length is not canonical")
        for _ in range(lattice_count):
            cell_raw = source.read(LATTICE_CELL.size)
            if len(cell_raw) != LATTICE_CELL.size:
                _fail("short lattice cell payload")
            re_lo, re_hi, im_lo, im_hi = LATTICE_CELL.unpack(cell_raw)
            if (
                not all(math.isfinite(value) for value in
                        (re_lo, re_hi, im_lo, im_hi))
                or re_lo > re_hi
                or im_lo > im_hi
            ):
                _fail("non-finite or reversed lattice cell")
        first: tuple[int, int, int, int, float] | None = None
        last: tuple[int, int, int, int, float] | None = None
        for _ in range(item_count):
            item = INPUT_ITEM.unpack(source.read(INPUT_ITEM.size))
            q, a, row, reserved, tail = item
            if (
                q < 3
                or q > SOURCE_Q_STOP
                or not 1 <= a < q
                or math.gcd(q, a) != 1
                or row != canonical_lattice_row(q, a)
                or reserved != 0
                or not math.isfinite(tail)
                or tail < 0
            ):
                _fail("invalid lattice input request")
            first = first or item
            last = item
    return {
        "sha256": digest,
        "size_bytes": size,
        "t": {"numerator": t_numerator, "denominator": t_denominator},
        "item_count": item_count,
        "first_request": {"q": first[0], "a": first[1]} if first else None,
        "last_request": {"q": last[0], "a": last[1]} if last else None,
    }


def _copy_immutable(source: Path, destination: Path, *, executable: bool) -> None:
    if not source.is_file():
        _fail(f"not a regular file: {source}")
    shutil.copyfile(source, destination)
    destination.chmod(stat.S_IRUSR | (stat.S_IXUSR if executable else 0))


def run_batch(
    root: Path,
    *,
    input_path: Path,
    runner: Path,
    checker: Path,
    device: int = 0,
    lattice_certificate: Path | None = None,
    synthetic_lattice: bool = False,
    timeout: float | None = None,
) -> dict[str, Any]:
    if root.exists():
        _fail(f"refusing to replace immutable batch root: {root}")
    if device < 0:
        _fail("device must be nonnegative")
    if synthetic_lattice == (lattice_certificate is not None):
        _fail(
            "select exactly one of synthetic_lattice or a lattice_certificate"
        )
    input_report = inspect_input(input_path)
    temporary = root.parent / f".{root.name}.tmp.{os.getpid()}"
    if temporary.exists():
        _fail(f"temporary batch root already exists: {temporary}")
    artifacts = temporary / "artifacts"
    artifacts.mkdir(parents=True)
    try:
        staged_input = artifacts / "input.bin"
        staged_runner = artifacts / "gpu-runner"
        staged_checker = artifacts / "exact-checker"
        _copy_immutable(input_path, staged_input, executable=False)
        _copy_immutable(runner, staged_runner, executable=True)
        _copy_immutable(checker, staged_checker, executable=True)
        certificate_report: dict[str, Any] | None = None
        if lattice_certificate is not None:
            staged_certificate = artifacts / "lattice-certificate"
            _copy_immutable(lattice_certificate, staged_certificate, executable=False)
            cert_hash, cert_size = sha256_file(staged_certificate)
            certificate_report = {"sha256": cert_hash, "size_bytes": cert_size}

        output_path = temporary / "output.bin"
        gpu = subprocess.run(
            [str(staged_runner.resolve()), str(staged_input.resolve()),
             str(output_path.resolve()), str(device), "1"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        if gpu.returncode != 0 or gpu.stderr:
            _fail(
                "GPU stage failed closed: "
                + gpu.stderr[:4096].decode("utf-8", errors="replace")
            )
        checker_run = subprocess.run(
            [str(staged_checker.resolve()), "verify", str(staged_input.resolve()),
             str(output_path.resolve())],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        if checker_run.returncode != 0 or checker_run.stderr:
            _fail(
                "exact checker failed closed: "
                + checker_run.stderr[:4096].decode("utf-8", errors="replace")
            )
        _write_atomic(temporary / "gpu.stdout", gpu.stdout)
        _write_atomic(temporary / "checker.stdout", checker_run.stdout)
        output_path.chmod(stat.S_IRUSR)

        plan = source_plan()
        runner_hash, runner_size = sha256_file(staged_runner)
        checker_hash, checker_size = sha256_file(staged_checker)
        output_hash, output_size = sha256_file(output_path)
        receipt: dict[str, Any] = {
            "schema": RECEIPT_SCHEMA,
            "schema_version": 1,
            "author": AUTHOR,
            "atom_id": ATOM_ID,
            "algorithm_id": ALGORITHM_ID,
            "checker_id": CHECKER_ID,
            "source_plan_sha256": plan["plan_sha256"],
            "classification": (
                "synthetic_arithmetic_conformance_only"
                if synthetic_lattice
                else "conditional_taylor_stage_with_external_lattice_certificate"
            ),
            "input": input_report,
            "artifacts": {
                "runner": {"sha256": runner_hash, "size_bytes": runner_size},
                "checker": {"sha256": checker_hash, "size_bytes": checker_size},
                "output": {"sha256": output_hash, "size_bytes": output_size},
                "lattice_certificate": certificate_report,
            },
            "decisions": {
                "canonical_input_replayed": True,
                "exact_rational_arithmetic_replay_passed": True,
                "lattice_semantics_proved_by_this_receipt": False,
                "taylor_tail_bound_proved_by_this_receipt": False,
                "unit_group_fft_completed": False,
                "turing_completeness_completed": False,
                "external_atom_discharged": False,
            },
        }
        receipt["receipt_sha256"] = sha256_bytes(canonical_json_bytes(receipt))
        _write_atomic(temporary / "receipt.json", canonical_json_bytes(receipt))
        os.replace(temporary, root)
        return receipt
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def benchmark_projection(
    *, items_per_second: float, h100_speedup_low: float = 1.0,
    h100_speedup_high: float = 14.3, h100_count: int = 8
) -> dict[str, Any]:
    if not math.isfinite(items_per_second) or items_per_second <= 0:
        _fail("items_per_second must be finite and positive")
    if not (0 < h100_speedup_low <= h100_speedup_high) or h100_count <= 0:
        _fail("invalid H100 projection parameters")
    # This projects only this Taylor stage. It deliberately excludes every
    # missing stage listed in source_plan().
    slow_seconds = SOURCE_RESIDUE_INTERPOLATIONS / (
        items_per_second * h100_speedup_low * h100_count
    )
    fast_seconds = SOURCE_RESIDUE_INTERPOLATIONS / (
        items_per_second * h100_speedup_high * h100_count
    )
    return {
        "classification": (
            "gb10_to_h100_sensitivity_for_conditional_taylor_stage_only"
        ),
        "dgx_spark_items_per_second": items_per_second,
        "per_h100_throughput_factor_sensitivity": [
            h100_speedup_low,
            h100_speedup_high,
        ],
        "upper_endpoint_note": (
            "14.3 is the H100-NVL/DGX-Spark memory-bandwidth ratio, not a "
            "measured kernel speedup or a promised runtime multiplier"
        ),
        "h100_count": h100_count,
        "projected_seconds_range": [fast_seconds, slow_seconds],
        "projected_hours_range": [fast_seconds / 3600.0, slow_seconds / 3600.0],
        "external_atom_runtime_estimated": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "ATOM_ID",
    "DirichletLatticeStageError",
    "SOURCE_MAX_T_INDEX",
    "SOURCE_Q_T_ROWS",
    "SOURCE_RESIDUE_INTERPOLATIONS",
    "SOURCE_TAYLOR_TERMS",
    "benchmark_projection",
    "canonical_lattice_row",
    "inspect_input",
    "maximum_t_index",
    "run_batch",
    "source_height",
    "source_plan",
    "source_work",
    "write_synthetic_input",
]
