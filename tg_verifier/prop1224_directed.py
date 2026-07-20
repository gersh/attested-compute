"""Directed rational producer for Helfgott Proposition 12.2.4 samples.

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

This module computes the source window endpoints and final margins itself.  It
does not accept decimal endpoint or margin values from a caller, and no native
floating-point value participates in a branch or inequality decision.

The elementary-function implementation is deliberately small:

* ``log(x)`` uses the positive atanh series after exact power-of-two range
  reduction;
* ``exp(x)`` uses a Taylor series with a geometric majorant for the tail;
* ``x**y`` is enclosed as ``exp(y * log(x))`` for positive ``x``; and
* cube roots of positive integers use an exact integer cube-root enclosure.

Two theorem-backed intervals are inputs to the rational computation rather
than caller-supplied data:

* ``577215657/10^9 <= EulerGamma <= 5772162/10^7``, bridged in Lean by
  ``Real.eulerMascheroniConstant_ge_d577215657`` and
  ``AnalyticNT.LargeSieve.eulerMascheroni_le_d5772162``; and
* ``1.3325822 <= c_E <= 1.3339``, bridged by
  ``RamareCE_lower_bound_holds`` and ``ramareCE_le_1_3339``.

Consequently a returned row is a sound directed enclosure conditional only on
those explicit theorem inputs and ordinary exact-integer/rational execution.
It is still a *bounded one-q reference*: this file has neither run the
3,389,047,618-row source campaign nor proved a Lean realization theorem for
the Python evaluator.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

from .finite_campaigns import (
    FiniteCampaignError,
    Prop1224Chunk,
    Prop1224Window,
    create_prop1224_chunk,
    create_prop1224_window,
    prop1224_next_q,
    prop1224_q_is_admissible,
    ramare_g_prefixes,
    verify_prop1224_chunk,
    verify_prop1224_window,
)


DEFAULT_BITS = 144
DEFAULT_LOG_TERMS = 48
MAX_SAMPLE_PAIRS = 100_000
MAX_DIRECTED_CHUNK_Q_ROWS = 10_000

EULER_GAMMA_BOUNDS = (
    Fraction(577_215_657, 10**9),
    Fraction(5_772_162, 10**7),
)
RAMARE_CE_BOUNDS = (
    Fraction(13_325_822, 10**7),
    Fraction(13_339, 10**4),
)


@dataclass(frozen=True)
class RationalInterval:
    """A closed rational interval, with exact endpoints."""

    lower: Fraction
    upper: Fraction

    def __post_init__(self) -> None:
        if not isinstance(self.lower, Fraction) or not isinstance(
            self.upper, Fraction
        ):
            raise FiniteCampaignError("interval endpoints must be Fractions")
        if self.lower > self.upper:
            raise FiniteCampaignError("rational interval is reversed")

    @classmethod
    def exact(cls, value: int | Fraction) -> "RationalInterval":
        if isinstance(value, bool) or not isinstance(value, (int, Fraction)):
            raise FiniteCampaignError("exact interval value must be rational")
        rational = Fraction(value)
        return cls(rational, rational)

    def contains(self, value: int | Fraction) -> bool:
        if isinstance(value, bool) or not isinstance(value, (int, Fraction)):
            return False
        return self.lower <= Fraction(value) <= self.upper


def _validate_precision(bits: int, terms: int) -> None:
    if isinstance(bits, bool) or not isinstance(bits, int) or bits < 32:
        raise FiniteCampaignError("bits must be an integer at least 32")
    if bits > 4_096:
        raise FiniteCampaignError("bits exceeds the rational safety limit")
    if isinstance(terms, bool) or not isinstance(terms, int) or terms < 8:
        raise FiniteCampaignError("log terms must be an integer at least 8")
    if terms > 4_096:
        raise FiniteCampaignError("log terms exceeds the rational safety limit")


def _floor(value: Fraction) -> int:
    return value.numerator // value.denominator


def _ceil(value: Fraction) -> int:
    return -((-value.numerator) // value.denominator)


def _round_down(value: Fraction, bits: int) -> Fraction:
    scale = 1 << bits
    return Fraction(_floor(value * scale), scale)


def _round_up(value: Fraction, bits: int) -> Fraction:
    scale = 1 << bits
    return Fraction(_ceil(value * scale), scale)


def _outward(value: RationalInterval, bits: int) -> RationalInterval:
    return RationalInterval(
        _round_down(value.lower, bits), _round_up(value.upper, bits)
    )


def _neg(value: RationalInterval) -> RationalInterval:
    return RationalInterval(-value.upper, -value.lower)


def _add(
    left: RationalInterval, right: RationalInterval, bits: int
) -> RationalInterval:
    return _outward(
        RationalInterval(left.lower + right.lower, left.upper + right.upper),
        bits,
    )


def _sub(
    left: RationalInterval, right: RationalInterval, bits: int
) -> RationalInterval:
    return _add(left, _neg(right), bits)


def _mul(
    left: RationalInterval, right: RationalInterval, bits: int
) -> RationalInterval:
    products = (
        left.lower * right.lower,
        left.lower * right.upper,
        left.upper * right.lower,
        left.upper * right.upper,
    )
    return _outward(RationalInterval(min(products), max(products)), bits)


def _reciprocal(value: RationalInterval, bits: int) -> RationalInterval:
    if value.lower <= 0 <= value.upper:
        raise FiniteCampaignError("cannot invert an interval containing zero")
    return _outward(
        RationalInterval(Fraction(1, value.upper), Fraction(1, value.lower)),
        bits,
    )


def _div(
    numerator: RationalInterval, denominator: RationalInterval, bits: int
) -> RationalInterval:
    return _mul(numerator, _reciprocal(denominator, bits), bits)


def _pow_nat(value: RationalInterval, exponent: int, bits: int) -> RationalInterval:
    if isinstance(exponent, bool) or not isinstance(exponent, int) or exponent < 0:
        raise FiniteCampaignError("natural interval exponent must be nonnegative")
    result = RationalInterval.exact(1)
    base = value
    power = exponent
    while power:
        if power & 1:
            result = _mul(result, base, bits)
        power >>= 1
        if power:
            base = _mul(base, base, bits)
    return result


def _max_interval(*values: RationalInterval) -> RationalInterval:
    if not values:
        raise FiniteCampaignError("interval maximum needs at least one value")
    return RationalInterval(
        max(value.lower for value in values),
        max(value.upper for value in values),
    )


def _power_of_two(exponent: int) -> Fraction:
    if exponent >= 0:
        return Fraction(1 << exponent)
    return Fraction(1, 1 << -exponent)


@lru_cache(maxsize=65_536)
def _log_point_bounds(value: Fraction, terms: int) -> RationalInterval:
    """Rigorous atanh-series bounds for ``log(value)``, ``value > 0``."""

    if value <= 0:
        raise FiniteCampaignError("logarithm requires a positive rational")
    if terms < 1:
        raise FiniteCampaignError("logarithm needs at least one series term")

    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    while value < _power_of_two(exponent):
        exponent -= 1
    while value >= _power_of_two(exponent + 1):
        exponent += 1
    mantissa = value / _power_of_two(exponent)

    def unit_log_bounds(argument: Fraction) -> RationalInterval:
        if not 1 <= argument <= 2:
            raise FiniteCampaignError("log range reduction failed")
        z = (argument - 1) / (argument + 1)
        if z == 0:
            return RationalInterval.exact(0)
        z_squared = z * z
        power = z
        partial = Fraction(0)
        for index in range(terms):
            partial += power / (2 * index + 1)
            power *= z_squared
        lower = 2 * partial
        tail = 2 * power / ((2 * terms + 1) * (1 - z_squared))
        return RationalInterval(lower, lower + tail)

    mantissa_log = unit_log_bounds(mantissa)
    log_two = unit_log_bounds(Fraction(2))
    if exponent >= 0:
        return RationalInterval(
            mantissa_log.lower + exponent * log_two.lower,
            mantissa_log.upper + exponent * log_two.upper,
        )
    return RationalInterval(
        mantissa_log.lower + exponent * log_two.upper,
        mantissa_log.upper + exponent * log_two.lower,
    )


def log_interval(
    value: RationalInterval, *, bits: int, terms: int
) -> RationalInterval:
    """Enclose the logarithm of a positive interval."""

    _validate_precision(bits, terms)
    if value.lower <= 0:
        raise FiniteCampaignError("log interval must be strictly positive")
    lower = _log_point_bounds(value.lower, terms).lower
    upper = _log_point_bounds(value.upper, terms).upper
    return _outward(RationalInterval(lower, upper), bits)


@lru_cache(maxsize=65_536)
def _exp_nonnegative_point(
    value: Fraction, bits: int, terms: int
) -> RationalInterval:
    """Taylor enclosure for ``exp(value)`` when ``value >= 0``."""

    if value < 0:
        raise FiniteCampaignError("internal exp series received a negative value")
    if value == 0:
        return RationalInterval.exact(1)

    divisor = 1
    while value * 8 > divisor:
        divisor <<= 1
    reduced = value / divisor

    partial = Fraction(1)
    term = Fraction(1)
    for index in range(1, terms + 1):
        term = term * reduced / index
        partial += term
    next_term = term * reduced / (terms + 1)
    ratio = reduced / (terms + 2)
    tail = next_term / (1 - ratio)
    base = _outward(RationalInterval(partial, partial + tail), bits)
    return _pow_nat(base, divisor, bits)


def _exp_point_bounds(
    value: Fraction, bits: int, terms: int
) -> RationalInterval:
    if value >= 0:
        return _exp_nonnegative_point(value, bits, terms)
    return _reciprocal(_exp_nonnegative_point(-value, bits, terms), bits)


def exp_interval(
    value: RationalInterval, *, bits: int, terms: int
) -> RationalInterval:
    """Enclose ``exp(value)`` using its monotonicity."""

    _validate_precision(bits, terms)
    lower = _exp_point_bounds(value.lower, bits, terms).lower
    upper = _exp_point_bounds(value.upper, bits, terms).upper
    return _outward(RationalInterval(lower, upper), bits)


def rpow_interval(
    base: RationalInterval,
    exponent: RationalInterval,
    *,
    bits: int,
    terms: int,
) -> RationalInterval:
    """Enclose ``base**exponent`` for a strictly positive base."""

    logarithm = log_interval(base, bits=bits, terms=terms)
    product = _mul(logarithm, exponent, bits)
    return exp_interval(product, bits=bits, terms=terms)


def _integer_cube_root_floor(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FiniteCampaignError("integer cube root needs a natural number")
    lower = 0
    upper = 1 << ((value.bit_length() + 2) // 3)
    while lower + 1 < upper:
        middle = (lower + upper) // 2
        if middle * middle * middle <= value:
            lower = middle
        else:
            upper = middle
    return lower


@lru_cache(maxsize=65_536)
def integer_cube_root_interval(value: int, bits: int) -> RationalInterval:
    """Return a dyadic enclosure of the positive real cube root."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FiniteCampaignError("cube-root radicand must be a positive integer")
    if isinstance(bits, bool) or not isinstance(bits, int) or bits < 1:
        raise FiniteCampaignError("cube-root bits must be positive")
    scale = 1 << bits
    scaled = value * scale * scale * scale
    lower = _integer_cube_root_floor(scaled)
    if lower * lower * lower == scaled:
        return RationalInterval.exact(Fraction(lower, scale))
    return RationalInterval(Fraction(lower, scale), Fraction(lower + 1, scale))


