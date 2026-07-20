#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Slow rigorous FLINT/Arb reference backend for the Dirichlet-GRH campaign.

This is deliberately a reference implementation, not Platt's fast lattice/FFT
engine.  For each primitive nonprincipal character it:

* certifies the winding number of ``L(s, chi)`` on the rectangle
  ``[-1/2,3/2] x [-T,T]`` by adaptive Arb box evaluation;
* subtracts the single simple zero at ``s=0`` for even characters; and
* compares the resulting multiplicity-counted nontrivial-zero total with
  disjoint strict sign changes of FLINT's real Hardy Z function.

Every contour box must map into a strict open half-plane.  Ambiguity triggers
precision increase or subdivision and ultimately fails closed.  No numeric
Turing estimate is used.  The method is far too slow for the published range,
but the same streaming code accepts every canonical source task.

When copied by ``tg_dirichlet_campaign.py``, the staged basename ``producer``
or ``checker`` selects the corresponding executable protocol.  The checker
recomputes the complete NDJSON certificate.  Using this one file for both
roles is not independent verification; the campaign records that fact.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Iterator, NoReturn


EXPECTED_PYTHON_FLINT = "0.9.0"
EXPECTED_FLINT = "3.6.0"
EXPECTED_FLINT_RELEASE = 30_600

PRODUCER_PROTOCOL = "sparkinterval.dirichlet-grh-producer.v1"
CHECKER_PROTOCOL = "sparkinterval.dirichlet-grh-checker.v1"
REQUEST_SCHEMA = "sparkinterval.tg.dirichlet_campaign.request.v1"
RESULT_SCHEMA = "sparkinterval.tg.dirichlet_campaign.external_result.v1"
RECEIPT_SCHEMA = "sparkinterval.tg.dirichlet_campaign.external_checker_receipt.v2"
CERTIFICATE_SCHEMA = "sparkinterval.tg.dirichlet_flint_argument_certificate.v1"
SUMMARY_SCHEMA = "sparkinterval.tg.dirichlet_flint_argument_character.v1"
ALGORITHM_ID = "flint-dirichlet-l-box-winding-plus-hardy-z-signs-v1"
CERTIFICATE_NAME = "flint-reference-certificate.ndjson"
MAX_CONTROL_BYTES = 32 * 1024 * 1024


class FlintReferenceError(RuntimeError):
    """The rigorous reference computation could not certify its claim."""


class ResolutionError(FlintReferenceError):
    """The current Arb precision/subdivision could not resolve a decision."""


def _fail(message: str) -> NoReturn:
    raise FlintReferenceError(message)


try:
    import flint
    from flint import acb, arb, ctx, dirichlet_char
except ImportError as error:  # pragma: no cover - exercised by CLI environments
    flint = None
    acb = arb = ctx = dirichlet_char = None
    FLINT_IMPORT_ERROR = error
else:
    FLINT_IMPORT_ERROR = None


def _require_flint() -> None:
    if FLINT_IMPORT_ERROR is not None:
        _fail(
            "python-flint is required; install requirements-tg-flint.txt "
            f"({FLINT_IMPORT_ERROR})"
        )
    versions = (
        flint.__version__,
        flint.__FLINT_VERSION__,
        flint.__FLINT_RELEASE__,
    )
    expected = (
        EXPECTED_PYTHON_FLINT,
        EXPECTED_FLINT,
        EXPECTED_FLINT_RELEASE,
    )
    if versions != expected:
        _fail(f"version mismatch: found {versions}, required {expected}")


def version_record() -> dict[str, object]:
    _require_flint()
    return {
        "python_flint": flint.__version__,
        "flint": flint.__FLINT_VERSION__,
        "flint_release": flint.__FLINT_RELEASE__,
    }


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def _reject_float(value: str) -> NoReturn:
    _fail(f"JSON floating-point values are forbidden: {value}")


