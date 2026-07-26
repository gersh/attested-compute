# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded independent arithmetic replay for ``TGDLTMB1`` CUDA output.

The production t-major component authenticates its input and binds the
concatenated ``TGDAFFI1`` output hash.  This module adds a deliberately
bounded differential checker for the arithmetic between those boundaries.
It emulates every CUDA directed binary64 add, subtract, multiply, and divide
through exact ``Fraction`` intermediates, rather than reusing the production
CUDA implementation or the host-side nextafter interval helpers.

The checker authenticates the complete block, seed, and output streams but
recomputes only a deterministic bounded roster of output values.  It is a
qualification artifact, not a source-scale replay, a proof of the seed
semantics, an executable-refinement theorem, or Platt's Theorem 7.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import math
import os
from pathlib import Path
import stat
import struct
from typing import Any, BinaryIO, Mapping, NoReturn

from tg_verifier.dirichlet_allchars_stage import (
    COMPLEX_INTERVAL,
    INPUT_HEADER as TGDAFFI_HEADER,
    INPUT_MAGIC as TGDAFFI_MAGIC,
    canonical_component_orders,
    canonical_residue_order,
    has_primitive_character_modulus,
)
from tg_verifier.dirichlet_lattice_stage import (
    LATTICE_ROWS,
    SOURCE_MAX_T_INDEX,
    SOURCE_SAMPLE_DENOMINATOR,
    SOURCE_SAMPLE_NUMERATOR,
    TAYLOR_COLUMNS,
    TAYLOR_DEGREE,
    canonical_lattice_row,
    maximum_t_index,
)
from tg_verifier import dirichlet_recovery_seeds as seed_format
from tg_verifier.dirichlet_tmajor_cuda_block import (
    ALGORITHM_ID,
    BLOCK_FOOTER,
    BLOCK_HEADER,
    BLOCK_MAGIC,
    FOOTER_MAGIC,
    FORMAT_VERSION,
    MAXIMUM_BATCH_COUNT,
    ROW_HEADER,
    ROW_MAGIC,
    ROW_PAYLOAD_BYTES,
    SIDECAR_MODE_DIRECT_MPFR,
    TARGET_HEADER,
    TARGET_MAGIC,
    TARGET_SIDECAR_DOMAIN,
    canonical_json_bytes,
    replay_tmajor_cuda_block,
    validate_tmajor_cuda_execution_summary,
)


AUTHOR = "Gershon Bialer"
CHECKER_ID = "exact-fraction-ieee754-directed-tmajor-sample-v1"
REPLAY_SCHEMA = (
    "sparkinterval.tg.dirichlet_tmajor_cuda.arithmetic_replay.v1"
)
TYPED_BUNDLE_SCHEMA = (
    "sparkinterval.tg.dirichlet_tmajor_cuda."
    "typed_arithmetic_qualification.v1"
)
DEFAULT_MAXIMUM_TARGETS = 8
DEFAULT_MAXIMUM_VALUES_PER_TARGET = 8
DEFAULT_MAXIMUM_BLOCK_BYTES = 128 * 1024 * 1024
DEFAULT_MAXIMUM_OUTPUT_BYTES = 128 * 1024 * 1024
MAXIMUM_EXACT_INTEGER_AS_BINARY64 = 1 << 53
HEX = frozenset("0123456789abcdef")


RealInterval = tuple[float, float]
ComplexInterval = tuple[RealInterval, RealInterval]


class DirichletTMajorCudaArithmeticReplayError(RuntimeError):
    """A bounded independent stream or arithmetic replay failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletTMajorCudaArithmeticReplayError(message)


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in HEX for character in value)
    ):
        _fail(f"{label} is not lowercase SHA-256")
    return value


def _positive_integer(
    value: object, label: str, *, maximum: int
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        _fail(f"{label} is outside [1,{maximum}]")
    return value


def _open_regular(path: Path, *, label: str) -> BinaryIO:
    try:
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        )
    except OSError as error:
        raise DirichletTMajorCudaArithmeticReplayError(
            f"cannot open {label}: {error}"
        ) from error
    source = os.fdopen(descriptor, "rb")
    if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
        source.close()
        _fail(f"{label} is not a regular file")
    return source


def _identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _read_exact(
    source: BinaryIO,
    count: int,
    *,
    label: str,
    digest: Any | None = None,
) -> bytes:
    raw = source.read(count)
    if len(raw) != count:
        _fail(f"truncated {label}")
    if digest is not None:
        digest.update(raw)
    return raw


def _finite_ordered_box(
    values: tuple[float, float, float, float], *, label: str
) -> tuple[float, float, float, float]:
    if (
        not all(math.isfinite(value) for value in values)
        or values[0] > values[1]
        or values[2] > values[3]
    ):
        _fail(f"{label} is not a finite ordered complex interval")
    return values


def _as_complex(
    values: tuple[float, float, float, float], *, label: str
) -> ComplexInterval:
    checked = _finite_ordered_box(values, label=label)
    return (checked[0], checked[1]), (checked[2], checked[3])


def _flatten(value: ComplexInterval) -> tuple[float, float, float, float]:
    return value[0][0], value[0][1], value[1][0], value[1][1]


def _round_exact(value: Fraction, *, upward: bool) -> float:
    """Return the tight directed binary64 rounding of an exact rational."""

    try:
        result = float(value)
    except OverflowError as error:
        raise DirichletTMajorCudaArithmeticReplayError(
            "exact arithmetic overflowed binary64"
        ) from error
    if not math.isfinite(result):
        _fail("exact arithmetic overflowed binary64")
    if upward:
        while Fraction.from_float(result) < value:
            result = math.nextafter(result, math.inf)
        while True:
            previous = math.nextafter(result, -math.inf)
            if (
                not math.isfinite(previous)
                or Fraction.from_float(previous) < value
            ):
                return result
            result = previous
    while Fraction.from_float(result) > value:
        result = math.nextafter(result, -math.inf)
    while True:
        following = math.nextafter(result, math.inf)
        if (
            not math.isfinite(following)
            or Fraction.from_float(following) > value
        ):
            return result
        result = following


def _directed_add(x: float, y: float, *, upward: bool) -> float:
    return _round_exact(
        Fraction.from_float(x) + Fraction.from_float(y),
        upward=upward,
    )


def _directed_sub(x: float, y: float, *, upward: bool) -> float:
    return _round_exact(
        Fraction.from_float(x) - Fraction.from_float(y),
        upward=upward,
    )


def _directed_mul(x: float, y: float, *, upward: bool) -> float:
    return _round_exact(
        Fraction.from_float(x) * Fraction.from_float(y),
        upward=upward,
    )


def _directed_div(x: float, y: float, *, upward: bool) -> float:
    if not math.isfinite(y) or y <= 0.0:
        _fail("directed interval division requires a positive denominator")
    return _round_exact(
        Fraction.from_float(x) / Fraction.from_float(y),
        upward=upward,
    )


def _real_add(x: RealInterval, y: RealInterval) -> RealInterval:
    return (
        _directed_add(x[0], y[0], upward=False),
        _directed_add(x[1], y[1], upward=True),
    )


def _real_sub(x: RealInterval, y: RealInterval) -> RealInterval:
    return (
        _directed_sub(x[0], y[1], upward=False),
        _directed_sub(x[1], y[0], upward=True),
    )


def _real_mul(x: RealInterval, y: RealInterval) -> RealInterval:
    lower = (
        _directed_mul(x[0], y[0], upward=False),
        _directed_mul(x[0], y[1], upward=False),
        _directed_mul(x[1], y[0], upward=False),
        _directed_mul(x[1], y[1], upward=False),
    )
    upper = (
        _directed_mul(x[0], y[0], upward=True),
        _directed_mul(x[0], y[1], upward=True),
        _directed_mul(x[1], y[0], upward=True),
        _directed_mul(x[1], y[1], upward=True),
    )
    return min(lower), max(upper)


def _real_divide_positive(
    value: RealInterval, denominator: float
) -> RealInterval:
    return (
        _directed_div(value[0], denominator, upward=False),
        _directed_div(value[1], denominator, upward=True),
    )


def _rational_nonnegative(
    numerator: int, denominator: int
) -> RealInterval:
    if (
        not 0 <= numerator <= MAXIMUM_EXACT_INTEGER_AS_BINARY64
        or not 1 <= denominator <= MAXIMUM_EXACT_INTEGER_AS_BINARY64
    ):
        _fail("CUDA rational operands are not exact binary64 integers")
    return _real_divide_positive(
        (float(numerator), float(numerator)), float(denominator)
    )


def _complex_add(
    x: ComplexInterval, y: ComplexInterval
) -> ComplexInterval:
    return _real_add(x[0], y[0]), _real_add(x[1], y[1])


def _complex_mul(
    x: ComplexInterval, y: ComplexInterval
) -> ComplexInterval:
    return (
        _real_sub(_real_mul(x[0], y[0]), _real_mul(x[1], y[1])),
        _real_add(_real_mul(x[0], y[1]), _real_mul(x[1], y[0])),
    )


def _complex_scale(
    x: ComplexInterval, y: RealInterval
) -> ComplexInterval:
    return _real_mul(x[0], y), _real_mul(x[1], y)


def _complex_divide_positive(
    x: ComplexInterval, denominator: float
) -> ComplexInterval:
    return (
        _real_divide_positive(x[0], denominator),
        _real_divide_positive(x[1], denominator),
    )


def _complex_power(
    base: ComplexInterval, exponent: int
) -> ComplexInterval:
    if not 0 <= exponent <= (1 << 64) - 1:
        _fail("seed recurrence exponent is outside uint64")
    answer: ComplexInterval = ((1.0, 1.0), (0.0, 0.0))
    while exponent:
        if exponent & 1:
            answer = _complex_mul(answer, base)
        exponent >>= 1
        if exponent:
            base = _complex_mul(base, base)
    return answer


def _independent_uniform_tail(t_index: int) -> float:
    """Re-derive the direct path's global Taylor tail without its producer."""

    if not 0 <= t_index <= SOURCE_MAX_T_INDEX:
        _fail("Taylor-tail ordinate is outside the bounded checker range")
    maximum_delta = Fraction(
        seed_format.SOURCE_MAX_Q - LATTICE_ROWS,
        LATTICE_ROWS * seed_format.SOURCE_MAX_Q,
    )
    if (
        maximum_delta
        != Fraction(1, LATTICE_ROWS)
        - Fraction(1, seed_format.SOURCE_MAX_Q)
        or maximum_delta < Fraction(1, 2 * LATTICE_ROWS)
        or maximum_delta >= Fraction(1, LATTICE_ROWS)
    ):
        _fail("global clipped-row displacement identity differs")
    t = Fraction(
        SOURCE_SAMPLE_NUMERATOR * t_index,
        SOURCE_SAMPLE_DENOMINATOR,
    )
    first_omitted_index = TAYLOR_DEGREE + 1
    base = seed_format.SOURCE_M + 1
    zeta_tail = Fraction(1, base**first_omitted_index) + Fraction(
        2,
        (2 * first_omitted_index - 1)
        * base ** (first_omitted_index - 1),
    )
    pochhammer = Fraction(1)
    for j in range(first_omitted_index):
        pochhammer *= t + Fraction(2 * j + 1, 2)
    first_omitted = (
        maximum_delta**first_omitted_index
        * pochhammer
        * zeta_tail
        / math.factorial(first_omitted_index)
    )
    norm_bound = t + Fraction(1, 2)
    ratio_factor = max(
        Fraction(1),
        (norm_bound + first_omitted_index)
        / (first_omitted_index + 1),
    )
    ratio = maximum_delta * ratio_factor / base
    if not 0 <= ratio < 1:
        _fail("independent Taylor-tail ratio is not geometric")
    return _round_exact(
        first_omitted / (1 - ratio), upward=True
    )


