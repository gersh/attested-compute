# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded-memory postprocessing for compact small-q completed-value signs.

``TGDBSSG1`` stores one two-bit sign code for every canonical
character/source-sample coordinate.  This module turns one complete q-level
artifact into a deterministic, character-blocked ``TGDBSZR1`` artifact:

* every maximal ambiguous sample range is retained for refinement; and
* every pair of consecutive resolved samples with opposite signs is retained
  as an arithmetic sign-transition interval.

The latter is only a zero lower bound after a separate continuity theorem
identifies the sign codes with one continuous completed-L evaluator.  This
module applies no such theorem, infers no exact multiplicity, performs no
upsampling or Turing count, and does not discharge the external GRH atom.

Materialization and replay both stream the packed sign payload once in
bounded memory.  Replay regenerates every character header and event record
from the original signs and compares the retained artifact byte for byte.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import time
from typing import Any, BinaryIO, Callable, Mapping, NoReturn, Sequence

try:
    import numpy as _np
except ImportError:  # pragma: no cover - scalar fallback is covered
    _np = None

from tg_verifier import dirichlet_booker_smallq as base
from tg_verifier import dirichlet_booker_smallq_semantic_reducer as semantic


AUTHOR = "Gershon Bialer"
ALGORITHM_ID = "platt-booker-smallq-sign-transition-materializer-v1"
CHECKER_ID = "platt-booker-smallq-sign-transition-full-replay-v1"
ARTIFACT_SCHEMA = "sparkinterval.tg.dirichlet_booker_smallq.sign_scan.v1"
RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_booker_smallq.sign_scan_receipt.v1"
)
CHECKER_RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_booker_smallq.sign_scan_checker_receipt.v1"
)

ARTIFACT_MAGIC = b"TGDBSZR1"
ARTIFACT_FORMAT_VERSION = 1

# magic, version, q, then character/sample/event/range/transition and sign
# counts, followed by plan/control/roster/sign/reducer-receipt SHA-256.
ARTIFACT_HEADER = struct.Struct(
    "<8sIIQQQQQQQQ32s32s32s32s32s"
)

# ordinal, Conrey id, parity, padding, then ambiguous/negative/positive sample
# counts, ambiguity-range count, transition count, and total event count.
CHARACTER_HEADER = struct.Struct("<IIB7xQQQQQQ")

# kind, packed endpoint codes, padding, lower sample, upper sample.  Ambiguity
# ranges are inclusive.  Transition endpoints are resolved sample indices.
EVENT_RECORD = struct.Struct("<BB6xQQ")
AMBIGUITY_RANGE_EVENT = 1
OPPOSITE_SIGN_INTERVAL_EVENT = 2
if _np is not None:
    _NUMPY_EVENT_DTYPE: Any = _np.dtype(
        {
            "names": ("kind", "codes", "lower", "upper"),
            "formats": ("u1", "u1", "<u8", "<u8"),
            "offsets": (0, 1, 8, 16),
            "itemsize": EVENT_RECORD.size,
        }
    )
else:  # pragma: no cover - exercised by the scalar-only installation
    _NUMPY_EVENT_DTYPE = None

DEFAULT_CHUNK_CODES = 1 << 20
EVENT_BUFFER_BYTES = 8 * 1024 * 1024
MAX_RECEIPT_BYTES = 1024 * 1024


class SmallQSignScanError(RuntimeError):
    """A sign artifact, scan artifact, receipt, or replay failed closed."""


def _fail(message: str) -> NoReturn:
    raise SmallQSignScanError(message)


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def _atomic_bytes(path: Path, raw: bytes) -> None:
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


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while raw := source.read(8 * 1024 * 1024):
            digest.update(raw)
            size += len(raw)
    return digest.hexdigest(), size


def _read_exact(stream: BinaryIO, length: int, *, label: str) -> bytes:
    pieces: list[bytes] = []
    retained = 0
    while retained < length:
        raw = stream.read(length - retained)
        if not raw:
            _fail(f"truncated {label}")
        pieces.append(raw)
        retained += len(raw)
    return b"".join(pieces)


