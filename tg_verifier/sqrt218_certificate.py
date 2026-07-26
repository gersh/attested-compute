# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Deterministic producer for the complete finite Sqrt218 archive.

The output is untrusted certificate data.  It becomes useful only after the
separate implementation in :mod:`sqrt218_certificate_verifier` accepts every
row and recomputes the pinned production summaries.
"""

from __future__ import annotations

from array import array
import hashlib
import math
import os
from pathlib import Path
from typing import Any

from .sqrt218_contract import (
    BOUND,
    CERTIFICATE_KIND,
    EXPECTED_ANCHOR_SLACK,
    EXPECTED_FINAL_PSI_LOWER,
    EXPECTED_FINAL_WEIGHTED_UPPER,
    EXPECTED_FIXED_SHA256,
    EXPECTED_LAYOUT_SHA256,
    EXPECTED_MINIMUM_HEAD_N,
    EXPECTED_MINIMUM_HEAD_SLACK,
    EXPECTED_POWER_EVENT_COUNT,
    EXPECTED_PRATT_SHA256,
    EXPECTED_PRIME_COUNT,
    EXPECTED_PROPER_POWER_COUNT,
    EXPECTED_REUSED_PRIME_COUNT,
    EXPECTED_TAIL_PRIME_COUNT,
    LOG_SEED_AT,
    LOG_SEEDS_30,
    RECIPROCAL_SCALE,
    REUSED_BOUND,
    SCALE,
    SCHEMA_VERSION,
    canonical_json_bytes,
    require_replay_scope,
)


class Sqrt218ProducerError(RuntimeError):
    """The deterministic producer found an internal or pin mismatch."""


def _smallest_prime_factors(bound: int) -> array:
    factors = array("I", range(bound + 1))
    if bound >= 1:
        factors[1] = 1
    for prime in range(2, math.isqrt(bound) + 1):
        if factors[prime] != prime:
            continue
        for value in range(prime * prime, bound + 1, prime):
            if factors[value] == value:
                factors[value] = prime
    return factors


def _factorization(value: int, smallest: array) -> tuple[int, ...]:
    factors: list[int] = []
    while value > 1:
        factor = int(smallest[value])
        factors.append(factor)
        value //= factor
    return tuple(factors)


def _lucas_witness(prime: int, factors: tuple[int, ...]) -> int:
    if prime == 2:
        return 0
    distinct = tuple(dict.fromkeys(factors))
    for witness in range(2, prime):
        if pow(witness, prime - 1, prime) != 1:
            continue
        if all(
            pow(witness, (prime - 1) // factor, prime) != 1
            for factor in distinct
        ):
            return witness
    raise Sqrt218ProducerError(f"no Lucas witness for {prime}")


def _log_ladders(bound: int) -> tuple[array, array]:
    lower = array("Q", [0]) * (bound + 1)
    upper = array("Q", [0]) * (bound + 1)
    for value in range(1, min(bound, LOG_SEED_AT) + 1):
        lower[value], upper[value] = LOG_SEEDS_30[value - 1]
    for value in range(LOG_SEED_AT, bound):
        denominator = 2 * value * value * (value - 1)
        lower_increment = (
            SCALE * (2 * value * value - 3 * value - 1) // denominator
        )
        upper_increment = (
            SCALE * (2 * value * value - 3 * value + 3)
            + denominator
            - 1
        ) // denominator
        lower[value + 1] = lower[value] + lower_increment
        upper[value + 1] = upper[value] + upper_increment
    return lower, upper


def _power_layout(
    primes: tuple[int, ...], bound: int
) -> tuple[
    tuple[tuple[int, int, int], ...],
    tuple[int, ...],
    tuple[tuple[int, ...], ...],
]:
    unsorted: list[tuple[int, int, int]] = []
    per_prime: list[list[int]] = []
    for prime_index, prime in enumerate(primes):
        exponents: list[int] = []
        value = prime
        exponent = 1
        while value <= bound:
            unsorted.append((value, prime_index, exponent))
            exponents.append(exponent)
            if value > bound // prime:
                break
            value *= prime
            exponent += 1
        per_prime.append(exponents)
    events = tuple(sorted(unsorted))
    if any(left[0] >= right[0] for left, right in zip(events, events[1:])):
        raise Sqrt218ProducerError("prime-power values are not strictly increasing")
    inverse = {
        (prime_index, exponent): event_index
        for event_index, (_, prime_index, exponent) in enumerate(events)
    }
    if len(inverse) != len(events):
        raise Sqrt218ProducerError("prime-power layout contains a duplicate")
    counts = tuple(len(exponents) for exponents in per_prime)
    canonical = tuple(
        tuple(inverse[(prime_index, exponent)] for exponent in exponents)
        for prime_index, exponents in enumerate(per_prime)
    )
    return events, counts, canonical


def _ceil_div(numerator: int, denominator: int) -> int:
    return (numerator + denominator - 1) // denominator


def _reciprocal_lower(value: int, root: int) -> int:
    remainder = value - root * root
    return RECIPROCAL_SCALE * (2 * root) // (
        2 * root * root + remainder
    )


def _reciprocal_upper(value: int, root: int) -> int:
    remainder = value - root * root
    return _ceil_div(
        RECIPROCAL_SCALE * (4 * root * root + remainder),
        root * (4 * root * root + 3 * remainder),
    )


def _pratt_digest(prime_rows: list[list[Any]]) -> str:
    digest = hashlib.sha256()
    for prime, witness, factors, _lower, _upper in prime_rows:
        digest.update(
            f"{prime}:{witness}:{','.join(map(str, factors))}\n".encode("ascii")
        )
    return digest.hexdigest()


def _layout_digest(
    primes: tuple[int, ...],
    events: tuple[tuple[int, int, int], ...],
    counts: tuple[int, ...],
    canonical: tuple[tuple[int, ...], ...],
) -> str:
    digest = hashlib.sha256()
    for prime_index, prime in enumerate(primes):
        mapping = ",".join(map(str, canonical[prime_index]))
        digest.update(
            f"prime:{prime_index}:{prime}:count={counts[prime_index]}:"
            f"map={mapping}\n".encode("ascii")
        )
    for event_index, (value, prime_index, exponent) in enumerate(events):
        digest.update(
            f"event:{event_index}:{value}:{prime_index}:{exponent}:"
            f"sqrt={math.isqrt(value)}\n".encode("ascii")
        )
    return digest.hexdigest()


def _fixed_scan(
    bound: int,
    events: tuple[tuple[int, int, int], ...],
    primes: tuple[int, ...],
    lower: array,
    upper: array,
) -> dict[str, Any]:
    weighted = 0
    psi = 0
    minimum_slack: int | None = None
    minimum_n = 0
    event_index = 0
    digest = hashlib.sha256()
    for value in range(2, bound + 1):
        if event_index < len(events) and events[event_index][0] == value:
            _, prime_index, exponent = events[event_index]
            prime = primes[prime_index]
            root = math.isqrt(value)
            lower_log = int(lower[prime])
            upper_log = int(upper[prime])
            weighted += upper_log * _reciprocal_upper(value, root)
            psi += lower_log
            digest.update(
                f"event:{value}:{prime_index}:{exponent}:{lower_log}:"
                f"{upper_log}:{weighted}:{psi}\n".encode("ascii")
            )
            event_index += 1
        root = math.isqrt(value)
        slack = (
            2501 * root * SCALE * RECIPROCAL_SCALE
            - 1250 * weighted
        )
        if slack <= 0:
            raise Sqrt218ProducerError(f"head guard failed at {value}")
        if minimum_slack is None or slack < minimum_slack:
            minimum_slack = slack
            minimum_n = value
    if event_index != len(events):
        raise Sqrt218ProducerError("fixed scan did not consume every event")
    root = math.isqrt(bound)
    anchor_slack = (
        2501 * root * SCALE * RECIPROCAL_SCALE
        - 2500 * (weighted - psi * _reciprocal_lower(bound, root))
    )
    if anchor_slack <= 0 or minimum_slack is None:
        raise Sqrt218ProducerError("endpoint anchor guard failed")
    digest.update(
        f"final:{bound}:{weighted}:{psi}:{minimum_slack}:"
        f"{minimum_n}:{anchor_slack}\n".encode("ascii")
    )
    return {
        "anchor_slack": anchor_slack,
        "final_psi_lower": psi,
        "final_weighted_upper": weighted,
        "fixed_scan_sha256": digest.hexdigest(),
        "minimum_head_n": minimum_n,
        "minimum_head_slack": minimum_slack,
    }


def produce_certificate(
    bound: int,
    *,
    execution_context: str | None = None,
) -> dict[str, Any]:
    if isinstance(bound, bool) or not isinstance(bound, int) or not 2 <= bound <= BOUND:
        raise Sqrt218ProducerError(f"bound must be an integer in [2,{BOUND}]")
    try:
        require_replay_scope(bound, execution_context=execution_context)
    except ValueError as error:
        raise Sqrt218ProducerError(str(error)) from error
    smallest = _smallest_prime_factors(bound)
    primes = tuple(
        value for value in range(2, bound + 1) if smallest[value] == value
    )
    lower, upper = _log_ladders(bound)
    prime_rows: list[list[Any]] = []
    for prime in primes:
        factors = () if prime == 2 else _factorization(prime - 1, smallest)
        witness = _lucas_witness(prime, factors)
        prime_rows.append(
            [
                prime,
                witness,
                list(factors),
                int(lower[prime]),
                int(upper[prime]),
            ]
        )
    events, counts, canonical = _power_layout(primes, bound)
    summary = _fixed_scan(bound, events, primes, lower, upper)
    summary.update(
        {
            "layout_sha256": _layout_digest(
                primes, events, counts, canonical
            ),
            "power_event_count": len(events),
            "pratt_sha256": _pratt_digest(prime_rows),
            "prime_count": len(primes),
            "proper_power_count": len(events) - len(primes),
            "reused_prime_count": sum(
                prime <= min(bound, REUSED_BOUND) for prime in primes
            ),
            "tail_prime_count": sum(
                REUSED_BOUND < prime <= bound for prime in primes
            ),
        }
    )
    if bound == BOUND:
        expected = {
            "anchor_slack": EXPECTED_ANCHOR_SLACK,
            "final_psi_lower": EXPECTED_FINAL_PSI_LOWER,
            "final_weighted_upper": EXPECTED_FINAL_WEIGHTED_UPPER,
            "fixed_scan_sha256": EXPECTED_FIXED_SHA256,
            "layout_sha256": EXPECTED_LAYOUT_SHA256,
            "minimum_head_n": EXPECTED_MINIMUM_HEAD_N,
            "minimum_head_slack": EXPECTED_MINIMUM_HEAD_SLACK,
            "power_event_count": EXPECTED_POWER_EVENT_COUNT,
            "pratt_sha256": EXPECTED_PRATT_SHA256,
            "prime_count": EXPECTED_PRIME_COUNT,
            "proper_power_count": EXPECTED_PROPER_POWER_COUNT,
            "reused_prime_count": EXPECTED_REUSED_PRIME_COUNT,
            "tail_prime_count": EXPECTED_TAIL_PRIME_COUNT,
        }
        if summary != expected:
            differing = {
                key: {"actual": summary.get(key), "expected": value}
                for key, value in expected.items()
                if summary.get(key) != value
            }
            raise Sqrt218ProducerError(
                f"production semantic pins changed: {differing}"
            )
    return {
        "bound": bound,
        "events": [list(event) for event in events],
        "kind": CERTIFICATE_KIND,
        "log_seed_at": LOG_SEED_AT,
        "log_scale": SCALE,
        "primes": prime_rows,
        "reciprocal_scale": RECIPROCAL_SCALE,
        "schema_version": SCHEMA_VERSION,
        "summary": summary,
    }


def produce_certificate_bytes(
    bound: int,
    *,
    execution_context: str | None = None,
) -> bytes:
    return canonical_json_bytes(
        produce_certificate(bound, execution_context=execution_context)
    )


def write_certificate(
    path: Path,
    bound: int,
    *,
    execution_context: str | None = None,
) -> dict[str, Any]:
    raw = produce_certificate_bytes(
        bound,
        execution_context=execution_context,
    )
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        descriptor = path.open("xb")
    except OSError as error:
        raise Sqrt218ProducerError(
            f"certificate output must be fresh: {path}: {error}"
        ) from error
    with descriptor:
        descriptor.write(raw)
        descriptor.flush()
        os.fsync(descriptor.fileno())
    return {
        "bound": bound,
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }
