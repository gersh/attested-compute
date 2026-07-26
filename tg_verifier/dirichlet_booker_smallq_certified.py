# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Certificate boundary for the certified small-q CUDA disk engine.

The H100 kernel intentionally has no transcendental implementation.  This
module constructs and independently replays the much smaller certificate that
it consumes: one complex disk for ``w = exp(-pi*exp(2u)/q)``, one prefactor
disk, and one analytic-radius upper bound per frequency.  Replaying these
objects costs O(N) Arb transcendental evaluations instead of replaying every
one of the O(sum truncation) Gaussian terms.  Character roots and FFT twiddles
are independently reconstructed by the CUDA runner with directed MPFR.

The seed producer is not trusted merely because it emitted the binary format.
``verify_seed_frame`` reconstructs the character, epsilon, exact truncation,
both analytic tails, and both disks at a higher precision and fails closed.
The CUDA recurrence/DFT is rigorous conditional on that verified frame and on
the documented CUDA directed-basic-arithmetic contract.  ``verify_output_kat``
is a deliberately bounded, independent Arb end-to-end test; it is not a
source-scale term-by-term replay requirement.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
from pathlib import Path
import struct
import time
from typing import Any, Iterable, Sequence

from tg_verifier import dirichlet_booker_smallq as base


AUTHOR = "Gershon Bialer"
ALGORITHM_ID = "platt-booker-smallq-certified-disk-dft-v2"
CHECKER_ID = "arb-smallq-transcendental-seed-replay-v2"

INPUT_MAGIC = b"TGDBSCI2"
OUTPUT_MAGIC = b"TGDBSCO2"
FORMAT_VERSION = 2
NONUNIT_EXPONENT = (1 << 32) - 1

INPUT_HEADER = struct.Struct("<8sIIIIQQQIIQ")
PARAMETER_HEADER = struct.Struct("<qQQQQQ")
CHARACTER_HEADER = struct.Struct("<QIIQ")
FREQUENCY_PREFIX = struct.Struct("<QqII")
DISK = struct.Struct("<ddd")
FREQUENCY_SUFFIX = struct.Struct("<dQ")
FREQUENCY_SIZE = FREQUENCY_PREFIX.size + 2 * DISK.size + FREQUENCY_SUFFIX.size
OUTPUT_HEADER = struct.Struct("<8sIIIIQQQQQII")
OUTPUT_ITEM = struct.Struct("<QQdddII")

assert INPUT_HEADER.size == 64
assert PARAMETER_HEADER.size == 48
assert CHARACTER_HEADER.size == 24
assert FREQUENCY_SIZE == 88
assert OUTPUT_HEADER.size == 72
assert OUTPUT_ITEM.size == 48


class CertifiedSmallQError(RuntimeError):
    """A seed frame, output disk, or independent replay failed closed."""


def _fail(message: str) -> None:
    raise CertifiedSmallQError(message)


def _disk(value: Any) -> tuple[float, float, float]:
    """Return a binary64 disk containing an Arb complex rectangle."""

    center_real = float(value.real.mid())
    center_imag = float(value.imag.mid())
    distance = abs(value - base.acb(center_real, center_imag))
    radius = math.nextafter(float(distance.upper()), math.inf)
    if not all(math.isfinite(v) for v in (center_real, center_imag, radius)):
        _fail("Arb value does not fit a finite binary64 disk")
    return center_real, center_imag, radius


def _upper(value: Any) -> float:
    result = math.nextafter(float(value.upper()), math.inf)
    if not math.isfinite(result) or result < 0:
        _fail("analytic radius does not fit a finite nonnegative binary64")
    return result


def _disk_contains(disk: tuple[float, float, float], value: Any) -> bool:
    re, im, radius = disk
    if not all(math.isfinite(v) for v in disk) or radius < 0:
        return False
    distance = abs(value - base.acb(re, im))
    return bool(distance <= base.arb(radius))


@dataclass(frozen=True)
class ParsedSeed:
    index: int
    signed_index: int
    truncation: int
    w: tuple[float, float, float]
    prefactor: tuple[float, float, float]
    analytic_radius_hi: float


@dataclass(frozen=True)
class ParsedCharacter:
    character_id: int
    parity: int
    exponents: tuple[int, ...]
    seeds: tuple[ParsedSeed, ...]


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


