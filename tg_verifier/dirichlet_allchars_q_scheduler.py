# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Receipt-bound q permutation for the primitive-only Dirichlet V2 roster.

The all-character CUDA transform is pointwise in ``q``.  Its former
strictly-increasing-q service order was therefore an execution convention,
not part of the mathematical transform.  This module gives that convention
an explicit binary manifest and replaces it with a deterministic
component-signature order that keeps every distinct order-specific
Bluestein object resident until its last use on the exact source roster.

The manifest retains each actual modulus and its exact ordinate-row count.
It commits both the increasing source roster and the execution permutation.
The independent summary replay below checks those commitments, exact q and
ordinate coverage, every input/output frame identity, and the split-cache
accounting.  It does not prove the analytic input intervals, CUDA arithmetic,
zero isolation, a Turing count, or Platt's Theorem 7.1.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import struct
import tempfile
from typing import Any, Iterable, Mapping, NoReturn, Sequence

from tg_verifier.dirichlet_allchars_stage import (
    ALGORITHM_ID,
    COMPLEX_INTERVAL,
    FORMAT_VERSION as TRANSFORM_FORMAT_VERSION,
    INPUT_HEADER,
    INPUT_MAGIC,
    MAX_COMPONENTS,
    MULTIQ_CACHE_ALGORITHM,
    MULTIQ_CACHE_KEY_DOMAIN,
    MULTIQ_ROOT_CATALOG_DOMAIN,
    MULTIQ_ROOT_POOL_ALGORITHM,
    MULTIQ_TOTAL_CACHE_BYTES,
    ORDER_CACHE_CAPACITY_BYTES,
    OUTPUT_HEADER,
    OUTPUT_MAGIC,
    PRIMITIVE_MODULUS_ROSTER_ID,
    PRIMITIVE_MODULUS_ROSTER_VERSION,
    ROOT_POOL_CATALOG_ENTRIES,
    ROOT_POOL_CONVOLUTION_LENGTHS,
    ROOT_POOL_RESERVED_BYTES,
    _next_power_of_two,
    _order_cache_entry_bytes,
    canonical_component_orders,
    has_primitive_character_modulus,
    modulus_butterflies,
)
from tg_verifier.dirichlet_lattice_stage import (
    SOURCE_Q_START,
    SOURCE_Q_STOP,
    SOURCE_SAMPLE_DENOMINATOR,
    SOURCE_SAMPLE_NUMERATOR,
    maximum_t_index,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
SCHEDULER_ALGORITHM_ID = (
    "primitive-v2-component-signature-lexicographic-q-v1"
)
MANIFEST_SCHEMA = (
    "sparkinterval.tg.dirichlet_allchars.q_order_manifest.v1"
)
SUMMARY_SCHEMA = (
    "sparkinterval.tg.dirichlet_allchars."
    "scheduled_multiq_framed_service.v1"
)
PHASE_SUMMARY_SCHEMA = (
    "sparkinterval.tg.dirichlet_allchars."
    "phase_scheduled_multiq_framed_service.v1"
)

MANIFEST_MAGIC = b"TGDQORD1"
MANIFEST_FORMAT_VERSION = 1
CLASSIFICATION_BOUNDED = 0
CLASSIFICATION_FULL_SOURCE = 1
BOUNDED_CLASSIFICATION = (
    "bounded-primitive-v2-conformance-permutation"
)
FULL_SOURCE_CLASSIFICATION = (
    "full-primitive-v2-source-permutation"
)

# magic, format, classification, primitive-roster version, q start, q stop,
# record bytes, q count, row count, increasing-source digest, execution digest
MANIFEST_HEADER = struct.Struct("<8sIIIIIIQQ32s32s")
MANIFEST_RECORD = struct.Struct("<II")
assert MANIFEST_HEADER.size == 112
assert MANIFEST_RECORD.size == 8

SOURCE_ROSTER_DOMAIN = b"TGDQ_SOURCE_ROSTER_V1"
EXECUTION_ORDER_DOMAIN = b"TGDQ_EXECUTION_ORDER_V1"
PHASE_SCHEDULE_DOMAIN = b"TGDQ_PHASE_SCHEDULE_V1"
PINNED_SOURCE_ACTIVE_MODULI = 292_500
PINNED_SOURCE_T_ROWS = 3_637_613_167
PINNED_SOURCE_ROSTER_SHA256 = (
    "d80a78ee36a82e2dab0d783b2c2407eff425a5978edb46585fba09d1ca7d5a2c"
)
PINNED_SOURCE_EXECUTION_SHA256 = (
    "34d633f0e3ed0d9cf3f684199fd2024a82e8027b4fc6733e48040a36007f3acd"
)


class DirichletAllCharsQSchedulerError(RuntimeError):
    """A q-order manifest, scheduled stream, or cache replay failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletAllCharsQSchedulerError(message)


@dataclass(frozen=True, order=True)
class ScheduleRecord:
    q: int
    t_index_count: int

    def packed(self) -> bytes:
        return MANIFEST_RECORD.pack(self.q, self.t_index_count)


@dataclass(frozen=True)
class ParsedScheduleManifest:
    classification: str
    q_start: int
    q_stop: int
    source_records: tuple[ScheduleRecord, ...]
    execution_records: tuple[ScheduleRecord, ...]
    source_roster_sha256: str
    execution_order_sha256: str
    manifest_sha256: str
    raw: bytes

    @property
    def q_count(self) -> int:
        return len(self.execution_records)

    @property
    def t_row_count(self) -> int:
        return sum(record.t_index_count for record in self.execution_records)

    def report(self) -> dict[str, Any]:
        return {
            "schema": MANIFEST_SCHEMA,
            "schema_version": MANIFEST_FORMAT_VERSION,
            "author": AUTHOR,
            "atom_id": ATOM_ID,
            "algorithm_id": SCHEDULER_ALGORITHM_ID,
            "classification": self.classification,
            "primitive_modulus_roster": PRIMITIVE_MODULUS_ROSTER_ID,
            "primitive_modulus_roster_version": (
                PRIMITIVE_MODULUS_ROSTER_VERSION
            ),
            "q_start_inclusive": self.q_start,
            "q_stop_inclusive": self.q_stop,
            "modulus_count": self.q_count,
            "t_index_row_count": self.t_row_count,
            "first_execution_q": self.execution_records[0].q,
            "last_execution_q": self.execution_records[-1].q,
            "source_roster_sha256": self.source_roster_sha256,
            "execution_order_sha256": self.execution_order_sha256,
            "manifest_sha256": self.manifest_sha256,
            "manifest_size_bytes": len(self.raw),
            "source_q_identity_retained": True,
            "source_roster_independently_reconstructed": (
                self.classification == FULL_SOURCE_CLASSIFICATION
            ),
            "external_atom_discharged": False,
        }


@dataclass(frozen=True)
class PhaseScheduleRecord:
    execution_q_index: int
    q: int
    first_t_index: int
    t_index_stop_exclusive: int

    @property
    def t_index_count(self) -> int:
        return self.t_index_stop_exclusive - self.first_t_index

    def packed(self) -> bytes:
        return struct.pack(
            "<IIII",
            self.execution_q_index,
            self.q,
            self.first_t_index,
            self.t_index_stop_exclusive,
        )


@dataclass(frozen=True)
class PhaseScheduleProjection:
    schedule: ParsedScheduleManifest
    phase_plan_sha256: str
    first_t_index: int
    t_index_stop_exclusive: int
    start_execution_q_index: int
    stop_execution_q_index: int
    active_records: tuple[PhaseScheduleRecord, ...]
    phase_schedule_sha256: str

    @property
    def active_modulus_count(self) -> int:
        return len(self.active_records)

    @property
    def t_index_row_count(self) -> int:
        return sum(record.t_index_count for record in self.active_records)


def _bounded_integer(
    value: object,
    *,
    label: str,
    minimum: int,
    maximum: int,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        _fail(f"{label} is outside [{minimum},{maximum}]")
    return value


def phase_schedule_projection(
    manifest: ParsedScheduleManifest | bytes | bytearray | memoryview | Path,
    *,
    phase_plan_sha256: str,
    first_t_index: int,
    t_index_stop_exclusive: int,
    start_execution_q_index: int = 0,
    stop_execution_q_index: int | None = None,
) -> PhaseScheduleProjection:
    """Project an immutable TGDQORD1 onto one exact resident t phase.

    Inactive moduli are skipped, while active moduli retain their parent
    execution order and exact intersection with ``[first, stop)``.  The
    projection is a commitment, not a second roster file, so source runs have
    only one independently pinned q-order artifact.
    """

    schedule = parse_schedule_manifest(
        manifest.raw
        if isinstance(manifest, ParsedScheduleManifest)
        else manifest
    )
    if (
        isinstance(manifest, ParsedScheduleManifest)
        and schedule != manifest
    ):
        _fail("preparsed phase schedule manifest differs from replay")
    return _phase_schedule_projection_from_parsed(
        schedule,
        phase_plan_sha256=phase_plan_sha256,
        first_t_index=first_t_index,
        t_index_stop_exclusive=t_index_stop_exclusive,
        start_execution_q_index=start_execution_q_index,
        stop_execution_q_index=stop_execution_q_index,
    )


def _phase_schedule_projection_from_parsed(
    schedule: ParsedScheduleManifest,
    *,
    phase_plan_sha256: str,
    first_t_index: int,
    t_index_stop_exclusive: int,
    start_execution_q_index: int = 0,
    stop_execution_q_index: int | None = None,
) -> PhaseScheduleProjection:
    """Private fast path for a manifest already replayed by this module."""

    digest = phase_plan_sha256
    if not _digest_is_lower_sha256(digest):
        _fail("phase schedule plan digest is malformed")
    first = _bounded_integer(
        first_t_index,
        label="phase first t index",
        minimum=0,
        maximum=(1 << 32) - 1,
    )
    stop = _bounded_integer(
        t_index_stop_exclusive,
        label="phase stop t index",
        minimum=1,
        maximum=(1 << 32) - 1,
    )
    q_start = _bounded_integer(
        start_execution_q_index,
        label="phase execution q start",
        minimum=0,
        maximum=len(schedule.execution_records),
    )
    q_stop = _bounded_integer(
        (
            len(schedule.execution_records)
            if stop_execution_q_index is None
            else stop_execution_q_index
        ),
        label="phase execution q stop",
        minimum=1,
        maximum=len(schedule.execution_records),
    )
    if first >= stop or q_start >= q_stop:
        _fail("phase schedule geometry is empty")
    selected = schedule.execution_records[q_start:q_stop]
    if max(record.t_index_count for record in selected) < stop:
        _fail("phase schedule stop is unused by every selected modulus")
    active = tuple(
        PhaseScheduleRecord(
            execution_q_index=q_start + offset,
            q=record.q,
            first_t_index=first,
            t_index_stop_exclusive=min(record.t_index_count, stop),
        )
        for offset, record in enumerate(selected)
        if record.t_index_count > first
    )
    if not active:
        _fail("phase schedule has no active modulus")

    commitment = hashlib.sha256(PHASE_SCHEDULE_DOMAIN)
    commitment.update(bytes.fromhex(schedule.manifest_sha256))
    commitment.update(bytes.fromhex(schedule.execution_order_sha256))
    commitment.update(bytes.fromhex(digest))
    commitment.update(struct.pack("<IIII", first, stop, q_start, q_stop))
    for record in active:
        commitment.update(record.packed())
    return PhaseScheduleProjection(
        schedule=schedule,
        phase_plan_sha256=digest,
        first_t_index=first,
        t_index_stop_exclusive=stop,
        start_execution_q_index=q_start,
        stop_execution_q_index=q_stop,
        active_records=active,
        phase_schedule_sha256=commitment.hexdigest(),
    )


def component_signature(q: int) -> tuple[int, ...]:
    """Fixed-width cache-locality signature, followed elsewhere by actual q."""

    descending = tuple(sorted(canonical_component_orders(q), reverse=True))
    if len(descending) > MAX_COMPONENTS:
        _fail("component signature exceeds the fixed format")
    return descending + (0,) * (MAX_COMPONENTS - len(descending))


def execution_sort_key(record: ScheduleRecord) -> tuple[int, ...]:
    return component_signature(record.q) + (record.q,)


def source_schedule_records() -> tuple[ScheduleRecord, ...]:
    records = tuple(
        ScheduleRecord(q, maximum_t_index(q) + 1)
        for q in range(SOURCE_Q_START, SOURCE_Q_STOP + 1)
        if has_primitive_character_modulus(q)
    )
    if (
        len(records) != PINNED_SOURCE_ACTIVE_MODULI
        or sum(record.t_index_count for record in records)
        != PINNED_SOURCE_T_ROWS
    ):
        _fail("primitive-only V2 source roster invariant failed")
    return records


def _digest_records(domain: bytes, records: Iterable[ScheduleRecord]) -> str:
    digest = hashlib.sha256(domain)
    for record in records:
        digest.update(record.packed())
    return digest.hexdigest()


def _validated_source_records(
    records: Sequence[ScheduleRecord],
    *,
    full_source: bool,
) -> tuple[ScheduleRecord, ...]:
    if not records:
        _fail("q-order manifest cannot be empty")
    source = tuple(sorted(records))
    if len({record.q for record in source}) != len(source):
        _fail("q-order manifest contains a duplicate modulus")
    for record in source:
        if (
            not SOURCE_Q_START <= record.q <= SOURCE_Q_STOP
            or not has_primitive_character_modulus(record.q)
            or not 1 <= record.t_index_count
            <= maximum_t_index(record.q) + 1
        ):
            _fail("q-order record is outside the primitive V2 source domain")
    if full_source and source != source_schedule_records():
        _fail("full-source q-order manifest differs from the exact V2 roster")
    return source


def build_schedule_manifest_bytes(
    records: Sequence[ScheduleRecord],
    *,
    full_source: bool = False,
) -> bytes:
    source = _validated_source_records(records, full_source=full_source)
    execution = tuple(sorted(source, key=execution_sort_key))
    source_digest = _digest_records(SOURCE_ROSTER_DOMAIN, source)
    execution_digest = _digest_records(EXECUTION_ORDER_DOMAIN, execution)
    if full_source and (
        source_digest != PINNED_SOURCE_ROSTER_SHA256
        or execution_digest != PINNED_SOURCE_EXECUTION_SHA256
    ):
        _fail("full-source q-order digest differs from its independent pin")
    header = MANIFEST_HEADER.pack(
        MANIFEST_MAGIC,
        MANIFEST_FORMAT_VERSION,
        (
            CLASSIFICATION_FULL_SOURCE
            if full_source
            else CLASSIFICATION_BOUNDED
        ),
        PRIMITIVE_MODULUS_ROSTER_VERSION,
        source[0].q,
        source[-1].q,
        MANIFEST_RECORD.size,
        len(source),
        sum(record.t_index_count for record in source),
        bytes.fromhex(source_digest),
        bytes.fromhex(execution_digest),
    )
    return header + b"".join(record.packed() for record in execution)


def parse_schedule_manifest(
    source: bytes | bytearray | memoryview | Path,
) -> ParsedScheduleManifest:
    raw = (
        source.read_bytes()
        if isinstance(source, Path)
        else bytes(source)
    )
    if len(raw) < MANIFEST_HEADER.size:
        _fail("q-order manifest has a short header")
    (
        magic,
        version,
        classification_id,
        roster_version,
        q_start,
        q_stop,
        record_size,
        q_count,
        t_rows,
        source_digest_raw,
        execution_digest_raw,
    ) = MANIFEST_HEADER.unpack_from(raw)
    if (
        magic != MANIFEST_MAGIC
        or version != MANIFEST_FORMAT_VERSION
        or classification_id
        not in {CLASSIFICATION_BOUNDED, CLASSIFICATION_FULL_SOURCE}
        or roster_version != PRIMITIVE_MODULUS_ROSTER_VERSION
        or record_size != MANIFEST_RECORD.size
        or q_count == 0
        or len(raw) != MANIFEST_HEADER.size + q_count * MANIFEST_RECORD.size
    ):
        _fail("q-order manifest header or size differs")
    execution = tuple(
        ScheduleRecord(*MANIFEST_RECORD.unpack_from(raw, offset))
        for offset in range(
            MANIFEST_HEADER.size, len(raw), MANIFEST_RECORD.size
        )
    )
    full_source = classification_id == CLASSIFICATION_FULL_SOURCE
    source_records = _validated_source_records(
        execution, full_source=full_source
    )
    expected_execution = tuple(
        sorted(source_records, key=execution_sort_key)
    )
    if execution != expected_execution:
        _fail("q-order execution records are not the canonical permutation")
    if (
        q_start != source_records[0].q
        or q_stop != source_records[-1].q
        or t_rows
        != sum(record.t_index_count for record in source_records)
    ):
        _fail("q-order manifest range or row coverage differs")
    source_digest = _digest_records(
        SOURCE_ROSTER_DOMAIN, source_records
    )
    execution_digest = _digest_records(
        EXECUTION_ORDER_DOMAIN, execution
    )
    if (
        source_digest_raw.hex() != source_digest
        or execution_digest_raw.hex() != execution_digest
        or (
            full_source
            and (
                source_digest != PINNED_SOURCE_ROSTER_SHA256
                or execution_digest != PINNED_SOURCE_EXECUTION_SHA256
                or q_count != PINNED_SOURCE_ACTIVE_MODULI
                or t_rows != PINNED_SOURCE_T_ROWS
            )
        )
    ):
        _fail("q-order manifest roster or permutation digest differs")
    return ParsedScheduleManifest(
        classification=(
            FULL_SOURCE_CLASSIFICATION
            if full_source
            else BOUNDED_CLASSIFICATION
        ),
        q_start=q_start,
        q_stop=q_stop,
        source_records=source_records,
        execution_records=execution,
        source_roster_sha256=source_digest,
        execution_order_sha256=execution_digest,
        manifest_sha256=hashlib.sha256(raw).hexdigest(),
        raw=raw,
    )


def _atomic_bytes(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        _fail(f"refusing to replace immutable q-order manifest: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)
        temporary.unlink()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_source_schedule_manifest(path: Path) -> dict[str, Any]:
    raw = build_schedule_manifest_bytes(
        source_schedule_records(), full_source=True
    )
    _atomic_bytes(path, raw)
    return parse_schedule_manifest(raw).report()


def write_bounded_schedule_manifest(
    path: Path,
    records: Sequence[ScheduleRecord],
) -> dict[str, Any]:
    raw = build_schedule_manifest_bytes(records, full_source=False)
    _atomic_bytes(path, raw)
    return parse_schedule_manifest(raw).report()


def _replay_split_cache(
    records: Sequence[ScheduleRecord],
) -> dict[str, int]:
    retained: OrderedDict[int, int] = OrderedDict()
    retained_bytes = 0
    peak_bytes = 0
    peak_total_bytes = 0
    roots: set[int] = set()
    root_retained_bytes = 0
    root_accesses = 0
    root_hits = 0
    root_misses = 0
    root_prepared = 0
    accesses = 0
    hits = 0
    misses = 0
    evictions = 0
    uncached = 0
    prepared = 0
    for record in records:
        active: set[int] = set()
        for length in canonical_component_orders(record.q):
            accesses += 1
            convolution = _next_power_of_two(2 * length - 1)
            if length in retained:
                hits += 1
                retained.move_to_end(length, last=False)
            else:
                misses += 1
                prepared += 2 * length
                root_accesses += 1
                if convolution in roots:
                    root_hits += 1
                else:
                    if convolution not in ROOT_POOL_CONVOLUTION_LENGTHS:
                        _fail("scheduled convolution is outside root catalog")
                    root_misses += 1
                    roots.add(convolution)
                    root_retained_bytes += (
                        2 * (convolution - 1) * COMPLEX_INTERVAL.size
                    )
                    root_prepared += 2 * (convolution - 1)
                peak_total_bytes = max(
                    peak_total_bytes,
                    retained_bytes + root_retained_bytes,
                )
                entry_bytes = _order_cache_entry_bytes(length)
                retain = entry_bytes <= ORDER_CACHE_CAPACITY_BYTES
                while (
                    retain
                    and retained_bytes
                    > ORDER_CACHE_CAPACITY_BYTES - entry_bytes
                ):
                    candidate = next(
                        (
                            key
                            for key in reversed(retained)
                            if key not in active
                        ),
                        None,
                    )
                    if candidate is None:
                        retain = False
                        break
                    retained_bytes -= retained.pop(candidate)
                    evictions += 1
                if retain:
                    retained[length] = entry_bytes
                    retained.move_to_end(length, last=False)
                    retained_bytes += entry_bytes
                    peak_bytes = max(peak_bytes, retained_bytes)
                    peak_total_bytes = max(
                        peak_total_bytes,
                        retained_bytes + root_retained_bytes,
                    )
                else:
                    uncached += 1
            active.add(length)
    return {
        "root_pool_accesses": root_accesses,
        "root_pool_hits": root_hits,
        "root_pool_misses": root_misses,
        "root_pool_retained_entries": len(roots),
        "root_pool_retained_bytes": root_retained_bytes,
        "root_pool_prepared_enclosures": root_prepared,
        "order_cache_accesses": accesses,
        "order_cache_hits": hits,
        "order_cache_misses": misses,
        "order_cache_evictions": evictions,
        "order_cache_uncached_misses": uncached,
        "order_cache_retained_entries": len(retained),
        "order_cache_retained_bytes": retained_bytes,
        "order_cache_peak_retained_bytes": peak_bytes,
        "order_cache_prepared_enclosures": prepared,
        "total_prepared_enclosures": prepared + root_prepared,
        "cache_peak_total_retained_bytes": peak_total_bytes,
    }


def source_schedule_inventory() -> dict[str, Any]:
    source = source_schedule_records()
    execution = tuple(sorted(source, key=execution_sort_key))
    cache = _replay_split_cache(execution)
    distinct_orders = {
        order
        for record in source
        for order in canonical_component_orders(record.q)
    }
    lower_bound = (
        2 * sum(distinct_orders)
        + 2 * sum(length - 1 for length in ROOT_POOL_CONVOLUTION_LENGTHS)
    )
    if (
        cache["order_cache_misses"] != len(distinct_orders)
        or cache["total_prepared_enclosures"] != lower_bound
    ):
        _fail("scheduled source cache no longer attains its cold-cache lower bound")
    result: dict[str, Any] = {
        "schema": (
            "sparkinterval.tg.dirichlet_allchars."
            "q_order_source_inventory.v1"
        ),
        "algorithm_id": SCHEDULER_ALGORITHM_ID,
        "classification": (
            "exact_source_simulation_not_h100_timing_or_atom_closure"
        ),
        "primitive_modulus_roster_version": (
            PRIMITIVE_MODULUS_ROSTER_VERSION
        ),
        "modulus_count": len(source),
        "t_index_row_count": sum(x.t_index_count for x in source),
        "source_roster_sha256": _digest_records(
            SOURCE_ROSTER_DOMAIN, source
        ),
        "execution_order_sha256": _digest_records(
            EXECUTION_ORDER_DOMAIN, execution
        ),
        "first_execution_q": execution[0].q,
        "last_execution_q": execution[-1].q,
        "distinct_component_orders": len(distinct_orders),
        "cold_cache_preparation_lower_bound_enclosures": lower_bound,
        "attains_cold_cache_preparation_lower_bound": True,
        "former_increasing_q_total_prepared_enclosures": 18_106_321_498,
        "saved_prepared_enclosures": 18_106_321_498 - lower_bound,
        "saved_prepared_fraction": (
            (18_106_321_498 - lower_bound) / 18_106_321_498
        ),
        "source_scale_run": False,
        "external_atom_discharged": False,
    }
    result.update(cache)
    return result


def _digest_is_lower_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def validate_scheduled_multiq_framed_summary_commitments(
    summary: Mapping[str, Any],
    *,
    manifest: bytes | bytearray | memoryview | Path,
    maximum_batch_count: int,
    input_stream_sha256: str,
    output_stream_sha256: str,
    require_full_source: bool = False,
) -> dict[str, Any]:
    """Replay schedule/cache/count metadata without retaining either stream.

    Adjacent supervised processes supply the ordered stream digests.  This
    checker independently reconstructs everything else that does not require
    visiting interval payload bytes.  The ordinary summary validator remains
    the stronger bounded-KAT path that also replays every binary interval.
    """

    schedule = parse_schedule_manifest(manifest)
    if (
        not isinstance(require_full_source, bool)
        or (
            require_full_source
            and schedule.classification != FULL_SOURCE_CLASSIFICATION
        )
    ):
        _fail("scheduled commitment replay requires a full-source manifest")
    if (
        isinstance(maximum_batch_count, bool)
        or not isinstance(maximum_batch_count, int)
        or maximum_batch_count <= 0
    ):
        _fail("scheduled commitment replay batch bound must be positive")
    for label, value in (
        ("input stream", input_stream_sha256),
        ("output stream", output_stream_sha256),
    ):
        if not _digest_is_lower_sha256(value):
            _fail(f"scheduled commitment replay {label} digest is malformed")

    cache_keys = {
        "root_pool_accesses",
        "root_pool_hits",
        "root_pool_misses",
        "root_pool_retained_entries",
        "root_pool_retained_bytes",
        "root_pool_prepared_enclosures",
        "order_cache_accesses",
        "order_cache_hits",
        "order_cache_misses",
        "order_cache_evictions",
        "order_cache_uncached_misses",
        "order_cache_retained_entries",
        "order_cache_retained_bytes",
        "order_cache_peak_retained_bytes",
        "order_cache_prepared_enclosures",
        "total_prepared_enclosures",
        "cache_peak_total_retained_bytes",
    }
    digest_fields = {
        "schedule_manifest_sha256",
        "schedule_source_roster_sha256",
        "schedule_execution_order_sha256",
        "order_cache_key_chain_sha256",
        "root_pool_catalog_sha256",
        "input_stream_sha256",
        "output_stream_sha256",
    }
    required = {
        "kind",
        "algorithm",
        "scheduler_algorithm",
        "schedule_classification",
        "cache_algorithm",
        "root_pool_algorithm",
        "maximum_batch_count",
        "cache_capacity_bytes",
        "root_pool_catalog_entries",
        "root_pool_reserved_bytes",
        "order_cache_capacity_bytes",
        "first_q",
        "last_q",
        "modulus_count",
        "scheduled_t_index_rows",
        "frame_count",
        "slice_count",
        "value_count",
        "radix2_butterflies",
        "preparation_nanoseconds",
        "elapsed_nanoseconds",
        *cache_keys,
        *digest_fields,
        "retained_input_frames",
        "retained_output_frames",
    }
    if (
        not isinstance(summary, Mapping)
        or set(summary) != required
        or summary.get("kind") != SUMMARY_SCHEMA
        or summary.get("algorithm") != ALGORITHM_ID
        or summary.get("scheduler_algorithm") != SCHEDULER_ALGORITHM_ID
        or summary.get("schedule_classification")
        != schedule.classification
        or summary.get("cache_algorithm") != MULTIQ_CACHE_ALGORITHM
        or summary.get("root_pool_algorithm")
        != MULTIQ_ROOT_POOL_ALGORITHM
        or not all(
            _digest_is_lower_sha256(summary.get(key))
            for key in digest_fields
        )
    ):
        _fail("scheduled commitment summary schema or algorithm differs")

    expected_root_catalog = hashlib.sha256(MULTIQ_ROOT_CATALOG_DOMAIN)
    for convolution in ROOT_POOL_CONVOLUTION_LENGTHS:
        expected_root_catalog.update(struct.pack("<I", convolution))
    if (
        summary["schedule_manifest_sha256"] != schedule.manifest_sha256
        or summary["schedule_source_roster_sha256"]
        != schedule.source_roster_sha256
        or summary["schedule_execution_order_sha256"]
        != schedule.execution_order_sha256
        or summary["root_pool_catalog_sha256"]
        != expected_root_catalog.hexdigest()
        or summary["input_stream_sha256"] != input_stream_sha256
        or summary["output_stream_sha256"] != output_stream_sha256
    ):
        _fail("scheduled commitment manifest, catalog, or stream digest differs")

    numeric_keys = required - {
        "kind",
        "algorithm",
        "scheduler_algorithm",
        "schedule_classification",
        "cache_algorithm",
        "root_pool_algorithm",
        *digest_fields,
    }
    numeric: dict[str, int] = {}
    for key in numeric_keys:
        value = summary.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            _fail(f"scheduled commitment summary {key} is not nonnegative")
        numeric[key] = value
    if (
        numeric["maximum_batch_count"] != maximum_batch_count
        or numeric["cache_capacity_bytes"] != MULTIQ_TOTAL_CACHE_BYTES
        or numeric["root_pool_catalog_entries"]
        != ROOT_POOL_CATALOG_ENTRIES
        or numeric["root_pool_reserved_bytes"] != ROOT_POOL_RESERVED_BYTES
        or numeric["order_cache_capacity_bytes"]
        != ORDER_CACHE_CAPACITY_BYTES
        or numeric["retained_input_frames"] != 0
        or numeric["retained_output_frames"] != 0
    ):
        _fail("scheduled commitment fixed cache or retention boundary differs")

    order_key_digest = hashlib.sha256(MULTIQ_CACHE_KEY_DOMAIN)
    frame_count = 0
    value_count = 0
    butterfly_count = 0
    for record in schedule.execution_records:
        orders = canonical_component_orders(record.q)
        for length in orders:
            convolution = _next_power_of_two(2 * length - 1)
            order_key_digest.update(struct.pack("<II", length, convolution))
        consumed = 0
        group_order = math.prod(orders)
        while consumed < record.t_index_count:
            batch_count = min(
                maximum_batch_count, record.t_index_count - consumed
            )
            frame_count += 1
            value_count += batch_count * group_order
            butterfly_count += modulus_butterflies(
                record.q, batch_count=batch_count
            )
            consumed += batch_count
    expected_numeric = {
        "first_q": schedule.execution_records[0].q,
        "last_q": schedule.execution_records[-1].q,
        "modulus_count": schedule.q_count,
        "scheduled_t_index_rows": schedule.t_row_count,
        "frame_count": frame_count,
        "slice_count": schedule.t_row_count,
        "value_count": value_count,
        "radix2_butterflies": butterfly_count,
        **_replay_split_cache(schedule.execution_records),
    }
    for key, expected in expected_numeric.items():
        if numeric[key] != expected:
            _fail(f"scheduled commitment summary {key} differs")
    if summary["order_cache_key_chain_sha256"] != order_key_digest.hexdigest():
        _fail("scheduled commitment cache-key chain differs")
    return dict(summary)


def validate_phase_scheduled_multiq_framed_summary_commitments(
    summary: Mapping[str, Any],
    *,
    projection: PhaseScheduleProjection,
    maximum_batch_count: int,
    input_stream_sha256: str,
    output_stream_sha256: str,
) -> dict[str, Any]:
    """Replay one partial-t multi-q service summary from its parent schedule.

    This is the source-scale metadata path: adjacent supervised stages supply
    the two ordered stream digests, while this function reconstructs the
    active-q projection, every frame/count identity, and split-cache behavior
    without retaining the interval payloads.
    """

    if not isinstance(projection, PhaseScheduleProjection):
        _fail("phase commitment replay requires a phase projection")
    if (
        isinstance(maximum_batch_count, bool)
        or not isinstance(maximum_batch_count, int)
        or maximum_batch_count <= 0
    ):
        _fail("phase commitment replay batch bound must be positive")
    for label, value in (
        ("input stream", input_stream_sha256),
        ("output stream", output_stream_sha256),
    ):
        if not _digest_is_lower_sha256(value):
            _fail(f"phase commitment replay {label} digest is malformed")

    cache_keys = {
        "root_pool_accesses",
        "root_pool_hits",
        "root_pool_misses",
        "root_pool_retained_entries",
        "root_pool_retained_bytes",
        "root_pool_prepared_enclosures",
        "order_cache_accesses",
        "order_cache_hits",
        "order_cache_misses",
        "order_cache_evictions",
        "order_cache_uncached_misses",
        "order_cache_retained_entries",
        "order_cache_retained_bytes",
        "order_cache_peak_retained_bytes",
        "order_cache_prepared_enclosures",
        "total_prepared_enclosures",
        "cache_peak_total_retained_bytes",
    }
    digest_fields = {
        "schedule_manifest_sha256",
        "schedule_source_roster_sha256",
        "schedule_execution_order_sha256",
        "phase_plan_sha256",
        "phase_schedule_sha256",
        "order_cache_key_chain_sha256",
        "root_pool_catalog_sha256",
        "input_stream_sha256",
        "output_stream_sha256",
    }
    required = {
        "kind",
        "algorithm",
        "scheduler_algorithm",
        "schedule_classification",
        "cache_algorithm",
        "root_pool_algorithm",
        "maximum_batch_count",
        "cache_capacity_bytes",
        "root_pool_catalog_entries",
        "root_pool_reserved_bytes",
        "order_cache_capacity_bytes",
        "phase_first_t_index",
        "phase_stop_t_index_exclusive",
        "phase_execution_q_start_index",
        "phase_execution_q_stop_index",
        "phase_active_modulus_count",
        "parent_scheduled_t_index_rows",
        "phase_t_index_rows",
        "first_q",
        "last_q",
        "modulus_count",
        "frame_count",
        "slice_count",
        "value_count",
        "radix2_butterflies",
        "preparation_nanoseconds",
        "elapsed_nanoseconds",
        *cache_keys,
        *digest_fields,
        "retained_input_frames",
        "retained_output_frames",
    }
    schedule = projection.schedule
    if (
        not isinstance(summary, Mapping)
        or set(summary) != required
        or summary.get("kind") != PHASE_SUMMARY_SCHEMA
        or summary.get("algorithm") != ALGORITHM_ID
        or summary.get("scheduler_algorithm") != SCHEDULER_ALGORITHM_ID
        or summary.get("schedule_classification")
        != schedule.classification
        or summary.get("cache_algorithm") != MULTIQ_CACHE_ALGORITHM
        or summary.get("root_pool_algorithm")
        != MULTIQ_ROOT_POOL_ALGORITHM
        or not all(
            _digest_is_lower_sha256(summary.get(key))
            for key in digest_fields
        )
    ):
        _fail("phase scheduled commitment schema or algorithm differs")

    expected_root_catalog = hashlib.sha256(MULTIQ_ROOT_CATALOG_DOMAIN)
    for convolution in ROOT_POOL_CONVOLUTION_LENGTHS:
        expected_root_catalog.update(struct.pack("<I", convolution))
    if (
        summary["schedule_manifest_sha256"] != schedule.manifest_sha256
        or summary["schedule_source_roster_sha256"]
        != schedule.source_roster_sha256
        or summary["schedule_execution_order_sha256"]
        != schedule.execution_order_sha256
        or summary["phase_plan_sha256"] != projection.phase_plan_sha256
        or summary["phase_schedule_sha256"]
        != projection.phase_schedule_sha256
        or summary["root_pool_catalog_sha256"]
        != expected_root_catalog.hexdigest()
        or summary["input_stream_sha256"] != input_stream_sha256
        or summary["output_stream_sha256"] != output_stream_sha256
    ):
        _fail("phase scheduled manifest, phase, catalog, or stream digest differs")

    numeric_keys = required - {
        "kind",
        "algorithm",
        "scheduler_algorithm",
        "schedule_classification",
        "cache_algorithm",
        "root_pool_algorithm",
        *digest_fields,
    }
    numeric: dict[str, int] = {}
    for key in numeric_keys:
        value = summary.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            _fail(f"phase scheduled summary {key} is not nonnegative")
        numeric[key] = value
    if (
        numeric["maximum_batch_count"] != maximum_batch_count
        or numeric["cache_capacity_bytes"] != MULTIQ_TOTAL_CACHE_BYTES
        or numeric["root_pool_catalog_entries"]
        != ROOT_POOL_CATALOG_ENTRIES
        or numeric["root_pool_reserved_bytes"] != ROOT_POOL_RESERVED_BYTES
        or numeric["order_cache_capacity_bytes"]
        != ORDER_CACHE_CAPACITY_BYTES
        or numeric["retained_input_frames"] != 0
        or numeric["retained_output_frames"] != 0
    ):
        _fail("phase scheduled fixed cache or retention boundary differs")

    order_key_digest = hashlib.sha256(MULTIQ_CACHE_KEY_DOMAIN)
    frame_count = 0
    value_count = 0
    butterfly_count = 0
    cache_records: list[ScheduleRecord] = []
    for record in projection.active_records:
        orders = canonical_component_orders(record.q)
        for length in orders:
            convolution = _next_power_of_two(2 * length - 1)
            order_key_digest.update(struct.pack("<II", length, convolution))
        consumed = 0
        group_order = math.prod(orders)
        while consumed < record.t_index_count:
            batch_count = min(
                maximum_batch_count, record.t_index_count - consumed
            )
            frame_count += 1
            value_count += batch_count * group_order
            butterfly_count += modulus_butterflies(
                record.q, batch_count=batch_count
            )
            consumed += batch_count
        cache_records.append(ScheduleRecord(record.q, record.t_index_count))
    expected_numeric = {
        "phase_first_t_index": projection.first_t_index,
        "phase_stop_t_index_exclusive": (
            projection.t_index_stop_exclusive
        ),
        "phase_execution_q_start_index": (
            projection.start_execution_q_index
        ),
        "phase_execution_q_stop_index": projection.stop_execution_q_index,
        "phase_active_modulus_count": projection.active_modulus_count,
        "parent_scheduled_t_index_rows": schedule.t_row_count,
        "phase_t_index_rows": projection.t_index_row_count,
        "first_q": projection.active_records[0].q,
        "last_q": projection.active_records[-1].q,
        "modulus_count": projection.active_modulus_count,
        "frame_count": frame_count,
        "slice_count": projection.t_index_row_count,
        "value_count": value_count,
        "radix2_butterflies": butterfly_count,
        **_replay_split_cache(cache_records),
    }
    for key, expected in expected_numeric.items():
        if numeric[key] != expected:
            _fail(f"phase scheduled summary {key} differs")
    if summary["order_cache_key_chain_sha256"] != order_key_digest.hexdigest():
        _fail("phase scheduled cache-key chain differs")
    return dict(summary)


def validate_scheduled_multiq_framed_summary(
    summary: Mapping[str, Any],
    *,
    manifest: bytes | bytearray | memoryview | Path,
    input_stream: bytes,
    output_stream: bytes,
    require_full_source: bool = False,
) -> dict[str, Any]:
    """Independently replay scheduled coverage, frames, and split-cache stats."""

    schedule = parse_schedule_manifest(manifest)
    if (
        not isinstance(require_full_source, bool)
        or (
            require_full_source
            and schedule.classification != FULL_SOURCE_CLASSIFICATION
        )
    ):
        _fail("scheduled replay requires a full-source manifest")
    cache_keys = {
        "root_pool_accesses",
        "root_pool_hits",
        "root_pool_misses",
        "root_pool_retained_entries",
        "root_pool_retained_bytes",
        "root_pool_prepared_enclosures",
        "order_cache_accesses",
        "order_cache_hits",
        "order_cache_misses",
        "order_cache_evictions",
        "order_cache_uncached_misses",
        "order_cache_retained_entries",
        "order_cache_retained_bytes",
        "order_cache_peak_retained_bytes",
        "order_cache_prepared_enclosures",
        "total_prepared_enclosures",
        "cache_peak_total_retained_bytes",
    }
    required = {
        "kind",
        "algorithm",
        "scheduler_algorithm",
        "schedule_classification",
        "schedule_manifest_sha256",
        "schedule_source_roster_sha256",
        "schedule_execution_order_sha256",
        "cache_algorithm",
        "root_pool_algorithm",
        "maximum_batch_count",
        "cache_capacity_bytes",
        "root_pool_catalog_entries",
        "root_pool_reserved_bytes",
        "order_cache_capacity_bytes",
        "first_q",
        "last_q",
        "modulus_count",
        "scheduled_t_index_rows",
        "frame_count",
        "slice_count",
        "value_count",
        "radix2_butterflies",
        "preparation_nanoseconds",
        "elapsed_nanoseconds",
        *cache_keys,
        "order_cache_key_chain_sha256",
        "root_pool_catalog_sha256",
        "retained_input_frames",
        "retained_output_frames",
        "input_stream_sha256",
        "output_stream_sha256",
    }
    if (
        not isinstance(summary, Mapping)
        or set(summary) != required
        or summary.get("kind") != SUMMARY_SCHEMA
        or summary.get("algorithm") != ALGORITHM_ID
        or summary.get("scheduler_algorithm") != SCHEDULER_ALGORITHM_ID
        or summary.get("schedule_classification")
        != schedule.classification
        or summary.get("cache_algorithm") != MULTIQ_CACHE_ALGORITHM
        or summary.get("root_pool_algorithm")
        != MULTIQ_ROOT_POOL_ALGORITHM
    ):
        _fail("scheduled multi-q summary schema or algorithm differs")
    digest_fields = (
        "schedule_manifest_sha256",
        "schedule_source_roster_sha256",
        "schedule_execution_order_sha256",
        "order_cache_key_chain_sha256",
        "root_pool_catalog_sha256",
        "input_stream_sha256",
        "output_stream_sha256",
    )
    if not all(_digest_is_lower_sha256(summary.get(key)) for key in digest_fields):
        _fail("scheduled multi-q summary contains a malformed digest")
    expected_root_catalog = hashlib.sha256(MULTIQ_ROOT_CATALOG_DOMAIN)
    for convolution in ROOT_POOL_CONVOLUTION_LENGTHS:
        expected_root_catalog.update(struct.pack("<I", convolution))
    if (
        summary["schedule_manifest_sha256"] != schedule.manifest_sha256
        or summary["schedule_source_roster_sha256"]
        != schedule.source_roster_sha256
        or summary["schedule_execution_order_sha256"]
        != schedule.execution_order_sha256
        or summary["root_pool_catalog_sha256"]
        != expected_root_catalog.hexdigest()
        or summary["input_stream_sha256"]
        != hashlib.sha256(input_stream).hexdigest()
        or summary["output_stream_sha256"]
        != hashlib.sha256(output_stream).hexdigest()
    ):
        _fail("scheduled multi-q manifest, catalog, or stream digest differs")
    numeric_keys = required - {
        "kind",
        "algorithm",
        "scheduler_algorithm",
        "schedule_classification",
        "cache_algorithm",
        "root_pool_algorithm",
        *digest_fields,
    }
    numeric: dict[str, int] = {}
    for key in numeric_keys:
        value = summary.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            _fail(f"scheduled multi-q summary {key} is not nonnegative")
        numeric[key] = value
    if (
        numeric["maximum_batch_count"] == 0
        or numeric["cache_capacity_bytes"] != MULTIQ_TOTAL_CACHE_BYTES
        or numeric["root_pool_catalog_entries"]
        != ROOT_POOL_CATALOG_ENTRIES
        or numeric["root_pool_reserved_bytes"] != ROOT_POOL_RESERVED_BYTES
        or numeric["order_cache_capacity_bytes"]
        != ORDER_CACHE_CAPACITY_BYTES
        or numeric["retained_input_frames"] != 0
        or numeric["retained_output_frames"] != 0
    ):
        _fail("scheduled multi-q fixed cache or retention boundary differs")

    expected_cache = _replay_split_cache(schedule.execution_records)
    order_key_digest = hashlib.sha256(MULTIQ_CACHE_KEY_DOMAIN)
    input_offset = 0
    output_offset = 0
    frame_count = 0
    slice_count = 0
    value_count_total = 0
    butterfly_total = 0
    elapsed_total = 0
    first_q = schedule.execution_records[0].q
    last_q = schedule.execution_records[-1].q
    for record in schedule.execution_records:
        orders = canonical_component_orders(record.q)
        for length in orders:
            convolution = _next_power_of_two(2 * length - 1)
            order_key_digest.update(struct.pack("<II", length, convolution))
        consumed_rows = 0
        expected_first = 0
        while consumed_rows < record.t_index_count:
            if len(input_stream) - input_offset < INPUT_HEADER.size:
                _fail("scheduled input stream is truncated before coverage")
            header = INPUT_HEADER.unpack_from(input_stream, input_offset)
            (
                magic,
                version,
                q,
                component_count,
                batch_count,
                group_order,
                first_t,
                denominator,
                step,
                values,
                reserved,
            ) = header
            expected_group_order = math.prod(orders)
            if (
                magic != INPUT_MAGIC
                or version != TRANSFORM_FORMAT_VERSION
                or q != record.q
                or component_count != len(orders)
                or not 1 <= batch_count <= numeric["maximum_batch_count"]
                or group_order != expected_group_order
                or first_t != expected_first
                or denominator != SOURCE_SAMPLE_DENOMINATOR
                or step != SOURCE_SAMPLE_NUMERATOR
                or values != batch_count * expected_group_order
                or reserved != 0
                or consumed_rows + batch_count > record.t_index_count
            ):
                _fail("scheduled input identity, order, or coverage differs")
            input_size = INPUT_HEADER.size + values * COMPLEX_INTERVAL.size
            if input_offset + input_size > len(input_stream):
                _fail("scheduled input values are truncated")
            for index in range(values):
                endpoints = COMPLEX_INTERVAL.unpack_from(
                    input_stream,
                    input_offset
                    + INPUT_HEADER.size
                    + index * COMPLEX_INTERVAL.size,
                )
                if not (
                    all(math.isfinite(value) for value in endpoints)
                    and endpoints[0] <= endpoints[1]
                    and endpoints[2] <= endpoints[3]
                ):
                    _fail("scheduled input contains a malformed interval")

            if len(output_stream) - output_offset < OUTPUT_HEADER.size:
                _fail("scheduled output stream is truncated before coverage")
            output_header = OUTPUT_HEADER.unpack_from(
                output_stream, output_offset
            )
            expected_butterflies = modulus_butterflies(
                record.q, batch_count=batch_count
            )
            if (
                output_header[:7]
                != (
                    OUTPUT_MAGIC,
                    TRANSFORM_FORMAT_VERSION,
                    record.q,
                    len(orders),
                    batch_count,
                    expected_group_order,
                    values,
                )
                or output_header[7] != expected_butterflies
            ):
                _fail("scheduled output frame identity differs")
            output_size = (
                OUTPUT_HEADER.size + values * COMPLEX_INTERVAL.size
            )
            if output_offset + output_size > len(output_stream):
                _fail("scheduled output values are truncated")
            for index in range(values):
                endpoints = COMPLEX_INTERVAL.unpack_from(
                    output_stream,
                    output_offset
                    + OUTPUT_HEADER.size
                    + index * COMPLEX_INTERVAL.size,
                )
                if not (
                    all(math.isfinite(value) for value in endpoints)
                    and endpoints[0] <= endpoints[1]
                    and endpoints[2] <= endpoints[3]
                ):
                    _fail("scheduled output contains a malformed interval")

            consumed_rows += batch_count
            expected_first += batch_count * SOURCE_SAMPLE_NUMERATOR
            input_offset += input_size
            output_offset += output_size
            frame_count += 1
            slice_count += batch_count
            value_count_total += values
            butterfly_total += expected_butterflies
            elapsed_total += output_header[8]

    if (
        input_offset != len(input_stream)
        or output_offset != len(output_stream)
        or frame_count == 0
    ):
        _fail("scheduled streams contain trailing bytes or no frames")
    expected_numeric = {
        "first_q": first_q,
        "last_q": last_q,
        "modulus_count": schedule.q_count,
        "scheduled_t_index_rows": schedule.t_row_count,
        "frame_count": frame_count,
        "slice_count": slice_count,
        "value_count": value_count_total,
        "radix2_butterflies": butterfly_total,
        "elapsed_nanoseconds": elapsed_total,
        **expected_cache,
    }
    for key, expected in expected_numeric.items():
        if numeric[key] != expected:
            _fail(f"scheduled multi-q summary {key} differs")
    if summary["order_cache_key_chain_sha256"] != order_key_digest.hexdigest():
        _fail("scheduled multi-q cache-key chain differs")
    return dict(summary)


__all__ = [
    "BOUNDED_CLASSIFICATION",
    "DirichletAllCharsQSchedulerError",
    "FULL_SOURCE_CLASSIFICATION",
    "MANIFEST_FORMAT_VERSION",
    "MANIFEST_HEADER",
    "MANIFEST_MAGIC",
    "MANIFEST_RECORD",
    "PINNED_SOURCE_ACTIVE_MODULI",
    "PINNED_SOURCE_EXECUTION_SHA256",
    "PINNED_SOURCE_ROSTER_SHA256",
    "PINNED_SOURCE_T_ROWS",
    "PHASE_SCHEDULE_DOMAIN",
    "PHASE_SUMMARY_SCHEMA",
    "PhaseScheduleProjection",
    "PhaseScheduleRecord",
    "ParsedScheduleManifest",
    "SCHEDULER_ALGORITHM_ID",
    "SUMMARY_SCHEMA",
    "ScheduleRecord",
    "build_schedule_manifest_bytes",
    "component_signature",
    "execution_sort_key",
    "parse_schedule_manifest",
    "phase_schedule_projection",
    "source_schedule_inventory",
    "source_schedule_records",
    "validate_phase_scheduled_multiq_framed_summary_commitments",
    "validate_scheduled_multiq_framed_summary",
    "validate_scheduled_multiq_framed_summary_commitments",
    "write_bounded_schedule_manifest",
    "write_source_schedule_manifest",
]
