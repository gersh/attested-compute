# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Compact directed arithmetic for Platt's routine factor-eight interpolation.

The source computation first has real completed-L intervals on the ``5/64``
lattice.  At a nonaligned point of the routine eight-times finer lattice,
Platt's accepted-manuscript parameters use forty consecutive completed-value
intervals (twenty on each side), a Gaussian-windowed sinc coefficient, and a
uniform interpolation-error allowance.

This module deliberately separates three things:

* a tiny, Arb-generated and independently replayed 7-by-40 coefficient table;
* a bounded binary shard of already-certified completed-L input intervals;
* a two-bit strict-sign/ambiguity artifact checked with exact rational
  arithmetic on the binary64 endpoints.

The CUDA producer may accelerate the interval convolution, but a strict sign
is accepted by the checker only if exact rational interval multiplication of
the retained input and coefficient endpoints proves it.  The construction
does not certify the upstream completed-L values, the manuscript's uniform
``8.6e-8`` interpolation bound, zero multiplicity/completeness, a physical
CUDA implementation, or the external GRH theorem.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile
from typing import Any, NoReturn, Sequence

from tg_verifier.dirichlet_production_work import PINNED


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
SOURCE_URL = "https://arxiv.org/abs/1305.3087v1"
ACCEPTED_MANUSCRIPT_URL = (
    "https://research-information.bris.ac.uk/ws/portalfiles/portal/"
    "67056136/platt_grh3.0.pdf"
)
ALGORITHM_ID = "platt-dirichlet-factor8-directed-convolution-sign-pack-v1"
CHECKER_ID = "platt-dirichlet-factor8-exact-rational-endpoint-replay-v1"

UPSAMPLE_FACTOR = 8
TRUNCATION = 20
FIRST_TAP_OFFSET = -19
LAST_TAP_OFFSET = 20
TAP_COUNT = LAST_TAP_OFFSET - FIRST_TAP_OFFSET + 1
INTERPOLATED_PHASES = tuple(range(1, UPSAMPLE_FACTOR))
BANDWIDTH = Fraction(32, 5)
GAUSSIAN_H = Fraction(7, 32)
SOURCE_STEP = Fraction(5, 64)
SOURCE_INTERPOLATION_ERROR = Fraction(86, 1_000_000_000)

COEFFICIENT_MAGIC = b"TGDF8CF1"
INPUT_MAGIC = b"TGDF8IN1"
OUTPUT_MAGIC = b"TGDF8SG1"
FORMAT_VERSION = 1

COEFFICIENT_HEADER = struct.Struct("<8sIIIIiiiiii32s")
INPUT_HEADER = struct.Struct("<8sIIIIqQqQd32s32s32s")
OUTPUT_HEADER = struct.Struct("<8sIIIIqQQQQQII32s32s32s")
INTERVAL = struct.Struct("<dd")

NEGATIVE_CODE = 0
AMBIGUOUS_CODE = 1
POSITIVE_CODE = 2
RESERVED_CODE = 3
MAX_ITEMS = 1 << 28

COEFFICIENT_COUNT = len(INTERPOLATED_PHASES) * TAP_COUNT
COEFFICIENT_BYTES = COEFFICIENT_HEADER.size + COEFFICIENT_COUNT * INTERVAL.size

BASE_COMPLETED_VALUE_SAMPLES = PINNED["all_primitive_character_samples"]
FACTOR8_TARGET_SAMPLES = PINNED["factor_8_primitive_character_samples"]
FACTOR8_NONALIGNED_TARGET_SAMPLES = (
    FACTOR8_TARGET_SAMPLES - BASE_COMPLETED_VALUE_SAMPLES
)
FACTOR8_SINC_PRODUCT_TERMS = FACTOR8_NONALIGNED_TARGET_SAMPLES * TAP_COUNT


class Factor8PostprocessError(RuntimeError):
    """A coefficient, bounded wire artifact, or replay failed closed."""


def _fail(message: str) -> NoReturn:
    raise Factor8PostprocessError(message)


try:
    import flint
    from flint import arb, ctx
except ImportError as error:  # pragma: no cover - installation dependent
    flint = arb = ctx = None
    FLINT_IMPORT_ERROR = error