def _seed_values(
    *,
    q: int,
    conrey_number: int,
    parameters: base.TransformParameters,
    index: int,
    target_bits: int,
    character: Any,
    epsilon: Any,
) -> tuple[int, int, Any, Any, Any]:
    length = parameters.transform_length
    signed = index if index <= length // 2 else index - length
    x = 2 * base.arb.pi() * abs(signed) / base._arb_fraction(parameters.b)
    truncation, gaussian_tail = base._choose_truncation(
        q=q,
        parity=int(character.parity()),
        eta=parameters.eta,
        x=x,
        target_bits=target_bits,
    )
    eta = base._arb_fraction(parameters.eta)
    u = base.acb(x, base.arb.pi() * eta / 4)
    w = (-base.arb.pi() * (2 * u).exp() / q).exp()
    p = base.arb(2 * int(character.parity()) + 1) / 2
    prefactor = 2 * epsilon * (p * u).exp() / (base.arb(q) ** (p / 2))
    alias = base._frequency_periodization_bound(
        q=q,
        parity=int(character.parity()),
        eta=parameters.eta,
        x=x,
        a=parameters.a,
    )
    return signed, truncation, w, prefactor, gaussian_tail + alias


def write_seed_frame(
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
    """Construct a producer frame; this becomes evidence only after replay."""

    base._require_flint()
    if parameters.q != q or not conrey_numbers:
        _fail("invalid modulus or empty character batch")
    stop = parameters.transform_length if frequency_stop is None else frequency_stop
    if not 0 <= frequency_start < stop <= parameters.transform_length:
        _fail("invalid frequency range")
    if run_dft and (frequency_start != 0 or stop != parameters.transform_length):
        _fail("DFT frames must contain a complete transform")
    characters = [base._character(q, n) for n in conrey_numbers]
    group_exponent = int(characters[0].group().exponent())
    if any(int(c.group().exponent()) != group_exponent for c in characters):
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
    total_terms = 0
    started = time.perf_counter_ns()
    with base.ctx.workprec(precision_bits):
        for conrey_number, character in zip(conrey_numbers, characters):
            chunks.append(
                CHARACTER_HEADER.pack(
                    conrey_number, int(character.parity()), 0, 0
                )
            )
            exponents = []
            for residue in range(q):
                exponent = character.chi_exponent(residue)
                exponents.append(
                    NONUNIT_EXPONENT if exponent is None else int(exponent)
                )
            chunks.append(struct.pack(f"<{q}I", *exponents))
            epsilon = base._epsilon_phase(character)
            for index in range(frequency_start, stop):
                signed, truncation, w, prefactor, analytic = _seed_values(
                    q=q,
                    conrey_number=conrey_number,
                    parameters=parameters,
                    index=index,
                    target_bits=target_bits,
                    character=character,
                    epsilon=epsilon,
                )
                chunks.append(FREQUENCY_PREFIX.pack(index, signed, truncation, 0))
                chunks.append(DISK.pack(*_disk(w)))
                chunks.append(DISK.pack(*_disk(prefactor)))
                chunks.append(FREQUENCY_SUFFIX.pack(_upper(analytic), 0))
                total_terms += truncation
    path.parent.mkdir(parents=True, exist_ok=True)
    base._write_atomic(path, b"".join(chunks))
    elapsed = time.perf_counter_ns() - started
    digest, size = base.sha256_file(path)
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.seed_frame.v2",
        "algorithm": ALGORITHM_ID,
        "classification": "untrusted-producer-output-requires-independent-replay",
        "q": q,
        "batch_count": len(characters),
        "frequency_count_per_character": stop - frequency_start,
        "finite_gaussian_terms_not_replayed_by_seed_checker": total_terms,
        "seed_generation_nanoseconds": elapsed,
        "path": str(path),
        "sha256": digest,
        "size_bytes": size,
    }


