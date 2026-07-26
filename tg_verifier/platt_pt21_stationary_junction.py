# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independent replay of the finite ``PT21EVT1`` → FLINT junction.

The 400-byte ``PT21STJ1`` wire binds one accepted event record to the exact
required DD words, canonical scanner candidate list, sparse-refinement trace,
native resolver input digest, stationary output, and pinned resolver/FLINT
identities.  This checker deliberately has no rule that turns those finite
relationships into Hardy-Z or Turing facts.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import struct
from typing import Mapping, Sequence

from tg_verifier.platt_pt21_event_record import (
    PT21EventRecordError,
    RECORD as EVENT_RECORD,
    parse_record as parse_event_record,
)
from tg_verifier.platt_stationary_trace import (
    PT21StationaryTraceError,
    validate as validate_stationary_trace,
)


MAGIC = b"PT21STJ1"
VERSION = 1
RECORD_BYTES = 400
RECORD_DIGEST_OFFSET = 368
SOURCE_BLOCK_COUNT = 2_966_443_783
REQUIRED_SAMPLE_COUNT = 25_741
MAXIMUM_CANDIDATES = 10_000
FLINT_RELEASE = 30_600
RECORD_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-stationary-junction-record/v1\0"
)
CANDIDATE_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-stationary-candidates/v1\0"
)
REFINEMENT_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-stationary-refinements/v1\0"
)
RESOLVER_INPUT_DOMAIN = (
    b"sparkinterval/tg/platt-pt21-stationary-input/v1\0"
)
SAMPLE = struct.Struct("<ddd")
CANDIDATE = struct.Struct("<IiiiiiIIIII")
PREFIX = struct.Struct("<8sIIQQ12I")
STREAM_RANGES = ((-12_800, -12_288), (-12_288, 12_288), (12_288, 12_800))


class PT21StationaryJunctionError(RuntimeError):
    """The finite junction record or one of its bound inputs differs."""


@dataclass(frozen=True)
class Candidate:
    stream: int
    left_sample: int
    middle_sample: int
    right_sample: int
    nleft_units_per_slot: int
    nright_units_per_slot: int
    source_positive: int
    strict_stat_pt: int
    requires_adaptive_resolution: int
    certified_multiplicity_slots: int
    multiplicity_slots_if_resolved: int

    def encode(self) -> bytes:
        return CANDIDATE.pack(
            self.stream,
            self.left_sample,
            self.middle_sample,
            self.right_sample,
            self.nleft_units_per_slot,
            self.nright_units_per_slot,
            self.source_positive,
            self.strict_stat_pt,
            self.requires_adaptive_resolution,
            self.certified_multiplicity_slots,
            self.multiplicity_slots_if_resolved,
        )


def _nonzero(raw: bytes, label: str) -> None:
    if len(raw) != 32 or raw == bytes(32):
        raise PT21StationaryJunctionError(f"{label} is zero or malformed")


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _lower_sha256(value: object, label: str) -> bytes:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PT21StationaryJunctionError(
            f"{label} is not lowercase SHA-256"
        )
    return bytes.fromhex(value)


def _u32(value: int) -> bytes:
    if isinstance(value, bool) or not 0 <= value < 2**32:
        raise PT21StationaryJunctionError("value leaves uint32")
    return struct.pack("<I", value)


def _i32(value: int) -> bytes:
    if isinstance(value, bool) or not -(2**31) <= value < 2**31:
        raise PT21StationaryJunctionError("value leaves int32")
    return struct.pack("<i", value)


def _bounded_string(value: object, label: str) -> bytes:
    if not isinstance(value, str):
        raise PT21StationaryJunctionError(f"{label} is not a string")
    encoded = value.encode()
    if not encoded or len(encoded) > 256 or b"\0" in encoded:
        raise PT21StationaryJunctionError(
            f"{label} leaves the native string bound"
        )
    return _u32(len(encoded)) + encoded


def validate_candidate(candidate: Candidate) -> None:
    if not 0 <= candidate.stream < len(STREAM_RANGES):
        raise PT21StationaryJunctionError("candidate stream leaves 0..2")
    lower, upper = STREAM_RANGES[candidate.stream]
    if (
        not lower <= candidate.left_sample <= upper - 2
        or candidate.middle_sample != candidate.left_sample + 1
        or candidate.right_sample != candidate.left_sample + 2
    ):
        raise PT21StationaryJunctionError("candidate geometry differs")
    edge = candidate.left_sample - lower
    if (
        candidate.nleft_units_per_slot != -edge
        or candidate.nright_units_per_slot != upper - lower - edge - 2
        or candidate.source_positive not in (0, 1)
        or candidate.strict_stat_pt != 1
        or candidate.requires_adaptive_resolution != 1
        or candidate.certified_multiplicity_slots != 0
        or candidate.multiplicity_slots_if_resolved != 2
    ):
        raise PT21StationaryJunctionError(
            "candidate finite or multiplicity contract differs"
        )