def _digest(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{name} must be a lowercase SHA-256 digest")
    return value


def _integer(name: str, value: object, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(f"{name} must be an integer at least {minimum}")
    return value


def _load_canonical_json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise SmallQSignScanError(f"cannot read {label}: {error}") from error
    if len(raw) > MAX_RECEIPT_BYTES:
        _fail(f"{label} exceeds one MiB")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SmallQSignScanError(f"invalid {label}: {error}") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail(f"{label} is not canonical JSON")
    return value


def _reject_output_alias(
    output: Path,
    protected: Sequence[Path],
    *,
    label: str,
) -> None:
    """Reject an output name that would atomically replace a required input."""

    try:
        output_key = output.resolve(strict=False)
        protected_keys = {path.resolve(strict=False) for path in protected}
    except OSError as error:
        raise SmallQSignScanError(f"cannot resolve {label} path: {error}") from error
    if output_key in protected_keys:
        _fail(f"{label} must not alias an input or another output")


_REDUCER_RECEIPT_KEYS = {
    "algorithm_id",
    "all_sample_codes_retained_in_exact_character_major_order",
    "all_samples_strictly_signed",
    "ambiguous_code",
    "ambiguous_samples_requiring_refinement",
    "arithmetic_containment_replayed",
    "atom_id",
    "author",
    "backend",
    "batch_count",
    "bits_per_sample",
    "character_count",
    "character_batch_partition_sha256",
    "character_parity_counts",
    "classification",
    "control_receipt_sha256",
    "control_sha256",
    "control_size_bytes",
    "control_unchanged_through_reduction",
    "downstream_zero_multiplicities_must_be_preserved",
    "external_atom_discharged",
    "full_character_partition_checked",
    "full_source_sample_grid_checked",
    "item_count",
    "kind",
    "multiplicity_bearing_zero_records_consumed_or_discarded",
    "multiplicity_inference_performed",
    "negative_code",
    "negative_samples",
    "plan_sha256",
    "positive_code",
    "positive_samples",
    "positive_scale_and_untilt_sign_invariance_used",
    "production_ready",
    "q",
    "raw_stream_bytes_consumed",
    "receipt_sha256",
    "reserved_code_rejected",
    "sample_count_per_character",
    "sign_artifact_bytes",
    "sign_artifact_sha256",
    "sign_change_or_zero_count_computed",
    "source_parameters_exact",
    "stream_elapsed_nanoseconds",
    "strict_sign_codes_are_not_zero_multiplicity_claims",
    "time_tail_over_positive_scale_controls_higher_precision_replayed",
    "transform_length",
    "trusted_execution_or_replayable_dft_evidence_required_after_raw_discard",
    "zero_completeness_claimed",
}


def _validate_reducer_receipt(
    path: Path,
    *,
    plan: Any,
    batches: Sequence[Any],
    parameters: base.TransformParameters,
    parity_counts: tuple[int, int],
    batch_partition_sha256: bytes,
    sign_metadata: Mapping[str, Any],
    sign_size_bytes: int,
) -> Mapping[str, Any]:
    receipt = _load_canonical_json(path, label="semantic reducer receipt")
    if set(receipt) != _REDUCER_RECEIPT_KEYS:
        _fail("semantic reducer receipt keys differ")
    body = dict(receipt)
    claimed = body.pop("receipt_sha256", None)
    if claimed != hashlib.sha256(canonical_json_bytes(body)).hexdigest():
        _fail("semantic reducer receipt self-hash differs")

    ambiguous = _integer(
        "ambiguous_samples_requiring_refinement",
        receipt.get("ambiguous_samples_requiring_refinement"),
    )
    negative = _integer("negative_samples", receipt.get("negative_samples"))
    positive = _integer("positive_samples", receipt.get("positive_samples"))
    item_count = plan.campaign_character_count * parameters.sample_count
    if ambiguous + negative + positive != item_count:
        _fail("semantic reducer receipt sign counts differ from source coverage")

    exact_classification = (
        "semantic_time_tail_sign_reduction_conditional_on_bound_dft_stream_"
        "not_zero_completeness_or_atom_discharge"
    )
    required_truths = (
        "all_sample_codes_retained_in_exact_character_major_order",
        "control_unchanged_through_reduction",
        "downstream_zero_multiplicities_must_be_preserved",
        "full_character_partition_checked",
        "full_source_sample_grid_checked",
        "positive_scale_and_untilt_sign_invariance_used",
        "reserved_code_rejected",
        "source_parameters_exact",
        "strict_sign_codes_are_not_zero_multiplicity_claims",
        "time_tail_over_positive_scale_controls_higher_precision_replayed",
        "trusted_execution_or_replayable_dft_evidence_required_after_raw_discard",
    )
    required_falsities = (
        "arithmetic_containment_replayed",
        "external_atom_discharged",
        "multiplicity_bearing_zero_records_consumed_or_discarded",
        "multiplicity_inference_performed",
        "production_ready",
        "sign_change_or_zero_count_computed",
        "zero_completeness_claimed",
    )
    if any(receipt.get(name) is not True for name in required_truths):
        _fail("semantic reducer receipt loses a required completeness guard")
    if any(receipt.get(name) is not False for name in required_falsities):
        _fail("semantic reducer receipt overstates an arithmetic or zero claim")

    if (
        receipt.get("kind") != semantic.REDUCER_RECEIPT_SCHEMA
        or receipt.get("algorithm_id") != semantic.ALGORITHM_ID
        or receipt.get("author") != AUTHOR
        or receipt.get("atom_id") != base.ATOM_ID
        or receipt.get("classification") != exact_classification
        or receipt.get("backend") not in {"numpy", "scalar"}
        or receipt.get("q") != plan.q
        or receipt.get("plan_sha256") != plan.sha256.hex()
        or receipt.get("control_sha256") != sign_metadata["control_sha256"]
        or receipt.get("character_count") != plan.campaign_character_count
        or receipt.get("sample_count_per_character") != parameters.sample_count
        or receipt.get("transform_length") != parameters.transform_length
        or receipt.get("item_count") != item_count
        or receipt.get("batch_count") != len(batches)
        or receipt.get("character_parity_counts") != list(parity_counts)
        or receipt.get("character_batch_partition_sha256")
        != batch_partition_sha256.hex()
        or receipt.get("bits_per_sample") != semantic.BITS_PER_CODE
        or receipt.get("ambiguous_code") != semantic.AMBIGUOUS_CODE
        or receipt.get("negative_code") != semantic.NEGATIVE_CODE
        or receipt.get("positive_code") != semantic.POSITIVE_CODE
        or receipt.get("all_samples_strictly_signed") != (ambiguous == 0)
        or receipt.get("sign_artifact_bytes") != sign_size_bytes
    ):
        _fail("semantic reducer receipt identity, source shape, or codes differ")
    for name in (
        "control_receipt_sha256",
        "control_sha256",
        "plan_sha256",
        "receipt_sha256",
        "sign_artifact_sha256",
    ):
        _digest(name, receipt.get(name))
    _integer("control_size_bytes", receipt.get("control_size_bytes"), minimum=1)
    _integer(
        "raw_stream_bytes_consumed",
        receipt.get("raw_stream_bytes_consumed"),
        minimum=1,
    )
    _integer(
        "stream_elapsed_nanoseconds",
        receipt.get("stream_elapsed_nanoseconds"),
    )
    return receipt


def _source_inputs(
    plan_path: Path,
    batch_paths: Sequence[Path],
    sign_path: Path,
    reducer_receipt_path: Path,
) -> tuple[
    Any,
    tuple[Any, ...],
    base.TransformParameters,
    tuple[int, int],
    bytes,
    tuple[Any, ...],
    Mapping[str, Any],
    Mapping[str, Any],
]:
    plan, batches, parameters, parity_counts = semantic._canonical_source_plan(
        plan_path, batch_paths
    )
    # This replay is intentionally repeated after semantic reduction.  A
    # self-hashed producer receipt cannot establish the source roster.
    semantic._replay_canonical_character_roster(plan, batches)
    partition = semantic._batch_partition_digest(batches)
    characters = tuple(
        character for batch in batches for character in batch.characters
    )
    if len(characters) != plan.campaign_character_count:
        _fail("flattened semantic character roster is incomplete")
    try:
        sign_size = sign_path.stat().st_size
        with sign_path.open("rb") as source:
            raw_header = _read_exact(
                source, semantic.SIGN_HEADER.size, label="TGDBSSG1 header"
            )
    except OSError as error:
        raise SmallQSignScanError(f"cannot inspect TGDBSSG1: {error}") from error
    sign_metadata = semantic._sign_metadata(raw_header, total_size=sign_size)
    if (
        sign_metadata["q"] != plan.q
        or sign_metadata["character_count"] != plan.campaign_character_count
        or sign_metadata["sample_count"] != parameters.sample_count
        or sign_metadata["plan_sha256"] != plan.sha256.hex()
        or sign_metadata["character_roster_sha256"]
        != plan.character_roster_sha256.hex()
    ):
        _fail("TGDBSSG1 plan, roster, or source-grid binding differs")
    reducer_receipt = _validate_reducer_receipt(
        reducer_receipt_path,
        plan=plan,
        batches=batches,
        parameters=parameters,
        parity_counts=parity_counts,
        batch_partition_sha256=partition,
        sign_metadata=sign_metadata,
        sign_size_bytes=sign_size,
    )
    return (
        plan,
        batches,
        parameters,
        parity_counts,
        partition,
        characters,
        sign_metadata,
        reducer_receipt,
    )


def _select_backend(backend: str) -> str:
    if backend not in {"auto", "numpy", "scalar"}:
        _fail("backend must be auto, numpy, or scalar")
    if backend == "numpy" and _np is None:
        _fail("NumPy backend requested but NumPy is unavailable")
    if backend == "auto":
        return "numpy" if _np is not None else "scalar"
    return backend


class _PackedCodeReader:
    """Read and hash a TGDBSSG1 payload exactly once."""

    def __init__(self, path: Path, *, backend: str) -> None:
        self.path = path
        self.backend = backend
        try:
            self.source = path.open("rb")
            self.initial_stat = os.fstat(self.source.fileno())
        except OSError as error:
            raise SmallQSignScanError(f"cannot open TGDBSSG1: {error}") from error
        self.digest = hashlib.sha256()
        self.header = _read_exact(
            self.source, semantic.SIGN_HEADER.size, label="TGDBSSG1 header"
        )
        self.digest.update(self.header)
        self.metadata = semantic._sign_metadata(
            self.header, total_size=self.initial_stat.st_size
        )
        self.total_codes = int(self.metadata["code_count"])
        self.payload_bytes = int(self.metadata["payload_bytes"])
        self.codes_delivered = 0
        self.payload_bytes_read = 0
        self.last_payload_byte: int | None = None
        if backend == "numpy":
            assert _np is not None
            self.pending: Any = _np.empty(0, dtype=_np.uint8)
        else:
            self.pending = []

    def _decode(self, raw: bytes) -> Any:
        if self.backend == "numpy":
            assert _np is not None
            packed = _np.frombuffer(raw, dtype=_np.uint8)
            decoded = _np.empty(4 * len(packed), dtype=_np.uint8)
            decoded[0::4] = packed & _np.uint8(3)
            decoded[1::4] = (packed >> _np.uint8(2)) & _np.uint8(3)
            decoded[2::4] = (packed >> _np.uint8(4)) & _np.uint8(3)
            decoded[3::4] = packed >> _np.uint8(6)
            return decoded
        decoded_list: list[int] = []
        for value in raw:
            decoded_list.extend(
                (
                    value & 3,
                    (value >> 2) & 3,
                    (value >> 4) & 3,
                    (value >> 6) & 3,
                )
            )
        return decoded_list

    def read_codes(self, count: int) -> Any:
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or count <= 0
            or self.codes_delivered + count > self.total_codes
        ):
            _fail("TGDBSSG1 code request is outside remaining coverage")
        pending_count = len(self.pending)
        need_raw_codes = max(0, count - pending_count)
        if need_raw_codes:
            raw_count = (need_raw_codes + 3) // 4
            if self.payload_bytes_read + raw_count > self.payload_bytes:
                _fail("TGDBSSG1 payload byte accounting underflows")
            raw = _read_exact(
                self.source, raw_count, label="TGDBSSG1 packed sign payload"
            )
            self.digest.update(raw)
            self.payload_bytes_read += len(raw)
            self.last_payload_byte = raw[-1]
            decoded = self._decode(raw)
            remaining_real = (
                self.total_codes - self.codes_delivered - pending_count
            )
            admitted = min(len(decoded), remaining_real)
            tail = decoded[admitted:]
            if any(int(code) != 0 for code in tail):
                _fail("TGDBSSG1 has nonzero unused padding bits")
            decoded = decoded[:admitted]
            if self.backend == "numpy":
                assert _np is not None
                self.pending = _np.concatenate((self.pending, decoded))
            else:
                self.pending.extend(decoded)
        if len(self.pending) < count:
            _fail("TGDBSSG1 decoded code accounting underflows")
        answer = self.pending[:count]
        self.pending = self.pending[count:]
        self.codes_delivered += count
        return answer

    def finish(self) -> str:
        if (
            self.codes_delivered != self.total_codes
            or len(self.pending) != 0
            or self.payload_bytes_read != self.payload_bytes
            or self.source.read(1)
        ):
            _fail("TGDBSSG1 code, payload, or EOF coverage differs")
        if self.total_codes % 4:
            if self.last_payload_byte is None:
                _fail("TGDBSSG1 final payload byte is absent")
            used_bits = 2 * (self.total_codes % 4)
            if self.last_payload_byte >> used_bits:
                _fail("TGDBSSG1 has nonzero unused padding bits")
        final_stat = os.fstat(self.source.fileno())
        if (
            final_stat.st_size != self.initial_stat.st_size
            or final_stat.st_ino != self.initial_stat.st_ino
            or final_stat.st_dev != self.initial_stat.st_dev
        ):
            _fail("TGDBSSG1 changed identity or size during the scan")
        self.source.close()
        return self.digest.hexdigest()

    def close(self) -> None:
        if not self.source.closed:
            self.source.close()


@dataclass
class _CharacterScan:
    ambiguous_samples: int = 0
    negative_samples: int = 0
    positive_samples: int = 0
    ambiguity_ranges: int = 0
    opposite_intervals: int = 0
    event_count: int = 0
    ambiguous_start: int | None = None
    previous_was_ambiguous: bool | None = None
    previous_resolved_sample: int | None = None
    previous_resolved_code: int | None = None


EventEmitter = Callable[[int, int, int, int], None]
PackedEventEmitter = Callable[[Any], None]


def _emit_ambiguity(
    state: _CharacterScan,
    emit: EventEmitter,
    lower: int,
    upper: int,
) -> None:
    if lower < 0 or upper < lower:
        _fail("internal ambiguity range is malformed")
    emit(AMBIGUITY_RANGE_EVENT, 0, lower, upper)
    state.ambiguity_ranges += 1
    state.event_count += 1


def _emit_opposite(
    state: _CharacterScan,
    emit: EventEmitter,
    lower: int,
    upper: int,
    lower_code: int,
    upper_code: int,
) -> None:
    if (
        lower < 0
        or upper <= lower
        or lower_code not in {semantic.NEGATIVE_CODE, semantic.POSITIVE_CODE}
        or upper_code not in {semantic.NEGATIVE_CODE, semantic.POSITIVE_CODE}
        or lower_code == upper_code
    ):
        _fail("internal opposite-sign interval is malformed")
    packed_codes = lower_code | (upper_code << 2)
    emit(OPPOSITE_SIGN_INTERVAL_EVENT, packed_codes, lower, upper)
    state.opposite_intervals += 1
    state.event_count += 1


def _scan_scalar_chunk(
    state: _CharacterScan,
    codes: Sequence[int],
    *,
    sample_start: int,
    emit: EventEmitter,
) -> None:
    for relative, raw_code in enumerate(codes):
        code = int(raw_code)
        sample = sample_start + relative
        if code == semantic.AMBIGUOUS_CODE:
            state.ambiguous_samples += 1
            if state.ambiguous_start is None:
                state.ambiguous_start = sample
            state.previous_was_ambiguous = True
            continue
        if code not in {semantic.NEGATIVE_CODE, semantic.POSITIVE_CODE}:
            _fail("TGDBSSG1 contains the reserved sign code")
        if state.ambiguous_start is not None:
            _emit_ambiguity(
                state, emit, state.ambiguous_start, sample - 1
            )
            state.ambiguous_start = None
        if (
            state.previous_resolved_code is not None
            and state.previous_resolved_code != code
        ):
            assert state.previous_resolved_sample is not None
            _emit_opposite(
                state,
                emit,
                state.previous_resolved_sample,
                sample,
                state.previous_resolved_code,
                code,
            )
        if code == semantic.NEGATIVE_CODE:
            state.negative_samples += 1
        else:
            state.positive_samples += 1
        state.previous_resolved_sample = sample
        state.previous_resolved_code = code
        state.previous_was_ambiguous = False


def _scan_numpy_chunk(
    state: _CharacterScan,
    codes: Any,
    *,
    sample_start: int,
    emit: EventEmitter,
    emit_packed: PackedEventEmitter | None = None,
) -> None:
    assert _np is not None
    assert _NUMPY_EVENT_DTYPE is not None
    if len(codes) == 0:
        return
    if bool(_np.any(codes > semantic.POSITIVE_CODE)):
        _fail("TGDBSSG1 contains the reserved sign code")
    ambiguous = codes == semantic.AMBIGUOUS_CODE
    negative = codes == semantic.NEGATIVE_CODE
    positive = codes == semantic.POSITIVE_CODE
    ambiguous_count = int(_np.count_nonzero(ambiguous))
    negative_count = int(_np.count_nonzero(negative))
    positive_count = int(_np.count_nonzero(positive))
    if ambiguous_count + negative_count + positive_count != len(codes):
        _fail("TGDBSSG1 contains an unknown sign code")
    state.ambiguous_samples += ambiguous_count
    state.negative_samples += negative_count
    state.positive_samples += positive_count

    first_ambiguous = bool(ambiguous[0])
    continuing_ambiguity = state.ambiguous_start is not None
    if continuing_ambiguity != (state.previous_was_ambiguous is True):
        _fail("internal ambiguity state is inconsistent at a chunk boundary")
    ambiguity_transitions = (
        _np.flatnonzero(ambiguous[1:] != ambiguous[:-1]) + 1
    )
    internal_starts = ambiguity_transitions[
        ambiguous[ambiguity_transitions]
    ]
    internal_ends = ambiguity_transitions[
        ~ambiguous[ambiguity_transitions]
    ]

    range_start_parts: list[Any] = []
    if continuing_ambiguity:
        range_start_parts.append(
            _np.asarray([state.ambiguous_start], dtype=_np.uint64)
        )
    elif first_ambiguous:
        range_start_parts.append(
            _np.asarray([sample_start], dtype=_np.uint64)
        )
    if len(internal_starts):
        range_start_parts.append(
            internal_starts.astype(_np.uint64, copy=False)
            + _np.uint64(sample_start)
        )
    range_starts = (
        _np.concatenate(range_start_parts)
        if range_start_parts
        else _np.empty(0, dtype=_np.uint64)
    )

    range_end_parts: list[Any] = []
    if continuing_ambiguity and not first_ambiguous:
        range_end_parts.append(
            _np.asarray([sample_start], dtype=_np.uint64)
        )
    if len(internal_ends):
        range_end_parts.append(
            internal_ends.astype(_np.uint64, copy=False)
            + _np.uint64(sample_start)
        )
    range_ends = (
        _np.concatenate(range_end_parts)
        if range_end_parts
        else _np.empty(0, dtype=_np.uint64)
    )
    expected_open_range = int(bool(ambiguous[-1]))
    if len(range_starts) != len(range_ends) + expected_open_range:
        _fail("internal vector ambiguity ranges do not pair")
    if expected_open_range:
        state.ambiguous_start = int(range_starts[-1])
    else:
        state.ambiguous_start = None
    state.previous_was_ambiguous = bool(ambiguous[-1])

    bracket_lower_parts: list[Any] = []
    bracket_upper_parts: list[Any] = []
    bracket_code_parts: list[Any] = []
    resolved_relative = _np.flatnonzero(~ambiguous)
    if len(resolved_relative):
        resolved_codes = codes[resolved_relative]
        first_sample = sample_start + int(resolved_relative[0])
        first_code = int(resolved_codes[0])
        if (
            state.previous_resolved_code is not None
            and state.previous_resolved_code != first_code
        ):
            assert state.previous_resolved_sample is not None
            bracket_lower_parts.append(
                _np.asarray(
                    [state.previous_resolved_sample], dtype=_np.uint64
                )
            )
            bracket_upper_parts.append(
                _np.asarray([first_sample], dtype=_np.uint64)
            )
            bracket_code_parts.append(
                _np.asarray(
                    [
                        state.previous_resolved_code
                        | (first_code << 2)
                    ],
                    dtype=_np.uint8,
                )
            )
        changes = _np.flatnonzero(
            resolved_codes[1:] != resolved_codes[:-1]
        ) + 1
        if len(changes):
            bracket_lower_parts.append(
                resolved_relative[changes - 1].astype(
                    _np.uint64, copy=False
                )
                + _np.uint64(sample_start)
            )
            bracket_upper_parts.append(
                resolved_relative[changes].astype(
                    _np.uint64, copy=False
                )
                + _np.uint64(sample_start)
            )
            bracket_code_parts.append(
                (
                    resolved_codes[changes - 1]
                    | (resolved_codes[changes] << _np.uint8(2))
                ).astype(_np.uint8, copy=False)
            )
        state.previous_resolved_sample = (
            sample_start + int(resolved_relative[-1])
        )
        state.previous_resolved_code = int(resolved_codes[-1])

    bracket_lowers = (
        _np.concatenate(bracket_lower_parts)
        if bracket_lower_parts
        else _np.empty(0, dtype=_np.uint64)
    )
    bracket_uppers = (
        _np.concatenate(bracket_upper_parts)
        if bracket_upper_parts
        else _np.empty(0, dtype=_np.uint64)
    )
    bracket_codes = (
        _np.concatenate(bracket_code_parts)
        if bracket_code_parts
        else _np.empty(0, dtype=_np.uint8)
    )
    range_count = len(range_ends)
    bracket_count = len(bracket_lowers)
    if (
        len(bracket_uppers) != bracket_count
        or len(bracket_codes) != bracket_count
        or (
            range_count
            and bool(_np.any(range_starts[:range_count] >= range_ends))
        )
        or (
            bracket_count
            and bool(_np.any(bracket_lowers >= bracket_uppers))
        )
    ):
        _fail("internal vector event endpoints are malformed")

    event_count = range_count + bracket_count
    if event_count:
        records = _np.zeros(event_count, dtype=_NUMPY_EVENT_DTYPE)
        if range_count == 0:
            records["kind"] = OPPOSITE_SIGN_INTERVAL_EVENT
            records["codes"] = bracket_codes
            records["lower"] = bracket_lowers
            records["upper"] = bracket_uppers
        elif bracket_count == 0:
            records["kind"] = AMBIGUITY_RANGE_EVENT
            records["lower"] = range_starts[:range_count]
            records["upper"] = range_ends - _np.uint64(1)
        else:
            # Both trigger streams are already increasing.  A range whose
            # exclusive end equals a bracket's upper endpoint precedes that
            # bracket, matching the scalar close-range-then-transition order.
            range_positions = (
                _np.arange(range_count, dtype=_np.intp)
                + _np.searchsorted(
                    bracket_uppers, range_ends, side="left"
                )
            )
            range_mask = _np.zeros(event_count, dtype=_np.bool_)
            range_mask[range_positions] = True
            records["kind"][range_mask] = AMBIGUITY_RANGE_EVENT
            records["lower"][range_mask] = range_starts[:range_count]
            records["upper"][range_mask] = (
                range_ends - _np.uint64(1)
            )
            records["kind"][~range_mask] = OPPOSITE_SIGN_INTERVAL_EVENT
            records["codes"][~range_mask] = bracket_codes
            records["lower"][~range_mask] = bracket_lowers
            records["upper"][~range_mask] = bracket_uppers
        packed = memoryview(records).cast("B")
        if emit_packed is not None:
            emit_packed(packed)
        else:
            for kind, packed_codes, lower, upper in EVENT_RECORD.iter_unpack(
                packed
            ):
                emit(kind, packed_codes, lower, upper)
    state.ambiguity_ranges += range_count
    state.opposite_intervals += bracket_count
    state.event_count += event_count


def _scan_character(
    reader: _PackedCodeReader,
    *,
    sample_count: int,
    chunk_codes: int,
    backend: str,
    emit: EventEmitter,
    emit_packed: PackedEventEmitter | None = None,
) -> _CharacterScan:
    state = _CharacterScan()
    sample_start = 0
    while sample_start < sample_count:
        count = min(chunk_codes, sample_count - sample_start)
        codes = reader.read_codes(count)
        if backend == "numpy":
            _scan_numpy_chunk(
                state,
                codes,
                sample_start=sample_start,
                emit=emit,
                emit_packed=emit_packed,
            )
        else:
            _scan_scalar_chunk(
                state, codes, sample_start=sample_start, emit=emit
            )
        sample_start += count
    if state.ambiguous_start is not None:
        _emit_ambiguity(
            state, emit, state.ambiguous_start, sample_count - 1
        )
        state.ambiguous_start = None
    if (
        state.ambiguous_samples
        + state.negative_samples
        + state.positive_samples
        != sample_count
        or state.event_count
        != state.ambiguity_ranges + state.opposite_intervals
    ):
        _fail("internal per-character sign coverage differs")
    return state


class _BufferedEventWriter:
    def __init__(self, output: BinaryIO) -> None:
        self.output = output
        self.buffer = bytearray()

    def emit(self, kind: int, codes: int, lower: int, upper: int) -> None:
        self.buffer.extend(EVENT_RECORD.pack(kind, codes, lower, upper))
        if len(self.buffer) >= EVENT_BUFFER_BYTES:
            self.flush()

    def emit_packed(self, raw: Any) -> None:
        self.flush()
        view = memoryview(raw).cast("B")
        for start in range(0, len(view), EVENT_BUFFER_BYTES):
            block = view[start : start + EVENT_BUFFER_BYTES]
            written = self.output.write(block)
            if written != len(block):
                _fail("short write while materializing TGDBSZR1 events")

    def flush(self) -> None:
        if self.buffer:
            written = self.output.write(self.buffer)
            if written != len(self.buffer):
                _fail("short write while materializing TGDBSZR1 events")
            self.buffer.clear()


class _BufferedEventComparator:
    def __init__(self, source: BinaryIO, digest: Any) -> None:
        self.source = source
        self.digest = digest
        self.expected = bytearray()

    def emit(self, kind: int, codes: int, lower: int, upper: int) -> None:
        self.expected.extend(EVENT_RECORD.pack(kind, codes, lower, upper))
        if len(self.expected) >= EVENT_BUFFER_BYTES:
            self.flush()

    def emit_packed(self, raw: Any) -> None:
        self.flush()
        view = memoryview(raw).cast("B")
        for start in range(0, len(view), EVENT_BUFFER_BYTES):
            expected = view[start : start + EVENT_BUFFER_BYTES]
            observed = _read_exact(
                self.source,
                len(expected),
                label="TGDBSZR1 event records",
            )
            self.digest.update(observed)
            if observed != expected:
                _fail("TGDBSZR1 event replay differs from the source signs")

    def flush(self) -> None:
        if not self.expected:
            return
        observed = _read_exact(
            self.source, len(self.expected), label="TGDBSZR1 event records"
        )
        self.digest.update(observed)
        if observed != self.expected:
            _fail("TGDBSZR1 event replay differs from the source signs")
        self.expected.clear()


def _character_header(
    ordinal: int, character: Any, state: _CharacterScan
) -> bytes:
    if ordinal > (1 << 32) - 1 or character.character_id > (1 << 32) - 1:
        _fail("character ordinal or id exceeds the TGDBSZR1 field width")
    return CHARACTER_HEADER.pack(
        ordinal,
        character.character_id,
        character.parity,
        state.ambiguous_samples,
        state.negative_samples,
        state.positive_samples,
        state.ambiguity_ranges,
        state.opposite_intervals,
        state.event_count,
    )


def _artifact_header(
    *,
    plan: Any,
    parameters: base.TransformParameters,
    totals: _CharacterScan,
    sign_metadata: Mapping[str, Any],
    sign_sha256: str,
    reducer_receipt_sha256: str,
) -> bytes:
    return ARTIFACT_HEADER.pack(
        ARTIFACT_MAGIC,
        ARTIFACT_FORMAT_VERSION,
        plan.q,
        plan.campaign_character_count,
        parameters.sample_count,
        totals.event_count,
        totals.ambiguity_ranges,
        totals.opposite_intervals,
        totals.ambiguous_samples,
        totals.negative_samples,
        totals.positive_samples,
        plan.sha256,
        bytes.fromhex(sign_metadata["control_sha256"]),
        plan.character_roster_sha256,
        bytes.fromhex(sign_sha256),
        bytes.fromhex(reducer_receipt_sha256),
    )


def _add_totals(total: _CharacterScan, local: _CharacterScan) -> None:
    total.ambiguous_samples += local.ambiguous_samples
    total.negative_samples += local.negative_samples
    total.positive_samples += local.positive_samples
    total.ambiguity_ranges += local.ambiguity_ranges
    total.opposite_intervals += local.opposite_intervals
    total.event_count += local.event_count


def materialize_sign_scan(
    plan_path: Path,
    batch_paths: Sequence[Path],
    sign_path: Path,
    reducer_receipt_path: Path,
    artifact_path: Path,
    *,
    receipt_path: Path | None = None,
    chunk_codes: int = DEFAULT_CHUNK_CODES,
    backend: str = "auto",
) -> dict[str, Any]:
    """Produce a deterministic q-level ambiguity/transition artifact."""

    if (
        isinstance(chunk_codes, bool)
        or not isinstance(chunk_codes, int)
        or chunk_codes <= 0
    ):
        _fail("chunk_codes must be a positive integer")
    protected_paths = [
        plan_path,
        *batch_paths,
        sign_path,
        reducer_receipt_path,
    ]
    _reject_output_alias(
        artifact_path, protected_paths, label="TGDBSZR1 artifact"
    )
    if receipt_path is not None:
        _reject_output_alias(
            receipt_path,
            [*protected_paths, artifact_path],
            label="TGDBSZR1 materializer receipt",
        )
    selected_backend = _select_backend(backend)
    (
        plan,
        batches,
        parameters,
        parity_counts,
        partition,
        characters,
        sign_metadata,
        reducer_receipt,
    ) = _source_inputs(
        plan_path, batch_paths, sign_path, reducer_receipt_path
    )
    reader = _PackedCodeReader(sign_path, backend=selected_backend)
    if dict(reader.metadata) != dict(sign_metadata):
        reader.close()
        _fail("TGDBSSG1 header changed before materialization")

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{artifact_path.name}.", dir=artifact_path.parent
    )
    totals = _CharacterScan()
    started = time.perf_counter_ns()
    try:
        with os.fdopen(descriptor, "w+b") as output:
            output.write(bytes(ARTIFACT_HEADER.size))
            for ordinal, character in enumerate(characters):
                character_header_offset = output.tell()
                output.write(bytes(CHARACTER_HEADER.size))
                event_writer = _BufferedEventWriter(output)
                state = _scan_character(
                    reader,
                    sample_count=parameters.sample_count,
                    chunk_codes=chunk_codes,
                    backend=selected_backend,
                    emit=event_writer.emit,
                    emit_packed=event_writer.emit_packed,
                )
                event_writer.flush()
                block_end = output.tell()
                output.seek(character_header_offset)
                output.write(_character_header(ordinal, character, state))
                output.seek(block_end)
                _add_totals(totals, state)

            sign_sha256 = reader.finish()
            if sign_sha256 != reducer_receipt["sign_artifact_sha256"]:
                _fail("TGDBSSG1 digest differs from the semantic reducer receipt")
            if (
                totals.ambiguous_samples
                != reducer_receipt["ambiguous_samples_requiring_refinement"]
                or totals.negative_samples != reducer_receipt["negative_samples"]
                or totals.positive_samples != reducer_receipt["positive_samples"]
            ):
                _fail("TGDBSZR1 scan counts differ from the reducer receipt")
            output.seek(0)
            output.write(
                _artifact_header(
                    plan=plan,
                    parameters=parameters,
                    totals=totals,
                    sign_metadata=sign_metadata,
                    sign_sha256=sign_sha256,
                    reducer_receipt_sha256=reducer_receipt["receipt_sha256"],
                )
            )
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, artifact_path)
    except BaseException:
        reader.close()
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise

    elapsed = time.perf_counter_ns() - started
    artifact_sha256, artifact_size = _sha256_file(artifact_path)
    expected_size = (
        ARTIFACT_HEADER.size
        + len(characters) * CHARACTER_HEADER.size
        + totals.event_count * EVENT_RECORD.size
    )
    if artifact_size != expected_size:
        _fail("TGDBSZR1 size differs from its complete event counts")
    receipt: dict[str, Any] = {
        "algorithm_id": ALGORITHM_ID,
        "all_character_blocks_materialized": True,
        "all_sign_codes_consumed_once_in_exact_source_order": True,
        "ambiguous_sample_count": totals.ambiguous_samples,
        "ambiguity_range_count": totals.ambiguity_ranges,
        "arithmetic_sign_transition_intervals_only": True,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_sha256": artifact_sha256,
        "artifact_size_bytes": artifact_size,
        "atom_id": base.ATOM_ID,
        "author": AUTHOR,
        "backend": selected_backend,
        "character_batch_partition_sha256": partition.hex(),
        "character_count": len(characters),
        "character_parity_counts": list(parity_counts),
        "classification": (
            "complete_small_q_sign_scan_not_continuity_zero_multiplicity_"
            "turing_or_grh"
        ),
        "continuity_theorem_applied": False,
        "event_count": totals.event_count,
        "event_record_bytes": EVENT_RECORD.size,
        "event_storage_can_exceed_packed_sign_input": True,
        "exact_zero_multiplicity_inferred": False,
        "external_atom_discharged": False,
        "kind": RECEIPT_SCHEMA,
        "negative_sample_count": totals.negative_samples,
        "opposite_sign_interval_count": totals.opposite_intervals,
        "plan_sha256": plan.sha256.hex(),
        "positive_sample_count": totals.positive_samples,
        "production_ready": False,
        "q": plan.q,
        "reducer_receipt_sha256": reducer_receipt["receipt_sha256"],
        "sample_count_per_character": parameters.sample_count,
        "sign_artifact_sha256": sign_sha256,
        "source_roster_replayed": True,
        "source_scale_measured": False,
        "stream_elapsed_nanoseconds": elapsed,
        "turing_or_zero_completeness_performed": False,
        "upsampling_or_exception_refinement_performed": False,
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(receipt)
    ).hexdigest()
    encoded = canonical_json_bytes(receipt)
    if len(encoded) > MAX_RECEIPT_BYTES:
        _fail("TGDBSZR1 materializer receipt exceeds one MiB")
    if receipt_path is not None:
        _atomic_bytes(receipt_path, encoded)
    return receipt


