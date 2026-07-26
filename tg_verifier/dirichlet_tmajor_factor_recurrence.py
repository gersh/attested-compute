# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded certified recurrence for the t-major ``q^(-1/2-it)`` factors.

For Platt's source grid ``t_j = 5 j / 64`` one has

    q^(-1/2-i t_(j+1))
      = q^(-1/2-i t_j) * q^(-i 5/64).

This module evaluates only the first factor and the unit-modulus step through
directed MPFR.  It encloses those rectangles by complex disks and advances a
disk recurrence.  Every multiplication carries the same 96-byte exact
rational witness checked by :mod:`tg_verifier.complex_disk_mul_certificate`
and by ``SparkInterval.Certified.ComplexDisk`` in Lean.

``TGDFREC1`` is deliberately a bounded qualification format.  It does not
replace or change the production ``TGDLTMB1`` format.  In particular, a
successful replay is not evidence that a production t-major block used this
algorithm, that the compiled executable refines the Python, or that Platt's
analytic source theorem has been realized.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import ctypes
import hashlib
import math
import os
from pathlib import Path
import stat
import struct
import tempfile
import time
from typing import Any, BinaryIO, Iterable, NoReturn, Sequence

from reference import exact_binary64 as binary64
from tg_verifier.complex_disk_mul_certificate import (
    ComplexDiskCertificateError,
    RawComplexDisk,
    RawMulCertificate,
    decode_raw_disk,
    verify_raw_mul_certificate,
)
from tg_verifier.dirichlet_lattice_certificates import (
    _exact_arb_endpoint,
    _load_flint,
    runtime_identity,
)
from tg_verifier.dirichlet_lattice_stage import (
    SOURCE_Q_START,
    SOURCE_Q_STOP,
    SOURCE_SAMPLE_DENOMINATOR,
    SOURCE_SAMPLE_NUMERATOR,
    maximum_t_index,
)
from tg_verifier.dirichlet_residue_composition import (
    MPFRFactorProvider,
    MPFR_RNDD,
    MPFR_RNDN,
    MPFR_RNDU,
)
from tg_verifier.dirichlet_tmajor_cuda_block import (
    DIRECT_FACTOR_PRECISION_BITS,
    DIRECT_FACTOR_REPLAY_PRECISION_BITS,
    FRAME_FACTOR,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-dirichlet-tmajor-factor-disk-recurrence-kat-v1"
CHECKER_ID = "exact-rational-complex-disk-recurrence-replay-v1"

MAGIC = b"TGDFREC1"
FOOTER_MAGIC = b"TGDFRCF1"
FORMAT_VERSION = 1
MAXIMUM_FACTOR_COUNT = 64
STEP_NUMERATOR = SOURCE_SAMPLE_NUMERATOR
STEP_DENOMINATOR = SOURCE_SAMPLE_DENOMINATOR

# The factor rectangles keep the exact existing FRAME_FACTOR byte order.
# The remainder is a separate qualification wire and is not TGDLTMB1.
HEADER = struct.Struct("<8sIIQIIIIII4d4d3Q3Q32s")
RAW_DISK = struct.Struct("<3Q")
RAW_MUL_CERTIFICATE = struct.Struct("<12Q")
FOOTER = struct.Struct("<8sIIQ32s")

assert HEADER.size == 192
assert RAW_DISK.size == 24
assert RAW_MUL_CERTIFICATE.size == 96
assert FOOTER.size == 56

MAXIMUM_ARTIFACT_BYTES = (
    HEADER.size
    + MAXIMUM_FACTOR_COUNT * FRAME_FACTOR.size
    + (MAXIMUM_FACTOR_COUNT - 1) * RAW_MUL_CERTIFICATE.size
    + FOOTER.size
)


class DirichletTMajorFactorRecurrenceError(RuntimeError):
    """A bounded recurrence artifact or analytic KAT failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletTMajorFactorRecurrenceError(message)


def _float_bits(value: float) -> int:
    if not math.isfinite(value):
        _fail("non-finite binary64 value")
    # The Lean wire rejects negative zero, so canonicalize it at creation.
    if value == 0.0:
        return binary64.POSITIVE_ZERO
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def _bits_float(word: int) -> float:
    if (
        isinstance(word, bool)
        or not isinstance(word, int)
        or not 0 <= word < binary64.WORD_LIMIT
        or not binary64.is_finite(word)
    ):
        _fail("invalid finite binary64 word")
    value = struct.unpack("<d", struct.pack("<Q", word))[0]
    if value == 0.0:
        return 0.0
    return value


def _round_exact(value: Fraction, *, upward: bool) -> float:
    """Tightly round one exact rational to finite binary64."""

    try:
        result = float(value)
    except OverflowError as error:
        raise DirichletTMajorFactorRecurrenceError(
            "exact recurrence value overflowed binary64"
        ) from error
    if not math.isfinite(result):
        _fail("exact recurrence value overflowed binary64")
    if upward:
        while Fraction.from_float(result) < value:
            result = math.nextafter(result, math.inf)
        while True:
            previous = math.nextafter(result, -math.inf)
            if (
                not math.isfinite(previous)
                or Fraction.from_float(previous) < value
            ):
                return 0.0 if result == 0.0 else result
            result = previous
    while Fraction.from_float(result) > value:
        result = math.nextafter(result, -math.inf)
    while True:
        following = math.nextafter(result, math.inf)
        if (
            not math.isfinite(following)
            or Fraction.from_float(following) > value
        ):
            return 0.0 if result == 0.0 else result
        result = following


def _sqrt_upper(value: Fraction) -> float:
    """Return a checked binary64 upper bound for ``sqrt(value)``.

    ``math.sqrt`` is only a proposal.  The exact squared comparison is the
    acceptance rule, so a libm error cannot make the result unsound.
    """

    if value < 0:
        _fail("cannot bound the square root of a negative rational")
    candidate = math.sqrt(float(value))
    if not math.isfinite(candidate):
        _fail("square-root proposal is non-finite")
    if candidate == 0.0 and value != 0:
        candidate = math.nextafter(0.0, math.inf)
    while Fraction.from_float(candidate) ** 2 < value:
        candidate = math.nextafter(candidate, math.inf)
        if not math.isfinite(candidate):
            _fail("square-root bound overflowed binary64")
    while candidate > 0.0:
        previous = math.nextafter(candidate, -math.inf)
        if Fraction.from_float(previous) ** 2 < value:
            break
        candidate = previous
    return candidate


def _finite_ordered_box(
    value: Sequence[float], *, label: str
) -> tuple[float, float, float, float]:
    if (
        len(value) != 4
        or not all(math.isfinite(endpoint) for endpoint in value)
        or value[0] > value[1]
        or value[2] > value[3]
    ):
        _fail(f"{label} is not a finite ordered complex rectangle")
    return value[0], value[1], value[2], value[3]


def _factor_contains(
    outer: Sequence[float], inner: Sequence[float]
) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] >= inner[1]
        and outer[2] <= inner[2]
        and outer[3] >= inner[3]
    )


def _raw_disk_values(
    raw: RawComplexDisk, *, label: str
) -> tuple[Fraction, Fraction, Fraction]:
    try:
        value = decode_raw_disk(raw, label=label)
    except ComplexDiskCertificateError as error:
        raise DirichletTMajorFactorRecurrenceError(str(error)) from error
    if value.radius < 0:
        _fail(f"{label} has a negative radius")
    return value.re, value.im, value.radius


def _decode_word_cached(
    word: int, cache: dict[int, Fraction]
) -> Fraction:
    if word == binary64.NEGATIVE_ZERO:
        _fail("certificate uses noncanonical negative zero")
    if word not in cache:
        try:
            cache[word] = binary64.decode_finite(word)
        except (
            TypeError,
            ValueError,
            binary64.NonFiniteBinary64Error,
        ) as error:
            raise DirichletTMajorFactorRecurrenceError(
                "certificate contains an invalid binary64 word"
            ) from error
    return cache[word]


def _verify_certificate_exact(
    certificate: RawMulCertificate,
    *,
    cache: dict[int, Fraction] | None = None,
) -> None:
    """Exact replay of Lean's multiplication inequalities with word caching.

    A 64-frame recurrence repeats the phase disk 63 times and repeats each
    intermediate disk as one output and the next input.  Caching their exact
    dyadic decodings changes no acceptance condition and removes most of the
    Python ``Fraction`` construction overhead.
    """

    words = {} if cache is None else cache

    def disk(raw: RawComplexDisk) -> tuple[Fraction, Fraction, Fraction]:
        return (
            _decode_word_cached(raw.re_bits, words),
            _decode_word_cached(raw.im_bits, words),
            _decode_word_cached(raw.radius_bits, words),
        )

    left_re, left_im, left_radius = disk(certificate.left)
    right_re, right_im, right_radius = disk(certificate.right)
    output_re, output_im, output_radius = disk(certificate.output)
    center_error = _decode_word_cached(
        certificate.center_error_bound_bits, words
    )
    left_norm = _decode_word_cached(
        certificate.left_center_norm_bound_bits, words
    )
    right_norm = _decode_word_cached(
        certificate.right_center_norm_bound_bits, words
    )
    if any(
        value < 0
        for value in (
            left_radius,
            right_radius,
            output_radius,
            center_error,
            left_norm,
            right_norm,
        )
    ):
        _fail("certificate contains a negative radius or norm bound")
    error_re = (
        left_re * right_re - left_im * right_im - output_re
    )
    error_im = (
        left_re * right_im + left_im * right_re - output_im
    )
    if (
        error_re * error_re + error_im * error_im
        > center_error * center_error
        or left_re * left_re + left_im * left_im
        > left_norm * left_norm
        or right_re * right_re + right_im * right_im
        > right_norm * right_norm
        or (
            center_error
            + left_norm * right_radius
            + right_norm * left_radius
            + left_radius * right_radius
            > output_radius
        )
    ):
        _fail("stored multiplication certificate failed exact replay")


def _rectangle_to_disk(
    box: Sequence[float], *, label: str
) -> RawComplexDisk:
    re_lo, re_hi, im_lo, im_hi = _finite_ordered_box(box, label=label)
    re_lo_q, re_hi_q, im_lo_q, im_hi_q = (
        Fraction.from_float(value)
        for value in (re_lo, re_hi, im_lo, im_hi)
    )
    center_re = float((re_lo_q + re_hi_q) / 2)
    center_im = float((im_lo_q + im_hi_q) / 2)
    if not math.isfinite(center_re) or not math.isfinite(center_im):
        _fail(f"{label} midpoint is non-finite")
    center_re_q = Fraction.from_float(center_re)
    center_im_q = Fraction.from_float(center_im)
    radius_squared = max(
        (re - center_re_q) ** 2 + (im - center_im_q) ** 2
        for re in (re_lo_q, re_hi_q)
        for im in (im_lo_q, im_hi_q)
    )
    result = RawComplexDisk(
        _float_bits(center_re),
        _float_bits(center_im),
        _float_bits(_sqrt_upper(radius_squared)),
    )
    _verify_rectangle_in_disk(box, result, label=label)
    return result


def _verify_rectangle_in_disk(
    box: Sequence[float], disk: RawComplexDisk, *, label: str
) -> None:
    re_lo, re_hi, im_lo, im_hi = _finite_ordered_box(box, label=label)
    center_re, center_im, radius = _raw_disk_values(
        disk, label=f"{label} disk"
    )
    radius_squared = radius * radius
    for re in (Fraction.from_float(re_lo), Fraction.from_float(re_hi)):
        for im in (
            Fraction.from_float(im_lo),
            Fraction.from_float(im_hi),
        ):
            if (
                (re - center_re) ** 2 + (im - center_im) ** 2
                > radius_squared
            ):
                _fail(f"{label} rectangle escaped its disk")


def _disk_to_rectangle(
    disk: RawComplexDisk, *, label: str
) -> tuple[float, float, float, float]:
    re, im, radius = _raw_disk_values(disk, label=label)
    result = (
        _round_exact(re - radius, upward=False),
        _round_exact(re + radius, upward=True),
        _round_exact(im - radius, upward=False),
        _round_exact(im + radius, upward=True),
    )
    return _finite_ordered_box(result, label=f"{label} rectangle")


def _verify_disk_rectangle_exact(
    disk: RawComplexDisk,
    rectangle: Sequence[float],
    *,
    label: str,
) -> None:
    re, im, radius = _raw_disk_values(disk, label=label)
    re_lo, re_hi, im_lo, im_hi = _finite_ordered_box(
        rectangle, label=f"{label} rectangle"
    )
    if not (
        Fraction.from_float(re_lo) <= re - radius
        and re + radius <= Fraction.from_float(re_hi)
        and Fraction.from_float(im_lo) <= im - radius
        and im + radius <= Fraction.from_float(im_hi)
    ):
        _fail(f"{label} rectangle does not contain its disk")


def _disk_to_rectangle_fast(
    disk: RawComplexDisk, *, label: str, verify: bool = True
) -> tuple[float, float, float, float]:
    re = _bits_float(disk.re_bits)
    im = _bits_float(disk.im_bits)
    radius = _bits_float(disk.radius_bits)
    if radius < 0.0:
        _fail(f"{label} has a negative radius")
    result = _finite_ordered_box(
        (
            math.nextafter(re - radius, -math.inf),
            math.nextafter(re + radius, math.inf),
            math.nextafter(im - radius, -math.inf),
            math.nextafter(im + radius, math.inf),
        ),
        label=f"{label} fast rectangle",
    )
    if verify:
        try:
            _verify_disk_rectangle_exact(disk, result, label=label)
        except DirichletTMajorFactorRecurrenceError:
            return _disk_to_rectangle(disk, label=label)
    return result


def _multiply_disks(
    left: RawComplexDisk,
    right: RawComplexDisk,
    *,
    verify: bool = True,
) -> RawMulCertificate:
    """Propose one disk product, then verify every inequality exactly."""

    left_re, left_im, left_radius = _raw_disk_values(left, label="left")
    right_re, right_im, right_radius = _raw_disk_values(
        right, label="right"
    )
    exact_re = left_re * right_re - left_im * right_im
    exact_im = left_re * right_im + left_im * right_re
    output_re = float(exact_re)
    output_im = float(exact_im)
    if not math.isfinite(output_re) or not math.isfinite(output_im):
        _fail("disk center multiplication overflowed binary64")
    output_re_q = Fraction.from_float(output_re)
    output_im_q = Fraction.from_float(output_im)

    # The l1 norm is an inexpensive exact upper bound for the Euclidean
    # center error and avoids a square root in every recurrence step.
    center_error = _round_exact(
        abs(exact_re - output_re_q) + abs(exact_im - output_im_q),
        upward=True,
    )
    # Every large-q factor center has modulus below 1/sqrt(10001), with ample
    # room below 1/64.  The phase center is enclosed by the next binary64
    # above one.  Both inexpensive proposals are still checked below through
    # exact squared rational comparisons, so drift cannot be hidden.
    left_norm = 1.0 / 64.0
    if (
        Fraction.from_float(left_norm) ** 2
        < left_re * left_re + left_im * left_im
    ):
        left_norm = _sqrt_upper(left_re * left_re + left_im * left_im)
    right_norm = math.nextafter(1.0, math.inf)
    if (
        Fraction.from_float(right_norm) ** 2
        < right_re * right_re + right_im * right_im
    ):
        right_norm = _sqrt_upper(
            right_re * right_re + right_im * right_im
        )
    required_radius = (
        Fraction.from_float(center_error)
        + Fraction.from_float(left_norm) * right_radius
        + Fraction.from_float(right_norm) * left_radius
        + left_radius * right_radius
    )
    output = RawComplexDisk(
        _float_bits(output_re),
        _float_bits(output_im),
        _float_bits(_round_exact(required_radius, upward=True)),
    )
    certificate = RawMulCertificate(
        left=left,
        right=right,
        output=output,
        center_error_bound_bits=_float_bits(center_error),
        left_center_norm_bound_bits=_float_bits(left_norm),
        right_center_norm_bound_bits=_float_bits(right_norm),
    )
    if verify:
        try:
            verify_raw_mul_certificate(certificate)
        except ComplexDiskCertificateError as error:
            raise DirichletTMajorFactorRecurrenceError(
                f"exact disk multiplication replay failed: {error}"
            ) from error
    return certificate


def _upward_nonnegative_product(left: float, right: float) -> float:
    if (
        not math.isfinite(left)
        or not math.isfinite(right)
        or left < 0.0
        or right < 0.0
    ):
        _fail("disk radius operation received a negative or non-finite value")
    value = left * right
    if not math.isfinite(value):
        _fail("disk radius multiplication overflowed")
    return math.nextafter(value, math.inf)


def _upward_nonnegative_sum(left: float, right: float) -> float:
    if (
        not math.isfinite(left)
        or not math.isfinite(right)
        or left < 0.0
        or right < 0.0
    ):
        _fail("disk radius operation received a negative or non-finite value")
    value = left + right
    if not math.isfinite(value):
        _fail("disk radius addition overflowed")
    return math.nextafter(value, math.inf)


def _multiply_disks_fast(
    left: RawComplexDisk,
    right: RawComplexDisk,
    *,
    verify: bool = True,
) -> RawMulCertificate:
    """Fast binary64 proposal with exact-rational acceptance.

    The fixed center-error proposal is intentionally loose at the large-q
    scale.  It is not trusted: if the exact checker rejects any proposed
    field, the implementation falls back to the exact producer above.
    """

    left_re = _bits_float(left.re_bits)
    left_im = _bits_float(left.im_bits)
    left_radius = _bits_float(left.radius_bits)
    right_re = _bits_float(right.re_bits)
    right_im = _bits_float(right.im_bits)
    right_radius = _bits_float(right.radius_bits)
    if left_radius < 0.0 or right_radius < 0.0:
        _fail("disk recurrence has a negative radius")
    output_re = left_re * right_re - left_im * right_im
    output_im = left_re * right_im + left_im * right_re
    if not math.isfinite(output_re) or not math.isfinite(output_im):
        _fail("disk center multiplication overflowed binary64")

    # 2^-54 is far above the observed center error for a <=1/64 factor
    # multiplied by a unit phase, while still adding less than 4e-15 across
    # an entire 64-frame block.  Exact replay, not this comment, is the guard.
    center_error = math.ldexp(1.0, -54)
    left_norm = 1.0 / 64.0
    right_norm = math.nextafter(1.0, math.inf)
    radius = center_error
    radius = _upward_nonnegative_sum(
        radius,
        _upward_nonnegative_product(left_norm, right_radius),
    )
    radius = _upward_nonnegative_sum(
        radius,
        _upward_nonnegative_product(right_norm, left_radius),
    )
    radius = _upward_nonnegative_sum(
        radius,
        _upward_nonnegative_product(left_radius, right_radius),
    )
    certificate = RawMulCertificate(
        left=left,
        right=right,
        output=RawComplexDisk(
            _float_bits(output_re),
            _float_bits(output_im),
            _float_bits(radius),
        ),
        center_error_bound_bits=_float_bits(center_error),
        left_center_norm_bound_bits=_float_bits(left_norm),
        right_center_norm_bound_bits=_float_bits(right_norm),
    )
    if verify:
        try:
            _verify_certificate_exact(certificate)
        except DirichletTMajorFactorRecurrenceError:
            # A changed platform, scale, or rounding path is allowed to lose
            # the optimization but never to weaken the acceptance condition.
            return _multiply_disks(left, right, verify=True)
    return certificate


def _phase_step(
    provider: MPFRFactorProvider, *, q: int
) -> tuple[float, float, float, float]:
    """Directed MPFR rectangle for ``q^(-i*5/64)``.

    This deliberately uses the same Lipschitz range construction as
    ``MPFRFactorProvider.factor`` but omits the ``q^(-1/2)`` amplitude.
    Access to the provider's private reusable workspace is intentional and
    fail-closed: this bounded prototype is source-pinned with that provider.
    """

    maximum_ulong = (1 << (8 * ctypes.sizeof(ctypes.c_ulong))) - 1
    if (
        not SOURCE_Q_START <= q <= SOURCE_Q_STOP
        or STEP_NUMERATOR > maximum_ulong
        or STEP_DENOMINATOR > maximum_ulong
    ):
        _fail("invalid or C-ABI-overflowing phase-step request")
    workspace = getattr(provider, "_workspace", None)
    if workspace is None:
        _fail("MPFR phase-step provider is closed or incompatible")
    (
        q_value,
        log_lo,
        log_hi,
        angle_lo,
        angle_hi,
        width,
        _sqrt_lo,
        _sqrt_hi,
        _inv_lo,
        _inv_hi,
        cos_lo,
        cos_hi,
        sin_lo,
        sin_hi,
        neg_sin_lo,
        neg_sin_hi,
        *_unused,
    ) = workspace.values
    library = provider.lib
    library.mpfr_set_ui(q_value.pointer, q, MPFR_RNDN)
    library.mpfr_log(log_lo.pointer, q_value.pointer, MPFR_RNDD)
    library.mpfr_log(log_hi.pointer, q_value.pointer, MPFR_RNDU)
    library.mpfr_mul_ui(
        angle_lo.pointer, log_lo.pointer, STEP_NUMERATOR, MPFR_RNDD
    )
    library.mpfr_div_ui(
        angle_lo.pointer, angle_lo.pointer, STEP_DENOMINATOR, MPFR_RNDD
    )
    library.mpfr_mul_ui(
        angle_hi.pointer, log_hi.pointer, STEP_NUMERATOR, MPFR_RNDU
    )
    library.mpfr_div_ui(
        angle_hi.pointer, angle_hi.pointer, STEP_DENOMINATOR, MPFR_RNDU
    )
    library.mpfr_sub(
        width.pointer, angle_hi.pointer, angle_lo.pointer, MPFR_RNDU
    )
    provider._trig_range_into(
        library.mpfr_cos, angle_lo, width, cos_lo, cos_hi
    )
    provider._trig_range_into(
        library.mpfr_sin, angle_lo, width, sin_lo, sin_hi
    )
    library.mpfr_neg(neg_sin_lo.pointer, sin_hi.pointer, MPFR_RNDD)
    library.mpfr_neg(neg_sin_hi.pointer, sin_lo.pointer, MPFR_RNDU)
    return _finite_ordered_box(
        (
            library.mpfr_get_d(cos_lo.pointer, MPFR_RNDD),
            library.mpfr_get_d(cos_hi.pointer, MPFR_RNDU),
            library.mpfr_get_d(neg_sin_lo.pointer, MPFR_RNDD),
            library.mpfr_get_d(neg_sin_hi.pointer, MPFR_RNDU),
        ),
        label="MPFR phase step",
    )


def _pack_disk(value: RawComplexDisk) -> bytes:
    _raw_disk_values(value, label="packed disk")
    if any(
        word == binary64.NEGATIVE_ZERO
        for word in (value.re_bits, value.im_bits, value.radius_bits)
    ):
        _fail("disk uses noncanonical negative zero")
    return RAW_DISK.pack(value.re_bits, value.im_bits, value.radius_bits)


def _unpack_disk(raw: bytes) -> RawComplexDisk:
    result = RawComplexDisk(*RAW_DISK.unpack(raw))
    _raw_disk_values(result, label="unpacked disk")
    if any(
        word == binary64.NEGATIVE_ZERO
        for word in (result.re_bits, result.im_bits, result.radius_bits)
    ):
        _fail("disk wire uses noncanonical negative zero")
    return result


def _pack_certificate(
    value: RawMulCertificate, *, verify: bool = True
) -> bytes:
    if verify:
        try:
            _verify_certificate_exact(value)
        except DirichletTMajorFactorRecurrenceError:
            raise
    return RAW_MUL_CERTIFICATE.pack(
        value.left.re_bits,
        value.left.im_bits,
        value.left.radius_bits,
        value.right.re_bits,
        value.right.im_bits,
        value.right.radius_bits,
        value.output.re_bits,
        value.output.im_bits,
        value.output.radius_bits,
        value.center_error_bound_bits,
        value.left_center_norm_bound_bits,
        value.right_center_norm_bound_bits,
    )


def _unpack_certificate(
    raw: bytes, *, cache: dict[int, Fraction] | None = None
) -> RawMulCertificate:
    words = RAW_MUL_CERTIFICATE.unpack(raw)
    result = RawMulCertificate(
        left=RawComplexDisk(*words[0:3]),
        right=RawComplexDisk(*words[3:6]),
        output=RawComplexDisk(*words[6:9]),
        center_error_bound_bits=words[9],
        left_center_norm_bound_bits=words[10],
        right_center_norm_bound_bits=words[11],
    )
    _verify_certificate_exact(result, cache=cache)
    return result


@dataclass(frozen=True)
class ParsedRecurrence:
    q: int
    first_t_index: int
    factor_count: int
    seed_box: tuple[float, float, float, float]
    step_box: tuple[float, float, float, float]
    seed_disk: RawComplexDisk
    step_disk: RawComplexDisk
    factors: tuple[tuple[float, float, float, float], ...]
    certificates: tuple[RawMulCertificate, ...]
    artifact_sha256: str
    payload_sha256: str


def _validate_request(*, q: int, first_t_index: int, count: int) -> None:
    if (
        isinstance(q, bool)
        or isinstance(first_t_index, bool)
        or isinstance(count, bool)
        or not isinstance(q, int)
        or not isinstance(first_t_index, int)
        or not isinstance(count, int)
        or not SOURCE_Q_START <= q <= SOURCE_Q_STOP
        or not 0 <= first_t_index <= maximum_t_index(q)
        or not 1 <= count <= MAXIMUM_FACTOR_COUNT
        or first_t_index + count - 1 > maximum_t_index(q)
    ):
        _fail("factor recurrence request is outside the bounded source grid")


def build_artifact_bytes(
    *,
    q: int,
    first_t_index: int,
    count: int,
) -> bytes:
    """Construct a complete bounded recurrence artifact in memory."""

    _validate_request(
        q=q, first_t_index=first_t_index, count=count
    )
    with MPFRFactorProvider(DIRECT_FACTOR_PRECISION_BITS) as generator:
        with MPFRFactorProvider(
            DIRECT_FACTOR_REPLAY_PRECISION_BITS
        ) as replayer:
            if generator.version != replayer.version:
                _fail("MPFR generation and replay versions differ")
            seed_box = generator.factor(
                q=q,
                t_numerator=first_t_index * STEP_NUMERATOR,
                t_denominator=STEP_DENOMINATOR,
            )
            replayed_seed = replayer.factor(
                q=q,
                t_numerator=first_t_index * STEP_NUMERATOR,
                t_denominator=STEP_DENOMINATOR,
            )
            step_box = _phase_step(generator, q=q)
            replayed_step = _phase_step(replayer, q=q)
            mpfr_version = generator.version
    if not _factor_contains(seed_box, replayed_seed):
        _fail("higher-precision MPFR seed escaped generated enclosure")
    if not _factor_contains(step_box, replayed_step):
        _fail("higher-precision MPFR step escaped generated enclosure")

    seed_disk = _rectangle_to_disk(seed_box, label="seed")
    step_disk = _rectangle_to_disk(step_box, label="step")
    disks = [seed_disk]
    certificates: list[RawMulCertificate] = []
    while len(disks) < count:
        # The completed serialized artifact is independently parsed and every
        # certificate is checked before these bytes are returned.  Avoid two
        # redundant pre-serialization validations of the same exact fields.
        certificate = _multiply_disks_fast(
            disks[-1], step_disk, verify=False
        )
        certificates.append(certificate)
        disks.append(certificate.output)
    factors = tuple(
        _disk_to_rectangle_fast(
            disk, label=f"factor {index}", verify=False
        )
        for index, disk in enumerate(disks)
    )
    payload = b"".join(FRAME_FACTOR.pack(*factor) for factor in factors)
    payload += b"".join(
        _pack_certificate(value, verify=False)
        for value in certificates
    )
    payload_sha256 = hashlib.sha256(payload).digest()
    header = HEADER.pack(
        MAGIC,
        FORMAT_VERSION,
        q,
        first_t_index,
        count,
        STEP_NUMERATOR,
        STEP_DENOMINATOR,
        DIRECT_FACTOR_PRECISION_BITS,
        DIRECT_FACTOR_REPLAY_PRECISION_BITS,
        0,
        *seed_box,
        *step_box,
        seed_disk.re_bits,
        seed_disk.im_bits,
        seed_disk.radius_bits,
        step_disk.re_bits,
        step_disk.im_bits,
        step_disk.radius_bits,
        payload_sha256,
    )
    prefix = header + payload
    footer = FOOTER.pack(
        FOOTER_MAGIC,
        FORMAT_VERSION,
        0,
        len(payload),
        hashlib.sha256(prefix).digest(),
    )
    raw = prefix + footer
    # Do not publish bytes which the independent parser/replayer rejects.
    _verify_artifact_bytes_impl(
        raw,
        _builder_seed_replay=(
            seed_box,
            replayed_seed,
            step_box,
            replayed_step,
            mpfr_version,
        ),
    )
    return raw


def _parse_artifact(raw: bytes) -> ParsedRecurrence:
    if (
        not isinstance(raw, bytes)
        or not HEADER.size + FRAME_FACTOR.size + FOOTER.size
        <= len(raw)
        <= MAXIMUM_ARTIFACT_BYTES
    ):
        _fail("recurrence artifact size is outside the bounded format")
    header = HEADER.unpack_from(raw, 0)
    (
        magic,
        version,
        q,
        first_t_index,
        count,
        step_numerator,
        step_denominator,
        generator_bits,
        replayer_bits,
        reserved,
        *tail,
    ) = header
    seed_box = _finite_ordered_box(tail[0:4], label="stored seed")
    step_box = _finite_ordered_box(tail[4:8], label="stored step")
    seed_disk = RawComplexDisk(*tail[8:11])
    step_disk = RawComplexDisk(*tail[11:14])
    payload_sha256 = tail[14]
    _validate_request(q=q, first_t_index=first_t_index, count=count)
    if (
        magic != MAGIC
        or version != FORMAT_VERSION
        or step_numerator != STEP_NUMERATOR
        or step_denominator != STEP_DENOMINATOR
        or generator_bits != DIRECT_FACTOR_PRECISION_BITS
        or replayer_bits != DIRECT_FACTOR_REPLAY_PRECISION_BITS
        or reserved != 0
    ):
        _fail("recurrence header identity or reserved field differs")
    _pack_disk(seed_disk)
    _pack_disk(step_disk)

    payload_size = (
        count * FRAME_FACTOR.size
        + (count - 1) * RAW_MUL_CERTIFICATE.size
    )
    if len(raw) != HEADER.size + payload_size + FOOTER.size:
        _fail("recurrence artifact has wrong exact length")
    payload_start = HEADER.size
    payload_stop = payload_start + payload_size
    payload = raw[payload_start:payload_stop]
    if hashlib.sha256(payload).digest() != payload_sha256:
        _fail("recurrence payload digest differs")
    (
        footer_magic,
        footer_version,
        footer_reserved,
        footer_payload_size,
        prefix_sha256,
    ) = FOOTER.unpack_from(raw, payload_stop)
    if (
        footer_magic != FOOTER_MAGIC
        or footer_version != FORMAT_VERSION
        or footer_reserved != 0
        or footer_payload_size != payload_size
        or hashlib.sha256(raw[:payload_stop]).digest() != prefix_sha256
    ):
        _fail("recurrence footer or prefix digest differs")

    factor_bytes = count * FRAME_FACTOR.size
    factors = tuple(
        _finite_ordered_box(value, label=f"stored factor {index}")
        for index, value in enumerate(
            FRAME_FACTOR.iter_unpack(payload[:factor_bytes])
        )
    )
    certificate_raw = payload[factor_bytes:]
    decoded_words: dict[int, Fraction] = {}
    certificates = tuple(
        _unpack_certificate(
            certificate_raw[
                index
                * RAW_MUL_CERTIFICATE.size : (index + 1)
                * RAW_MUL_CERTIFICATE.size
            ],
            cache=decoded_words,
        )
        for index in range(count - 1)
    )
    return ParsedRecurrence(
        q=q,
        first_t_index=first_t_index,
        factor_count=count,
        seed_box=seed_box,
        step_box=step_box,
        seed_disk=seed_disk,
        step_disk=step_disk,
        factors=factors,
        certificates=certificates,
        artifact_sha256=hashlib.sha256(raw).hexdigest(),
        payload_sha256=payload_sha256.hex(),
    )


def _verify_artifact_bytes_impl(
    raw: bytes,
    *,
    full_direct_mpfr: bool = False,
    _builder_seed_replay: tuple[
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        str,
    ]
    | None = None,
) -> dict[str, Any]:
    """Parse and exactly replay every finite recurrence multiplication.

    ``full_direct_mpfr`` is a bounded differential KAT.  The recurrence proof
    itself uses only the two high-precision MPFR seed checks and exact disk
    multiplication, so production qualification does not need one
    transcendental call per output factor.
    """

    parsed = _parse_artifact(raw)
    direct_replayed: list[
        tuple[float, float, float, float]
    ] = []
    if _builder_seed_replay is None:
        with MPFRFactorProvider(DIRECT_FACTOR_PRECISION_BITS) as generator:
            with MPFRFactorProvider(
                DIRECT_FACTOR_REPLAY_PRECISION_BITS
            ) as replayer:
                if generator.version != replayer.version:
                    _fail("MPFR generation and replay versions differ")
                expected_seed = generator.factor(
                    q=parsed.q,
                    t_numerator=(
                        parsed.first_t_index * STEP_NUMERATOR
                    ),
                    t_denominator=STEP_DENOMINATOR,
                )
                replayed_seed = replayer.factor(
                    q=parsed.q,
                    t_numerator=(
                        parsed.first_t_index * STEP_NUMERATOR
                    ),
                    t_denominator=STEP_DENOMINATOR,
                )
                expected_step = _phase_step(generator, q=parsed.q)
                replayed_step = _phase_step(replayer, q=parsed.q)
                if full_direct_mpfr:
                    direct_replayed = [
                        replayer.factor(
                            q=parsed.q,
                            t_numerator=(
                                parsed.first_t_index + index
                            )
                            * STEP_NUMERATOR,
                            t_denominator=STEP_DENOMINATOR,
                        )
                        for index in range(parsed.factor_count)
                    ]
                mpfr_version = generator.version
    else:
        if full_direct_mpfr:
            _fail(
                "builder-local seed reuse cannot request full direct MPFR"
            )
        (
            expected_seed,
            replayed_seed,
            expected_step,
            replayed_step,
            mpfr_version,
        ) = _builder_seed_replay
    if struct.pack("<4d", *expected_seed) != struct.pack(
        "<4d", *parsed.seed_box
    ):
        _fail("stored seed is not the exact directed MPFR output")
    if struct.pack("<4d", *expected_step) != struct.pack(
        "<4d", *parsed.step_box
    ):
        _fail("stored step is not the exact directed MPFR output")
    if not _factor_contains(parsed.seed_box, replayed_seed):
        _fail("higher-precision MPFR seed escaped stored enclosure")
    if not _factor_contains(parsed.step_box, replayed_step):
        _fail("higher-precision MPFR step escaped stored enclosure")
    expected_seed_disk = _rectangle_to_disk(
        parsed.seed_box, label="replayed seed"
    )
    expected_step_disk = _rectangle_to_disk(
        parsed.step_box, label="replayed step"
    )
    if (
        parsed.seed_disk != expected_seed_disk
        or parsed.step_disk != expected_step_disk
    ):
        _fail("stored seed or step disk differs from exact replay")

    current = parsed.seed_disk
    disks = [current]
    for index, certificate in enumerate(parsed.certificates, start=1):
        if certificate.left != current:
            _fail(f"recurrence step {index} breaks the left-disk chain")
        if certificate.right != parsed.step_disk:
            _fail(f"recurrence step {index} substitutes the phase step")
        # The parsed certificate immediately above already passed every exact
        # inequality.  This second construction is only the deterministic
        # algorithm replay used for byte equality.
        expected = _multiply_disks_fast(
            current, parsed.step_disk, verify=False
        )
        if certificate != expected:
            _fail(
                f"recurrence step {index} differs from exact-rational replay"
            )
        current = certificate.output
        disks.append(current)
    if len(disks) != parsed.factor_count:
        _fail("recurrence disk count differs")
    for index, (disk, factor) in enumerate(zip(disks, parsed.factors)):
        expected = _disk_to_rectangle_fast(
            disk,
            label=f"replayed factor {index}",
            verify=False,
        )
        if FRAME_FACTOR.pack(*factor) != FRAME_FACTOR.pack(*expected):
            _fail(f"factor rectangle {index} differs from its disk")
        _verify_disk_rectangle_exact(
            disk, factor, label=f"factor {index}"
        )
        if full_direct_mpfr and not _factor_contains(
            factor, direct_replayed[index]
        ):
            _fail(
                f"direct higher-precision MPFR factor {index} "
                "escaped recurrence rectangle"
            )

    widths = tuple(
        max(factor[1] - factor[0], factor[3] - factor[2])
        for factor in parsed.factors
    )
    return {
        "schema": "sparkinterval.tg.dirichlet_factor_recurrence.replay.v1",
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "checker_id": CHECKER_ID,
        "artifact_sha256": parsed.artifact_sha256,
        "artifact_size_bytes": len(raw),
        "payload_sha256": parsed.payload_sha256,
        "q": parsed.q,
        "first_t_index": parsed.first_t_index,
        "factor_count": parsed.factor_count,
        "mpfr_version": mpfr_version,
        "mpfr_generator_precision_bits": DIRECT_FACTOR_PRECISION_BITS,
        "mpfr_replayer_precision_bits": (
            DIRECT_FACTOR_REPLAY_PRECISION_BITS
        ),
        "transcendental_boxes_per_precision": 2,
        "exact_rational_multiplication_steps_replayed": len(
            parsed.certificates
        ),
        "first_factor_max_width": widths[0],
        "last_factor_max_width": widths[-1],
        "maximum_factor_width": max(widths),
        "higher_precision_seed_and_step_contained": True,
        "full_direct_mpfr_differential_checked": full_direct_mpfr,
        "independent_arb_checked": False,
        "production_TGDLTMB1_format_unchanged": True,
        "compiled_executable_refinement_proved": False,
        "lean_typed_recurrence_theorem_implemented": True,
        "lean_TGDFREC1_chain_parser_implemented": False,
        "analytic_seed_realization_in_lean": False,
        "source_scale_run": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }


def verify_artifact_bytes(
    raw: bytes, *, full_direct_mpfr: bool = False
) -> dict[str, Any]:
    """Public replay always recomputes the MPFR seed and phase-step boxes."""

    return _verify_artifact_bytes_impl(
        raw,
        full_direct_mpfr=full_direct_mpfr,
        _builder_seed_replay=None,
    )


def _contains_arb(
    box: Sequence[float], value: Any, *, label: str
) -> None:
    outer = _finite_ordered_box(box, label=label)
    if not value.is_finite():
        _fail(f"{label} Arb value is not finite")
    if not (
        Fraction.from_float(outer[0])
        <= _exact_arb_endpoint(value.real, lower=True)
        and _exact_arb_endpoint(value.real, lower=False)
        <= Fraction.from_float(outer[1])
        and Fraction.from_float(outer[2])
        <= _exact_arb_endpoint(value.imag, lower=True)
        and _exact_arb_endpoint(value.imag, lower=False)
        <= Fraction.from_float(outer[3])
    ):
        _fail(f"{label} Arb enclosure escaped recurrence rectangle")


def verify_artifact_with_arb(
    raw: bytes,
    *,
    precision_bits: int = 384,
    frame_indices: Iterable[int] | None = None,
) -> dict[str, Any]:
    """Independently check selected (or all) factors with pinned Arb/FLINT."""

    if (
        isinstance(precision_bits, bool)
        or not isinstance(precision_bits, int)
        or precision_bits < DIRECT_FACTOR_REPLAY_PRECISION_BITS
    ):
        _fail("Arb precision is below the MPFR replay precision")
    parsed = _parse_artifact(raw)
    if frame_indices is None:
        frames = tuple(range(parsed.factor_count))
        mode = "full_bounded"
    else:
        frames = tuple(frame_indices)
        if (
            not frames
            or tuple(sorted(set(frames))) != frames
            or frames[0] < 0
            or frames[-1] >= parsed.factor_count
        ):
            _fail("Arb spot-check indices are not sorted unique in range")
        mode = "selected_frames"

    # Replay the exact recurrence first.  Arb is an independent analytic
    # cross-check, not a substitute for byte and rational-chain validation.
    report = verify_artifact_bytes(raw)
    flint = _load_flint()
    old_precision = flint.ctx.prec
    old_threads = flint.ctx.threads
    flint.ctx.prec = precision_bits
    flint.ctx.threads = 1
    try:
        q_value = flint.acb(parsed.q)
        seed_t = (
            flint.arb(parsed.first_t_index * STEP_NUMERATOR)
            / STEP_DENOMINATOR
        )
        seed = q_value ** (-flint.acb(flint.arb(1) / 2, seed_t))
        step_t = flint.arb(STEP_NUMERATOR) / STEP_DENOMINATOR
        step = q_value ** (-flint.acb(0, step_t))
        _contains_arb(parsed.seed_box, seed, label="Arb seed")
        _contains_arb(parsed.step_box, step, label="Arb phase step")
        for frame in frames:
            t = (
                flint.arb(
                    (parsed.first_t_index + frame) * STEP_NUMERATOR
                )
                / STEP_DENOMINATOR
            )
            value = q_value ** (-flint.acb(flint.arb(1) / 2, t))
            _contains_arb(
                parsed.factors[frame],
                value,
                label=f"Arb factor {frame}",
            )
    finally:
        flint.ctx.prec = old_precision
        flint.ctx.threads = old_threads
    report["independent_arb_checked"] = True
    report["independent_arb_mode"] = mode
    report["independent_arb_factor_count"] = len(frames)
    report["independent_arb_precision_bits"] = precision_bits
    report["independent_arb_runtime"] = runtime_identity(flint)
    return report


def _open_regular(path: Path, *, label: str) -> BinaryIO:
    try:
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        )
    except OSError as error:
        raise DirichletTMajorFactorRecurrenceError(
            f"cannot open {label}: {error}"
        ) from error
    source = os.fdopen(descriptor, "rb")
    if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
        source.close()
        _fail(f"{label} is not a regular file")
    return source


def write_artifact(
    path: Path, *, q: int, first_t_index: int, count: int
) -> dict[str, Any]:
    """Atomically publish an immutable, already-replayed bounded artifact."""

    if path.exists() or path.is_symlink():
        _fail(f"refusing to replace immutable output: {path}")
    raw = build_artifact_bytes(
        q=q, first_t_index=first_t_index, count=count
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)
        temporary.unlink()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return verify_artifact(path)


def verify_artifact(
    path: Path,
    *,
    expected_sha256: str | None = None,
    full_direct_mpfr: bool = False,
) -> dict[str, Any]:
    """Read one regular file once, bind its bytes, and replay it."""

    raw = _read_artifact_file(path, expected_sha256=expected_sha256)
    return verify_artifact_bytes(
        raw, full_direct_mpfr=full_direct_mpfr
    )


def _read_artifact_file(
    path: Path, *, expected_sha256: str | None
) -> bytes:
    with _open_regular(path, label="TGDFREC1 artifact") as source:
        initial = os.fstat(source.fileno())
        if not 1 <= initial.st_size <= MAXIMUM_ARTIFACT_BYTES:
            _fail("TGDFREC1 file size is outside the bounded format")
        raw = source.read(MAXIMUM_ARTIFACT_BYTES + 1)
        if len(raw) != initial.st_size:
            _fail("TGDFREC1 file length changed during read")
        final = os.fstat(source.fileno())
        identity = (
            initial.st_dev,
            initial.st_ino,
            initial.st_mode,
            initial.st_size,
            initial.st_mtime_ns,
            initial.st_ctime_ns,
        )
        if identity != (
            final.st_dev,
            final.st_ino,
            final.st_mode,
            final.st_size,
            final.st_mtime_ns,
            final.st_ctime_ns,
        ):
            _fail("TGDFREC1 file changed while it was read")
    observed = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and observed != expected_sha256:
        _fail("TGDFREC1 artifact differs from its external SHA-256 pin")
    return raw


def verify_artifact_file_with_arb(
    path: Path,
    *,
    expected_sha256: str | None = None,
    precision_bits: int = 384,
    frame_indices: Iterable[int] | None = None,
) -> dict[str, Any]:
    """Read once with no-follow/identity guards, then run the Arb KAT."""

    return verify_artifact_with_arb(
        _read_artifact_file(
            path, expected_sha256=expected_sha256
        ),
        precision_bits=precision_bits,
        frame_indices=frame_indices,
    )


def benchmark(
    *,
    q: int,
    first_t_index: int,
    count: int = MAXIMUM_FACTOR_COUNT,
    repetitions: int = 8,
) -> dict[str, Any]:
    """Bounded wall-clock comparison with the current two-pass direct path."""

    _validate_request(
        q=q, first_t_index=first_t_index, count=count
    )
    if (
        isinstance(repetitions, bool)
        or not isinstance(repetitions, int)
        or not 1 <= repetitions <= 1_000
    ):
        _fail("benchmark repetitions are outside [1,1000]")

    direct_seconds: list[float] = []
    recurrence_seconds: list[float] = []
    recurrence_verify_seconds: list[float] = []
    recurrence_raw = b""
    for _ in range(repetitions):
        started = time.perf_counter()
        with MPFRFactorProvider(DIRECT_FACTOR_PRECISION_BITS) as generator:
            with MPFRFactorProvider(
                DIRECT_FACTOR_REPLAY_PRECISION_BITS
            ) as replayer:
                for frame in range(count):
                    arguments = {
                        "q": q,
                        "t_numerator": (
                            first_t_index + frame
                        )
                        * STEP_NUMERATOR,
                        "t_denominator": STEP_DENOMINATOR,
                    }
                    generated = generator.factor(**arguments)
                    replayed = replayer.factor(**arguments)
                    if not _factor_contains(generated, replayed):
                        _fail("direct benchmark containment failed")
        direct_seconds.append(time.perf_counter() - started)

        started = time.perf_counter()
        recurrence_raw = build_artifact_bytes(
            q=q, first_t_index=first_t_index, count=count
        )
        recurrence_seconds.append(time.perf_counter() - started)
        started = time.perf_counter()
        recurrence_report = verify_artifact_bytes(recurrence_raw)
        recurrence_verify_seconds.append(time.perf_counter() - started)

    direct_sorted = sorted(direct_seconds)
    recurrence_sorted = sorted(recurrence_seconds)
    verify_sorted = sorted(recurrence_verify_seconds)
    middle = repetitions // 2
    direct_median = direct_sorted[middle]
    recurrence_median = recurrence_sorted[middle]
    verify_median = verify_sorted[middle]
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_factor_recurrence.benchmark.v1"
        ),
        "algorithm_id": ALGORITHM_ID,
        "q": q,
        "first_t_index": first_t_index,
        "factor_count": count,
        "repetitions": repetitions,
        "direct_two_precision_mpfr_median_seconds": direct_median,
        "recurrence_build_and_self_replay_median_seconds": (
            recurrence_median
        ),
        "recurrence_independent_replay_median_seconds": verify_median,
        "direct_over_recurrence_build_speedup": (
            direct_median / recurrence_median
        ),
        "direct_over_recurrence_replay_speedup": (
            direct_median / verify_median
        ),
        "artifact_size_bytes": len(recurrence_raw),
        "transcendental_box_reduction_factor": count / 2,
        "maximum_factor_width": recurrence_report[
            "maximum_factor_width"
        ],
        "last_factor_max_width": recurrence_report[
            "last_factor_max_width"
        ],
        "independent_arb_in_timing": False,
        "source_scale_projection_authoritative": False,
        "production_format_changed": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "CHECKER_ID",
    "DirichletTMajorFactorRecurrenceError",
    "MAXIMUM_FACTOR_COUNT",
    "ParsedRecurrence",
    "benchmark",
    "build_artifact_bytes",
    "verify_artifact",
    "verify_artifact_bytes",
    "verify_artifact_file_with_arb",
    "verify_artifact_with_arb",
    "write_artifact",
]
