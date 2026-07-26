# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Strict decoder for the compact PT21 block-to-Lean handoff.

The JSON file is intentionally a small retained output of a fused worker, not
the ephemeral 25,741-sample interpolation packet.  It contains exact rational
endpoint enclosures and exact rational Turing intervals.  This module checks
the same finite geometry and arithmetic independently with ``Fraction`` and
can emit a Lean literal consumed by
``SparkInterval.Zeta.PT21ArtifactBinding.BlockArtifact.check``.

Acceptance here and in Lean does not establish Hardy-Z enclosure semantics or
the analytic Turing inequalities.  Those remain explicit Lean premises.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from tg_verifier.platt_required_sign_packet import (
    PlattRequiredSignPacketError,
    load_required_sign_packet,
)


SCHEMA = "sparkinterval.tg.platt-pt21-lean-block-artifact.v2"
UPSTREAM_COMMIT = "42b21426718e542daa2b006dc05ea2d7f26426e6"
SOURCE_LOWER = 10_000_000_000
SOURCE_STEP = 1_008
SOURCE_HALF_STEP = 504
SOURCE_BLOCK_COUNT = 2_966_443_783
SOURCE_SPACING = Fraction(21, 512)
MAX_BYTES = 16 * 1024 * 1024
MAX_BRACKETS_PER_STREAM = 10_000
SHA256_RE = re.compile(r"[0-9a-f]{64}")
LEAN_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_']*")
STREAM_RANGES = {
    "main": (-12_288, 12_288),
    "left_flank": (-12_800, -12_288),
    "right_flank": (12_288, 12_800),
}
RESOLVERS = {
    "direct",
    "stationary_left",
    "stationary_right",
    "pinned_arb_fallback",
}


