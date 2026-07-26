# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Framed strict-sign transport for the factored small-q CUDA service.

``TGDBSPK1`` is a transport format, not a source certificate.  It lets the
production runner apply the same sufficient sign test as the Python
``TGDBSQR3`` reducer and send two bits, rather than a 48-byte complex disk,
for each character/source-sample coordinate.

Every frame binds the exact plan, batch, time-tail control, control replay
receipt, batch partition, both roster identities, span, mode, pinset, and
compact-state source binding.  Payloads are character-major/sample-major,
four little-endian two-bit codes per byte.  Code 3 and nonzero padding are
rejected.  Frame hashes form a chain, and a terminal record commits to the
complete byte stream and exact coverage.

Production mode 1 identifies the host classifier and production mode 3
identifies the CUDA classifier.  The reducer requires an expected packing
location and will not substitute one for the other.  The compact arithmetic
state is intentionally independent of transport location when the sign bytes
are identical; its receipt retains the location and complete stream digest.

The CPU producer below is an executable protocol reference and differential
test oracle for the CUDA runner.  It applies exactly

``boundary = nextafter(radius + threshold, +infinity)``

and emits 1 for ``real < -boundary``, 2 for ``real > boundary``, and 0
otherwise.  Neither producer nor consumer replays the DFT containment,
character exponent semantics, analytic seed values, zero multiplicities,
Turing bounds, or GRH.  Source admission is deliberately always false.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import mmap
import os
from pathlib import Path
import struct
import time
from typing import Any, BinaryIO, Iterator, Mapping, NoReturn, Sequence

from tg_verifier import dirichlet_booker_smallq_certified as v2
from tg_verifier import dirichlet_booker_smallq_compact_v3 as adapter
from tg_verifier import dirichlet_booker_smallq_semantic_reducer as semantic
from tg_verifier import dirichlet_compact_state_streaming_v3 as compact
from tg_verifier.dirichlet_booker_smallq_compact_v3 import (
    SmallQCompactV3Pins,
)
from tg_verifier.dirichlet_booker_smallq_factored import (
    FORMAT_VERSION,
    REDUCED_SERVICE_OUTPUT_MAGIC,
    SERVICE_OUTPUT_BINDING,
)


AUTHOR = "Gershon Bialer"
PACKER_ALGORITHM_ID = "platt-booker-smallq-runner-strict-sign-pack-v1"
REDUCER_ALGORITHM_ID = "platt-booker-smallq-packed-to-compact-v3-v1"
RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_booker_smallq.packed_compact_receipt.v1"
)

FRAME_MAGIC = b"TGDBSPK1"
END_MAGIC = b"TGDBSPE1"
TRAILER_MAGIC = b"TGDBSPT1"
FORMAT_VERSION_V1 = 1
HOST_PRODUCTION_MODE = 1
PRODUCTION_MODE = HOST_PRODUCTION_MODE
STRUCTURAL_KAT_MODE = 2
DEVICE_PRODUCTION_MODE = 3
BITS_PER_CODE = 2
ZERO_DIGEST = bytes(32)

# magic; version/mode/q/bits; batch characters/source span/payload/work;
# aggregate status and reserved.
FRAME_PREFIX = struct.Struct("<8sIIII9QII")
# character start/campaign count/batch ordinal/campaign batch count.
FRAME_BATCH_BINDING = struct.Struct("<4Q")
# plan, batch, control, control receipt, partition, plan roster, compact
# roster, pinset, source binding, and preceding frame hash.
FRAME_DIGESTS = struct.Struct("<" + "32s" * 10)
# magic, version, reserved, frame ordinal, payload bytes, payload SHA-256,
# and domain-separated complete-frame SHA-256.
FRAME_TRAILER = struct.Struct("<8sIIQQ32s32s")
# magic, version, reserved, frame count, item count, last-frame SHA-256, and
# SHA-256 of every frame byte including trailers.
STREAM_END = struct.Struct("<8sIIQQ32s32s")

FRAME_DOMAIN = (
    b"SparkInterval/DirichletBookerSmallQ/packed-sign-frame/v1\x00"
)

DEFAULT_CHUNK_ITEMS = 1 << 16
MAXIMUM_CHUNK_ITEMS = 1 << 20


class SmallQPackedStreamV1Error(RuntimeError):
    """A packed frame, source disk stream, or exact binding failed closed."""


def _fail(message: str) -> NoReturn:
    raise SmallQPackedStreamV1Error(message)


