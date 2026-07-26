# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Semantic sign reduction for the split-v3 Platt--Booker small-q stream.

The CUDA ``TGDBSQR3`` stream contains one Euclidean complex disk for every
primitive-character/source-sample coordinate.  For a Fourier disk

    |F - (x + i y)| <= r

and a certified upper bound ``e >= time_tail / (2*pi/b)``, positivity of the
scale and untilt factors makes either of the exact binary64 comparisons

    r + e < x              or              x < -(r + e)

sufficient for the final completed-real sign.  This module performs those
comparisons with an outward-rounded binary64 sum, retaining every undecidable
coordinate as the explicit code zero.

The expensive analytic bound is character-independent.  A q-level
``TGDBSQT1`` control stores one even and one odd ``e`` per source ordinate.
The producer and higher-precision checker below use the existing Arb
implementation of Platt's displayed time-periodization bound.  A complete
control therefore has O(modulus/source-ordinate) rather than
O(character/source-ordinate) records.

The resulting ``TGDBSSG1`` payload is exactly two bits per coordinate in
character-major/sample-major order:

* 0: ambiguous and requiring refinement;
* 1: certified negative, conditional on the retained DFT containment;
* 2: certified positive, conditional on the retained DFT containment;
* 3: reserved and rejected.

No sign-change scan, zero count, multiplicity inference, interpolation,
exception closure, Turing argument, or GRH claim is performed.  Discarding the
raw disk stream also still requires measured/trusted execution evidence or a
separately replayable DFT artifact.  These limitations are recorded in every
receipt.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import time
from typing import Any, BinaryIO, Mapping, NoReturn, Sequence

try:
    import numpy as _np
except ImportError:  # pragma: no cover - scalar fallback is covered
    _np = None

from tg_verifier import dirichlet_booker_smallq as base
from tg_verifier import dirichlet_booker_smallq_certified as v2
from tg_verifier.dirichlet_booker_smallq_factored import (
    FORMAT_VERSION,
    REDUCED_SERVICE_OUTPUT_MAGIC,
    SERVICE_OUTPUT_BINDING,
    ParsedCharacterBatch,
    ParsedSharedPlan,
)
from tg_verifier.dirichlet_booker_smallq_output_stream import (
    _preflight_batches,
    _read_exact,
)


AUTHOR = "Gershon Bialer"
ALGORITHM_ID = "platt-booker-smallq-semantic-sign-reducer-v1"
CONTROL_ALGORITHM_ID = "platt-booker-smallq-time-tail-control-v1"
CONTROL_CHECKER_ID = "arb-higher-precision-time-tail-control-replay-v1"
CONTROL_RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_booker_smallq.time_tail_control_replay.v1"
)
REDUCER_RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_booker_smallq.semantic_sign_receipt.v1"
)

CONTROL_MAGIC = b"TGDBSQT1"
SIGN_MAGIC = b"TGDBSSG1"
CONTROL_FORMAT_VERSION = 1
SIGN_FORMAT_VERSION = 1

# magic, version, q, even characters, odd characters, transform length,
# source sample count, producer precision, reserved, complete plan SHA-256, and
# the ordered complete character-batch partition SHA-256.  The latter binds
# each character's parity rather than merely the plan's character-id roster.
CONTROL_HEADER = struct.Struct("<8sIIIIQQII32s32s")
# Natural sample order is implicit.  Both words are outward upper bounds for
# time_tail / (2*pi/b), first for even and then for odd characters.
CONTROL_ITEM = struct.Struct("<dd")

# magic, version, q, bits/code, ambiguous code, negative code, positive code,
# character count, source sample count, payload bytes, plan/control/roster
# SHA-256.  Payload order is the exact plan roster times [0,sample_count).
SIGN_HEADER = struct.Struct("<8sIIIIIIQQQ32s32s32s")

AMBIGUOUS_CODE = 0
NEGATIVE_CODE = 1
POSITIVE_CODE = 2
RESERVED_CODE = 3
BITS_PER_CODE = 2
DEFAULT_CHUNK_ITEMS = 1 << 16
MAX_RECEIPT_BYTES = 1024 * 1024


class SmallQSemanticReducerError(RuntimeError):
    """A control, source stream, sign decision, or binding failed closed."""


def _fail(message: str) -> NoReturn:
    raise SmallQSemanticReducerError(message)


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while block := source.read(8 * 1024 * 1024):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


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


def _canonical_source_plan(
    plan_path: Path, batch_paths: Sequence[Path]
) -> tuple[
    ParsedSharedPlan,
    tuple[ParsedCharacterBatch, ...],
    base.TransformParameters,
    tuple[int, int],
]:
    plan, batches = _preflight_batches(plan_path, batch_paths)
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
        _fail("semantic reduction requires the exact canonical source plan")
    parity_counts = [0, 0]
    for batch in batches:
        for character in batch.characters:
            if character.parity not in (0, 1):
                _fail("character parity is outside the complete even/odd split")
            parity_counts[character.parity] += 1
    if sum(parity_counts) != plan.campaign_character_count:
        _fail("character parity coverage differs from the complete roster")
    return plan, batches, canonical, (parity_counts[0], parity_counts[1])


@dataclass(frozen=True)
class TimeTailControl:
    path: Path
    q: int
    even_character_count: int
    odd_character_count: int
    transform_length: int
    sample_count: int
    precision_bits: int
    plan_sha256: bytes
    batch_partition_sha256: bytes
    sha256: str
    size_bytes: int