class PT21LeanArtifactError(ValueError):
    """A handoff failed a structural or exact-arithmetic gate."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PT21LeanArtifactError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _exact_object(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PT21LeanArtifactError(f"{label} fields differ")
    return value


def _integer(value: object, label: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PT21LeanArtifactError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise PT21LeanArtifactError(f"{label} is below {minimum}")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise PT21LeanArtifactError(f"{label} must be Boolean")
    return value


def _fraction(value: object, label: str) -> Fraction:
    item = _exact_object(value, {"numerator", "denominator"}, label)
    numerator = _integer(item["numerator"], f"{label}.numerator")
    denominator = _integer(
        item["denominator"], f"{label}.denominator", minimum=1
    )
    fraction = Fraction(numerator, denominator)
    if fraction.numerator != numerator or fraction.denominator != denominator:
        raise PT21LeanArtifactError(f"{label} is not in canonical lowest terms")
    return fraction


Interval = tuple[Fraction, Fraction]


def _interval(value: object, label: str) -> Interval:
    item = _exact_object(value, {"lo", "hi"}, label)
    result = (_fraction(item["lo"], f"{label}.lo"), _fraction(item["hi"], f"{label}.hi"))
    if result[0] > result[1]:
        raise PT21LeanArtifactError(f"{label} is an invalid interval")
    return result


def _endpoint(value: object, label: str) -> dict[str, object]:
    item = _exact_object(value, {"enclosure", "positive"}, label)
    enclosure = _interval(item["enclosure"], f"{label}.enclosure")
    positive = _boolean(item["positive"], f"{label}.positive")
    if positive and enclosure[0] <= 0:
        raise PT21LeanArtifactError(f"{label} is not strictly positive")
    if not positive and enclosure[1] >= 0:
        raise PT21LeanArtifactError(f"{label} is not strictly negative")
    return {"enclosure": enclosure, "positive": positive}


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise PT21LeanArtifactError(f"{label} must be lowercase SHA-256 hex")
    return value


def _check_fallback(bracket: dict[str, object], label: str) -> None:
    resolver = bracket["resolver"]
    digest = bracket["fallback_receipt_sha256"]
    if resolver == "pinned_arb_fallback":
        _sha256(digest, f"{label}.fallback_receipt_sha256")
    elif digest is not None:
        raise PT21LeanArtifactError(
            f"{label} has fallback evidence for a non-fallback resolver"
        )


def _stream(value: object, name: str) -> dict[str, object]:
    item = _exact_object(
        value, {"left_boundary", "right_boundary", "brackets", "events"}, name
    )
    left = _endpoint(item["left_boundary"], f"{name}.left_boundary")
    right = _endpoint(item["right_boundary"], f"{name}.right_boundary")
    raw_brackets = item["brackets"]
    if not isinstance(raw_brackets, list):
        raise PT21LeanArtifactError(f"{name}.brackets must be a list")
    if len(raw_brackets) > MAX_BRACKETS_PER_STREAM:
        raise PT21LeanArtifactError(f"{name}.brackets exceeds the format limit")
    lower_range, upper_range = STREAM_RANGES[name]
    brackets: list[dict[str, object]] = []
    previous: dict[str, object] | None = None
    for index, raw in enumerate(raw_brackets):
        label = f"{name}.brackets[{index}]"
        bracket = _exact_object(
            raw,
            {
                "lower_offset",
                "upper_offset",
                "lower_value",
                "upper_value",
                "resolver",
                "fallback_receipt_sha256",
            },
            label,
        )
        lower_offset = _fraction(bracket["lower_offset"], f"{label}.lower_offset")
        upper_offset = _fraction(bracket["upper_offset"], f"{label}.upper_offset")
        if not lower_range <= lower_offset < upper_offset <= upper_range:
            raise PT21LeanArtifactError(f"{label} is outside the fixed sample range")
        lower_value = _endpoint(bracket["lower_value"], f"{label}.lower_value")
        upper_value = _endpoint(bracket["upper_value"], f"{label}.upper_value")
        if lower_value["positive"] == upper_value["positive"]:
            raise PT21LeanArtifactError(f"{label} lacks a strict sign change")
        resolver = bracket["resolver"]
        if not isinstance(resolver, str) or resolver not in RESOLVERS:
            raise PT21LeanArtifactError(f"{label}.resolver is unknown")
        normalized: dict[str, object] = {
            "lower_offset": lower_offset,
            "upper_offset": upper_offset,
            "lower_value": lower_value,
            "upper_value": upper_value,
            "resolver": resolver,
            "fallback_receipt_sha256": bracket["fallback_receipt_sha256"],
        }
        _check_fallback(normalized, label)
        if previous is not None:
            previous_upper = previous["upper_offset"]
            if previous_upper > lower_offset:
                raise PT21LeanArtifactError(f"{label} overlaps the previous interior")
            if (
                previous_upper == lower_offset
                and previous["upper_value"]["positive"]
                != lower_value["positive"]
            ):
                raise PT21LeanArtifactError(
                    f"{label} disagrees at a touching endpoint"
                )
        if lower_offset == lower_range and lower_value["positive"] != left["positive"]:
            raise PT21LeanArtifactError(f"{label} disagrees with the left boundary")
        if upper_offset == upper_range and upper_value["positive"] != right["positive"]:
            raise PT21LeanArtifactError(f"{label} disagrees with the right boundary")
        brackets.append(normalized)
        previous = normalized

    index = 0
    while index < len(brackets):
        resolver = brackets[index]["resolver"]
        if resolver == "stationary_left":
            if index + 1 >= len(brackets):
                raise PT21LeanArtifactError(f"{name} has an unpaired stationary_left")
            partner = brackets[index + 1]
            if (
                partner["resolver"] != "stationary_right"
                or brackets[index]["upper_offset"] != partner["lower_offset"]
            ):
                raise PT21LeanArtifactError(f"{name} stationary resolver pair differs")
            index += 2
        elif resolver == "stationary_right":
            raise PT21LeanArtifactError(f"{name} has an unpaired stationary_right")
        else:
            index += 1

    if (left["positive"] == right["positive"]) != (len(brackets) % 2 == 0):
        raise PT21LeanArtifactError(f"{name} endpoint parity differs from slot count")

    raw_events = item["events"]
    if not isinstance(raw_events, list):
        raise PT21LeanArtifactError(f"{name}.events must be a list")
    if len(raw_events) > MAX_BRACKETS_PER_STREAM:
        raise PT21LeanArtifactError(f"{name}.events exceeds the format limit")
    events: list[dict[str, int]] = []
    previous_right: int | None = None
    bracket_index = 0
    for index, raw in enumerate(raw_events):
        label = f"{name}.events[{index}]"
        event = _exact_object(
            raw, {"left_sample", "right_sample", "multiplicity"}, label
        )
        left_sample = _integer(event["left_sample"], f"{label}.left_sample")
        right_sample = _integer(event["right_sample"], f"{label}.right_sample")
        multiplicity = _integer(
            event["multiplicity"], f"{label}.multiplicity", minimum=1
        )
        if (
            not lower_range <= left_sample < right_sample <= upper_range
            or multiplicity not in (1, 2)
        ):
            raise PT21LeanArtifactError(f"{label} is outside the fixed event range")
        if previous_right is not None and previous_right > left_sample:
            raise PT21LeanArtifactError(f"{label} overlaps the previous event cell")
        if bracket_index >= len(brackets):
            raise PT21LeanArtifactError(f"{label} has no matching bracket")
        first = brackets[bracket_index]
        if Fraction(left_sample) > first["lower_offset"]:
            raise PT21LeanArtifactError(f"{label} does not contain its first bracket")
        if multiplicity == 1:
            if (
                first["resolver"] not in ("direct", "pinned_arb_fallback")
                or first["upper_offset"] > Fraction(right_sample)
            ):
                raise PT21LeanArtifactError(f"{label} direct bracket binding differs")
            bracket_index += 1
        else:
            if bracket_index + 1 >= len(brackets):
                raise PT21LeanArtifactError(f"{label} lacks its stationary bracket pair")
            second = brackets[bracket_index + 1]
            if (
                first["resolver"] != "stationary_left"
                or second["resolver"] != "stationary_right"
                or first["upper_offset"] != second["lower_offset"]
                or second["upper_offset"] > Fraction(right_sample)
            ):
                raise PT21LeanArtifactError(f"{label} stationary bracket binding differs")
            bracket_index += 2
        events.append(
            {
                "left_sample": left_sample,
                "right_sample": right_sample,
                "multiplicity": multiplicity,
            }
        )
        previous_right = right_sample
    if bracket_index != len(brackets):
        raise PT21LeanArtifactError(f"{name} has brackets not bound to Turing events")
    if sum(event["multiplicity"] for event in events) != len(brackets):
        raise PT21LeanArtifactError(f"{name} event multiplicities differ from slots")
    return {
        "left_boundary": left,
        "right_boundary": right,
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
        left[0] * right[0], left[0] * right[1],
        left[1] * right[0], left[1] * right[1],
    )
    return (min(products), max(products))


def _div(left: Interval, right: Interval, label: str) -> Interval:
    if right[0] <= 0 <= right[1]:
        raise PT21LeanArtifactError(f"{label} divides by an interval containing zero")
    return _mul(left, (Fraction(1, right[1]), Fraction(1, right[0])))


def _event_weights(stream: dict[str, object], name: str) -> tuple[int, int]:
    lower_range, upper_range = STREAM_RANGES[name]
    span = upper_range - lower_range
    events: list[dict[str, int]] = stream["events"]
    left = -sum(
        item["multiplicity"] * (item["left_sample"] - lower_range)
        for item in events
    )
    right = sum(
        item["multiplicity"] * (span - (item["right_sample"] - lower_range))
        for item in events
    )
    return left, right


def _turing(
    value: object,
    *,
    height_lower: int,
    height_upper: int,
    main: dict[str, object],
    left_flank: dict[str, object],
    right_flank: dict[str, object],
) -> dict[str, object]:
    item = _exact_object(value, {"lower", "upper"}, "turing")

    def side(raw: object, label: str) -> dict[str, object]:
        source = _exact_object(
            raw,
            {"s_bound", "log_pi", "im_gamma_integral", "pi", "quotient", "count"},
            label,
        )
        result: dict[str, object] = {
            "s_bound": _interval(source["s_bound"], f"{label}.s_bound"),
            "log_pi": _interval(source["log_pi"], f"{label}.log_pi"),
            "im_gamma_integral": _interval(
                source["im_gamma_integral"], f"{label}.im_gamma_integral"
            ),
            "pi": _interval(source["pi"], f"{label}.pi"),
            "quotient": _interval(source["quotient"], f"{label}.quotient"),
            "count": _integer(source["count"], f"{label}.count", minimum=1),
        }
        if result["s_bound"][0] < 0 or result["pi"][0] <= 0:
            raise PT21LeanArtifactError(
                f"{label} S bound or pi interval has the wrong sign"
            )
        return result

    lower_side = side(item["lower"], "turing.lower")
    upper_side = side(item["upper"], "turing.upper")

    def common(result: dict[str, object], a: int, b: int, label: str) -> Interval:
        span = Fraction(b - a)
        coefficient = Fraction(-(a + b), 4)
        log_term = _mul(
            _mul(_point(coefficient), result["log_pi"]), _point(span)
        )
        return _div(
            _add(log_term, result["im_gamma_integral"]),
            result["pi"],
            f"{label} common term",
        )

    lower_a, lower_b = height_lower - 21, height_lower
    lower_span = Fraction(lower_b - lower_a)
    left_weight = _event_weights(left_flank, "left_flank")[0]
    lower = _div(
        _add(
            _sub(_neg(lower_side["s_bound"]), _point(left_weight * SOURCE_SPACING)),
            common(lower_side, lower_a, lower_b, "lower Turing"),
        ),
        _point(lower_span),
        "lower Turing quotient",
    )
    upper_a, upper_b = height_upper, height_upper + 21
    upper_span = Fraction(upper_b - upper_a)
    right_weight = _event_weights(right_flank, "right_flank")[1]
    upper = _div(
        _add(
            _sub(upper_side["s_bound"], _point(right_weight * SOURCE_SPACING)),
            common(upper_side, upper_a, upper_b, "upper Turing"),
        ),
        _point(upper_span),
        "upper Turing quotient",
    )
    if lower != lower_side["quotient"] or upper != upper_side["quotient"]:
        raise PT21LeanArtifactError("advertised one-sided Turing quotient differs")
    lower_count = int(lower_side["count"])
    upper_count = int(upper_side["count"])
    if not Fraction(lower_count - 2) < lower[0] or not lower[1] <= lower_count - 1:
        raise PT21LeanArtifactError("lower quotient does not force the advertised ceiling")
    if not Fraction(upper_count - 1) <= upper[0] or not upper[1] < upper_count:
        raise PT21LeanArtifactError("upper quotient does not force the advertised floor")
    if lower_count + len(main["brackets"]) != upper_count:
        raise PT21LeanArtifactError("Turing count closure equation differs")
    return {"lower": lower_side, "upper": upper_side}


def validate(value: object) -> dict[str, object]:
    keys = {
        "schema", "upstream_commit", "block", "height_lower", "height_upper",
        "window_center", "required_sign_packet_sha256", "source_trace_sha256",
        "streams", "turing",
    }
    item = _exact_object(value, keys, "artifact")
    if item["schema"] != SCHEMA or item["upstream_commit"] != UPSTREAM_COMMIT:
        raise PT21LeanArtifactError("schema or pinned upstream commit differs")
    block = _integer(item["block"], "block", minimum=0)
    if block >= SOURCE_BLOCK_COUNT:
        raise PT21LeanArtifactError("block is outside the fixed source campaign")
    height_lower = _integer(item["height_lower"], "height_lower", minimum=0)
    height_upper = _integer(item["height_upper"], "height_upper", minimum=0)
    window_center = _integer(item["window_center"], "window_center", minimum=0)
    expected_lower = SOURCE_LOWER + block * SOURCE_STEP
    if (
        height_lower != expected_lower
        or height_upper != height_lower + SOURCE_STEP
        or window_center != height_lower + SOURCE_HALF_STEP
    ):
        raise PT21LeanArtifactError("artifact heights differ from fixed lattice geometry")
    packet_sha256 = _sha256(
        item["required_sign_packet_sha256"], "required_sign_packet_sha256"
    )
    source_trace_sha256 = _sha256(item["source_trace_sha256"], "source_trace_sha256")
    streams = _exact_object(
        item["streams"], {"main", "left_flank", "right_flank"}, "streams"
    )
    main = _stream(streams["main"], "main")
    left_flank = _stream(streams["left_flank"], "left_flank")
    right_flank = _stream(streams["right_flank"], "right_flank")
    if left_flank["right_boundary"]["positive"] != main["left_boundary"]["positive"]:
        raise PT21LeanArtifactError("left flank/main shared endpoint sign differs")
    if main["right_boundary"]["positive"] != right_flank["left_boundary"]["positive"]:
        raise PT21LeanArtifactError("main/right flank shared endpoint sign differs")
    turing = _turing(
        item["turing"],
        height_lower=height_lower,
        height_upper=height_upper,
        main=main,
        left_flank=left_flank,
        right_flank=right_flank,
    )
    return {
        "schema": SCHEMA,
        "upstream_commit": UPSTREAM_COMMIT,
        "block": block,
        "height_lower": height_lower,
        "height_upper": height_upper,
        "window_center": window_center,
        "required_sign_packet_sha256": packet_sha256,
        "source_trace_sha256": source_trace_sha256,
        "streams": {"main": main, "left_flank": left_flank, "right_flank": right_flank},
        "turing": turing,
    }


def load(
    path: Path,
    *,
    required_sign_packet: Path | None = None,
    source_packet: Path | None = None,
) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise PT21LeanArtifactError(f"artifact is not a regular file: {path}")
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise PT21LeanArtifactError("artifact exceeds the format size limit")
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise PT21LeanArtifactError(f"artifact is not strict JSON: {error}") from error
    artifact = validate(value)
    if source_packet is not None and required_sign_packet is None:
        raise PT21LeanArtifactError(
            "a source packet can only be checked through its required-sign packet"
        )
    if required_sign_packet is not None:
        try:
            packet = load_required_sign_packet(
                required_sign_packet, source_packet=source_packet
            )
        except PlattRequiredSignPacketError as error:
            raise PT21LeanArtifactError(
                f"required-sign packet failed validation: {error}"
            ) from error
        if packet.sha256 != artifact["required_sign_packet_sha256"]:
            raise PT21LeanArtifactError("required-sign packet digest differs")
        if packet.window_center != artifact["window_center"]:
            raise PT21LeanArtifactError("required-sign packet window center differs")
    return artifact


def inspect(
    path: Path,
    *,
    required_sign_packet: Path | None = None,
    source_packet: Path | None = None,
) -> dict[str, object]:
    value = load(
        path,
        required_sign_packet=required_sign_packet,
        source_packet=source_packet,
    )
    raw = path.read_bytes()
    return {
        "schema": "sparkinterval.tg.platt-pt21-lean-block-inspection.v1",
        "accepted": True,
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "block": value["block"],
        "main_slot_count": len(value["streams"]["main"]["brackets"]),
        "required_sign_packet_rechecked": required_sign_packet is not None,
        "source_transform_packet_rechecked": source_packet is not None,
        "fixed_lattice_geometry_recomputed": True,
        "exact_rational_turing_recomputed": True,
        "lean_checker": "SparkInterval.Zeta.PT21ArtifactBinding.BlockArtifact.check",
        "finite_lean_contract_ready": True,
        "hardy_z_endpoint_realization_proved": False,
        "main_multiplicity_realization_proved": False,
        "analytic_turing_bounds_proved": False,
        "lean_source_claim_ready": False,
    }


def _rat(value: Fraction) -> str:
    if value.denominator == 1:
        return f"({value.numerator} : ℚ)"
    return f"({value.numerator} / {value.denominator} : ℚ)"


def _rat_interval(value: Interval) -> str:
    return f"⟨{_rat(value[0])}, {_rat(value[1])}⟩"


def _bytes(value: str) -> str:
    raw = bytes.fromhex(value)
    return "[" + ", ".join(f"0x{byte:02x}" for byte in raw) + "]"


def _endpoint_lean(value: dict[str, object], indent: str) -> str:
    positive = "true" if value["positive"] else "false"
    return f"⟨{_rat_interval(value['enclosure'])}, {positive}⟩"


def _bracket_lean(value: dict[str, object], indent: str) -> str:
    resolver = {
        "direct": ".direct",
        "stationary_left": ".stationaryLeft",
        "stationary_right": ".stationaryRight",
        "pinned_arb_fallback": ".pinnedArbFallback",
    }[value["resolver"]]
    digest = value["fallback_receipt_sha256"]
    fallback = "none" if digest is None else f"some {_bytes(digest)}"
    return (
        "⟨" + _rat(value["lower_offset"])
        + ", " + _rat(value["upper_offset"])
        + ", " + _endpoint_lean(value["lower_value"], indent)
        + ", " + _endpoint_lean(value["upper_value"], indent)
        + f", {resolver}, {fallback}⟩"
    )


def _event_lean(value: dict[str, int]) -> str:
    return (
        "⟨" + str(value["left_sample"])
        + ", " + str(value["right_sample"])
        + ", " + str(value["multiplicity"]) + "⟩"
    )


def _stream_lean(value: dict[str, object], indent: str = "  ") -> str:
    brackets = value["brackets"]
    if brackets:
        rendered = (",\n" + indent + "    ").join(
            _bracket_lean(bracket, indent + "    ") for bracket in brackets
        )
        bracket_text = "[\n" + indent + "    " + rendered + "\n" + indent + "  ]"
    else:
        bracket_text = "[]"
    events = value["events"]
    if events:
        event_rendered = (",\n" + indent + "    ").join(
            _event_lean(event) for event in events
        )
        event_text = "[\n" + indent + "    " + event_rendered + "\n" + indent + "  ]"
    else:
        event_text = "[]"
    return (
        "⟨" + _endpoint_lean(value["left_boundary"], indent)
        + ", " + _endpoint_lean(value["right_boundary"], indent)
        + ", " + bracket_text + ", " + event_text + "⟩"
    )


def render_lean_source(
    path: Path,
    declaration: str = "pt21BlockArtifact",
    *,
    required_sign_packet: Path | None = None,
    source_packet: Path | None = None,
) -> str:
    if not LEAN_NAME_RE.fullmatch(declaration):
        raise PT21LeanArtifactError("Lean declaration name is malformed")
    value = load(
        path,
        required_sign_packet=required_sign_packet,
        source_packet=source_packet,
    )
    streams = value["streams"]
    turing = value["turing"]
    lower = turing["lower"]
    upper = turing["upper"]
    return f"""import SparkInterval.Zeta.PT21ArtifactBinding

