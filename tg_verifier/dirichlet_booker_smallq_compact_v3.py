# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Typed factored-small-q producer boundary for ``TGDCSB03``.

This module consumes the existing character-major ``TGDBSQR3`` service
stream, validates its plan/batch/control identities, performs the strict
completed-real sign test, and feeds the resulting code chunks directly to
the compact v3 writer.  Neither the raw disk stream nor a ``TGDBSSG1`` sign
artifact is materialized.

The resulting state is still conditional on the producer's DFT containment.
The exact input-stream SHA-256 is retained by the receipt, not by the compact
artifact header.  Source admission, execution attestation, zero
completeness, multiplicity, refinement, and Turing realization remain false.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import mmap
import os
from pathlib import Path
import stat
import struct
import tempfile
import time
from typing import Any, BinaryIO, Iterator, Mapping, NoReturn, Sequence

from tg_verifier import dirichlet_booker_smallq as base
from tg_verifier import dirichlet_booker_smallq_certified as v2
from tg_verifier import dirichlet_booker_smallq_factored as factored
from tg_verifier import dirichlet_booker_smallq_semantic_reducer as semantic
from tg_verifier import dirichlet_compact_state_streaming_v3 as compact
from tg_verifier.dirichlet_booker_smallq_factored import (
    BATCH_BINDING,
    BATCH_MAGIC,
    CHARACTER_HEADER,
    FORMAT_VERSION,
    INPUT_HEADER,
    NONUNIT_EXPONENT,
    REDUCED_SERVICE_OUTPUT_MAGIC,
    SERVICE_OUTPUT_BINDING,
    _character_roster_digest,
)
from tg_verifier.dirichlet_root_number_stage import (
    primitive_frequency_records_bulk,
)


AUTHOR = "Gershon Bialer"
ALGORITHM_ID = "platt-booker-smallq-factored-to-compact-v3-v1"
RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_booker_smallq.compact_v3_receipt.v1"
)
PINSET_SCHEMA = (
    "sparkinterval.tg.dirichlet_booker_smallq.compact_v3_pinset.v1"
)
SOURCE_BINDING_DOMAIN = (
    b"SparkInterval/DirichletBookerSmallQ/compact-v3-source-binding/v1\x00"
)
PINSET_DOMAIN = (
    b"SparkInterval/DirichletBookerSmallQ/compact-v3-pinset/v1\x00"
)
MAXIMUM_RECEIPT_BYTES = 1024 * 1024
DEFAULT_CHUNK_ITEMS = 1 << 16
MAXIMUM_CHUNK_ITEMS = 1 << 20
SHARED_SEED_VALIDATION_CHUNK_RECORDS = 1 << 10


class SmallQCompactV3Error(RuntimeError):
    """A typed source input, external pin, or stream failed closed."""


def _fail(message: str) -> NoReturn:
    raise SmallQCompactV3Error(message)


