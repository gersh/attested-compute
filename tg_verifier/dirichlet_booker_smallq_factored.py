# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Factored certified seeds for Platt--Booker small-conductor transforms.

Version 2 of the certified CUDA boundary stored ``w``, the completed-value
prefactor, and the analytic error once for every ``(character, frequency)``.
Only the character phase in that data actually depends on the character:

``prefactor(chi, parity, u) = epsilon(chi) * parity_prefactor(parity, u)``.

This module makes that factorisation explicit.  A version-3 frame stores one
epsilon disk and exact exponent table per character, followed by one ``w``
disk and two parity records per frequency.  The producer is still untrusted;
``verify_factored_seed_frame`` independently reconstructs every character,
phase, shared transcendental, truncation, and analytic tail using Arb at a
higher precision.

The format is deliberately separate from v2.  Consuming a v3 frame requires
the factored CUDA kernel and its disk-multiplication soundness bridge; a v2
runner must fail on the changed magic rather than silently reinterpret it.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import math
import os
from pathlib import Path
import struct
import tempfile
import time
from typing import Any, Sequence

from tg_verifier import dirichlet_booker_smallq as base
from tg_verifier import dirichlet_booker_smallq_certified as v2


AUTHOR = "Gershon Bialer"
ALGORITHM_ID = "platt-booker-smallq-factored-disk-dft-v3"
CHECKER_ID = "arb-smallq-factored-seed-replay-v3"

INPUT_MAGIC = b"TGDBSCI3"
FORMAT_VERSION = 3
NONUNIT_EXPONENT = (1 << 32) - 1

INPUT_HEADER = v2.INPUT_HEADER
PARAMETER_HEADER = v2.PARAMETER_HEADER
DISK = v2.DISK

# character_id, parity, reserved words, epsilon disk
CHARACTER_HEADER = struct.Struct("<QIIQddd")
# index, signed index, followed by w and the two parity records
SHARED_PREFIX = struct.Struct("<Qq")
# truncation, reserved, parity prefactor disk, analytic radius
PARITY_SEED = struct.Struct("<IIdddd")

SHARED_FREQUENCY_SIZE = SHARED_PREFIX.size + DISK.size + 2 * PARITY_SEED.size
OUTPUT_MAGIC = b"TGDBSCO3"
OUTPUT_HEADER = v2.OUTPUT_HEADER
OUTPUT_ITEM = v2.OUTPUT_ITEM

# Split-service formats.  The plan owns the expensive shared frequency stream;
# bounded character batches contain no copy of it.  Every batch commits to the
# complete plan bytes, and the plan commits to the ordered character-id roster.
PLAN_MAGIC = b"TGDBSQP3"
BATCH_MAGIC = b"TGDBSQB3"
SERVICE_OUTPUT_MAGIC = b"TGDBSQO3"
REDUCED_SERVICE_OUTPUT_MAGIC = b"TGDBSQR3"
ROSTER_DOMAIN = b"SparkInterval/DirichletBookerSmallQ/roster/v3\x00"
PLAN_COMMITMENT = struct.Struct("<32s")
BATCH_BINDING = struct.Struct("<32sQQQQ")
SERVICE_OUTPUT_BINDING = struct.Struct("<32s32sQQQQ")

assert INPUT_HEADER.size == 64
assert PARAMETER_HEADER.size == 48
assert CHARACTER_HEADER.size == 48
assert SHARED_PREFIX.size == 16
assert PARITY_SEED.size == 40
assert SHARED_FREQUENCY_SIZE == 120
assert PLAN_COMMITMENT.size == 32
assert BATCH_BINDING.size == 64
assert SERVICE_OUTPUT_BINDING.size == 96


class FactoredSmallQError(RuntimeError):
    """A factored seed frame or its independent replay failed closed."""


def _fail(message: str) -> None:
    raise FactoredSmallQError(message)


@dataclass(frozen=True)
class ParsedParitySeed:
    truncation: int
    prefactor: tuple[float, float, float]
    analytic_radius_hi: float


@dataclass(frozen=True)
class ParsedSharedSeed:
    index: int
    signed_index: int
    w: tuple[float, float, float]
    parities: tuple[ParsedParitySeed, ParsedParitySeed]


@dataclass(frozen=True)
class ParsedCharacter:
    character_id: int
    parity: int
    epsilon: tuple[float, float, float]
    exponents: tuple[int, ...]


@dataclass(frozen=True)
class ParsedFrame:
    q: int
    group_exponent: int
    transform_length: int
    frequency_start: int
    frequency_count: int
    run_dft: bool
    target_bits: int
    eta: Fraction
    a: Fraction
    b: Fraction
    characters: tuple[ParsedCharacter, ...]
    shared_seeds: tuple[ParsedSharedSeed, ...]


@dataclass(frozen=True)
class ParsedSharedPlan:
    q: int
    group_exponent: int
    campaign_character_count: int
    transform_length: int
    frequency_start: int
    frequency_count: int
    run_dft: bool
    target_bits: int
    eta: Fraction
    a: Fraction
    b: Fraction
    character_roster_sha256: bytes
    shared_seeds: tuple[ParsedSharedSeed, ...]
    sha256: bytes


@dataclass(frozen=True)
class ParsedCharacterBatch:
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
    characters: tuple[ParsedCharacter, ...]
    sha256: bytes


def _shared_seed_values(
    *,
    q: int,
    parameters: base.TransformParameters,
    index: int,
    target_bits: int,
) -> tuple[int, Any, tuple[tuple[int, Any, Any], tuple[int, Any, Any]]]:
    """Return the character-independent and parity-only analytic values."""

    length = parameters.transform_length
    signed = index if index <= length // 2 else index - length
    x = 2 * base.arb.pi() * abs(signed) / base._arb_fraction(parameters.b)
    eta = base._arb_fraction(parameters.eta)
    u = base.acb(x, base.arb.pi() * eta / 4)
    w = (-base.arb.pi() * (2 * u).exp() / q).exp()
    parity_values: list[tuple[int, Any, Any]] = []
    for parity in (0, 1):
        truncation, gaussian_tail = base._choose_truncation(
            q=q,
            parity=parity,
            eta=parameters.eta,
            x=x,
            target_bits=target_bits,
        )
        p = base.arb(2 * parity + 1) / 2
        # epsilon(chi) is deliberately absent.  The CUDA consumer composes
        # this parity-only disk with the independently checked character disk.
        prefactor = 2 * (p * u).exp() / (base.arb(q) ** (p / 2))
        alias = base._frequency_periodization_bound(
            q=q,
            parity=parity,
            eta=parameters.eta,
            x=x,
            a=parameters.a,
        )
        parity_values.append((truncation, prefactor, gaussian_tail + alias))
    return signed, w, (parity_values[0], parity_values[1])


def _character_roster_digest(conrey_numbers: Sequence[int]) -> bytes:
    """Commit to one ordered roster with an explicit domain separator."""

    digest = hashlib.sha256()
    digest.update(ROSTER_DOMAIN)
    for number in conrey_numbers:
        if isinstance(number, bool) or not isinstance(number, int) or not 0 <= number < 1 << 64:
            _fail("character id is not an unsigned 64-bit integer")
        digest.update(struct.pack("<Q", number))
    return digest.digest()


def _pack_shared_seeds(
    *,
    q: int,
    parameters: base.TransformParameters,
    frequency_start: int,
    frequency_stop: int,
    target_bits: int,
) -> tuple[list[bytes], tuple[int, int]]:
    chunks: list[bytes] = []
    parity_truncations = [0, 0]
    for index in range(frequency_start, frequency_stop):
        encoded, truncations = _packed_shared_seed(
            q=q,
            parameters=parameters,
            index=index,
            target_bits=target_bits,
        )
        chunks.append(encoded)
        for parity in (0, 1):
            parity_truncations[parity] += truncations[parity]
    return chunks, (parity_truncations[0], parity_truncations[1])


def _packed_shared_seed(
    *, q: int, parameters: base.TransformParameters, index: int, target_bits: int
) -> tuple[bytes, tuple[int, int]]:
    signed, w, parity_values = _shared_seed_values(
        q=q,
        parameters=parameters,
        index=index,
        target_bits=target_bits,
    )
    chunks = [SHARED_PREFIX.pack(index, signed), DISK.pack(*v2._disk(w))]
    truncations = []
    for truncation, prefactor, analytic in parity_values:
        chunks.append(
            PARITY_SEED.pack(
                truncation,
                0,
                *v2._disk(prefactor),
                v2._upper(analytic),
            )
        )
        truncations.append(truncation)
    encoded = b"".join(chunks)
    assert len(encoded) == SHARED_FREQUENCY_SIZE
    return encoded, (truncations[0], truncations[1])


