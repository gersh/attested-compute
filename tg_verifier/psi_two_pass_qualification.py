# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded source/oracle qualification for the CH25 psi two-pass worker.

The qualification regenerates a literal ordered prime-power roster with the
existing exact Python implementation.  A separately loaded pinned CRlibm
library supplies directed binary64 endpoints; Python independently decodes
those bits into Q64, checks every endpoint against the rational-series
``Real.log`` enclosure, constructs both retained SHA-256 commitments, replays
every integer gap guard, and derives every shard input from root ``[0, 0]``.

Both the candidate and an optional baseline worker are then run in summary and
verify modes.  Exact receipt bytes are retained.  Replay requires exact
agreement with the literal oracle, between passes, between repeats, and
between baseline and candidate after removing timing only.

This remains bounded executable qualification.  It does not prove the
primesieve or CRlibm implementations refine Mathlib, prove a compiler or CPU,
attest a source run, admit a receipt, or discharge the CH25 atom.
"""

from __future__ import annotations

import ctypes
from copy import deepcopy
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
from math import isqrt
import os
from pathlib import Path
import struct
import time
from typing import Any, Mapping, Sequence

from .campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    canonical_sha256,
    hash_file_once,
    load_json,
    sha256_bytes,
)
from .evidence import EvidenceError, load_decimal_json_bytes
from .finite_campaigns import fixed_log_bounds, prime_power_events
from .psi_residual_campaign import (
    ATOM,
    CRLIBM_COMMIT,
    FALLBACK_FIELDS,
    MAX_RECEIPT_BYTES,
    MAX_RUNNER_BYTES,
    MAX_SOURCE_BYTES,
    PRIMESIEVE_COMMIT,
    RUNNER_ALGORITHM,
    SOURCE_EVENT_COUNT,
    SOURCE_UPPER_EXCLUSIVE,
    PsiResidualCampaignError,
    _execute,
    _validate_upstream_manifest,
    validate_runner_receipt,
)


SCHEMA = "sparkinterval.tg.psi-two-pass-bounded-qualification.v1"
ALGORITHM = "ch25-psi-two-pass-literal-oracle-qualification-v1"
CLASSIFICATION = (
    "bounded_literal_oracle_and_binary_equivalence_not_source_evidence_or_proof"
)
SCALE = 1 << 64
U64_MAX = (1 << 64) - 1
U128_LIMIT = 1 << 128
EVENT_DOMAIN = b"sparkinterval.tg.psi-prime-power-events.v1\0"
ROW_DOMAIN = b"sparkinterval.tg.psi-prime-power-rows.v1\0"

_TOP_FIELDS = frozenset(
    {
        "schema",
        "algorithm",
        "classification",
        "identity",
        "configuration",
        "oracle",
        "executions",
        "performance",
        "checks",
        "capabilities",
    }
)
_IDENTITY_FIELDS = frozenset(
    {
        "candidate_runner_sha256",
        "candidate_runner_size_bytes",
        "baseline_runner_sha256",
        "baseline_runner_size_bytes",
        "source_sha256",
        "source_size_bytes",
        "upstream_manifest_sha256",
        "upstream_manifest_size_bytes",
        "crlibm_shared_sha256",
        "crlibm_shared_size_bytes",
    }
)
_CONFIG_FIELDS = frozenset(
    {
        "domain_lower",
        "domain_upper_exclusive",
        "shard_span",
        "shard_count",
        "sieve_size_kib",
        "series_terms",
        "oracle_segment_size",
        "repeat_count",
    }
)
_ORACLE_FIELDS = frozenset({"semantics", "timing"})
_ORACLE_TIMING_FIELDS = frozenset(
    {
        "prime_power_enumeration_seconds_decimal",
        "directed_log_refinement_seconds_decimal",
        "commitment_gap_fold_seconds_decimal",
        "total_seconds_decimal",
        "scope",
    }
)
_ORACLE_SEMANTIC_FIELDS = frozenset(
    {
        "prime_power_events",
        "prime_events",
        "higher_power_events",
        "unique_primes",
        "rational_log_pairs_enclosed",
        "root_state",
        "entries",
        "final_state",
    }
)
_ORACLE_ENTRY_FIELDS = frozenset(
    {
        "index",
        "lower",
        "upper_exclusive",
        "prime_power_events",
        "prime_events",
        "higher_power_events",
        "event_sha256",
        "row_sha256",
        "delta",
        "incoming",
        "outgoing",
        "exact_fallbacks",
        "all_gap_guards_accept",
    }
)
_EXECUTION_FIELDS = frozenset({"candidate", "baseline"})
_BINARY_EXECUTION_FIELDS = frozenset({"runs"})
_RUN_FIELDS = frozenset({"repeat_index", "mode_order", "summary", "verify"})
_RECORD_FIELDS = frozenset(
    {
        "index",
        "lower",
        "upper_exclusive",
        "receipt_sha256",
        "receipt_size_bytes",
        "receipt_hex",
        "report",
        "process_wall_seconds_decimal",
    }
)
_PERFORMANCE_FIELDS = frozenset(
    {
        "configuration",
        "candidate",
        "baseline",
        "comparison",
        "linear_source_projection",
        "scope",
    }
)
_PERFORMANCE_CONFIG_FIELDS = frozenset(
    {
        "lower",
        "upper_exclusive",
        "sieve_size_kib",
        "repeat_count",
        "incoming_state",
        "incoming_state_is_root_derived",
    }
)
_PERFORMANCE_BINARY_FIELDS = frozenset(
    {
        "summary_records",
        "verify_records",
        "summary_elapsed_median",
        "verify_elapsed_median",
        "two_pass_elapsed_median",
        "summary_wall_median",
        "verify_wall_median",
        "two_pass_wall_median",
    }
)
_PERFORMANCE_COMPARISON_FIELDS = frozenset(
    {
        "semantic_outputs_equal_ignoring_timing",
        "summary_elapsed_speedup",
        "verify_elapsed_speedup",
        "two_pass_elapsed_speedup",
        "summary_wall_speedup",
        "verify_wall_speedup",
        "two_pass_wall_speedup",
    }
)
_PROJECTION_FIELDS = frozenset(
    {
        "bounded_prime_power_events_per_pass",
        "candidate_event_passes_per_second",
        "published_source_event_count_per_pass",
        "linear_two_pass_source_seconds",
        "linear_two_pass_source_hours",
        "is_source_run",
    }
)
_CHECK_FIELDS = frozenset(
    {
        "literal_prime_power_roster_replayed",
        "every_crlibm_q64_pair_contains_rational_oracle",
        "event_commitments_match_oracle",
        "row_commitments_match_oracle",
        "summary_verify_deltas_match_oracle",
        "root_derived_incoming_states_match",
        "every_gap_guard_replayed",
        "ordered_merge_and_final_state_match",
        "candidate_repeats_match_ignoring_timing",
        "baseline_candidate_match_ignoring_timing",
        "performance_outputs_match_ignoring_timing",
    }
)
_CAPABILITY_FIELDS = frozenset(
    {
        "bounded_qualification_complete",
        "full_source_range",
        "primesieve_to_mathlib_realization_proved",
        "crlibm_to_mathlib_realization_proved",
        "compiler_or_cpu_refinement_proved",
        "source_run_completed",
        "execution_attested",
        "receipt_admitted",
        "lean_atom_discharged",
        "linear_source_projection_is_proof",
    }
)
_MODE_ORDERS = (("summary", "verify"), ("verify", "summary"))
_COMMON_FIELDS = (
    "algorithm",
    "classification",
    "atom",
    "primesieve_commit",
    "crlibm_commit",
    "lower",
    "upper_exclusive",
    "work_count",
    "scale_bits",
    "sieve_size_kib",
    "log_interval_encoding",
    "event_encoding",
    "event_sha256",
    "row_encoding",
    "row_sha256",
    "prime_power_events",
    "prime_events",
    "higher_power_events",
    "state_components",
    "delta",
    "accepted",
    "execution_attested",
    "lean_atom_discharged",
)


class PsiTwoPassQualificationError(RuntimeError):
    """A bounded psi qualification failed closed."""


def _integer(value: object, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PsiTwoPassQualificationError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise PsiTwoPassQualificationError(f"{name} must be at least {minimum}")
    return value


def _state(value: object, name: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise PsiTwoPassQualificationError(f"{name} must be a two-integer array")
    result = tuple(
        _integer(item, f"{name}[{index}]", minimum=0)
        for index, item in enumerate(value)
    )
    if result[0] > result[1] or result[1] >= U128_LIMIT:
        raise PsiTwoPassQualificationError(f"{name} is reversed or outside u128")
    return result  # type: ignore[return-value]


def _sha256_hex(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise PsiTwoPassQualificationError(f"{name} must be 32-byte lowercase hex")
    try:
        decoded = bytes.fromhex(value)
    except ValueError as exc:
        raise PsiTwoPassQualificationError(
            f"{name} must be 32-byte lowercase hex"
        ) from exc
    if len(decoded) != 32 or value != value.lower():
        raise PsiTwoPassQualificationError(f"{name} must be 32-byte lowercase hex")
    return value


def _decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, str) or not value:
        raise PsiTwoPassQualificationError(f"{name} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise PsiTwoPassQualificationError(f"{name} is not decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise PsiTwoPassQualificationError(f"{name} must be finite and nonnegative")
    return parsed


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite() or value < 0:
        raise PsiTwoPassQualificationError("timing must be finite and nonnegative")
    return format(value, "f")


def _median(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise PsiTwoPassQualificationError("cannot take an empty timing median")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _ratio(numerator: Decimal, denominator: Decimal, name: str) -> Decimal:
    if denominator <= 0:
        raise PsiTwoPassQualificationError(f"{name} denominator is not positive")
    with localcontext() as context:
        context.prec = 28
        return numerator / denominator


def _ranges(
    upper_exclusive: int, shard_span: int
) -> tuple[tuple[int, int], ...]:
    upper = _integer(upper_exclusive, "domain upper exclusive", minimum=3)
    span = _integer(shard_span, "shard span", minimum=1)
    if upper > SOURCE_UPPER_EXCLUSIVE:
        raise PsiTwoPassQualificationError("qualification exceeds the source range")
    if upper == SOURCE_UPPER_EXCLUSIVE:
        raise PsiTwoPassQualificationError(
            "bounded qualification refuses the literal full source range"
        )
    result: list[tuple[int, int]] = []
    lower = 2
    while lower < upper:
        following = min(lower + span, upper)
        result.append((lower, following))
        lower = following
    return tuple(result)


class _CRlibmQ64:
    def __init__(self, path: Path):
        try:
            self.library = ctypes.CDLL(os.fspath(path.resolve()))
        except OSError as exc:
            raise PsiTwoPassQualificationError(
                f"cannot load CRlibm oracle library: {exc}"
            ) from exc
        self.library.crlibm_init.argtypes = []
        self.library.crlibm_init.restype = ctypes.c_ulonglong
        self.library.crlibm_exit.argtypes = [ctypes.c_ulonglong]
        self.library.crlibm_exit.restype = None
        for name in ("log_rd", "log_ru"):
            function = getattr(self.library, name)
            function.argtypes = [ctypes.c_double]
            function.restype = ctypes.c_double
        self.state = self.library.crlibm_init()

    def close(self) -> None:
        self.library.crlibm_exit(self.state)

    @staticmethod
    def _scale(value: float, round_up: bool) -> int:
        bits = struct.unpack(">Q", struct.pack(">d", value))[0]
        if bits >> 63:
            raise PsiTwoPassQualificationError("CRlibm returned a negative log")
        biased = (bits >> 52) & 0x7FF
        if biased in (0, 0x7FF):
            raise PsiTwoPassQualificationError(
                "CRlibm returned a non-normal or non-finite log"
            )
        significand = (1 << 52) | (bits & ((1 << 52) - 1))
        exponent = biased - 1023
        shift = exponent - 52 + 64
        if shift >= 0:
            result = significand << shift
        else:
            right = -shift
            quotient, remainder = divmod(significand, 1 << right)
            result = quotient + int(round_up and remainder != 0)
        if not 0 <= result < U128_LIMIT:
            raise PsiTwoPassQualificationError("scaled CRlibm log exceeds u128")
        return result

    def bounds(self, prime: int) -> tuple[int, int]:
        input_value = float(prime)
        if int(input_value) != prime:
            raise PsiTwoPassQualificationError("prime is not exact binary64")
        lower = self._scale(self.library.log_rd(input_value), False)
        upper = self._scale(self.library.log_ru(input_value), True)
        if lower > upper:
            raise PsiTwoPassQualificationError("CRlibm interval is reversed")
        return lower, upper


def _lower_guard(
    value: int, psi_lower: int, *, strict: bool
) -> tuple[bool, int]:
    x_scaled = value << 64
    if psi_lower >= x_scaled:
        return True, 0
    difference = x_scaled - psi_lower
    quotient, remainder = divmod(difference, SCALE)
    has_remainder = remainder != 0
    if has_remainder and quotient == U64_MAX:
        return False, 0
    ceiling = quotient + int(has_remainder)
    root = isqrt(2 * value)
    if ceiling <= root and (
        not strict
        or ceiling < root
        or has_remainder
        or root * root < 2 * value
    ):
        return True, 0
    if quotient > root:
        return False, 0
    accepted = (
        difference * difference < 2 * value * SCALE * SCALE
        if strict
        else difference * difference <= 2 * value * SCALE * SCALE
    )
    return accepted, 1


def _upper_guard(value: int, psi_upper: int) -> tuple[bool, int]:
    x_scaled = value << 64
    if psi_upper <= x_scaled:
        return True, 0
    difference = psi_upper - x_scaled
    quotient, remainder = divmod(difference, SCALE)
    has_remainder = remainder != 0
    exact = (
        difference
        * difference
        * 25_000_000
        * 25_000_000
        <= 19_764_819
        * 19_764_819
        * value
        * SCALE
        * SCALE
    )
    if quotient > 3_000_000:
        return exact, 1
    ceiling = quotient + int(has_remainder)
    right = 19_764_819 * 19_764_819 * value
    if ceiling * ceiling * 25_000_000 * 25_000_000 <= right:
        return True, 0
    if quotient * quotient * 25_000_000 * 25_000_000 > right:
        return False, 0
    return exact, 1


def _literal_oracle(
    *,
    crlibm_shared: Path,
    ranges: Sequence[tuple[int, int]],
    series_terms: int,
    segment_size: int,
) -> dict[str, Any]:
    started = time.monotonic_ns()
    events = prime_power_events(
        ranges[0][0], ranges[-1][1], segment_size=segment_size
    )
    enumerated = time.monotonic_ns()
    bounds: dict[int, tuple[int, int]] = {}
    crlibm = _CRlibmQ64(crlibm_shared)
    try:
        for event in events:
            if event.prime in bounds:
                continue
            directed = crlibm.bounds(event.prime)
            rational = fixed_log_bounds(event.prime, 64, series_terms)
            if not (
                directed[0] <= rational[0] <= rational[1] <= directed[1]
            ):
                raise PsiTwoPassQualificationError(
                    f"CRlibm Q64 interval misses rational oracle at p={event.prime}"
                )
            bounds[event.prime] = directed
    finally:
        crlibm.close()
    refined = time.monotonic_ns()

    entries: list[dict[str, Any]] = []
    current = (0, 0)
    event_index = 0
    total_prime = 0
    total_higher = 0
    for index, (lower, upper) in enumerate(ranges):
        event_digest = hashlib.sha256(EVENT_DOMAIN)
        row_digest = hashlib.sha256(ROW_DOMAIN)
        delta_lower = 0
        delta_upper = 0
        prime_count = 0
        higher_count = 0
        lower_fallbacks = 0
        upper_fallbacks = 0
        incoming = current
        previous_value = 0
        while event_index < len(events) and events[event_index].value < upper:
            event = events[event_index]
            if event.value < lower or event.value <= previous_value:
                raise PsiTwoPassQualificationError(
                    "literal prime-power roster is missing, duplicated, or reordered"
                )
            log_lower, log_upper = bounds[event.prime]
            structural = (
                event.value.to_bytes(8, "big")
                + event.prime.to_bytes(8, "big")
                + event.exponent.to_bytes(4, "big")
            )
            event_digest.update(structural)
            row_digest.update(structural)
            row_digest.update(log_lower.to_bytes(16, "big"))
            row_digest.update(log_upper.to_bytes(16, "big"))
            lower_ok, lower_fallback = _lower_guard(
                event.value, current[0], strict=False
            )
            if not lower_ok:
                raise PsiTwoPassQualificationError(
                    f"literal lower gap guard fails at {event.value}"
                )
            lower_fallbacks += lower_fallback
            current = (current[0] + log_lower, current[1] + log_upper)
            upper_ok, upper_fallback = _upper_guard(event.value, current[1])
            if not upper_ok:
                raise PsiTwoPassQualificationError(
                    f"literal upper gap guard fails at {event.value}"
                )
            upper_fallbacks += upper_fallback
            delta_lower += log_lower
            delta_upper += log_upper
            if event.exponent == 1:
                prime_count += 1
            else:
                higher_count += 1
            previous_value = event.value
            event_index += 1
        event_count = prime_count + higher_count
        total_prime += prime_count
        total_higher += higher_count
        entries.append(
            {
                "index": index,
                "lower": lower,
                "upper_exclusive": upper,
                "prime_power_events": event_count,
                "prime_events": prime_count,
                "higher_power_events": higher_count,
                "event_sha256": event_digest.hexdigest(),
                "row_sha256": row_digest.hexdigest(),
                "delta": [delta_lower, delta_upper],
                "incoming": list(incoming),
                "outgoing": list(current),
                "exact_fallbacks": {
                    "lower_left_limit": lower_fallbacks,
                    "upper_post_jump": upper_fallbacks,
                    "terminal_lower": 0,
                },
                "all_gap_guards_accept": True,
            }
        )
    if event_index != len(events):
        raise PsiTwoPassQualificationError("literal roster escaped shard coverage")
    folded = time.monotonic_ns()
    semantics = {
        "prime_power_events": len(events),
        "prime_events": total_prime,
        "higher_power_events": total_higher,
        "unique_primes": len(bounds),
        "rational_log_pairs_enclosed": len(bounds),
        "root_state": [0, 0],
        "entries": entries,
        "final_state": list(current),
    }
    return {
        "semantics": semantics,
        "timing": {
            "prime_power_enumeration_seconds_decimal": _decimal_text(
                Decimal(enumerated - started) / Decimal(1_000_000_000)
            ),
            "directed_log_refinement_seconds_decimal": _decimal_text(
                Decimal(refined - enumerated) / Decimal(1_000_000_000)
            ),
            "commitment_gap_fold_seconds_decimal": _decimal_text(
                Decimal(folded - refined) / Decimal(1_000_000_000)
            ),
            "total_seconds_decimal": _decimal_text(
                Decimal(folded - started) / Decimal(1_000_000_000)
            ),
            "scope": (
                "bounded_python_roster_rational_log_and_loaded_crlibm_oracle_timing"
            ),
        },
    }


def _wire_report(report: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(report))
    elapsed = value.get("elapsed_seconds")
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, Decimal)):
        raise PsiTwoPassQualificationError("receipt elapsed_seconds is malformed")
    value["elapsed_seconds"] = _decimal_text(Decimal(elapsed))
    return value


def _without_elapsed(report: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(report))
    value.pop("elapsed_seconds", None)
    return value


def _command(
    runner: Path,
    *,
    mode: str,
    lower: int,
    upper: int,
    sieve_size_kib: int,
    incoming: Sequence[int] | None,
) -> tuple[str, ...]:
    command = [
        os.fspath(runner.resolve()),
        "--mode",
        mode,
        "--lower",
        str(lower),
        "--upper",
        str(upper - 1),
        "--sieve-size-kib",
        str(sieve_size_kib),
    ]
    if mode == "verify":
        if incoming is None:
            raise PsiTwoPassQualificationError("verify mode requires incoming state")
        command += [
            "--incoming-lower",
            str(incoming[0]),
            "--incoming-upper",
            str(incoming[1]),
        ]
    return tuple(command)


def _run_record(
    runner: Path,
    *,
    index: int,
    mode: str,
    lower: int,
    upper: int,
    sieve_size_kib: int,
    incoming: Sequence[int] | None,
    timeout_seconds: int | None,
) -> dict[str, Any]:
    started = time.monotonic_ns()
    try:
        raw = _execute(
            _command(
                runner,
                mode=mode,
                lower=lower,
                upper=upper,
                sieve_size_kib=sieve_size_kib,
                incoming=incoming,
            ),
            timeout_seconds,
        )
    except PsiResidualCampaignError as exc:
        raise PsiTwoPassQualificationError(str(exc)) from exc
    wall = Decimal(time.monotonic_ns() - started) / Decimal(1_000_000_000)
    try:
        report = load_decimal_json_bytes(raw, label=f"{mode} shard {index}")
    except EvidenceError as exc:
        raise PsiTwoPassQualificationError(str(exc)) from exc
    try:
        validate_runner_receipt(
            report,
            phase=mode,
            shard_lower=lower,
            shard_upper=upper,
            sieve_size_kib=sieve_size_kib,
            expected_incoming=incoming,
            source_terminal=(
                mode == "verify" and upper == SOURCE_UPPER_EXCLUSIVE
            ),
        )
    except PsiResidualCampaignError as exc:
        raise PsiTwoPassQualificationError(str(exc)) from exc
    return {
        "index": index,
        "lower": lower,
        "upper_exclusive": upper,
        "receipt_sha256": sha256_bytes(raw),
        "receipt_size_bytes": len(raw),
        "receipt_hex": raw.hex(),
        "report": _wire_report(report),
        "process_wall_seconds_decimal": _decimal_text(wall),
    }


def _decode_record(
    value: object,
    *,
    index: int,
    mode: str,
    bounds: tuple[int, int],
    sieve_size_kib: int,
    incoming: Sequence[int] | None,
) -> tuple[dict[str, Any], Decimal]:
    if not isinstance(value, dict) or set(value) != _RECORD_FIELDS:
        raise PsiTwoPassQualificationError(f"{mode} record fields changed")
    lower, upper = bounds
    if (
        value.get("index"),
        value.get("lower"),
        value.get("upper_exclusive"),
    ) != (index, lower, upper):
        raise PsiTwoPassQualificationError(
            f"{mode} record order/range changed at index {index}"
        )
    size = _integer(value.get("receipt_size_bytes"), "receipt size", minimum=1)
    if size > MAX_RECEIPT_BYTES:
        raise PsiTwoPassQualificationError("receipt exceeds byte limit")
    encoded = value.get("receipt_hex")
    if not isinstance(encoded, str) or len(encoded) != 2 * size:
        raise PsiTwoPassQualificationError("receipt hex length changed")
    try:
        raw = bytes.fromhex(encoded)
    except ValueError as exc:
        raise PsiTwoPassQualificationError("receipt hex is malformed") from exc
    if value.get("receipt_sha256") != sha256_bytes(raw):
        raise PsiTwoPassQualificationError("receipt digest differs from bytes")
    try:
        report = load_decimal_json_bytes(raw, label=f"{mode} record {index}")
    except EvidenceError as exc:
        raise PsiTwoPassQualificationError(str(exc)) from exc
    if value.get("report") != _wire_report(report):
        raise PsiTwoPassQualificationError("readable report differs from raw receipt")
    try:
        validate_runner_receipt(
            report,
            phase=mode,
            shard_lower=lower,
            shard_upper=upper,
            sieve_size_kib=sieve_size_kib,
            expected_incoming=incoming,
            source_terminal=(
                mode == "verify" and upper == SOURCE_UPPER_EXCLUSIVE
            ),
        )
    except PsiResidualCampaignError as exc:
        raise PsiTwoPassQualificationError(str(exc)) from exc
    wall = _decimal(
        value.get("process_wall_seconds_decimal"), "process wall seconds"
    )
    return report, wall


def _check_against_oracle(
    report: Mapping[str, Any], entry: Mapping[str, Any], mode: str
) -> None:
    for field in (
        "prime_power_events",
        "prime_events",
        "higher_power_events",
        "event_sha256",
        "row_sha256",
        "delta",
    ):
        if report.get(field) != entry.get(field):
            raise PsiTwoPassQualificationError(
                f"{mode} {field} differs from literal oracle at shard {entry['index']}"
            )
    if mode == "verify":
        if report.get("incoming_state") != entry.get("incoming"):
            raise PsiTwoPassQualificationError(
                "verify incoming state differs from literal exclusive scan"
            )
        if report.get("outgoing_state") != entry.get("outgoing"):
            raise PsiTwoPassQualificationError(
                "verify outgoing state differs from literal fold"
            )
        if report.get("exact_fallbacks") != entry.get("exact_fallbacks"):
            raise PsiTwoPassQualificationError(
                "verify fallback path differs from literal gap replay"
            )


def _same_common(
    summary: Mapping[str, Any], verification: Mapping[str, Any], label: str
) -> None:
    if {field: summary[field] for field in _COMMON_FIELDS} != {
        field: verification[field] for field in _COMMON_FIELDS
    }:
        raise PsiTwoPassQualificationError(f"{label} summary/verify output differs")


def _run_binary_root_campaign(
    runner: Path,
    *,
    ranges: Sequence[tuple[int, int]],
    oracle_entries: Sequence[Mapping[str, Any]],
    sieve_size_kib: int,
    repeat_count: int,
    timeout_seconds: int | None,
) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    baseline: dict[str, list[dict[str, Any]]] | None = None
    for repeat_index in range(repeat_count):
        order = _MODE_ORDERS[repeat_index % len(_MODE_ORDERS)]
        records: dict[str, list[dict[str, Any]]] = {"summary": [], "verify": []}
        decoded: dict[str, list[dict[str, Any]]] = {"summary": [], "verify": []}
        for mode in order:
            for index, ((lower, upper), entry) in enumerate(
                zip(ranges, oracle_entries, strict=True)
            ):
                incoming = entry["incoming"] if mode == "verify" else None
                record = _run_record(
                    runner,
                    index=index,
                    mode=mode,
                    lower=lower,
                    upper=upper,
                    sieve_size_kib=sieve_size_kib,
                    incoming=incoming,
                    timeout_seconds=timeout_seconds,
                )
                report, _ = _decode_record(
                    record,
                    index=index,
                    mode=mode,
                    bounds=(lower, upper),
                    sieve_size_kib=sieve_size_kib,
                    incoming=incoming,
                )
                _check_against_oracle(report, entry, mode)
                records[mode].append(record)
                decoded[mode].append(report)
        for index, pair in enumerate(
            zip(decoded["summary"], decoded["verify"], strict=True)
        ):
            _same_common(pair[0], pair[1], f"shard {index}")
        semantic = {
            mode: [_without_elapsed(report) for report in decoded[mode]]
            for mode in ("summary", "verify")
        }
        if baseline is None:
            baseline = semantic
        elif semantic != baseline:
            raise PsiTwoPassQualificationError(
                f"runner semantic output changed at repeat {repeat_index}"
            )
        runs.append(
            {
                "repeat_index": repeat_index,
                "mode_order": list(order),
                "summary": records["summary"],
                "verify": records["verify"],
            }
        )
    return {"runs": runs}


def _decode_binary_root_campaign(
    value: object,
    *,
    ranges: Sequence[tuple[int, int]],
    oracle_entries: Sequence[Mapping[str, Any]],
    sieve_size_kib: int,
    repeat_count: int,
) -> list[dict[str, list[dict[str, Any]]]]:
    if not isinstance(value, dict) or set(value) != _BINARY_EXECUTION_FIELDS:
        raise PsiTwoPassQualificationError("binary execution fields changed")
    runs = value.get("runs")
    if not isinstance(runs, list) or len(runs) != repeat_count:
        raise PsiTwoPassQualificationError("binary execution repeats are incomplete")
    decoded_runs: list[dict[str, list[dict[str, Any]]]] = []
    semantic_baseline: dict[str, list[dict[str, Any]]] | None = None
    for repeat_index, run in enumerate(runs):
        if not isinstance(run, dict) or set(run) != _RUN_FIELDS:
            raise PsiTwoPassQualificationError("binary run fields changed")
        if run.get("repeat_index") != repeat_index:
            raise PsiTwoPassQualificationError("binary repeat order changed")
        if run.get("mode_order") != list(
            _MODE_ORDERS[repeat_index % len(_MODE_ORDERS)]
        ):
            raise PsiTwoPassQualificationError("binary mode order changed")
        decoded: dict[str, list[dict[str, Any]]] = {}
        for mode in ("summary", "verify"):
            records = run.get(mode)
            if not isinstance(records, list) or len(records) != len(ranges):
                raise PsiTwoPassQualificationError(f"{mode} records are incomplete")
            reports: list[dict[str, Any]] = []
            for index, (record, bounds, entry) in enumerate(
                zip(records, ranges, oracle_entries, strict=True)
            ):
                incoming = entry["incoming"] if mode == "verify" else None
                report, _ = _decode_record(
                    record,
                    index=index,
                    mode=mode,
                    bounds=bounds,
                    sieve_size_kib=sieve_size_kib,
                    incoming=incoming,
                )
                _check_against_oracle(report, entry, mode)
                reports.append(report)
            decoded[mode] = reports
        for index, pair in enumerate(
            zip(decoded["summary"], decoded["verify"], strict=True)
        ):
            _same_common(pair[0], pair[1], f"shard {index}")
        semantic = {
            mode: [_without_elapsed(report) for report in decoded[mode]]
            for mode in ("summary", "verify")
        }
        if semantic_baseline is None:
            semantic_baseline = semantic
        elif semantic != semantic_baseline:
            raise PsiTwoPassQualificationError(
                f"binary semantic output changed at repeat {repeat_index}"
            )
        decoded_runs.append(decoded)
    return decoded_runs


def _performance_binary(
    runner: Path,
    *,
    lower: int,
    upper: int,
    sieve_size_kib: int,
    incoming: tuple[int, int],
    repeat_count: int,
    timeout_seconds: int | None,
) -> dict[str, Any]:
    records: dict[str, list[dict[str, Any]]] = {"summary": [], "verify": []}
    elapsed: dict[str, list[Decimal]] = {"summary": [], "verify": []}
    walls: dict[str, list[Decimal]] = {"summary": [], "verify": []}
    semantic: dict[str, dict[str, Any] | None] = {"summary": None, "verify": None}
    for repeat_index in range(repeat_count):
        for mode in _MODE_ORDERS[repeat_index % len(_MODE_ORDERS)]:
            record = _run_record(
                runner,
                index=repeat_index,
                mode=mode,
                lower=lower,
                upper=upper,
                sieve_size_kib=sieve_size_kib,
                incoming=incoming if mode == "verify" else None,
                timeout_seconds=timeout_seconds,
            )
            report, wall = _decode_record(
                record,
                index=repeat_index,
                mode=mode,
                bounds=(lower, upper),
                sieve_size_kib=sieve_size_kib,
                incoming=incoming if mode == "verify" else None,
            )
            candidate = _without_elapsed(report)
            if semantic[mode] is None:
                semantic[mode] = candidate
            elif semantic[mode] != candidate:
                raise PsiTwoPassQualificationError(
                    f"performance {mode} output changed across repeats"
                )
            records[mode].append(record)
            elapsed[mode].append(Decimal(report["elapsed_seconds"]))
            walls[mode].append(wall)
    assert semantic["summary"] is not None and semantic["verify"] is not None
    _same_common(semantic["summary"], semantic["verify"], "performance")
    summary_elapsed = _median(elapsed["summary"])
    verify_elapsed = _median(elapsed["verify"])
    summary_wall = _median(walls["summary"])
    verify_wall = _median(walls["verify"])
    return {
        "summary_records": records["summary"],
        "verify_records": records["verify"],
        "summary_elapsed_median": _decimal_text(summary_elapsed),
        "verify_elapsed_median": _decimal_text(verify_elapsed),
        "two_pass_elapsed_median": _decimal_text(summary_elapsed + verify_elapsed),
        "summary_wall_median": _decimal_text(summary_wall),
        "verify_wall_median": _decimal_text(verify_wall),
        "two_pass_wall_median": _decimal_text(summary_wall + verify_wall),
    }


def _decode_performance_binary(
    value: object,
    *,
    lower: int,
    upper: int,
    sieve_size_kib: int,
    incoming: tuple[int, int],
    repeat_count: int,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not isinstance(value, dict) or set(value) != _PERFORMANCE_BINARY_FIELDS:
        raise PsiTwoPassQualificationError("performance binary fields changed")
    semantic: dict[str, dict[str, Any] | None] = {"summary": None, "verify": None}
    elapsed: dict[str, list[Decimal]] = {"summary": [], "verify": []}
    walls: dict[str, list[Decimal]] = {"summary": [], "verify": []}
    for mode, record_field in (
        ("summary", "summary_records"),
        ("verify", "verify_records"),
    ):
        records = value.get(record_field)
        if not isinstance(records, list) or len(records) != repeat_count:
            raise PsiTwoPassQualificationError(
                f"performance {mode} records are incomplete"
            )
        for repeat_index, record in enumerate(records):
            report, wall = _decode_record(
                record,
                index=repeat_index,
                mode=mode,
                bounds=(lower, upper),
                sieve_size_kib=sieve_size_kib,
                incoming=incoming if mode == "verify" else None,
            )
            candidate = _without_elapsed(report)
            if semantic[mode] is None:
                semantic[mode] = candidate
            elif semantic[mode] != candidate:
                raise PsiTwoPassQualificationError(
                    f"performance {mode} output changed across repeats"
                )
            elapsed[mode].append(Decimal(report["elapsed_seconds"]))
            walls[mode].append(wall)
    assert semantic["summary"] is not None and semantic["verify"] is not None
    _same_common(semantic["summary"], semantic["verify"], "performance")
    expected = {
        "summary_records": value["summary_records"],
        "verify_records": value["verify_records"],
        "summary_elapsed_median": _decimal_text(_median(elapsed["summary"])),
        "verify_elapsed_median": _decimal_text(_median(elapsed["verify"])),
        "two_pass_elapsed_median": _decimal_text(
            _median(elapsed["summary"]) + _median(elapsed["verify"])
        ),
        "summary_wall_median": _decimal_text(_median(walls["summary"])),
        "verify_wall_median": _decimal_text(_median(walls["verify"])),
        "two_pass_wall_median": _decimal_text(
            _median(walls["summary"]) + _median(walls["verify"])
        ),
    }
    if dict(value) != expected:
        raise PsiTwoPassQualificationError(
            "performance timing arithmetic differs from raw records"
        )
    return expected, semantic  # type: ignore[return-value]


def _comparison(
    candidate: Mapping[str, Any], baseline: Mapping[str, Any]
) -> dict[str, Any]:
    fields = (
        ("summary_elapsed", "summary_elapsed_median"),
        ("verify_elapsed", "verify_elapsed_median"),
        ("two_pass_elapsed", "two_pass_elapsed_median"),
        ("summary_wall", "summary_wall_median"),
        ("verify_wall", "verify_wall_median"),
        ("two_pass_wall", "two_pass_wall_median"),
    )
    result: dict[str, Any] = {"semantic_outputs_equal_ignoring_timing": True}
    for label, field in fields:
        result[f"{label}_speedup"] = _decimal_text(
            _ratio(
                _decimal(baseline[field], f"baseline {field}"),
                _decimal(candidate[field], f"candidate {field}"),
                f"{label} speedup",
            )
        )
    return result


def _projection(
    candidate: Mapping[str, Any], events: int
) -> dict[str, Any]:
    two_pass = _decimal(
        candidate["two_pass_wall_median"], "candidate two-pass wall"
    )
    rate = _ratio(Decimal(2 * events), two_pass, "event-pass rate")
    source_seconds = _ratio(
        Decimal(2 * SOURCE_EVENT_COUNT), rate, "linear source projection"
    )
    return {
        "bounded_prime_power_events_per_pass": events,
        "candidate_event_passes_per_second": _decimal_text(rate),
        "published_source_event_count_per_pass": SOURCE_EVENT_COUNT,
        "linear_two_pass_source_seconds": _decimal_text(source_seconds),
        "linear_two_pass_source_hours": _decimal_text(
            source_seconds / Decimal(3600)
        ),
        "is_source_run": False,
    }


def _identity(
    candidate_runner: Path,
    baseline_runner: Path,
    runner_source: Path,
    upstream_manifest: Path,
    crlibm_shared: Path,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for path, prefix, maximum in (
        (candidate_runner, "candidate_runner", MAX_RUNNER_BYTES),
        (baseline_runner, "baseline_runner", MAX_RUNNER_BYTES),
        (runner_source, "source", MAX_SOURCE_BYTES),
        (upstream_manifest, "upstream_manifest", MAX_SOURCE_BYTES),
        (crlibm_shared, "crlibm_shared", MAX_RUNNER_BYTES),
    ):
        try:
            digest, size = hash_file_once(path, limit=maximum)
        except CampaignIOError as exc:
            raise PsiTwoPassQualificationError(str(exc)) from exc
        result[f"{prefix}_sha256"] = digest
        result[f"{prefix}_size_bytes"] = size
    try:
        raw = upstream_manifest.read_bytes()
        _validate_upstream_manifest(raw)
    except (OSError, PsiResidualCampaignError) as exc:
        raise PsiTwoPassQualificationError(str(exc)) from exc
    return result


def run_qualification(
    *,
    candidate_runner: Path,
    baseline_runner: Path,
    runner_source: Path,
    upstream_manifest: Path,
    crlibm_shared: Path,
    output: Path,
    domain_upper_exclusive: int,
    shard_span: int,
    sieve_size_kib: int = 384,
    series_terms: int = 32,
    oracle_segment_size: int = 100_000,
    repeat_count: int = 3,
    performance_lower: int,
    performance_upper_exclusive: int,
    performance_repeat_count: int = 3,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Run one bounded literal-oracle and optimized/baseline qualification."""

    if output.exists():
        raise PsiTwoPassQualificationError(
            f"refusing to overwrite qualification artifact: {output}"
        )
    ranges = _ranges(domain_upper_exclusive, shard_span)
    sieve = _integer(sieve_size_kib, "sieve size", minimum=16)
    if sieve > 8192:
        raise PsiTwoPassQualificationError("sieve size exceeds 8192 KiB")
    terms = _integer(series_terms, "series terms", minimum=1)
    segment = _integer(
        oracle_segment_size, "oracle segment size", minimum=1
    )
    repeats = _integer(repeat_count, "repeat count", minimum=1)
    performance_repeats = _integer(
        performance_repeat_count, "performance repeat count", minimum=1
    )
    perf_lower = _integer(performance_lower, "performance lower", minimum=2)
    perf_upper = _integer(
        performance_upper_exclusive, "performance upper exclusive", minimum=3
    )
    if not perf_lower < perf_upper <= SOURCE_UPPER_EXCLUSIVE:
        raise PsiTwoPassQualificationError("performance range is invalid")
    if timeout_seconds is not None:
        _integer(timeout_seconds, "timeout seconds", minimum=1)

    identity = _identity(
        candidate_runner,
        baseline_runner,
        runner_source,
        upstream_manifest,
        crlibm_shared,
    )
    oracle = _literal_oracle(
        crlibm_shared=crlibm_shared,
        ranges=ranges,
        series_terms=terms,
        segment_size=segment,
    )
    entries = oracle["semantics"]["entries"]
    candidate = _run_binary_root_campaign(
        candidate_runner,
        ranges=ranges,
        oracle_entries=entries,
        sieve_size_kib=sieve,
        repeat_count=repeats,
        timeout_seconds=timeout_seconds,
    )
    baseline = _run_binary_root_campaign(
        baseline_runner,
        ranges=ranges,
        oracle_entries=entries,
        sieve_size_kib=sieve,
        repeat_count=repeats,
        timeout_seconds=timeout_seconds,
    )

    incoming = ((perf_lower - 1) << 64, (perf_lower - 1) << 64)
    candidate_performance = _performance_binary(
        candidate_runner,
        lower=perf_lower,
        upper=perf_upper,
        sieve_size_kib=sieve,
        incoming=incoming,
        repeat_count=performance_repeats,
        timeout_seconds=timeout_seconds,
    )
    baseline_performance = _performance_binary(
        baseline_runner,
        lower=perf_lower,
        upper=perf_upper,
        sieve_size_kib=sieve,
        incoming=incoming,
        repeat_count=performance_repeats,
        timeout_seconds=timeout_seconds,
    )
    candidate_semantic = _without_elapsed(
        _decode_record(
            candidate_performance["summary_records"][0],
            index=0,
            mode="summary",
            bounds=(perf_lower, perf_upper),
            sieve_size_kib=sieve,
            incoming=None,
        )[0]
    )
    baseline_semantic = _without_elapsed(
        _decode_record(
            baseline_performance["summary_records"][0],
            index=0,
            mode="summary",
            bounds=(perf_lower, perf_upper),
            sieve_size_kib=sieve,
            incoming=None,
        )[0]
    )
    if candidate_semantic != baseline_semantic:
        raise PsiTwoPassQualificationError(
            "candidate performance output differs from baseline"
        )
    events = candidate_semantic["prime_power_events"]
    performance = {
        "configuration": {
            "lower": perf_lower,
            "upper_exclusive": perf_upper,
            "sieve_size_kib": sieve,
            "repeat_count": performance_repeats,
            "incoming_state": list(incoming),
            "incoming_state_is_root_derived": False,
        },
        "candidate": candidate_performance,
        "baseline": baseline_performance,
        "comparison": _comparison(
            candidate_performance, baseline_performance
        ),
        "linear_source_projection": _projection(
            candidate_performance, events
        ),
        "scope": (
            "bounded_source_height_synthetic_safe_state_performance_only_not_source_run"
        ),
    }
    artifact = {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "classification": CLASSIFICATION,
        "identity": identity,
        "configuration": {
            "domain_lower": 2,
            "domain_upper_exclusive": domain_upper_exclusive,
            "shard_span": shard_span,
            "shard_count": len(ranges),
            "sieve_size_kib": sieve,
            "series_terms": terms,
            "oracle_segment_size": segment,
            "repeat_count": repeats,
        },
        "oracle": oracle,
        "executions": {"candidate": candidate, "baseline": baseline},
        "performance": performance,
        "checks": {
            "literal_prime_power_roster_replayed": True,
            "every_crlibm_q64_pair_contains_rational_oracle": True,
            "event_commitments_match_oracle": True,
            "row_commitments_match_oracle": True,
            "summary_verify_deltas_match_oracle": True,
            "root_derived_incoming_states_match": True,
            "every_gap_guard_replayed": True,
            "ordered_merge_and_final_state_match": True,
            "candidate_repeats_match_ignoring_timing": True,
            "baseline_candidate_match_ignoring_timing": True,
            "performance_outputs_match_ignoring_timing": True,
        },
        "capabilities": {
            "bounded_qualification_complete": True,
            "full_source_range": False,
            "primesieve_to_mathlib_realization_proved": False,
            "crlibm_to_mathlib_realization_proved": False,
            "compiler_or_cpu_refinement_proved": False,
            "source_run_completed": False,
            "execution_attested": False,
            "receipt_admitted": False,
            "lean_atom_discharged": False,
            "linear_source_projection_is_proof": False,
        },
    }
    _decode_and_check(
        artifact,
        candidate_runner=candidate_runner,
        baseline_runner=baseline_runner,
        runner_source=runner_source,
        upstream_manifest=upstream_manifest,
        crlibm_shared=crlibm_shared,
        regenerate_oracle=False,
    )
    raw = canonical_json_bytes(artifact)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream:
            if stream.write(raw) != len(raw):
                raise PsiTwoPassQualificationError(
                    "short qualification artifact write"
                )
    except FileExistsError as exc:
        raise PsiTwoPassQualificationError(
            f"refusing to overwrite qualification artifact: {output}"
        ) from exc
    except OSError as exc:
        raise PsiTwoPassQualificationError(
            f"cannot write qualification artifact: {exc}"
        ) from exc
    return artifact


