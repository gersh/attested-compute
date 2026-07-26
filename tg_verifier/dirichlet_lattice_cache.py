# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Authenticated t-major cache geometry for Platt's Hurwitz lattice.

The large-q CUDA path needs the same 2048 by 16 Hurwitz lattice at a fixed
ordinate for every active modulus.  A q-major input repeats those cells about
5.180 PB times.  This module defines a complete representation of that
large-q main positive grid in which every lattice cell is stored once,
authenticates one bounded 1 MiB row before exposing it, and assigns complete
storage shards to deterministic work-balanced execution lanes.  It does not
add the finer interpolation, exception, endpoint, or Turing grids.

This is deliberately a transport component.  Chunk hashes do not prove that a
binary64 rectangle encloses a Hurwitz-zeta value.  The only producer promoted
from ``synthetic`` to ``replayed_lattice_certificate`` below first invokes the
existing pinned-Arb higher-precision replay for every source certificate that
it repacks.  Neither route performs zero isolation, a Turing count, or the
Lean realization of Platt's Theorem 7.1.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import tempfile
import time
from typing import Any, Iterable, Iterator, Mapping, NoReturn, Sequence

from tg_verifier.dirichlet_lattice_stage import (
    INPUT_HEADER as LEGACY_INPUT_HEADER,
    INPUT_MAGIC as LEGACY_INPUT_MAGIC,
    LATTICE_CELL,
    LATTICE_ROWS,
    SOURCE_MAX_T_INDEX,
    SOURCE_SAMPLE_DENOMINATOR,
    SOURCE_SAMPLE_NUMERATOR,
    TAYLOR_COLUMNS,
    TAYLOR_DEGREE,
    source_work,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
SOURCE_URL = "https://arxiv.org/abs/1305.3087v1"
ALGORITHM_ID = "platt-dirichlet-t-major-hurwitz-cache-v1"
PLAN_SCHEMA = "sparkinterval.tg.dirichlet_lattice_cache.plan.v1"
CATALOG_SCHEMA = "sparkinterval.tg.dirichlet_lattice_cache.catalog.v1"
PACK_RECEIPT_SCHEMA = "sparkinterval.tg.dirichlet_lattice_cache.pack_receipt.v1"

FORMAT_VERSION = 1
SOURCE_M = 4
SOURCE_T_INDEX_STOP = SOURCE_MAX_T_INDEX + 1
DEFAULT_T_INDICES_PER_SHARD = 128
MAXIMUM_T_INDICES_PER_SHARD = 512
DEFAULT_BROADCAST_LANES = 8

CELLS_PER_T_INDEX = LATTICE_ROWS * TAYLOR_COLUMNS
ROW_PAYLOAD_BYTES = CELLS_PER_T_INDEX * LATTICE_CELL.size
SOURCE_LATTICE_CELLS = SOURCE_T_INDEX_STOP * CELLS_PER_T_INDEX
SOURCE_CACHE_PAYLOAD_BYTES = SOURCE_T_INDEX_STOP * ROW_PAYLOAD_BYTES
OLD_Q_MAJOR_LATTICE_BYTES = 5_139_124_740_685_824
OLD_SEEDED_COMPACT_INPUT_BYTES = 5_180_404_381_680_112
NON_LATTICE_COMPACT_INPUT_BYTES = (
    OLD_SEEDED_COMPACT_INPUT_BYTES - OLD_Q_MAJOR_LATTICE_BYTES
)
T_MAJOR_COMPACT_INPUT_BYTES = (
    NON_LATTICE_COMPACT_INPUT_BYTES + SOURCE_CACHE_PAYLOAD_BYTES
)

PRODUCER_SYNTHETIC = 0
PRODUCER_REPLAYED_LATTICE_CERTIFICATE = 1

HEADER_MAGIC = b"TGDLTCH1"
ROW_MAGIC = b"TGDLTCR1"
FOOTER_MAGIC = b"TGDLTCF1"

# Header: fixed lattice/source geometry, storage-shard identity, generation
# precision (zero for synthetic data), and binary plan/descriptor hashes.
HEADER = struct.Struct("<8sIIIIIIIIQQQQIIQQ32s32s")
ROW_HEADER = struct.Struct("<8sIIQQQ32s")
FOOTER = struct.Struct("<8sIIQQQ32s32s")

assert HEADER.size == 160
assert ROW_HEADER.size == 72
assert FOOTER.size == 104
assert ROW_PAYLOAD_BYTES == 1_048_576

ROW_DOMAIN = b"sparkinterval/dirichlet-lattice-cache/row/v1\0"
ROOT_DOMAIN = b"sparkinterval/dirichlet-lattice-cache/root/v1\0"
DESCRIPTOR_DOMAIN = b"sparkinterval/dirichlet-lattice-cache/descriptor/v1\0"


class DirichletLatticeCacheError(RuntimeError):
    """A cache plan, shard, source binding, or replay failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletLatticeCacheError(message)


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _sha256_regular_file_nofollow(path: Path) -> tuple[str, int]:
    """Hash one regular file without accepting a symbolic-link substitution."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletLatticeCacheError(
            "cannot open cache identity file without following links"
        ) from error
    digest = hashlib.sha256()
    size = 0
    with os.fdopen(descriptor, "rb") as source:
        file_status = os.fstat(source.fileno())
        if not stat.S_ISREG(file_status.st_mode):
            _fail("cache identity path is not a regular file")
        while block := source.read(1024 * 1024):
            digest.update(block)
            size += len(block)
        if size != file_status.st_size:
            _fail("cache identity file changed while hashing")
    return digest.hexdigest(), size


def _lower_sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} is not lowercase SHA-256")
    return value


def _atomic_bytes(path: Path, raw: bytes) -> None:
    if path.exists():
        _fail(f"refusing to replace immutable output: {path}")
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
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class CacheShard:
    index: int
    t_index_start: int
    t_index_stop: int

    @property
    def t_index_count(self) -> int:
        return self.t_index_stop - self.t_index_start

    @property
    def lattice_cells(self) -> int:
        return self.t_index_count * CELLS_PER_T_INDEX

    @property
    def payload_bytes(self) -> int:
        return self.t_index_count * ROW_PAYLOAD_BYTES

    @property
    def artifact_bytes(self) -> int:
        return (
            HEADER.size
            + self.t_index_count * (ROW_HEADER.size + ROW_PAYLOAD_BYTES)
            + FOOTER.size
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "shard_index": self.index,
            "t_index_start_inclusive": self.t_index_start,
            "t_index_stop_exclusive": self.t_index_stop,
            "t_index_count": self.t_index_count,
            "lattice_cells": self.lattice_cells,
            "payload_bytes": self.payload_bytes,
            "artifact_bytes": self.artifact_bytes,
        }


def cache_shard_filename(index: int) -> str:
    if type(index) is not int or index < 0:
        _fail("cache shard index must be nonnegative")
    return f"lattice-shard-{index:04d}.bin"


def source_cache_plan(
    *,
    t_index_stop_exclusive: int = SOURCE_T_INDEX_STOP,
    t_indices_per_shard: int = DEFAULT_T_INDICES_PER_SHARD,
) -> dict[str, Any]:
    """Return the canonical storage plan or an explicitly labelled prefix KAT."""

    if (
        type(t_index_stop_exclusive) is not int
        or not 1 <= t_index_stop_exclusive <= SOURCE_T_INDEX_STOP
    ):
        _fail("cache t-index stop is outside the source grid")
    if (
        type(t_indices_per_shard) is not int
        or not 1 <= t_indices_per_shard <= MAXIMUM_T_INDICES_PER_SHARD
    ):
        _fail("cache shard span is outside its fixed bound")
    shards = tuple(
        CacheShard(index, start, min(start + t_indices_per_shard, t_index_stop_exclusive))
        for index, start in enumerate(
            range(0, t_index_stop_exclusive, t_indices_per_shard)
        )
    )
    full_main_grid = (
        t_index_stop_exclusive == SOURCE_T_INDEX_STOP
        and t_indices_per_shard == DEFAULT_T_INDICES_PER_SHARD
    )
    body: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "source": SOURCE_URL,
        "classification": (
            "complete_large_q_main_grid_storage_geometry_not_execution_evidence"
            if full_main_grid
            else "bounded_prefix_conformance_geometry_not_source_evidence"
        ),
        "parameters": {
            "M": SOURCE_M,
            "D": LATTICE_ROWS,
            "taylor_degree_N": TAYLOR_DEGREE,
            "taylor_columns": TAYLOR_COLUMNS,
            "positive_t_step": [
                SOURCE_SAMPLE_NUMERATOR,
                SOURCE_SAMPLE_DENOMINATOR,
            ],
            "t_index_start_inclusive": 0,
            "t_index_stop_exclusive": t_index_stop_exclusive,
            "t_indices_per_storage_shard": t_indices_per_shard,
        },
        "storage": {
            "shard_count": len(shards),
            "row_payload_bytes": ROW_PAYLOAD_BYTES,
            "lattice_cells": sum(shard.lattice_cells for shard in shards),
            "payload_bytes": sum(shard.payload_bytes for shard in shards),
            "artifact_bytes": sum(shard.artifact_bytes for shard in shards),
            "authentication_policy": (
                "optional whole-file SHA-256 before parsing, then one "
                "domain-separated 1-MiB row hash before each row is exposed"
            ),
        },
        "storage_shards": [shard.to_dict() for shard in shards],
        "complete_large_q_main_grid_geometry": full_main_grid,
        "excluded_grids": [
            "interpolation upsampling",
            "endpoint padding and shifted exception windows",
            "paired Turing windows",
        ],
        "external_atom_discharged": False,
    }
    body["plan_sha256"] = sha256_bytes(canonical_json_bytes(body))
    return body


