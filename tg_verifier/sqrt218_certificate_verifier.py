# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Independent replay of the canonical finite Sqrt218 archive.

This module intentionally does not import the producer.  It reconstructs the
prime roster with a different sieve representation, checks every supplied
Lucas/Pratt row, rebuilds every prime-power row and digest, independently
advances the log ladder, and reruns all two million fixed-point head guards.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import re
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
    VERIFICATION_KIND,
    canonical_json_bytes,
    parse_canonical_json,
    production_run_input,
    require_replay_scope,
    sha256_bytes,
)


MAX_CERTIFICATE_BYTES = 256 * 1024 * 1024
CERTIFICATE_FIELDS = {
    "bound",
    "events",
    "kind",
    "log_scale",
    "log_seed_at",
    "primes",
    "reciprocal_scale",
    "schema_version",
    "summary",
}
SUMMARY_FIELDS = {
    "anchor_slack",
    "final_psi_lower",
    "final_weighted_upper",
    "fixed_scan_sha256",
    "layout_sha256",
    "minimum_head_n",
    "minimum_head_slack",
    "power_event_count",
    "pratt_sha256",
    "prime_count",
    "proper_power_count",
    "reused_prime_count",
    "tail_prime_count",
}
CANONICAL_BOUND_PREFIX = re.compile(br'\A\{"bound":([0-9]+),')


class Sqrt218VerificationError(ValueError):
    """The archive does not establish the closed finite computation."""


def _exact_object(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise Sqrt218VerificationError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, unexpected={sorted(actual - fields)})"
        )
    return value