def _character_blocks(
    *, q: int, conrey_numbers: Sequence[int], expected_group_exponent: int
) -> tuple[list[bytes], tuple[int, int]]:
    chunks: list[bytes] = []
    parity_counts = [0, 0]
    for number in conrey_numbers:
        character = base._character(q, number)
        group_exponent = int(character.group().exponent())
        if group_exponent != expected_group_exponent:
            _fail("character batch has inconsistent unit-group exponent")
        parity = int(character.parity())
        parity_counts[parity] += 1
        chunks.append(
            CHARACTER_HEADER.pack(number, parity, 0, 0, *v2._disk(base._epsilon_phase(character)))
        )
        exponents = []
        for residue in range(q):
            exponent = character.chi_exponent(residue)
            exponents.append(NONUNIT_EXPONENT if exponent is None else int(exponent))
        chunks.append(struct.pack(f"<{q}I", *exponents))
    return chunks, (parity_counts[0], parity_counts[1])


def write_factored_seed_frame(
    path: Path,
    *,
    q: int,
    conrey_numbers: Sequence[int],
    parameters: base.TransformParameters,
    frequency_start: int = 0,
    frequency_stop: int | None = None,
    target_bits: int = base.DEFAULT_TARGET_BITS,
    precision_bits: int = base.DEFAULT_PRECISION_BITS,
    run_dft: bool = True,
) -> dict[str, object]:
    """Write an untrusted v3 producer frame with shared analytic seeds."""

    base._require_flint()
    if parameters.q != q or not conrey_numbers:
        _fail("invalid modulus or empty character batch")
    stop = parameters.transform_length if frequency_stop is None else frequency_stop
    if not 0 <= frequency_start < stop <= parameters.transform_length:
        _fail("invalid frequency range")
    if run_dft and (frequency_start != 0 or stop != parameters.transform_length):
        _fail("DFT frames must contain a complete transform")
    characters = [base._character(q, number) for number in conrey_numbers]
    group_exponent = int(characters[0].group().exponent())
    if any(int(character.group().exponent()) != group_exponent for character in characters):
        _fail("character batch has inconsistent unit-group exponent")
    chunks = [
        INPUT_HEADER.pack(
            INPUT_MAGIC,
            FORMAT_VERSION,
            q,
            group_exponent,
            len(characters),
            parameters.transform_length,
            frequency_start,
            stop - frequency_start,
            int(run_dft),
            target_bits,
            0,
        ),
        PARAMETER_HEADER.pack(
            parameters.eta.numerator,
            parameters.eta.denominator,
            parameters.a.numerator,
            parameters.a.denominator,
            parameters.b.numerator,
            parameters.b.denominator,
        ),
    ]
    parity_counts = [0, 0]
    started = time.perf_counter_ns()
    with base.ctx.workprec(precision_bits):
        for number, character in zip(conrey_numbers, characters):
            parity = int(character.parity())
            parity_counts[parity] += 1
            epsilon = v2._disk(base._epsilon_phase(character))
            chunks.append(CHARACTER_HEADER.pack(number, parity, 0, 0, *epsilon))
            exponents = []
            for residue in range(q):
                exponent = character.chi_exponent(residue)
                exponents.append(
                    NONUNIT_EXPONENT if exponent is None else int(exponent)
                )
            chunks.append(struct.pack(f"<{q}I", *exponents))
        total_terms = 0
        for index in range(frequency_start, stop):
            signed, w, parity_values = _shared_seed_values(
                q=q,
                parameters=parameters,
                index=index,
                target_bits=target_bits,
            )
            chunks.append(SHARED_PREFIX.pack(index, signed))
            chunks.append(DISK.pack(*v2._disk(w)))
            for parity, (truncation, prefactor, analytic) in enumerate(parity_values):
                chunks.append(
                    PARITY_SEED.pack(
                        truncation,
                        0,
                        *v2._disk(prefactor),
                        v2._upper(analytic),
                    )
                )
                total_terms += parity_counts[parity] * truncation
    path.parent.mkdir(parents=True, exist_ok=True)
    base._write_atomic(path, b"".join(chunks))
    elapsed = time.perf_counter_ns() - started
    digest, size = base.sha256_file(path)
    legacy_frequency_bytes = len(characters) * (stop - frequency_start) * v2.FREQUENCY_SIZE
    factored_frequency_bytes = (stop - frequency_start) * SHARED_FREQUENCY_SIZE
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.factored_seed_frame.v3",
        "algorithm": ALGORITHM_ID,
        "classification": "untrusted-producer-output-requires-independent-replay",
        "q": q,
        "batch_count": len(characters),
        "frequency_count": stop - frequency_start,
        "character_parity_counts": parity_counts,
        "shared_transcendental_frequency_records": stop - frequency_start,
        "legacy_v2_frequency_bytes_for_same_batch": legacy_frequency_bytes,
        "factored_v3_frequency_bytes": factored_frequency_bytes,
        "frequency_payload_reduction_ratio": legacy_frequency_bytes / factored_frequency_bytes,
        "finite_gaussian_terms_not_replayed_by_seed_checker": total_terms,
        "seed_generation_nanoseconds": elapsed,
        "path": str(path),
        "sha256": digest,
        "size_bytes": size,
    }


def write_factored_shared_plan(
    path: Path,
    *,
    q: int,
    conrey_numbers: Sequence[int],
    parameters: base.TransformParameters,
    frequency_start: int = 0,
    frequency_stop: int | None = None,
    target_bits: int = base.DEFAULT_TARGET_BITS,
    precision_bits: int = base.DEFAULT_PRECISION_BITS,
    run_dft: bool = True,
) -> dict[str, object]:
    """Write the q-level v3 plan exactly once for a character campaign."""

    base._require_flint()
    numbers = tuple(conrey_numbers)
    if parameters.q != q or not numbers or len(numbers) >= 1 << 32:
        _fail("invalid modulus or character campaign")
    if len(set(numbers)) != len(numbers):
        _fail("character roster contains a duplicate id")
    stop = parameters.transform_length if frequency_stop is None else frequency_stop
    if not 0 <= frequency_start < stop <= parameters.transform_length:
        _fail("invalid frequency range")
    if run_dft and (frequency_start != 0 or stop != parameters.transform_length):
        _fail("DFT plans must contain a complete transform")
    group_exponent = int(base._character(q, numbers[0]).group().exponent())
    for number in numbers[1:]:
        if int(base._character(q, number).group().exponent()) != group_exponent:
            _fail("character campaign has inconsistent unit-group exponent")
    roster_digest = _character_roster_digest(numbers)
    prefix = b"".join([
        INPUT_HEADER.pack(
            PLAN_MAGIC,
            FORMAT_VERSION,
            q,
            group_exponent,
            len(numbers),
            parameters.transform_length,
            frequency_start,
            stop - frequency_start,
            int(run_dft),
            target_bits,
            0,
        ),
        PLAN_COMMITMENT.pack(roster_digest),
        PARAMETER_HEADER.pack(
            parameters.eta.numerator,
            parameters.eta.denominator,
            parameters.a.numerator,
            parameters.a.denominator,
            parameters.b.numerator,
            parameters.b.denominator,
        ),
    ])
    started = time.perf_counter_ns()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    digest_state = hashlib.sha256()
    size = 0
    parity_truncation_sums = [0, 0]
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(prefix)
            digest_state.update(prefix)
            size += len(prefix)
            # Flush in multi-megabyte blocks.  Source q=3 has 2^29 records;
            # retaining this stream in a Python list would require far more
            # memory than either the host or the target GPU.
            buffer = bytearray()
            with base.ctx.workprec(precision_bits):
                for index in range(frequency_start, stop):
                    encoded, truncations = _packed_shared_seed(
                        q=q,
                        parameters=parameters,
                        index=index,
                        target_bits=target_bits,
                    )
                    buffer.extend(encoded)
                    parity_truncation_sums[0] += truncations[0]
                    parity_truncation_sums[1] += truncations[1]
                    if len(buffer) >= 8 * 1024 * 1024:
                        output.write(buffer)
                        digest_state.update(buffer)
                        size += len(buffer)
                        buffer.clear()
            if buffer:
                output.write(buffer)
                digest_state.update(buffer)
                size += len(buffer)
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
    digest = digest_state.hexdigest()
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.factored_shared_plan.v3",
        "algorithm": ALGORITHM_ID,
        "classification": "untrusted-plan-requires-independent-replay",
        "q": q,
        "group_exponent": group_exponent,
        "campaign_character_count": len(numbers),
        "frequency_count": stop - frequency_start,
        "character_roster_sha256": roster_digest.hex(),
        "parity_truncation_sums": list(parity_truncation_sums),
        "seed_generation_nanoseconds": elapsed,
        "path": str(path),
        "sha256": digest,
        "size_bytes": size,
    }


