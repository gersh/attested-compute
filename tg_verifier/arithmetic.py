# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded, exact CPU references for ternary-Goldbach arithmetic jobs.

This module supplies small, auditable reference operations that can be used to
test future CPU or GPU implementations.  All inequalities are reduced to
integer or :class:`fractions.Fraction` comparisons; native floating-point
arithmetic is intentionally absent.

The routines only check the finite range explicitly passed to them.  A
successful sample result is not evidence that one of the much larger source
ranges has been covered.  Likewise, the hash-linked chunk format detects
accidental mutation and broken ordering but is neither a digital signature nor
a proof that a payload was computed correctly.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
import hashlib
import json
from math import isqrt
import re


# These atom and verifier identifiers match the checked catalog.  The two
# little-Mertens claims intentionally share one arithmetic stream algorithm.
CDEM_SQUAREFREE_ATOM = "cdem-squarefree"
CDEM_ABEL_ATOM = "cdem-table-abel"
HURST_MERTENS_ATOM = "mertens-hurst"
RAMARE_ZUNIGA_R2STAR_ATOM = "ramare-zuniga-lemma-6-2"
PLATT_2_11_ATOM = "platt-little-mertens-2-11"
PLATT_STRONGER_ATOM = "platt-little-mertens-stronger"

CDEM_SQUAREFREE_ALGORITHM = "squarefree_real_endpoint_stream_v1"
CDEM_ABEL_ALGORITHM = "cdem_abel_exact_scan_v1"
HURST_MERTENS_ALGORITHM = "mertens_exact_squared_stream_v1"
RAMARE_ZUNIGA_R2STAR_ALGORITHM = "r2star_fixed_point_stream_v1"
PLATT_2_11_ALGORITHM = "little_mertens_fixed_point_stream_v1"
PLATT_STRONGER_ALGORITHM = "little_mertens_fixed_point_stream_v1"

ARITHMETIC_ATOMS = (
    CDEM_SQUAREFREE_ATOM,
    CDEM_ABEL_ATOM,
    HURST_MERTENS_ATOM,
    RAMARE_ZUNIGA_R2STAR_ATOM,
    PLATT_2_11_ATOM,
    PLATT_STRONGER_ATOM,
)