def _natural(value: Any, what: str, *, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise Sqrt218VerificationError(f"{what} is not a natural number")
    if maximum is not None and value > maximum:
        raise Sqrt218VerificationError(f"{what} exceeds {maximum}")
    return value


def _hex_digest(value: Any, what: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise Sqrt218VerificationError(f"{what} is not lowercase SHA-256")
    return value


def _eratosthenes(bound: int) -> list[int]:
    flags = bytearray(b"\x01") * (bound + 1)
    flags[0:2] = b"\x00\x00"
    for prime in range(2, math.isqrt(bound) + 1):
        if not flags[prime]:
            continue
        start = prime * prime
        flags[start : bound + 1 : prime] = b"\x00" * (
            (bound - start) // prime + 1
        )
    return [value for value in range(2, bound + 1) if flags[value]]


def _expected_log_rows(bound: int, prime_set: set[int]) -> dict[int, tuple[int, int]]:
    rows: dict[int, tuple[int, int]] = {}
    for value in range(1, min(bound, LOG_SEED_AT) + 1):
        lower, upper = LOG_SEEDS_30[value - 1]
        if value in prime_set:
            rows[value] = (lower, upper)
    if bound <= LOG_SEED_AT:
        return rows
    lower, upper = LOG_SEEDS_30[LOG_SEED_AT - 1]
    for value in range(LOG_SEED_AT, bound):
        denominator = 2 * value * value * (value - 1)
        lower += (
            SCALE * (2 * value * value - 3 * value - 1) // denominator
        )
        upper += (
            SCALE * (2 * value * value - 3 * value + 3)
            + denominator
            - 1
        ) // denominator
        if value + 1 in prime_set:
            rows[value + 1] = (lower, upper)
    return rows


def _verify_prime_rows(
    value: Any, bound: int
) -> tuple[list[int], dict[int, tuple[int, int]], str]:
    if not isinstance(value, list):
        raise Sqrt218VerificationError("primes must be an array")
    expected_primes = _eratosthenes(bound)
    if len(value) != len(expected_primes):
        raise Sqrt218VerificationError("prime-row count differs from Eratosthenes")
    prime_set = set(expected_primes)
    expected_logs = _expected_log_rows(bound, prime_set)
    actual_logs: dict[int, tuple[int, int]] = {}
    digest = hashlib.sha256()
    for index, (row, expected_prime) in enumerate(zip(value, expected_primes)):
        if not isinstance(row, list) or len(row) != 5:
            raise Sqrt218VerificationError(f"prime row {index} has wrong arity")
        prime = _natural(row[0], f"prime row {index} prime", maximum=bound)
        witness = _natural(row[1], f"prime row {index} witness", maximum=bound)
        factors_raw = row[2]
        lower = _natural(row[3], f"prime row {index} lower log")
        upper = _natural(row[4], f"prime row {index} upper log")
        if prime != expected_prime:
            raise Sqrt218VerificationError(
                f"prime row {index} differs from complete sieve"
            )
        if not isinstance(factors_raw, list):
            raise Sqrt218VerificationError(f"prime row {index} factors are not an array")
        factors = [
            _natural(factor, f"prime row {index} factor", maximum=prime)
            for factor in factors_raw
        ]
        if prime == 2:
            if witness != 0 or factors:
                raise Sqrt218VerificationError("the prime-two base row is malformed")
        else:
            if (
                not factors
                or factors != sorted(factors)
                or math.prod(factors) != prime - 1
                or any(factor not in prime_set or factor >= prime for factor in factors)
            ):
                raise Sqrt218VerificationError(
                    f"prime row {index} does not completely factor p-1"
                )
            if not 2 <= witness < prime or pow(witness, prime - 1, prime) != 1:
                raise Sqrt218VerificationError(
                    f"prime row {index} fails its full Lucas residue"
                )
            if any(
                pow(witness, (prime - 1) // factor, prime) == 1
                for factor in set(factors)
            ):
                raise Sqrt218VerificationError(
                    f"prime row {index} fails a quotient Lucas residue"
                )
        if expected_logs.get(prime) != (lower, upper) or lower > upper:
            raise Sqrt218VerificationError(
                f"prime row {index} differs from the independent log ladder"
            )
        actual_logs[prime] = (lower, upper)
        digest.update(
            f"{prime}:{witness}:{','.join(map(str, factors))}\n".encode("ascii")
        )
    return expected_primes, actual_logs, digest.hexdigest()


def _expected_events(
    primes: list[int], bound: int
) -> tuple[list[tuple[int, int, int]], list[int], list[list[int]]]:
    unordered: list[tuple[int, int, int]] = []
    exponents: list[list[int]] = []
    for prime_index, prime in enumerate(primes):
        current: list[int] = []
        power = prime
        exponent = 1
        while power <= bound:
            unordered.append((power, prime_index, exponent))
            current.append(exponent)
            if power > bound // prime:
                break
            power *= prime
            exponent += 1
        exponents.append(current)
    events = sorted(unordered)
    inverse = {
        (prime_index, exponent): event_index
        for event_index, (_power, prime_index, exponent) in enumerate(events)
    }
    canonical = [
        [inverse[(prime_index, exponent)] for exponent in row]
        for prime_index, row in enumerate(exponents)
    ]
    return events, [len(row) for row in exponents], canonical


def _verify_events(
    value: Any, primes: list[int], bound: int
) -> tuple[list[tuple[int, int, int]], str]:
    if not isinstance(value, list):
        raise Sqrt218VerificationError("events must be an array")
    expected, counts, canonical = _expected_events(primes, bound)
    if len(value) != len(expected):
        raise Sqrt218VerificationError("event-row count differs")
    actual: list[tuple[int, int, int]] = []
    for index, (row, expected_row) in enumerate(zip(value, expected)):
        if not isinstance(row, list) or len(row) != 3:
            raise Sqrt218VerificationError(f"event row {index} has wrong arity")
        decoded = (
            _natural(row[0], f"event row {index} value", maximum=bound),
            _natural(
                row[1],
                f"event row {index} prime index",
                maximum=max(0, len(primes) - 1),
            ),
            _natural(row[2], f"event row {index} exponent", maximum=64),
        )
        if decoded != expected_row:
            raise Sqrt218VerificationError(
                f"event row {index} differs from complete prime-power enumeration"
            )
        actual.append(decoded)
    digest = hashlib.sha256()
    for prime_index, prime in enumerate(primes):
        digest.update(
            f"prime:{prime_index}:{prime}:count={counts[prime_index]}:"
            f"map={','.join(map(str, canonical[prime_index]))}\n".encode("ascii")
        )
    for event_index, (power, prime_index, exponent) in enumerate(actual):
        digest.update(
            f"event:{event_index}:{power}:{prime_index}:{exponent}:"
            f"sqrt={math.isqrt(power)}\n".encode("ascii")
        )
    return actual, digest.hexdigest()


def _ceil_ratio(numerator: int, denominator: int) -> int:
    quotient, remainder = divmod(numerator, denominator)
    return quotient + (1 if remainder else 0)


def _lower_reciprocal_sqrt(value: int, root: int) -> int:
    remainder = value - root * root
    return (RECIPROCAL_SCALE * 2 * root) // (
        2 * root * root + remainder
    )


def _upper_reciprocal_sqrt(value: int, root: int) -> int:
    remainder = value - root * root
    return _ceil_ratio(
        RECIPROCAL_SCALE * (4 * root * root + remainder),
        root * (4 * root * root + 3 * remainder),
    )


def _replay_scan(
    events: list[tuple[int, int, int]],
    primes: list[int],
    logs: dict[int, tuple[int, int]],
    bound: int,
) -> dict[str, Any]:
    weighted = 0
    psi = 0
    minimum: int | None = None
    minimum_at = 0
    next_event = 0
    digest = hashlib.sha256()
    for value in range(2, bound + 1):
        if next_event < len(events) and events[next_event][0] == value:
            _power, prime_index, exponent = events[next_event]
            lower, upper = logs[primes[prime_index]]
            root = math.isqrt(value)
            weighted = weighted + upper * _upper_reciprocal_sqrt(value, root)
            psi = psi + lower
            digest.update(
                f"event:{value}:{prime_index}:{exponent}:{lower}:{upper}:"
                f"{weighted}:{psi}\n".encode("ascii")
            )
            next_event += 1
        root = math.isqrt(value)
        slack = 2501 * root * SCALE * RECIPROCAL_SCALE - 1250 * weighted
        if slack <= 0:
            raise Sqrt218VerificationError(f"head guard fails at {value}")
        if minimum is None or slack < minimum:
            minimum = slack
            minimum_at = value
    if minimum is None or next_event != len(events):
        raise Sqrt218VerificationError("full scan did not consume the event roster")
    root = math.isqrt(bound)
    anchor = (
        2501 * root * SCALE * RECIPROCAL_SCALE
        - 2500
        * (weighted - psi * _lower_reciprocal_sqrt(bound, root))
    )
    if anchor <= 0:
        raise Sqrt218VerificationError("endpoint Abel anchor fails")
    digest.update(
        f"final:{bound}:{weighted}:{psi}:{minimum}:{minimum_at}:{anchor}\n".encode(
            "ascii"
        )
    )
    return {
        "anchor_slack": anchor,
        "final_psi_lower": psi,
        "final_weighted_upper": weighted,
        "fixed_scan_sha256": digest.hexdigest(),
        "minimum_head_n": minimum_at,
        "minimum_head_slack": minimum,
    }


def verify_certificate_bytes(
    raw: bytes,
    *,
    run_input_raw: bytes | None = None,
    require_production: bool = False,
    execution_context: str | None = None,
) -> dict[str, Any]:
    try:
        certificate = parse_canonical_json(
            raw, what="Sqrt218 certificate", maximum_bytes=MAX_CERTIFICATE_BYTES
        )
    except ValueError as error:
        raise Sqrt218VerificationError(str(error)) from error
    certificate = _exact_object(certificate, CERTIFICATE_FIELDS, "certificate")
    if (
        certificate["kind"] != CERTIFICATE_KIND
        or certificate["schema_version"] != SCHEMA_VERSION
        or certificate["log_seed_at"] != LOG_SEED_AT
        or certificate["log_scale"] != SCALE
        or certificate["reciprocal_scale"] != RECIPROCAL_SCALE
    ):
        raise Sqrt218VerificationError("certificate protocol constants differ")
    bound = _natural(certificate["bound"], "bound", maximum=BOUND)
    if bound < 2 or (require_production and bound != BOUND):
        raise Sqrt218VerificationError("certificate bound is outside the selected profile")
    try:
        require_replay_scope(bound, execution_context=execution_context)
    except ValueError as error:
        raise Sqrt218VerificationError(str(error)) from error
    if run_input_raw is not None:
        try:
            run_input = parse_canonical_json(
                run_input_raw, what="Sqrt218 run input", maximum_bytes=1 << 20
            )
        except ValueError as error:
            raise Sqrt218VerificationError(str(error)) from error
        if run_input != production_run_input():
            raise Sqrt218VerificationError("run input differs from the production contract")
        if bound != run_input["bound"]:
            raise Sqrt218VerificationError("certificate bound differs from run input")
    primes, logs, pratt_digest = _verify_prime_rows(
        certificate["primes"], bound
    )
    events, layout_digest = _verify_events(
        certificate["events"], primes, bound
    )
    summary = _exact_object(certificate["summary"], SUMMARY_FIELDS, "summary")
    for field in SUMMARY_FIELDS - {
        "fixed_scan_sha256",
        "layout_sha256",
        "pratt_sha256",
    }:
        _natural(summary[field], f"summary {field}")
    for field in ("fixed_scan_sha256", "layout_sha256", "pratt_sha256"):
        _hex_digest(summary[field], f"summary {field}")
    replay = _replay_scan(events, primes, logs, bound)
    replay.update(
        {
            "layout_sha256": layout_digest,
            "power_event_count": len(events),
            "pratt_sha256": pratt_digest,
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
    if replay != summary:
        differing = {
            field: {"archive": summary.get(field), "replay": value}
            for field, value in replay.items()
            if summary.get(field) != value
        }
        raise Sqrt218VerificationError(f"summary differs from replay: {differing}")
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
            raise Sqrt218VerificationError("production summary differs from semantic pins")
    elif require_production:
        raise Sqrt218VerificationError("a sample certificate cannot enter production")
    return {
        "accepted": True,
        "bound": bound,
        "certificate_sha256": sha256_bytes(raw),
        "certificate_size_bytes": len(raw),
        "classification": "full_exact_external_replay_not_lean_theorem",
        "kind": VERIFICATION_KIND,
        "proves_lean_claim": False,
        "schema_version": SCHEMA_VERSION,
        "summary": summary,
    }


def verify_certificate(
    path: Path,
    *,
    run_input_path: Path | None = None,
    require_production: bool = False,
    execution_context: str | None = None,
) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise Sqrt218VerificationError("certificate must be a regular non-symlink file")
    with path.open("rb") as source:
        prefix = source.read(64)
    match = CANONICAL_BOUND_PREFIX.match(prefix)
    if match is not None:
        prefix_bound = int(match.group(1))
        try:
            require_replay_scope(
                prefix_bound,
                execution_context=execution_context,
            )
        except ValueError as error:
            raise Sqrt218VerificationError(str(error)) from error
    raw = path.read_bytes()
    run_input_raw = None
    if run_input_path is not None:
        if run_input_path.is_symlink() or not run_input_path.is_file():
            raise Sqrt218VerificationError(
                "run input must be a regular non-symlink file"
            )
        run_input_raw = run_input_path.read_bytes()
    return verify_certificate_bytes(
        raw,
        run_input_raw=run_input_raw,
        require_production=require_production,
        execution_context=execution_context,
    )


def verification_bytes(report: dict[str, Any]) -> bytes:
    return canonical_json_bytes(report)