_PRODUCER_RECEIPT_KEYS = {
    "algorithm_id",
    "all_character_blocks_materialized",
    "all_sign_codes_consumed_once_in_exact_source_order",
    "ambiguous_sample_count",
    "ambiguity_range_count",
    "arithmetic_sign_transition_intervals_only",
    "artifact_schema",
    "artifact_sha256",
    "artifact_size_bytes",
    "atom_id",
    "author",
    "backend",
    "character_batch_partition_sha256",
    "character_count",
    "character_parity_counts",
    "classification",
    "continuity_theorem_applied",
    "event_count",
    "event_record_bytes",
    "event_storage_can_exceed_packed_sign_input",
    "exact_zero_multiplicity_inferred",
    "external_atom_discharged",
    "kind",
    "negative_sample_count",
    "opposite_sign_interval_count",
    "plan_sha256",
    "positive_sample_count",
    "production_ready",
    "q",
    "receipt_sha256",
    "reducer_receipt_sha256",
    "sample_count_per_character",
    "sign_artifact_sha256",
    "source_roster_replayed",
    "source_scale_measured",
    "stream_elapsed_nanoseconds",
    "turing_or_zero_completeness_performed",
    "upsampling_or_exception_refinement_performed",
}


def _validate_producer_receipt(
    path: Path,
    *,
    plan: Any,
    parameters: base.TransformParameters,
    parity_counts: tuple[int, int],
    partition: bytes,
    sign_sha256: str,
    reducer_receipt_sha256: str,
    artifact_sha256: str,
    artifact_size: int,
    totals: _CharacterScan,
) -> Mapping[str, Any]:
    receipt = _load_canonical_json(path, label="TGDBSZR1 materializer receipt")
    if set(receipt) != _PRODUCER_RECEIPT_KEYS:
        _fail("TGDBSZR1 materializer receipt keys differ")
    body = dict(receipt)
    claimed = body.pop("receipt_sha256", None)
    if claimed != hashlib.sha256(canonical_json_bytes(body)).hexdigest():
        _fail("TGDBSZR1 materializer receipt self-hash differs")
    required_truths = (
        "all_character_blocks_materialized",
        "all_sign_codes_consumed_once_in_exact_source_order",
        "arithmetic_sign_transition_intervals_only",
        "source_roster_replayed",
    )
    required_falsities = (
        "continuity_theorem_applied",
        "exact_zero_multiplicity_inferred",
        "external_atom_discharged",
        "production_ready",
        "source_scale_measured",
        "turing_or_zero_completeness_performed",
        "upsampling_or_exception_refinement_performed",
    )
    if any(receipt.get(name) is not True for name in required_truths):
        _fail("TGDBSZR1 materializer receipt loses a completeness guard")
    if any(receipt.get(name) is not False for name in required_falsities):
        _fail("TGDBSZR1 materializer receipt overstates a zero claim")
    if (
        receipt.get("kind") != RECEIPT_SCHEMA
        or receipt.get("artifact_schema") != ARTIFACT_SCHEMA
        or receipt.get("algorithm_id") != ALGORITHM_ID
        or receipt.get("author") != AUTHOR
        or receipt.get("atom_id") != base.ATOM_ID
        or receipt.get("classification")
        != (
            "complete_small_q_sign_scan_not_continuity_zero_multiplicity_"
            "turing_or_grh"
        )
        or receipt.get("backend") not in {"numpy", "scalar"}
        or receipt.get("q") != plan.q
        or receipt.get("plan_sha256") != plan.sha256.hex()
        or receipt.get("character_count") != plan.campaign_character_count
        or receipt.get("sample_count_per_character") != parameters.sample_count
        or receipt.get("character_parity_counts") != list(parity_counts)
        or receipt.get("character_batch_partition_sha256") != partition.hex()
        or receipt.get("sign_artifact_sha256") != sign_sha256
        or receipt.get("reducer_receipt_sha256")
        != reducer_receipt_sha256
        or receipt.get("artifact_sha256") != artifact_sha256
        or receipt.get("artifact_size_bytes") != artifact_size
        or receipt.get("event_count") != totals.event_count
        or receipt.get("event_record_bytes") != EVENT_RECORD.size
        or receipt.get("event_storage_can_exceed_packed_sign_input") is not True
        or receipt.get("ambiguity_range_count") != totals.ambiguity_ranges
        or receipt.get("opposite_sign_interval_count")
        != totals.opposite_intervals
        or receipt.get("ambiguous_sample_count") != totals.ambiguous_samples
        or receipt.get("negative_sample_count") != totals.negative_samples
        or receipt.get("positive_sample_count") != totals.positive_samples
    ):
        _fail("TGDBSZR1 materializer receipt identity or totals differ")
    _integer(
        "stream_elapsed_nanoseconds",
        receipt.get("stream_elapsed_nanoseconds"),
    )
    return receipt