def _exact_arb_endpoint(value: Any, *, lower: bool) -> Fraction:
    endpoint = value.lower() if lower else value.upper()
    if not endpoint.is_exact():
        _fail("Arb did not expose an exact factor endpoint")
    rational = endpoint.fmpq()
    return Fraction(int(rational.p), int(rational.q))


def _independent_arb_factor_replay(
    block: "_Block", *, precision_bits: int
) -> tuple[int, dict[str, Any]]:
    """Contain every stored MPFR box around a separately evaluated Arb box."""

    if precision_bits < 320:
        _fail("independent Arb factor replay requires at least 320 bits")
    try:
        import flint  # type: ignore[import-not-found]
    except ImportError as error:
        raise DirichletTMajorCudaArithmeticReplayError(
            "independent factor replay requires pinned python-flint"
        ) from error
    if (
        str(flint.__version__) != "0.9.0"
        or str(flint.__FLINT_VERSION__) != "3.6.0"
        or int(flint.__FLINT_RELEASE__) != 30_600
    ):
        _fail("independent factor replay loaded an unpinned Arb/FLINT runtime")
    old_threads = flint.ctx.threads
    flint.ctx.threads = 1
    replayed = 0
    try:
        with flint.ctx.workprec(precision_bits):
            for target in block.targets:
                for frame, outer in enumerate(target.factors):
                    t_numerator = (
                        target.first_t_numerator
                        + frame * target.t_step_numerator
                    )
                    exact_t = (
                        flint.arb(t_numerator) / target.t_denominator
                    )
                    s = flint.acb(flint.arb(1) / 2, exact_t)
                    value = flint.acb(target.q) ** (-s)
                    real_lo = _exact_arb_endpoint(
                        value.real, lower=True
                    )
                    real_hi = _exact_arb_endpoint(
                        value.real, lower=False
                    )
                    imag_lo = _exact_arb_endpoint(
                        value.imag, lower=True
                    )
                    imag_hi = _exact_arb_endpoint(
                        value.imag, lower=False
                    )
                    if not (
                        Fraction.from_float(outer[0][0]) <= real_lo
                        and real_hi <= Fraction.from_float(outer[0][1])
                        and Fraction.from_float(outer[1][0]) <= imag_lo
                        and imag_hi <= Fraction.from_float(outer[1][1])
                    ):
                        _fail(
                            "independent Arb factor escaped the stored MPFR box"
                        )
                    replayed += 1
    finally:
        flint.ctx.threads = old_threads
    from tg_verifier.dirichlet_lattice_certificates import (
        runtime_identity,
    )

    runtime = runtime_identity(flint)
    runtime["precision_bits"] = precision_bits
    return replayed, runtime


@dataclass(frozen=True)
class _Target:
    q: int
    component_count: int
    batch_count: int
    group_order: int
    first_t_numerator: int
    t_denominator: int
    t_step_numerator: int
    value_count: int
    factors: tuple[ComplexInterval, ...]
    tails: tuple[float, ...]


@dataclass(frozen=True)
class _Block:
    lane_index: int
    first_t_index: int
    rows: tuple[bytes, ...]
    targets: tuple[_Target, ...]
    artifact_sha256: str
    artifact_size: int
    sidecar_mode: int


def _active_qs(
    q_start: int, q_stop: int, first_t_index: int
) -> tuple[int, ...]:
    return tuple(
        q
        for q in range(q_start, q_stop + 1)
        if (
            has_primitive_character_modulus(q)
            and first_t_index <= maximum_t_index(q)
        )
    )


def _target_sidecar_digest(
    target: _Target, factor_raw: bytes, tail_raw: bytes
) -> bytes:
    digest = hashlib.sha256(TARGET_SIDECAR_DOMAIN)
    digest.update(
        struct.pack(
            "<IIqQ",
            target.q,
            target.batch_count,
            target.first_t_numerator,
            target.group_order,
        )
    )
    digest.update(factor_raw)
    digest.update(tail_raw)
    return digest.digest()


