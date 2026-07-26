# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Rigorous small-conductor Fourier engine for Platt's GRH computation.

This module implements the finite Fourier method in Section 5 of
``arXiv:1305.3087v1`` (specialized there from Booker 2006).  For one primitive
Dirichlet character it

* evaluates the displayed Gaussian series for ``Fhat_e`` or ``Fhat_o``;
* proves a geometric bound for the omitted Gaussian terms;
* proves a direct Gaussian bound for both omitted periodization wings;
* applies the positive-sign DFT pair with ``A = 64/5``; and
* removes Platt's exponential tilt and applies the displayed ``E/beta`` bound
  for the omitted time-periodization terms.

All analytic values are Arb rectangles.  Frequency work is split into
hash-bound, independently replayable chunks.  The full source plan covers
every primitive character with ``q <= 10000`` and every ``5/64`` sample up to
Platt's parity-dependent height, but running that plan is intentionally not
confused with having completed Theorem 7.1: upsampling, exceptional cases,
zero isolation, and Turing completeness live in later stages.

The periodized-frequency bound is derived directly from Lemmas 5.1/5.2's
Gaussian series.  This avoids relying on the apparent missing exponential and
conductor factors in the v1 TeX definition of ``X(x)`` on line 605.
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
import time
from typing import Any, Iterable, Iterator, NoReturn, Sequence

