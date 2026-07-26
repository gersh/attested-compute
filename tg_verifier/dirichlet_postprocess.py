# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Rigorous post-character stages from Platt's Dirichlet-GRH computation.

The functions here are deliberately compositional.  Completed values consume
interval ``L(1/2+it,chi)`` and root-number rectangles emitted by an upstream
all-character stage.  Whittaker--Shannon reconstruction consumes completed
real intervals.  The paired Turing stage consumes certified zero brackets in
one window.  Pinned Arb evaluates all transcendental expressions outward.

This is the executable arithmetic after the all-character transform, not a
claim that the transform inputs, Lemma 6.7's unspecified "large enough t0"
condition, or a full source campaign have been certified.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from pathlib import Path
from typing import Any, NoReturn, Sequence

from tg_verifier.dirichlet_campaign import primitive_character_descriptor


SOURCE_URL = "https://arxiv.org/abs/1305.3087v1"
RELEASED_CODE_COMMIT = "42b21426718e542daa2b006dc05ea2d7f26426e6"
RELEASED_TURING_CODE_URL = (
    "https://github.com/djplatt/code/blob/"
    f"{RELEASED_CODE_COMMIT}/l-func-hi/find_zeros.cpp"
)
COMPLETED_SCHEMA = "sparkinterval.tg.dirichlet_completed_value.request.v1"
UPSAMPLE_SCHEMA = "sparkinterval.tg.dirichlet_ws_upsample.request.v1"
TURING_SCHEMA = "sparkinterval.tg.dirichlet_paired_turing.request.v2"
RESULT_SCHEMA = "sparkinterval.tg.dirichlet_postprocess.result.v2"
ALGORITHM_ID = "platt-dirichlet-completed-ws-turing-arb-v2"