def _load_bounded_block(
    path: Path,
    receipt: Mapping[str, Any],
    *,
    maximum_targets: int,
    maximum_block_bytes: int,
) -> _Block:
    with _open_regular(path, label="TGDLTMB1 arithmetic-replay input") as source:
        initial = os.fstat(source.fileno())
        if not 1 <= initial.st_size <= maximum_block_bytes:
            _fail("TGDLTMB1 exceeds the bounded arithmetic-replay size")
        digest = hashlib.sha256()
        raw_header = _read_exact(
            source,
            BLOCK_HEADER.size,
            label="TGDLTMB1 header",
            digest=digest,
        )
        fields = BLOCK_HEADER.unpack(raw_header)
        (
            magic,
            version,
            lane_index,
            row_count,
            target_count,
            q_start,
            q_stop,
            _m,
            sidecar_mode,
            first_t_index,
            block_stop,
            row_payload_bytes,
            row_record_bytes,
            target_header_bytes,
            raw_contract,
            raw_spool,
            raw_rows,
            raw_seed,
            raw_seed_replay,
            raw_sidecar,
        ) = fields
        accounting = receipt.get("accounting")
        sidecar_source = receipt.get("sidecar_source")
        if not isinstance(accounting, dict) or not isinstance(
            sidecar_source, dict
        ):
            _fail("TGDLTMB1 receipt accounting is malformed")
        expected_sidecar = (
            sidecar_source.get("recipe", {}).get("recipe_sha256")
            if sidecar_mode == SIDECAR_MODE_DIRECT_MPFR
            else sidecar_source.get("manifest", {}).get("sha256")
        )
        if (
            magic != BLOCK_MAGIC
            or version != FORMAT_VERSION
            or lane_index != receipt.get("lane_index")
            or row_count
            != accounting.get("authenticated_unique_row_count")
            or not 1 <= row_count <= MAXIMUM_BATCH_COUNT
            or target_count != accounting.get("active_target_count")
            or not 1 <= target_count <= maximum_targets
            or q_start != receipt.get("q_start_inclusive")
            or q_stop != receipt.get("q_stop_inclusive")
            or first_t_index != receipt.get("first_t_index")
            or block_stop != receipt.get("t_index_stop_exclusive")
            or block_stop != first_t_index + row_count
            or row_payload_bytes != ROW_PAYLOAD_BYTES
            or row_record_bytes != ROW_HEADER.size + ROW_PAYLOAD_BYTES
            or target_header_bytes != TARGET_HEADER.size
            or raw_contract.hex() != receipt.get("source_contract_sha256")
            or raw_spool.hex() != receipt.get("spool_receipt_sha256")
            or raw_rows.hex() != receipt.get("row_bindings_sha256")
            or raw_seed.hex()
            != receipt.get("recovery_seed_artifact_sha256")
            or raw_seed_replay.hex()
            != receipt.get("recovery_seed_replay_sha256")
            or raw_sidecar.hex() != expected_sidecar
        ):
            _fail("TGDLTMB1 header differs from its typed receipt")

        row_stream = hashlib.sha256()
        rows: list[bytes] = []
        for offset in range(row_count):
            raw_row = _read_exact(
                source,
                ROW_HEADER.size,
                label="TGDLTMB1 row header",
                digest=digest,
            )
            row_stream.update(raw_row)
            (
                row_magic,
                row_version,
                reserved,
                t_index,
                payload_bytes,
                payload_sha,
            ) = ROW_HEADER.unpack(raw_row)
            payload = _read_exact(
                source,
                ROW_PAYLOAD_BYTES,
                label="TGDLTMB1 row payload",
                digest=digest,
            )
            row_stream.update(payload)
            if (
                row_magic != ROW_MAGIC
                or row_version != FORMAT_VERSION
                or reserved != 0
                or t_index != first_t_index + offset
                or payload_bytes != ROW_PAYLOAD_BYTES
                or hashlib.sha256(payload).digest() != payload_sha
            ):
                _fail("TGDLTMB1 row identity differs during arithmetic replay")
            rows.append(payload)

        q_roster = _active_qs(q_start, q_stop, first_t_index)
        if len(q_roster) != target_count:
            _fail("TGDLTMB1 active target roster differs")
        target_stream = hashlib.sha256()
        targets: list[_Target] = []
        total_target_rows = 0
        total_values = 0
        total_sidecar_bytes = 0
        for q in q_roster:
            raw_target = _read_exact(
                source,
                TARGET_HEADER.size,
                label="TGDLTMB1 target header",
                digest=digest,
            )
            target_stream.update(raw_target)
            target_fields = TARGET_HEADER.unpack(raw_target)
            (
                target_magic,
                target_version,
                target_q,
                component_count,
                batch_count,
                reserved0,
                reserved1,
                group_order,
                first_t_numerator,
                denominator,
                step,
                value_count,
                factor_bytes,
                tail_bytes,
                sidecar_sha,
            ) = target_fields
            expected_batch = (
                min(block_stop, maximum_t_index(q) + 1) - first_t_index
            )
            expected_orders = canonical_component_orders(q)
            if (
                target_magic != TARGET_MAGIC
                or target_version != FORMAT_VERSION
                or target_q != q
                or component_count != len(expected_orders)
                or batch_count != expected_batch
                or reserved0 != 0
                or reserved1 != 0
                or group_order != math.prod(expected_orders)
                or first_t_numerator
                != first_t_index * SOURCE_SAMPLE_NUMERATOR
                or denominator != SOURCE_SAMPLE_DENOMINATOR
                or step != SOURCE_SAMPLE_NUMERATOR
                or value_count != batch_count * group_order
                or factor_bytes != batch_count * COMPLEX_INTERVAL.size
                or tail_bytes != batch_count * 8
            ):
                _fail("TGDLTMB1 target geometry differs during arithmetic replay")
            factor_raw = _read_exact(
                source,
                factor_bytes,
                label="TGDLTMB1 factors",
                digest=digest,
            )
            tail_raw = _read_exact(
                source,
                tail_bytes,
                label="TGDLTMB1 tails",
                digest=digest,
            )
            target_stream.update(factor_raw)
            target_stream.update(tail_raw)
            factors = tuple(
                _as_complex(
                    tuple(values),
                    label=f"q={q} factor",
                )
                for values in COMPLEX_INTERVAL.iter_unpack(factor_raw)
            )
            tails = tuple(value[0] for value in struct.iter_unpack("<d", tail_raw))
            if any(
                not math.isfinite(value) or value < 0.0 for value in tails
            ):
                _fail("TGDLTMB1 Taylor tail is malformed")
            target = _Target(
                q=q,
                component_count=component_count,
                batch_count=batch_count,
                group_order=group_order,
                first_t_numerator=first_t_numerator,
                t_denominator=denominator,
                t_step_numerator=step,
                value_count=value_count,
                factors=factors,
                tails=tails,
            )
            if _target_sidecar_digest(
                target, factor_raw, tail_raw
            ) != sidecar_sha:
                _fail("TGDLTMB1 target sidecar digest differs")
            targets.append(target)
            total_target_rows += batch_count
            total_values += value_count
            total_sidecar_bytes += factor_bytes + tail_bytes

        raw_footer = _read_exact(
            source,
            BLOCK_FOOTER.size,
            label="TGDLTMB1 footer",
            digest=digest,
        )
        if source.read(1):
            _fail("TGDLTMB1 has trailing bytes")
        footer = BLOCK_FOOTER.unpack(raw_footer)
        if (
            footer[0] != FOOTER_MAGIC
            or footer[1] != FORMAT_VERSION
            or footer[2] != 0
            or footer[3] != row_count
            or footer[4] != target_count
            or footer[5] != total_target_rows
            or footer[6] != total_values
            or footer[7] != total_sidecar_bytes
            or footer[9] != row_stream.digest()
            or footer[10] != target_stream.digest()
        ):
            _fail("TGDLTMB1 footer differs during arithmetic replay")
        if _identity(os.fstat(source.fileno())) != _identity(initial):
            _fail("TGDLTMB1 changed during arithmetic replay")
        observed_sha = digest.hexdigest()
        artifact = receipt.get("artifact")
        if (
            not isinstance(artifact, dict)
            or artifact.get("path") != str(path.resolve())
            or artifact.get("sha256") != observed_sha
            or artifact.get("size_bytes") != initial.st_size
        ):
            _fail("TGDLTMB1 artifact differs from its typed receipt")
    return _Block(
        lane_index=lane_index,
        first_t_index=first_t_index,
        rows=tuple(rows),
        targets=tuple(targets),
        artifact_sha256=observed_sha,
        artifact_size=initial.st_size,
        sidecar_mode=sidecar_mode,
    )