HURST_NUMERATOR = 571
HURST_DENOMINATOR = 1_000
CHUNK_SCHEMA_VERSION = 1
ZERO_SHA256 = "0" * 64
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _require_int(name: str, value: object, *, minimum: int | None = None) -> int:
    """Return ``value`` as an integer, rejecting booleans and bad bounds."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _require_fraction(name: str, value: object) -> Fraction:
    """Accept only exact integer/rational inputs; in particular reject float."""

    if isinstance(value, bool):
        raise TypeError(f"{name} must be an int or Fraction")
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value)
    raise TypeError(f"{name} must be an int or Fraction")


def _validate_mu_table(mu: Sequence[int], through: int) -> None:
    """Validate the portion of an inclusive Möbius table that will be read."""

    through = _require_int("through", through, minimum=0)
    if len(mu) <= through:
        raise ValueError(
            f"Möbius table ends at {len(mu) - 1}, but index {through} is needed"
        )
    if not mu:
        raise ValueError("Möbius table must contain mu(0)")
    if isinstance(mu[0], bool) or mu[0] != 0:
        raise ValueError("Möbius table must use mu(0) = 0")
    for index in range(1, through + 1):
        coefficient = mu[index]
        if (
            isinstance(coefficient, bool)
            or not isinstance(coefficient, int)
            or coefficient not in (-1, 0, 1)
        ):
            raise ValueError(
                f"invalid Möbius coefficient mu({index})={coefficient!r}"
            )


def _primes_through(limit: int) -> list[int]:
    """Return the primes at most ``limit`` by an exact Eratosthenes sieve."""

    limit = _require_int("limit", limit, minimum=0)
    if limit < 2:
        return []
    composite = bytearray(limit + 1)
    for prime in range(2, isqrt(limit) + 1):
        if composite[prime]:
            continue
        start = prime * prime
        composite[start : limit + 1 : prime] = b"\x01" * (
            ((limit - start) // prime) + 1
        )
    return [number for number in range(2, limit + 1) if not composite[number]]


def mobius_linear(limit: int) -> list[int]:
    """Return ``mu(0), ..., mu(limit)`` using a deterministic linear sieve.

    The caller chooses the finite bound and is responsible for keeping it
    suitable for a host-side reference run.
    """

    limit = _require_int("limit", limit, minimum=0)
    mu = [0] * (limit + 1)
    if limit == 0:
        return mu

    composite = bytearray(limit + 1)
    primes: list[int] = []
    mu[1] = 1
    for number in range(2, limit + 1):
        if not composite[number]:
            primes.append(number)
            mu[number] = -1
        for prime in primes:
            product = number * prime
            if product > limit:
                break
            composite[product] = 1
            if number % prime == 0:
                mu[product] = 0
                break
            mu[product] = -mu[number]
    return mu


def mobius_segment(start: int, stop: int) -> list[int]:
    """Return exact Möbius values on the half-open interval ``[start, stop)``.

    This segmented implementation stores only the requested interval plus the
    base-prime sieve through ``sqrt(stop - 1)``.  It is intended for bounded
    cross-checks, not as a claim about production-scale feasibility.
    """

    start = _require_int("start", start, minimum=1)
    stop = _require_int("stop", stop, minimum=1)
    if stop < start:
        raise ValueError("stop must not be less than start")
    if stop == start:
        return []

    remaining = list(range(start, stop))
    values = [1] * (stop - start)
    for prime in _primes_through(isqrt(stop - 1)):
        first = ((start + prime - 1) // prime) * prime
        for number in range(first, stop, prime):
            offset = number - start
            # Remove one distinct prime and flip parity.  A second copy proves
            # that the original number was not squarefree.
            remaining[offset] //= prime
            if values[offset] != 0:
                values[offset] = -values[offset]
            if remaining[offset] % prime == 0:
                values[offset] = 0
                while remaining[offset] % prime == 0:
                    remaining[offset] //= prime

    # After removing all base primes, a residual greater than one is one
    # additional prime factor (there cannot be two above sqrt(stop - 1)).
    for offset, residual in enumerate(remaining):
        if residual > 1 and values[offset] != 0:
            values[offset] = -values[offset]
    return values


def hurst_squared_slack(n: int, mertens: int) -> int:
    """Return exact slack for ``|M(n)| <= 0.571 * sqrt(n)``.

    For nonnegative ``n`` the source inequality is equivalent to

    ``571^2 * n - 1000^2 * M(n)^2 >= 0``.
    """

    n = _require_int("n", n, minimum=0)
    mertens = _require_int("mertens", mertens)
    return (
        HURST_NUMERATOR * HURST_NUMERATOR * n
        - HURST_DENOMINATOR * HURST_DENOMINATOR * mertens * mertens
    )


def check_hurst_squared(n: int, mertens: int) -> bool:
    """Check Hurst's square-root inequality by the exact squared predicate."""

    return hurst_squared_slack(n, mertens) >= 0


@dataclass(frozen=True)
class HurstSampleResult:
    """Result of checking a caller-selected finite integer sample."""

    lower: int
    upper: int
    checks: int
    final_mertens: int
    minimum_slack: int
    minimum_slack_at: int
    first_failure: int | None

    @property
    def passed(self) -> bool:
        return self.first_failure is None


