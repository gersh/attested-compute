# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Source-streaming compact Dirichlet sign state.

``TGDCSB03`` is the production-oriented successor to ``TGDCSB02``.  It does
not retain a 104-byte index or an exact bracket coordinate for every
character.  Instead, each fixed-q artifact contains, in canonical primitive
ordinal order:

* one fixed-width bit-packed record per character;
* a transition count whose width is derived from the artifact's exact sample
  span;
* determinate/first-sign/last-sign/sparse flags; and
* only maximal ambiguity ranges as sparse production records.

The fourth flag is a page-local rank/select bitmap.  A popcount before an
ordinal selects its sparse row without any per-character offset.  Pages have
at most ``PAGE_CHARACTERS`` records, so replay and cross-lane merge use memory
bounded independently of the source roster size.

Exact bracket coordinates are available only in explicit debug mode.  Debug
artifacts are rejected by every source-admission helper because their
32-byte records recreate the petabyte-scale storage problem that this format
is intended to remove.

The compact arithmetic is not a zero-completeness proof.  In particular, a
q-level equality between the transition total and a Turing total is useful
only with all three independent semantic premises mirrored by
``SparkInterval.Dirichlet.AggregateTuringClosure``:

1. each character's transition count is a multiplicity-preserving lower
   bound for that character's zeros;
2. each Turing count is an analytic upper bound for the same character; and
3. both finite sums range over the same complete, duplicate-free canonical
   primitive-character roster.

This module records those obligations and always leaves source admission
false.  It does not claim source truth, interval usefulness, refinement,
Turing realization, trusted execution, GRH, or discharge of Platt's theorem.
The q=1 zeta case is separate.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import itertools
import math
import os
from pathlib import Path
import stat
import struct
import tempfile
from typing import (
    Any,
    BinaryIO,
    Generator,
    Iterable,
    Iterator,
    Mapping,
    NoReturn,
    Sequence,
)

from tg_verifier.dirichlet_campaign import (
    _smallest_prime_factors,
    primitive_character_count,
)
from tg_verifier.dirichlet_lattice_cache import canonical_json_bytes
from tg_verifier.dirichlet_lattice_stage import maximum_t_index
from tg_verifier.dirichlet_root_number_stage import (
    primitive_frequency_records_bulk,
)
from tg_verifier.dirichlet_source_supervisor import PINNED_SOURCE_LANE_TOTALS
from tg_verifier.dirichlet_stream_zero_consumer import (
    MAX_EVENT_COUNT,
    SOURCE_SAMPLE_DENOMINATOR,
    SOURCE_SAMPLE_NUMERATOR,
    _ROLLING_BASE,
    _ROLLING_MODULUS,
    combine_associative_event_commitments,
)


AUTHOR = "Gershon Bialer"
ARTIFACT_SCHEMA = (
    "sparkinterval.tg.dirichlet_stream_consumer.compact_state_binary.v3"
)
ARTIFACT_MAGIC = b"TGDCSB03"
ARTIFACT_FORMAT_VERSION = 3
PRODUCTION_FLAG = 1
DEBUG_BRACKET_FLAG = 2
PAGE_CHARACTERS = 4_096
MAXIMUM_LANES = 8
DEFAULT_MAXIMUM_ARTIFACT_BYTES = 1024 * 1024 * 1024
MAXIMUM_ARTIFACT_BYTES = 4 * 1024 * 1024 * 1024
DEFAULT_MAXIMUM_PAGE_PAYLOAD_BYTES = 64 * 1024 * 1024
MAXIMUM_PAGE_PAYLOAD_BYTES = 256 * 1024 * 1024
MAXIMUM_MODULUS = 400_000

# magic; version/mode/q/page-size/count-width/reserved; primitive/frame/grid;
# page/transition/ambiguity/range/debug-bracket/leaf counts; leaf value,
# complete-roster digest and upstream source binding.
ARTIFACT_HEADER = struct.Struct("<8s6I10Q32s32s32s")

# ordinal start; character/sparse counts; payload bytes and page totals.
PAGE_PREFIX = struct.Struct("<QIIQQQQQ")
PAGE_HEADER = struct.Struct("<QIIQQQQQ32s")

# One row is present for every set sparse flag.  In production bracket_count
# must be zero.  Exact maximal ranges and optional debug brackets use the
# already reviewed v2 fixed records.
SPARSE_ROW_HEADER = struct.Struct("<II")
AMBIGUITY_RANGE_RECORD = struct.Struct("<QQ")
DEBUG_BRACKET_RECORD = struct.Struct("<QQbb6xQ")

EXCEPTION_MAGIC = b"TGDCSA03"
EXCEPTION_FORMAT_VERSION = 3
# magic/version/q; roster/grid/range-character/range/ambiguity counts; roster,
# source-state and MMR roots.
EXCEPTION_HEADER = struct.Struct("<8sII6Q32s32s32s")
EXCEPTION_CHARACTER_HEADER = struct.Struct("<QQ")

PAGE_DOMAIN = b"sparkinterval/tg/dirichlet-compact-state-v3/page\0"
LEAF_DOMAIN = b"sparkinterval/tg/dirichlet-compact-state-v3/leaf\0"
SOURCE_MERGE_DOMAIN = (
    b"sparkinterval/tg/dirichlet-compact-state-v3/source-merge\0"
)
EXCEPTION_LEAF_DOMAIN = (
    b"sparkinterval/tg/dirichlet-compact-state-v3/exception-leaf\0"
)
EXCEPTION_NODE_DOMAIN = (
    b"sparkinterval/tg/dirichlet-compact-state-v3/exception-node\0"
)
EXCEPTION_ROOT_DOMAIN = (
    b"sparkinterval/tg/dirichlet-compact-state-v3/exception-root\0"
)

SOURCE_Q_START = 10_001
SOURCE_Q_STOP = 400_000
SOURCE_CHARACTER_COUNT = 29_547_446_729
SOURCE_SAMPLE_COUNT = 191_701_043_433_012