def _read_exact(source: BinaryIO, count: int, *, label: str) -> bytes:
    raw = source.read(count)
    if len(raw) != count:
        _fail(f"truncated {label}")
    return raw


def _bytes_digest(name: str, value: str) -> bytes:
    try:
        raw = bytes.fromhex(value)
    except (TypeError, ValueError) as error:
        raise SmallQPackedStreamV1Error(
            f"{name} is not lowercase SHA-256"
        ) from error
    if len(raw) != 32 or value != raw.hex():
        _fail(f"{name} is not lowercase SHA-256")
    return raw


def _mode(pins: SmallQCompactV3Pins, packing_location: str = "host") -> int:
    if packing_location not in {"host", "device"}:
        _fail("packed stream packing location must be host or device")
    if pins.structural_bounded_span_kat:
        if packing_location != "host":
            _fail(
                "device packing is admitted only for the full production span"
            )
        return STRUCTURAL_KAT_MODE
    return (
        HOST_PRODUCTION_MODE
        if packing_location == "host"
        else DEVICE_PRODUCTION_MODE
    )


@dataclass(frozen=True)
class _Prepared:
    plan: Any
    batches: tuple[Any, ...]
    parameters: Any
    controls: Any
    control_receipt: Mapping[str, Any]
    roster_sha256: str
    batch_partition_sha256: bytes
    sample_start: int
    sample_count: int
    pins: SmallQCompactV3Pins
    source_binding: str
    snapshots: tuple[Any, ...]
    input_paths: tuple[Path, ...]


def _prepare(
    plan_path: Path,
    batch_paths: Sequence[Path],
    control_path: Path,
    control_receipt_path: Path,
    pins: SmallQCompactV3Pins,
) -> _Prepared:
    """Replay the exact compact-v3 preflight without accepting source truth."""

    adapter._validate_pins(pins)
    input_paths = (
        Path(plan_path),
        *(Path(path) for path in batch_paths),
        Path(control_path),
        Path(control_receipt_path),
    )
    for index, path in enumerate(input_paths):
        adapter._require_regular(path, label=f"packed stream input {index}")
    plan, batches, parameters, parity_counts = (
        adapter._canonical_plan_and_batches(
            Path(plan_path), tuple(Path(path) for path in batch_paths)
        )
    )
    batch_partition_sha256 = semantic._batch_partition_digest(batches)
    _identities, roster_sha256 = adapter._canonical_roster(
        q=plan.q,
        batches=batches,
        campaign_character_count=plan.campaign_character_count,
    )
    control = semantic.load_time_tail_control_metadata(Path(control_path))
    semantic._validate_control_binding(
        control,
        plan=plan,
        parameters=parameters,
        parity_counts=parity_counts,
        batch_partition_sha256=batch_partition_sha256,
    )
    semantic._validate_control_words(control)
    control_receipt = semantic._validate_control_receipt(
        Path(control_receipt_path),
        control=control,
        plan=plan,
        parameters=parameters,
        parity_counts=parity_counts,
        batch_partition_sha256=batch_partition_sha256,
    )

    first = pins.first_t_numerator
    stop = pins.stop_t_numerator
    step = compact.SOURCE_SAMPLE_NUMERATOR
    full_stop = parameters.sample_count * step
    if (
        first % step
        or stop % step
        or not 0 <= first < stop <= full_stop
    ):
        _fail("packed stream span is outside the exact small-q source grid")
    if (
        not pins.structural_bounded_span_kat
        and (first != 0 or stop != full_stop)
    ):
        _fail("production packed stream requires the full source span")

    actual = SmallQCompactV3Pins(
        q=plan.q,
        shared_plan_cache_sha256=plan.sha256.hex(),
        time_tail_control_sha256=control.sha256,
        time_tail_control_receipt_sha256=str(
            control_receipt["receipt_sha256"]
        ),
        character_batch_partition_sha256=batch_partition_sha256.hex(),
        plan_character_roster_sha256=plan.character_roster_sha256.hex(),
        compact_complete_roster_sha256=roster_sha256,
        first_t_numerator=first,
        stop_t_numerator=stop,
        structural_bounded_span_kat=pins.structural_bounded_span_kat,
    )
    if actual != pins:
        _fail("packed stream inputs differ from the external pinset")

    expected_input_sha256 = (
        plan.sha256.hex(),
        *(batch.sha256.hex() for batch in batches),
        control.sha256,
        hashlib.sha256(
            semantic.canonical_json_bytes(control_receipt)
        ).hexdigest(),
    )
    snapshots = tuple(
        adapter._snapshot(
            path,
            label=f"packed stream input {index}",
            expected_sha256=expected_input_sha256[index],
        )
        for index, path in enumerate(input_paths)
    )
    return _Prepared(
        plan=plan,
        batches=tuple(batches),
        parameters=parameters,
        controls=control,
        control_receipt=control_receipt,
        roster_sha256=roster_sha256,
        batch_partition_sha256=batch_partition_sha256,
        sample_start=first // step,
        sample_count=(stop - first) // step,
        pins=actual,
        source_binding=adapter._source_binding_sha256(actual),
        snapshots=snapshots,
        input_paths=input_paths,
    )