def write_factored_character_batch(
    path: Path,
    *,
    plan_path: Path,
    conrey_numbers: Sequence[int],
    character_start: int,
    batch_ordinal: int,
    campaign_batch_count: int,
    precision_bits: int = base.DEFAULT_PRECISION_BITS,
    _plan_metadata: ParsedSharedPlan | None = None,
) -> dict[str, object]:
    """Write one bounded character-only batch bound to an exact plan hash."""

    base._require_flint()
    plan = (
        parse_factored_shared_plan_metadata(plan_path)
        if _plan_metadata is None
        else _plan_metadata
    )
    numbers = tuple(conrey_numbers)
    if (
        not numbers
        or len(numbers) >= 1 << 32
        or character_start < 0
        or character_start + len(numbers) > plan.campaign_character_count
        or not 0 <= batch_ordinal < campaign_batch_count
    ):
        _fail("invalid factored character batch range")
    started = time.perf_counter_ns()
    chunks = [
        INPUT_HEADER.pack(
            BATCH_MAGIC,
            FORMAT_VERSION,
            plan.q,
            plan.group_exponent,
            len(numbers),
            plan.transform_length,
            plan.frequency_start,
            plan.frequency_count,
            int(plan.run_dft),
            plan.target_bits,
            0,
        ),
        BATCH_BINDING.pack(
            plan.sha256,
            character_start,
            plan.campaign_character_count,
            batch_ordinal,
            campaign_batch_count,
        ),
    ]
    with base.ctx.workprec(precision_bits):
        character_chunks, parity_counts = _character_blocks(
            q=plan.q,
            conrey_numbers=numbers,
            expected_group_exponent=plan.group_exponent,
        )
    chunks.extend(character_chunks)
    base._write_atomic(path, b"".join(chunks))
    elapsed = time.perf_counter_ns() - started
    digest, size = base.sha256_file(path)
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.factored_character_batch.v3",
        "algorithm": ALGORITHM_ID,
        "classification": "untrusted-batch-requires-independent-replay",
        "q": plan.q,
        "character_start": character_start,
        "batch_count": len(numbers),
        "batch_ordinal": batch_ordinal,
        "campaign_batch_count": campaign_batch_count,
        "plan_sha256": plan.sha256.hex(),
        "character_parity_counts": list(parity_counts),
        "character_generation_nanoseconds": elapsed,
        "path": str(path),
        "sha256": digest,
        "size_bytes": size,
    }