def _parse_control_header(raw: bytes, *, path: Path) -> TimeTailControl:
    if len(raw) != CONTROL_HEADER.size:
        _fail("truncated TGDBSQT1 header")
    (
        magic,
        version,
        q,
        even_count,
        odd_count,
        transform_length,
        sample_count,
        precision_bits,
        reserved,
        plan_sha256,
        batch_partition_sha256,
    ) = CONTROL_HEADER.unpack(raw)
    if (
        magic != CONTROL_MAGIC
        or version != CONTROL_FORMAT_VERSION
        or not base.SOURCE_Q_START <= q <= base.SOURCE_Q_STOP
        or even_count + odd_count <= 0
        or transform_length <= 0
        or transform_length & (transform_length - 1)
        or sample_count <= 0
        or sample_count > transform_length
        or not 128 <= precision_bits <= 4096
        or reserved != 0
    ):
        _fail("invalid TGDBSQT1 header")
    expected_size = CONTROL_HEADER.size + sample_count * CONTROL_ITEM.size
    try:
        observed_size = path.stat().st_size
    except OSError as error:
        raise SmallQSemanticReducerError(f"cannot stat TGDBSQT1: {error}") from error
    if observed_size != expected_size:
        _fail("TGDBSQT1 size differs from its source sample count")
    digest, size = _sha256_file(path)
    if size != observed_size:
        _fail("TGDBSQT1 changed while hashing")
    return TimeTailControl(
        path=path,
        q=q,
        even_character_count=even_count,
        odd_character_count=odd_count,
        transform_length=transform_length,
        sample_count=sample_count,
        precision_bits=precision_bits,
        plan_sha256=plan_sha256,
        batch_partition_sha256=batch_partition_sha256,
        sha256=digest,
        size_bytes=size,
    )


def load_time_tail_control_metadata(path: Path) -> TimeTailControl:
    with path.open("rb") as source:
        raw = source.read(CONTROL_HEADER.size)
    return _parse_control_header(raw, path=path)


def _validate_control_binding(
    control: TimeTailControl,
    *,
    plan: ParsedSharedPlan,
    parameters: base.TransformParameters,
    parity_counts: tuple[int, int],
    batch_partition_sha256: bytes,
) -> None:
    if (
        control.q != plan.q
        or control.plan_sha256 != plan.sha256
        or control.batch_partition_sha256 != batch_partition_sha256
        or control.even_character_count != parity_counts[0]
        or control.odd_character_count != parity_counts[1]
        or control.transform_length != parameters.transform_length
        or control.sample_count != parameters.sample_count
    ):
        _fail("TGDBSQT1 plan, parity roster, or source grid binding differs")


def _batch_partition_digest(
    batches: Sequence[ParsedCharacterBatch],
) -> bytes:
    digest = hashlib.sha256()
    digest.update(
        b"SparkInterval/DirichletBookerSmallQ/"
        b"semantic-control-batch-partition/v1\x00"
    )
    digest.update(struct.pack("<Q", len(batches)))
    for batch in batches:
        digest.update(batch.sha256)
        digest.update(
            struct.pack(
                "<QQQQ",
                batch.character_start,
                batch.campaign_character_count,
                batch.batch_ordinal,
                batch.campaign_batch_count,
            )
        )
        digest.update(struct.pack("<Q", len(batch.characters)))
        for character in batch.characters:
            digest.update(struct.pack("<QI", character.character_id, character.parity))
    return digest.digest()


def _replay_canonical_character_roster(
    plan: ParsedSharedPlan, batches: Sequence[ParsedCharacterBatch]
) -> None:
    """Recompute the complete source Conrey roster and each parity exactly."""

    expected_count = base.primitive_character_count(plan.q)
    if expected_count != plan.campaign_character_count:
        _fail("semantic control character count differs from the source roster")
    ordinal = 0
    for batch in batches:
        for character in batch.characters:
            descriptor = base.primitive_character_descriptor(plan.q, ordinal)
            if (
                int(descriptor["conrey_number"]) != character.character_id
                or int(descriptor["parity"]) != character.parity
            ):
                _fail(
                    "semantic control character id/parity differs from the "
                    f"canonical source roster at ordinal {ordinal}"
                )
            ordinal += 1
    if ordinal != expected_count:
        _fail("semantic control canonical character roster is incomplete")


def _validate_control_words(control: TimeTailControl) -> None:
    """Check both parity words for every source ordinate in bounded memory."""

    with control.path.open("rb") as source:
        if len(source.read(CONTROL_HEADER.size)) != CONTROL_HEADER.size:
            _fail("truncated TGDBSQT1 during word validation")
        remaining = control.sample_count
        chunk_records = 1 << 18
        while remaining:
            count = min(remaining, chunk_records)
            raw = _read_exact(
                source, count * CONTROL_ITEM.size, label="TGDBSQT1 control records"
            )
            if _np is not None:
                words = _np.frombuffer(raw, dtype="<f8")
                if not bool(_np.all(_np.isfinite(words) & (words >= 0.0))):
                    _fail("TGDBSQT1 contains a nonfinite or negative bound")
            else:
                for even, odd in CONTROL_ITEM.iter_unpack(raw):
                    if not (
                        math.isfinite(even)
                        and even >= 0.0
                        and math.isfinite(odd)
                        and odd >= 0.0
                    ):
                        _fail("TGDBSQT1 contains a nonfinite or negative bound")
            remaining -= count
        if source.read(1):
            _fail("TGDBSQT1 has trailing bytes")


