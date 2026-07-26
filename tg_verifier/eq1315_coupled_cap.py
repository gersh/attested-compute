# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed prototype for the corrected Chapter-14 equation (13.15) cap.

The Lean boundary mirrored here is
``PaperEq1315DirectEndpointAwareLowerBandCoupledCap``.  This module does not
claim to realize that boundary yet.  It implements the finite, outward-rounded
part of the proposed certificate and deliberately refuses production
acceptance until a separately reviewed infinite-tail witness is implemented.

The live Dirichlet guard has a particularly useful exact normalization.  Put

``u = log y``, ``v = log q`` and
``t = 3 |delta| q / (4 y^(1/3))``.

Then the guard in Lean is exactly ``0 <= t <= 1`` and the old/fresh selector
is ``t * w^(2/3) <= 1``.  Keeping ``u``, ``v`` and ``t`` in the same cell
preserves the correlation that was lost in several earlier headline bounds.
Integer q blocks are split by parity and carry a freshly recomputed exact
maximum of ``q / phi(q)``.

Finite ``w`` panels are evaluated with the rational directed arithmetic used
by :mod:`tg_verifier.prop1224_directed`.  Its logarithm and exponential use
exact atanh/Taylor remainder bounds and correspond to the proved elementary
primitives in ``SparkInterval/Certified/Exp.lean``.  A panel contribution is
an upper Darboux bound, not a midpoint quadrature.

Two boundaries remain explicit:

* the odd-q fixed-piece expression is the theorem-level upper model used by
  the Chapter-14 audit.  A Lean realization theorem connecting that model to
  ``lowQPiecesTotal413Corrected`` is still required;
* the fresh envelope has a remote logarithmic singularity.  A finite cutoff
  cannot simply discard the Gaussian tail.  ``verify_production_certificate``
  therefore rejects every current certificate because no supported
  ``TailWitness`` schema exists.

Consequently a successful call to ``verify_truncated_certificate`` proves only
the displayed bounded-w interval statement.  It can never be confused with a
successful production result.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
import math
from typing import Iterable, Literal, NoReturn

from tg_verifier.prop1224_directed import (
    RationalInterval,
    _add,
    _div,
    _max_interval,
    _mul,
    _outward,
    _pow_nat,
    _sub,
    exp_interval,
    log_interval,
    rpow_interval,
)


class Eq1315CertificateError(RuntimeError):
    """A cell, arithmetic enclosure, or claimed result failed closed."""


def _fail(message: str) -> NoReturn:
    raise Eq1315CertificateError(message)


N_LOWER = 10**27
N_UPPER = 8_875_694_145_621_773_516_800_000_000_000
R0 = 150_000

PI_INTERVAL = RationalInterval(
    Fraction(314_159_265_358_979_323_846, 10**20),
    Fraction(314_159_265_358_979_323_847, 10**20),
)

Parity = Literal["even", "odd"]
Branch = Literal["q_le_r1", "q_gt_r1", "split"]


@dataclass(frozen=True, slots=True)
class EvalConfig:
    """Directed rational precision and elementary-series length."""

    bits: int = 144
    terms: int = 48

    def validate(self) -> None:
        if isinstance(self.bits, bool) or not isinstance(self.bits, int):
            _fail("bits must be an integer")
        # Values near y=10^29 are divided after normalization.  An absolute
        # dyadic grid below 2^-128 can round their reciprocals to an interval
        # far too wide to be useful (while remaining sound).
        if not 128 <= self.bits <= 512:
            _fail("bits must lie in [128, 512]")
        if isinstance(self.terms, bool) or not isinstance(self.terms, int):
            _fail("terms must be an integer")
        if not 16 <= self.terms <= 512:
            _fail("terms must lie in [16, 512]")


@dataclass(frozen=True, slots=True)
class CellBox:
    """One outward rectangular cell in ``(u, v, t)`` plus its integer roster."""

    u: RationalInterval
    v: RationalInterval
    t: RationalInterval
    q_lower: int
    q_upper: int
    parity: Parity
    branch: Branch


@dataclass(frozen=True, slots=True)
class WPanel:
    """One closed panel; endpoint overlap has measure zero."""

    lower: Fraction
    upper: Fraction


@dataclass(frozen=True, slots=True)
class TruncatedCellCertificate:
    """Self-contained finite-panel claim.

    ``tail_witness`` must stay ``None`` in the prototype.  It is present in
    the format so a later version can add an explicitly versioned checker
    without weakening or overloading the finite statement.
    """

    schema: str
    config: EvalConfig
    box: CellBox
    panels: tuple[WPanel, ...]
    totient_ratio_upper: Fraction
    claimed_integral_upper: Fraction
    claimed_target_lower: Fraction
    claimed_selector_crossing_panels: int
    tail_witness: None = None


@dataclass(frozen=True, slots=True)
class TruncatedVerification:
    """Recomputed bounded-w result."""

    integral_upper: Fraction
    target_lower: Fraction
    selector_crossing_panels: int
    bounded_w_inequality_holds: bool
    branch: Branch
    q_count: int
    panel_count: int


SCHEMA = "sparkinterval.tg.eq1315-coupled-cap.truncated-cell.v1"
SOURCE_MODEL = "eq1315-direct-piece-theorem-upper-model-v1"
SUPPORTED_TAIL_WITNESS_SCHEMAS: tuple[str, ...] = ()


def _point(value: int | Fraction) -> RationalInterval:
    return RationalInterval.exact(Fraction(value))


def _interval_min(
    left: RationalInterval, right: RationalInterval
) -> RationalInterval:
    return RationalInterval(
        min(left.lower, right.lower),
        min(left.upper, right.upper),
    )