def _digest(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{name} must be a lowercase SHA-256 digest")
    return value


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("ascii")


@dataclass(frozen=True)
class SmallQCompactV3Pins:
    """Externally retained identities required by the fused producer."""

    q: int
    shared_plan_cache_sha256: str
    time_tail_control_sha256: str
    time_tail_control_receipt_sha256: str
    character_batch_partition_sha256: str
    plan_character_roster_sha256: str
    compact_complete_roster_sha256: str
    first_t_numerator: int
    stop_t_numerator: int
    structural_bounded_span_kat: bool

    def record(self) -> dict[str, Any]:
        return asdict(self)


def _validate_pins(pins: SmallQCompactV3Pins) -> None:
    if not isinstance(pins, SmallQCompactV3Pins):
        _fail("compact v3 pins must use the typed pin record")
    if (
        isinstance(pins.q, bool)
        or not isinstance(pins.q, int)
        or not base.SOURCE_Q_START <= pins.q <= base.SOURCE_Q_STOP
        or isinstance(pins.first_t_numerator, bool)
        or not isinstance(pins.first_t_numerator, int)
        or pins.first_t_numerator < 0
        or isinstance(pins.stop_t_numerator, bool)
        or not isinstance(pins.stop_t_numerator, int)
        or pins.stop_t_numerator <= pins.first_t_numerator
        or type(pins.structural_bounded_span_kat) is not bool
    ):
        _fail("compact v3 q, span, or mode pin is malformed")
    for name in (
        "shared_plan_cache_sha256",
        "time_tail_control_sha256",
        "time_tail_control_receipt_sha256",
        "character_batch_partition_sha256",
        "plan_character_roster_sha256",
        "compact_complete_roster_sha256",
    ):
        _digest(name, getattr(pins, name))


def pinset_sha256(pins: SmallQCompactV3Pins) -> str:
    """Domain-separated digest for an externally reviewed typed pinset."""

    _validate_pins(pins)
    return hashlib.sha256(
        PINSET_DOMAIN + _canonical_json_bytes(pins.record())
    ).hexdigest()


def load_pinset(
    path: Path,
    *,
    expected_pinset_sha256: str,
) -> SmallQCompactV3Pins:
    """Load one canonical pin file under an out-of-band expected digest."""

    expected = _digest("expected compact v3 pinset", expected_pinset_sha256)
    status = _require_regular(path, label="compact v3 pinset")
    if status.st_size > MAXIMUM_RECEIPT_BYTES:
        _fail("compact v3 pinset exceeds one MiB")
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise SmallQCompactV3Error(
            f"cannot read compact v3 pinset: {error}"
        ) from error
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SmallQCompactV3Error(
            f"invalid compact v3 pinset JSON: {error}"
        ) from error
    if (
        not isinstance(value, dict)
        or _canonical_json_bytes(value) != raw
        or set(value)
        != {"schema", "schema_version", "pins", "pinset_sha256"}
        or value.get("schema") != PINSET_SCHEMA
        or value.get("schema_version") != 1
        or not isinstance(value.get("pins"), dict)
    ):
        _fail("compact v3 pinset identity or canonical encoding differs")
    raw_pins = value["pins"]
    expected_fields = set(SmallQCompactV3Pins.__dataclass_fields__)
    if set(raw_pins) != expected_fields:
        _fail("compact v3 pinset fields differ")
    try:
        pins = SmallQCompactV3Pins(**raw_pins)
    except TypeError as error:
        raise SmallQCompactV3Error(
            f"compact v3 pinset fields are malformed: {error}"
        ) from error
    _validate_pins(pins)
    observed = pinset_sha256(pins)
    if value.get("pinset_sha256") != observed or observed != expected:
        _fail("compact v3 pinset self-hash or external digest differs")
    try:
        final = path.lstat()
    except OSError as error:
        raise SmallQCompactV3Error(
            f"cannot restat compact v3 pinset: {error}"
        ) from error
    if _stat_identity(final) != _stat_identity(status):
        _fail("compact v3 pinset changed while it was loaded")
    return pins


def _source_binding_sha256(pins: SmallQCompactV3Pins) -> str:
    _validate_pins(pins)
    return hashlib.sha256(
        SOURCE_BINDING_DOMAIN + _canonical_json_bytes(pins.record())
    ).hexdigest()


def _require_regular(path: Path, *, label: str) -> os.stat_result:
    try:
        status = path.lstat()
    except OSError as error:
        raise SmallQCompactV3Error(f"cannot stat {label}: {error}") from error
    if path.is_symlink() or not stat.S_ISREG(status.st_mode):
        _fail(f"{label} must be one nonsymbolic regular file")
    return status


def _stat_identity(status: os.stat_result) -> tuple[int, ...]:
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_size,
        getattr(status, "st_mtime_ns", int(status.st_mtime * 1_000_000_000)),
        getattr(status, "st_ctime_ns", int(status.st_ctime * 1_000_000_000)),
    )


@dataclass(frozen=True)
class _InputSnapshot:
    path: Path
    identity: tuple[int, ...]
    sha256: str


@dataclass(frozen=True)
class _CompactCharacter:
    character_id: int
    parity: int


