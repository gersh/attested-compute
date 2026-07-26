# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact witnesses for Lean's complex-disk multiplication checker.

The module is deliberately a certificate *producer* and an independent
preflight checker, not a CUDA execution claim.  All binary64 words are decoded
to :class:`fractions.Fraction`; no Python floating-point operation participates
in witness generation or validation.  The rendered Lean source asks
``RawMulCertificate.check`` to repeat the decisive rational inequalities.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import re

from reference import exact_binary64 as binary64


class ComplexDiskCertificateError(ValueError):
    """A raw disk or multiplication witness is malformed or invalid."""


@dataclass(frozen=True)
class RawComplexDisk:
    """The three binary64 words in ``ComplexDisk.Raw``."""

    re_bits: int
    im_bits: int
    radius_bits: int


@dataclass(frozen=True)
class RawMulCertificate:
    """Python representation of Lean's ``RawMulCertificate``."""

    left: RawComplexDisk
    right: RawComplexDisk
    output: RawComplexDisk
    center_error_bound_bits: int
    left_center_norm_bound_bits: int
    right_center_norm_bound_bits: int


@dataclass(frozen=True)
class DecodedComplexDisk:
    """Exact rational semantics of one finite raw disk."""

    re: Fraction
    im: Fraction
    radius: Fraction

    @property
    def center_norm_sq(self) -> Fraction:
        return self.re * self.re + self.im * self.im


@dataclass(frozen=True)
class DecodedMulCertificate:
    """Exact rational data accepted by the Python preflight checker."""

    left: DecodedComplexDisk
    right: DecodedComplexDisk
    output: DecodedComplexDisk
    center_error_bound: Fraction
    left_center_norm_bound: Fraction
    right_center_norm_bound: Fraction

    @property
    def product_center_error_sq(self) -> Fraction:
        error_re = (
            self.left.re * self.right.re
            - self.left.im * self.right.im
            - self.output.re
        )
        error_im = (
            self.left.re * self.right.im
            + self.left.im * self.right.re
            - self.output.im
        )
        return error_re * error_re + error_im * error_im

    @property
    def required_output_radius(self) -> Fraction:
        return (
            self.center_error_bound
            + self.left_center_norm_bound * self.right.radius
            + self.right_center_norm_bound * self.left.radius
            + self.left.radius * self.right.radius
        )