def candidate_list_sha256(candidates: Sequence[Candidate]) -> bytes:
    if len(candidates) > MAXIMUM_CANDIDATES:
        raise PT21StationaryJunctionError("candidate list exceeds cap")
    previous: tuple[int, int] | None = None
    frame = bytearray(_u32(len(candidates)))
    for candidate in candidates:
        validate_candidate(candidate)
        key = (candidate.stream, candidate.left_sample)
        if previous is not None and key <= previous:
            raise PT21StationaryJunctionError(
                "candidate list is duplicate or not canonical"
            )
        previous = key
        frame.extend(candidate.encode())
    return hashlib.sha256(CANDIDATE_DOMAIN + frame).digest()


def _validated_refinements(
    refinements: Sequence[Mapping[str, object]],
) -> tuple[bytes, int]:
    frame = bytearray(_u32(len(refinements)))
    previous: int | None = None
    for index, refinement in enumerate(refinements):
        if set(refinement) != {
            "sample_offset",
            "lower_arf_dump",
            "upper_arf_dump",
        }:
            raise PT21StationaryJunctionError(
                f"refinement[{index}] fields differ"
            )
        offset = refinement["sample_offset"]
        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or not -12_870 <= offset <= 12_870
            or (previous is not None and offset <= previous)
        ):
            raise PT21StationaryJunctionError(
                f"refinement[{index}] offset differs"
            )
        previous = offset
        frame.extend(_i32(offset))
        frame.extend(
            _bounded_string(
                refinement["lower_arf_dump"],
                f"refinement[{index}].lower_arf_dump",
            )
        )
        frame.extend(
            _bounded_string(
                refinement["upper_arf_dump"],
                f"refinement[{index}].upper_arf_dump",
            )
        )
    return bytes(frame), len(refinements)


def refinement_trace_sha256(
    refinements: Sequence[Mapping[str, object]],
) -> bytes:
    frame, _ = _validated_refinements(refinements)
    return hashlib.sha256(REFINEMENT_DOMAIN + frame).digest()


def validate_sample_payload(sample_payload: bytes) -> None:
    if len(sample_payload) != REQUIRED_SAMPLE_COUNT * SAMPLE.size:
        raise PT21StationaryJunctionError(
            "required sample payload has wrong byte length"
        )
    for index, (high, low, radius) in enumerate(
        SAMPLE.iter_unpack(sample_payload)
    ):
        if (
            not math.isfinite(high)
            or not math.isfinite(low)
            or not math.isfinite(radius)
            or radius < 0
        ):
            raise PT21StationaryJunctionError(
                f"required sample {index} is malformed"
            )


def resolver_input_sha256(
    sample_payload: bytes,
    candidates: Sequence[Candidate],
    refinements: Sequence[Mapping[str, object]],
) -> bytes:
    validate_sample_payload(sample_payload)
    # Validate and canonicalize the full scanner list first.  The native
    # resolver input deliberately retains only its four consumed fields.
    candidate_list_sha256(candidates)
    refinement_frame, refinement_count = _validated_refinements(refinements)
    frame = bytearray(_u32(REQUIRED_SAMPLE_COUNT))
    frame.extend(sample_payload)
    frame.extend(_u32(len(candidates)))
    for candidate in candidates:
        frame.extend(_u32(candidate.stream))
        frame.extend(_i32(candidate.left_sample))
        frame.extend(_i32(candidate.right_sample))
        frame.extend(_u32(candidate.source_positive))
    frame.extend(_u32(refinement_count))
    # Drop the already-encoded count from the standalone refinement frame.
    frame.extend(refinement_frame[4:])
    return hashlib.sha256(RESOLVER_INPUT_DOMAIN + frame).digest()


def parse_record(raw: bytes) -> dict[str, object]:
    if len(raw) != RECORD_BYTES:
        raise PT21StationaryJunctionError(
            "stationary junction record has wrong byte length"
        )
    fields = PREFIX.unpack_from(raw)
    (
        magic,
        version,
        encoded_bytes,
        block,
        failure_flags,
        candidate_count,
        resolution_count,
        ambiguous_input_count,
        refinement_count,
        multiplicity_slots,
        precision_bits,
        maximum_depth,
        replay_extra_precision_bits,
        flint_release,
        semantic_flags,
        resolver_replay_accepted,
        higher_precision_containment_complete,
    ) = fields
    if (
        magic != MAGIC
        or version != VERSION
        or encoded_bytes != RECORD_BYTES
        or not 0 <= block < SOURCE_BLOCK_COUNT
        or failure_flags != 0
        or candidate_count > MAXIMUM_CANDIDATES
        or resolution_count != candidate_count
        or ambiguous_input_count != refinement_count
        or ambiguous_input_count != 0
        or refinement_count != 0
        or multiplicity_slots != 2 * candidate_count
        or precision_bits != 128
        or not 1 <= maximum_depth <= 96
        or not 32 <= replay_extra_precision_bits <= 512
        or flint_release != FLINT_RELEASE
        or semantic_flags != 0
        or resolver_replay_accepted != 1
        or higher_precision_containment_complete != 1
    ):
        raise PT21StationaryJunctionError(
            "stationary junction finite fields differ"
        )
    names = (
        "event_record_sha256",
        "event_artifact_sha256",
        "candidate_list_sha256",
        "resolver_input_sha256",
        "refinement_trace_sha256",
        "resolution_sha256",
        "stationary_trace_sha256",
        "resolver_sha256",
        "flint_sha256",
    )
    result: dict[str, object] = {
        "block": block,
        "candidate_count": candidate_count,
        "resolution_count": resolution_count,
        "ambiguous_input_count": ambiguous_input_count,
        "refinement_count": refinement_count,
        "resolved_multiplicity_slots": multiplicity_slots,
        "precision_bits": precision_bits,
        "maximum_depth": maximum_depth,
        "replay_extra_precision_bits": replay_extra_precision_bits,
        "flint_release": flint_release,
        "resolver_replay_accepted": True,
        "higher_precision_containment_complete": True,
    }
    for index, name in enumerate(names):
        digest = raw[80 + 32 * index : 112 + 32 * index]
        _nonzero(digest, name)
        result[name] = digest.hex()
    expected = hashlib.sha256(
        RECORD_DOMAIN + raw[:RECORD_DIGEST_OFFSET]
    ).digest()
    if raw[RECORD_DIGEST_OFFSET:] != expected:
        raise PT21StationaryJunctionError(
            "stationary junction record digest differs"
        )
    result["record_sha256"] = expected.hex()
    return result