@dataclass(frozen=True)
class _CompactBatch:
    q: int
    group_exponent: int
    transform_length: int
    frequency_start: int
    frequency_count: int
    run_dft: bool
    target_bits: int
    plan_sha256: bytes
    character_start: int
    campaign_character_count: int
    batch_ordinal: int
    campaign_batch_count: int
    characters: tuple[_CompactCharacter, ...]
    sha256: bytes


def _snapshot(
    path: Path,
    *,
    label: str,
    expected_sha256: str,
) -> _InputSnapshot:
    status = _require_regular(path, label=label)
    sha256, size = semantic._sha256_file(path)
    if (
        sha256 != _digest(f"{label} expected bytes", expected_sha256)
        or size != status.st_size
    ):
        _fail(f"{label} differs from the bytes parsed and pinned earlier")
    try:
        final = path.lstat()
    except OSError as error:
        raise SmallQCompactV3Error(
            f"cannot restat {label}: {error}"
        ) from error
    if _stat_identity(final) != _stat_identity(status):
        _fail(f"{label} changed while it was hashed")
    return _InputSnapshot(path, _stat_identity(status), sha256)


def _verify_snapshots(snapshots: Sequence[_InputSnapshot]) -> None:
    for snapshot in snapshots:
        try:
            status = snapshot.path.lstat()
        except OSError as error:
            raise SmallQCompactV3Error(
                f"cannot restat bound input {snapshot.path}: {error}"
            ) from error
        if _stat_identity(status) != snapshot.identity:
            _fail(f"bound input changed during compact reduction: {snapshot.path}")
        sha256, size = semantic._sha256_file(snapshot.path)
        if (
            sha256 != snapshot.sha256
            or size != snapshot.identity[3]
        ):
            _fail(
                "bound input bytes changed during compact reduction: "
                f"{snapshot.path}"
            )
        try:
            final = snapshot.path.lstat()
        except OSError as error:
            raise SmallQCompactV3Error(
                f"cannot finally restat bound input {snapshot.path}: {error}"
            ) from error
        if _stat_identity(final) != snapshot.identity:
            _fail(f"bound input changed during compact reduction: {snapshot.path}")


def _bound_control_records(
    control: Any,
    *,
    snapshot: _InputSnapshot,
    backend: str,
) -> tuple[BinaryIO, Any]:
    """Open the exact snapshotted control inode used by the sign reducer."""

    try:
        source = control.path.open("rb")
    except OSError as error:
        raise SmallQCompactV3Error(
            f"cannot open bound time-tail control: {error}"
        ) from error
    try:
        if _stat_identity(os.fstat(source.fileno())) != snapshot.identity:
            _fail("time-tail control descriptor differs from its pinned snapshot")
        if backend == "numpy":
            assert semantic._np is not None
            records = semantic._np.memmap(
                source,
                mode="r",
                dtype="<f8",
                offset=semantic.CONTROL_HEADER.size,
                shape=(control.sample_count, 2),
            )
        else:
            records = mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ)
    except BaseException:
        source.close()
        raise
    return source, records


