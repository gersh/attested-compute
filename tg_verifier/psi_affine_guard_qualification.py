# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Reproducible literal qualification of the one-pass CH25 psi guard."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import os
from pathlib import Path
import subprocess
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
from .finite_campaigns import prime_power_events
from .psi_residual_campaign import (
    CRLIBM_COMMIT,
    FALLBACK_FIELDS,
    MAX_RECEIPT_BYTES,
    MAX_RUNNER_BYTES,
    MAX_SOURCE_BYTES,
    PRIMESIEVE_COMMIT,
    SOURCE_UPPER_EXCLUSIVE,
    PsiResidualCampaignError,
    _validate_upstream_manifest,
    validate_runner_receipt,
)
from .psi_two_pass_qualification import _CRlibmQ64


SCHEMA = "sparkinterval.tg.psi-affine-literal-qualification.v1"
CLASSIFICATION = (
    "bounded_literal_all_event_extremum_qualification_not_source_evidence_or_proof"
)
AFFINE_ALGORITHM = "ch25-psi-prime-power-affine-guard-v1"
TWO_PASS_ALGORITHM = "ch25-psi-prime-power-two-pass-v1"
SCALE = 1 << 64
U128_LIMIT = 1 << 128
FRACTION_BITS = 16
Q64_SHIFT = 48
UPPER_NUMERATOR = 19_764_819
UPPER_DENOMINATOR = 25_000_000
EVENT_DOMAIN = b"sparkinterval.tg.psi-prime-power-events.v1\0"
ROW_DOMAIN = b"sparkinterval.tg.psi-prime-power-rows.v1\0"
COMMON_FIELDS = (
    "delta",
    "event_sha256",
    "row_sha256",
    "prime_power_events",
    "prime_events",
    "higher_power_events",
)
AFFINE_FIELDS = frozenset(
    {
        "algorithm",
        "mode",
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
        "guard_encoding",
        "allowed_incoming_q64",
        "guard_witnesses",
        "guard_derivation",
        "terminal_strict_lower_constrained",
        "incoming_state",
        "outgoing_state",
        "accepted",
        "elapsed_seconds",
        "execution_attested",
        "lean_atom_discharged",
    }
)
CAPABILITIES = {
    "bounded_all_event_extremum_qualification_complete": True,
    "full_source_range": False,
    "root_derived_source_prefix": False,
    "primesieve_to_mathlib_realization_proved": False,
    "crlibm_to_mathlib_realization_proved": False,
    "compiler_or_cpu_refinement_proved": False,
    "source_run_completed": False,
    "execution_attested": False,
    "receipt_admitted": False,
    "lean_atom_discharged": False,
}
CHECKS = {
    "literal_prime_power_roster_replayed": True,
    "every_crlibm_q64_row_replayed": True,
    "every_lower_requirement_folded": True,
    "every_upper_allowance_folded": True,
    "reported_extremum_witnesses_match_global_fold": True,
    "event_and_row_commitments_match": True,
    "delta_and_event_counts_match": True,
    "two_pass_summary_and_verify_match": True,
    "incoming_state_inside_affine_rectangle": True,
    "repeats_match_ignoring_timing": True,
}


class PsiAffineQualificationError(RuntimeError):
    """The affine qualification failed closed."""