def _require_word(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ComplexDiskCertificateError(f"{label} must be an integer")
    if value < 0 or value >= binary64.WORD_LIMIT:
        raise ComplexDiskCertificateError(
            f"{label} must be a 64-bit unsigned integer"
        )
    return value


def _decode_finite_word(value: object, *, label: str) -> Fraction:
    word = _require_word(value, label=label)
    try:
        return binary64.decode_finite(word)
    except binary64.NonFiniteBinary64Error as exc:
        raise ComplexDiskCertificateError(f"{label} must be finite") from exc


def decode_raw_disk(raw: object, *, label: str = "disk") -> DecodedComplexDisk:
    """Decode a disk fail-closed, retaining exact rational values only."""

    if not isinstance(raw, RawComplexDisk):
        raise ComplexDiskCertificateError(f"{label} must be a RawComplexDisk")
    return DecodedComplexDisk(
        re=_decode_finite_word(raw.re_bits, label=f"{label}.re_bits"),
        im=_decode_finite_word(raw.im_bits, label=f"{label}.im_bits"),
        radius=_decode_finite_word(
            raw.radius_bits, label=f"{label}.radius_bits"
        ),
    )


def minimal_binary64_sqrt_upper_bound_bits(squared: Fraction | int) -> int:
    """Return the least finite nonnegative binary64 ``b`` with ``squared <= b^2``.

    The search is over the monotonically ordered positive binary64 encodings.
    Every comparison decodes the candidate to an exact ``Fraction``.  Thus the
    result is a directed upper bound without calling ``sqrt`` or converting to
    a host float.
    """

    if isinstance(squared, bool) or not isinstance(squared, (Fraction, int)):
        raise ComplexDiskCertificateError(
            "squared quantity must be an exact Fraction or integer"
        )
    target = Fraction(squared)
    if target < 0:
        raise ComplexDiskCertificateError("squared quantity must be nonnegative")
    if target > binary64.MAX_FINITE_VALUE * binary64.MAX_FINITE_VALUE:
        raise ComplexDiskCertificateError(
            "no finite binary64 upper bound exists for the squared quantity"
        )

    lower = binary64.POSITIVE_ZERO
    upper = binary64.MAX_FINITE
    while lower < upper:
        middle = (lower + upper) // 2
        candidate = binary64.decode_finite(middle)
        if candidate * candidate >= target:
            upper = middle
        else:
            lower = middle + 1
    return lower


def _decode_certificate(raw: object) -> DecodedMulCertificate:
    if not isinstance(raw, RawMulCertificate):
        raise ComplexDiskCertificateError(
            "certificate must be a RawMulCertificate"
        )
    return DecodedMulCertificate(
        left=decode_raw_disk(raw.left, label="left"),
        right=decode_raw_disk(raw.right, label="right"),
        output=decode_raw_disk(raw.output, label="output"),
        center_error_bound=_decode_finite_word(
            raw.center_error_bound_bits, label="center_error_bound_bits"
        ),
        left_center_norm_bound=_decode_finite_word(
            raw.left_center_norm_bound_bits,
            label="left_center_norm_bound_bits",
        ),
        right_center_norm_bound=_decode_finite_word(
            raw.right_center_norm_bound_bits,
            label="right_center_norm_bound_bits",
        ),
    )


def verify_raw_mul_certificate(raw: object) -> DecodedMulCertificate:
    """Recheck exactly the conjunction in Lean's ``MulCertificate.WellFormed``.

    Success returns the decoded rational witness.  Any malformed word or false
    inequality raises ``ComplexDiskCertificateError``.  This function is a
    preflight convenience; the generated Lean theorem does not trust it.
    """

    decoded = _decode_certificate(raw)
    nonnegative = (
        ("left.radius", decoded.left.radius),
        ("right.radius", decoded.right.radius),
        ("output.radius", decoded.output.radius),
        ("center_error_bound", decoded.center_error_bound),
        ("left_center_norm_bound", decoded.left_center_norm_bound),
        ("right_center_norm_bound", decoded.right_center_norm_bound),
    )
    for label, value in nonnegative:
        if value < 0:
            raise ComplexDiskCertificateError(f"{label} must be nonnegative")

    squared_bounds = (
        (
            "product center error",
            decoded.product_center_error_sq,
            decoded.center_error_bound,
        ),
        (
            "left center norm",
            decoded.left.center_norm_sq,
            decoded.left_center_norm_bound,
        ),
        (
            "right center norm",
            decoded.right.center_norm_sq,
            decoded.right_center_norm_bound,
        ),
    )
    for label, squared_value, bound in squared_bounds:
        if squared_value > bound * bound:
            raise ComplexDiskCertificateError(
                f"{label} squared bound is too small"
            )

    if decoded.required_output_radius > decoded.output.radius:
        raise ComplexDiskCertificateError(
            "disk multiplication error bound exceeds output.radius"
        )
    return decoded


def check_raw_mul_certificate(raw: object) -> bool:
    """Boolean fail-closed wrapper corresponding to Lean's raw checker."""

    try:
        verify_raw_mul_certificate(raw)
    except (ComplexDiskCertificateError, TypeError, ValueError, OverflowError):
        return False
    return True


def generate_raw_mul_certificate(
    left: RawComplexDisk,
    right: RawComplexDisk,
    output: RawComplexDisk,
) -> RawMulCertificate:
    """Generate least-binary64 auxiliary bounds and verify the full witness."""

    left_value = decode_raw_disk(left, label="left")
    right_value = decode_raw_disk(right, label="right")
    output_value = decode_raw_disk(output, label="output")
    error_re = (
        left_value.re * right_value.re
        - left_value.im * right_value.im
        - output_value.re
    )
    error_im = (
        left_value.re * right_value.im
        + left_value.im * right_value.re
        - output_value.im
    )
    certificate = RawMulCertificate(
        left=left,
        right=right,
        output=output,
        center_error_bound_bits=minimal_binary64_sqrt_upper_bound_bits(
            error_re * error_re + error_im * error_im
        ),
        left_center_norm_bound_bits=minimal_binary64_sqrt_upper_bound_bits(
            left_value.center_norm_sq
        ),
        right_center_norm_bound_bits=minimal_binary64_sqrt_upper_bound_bits(
            right_value.center_norm_sq
        ),
    )
    verify_raw_mul_certificate(certificate)
    return certificate


def verify_minimal_auxiliary_bounds(raw: object) -> None:
    """Check that an accepted witness uses the generator's least three words."""

    decoded = verify_raw_mul_certificate(raw)
    assert isinstance(raw, RawMulCertificate)  # Established by verification.
    expected = (
        (
            "center_error_bound_bits",
            raw.center_error_bound_bits,
            decoded.product_center_error_sq,
        ),
        (
            "left_center_norm_bound_bits",
            raw.left_center_norm_bound_bits,
            decoded.left.center_norm_sq,
        ),
        (
            "right_center_norm_bound_bits",
            raw.right_center_norm_bound_bits,
            decoded.right.center_norm_sq,
        ),
    )
    for label, actual, squared_value in expected:
        minimal = minimal_binary64_sqrt_upper_bound_bits(squared_value)
        if actual != minimal:
            raise ComplexDiskCertificateError(
                f"{label} is not minimal: got 0x{actual:016x}, "
                f"expected 0x{minimal:016x}"
            )


_LEAN_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_']*$")


def _lean_word(word: object, *, label: str) -> str:
    return f"0x{_require_word(word, label=label):016x}"


def _render_disk(raw: RawComplexDisk, *, label: str) -> str:
    # Reuse exact decoding at this final syntax boundary.  In particular, do
    # not render an infinity or NaN that Lean's decoder will reject.
    decode_raw_disk(raw, label=label)
    return (
        "\u27e8"
        + _lean_word(raw.re_bits, label=f"{label}.re_bits")
        + ", "
        + _lean_word(raw.im_bits, label=f"{label}.im_bits")
        + ", "
        + _lean_word(raw.radius_bits, label=f"{label}.radius_bits")
        + "\u27e9"
    )


def render_lean_literal(
    raw: RawMulCertificate, *, declaration: str = "certificate"
) -> str:
    """Render a deterministic, fully validated Lean certificate declaration."""

    if _LEAN_IDENTIFIER_RE.fullmatch(declaration) is None:
        raise ComplexDiskCertificateError("declaration is not a Lean identifier")
    verify_raw_mul_certificate(raw)
    return "\n".join(
        (
            f"def {declaration} : RawMulCertificate := {{",
            f"  left := {_render_disk(raw.left, label='left')}",
            f"  right := {_render_disk(raw.right, label='right')}",
            f"  output := {_render_disk(raw.output, label='output')}",
            "  centerErrorBoundBits := "
            + _lean_word(
                raw.center_error_bound_bits, label="center_error_bound_bits"
            ),
            "  leftCenterNormBoundBits := "
            + _lean_word(
                raw.left_center_norm_bound_bits,
                label="left_center_norm_bound_bits",
            ),
            "  rightCenterNormBoundBits := "
            + _lean_word(
                raw.right_center_norm_bound_bits,
                label="right_center_norm_bound_bits",
            ),
            "}",
        )
    )


def render_lean_source(
    raw: RawMulCertificate, *, declaration: str = "certificate"
) -> str:
    """Render a standalone ordinary-Lean check and typed validation theorem."""

    literal = render_lean_literal(raw, declaration=declaration)
    check_theorem = f"{declaration}_check"
    validated_theorem = f"{declaration}_validated"
    application_theorem = f"{declaration}_output_contains_mul"
    return f"""/- Generated by tg_verifier.complex_disk_mul_certificate.
   The Python producer is not trusted: Lean rechecks every rational inequality. -/

import SparkInterval.Certified.ComplexDisk

set_option autoImplicit false

namespace SparkInterval.GeneratedComplexDiskCertificate

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Certified.ComplexDisk

{literal}

theorem {check_theorem} : {declaration}.check = true := by
  norm_num [{declaration}, RawMulCertificate.check, RawMulCertificate.decode,
    Raw.decode, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold, MulCertificate.check, MulCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

theorem {validated_theorem} : {declaration}.Validated :=
  RawMulCertificate.check_sound {check_theorem}

theorem {application_theorem} :
    ∃ decoded : MulCertificate,
      {declaration}.decode = some decoded ∧
      ∀ {{x y : ℂ}},
        decoded.left.ContainsComplex x →
        decoded.right.ContainsComplex y →
        decoded.output.ContainsComplex (x * y) := by
  rcases {validated_theorem} with ⟨decoded, hdecode, _⟩
  refine ⟨decoded, hdecode, ?_⟩
  intro x y hx hy
  exact RawMulCertificate.output_contains_mul
    {check_theorem} hdecode hx hy

#print axioms {check_theorem}
#print axioms {validated_theorem}
#print axioms {application_theorem}

end SparkInterval.GeneratedComplexDiskCertificate
"""
