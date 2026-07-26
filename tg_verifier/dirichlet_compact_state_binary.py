# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Canonical bounded binary storage for fixed-q compact sign-scan state.

``TGDCSB02`` has one fixed-width index record per canonical primitive
character followed by character-major maximal-ambiguity and ordered-bracket
sections.  Every sparse slice has one canonical absolute offset and length;
the reader requires those slices to cover each section exactly once in roster
order.  This makes restart validation streaming and fail-closed for gaps,
overlaps, reorderings, truncation, substitution, and integer overflow.

This remains restart state, not zero completeness.  Exact exception locations
are retained, but no refinement or Turing count is performed here.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
from typing import Any, BinaryIO, Mapping, NoReturn

from tg_verifier.dirichlet_root_number_stage import (
    primitive_frequency_records_bulk,
)
from tg_verifier.dirichlet_stream_zero_consumer import (
    COMPACT_STATE_SCHEMA,
    MAX_EVENT_COUNT,
    SOURCE_SAMPLE_DENOMINATOR,
    SOURCE_SAMPLE_NUMERATOR,
    _ROLLING_BASE,
    _ROLLING_MODULUS,
    canonical_json_bytes,
    validate_compact_state_summary,
)


AUTHOR = "Gershon Bialer"
ARTIFACT_SCHEMA = (
    "sparkinterval.tg.dirichlet_stream_consumer.compact_state_binary.v2"
)
ARTIFACT_MAGIC = b"TGDCSB02"
ARTIFACT_FORMAT_VERSION = 2
DEFAULT_MAXIMUM_ARTIFACT_BYTES = 64 * 1024 * 1024
MAXIMUM_ARTIFACT_BYTES = 256 * 1024 * 1024
MAXIMUM_MODULUS = 400_000

# magic, version, q; primitive/frame/grid; denominator/step; leaf/internal/
# cross/total/ambiguity/range/bracket counts; leaf commitment; roster digest.
ARTIFACT_HEADER = struct.Struct(
    "<8sIIQQQQIIQQQQQQQ32s32s"
)

# first/last determinate numerator (UINT64_MAX means absent), leading/trailing
# ambiguity, total ambiguity, positive, negative and bracket counts; canonical
# absolute byte offset and record count for each sparse section; first/last
# signs and fixed zero padding.  Sample count and identity are implicit.
CHARACTER_RECORD = struct.Struct("<QQQQQQQQQQQQbb6x")
AMBIGUITY_RANGE_RECORD = struct.Struct("<QQ")
BRACKET_RECORD = struct.Struct("<QQbb6xQ")
ABSENT_NUMERATOR = (1 << 64) - 1


class DirichletCompactStateBinaryError(RuntimeError):
    """A compact state artifact is malformed, substituted, or unbounded."""


def _fail(message: str) -> NoReturn:
    raise DirichletCompactStateBinaryError(message)


