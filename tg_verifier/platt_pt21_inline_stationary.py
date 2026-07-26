# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independent verifier for qualification-only inline PT21 stationary wire.

``PT21IQF1`` binds an existing ``PT21EVT1`` record, its ``PT21STJ1`` finite
junction record, and the canonical stationary trace.  This parser checks the
stream framing, ordered range, nested finite records, identity pins, and the
stationary trace's exact-rational semantics.  It deliberately has no rule for
SGN2/static-manifest realization, a multi-block source chain, Turing closure,
or the PT21 analytic claim.
"""

from __future__ import annotations

import hashlib
import json
import struct
from typing import Any

from tg_verifier.platt_pt21_event_record import (
    SOURCE_BLOCK_COUNT,
    parse_record as parse_event_record,
)
from tg_verifier.platt_pt21_stationary_junction import (
    parse_record as parse_junction_record,
)
from tg_verifier.platt_stationary_trace import (
    MAXIMUM_BYTES as MAXIMUM_TRACE_BYTES,
    PT21StationaryTraceError,
    validate as validate_stationary_trace,
)


VERSION = 1
FINITE_QUALIFICATION_ONLY_FLAG = 1
HEADER_MAGIC = b"PT21IQH1"
FRAME_MAGIC = b"PT21IQF1"
FOOTER_MAGIC = b"PT21IQT1"
ALGORITHM_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-inline-stationary-qualification/v1\0"
)
HEADER_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-inline-stationary-header/v1\0"
)
FRAME_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-inline-stationary-frame/v1\0"
)
FOOTER_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-inline-stationary-footer/v1\0"
)

HEADER = struct.Struct("<8s4I2Q32s32s32s32s32sI20s32s")
FRAME_PREFIX = struct.Struct("<8sIIQ4IQ32s32s32s")
FOOTER = struct.Struct("<8sII5Q32s32s32s8s32s")
EVENT_BYTES = 192
JUNCTION_BYTES = 400
FRAME_DIGEST_BYTES = 32
MAXIMUM_FRAME_BYTES = (
    FRAME_PREFIX.size
    + EVENT_BYTES
    + JUNCTION_BYTES
    + MAXIMUM_TRACE_BYTES
    + FRAME_DIGEST_BYTES
)


class PT21InlineStationaryError(RuntimeError):
    """The qualification-only inline stationary stream is malformed."""


def _nonzero(value: bytes, label: str) -> None:
    if len(value) != 32 or value == bytes(32):
        raise PT21InlineStationaryError(f"{label} identity is zero")


def _lower_sha256(value: str, label: str) -> bytes:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PT21InlineStationaryError(
            f"{label} is not lowercase SHA-256"
        )
    return bytes.fromhex(value)


def _geometry(first_block: int, block_count: int) -> None:
    # This subtraction-shaped bound is also the explicit overflow guard in the
    # C++ encoder. Python integers do not overflow, but the wire values are Q.
    if (
        not 0 <= first_block < SOURCE_BLOCK_COUNT
        or block_count < 1
        or block_count > SOURCE_BLOCK_COUNT - first_block
    ):
        raise PT21InlineStationaryError(
            "inline stationary range is outside PT21"
        )


def parse_header(
    raw: bytes,
    *,
    expected_gamma_stream_sha256: str | None = None,
    expected_producer_sha256: str | None = None,
    expected_resolver_sha256: str | None = None,
    expected_flint_sha256: str | None = None,
) -> dict[str, object]:
    if len(raw) != HEADER.size:
        raise PT21InlineStationaryError(
            "inline stationary header has wrong byte length"
        )
    (
        magic,
        version,
        header_bytes,
        frame_prefix_bytes,
        footer_bytes,
        first_block,
        block_count,
        gamma,
        producer,
        resolver,
        flint,
        algorithm,
        finite_flag,
        reserved,
        digest,
    ) = HEADER.unpack(raw)
    if (
        magic != HEADER_MAGIC
        or version != VERSION
        or header_bytes != HEADER.size
        or frame_prefix_bytes != FRAME_PREFIX.size
        or footer_bytes != FOOTER.size
        or finite_flag != FINITE_QUALIFICATION_ONLY_FLAG
        or reserved != bytes(len(reserved))
    ):
        raise PT21InlineStationaryError(
            "inline stationary fixed header fields differ"
        )
    _geometry(first_block, block_count)
    for value, label in (
        (gamma, "Gamma stream"),
        (producer, "producer"),
        (resolver, "resolver"),
        (flint, "FLINT"),
    ):
        _nonzero(value, label)
    if algorithm != hashlib.sha256(ALGORITHM_DOMAIN).digest():
        raise PT21InlineStationaryError(
            "inline stationary algorithm identity differs"
        )
    expected_digest = hashlib.sha256(
        HEADER_DOMAIN + raw[: HEADER.size - 32]
    ).digest()
    if digest != expected_digest:
        raise PT21InlineStationaryError(
            "inline stationary header digest differs"
        )
    for actual, expected, label in (
        (gamma, expected_gamma_stream_sha256, "Gamma stream"),
        (producer, expected_producer_sha256, "producer"),
        (resolver, expected_resolver_sha256, "resolver"),
        (flint, expected_flint_sha256, "FLINT"),
    ):
        if expected is not None and actual != _lower_sha256(expected, label):
            raise PT21InlineStationaryError(
                f"inline stationary {label} differs from its external pin"
            )
    return {
        "first_block": first_block,
        "block_count": block_count,
        "gamma_stream_sha256": gamma.hex(),
        "producer_sha256": producer.hex(),
        "resolver_sha256": resolver.hex(),
        "flint_sha256": flint.hex(),
        "algorithm_sha256": algorithm.hex(),
        "header_sha256": digest.hex(),
    }


def parse_frame(
    raw: bytes,
    *,
    expected_block: int,
    expected_resolver_sha256: str,
    expected_flint_sha256: str,
) -> dict[str, object]:
    if len(raw) < FRAME_PREFIX.size + EVENT_BYTES + JUNCTION_BYTES + 1 + 32:
        raise PT21InlineStationaryError(
            "inline stationary frame is truncated"
        )
    (
        magic,
        version,
        frame_bytes,
        block,
        event_bytes,
        junction_bytes,
        trace_bytes,
        reserved32,
        failure_flags,
        event_sha256,
        junction_sha256,
        trace_sha256,
    ) = FRAME_PREFIX.unpack_from(raw)
    if (
        magic != FRAME_MAGIC
        or version != VERSION
        or frame_bytes != len(raw)
        or frame_bytes > MAXIMUM_FRAME_BYTES
        or block != expected_block
        or event_bytes != EVENT_BYTES
        or junction_bytes != JUNCTION_BYTES
        or not 1 <= trace_bytes <= MAXIMUM_TRACE_BYTES
        or reserved32 != 0
        or failure_flags != 0
        or frame_bytes
        != FRAME_PREFIX.size
        + event_bytes
        + junction_bytes
        + trace_bytes
        + FRAME_DIGEST_BYTES
    ):
        raise PT21InlineStationaryError(
            "inline stationary frame fields or lengths differ"
        )
    expected_frame_digest = hashlib.sha256(
        FRAME_DOMAIN + raw[:-FRAME_DIGEST_BYTES]
    ).digest()
    if raw[-FRAME_DIGEST_BYTES:] != expected_frame_digest:
        raise PT21InlineStationaryError(
            "inline stationary frame digest differs"
        )
    offset = FRAME_PREFIX.size
    event = raw[offset : offset + event_bytes]
    offset += event_bytes
    junction = raw[offset : offset + junction_bytes]
    offset += junction_bytes
    trace_raw = raw[offset : offset + trace_bytes]
    if (
        hashlib.sha256(event).digest() != event_sha256
        or hashlib.sha256(junction).digest() != junction_sha256
        or hashlib.sha256(trace_raw).digest() != trace_sha256
    ):
        raise PT21InlineStationaryError(
            "inline stationary payload digest differs"
        )
    try:
        event_value = parse_event_record(event, expected_block=expected_block)
        junction_value = parse_junction_record(junction)
    except Exception as error:
        raise PT21InlineStationaryError(
            f"inline stationary nested record failed: {error}"
        ) from error
    if (
        junction_value["block"] != expected_block
        or junction_value["event_record_sha256"]
        != event_value["record_sha256"]
        or junction_value["event_artifact_sha256"]
        != event_value["event_artifact_sha256"]
        or junction_value["resolver_sha256"]
        != expected_resolver_sha256
        or junction_value["flint_sha256"] != expected_flint_sha256
    ):
        raise PT21InlineStationaryError(
            "inline stationary nested record link or identity differs"
        )
    try:
        trace_text = trace_raw.decode("utf-8")
        trace_json = json.loads(trace_text)
        canonical = (
            json.dumps(trace_json, sort_keys=True, separators=(",", ":"))
            + "\n"
        )
        if trace_text != canonical:
            raise PT21InlineStationaryError(
                "inline stationary trace is not canonical JSON"
            )
        trace_value = validate_stationary_trace(trace_json)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        PT21StationaryTraceError,
    ) as error:
        raise PT21InlineStationaryError(
            f"inline stationary trace semantics failed: {error}"
        ) from error
    if (
        junction_value["stationary_trace_sha256"] != trace_sha256.hex()
        or junction_value["candidate_count"] != trace_value["candidate_count"]
        or junction_value["resolution_count"]
        != len(trace_value["stationary_resolutions"])
        or junction_value["resolution_sha256"]
        != trace_value["resolution_sha256"]
    ):
        raise PT21InlineStationaryError(
            "inline stationary trace differs from PT21STJ1")
    return {
        "block": expected_block,
        "event_record": event,
        "junction_record": junction,
        "stationary_trace": trace_raw,
        "trace_value": trace_value,
        "trace_bytes": trace_bytes,
        "frame_sha256": expected_frame_digest.hex(),
    }


def parse_footer(raw: bytes) -> dict[str, object]:
    if len(raw) != FOOTER.size:
        raise PT21InlineStationaryError(
            "inline stationary footer has wrong byte length"
        )
    (
        magic,
        version,
        footer_bytes,
        first_block,
        block_count,
        total_event_records,
        total_junction_records,
        total_trace_bytes,
        frame_stream_sha256,
        header_sha256,
        gamma_stream_sha256,
        reserved,
        digest,
    ) = FOOTER.unpack(raw)
    if (
        magic != FOOTER_MAGIC
        or version != VERSION
        or footer_bytes != FOOTER.size
        or total_event_records != block_count
        or total_junction_records != block_count
        or reserved != bytes(len(reserved))
    ):
        raise PT21InlineStationaryError(
            "inline stationary footer fields differ"
        )
    _geometry(first_block, block_count)
    for value, label in (
        (frame_stream_sha256, "frame stream"),
        (header_sha256, "header"),
        (gamma_stream_sha256, "Gamma stream"),
    ):
        _nonzero(value, label)
    expected_digest = hashlib.sha256(
        FOOTER_DOMAIN + raw[: FOOTER.size - 32]
    ).digest()
    if digest != expected_digest:
        raise PT21InlineStationaryError(
            "inline stationary footer digest differs"
        )
    return {
        "first_block": first_block,
        "block_count": block_count,
        "total_event_records": total_event_records,
        "total_junction_records": total_junction_records,
        "total_trace_bytes": total_trace_bytes,
        "frame_stream_sha256": frame_stream_sha256.hex(),
        "header_sha256": header_sha256.hex(),
        "gamma_stream_sha256": gamma_stream_sha256.hex(),
        "footer_sha256": digest.hex(),
    }


def validate_bytes(
    raw: bytes,
    *,
    expected_gamma_stream_sha256: str,
    expected_producer_sha256: str,
    expected_resolver_sha256: str,
    expected_flint_sha256: str,
) -> dict[str, Any]:
    if len(raw) < HEADER.size + FOOTER.size:
        raise PT21InlineStationaryError(
            "inline stationary stream is truncated"
        )
    header_raw = raw[: HEADER.size]
    header = parse_header(
        header_raw,
        expected_gamma_stream_sha256=expected_gamma_stream_sha256,
        expected_producer_sha256=expected_producer_sha256,
        expected_resolver_sha256=expected_resolver_sha256,
        expected_flint_sha256=expected_flint_sha256,
    )
    offset = HEADER.size
    frames: list[dict[str, object]] = []
    frame_hasher = hashlib.sha256()
    trace_total = 0
    for index in range(int(header["block_count"])):
        if offset + FRAME_PREFIX.size > len(raw) - FOOTER.size:
            raise PT21InlineStationaryError(
                "inline stationary frame prefix is truncated"
            )
        frame_bytes = struct.unpack_from("<I", raw, offset + 12)[0]
        if (
            frame_bytes < FRAME_PREFIX.size + EVENT_BYTES
            + JUNCTION_BYTES + 1 + FRAME_DIGEST_BYTES
            or frame_bytes > MAXIMUM_FRAME_BYTES
            or offset + frame_bytes > len(raw) - FOOTER.size
        ):
            raise PT21InlineStationaryError(
                "inline stationary frame leaves its stream bound"
            )
        frame_raw = raw[offset : offset + frame_bytes]
        frame = parse_frame(
            frame_raw,
            expected_block=int(header["first_block"]) + index,
            expected_resolver_sha256=expected_resolver_sha256,
            expected_flint_sha256=expected_flint_sha256,
        )
        frame_hasher.update(frame_raw)
        trace_total += int(frame["trace_bytes"])
        if trace_total >= 2**64:
            raise PT21InlineStationaryError(
                "inline stationary trace byte total overflows uint64"
            )
        frames.append(frame)
        offset += frame_bytes
    if offset + FOOTER.size != len(raw):
        raise PT21InlineStationaryError(
            "inline stationary stream has missing or trailing bytes"
        )
    footer = parse_footer(raw[offset:])
    expected_footer = {
        "first_block": header["first_block"],
        "block_count": header["block_count"],
        "total_event_records": header["block_count"],
        "total_junction_records": header["block_count"],
        "total_trace_bytes": trace_total,
        "frame_stream_sha256": frame_hasher.hexdigest(),
        "header_sha256": header["header_sha256"],
        "gamma_stream_sha256": header["gamma_stream_sha256"],
    }
    for key, expected in expected_footer.items():
        if footer[key] != expected:
            raise PT21InlineStationaryError(
                f"inline stationary footer {key} differs from its stream"
            )
    return {
        "accepted": True,
        "qualification_only": True,
        "header": header,
        "frames": frames,
        "footer": footer,
        # PT21IQF1 deliberately retains only the compact finite outputs.  It
        # therefore permits an independent framing, exact-hull, and semantic
        # replay, but not regeneration of the resolver input hash or proof
        # that its 25,741-sample candidate roster was complete.
        "resolver_inputs_retained": False,
        "resolver_input_sha256_recomputed_from_frame": False,
        "candidate_completeness_recomputed_from_frame": False,
        "independent_checker_complete": False,
        # These are caller-supplied identity pins.  The compact stream does
        # not inspect its producer, resolver, or FLINT executable bytes.
        "producer_sha256_self_verified": False,
        "resolver_sha256_self_verified": False,
        "flint_sha256_self_verified": False,
        "identity_pins_require_external_manifest_or_attestation": True,
        "higher_precision_containment_semantics":
            "replay_contained_in_retained_outward_hull",
        "hardy_z_endpoint_realization_proved": False,
        "flint_to_mathlib_realization_proved": False,
        "analytic_turing_realization_proved": False,
        "sgn2_static_manifest_bound": False,
        "multi_block_source_chain_closed": False,
        "source_claim_ready": False,
        "production_ready": False,
        "pt21_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_DOMAIN",
    "FOOTER",
    "FRAME_PREFIX",
    "HEADER",
    "PT21InlineStationaryError",
    "_geometry",
    "parse_footer",
    "parse_frame",
    "parse_header",
    "validate_bytes",
]