def check_hurst_sample(
    mu: Sequence[int], lower: int, upper: int
) -> HurstSampleResult:
    """Check the exact Hurst predicate at every integer in ``[lower, upper]``."""

    lower = _require_int("lower", lower, minimum=1)
    upper = _require_int("upper", upper, minimum=1)
    if upper < lower:
        raise ValueError("upper must not be less than lower")
    _validate_mu_table(mu, upper)

    mertens = 0
    minimum_slack: int | None = None
    minimum_slack_at: int | None = None
    first_failure: int | None = None
    for n in range(1, upper + 1):
        mertens += mu[n]
        if n < lower:
            continue
        slack = hurst_squared_slack(n, mertens)
        if minimum_slack is None or slack < minimum_slack:
            minimum_slack = slack
            minimum_slack_at = n
        if slack < 0 and first_failure is None:
            first_failure = n

    if minimum_slack is None or minimum_slack_at is None:
        raise RuntimeError("nonempty Hurst range produced no minimum")
    return HurstSampleResult(
        lower=lower,
        upper=upper,
        checks=upper - lower + 1,
        final_mertens=mertens,
        minimum_slack=minimum_slack,
        minimum_slack_at=minimum_slack_at,
        first_failure=first_failure,
    )


class LittleMertensBound(str, Enum):
    """The two finite real-variable little-Mertens source bounds."""

    SQRT_TWO_OVER_X = "sqrt_two_over_x"
    ONE_OVER_TWO_SQRT_X = "one_over_two_sqrt_x"


def little_mertens_prefix_sums(mu: Sequence[int]) -> list[Fraction]:
    """Return exact ``sum_{1 <= k <= n} mu(k)/k`` for every table index."""

    if not mu:
        raise ValueError("Möbius table must contain mu(0)")
    _validate_mu_table(mu, len(mu) - 1)
    result = [Fraction(0)] * len(mu)
    state = Fraction(0)
    for n in range(1, len(mu)):
        state += Fraction(mu[n], n)
        result[n] = state
    return result


def little_mertens_interval_slack(
    partial_sum: Fraction | int,
    right_endpoint: int,
    bound: LittleMertensBound,
) -> Fraction:
    """Return exact squared slack on a constant-sum real interval.

    If the little-Mertens sum is constant with value ``s`` while ``x`` tends
    upward to the positive integer ``r``, the two source claims reduce to

    * ``2 - r*s^2 >= 0`` for ``|s| <= sqrt(2/x)``; and
    * ``1 - 4*r*s^2 >= 0`` for ``|s| <= 1/(2*sqrt(x))``.

    Using the right endpoint is essential: both right-hand sides decrease with
    ``x``.  The returned rational therefore checks the entire half-open slab,
    including its limiting endpoint inequality.
    """

    partial_sum = _require_fraction("partial_sum", partial_sum)
    right_endpoint = _require_int("right_endpoint", right_endpoint, minimum=1)
    if not isinstance(bound, LittleMertensBound):
        raise TypeError("bound must be a LittleMertensBound")
    square = partial_sum * partial_sum
    if bound is LittleMertensBound.SQRT_TWO_OVER_X:
        return Fraction(2) - right_endpoint * square
    return Fraction(1) - 4 * right_endpoint * square


def check_little_mertens_interval(
    partial_sum: Fraction | int,
    right_endpoint: int,
    bound: LittleMertensBound,
) -> bool:
    """Check one exact constant-sum real slab for the selected source bound."""

    return little_mertens_interval_slack(partial_sum, right_endpoint, bound) >= 0


@dataclass(frozen=True)
class LittleMertensSampleResult:
    """Exact report for one caller-selected closed real interval."""

    bound: LittleMertensBound
    lower: int
    upper: int
    slabs_checked: int
    final_sum: Fraction
    minimum_slack: Fraction
    minimum_slack_floor: int
    minimum_slack_right_endpoint: int
    first_failure_floor: int | None

    @property
    def passed(self) -> bool:
        return self.first_failure_floor is None