def _parse_artifact_header(raw: bytes) -> dict[str, Any]:
    if len(raw) != ARTIFACT_HEADER.size:
        _fail("truncated TGDBSZR1 header")
    (
        magic,
        version,
        q,
        character_count,
        sample_count,
        event_count,
        ambiguity_ranges,
        opposite_intervals,
        ambiguous_samples,
        negative_samples,
        positive_samples,
        plan_sha256,
        control_sha256,
        roster_sha256,
        sign_sha256,
        reducer_receipt_sha256,
    ) = ARTIFACT_HEADER.unpack(raw)
    if (
        magic != ARTIFACT_MAGIC
        or version != ARTIFACT_FORMAT_VERSION
        or not base.SOURCE_Q_START <= q <= base.SOURCE_Q_STOP
        or character_count <= 0
        or sample_count <= 0
        or event_count != ambiguity_ranges + opposite_intervals
        or ambiguous_samples + negative_samples + positive_samples
        != character_count * sample_count
    ):
        _fail("invalid TGDBSZR1 header counts or source shape")
    return {
        "q": q,
        "character_count": character_count,
        "sample_count": sample_count,
        "event_count": event_count,
        "ambiguity_range_count": ambiguity_ranges,
        "opposite_sign_interval_count": opposite_intervals,
        "ambiguous_sample_count": ambiguous_samples,
        "negative_sample_count": negative_samples,
        "positive_sample_count": positive_samples,
        "plan_sha256": plan_sha256.hex(),
        "control_sha256": control_sha256.hex(),
        "character_roster_sha256": roster_sha256.hex(),
        "sign_artifact_sha256": sign_sha256.hex(),
        "reducer_receipt_sha256": reducer_receipt_sha256.hex(),
    }