def _hull(*values: RationalInterval) -> RationalInterval:
    if not values:
        _fail("interval hull needs at least one value")
    return RationalInterval(
        min(value.lower for value in values),
        max(value.upper for value in values),
    )


def _scale(
    value: RationalInterval, scalar: int | Fraction, config: EvalConfig
) -> RationalInterval:
    return _mul(value, _point(scalar), config.bits)


def _square_root(value: RationalInterval, config: EvalConfig) -> RationalInterval:
    if value.lower <= 0:
        _fail("square-root interval must be strictly positive")
    return rpow_interval(
        value,
        _point(Fraction(1, 2)),
        bits=config.bits,
        terms=config.terms,
    )


def _rpow(
    value: RationalInterval, exponent: Fraction, config: EvalConfig
) -> RationalInterval:
    if value.lower <= 0:
        _fail("real-power base interval must be strictly positive")
    return rpow_interval(
        value,
        _point(exponent),
        bits=config.bits,
        terms=config.terms,
    )


def _log(value: RationalInterval, config: EvalConfig) -> RationalInterval:
    return log_interval(value, bits=config.bits, terms=config.terms)


def _exp(value: RationalInterval, config: EvalConfig) -> RationalInterval:
    return exp_interval(value, bits=config.bits, terms=config.terms)


def _log_plus(value: RationalInterval, config: EvalConfig) -> RationalInterval:
    return _max_interval(_point(0), _log(value, config))


def _damp(
    constant: Fraction, displacement: RationalInterval, config: EvalConfig
) -> RationalInterval:
    """Range of ``min(1, constant / d^2)`` for ``0 <= d``."""

    if displacement.lower < 0:
        _fail("displacement interval must be nonnegative")
    if displacement.upper == 0:
        return _point(1)
    lower = min(
        Fraction(1),
        constant / (displacement.upper * displacement.upper),
    )
    if displacement.lower == 0:
        upper = Fraction(1)
    else:
        upper = min(
            Fraction(1),
            constant / (displacement.lower * displacement.lower),
        )
    return _outward(RationalInterval(lower, upper), config.bits)