from tg_verifier.dirichlet_campaign import (
    primitive_character_count,
    primitive_character_descriptor,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-booker-smallq-gaussian-dft-v1"
CHECKER_ID = "arb-higher-precision-smallq-replay-v1"
SOURCE_URL = "https://arxiv.org/abs/1305.3087v1"
BOOKER_SOURCE_URL = "https://arxiv.org/abs/math/0507502v1"
ACCEPTED_MANUSCRIPT_URL = (
    "https://research-information.bris.ac.uk/ws/portalfiles/portal/"
    "67056136/platt_grh3.0.pdf"
)
ACCEPTED_MANUSCRIPT_SHA256 = (
    "6b6a98461613018a4516d946bc0471f792ecf6a9ade7e7862b5e44c73f98c40a"
)

EXPECTED_PYTHON_FLINT = "0.9.0"
EXPECTED_FLINT = "3.6.0"
EXPECTED_FLINT_RELEASE = 30_600

SOURCE_Q_START = 2
SOURCE_Q_STOP = 10_000
SAMPLE_STEP = Fraction(5, 64)
SAMPLE_RATE_A = Fraction(64, 5)
DEFAULT_GUARD_HEIGHT = Fraction(64)
DEFAULT_TARGET_BITS = 96
DEFAULT_PRECISION_BITS = 160
DEFAULT_REPLAY_GUARD_BITS = 64
DEFAULT_FREQUENCY_CHUNK_SIZE = 1 << 20
MAX_CONTROL_BYTES = 64 * 1024 * 1024

CHUNK_SCHEMA = "sparkinterval.tg.dirichlet_booker_smallq.frequency_chunk.v1"
CHUNK_MANIFEST_SCHEMA = (
    "sparkinterval.tg.dirichlet_booker_smallq.frequency_manifest.v1"
)
SAMPLES_SCHEMA = "sparkinterval.tg.dirichlet_booker_smallq.samples.v1"
PLAN_SCHEMA = "sparkinterval.tg.dirichlet_booker_smallq.source_plan.v1"
CAPABILITY_SCHEMA = "sparkinterval.tg.dirichlet_booker_smallq.capability.v1"

HEADER_NAME = "request.json"
VALUES_NAME = "frequencies.ndjson"
MANIFEST_NAME = "manifest.json"
SAMPLES_NAME = "samples.ndjson"

GPU_INPUT_MAGIC = b"TGDBSQI1"
GPU_OUTPUT_MAGIC = b"TGDBSQO1"
GPU_FORMAT_VERSION = 1
GPU_NONUNIT_EXPONENT = (1 << 32) - 1
GPU_INPUT_HEADER = struct.Struct("<8sIIIIQQQddddQ")
GPU_FREQUENCY_REQUEST = struct.Struct("<QqII")
GPU_OUTPUT_HEADER = struct.Struct("<8sIIQQQQ")
GPU_OUTPUT_ITEM = struct.Struct("<QddII")

SOURCE_MAPPING = (
    {
        "paper": "accepted manuscript Section 7, definitions preceding Lemma 7.1",
        "implementation": "tilted completed F_e/F_o and positive-sign DFT pair",
    },
    {
        "paper": "accepted manuscript Lemmas 7.1 and 7.2",
        "implementation": "even and odd truncated Gaussian character sums",
    },
    {
        "paper": "paragraph after accepted-manuscript Lemma 7.1",
        "implementation": "explicit project-derived geometric Gaussian tail",
    },
    {
        "paper": "accepted manuscript Lemma 7.5",
        "implementation": "two omitted frequency-periodization wings",
    },
    {
        "paper": "accepted manuscript Lemma 7.6",
        "implementation": "E_e/E_o and beta_e/beta_o time-periodization bound",
    },
)

DECISIONS = {
    "full_q_2_through_10000_domain_scheduled": True,
    "full_5_over_64_lattice_scheduled": True,
    "gaussian_series_interval_algorithm_implemented": True,
    "gaussian_tail_bound_algorithm_implemented": True,
    "frequency_periodization_bound_algorithm_implemented": True,
    "positive_sign_dft_algorithm_implemented": True,
    "time_periodization_bound_algorithm_implemented": True,
    "completed_real_lambda_sample_algorithm_implemented": True,
    "upsampling_completed": False,
    "exceptional_cases_completed": False,
    "zero_isolation_completed": False,
    "turing_completeness_completed": False,
    "external_atom_discharged": False,
}


class DirichletBookerSmallQError(RuntimeError):
    """A small-q request, interval decision, artifact, or replay failed."""


def _fail(message: str) -> NoReturn:
    raise DirichletBookerSmallQError(message)


try:
    import flint
    from flint import acb, arb, ctx, dirichlet_char
except ImportError as error:  # pragma: no cover - runtime-dependent
    flint = acb = arb = ctx = dirichlet_char = None
    FLINT_IMPORT_ERROR = error
else:
    FLINT_IMPORT_ERROR = None


def _require_flint() -> None:
    if FLINT_IMPORT_ERROR is not None:
        _fail(f"python-flint is required ({FLINT_IMPORT_ERROR})")
    found = (
        str(flint.__version__),
        str(flint.__FLINT_VERSION__),
        int(flint.__FLINT_RELEASE__),
    )
    expected = (
        EXPECTED_PYTHON_FLINT,
        EXPECTED_FLINT,
        EXPECTED_FLINT_RELEASE,
    )
    if found != expected:
        _fail(f"FLINT runtime mismatch: found {found}, required {expected}")


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


def _write_atomic(path: Path, raw: bytes) -> None:
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


def _load_canonical_json(path: Path) -> Any:
    raw = path.read_bytes()
    if len(raw) > MAX_CONTROL_BYTES:
        _fail(f"control JSON exceeds {MAX_CONTROL_BYTES} bytes: {path}")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletBookerSmallQError(f"invalid JSON {path}: {error}") from error
    if canonical_json_bytes(value) != raw:
        _fail(f"noncanonical JSON: {path}")
    return value


def _fraction_record(value: Fraction) -> dict[str, str]:
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def _fraction_from_record(value: object, label: str) -> Fraction:
    if not isinstance(value, dict) or set(value) != {"numerator", "denominator"}:
        _fail(f"{label} is not a rational record")
    try:
        numerator = int(value["numerator"])
        denominator = int(value["denominator"])
    except (TypeError, ValueError) as error:
        raise DirichletBookerSmallQError(f"invalid rational {label}") from error
    answer = Fraction(numerator, denominator)
    if denominator <= 0 or answer.numerator != numerator or answer.denominator != denominator:
        _fail(f"{label} is not a reduced positive-denominator rational")
    if str(numerator) != value["numerator"] or str(denominator) != value["denominator"]:
        _fail(f"{label} is not canonically encoded")
    return answer


def _arb_fraction(value: Fraction) -> Any:
    return arb(f"{value.numerator}/{value.denominator}")


def _decimal_digits(bits: int) -> int:
    return max(30, math.ceil(bits * math.log10(2)) + 16)


def _arb_record(value: Any, bits: int) -> dict[str, object]:
    midpoint, radius, exponent = value.mid_rad_10exp(_decimal_digits(bits))
    return {"mid": str(midpoint), "rad": str(radius), "exp10": int(exponent)}


def _arb_from_record(value: object, label: str) -> Any:
    if not isinstance(value, dict) or set(value) != {"mid", "rad", "exp10"}:
        _fail(f"{label} is not an Arb decimal-ball record")
    if not isinstance(value["mid"], str) or not isinstance(value["rad"], str):
        _fail(f"{label} midpoint/radius must be strings")
    if isinstance(value["exp10"], bool) or not isinstance(value["exp10"], int):
        _fail(f"{label} exponent must be an integer")
    try:
        midpoint = int(value["mid"])
        radius = int(value["rad"])
    except ValueError as error:
        raise DirichletBookerSmallQError(f"{label} contains nonintegers") from error
    if radius < 0 or str(midpoint) != value["mid"] or str(radius) != value["rad"]:
        _fail(f"{label} is not canonically encoded")
    exponent = value["exp10"]
    return arb(f"{midpoint}e{exponent}", f"{radius}e{exponent}")


def _acb_record(value: Any, bits: int) -> dict[str, object]:
    return {"real": _arb_record(value.real, bits), "imag": _arb_record(value.imag, bits)}


def _acb_from_record(value: object, label: str) -> Any:
    if not isinstance(value, dict) or set(value) != {"real", "imag"}:
        _fail(f"{label} is not a complex-ball record")
    return acb(
        _arb_from_record(value["real"], f"{label}.real"),
        _arb_from_record(value["imag"], f"{label}.imag"),
    )


def source_height(q: int) -> Fraction:
    if not SOURCE_Q_START <= q <= SOURCE_Q_STOP:
        _fail("small-q source modulus is outside 2..10000")
    additive = 75_000_000 if q % 2 == 0 else 37_500_000
    return Fraction(max(100_000_000, additive + 200 * q), q)


def _ceil_fraction(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def _next_power_of_two(value: int) -> int:
    if value <= 0:
        _fail("positive transform length requested")
    return 1 << (value - 1).bit_length()


@dataclass(frozen=True)
class TransformParameters:
    q: int
    height: Fraction
    a: Fraction
    b: Fraction
    eta: Fraction
    transform_length: int
    sample_count: int

    def record(self) -> dict[str, object]:
        return {
            "q": self.q,
            "height": _fraction_record(self.height),
            "a": _fraction_record(self.a),
            "b": _fraction_record(self.b),
            "eta": _fraction_record(self.eta),
            "transform_length": self.transform_length,
            "sample_step": _fraction_record(1 / self.a),
            "sample_count": self.sample_count,
        }


def transform_parameters(
    q: int,
    *,
    height: Fraction | None = None,
    guard_height: Fraction = DEFAULT_GUARD_HEIGHT,
    transform_length: int | None = None,
    eta: Fraction | None = None,
) -> TransformParameters:
    if not SOURCE_Q_START <= q <= SOURCE_Q_STOP:
        _fail("small-q modulus is outside 2..10000")
    height = source_height(q) if height is None else Fraction(height)
    guard_height = Fraction(guard_height)
    if height < 0 or guard_height <= 2:
        _fail("height must be nonnegative and guard_height must exceed 2")
    minimum = _ceil_fraction(SAMPLE_RATE_A * (height + guard_height))
    if transform_length is None:
        transform_length = _next_power_of_two(minimum)
    if (
        isinstance(transform_length, bool)
        or transform_length < minimum
        or transform_length & (transform_length - 1)
    ):
        _fail("transform_length must be a power of two covering height+guard")
    b = Fraction(transform_length, 1) / SAMPLE_RATE_A
    eta = height / (height + guard_height) if eta is None else Fraction(eta)
    if not -1 < eta < 1:
        _fail("eta must be strictly between -1 and 1")
    samples = int(height * SAMPLE_RATE_A) + 1
    if Fraction(samples - 1, 1) / SAMPLE_RATE_A > height:
        _fail("internal source-sample count failure")
    return TransformParameters(
        q=q,
        height=height,
        a=SAMPLE_RATE_A,
        b=b,
        eta=eta,
        transform_length=transform_length,
        sample_count=samples,
    )


def _character(q: int, conrey_number: int) -> Any:
    _require_flint()
    try:
        character = dirichlet_char(q, conrey_number)
    except (ValueError, TypeError) as error:
        raise DirichletBookerSmallQError("invalid Dirichlet character") from error
    if not character.is_primitive() or character.is_principal():
        _fail("the small-q engine requires a primitive nonprincipal character")
    return character


def _character_value(character: Any, n: int) -> Any:
    exponent = character.chi_exponent(n % character.modulus())
    if exponent is None:
        return acb(0)
    group_exponent = character.group().exponent()
    return acb(arb(2 * exponent) / group_exponent).exp_pi_i()


def _epsilon_phase(character: Any) -> Any:
    """Return Platt's epsilon with principal positive-real square root."""

    q = character.modulus()
    parity = character.parity()
    tau = acb(0)
    for residue in range(1, q + 1):
        value = _character_value(character, residue)
        if value.is_zero():
            continue
        additive = acb(arb(2 * residue) / q).exp_pi_i()
        tau += value * additive
    root_number = tau / ((acb(0, 1) ** parity) * arb(q).sqrt())
    epsilon = root_number.conjugate().sqrt()
    if epsilon.real < 0 or (epsilon.real.contains(0) and epsilon.imag < 0):
        epsilon = -epsilon
    modulus_error = abs(abs(epsilon) - 1)
    if not modulus_error.contains(0):
        _fail("Gauss-sum phase is not certified to have unit magnitude")
    return epsilon


def _positive_arb(value: Any, label: str) -> None:
    if not value > 0:
        _fail(f"{label} is not certified positive")


def _gaussian_tail(
    *, q: int, parity: int, eta: Fraction, x: Any, truncation: int
) -> Any:
    if truncation < 0:
        _fail("negative Gaussian truncation")
    eta_ball = _arb_fraction(eta)
    cosine = (arb.pi() * eta_ball / 2).cos()
    _positive_arb(cosine, "Gaussian decay cosine")
    decay = arb.pi() * (2 * x).exp() * cosine / q
    _positive_arb(decay, "Gaussian decay coefficient")
    first_index = truncation + 1
    ratio = (-decay * (2 * truncation + 3)).exp()
    if parity:
        ratio *= arb(first_index + 1) / first_index
    if not ratio < 1:
        _fail("Gaussian tail ratio is not certified below one")
    first = (-decay * first_index * first_index).exp()
    if parity:
        first *= first_index
    series_tail = first / (1 - ratio)
    p = arb(2 * parity + 1) / 2
    prefactor_abs = 2 * (p * x).exp() / (arb(q) ** (p / 2))
    return prefactor_abs * series_tail


def _choose_truncation(
    *, q: int, parity: int, eta: Fraction, x: Any, target_bits: int
) -> tuple[int, Any]:
    if target_bits < 32:
        _fail("target_bits must be at least 32")
    eta_float = float(eta)
    x_float = float(x.mid())
    cosine = math.cos(math.pi * eta_float / 2)
    decay = math.pi * math.exp(2 * x_float) * cosine / q
    if not decay > 0 or not math.isfinite(decay):
        _fail("cannot initialize Gaussian truncation")
    initial = max(0, math.ceil(math.sqrt((target_bits + 16) * math.log(2) / decay)) - 1)
    target = arb(2) ** (-target_bits)
    truncation = initial
    while True:
        tail = _gaussian_tail(
            q=q, parity=parity, eta=eta, x=x, truncation=truncation
        )
        if tail < target:
            return truncation, tail
        truncation += max(1, truncation // 32)
        if truncation > 100_000_000:
            _fail("Gaussian truncation exceeds the safety limit")


def _frequency_periodization_bound(
    *, q: int, parity: int, eta: Fraction, x: Any, a: Fraction
) -> Any:
    """Bound all nonzero frequency-periodization copies directly.

    For a positive wing starting at ``w`` the magnitude of each Gaussian
    term after increasing ``w`` by ``Delta=2*pi*A`` has ratio at most

      exp(p*Delta - C(w)*(exp(2*Delta)-1)),

    where ``p=1/2`` or ``3/2`` and ``C(w)>0`` is the Gaussian decay.  The
    ratio decreases with both the Gaussian index and the wing index.
    """

    eta_ball = _arb_fraction(eta)
    a_ball = _arb_fraction(a)
    delta_w = 2 * arb.pi() * a_ball
    p = arb(2 * parity + 1) / 2
    cosine = (arb.pi() * eta_ball / 2).cos()
    _positive_arb(cosine, "frequency-periodization cosine")

    def wing(w: Any) -> Any:
        decay = arb.pi() * (2 * w).exp() * cosine / q
        _positive_arb(decay, "frequency-periodization decay")
        term_ratio = (-3 * decay).exp()
        if parity:
            term_ratio *= 2
        if not term_ratio < 1:
            _fail("frequency-wing Gaussian ratio is not below one")
        gaussian_sum = (-decay).exp() / (1 - term_ratio)
        prefactor = 2 * (p * w).exp() / (arb(q) ** (p / 2))
        first_wing = prefactor * gaussian_sum
        wing_ratio = (p * delta_w - decay * ((2 * delta_w).exp() - 1)).exp()
        if not wing_ratio < 1:
            _fail("frequency-periodization wing ratio is not below one")
        return first_wing / (1 - wing_ratio)

    w1 = delta_w + x
    w2 = delta_w - x
    _positive_arb(w1, "positive frequency wing")
    _positive_arb(w2, "negative frequency wing")
    return wing(w1) + wing(w2)


def evaluate_frequency(
    *,
    q: int,
    conrey_number: int,
    parameters: TransformParameters,
    frequency_index: int,
    target_bits: int = DEFAULT_TARGET_BITS,
    truncation: int | None = None,
    _character_object: Any | None = None,
    _epsilon: Any | None = None,
) -> dict[str, Any]:
    if parameters.q != q:
        _fail("parameter modulus mismatch")
    length = parameters.transform_length
    if not 0 <= frequency_index < length:
        _fail("frequency index is outside the transform")
    character = (
        _character(q, conrey_number)
        if _character_object is None
        else _character_object
    )
    if character.modulus() != q or character.number() != conrey_number:
        _fail("cached character identity mismatch")
    parity = character.parity()
    signed = frequency_index if frequency_index <= length // 2 else frequency_index - length
    positive_signed = abs(signed)
    x = 2 * arb.pi() * positive_signed / _arb_fraction(parameters.b)
    if truncation is None:
        truncation, gaussian_tail = _choose_truncation(
            q=q,
            parity=parity,
            eta=parameters.eta,
            x=x,
            target_bits=target_bits,
        )
    else:
        gaussian_tail = _gaussian_tail(
            q=q,
            parity=parity,
            eta=parameters.eta,
            x=x,
            truncation=truncation,
        )
    epsilon = _epsilon_phase(character) if _epsilon is None else _epsilon
    eta_ball = _arb_fraction(parameters.eta)
    u = acb(x, arb.pi() * eta_ball / 4)
    exponential = (2 * u).exp()
    subtotal = acb(0)
    for n in range(1, truncation + 1):
        chi = _character_value(character, n)
        if chi.is_zero():
            continue
        term = chi * (-arb.pi() * n * n * exponential / q).exp()
        if parity:
            term *= n
        subtotal += term
    p = arb(2 * parity + 1) / 2
    finite = 2 * epsilon * (p * u).exp() * subtotal / (arb(q) ** (p / 2))
    if signed < 0:
        finite = finite.conjugate()
    alias = _frequency_periodization_bound(
        q=q, parity=parity, eta=parameters.eta, x=x, a=parameters.a
    )
    total_radius = gaussian_tail + alias
    enclosure = finite + acb(arb(0, total_radius), arb(0, total_radius))
    return {
        "index": frequency_index,
        "signed_index": signed,
        "truncation": truncation,
        "finite": finite,
        "gaussian_tail": gaussian_tail,
        "frequency_periodization": alias,
        "enclosure": enclosure,
    }


def _time_periodization_bound(
    *, q: int, parity: int, eta: Fraction, t: Fraction, b: Fraction
) -> Any:
    """Apply Platt's displayed E/beta bound to both omitted time wings."""

    eta_ball = _arb_fraction(eta)
    t_ball = _arb_fraction(t)
    b_ball = _arb_fraction(b)
    pi = arb.pi()

    def beta(value: Any) -> Any:
        absolute = abs(value)
        if not absolute > 0:
            _fail("time-periodization beta is singular at zero")
        coefficient = arb(2 * parity + 1) / 2
        singular_square = arb((2 * parity + 1) ** 2) / 4
        denominator = pi * pi * abs(value * value - singular_square)
        _positive_arb(denominator, "time-periodization beta denominator")
        return pi / 4 - coefficient * (1 / (2 * absolute)).atan() - 4 / denominator

    def envelope(value: Any) -> Any:
        gamma_real = arb(2 * parity + 1) / 4
        gamma_value = abs(acb(gamma_real, value / 2).gamma())
        # Rademacher gives (3/2+|t|), which is also safe on the negative wing.
        conductor = q * (arb(3) / 2 + abs(value)) / (2 * pi)
        return (
            (arb(9) / 8).zeta()
            * (pi ** (-gamma_real))
            * gamma_value
            * (pi * eta_ball * value / 4).exp()
            * (conductor ** (arb(5) / 16))
        )

    positive_t = t_ball + b_ball
    negative_t = t_ball - b_ball
    positive_decay = beta(positive_t) - pi * eta_ball / 4
    negative_decay = beta(negative_t) + pi * eta_ball / 4
    _positive_arb(positive_decay, "positive time-wing decay")
    _positive_arb(negative_decay, "negative time-wing decay")
    positive_denominator = 1 - (-b_ball * positive_decay).exp()
    negative_denominator = 1 - (-b_ball * negative_decay).exp()
    _positive_arb(positive_denominator, "positive time-wing denominator")
    _positive_arb(negative_denominator, "negative time-wing denominator")
    return (
        envelope(positive_t) / positive_denominator
        + envelope(negative_t) / negative_denominator
    )


def _positive_dft(values: Sequence[Any]) -> list[Any]:
    """Radix-2 DFT with exp(+2*pi*i*j*k/N), without normalization."""

    length = len(values)
    if length == 0 or length & (length - 1):
        _fail("DFT input length must be a positive power of two")
    result = list(values)
    j = 0
    for i in range(1, length):
        bit = length >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            result[i], result[j] = result[j], result[i]
    width = 2
    while width <= length:
        root = acb(arb(2) / width).exp_pi_i()
        half = width // 2
        for start in range(0, length, width):
            twiddle = acb(1)
            for offset in range(half):
                even = result[start + offset]
                odd = result[start + offset + half] * twiddle
                result[start + offset] = even + odd
                result[start + offset + half] = even - odd
                twiddle *= root
        width *= 2
    return result


def _chunk_header(
    *,
    q: int,
    conrey_number: int,
    character_ordinal: int | None,
    parameters: TransformParameters,
    frequency_start: int,
    frequency_stop: int,
    precision_bits: int,
    target_bits: int,
) -> dict[str, object]:
    character = _character(q, conrey_number)
    return {
        "kind": CHUNK_SCHEMA,
        "algorithm_id": ALGORITHM_ID,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "source": {
            "platt": SOURCE_URL,
            "accepted_manuscript": ACCEPTED_MANUSCRIPT_URL,
            "accepted_manuscript_sha256": ACCEPTED_MANUSCRIPT_SHA256,
            "booker": BOOKER_SOURCE_URL,
            "mapping": list(SOURCE_MAPPING),
            "parameter_note": (
                "the source fixes A=64/5 but does not publish production B or eta; "
                "this artifact's B and eta are explicit project-derived choices"
            ),
        },
        "q": q,
        "conrey_number": conrey_number,
        "character_ordinal": character_ordinal,
        "parity": int(character.parity()),
        "group_exponent": int(character.group().exponent()),
        "parameters": parameters.record(),
        "frequency_start": frequency_start,
        "frequency_stop": frequency_stop,
        "precision_bits": precision_bits,
        "target_bits": target_bits,
        "decisions": DECISIONS,
    }


def produce_frequency_chunk(
    root: Path,
    *,
    q: int,
    conrey_number: int,
    frequency_start: int,
    frequency_stop: int,
    parameters: TransformParameters | None = None,
    character_ordinal: int | None = None,
    precision_bits: int = DEFAULT_PRECISION_BITS,
    target_bits: int = DEFAULT_TARGET_BITS,
) -> dict[str, object]:
    _require_flint()
    if precision_bits < target_bits + 32:
        _fail("precision_bits must exceed target_bits by at least 32")
    parameters = transform_parameters(q) if parameters is None else parameters
    if not 0 <= frequency_start < frequency_stop <= parameters.transform_length:
        _fail("invalid frequency half-open range")
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        _fail(f"chunk output directory is not empty: {root}")
    header = _chunk_header(
        q=q,
        conrey_number=conrey_number,
        character_ordinal=character_ordinal,
        parameters=parameters,
        frequency_start=frequency_start,
        frequency_stop=frequency_stop,
        precision_bits=precision_bits,
        target_bits=target_bits,
    )
    _write_atomic(root / HEADER_NAME, canonical_json_bytes(header))
    started = time.perf_counter_ns()
    lines: list[bytes] = []
    with ctx.workprec(precision_bits):
        character = _character(q, conrey_number)
        epsilon = _epsilon_phase(character)
        for index in range(frequency_start, frequency_stop):
            value = evaluate_frequency(
                q=q,
                conrey_number=conrey_number,
                parameters=parameters,
                frequency_index=index,
                target_bits=target_bits,
                _character_object=character,
                _epsilon=epsilon,
            )
            record = {
                "index": value["index"],
                "signed_index": value["signed_index"],
                "truncation": value["truncation"],
                "finite": _acb_record(value["finite"], precision_bits),
                "gaussian_tail": _arb_record(value["gaussian_tail"], precision_bits),
                "frequency_periodization": _arb_record(
                    value["frequency_periodization"], precision_bits
                ),
                "enclosure": _acb_record(value["enclosure"], precision_bits),
            }
            lines.append(canonical_json_bytes(record))
    _write_atomic(root / VALUES_NAME, b"".join(lines))
    elapsed = time.perf_counter_ns() - started
    request_hash, request_size = sha256_file(root / HEADER_NAME)
    values_hash, values_size = sha256_file(root / VALUES_NAME)
    manifest = {
        "kind": CHUNK_MANIFEST_SCHEMA,
        "algorithm_id": ALGORITHM_ID,
        "checker_id": CHECKER_ID,
        "q": q,
        "conrey_number": conrey_number,
        "frequency_start": frequency_start,
        "frequency_stop": frequency_stop,
        "frequency_count": frequency_stop - frequency_start,
        "elapsed_nanoseconds": elapsed,
        "artifacts": {
            HEADER_NAME: {"sha256": request_hash, "size_bytes": request_size},
            VALUES_NAME: {"sha256": values_hash, "size_bytes": values_size},
        },
        "decisions": DECISIONS,
    }
    _write_atomic(root / MANIFEST_NAME, canonical_json_bytes(manifest))
    return manifest


def _read_ndjson(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("rb") as source:
        for line_number, raw in enumerate(source, 1):
            if len(raw) > MAX_CONTROL_BYTES:
                _fail(f"NDJSON line {line_number} is too large")
            try:
                value = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise DirichletBookerSmallQError(
                    f"invalid NDJSON line {line_number}: {error}"
                ) from error
            if canonical_json_bytes(value) != raw or not isinstance(value, dict):
                _fail(f"noncanonical NDJSON line {line_number}")
            yield value


def _validate_manifest(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _load_canonical_json(root / MANIFEST_NAME)
    header = _load_canonical_json(root / HEADER_NAME)
    if manifest.get("kind") != CHUNK_MANIFEST_SCHEMA or header.get("kind") != CHUNK_SCHEMA:
        _fail("small-q chunk schema mismatch")
    if manifest.get("algorithm_id") != ALGORITHM_ID or header.get("algorithm_id") != ALGORITHM_ID:
        _fail("small-q algorithm mismatch")
    if manifest.get("decisions") != DECISIONS or header.get("decisions") != DECISIONS:
        _fail("small-q trust-boundary decisions differ")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {HEADER_NAME, VALUES_NAME}:
        _fail("small-q manifest artifacts differ")
    for name in (HEADER_NAME, VALUES_NAME):
        digest, size = sha256_file(root / name)
        if artifacts[name] != {"sha256": digest, "size_bytes": size}:
            _fail(f"small-q artifact hash/size mismatch: {name}")
    for key in ("q", "conrey_number", "frequency_start", "frequency_stop"):
        if manifest.get(key) != header.get(key):
            _fail(f"manifest/header {key} mismatch")
    return manifest, header


def _parameters_from_header(header: dict[str, Any]) -> TransformParameters:
    value = header.get("parameters")
    if not isinstance(value, dict):
        _fail("missing transform parameters")
    expected_keys = {
        "q", "height", "a", "b", "eta", "transform_length", "sample_step", "sample_count"
    }
    if set(value) != expected_keys:
        _fail("transform parameter keys differ")
    q = value["q"]
    if isinstance(q, bool) or not isinstance(q, int):
        _fail("parameter q is not an integer")
    parameters = transform_parameters(
        q,
        height=_fraction_from_record(value["height"], "height"),
        guard_height=Fraction(3),
        transform_length=value["transform_length"],
        eta=_fraction_from_record(value["eta"], "eta"),
    )
    # transform_parameters only uses guard_height to validate the minimum;
    # reconstruct the exact recorded B/A and then validate all identities.
    a = _fraction_from_record(value["a"], "a")
    b = _fraction_from_record(value["b"], "b")
    step = _fraction_from_record(value["sample_step"], "sample_step")
    if a != SAMPLE_RATE_A or step != 1 / a or b != Fraction(parameters.transform_length, 1) / a:
        _fail("transform rational identity mismatch")
    if value["sample_count"] != parameters.sample_count:
        _fail("sample count mismatch")
    return TransformParameters(
        q=q,
        height=parameters.height,
        a=a,
        b=b,
        eta=parameters.eta,
        transform_length=parameters.transform_length,
        sample_count=parameters.sample_count,
    )


def replay_frequency_chunk(
    root: Path, *, guard_bits: int = DEFAULT_REPLAY_GUARD_BITS
) -> dict[str, object]:
    _require_flint()
    manifest, header = _validate_manifest(root)
    precision = header.get("precision_bits")
    target_bits = header.get("target_bits")
    if isinstance(precision, bool) or not isinstance(precision, int) or precision < 64:
        _fail("invalid chunk precision")
    if isinstance(target_bits, bool) or not isinstance(target_bits, int) or target_bits < 32:
        _fail("invalid chunk target bits")
    parameters = _parameters_from_header(header)
    q = header["q"]
    conrey = header["conrey_number"]
    start = header["frequency_start"]
    stop = header["frequency_stop"]
    expected = start
    replayed_terms = 0
    with ctx.workprec(precision + guard_bits):
        character = _character(q, conrey)
        epsilon = _epsilon_phase(character)
        for record in _read_ndjson(root / VALUES_NAME):
            if record.get("index") != expected:
                _fail("frequency records are not exact contiguous coverage")
            signed = expected if expected <= parameters.transform_length // 2 else expected - parameters.transform_length
            if record.get("signed_index") != signed:
                _fail("signed frequency index mismatch")
            truncation = record.get("truncation")
            if isinstance(truncation, bool) or not isinstance(truncation, int) or truncation < 0:
                _fail("invalid Gaussian truncation")
            fresh = evaluate_frequency(
                q=q,
                conrey_number=conrey,
                parameters=parameters,
                frequency_index=expected,
                target_bits=target_bits,
                truncation=truncation,
                _character_object=character,
                _epsilon=epsilon,
            )
            stored_enclosure = _acb_from_record(record.get("enclosure"), "enclosure")
            if not stored_enclosure.contains(fresh["enclosure"]):
                _fail(f"higher-precision replay escapes stored enclosure at {expected}")
            stored_tail = _arb_from_record(record.get("gaussian_tail"), "gaussian_tail")
            stored_alias = _arb_from_record(
                record.get("frequency_periodization"), "frequency_periodization"
            )
            if not stored_tail.contains(fresh["gaussian_tail"]):
                _fail(f"Gaussian tail replay escapes at {expected}")
            if not stored_alias.contains(fresh["frequency_periodization"]):
                _fail(f"frequency-periodization replay escapes at {expected}")
            replayed_terms += truncation
            expected += 1
    if expected != stop or manifest.get("frequency_count") != stop - start:
        _fail("frequency chunk does not cover its declared half-open range")
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.replay.v1",
        "algorithm_id": ALGORITHM_ID,
        "checker_id": CHECKER_ID,
        "q": q,
        "conrey_number": conrey,
        "frequency_start": start,
        "frequency_stop": stop,
        "frequencies_replayed": stop - start,
        "finite_gaussian_terms_replayed": replayed_terms,
        "replay_precision_bits": precision + guard_bits,
        "higher_precision_containment_passed": True,
        "external_atom_discharged": False,
    }


def _load_chunk_values(root: Path) -> tuple[dict[str, Any], TransformParameters, list[Any]]:
    _, header = _validate_manifest(root)
    parameters = _parameters_from_header(header)
    values: list[Any] = []
    expected = header["frequency_start"]
    for record in _read_ndjson(root / VALUES_NAME):
        if record.get("index") != expected:
            _fail("frequency records are not contiguous")
        values.append(_acb_from_record(record.get("enclosure"), "enclosure"))
        expected += 1
    if expected != header["frequency_stop"]:
        _fail("frequency record count mismatch")
    return header, parameters, values


def assemble_character(
    output: Path,
    chunk_roots: Sequence[Path],
    *,
    sample_start: int = 0,
    sample_stop: int | None = None,
    precision_bits: int = DEFAULT_PRECISION_BITS,
    compare_direct_flint: bool = True,
) -> dict[str, object]:
    _require_flint()
    if not chunk_roots:
        _fail("at least one frequency chunk is required")
    loaded = [_load_chunk_values(path) for path in chunk_roots]
    loaded.sort(key=lambda item: item[0]["frequency_start"])
    first_header, parameters, _ = loaded[0]
    q = first_header["q"]
    conrey = first_header["conrey_number"]
    expected = 0
    frequencies: list[Any] = []
    for header, candidate_parameters, values in loaded:
        if (
            header["q"] != q
            or header["conrey_number"] != conrey
            or candidate_parameters != parameters
            or header["frequency_start"] != expected
        ):
            _fail("frequency chunks do not form one exact character transform")
        frequencies.extend(values)
        expected = header["frequency_stop"]
    if expected != parameters.transform_length:
        _fail("frequency chunks do not cover the full transform")
    sample_stop = parameters.sample_count if sample_stop is None else sample_stop
    if not 0 <= sample_start < sample_stop <= parameters.sample_count:
        _fail("invalid sample half-open range")
    character = _character(q, conrey)
    parity = character.parity()
    started = time.perf_counter_ns()
    rows: list[bytes] = []
    direct_passed = True
    with ctx.workprec(precision_bits):
        transformed = _positive_dft(frequencies)
        scale = 2 * arb.pi() / _arb_fraction(parameters.b)
        eta_ball = _arb_fraction(parameters.eta)
        for index in range(sample_start, sample_stop):
            t = Fraction(index, 1) / parameters.a
            periodized = transformed[index] * scale
            time_tail = _time_periodization_bound(
                q=q,
                parity=parity,
                eta=parameters.eta,
                t=t,
                b=parameters.b,
            )
            f_value = periodized + acb(arb(0, time_tail), arb(0, time_tail))
            untilted = f_value * (-arb.pi() * eta_ball * _arb_fraction(t) / 4).exp()
            if not untilted.imag.contains(0):
                _fail(f"completed sample is not certified real at sample {index}")
            direct_record: dict[str, object] | None = None
            if compare_direct_flint:
                t_ball = _arb_fraction(t)
                gamma_argument = acb(arb(2 * parity + 1) / 4, t_ball / 2)
                gamma_scale = abs(
                    (-gamma_argument * arb.pi().log()).exp()
                    * gamma_argument.gamma()
                )
                direct_value = character.hardy_z(t_ball) * gamma_scale
                direct = direct_value.real if isinstance(direct_value, acb) else direct_value
                contained = untilted.real.contains(direct)
                direct_passed &= contained
                if not contained:
                    _fail(f"DFT enclosure misses direct FLINT value at sample {index}")
                direct_record = _arb_record(direct, precision_bits)
            row = {
                "index": index,
                "t": _fraction_record(t),
                "time_periodization": _arb_record(time_tail, precision_bits),
                "completed_real": _arb_record(untilted.real, precision_bits),
                "completed_imaginary": _arb_record(untilted.imag, precision_bits),
                "direct_flint_completed_real": direct_record,
            }
            rows.append(canonical_json_bytes(row))
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(output, b"".join(rows))
    elapsed = time.perf_counter_ns() - started
    digest, size = sha256_file(output)
    return {
        "kind": SAMPLES_SCHEMA,
        "algorithm_id": ALGORITHM_ID,
        "q": q,
        "conrey_number": conrey,
        "sample_start": sample_start,
        "sample_stop": sample_stop,
        "sample_count": sample_stop - sample_start,
        "sample_step": _fraction_record(SAMPLE_STEP),
        "transform_length": parameters.transform_length,
        "elapsed_nanoseconds": elapsed,
        "samples": {"path": str(output), "sha256": digest, "size_bytes": size},
        "direct_flint_comparison_passed": direct_passed if compare_direct_flint else None,
        "decisions": DECISIONS,
    }


def source_campaign_plan(
    *,
    q_start: int = SOURCE_Q_START,
    q_stop: int = SOURCE_Q_STOP,
    frequency_chunk_size: int = DEFAULT_FREQUENCY_CHUNK_SIZE,
    include_moduli: bool = True,
) -> dict[str, object]:
    if not SOURCE_Q_START <= q_start <= q_stop <= SOURCE_Q_STOP:
        _fail("source plan range must lie in 2..10000")
    if frequency_chunk_size <= 0:
        _fail("frequency_chunk_size must be positive")
    total_characters = 0
    total_frequency_values = 0
    total_lattice_values = 0
    total_chunks = 0
    total_radix2_butterflies = 0
    estimated_terms = 0
    moduli: list[dict[str, object]] = []
    for q in range(q_start, q_stop + 1):
        count = primitive_character_count(q)
        parameters = transform_parameters(q)
        chunks_per_character = (
            parameters.transform_length + frequency_chunk_size - 1
        ) // frequency_chunk_size
        # A transparent planning estimate, not a proof or measured ETA.  The
        # x=0 truncation is integrated against its exp(-x) asymptotic over the
        # nonnegative half-grid; retained artifacts record exact term counts.
        one_minus_eta = float(1 - parameters.eta)
        decay0_lower = math.pi * one_minus_eta / q
        m0 = math.ceil(
            math.sqrt((DEFAULT_TARGET_BITS + 32) * math.log(2) / decay0_lower)
        )
        b_float = float(parameters.b)
        per_character_terms = math.ceil(m0 * b_float / math.pi)
        total_characters += count
        total_frequency_values += count * parameters.transform_length
        total_lattice_values += count * parameters.sample_count
        total_chunks += count * chunks_per_character
        total_radix2_butterflies += (
            count
            * (parameters.transform_length // 2)
            * (parameters.transform_length.bit_length() - 1)
        )
        estimated_terms += count * per_character_terms
        if include_moduli:
            moduli.append(
                {
                    "q": q,
                    "primitive_characters": count,
                    "parameters": parameters.record(),
                    "frequency_chunks_per_character": chunks_per_character,
                    "estimated_finite_gaussian_terms_per_character": per_character_terms,
                }
            )
    return {
        "kind": PLAN_SCHEMA,
        "algorithm_id": ALGORITHM_ID,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "q_start": q_start,
        "q_stop": q_stop,
        "frequency_chunk_size": frequency_chunk_size,
        "total_primitive_characters": total_characters,
        "total_frequency_values": total_frequency_values,
        "total_5_over_64_lattice_values": total_lattice_values,
        "total_frequency_chunks": total_chunks,
        "total_positive_sign_radix2_butterflies": total_radix2_butterflies,
        "planning_estimated_finite_gaussian_terms": estimated_terms,
        "planning_estimate_is_not_a_runtime_measurement": True,
        "moduli": moduli,
        "source_mapping": list(SOURCE_MAPPING),
        "source_parameter_status": {
            "a_equals_64_over_5_published": True,
            "production_b_published": False,
            "production_eta_published": False,
            "b_eta_selection_project_derived_and_recorded": True,
        },
        "decisions": DECISIONS,
    }


def source_chunk_request(
    *,
    q: int,
    character_ordinal: int,
    frequency_chunk_index: int,
    frequency_chunk_size: int = DEFAULT_FREQUENCY_CHUNK_SIZE,
) -> dict[str, object]:
    count = primitive_character_count(q)
    if not 0 <= character_ordinal < count:
        _fail("character ordinal is outside the primitive-character range")
    if frequency_chunk_index < 0 or frequency_chunk_size <= 0:
        _fail("invalid frequency chunk index/size")
    descriptor = primitive_character_descriptor(q, character_ordinal)
    parameters = transform_parameters(q)
    start = frequency_chunk_index * frequency_chunk_size
    stop = min(start + frequency_chunk_size, parameters.transform_length)
    if start >= stop:
        _fail("frequency chunk is outside the character transform")
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.chunk_request.v1",
        "algorithm_id": ALGORITHM_ID,
        "q": q,
        "character_ordinal": character_ordinal,
        "conrey_number": descriptor["conrey_number"],
        "parity": descriptor["parity"],
        "frequency_chunk_index": frequency_chunk_index,
        "frequency_start": start,
        "frequency_stop": stop,
        "parameters": parameters.record(),
    }


def write_gpu_proposal_input(
    path: Path,
    *,
    q: int,
    conrey_number: int,
    parameters: TransformParameters,
    frequency_start: int,
    frequency_stop: int,
    target_bits: int = DEFAULT_TARGET_BITS,
    precision_bits: int = DEFAULT_PRECISION_BITS,
) -> dict[str, object]:
    """Write finite-sum work for the explicitly untrusted CUDA accelerator."""

    _require_flint()
    if parameters.q != q:
        _fail("GPU proposal parameter modulus mismatch")
    if not 0 <= frequency_start < frequency_stop <= parameters.transform_length:
        _fail("invalid GPU proposal frequency range")
    character = _character(q, conrey_number)
    exponent = int(character.group().exponent())
    parity = int(character.parity())
    requests: list[bytes] = []
    total_terms = 0
    with ctx.workprec(precision_bits):
        epsilon = _epsilon_phase(character)
        for index in range(frequency_start, frequency_stop):
            signed = index if index <= parameters.transform_length // 2 else index - parameters.transform_length
            x = 2 * arb.pi() * abs(signed) / _arb_fraction(parameters.b)
            truncation, _ = _choose_truncation(
                q=q,
                parity=parity,
                eta=parameters.eta,
                x=x,
                target_bits=target_bits,
            )
            if truncation >= GPU_NONUNIT_EXPONENT:
                _fail("GPU proposal truncation exceeds uint32")
            requests.append(
                GPU_FREQUENCY_REQUEST.pack(index, signed, truncation, 0)
            )
            total_terms += truncation
        exponents = []
        for residue in range(q):
            value = character.chi_exponent(residue)
            exponents.append(
                GPU_NONUNIT_EXPONENT if value is None else int(value)
            )
        header = GPU_INPUT_HEADER.pack(
            GPU_INPUT_MAGIC,
            GPU_FORMAT_VERSION,
            q,
            exponent,
            parity,
            parameters.transform_length,
            frequency_start,
            frequency_stop - frequency_start,
            float(parameters.eta),
            float(parameters.b),
            float(epsilon.real.mid()),
            float(epsilon.imag.mid()),
            0,
        )
    raw = header + struct.pack(f"<{q}I", *exponents) + b"".join(requests)
    _write_atomic(path, raw)
    digest, size = sha256_file(path)
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.gpu_input.v1",
        "algorithm": "platt-booker-smallq-gaussian-gpu-proposal-v1",
        "trusted_certificate": False,
        "q": q,
        "conrey_number": conrey_number,
        "frequency_start": frequency_start,
        "frequency_stop": frequency_stop,
        "frequency_count": frequency_stop - frequency_start,
        "finite_gaussian_terms": total_terms,
        "path": str(path),
        "sha256": digest,
        "size_bytes": size,
    }


def inspect_gpu_proposal(
    input_path: Path,
    output_path: Path,
    *,
    conrey_number: int,
    parameters: TransformParameters,
    precision_bits: int = DEFAULT_PRECISION_BITS,
) -> dict[str, object]:
    """Recompute GPU finite sums with Arb and report midpoint disagreement.

    The returned comparison is diagnostic.  Certified artifacts always retain
    Arb's fresh enclosure and analytic tails, never the CUDA midpoint.
    """

    _require_flint()
    input_raw = input_path.read_bytes()
    if len(input_raw) < GPU_INPUT_HEADER.size:
        _fail("truncated GPU proposal input")
    (
        magic,
        version,
        q,
        group_exponent,
        parity,
        transform_length,
        frequency_start,
        frequency_count,
        eta_float,
        b_float,
        epsilon_real,
        epsilon_imag,
        reserved,
    ) = GPU_INPUT_HEADER.unpack_from(input_raw)
    expected_size = (
        GPU_INPUT_HEADER.size
        + q * 4
        + frequency_count * GPU_FREQUENCY_REQUEST.size
    )
    if (
        magic != GPU_INPUT_MAGIC
        or version != GPU_FORMAT_VERSION
        or reserved
        or q != parameters.q
        or transform_length != parameters.transform_length
        or len(input_raw) != expected_size
        or float(parameters.eta) != eta_float
        or float(parameters.b) != b_float
    ):
        _fail("GPU proposal input identity/size mismatch")
    character = _character(q, conrey_number)
    if group_exponent != int(character.group().exponent()) or parity != int(character.parity()):
        _fail("GPU proposal character identity mismatch")
    exponent_offset = GPU_INPUT_HEADER.size
    stored_exponents = struct.unpack_from(f"<{q}I", input_raw, exponent_offset)
    for residue, stored in enumerate(stored_exponents):
        fresh = character.chi_exponent(residue)
        expected = GPU_NONUNIT_EXPONENT if fresh is None else int(fresh)
        if stored != expected:
            _fail("GPU proposal character table mismatch")
    with ctx.workprec(precision_bits):
        epsilon = _epsilon_phase(character)
        # The phase is a proposal input, but reject changes larger than one
        # binary64 ulp so a benchmark cannot silently change the character.
        if abs(float(epsilon.real.mid()) - epsilon_real) > math.ulp(epsilon_real):
            _fail("GPU proposal epsilon real component mismatch")
        if abs(float(epsilon.imag.mid()) - epsilon_imag) > math.ulp(epsilon_imag):
            _fail("GPU proposal epsilon imaginary component mismatch")

    output_raw = output_path.read_bytes()
    if len(output_raw) < GPU_OUTPUT_HEADER.size:
        _fail("truncated GPU proposal output")
    (
        output_magic,
        output_version,
        output_q,
        output_start,
        output_count,
        elapsed_ns,
        output_reserved,
    ) = GPU_OUTPUT_HEADER.unpack_from(output_raw)
    if (
        output_magic != GPU_OUTPUT_MAGIC
        or output_version != GPU_FORMAT_VERSION
        or output_q != q
        or output_start != frequency_start
        or output_count != frequency_count
        or output_reserved
        or len(output_raw) != GPU_OUTPUT_HEADER.size + output_count * GPU_OUTPUT_ITEM.size
    ):
        _fail("GPU proposal output identity/size mismatch")
    request_offset = exponent_offset + q * 4
    maximum_absolute_error = 0.0
    maximum_relative_error = 0.0
    total_terms = 0
    with ctx.workprec(precision_bits):
        cached_character = _character(q, conrey_number)
        cached_epsilon = _epsilon_phase(cached_character)
        for local in range(frequency_count):
            index, signed, truncation, request_reserved = GPU_FREQUENCY_REQUEST.unpack_from(
                input_raw, request_offset + local * GPU_FREQUENCY_REQUEST.size
            )
            out_index, real, imag, status, item_reserved = GPU_OUTPUT_ITEM.unpack_from(
                output_raw, GPU_OUTPUT_HEADER.size + local * GPU_OUTPUT_ITEM.size
            )
            if (
                index != frequency_start + local
                or out_index != index
                or request_reserved
                or item_reserved
                or status
                or not math.isfinite(real)
                or not math.isfinite(imag)
            ):
                _fail("GPU proposal request/output item failed validation")
            expected_signed = index if index <= transform_length // 2 else index - transform_length
            if signed != expected_signed:
                _fail("GPU proposal signed index mismatch")
            fresh = evaluate_frequency(
                q=q,
                conrey_number=conrey_number,
                parameters=parameters,
                frequency_index=index,
                truncation=truncation,
                _character_object=cached_character,
                _epsilon=cached_epsilon,
            )["finite"]
            expected_real = float(fresh.real.mid())
            expected_imag = float(fresh.imag.mid())
            error = math.hypot(real - expected_real, imag - expected_imag)
            magnitude = math.hypot(expected_real, expected_imag)
            maximum_absolute_error = max(maximum_absolute_error, error)
            maximum_relative_error = max(
                maximum_relative_error, error / max(magnitude, 1e-300)
            )
            total_terms += truncation
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.gpu_comparison.v1",
        "algorithm": "platt-booker-smallq-gaussian-gpu-proposal-v1",
        "q": q,
        "conrey_number": conrey_number,
        "frequency_count": frequency_count,
        "finite_gaussian_terms": total_terms,
        "elapsed_nanoseconds": elapsed_ns,
        "frequencies_per_second": frequency_count * 1_000_000_000 // max(elapsed_ns, 1),
        "gaussian_terms_per_second": total_terms * 1_000_000_000 // max(elapsed_ns, 1),
        "maximum_absolute_midpoint_error": maximum_absolute_error,
        "maximum_relative_midpoint_error": maximum_relative_error,
        "arb_enclosures_recomputed": True,
        "gpu_values_retained_as_certificates": False,
        "trusted_certificate": False,
    }


def capability() -> dict[str, object]:
    pinned = False
    if FLINT_IMPORT_ERROR is None:
        pinned = (
            str(flint.__version__) == EXPECTED_PYTHON_FLINT
            and str(flint.__FLINT_VERSION__) == EXPECTED_FLINT
            and int(flint.__FLINT_RELEASE__) == EXPECTED_FLINT_RELEASE
        )
    return {
        "kind": CAPABILITY_SCHEMA,
        "algorithm_id": ALGORITHM_ID,
        "checker_id": CHECKER_ID,
        "source_domain": {"q_start": SOURCE_Q_START, "q_stop": SOURCE_Q_STOP},
        "sample_step": _fraction_record(SAMPLE_STEP),
        "pinned_flint_available": pinned,
        "pinned_runtime": {
            "python_flint": EXPECTED_PYTHON_FLINT,
            "flint": EXPECTED_FLINT,
            "flint_release": EXPECTED_FLINT_RELEASE,
        },
        "frequency_chunks_independently_replayable": True,
        "full_source_plan_available": True,
        "source_parameter_status": {
            "a_equals_64_over_5_published": True,
            "production_b_published": False,
            "production_eta_published": False,
            "b_eta_selection_project_derived_and_recorded": True,
        },
        "production_source_run_completed": False,
        "production_ready": False,
        "external_atom_discharged": False,
        "remaining_after_this_stage": [
            "rigorous upsampling",
            "exception resolution",
            "zero isolation with multiplicity",
            "Turing completeness",
            "Lean analytic realization",
        ],
        "decisions": DECISIONS,
    }


def known_answer_case(
    root: Path,
    *,
    q: int,
    conrey_number: int,
    transform_length: int = 128,
    sample_stop: int = 5,
    precision_bits: int = 160,
) -> dict[str, object]:
    parameters = transform_parameters(
        q,
        height=Fraction(1),
        guard_height=Fraction(4),
        transform_length=transform_length,
        eta=Fraction(0),
    )
    chunk = root / f"q{q}-chi{conrey_number}"
    produce_frequency_chunk(
        chunk,
        q=q,
        conrey_number=conrey_number,
        frequency_start=0,
        frequency_stop=transform_length,
        parameters=parameters,
        precision_bits=precision_bits,
        target_bits=96,
    )
    replay = replay_frequency_chunk(chunk, guard_bits=64)
    samples = assemble_character(
        chunk / SAMPLES_NAME,
        [chunk],
        sample_start=0,
        sample_stop=sample_stop,
        precision_bits=precision_bits + 32,
        compare_direct_flint=True,
    )
    return {"replay": replay, "samples": samples}


def benchmark(
    *, q: int = 5, conrey_number: int = 2, frequency_count: int = 256
) -> dict[str, object]:
    length = _next_power_of_two(max(frequency_count, 128))
    parameters = transform_parameters(
        q,
        height=Fraction(1),
        guard_height=Fraction(4),
        transform_length=length,
        eta=Fraction(0),
    )
    stop = min(frequency_count, length)
    terms = 0
    started = time.perf_counter_ns()
    with ctx.workprec(DEFAULT_PRECISION_BITS):
        character = _character(q, conrey_number)
        epsilon = _epsilon_phase(character)
        for index in range(stop):
            result = evaluate_frequency(
                q=q,
                conrey_number=conrey_number,
                parameters=parameters,
                frequency_index=index,
                _character_object=character,
                _epsilon=epsilon,
            )
            terms += result["truncation"]
    elapsed = time.perf_counter_ns() - started
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.benchmark.v1",
        "q": q,
        "conrey_number": conrey_number,
        "frequency_count": stop,
        "finite_gaussian_terms": terms,
        "elapsed_nanoseconds": elapsed,
        "frequencies_per_second": stop * 1_000_000_000 // max(elapsed, 1),
        "gaussian_terms_per_second": terms * 1_000_000_000 // max(elapsed, 1),
        "scope": "local pinned-Arb reference; not a source-run or H100 rate",
    }