def _decode_and_check(
    artifact: Mapping[str, Any],
    *,
    candidate_runner: Path,
    baseline_runner: Path,
    runner_source: Path,
    upstream_manifest: Path,
    crlibm_shared: Path,
    regenerate_oracle: bool,
) -> dict[str, Any]:
    if set(artifact) != _TOP_FIELDS:
        raise PsiTwoPassQualificationError("qualification fields changed")
    if (
        artifact.get("schema"),
        artifact.get("algorithm"),
        artifact.get("classification"),
    ) != (SCHEMA, ALGORITHM, CLASSIFICATION):
        raise PsiTwoPassQualificationError("qualification identity changed")
    identity = artifact.get("identity")
    if not isinstance(identity, dict) or set(identity) != _IDENTITY_FIELDS:
        raise PsiTwoPassQualificationError("file identity fields changed")
    if identity != _identity(
        candidate_runner,
        baseline_runner,
        runner_source,
        upstream_manifest,
        crlibm_shared,
    ):
        raise PsiTwoPassQualificationError("bound file identity changed")

    config = artifact.get("configuration")
    if not isinstance(config, dict) or set(config) != _CONFIG_FIELDS:
        raise PsiTwoPassQualificationError("configuration fields changed")
    if config.get("domain_lower") != 2:
        raise PsiTwoPassQualificationError("qualification root changed")
    ranges = _ranges(
        _integer(
            config.get("domain_upper_exclusive"),
            "domain upper exclusive",
            minimum=3,
        ),
        _integer(config.get("shard_span"), "shard span", minimum=1),
    )
    if config.get("shard_count") != len(ranges):
        raise PsiTwoPassQualificationError("shard count changed")
    sieve = _integer(config.get("sieve_size_kib"), "sieve size", minimum=16)
    if sieve > 8192:
        raise PsiTwoPassQualificationError("sieve size exceeds 8192 KiB")
    terms = _integer(config.get("series_terms"), "series terms", minimum=1)
    segment = _integer(
        config.get("oracle_segment_size"), "oracle segment", minimum=1
    )
    repeats = _integer(config.get("repeat_count"), "repeat count", minimum=1)

    oracle = artifact.get("oracle")
    if not isinstance(oracle, dict) or set(oracle) != _ORACLE_FIELDS:
        raise PsiTwoPassQualificationError("oracle fields changed")
    timing = oracle.get("timing")
    if not isinstance(timing, dict) or set(timing) != _ORACLE_TIMING_FIELDS:
        raise PsiTwoPassQualificationError("oracle timing fields changed")
    for field in _ORACLE_TIMING_FIELDS - {"scope"}:
        _decimal(timing.get(field), f"oracle timing {field}")
    if timing.get("scope") != (
        "bounded_python_roster_rational_log_and_loaded_crlibm_oracle_timing"
    ):
        raise PsiTwoPassQualificationError("oracle timing scope changed")
    semantics = oracle.get("semantics")
    if not isinstance(semantics, dict) or set(semantics) != _ORACLE_SEMANTIC_FIELDS:
        raise PsiTwoPassQualificationError("oracle semantic fields changed")
    entries = semantics.get("entries")
    if not isinstance(entries, list) or len(entries) != len(ranges):
        raise PsiTwoPassQualificationError("oracle entries are incomplete")
    root_state = _state(semantics.get("root_state"), "oracle root state")
    if root_state != (0, 0):
        raise PsiTwoPassQualificationError("oracle root state changed")
    current = root_state
    total_events = 0
    total_primes = 0
    total_higher_powers = 0
    for index, (entry, bounds) in enumerate(zip(entries, ranges, strict=True)):
        if not isinstance(entry, dict) or set(entry) != _ORACLE_ENTRY_FIELDS:
            raise PsiTwoPassQualificationError("oracle entry fields changed")
        if (
            entry.get("index"),
            entry.get("lower"),
            entry.get("upper_exclusive"),
        ) != (index, bounds[0], bounds[1]):
            raise PsiTwoPassQualificationError(
                f"oracle entry order/range changed at {index}"
            )
        event_count = _integer(
            entry.get("prime_power_events"),
            "oracle prime-power event count",
            minimum=0,
        )
        prime_count = _integer(
            entry.get("prime_events"), "oracle prime event count", minimum=0
        )
        higher_count = _integer(
            entry.get("higher_power_events"),
            "oracle higher-power event count",
            minimum=0,
        )
        if event_count != prime_count + higher_count:
            raise PsiTwoPassQualificationError(
                f"oracle event-count partition changed at {index}"
            )
        _sha256_hex(entry.get("event_sha256"), "oracle event commitment")
        _sha256_hex(entry.get("row_sha256"), "oracle row commitment")
        incoming_state = _state(entry.get("incoming"), "oracle incoming")
        outgoing_state = _state(entry.get("outgoing"), "oracle outgoing")
        delta = _state(entry.get("delta"), "oracle delta")
        if incoming_state != current:
            raise PsiTwoPassQualificationError(
                f"oracle incoming-state chain changed at {index}"
            )
        expected_outgoing = (
            incoming_state[0] + delta[0],
            incoming_state[1] + delta[1],
        )
        if expected_outgoing[1] >= U128_LIMIT:
            raise PsiTwoPassQualificationError(
                f"oracle state addition overflows u128 at {index}"
            )
        if outgoing_state != expected_outgoing:
            raise PsiTwoPassQualificationError(
                f"oracle affine state fold changed at {index}"
            )
        fallbacks = entry.get("exact_fallbacks")
        if not isinstance(fallbacks, dict) or set(fallbacks) != FALLBACK_FIELDS:
            raise PsiTwoPassQualificationError("oracle fallback fields changed")
        for field in FALLBACK_FIELDS:
            _integer(
                fallbacks.get(field),
                f"oracle {field} fallback count",
                minimum=0,
            )
        if entry.get("all_gap_guards_accept") is not True:
            raise PsiTwoPassQualificationError("oracle gap acceptance changed")
        current = outgoing_state
        total_events += event_count
        total_primes += prime_count
        total_higher_powers += higher_count
    retained_totals = (
        _integer(
            semantics.get("prime_power_events"),
            "oracle total prime-power events",
            minimum=0,
        ),
        _integer(
            semantics.get("prime_events"),
            "oracle total prime events",
            minimum=0,
        ),
        _integer(
            semantics.get("higher_power_events"),
            "oracle total higher-power events",
            minimum=0,
        ),
    )
    if retained_totals != (total_events, total_primes, total_higher_powers):
        raise PsiTwoPassQualificationError("oracle retained totals differ from shards")
    unique_primes = _integer(
        semantics.get("unique_primes"), "oracle unique primes", minimum=0
    )
    rational_pairs = _integer(
        semantics.get("rational_log_pairs_enclosed"),
        "oracle rational log pairs",
        minimum=0,
    )
    if unique_primes != total_primes or rational_pairs != unique_primes:
        raise PsiTwoPassQualificationError(
            "oracle prime/log cardinalities differ from the rooted roster"
        )
    if _state(semantics.get("final_state"), "oracle final state") != current:
        raise PsiTwoPassQualificationError("oracle final state differs from shard fold")
    if regenerate_oracle:
        regenerated = _literal_oracle(
            crlibm_shared=crlibm_shared,
            ranges=ranges,
            series_terms=terms,
            segment_size=segment,
        )
        if regenerated["semantics"] != semantics:
            raise PsiTwoPassQualificationError(
                "retained oracle differs from fresh literal replay"
            )

    executions = artifact.get("executions")
    if not isinstance(executions, dict) or set(executions) != _EXECUTION_FIELDS:
        raise PsiTwoPassQualificationError("execution fields changed")
    decoded_candidate = _decode_binary_root_campaign(
        executions["candidate"],
        ranges=ranges,
        oracle_entries=entries,
        sieve_size_kib=sieve,
        repeat_count=repeats,
    )
    decoded_baseline = _decode_binary_root_campaign(
        executions["baseline"],
        ranges=ranges,
        oracle_entries=entries,
        sieve_size_kib=sieve,
        repeat_count=repeats,
    )
    for candidate_run, baseline_run in zip(
        decoded_candidate, decoded_baseline, strict=True
    ):
        for mode in ("summary", "verify"):
            if [
                _without_elapsed(report) for report in candidate_run[mode]
            ] != [
                _without_elapsed(report) for report in baseline_run[mode]
            ]:
                raise PsiTwoPassQualificationError(
                    "candidate output differs from baseline ignoring timing"
                )

    performance = artifact.get("performance")
    if not isinstance(performance, dict) or set(performance) != _PERFORMANCE_FIELDS:
        raise PsiTwoPassQualificationError("performance fields changed")
    perf_config = performance.get("configuration")
    if (
        not isinstance(perf_config, dict)
        or set(perf_config) != _PERFORMANCE_CONFIG_FIELDS
    ):
        raise PsiTwoPassQualificationError("performance configuration changed")
    perf_lower = _integer(perf_config.get("lower"), "performance lower", minimum=2)
    perf_upper = _integer(
        perf_config.get("upper_exclusive"), "performance upper", minimum=3
    )
    if not perf_lower < perf_upper <= SOURCE_UPPER_EXCLUSIVE:
        raise PsiTwoPassQualificationError("performance range changed")
    if perf_config.get("sieve_size_kib") != sieve:
        raise PsiTwoPassQualificationError("performance sieve size changed")
    perf_repeats = _integer(
        perf_config.get("repeat_count"), "performance repeats", minimum=1
    )
    incoming = _state(perf_config.get("incoming_state"), "performance incoming")
    if incoming != ((perf_lower - 1) << 64, (perf_lower - 1) << 64):
        raise PsiTwoPassQualificationError("performance synthetic state changed")
    if perf_config.get("incoming_state_is_root_derived") is not False:
        raise PsiTwoPassQualificationError(
            "performance state made an unsafe root-derived claim"
        )
    candidate_perf, candidate_semantic = _decode_performance_binary(
        performance.get("candidate"),
        lower=perf_lower,
        upper=perf_upper,
        sieve_size_kib=sieve,
        incoming=incoming,
        repeat_count=perf_repeats,
    )
    baseline_perf, baseline_semantic = _decode_performance_binary(
        performance.get("baseline"),
        lower=perf_lower,
        upper=perf_upper,
        sieve_size_kib=sieve,
        incoming=incoming,
        repeat_count=perf_repeats,
    )
    if candidate_semantic != baseline_semantic:
        raise PsiTwoPassQualificationError(
            "performance candidate differs from baseline ignoring timing"
        )
    expected_comparison = _comparison(candidate_perf, baseline_perf)
    comparison = performance.get("comparison")
    if (
        not isinstance(comparison, dict)
        or set(comparison) != _PERFORMANCE_COMPARISON_FIELDS
        or comparison != expected_comparison
    ):
        raise PsiTwoPassQualificationError("performance comparison changed")
    events = candidate_semantic["summary"]["prime_power_events"]
    expected_projection = _projection(candidate_perf, events)
    projection = performance.get("linear_source_projection")
    if (
        not isinstance(projection, dict)
        or set(projection) != _PROJECTION_FIELDS
        or projection != expected_projection
    ):
        raise PsiTwoPassQualificationError("linear source projection changed")
    if performance.get("scope") != (
        "bounded_source_height_synthetic_safe_state_performance_only_not_source_run"
    ):
        raise PsiTwoPassQualificationError("performance scope changed")

    checks = artifact.get("checks")
    if (
        not isinstance(checks, dict)
        or set(checks) != _CHECK_FIELDS
        or any(value is not True for value in checks.values())
    ):
        raise PsiTwoPassQualificationError("qualification checks changed")
    expected_capabilities = {
        "bounded_qualification_complete": True,
        "full_source_range": False,
        "primesieve_to_mathlib_realization_proved": False,
        "crlibm_to_mathlib_realization_proved": False,
        "compiler_or_cpu_refinement_proved": False,
        "source_run_completed": False,
        "execution_attested": False,
        "receipt_admitted": False,
        "lean_atom_discharged": False,
        "linear_source_projection_is_proof": False,
    }
    capabilities = artifact.get("capabilities")
    if (
        not isinstance(capabilities, dict)
        or set(capabilities) != _CAPABILITY_FIELDS
        or capabilities != expected_capabilities
    ):
        raise PsiTwoPassQualificationError("capability boundary changed")
    return dict(artifact)