def _parse_compact_batch(
    path: Path,
    *,
    plan: Any,
) -> _CompactBatch:
    """Stream one batch while retaining no q-word exponent tables."""

    status = _require_regular(path, label="factored compact character batch")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        if _stat_identity(os.fstat(source.fileno())) != (
            _stat_identity(status)
        ):
            _fail("factored compact batch changed before it was opened")
        raw_header = semantic._read_exact(
            source, INPUT_HEADER.size, label="factored compact batch header"
        )
        digest.update(raw_header)
        (
            q,
            group_exponent,
            batch_count,
            transform_length,
            frequency_start,
            frequency_count,
            run_dft,
            target_bits,
        ) = factored._validated_split_header(
            raw_header,
            expected_magic=BATCH_MAGIC,
            label="factored compact batch",
        )
        raw_binding = semantic._read_exact(
            source,
            BATCH_BINDING.size,
            label="factored compact batch binding",
        )
        digest.update(raw_binding)
        (
            plan_sha256,
            character_start,
            campaign_character_count,
            batch_ordinal,
            campaign_batch_count,
        ) = BATCH_BINDING.unpack(raw_binding)
        if (
            plan_sha256 != plan.sha256
            or q != plan.q
            or group_exponent != plan.group_exponent
            or transform_length != plan.transform_length
            or frequency_start != plan.frequency_start
            or frequency_count != plan.frequency_count
            or run_dft != plan.run_dft
            or target_bits != plan.target_bits
            or campaign_character_count != plan.campaign_character_count
            or character_start + batch_count > campaign_character_count
            or campaign_batch_count <= 0
            or batch_ordinal >= campaign_batch_count
        ):
            _fail("factored compact batch differs from its shared plan")
        characters: list[_CompactCharacter] = []
        exponent_bytes = q * struct.calcsize("<I")
        for _local in range(batch_count):
            raw_character = semantic._read_exact(
                source,
                CHARACTER_HEADER.size,
                label="factored compact character header",
            )
            digest.update(raw_character)
            (
                character_id,
                parity,
                reserved0,
                reserved1,
                epsilon_re,
                epsilon_im,
                epsilon_radius,
            ) = CHARACTER_HEADER.unpack(raw_character)
            if (
                parity not in (0, 1)
                or reserved0
                or reserved1
                or not all(
                    math.isfinite(value)
                    for value in (
                        epsilon_re,
                        epsilon_im,
                        epsilon_radius,
                    )
                )
                or epsilon_radius < 0.0
            ):
                _fail("factored compact character header is invalid")
            raw_exponents = semantic._read_exact(
                source,
                exponent_bytes,
                label="factored compact character exponent table",
            )
            digest.update(raw_exponents)
            if semantic._np is not None:
                exponents = semantic._np.frombuffer(
                    raw_exponents, dtype="<u4"
                )
                invalid = (exponents != NONUNIT_EXPONENT) & (
                    exponents >= group_exponent
                )
                if bool(semantic._np.any(invalid)):
                    _fail(
                        "factored compact character exponent is outside "
                        "the group exponent"
                    )
            else:
                for (exponent,) in struct.iter_unpack(
                    "<I", raw_exponents
                ):
                    if (
                        exponent != NONUNIT_EXPONENT
                        and exponent >= group_exponent
                    ):
                        _fail(
                            "factored compact character exponent is outside "
                            "the group exponent"
                        )
            characters.append(_CompactCharacter(character_id, parity))
        if source.read(1):
            _fail("factored compact batch has trailing bytes")
        final_open = os.fstat(source.fileno())
    try:
        final_path = path.lstat()
    except OSError as error:
        raise SmallQCompactV3Error(
            f"cannot restat factored compact batch: {error}"
        ) from error
    if (
        _stat_identity(final_open) != _stat_identity(status)
        or _stat_identity(final_path) != _stat_identity(status)
    ):
        _fail("factored compact batch changed while it was streamed")
    return _CompactBatch(
        q=q,
        group_exponent=group_exponent,
        transform_length=transform_length,
        frequency_start=frequency_start,
        frequency_count=frequency_count,
        run_dft=run_dft,
        target_bits=target_bits,
        plan_sha256=plan_sha256,
        character_start=character_start,
        campaign_character_count=campaign_character_count,
        batch_ordinal=batch_ordinal,
        campaign_batch_count=campaign_batch_count,
        characters=tuple(characters),
        sha256=digest.digest(),
    )