def _distinct_prime_factors(value: int) -> tuple[int, ...]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise FiniteCampaignError("q must be a positive integer")
    remainder = value
    factors: list[int] = []
    divisor = 2
    while divisor * divisor <= remainder:
        if remainder % divisor == 0:
            factors.append(divisor)
            while remainder % divisor == 0:
                remainder //= divisor
        divisor = 3 if divisor == 2 else divisor + 2
    if remainder > 1:
        factors.append(remainder)
    return tuple(factors)


def _totient_from_factors(value: int, factors: tuple[int, ...]) -> int:
    result = value
    for prime in factors:
        result -= result // prime
    return result


@dataclass(frozen=True)
class Prop1224DirectedParameters:
    """All source expressions needed to construct one directed q row."""

    q: int
    prime_factors: tuple[int, ...]
    phi_q: int
    log_q: RationalInterval
    log_prime_sum: RationalInterval
    euler_gamma: RationalInterval
    ramare_ce: RationalInterval
    tau: RationalInterval
    c_sigma: RationalInterval
    c2: RationalInterval
    kappa: RationalInterval
    f1: RationalInterval
    varpi: RationalInterval
    lambda_: RationalInterval
    bits: int
    log_terms: int


def prop1224_directed_parameters(
    q: int, *, bits: int = DEFAULT_BITS, log_terms: int = DEFAULT_LOG_TERMS
) -> Prop1224DirectedParameters:
    """Compute source-exact directed endpoint parameters for one admissible q."""

    _validate_precision(bits, log_terms)
    if not prop1224_q_is_admissible(q):
        raise FiniteCampaignError("q is outside the Proposition 12.2.4 range")

    exact = RationalInterval.exact
    one = exact(1)
    omega = exact(Fraction(627_312, 10**6))
    beta = exact(Fraction(23_111, 10**6))
    gamma = RationalInterval(*EULER_GAMMA_BOUNDS)
    ce = RationalInterval(*RAMARE_CE_BOUNDS)

    factors = _distinct_prime_factors(q)
    phi_q = _totient_from_factors(q, factors)
    log_q = log_interval(exact(q), bits=bits, terms=log_terms)
    log_prime_sum = exact(0)
    for prime in factors:
        log_prime = log_interval(exact(prime), bits=bits, terms=log_terms)
        log_prime_sum = _add(
            log_prime_sum, _mul(log_prime, exact(Fraction(1, prime)), bits), bits
        )

    exp_minus_gamma = exp_interval(_neg(gamma), bits=bits, terms=log_terms)
    tau = _mul(exact(Fraction(2, 5)), exp_minus_gamma, bits)

    sigma = Fraction(34, 25)
    sigma_expression = sigma - sigma * sigma / Fraction(656, 125) - Fraction(293, 250)
    c_sigma_exponent = _mul(exp_minus_gamma, exact(sigma_expression), bits)
    c_sigma = exp_interval(c_sigma_exponent, bits=bits, terms=log_terms)

    # Algebraically simplify the source exponent so the two occurrences of
    # c_E which cancel are not spuriously treated as independent intervals.
    c2_exponent = _add(
        exact(Fraction(1_109, 10_000)),
        _mul(omega, _sub(ce, exact(Fraction(164, 125)), bits), bits),
        bits,
    )
    c2 = exp_interval(c2_exponent, bits=bits, terms=log_terms)

    c_delta = _sub(exact(Fraction(34, 25)), ce, bits)
    kappa = _add(
        _mul(
            _sub(one, omega, bits),
            _sub(log_q, log_prime_sum, bits),
            bits,
        ),
        c_delta,
        bits,
    )
    if kappa.lower <= 0:
        raise FiniteCampaignError("directed kappa enclosure does not prove positivity")

    f1 = exact(1)
    for prime in factors:
        cube_root = integer_cube_root_interval(prime, bits)
        two_thirds = _mul(cube_root, cube_root, bits)
        numerator = _add(one, _reciprocal(two_thirds, bits), bits)
        denominator = _add(
            one,
            _mul(
                _add(cube_root, two_thirds, bits),
                exact(Fraction(1, prime * (prime - 1))),
                bits,
            ),
            bits,
        )
        f1 = _mul(f1, _div(numerator, denominator, bits), bits)

    lambda_base = _div(
        _mul(
            _mul(
                exact(Fraction(q, phi_q)),
                exact(Fraction(1_821, 250) * (1 + Fraction(23_111, 10**6))),
                bits,
            ),
            f1,
            bits,
        ),
        kappa,
        bits,
    )
    lambda_ = _pow_nat(lambda_base, 3, bits)

    q_to_tau = rpow_interval(exact(q), tau, bits=bits, terms=log_terms)
    a_value = _mul(c_sigma, q_to_tau, bits)
    gate_left = _add(one, log_q, bits)
    if gate_left.upper < a_value.lower:
        difference = _sub(a_value, log_q, bits)
        if difference.lower <= 0:
            raise FiniteCampaignError("varpiZero base was not proved positive")
        exponent = _neg(_div(tau, _sub(one, tau, bits), bits))
        correction_power = rpow_interval(
            difference, exponent, bits=bits, terms=log_terms
        )
        inner = _sub(
            a_value, _mul(log_q, correction_power, bits), bits
        )
        if inner.lower <= 0:
            raise FiniteCampaignError("varpiZero outer base was not proved positive")
        varpi_zero = rpow_interval(
            inner,
            _reciprocal(_sub(one, tau, bits), bits),
            bits=bits,
            terms=log_terms,
        )
    elif gate_left.lower >= a_value.upper:
        varpi_zero = exact(0)
    else:
        raise FiniteCampaignError(
            "precision does not decide the strict varpiZero branch; increase bits/terms"
        )

    hundred_thousand_to_tau = rpow_interval(
        exact(100_000), tau, bits=bits, terms=log_terms
    )
    varpi_middle = _sub(
        _mul(c_sigma, hundred_thousand_to_tau, bits), log_q, bits
    )
    omega_exponent = _reciprocal(_sub(one, omega, bits), bits)
    varpi_last_denominator = rpow_interval(
        _mul(c2, exact(q), bits),
        omega_exponent,
        bits=bits,
        terms=log_terms,
    )
    varpi_last = _div(exact(100_000), varpi_last_denominator, bits)
    varpi = _outward(
        _max_interval(varpi_zero, varpi_middle, varpi_last), bits
    )

    return Prop1224DirectedParameters(
        q=q,
        prime_factors=factors,
        phi_q=phi_q,
        log_q=log_q,
        log_prime_sum=log_prime_sum,
        euler_gamma=gamma,
        ramare_ce=ce,
        tau=tau,
        c_sigma=c_sigma,
        c2=c2,
        kappa=kappa,
        f1=f1,
        varpi=varpi,
        lambda_=lambda_,
        bits=bits,
        log_terms=log_terms,
    )


