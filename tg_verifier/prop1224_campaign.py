# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Full-domain, resumable campaign for Helfgott Proposition 12.2.4.

The source domain has 3,389,047,618 admissible ``q`` values.  This driver
always starts at ``q = 1`` and uses the exact source scheduler; ``max_chunks``
only pauses that same campaign.  It never relabels a bounded run as full.

For one ``q``, ``G_q(k)`` is streamed as a directed dyadic interval.  This is
important at ``q = 1``, whose conservative window contains over 23 million
candidate ``k`` values: neither the candidates nor the exact rational prefix
are retained in memory.  Each compact receipt commits to every arithmetic
step and can be regenerated independently from the immutable configuration.

Even a completed replay remains an external Python computation.  There is no
Lean realization theorem for this evaluator, so no result from this module
claims to discharge the Lean atom.
"""

from __future__ import annotations

from array import array
from dataclasses import asdict, dataclass
from fractions import Fraction
import hashlib
from math import gcd, isqrt
from pathlib import Path
import platform
import re
from typing import Any, Iterator, Mapping, Sequence

from . import campaign_io, finite_campaigns, prop1224_directed
from .arithmetic import ZERO_SHA256
from .campaign_io import (
    CampaignIOError,
    advisory_lock,
    atomic_write_json,
    canonical_json_bytes,
    hash_file_once,
    load_json,
    write_immutable_json,
)
from .finite_campaigns import (
    FiniteCampaignError,
    PROP1224_ATOM,
    PROP1224_Q_END,
    PROP1224_Q_SPLIT,
    prop1224_first_extension_q,
    prop1224_next_q,
    prop1224_q_is_admissible,
    prop1224_source_q_count,
)
from .prop1224_directed import (
    DEFAULT_BITS,
    DEFAULT_LOG_TERMS,
    Prop1224DirectedParameters,
    prop1224_directed_margin_lower_from_g_upper,
    prop1224_directed_parameters,
)


CAMPAIGN_ALGORITHM = "prop1224_directed_fixedpoint_campaign_v1"
ARITHMETIC_DIGEST_ENCODING = "prop1224-directed-step-lines-v1"
CONFIG_NAME = "campaign-config.json"
MANIFEST_NAME = "campaign-manifest.json"
RECEIPT_PATTERN = re.compile(r"receipt-([0-9]{10})\.json\Z")
MAX_RECEIPTS = 10**10


class Prop1224CampaignError(RuntimeError):
    """A campaign configuration, receipt, transition, or replay failed."""


@dataclass(frozen=True)
class CampaignState:
    """The next exact arithmetic state in the source scheduler."""

    q: int
    next_r: int
    g_lower_units: int
    g_upper_units: int


@dataclass(frozen=True)
class Prop1224CampaignResult:
    source_q_rows: int
    completed_q_rows: int
    next_q: int
    next_r: int
    receipts: int
    r_steps: int
    conservative_k_rows_checked: int
    complete: bool
    final_receipt_hash: str
    compact_chain_verified: bool
    locally_supervised_execution: bool
    replayed_receipts: int
    fresh_arithmetic_replay: bool
    full_source_q_scheduler_coverage_recorded: bool
    execution_attested: bool = False
    lean_realization_proved: bool = False
    lean_atom_discharged: bool = False

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def _integer(value: object, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Prop1224CampaignError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise Prop1224CampaignError(f"{name} must be at least {minimum}")
    return value


def _digest(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise Prop1224CampaignError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _ceil(value: Fraction) -> int:
    return -((-value.numerator) // value.denominator)


def _fraction_pair(value: Fraction) -> list[int]:
    return [value.numerator, value.denominator]


def _fraction_from_pair(value: object, name: str) -> Fraction:
    if not isinstance(value, list) or len(value) != 2:
        raise Prop1224CampaignError(f"{name} must be a numerator/denominator pair")
    numerator = _integer(value[0], f"{name}.numerator")
    denominator = _integer(value[1], f"{name}.denominator", minimum=1)
    result = Fraction(numerator, denominator)
    if (result.numerator, result.denominator) != (numerator, denominator):
        raise Prop1224CampaignError(f"{name} must be in canonical lowest terms")
    return result


def _source_hashes() -> dict[str, str]:
    return {
        "finite_campaigns_source_sha256": hash_file_once(
            Path(finite_campaigns.__file__).resolve()
        )[0],
        "prop1224_directed_source_sha256": hash_file_once(
            Path(prop1224_directed.__file__).resolve()
        )[0],
        "prop1224_campaign_source_sha256": hash_file_once(
            Path(__file__).resolve()
        )[0],
        "campaign_io_source_sha256": hash_file_once(
            Path(campaign_io.__file__).resolve()
        )[0],
    }


def _validate_parameters(
    *,
    precision_bits: int,
    log_series_terms: int,
    r_steps_per_chunk: int,
    q_rows_per_chunk: int,
    sieve_segment_size: int,
    max_chunks: int | None,
) -> None:
    for value, name, lower, upper in (
        (precision_bits, "precision_bits", 32, 4_096),
        (log_series_terms, "log_series_terms", 8, 4_096),
        (r_steps_per_chunk, "r_steps_per_chunk", 1, 100_000_000),
        (q_rows_per_chunk, "q_rows_per_chunk", 1, 100_000_000),
        (sieve_segment_size, "sieve_segment_size", 1, 10_000_000),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not lower <= value <= upper
        ):
            raise Prop1224CampaignError(f"{name} must lie in [{lower}, {upper}]")
    if max_chunks is not None and (
        isinstance(max_chunks, bool)
        or not isinstance(max_chunks, int)
        or max_chunks < 1
    ):
        raise Prop1224CampaignError("max_chunks must be positive or null")


def _expected_config(
    *,
    precision_bits: int,
    log_series_terms: int,
    r_steps_per_chunk: int,
    q_rows_per_chunk: int,
    sieve_segment_size: int,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "algorithm": CAMPAIGN_ALGORITHM,
        "classification": "full_source_capable_external_computation_not_lean_proof",
        "atom_id": PROP1224_ATOM,
        "source_domain": {
            "initial_q": 1,
            "dense_q_upper_exclusive": PROP1224_Q_SPLIT,
            "extension_q_upper_exclusive": PROP1224_Q_END,
            "extension_divisor": finite_campaigns.PROP1224_DIVISOR,
            "admissible_q_rows": prop1224_source_q_count(),
        },
        "precision_bits": precision_bits,
        "log_series_terms": log_series_terms,
        "g_fixed_point_scale": 1 << precision_bits,
        "r_steps_per_chunk": r_steps_per_chunk,
        "q_rows_per_chunk": q_rows_per_chunk,
        "sieve_segment_size": sieve_segment_size,
        "arithmetic_digest_encoding": ARITHMETIC_DIGEST_ENCODING,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        **_source_hashes(),
    }


def _load_config(output_directory: Path) -> dict[str, Any]:
    path = output_directory / CONFIG_NAME
    try:
        value = load_json(path, require_canonical=True)
    except CampaignIOError as exc:
        raise Prop1224CampaignError(str(exc)) from exc
    if not isinstance(value, dict):
        raise Prop1224CampaignError("campaign config must be a JSON object")
    try:
        _validate_parameters(
            precision_bits=value.get("precision_bits"),
            log_series_terms=value.get("log_series_terms"),
            r_steps_per_chunk=value.get("r_steps_per_chunk"),
            q_rows_per_chunk=value.get("q_rows_per_chunk"),
            sieve_segment_size=value.get("sieve_segment_size"),
            max_chunks=None,
        )
        expected = _expected_config(
            precision_bits=value["precision_bits"],
            log_series_terms=value["log_series_terms"],
            r_steps_per_chunk=value["r_steps_per_chunk"],
            q_rows_per_chunk=value["q_rows_per_chunk"],
            sieve_segment_size=value["sieve_segment_size"],
        )
    except (KeyError, TypeError) as exc:
        raise Prop1224CampaignError("campaign config fields are malformed") from exc
    if value != expected:
        raise Prop1224CampaignError("campaign configuration or source identity changed")
    return value


def _initialize_or_check(
    output_directory: Path,
    *,
    precision_bits: int,
    log_series_terms: int,
    r_steps_per_chunk: int,
    q_rows_per_chunk: int,
    sieve_segment_size: int,
) -> dict[str, Any]:
    expected = _expected_config(
        precision_bits=precision_bits,
        log_series_terms=log_series_terms,
        r_steps_per_chunk=r_steps_per_chunk,
        q_rows_per_chunk=q_rows_per_chunk,
        sieve_segment_size=sieve_segment_size,
    )
    path = output_directory / CONFIG_NAME
    try:
        if path.exists():
            current = _load_config(output_directory)
            if current != expected:
                raise Prop1224CampaignError("resume configuration changed")
        else:
            write_immutable_json(path, expected)
    except CampaignIOError as exc:
        raise Prop1224CampaignError(str(exc)) from exc
    return expected


def _simple_primes(limit: int) -> list[int]:
    if limit < 2:
        return []
    composite = bytearray(limit + 1)
    for prime in range(2, isqrt(limit) + 1):
        if composite[prime]:
            continue
        first = prime * prime
        composite[first : limit + 1 : prime] = b"\x01" * (
            (limit - first) // prime + 1
        )
    return [value for value in range(2, limit + 1) if not composite[value]]


def iter_totient_squarefree_segment(
    lower: int, upper: int, *, segment_size: int
) -> Iterator[tuple[int, int, bool]]:
    """Yield exact ``(r, phi(r), squarefree(r))`` rows in ``[lower, upper)``.

    Only the current segment and primes through its square root are retained.
    The routine is intentionally public so an independent checker can test
    the finite-sieve layer separately from the transcendental evaluator.
    """

    lower = _integer(lower, "lower", minimum=1)
    upper = _integer(upper, "upper", minimum=1)
    segment_size = _integer(segment_size, "segment_size", minimum=1)
    if upper < lower:
        raise Prop1224CampaignError("upper must not be below lower")
    for lo in range(lower, upper, segment_size):
        hi = min(upper, lo + segment_size)
        phi = array("Q", range(lo, hi))
        remainder = array("Q", range(lo, hi))
        squarefree = bytearray(b"\x01") * (hi - lo)
        for prime in _simple_primes(isqrt(hi - 1)):
            first = ((lo + prime - 1) // prime) * prime
            for multiple in range(first, hi, prime):
                index = multiple - lo
                phi[index] -= phi[index] // prime
                exponent = 0
                while remainder[index] % prime == 0:
                    remainder[index] //= prime
                    exponent += 1
                if exponent > 1:
                    squarefree[index] = 0
        for index, r in enumerate(range(lo, hi)):
            leftover = remainder[index]
            if leftover > 1:
                phi[index] -= phi[index] // leftover
            yield r, int(phi[index]), bool(squarefree[index])


def _q_rank(q: int) -> int:
    """Zero-based source rank, with the terminal sentinel at row count."""

    if q == PROP1224_Q_END:
        return prop1224_source_q_count()
    if not prop1224_q_is_admissible(q):
        raise Prop1224CampaignError(f"q={q} is not in the source scheduler")
    if q < PROP1224_Q_SPLIT:
        return q - 1
    first = prop1224_first_extension_q()
    return PROP1224_Q_SPLIT - 1 + (q - first) // finite_campaigns.PROP1224_DIVISOR


def _q_at_rank(rank: int) -> int:
    rank = _integer(rank, "q rank", minimum=0)
    total = prop1224_source_q_count()
    if rank > total:
        raise Prop1224CampaignError("q rank exceeds the source scheduler")
    if rank == total:
        return PROP1224_Q_END
    dense = PROP1224_Q_SPLIT - 1
    if rank < dense:
        return rank + 1
    return prop1224_first_extension_q() + (
        rank - dense
    ) * finite_campaigns.PROP1224_DIVISOR


def _advance_q(q: int, count: int) -> int:
    count = _integer(count, "q row count", minimum=0)
    return _q_at_rank(_q_rank(q) + count)


def _window(parameters: Prop1224DirectedParameters) -> tuple[int, int]:
    return (
        max(1, _ceil(parameters.varpi.lower)),
        _ceil(parameters.lambda_.upper) - 1,
    )


def _interval_token(lower: Fraction, upper: Fraction) -> str:
    return (
        f"{lower.numerator}/{lower.denominator}:"
        f"{upper.numerator}/{upper.denominator}"
    )


def _hash_q_header(
    digest: Any,
    parameters: Prop1224DirectedParameters,
    first: int,
    last: int,
) -> None:
    digest.update(
        (
            f"Q:{parameters.q}:{parameters.phi_q}:"
            f"{','.join(str(p) for p in parameters.prime_factors)}:"
            f"{_interval_token(parameters.varpi.lower, parameters.varpi.upper)}:"
            f"{_interval_token(parameters.lambda_.lower, parameters.lambda_.upper)}:"
            f"{first}:{last}\n"
        ).encode("ascii")
    )


def _initial_state() -> CampaignState:
    return CampaignState(q=1, next_r=1, g_lower_units=0, g_upper_units=0)


def _validate_state(state: CampaignState, *, name: str, allow_terminal: bool) -> None:
    if not isinstance(state, CampaignState):
        raise Prop1224CampaignError(f"{name} has the wrong type")
    _integer(state.next_r, f"{name}.next_r", minimum=1)
    _integer(state.g_lower_units, f"{name}.g_lower_units", minimum=0)
    _integer(state.g_upper_units, f"{name}.g_upper_units", minimum=0)
    if state.g_lower_units > state.g_upper_units:
        raise Prop1224CampaignError(f"{name} has a reversed G interval")
    if state.q == PROP1224_Q_END:
        if not allow_terminal:
            raise Prop1224CampaignError(f"{name} may not be terminal")
        if state != CampaignState(PROP1224_Q_END, 1, 0, 0):
            raise Prop1224CampaignError("terminal campaign state must be canonical")
    elif not prop1224_q_is_admissible(state.q):
        raise Prop1224CampaignError(f"{name}.q is outside the source scheduler")
    if state.next_r == 1 and (state.g_lower_units or state.g_upper_units):
        raise Prop1224CampaignError(f"{name} has nonzero G state at r=1")


def _state_json(state: CampaignState, prefix: str) -> dict[str, int]:
    return {
        f"{prefix}_q": state.q,
        f"{prefix}_next_r": state.next_r,
        f"{prefix}_g_lower_units": state.g_lower_units,
        f"{prefix}_g_upper_units": state.g_upper_units,
    }


def _state_from_receipt(report: Mapping[str, Any], prefix: str) -> CampaignState:
    return CampaignState(
        q=_integer(report.get(f"{prefix}_q"), f"{prefix}_q", minimum=1),
        next_r=_integer(
            report.get(f"{prefix}_next_r"), f"{prefix}_next_r", minimum=1
        ),
        g_lower_units=_integer(
            report.get(f"{prefix}_g_lower_units"),
            f"{prefix}_g_lower_units",
            minimum=0,
        ),
        g_upper_units=_integer(
            report.get(f"{prefix}_g_upper_units"),
            f"{prefix}_g_upper_units",
            minimum=0,
        ),
    )


def _receipt_body(
    *,
    incoming: CampaignState,
    outgoing: CampaignState,
    q_rows_completed: int,
    r_steps: int,
    k_rows_checked: int,
    minimum_margin_lower: Fraction | None,
    arithmetic_digest: str,
    previous_receipt_hash: str,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "algorithm": CAMPAIGN_ALGORITHM,
        "classification": "directed_external_computation_not_lean_proof",
        "atom_id": PROP1224_ATOM,
        **_state_json(incoming, "incoming"),
        **_state_json(outgoing, "outgoing"),
        "q_rows_completed": q_rows_completed,
        "r_steps": r_steps,
        "conservative_k_rows_checked": k_rows_checked,
        "minimum_margin_lower": (
            None if minimum_margin_lower is None else _fraction_pair(minimum_margin_lower)
        ),
        "arithmetic_digest_encoding": ARITHMETIC_DIGEST_ENCODING,
        "arithmetic_digest": arithmetic_digest,
        "previous_receipt_hash": previous_receipt_hash,
        "precision_bits": config["precision_bits"],
        "log_series_terms": config["log_series_terms"],
        "finite_campaigns_source_sha256": config["finite_campaigns_source_sha256"],
        "prop1224_directed_source_sha256": config[
            "prop1224_directed_source_sha256"
        ],
        "prop1224_campaign_source_sha256": config[
            "prop1224_campaign_source_sha256"
        ],
        "campaign_io_source_sha256": config["campaign_io_source_sha256"],
        "fixed_point_g_interval_recomputed": True,
        "transcendental_enclosures_recomputed": True,
        "all_retained_margin_lower_bounds_nonnegative": True,
        "execution_attested": False,
        "lean_realization_proved": False,
        "lean_atom_discharged": False,
    }


def _make_receipt(**kwargs: Any) -> dict[str, Any]:
    body = _receipt_body(**kwargs)
    return {**body, "receipt_hash": hashlib.sha256(canonical_json_bytes(body)).hexdigest()}


def _receipt_fields() -> set[str]:
    dummy_config = {
        "precision_bits": 32,
        "log_series_terms": 8,
        "finite_campaigns_source_sha256": ZERO_SHA256,
        "prop1224_directed_source_sha256": ZERO_SHA256,
        "prop1224_campaign_source_sha256": ZERO_SHA256,
        "campaign_io_source_sha256": ZERO_SHA256,
    }
    return set(
        _receipt_body(
            incoming=_initial_state(),
            outgoing=_initial_state(),
            q_rows_completed=0,
            r_steps=1,
            k_rows_checked=0,
            minimum_margin_lower=None,
            arithmetic_digest=ZERO_SHA256,
            previous_receipt_hash=ZERO_SHA256,
            config=dummy_config,
        )
    ) | {"receipt_hash"}


def _validate_receipt(report: Mapping[str, Any], config: Mapping[str, Any]) -> None:
    if not isinstance(report, Mapping) or set(report) != _receipt_fields():
        raise Prop1224CampaignError("receipt fields changed")
    if (
        report.get("schema_version") != 1
        or report.get("algorithm") != CAMPAIGN_ALGORITHM
    ):
        raise Prop1224CampaignError("unsupported receipt schema or algorithm")
    if report.get("classification") != "directed_external_computation_not_lean_proof":
        raise Prop1224CampaignError("receipt classification changed")
    if report.get("atom_id") != PROP1224_ATOM:
        raise Prop1224CampaignError("receipt atom changed")
    incoming = _state_from_receipt(report, "incoming")
    outgoing = _state_from_receipt(report, "outgoing")
    _validate_state(incoming, name="incoming state", allow_terminal=False)
    _validate_state(outgoing, name="outgoing state", allow_terminal=True)
    q_rows = _integer(report.get("q_rows_completed"), "q_rows_completed", minimum=0)
    r_steps = _integer(report.get("r_steps"), "r_steps", minimum=0)
    k_rows = _integer(
        report.get("conservative_k_rows_checked"),
        "conservative_k_rows_checked",
        minimum=0,
    )
    if not (q_rows or r_steps):
        raise Prop1224CampaignError("receipt makes no scheduler progress")
    if q_rows > config["q_rows_per_chunk"] or r_steps > config["r_steps_per_chunk"]:
        raise Prop1224CampaignError("receipt exceeds its immutable chunk budget")
    if k_rows > r_steps:
        raise Prop1224CampaignError("receipt checks more k rows than arithmetic steps")
    if outgoing.q != _advance_q(incoming.q, q_rows):
        raise Prop1224CampaignError(
            "receipt q transition disagrees with the exact scheduler"
        )
    if outgoing.q != incoming.q and outgoing.next_r != 1:
        raise Prop1224CampaignError("advanced q transition did not reset r")
    if outgoing.q != PROP1224_Q_END and (
        q_rows != config["q_rows_per_chunk"]
        and r_steps != config["r_steps_per_chunk"]
    ):
        raise Prop1224CampaignError("nonterminal receipt stopped before either chunk budget")
    margin = report.get("minimum_margin_lower")
    if k_rows == 0:
        if margin is not None:
            raise Prop1224CampaignError("empty k receipt has a minimum margin")
    else:
        if _fraction_from_pair(margin, "minimum_margin_lower") < 0:
            raise Prop1224CampaignError("receipt stores a negative minimum margin")
    if report.get("arithmetic_digest_encoding") != ARITHMETIC_DIGEST_ENCODING:
        raise Prop1224CampaignError("arithmetic digest encoding changed")
    for name in (
        "arithmetic_digest",
        "previous_receipt_hash",
        "finite_campaigns_source_sha256",
        "prop1224_directed_source_sha256",
        "prop1224_campaign_source_sha256",
        "campaign_io_source_sha256",
        "receipt_hash",
    ):
        _digest(report.get(name), name)
    for name in (
        "fixed_point_g_interval_recomputed",
        "transcendental_enclosures_recomputed",
        "all_retained_margin_lower_bounds_nonnegative",
    ):
        if report.get(name) is not True:
            raise Prop1224CampaignError(f"receipt assertion {name} is absent")
    for name in (
        "execution_attested",
        "lean_realization_proved",
        "lean_atom_discharged",
    ):
        if report.get(name) is not False:
            raise Prop1224CampaignError(f"unsafe receipt claim in {name}")
    if (report["precision_bits"], report["log_series_terms"]) != (
        config["precision_bits"],
        config["log_series_terms"],
    ):
        raise Prop1224CampaignError("receipt changes arithmetic precision")
    for name in (
        "finite_campaigns_source_sha256",
        "prop1224_directed_source_sha256",
        "prop1224_campaign_source_sha256",
        "campaign_io_source_sha256",
    ):
        if report[name] != config[name]:
            raise Prop1224CampaignError(f"receipt changes {name}")
    body = {key: value for key, value in report.items() if key != "receipt_hash"}
    if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != report["receipt_hash"]:
        raise Prop1224CampaignError("receipt canonical hash is invalid")


def _receipt_paths(output_directory: Path) -> list[Path]:
    indexed: list[tuple[int, Path]] = []
    for path in output_directory.glob("receipt-*.json"):
        match = RECEIPT_PATTERN.fullmatch(path.name)
        if match is None or not path.is_file():
            raise Prop1224CampaignError(f"malformed receipt path {path.name!r}")
        indexed.append((int(match.group(1)), path))
    indexed.sort()
    if [index for index, _ in indexed] != list(range(len(indexed))):
        raise Prop1224CampaignError("receipt indices are not consecutive")
    return [path for _, path in indexed]


def _load_receipts(
    output_directory: Path, config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in _receipt_paths(output_directory):
        try:
            value = load_json(path, require_canonical=True)
        except CampaignIOError as exc:
            raise Prop1224CampaignError(str(exc)) from exc
        if not isinstance(value, dict):
            raise Prop1224CampaignError(f"receipt {path.name} must be a JSON object")
        _validate_receipt(value, config)
        reports.append(value)
    return reports


def _check_chain(reports: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> None:
    expected_state = _initial_state()
    previous_hash = ZERO_SHA256
    total_q = 0
    for index, report in enumerate(reports):
        _validate_receipt(report, config)
        if _state_from_receipt(report, "incoming") != expected_state:
            raise Prop1224CampaignError(f"receipt {index} breaks arithmetic state linkage")
        if report["previous_receipt_hash"] != previous_hash:
            raise Prop1224CampaignError(f"receipt {index} breaks the receipt hash chain")
        expected_state = _state_from_receipt(report, "outgoing")
        previous_hash = report["receipt_hash"]
        total_q += report["q_rows_completed"]
    if expected_state.q == PROP1224_Q_END and total_q != prop1224_source_q_count():
        raise Prop1224CampaignError("terminal chain has the wrong exact q-row count")


def _process_chunk(
    incoming: CampaignState,
    *,
    previous_receipt_hash: str,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Execute one deterministic bounded-memory transition."""

    _validate_state(incoming, name="incoming state", allow_terminal=False)
    scale = config["g_fixed_point_scale"]
    q = incoming.q
    next_r = incoming.next_r
    g_lower = incoming.g_lower_units
    g_upper = incoming.g_upper_units
    q_rows = 0
    r_steps = 0
    k_rows = 0
    minimum_margin: Fraction | None = None
    arithmetic = hashlib.sha256()
    arithmetic.update(ARITHMETIC_DIGEST_ENCODING.encode("ascii") + b"\0")

    try:
        while q != PROP1224_Q_END:
            if (
                q_rows >= config["q_rows_per_chunk"]
                or r_steps >= config["r_steps_per_chunk"]
            ):
                break
            parameters = prop1224_directed_parameters(
                q,
                bits=config["precision_bits"],
                log_terms=config["log_series_terms"],
            )
            first, last = _window(parameters)
            _hash_q_header(arithmetic, parameters, first, last)
            if last < first:
                if next_r != 1 or g_lower or g_upper:
                    raise Prop1224CampaignError("empty q row has noninitial arithmetic state")
                arithmetic.update(f"C:{q}:{first}:{last}:0\n".encode("ascii"))
                q_rows += 1
                q = prop1224_next_q(q)
                next_r = 1
                g_lower = 0
                g_upper = 0
                continue
            if not 1 <= next_r <= last:
                raise Prop1224CampaignError("partial q state lies outside its exact r range")
            remaining = config["r_steps_per_chunk"] - r_steps
            stop = min(last + 1, next_r + remaining)
            for r, phi_r, squarefree in iter_totient_squarefree_segment(
                next_r, stop, segment_size=config["sieve_segment_size"]
            ):
                coprime = gcd(r, q) == 1
                if squarefree and coprime:
                    g_lower += scale // phi_r
                    g_upper += (scale + phi_r - 1) // phi_r
                arithmetic.update(
                    f"R:{q}:{r}:{phi_r}:{int(squarefree)}:{int(coprime)}:{g_lower}:{g_upper}\n".encode(
                        "ascii"
                    )
                )
                r_steps += 1
                next_r = r + 1
                if r >= first:
                    margin = prop1224_directed_margin_lower_from_g_upper(
                        parameters, r, Fraction(g_upper, scale)
                    )
                    if margin < 0:
                        raise Prop1224CampaignError(
                            f"source margin is not proved nonnegative at q={q}, k={r}"
                        )
                    if minimum_margin is None or margin < minimum_margin:
                        minimum_margin = margin
                    k_rows += 1
                    arithmetic.update(
                        f"K:{q}:{r}:{g_lower}:{g_upper}:{margin.numerator}/{margin.denominator}\n".encode(
                            "ascii"
                        )
                    )
            if next_r == last + 1:
                arithmetic.update(f"C:{q}:{first}:{last}:{last}\n".encode("ascii"))
                q_rows += 1
                q = prop1224_next_q(q)
                next_r = 1
                g_lower = 0
                g_upper = 0
            else:
                break
    except FiniteCampaignError as exc:
        raise Prop1224CampaignError(str(exc)) from exc

    outgoing = CampaignState(q, next_r, g_lower, g_upper)
    return _make_receipt(
        incoming=incoming,
        outgoing=outgoing,
        q_rows_completed=q_rows,
        r_steps=r_steps,
        k_rows_checked=k_rows,
        minimum_margin_lower=minimum_margin,
        arithmetic_digest=arithmetic.hexdigest(),
        previous_receipt_hash=previous_receipt_hash,
        config=config,
    )