class DirichletCompactStateV3Error(RuntimeError):
    """A v3 state, artifact, merge, or source projection failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletCompactStateV3Error(message)


def _uint(name: str, value: object, *, maximum: int = MAX_EVENT_COUNT) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= maximum
    ):
        _fail(f"{name} is outside its fixed unsigned bound")
    return value


def _positive_bound(name: str, value: object, *, maximum: int) -> int:
    result = _uint(name, value, maximum=maximum)
    if result == 0:
        _fail(f"{name} must be positive")
    return result


def _digest(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{name} must be a lowercase SHA-256 digest")
    return value


def _read_exact(source: BinaryIO, count: int, *, label: str) -> bytes:
    raw = source.read(count)
    if len(raw) != count:
        _fail(f"truncated {label}")
    return raw


def transition_count_width(sample_count: int) -> int:
    """Canonical bits needed for every count in ``0..sample_count-1``."""

    sample_count = _positive_bound(
        "sample count", sample_count, maximum=MAX_EVENT_COUNT
    )
    return max(1, (sample_count - 1).bit_length())


def _record_width(sample_count: int) -> int:
    return 4 + transition_count_width(sample_count)


def _packed_bytes(record_count: int, record_width: int) -> int:
    return (record_count * record_width + 7) // 8


def _set_bits(
    output: bytearray, bit_offset: int, width: int, value: int
) -> None:
    if width <= 0 or value < 0 or value >= 1 << width:
        _fail("packed state value is outside its canonical bit width")
    for bit in range(width):
        if value & (1 << bit):
            absolute = bit_offset + bit
            output[absolute // 8] |= 1 << (absolute % 8)


def _get_bits(raw: bytes, bit_offset: int, width: int) -> int:
    value = 0
    for bit in range(width):
        absolute = bit_offset + bit
        value |= ((raw[absolute // 8] >> (absolute % 8)) & 1) << bit
    return value


def _check_padding(raw: bytes, used_bits: int, *, label: str) -> None:
    if used_bits < 0 or used_bits > 8 * len(raw):
        _fail(f"{label} bit accounting differs")
    if used_bits % 8 and raw and raw[-1] >> (used_bits % 8):
        _fail(f"{label} has nonzero unused padding bits")


def _roster_digest(identities: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(canonical_json_bytes(list(identities))).hexdigest()


def complete_primitive_roster_sha256_v3(q: int) -> str:
    """Return the canonical v3 roster digest for one supported modulus."""

    q = _positive_bound("q", q, maximum=MAXIMUM_MODULUS)
    identities = primitive_frequency_records_bulk(q)
    if not identities:
        _fail("v3 artifacts require a nonempty primitive roster")
    return _roster_digest(identities)


def _state_span(
    *,
    first_t_numerator: int,
    stop_t_numerator: int,
) -> tuple[int, int, int]:
    first = _uint("first t numerator", first_t_numerator)
    stop = _uint("stop t numerator", stop_t_numerator)
    if (
        stop <= first
        or (stop - first) % SOURCE_SAMPLE_NUMERATOR
    ):
        _fail("v3 state is not a nonempty exact 5/64 grid")
    samples = (stop - first) // SOURCE_SAMPLE_NUMERATOR
    return first, stop, samples


@dataclass(frozen=True)
class V3Header:
    mode_flags: int
    q: int
    page_characters: int
    count_width: int
    primitive_count: int
    frame_count: int
    first_t_numerator: int
    stop_t_numerator: int
    page_count: int
    transition_count: int
    ambiguity_sample_count: int
    ambiguity_range_count: int
    debug_bracket_count: int
    leaf_count: int
    leaf_commitment: int
    roster_sha256: str
    source_binding_sha256: str

    @property
    def sample_count(self) -> int:
        return (
            self.stop_t_numerator - self.first_t_numerator
        ) // SOURCE_SAMPLE_NUMERATOR

    @property
    def debug(self) -> bool:
        return bool(self.mode_flags & DEBUG_BRACKET_FLAG)


@dataclass(frozen=True)
class _ReplayCompletion:
    record: dict[str, Any]
    header: V3Header


def _pack_header(header: V3Header) -> bytes:
    return ARTIFACT_HEADER.pack(
        ARTIFACT_MAGIC,
        ARTIFACT_FORMAT_VERSION,
        header.mode_flags,
        header.q,
        header.page_characters,
        header.count_width,
        0,
        header.primitive_count,
        header.frame_count,
        header.first_t_numerator,
        header.stop_t_numerator,
        header.page_count,
        header.transition_count,
        header.ambiguity_sample_count,
        header.ambiguity_range_count,
        header.debug_bracket_count,
        header.leaf_count,
        header.leaf_commitment.to_bytes(32, "big"),
        bytes.fromhex(header.roster_sha256),
        bytes.fromhex(header.source_binding_sha256),
    )


def _unpack_header(raw: bytes) -> V3Header:
    if len(raw) != ARTIFACT_HEADER.size:
        _fail("truncated v3 header")
    (
        magic,
        version,
        mode_flags,
        q,
        page_characters,
        count_width,
        reserved,
        primitive_count,
        frame_count,
        first_t_numerator,
        stop_t_numerator,
        page_count,
        transition_count,
        ambiguity_sample_count,
        ambiguity_range_count,
        debug_bracket_count,
        leaf_count,
        raw_commitment,
        raw_roster,
        raw_source,
    ) = ARTIFACT_HEADER.unpack(raw)
    first, stop, samples = _state_span(
        first_t_numerator=first_t_numerator,
        stop_t_numerator=stop_t_numerator,
    )
    expected_pages = (primitive_count + PAGE_CHARACTERS - 1) // PAGE_CHARACTERS
    if (
        magic != ARTIFACT_MAGIC
        or version != ARTIFACT_FORMAT_VERSION
        or mode_flags not in {
            PRODUCTION_FLAG,
            PRODUCTION_FLAG | DEBUG_BRACKET_FLAG,
        }
        or not 1 <= q <= MAXIMUM_MODULUS
        or page_characters != PAGE_CHARACTERS
        or count_width != transition_count_width(samples)
        or reserved != 0
        or primitive_count == 0
        or frame_count == 0
        or page_count != expected_pages
        or transition_count
        > primitive_count * max(0, samples - 1)
        or ambiguity_sample_count > primitive_count * samples
        or leaf_count == 0
        or int.from_bytes(raw_commitment, "big") >= _ROLLING_MODULUS
        or (
            not mode_flags & DEBUG_BRACKET_FLAG
            and debug_bracket_count != 0
        )
    ):
        _fail("v3 header identity, flags, or arithmetic differs")
    return V3Header(
        mode_flags=mode_flags,
        q=q,
        page_characters=page_characters,
        count_width=count_width,
        primitive_count=primitive_count,
        frame_count=frame_count,
        first_t_numerator=first,
        stop_t_numerator=stop,
        page_count=page_count,
        transition_count=transition_count,
        ambiguity_sample_count=ambiguity_sample_count,
        ambiguity_range_count=ambiguity_range_count,
        debug_bracket_count=debug_bracket_count,
        leaf_count=leaf_count,
        leaf_commitment=int.from_bytes(raw_commitment, "big"),
        roster_sha256=raw_roster.hex(),
        source_binding_sha256=raw_source.hex(),
    )


def inspect_compact_state_v3(
    path: Path,
    *,
    maximum_bytes: int = DEFAULT_MAXIMUM_ARTIFACT_BYTES,
) -> V3Header:
    """Read the bounded header without claiming that page replay succeeded."""

    maximum_bytes = _positive_bound(
        "maximum artifact bytes",
        maximum_bytes,
        maximum=MAXIMUM_ARTIFACT_BYTES,
    )
    try:
        status = path.lstat()
    except OSError as error:
        raise DirichletCompactStateV3Error(
            f"cannot stat v3 artifact: {error}"
        ) from error
    if (
        path.is_symlink()
        or not stat.S_ISREG(status.st_mode)
        or not ARTIFACT_HEADER.size <= status.st_size <= maximum_bytes
    ):
        _fail("v3 artifact is not one bounded regular file")
    with path.open("rb") as source:
        header = _unpack_header(
            _read_exact(source, ARTIFACT_HEADER.size, label="v3 header")
        )
    if primitive_character_count(header.q) != header.primitive_count:
        _fail("v3 primitive-character count differs from the source formula")
    return header


def _normalize_range(
    value: object,
    *,
    span_first: int,
    span_stop: int,
    previous_stop: int | None,
) -> tuple[dict[str, int], int]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"first_t_numerator", "stop_t_numerator"}
    ):
        _fail("v3 ambiguity range fields differ")
    first = _uint("ambiguity range first", value.get("first_t_numerator"))
    stop = _uint("ambiguity range stop", value.get("stop_t_numerator"))
    if (
        not span_first <= first < stop <= span_stop
        or (first - span_first) % SOURCE_SAMPLE_NUMERATOR
        or (stop - span_first) % SOURCE_SAMPLE_NUMERATOR
        or (
            previous_stop is not None
            and first <= previous_stop
        )
    ):
        _fail("v3 ambiguity ranges are not ordered maximal grid ranges")
    return {
        "first_t_numerator": first,
        "stop_t_numerator": stop,
    }, (stop - first) // SOURCE_SAMPLE_NUMERATOR


def _normalize_debug_bracket(
    value: object,
    *,
    span_first: int,
    span_stop: int,
    ranges: Sequence[Mapping[str, int]],
    previous_upper: int | None,
    previous_upper_sign: int | None,
) -> dict[str, int]:
    fields = {
        "lower_t_numerator",
        "upper_t_numerator",
        "lower_sign",
        "upper_sign",
        "intervening_ambiguity_count",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        _fail("v3 debug bracket fields differ")
    lower = _uint("debug bracket lower", value.get("lower_t_numerator"))
    upper = _uint("debug bracket upper", value.get("upper_t_numerator"))
    intervening = _uint(
        "debug bracket ambiguity",
        value.get("intervening_ambiguity_count"),
    )
    lower_sign = value.get("lower_sign")
    upper_sign = value.get("upper_sign")
    if (
        lower_sign not in (-1, 1)
        or upper_sign not in (-1, 1)
        or lower_sign == upper_sign
        or not span_first <= lower < upper < span_stop
        or (lower - span_first) % SOURCE_SAMPLE_NUMERATOR
        or (upper - span_first) % SOURCE_SAMPLE_NUMERATOR
        or intervening
        != (upper - lower) // SOURCE_SAMPLE_NUMERATOR - 1
        or (previous_upper is not None and lower < previous_upper)
        or (
            previous_upper_sign is not None
            and lower_sign != previous_upper_sign
        )
    ):
        _fail("v3 debug bracket order, signs, or grid differs")
    for endpoint in (lower, upper):
        if any(
            row["first_t_numerator"] <= endpoint < row["stop_t_numerator"]
            for row in ranges
        ):
            _fail("v3 debug bracket endpoint is ambiguous")
    if intervening and not any(
        row["first_t_numerator"] == lower + SOURCE_SAMPLE_NUMERATOR
        and row["stop_t_numerator"] == upper
        for row in ranges
    ):
        _fail("v3 debug bracket intervening ambiguity differs")
    return {
        "lower_t_numerator": lower,
        "upper_t_numerator": upper,
        "lower_sign": int(lower_sign),
        "upper_sign": int(upper_sign),
        "intervening_ambiguity_count": intervening,
    }


def _normalize_state(
    value: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    span_first: int,
    span_stop: int,
    sample_count: int,
    debug: bool,
) -> dict[str, Any]:
    """Normalize either the v3 production state or a full v2 character row."""

    if not isinstance(value, Mapping):
        _fail("v3 character state is not an object")
    ordinal = _uint("primitive ordinal", value.get("primitive_ordinal"))
    conrey = _uint("Conrey number", value.get("conrey_number"))
    parity = value.get("parity")
    if (
        ordinal != identity["primitive_ordinal"]
        or conrey != identity["conrey_number"]
        or parity != identity["parity"]
    ):
        _fail("v3 character identity differs from the canonical roster")
    if value.get("sample_count") != sample_count:
        _fail("v3 character sample coverage differs")
    raw_ranges = value.get("ambiguity_ranges")
    if not isinstance(raw_ranges, Sequence):
        _fail("v3 character ambiguity ranges are absent")
    ranges: list[dict[str, int]] = []
    ambiguity_count = 0
    previous_stop: int | None = None
    for raw_range in raw_ranges:
        row, count = _normalize_range(
            raw_range,
            span_first=span_first,
            span_stop=span_stop,
            previous_stop=previous_stop,
        )
        ranges.append(row)
        ambiguity_count += count
        previous_stop = row["stop_t_numerator"]
    if ambiguity_count > sample_count:
        _fail("v3 character ambiguity total exceeds its grid")
    if value.get("ambiguity_count") not in (None, ambiguity_count):
        _fail("v3 character ambiguity counter differs from maximal ranges")
    determinate_count = sample_count - ambiguity_count
    has_determinate = determinate_count != 0
    first = value.get("first_determinate_numerator")
    last = value.get("last_determinate_numerator")
    first_sign = value.get("first_sign")
    last_sign = value.get("last_sign")
    leading = (
        (ranges[0]["stop_t_numerator"] - span_first)
        // SOURCE_SAMPLE_NUMERATOR
        if ranges and ranges[0]["first_t_numerator"] == span_first
        else 0
    )
    trailing = (
        (span_stop - ranges[-1]["first_t_numerator"])
        // SOURCE_SAMPLE_NUMERATOR
        if ranges and ranges[-1]["stop_t_numerator"] == span_stop
        else 0
    )
    derived_first = (
        None
        if not has_determinate
        else span_first + leading * SOURCE_SAMPLE_NUMERATOR
    )
    derived_last = (
        None
        if not has_determinate
        else span_stop
        - (trailing + 1) * SOURCE_SAMPLE_NUMERATOR
    )
    if (
        first != derived_first
        or last != derived_last
        or value.get("leading_ambiguity_count") not in (None, leading)
        or value.get("trailing_ambiguity_count") not in (None, trailing)
    ):
        _fail("v3 determinate ordinates are not derived from maximal ranges")
    if has_determinate:
        if first_sign not in (-1, 1) or last_sign not in (-1, 1):
            _fail("v3 determinate boundary signs differ")
    elif (
        first_sign != 0
        or last_sign != 0
        or len(ranges) != 1
        or ranges[0]["first_t_numerator"] != span_first
        or ranges[0]["stop_t_numerator"] != span_stop
    ):
        _fail("v3 all-ambiguous character state differs")
    transition = value.get(
        "internal_sign_change_count",
        value.get("bracket_count"),
    )
    transition = _uint("character transition count", transition)
    if (
        transition > max(0, determinate_count - 1)
        or (
            has_determinate
            and (transition & 1) != int(first_sign != last_sign)
        )
        or (not has_determinate and transition != 0)
    ):
        _fail("v3 transition count, parity, or determinate span differs")
    raw_brackets = value.get("bracket_records", [])
    if not isinstance(raw_brackets, Sequence):
        _fail("v3 debug bracket rows are malformed")
    brackets: list[dict[str, int]] = []
    if debug:
        previous_upper: int | None = None
        previous_upper_sign: int | None = None
        for raw_bracket in raw_brackets:
            bracket = _normalize_debug_bracket(
                raw_bracket,
                span_first=span_first,
                span_stop=span_stop,
                ranges=ranges,
                previous_upper=previous_upper,
                previous_upper_sign=previous_upper_sign,
            )
            brackets.append(bracket)
            previous_upper = bracket["upper_t_numerator"]
            previous_upper_sign = bracket["upper_sign"]
        if len(brackets) != transition:
            _fail("v3 debug brackets do not realize the transition count")
        if brackets:
            if (
                brackets[0]["lower_sign"] != first_sign
                or brackets[-1]["upper_sign"] != last_sign
            ):
                _fail("v3 debug bracket endpoint signs differ")
    return {
        "conrey_number": conrey,
        "primitive_ordinal": ordinal,
        "parity": parity,
        "sample_count": sample_count,
        "first_determinate_numerator": derived_first,
        "first_sign": first_sign,
        "last_determinate_numerator": derived_last,
        "last_sign": last_sign,
        "leading_ambiguity_count": leading,
        "trailing_ambiguity_count": trailing,
        "ambiguity_count": ambiguity_count,
        "internal_sign_change_count": transition,
        "ambiguity_ranges": ranges,
        "bracket_records": brackets,
    }


def _state_from_codes(
    identity: Mapping[str, Any],
    codes: Iterator[int],
    *,
    span_first: int,
    sample_count: int,
) -> dict[str, Any]:
    first: int | None = None
    first_sign = 0
    last: int | None = None
    last_sign = 0
    transitions = 0
    ambiguity_count = 0
    ranges: list[dict[str, int]] = []
    open_range: int | None = None
    for sample_index in range(sample_count):
        try:
            code = next(codes)
        except StopIteration:
            _fail("direct v3 sign producer ended inside one character")
        if isinstance(code, bool) or not isinstance(code, int) or code not in {
            0,
            1,
            2,
        }:
            _fail("direct v3 sign producer emitted a reserved code")
        numerator = (
            span_first + sample_index * SOURCE_SAMPLE_NUMERATOR
        )
        if code == 0:
            ambiguity_count += 1
            if open_range is None:
                open_range = numerator
            continue
        if open_range is not None:
            ranges.append(
                {
                    "first_t_numerator": open_range,
                    "stop_t_numerator": numerator,
                }
            )
            open_range = None
        sign = -1 if code == 1 else 1
        if first is None:
            first = numerator
            first_sign = sign
        elif last_sign != sign:
            transitions += 1
        last = numerator
        last_sign = sign
    span_stop = span_first + sample_count * SOURCE_SAMPLE_NUMERATOR
    if open_range is not None:
        ranges.append(
            {
                "first_t_numerator": open_range,
                "stop_t_numerator": span_stop,
            }
        )
    leading = (
        (ranges[0]["stop_t_numerator"] - span_first)
        // SOURCE_SAMPLE_NUMERATOR
        if ranges and ranges[0]["first_t_numerator"] == span_first
        else 0
    )
    trailing = (
        (span_stop - ranges[-1]["first_t_numerator"])
        // SOURCE_SAMPLE_NUMERATOR
        if ranges and ranges[-1]["stop_t_numerator"] == span_stop
        else 0
    )
    return {
        "conrey_number": identity["conrey_number"],
        "primitive_ordinal": identity["primitive_ordinal"],
        "parity": identity["parity"],
        "sample_count": sample_count,
        "first_determinate_numerator": first,
        "first_sign": first_sign,
        "last_determinate_numerator": last,
        "last_sign": last_sign,
        "leading_ambiguity_count": leading,
        "trailing_ambiguity_count": trailing,
        "ambiguity_count": ambiguity_count,
        "internal_sign_change_count": transitions,
        "ambiguity_ranges": ranges,
        "bracket_records": [],
    }


def character_states_from_flat_sign_codes(
    *,
    q: int,
    first_t_numerator: int,
    stop_t_numerator: int,
    code_chunks: Iterable[Iterable[int]],
) -> Iterator[dict[str, Any]]:
    """Turn direct character-major producer chunks into v3 states.

    The iterator never materializes a sign artifact or a complete character
    row.  It consumes exactly one code at a time, retains only the current
    character's maximal ambiguity ranges, and rejects both early EOF and
    trailing codes.
    """

    first, _stop, samples = _state_span(
        first_t_numerator=first_t_numerator,
        stop_t_numerator=stop_t_numerator,
    )
    identities = primitive_frequency_records_bulk(q)
    flat = itertools.chain.from_iterable(code_chunks)
    for identity in identities:
        yield _state_from_codes(
            identity,
            flat,
            span_first=first,
            sample_count=samples,
        )
    try:
        next(flat)
    except StopIteration:
        return
    _fail("direct v3 sign producer has trailing codes")


def _page_bytes(
    states: Sequence[Mapping[str, Any]],
    *,
    ordinal_start: int,
    sample_count: int,
    count_width: int,
    debug: bool,
    maximum_page_payload_bytes: int,
) -> tuple[bytes, dict[str, int]]:
    record_width = 4 + count_width
    packed = bytearray(_packed_bytes(len(states), record_width))
    sparse = bytearray()
    transitions = 0
    ambiguity_samples = 0
    ambiguity_ranges = 0
    debug_brackets = 0
    sparse_characters = 0
    for local, state in enumerate(states):
        has_determinate = state["first_determinate_numerator"] is not None
        ranges = state["ambiguity_ranges"]
        brackets = state["bracket_records"] if debug else []
        has_sparse = bool(ranges or brackets)
        transition = state["internal_sign_change_count"]
        flags = (
            int(has_determinate)
            | (int(state["first_sign"] > 0) << 1)
            | (int(state["last_sign"] > 0) << 2)
            | (int(has_sparse) << 3)
        )
        value = flags | (transition << 4)
        _set_bits(
            packed,
            local * record_width,
            record_width,
            value,
        )
        transitions += transition
        ambiguity_samples += state["ambiguity_count"]
        ambiguity_ranges += len(ranges)
        debug_brackets += len(brackets)
        if has_sparse:
            sparse_characters += 1
            if len(ranges) > (1 << 32) - 1 or len(brackets) > (1 << 32) - 1:
                _fail("v3 sparse row count exceeds uint32")
            sparse.extend(
                SPARSE_ROW_HEADER.pack(len(ranges), len(brackets))
            )
            for row in ranges:
                sparse.extend(
                    AMBIGUITY_RANGE_RECORD.pack(
                        row["first_t_numerator"],
                        row["stop_t_numerator"],
                    )
                )
            for bracket in brackets:
                sparse.extend(
                    DEBUG_BRACKET_RECORD.pack(
                        bracket["lower_t_numerator"],
                        bracket["upper_t_numerator"],
                        bracket["lower_sign"],
                        bracket["upper_sign"],
                        bracket["intervening_ambiguity_count"],
                    )
                )
    _check_padding(
        bytes(packed),
        len(states) * record_width,
        label="v3 packed page",
    )
    payload = bytes(packed + sparse)
    if len(payload) > maximum_page_payload_bytes:
        _fail("v3 page exceeds its externally supplied payload bound")
    values = {
        "ordinal_start": ordinal_start,
        "character_count": len(states),
        "sparse_character_count": sparse_characters,
        "payload_bytes": len(payload),
        "transition_count": transitions,
        "ambiguity_sample_count": ambiguity_samples,
        "ambiguity_range_count": ambiguity_ranges,
        "debug_bracket_count": debug_brackets,
    }
    prefix = PAGE_PREFIX.pack(
        values["ordinal_start"],
        values["character_count"],
        values["sparse_character_count"],
        values["payload_bytes"],
        values["transition_count"],
        values["ambiguity_sample_count"],
        values["ambiguity_range_count"],
        values["debug_bracket_count"],
    )
    page_sha256 = hashlib.sha256(PAGE_DOMAIN + prefix + payload).digest()
    header = PAGE_HEADER.pack(
        values["ordinal_start"],
        values["character_count"],
        values["sparse_character_count"],
        values["payload_bytes"],
        values["transition_count"],
        values["ambiguity_sample_count"],
        values["ambiguity_range_count"],
        values["debug_bracket_count"],
        page_sha256,
    )
    return header + payload, values


def _artifact_record(
    *,
    path: Path,
    artifact_sha256: str,
    size_bytes: int,
    header: V3Header,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": ARTIFACT_SCHEMA,
        "schema_version": 3,
        "classification": (
            "source_streaming_dense_counts_and_sparse_ambiguities_"
            "not_zero_or_turing_evidence"
        ),
        "path": str(path.resolve()),
        "artifact_sha256": artifact_sha256,
        "size_bytes": size_bytes,
        "q": header.q,
        "primitive_character_count": header.primitive_count,
        "frame_count": header.frame_count,
        "first_t_numerator": header.first_t_numerator,
        "stop_t_numerator": header.stop_t_numerator,
        "sample_count_per_character": header.sample_count,
        "transition_count_width_bits": header.count_width,
        "transition_count": header.transition_count,
        "ambiguity_sample_count": header.ambiguity_sample_count,
        "ambiguity_range_count": header.ambiguity_range_count,
        "debug_bracket_count": header.debug_bracket_count,
        "page_count": header.page_count,
        "page_characters": PAGE_CHARACTERS,
        "complete_primitive_roster_sha256": header.roster_sha256,
        "upstream_source_binding_sha256": header.source_binding_sha256,
        "rank_select_sparse_rows": True,
        "first_last_ordinates_derived_from_span_and_maximal_ranges": True,
        "dense_transition_counts": True,
        "exact_maximal_ambiguity_ranges_retained": True,
        "exact_bracket_coordinates_retained_for_debug_only": header.debug,
        "source_scale_layout": not header.debug,
        "producer_fused_with_arithmetic": False,
        "pointwise_transition_lower_bounds_proved": False,
        "exact_turing_totals_realized": False,
        "complete_roster_equivalence_realized": False,
        "aggregate_turing_closure_admitted": False,
        "source_scale_storage_admitted": False,
        "external_atom_discharged": False,
    }
    result = dict(body)
    result["record_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def write_compact_state_v3(
    path: Path,
    *,
    q: int,
    frame_count: int,
    first_t_numerator: int,
    stop_t_numerator: int,
    states: Iterable[Mapping[str, Any]],
    source_binding_sha256: str,
    debug_brackets: bool = False,
    leaf_count: int | None = None,
    leaf_commitment: int | None = None,
    expected_roster_sha256: str | None = None,
    maximum_bytes: int = DEFAULT_MAXIMUM_ARTIFACT_BYTES,
    maximum_page_payload_bytes: int = DEFAULT_MAXIMUM_PAGE_PAYLOAD_BYTES,
) -> dict[str, Any]:
    """Atomically stream one fixed-q state to canonical v3 pages."""

    q = _positive_bound("q", q, maximum=MAXIMUM_MODULUS)
    frame_count = _positive_bound(
        "frame count", frame_count, maximum=MAX_EVENT_COUNT
    )
    first, stop, sample_count = _state_span(
        first_t_numerator=first_t_numerator,
        stop_t_numerator=stop_t_numerator,
    )
    source_binding_sha256 = _digest(
        "upstream source binding", source_binding_sha256
    )
    maximum_bytes = _positive_bound(
        "maximum artifact bytes",
        maximum_bytes,
        maximum=MAXIMUM_ARTIFACT_BYTES,
    )
    maximum_page_payload_bytes = _positive_bound(
        "maximum page payload bytes",
        maximum_page_payload_bytes,
        maximum=MAXIMUM_PAGE_PAYLOAD_BYTES,
    )
    if (leaf_count is None) != (leaf_commitment is None):
        _fail("v3 leaf count and commitment must be supplied together")
    if leaf_count is not None:
        leaf_count = _positive_bound(
            "leaf count", leaf_count, maximum=MAX_EVENT_COUNT
        )
        leaf_commitment = _uint(
            "leaf commitment",
            leaf_commitment,
            maximum=_ROLLING_MODULUS - 1,
        )
    identities = primitive_frequency_records_bulk(q)
    primitive_count = len(identities)
    if primitive_count == 0:
        _fail("v3 artifacts require a nonempty primitive roster")
    roster_sha256 = _roster_digest(identities)
    if (
        expected_roster_sha256 is not None
        and roster_sha256
        != _digest("expected complete roster", expected_roster_sha256)
    ):
        _fail("v3 complete primitive roster differs from its external pin")
    page_count = (primitive_count + PAGE_CHARACTERS - 1) // PAGE_CHARACTERS
    count_width = transition_count_width(sample_count)
    mode_flags = PRODUCTION_FLAG | (
        DEBUG_BRACKET_FLAG if debug_brackets else 0
    )
    path = Path(path)
    if path.exists() or path.is_symlink():
        _fail("refusing to replace an immutable v3 artifact")
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    iterator = iter(states)
    transition_total = 0
    ambiguity_total = 0
    range_total = 0
    debug_bracket_total = 0
    observed_characters = 0
    observed_pages = 0
    semantic = hashlib.sha256()
    semantic.update(LEAF_DOMAIN)
    written = 0
    placeholder = bytes(ARTIFACT_HEADER.size)
    try:
        with os.fdopen(descriptor, "w+b") as output:
            output.write(placeholder)
            written += len(placeholder)
            for page_index in range(page_count):
                start = page_index * PAGE_CHARACTERS
                count = min(PAGE_CHARACTERS, primitive_count - start)
                page_states: list[dict[str, Any]] = []
                for local in range(count):
                    try:
                        raw_state = next(iterator)
                    except StopIteration:
                        _fail("v3 state producer ended before the complete roster")
                    page_states.append(
                        _normalize_state(
                            raw_state,
                            identity=identities[start + local],
                            span_first=first,
                            span_stop=stop,
                            sample_count=sample_count,
                            debug=debug_brackets,
                        )
                    )
                raw_page, totals = _page_bytes(
                    page_states,
                    ordinal_start=start,
                    sample_count=sample_count,
                    count_width=count_width,
                    debug=debug_brackets,
                    maximum_page_payload_bytes=maximum_page_payload_bytes,
                )
                if written + len(raw_page) > maximum_bytes:
                    _fail("v3 artifact exceeds its externally supplied byte bound")
                output.write(raw_page)
                semantic.update(raw_page)
                written += len(raw_page)
                observed_characters += totals["character_count"]
                observed_pages += 1
                transition_total += totals["transition_count"]
                ambiguity_total += totals["ambiguity_sample_count"]
                range_total += totals["ambiguity_range_count"]
                debug_bracket_total += totals["debug_bracket_count"]
            try:
                next(iterator)
            except StopIteration:
                pass
            else:
                _fail("v3 state producer contains characters after the roster")
            if (
                observed_characters != primitive_count
                or observed_pages != page_count
            ):
                _fail("v3 page coverage differs from the complete roster")
            if leaf_count is None:
                leaf_count = 1
                raw_leaf = hashlib.sha256(
                    LEAF_DOMAIN
                    + bytes.fromhex(source_binding_sha256)
                    + semantic.digest()
                ).digest()
                leaf_commitment = (
                    int.from_bytes(raw_leaf, "big") % _ROLLING_MODULUS
                )
            assert leaf_commitment is not None
            header = V3Header(
                mode_flags=mode_flags,
                q=q,
                page_characters=PAGE_CHARACTERS,
                count_width=count_width,
                primitive_count=primitive_count,
                frame_count=frame_count,
                first_t_numerator=first,
                stop_t_numerator=stop,
                page_count=page_count,
                transition_count=transition_total,
                ambiguity_sample_count=ambiguity_total,
                ambiguity_range_count=range_total,
                debug_bracket_count=debug_bracket_total,
                leaf_count=leaf_count,
                leaf_commitment=leaf_commitment,
                roster_sha256=roster_sha256,
                source_binding_sha256=source_binding_sha256,
            )
            output.seek(0)
            output.write(_pack_header(header))
            output.flush()
            os.fsync(output.fileno())
        digest = hashlib.sha256()
        with temporary.open("rb") as source:
            while raw := source.read(8 * 1024 * 1024):
                digest.update(raw)
        if temporary.stat().st_size != written:
            _fail("v3 writer byte accounting differs")
        os.link(temporary, path)
        temporary.unlink()
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
        artifact_sha256=digest.hexdigest(),
        size_bytes=written,
        header=header,
    )
    replay = replay_compact_state_v3(
        path,
        expected_record=record,
        maximum_bytes=maximum_bytes,
        maximum_page_payload_bytes=maximum_page_payload_bytes,
    )
    if replay != record:
        _fail("fresh v3 replay record differs after materialization")
    return record


def write_flat_sign_codes_v3(
    path: Path,
    *,
    q: int,
    frame_count: int,
    first_t_numerator: int,
    stop_t_numerator: int,
    code_chunks: Iterable[Iterable[int]],
    source_binding_sha256: str,
    expected_roster_sha256: str | None = None,
    maximum_bytes: int = DEFAULT_MAXIMUM_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Direct producer-to-v3 vertical slice with no packed sign handoff."""

    return write_compact_state_v3(
        path,
        q=q,
        frame_count=frame_count,
        first_t_numerator=first_t_numerator,
        stop_t_numerator=stop_t_numerator,
        states=character_states_from_flat_sign_codes(
            q=q,
            first_t_numerator=first_t_numerator,
            stop_t_numerator=stop_t_numerator,
            code_chunks=code_chunks,
        ),
        source_binding_sha256=source_binding_sha256,
        expected_roster_sha256=expected_roster_sha256,
        maximum_bytes=maximum_bytes,
    )


