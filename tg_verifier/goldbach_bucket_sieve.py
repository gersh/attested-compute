# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independent exact model of the persistent Goldbach odd-prime sieve.

The CUDA runner uses a C++ circular-bucket scheduler and GPU atomics.  This
module deliberately reimplements the arithmetic in Python and supplies both a
persistent model and a stateless segmented replay.  It is a bounded KAT and
audit aid, not evidence for the full ``4 * 10**18`` campaign.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Iterable, Sequence


WORD_BITS = 64
WORD_MASK = (1 << WORD_BITS) - 1
MAX_SEGMENT_ODDS = 1 << 31


class GoldbachBucketSieveError(ValueError):
    """A range, base-prime table, or persistent-state invariant failed."""


def odd_primes_through(limit: int) -> tuple[int, ...]:
    """Return every odd prime at most ``limit`` by an exact finite sieve."""

    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise GoldbachBucketSieveError("prime limit must be a natural number")
    if limit < 3:
        return ()
    flags = bytearray(b"\x01") * ((limit - 1) // 2)
    for index in range(len(flags)):
        prime = 2 * index + 3
        if prime * prime > limit:
            break
        if not flags[index]:
            continue
        first = (prime * prime - 3) // 2
        flags[first::prime] = b"\x00" * (((len(flags) - 1 - first) // prime) + 1)
    return tuple(2 * index + 3 for index, flag in enumerate(flags) if flag)


def _validate_segment(odd_low: int, odd_count: int) -> None:
    if (
        isinstance(odd_low, bool)
        or not isinstance(odd_low, int)
        or odd_low < 1
        or odd_low % 2 == 0
    ):
        raise GoldbachBucketSieveError("odd_low must be a positive odd integer")
    if (
        isinstance(odd_count, bool)
        or not isinstance(odd_count, int)
        or not 1 <= odd_count <= MAX_SEGMENT_ODDS
    ):
        raise GoldbachBucketSieveError("odd_count is outside the reviewed bound")


def _validate_primes(primes: Sequence[int]) -> None:
    previous = 1
    for index, prime in enumerate(primes):
        if (
            isinstance(prime, bool)
            or not isinstance(prime, int)
            or prime < 3
            or prime % 2 == 0
            or prime <= previous
        ):
            raise GoldbachBucketSieveError(
                f"base prime {index} is not a strictly increasing odd integer"
            )
        previous = prime


def first_odd_composite(odd_low: int, prime: int) -> int:
    """First odd multiple of ``prime`` at least ``max(odd_low, prime**2)``."""

    quotient = (odd_low + prime - 1) // prime
    multiple = quotient * prime
    if multiple % 2 == 0:
        multiple += prime
    return max(multiple, prime * prime)


def _initial_words(odd_count: int) -> list[int]:
    words = [WORD_MASK] * ((odd_count + WORD_BITS - 1) // WORD_BITS)
    tail = odd_count % WORD_BITS
    if tail:
        words[-1] &= (1 << tail) - 1
    return words


def _clear(words: list[int], offset: int) -> None:
    words[offset // WORD_BITS] &= ~(1 << (offset % WORD_BITS))


def stateless_odd_prime_words(
    odd_low: int, odd_count: int, odd_primes: Sequence[int]
) -> tuple[int, ...]:
    """Exact independent replay that recomputes every first multiple."""

    _validate_segment(odd_low, odd_count)
    _validate_primes(odd_primes)
    high = odd_low + 2 * odd_count
    words = _initial_words(odd_count)
    for prime in odd_primes:
        if prime * prime >= high:
            break
        for composite in range(
            first_odd_composite(odd_low, prime), high, 2 * prime
        ):
            _clear(words, (composite - odd_low) // 2)
    if odd_low == 1:
        _clear(words, 0)
    return tuple(words)


def trial_division_odd_prime_words(odd_low: int, odd_count: int) -> tuple[int, ...]:
    """Slow KAT oracle with no segmented-sieve or bucket state."""

    _validate_segment(odd_low, odd_count)
    words = [0] * ((odd_count + WORD_BITS - 1) // WORD_BITS)
    for offset in range(odd_count):
        value = odd_low + 2 * offset
        is_prime = value >= 2
        divisor = 3
        while is_prime and divisor * divisor <= value:
            if value % divisor == 0:
                is_prime = False
            divisor += 2
        if is_prime:
            words[offset // WORD_BITS] |= 1 << (offset % WORD_BITS)
    return tuple(words)


@dataclass(frozen=True)
class PersistentSegment:
    index: int
    odd_low: int
    words: tuple[int, ...]
    active_dense_primes: int
    sparse_events: int
    newly_activated_primes: int


class PersistentBucketOddSieve:
    """Exact Python replay of the hybrid dense/circular-bucket schedule."""

    def __init__(
        self,
        *,
        odd_low: int,
        odd_count: int,
        segments: int,
        odd_primes: Sequence[int],
    ) -> None:
        _validate_segment(odd_low, odd_count)
        if isinstance(segments, bool) or not isinstance(segments, int) or segments < 1:
            raise GoldbachBucketSieveError("segments must be a positive integer")
        _validate_primes(odd_primes)
        self._first_low = odd_low
        self._odd_count = odd_count
        self._segments = segments
        self._primes = tuple(odd_primes)
        base_limit = self._primes[-1] if self._primes else 1
        self._ring_size = base_limit // odd_count + 3
        if self._ring_size > 1 << 24:
            raise GoldbachBucketSieveError(
                "bucket ring exceeds review bound; use a larger segment"
            )
        self._buckets: list[list[tuple[int, int]]] = [
            [] for _ in range(self._ring_size)
        ]
        self._dense: list[list[int]] = []
        self._activation_index = 0
        self._next_segment = 0
        self._sparse_events = 0

    @property
    def ring_size(self) -> int:
        return self._ring_size

    @property
    def activated_prime_count(self) -> int:
        return self._activation_index

    @property
    def sparse_event_count(self) -> int:
        return self._sparse_events

    def next_segment(self) -> PersistentSegment:
        if self._next_segment >= self._segments:
            raise GoldbachBucketSieveError("all configured segments were emitted")
        segment = self._next_segment
        low = self._first_low + 2 * self._odd_count * segment
        high = low + 2 * self._odd_count
        activated_before = self._activation_index

        while self._activation_index < len(self._primes):
            prime = self._primes[self._activation_index]
            if prime * prime >= high:
                break
            self._activation_index += 1
            offset = (first_odd_composite(low, prime) - low) // 2
            if prime <= self._odd_count:
                if offset >= self._odd_count:
                    raise GoldbachBucketSieveError(
                        "new dense prime missed its activation segment"
                    )
                self._dense.append([prime, offset])
            else:
                delta, bucket_offset = divmod(offset, self._odd_count)
                if delta >= self._ring_size:
                    raise GoldbachBucketSieveError(
                        "new sparse event escaped the bucket horizon"
                    )
                target = segment + delta
                if target < self._segments:
                    self._buckets[target % self._ring_size].append(
                        (prime, bucket_offset)
                    )

        words = _initial_words(self._odd_count)
        for state in self._dense:
            prime, offset = state
            while offset < self._odd_count:
                _clear(words, offset)
                offset += prime
            state[1] = offset - self._odd_count

        slot = segment % self._ring_size
        events = self._buckets[slot]
        self._buckets[slot] = []
        for prime, offset in events:
            if not (prime > self._odd_count and 0 <= offset < self._odd_count):
                raise GoldbachBucketSieveError("malformed sparse bucket event")
            _clear(words, offset)
            self._sparse_events += 1
            delta, next_offset = divmod(offset + prime, self._odd_count)
            if not 0 < delta < self._ring_size:
                raise GoldbachBucketSieveError(
                    "rescheduled sparse event escaped the bucket horizon"
                )
            target = segment + delta
            if target < self._segments:
                self._buckets[target % self._ring_size].append(
                    (prime, next_offset)
                )
        if low == 1:
            _clear(words, 0)
        self._next_segment += 1
        return PersistentSegment(
            index=segment,
            odd_low=low,
            words=tuple(words),
            active_dense_primes=len(self._dense),
            sparse_events=len(events),
            newly_activated_primes=self._activation_index - activated_before,
        )


def words_sha256_le(word_groups: Iterable[Sequence[int]]) -> str:
    """Hash packed words using the CUDA runner's canonical little-endian form."""

    digest = hashlib.sha256()
    for words in word_groups:
        for word in words:
            if isinstance(word, bool) or not isinstance(word, int) or not 0 <= word <= WORD_MASK:
                raise GoldbachBucketSieveError("packed value is not a uint64 word")
            digest.update(word.to_bytes(8, "little"))
    return digest.hexdigest()


def source_scale_work_model(*, segment_odds: int = 1 << 26) -> dict[str, int | float]:
    """Transparent operation/memory model for the ``4e18`` endpoint.

    Counts of base primes use the exact published integer ``pi(2e9)``.  Event
    counts use the explicitly labelled Mertens-sum approximation and are not
    completion evidence or a runtime certificate.
    """

    if (
        isinstance(segment_odds, bool)
        or not isinstance(segment_odds, int)
        or not 1 <= segment_odds <= MAX_SEGMENT_ODDS
    ):
        raise GoldbachBucketSieveError("source-model segment size is invalid")
    source_odd_candidates = 2_000_000_000_000_000_000
    base_limit = 2_000_000_000
    base_odd_prime_count = 98_222_286  # pi(2e9) - 1 (prime 2 is not stored)
    wheel_prime_count = 5  # 3, 5, 7, 11, 13
    scheduled_base_prime_count = base_odd_prime_count - wheel_prime_count
    if segment_odds == 1 << 26:
        # Exact pi(2^26) = 3,957,809, including prime 2.
        dense_scheduled_prime_count = 3_957_803
    else:
        # Only a sizing estimate off the reviewed default; no trust claim uses it.
        dense_scheduled_prime_count = max(
            0,
            round(segment_odds / math.log(max(segment_odds, 3)))
            - 1
            - wheel_prime_count,
        )
    sparse_scheduled_prime_count = (
        scheduled_base_prime_count - dense_scheduled_prime_count
    )
    loglog_difference = math.log(math.log(base_limit)) - math.log(
        math.log(max(segment_odds, 3))
    )
    wheel_survival_fraction = 5760 / 15015
    sparse_events_per_segment = (
        segment_odds * max(loglog_difference, 0.0) * wheel_survival_fraction
    )
    prime_reciprocal_constant = 0.2614972128476428
    small_prime_reciprocal_sum = sum(1 / prime for prime in (2, 3, 5, 7, 11, 13))
    dense_reciprocal_sum = max(
        0.0,
        math.log(math.log(max(segment_odds, 3)))
        + prime_reciprocal_constant
        - small_prime_reciprocal_sum,
    )
    dense_marks_per_segment = segment_odds * dense_reciprocal_sum
    composite_marks_per_segment = dense_marks_per_segment + sparse_events_per_segment
    return {
        "source_odd_candidates": source_odd_candidates,
        "base_limit": base_limit,
        "base_odd_prime_count": base_odd_prime_count,
        "scheduled_base_prime_count": scheduled_base_prime_count,
        "dense_scheduled_prime_count": dense_scheduled_prime_count,
        "sparse_scheduled_prime_count": sparse_scheduled_prime_count,
        "segment_odds": segment_odds,
        "segment_count": math.ceil(source_odd_candidates / segment_odds),
        "q_word_bytes": 8 * math.ceil(segment_odds / WORD_BITS),
        "base_prime_bytes": 4 * scheduled_base_prime_count,
        "dense_device_state_bytes": 12 * dense_scheduled_prime_count,
        "sparse_state_bytes_upper_bound": 12 * sparse_scheduled_prime_count,
        "wheel_survival_fraction": wheel_survival_fraction,
        "estimated_dense_marks_per_segment": dense_marks_per_segment,
        "estimated_sparse_events_per_segment": sparse_events_per_segment,
        "estimated_composite_marks_per_segment": composite_marks_per_segment,
        "estimated_total_composite_marks": (
            source_odd_candidates
            * (dense_reciprocal_sum
               + max(loglog_difference, 0.0) * wheel_survival_fraction)
        ),
        "estimated_total_candidate_byte_initializations": source_odd_candidates,
        "model_is_certificate": False,
    }


def source_scale_eta_model(
    *,
    measured_candidates: int,
    measured_pipeline_seconds: float,
    measured_host_seconds: float,
    measured_gpu_seconds: float,
    gpu_count: int = 8,
    gpu_speedup: float = 1.0,
) -> dict[str, int | float | bool]:
    """Project a clearly labelled sensitivity from one measured shard.

    Only the measured GPU portion receives ``gpu_speedup``.  Host scheduling
    and observed residual time remain unchanged.  This deliberately exposes
    the CPU floor instead of scaling the whole pipeline as if it were a kernel.
    """

    for name, value in (
        ("measured_pipeline_seconds", measured_pipeline_seconds),
        ("measured_host_seconds", measured_host_seconds),
        ("measured_gpu_seconds", measured_gpu_seconds),
        ("gpu_speedup", gpu_speedup),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise GoldbachBucketSieveError(f"{name} must be positive")
    if (
        isinstance(measured_candidates, bool)
        or not isinstance(measured_candidates, int)
        or measured_candidates <= 0
        or isinstance(gpu_count, bool)
        or not isinstance(gpu_count, int)
        or gpu_count <= 0
    ):
        raise GoldbachBucketSieveError("candidate and GPU counts must be positive integers")
    residual = measured_pipeline_seconds - measured_host_seconds - measured_gpu_seconds
    if residual < 0:
        raise GoldbachBucketSieveError("timing components exceed measured pipeline time")
    projected_seconds = (
        measured_host_seconds + measured_gpu_seconds / gpu_speedup + residual
    )
    per_gpu_rate = measured_candidates / projected_seconds
    source_candidates = 2_000_000_000_000_000_000
    wall_seconds = source_candidates / (gpu_count * per_gpu_rate)
    required_per_gpu_rate = source_candidates / (gpu_count * 7 * 24 * 3600)
    return {
        "gpu_count": gpu_count,
        "gpu_speedup_sensitivity": gpu_speedup,
        "projected_per_gpu_candidates_per_second": per_gpu_rate,
        "projected_wall_hours": wall_seconds / 3600,
        "projected_wall_years": wall_seconds / (365.25 * 24 * 3600),
        "one_week_required_per_gpu_candidates_per_second": required_per_gpu_rate,
        "one_week_rate_shortfall_factor": required_per_gpu_rate / per_gpu_rate,
        "projection_is_certificate": False,
    }