def _validate_integer(value: object, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(f"{label} must be an integer at least {minimum}")
    return value


def _prime_roster(limit: int) -> tuple[int, ...]:
    if limit < 2:
        return ()
    sieve = bytearray(b"\x01") * (limit + 1)
    sieve[0:2] = b"\x00\x00"
    for prime in range(2, math.isqrt(limit) + 1):
        if sieve[prime]:
            start = prime * prime
            sieve[start : limit + 1 : prime] = b"\x00" * (
                (limit - start) // prime + 1
            )
    return tuple(index for index, flag in enumerate(sieve) if flag)


def _totient_values(lower: int, upper: int) -> list[int]:
    """Exact segmented Euler-phi values on one bounded block."""

    _validate_integer(lower, "q lower", 1)
    _validate_integer(upper, "q upper", lower)
    if upper - lower + 1 > 1_000_000:
        _fail("one certificate q block may contain at most 1,000,000 integers")
    values = list(range(lower, upper + 1))
    remainders = values.copy()
    phis = values.copy()
    for prime in _prime_roster(math.isqrt(upper)):
        first = ((lower + prime - 1) // prime) * prime
        for value in range(first, upper + 1, prime):
            index = value - lower
            if remainders[index] % prime:
                continue
            phis[index] -= phis[index] // prime
            while remainders[index] % prime == 0:
                remainders[index] //= prime
    for index, remainder in enumerate(remainders):
        if remainder > 1:
            phis[index] -= phis[index] // remainder
    return phis


@lru_cache(maxsize=8_192)
def _exact_totient_ratio_envelopes(
    q_lower: int, q_upper: int
) -> tuple[tuple[Fraction | None, int], tuple[Fraction | None, int]]:
    """Compute both parity envelopes in one exact segmented-phi pass."""

    phis = _totient_values(q_lower, q_upper)
    maxima: list[Fraction | None] = [None, None]
    counts = [0, 0]
    for offset, phi in enumerate(phis):
        q = q_lower + offset
        parity_index = q % 2
        ratio = Fraction(q, phi)
        current = maxima[parity_index]
        maxima[parity_index] = ratio if current is None else max(current, ratio)
        counts[parity_index] += 1
    return (
        (maxima[0], counts[0]),
        (maxima[1], counts[1]),
    )


def exact_totient_ratio_upper(
    q_lower: int, q_upper: int, parity: Parity
) -> tuple[Fraction, int]:
    """Return ``max q/phi(q)`` and the number of selected q values."""

    if parity not in ("even", "odd"):
        _fail("parity must be 'even' or 'odd'")
    wanted = 0 if parity == "even" else 1
    ratio, count = _exact_totient_ratio_envelopes(q_lower, q_upper)[wanted]
    if ratio is None:
        _fail("q block contains no integer of the declared parity")
    return ratio, count


def _pi_half_mass(config: EvalConfig) -> RationalInterval:
    return _square_root(_scale(PI_INTERVAL, Fraction(1, 2), config), config)


def _chapter14_y_for_n(n: int, config: EvalConfig) -> RationalInterval:
    """Outward enclosure of ``n / (98 + c1)``."""

    n = _validate_integer(n, "n", 1)
    sqrt_two_pi = _square_root(_scale(PI_INTERVAL, 2, config), config)
    c1 = _div(_point(Fraction(9, 4)), sqrt_two_pi, config.bits)
    denominator = _add(_point(98), c1, config.bits)
    return _div(_point(n), denominator, config.bits)


@lru_cache(maxsize=32)
def global_u_domain(config: EvalConfig = EvalConfig()) -> RationalInterval:
    """Continuous u-domain covering every live integer n."""

    config.validate()
    low = _log(_chapter14_y_for_n(N_LOWER, config), config).lower
    high = _log(_chapter14_y_for_n(N_UPPER, config), config).upper
    return RationalInterval(low, high)


def _r1_from_u(u: RationalInterval, config: EvalConfig) -> RationalInterval:
    return _scale(_exp(_scale(u, Fraction(4, 15), config), config), Fraction(3, 8), config)


def _q_limit_from_u(u: RationalInterval, config: EvalConfig) -> RationalInterval:
    y = _exp(u, config)
    k = _scale(u, Fraction(1, 2), config)
    return _scale(_rpow(_div(y, k, config.bits), Fraction(1, 3), config), Fraction(1, 6), config)


def global_q_upper(config: EvalConfig = EvalConfig()) -> int:
    """Safe integer q ceiling for the full lower-band campaign."""

    domain = global_u_domain(config)
    q_upper = _q_limit_from_u(_point(domain.upper), config).upper
    return -((-q_upper.numerator) // q_upper.denominator)


def _expected_v(
    q_lower: int, q_upper: int, config: EvalConfig
) -> RationalInterval:
    return _log(
        RationalInterval(Fraction(q_lower), Fraction(q_upper)),
        config,
    )


def classify_branch(
    u: RationalInterval, q_lower: int, q_upper: int, config: EvalConfig
) -> Branch:
    """Classify the exact piecewise ``q <= r1`` seam for a rectangle."""

    r1 = _r1_from_u(u, config)
    if Fraction(q_upper) <= r1.lower:
        return "q_le_r1"
    if Fraction(q_lower) > r1.upper:
        return "q_gt_r1"
    return "split"


def make_cell_box(
    *,
    u: RationalInterval,
    t: RationalInterval,
    q_lower: int,
    q_upper: int,
    parity: Parity,
    config: EvalConfig = EvalConfig(),
) -> CellBox:
    """Construct a box with a derived, checked v enclosure and branch tag."""

    config.validate()
    return CellBox(
        u=u,
        v=_expected_v(q_lower, q_upper, config),
        t=t,
        q_lower=q_lower,
        q_upper=q_upper,
        parity=parity,
        branch=classify_branch(u, q_lower, q_upper, config),
    )


def _validate_box(box: CellBox, config: EvalConfig) -> tuple[Fraction, int]:
    if not isinstance(box, CellBox):
        _fail("box must be a CellBox")
    if not isinstance(box.u, RationalInterval):
        _fail("u must be a RationalInterval")
    if not isinstance(box.v, RationalInterval):
        _fail("v must be a RationalInterval")
    if not isinstance(box.t, RationalInterval):
        _fail("t must be a RationalInterval")
    if box.parity not in ("even", "odd"):
        _fail("invalid parity")
    q_lower = _validate_integer(box.q_lower, "q lower", R0 + 1)
    q_upper = _validate_integer(box.q_upper, "q upper", q_lower)
    if box.u.lower > box.u.upper or box.v.lower > box.v.upper:
        _fail("reversed u or v cell")
    if box.t.lower < 0 or box.t.upper > 1:
        _fail("the exact delta guard requires t in [0, 1]")
    domain = global_u_domain(config)
    if box.u.lower < domain.lower or box.u.upper > domain.upper:
        _fail("u cell is outside the lower-band n domain")
    expected_v = _expected_v(q_lower, q_upper, config)
    if box.v.lower > expected_v.lower or box.v.upper < expected_v.upper:
        _fail("v cell does not enclose log(q) for the full integer block")
    expected_branch = classify_branch(box.u, q_lower, q_upper, config)
    if box.branch != expected_branch:
        _fail("piecewise q/r1 branch tag is stale or incorrect")
    q_limit = _q_limit_from_u(box.u, config)
    if Fraction(q_upper) > q_limit.lower:
        _fail(
            "q block is not wholly inside the exact q upper guard; "
            "split the u/q cell"
        )
    return exact_totient_ratio_upper(q_lower, q_upper, box.parity)


def _z_factor(radius: RationalInterval, config: EvalConfig) -> RationalInterval:
    loglog = _log(_log(radius, config), config)
    # A theorem-backed Euler-gamma interval would be preferable in the final
    # Lean bridge.  exp(gamma) only occurs positively here, so the existing
    # repository bounds are sufficient for this upper/lower evaluator.
    gamma = RationalInterval(
        Fraction(577_215_657, 10**9),
        Fraction(5_772_162, 10**7),
    )
    exp_gamma = _exp(gamma, config)
    return _add(
        _mul(exp_gamma, loglog, config.bits),
        _div(_point(Fraction(250_637, 100_000)), loglog, config.bits),
        config.bits,
    )


def _r_factor(
    x: RationalInterval, tau: RationalInterval, config: EvalConfig
) -> RationalInterval:
    numerator = _log(_scale(tau, 4, config), config)
    denominator_argument = _div(
        _scale(_rpow(x, Fraction(1, 3), config), 9, config),
        _scale(tau, Fraction(501, 250), config),
        config.bits,
    )
    denominator = _scale(_log(denominator_argument, config), 2, config)
    quotient = _div(numerator, denominator, config.bits)
    return _add(
        _scale(_log(_add(_point(1), quotient, config.bits), config), Fraction(217, 800), config),
        _point(Fraction(8_283, 20_000)),
        config.bits,
    )


def _l_factor(tau: RationalInterval, config: EvalConfig) -> RationalInterval:
    log_tau = _log(tau, config)
    first = _mul(
        _z_factor(_scale(tau, Fraction(1, 2), config), config),
        _add(
            _scale(log_tau, Fraction(13, 4), config),
            _point(Fraction(391, 50)),
            config.bits,
        ),
        config.bits,
    )
    return _add(
        first,
        _add(
            _scale(log_tau, Fraction(683, 50), config),
            _point(Fraction(751, 20)),
            config.bits,
        ),
        config.bits,
    )


def _h_corrected(x: RationalInterval, config: EvalConfig) -> RationalInterval:
    log_x = _log(x, config)
    first = _mul(
        _scale(_rpow(x, Fraction(-1, 6), config), Fraction(2727, 10_000), config),
        _rpow(log_x, Fraction(3, 2), config),
        config.bits,
    )
    second = _mul(
        _scale(_rpow(x, Fraction(-1, 3), config), Fraction(4875, 4), config),
        log_x,
        config.bits,
    )
    return _add(first, second, config.bits)


def _g_unweighted_corrected(
    x: RationalInterval, rho: RationalInterval, config: EvalConfig
) -> RationalInterval:
    two_rho = _scale(rho, 2, config)
    headline = _add(
        _mul(
            _r_factor(x, two_rho, config),
            _log(two_rho, config),
            config.bits,
        ),
        _point(Fraction(811, 1000)),
        config.bits,
    )
    first = _div(
        _add(
            _mul(headline, _square_root(_z_factor(rho, config), config), config.bits),
            _point(Fraction(5, 2)),
            config.bits,
        ),
        _square_root(two_rho, config),
        config.bits,
    )
    return _add(
        _add(first, _div(_l_factor(two_rho, config), rho, config.bits), config.bits),
        _scale(_rpow(x, Fraction(-1, 6), config), Fraction(16, 5), config),
        config.bits,
    )


def _g_target_lower(
    y: RationalInterval, k: RationalInterval, radius: RationalInterval, config: EvalConfig
) -> RationalInterval:
    """A theorem-backed lower model for ``paperGPhiCorrected``.

    ``paperRPhi >= paperR y`` on the live domain, so dropping the positive
    interpolation correction gives a safe lower target and avoids putting a
    nested Cphi quadrature inside every cell.
    """

    two_r = _scale(radius, 2, config)
    headline = _add(
        _mul(_r_factor(y, two_r, config), _log(two_r, config), config.bits),
        _point(Fraction(811, 1000)),
        config.bits,
    )
    first = _div(
        _add(
            _mul(headline, _square_root(_z_factor(radius, config), config), config.bits),
            _point(Fraction(5, 2)),
            config.bits,
        ),
        _square_root(two_r, config),
        config.bits,
    )
    tail = _mul(
        _scale(_rpow(k, Fraction(1, 6), config), Fraction(84, 25), config),
        _rpow(y, Fraction(-1, 6), config),
        config.bits,
    )
    return _add(
        _add(first, _div(_l_factor(two_r, config), radius, config.bits), config.bits),
        tail,
        config.bits,
    )


def _section5_c(
    x: RationalInterval, tau: RationalInterval, config: EvalConfig
) -> RationalInterval:
    numerator = _log(_scale(tau, 4, config), config)
    denominator_argument = _div(
        _scale(_rpow(x, Fraction(1, 3), config), 9, config),
        _scale(tau, Fraction(501, 250), config),
        config.bits,
    )
    denominator = _scale(_log(denominator_argument, config), 2, config)
    return _log(
        _add(_point(1), _div(numerator, denominator, config.bits), config.bits),
        config,
    )


def _delta_zero_or_positive_damp(
    constant: Fraction, d: RationalInterval, config: EvalConfig
) -> RationalInterval:
    return _damp(constant, d, config)


def _p1_upper(
    x: RationalInterval,
    d: RationalInterval,
    q: RationalInterval,
    ratio: RationalInterval,
    parity: Parity,
    config: EvalConfig,
) -> RationalInterval:
    d0 = _max_interval(_point(2), _scale(d, Fraction(1, 4), config))
    x23 = _rpow(x, Fraction(2, 3), config)
    common = _add(
        _mul(
            _div(x23, _square_root(_mul(q, d0, config.bits), config), config.bits),
            _sub(
                _scale(_log(x, config), Fraction(13_569, 20_000), config),
                _point(Fraction(60_409, 50_000)),
                config.bits,
            ),
            config.bits,
        ),
        _scale(x23, Fraction(379, 1000), config),
        config.bits,
    )
    if parity == "even":
        return common
    rho = _mul(_max_interval(_point(1), _scale(d, Fraction(1, 8), config)), q, config.bits)
    resonant = _add(
        _mul(
            _mul(
                _mul(
                    _div(x, _scale(q, 2, config), config.bits),
                    _delta_zero_or_positive_damp(Fraction(1597, 500), d, config),
                    config.bits,
                ),
                ratio,
                config.bits,
            ),
            _add(
                _scale(_log(_mul(d0, q, config.bits), config), Fraction(7, 2), config),
                _point(15),
                config.bits,
            ),
            config.bits,
        ),
        _scale(_div(x, rho, config.bits), Fraction(1, 1_000_000), config),
        config.bits,
    )
    return _add(resonant, common, config.bits)


def _low_si2_corrected(
    x: RationalInterval,
    d: RationalInterval,
    q: RationalInterval,
    phi: RationalInterval,
    config: EvalConfig,
) -> RationalInterval:
    """Directed form of the corrected Section-5.2 P2 upper surface."""

    d0 = _max_interval(_point(2), _scale(d, Fraction(1, 4), config))
    log_x = _log(x, config)
    log_q = _log(q, config)
    log_two = _log(_point(2), config)
    l1 = _scale(log_two, 8, config)
    sqrt_qd0 = _square_root(_mul(q, d0, config.bits), config)
    x13 = _rpow(x, Fraction(1, 3), config)
    beta = _div(l1, _scale(_mul(sqrt_qd0, x13, config.bits), 9, config), config.bits)
    vr = _scale(x13, Fraction(9, 2), config)
    lam1 = _scale(vr, Fraction(2501, 2500), config)
    lamv = _scale(_pow_nat(vr, 2, config.bits), Fraction(1251, 2500), config)
    lgr = _add(
        lam1,
        _mul(
            q,
            _add(
                _scale(log_x, Fraction(1, 3), config),
                _log(_point(Fraction(9, 2)), config),
                config.bits,
            ),
            config.bits,
        ),
        config.bits,
    )
    t2b = _mul(
        _scale(beta, Fraction(3, 2), config),
        _mul(
            _div(x, q, config.bits),
            _mul(
                _log_plus(
                    _div(
                        _mul(
                            q,
                            _low_delta_threshold(config),
                            config.bits,
                        ),
                        sqrt_qd0,
                        config.bits,
                    ),
                    config,
                ),
                lgr,
                config.bits,
            ),
            config.bits,
        ),
        config.bits,
    )

    damp_p = _damp(Fraction(798_437, 250_000), d, config)
    min_left = _div(
        _add(
            _scale(log_q, Fraction(3, 2), config),
            _point(Fraction(314_107, 100_000)),
            config.bits,
        ),
        phi,
        config.bits,
    )
    min_right = _div(
        _add(
            _scale(log_x, Fraction(1, 3), config),
            _scale(_log(_point(Fraction(3, 4)), config), Fraction(1, 2), config),
            config.bits,
        ),
        q,
        config.bits,
    )
    base = _add(
        _scale(_div(x, sqrt_qd0, config.bits), Fraction(24_919, 10_000), config),
        _scale(_div(x, _mul(q, d0, config.bits), config.bits), Fraction(3461, 2000), config),
        config.bits,
    )
    base = _add(
        base,
        _mul(_mul(x, damp_p, config.bits), _interval_min(min_left, min_right), config.bits),
        config.bits,
    )
    base = _add(
        base,
        _scale(
            _div(x, _mul(_pow_nat(q, 2, config.bits), d0, config.bits), config.bits),
            Fraction(5_863, 20_000),
            config,
        ),
        config.bits,
    )
    base = _add(
        base,
        _mul(
            _add(_scale(log_x, Fraction(1, 2), config), _point(60), config.bits),
            _rpow(x, Fraction(2, 3), config),
            config.bits,
        ),
        config.bits,
    )
    base = _add(base, t2b, config.bits)

    threshold = _low_delta_threshold(config)
    if d.upper < threshold.lower:
        return base
    # On the conditional branch d is bounded away from zero by the exact
    # threshold.  Intersecting before division avoids evaluating a formula
    # outside the branch where it is used.
    conditional_d = RationalInterval(
        max(d.lower, threshold.lower),
        d.upper,
    )

    # Every live q is above 30,000, hence epsilon = 7/100.
    cc = Fraction(67_769, 10_000)
    ieps = Fraction(107, 7)
    sqrt_two = _square_root(_point(2), config)
    conditional = _mul(
        _mul(
            _add(
                _add(
                    _point(Fraction(103_883, 100_000)),
                    log_q,
                    config.bits,
                ),
                _log_plus(
                    _div(
                        _scale(_mul(conditional_d, q, config.bits), 3, config),
                        _mul(sqrt_two, sqrt_qd0, config.bits),
                        config.bits,
                    ),
                    config,
                ),
                config.bits,
            ),
            _point(cc),
            config.bits,
        ),
        _div(x, _mul(conditional_d, q, config.bits), config.bits),
        config.bits,
    )
    conditional = _add(
        conditional,
        _mul(
            _scale(_mul(beta, lgr, config.bits), cc / 2, config),
            _div(x, _mul(conditional_d, q, config.bits), config.bits),
            config.bits,
        ),
        config.bits,
    )
    xq_term = _mul(
        _scale(x13, 2, config),
        _mul(
            _add(
                _point(2),
                _scale(
                    _log_plus(
                        _div(
                            _mul(conditional_d, q, config.bits),
                            sqrt_qd0,
                            config.bits,
                        ),
                        config,
                    ),
                    ieps,
                    config,
                ),
                config.bits,
            ),
            _add(lam1, _mul(beta, lamv, config.bits), config.bits),
            config.bits,
        ),
        config.bits,
    )
    conditional = _add(conditional, xq_term, config.bits)
    if d.lower >= threshold.upper:
        return _add(base, conditional, config.bits)
    # The surface adds a nonnegative conditional term at the threshold.
    return _add(
        base,
        RationalInterval(Fraction(0), max(Fraction(0), conditional.upper)),
        config.bits,
    )


def _low_delta_threshold(config: EvalConfig) -> RationalInterval:
    # 5 sqrt(31.521) / (12 pi)
    return _div(
        _scale(_square_root(_point(Fraction(31_521, 1000)), config), 5, config),
        _scale(PI_INTERVAL, 12, config),
        config.bits,
    )


def _sii_413_corrected(
    x: RationalInterval,
    d: RationalInterval,
    q: RationalInterval,
    phi: RationalInterval,
    config: EvalConfig,
) -> RationalInterval:
    d0 = _max_interval(_point(2), _scale(d, Fraction(1, 4), config))

    def small() -> RationalInterval:
        tau = _scale(q, 2, config)
        a = _add(
            _mul(_section5_c(x, tau, config), _log(tau, config), config.bits),
            _scale(_log(_scale(q, 8, config), config), Fraction(1, 2), config),
            config.bits,
        )
        b = _add(
            _scale(_log(tau, config), Fraction(16_087, 50_000), config),
            _point(Fraction(70_223, 100_000)),
            config.bits,
        )
        lead = _mul(
            _div(x, _square_root(_scale(phi, 2, config), config), config.bits),
            _mul(_square_root(a, config), _square_root(b, config), config.bits),
            config.bits,
        )
        return _add(
            _add(
                lead,
                _scale(
                    _mul(
                        _square_root(_div(q, phi, config.bits), config),
                        _rpow(x, Fraction(3, 4), config),
                        config.bits,
                    ),
                    Fraction(4101, 250),
                    config,
                ),
                config.bits,
            ),
            _scale(_rpow(x, Fraction(5, 6), config), Fraction(184_251, 100_000), config),
            config.bits,
        )

    def large() -> RationalInterval:
        tau = _mul(d0, q, config.bits)
        a = _add(
            _mul(
                _section5_c(x, tau, config),
                _add(_log(tau, config), _point(Fraction(1, 500)), config.bits),
                config.bits,
            ),
            _scale(_log(_scale(tau, 4, config), config), Fraction(1, 2), config),
            config.bits,
        )
        b = _add(
            _scale(_log(tau, config), Fraction(16_087, 50_000), config),
            _point(Fraction(70_223, 100_000)),
            config.bits,
        )
        lead = _mul(
            _div(x, _square_root(_mul(d0, phi, config.bits), config), config.bits),
            _mul(_square_root(a, config), _square_root(b, config), config.bits),
            config.bits,
        )
        return _add(
            _add(
                lead,
                _scale(
                    _mul(
                        _square_root(_div(q, phi, config.bits), config),
                        _rpow(x, Fraction(4, 5), config),
                        config.bits,
                    ),
                    Fraction(84_019, 50_000),
                    config,
                ),
                config.bits,
            ),
            _scale(_rpow(x, Fraction(5, 6), config), Fraction(184_251, 100_000), config),
            config.bits,
        )

    if d.upper < 8:
        return small()
    if d.lower >= 8:
        return large()
    return _hull(small(), large())


def _fixed_piece_upper(
    x: RationalInterval,
    d: RationalInterval,
    q: RationalInterval,
    ratio: RationalInterval,
    parity: Parity,
    config: EvalConfig,
) -> RationalInterval:
    # phi = q / (q/phi).  The ratio interval preserves the useful q scaling
    # across a block while remaining an outward relaxation.
    phi = _div(q, ratio, config.bits)
    total = _add(
        _add(
            _p1_upper(x, d, q, ratio, parity, config),
            _low_si2_corrected(x, d, q, phi, config),
            config.bits,
        ),
        _sii_413_corrected(x, d, q, phi, config),
        config.bits,
    )
    return _div(total, x, config.bits)


def _high_repair(
    k: RationalInterval,
    y: RationalInterval,
    w: RationalInterval,
    config: EvalConfig,
) -> RationalInterval:
    scale = _scale(_rpow(_div(y, k, config.bits), Fraction(1, 3), config), Fraction(1, 6), config)
    wy = _mul(w, y, config.bits)
    u = _log(_scale(_rpow(wy, Fraction(1, 3), config), Fraction(1, 3), config), config)
    return _add(
        _mul(
            _scale(_div(_point(1), scale, config.bits), Fraction(201, 100), config),
            _log(wy, config),
            config.bits,
        ),
        _mul(
            _scale(
                _div(_point(1), _square_root(_scale(scale, 2, config), config), config.bits),
                Fraction(9, 125),
                config,
            ),
            _mul(u, _log(u, config), config.bits),
            config.bits,
        ),
        config.bits,
    )


def _fresh_piece_upper(
    y: RationalInterval,
    k: RationalInterval,
    w: RationalInterval,
    d: RationalInterval,
    q: RationalInterval,
    config: EvalConfig,
) -> RationalInterval:
    x = _mul(w, y, config.bits)
    rho = _mul(_max_interval(_point(1), _scale(d, Fraction(1, 8), config)), q, config.bits)
    base = _max_interval(
        _g_unweighted_corrected(x, rho, config),
        _h_corrected(_div(y, k, config.bits), config),
    )
    return _add(base, _high_repair(k, y, w, config), config.bits)


def _phi_weight(w: RationalInterval, config: EvalConfig) -> RationalInterval:
    w2 = _pow_nat(w, 2, config.bits)
    return _mul(
        w2,
        _exp(_scale(w2, Fraction(-1, 2), config), config),
        config.bits,
    )


def _cell_parameters(
    box: CellBox, ratio_upper: Fraction, config: EvalConfig
) -> tuple[
    RationalInterval,
    RationalInterval,
    RationalInterval,
    RationalInterval,
    RationalInterval,
]:
    y = _exp(box.u, config)
    k = _scale(box.u, Fraction(1, 2), config)
    q = RationalInterval(Fraction(box.q_lower), Fraction(box.q_upper))
    ratio = RationalInterval(Fraction(1), ratio_upper)
    # delta = (4/3) t exp(u/3-v), exactly in the normalized variables.
    delta = _scale(
        _mul(
            box.t,
            _exp(
                _sub(
                    _scale(box.u, Fraction(1, 3), config),
                    box.v,
                    config.bits,
                ),
                config,
            ),
            config.bits,
        ),
        Fraction(4, 3),
        config,
    )
    return y, k, q, ratio, delta


def _panel_integrand(
    box: CellBox,
    panel: WPanel,
    ratio_upper: Fraction,
    config: EvalConfig,
) -> tuple[RationalInterval, bool]:
    w = RationalInterval(panel.lower, panel.upper)
    y, k, q, ratio, delta = _cell_parameters(box, ratio_upper, config)
    x = _mul(w, y, config.bits)
    d = _mul(w, delta, config.bits)
    fixed = _fixed_piece_upper(x, d, q, ratio, box.parity, config)
    fresh = _fresh_piece_upper(y, k, w, d, q, config)
    selector = _mul(box.t, _rpow(w, Fraction(2, 3), config), config.bits)
    crossing = selector.lower <= 1 < selector.upper
    if selector.upper <= 1:
        chosen = fixed
    elif selector.lower > 1:
        chosen = fresh
    else:
        chosen = _hull(fixed, fresh)
    return _mul(chosen, _phi_weight(w, config), config.bits), crossing


def _target_lower(box: CellBox, config: EvalConfig) -> Fraction:
    y = _exp(box.u, config)
    k = _scale(box.u, Fraction(1, 2), config)
    q = RationalInterval(Fraction(box.q_lower), Fraction(box.q_upper))
    r1 = _r1_from_u(box.u, config)
    head = _g_target_lower(y, k, _point(R0), config)
    le_branch = _scale(
        _g_target_lower(y, k, q, config),
        Fraction(26, 25),
        config,
    )
    gt_branch = _scale(
        _g_target_lower(y, k, r1, config),
        Fraction(101, 100),
        config,
    )
    if box.branch == "q_le_r1":
        branch = le_branch
    elif box.branch == "q_gt_r1":
        branch = gt_branch
    else:
        # Exact piecewise semantics on a crossing rectangle: every point uses
        # one of these two arms.  Taking the hull is conservative and never
        # replaces the seam by an unrelated uniform headline.
        branch = _hull(le_branch, gt_branch)
    boundary = _interval_min(head, branch)
    return _mul(boundary, _pi_half_mass(config), config.bits).lower


def _validate_panels(
    panels: Iterable[WPanel],
    box: CellBox,
    config: EvalConfig,
) -> tuple[WPanel, ...]:
    result = tuple(panels)
    if not result:
        _fail("finite certificate must contain at least one w panel")
    natural_lower = Fraction(2, 1) / box.u.upper
    if result[0].lower != natural_lower:
        _fail("first panel must start at the conservative lower limit 2/u_hi")
    previous = natural_lower
    for index, panel in enumerate(result):
        if not isinstance(panel, WPanel):
            _fail(f"panel {index} is not a WPanel")
        if not isinstance(panel.lower, Fraction):
            _fail(f"panel {index} lower endpoint is not a Fraction")
        if not isinstance(panel.upper, Fraction):
            _fail(f"panel {index} upper endpoint is not a Fraction")
        if panel.lower != previous:
            _fail(f"panel {index} is not contiguous with its predecessor")
        if panel.lower <= 0 or panel.upper <= panel.lower:
            _fail(f"panel {index} is empty or nonpositive")
        if panel.upper > 32:
            _fail("prototype finite panels are capped at w=32")
        previous = panel.upper
    return result


def compute_truncated_bounds(
    box: CellBox,
    panels: Iterable[WPanel],
    *,
    config: EvalConfig = EvalConfig(),
) -> tuple[Fraction, Fraction, int, Fraction, int]:
    """Recompute the exact finite-panel upper and target lower bounds."""

    config.validate()
    ratio_upper, q_count = _validate_box(box, config)
    checked_panels = _validate_panels(panels, box, config)
    total = Fraction(0)
    crossing_count = 0
    for panel in checked_panels:
        integrand, crossing = _panel_integrand(
            box, panel, ratio_upper, config
        )
        if integrand.upper < 0:
            _fail("a supposedly nonnegative panel has a negative upper bound")
        total += (panel.upper - panel.lower) * max(Fraction(0), integrand.upper)
        crossing_count += int(crossing)
    total = _outward(RationalInterval(total, total), config.bits).upper
    target = _target_lower(box, config)
    return total, target, crossing_count, ratio_upper, q_count


def issue_truncated_certificate(
    box: CellBox,
    panels: Iterable[WPanel],
    *,
    config: EvalConfig = EvalConfig(),
) -> TruncatedCellCertificate:
    """Generate a bounded-w certificate; this is never a production result."""

    checked_panels = tuple(panels)
    total, target, crossing, ratio, _ = compute_truncated_bounds(
        box, checked_panels, config=config
    )
    return TruncatedCellCertificate(
        schema=SCHEMA,
        config=config,
        box=box,
        panels=checked_panels,
        totient_ratio_upper=ratio,
        claimed_integral_upper=total,
        claimed_target_lower=target,
        claimed_selector_crossing_panels=crossing,
    )


def verify_truncated_certificate(
    certificate: TruncatedCellCertificate,
) -> TruncatedVerification:
    """Fail-closed replay of every finite arithmetic and topology decision."""

    if not isinstance(certificate, TruncatedCellCertificate):
        _fail("certificate has the wrong Python type")
    if certificate.schema != SCHEMA:
        _fail("unknown truncated certificate schema")
    if not isinstance(certificate.config, EvalConfig):
        _fail("certificate config has the wrong Python type")
    for label, value in (
        ("totient ratio", certificate.totient_ratio_upper),
        ("integral upper", certificate.claimed_integral_upper),
        ("target lower", certificate.claimed_target_lower),
    ):
        if not isinstance(value, Fraction):
            _fail(f"claimed {label} is not a Fraction")
    if (
        isinstance(certificate.claimed_selector_crossing_panels, bool)
        or not isinstance(certificate.claimed_selector_crossing_panels, int)
    ):
        _fail("claimed selector-crossing count is not an integer")
    if certificate.tail_witness is not None:
        _fail("the v1 truncated schema does not accept a tail witness")
    total, target, crossing, ratio, q_count = compute_truncated_bounds(
        certificate.box,
        certificate.panels,
        config=certificate.config,
    )
    if certificate.totient_ratio_upper != ratio:
        _fail("claimed q/phi(q) envelope differs from exact replay")
    if certificate.claimed_integral_upper != total:
        _fail("claimed finite-panel integral differs from directed replay")
    if certificate.claimed_target_lower != target:
        _fail("claimed coupled-boundary lower bound differs from replay")
    if certificate.claimed_selector_crossing_panels != crossing:
        _fail("claimed selector-crossing count differs from replay")
    return TruncatedVerification(
        integral_upper=total,
        target_lower=target,
        selector_crossing_panels=crossing,
        bounded_w_inequality_holds=total <= target,
        branch=certificate.box.branch,
        q_count=q_count,
        panel_count=len(certificate.panels),
    )


def check_truncated_certificate(certificate: object) -> bool:
    try:
        result = verify_truncated_certificate(
            certificate  # type: ignore[arg-type]
        )
    except (
        Eq1315CertificateError,
        ArithmeticError,
        ValueError,
        TypeError,
        AttributeError,
    ):
        return False
    return result.bounded_w_inequality_holds


def verify_production_certificate(
    certificate: TruncatedCellCertificate,
) -> TruncatedVerification:
    """Refuse production closure until an infinite-tail checker exists."""

    result = verify_truncated_certificate(certificate)
    if not SUPPORTED_TAIL_WITNESS_SCHEMAS:
        _fail(
            "production closure is disabled: no reviewed infinite Gaussian-tail "
            "witness schema is implemented"
        )
    _fail("unreachable prototype tail-witness dispatch")


def check_production_certificate(certificate: object) -> bool:
    try:
        verify_production_certificate(certificate)  # type: ignore[arg-type]
    except (
        Eq1315CertificateError,
        ArithmeticError,
        ValueError,
        TypeError,
        AttributeError,
    ):
        return False
    return True


def geometric_panels(
    box: CellBox,
    *,
    stop: Fraction = Fraction(4),
    subdivisions: int = 2,
) -> tuple[WPanel, ...]:
    """Small deterministic panel roster for tests and bounded benchmarks."""

    subdivisions = _validate_integer(subdivisions, "subdivisions", 1)
    if stop <= 0 or stop > 32:
        _fail("stop must lie in (0, 32]")
    start = Fraction(2, 1) / box.u.upper
    anchors = [start]
    for candidate in (
        Fraction(1, 16),
        Fraction(1, 8),
        Fraction(1, 4),
        Fraction(1, 2),
        Fraction(1),
        Fraction(2),
        Fraction(4),
        Fraction(8),
        Fraction(12),
        Fraction(16),
        Fraction(24),
        Fraction(32),
    ):
        if start < candidate < stop:
            anchors.append(candidate)
    anchors.append(stop)
    result: list[WPanel] = []
    for left, right in zip(anchors, anchors[1:]):
        width = (right - left) / subdivisions
        for index in range(subdivisions):
            lo = left + index * width
            result.append(WPanel(lo, lo + width))
    return tuple(result)


def capability_report(config: EvalConfig = EvalConfig()) -> dict[str, object]:
    """Machine-readable disabled-stage status; contains no receipt or pin."""

    config.validate()
    return {
        "algorithm_id": "sparkinterval.ternary-goldbach.eq1315-coupled-cap.v1",
        "enabled": False,
        "registered_invocation": None,
        "lean_theorem": (
            "Math.Problems.TernaryGoldbach."
            "PaperEq1315DirectEndpointAwareLowerBandCoupledCap"
        ),
        "source_model": SOURCE_MODEL,
        "coordinate_system": {
            "u": "log(y)",
            "v": "log(q)",
            "t": "3*abs(delta)*q/(4*y^(1/3))",
        },
        "exact_guard": "q>150000; q<=((y/(log(y)/2))^(1/3))/6; 0<=t<=1",
        "boundary": "if q<=r1 then min(G(r0),1.04*G(q)) else min(G(r0),1.01*G(r1))",
        "parity_lanes": ["even", "odd"],
        "n_lower": N_LOWER,
        "n_upper": N_UPPER,
        "q_upper_safe": global_q_upper(config),
        "finite_panel_checker": True,
        "production_tail_checker": False,
        "source_upper_model_lean_realization": False,
        "full_artifact_present": False,
        "successful_receipt_present": False,
        "supported_tail_witness_schemas": list(SUPPORTED_TAIL_WITNESS_SCHEMAS),
    }


__all__ = [
    "Branch",
    "CellBox",
    "Eq1315CertificateError",
    "EvalConfig",
    "N_LOWER",
    "N_UPPER",
    "Parity",
    "R0",
    "SCHEMA",
    "TruncatedCellCertificate",
    "TruncatedVerification",
    "WPanel",
    "capability_report",
    "check_production_certificate",
    "check_truncated_certificate",
    "classify_branch",
    "compute_truncated_bounds",
    "exact_totient_ratio_upper",
    "geometric_panels",
    "global_q_upper",
    "global_u_domain",
    "issue_truncated_certificate",
    "make_cell_box",
    "verify_production_certificate",
    "verify_truncated_certificate",
]