def _frame_bytes(
    prepared: _Prepared,
    batch: Any,
    *,
    terms: int,
    butterflies: int,
    elapsed: int,
    previous_frame: bytes,
    packing_location: str = "host",
) -> tuple[bytes, bytes, bytes]:
    item_count = len(batch.characters) * prepared.sample_count
    payload_bytes = (item_count + 3) // 4
    prefix = FRAME_PREFIX.pack(
        FRAME_MAGIC,
        FORMAT_VERSION_V1,
        _mode(prepared.pins, packing_location),
        prepared.plan.q,
        BITS_PER_CODE,
        len(batch.characters),
        prepared.sample_start,
        prepared.sample_count,
        prepared.pins.first_t_numerator,
        prepared.pins.stop_t_numerator,
        payload_bytes,
        terms,
        butterflies,
        elapsed,
        0,
        0,
    )
    binding = FRAME_BATCH_BINDING.pack(
        batch.character_start,
        batch.campaign_character_count,
        batch.batch_ordinal,
        batch.campaign_batch_count,
    )
    digests = FRAME_DIGESTS.pack(
        prepared.plan.sha256,
        batch.sha256,
        _bytes_digest("control SHA-256", prepared.controls.sha256),
        _bytes_digest(
            "control receipt SHA-256",
            str(prepared.control_receipt["receipt_sha256"]),
        ),
        prepared.batch_partition_sha256,
        prepared.plan.character_roster_sha256,
        _bytes_digest("compact roster SHA-256", prepared.roster_sha256),
        _bytes_digest(
            "pinset SHA-256", adapter.pinset_sha256(prepared.pins)
        ),
        _bytes_digest("source binding SHA-256", prepared.source_binding),
        previous_frame,
    )
    return prefix, binding, digests


class _FramePayloadWriter:
    """Pack codes and hash both payload and complete frame incrementally."""

    def __init__(
        self,
        output: BinaryIO,
        stream_digest: Any,
        frame_digest: Any,
    ) -> None:
        self.output = output
        self.stream_digest = stream_digest
        self.frame_digest = frame_digest
        self.payload_digest = hashlib.sha256()
        self.pending: list[int] = []
        self.bytes_written = 0

    def _write(self, raw: bytes) -> None:
        if not raw:
            return
        self.output.write(raw)
        self.stream_digest.update(raw)
        self.frame_digest.update(raw)
        self.payload_digest.update(raw)
        self.bytes_written += len(raw)

    def append(self, codes: Any) -> None:
        if semantic._np is not None and isinstance(
            codes, semantic._np.ndarray
        ):
            values = codes.astype(semantic._np.uint8, copy=False)
            for value in values:
                self._append_one(int(value))
            return
        for value in codes:
            self._append_one(int(value))

    def _append_one(self, code: int) -> None:
        if code not in (
            semantic.AMBIGUOUS_CODE,
            semantic.NEGATIVE_CODE,
            semantic.POSITIVE_CODE,
        ):
            _fail("strict-sign producer attempted to emit a reserved code")
        self.pending.append(code)
        if len(self.pending) == 4:
            self._write(
                bytes(
                    (
                        self.pending[0]
                        | self.pending[1] << 2
                        | self.pending[2] << 4
                        | self.pending[3] << 6,
                    )
                )
            )
            self.pending.clear()

    def finish(self) -> tuple[bytes, int]:
        if self.pending:
            encoded = 0
            for ordinal, code in enumerate(self.pending):
                encoded |= code << (2 * ordinal)
            self._write(bytes((encoded,)))
            self.pending.clear()
        return self.payload_digest.digest(), self.bytes_written