def _result(
    reports: Sequence[Mapping[str, Any]], *, local: bool, replayed: int
) -> Prop1224CampaignResult:
    state = (
        _initial_state()
        if not reports
        else _state_from_receipt(reports[-1], "outgoing")
    )
    completed_q = sum(report["q_rows_completed"] for report in reports)
    complete = state.q == PROP1224_Q_END
    fully_replayed = bool(reports) and replayed == len(reports)
    return Prop1224CampaignResult(
        source_q_rows=prop1224_source_q_count(),
        completed_q_rows=completed_q,
        next_q=state.q,
        next_r=state.next_r,
        receipts=len(reports),
        r_steps=sum(report["r_steps"] for report in reports),
        conservative_k_rows_checked=sum(
            report["conservative_k_rows_checked"] for report in reports
        ),
        complete=complete,
        final_receipt_hash=ZERO_SHA256 if not reports else reports[-1]["receipt_hash"],
        compact_chain_verified=True,
        locally_supervised_execution=local,
        replayed_receipts=replayed,
        fresh_arithmetic_replay=fully_replayed,
        full_source_q_scheduler_coverage_recorded=(
            complete and completed_q == prop1224_source_q_count()
        ),
    )


def verify_campaign(output_directory: Path) -> Prop1224CampaignResult:
    """Validate canonical receipts, hashes, budgets, and exact q transitions."""

    config = _load_config(output_directory)
    reports = _load_receipts(output_directory, config)
    _check_chain(reports, config)
    return _result(reports, local=False, replayed=0)