def write_completed_real_disk_stream_v3(
    path: Path,
    *,
    q: int,
    frame_count: int,
    first_t_numerator: int,
    stop_t_numerator: int,
    disk_chunks: Iterable[
        Iterable[tuple[float, float, float]]
    ],
    source_binding_sha256: str,
    expected_roster_sha256: str | None = None,
    maximum_bytes: int = DEFAULT_MAXIMUM_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Fuse strict semantic signs into v3 without a disk/sign artifact.

    Each tuple is ``(real_center, disk_radius, replayed_time_tail_bound)``.
    Both errors are nonnegative outward binary64 bounds. Advancing their sum
    one word toward positive infinity reproduces the small-q semantic
    reducer's sufficient strict-sign test. The DFT containment and time-tail
    truth remain obligations of ``source_binding_sha256``; this function does
    not prove them.
    """

    def sign_chunks() -> Iterator[bytes]:
        for raw_chunk in disk_chunks:
            codes = bytearray()
            for row in raw_chunk:
                if (
                    not isinstance(row, tuple)
                    or len(row) != 3
                    or any(
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value)
                        for value in row
                    )
                ):
                    _fail("direct semantic disk row is malformed or nonfinite")
                real_center, radius, time_tail = map(float, row)
                if radius < 0.0 or time_tail < 0.0:
                    _fail("direct semantic disk errors must be nonnegative")
                boundary = math.nextafter(radius + time_tail, math.inf)
                if not math.isfinite(boundary):
                    _fail("direct semantic disk boundary overflows binary64")
                if real_center < -boundary:
                    codes.append(1)
                elif real_center > boundary:
                    codes.append(2)
                else:
                    codes.append(0)
            if codes:
                yield bytes(codes)

    return write_flat_sign_codes_v3(
        path,
        q=q,
        frame_count=frame_count,
        first_t_numerator=first_t_numerator,
        stop_t_numerator=stop_t_numerator,
        code_chunks=sign_chunks(),
        source_binding_sha256=source_binding_sha256,
        expected_roster_sha256=expected_roster_sha256,
        maximum_bytes=maximum_bytes,
    )


def _validate_artifact_record(value: Mapping[str, Any]) -> None:
    required = {
        "schema",
        "schema_version",
        "classification",
        "path",
        "artifact_sha256",
        "size_bytes",
        "q",
        "primitive_character_count",
        "frame_count",
        "first_t_numerator",
        "stop_t_numerator",
        "sample_count_per_character",
        "transition_count_width_bits",
        "transition_count",
        "ambiguity_sample_count",
        "ambiguity_range_count",
        "debug_bracket_count",
        "page_count",
        "page_characters",
        "complete_primitive_roster_sha256",
        "upstream_source_binding_sha256",
        "rank_select_sparse_rows",
        "first_last_ordinates_derived_from_span_and_maximal_ranges",
        "dense_transition_counts",
        "exact_maximal_ambiguity_ranges_retained",
        "exact_bracket_coordinates_retained_for_debug_only",
        "source_scale_layout",
        "producer_fused_with_arithmetic",
        "pointwise_transition_lower_bounds_proved",
        "exact_turing_totals_realized",
        "complete_roster_equivalence_realized",
        "aggregate_turing_closure_admitted",
        "source_scale_storage_admitted",
        "external_atom_discharged",
        "record_sha256",
    }
    body = dict(value)
    claimed = body.pop("record_sha256", None)
    raw_path = value.get("path")
    if (
        set(value) != required
        or value.get("schema") != ARTIFACT_SCHEMA
        or value.get("schema_version") != 3
        or value.get("classification")
        != (
            "source_streaming_dense_counts_and_sparse_ambiguities_"
            "not_zero_or_turing_evidence"
        )
        or not isinstance(raw_path, str)
        or not Path(raw_path).is_absolute()
        or str(Path(raw_path).resolve()) != raw_path
        or value.get("page_characters") != PAGE_CHARACTERS
        or value.get("rank_select_sparse_rows") is not True
        or value.get(
            "first_last_ordinates_derived_from_span_and_maximal_ranges"
        )
        is not True
        or value.get("dense_transition_counts") is not True
        or value.get("exact_maximal_ambiguity_ranges_retained") is not True
        or type(
            value.get("exact_bracket_coordinates_retained_for_debug_only")
        )
        is not bool
        or type(value.get("source_scale_layout")) is not bool
        or value["source_scale_layout"]
        is value["exact_bracket_coordinates_retained_for_debug_only"]
        or value.get("producer_fused_with_arithmetic") is not False
        or value.get("pointwise_transition_lower_bounds_proved") is not False
        or value.get("exact_turing_totals_realized") is not False
        or value.get("complete_roster_equivalence_realized") is not False
        or value.get("aggregate_turing_closure_admitted") is not False
        or value.get("source_scale_storage_admitted") is not False
        or value.get("external_atom_discharged") is not False
        or claimed
        != hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    ):
        _fail("v3 artifact record identity or self-hash differs")
    _digest("v3 artifact", value.get("artifact_sha256"))
    _digest(
        "v3 complete roster",
        value.get("complete_primitive_roster_sha256"),
    )
    _digest(
        "v3 upstream source",
        value.get("upstream_source_binding_sha256"),
    )
    for field in (
        "size_bytes",
        "q",
        "primitive_character_count",
        "frame_count",
        "first_t_numerator",
        "stop_t_numerator",
        "sample_count_per_character",
        "transition_count_width_bits",
        "transition_count",
        "ambiguity_sample_count",
        "ambiguity_range_count",
        "debug_bracket_count",
        "page_count",
    ):
        _uint(field, value.get(field), maximum=MAX_EVENT_COUNT)


def _decode_page(
    payload: bytes,
    *,
    header: V3Header,
    ordinal_start: int,
    character_count: int,
    sparse_character_count: int,
    identities: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    record_width = 4 + header.count_width
    fixed_bytes = _packed_bytes(character_count, record_width)
    if len(payload) < fixed_bytes:
        _fail("v3 page is shorter than its dense records")
    packed = payload[:fixed_bytes]
    _check_padding(
        packed,
        character_count * record_width,
        label="v3 packed page",
    )
    decoded: list[tuple[bool, int, int, bool, int]] = []
    observed_sparse = 0
    for local in range(character_count):
        value = _get_bits(
            packed,
            local * record_width,
            record_width,
        )
        has_determinate = bool(value & 1)
        first_sign = 1 if value & 2 else -1
        last_sign = 1 if value & 4 else -1
        has_sparse = bool(value & 8)
        transition = value >> 4
        if not has_determinate:
            if value & 6 or transition:
                _fail("v3 absent-determinate record has sign or count bits")
            first_sign = 0
            last_sign = 0
        observed_sparse += int(has_sparse)
        decoded.append(
            (
                has_determinate,
                first_sign,
                last_sign,
                has_sparse,
                transition,
            )
        )
    if observed_sparse != sparse_character_count:
        _fail("v3 sparse flag rank differs from the page header")
    offset = fixed_bytes
    states: list[dict[str, Any]] = []
    page_transitions = 0
    page_ambiguities = 0
    page_ranges = 0
    page_brackets = 0
    span_first = header.first_t_numerator
    span_stop = header.stop_t_numerator
    samples = header.sample_count
    for local, (
        has_determinate,
        first_sign,
        last_sign,
        has_sparse,
        transition,
    ) in enumerate(decoded):
        ranges: list[dict[str, int]] = []
        brackets: list[dict[str, int]] = []
        if has_sparse:
            stop = offset + SPARSE_ROW_HEADER.size
            if stop > len(payload):
                _fail("truncated v3 sparse row header")
            range_count, bracket_count = SPARSE_ROW_HEADER.unpack(
                payload[offset:stop]
            )
            offset = stop
            if not header.debug and bracket_count:
                _fail("production v3 page contains debug bracket rows")
            previous_range_stop: int | None = None
            for _index in range(range_count):
                stop = offset + AMBIGUITY_RANGE_RECORD.size
                if stop > len(payload):
                    _fail("truncated v3 ambiguity range")
                first_value, stop_value = AMBIGUITY_RANGE_RECORD.unpack(
                    payload[offset:stop]
                )
                offset = stop
                row, _count = _normalize_range(
                    {
                        "first_t_numerator": first_value,
                        "stop_t_numerator": stop_value,
                    },
                    span_first=span_first,
                    span_stop=span_stop,
                    previous_stop=previous_range_stop,
                )
                ranges.append(row)
                previous_range_stop = row["stop_t_numerator"]
            previous_upper: int | None = None
            previous_upper_sign: int | None = None
            for _index in range(bracket_count):
                stop = offset + DEBUG_BRACKET_RECORD.size
                if stop > len(payload):
                    _fail("truncated v3 debug bracket")
                (
                    lower,
                    upper,
                    lower_sign,
                    upper_sign,
                    intervening,
                ) = DEBUG_BRACKET_RECORD.unpack(payload[offset:stop])
                offset = stop
                bracket = _normalize_debug_bracket(
                    {
                        "lower_t_numerator": lower,
                        "upper_t_numerator": upper,
                        "lower_sign": lower_sign,
                        "upper_sign": upper_sign,
                        "intervening_ambiguity_count": intervening,
                    },
                    span_first=span_first,
                    span_stop=span_stop,
                    ranges=ranges,
                    previous_upper=previous_upper,
                    previous_upper_sign=previous_upper_sign,
                )
                brackets.append(bracket)
                previous_upper = upper
                previous_upper_sign = upper_sign
        if has_sparse != bool(ranges or brackets):
            _fail("v3 sparse flag is noncanonical")
        ambiguity_count = sum(
            (
                row["stop_t_numerator"] - row["first_t_numerator"]
            )
            // SOURCE_SAMPLE_NUMERATOR
            for row in ranges
        )
        leading = (
            (ranges[0]["stop_t_numerator"] - span_first)
            // SOURCE_SAMPLE_NUMERATOR
            if ranges and ranges[0]["first_t_numerator"] == span_first
            else 0
        )
        trailing = (
            (span_stop - ranges[-1]["first_t_numerator"])
            // SOURCE_SAMPLE_NUMERATOR
            if ranges and ranges[-1]["stop_t_numerator"] == span_stop
            else 0
        )
        derived_has = ambiguity_count < samples
        first_value = (
            span_first + leading * SOURCE_SAMPLE_NUMERATOR
            if derived_has
            else None
        )
        last_value = (
            span_stop - (trailing + 1) * SOURCE_SAMPLE_NUMERATOR
            if derived_has
            else None
        )
        if has_determinate != derived_has:
            _fail("v3 determinate flag differs from its maximal ranges")
        raw_state = {
            "conrey_number": identities[local]["conrey_number"],
            "primitive_ordinal": identities[local]["primitive_ordinal"],
            "parity": identities[local]["parity"],
            "sample_count": samples,
            "first_determinate_numerator": first_value,
            "first_sign": first_sign,
            "last_determinate_numerator": last_value,
            "last_sign": last_sign,
            "leading_ambiguity_count": leading,
            "trailing_ambiguity_count": trailing,
            "ambiguity_count": ambiguity_count,
            "internal_sign_change_count": transition,
            "ambiguity_ranges": ranges,
            "bracket_records": brackets,
        }
        state = _normalize_state(
            raw_state,
            identity=identities[local],
            span_first=span_first,
            span_stop=span_stop,
            sample_count=samples,
            debug=header.debug,
        )
        states.append(state)
        page_transitions += transition
        page_ambiguities += ambiguity_count
        page_ranges += len(ranges)
        page_brackets += len(brackets)
    if offset != len(payload):
        _fail("v3 page has a gap, overlap, or trailing payload")
    return states, {
        "transition_count": page_transitions,
        "ambiguity_sample_count": page_ambiguities,
        "ambiguity_range_count": page_ranges,
        "debug_bracket_count": page_brackets,
    }


def _replay_stat_identity(status: os.stat_result) -> tuple[int, ...]:
    """Fields which must remain fixed over one semantic replay."""

    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_size,
        getattr(status, "st_mtime_ns", int(status.st_mtime * 1_000_000_000)),
        getattr(status, "st_ctime_ns", int(status.st_ctime * 1_000_000_000)),
    )


def _iter_compact_state_v3(
    path: Path,
    *,
    expected_record: Mapping[str, Any] | None,
    maximum_bytes: int,
    maximum_page_payload_bytes: int,
) -> Generator[dict[str, Any], None, _ReplayCompletion]:
    maximum_bytes = _positive_bound(
        "maximum artifact bytes",
        maximum_bytes,
        maximum=MAXIMUM_ARTIFACT_BYTES,
    )
    maximum_page_payload_bytes = _positive_bound(
        "maximum page payload bytes",
        maximum_page_payload_bytes,
        maximum=MAXIMUM_PAGE_PAYLOAD_BYTES,
    )
    if expected_record is not None:
        _validate_artifact_record(expected_record)
        if expected_record["path"] != str(path.resolve()):
            _fail("v3 expected artifact path differs")
    try:
        status = path.lstat()
    except OSError as error:
        raise DirichletCompactStateV3Error(
            f"cannot stat v3 artifact: {error}"
        ) from error
    if (
        path.is_symlink()
        or not stat.S_ISREG(status.st_mode)
        or not ARTIFACT_HEADER.size <= status.st_size <= maximum_bytes
        or (
            expected_record is not None
            and status.st_size != expected_record["size_bytes"]
        )
    ):
        _fail("v3 artifact type, size, or expected bound differs")
    digest = hashlib.sha256()
    transition_total = 0
    ambiguity_total = 0
    range_total = 0
    bracket_total = 0
    observed_characters = 0
    with path.open("rb") as source:
        if _replay_stat_identity(os.fstat(source.fileno())) != (
            _replay_stat_identity(status)
        ):
            _fail("v3 artifact changed between stat and replay open")
        raw_header = _read_exact(
            source, ARTIFACT_HEADER.size, label="v3 header"
        )
        digest.update(raw_header)
        header = _unpack_header(raw_header)
        identities = primitive_frequency_records_bulk(header.q)
        if (
            len(identities) != header.primitive_count
            or _roster_digest(identities) != header.roster_sha256
        ):
            _fail("v3 complete primitive roster digest differs")
        for page_index in range(header.page_count):
            raw_page_header = _read_exact(
                source, PAGE_HEADER.size, label="v3 page header"
            )
            digest.update(raw_page_header)
            (
                ordinal_start,
                character_count,
                sparse_character_count,
                payload_bytes,
                page_transitions,
                page_ambiguities,
                page_ranges,
                page_brackets,
                raw_page_sha256,
            ) = PAGE_HEADER.unpack(raw_page_header)
            expected_start = page_index * PAGE_CHARACTERS
            expected_count = min(
                PAGE_CHARACTERS,
                header.primitive_count - expected_start,
            )
            if (
                ordinal_start != expected_start
                or character_count != expected_count
                or sparse_character_count > character_count
                or payload_bytes > maximum_page_payload_bytes
                or page_transitions
                > character_count * max(0, header.sample_count - 1)
                or page_ambiguities
                > character_count * header.sample_count
                or (not header.debug and page_brackets)
            ):
                _fail("v3 page identity, bound, or arithmetic differs")
            payload = _read_exact(
                source, payload_bytes, label="v3 page payload"
            )
            digest.update(payload)
            prefix = PAGE_PREFIX.pack(
                ordinal_start,
                character_count,
                sparse_character_count,
                payload_bytes,
                page_transitions,
                page_ambiguities,
                page_ranges,
                page_brackets,
            )
            if hashlib.sha256(PAGE_DOMAIN + prefix + payload).digest() != (
                raw_page_sha256
            ):
                _fail("v3 page digest differs")
            states, totals = _decode_page(
                payload,
                header=header,
                ordinal_start=ordinal_start,
                character_count=character_count,
                sparse_character_count=sparse_character_count,
                identities=identities[
                    ordinal_start : ordinal_start + character_count
                ],
            )
            if totals != {
                "transition_count": page_transitions,
                "ambiguity_sample_count": page_ambiguities,
                "ambiguity_range_count": page_ranges,
                "debug_bracket_count": page_brackets,
            }:
                _fail("v3 page semantic totals differ")
            transition_total += page_transitions
            ambiguity_total += page_ambiguities
            range_total += page_ranges
            bracket_total += page_brackets
            observed_characters += character_count
            yield from states
        if source.read(1):
            _fail("v3 artifact has trailing bytes")
        final_open_status = os.fstat(source.fileno())
    try:
        final_status = path.lstat()
    except OSError as error:
        raise DirichletCompactStateV3Error(
            f"cannot restat replayed v3 artifact: {error}"
        ) from error
    if (
        _replay_stat_identity(final_open_status)
        != _replay_stat_identity(status)
        or _replay_stat_identity(final_status)
        != _replay_stat_identity(status)
    ):
        _fail("v3 artifact changed while it was replayed")
    if (
        observed_characters != header.primitive_count
        or transition_total != header.transition_count
        or ambiguity_total != header.ambiguity_sample_count
        or range_total != header.ambiguity_range_count
        or bracket_total != header.debug_bracket_count
    ):
        _fail("v3 artifact totals differ from its header")
    record = _artifact_record(
        path=path.resolve(),
        artifact_sha256=digest.hexdigest(),
        size_bytes=status.st_size,
        header=header,
    )
    if expected_record is not None and dict(expected_record) != record:
        _fail("v3 artifact differs from its expected record")
    return _ReplayCompletion(record=record, header=header)


def iter_compact_state_v3(
    path: Path,
    *,
    expected_record: Mapping[str, Any] | None = None,
    maximum_bytes: int = DEFAULT_MAXIMUM_ARTIFACT_BYTES,
    maximum_page_payload_bytes: int = DEFAULT_MAXIMUM_PAGE_PAYLOAD_BYTES,
) -> Iterator[dict[str, Any]]:
    """Yield fully page-validated states in complete-roster order."""

    yield from _iter_compact_state_v3(
        Path(path),
        expected_record=expected_record,
        maximum_bytes=maximum_bytes,
        maximum_page_payload_bytes=maximum_page_payload_bytes,
    )


def replay_compact_state_v3(
    path: Path,
    *,
    expected_record: Mapping[str, Any] | None = None,
    maximum_bytes: int = DEFAULT_MAXIMUM_ARTIFACT_BYTES,
    maximum_page_payload_bytes: int = DEFAULT_MAXIMUM_PAGE_PAYLOAD_BYTES,
) -> dict[str, Any]:
    """Bounded-memory full replay returning canonical artifact metadata."""

    path = Path(path)
    iterator = _iter_compact_state_v3(
        path,
        expected_record=expected_record,
        maximum_bytes=maximum_bytes,
        maximum_page_payload_bytes=maximum_page_payload_bytes,
    )
    while True:
        try:
            next(iterator)
        except StopIteration as completed:
            result = completed.value
            if not isinstance(result, _ReplayCompletion):
                _fail("v3 semantic replay did not return its canonical record")
            return result.record


def _merge_character_states(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    left_first: int,
    left_stop: int,
    right_first: int,
    right_stop: int,
    debug: bool,
) -> dict[str, Any]:
    if left_stop != right_first:
        _fail("v3 character states are not adjacent exact-grid lanes")
    for field in ("conrey_number", "primitive_ordinal", "parity"):
        if left.get(field) != right.get(field):
            _fail("v3 cross-lane character identities differ")
    left_has = left["first_determinate_numerator"] is not None
    right_has = right["first_determinate_numerator"] is not None
    left_samples = (left_stop - left_first) // SOURCE_SAMPLE_NUMERATOR
    right_samples = (right_stop - right_first) // SOURCE_SAMPLE_NUMERATOR
    transition = (
        left["internal_sign_change_count"]
        + right["internal_sign_change_count"]
    )
    insert_boundary = (
        left_has and right_has and left["last_sign"] != right["first_sign"]
    )
    transition += int(insert_boundary)
    ranges = [dict(row) for row in left["ambiguity_ranges"]]
    ranges.extend(dict(row) for row in right["ambiguity_ranges"])
    if (
        left["ambiguity_ranges"]
        and right["ambiguity_ranges"]
        and left["ambiguity_ranges"][-1]["stop_t_numerator"]
        == right["ambiguity_ranges"][0]["first_t_numerator"]
    ):
        join = len(left["ambiguity_ranges"]) - 1
        ranges[join : join + 2] = [
            {
                "first_t_numerator": ranges[join]["first_t_numerator"],
                "stop_t_numerator": ranges[join + 1][
                    "stop_t_numerator"
                ],
            }
        ]
    if left_has:
        first = left["first_determinate_numerator"]
        first_sign = left["first_sign"]
    else:
        first = right["first_determinate_numerator"]
        first_sign = right["first_sign"]
    if right_has:
        last = right["last_determinate_numerator"]
        last_sign = right["last_sign"]
    else:
        last = left["last_determinate_numerator"]
        last_sign = left["last_sign"]
    if not left_has and not right_has:
        first_sign = 0
        last_sign = 0
    leading = (
        left["leading_ambiguity_count"]
        if left_has
        else left_samples + right["leading_ambiguity_count"]
    )
    trailing = (
        right["trailing_ambiguity_count"]
        if right_has
        else right_samples + left["trailing_ambiguity_count"]
    )
    brackets: list[dict[str, int]] = []
    if debug:
        brackets.extend(dict(row) for row in left["bracket_records"])
        if insert_boundary:
            assert left["last_determinate_numerator"] is not None
            assert right["first_determinate_numerator"] is not None
            brackets.append(
                {
                    "lower_t_numerator": left[
                        "last_determinate_numerator"
                    ],
                    "upper_t_numerator": right[
                        "first_determinate_numerator"
                    ],
                    "lower_sign": left["last_sign"],
                    "upper_sign": right["first_sign"],
                    "intervening_ambiguity_count": (
                        left["trailing_ambiguity_count"]
                        + right["leading_ambiguity_count"]
                    ),
                }
            )
        brackets.extend(dict(row) for row in right["bracket_records"])
    return {
        "conrey_number": left["conrey_number"],
        "primitive_ordinal": left["primitive_ordinal"],
        "parity": left["parity"],
        "sample_count": left_samples + right_samples,
        "first_determinate_numerator": first,
        "first_sign": first_sign,
        "last_determinate_numerator": last,
        "last_sign": last_sign,
        "leading_ambiguity_count": leading,
        "trailing_ambiguity_count": trailing,
        "ambiguity_count": (
            left["ambiguity_count"] + right["ambiguity_count"]
        ),
        "internal_sign_change_count": transition,
        "ambiguity_ranges": ranges,
        "bracket_records": brackets,
    }


def _merged_source_binding(
    *,
    q: int,
    roster_sha256: str,
    first_t_numerator: int,
    stop_t_numerator: int,
    leaf_count: int,
    leaf_commitment: int,
) -> str:
    """Grouping-independent identifier for the polynomial leaf summary.

    The returned value is SHA-256, but its ``leaf_commitment`` input is a
    rolling field summary rather than a collision-resistant commitment.
    Consequently this identifier must not be described as cryptographically
    binding every lane's upstream source digest.  The finalizer receipt pins
    the lane artifact SHA-256 values separately and admission remains false.
    """

    digest = hashlib.sha256(SOURCE_MERGE_DOMAIN)
    digest.update(q.to_bytes(4, "little"))
    digest.update(bytes.fromhex(roster_sha256))
    digest.update(first_t_numerator.to_bytes(8, "little"))
    digest.update(stop_t_numerator.to_bytes(8, "little"))
    digest.update(leaf_count.to_bytes(8, "little"))
    digest.update(leaf_commitment.to_bytes(32, "big"))
    return digest.hexdigest()


def finalize_compact_state_v3_lanes(
    lane_paths: Sequence[Path],
    output_path: Path,
    *,
    expected_records: Sequence[Mapping[str, Any]] | None = None,
    turing_total: int | None = None,
    maximum_bytes: int = DEFAULT_MAXIMUM_ARTIFACT_BYTES,
    maximum_page_payload_bytes: int = DEFAULT_MAXIMUM_PAGE_PAYLOAD_BYTES,
) -> dict[str, Any]:
    """Merge adjacent lane states and report the aggregate-Turing boundary."""

    if not 1 <= len(lane_paths) <= MAXIMUM_LANES:
        _fail(f"v3 finalizer requires 1..{MAXIMUM_LANES} lanes")
    if expected_records is not None and len(expected_records) != len(
        lane_paths
    ):
        _fail("v3 expected-record and lane counts differ")
    paths = [Path(path) for path in lane_paths]
    headers = [
        inspect_compact_state_v3(path, maximum_bytes=maximum_bytes)
        for path in paths
    ]
    first_header = headers[0]
    for index, header in enumerate(headers):
        if (
            header.q != first_header.q
            or header.primitive_count != first_header.primitive_count
            or header.roster_sha256 != first_header.roster_sha256
            or header.mode_flags != first_header.mode_flags
            or (
                index
                and headers[index - 1].stop_t_numerator
                != header.first_t_numerator
            )
        ):
            _fail("v3 lane roster, mode, or exact adjacency differs")
    iterators = [
        _iter_compact_state_v3(
            path,
            expected_record=(
                None if expected_records is None else expected_records[index]
            ),
            maximum_bytes=maximum_bytes,
            maximum_page_payload_bytes=maximum_page_payload_bytes,
        )
        for index, path in enumerate(paths)
    ]
    lane_replay_records: list[dict[str, Any] | None] = [
        None for _path in paths
    ]

    def merged_states() -> Iterator[dict[str, Any]]:
        for ordinal in range(first_header.primitive_count):
            lane_states: list[dict[str, Any]] = []
            for iterator in iterators:
                try:
                    lane_states.append(next(iterator))
                except StopIteration:
                    _fail("v3 lane ended before the complete roster")
            current = lane_states[0]
            current_first = headers[0].first_t_numerator
            current_stop = headers[0].stop_t_numerator
            for lane_index in range(1, len(lane_states)):
                current = _merge_character_states(
                    current,
                    lane_states[lane_index],
                    left_first=current_first,
                    left_stop=current_stop,
                    right_first=headers[lane_index].first_t_numerator,
                    right_stop=headers[lane_index].stop_t_numerator,
                    debug=first_header.debug,
                )
                current_stop = headers[lane_index].stop_t_numerator
            if current["primitive_ordinal"] != ordinal:
                _fail("v3 merged primitive ordinals differ")
            yield current
        for lane_index, iterator in enumerate(iterators):
            try:
                next(iterator)
            except StopIteration as completed:
                result = completed.value
                if (
                    not isinstance(result, _ReplayCompletion)
                    or result.header != headers[lane_index]
                ):
                    _fail(
                        "v3 lane header changed between finalizer preflight "
                        "and semantic replay"
                    )
                lane_replay_records[lane_index] = result.record
                continue
            _fail("v3 lane contains characters after the complete roster")

    leaf_count = headers[0].leaf_count
    leaf_commitment = headers[0].leaf_commitment
    for header in headers[1:]:
        leaf_count, leaf_commitment = combine_associative_event_commitments(
            leaf_count,
            leaf_commitment,
            header.leaf_count,
            header.leaf_commitment,
        )
    output_record = write_compact_state_v3(
        output_path,
        q=first_header.q,
        frame_count=sum(header.frame_count for header in headers),
        first_t_numerator=first_header.first_t_numerator,
        stop_t_numerator=headers[-1].stop_t_numerator,
        states=merged_states(),
        source_binding_sha256=_merged_source_binding(
            q=first_header.q,
            roster_sha256=first_header.roster_sha256,
            first_t_numerator=first_header.first_t_numerator,
            stop_t_numerator=headers[-1].stop_t_numerator,
            leaf_count=leaf_count,
            leaf_commitment=leaf_commitment,
        ),
        debug_brackets=first_header.debug,
        leaf_count=leaf_count,
        leaf_commitment=leaf_commitment,
        expected_roster_sha256=first_header.roster_sha256,
        maximum_bytes=maximum_bytes,
        maximum_page_payload_bytes=maximum_page_payload_bytes,
    )
    output_header = inspect_compact_state_v3(
        output_path.resolve(), maximum_bytes=maximum_bytes
    )
    if any(record is None for record in lane_replay_records):
        _fail("v3 finalizer did not capture every replayed lane record")
    lane_internal = sum(header.transition_count for header in headers)
    if not lane_internal <= output_header.transition_count:
        _fail("v3 merged transition total lost lane-internal changes")
    cross = output_header.transition_count - lane_internal
    if cross > (len(headers) - 1) * first_header.primitive_count:
        _fail("v3 cross-lane transition count exceeds one per boundary")
    if turing_total is not None:
        turing_total = _uint("q-level Turing total", turing_total)
    aggregate_equal = (
        turing_total is not None
        and turing_total == output_header.transition_count
    )
    body: dict[str, Any] = {
        "schema": (
            "sparkinterval.tg.dirichlet_compact_state_finalizer.receipt.v3"
        ),
        "schema_version": 3,
        "classification": (
            "q_transition_aggregate_and_exception_state_"
            "not_analytic_or_turing_realization"
        ),
        "q": output_header.q,
        "q1_zeta_case_separate": True,
        "lane_count": len(headers),
        "lane_artifact_sha256": [
            record["artifact_sha256"]
            for record in lane_replay_records
            if record is not None
        ],
        "merged_source_binding_construction": (
            "sha256_over_q_roster_span_and_polynomial_ordered_leaf_summary"
        ),
        "merged_source_binding_commits_lane_upstream_sha256s": False,
        "lane_artifact_sha256s_pinned_by_receipt_only": True,
        "lane_internal_transition_sum": lane_internal,
        "cross_lane_transition_count": cross,
        "q_transition_count": output_header.transition_count,
        "q_turing_total": turing_total,
        "q_aggregate_counts_equal": aggregate_equal,
        "complete_primitive_roster_sha256": output_header.roster_sha256,
        "complete_roster_formulaic_and_duplicate_free_checked": True,
        "output_artifact": output_record,
        "aggregate_turing_lean_boundary": {
            "module": "SparkInterval.Dirichlet.AggregateTuringClosure",
            "evidence": "AggregateTuringCountEvidence",
            "pointwise_lower_bound_required": True,
            "per_character_turing_upper_bound_required": True,
            "exact_same_complete_roster_sum_required": True,
            "zero_count_upper_bound_rewrite": (
                "zeroCountUpperBound_at_bracketCount"
            ),
            "complete_roster_capstone": (
                "grhVerifiedForModulus_of_aggregateTuringEndpointFamilies"
            ),
        },
        "physical_pointwise_transition_lower_bounds_proved": False,
        "physical_turing_totals_realized": False,
        "physical_complete_roster_equivalence_realized": False,
        "aggregate_turing_closure_admitted": False,
        "source_scale_storage_admitted": False,
        "source_scale_run": False,
        "external_atom_discharged": False,
    }
    result = dict(body)
    result["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def _mmr_append(peaks: list[bytes | None], leaf: bytes) -> None:
    height = 0
    node = leaf
    while height < len(peaks) and peaks[height] is not None:
        left = peaks[height]
        assert left is not None
        digest = hashlib.sha256(EXCEPTION_NODE_DOMAIN)
        digest.update(height.to_bytes(4, "little"))
        digest.update(left)
        digest.update(node)
        node = digest.digest()
        peaks[height] = None
        height += 1
    if height == len(peaks):
        peaks.append(node)
    else:
        peaks[height] = node


def _mmr_root(count: int, peaks: Sequence[bytes | None]) -> str:
    occupied = [
        (height, peak)
        for height, peak in reversed(list(enumerate(peaks)))
        if peak is not None
    ]
    digest = hashlib.sha256(EXCEPTION_ROOT_DOMAIN)
    digest.update(count.to_bytes(8, "little"))
    digest.update(len(occupied).to_bytes(4, "little"))
    for height, peak in occupied:
        assert peak is not None
        digest.update(height.to_bytes(4, "little"))
        digest.update(peak)
    return digest.hexdigest()


def _exception_record(
    *,
    path: Path,
    artifact_sha256: str,
    size_bytes: int,
    q: int,
    roster_count: int,
    first_t_numerator: int,
    stop_t_numerator: int,
    range_character_count: int,
    range_count: int,
    ambiguity_sample_count: int,
    roster_sha256: str,
    source_state_sha256: str,
    exception_mmr_sha256: str,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": (
            "sparkinterval.tg.dirichlet_compact_state_v3."
            "exception_artifact.v1"
        ),
        "schema_version": 1,
        "classification": (
            "sparse_maximal_ambiguity_refinement_input_"
            "not_zero_or_turing_evidence"
        ),
        "path": str(path.resolve()),
        "artifact_sha256": artifact_sha256,
        "size_bytes": size_bytes,
        "q": q,
        "complete_roster_count": roster_count,
        "first_t_numerator": first_t_numerator,
        "stop_t_numerator": stop_t_numerator,
        "ambiguity_character_count": range_character_count,
        "ambiguity_range_count": range_count,
        "ambiguity_sample_count": ambiguity_sample_count,
        "complete_primitive_roster_sha256": roster_sha256,
        "source_dense_state_sha256": source_state_sha256,
        "exception_mmr_sha256": exception_mmr_sha256,
        "formulaic_ordinal_sparse_rows": True,
        "exact_maximal_ambiguity_ranges_retained": True,
        "refinement_complete": False,
        "source_scale_storage_admitted": False,
        "external_atom_discharged": False,
    }
    result = dict(body)
    result["record_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def write_exception_artifact_v3(
    state_path: Path,
    exception_path: Path,
    *,
    expected_state_record: Mapping[str, Any] | None = None,
    maximum_state_bytes: int = DEFAULT_MAXIMUM_ARTIFACT_BYTES,
    maximum_exception_bytes: int = DEFAULT_MAXIMUM_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Retain only sparse ambiguity rows plus an ordered MMR commitment."""

    state_path = Path(state_path)
    exception_path = Path(exception_path)
    if exception_path.exists() or exception_path.is_symlink():
        _fail("refusing to replace an immutable v3 exception artifact")
    exception_path = exception_path.resolve()
    state_record = replay_compact_state_v3(
        state_path,
        expected_record=expected_state_record,
        maximum_bytes=maximum_state_bytes,
    )
    header = inspect_compact_state_v3(
        state_path, maximum_bytes=maximum_state_bytes
    )
    maximum_exception_bytes = _positive_bound(
        "maximum exception artifact bytes",
        maximum_exception_bytes,
        maximum=MAXIMUM_ARTIFACT_BYTES,
    )
    exception_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{exception_path.name}.", dir=exception_path.parent
    )
    temporary = Path(temporary_name)
    range_characters = 0
    range_count = 0
    ambiguity_count = 0
    peaks: list[bytes | None] = []
    written = EXCEPTION_HEADER.size
    placeholder = bytes(EXCEPTION_HEADER.size)
    try:
        with os.fdopen(descriptor, "w+b") as output:
            output.write(placeholder)
            for state in iter_compact_state_v3(
                state_path,
                expected_record=state_record,
                maximum_bytes=maximum_state_bytes,
            ):
                ranges = state["ambiguity_ranges"]
                if not ranges:
                    continue
                row = bytearray(
                    EXCEPTION_CHARACTER_HEADER.pack(
                        state["primitive_ordinal"], len(ranges)
                    )
                )
                for raw_range in ranges:
                    row.extend(
                        AMBIGUITY_RANGE_RECORD.pack(
                            raw_range["first_t_numerator"],
                            raw_range["stop_t_numerator"],
                        )
                    )
                if written + len(row) > maximum_exception_bytes:
                    _fail(
                        "v3 exception artifact exceeds its external byte bound"
                    )
                output.write(row)
                leaf = hashlib.sha256(
                    EXCEPTION_LEAF_DOMAIN + bytes(row)
                ).digest()
                _mmr_append(peaks, leaf)
                written += len(row)
                range_characters += 1
                range_count += len(ranges)
                ambiguity_count += state["ambiguity_count"]
            root = _mmr_root(range_characters, peaks)
            if (
                range_count != header.ambiguity_range_count
                or ambiguity_count != header.ambiguity_sample_count
            ):
                _fail("v3 exception extraction totals differ")
            raw_header = EXCEPTION_HEADER.pack(
                EXCEPTION_MAGIC,
                EXCEPTION_FORMAT_VERSION,
                header.q,
                header.primitive_count,
                header.first_t_numerator,
                header.stop_t_numerator,
                range_characters,
                range_count,
                ambiguity_count,
                bytes.fromhex(header.roster_sha256),
                bytes.fromhex(state_record["artifact_sha256"]),
                bytes.fromhex(root),
            )
            output.seek(0)
            output.write(raw_header)
            output.flush()
            os.fsync(output.fileno())
        digest = hashlib.sha256()
        with temporary.open("rb") as source:
            while raw := source.read(8 * 1024 * 1024):
                digest.update(raw)
        if temporary.stat().st_size != written:
            _fail("v3 exception artifact byte accounting differs")
        os.link(temporary, exception_path)
        temporary.unlink()
        directory = os.open(
            exception_path.parent,
            getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY,
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    record = _exception_record(
        path=exception_path,
        artifact_sha256=digest.hexdigest(),
        size_bytes=written,
        q=header.q,
        roster_count=header.primitive_count,
        first_t_numerator=header.first_t_numerator,
        stop_t_numerator=header.stop_t_numerator,
        range_character_count=range_characters,
        range_count=range_count,
        ambiguity_sample_count=ambiguity_count,
        roster_sha256=header.roster_sha256,
        source_state_sha256=state_record["artifact_sha256"],
        exception_mmr_sha256=root,
    )
    replayed = replay_exception_artifact_v3(
        exception_path,
        expected_record=record,
        maximum_bytes=maximum_exception_bytes,
    )
    if replayed != record:
        _fail("fresh v3 exception replay differs")
    return record


def replay_exception_artifact_v3(
    path: Path,
    *,
    expected_record: Mapping[str, Any] | None = None,
    maximum_bytes: int = DEFAULT_MAXIMUM_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Streaming replay for the retained ambiguity-only artifact."""

    path = Path(path)
    maximum_bytes = _positive_bound(
        "maximum exception artifact bytes",
        maximum_bytes,
        maximum=MAXIMUM_ARTIFACT_BYTES,
    )
    try:
        status = path.lstat()
    except OSError as error:
        raise DirichletCompactStateV3Error(
            f"cannot stat v3 exception artifact: {error}"
        ) from error
    if (
        path.is_symlink()
        or not stat.S_ISREG(status.st_mode)
        or not EXCEPTION_HEADER.size <= status.st_size <= maximum_bytes
    ):
        _fail("v3 exception artifact type or size differs")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        if _replay_stat_identity(os.fstat(source.fileno())) != (
            _replay_stat_identity(status)
        ):
            _fail("v3 exception artifact changed between stat and replay open")
        raw_header = _read_exact(
            source, EXCEPTION_HEADER.size, label="v3 exception header"
        )
        digest.update(raw_header)
        (
            magic,
            version,
            q,
            roster_count,
            first_t_numerator,
            stop_t_numerator,
            range_character_count,
            range_count,
            ambiguity_sample_count,
            raw_roster,
            raw_state,
            raw_mmr,
        ) = EXCEPTION_HEADER.unpack(raw_header)
        _first, _stop, _samples = _state_span(
            first_t_numerator=first_t_numerator,
            stop_t_numerator=stop_t_numerator,
        )
        if (
            magic != EXCEPTION_MAGIC
            or version != EXCEPTION_FORMAT_VERSION
            or not 1 <= q <= MAXIMUM_MODULUS
            or roster_count != primitive_character_count(q)
            or raw_roster.hex()
            != _roster_digest(primitive_frequency_records_bulk(q))
            or range_character_count > roster_count
            or ambiguity_sample_count > roster_count * _samples
        ):
            _fail("v3 exception header identity or arithmetic differs")
        previous_ordinal: int | None = None
        observed_ranges = 0
        observed_ambiguity = 0
        peaks: list[bytes | None] = []
        for _row_index in range(range_character_count):
            raw_character = _read_exact(
                source,
                EXCEPTION_CHARACTER_HEADER.size,
                label="v3 exception character",
            )
            ordinal, character_ranges = EXCEPTION_CHARACTER_HEADER.unpack(
                raw_character
            )
            if (
                character_ranges == 0
                or ordinal >= roster_count
                or (
                    previous_ordinal is not None
                    and ordinal <= previous_ordinal
                )
            ):
                _fail("v3 exception ordinal or range rank is noncanonical")
            previous_ordinal = ordinal
            raw_row = bytearray(raw_character)
            previous_stop: int | None = None
            for _index in range(character_ranges):
                raw_range = _read_exact(
                    source,
                    AMBIGUITY_RANGE_RECORD.size,
                    label="v3 exception range",
                )
                raw_row.extend(raw_range)
                range_first, range_stop = AMBIGUITY_RANGE_RECORD.unpack(
                    raw_range
                )
                row, count = _normalize_range(
                    {
                        "first_t_numerator": range_first,
                        "stop_t_numerator": range_stop,
                    },
                    span_first=_first,
                    span_stop=_stop,
                    previous_stop=previous_stop,
                )
                previous_stop = row["stop_t_numerator"]
                observed_ranges += 1
                observed_ambiguity += count
            digest.update(raw_row)
            _mmr_append(
                peaks,
                hashlib.sha256(
                    EXCEPTION_LEAF_DOMAIN + bytes(raw_row)
                ).digest(),
            )
        if source.read(1):
            _fail("v3 exception artifact has trailing bytes")
        final_open_status = os.fstat(source.fileno())
    try:
        final_status = path.lstat()
    except OSError as error:
        raise DirichletCompactStateV3Error(
            f"cannot restat replayed v3 exception artifact: {error}"
        ) from error
    if (
        _replay_stat_identity(final_open_status)
        != _replay_stat_identity(status)
        or _replay_stat_identity(final_status)
        != _replay_stat_identity(status)
    ):
        _fail("v3 exception artifact changed while it was replayed")
    if (
        observed_ranges != range_count
        or observed_ambiguity != ambiguity_sample_count
        or _mmr_root(range_character_count, peaks) != raw_mmr.hex()
    ):
        _fail("v3 exception totals or MMR differ")
    record = _exception_record(
        path=path,
        artifact_sha256=digest.hexdigest(),
        size_bytes=status.st_size,
        q=q,
        roster_count=roster_count,
        first_t_numerator=_first,
        stop_t_numerator=_stop,
        range_character_count=range_character_count,
        range_count=range_count,
        ambiguity_sample_count=ambiguity_sample_count,
        roster_sha256=raw_roster.hex(),
        source_state_sha256=raw_state.hex(),
        exception_mmr_sha256=raw_mmr.hex(),
    )
    if expected_record is not None and dict(expected_record) != record:
        _fail("v3 exception artifact differs from its expected record")
    return record


def retire_compact_state_v3(
    state_path: Path,
    exception_path: Path,
    summary_path: Path,
    *,
    expected_state_record: Mapping[str, Any] | None = None,
    turing_total: int,
    discard_dense_state: bool = False,
) -> dict[str, Any]:
    """Retain a q summary/exceptions, preserving dense pages by default.

    Discarding the only dense copy sacrifices independent per-character
    replay and is intended only after a trusted-execution result is accepted
    or the dense artifact is archived elsewhere.
    """

    state_path = Path(state_path)
    summary_path = Path(summary_path)
    if summary_path.exists() or summary_path.is_symlink():
        _fail("refusing to replace an immutable v3 retained q summary")
    summary_path = summary_path.resolve()
    state_record = replay_compact_state_v3(
        state_path, expected_record=expected_state_record
    )
    turing_total = _uint("q-level Turing total", turing_total)
    equal = state_record["transition_count"] == turing_total
    if discard_dense_state and not equal:
        _fail(
            "v3 dense state cannot be retired before its q aggregate "
            "matches the supplied Turing total"
        )
    exception_record = write_exception_artifact_v3(
        state_path,
        exception_path,
        expected_state_record=state_record,
    )
    body: dict[str, Any] = {
        "schema": (
            "sparkinterval.tg.dirichlet_compact_state_v3."
            "retained_q_summary.v1"
        ),
        "schema_version": 1,
        "classification": (
            "retained_q_aggregate_and_exception_commitment_"
            "not_analytic_or_turing_realization"
        ),
        "q": state_record["q"],
        "q1_zeta_case_separate": True,
        "complete_primitive_roster_sha256": state_record[
            "complete_primitive_roster_sha256"
        ],
        "dense_state_artifact_sha256": state_record["artifact_sha256"],
        "q_transition_count": state_record["transition_count"],
        "q_turing_total": turing_total,
        "q_aggregate_counts_equal": equal,
        "exception_artifact": exception_record,
        "exception_mmr_sha256": exception_record[
            "exception_mmr_sha256"
        ],
        "dense_state_retirement_authorized_after_durable_summary": (
            discard_dense_state
        ),
        "aggregate_turing_lean_boundary": {
            "module": "SparkInterval.Dirichlet.AggregateTuringClosure",
            "evidence": "AggregateTuringCountEvidence",
            "pointwise_lower_bound_required": True,
            "per_character_turing_upper_bound_required": True,
            "same_complete_roster_equivalence_required": True,
        },
        "physical_pointwise_transition_lower_bounds_proved": False,
        "physical_turing_totals_realized": False,
        "physical_complete_roster_equivalence_realized": False,
        "aggregate_turing_closure_admitted": False,
        "refinement_complete": False,
        "source_scale_storage_admitted": False,
        "external_atom_discharged": False,
    }
    result = dict(body)
    result["summary_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{summary_path.name}.", dir=summary_path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(canonical_json_bytes(result))
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, summary_path)
        temporary.unlink()
        directory = os.open(
            summary_path.parent,
            getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY,
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        if discard_dense_state:
            _unlink_dense_state(state_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return result


def _unlink_dense_state(path: Path) -> None:
    """Retire dense pages only after the retained summary is durable."""

    path.unlink()
    directory = os.open(
        path.parent,
        getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY,
    )
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _source_projection_body() -> dict[str, Any]:
    spf = _smallest_prime_factors(SOURCE_Q_STOP)
    width_histogram: dict[int, int] = {}
    final_dense_bits = 0
    final_wire_bytes = 0
    final_pages = 0
    active_moduli = 0
    characters = 0
    samples = 0
    lane_dense_bits = [0] * len(PINNED_SOURCE_LANE_TOTALS)
    lane_dense_payload_bytes = [0] * len(PINNED_SOURCE_LANE_TOTALS)
    lane_wire_bytes = [0] * len(PINNED_SOURCE_LANE_TOTALS)
    lane_active_moduli = [0] * len(PINNED_SOURCE_LANE_TOTALS)
    for q in range(SOURCE_Q_START, SOURCE_Q_STOP + 1):
        count = primitive_character_count(q, spf)
        if count == 0:
            continue
        sample_count = maximum_t_index(q) + 1
        width = transition_count_width(sample_count)
        width_histogram[width] = width_histogram.get(width, 0) + count
        bits = count * (4 + width)
        pages = (count + PAGE_CHARACTERS - 1) // PAGE_CHARACTERS
        dense_page_bytes = sum(
            _packed_bytes(
                min(PAGE_CHARACTERS, count - page * PAGE_CHARACTERS),
                4 + width,
            )
            for page in range(pages)
        )
        final_dense_bits += bits
        final_wire_bytes += (
            ARTIFACT_HEADER.size
            + pages * PAGE_HEADER.size
            + dense_page_bytes
        )
        final_pages += pages
        active_moduli += 1
        characters += count
        samples += count * sample_count
        for lane_index, (
            _index,
            lane_start,
            lane_stop,
            _cache_bytes,
            _interpolations,
        ) in enumerate(PINNED_SOURCE_LANE_TOTALS):
            active_stop = min(lane_stop, sample_count)
            lane_samples = max(0, active_stop - lane_start)
            if lane_samples == 0:
                continue
            lane_width = transition_count_width(lane_samples)
            lane_dense_bits[lane_index] += count * (4 + lane_width)
            lane_payload = sum(
                _packed_bytes(
                    min(
                        PAGE_CHARACTERS,
                        count - page * PAGE_CHARACTERS,
                    ),
                    4 + lane_width,
                )
                for page in range(pages)
            )
            lane_dense_payload_bytes[lane_index] += lane_payload
            lane_wire_bytes[lane_index] += (
                ARTIFACT_HEADER.size
                + pages * PAGE_HEADER.size
                + lane_payload
            )
            lane_active_moduli[lane_index] += 1
    if (
        characters != SOURCE_CHARACTER_COUNT
        or samples != SOURCE_SAMPLE_COUNT
    ):
        _fail("v3 source projection differs from the pinned source formulas")
    dense_floor = (final_dense_bits + 7) // 8
    lane_floors = [(bits + 7) // 8 for bits in lane_dense_bits]
    pinned_histogram = {
        12: 10_240_064_835,
        13: 14_719_219_258,
        14: 3_478_761_803,
        15: 845_913_314,
        16: 211_464_707,
        17: 52_022_812,
    }
    pinned_lane_floors = [
        51_708_031_776,
        51_708_031_776,
        51_708_031_776,
        51_708_031_776,
        51_310_245_185,
        31_294_728_250,
        17_936_334_940,
        5_860_572_012,
    ]
    if (
        width_histogram != pinned_histogram
        or dense_floor != 62_259_950_420
        or lane_floors != pinned_lane_floors
        or sum(lane_floors) != 313_234_007_491
        or sum(lane_dense_payload_bytes) != 313_234_745_972
    ):
        _fail("v3 dense source projection changed from its reviewed values")
    ambiguity_sensitivities = []
    for numerator, denominator in (
        (0, 1),
        (1, 1_000_000),
        (1, 100_000),
        (1, 10_000),
        (1, 1_000),
    ):
        ambiguous_samples = samples * numerator // denominator
        # Conservative storage sensitivity: every ambiguous sample is a
        # distinct one-sample range in a distinct sparse row.  Real maximal
        # ranges and repeated ranges per character need less row overhead.
        extra = ambiguous_samples * (
            SPARSE_ROW_HEADER.size + AMBIGUITY_RANGE_RECORD.size
        )
        ambiguity_sensitivities.append(
            {
                "density_numerator": numerator,
                "density_denominator": denominator,
                "ambiguous_sample_floor": ambiguous_samples,
                "conservative_extra_bytes_if_each_is_a_distinct_range": (
                    extra
                ),
                "measured_or_expected_density": False,
            }
        )
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_compact_state_v3."
            "source_storage_projection.v1"
        ),
        "schema_version": 1,
        "classification": (
            "exact_formulaic_dense_storage_and_unmeasured_"
            "ambiguity_sensitivities"
        ),
        "q_start": SOURCE_Q_START,
        "q_stop": SOURCE_Q_STOP,
        "active_modulus_count": active_moduli,
        "primitive_character_count": characters,
        "primitive_character_sample_count": samples,
        "final_count_width_histogram": {
            str(width): count
            for width, count in sorted(width_histogram.items())
        },
        "fixed_bits_per_character": 4,
        "final_dense_bit_floor": final_dense_bits,
        "final_dense_byte_floor_without_q_or_page_padding": dense_floor,
        "final_canonical_wire_bytes_without_ambiguity_ranges": (
            final_wire_bytes
        ),
        "final_page_count": final_pages,
        "eight_lane_dense_byte_floors_without_q_or_page_padding": (
            lane_floors
        ),
        "eight_lane_dense_byte_floor_total": sum(lane_floors),
        "eight_lane_dense_payload_bytes_with_per_q_page_padding": (
            lane_dense_payload_bytes
        ),
        "eight_lane_dense_payload_byte_total_with_per_q_page_padding": (
            sum(lane_dense_payload_bytes)
        ),
        "eight_lane_canonical_wire_bytes_without_ambiguity_ranges": (
            lane_wire_bytes
        ),
        "eight_lane_active_modulus_counts": lane_active_moduli,
        "ambiguity_range_sensitivities": ambiguity_sensitivities,
        "exact_bracket_coordinate_debug_sensitivity": {
            "illustrative_bracket_count_not_source_measurement": (
                38_000_000_000_000
            ),
            "record_bytes": DEBUG_BRACKET_RECORD.size,
            "bytes": 38_000_000_000_000 * DEBUG_BRACKET_RECORD.size,
            "source_admission": False,
        },
        "producer_fusion_measured": False,
        "ambiguity_density_measured": False,
        "source_scale_storage_admitted": False,
        "external_atom_discharged": False,
    }


def source_storage_projection_v3() -> dict[str, Any]:
    """Recompute exact dense floors and explicitly unmeasured sensitivities."""

    body = _source_projection_body()
    result = dict(body)
    result["projection_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def require_source_admission_v3() -> NoReturn:
    """Stay fail-closed until physical and analytic premises are realized."""

    _fail(
        "TGDCSB03 source admission is disabled: direct arithmetic-producer "
        "fusion, source-wide interval usefulness, pointwise multiplicity-"
        "preserving bracket lower bounds, exact same-roster Turing totals, "
        "ambiguity refinement, trusted execution, and the physical Lean "
        "realization are not established"
    )


__all__ = [
    "AMBIGUITY_RANGE_RECORD",
    "ARTIFACT_FORMAT_VERSION",
    "ARTIFACT_HEADER",
    "ARTIFACT_MAGIC",
    "ARTIFACT_SCHEMA",
    "DEBUG_BRACKET_FLAG",
    "DEBUG_BRACKET_RECORD",
    "DEFAULT_MAXIMUM_ARTIFACT_BYTES",
    "DEFAULT_MAXIMUM_PAGE_PAYLOAD_BYTES",
    "DirichletCompactStateV3Error",
    "MAXIMUM_ARTIFACT_BYTES",
    "MAXIMUM_LANES",
    "MAXIMUM_PAGE_PAYLOAD_BYTES",
    "PAGE_CHARACTERS",
    "PAGE_HEADER",
    "PRODUCTION_FLAG",
    "SPARSE_ROW_HEADER",
    "V3Header",
    "character_states_from_flat_sign_codes",
    "complete_primitive_roster_sha256_v3",
    "finalize_compact_state_v3_lanes",
    "inspect_compact_state_v3",
    "iter_compact_state_v3",
    "replay_compact_state_v3",
    "replay_exception_artifact_v3",
    "require_source_admission_v3",
    "retire_compact_state_v3",
    "source_storage_projection_v3",
    "transition_count_width",
    "write_completed_real_disk_stream_v3",
    "write_compact_state_v3",
    "write_exception_artifact_v3",
    "write_flat_sign_codes_v3",
]