def _prop1224_margin_interval_from_exact_g(
    parameters: Prop1224DirectedParameters, k: int, g_q_k: Fraction
) -> RationalInterval:
    """Compute one margin from an internally generated exact ``G_q(k)``."""

    if not isinstance(parameters, Prop1224DirectedParameters):
        raise FiniteCampaignError("parameters have the wrong type")
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise FiniteCampaignError("k must be a positive integer")
    if not isinstance(g_q_k, Fraction):
        raise FiniteCampaignError("G_q(k) must be an exact Fraction")

    bits = parameters.bits
    terms = parameters.log_terms
    exact = RationalInterval.exact
    log_k = log_interval(exact(k), bits=bits, terms=terms)
    phi_ratio = exact(Fraction(parameters.phi_q, parameters.q))

    # Expand RHS - err before interval evaluation.  The two occurrences of
    # c_E cancel exactly, and
    #   (1-omega)*(log q-L) + L
    # = (1-omega)*log q + omega*L.
    # Preserving that algebraic dependency is both tighter and closer to the
    # exact source expression than evaluating two independent c_E intervals.
    omega = exact(Fraction(627_312, 10**6))
    right_minus_error_inner = _add(
        _add(
            _mul(_sub(exact(1), omega, bits), parameters.log_q, bits),
            _mul(omega, parameters.log_prime_sum, bits),
            bits,
        ),
        _add(exact(Fraction(34, 25)), log_k, bits),
        bits,
    )
    right_minus_error = _sub(
        _mul(phi_ratio, right_minus_error_inner, bits), exact(g_q_k), bits
    )

    cube_root = integer_cube_root_interval(20_000 * k, bits)
    remote_envelope = _mul(
        _mul(
            exact(Fraction(627_312, 10**6) * Fraction(1_821, 250)),
            _reciprocal(cube_root, bits),
            bits,
        ),
        parameters.f1,
        bits,
    )
    return _sub(right_minus_error, remote_envelope, bits)


