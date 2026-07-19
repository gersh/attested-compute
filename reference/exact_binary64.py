"""Exact IEEE-754 binary64 reference arithmetic.

The module deliberately does not use Python's native binary floating-point
type.  Finite values are decoded to :class:`fractions.Fraction`, arithmetic is
performed there, and the result is rounded by searching the monotonically
ordered positive binary64 encodings.

Raw binary64 values are represented as unsigned 64-bit integers.  Primitive
operations require finite operands and reject division by either signed zero.
Interval inputs may have infinite (but never NaN) endpoints; the four
arithmetic operations are exact for finite endpoints and conservatively return
the whole extended interval if a prior operation produced an infinite bound.

Signed-zero policy
------------------

``round_down(0)`` returns ``-0``, ``round_up(0)`` and
``round_nearest_even(0)`` return ``+0``.  That convention gives canonical
outward bounds when only an exact rational is available.  Primitive operations
add the IEEE operation-specific rules: multiplication and division use the XOR
of operand signs; addition/subtraction preserve equal zero signs, while exact
cancellation is ``-0`` only under round-toward-negative.  Endpoint-selection
ties prefer ``-0`` for a lower/minimum endpoint and ``+0`` for an
upper/maximum endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Callable


WORD_BITS = 64
WORD_LIMIT = 1 << WORD_BITS
SIGN_MASK = 1 << 63
FRACTION_BITS = 52
FRACTION_MASK = (1 << FRACTION_BITS) - 1
EXPONENT_MASK = 0x7FF
EXPONENT_SHIFT = FRACTION_BITS

POSITIVE_ZERO = 0x0000000000000000
NEGATIVE_ZERO = 0x8000000000000000
MIN_POSITIVE_SUBNORMAL = 0x0000000000000001
MAX_POSITIVE_SUBNORMAL = 0x000FFFFFFFFFFFFF
MIN_POSITIVE_NORMAL = 0x0010000000000000
MAX_FINITE = 0x7FEFFFFFFFFFFFFF
MIN_FINITE = 0xFFEFFFFFFFFFFFFF
POSITIVE_INFINITY = 0x7FF0000000000000
NEGATIVE_INFINITY = 0xFFF0000000000000


class Binary64Class(str, Enum):
    """The mutually exclusive binary64 encoding classes."""

    POSITIVE_ZERO = "positive_zero"
    NEGATIVE_ZERO = "negative_zero"
    POSITIVE_SUBNORMAL = "positive_subnormal"
    NEGATIVE_SUBNORMAL = "negative_subnormal"
    POSITIVE_NORMAL = "positive_normal"
    NEGATIVE_NORMAL = "negative_normal"
    POSITIVE_INFINITY = "positive_infinity"
    NEGATIVE_INFINITY = "negative_infinity"
    NAN = "nan"


class NonFiniteBinary64Error(ValueError):
    """Raised when a strict finite operation receives infinity or NaN."""


class InvalidBinary64Operation(ValueError):
    """Raised for an undefined operation, currently finite division by zero."""


def _validate_bits(bits: int) -> int:
    if isinstance(bits, bool) or not isinstance(bits, int):
        raise TypeError("binary64 bits must be an integer")
    if bits < 0 or bits >= WORD_LIMIT:
        raise ValueError("binary64 bits must be in [0, 2^64)")
    return bits


def sign_bit(bits: int) -> int:
    """Return 1 exactly when the raw binary64 sign bit is set."""

    return 1 if _validate_bits(bits) & SIGN_MASK else 0


def classify(bits: int) -> Binary64Class:
    """Classify one raw binary64 word without converting it to a float."""

    bits = _validate_bits(bits)
    negative = bool(bits & SIGN_MASK)
    exponent = (bits >> EXPONENT_SHIFT) & EXPONENT_MASK
    fraction = bits & FRACTION_MASK
    if exponent == 0:
        if fraction == 0:
            return (
                Binary64Class.NEGATIVE_ZERO
                if negative
                else Binary64Class.POSITIVE_ZERO
            )
        return (
            Binary64Class.NEGATIVE_SUBNORMAL
            if negative
            else Binary64Class.POSITIVE_SUBNORMAL
        )
    if exponent == EXPONENT_MASK:
        if fraction != 0:
            return Binary64Class.NAN
        return (
            Binary64Class.NEGATIVE_INFINITY
            if negative
            else Binary64Class.POSITIVE_INFINITY
        )
    return (
        Binary64Class.NEGATIVE_NORMAL
        if negative
        else Binary64Class.POSITIVE_NORMAL
    )


def is_finite(bits: int) -> bool:
    """Return whether ``bits`` is a finite binary64 encoding."""

    return (
        (_validate_bits(bits) >> EXPONENT_SHIFT) & EXPONENT_MASK
    ) != EXPONENT_MASK


def is_nan(bits: int) -> bool:
    """Return whether ``bits`` is a NaN encoding."""

    return classify(bits) is Binary64Class.NAN


def is_infinite(bits: int) -> bool:
    """Return whether ``bits`` is either infinity."""

    kind = classify(bits)
    return kind in (
        Binary64Class.POSITIVE_INFINITY,
        Binary64Class.NEGATIVE_INFINITY,
    )


def is_zero(bits: int) -> bool:
    """Return whether ``bits`` is either signed-zero encoding."""

    return (_validate_bits(bits) & ~SIGN_MASK) == 0


def _positive_finite_value(bits: int) -> Fraction:
    """Decode an already-validated positive finite encoding."""

    exponent = (bits >> EXPONENT_SHIFT) & EXPONENT_MASK
    fraction = bits & FRACTION_MASK
    if exponent == 0:
        return Fraction(fraction, 1 << 1074)

    significand = (1 << FRACTION_BITS) + fraction
    power = exponent - 1023 - FRACTION_BITS
    if power >= 0:
        return Fraction(significand << power)
    return Fraction(significand, 1 << (-power))


def decode_finite(bits: int) -> Fraction:
    """Decode a finite binary64 word to its exact rational value.

    Both signed-zero words decode to the mathematical value zero; callers that
    need the zero sign retain the original word.  Infinity and every NaN
    payload are rejected rather than silently mapped to a sentinel.
    """

    bits = _validate_bits(bits)
    if not is_finite(bits):
        raise NonFiniteBinary64Error(
            f"expected finite binary64 encoding, got {classify(bits).value}"
        )
    magnitude = _positive_finite_value(bits & ~SIGN_MASK)
    return -magnitude if bits & SIGN_MASK else magnitude


MIN_SUBNORMAL_VALUE = Fraction(1, 1 << 1074)
MAX_FINITE_VALUE = _positive_finite_value(MAX_FINITE)
RNE_OVERFLOW_THRESHOLD = MAX_FINITE_VALUE + Fraction(1 << 970)


def _as_fraction(value: Fraction | int) -> Fraction:
    if isinstance(value, bool):
        raise TypeError("rounding input must be an exact Fraction or integer")
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value)
    raise TypeError("rounding input must be an exact Fraction or integer")


def _positive_floor(value: Fraction) -> int:
    """Greatest nonnegative finite encoding no greater than ``value``."""

    if value < 0:
        raise ValueError("_positive_floor requires a nonnegative value")
    if value >= MAX_FINITE_VALUE:
        return MAX_FINITE

    low = POSITIVE_ZERO
    high = MAX_FINITE
    answer = POSITIVE_ZERO
    while low <= high:
        middle = (low + high) // 2
        if _positive_finite_value(middle) <= value:
            answer = middle
            low = middle + 1
        else:
            high = middle - 1
    return answer


def _positive_ceil(value: Fraction) -> int:
    """Least nonnegative binary64 encoding no less than ``value``."""

    if value < 0:
        raise ValueError("_positive_ceil requires a nonnegative value")
    if value > MAX_FINITE_VALUE:
        return POSITIVE_INFINITY

    low = POSITIVE_ZERO
    high = MAX_FINITE
    answer = MAX_FINITE
    while low <= high:
        middle = (low + high) // 2
        if _positive_finite_value(middle) >= value:
            answer = middle
            high = middle - 1
        else:
            low = middle + 1
    return answer


def _negate_non_nan_bits(bits: int) -> int:
    bits = _validate_bits(bits)
    if is_nan(bits):
        raise ValueError("cannot negate a NaN endpoint")
    return bits ^ SIGN_MASK


def round_down(value: Fraction | int) -> int:
    """Correctly round an exact rational toward negative infinity."""

    value = _as_fraction(value)
    if value == 0:
        return NEGATIVE_ZERO
    if value > 0:
        return _positive_floor(value)
    upper_magnitude = _positive_ceil(-value)
    return _negate_non_nan_bits(upper_magnitude)


def round_up(value: Fraction | int) -> int:
    """Correctly round an exact rational toward positive infinity."""

    value = _as_fraction(value)
    if value == 0:
        return POSITIVE_ZERO
    if value > 0:
        return _positive_ceil(value)
    lower_magnitude = _positive_floor(-value)
    return _negate_non_nan_bits(lower_magnitude)


def _round_positive_nearest_even(value: Fraction) -> int:
    if value >= RNE_OVERFLOW_THRESHOLD:
        return POSITIVE_INFINITY
    if value > MAX_FINITE_VALUE:
        return MAX_FINITE

    lower = _positive_floor(value)
    lower_value = _positive_finite_value(lower)
    if lower_value == value:
        return lower
    upper = _positive_ceil(value)
    # The overflow case was handled above, so this endpoint is finite.
    upper_value = _positive_finite_value(upper)
    lower_distance = value - lower_value
    upper_distance = upper_value - value
    if lower_distance < upper_distance:
        return lower
    if upper_distance < lower_distance:
        return upper
    return lower if (lower & 1) == 0 else upper


def round_nearest_even(value: Fraction | int) -> int:
    """Correctly round an exact rational to nearest, with ties to even."""

    value = _as_fraction(value)
    if value == 0:
        return POSITIVE_ZERO
    if value > 0:
        return _round_positive_nearest_even(value)
    return _negate_non_nan_bits(_round_positive_nearest_even(-value))


def next_up_bits(bits: int) -> int:
    """Return the least binary64 value numerically greater than ``bits``.

    Positive infinity is a fixed point.  NaNs are rejected.  The two zero
    encodings are treated as the same numeric value, so either advances to the
    smallest positive subnormal.
    """

    bits = _validate_bits(bits)
    if is_nan(bits):
        raise NonFiniteBinary64Error("next_up_bits rejects NaN")
    if bits == POSITIVE_INFINITY:
        return POSITIVE_INFINITY
    if bits == NEGATIVE_INFINITY:
        return MIN_FINITE
    if is_zero(bits):
        return MIN_POSITIVE_SUBNORMAL
    return bits - 1 if bits & SIGN_MASK else bits + 1


def next_down_bits(bits: int) -> int:
    """Return the greatest binary64 value numerically less than ``bits``."""

    bits = _validate_bits(bits)
    if is_nan(bits):
        raise NonFiniteBinary64Error("next_down_bits rejects NaN")
    if bits == NEGATIVE_INFINITY:
        return NEGATIVE_INFINITY
    if bits == POSITIVE_INFINITY:
        return MAX_FINITE
    if is_zero(bits):
        return SIGN_MASK | MIN_POSITIVE_SUBNORMAL
    return bits + 1 if bits & SIGN_MASK else bits - 1


_RoundingFunction = Callable[[Fraction | int], int]


def _zero_for_addition(
    a_bits: int,
    effective_b_sign: int,
    effective_b_is_zero: bool,
    rounding: _RoundingFunction,
) -> int:
    a_sign = sign_bit(a_bits)
    if is_zero(a_bits) and effective_b_is_zero and a_sign == effective_b_sign:
        return NEGATIVE_ZERO if a_sign else POSITIVE_ZERO
    return NEGATIVE_ZERO if rounding is round_down else POSITIVE_ZERO


def _add_exact(
    a_bits: int,
    b_bits: int,
    rounding: _RoundingFunction,
) -> int:
    exact = decode_finite(a_bits) + decode_finite(b_bits)
    if exact == 0:
        return _zero_for_addition(
            a_bits, sign_bit(b_bits), is_zero(b_bits), rounding
        )
    return rounding(exact)


def _sub_exact(
    a_bits: int,
    b_bits: int,
    rounding: _RoundingFunction,
) -> int:
    exact = decode_finite(a_bits) - decode_finite(b_bits)
    if exact == 0:
        return _zero_for_addition(
            a_bits, sign_bit(b_bits) ^ 1, is_zero(b_bits), rounding
        )
    return rounding(exact)


def _mul_exact(
    a_bits: int,
    b_bits: int,
    rounding: _RoundingFunction,
) -> int:
    exact = decode_finite(a_bits) * decode_finite(b_bits)
    if exact == 0:
        return NEGATIVE_ZERO if sign_bit(a_bits) ^ sign_bit(b_bits) else POSITIVE_ZERO
    return rounding(exact)


def _div_exact(
    a_bits: int,
    b_bits: int,
    rounding: _RoundingFunction,
) -> int:
    numerator = decode_finite(a_bits)
    denominator = decode_finite(b_bits)
    if denominator == 0:
        raise InvalidBinary64Operation("division by a signed zero is invalid")
    exact = numerator / denominator
    if exact == 0:
        return NEGATIVE_ZERO if sign_bit(a_bits) ^ sign_bit(b_bits) else POSITIVE_ZERO
    return rounding(exact)


def add_down(a_bits: int, b_bits: int) -> int:
    return _add_exact(a_bits, b_bits, round_down)


def add_up(a_bits: int, b_bits: int) -> int:
    return _add_exact(a_bits, b_bits, round_up)


def add_rne(a_bits: int, b_bits: int) -> int:
    return _add_exact(a_bits, b_bits, round_nearest_even)


def sub_down(a_bits: int, b_bits: int) -> int:
    return _sub_exact(a_bits, b_bits, round_down)


def sub_up(a_bits: int, b_bits: int) -> int:
    return _sub_exact(a_bits, b_bits, round_up)


def sub_rne(a_bits: int, b_bits: int) -> int:
    return _sub_exact(a_bits, b_bits, round_nearest_even)


def mul_down(a_bits: int, b_bits: int) -> int:
    return _mul_exact(a_bits, b_bits, round_down)


def mul_up(a_bits: int, b_bits: int) -> int:
    return _mul_exact(a_bits, b_bits, round_up)


def mul_rne(a_bits: int, b_bits: int) -> int:
    return _mul_exact(a_bits, b_bits, round_nearest_even)


def div_down(a_bits: int, b_bits: int) -> int:
    return _div_exact(a_bits, b_bits, round_down)


def div_up(a_bits: int, b_bits: int) -> int:
    return _div_exact(a_bits, b_bits, round_up)


def div_rne(a_bits: int, b_bits: int) -> int:
    return _div_exact(a_bits, b_bits, round_nearest_even)


def _endpoint_rank(bits: int) -> tuple[int, Fraction]:
    bits = _validate_bits(bits)
    kind = classify(bits)
    if kind is Binary64Class.NAN:
        raise ValueError("NaN is not an interval endpoint")
    if kind is Binary64Class.NEGATIVE_INFINITY:
        return (0, Fraction())
    if kind is Binary64Class.POSITIVE_INFINITY:
        return (2, Fraction())
    return (1, decode_finite(bits))


def _endpoint_compare(left: int, right: int) -> int:
    left_rank = _endpoint_rank(left)
    right_rank = _endpoint_rank(right)
    if left_rank < right_rank:
        return -1
    if right_rank < left_rank:
        return 1
    return 0


def _minimum_endpoint(left: int, right: int) -> int:
    comparison = _endpoint_compare(left, right)
    if comparison < 0:
        return left
    if comparison > 0:
        return right
    if is_zero(left) and is_zero(right):
        return NEGATIVE_ZERO if sign_bit(left) or sign_bit(right) else POSITIVE_ZERO
    return left


def _maximum_endpoint(left: int, right: int) -> int:
    comparison = _endpoint_compare(left, right)
    if comparison > 0:
        return left
    if comparison < 0:
        return right
    if is_zero(left) and is_zero(right):
        return POSITIVE_ZERO if not (sign_bit(left) and sign_bit(right)) else NEGATIVE_ZERO
    return left


@dataclass(frozen=True, slots=True)
class Binary64Interval:
    """A nonempty closed interval with raw non-NaN binary64 endpoints."""

    lo: int
    hi: int

    def __post_init__(self) -> None:
        _validate_bits(self.lo)
        _validate_bits(self.hi)
        if is_nan(self.lo) or is_nan(self.hi):
            raise ValueError("NaN is not a valid interval endpoint")
        if _endpoint_compare(self.lo, self.hi) > 0:
            raise ValueError("interval lower endpoint exceeds upper endpoint")

    @property
    def has_finite_endpoints(self) -> bool:
        return is_finite(self.lo) and is_finite(self.hi)

    def contains_zero(self) -> bool:
        return (
            _endpoint_compare(self.lo, POSITIVE_ZERO) <= 0
            and _endpoint_compare(POSITIVE_ZERO, self.hi) <= 0
        )


WHOLE_INTERVAL = Binary64Interval(NEGATIVE_INFINITY, POSITIVE_INFINITY)


def _require_finite_intervals(*intervals: Binary64Interval) -> bool:
    if not all(isinstance(interval, Binary64Interval) for interval in intervals):
        raise TypeError("interval operation requires Binary64Interval operands")
    return all(interval.has_finite_endpoints for interval in intervals)


def interval_add(a: Binary64Interval, b: Binary64Interval) -> Binary64Interval:
    """Outward-rounded interval addition."""

    if not _require_finite_intervals(a, b):
        return WHOLE_INTERVAL
    return Binary64Interval(add_down(a.lo, b.lo), add_up(a.hi, b.hi))


def interval_sub(a: Binary64Interval, b: Binary64Interval) -> Binary64Interval:
    """Outward-rounded interval subtraction."""

    if not _require_finite_intervals(a, b):
        return WHOLE_INTERVAL
    return Binary64Interval(sub_down(a.lo, b.hi), sub_up(a.hi, b.lo))


def _select_four(
    values: tuple[int, int, int, int],
    selector: Callable[[int, int], int],
) -> int:
    result = values[0]
    for value in values[1:]:
        result = selector(result, value)
    return result


def interval_mul(a: Binary64Interval, b: Binary64Interval) -> Binary64Interval:
    """Outward-rounded interval multiplication."""

    if not _require_finite_intervals(a, b):
        return WHOLE_INTERVAL
    lower_candidates = (
        mul_down(a.lo, b.lo),
        mul_down(a.lo, b.hi),
        mul_down(a.hi, b.lo),
        mul_down(a.hi, b.hi),
    )
    upper_candidates = (
        mul_up(a.lo, b.lo),
        mul_up(a.lo, b.hi),
        mul_up(a.hi, b.lo),
        mul_up(a.hi, b.hi),
    )
    return Binary64Interval(
        _select_four(lower_candidates, _minimum_endpoint),
        _select_four(upper_candidates, _maximum_endpoint),
    )


def interval_div(a: Binary64Interval, b: Binary64Interval) -> Binary64Interval:
    """Outward-rounded interval division, rejecting a zero-containing divisor."""

    if not isinstance(a, Binary64Interval) or not isinstance(b, Binary64Interval):
        raise TypeError("interval operation requires Binary64Interval operands")
    if b.contains_zero():
        raise InvalidBinary64Operation("divisor interval contains zero")
    if not _require_finite_intervals(a, b):
        return WHOLE_INTERVAL
    lower_candidates = (
        div_down(a.lo, b.lo),
        div_down(a.lo, b.hi),
        div_down(a.hi, b.lo),
        div_down(a.hi, b.hi),
    )
    upper_candidates = (
        div_up(a.lo, b.lo),
        div_up(a.lo, b.hi),
        div_up(a.hi, b.lo),
        div_up(a.hi, b.hi),
    )
    return Binary64Interval(
        _select_four(lower_candidates, _minimum_endpoint),
        _select_four(upper_candidates, _maximum_endpoint),
    )


def interval_neg(a: Binary64Interval) -> Binary64Interval:
    """Exact interval negation, including infinity and signed-zero endpoints."""

    if not isinstance(a, Binary64Interval):
        raise TypeError("interval operation requires a Binary64Interval operand")
    return Binary64Interval(
        _negate_non_nan_bits(a.hi),
        _negate_non_nan_bits(a.lo),
    )


def _abs_bits(bits: int) -> int:
    bits = _validate_bits(bits)
    if is_nan(bits):
        raise ValueError("cannot take interval absolute value of NaN")
    return bits & ~SIGN_MASK


def interval_abs(a: Binary64Interval) -> Binary64Interval:
    """Exact range of absolute value over an interval."""

    if not isinstance(a, Binary64Interval):
        raise TypeError("interval operation requires a Binary64Interval operand")
    if _endpoint_compare(a.lo, POSITIVE_ZERO) >= 0:
        return Binary64Interval(_abs_bits(a.lo), _abs_bits(a.hi))
    if _endpoint_compare(a.hi, POSITIVE_ZERO) <= 0:
        return Binary64Interval(_abs_bits(a.hi), _abs_bits(a.lo))
    return Binary64Interval(
        POSITIVE_ZERO,
        _maximum_endpoint(_abs_bits(a.lo), _abs_bits(a.hi)),
    )


def interval_min(a: Binary64Interval, b: Binary64Interval) -> Binary64Interval:
    """Range of pointwise minimum for independently varying interval values."""

    if not isinstance(a, Binary64Interval) or not isinstance(b, Binary64Interval):
        raise TypeError("interval operation requires Binary64Interval operands")
    return Binary64Interval(
        _minimum_endpoint(a.lo, b.lo),
        _minimum_endpoint(a.hi, b.hi),
    )


def interval_max(a: Binary64Interval, b: Binary64Interval) -> Binary64Interval:
    """Range of pointwise maximum for independently varying interval values."""

    if not isinstance(a, Binary64Interval) or not isinstance(b, Binary64Interval):
        raise TypeError("interval operation requires Binary64Interval operands")
    return Binary64Interval(
        _maximum_endpoint(a.lo, b.lo),
        _maximum_endpoint(a.hi, b.hi),
    )


def interval_pow_nat(a: Binary64Interval, exponent: int) -> Binary64Interval:
    """Repeated outward interval multiplication for a natural-number power.

    This intentionally follows the formal ``pow`` recurrence, rather than
    computing the tight range of the dependent function ``x ↦ x^n``.  Thus
    ``[-1, 1]^2`` is ``[-1, 1]``: the two occurrences are treated as
    independently varying interval values by interval multiplication.  The
    wire format caps the exponent at a small value.
    """

    if isinstance(exponent, bool) or not isinstance(exponent, int) or exponent < 0:
        raise ValueError("interval exponent must be a nonnegative integer")
    if not isinstance(a, Binary64Interval):
        raise TypeError("interval operation requires a Binary64Interval operand")
    one = 0x3FF0000000000000
    result = Binary64Interval(one, one)
    for _ in range(exponent):
        result = interval_mul(result, a)
    return result