def write_time_tail_control(
    path: Path,
    plan_path: Path,
    batch_paths: Sequence[Path],
    *,
    precision_bits: int = 192,
) -> dict[str, Any]:
    """Materialize every q-level even/odd time-tail-over-scale upper bound.

    This is an untrusted producer.  ``verify_time_tail_control`` must replay
    every record at a higher precision before semantic reduction.
    """

    if (
        isinstance(precision_bits, bool)
        or not isinstance(precision_bits, int)
        or not 128 <= precision_bits <= 4096
    ):
        _fail("control precision must lie in 128..4096 bits")
    plan, batches, parameters, parity_counts = _canonical_source_plan(
        plan_path, batch_paths
    )
    _replay_canonical_character_roster(plan, batches)
    batch_partition_sha256 = _batch_partition_digest(batches)
    base._require_flint()
    header = CONTROL_HEADER.pack(
        CONTROL_MAGIC,
        CONTROL_FORMAT_VERSION,
        plan.q,
        parity_counts[0],
        parity_counts[1],
        parameters.transform_length,
        parameters.sample_count,
        precision_bits,
        0,
        plan.sha256,
        batch_partition_sha256,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    started = time.perf_counter_ns()
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(header)
            with base.ctx.workprec(precision_bits):
                scale = 2 * base.arb.pi() / base._arb_fraction(parameters.b)
                base._positive_arb(scale, "source Fourier scale")
                for sample in range(parameters.sample_count):
                    t = Fraction(sample, 1) / parameters.a
                    bounds = []
                    for parity in (0, 1):
                        tail = base._time_periodization_bound(
                            q=plan.q,
                            parity=parity,
                            eta=parameters.eta,
                            t=t,
                            b=parameters.b,
                        )
                        bounds.append(v2._upper(tail / scale))
                    output.write(CONTROL_ITEM.pack(bounds[0], bounds[1]))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    elapsed = time.perf_counter_ns() - started
    control = load_time_tail_control_metadata(path)
    _validate_control_binding(
        control,
        plan=plan,
        parameters=parameters,
        parity_counts=parity_counts,
        batch_partition_sha256=batch_partition_sha256,
    )
    return {
        "algorithm_id": CONTROL_ALGORITHM_ID,
        "all_source_ordinates_materialized": True,
        "atom_id": base.ATOM_ID,
        "author": AUTHOR,
        "character_parity_counts": list(parity_counts),
        "character_batch_partition_sha256": batch_partition_sha256.hex(),
        "canonical_primitive_character_roster_replayed": True,
        "character_id_parity_mapping_replayed": True,
        "classification": "untrusted_time_tail_control_requires_independent_replay",
        "control_sha256": control.sha256,
        "control_size_bytes": control.size_bytes,
        "elapsed_nanoseconds": elapsed,
        "external_atom_discharged": False,
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.time_tail_control.v1",
        "plan_sha256": plan.sha256.hex(),
        "precision_bits": precision_bits,
        "q": plan.q,
        "sample_count": parameters.sample_count,
        "transform_length": parameters.transform_length,
    }


def verify_time_tail_control(
    path: Path,
    plan_path: Path,
    batch_paths: Sequence[Path],
    *,
    guard_bits: int = 64,
    receipt_path: Path | None = None,
) -> dict[str, Any]:
    """Higher-precision replay of every stored parity/source-ordinate bound."""

    if (
        isinstance(guard_bits, bool)
        or not isinstance(guard_bits, int)
        or not 32 <= guard_bits <= 4096
    ):
        _fail("control replay guard must lie in 32..4096 bits")
    plan, batches, parameters, parity_counts = _canonical_source_plan(
        plan_path, batch_paths
    )
    _replay_canonical_character_roster(plan, batches)
    batch_partition_sha256 = _batch_partition_digest(batches)
    control = load_time_tail_control_metadata(path)
    _validate_control_binding(
        control,
        plan=plan,
        parameters=parameters,
        parity_counts=parity_counts,
        batch_partition_sha256=batch_partition_sha256,
    )
    base._require_flint()
    started = time.perf_counter_ns()
    with path.open("rb") as source:
        header = _read_exact(source, CONTROL_HEADER.size, label="TGDBSQT1 header")
        if header != CONTROL_HEADER.pack(
            CONTROL_MAGIC,
            CONTROL_FORMAT_VERSION,
            plan.q,
            parity_counts[0],
            parity_counts[1],
            parameters.transform_length,
            parameters.sample_count,
            control.precision_bits,
            0,
            plan.sha256,
            batch_partition_sha256,
        ):
            _fail("TGDBSQT1 header changed before replay")
        with base.ctx.workprec(control.precision_bits + guard_bits):
            scale = 2 * base.arb.pi() / base._arb_fraction(parameters.b)
            base._positive_arb(scale, "replayed source Fourier scale")
            for sample in range(parameters.sample_count):
                raw = _read_exact(
                    source, CONTROL_ITEM.size, label="TGDBSQT1 control record"
                )
                stored = CONTROL_ITEM.unpack(raw)
                if not all(math.isfinite(value) and value >= 0.0 for value in stored):
                    _fail("TGDBSQT1 contains a nonfinite or negative bound")
                t = Fraction(sample, 1) / parameters.a
                for parity in (0, 1):
                    fresh = base._time_periodization_bound(
                        q=plan.q,
                        parity=parity,
                        eta=parameters.eta,
                        t=t,
                        b=parameters.b,
                    ) / scale
                    if not fresh <= base.arb(stored[parity]):
                        _fail(
                            "TGDBSQT1 understates a higher-precision "
                            f"time-tail bound at sample {sample}, parity {parity}"
                        )
        if source.read(1):
            _fail("TGDBSQT1 has trailing bytes after replay")
    elapsed = time.perf_counter_ns() - started
    receipt: dict[str, Any] = {
        "algorithm_id": CONTROL_ALGORITHM_ID,
        "all_even_and_odd_records_higher_precision_replayed": True,
        "all_source_ordinates_replayed": True,
        "atom_id": base.ATOM_ID,
        "author": AUTHOR,
        "character_parity_counts": list(parity_counts),
        "character_batch_partition_sha256": batch_partition_sha256.hex(),
        "canonical_primitive_character_roster_replayed": True,
        "character_id_parity_mapping_replayed": True,
        "checker_id": CONTROL_CHECKER_ID,
        "classification": "exact_time_tail_control_replay_not_grh_or_execution_evidence",
        "control_sha256": control.sha256,
        "control_size_bytes": control.size_bytes,
        "elapsed_nanoseconds": elapsed,
        "external_atom_discharged": False,
        "guard_bits": guard_bits,
        "kind": CONTROL_RECEIPT_SCHEMA,
        "passed": True,
        "plan_sha256": plan.sha256.hex(),
        "producer_precision_bits": control.precision_bits,
        "q": plan.q,
        "sample_count": parameters.sample_count,
        "source_parameters_exact": True,
        "transform_length": parameters.transform_length,
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(receipt)
    ).hexdigest()
    encoded = canonical_json_bytes(receipt)
    if len(encoded) > MAX_RECEIPT_BYTES:
        _fail("control replay receipt exceeds one MiB")
    if receipt_path is not None:
        _atomic_bytes(receipt_path, encoded)
    return receipt


def _load_canonical_json(path: Path) -> Mapping[str, Any]:
    raw = path.read_bytes()
    if len(raw) > MAX_RECEIPT_BYTES:
        _fail("control replay receipt exceeds one MiB")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SmallQSemanticReducerError(
            f"invalid control replay receipt: {error}"
        ) from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail("control replay receipt is not canonical JSON")
    return value


def _validate_control_receipt(
    receipt_path: Path,
    *,
    control: TimeTailControl,
    plan: ParsedSharedPlan,
    parameters: base.TransformParameters,
    parity_counts: tuple[int, int],
    batch_partition_sha256: bytes,
) -> Mapping[str, Any]:
    receipt = _load_canonical_json(receipt_path)
    required = {
        "algorithm_id",
        "all_even_and_odd_records_higher_precision_replayed",
        "all_source_ordinates_replayed",
        "atom_id",
        "author",
        "canonical_primitive_character_roster_replayed",
        "character_batch_partition_sha256",
        "character_id_parity_mapping_replayed",
        "character_parity_counts",
        "checker_id",
        "classification",
        "control_sha256",
        "control_size_bytes",
        "elapsed_nanoseconds",
        "external_atom_discharged",
        "guard_bits",
        "kind",
        "passed",
        "plan_sha256",
        "producer_precision_bits",
        "q",
        "receipt_sha256",
        "sample_count",
        "source_parameters_exact",
        "transform_length",
    }
    if set(receipt) != required:
        _fail("control replay receipt keys differ")
    body = dict(receipt)
    claimed = body.pop("receipt_sha256", None)
    if claimed != hashlib.sha256(canonical_json_bytes(body)).hexdigest():
        _fail("control replay receipt self-hash differs")
    if (
        receipt.get("kind") != CONTROL_RECEIPT_SCHEMA
        or receipt.get("algorithm_id") != CONTROL_ALGORITHM_ID
        or receipt.get("checker_id") != CONTROL_CHECKER_ID
        or receipt.get("author") != AUTHOR
        or receipt.get("q") != plan.q
        or receipt.get("plan_sha256") != plan.sha256.hex()
        or receipt.get("control_sha256") != control.sha256
        or receipt.get("control_size_bytes") != control.size_bytes
        or receipt.get("transform_length") != parameters.transform_length
        or receipt.get("sample_count") != parameters.sample_count
        or receipt.get("character_parity_counts") != list(parity_counts)
        or receipt.get("character_batch_partition_sha256")
        != batch_partition_sha256.hex()
        or receipt.get("canonical_primitive_character_roster_replayed") is not True
        or receipt.get("character_id_parity_mapping_replayed") is not True
        or receipt.get("producer_precision_bits") != control.precision_bits
        or isinstance(receipt.get("guard_bits"), bool)
        or not isinstance(receipt.get("guard_bits"), int)
        or receipt.get("guard_bits", 0) < 32
        or receipt.get("source_parameters_exact") is not True
        or receipt.get("all_source_ordinates_replayed") is not True
        or receipt.get("all_even_and_odd_records_higher_precision_replayed")
        is not True
        or receipt.get("passed") is not True
        or receipt.get("external_atom_discharged") is not False
    ):
        _fail("control replay receipt identity, completeness, or claim differs")
    return receipt


class _PackedSignWriter:
    """Incrementally pack natural-order two-bit codes without frame padding."""

    def __init__(self, output: BinaryIO, digest: Any) -> None:
        self.output = output
        self.digest = digest
        self.pending: list[int] = []
        self.bytes_written = 0

    def _write(self, raw: bytes) -> None:
        if not raw:
            return
        self.output.write(raw)
        self.digest.update(raw)
        self.bytes_written += len(raw)

    def append(self, codes: Any) -> None:
        if _np is not None and isinstance(codes, _np.ndarray):
            array = codes.astype(_np.uint8, copy=False)
            if self.pending:
                needed = min(4 - len(self.pending), len(array))
                self.pending.extend(int(value) for value in array[:needed])
                array = array[needed:]
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
            complete = len(array) - len(array) % 4
            if complete:
                rows = array[:complete].reshape((-1, 4))
                packed = (
                    rows[:, 0]
                    | rows[:, 1] << _np.uint8(2)
                    | rows[:, 2] << _np.uint8(4)
                    | rows[:, 3] << _np.uint8(6)
                )
                self._write(packed.astype(_np.uint8, copy=False).tobytes())
            self.pending.extend(int(value) for value in array[complete:])
            return
        for code in codes:
            value = int(code)
            if not 0 <= value < 4:
                _fail("internal sign code is outside two bits")
            self.pending.append(value)
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

    def finish(self) -> None:
        if self.pending:
            value = 0
            for shift, code in enumerate(self.pending):
                value |= code << (2 * shift)
            self._write(bytes((value,)))
            self.pending.clear()


def _numpy_control_records(control: TimeTailControl) -> Any:
    assert _np is not None
    return _np.memmap(
        control.path,
        mode="r",
        dtype="<f8",
        offset=CONTROL_HEADER.size,
        shape=(control.sample_count, 2),
    )


def _scalar_control_records(control: TimeTailControl) -> Any:
    import mmap

    source = control.path.open("rb")
    mapped = mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ)
    return source, mapped