def _validated_plan(plan: object) -> dict[str, Any]:
    if not isinstance(plan, dict):
        _fail("cache plan is not an object")
    parameters = plan.get("parameters")
    if not isinstance(parameters, dict):
        _fail("cache plan parameters are missing")
    expected = source_cache_plan(
        t_index_stop_exclusive=parameters.get("t_index_stop_exclusive"),
        t_indices_per_shard=parameters.get("t_indices_per_storage_shard"),
    )
    if plan != expected:
        _fail("cache plan differs from the canonical deterministic plan")
    return expected


def _plan_shard(plan: dict[str, Any], shard_index: int) -> CacheShard:
    _validated_plan(plan)
    rows = plan["storage_shards"]
    if type(shard_index) is not int or not 0 <= shard_index < len(rows):
        _fail("cache shard index is outside the plan")
    row = rows[shard_index]
    return CacheShard(
        index=row["shard_index"],
        t_index_start=row["t_index_start_inclusive"],
        t_index_stop=row["t_index_stop_exclusive"],
    )


def _descriptor_bytes(plan: dict[str, Any], shard: CacheShard) -> bytes:
    return canonical_json_bytes(
        {
            "algorithm_id": ALGORITHM_ID,
            "plan_sha256": plan["plan_sha256"],
            "shard": shard.to_dict(),
            "filename": cache_shard_filename(shard.index),
        }
    )


def _descriptor_digest(plan: dict[str, Any], shard: CacheShard) -> bytes:
    digest = hashlib.sha256(DESCRIPTOR_DOMAIN)
    digest.update(_descriptor_bytes(plan, shard))
    return digest.digest()


@lru_cache(maxsize=1)
def _source_residue_prefix() -> tuple[int, ...]:
    return source_work().prefix_residue_counts


def broadcast_plan(
    plan: Mapping[str, Any],
    *,
    lane_count: int = DEFAULT_BROADCAST_LANES,
) -> dict[str, Any]:
    """Assign complete storage shards to contiguous, work-balanced t lanes.

    Each lattice row belongs to exactly one lane.  Within a lane the row can be
    retained and broadcast to every active q stream before advancing t.
    """

    canonical = _validated_plan(dict(plan))
    shards = [
        _plan_shard(canonical, index)
        for index in range(canonical["storage"]["shard_count"])
    ]
    if type(lane_count) is not int or not 1 <= lane_count <= len(shards):
        _fail("broadcast lane count must fit the storage shard count")
    prefix = _source_residue_prefix()
    stops = [0, *(shard.t_index_stop for shard in shards)]
    weights = [prefix[stop] for stop in stops]
    total = weights[-1]
    boundaries = [0]
    for lane in range(1, lane_count):
        target = total * lane // lane_count
        insertion = bisect_left(weights, target, boundaries[-1] + 1)
        maximum_boundary = len(shards) - (lane_count - lane)
        candidates = {
            min(max(insertion - 1, boundaries[-1] + 1), maximum_boundary),
            min(max(insertion, boundaries[-1] + 1), maximum_boundary),
        }
        boundary = min(
            candidates,
            key=lambda index: (abs(weights[index] - target), index),
        )
        boundaries.append(boundary)
    boundaries.append(len(shards))

    lanes: list[dict[str, Any]] = []
    for lane, (first_shard, stop_shard) in enumerate(
        zip(boundaries, boundaries[1:])
    ):
        t_start = shards[first_shard].t_index_start
        t_stop = shards[stop_shard - 1].t_index_stop
        lanes.append(
            {
                "lane_index": lane,
                "storage_shard_start_inclusive": first_shard,
                "storage_shard_stop_exclusive": stop_shard,
                "t_index_start_inclusive": t_start,
                "t_index_stop_exclusive": t_stop,
                "cache_payload_bytes": (t_stop - t_start) * ROW_PAYLOAD_BYTES,
                "residue_interpolations": prefix[t_stop] - prefix[t_start],
                "scheduling_note": (
                    "load each t-major row once in this lane and broadcast it "
                    "across the lane's active modulus streams"
                ),
            }
        )
    result: dict[str, Any] = {
        "schema": "sparkinterval.tg.dirichlet_lattice_cache.broadcast_plan.v1",
        "schema_version": 1,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "deterministic_work_assignment_not_h100_execution_evidence"
        ),
        "storage_plan_sha256": canonical["plan_sha256"],
        "lane_count": lane_count,
        "lanes": lanes,
        "totals": {
            "storage_shards": len(shards),
            "t_indices": canonical["parameters"]["t_index_stop_exclusive"],
            "cache_payload_bytes": sum(
                lane["cache_payload_bytes"] for lane in lanes
            ),
            "residue_interpolations": sum(
                lane["residue_interpolations"] for lane in lanes
            ),
        },
        "cuda_broadcaster_integrated": False,
        "external_atom_discharged": False,
    }
    result["broadcast_plan_sha256"] = sha256_bytes(canonical_json_bytes(result))
    return result


def _row_hash(
    plan_digest: bytes,
    descriptor_digest: bytes,
    t_index: int,
    payload: bytes,
) -> bytes:
    digest = hashlib.sha256(ROW_DOMAIN)
    digest.update(plan_digest)
    digest.update(descriptor_digest)
    digest.update(struct.pack("<QQQ", t_index, CELLS_PER_T_INDEX, len(payload)))
    digest.update(payload)
    return digest.digest()


@dataclass(frozen=True)
class CacheHeader:
    producer_kind: int
    shard_index: int
    shard_count: int
    t_index_start: int
    t_index_stop: int
    generation_precision_bits: int
    union_precision_bits: int
    plan_sha256: str
    descriptor_sha256: str

    @property
    def t_index_count(self) -> int:
        return self.t_index_stop - self.t_index_start


def _header_bytes(
    plan: dict[str, Any],
    shard: CacheShard,
    *,
    producer_kind: int,
    generation_precision_bits: int,
    union_precision_bits: int,
) -> bytes:
    return HEADER.pack(
        HEADER_MAGIC,
        FORMAT_VERSION,
        SOURCE_M,
        LATTICE_ROWS,
        TAYLOR_COLUMNS,
        LATTICE_CELL.size,
        shard.index,
        plan["storage"]["shard_count"],
        producer_kind,
        shard.t_index_start,
        shard.t_index_stop,
        SOURCE_SAMPLE_NUMERATOR,
        SOURCE_SAMPLE_DENOMINATOR,
        generation_precision_bits,
        union_precision_bits,
        shard.t_index_count,
        0,
        bytes.fromhex(plan["plan_sha256"]),
        _descriptor_digest(plan, shard),
    )


def _unpack_header(
    raw: bytes,
    *,
    expected_plan: dict[str, Any],
    expected_shard_index: int,
) -> CacheHeader:
    if len(raw) != HEADER.size:
        _fail("short lattice-cache header")
    (
        magic,
        version,
        m,
        rows,
        columns,
        cell_size,
        shard_index,
        shard_count,
        producer_kind,
        t_start,
        t_stop,
        step_numerator,
        step_denominator,
        generation_precision,
        union_precision,
        record_count,
        reserved,
        plan_digest,
        descriptor_digest,
    ) = HEADER.unpack(raw)
    shard = _plan_shard(expected_plan, expected_shard_index)
    if (
        magic != HEADER_MAGIC
        or version != FORMAT_VERSION
        or m != SOURCE_M
        or rows != LATTICE_ROWS
        or columns != TAYLOR_COLUMNS
        or cell_size != LATTICE_CELL.size
        or shard_index != shard.index
        or shard_count != expected_plan["storage"]["shard_count"]
        or producer_kind
        not in (PRODUCER_SYNTHETIC, PRODUCER_REPLAYED_LATTICE_CERTIFICATE)
        or t_start != shard.t_index_start
        or t_stop != shard.t_index_stop
        or step_numerator != SOURCE_SAMPLE_NUMERATOR
        or step_denominator != SOURCE_SAMPLE_DENOMINATOR
        or record_count != shard.t_index_count
        or reserved
        or plan_digest != bytes.fromhex(expected_plan["plan_sha256"])
        or descriptor_digest != _descriptor_digest(expected_plan, shard)
    ):
        _fail("lattice-cache header or plan binding differs")
    if producer_kind == PRODUCER_SYNTHETIC:
        if generation_precision or union_precision:
            _fail("synthetic cache header carries an analytic precision")
    elif generation_precision < 128 or union_precision != generation_precision + 64:
        _fail("replayed cache header has an invalid generation precision")
    return CacheHeader(
        producer_kind=producer_kind,
        shard_index=shard_index,
        shard_count=shard_count,
        t_index_start=t_start,
        t_index_stop=t_stop,
        generation_precision_bits=generation_precision,
        union_precision_bits=union_precision,
        plan_sha256=plan_digest.hex(),
        descriptor_sha256=descriptor_digest.hex(),
    )