class DirichletPostprocessError(RuntimeError):
    """A post-character interval or source precondition failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletPostprocessError(message)


try:
    import flint
    from flint import acb, arb, ctx, dirichlet_char
except ImportError as error:  # pragma: no cover - environment-dependent
    flint = acb = arb = ctx = dirichlet_char = None
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


def fraction_json(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _fraction(name: str, value: object) -> Fraction:
    if not isinstance(value, dict) or set(value) != {"numerator", "denominator"}:
        _fail(f"{name} must be a canonical rational")
    numerator = value["numerator"]
    denominator = value["denominator"]
    if (
        isinstance(numerator, bool)
        or not isinstance(numerator, int)
        or isinstance(denominator, bool)
        or not isinstance(denominator, int)
        or denominator <= 0
    ):
        _fail(f"{name} has invalid rational components")
    answer = Fraction(numerator, denominator)
    if (answer.numerator, answer.denominator) != (numerator, denominator):
        _fail(f"{name} is not in lowest terms")
    return answer


def _arb_fraction(value: Fraction):
    return arb(f"{value.numerator}/{value.denominator}")


def _dyadic(value: Any) -> Fraction:
    mantissa, exponent = value.mid().man_exp()
    exponent = int(exponent)
    mantissa = int(mantissa)
    if exponent >= 0:
        return Fraction(mantissa << exponent)
    return Fraction(mantissa, 1 << (-exponent))


def arb_interval(value: Any) -> dict[str, dict[str, int]]:
    """Return an exact rational enclosure of an Arb ball."""

    midpoint = _dyadic(value.mid())
    radius = abs(_dyadic(value.rad()))
    if radius == 0 and not value.is_exact():
        radius = Fraction(1, 1 << max(16, ctx.prec))
    while True:
        candidate = arb(
            f"{midpoint.numerator}/{midpoint.denominator}",
            f"{radius.numerator}/{radius.denominator}",
        )
        if candidate.contains(value):
            return {
                "lower": fraction_json(midpoint - radius),
                "upper": fraction_json(midpoint + radius),
            }
        radius = max(Fraction(1, 1 << max(16, ctx.prec)), 2 * radius)


def interval_arb(name: str, value: object):
    if not isinstance(value, dict) or set(value) != {"lower", "upper"}:
        _fail(f"{name} must contain lower and upper rationals")
    lower = _fraction(f"{name}.lower", value["lower"])
    upper = _fraction(f"{name}.upper", value["upper"])
    if lower > upper:
        _fail(f"{name} is reversed")
    midpoint = (lower + upper) / 2
    radius = (upper - lower) / 2
    return arb(
        f"{midpoint.numerator}/{midpoint.denominator}",
        f"{radius.numerator}/{radius.denominator}",
    )


def rectangle_acb(name: str, value: object):
    if not isinstance(value, dict) or set(value) != {"real", "imag"}:
        _fail(f"{name} must be a complex rectangle")
    return acb(
        interval_arb(f"{name}.real", value["real"]),
        interval_arb(f"{name}.imag", value["imag"]),
    )


def rectangle_json(value: Any) -> dict[str, Any]:
    return {"real": arb_interval(value.real), "imag": arb_interval(value.imag)}


def completed_value(request: dict[str, Any], *, precision: int = 192) -> dict[str, Any]:
    """Reconstruct Platt's Section 1 real completed value from an L rectangle."""

    require_flint()
    if request.get("kind") != COMPLETED_SCHEMA:
        _fail("unsupported completed-value request")
    required_truths = (
        "q_minus_s_factor_applied",
        "finite_dirichlet_term_addback_applied",
        "primitive_frequency_conrey_identity_checked",
        "root_number_certified_from_character",
    )
    for name in required_truths:
        if request.get(name) is not True:
            _fail(f"completed-value upstream obligation is false: {name}")
    q = request.get("q")
    conrey = request.get("conrey_number")
    ordinal = request.get("primitive_character_ordinal")
    parity = request.get("parity")
    if (
        isinstance(q, bool)
        or not isinstance(q, int)
        or q < 2
        or isinstance(conrey, bool)
        or not isinstance(conrey, int)
        or not 1 <= conrey < q
        or isinstance(ordinal, bool)
        or not isinstance(ordinal, int)
        or ordinal < 0
        or parity not in (0, 1)
    ):
        _fail("invalid completed-value character identity")
    descriptor = primitive_character_descriptor(q, ordinal)
    if (
        descriptor["conrey_number"] != conrey
        or descriptor["parity"] != parity
    ):
        _fail("primitive ordinal, Conrey number, and parity do not agree")
    commitment_fields = (
        "all_character_stage_receipt_sha256",
        "lattice_and_tail_receipt_sha256",
        "finite_addback_receipt_sha256",
        "root_number_receipt_sha256",
    )
    for name in commitment_fields:
        digest = request.get(name)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            _fail(f"completed-value commitment is not a SHA-256 digest: {name}")
    ordinate = _fraction("ordinate", request.get("ordinate"))
    ctx.prec = precision
    t = _arb_fraction(ordinate)
    l_value = rectangle_acb("l_value", request.get("l_value"))
    root_number = rectangle_acb("root_number", request.get("root_number"))
    if not abs(root_number).contains(1):
        _fail("root-number rectangle does not contain unit modulus")

    # For root number omega, epsilon=conj(sqrt(omega)) gives the phase used in
    # FLINT's theta convention, up to one fixed sign from the square-root branch.
    epsilon = root_number.conjugate().sqrt()
    pi = arb.pi()
    phase_angle = t * ((_arb_fraction(Fraction(q)) / pi).log()) / 2
    conductor_phase = acb(arb(0), phase_angle).exp()
    gamma_argument = acb(_arb_fraction(Fraction(1 + 2 * parity, 4)), t / 2)
    gamma_factor = gamma_argument.gamma()
    scaling = (pi * t / 4).exp()
    completed = epsilon * conductor_phase * gamma_factor * scaling * l_value
    if not completed.imag.contains(0):
        _fail("completed-value imaginary interval does not contain zero")
    sign = 1 if completed.real > 0 else -1 if completed.real < 0 else 0
    return {
        "kind": RESULT_SCHEMA,
        "stage": "completed_value",
        "algorithm_id": ALGORITHM_ID,
        "source_mapping": "Platt Section 1 displayed definition of Lambda_chi",
        "q": q,
        "conrey_number": conrey,
        "primitive_character_ordinal": ordinal,
        "parity": parity,
        "ordinate": request["ordinate"],
        "completed_rectangle": rectangle_json(completed),
        "completed_real": arb_interval(completed.real),
        "strict_sign": sign,
        "upstream_l_value_consumed": True,
        "upstream_commitments": {
            name: request[name] for name in commitment_fields
        },
        "direct_flint_hardy_z_called": False,
        "conditional_on_upstream_interval_semantics": True,
    }