def prop1224_directed_margin_lower_from_g_upper(
    parameters: Prop1224DirectedParameters,
    k: int,
    g_q_k_upper: Fraction,
) -> Fraction:
    """Return a sound lower margin using an upper enclosure for ``G_q(k)``.

    The source margin is affine and decreasing in ``G_q(k)``.  Replacing the
    exact finite sum by any rational upper bound can therefore only decrease
    the margin.  This small interface lets the production campaign retain a
    bounded-memory fixed-point enclosure instead of constructing the enormous
    exact denominator of a prefix containing millions of terms.
    """

    if not isinstance(g_q_k_upper, Fraction):
        raise FiniteCampaignError("G_q(k) upper endpoint must be an exact Fraction")
    return _prop1224_margin_interval_from_exact_g(
        parameters, k, g_q_k_upper
    ).lower


def prop1224_directed_margin(
    q: int,
    k: int,
    *,
    bits: int = DEFAULT_BITS,
    log_terms: int = DEFAULT_LOG_TERMS,
) -> RationalInterval:
    """Recompute all parameters and exact ``G_q(k)``, then enclose the margin."""

    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise FiniteCampaignError("k must be a positive integer")
    parameters = prop1224_directed_parameters(
        q, bits=bits, log_terms=log_terms
    )
    g_q_k = ramare_g_prefixes(q, (k,))[k]
    return _prop1224_margin_interval_from_exact_g(parameters, k, g_q_k)