def _write_cache_artifact(
    path: Path,
    *,
    plan: dict[str, Any],
    shard_index: int,
    producer_kind: int,
    generation_precision_bits: int,
    union_precision_bits: int,
    row_payloads: Iterable[tuple[int, bytes]],
) -> dict[str, Any]:
    plan = _validated_plan(plan)
    shard = _plan_shard(plan, shard_index)
    if path.exists():
        _fail(f"refusing to replace immutable cache shard: {path}")
    if path.name != cache_shard_filename(shard_index):
        _fail("cache shard filename is not canonical")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    plan_digest = bytes.fromhex(plan["plan_sha256"])
    descriptor_digest = _descriptor_digest(plan, shard)
    records_digest = hashlib.sha256()
    root_digest = hashlib.sha256(ROOT_DOMAIN)
    root_digest.update(plan_digest)
    root_digest.update(descriptor_digest)
    started = time.perf_counter()
    count = 0
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(
                _header_bytes(
                    plan,
                    shard,
                    producer_kind=producer_kind,
                    generation_precision_bits=generation_precision_bits,
                    union_precision_bits=union_precision_bits,
                )
            )
            iterator = iter(row_payloads)
            for expected_t in range(shard.t_index_start, shard.t_index_stop):
                try:
                    t_index, payload = next(iterator)
                except StopIteration as error:
                    raise DirichletLatticeCacheError(
                        "cache producer omitted a planned t row"
                    ) from error
                if t_index != expected_t or len(payload) != ROW_PAYLOAD_BYTES:
                    _fail("cache producer row ordering or byte length differs")
                row_digest = _row_hash(
                    plan_digest, descriptor_digest, t_index, payload
                )
                output.write(
                    ROW_HEADER.pack(
                        ROW_MAGIC,
                        FORMAT_VERSION,
                        0,
                        t_index,
                        CELLS_PER_T_INDEX,
                        ROW_PAYLOAD_BYTES,
                        row_digest,
                    )
                )
                output.write(payload)
                records_digest.update(payload)
                root_digest.update(row_digest)
                count += 1
            try:
                next(iterator)
            except StopIteration:
                pass
            else:
                _fail("cache producer supplied rows outside the planned shard")
            output.write(
                FOOTER.pack(
                    FOOTER_MAGIC,
                    FORMAT_VERSION,
                    0,
                    count,
                    count * CELLS_PER_T_INDEX,
                    count * ROW_PAYLOAD_BYTES,
                    records_digest.digest(),
                    root_digest.digest(),
                )
            )
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    digest, size = sha256_file(path)
    if size != shard.artifact_bytes:
        path.unlink(missing_ok=True)
        _fail("written cache shard length differs from its exact plan")
    return {
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "synthetic_cache_format_kat_not_analytic_evidence"
            if producer_kind == PRODUCER_SYNTHETIC
            else "repacked_higher_precision_replayed_lattice_component"
        ),
        "plan_sha256": plan["plan_sha256"],
        "descriptor_sha256": descriptor_digest.hex(),
        "shard": shard.to_dict(),
        "producer_kind": producer_kind,
        "artifact": {"sha256": digest, "size_bytes": size},
        "records_sha256": records_digest.hexdigest(),
        "row_root_sha256": root_digest.hexdigest(),
        "elapsed_seconds": time.perf_counter() - started,
        "external_atom_discharged": False,
    }


def _synthetic_row(t_index: int) -> bytes:
    payload = bytearray(ROW_PAYLOAD_BYTES)
    offset = 0
    width = math.ldexp(1.0, -42)
    for row in range(1, LATTICE_ROWS + 1):
        for column in range(TAYLOR_COLUMNS):
            real = (((t_index * 11 + row * 17 + column * 13) % 251) - 125) / 64
            imag = (((t_index * 19 + row * 29 + column * 7) % 257) - 128) / 64
            LATTICE_CELL.pack_into(
                payload,
                offset,
                real - width,
                real + width,
                imag - width,
                imag + width,
            )
            offset += LATTICE_CELL.size
    return bytes(payload)


def write_synthetic_cache_shard(
    path: Path,
    *,
    plan: dict[str, Any],
    shard_index: int,
) -> dict[str, Any]:
    """Write a deterministic format/KAT shard with no analytic meaning."""

    shard = _plan_shard(_validated_plan(plan), shard_index)
    return _write_cache_artifact(
        path,
        plan=plan,
        shard_index=shard_index,
        producer_kind=PRODUCER_SYNTHETIC,
        generation_precision_bits=0,
        union_precision_bits=0,
        row_payloads=(
            (t_index, _synthetic_row(t_index))
            for t_index in range(shard.t_index_start, shard.t_index_stop)
        ),
    )


def iter_authenticated_cache_rows(
    path: Path,
    *,
    plan: dict[str, Any],
    shard_index: int,
    expected_sha256: str | None = None,
    authenticated_identity: dict[str, str] | None = None,
) -> Iterator[tuple[int, bytes]]:
    """Yield one bounded row only after its plan-bound hash authenticates.

    If ``expected_sha256`` is supplied, the complete immutable file is hashed
    before any row is yielded.  The parser then authenticates each 1 MiB row
    independently.  ``authenticated_identity`` is populated only after the
    iterator is exhausted and the footer has authenticated.
    """

    plan = _validated_plan(plan)
    shard = _plan_shard(plan, shard_index)
    if path.name != cache_shard_filename(shard_index):
        _fail("lattice-cache shard filename is not canonical")
    if expected_sha256 is not None:
        expected_sha256 = _lower_sha256(expected_sha256, "cache artifact digest")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletLatticeCacheError(
            "cannot open lattice-cache shard without following links"
        ) from error
    with os.fdopen(descriptor, "rb") as source:
        file_status = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(file_status.st_mode)
            or file_status.st_size != shard.artifact_bytes
        ):
            _fail("lattice-cache shard exact length differs from the plan")
        if expected_sha256 is not None:
            preparse_digest = hashlib.sha256()
            while block := source.read(1024 * 1024):
                preparse_digest.update(block)
            if preparse_digest.hexdigest() != expected_sha256:
                _fail("lattice-cache shard SHA-256 differs before parsing")
            source.seek(0)

        file_digest = hashlib.sha256()
        raw_header = source.read(HEADER.size)
        file_digest.update(raw_header)
        header = _unpack_header(
            raw_header,
            expected_plan=plan,
            expected_shard_index=shard_index,
        )
        plan_digest = bytes.fromhex(header.plan_sha256)
        descriptor_digest = bytes.fromhex(header.descriptor_sha256)
        records_digest = hashlib.sha256()
        root_digest = hashlib.sha256(ROOT_DOMAIN)
        root_digest.update(plan_digest)
        root_digest.update(descriptor_digest)
        count = 0
        for expected_t in range(header.t_index_start, header.t_index_stop):
            raw_header = source.read(ROW_HEADER.size)
            if len(raw_header) != ROW_HEADER.size:
                _fail("short lattice-cache row header")
            file_digest.update(raw_header)
            (
                magic,
                version,
                reserved,
                t_index,
                cell_count,
                payload_bytes,
                claimed_digest,
            ) = ROW_HEADER.unpack(raw_header)
            if (
                magic != ROW_MAGIC
                or version != FORMAT_VERSION
                or reserved
                or t_index != expected_t
                or cell_count != CELLS_PER_T_INDEX
                or payload_bytes != ROW_PAYLOAD_BYTES
            ):
                _fail("lattice-cache row geometry or ordering differs")
            payload = source.read(ROW_PAYLOAD_BYTES)
            if len(payload) != ROW_PAYLOAD_BYTES:
                _fail("short lattice-cache row payload")
            file_digest.update(payload)
            actual_digest = _row_hash(
                plan_digest, descriptor_digest, t_index, payload
            )
            if actual_digest != claimed_digest:
                _fail("lattice-cache row SHA-256 differs")
            records_digest.update(payload)
            root_digest.update(actual_digest)
            count += 1
            yield t_index, payload

        raw_footer = source.read(FOOTER.size)
        file_digest.update(raw_footer)
        trailing = source.read(1)
        file_digest.update(trailing)
        if len(raw_footer) != FOOTER.size or trailing:
            _fail("lattice-cache footer is missing or has trailing bytes")
        (
            magic,
            version,
            reserved,
            record_count,
            cell_count,
            payload_bytes,
            claimed_records,
            claimed_root,
        ) = FOOTER.unpack(raw_footer)
        if (
            magic != FOOTER_MAGIC
            or version != FORMAT_VERSION
            or reserved
            or record_count != count
            or cell_count != count * CELLS_PER_T_INDEX
            or payload_bytes != count * ROW_PAYLOAD_BYTES
            or claimed_records != records_digest.digest()
            or claimed_root != root_digest.digest()
        ):
            _fail("lattice-cache footer or global digest differs")
        artifact_digest = file_digest.hexdigest()
        if expected_sha256 is not None and artifact_digest != expected_sha256:
            _fail("lattice-cache shard changed between authentication passes")
        if authenticated_identity is not None:
            authenticated_identity.update(
                {
                    "producer_kind": str(header.producer_kind),
                    "artifact_sha256": artifact_digest,
                    "artifact_size_bytes": str(file_status.st_size),
                    "records_sha256": records_digest.hexdigest(),
                    "row_root_sha256": root_digest.hexdigest(),
                }
            )