def factored_device_memory_bytes(
    *,
    q: int,
    transform_length: int,
    batch_count: int,
    run_dft: bool = True,
    resident_shared_seed_records: int | None = None,
) -> dict[str, int]:
    """Exact explicit CUDA allocation model for the current v3 runner.

    CUDA allocator/context overhead is intentionally excluded.  Production
    planning therefore supplies an already-safe usable byte budget rather than
    interpreting total device memory as usable memory.
    """

    if (
        not 3 <= q <= 10_000
        or transform_length < 1
        or transform_length & (transform_length - 1)
        or batch_count < 1
    ):
        _fail("invalid device-memory dimensions")
    shared_records = (
        transform_length
        if resident_shared_seed_records is None
        else resident_shared_seed_records
    )
    if not 1 <= shared_records <= transform_length:
        _fail("invalid resident shared-seed count")
    shared = shared_records * SHARED_FREQUENCY_SIZE
    values = batch_count * transform_length * DISK.size
    statuses = batch_count * transform_length * 4
    character_roots = batch_count * q * DISK.size
    character_metadata = batch_count * (24 + DISK.size)
    fft_scratch = batch_count * transform_length * DISK.size if run_dft else 0
    fft_roots = (transform_length - 1) * DISK.size if run_dft else 0
    fft_anchors = (
        ((transform_length // 2 + 255) // 256) * DISK.size if run_dft else 0
    )
    total = (
        shared
        + values
        + statuses
        + character_roots
        + character_metadata
        + fft_scratch
        + fft_roots
        + fft_anchors
    )
    return {
        "shared_frequency_seeds": shared,
        "values": values,
        "statuses": statuses,
        "character_roots": character_roots,
        "character_metadata": character_metadata,
        "fft_scratch": fft_scratch,
        "fft_roots": fft_roots,
        "fft_anchors": fft_anchors,
        "explicit_allocation_total": total,
    }


def maximum_factored_batch_characters(
    *,
    q: int,
    transform_length: int,
    usable_device_bytes: int,
    run_dft: bool = True,
    resident_shared_seed_records: int | None = None,
) -> int:
    """Largest batch whose explicit allocations fit a caller-safe budget."""

    if isinstance(usable_device_bytes, bool) or usable_device_bytes <= 0:
        _fail("usable device bytes must be positive")
    fixed = factored_device_memory_bytes(
        q=q,
        transform_length=transform_length,
        batch_count=1,
        run_dft=run_dft,
        resident_shared_seed_records=resident_shared_seed_records,
    )
    one = fixed["explicit_allocation_total"]
    two = factored_device_memory_bytes(
        q=q,
        transform_length=transform_length,
        batch_count=2,
        run_dft=run_dft,
        resident_shared_seed_records=resident_shared_seed_records,
    )["explicit_allocation_total"]
    per_character = two - one
    fixed_bytes = one - per_character
    if usable_device_bytes < fixed_bytes + per_character:
        _fail("usable device budget cannot hold one character")
    return (usable_device_bytes - fixed_bytes) // per_character


def factored_service_batch_plan(
    *,
    q: int,
    transform_length: int,
    character_count: int,
    usable_device_bytes: int,
    streaming_seed_chunk_records: int = 1 << 20,
) -> dict[str, int | bool]:
    """Choose resident seeds when possible, otherwise a bounded seed stream."""

    if character_count <= 0:
        _fail("character count must be positive")
    try:
        maximum_batch = maximum_factored_batch_characters(
            q=q,
            transform_length=transform_length,
            usable_device_bytes=usable_device_bytes,
        )
        resident_records = transform_length
        shared_resident = True
    except FactoredSmallQError:
        resident_records = min(streaming_seed_chunk_records, transform_length)
        maximum_batch = maximum_factored_batch_characters(
            q=q,
            transform_length=transform_length,
            usable_device_bytes=usable_device_bytes,
            resident_shared_seed_records=resident_records,
        )
        shared_resident = False
    actual_batch = min(maximum_batch, character_count)
    batch_count = (character_count + maximum_batch - 1) // maximum_batch
    memory = factored_device_memory_bytes(
        q=q,
        transform_length=transform_length,
        batch_count=actual_batch,
        resident_shared_seed_records=resident_records,
    )
    return {
        "shared_seeds_resident": shared_resident,
        "resident_shared_seed_records": resident_records,
        "maximum_batch_characters": maximum_batch,
        "campaign_batch_count": batch_count,
        "explicit_device_bytes": memory["explicit_allocation_total"],
    }


def write_factored_service_campaign(
    plan_path: Path,
    batch_directory: Path,
    *,
    q: int,
    conrey_numbers: Sequence[int],
    parameters: base.TransformParameters,
    maximum_batch_characters: int,
    target_bits: int = base.DEFAULT_TARGET_BITS,
    precision_bits: int = base.DEFAULT_PRECISION_BITS,
) -> dict[str, object]:
    """Write one plan and a complete, contiguous set of bounded batches."""

    numbers = tuple(conrey_numbers)
    if maximum_batch_characters <= 0:
        _fail("maximum batch size must be positive")
    plan_record = write_factored_shared_plan(
        plan_path,
        q=q,
        conrey_numbers=numbers,
        parameters=parameters,
        target_bits=target_bits,
        precision_bits=precision_bits,
    )
    plan_metadata = ParsedSharedPlan(
        q=q,
        group_exponent=int(plan_record["group_exponent"]),
        campaign_character_count=len(numbers),
        transform_length=parameters.transform_length,
        frequency_start=0,
        frequency_count=parameters.transform_length,
        run_dft=True,
        target_bits=target_bits,
        eta=parameters.eta,
        a=parameters.a,
        b=parameters.b,
        character_roster_sha256=bytes.fromhex(
            str(plan_record["character_roster_sha256"])
        ),
        shared_seeds=(),
        sha256=bytes.fromhex(str(plan_record["sha256"])),
    )
    batch_count = (len(numbers) + maximum_batch_characters - 1) // maximum_batch_characters
    batch_directory.mkdir(parents=True, exist_ok=True)
    batches = []
    for ordinal in range(batch_count):
        start = ordinal * maximum_batch_characters
        stop = min(start + maximum_batch_characters, len(numbers))
        batch_path = batch_directory / f"batch-{ordinal:08d}.bin"
        batches.append(
            write_factored_character_batch(
                batch_path,
                plan_path=plan_path,
                conrey_numbers=numbers[start:stop],
                character_start=start,
                batch_ordinal=ordinal,
                campaign_batch_count=batch_count,
                precision_bits=precision_bits,
                _plan_metadata=plan_metadata,
            )
        )
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.factored_service_campaign.v3",
        "algorithm": ALGORITHM_ID,
        "q": q,
        "plan": plan_record,
        "batches": batches,
        "campaign_batch_count": batch_count,
        "maximum_batch_characters": maximum_batch_characters,
        "physical_payload_bytes": int(plan_record["size_bytes"])
        + sum(int(batch["size_bytes"]) for batch in batches),
        "shared_seed_stream_copies": 1,
    }


def _valid_disk(value: tuple[float, float, float]) -> bool:
    return all(math.isfinite(item) for item in value) and value[2] >= 0


def _validated_split_header(
    raw: bytes, *, expected_magic: bytes, label: str
) -> tuple[int, int, int, int, int, int, bool, int]:
    if len(raw) < INPUT_HEADER.size:
        _fail(f"truncated {label} header")
    (
        magic,
        version,
        q,
        group_exponent,
        batch_count,
        transform_length,
        frequency_start,
        frequency_count,
        run_dft,
        target_bits,
        reserved,
    ) = INPUT_HEADER.unpack_from(raw)
    if (
        magic != expected_magic
        or version != FORMAT_VERSION
        or not 3 <= q <= 10_000
        or group_exponent <= 0
        or batch_count <= 0
        or transform_length <= 0
        or transform_length & (transform_length - 1)
        or frequency_count <= 0
        or frequency_start + frequency_count > transform_length
        or run_dft not in (0, 1)
        or (
            run_dft
            and (
                transform_length < 2
                or frequency_start != 0
                or frequency_count != transform_length
            )
        )
        or not 32 <= target_bits <= 1024
        or reserved
    ):
        _fail(f"invalid {label} header")
    return (
        q,
        group_exponent,
        batch_count,
        transform_length,
        frequency_start,
        frequency_count,
        bool(run_dft),
        target_bits,
    )


def _parse_exact_parameters(raw: bytes, offset: int) -> tuple[Fraction, Fraction, Fraction, int]:
    if offset + PARAMETER_HEADER.size > len(raw):
        _fail("truncated exact transform parameters")
    values = PARAMETER_HEADER.unpack_from(raw, offset)
    eta_numerator, eta_denominator, a_numerator, a_denominator, b_numerator, b_denominator = values
    try:
        eta = Fraction(eta_numerator, eta_denominator)
        a = Fraction(a_numerator, a_denominator)
        b = Fraction(b_numerator, b_denominator)
    except ZeroDivisionError as error:
        raise FactoredSmallQError("zero exact parameter denominator") from error
    if (
        abs(eta) >= 1
        or a <= 0
        or b <= 0
        or (eta.numerator, eta.denominator) != (eta_numerator, eta_denominator)
        or (a.numerator, a.denominator) != (a_numerator, a_denominator)
        or (b.numerator, b.denominator) != (b_numerator, b_denominator)
    ):
        _fail("noncanonical exact transform parameters")
    return eta, a, b, offset + PARAMETER_HEADER.size


def _parse_shared_seed_records(
    raw: bytes,
    *,
    offset: int,
    frequency_start: int,
    frequency_count: int,
    transform_length: int,
) -> tuple[tuple[ParsedSharedSeed, ...], int]:
    shared: list[ParsedSharedSeed] = []
    for local in range(frequency_count):
        if offset + SHARED_FREQUENCY_SIZE > len(raw):
            _fail("truncated shared frequency seed")
        index, signed = SHARED_PREFIX.unpack_from(raw, offset)
        offset += SHARED_PREFIX.size
        w = DISK.unpack_from(raw, offset)
        offset += DISK.size
        parities: list[ParsedParitySeed] = []
        for _parity in (0, 1):
            truncation, item_reserved, re, im, radius, analytic = PARITY_SEED.unpack_from(raw, offset)
            offset += PARITY_SEED.size
            prefactor = (re, im, radius)
            if (
                truncation > 100_000_000
                or item_reserved
                or not _valid_disk(prefactor)
                or not math.isfinite(analytic)
                or analytic < 0
            ):
                _fail("invalid parity seed")
            parities.append(ParsedParitySeed(truncation, prefactor, analytic))
        expected = frequency_start + local
        expected_signed = expected if expected <= transform_length // 2 else expected - transform_length
        if index != expected or signed != expected_signed or not _valid_disk(w):
            _fail("invalid shared frequency identity or disk")
        shared.append(ParsedSharedSeed(index, signed, w, (parities[0], parities[1])))
    return tuple(shared), offset


def parse_factored_shared_plan(path: Path) -> ParsedSharedPlan:
    """Parse a split q plan and compute the exact bytes to which batches bind."""

    raw = path.read_bytes()
    (
        q,
        group_exponent,
        campaign_character_count,
        transform_length,
        frequency_start,
        frequency_count,
        run_dft,
        target_bits,
    ) = _validated_split_header(raw, expected_magic=PLAN_MAGIC, label="factored plan")
    offset = INPUT_HEADER.size
    if offset + PLAN_COMMITMENT.size > len(raw):
        _fail("truncated factored plan commitment")
    (roster_digest,) = PLAN_COMMITMENT.unpack_from(raw, offset)
    offset += PLAN_COMMITMENT.size
    eta, a, b, offset = _parse_exact_parameters(raw, offset)
    shared, offset = _parse_shared_seed_records(
        raw,
        offset=offset,
        frequency_start=frequency_start,
        frequency_count=frequency_count,
        transform_length=transform_length,
    )
    if offset != len(raw):
        _fail("trailing bytes in factored shared plan")
    return ParsedSharedPlan(
        q=q,
        group_exponent=group_exponent,
        campaign_character_count=campaign_character_count,
        transform_length=transform_length,
        frequency_start=frequency_start,
        frequency_count=frequency_count,
        run_dft=run_dft,
        target_bits=target_bits,
        eta=eta,
        a=a,
        b=b,
        character_roster_sha256=roster_digest,
        shared_seeds=shared,
        sha256=hashlib.sha256(raw).digest(),
    )


def parse_factored_shared_plan_metadata(path: Path) -> ParsedSharedPlan:
    """Parse a source-scale plan without materializing its seed stream."""

    prefix_size = INPUT_HEADER.size + PLAN_COMMITMENT.size + PARAMETER_HEADER.size
    with path.open("rb") as source:
        raw = source.read(prefix_size)
    (
        q,
        group_exponent,
        campaign_character_count,
        transform_length,
        frequency_start,
        frequency_count,
        run_dft,
        target_bits,
    ) = _validated_split_header(raw, expected_magic=PLAN_MAGIC, label="factored plan")
    if len(raw) != prefix_size:
        _fail("truncated factored plan prefix")
    offset = INPUT_HEADER.size
    (roster_digest,) = PLAN_COMMITMENT.unpack_from(raw, offset)
    offset += PLAN_COMMITMENT.size
    eta, a, b, offset = _parse_exact_parameters(raw, offset)
    expected_size = prefix_size + frequency_count * SHARED_FREQUENCY_SIZE
    if path.stat().st_size != expected_size:
        _fail("factored plan size does not match its frequency count")
    digest_hex, size = base.sha256_file(path)
    if size != expected_size:
        _fail("factored plan changed while hashing metadata")
    return ParsedSharedPlan(
        q=q,
        group_exponent=group_exponent,
        campaign_character_count=campaign_character_count,
        transform_length=transform_length,
        frequency_start=frequency_start,
        frequency_count=frequency_count,
        run_dft=run_dft,
        target_bits=target_bits,
        eta=eta,
        a=a,
        b=b,
        character_roster_sha256=roster_digest,
        shared_seeds=(),
        sha256=bytes.fromhex(digest_hex),
    )


def _iter_factored_shared_plan_seeds(
    path: Path, plan: ParsedSharedPlan, *, chunk_records: int = 1 << 16
):
    """Stream parsed seed records and recheck the complete plan digest."""

    if chunk_records <= 0:
        _fail("shared-plan parser chunk must be positive")
    prefix_size = INPUT_HEADER.size + PLAN_COMMITMENT.size + PARAMETER_HEADER.size
    digest = hashlib.sha256()
    with path.open("rb") as source:
        prefix = source.read(prefix_size)
        if len(prefix) != prefix_size:
            _fail("truncated factored plan during streaming replay")
        digest.update(prefix)
        completed = 0
        while completed < plan.frequency_count:
            count = min(chunk_records, plan.frequency_count - completed)
            raw = source.read(count * SHARED_FREQUENCY_SIZE)
            if len(raw) != count * SHARED_FREQUENCY_SIZE:
                _fail("truncated factored plan seed stream")
            digest.update(raw)
            parsed, offset = _parse_shared_seed_records(
                raw,
                offset=0,
                frequency_start=plan.frequency_start + completed,
                frequency_count=count,
                transform_length=plan.transform_length,
            )
            if offset != len(raw):
                _fail("internal shared-plan chunk parse mismatch")
            yield from parsed
            completed += count
        if source.read(1):
            _fail("factored shared plan grew during streaming replay")
    if digest.digest() != plan.sha256:
        _fail("factored shared plan changed during streaming replay")


def parse_factored_character_batch(
    path: Path, *, plan: ParsedSharedPlan
) -> ParsedCharacterBatch:
    """Parse one character-only batch and reject every plan mismatch."""

    raw = path.read_bytes()
    (
        q,
        group_exponent,
        batch_count,
        transform_length,
        frequency_start,
        frequency_count,
        run_dft,
        target_bits,
    ) = _validated_split_header(raw, expected_magic=BATCH_MAGIC, label="factored batch")
    offset = INPUT_HEADER.size
    if offset + BATCH_BINDING.size > len(raw):
        _fail("truncated factored batch binding")
    (
        plan_sha256,
        character_start,
        campaign_character_count,
        batch_ordinal,
        campaign_batch_count,
    ) = BATCH_BINDING.unpack_from(raw, offset)
    offset += BATCH_BINDING.size
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
        _fail("factored batch does not match its shared plan")
    characters: list[ParsedCharacter] = []
    for _ in range(batch_count):
        if offset + CHARACTER_HEADER.size > len(raw):
            _fail("truncated factored batch character header")
        character_id, parity, reserved0, reserved1, epsilon_re, epsilon_im, epsilon_radius = CHARACTER_HEADER.unpack_from(raw, offset)
        offset += CHARACTER_HEADER.size
        epsilon = (epsilon_re, epsilon_im, epsilon_radius)
        if parity not in (0, 1) or reserved0 or reserved1 or not _valid_disk(epsilon):
            _fail("invalid factored batch character header")
        exponent_size = q * 4
        if offset + exponent_size > len(raw):
            _fail("truncated factored batch character table")
        exponents = struct.unpack_from(f"<{q}I", raw, offset)
        offset += exponent_size
        if any(value != NONUNIT_EXPONENT and value >= group_exponent for value in exponents):
            _fail("batch character exponent outside group exponent")
        characters.append(ParsedCharacter(character_id, parity, epsilon, exponents))
    if offset != len(raw):
        _fail("trailing bytes in factored character batch")
    return ParsedCharacterBatch(
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
        sha256=hashlib.sha256(raw).digest(),
    )


def parse_factored_seed_frame(path: Path) -> ParsedFrame:
    raw = path.read_bytes()
    if len(raw) < INPUT_HEADER.size + PARAMETER_HEADER.size:
        _fail("truncated factored seed frame")
    (
        magic,
        version,
        q,
        group_exponent,
        batch_count,
        transform_length,
        frequency_start,
        frequency_count,
        run_dft,
        target_bits,
        reserved,
    ) = INPUT_HEADER.unpack_from(raw)
    if (
        magic != INPUT_MAGIC
        or version != FORMAT_VERSION
        or not 3 <= q <= 10_000
        or group_exponent <= 0
        or batch_count <= 0
        or transform_length <= 0
        or transform_length & (transform_length - 1)
        or frequency_count <= 0
        or frequency_start + frequency_count > transform_length
        or run_dft not in (0, 1)
        or (
            run_dft
            and (
                transform_length < 2
                or frequency_start != 0
                or frequency_count != transform_length
            )
        )
        or not 32 <= target_bits <= 1024
        or reserved
    ):
        _fail("invalid factored seed-frame header")
    parameter_values = PARAMETER_HEADER.unpack_from(raw, INPUT_HEADER.size)
    eta_numerator, eta_denominator, a_numerator, a_denominator, b_numerator, b_denominator = parameter_values
    try:
        eta = Fraction(eta_numerator, eta_denominator)
        a = Fraction(a_numerator, a_denominator)
        b = Fraction(b_numerator, b_denominator)
    except ZeroDivisionError as error:
        raise FactoredSmallQError("zero exact parameter denominator") from error
    if (
        abs(eta) >= 1
        or a <= 0
        or b <= 0
        or (eta.numerator, eta.denominator) != (eta_numerator, eta_denominator)
        or (a.numerator, a.denominator) != (a_numerator, a_denominator)
        or (b.numerator, b.denominator) != (b_numerator, b_denominator)
    ):
        _fail("noncanonical exact transform parameters")
    offset = INPUT_HEADER.size + PARAMETER_HEADER.size
    characters: list[ParsedCharacter] = []
    for _ in range(batch_count):
        if offset + CHARACTER_HEADER.size > len(raw):
            _fail("truncated factored character header")
        character_id, parity, reserved0, reserved1, epsilon_re, epsilon_im, epsilon_radius = CHARACTER_HEADER.unpack_from(raw, offset)
        offset += CHARACTER_HEADER.size
        epsilon = (epsilon_re, epsilon_im, epsilon_radius)
        if parity not in (0, 1) or reserved0 or reserved1 or not _valid_disk(epsilon):
            _fail("invalid factored character header")
        exponent_size = q * 4
        if offset + exponent_size > len(raw):
            _fail("truncated factored character table")
        exponents = struct.unpack_from(f"<{q}I", raw, offset)
        offset += exponent_size
        if any(value != NONUNIT_EXPONENT and value >= group_exponent for value in exponents):
            _fail("character exponent outside group exponent")
        characters.append(ParsedCharacter(character_id, parity, epsilon, exponents))
    shared: list[ParsedSharedSeed] = []
    for local in range(frequency_count):
        if offset + SHARED_FREQUENCY_SIZE > len(raw):
            _fail("truncated shared frequency seed")
        index, signed = SHARED_PREFIX.unpack_from(raw, offset)
        offset += SHARED_PREFIX.size
        w = DISK.unpack_from(raw, offset)
        offset += DISK.size
        parities: list[ParsedParitySeed] = []
        for _parity in (0, 1):
            truncation, item_reserved, re, im, radius, analytic = PARITY_SEED.unpack_from(raw, offset)
            offset += PARITY_SEED.size
            prefactor = (re, im, radius)
            if (
                truncation > 100_000_000
                or item_reserved
                or not _valid_disk(prefactor)
                or not math.isfinite(analytic)
                or analytic < 0
            ):
                _fail("invalid parity seed")
            parities.append(ParsedParitySeed(truncation, prefactor, analytic))
        expected = frequency_start + local
        expected_signed = expected if expected <= transform_length // 2 else expected - transform_length
        if index != expected or signed != expected_signed or not _valid_disk(w):
            _fail("invalid shared frequency identity or disk")
        shared.append(ParsedSharedSeed(index, signed, w, (parities[0], parities[1])))
    if offset != len(raw):
        _fail("trailing bytes in factored seed frame")
    return ParsedFrame(
        q=q,
        group_exponent=group_exponent,
        transform_length=transform_length,
        frequency_start=frequency_start,
        frequency_count=frequency_count,
        run_dft=bool(run_dft),
        target_bits=target_bits,
        eta=eta,
        a=a,
        b=b,
        characters=tuple(characters),
        shared_seeds=tuple(shared),
    )


def verify_factored_seed_frame(
    path: Path,
    *,
    parameters: base.TransformParameters,
    guard_bits: int = 64,
) -> dict[str, object]:
    """Replay every distinct transcendental rather than every repetition."""

    base._require_flint()
    frame = parse_factored_seed_frame(path)
    if (
        parameters.q != frame.q
        or parameters.transform_length != frame.transform_length
        or parameters.eta != frame.eta
        or parameters.a != frame.a
        or parameters.b != frame.b
    ):
        _fail("checker parameters do not match factored frame")
    if guard_bits < 32:
        _fail("seed replay guard must be at least 32 bits")
    started = time.perf_counter_ns()
    parity_counts = [0, 0]
    with base.ctx.workprec(base.DEFAULT_PRECISION_BITS + guard_bits):
        for stored in frame.characters:
            character = base._character(frame.q, stored.character_id)
            if (
                int(character.parity()) != stored.parity
                or int(character.group().exponent()) != frame.group_exponent
            ):
                _fail("stored character identity mismatch")
            parity_counts[stored.parity] += 1
            epsilon = base._epsilon_phase(character)
            if not v2._disk_contains(stored.epsilon, epsilon):
                _fail("epsilon disk misses higher-precision replay")
            for residue, encoded in enumerate(stored.exponents):
                fresh = character.chi_exponent(residue)
                expected = NONUNIT_EXPONENT if fresh is None else int(fresh)
                if encoded != expected:
                    _fail("stored character table mismatch")
        avoided_terms = 0
        for stored in frame.shared_seeds:
            signed, w, parity_values = _shared_seed_values(
                q=frame.q,
                parameters=parameters,
                index=stored.index,
                target_bits=frame.target_bits,
            )
            if signed != stored.signed_index or not v2._disk_contains(stored.w, w):
                _fail(f"shared w replay mismatch at {stored.index}")
            for parity, (truncation, prefactor, analytic) in enumerate(parity_values):
                encoded = stored.parities[parity]
                if encoded.truncation != truncation:
                    _fail(f"parity truncation mismatch at {stored.index}")
                if not v2._disk_contains(encoded.prefactor, prefactor):
                    _fail(f"parity prefactor replay mismatch at {stored.index}")
                if not analytic <= base.arb(encoded.analytic_radius_hi):
                    _fail(f"parity analytic tail understated at {stored.index}")
                avoided_terms += parity_counts[parity] * truncation
    elapsed = time.perf_counter_ns() - started
    distinct = len(frame.characters) + 3 * len(frame.shared_seeds)
    legacy = len(frame.characters) * len(frame.shared_seeds)
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.factored_seed_replay.v3",
        "checker": CHECKER_ID,
        "q": frame.q,
        "characters": len(frame.characters),
        "character_epsilons_replayed": len(frame.characters),
        "shared_frequency_records_replayed": len(frame.shared_seeds),
        "distinct_transcendental_families_replayed": distinct,
        "legacy_character_frequency_seed_count": legacy,
        "finite_gaussian_terms_avoided": avoided_terms,
        "elapsed_nanoseconds": elapsed,
        "distinct_values_per_second": distinct * 1_000_000_000 / max(elapsed, 1),
        "factored_prefactor_composition_requires_sound_disk_mul": True,
        "term_by_term_arb_replay_required": False,
        "passed": True,
    }