def _numpy_codes(
    raw: bytes,
    *,
    flat_start: int,
    sample_count: int,
    sample_start: int = 0,
    character_ids: Any,
    parities: Any,
    controls: Any,
) -> tuple[Any, tuple[int, int, int]]:
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
    rows = _np.frombuffer(raw, dtype=dtype)
    positions = _np.arange(flat_start, flat_start + len(rows), dtype=_np.uint64)
    character_positions = positions // _np.uint64(sample_count)
    sample_indices = positions % _np.uint64(sample_count)
    expected_ids = character_ids[character_positions]
    expected_indices = sample_indices + _np.uint64(sample_start)
    if not (
        _np.array_equal(rows["character_id"], expected_ids)
        and _np.array_equal(rows["index"], expected_indices)
        and bool(_np.all(_np.isfinite(rows["real"])))
        and bool(_np.all(_np.isfinite(rows["imaginary"])))
        and bool(_np.all(_np.isfinite(rows["radius"])))
        and bool(_np.all(rows["radius"] >= 0.0))
        and bool(_np.all(rows["status"] == 0))
        and bool(_np.all(rows["reserved"] == 0))
    ):
        _fail("TGDBSQR3 item identity, disk, or status differs")
    selected_parities = parities[character_positions]
    thresholds = controls[expected_indices, selected_parities]
    # Binary64 addition is correctly rounded to nearest.  Advancing one word
    # toward +infinity yields an upper bound for the exact sum r + e.
    boundary = _np.nextafter(
        rows["radius"] + thresholds, _np.float64(_np.inf)
    )
    if not bool(_np.all(_np.isfinite(boundary))):
        _fail("semantic sign boundary overflows binary64")
    negative = rows["real"] < -boundary
    positive = rows["real"] > boundary
    if bool(_np.any(negative & positive)):
        _fail("internal strict-sign decisions overlap")
    codes = _np.zeros(len(rows), dtype=_np.uint8)
    codes[negative] = NEGATIVE_CODE
    codes[positive] = POSITIVE_CODE
    negative_count = int(_np.count_nonzero(negative))
    positive_count = int(_np.count_nonzero(positive))
    return codes, (
        len(rows) - negative_count - positive_count,
        negative_count,
        positive_count,
    )