def _digest(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{name} must be a lowercase SHA-256 digest")
    return value


def _bounded_uint64(name: str, value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= MAX_EVENT_COUNT
    ):
        _fail(f"{name} is outside uint64")
    return value


def _maximum_bytes(value: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= MAXIMUM_ARTIFACT_BYTES
    ):
        _fail(
            "maximum compact-state artifact bytes must be in "
            f"1..{MAXIMUM_ARTIFACT_BYTES}"
        )
    return value


def _read_exact(source: BinaryIO, length: int, *, label: str) -> bytes:
    raw = source.read(length)
    if len(raw) != length:
        _fail(f"truncated {label}")
    return raw


def _roster_digest(identities: object) -> str:
    return hashlib.sha256(canonical_json_bytes(identities)).hexdigest()


def _state_body(
    *,
    q: int,
    primitive_count: int,
    frame_count: int,
    first_t_numerator: int,
    stop_t_numerator: int,
    leaf_count: int,
    leaf_commitment: int,
    internal_sign_changes: int,
    cross_boundary_sign_changes: int,
    sign_change_lower_bound: int,
    ambiguity_samples: int,
    states: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": COMPACT_STATE_SCHEMA,
        "schema_version": 2,
        "classification": (
            "associative_per_character_sign_scan_state_not_zero_completeness"
        ),
        "context": {
            "q": q,
            "primitive_character_count": primitive_count,
            "frame_count": frame_count,
            "first_t_numerator": first_t_numerator,
            "stop_t_numerator": stop_t_numerator,
            "t_denominator": SOURCE_SAMPLE_DENOMINATOR,
            "t_step_numerator": SOURCE_SAMPLE_NUMERATOR,
        },
        "character_states": states,
        "leaf_event_summary_count": leaf_count,
        "leaf_event_summary_commitment": {
            "modulus_hex": f"{_ROLLING_MODULUS:064x}",
            "base_hex": f"{_ROLLING_BASE:064x}",
            "value_hex": f"{leaf_commitment:064x}",
            "leaf_count": leaf_count,
            "combination": (
                "(n,h)++(m,g)=(n+m,h*base^m+g mod modulus)"
            ),
        },
        "internal_sign_change_count": internal_sign_changes,
        "cross_boundary_sign_change_count": cross_boundary_sign_changes,
        "sign_change_lower_bound": sign_change_lower_bound,
        "ambiguity_sample_count": ambiguity_samples,
        "exact_ambiguity_ranges_retained": True,
        "ordered_bracket_records_retained": True,
        "refinement_artifacts_complete": False,
        "turing_completeness": False,
        "source_scale_state_encoding": False,
        "external_atom_discharged": False,
    }


def _artifact_record(
    *,
    path: Path,
    artifact_sha256: str,
    size_bytes: int,
    state: Mapping[str, Any],
) -> dict[str, Any]:
    context = state["context"]
    ambiguity_range_count = sum(
        len(character["ambiguity_ranges"])
        for character in state["character_states"]
    )
    bracket_record_count = sum(
        len(character["bracket_records"])
        for character in state["character_states"]
    )
    body: dict[str, Any] = {
        "schema": ARTIFACT_SCHEMA,
        "schema_version": 2,
        "classification": (
            "bounded_q_major_restart_state_not_zero_or_turing_evidence"
        ),
        "path": str(path.resolve()),
        "artifact_sha256": artifact_sha256,
        "size_bytes": size_bytes,
        "state_sha256": state["state_sha256"],
        "q": context["q"],
        "primitive_character_count": context[
            "primitive_character_count"
        ],
        "frame_count": context["frame_count"],
        "first_t_numerator": context["first_t_numerator"],
        "stop_t_numerator": context["stop_t_numerator"],
        "header_bytes": ARTIFACT_HEADER.size,
        "character_record_bytes": CHARACTER_RECORD.size,
        "character_record_count": len(state["character_states"]),
        "ambiguity_range_record_bytes": AMBIGUITY_RANGE_RECORD.size,
        "ambiguity_range_record_count": ambiguity_range_count,
        "bracket_record_bytes": BRACKET_RECORD.size,
        "bracket_record_count": bracket_record_count,
        "canonical_roster_implicit_by_ordinal": True,
        "canonical_sparse_offsets_and_lengths": True,
        "exact_ambiguity_ranges_retained": True,
        "ordered_bracket_records_retained": True,
        "streaming_validation": True,
        "refinement_artifacts_complete": False,
        "turing_completeness": False,
        "source_scale_state_encoding": False,
        "external_atom_discharged": False,
    }
    result = dict(body)
    result["record_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def _validate_record(value: Mapping[str, Any]) -> str:
    required = {
        "schema",
        "schema_version",
        "classification",
        "path",
        "artifact_sha256",
        "size_bytes",
        "state_sha256",
        "q",
        "primitive_character_count",
        "frame_count",
        "first_t_numerator",
        "stop_t_numerator",
        "header_bytes",
        "character_record_bytes",
        "character_record_count",
        "ambiguity_range_record_bytes",
        "ambiguity_range_record_count",
        "bracket_record_bytes",
        "bracket_record_count",
        "canonical_roster_implicit_by_ordinal",
        "canonical_sparse_offsets_and_lengths",
        "exact_ambiguity_ranges_retained",
        "ordered_bracket_records_retained",
        "streaming_validation",
        "refinement_artifacts_complete",
        "turing_completeness",
        "source_scale_state_encoding",
        "external_atom_discharged",
        "record_sha256",
    }
    body = dict(value)
    claimed = body.pop("record_sha256", None)
    path = value.get("path")
    if (
        set(value) != required
        or value.get("schema") != ARTIFACT_SCHEMA
        or value.get("schema_version") != 2
        or value.get("classification")
        != "bounded_q_major_restart_state_not_zero_or_turing_evidence"
        or not isinstance(path, str)
        or not Path(path).is_absolute()
        or str(Path(path).resolve()) != path
        or value.get("header_bytes") != ARTIFACT_HEADER.size
        or value.get("character_record_bytes") != CHARACTER_RECORD.size
        or value.get("ambiguity_range_record_bytes")
        != AMBIGUITY_RANGE_RECORD.size
        or value.get("bracket_record_bytes") != BRACKET_RECORD.size
        or value.get("canonical_roster_implicit_by_ordinal") is not True
        or value.get("canonical_sparse_offsets_and_lengths") is not True
        or value.get("exact_ambiguity_ranges_retained") is not True
        or value.get("ordered_bracket_records_retained") is not True
        or value.get("streaming_validation") is not True
        or value.get("refinement_artifacts_complete") is not False
        or value.get("turing_completeness") is not False
        or value.get("source_scale_state_encoding") is not False
        or value.get("external_atom_discharged") is not False
        or claimed != hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    ):
        _fail("compact-state artifact record identity or self-hash differs")
    _digest("compact-state artifact", value.get("artifact_sha256"))
    _digest("compact-state semantic state", value.get("state_sha256"))
    for field in (
        "size_bytes",
        "q",
        "primitive_character_count",
        "frame_count",
        "first_t_numerator",
        "stop_t_numerator",
        "character_record_count",
        "ambiguity_range_record_count",
        "bracket_record_count",
    ):
        _bounded_uint64(field, value.get(field))
    if (
        value["size_bytes"]
        != ARTIFACT_HEADER.size
        + value["character_record_count"] * CHARACTER_RECORD.size
        + value["ambiguity_range_record_count"]
        * AMBIGUITY_RANGE_RECORD.size
        + value["bracket_record_count"] * BRACKET_RECORD.size
        or value["character_record_count"]
        != value["primitive_character_count"]
        or value["frame_count"] == 0
        or not 1 <= value["q"] <= MAXIMUM_MODULUS
        or value["stop_t_numerator"] < value["first_t_numerator"]
    ):
        _fail("compact-state artifact record arithmetic differs")
    return claimed


def write_compact_state_binary(
    path: Path,
    state: Mapping[str, Any],
    *,
    maximum_bytes: int = DEFAULT_MAXIMUM_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Atomically materialize one validated fixed-q state."""

    maximum_bytes = _maximum_bytes(maximum_bytes)
    validate_compact_state_summary(state)
    context = state["context"]
    q = _bounded_uint64("state q", context["q"])
    if not 1 <= q <= MAXIMUM_MODULUS:
        _fail(f"state q is outside 1..{MAXIMUM_MODULUS}")
    identities = primitive_frequency_records_bulk(q)
    primitive_count = len(identities)
    if primitive_count != context["primitive_character_count"]:
        _fail("state primitive roster differs before binary materialization")
    ambiguity_range_count = 0
    bracket_record_count = 0
    for character in state["character_states"]:
        ambiguity_range_count += len(character["ambiguity_ranges"])
        bracket_record_count += len(character["bracket_records"])
        if (
            ambiguity_range_count > MAX_EVENT_COUNT
            or bracket_record_count > MAX_EVENT_COUNT
        ):
            _fail("compact-state sparse record count overflows uint64")
    character_section_stop = (
        ARTIFACT_HEADER.size + primitive_count * CHARACTER_RECORD.size
    )
    ambiguity_section_stop = (
        character_section_stop
        + ambiguity_range_count * AMBIGUITY_RANGE_RECORD.size
    )
    size = (
        ambiguity_section_stop
        + bracket_record_count * BRACKET_RECORD.size
    )
    if size > maximum_bytes:
        _fail("compact-state binary exceeds its externally supplied byte bound")
    commitment = int(
        state["leaf_event_summary_commitment"]["value_hex"], 16
    )
    header = ARTIFACT_HEADER.pack(
        ARTIFACT_MAGIC,
        ARTIFACT_FORMAT_VERSION,
        q,
        primitive_count,
        _bounded_uint64("frame count", context["frame_count"]),
        _bounded_uint64("first t numerator", context["first_t_numerator"]),
        _bounded_uint64("stop t numerator", context["stop_t_numerator"]),
        SOURCE_SAMPLE_DENOMINATOR,
        SOURCE_SAMPLE_NUMERATOR,
        _bounded_uint64(
            "leaf event-summary count",
            state["leaf_event_summary_count"],
        ),
        _bounded_uint64(
            "internal sign changes", state["internal_sign_change_count"]
        ),
        _bounded_uint64(
            "cross-boundary sign changes",
            state["cross_boundary_sign_change_count"],
        ),
        _bounded_uint64(
            "sign-change lower bound", state["sign_change_lower_bound"]
        ),
        _bounded_uint64(
            "ambiguity samples", state["ambiguity_sample_count"]
        ),
        ambiguity_range_count,
        bracket_record_count,
        commitment.to_bytes(32, "big"),
        bytes.fromhex(_roster_digest(identities)),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    digest = hashlib.sha256()
    written = 0
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(header)
            digest.update(header)
            written += len(header)
            ambiguity_offset = character_section_stop
            bracket_offset = ambiguity_section_stop
            for character in state["character_states"]:
                first = character["first_determinate_numerator"]
                last = character["last_determinate_numerator"]
                if first == ABSENT_NUMERATOR or last == ABSENT_NUMERATOR:
                    _fail("determinate numerator collides with absent sentinel")
                character_ambiguities = len(character["ambiguity_ranges"])
                character_brackets = len(character["bracket_records"])
                raw = CHARACTER_RECORD.pack(
                    ABSENT_NUMERATOR if first is None else first,
                    ABSENT_NUMERATOR if last is None else last,
                    character["leading_ambiguity_count"],
                    character["trailing_ambiguity_count"],
                    character["ambiguity_count"],
                    character["positive_count"],
                    character["negative_count"],
                    character["bracket_count"],
                    ambiguity_offset,
                    character_ambiguities,
                    bracket_offset,
                    character_brackets,
                    character["first_sign"],
                    character["last_sign"],
                )
                output.write(raw)
                digest.update(raw)
                written += len(raw)
                ambiguity_offset += (
                    character_ambiguities * AMBIGUITY_RANGE_RECORD.size
                )
                bracket_offset += (
                    character_brackets * BRACKET_RECORD.size
                )
            if (
                ambiguity_offset != ambiguity_section_stop
                or bracket_offset != size
            ):
                _fail("compact-state sparse index coverage differs")
            for character in state["character_states"]:
                for ambiguity_range in character["ambiguity_ranges"]:
                    raw = AMBIGUITY_RANGE_RECORD.pack(
                        _bounded_uint64(
                            "ambiguity range first",
                            ambiguity_range["first_t_numerator"],
                        ),
                        _bounded_uint64(
                            "ambiguity range stop",
                            ambiguity_range["stop_t_numerator"],
                        ),
                    )
                    output.write(raw)
                    digest.update(raw)
                    written += len(raw)
            for character in state["character_states"]:
                for bracket in character["bracket_records"]:
                    raw = BRACKET_RECORD.pack(
                        _bounded_uint64(
                            "bracket lower",
                            bracket["lower_t_numerator"],
                        ),
                        _bounded_uint64(
                            "bracket upper",
                            bracket["upper_t_numerator"],
                        ),
                        bracket["lower_sign"],
                        bracket["upper_sign"],
                        _bounded_uint64(
                            "bracket intervening ambiguity",
                            bracket["intervening_ambiguity_count"],
                        ),
                    )
                    output.write(raw)
                    digest.update(raw)
                    written += len(raw)
            output.flush()
            os.fsync(output.fileno())
        if written != size:
            _fail("compact-state binary write size differs")
        artifact_sha256 = digest.hexdigest()
        if path.exists():
            existing = read_compact_state_binary(
                path,
                maximum_bytes=maximum_bytes,
            )
            if (
                existing["state_sha256"] != state["state_sha256"]
                or hashlib.sha256(path.read_bytes()).hexdigest()
                != artifact_sha256
            ):
                _fail("existing compact-state binary is substituted")
            temporary.unlink()
        else:
            os.replace(temporary, path)
            directory = os.open(
                path.parent,
                getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY,
            )
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    record = _artifact_record(
        path=path,
        artifact_sha256=artifact_sha256,
        size_bytes=size,
        state=state,
    )
    _validate_record(record)
    return record


def read_compact_state_binary(
    path: Path,
    *,
    expected_record: Mapping[str, Any] | None = None,
    maximum_bytes: int = DEFAULT_MAXIMUM_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Stream, validate, and reconstruct one canonical state artifact."""

    maximum_bytes = _maximum_bytes(maximum_bytes)
    if expected_record is not None:
        _validate_record(expected_record)
        if expected_record.get("path") != str(path.resolve()):
            _fail("compact-state expected path differs")
    try:
        status = path.lstat()
    except OSError as error:
        raise DirichletCompactStateBinaryError(
            f"cannot stat compact-state binary: {error}"
        ) from error
    if (
        not stat.S_ISREG(status.st_mode)
        or path.is_symlink()
        or status.st_size < ARTIFACT_HEADER.size
        or status.st_size > maximum_bytes
    ):
        _fail("compact-state binary is not one bounded regular file")
    if (
        expected_record is not None
        and status.st_size != expected_record["size_bytes"]
    ):
        _fail("compact-state binary size differs from checkpoint")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        raw_header = _read_exact(
            source, ARTIFACT_HEADER.size, label="compact-state header"
        )
        digest.update(raw_header)
        (
            magic,
            version,
            q,
            primitive_count,
            frame_count,
            first_t_numerator,
            stop_t_numerator,
            denominator,
            step,
            leaf_count,
            internal_sign_changes,
            cross_boundary_sign_changes,
            sign_change_lower_bound,
            ambiguity_samples,
            ambiguity_range_count,
            bracket_record_count,
            raw_commitment,
            raw_roster_digest,
        ) = ARTIFACT_HEADER.unpack(raw_header)
        character_section_stop = (
            ARTIFACT_HEADER.size
            + primitive_count * CHARACTER_RECORD.size
        )
        ambiguity_section_stop = (
            character_section_stop
            + ambiguity_range_count * AMBIGUITY_RANGE_RECORD.size
        )
        expected_size = (
            ambiguity_section_stop
            + bracket_record_count * BRACKET_RECORD.size
        )
        if (
            magic != ARTIFACT_MAGIC
            or version != ARTIFACT_FORMAT_VERSION
            or not 1 <= q <= MAXIMUM_MODULUS
            or frame_count == 0
            or denominator != SOURCE_SAMPLE_DENOMINATOR
            or step != SOURCE_SAMPLE_NUMERATOR
            or stop_t_numerator < first_t_numerator
            or (stop_t_numerator - first_t_numerator) % step
            or leaf_count == 0
            or internal_sign_changes + cross_boundary_sign_changes
            != sign_change_lower_bound
            or primitive_count
            > (
                maximum_bytes - ARTIFACT_HEADER.size
            ) // CHARACTER_RECORD.size
            or ambiguity_range_count
            > maximum_bytes // AMBIGUITY_RANGE_RECORD.size
            or bracket_record_count
            > maximum_bytes // BRACKET_RECORD.size
            or expected_size != status.st_size
        ):
            _fail("compact-state header identity or arithmetic differs")
        identities = primitive_frequency_records_bulk(q)
        if (
            len(identities) != primitive_count
            or raw_roster_digest.hex() != _roster_digest(identities)
        ):
            _fail("compact-state canonical primitive roster differs")
        sample_count = (stop_t_numerator - first_t_numerator) // step
        states: list[dict[str, Any]] = []
        sparse_counts: list[tuple[int, int]] = []
        expected_ambiguity_offset = character_section_stop
        expected_bracket_offset = ambiguity_section_stop
        for ordinal, identity in enumerate(identities):
            raw = _read_exact(
                source,
                CHARACTER_RECORD.size,
                label="compact-state character record",
            )
            digest.update(raw)
            if any(raw[-6:]):
                _fail("compact-state character record has nonzero padding")
            (
                first,
                last,
                leading,
                trailing,
                ambiguity,
                positive,
                negative,
                brackets,
                ambiguity_offset,
                character_ambiguity_ranges,
                bracket_offset,
                character_bracket_records,
                first_sign,
                last_sign,
            ) = CHARACTER_RECORD.unpack(raw)
            if (
                ambiguity_offset != expected_ambiguity_offset
                or bracket_offset != expected_bracket_offset
                or character_bracket_records != brackets
                or character_ambiguity_ranges > ambiguity
            ):
                _fail(
                    "compact-state sparse offsets, lengths, or counts differ"
                )
            expected_ambiguity_offset += (
                character_ambiguity_ranges
                * AMBIGUITY_RANGE_RECORD.size
            )
            expected_bracket_offset += (
                character_bracket_records * BRACKET_RECORD.size
            )
            if (
                expected_ambiguity_offset > ambiguity_section_stop
                or expected_bracket_offset > expected_size
            ):
                _fail("compact-state sparse section coverage overflows")
            first_value = None if first == ABSENT_NUMERATOR else first
            last_value = None if last == ABSENT_NUMERATOR else last
            if (first_value is None) != (last_value is None):
                _fail("compact-state absent boundary sentinels differ")
            states.append(
                {
                    "conrey_number": identity["conrey_number"],
                    "primitive_ordinal": ordinal,
                    "parity": identity["parity"],
                    "sample_count": sample_count,
                    "first_determinate_numerator": first_value,
                    "first_sign": first_sign,
                    "last_determinate_numerator": last_value,
                    "last_sign": last_sign,
                    "leading_ambiguity_count": leading,
                    "trailing_ambiguity_count": trailing,
                    "ambiguity_count": ambiguity,
                    "positive_count": positive,
                    "negative_count": negative,
                    "bracket_count": brackets,
                    "multiplicity_lower_bound_sum": brackets,
                    "ambiguity_ranges": [],
                    "bracket_records": [],
                }
            )
            sparse_counts.append(
                (character_ambiguity_ranges, character_bracket_records)
            )
        if (
            expected_ambiguity_offset != ambiguity_section_stop
            or expected_bracket_offset != expected_size
        ):
            _fail("compact-state sparse sections contain a gap or overlap")
        observed_ambiguity_ranges = 0
        for state, (range_count, _bracket_count) in zip(
            states, sparse_counts
        ):
            ranges = state["ambiguity_ranges"]
            for _index in range(range_count):
                raw = _read_exact(
                    source,
                    AMBIGUITY_RANGE_RECORD.size,
                    label="compact-state ambiguity range",
                )
                digest.update(raw)
                range_first, range_stop = AMBIGUITY_RANGE_RECORD.unpack(raw)
                ranges.append(
                    {
                        "first_t_numerator": range_first,
                        "stop_t_numerator": range_stop,
                    }
                )
                observed_ambiguity_ranges += 1
        if observed_ambiguity_ranges != ambiguity_range_count:
            _fail("compact-state ambiguity range section count differs")
        observed_brackets = 0
        for state, (_range_count, bracket_count) in zip(
            states, sparse_counts
        ):
            bracket_records = state["bracket_records"]
            for _index in range(bracket_count):
                raw = _read_exact(
                    source,
                    BRACKET_RECORD.size,
                    label="compact-state bracket record",
                )
                digest.update(raw)
                if any(raw[18:24]):
                    _fail("compact-state bracket record has nonzero padding")
                (
                    lower,
                    upper,
                    lower_sign,
                    upper_sign,
                    intervening,
                ) = BRACKET_RECORD.unpack(raw)
                bracket_records.append(
                    {
                        "lower_t_numerator": lower,
                        "upper_t_numerator": upper,
                        "lower_sign": lower_sign,
                        "upper_sign": upper_sign,
                        "intervening_ambiguity_count": intervening,
                    }
                )
                observed_brackets += 1
        if observed_brackets != bracket_record_count:
            _fail("compact-state bracket section count differs")
        if source.read(1):
            _fail("compact-state binary has trailing bytes")
    final_status = path.lstat()
    if (
        final_status.st_dev != status.st_dev
        or final_status.st_ino != status.st_ino
        or final_status.st_size != status.st_size
    ):
        _fail("compact-state binary changed during replay")
    artifact_sha256 = digest.hexdigest()
    if (
        expected_record is not None
        and artifact_sha256 != expected_record["artifact_sha256"]
    ):
        _fail("compact-state binary digest differs from checkpoint")
    body = _state_body(
        q=q,
        primitive_count=primitive_count,
        frame_count=frame_count,
        first_t_numerator=first_t_numerator,
        stop_t_numerator=stop_t_numerator,
        leaf_count=leaf_count,
        leaf_commitment=int.from_bytes(raw_commitment, "big"),
        internal_sign_changes=internal_sign_changes,
        cross_boundary_sign_changes=cross_boundary_sign_changes,
        sign_change_lower_bound=sign_change_lower_bound,
        ambiguity_samples=ambiguity_samples,
        states=states,
    )
    state = dict(body)
    state["state_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    validate_compact_state_summary(state)
    record = _artifact_record(
        path=path,
        artifact_sha256=artifact_sha256,
        size_bytes=status.st_size,
        state=state,
    )
    _validate_record(record)
    if expected_record is not None and dict(expected_record) != record:
        _fail("compact-state binary metadata differs from checkpoint")
    return state


__all__ = [
    "ABSENT_NUMERATOR",
    "AMBIGUITY_RANGE_RECORD",
    "ARTIFACT_FORMAT_VERSION",
    "ARTIFACT_HEADER",
    "ARTIFACT_MAGIC",
    "ARTIFACT_SCHEMA",
    "BRACKET_RECORD",
    "CHARACTER_RECORD",
    "DEFAULT_MAXIMUM_ARTIFACT_BYTES",
    "DirichletCompactStateBinaryError",
    "MAXIMUM_ARTIFACT_BYTES",
    "MAXIMUM_MODULUS",
    "read_compact_state_binary",
    "write_compact_state_binary",
]