def verify_factored_service_campaign(
    plan_path: Path,
    batch_paths: Sequence[Path],
    *,
    parameters: base.TransformParameters,
    expected_conrey_numbers: Sequence[int] | None = None,
    guard_bits: int = 64,
) -> dict[str, object]:
    """Independently replay one complete split campaign, shared values once."""

    base._require_flint()
    plan = parse_factored_shared_plan_metadata(plan_path)
    if (
        parameters.q != plan.q
        or parameters.transform_length != plan.transform_length
        or parameters.eta != plan.eta
        or parameters.a != plan.a
        or parameters.b != plan.b
    ):
        _fail("checker parameters do not match factored shared plan")
    if guard_bits < 32 or not batch_paths:
        _fail("invalid service checker guard or empty batch list")
    roster: list[int] = []
    next_start = 0
    parity_counts = [0, 0]
    promised_batch_count: int | None = None
    started = time.perf_counter_ns()
    with base.ctx.workprec(base.DEFAULT_PRECISION_BITS + guard_bits):
        for ordinal, batch_path in enumerate(batch_paths):
            batch = parse_factored_character_batch(batch_path, plan=plan)
            if promised_batch_count is None:
                promised_batch_count = batch.campaign_batch_count
            if (
                batch.batch_ordinal != ordinal
                or batch.campaign_batch_count != promised_batch_count
                or batch.character_start != next_start
            ):
                _fail("factored service batches are not a contiguous ordered partition")
            for stored in batch.characters:
                character = base._character(plan.q, stored.character_id)
                if (
                    int(character.parity()) != stored.parity
                    or int(character.group().exponent()) != plan.group_exponent
                ):
                    _fail("stored service character identity mismatch")
                parity_counts[stored.parity] += 1
                roster.append(stored.character_id)
                epsilon = base._epsilon_phase(character)
                if not v2._disk_contains(stored.epsilon, epsilon):
                    _fail("service epsilon disk misses higher-precision replay")
                for residue, encoded in enumerate(stored.exponents):
                    fresh = character.chi_exponent(residue)
                    expected = NONUNIT_EXPONENT if fresh is None else int(fresh)
                    if encoded != expected:
                        _fail("stored service character table mismatch")
            next_start += len(batch.characters)
        if promised_batch_count is None or len(batch_paths) != promised_batch_count:
            _fail("factored service batch count is incomplete")
        if next_start != plan.campaign_character_count:
            _fail("factored service character coverage is incomplete")
        if len(set(roster)) != len(roster):
            _fail("factored service character roster contains duplicates")
        if _character_roster_digest(roster) != plan.character_roster_sha256:
            _fail("factored service character roster commitment mismatch")
        if expected_conrey_numbers is not None and tuple(roster) != tuple(expected_conrey_numbers):
            _fail("factored service roster differs from the caller's expected roster")
        total_terms = 0
        for stored in _iter_factored_shared_plan_seeds(plan_path, plan):
            signed, w, parity_values = _shared_seed_values(
                q=plan.q,
                parameters=parameters,
                index=stored.index,
                target_bits=plan.target_bits,
            )
            if signed != stored.signed_index or not v2._disk_contains(stored.w, w):
                _fail(f"service shared w replay mismatch at {stored.index}")
            for parity, (truncation, prefactor, analytic) in enumerate(parity_values):
                encoded = stored.parities[parity]
                if encoded.truncation != truncation:
                    _fail(f"service parity truncation mismatch at {stored.index}")
                if not v2._disk_contains(encoded.prefactor, prefactor):
                    _fail(f"service parity prefactor replay mismatch at {stored.index}")
                if not analytic <= base.arb(encoded.analytic_radius_hi):
                    _fail(f"service parity analytic tail understated at {stored.index}")
                total_terms += parity_counts[parity] * truncation
    elapsed = time.perf_counter_ns() - started
    distinct = len(roster) + 3 * plan.frequency_count
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.factored_service_replay.v3",
        "checker": CHECKER_ID,
        "q": plan.q,
        "characters": len(roster),
        "batches": len(batch_paths),
        "shared_frequency_records_replayed_once": plan.frequency_count,
        "distinct_transcendental_families_replayed": distinct,
        "finite_gaussian_terms_not_replayed": total_terms,
        "plan_sha256": plan.sha256.hex(),
        "character_roster_sha256": plan.character_roster_sha256.hex(),
        "elapsed_nanoseconds": elapsed,
        "distinct_values_per_second": distinct * 1_000_000_000 / max(elapsed, 1),
        "complete_contiguous_character_partition": True,
        "passed": True,
    }