@dataclass(frozen=True)
class Prop1224DirectedSample:
    """One bounded directed row and its explicit assurance boundary."""

    parameters: Prop1224DirectedParameters
    window: Prop1224Window
    endpoint_enclosures_recomputed: bool = True
    margin_enclosures_recomputed: bool = True
    native_float_used_in_decisions: bool = False
    full_source_campaign: bool = False
    lean_realization_proved: bool = False


def create_directed_prop1224_sample(
    q: int,
    *,
    bits: int = DEFAULT_BITS,
    log_terms: int = DEFAULT_LOG_TERMS,
    max_pairs: int = MAX_SAMPLE_PAIRS,
) -> Prop1224DirectedSample:
    """Build a bounded, fully directed Proposition 12.2.4 q row.

    ``max_pairs`` is only a resource guard.  It cannot truncate a row: the
    function fails before producing a value if the complete conservative
    window would be larger.
    """

    if isinstance(max_pairs, bool) or not isinstance(max_pairs, int) or max_pairs < 0:
        raise FiniteCampaignError("max_pairs must be a nonnegative integer")
    parameters = prop1224_directed_parameters(
        q, bits=bits, log_terms=log_terms
    )
    first = max(1, _ceil(parameters.varpi.lower))
    last = _ceil(parameters.lambda_.upper) - 1
    count = max(0, last - first + 1)
    if count > max_pairs:
        raise FiniteCampaignError(
            f"directed conservative window has {count} pairs, exceeding "
            f"the bounded-sample guard {max_pairs}"
        )
    ks = tuple(range(first, last + 1)) if count else ()
    exact_g = ramare_g_prefixes(q, ks)
    margins = {
        k: _prop1224_margin_interval_from_exact_g(
            parameters, k, exact_g[k]
        ).lower
        for k in ks
    }
    window = create_prop1224_window(
        q=q,
        varpi_lower=parameters.varpi.lower,
        varpi_upper=parameters.varpi.upper,
        lambda_lower=parameters.lambda_.lower,
        lambda_upper=parameters.lambda_.upper,
        margin_lower=margins,
    )
    verify_prop1224_window(window)
    return Prop1224DirectedSample(parameters=parameters, window=window)