def _parse_character_header(raw: bytes) -> dict[str, int]:
    if len(raw) != CHARACTER_HEADER.size:
        _fail("truncated TGDBSZR1 character header")
    if any(raw[9:16]):
        _fail("TGDBSZR1 character header has nonzero padding")
    (
        ordinal,
        character_id,
        parity,
        ambiguous,
        negative,
        positive,
        ranges,
        intervals,
        events,
    ) = CHARACTER_HEADER.unpack(raw)
    if (
        parity not in (0, 1)
        or events != ranges + intervals
    ):
        _fail("invalid TGDBSZR1 character header")
    return {
        "ordinal": ordinal,
        "character_id": character_id,
        "parity": parity,
        "ambiguous_samples": ambiguous,
        "negative_samples": negative,
        "positive_samples": positive,
        "ambiguity_ranges": ranges,
        "opposite_intervals": intervals,
        "event_count": events,
    }


def verify_sign_scan(
    plan_path: Path,
    batch_paths: Sequence[Path],
    sign_path: Path,
    reducer_receipt_path: Path,
    artifact_path: Path,
    producer_receipt_path: Path,
    *,
    receipt_path: Path | None = None,
    chunk_codes: int = DEFAULT_CHUNK_CODES,
    backend: str = "auto",
) -> dict[str, Any]:
    """Replay every TGDBSZR1 block and event from the packed source signs."""

    if (
        isinstance(chunk_codes, bool)
        or not isinstance(chunk_codes, int)
        or chunk_codes <= 0
    ):
        _fail("chunk_codes must be a positive integer")
    if receipt_path is not None:
        _reject_output_alias(
            receipt_path,
            [
                plan_path,
                *batch_paths,
                sign_path,
                reducer_receipt_path,
                artifact_path,
                producer_receipt_path,
            ],
            label="TGDBSZR1 checker receipt",
        )
    selected_backend = _select_backend(backend)
    (
        plan,
        batches,
        parameters,
        parity_counts,
        partition,
        characters,
        sign_metadata,
        reducer_receipt,
    ) = _source_inputs(
        plan_path, batch_paths, sign_path, reducer_receipt_path
    )
    reader = _PackedCodeReader(sign_path, backend=selected_backend)
    if dict(reader.metadata) != dict(sign_metadata):
        reader.close()
        _fail("TGDBSSG1 header changed before replay")

    try:
        artifact_source = artifact_path.open("rb")
        artifact_initial_stat = os.fstat(artifact_source.fileno())
        artifact_size = artifact_initial_stat.st_size
    except OSError as error:
        reader.close()
        raise SmallQSignScanError(f"cannot open TGDBSZR1: {error}") from error
    artifact_digest = hashlib.sha256()
    totals = _CharacterScan()
    started = time.perf_counter_ns()
    try:
        raw_header = _read_exact(
            artifact_source, ARTIFACT_HEADER.size, label="TGDBSZR1 header"
        )
        artifact_digest.update(raw_header)
        header = _parse_artifact_header(raw_header)
        if (
            header["q"] != plan.q
            or header["character_count"] != plan.campaign_character_count
            or header["sample_count"] != parameters.sample_count
            or header["plan_sha256"] != plan.sha256.hex()
            or header["control_sha256"] != sign_metadata["control_sha256"]
            or header["character_roster_sha256"]
            != plan.character_roster_sha256.hex()
            or header["sign_artifact_sha256"]
            != reducer_receipt["sign_artifact_sha256"]
            or header["reducer_receipt_sha256"]
            != reducer_receipt["receipt_sha256"]
        ):
            _fail("TGDBSZR1 source identity or hash binding differs")

        for ordinal, character in enumerate(characters):
            raw_character = _read_exact(
                artifact_source,
                CHARACTER_HEADER.size,
                label="TGDBSZR1 character header",
            )
            artifact_digest.update(raw_character)
            retained = _parse_character_header(raw_character)
            if (
                retained["ordinal"] != ordinal
                or retained["character_id"] != character.character_id
                or retained["parity"] != character.parity
            ):
                _fail("TGDBSZR1 character roster order differs")
            comparator = _BufferedEventComparator(
                artifact_source, artifact_digest
            )
            state = _scan_character(
                reader,
                sample_count=parameters.sample_count,
                chunk_codes=chunk_codes,
                backend=selected_backend,
                emit=comparator.emit,
                emit_packed=comparator.emit_packed,
            )
            comparator.flush()
            expected_header = _parse_character_header(
                _character_header(ordinal, character, state)
            )
            if retained != expected_header:
                _fail("TGDBSZR1 character summary replay differs")
            _add_totals(totals, state)

        if artifact_source.read(1):
            _fail("TGDBSZR1 has trailing bytes after all character blocks")
        artifact_final_stat = os.fstat(artifact_source.fileno())
        if (
            artifact_final_stat.st_size != artifact_initial_stat.st_size
            or artifact_final_stat.st_ino != artifact_initial_stat.st_ino
            or artifact_final_stat.st_dev != artifact_initial_stat.st_dev
        ):
            _fail("TGDBSZR1 changed identity or size during replay")
        sign_sha256 = reader.finish()
    except BaseException:
        reader.close()
        artifact_source.close()
        raise
    artifact_source.close()
    elapsed = time.perf_counter_ns() - started
    artifact_sha256 = artifact_digest.hexdigest()
    expected_artifact_size = (
        ARTIFACT_HEADER.size
        + len(characters) * CHARACTER_HEADER.size
        + totals.event_count * EVENT_RECORD.size
    )
    if artifact_size != expected_artifact_size:
        _fail("TGDBSZR1 size differs from replayed event coverage")
    if (
        sign_sha256 != reducer_receipt["sign_artifact_sha256"]
        or header["event_count"] != totals.event_count
        or header["ambiguity_range_count"] != totals.ambiguity_ranges
        or header["opposite_sign_interval_count"] != totals.opposite_intervals
        or header["ambiguous_sample_count"] != totals.ambiguous_samples
        or header["negative_sample_count"] != totals.negative_samples
        or header["positive_sample_count"] != totals.positive_samples
    ):
        _fail("TGDBSZR1 global replay totals or source digest differ")
    producer_receipt = _validate_producer_receipt(
        producer_receipt_path,
        plan=plan,
        parameters=parameters,
        parity_counts=parity_counts,
        partition=partition,
        sign_sha256=sign_sha256,
        reducer_receipt_sha256=reducer_receipt["receipt_sha256"],
        artifact_sha256=artifact_sha256,
        artifact_size=artifact_size,
        totals=totals,
    )
    receipt: dict[str, Any] = {
        "all_character_headers_replayed": True,
        "all_event_records_replayed": True,
        "all_sign_codes_replayed_in_exact_source_order": True,
        "ambiguity_range_count": totals.ambiguity_ranges,
        "artifact_sha256": artifact_sha256,
        "artifact_size_bytes": artifact_size,
        "atom_id": base.ATOM_ID,
        "author": AUTHOR,
        "checker_backend": selected_backend,
        "checker_id": CHECKER_ID,
        "classification": (
            "full_small_q_sign_scan_replay_not_continuity_zero_multiplicity_"
            "turing_or_grh"
        ),
        "continuity_theorem_applied": False,
        "event_count": totals.event_count,
        "event_record_bytes": EVENT_RECORD.size,
        "event_storage_can_exceed_packed_sign_input": True,
        "exact_zero_multiplicity_inferred": False,
        "external_atom_discharged": False,
        "kind": CHECKER_RECEIPT_SCHEMA,
        "opposite_sign_interval_count": totals.opposite_intervals,
        "passed": True,
        "plan_sha256": plan.sha256.hex(),
        "producer_receipt_sha256": producer_receipt["receipt_sha256"],
        "q": plan.q,
        "reducer_receipt_sha256": reducer_receipt["receipt_sha256"],
        "replay_elapsed_nanoseconds": elapsed,
        "sign_artifact_sha256": sign_sha256,
        "source_roster_replayed": True,
        "source_scale_measured": False,
        "turing_or_zero_completeness_performed": False,
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(receipt)
    ).hexdigest()
    encoded = canonical_json_bytes(receipt)
    if len(encoded) > MAX_RECEIPT_BYTES:
        _fail("TGDBSZR1 checker receipt exceeds one MiB")
    if receipt_path is not None:
        _atomic_bytes(receipt_path, encoded)
    return receipt