def _service_frame(plan: ParsedSharedPlan, batch: ParsedCharacterBatch) -> ParsedFrame:
    return ParsedFrame(
        q=plan.q,
        group_exponent=plan.group_exponent,
        transform_length=plan.transform_length,
        frequency_start=plan.frequency_start,
        frequency_count=plan.frequency_count,
        run_dft=plan.run_dft,
        target_bits=plan.target_bits,
        eta=plan.eta,
        a=plan.a,
        b=plan.b,
        characters=batch.characters,
        shared_seeds=plan.shared_seeds,
    )


def _read_factored_output(
    path: Path, frame: ParsedFrame
) -> tuple[dict[str, int], list[tuple[int, int, tuple[float, float, float]]]]:
    raw = path.read_bytes()
    if len(raw) < OUTPUT_HEADER.size:
        _fail("truncated factored CUDA output")
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
    ) = OUTPUT_HEADER.unpack_from(raw)
    count = batch_count * frequency_count
    if (
        magic != OUTPUT_MAGIC
        or version != FORMAT_VERSION
        or q != frame.q
        or batch_count != len(frame.characters)
        or run_dft != int(frame.run_dft)
        or frequency_start != frame.frequency_start
        or frequency_count != frame.frequency_count
        or status_or
        or reserved
        or len(raw) != OUTPUT_HEADER.size + count * OUTPUT_ITEM.size
    ):
        _fail("factored CUDA output header/size mismatch")
    items: list[tuple[int, int, tuple[float, float, float]]] = []
    offset = OUTPUT_HEADER.size
    for character in frame.characters:
        for local in range(frame.frequency_count):
            character_id, index, re, im, radius, status, item_reserved = OUTPUT_ITEM.unpack_from(raw, offset)
            offset += OUTPUT_ITEM.size
            if (
                character_id != character.character_id
                or index != frame.frequency_start + local
                or status
                or item_reserved
                or not _valid_disk((re, im, radius))
            ):
                _fail("malformed factored CUDA output item")
            items.append((character_id, index, (re, im, radius)))
    return {
        "terms": terms,
        "butterflies": butterflies,
        "elapsed_nanoseconds": elapsed,
    }, items


