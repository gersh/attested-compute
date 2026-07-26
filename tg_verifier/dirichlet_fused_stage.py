# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Compact CRT-generated selected-character stage for Platt's large-q path.

The stage shares one synthetic/certified Hurwitz lattice across a batch of
moduli.  It stores no per-residue requests: the CUDA and exact CPU programs
independently rebuild the canonical CRT unit-group enumeration.  It also stores
no per-residue results: each requested character is reduced directly to
``sum_a chi(a) zeta_M(s,a/q)``.

This is an exact arithmetic/conformance oracle and an exception path, not the
missing all-character interval FFT.  Its direct cost is K*phi(q) for K selected
characters, so using it for every character would be quadratic and infeasible.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile
from typing import Any, NoReturn, Sequence

from tg_verifier.dirichlet_lattice_stage import (
    LATTICE_ROWS,
    SOURCE_SAMPLE_DENOMINATOR,
    SOURCE_SAMPLE_NUMERATOR,
    TAYLOR_COLUMNS,
    TAYLOR_DEGREE,
    maximum_t_index,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
SOURCE_URL = "https://arxiv.org/abs/1305.3087v1"
ALGORITHM_ID = "platt-dirichlet-fused-character-block-v1"
CHECKER_ID = "cpu-exact-rational-fused-character-v1"
FORMAT_VERSION = 1
MAXIMUM_MODULUS = 400_000
MAX_LOCAL_FACTORS = 8
MAX_COMPONENTS = 8
SOURCE_Q_START = 10_001
SOURCE_Q_STOP = 400_000
SOURCE_DIRECT_ALL_CHARACTER_GROUP_POINTS = 47_631_269_684_196_653_160

INPUT_MAGIC = b"TGDFUSI1"
OUTPUT_MAGIC = b"TGDFUSO1"
INPUT_HEADER = struct.Struct("<8sIIIIIIIIqQQQQ")
MODULUS_TASK = struct.Struct("<IIIIIIIIQdQ")
LOCAL_FACTOR = struct.Struct("<IIIIQQ")
CYCLIC_COMPONENT = struct.Struct("<IIIIdddd")
CHARACTER_REQUEST = struct.Struct("<II8I")
LATTICE_CELL = struct.Struct("<dddd")
OUTPUT_HEADER = struct.Struct("<8sIIIIQQQ")
OUTPUT_ITEM = struct.Struct("<IIIIdddd")


class DirichletFusedStageError(RuntimeError):
    """A compact fused-stage plan or artifact failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletFusedStageError(message)


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _factor_prime_powers(q: int) -> list[tuple[int, int, int]]:
    if not 3 <= q <= MAXIMUM_MODULUS:
        _fail("q is outside 3..400000")
    answer: list[tuple[int, int, int]] = []
    remainder = q
    prime = 2
    while prime * prime <= remainder:
        if remainder % prime:
            prime += 1
            continue
        exponent = 0
        modulus = 1
        while remainder % prime == 0:
            remainder //= prime
            modulus *= prime
            exponent += 1
        answer.append((prime, exponent, modulus))
        prime += 1
    if remainder > 1:
        answer.append((remainder, 1, remainder))
    return answer


def _prime_divisors(value: int) -> list[int]:
    answer: list[int] = []
    prime = 2
    while prime * prime <= value:
        if value % prime:
            prime += 1
            continue
        answer.append(prime)
        while value % prime == 0:
            value //= prime
        prime += 1
    if value > 1:
        answer.append(value)
    return answer


def _least_primitive_root(modulus: int, prime: int) -> int:
    order = modulus - modulus // prime
    divisors = _prime_divisors(order)
    for candidate in range(2, modulus):
        if math.gcd(candidate, modulus) != 1:
            continue
        if all(pow(candidate, order // divisor, modulus) != 1
               for divisor in divisors):
            return candidate
    _fail("primitive-root reconstruction failed")


@dataclass(frozen=True)
class ComponentModel:
    generator: int
    order: int


@dataclass(frozen=True)
class FactorModel:
    modulus: int
    components: tuple[ComponentModel, ...]


def canonical_group_model(q: int) -> tuple[FactorModel, ...]:
    factors: list[FactorModel] = []
    for prime, exponent, modulus in _factor_prime_powers(q):
        components: list[ComponentModel] = []
        if prime == 2:
            if exponent == 2:
                components.append(ComponentModel(3, 2))
            elif exponent > 2:
                components.append(ComponentModel(modulus - 1, 2))
                components.append(ComponentModel(5, 1 << (exponent - 2)))
        else:
            components.append(
                ComponentModel(
                    _least_primitive_root(modulus, prime),
                    modulus - modulus // prime,
                )
            )
        factors.append(FactorModel(modulus, tuple(components)))
    if len(factors) > MAX_LOCAL_FACTORS:
        _fail("canonical factor model exceeds the format limit")
    if sum(len(factor.components) for factor in factors) > MAX_COMPONENTS:
        _fail("canonical component model exceeds the format limit")
    return tuple(factors)


def group_order(model: Sequence[FactorModel]) -> int:
    answer = 1
    for factor in model:
        for component in factor.components:
            answer *= component.order
    return answer


def source_direct_all_character_group_points() -> int:
    """Recompute the exact quadratic work count for the prohibited direct plan."""

    phi = list(range(SOURCE_Q_STOP + 1))
    for prime in range(2, SOURCE_Q_STOP + 1):
        if phi[prime] != prime:
            continue
        for multiple in range(prime, SOURCE_Q_STOP + 1, prime):
            phi[multiple] -= phi[multiple] // prime
    total = sum(
        (maximum_t_index(q) + 1) * phi[q] * phi[q]
        for q in range(SOURCE_Q_START, SOURCE_Q_STOP + 1)
    )
    if total != SOURCE_DIRECT_ALL_CHARACTER_GROUP_POINTS:
        _fail("pinned direct all-character work count changed")
    return total


def _outward(value: float, ulps: int = 8) -> tuple[float, float]:
    lo = value
    hi = value
    for _ in range(ulps):
        lo = math.nextafter(lo, -math.inf)
        hi = math.nextafter(hi, math.inf)
    return lo, hi


def _synthetic_root(order: int) -> tuple[float, float, float, float]:
    # The exact orders used by the KATs avoid any libm semantic assumption.
    if order == 2:
        return -1.0, -1.0, 0.0, 0.0
    if order == 4:
        return 0.0, 0.0, 1.0, 1.0
    angle = 2.0 * math.pi / order
    re_lo, re_hi = _outward(math.cos(angle))
    im_lo, im_hi = _outward(math.sin(angle))
    return re_lo, re_hi, im_lo, im_hi


def _synthetic_cell(row: int, column: int) -> tuple[float, float, float, float]:
    real = (((row * 17 + column * 13) % 101) - 50) / 64.0
    imag = (((row * 29 + column * 7) % 103) - 51) / 64.0
    width = math.ldexp(1.0, -40)
    return real - width, real + width, imag - width, imag + width


def _frequencies(ordinal: int, orders: Sequence[int]) -> tuple[int, ...]:
    values: list[int] = []
    remainder = ordinal
    for order in orders:
        remainder, value = divmod(remainder, order)
        values.append(value)
    if remainder:
        _fail("character ordinal exceeds the unit group")
    return tuple(values)


def write_synthetic_compact_input(
    path: Path,
    *,
    q_values: Sequence[int],
    t_index: int,
    characters_per_q: int | None = None,
) -> dict[str, Any]:
    """Write a labeled synthetic batch with no per-residue payload.

    ``characters_per_q=None`` requests every character and is intended only for
    tiny KAT moduli.  General root intervals are deliberately labeled
    synthetic; a production job must replace them with certified enclosures.
    """

    if not q_values:
        _fail("at least one modulus is required")
    if list(q_values) != sorted(set(q_values)):
        _fail("q values must be strictly increasing")
    if t_index < 0:
        _fail("t_index must be nonnegative")
    if characters_per_q is not None and characters_per_q <= 0:
        _fail("characters_per_q must be positive")

    tasks: list[bytes] = []
    factors: list[bytes] = []
    components: list[bytes] = []
    characters: list[bytes] = []
    task_report: list[dict[str, Any]] = []
    for q in q_values:
        model = canonical_group_model(q)
        orders = [component.order for factor in model
                  for component in factor.components]
        phi = group_order(model)
        count = phi if characters_per_q is None else min(phi, characters_per_q)
        factor_offset = len(factors)
        component_offset = len(components)
        character_offset = len(characters)
        local_component_offset = component_offset
        for local_factor, factor in enumerate(model):
            cofactor = q // factor.modulus
            inverse = pow(cofactor, -1, factor.modulus)
            factors.append(
                LOCAL_FACTOR.pack(
                    factor.modulus,
                    local_component_offset,
                    len(factor.components),
                    0,
                    cofactor,
                    inverse,
                )
            )
            for component in factor.components:
                components.append(
                    CYCLIC_COMPONENT.pack(
                        factor_offset + local_factor,
                        component.generator,
                        component.order,
                        0,
                        *_synthetic_root(component.order),
                    )
                )
            local_component_offset += len(factor.components)
        for ordinal in range(count):
            frequency = list(_frequencies(ordinal, orders))
            frequency.extend([0] * (MAX_COMPONENTS - len(frequency)))
            characters.append(CHARACTER_REQUEST.pack(ordinal, 0, *frequency))
        tail = math.ldexp(1.0, -42)
        tasks.append(
            MODULUS_TASK.pack(
                q,
                factor_offset,
                len(model),
                component_offset,
                len(orders),
                character_offset,
                count,
                0,
                phi,
                tail,
                0,
            )
        )
        task_report.append(
            {
                "q": q,
                "phi_q": phi,
                "local_factors": len(model),
                "cyclic_components": len(orders),
                "selected_characters": count,
                "direct_group_points": phi * count,
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(
                INPUT_HEADER.pack(
                    INPUT_MAGIC,
                    FORMAT_VERSION,
                    LATTICE_ROWS,
                    TAYLOR_DEGREE,
                    len(tasks),
                    len(factors),
                    len(components),
                    len(characters),
                    0,
                    SOURCE_SAMPLE_NUMERATOR * t_index,
                    SOURCE_SAMPLE_DENOMINATOR,
                    LATTICE_ROWS * TAYLOR_COLUMNS,
                    0,
                    0,
                )
            )
            for collection in (tasks, factors, components, characters):
                for row in collection:
                    output.write(row)
            for row in range(1, LATTICE_ROWS + 1):
                for column in range(TAYLOR_COLUMNS):
                    output.write(LATTICE_CELL.pack(*_synthetic_cell(row, column)))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    digest, size = sha256_file(path)
    old_request_bytes = sum(task["phi_q"] for task in task_report) * 24
    old_output_bytes = sum(task["phi_q"] for task in task_report) * 48
    return {
        "algorithm_id": ALGORITHM_ID,
        "classification": "synthetic_compact_fused_arithmetic_conformance_only",
        "t_index": t_index,
        "tasks": task_report,
        "total_selected_characters": len(characters),
        "total_direct_group_points": sum(
            task["direct_group_points"] for task in task_report
        ),
        "per_residue_requests_materialized": False,
        "per_residue_results_materialized": False,
        "old_explicit_request_bytes_for_one_slice": old_request_bytes,
        "old_explicit_result_bytes_for_one_slice": old_output_bytes,
        "sha256": digest,
        "size_bytes": size,
    }


def inspect_compact_input(path: Path) -> dict[str, Any]:
    digest, size = sha256_file(path)
    with path.open("rb") as source:
        raw = source.read(INPUT_HEADER.size)
        if len(raw) != INPUT_HEADER.size:
            _fail("short compact input header")
        values = INPUT_HEADER.unpack(raw)
        (
            magic,
            version,
            rows,
            degree,
            task_count,
            factor_count,
            component_count,
            character_count,
            reserved0,
            t_numerator,
            t_denominator,
            lattice_count,
            reserved1,
            reserved2,
        ) = values
        if (
            magic != INPUT_MAGIC
            or version != FORMAT_VERSION
            or rows != LATTICE_ROWS
            or degree != TAYLOR_DEGREE
            or task_count == 0
            or character_count == 0
            or reserved0 != 0
            or reserved1 != 0
            or reserved2 != 0
            or t_numerator < 0
            or t_denominator == 0
            or lattice_count != LATTICE_ROWS * TAYLOR_COLUMNS
        ):
            _fail("invalid compact input header")
        expected = (
            INPUT_HEADER.size
            + task_count * MODULUS_TASK.size
            + factor_count * LOCAL_FACTOR.size
            + component_count * CYCLIC_COMPONENT.size
            + character_count * CHARACTER_REQUEST.size
            + lattice_count * LATTICE_CELL.size
        )
        if size != expected:
            _fail("compact input length is not canonical")
        tasks = [MODULUS_TASK.unpack(source.read(MODULUS_TASK.size))
                 for _ in range(task_count)]
        first_q = tasks[0][0]
        last_q = tasks[-1][0]
        if any(left[0] >= right[0] for left, right in zip(tasks, tasks[1:])):
            _fail("modulus tasks are not strictly increasing")
    return {
        "sha256": digest,
        "size_bytes": size,
        "t": {"numerator": t_numerator, "denominator": t_denominator},
        "task_count": task_count,
        "q_first": first_q,
        "q_last": last_q,
        "local_factor_count": factor_count,
        "cyclic_component_count": component_count,
        "selected_character_count": character_count,
        "per_residue_payload_present": False,
    }


def capability_report() -> dict[str, Any]:
    old_requests = 327_089_206_283_008 * 24
    old_results = 327_089_206_283_008 * 48
    return {
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "source": SOURCE_URL,
        "classification": "conditional_selected_character_oracle_not_full_grh",
        "implemented": {
            "one_lattice_shared_across_multiple_moduli_at_one_ordinate": True,
            "canonical_crt_unit_residues_generated_on_device": True,
            "taylor_reconstruction_fused_with_character_weighting": True,
            "selected_character_dft_coefficients_reduced_on_device": True,
            "per_residue_request_files": False,
            "per_residue_result_files": False,
            "independent_exact_dyadic_cpu_replay": True,
        },
        "avoided_for_sparse_selected_coefficients": {
            "explicit_request_bytes": old_requests,
            "explicit_result_bytes": old_results,
            "total_bytes": old_requests + old_results,
            "warning": (
                "requesting every character would again produce a petabyte-scale "
                "stream; the future FFT must fuse into downstream zero state"
            ),
        },
        "complexity": {
            "selected_K_characters": "O(K * phi(q) * (N + log q))",
            "all_phi_characters_if_misused": "quadratic O(phi(q)^2), prohibited as a source-scale plan",
        },
        "conditional_inputs_not_proved": [
            "Hurwitz-zeta lattice rectangles",
            "Taylor-tail radius",
            "root-of-unity rectangles for cyclic factors",
        ],
        "still_absent": [
            "source-faithful all-character CRT/Bluestein interval FFT",
            "finite-term recovery and q^(-s) completed-L factors",
            "certified lattice and tail producer",
            "small-q Booker FFT path",
            "upsampling, zero isolation, exceptional cases, and Turing completeness",
            "Lean realization theorem",
        ],
        "production_role": "bounded character samples, exception recomputation, and future FFT KAT oracle",
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "ATOM_ID",
    "CHARACTER_REQUEST",
    "CYCLIC_COMPONENT",
    "DirichletFusedStageError",
    "INPUT_HEADER",
    "LOCAL_FACTOR",
    "MODULUS_TASK",
    "SOURCE_DIRECT_ALL_CHARACTER_GROUP_POINTS",
    "canonical_group_model",
    "capability_report",
    "group_order",
    "inspect_compact_input",
    "source_direct_all_character_group_points",
    "write_synthetic_compact_input",
]