open SparkInterval.Zeta.PT21ArtifactBinding

def {declaration} : BlockArtifact := {{
  block := {value['block']}
  heightLower := {value['height_lower']}
  heightUpper := {value['height_upper']}
  windowCenter := {value['window_center']}
  upstreamCommitSha1 := {_bytes(value['upstream_commit'])}
  requiredSignPacketSha256 := {_bytes(value['required_sign_packet_sha256'])}
  sourceTraceSha256 := {_bytes(value['source_trace_sha256'])}
  main := {_stream_lean(streams['main'])}
  leftFlank := {_stream_lean(streams['left_flank'])}
  rightFlank := {_stream_lean(streams['right_flank'])}
  turing := {{
    lower := {{
      sBound := {_rat_interval(lower['s_bound'])}
      logPi := {_rat_interval(lower['log_pi'])}
      imGammaIntegral := {_rat_interval(lower['im_gamma_integral'])}
      pi := {_rat_interval(lower['pi'])}
      quotient := {_rat_interval(lower['quotient'])}
      count := {lower['count']}
    }}
    upper := {{
      sBound := {_rat_interval(upper['s_bound'])}
      logPi := {_rat_interval(upper['log_pi'])}
      imGammaIntegral := {_rat_interval(upper['im_gamma_integral'])}
      pi := {_rat_interval(upper['pi'])}
      quotient := {_rat_interval(upper['quotient'])}
      count := {upper['count']}
    }}
  }}
}}

#guard {declaration}.check
"""


__all__ = [
    "PT21LeanArtifactError",
    "SCHEMA",
    "UPSTREAM_COMMIT",
    "inspect",
    "load",
    "render_lean_source",
    "validate",
]
