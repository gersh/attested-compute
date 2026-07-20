# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact structural checks for retained ternary-Goldbach analytic artifacts.

The checkers in this module deliberately have a narrow trust claim.  They
validate canonical JSON, certificate topology, and exact integer/rational
relationships without importing FLINT or evaluating an analytic function.
In particular, acceptance does *not* prove that a recorded interval encloses
``zeta``, ``zeta'``, a zeta zero, or any other analytic value.

The public entry points accept either canonical JSON bytes or a filesystem
path and fail closed by raising :class:`AnalyticArtifactError`.
"""

from __future__ import annotations

import base64
import binascii
from fractions import Fraction
import hashlib
from math import gcd, isqrt
import json
from pathlib import Path
import re
from typing import Any, NoReturn


class AnalyticArtifactError(ValueError):
    """A retained analytic artifact failed an exact local check."""


A7_SCHEMA = "ch25-a7-boundary-v1"
PROP77_SCHEMA = "ch25-prop77-flint-head-v1"

_AUTHOR = "Gershon Bialer"
_A7_NORM_TARGET = Fraction(349, 250)
_A7_NORM_SQ_TARGET = _A7_NORM_TARGET * _A7_NORM_TARGET
_A7_RETAINED_ARTIFACT_SHA256 = (
    "ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29"
)
_PROP77_HEIGHT = 20_000
_PROP77_COUNT = 22_491
_PROP77_REQUESTED = _PROP77_COUNT + 1
_PROP77_PRECISION_BITS = 96
_PROP77_RECIPROCAL_TARGET = Fraction(257_983, 50_000)
_PROP77_ORDINATE_INTERVALS_SHA256 = (
    "9a3b89e580d50514690488dcea35ba6b24ff4180eb72378bba52216b0e1143ff"
)
_PROP77_RETAINED_ARTIFACT_SHA256 = (
    "60bbfe8268722320a45e264c17f9b4132cccbf135f63b5b9a8d4fc8ae2ec952a"
)

_MAX_JSON_BYTES = 64 * 1024 * 1024
_MAX_JSON_INTEGER_DIGITS = 128
_MAX_RATIONAL_DIGITS = 4_096
_MAX_A7_LEAVES = 2_000_000
_MAX_A7_DEPTH = 64
_MAX_DYADIC_BITS = 16_384
_MAX_DYADIC_EXPONENT = 16_384

_INTEGER_RE = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")
_POSITIVE_INTEGER_RE = re.compile(r"[1-9][0-9]*\Z")
_DECIMAL_RE = re.compile(r"(?:0|[1-9][0-9]*)(?:\.([0-9]+))?\Z")
_BASE64URL_RE = re.compile(r"[A-Za-z0-9_-]+\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")

_A7_EDGE_SPECS = (
    ("left", "imag", Fraction(-4), Fraction(4), Fraction(-3)),
    ("right", "imag", Fraction(-4), Fraction(4), Fraction(5)),
    ("bottom", "real", Fraction(-3), Fraction(5), Fraction(-4)),
    ("top", "real", Fraction(-3), Fraction(5), Fraction(4)),
)

_A7_LEAF_ENCODING = {
    "fields": [
        "edge_id",
        "depth",
        "index",
        "norm_sq_upper_mantissa_base64url",
        "norm_sq_upper_exponent",
        "zeta_abs_lower_mantissa_base64url",
        "zeta_abs_lower_exponent",
    ],
    "value_rule": "mantissa * 2^exponent",
    "mantissa_encoding": (
        "unsigned big-endian, unpadded RFC 4648 base64url"
    ),
    "edge_id_rule": "zero-based index into edges",
    "interval_rule": (
        "[start + index*(end-start)/2^depth, "
        "start + (index+1)*(end-start)/2^depth]"
    ),
}

_A7_REJECTION_REASONS = {
    "s_minus_one_contains_zero",
    "s_plus_two_contains_zero",
    "zeta_jet_nonfinite",
    "zeta_contains_zero",
    "zeta_lower_nonfinite",
    "zeta_lower_not_positive",
    "g_nonfinite",
    "norm_sq_nonfinite",
    "norm_sq_upper_nonfinite",
    "bound_not_strict",
}

_PROP77_COUNTING_CONVENTION = (
    "nontrivial zeta zeros with 0 < Im(rho) <= 20000, counted according "
    "to multiplicity"
)
_PROP77_COMPLETENESS_ARGUMENT = (
    "N(20000) is exactly 22491 counting all nontrivial zeros with "
    "multiplicity. The first 22491 returned critical-line zero balls are "
    "positive, pairwise disjoint, and lie below the cutoff, so they account "
    "for at least 22491 multiplicity units. Equality forces each ball to "
    "contain multiplicity exactly one and leaves no additional on-line or "
    "off-line zero below the cutoff. The 22492nd ball lies strictly above "
    "the cutoff."
)
_PROP77_TRUST_BOUNDARY = (
    "This deterministic artifact is independently recomputed by FLINT/Arb "
    "outside Lean. It depends on the reviewed FLINT implementation and the "
    "host toolchain; it is not an ordinary-kernel Lean proof."
)
_PROP77_PROVENANCE = {
    "flint_documentation": (
        "https://flintlib.org/doc/acb_dirichlet.html#riemann-zeta-function-zeros"
    ),
    "flint_3_6_source": (
        "https://github.com/flintlib/flint/tree/v3.6.0/src/acb_dirichlet"
    ),
    "ch25_proposition": "https://arxiv.org/abs/2512.15709v1",
    "python_flint_requirement": "python-flint==0.9.0",
    "flint_requirement": "FLINT==3.6.0",
}


def _fail(message: str) -> NoReturn:
    raise AnalyticArtifactError(message)


def _reject_json_constant(value: str) -> NoReturn:
    _fail(f"non-finite JSON number is forbidden: {value}")


def _reject_json_float(value: str) -> NoReturn:
    _fail(f"JSON floating-point numbers are forbidden: {value}")


def _parse_json_int(value: str) -> int:
    if len(value.lstrip("-")) > _MAX_JSON_INTEGER_DIGITS:
        _fail("JSON integer exceeds the local digit limit")
    return int(value)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def canonical_json_bytes(value: Any) -> bytes:
    """Return the canonical compact ASCII encoding used by both artifacts."""

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _load_canonical_json(raw: bytes, *, label: str) -> dict[str, Any]:
    if type(raw) is not bytes:
        _fail(f"{label} must be supplied as bytes")
    if len(raw) > _MAX_JSON_BYTES:
        _fail(f"{label} exceeds the {_MAX_JSON_BYTES}-byte local limit")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise AnalyticArtifactError(f"{label} is not ASCII JSON") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
            parse_float=_reject_json_float,
            parse_int=_parse_json_int,
        )
    except AnalyticArtifactError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as error:
        raise AnalyticArtifactError(f"{label} is not valid JSON: {error}") from error
    if type(value) is not dict:
        _fail(f"{label} root must be a JSON object")
    try:
        canonical = canonical_json_bytes(value) + b"\n"
    except (RecursionError, ValueError) as error:
        raise AnalyticArtifactError(
            f"{label} cannot be represented as bounded canonical JSON"
        ) from error
    if raw != canonical:
        _fail(f"{label} is not canonical compact JSON with one final newline")
    return value


def read_analytic_artifact_bytes(path: str | Path, *, label: str) -> bytes:
    """Capture at most the local artifact limit from one open file handle."""

    artifact = Path(path)
    try:
        with artifact.open("rb") as source:
            raw = source.read(_MAX_JSON_BYTES + 1)
        if len(raw) > _MAX_JSON_BYTES:
            _fail(f"{label} exceeds the {_MAX_JSON_BYTES}-byte local limit")
        return raw
    except AnalyticArtifactError:
        raise
    except OSError as error:
        raise AnalyticArtifactError(f"cannot read {label} {artifact}: {error}") from error


def _object(
    value: Any, expected_keys: set[str], *, label: str
) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(f"{label} must be an object")
    actual_keys = set(value)
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        _fail(f"{label} has wrong keys: missing={missing}, extra={extra}")
    return value


def _list(value: Any, *, label: str) -> list[Any]:
    if type(value) is not list:
        _fail(f"{label} must be a list")
    return value


def _string(value: Any, *, label: str) -> str:
    if type(value) is not str:
        _fail(f"{label} must be a string")
    return value


def _integer(
    value: Any,
    *,
    label: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if type(value) is not int:
        _fail(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        _fail(f"{label} must be at least {minimum}")
    if maximum is not None and value > maximum:
        _fail(f"{label} must be at most {maximum}")
    return value


def _true(value: Any, *, label: str) -> None:
    if value is not True:
        _fail(f"{label} must be true")


def _exact_json_equal(value: Any, expected: Any) -> bool:
    """Compare JSON values without identifying booleans with integers."""

    if type(value) is not type(expected):
        return False
    if type(expected) is list:
        return len(value) == len(expected) and all(
            _exact_json_equal(left, right)
            for left, right in zip(value, expected)
        )
    if type(expected) is dict:
        return set(value) == set(expected) and all(
            _exact_json_equal(value[key], expected[key]) for key in expected
        )
    return value == expected


def _equal(value: Any, expected: Any, *, label: str) -> None:
    if not _exact_json_equal(value, expected):
        _fail(f"{label} must equal {expected!r}")


def _parse_integer_text(value: Any, *, label: str, positive: bool = False) -> int:
    text = _string(value, label=label)
    pattern = _POSITIVE_INTEGER_RE if positive else _INTEGER_RE
    if len(text.lstrip("-")) > _MAX_RATIONAL_DIGITS or pattern.fullmatch(text) is None:
        _fail(f"{label} is not a canonical {'positive ' if positive else ''}integer")
    return int(text)


def _rational(value: Any, *, label: str) -> Fraction:
    item = _object(value, {"numerator", "denominator"}, label=label)
    numerator = _parse_integer_text(item["numerator"], label=f"{label}.numerator")
    denominator = _parse_integer_text(
        item["denominator"], label=f"{label}.denominator", positive=True
    )
    if gcd(abs(numerator), denominator) != 1:
        _fail(f"{label} is not in reduced canonical form")
    return Fraction(numerator, denominator)


def _decimal(value: Any, *, label: str) -> tuple[Fraction, int]:
    text = _string(value, label=label)
    if len(text) > _MAX_RATIONAL_DIGITS:
        _fail(f"{label} exceeds the local digit limit")
    match = _DECIMAL_RE.fullmatch(text)
    if match is None:
        _fail(f"{label} is not a canonical nonnegative decimal")
    fractional = match.group(1)
    if fractional is None:
        return Fraction(int(text), 1), 0
    whole, digits = text.split(".")
    scale = 10 ** len(digits)
    return Fraction(int(whole) * scale + int(digits), scale), len(digits)


def _decimal_floor(value: Fraction, digits: int) -> str:
    scale = 10**digits
    scaled = value.numerator * scale // value.denominator
    whole, fractional = divmod(scaled, scale)
    return f"{whole}.{fractional:0{digits}d}"


def _decimal_ceiling(value: Fraction, digits: int) -> str:
    scale = 10**digits
    numerator = value.numerator * scale
    scaled = -(-numerator // value.denominator)
    whole, fractional = divmod(scaled, scale)
    return f"{whole}.{fractional:0{digits}d}"


def _check_floor_decimal(text: Any, value: Fraction, *, label: str) -> None:
    _parsed, digits = _decimal(text, label=label)
    if text != _decimal_floor(value, digits):
        _fail(f"{label} is not the exact outward floor of its rational value")


def _check_ceiling_decimal(text: Any, value: Fraction, *, label: str) -> None:
    _parsed, digits = _decimal(text, label=label)
    if text != _decimal_ceiling(value, digits):
        _fail(f"{label} is not the exact outward ceiling of its rational value")


def _dyadic(mantissa_text: Any, exponent_value: Any, *, label: str) -> Fraction:
    encoded = _string(mantissa_text, label=f"{label}.mantissa")
    if len(encoded) > (_MAX_DYADIC_BITS + 5) // 6:
        _fail(f"{label}.mantissa exceeds the local bit limit")
    if _BASE64URL_RE.fullmatch(encoded) is None:
        _fail(f"{label}.mantissa is not unpadded base64url")
    try:
        decoded = base64.b64decode(
            encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True
        )
    except (binascii.Error, ValueError) as error:
        raise AnalyticArtifactError(
            f"{label}.mantissa is not valid unpadded base64url"
        ) from error
    if not decoded or decoded[0] == 0:
        _fail(f"{label}.mantissa is not a minimal positive big-endian integer")
    canonical = base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=")
    if canonical != encoded:
        _fail(f"{label}.mantissa is not canonically encoded")
    mantissa = int.from_bytes(decoded, "big")
    if mantissa <= 0 or mantissa.bit_length() > _MAX_DYADIC_BITS:
        _fail(f"{label}.mantissa is not a bounded positive integer")
    exponent = _integer(
        exponent_value,
        label=f"{label}.exponent",
        minimum=-_MAX_DYADIC_EXPONENT,
        maximum=_MAX_DYADIC_EXPONENT,
    )
    if exponent >= 0:
        return Fraction(mantissa << exponent, 1)
    return Fraction(mantissa, 1 << -exponent)


def _digest(value: Any, *, label: str) -> str:
    text = _string(value, label=label)
    if _SHA256_RE.fullmatch(text) is None:
        _fail(f"{label} must be exactly 64 lowercase hexadecimal characters")
    return text


def _a7_edges(value: Any) -> list[tuple[Fraction, Fraction]]:
    edges = _list(value, label="edges")
    if len(edges) != len(_A7_EDGE_SPECS):
        _fail("edges must contain exactly the four canonical rectangle edges")
    ranges: list[tuple[Fraction, Fraction]] = []
    for edge_id, (value_edge, expected) in enumerate(zip(edges, _A7_EDGE_SPECS)):
        name, varying, start, end, fixed = expected
        edge = _object(
            value_edge,
            {"name", "varying_coordinate", "start", "end", "fixed_coordinate"},
            label=f"edges[{edge_id}]",
        )
        _equal(edge["name"], name, label=f"edges[{edge_id}].name")
        _equal(
            edge["varying_coordinate"],
            varying,
            label=f"edges[{edge_id}].varying_coordinate",
        )
        actual_start = _rational(edge["start"], label=f"edges[{edge_id}].start")
        actual_end = _rational(edge["end"], label=f"edges[{edge_id}].end")
        actual_fixed = _rational(
            edge["fixed_coordinate"], label=f"edges[{edge_id}].fixed_coordinate"
        )
        if (actual_start, actual_end, actual_fixed) != (start, end, fixed):
            _fail(f"edges[{edge_id}] does not describe the canonical {name} edge")
        ranges.append((start, end))
    return ranges


def _a7_static_sections(document: dict[str, Any]) -> tuple[int, int]:
    _equal(document["schema"], A7_SCHEMA, label="schema")
    _equal(document["author"], _AUTHOR, label="author")

    claim = _object(
        document["claim"],
        {"function", "rectangle", "norm_bound", "norm_sq_bound"},
        label="claim",
    )
    _equal(
        claim["function"],
        "-zeta'(s)/zeta(s)-1/(s-1)+1/(s+2)",
        label="claim.function",
    )
    rectangle = _object(
        claim["rectangle"], {"real", "imag", "locus"}, label="claim.rectangle"
    )
    _equal(rectangle["real"], ["-3", "5"], label="claim.rectangle.real")
    _equal(rectangle["imag"], ["-4", "4"], label="claim.rectangle.imag")
    _equal(
        rectangle["locus"], "all four closed edges", label="claim.rectangle.locus"
    )
    if _rational(claim["norm_bound"], label="claim.norm_bound") != _A7_NORM_TARGET:
        _fail("claim.norm_bound is not exactly 349/250")
    if (
        _rational(claim["norm_sq_bound"], label="claim.norm_sq_bound")
        != _A7_NORM_SQ_TARGET
    ):
        _fail("claim.norm_sq_bound is not exactly (349/250)^2")

    arithmetic = _object(
        document["arithmetic"],
        {
            "acceptance",
            "flint_release",
            "flint_version",
            "precision_bits",
            "python_flint_version",
            "series_cap",
            "series_length",
            "subdivision",
            "threads",
        },
        label="arithmetic",
    )
    _equal(
        arithmetic["acceptance"],
        "exact upper(normSq(G(box))) < (349/250)^2",
        label="arithmetic.acceptance",
    )
    _equal(arithmetic["flint_release"], 30600, label="arithmetic.flint_release")
    _equal(arithmetic["flint_version"], "3.6.0", label="arithmetic.flint_version")
    _equal(
        arithmetic["python_flint_version"],
        "0.9.0",
        label="arithmetic.python_flint_version",
    )
    _integer(
        arithmetic["precision_bits"],
        label="arithmetic.precision_bits",
        minimum=192,
        maximum=1_000_000,
    )
    _equal(arithmetic["series_cap"], 4, label="arithmetic.series_cap")
    _equal(arithmetic["series_length"], 2, label="arithmetic.series_length")
    _equal(
        arithmetic["subdivision"],
        "exact dyadic midpoint",
        label="arithmetic.subdivision",
    )
    _equal(arithmetic["threads"], 1, label="arithmetic.threads")

    guards = _object(document["guards"], {"max_depth", "max_work"}, label="guards")
    max_depth = _integer(
        guards["max_depth"],
        label="guards.max_depth",
        minimum=0,
        maximum=_MAX_A7_DEPTH,
    )
    max_work = _integer(
        guards["max_work"],
        label="guards.max_work",
        minimum=1,
        maximum=100_000_000,
    )

    encoding = _object(
        document["leaf_encoding"], set(_A7_LEAF_ENCODING), label="leaf_encoding"
    )
    if encoding != _A7_LEAF_ENCODING:
        _fail("leaf_encoding does not match the canonical v1 encoding")
    return max_depth, max_work


def _a7_leaf_data(
    leaves_value: Any, *, max_depth: int
) -> tuple[list[dict[str, Any]], dict[str, int], int, Fraction, Fraction]:
    leaves = _list(leaves_value, label="leaves")
    if not 4 <= len(leaves) <= _MAX_A7_LEAVES:
        _fail("leaves must contain a bounded nonempty cover of all four edges")
    records: list[dict[str, Any]] = []
    counts = {name: 0 for name, *_rest in _A7_EDGE_SPECS}

    for position, leaf_value in enumerate(leaves):
        leaf = _list(leaf_value, label=f"leaves[{position}]")
        if len(leaf) != 7:
            _fail(f"leaves[{position}] must have exactly seven fields")
        edge_id = _integer(
            leaf[0], label=f"leaves[{position}].edge_id", minimum=0, maximum=3
        )
        depth = _integer(
            leaf[1],
            label=f"leaves[{position}].depth",
            minimum=0,
            maximum=max_depth,
        )
        index = _integer(
            leaf[2],
            label=f"leaves[{position}].index",
            minimum=0,
            maximum=(1 << depth) - 1,
        )
        denominator = 1 << depth
        lower = Fraction(index, denominator)
        upper = Fraction(index + 1, denominator)
        norm_sq = _dyadic(
            leaf[3], leaf[4], label=f"leaves[{position}].norm_sq_upper"
        )
        zeta_lower = _dyadic(
            leaf[5], leaf[6], label=f"leaves[{position}].zeta_abs_lower"
        )
        if not 0 < norm_sq < _A7_NORM_SQ_TARGET:
            _fail(
                f"leaves[{position}].norm_sq_upper is not strictly between zero "
                "and (349/250)^2"
            )
        if zeta_lower <= 0:
            _fail(f"leaves[{position}].zeta_abs_lower is not strictly positive")
        name = _A7_EDGE_SPECS[edge_id][0]
        counts[name] += 1
        records.append(
            {
                "position": position,
                "edge_id": edge_id,
                "edge": name,
                "depth": depth,
                "index": index,
                "lower": lower,
                "upper": upper,
                "norm_sq": norm_sq,
                "zeta_lower": zeta_lower,
            }
        )

    keys = [(r["edge_id"], r["lower"], r["upper"]) for r in records]
    if keys != sorted(keys):
        _fail("leaves are not canonically grouped by edge and increasing coordinate")

    for edge_id, (name, *_rest) in enumerate(_A7_EDGE_SPECS):
        edge_records = [r for r in records if r["edge_id"] == edge_id]
        if not edge_records:
            _fail(f"the {name} edge has no leaves")
        cursor = Fraction(0)
        for record in edge_records:
            if record["lower"] != cursor:
                relation = "overlap" if record["lower"] < cursor else "gap"
                _fail(f"the {name} edge has a dyadic {relation} at {cursor}")
            cursor = record["upper"]
        if cursor != 1:
            _fail(f"the {name} edge does not cover its complete endpoint range")

    deepest = max(record["depth"] for record in records)
    max_norm_sq = max(record["norm_sq"] for record in records)
    min_zeta_lower = min(record["zeta_lower"] for record in records)
    return records, counts, deepest, max_norm_sq, min_zeta_lower


def _a7_norm_diagnostics(max_norm_sq: Fraction) -> tuple[str, str]:
    digits = 45
    scale = 10**digits
    radicand = max_norm_sq.numerator * scale * scale
    norm_scaled = isqrt(radicand // max_norm_sq.denominator)
    if norm_scaled * norm_scaled * max_norm_sq.denominator < radicand:
        norm_scaled += 1
    target_scaled = _A7_NORM_TARGET.numerator * scale
    if target_scaled % _A7_NORM_TARGET.denominator:
        _fail("internal A7 decimal scale does not represent the norm target")
    margin_scaled = target_scaled // _A7_NORM_TARGET.denominator - norm_scaled
    if margin_scaled <= 0:
        _fail("the outward A7 norm diagnostic has no positive margin")
    norm_whole, norm_fraction = divmod(norm_scaled, scale)
    margin_whole, margin_fraction = divmod(margin_scaled, scale)
    return (
        f"{norm_whole}.{norm_fraction:0{digits}d}",
        f"{margin_whole}.{margin_fraction:0{digits}d}",
    )


def _a7_summary(
    document: dict[str, Any],
    records: list[dict[str, Any]],
    counts: dict[str, int],
    deepest: int,
    max_norm_sq: Fraction,
    min_zeta_lower: Fraction,
    edge_ranges: list[tuple[Fraction, Fraction]],
    *,
    max_work: int,
) -> str:
    summary = _object(
        document["summary"],
        {
            "leaf_count",
            "leaf_counts_by_edge",
            "work_count",
            "max_depth",
            "rejection_counts",
            "max_norm_sq_upper",
            "margin_norm_sq",
            "min_zeta_abs_lower",
            "max_leaf",
            "max_norm_upper_decimal_outward",
            "margin_norm_lower_decimal_outward",
            "leaves_sha256",
        },
        label="summary",
    )
    if _integer(summary["leaf_count"], label="summary.leaf_count") != len(records):
        _fail("summary.leaf_count does not match the leaf array")

    recorded_counts = _object(
        summary["leaf_counts_by_edge"], set(counts), label="summary.leaf_counts_by_edge"
    )
    for name, count in counts.items():
        if _integer(recorded_counts[name], label=f"summary.leaf_counts_by_edge.{name}") != count:
            _fail(f"summary leaf count for {name} does not match the leaf array")

    if _integer(summary["max_depth"], label="summary.max_depth") != deepest:
        _fail("summary.max_depth does not match the deepest leaf")

    rejection_counts = summary["rejection_counts"]
    if type(rejection_counts) is not dict:
        _fail("summary.rejection_counts must be an object")
    unknown_reasons = set(rejection_counts) - _A7_REJECTION_REASONS
    if unknown_reasons:
        _fail(f"summary.rejection_counts has unknown reasons: {sorted(unknown_reasons)}")
    rejected = 0
    for reason, count in rejection_counts.items():
        rejected += _integer(
            count, label=f"summary.rejection_counts.{reason}", minimum=1
        )
    if rejected != len(records) - len(_A7_EDGE_SPECS):
        _fail("summary rejection count is inconsistent with four full binary covers")
    expected_work = len(records) + rejected
    work = _integer(summary["work_count"], label="summary.work_count", minimum=1)
    if work != expected_work or work > max_work:
        _fail("summary.work_count is inconsistent with the cover or work guard")

    if (
        _rational(summary["max_norm_sq_upper"], label="summary.max_norm_sq_upper")
        != max_norm_sq
    ):
        _fail("summary.max_norm_sq_upper does not match the leaves")
    expected_margin = _A7_NORM_SQ_TARGET - max_norm_sq
    if _rational(summary["margin_norm_sq"], label="summary.margin_norm_sq") != expected_margin:
        _fail("summary.margin_norm_sq is not target minus the maximum leaf bound")
    if (
        _rational(
            summary["min_zeta_abs_lower"], label="summary.min_zeta_abs_lower"
        )
        != min_zeta_lower
    ):
        _fail("summary.min_zeta_abs_lower does not match the leaves")

    first_max = next(r for r in records if r["norm_sq"] == max_norm_sq)
    max_leaf = _object(
        summary["max_leaf"], {"edge", "depth", "index", "lo", "hi"}, label="summary.max_leaf"
    )
    _equal(max_leaf["edge"], first_max["edge"], label="summary.max_leaf.edge")
    _equal(max_leaf["depth"], first_max["depth"], label="summary.max_leaf.depth")
    _equal(max_leaf["index"], first_max["index"], label="summary.max_leaf.index")
    start, end = edge_ranges[first_max["edge_id"]]
    expected_lo = start + (end - start) * first_max["lower"]
    expected_hi = start + (end - start) * first_max["upper"]
    if _rational(max_leaf["lo"], label="summary.max_leaf.lo") != expected_lo:
        _fail("summary.max_leaf.lo does not match its dyadic leaf")
    if _rational(max_leaf["hi"], label="summary.max_leaf.hi") != expected_hi:
        _fail("summary.max_leaf.hi does not match its dyadic leaf")

    expected_norm_decimal, expected_margin_decimal = _a7_norm_diagnostics(max_norm_sq)
    _equal(
        summary["max_norm_upper_decimal_outward"],
        expected_norm_decimal,
        label="summary.max_norm_upper_decimal_outward",
    )
    _equal(
        summary["margin_norm_lower_decimal_outward"],
        expected_margin_decimal,
        label="summary.margin_norm_lower_decimal_outward",
    )

    expected_digest = hashlib.sha256(canonical_json_bytes(document["leaves"])).hexdigest()
    recorded_digest = _digest(summary["leaves_sha256"], label="summary.leaves_sha256")
    if recorded_digest != expected_digest:
        _fail("summary.leaves_sha256 does not match the canonical leaf array")
    return recorded_digest


def verify_a7_boundary_bytes(
    raw: bytes, *, require_retained_identity: bool = False
) -> dict[str, Any]:
    """Verify exact finite structure/arithmetic of an A.7 boundary transcript.

    The returned receipt always records that zeta and derivative enclosure
    semantics were not verified.  A malformed or inconsistent artifact raises
    :class:`AnalyticArtifactError` rather than returning a negative receipt.
    """

    document = _load_canonical_json(raw, label="A7 boundary artifact")
    _object(
        document,
        {
            "schema",
            "author",
            "claim",
            "arithmetic",
            "guards",
            "edges",
            "leaf_encoding",
            "leaves",
            "summary",
        },
        label="A7 boundary artifact",
    )
    max_depth, max_work = _a7_static_sections(document)
    edge_ranges = _a7_edges(document["edges"])
    records, counts, deepest, max_norm_sq, min_zeta_lower = _a7_leaf_data(
        document["leaves"], max_depth=max_depth
    )
    digest = _a7_summary(
        document,
        records,
        counts,
        deepest,
        max_norm_sq,
        min_zeta_lower,
        edge_ranges,
        max_work=max_work,
    )
    result = {
        "accepted": True,
        "artifact_kind": "ch25_a7_boundary",
        "schema": A7_SCHEMA,
        "verification_class": "exact_structure_and_arithmetic_only",
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "leaf_count": len(records),
        "leaf_counts_by_edge": counts,
        "max_depth": deepest,
        "leaves_sha256": digest,
        "four_edge_dyadic_cover_verified": True,
        "leaf_digest_contents_verified": True,
        "stored_norm_square_inequalities_verified": True,
        "flint_box_evaluations_recomputed": False,
        "zeta_enclosures_verified": False,
        "zeta_derivative_enclosures_verified": False,
        "analytic_claim_proved": False,
        "external_semantics_required": True,
    }
    if require_retained_identity:
        if result["artifact_sha256"] != _A7_RETAINED_ARTIFACT_SHA256:
            _fail("A7 boundary bytes do not match the pinned retained artifact")
        result["artifact_bytes_match_pinned_sha256"] = True
        result["verification_class"] = (
            "pinned_identity_plus_exact_structure_and_arithmetic_only"
        )
    else:
        result["artifact_bytes_match_pinned_sha256"] = False
    return result


def verify_a7_boundary_file(
    path: str | Path, *, require_retained_identity: bool = False
) -> dict[str, Any]:
    """Read and structurally verify an A.7 boundary transcript.

    ``require_retained_identity`` additionally pins the exact artifact used by
    the ternary-Goldbach source repository.  Identity pinning does not replay
    FLINT and does not establish zeta semantics.
    """

    return verify_a7_boundary_bytes(
        read_analytic_artifact_bytes(path, label="A7 boundary artifact"),
        require_retained_identity=require_retained_identity,
    )


def _prop77_static_sections(document: dict[str, Any]) -> None:
    _equal(document["schema"], PROP77_SCHEMA, label="schema")
    _equal(document["author"], _AUTHOR, label="author")

    claim = _object(
        document["claim"],
        {
            "height_cutoff",
            "multiplicity_count",
            "proved",
            "reciprocal_sum",
            "strict_upper_bound",
        },
        label="claim",
    )
    _equal(claim["height_cutoff"], "20000", label="claim.height_cutoff")
    _equal(claim["multiplicity_count"], _PROP77_COUNT, label="claim.multiplicity_count")
    _true(claim["proved"], label="claim.proved")
    _equal(
        claim["reciprocal_sum"],
        "sum_{0 < gamma <= 20000} 1/gamma",
        label="claim.reciprocal_sum",
    )
    _equal(claim["strict_upper_bound"], "5.15966", label="claim.strict_upper_bound")

    configuration = _object(
        document["configuration"],
        {"precision_bits", "requested_zero_indices", "threads"},
        label="configuration",
    )
    _equal(
        configuration["precision_bits"],
        _PROP77_PRECISION_BITS,
        label="configuration.precision_bits",
    )
    _equal(configuration["threads"], 1, label="configuration.threads")
    _equal(
        configuration["requested_zero_indices"],
        [1, _PROP77_REQUESTED],
        label="configuration.requested_zero_indices",
    )

    versions = _object(
        document["versions"], {"flint", "flint_release", "python_flint"}, label="versions"
    )
    _equal(versions["flint"], "3.6.0", label="versions.flint")
    _equal(versions["flint_release"], 30600, label="versions.flint_release")
    _equal(versions["python_flint"], "0.9.0", label="versions.python_flint")

    _equal(
        document["completeness_and_multiplicity_argument"],
        _PROP77_COMPLETENESS_ARGUMENT,
        label="completeness_and_multiplicity_argument",
    )
    _equal(document["trust_boundary"], _PROP77_TRUST_BOUNDARY, label="trust_boundary")
    provenance = _object(document["provenance"], set(_PROP77_PROVENANCE), label="provenance")
    if provenance != _PROP77_PROVENANCE:
        _fail("provenance does not match the canonical v1 source record")


def _prop77_interval(
    value: Any, *, label: str, expected_index: int, expected_certifies: str
) -> tuple[Fraction, Fraction]:
    entry = _object(
        value,
        {"index", "ordinate", "certifies", "lower_reused", "upper_reused"},
        label=label,
    )
    _equal(entry["index"], expected_index, label=f"{label}.index")
    _equal(entry["certifies"], expected_certifies, label=f"{label}.certifies")
    ordinate = _object(
        entry["ordinate"],
        {"lower", "upper", "lower_decimal_outward", "upper_decimal_outward"},
        label=f"{label}.ordinate",
    )
    lower = _rational(ordinate["lower"], label=f"{label}.ordinate.lower")
    upper = _rational(ordinate["upper"], label=f"{label}.ordinate.upper")
    if not 0 < lower <= upper:
        _fail(f"{label}.ordinate is not a positive nonempty interval")
    if _rational(entry["lower_reused"], label=f"{label}.lower_reused") != lower:
        _fail(f"{label}.lower_reused does not equal ordinate.lower")
    if _rational(entry["upper_reused"], label=f"{label}.upper_reused") != upper:
        _fail(f"{label}.upper_reused does not equal ordinate.upper")
    _check_floor_decimal(
        ordinate["lower_decimal_outward"], lower, label=f"{label}.ordinate.lower_decimal_outward"
    )
    _check_ceiling_decimal(
        ordinate["upper_decimal_outward"], upper, label=f"{label}.ordinate.upper_decimal_outward"
    )
    return lower, upper


def _prop77_zero_count(document: dict[str, Any]) -> None:
    zero_count = _object(
        document["zero_count"],
        {"arb_result_exact", "count", "counting_convention", "height"},
        label="zero_count",
    )
    _true(zero_count["arb_result_exact"], label="zero_count.arb_result_exact")
    _equal(zero_count["count"], _PROP77_COUNT, label="zero_count.count")
    _equal(zero_count["height"], "20000", label="zero_count.height")
    _equal(
        zero_count["counting_convention"],
        _PROP77_COUNTING_CONVENTION,
        label="zero_count.counting_convention",
    )


def _prop77_isolation(document: dict[str, Any]) -> tuple[str, Fraction]:
    isolation = _object(
        document["isolation"],
        {
            "all_consecutive_ordinate_balls_disjoint",
            "all_ordinates_positive",
            "all_real_parts_exact",
            "critical_line_real_part",
            "first_excluded",
            "last_included",
            "minimum_consecutive_gap",
            "minimum_gap_after_index",
            "ordinate_intervals_sha256",
            "reciprocal_sum",
            "requested_indices",
            "returned_records",
        },
        label="isolation",
    )
    for field in (
        "all_consecutive_ordinate_balls_disjoint",
        "all_ordinates_positive",
        "all_real_parts_exact",
    ):
        _true(isolation[field], label=f"isolation.{field}")
    if _rational(
        isolation["critical_line_real_part"], label="isolation.critical_line_real_part"
    ) != Fraction(1, 2):
        _fail("isolation.critical_line_real_part is not exactly 1/2")
    _equal(
        isolation["requested_indices"],
        [1, _PROP77_REQUESTED],
        label="isolation.requested_indices",
    )
    _equal(
        isolation["returned_records"], _PROP77_REQUESTED, label="isolation.returned_records"
    )
    digest = _digest(
        isolation["ordinate_intervals_sha256"], label="isolation.ordinate_intervals_sha256"
    )
    if digest != _PROP77_ORDINATE_INTERVALS_SHA256:
        _fail(
            "isolation.ordinate_intervals_sha256 does not match the pinned "
            "retained interval digest"
        )
    minimum_gap = _rational(
        isolation["minimum_consecutive_gap"], label="isolation.minimum_consecutive_gap"
    )
    if minimum_gap <= 0:
        _fail("isolation.minimum_consecutive_gap must be strictly positive")
    _integer(
        isolation["minimum_gap_after_index"],
        label="isolation.minimum_gap_after_index",
        minimum=1,
        maximum=_PROP77_COUNT,
    )

    last_lower, last_upper = _prop77_interval(
        isolation["last_included"],
        label="isolation.last_included",
        expected_index=_PROP77_COUNT,
        expected_certifies="upper <= 20000",
    )
    next_lower, _next_upper = _prop77_interval(
        isolation["first_excluded"],
        label="isolation.first_excluded",
        expected_index=_PROP77_REQUESTED,
        expected_certifies="20000 < lower",
    )
    cutoff = Fraction(_PROP77_HEIGHT)
    if last_upper > cutoff:
        _fail("isolation.last_included does not end at or below height 20000")
    if next_lower <= cutoff:
        _fail("isolation.first_excluded does not start strictly above height 20000")
    if last_upper >= next_lower:
        _fail("the last included and first excluded intervals are not disjoint")
    if minimum_gap > next_lower - last_upper:
        _fail("minimum_consecutive_gap exceeds the displayed cutoff gap")
    if last_lower <= 0:
        _fail("isolation.last_included is not at positive height")

    reciprocal = _object(
        isolation["reciprocal_sum"],
        {
            "terms",
            "arb_lower",
            "arb_upper",
            "lower_decimal_outward",
            "upper_decimal_outward",
            "strict_target",
            "strict_target_decimal",
            "certified_margin_lower",
            "certified_margin_lower_decimal_outward",
            "proved_strict_upper_bound",
        },
        label="isolation.reciprocal_sum",
    )
    _equal(reciprocal["terms"], _PROP77_COUNT, label="isolation.reciprocal_sum.terms")
    lower = _rational(reciprocal["arb_lower"], label="isolation.reciprocal_sum.arb_lower")
    upper = _rational(reciprocal["arb_upper"], label="isolation.reciprocal_sum.arb_upper")
    if not 0 < lower <= upper:
        _fail("isolation.reciprocal_sum is not a positive nonempty interval")
    target = _rational(
        reciprocal["strict_target"], label="isolation.reciprocal_sum.strict_target"
    )
    if target != _PROP77_RECIPROCAL_TARGET:
        _fail("isolation.reciprocal_sum.strict_target is not exactly 257983/50000")
    target_decimal, _digits = _decimal(
        reciprocal["strict_target_decimal"],
        label="isolation.reciprocal_sum.strict_target_decimal",
    )
    if target_decimal != target or reciprocal["strict_target_decimal"] != "5.15966":
        _fail("isolation.reciprocal_sum.strict_target_decimal is inconsistent")
    if not upper < target:
        _fail("isolation.reciprocal_sum.arb_upper is not strictly below the target")
    margin = _rational(
        reciprocal["certified_margin_lower"],
        label="isolation.reciprocal_sum.certified_margin_lower",
    )
    if margin != target - upper or margin <= 0:
        _fail("isolation.reciprocal_sum certified margin is inconsistent")
    _check_floor_decimal(
        reciprocal["lower_decimal_outward"],
        lower,
        label="isolation.reciprocal_sum.lower_decimal_outward",
    )
    _check_ceiling_decimal(
        reciprocal["upper_decimal_outward"],
        upper,
        label="isolation.reciprocal_sum.upper_decimal_outward",
    )
    _check_floor_decimal(
        reciprocal["certified_margin_lower_decimal_outward"],
        margin,
        label="isolation.reciprocal_sum.certified_margin_lower_decimal_outward",
    )
    _true(
        reciprocal["proved_strict_upper_bound"],
        label="isolation.reciprocal_sum.proved_strict_upper_bound",
    )
    return digest, upper


def verify_prop77_flint_bytes(raw: bytes) -> dict[str, Any]:
    """Identify and structurally check the pinned Prop. 7.7 FLINT summary.

    The retained summary contains no zero-interval records.  Matching its
    pinned byte hash and interval-digest value therefore authenticates only
    which retained file was supplied; it does not check the digest preimage,
    rerun FLINT, or prove that any stored value has zeta-zero semantics.  A
    newly fabricated, internally self-consistent summary is rejected.
    """

    document = _load_canonical_json(raw, label="Prop77 FLINT summary")
    _object(
        document,
        {
            "author",
            "claim",
            "completeness_and_multiplicity_argument",
            "configuration",
            "isolation",
            "provenance",
            "schema",
            "trust_boundary",
            "versions",
            "zero_count",
        },
        label="Prop77 FLINT summary",
    )
    _prop77_static_sections(document)
    _prop77_zero_count(document)
    digest, reciprocal_upper = _prop77_isolation(document)
    artifact_sha256 = hashlib.sha256(raw).hexdigest()
    if artifact_sha256 != _PROP77_RETAINED_ARTIFACT_SHA256:
        _fail(
            "Prop77 FLINT summary bytes do not match the pinned retained "
            "artifact SHA-256"
        )
    return {
        "accepted": True,
        "accepted_as": "pinned retained summary only; not an analytic certificate",
        "artifact_kind": "ch25_prop77_flint_summary",
        "schema": PROP77_SCHEMA,
        "verification_class": "pinned_summary_identity_and_internal_arithmetic_only",
        "acceptance_scope": (
            "exact pinned bytes plus stored-field consistency; no FLINT or "
            "zeta semantics"
        ),
        "artifact_sha256": artifact_sha256,
        "artifact_bytes_match_pinned_sha256": True,
        "stored_configuration_matches_pinned_value": True,
        "stored_claim_height_cutoff": _PROP77_HEIGHT,
        "stored_claim_multiplicity_count": _PROP77_COUNT,
        "self_reported_zero_record_count": _PROP77_REQUESTED,
        "ordinate_intervals_sha256": digest,
        "ordinate_digest_matches_pinned_value": True,
        "stored_count_fields_internally_consistent": True,
        "stored_cutoff_endpoint_fractions_internally_consistent": True,
        "stored_reciprocal_endpoints_arithmetically_below_target": True,
        "stored_reciprocal_upper_numerator": reciprocal_upper.numerator,
        "stored_reciprocal_upper_denominator": reciprocal_upper.denominator,
        "ordinate_digest_preimage_verified": False,
        "flint_replay_performed": False,
        "self_reported_flint_boolean_semantics_verified": False,
        "minimum_gap_preimage_verified": False,
        "reciprocal_sum_semantics_verified": False,
        "zeta_zero_isolation_semantics_verified": False,
        "zeta_zero_count_semantics_verified": False,
        "semantic_verification_performed": False,
        "analytic_claim_proved": False,
        "external_semantics_required": True,
    }


def verify_prop77_flint_file(path: str | Path) -> dict[str, Any]:
    """Read and verify a Prop. 7.7 FLINT summary from ``path``."""

    return verify_prop77_flint_bytes(
        read_analytic_artifact_bytes(path, label="Prop77 FLINT summary")
    )