def pack_factored_service_stream_v1(
    plan_path: Path,
    batch_paths: Sequence[Path],
    control_path: Path,
    control_receipt_path: Path,
    raw_stream: BinaryIO,
    packed_stream: BinaryIO,
    *,
    pins: SmallQCompactV3Pins,
    chunk_items: int = DEFAULT_CHUNK_ITEMS,
    backend: str = "auto",
) -> dict[str, Any]:
    """CPU reference: convert complete ``TGDBSQR3`` frames to ``TGDBSPK1``."""

    if (
        isinstance(chunk_items, bool)
        or not isinstance(chunk_items, int)
        or not 0 < chunk_items <= MAXIMUM_CHUNK_ITEMS
    ):
        _fail("packed stream chunk_items is outside its fixed bound")
    if backend not in {"auto", "numpy", "scalar"}:
        _fail("packed stream backend must be auto, numpy, or scalar")
    if backend == "numpy" and semantic._np is None:
        _fail("NumPy backend requested but NumPy is unavailable")
    selected_backend = (
        "numpy"
        if backend == "auto" and semantic._np is not None
        else backend
    )
    if selected_backend == "auto":
        selected_backend = "scalar"

    prepared = _prepare(
        plan_path, batch_paths, control_path, control_receipt_path, pins
    )
    control_snapshot = prepared.snapshots[len(prepared.batches) + 1]
    control_source, controls = adapter._bound_control_records(
        prepared.controls,
        snapshot=control_snapshot,
        backend=selected_backend,
    )
    raw_digest = hashlib.sha256()
    stream_digest = hashlib.sha256()
    previous_frame = ZERO_DIGEST
    raw_bytes = 0
    packed_bytes = 0
    item_count = 0
    counts = [0, 0, 0]
    finite_terms = 0
    butterflies_total = 0
    cuda_elapsed = 0
    started = time.perf_counter_ns()
    try:
        for ordinal, batch in enumerate(prepared.batches):
            header_raw = _read_exact(
                raw_stream, v2.OUTPUT_HEADER.size, label="TGDBSQR3 header"
            )
            binding_raw = _read_exact(
                raw_stream,
                SERVICE_OUTPUT_BINDING.size,
                label="TGDBSQR3 binding",
            )
            raw_digest.update(header_raw)
            raw_digest.update(binding_raw)
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
                butterflies,
                elapsed,
                status_or,
                reserved,
            ) = v2.OUTPUT_HEADER.unpack(header_raw)
            expected_binding = (
                prepared.plan.sha256,
                batch.sha256,
                batch.character_start,
                batch.campaign_character_count,
                batch.batch_ordinal,
                batch.campaign_batch_count,
            )
            expected_butterflies = (
                batch_count
                * (prepared.plan.transform_length // 2)
                * (prepared.plan.transform_length.bit_length() - 1)
            )
            if (
                magic != REDUCED_SERVICE_OUTPUT_MAGIC
                or version != FORMAT_VERSION
                or q != prepared.plan.q
                or batch_count != len(batch.characters)
                or run_dft != 1
                or frequency_start != prepared.sample_start
                or frequency_count != prepared.sample_count
                or SERVICE_OUTPUT_BINDING.unpack(binding_raw)
                != expected_binding
                or butterflies != expected_butterflies
                or status_or != 0
                or reserved != 0
            ):
                _fail(
                    "TGDBSQR3 packed frame identity, span, binding, or "
                    "aggregate status differs"
                )
            prefix, binding, digests = _frame_bytes(
                prepared,
                batch,
                terms=terms,
                butterflies=butterflies,
                elapsed=elapsed,
                previous_frame=previous_frame,
            )
            frame_digest = hashlib.sha256(FRAME_DOMAIN)
            for raw in (prefix, binding, digests):
                packed_stream.write(raw)
                stream_digest.update(raw)
                frame_digest.update(raw)
                packed_bytes += len(raw)
            writer = _FramePayloadWriter(
                packed_stream, stream_digest, frame_digest
            )
            frame_items = batch_count * prepared.sample_count
            if selected_backend == "numpy":
                assert semantic._np is not None
                character_ids: Any = semantic._np.asarray(
                    [
                        character.character_id
                        for character in batch.characters
                    ],
                    dtype=semantic._np.uint64,
                )
                parities: Any = semantic._np.asarray(
                    [character.parity for character in batch.characters],
                    dtype=semantic._np.uint64,
                )
            flat = 0
            while flat < frame_items:
                count = min(chunk_items, frame_items - flat)
                raw = _read_exact(
                    raw_stream,
                    count * v2.OUTPUT_ITEM.size,
                    label="TGDBSQR3 item chunk",
                )
                raw_digest.update(raw)
                raw_bytes += len(raw)
                if selected_backend == "numpy":
                    codes, local = semantic._numpy_codes(
                        raw,
                        flat_start=flat,
                        sample_count=prepared.sample_count,
                        sample_start=prepared.sample_start,
                        character_ids=character_ids,
                        parities=parities,
                        controls=controls,
                    )
                else:
                    codes, local = semantic._scalar_codes(
                        raw,
                        flat_start=flat,
                        sample_count=prepared.sample_count,
                        sample_start=prepared.sample_start,
                        characters=batch.characters,
                        control_mapping=controls,
                    )
                for code in range(3):
                    counts[code] += local[code]
                writer.append(codes)
                flat += count
            payload_sha256, payload_bytes = writer.finish()
            expected_payload_bytes = (frame_items + 3) // 4
            if payload_bytes != expected_payload_bytes:
                _fail("internal packed payload byte count differs")
            packed_bytes += payload_bytes
            complete_frame = frame_digest.digest()
            trailer = FRAME_TRAILER.pack(
                TRAILER_MAGIC,
                FORMAT_VERSION_V1,
                0,
                ordinal,
                payload_bytes,
                payload_sha256,
                complete_frame,
            )
            packed_stream.write(trailer)
            stream_digest.update(trailer)
            packed_bytes += len(trailer)
            previous_frame = complete_frame
            item_count += frame_items
            finite_terms += terms
            butterflies_total += butterflies
            cuda_elapsed += elapsed
        if raw_stream.read(1):
            _fail("TGDBSQR3 source stream has trailing bytes")
        expected_items = (
            prepared.plan.campaign_character_count * prepared.sample_count
        )
        if item_count != expected_items or sum(counts) != expected_items:
            _fail("TGDBSQR3 packed source coverage totals differ")
        if (
            adapter._stat_identity(os.fstat(control_source.fileno()))
            != control_snapshot.identity
        ):
            _fail("time-tail control changed during packed sign decisions")
        adapter._verify_snapshots(prepared.snapshots)
        end = STREAM_END.pack(
            END_MAGIC,
            FORMAT_VERSION_V1,
            0,
            len(prepared.batches),
            item_count,
            previous_frame,
            stream_digest.digest(),
        )
        packed_stream.write(end)
        packed_bytes += len(end)
        complete_stream_digest = stream_digest.copy()
        complete_stream_digest.update(end)
        if hasattr(packed_stream, "flush"):
            packed_stream.flush()
    finally:
        if (
            semantic._np is not None
            and isinstance(controls, semantic._np.memmap)
        ):
            controls._mmap.close()
        else:
            controls.close()
        control_source.close()

    elapsed_total = time.perf_counter_ns() - started
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_booker_smallq."
            "packed_sign_stream_producer.v1"
        ),
        "schema_version": 1,
        "algorithm_id": PACKER_ALGORITHM_ID,
        "author": AUTHOR,
        "classification": (
            "runner_side_strict_sign_transport_not_source_or_dft_replay"
        ),
        "q": prepared.plan.q,
        "mode": _mode(prepared.pins, "host"),
        "packing_location": "host",
        "pinset_sha256": adapter.pinset_sha256(prepared.pins),
        "source_binding_sha256": prepared.source_binding,
        "frame_count": len(prepared.batches),
        "item_count": item_count,
        "raw_disk_stream_sha256": raw_digest.hexdigest(),
        "raw_disk_stream_bytes_consumed": raw_bytes,
        "packed_stream_sha256": complete_stream_digest.hexdigest(),
        "packed_stream_bytes_emitted": packed_bytes,
        "ambiguous_sample_count": counts[0],
        "negative_sample_count": counts[1],
        "positive_sample_count": counts[2],
        "finite_terms_reported_not_recomputed": finite_terms,
        "butterflies_reported_and_shape_checked": butterflies_total,
        "cuda_elapsed_nanoseconds_reported_not_trusted": cuda_elapsed,
        "packing_elapsed_nanoseconds": elapsed_total,
        "strict_boundary_rule": (
            "nextafter(radius + threshold, +infinity)"
        ),
        "four_little_endian_two_bit_codes_per_byte": True,
        "frame_hash_chain_complete": True,
        "terminal_coverage_and_eof_record_emitted": True,
        "raw_disk_artifact_materialized": False,
        "packed_sign_artifact_required": False,
        "dft_arithmetic_containment_replayed": False,
        "analytic_seed_values_replayed": False,
        "character_exponent_semantics_replayed": False,
        "zero_multiplicity_realized": False,
        "turing_closure_realized": False,
        "source_admission_enabled": False,
        "external_atom_discharged": False,
        "production_ready": False,
    }