def verify_directed_prop1224_sample(sample: Prop1224DirectedSample) -> int:
    """Replay every enclosure and require byte-level dataclass equality."""

    if not isinstance(sample, Prop1224DirectedSample):
        raise FiniteCampaignError("directed sample has the wrong type")
    if (
        not sample.endpoint_enclosures_recomputed
        or not sample.margin_enclosures_recomputed
        or sample.native_float_used_in_decisions
        or sample.full_source_campaign
        or sample.lean_realization_proved
    ):
        raise FiniteCampaignError("directed sample has invalid assurance flags")
    rebuilt = create_directed_prop1224_sample(
        sample.parameters.q,
        bits=sample.parameters.bits,
        log_terms=sample.parameters.log_terms,
        max_pairs=len(sample.window.pairs),
    )
    if rebuilt != sample:
        raise FiniteCampaignError("directed Proposition 12.2.4 replay differs")
    return len(sample.window.pairs)


@dataclass(frozen=True)
class DirectedProp1224ChunkVerification:
    """Bounded directed replay layered over the generic hash-chain row."""

    first_q: int
    next_q: int
    q_rows: int
    pairs: int
    record_hash: str
    precision_bits: int
    log_series_terms: int
    structural_hash_and_scheduler_verified: bool = True
    endpoint_enclosures_recomputed: bool = True
    margin_enclosures_recomputed: bool = True
    exact_gq_recomputed: bool = True
    full_source_campaign: bool = False
    lean_realization_proved: bool = False
    lean_atom_discharged: bool = False


