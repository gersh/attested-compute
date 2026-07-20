# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact finite-campaign primitives for two ternary-Goldbach atoms.

This module has two deliberately different trust boundaries.

``ch25-psi-1e13``
    Prime and prime-power coverage is recomputed by an integer segmented
    sieve.  Every ``log(p)`` enclosure is recomputed with rational arithmetic
    from

    ``log(x) = 2 * sum_{j >= 0} z^(2*j+1)/(2*j+1)``,
    ``z = (x-1)/(x+1)``.

    The two real-variable psi envelopes are then reduced to exact integer
    inequalities at the jump endpoints.  The format is chunked and
    hash-linked so a large run can be checked incrementally.  A bounded run is
    still only a bounded run, and even a source-range run does not by itself
    construct a Lean proof relating the Python computation to Mathlib's
    ``Chebyshev.psi``.

``helfgott-prop-12-2-4``
    The admissible-q scheduler, conservative integer k-window coverage, and
    the finite rational sum ``G_q(k)`` are recomputed exactly.  The source
    window endpoints and final analytic margins contain logarithms,
    exponentials, Euler's constant, and fractional powers.  This module does
    not invent an evaluator for them.  It therefore accepts only outward
    rational enclosures supplied by another component and always reports the
    transcendental semantics as unverified.  Hashes provide deterministic
    integrity, not authenticity.

No successful result returned here sets ``lean_atom_discharged`` to true.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import lru_cache
import hashlib
import json
from math import gcd, isqrt
from typing import NoReturn

from .arithmetic import ZERO_SHA256, mobius_linear


PSI_ATOM = "ch25-psi-1e13"
PSI_ALGORITHM = "psi_prime_power_stream_v1"
PSI_SOURCE_LIMIT = 10**13
PSI_UPPER_NUMERATOR = 19_764_819
PSI_UPPER_DENOMINATOR = 25_000_000
PSI_LOG_SERIES = "atanh-rational-positive-v1"

PROP1224_ATOM = "helfgott-prop-12-2-4"
PROP1224_ALGORITHM = "prop1224_interval_window_stream_v1"
PROP1224_Q_SPLIT = 3_300_000_000
PROP1224_Q_END = 22_000_000_000
PROP1224_DIVISOR = 210
PROP1224_SEMANTICS_STATUS = (
    "structural-only: outward transcendental enclosures are supplied, "
    "not recomputed"
)

_MAX_SCALE_BITS = 4_096
_MAX_SERIES_TERMS = 4_096
# The q=1 source window is approximately 20.01 million k rows, so the guard
# must remain above that legitimate worst case.  It is a per-chunk allocation
# guard, not a claim that retaining such a Python object graph is economical.
_MAX_HASHED_ROWS = 25_000_000


class FiniteCampaignError(ValueError):
    """A finite-campaign certificate failed closed."""


def _fail(message: str) -> NoReturn:
    raise FiniteCampaignError(message)


