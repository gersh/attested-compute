# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Canonical boundary for a rigorous Dirichlet zero-closure chunk.

This module intentionally contains no analytic evaluator.  It defines the
small, source-shaped request/result formats shared by a role-separated Arb
producer and checker.  The current evaluator is a slow reference path: it
reconstructs Hardy Z directly with pinned FLINT, isolates strict sign changes
on Platt's 5/64 lattice and its documented upsampling ladder, and closes the
count with an argument-principle contour.  It is not Platt's fast FFT/Turing
implementation and it does not discharge the external theorem atom.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, NoReturn, Sequence

from tg_verifier.dirichlet_campaign import (
    REQUEST_SCHEMA as CAMPAIGN_REQUEST_SCHEMA,
    primitive_character_descriptor,
    source_height,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
SOURCE_URL = "https://arxiv.org/abs/1305.3087v1"

REQUEST_SCHEMA = "sparkinterval.tg.dirichlet_zero_closure.request.v1"
RESULT_SCHEMA = "sparkinterval.tg.dirichlet_zero_closure.result.v1"
RECEIPT_SCHEMA = "sparkinterval.tg.dirichlet_zero_closure.checker_receipt.v1"
PRODUCER_PROTOCOL = "sparkinterval.dirichlet-zero-closure-producer.v1"
CHECKER_PROTOCOL = "sparkinterval.dirichlet-zero-closure-checker.v1"
ALGORITHM_ID = "flint-direct-hardy-source-grid-argument-count-v1"
CHECKER_ID = "flint-fresh-alternate-grid-and-contour-replay-v1"

SOURCE_SAMPLE_STEP = Fraction(5, 64)
SOURCE_UPSAMPLE_FACTORS = (1, 8, 32, 128, 512)
HEIGHT_MARGIN = Fraction(1, 64)
MAX_CONTROL_BYTES = 32 * 1024 * 1024


class DirichletZeroClosureError(RuntimeError):
    """A closure request, result, or checker decision failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletZeroClosureError(message)


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


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
        raise DirichletZeroClosureError(f"cannot read {path}: {error}") from error
    if len(raw) > MAX_CONTROL_BYTES:
        _fail(f"control JSON exceeds {MAX_CONTROL_BYTES} bytes")
    try:
        value = json.loads(
            raw,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletZeroClosureError(f"invalid JSON in {path}: {error}") from error
    if canonical_json_bytes(value) != raw:
        _fail(f"JSON is not canonical: {path}")
    return value


def write_canonical_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def fraction_json(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


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
    answer = Fraction(numerator, denominator)
    if (answer.numerator, answer.denominator) != (numerator, denominator):
        _fail(f"{name} is not in lowest terms")
    return answer


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        _fail(f"{name} must be a lowercase SHA-256 digest")
    if any(character not in "0123456789abcdef" for character in value):
        _fail(f"{name} must be a lowercase SHA-256 digest")
    return value


def _character_row(
    q: int,
    conrey_number: int,
    parity: int,
    height: Fraction,
    *,
    expected_count: int | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "q": q,
        "conrey_number": conrey_number,
        "conjugate_conrey_number": pow(conrey_number, -1, q),
        "parity": parity,
        "absolute_height": fraction_json(height),
    }
    if expected_count is not None:
        row["known_answer_multiplicity_count"] = expected_count
    return row


def make_request(
    characters: Sequence[dict[str, Any]],
    *,
    profile: str,
    initial_precision_bits: int = 128,
    maximum_precision_bits: int = 4096,
    maximum_contour_depth: int = 64,
    maximum_contour_evaluations: int = 10_000_000,
    maximum_direct_refinements: int = 4,
) -> dict[str, Any]:
    """Build and validate an immutable closure request."""

    body: dict[str, Any] = {
        "kind": REQUEST_SCHEMA,
        "schema_version": 1,
        "atom_id": ATOM_ID,
        "source": SOURCE_URL,
        "profile": profile,
        "character_count": len(characters),
        "characters": list(characters),
        "source_algorithm": {
            "completed_function": "Platt Section 1 Lambda_chi; FLINT Hardy Z differs by a nonzero real scale",
            "sample_step": fraction_json(SOURCE_SAMPLE_STEP),
            "upsample_factors": list(SOURCE_UPSAMPLE_FACTORS),
            "upsampling": "Platt Section 6, routinely 8 then 32, 128, 512",
            "exception_classes": "Platt Section 7 four listed exceptional outcomes",
            "paper_count_closure": "Platt Theorems 3.1--3.3, conjugate-paired Turing method",
            "implemented_count_closure": "multiplicity-preserving argument principle on a stronger closed rectangle",
        },
        "configuration": {
            "initial_precision_bits": initial_precision_bits,
            "maximum_precision_bits": maximum_precision_bits,
            "maximum_contour_depth": maximum_contour_depth,
            "maximum_contour_evaluations": maximum_contour_evaluations,
            "maximum_direct_refinements_after_512": maximum_direct_refinements,
            "height_margin": fraction_json(HEIGHT_MARGIN),
        },
    }
    body["request_sha256"] = sha256_bytes(canonical_json_bytes(body))
    validate_request(body)
    return body


def make_known_answer_request() -> dict[str, Any]:
    """Small q=3,4,5 closure vectors, including a complex conjugate pair."""

    height = Fraction(10)
    return make_request(
        [
            _character_row(3, 2, 1, height, expected_count=2),
            _character_row(4, 3, 1, height, expected_count=2),
            _character_row(5, 2, 1, height, expected_count=4),
            _character_row(5, 3, 1, height, expected_count=4),
            _character_row(5, 4, 0, height, expected_count=4),
        ],
        profile="small_known_answers_q3_q4_q5",
        maximum_contour_evaluations=250_000,
    )


def request_from_campaign(campaign: dict[str, Any]) -> dict[str, Any]:
    """Expand one canonical campaign chunk into a closure request.

    This adapter is deliberately per chunk.  It never materializes the full
    29.6-billion-character source schedule.
    """

    if not isinstance(campaign, dict) or campaign.get("kind") != CAMPAIGN_REQUEST_SCHEMA:
        _fail("input is not a Dirichlet campaign request")
    characters: list[dict[str, Any]] = []
    for segment in campaign.get("segments", []):
        if not isinstance(segment, dict):
            _fail("campaign segment must be an object")
        q = _integer("segment.q", segment.get("q"), minimum=2)
        height = _fraction("segment.absolute_height", segment.get("absolute_height"))
        if height != source_height(q):
            _fail("campaign segment height differs from Platt's source height")
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
        for ordinal in range(start, stop):
            descriptor = primitive_character_descriptor(q, ordinal)
            characters.append(
                _character_row(
                    q,
                    descriptor["conrey_number"],
                    descriptor["parity"],
                    height,
                )
            )
    if len(characters) != campaign.get("character_count"):
        _fail("expanded campaign character count differs")
    return make_request(characters, profile="platt_theorem_7_1_source_chunk")


def validate_request(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("closure request must be an object")
    required = {
        "kind",
        "schema_version",
        "atom_id",
        "source",
        "profile",
        "character_count",
        "characters",
        "source_algorithm",
        "configuration",
        "request_sha256",
    }
    if set(value) != required:
        _fail("closure request keys differ")
    if value["kind"] != REQUEST_SCHEMA or value["schema_version"] != 1:
        _fail("unsupported closure request schema")
    if value["atom_id"] != ATOM_ID or value["source"] != SOURCE_URL:
        _fail("closure request source identity differs")
    retained_hash = _digest("request_sha256", value["request_sha256"])
    unhashed = dict(value)
    del unhashed["request_sha256"]
    if sha256_bytes(canonical_json_bytes(unhashed)) != retained_hash:
        _fail("closure request self-hash differs")
    if value["profile"] not in {
        "small_known_answers_q3_q4_q5",
        "platt_theorem_7_1_source_chunk",
    }:
        _fail("unknown closure request profile")
    characters = value["characters"]
    if not isinstance(characters, list) or not characters:
        _fail("closure request must contain characters")
    if value["character_count"] != len(characters):
        _fail("closure request character count differs")
    seen: set[tuple[int, int]] = set()
    for index, row in enumerate(characters):
        if not isinstance(row, dict):
            _fail("character row must be an object")
        base_keys = {
            "q",
            "conrey_number",
            "conjugate_conrey_number",
            "parity",
            "absolute_height",
        }
        allowed = base_keys | {"known_answer_multiplicity_count"}
        if not base_keys <= set(row) or not set(row) <= allowed:
            _fail(f"character row {index} keys differ")
        q = _integer(f"characters[{index}].q", row["q"], minimum=2)
        conrey = _integer(
            f"characters[{index}].conrey_number", row["conrey_number"], minimum=1
        )
        if conrey >= q or __import__("math").gcd(conrey, q) != 1:
            _fail("Conrey number must be a unit strictly below q")
        conjugate = _integer(
            f"characters[{index}].conjugate_conrey_number",
            row["conjugate_conrey_number"],
            minimum=1,
        )
        if conjugate != pow(conrey, -1, q):
            _fail("conjugate Conrey mapping differs from modular inversion")
        if row["parity"] not in (0, 1):
            _fail("character parity must be zero or one")
        height = _fraction(f"characters[{index}].absolute_height", row["absolute_height"])
        if height <= 0:
            _fail("absolute height must be positive")
        if value["profile"] == "platt_theorem_7_1_source_chunk" and height != source_height(q):
            _fail("source-chunk height differs from Theorem 7.1")
        if "known_answer_multiplicity_count" in row:
            _integer(
                "known_answer_multiplicity_count",
                row["known_answer_multiplicity_count"],
                minimum=0,
            )
        key = (q, conrey)
        if key in seen:
            _fail("duplicate character in closure request")
        seen.add(key)

    algorithm = value["source_algorithm"]
    if not isinstance(algorithm, dict):
        _fail("source_algorithm must be an object")
    if _fraction("source_algorithm.sample_step", algorithm.get("sample_step")) != SOURCE_SAMPLE_STEP:
        _fail("source sampling step differs from 5/64")
    if algorithm.get("upsample_factors") != list(SOURCE_UPSAMPLE_FACTORS):
        _fail("source upsampling ladder differs")
    configuration = value["configuration"]
    expected_configuration = {
        "initial_precision_bits",
        "maximum_precision_bits",
        "maximum_contour_depth",
        "maximum_contour_evaluations",
        "maximum_direct_refinements_after_512",
        "height_margin",
    }
    if not isinstance(configuration, dict) or set(configuration) != expected_configuration:
        _fail("closure configuration keys differ")
    initial = _integer(
        "initial_precision_bits", configuration["initial_precision_bits"], minimum=64
    )
    maximum = _integer(
        "maximum_precision_bits", configuration["maximum_precision_bits"], minimum=initial
    )
    if maximum < initial:
        _fail("maximum precision is below initial precision")
    _integer("maximum_contour_depth", configuration["maximum_contour_depth"], minimum=1)
    _integer(
        "maximum_contour_evaluations",
        configuration["maximum_contour_evaluations"],
        minimum=0,
    )
    _integer(
        "maximum_direct_refinements_after_512",
        configuration["maximum_direct_refinements_after_512"],
        minimum=0,
    )
    if _fraction("height_margin", configuration["height_margin"]) != HEIGHT_MARGIN:
        _fail("height margin differs from 1/64")
    return value


def validate_result(request: dict[str, Any], value: object) -> dict[str, Any]:
    validate_request(request)
    if not isinstance(value, dict):
        _fail("closure result must be an object")
    required = {
        "kind",
        "schema_version",
        "algorithm_id",
        "classification",
        "request_sha256",
        "character_count",
        "versions",
        "characters",
        "completed",
        "paper_turing_method_executed",
        "external_atom_discharged",
    }
    if set(value) != required:
        _fail("closure result keys differ")
    if value["kind"] != RESULT_SCHEMA or value["schema_version"] != 1:
        _fail("unsupported closure result schema")
    if value["algorithm_id"] != ALGORITHM_ID:
        _fail("closure result algorithm differs")
    if value["request_sha256"] != request["request_sha256"]:
        _fail("closure result request hash differs")
    if value["character_count"] != request["character_count"]:
        _fail("closure result character count differs")
    if value["completed"] is not True:
        _fail("closure result is incomplete")
    if value["paper_turing_method_executed"] is not False:
        _fail("reference closure must not claim Platt's Turing method was executed")
    if value["external_atom_discharged"] is not False:
        _fail("a closure chunk must not claim to discharge the full atom")
    rows = value["characters"]
    if not isinstance(rows, list) or len(rows) != request["character_count"]:
        _fail("closure result character rows differ")
    expected_keys = {
        "q",
        "conrey_number",
        "parity",
        "absolute_height",
        "stronger_certified_height",
        "completed_hardy_reconstruction",
        "multiplicity_counted_nontrivial_zeros",
        "argument_principle",
        "zero_isolation",
        "exception_handling",
        "all_nontrivial_zeros_on_critical_line",
    }
    for request_row, row in zip(request["characters"], rows):
        if not isinstance(row, dict) or set(row) != expected_keys:
            _fail("closure result character row keys differ")
        if (row["q"], row["conrey_number"], row["parity"], row["absolute_height"]) != (
            request_row["q"],
            request_row["conrey_number"],
            request_row["parity"],
            request_row["absolute_height"],
        ):
            _fail("closure result character identity differs")
        height = _fraction("absolute_height", row["absolute_height"])
        stronger = _fraction("stronger_certified_height", row["stronger_certified_height"])
        if stronger != height + HEIGHT_MARGIN:
            _fail("closure result stronger height differs")
        count = _integer(
            "multiplicity_counted_nontrivial_zeros",
            row["multiplicity_counted_nontrivial_zeros"],
            minimum=0,
        )
        isolation = row["zero_isolation"]
        if not isinstance(isolation, dict):
            _fail("zero isolation must be an object")
        if isolation.get("strict_sign_change_brackets") != count:
            _fail("sign-change count differs from multiplicity count")
        _digest("bracket_digest_sha256", isolation.get("bracket_digest_sha256"))
        if row["all_nontrivial_zeros_on_critical_line"] is not True:
            _fail("closure result did not reach its per-character conclusion")
    return value


def capability_report() -> dict[str, Any]:
    return {
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "checker_id": CHECKER_ID,
        "source": SOURCE_URL,
        "classification": "range-general-rigorous-reference-closure-not-source-scale-fast-path",
        "production_ready": False,
        "full_source": {
            "input_domain_supported": True,
            "campaign_run_completed": False,
            "economically_scaled": False,
        },
        "implemented": {
            "completed_hardy_z_reconstruction": True,
            "source_sample_step_5_over_64": True,
            "source_upsampling_factors": list(SOURCE_UPSAMPLE_FACTORS),
            "direct_arb_exception_recomputation": True,
            "strict_sign_change_zero_isolation": True,
            "multiplicity_preserving_argument_principle_count": True,
            "fresh_role_separated_checker": True,
            "canonical_source_chunk_adapter": True,
            "q3_q4_q5_known_answers": True,
        },
        "trust_boundary": {
            "analytic_library": "pinned python-flint 0.9.0 / FLINT 3.6.0 Arb",
            "checker_independence": "separate executable and fresh evaluations; shared FLINT analytic library",
            "lean_realization": False,
        },
        "work_units": {
            "ordinary_upsampling": "rigorous Hardy-Z sample sign",
            "exception_path": "precision-escalated or split-point direct Arb sign",
            "count_path": "L-function contour box or endpoint evaluation",
            "turing_path": "not used by this argument-principle fallback; see dirichlet_postprocess capability",
        },
        "local_reference_benchmark": {
            "date": "2026-07-21",
            "host": "DGX Spark / NVIDIA GB10 / 20-core Cortex-X925",
            "profile": "q=3,4,5 five-character producer KAT at height 10",
            "elapsed_seconds": 44.48,
            "ordinary_hardy_samples": 1295,
            "ordinary_hardy_samples_per_second_over_whole_run": 29.114208633093526,
            "contour_box_and_point_evaluations": 357040,
            "contour_evaluations_per_second_over_whole_run": 8026.978417266188,
            "exception_events": 0,
            "warning": "heterogeneous rates share one wall-clock denominator and are not a full-source ETA",
        },
        "not_implemented": [
            "Platt Section 4 all-character CRT/Bluestein interval FFT",
            "Platt Section 5 Booker small-q FFT",
            "Platt Section 6 Whittaker-Shannon/Weiss interpolation and Lemmas 6.3--6.7 error budgets",
            "Platt Theorem 3.2 conjugate-paired Turing integral and Theorem 3.3/Trudgian bounds",
            "source-scale exception batching and shift/retry policy",
            "Lean theorem realizing FLINT completed-L and contour semantics",
        ],
        "paper_turing_method_executed": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "ATOM_ID",
    "CHECKER_ID",
    "CHECKER_PROTOCOL",
    "DirichletZeroClosureError",
    "HEIGHT_MARGIN",
    "PRODUCER_PROTOCOL",
    "RECEIPT_SCHEMA",
    "REQUEST_SCHEMA",
    "RESULT_SCHEMA",
    "SOURCE_SAMPLE_STEP",
    "SOURCE_UPSAMPLE_FACTORS",
    "canonical_json_bytes",
    "capability_report",
    "fraction_json",
    "load_canonical_json",
    "make_known_answer_request",
    "make_request",
    "request_from_campaign",
    "sha256_bytes",
    "validate_request",
    "validate_result",
    "write_canonical_json",
]