def validate_lattice_row(payload: bytes) -> dict[str, float | int]:
    """Decode and validate one authenticated row with bounded memory."""

    if len(payload) != ROW_PAYLOAD_BYTES:
        _fail("decoded lattice row has the wrong byte length")
    maximum_width = 0.0
    count = 0
    for re_lo, re_hi, im_lo, im_hi in LATTICE_CELL.iter_unpack(payload):
        if (
            not all(math.isfinite(value) for value in (re_lo, re_hi, im_lo, im_hi))
            or re_lo > re_hi
            or im_lo > im_hi
        ):
            _fail("lattice-cache row contains a malformed complex interval")
        maximum_width = max(maximum_width, re_hi - re_lo, im_hi - im_lo)
        count += 1
    if count != CELLS_PER_T_INDEX:
        _fail("decoded lattice row cell count differs")
    return {"lattice_cells": count, "maximum_component_width": maximum_width}


def inspect_cache_shard(
    path: Path,
    *,
    plan: dict[str, Any],
    shard_index: int,
    expected_sha256: str | None = None,
    validate_cells: bool = False,
) -> dict[str, Any]:
    identity: dict[str, str] = {}
    count = 0
    maximum_width = 0.0
    for _t_index, payload in iter_authenticated_cache_rows(
        path,
        plan=plan,
        shard_index=shard_index,
        expected_sha256=expected_sha256,
        authenticated_identity=identity,
    ):
        if validate_cells:
            checked = validate_lattice_row(payload)
            maximum_width = max(
                maximum_width, float(checked["maximum_component_width"])
            )
        count += 1
    digest = identity["artifact_sha256"]
    size = int(identity["artifact_size_bytes"])
    return {
        "algorithm_id": ALGORITHM_ID,
        "classification": "authenticated_cache_transport_not_analytic_replay",
        "plan_sha256": plan["plan_sha256"],
        "shard_index": shard_index,
        "artifact": {"sha256": digest, "size_bytes": size},
        "t_rows_authenticated": count,
        "lattice_cells_authenticated": count * CELLS_PER_T_INDEX,
        "all_interval_encodings_validated": validate_cells,
        "maximum_component_width": maximum_width if validate_cells else None,
        **identity,
        "external_atom_discharged": False,
    }


def _legacy_lattice_payload(
    path: Path,
    *,
    expected_t_index: int,
    expected_sha256: str,
    expected_size: int,
) -> bytes:
    expected_sha256 = _lower_sha256(
        expected_sha256, "replayed lattice-input digest"
    )
    if type(expected_size) is not int or expected_size <= 0:
        _fail("replayed lattice-input size is invalid")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletLatticeCacheError(
            "cannot open replayed lattice input without following links"
        ) from error
    with os.fdopen(descriptor, "rb") as source:
        file_status = os.fstat(source.fileno())
        if not stat.S_ISREG(file_status.st_mode) or file_status.st_size != expected_size:
            _fail("replayed lattice input is not the bound regular file")
        digest = hashlib.sha256()
        raw_header = source.read(LEGACY_INPUT_HEADER.size)
        if len(raw_header) != LEGACY_INPUT_HEADER.size:
            _fail("short replayed lattice-input header")
        digest.update(raw_header)
        (
            magic,
            version,
            rows,
            degree,
            reserved0,
            t_numerator,
            t_denominator,
            _item_count,
            lattice_count,
            reserved1,
        ) = LEGACY_INPUT_HEADER.unpack(raw_header)
        if (
            magic != LEGACY_INPUT_MAGIC
            or version != 1
            or rows != LATTICE_ROWS
            or degree != TAYLOR_DEGREE
            or reserved0
            or reserved1
            or t_numerator != SOURCE_SAMPLE_NUMERATOR * expected_t_index
            or t_denominator != SOURCE_SAMPLE_DENOMINATOR
            or lattice_count != CELLS_PER_T_INDEX
        ):
            _fail("replayed lattice input differs from the cache geometry")
        payload = source.read(ROW_PAYLOAD_BYTES)
        if len(payload) != ROW_PAYLOAD_BYTES:
            _fail("short replayed lattice payload")
        digest.update(payload)
        while block := source.read(1024 * 1024):
            digest.update(block)
        if digest.hexdigest() != expected_sha256:
            _fail("replayed lattice input differs while entering the cache")
    validate_lattice_row(payload)
    return payload


def pack_replayed_lattice_certificates(
    artifact_path: Path,
    receipt_path: Path,
    *,
    plan: dict[str, Any],
    shard_index: int,
    certificate_roots: Sequence[Path],
    replay_precision_bits: int | None = None,
) -> dict[str, Any]:
    """Replay and repack one exact sequence of existing Arb certificates.

    This operation is intentionally expensive.  It recomputes every Hurwitz
    rectangle at higher precision through the existing independent replay
    before the row enters the cache.  The resulting receipt binds every input
    certificate and replay digest.
    """

    from tg_verifier.dirichlet_lattice_certificates import (
        LATTICE_FILENAME,
        _load_manifest,
        _manifest_parameters,
        _require_artifact,
        replay_certificate,
    )

    plan = _validated_plan(plan)
    shard = _plan_shard(plan, shard_index)
    if len(certificate_roots) != shard.t_index_count:
        _fail("certificate-root count differs from the planned cache shard")
    if len({root.resolve() for root in certificate_roots}) != len(certificate_roots):
        _fail("certificate-root list contains a duplicate")
    if artifact_path.exists() or receipt_path.exists():
        _fail("refusing to replace an immutable cache artifact or receipt")
    if receipt_path.name != f"lattice-shard-{shard_index:04d}.receipt.json":
        _fail("cache pack receipt filename is not canonical")

    manifests: list[dict[str, Any]] = []
    precisions: set[tuple[int, int]] = set()
    for expected_t, root in zip(
        range(shard.t_index_start, shard.t_index_stop), certificate_roots
    ):
        manifest = _load_manifest(root)
        parameters = _manifest_parameters(manifest)
        if parameters["t_index"] != expected_t or parameters["M"] != SOURCE_M:
            _fail("certificate t index or M differs from the cache shard")
        precisions.add(
            (
                parameters["generation_precision_bits"],
                parameters["second_generation_precision_bits"],
            )
        )
        manifests.append(manifest)
    if len(precisions) != 1:
        _fail("cache shard certificates use inconsistent generation precisions")
    generation_precision, union_precision = next(iter(precisions))
    source_bindings: list[dict[str, Any]] = []

    def rows() -> Iterator[tuple[int, bytes]]:
        for expected_t, root, manifest in zip(
            range(shard.t_index_start, shard.t_index_stop),
            certificate_roots,
            manifests,
        ):
            replay = replay_certificate(
                root, replay_precision_bits=replay_precision_bits
            )
            if (
                replay.get("certificate_sha256") != manifest["certificate_sha256"]
                or replay.get("lattice_cells_replayed") != CELLS_PER_T_INDEX
                or replay.get("higher_precision_arb_containment_passed") is not True
            ):
                _fail("lattice certificate replay did not close every cache cell")
            lattice_path = _require_artifact(manifest, root, LATTICE_FILENAME)
            lattice_record = manifest["artifacts"][LATTICE_FILENAME]
            lattice_sha = lattice_record["sha256"]
            lattice_size = lattice_record["size_bytes"]
            payload = _legacy_lattice_payload(
                lattice_path,
                expected_t_index=expected_t,
                expected_sha256=lattice_sha,
                expected_size=lattice_size,
            )
            source_bindings.append(
                {
                    "t_index": expected_t,
                    "certificate_sha256": manifest["certificate_sha256"],
                    "replay_sha256": replay["replay_sha256"],
                    "replay_precision_bits": replay["replay_precision_bits"],
                    "lattice_input": {
                        "sha256": lattice_sha,
                        "size_bytes": lattice_size,
                    },
                }
            )
            yield expected_t, payload

    started = time.perf_counter()
    artifact_report = _write_cache_artifact(
        artifact_path,
        plan=plan,
        shard_index=shard_index,
        producer_kind=PRODUCER_REPLAYED_LATTICE_CERTIFICATE,
        generation_precision_bits=generation_precision,
        union_precision_bits=union_precision,
        row_payloads=rows(),
    )
    producer_sha, producer_size = sha256_file(Path(__file__).resolve())
    receipt: dict[str, Any] = {
        "schema": PACK_RECEIPT_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "higher_precision_replayed_hurwitz_cache_component_not_theorem_7_1"
        ),
        "plan_sha256": plan["plan_sha256"],
        "descriptor_sha256": artifact_report["descriptor_sha256"],
        "shard": shard.to_dict(),
        "generation_precision_bits": generation_precision,
        "union_precision_bits": union_precision,
        "artifact": artifact_report["artifact"],
        "records_sha256": artifact_report["records_sha256"],
        "row_root_sha256": artifact_report["row_root_sha256"],
        "producer_module": {
            "sha256": producer_sha,
            "size_bytes": producer_size,
        },
        "source_bindings": source_bindings,
        "elapsed_seconds": time.perf_counter() - started,
        "decisions": {
            "every_cache_row_from_canonical_lattice_input": True,
            "every_hurwitz_cell_higher_precision_replayed_before_pack": True,
            "cache_transport_authenticated": True,
            "complete_main_grid_cache_in_this_shard": (
                plan["complete_large_q_main_grid_geometry"]
                and shard.t_index_count == SOURCE_T_INDEX_STOP
            ),
            "cuda_broadcast_executed": False,
            "execution_attested": False,
            "zero_isolation_or_turing_completed": False,
            "external_atom_discharged": False,
        },
    }
    receipt["receipt_sha256"] = sha256_bytes(canonical_json_bytes(receipt))
    try:
        _atomic_bytes(receipt_path, canonical_json_bytes(receipt))
    except BaseException:
        # Both paths were absent on entry and the artifact was created by this
        # invocation. Do not leave a valid-looking unreceipted production
        # shard that makes an idempotent retry impossible.
        artifact_path.unlink(missing_ok=True)
        raise
    return receipt