def _canonical_plan_and_batches(
    plan_path: Path,
    batch_paths: Sequence[Path],
) -> tuple[Any, tuple[_CompactBatch, ...], Any, tuple[int, int]]:
    """Preflight the exact plan/roster with O(characters + q) memory."""

    plan = factored.parse_factored_shared_plan_metadata(plan_path)
    canonical = base.transform_parameters(plan.q)
    if (
        plan.transform_length != canonical.transform_length
        or plan.frequency_start != 0
        or plan.frequency_count != canonical.transform_length
        or plan.eta != canonical.eta
        or plan.a != canonical.a
        or plan.b != canonical.b
        or not plan.run_dft
    ):
        _fail("compact v3 reduction requires the canonical source plan")
    # Metadata parsing deliberately avoids retaining the source-scale seed
    # cache.  Still replay every wire record here so a hash-pinned but
    # malformed cache cannot reach a nominally successful typed receipt.
    for _record in factored._iter_factored_shared_plan_seeds(
        plan_path,
        plan,
        chunk_records=SHARED_SEED_VALIDATION_CHUNK_RECORDS,
    ):
        pass
    if not batch_paths:
        _fail("compact v3 reduction requires character batches")
    batches: list[_CompactBatch] = []
    roster: list[int] = []
    parity_counts = [0, 0]
    next_start = 0
    promised_count: int | None = None
    for ordinal, path in enumerate(batch_paths):
        batch = _parse_compact_batch(path, plan=plan)
        if promised_count is None:
            promised_count = batch.campaign_batch_count
        if (
            batch.batch_ordinal != ordinal
            or batch.campaign_batch_count != promised_count
            or batch.character_start != next_start
        ):
            _fail(
                "factored compact batches are not one ordered partition"
            )
        for character in batch.characters:
            roster.append(character.character_id)
            parity_counts[character.parity] += 1
        next_start += len(batch.characters)
        batches.append(batch)
    if (
        promised_count != len(batches)
        or next_start != plan.campaign_character_count
        or len(set(roster)) != len(roster)
        or _character_roster_digest(roster)
        != plan.character_roster_sha256
    ):
        _fail("factored compact character coverage or roster differs")
    return (
        plan,
        tuple(batches),
        canonical,
        (parity_counts[0], parity_counts[1]),
    )


def _atomic_immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    raw = _canonical_json_bytes(dict(value))
    if len(raw) > MAXIMUM_RECEIPT_BYTES:
        _fail("compact v3 receipt exceeds one MiB")
    if path.exists() or path.is_symlink():
        _fail("refusing to replace an immutable compact v3 receipt")
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


def _reject_aliases(
    *,
    inputs: Sequence[Path],
    state_path: Path,
    receipt_path: Path | None,
) -> None:
    resolved_inputs = [path.resolve() for path in inputs]
    if len(set(resolved_inputs)) != len(resolved_inputs):
        _fail("compact v3 typed inputs contain duplicate paths")
    raw_outputs = [state_path]
    if receipt_path is not None:
        raw_outputs.append(receipt_path)
    for output in raw_outputs:
        if output.exists() or output.is_symlink():
            _fail("refusing to replace an immutable compact v3 output")
    outputs = [output.resolve() for output in raw_outputs]
    if len(set(outputs)) != len(outputs):
        _fail("compact v3 state and receipt paths alias")
    if set(outputs) & set(resolved_inputs):
        _fail("compact v3 output path aliases a required input")


def _canonical_roster(
    *,
    q: int,
    batches: Sequence[Any],
    campaign_character_count: int,
) -> tuple[tuple[Mapping[str, Any], ...], str]:
    identities = primitive_frequency_records_bulk(q)
    if len(identities) != campaign_character_count or not identities:
        _fail("factored plan count differs from the complete primitive roster")
    ordinal = 0
    for batch in batches:
        for character in batch.characters:
            identity = identities[ordinal]
            if (
                character.character_id != identity["conrey_number"]
                or character.parity != identity["parity"]
                or identity["primitive_ordinal"] != ordinal
            ):
                _fail(
                    "factored character id/parity differs from the canonical "
                    f"primitive roster at ordinal {ordinal}"
                )
            ordinal += 1
    if ordinal != len(identities):
        _fail("factored character partition does not cover the complete roster")
    return tuple(identities), compact.complete_primitive_roster_sha256_v3(q)


@dataclass
class _StreamRun:
    completed: bool = False
    raw_bytes: int = 0
    frame_count: int = 0
    item_count: int = 0
    ambiguous: int = 0
    negative: int = 0
    positive: int = 0
    finite_terms_reported: int = 0
    butterflies_reported: int = 0
    cuda_elapsed_reported: int = 0
    raw_stream_sha256: str = ""


