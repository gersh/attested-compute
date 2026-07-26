# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Deterministic PT21 required-packet, event, and Turing finalization.

The H100 transform retains one compact required-region DD/sign packet per
window.  A measured source worker additionally emits a small canonical source
trace containing only the dyadic stationary resolutions and four directed
Arb intervals for each of the two source-shaped 21-unit Turing calls.  This
module independently
replays the finite work with :class:`fractions.Fraction`:

* recover exact rational endpoint disks from every binary64 DD sample;
* reproduce direct sign events and the source stationary-point predicate;
* bind two dyadic stationary brackets to one multiplicity-two integer cell;
* recompute both Turing quotients, their unique roundings, and the closure;
* emit the exact v2 artifact checked by ``PT21ArtifactBinding``; and
* Merkle-finalize contiguous block and shard streams without accepting gaps.

This is deliberately not an analytic proof.  In particular, neither a DD
disk nor a source-trace interval is promoted here to a theorem about Hardy Z,
and the analytic Turing inequalities remain the explicit Lean premises.  A
production confidential-compute invocation must bind the measured producer
and the retained trace/root before the single trusted-run axiom is used.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Iterable

from tg_verifier.platt_pt21_lean_artifact import (
    SOURCE_BLOCK_COUNT,
    SOURCE_HALF_STEP,
    SOURCE_LOWER,
    SOURCE_SPACING,
    SOURCE_STEP,
    STREAM_RANGES,
    UPSTREAM_COMMIT,
    PT21LeanArtifactError,
    load as load_block_artifact,
    validate as validate_block_artifact,
)
from tg_verifier.platt_required_sign_packet import (
    REQUIRED_COUNT,
    RequiredSignPacket,
    RequiredSample,
    load_required_sign_packet,
)


TRACE_SCHEMA = "sparkinterval.tg.platt-pt21-fused-source-trace.v1"
SHARD_SCHEMA = "sparkinterval.tg.platt-pt21-fused-shard.v1"
FINAL_SCHEMA = "sparkinterval.tg.platt-pt21-fused-final.v1"
INTERPOLATION_PATCH_SHA256 = (
    "2bc33d3d4f6163ba5af8982f1272e9544154ed95bc6155a4ee215c4e425c85b3"
)
REQUIRED_OFFSET_LOWER = -12_870
REQUIRED_OFFSET_UPPER = 12_870
SOURCE_HEIGHT = 3_000_175_332_800
SOURCE_HEIGHT_COUNT = 12_363_153_437_138
SOURCE_LOWER_COUNT = 32_130_158_315
MAX_TRACE_BYTES = 16 * 1024 * 1024
MAX_BLOCK_BYTES = 16 * 1024 * 1024
SHA256_RE = re.compile(r"[0-9a-f]{64}")
BLOCK_LEAF_DOMAIN = b"sparkinterval/tg/platt-pt21-fused-block-leaf/v1\0"
BLOCK_NODE_DOMAIN = b"sparkinterval/tg/platt-pt21-fused-block-node/v1\0"
SHARD_RECEIPT_DOMAIN = b"sparkinterval/tg/platt-pt21-fused-shard-receipt/v1\0"
SHARD_LEAF_DOMAIN = b"sparkinterval/tg/platt-pt21-fused-shard-leaf/v1\0"
SHARD_NODE_DOMAIN = b"sparkinterval/tg/platt-pt21-fused-shard-node/v1\0"
FINAL_RECEIPT_DOMAIN = b"sparkinterval/tg/platt-pt21-fused-final-receipt/v1\0"


class PT21FusedArtifactError(RuntimeError):
    """A source trace, block, shard, or final chain failed closed."""