def _sinc(value: Any):
    if value.contains(0):
        # Arb's sin(x)/x is unnecessarily wide at an exact zero-containing
        # point.  All production target/sample differences are exact rationals;
        # only the exact zero case reaches this branch.
        if value.is_zero():
            return arb(1)
    return value.sin() / value


def whittaker_shannon(request: dict[str, Any], *, precision: int = 192) -> dict[str, Any]:
    """Finite sinc reconstruction with explicit source alias/tail budgets."""

    require_flint()
    if request.get("kind") != UPSAMPLE_SCHEMA:
        _fail("unsupported Whittaker--Shannon request")
    q = request.get("q")
    parity = request.get("parity")
    truncation = request.get("truncation_index")
    if (
        isinstance(q, bool)
        or not isinstance(q, int)
        or q < 2
        or parity not in (0, 1)
        or isinstance(truncation, bool)
        or not isinstance(truncation, int)
        or truncation < 2
    ):
        _fail("invalid Whittaker--Shannon parameters")
    bandwidth = _fraction("bandwidth", request.get("bandwidth"))
    gaussian_h = _fraction("gaussian_h", request.get("gaussian_h"))
    target = _fraction("target_ordinate", request.get("target_ordinate"))
    if bandwidth <= 0 or gaussian_h <= 0 or target < 0:
        _fail("Whittaker--Shannon B,h,t0 domain failed")
    samples = request.get("samples")
    if not isinstance(samples, list) or not samples:
        _fail("finite sinc request has no samples")
    indices = [row.get("index") for row in samples]
    if any(isinstance(index, bool) or not isinstance(index, int) for index in indices):
        _fail("finite sinc sample indices must be integers")
    if any(right != left + 1 for left, right in zip(indices, indices[1:])):
        _fail("finite sinc sample indices must be consecutive")
    target_grid_index = 2 * bandwidth * target
    below = sum(Fraction(index) < target_grid_index for index in indices)
    above = sum(Fraction(index) > target_grid_index for index in indices)
    if below < truncation or above < truncation:
        _fail("finite sinc request must retain N samples on each side of t0")

    ctx.prec = precision
    B = _arb_fraction(bandwidth)
    h = _arb_fraction(gaussian_h)
    t0 = _arb_fraction(target)
    pi = arb.pi()
    finite = arb(0)
    for row in samples:
        completed = interval_arb("sample.completed_value", row.get("completed_value"))
        n = row["index"]
        sample_ordinate = Fraction(n, 1) / (2 * bandwidth)
        delta = _arb_fraction(target - sample_ordinate)
        window = (-(delta**2) / (2 * h**2)).exp()
        finite += completed * window * _sinc(2 * B * pi * delta)

    # Theorems 6.2 and Lemmas 6.4--6.5.
    M = _arb_fraction(Fraction(5, 2) - parity)
    p_bound = h * pi * (t0 + h / (2 * pi).sqrt() + 1 + 1 / (2 * arb(2).sqrt()))
    alias = (
        2
        * (arb(q) / pi) ** (M / 2)
        * (M + _arb_fraction(Fraction(1, 2))).zeta()
        * (M**2 / (2 * h**2) - 2 * pi * B * M).exp()
        * p_bound
        / (pi * M)
    )

    # Lemmas 6.6--6.7 exactly as printed.  The source leaves "large enough
    # t0" without a numeric threshold, so this budget is executable but its
    # analytic applicability remains a separately recorded obligation.
    N = arb(truncation)

    def G(offset: int):
        x = N + offset
        return (
            (_arb_fraction(Fraction(3, 2)) + t0 + x / (2 * B))
            ** _arb_fraction(Fraction(9, 16))
            * (-(x**2) / (8 * B**2 * h**2)).exp()
            / (pi * x)
        )

    g0 = G(0)
    ratio = G(1) / g0
    if not ratio < 1:
        _fail("Lemma 6.6 geometric-tail ratio is not strictly below one")
    tail = (
        pi.sqrt()
        * _arb_fraction(Fraction(9, 8)).zeta()
        * _arb_fraction(Fraction(1, 6)).exp()
        * arb(2) ** _arb_fraction(Fraction(5, 4))
        * (arb(q) / (2 * pi)) ** _arb_fraction(Fraction(5, 16))
        * g0
        / (1 - ratio)
    )
    total_radius = alias + tail
    enclosure = finite + arb(0, total_radius.abs_upper())
    sign = 1 if enclosure > 0 else -1 if enclosure < 0 else 0
    return {
        "kind": RESULT_SCHEMA,
        "stage": "whittaker_shannon_upsample",
        "algorithm_id": ALGORITHM_ID,
        "source_mapping": {
            "finite_sinc": "Theorems 6.1--6.2",
            "weiss_alias": "Lemmas 6.4--6.5",
            "truncation": "Lemmas 6.6--6.7",
        },
        "finite_sample_count": len(samples),
        "finite_sinc_sum": arb_interval(finite),
        "weiss_alias_budget": arb_interval(alias),
        "truncation_budget": arb_interval(tail),
        "total_enclosure": arb_interval(enclosure),
        "strict_sign": sign,
        "ordinary_upsampling_path": True,
        "exception_path_used": False,
        "request_asserted_lemma_6_7_large_enough_t0": request.get(
            "lemma_6_7_large_enough_t0_obligation_discharged"
        )
        is True,
        # No reviewed theorem artifact currently realizes the source's
        # unquantified "large enough" condition.  A request Boolean is retained
        # for audit but can never promote itself to a production decision.
        "production_accept": False,
    }