def replay_campaign(
    output_directory: Path, *, max_chunks: int | None = None
) -> Prop1224CampaignResult:
    """Regenerate receipt arithmetic from the root and compare exact bytes."""

    if max_chunks is not None:
        _integer(max_chunks, "max_chunks", minimum=1)
    config = _load_config(output_directory)
    reports = _load_receipts(output_directory, config)
    _check_chain(reports, config)
    selected_count = (
        len(reports) if max_chunks is None else min(max_chunks, len(reports))
    )
    state = _initial_state()
    previous_hash = ZERO_SHA256
    for index, report in enumerate(reports[:selected_count]):
        expected = _process_chunk(
            state, previous_receipt_hash=previous_hash, config=config
        )
        if expected != report:
            raise Prop1224CampaignError(f"fresh arithmetic replay differs at receipt {index}")
        state = _state_from_receipt(expected, "outgoing")
        previous_hash = expected["receipt_hash"]
    return _result(reports, local=False, replayed=selected_count)


def run_campaign(
    output_directory: Path,
    *,
    precision_bits: int = DEFAULT_BITS,
    log_series_terms: int = DEFAULT_LOG_TERMS,
    r_steps_per_chunk: int = 250_000,
    q_rows_per_chunk: int = 100_000,
    sieve_segment_size: int = 250_000,
    max_chunks: int | None = None,
) -> Prop1224CampaignResult:
    """Start or resume the one literal full-source campaign.

    Omitting ``max_chunks`` continues until the terminal source sentinel.
    Supplying it performs that many new resumable chunks and reports
    ``complete = false`` unless the true terminal state was reached.
    """

    _validate_parameters(
        precision_bits=precision_bits,
        log_series_terms=log_series_terms,
        r_steps_per_chunk=r_steps_per_chunk,
        q_rows_per_chunk=q_rows_per_chunk,
        sieve_segment_size=sieve_segment_size,
        max_chunks=max_chunks,
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    with advisory_lock(output_directory / ".prop1224-campaign.lock"):
        config = _initialize_or_check(
            output_directory,
            precision_bits=precision_bits,
            log_series_terms=log_series_terms,
            r_steps_per_chunk=r_steps_per_chunk,
            q_rows_per_chunk=q_rows_per_chunk,
            sieve_segment_size=sieve_segment_size,
        )
        reports = _load_receipts(output_directory, config)
        _check_chain(reports, config)
        chunks_run = 0
        while (not reports or reports[-1]["outgoing_q"] != PROP1224_Q_END) and (
            max_chunks is None or chunks_run < max_chunks
        ):
            state = _initial_state() if not reports else _state_from_receipt(
                reports[-1], "outgoing"
            )
            previous_hash = ZERO_SHA256 if not reports else reports[-1]["receipt_hash"]
            report = _process_chunk(
                state, previous_receipt_hash=previous_hash, config=config
            )
            _validate_receipt(report, config)
            path = output_directory / f"receipt-{len(reports):010d}.json"
            if path.exists() or len(reports) >= MAX_RECEIPTS:
                raise Prop1224CampaignError("refusing to replace or overflow receipts")
            try:
                write_immutable_json(path, report)
            except CampaignIOError as exc:
                raise Prop1224CampaignError(str(exc)) from exc
            reports.append(report)
            chunks_run += 1
        _check_chain(reports, config)
        result = _result(reports, local=chunks_run > 0, replayed=0)
        try:
            atomic_write_json(output_directory / MANIFEST_NAME, result.as_json())
        except CampaignIOError as exc:
            raise Prop1224CampaignError(str(exc)) from exc
        return result
