"""Exact fixed-point reference for the Ramaré--Zúñiga ``R2Star`` campaign.

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

This is the arithmetic contract for a future segmented GPU producer.  It
uses integer-directed logarithm and Euler-gamma enclosures and reduces the
target inequality to a squared integer comparison.  The implementation is a
small-range CPU reference, not a claim that the 21-billion range has run.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from functools import lru_cache
import hashlib
import json
from math import isqrt
from typing import NoReturn

from .arithmetic import ZERO_SHA256
from .finite_campaigns import fixed_log_bounds


R2STAR_ATOM = "ramare-zuniga-lemma-6-2"
R2STAR_ALGORITHM = "r2star_fixed_point_stream_v1"
R2STAR_SOURCE_LIMIT = 21_000_000_000
R2STAR_BOUND_NUMERATOR = 193
R2STAR_BOUND_DENOMINATOR = 100
R2STAR_CHUNK_SCHEMA_VERSION = 1
R2STAR_FACTOR_SUPPORT_ENCODING = "r2star-distinct-prime-support-u64be-v1"
# A verifier holds one segmented factor table at a time.  This limit is an
# allocation guard, not a recommended production chunk size.
R2STAR_MAX_CHUNK_SPAN = 10_000_000


class R2StarReferenceError(ValueError):
    """An exact R2Star reference input or inequality failed closed."""


def _fail(message: str) -> NoReturn:
    raise R2StarReferenceError(message)


def _positive_integer(name: str, value: int, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        _fail(f"{name} must be an integer in [1, {maximum}]")
    return value


def _integer(
    name: str,
    value: object,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        _fail(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        _fail(f"{name} must be at most {maximum}")
    return value


def _digest(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{name} must be a lowercase SHA-256 digest")
    return value


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


def euler_gamma_fixed_bounds(
    *, scale_bits: int = 128, series_terms: int = 48, harmonic_terms: int = 100_000
) -> tuple[int, int]:
    """Enclose ``2**scale_bits * EulerGamma`` using elementary inequalities.

    The standard monotone bounds

    ``H_m - log(m+1) <= gamma <= H_m - log(m)``

    are combined with directed fixed-point harmonic sums and the rational
    atanh-series logarithm used by the psi checker.
    """

    scale_bits = _positive_integer("scale_bits", scale_bits, maximum=4_096)
    series_terms = _positive_integer("series_terms", series_terms, maximum=4_096)
    harmonic_terms = _positive_integer(
        "harmonic_terms", harmonic_terms, maximum=10_000_000
    )
    scale = 1 << scale_bits
    harmonic_lower = 0
    harmonic_upper = 0
    for denominator in range(1, harmonic_terms + 1):
        harmonic_lower += scale // denominator
        harmonic_upper += _ceil_div(scale, denominator)
    log_m_lower, _log_m_upper = fixed_log_bounds(
        harmonic_terms, scale_bits, series_terms
    )
    _log_next_lower, log_next_upper = fixed_log_bounds(
        harmonic_terms + 1, scale_bits, series_terms
    )
    lower = harmonic_lower - log_next_upper
    upper = harmonic_upper - log_m_lower
    if not 0 < lower <= upper:
        _fail("directed Euler-gamma enclosure is invalid")
    return lower, upper


def _primes_upto(limit: int) -> tuple[int, ...]:
    if limit < 2:
        return ()
    sieve = bytearray(b"\x01") * (limit + 1)
    sieve[0:2] = b"\x00\x00"
    for prime in range(2, isqrt(limit) + 1):
        if not sieve[prime]:
            continue
        start = prime * prime
        sieve[start : limit + 1 : prime] = b"\x00" * (
            (limit - start) // prime + 1
        )
    return tuple(index for index in range(2, limit + 1) if sieve[index])


def _factor_block(
    lower: int, upper: int, primes: tuple[int, ...]
) -> tuple[tuple[int, ...], ...]:
    """Return distinct prime factors for every integer in ``[lower, upper)``."""

    remaining = list(range(lower, upper))
    factors: list[list[int]] = [[] for _ in remaining]
    root = isqrt(upper - 1)
    for prime in primes:
        if prime > root:
            break
        first = (-lower) % prime
        for index in range(first, len(remaining), prime):
            value = remaining[index]
            if value % prime != 0:
                continue
            factors[index].append(prime)
            while value % prime == 0:
                value //= prime
            remaining[index] = value
    for index, value in enumerate(remaining):
        if value > 1:
            factors[index].append(value)
    return tuple(tuple(row) for row in factors)


def factor_support_rows_digest(
    lower: int, rows: Iterable[Iterable[int]]
) -> str:
    """Hash one factor-support stream with an unambiguous integer encoding.

    The preamble fixes the format.  Each row is encoded as the corresponding
    integer, the number of distinct prime factors, and the factors themselves;
    every integer word is unsigned, eight-byte, and big-endian.  Consequently
    a future GPU producer can implement this commitment without serializing a
    large JSON object.  This function consumes ``rows`` exactly once.
    """

    lower = _integer(
        "lower", lower, minimum=1, maximum=R2STAR_SOURCE_LIMIT
    )
    if isinstance(rows, (str, bytes, bytearray)):
        _fail("factor-support rows must be an iterable of integer iterables")
    try:
        iterator = iter(rows)
    except TypeError as error:
        raise R2StarReferenceError(
            "factor-support rows must be an iterable of integer iterables"
        ) from error
    digest = hashlib.sha256()
    digest.update(R2STAR_FACTOR_SUPPORT_ENCODING.encode("ascii") + b"\x00")
    number = lower
    for row_index, row in enumerate(iterator):
        if number > R2STAR_SOURCE_LIMIT:
            _fail("factor-support stream exceeds the source range")
        if isinstance(row, (str, bytes, bytearray)):
            _fail(f"factor-support row {row_index} must be an integer iterable")
        try:
            factors = tuple(row)
        except TypeError as error:
            raise R2StarReferenceError(
                f"factor-support row {row_index} must be an integer iterable"
            ) from error
        if len(factors) > 10:
            # The product of the first eleven primes already exceeds 21e9.
            _fail(f"factor-support row {row_index} has too many factors")
        previous = 1
        for factor_index, factor in enumerate(factors):
            factor = _integer(
                f"factor-support row {row_index} factor {factor_index}",
                factor,
                minimum=2,
                maximum=R2STAR_SOURCE_LIMIT,
            )
            if factor <= previous:
                _fail(
                    f"factor-support row {row_index} is not strictly increasing"
                )
            previous = factor
        digest.update(number.to_bytes(8, "big"))
        digest.update(len(factors).to_bytes(8, "big"))
        for factor in factors:
            digest.update(factor.to_bytes(8, "big"))
        number += 1
    return digest.hexdigest()


@dataclass(frozen=True)
class R2StarChunk:
    """One exact, hash-linked ``R2Star`` transition over ``[lower, upper)``.

    The factor rows are intentionally not retained.  Their canonical digest
    is committed here and independently recomputed by the verifier, keeping
    both certificate generation and verification bounded by one chunk.
    """

    schema_version: int
    lower: int
    upper: int
    scale_bits: int
    series_terms: int
    harmonic_terms: int
    bound_numerator: int
    bound_denominator: int
    gamma_lower: int
    gamma_upper: int
    incoming_lower: int
    incoming_upper: int
    outgoing_lower: int
    outgoing_upper: int
    minimum_squared_slack: int
    minimum_slack_index: int
    factor_support_digest: str
    previous_hash: str
    record_hash: str

    def body(self) -> dict[str, object]:
        """Return the exact integer/string body committed by ``record_hash``."""

        return {
            "algorithm": R2STAR_ALGORITHM,
            "atom": R2STAR_ATOM,
            "bound_denominator": self.bound_denominator,
            "bound_numerator": self.bound_numerator,
            "factor_support_digest": self.factor_support_digest,
            "factor_support_encoding": R2STAR_FACTOR_SUPPORT_ENCODING,
            "gamma_lower": self.gamma_lower,
            "gamma_upper": self.gamma_upper,
            "harmonic_terms": self.harmonic_terms,
            "incoming_lower": self.incoming_lower,
            "incoming_upper": self.incoming_upper,
            "lower": self.lower,
            "minimum_slack_index": self.minimum_slack_index,
            "minimum_squared_slack": self.minimum_squared_slack,
            "outgoing_lower": self.outgoing_lower,
            "outgoing_upper": self.outgoing_upper,
            "previous_hash": self.previous_hash,
            "scale_bits": self.scale_bits,
            "schema_version": self.schema_version,
            "series_terms": self.series_terms,
            "upper": self.upper,
        }

    def recomputed_hash(self) -> str:
        return _sha256(self.body())


def _validate_r2star_chunk_fields(
    chunk: R2StarChunk, *, check_hash: bool
) -> None:
    if not isinstance(chunk, R2StarChunk):
        _fail("R2Star chunk must be an R2StarChunk")
    schema = _integer("chunk.schema_version", chunk.schema_version, minimum=1)
    if schema != R2STAR_CHUNK_SCHEMA_VERSION:
        _fail(f"unsupported R2Star chunk schema version {schema}")
    lower = _integer(
        "chunk.lower", chunk.lower, minimum=1, maximum=R2STAR_SOURCE_LIMIT
    )
    upper = _integer(
        "chunk.upper", chunk.upper, minimum=2, maximum=R2STAR_SOURCE_LIMIT + 1
    )
    if upper <= lower:
        _fail("R2Star chunk range must be nonempty and half-open")
    if upper - lower > R2STAR_MAX_CHUNK_SPAN:
        _fail("R2Star chunk exceeds the bounded-memory span limit")
    if upper <= 3:
        _fail("every R2Star chunk must contain an envelope witness n >= 3")
    _integer("chunk.scale_bits", chunk.scale_bits, minimum=1, maximum=4_096)
    _integer("chunk.series_terms", chunk.series_terms, minimum=1, maximum=4_096)
    _integer(
        "chunk.harmonic_terms",
        chunk.harmonic_terms,
        minimum=1,
        maximum=10_000_000,
    )
    if chunk.bound_numerator != R2STAR_BOUND_NUMERATOR:
        _fail("R2Star chunk changes the exact bound numerator")
    if chunk.bound_denominator != R2STAR_BOUND_DENOMINATOR:
        _fail("R2Star chunk changes the exact bound denominator")
    gamma_lower = _integer("chunk.gamma_lower", chunk.gamma_lower, minimum=1)
    gamma_upper = _integer("chunk.gamma_upper", chunk.gamma_upper, minimum=1)
    if gamma_lower > gamma_upper:
        _fail("R2Star chunk has a reversed Euler-gamma enclosure")
    incoming_lower = _integer("chunk.incoming_lower", chunk.incoming_lower)
    incoming_upper = _integer("chunk.incoming_upper", chunk.incoming_upper)
    if incoming_lower > incoming_upper:
        _fail("R2Star chunk has a reversed incoming state")
    outgoing_lower = _integer("chunk.outgoing_lower", chunk.outgoing_lower)
    outgoing_upper = _integer("chunk.outgoing_upper", chunk.outgoing_upper)
    if outgoing_lower > outgoing_upper:
        _fail("R2Star chunk has a reversed outgoing state")
    _integer(
        "chunk.minimum_squared_slack", chunk.minimum_squared_slack, minimum=0
    )
    witness = _integer(
        "chunk.minimum_slack_index",
        chunk.minimum_slack_index,
        minimum=max(3, lower),
        maximum=upper - 1,
    )
    if not lower <= witness < upper:
        _fail("R2Star chunk minimum-slack witness lies outside its range")
    _digest("chunk.factor_support_digest", chunk.factor_support_digest)
    _digest("chunk.previous_hash", chunk.previous_hash)
    _digest("chunk.record_hash", chunk.record_hash)
    if check_hash and chunk.recomputed_hash() != chunk.record_hash:
        _fail("R2Star chunk hash does not match its canonical body")


def rehash_r2star_chunk(chunk: R2StarChunk) -> R2StarChunk:
    """Rehash a modified chunk so tests can reach the semantic checks."""

    _validate_r2star_chunk_fields(chunk, check_hash=False)
    result = replace(chunk, record_hash=chunk.recomputed_hash())
    _validate_r2star_chunk_fields(result, check_hash=True)
    return result


@dataclass(frozen=True)
class R2StarChunkVerification:
    lower: int
    upper: int
    checked_integers: int
    outgoing_lower: int
    outgoing_upper: int
    minimum_squared_slack: int
    minimum_slack_index: int
    factor_support_digest: str
    record_hash: str


def _r2star_chunk_transition(
    *,
    lower: int,
    upper: int,
    scale_bits: int,
    series_terms: int,
    gamma_lower: int,
    gamma_upper: int,
    incoming_lower: int,
    incoming_upper: int,
    primes: tuple[int, ...],
) -> tuple[int, int, int, int, str]:
    factor_rows = _factor_block(lower, upper, primes)
    rows_digest = factor_support_rows_digest(lower, factor_rows)
    scale = 1 << scale_bits

    @lru_cache(maxsize=None)
    def log_bounds(integer: int) -> tuple[int, int]:
        return fixed_log_bounds(integer, scale_bits, series_terms)

    r_lower = incoming_lower
    r_upper = incoming_upper
    minimum_slack: int | None = None
    minimum_index = 0
    for offset, factors in enumerate(factor_rows):
        number = lower + offset
        a_lower = 0
        a_upper = 0
        if len(factors) == 1:
            log_lower, log_upper = log_bounds(factors[0])
            a_lower = -_ceil_div(log_upper * log_upper, scale)
            a_upper = -(log_lower * log_lower // scale)
        elif len(factors) == 2:
            left_lower, left_upper = log_bounds(factors[0])
            right_lower, right_upper = log_bounds(factors[1])
            a_lower = 2 * left_lower * right_lower // scale
            a_upper = _ceil_div(2 * left_upper * right_upper, scale)
        r_lower += a_lower + 2 * gamma_lower
        r_upper += a_upper + 2 * gamma_upper
        if r_lower > r_upper:
            _fail(f"R2Star enclosure reversed at n={number}")
        if number < 3:
            continue
        log_lower, _log_upper = log_bounds(number)
        magnitude = max(abs(r_lower), abs(r_upper))
        left = (R2STAR_BOUND_DENOMINATOR * magnitude) ** 2
        right = (
            R2STAR_BOUND_NUMERATOR
            * R2STAR_BOUND_NUMERATOR
            * number
            * log_lower
            * log_lower
        )
        slack = right - left
        if slack < 0:
            _fail(f"R2Star squared envelope fails at n={number}")
        if minimum_slack is None or slack < minimum_slack:
            minimum_slack = slack
            minimum_index = number
    if minimum_slack is None:
        _fail("R2Star chunk contains no checked envelope endpoint")
    return r_lower, r_upper, minimum_slack, minimum_index, rows_digest


def _create_r2star_chunk_with_constants(
    *,
    lower: int,
    upper: int,
    scale_bits: int,
    series_terms: int,
    harmonic_terms: int,
    gamma_lower: int,
    gamma_upper: int,
    incoming_lower: int,
    incoming_upper: int,
    previous_hash: str,
    primes: tuple[int, ...],
) -> R2StarChunk:
    (
        outgoing_lower,
        outgoing_upper,
        minimum_slack,
        minimum_index,
        rows_digest,
    ) = _r2star_chunk_transition(
        lower=lower,
        upper=upper,
        scale_bits=scale_bits,
        series_terms=series_terms,
        gamma_lower=gamma_lower,
        gamma_upper=gamma_upper,
        incoming_lower=incoming_lower,
        incoming_upper=incoming_upper,
        primes=primes,
    )
    chunk = R2StarChunk(
        schema_version=R2STAR_CHUNK_SCHEMA_VERSION,
        lower=lower,
        upper=upper,
        scale_bits=scale_bits,
        series_terms=series_terms,
        harmonic_terms=harmonic_terms,
        bound_numerator=R2STAR_BOUND_NUMERATOR,
        bound_denominator=R2STAR_BOUND_DENOMINATOR,
        gamma_lower=gamma_lower,
        gamma_upper=gamma_upper,
        incoming_lower=incoming_lower,
        incoming_upper=incoming_upper,
        outgoing_lower=outgoing_lower,
        outgoing_upper=outgoing_upper,
        minimum_squared_slack=minimum_slack,
        minimum_slack_index=minimum_index,
        factor_support_digest=rows_digest,
        previous_hash=previous_hash,
        record_hash=ZERO_SHA256,
    )
    return rehash_r2star_chunk(chunk)


def create_r2star_chunk(
    *,
    lower: int,
    upper: int,
    scale_bits: int = 128,
    series_terms: int = 48,
    harmonic_terms: int = 100_000,
    incoming_lower: int,
    incoming_upper: int,
    previous_hash: str = ZERO_SHA256,
) -> R2StarChunk:
    """Compute one deterministic exact chunk from its directed input state."""

    lower = _integer(
        "lower", lower, minimum=1, maximum=R2STAR_SOURCE_LIMIT
    )
    upper = _integer(
        "upper", upper, minimum=2, maximum=R2STAR_SOURCE_LIMIT + 1
    )
    scale_bits = _positive_integer("scale_bits", scale_bits, maximum=4_096)
    series_terms = _positive_integer("series_terms", series_terms, maximum=4_096)
    harmonic_terms = _positive_integer(
        "harmonic_terms", harmonic_terms, maximum=10_000_000
    )
    incoming_lower = _integer("incoming_lower", incoming_lower)
    incoming_upper = _integer("incoming_upper", incoming_upper)
    if incoming_lower > incoming_upper:
        _fail("incoming R2Star interval is reversed")
    _digest("previous_hash", previous_hash)
    # Field validation below gives the canonical range/span diagnostics before
    # a factor table can be allocated.
    if upper <= lower:
        _fail("R2Star chunk range must be nonempty and half-open")
    if upper - lower > R2STAR_MAX_CHUNK_SPAN:
        _fail("R2Star chunk exceeds the bounded-memory span limit")
    if upper <= 3:
        _fail("every R2Star chunk must contain an envelope witness n >= 3")
    gamma_lower, gamma_upper = euler_gamma_fixed_bounds(
        scale_bits=scale_bits,
        series_terms=series_terms,
        harmonic_terms=harmonic_terms,
    )
    return _create_r2star_chunk_with_constants(
        lower=lower,
        upper=upper,
        scale_bits=scale_bits,
        series_terms=series_terms,
        harmonic_terms=harmonic_terms,
        gamma_lower=gamma_lower,
        gamma_upper=gamma_upper,
        incoming_lower=incoming_lower,
        incoming_upper=incoming_upper,
        previous_hash=previous_hash,
        primes=_primes_upto(isqrt(upper - 1)),
    )


def _verify_r2star_chunk_with_constants(
    chunk: R2StarChunk,
    *,
    gamma_bounds: tuple[int, int],
    primes: tuple[int, ...],
) -> R2StarChunkVerification:
    _validate_r2star_chunk_fields(chunk, check_hash=True)
    if (chunk.gamma_lower, chunk.gamma_upper) != gamma_bounds:
        _fail("R2Star chunk has incorrect directed Euler-gamma bounds")
    (
        outgoing_lower,
        outgoing_upper,
        minimum_slack,
        minimum_index,
        rows_digest,
    ) = _r2star_chunk_transition(
        lower=chunk.lower,
        upper=chunk.upper,
        scale_bits=chunk.scale_bits,
        series_terms=chunk.series_terms,
        gamma_lower=chunk.gamma_lower,
        gamma_upper=chunk.gamma_upper,
        incoming_lower=chunk.incoming_lower,
        incoming_upper=chunk.incoming_upper,
        primes=primes,
    )
    if chunk.factor_support_digest != rows_digest:
        _fail("R2Star chunk has an incorrect factor-support digest")
    if (chunk.outgoing_lower, chunk.outgoing_upper) != (
        outgoing_lower,
        outgoing_upper,
    ):
        _fail("R2Star chunk has an incorrect outgoing directed state")
    if (chunk.minimum_squared_slack, chunk.minimum_slack_index) != (
        minimum_slack,
        minimum_index,
    ):
        _fail("R2Star chunk has an incorrect minimum-slack witness")
    return R2StarChunkVerification(
        lower=chunk.lower,
        upper=chunk.upper,
        checked_integers=chunk.upper - max(3, chunk.lower),
        outgoing_lower=outgoing_lower,
        outgoing_upper=outgoing_upper,
        minimum_squared_slack=minimum_slack,
        minimum_slack_index=minimum_index,
        factor_support_digest=rows_digest,
        record_hash=chunk.record_hash,
    )


def verify_r2star_chunk(chunk: R2StarChunk) -> R2StarChunkVerification:
    """Recompute every factor row and exact state transition in one chunk."""

    _validate_r2star_chunk_fields(chunk, check_hash=True)
    gamma_bounds = euler_gamma_fixed_bounds(
        scale_bits=chunk.scale_bits,
        series_terms=chunk.series_terms,
        harmonic_terms=chunk.harmonic_terms,
    )
    return _verify_r2star_chunk_with_constants(
        chunk,
        gamma_bounds=gamma_bounds,
        primes=_primes_upto(isqrt(chunk.upper - 1)),
    )


@dataclass(frozen=True)
class R2StarChainVerification:
    limit: int
    chunks: int
    checked_integers: int
    scale_bits: int
    series_terms: int
    harmonic_terms: int
    gamma_lower: int
    gamma_upper: int
    final_lower: int
    final_upper: int
    minimum_squared_slack: int
    minimum_slack_index: int
    final_hash: str
    exact_factor_support_verified: bool
    rational_log_enclosures_verified: bool
    rational_euler_gamma_enclosure_verified: bool
    exact_squared_envelope_verified: bool
    gap_free_hash_and_state_chain_verified: bool
    full_source_range: bool
    lean_atom_discharged: bool = False


def verify_r2star_chain(
    chunks: Iterable[R2StarChunk], *, expected_limit: int
) -> R2StarChainVerification:
    """Verify a one-pass, gap-free chain by recomputing every transition."""

    expected_limit = _integer(
        "expected_limit",
        expected_limit,
        minimum=3,
        maximum=R2STAR_SOURCE_LIMIT,
    )
    if isinstance(chunks, (str, bytes, bytearray)):
        _fail("R2Star certificate must be an iterable of chunks")
    try:
        iterator = iter(chunks)
        first = next(iterator)
    except TypeError as error:
        raise R2StarReferenceError(
            "R2Star certificate must be an iterable of chunks"
        ) from error
    except StopIteration:
        _fail("R2Star certificate must contain at least one chunk")
    if not isinstance(first, R2StarChunk):
        _fail("R2Star chain entry 0 has the wrong type")
    _validate_r2star_chunk_fields(first, check_hash=True)
    if first.lower != 1:
        _fail("R2Star certificate must begin at integer 1")
    if (first.incoming_lower, first.incoming_upper) != (0, 0):
        _fail("R2Star certificate must begin with the zero directed state")
    if first.previous_hash != ZERO_SHA256:
        _fail("R2Star certificate has a nonzero initial predecessor hash")
    if first.upper > expected_limit + 1:
        _fail("R2Star certificate extends beyond expected_limit")

    config = (first.scale_bits, first.series_terms, first.harmonic_terms)
    gamma_bounds = euler_gamma_fixed_bounds(
        scale_bits=first.scale_bits,
        series_terms=first.series_terms,
        harmonic_terms=first.harmonic_terms,
    )
    primes = _primes_upto(isqrt(expected_limit))
    first_result = _verify_r2star_chunk_with_constants(
        first, gamma_bounds=gamma_bounds, primes=primes
    )
    chunk_count = 1
    checked_integers = first_result.checked_integers
    minimum_slack = first_result.minimum_squared_slack
    minimum_index = first_result.minimum_slack_index
    previous = first

    for index, chunk in enumerate(iterator, start=1):
        if not isinstance(chunk, R2StarChunk):
            _fail(f"R2Star chain entry {index} has the wrong type")
        _validate_r2star_chunk_fields(chunk, check_hash=True)
        if chunk.lower != previous.upper:
            _fail(f"R2Star chunk {index} breaks integer range coverage")
        if chunk.upper > expected_limit + 1:
            _fail(f"R2Star chunk {index} extends beyond expected_limit")
        if chunk.previous_hash != previous.record_hash:
            _fail(f"R2Star chunk {index} breaks the hash chain")
        if (chunk.incoming_lower, chunk.incoming_upper) != (
            previous.outgoing_lower,
            previous.outgoing_upper,
        ):
            _fail(f"R2Star chunk {index} breaks the directed-state chain")
        if (chunk.scale_bits, chunk.series_terms, chunk.harmonic_terms) != config:
            _fail(f"R2Star chunk {index} changes the exact configuration")
        result = _verify_r2star_chunk_with_constants(
            chunk, gamma_bounds=gamma_bounds, primes=primes
        )
        checked_integers += result.checked_integers
        if result.minimum_squared_slack < minimum_slack:
            minimum_slack = result.minimum_squared_slack
            minimum_index = result.minimum_slack_index
        chunk_count += 1
        previous = chunk

    if previous.upper != expected_limit + 1:
        _fail("R2Star certificate does not end immediately after expected_limit")
    return R2StarChainVerification(
        limit=expected_limit,
        chunks=chunk_count,
        checked_integers=checked_integers,
        scale_bits=config[0],
        series_terms=config[1],
        harmonic_terms=config[2],
        gamma_lower=gamma_bounds[0],
        gamma_upper=gamma_bounds[1],
        final_lower=previous.outgoing_lower,
        final_upper=previous.outgoing_upper,
        minimum_squared_slack=minimum_slack,
        minimum_slack_index=minimum_index,
        final_hash=previous.record_hash,
        exact_factor_support_verified=True,
        rational_log_enclosures_verified=True,
        rational_euler_gamma_enclosure_verified=True,
        exact_squared_envelope_verified=True,
        gap_free_hash_and_state_chain_verified=True,
        full_source_range=expected_limit == R2STAR_SOURCE_LIMIT,
    )


def iter_r2star_certificate(
    limit: int,
    *,
    chunk_span: int = 100_000,
    scale_bits: int = 128,
    series_terms: int = 48,
    harmonic_terms: int = 100_000,
) -> Iterator[R2StarChunk]:
    """Yield an exact certificate while retaining only one factor chunk."""

    limit = _integer(
        "limit", limit, minimum=3, maximum=R2STAR_SOURCE_LIMIT
    )
    chunk_span = _integer(
        "chunk_span", chunk_span, minimum=3, maximum=R2STAR_MAX_CHUNK_SPAN
    )
    scale_bits = _positive_integer("scale_bits", scale_bits, maximum=4_096)
    series_terms = _positive_integer("series_terms", series_terms, maximum=4_096)
    harmonic_terms = _positive_integer(
        "harmonic_terms", harmonic_terms, maximum=10_000_000
    )
    gamma_lower, gamma_upper = euler_gamma_fixed_bounds(
        scale_bits=scale_bits,
        series_terms=series_terms,
        harmonic_terms=harmonic_terms,
    )
    primes = _primes_upto(isqrt(limit))
    lower = 1
    incoming_lower = 0
    incoming_upper = 0
    previous_hash = ZERO_SHA256
    while lower <= limit:
        upper = min(limit + 1, lower + chunk_span)
        chunk = _create_r2star_chunk_with_constants(
            lower=lower,
            upper=upper,
            scale_bits=scale_bits,
            series_terms=series_terms,
            harmonic_terms=harmonic_terms,
            gamma_lower=gamma_lower,
            gamma_upper=gamma_upper,
            incoming_lower=incoming_lower,
            incoming_upper=incoming_upper,
            previous_hash=previous_hash,
            primes=primes,
        )
        yield chunk
        lower = upper
        incoming_lower = chunk.outgoing_lower
        incoming_upper = chunk.outgoing_upper
        previous_hash = chunk.record_hash


def create_r2star_certificate(
    limit: int,
    *,
    chunk_span: int = 100_000,
    scale_bits: int = 128,
    series_terms: int = 48,
    harmonic_terms: int = 100_000,
) -> tuple[R2StarChunk, ...]:
    """Materialize a small certificate; use the iterator for production."""

    return tuple(
        iter_r2star_certificate(
            limit,
            chunk_span=chunk_span,
            scale_bits=scale_bits,
            series_terms=series_terms,
            harmonic_terms=harmonic_terms,
        )
    )


@dataclass(frozen=True)
class R2StarSample:
    limit: int
    scale_bits: int
    series_terms: int
    harmonic_terms: int
    block_size: int
    gamma_lower: int
    gamma_upper: int
    final_lower: int
    final_upper: int
    minimum_squared_slack: int
    minimum_slack_index: int
    exact_factor_support_verified: bool
    rational_log_enclosures_verified: bool
    rational_euler_gamma_enclosure_verified: bool
    exact_squared_envelope_verified: bool
    full_source_range: bool
    lean_atom_discharged: bool = False


def verify_r2star_sample(
    limit: int,
    *,
    scale_bits: int = 128,
    series_terms: int = 48,
    harmonic_terms: int = 100_000,
    block_size: int = 100_000,
) -> R2StarSample:
    """Recompute the exact directed ``R2Star`` stream through ``limit``."""

    limit = _positive_integer("limit", limit, maximum=R2STAR_SOURCE_LIMIT)
    if limit < 3:
        _fail("R2Star verification requires limit >= 3")
    scale_bits = _positive_integer("scale_bits", scale_bits, maximum=4_096)
    series_terms = _positive_integer("series_terms", series_terms, maximum=4_096)
    harmonic_terms = _positive_integer(
        "harmonic_terms", harmonic_terms, maximum=10_000_000
    )
    block_size = _positive_integer("block_size", block_size, maximum=10_000_000)
    scale = 1 << scale_bits
    gamma_lower, gamma_upper = euler_gamma_fixed_bounds(
        scale_bits=scale_bits,
        series_terms=series_terms,
        harmonic_terms=harmonic_terms,
    )
    primes = _primes_upto(isqrt(limit))

    @lru_cache(maxsize=None)
    def log_bounds(integer: int) -> tuple[int, int]:
        return fixed_log_bounds(integer, scale_bits, series_terms)

    r_lower = 0
    r_upper = 0
    minimum_slack: int | None = None
    minimum_index = 0
    for lower in range(1, limit + 1, block_size):
        upper = min(limit + 1, lower + block_size)
        factor_rows = _factor_block(lower, upper, primes)
        for offset, factors in enumerate(factor_rows):
            number = lower + offset
            a_lower = 0
            a_upper = 0
            if len(factors) == 1:
                log_lower, log_upper = log_bounds(factors[0])
                a_lower = -_ceil_div(log_upper * log_upper, scale)
                a_upper = -(log_lower * log_lower // scale)
            elif len(factors) == 2:
                left_lower, left_upper = log_bounds(factors[0])
                right_lower, right_upper = log_bounds(factors[1])
                a_lower = 2 * left_lower * right_lower // scale
                a_upper = _ceil_div(2 * left_upper * right_upper, scale)
            r_lower += a_lower + 2 * gamma_lower
            r_upper += a_upper + 2 * gamma_upper
            if r_lower > r_upper:
                _fail(f"R2Star enclosure reversed at n={number}")
            if number < 3:
                continue
            log_lower, _log_upper = log_bounds(number)
            magnitude = max(abs(r_lower), abs(r_upper))
            left = (R2STAR_BOUND_DENOMINATOR * magnitude) ** 2
            right = (
                R2STAR_BOUND_NUMERATOR
                * R2STAR_BOUND_NUMERATOR
                * number
                * log_lower
                * log_lower
            )
            slack = right - left
            if slack < 0:
                _fail(f"R2Star squared envelope fails at n={number}")
            if minimum_slack is None or slack < minimum_slack:
                minimum_slack = slack
                minimum_index = number
    if minimum_slack is None:
        _fail("R2Star verification produced no checked endpoint")
    return R2StarSample(
        limit=limit,
        scale_bits=scale_bits,
        series_terms=series_terms,
        harmonic_terms=harmonic_terms,
        block_size=block_size,
        gamma_lower=gamma_lower,
        gamma_upper=gamma_upper,
        final_lower=r_lower,
        final_upper=r_upper,
        minimum_squared_slack=minimum_slack,
        minimum_slack_index=minimum_index,
        exact_factor_support_verified=True,
        rational_log_enclosures_verified=True,
        rational_euler_gamma_enclosure_verified=True,
        exact_squared_envelope_verified=True,
        full_source_range=limit == R2STAR_SOURCE_LIMIT,
    )