def _zero_staircase_integral(
    name: str, rows: object, t0: Fraction, stop: Fraction
):
    if not isinstance(rows, list):
        _fail(f"{name} must be a list")
    total = arb(0)
    previous_upper = t0
    multiplicities = 0
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"lower", "upper", "multiplicity"}:
            _fail(f"{name}[{index}] is malformed")
        lower = _fraction(f"{name}[{index}].lower", row["lower"])
        upper = _fraction(f"{name}[{index}].upper", row["upper"])
        multiplicity = row["multiplicity"]
        if (
            lower > upper
            or lower < t0
            or upper >= stop
            or lower < previous_upper
            or isinstance(multiplicity, bool)
            or not isinstance(multiplicity, int)
            or multiplicity < 1
        ):
            _fail(f"{name}[{index}] bracket/order/multiplicity failed")
        ordinate = interval_arb(
            f"{name}[{index}]", {"lower": row["lower"], "upper": row["upper"]}
        )
        total += multiplicity * (_arb_fraction(stop) - ordinate)
        multiplicities += multiplicity
        previous_upper = upper
    return total, multiplicities


def paired_turing(request: dict[str, Any], *, precision: int = 192) -> dict[str, Any]:
    """Execute the corrected reflected paired Turing upper bound.

    The target is the symmetric zero count for ``chi``.  Booker's counting
    function is evaluated at ``+t0`` and at ``-t0`` and subtracted; the
    negative window is reflected to the positive window of ``conjugate(chi)``
    through ``L_bar-chi(conj s)=conj(L_chi(s))``.  That cancels the arbitrary
    completed-function phase ``arg(epsilon_chi)`` before integration.
    Expanding ``N=Phi+S`` and averaging over ``[t0,t0+h]`` gives the exact
    identity

        N_chi(t0) = Phi_pair/(h*pi)
                    - (int Ntilde_chi + int Ntilde_bar-chi)/h
                    + (int S_chi + int S_bar-chi)/h,

    so the elementary/log-gamma terms scale by ``1/(h*pi)`` while the
    zero-count staircases and the already ``1/pi``-normalized ``S`` integrals
    scale by ``1/h``.  See ``docs/algorithms/DIRICHLET_TURING_REFLECTED_BOUND.md``
    for the derivation, the two independent literature confirmations, and the
    refutation of the source's extra ``+2h`` bracket term.
    """

    require_flint()
    if request.get("kind") != TURING_SCHEMA:
        _fail("unsupported paired-Turing request")
    q = request.get("q")
    conrey = request.get("conrey_number")
    conjugate_conrey = request.get("conjugate_conrey_number")
    parity = request.get("parity")
    if (
        isinstance(q, bool)
        or not isinstance(q, int)
        or q < 2
        or isinstance(conrey, bool)
        or not isinstance(conrey, int)
        or not 1 <= conrey < q
        or isinstance(conjugate_conrey, bool)
        or not isinstance(conjugate_conrey, int)
        or conjugate_conrey != pow(conrey, -1, q)
        or parity not in (0, 1)
    ):
        _fail("invalid paired-Turing character identity")
    t0_q = _fraction("t0", request.get("t0"))
    h_q = _fraction("h", request.get("h"))
    if t0_q <= 50 or h_q <= 0:
        _fail("Rumely's source bound requires t0>50 and h>0")
    if request.get("endpoints_zero_free") is not True:
        _fail("Turing window endpoints must be certified zero-free")
    if request.get("window_bracket_multiplicity_lower_bounds_certified") is not True:
        _fail("Turing window bracket multiplicity lower bounds are not certified")
    if request.get("negative_window_reflected_to_conjugate_certified") is not True:
        _fail("negative chi window to positive conjugate reflection is not certified")
    isolated_below = request.get("isolated_count_below_t0")
    if (
        isinstance(isolated_below, bool)
        or not isinstance(isolated_below, int)
        or isolated_below < 0
        or request.get("isolated_below_t0_certified") is not True
    ):
        _fail("certified isolated count below t0 is required")
    # Optional, strictly stronger caller assertion.  It claims that the window
    # bracket list is complete with exact multiplicities and that
    # ``isolated_count_below_t0`` is exactly ``N_chi(t0)``, not merely a lower
    # bound.  Under that assertion the corrected display is an equality, so the
    # residual must be the paired S integral and must satisfy Theorem 3.3.
    # The check is fail-closed in both directions: it also rejects a bracket
    # list whose ordinate enclosures are simply too wide to resolve the
    # residual, so a caller must bisect before setting the flag.
    identity_residual_certified = request.get(
        "window_complete_and_count_exact_certified", False
    )
    if identity_residual_certified not in (True, False):
        _fail("window_complete_and_count_exact_certified must be boolean")
    stop_q = t0_q + h_q
    ctx.prec = precision
    t0 = _arb_fraction(t0_q)
    h = _arb_fraction(h_q)
    stop = _arb_fraction(stop_q)
    pi = arb.pi()

    def gamma_integrand(x: Any, analytic: bool):
        argument = (
            acb(_arb_fraction(Fraction(1, 2) + parity)) + acb(0, 1) * x
        ) / 2
        # The path has strictly positive real part, so it meets no gamma pole
        # or log-gamma branch obstruction.  python-flint 0.9 exposes lgamma as
        # a meromorphic evaluator without an ``analytic=`` keyword.
        return argument.lgamma()

    gamma_integral = acb.integral(
        gamma_integrand,
        t0,
        stop,
        rel_tol=arb(2) ** (-precision + 16),
        abs_tol=arb(2) ** (-precision + 16),
    ).imag
    chi_staircase, chi_multiplicity = _zero_staircase_integral(
        "chi_window_zeros", request.get("chi_window_zeros"), t0_q, stop_q
    )
    conjugate_staircase, conjugate_multiplicity = _zero_staircase_integral(
        "conjugate_window_zeros",
        request.get("conjugate_window_zeros"),
        t0_q,
        stop_q,
    )
    phase_main = (
        ((2 * h * t0 + h**2) / 2) * (arb(q) / pi).log()
        + 2 * gamma_integral
    )
    # Theorem 3.3, applied once to chi and once to conjugate chi.
    rumely_one = _arb_fraction(Fraction(18397, 10000)) + _arb_fraction(
        Fraction(621, 5000)
    ) * (
        arb(q) * stop / (2 * pi)
    ).log()
    if not rumely_one > 0:
        _fail("Rumely bound did not resolve positive")
    s_pair_integral = arb(0, 2 * rumely_one.abs_upper())

    # Evaluate Booker's counting function at +t0 and at -t0 and subtract.
    # Reflection identifies the negative window with the positive
    # conjugate-character window.  The constant arg(epsilon) cancels between
    # the two endpoints, so no caller-supplied phase anchor belongs here.
    # Expanding N=Phi+S fixes the normalization: Phi's elementary/gamma terms
    # carry 1/(h*pi), whereas N-tilde is a plain zero count and S already
    # carries its own 1/pi, so both carry 1/h.
    phi_over_h_pi = phase_main / (h * pi)
    paired_staircase_over_h = (chi_staircase + conjugate_staircase) / h
    source_normalized_interval = (
        phi_over_h_pi - paired_staircase_over_h + s_pair_integral / h
    )
    # Audit only.  The arXiv v1 Theorem 3.2 display puts the staircase and S
    # integrals behind the same 1/(h*pi) as the elementary/gamma terms.  Those
    # objects are not pi-normalized, so the display is dimensionally
    # inconsistent and lands near 86 where the true q=3 count is 44.
    literal_typeset_interval = (
        2 * h
        + phase_main
        - chi_staircase
        - conjugate_staircase
        + s_pair_integral
    ) / (h * pi)
    # The retained future-window list need not be assumed complete.  Every
    # certified bracket is a lower bound for the true staircase, whose minus
    # sign makes the following an upper bound for N_chi(t0).  The already
    # isolated zeros below t0 give N_chi(t0) >= isolated_below.  If this upper
    # bound is below the next integer, equality follows and all lower zeros are
    # complete.  This is the non-circular Turing decision used in production.
    completion_upper = phi_over_h_pi - paired_staircase_over_h + 2 * rumely_one / h
    # Audit only.  Platt's arXiv v1 bracket carries an extra "+2h", and his
    # released find_zeros.cpp adds one h per character at the end of ln_term;
    # both amount to +2/pi once the corrected scaling is applied.  The identity
    # derived from Booker Theorem 3.1 -- and Trudgian's independent display
    # (2.3) -- has no such constant, and the multi-conductor identity KAT
    # refutes it: including it forces (int S_chi + int S_bar-chi)/h far outside
    # Theorem 3.3's envelope.  Because it enters an upper bound with a positive
    # sign it is conservative, so bounds computed with it stay valid; it is
    # simply 2/pi of wasted margin in a decision whose whole budget is 1.
    released_code_upper = completion_upper + 2 / pi
    # Under the corrected normalization the display is an equality, so when the
    # caller certifies a complete exact-multiplicity window and an exact count
    # the residual must be the paired S integral.  Theorem 3.3 then bounds it.
    identity_residual = (
        _arb_fraction(Fraction(isolated_below)) - phi_over_h_pi + paired_staircase_over_h
    )
    if identity_residual_certified:
        bound = 2 * rumely_one / h
        if not (identity_residual < bound and identity_residual > -bound):
            _fail(
                "certified-complete window residual escapes Rumely Theorem 3.3; "
                "the reflected Turing identity does not hold as normalized"
            )
    if not completion_upper < isolated_below + 1:
        _fail("paired Turing upper bound does not fall below the next integer")
    if completion_upper < isolated_below:
        _fail("paired Turing upper bound contradicts certified isolated zeros")
    count = isolated_below
    return {
        "kind": RESULT_SCHEMA,
        "stage": "paired_turing_closure",
        "algorithm_id": ALGORITHM_ID,
        "source_mapping": {
            "count_identity": "Platt Theorem 3.2",
            "s_integral_bound": "Platt Theorem 3.3 (Rumely constants 1.8397, 0.1242)",
            "released_code": {
                "commit": RELEASED_CODE_COMMIT,
                "path": "l-func-hi/find_zeros.cpp",
                "functions": ["ln_term", "turing_max"],
                "url": RELEASED_TURING_CODE_URL,
            },
            "conjugate_pairing": True,
            "independent_identity_confirmation": (
                "Trudgian, Math. Comp. 84 (2015), no. 293, 1439-1450 "
                "(arXiv:1206.1844v4), display (2.3): N(T,chi) = "
                "(T/pi)log(k/pi) + (2/pi) Im logGamma(1/4+a/2+iT/2) "
                "+ (1/pi) Delta_C arg L(s,chi), with no additive constant."
            ),
            "normalization_audit": (
                "Booker N(+t0) minus N(-t0), reflected to bar-chi, cancels "
                "arg(epsilon); Phi uses 1/(h*pi), while the zero staircases and "
                "the already 1/pi-normalized S integrals use 1/h. The display's "
                "common 1/(h*pi) and its extra +2h are retained as audit "
                "quantities only; neither is used in the decision."
            ),
            "source_2h_term": (
                "arXiv v1 Theorem 3.2 prints '+2h' inside the common bracket "
                "and find_zeros.cpp ln_term adds one h per character; both give "
                "+2/pi. The identity has no such constant. It is a positive "
                "slack, hence conservative, but it is not part of the theorem."
            ),
            "negative_window_reflection": (
                "L_bar-chi(conj(s))=conj(L_chi(s)) and S_chi(-t)=-S_bar-chi(t)"
            ),
        },
        "q": q,
        "conrey_number": conrey,
        "conjugate_conrey_number": conjugate_conrey,
        "parity": parity,
        "t0": request["t0"],
        "h": request["h"],
        "gamma_integral": arb_interval(gamma_integral),
        "chi_staircase_integral": arb_interval(chi_staircase),
        "conjugate_staircase_integral": arb_interval(conjugate_staircase),
        "chi_window_multiplicity": chi_multiplicity,
        "conjugate_window_multiplicity": conjugate_multiplicity,
        "rumely_bound_per_character": arb_interval(rumely_one),
        "paired_rumely_bound_over_h": arb_interval(2 * rumely_one / h),
        "phi_over_h_pi_interval": arb_interval(phi_over_h_pi),
        "paired_staircase_over_h_interval": arb_interval(paired_staircase_over_h),
        "source_two_over_pi_contribution": arb_interval(2 / pi),
        "source_normalized_model_interval": arb_interval(source_normalized_interval),
        "completion_upper_bound": arb_interval(completion_upper),
        "identity_residual_interval": arb_interval(identity_residual),
        "platt_released_code_upper_bound": arb_interval(released_code_upper),
        "literal_arxiv_v1_typeset_interval": arb_interval(literal_typeset_interval),
        "certified_multiplicity_count_below_t0": count,
        "next_integer_excluded_by_turing_upper_bound": count + 1,
        "future_window_completeness_assumed": False,
        "window_complete_and_count_exact_certified": identity_residual_certified,
        "multiplicity_preserved": True,
        "source_normalized_reflected_turing_candidate_executed": True,
        "negative_window_reflected_to_conjugate_certified": True,
        "source_2h_constant_included_in_bound": False,
        "literal_paper_theorem_3_2_accepted": False,
        "production_accept": False,
    }