def verify_qualification(
    path: Path,
    *,
    candidate_runner: Path,
    baseline_runner: Path,
    runner_source: Path,
    upstream_manifest: Path,
    crlibm_shared: Path,
    regenerate_oracle: bool = True,
) -> dict[str, Any]:
    """Replay a retained qualification, regenerating the literal oracle."""

    try:
        value = load_json(path, require_canonical=True)
    except CampaignIOError as exc:
        raise PsiTwoPassQualificationError(str(exc)) from exc
    if not isinstance(value, dict):
        raise PsiTwoPassQualificationError("qualification root is not an object")
    return _decode_and_check(
        value,
        candidate_runner=candidate_runner,
        baseline_runner=baseline_runner,
        runner_source=runner_source,
        upstream_manifest=upstream_manifest,
        crlibm_shared=crlibm_shared,
        regenerate_oracle=regenerate_oracle,
    )


def qualification_summary(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "qualification_sha256": canonical_sha256(dict(artifact)),
        "configuration": artifact["configuration"],
        "oracle": {
            "prime_power_events": artifact["oracle"]["semantics"][
                "prime_power_events"
            ],
            "higher_power_events": artifact["oracle"]["semantics"][
                "higher_power_events"
            ],
            "unique_primes": artifact["oracle"]["semantics"]["unique_primes"],
            "final_state": artifact["oracle"]["semantics"]["final_state"],
            "timing": artifact["oracle"]["timing"],
        },
        "performance": {
            "candidate": {
                key: value
                for key, value in artifact["performance"]["candidate"].items()
                if key.endswith("_median")
            },
            "baseline": {
                key: value
                for key, value in artifact["performance"]["baseline"].items()
                if key.endswith("_median")
            },
            "comparison": artifact["performance"]["comparison"],
            "linear_source_projection": artifact["performance"][
                "linear_source_projection"
            ],
        },
        "capabilities": artifact["capabilities"],
    }


__all__ = [
    "ALGORITHM",
    "CLASSIFICATION",
    "PsiTwoPassQualificationError",
    "SCHEMA",
    "qualification_summary",
    "run_qualification",
    "verify_qualification",
]