def _expected_frame_parts(
    prepared: _Prepared,
    batch: Any,
    *,
    terms: int,
    butterflies: int,
    elapsed: int,
    previous_frame: bytes,
    packing_location: str,
) -> tuple[bytes, bytes, bytes]:
    return _frame_bytes(
        prepared,
        batch,
        terms=terms,
        butterflies=butterflies,
        elapsed=elapsed,
        previous_frame=previous_frame,
        packing_location=packing_location,
    )


@dataclass
class _PackedRun:
    completed: bool = False
    stream_bytes: int = 0
    frame_count: int = 0
    item_count: int = 0
    ambiguous: int = 0
    negative: int = 0
    positive: int = 0
    finite_terms: int = 0
    butterflies: int = 0
    cuda_elapsed: int = 0
    stream_sha256: str = ""


def reduce_packed_stream_to_compact_v3(
    plan_path: Path,
    batch_paths: Sequence[Path],
    control_path: Path,
    control_receipt_path: Path,
    packed_stream: BinaryIO,
    state_path: Path,
    *,
    pins: SmallQCompactV3Pins,
    receipt_path: Path | None = None,
    chunk_items: int = DEFAULT_CHUNK_ITEMS,
    maximum_state_bytes: int = compact.DEFAULT_MAXIMUM_ARTIFACT_BYTES,
    expected_packing_location: str = "host",
) -> dict[str, Any]:
    """Validate ``TGDBSPK1`` and stream its codes directly into ``TGDCSB03``."""

    if (
        isinstance(chunk_items, bool)
        or not isinstance(chunk_items, int)
        or not 0 < chunk_items <= MAXIMUM_CHUNK_ITEMS
    ):
        _fail("packed compact chunk_items is outside its fixed bound")
    if expected_packing_location not in {"host", "device"}:
        _fail("expected packing location must be host or device")
    prepared = _prepare(
        plan_path, batch_paths, control_path, control_receipt_path, pins
    )
    adapter._reject_aliases(
        inputs=prepared.input_paths,
        state_path=Path(state_path),
        receipt_path=None if receipt_path is None else Path(receipt_path),
    )
    run = _PackedRun()
    whole_digest = hashlib.sha256()
    previous_frame = ZERO_DIGEST

    def code_chunks() -> Iterator[bytes]:
        nonlocal previous_frame
        for ordinal, batch in enumerate(prepared.batches):
            prefix = _read_exact(
                packed_stream, FRAME_PREFIX.size, label="TGDBSPK1 prefix"
            )
            binding = _read_exact(
                packed_stream,
                FRAME_BATCH_BINDING.size,
                label="TGDBSPK1 batch binding",
            )
            digests = _read_exact(
                packed_stream,
                FRAME_DIGESTS.size,
                label="TGDBSPK1 digest binding",
            )
            (
                magic,
                version,
                mode,
                q,
                bits,
                batch_count,
                frequency_start,
                frequency_count,
                first_t,
                stop_t,
                payload_bytes,
                terms,
                butterflies,
                elapsed,
                status_or,
                reserved,
            ) = FRAME_PREFIX.unpack(prefix)
            expected_butterflies = (
                len(batch.characters)
                * (prepared.plan.transform_length // 2)
                * (prepared.plan.transform_length.bit_length() - 1)
            )
            expected_prefix, expected_binding, expected_digests = (
                _expected_frame_parts(
                    prepared,
                    batch,
                    terms=terms,
                    butterflies=butterflies,
                    elapsed=elapsed,
                    previous_frame=previous_frame,
                    packing_location=expected_packing_location,
                )
            )
            frame_items = len(batch.characters) * prepared.sample_count
            if (
                magic != FRAME_MAGIC
                or version != FORMAT_VERSION_V1
                or mode
                != _mode(prepared.pins, expected_packing_location)
                or q != prepared.plan.q
                or bits != BITS_PER_CODE
                or batch_count != len(batch.characters)
                or frequency_start != prepared.sample_start
                or frequency_count != prepared.sample_count
                or first_t != prepared.pins.first_t_numerator
                or stop_t != prepared.pins.stop_t_numerator
                or payload_bytes != (frame_items + 3) // 4
                or butterflies != expected_butterflies
                or status_or != 0
                or reserved != 0
                or prefix != expected_prefix
                or binding != expected_binding
                or digests != expected_digests
            ):
                _fail(
                    "TGDBSPK1 frame identity, mode, span, work, status, "
                    "or digest binding differs"
                )
            frame_digest = hashlib.sha256(FRAME_DOMAIN)
            frame_digest.update(prefix)
            frame_digest.update(binding)
            frame_digest.update(digests)
            whole_digest.update(prefix)
            whole_digest.update(binding)
            whole_digest.update(digests)
            run.stream_bytes += len(prefix) + len(binding) + len(digests)
            payload_digest = hashlib.sha256()
            remaining_items = frame_items
            remaining_bytes = payload_bytes
            maximum_chunk_bytes = max(1, (chunk_items + 3) // 4)
            while remaining_bytes:
                count = min(remaining_bytes, maximum_chunk_bytes)
                raw = _read_exact(
                    packed_stream, count, label="TGDBSPK1 packed codes"
                )
                frame_digest.update(raw)
                whole_digest.update(raw)
                payload_digest.update(raw)
                run.stream_bytes += len(raw)
                remaining_bytes -= len(raw)
                codes = bytearray()
                for byte in raw:
                    for shift in (0, 2, 4, 6):
                        if remaining_items == 0:
                            if byte >> shift:
                                _fail(
                                    "TGDBSPK1 has nonzero unused padding bits"
                                )
                            break
                        code = (byte >> shift) & 3
                        if code == semantic.RESERVED_CODE:
                            _fail("TGDBSPK1 contains reserved sign code 3")
                        codes.append(code)
                        if code == semantic.AMBIGUOUS_CODE:
                            run.ambiguous += 1
                        elif code == semantic.NEGATIVE_CODE:
                            run.negative += 1
                        else:
                            run.positive += 1
                        remaining_items -= 1
                if codes:
                    yield bytes(codes)
            if remaining_items != 0:
                _fail("TGDBSPK1 payload does not cover its exact frame")
            trailer = _read_exact(
                packed_stream,
                FRAME_TRAILER.size,
                label="TGDBSPK1 frame trailer",
            )
            (
                trailer_magic,
                trailer_version,
                trailer_reserved,
                trailer_ordinal,
                trailer_payload_bytes,
                trailer_payload_sha256,
                trailer_frame_sha256,
            ) = FRAME_TRAILER.unpack(trailer)
            complete_frame = frame_digest.digest()
            if (
                trailer_magic != TRAILER_MAGIC
                or trailer_version != FORMAT_VERSION_V1
                or trailer_reserved != 0
                or trailer_ordinal != ordinal
                or trailer_payload_bytes != payload_bytes
                or trailer_payload_sha256 != payload_digest.digest()
                or trailer_frame_sha256 != complete_frame
            ):
                _fail("TGDBSPK1 frame trailer or payload digest differs")
            whole_digest.update(trailer)
            run.stream_bytes += len(trailer)
            previous_frame = complete_frame
            run.frame_count += 1
            run.item_count += frame_items
            run.finite_terms += terms
            run.butterflies += butterflies
            run.cuda_elapsed += elapsed

        end = _read_exact(
            packed_stream, STREAM_END.size, label="TGDBSPK1 terminal record"
        )
        (
            end_magic,
            end_version,
            end_reserved,
            end_frames,
            end_items,
            end_last_frame,
            end_body_sha256,
        ) = STREAM_END.unpack(end)
        if (
            end_magic != END_MAGIC
            or end_version != FORMAT_VERSION_V1
            or end_reserved != 0
            or end_frames != len(prepared.batches)
            or end_items
            != prepared.plan.campaign_character_count
            * prepared.sample_count
            or end_last_frame != previous_frame
            or end_body_sha256 != whole_digest.digest()
        ):
            _fail("TGDBSPK1 terminal coverage or body digest differs")
        run.stream_bytes += len(end)
        if packed_stream.read(1):
            _fail("TGDBSPK1 stream has trailing bytes after terminal record")
        expected_items = (
            prepared.plan.campaign_character_count * prepared.sample_count
        )
        if (
            run.frame_count != len(prepared.batches)
            or run.item_count != expected_items
            or run.ambiguous + run.negative + run.positive != expected_items
        ):
            _fail("TGDBSPK1 complete coverage totals differ")
        adapter._verify_snapshots(prepared.snapshots)
        complete_stream_digest = whole_digest.copy()
        complete_stream_digest.update(end)
        run.stream_sha256 = complete_stream_digest.hexdigest()
        run.completed = True

    started = time.perf_counter_ns()
    state_record = compact.write_flat_sign_codes_v3(
        Path(state_path),
        q=prepared.plan.q,
        frame_count=len(prepared.batches),
        first_t_numerator=prepared.pins.first_t_numerator,
        stop_t_numerator=prepared.pins.stop_t_numerator,
        code_chunks=code_chunks(),
        source_binding_sha256=prepared.source_binding,
        expected_roster_sha256=prepared.roster_sha256,
        maximum_bytes=maximum_state_bytes,
    )
    elapsed = time.perf_counter_ns() - started
    if not run.completed:
        _fail("compact v3 writer did not exhaust the packed stream")

    full_source_span = (
        prepared.pins.first_t_numerator == 0
        and prepared.pins.stop_t_numerator
        == prepared.parameters.sample_count * compact.SOURCE_SAMPLE_NUMERATOR
    )
    body: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "schema_version": 1,
        "algorithm_id": REDUCER_ALGORITHM_ID,
        "author": AUTHOR,
        "classification": (
            "typed_runner_packed_sign_to_compact_state_"
            "not_dft_replay_zero_completeness_or_atom_discharge"
        ),
        "expected_packing_location": expected_packing_location,
        "packing_mode": _mode(
            prepared.pins, expected_packing_location
        ),
        "q": prepared.plan.q,
        "pinset": prepared.pins.record(),
        "pinset_sha256": adapter.pinset_sha256(prepared.pins),
        "pinset_matches_exact_inputs": True,
        "pinset_authority_established_by_reducer": False,
        "compact_source_binding_sha256": prepared.source_binding,
        "packed_stream_sha256_receipt_only": run.stream_sha256,
        "packed_stream_bytes_consumed": run.stream_bytes,
        "packed_stream_materialized": False,
        "raw_disk_stream_materialized": False,
        "strict_sign_codes_fed_directly_to_TGDCSB03": True,
        "four_little_endian_two_bit_codes_per_byte": True,
        "reserved_code_and_padding_checked": True,
        "frame_hash_chain_checked": True,
        "terminal_coverage_and_eof_checked": True,
        "exact_plan_batch_control_roster_span_mode_bindings_checked": True,
        "full_character_partition_checked": True,
        "complete_primitive_roster_checked": True,
        "exact_span_checked": True,
        "full_source_span": full_source_span,
        "structural_bounded_span_kat": (
            prepared.pins.structural_bounded_span_kat
        ),
        "frame_count": run.frame_count,
        "sample_count_per_character": prepared.sample_count,
        "item_count": run.item_count,
        "ambiguous_sample_count": run.ambiguous,
        "negative_sample_count": run.negative,
        "positive_sample_count": run.positive,
        "finite_terms_reported_not_recomputed": run.finite_terms,
        "butterflies_reported_and_shape_checked": run.butterflies,
        "cuda_elapsed_nanoseconds_reported_not_trusted": run.cuda_elapsed,
        "elapsed_nanoseconds": elapsed,
        "compact_state_artifact": state_record,
        "runner_strict_sign_arithmetic_replayed_by_reducer": False,
        "dft_arithmetic_containment_replayed": False,
        "analytic_seed_values_replayed": False,
        "character_exponent_semantics_replayed": False,
        "pointwise_transition_lower_bounds_proved": False,
        "zero_multiplicity_realized": False,
        "physical_complete_roster_equivalence_realized": False,
        "turing_totals_realized": False,
        "turing_closure_realized": False,
        "ambiguity_refinement_complete": False,
        "source_scale_storage_admitted": False,
        "source_admission_enabled": False,
        "external_atom_discharged": False,
        "production_ready": False,
    }
    result = dict(body)
    result["receipt_sha256"] = hashlib.sha256(
        adapter._canonical_json_bytes(body)
    ).hexdigest()
    if receipt_path is not None:
        adapter._atomic_immutable_json(Path(receipt_path), result)
    return result


__all__ = [
    "BITS_PER_CODE",
    "DEFAULT_CHUNK_ITEMS",
    "DEVICE_PRODUCTION_MODE",
    "END_MAGIC",
    "FORMAT_VERSION_V1",
    "FRAME_BATCH_BINDING",
    "FRAME_DIGESTS",
    "FRAME_MAGIC",
    "FRAME_PREFIX",
    "FRAME_TRAILER",
    "HOST_PRODUCTION_MODE",
    "MAXIMUM_CHUNK_ITEMS",
    "PACKER_ALGORITHM_ID",
    "PRODUCTION_MODE",
    "REDUCER_ALGORITHM_ID",
    "STREAM_END",
    "STRUCTURAL_KAT_MODE",
    "SmallQPackedStreamV1Error",
    "pack_factored_service_stream_v1",
    "reduce_packed_stream_to_compact_v3",
]