def evaluate(request: dict[str, Any], *, precision: int = 192) -> dict[str, Any]:
    kind = request.get("kind")
    if kind == COMPLETED_SCHEMA:
        return completed_value(request, precision=precision)
    if kind == UPSAMPLE_SCHEMA:
        return whittaker_shannon(request, precision=precision)
    if kind == TURING_SCHEMA:
        return paired_turing(request, precision=precision)
    _fail("unknown Dirichlet postprocess request kind")


def capability_report() -> dict[str, Any]:
    return {
        "algorithm_id": ALGORITHM_ID,
        "source": SOURCE_URL,
        "released_turing_code": {
            "commit": RELEASED_CODE_COMMIT,
            "path": "l-func-hi/find_zeros.cpp",
            "functions": ["ln_term", "turing_max"],
            "url": RELEASED_TURING_CODE_URL,
        },
        "production_ready": False,
        "full_source": {
            "input_domain_supported": True,
            "campaign_run_completed": False,
            "parameter_optimization_complete": False,
        },
        "stages": {
            "completed_value_from_interval_L": True,
            "ordinary_whittaker_shannon_finite_sinc": True,
            "weiss_alias_budget": True,
            "lemma_6_7_truncation_budget": True,
            "direct_arb_exception_fallback": True,
            "conjugate_paired_turing_formula": True,
            "rumely_bound": True,
            "literal_theorem_3_2_normalization_accepted": False,
            "source_normalized_reflection_candidate_only": True,
            "source_two_over_pi_contribution_included": False,
            "source_2h_constant_refuted_by_identity_kat": True,
            "identity_residual_check_available": True,
        },
        "accepted_manuscript_parameters": {
            "source": "https://research-information.bris.ac.uk/ws/portalfiles/portal/67056136/platt_grh3.0.pdf",
            "section": 9,
            "A": fraction_json(Fraction(64, 5)),
            "B_from_2B_equals_A": fraction_json(Fraction(32, 5)),
            "gaussian_h": fraction_json(Fraction(7, 32)),
            "samples_each_side": 20,
            "claimed_error_strictly_below": fraction_json(Fraction(86, 1_000_000_000)),
            "q3_odd_source_height_formula_kat": {
                "target": fraction_json(Fraction(100_000_000, 3)),
                "computed_total_budget_approximately": "8.4123e-8",
                "strictly_below_claimed_error": True,
            },
            "uniform_source_range_reproved": False,
        },
        "work_units": {
            "ordinary_upsampling": "finite completed-value intervals consumed",
            "exception_path": "direct Arb completed-L evaluations",
            "turing_path": "window zero brackets plus one rigorous log-gamma integral per pair",
        },
        "benchmark": {
            "command": "python3 tools/benchmark_tg_dirichlet_postprocess.py --pretty",
            "rate_fields": {
                "ordinary_upsampling": "finite completed-value intervals per second",
                "exception_path": "direct FLINT Hardy-Z signs per second",
                "turing_path": "paired window arithmetic closures per second",
            },
            "local_reference_sample": {
                "date": "2026-07-21",
                "host": "DGX Spark / NVIDIA GB10 / 20-core Cortex-X925",
                "precision_bits": 128,
                "ordinary_intervals": 8192,
                "ordinary_intervals_per_second": 100984.52814459895,
                "exception_signs": 100,
                "exception_signs_per_second": 6565.742455835682,
                "turing_window_repeats": 20,
                "turing_windows_per_second": 694.3817630388589,
                "warning": "synthetic/local arithmetic microbenchmark, not a source campaign ETA",
            },
        },
        "unclosed_conditions": [
            "certified source all-character L rectangles and root numbers",
            "numeric threshold for Lemma 6.7's printed 'large enough t0' hypothesis",
            "source parameter selection and window-shift retry policy",
            "uniform proof of the accepted manuscript's <8.6e-8 claim over every source case",
            "Lean realization of the corrected reflected Theorem 3.2 identity",
            "full-source production execution",
            "Lean analytic realization",
        ],
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "COMPLETED_SCHEMA",
    "DirichletPostprocessError",
    "RESULT_SCHEMA",
    "RELEASED_CODE_COMMIT",
    "RELEASED_TURING_CODE_URL",
    "TURING_SCHEMA",
    "UPSAMPLE_SCHEMA",
    "arb_interval",
    "capability_report",
    "completed_value",
    "evaluate",
    "fraction_json",
    "interval_arb",
    "paired_turing",
    "rectangle_json",
    "whittaker_shannon",
]