def inspect_sign_scan(path: Path) -> dict[str, Any]:
    """Structurally inspect one bounded q-level TGDBSZR1 artifact."""

    try:
        source = path.open("rb")
        initial_stat = os.fstat(source.fileno())
        size = initial_stat.st_size
    except OSError as error:
        raise SmallQSignScanError(f"cannot inspect TGDBSZR1: {error}") from error
    digest = hashlib.sha256()
    try:
        raw_header = _read_exact(
            source, ARTIFACT_HEADER.size, label="TGDBSZR1 header"
        )
        digest.update(raw_header)
        header = _parse_artifact_header(raw_header)
        totals = _CharacterScan()
        previous_character_id: int | None = None
        for ordinal in range(header["character_count"]):
            raw_character = _read_exact(
                source,
                CHARACTER_HEADER.size,
                label="TGDBSZR1 character header",
            )
            digest.update(raw_character)
            character = _parse_character_header(raw_character)
            if (
                character["ordinal"] != ordinal
                or character["ambiguous_samples"]
                + character["negative_samples"]
                + character["positive_samples"]
                != header["sample_count"]
            ):
                _fail("TGDBSZR1 character ordinal or sample coverage differs")
            if (
                previous_character_id is not None
                and character["character_id"] == previous_character_id
            ):
                _fail("TGDBSZR1 repeats an adjacent character id")
            previous_character_id = character["character_id"]
            previous_trigger = -1
            observed_ranges = 0
            observed_intervals = 0
            for _ in range(character["event_count"]):
                raw_event = _read_exact(
                    source, EVENT_RECORD.size, label="TGDBSZR1 event record"
                )
                digest.update(raw_event)
                if any(raw_event[2:8]):
                    _fail("TGDBSZR1 event record has nonzero padding")
                kind, codes, lower, upper = EVENT_RECORD.unpack(raw_event)
                if kind == AMBIGUITY_RANGE_EVENT:
                    if (
                        codes != 0
                        or lower > upper
                        or upper >= header["sample_count"]
                    ):
                        _fail("malformed TGDBSZR1 ambiguity range")
                    trigger = upper + 1
                    observed_ranges += 1
                elif kind == OPPOSITE_SIGN_INTERVAL_EVENT:
                    lower_code = codes & 3
                    upper_code = (codes >> 2) & 3
                    if (
                        codes >> 4
                        or lower >= upper
                        or upper >= header["sample_count"]
                        or lower_code
                        not in {semantic.NEGATIVE_CODE, semantic.POSITIVE_CODE}
                        or upper_code
                        not in {semantic.NEGATIVE_CODE, semantic.POSITIVE_CODE}
                        or lower_code == upper_code
                    ):
                        _fail("malformed TGDBSZR1 opposite-sign interval")
                    trigger = upper
                    observed_intervals += 1
                else:
                    _fail("unknown TGDBSZR1 event kind")
                if trigger < previous_trigger:
                    _fail("TGDBSZR1 event trigger order decreases")
                previous_trigger = trigger
            if (
                observed_ranges != character["ambiguity_ranges"]
                or observed_intervals != character["opposite_intervals"]
            ):
                _fail("TGDBSZR1 character event-kind counts differ")
            local = _CharacterScan(
                ambiguous_samples=character["ambiguous_samples"],
                negative_samples=character["negative_samples"],
                positive_samples=character["positive_samples"],
                ambiguity_ranges=character["ambiguity_ranges"],
                opposite_intervals=character["opposite_intervals"],
                event_count=character["event_count"],
            )
            _add_totals(totals, local)
        if source.read(1):
            _fail("TGDBSZR1 has trailing bytes")
        final_stat = os.fstat(source.fileno())
        if (
            final_stat.st_size != initial_stat.st_size
            or final_stat.st_ino != initial_stat.st_ino
            or final_stat.st_dev != initial_stat.st_dev
        ):
            _fail("TGDBSZR1 changed identity or size during inspection")
    finally:
        source.close()
    if (
        size
        != ARTIFACT_HEADER.size
        + header["character_count"] * CHARACTER_HEADER.size
        + totals.event_count * EVENT_RECORD.size
        or header["event_count"] != totals.event_count
        or header["ambiguity_range_count"] != totals.ambiguity_ranges
        or header["opposite_sign_interval_count"] != totals.opposite_intervals
        or header["ambiguous_sample_count"] != totals.ambiguous_samples
        or header["negative_sample_count"] != totals.negative_samples
        or header["positive_sample_count"] != totals.positive_samples
    ):
        _fail("TGDBSZR1 structural totals or size differ")
    return {
        **header,
        "artifact_sha256": digest.hexdigest(),
        "artifact_size_bytes": size,
        "structural_only_not_source_sign_replay": True,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "AMBIGUITY_RANGE_EVENT",
    "ARTIFACT_FORMAT_VERSION",
    "ARTIFACT_HEADER",
    "ARTIFACT_MAGIC",
    "ARTIFACT_SCHEMA",
    "CHARACTER_HEADER",
    "CHECKER_ID",
    "CHECKER_RECEIPT_SCHEMA",
    "DEFAULT_CHUNK_CODES",
    "EVENT_RECORD",
    "OPPOSITE_SIGN_INTERVAL_EVENT",
    "RECEIPT_SCHEMA",
    "SmallQSignScanError",
    "canonical_json_bytes",
    "inspect_sign_scan",
    "materialize_sign_scan",
    "verify_sign_scan",
]