def _sample_indices(total: int, maximum: int) -> tuple[int, ...]:
    if maximum >= total:
        return tuple(range(total))
    if maximum == 1:
        return (0,)
    return tuple(
        sorted(
            {
                index * (total - 1) // (maximum - 1)
                for index in range(maximum)
            }
        )
    )


def _load_output_samples(
    path: Path,
    block: _Block,
    *,
    expected_sha256: str,
    maximum_values_per_target: int,
    maximum_output_bytes: int,
) -> tuple[
    dict[tuple[int, int], tuple[float, float, float, float]],
    int,
    str,
]:
    expected_sha256 = _digest(expected_sha256, "expected TGDAFFI1 stream")
    observations: dict[
        tuple[int, int], tuple[float, float, float, float]
    ] = {}
    with _open_regular(path, label="TGDAFFI1 arithmetic-replay output") as source:
        initial = os.fstat(source.fileno())
        if not 1 <= initial.st_size <= maximum_output_bytes:
            _fail("TGDAFFI1 exceeds the bounded arithmetic-replay size")
        digest = hashlib.sha256()
        expected_size = 0
        for target_index, target in enumerate(block.targets):
            raw_header = _read_exact(
                source,
                TGDAFFI_HEADER.size,
                label="TGDAFFI1 frame header",
                digest=digest,
            )
            expected_size += TGDAFFI_HEADER.size
            header = TGDAFFI_HEADER.unpack(raw_header)
            if header != (
                TGDAFFI_MAGIC,
                1,
                target.q,
                target.component_count,
                target.batch_count,
                target.group_order,
                target.first_t_numerator,
                target.t_denominator,
                target.t_step_numerator,
                target.value_count,
                0,
            ):
                _fail("TGDAFFI1 frame header differs from TGDLTMB1")
            selected = _sample_indices(
                target.value_count, maximum_values_per_target
            )
            selected_cursor = 0
            value_base = 0
            remaining = target.value_count
            values_per_chunk = 1 << 12
            while remaining:
                count = min(remaining, values_per_chunk)
                raw = _read_exact(
                    source,
                    count * COMPLEX_INTERVAL.size,
                    label="TGDAFFI1 frame values",
                    digest=digest,
                )
                for local_index, endpoints in enumerate(
                    COMPLEX_INTERVAL.iter_unpack(raw)
                ):
                    _finite_ordered_box(
                        tuple(endpoints),
                        label="TGDAFFI1 output value",
                    )
                    flat = value_base + local_index
                    if (
                        selected_cursor < len(selected)
                        and flat == selected[selected_cursor]
                    ):
                        observations[(target_index, flat)] = tuple(endpoints)
                        selected_cursor += 1
                value_base += count
                remaining -= count
            if selected_cursor != len(selected):
                _fail("TGDAFFI1 deterministic sample roster was incomplete")
            expected_size += target.value_count * COMPLEX_INTERVAL.size
        if source.read(1):
            _fail("TGDAFFI1 stream has trailing bytes")
        if (
            expected_size != initial.st_size
            or _identity(os.fstat(source.fileno())) != _identity(initial)
        ):
            _fail("TGDAFFI1 size or file identity changed during replay")
        observed_sha = digest.hexdigest()
        if observed_sha != expected_sha256:
            _fail("TGDAFFI1 stream digest differs from its external pin")
    return observations, initial.st_size, observed_sha