def check_little_mertens_sample(
    mu: Sequence[int],
    lower: int,
    upper: int,
    bound: LittleMertensBound,
) -> LittleMertensSampleResult:
    """Check a selected closed real interval using exact Möbius reciprocals.

    For every integer ``n < upper``, the sum with ``floor(x) = n`` is checked
    at the limiting right endpoint ``n + 1``.  At the final integer it is
    checked at ``upper`` itself.  Thus integer jumps and left limits are both
    represented; no floating-point square root is evaluated.
    """

    lower = _require_int("lower", lower, minimum=1)
    upper = _require_int("upper", upper, minimum=1)
    if upper < lower:
        raise ValueError("upper must not be less than lower")
    if not isinstance(bound, LittleMertensBound):
        raise TypeError("bound must be a LittleMertensBound")
    _validate_mu_table(mu, upper)

    state = Fraction(0)
    minimum_slack: Fraction | None = None
    minimum_floor: int | None = None
    minimum_right: int | None = None
    first_failure: int | None = None
    for n in range(1, upper + 1):
        state += Fraction(mu[n], n)
        if n < lower:
            continue
        right_endpoint = n + 1 if n < upper else n
        slack = little_mertens_interval_slack(state, right_endpoint, bound)
        if minimum_slack is None or slack < minimum_slack:
            minimum_slack = slack
            minimum_floor = n
            minimum_right = right_endpoint
        if slack < 0 and first_failure is None:
            first_failure = n

    if (
        minimum_slack is None
        or minimum_floor is None
        or minimum_right is None
    ):
        raise RuntimeError("nonempty little-Mertens range produced no minimum")
    return LittleMertensSampleResult(
        bound=bound,
        lower=lower,
        upper=upper,
        slabs_checked=upper - lower + 1,
        final_sum=state,
        minimum_slack=minimum_slack,
        minimum_slack_floor=minimum_floor,
        minimum_slack_right_endpoint=minimum_right,
        first_failure_floor=first_failure,
    )


def atan_inverse_bounds(q: int, last_index: int) -> tuple[Fraction, Fraction]:
    """Alternating-series enclosure for ``atan(1/q)``."""

    q = _require_int("q", q, minimum=2)
    last_index = _require_int("last_index", last_index, minimum=0)
    partial = sum(
        (
            Fraction(-1 if index % 2 else 1, (2 * index + 1) * q ** (2 * index + 1))
            for index in range(last_index + 1)
        ),
        Fraction(0),
    )
    next_term = Fraction(
        -1 if (last_index + 1) % 2 else 1,
        (2 * last_index + 3) * q ** (2 * last_index + 3),
    )
    next_partial = partial + next_term
    return min(partial, next_partial), max(partial, next_partial)


def machin_pi_bounds() -> tuple[Fraction, Fraction]:
    """Enclose pi exactly using Machin's identity and alternating tails."""

    atan5_lower, atan5_upper = atan_inverse_bounds(5, 20)
    atan239_lower, atan239_upper = atan_inverse_bounds(239, 6)
    return (
        16 * atan5_lower - 4 * atan239_upper,
        16 * atan5_upper - 4 * atan239_lower,
    )


PI_LOWER, PI_UPPER = machin_pi_bounds()
SQUAREFREE_DENSITY_LOWER = Fraction(6) / (PI_UPPER * PI_UPPER)
SQUAREFREE_DENSITY_UPPER = Fraction(6) / (PI_LOWER * PI_LOWER)


class SquarefreeEndpointClassification(str, Enum):
    """Outcome of an interval-safe squarefree-density comparison."""

    SAFE = "safe"
    VIOLATION = "violation"
    UNRESOLVED = "unresolved"


def squarefree_prefix_counts(mu: Sequence[int]) -> list[int]:
    """Return inclusive exact counts of squarefree positive integers."""

    if not mu:
        raise ValueError("Möbius table must contain mu(0)")
    _validate_mu_table(mu, len(mu) - 1)
    counts = [0] * len(mu)
    count = 0
    for n in range(1, len(mu)):
        if mu[n] != 0:
            count += 1
        counts[n] = count
    return counts