def _integer(value: object, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PsiAffineQualificationError(
            f"{name} must be an integer at least {minimum}"
        )
    return value


def _decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, str):
        raise PsiAffineQualificationError(f"{name} must be a decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise PsiAffineQualificationError(f"{name} is not decimal") from exc
    if not result.is_finite() or result < 0:
        raise PsiAffineQualificationError(f"{name} is not finite/nonnegative")
    return result


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite() or value < 0:
        raise PsiAffineQualificationError("timing is not finite/nonnegative")
    return format(value, "f")


def _lower_radius(value: int, strict: bool) -> int:
    from math import isqrt

    radicand = (2 * value) << (2 * FRACTION_BITS)
    root = isqrt(radicand)
    radius = root << Q64_SHIFT
    if strict and root * root == radicand:
        radius -= 1
    return radius


def _upper_radius(value: int) -> int:
    from math import isqrt

    root = isqrt(value << (2 * FRACTION_BITS))
    return (
        UPPER_NUMERATOR * root * (1 << Q64_SHIFT)
    ) // UPPER_DENOMINATOR


def literal_affine_oracle(
    *,
    lower: int,
    upper_exclusive: int,
    crlibm_shared: Path,
    segment_size: int,
) -> dict[str, Any]:
    """Fold every literal event and retain the globally attaining rows."""

    started = time.monotonic_ns()
    events = prime_power_events(
        lower, upper_exclusive, segment_size=segment_size
    )
    enumerated = time.monotonic_ns()
    event_digest = hashlib.sha256(EVENT_DOMAIN)
    row_digest = hashlib.sha256(ROW_DOMAIN)
    bounds: dict[int, tuple[int, int]] = {}
    delta_lower = 0
    delta_upper = 0
    minimum_lower = 0
    maximum_upper = U128_LIMIT - 1
    lower_witness: dict[str, Any] | None = None
    upper_witness: dict[str, Any] | None = None
    prime_count = 0
    higher_count = 0
    previous = 0
    crlibm = _CRlibmQ64(crlibm_shared)
    try:
        for index, event in enumerate(events):
            if event.value <= previous:
                raise PsiAffineQualificationError(
                    "literal event roster is duplicated or reordered"
                )
            if event.prime not in bounds:
                bounds[event.prime] = crlibm.bounds(event.prime)
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

            radius = _lower_radius(event.value, False)
            required = max(
                0, event.value * SCALE - radius - delta_lower
            )
            if lower_witness is None or required > minimum_lower:
                minimum_lower = required
                lower_witness = {
                    "event_index": index,
                    "value": event.value,
                    "prefix_delta_q64": delta_lower,
                    "radius_q64": radius,
                    "strict": False,
                    "kind": "lower_left_limit",
                }
            delta_lower += log_lower
            delta_upper += log_upper
            if delta_upper >= U128_LIMIT:
                raise PsiAffineQualificationError(
                    "literal affine delta overflows u128"
                )
            radius = _upper_radius(event.value)
            allowance = event.value * SCALE + radius - delta_upper
            if allowance < 0:
                raise PsiAffineQualificationError(
                    "literal affine upper allowance is negative"
                )
            if upper_witness is None or allowance < maximum_upper:
                maximum_upper = allowance
                upper_witness = {
                    "event_index": index,
                    "value": event.value,
                    "prefix_delta_q64": delta_upper,
                    "radius_q64": radius,
                    "kind": "upper_post_jump",
                }
            if event.exponent == 1:
                prime_count += 1
            else:
                higher_count += 1
            previous = event.value
    finally:
        crlibm.close()
    folded = time.monotonic_ns()
    terminal = upper_exclusive == SOURCE_UPPER_EXCLUSIVE
    if terminal:
        value = upper_exclusive - 1
        radius = _lower_radius(value, True)
        required = max(0, value * SCALE - radius - delta_lower)
        if lower_witness is None or required > minimum_lower:
            minimum_lower = required
            lower_witness = {
                "event_index": len(events),
                "value": value,
                "prefix_delta_q64": delta_lower,
                "radius_q64": radius,
                "strict": True,
                "kind": "terminal_strict_lower",
            }
    if lower_witness is None or upper_witness is None:
        raise PsiAffineQualificationError("literal shard has no event witnesses")
    if not minimum_lower <= maximum_upper:
        raise PsiAffineQualificationError("literal affine rectangle is empty")
    semantics = {
        "lower": lower,
        "upper_exclusive": upper_exclusive,
        "prime_power_events": len(events),
        "prime_events": prime_count,
        "higher_power_events": higher_count,
        "unique_primes": len(bounds),
        "event_sha256": event_digest.hexdigest(),
        "row_sha256": row_digest.hexdigest(),
        "delta": [delta_lower, delta_upper],
        "allowed_incoming_q64": {
            "lower_min": minimum_lower,
            "upper_max": maximum_upper,
            "predicate": "lower_min<=lower<=upper<=upper_max",
        },
        "guard_witnesses": {
            "lower_min": lower_witness,
            "upper_max": upper_witness,
        },
        "terminal_strict_lower_constrained": terminal,
    }
    return {
        "semantics": semantics,
        "timing": {
            "prime_power_enumeration_seconds_decimal": _decimal_text(
                Decimal(enumerated - started) / Decimal(1_000_000_000)
            ),
            "row_and_extremum_fold_seconds_decimal": _decimal_text(
                Decimal(folded - enumerated) / Decimal(1_000_000_000)
            ),
            "total_seconds_decimal": _decimal_text(
                Decimal(folded - started) / Decimal(1_000_000_000)
            ),
            "scope": (
                "bounded_all_event_python_roster_loaded_crlibm_and_extremum_fold"
            ),
        },
    }


def _command(
    runner: Path,
    mode: str,
    lower: int,
    upper_exclusive: int,
    sieve_size_kib: int,
    incoming: Sequence[int] | None,
) -> list[str]:
    result = [
        os.fspath(runner.resolve()),
        "--mode",
        mode,
        "--lower",
        str(lower),
        "--upper",
        str(upper_exclusive - 1),
        "--sieve-size-kib",
        str(sieve_size_kib),
    ]
    if incoming is not None:
        result += [
            "--incoming-lower",
            str(incoming[0]),
            "--incoming-upper",
            str(incoming[1]),
        ]
    return result


def _record(
    runner: Path,
    mode: str,
    lower: int,
    upper_exclusive: int,
    sieve_size_kib: int,
    incoming: Sequence[int] | None,
    timeout_seconds: int | None,
) -> dict[str, Any]:
    started = time.monotonic_ns()
    try:
        completed = subprocess.run(
            _command(
                runner,
                mode,
                lower,
                upper_exclusive,
                sieve_size_kib,
                incoming,
            ),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PsiAffineQualificationError(f"{mode} execution failed: {exc}") from exc
    wall = Decimal(time.monotonic_ns() - started) / Decimal(1_000_000_000)
    if completed.returncode != 0:
        raise PsiAffineQualificationError(
            f"{mode} worker failed ({completed.returncode}): "
            f"{completed.stderr.decode('utf-8', errors='replace').strip()}"
        )
    raw = completed.stdout
    if not raw or len(raw) > MAX_RECEIPT_BYTES:
        raise PsiAffineQualificationError(f"{mode} receipt size is invalid")
    try:
        report = load_decimal_json_bytes(raw, label=f"{mode} receipt")
    except EvidenceError as exc:
        raise PsiAffineQualificationError(str(exc)) from exc
    wire = deepcopy(report)
    elapsed = wire.get("elapsed_seconds")
    if not isinstance(elapsed, Decimal):
        raise PsiAffineQualificationError(f"{mode} elapsed time is malformed")
    wire["elapsed_seconds"] = _decimal_text(elapsed)
    return {
        "receipt_sha256": sha256_bytes(raw),
        "receipt_size_bytes": len(raw),
        "receipt_hex": raw.hex(),
        "report": wire,
        "process_wall_seconds_decimal": _decimal_text(wall),
    }


def _decode_record(value: object, label: str) -> dict[str, Any]:
    fields = {
        "receipt_sha256",
        "receipt_size_bytes",
        "receipt_hex",
        "report",
        "process_wall_seconds_decimal",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise PsiAffineQualificationError(f"{label} record fields changed")
    size = _integer(value.get("receipt_size_bytes"), f"{label} size", 1)
    encoded = value.get("receipt_hex")
    if (
        size > MAX_RECEIPT_BYTES
        or not isinstance(encoded, str)
        or len(encoded) != 2 * size
    ):
        raise PsiAffineQualificationError(f"{label} receipt bytes are malformed")
    try:
        raw = bytes.fromhex(encoded)
    except ValueError as exc:
        raise PsiAffineQualificationError(
            f"{label} receipt hex is malformed"
        ) from exc
    if value.get("receipt_sha256") != sha256_bytes(raw):
        raise PsiAffineQualificationError(f"{label} receipt digest changed")
    try:
        report = load_decimal_json_bytes(raw, label=label)
    except EvidenceError as exc:
        raise PsiAffineQualificationError(str(exc)) from exc
    wire = deepcopy(report)
    elapsed = wire.get("elapsed_seconds")
    if not isinstance(elapsed, Decimal):
        raise PsiAffineQualificationError(f"{label} elapsed time is malformed")
    wire["elapsed_seconds"] = _decimal_text(elapsed)
    if value.get("report") != wire:
        raise PsiAffineQualificationError(f"{label} readable report differs")
    _decimal(value.get("process_wall_seconds_decimal"), f"{label} wall time")
    return report


def _without_elapsed(report: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(report)
    result.pop("elapsed_seconds", None)
    return result


def _digest(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
    ):
        raise PsiAffineQualificationError(f"{name} is not lowercase SHA-256")
    try:
        if len(bytes.fromhex(value)) != 32:
            raise ValueError
    except ValueError as exc:
        raise PsiAffineQualificationError(
            f"{name} is not lowercase SHA-256"
        ) from exc
    return value


def _validate_semantics(
    semantics: object, lower: int, upper_exclusive: int
) -> Mapping[str, Any]:
    fields = {
        "lower",
        "upper_exclusive",
        "prime_power_events",
        "prime_events",
        "higher_power_events",
        "unique_primes",
        "event_sha256",
        "row_sha256",
        "delta",
        "allowed_incoming_q64",
        "guard_witnesses",
        "terminal_strict_lower_constrained",
    }
    if not isinstance(semantics, dict) or set(semantics) != fields:
        raise PsiAffineQualificationError("oracle semantic fields changed")
    if (
        semantics.get("lower") != lower
        or semantics.get("upper_exclusive") != upper_exclusive
    ):
        raise PsiAffineQualificationError("oracle semantic range changed")
    events = _integer(
        semantics.get("prime_power_events"), "oracle event count", 1
    )
    primes = _integer(semantics.get("prime_events"), "oracle prime count")
    higher = _integer(
        semantics.get("higher_power_events"), "oracle higher-power count"
    )
    unique = _integer(
        semantics.get("unique_primes"), "oracle unique-prime count"
    )
    if (
        events != primes + higher
        or unique < primes
        or unique > events
    ):
        raise PsiAffineQualificationError("oracle event cardinalities changed")
    _digest(semantics.get("event_sha256"), "oracle event commitment")
    _digest(semantics.get("row_sha256"), "oracle row commitment")
    delta = semantics.get("delta")
    if (
        not isinstance(delta, list)
        or len(delta) != 2
        or any(
            isinstance(item, bool)
            or not isinstance(item, int)
            or not 0 <= item < U128_LIMIT
            for item in delta
        )
        or delta[0] > delta[1]
    ):
        raise PsiAffineQualificationError("oracle delta is malformed")
    bounds = semantics.get("allowed_incoming_q64")
    if not isinstance(bounds, dict) or set(bounds) != {
        "lower_min",
        "upper_max",
        "predicate",
    }:
        raise PsiAffineQualificationError("oracle affine bounds changed")
    minimum = _integer(bounds.get("lower_min"), "oracle lower minimum")
    maximum = _integer(bounds.get("upper_max"), "oracle upper maximum")
    if (
        maximum >= U128_LIMIT
        or minimum > maximum
        or bounds.get("predicate") != "lower_min<=lower<=upper<=upper_max"
        or maximum + delta[0] >= U128_LIMIT
        or maximum + delta[1] >= U128_LIMIT
    ):
        raise PsiAffineQualificationError(
            "oracle affine rectangle is malformed or can overflow"
        )
    witnesses = semantics.get("guard_witnesses")
    if not isinstance(witnesses, dict) or set(witnesses) != {
        "lower_min",
        "upper_max",
    }:
        raise PsiAffineQualificationError("oracle extremum witnesses changed")
    lower_witness = witnesses.get("lower_min")
    upper_witness = witnesses.get("upper_max")
    if (
        not isinstance(lower_witness, dict)
        or set(lower_witness)
        != {
            "event_index",
            "value",
            "prefix_delta_q64",
            "radius_q64",
            "strict",
            "kind",
        }
        or not isinstance(upper_witness, dict)
        or set(upper_witness)
        != {
            "event_index",
            "value",
            "prefix_delta_q64",
            "radius_q64",
            "kind",
        }
    ):
        raise PsiAffineQualificationError("oracle witness fields changed")
    lower_index = _integer(
        lower_witness.get("event_index"), "lower witness index"
    )
    lower_value = _integer(
        lower_witness.get("value"), "lower witness value", lower
    )
    lower_prefix = _integer(
        lower_witness.get("prefix_delta_q64"), "lower witness prefix"
    )
    lower_radius = _integer(
        lower_witness.get("radius_q64"), "lower witness radius"
    )
    strict = lower_witness.get("strict")
    terminal = semantics.get("terminal_strict_lower_constrained")
    expected_terminal = upper_exclusive == SOURCE_UPPER_EXCLUSIVE
    if terminal is not expected_terminal or not isinstance(strict, bool):
        raise PsiAffineQualificationError("oracle terminal classification changed")
    if lower_witness.get("kind") == "terminal_strict_lower":
        if (
            not terminal
            or not strict
            or lower_index != events
            or lower_value != upper_exclusive - 1
        ):
            raise PsiAffineQualificationError(
                "oracle terminal lower witness is inconsistent"
            )
    elif lower_witness.get("kind") == "lower_left_limit":
        if (
            strict
            or lower_index >= events
            or not lower <= lower_value < upper_exclusive
        ):
            raise PsiAffineQualificationError(
                "oracle ordinary lower witness is inconsistent"
            )
    else:
        raise PsiAffineQualificationError("oracle lower witness kind changed")
    if lower_radius != _lower_radius(lower_value, strict):
        raise PsiAffineQualificationError("oracle lower witness radius changed")
    lower_square = lower_radius * lower_radius
    lower_bound = 2 * lower_value * SCALE * SCALE
    if (strict and not lower_square < lower_bound) or (
        not strict and not lower_square <= lower_bound
    ):
        raise PsiAffineQualificationError("oracle lower radius is unsafe")
    if minimum != max(
        0, lower_value * SCALE - lower_radius - lower_prefix
    ):
        raise PsiAffineQualificationError(
            "oracle lower witness does not attain minimum"
        )
    upper_index = _integer(
        upper_witness.get("event_index"), "upper witness index"
    )
    upper_value = _integer(
        upper_witness.get("value"), "upper witness value", lower
    )
    upper_prefix = _integer(
        upper_witness.get("prefix_delta_q64"), "upper witness prefix"
    )
    upper_radius = _integer(
        upper_witness.get("radius_q64"), "upper witness radius"
    )
    if (
        upper_witness.get("kind") != "upper_post_jump"
        or upper_index >= events
        or not lower <= upper_value < upper_exclusive
        or upper_radius != _upper_radius(upper_value)
        or maximum
        != upper_value * SCALE + upper_radius - upper_prefix
    ):
        raise PsiAffineQualificationError(
            "oracle upper witness does not attain maximum"
        )
    if (
        upper_radius
        * upper_radius
        * UPPER_DENOMINATOR
        * UPPER_DENOMINATOR
        > UPPER_NUMERATOR
        * UPPER_NUMERATOR
        * upper_value
        * SCALE
        * SCALE
    ):
        raise PsiAffineQualificationError("oracle upper radius is unsafe")
    return semantics


def _check_affine(
    report: Mapping[str, Any],
    semantics: Mapping[str, Any],
    sieve_size_kib: int,
) -> None:
    if set(report) != AFFINE_FIELDS:
        raise PsiAffineQualificationError("affine receipt fields changed")
    if (
        report.get("algorithm") != AFFINE_ALGORITHM
        or report.get("mode") != "affine"
        or report.get("classification") != "source-scale-shard-not-lean-proof"
        or report.get("atom") != "ch25-psi-1e13"
        or report.get("primesieve_commit") != PRIMESIEVE_COMMIT
        or report.get("crlibm_commit") != CRLIBM_COMMIT
        or report.get("lower") != semantics["lower"]
        or report.get("upper_exclusive") != semantics["upper_exclusive"]
        or report.get("work_count")
        != semantics["upper_exclusive"] - semantics["lower"]
        or report.get("scale_bits") != 64
        or report.get("sieve_size_kib") != sieve_size_kib
        or report.get("log_interval_encoding")
        != "crlibm-binary64-directed-to-q64-v1"
        or report.get("event_encoding")
        != "u64be-value-u64be-prime-u32be-exponent-v1"
        or report.get("row_encoding")
        != "u64be-value-u64be-prime-u32be-exponent-u128be-log-pair-v1"
        or report.get("state_components")
        != ["psi_lower_q64", "psi_upper_q64"]
        or report.get("guard_encoding")
        != "independent-q64-rectangle-with-lower-le-upper-v1"
        or report.get("incoming_state") is not None
        or report.get("outgoing_state") is not None
        or report.get("accepted") is not True
        or report.get("execution_attested") is not False
        or report.get("lean_atom_discharged") is not False
    ):
        raise PsiAffineQualificationError("affine identity or trust flags changed")
    for field in COMMON_FIELDS + (
        "allowed_incoming_q64",
        "guard_witnesses",
        "terminal_strict_lower_constrained",
    ):
        if report.get(field) != semantics.get(field):
            raise PsiAffineQualificationError(
                f"affine {field} differs from literal all-event fold"
            )
    if report.get("guard_derivation") != {
        "sqrt_fraction_bits": 16,
        "lower_radius": "floor(sqrt(2*x)*2^16)*2^48",
        "upper_radius": (
            "floor(19764819*floor(sqrt(x)*2^16)*2^48/25000000)"
        ),
    }:
        raise PsiAffineQualificationError("affine radius derivation changed")


def _check_two_pass(
    report: Mapping[str, Any],
    mode: str,
    semantics: Mapping[str, Any],
    sieve_size_kib: int,
    incoming: Sequence[int] | None,
) -> None:
    try:
        validate_runner_receipt(
            report,
            phase=mode,
            shard_lower=semantics["lower"],
            shard_upper=semantics["upper_exclusive"],
            sieve_size_kib=sieve_size_kib,
            expected_incoming=incoming,
            source_terminal=(
                mode == "verify"
                and semantics["upper_exclusive"] == SOURCE_UPPER_EXCLUSIVE
            ),
        )
    except PsiResidualCampaignError as exc:
        raise PsiAffineQualificationError(str(exc)) from exc
    for field in COMMON_FIELDS:
        if report.get(field) != semantics.get(field):
            raise PsiAffineQualificationError(
                f"two-pass {mode} {field} differs from literal fold"
            )


def _identity(paths: Mapping[str, Path]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for label, path in paths.items():
        maximum = (
            MAX_RUNNER_BYTES if "runner" in label or "shared" in label
            else MAX_SOURCE_BYTES
        )
        try:
            digest, size = hash_file_once(path, limit=maximum)
        except CampaignIOError as exc:
            raise PsiAffineQualificationError(str(exc)) from exc
        result[f"{label}_sha256"] = digest
        result[f"{label}_size_bytes"] = size
    try:
        _validate_upstream_manifest(paths["upstream_manifest"].read_bytes())
    except (OSError, PsiResidualCampaignError) as exc:
        raise PsiAffineQualificationError(str(exc)) from exc
    return result


def _validate_build_manifest(
    path: Path, identity: Mapping[str, Any]
) -> None:
    try:
        value = load_json(path, require_canonical=True)
    except CampaignIOError as exc:
        raise PsiAffineQualificationError(str(exc)) from exc
    if (
        not isinstance(value, dict)
        or value.get("schema") != "sparkinterval.tg.psi-qualification-build.v1"
        or value.get("classification")
        != "local_source_build_identity_not_compiler_or_cpu_refinement"
    ):
        raise PsiAffineQualificationError("two-pass build manifest changed")
    source = value.get("source")
    builds = value.get("builds")
    capabilities = value.get("capabilities")
    if (
        not isinstance(source, dict)
        or source.get("sha256") != identity["two_pass_source_sha256"]
        or not isinstance(builds, dict)
        or set(builds) != {"candidate", "literal_reference"}
        or not isinstance(capabilities, dict)
        or capabilities.get("both_modes_built_from_identical_source_bytes")
        is not True
        or capabilities.get("compiler_refinement_proved") is not False
        or capabilities.get("cpu_refinement_proved") is not False
        or capabilities.get("source_run_completed") is not False
        or capabilities.get("execution_attested") is not False
        or capabilities.get("lean_atom_discharged") is not False
    ):
        raise PsiAffineQualificationError(
            "two-pass build source or capability boundary changed"
        )
    candidate = builds.get("candidate")
    literal = builds.get("literal_reference")
    if (
        not isinstance(candidate, dict)
        or candidate.get("macro_mode")
        != "optimized_square_filter_and_compile_time_dispatch"
        or candidate.get("literal_reference_macro") is not False
        or not isinstance(candidate.get("executable"), dict)
        or candidate["executable"].get("sha256")
        != identity["two_pass_runner_sha256"]
        or not isinstance(literal, dict)
        or literal.get("macro_mode")
        != "literal_integer_sqrt_filter_and_runtime_dispatch"
        or literal.get("literal_reference_macro") is not True
        or not isinstance(literal.get("executable"), dict)
    ):
        raise PsiAffineQualificationError(
            "two-pass build macro modes or candidate identity changed"
        )


def run_qualification(
    *,
    affine_runner: Path,
    two_pass_runner: Path,
    affine_source: Path,
    two_pass_source: Path,
    crlibm_shared: Path,
    upstream_manifest: Path,
    build_manifest: Path,
    output: Path,
    lower: int,
    upper_exclusive: int,
    sieve_size_kib: int = 384,
    segment_size: int = 100_000,
    repeat_count: int = 2,
    timeout_seconds: int | None = 120,
) -> dict[str, Any]:
    if output.exists():
        raise PsiAffineQualificationError(f"refusing to overwrite {output}")
    lower_value = _integer(lower, "lower", 2)
    upper_value = _integer(upper_exclusive, "upper exclusive", 3)
    if not lower_value < upper_value <= SOURCE_UPPER_EXCLUSIVE:
        raise PsiAffineQualificationError("qualification range is invalid")
    if lower_value == 2 and upper_value == SOURCE_UPPER_EXCLUSIVE:
        raise PsiAffineQualificationError("bounded qualification refuses full source")
    sieve = _integer(sieve_size_kib, "sieve size", 16)
    if sieve > 8192:
        raise PsiAffineQualificationError("sieve size exceeds 8192")
    segment = _integer(segment_size, "segment size", 1)
    repeats = _integer(repeat_count, "repeat count", 1)
    paths = {
        "affine_runner": affine_runner,
        "two_pass_runner": two_pass_runner,
        "affine_source": affine_source,
        "two_pass_source": two_pass_source,
        "crlibm_shared": crlibm_shared,
        "upstream_manifest": upstream_manifest,
        "build_manifest": build_manifest,
    }
    identity = _identity(paths)
    oracle = literal_affine_oracle(
        lower=lower_value,
        upper_exclusive=upper_value,
        crlibm_shared=crlibm_shared,
        segment_size=segment,
    )
    semantics = oracle["semantics"]
    synthetic_value = (lower_value - 1) * SCALE
    incoming = (synthetic_value, synthetic_value)
    bounds = semantics["allowed_incoming_q64"]
    if not (
        bounds["lower_min"] <= incoming[0] <= incoming[1] <= bounds["upper_max"]
    ):
        raise PsiAffineQualificationError(
            "synthetic bounded input is outside literal affine rectangle"
        )
    executions: list[dict[str, Any]] = []
    semantic_baseline: dict[str, dict[str, Any]] | None = None
    orders = (
        ("affine", "summary", "verify"),
        ("verify", "summary", "affine"),
    )
    for repeat in range(repeats):
        records: dict[str, dict[str, Any]] = {}
        decoded: dict[str, dict[str, Any]] = {}
        order = orders[repeat % 2]
        for mode in order:
            runner = affine_runner if mode == "affine" else two_pass_runner
            state = incoming if mode == "verify" else None
            record = _record(
                runner,
                mode,
                lower_value,
                upper_value,
                sieve,
                state,
                timeout_seconds,
            )
            report = _decode_record(record, f"{mode} repeat {repeat}")
            if mode == "affine":
                _check_affine(report, semantics, sieve)
            else:
                _check_two_pass(report, mode, semantics, sieve, state)
            records[mode] = record
            decoded[mode] = report
        semantic = {
            mode: _without_elapsed(decoded[mode])
            for mode in ("affine", "summary", "verify")
        }
        if semantic_baseline is None:
            semantic_baseline = semantic
        elif semantic != semantic_baseline:
            raise PsiAffineQualificationError(
                f"semantic output changed at repeat {repeat}"
            )
        executions.append(
            {
                "repeat_index": repeat,
                "mode_order": list(order),
                "affine": records["affine"],
                "summary": records["summary"],
                "verify": records["verify"],
            }
        )
    artifact = {
        "schema": SCHEMA,
        "classification": CLASSIFICATION,
        "identity": identity,
        "configuration": {
            "lower": lower_value,
            "upper_exclusive": upper_value,
            "sieve_size_kib": sieve,
            "segment_size": segment,
            "repeat_count": repeats,
            "incoming_state": list(incoming),
            "incoming_state_is_root_derived": False,
        },
        "oracle": oracle,
        "executions": executions,
        "checks": dict(CHECKS),
        "capabilities": dict(CAPABILITIES),
    }
    _decode_and_check(
        artifact,
        paths=paths,
        regenerate_oracle=False,
    )
    raw = canonical_json_bytes(artifact)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        if stream.write(raw) != len(raw):
            raise PsiAffineQualificationError("short qualification write")
    return artifact


def _decode_and_check(
    artifact: Mapping[str, Any],
    *,
    paths: Mapping[str, Path],
    regenerate_oracle: bool,
) -> dict[str, Any]:
    if set(artifact) != {
        "schema",
        "classification",
        "identity",
        "configuration",
        "oracle",
        "executions",
        "checks",
        "capabilities",
    }:
        raise PsiAffineQualificationError("qualification fields changed")
    current_identity = _identity(paths)
    if (
        artifact.get("schema") != SCHEMA
        or artifact.get("classification") != CLASSIFICATION
        or artifact.get("identity") != current_identity
        or artifact.get("checks") != CHECKS
        or artifact.get("capabilities") != CAPABILITIES
    ):
        raise PsiAffineQualificationError(
            "qualification identity, checks, or capability boundary changed"
        )
    _validate_build_manifest(paths["build_manifest"], current_identity)
    config = artifact.get("configuration")
    if not isinstance(config, dict) or set(config) != {
        "lower",
        "upper_exclusive",
        "sieve_size_kib",
        "segment_size",
        "repeat_count",
        "incoming_state",
        "incoming_state_is_root_derived",
    }:
        raise PsiAffineQualificationError("qualification configuration changed")
    lower = _integer(config.get("lower"), "lower", 2)
    upper = _integer(config.get("upper_exclusive"), "upper", 3)
    sieve = _integer(config.get("sieve_size_kib"), "sieve", 16)
    segment = _integer(config.get("segment_size"), "segment", 1)
    repeats = _integer(config.get("repeat_count"), "repeats", 1)
    incoming = config.get("incoming_state")
    expected_value = (lower - 1) * SCALE
    if (
        not lower < upper <= SOURCE_UPPER_EXCLUSIVE
        or lower == 2
        and upper == SOURCE_UPPER_EXCLUSIVE
        or sieve > 8192
        or incoming != [expected_value, expected_value]
        or config.get("incoming_state_is_root_derived") is not False
    ):
        raise PsiAffineQualificationError("qualification configuration is unsafe")
    oracle = artifact.get("oracle")
    if not isinstance(oracle, dict) or set(oracle) != {"semantics", "timing"}:
        raise PsiAffineQualificationError("oracle fields changed")
    semantics = oracle.get("semantics")
    timing = oracle.get("timing")
    if not isinstance(timing, dict) or set(timing) != {
        "prime_power_enumeration_seconds_decimal",
        "row_and_extremum_fold_seconds_decimal",
        "total_seconds_decimal",
        "scope",
    }:
        raise PsiAffineQualificationError("oracle value is malformed")
    semantics = _validate_semantics(semantics, lower, upper)
    for field in (
        "prime_power_enumeration_seconds_decimal",
        "row_and_extremum_fold_seconds_decimal",
        "total_seconds_decimal",
    ):
        _decimal(timing.get(field), f"oracle {field}")
    if timing.get("scope") != (
        "bounded_all_event_python_roster_loaded_crlibm_and_extremum_fold"
    ):
        raise PsiAffineQualificationError("oracle timing scope changed")
    bounds = semantics["allowed_incoming_q64"]
    if not (
        bounds["lower_min"]
        <= incoming[0]
        <= incoming[1]
        <= bounds["upper_max"]
    ):
        raise PsiAffineQualificationError(
            "retained incoming state is outside affine rectangle"
        )
    if regenerate_oracle:
        regenerated = literal_affine_oracle(
            lower=lower,
            upper_exclusive=upper,
            crlibm_shared=paths["crlibm_shared"],
            segment_size=segment,
        )
        if regenerated["semantics"] != semantics:
            raise PsiAffineQualificationError(
                "retained extrema differ from fresh all-event fold"
            )
    executions = artifact.get("executions")
    if not isinstance(executions, list) or len(executions) != repeats:
        raise PsiAffineQualificationError("execution repeats are incomplete")
    semantic_baseline: dict[str, dict[str, Any]] | None = None
    orders = (
        ("affine", "summary", "verify"),
        ("verify", "summary", "affine"),
    )
    for repeat, execution in enumerate(executions):
        if not isinstance(execution, dict) or set(execution) != {
            "repeat_index",
            "mode_order",
            "affine",
            "summary",
            "verify",
        }:
            raise PsiAffineQualificationError("execution fields changed")
        if (
            execution.get("repeat_index") != repeat
            or execution.get("mode_order") != list(orders[repeat % 2])
        ):
            raise PsiAffineQualificationError("execution order changed")
        decoded: dict[str, dict[str, Any]] = {}
        for mode in ("affine", "summary", "verify"):
            report = _decode_record(
                execution.get(mode), f"{mode} repeat {repeat}"
            )
            if mode == "affine":
                _check_affine(report, semantics, sieve)
            else:
                _check_two_pass(
                    report,
                    mode,
                    semantics,
                    sieve,
                    incoming if mode == "verify" else None,
                )
            decoded[mode] = report
        semantic = {
            mode: _without_elapsed(decoded[mode])
            for mode in ("affine", "summary", "verify")
        }
        if semantic_baseline is None:
            semantic_baseline = semantic
        elif semantic != semantic_baseline:
            raise PsiAffineQualificationError("execution repeats changed")
    return dict(artifact)


def verify_qualification(
    path: Path,
    *,
    affine_runner: Path,
    two_pass_runner: Path,
    affine_source: Path,
    two_pass_source: Path,
    crlibm_shared: Path,
    upstream_manifest: Path,
    build_manifest: Path,
    regenerate_oracle: bool = True,
) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except CampaignIOError as exc:
        raise PsiAffineQualificationError(str(exc)) from exc
    if not isinstance(value, dict):
        raise PsiAffineQualificationError("qualification root is not an object")
    return _decode_and_check(
        value,
        paths={
            "affine_runner": affine_runner,
            "two_pass_runner": two_pass_runner,
            "affine_source": affine_source,
            "two_pass_source": two_pass_source,
            "crlibm_shared": crlibm_shared,
            "upstream_manifest": upstream_manifest,
            "build_manifest": build_manifest,
        },
        regenerate_oracle=regenerate_oracle,
    )


def qualification_summary(artifact: Mapping[str, Any]) -> dict[str, Any]:
    semantics = artifact["oracle"]["semantics"]
    return {
        "qualification_sha256": canonical_sha256(dict(artifact)),
        "configuration": artifact["configuration"],
        "literal_all_event_oracle": {
            key: semantics[key]
            for key in (
                "prime_power_events",
                "prime_events",
                "higher_power_events",
                "unique_primes",
                "event_sha256",
                "row_sha256",
                "delta",
                "allowed_incoming_q64",
                "guard_witnesses",
                "terminal_strict_lower_constrained",
            )
        },
        "oracle_timing": artifact["oracle"]["timing"],
        "checks": artifact["checks"],
        "capabilities": artifact["capabilities"],
    }


__all__ = [
    "CLASSIFICATION",
    "PsiAffineQualificationError",
    "SCHEMA",
    "literal_affine_oracle",
    "qualification_summary",
    "run_qualification",
    "verify_qualification",
]