def create_directed_prop1224_chunk(
    qs: tuple[int, ...],
    *,
    bits: int = DEFAULT_BITS,
    log_terms: int = DEFAULT_LOG_TERMS,
    max_pairs_per_q: int = MAX_SAMPLE_PAIRS,
    previous_hash: str,
) -> Prop1224Chunk:
    """Create one existing-format hash chunk from fully directed bounded rows."""

    if not isinstance(qs, tuple) or not qs:
        raise FiniteCampaignError("directed chunk q values must be a nonempty tuple")
    if len(qs) > MAX_DIRECTED_CHUNK_Q_ROWS:
        raise FiniteCampaignError("directed chunk exceeds the bounded q-row guard")
    expected_q = qs[0]
    windows: list[Prop1224Window] = []
    for index, q in enumerate(qs):
        if q != expected_q:
            raise FiniteCampaignError(
                f"directed chunk q row {index} breaks exact scheduler order"
            )
        sample = create_directed_prop1224_sample(
            q,
            bits=bits,
            log_terms=log_terms,
            max_pairs=max_pairs_per_q,
        )
        windows.append(sample.window)
        expected_q = prop1224_next_q(q)
    return create_prop1224_chunk(tuple(windows), previous_hash=previous_hash)


def verify_directed_prop1224_chunk(
    chunk: Prop1224Chunk,
    *,
    bits: int = DEFAULT_BITS,
    log_terms: int = DEFAULT_LOG_TERMS,
    max_pairs_per_q: int = MAX_SAMPLE_PAIRS,
) -> DirectedProp1224ChunkVerification:
    """Replay endpoint and margin semantics for every row in one hash chunk."""

    q_rows, pairs = verify_prop1224_chunk(chunk)
    if q_rows > MAX_DIRECTED_CHUNK_Q_ROWS:
        raise FiniteCampaignError("directed chunk exceeds the bounded q-row guard")
    for index, window in enumerate(chunk.windows):
        rebuilt = create_directed_prop1224_sample(
            window.q,
            bits=bits,
            log_terms=log_terms,
            max_pairs=max_pairs_per_q,
        )
        if rebuilt.window != window:
            raise FiniteCampaignError(
                f"directed Proposition 12.2.4 chunk row {index} differs on replay"
            )
    return DirectedProp1224ChunkVerification(
        first_q=chunk.first_q,
        next_q=chunk.next_q,
        q_rows=q_rows,
        pairs=pairs,
        record_hash=chunk.record_hash,
        precision_bits=bits,
        log_series_terms=log_terms,
    )