def squarefree_endpoint_slack_bounds(
    squarefree_count: int,
    y: int,
    bound: Fraction | int,
) -> tuple[Fraction, Fraction]:
    """Return lower/upper exact slack bounds at one real endpoint.

    The claim is ``|Q - (6/pi^2)y| <= bound*sqrt(y)``.  The Machin enclosure
    yields an interval for the absolute error; squaring it gives an interval
    for the slack ``bound^2*y - error^2``.
    """

    squarefree_count = _require_int(
        "squarefree_count", squarefree_count, minimum=0
    )
    y = _require_int("y", y, minimum=1)
    bound = _require_fraction("bound", bound)
    if bound < 0:
        raise ValueError("bound must be nonnegative")

    difference_lower = (
        Fraction(squarefree_count) - SQUAREFREE_DENSITY_UPPER * y
    )
    difference_upper = (
        Fraction(squarefree_count) - SQUAREFREE_DENSITY_LOWER * y
    )
    if difference_lower > difference_upper:
        raise RuntimeError("squarefree-density enclosure is reversed")
    if difference_lower <= 0 <= difference_upper:
        absolute_lower = Fraction(0)
    else:
        absolute_lower = min(abs(difference_lower), abs(difference_upper))
    absolute_upper = max(abs(difference_lower), abs(difference_upper))
    rhs_square = bound * bound * y
    return (
        rhs_square - absolute_upper * absolute_upper,
        rhs_square - absolute_lower * absolute_lower,
    )


def classify_squarefree_endpoint(
    squarefree_count: int,
    y: int,
    bound: Fraction | int,
) -> SquarefreeEndpointClassification:
    """Classify one endpoint using only exact rational comparisons."""

    slack_lower, slack_upper = squarefree_endpoint_slack_bounds(
        squarefree_count, y, bound
    )
    if slack_lower >= 0:
        return SquarefreeEndpointClassification.SAFE
    if slack_upper < 0:
        return SquarefreeEndpointClassification.VIOLATION
    return SquarefreeEndpointClassification.UNRESOLVED


@dataclass(frozen=True)
class SquarefreeSampleResult:
    """Exact report for a caller-selected real squarefree-density sample."""

    lower: int
    upper: int
    bound: Fraction
    final_squarefree_count: int
    endpoints_checked: int
    safe_endpoints: int
    violating_endpoints: int
    unresolved_endpoints: int
    minimum_lower_slack: Fraction
    minimum_lower_slack_at: tuple[int, str]
    first_problem: tuple[int, str] | None

    @property
    def passed(self) -> bool:
        return self.violating_endpoints == 0 and self.unresolved_endpoints == 0