def _scalar_codes(
    raw: bytes,
    *,
    flat_start: int,
    sample_count: int,
    sample_start: int = 0,
    characters: Sequence[Any],
    control_mapping: Any,
) -> tuple[list[int], tuple[int, int, int]]:
    codes: list[int] = []
    counts = [0, 0, 0]
    for relative, row in enumerate(v2.OUTPUT_ITEM.iter_unpack(raw)):
        character_id, index, real, imaginary, radius, status, reserved = row
        flat = flat_start + relative
        character_position = flat // sample_count
        sample = sample_start + flat % sample_count
        character = characters[character_position]
        if (
            character_id != character.character_id
            or index != sample
            or not all(math.isfinite(value) for value in (real, imaginary, radius))
            or radius < 0.0
            or status != 0
            or reserved != 0
        ):
            _fail("TGDBSQR3 item identity, disk, or status differs")
        offset = (
            CONTROL_HEADER.size
            + sample * CONTROL_ITEM.size
            + character.parity * struct.calcsize("<d")
        )
        (threshold,) = struct.unpack_from("<d", control_mapping, offset)
        boundary = math.nextafter(radius + threshold, math.inf)
        if not math.isfinite(boundary):
            _fail("semantic sign boundary overflows binary64")
        if real < -boundary:
            code = NEGATIVE_CODE
        elif real > boundary:
            code = POSITIVE_CODE
        else:
            code = AMBIGUOUS_CODE
        codes.append(code)
        counts[code] += 1
    return codes, (counts[0], counts[1], counts[2])