def _read_factored_service_output(
    path: Path,
    frame: ParsedFrame,
    plan: ParsedSharedPlan,
    batch: ParsedCharacterBatch,
) -> tuple[dict[str, int], list[tuple[int, int, tuple[float, float, float]]]]:
    raw = path.read_bytes()
    minimum = OUTPUT_HEADER.size + SERVICE_OUTPUT_BINDING.size
    if len(raw) < minimum:
        _fail("truncated factored service CUDA output")
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
    ) = OUTPUT_HEADER.unpack_from(raw)
    binding = SERVICE_OUTPUT_BINDING.unpack_from(raw, OUTPUT_HEADER.size)
    expected_binding = (
        plan.sha256,
        batch.sha256,
        batch.character_start,
        batch.campaign_character_count,
        batch.batch_ordinal,
        batch.campaign_batch_count,
    )
    count = batch_count * frequency_count
    if (
        magic != SERVICE_OUTPUT_MAGIC
        or version != FORMAT_VERSION
        or q != frame.q
        or batch_count != len(frame.characters)
        or run_dft != int(frame.run_dft)
        or frequency_start != frame.frequency_start
        or frequency_count != frame.frequency_count
        or binding != expected_binding
        or status_or
        or reserved
        or len(raw) != minimum + count * OUTPUT_ITEM.size
    ):
        _fail("factored service CUDA output identity/size mismatch")
    items: list[tuple[int, int, tuple[float, float, float]]] = []
    offset = minimum
    for character in frame.characters:
        for local in range(frame.frequency_count):
            character_id, index, re, im, radius, status, item_reserved = OUTPUT_ITEM.unpack_from(raw, offset)
            offset += OUTPUT_ITEM.size
            if (
                character_id != character.character_id
                or index != frame.frequency_start + local
                or status
                or item_reserved
                or not _valid_disk((re, im, radius))
            ):
                _fail("malformed factored service CUDA output item")
            items.append((character_id, index, (re, im, radius)))
    return {
        "terms": terms,
        "butterflies": butterflies,
        "elapsed_nanoseconds": elapsed,
    }, items


def verify_factored_output_kat(
    input_path: Path,
    output_path: Path,
    *,
    parameters: base.TransformParameters,
    precision_bits: int = 224,
) -> dict[str, object]:
    """Bounded independent Arb replay of the expanded v3 CUDA result."""

    base._require_flint()
    frame = parse_factored_seed_frame(input_path)
    metadata, items = _read_factored_output(output_path, frame)
    if (
        parameters.q != frame.q
        or parameters.transform_length != frame.transform_length
        or parameters.eta != frame.eta
        or parameters.a != frame.a
        or parameters.b != frame.b
    ):
        _fail("factored KAT parameter mismatch")
    checked = 0
    item_offset = 0
    with base.ctx.workprec(precision_bits):
        for stored_character in frame.characters:
            character = base._character(frame.q, stored_character.character_id)
            epsilon = base._epsilon_phase(character)
            fresh = []
            for shared in frame.shared_seeds:
                parity_seed = shared.parities[stored_character.parity]
                fresh.append(
                    base.evaluate_frequency(
                        q=frame.q,
                        conrey_number=stored_character.character_id,
                        parameters=parameters,
                        frequency_index=shared.index,
                        target_bits=frame.target_bits,
                        truncation=parity_seed.truncation,
                        _character_object=character,
                        _epsilon=epsilon,
                    )["enclosure"]
                )
            if frame.run_dft:
                fresh = base._positive_dft(fresh)
            for value in fresh:
                if not v2._disk_contains(items[item_offset][2], value):
                    _fail(f"factored CUDA disk misses Arb KAT item {item_offset}")
                item_offset += 1
                checked += 1
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.factored_cuda_kat.v3",
        "algorithm": ALGORITHM_ID,
        "independent_arb_values_checked": checked,
        "finite_gaussian_terms": metadata["terms"],
        "radix2_butterflies": metadata["butterflies"],
        "cuda_elapsed_nanoseconds": metadata["elapsed_nanoseconds"],
        "passed": True,
        "source_scale_kat_required": False,
    }


def verify_factored_service_output_kat(
    plan_path: Path,
    batch_path: Path,
    output_path: Path,
    *,
    parameters: base.TransformParameters,
    precision_bits: int = 224,
) -> dict[str, object]:
    """Bounded Arb replay for one output of the q-persistent service."""

    plan = parse_factored_shared_plan(plan_path)
    batch = parse_factored_character_batch(batch_path, plan=plan)
    frame = _service_frame(plan, batch)
    metadata, items = _read_factored_service_output(
        output_path, frame, plan, batch
    )
    if (
        parameters.q != plan.q
        or parameters.transform_length != plan.transform_length
        or parameters.eta != plan.eta
        or parameters.a != plan.a
        or parameters.b != plan.b
    ):
        _fail("factored service KAT parameter mismatch")
    checked = 0
    item_offset = 0
    with base.ctx.workprec(precision_bits):
        for stored_character in batch.characters:
            character = base._character(plan.q, stored_character.character_id)
            epsilon = base._epsilon_phase(character)
            fresh = []
            for shared in plan.shared_seeds:
                parity_seed = shared.parities[stored_character.parity]
                fresh.append(
                    base.evaluate_frequency(
                        q=plan.q,
                        conrey_number=stored_character.character_id,
                        parameters=parameters,
                        frequency_index=shared.index,
                        target_bits=plan.target_bits,
                        truncation=parity_seed.truncation,
                        _character_object=character,
                        _epsilon=epsilon,
                    )["enclosure"]
                )
            if plan.run_dft:
                fresh = base._positive_dft(fresh)
            for value in fresh:
                if not v2._disk_contains(items[item_offset][2], value):
                    _fail(f"factored service CUDA disk misses Arb KAT item {item_offset}")
                item_offset += 1
                checked += 1
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.factored_service_cuda_kat.v3",
        "algorithm": ALGORITHM_ID,
        "plan_sha256": plan.sha256.hex(),
        "batch_ordinal": batch.batch_ordinal,
        "independent_arb_values_checked": checked,
        "finite_gaussian_terms": metadata["terms"],
        "radix2_butterflies": metadata["butterflies"],
        "cuda_elapsed_nanoseconds": metadata["elapsed_nanoseconds"],
        "passed": True,
    }