def _load_seed_lookup(
    path: Path,
    required_x: frozenset[int],
    *,
    expected_sha256: str,
) -> tuple[dict[int, tuple[float, ...]], int]:
    expected_sha256 = _digest(
        expected_sha256, "expected recovery-seed artifact"
    )
    found: dict[int, tuple[float, ...]] = {}
    with _open_regular(path, label="recovery-seed arithmetic-replay input") as source:
        initial = os.fstat(source.fileno())
        if not (
            seed_format.HEADER.size
            + seed_format.CHUNK_HEADER.size
            + seed_format.SEED_RECORD.size
            + seed_format.FOOTER.size
            <= initial.st_size
            <= seed_format.MAXIMUM_ARTIFACT_BYTES
        ):
            _fail("recovery-seed artifact size is outside its fixed bound")
        artifact_digest = hashlib.sha256()
        raw_header = _read_exact(
            source,
            seed_format.HEADER.size,
            label="recovery-seed header",
            digest=artifact_digest,
        )
        (
            magic,
            version,
            m,
            maximum_q,
            record_size,
            x_start,
            x_stop,
            step_numerator,
            step_denominator,
            record_count,
            generation_precision,
            union_precision,
            chunk_records,
            reserved0,
            reserved1,
        ) = seed_format.HEADER.unpack(raw_header)
        if (
            magic != seed_format.HEADER_MAGIC
            or version != seed_format.FORMAT_VERSION
            or m != seed_format.SOURCE_M
            or maximum_q != seed_format.SOURCE_MAX_Q
            or record_size != seed_format.SEED_RECORD.size
            or x_start != seed_format.SOURCE_X_START
            or not x_start <= x_stop <= seed_format.SOURCE_X_STOP
            or step_numerator != seed_format.SOURCE_STEP_NUMERATOR
            or step_denominator != seed_format.SOURCE_STEP_DENOMINATOR
            or record_count != x_stop - x_start + 1
            or generation_precision < 128
            or union_precision
            != generation_precision
            + seed_format.DEFAULT_REPLAY_GUARD_BITS
            or not 1
            <= chunk_records
            <= seed_format.MAXIMUM_CHUNK_RECORDS
            or reserved0 != 0
            or reserved1 != 0
            or any(not x_start <= x <= x_stop for x in required_x)
        ):
            _fail("recovery-seed header or required coverage differs")

        records_digest = hashlib.sha256()
        root_digest = hashlib.sha256(seed_format.ROOT_DOMAIN)
        remaining = record_count
        expected_x = x_start
        observed_chunks = 0
        while remaining:
            raw_chunk = _read_exact(
                source,
                seed_format.CHUNK_HEADER.size,
                label="recovery-seed chunk header",
                digest=artifact_digest,
            )
            (
                chunk_magic,
                chunk_version,
                chunk_reserved,
                first_x,
                count,
                claimed_chunk_sha,
            ) = seed_format.CHUNK_HEADER.unpack(raw_chunk)
            expected_count = min(chunk_records, remaining)
            if (
                chunk_magic != seed_format.CHUNK_MAGIC
                or chunk_version != seed_format.FORMAT_VERSION
                or chunk_reserved != 0
                or first_x != expected_x
                or count != expected_count
            ):
                _fail("recovery-seed chunk geometry differs")
            payload = _read_exact(
                source,
                count * seed_format.SEED_RECORD.size,
                label="recovery-seed chunk payload",
                digest=artifact_digest,
            )
            chunk_digest = hashlib.sha256(
                seed_format.CHUNK_DOMAIN
                + first_x.to_bytes(8, "little")
                + count.to_bytes(8, "little")
                + payload
            ).digest()
            if chunk_digest != claimed_chunk_sha:
                _fail("recovery-seed chunk digest differs")
            for offset, record in enumerate(
                seed_format.SEED_RECORD.iter_unpack(payload)
            ):
                if (
                    not all(math.isfinite(value) for value in record)
                    or not 0.0 < record[0] <= record[1] <= 1.0
                    or not -1.0 <= record[2] <= record[3] <= 1.0
                    or not -1.0 <= record[4] <= record[5] <= 1.0
                ):
                    _fail("recovery-seed record is malformed")
                x = first_x + offset
                if x in required_x:
                    found[x] = tuple(record)
            records_digest.update(payload)
            root_digest.update(chunk_digest)
            expected_x += count
            remaining -= count
            observed_chunks += 1

        raw_footer = _read_exact(
            source,
            seed_format.FOOTER.size,
            label="recovery-seed footer",
            digest=artifact_digest,
        )
        if source.read(1):
            _fail("recovery-seed artifact has trailing bytes")
        footer = seed_format.FOOTER.unpack(raw_footer)
        if (
            footer[0] != seed_format.FOOTER_MAGIC
            or footer[1] != seed_format.FORMAT_VERSION
            or footer[2] != 0
            or footer[3] != record_count
            or footer[4] != observed_chunks
            or footer[5] != records_digest.digest()
            or footer[6] != root_digest.digest()
            or artifact_digest.hexdigest() != expected_sha256
            or _identity(os.fstat(source.fileno())) != _identity(initial)
        ):
            _fail("recovery-seed footer or external identity differs")
    if set(found) != set(required_x):
        _fail("recovery-seed artifact omitted a sampled recurrence input")
    return found, initial.st_size


def _lattice_value(
    payload: bytes, *, row: int, column: int
) -> ComplexInterval:
    if (
        len(payload) != ROW_PAYLOAD_BYTES
        or not 1 <= row <= LATTICE_ROWS
        or not 0 <= column < TAYLOR_COLUMNS
    ):
        _fail("sampled lattice coordinate is outside TGDLTMB1")
    offset = (
        ((row - 1) * TAYLOR_COLUMNS + column)
        * COMPLEX_INTERVAL.size
    )
    return _as_complex(
        tuple(COMPLEX_INTERVAL.unpack_from(payload, offset)),
        label="sampled lattice value",
    )


def _recompute_value(
    block: _Block,
    target: _Target,
    *,
    flat: int,
    residues: tuple[int, ...],
    seeds: Mapping[int, tuple[float, ...]],
) -> ComplexInterval:
    frame, position = divmod(flat, target.group_order)
    if (
        not 0 <= frame < target.batch_count
        or len(residues) != target.group_order
    ):
        _fail("sampled TGDAFFI1 coordinate is outside its target")
    a = residues[position]
    row = canonical_lattice_row(target.q, a)
    t_numerator = (
        target.first_t_numerator + frame * target.t_step_numerator
    )
    if (
        t_numerator < 0
        or t_numerator % seed_format.SOURCE_STEP_NUMERATOR
        or t_numerator > MAXIMUM_EXACT_INTEGER_AS_BINARY64
    ):
        _fail("sampled ordinate is not an exact uint64 source-grid index")
    t_index = t_numerator // seed_format.SOURCE_STEP_NUMERATOR
    minus_delta = _real_sub(
        _rational_nonnegative(row, LATTICE_ROWS),
        _rational_nonnegative(a, target.q),
    )
    t = _rational_nonnegative(t_numerator, target.t_denominator)
    power: ComplexInterval = ((1.0, 1.0), (0.0, 0.0))
    zeta: ComplexInterval = ((0.0, 0.0), (0.0, 0.0))
    payload = block.rows[frame]
    for column in range(TAYLOR_DEGREE + 1):
        zeta = _complex_add(
            zeta,
            _complex_mul(
                power,
                _lattice_value(payload, row=row, column=column),
            ),
        )
        if column != TAYLOR_DEGREE:
            s_plus_column: ComplexInterval = (
                (float(column) + 0.5, float(column) + 0.5),
                t,
            )
            power = _complex_divide_positive(
                _complex_scale(
                    _complex_mul(power, s_plus_column),
                    minus_delta,
                ),
                float(column + 1),
            )
    tail = target.tails[frame]
    zeta = (
        (
            _directed_sub(zeta[0][0], tail, upward=False),
            _directed_add(zeta[0][1], tail, upward=True),
        ),
        (
            _directed_sub(zeta[1][0], tail, upward=False),
            _directed_add(zeta[1][1], tail, upward=True),
        ),
    )

    recovery: ComplexInterval = ((0.0, 0.0), (0.0, 0.0))
    for n in range(seed_format.SOURCE_M + 1):
        x = target.q * n + a
        record = seeds.get(x)
        if record is None:
            _fail("sampled recovery seed is missing")
        phase: ComplexInterval = (
            (record[2], record[3]),
            (record[4], record[5]),
        )
        term = _complex_power(phase, t_index)
        amplitude: RealInterval = (record[0], record[1])
        recovery = _complex_add(
            recovery,
            (
                _real_mul(term[0], amplitude),
                _real_mul(term[1], amplitude),
            ),
        )
    return _complex_add(
        _complex_mul(target.factors[frame], zeta),
        recovery,
    )