def reduce_semantic_sign_stream(
    plan_path: Path,
    batch_paths: Sequence[Path],
    control_path: Path,
    control_receipt_path: Path,
    stream: BinaryIO,
    sign_path: Path,
    *,
    receipt_path: Path | None = None,
    chunk_items: int = DEFAULT_CHUNK_ITEMS,
    backend: str = "auto",
    require_eof: bool = True,
) -> dict[str, Any]:
    """Reduce a complete q-level TGDBSQR3 stream to exact ordered sign codes."""

    if (
        isinstance(chunk_items, bool)
        or not isinstance(chunk_items, int)
        or chunk_items <= 0
    ):
        _fail("chunk_items must be a positive integer")
    if not require_eof:
        _fail("semantic source reduction requires an EOF check")
    if backend not in {"auto", "numpy", "scalar"}:
        _fail("backend must be auto, numpy, or scalar")
    if backend == "numpy" and _np is None:
        _fail("NumPy backend requested but NumPy is unavailable")
    selected_backend = "numpy" if backend == "auto" and _np is not None else backend
    if selected_backend == "auto":
        selected_backend = "scalar"

    plan, batches, parameters, parity_counts = _canonical_source_plan(
        plan_path, batch_paths
    )
    batch_partition_sha256 = _batch_partition_digest(batches)
    control = load_time_tail_control_metadata(control_path)
    _validate_control_binding(
        control,
        plan=plan,
        parameters=parameters,
        parity_counts=parity_counts,
        batch_partition_sha256=batch_partition_sha256,
    )
    _validate_control_words(control)
    control_receipt = _validate_control_receipt(
        control_receipt_path,
        control=control,
        plan=plan,
        parameters=parameters,
        parity_counts=parity_counts,
        batch_partition_sha256=batch_partition_sha256,
    )

    total_items = plan.campaign_character_count * parameters.sample_count
    payload_bytes = (total_items + 3) // 4
    header = SIGN_HEADER.pack(
        SIGN_MAGIC,
        SIGN_FORMAT_VERSION,
        plan.q,
        BITS_PER_CODE,
        AMBIGUOUS_CODE,
        NEGATIVE_CODE,
        POSITIVE_CODE,
        plan.campaign_character_count,
        parameters.sample_count,
        payload_bytes,
        plan.sha256,
        bytes.fromhex(control.sha256),
        plan.character_roster_sha256,
    )
    raw_bytes = 0
    frame_count = 0
    item_count = 0
    counts = [0, 0, 0]
    started = time.perf_counter_ns()
    digest = hashlib.sha256()
    digest.update(header)
    scalar_resources: tuple[Any, Any] | None = None
    controls: Any
    if selected_backend == "numpy":
        controls = _numpy_control_records(control)
    else:
        scalar_resources = _scalar_control_records(control)
        controls = scalar_resources[1]
    sign_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{sign_path.name}.", dir=sign_path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(header)
            writer = _PackedSignWriter(output, digest)
            for ordinal, batch in enumerate(batches):
                header_raw = _read_exact(
                    stream, v2.OUTPUT_HEADER.size, label="TGDBSQR3 header"
                )
                binding_raw = _read_exact(
                    stream, SERVICE_OUTPUT_BINDING.size, label="TGDBSQR3 binding"
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
                    _terms,
                    frame_butterflies,
                    _elapsed,
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
                    or frequency_start != 0
                    or frequency_count != parameters.sample_count
                    or binding != expected_binding
                    or frame_butterflies != expected_butterflies
                    or status_or != 0
                    or reserved != 0
                ):
                    _fail(
                        "TGDBSQR3 header, source shape, binding, or status differs"
                    )
                frame_items = batch_count * parameters.sample_count
                if selected_backend == "numpy":
                    assert _np is not None
                    character_ids: Any = _np.asarray(
                        [character.character_id for character in batch.characters],
                        dtype=_np.uint64,
                    )
                    parities: Any = _np.asarray(
                        [character.parity for character in batch.characters],
                        dtype=_np.uint64,
                    )
                flat = 0
                while flat < frame_items:
                    count = min(chunk_items, frame_items - flat)
                    raw = _read_exact(
                        stream,
                        count * v2.OUTPUT_ITEM.size,
                        label="TGDBSQR3 item chunk",
                    )
                    raw_bytes += len(raw)
                    if selected_backend == "numpy":
                        codes, local_counts = _numpy_codes(
                            raw,
                            flat_start=flat,
                            sample_count=parameters.sample_count,
                            character_ids=character_ids,
                            parities=parities,
                            controls=controls,
                        )
                    else:
                        codes, local_counts = _scalar_codes(
                            raw,
                            flat_start=flat,
                            sample_count=parameters.sample_count,
                            characters=batch.characters,
                            control_mapping=controls,
                        )
                    writer.append(codes)
                    for code in range(3):
                        counts[code] += local_counts[code]
                    flat += count
                frame_count += 1
                item_count += frame_items
            writer.finish()
            if writer.bytes_written != payload_bytes:
                _fail("internal TGDBSSG1 payload byte accounting differs")
            output.flush()
            os.fsync(output.fileno())
        if stream.read(1):
            _fail("TGDBSQR3 has trailing bytes after the complete q campaign")
        if item_count != total_items or sum(counts) != total_items:
            _fail("semantic sign counts differ from complete source coverage")
        final_control_sha256, final_control_size = _sha256_file(control.path)
        if (
            final_control_sha256 != control.sha256
            or final_control_size != control.size_bytes
        ):
            _fail("TGDBSQT1 changed while semantic reduction was running")
        os.replace(temporary, sign_path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    finally:
        if scalar_resources is not None:
            scalar_resources[1].close()
            scalar_resources[0].close()
        if _np is not None and isinstance(controls, _np.memmap):
            controls._mmap.close()

    elapsed = time.perf_counter_ns() - started
    sign_sha256 = digest.hexdigest()
    observed_size = sign_path.stat().st_size
    if observed_size != len(header) + payload_bytes:
        _fail("published TGDBSSG1 size differs from the streamed byte count")
    receipt: dict[str, Any] = {
        "algorithm_id": ALGORITHM_ID,
        "all_sample_codes_retained_in_exact_character_major_order": True,
        "all_samples_strictly_signed": counts[AMBIGUOUS_CODE] == 0,
        "ambiguous_code": AMBIGUOUS_CODE,
        "ambiguous_samples_requiring_refinement": counts[AMBIGUOUS_CODE],
        "arithmetic_containment_replayed": False,
        "atom_id": base.ATOM_ID,
        "author": AUTHOR,
        "backend": selected_backend,
        "batch_count": frame_count,
        "bits_per_sample": BITS_PER_CODE,
        "character_count": plan.campaign_character_count,
        "character_batch_partition_sha256": batch_partition_sha256.hex(),
        "character_parity_counts": list(parity_counts),
        "classification": (
            "semantic_time_tail_sign_reduction_conditional_on_bound_dft_stream_"
            "not_zero_completeness_or_atom_discharge"
        ),
        "control_receipt_sha256": control_receipt["receipt_sha256"],
        "control_sha256": control.sha256,
        "control_size_bytes": control.size_bytes,
        "control_unchanged_through_reduction": True,
        "external_atom_discharged": False,
        "full_character_partition_checked": True,
        "full_source_sample_grid_checked": True,
        "item_count": item_count,
        "kind": REDUCER_RECEIPT_SCHEMA,
        "downstream_zero_multiplicities_must_be_preserved": True,
        "multiplicity_inference_performed": False,
        "multiplicity_bearing_zero_records_consumed_or_discarded": False,
        "negative_code": NEGATIVE_CODE,
        "negative_samples": counts[NEGATIVE_CODE],
        "plan_sha256": plan.sha256.hex(),
        "positive_code": POSITIVE_CODE,
        "positive_scale_and_untilt_sign_invariance_used": True,
        "positive_samples": counts[POSITIVE_CODE],
        "production_ready": False,
        "q": plan.q,
        "raw_stream_bytes_consumed": raw_bytes,
        "reserved_code_rejected": True,
        "sample_count_per_character": parameters.sample_count,
        "sign_artifact_bytes": observed_size,
        "sign_artifact_sha256": sign_sha256,
        "sign_change_or_zero_count_computed": False,
        "strict_sign_codes_are_not_zero_multiplicity_claims": True,
        "source_parameters_exact": True,
        "stream_elapsed_nanoseconds": elapsed,
        "time_tail_over_positive_scale_controls_higher_precision_replayed": True,
        "transform_length": parameters.transform_length,
        "trusted_execution_or_replayable_dft_evidence_required_after_raw_discard": True,
        "zero_completeness_claimed": False,
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(receipt)
    ).hexdigest()
    encoded = canonical_json_bytes(receipt)
    if len(encoded) > MAX_RECEIPT_BYTES:
        _fail("semantic sign receipt exceeds one MiB")
    if receipt_path is not None:
        _atomic_bytes(receipt_path, encoded)
    return receipt


def _sign_metadata(raw_header: bytes, *, total_size: int) -> dict[str, Any]:
    if len(raw_header) != SIGN_HEADER.size:
        _fail("truncated TGDBSSG1 header")
    values = SIGN_HEADER.unpack(raw_header)
    (
        magic,
        version,
        q,
        bits,
        ambiguous,
        negative,
        positive,
        character_count,
        sample_count,
        payload_bytes,
        plan_sha256,
        control_sha256,
        roster_sha256,
    ) = values
    if (
        magic != SIGN_MAGIC
        or version != SIGN_FORMAT_VERSION
        or not base.SOURCE_Q_START <= q <= base.SOURCE_Q_STOP
        or bits != BITS_PER_CODE
        or (ambiguous, negative, positive)
        != (AMBIGUOUS_CODE, NEGATIVE_CODE, POSITIVE_CODE)
        or character_count <= 0
        or sample_count <= 0
        or payload_bytes != (character_count * sample_count + 3) // 4
        or total_size != SIGN_HEADER.size + payload_bytes
    ):
        _fail("invalid TGDBSSG1 header or size")
    return {
        "q": q,
        "character_count": character_count,
        "sample_count": sample_count,
        "code_count": character_count * sample_count,
        "payload_bytes": payload_bytes,
        "plan_sha256": plan_sha256.hex(),
        "control_sha256": control_sha256.hex(),
        "character_roster_sha256": roster_sha256.hex(),
    }


def inspect_sign_artifact(path: Path) -> dict[str, Any]:
    """Stream-check a TGDBSSG1 artifact and count all three admitted codes."""

    total_size = path.stat().st_size
    digest = hashlib.sha256()
    counts = [0, 0, 0]
    with path.open("rb") as source:
        header = _read_exact(source, SIGN_HEADER.size, label="TGDBSSG1 header")
        digest.update(header)
        metadata = _sign_metadata(header, total_size=total_size)
        remaining_codes = int(metadata["code_count"])
        remaining_bytes = int(metadata["payload_bytes"])
        while remaining_bytes:
            count = min(remaining_bytes, 8 * 1024 * 1024)
            raw = _read_exact(source, count, label="TGDBSSG1 payload")
            digest.update(raw)
            admitted = min(remaining_codes, 4 * len(raw))
            if _np is not None:
                packed = _np.frombuffer(raw, dtype=_np.uint8)
                codes = _np.empty(4 * len(packed), dtype=_np.uint8)
                codes[0::4] = packed & _np.uint8(3)
                codes[1::4] = (packed >> _np.uint8(2)) & _np.uint8(3)
                codes[2::4] = (packed >> _np.uint8(4)) & _np.uint8(3)
                codes[3::4] = packed >> _np.uint8(6)
                codes = codes[:admitted]
                if bool(_np.any(codes == RESERVED_CODE)):
                    _fail("TGDBSSG1 contains the reserved sign code")
                for code in range(3):
                    counts[code] += int(_np.count_nonzero(codes == code))
            else:
                observed = 0
                for value in raw:
                    for shift in (0, 2, 4, 6):
                        if observed == admitted:
                            break
                        code = (value >> shift) & 3
                        if code == RESERVED_CODE:
                            _fail("TGDBSSG1 contains the reserved sign code")
                        counts[code] += 1
                        observed += 1
            remaining_codes -= admitted
            remaining_bytes -= len(raw)
        if remaining_codes != 0 or source.read(1):
            _fail("TGDBSSG1 payload coverage or EOF differs")
    if metadata["code_count"] % 4:
        with path.open("rb") as source:
            source.seek(-1, os.SEEK_END)
            last = source.read(1)[0]
        used_bits = 2 * (int(metadata["code_count"]) % 4)
        if last >> used_bits:
            _fail("TGDBSSG1 has nonzero unused padding bits")
    return {
        **metadata,
        "sha256": digest.hexdigest(),
        "ambiguous_samples": counts[AMBIGUOUS_CODE],
        "negative_samples": counts[NEGATIVE_CODE],
        "positive_samples": counts[POSITIVE_CODE],
        "reserved_code_rejected": True,
        "multiplicity_inference_performed": False,
        "external_atom_discharged": False,
    }


def unpack_sign_codes(path: Path) -> tuple[dict[str, Any], bytes]:
    """Read a bounded TGDBSSG1 artifact for tests."""

    raw = path.read_bytes()
    if len(raw) < SIGN_HEADER.size:
        _fail("truncated TGDBSSG1 header")
    metadata = _sign_metadata(raw[: SIGN_HEADER.size], total_size=len(raw))
    code_count = int(metadata["code_count"])
    payload = raw[SIGN_HEADER.size :]
    codes = bytearray(code_count)
    for index in range(code_count):
        code = (payload[index // 4] >> (2 * (index % 4))) & 3
        if code == RESERVED_CODE:
            _fail("TGDBSSG1 contains the reserved sign code")
        codes[index] = code
    if code_count % 4:
        used_bits = 2 * (code_count % 4)
        if payload[-1] >> used_bits:
            _fail("TGDBSSG1 has nonzero unused padding bits")
    return {
        **metadata,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }, bytes(codes)


__all__ = [
    "ALGORITHM_ID",
    "AMBIGUOUS_CODE",
    "BITS_PER_CODE",
    "CONTROL_ALGORITHM_ID",
    "CONTROL_CHECKER_ID",
    "CONTROL_FORMAT_VERSION",
    "CONTROL_HEADER",
    "CONTROL_ITEM",
    "CONTROL_MAGIC",
    "CONTROL_RECEIPT_SCHEMA",
    "DEFAULT_CHUNK_ITEMS",
    "NEGATIVE_CODE",
    "POSITIVE_CODE",
    "REDUCER_RECEIPT_SCHEMA",
    "RESERVED_CODE",
    "SIGN_HEADER",
    "SIGN_MAGIC",
    "SmallQSemanticReducerError",
    "TimeTailControl",
    "canonical_json_bytes",
    "inspect_sign_artifact",
    "load_time_tail_control_metadata",
    "reduce_semantic_sign_stream",
    "unpack_sign_codes",
    "verify_time_tail_control",
    "write_time_tail_control",
]
