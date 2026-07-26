# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independent finite validator for the PT21 stationary fallback trace.

The native resolver performs the Arb interpolation and deterministic replay.
This module deliberately does not promote those intervals to Hardy-Z facts.
It checks the canonical wire shape, source identities, exact rational bracket
geometry, strict signs, all-or-nothing failure behavior, and the
domain-separated resolution digest before a trace can be inserted into the
larger PT21 source artifact.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "sparkinterval.tg.platt-pt21-stationary-trace.v1"
SCHEMA_V2 = "sparkinterval.tg.platt-pt21-stationary-trace.v2"
UPSTREAM_COMMIT = "42b21426718e542daa2b006dc05ea2d7f26426e6"
INTERPOLATION_PATCH_SHA256 = (
    "2bc33d3d4f6163ba5af8982f1272e9544154ed95bc6155a4ee215c4e425c85b3"
)
RESOLUTION_DOMAIN = b"sparkinterval/tg/platt-pt21-stationary-resolutions/v1\0"
MAXIMUM_BYTES = 16 * 1024 * 1024
MAXIMUM_RESOLUTIONS = 10_000
SHA256_RE = re.compile(r"[0-9a-f]{64}")
STREAM_RANGES = {
    "left_flank": (-12_800, -12_288),
    "main": (-12_288, 12_288),
    "right_flank": (12_288, 12_800),
}


