# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed one-pass affine campaign for the CH25 psi worker.

Every worker is independent of the prefix state.  It emits an additive Q64
transition and a conservative rectangle of admitted incoming endpoints.  The
supervisor fixes the shard plan, retains one raw receipt per shard, derives all
inputs by an exclusive scan from the sole root ``[0, 0]``, checks every
rectangle, and commits ordered child records with domain-separated SHA-256.

This is external finite-computation plumbing.  It never turns a receipt into a
Lean theorem and never claims source execution, attestation, or compiler/CPU
refinement.
"""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Mapping, Sequence

from .affine_guard_certificate import (
    AffineGuardCertificateError,
    FixedShardPlan,
)
from .campaign_io import (
    CampaignIOError,
    advisory_lock,
    atomic_write_bytes,
    canonical_json_bytes,
    load_json,
    read_bytes_once,
    sha256_bytes,
    write_immutable_json,
)
from .evidence import EvidenceError, load_decimal_json_bytes
from .psi_affine_guard_qualification import (
    AFFINE_ALGORITHM,
    AFFINE_FIELDS,
    _lower_radius,
    _upper_radius,
)
from .psi_residual_campaign import (
    ATOM,
    CRLIBM_COMMIT,
    DEFAULT_SHARD_SPAN,
    DEFAULT_SIEVE_SIZE_KIB,
    DEFAULT_WORKERS,
    MAX_RECEIPT_BYTES,
    MAX_RUNNER_BYTES,
    MAX_SOURCE_BYTES,
    PRIMESIEVE_COMMIT,
    SOURCE_EVENT_COUNT,
    SOURCE_LOWER,
    SOURCE_UPPER_EXCLUSIVE,
    STATE_COMPONENTS,
    PsiResidualCampaignError,
    _validate_upstream_manifest,
)


CAMPAIGN_SCHEMA = "sparkinterval.tg.psi-affine-guard-campaign.v1"
FINAL_SCHEMA = "sparkinterval.tg.psi-affine-guard-certificate.v1"
CHILD_SCHEMA = "sparkinterval.tg.psi-affine-guard-child.v1"
CAMPAIGN_ALGORITHM = "ch25-psi-one-pass-affine-guard-campaign-v1"
CLASSIFICATION = "external_finite_computation_not_attestation_or_lean_proof"
CAPTURED_RUNNER_NAME = "captured-psi-affine-guard-runner"
CAPTURED_SOURCE_NAME = "captured-tg-psi-affine-guard-shard.cpp"
CAPTURED_UPSTREAM_NAME = "captured-psi-upstreams.json"
CONFIG_NAME = "campaign-config.json"
PLAN_NAME = "shard-plan.json"
RECEIPT_DIRECTORY = "affine-receipts"
CHILD_DIRECTORY = "ordered-children"
FINAL_NAME = "certificate.json"
LOCK_NAME = ".psi-affine-guard-campaign.lock"
U128_LIMIT = 1 << 128
SCALE = 1 << 64

_RECEIPT_NAME = re.compile(r"receipt-([0-9]{8})\.json\Z")
_CHILD_NAME = re.compile(r"child-([0-9]{8})\.json\Z")
_RECEIPT_LOCK_NAME = re.compile(r"\.receipt-([0-9]{8})\.json\.lock\Z")
_CHILD_LOCK_NAME = re.compile(r"\.child-([0-9]{8})\.json\.lock\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CHILD_DOMAIN = b"sparkinterval/tg/psi-affine-child/v1\x00"
_NODE_DOMAIN = b"sparkinterval/tg/psi-affine-node/v1\x00"
_ODD_DOMAIN = b"sparkinterval/tg/psi-affine-odd/v1\x00"
_EMPTY_DOMAIN = b"sparkinterval/tg/psi-affine-empty/v1\x00"
_CERTIFICATE_DOMAIN = b"sparkinterval/tg/psi-affine-certificate/v1\x00"

CAPABILITIES = {
    "source_run_completed": False,
    "execution_attested": False,
    "primesieve_to_mathlib_realization_proved": False,
    "crlibm_to_mathlib_realization_proved": False,
    "compiler_or_cpu_refinement_proved": False,
    "receipt_admitted": False,
    "lean_atom_discharged": False,
}


class PsiAffineCampaignError(RuntimeError):
    """A one-pass plan, receipt, scan, or commitment failed closed."""


@dataclass(frozen=True)
class PsiAffineCampaignResult:
    mode: str
    plan_sha256: str
    shard_count: int
    receipts: int
    complete: bool
    full_source_range: bool
    final_state: tuple[int, int] | None
    child_merkle_root_sha256: str | None
    certificate_root_sha256: str | None
    source_run_completed: bool = False
    execution_attested: bool = False
    lean_atom_discharged: bool = False

    def as_json(self) -> dict[str, Any]:
        result = asdict(self)
        if self.final_state is not None:
            result["final_state"] = list(self.final_state)
        return result


def _integer(
    value: object, name: str, *, minimum: int | None = None
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PsiAffineCampaignError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise PsiAffineCampaignError(f"{name} must be at least {minimum}")
    return value


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PsiAffineCampaignError(
            f"{name} must be lowercase 64-digit SHA-256"
        )
    return value


def _read(path: Path, limit: int, label: str) -> bytes:
    try:
        return read_bytes_once(path, limit=limit)
    except CampaignIOError as exc:
        raise PsiAffineCampaignError(f"cannot read {label}: {exc}") from exc


def _load_control(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except CampaignIOError as exc:
        raise PsiAffineCampaignError(str(exc)) from exc
    if not isinstance(value, dict):
        raise PsiAffineCampaignError(f"control file is not an object: {path}")
    return value


def _load_receipt(raw: bytes, label: str) -> dict[str, Any]:
    if not raw or len(raw) > MAX_RECEIPT_BYTES:
        raise PsiAffineCampaignError(f"{label} has invalid byte length")
    try:
        value = load_decimal_json_bytes(raw, label=label)
    except EvidenceError as exc:
        raise PsiAffineCampaignError(str(exc)) from exc
    if not isinstance(value, dict):
        raise PsiAffineCampaignError(f"{label} is not an object")
    return value


def _plan_identity(
    runner_sha256: str,
    source_sha256: str,
    upstream_sha256: str,
    sieve_size_kib: int,
) -> str:
    return (
        f"{CAMPAIGN_ALGORITHM};runner={runner_sha256};"
        f"source={source_sha256};upstreams={upstream_sha256};"
        f"sieve_kib={sieve_size_kib}"
    )


def create_plan(
    *,
    runner_sha256: str,
    source_sha256: str,
    upstream_manifest_sha256: str,
    sieve_size_kib: int = DEFAULT_SIEVE_SIZE_KIB,
    domain_upper_exclusive: int = SOURCE_UPPER_EXCLUSIVE,
    shard_span: int = DEFAULT_SHARD_SPAN,
    allow_bounded_test: bool = False,
) -> FixedShardPlan:
    for value, name in (
        (runner_sha256, "runner SHA"),
        (source_sha256, "source SHA"),
        (upstream_manifest_sha256, "upstream SHA"),
    ):
        _digest(value, name)
    upper = _integer(domain_upper_exclusive, "domain upper", minimum=3)
    span = _integer(shard_span, "shard span", minimum=1)
    sieve = _integer(sieve_size_kib, "sieve size", minimum=16)
    if upper > SOURCE_UPPER_EXCLUSIVE or sieve > 8192:
        raise PsiAffineCampaignError("campaign range or sieve size is invalid")
    full = upper == SOURCE_UPPER_EXCLUSIVE
    if not full and not allow_bounded_test:
        raise PsiAffineCampaignError(
            "a bounded campaign requires allow_bounded_test=True"
        )
    if full and span != DEFAULT_SHARD_SPAN:
        raise PsiAffineCampaignError(
            "the full campaign requires fixed 100,000,000-integer shards"
        )
    ranges: list[tuple[int, int]] = []
    lower = SOURCE_LOWER
    while lower < upper:
        following = min(upper, lower + span)
        ranges.append((lower, following))
        lower = following
    try:
        return FixedShardPlan.from_ranges(
            algorithm=_plan_identity(
                runner_sha256,
                source_sha256,
                upstream_manifest_sha256,
                sieve,
            ),
            state_dimension=2,
            ranges=ranges,
        )
    except AffineGuardCertificateError as exc:
        raise PsiAffineCampaignError(str(exc)) from exc


def _expected_config(
    *,
    plan: FixedShardPlan,
    runner_sha256: str,
    runner_size: int,
    source_sha256: str,
    source_size: int,
    upstream_sha256: str,
    shard_span: int,
    sieve_size_kib: int,
) -> dict[str, Any]:
    full = plan.domain_upper == SOURCE_UPPER_EXCLUSIVE
    return {
        "schema": CAMPAIGN_SCHEMA,
        "algorithm": CAMPAIGN_ALGORITHM,
        "runner_algorithm": AFFINE_ALGORITHM,
        "classification": CLASSIFICATION,
        "mode": "full_source" if full else "bounded_test",
        "atom": ATOM,
        "domain_lower": plan.domain_lower,
        "domain_upper_exclusive": plan.domain_upper,
        "source_event_count": SOURCE_EVENT_COUNT,
        "shard_span": shard_span,
        "shard_count": len(plan.shards),
        "sieve_size_kib": sieve_size_kib,
        "state_components": list(STATE_COMPONENTS),
        "root_state": [0, 0],
        "plan_sha256": plan.plan_sha256,
        "captured_runner_sha256": runner_sha256,
        "captured_runner_size": runner_size,
        "captured_source_sha256": source_sha256,
        "captured_source_size": source_size,
        "upstream_manifest_sha256": upstream_sha256,
        "primesieve_commit": PRIMESIEVE_COMMIT,
        "crlibm_commit": CRLIBM_COMMIT,
        "capabilities": dict(CAPABILITIES),
    }


def initialize_campaign(
    *,
    runner: Path,
    runner_source: Path,
    upstream_manifest: Path,
    output_directory: Path,
    shard_span: int = DEFAULT_SHARD_SPAN,
    sieve_size_kib: int = DEFAULT_SIEVE_SIZE_KIB,
    domain_upper_exclusive: int = SOURCE_UPPER_EXCLUSIVE,
    allow_bounded_test: bool = False,
) -> PsiAffineCampaignResult:
    runner_raw = _read(runner, MAX_RUNNER_BYTES, "runner")
    source_raw = _read(runner_source, MAX_SOURCE_BYTES, "source")
    upstream_raw = _read(
        upstream_manifest, MAX_SOURCE_BYTES, "upstream manifest"
    )
    try:
        _validate_upstream_manifest(upstream_raw)
    except PsiResidualCampaignError as exc:
        raise PsiAffineCampaignError(str(exc)) from exc
    runner_sha = sha256_bytes(runner_raw)
    source_sha = sha256_bytes(source_raw)
    upstream_sha = sha256_bytes(upstream_raw)
    plan = create_plan(
        runner_sha256=runner_sha,
        source_sha256=source_sha,
        upstream_manifest_sha256=upstream_sha,
        sieve_size_kib=sieve_size_kib,
        domain_upper_exclusive=domain_upper_exclusive,
        shard_span=shard_span,
        allow_bounded_test=allow_bounded_test,
    )
    config = _expected_config(
        plan=plan,
        runner_sha256=runner_sha,
        runner_size=len(runner_raw),
        source_sha256=source_sha,
        source_size=len(source_raw),
        upstream_sha256=upstream_sha,
        shard_span=shard_span,
        sieve_size_kib=sieve_size_kib,
    )
    if output_directory.exists() and not output_directory.is_dir():
        raise PsiAffineCampaignError("output path is not a directory")
    output_directory.mkdir(parents=True, exist_ok=True)
    try:
        with advisory_lock(output_directory / LOCK_NAME):
            captures = (
                (CAPTURED_RUNNER_NAME, runner_raw),
                (CAPTURED_SOURCE_NAME, source_raw),
                (CAPTURED_UPSTREAM_NAME, upstream_raw),
            )
            paths = [output_directory / name for name, _ in captures]
            paths += [
                output_directory / CONFIG_NAME,
                output_directory / PLAN_NAME,
            ]
            if any(path.exists() for path in paths):
                if not all(path.is_file() for path in paths):
                    raise PsiAffineCampaignError(
                        "campaign initialization is partial"
                    )
                for name, raw in captures:
                    if _read(
                        output_directory / name, max(1, len(raw)), name
                    ) != raw:
                        raise PsiAffineCampaignError(
                            f"captured identity changed: {name}"
                        )
                if _load_control(output_directory / CONFIG_NAME) != config:
                    raise PsiAffineCampaignError(
                        "resume configuration changed"
                    )
                if _load_control(
                    output_directory / PLAN_NAME
                ) != plan.to_dict():
                    raise PsiAffineCampaignError("fixed plan changed")
            else:
                for name, raw in captures:
                    atomic_write_bytes(output_directory / name, raw)
                write_immutable_json(
                    output_directory / CONFIG_NAME, config
                )
                write_immutable_json(
                    output_directory / PLAN_NAME, plan.to_dict()
                )
            (output_directory / CAPTURED_RUNNER_NAME).chmod(
                stat.S_IRUSR
                | stat.S_IXUSR
                | stat.S_IRGRP
                | stat.S_IXGRP
            )
    except (CampaignIOError, OSError) as exc:
        raise PsiAffineCampaignError(str(exc)) from exc
    return verify_campaign(output_directory)


def _load_setup(
    output_directory: Path,
) -> tuple[dict[str, Any], FixedShardPlan]:
    config = _load_control(output_directory / CONFIG_NAME)
    required = {
        "schema",
        "algorithm",
        "runner_algorithm",
        "classification",
        "mode",
        "atom",
        "domain_lower",
        "domain_upper_exclusive",
        "source_event_count",
        "shard_span",
        "shard_count",
        "sieve_size_kib",
        "state_components",
        "root_state",
        "plan_sha256",
        "captured_runner_sha256",
        "captured_runner_size",
        "captured_source_sha256",
        "captured_source_size",
        "upstream_manifest_sha256",
        "primesieve_commit",
        "crlibm_commit",
        "capabilities",
    }
    if set(config) != required:
        raise PsiAffineCampaignError("campaign config fields changed")
    if (
        config.get("schema") != CAMPAIGN_SCHEMA
        or config.get("algorithm") != CAMPAIGN_ALGORITHM
        or config.get("runner_algorithm") != AFFINE_ALGORITHM
        or config.get("classification") != CLASSIFICATION
        or config.get("atom") != ATOM
        or config.get("source_event_count") != SOURCE_EVENT_COUNT
        or config.get("state_components") != list(STATE_COMPONENTS)
        or config.get("root_state") != [0, 0]
        or config.get("primesieve_commit") != PRIMESIEVE_COMMIT
        or config.get("crlibm_commit") != CRLIBM_COMMIT
        or config.get("capabilities") != CAPABILITIES
    ):
        raise PsiAffineCampaignError(
            "campaign identity or capability boundary changed"
        )
    runner_raw = _read(
        output_directory / CAPTURED_RUNNER_NAME,
        MAX_RUNNER_BYTES,
        "captured runner",
    )
    source_raw = _read(
        output_directory / CAPTURED_SOURCE_NAME,
        MAX_SOURCE_BYTES,
        "captured source",
    )
    upstream_raw = _read(
        output_directory / CAPTURED_UPSTREAM_NAME,
        MAX_SOURCE_BYTES,
        "captured upstream manifest",
    )
    try:
        _validate_upstream_manifest(upstream_raw)
    except PsiResidualCampaignError as exc:
        raise PsiAffineCampaignError(str(exc)) from exc
    if (
        sha256_bytes(runner_raw) != config["captured_runner_sha256"]
        or len(runner_raw) != config["captured_runner_size"]
        or sha256_bytes(source_raw) != config["captured_source_sha256"]
        or len(source_raw) != config["captured_source_size"]
        or sha256_bytes(upstream_raw) != config["upstream_manifest_sha256"]
    ):
        raise PsiAffineCampaignError("captured file identity changed")
    try:
        plan = FixedShardPlan.from_dict(
            _load_control(output_directory / PLAN_NAME)
        )
    except AffineGuardCertificateError as exc:
        raise PsiAffineCampaignError(str(exc)) from exc
    expected = create_plan(
        runner_sha256=config["captured_runner_sha256"],
        source_sha256=config["captured_source_sha256"],
        upstream_manifest_sha256=config["upstream_manifest_sha256"],
        sieve_size_kib=config["sieve_size_kib"],
        domain_upper_exclusive=config["domain_upper_exclusive"],
        shard_span=config["shard_span"],
        allow_bounded_test=config["mode"] == "bounded_test",
    )
    if (
        plan.to_dict() != expected.to_dict()
        or config["plan_sha256"] != plan.plan_sha256
        or config["shard_count"] != len(plan.shards)
        or config["domain_lower"] != plan.domain_lower
        or config["domain_upper_exclusive"] != plan.domain_upper
        or config["mode"]
        != (
            "full_source"
            if plan.domain_upper == SOURCE_UPPER_EXCLUSIVE
            else "bounded_test"
        )
    ):
        raise PsiAffineCampaignError("fixed plan/configuration changed")
    return config, plan


def command_for_shard(
    output_directory: Path, shard_index: int
) -> tuple[str, ...]:
    config, plan = _load_setup(output_directory)
    index = _integer(shard_index, "shard index", minimum=0)
    if index >= len(plan.shards):
        raise PsiAffineCampaignError("shard index is outside the plan")
    return _command(output_directory, config, plan, index)


def _command(
    output_directory: Path,
    config: Mapping[str, Any],
    plan: FixedShardPlan,
    index: int,
) -> tuple[str, ...]:
    shard = plan.shards[index]
    return (
        os.fspath((output_directory / CAPTURED_RUNNER_NAME).resolve()),
        "--mode",
        "affine",
        "--lower",
        str(shard.lower),
        "--upper",
        str(shard.upper - 1),
        "--sieve-size-kib",
        str(config["sieve_size_kib"]),
    )


def grouped_shard_indices(
    output_directory: Path, *, group_index: int, group_count: int
) -> tuple[int, ...]:
    """Return one exact disjoint strided group of fixed-plan shard indices."""

    _, plan = _load_setup(output_directory)
    count = _integer(group_count, "worker group count", minimum=1)
    index = _integer(group_index, "worker group index", minimum=0)
    if count > len(plan.shards):
        raise PsiAffineCampaignError(
            "worker group count cannot exceed the fixed-plan shard count"
        )
    if index >= count:
        raise PsiAffineCampaignError(
            "worker group index is outside the group count"
        )
    return tuple(range(index, len(plan.shards), count))


def validate_affine_receipt(
    report: Mapping[str, Any],
    *,
    shard_lower: int,
    shard_upper: int,
    sieve_size_kib: int,
) -> dict[str, Any]:
    if set(report) != AFFINE_FIELDS:
        raise PsiAffineCampaignError("affine receipt fields changed")
    if (
        report.get("algorithm") != AFFINE_ALGORITHM
        or report.get("mode") != "affine"
        or report.get("classification") != "source-scale-shard-not-lean-proof"
        or report.get("atom") != ATOM
        or report.get("primesieve_commit") != PRIMESIEVE_COMMIT
        or report.get("crlibm_commit") != CRLIBM_COMMIT
        or report.get("lower") != shard_lower
        or report.get("upper_exclusive") != shard_upper
        or report.get("work_count") != shard_upper - shard_lower
        or report.get("scale_bits") != 64
        or report.get("sieve_size_kib") != sieve_size_kib
        or report.get("log_interval_encoding")
        != "crlibm-binary64-directed-to-q64-v1"
        or report.get("event_encoding")
        != "u64be-value-u64be-prime-u32be-exponent-v1"
        or report.get("row_encoding")
        != "u64be-value-u64be-prime-u32be-exponent-u128be-log-pair-v1"
        or report.get("state_components") != list(STATE_COMPONENTS)
        or report.get("guard_encoding")
        != "independent-q64-rectangle-with-lower-le-upper-v1"
        or report.get("incoming_state") is not None
        or report.get("outgoing_state") is not None
        or report.get("accepted") is not True
        or report.get("execution_attested") is not False
        or report.get("lean_atom_discharged") is not False
    ):
        raise PsiAffineCampaignError(
            "affine receipt identity, range, or trust flags changed"
        )
    elapsed = report.get("elapsed_seconds")
    if not isinstance(elapsed, Decimal) or not elapsed.is_finite() or elapsed < 0:
        raise PsiAffineCampaignError("affine elapsed time is malformed")
    for field in ("event_sha256", "row_sha256"):
        _digest(report.get(field), field)
    events = _integer(
        report.get("prime_power_events"), "prime-power events", minimum=1
    )
    primes = _integer(report.get("prime_events"), "prime events", minimum=0)
    higher = _integer(
        report.get("higher_power_events"), "higher-power events", minimum=0
    )
    if events != primes + higher:
        raise PsiAffineCampaignError("event count partition changed")
    if events > shard_upper - shard_lower:
        raise PsiAffineCampaignError("event count exceeds the shard width")
    delta = report.get("delta")
    if (
        not isinstance(delta, list)
        or len(delta) != 2
        or any(
            isinstance(item, bool)
            or not isinstance(item, int)
            or not 0 <= item < U128_LIMIT
            for item in delta
        )
        or not 0 < delta[0] <= delta[1]
        or delta[1] > events * 31 * SCALE
    ):
        raise PsiAffineCampaignError("affine delta is malformed")
    bounds = report.get("allowed_incoming_q64")
    if not isinstance(bounds, dict) or set(bounds) != {
        "lower_min",
        "upper_max",
        "predicate",
    }:
        raise PsiAffineCampaignError("affine bound fields changed")
    minimum = _integer(bounds.get("lower_min"), "minimum lower", minimum=0)
    maximum = _integer(bounds.get("upper_max"), "maximum upper", minimum=0)
    if (
        minimum > maximum
        or maximum >= U128_LIMIT
        or bounds.get("predicate") != "lower_min<=lower<=upper<=upper_max"
        or maximum + delta[0] >= U128_LIMIT
        or maximum + delta[1] >= U128_LIMIT
    ):
        raise PsiAffineCampaignError(
            "affine rectangle is empty, malformed, or permits overflow"
        )
    witnesses = report.get("guard_witnesses")
    if not isinstance(witnesses, dict) or set(witnesses) != {
        "lower_min",
        "upper_max",
    }:
        raise PsiAffineCampaignError("affine witness set changed")
    lower = witnesses.get("lower_min")
    upper = witnesses.get("upper_max")
    if (
        not isinstance(lower, dict)
        or set(lower)
        != {
            "event_index",
            "value",
            "prefix_delta_q64",
            "radius_q64",
            "strict",
            "kind",
        }
        or not isinstance(upper, dict)
        or set(upper)
        != {
            "event_index",
            "value",
            "prefix_delta_q64",
            "radius_q64",
            "kind",
        }
    ):
        raise PsiAffineCampaignError("affine witness fields changed")
    lower_index = _integer(
        lower.get("event_index"), "lower witness event index", minimum=0
    )
    lower_value = _integer(
        lower.get("value"), "lower witness value", minimum=shard_lower
    )
    lower_prefix = _integer(
        lower.get("prefix_delta_q64"), "lower witness prefix", minimum=0
    )
    lower_radius = _integer(
        lower.get("radius_q64"), "lower witness radius", minimum=0
    )
    strict = lower.get("strict")
    terminal = shard_upper == SOURCE_UPPER_EXCLUSIVE
    if (
        report.get("terminal_strict_lower_constrained") is not terminal
        or not isinstance(strict, bool)
        or lower_prefix > delta[0]
    ):
        raise PsiAffineCampaignError("lower witness classification changed")
    if lower.get("kind") == "terminal_strict_lower":
        if (
            not terminal
            or not strict
            or lower_index != events
            or lower_value != SOURCE_UPPER_EXCLUSIVE - 1
            or lower_prefix != delta[0]
        ):
            raise PsiAffineCampaignError("terminal lower witness is inconsistent")
    elif lower.get("kind") == "lower_left_limit":
        if (
            strict
            or lower_index >= events
            or not shard_lower <= lower_value < shard_upper
        ):
            raise PsiAffineCampaignError("ordinary lower witness is inconsistent")
    else:
        raise PsiAffineCampaignError("lower witness kind changed")
    if (
        lower_radius != _lower_radius(lower_value, strict)
        or minimum
        != max(0, lower_value * SCALE - lower_radius - lower_prefix)
    ):
        raise PsiAffineCampaignError(
            "lower witness radius or attaining equation changed"
        )
    upper_index = _integer(
        upper.get("event_index"), "upper witness event index", minimum=0
    )
    upper_value = _integer(
        upper.get("value"), "upper witness value", minimum=shard_lower
    )
    upper_prefix = _integer(
        upper.get("prefix_delta_q64"), "upper witness prefix", minimum=0
    )
    upper_radius = _integer(
        upper.get("radius_q64"), "upper witness radius", minimum=0
    )
    if (
        upper.get("kind") != "upper_post_jump"
        or upper_index >= events
        or not shard_lower <= upper_value < shard_upper
        or not 0 < upper_prefix <= delta[1]
        or upper_radius != _upper_radius(upper_value)
        or maximum
        != upper_value * SCALE + upper_radius - upper_prefix
    ):
        raise PsiAffineCampaignError(
            "upper witness radius or attaining equation changed"
        )
    if report.get("guard_derivation") != {
        "sqrt_fraction_bits": 16,
        "lower_radius": "floor(sqrt(2*x)*2^16)*2^48",
        "upper_radius": (
            "floor(19764819*floor(sqrt(x)*2^16)*2^48/25000000)"
        ),
    }:
        raise PsiAffineCampaignError("guard derivation changed")
    return dict(report)


def _receipt_path(output_directory: Path, index: int) -> Path:
    return output_directory / RECEIPT_DIRECTORY / f"receipt-{index:08d}.json"


def _child_path(output_directory: Path, index: int) -> Path:
    return output_directory / CHILD_DIRECTORY / f"child-{index:08d}.json"


def _receipt_indices(
    output_directory: Path, pattern: re.Pattern[str], directory: str
) -> tuple[int, ...]:
    root = output_directory / directory
    if not root.exists():
        return ()
    if not root.is_dir():
        raise PsiAffineCampaignError(f"{directory} is not a directory")
    lock_pattern = (
        _RECEIPT_LOCK_NAME
        if directory == RECEIPT_DIRECTORY
        else _CHILD_LOCK_NAME
    )
    indices: list[int] = []
    for path in root.iterdir():
        match = pattern.fullmatch(path.name)
        if match is None:
            if lock_pattern.fullmatch(path.name) is not None and path.is_file():
                continue
            raise PsiAffineCampaignError(
                f"unexpected file in {directory}: {path.name}"
            )
        if not path.is_file():
            raise PsiAffineCampaignError(f"unexpected file in {directory}: {path.name}")
        indices.append(int(match.group(1)))
    if len(indices) != len(set(indices)):
        raise PsiAffineCampaignError(f"duplicate index in {directory}")
    return tuple(sorted(indices))


def ingest_receipt_bytes(
    output_directory: Path, shard_index: int, raw: bytes
) -> None:
    config, plan = _load_setup(output_directory)
    index = _integer(shard_index, "shard index", minimum=0)
    if index >= len(plan.shards):
        raise PsiAffineCampaignError("shard index is outside the plan")
    _validate_receipt_for_index(
        raw=raw, index=index, config=config, plan=plan
    )
    _retain_receipt_bytes(output_directory, index, raw)


def _validate_receipt_for_index(
    *,
    raw: bytes,
    index: int,
    config: Mapping[str, Any],
    plan: FixedShardPlan,
) -> dict[str, Any]:
    shard = plan.shards[index]
    report = _load_receipt(raw, f"affine shard {index}")
    validate_affine_receipt(
        report,
        shard_lower=shard.lower,
        shard_upper=shard.upper,
        sieve_size_kib=config["sieve_size_kib"],
    )
    return report


def _retain_receipt_bytes(
    output_directory: Path, index: int, raw: bytes
) -> None:
    destination = _receipt_path(output_directory, index)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with advisory_lock(output_directory / LOCK_NAME):
            if destination.exists():
                if _read(
                    destination, MAX_RECEIPT_BYTES, f"receipt {index}"
                ) != raw:
                    raise PsiAffineCampaignError(
                        f"receipt {index} is already bound to different bytes"
                    )
            else:
                atomic_write_bytes(destination, raw)
    except CampaignIOError as exc:
        raise PsiAffineCampaignError(str(exc)) from exc


def ingest_receipt(
    output_directory: Path, shard_index: int, receipt_path: Path
) -> None:
    ingest_receipt_bytes(
        output_directory,
        shard_index,
        _read(receipt_path, MAX_RECEIPT_BYTES, "external receipt"),
    )


def run_campaign(
    output_directory: Path,
    *,
    shard_indices: Sequence[int] | None = None,
    workers: int = DEFAULT_WORKERS,
    max_shards: int | None = None,
    timeout_seconds: int | None = None,
) -> PsiAffineCampaignResult:
    config, plan = _load_setup(output_directory)
    worker_count = _integer(workers, "workers", minimum=1)
    if max_shards is not None:
        _integer(max_shards, "max shards", minimum=1)
    if timeout_seconds is not None:
        _integer(timeout_seconds, "timeout seconds", minimum=1)
    existing = set(
        _receipt_indices(
            output_directory, _RECEIPT_NAME, RECEIPT_DIRECTORY
        )
    )
    if shard_indices is None:
        indices = [
            index
            for index in range(len(plan.shards))
            if index not in existing
        ]
    else:
        indices = []
        seen: set[int] = set()
        for raw_index in shard_indices:
            index = _integer(raw_index, "shard index", minimum=0)
            if index >= len(plan.shards):
                raise PsiAffineCampaignError(
                    "shard index is outside the fixed plan"
                )
            if index in seen:
                raise PsiAffineCampaignError(
                    "duplicate requested shard index"
                )
            seen.add(index)
            if index not in existing:
                indices.append(index)
    if max_shards is not None:
        indices = indices[:max_shards]

    def execute(index: int) -> tuple[int, bytes]:
        try:
            completed = subprocess.run(
                _command(output_directory, config, plan, index),
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PsiAffineCampaignError(
                f"affine shard {index} execution failed: {exc}"
            ) from exc
        if completed.returncode != 0:
            raise PsiAffineCampaignError(
                f"affine shard {index} failed ({completed.returncode}): "
                f"{completed.stderr[:4096].decode('utf-8', errors='replace').strip()}"
            )
        if len(completed.stdout) > MAX_RECEIPT_BYTES:
            raise PsiAffineCampaignError(
                f"affine shard {index} emitted an oversized receipt"
            )
        return index, completed.stdout

    iterator = iter(indices)
    pending: dict[Future[tuple[int, bytes]], int] = {}
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        for _ in range(min(len(indices), worker_count * 2)):
            index = next(iterator, None)
            if index is None:
                break
            pending[executor.submit(execute, index)] = index
        while pending:
            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                index = pending.pop(future)
                try:
                    returned_index, raw = future.result()
                    if returned_index != index:
                        raise PsiAffineCampaignError(
                            "worker result index changed"
                        )
                    _validate_receipt_for_index(
                        raw=raw, index=index, config=config, plan=plan
                    )
                    _retain_receipt_bytes(output_directory, index, raw)
                except BaseException:
                    for other in pending:
                        other.cancel()
                    raise
                following = next(iterator, None)
                if following is not None:
                    pending[executor.submit(execute, following)] = following
    return verify_campaign(output_directory)


def _load_all_receipts(
    output_directory: Path,
    config: Mapping[str, Any],
    plan: FixedShardPlan,
    *,
    require_complete: bool,
) -> list[tuple[bytes, dict[str, Any]]]:
    indices = _receipt_indices(
        output_directory, _RECEIPT_NAME, RECEIPT_DIRECTORY
    )
    expected = tuple(range(len(plan.shards)))
    if any(index >= len(plan.shards) for index in indices):
        raise PsiAffineCampaignError("receipt index is outside the fixed plan")
    if require_complete and indices != expected:
        raise PsiAffineCampaignError("affine receipt phase is incomplete")
    result: list[tuple[bytes, dict[str, Any]]] = []
    for index in indices:
        raw = _read(
            _receipt_path(output_directory, index),
            MAX_RECEIPT_BYTES,
            f"receipt {index}",
        )
        report = _load_receipt(raw, f"affine shard {index}")
        shard = plan.shards[index]
        validate_affine_receipt(
            report,
            shard_lower=shard.lower,
            shard_upper=shard.upper,
            sieve_size_kib=config["sieve_size_kib"],
        )
        result.append((raw, report))
    return result


def _child_payload(
    *,
    plan: FixedShardPlan,
    index: int,
    raw: bytes,
    report: Mapping[str, Any],
    incoming: tuple[int, int],
    outgoing: tuple[int, int],
) -> dict[str, Any]:
    shard = plan.shards[index]
    return {
        "child_schema": CHILD_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "index": index,
        "lower": shard.lower,
        "upper_exclusive": shard.upper,
        "work_count": shard.work_count,
        "receipt_sha256": sha256_bytes(raw),
        "event_sha256": report["event_sha256"],
        "row_sha256": report["row_sha256"],
        "prime_power_events": report["prime_power_events"],
        "prime_events": report["prime_events"],
        "higher_power_events": report["higher_power_events"],
        "delta": report["delta"],
        "allowed_incoming_q64": report["allowed_incoming_q64"],
        "guard_witnesses": report["guard_witnesses"],
        "terminal_strict_lower_constrained": report[
            "terminal_strict_lower_constrained"
        ],
        "incoming_state": list(incoming),
        "outgoing_state": list(outgoing),
    }


def _child_sha(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _CHILD_DOMAIN + canonical_json_bytes(dict(payload))
    ).hexdigest()


def _merkle_root(digests: Sequence[str]) -> str:
    if not digests:
        return hashlib.sha256(_EMPTY_DOMAIN).hexdigest()
    level = [bytes.fromhex(_digest(item, "child digest")) for item in digests]
    while len(level) > 1:
        following: list[bytes] = []
        for index in range(0, len(level), 2):
            left = level[index]
            if index + 1 == len(level):
                following.append(hashlib.sha256(_ODD_DOMAIN + left).digest())
            else:
                following.append(
                    hashlib.sha256(
                        _NODE_DOMAIN + left + level[index + 1]
                    ).digest()
                )
        level = following
    return level[0].hex()


def _derive_children(
    *,
    plan: FixedShardPlan,
    receipts: Sequence[tuple[bytes, Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], tuple[int, int], int]:
    current = (0, 0)
    children: list[dict[str, Any]] = []
    total_events = 0
    for index, (raw, report) in enumerate(receipts):
        bounds = report["allowed_incoming_q64"]
        if not (
            bounds["lower_min"]
            <= current[0]
            <= current[1]
            <= bounds["upper_max"]
        ):
            raise PsiAffineCampaignError(
                f"root-derived incoming state violates shard {index} rectangle"
            )
        delta = report["delta"]
        outgoing = (current[0] + delta[0], current[1] + delta[1])
        if (
            outgoing[1] >= U128_LIMIT
            or outgoing[0] > outgoing[1]
        ):
            raise PsiAffineCampaignError(
                f"shard {index} outgoing state overflows or reverses"
            )
        payload = _child_payload(
            plan=plan,
            index=index,
            raw=raw,
            report=report,
            incoming=current,
            outgoing=outgoing,
        )
        children.append(
            {**payload, "child_sha256": _child_sha(payload)}
        )
        total_events += report["prime_power_events"]
        current = outgoing
    return children, current, total_events


def _certificate_payload(
    *,
    config: Mapping[str, Any],
    plan: FixedShardPlan,
    children: Sequence[Mapping[str, Any]],
    final_state: tuple[int, int],
    total_events: int,
) -> dict[str, Any]:
    child_digests = [child["child_sha256"] for child in children]
    full = plan.domain_upper == SOURCE_UPPER_EXCLUSIVE
    if full and total_events != SOURCE_EVENT_COUNT:
        raise PsiAffineCampaignError(
            "full-source event count differs from the pinned value"
        )
    return {
        "schema": FINAL_SCHEMA,
        "algorithm": CAMPAIGN_ALGORITHM,
        "classification": CLASSIFICATION,
        "mode": config["mode"],
        "atom": ATOM,
        "plan_sha256": plan.plan_sha256,
        "root_state": [0, 0],
        "final_state": list(final_state),
        "shard_count": len(children),
        "total_prime_power_events": total_events,
        "source_event_count": SOURCE_EVENT_COUNT,
        "source_event_count_matches": full and total_events == SOURCE_EVENT_COUNT,
        "full_source_range": full,
        "ordered_child_sha256": child_digests,
        "child_merkle_root_sha256": _merkle_root(child_digests),
        "capabilities": dict(CAPABILITIES),
    }


def finalize_campaign(
    output_directory: Path,
) -> PsiAffineCampaignResult:
    config, plan = _load_setup(output_directory)
    receipts = _load_all_receipts(
        output_directory, config, plan, require_complete=True
    )
    children, final_state, total_events = _derive_children(
        plan=plan, receipts=receipts
    )
    payload = _certificate_payload(
        config=config,
        plan=plan,
        children=children,
        final_state=final_state,
        total_events=total_events,
    )
    certificate_root = hashlib.sha256(
        _CERTIFICATE_DOMAIN + canonical_json_bytes(payload)
    ).hexdigest()
    certificate = {
        **payload,
        "certificate_root_sha256": certificate_root,
    }
    try:
        with advisory_lock(output_directory / LOCK_NAME):
            child_root = output_directory / CHILD_DIRECTORY
            child_root.mkdir(parents=True, exist_ok=True)
            existing = _receipt_indices(
                output_directory, _CHILD_NAME, CHILD_DIRECTORY
            )
            if existing and existing != tuple(range(len(children))):
                raise PsiAffineCampaignError(
                    "ordered child files are missing, duplicated, or reordered"
                )
            for index, child in enumerate(children):
                path = _child_path(output_directory, index)
                if path.exists():
                    if _load_control(path) != child:
                        raise PsiAffineCampaignError(
                            f"retained child {index} changed"
                        )
                else:
                    write_immutable_json(path, child)
            final_path = output_directory / FINAL_NAME
            if final_path.exists():
                if _load_control(final_path) != certificate:
                    raise PsiAffineCampaignError("certificate changed")
            else:
                write_immutable_json(final_path, certificate)
    except (CampaignIOError, OSError) as exc:
        raise PsiAffineCampaignError(str(exc)) from exc
    return verify_campaign(output_directory)


def _validate_retained_children(
    output_directory: Path,
    expected: Sequence[Mapping[str, Any]],
) -> None:
    indices = _receipt_indices(
        output_directory, _CHILD_NAME, CHILD_DIRECTORY
    )
    if indices != tuple(range(len(expected))):
        raise PsiAffineCampaignError(
            "ordered child files are incomplete or reordered"
        )
    for index, wanted in enumerate(expected):
        actual = _load_control(_child_path(output_directory, index))
        if set(actual) != set(wanted) or actual != wanted:
            raise PsiAffineCampaignError(
                f"retained ordered child {index} changed"
            )
        payload = dict(actual)
        digest = payload.pop("child_sha256", None)
        if digest != _child_sha(payload):
            raise PsiAffineCampaignError(
                f"retained child {index} digest changed"
            )


def verify_campaign(
    output_directory: Path,
) -> PsiAffineCampaignResult:
    config, plan = _load_setup(output_directory)
    receipts = _load_all_receipts(
        output_directory, config, plan, require_complete=False
    )
    complete = len(receipts) == len(plan.shards)
    final_state: tuple[int, int] | None = None
    child_root: str | None = None
    certificate_root: str | None = None
    final_path = output_directory / FINAL_NAME
    child_directory = output_directory / CHILD_DIRECTORY
    if final_path.exists() or child_directory.exists():
        if not complete:
            raise PsiAffineCampaignError(
                "certificate artifacts exist before receipt completion"
            )
        children, final_state, total_events = _derive_children(
            plan=plan, receipts=receipts
        )
        _validate_retained_children(output_directory, children)
        payload = _certificate_payload(
            config=config,
            plan=plan,
            children=children,
            final_state=final_state,
            total_events=total_events,
        )
        expected_root = hashlib.sha256(
            _CERTIFICATE_DOMAIN + canonical_json_bytes(payload)
        ).hexdigest()
        if not final_path.is_file():
            raise PsiAffineCampaignError("final certificate is missing")
        certificate = _load_control(final_path)
        expected = {
            **payload,
            "certificate_root_sha256": expected_root,
        }
        if certificate != expected:
            raise PsiAffineCampaignError("final certificate changed")
        child_root = payload["child_merkle_root_sha256"]
        certificate_root = expected_root
    return PsiAffineCampaignResult(
        mode=config["mode"],
        plan_sha256=plan.plan_sha256,
        shard_count=len(plan.shards),
        receipts=len(receipts),
        complete=complete and final_path.is_file(),
        full_source_range=plan.domain_upper == SOURCE_UPPER_EXCLUSIVE,
        final_state=final_state,
        child_merkle_root_sha256=child_root,
        certificate_root_sha256=certificate_root,
    )


__all__ = [
    "CAMPAIGN_ALGORITHM",
    "CAMPAIGN_SCHEMA",
    "CHILD_SCHEMA",
    "FINAL_SCHEMA",
    "PsiAffineCampaignError",
    "PsiAffineCampaignResult",
    "command_for_shard",
    "create_plan",
    "finalize_campaign",
    "grouped_shard_indices",
    "ingest_receipt",
    "ingest_receipt_bytes",
    "initialize_campaign",
    "run_campaign",
    "validate_affine_receipt",
    "verify_campaign",
]