def reduce_factored_service_stream_to_compact_v3(
    plan_path: Path,
    batch_paths: Sequence[Path],
    control_path: Path,
    control_receipt_path: Path,
    stream: BinaryIO,
    state_path: Path,
    *,
    pins: SmallQCompactV3Pins,
    receipt_path: Path | None = None,
    chunk_items: int = DEFAULT_CHUNK_ITEMS,
    backend: str = "auto",
    maximum_state_bytes: int = compact.DEFAULT_MAXIMUM_ARTIFACT_BYTES,
) -> dict[str, Any]:
    """Stream one complete typed q/span directly into ``TGDCSB03``.

    Production mode requires the full canonical small-q source span.
    ``structural_bounded_span_kat=True`` permits a shorter exact span solely
    for bounded protocol tests; every source/evidence/admission decision
    remains false in both modes.
    """

    _validate_pins(pins)
    if (
        isinstance(chunk_items, bool)
        or not isinstance(chunk_items, int)
        or chunk_items <= 0
        or chunk_items > MAXIMUM_CHUNK_ITEMS
    ):
        _fail(
            "compact v3 chunk_items must be a positive integer no larger "
            f"than {MAXIMUM_CHUNK_ITEMS}"
        )
    if backend not in {"auto", "numpy", "scalar"}:
        _fail("compact v3 backend must be auto, numpy, or scalar")
    if backend == "numpy" and semantic._np is None:
        _fail("NumPy backend requested but NumPy is unavailable")
    selected_backend = (
        "numpy"
        if backend == "auto" and semantic._np is not None
        else backend
    )
    if selected_backend == "auto":
        selected_backend = "scalar"

    input_paths = [
        Path(plan_path),
        *(Path(path) for path in batch_paths),
        Path(control_path),
        Path(control_receipt_path),
    ]
    for index, path in enumerate(input_paths):
        _require_regular(path, label=f"compact v3 input {index}")
    _reject_aliases(
        inputs=input_paths,
        state_path=Path(state_path),
        receipt_path=None if receipt_path is None else Path(receipt_path),
    )

    plan, batches, parameters, parity_counts = _canonical_plan_and_batches(
        Path(plan_path), tuple(Path(path) for path in batch_paths)
    )
    batch_partition_sha256 = semantic._batch_partition_digest(batches)
    _identities, roster_sha256 = _canonical_roster(
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
        _fail("compact v3 span is outside the exact small-q source grid")
    full_source_span = first == 0 and stop == full_stop
    if not pins.structural_bounded_span_kat and not full_source_span:
        _fail("production compact v3 reduction requires the full source span")
    sample_start = first // step
    sample_count = (stop - first) // step

    actual_pins = SmallQCompactV3Pins(
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
    if actual_pins != pins:
        _fail("factored compact v3 inputs differ from the external pinset")

    expected_input_sha256 = (
        plan.sha256.hex(),
        *(batch.sha256.hex() for batch in batches),
        control.sha256,
        hashlib.sha256(
            semantic.canonical_json_bytes(control_receipt)
        ).hexdigest(),
    )
    snapshots = tuple(
        _snapshot(
            path,
            label=f"compact v3 input {index}",
            expected_sha256=expected_input_sha256[index],
        )
        for index, path in enumerate(input_paths)
    )
    source_binding = _source_binding_sha256(actual_pins)
    run = _StreamRun()
    raw_digest = hashlib.sha256()
    control_snapshot = snapshots[len(batches) + 1]

    def code_chunks() -> Iterator[Any]:
        control_source, controls = _bound_control_records(
            control,
            snapshot=control_snapshot,
            backend=selected_backend,
        )
        try:
            for ordinal, batch in enumerate(batches):
                header_raw = semantic._read_exact(
                    stream, v2.OUTPUT_HEADER.size, label="TGDBSQR3 header"
                )
                binding_raw = semantic._read_exact(
                    stream,
                    SERVICE_OUTPUT_BINDING.size,
                    label="TGDBSQR3 binding",
                )
                raw_digest.update(header_raw)
                raw_digest.update(binding_raw)
                run.raw_bytes += len(header_raw) + len(binding_raw)
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
                    cuda_elapsed,
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
                expected_butterflies = (
                    batch_count
                    * (plan.transform_length // 2)
                    * (plan.transform_length.bit_length() - 1)
                )
                if (
                    magic != REDUCED_SERVICE_OUTPUT_MAGIC
                    or version != FORMAT_VERSION
                    or q != plan.q
                    or batch_count != len(batch.characters)
                    or run_dft != 1
                    or frequency_start != sample_start
                    or frequency_count != sample_count
                    or binding != expected_binding
                    or butterflies != expected_butterflies
                    or status_or != 0
                    or reserved != 0
                ):
                    _fail(
                        "TGDBSQR3 compact frame identity, span, binding, "
                        "or status differs"
                    )
                frame_items = batch_count * sample_count
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
                    raw = semantic._read_exact(
                        stream,
                        count * v2.OUTPUT_ITEM.size,
                        label="TGDBSQR3 compact item chunk",
                    )
                    raw_digest.update(raw)
                    run.raw_bytes += len(raw)
                    if selected_backend == "numpy":
                        codes, local = semantic._numpy_codes(
                            raw,
                            flat_start=flat,
                            sample_count=sample_count,
                            sample_start=sample_start,
                            character_ids=character_ids,
                            parities=parities,
                            controls=controls,
                        )
                    else:
                        codes, local = semantic._scalar_codes(
                            raw,
                            flat_start=flat,
                            sample_count=sample_count,
                            sample_start=sample_start,
                            characters=batch.characters,
                            control_mapping=controls,
                        )
                    run.ambiguous += local[semantic.AMBIGUOUS_CODE]
                    run.negative += local[semantic.NEGATIVE_CODE]
                    run.positive += local[semantic.POSITIVE_CODE]
                    flat += count
                    if (
                        semantic._np is not None
                        and isinstance(codes, semantic._np.ndarray)
                    ):
                        yield codes.astype(
                            semantic._np.uint8, copy=False
                        ).tobytes()
                    else:
                        yield codes
                run.frame_count += 1
                run.item_count += frame_items
                run.finite_terms_reported += terms
                run.butterflies_reported += butterflies
                run.cuda_elapsed_reported += cuda_elapsed
            if stream.read(1):
                _fail("TGDBSQR3 compact stream has trailing bytes")
            expected_items = plan.campaign_character_count * sample_count
            if (
                run.frame_count != len(batches)
                or run.item_count != expected_items
                or run.ambiguous + run.negative + run.positive
                != expected_items
            ):
                _fail("TGDBSQR3 compact stream coverage totals differ")
            if (
                _stat_identity(os.fstat(control_source.fileno()))
                != control_snapshot.identity
            ):
                _fail(
                    "time-tail control changed while its semantic records "
                    "were consumed"
                )
            _verify_snapshots(snapshots)
            run.raw_stream_sha256 = raw_digest.hexdigest()
            run.completed = True
        finally:
            if (
                semantic._np is not None
                and isinstance(controls, semantic._np.memmap)
            ):
                controls._mmap.close()
            else:
                controls.close()
            control_source.close()

    started = time.perf_counter_ns()
    state_record = compact.write_flat_sign_codes_v3(
        Path(state_path),
        q=plan.q,
        frame_count=len(batches),
        first_t_numerator=first,
        stop_t_numerator=stop,
        code_chunks=code_chunks(),
        source_binding_sha256=source_binding,
        expected_roster_sha256=roster_sha256,
        maximum_bytes=maximum_state_bytes,
    )
    elapsed = time.perf_counter_ns() - started
    if not run.completed:
        _fail("compact v3 writer did not exhaust the typed source stream")

    body: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "schema_version": 1,
        "algorithm_id": ALGORITHM_ID,
        "author": AUTHOR,
        "atom_id": base.ATOM_ID,
        "classification": (
            "typed_factored_disk_to_compact_state_"
            "not_dft_replay_zero_completeness_or_atom_discharge"
        ),
        "q": plan.q,
        "pinset": actual_pins.record(),
        "pinset_sha256": pinset_sha256(actual_pins),
        "pinset_matches_exact_inputs": True,
        "pinset_authority_established_by_reducer": False,
        "shared_plan_cache_sha256": plan.sha256.hex(),
        "character_batch_partition_sha256": (
            batch_partition_sha256.hex()
        ),
        "time_tail_control_sha256": control.sha256,
        "time_tail_control_receipt_sha256": control_receipt[
            "receipt_sha256"
        ],
        "compact_source_binding_sha256": source_binding,
        "compact_source_binding_includes_raw_disk_stream_sha256": False,
        "raw_disk_stream_sha256_pinned_before_reduction": False,
        "raw_disk_stream_sha256_receipt_only": run.raw_stream_sha256,
        "raw_disk_stream_integrity_requires_retained_receipt_state_pair": True,
        "raw_disk_stream_bytes_consumed": run.raw_bytes,
        "raw_disk_stream_materialized": False,
        "packed_sign_artifact_materialized": False,
        "character_major_disk_rows_streamed_once": True,
        "strict_sign_codes_fed_directly_to_TGDCSB03": True,
        "full_character_partition_checked": True,
        "complete_primitive_roster_checked": True,
        "complete_primitive_roster_formula_and_order_checked": True,
        "character_exponent_tables_structurally_validated": True,
        "character_exponent_tables_canonical_replayed": False,
        "shared_frequency_seed_records_structurally_validated": True,
        "shared_frequency_seed_validation_chunk_records": (
            SHARED_SEED_VALIDATION_CHUNK_RECORDS
        ),
        "shared_frequency_seed_values_higher_precision_replayed": False,
        "character_epsilon_disks_higher_precision_replayed": False,
        "exact_span_checked": True,
        "full_source_span": full_source_span,
        "structural_bounded_span_kat": pins.structural_bounded_span_kat,
        "frame_count": run.frame_count,
        "sample_count_per_character": sample_count,
        "item_count": run.item_count,
        "ambiguous_sample_count": run.ambiguous,
        "negative_sample_count": run.negative,
        "positive_sample_count": run.positive,
        "finite_terms_reported_not_recomputed": run.finite_terms_reported,
        "butterflies_reported_and_shape_checked": (
            run.butterflies_reported
        ),
        "cuda_elapsed_nanoseconds_reported_not_trusted": (
            run.cuda_elapsed_reported
        ),
        "backend": selected_backend,
        "elapsed_nanoseconds": elapsed,
        "compact_state_artifact": state_record,
        "artifact_self_authenticates_producer_fusion": False,
        "time_tail_control_higher_precision_receipt_validated": True,
        "dft_arithmetic_containment_replayed": False,
        "input_stream_arithmetic_replayed": False,
        "trusted_execution_or_replayable_dft_evidence_required": True,
        "pointwise_transition_lower_bounds_proved": False,
        "physical_complete_roster_equivalence_realized": False,
        "turing_totals_realized": False,
        "ambiguity_refinement_complete": False,
        "source_scale_storage_admitted": False,
        "source_admission_enabled": False,
        "external_atom_discharged": False,
        "production_ready": False,
    }
    result = dict(body)
    result["receipt_sha256"] = hashlib.sha256(
        _canonical_json_bytes(body)
    ).hexdigest()
    if receipt_path is not None:
        _atomic_immutable_json(Path(receipt_path), result)
    return result


__all__ = [
    "ALGORITHM_ID",
    "DEFAULT_CHUNK_ITEMS",
    "MAXIMUM_CHUNK_ITEMS",
    "PINSET_SCHEMA",
    "RECEIPT_SCHEMA",
    "SHARED_SEED_VALIDATION_CHUNK_RECORDS",
    "SmallQCompactV3Error",
    "SmallQCompactV3Pins",
    "load_pinset",
    "pinset_sha256",
    "reduce_factored_service_stream_to_compact_v3",
]