def _load_pack_receipt(
    path: Path,
    *,
    plan: dict[str, Any],
    shard_index: int,
    artifact: dict[str, Any],
    records_sha256: str,
    row_root_sha256: str,
    expected_file_sha256: str | None = None,
    expected_file_size: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if expected_file_sha256 is not None:
        expected_file_sha256 = _lower_sha256(
            expected_file_sha256, "cache pack receipt file digest"
        )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletLatticeCacheError(
            "cannot open cache pack receipt without following links"
        ) from error
    with os.fdopen(descriptor, "rb") as source:
        file_status = os.fstat(source.fileno())
        if not stat.S_ISREG(file_status.st_mode):
            _fail("cache pack receipt is not a regular file")
        if (
            expected_file_size is not None
            and file_status.st_size != expected_file_size
        ):
            _fail("cache pack receipt file size differs")
        raw = source.read(2 * 1024 * 1024 + 1)
    if not raw or len(raw) > 2 * 1024 * 1024:
        _fail("cache pack receipt size is outside its fixed bound")
    file_digest = sha256_bytes(raw)
    if expected_file_sha256 is not None and file_digest != expected_file_sha256:
        _fail("cache pack receipt file SHA-256 differs")
    try:
        receipt = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletLatticeCacheError("invalid cache pack receipt JSON") from error
    if not isinstance(receipt, dict) or canonical_json_bytes(receipt) != raw:
        _fail("cache pack receipt is not canonical JSON")
    body = dict(receipt)
    claimed = body.pop("receipt_sha256", None)
    if claimed != sha256_bytes(canonical_json_bytes(body)):
        _fail("cache pack receipt self-hash differs")
    required = {
        "schema",
        "schema_version",
        "author",
        "atom_id",
        "algorithm_id",
        "classification",
        "plan_sha256",
        "descriptor_sha256",
        "shard",
        "generation_precision_bits",
        "union_precision_bits",
        "artifact",
        "records_sha256",
        "row_root_sha256",
        "producer_module",
        "source_bindings",
        "elapsed_seconds",
        "decisions",
        "receipt_sha256",
    }
    if set(receipt) != required:
        _fail("cache pack receipt fields changed")
    shard = _plan_shard(plan, shard_index)
    decisions = receipt.get("decisions")
    generation_precision = receipt.get("generation_precision_bits")
    union_precision = receipt.get("union_precision_bits")
    elapsed = receipt.get("elapsed_seconds")
    producer_module = receipt.get("producer_module")
    current_module_sha, current_module_size = sha256_file(Path(__file__).resolve())
    expected_decisions = {
        "every_cache_row_from_canonical_lattice_input": True,
        "every_hurwitz_cell_higher_precision_replayed_before_pack": True,
        "cache_transport_authenticated": True,
        "complete_main_grid_cache_in_this_shard": (
            plan["complete_large_q_main_grid_geometry"]
            and shard.t_index_count == SOURCE_T_INDEX_STOP
        ),
        "cuda_broadcast_executed": False,
        "execution_attested": False,
        "zero_isolation_or_turing_completed": False,
        "external_atom_discharged": False,
    }
    if (
        receipt.get("schema") != PACK_RECEIPT_SCHEMA
        or receipt.get("schema_version") != 1
        or receipt.get("author") != AUTHOR
        or receipt.get("atom_id") != ATOM_ID
        or receipt.get("algorithm_id") != ALGORITHM_ID
        or receipt.get("classification")
        != "higher_precision_replayed_hurwitz_cache_component_not_theorem_7_1"
        or receipt.get("plan_sha256") != plan["plan_sha256"]
        or receipt.get("descriptor_sha256")
        != _descriptor_digest(plan, shard).hex()
        or receipt.get("shard") != shard.to_dict()
        or receipt.get("artifact") != artifact
        or receipt.get("records_sha256")
        != _lower_sha256(records_sha256, "cache records digest")
        or receipt.get("row_root_sha256")
        != _lower_sha256(row_root_sha256, "cache row-root digest")
        or producer_module
        != {"sha256": current_module_sha, "size_bytes": current_module_size}
        or type(generation_precision) is not int
        or generation_precision < 128
        or union_precision != generation_precision + 64
        or isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(elapsed)
        or elapsed < 0
        or decisions != expected_decisions
    ):
        _fail("cache pack receipt does not bind the reviewed component")
    bindings = receipt.get("source_bindings")
    if not isinstance(bindings, list) or len(bindings) != shard.t_index_count:
        _fail("cache pack receipt source binding count differs")
    if not all(isinstance(binding, dict) for binding in bindings):
        _fail("cache pack receipt contains a malformed source binding")
    if [binding.get("t_index") for binding in bindings] != list(
        range(shard.t_index_start, shard.t_index_stop)
    ):
        _fail("cache pack receipt source rows are reordered")
    for binding in bindings:
        if set(binding) != {
            "t_index",
            "certificate_sha256",
            "replay_sha256",
            "replay_precision_bits",
            "lattice_input",
        }:
            _fail("cache pack receipt source binding fields changed")
        _lower_sha256(binding.get("certificate_sha256"), "certificate digest")
        _lower_sha256(binding.get("replay_sha256"), "replay digest")
        replay_precision = binding.get("replay_precision_bits")
        if (
            type(replay_precision) is not int
            or replay_precision < generation_precision + 64
        ):
            _fail("cache pack receipt replay precision is insufficient")
        lattice_input = binding.get("lattice_input")
        if (
            not isinstance(lattice_input, dict)
            or set(lattice_input) != {"sha256", "size_bytes"}
            or type(lattice_input.get("size_bytes")) is not int
            or lattice_input["size_bytes"] <= 0
        ):
            _fail("cache pack receipt lattice-input binding is malformed")
        _lower_sha256(
            lattice_input.get("sha256"), "cache lattice-input digest"
        )
    return receipt, {"sha256": file_digest, "size_bytes": len(raw)}


def build_cache_catalog(
    catalog_path: Path,
    root: Path,
    *,
    plan: dict[str, Any],
    require_replayed_receipts: bool = True,
) -> dict[str, Any]:
    """Authenticate every canonical shard and publish a gap-free catalog."""

    plan = _validated_plan(plan)
    if catalog_path.exists():
        _fail(f"refusing to replace immutable cache catalog: {catalog_path}")
    entries: list[dict[str, Any]] = []
    all_replayed = True
    for shard_index in range(plan["storage"]["shard_count"]):
        artifact_path = root / cache_shard_filename(shard_index)
        inspected = inspect_cache_shard(
            artifact_path,
            plan=plan,
            shard_index=shard_index,
        )
        digest = inspected["artifact"]["sha256"]
        size = inspected["artifact"]["size_bytes"]
        producer_kind = int(inspected["producer_kind"])
        receipt_record: dict[str, Any] | None = None
        if producer_kind == PRODUCER_REPLAYED_LATTICE_CERTIFICATE:
            receipt_path = root / f"lattice-shard-{shard_index:04d}.receipt.json"
            receipt, receipt_file = _load_pack_receipt(
                receipt_path,
                plan=plan,
                shard_index=shard_index,
                artifact={"sha256": digest, "size_bytes": size},
                records_sha256=inspected["records_sha256"],
                row_root_sha256=inspected["row_root_sha256"],
            )
            receipt_record = {
                "filename": receipt_path.name,
                "sha256": receipt_file["sha256"],
                "size_bytes": receipt_file["size_bytes"],
                "receipt_sha256": receipt["receipt_sha256"],
            }
        else:
            all_replayed = False
            if require_replayed_receipts:
                _fail("catalog requires replayed analytic cache shards")
        entries.append(
            {
                "shard_index": shard_index,
                "filename": artifact_path.name,
                "sha256": digest,
                "size_bytes": size,
                "producer_kind": producer_kind,
                "records_sha256": inspected["records_sha256"],
                "row_root_sha256": inspected["row_root_sha256"],
                "pack_receipt": receipt_record,
            }
        )
    catalog: dict[str, Any] = {
        "schema": CATALOG_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "complete_main_grid_cache_with_replay_receipts_not_attested"
            if all_replayed and plan["complete_large_q_main_grid_geometry"]
            else "structural_or_partial_cache_catalog_not_source_evidence"
        ),
        "plan_sha256": plan["plan_sha256"],
        "plan_parameters": plan["parameters"],
        "shards": entries,
        "totals": {
            "shard_count": len(entries),
            "t_indices": plan["parameters"]["t_index_stop_exclusive"],
            "lattice_cells": plan["storage"]["lattice_cells"],
            "payload_bytes": plan["storage"]["payload_bytes"],
            "artifact_bytes": sum(entry["size_bytes"] for entry in entries),
        },
        "decisions": {
            "gap_free_t_index_coverage": True,
            "all_artifacts_hash_bound_and_fully_parsed": True,
            "all_shards_bind_higher_precision_replay_receipts": all_replayed,
            "replay_receipt_execution_attested": False,
            "complete_large_q_main_grid_geometry": (
                plan["complete_large_q_main_grid_geometry"]
            ),
            "cuda_broadcast_executed": False,
            "zero_isolation_or_turing_completed": False,
            "external_atom_discharged": False,
        },
    }
    catalog["catalog_sha256"] = sha256_bytes(canonical_json_bytes(catalog))
    _atomic_bytes(catalog_path, canonical_json_bytes(catalog))
    return catalog


