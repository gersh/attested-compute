# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed streaming reduction for split-v3 small-q CUDA outputs.

``TGDBSQO3`` is intentionally a verbose arithmetic boundary: it contains one
48-byte complex disk for every character/frequency pair.  A source run would
produce hundreds of terabytes if every batch were retained.  This module
accepts the concatenation of those frames from a pipe, FIFO, or regular file,
checks their exact plan/batch identity and item ordering, and emits one compact
hash commitment.

This is an integrity and coverage adapter, not an analytic checker.  In
particular, SHA-256 does not prove that a disk contains the mathematical DFT
value, and a compact receipt cannot be independently replayed after the raw
stream is discarded.  Arithmetic acceptance still requires the Lean disk
checker/trace boundary (or an independently replayable arithmetic artifact),
and the next small-q stage must apply Platt's time-periodization bound,
untilting, upsampling, zero isolation, and Turing count.  These limitations are
machine-readable in every receipt.
"""

from __future__ import annotations

from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import time
from typing import Any, BinaryIO, NoReturn, Sequence

try:
    import numpy as _np
except ImportError:  # pragma: no cover - exercised by the scalar fallback
    _np = None

from tg_verifier import dirichlet_booker_smallq as base
from tg_verifier import dirichlet_booker_smallq_certified as v2
from tg_verifier.dirichlet_booker_smallq_factored import (
    FORMAT_VERSION,
    REDUCED_SERVICE_OUTPUT_MAGIC,
    SERVICE_OUTPUT_BINDING,
    SERVICE_OUTPUT_MAGIC,
    ParsedCharacterBatch,
    ParsedSharedPlan,
    _character_roster_digest,
    parse_factored_character_batch,
    parse_factored_shared_plan_metadata,
)


AUTHOR = "Gershon Bialer"
ALGORITHM_ID = "platt-booker-smallq-output-stream-mmr-v1"
RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_booker_smallq.output_stream_receipt.v1"
)
LEAF_DOMAIN = b"SparkInterval/DirichletBookerSmallQ/output-frame-leaf/v1\x00"
FRAME_HEADER_DOMAIN = (
    b"SparkInterval/DirichletBookerSmallQ/output-frame-header/v1\x00"
)
ITEM_CHUNK_DOMAIN = (
    b"SparkInterval/DirichletBookerSmallQ/output-item-chunk/v1\x00"
)
NODE_DOMAIN = b"SparkInterval/DirichletBookerSmallQ/output-mmr-node/v1\x00"
ROOT_DOMAIN = b"SparkInterval/DirichletBookerSmallQ/output-mmr-root/v1\x00"
DEFAULT_CHUNK_ITEMS = 1 << 16
MAX_RECEIPT_BYTES = 1024 * 1024


class SmallQOutputStreamError(RuntimeError):
    """A streamed output, source binding, or coverage check failed closed."""


def _fail(message: str) -> NoReturn:
    raise SmallQOutputStreamError(message)


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def _read_exact(stream: BinaryIO, length: int, *, label: str) -> bytes:
    raw = bytearray(length)
    view = memoryview(raw)
    retained = 0
    while retained < length:
        readinto = getattr(stream, "readinto", None)
        if readinto is not None:
            count = readinto(view[retained:])
        else:  # pragma: no cover - standard buffered/raw streams have readinto
            piece = stream.read(length - retained)
            count = len(piece) if piece else 0
            if count:
                view[retained : retained + count] = piece
        if not count:
            _fail(f"truncated {label}")
        retained += count
    return bytes(raw)


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


class _MerkleMountainRange:
    """Streaming Merkle accumulator with a canonical peak commitment.

    Equal-height adjacent peaks are combined immediately.  The final root
    commits to the leaf count and the ordered, height-labelled peaks.  This
    avoids retaining one digest per service batch while keeping the tree
    convention unambiguous for an independent implementation.
    """

    def __init__(self) -> None:
        self._peaks: list[bytes | None] = []
        self.leaf_count = 0

    def append(self, leaf: bytes) -> None:
        if len(leaf) != 32:
            _fail("internal MMR leaf is not a SHA-256 digest")
        node = leaf
        height = 0
        while height < len(self._peaks) and self._peaks[height] is not None:
            left = self._peaks[height]
            assert left is not None
            node = hashlib.sha256(
                NODE_DOMAIN + struct.pack("<Q", height) + left + node
            ).digest()
            self._peaks[height] = None
            height += 1
        if height == len(self._peaks):
            self._peaks.append(node)
        else:
            self._peaks[height] = node
        self.leaf_count += 1

    def root(self) -> bytes:
        digest = hashlib.sha256()
        digest.update(ROOT_DOMAIN)
        digest.update(struct.pack("<Q", self.leaf_count))
        occupied = [
            (height, peak)
            for height, peak in reversed(tuple(enumerate(self._peaks)))
            if peak is not None
        ]
        digest.update(struct.pack("<Q", len(occupied)))
        for height, peak in occupied:
            assert peak is not None
            digest.update(struct.pack("<Q", height))
            digest.update(peak)
        return digest.digest()


def _preflight_batches(
    plan_path: Path, batch_paths: Sequence[Path]
) -> tuple[ParsedSharedPlan, tuple[ParsedCharacterBatch, ...]]:
    """Validate the complete ordered character partition before consuming bytes."""

    plan = parse_factored_shared_plan_metadata(plan_path)
    if not batch_paths:
        _fail("output stream requires at least one character batch")
    batches: list[ParsedCharacterBatch] = []
    roster: list[int] = []
    next_start = 0
    promised_count: int | None = None
    for ordinal, path in enumerate(batch_paths):
        batch = parse_factored_character_batch(path, plan=plan)
        if promised_count is None:
            promised_count = batch.campaign_batch_count
        if (
            batch.batch_ordinal != ordinal
            or batch.campaign_batch_count != promised_count
            or batch.character_start != next_start
        ):
            _fail("character batches are not one ordered contiguous partition")
        roster.extend(character.character_id for character in batch.characters)
        next_start += len(batch.characters)
        batches.append(batch)
    if promised_count != len(batches) or next_start != plan.campaign_character_count:
        _fail("character batch coverage is incomplete")
    if len(set(roster)) != len(roster):
        _fail("character roster contains duplicate ids")
    if _character_roster_digest(roster) != plan.character_roster_sha256:
        _fail("character roster commitment differs from the supplied batches")
    return plan, tuple(batches)


def _validate_numpy_items(
    raw: bytes,
    *,
    flat_start: int,
    frequency_start: int,
    frequency_count: int,
    character_ids: Sequence[int],
) -> None:
    assert _np is not None
    dtype = _np.dtype(
        [
            ("character_id", "<u8"),
            ("index", "<u8"),
            ("real", "<f8"),
            ("imaginary", "<f8"),
            ("radius", "<f8"),
            ("status", "<u4"),
            ("reserved", "<u4"),
        ],
        align=False,
    )
    if dtype.itemsize != v2.OUTPUT_ITEM.size:
        _fail("NumPy output-item ABI differs from TGDBSQO3")
    rows = _np.frombuffer(raw, dtype=dtype)
    positions = _np.arange(flat_start, flat_start + len(rows), dtype=_np.uint64)
    character_positions = positions // _np.uint64(frequency_count)
    expected_ids = _np.asarray(character_ids, dtype=_np.uint64)[character_positions]
    expected_indices = (
        _np.uint64(frequency_start) + positions % _np.uint64(frequency_count)
    )
    finite = (
        _np.isfinite(rows["real"])
        & _np.isfinite(rows["imaginary"])
        & _np.isfinite(rows["radius"])
    )
    if not (
        _np.array_equal(rows["character_id"], expected_ids)
        and _np.array_equal(rows["index"], expected_indices)
        and bool(_np.all(finite))
        and bool(_np.all(rows["radius"] >= 0.0))
        and bool(_np.all(rows["status"] == 0))
        and bool(_np.all(rows["reserved"] == 0))
    ):
        _fail("TGDBSQO3 item identity, finiteness, radius, or status differs")


def _validate_scalar_items(
    raw: bytes,
    *,
    flat_start: int,
    frequency_start: int,
    frequency_count: int,
    character_ids: Sequence[int],
) -> None:
    for relative, row in enumerate(v2.OUTPUT_ITEM.iter_unpack(raw)):
        character_id, index, real, imaginary, radius, status, reserved = row
        flat = flat_start + relative
        if (
            character_id != character_ids[flat // frequency_count]
            or index != frequency_start + flat % frequency_count
            or not all(math.isfinite(value) for value in (real, imaginary, radius))
            or radius < 0.0
            or status != 0
            or reserved != 0
        ):
            _fail("TGDBSQO3 item identity, finiteness, radius, or status differs")


def _validate_and_hash_item_chunk(
    raw: bytes,
    *,
    frame_ordinal: int,
    chunk_ordinal: int,
    flat_start: int,
    frequency_start: int,
    frequency_count: int,
    character_ids: Sequence[int],
    backend: str,
) -> bytes:
    """Worker task: one structural pass and one domain-separated SHA pass."""

    if backend == "numpy":
        _validate_numpy_items(
            raw,
            flat_start=flat_start,
            frequency_start=frequency_start,
            frequency_count=frequency_count,
            character_ids=character_ids,
        )
    else:
        _validate_scalar_items(
            raw,
            flat_start=flat_start,
            frequency_start=frequency_start,
            frequency_count=frequency_count,
            character_ids=character_ids,
        )
    return hashlib.sha256(
        ITEM_CHUNK_DOMAIN
        + struct.pack("<QQQ", frame_ordinal, chunk_ordinal, flat_start)
        + raw
    ).digest()


def reduce_factored_service_output_stream(
    plan_path: Path,
    batch_paths: Sequence[Path],
    stream: BinaryIO,
    *,
    receipt_path: Path | None = None,
    chunk_items: int = DEFAULT_CHUNK_ITEMS,
    require_eof: bool = True,
    backend: str = "auto",
    worker_count: int | None = None,
) -> dict[str, Any]:
    """Validate concatenated ``TGDBSQO3`` frames and emit one compact receipt.

    ``backend='auto'`` uses vectorized NumPy structural checks when available.
    The scalar backend is dependency-free and semantically identical.  The
    stream is consumed exactly once and never retained by this function.
    """

    if (
        isinstance(chunk_items, bool)
        or not isinstance(chunk_items, int)
        or chunk_items <= 0
    ):
        _fail("chunk_items must be a positive integer")
    if backend not in {"auto", "numpy", "scalar"}:
        _fail("backend must be auto, numpy, or scalar")
    if backend == "numpy" and _np is None:
        _fail("NumPy backend requested but NumPy is unavailable")
    selected_backend = (
        "numpy" if backend == "auto" and _np is not None else backend
    )
    if selected_backend == "auto":
        selected_backend = "scalar"
    if worker_count is None:
        worker_count = (
            min(8, os.cpu_count() or 1) if selected_backend == "numpy" else 1
        )
    if (
        isinstance(worker_count, bool)
        or not isinstance(worker_count, int)
        or worker_count <= 0
    ):
        _fail("worker_count must be a positive integer")
    if selected_backend == "scalar" and worker_count != 1:
        _fail("the scalar backend requires exactly one worker")

    plan, batches = _preflight_batches(plan_path, batch_paths)
    canonical = base.transform_parameters(plan.q)
    source_parameters_match = (
        plan.transform_length == canonical.transform_length
        and plan.frequency_start == 0
        and plan.frequency_count == canonical.transform_length
        and plan.eta == canonical.eta
        and plan.a == canonical.a
        and plan.b == canonical.b
        and plan.run_dft
    )
    source_samples = (
        plan.campaign_character_count * canonical.sample_count
        if source_parameters_match
        else None
    )
    mmr = _MerkleMountainRange()
    frame_count = 0
    item_count = 0
    raw_bytes = 0
    finite_terms_reported = 0
    butterflies = 0
    cuda_elapsed = 0
    output_mode: str | None = None
    started = time.perf_counter_ns()

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        for ordinal, batch in enumerate(batches):
          header_raw = _read_exact(stream, v2.OUTPUT_HEADER.size, label="TGDBSQO3 header")
          binding_raw = _read_exact(
              stream, SERVICE_OUTPUT_BINDING.size, label="TGDBSQO3 binding"
          )
          raw_bytes += len(header_raw) + len(binding_raw)
          (
              magic,
              version,
              q,
              batch_count,
              run_dft,
              frequency_start,
              frequency_count,
              terms,
              frame_butterflies,
              elapsed,
              status_or,
              reserved,
          ) = v2.OUTPUT_HEADER.unpack(header_raw)
          binding = SERVICE_OUTPUT_BINDING.unpack(binding_raw)
          expected_binding = (
              plan.sha256,
              batch.sha256,
              batch.character_start,
              batch.campaign_character_count,
              batch.batch_ordinal,
              batch.campaign_batch_count,
          )
          if magic == SERVICE_OUTPUT_MAGIC:
              frame_mode = "complete_transform"
              expected_frequency_count = plan.frequency_count
          elif magic == REDUCED_SERVICE_OUTPUT_MAGIC:
              if not source_parameters_match:
                  _fail("TGDBSQR3 requires the exact canonical source parameters")
              frame_mode = "source_samples_only"
              expected_frequency_count = canonical.sample_count
          else:
              frame_mode = "invalid"
              expected_frequency_count = 0
          if output_mode is None:
              output_mode = frame_mode
          elif output_mode != frame_mode:
              _fail("service output stream mixes complete and reduced frame modes")
          expected_butterflies = (
              batch_count
              * (plan.transform_length // 2)
              * (plan.transform_length.bit_length() - 1)
              if run_dft
              else 0
          )
          if (
              frame_mode == "invalid"
              or version != FORMAT_VERSION
              or q != plan.q
              or batch_count != len(batch.characters)
              or run_dft != int(plan.run_dft)
              or frequency_start != plan.frequency_start
              or frequency_count != expected_frequency_count
              or binding != expected_binding
              or frame_butterflies != expected_butterflies
              or status_or != 0
              or reserved != 0
          ):
              _fail("TGDBSQO3 header, binding, shape, or aggregate status differs")
  
          characters: Sequence[int] = tuple(
              character.character_id for character in batch.characters
          )
          if selected_backend == "numpy":
              assert _np is not None
              characters = _np.asarray(characters, dtype=_np.uint64)
          frame_items = batch_count * frequency_count
          frame_mmr = _MerkleMountainRange()
          frame_mmr.append(
              hashlib.sha256(
                  FRAME_HEADER_DOMAIN
                  + struct.pack("<Q", ordinal)
                  + header_raw
                  + binding_raw
              ).digest()
          )
          pending: deque[Future[bytes]] = deque()
          flat = 0
          chunk_ordinal = 0
          # At most two chunks per worker remain live.  The bounded queue overlaps
          # pipe reads, vector checks, and SHA-NI without retaining a frame.
          maximum_pending = max(1, 2 * worker_count)
          while flat < frame_items:
              count = min(chunk_items, frame_items - flat)
              raw = _read_exact(
                  stream,
                  count * v2.OUTPUT_ITEM.size,
                  label="TGDBSQO3 item chunk",
              )
              raw_bytes += len(raw)
              pending.append(
                  executor.submit(
                      _validate_and_hash_item_chunk,
                      raw,
                      frame_ordinal=ordinal,
                      chunk_ordinal=chunk_ordinal,
                      flat_start=flat,
                      frequency_start=frequency_start,
                      frequency_count=frequency_count,
                      character_ids=characters,
                      backend=selected_backend,
                  )
              )
              if len(pending) >= maximum_pending:
                  frame_mmr.append(pending.popleft().result())
              flat += count
              chunk_ordinal += 1
          while pending:
              frame_mmr.append(pending.popleft().result())
  
          frame_sha = frame_mmr.root()
          leaf = hashlib.sha256(
              LEAF_DOMAIN
              + struct.pack("<Q", ordinal)
              + batch.sha256
              + binding_raw
              + frame_sha
          ).digest()
          mmr.append(leaf)
          frame_count += 1
          item_count += frame_items
          finite_terms_reported += terms
          butterflies += frame_butterflies
          cuda_elapsed += elapsed
  
    if require_eof and stream.read(1):
        _fail("TGDBSQO3 stream has trailing bytes after the complete batch partition")

    elapsed = time.perf_counter_ns() - started
    receipt: dict[str, Any] = {
        "algorithm_id": ALGORITHM_ID,
        "arithmetic_containment_replayed": False,
        "atom_id": base.ATOM_ID,
        "author": AUTHOR,
        "backend": selected_backend,
        "batch_count": frame_count,
        "butterflies_reported_and_shape_checked": butterflies,
        "character_count": plan.campaign_character_count,
        "character_roster_sha256": plan.character_roster_sha256.hex(),
        "classification": "streaming_coverage_and_integrity_only_not_atom_discharge",
        "compact_receipt_replayable_without_raw_stream": False,
        "commitment_chunk_items": chunk_items,
        "cuda_elapsed_nanoseconds_reported_not_trusted": cuda_elapsed,
        "external_atom_discharged": False,
        "finite_gaussian_terms_reported_not_recomputed": finite_terms_reported,
        "frame_mmr_leaf_count": mmr.leaf_count,
        "frame_mmr_sha256": mmr.root().hex(),
        "frequency_coverage": (
            "0..transform_length-1"
            if output_mode == "complete_transform"
            else "0..canonical_source_sample_count-1"
        ),
        "full_character_partition_checked": True,
        "item_count": item_count,
        "item_identity_finiteness_radius_and_status_checked": True,
        "kind": RECEIPT_SCHEMA,
        "maximum_pending_output_bytes": (
            max(1, 2 * worker_count) * chunk_items * v2.OUTPUT_ITEM.size
        ),
        "next_analytic_stage": (
            "apply 2*pi/b scaling, Platt time-periodization enclosure, positive "
            "untilting, then upsampling/exception/zero/Turing closure"
        ),
        "output_stream_commitment_kind": (
            "sha256_merkle_mountain_range_over_bound_headers_and_fixed_item_chunks"
        ),
        "output_stream_mmr_sha256": mmr.root().hex(),
        "output_mode": output_mode,
        "persistent_raw_output_bytes_required": 0,
        "plan_sha256": plan.sha256.hex(),
        "production_accept": False,
        "q": plan.q,
        "raw_stream_bytes_consumed": raw_bytes,
        "receipt_limitation": (
            "hashes bind bytes observed in this run but do not prove disk arithmetic; "
            "discarded bytes require trusted-run evidence or a separately retained "
            "replay artifact"
        ),
        "source_completed_sample_items_if_canonical": source_samples,
        "source_parameters_match": source_parameters_match,
        "stream_elapsed_nanoseconds": elapsed,
        "stream_megabytes_per_second": (
            raw_bytes * 1000.0 / max(elapsed, 1)
        ),
        "transform_length": plan.transform_length,
        "trusted_execution_evidence_required_after_raw_discard": True,
        "worker_count": worker_count,
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical_json_bytes(receipt)).hexdigest()
    encoded = canonical_json_bytes(receipt)
    if len(encoded) > MAX_RECEIPT_BYTES:
        _fail("internal compact receipt exceeds its one-MiB bound")
    if receipt_path is not None:
        _atomic_write(receipt_path, encoded)
    return receipt


def reduce_factored_service_output_path(
    plan_path: Path,
    batch_paths: Sequence[Path],
    stream_path: Path,
    **kwargs: Any,
) -> dict[str, Any]:
    """Path wrapper; ``stream_path`` may name a FIFO as well as a file."""

    with stream_path.open("rb", buffering=0) as stream:
        return reduce_factored_service_output_stream(
            plan_path, batch_paths, stream, **kwargs
        )


__all__ = [
    "ALGORITHM_ID",
    "DEFAULT_CHUNK_ITEMS",
    "MAX_RECEIPT_BYTES",
    "RECEIPT_SCHEMA",
    "SmallQOutputStreamError",
    "canonical_json_bytes",
    "reduce_factored_service_output_path",
    "reduce_factored_service_output_stream",
]