Interval = tuple[Fraction, Fraction]
DirectedFloatInterval = tuple[float, float]


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _domain_digest(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + _canonical(value)).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PT21FusedArtifactError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _exact_object(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PT21FusedArtifactError(f"{label} fields differ")
    return value


def _integer(value: object, label: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PT21FusedArtifactError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise PT21FusedArtifactError(f"{label} is below {minimum}")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise PT21FusedArtifactError(f"{label} must be Boolean")
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise PT21FusedArtifactError(f"{label} must be lowercase SHA-256 hex")
    return value


def _fraction(value: object, label: str) -> Fraction:
    item = _exact_object(value, {"numerator", "denominator"}, label)
    numerator = _integer(item["numerator"], f"{label}.numerator")
    denominator = _integer(item["denominator"], f"{label}.denominator", minimum=1)
    result = Fraction(numerator, denominator)
    if (result.numerator, result.denominator) != (numerator, denominator):
        raise PT21FusedArtifactError(f"{label} is not in canonical lowest terms")
    return result


def _interval(value: object, label: str) -> Interval:
    item = _exact_object(value, {"lo", "hi"}, label)
    result = (_fraction(item["lo"], f"{label}.lo"), _fraction(item["hi"], f"{label}.hi"))
    if result[0] > result[1]:
        raise PT21FusedArtifactError(f"{label} is an invalid interval")
    return result


def _fraction_json(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _interval_json(value: Interval) -> dict[str, object]:
    return {"lo": _fraction_json(value[0]), "hi": _fraction_json(value[1])}


def _endpoint_json(value: Interval) -> dict[str, object]:
    if value[0] > 0:
        positive = True
    elif value[1] < 0:
        positive = False
    else:
        raise PT21FusedArtifactError("endpoint interval contains zero")
    return {"enclosure": _interval_json(value), "positive": positive}


def _sample_interval(sample: RequiredSample) -> Interval:
    center = Fraction.from_float(sample.center_hi) + Fraction.from_float(sample.center_lo)
    radius = Fraction.from_float(sample.radius)
    result = (center - radius, center + radius)
    if (sample.positive and result[0] <= 0) or (
        not sample.positive and result[1] >= 0
    ):
        raise PT21FusedArtifactError("required sample sign is not implied by its exact DD disk")
    return result


def _sample_at(samples: tuple[RequiredSample, ...], offset: int) -> RequiredSample:
    index = offset - REQUIRED_OFFSET_LOWER
    if not 0 <= index < len(samples):
        raise PT21FusedArtifactError("sample offset is outside the required-region packet")
    return samples[index]


def _strict_gt(left: Interval, right: Interval) -> bool:
    """Exact counterpart of the source's strict ``arb_gt`` predicate."""

    return left[0] > right[1]


def _directed_sample_interval(sample: RequiredSample) -> DirectedFloatInterval:
    """Cheap binary64 enclosure used only to certify strict comparisons.

    Each arithmetic result is widened by one representable number in the
    required direction.  If an intermediate overflows, the uninformative
    whole-line enclosure forces the exact-rational fallback.
    """

    center = sample.center_hi + sample.center_lo
    if not math.isfinite(center):
        return (-math.inf, math.inf)
    center_lower = math.nextafter(center, -math.inf)
    center_upper = math.nextafter(center, math.inf)
    lower = center_lower - sample.radius
    upper = center_upper + sample.radius
    if not math.isfinite(lower) or not math.isfinite(upper):
        return (-math.inf, math.inf)
    return (
        math.nextafter(lower, -math.inf),
        math.nextafter(upper, math.inf),
    )


def _exact_interval_at(
    samples: tuple[RequiredSample, ...],
    cache: dict[int, Interval],
    offset: int,
) -> Interval:
    index = offset - REQUIRED_OFFSET_LOWER
    if not 0 <= index < len(samples):
        raise PT21FusedArtifactError(
            "sample interval offset is outside the required-region packet"
        )
    result = cache.get(index)
    if result is None:
        result = _sample_interval(samples[index])
        cache[index] = result
    return result


def _is_stationary_candidate_exact(
    samples: tuple[RequiredSample, ...],
    left: int,
    cache: dict[int, Interval] | None = None,
) -> bool:
    """Slow exact reference predicate used by the fallback and tests."""

    first = _sample_at(samples, left)
    middle = _sample_at(samples, left + 1)
    right = _sample_at(samples, left + 2)
    if not (first.positive == middle.positive == right.positive):
        return False
    if cache is None:
        first_interval = _sample_interval(first)
        middle_interval = _sample_interval(middle)
        right_interval = _sample_interval(right)
    else:
        first_interval = _exact_interval_at(samples, cache, left)
        middle_interval = _exact_interval_at(samples, cache, left + 1)
        right_interval = _exact_interval_at(samples, cache, left + 2)
    if middle.positive:
        return _strict_gt(first_interval, middle_interval) and _strict_gt(
            right_interval, middle_interval
        )
    return _strict_gt(middle_interval, first_interval) and _strict_gt(
        middle_interval, right_interval
    )


def _is_stationary_candidate(
    samples: tuple[RequiredSample, ...],
    directed: tuple[DirectedFloatInterval, ...],
    exact_cache: dict[int, Interval],
    left: int,
) -> bool:
    first = _sample_at(samples, left)
    middle = _sample_at(samples, left + 1)
    right = _sample_at(samples, left + 2)
    if not (first.positive == middle.positive == right.positive):
        return False
    first_interval = directed[left - REQUIRED_OFFSET_LOWER]
    middle_interval = directed[left + 1 - REQUIRED_OFFSET_LOWER]
    right_interval = directed[left + 2 - REQUIRED_OFFSET_LOWER]
    if middle.positive:
        certified = (
            first_interval[0] > middle_interval[1]
            and right_interval[0] > middle_interval[1]
        )
        rejected = (
            first == middle
            or right == middle
            or first_interval[1] <= middle_interval[0]
            or right_interval[1] <= middle_interval[0]
        )
    else:
        certified = (
            middle_interval[0] > first_interval[1]
            and middle_interval[0] > right_interval[1]
        )
        rejected = (
            first == middle
            or right == middle
            or middle_interval[1] <= first_interval[0]
            or middle_interval[1] <= right_interval[0]
        )
    if certified:
        return True
    if rejected:
        return False
    return _is_stationary_candidate_exact(samples, left, exact_cache)


def _load_canonical_json(path: Path, *, maximum: int, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise PT21FusedArtifactError(f"{label} is not a regular file: {path}")
    raw = path.read_bytes()
    if not raw or len(raw) > maximum:
        raise PT21FusedArtifactError(f"{label} has an invalid byte length")
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PT21FusedArtifactError(f"{label} is not strict JSON: {error}") from error
    if not isinstance(value, dict):
        raise PT21FusedArtifactError(f"{label} must be a JSON object")
    if raw != _canonical(value) + b"\n":
        raise PT21FusedArtifactError(f"{label} is not canonical JSON with one newline")
    return value, raw


def _parse_trace(path: Path, *, packet_sha256: str, block: int) -> tuple[dict[str, Any], str]:
    value, raw = _load_canonical_json(path, maximum=MAX_TRACE_BYTES, label="source trace")
    item = _exact_object(
        value,
        {
            "schema",
            "upstream_commit",
            "interpolation_patch_sha256",
            "block",
            "required_sign_packet_sha256",
            "producer",
            "stationary_resolutions",
            "turing_inputs",
            "semantic_status",
        },
        "source trace",
    )
    if (
        item["schema"] != TRACE_SCHEMA
        or item["upstream_commit"] != UPSTREAM_COMMIT
        or item["interpolation_patch_sha256"] != INTERPOLATION_PATCH_SHA256
        or item["block"] != block
        or item["required_sign_packet_sha256"] != packet_sha256
    ):
        raise PT21FusedArtifactError("source trace identity differs")
    producer = _exact_object(
        item["producer"],
        {
            "worker_sha256",
            "worker_size_bytes",
            "precision_bits",
            "all_required_samples_certified",
            "all_stationary_queries_resolved",
        },
        "source trace producer",
    )
    _sha256(producer["worker_sha256"], "producer.worker_sha256")
    _integer(producer["worker_size_bytes"], "producer.worker_size_bytes", minimum=1)
    if producer["precision_bits"] != 128:
        raise PT21FusedArtifactError("source trace precision differs from 128 bits")
    if (
        _boolean(
            producer["all_required_samples_certified"],
            "producer.all_required_samples_certified",
        )
        is not True
        or _boolean(
            producer["all_stationary_queries_resolved"],
            "producer.all_stationary_queries_resolved",
        )
        is not True
    ):
        raise PT21FusedArtifactError("source trace advertises an incomplete block")
    status = _exact_object(
        item["semantic_status"],
        {
            "hardy_z_endpoint_realization_proved",
            "main_multiplicity_realization_proved",
            "analytic_turing_realization_proved",
        },
        "source trace semantic status",
    )
    if any(
        _boolean(status[key], f"semantic_status.{key}")
        for key in status
    ):
        raise PT21FusedArtifactError(
            "finite source trace must not claim an unimplemented analytic realization"
        )
    if not isinstance(item["stationary_resolutions"], list):
        raise PT21FusedArtifactError("stationary_resolutions must be a list")
    turing = _exact_object(item["turing_inputs"], {"lower", "upper"}, "turing_inputs")
    parsed_turing: dict[str, dict[str, Interval]] = {}
    for side_name in ("lower", "upper"):
        side = _exact_object(
            turing[side_name],
            {"s_bound", "log_pi", "im_gamma_integral", "pi"},
            f"turing_inputs.{side_name}",
        )
        parsed_turing[side_name] = {
            key: _interval(side[key], f"turing_inputs.{side_name}.{key}")
            for key in side
        }
        if (
            parsed_turing[side_name]["s_bound"][0] < 0
            or parsed_turing[side_name]["pi"][0] <= 0
        ):
            raise PT21FusedArtifactError(
                f"Turing {side_name} S bound or pi interval has the wrong sign"
            )
    normalized = dict(item)
    normalized["turing_inputs"] = parsed_turing
    return normalized, hashlib.sha256(raw).hexdigest()


def _parse_resolution(raw: object, label: str) -> dict[str, object]:
    item = _exact_object(
        raw,
        {
            "stream",
            "outer_left_sample",
            "outer_right_sample",
            "lower_offset",
            "midpoint_offset",
            "upper_offset",
            "lower_value",
            "midpoint_value",
            "upper_value",
        },
        label,
    )
    stream = item["stream"]
    if stream not in STREAM_RANGES:
        raise PT21FusedArtifactError(f"{label}.stream is unknown")
    outer_left = _integer(item["outer_left_sample"], f"{label}.outer_left_sample")
    outer_right = _integer(item["outer_right_sample"], f"{label}.outer_right_sample")
    if outer_right != outer_left + 2:
        raise PT21FusedArtifactError(f"{label} is not one source stationary cell")
    lower = _fraction(item["lower_offset"], f"{label}.lower_offset")
    midpoint = _fraction(item["midpoint_offset"], f"{label}.midpoint_offset")
    upper = _fraction(item["upper_offset"], f"{label}.upper_offset")
    if not Fraction(outer_left) <= lower < midpoint < upper <= Fraction(outer_right):
        raise PT21FusedArtifactError(f"{label} dyadic offsets leave the conservative cell")
    values = {
        key: _interval(item[key], f"{label}.{key}")
        for key in ("lower_value", "midpoint_value", "upper_value")
    }
    lower_positive = values["lower_value"][0] > 0
    middle_positive = values["midpoint_value"][0] > 0
    upper_positive = values["upper_value"][0] > 0
    if any(lo <= 0 <= hi for lo, hi in values.values()):
        raise PT21FusedArtifactError(f"{label} contains a zero endpoint")
    if lower_positive != upper_positive or lower_positive == middle_positive:
        raise PT21FusedArtifactError(f"{label} does not contain two strict sign changes")
    return {
        "stream": stream,
        "outer_left_sample": outer_left,
        "outer_right_sample": outer_right,
        "lower_offset": lower,
        "midpoint_offset": midpoint,
        "upper_offset": upper,
        **values,
    }


def _bracket(
    lower: Fraction,
    upper: Fraction,
    lower_value: Interval,
    upper_value: Interval,
    resolver: str,
) -> dict[str, object]:
    return {
        "lower_offset": _fraction_json(lower),
        "upper_offset": _fraction_json(upper),
        "lower_value": _endpoint_json(lower_value),
        "upper_value": _endpoint_json(upper_value),
        "resolver": resolver,
        "fallback_receipt_sha256": None,
    }


def _build_stream(
    samples: tuple[RequiredSample, ...],
    directed: tuple[DirectedFloatInterval, ...],
    exact_cache: dict[int, Interval],
    name: str,
    resolutions: dict[tuple[str, int], dict[str, object]],
) -> dict[str, object]:
    lower, upper = STREAM_RANGES[name]
    candidates = [
        offset
        for offset in range(lower, upper - 1)
        if _is_stationary_candidate(
            samples, directed, exact_cache, offset
        )
    ]
    expected = {(name, offset) for offset in candidates}
    actual = {key for key in resolutions if key[0] == name}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise PT21FusedArtifactError(
            f"{name} stationary resolutions differ; missing={missing[:4]} extra={extra[:4]}"
        )
    events: list[dict[str, int]] = []
    brackets: list[dict[str, object]] = []
    for offset in range(lower, upper):
        left = _sample_at(samples, offset)
        right = _sample_at(samples, offset + 1)
        if left.positive != right.positive:
            events.append(
                {"left_sample": offset, "right_sample": offset + 1, "multiplicity": 1}
            )
            brackets.append(
                _bracket(
                    Fraction(offset),
                    Fraction(offset + 1),
                    _exact_interval_at(samples, exact_cache, offset),
                    _exact_interval_at(samples, exact_cache, offset + 1),
                    "direct",
                )
            )
    for offset in candidates:
        resolution = resolutions[(name, offset)]
        source_sign = _sample_at(samples, offset + 1).positive
        lower_positive = resolution["lower_value"][0] > 0
        if lower_positive != source_sign:
            raise PT21FusedArtifactError(
                f"{name} stationary resolution at {offset} reverses the source sign"
            )
        events.append(
            {"left_sample": offset, "right_sample": offset + 2, "multiplicity": 2}
        )
        brackets.extend(
            [
                _bracket(
                    resolution["lower_offset"],
                    resolution["midpoint_offset"],
                    resolution["lower_value"],
                    resolution["midpoint_value"],
                    "stationary_left",
                ),
                _bracket(
                    resolution["midpoint_offset"],
                    resolution["upper_offset"],
                    resolution["midpoint_value"],
                    resolution["upper_value"],
                    "stationary_right",
                ),
            ]
        )
    events.sort(key=lambda event: (event["left_sample"], event["right_sample"]))
    brackets.sort(
        key=lambda bracket: (
            Fraction(
                bracket["lower_offset"]["numerator"],
                bracket["lower_offset"]["denominator"],
            ),
            Fraction(
                bracket["upper_offset"]["numerator"],
                bracket["upper_offset"]["denominator"],
            ),
        )
    )
    return {
        "left_boundary": _endpoint_json(
            _exact_interval_at(samples, exact_cache, lower)
        ),
        "right_boundary": _endpoint_json(
            _exact_interval_at(samples, exact_cache, upper)
        ),
        "brackets": brackets,
        "events": events,
    }


def _build_stream_from_prevalidated_scan(
    *,
    name: str,
    direct_offsets: tuple[int, ...],
    stationary_offsets: tuple[int, ...],
    resolutions: dict[tuple[str, int], dict[str, object]],
    positive_at: Callable[[int], bool],
    interval_at: Callable[[int], Interval],
) -> dict[str, object]:
    """Build one stream from a complete independently checked scan list.

    The caller must have revalidated scan completeness against the packet.
    This function still checks every stationary-resolution identity, source
    sign, exact endpoint interval, ordering relationship, and final artifact.
    It exists only for the explicitly selected native qualification fast path;
    the ordinary production/reference function above remains unchanged.
    """

    lower, upper = STREAM_RANGES[name]
    if (
        any(
            not lower <= offset < upper
            for offset in direct_offsets
        )
        or any(
            not lower <= offset <= upper - 2
            for offset in stationary_offsets
        )
        or tuple(sorted(set(direct_offsets))) != direct_offsets
        or tuple(sorted(set(stationary_offsets))) != stationary_offsets
    ):
        raise PT21FusedArtifactError(
            f"{name} prevalidated scan geometry differs"
        )
    expected = {(name, offset) for offset in stationary_offsets}
    actual = {key for key in resolutions if key[0] == name}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise PT21FusedArtifactError(
            f"{name} stationary resolutions differ; "
            f"missing={missing[:4]} extra={extra[:4]}"
        )

    events: list[dict[str, int]] = []
    brackets: list[dict[str, object]] = []
    for offset in direct_offsets:
        if positive_at(offset) == positive_at(offset + 1):
            raise PT21FusedArtifactError(
                f"{name} direct scan offset lacks a sign change"
            )
        events.append(
            {
                "left_sample": offset,
                "right_sample": offset + 1,
                "multiplicity": 1,
            }
        )
        brackets.append(
            _bracket(
                Fraction(offset),
                Fraction(offset + 1),
                interval_at(offset),
                interval_at(offset + 1),
                "direct",
            )
        )
    for offset in stationary_offsets:
        resolution = resolutions[(name, offset)]
        source_sign = positive_at(offset + 1)
        lower_positive = resolution["lower_value"][0] > 0
        if lower_positive != source_sign:
            raise PT21FusedArtifactError(
                f"{name} stationary resolution at {offset} "
                "reverses the source sign"
            )
        events.append(
            {
                "left_sample": offset,
                "right_sample": offset + 2,
                "multiplicity": 2,
            }
        )
        brackets.extend(
            [
                _bracket(
                    resolution["lower_offset"],
                    resolution["midpoint_offset"],
                    resolution["lower_value"],
                    resolution["midpoint_value"],
                    "stationary_left",
                ),
                _bracket(
                    resolution["midpoint_offset"],
                    resolution["upper_offset"],
                    resolution["midpoint_value"],
                    resolution["upper_value"],
                    "stationary_right",
                ),
            ]
        )
    events.sort(key=lambda event: (event["left_sample"], event["right_sample"]))
    brackets.sort(
        key=lambda bracket: (
            Fraction(
                bracket["lower_offset"]["numerator"],
                bracket["lower_offset"]["denominator"],
            ),
            Fraction(
                bracket["upper_offset"]["numerator"],
                bracket["upper_offset"]["denominator"],
            ),
        )
    )
    return {
        "left_boundary": _endpoint_json(interval_at(lower)),
        "right_boundary": _endpoint_json(interval_at(upper)),
        "brackets": brackets,
        "events": events,
    }


def _point(value: Fraction) -> Interval:
    return (value, value)


def _neg(value: Interval) -> Interval:
    return (-value[1], -value[0])


def _add(left: Interval, right: Interval) -> Interval:
    return (left[0] + right[0], left[1] + right[1])


def _sub(left: Interval, right: Interval) -> Interval:
    return (left[0] - right[1], left[1] - right[0])


def _mul(left: Interval, right: Interval) -> Interval:
    products = (
        left[0] * right[0],
        left[0] * right[1],
        left[1] * right[0],
        left[1] * right[1],
    )
    return (min(products), max(products))


def _div(left: Interval, right: Interval, label: str) -> Interval:
    if right[0] <= 0 <= right[1]:
        raise PT21FusedArtifactError(f"{label} divides by an interval containing zero")
    return _mul(left, (Fraction(1, right[1]), Fraction(1, right[0])))


def _weights(stream: dict[str, object], name: str) -> tuple[int, int]:
    lower, upper = STREAM_RANGES[name]
    span = upper - lower
    events = stream["events"]
    left = -sum(
        event["multiplicity"] * (event["left_sample"] - lower) for event in events
    )
    right = sum(
        event["multiplicity"] * (span - (event["right_sample"] - lower))
        for event in events
    )
    return left, right


def _ceil(value: Fraction) -> int:
    return -((-value.numerator) // value.denominator)


def _turing_payload(
    inputs: dict[str, dict[str, Interval]],
    *,
    height_lower: int,
    height_upper: int,
    main: dict[str, object],
    left_flank: dict[str, object],
    right_flank: dict[str, object],
) -> dict[str, object]:
    left_weight = _weights(left_flank, "left_flank")[0]
    right_weight = _weights(right_flank, "right_flank")[1]
    lower_a, lower_b = height_lower - 21, height_lower
    upper_a, upper_b = height_upper, height_upper + 21

    def common(side: dict[str, Interval], a: int, b: int, label: str) -> Interval:
        span = Fraction(b - a)
        log_coefficient = Fraction(-(a + b), 4)
        log_term = _mul(
            _mul(_point(log_coefficient), side["log_pi"]), _point(span)
        )
        return _div(
            _add(log_term, side["im_gamma_integral"]),
            side["pi"],
            f"{label} Turing common",
        )

    lower_inputs = inputs["lower"]
    upper_inputs = inputs["upper"]
    lower = _div(
        _add(
            _sub(
                _neg(lower_inputs["s_bound"]),
                _point(left_weight * SOURCE_SPACING),
            ),
            common(lower_inputs, lower_a, lower_b, "lower"),
        ),
        _point(Fraction(lower_b - lower_a)),
        "Turing lower quotient",
    )
    upper = _div(
        _add(
            _sub(
                upper_inputs["s_bound"],
                _point(right_weight * SOURCE_SPACING),
            ),
            common(upper_inputs, upper_a, upper_b, "upper"),
        ),
        _point(Fraction(upper_b - upper_a)),
        "Turing upper quotient",
    )
    lower_target = _ceil(lower[1])
    upper_target = upper[0].numerator // upper[0].denominator
    if not Fraction(lower_target - 1) < lower[0] or not lower[1] <= lower_target:
        raise PT21FusedArtifactError("lower Turing quotient has no unique ceiling")
    if not Fraction(upper_target) <= upper[0] or not upper[1] < upper_target + 1:
        raise PT21FusedArtifactError("upper Turing quotient has no unique floor")
    lower_count = lower_target + 1
    upper_count = upper_target + 1
    slots = len(main["brackets"])
    if lower_count < 1 or upper_count < 1 or lower_count + slots != upper_count:
        raise PT21FusedArtifactError("paired Turing count does not close on main slots")
    return {
        "lower": {
            "s_bound": _interval_json(lower_inputs["s_bound"]),
            "log_pi": _interval_json(lower_inputs["log_pi"]),
            "im_gamma_integral": _interval_json(
                lower_inputs["im_gamma_integral"]
            ),
            "pi": _interval_json(lower_inputs["pi"]),
            "quotient": _interval_json(lower),
            "count": lower_count,
        },
        "upper": {
            "s_bound": _interval_json(upper_inputs["s_bound"]),
            "log_pi": _interval_json(upper_inputs["log_pi"]),
            "im_gamma_integral": _interval_json(
                upper_inputs["im_gamma_integral"]
            ),
            "pi": _interval_json(upper_inputs["pi"]),
            "quotient": _interval_json(upper),
            "count": upper_count,
        },
    }


def build_block_artifact_from_packet(
    packet: RequiredSignPacket, source_trace: Path
) -> dict[str, object]:
    """Build one artifact from an already decoded required-sign packet."""

    block_delta = packet.window_center - (SOURCE_LOWER + SOURCE_HALF_STEP)
    if block_delta < 0 or block_delta % SOURCE_STEP:
        raise PT21FusedArtifactError("required-sign packet center is off the source grid")
    block = block_delta // SOURCE_STEP
    if block >= SOURCE_BLOCK_COUNT or len(packet.samples) != REQUIRED_COUNT:
        raise PT21FusedArtifactError("required-sign packet is outside the full campaign")
    trace, trace_sha256 = _parse_trace(
        source_trace, packet_sha256=packet.sha256, block=block
    )
    resolutions: dict[tuple[str, int], dict[str, object]] = {}
    for index, raw in enumerate(trace["stationary_resolutions"]):
        parsed = _parse_resolution(raw, f"stationary_resolutions[{index}]")
        key = (str(parsed["stream"]), int(parsed["outer_left_sample"]))
        if key in resolutions:
            raise PT21FusedArtifactError(f"duplicate stationary resolution: {key}")
        resolutions[key] = parsed
    directed = tuple(
        _directed_sample_interval(sample) for sample in packet.samples
    )
    exact_cache: dict[int, Interval] = {}
    streams = {
        name: _build_stream(
            packet.samples, directed, exact_cache, name, resolutions
        )
        for name in ("main", "left_flank", "right_flank")
    }
    height_lower = SOURCE_LOWER + block * SOURCE_STEP
    height_upper = height_lower + SOURCE_STEP
    artifact: dict[str, object] = {
        "schema": "sparkinterval.tg.platt-pt21-lean-block-artifact.v2",
        "upstream_commit": UPSTREAM_COMMIT,
        "block": block,
        "height_lower": height_lower,
        "height_upper": height_upper,
        "window_center": packet.window_center,
        "required_sign_packet_sha256": packet.sha256,
        "source_trace_sha256": trace_sha256,
        "streams": streams,
        "turing": _turing_payload(
            trace["turing_inputs"],
            height_lower=height_lower,
            height_upper=height_upper,
            main=streams["main"],
            left_flank=streams["left_flank"],
            right_flank=streams["right_flank"],
        ),
    }
    try:
        validate_block_artifact(artifact)
        return artifact
    except PT21LeanArtifactError as error:
        raise PT21FusedArtifactError(f"generated Lean artifact failed: {error}") from error


def build_block_artifact_from_prevalidated_scan(
    *,
    packet_sha256: str,
    window_center: int,
    sample_count: int,
    direct_offsets: tuple[
        tuple[int, ...], tuple[int, ...], tuple[int, ...]
    ],
    stationary_offsets: tuple[
        tuple[int, ...], tuple[int, ...], tuple[int, ...]
    ],
    positive_at: Callable[[int], bool],
    interval_at: Callable[[int], Interval],
    source_trace: Path,
) -> dict[str, object]:
    """Build the canonical artifact from an independently replayed scan.

    This does not weaken the exact-rational artifact or Turing checks.  It
    only replaces the two O(25,741) scalar Python scans with complete offset
    lists that a separate checker has already recomputed.
    """

    block_delta = window_center - (SOURCE_LOWER + SOURCE_HALF_STEP)
    if block_delta < 0 or block_delta % SOURCE_STEP:
        raise PT21FusedArtifactError(
            "prevalidated packet center is off the source grid"
        )
    block = block_delta // SOURCE_STEP
    if block >= SOURCE_BLOCK_COUNT or sample_count != REQUIRED_COUNT:
        raise PT21FusedArtifactError(
            "prevalidated packet is outside the full campaign"
        )
    _sha256(packet_sha256, "prevalidated required packet SHA-256")
    trace, trace_sha256 = _parse_trace(
        source_trace, packet_sha256=packet_sha256, block=block
    )
    resolutions: dict[tuple[str, int], dict[str, object]] = {}
    for index, raw in enumerate(trace["stationary_resolutions"]):
        parsed = _parse_resolution(raw, f"stationary_resolutions[{index}]")
        key = (str(parsed["stream"]), int(parsed["outer_left_sample"]))
        if key in resolutions:
            raise PT21FusedArtifactError(
                f"duplicate stationary resolution: {key}"
            )
        resolutions[key] = parsed
    names = ("main", "left_flank", "right_flank")
    streams = {
        name: _build_stream_from_prevalidated_scan(
            name=name,
            direct_offsets=direct_offsets[index],
            stationary_offsets=stationary_offsets[index],
            resolutions=resolutions,
            positive_at=positive_at,
            interval_at=interval_at,
        )
        for index, name in enumerate(names)
    }
    height_lower = SOURCE_LOWER + block * SOURCE_STEP
    height_upper = height_lower + SOURCE_STEP
    artifact: dict[str, object] = {
        "schema": "sparkinterval.tg.platt-pt21-lean-block-artifact.v2",
        "upstream_commit": UPSTREAM_COMMIT,
        "block": block,
        "height_lower": height_lower,
        "height_upper": height_upper,
        "window_center": window_center,
        "required_sign_packet_sha256": packet_sha256,
        "source_trace_sha256": trace_sha256,
        "streams": streams,
        "turing": _turing_payload(
            trace["turing_inputs"],
            height_lower=height_lower,
            height_upper=height_upper,
            main=streams["main"],
            left_flank=streams["left_flank"],
            right_flank=streams["right_flank"],
        ),
    }
    try:
        validate_block_artifact(artifact)
        return artifact
    except PT21LeanArtifactError as error:
        raise PT21FusedArtifactError(
            f"generated prevalidated Lean artifact failed: {error}"
        ) from error


def build_block_artifact(required_sign_packet: Path, source_trace: Path) -> dict[str, object]:
    """Build and recheck one canonical Lean wire artifact."""

    return build_block_artifact_from_packet(
        load_required_sign_packet(required_sign_packet), source_trace
    )


def write_block_artifact(
    required_sign_packet: Path, source_trace: Path, output: Path
) -> dict[str, object]:
    artifact = build_block_artifact(required_sign_packet, source_trace)
    _write_new(output, _canonical(artifact) + b"\n")
    return artifact


def _write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise PT21FusedArtifactError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _merkle_root(leaves: list[str], leaf_domain: bytes, node_domain: bytes) -> str:
    if not leaves:
        raise PT21FusedArtifactError("cannot Merkle-finalize an empty stream")
    level = [hashlib.sha256(leaf_domain + bytes.fromhex(leaf)).digest() for leaf in leaves]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(node_domain + level[index] + level[index + 1]).digest()
            for index in range(0, len(level), 2)
        ]
    return level[0].hex()


def _fraction_from_json(value: Fraction | dict[str, int]) -> Fraction:
    if isinstance(value, Fraction):
        return value
    return Fraction(value["numerator"], value["denominator"])


def _source_height_count(artifact: dict[str, object]) -> int | None:
    lower = int(artifact["height_lower"])
    upper = int(artifact["height_upper"])
    if not lower <= SOURCE_HEIGHT <= upper:
        return None
    lower_count = int(artifact["turing"]["lower"]["count"])
    if SOURCE_HEIGHT == lower:
        return lower_count
    if SOURCE_HEIGHT == upper:
        return int(artifact["turing"]["upper"]["count"])
    center = Fraction(int(artifact["window_center"]))
    target = Fraction(SOURCE_HEIGHT)
    below = 0
    for index, bracket in enumerate(artifact["streams"]["main"]["brackets"]):
        bracket_lower = center + _fraction_from_json(bracket["lower_offset"]) * SOURCE_SPACING
        bracket_upper = center + _fraction_from_json(bracket["upper_offset"]) * SOURCE_SPACING
        if bracket_upper <= target:
            below += 1
        elif bracket_lower >= target:
            pass
        else:
            raise PT21FusedArtifactError(
                f"main bracket {index} straddles the exact PT21 source height"
            )
    return lower_count + below


def finalize_shard(
    artifact_paths: Iterable[Path],
    *,
    first_block: int,
    allow_bounded_test: bool = False,
) -> dict[str, object]:
    paths = list(artifact_paths)
    if not paths:
        raise PT21FusedArtifactError("shard contains no block artifacts")
    artifacts: list[dict[str, object]] = []
    artifact_digests: list[str] = []
    source_height_count: int | None = None
    for offset, path in enumerate(paths):
        if path.is_symlink() or not path.is_file():
            raise PT21FusedArtifactError(f"block artifact is not regular: {path}")
        raw = path.read_bytes()
        if not raw or len(raw) > MAX_BLOCK_BYTES:
            raise PT21FusedArtifactError(f"block artifact byte length is invalid: {path}")
        try:
            wire_value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PT21FusedArtifactError(f"block artifact is not strict JSON: {error}") from error
        if raw != _canonical(wire_value) + b"\n":
            raise PT21FusedArtifactError("block artifact is not canonical JSON")
        try:
            artifact = load_block_artifact(path)
        except (OSError, PT21LeanArtifactError) as error:
            raise PT21FusedArtifactError(f"block artifact failed validation: {error}") from error
        expected_block = first_block + offset
        if artifact["block"] != expected_block:
            raise PT21FusedArtifactError("shard block indices are not gap-free and ordered")
        if offset:
            previous = artifacts[-1]
            if (
                previous["height_upper"] != artifact["height_lower"]
                or previous["turing"]["upper"]["count"]
                != artifact["turing"]["lower"]["count"]
            ):
                raise PT21FusedArtifactError("shard height/count chain does not telescope")
        target_count = _source_height_count(artifact)
        if target_count is not None:
            if source_height_count is not None:
                raise PT21FusedArtifactError("source height occurs in more than one block")
            source_height_count = target_count
        artifacts.append(artifact)
        artifact_digests.append(hashlib.sha256(raw).hexdigest())
    upper = first_block + len(artifacts)
    if first_block < 0 or upper > SOURCE_BLOCK_COUNT:
        raise PT21FusedArtifactError("shard lies outside the fixed campaign")
    if not allow_bounded_test and first_block == 0:
        if artifacts[0]["turing"]["lower"]["count"] != SOURCE_LOWER_COUNT:
            raise PT21FusedArtifactError("production chain does not start at N(10^10)")
    receipt: dict[str, object] = {
        "schema": SHARD_SCHEMA,
        "mode": "bounded_test" if allow_bounded_test else "production",
        "upstream_commit": UPSTREAM_COMMIT,
        "first_block": first_block,
        "upper_block_exclusive": upper,
        "block_count": len(artifacts),
        "height_lower": artifacts[0]["height_lower"],
        "height_upper": artifacts[-1]["height_upper"],
        "first_count": artifacts[0]["turing"]["lower"]["count"],
        "last_count": artifacts[-1]["turing"]["upper"]["count"],
        "total_main_slots": sum(len(item["streams"]["main"]["brackets"]) for item in artifacts),
        "source_height_count": source_height_count,
        "block_artifact_merkle_root_sha256": _merkle_root(
            artifact_digests, BLOCK_LEAF_DOMAIN, BLOCK_NODE_DOMAIN
        ),
        "all_block_artifacts_kernel_wire_ready": True,
        "hardy_z_endpoint_realization_proved": False,
        "main_multiplicity_realization_proved": False,
        "analytic_turing_realization_proved": False,
        "source_claim_ready": False,
    }
    receipt["receipt_sha256"] = _domain_digest(SHARD_RECEIPT_DOMAIN, receipt)
    return receipt


def validate_shard_receipt(value: object) -> dict[str, object]:
    keys = {
        "schema", "mode", "upstream_commit", "first_block",
        "upper_block_exclusive", "block_count", "height_lower", "height_upper",
        "first_count", "last_count", "total_main_slots", "source_height_count",
        "block_artifact_merkle_root_sha256", "all_block_artifacts_kernel_wire_ready",
        "hardy_z_endpoint_realization_proved", "main_multiplicity_realization_proved",
        "analytic_turing_realization_proved", "source_claim_ready", "receipt_sha256",
    }
    item = _exact_object(value, keys, "shard receipt")
    if item["schema"] != SHARD_SCHEMA or item["upstream_commit"] != UPSTREAM_COMMIT:
        raise PT21FusedArtifactError("shard receipt identity differs")
    if item["mode"] not in ("production", "bounded_test"):
        raise PT21FusedArtifactError("shard receipt mode is unknown")
    first = _integer(item["first_block"], "first_block", minimum=0)
    upper = _integer(item["upper_block_exclusive"], "upper_block_exclusive", minimum=1)
    count = _integer(item["block_count"], "block_count", minimum=1)
    if upper != first + count or upper > SOURCE_BLOCK_COUNT:
        raise PT21FusedArtifactError("shard receipt block range differs")
    if item["height_lower"] != SOURCE_LOWER + first * SOURCE_STEP or item["height_upper"] != SOURCE_LOWER + upper * SOURCE_STEP:
        raise PT21FusedArtifactError("shard receipt height range differs")
    first_count = _integer(item["first_count"], "first_count", minimum=1)
    last_count = _integer(item["last_count"], "last_count", minimum=1)
    slots = _integer(item["total_main_slots"], "total_main_slots", minimum=0)
    if first_count + slots != last_count:
        raise PT21FusedArtifactError("shard receipt count chain does not telescope")
    if item["source_height_count"] is not None:
        _integer(item["source_height_count"], "source_height_count", minimum=1)
        if not item["height_lower"] <= SOURCE_HEIGHT <= item["height_upper"]:
            raise PT21FusedArtifactError("source-height count is outside this shard")
    _sha256(item["block_artifact_merkle_root_sha256"], "block Merkle root")
    if item["all_block_artifacts_kernel_wire_ready"] is not True:
        raise PT21FusedArtifactError("shard does not bind all finite block artifacts")
    for key in (
        "hardy_z_endpoint_realization_proved",
        "main_multiplicity_realization_proved",
        "analytic_turing_realization_proved",
        "source_claim_ready",
    ):
        if _boolean(item[key], key):
            raise PT21FusedArtifactError("finite shard receipt overclaims analytic semantics")
    digest = _sha256(item["receipt_sha256"], "receipt_sha256")
    body = {key: value for key, value in item.items() if key != "receipt_sha256"}
    if digest != _domain_digest(SHARD_RECEIPT_DOMAIN, body):
        raise PT21FusedArtifactError("shard receipt digest differs")
    return item


def finalize_campaign(
    shard_receipt_paths: Iterable[Path], *, allow_bounded_test: bool = False
) -> dict[str, object]:
    paths = list(shard_receipt_paths)
    if not paths:
        raise PT21FusedArtifactError("campaign contains no shard receipts")
    receipts: list[dict[str, object]] = []
    for path in paths:
        value, _raw = _load_canonical_json(path, maximum=MAX_TRACE_BYTES, label="shard receipt")
        receipts.append(validate_shard_receipt(value))
    receipts.sort(key=lambda item: item["first_block"])
    for index, receipt in enumerate(receipts):
        if index:
            previous = receipts[index - 1]
            if (
                previous["upper_block_exclusive"] != receipt["first_block"]
                or previous["height_upper"] != receipt["height_lower"]
                or previous["last_count"] != receipt["first_count"]
            ):
                raise PT21FusedArtifactError("campaign shard chain is not contiguous")
    first = receipts[0]
    last = receipts[-1]
    block_count = sum(int(item["block_count"]) for item in receipts)
    slots = sum(int(item["total_main_slots"]) for item in receipts)
    if int(first["first_count"]) + slots != int(last["last_count"]):
        raise PT21FusedArtifactError("campaign count chain does not telescope")
    target_counts = [
        int(item["source_height_count"])
        for item in receipts
        if item["source_height_count"] is not None
    ]
    if allow_bounded_test:
        mode = "bounded_test"
    else:
        mode = "production"
        if (
            first["first_block"] != 0
            or last["upper_block_exclusive"] != SOURCE_BLOCK_COUNT
            or block_count != SOURCE_BLOCK_COUNT
            or first["first_count"] != SOURCE_LOWER_COUNT
            or target_counts != [SOURCE_HEIGHT_COUNT]
        ):
            raise PT21FusedArtifactError(
                "production campaign lacks full geometry or the exact PT21 source count"
            )
        if any(item["mode"] != "production" for item in receipts):
            raise PT21FusedArtifactError("bounded-test shard entered production finalization")
    result: dict[str, object] = {
        "schema": FINAL_SCHEMA,
        "mode": mode,
        "upstream_commit": UPSTREAM_COMMIT,
        "first_block": first["first_block"],
        "upper_block_exclusive": last["upper_block_exclusive"],
        "block_count": block_count,
        "shard_count": len(receipts),
        "height_lower": first["height_lower"],
        "height_upper": last["height_upper"],
        "first_count": first["first_count"],
        "last_count": last["last_count"],
        "source_height": SOURCE_HEIGHT,
        "source_height_count": target_counts[0] if len(target_counts) == 1 else None,
        "total_main_slots": slots,
        "shard_receipt_merkle_root_sha256": _merkle_root(
            [str(item["receipt_sha256"]) for item in receipts],
            SHARD_LEAF_DOMAIN,
            SHARD_NODE_DOMAIN,
        ),
        "all_finite_artifacts_closed": True,
        "hardy_z_endpoint_realization_proved": False,
        "main_multiplicity_realization_proved": False,
        "analytic_turing_realization_proved": False,
        "azure_execution_attested": False,
        "source_claim_ready": False,
    }
    result["final_sha256"] = _domain_digest(FINAL_RECEIPT_DOMAIN, result)
    return result


def validate_final_receipt(value: object) -> dict[str, object]:
    keys = {
        "schema", "mode", "upstream_commit", "first_block",
        "upper_block_exclusive", "block_count", "shard_count", "height_lower",
        "height_upper", "first_count", "last_count", "source_height",
        "source_height_count", "total_main_slots",
        "shard_receipt_merkle_root_sha256", "all_finite_artifacts_closed",
        "hardy_z_endpoint_realization_proved", "main_multiplicity_realization_proved",
        "analytic_turing_realization_proved", "azure_execution_attested",
        "source_claim_ready", "final_sha256",
    }
    item = _exact_object(value, keys, "final receipt")
    if item["schema"] != FINAL_SCHEMA or item["upstream_commit"] != UPSTREAM_COMMIT:
        raise PT21FusedArtifactError("final receipt identity differs")
    if item["mode"] not in ("production", "bounded_test"):
        raise PT21FusedArtifactError("final receipt mode is unknown")
    first = _integer(item["first_block"], "first_block", minimum=0)
    upper = _integer(item["upper_block_exclusive"], "upper_block_exclusive", minimum=1)
    count = _integer(item["block_count"], "block_count", minimum=1)
    _integer(item["shard_count"], "shard_count", minimum=1)
    if upper != first + count or upper > SOURCE_BLOCK_COUNT:
        raise PT21FusedArtifactError("final receipt block range differs")
    if item["height_lower"] != SOURCE_LOWER + first * SOURCE_STEP or item["height_upper"] != SOURCE_LOWER + upper * SOURCE_STEP:
        raise PT21FusedArtifactError("final receipt height range differs")
    first_count = _integer(item["first_count"], "first_count", minimum=1)
    last_count = _integer(item["last_count"], "last_count", minimum=1)
    slots = _integer(item["total_main_slots"], "total_main_slots", minimum=0)
    if first_count + slots != last_count or item["source_height"] != SOURCE_HEIGHT:
        raise PT21FusedArtifactError("final receipt count or source height differs")
    if item["source_height_count"] is not None:
        _integer(item["source_height_count"], "source_height_count", minimum=1)
    if item["mode"] == "production" and (
        first != 0
        or upper != SOURCE_BLOCK_COUNT
        or count != SOURCE_BLOCK_COUNT
        or first_count != SOURCE_LOWER_COUNT
        or item["source_height_count"] != SOURCE_HEIGHT_COUNT
    ):
        raise PT21FusedArtifactError("production final receipt differs from the source claim")
    _sha256(item["shard_receipt_merkle_root_sha256"], "shard receipt Merkle root")
    if item["all_finite_artifacts_closed"] is not True:
        raise PT21FusedArtifactError("final receipt does not close every finite artifact")
    for key in (
        "hardy_z_endpoint_realization_proved",
        "main_multiplicity_realization_proved",
        "analytic_turing_realization_proved",
        "azure_execution_attested",
        "source_claim_ready",
    ):
        if _boolean(item[key], key):
            raise PT21FusedArtifactError("finite final receipt overclaims external semantics")
    digest = _sha256(item["final_sha256"], "final_sha256")
    body = {key: field for key, field in item.items() if key != "final_sha256"}
    if digest != _domain_digest(FINAL_RECEIPT_DOMAIN, body):
        raise PT21FusedArtifactError("final receipt digest differs")
    return item


__all__ = [
    "FINAL_SCHEMA",
    "INTERPOLATION_PATCH_SHA256",
    "PT21FusedArtifactError",
    "SHARD_SCHEMA",
    "SOURCE_HEIGHT",
    "SOURCE_HEIGHT_COUNT",
    "TRACE_SCHEMA",
    "build_block_artifact",
    "build_block_artifact_from_prevalidated_scan",
    "finalize_campaign",
    "finalize_shard",
    "validate_shard_receipt",
    "validate_final_receipt",
    "write_block_artifact",
]
