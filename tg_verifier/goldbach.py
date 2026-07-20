# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact bounded certificate primitives related to ternary Goldbach.

This module checks small, explicit certificate objects with integer arithmetic.
It does **not** verify Helfgott--Platt Theorem 4.1, the binary-Goldbach
computation through ``4 * 10**18``, the full prime ladder used by that
argument, or any production GPU run.  In particular, a successful sample
check must not be reported as coverage of one of those source computations.

The direct primality predicate is exact only on the documented unsigned
64-bit domain.  Larger primes may be represented only by the deliberately
limited Proth-certificate interface below.  These restrictions make every
accepted certificate's trust boundary explicit and keep malformed inputs
fail-closed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


MAX_DETERMINISTIC_PRIME_INPUT = (1 << 64) - 1
"""Largest input accepted by :func:`is_prime_bounded`."""

MAX_PROTH_EXPONENT = 256
"""Resource guard for the bounded Proth-certificate checker."""

_MILLER_RABIN_BASES_64 = (
    2,
    325,
    9_375,
    28_178,
    450_775,
    9_780_504,
    1_795_265_022,
)

_SMALL_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)


def _is_plain_int(value: object) -> bool:
    """Return whether ``value`` is an integer but not a Boolean."""

    return isinstance(value, int) and not isinstance(value, bool)


def is_prime_bounded(value: int) -> bool:
    """Decide primality exactly for ``0 <= value < 2**64``.

    The seven fixed Miller--Rabin bases used here are deterministic throughout
    that domain.  Values outside the domain, including negative integers and
    non-integers, are rejected rather than treated as probable primes.
    """

    if (
        not _is_plain_int(value)
        or value < 2
        or value > MAX_DETERMINISTIC_PRIME_INPUT
    ):
        return False

    for prime in _SMALL_PRIMES:
        if value == prime:
            return True
        if value % prime == 0:
            return False

    # Write value - 1 = odd_part * 2**power_of_two.
    odd_part = value - 1
    power_of_two = 0
    while odd_part & 1 == 0:
        odd_part >>= 1
        power_of_two += 1

    for base in _MILLER_RABIN_BASES_64:
        base %= value
        if base == 0:
            continue
        residue = pow(base, odd_part, value)
        if residue in (1, value - 1):
            continue
        for _ in range(power_of_two - 1):
            residue = residue * residue % value
            if residue == value - 1:
                break
        else:
            return False
    return True


def jacobi_symbol(numerator: int, denominator: int) -> int:
    """Return the exact Jacobi symbol ``(numerator / denominator)``.

    ``denominator`` must be a positive odd integer.  Unlike the certificate
    predicates, this low-level arithmetic operation raises on a malformed
    domain so callers cannot accidentally interpret a sentinel as a symbol.
    """

    if not _is_plain_int(numerator):
        raise TypeError("numerator must be an integer")
    if not _is_plain_int(denominator):
        raise TypeError("denominator must be an integer")
    if denominator <= 0 or denominator % 2 == 0:
        raise ValueError("denominator must be a positive odd integer")

    numerator %= denominator
    result = 1
    while numerator:
        while numerator % 2 == 0:
            numerator //= 2
            residue = denominator % 8
            if residue in (3, 5):
                result = -result
        numerator, denominator = denominator, numerator
        if numerator % 4 == denominator % 4 == 3:
            result = -result
        numerator %= denominator
    return result if denominator == 1 else 0


@dataclass(frozen=True)
class ProthCertificate:
    """A witness for a number of the form ``k * 2**exponent + 1``."""

    number: int
    k: int
    exponent: int
    witness: int