class PT21StationaryTraceError(RuntimeError):
    """A stationary trace is malformed, partial, or semantically overclaims."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PT21StationaryTraceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _exact_object(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PT21StationaryTraceError(f"{label} fields differ")
    return value


def _integer(value: object, label: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PT21StationaryTraceError(f"{label} is not an integer")
    if minimum is not None and value < minimum:
        raise PT21StationaryTraceError(f"{label} is below {minimum}")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise PT21StationaryTraceError(f"{label} is not Boolean")
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise PT21StationaryTraceError(f"{label} is not lowercase SHA-256")
    return value


def _rational(value: object, label: str) -> Fraction:
    item = _exact_object(value, {"denominator", "numerator"}, label)
    numerator = _integer(item["numerator"], f"{label}.numerator")
    denominator = _integer(
        item["denominator"], f"{label}.denominator", minimum=1
    )
    result = Fraction(numerator, denominator)
    if (result.numerator, result.denominator) != (numerator, denominator):
        raise PT21StationaryTraceError(f"{label} is not in lowest terms")
    return result


def _interval(value: object, label: str) -> tuple[Fraction, Fraction]:
    item = _exact_object(value, {"hi", "lo"}, label)
    result = (
        _rational(item["lo"], f"{label}.lo"),
        _rational(item["hi"], f"{label}.hi"),
    )
    if result[0] > result[1]:
        raise PT21StationaryTraceError(f"{label} has reversed endpoints")
    return result


def _strict_sign(value: tuple[Fraction, Fraction], label: str) -> bool:
    if value[0] > 0:
        return True
    if value[1] < 0:
        return False
    raise PT21StationaryTraceError(f"{label} contains zero")


def _resolution(value: object, index: int) -> tuple[str, int]:
    label = f"stationary_resolutions[{index}]"
    item = _exact_object(
        value,
        {
            "lower_offset",
            "lower_value",
            "midpoint_offset",
            "midpoint_value",
            "outer_left_sample",
            "outer_right_sample",
            "stream",
            "upper_offset",
            "upper_value",
        },
        label,
    )
    stream = item["stream"]
    if stream not in STREAM_RANGES:
        raise PT21StationaryTraceError(f"{label}.stream is unknown")
    left = _integer(item["outer_left_sample"], f"{label}.outer_left_sample")
    right = _integer(item["outer_right_sample"], f"{label}.outer_right_sample")
    if right != left + 2:
        raise PT21StationaryTraceError(f"{label} is not one source cell")
    stream_lower, stream_upper = STREAM_RANGES[stream]
    if left < stream_lower or right > stream_upper:
        raise PT21StationaryTraceError(f"{label} leaves its source stream")
    lower = _rational(item["lower_offset"], f"{label}.lower_offset")
    midpoint = _rational(item["midpoint_offset"], f"{label}.midpoint_offset")
    upper = _rational(item["upper_offset"], f"{label}.upper_offset")
    if not Fraction(left) <= lower < midpoint < upper <= Fraction(right):
        raise PT21StationaryTraceError(f"{label} dyadic brackets are unordered")
    for name, coordinate in (
        ("lower_offset", lower),
        ("midpoint_offset", midpoint),
        ("upper_offset", upper),
    ):
        if coordinate.denominator & (coordinate.denominator - 1):
            raise PT21StationaryTraceError(f"{label}.{name} is not dyadic")
    lower_value = _interval(item["lower_value"], f"{label}.lower_value")
    midpoint_value = _interval(item["midpoint_value"], f"{label}.midpoint_value")
    upper_value = _interval(item["upper_value"], f"{label}.upper_value")
    lower_positive = _strict_sign(lower_value, f"{label}.lower_value")
    midpoint_positive = _strict_sign(midpoint_value, f"{label}.midpoint_value")
    upper_positive = _strict_sign(upper_value, f"{label}.upper_value")
    if lower_positive != upper_positive or lower_positive == midpoint_positive:
        raise PT21StationaryTraceError(
            f"{label} does not encode two touching strict brackets"
        )
    return stream, left


def validate(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PT21StationaryTraceError("stationary trace fields differ")
    schema = value.get("schema")
    if schema not in (SCHEMA, SCHEMA_V2):
        raise PT21StationaryTraceError("stationary source identity differs")
    keys = {
        "accepted",
        "ambiguous_input_disks",
        "candidate_count",
        "error",
        "failure_flags",
        "input_sha256",
        "interpolation_evaluations",
        "interpolation_patch_sha256",
        "maximum_depth",
        "precision_bits",
        "refinements_applied",
        "replay_accepted",
        "required_sample_count",
        "resolution_sha256",
        "schema",
        "semantic_status",
        "stationary_resolutions",
        "upstream_commit",
    }
    if schema == SCHEMA_V2:
        keys.add("precision_replay_audit")
    item = _exact_object(
        value,
        keys,
        "stationary trace",
    )
    if (
        item["upstream_commit"] != UPSTREAM_COMMIT
        or item["interpolation_patch_sha256"] != INTERPOLATION_PATCH_SHA256
        or item["precision_bits"] != 128
        or item["required_sample_count"] != 25_741
    ):
        raise PT21StationaryTraceError("stationary source identity differs")
    accepted = _boolean(item["accepted"], "accepted")
    replay = _boolean(item["replay_accepted"], "replay_accepted")
    ambiguous = _integer(
        item["ambiguous_input_disks"], "ambiguous_input_disks", minimum=0
    )
    candidates = _integer(item["candidate_count"], "candidate_count", minimum=0)
    failures = _integer(item["failure_flags"], "failure_flags", minimum=0)
    evaluations = _integer(
        item["interpolation_evaluations"],
        "interpolation_evaluations",
        minimum=0,
    )
    depth = _integer(item["maximum_depth"], "maximum_depth", minimum=1)
    refinements = _integer(
        item["refinements_applied"], "refinements_applied", minimum=0
    )
    if depth > 96 or candidates > MAXIMUM_RESOLUTIONS or refinements > 10_000:
        raise PT21StationaryTraceError("stationary bounds exceed production caps")
    _sha256(item["input_sha256"], "input_sha256")
    resolution_sha256 = _sha256(
        item["resolution_sha256"], "resolution_sha256"
    )
    if not isinstance(item["error"], str):
        raise PT21StationaryTraceError("error is not a string")
    status = _exact_object(
        item["semantic_status"],
        {
            "analytic_turing_realization_proved",
            "flint_to_mathlib_realization_proved",
            "hardy_z_endpoint_realization_proved",
        },
        "semantic_status",
    )
    if any(_boolean(status[key], f"semantic_status.{key}") for key in status):
        raise PT21StationaryTraceError("finite stationary trace overclaims semantics")
    resolutions = item["stationary_resolutions"]
    if not isinstance(resolutions, list) or len(resolutions) > MAXIMUM_RESOLUTIONS:
        raise PT21StationaryTraceError("stationary_resolutions is not bounded")
    previous: tuple[int, int] | None = None
    stream_rank = {"left_flank": 0, "main": 1, "right_flank": 2}
    for index, resolution in enumerate(resolutions):
        stream, left = _resolution(resolution, index)
        key = (stream_rank[stream], left)
        if previous is not None and key <= previous:
            raise PT21StationaryTraceError(
                "stationary resolutions are duplicate or not canonical"
            )
        previous = key
    if schema == SCHEMA_V2:
        audits = item["precision_replay_audit"]
        if not isinstance(audits, list) or len(audits) != len(resolutions):
            raise PT21StationaryTraceError(
                "precision replay audit count differs"
            )
        for index, (resolution, audit_value) in enumerate(
            zip(resolutions, audits, strict=True)
        ):
            audit = _exact_object(
                audit_value,
                {
                    "base_precision_bits",
                    "lower",
                    "midpoint",
                    "outer_left_sample",
                    "outer_right_sample",
                    "replay_precision_bits",
                    "stream",
                    "upper",
                },
                f"precision_replay_audit[{index}]",
            )
            if (
                audit["base_precision_bits"] != 128
                or audit["replay_precision_bits"] != 192
                or audit["stream"] != resolution["stream"]
                or audit["outer_left_sample"]
                != resolution["outer_left_sample"]
                or audit["outer_right_sample"]
                != resolution["outer_right_sample"]
            ):
                raise PT21StationaryTraceError(
                    f"precision_replay_audit[{index}] identity differs"
                )
            for endpoint in ("lower", "midpoint", "upper"):
                endpoint_audit = _exact_object(
                    audit[endpoint],
                    {
                        "base_interval",
                        "replay_interval",
                        "retained_hull",
                    },
                    f"precision_replay_audit[{index}].{endpoint}",
                )
                base = _interval(
                    endpoint_audit["base_interval"],
                    f"precision_replay_audit[{index}].{endpoint}.base_interval",
                )
                replay_interval = _interval(
                    endpoint_audit["replay_interval"],
                    f"precision_replay_audit[{index}].{endpoint}.replay_interval",
                )
                hull = _interval(
                    endpoint_audit["retained_hull"],
                    f"precision_replay_audit[{index}].{endpoint}.retained_hull",
                )
                expected_hull = (
                    min(base[0], replay_interval[0]),
                    max(base[1], replay_interval[1]),
                )
                retained = _interval(
                    resolution[f"{endpoint}_value"],
                    f"stationary_resolutions[{index}].{endpoint}_value",
                )
                if hull != expected_hull or retained != hull:
                    raise PT21StationaryTraceError(
                        f"precision_replay_audit[{index}].{endpoint} "
                        "is not the exact outward hull"
                    )
                base_sign = _strict_sign(
                    base,
                    f"precision_replay_audit[{index}].{endpoint}.base_interval",
                )
                replay_sign = _strict_sign(
                    replay_interval,
                    f"precision_replay_audit[{index}].{endpoint}.replay_interval",
                )
                hull_sign = _strict_sign(
                    hull,
                    f"precision_replay_audit[{index}].{endpoint}.retained_hull",
                )
                if base_sign != replay_sign or base_sign != hull_sign:
                    raise PT21StationaryTraceError(
                        f"precision_replay_audit[{index}].{endpoint} "
                        "strict signs differ"
                    )
    actual_digest = hashlib.sha256(
        RESOLUTION_DOMAIN + _canonical(resolutions)
    ).hexdigest()
    if actual_digest != resolution_sha256:
        raise PT21StationaryTraceError("stationary resolution digest differs")
    if accepted:
        if (
            failures != 0
            or not replay
            or item["error"]
            or len(resolutions) != candidates
            or ambiguous != refinements
            or evaluations < candidates
            or evaluations > 2 * depth * candidates
        ):
            raise PT21StationaryTraceError("accepted stationary trace is incomplete")
    elif replay or failures == 0 or resolutions:
        raise PT21StationaryTraceError("failed stationary trace retained partial output")
    return item


def load(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise PT21StationaryTraceError(f"trace is not a regular file: {path}")
    raw = path.read_bytes()
    if not raw or len(raw) > MAXIMUM_BYTES:
        raise PT21StationaryTraceError("trace has an invalid byte length")
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PT21StationaryTraceError(f"trace is not strict JSON: {error}") from error
    if raw != _canonical(value) + b"\n":
        raise PT21StationaryTraceError("trace is not canonical JSON")
    return validate(value)