def _int(name: str, value: object, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        _fail(f"{name} must be at least {minimum}")
    return value


def _digest(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        _fail(f"{name} must be a lowercase SHA-256 digest")
    return value


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _fraction(name: str, numerator: object, denominator: object) -> Fraction:
    numerator = _int(f"{name}.numerator", numerator)
    denominator = _int(f"{name}.denominator", denominator, minimum=1)
    value = Fraction(numerator, denominator)
    if value.numerator != numerator or value.denominator != denominator:
        _fail(f"{name} must be stored in canonical lowest terms")
    return value


def _floor(value: Fraction) -> int:
    return value.numerator // value.denominator


def _ceil(value: Fraction) -> int:
    return -((-value.numerator) // value.denominator)


def _simple_primes(limit: int) -> list[int]:
    limit = _int("limit", limit, minimum=0)
    if limit < 2:
        return []
    composite = bytearray(limit + 1)
    for prime in range(2, isqrt(limit) + 1):
        if composite[prime]:
            continue
        start = prime * prime
        composite[start : limit + 1 : prime] = b"\x01" * (
            (limit - start) // prime + 1
        )
    return [number for number in range(2, limit + 1) if not composite[number]]


def iter_primes_segmented(
    lower: int, upper: int, *, segment_size: int = 1_000_000
) -> Iterator[int]:
    """Yield every prime in the half-open integer interval ``[lower, upper)``.

    The base sieve only reaches ``sqrt(upper - 1)``.  This is full-capable in
    the literal algorithmic sense, but enumerating primes through ``10^13`` is
    not asserted to be practically feasible on the development server.
    """

    lower = _int("lower", lower, minimum=0)
    upper = _int("upper", upper, minimum=0)
    segment_size = _int("segment_size", segment_size, minimum=1)
    if upper < lower:
        _fail("upper must not be below lower")
    if upper <= 2:
        return
    lower = max(lower, 2)
    base = _simple_primes(isqrt(upper - 1))
    for lo in range(lower, upper, segment_size):
        hi = min(upper, lo + segment_size)
        composite = bytearray(hi - lo)
        for prime in base:
            if prime * prime >= hi and prime > isqrt(hi - 1):
                break
            first = max(prime * prime, ((lo + prime - 1) // prime) * prime)
            if first < hi:
                composite[first - lo : hi - lo : prime] = b"\x01" * (
                    (hi - 1 - first) // prime + 1
                )
        for offset, marked in enumerate(composite):
            if not marked:
                yield lo + offset


@dataclass(frozen=True, order=True)
class PrimePower:
    """One exact von-Mangoldt jump ``value = prime**exponent``."""

    value: int
    prime: int
    exponent: int


def prime_power_events(
    lower: int, upper: int, *, segment_size: int = 1_000_000
) -> tuple[PrimePower, ...]:
    """Return all and only prime powers in ``[lower, upper)`` in value order."""

    lower = _int("lower", lower, minimum=1)
    upper = _int("upper", upper, minimum=1)
    if upper < lower:
        _fail("upper must not be below lower")
    if upper == lower or upper <= 2:
        return ()

    events = [
        PrimePower(prime, prime, 1)
        for prime in iter_primes_segmented(
            lower, upper, segment_size=segment_size
        )
    ]
    # Every exponent >= 2 has base at most sqrt(upper - 1), so the small base
    # sieve is complete.  Repeated powers of one prime are distinct events;
    # powers of distinct primes cannot coincide.
    for prime in _simple_primes(isqrt(upper - 1)):
        value = prime * prime
        exponent = 2
        while value < upper:
            if value >= lower:
                events.append(PrimePower(value, prime, exponent))
            if value > (upper - 1) // prime:
                break
            value *= prime
            exponent += 1
    events.sort()
    return tuple(events)


def _positive_log_series_bounds(
    numerator: int, denominator: int, terms: int
) -> tuple[Fraction, Fraction]:
    """Bound ``log(numerator/denominator)`` for ``1 <= ratio <= 2``.

    For ``z=(x-1)/(x+1)`` all terms are nonnegative.  After ``terms`` terms,
    replacing every remaining odd denominator by ``2*terms+1`` gives the
    rigorous geometric-tail upper bound used below.
    """

    numerator = _int("numerator", numerator, minimum=1)
    denominator = _int("denominator", denominator, minimum=1)
    terms = _int("terms", terms, minimum=1)
    if terms > _MAX_SERIES_TERMS:
        _fail(f"terms exceeds {_MAX_SERIES_TERMS}")
    if not denominator <= numerator <= 2 * denominator:
        _fail("positive log series requires 1 <= numerator/denominator <= 2")
    z = Fraction(numerator - denominator, numerator + denominator)
    if z == 0:
        return Fraction(0), Fraction(0)
    z_squared = z * z
    power = z
    partial = Fraction(0)
    for index in range(terms):
        partial += power / (2 * index + 1)
        power *= z_squared
    lower = 2 * partial
    remainder = 2 * power / ((2 * terms + 1) * (1 - z_squared))
    return lower, lower + remainder


@lru_cache(maxsize=32_768)
def fixed_log_bounds(prime: int, scale_bits: int, terms: int) -> tuple[int, int]:
    """Return exact outward integer bounds for ``2**scale_bits * log(prime)``."""

    prime = _int("prime", prime, minimum=2)
    scale_bits = _int("scale_bits", scale_bits, minimum=1)
    if scale_bits > _MAX_SCALE_BITS:
        _fail(f"scale_bits exceeds {_MAX_SCALE_BITS}")
    terms = _int("terms", terms, minimum=1)
    if terms > _MAX_SERIES_TERMS:
        _fail(f"terms exceeds {_MAX_SERIES_TERMS}")

    exponent = prime.bit_length() - 1
    power_of_two = 1 << exponent
    log_two_lower, log_two_upper = _positive_log_series_bounds(2, 1, terms)
    mantissa_lower, mantissa_upper = _positive_log_series_bounds(
        prime, power_of_two, terms
    )
    lower = exponent * log_two_lower + mantissa_lower
    upper = exponent * log_two_upper + mantissa_upper
    scale = 1 << scale_bits
    return _floor(lower * scale), _ceil(upper * scale)


@dataclass(frozen=True)
class PsiEvent:
    """A prime-power jump and independently reproducible fixed log bounds."""

    value: int
    prime: int
    exponent: int
    log_lower: int
    log_upper: int

    def body(self) -> list[int]:
        return [
            self.value,
            self.prime,
            self.exponent,
            self.log_lower,
            self.log_upper,
        ]


@dataclass(frozen=True)
class PsiChunk:
    """One hash-linked, half-open prime-power certificate chunk."""

    lower: int
    upper: int
    scale_bits: int
    series_terms: int
    incoming_lower: int
    incoming_upper: int
    outgoing_lower: int
    outgoing_upper: int
    events: tuple[PsiEvent, ...]
    previous_hash: str
    record_hash: str

    def body(self) -> dict[str, object]:
        return {
            "algorithm": PSI_ALGORITHM,
            "atom": PSI_ATOM,
            "events": [event.body() for event in self.events],
            "incoming_lower": self.incoming_lower,
            "incoming_upper": self.incoming_upper,
            "log_series": PSI_LOG_SERIES,
            "lower": self.lower,
            "outgoing_lower": self.outgoing_lower,
            "outgoing_upper": self.outgoing_upper,
            "previous_hash": self.previous_hash,
            "scale_bits": self.scale_bits,
            "series_terms": self.series_terms,
            "upper": self.upper,
        }

    def recomputed_hash(self) -> str:
        return _sha256(self.body())


def rehash_psi_chunk(chunk: PsiChunk) -> PsiChunk:
    """Rehash a modified chunk; useful to test semantic checks past hashing."""

    if not isinstance(chunk, PsiChunk):
        _fail("chunk must be a PsiChunk")
    if not isinstance(chunk.events, tuple) or any(
        not isinstance(event, PsiEvent) for event in chunk.events
    ):
        _fail("chunk events must be a tuple of PsiEvent values")
    return replace(chunk, record_hash=chunk.recomputed_hash())


def create_psi_chunk(
    *,
    lower: int,
    upper: int,
    scale_bits: int,
    series_terms: int,
    incoming_lower: int,
    incoming_upper: int,
    previous_hash: str = ZERO_SHA256,
    segment_size: int = 1_000_000,
) -> PsiChunk:
    """Compute one deterministic exact psi certificate chunk."""

    lower = _int("lower", lower, minimum=2)
    upper = _int("upper", upper, minimum=3)
    if upper <= lower:
        _fail("psi chunks must be nonempty")
    scale_bits = _int("scale_bits", scale_bits, minimum=1)
    series_terms = _int("series_terms", series_terms, minimum=1)
    incoming_lower = _int("incoming_lower", incoming_lower, minimum=0)
    incoming_upper = _int("incoming_upper", incoming_upper, minimum=0)
    if incoming_lower > incoming_upper:
        _fail("incoming psi interval is reversed")
    _digest("previous_hash", previous_hash)

    psi_lower = incoming_lower
    psi_upper = incoming_upper
    events: list[PsiEvent] = []
    for event in prime_power_events(lower, upper, segment_size=segment_size):
        log_lower, log_upper = fixed_log_bounds(
            event.prime, scale_bits, series_terms
        )
        events.append(
            PsiEvent(
                value=event.value,
                prime=event.prime,
                exponent=event.exponent,
                log_lower=log_lower,
                log_upper=log_upper,
            )
        )
        psi_lower += log_lower
        psi_upper += log_upper

    chunk = PsiChunk(
        lower=lower,
        upper=upper,
        scale_bits=scale_bits,
        series_terms=series_terms,
        incoming_lower=incoming_lower,
        incoming_upper=incoming_upper,
        outgoing_lower=psi_lower,
        outgoing_upper=psi_upper,
        events=tuple(events),
        previous_hash=previous_hash,
        record_hash=ZERO_SHA256,
    )
    return rehash_psi_chunk(chunk)


def _check_lower_psi_limit(value: int, psi_lower: int, scale: int) -> bool:
    """Check the non-strict left-limit bound needed for a strict open slab.

    On a slab with fixed true value ``a >= psi_lower >= 0``, the function
    ``(x-a)/sqrt(x)`` is strictly increasing.  Replacing ``a`` by its lower
    bound only increases it.  Thus a non-strict check at the excluded next
    jump proves the source's strict lower inequality at every point inside
    the slab.  The terminal closed endpoint is handled strictly by
    :func:`verify_psi_chain`.
    """

    difference = value * scale - psi_lower
    return difference <= 0 or difference * difference <= 2 * value * scale * scale


def _check_upper_psi_jump(value: int, psi_upper: int, scale: int) -> bool:
    """Check the upper envelope immediately after a jump.

    For fixed ``a >= 0``, ``(a-x)/sqrt(x)`` is strictly decreasing.  Replacing
    the true psi value by ``psi_upper`` only increases the expression, so the
    post-jump endpoint controls the entire following slab.
    """

    difference = psi_upper - value * scale
    if difference <= 0:
        return True
    return (
        difference
        * difference
        * PSI_UPPER_DENOMINATOR
        * PSI_UPPER_DENOMINATOR
        <= PSI_UPPER_NUMERATOR
        * PSI_UPPER_NUMERATOR
        * value
        * scale
        * scale
    )


def verify_psi_chunk(
    chunk: PsiChunk, *, segment_size: int = 1_000_000
) -> tuple[int, int, int]:
    """Recompute one chunk and return ``(events, outgoing_lo, outgoing_hi)``."""

    if not isinstance(chunk, PsiChunk):
        _fail("psi chain entries must be PsiChunk values")
    _int("chunk.lower", chunk.lower, minimum=2)
    _int("chunk.upper", chunk.upper, minimum=3)
    if chunk.upper <= chunk.lower:
        _fail("psi chunk range is empty or reversed")
    scale_bits = _int("chunk.scale_bits", chunk.scale_bits, minimum=1)
    if scale_bits > _MAX_SCALE_BITS:
        _fail("psi scale is too large")
    terms = _int("chunk.series_terms", chunk.series_terms, minimum=1)
    if terms > _MAX_SERIES_TERMS:
        _fail("psi series term count is too large")
    incoming_lower = _int(
        "chunk.incoming_lower", chunk.incoming_lower, minimum=0
    )
    incoming_upper = _int(
        "chunk.incoming_upper", chunk.incoming_upper, minimum=0
    )
    if incoming_lower > incoming_upper:
        _fail("psi incoming interval is reversed")
    _digest("chunk.previous_hash", chunk.previous_hash)
    _digest("chunk.record_hash", chunk.record_hash)
    if not isinstance(chunk.events, tuple):
        _fail("psi events must be stored as a tuple")
    for index, event in enumerate(chunk.events):
        if not isinstance(event, PsiEvent):
            _fail(f"psi event {index} has the wrong type")
        _int(f"psi event {index}.value", event.value, minimum=2)
        _int(f"psi event {index}.prime", event.prime, minimum=2)
        _int(f"psi event {index}.exponent", event.exponent, minimum=1)
        log_lower = _int(
            f"psi event {index}.log_lower", event.log_lower, minimum=0
        )
        log_upper = _int(
            f"psi event {index}.log_upper", event.log_upper, minimum=0
        )
        if log_lower > log_upper:
            _fail(f"psi event {index} has a reversed log interval")
    if chunk.recomputed_hash() != chunk.record_hash:
        _fail("psi chunk hash does not match its canonical body")

    expected = prime_power_events(
        chunk.lower, chunk.upper, segment_size=segment_size
    )
    if len(chunk.events) != len(expected):
        _fail("psi chunk does not have the exact prime-power event count")
    if len(expected) > _MAX_HASHED_ROWS:
        _fail("psi chunk exceeds the local row safety limit")

    psi_lower = incoming_lower
    psi_upper = incoming_upper
    scale = 1 << scale_bits
    for index, (stored, exact) in enumerate(zip(chunk.events, expected)):
        if (stored.value, stored.prime, stored.exponent) != (
            exact.value,
            exact.prime,
            exact.exponent,
        ):
            _fail(f"psi event {index} is missing, spurious, or out of order")
        log_lower, log_upper = fixed_log_bounds(
            exact.prime, scale_bits, terms
        )
        if (stored.log_lower, stored.log_upper) != (log_lower, log_upper):
            _fail(f"psi event {index} has incorrect directed log bounds")
        if not _check_lower_psi_limit(exact.value, psi_lower, scale):
            _fail(f"lower psi envelope fails at the left limit of {exact.value}")
        psi_lower += log_lower
        psi_upper += log_upper
        if not _check_upper_psi_jump(exact.value, psi_upper, scale):
            _fail(f"upper psi envelope fails after the jump at {exact.value}")

    if (chunk.outgoing_lower, chunk.outgoing_upper) != (psi_lower, psi_upper):
        _fail("psi chunk has an incorrect outgoing interval state")
    return len(expected), psi_lower, psi_upper


@dataclass(frozen=True)
class PsiVerification:
    limit: int
    chunks: int
    events: int
    final_lower: int
    final_upper: int
    final_hash: str
    exact_prime_power_coverage_verified: bool
    rational_log_enclosures_verified: bool
    exact_envelope_inequalities_verified: bool
    full_source_range: bool
    lean_atom_discharged: bool = False


def verify_psi_chain(
    chunks: Iterable[PsiChunk],
    *,
    expected_limit: int,
    segment_size: int = 1_000_000,
) -> PsiVerification:
    """Verify gap-free chunks and the psi envelopes through ``expected_limit``."""

    expected_limit = _int("expected_limit", expected_limit, minimum=2)
    if isinstance(chunks, (str, bytes, bytearray)):
        _fail("psi certificate must be an iterable of chunks")
    try:
        iterator = iter(chunks)
        first = next(iterator)
    except TypeError as error:
        raise FiniteCampaignError(
            "psi certificate must be an iterable of chunks"
        ) from error
    except StopIteration:
        _fail("psi certificate must contain at least one chunk")
    if not isinstance(first, PsiChunk):
        _fail("psi chain entry 0 has the wrong type")
    if first.lower != 2:
        _fail("psi certificate must begin at integer 2")
    if first.incoming_lower != 0 or first.incoming_upper != 0:
        _fail("psi certificate must begin with psi(1)=0")
    if first.previous_hash != ZERO_SHA256:
        _fail("psi certificate has a nonzero initial predecessor hash")

    total_events, _, _ = verify_psi_chunk(first, segment_size=segment_size)
    chunk_count = 1
    previous = first
    for index, chunk in enumerate(iterator, start=1):
        if not isinstance(chunk, PsiChunk):
            _fail(f"psi chain entry {index} has the wrong type")
        if chunk.lower != previous.upper:
            _fail(f"psi chunk {index} breaks integer range coverage")
        if chunk.previous_hash != previous.record_hash:
            _fail(f"psi chunk {index} breaks the hash chain")
        if (
            chunk.incoming_lower,
            chunk.incoming_upper,
        ) != (
            previous.outgoing_lower,
            previous.outgoing_upper,
        ):
            _fail(f"psi chunk {index} breaks the interval-state chain")
        if (
            chunk.scale_bits,
            chunk.series_terms,
        ) != (
            first.scale_bits,
            first.series_terms,
        ):
            _fail(f"psi chunk {index} changes numerical constants")
        count, _, _ = verify_psi_chunk(chunk, segment_size=segment_size)
        total_events += count
        chunk_count += 1
        previous = chunk

    if previous.upper != expected_limit + 1:
        _fail("psi certificate does not end immediately after expected_limit")
    # The lower envelope is strict at the closed terminal point.  At all
    # earlier event left limits a non-strict inequality suffices because that
    # endpoint belongs to the following jump, while values inside the open
    # constant slab are strictly smaller.
    scale = 1 << first.scale_bits
    terminal_difference = expected_limit * scale - previous.outgoing_lower
    if (
        terminal_difference > 0
        and terminal_difference * terminal_difference
        >= 2 * expected_limit * scale * scale
    ):
        _fail("strict lower psi envelope fails at the terminal point")

    return PsiVerification(
        limit=expected_limit,
        chunks=chunk_count,
        events=total_events,
        final_lower=previous.outgoing_lower,
        final_upper=previous.outgoing_upper,
        final_hash=previous.record_hash,
        exact_prime_power_coverage_verified=True,
        rational_log_enclosures_verified=True,
        exact_envelope_inequalities_verified=True,
        full_source_range=expected_limit == PSI_SOURCE_LIMIT,
    )


def iter_psi_certificate(
    limit: int,
    *,
    chunk_span: int = 1_000_000,
    scale_bits: int = 128,
    series_terms: int = 48,
    segment_size: int = 1_000_000,
) -> Iterator[PsiChunk]:
    """Yield a bounded-memory certificate stream.

    With ``limit=10**13`` this is a literal full-range algorithm, but its
    event count makes the current Python implementation computationally
    prohibitive.  Only one chunk is retained by this generator at a time.
    """

    limit = _int("limit", limit, minimum=2)
    chunk_span = _int("chunk_span", chunk_span, minimum=1)
    lower = 2
    incoming_lower = 0
    incoming_upper = 0
    previous_hash = ZERO_SHA256
    while lower <= limit:
        upper = min(limit + 1, lower + chunk_span)
        chunk = create_psi_chunk(
            lower=lower,
            upper=upper,
            scale_bits=scale_bits,
            series_terms=series_terms,
            incoming_lower=incoming_lower,
            incoming_upper=incoming_upper,
            previous_hash=previous_hash,
            segment_size=segment_size,
        )
        yield chunk
        lower = upper
        incoming_lower = chunk.outgoing_lower
        incoming_upper = chunk.outgoing_upper
        previous_hash = chunk.record_hash


def create_psi_certificate(
    limit: int,
    *,
    chunk_span: int = 1_000_000,
    scale_bits: int = 128,
    series_terms: int = 48,
    segment_size: int = 1_000_000,
) -> tuple[PsiChunk, ...]:
    """Materialize a bounded certificate for tests and small retained runs.

    Use :func:`iter_psi_certificate` for a production stream.  Calling this
    tuple wrapper at the ``10^13`` source limit is not bounded-memory.
    """

    return tuple(
        iter_psi_certificate(
            limit,
            chunk_span=chunk_span,
            scale_bits=scale_bits,
            series_terms=series_terms,
            segment_size=segment_size,
        )
    )


# ---------------------------------------------------------------------------
# Proposition 12.2.4 structural checker


def prop1224_first_extension_q() -> int:
    return PROP1224_Q_SPLIT + (-PROP1224_Q_SPLIT) % PROP1224_DIVISOR


def prop1224_q_is_admissible(q: int) -> bool:
    q = _int("q", q, minimum=1)
    return q < PROP1224_Q_SPLIT or (
        q < PROP1224_Q_END and q % PROP1224_DIVISOR == 0
    )


def prop1224_next_q(q: int) -> int:
    """Return the exact next admissible q, or ``PROP1224_Q_END`` sentinel."""

    q = _int("q", q, minimum=1)
    if not prop1224_q_is_admissible(q):
        _fail(f"q={q} is not in the Proposition 12.2.4 source range")
    if q < PROP1224_Q_SPLIT - 1:
        return q + 1
    if q < PROP1224_Q_SPLIT:
        return prop1224_first_extension_q()
    candidate = q + PROP1224_DIVISOR
    return candidate if candidate < PROP1224_Q_END else PROP1224_Q_END


def prop1224_source_q_count() -> int:
    first = prop1224_first_extension_q()
    extension = (PROP1224_Q_END - 1 - first) // PROP1224_DIVISOR + 1
    return PROP1224_Q_SPLIT - 1 + extension


def _totients_through(limit: int) -> list[int]:
    limit = _int("limit", limit, minimum=0)
    phi = list(range(limit + 1))
    if limit >= 1:
        phi[1] = 1
    for prime in range(2, limit + 1):
        if phi[prime] != prime:
            continue
        for multiple in range(prime, limit + 1, prime):
            phi[multiple] -= phi[multiple] // prime
    return phi


def ramare_g_prefixes(q: int, ks: Iterable[int]) -> dict[int, Fraction]:
    """Recompute the exact finite ``G_q(k)`` values requested by ``ks``."""

    q = _int("q", q, minimum=1)
    if isinstance(ks, (str, bytes, bytearray)):
        _fail("requested k values must be an integer iterable")
    requested_list: list[int] = []
    try:
        for index, k in enumerate(ks):
            if index >= _MAX_HASHED_ROWS:
                _fail("requested k sequence exceeds the local row safety limit")
            requested_list.append(_int("k", k, minimum=1))
    except TypeError as error:
        raise FiniteCampaignError(
            "requested k values must be an integer iterable"
        ) from error
    requested = tuple(requested_list)
    if not requested:
        return {}
    if tuple(sorted(set(requested))) != requested:
        _fail("requested k values must be strictly increasing")
    limit = requested[-1]
    if limit > _MAX_HASHED_ROWS:
        _fail("largest requested k exceeds the local arithmetic safety limit")
    mu = mobius_linear(limit)
    phi = _totients_through(limit)
    wanted = set(requested)
    result: dict[int, Fraction] = {}
    total = Fraction(0)
    for r in range(1, limit + 1):
        if mu[r] != 0 and gcd(r, q) == 1:
            total += Fraction(1, phi[r])
        if r in wanted:
            result[r] = total
    return result


@dataclass(frozen=True)
class Prop1224Pair:
    """One structurally checked k row.

    ``margin_lower`` is merely a supplied rational lower endpoint.  Its
    nonnegativity is checked, but this module does not establish that it
    encloses the source transcendental expression.
    """

    k: int
    g_numerator: int
    g_denominator: int
    margin_lower_numerator: int
    margin_lower_denominator: int

    def body(self) -> list[int]:
        return [
            self.k,
            self.g_numerator,
            self.g_denominator,
            self.margin_lower_numerator,
            self.margin_lower_denominator,
        ]


@dataclass(frozen=True)
class Prop1224Window:
    """A conservative k-window for one admissible q."""

    q: int
    varpi_lower_numerator: int
    varpi_lower_denominator: int
    varpi_upper_numerator: int
    varpi_upper_denominator: int
    lambda_lower_numerator: int
    lambda_lower_denominator: int
    lambda_upper_numerator: int
    lambda_upper_denominator: int
    pairs: tuple[Prop1224Pair, ...]

    def body(self) -> dict[str, object]:
        return {
            "lambda": [
                self.lambda_lower_numerator,
                self.lambda_lower_denominator,
                self.lambda_upper_numerator,
                self.lambda_upper_denominator,
            ],
            "pairs": [pair.body() for pair in self.pairs],
            "q": self.q,
            "varpi": [
                self.varpi_lower_numerator,
                self.varpi_lower_denominator,
                self.varpi_upper_numerator,
                self.varpi_upper_denominator,
            ],
        }


def _window_bounds(
    window: Prop1224Window,
) -> tuple[Fraction, Fraction, Fraction, Fraction]:
    if not isinstance(window, Prop1224Window):
        _fail("window rows must be Prop1224Window values")
    varpi_lower = _fraction(
        "varpi_lower",
        window.varpi_lower_numerator,
        window.varpi_lower_denominator,
    )
    varpi_upper = _fraction(
        "varpi_upper",
        window.varpi_upper_numerator,
        window.varpi_upper_denominator,
    )
    lambda_lower = _fraction(
        "lambda_lower",
        window.lambda_lower_numerator,
        window.lambda_lower_denominator,
    )
    lambda_upper = _fraction(
        "lambda_upper",
        window.lambda_upper_numerator,
        window.lambda_upper_denominator,
    )
    if min(varpi_lower, lambda_lower) < 0:
        _fail("Proposition 12.2.4 window endpoints must be nonnegative")
    if varpi_lower > varpi_upper:
        _fail("varpi enclosure is reversed")
    if lambda_lower > lambda_upper:
        _fail("lambda enclosure is reversed")
    return varpi_lower, varpi_upper, lambda_lower, lambda_upper


def prop1224_conservative_ks(window: Prop1224Window) -> tuple[int, ...]:
    """Return a superset of all k in any represented true source window.

    If ``varpi`` lies in ``[v_lo,v_hi]`` and ``lambda`` lies in
    ``[l_lo,l_hi]``, then every integer satisfying
    ``varpi <= k < lambda`` lies in
    ``ceil(v_lo) <= k <= ceil(l_hi)-1``.  Checking this possibly larger range
    is safe conditional on the two supplied enclosures.
    """

    varpi_lower, _, _, lambda_upper = _window_bounds(window)
    first = max(1, _ceil(varpi_lower))
    last = _ceil(lambda_upper) - 1
    if last < first:
        return ()
    count = last - first + 1
    if count > _MAX_HASHED_ROWS:
        _fail(
            "conservative k window exceeds the local row safety limit; "
            "split or tighten the outward enclosure before materializing it"
        )
    return tuple(range(first, last + 1))


def create_prop1224_window(
    *,
    q: int,
    varpi_lower: Fraction,
    varpi_upper: Fraction,
    lambda_lower: Fraction,
    lambda_upper: Fraction,
    margin_lower: Mapping[int, Fraction] | Callable[[int], Fraction],
) -> Prop1224Window:
    """Create one structural row from caller-supplied directed enclosures.

    This constructor's name intentionally omits "verify": the caller remains
    responsible for the transcendental endpoint and margin semantics.
    """

    q = _int("q", q, minimum=1)
    if not prop1224_q_is_admissible(q):
        _fail("q is not admissible")
    for name, value in (
        ("varpi_lower", varpi_lower),
        ("varpi_upper", varpi_upper),
        ("lambda_lower", lambda_lower),
        ("lambda_upper", lambda_upper),
    ):
        if not isinstance(value, Fraction):
            _fail(f"{name} must be a Fraction")
    if not callable(margin_lower) and not isinstance(margin_lower, Mapping):
        _fail("margin_lower must be a mapping or callable")
    placeholder = Prop1224Window(
        q=q,
        varpi_lower_numerator=varpi_lower.numerator,
        varpi_lower_denominator=varpi_lower.denominator,
        varpi_upper_numerator=varpi_upper.numerator,
        varpi_upper_denominator=varpi_upper.denominator,
        lambda_lower_numerator=lambda_lower.numerator,
        lambda_lower_denominator=lambda_lower.denominator,
        lambda_upper_numerator=lambda_upper.numerator,
        lambda_upper_denominator=lambda_upper.denominator,
        pairs=(),
    )
    ks = prop1224_conservative_ks(placeholder)
    values = ramare_g_prefixes(q, ks)
    pairs: list[Prop1224Pair] = []
    for k in ks:
        if callable(margin_lower):
            margin = margin_lower(k)
        else:
            try:
                margin = margin_lower[k]
            except KeyError as error:
                raise FiniteCampaignError(
                    f"margin_lower is missing conservative-window k={k}"
                ) from error
        if not isinstance(margin, Fraction):
            _fail("margin lower endpoints must be Fractions")
        g_value = values[k]
        pairs.append(
            Prop1224Pair(
                k=k,
                g_numerator=g_value.numerator,
                g_denominator=g_value.denominator,
                margin_lower_numerator=margin.numerator,
                margin_lower_denominator=margin.denominator,
            )
        )
    return replace(placeholder, pairs=tuple(pairs))


def verify_prop1224_window(window: Prop1224Window) -> int:
    """Check q, conservative k coverage, exact G_q, and margin signs."""

    if not isinstance(window, Prop1224Window):
        _fail("window rows must be Prop1224Window values")
    q = _int("window.q", window.q, minimum=1)
    if not prop1224_q_is_admissible(q):
        _fail(f"q={q} is not admissible")
    if not isinstance(window.pairs, tuple):
        _fail(f"q={q} pairs must be stored as a tuple")
    for index, pair in enumerate(window.pairs):
        if not isinstance(pair, Prop1224Pair):
            _fail(f"q={q} pair {index} has the wrong type")
        _int(f"q={q} pair {index}.k", pair.k, minimum=1)
    expected_ks = prop1224_conservative_ks(window)
    if tuple(pair.k for pair in window.pairs) != expected_ks:
        _fail(f"q={q} does not cover its complete conservative k window")
    exact_g = ramare_g_prefixes(q, expected_ks)
    for pair in window.pairs:
        g_value = _fraction("G_q(k)", pair.g_numerator, pair.g_denominator)
        if g_value != exact_g[pair.k]:
            _fail(f"q={q}, k={pair.k} has an incorrect exact G_q(k)")
        margin = _fraction(
            "margin_lower",
            pair.margin_lower_numerator,
            pair.margin_lower_denominator,
        )
        if margin < 0:
            _fail(f"q={q}, k={pair.k} has a negative supplied margin lower bound")
    return len(expected_ks)


@dataclass(frozen=True)
class Prop1224Chunk:
    """A hash-linked consecutive sequence in the exact admissible-q order."""

    first_q: int
    next_q: int
    windows: tuple[Prop1224Window, ...]
    previous_hash: str
    record_hash: str

    def body(self) -> dict[str, object]:
        return {
            "algorithm": PROP1224_ALGORITHM,
            "atom": PROP1224_ATOM,
            "first_q": self.first_q,
            "next_q": self.next_q,
            "previous_hash": self.previous_hash,
            "semantics_status": PROP1224_SEMANTICS_STATUS,
            "windows": [window.body() for window in self.windows],
        }

    def recomputed_hash(self) -> str:
        return _sha256(self.body())


def rehash_prop1224_chunk(chunk: Prop1224Chunk) -> Prop1224Chunk:
    if not isinstance(chunk, Prop1224Chunk):
        _fail("chunk must be a Prop1224Chunk")
    if not isinstance(chunk.windows, tuple) or any(
        not isinstance(window, Prop1224Window) for window in chunk.windows
    ):
        _fail("chunk windows must be a tuple of Prop1224Window values")
    return replace(chunk, record_hash=chunk.recomputed_hash())


def create_prop1224_chunk(
    windows: Sequence[Prop1224Window], *, previous_hash: str = ZERO_SHA256
) -> Prop1224Chunk:
    if isinstance(windows, (str, bytes, bytearray)) or not windows:
        _fail("a Proposition 12.2.4 chunk must contain at least one q")
    for index, window in enumerate(windows):
        if not isinstance(window, Prop1224Window):
            _fail(f"window {index} has the wrong type")
    _digest("previous_hash", previous_hash)
    expected_q = windows[0].q
    for index, window in enumerate(windows):
        if window.q != expected_q:
            _fail(f"window {index} breaks admissible-q ordering")
        expected_q = prop1224_next_q(window.q)
    chunk = Prop1224Chunk(
        first_q=windows[0].q,
        next_q=expected_q,
        windows=tuple(windows),
        previous_hash=previous_hash,
        record_hash=ZERO_SHA256,
    )
    return rehash_prop1224_chunk(chunk)


def verify_prop1224_chunk(chunk: Prop1224Chunk) -> tuple[int, int]:
    if not isinstance(chunk, Prop1224Chunk):
        _fail("chain entries must be Prop1224Chunk values")
    _int("chunk.first_q", chunk.first_q, minimum=1)
    _int("chunk.next_q", chunk.next_q, minimum=1)
    _digest("chunk.previous_hash", chunk.previous_hash)
    _digest("chunk.record_hash", chunk.record_hash)
    if not isinstance(chunk.windows, tuple):
        _fail("Proposition 12.2.4 windows must be stored as a tuple")
    for index, window in enumerate(chunk.windows):
        if not isinstance(window, Prop1224Window):
            _fail(f"q row {index} has the wrong type")
        if not isinstance(window.pairs, tuple) or any(
            not isinstance(pair, Prop1224Pair) for pair in window.pairs
        ):
            _fail(f"q row {index} has malformed pair storage")
    if chunk.recomputed_hash() != chunk.record_hash:
        _fail("Proposition 12.2.4 chunk hash is incorrect")
    if not chunk.windows:
        _fail("Proposition 12.2.4 chunks may not be empty")
    if chunk.first_q != chunk.windows[0].q:
        _fail("chunk first_q does not match its first row")
    expected_q = chunk.first_q
    pairs = 0
    for index, window in enumerate(chunk.windows):
        if window.q != expected_q:
            _fail(f"q row {index} breaks exact scheduler coverage")
        pairs += verify_prop1224_window(window)
        expected_q = prop1224_next_q(window.q)
    if chunk.next_q != expected_q:
        _fail("chunk next_q does not match the exact scheduler")
    return len(chunk.windows), pairs


@dataclass(frozen=True)
class Prop1224Verification:
    first_q: int
    next_q: int
    chunks: int
    q_rows: int
    pairs: int
    final_hash: str
    exact_q_scheduler_coverage_verified: bool
    conservative_k_coverage_verified: bool
    exact_gq_arithmetic_verified: bool
    supplied_margin_nonnegativity_verified: bool
    transcendental_enclosure_semantics_verified: bool = False
    full_source_q_coverage: bool = False
    lean_atom_discharged: bool = False


def verify_prop1224_chain(
    chunks: Iterable[Prop1224Chunk],
    *,
    expected_first_q: int = 1,
    expected_next_q: int | None = None,
) -> Prop1224Verification:
    """Check exact structural coverage without upgrading analytic semantics."""

    if isinstance(chunks, (str, bytes, bytearray)):
        _fail("Proposition 12.2.4 certificate must be a chunk iterable")
    expected_first_q = _int("expected_first_q", expected_first_q, minimum=1)
    if expected_next_q is not None:
        expected_next_q = _int(
            "expected_next_q", expected_next_q, minimum=1
        )
    try:
        iterator = iter(chunks)
        first = next(iterator)
    except TypeError as error:
        raise FiniteCampaignError(
            "Proposition 12.2.4 certificate must be a chunk iterable"
        ) from error
    except StopIteration:
        _fail("Proposition 12.2.4 certificate must have at least one chunk")
    if not isinstance(first, Prop1224Chunk):
        _fail("Proposition 12.2.4 chain entry 0 has the wrong type")
    if first.first_q != expected_first_q:
        _fail("certificate begins at the wrong q")
    if first.previous_hash != ZERO_SHA256:
        _fail("certificate has a nonzero initial predecessor hash")

    q_rows = 0
    pairs = 0
    chunk_count = 1
    chunk_rows, chunk_pairs = verify_prop1224_chunk(first)
    q_rows += chunk_rows
    pairs += chunk_pairs
    previous = first
    for index, chunk in enumerate(iterator, start=1):
        if not isinstance(chunk, Prop1224Chunk):
            _fail(f"Proposition 12.2.4 chain entry {index} has the wrong type")
        if chunk.first_q != previous.next_q:
            _fail(f"chunk {index} breaks q-range coverage")
        if chunk.previous_hash != previous.record_hash:
            _fail(f"chunk {index} breaks the hash chain")
        chunk_rows, chunk_pairs = verify_prop1224_chunk(chunk)
        q_rows += chunk_rows
        pairs += chunk_pairs
        chunk_count += 1
        previous = chunk
    if expected_next_q is not None and previous.next_q != expected_next_q:
        _fail("certificate ends at the wrong next-q state")

    full_source_q_coverage = (
        first.first_q == 1 and previous.next_q == PROP1224_Q_END
    )
    if full_source_q_coverage and q_rows != prop1224_source_q_count():
        _fail("full source q coverage has an inconsistent exact row count")

    return Prop1224Verification(
        first_q=first.first_q,
        next_q=previous.next_q,
        chunks=chunk_count,
        q_rows=q_rows,
        pairs=pairs,
        final_hash=previous.record_hash,
        exact_q_scheduler_coverage_verified=True,
        conservative_k_coverage_verified=True,
        exact_gq_arithmetic_verified=True,
        supplied_margin_nonnegativity_verified=True,
        full_source_q_coverage=full_source_q_coverage,
    )