def load_cache_catalog(
    catalog_path: Path,
    *,
    require_replayed: bool = False,
    expected_sha256: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(catalog_path, flags)
    except OSError as error:
        raise DirichletLatticeCacheError(
            "cannot open cache catalog without following links"
        ) from error
    with os.fdopen(descriptor, "rb") as source:
        file_status = os.fstat(source.fileno())
        if not stat.S_ISREG(file_status.st_mode):
            _fail("cache catalog is not a regular file")
        raw = source.read(4 * 1024 * 1024 + 1)
    if not raw or len(raw) > 4 * 1024 * 1024:
        _fail("cache catalog size is outside its fixed bound")
    if expected_sha256 is not None and sha256_bytes(raw) != _lower_sha256(
        expected_sha256, "cache catalog file digest"
    ):
        _fail("cache catalog file SHA-256 differs")
    try:
        catalog = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletLatticeCacheError("invalid cache catalog JSON") from error
    if not isinstance(catalog, dict) or canonical_json_bytes(catalog) != raw:
        _fail("cache catalog is not canonical JSON")
    body = dict(catalog)
    claimed = body.pop("catalog_sha256", None)
    if claimed != sha256_bytes(canonical_json_bytes(body)):
        _fail("cache catalog self-hash differs")
    required = {
        "schema",
        "schema_version",
        "author",
        "atom_id",
        "algorithm_id",
        "classification",
        "plan_sha256",
        "plan_parameters",
        "shards",
        "totals",
        "decisions",
        "catalog_sha256",
    }
    if set(catalog) != required:
        _fail("cache catalog fields changed")
    parameters = catalog.get("plan_parameters")
    if not isinstance(parameters, dict):
        _fail("cache catalog plan parameters are missing")
    plan = source_cache_plan(
        t_index_stop_exclusive=parameters.get("t_index_stop_exclusive"),
        t_indices_per_shard=parameters.get("t_indices_per_storage_shard"),
    )
    entries = catalog.get("shards")
    decisions = catalog.get("decisions")
    expected_totals = {
        "shard_count": plan["storage"]["shard_count"],
        "t_indices": plan["parameters"]["t_index_stop_exclusive"],
        "lattice_cells": plan["storage"]["lattice_cells"],
        "payload_bytes": plan["storage"]["payload_bytes"],
        "artifact_bytes": plan["storage"]["artifact_bytes"],
    }
    if (
        catalog.get("schema") != CATALOG_SCHEMA
        or catalog.get("schema_version") != 1
        or catalog.get("author") != AUTHOR
        or catalog.get("atom_id") != ATOM_ID
        or catalog.get("algorithm_id") != ALGORITHM_ID
        or catalog.get("plan_sha256") != plan["plan_sha256"]
        or parameters != plan["parameters"]
        or catalog.get("totals") != expected_totals
        or not isinstance(entries, list)
        or len(entries) != plan["storage"]["shard_count"]
        or not isinstance(decisions, dict)
    ):
        _fail("cache catalog geometry or trust boundary differs")
    all_replayed = True
    for expected_index, entry in enumerate(entries):
        expected_keys = {
            "shard_index",
            "filename",
            "sha256",
            "size_bytes",
            "producer_kind",
            "records_sha256",
            "row_root_sha256",
            "pack_receipt",
        }
        if (
            not isinstance(entry, dict)
            or set(entry) != expected_keys
            or entry.get("shard_index") != expected_index
            or entry.get("filename") != cache_shard_filename(expected_index)
            or type(entry.get("size_bytes")) is not int
            or entry["size_bytes"]
            != _plan_shard(plan, expected_index).artifact_bytes
        ):
            _fail("cache catalog shard sequence or length differs")
        _lower_sha256(entry.get("sha256"), "catalog artifact digest")
        _lower_sha256(entry.get("records_sha256"), "catalog records digest")
        _lower_sha256(entry.get("row_root_sha256"), "catalog row-root digest")
        producer_kind = entry.get("producer_kind")
        if producer_kind == PRODUCER_REPLAYED_LATTICE_CERTIFICATE:
            receipt = entry.get("pack_receipt")
            if not isinstance(receipt, dict) or set(receipt) != {
                "filename",
                "sha256",
                "size_bytes",
                "receipt_sha256",
            }:
                _fail("replayed cache catalog entry lacks its pack receipt")
            if receipt.get("filename") != (
                f"lattice-shard-{expected_index:04d}.receipt.json"
            ):
                _fail("cache catalog receipt filename is not canonical")
            _lower_sha256(receipt.get("sha256"), "catalog receipt file digest")
            _lower_sha256(receipt.get("receipt_sha256"), "catalog receipt digest")
            if type(receipt.get("size_bytes")) is not int or not (
                0 < receipt["size_bytes"] <= 2 * 1024 * 1024
            ):
                _fail("cache catalog receipt size is outside its fixed bound")
        elif producer_kind == PRODUCER_SYNTHETIC:
            all_replayed = False
            if entry.get("pack_receipt") is not None:
                _fail("synthetic cache catalog entry carries a replay receipt")
        else:
            _fail("cache catalog entry has an unknown producer kind")
    expected_decisions = {
        "gap_free_t_index_coverage": True,
        "all_artifacts_hash_bound_and_fully_parsed": True,
        "all_shards_bind_higher_precision_replay_receipts": all_replayed,
        "replay_receipt_execution_attested": False,
        "complete_large_q_main_grid_geometry": (
            plan["complete_large_q_main_grid_geometry"]
        ),
        "cuda_broadcast_executed": False,
        "zero_isolation_or_turing_completed": False,
        "external_atom_discharged": False,
    }
    expected_classification = (
        "complete_main_grid_cache_with_replay_receipts_not_attested"
        if all_replayed and plan["complete_large_q_main_grid_geometry"]
        else "structural_or_partial_cache_catalog_not_source_evidence"
    )
    if (
        decisions != expected_decisions
        or catalog.get("classification") != expected_classification
    ):
        _fail("cache catalog decisions or classification changed")
    if require_replayed and (
        not all_replayed
    ):
        _fail("cache catalog is not backed by higher-precision replay receipts")
    return catalog, plan


def iter_catalog_rows(
    root: Path,
    catalog_path: Path,
    *,
    require_replayed: bool = False,
    expected_catalog_sha256: str | None = None,
) -> Iterator[tuple[int, bytes]]:
    """Stream a catalog in exact t order with at most one row buffered."""

    catalog, plan = load_cache_catalog(
        catalog_path,
        require_replayed=require_replayed,
        expected_sha256=expected_catalog_sha256,
    )
    expected_t = 0
    for entry in catalog["shards"]:
        path = root / entry["filename"]
        receipt_record = entry["pack_receipt"]
        if receipt_record is not None:
            receipt_path = root / receipt_record["filename"]
            _load_pack_receipt(
                receipt_path,
                plan=plan,
                shard_index=entry["shard_index"],
                artifact={
                    "sha256": entry["sha256"],
                    "size_bytes": entry["size_bytes"],
                },
                records_sha256=entry["records_sha256"],
                row_root_sha256=entry["row_root_sha256"],
                expected_file_sha256=receipt_record["sha256"],
                expected_file_size=receipt_record["size_bytes"],
            )
        for t_index, payload in iter_authenticated_cache_rows(
            path,
            plan=plan,
            shard_index=entry["shard_index"],
            expected_sha256=entry["sha256"],
        ):
            if t_index != expected_t:
                _fail("cache catalog stream has a t-index gap or overlap")
            yield t_index, payload
            expected_t += 1
    if expected_t != plan["parameters"]["t_index_stop_exclusive"]:
        _fail("cache catalog stream ended before its exact t boundary")


def iter_catalog_range_rows(
    root: Path,
    catalog_path: Path,
    *,
    t_index_start_inclusive: int,
    t_index_stop_exclusive: int,
    require_replayed: bool = False,
    expected_catalog_sha256: str | None = None,
    authenticated_identity: dict[str, Any] | None = None,
) -> Iterator[tuple[int, bytes]]:
    """Stream one exact t range while fully authenticating every touched shard.

    Storage shards and execution phases are deliberately independent.  In
    particular, a source phase may start or stop in the middle of a 128-row
    storage shard.  This iterator therefore parses every row and the footer of
    each intersecting shard, but yields only rows in the requested half-open
    range.  ``authenticated_identity`` is populated only after the iterator is
    exhausted.  A caller that publishes an artifact from the yielded rows must
    exhaust the iterator before publication.
    """

    catalog, plan = load_cache_catalog(
        catalog_path,
        require_replayed=require_replayed,
        expected_sha256=expected_catalog_sha256,
    )
    cache_stop = plan["parameters"]["t_index_stop_exclusive"]
    if (
        type(t_index_start_inclusive) is not int
        or type(t_index_stop_exclusive) is not int
        or not 0 <= t_index_start_inclusive < t_index_stop_exclusive
        or t_index_stop_exclusive > cache_stop
    ):
        _fail("cache catalog range is outside its exact t coverage")

    catalog_file_sha256, catalog_file_size = _sha256_regular_file_nofollow(
        catalog_path
    )
    if (
        expected_catalog_sha256 is not None
        and catalog_file_sha256 != expected_catalog_sha256
    ):
        _fail("cache catalog changed after validation")

    selected_rows = 0
    physical_rows = 0
    physical_artifact_bytes = 0
    touched_shards: list[dict[str, Any]] = []
    for entry in catalog["shards"]:
        shard = _plan_shard(plan, entry["shard_index"])
        if (
            shard.t_index_stop <= t_index_start_inclusive
            or t_index_stop_exclusive <= shard.t_index_start
        ):
            continue
        receipt_record = entry["pack_receipt"]
        if receipt_record is not None:
            receipt_path = root / receipt_record["filename"]
            _load_pack_receipt(
                receipt_path,
                plan=plan,
                shard_index=entry["shard_index"],
                artifact={
                    "sha256": entry["sha256"],
                    "size_bytes": entry["size_bytes"],
                },
                records_sha256=entry["records_sha256"],
                row_root_sha256=entry["row_root_sha256"],
                expected_file_sha256=receipt_record["sha256"],
                expected_file_size=receipt_record["size_bytes"],
            )
        shard_identity: dict[str, str] = {}
        artifact_path = root / entry["filename"]
        for t_index, payload in iter_authenticated_cache_rows(
            artifact_path,
            plan=plan,
            shard_index=entry["shard_index"],
            expected_sha256=entry["sha256"],
            authenticated_identity=shard_identity,
        ):
            physical_rows += 1
            if t_index_start_inclusive <= t_index < t_index_stop_exclusive:
                expected_t = t_index_start_inclusive + selected_rows
                if t_index != expected_t:
                    _fail("cache range stream has a t-index gap or overlap")
                selected_rows += 1
                yield t_index, payload
        if not shard_identity:
            _fail("cache range shard footer was not authenticated")
        physical_artifact_bytes += entry["size_bytes"]
        touched_shards.append(
            {
                "shard_index": entry["shard_index"],
                "t_index_start_inclusive": shard.t_index_start,
                "t_index_stop_exclusive": shard.t_index_stop,
                "artifact_sha256": shard_identity["artifact_sha256"],
                "artifact_size_bytes": int(
                    shard_identity["artifact_size_bytes"]
                ),
                "producer_kind": int(shard_identity["producer_kind"]),
                "records_sha256": shard_identity["records_sha256"],
                "row_root_sha256": shard_identity["row_root_sha256"],
            }
        )

    expected_rows = t_index_stop_exclusive - t_index_start_inclusive
    if selected_rows != expected_rows or not touched_shards:
        _fail("cache range stream ended before its exact t boundary")
    if authenticated_identity is not None:
        authenticated_identity.update(
            {
                "catalog_file_sha256": catalog_file_sha256,
                "catalog_file_size_bytes": catalog_file_size,
                "catalog_sha256": catalog["catalog_sha256"],
                "cache_plan_sha256": plan["plan_sha256"],
                "t_index_start_inclusive": t_index_start_inclusive,
                "t_index_stop_exclusive": t_index_stop_exclusive,
                "selected_row_count": selected_rows,
                "selected_payload_bytes": selected_rows * ROW_PAYLOAD_BYTES,
                "authenticated_physical_row_count": physical_rows,
                "authenticated_unselected_boundary_row_count": (
                    physical_rows - selected_rows
                ),
                # iter_authenticated_cache_rows performs a complete pre-hash
                # and then a complete parsing/hash pass.
                "authenticated_physical_file_bytes": (
                    2 * physical_artifact_bytes
                ),
                "full_touched_shard_footers_authenticated": True,
                "require_replayed": require_replayed,
                "touched_shards": touched_shards,
            }
        )


def iter_catalog_lane_rows(
    root: Path,
    catalog_path: Path,
    *,
    lane_index: int,
    lane_count: int = DEFAULT_BROADCAST_LANES,
    require_replayed: bool = False,
    expected_catalog_sha256: str | None = None,
) -> Iterator[tuple[int, bytes]]:
    """Stream exactly one broadcast lane with at most one row buffered.

    Unlike :func:`iter_catalog_rows`, this reader does not authenticate or
    traverse shards assigned to earlier lanes.  It still checks the catalog,
    the deterministic lane boundary, every replay receipt, both whole-file
    passes, every row hash, and the final footer for each assigned shard.
    """

    catalog, plan = load_cache_catalog(
        catalog_path,
        require_replayed=require_replayed,
        expected_sha256=expected_catalog_sha256,
    )
    assignment = broadcast_plan(plan, lane_count=lane_count)
    if type(lane_index) is not int or not 0 <= lane_index < lane_count:
        _fail("cache broadcast lane index is outside the plan")
    lane = assignment["lanes"][lane_index]
    first_shard = lane["storage_shard_start_inclusive"]
    stop_shard = lane["storage_shard_stop_exclusive"]
    expected_t = lane["t_index_start_inclusive"]
    for entry in catalog["shards"][first_shard:stop_shard]:
        receipt_record = entry["pack_receipt"]
        if receipt_record is not None:
            receipt_path = root / receipt_record["filename"]
            _load_pack_receipt(
                receipt_path,
                plan=plan,
                shard_index=entry["shard_index"],
                artifact={
                    "sha256": entry["sha256"],
                    "size_bytes": entry["size_bytes"],
                },
                records_sha256=entry["records_sha256"],
                row_root_sha256=entry["row_root_sha256"],
                expected_file_sha256=receipt_record["sha256"],
                expected_file_size=receipt_record["size_bytes"],
            )
        artifact_path = root / entry["filename"]
        for t_index, payload in iter_authenticated_cache_rows(
            artifact_path,
            plan=plan,
            shard_index=entry["shard_index"],
            expected_sha256=entry["sha256"],
        ):
            if t_index != expected_t:
                _fail("cache lane stream has a t-index gap or overlap")
            yield t_index, payload
            expected_t += 1
    if expected_t != lane["t_index_stop_exclusive"]:
        _fail("cache lane stream ended before its deterministic boundary")


def projection(
    *,
    authenticated_file_bytes_per_second: float,
    lane_count: int = DEFAULT_BROADCAST_LANES,
    analytic_cells_per_second: float | None = None,
) -> dict[str, Any]:
    """Project only cache I/O and optional externally measured cell production."""

    if (
        not math.isfinite(authenticated_file_bytes_per_second)
        or authenticated_file_bytes_per_second <= 0
    ):
        _fail("authenticated cache rate must be finite and positive")
    if analytic_cells_per_second is not None and (
        not math.isfinite(analytic_cells_per_second)
        or analytic_cells_per_second <= 0
    ):
        _fail("analytic cell rate must be finite and positive")
    plan = source_cache_plan()
    broadcast = broadcast_plan(plan, lane_count=lane_count)
    artifact_bytes = plan["storage"]["artifact_bytes"]
    # The strict reader first hashes the whole file and then parses/hash-checks
    # every row, so it intentionally reads every artifact byte twice.
    physical_read_bytes = 2 * artifact_bytes
    result: dict[str, Any] = {
        "algorithm_id": ALGORITHM_ID,
        "classification": "component_sensitivity_not_h100_or_atom_eta",
        "source_geometry": {
            "t_indices": SOURCE_T_INDEX_STOP,
            "lattice_cells": SOURCE_LATTICE_CELLS,
            "cache_payload_bytes": SOURCE_CACHE_PAYLOAD_BYTES,
            "cache_artifact_bytes": artifact_bytes,
            "strict_reader_physical_bytes": physical_read_bytes,
            "old_q_major_lattice_bytes": OLD_Q_MAJOR_LATTICE_BYTES,
            "lattice_payload_reduction_ratio": (
                OLD_Q_MAJOR_LATTICE_BYTES / SOURCE_CACHE_PAYLOAD_BYTES
            ),
            "old_seeded_compact_input_bytes": OLD_SEEDED_COMPACT_INPUT_BYTES,
            "remaining_non_lattice_compact_input_bytes": (
                NON_LATTICE_COMPACT_INPUT_BYTES
            ),
            "t_major_compact_input_bytes": T_MAJOR_COMPACT_INPUT_BYTES,
            "direct_t_major_cuda_input_bytes": 286_556_459_000,
            "direct_t_major_input_including_recovery_seeds": 339_564_685_336,
            "total_compact_input_reduction_ratio": (
                OLD_SEEDED_COMPACT_INPUT_BYTES / T_MAJOR_COMPACT_INPUT_BYTES
            ),
        },
        "authenticated_reader": {
            "measured_or_supplied_file_bytes_per_second": (
                authenticated_file_bytes_per_second
            ),
            "projected_full_cache_seconds": (
                physical_read_bytes / authenticated_file_bytes_per_second
            ),
            "projected_full_cache_hours": (
                physical_read_bytes
                / authenticated_file_bytes_per_second
                / 3600
            ),
            "note": (
                "The denominator counts both the mandatory pre-hash scan and "
                "the authenticated parser scan."
            ),
        },
        "broadcast_assignment": broadcast,
        "analytic_generation": (
            None
            if analytic_cells_per_second is None
            else {
                "externally_measured_cells_per_second": analytic_cells_per_second,
                "projected_single_process_hours": (
                    SOURCE_LATTICE_CELLS / analytic_cells_per_second / 3600
                ),
                "warning": (
                    "This is straight-line scaling of a supplied Arb sample, "
                    "not an H100 measurement or a parallel-efficiency claim."
                ),
            }
        ),
        "exclusions": [
            "Hurwitz-cell generation unless an external measured rate is supplied",
            "host-to-H100 transfer and in-HBM reuse",
            "Taylor reconstruction and all-character transforms",
            "completed-L values, zero isolation, exceptions, and Turing closure",
            "Azure attestation, retries, and Lean realization",
        ],
        "h100_end_to_end_runtime_estimated": False,
        "external_atom_discharged": False,
    }
    return result


def benchmark_cache_io(
    *,
    t_indices: int = 4,
    repetitions: int = 3,
) -> dict[str, Any]:
    """Measure strict double-pass authentication on a deterministic local KAT."""

    if not 1 <= t_indices <= 32:
        _fail("I/O benchmark t_indices must be in 1..32")
    if not 1 <= repetitions <= 100:
        _fail("I/O benchmark repetitions must be in 1..100")
    plan = source_cache_plan(
        t_index_stop_exclusive=t_indices,
        t_indices_per_shard=t_indices,
    )
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        path = root / cache_shard_filename(0)
        write_report = write_synthetic_cache_shard(
            path, plan=plan, shard_index=0
        )
        digest = write_report["artifact"]["sha256"]
        started = time.perf_counter()
        rows = 0
        for _ in range(repetitions):
            rows += sum(
                1
                for _item in iter_authenticated_cache_rows(
                    path,
                    plan=plan,
                    shard_index=0,
                    expected_sha256=digest,
                )
            )
        elapsed = time.perf_counter() - started
        artifact_bytes = write_report["artifact"]["size_bytes"]
    physical_bytes = 2 * artifact_bytes * repetitions
    rate = physical_bytes / elapsed
    return {
        "algorithm_id": ALGORITHM_ID,
        "classification": "local_synthetic_cache_io_not_analytic_or_h100_benchmark",
        "sample": {
            "t_indices_per_repetition": t_indices,
            "repetitions": repetitions,
            "rows_authenticated": rows,
            "artifact_bytes_per_repetition": artifact_bytes,
            "physical_bytes_read": physical_bytes,
            "elapsed_seconds": elapsed,
            "physical_file_bytes_per_second": rate,
        },
        "source_projection": projection(
            authenticated_file_bytes_per_second=rate
        ),
        "external_atom_discharged": False,
    }


def capability() -> dict[str, Any]:
    plan = source_cache_plan()
    return {
        "algorithm_id": ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "classification": "t_major_cache_transport_component_not_theorem_7_1",
        "format": {
            "header_magic": HEADER_MAGIC.decode("ascii"),
            "row_magic": ROW_MAGIC.decode("ascii"),
            "footer_magic": FOOTER_MAGIC.decode("ascii"),
            "version": FORMAT_VERSION,
            "row_payload_bytes": ROW_PAYLOAD_BYTES,
        },
        "large_q_main_grid_plan_sha256": plan["plan_sha256"],
        "large_q_main_grid_storage_shards": plan["storage"]["shard_count"],
        "large_q_main_grid_cache_payload_bytes": SOURCE_CACHE_PAYLOAD_BYTES,
        "large_q_main_grid_cache_artifact_bytes": plan["storage"]["artifact_bytes"],
        "covers_large_q_main_positive_grid_only": True,
        "interpolation_exception_and_turing_grids_included": False,
        "old_q_major_lattice_bytes": OLD_Q_MAJOR_LATTICE_BYTES,
        "old_seeded_compact_input_bytes": OLD_SEEDED_COMPACT_INPUT_BYTES,
        "remaining_non_lattice_compact_input_bytes": (
            NON_LATTICE_COMPACT_INPUT_BYTES
        ),
        "t_major_compact_input_bytes": T_MAJOR_COMPACT_INPUT_BYTES,
        "direct_t_major_cuda_input_bytes": 286_556_459_000,
        "direct_t_major_input_including_recovery_seeds": 339_564_685_336,
        "bounded_authenticated_reader_implemented": True,
        "deterministic_work_balanced_broadcast_plan_implemented": True,
        "replayed_certificate_repacker_implemented": True,
        "source_catalog_implemented": True,
        "cuda_t_major_broadcaster_integrated": True,
        "cuda_t_major_broadcaster_source_scale_executed": False,
        "cuda_t_major_broadcaster_component": (
            "tools/tg_dirichlet_tmajor_cuda_block.py capability"
        ),
        "source_campaign_run": False,
        "source_widths_proved_sufficient_for_zero_isolation": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "CATALOG_SCHEMA",
    "CELLS_PER_T_INDEX",
    "DEFAULT_T_INDICES_PER_SHARD",
    "DirichletLatticeCacheError",
    "FOOTER",
    "HEADER",
    "OLD_Q_MAJOR_LATTICE_BYTES",
    "OLD_SEEDED_COMPACT_INPUT_BYTES",
    "PACK_RECEIPT_SCHEMA",
    "PLAN_SCHEMA",
    "PRODUCER_REPLAYED_LATTICE_CERTIFICATE",
    "PRODUCER_SYNTHETIC",
    "ROW_HEADER",
    "ROW_PAYLOAD_BYTES",
    "SOURCE_CACHE_PAYLOAD_BYTES",
    "SOURCE_LATTICE_CELLS",
    "SOURCE_T_INDEX_STOP",
    "T_MAJOR_COMPACT_INPUT_BYTES",
    "benchmark_cache_io",
    "broadcast_plan",
    "build_cache_catalog",
    "cache_shard_filename",
    "capability",
    "inspect_cache_shard",
    "iter_authenticated_cache_rows",
    "iter_catalog_lane_rows",
    "iter_catalog_range_rows",
    "iter_catalog_rows",
    "load_cache_catalog",
    "pack_replayed_lattice_certificates",
    "projection",
    "source_cache_plan",
    "validate_lattice_row",
    "write_synthetic_cache_shard",
]