def _reject_constant(value: str) -> NoReturn:
    _fail(f"non-finite JSON value is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_canonical_json(path: Path) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise FlintReferenceError(f"cannot read {path}: {error}") from error
    if len(raw) > MAX_CONTROL_BYTES:
        _fail(f"control JSON exceeds {MAX_CONTROL_BYTES} bytes: {path}")
    try:
        value = json.loads(
            raw,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FlintReferenceError(f"invalid JSON in {path}: {error}") from error
    if canonical_json_bytes(value) != raw:
        _fail(f"noncanonical JSON: {path}")
    return value


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as source:
            while block := source.read(1024 * 1024):
                digest.update(block)
                size += len(block)
    except OSError as error:
        raise FlintReferenceError(f"cannot hash {path}: {error}") from error
    return digest.hexdigest(), size


def _integer(name: str, value: object, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        _fail(f"{name} must be at least {minimum}")
    return value


def _fraction(name: str, value: object) -> Fraction:
    if not isinstance(value, dict) or set(value) != {"numerator", "denominator"}:
        _fail(f"{name} must be a canonical rational object")
    numerator = _integer(f"{name}.numerator", value["numerator"])
    denominator = _integer(f"{name}.denominator", value["denominator"], minimum=1)
    result = Fraction(numerator, denominator)
    if (result.numerator, result.denominator) != (numerator, denominator):
        _fail(f"{name} is not in lowest terms")
    return result


def _fraction_json(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _source_height(q: int) -> Fraction:
    additive = 75_000_000 if q % 2 == 0 else 37_500_000
    return Fraction(max(100_000_000, 200 * q + additive), q)


def _environment_integer(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise FlintReferenceError(f"{name} must be an integer") from error
    if value < minimum:
        _fail(f"{name} must be at least {minimum}")
    return value


def configuration() -> dict[str, int]:
    initial = _environment_integer("TG_DIRICHLET_FLINT_INITIAL_PRECISION", 128, 64)
    maximum = _environment_integer("TG_DIRICHLET_FLINT_MAX_PRECISION", 4096, initial)
    return {
        "initial_precision_bits": initial,
        "maximum_precision_bits": maximum,
        "maximum_contour_depth": _environment_integer(
            "TG_DIRICHLET_FLINT_MAX_CONTOUR_DEPTH", 64, 1
        ),
        "maximum_contour_evaluations": _environment_integer(
            "TG_DIRICHLET_FLINT_MAX_CONTOUR_EVALUATIONS", 10_000_000, 0
        ),
        "maximum_grid_refinements": _environment_integer(
            "TG_DIRICHLET_FLINT_MAX_GRID_REFINEMENTS", 20, 0
        ),
        "hardy_step_numerator": 5,
        "hardy_step_denominator": 64,
    }


def _arb_fraction(value: Fraction):
    return arb(f"{value.numerator}/{value.denominator}")


def _complex_point(point: tuple[Fraction, Fraction]):
    return acb(_arb_fraction(point[0]), _arb_fraction(point[1]))


def _segment_box(
    start: tuple[Fraction, Fraction], stop: tuple[Fraction, Fraction]
):
    real_mid = (start[0] + stop[0]) / 2
    real_radius = abs(start[0] - stop[0]) / 2
    imag_mid = (start[1] + stop[1]) / 2
    imag_radius = abs(start[1] - stop[1]) / 2
    return acb(
        arb(
            f"{real_mid.numerator}/{real_mid.denominator}",
            f"{real_radius.numerator}/{real_radius.denominator}",
        ),
        arb(
            f"{imag_mid.numerator}/{imag_mid.denominator}",
            f"{imag_radius.numerator}/{imag_radius.denominator}",
        ),
    )


def _half_plane(value: Any) -> str | None:
    if not value.is_finite():
        return None
    if value.real > 0:
        return "right"
    if value.imag > 0:
        return "upper"
    if value.real < 0:
        return "left"
    if value.imag < 0:
        return "lower"
    return None


def _sector(value: Any) -> int | None:
    """Certified octant/axis label, counterclockwise from the positive axis."""

    if not value.is_finite():
        return None
    real = value.real
    imag = value.imag
    if real > 0 and imag.is_zero():
        return 0
    if real > 0 and imag > 0:
        return 1
    if real.is_zero() and imag > 0:
        return 2
    if real < 0 and imag > 0:
        return 3
    if real < 0 and imag.is_zero():
        return 4
    if real < 0 and imag < 0:
        return 5
    if real.is_zero() and imag < 0:
        return 6
    if real > 0 and imag < 0:
        return 7
    return None


_ALLOWED_SECTORS = {
    "right": {7, 0, 1},
    "upper": {1, 2, 3},
    "left": {3, 4, 5},
    "lower": {5, 6, 7},
}


class _ContourAttempt:
    def __init__(self, character: Any, max_depth: int, max_evaluations: int):
        self.character = character
        self.max_depth = max_depth
        self.max_evaluations = max_evaluations
        self.point_cache: dict[tuple[Fraction, Fraction], Any] = {}
        self.box_evaluations = 0
        self.point_evaluations = 0
        self.edges = 0
        self.sector_delta = 0

    def _check_budget(self) -> None:
        if self.max_evaluations and (
            self.box_evaluations + self.point_evaluations >= self.max_evaluations
        ):
            raise ResolutionError("contour evaluation budget exhausted")

    def point_value(self, point: tuple[Fraction, Fraction]):
        if point not in self.point_cache:
            self._check_budget()
            self.point_cache[point] = self.character.l_function(
                _complex_point(point)
            )
            self.point_evaluations += 1
        return self.point_cache[point]

    def visit(
        self,
        start: tuple[Fraction, Fraction],
        stop: tuple[Fraction, Fraction],
        depth: int,
    ) -> None:
        self._check_budget()
        image = self.character.l_function(_segment_box(start, stop))
        self.box_evaluations += 1
        half_plane = _half_plane(image)
        start_sector = _sector(self.point_value(start))
        stop_sector = _sector(self.point_value(stop))
        if (
            half_plane is not None
            and start_sector in _ALLOWED_SECTORS[half_plane]
            and stop_sector in _ALLOWED_SECTORS[half_plane]
        ):
            delta = stop_sector - start_sector
            if delta <= -4:
                delta += 8
            if delta >= 4:
                delta -= 8
            if not -4 < delta < 4:
                raise ResolutionError("half-plane sector lift is ambiguous")
            self.edges += 1
            self.sector_delta += delta
            return
        if depth >= self.max_depth:
            raise ResolutionError(
                "contour segment did not map into a certified open half-plane"
            )
        midpoint = (
            (start[0] + stop[0]) / 2,
            (start[1] + stop[1]) / 2,
        )
        self.visit(start, midpoint, depth + 1)
        self.visit(midpoint, stop, depth + 1)


def _winding_at_precision(
    character: Any, height: Fraction, precision: int, config: dict[str, int]
) -> dict[str, int]:
    ctx.prec = precision
    attempt = _ContourAttempt(
        character,
        config["maximum_contour_depth"],
        config["maximum_contour_evaluations"],
    )
    left = Fraction(-1, 2)
    right = Fraction(3, 2)
    vertices = (
        (left, -height),
        (right, -height),
        (right, height),
        (left, height),
        (left, -height),
    )
    for start, stop in zip(vertices, vertices[1:]):
        attempt.visit(start, stop, 0)
    if attempt.sector_delta % 8 != 0:
        raise ResolutionError("certified contour sector sum is not a full turn")
    winding = attempt.sector_delta // 8
    if winding < 0:
        raise ResolutionError("counterclockwise contour returned negative winding")
    return {
        "zero_count_with_trivial_zeros": winding,
        "precision_bits": precision,
        "certified_half_plane_edges": attempt.edges,
        "contour_box_evaluations": attempt.box_evaluations,
        "contour_point_evaluations": attempt.point_evaluations,
    }


def certified_winding_count(
    character: Any, height: Fraction, config: dict[str, int]
) -> dict[str, int]:
    precision = config["initial_precision_bits"]
    last_error: Exception | None = None
    while precision <= config["maximum_precision_bits"]:
        try:
            return _winding_at_precision(character, height, precision, config)
        except ResolutionError as error:
            last_error = error
            precision *= 2
    raise ResolutionError(
        "contour certification failed through maximum precision: "
        f"{last_error}"
    )


def _hardy_sign(character: Any, ordinate: Fraction, config: dict[str, int]) -> tuple[int, int]:
    precision = config["initial_precision_bits"]
    while precision <= config["maximum_precision_bits"]:
        ctx.prec = precision
        value = character.hardy_z(_arb_fraction(ordinate))
        if value.is_finite() and value.imag.contains(0):
            if value.real > 0:
                return 1, precision
            if value.real < 0:
                return -1, precision
        precision *= 2
    raise ResolutionError(
        f"Hardy Z sign unresolved at {ordinate.numerator}/{ordinate.denominator}"
    )


def _grid_points(height: Fraction, step: Fraction) -> Iterator[Fraction]:
    yield -height
    # A one-third offset avoids systematically sampling the symmetry point and
    # still leaves gaps no larger than the requested step.
    point = -height + step / 3
    while point < height:
        yield point
        point += step
    yield height


def _scan_hardy_sign_changes(
    character: Any,
    height: Fraction,
    step: Fraction,
    config: dict[str, int],
) -> dict[str, object]:
    digest = hashlib.sha256()
    previous_point: Fraction | None = None
    previous_sign: int | None = None
    samples = 0
    brackets = 0
    maximum_precision = 0
    for point in _grid_points(height, step):
        sign, precision = _hardy_sign(character, point, config)
        maximum_precision = max(maximum_precision, precision)
        samples += 1
        if previous_point is not None and previous_sign != sign:
            brackets += 1
            digest.update(
                (
                    f"{previous_point.numerator}/{previous_point.denominator}:"
                    f"{point.numerator}/{point.denominator}:"
                    f"{previous_sign}:{sign}\n"
                ).encode("ascii")
            )
        previous_point = point
        previous_sign = sign
    return {
        "strict_sign_change_brackets": brackets,
        "bracket_digest_sha256": digest.hexdigest(),
        "samples": samples,
        "maximum_precision_bits": maximum_precision,
        "step": _fraction_json(step),
    }


def certified_hardy_count(
    character: Any,
    height: Fraction,
    required_count: int,
    config: dict[str, int],
) -> dict[str, object]:
    if required_count == 0:
        return {
            "strict_sign_change_brackets": 0,
            "bracket_digest_sha256": hashlib.sha256().hexdigest(),
            "samples": 0,
            "maximum_precision_bits": 0,
            "step": _fraction_json(Fraction(5, 64)),
            "grid_refinement": 0,
        }
    base_step = Fraction(
        config["hardy_step_numerator"], config["hardy_step_denominator"]
    )
    for refinement in range(config["maximum_grid_refinements"] + 1):
        result = _scan_hardy_sign_changes(
            character, height, base_step / (1 << refinement), config
        )
        found = result["strict_sign_change_brackets"]
        if found == required_count:
            result["grid_refinement"] = refinement
            return result
        if found > required_count:
            _fail(
                "Hardy sign-change count exceeds the argument-principle count"
            )
    raise ResolutionError(
        "Hardy grid did not find the multiplicity-counted contour total"
    )


def verify_character(
    q: int,
    conrey_number: int,
    height: Fraction,
    config: dict[str, int] | None = None,
) -> dict[str, object]:
    """Certify one primitive nonprincipal character through ``height``."""

    _require_flint()
    if q < 2:
        _fail("q=1 is the separate Riemann-zeta prerequisite")
    if height <= 0:
        _fail("height must be positive")
    config = configuration() if config is None else config
    character = dirichlet_char(q, conrey_number)
    if character.number() != conrey_number:
        _fail("FLINT changed the requested Conrey number")
    if not character.is_primitive() or character.conductor() != q:
        _fail("requested FLINT character is not primitive of conductor q")
    if character.is_principal():
        _fail("the Dirichlet backend does not accept a principal character")

    parity = int(character.parity())
    # Prove a slightly stronger closed-height statement so that a zero exactly
    # at the source cutoff is in the interior, never silently placed on the
    # argument-principle contour.
    verification_height = height + Fraction(1, 64)
    contour = certified_winding_count(character, verification_height, config)
    # For a primitive nonprincipal character, the only trivial zero in
    # -1/2 <= Re(s) <= 3/2 is the simple zero at s=0 when chi is even.
    trivial_zeros = 1 if parity == 0 else 0
    nontrivial_count = contour["zero_count_with_trivial_zeros"] - trivial_zeros
    if nontrivial_count < 0:
        _fail("argument-principle count is smaller than the known trivial count")
    hardy = certified_hardy_count(
        character, verification_height, nontrivial_count, config
    )
    if hardy["strict_sign_change_brackets"] != nontrivial_count:
        _fail("critical-line bracket count does not equal the contour count")
    return {
        "kind": SUMMARY_SCHEMA,
        "q": q,
        "conrey_number": conrey_number,
        "parity": parity,
        "absolute_height": _fraction_json(height),
        "stronger_certified_height": _fraction_json(verification_height),
        "contour": contour,
        "known_trivial_zeros_in_contour": trivial_zeros,
        "multiplicity_counted_nontrivial_zeros": nontrivial_count,
        "hardy_z": hardy,
        "all_nontrivial_zeros_on_critical_line": True,
    }


def _unrank_local(model: dict[str, Any], ordinal: int) -> tuple[int, ...]:
    prime = _integer("local prime", model.get("prime"), minimum=2)
    exponent = _integer("local exponent", model.get("exponent"), minimum=1)
    count = _integer("local primitive count", model.get("primitive_count"), minimum=1)
    if not 0 <= ordinal < count:
        _fail("local character ordinal is out of range")
    if prime != 2:
        if exponent == 1:
            return (ordinal + 1,)
        block, offset = divmod(ordinal, prime - 1)
        return (block * prime + offset + 1,)
    if exponent == 2:
        return (1,)
    per_sign = 1 << (exponent - 3)
    sign, cyclic = divmod(ordinal, per_sign)
    return sign, 2 * cyclic + 1


def _crt_pair(value: int, modulus: int, residue: int, local_modulus: int) -> tuple[int, int]:
    step = ((residue - value) * pow(modulus, -1, local_modulus)) % local_modulus
    return (value + modulus * step) % (modulus * local_modulus), modulus * local_modulus


def _conrey_from_segment(segment: dict[str, Any], ordinal: int) -> tuple[int, int]:
    models = segment.get("local_models")
    if not isinstance(models, list) or not models:
        _fail("Dirichlet source task must contain local character models")
    radices = [
        _integer("local primitive count", model.get("primitive_count"), minimum=1)
        for model in models
    ]
    local_ordinals = [0] * len(radices)
    remainder = ordinal
    for index in range(len(radices) - 1, -1, -1):
        remainder, local_ordinals[index] = divmod(remainder, radices[index])
    if remainder:
        _fail("character ordinal exceeds the local mixed-radix product")
    value = 0
    modulus = 1
    parity = 0
    for model, local_ordinal in zip(models, local_ordinals):
        prime = model["prime"]
        exponent = model["exponent"]
        local_modulus = prime**exponent
        if model.get("modulus") != local_modulus:
            _fail("local model modulus mismatch")
        generators = model.get("generators")
        if not isinstance(generators, list):
            _fail("local model generators must be a list")
        exponents = _unrank_local(model, local_ordinal)
        if len(generators) != len(exponents):
            _fail("local generator/exponent arity mismatch")
        local_number = 1
        for generator, char_exponent in zip(generators, exponents):
            local_number = (
                local_number * pow(generator, char_exponent, local_modulus)
            ) % local_modulus
        value, modulus = _crt_pair(value, modulus, local_number, local_modulus)
        parity ^= exponents[0] & 1
    if modulus != segment["q"]:
        _fail("CRT local models do not multiply to q")
    return value, parity


def _request_rows(request: dict[str, Any]) -> Iterator[tuple[int, int, int, Fraction]]:
    if request.get("kind") != REQUEST_SCHEMA or request.get("schema_version") != 1:
        _fail("unsupported campaign request schema")
    segments = request.get("segments")
    if not isinstance(segments, list) or len(segments) != request.get("segment_count"):
        _fail("request segment count mismatch")
    emitted = 0
    for segment in segments:
        if not isinstance(segment, dict):
            _fail("request segment must be an object")
        q = _integer("segment.q", segment.get("q"), minimum=2)
        height = _fraction("segment.absolute_height", segment.get("absolute_height"))
        if height != _source_height(q):
            _fail("request does not use Platt's exact source height")
        start = _integer(
            "segment.character_ordinal_start",
            segment.get("character_ordinal_start"),
            minimum=0,
        )
        stop = _integer(
            "segment.character_ordinal_stop",
            segment.get("character_ordinal_stop"),
            minimum=start,
        )
        total = _integer(
            "segment.primitive_character_count_for_q",
            segment.get("primitive_character_count_for_q"),
            minimum=1,
        )
        if stop > total:
            _fail("segment ordinal range exceeds the primitive character count")
        for ordinal in range(start, stop):
            conrey, expected_parity = _conrey_from_segment(segment, ordinal)
            yield q, conrey, expected_parity, height
            emitted += 1
    if emitted != request.get("character_count"):
        _fail("request character count differs from expanded compact segments")


def _certificate_header(request: dict[str, Any], config: dict[str, int]) -> dict[str, Any]:
    return {
        "kind": CERTIFICATE_SCHEMA,
        "schema_version": 1,
        "algorithm": ALGORITHM_ID,
        "request_sha256": hashlib.sha256(canonical_json_bytes(request)).hexdigest(),
        "compact_task_set_sha256": request["compact_task_set_sha256"],
        "character_count": request["character_count"],
        "versions": version_record(),
        "configuration": config,
        "contour": {
            "real_lower": {"numerator": -1, "denominator": 2},
            "real_upper": {"numerator": 3, "denominator": 2},
            "ordinate_range": "closed_symmetric_source_height_plus_1_over_64",
            "height_margin": {"numerator": 1, "denominator": 64},
            "orientation": "counterclockwise",
        },
        "analytic_reduction": {
            "argument_principle": (
                "zeros counted with multiplicity; no poles for primitive "
                "nonprincipal L"
            ),
            "trivial_zero_correction": "one simple zero at s=0 exactly when chi is even",
            "critical_line": "each strict Hardy-Z sign change supplies a distinct L zero",
        },
    }


def _certificate_lines(
    request: dict[str, Any], config: dict[str, int]
) -> Iterator[bytes]:
    yield canonical_json_bytes(_certificate_header(request, config))
    for q, conrey, expected_parity, height in _request_rows(request):
        summary = verify_character(q, conrey, height, config)
        if summary["parity"] != expected_parity:
            _fail("canonical CRT parity differs from FLINT character parity")
        yield canonical_json_bytes(summary)


def _write_certificate(path: Path, request: dict[str, Any], config: dict[str, int]) -> None:
    with path.open("wb") as output:
        for line in _certificate_lines(request, config):
            output.write(line)
        output.flush()
        os.fsync(output.fileno())


def _replay_certificate(path: Path, request: dict[str, Any], config: dict[str, int]) -> None:
    try:
        retained = path.open("rb")
    except OSError as error:
        raise FlintReferenceError(f"cannot open certificate {path}: {error}") from error
    with retained:
        for row_number, expected in enumerate(_certificate_lines(request, config), 1):
            actual = retained.readline()
            if actual != expected:
                _fail(f"FLINT certificate replay differs at NDJSON row {row_number}")
        if retained.read(1):
            _fail("FLINT certificate contains trailing rows")


def _parse_options(words: list[str], names: set[str]) -> dict[str, Path]:
    if len(words) % 2:
        _fail("backend protocol options must be name/value pairs")
    result: dict[str, Path] = {}
    for index in range(0, len(words), 2):
        name = words[index]
        if name not in names or name in result:
            _fail(f"unexpected or duplicate backend option: {name}")
        result[name] = Path(words[index + 1])
    if set(result) != names:
        _fail(f"backend options differ: expected {sorted(names)}")
    return result


def _producer(words: list[str]) -> None:
    options = _parse_options(words, {"--request", "--output", "--artifact-root"})
    request = load_canonical_json(options["--request"])
    if not isinstance(request, dict):
        _fail("request must be an object")
    artifact_root = options["--artifact-root"]
    artifact_root.mkdir(parents=True, exist_ok=True)
    certificate = artifact_root / CERTIFICATE_NAME
    config = configuration()
    _write_certificate(certificate, request, config)
    digest, size = _sha256_file(certificate)
    result = {
        "kind": RESULT_SCHEMA,
        "schema_version": 1,
        "producer_algorithm_id": ALGORITHM_ID,
        "producer_version": "1",
        "request_sha256": hashlib.sha256(canonical_json_bytes(request)).hexdigest(),
        "compact_task_set_sha256": request["compact_task_set_sha256"],
        "character_count": request["character_count"],
        "segment_count": request["segment_count"],
        "completed": True,
        "output_artifacts": [
            {
                "path": CERTIFICATE_NAME,
                "sha256": digest,
                "size": size,
                "media_type": "application/x-ndjson",
            }
        ],
    }
    options["--output"].write_bytes(canonical_json_bytes(result))


def _checker(words: list[str]) -> None:
    options = _parse_options(
        words, {"--request", "--result", "--artifact-root", "--receipt"}
    )
    request = load_canonical_json(options["--request"])
    result = load_canonical_json(options["--result"])
    if not isinstance(request, dict) or not isinstance(result, dict):
        _fail("request and result must be objects")
    expected_request_hash = hashlib.sha256(canonical_json_bytes(request)).hexdigest()
    if result.get("request_sha256") != expected_request_hash:
        _fail("producer result request hash mismatch")
    artifacts = result.get("output_artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1:
        _fail("reference result must contain exactly one certificate artifact")
    artifact = artifacts[0]
    if artifact.get("path") != CERTIFICATE_NAME:
        _fail("reference certificate artifact has the wrong path")
    certificate = options["--artifact-root"] / CERTIFICATE_NAME
    digest, size = _sha256_file(certificate)
    if artifact.get("sha256") != digest or artifact.get("size") != size:
        _fail("reference certificate artifact digest or size mismatch")
    config = configuration()
    _replay_certificate(certificate, request, config)
    result_hash = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    receipt = {
        "kind": RECEIPT_SCHEMA,
        "schema_version": 1,
        "checker_algorithm_id": ALGORITHM_ID + "-fresh-replay",
        "checker_version": "1",
        "request_sha256": expected_request_hash,
        "result_sha256": result_hash,
        "compact_task_set_sha256": request["compact_task_set_sha256"],
        "character_count": request["character_count"],
        "segment_count": request["segment_count"],
        "accepted": True,
        "all_requested_characters_covered": True,
        "primitive_character_mapping_checked": True,
        "source_height_exact": True,
        "closed_symmetric_height_covered": True,
        "analytic_function_enclosures_rigorous": True,
        "critical_strip_boundary_zero_free": True,
        "turing_or_argument_principle_count_complete": True,
        "zero_multiplicities_preserved": True,
        "all_nontrivial_zeros_on_critical_line": True,
    }
    options["--receipt"].write_bytes(canonical_json_bytes(receipt))


def _staged_role() -> str | None:
    name = Path(sys.argv[0]).name
    if name == "producer":
        return "producer"
    if name == "checker":
        return "checker"
    return None


def _protocol_main() -> bool:
    role = _staged_role()
    if role is None:
        return False
    if sys.argv[1:] == ["protocol-version"]:
        _require_flint()
        print(PRODUCER_PROTOCOL if role == "producer" else CHECKER_PROTOCOL)
        return True
    if len(sys.argv) < 2:
        _fail("missing backend protocol command")
    command = sys.argv[1]
    if role == "producer" and command == "produce":
        _producer(sys.argv[2:])
        return True
    if role == "checker" and command == "verify":
        _checker(sys.argv[2:])
        return True
    _fail(f"command {command!r} is invalid for staged role {role}")


def _direct_main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    versions = subparsers.add_parser("versions")
    versions.set_defaults(action="versions")
    verify = subparsers.add_parser("verify-character")
    verify.add_argument("--q", type=int, required=True)
    verify.add_argument("--conrey", type=int, required=True)
    verify.add_argument("--height", type=str, required=True)
    verify.set_defaults(action="verify-character")
    args = parser.parse_args()
    if args.action == "versions":
        print(json.dumps(version_record(), sort_keys=True))
        return
    try:
        height = Fraction(args.height)
    except (ValueError, ZeroDivisionError) as error:
        raise FlintReferenceError(f"invalid rational height: {args.height}") from error
    print(json.dumps(verify_character(args.q, args.conrey, height), sort_keys=True))


def main() -> int:
    try:
        if not _protocol_main():
            _direct_main()
    except FlintReferenceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