def parse_seed_frame(path: Path) -> ParsedFrame:
    raw = path.read_bytes()
    if len(raw) < INPUT_HEADER.size:
        _fail("truncated seed-frame header")
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
        _fail("invalid seed-frame header")
    if len(raw) < INPUT_HEADER.size + PARAMETER_HEADER.size:
        _fail("truncated exact parameter header")
    (
        eta_numerator,
        eta_denominator,
        a_numerator,
        a_denominator,
        b_numerator,
        b_denominator,
    ) = PARAMETER_HEADER.unpack_from(raw, INPUT_HEADER.size)
    try:
        eta = Fraction(eta_numerator, eta_denominator)
        a = Fraction(a_numerator, a_denominator)
        b = Fraction(b_numerator, b_denominator)
    except ZeroDivisionError as error:
        raise CertifiedSmallQError("zero exact parameter denominator") from error
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
            _fail("truncated character header")
        character_id, parity, reserved0, reserved1 = CHARACTER_HEADER.unpack_from(
            raw, offset
        )
        offset += CHARACTER_HEADER.size
        if parity not in (0, 1) or reserved0 or reserved1:
            _fail("invalid character header")
        exponent_size = q * 4
        if offset + exponent_size > len(raw):
            _fail("truncated character table")
        exponents = struct.unpack_from(f"<{q}I", raw, offset)
        offset += exponent_size
        if any(e != NONUNIT_EXPONENT and e >= group_exponent for e in exponents):
            _fail("character exponent outside group exponent")
        seeds: list[ParsedSeed] = []
        for local in range(frequency_count):
            if offset + FREQUENCY_SIZE > len(raw):
                _fail("truncated frequency seed")
            index, signed, truncation, item_reserved = FREQUENCY_PREFIX.unpack_from(
                raw, offset
            )
            offset += FREQUENCY_PREFIX.size
            w = DISK.unpack_from(raw, offset)
            offset += DISK.size
            prefactor = DISK.unpack_from(raw, offset)
            offset += DISK.size
            analytic, suffix_reserved = FREQUENCY_SUFFIX.unpack_from(raw, offset)
            offset += FREQUENCY_SUFFIX.size
            expected = frequency_start + local
            expected_signed = (
                expected if expected <= transform_length // 2 else expected - transform_length
            )
            if (
                index != expected
                or signed != expected_signed
                or truncation > 100_000_000
                or item_reserved
                or suffix_reserved
                or not all(math.isfinite(x) for x in (*w, *prefactor, analytic))
                or w[2] < 0
                or prefactor[2] < 0
                or analytic < 0
            ):
                _fail("invalid frequency seed")
            seeds.append(ParsedSeed(index, signed, truncation, w, prefactor, analytic))
        characters.append(ParsedCharacter(character_id, parity, exponents, tuple(seeds)))
    if offset != len(raw):
        _fail("trailing bytes in seed frame")
    return ParsedFrame(
        q,
        group_exponent,
        transform_length,
        frequency_start,
        frequency_count,
        bool(run_dft),
        target_bits,
        eta,
        a,
        b,
        tuple(characters),
    )


def verify_seed_frame(
    path: Path,
    *,
    parameters: base.TransformParameters,
    guard_bits: int = 64,
) -> dict[str, object]:
    """Independently replay every O(N) transcendental seed and tail bound."""

    base._require_flint()
    frame = parse_seed_frame(path)
    if (
        parameters.q != frame.q
        or parameters.transform_length != frame.transform_length
        or parameters.eta != frame.eta
        or parameters.a != frame.a
        or parameters.b != frame.b
    ):
        _fail("checker parameters do not match seed frame")
    if guard_bits < 32:
        _fail("seed replay guard must be at least 32 bits")
    started = time.perf_counter_ns()
    seed_count = 0
    avoided_terms = 0
    with base.ctx.workprec(base.DEFAULT_PRECISION_BITS + guard_bits):
        for stored_character in frame.characters:
            character = base._character(frame.q, stored_character.character_id)
            if (
                int(character.parity()) != stored_character.parity
                or int(character.group().exponent()) != frame.group_exponent
            ):
                _fail("stored character identity mismatch")
            for residue, stored in enumerate(stored_character.exponents):
                fresh = character.chi_exponent(residue)
                expected = NONUNIT_EXPONENT if fresh is None else int(fresh)
                if stored != expected:
                    _fail("stored character table mismatch")
            epsilon = base._epsilon_phase(character)
            for seed in stored_character.seeds:
                signed, truncation, w, prefactor, analytic = _seed_values(
                    q=frame.q,
                    conrey_number=stored_character.character_id,
                    parameters=parameters,
                    index=seed.index,
                    target_bits=frame.target_bits,
                    character=character,
                    epsilon=epsilon,
                )
                if seed.signed_index != signed or seed.truncation != truncation:
                    _fail(f"truncation/signed-index replay mismatch at {seed.index}")
                if not _disk_contains(seed.w, w):
                    _fail(f"w disk misses higher-precision replay at {seed.index}")
                if not _disk_contains(seed.prefactor, prefactor):
                    _fail(f"prefactor disk misses higher-precision replay at {seed.index}")
                if not analytic <= base.arb(seed.analytic_radius_hi):
                    _fail(f"analytic tail is understated at {seed.index}")
                seed_count += 1
                avoided_terms += truncation
    elapsed = time.perf_counter_ns() - started
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.seed_replay.v2",
        "checker": CHECKER_ID,
        "q": frame.q,
        "characters": len(frame.characters),
        "transcendental_seeds_replayed": seed_count,
        "finite_gaussian_terms_avoided": avoided_terms,
        "elapsed_nanoseconds": elapsed,
        "seeds_per_second": seed_count * 1_000_000_000 / max(elapsed, 1),
        "term_by_term_arb_replay_required": False,
        "passed": True,
    }