def replay(
    raw: bytes,
    *,
    event_record: bytes,
    sample_payload: bytes,
    candidates: Sequence[Candidate],
    refinements: Sequence[Mapping[str, object]],
    stationary_trace: Mapping[str, object],
    expected_resolver_sha256: str,
    expected_flint_sha256: str,
) -> dict[str, object]:
    """Independently replay every retained finite link in one junction."""

    record = parse_record(raw)
    if refinements:
        raise PT21StationaryJunctionError(
            "PT21STJ1 v1 requires event-scan rerun support before a "
            "nonempty sparse-refinement trace"
        )
    try:
        event = parse_event_record(
            event_record, expected_block=int(record["block"])
        )
    except PT21EventRecordError as error:
        raise PT21StationaryJunctionError(
            f"bound PT21EVT1 fails: {error}"
        ) from error
    if len(event_record) != EVENT_RECORD.size:
        raise PT21StationaryJunctionError("bound PT21EVT1 has wrong size")
    candidate_digest = candidate_list_sha256(candidates)
    input_digest = resolver_input_sha256(
        sample_payload, candidates, refinements
    )
    refinement_digest = refinement_trace_sha256(refinements)
    try:
        trace = validate_stationary_trace(dict(stationary_trace))
    except PT21StationaryTraceError as error:
        raise PT21StationaryJunctionError(
            f"stationary trace fails: {error}"
        ) from error
    trace_bytes = _canonical_json(trace) + b"\n"
    links = {
        "event_record_sha256": event_record[160:192],
        "event_artifact_sha256": bytes.fromhex(
            str(event["event_artifact_sha256"])
        ),
        "candidate_list_sha256": candidate_digest,
        "resolver_input_sha256": input_digest,
        "refinement_trace_sha256": refinement_digest,
        "resolution_sha256": _lower_sha256(
            trace["resolution_sha256"], "trace resolution_sha256"
        ),
        "stationary_trace_sha256": hashlib.sha256(trace_bytes).digest(),
        "resolver_sha256": _lower_sha256(
            expected_resolver_sha256, "expected resolver SHA-256"
        ),
        "flint_sha256": _lower_sha256(
            expected_flint_sha256, "expected FLINT SHA-256"
        ),
    }
    for name, expected in links.items():
        if record[name] != expected.hex():
            raise PT21StationaryJunctionError(f"{name} differs")
    counts = tuple(int(value) for value in event["stationary_candidate_count"])
    candidate_counts = tuple(
        sum(candidate.stream == stream for candidate in candidates)
        for stream in range(3)
    )
    if (
        counts != candidate_counts
        or int(record["candidate_count"]) != len(candidates)
        or int(record["refinement_count"]) != len(refinements)
        or int(trace["candidate_count"]) != len(candidates)
        or int(trace["ambiguous_input_disks"]) != len(refinements)
        or int(trace["refinements_applied"]) != len(refinements)
        or trace["input_sha256"] != input_digest.hex()
        or len(trace["stationary_resolutions"]) != len(candidates)
    ):
        raise PT21StationaryJunctionError(
            "junction count, input, or multiplicity linkage differs"
        )
    return {
        **record,
        "accepted": True,
        "event_record_valid": True,
        "resolver_input_replayed": True,
        "stationary_trace_replayed": True,
        "resolved_multiplicity_slots": 2 * len(candidates),
        "unresolved_stationary_count": 0,
        "hardy_z_endpoint_realization_proved": False,
        "flint_to_mathlib_realization_proved": False,
        "analytic_turing_realization_proved": False,
        "source_claim_ready": False,
    }


__all__ = [
    "CANDIDATE",
    "Candidate",
    "PT21StationaryJunctionError",
    "RECORD_BYTES",
    "SAMPLE",
    "candidate_list_sha256",
    "parse_record",
    "refinement_trace_sha256",
    "replay",
    "resolver_input_sha256",
]