def check_squarefree_sample(
    mu: Sequence[int], lower: int, upper: int, bound: Fraction | int
) -> SquarefreeSampleResult:
    """Check both endpoint regimes on the closed real interval given.

    On ``[n, n+1)`` the squarefree count is ``Q(n)``.  The squared normalized
    error is convex there, so the integer endpoint and the left limit at the
    next integer suffice.  The final integer is included, but no point above
    ``upper`` is checked.
    """

    lower = _require_int("lower", lower, minimum=1)
    upper = _require_int("upper", upper, minimum=1)
    if upper < lower:
        raise ValueError("upper must not be less than lower")
    bound = _require_fraction("bound", bound)
    if bound < 0:
        raise ValueError("bound must be nonnegative")
    _validate_mu_table(mu, upper)

    count = 0
    checked = 0
    safe = 0
    violations = 0
    unresolved = 0
    first_problem: tuple[int, str] | None = None
    minimum_lower_slack: Fraction | None = None
    minimum_at: tuple[int, str] | None = None
    for n in range(1, upper + 1):
        if mu[n] != 0:
            count += 1
        if n < lower:
            continue
        endpoints = [(n, "at_integer")]
        if n < upper:
            endpoints.append((n + 1, "left_limit"))
        for y, side in endpoints:
            checked += 1
            slack_lower, slack_upper = squarefree_endpoint_slack_bounds(
                count, y, bound
            )
            if minimum_lower_slack is None or slack_lower < minimum_lower_slack:
                minimum_lower_slack = slack_lower
                minimum_at = (y, side)
            if slack_lower >= 0:
                safe += 1
            elif slack_upper < 0:
                violations += 1
                if first_problem is None:
                    first_problem = (y, side)
            else:
                unresolved += 1
                if first_problem is None:
                    first_problem = (y, side)

    if minimum_lower_slack is None or minimum_at is None:
        raise RuntimeError("nonempty squarefree range produced no minimum")
    return SquarefreeSampleResult(
        lower=lower,
        upper=upper,
        bound=bound,
        final_squarefree_count=count,
        endpoints_checked=checked,
        safe_endpoints=safe,
        violating_endpoints=violations,
        unresolved_endpoints=unresolved,
        minimum_lower_slack=minimum_lower_slack,
        minimum_lower_slack_at=minimum_at,
        first_problem=first_problem,
    )


class ChunkVerificationError(ValueError):
    """Raised when a chunk record or hash-linked chain fails closed."""


def sha256_bytes(payload: bytes) -> str:
    """Return the lowercase SHA-256 digest of a byte payload."""

    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    return hashlib.sha256(payload).hexdigest()


def _require_digest(name: str, digest: object) -> str:
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        raise ChunkVerificationError(
            f"{name} must be 64 lowercase hexadecimal characters"
        )
    return digest