def replay_tmajor_cuda_arithmetic_sample(
    artifact_path: Path,
    receipt_path: Path,
    seed_artifact_path: Path,
    output_stream_path: Path,
    *,
    expected_receipt_sha256: str,
    expected_seed_artifact_sha256: str,
    expected_output_stream_sha256: str,
    maximum_targets: int = DEFAULT_MAXIMUM_TARGETS,
    maximum_values_per_target: int = DEFAULT_MAXIMUM_VALUES_PER_TARGET,
    maximum_block_bytes: int = DEFAULT_MAXIMUM_BLOCK_BYTES,
    maximum_output_bytes: int = DEFAULT_MAXIMUM_OUTPUT_BYTES,
    independent_arb_factor_precision_bits: int | None = None,
) -> dict[str, Any]:
    """Recompute a deterministic bounded roster of CUDA output values exactly."""

    maximum_targets = _positive_integer(
        maximum_targets, "maximum targets", maximum=64
    )
    maximum_values_per_target = _positive_integer(
        maximum_values_per_target,
        "maximum values per target",
        maximum=64,
    )
    maximum_block_bytes = _positive_integer(
        maximum_block_bytes,
        "maximum block bytes",
        maximum=4 * 1024 * 1024 * 1024,
    )
    maximum_output_bytes = _positive_integer(
        maximum_output_bytes,
        "maximum output bytes",
        maximum=4 * 1024 * 1024 * 1024,
    )
    expected_receipt_sha256 = _digest(
        expected_receipt_sha256, "expected TGDLTMB1 receipt"
    )
    expected_seed_artifact_sha256 = _digest(
        expected_seed_artifact_sha256,
        "expected recovery-seed artifact",
    )
    expected_output_stream_sha256 = _digest(
        expected_output_stream_sha256,
        "expected TGDAFFI1 output stream",
    )
    receipt = replay_tmajor_cuda_block(
        artifact_path,
        receipt_path,
        expected_receipt_sha256=expected_receipt_sha256,
    )
    if (
        receipt.get("recovery_seed_artifact_sha256")
        != expected_seed_artifact_sha256
    ):
        _fail("recovery-seed pin differs from the TGDLTMB1 receipt")
    block = _load_bounded_block(
        artifact_path,
        receipt,
        maximum_targets=maximum_targets,
        maximum_block_bytes=maximum_block_bytes,
    )
    independently_replayed_tails = 0
    if block.sidecar_mode == SIDECAR_MODE_DIRECT_MPFR:
        for target in block.targets:
            for frame, tail in enumerate(target.tails):
                t_numerator = (
                    target.first_t_numerator
                    + frame * target.t_step_numerator
                )
                if (
                    t_numerator < 0
                    or t_numerator % SOURCE_SAMPLE_NUMERATOR
                ):
                    _fail("direct Taylor-tail ordinate is off the source grid")
                if (
                    _independent_uniform_tail(
                        t_numerator // SOURCE_SAMPLE_NUMERATOR
                    )
                    != tail
                ):
                    _fail(
                        "independent exact-rational Taylor-tail replay differs"
                    )
                independently_replayed_tails += 1
    independently_replayed_factors = 0
    arb_runtime: dict[str, Any] | None = None
    if independent_arb_factor_precision_bits is not None:
        if block.sidecar_mode != SIDECAR_MODE_DIRECT_MPFR:
            _fail("independent Arb factor replay requires direct sidecars")
        if (
            isinstance(independent_arb_factor_precision_bits, bool)
            or not isinstance(independent_arb_factor_precision_bits, int)
        ):
            _fail("independent Arb factor precision is not an integer")
        (
            independently_replayed_factors,
            arb_runtime,
        ) = _independent_arb_factor_replay(
            block,
            precision_bits=independent_arb_factor_precision_bits,
        )
    observations, output_size, output_sha256 = _load_output_samples(
        output_stream_path,
        block,
        expected_sha256=expected_output_stream_sha256,
        maximum_values_per_target=maximum_values_per_target,
        maximum_output_bytes=maximum_output_bytes,
    )

    residue_orders: dict[int, tuple[int, ...]] = {}
    required_x: set[int] = set()
    for target_index, target in enumerate(block.targets):
        residues = canonical_residue_order(target.q)
        residue_orders[target.q] = residues
        for flat in _sample_indices(
            target.value_count, maximum_values_per_target
        ):
            _frame, position = divmod(flat, target.group_order)
            a = residues[position]
            for n in range(seed_format.SOURCE_M + 1):
                required_x.add(target.q * n + a)
    seed_lookup, seed_size = _load_seed_lookup(
        seed_artifact_path,
        frozenset(required_x),
        expected_sha256=expected_seed_artifact_sha256,
    )

    roster_digest = hashlib.sha256()
    sampled = 0
    for target_index, target in enumerate(block.targets):
        for flat in _sample_indices(
            target.value_count, maximum_values_per_target
        ):
            expected = _flatten(
                _recompute_value(
                    block,
                    target,
                    flat=flat,
                    residues=residue_orders[target.q],
                    seeds=seed_lookup,
                )
            )
            observed = observations[(target_index, flat)]
            # IEEE +0 and -0 are the same interval endpoint.  Every other
            # endpoint must be exactly the same binary64 value.
            if expected != observed:
                _fail(
                    f"exact directed arithmetic differs at q={target.q}, "
                    f"flat={flat}"
                )
            roster_digest.update(
                struct.pack("<IQ", target.q, flat)
            )
            roster_digest.update(COMPLEX_INTERVAL.pack(*observed))
            sampled += 1

    total_values = sum(target.value_count for target in block.targets)
    implementation_path = Path(__file__).resolve()
    implementation_raw = implementation_path.read_bytes()
    body: dict[str, Any] = {
        "schema": REPLAY_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "algorithm_id": ALGORITHM_ID,
        "checker_id": CHECKER_ID,
        "classification": (
            "bounded_exact_directed_cuda_arithmetic_replay_not_source_scale"
        ),
        "input_receipt_sha256": expected_receipt_sha256,
        "input_artifact": {
            "sha256": block.artifact_sha256,
            "size_bytes": block.artifact_size,
        },
        "recovery_seed_artifact": {
            "sha256": expected_seed_artifact_sha256,
            "size_bytes": seed_size,
        },
        "output_stream": {
            "sha256": output_sha256,
            "size_bytes": output_size,
        },
        "checker_implementation": {
            "filename": implementation_path.name,
            "sha256": hashlib.sha256(implementation_raw).hexdigest(),
            "size_bytes": len(implementation_raw),
        },
        "bounds": {
            "maximum_targets": maximum_targets,
            "maximum_values_per_target": maximum_values_per_target,
            "maximum_block_bytes": maximum_block_bytes,
            "maximum_output_bytes": maximum_output_bytes,
        },
        "row_count": len(block.rows),
        "target_count": len(block.targets),
        "total_output_value_count": total_values,
        "sampled_output_value_count": sampled,
        "sample_roster_and_values_sha256": roster_digest.hexdigest(),
        "exact_fraction_intermediate_rounding_used": True,
        "directed_binary64_cuda_endpoints_matched": True,
        "complete_streams_authenticated": True,
        "direct_MPFR_factor_and_exact_tail_replay_inherited_from_input_receipt": (
            block.sidecar_mode == SIDECAR_MODE_DIRECT_MPFR
        ),
        "independent_exact_rational_global_tail_count": (
            independently_replayed_tails
        ),
        "independent_Arb_factor_containment_count": (
            independently_replayed_factors
        ),
        "independent_Arb_factor_runtime": arb_runtime,
        "recovery_seed_analytic_containment_replayed": False,
        "compiler_to_SASS_refinement_proved": False,
        "full_output_arithmetic_replayed": sampled == total_values,
        "source_scale_run": False,
        "trusted_execution_attested": False,
        "all_character_fft_executed": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }
    result = dict(body)
    result["replay_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def validate_tmajor_cuda_execution_arithmetic_sample(
    summary_path: Path,
    artifact_path: Path,
    receipt_path: Path,
    seed_artifact_path: Path,
    output_stream_path: Path,
    *,
    expected_summary_sha256: str,
    expected_receipt_sha256: str,
    expected_seed_artifact_sha256: str,
    maximum_targets: int = DEFAULT_MAXIMUM_TARGETS,
    maximum_values_per_target: int = DEFAULT_MAXIMUM_VALUES_PER_TARGET,
    maximum_block_bytes: int = DEFAULT_MAXIMUM_BLOCK_BYTES,
    maximum_output_bytes: int = DEFAULT_MAXIMUM_OUTPUT_BYTES,
    independent_arb_factor_precision_bits: int | None = None,
) -> dict[str, Any]:
    """Bind the bounded arithmetic replay to the typed CUDA summary."""

    summary = validate_tmajor_cuda_execution_summary(
        summary_path,
        artifact_path,
        receipt_path,
        expected_summary_sha256=expected_summary_sha256,
        expected_receipt_sha256=expected_receipt_sha256,
    )
    arithmetic = replay_tmajor_cuda_arithmetic_sample(
        artifact_path,
        receipt_path,
        seed_artifact_path,
        output_stream_path,
        expected_receipt_sha256=expected_receipt_sha256,
        expected_seed_artifact_sha256=expected_seed_artifact_sha256,
        expected_output_stream_sha256=summary["output_stream_sha256"],
        maximum_targets=maximum_targets,
        maximum_values_per_target=maximum_values_per_target,
        maximum_block_bytes=maximum_block_bytes,
        maximum_output_bytes=maximum_output_bytes,
        independent_arb_factor_precision_bits=(
            independent_arb_factor_precision_bits
        ),
    )
    body: dict[str, Any] = {
        "schema": TYPED_BUNDLE_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "algorithm_id": ALGORITHM_ID,
        "checker_id": CHECKER_ID,
        "classification": (
            "typed_bounded_arithmetic_qualification_not_source_scale"
        ),
        "input_receipt_sha256": expected_receipt_sha256,
        "execution_summary_replay_sha256": summary["replay_sha256"],
        "arithmetic_replay_sha256": arithmetic["replay_sha256"],
        "output_stream_sha256": summary["output_stream_sha256"],
        "summary_and_arithmetic_output_identity_equal": True,
        "sampled_output_value_count": arithmetic[
            "sampled_output_value_count"
        ],
        "full_output_arithmetic_replayed": arithmetic[
            "full_output_arithmetic_replayed"
        ],
        "source_scale_run": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }
    result = dict(body)
    result["bundle_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


__all__ = [
    "CHECKER_ID",
    "DirichletTMajorCudaArithmeticReplayError",
    "REPLAY_SCHEMA",
    "replay_tmajor_cuda_arithmetic_sample",
    "TYPED_BUNDLE_SCHEMA",
    "validate_tmajor_cuda_execution_arithmetic_sample",
]