def source_work(*, usable_device_bytes: int = 80 * 1024**3) -> dict[str, object]:
    """Return exact v2/v3 cardinalities and split-service batch accounting."""

    # Local import avoids a module-initialization cycle: the semantic reducer
    # consumes the v3 structs defined here, while this accounting function only
    # needs its final wire sizes after both modules are initialized.
    from tg_verifier.dirichlet_booker_smallq_semantic_reducer import (
        CONTROL_HEADER as SEMANTIC_CONTROL_HEADER,
        CONTROL_ITEM as SEMANTIC_CONTROL_ITEM,
        SIGN_HEADER as SEMANTIC_SIGN_HEADER,
    )

    plan = base.source_campaign_plan(include_moduli=True)
    moduli = plan["moduli"]
    shared_frequency_records = sum(
        int(row["parameters"]["transform_length"]) for row in moduli
    )
    character_exponent_words = sum(
        int(row["q"]) * int(row["primitive_characters"]) for row in moduli
    )
    characters = int(plan["total_primitive_characters"])
    legacy_seeds = int(plan["total_frequency_values"])
    source_lattice_values = int(plan["total_5_over_64_lattice_values"])
    guard_frequency_values = legacy_seeds - source_lattice_values
    legacy_seed_bytes = legacy_seeds * v2.FREQUENCY_SIZE
    factored_shared_bytes = shared_frequency_records * SHARED_FREQUENCY_SIZE
    factored_character_bytes = characters * CHARACTER_HEADER.size
    exponent_bytes = character_exponent_words * 4
    # One header pair per active modulus.  This is the minimum logical payload
    # for a q-persistent service; bounded character batches may add headers but
    # must not repeat the shared frequency stream.
    active_moduli = sum(1 for row in moduli if int(row["primitive_characters"]) > 0)
    semantic_control_records = sum(
        int(row["parameters"]["sample_count"])
        for row in moduli
        if int(row["primitive_characters"]) > 0
    )
    header_bytes = active_moduli * (INPUT_HEADER.size + PARAMETER_HEADER.size)
    factored_total = (
        factored_shared_bytes + factored_character_bytes + exponent_bytes + header_bytes
    )
    service_batch_count = 0
    maximum_batches_for_one_q = 0
    peak_explicit_device_bytes = 0
    streamed_seed_moduli = 0
    for row in moduli:
        character_count = int(row["primitive_characters"])
        if character_count == 0:
            continue
        q = int(row["q"])
        transform_length = int(row["parameters"]["transform_length"])
        batch_plan = factored_service_batch_plan(
            q=q,
            transform_length=transform_length,
            character_count=character_count,
            usable_device_bytes=usable_device_bytes,
        )
        batches = int(batch_plan["campaign_batch_count"])
        service_batch_count += batches
        maximum_batches_for_one_q = max(maximum_batches_for_one_q, batches)
        peak_explicit_device_bytes = max(peak_explicit_device_bytes, int(batch_plan["explicit_device_bytes"]))
        streamed_seed_moduli += int(not batch_plan["shared_seeds_resident"])
    service_plan_header_bytes = active_moduli * (
        INPUT_HEADER.size + PLAN_COMMITMENT.size + PARAMETER_HEADER.size
    )
    service_batch_header_bytes = service_batch_count * (
        INPUT_HEADER.size + BATCH_BINDING.size
    )
    service_total = (
        factored_shared_bytes
        + factored_character_bytes
        + exponent_bytes
        + service_plan_header_bytes
        + service_batch_header_bytes
    )
    service_output_bytes = (
        legacy_seeds * OUTPUT_ITEM.size
        + service_batch_count * (OUTPUT_HEADER.size + SERVICE_OUTPUT_BINDING.size)
    )
    reduced_service_output_bytes = (
        source_lattice_values * OUTPUT_ITEM.size
        + service_batch_count * (OUTPUT_HEADER.size + SERVICE_OUTPUT_BINDING.size)
    )
    semantic_control_bytes = (
        semantic_control_records * SEMANTIC_CONTROL_ITEM.size
        + active_moduli * SEMANTIC_CONTROL_HEADER.size
    )
    # TGDBSSG1 is one independently byte-padded file per active modulus.
    # Rounding the global code count only once understates the physical wire
    # family whenever two q-level payloads both have a partial final byte.
    semantic_sign_payload_bytes = sum(
        (
            int(row["primitive_characters"])
            * int(row["parameters"]["sample_count"])
            + 3
        )
        // 4
        for row in moduli
        if int(row["primitive_characters"]) > 0
    )
    semantic_sign_bytes = (
        semantic_sign_payload_bytes
        + active_moduli * SEMANTIC_SIGN_HEADER.size
    )
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.factored_source_work.v3",
        "classification": "exact_q_persistent_split_service_payload",
        "q_start": base.SOURCE_Q_START,
        "q_stop": base.SOURCE_Q_STOP,
        "active_moduli": active_moduli,
        "primitive_characters": characters,
        "legacy_character_frequency_seeds": legacy_seeds,
        "shared_frequency_records": shared_frequency_records,
        "character_exponent_words": character_exponent_words,
        "legacy_v2_seed_bytes": legacy_seed_bytes,
        "factored_v3_shared_seed_bytes": factored_shared_bytes,
        "factored_v3_character_header_bytes": factored_character_bytes,
        "factored_v3_character_exponent_bytes": exponent_bytes,
        "factored_v3_header_bytes": header_bytes,
        "factored_v3_minimum_logical_bytes": factored_total,
        "service_usable_device_bytes": usable_device_bytes,
        "service_batch_count": service_batch_count,
        "service_maximum_batches_for_one_q": maximum_batches_for_one_q,
        "service_peak_explicit_device_bytes": peak_explicit_device_bytes,
        "service_streamed_seed_moduli": streamed_seed_moduli,
        "service_plan_header_bytes": service_plan_header_bytes,
        "service_batch_header_bytes": service_batch_header_bytes,
        "factored_v3_service_physical_bytes": service_total,
        "factored_v3_service_overhead_above_minimum_bytes": service_total - factored_total,
        "factored_v3_literal_service_output_bytes": service_output_bytes,
        "factored_v3_source_sample_only_service_output_bytes": reduced_service_output_bytes,
        "factored_v3_source_sample_only_bytes_avoided": (
            service_output_bytes - reduced_service_output_bytes
        ),
        "factored_v3_literal_output_item_bytes": legacy_seeds * OUTPUT_ITEM.size,
        "source_completed_lattice_output_items": source_lattice_values,
        "source_guard_frequency_output_items": guard_frequency_values,
        "source_guard_frequency_output_bytes": guard_frequency_values * OUTPUT_ITEM.size,
        "source_two_bit_sign_payload_bytes_if_materialized": (
            semantic_sign_payload_bytes
        ),
        "semantic_time_tail_control_records": semantic_control_records,
        "semantic_time_tail_control_bytes": semantic_control_bytes,
        "semantic_two_bit_sign_artifact_bytes": semantic_sign_bytes,
        "streaming_integrity_reducer_implemented": True,
        "streaming_integrity_persistent_raw_output_bytes": 0,
        "streaming_semantic_sign_reducer_implemented": True,
        "streaming_semantic_sign_reducer_cuda_fused": False,
        "streaming_semantic_sign_reducer_requires_replayed_control": True,
        "streaming_semantic_sign_reducer_preserves_ambiguous_samples": True,
        "streaming_semantic_sign_reducer_performs_multiplicity_inference": False,
        "streaming_full_raw_output_bytes_cross_process_boundary": service_output_bytes,
        "streaming_source_sample_only_raw_output_bytes_cross_process_boundary": (
            reduced_service_output_bytes
        ),
        "literal_output_requires_fused_downstream_reduction_for_cost_efficiency": True,
        "shared_seed_stream_copies_per_q": 1,
        "payload_reduction_ratio": legacy_seed_bytes / factored_total,
        "service_payload_reduction_ratio": legacy_seed_bytes / service_total,
        "seed_cardinality_reduction_ratio": legacy_seeds / shared_frequency_records,
        "q_persistent_service_implemented": True,
        "cuda_factored_consumer_implemented": True,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "CHECKER_ID",
    "FactoredSmallQError",
    "ParsedCharacterBatch",
    "ParsedFrame",
    "ParsedSharedPlan",
    "REDUCED_SERVICE_OUTPUT_MAGIC",
    "factored_device_memory_bytes",
    "factored_service_batch_plan",
    "maximum_factored_batch_characters",
    "parse_factored_character_batch",
    "parse_factored_shared_plan",
    "parse_factored_shared_plan_metadata",
    "parse_factored_seed_frame",
    "source_work",
    "verify_factored_output_kat",
    "verify_factored_service_campaign",
    "verify_factored_service_output_kat",
    "verify_factored_seed_frame",
    "write_factored_character_batch",
    "write_factored_seed_frame",
    "write_factored_service_campaign",
    "write_factored_shared_plan",
]