def _integer_tuple(name: str, values: Iterable[int]) -> tuple[int, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError(f"{name} must be an iterable of integers")
    result = tuple(values)
    for value in result:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must contain only integers")
    return result


@dataclass(frozen=True)
class ChunkRecord:
    """A deterministic, exact-state, hash-linked half-open range record.

    State and summary tuples are deliberately algorithm-neutral integer words.
    An algorithm-specific layer can encode signed accumulators or rational
    endpoints as numerator/denominator pairs without introducing JSON floats.
    """

    schema_version: int
    algorithm: str
    lo: int
    hi: int
    constants_digest: str
    previous_hash: str
    incoming_state: tuple[int, ...]
    outgoing_state: tuple[int, ...]
    summary: tuple[int, ...]
    payload_digest: str
    record_hash: str

    def body(self) -> dict[str, object]:
        """Return the integer/string-only body committed by ``record_hash``."""

        return {
            "algorithm": self.algorithm,
            "constants_digest": self.constants_digest,
            "hi": self.hi,
            "incoming_state": list(self.incoming_state),
            "lo": self.lo,
            "outgoing_state": list(self.outgoing_state),
            "payload_digest": self.payload_digest,
            "previous_hash": self.previous_hash,
            "schema_version": self.schema_version,
            "summary": list(self.summary),
        }

    def canonical_body_bytes(self) -> bytes:
        """Serialize the committed body with one deterministic JSON encoding."""

        return json.dumps(
            self.body(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")

    def recomputed_hash(self) -> str:
        """Recompute the record hash from its canonical body."""

        return sha256_bytes(self.canonical_body_bytes())


def _validate_chunk_fields(record: ChunkRecord, *, check_hash: bool) -> None:
    if not isinstance(record, ChunkRecord):
        raise ChunkVerificationError("chain entries must be ChunkRecord values")
    try:
        schema_version = _require_int(
            "schema_version", record.schema_version, minimum=1
        )
    except (TypeError, ValueError) as error:
        raise ChunkVerificationError(str(error)) from error
    if schema_version != CHUNK_SCHEMA_VERSION:
        raise ChunkVerificationError(
            f"unsupported chunk schema version {record.schema_version!r}"
        )
    if not isinstance(record.algorithm, str) or not record.algorithm:
        raise ChunkVerificationError("algorithm must be a nonempty string")
    if len(record.algorithm.encode("utf-8")) > 256:
        raise ChunkVerificationError("algorithm identifier is too long")
    try:
        lo = _require_int("lo", record.lo, minimum=0)
        hi = _require_int("hi", record.hi, minimum=0)
        _integer_tuple("incoming_state", record.incoming_state)
        _integer_tuple("outgoing_state", record.outgoing_state)
        _integer_tuple("summary", record.summary)
    except (TypeError, ValueError) as error:
        raise ChunkVerificationError(str(error)) from error
    if hi <= lo:
        raise ChunkVerificationError("chunk range must be nonempty and half-open")
    _require_digest("constants_digest", record.constants_digest)
    _require_digest("previous_hash", record.previous_hash)
    _require_digest("payload_digest", record.payload_digest)
    _require_digest("record_hash", record.record_hash)
    if check_hash and record.recomputed_hash() != record.record_hash:
        raise ChunkVerificationError("record hash does not match canonical body")


def create_chunk_record(
    *,
    algorithm: str,
    lo: int,
    hi: int,
    incoming_state: Iterable[int],
    outgoing_state: Iterable[int],
    summary: Iterable[int] = (),
    constants: bytes = b"",
    payload: bytes = b"",
    previous_hash: str = ZERO_SHA256,
) -> ChunkRecord:
    """Create one validated deterministic chunk record from exact inputs."""

    if not isinstance(constants, bytes):
        raise TypeError("constants must be bytes")
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    record = ChunkRecord(
        schema_version=CHUNK_SCHEMA_VERSION,
        algorithm=algorithm,
        lo=lo,
        hi=hi,
        constants_digest=sha256_bytes(constants),
        previous_hash=previous_hash,
        incoming_state=_integer_tuple("incoming_state", incoming_state),
        outgoing_state=_integer_tuple("outgoing_state", outgoing_state),
        summary=_integer_tuple("summary", summary),
        payload_digest=sha256_bytes(payload),
        record_hash=ZERO_SHA256,
    )
    # Validate every field before hashing.  The placeholder hash itself is a
    # well-formed digest and is replaced immediately afterward.
    _validate_chunk_fields(record, check_hash=False)
    result = ChunkRecord(
        schema_version=record.schema_version,
        algorithm=record.algorithm,
        lo=record.lo,
        hi=record.hi,
        constants_digest=record.constants_digest,
        previous_hash=record.previous_hash,
        incoming_state=record.incoming_state,
        outgoing_state=record.outgoing_state,
        summary=record.summary,
        payload_digest=record.payload_digest,
        record_hash=record.recomputed_hash(),
    )
    _validate_chunk_fields(result, check_hash=True)
    return result


@dataclass(frozen=True)
class ChainVerification:
    """Coverage and final-state summary returned by a successful check."""

    algorithm: str
    lo: int
    hi: int
    chunks: int
    constants_digest: str
    final_state: tuple[int, ...]
    final_hash: str


def verify_chunk_chain(
    records: Sequence[ChunkRecord],
    *,
    payloads: Sequence[bytes] | None = None,
    expected_algorithm: str | None = None,
    expected_constants_digest: str | None = None,
    expected_lo: int | None = None,
    expected_hi: int | None = None,
    expected_initial_state: Iterable[int] | None = None,
    expected_final_state: Iterable[int] | None = None,
    expected_previous_hash: str = ZERO_SHA256,
) -> ChainVerification:
    """Validate hashes, payloads, coverage, and exact boundary-state links.

    Payload bytes are optional because a streaming verifier may validate them
    separately.  When supplied, their length and every SHA-256 commitment are
    checked.  This function does not interpret the payload's arithmetic.
    """

    if isinstance(records, (str, bytes, bytearray)) or not records:
        raise ChunkVerificationError("chunk chain must be a nonempty sequence")
    _require_digest("expected_previous_hash", expected_previous_hash)
    if expected_constants_digest is not None:
        _require_digest("expected_constants_digest", expected_constants_digest)
    if payloads is not None and len(payloads) != len(records):
        raise ChunkVerificationError("payload count does not match chunk count")
    if expected_lo is not None:
        try:
            expected_lo = _require_int("expected_lo", expected_lo, minimum=0)
        except (TypeError, ValueError) as error:
            raise ChunkVerificationError(str(error)) from error
    if expected_hi is not None:
        try:
            expected_hi = _require_int("expected_hi", expected_hi, minimum=0)
        except (TypeError, ValueError) as error:
            raise ChunkVerificationError(str(error)) from error
        if expected_lo is not None and expected_hi <= expected_lo:
            raise ChunkVerificationError("expected range must be nonempty")

    first = records[0]
    _validate_chunk_fields(first, check_hash=True)
    algorithm = first.algorithm
    constants_digest = first.constants_digest
    if expected_algorithm is not None and algorithm != expected_algorithm:
        raise ChunkVerificationError("first chunk has the wrong algorithm")
    if (
        expected_constants_digest is not None
        and constants_digest != expected_constants_digest
    ):
        raise ChunkVerificationError("first chunk has the wrong constants digest")
    if first.previous_hash != expected_previous_hash:
        raise ChunkVerificationError("first chunk has the wrong predecessor hash")
    if expected_lo is not None and first.lo != expected_lo:
        raise ChunkVerificationError("first chunk has the wrong lower endpoint")
    if expected_initial_state is not None and first.incoming_state != _integer_tuple(
        "expected_initial_state", expected_initial_state
    ):
        raise ChunkVerificationError("first chunk has the wrong incoming state")

    previous: ChunkRecord | None = None
    for index, record in enumerate(records):
        _validate_chunk_fields(record, check_hash=True)
        if record.algorithm != algorithm:
            raise ChunkVerificationError(f"chunk {index} changes algorithm")
        if record.constants_digest != constants_digest:
            raise ChunkVerificationError(f"chunk {index} changes constants")
        if payloads is not None:
            payload = payloads[index]
            if not isinstance(payload, bytes):
                raise ChunkVerificationError(f"payload {index} is not bytes")
            if sha256_bytes(payload) != record.payload_digest:
                raise ChunkVerificationError(f"payload {index} digest mismatch")
        if previous is not None:
            if record.previous_hash != previous.record_hash:
                raise ChunkVerificationError(f"chunk {index} breaks the hash link")
            if record.lo != previous.hi:
                raise ChunkVerificationError(f"chunk {index} breaks range coverage")
            if record.incoming_state != previous.outgoing_state:
                raise ChunkVerificationError(f"chunk {index} breaks the state link")
        previous = record

    if previous is None:
        raise ChunkVerificationError("chunk chain unexpectedly ended empty")
    if expected_hi is not None and previous.hi != expected_hi:
        raise ChunkVerificationError("last chunk has the wrong upper endpoint")
    if expected_final_state is not None and previous.outgoing_state != _integer_tuple(
        "expected_final_state", expected_final_state
    ):
        raise ChunkVerificationError("last chunk has the wrong outgoing state")
    return ChainVerification(
        algorithm=algorithm,
        lo=first.lo,
        hi=previous.hi,
        chunks=len(records),
        constants_digest=constants_digest,
        final_state=previous.outgoing_state,
        final_hash=previous.record_hash,
    )


def check_chunk_chain(
    records: Sequence[ChunkRecord], **kwargs: object
) -> bool:
    """Return ``False`` rather than raising when a chunk chain is malformed."""

    try:
        verify_chunk_chain(records, **kwargs)
    except (ChunkVerificationError, TypeError, ValueError):
        return False
    return True
