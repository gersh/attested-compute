# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed decoder for one PT21 block's one-sided Turing inputs.

The native producer evaluates the literal Arb formulas used by the pinned
``zeta_arb/turing.c`` implementation.  This decoder independently enforces the
campaign geometry, exact source identities, canonical reduced dyadic
endpoints, and the caller's expected block/required-sign-packet identity.  It
then exposes only the four intervals per side expected by
``platt_pt21_fused_artifact``.

This is a finite arithmetic boundary, not the analytic Turing theorem.  The
artifact is therefore required to keep ``analytic_turing_realization_proved``
false.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "sparkinterval.tg.platt-pt21-turing-inputs.v1"
ALGORITHM = "pinned-platt-pt21-one-sided-turing-inputs-flint-3.6-v1"
UPSTREAM_COMMIT = "42b21426718e542daa2b006dc05ea2d7f26426e6"
SOURCE_TURING_C_SHA256 = (
    "07305e04e85477749ced09325c9e78388dd55d6107aa526d3becde345a430c27"
)
FLINT_COMMIT = "8d5454b96761fafe4d5a9da76a369a602f500f49"
INTERPOLATION_PATCH_SHA256 = (
    "2bc33d3d4f6163ba5af8982f1272e9544154ed95bc6155a4ee215c4e425c85b3"
)
SOURCE_LOWER = 10_000_000_000
SOURCE_STEP = 1_008
SOURCE_BLOCK_COUNT = 2_966_443_783
TURING_WIDTH = 21
PRECISION_BITS = 128
REPLAY_PRECISION_BITS = 256
MAX_BYTES = 64 * 1024
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class PT21TuringInputsError(ValueError):
    """The artifact is malformed, incomplete, or bound to another block."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PT21TuringInputsError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _exact_object(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PT21TuringInputsError(f"{label} fields differ")
    return value


def _integer(value: object, label: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PT21TuringInputsError(f"{label} is not an integer")
    if minimum is not None and value < minimum:
        raise PT21TuringInputsError(f"{label} is below {minimum}")
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise PT21TuringInputsError(f"{label} is not lowercase SHA-256")
    return value


def _fraction(value: object, label: str) -> Fraction:
    item = _exact_object(value, {"numerator", "denominator"}, label)
    numerator = _integer(item["numerator"], f"{label}.numerator")
    denominator = _integer(item["denominator"], f"{label}.denominator", minimum=1)
    result = Fraction(numerator, denominator)
    if (result.numerator, result.denominator) != (numerator, denominator):
        raise PT21TuringInputsError(f"{label} is not in lowest terms")
    if denominator & (denominator - 1):
        raise PT21TuringInputsError(f"{label} is not dyadic")
    return result


Interval = tuple[Fraction, Fraction]


def _interval(value: object, label: str) -> Interval:
    item = _exact_object(value, {"lo", "hi"}, label)
    result = (
        _fraction(item["lo"], f"{label}.lo"),
        _fraction(item["hi"], f"{label}.hi"),
    )
    if result[0] > result[1]:
        raise PT21TuringInputsError(f"{label} has reversed endpoints")
    return result


def _parse_values(value: object, label: str) -> dict[str, Interval]:
    item = _exact_object(
        value,
        {"s_bound", "log_pi", "im_gamma_integral", "pi"},
        label,
    )
    result = {name: _interval(item[name], f"{label}.{name}") for name in item}
    for name in ("s_bound", "log_pi", "pi"):
        if result[name][0] <= 0:
            raise PT21TuringInputsError(f"{label}.{name} is not strictly positive")
    return result


def validate(
    value: object,
    *,
    expected_block: int,
    expected_packet_sha256: str,
) -> dict[str, object]:
    """Validate one artifact against an independently supplied identity."""

    if isinstance(expected_block, bool) or not isinstance(expected_block, int):
        raise PT21TuringInputsError("expected_block is not an integer")
    if not 0 <= expected_block < SOURCE_BLOCK_COUNT:
        raise PT21TuringInputsError("expected_block is outside the source campaign")
    if (
        not isinstance(expected_packet_sha256, str)
        or SHA256_RE.fullmatch(expected_packet_sha256) is None
    ):
        raise PT21TuringInputsError(
            "expected_packet_sha256 is not lowercase SHA-256"
        )

    item = _exact_object(
        value,
        {
            "algorithm",
            "block",
            "flint_commit",
            "inputs",
            "precision_bits",
            "replay_precision_bits",
            "required_sign_packet_sha256",
            "schema",
            "source_identity",
            "semantic_status",
        },
        "Turing input artifact",
    )
    block = _integer(item["block"], "block", minimum=0)
    packet_sha256 = _sha256(
        item["required_sign_packet_sha256"], "required_sign_packet_sha256"
    )
    if (
        item["schema"] != SCHEMA
        or item["algorithm"] != ALGORITHM
        or item["flint_commit"] != FLINT_COMMIT
    ):
        raise PT21TuringInputsError("producer schema, algorithm, or FLINT pin differs")
    if block != expected_block or packet_sha256 != expected_packet_sha256:
        raise PT21TuringInputsError("caller-supplied block/packet identity differs")
    if block >= SOURCE_BLOCK_COUNT:
        raise PT21TuringInputsError("block is outside the source campaign")
    if (
        item["precision_bits"] != PRECISION_BITS
        or item["replay_precision_bits"] != REPLAY_PRECISION_BITS
    ):
        raise PT21TuringInputsError("retained or replay precision differs")

    height_lower = SOURCE_LOWER + block * SOURCE_STEP
    height_upper = height_lower + SOURCE_STEP
    source = _exact_object(
        item["source_identity"],
        {
            "height_lower",
            "height_upper",
            "interpolation_patch_sha256",
            "source_turing_c_sha256",
            "upstream_commit",
        },
        "source_identity",
    )
    if source != {
        "height_lower": height_lower,
        "height_upper": height_upper,
        "interpolation_patch_sha256": INTERPOLATION_PATCH_SHA256,
        "source_turing_c_sha256": SOURCE_TURING_C_SHA256,
        "upstream_commit": UPSTREAM_COMMIT,
    }:
        raise PT21TuringInputsError("source identity or block geometry differs")

    raw_inputs = _exact_object(item["inputs"], {"lower", "upper"}, "inputs")
    geometries = {
        "lower": ("turing_min", height_lower - TURING_WIDTH, height_lower),
        "upper": ("turing_max", height_upper, height_upper + TURING_WIDTH),
    }
    parsed_inputs: dict[str, dict[str, Interval]] = {}
    payload: dict[str, object] = {}
    for side_name in ("lower", "upper"):
        side = _exact_object(
            raw_inputs[side_name],
            {"function", "interval", "values"},
            f"inputs.{side_name}",
        )
        function, a, b = geometries[side_name]
        interval = _exact_object(
            side["interval"], {"a", "b"}, f"inputs.{side_name}.interval"
        )
        if (
            side["function"] != function
            or interval["a"] != a
            or interval["b"] != b
            or b - a != TURING_WIDTH
        ):
            raise PT21TuringInputsError(
                f"inputs.{side_name} is not the source one-sided interval"
            )
        parsed_inputs[side_name] = _parse_values(
            side["values"], f"inputs.{side_name}.values"
        )
        # Preserve the exact canonical rational wire shape consumed by the
        # fused source-trace finalizer.
        payload[side_name] = side["values"]

    # pi and log(pi) are block-independent source inputs.  Requiring the two
    # independently evaluated sides to agree exactly catches partial output
    # splicing and side substitution before the final trace is built.
    for name in ("pi", "log_pi"):
        if parsed_inputs["lower"][name] != parsed_inputs["upper"][name]:
            raise PT21TuringInputsError(f"lower/upper {name} intervals differ")

    status = _exact_object(
        item["semantic_status"],
        {
            "analytic_turing_realization_proved",
            "arb_interval_arithmetic_executed",
            "hardy_z_endpoint_realization_proved",
        },
        "semantic_status",
    )
    if status != {
        "analytic_turing_realization_proved": False,
        "arb_interval_arithmetic_executed": True,
        "hardy_z_endpoint_realization_proved": False,
    }:
        raise PT21TuringInputsError("semantic status overclaims the finite artifact")

    return {
        "block": block,
        "required_sign_packet_sha256": packet_sha256,
        "height_lower": height_lower,
        "height_upper": height_upper,
        "turing_inputs": payload,
    }


def load(
    path: Path,
    *,
    expected_block: int,
    expected_packet_sha256: str,
) -> dict[str, object]:
    """Load canonical JSON and validate it against the caller's identity."""

    if path.is_symlink() or not path.is_file():
        raise PT21TuringInputsError(f"artifact is not a regular file: {path}")
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_BYTES:
        raise PT21TuringInputsError("artifact has an invalid byte length")
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PT21TuringInputsError(f"artifact is not strict JSON: {error}") from error
    if raw != _canonical(value) + b"\n":
        raise PT21TuringInputsError("artifact is not canonical JSON with one newline")
    result = validate(
        value,
        expected_block=expected_block,
        expected_packet_sha256=expected_packet_sha256,
    )
    result["artifact_sha256"] = hashlib.sha256(raw).hexdigest()
    return result


__all__ = [
    "PT21TuringInputsError",
    "load",
    "validate",
]