def check_proth_certificate(certificate: ProthCertificate) -> bool:
    """Validate the hypotheses and congruence in Proth's theorem exactly.

    Besides the usual Proth-shape guards, the checker requires both
    ``Jacobi(witness, number) = -1`` and
    ``witness**((number - 1) / 2) = -1 (mod number)``.  The exponent cap is a
    resource bound on untrusted certificate inputs, not a mathematical one.
    """

    if not isinstance(certificate, ProthCertificate):
        return False
    fields = (
        certificate.number,
        certificate.k,
        certificate.exponent,
        certificate.witness,
    )
    if not all(_is_plain_int(field) for field in fields):
        return False

    number = certificate.number
    k = certificate.k
    exponent = certificate.exponent
    witness = certificate.witness
    if number <= 2 or k <= 0 or k % 2 == 0:
        return False
    if exponent < 1 or exponent > MAX_PROTH_EXPONENT:
        return False

    power = 1 << exponent
    if k >= power or number != k * power + 1:
        return False
    if witness < 2 or witness >= number:
        return False
    if jacobi_symbol(witness, number) != -1:
        return False
    return pow(witness, (number - 1) // 2, number) == number - 1


@dataclass(frozen=True)
class PrimeCertificate:
    """A prime value checked directly or by the bounded Proth interface."""

    number: int
    proth: ProthCertificate | None = None


def check_prime_certificate(certificate: PrimeCertificate) -> bool:
    """Validate one supported prime certificate, failing closed."""

    if not isinstance(certificate, PrimeCertificate):
        return False
    if not _is_plain_int(certificate.number):
        return False
    if certificate.proth is None:
        return is_prime_bounded(certificate.number)
    return (
        isinstance(certificate.proth, ProthCertificate)
        and certificate.number == certificate.proth.number
        and check_proth_certificate(certificate.proth)
    )


@dataclass(frozen=True)
class TernaryGoldbachWitness:
    """Three explicit primes claimed to sum to one odd target."""

    target: int
    p: int
    q: int
    r: int


def check_ternary_goldbach_witness(
    witness: TernaryGoldbachWitness,
) -> bool:
    """Check one explicit ternary-Goldbach witness exactly."""

    if not isinstance(witness, TernaryGoldbachWitness):
        return False
    fields = (witness.target, witness.p, witness.q, witness.r)
    if not all(_is_plain_int(field) for field in fields):
        return False
    if witness.target < 7 or witness.target % 2 == 0:
        return False
    if witness.p + witness.q + witness.r != witness.target:
        return False
    return all(is_prime_bounded(prime) for prime in fields[1:])


def check_ternary_goldbach_interval(
    first_odd: int,
    last_odd: int,
    witnesses: Sequence[TernaryGoldbachWitness],
) -> bool:
    """Check explicit witnesses for every odd integer in an inclusive interval.

    The witness sequence must contain exactly one entry for each target, in
    increasing order ``first_odd, first_odd + 2, ..., last_odd``.  Consequently
    omissions, duplicates, reordered entries, and endpoint truncation all
    fail rather than silently narrowing the claimed interval.
    """

    if not _is_plain_int(first_odd) or not _is_plain_int(last_odd):
        return False
    if (
        first_odd < 7
        or first_odd > last_odd
        or first_odd % 2 == 0
        or last_odd % 2 == 0
    ):
        return False
    if not isinstance(witnesses, Sequence):
        return False

    expected_count = (last_odd - first_odd) // 2 + 1
    if len(witnesses) != expected_count:
        return False
    for offset, witness in enumerate(witnesses):
        expected_target = first_odd + 2 * offset
        if (
            not isinstance(witness, TernaryGoldbachWitness)
            or witness.target != expected_target
            or not check_ternary_goldbach_witness(witness)
        ):
            return False
    return True


@dataclass(frozen=True)
class PrimeLadderCertificate:
    """An ordered list of certified primes bracketing an interval."""

    interval_start: int
    interval_end: int
    maximum_gap: int
    rungs: tuple[PrimeCertificate, ...]


def check_prime_ladder(certificate: PrimeLadderCertificate) -> bool:
    """Check prime validity, ordering, gaps, and inclusive interval coverage.

    The first rung must be at or below ``interval_start`` and the last at or
    above ``interval_end``.  Each consecutive gap must be positive and at most
    ``maximum_gap``.  This generic coverage fact does not itself prove ternary
    Goldbach: using such a ladder requires a separate binary-Goldbach theorem
    with precisely matched ranges and inequalities.
    """

    if not isinstance(certificate, PrimeLadderCertificate):
        return False
    bounds = (
        certificate.interval_start,
        certificate.interval_end,
        certificate.maximum_gap,
    )
    if not all(_is_plain_int(value) for value in bounds):
        return False
    if (
        certificate.interval_start < 0
        or certificate.interval_start > certificate.interval_end
        or certificate.maximum_gap <= 0
    ):
        return False
    if not isinstance(certificate.rungs, tuple) or not certificate.rungs:
        return False
    if not all(check_prime_certificate(rung) for rung in certificate.rungs):
        return False

    numbers = tuple(rung.number for rung in certificate.rungs)
    if numbers[0] > certificate.interval_start:
        return False
    if numbers[-1] < certificate.interval_end:
        return False
    return all(
        0 < right - left <= certificate.maximum_gap
        for left, right in zip(numbers, numbers[1:])
    )


__all__ = (
    "MAX_DETERMINISTIC_PRIME_INPUT",
    "MAX_PROTH_EXPONENT",
    "PrimeCertificate",
    "PrimeLadderCertificate",
    "ProthCertificate",
    "TernaryGoldbachWitness",
    "check_prime_certificate",
    "check_prime_ladder",
    "check_proth_certificate",
    "check_ternary_goldbach_interval",
    "check_ternary_goldbach_witness",
    "is_prime_bounded",
    "jacobi_symbol",
)