else:
    FLINT_IMPORT_ERROR = None


def require_flint() -> None:
    if FLINT_IMPORT_ERROR is not None:
        _fail(f"python-flint 0.9.0 / FLINT 3.6.0 is required: {FLINT_IMPORT_ERROR}")
    versions = (flint.__version__, flint.__FLINT_VERSION__, flint.__FLINT_RELEASE__)
    if versions != ("0.9.0", "3.6.0", 30_600):
        _fail(f"pinned FLINT versions differ: {versions}")


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def _sha256(raw: bytes) -> bytes:
    return hashlib.sha256(raw).digest()


def _digest(name: str, value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        if len(value) != 32:
            _fail(f"{name} must contain 32 digest bytes")
        return value
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{name} must be a lowercase SHA-256 digest")
    return bytes.fromhex(value)


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _dyadic(value: Any) -> Fraction:
    mantissa, exponent = value.mid().man_exp()
    mantissa = int(mantissa)
    exponent = int(exponent)
    if exponent >= 0:
        return Fraction(mantissa << exponent)
    return Fraction(mantissa, 1 << (-exponent))


def _arb_bounds(value: Any) -> tuple[Fraction, Fraction]:
    midpoint = _dyadic(value.mid())
    radius = abs(_dyadic(value.rad()))
    if radius == 0 and not value.is_exact():
        radius = Fraction(1, 1 << max(16, int(ctx.prec)))
    while True:
        candidate = arb(
            f"{midpoint.numerator}/{midpoint.denominator}",
            f"{radius.numerator}/{radius.denominator}",
        )
        if candidate.contains(value):
            return midpoint - radius, midpoint + radius
        radius = max(Fraction(1, 1 << max(16, int(ctx.prec))), 2 * radius)


def _float_down(value: Fraction) -> float:
    answer = float(value)
    while Fraction.from_float(answer) > value:
        answer = math.nextafter(answer, -math.inf)
    if not math.isfinite(answer):
        _fail("coefficient lower endpoint is not finite binary64")
    return answer


def _float_up(value: Fraction) -> float:
    answer = float(value)
    while Fraction.from_float(answer) < value:
        answer = math.nextafter(answer, math.inf)
    if not math.isfinite(answer):
        _fail("coefficient upper endpoint is not finite binary64")
    return answer


def _arb_fraction(value: Fraction) -> Any:
    return arb(f"{value.numerator}/{value.denominator}")


def source_coefficient(phase: int, tap_offset: int) -> Any:
    """Evaluate one accepted-manuscript Gaussian-sinc coefficient with Arb."""

    require_flint()
    if phase not in INTERPOLATED_PHASES:
        _fail("factor-eight coefficient phase must be in 1..7")
    if not FIRST_TAP_OFFSET <= tap_offset <= LAST_TAP_OFFSET:
        _fail("factor-eight tap offset is outside -19..20")
    displacement = Fraction(phase, UPSAMPLE_FACTOR) - tap_offset
    delta = displacement / (2 * BANDWIDTH)
    x = _arb_fraction(displacement)
    delta_arb = _arb_fraction(delta)
    pi = arb.pi()
    sinc = (pi * x).sin() / (pi * x)
    gaussian = (-(delta_arb**2) / (2 * _arb_fraction(GAUSSIAN_H) ** 2)).exp()
    return gaussian * sinc


def generate_coefficient_artifact(*, precision: int = 256) -> bytes:
    """Generate the complete 7-by-40 outward binary64 coefficient table."""

    require_flint()
    if not 192 <= precision <= 4096:
        _fail("coefficient precision must be in 192..4096")
    ctx.prec = precision
    payload = bytearray()
    for phase in INTERPOLATED_PHASES:
        for offset in range(FIRST_TAP_OFFSET, LAST_TAP_OFFSET + 1):
            lower, upper = _arb_bounds(source_coefficient(phase, offset))
            payload.extend(INTERVAL.pack(_float_down(lower), _float_up(upper)))
    payload_raw = bytes(payload)
    header = COEFFICIENT_HEADER.pack(
        COEFFICIENT_MAGIC,
        FORMAT_VERSION,
        UPSAMPLE_FACTOR,
        TRUNCATION,
        TAP_COUNT,
        BANDWIDTH.numerator,
        BANDWIDTH.denominator,
        GAUSSIAN_H.numerator,
        GAUSSIAN_H.denominator,
        FIRST_TAP_OFFSET,
        LAST_TAP_OFFSET,
        _sha256(payload_raw),
    )
    return header + payload_raw


def write_coefficient_artifact(path: Path, *, precision: int = 256) -> dict[str, Any]:
    raw = generate_coefficient_artifact(precision=precision)
    _atomic_write(path, raw)
    table = read_coefficient_artifact(raw)
    return {
        "algorithm_id": ALGORITHM_ID,
        "artifact_bytes": len(raw),
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "coefficient_count": len(table),
        "kind": "sparkinterval.tg.dirichlet_factor8.coefficients.v1",
        "source_parameters": source_parameters(),
    }


def read_coefficient_artifact(raw_or_path: bytes | Path) -> tuple[tuple[float, float], ...]:
    raw = raw_or_path if isinstance(raw_or_path, bytes) else raw_or_path.read_bytes()
    if len(raw) != COEFFICIENT_BYTES:
        _fail("factor-eight coefficient artifact length differs")
    fields = COEFFICIENT_HEADER.unpack_from(raw)
    (
        magic,
        version,
        factor,
        truncation,
        tap_count,
        bandwidth_numerator,
        bandwidth_denominator,
        h_numerator,
        h_denominator,
        first_offset,
        last_offset,
        payload_sha,
    ) = fields
    if (
        magic != COEFFICIENT_MAGIC
        or version != FORMAT_VERSION
        or factor != UPSAMPLE_FACTOR
        or truncation != TRUNCATION
        or tap_count != TAP_COUNT
        or Fraction(bandwidth_numerator, bandwidth_denominator) != BANDWIDTH
        or Fraction(h_numerator, h_denominator) != GAUSSIAN_H
        or first_offset != FIRST_TAP_OFFSET
        or last_offset != LAST_TAP_OFFSET
    ):
        _fail("factor-eight coefficient header differs")
    payload = raw[COEFFICIENT_HEADER.size :]
    if _sha256(payload) != payload_sha:
        _fail("factor-eight coefficient payload digest differs")
    intervals = tuple(INTERVAL.iter_unpack(payload))
    if len(intervals) != COEFFICIENT_COUNT:
        _fail("factor-eight coefficient count differs")
    if any(
        not math.isfinite(lower)
        or not math.isfinite(upper)
        or lower > upper
        or not (lower > 0.0 or upper < 0.0)
        for lower, upper in intervals
    ):
        _fail("factor-eight coefficient interval is invalid or crosses zero")
    return intervals


def verify_coefficient_artifact(
    raw_or_path: bytes | Path, *, precision: int = 320
) -> dict[str, Any]:
    """Freshly verify that every retained binary64 interval contains its weight."""

    require_flint()
    raw = raw_or_path if isinstance(raw_or_path, bytes) else raw_or_path.read_bytes()
    intervals = read_coefficient_artifact(raw)
    if not 256 <= precision <= 4096:
        _fail("coefficient replay precision must be in 256..4096")
    ctx.prec = precision
    index = 0
    maximum_width = Fraction()
    for phase in INTERPOLATED_PHASES:
        for offset in range(FIRST_TAP_OFFSET, LAST_TAP_OFFSET + 1):
            lower_float, upper_float = intervals[index]
            lower = Fraction.from_float(lower_float)
            upper = Fraction.from_float(upper_float)
            exact = source_coefficient(phase, offset)
            candidate = arb(
                f"{((lower + upper) / 2).numerator}/{((lower + upper) / 2).denominator}",
                f"{((upper - lower) / 2).numerator}/{((upper - lower) / 2).denominator}",
            )
            if not candidate.contains(exact):
                _fail(f"coefficient interval does not contain phase={phase}, tap={offset}")
            maximum_width = max(maximum_width, upper - lower)
            index += 1
    return {
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "coefficient_count": index,
        "complete_fresh_arb_replay": True,
        "kind": "sparkinterval.tg.dirichlet_factor8.coefficient_checker.v1",
        "maximum_binary64_interval_width": {
            "numerator": maximum_width.numerator,
            "denominator": maximum_width.denominator,
        },
        "precision_bits": precision,
        "physical_cuda_refinement_proved": False,
    }


def source_parameters() -> dict[str, Any]:
    return {
        "bandwidth": {
            "numerator": BANDWIDTH.numerator,
            "denominator": BANDWIDTH.denominator,
        },
        "gaussian_h": {
            "numerator": GAUSSIAN_H.numerator,
            "denominator": GAUSSIAN_H.denominator,
        },
        "interpolated_phases": list(INTERPOLATED_PHASES),
        "source_step": {
            "numerator": SOURCE_STEP.numerator,
            "denominator": SOURCE_STEP.denominator,
        },
        "tap_offsets": [FIRST_TAP_OFFSET, LAST_TAP_OFFSET],
        "truncation": TRUNCATION,
        "upsample_factor": UPSAMPLE_FACTOR,
    }


def work_audit() -> dict[str, Any]:
    """Expose the dimensional distinction hidden by the old sizing row."""

    return {
        "all_base_grid_completed_value_samples": BASE_COMPLETED_VALUE_SAMPLES,
        "factor8_target_grid_samples": FACTOR8_TARGET_SAMPLES,
        "factor8_aligned_targets_reusing_base_values": BASE_COMPLETED_VALUE_SAMPLES,
        "factor8_nonaligned_interpolated_targets": FACTOR8_NONALIGNED_TARGET_SAMPLES,
        "factor8_forty_tap_interval_products": FACTOR8_SINC_PRODUCT_TERMS,
        "classification": "exact_source_schedule_counts_not_execution_evidence",
        "old_100985_per_second_unit": (
            "one synthetic input interval term accumulated into one direct "
            "Whittaker-Shannon sum; not one factor-eight target"
        ),
        "source_parameters": source_parameters(),
    }


@dataclass(frozen=True)
class InputArtifact:
    q: int
    conrey_number: int
    parity: int
    first_base_index: int
    first_fine_index: int
    interpolation_error_upper: float
    intervals: tuple[tuple[float, float], ...]
    output_count: int
    coefficient_sha256: bytes
    upstream_sha256: bytes
    raw: bytes


def _validate_window(
    *,
    first_base_index: int,
    base_count: int,
    first_fine_index: int,
    output_count: int,
) -> None:
    if base_count <= 0 or output_count <= 0:
        _fail("factor-eight shard counts must be positive")
    if base_count > MAX_ITEMS or output_count > MAX_ITEMS:
        _fail("factor-eight shard exceeds the fixed 2^28 item bound")
    if first_base_index < 0 or first_fine_index < 0:
        _fail("factor-eight production indices must be nonnegative")
    if first_fine_index > (1 << 63) - 1 - (output_count - 1):
        _fail("factor-eight output index range overflows int64")
    first_source = first_base_index
    stop_source = first_base_index + base_count
    first_center = first_fine_index // UPSAMPLE_FACTOR
    last_center = (first_fine_index + output_count - 1) // UPSAMPLE_FACTOR
    if (
        first_center + FIRST_TAP_OFFSET < first_source
        or last_center + LAST_TAP_OFFSET >= stop_source
    ):
        _fail("factor-eight output window lies outside the retained input shard")


def make_input_artifact(
    *,
    q: int,
    conrey_number: int,
    parity: int,
    first_base_index: int,
    intervals: Sequence[tuple[float, float]],
    first_fine_index: int,
    output_count: int,
    interpolation_error_upper: float,
    coefficient_artifact_sha256: str | bytes,
    upstream_sha256: str | bytes,
) -> bytes:
    if (
        isinstance(q, bool)
        or not isinstance(q, int)
        or q < 2
        or isinstance(conrey_number, bool)
        or not isinstance(conrey_number, int)
        or not 1 <= conrey_number < q
        or parity not in (0, 1)
    ):
        _fail("factor-eight character identity is invalid")
    if (
        not math.isfinite(interpolation_error_upper)
        or interpolation_error_upper < 0.0
        or Fraction.from_float(interpolation_error_upper)
        < SOURCE_INTERPOLATION_ERROR
    ):
        _fail("factor-eight interpolation error upper bound is below 8.6e-8")
    _validate_window(
        first_base_index=first_base_index,
        base_count=len(intervals),
        first_fine_index=first_fine_index,
        output_count=output_count,
    )
    payload = bytearray()
    for lower, upper in intervals:
        if (
            not math.isfinite(lower)
            or not math.isfinite(upper)
            or lower > upper
        ):
            _fail("factor-eight input interval is invalid")
        payload.extend(INTERVAL.pack(lower, upper))
    payload_raw = bytes(payload)
    return INPUT_HEADER.pack(
        INPUT_MAGIC,
        FORMAT_VERSION,
        q,
        conrey_number,
        parity,
        first_base_index,
        len(intervals),
        first_fine_index,
        output_count,
        interpolation_error_upper,
        _digest("coefficient artifact", coefficient_artifact_sha256),
        _digest("upstream artifact", upstream_sha256),
        _sha256(payload_raw),
    ) + payload_raw


def read_input_artifact(raw_or_path: bytes | Path) -> InputArtifact:
    raw = raw_or_path if isinstance(raw_or_path, bytes) else raw_or_path.read_bytes()
    if len(raw) < INPUT_HEADER.size:
        _fail("truncated factor-eight input header")
    (
        magic,
        version,
        q,
        conrey,
        parity,
        first_base,
        base_count,
        first_fine,
        output_count,
        error_upper,
        coefficient_sha,
        upstream_sha,
        payload_sha,
    ) = INPUT_HEADER.unpack_from(raw)
    if magic != INPUT_MAGIC or version != FORMAT_VERSION:
        _fail("factor-eight input magic/version differs")
    expected = INPUT_HEADER.size + base_count * INTERVAL.size
    if len(raw) != expected:
        _fail("factor-eight input length or trailing bytes differ")
    if q < 2 or not 1 <= conrey < q or parity not in (0, 1):
        _fail("factor-eight input character identity is invalid")
    if (
        not math.isfinite(error_upper)
        or Fraction.from_float(error_upper) < SOURCE_INTERPOLATION_ERROR
    ):
        _fail("factor-eight input interpolation error is below 8.6e-8")
    _validate_window(
        first_base_index=first_base,
        base_count=base_count,
        first_fine_index=first_fine,
        output_count=output_count,
    )
    payload = raw[INPUT_HEADER.size :]
    if _sha256(payload) != payload_sha:
        _fail("factor-eight input payload digest differs")
    intervals = tuple(INTERVAL.iter_unpack(payload))
    if any(
        not math.isfinite(lower)
        or not math.isfinite(upper)
        or lower > upper
        for lower, upper in intervals
    ):
        _fail("factor-eight input interval is invalid")
    return InputArtifact(
        q=q,
        conrey_number=conrey,
        parity=parity,
        first_base_index=first_base,
        first_fine_index=first_fine,
        interpolation_error_upper=error_upper,
        intervals=intervals,
        output_count=output_count,
        coefficient_sha256=coefficient_sha,
        upstream_sha256=upstream_sha,
        raw=raw,
    )


def _product_bounds(
    left: tuple[Fraction, Fraction], right: tuple[Fraction, Fraction]
) -> tuple[Fraction, Fraction]:
    products = (
        left[0] * right[0],
        left[0] * right[1],
        left[1] * right[0],
        left[1] * right[1],
    )
    return min(products), max(products)


def exact_output_interval(
    shard: InputArtifact,
    coefficients: Sequence[tuple[float, float]],
    output_offset: int,
) -> tuple[Fraction, Fraction]:
    if not 0 <= output_offset < shard.output_count:
        _fail("factor-eight output offset is outside the shard")
    fine = shard.first_fine_index + output_offset
    center, phase = divmod(fine, UPSAMPLE_FACTOR)
    if phase == 0:
        lower, upper = shard.intervals[center - shard.first_base_index]
        return Fraction.from_float(lower), Fraction.from_float(upper)
    lower_sum = Fraction()
    upper_sum = Fraction()
    coefficient_base = (phase - 1) * TAP_COUNT
    for tap, source_index in enumerate(
        range(center + FIRST_TAP_OFFSET, center + LAST_TAP_OFFSET + 1)
    ):
        input_interval = tuple(
            Fraction.from_float(value)
            for value in shard.intervals[source_index - shard.first_base_index]
        )
        coefficient_interval = tuple(
            Fraction.from_float(value)
            for value in coefficients[coefficient_base + tap]
        )
        product_lower, product_upper = _product_bounds(
            input_interval, coefficient_interval
        )
        lower_sum += product_lower
        upper_sum += product_upper
    error = Fraction.from_float(shard.interpolation_error_upper)
    return lower_sum - error, upper_sum + error


def _strict_code(interval: tuple[Fraction, Fraction]) -> int:
    if interval[1] < 0:
        return NEGATIVE_CODE
    if interval[0] > 0:
        return POSITIVE_CODE
    return AMBIGUOUS_CODE


def exact_codes(
    shard: InputArtifact, coefficients: Sequence[tuple[float, float]]
) -> bytes:
    return bytes(
        _strict_code(exact_output_interval(shard, coefficients, offset))
        for offset in range(shard.output_count)
    )


def pack_codes(codes: bytes) -> bytes:
    packed = bytearray((len(codes) + 3) // 4)
    for index, code in enumerate(codes):
        if code not in (NEGATIVE_CODE, AMBIGUOUS_CODE, POSITIVE_CODE):
            _fail("factor-eight code cannot be packed")
        packed[index // 4] |= code << (2 * (index & 3))
    return bytes(packed)


def unpack_codes(payload: bytes, count: int) -> bytes:
    if len(payload) != (count + 3) // 4:
        _fail("factor-eight packed-code length differs")
    codes = bytes(
        (payload[index // 4] >> (2 * (index & 3))) & 3
        for index in range(count)
    )
    if any(code == RESERVED_CODE for code in codes):
        _fail("factor-eight output contains the reserved code")
    used = 2 * (count & 3)
    if used and payload[-1] >> used:
        _fail("factor-eight unused packed-code lanes are nonzero")
    return codes


def _counters(codes: bytes) -> tuple[int, int, int, int]:
    negative = codes.count(NEGATIVE_CODE)
    ambiguous = codes.count(AMBIGUOUS_CODE)
    positive = codes.count(POSITIVE_CODE)
    transitions = sum(
        (left == NEGATIVE_CODE and right == POSITIVE_CODE)
        or (left == POSITIVE_CODE and right == NEGATIVE_CODE)
        for left, right in zip(codes, codes[1:])
    )
    return negative, ambiguous, positive, transitions


def make_output_artifact(
    shard: InputArtifact,
    *,
    coefficient_artifact_raw: bytes,
    codes: bytes,
    device_error_or: int = 0,
) -> bytes:
    if len(codes) != shard.output_count:
        _fail("factor-eight output code count differs")
    payload = pack_codes(codes)
    negative, ambiguous, positive, transitions = _counters(codes)
    return OUTPUT_HEADER.pack(
        OUTPUT_MAGIC,
        FORMAT_VERSION,
        shard.q,
        shard.conrey_number,
        shard.parity,
        shard.first_fine_index,
        shard.output_count,
        negative,
        ambiguous,
        positive,
        transitions,
        device_error_or,
        0,
        hashlib.sha256(coefficient_artifact_raw).digest(),
        hashlib.sha256(shard.raw).digest(),
        hashlib.sha256(payload).digest(),
    ) + payload


def verify_output_artifact(
    coefficient_raw_or_path: bytes | Path,
    input_raw_or_path: bytes | Path,
    output_raw_or_path: bytes | Path,
) -> dict[str, Any]:
    coefficient_raw = (
        coefficient_raw_or_path
        if isinstance(coefficient_raw_or_path, bytes)
        else coefficient_raw_or_path.read_bytes()
    )
    input_raw = (
        input_raw_or_path
        if isinstance(input_raw_or_path, bytes)
        else input_raw_or_path.read_bytes()
    )
    output_raw = (
        output_raw_or_path
        if isinstance(output_raw_or_path, bytes)
        else output_raw_or_path.read_bytes()
    )
    coefficients = read_coefficient_artifact(coefficient_raw)
    shard = read_input_artifact(input_raw)
    if shard.coefficient_sha256 != hashlib.sha256(coefficient_raw).digest():
        _fail("factor-eight input binds a different coefficient artifact")
    if len(output_raw) < OUTPUT_HEADER.size:
        _fail("truncated factor-eight output header")
    (
        magic,
        version,
        q,
        conrey,
        parity,
        first_fine,
        count,
        negative,
        ambiguous,
        positive,
        transitions,
        error_or,
        reserved,
        coefficient_sha,
        input_sha,
        payload_sha,
    ) = OUTPUT_HEADER.unpack_from(output_raw)
    if magic != OUTPUT_MAGIC or version != FORMAT_VERSION:
        _fail("factor-eight output magic/version differs")
    if (
        q != shard.q
        or conrey != shard.conrey_number
        or parity != shard.parity
        or first_fine != shard.first_fine_index
        or count != shard.output_count
        or coefficient_sha != hashlib.sha256(coefficient_raw).digest()
        or input_sha != hashlib.sha256(input_raw).digest()
    ):
        _fail("factor-eight output input/coordinate binding differs")
    if error_or != 0 or reserved != 0:
        _fail("factor-eight device status or reserved word is nonzero")
    payload = output_raw[OUTPUT_HEADER.size :]
    if len(payload) != (count + 3) // 4 or hashlib.sha256(payload).digest() != payload_sha:
        _fail("factor-eight output payload length/digest differs")
    codes = unpack_codes(payload, count)
    observed_counters = _counters(codes)
    if observed_counters != (negative, ambiguous, positive, transitions):
        _fail("factor-eight output counters differ from the packed signs")

    strict_replayed = 0
    for offset, code in enumerate(codes):
        exact = exact_output_interval(shard, coefficients, offset)
        if code == NEGATIVE_CODE and not exact[1] < 0:
            _fail(f"factor-eight negative code {offset} lacks exact support")
        if code == POSITIVE_CODE and not exact[0] > 0:
            _fail(f"factor-eight positive code {offset} lacks exact support")
        if code != AMBIGUOUS_CODE:
            strict_replayed += 1

    receipt = {
        "algorithm_id": ALGORITHM_ID,
        "ambiguous_samples": ambiguous,
        "atom_id": ATOM_ID,
        "author": AUTHOR,
        "checker_id": CHECKER_ID,
        "coefficient_artifact_sha256": hashlib.sha256(coefficient_raw).hexdigest(),
        "complete_exact_rational_endpoint_replay": True,
        "external_atom_discharged": False,
        "input_artifact_sha256": hashlib.sha256(input_raw).hexdigest(),
        "interpolation_error_analytic_source_proved": False,
        "kind": "sparkinterval.tg.dirichlet_factor8.checker_receipt.v1",
        "negative_samples": negative,
        "opposite_adjacent_sign_intervals": transitions,
        "output_artifact_sha256": hashlib.sha256(output_raw).hexdigest(),
        "physical_cuda_refinement_proved": False,
        "positive_samples": positive,
        "production_ready": False,
        "strict_samples_replayed": strict_replayed,
        "target_samples_replayed": count,
        "upstream_completed_values_proved_by_this_checker": False,
        "zero_completeness_or_multiplicity_claimed": False,
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical_json_bytes(receipt)).hexdigest()
    return receipt


__all__ = [
    "ALGORITHM_ID",
    "AMBIGUOUS_CODE",
    "BASE_COMPLETED_VALUE_SAMPLES",
    "CHECKER_ID",
    "COEFFICIENT_BYTES",
    "COEFFICIENT_HEADER",
    "FACTOR8_NONALIGNED_TARGET_SAMPLES",
    "FACTOR8_SINC_PRODUCT_TERMS",
    "FACTOR8_TARGET_SAMPLES",
    "Factor8PostprocessError",
    "INPUT_HEADER",
    "INTERVAL",
    "NEGATIVE_CODE",
    "OUTPUT_HEADER",
    "POSITIVE_CODE",
    "SOURCE_INTERPOLATION_ERROR",
    "exact_codes",
    "generate_coefficient_artifact",
    "make_input_artifact",
    "make_output_artifact",
    "read_coefficient_artifact",
    "read_input_artifact",
    "source_parameters",
    "verify_coefficient_artifact",
    "verify_output_artifact",
    "work_audit",
    "write_coefficient_artifact",
]