def _read_output(path: Path, frame: ParsedFrame) -> tuple[dict[str, int], list[tuple[int, int, tuple[float, float, float], int]]]:
    raw = path.read_bytes()
    if len(raw) < OUTPUT_HEADER.size:
        _fail("truncated certified CUDA output")
    values = OUTPUT_HEADER.unpack_from(raw)
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
    ) = values
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
        _fail("certified CUDA output header/size mismatch")
    items = []
    offset = OUTPUT_HEADER.size
    for batch, character in enumerate(frame.characters):
        for local in range(frame.frequency_count):
            character_id, index, re, im, radius, status, item_reserved = OUTPUT_ITEM.unpack_from(raw, offset)
            offset += OUTPUT_ITEM.size
            if (
                character_id != character.character_id
                or index != frame.frequency_start + local
                or status
                or item_reserved
                or not all(math.isfinite(x) for x in (re, im, radius))
                or radius < 0
            ):
                _fail("malformed certified CUDA output item")
            items.append((character_id, index, (re, im, radius), status))
    return {
        "terms": terms,
        "butterflies": butterflies,
        "elapsed_nanoseconds": elapsed,
    }, items


def verify_output_kat(
    input_path: Path,
    output_path: Path,
    *,
    parameters: base.TransformParameters,
    precision_bits: int = 224,
) -> dict[str, object]:
    """Bounded independent Arb replay of finite sums, tails, and the DFT."""

    frame = parse_seed_frame(input_path)
    metadata, items = _read_output(output_path, frame)
    if (
        parameters.q != frame.q
        or parameters.transform_length != frame.transform_length
        or parameters.eta != frame.eta
        or parameters.a != frame.a
        or parameters.b != frame.b
    ):
        _fail("KAT parameter mismatch")
    checked = 0
    with base.ctx.workprec(precision_bits):
        item_offset = 0
        for stored_character in frame.characters:
            character = base._character(frame.q, stored_character.character_id)
            epsilon = base._epsilon_phase(character)
            fresh = [
                base.evaluate_frequency(
                    q=frame.q,
                    conrey_number=stored_character.character_id,
                    parameters=parameters,
                    frequency_index=seed.index,
                    target_bits=frame.target_bits,
                    truncation=seed.truncation,
                    _character_object=character,
                    _epsilon=epsilon,
                )["enclosure"]
                for seed in stored_character.seeds
            ]
            if frame.run_dft:
                fresh = base._positive_dft(fresh)
            for value in fresh:
                disk = items[item_offset][2]
                if not _disk_contains(disk, value):
                    _fail(f"CUDA disk misses independent Arb KAT item {item_offset}")
                item_offset += 1
                checked += 1
    return {
        "kind": "sparkinterval.tg.dirichlet_booker_smallq.cuda_disk_kat.v2",
        "algorithm": ALGORITHM_ID,
        "independent_arb_values_checked": checked,
        "finite_gaussian_terms": metadata["terms"],
        "radix2_butterflies": metadata["butterflies"],
        "cuda_elapsed_nanoseconds": metadata["elapsed_nanoseconds"],
        "passed": True,
        "source_scale_kat_required": False,
    }


def benchmark_seed_replay(
    root: Path,
    *,
    q: int = 5,
    conrey_numbers: Sequence[int] = (2, 4),
    transform_length: int = 1024,
) -> dict[str, object]:
    parameters = base.transform_parameters(
        q,
        height=Fraction(1),
        guard_height=Fraction(4),
        transform_length=transform_length,
        eta=Fraction(0),
    )
    path = root / "seed-frame.bin"
    produced = write_seed_frame(
        path,
        q=q,
        conrey_numbers=conrey_numbers,
        parameters=parameters,
    )
    checked = verify_seed_frame(path, parameters=parameters)
    return {"producer": produced, "checker": checked}


__all__ = [
    "ALGORITHM_ID",
    "CHECKER_ID",
    "CertifiedSmallQError",
    "benchmark_seed_replay",
    "parse_seed_frame",
    "verify_output_kat",
    "verify_seed_frame",
    "write_seed_frame",
]
