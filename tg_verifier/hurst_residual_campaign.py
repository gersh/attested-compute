# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Two-pass campaign for the source-scale Hurst residual shard runner.

The first pass is embarrassingly parallel: every fixed shard is run in
``summary`` mode and contributes an exact four-coordinate additive delta.
Only after *all* summaries are present does the reducer derive every incoming
state from the single root ``(0, 0, 0, 0)``.  The second pass independently
reruns every shard in ``verify`` mode with that derived state.

The retained certificate binds the ordered ranges, captured executable,
adapter source, pinned upstream manifest, row hashes, deltas, and singleton
boundary states.  It is external finite-computation evidence; by itself it is
neither hardware attestation nor a Lean theorem.
"""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from decimal import Decimal
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import threading
import time
from typing import Any, Mapping, Sequence

from .affine_guard_certificate import (
    AffineGuardCertificateError,
    AffineGuardLeaf,
    AffineGuardTransition,
    EMPTY_EXCEPTION_ROOT_SHA256,
    FixedShardPlan,
    TightGuardWitness,
    make_affine_guard_leaf,
    verify_affine_guard_certificate,
)
from .campaign_io import (
    CampaignIOError,
    advisory_lock,
    atomic_write_bytes,
    canonical_sha256,
    hash_file_once,
    load_json,
    parse_json_bytes,
    read_bytes_once,
    sha256_bytes,
    write_immutable_json,
)
from .evidence import EvidenceError, load_decimal_json_bytes


CAMPAIGN_SCHEMA = "sparkinterval.tg.hurst-residual-campaign.v1"
DERIVED_SCHEMA = "sparkinterval.tg.hurst-residual-derived-inputs.v1"
FINAL_SCHEMA = "sparkinterval.tg.hurst-residual-certificate.v1"
RUNNER_ALGORITHM = "hurst-segmented-mobius-two-pass-v2"
CAMPAIGN_ALGORITHM = "hurst-segmented-mobius-four-residual-campaign-v2"
RUNNER_CLASSIFICATION = "source-scale-shard-not-lean-proof"
UPSTREAM_COMMIT = "fb47790c876c92690fce62990199ce961c5bdd72"

SOURCE_LOWER = 1
SOURCE_UPPER_EXCLUSIVE = 10_000_000_000_000_001
DEFAULT_SHARD_SPAN = 1_000_000_000_000
DEFAULT_WORKER_GROUPS = 320
DEFAULT_LOCAL_WORKERS = 1
MAX_FULL_SOURCE_SHARD_SPAN = 1_000_000_000_000
DEFAULT_SEGMENT_SIZE = 110_880_000
MIN_SEGMENT_SIZE = 13_860
MAX_SEGMENT_SIZE = 2_000_000_000
MAX_RUNNER_BYTES = 1 << 30
MAX_SOURCE_BYTES = 32 << 20
MAX_RECEIPT_BYTES = 4 << 20

ATOM_PROFILES = (
    "mertens-hurst",
    "cdem-squarefree",
    "platt-little-mertens-2-11",
    "platt-little-mertens-stronger",
)
STATE_COMPONENTS = ("M", "Q", "lm_lower_q96", "lm_upper_q96")
EXACT_FALLBACK_FIELDS = frozenset(
    {
        "mertens_hurst",
        "squarefree",
        "little_mertens_2_11",
        "little_mertens_stronger",
    }
)
RECEIPT_FIELDS = frozenset(
    {
        "algorithm",
        "mode",
        "classification",
        "upstream_commit",
        "lower",
        "upper_exclusive",
        "work_count",
        "segment_size",
        "segments",
        "row_encoding",
        "squarefree_threshold_endpoint_policy",
        "reduction_block_rows",
        "row_sha256",
        "state_components",
        "delta",
        "guards",
        "exact_fallbacks",
        "accepted",
        "elapsed_seconds",
        "execution_attested",
        "lean_atom_discharged",
    }
)

CAPTURED_RUNNER_NAME = "captured-hurst-residual-runner"
CAPTURED_SOURCE_NAME = "captured-hurst-residual-shard.cpp"
CAPTURED_UPSTREAM_NAME = "captured-hurst-upstream-manifest.json"
CONFIG_NAME = "campaign-config.json"
PLAN_NAME = "shard-plan.json"
DERIVED_NAME = "derived-inputs.json"
FINAL_NAME = "certificate.json"
LEAF_DIRECTORY = "affine-leaves"
_RECEIPT_NAME = re.compile(r"receipt-([0-9]{8})\.json\Z")
_LEAF_NAME = re.compile(r"leaf-([0-9]{8})\.json\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
REGISTERED_RESULT = b"true"
REGISTERED_RESULT_SHA256 = sha256_bytes(REGISTERED_RESULT)


class HurstResidualCampaignError(RuntimeError):
    """A campaign artifact or runner invocation failed closed."""


@dataclass(frozen=True)
class HurstResidualCampaignResult:
    mode: str
    plan_sha256: str
    shard_count: int
    summaries: int
    derived_inputs_ready: bool
    verifications: int
    complete: bool
    full_source_range: bool
    certificate_root_sha256: str | None
    final_state: tuple[int, int, int, int] | None
    runner_sha256: str
    source_sha256: str
    upstream_commit: str
    source_residuals_replayed: bool
    execution_attested: bool = False
    lean_atoms_discharged: bool = False

    def as_json(self) -> dict[str, Any]:
        value = asdict(self)
        if self.final_state is not None:
            value["final_state"] = list(self.final_state)
        return value


def _plain_int(value: object, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HurstResidualCampaignError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise HurstResidualCampaignError(f"{name} must be at least {minimum}")
    return value


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise HurstResidualCampaignError(
            f"{name} must be a lowercase 64-digit SHA-256 digest"
        )
    return value


def _vector(value: object, name: str) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise HurstResidualCampaignError(f"{name} must be a four-integer array")
    result = tuple(_plain_int(item, f"{name}[{index}]") for index, item in enumerate(value))
    return result  # type: ignore[return-value]


def _load_receipt_bytes(raw: bytes, label: str) -> dict[str, Any]:
    if len(raw) > MAX_RECEIPT_BYTES:
        raise HurstResidualCampaignError("runner receipt exceeds the byte limit")
    try:
        return load_decimal_json_bytes(raw, label=label)
    except EvidenceError as exc:
        raise HurstResidualCampaignError(str(exc)) from exc


def _load_control(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except CampaignIOError as exc:
        raise HurstResidualCampaignError(str(exc)) from exc
    if not isinstance(value, dict):
        raise HurstResidualCampaignError(f"control artifact must be an object: {path}")
    return value


def _read_bounded(path: Path, maximum: int, label: str) -> bytes:
    try:
        return read_bytes_once(path, limit=maximum)
    except CampaignIOError as exc:
        raise HurstResidualCampaignError(f"cannot read {label}: {exc}") from exc


def _validate_upstream_manifest(raw: bytes) -> dict[str, Any]:
    try:
        value = parse_json_bytes(raw, label="upstream manifest")
    except CampaignIOError as exc:
        raise HurstResidualCampaignError("upstream manifest is not valid JSON") from exc
    if not isinstance(value, dict):
        raise HurstResidualCampaignError("upstream manifest must be an object")
    if value.get("kind") != "sparkinterval.pinned_upstream_source.v1":
        raise HurstResidualCampaignError("unexpected upstream manifest kind")
    if value.get("commit") != UPSTREAM_COMMIT:
        raise HurstResidualCampaignError("upstream manifest has the wrong pinned commit")
    files = value.get("files")
    if not isinstance(files, list) or not files:
        raise HurstResidualCampaignError("upstream manifest has no pinned source files")
    for index, item in enumerate(files):
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "size_bytes"}:
            raise HurstResidualCampaignError(
                f"upstream manifest file {index} has the wrong fields"
            )
        if not isinstance(item["path"], str) or not item["path"]:
            raise HurstResidualCampaignError("upstream manifest path is malformed")
        _digest(item["sha256"], "upstream file digest")
        _plain_int(item["size_bytes"], "upstream file size", minimum=1)
    return value


def _plan_algorithm_identity(
    *, runner_sha256: str, source_sha256: str, upstream_manifest_sha256: str
) -> str:
    return (
        f"{CAMPAIGN_ALGORITHM};runner={runner_sha256};source={source_sha256};"
        f"upstream={UPSTREAM_COMMIT};manifest={upstream_manifest_sha256}"
    )


def create_plan(
    *,
    domain_upper_exclusive: int = SOURCE_UPPER_EXCLUSIVE,
    shard_span: int = DEFAULT_SHARD_SPAN,
    runner_sha256: str,
    source_sha256: str,
    upstream_manifest_sha256: str,
    allow_bounded_test: bool = False,
) -> FixedShardPlan:
    """Create the literal half-open plan, refusing an implicit sample."""

    upper = _plain_int(domain_upper_exclusive, "domain upper", minimum=2)
    span = _plain_int(shard_span, "shard span", minimum=1)
    if upper > SOURCE_UPPER_EXCLUSIVE:
        raise HurstResidualCampaignError("campaign exceeds the source endpoint")
    full = upper == SOURCE_UPPER_EXCLUSIVE
    if not full and not allow_bounded_test:
        raise HurstResidualCampaignError(
            "a shortened domain requires explicit allow_bounded_test=True"
        )
    if full and span > MAX_FULL_SOURCE_SHARD_SPAN:
        raise HurstResidualCampaignError(
            "full-source shard span is too large for checkpointed recovery"
        )
    ranges: list[tuple[int, int]] = []
    lower = SOURCE_LOWER
    while lower < upper:
        following = min(upper, lower + span)
        ranges.append((lower, following))
        lower = following
    try:
        return FixedShardPlan.from_ranges(
            algorithm=_plan_algorithm_identity(
                runner_sha256=runner_sha256,
                source_sha256=source_sha256,
                upstream_manifest_sha256=upstream_manifest_sha256,
            ),
            state_dimension=4,
            ranges=ranges,
        )
    except AffineGuardCertificateError as exc:
        raise HurstResidualCampaignError(str(exc)) from exc


def _expected_config(
    *,
    plan: FixedShardPlan,
    shard_span: int,
    segment_size: int,
    runner_sha256: str,
    runner_size: int,
    source_sha256: str,
    source_size: int,
    upstream_manifest_sha256: str,
) -> dict[str, Any]:
    full = plan.domain_upper == SOURCE_UPPER_EXCLUSIVE
    return {
        "schema": CAMPAIGN_SCHEMA,
        "algorithm": CAMPAIGN_ALGORITHM,
        "runner_algorithm": RUNNER_ALGORITHM,
        "classification": "external_finite_computation_not_attestation_or_lean_proof",
        "mode": "full_source" if full else "bounded_test",
        "domain_lower": plan.domain_lower,
        "domain_upper_exclusive": plan.domain_upper,
        "shard_span": shard_span,
        "shard_count": len(plan.shards),
        "segment_size": segment_size,
        "state_components": list(STATE_COMPONENTS),
        "atom_profiles": list(ATOM_PROFILES),
        "plan_sha256": plan.plan_sha256,
        "captured_runner_sha256": runner_sha256,
        "captured_runner_size": runner_size,
        "captured_source_sha256": source_sha256,
        "captured_source_size": source_size,
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_manifest_sha256": upstream_manifest_sha256,
    }


def initialize_campaign(
    *,
    runner: Path,
    runner_source: Path,
    upstream_manifest: Path,
    output_directory: Path,
    shard_span: int = DEFAULT_SHARD_SPAN,
    segment_size: int = DEFAULT_SEGMENT_SIZE,
    domain_upper_exclusive: int = SOURCE_UPPER_EXCLUSIVE,
    allow_bounded_test: bool = False,
) -> HurstResidualCampaignResult:
    """Capture immutable identities and write the fixed campaign plan."""

    span = _plain_int(shard_span, "shard span", minimum=1)
    segment = _plain_int(segment_size, "segment size", minimum=MIN_SEGMENT_SIZE)
    if segment > MAX_SEGMENT_SIZE:
        raise HurstResidualCampaignError("segment size exceeds the runner limit")
    runner_raw = _read_bounded(runner, MAX_RUNNER_BYTES, "runner")
    source_raw = _read_bounded(runner_source, MAX_SOURCE_BYTES, "runner source")
    upstream_raw = _read_bounded(upstream_manifest, MAX_SOURCE_BYTES, "upstream manifest")
    _validate_upstream_manifest(upstream_raw)
    runner_sha = sha256_bytes(runner_raw)
    source_sha = sha256_bytes(source_raw)
    upstream_sha = sha256_bytes(upstream_raw)
    plan = create_plan(
        domain_upper_exclusive=domain_upper_exclusive,
        shard_span=span,
        runner_sha256=runner_sha,
        source_sha256=source_sha,
        upstream_manifest_sha256=upstream_sha,
        allow_bounded_test=allow_bounded_test,
    )
    config = _expected_config(
        plan=plan,
        shard_span=span,
        segment_size=segment,
        runner_sha256=runner_sha,
        runner_size=len(runner_raw),
        source_sha256=source_sha,
        source_size=len(source_raw),
        upstream_manifest_sha256=upstream_sha,
    )
    if output_directory.exists() and not output_directory.is_dir():
        raise HurstResidualCampaignError("campaign output path is not a directory")
    output_directory.mkdir(parents=True, exist_ok=True)
    try:
        with advisory_lock(output_directory / ".hurst-residual-campaign.lock"):
            captures = (
                (CAPTURED_RUNNER_NAME, runner_raw),
                (CAPTURED_SOURCE_NAME, source_raw),
                (CAPTURED_UPSTREAM_NAME, upstream_raw),
            )
            any_existing = any((output_directory / name).exists() for name, _ in captures)
            any_existing = any_existing or (output_directory / CONFIG_NAME).exists()
            any_existing = any_existing or (output_directory / PLAN_NAME).exists()
            if any_existing:
                expected_paths = [output_directory / name for name, _ in captures]
                expected_paths += [output_directory / CONFIG_NAME, output_directory / PLAN_NAME]
                if not all(path.is_file() for path in expected_paths):
                    raise HurstResidualCampaignError("campaign initialization is partial")
                for name, raw in captures:
                    if _read_bounded(output_directory / name, max(len(raw), 1), name) != raw:
                        raise HurstResidualCampaignError(f"captured identity changed: {name}")
                if _load_control(output_directory / CONFIG_NAME) != config:
                    raise HurstResidualCampaignError("resume configuration changed")
                if _load_control(output_directory / PLAN_NAME) != plan.to_dict():
                    raise HurstResidualCampaignError("fixed shard plan changed")
            else:
                atomic_write_bytes(output_directory / CAPTURED_RUNNER_NAME, runner_raw)
                atomic_write_bytes(output_directory / CAPTURED_SOURCE_NAME, source_raw)
                atomic_write_bytes(output_directory / CAPTURED_UPSTREAM_NAME, upstream_raw)
                write_immutable_json(output_directory / PLAN_NAME, plan.to_dict())
                write_immutable_json(output_directory / CONFIG_NAME, config)
            try:
                (output_directory / CAPTURED_RUNNER_NAME).chmod(
                    stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP
                )
            except OSError as exc:
                raise HurstResidualCampaignError(
                    f"cannot make captured runner executable: {exc}"
                ) from exc
            return _verify_campaign_unlocked(output_directory)
    except CampaignIOError as exc:
        raise HurstResidualCampaignError(str(exc)) from exc


def _validate_loaded_setup(output_directory: Path) -> tuple[dict[str, Any], FixedShardPlan]:
    config = _load_control(output_directory / CONFIG_NAME)
    expected_fields = set(
        _expected_config(
            plan=FixedShardPlan.from_ranges(
                algorithm="placeholder", state_dimension=4, ranges=((1, 2),)
            ),
            shard_span=1,
            segment_size=1,
            runner_sha256="0" * 64,
            runner_size=1,
            source_sha256="0" * 64,
            source_size=1,
            upstream_manifest_sha256="0" * 64,
        )
    )
    if set(config) != expected_fields:
        raise HurstResidualCampaignError("campaign config fields changed")
    if config.get("schema") != CAMPAIGN_SCHEMA or config.get("algorithm") != CAMPAIGN_ALGORITHM:
        raise HurstResidualCampaignError("unsupported campaign configuration")
    if config.get("runner_algorithm") != RUNNER_ALGORITHM:
        raise HurstResidualCampaignError("runner algorithm changed")
    if config.get("classification") != "external_finite_computation_not_attestation_or_lean_proof":
        raise HurstResidualCampaignError("unsafe campaign classification")
    if config.get("state_components") != list(STATE_COMPONENTS):
        raise HurstResidualCampaignError("state component order changed")
    if config.get("atom_profiles") != list(ATOM_PROFILES):
        raise HurstResidualCampaignError("atom profile set changed")
    if config.get("upstream_commit") != UPSTREAM_COMMIT:
        raise HurstResidualCampaignError("campaign upstream commit changed")
    for name in (
        "plan_sha256",
        "captured_runner_sha256",
        "captured_source_sha256",
        "upstream_manifest_sha256",
    ):
        _digest(config.get(name), name)
    for name in (
        "domain_lower",
        "domain_upper_exclusive",
        "shard_span",
        "shard_count",
        "segment_size",
        "captured_runner_size",
        "captured_source_size",
    ):
        _plain_int(config.get(name), name, minimum=1)
    mode = config.get("mode")
    if mode not in ("full_source", "bounded_test"):
        raise HurstResidualCampaignError("unknown campaign mode")
    if config["domain_lower"] != SOURCE_LOWER or not (
        2 <= config["domain_upper_exclusive"] <= SOURCE_UPPER_EXCLUSIVE
    ):
        raise HurstResidualCampaignError("campaign domain is invalid")
    full = config["domain_upper_exclusive"] == SOURCE_UPPER_EXCLUSIVE
    if (mode == "full_source") != full:
        raise HurstResidualCampaignError("campaign mode mislabels its domain")
    if full and config["shard_span"] > MAX_FULL_SOURCE_SHARD_SPAN:
        raise HurstResidualCampaignError("full-source checkpoint span is too large")
    if not MIN_SEGMENT_SIZE <= config["segment_size"] <= MAX_SEGMENT_SIZE:
        raise HurstResidualCampaignError("campaign segment size exceeds runner limits")

    try:
        plan = FixedShardPlan.from_dict(_load_control(output_directory / PLAN_NAME))
    except AffineGuardCertificateError as exc:
        raise HurstResidualCampaignError(f"invalid fixed plan: {exc}") from exc
    if plan.plan_sha256 != config["plan_sha256"]:
        raise HurstResidualCampaignError("plan digest differs from configuration")
    if (plan.domain_lower, plan.domain_upper, len(plan.shards)) != (
        config["domain_lower"],
        config["domain_upper_exclusive"],
        config["shard_count"],
    ):
        raise HurstResidualCampaignError("plan domain/count differs from configuration")
    runner_path = output_directory / CAPTURED_RUNNER_NAME
    source_path = output_directory / CAPTURED_SOURCE_NAME
    upstream_path = output_directory / CAPTURED_UPSTREAM_NAME
    for path, digest_name, size_name, maximum in (
        (runner_path, "captured_runner_sha256", "captured_runner_size", MAX_RUNNER_BYTES),
        (source_path, "captured_source_sha256", "captured_source_size", MAX_SOURCE_BYTES),
    ):
        try:
            digest, size = hash_file_once(path, limit=maximum)
        except CampaignIOError as exc:
            raise HurstResidualCampaignError(str(exc)) from exc
        if (digest, size) != (config[digest_name], config[size_name]):
            raise HurstResidualCampaignError(f"captured file identity changed: {path.name}")
    upstream_raw = _read_bounded(upstream_path, MAX_SOURCE_BYTES, "upstream manifest")
    _validate_upstream_manifest(upstream_raw)
    if sha256_bytes(upstream_raw) != config["upstream_manifest_sha256"]:
        raise HurstResidualCampaignError("captured upstream manifest identity changed")
    expected_identity = _plan_algorithm_identity(
        runner_sha256=config["captured_runner_sha256"],
        source_sha256=config["captured_source_sha256"],
        upstream_manifest_sha256=config["upstream_manifest_sha256"],
    )
    if plan.algorithm != expected_identity or plan.state_dimension != 4:
        raise HurstResidualCampaignError("plan is not bound to the captured identities")
    return config, plan


def _receipt_paths(output_directory: Path, phase: str) -> dict[int, Path]:
    directory = output_directory / phase
    if not directory.exists():
        return {}
    if not directory.is_dir():
        raise HurstResidualCampaignError(f"{phase} receipt path is not a directory")
    indexed: dict[int, Path] = {}
    for path in directory.glob("receipt-*.json"):
        match = _RECEIPT_NAME.fullmatch(path.name)
        if match is None or not path.is_file():
            raise HurstResidualCampaignError(f"malformed {phase} receipt path {path.name!r}")
        index = int(match.group(1))
        if index in indexed:
            raise HurstResidualCampaignError(f"duplicate {phase} receipt index {index}")
        indexed[index] = path
    return indexed


def validate_runner_receipt(
    report: Mapping[str, Any],
    *,
    phase: str,
    shard_lower: int,
    shard_upper: int,
    segment_size: int,
    expected_incoming: Sequence[int] | None = None,
) -> tuple[int, int, int, int]:
    """Strictly check a summary or verify receipt against one plan leaf."""

    if not isinstance(report, Mapping) or set(report) != RECEIPT_FIELDS:
        actual = set(report) if isinstance(report, Mapping) else set()
        raise HurstResidualCampaignError(
            "runner receipt fields changed; "
            f"missing={sorted(RECEIPT_FIELDS - actual)}, "
            f"extra={sorted(actual - RECEIPT_FIELDS)}"
        )
    if phase not in ("summary", "verify") or report.get("mode") != phase:
        raise HurstResidualCampaignError("runner receipt has the wrong phase")
    if report.get("algorithm") != RUNNER_ALGORITHM:
        raise HurstResidualCampaignError("runner algorithm changed")
    if report.get("classification") != RUNNER_CLASSIFICATION:
        raise HurstResidualCampaignError("runner classification changed")
    if report.get("upstream_commit") != UPSTREAM_COMMIT:
        raise HurstResidualCampaignError("runner used the wrong upstream commit")
    if (
        report.get("lower"),
        report.get("upper_exclusive"),
        report.get("work_count"),
        report.get("segment_size"),
    ) != (shard_lower, shard_upper, shard_upper - shard_lower, segment_size):
        raise HurstResidualCampaignError("runner receipt range/config differs from request")
    expected_segments = (shard_upper - shard_lower + segment_size - 1) // segment_size
    if report.get("segments") != expected_segments:
        raise HurstResidualCampaignError("runner receipt has the wrong segment count")
    if report.get("row_encoding") != "mu-plus-one-block-sha256-v1":
        raise HurstResidualCampaignError("runner row encoding changed")
    if (
        report.get("squarefree_threshold_endpoint_policy")
        != "inclusive-value-and-right-limit-v2"
    ):
        raise HurstResidualCampaignError(
            "runner squarefree threshold endpoint policy changed"
        )
    if report.get("reduction_block_rows") != 1_048_576:
        raise HurstResidualCampaignError("runner reduction block size changed")
    _digest(report.get("row_sha256"), "row_sha256")
    if report.get("state_components") != list(STATE_COMPONENTS):
        raise HurstResidualCampaignError("runner state component order changed")
    delta = _vector(report.get("delta"), "delta")
    work_count = shard_upper - shard_lower
    if not -work_count <= delta[0] <= work_count:
        raise HurstResidualCampaignError("Mertens delta exceeds its row count")
    if not 0 <= delta[1] <= work_count:
        raise HurstResidualCampaignError("squarefree delta exceeds its row count")
    signed_128_lower = -(1 << 127)
    signed_128_upper = (1 << 127) - 1
    if any(not signed_128_lower <= coordinate <= signed_128_upper for coordinate in delta):
        raise HurstResidualCampaignError("runner delta exceeds signed 128-bit range")
    if delta[2] > delta[3]:
        raise HurstResidualCampaignError("little-Mertens directed delta is reversed")
    fallbacks = report.get("exact_fallbacks")
    if not isinstance(fallbacks, dict) or set(fallbacks) != EXACT_FALLBACK_FIELDS:
        raise HurstResidualCampaignError("runner fallback counters changed")
    for name, value in fallbacks.items():
        _plain_int(value, f"fallback counter {name}", minimum=0)
    if phase == "summary" and any(fallbacks.values()):
        raise HurstResidualCampaignError("summary pass unexpectedly reports verification fallbacks")
    elapsed = report.get("elapsed_seconds")
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, Decimal)) or elapsed < 0:
        raise HurstResidualCampaignError("elapsed_seconds must be nonnegative")
    if report.get("accepted") is not True:
        raise HurstResidualCampaignError("runner did not accept the shard")
    if report.get("execution_attested") is not False or report.get("lean_atom_discharged") is not False:
        raise HurstResidualCampaignError("runner made an unsafe trust-boundary claim")
    guards = report.get("guards")
    if phase == "summary":
        if guards != {}:
            raise HurstResidualCampaignError("summary receipt must not claim incoming guards")
    else:
        if expected_incoming is None:
            raise HurstResidualCampaignError("verify receipt needs a root-derived input")
        incoming = tuple(expected_incoming)
        if len(incoming) != 4 or any(type(value) is not int for value in incoming):
            raise HurstResidualCampaignError("derived input must have four integer coordinates")
        if not isinstance(guards, dict) or set(guards) != set(ATOM_PROFILES):
            raise HurstResidualCampaignError("verify receipt atom guards changed")
        for atom in ATOM_PROFILES:
            guard = guards[atom]
            if not isinstance(guard, dict) or set(guard) != {"lower", "upper", "witnesses"}:
                raise HurstResidualCampaignError(f"verify guard for {atom} is malformed")
            if _vector(guard["lower"], f"{atom} lower guard") != incoming or (
                _vector(guard["upper"], f"{atom} upper guard") != incoming
            ):
                raise HurstResidualCampaignError(
                    f"verify guard for {atom} differs from the root-derived input"
                )
            if guard["witnesses"] != []:
                raise HurstResidualCampaignError("singleton verify guards must not carry witnesses")
    return delta


def _load_phase_receipts(
    output_directory: Path,
    phase: str,
    config: Mapping[str, Any],
    plan: FixedShardPlan,
    derived: Mapping[str, Any] | None = None,
) -> dict[int, tuple[dict[str, Any], bytes]]:
    result: dict[int, tuple[dict[str, Any], bytes]] = {}
    for index, path in _receipt_paths(output_directory, phase).items():
        if index >= len(plan.shards):
            raise HurstResidualCampaignError(f"{phase} receipt index is outside the plan")
        raw = _read_bounded(path, MAX_RECEIPT_BYTES, f"{phase} receipt")
        report = _load_receipt_bytes(raw, str(path))
        shard = plan.shards[index]
        incoming = None
        if phase == "verify":
            if derived is None:
                raise HurstResidualCampaignError("verify receipts exist before derived inputs")
            entries = derived.get("entries")
            if not isinstance(entries, list) or index >= len(entries):
                raise HurstResidualCampaignError("derived input table is malformed")
            entry = entries[index]
            if not isinstance(entry, dict):
                raise HurstResidualCampaignError("derived input entry is malformed")
            incoming = _vector(entry.get("incoming"), "derived incoming")
        validate_runner_receipt(
            report,
            phase=phase,
            shard_lower=shard.lower,
            shard_upper=shard.upper,
            segment_size=config["segment_size"],
            expected_incoming=incoming,
        )
        result[index] = (report, raw)
    return result


def _require_complete_indices(
    receipts: Mapping[int, object], plan: FixedShardPlan, phase: str
) -> None:
    wanted = set(range(len(plan.shards)))
    actual = set(receipts)
    if actual != wanted:
        missing = sorted(wanted - actual)
        extra = sorted(actual - wanted)
        preview = missing[:8]
        raise HurstResidualCampaignError(
            f"{phase} receipts are incomplete (missing={preview}"
            f"{'...' if len(missing) > len(preview) else ''}, extra={extra})"
        )


def _derive_payload(
    config: Mapping[str, Any],
    plan: FixedShardPlan,
    summaries: Mapping[int, tuple[dict[str, Any], bytes]],
) -> dict[str, Any]:
    _require_complete_indices(summaries, plan, "summary")
    current = (0, 0, 0, 0)
    entries: list[dict[str, Any]] = []
    for index, shard in enumerate(plan.shards):
        report, raw = summaries[index]
        delta = _vector(report["delta"], "summary delta")
        outgoing = tuple(left + right for left, right in zip(current, delta, strict=True))
        entries.append(
            {
                "index": index,
                "lower": shard.lower,
                "upper": shard.upper,
                "summary_receipt_sha256": sha256_bytes(raw),
                "row_sha256": report["row_sha256"],
                "delta": list(delta),
                "incoming": list(current),
                "outgoing": list(outgoing),
            }
        )
        current = outgoing
    config_sha = canonical_sha256(dict(config))
    content = {
        "schema": DERIVED_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "config_sha256": config_sha,
        "root_state": [0, 0, 0, 0],
        "entries": entries,
        "final_state": list(current),
    }
    content["summary_set_sha256"] = canonical_sha256(content)
    return content


def reduce_summaries(output_directory: Path) -> dict[str, Any]:
    """Derive all phase-two inputs, but only from a complete summary set."""

    try:
        with advisory_lock(output_directory / ".hurst-residual-campaign.lock"):
            config, plan = _validate_loaded_setup(output_directory)
            summaries = _load_phase_receipts(output_directory, "summary", config, plan)
            derived = _derive_payload(config, plan, summaries)
            write_immutable_json(output_directory / DERIVED_NAME, derived)
            return derived
    except (CampaignIOError, AffineGuardCertificateError) as exc:
        raise HurstResidualCampaignError(str(exc)) from exc


def _load_and_check_derived(
    output_directory: Path,
    config: Mapping[str, Any],
    plan: FixedShardPlan,
    summaries: Mapping[int, tuple[dict[str, Any], bytes]],
) -> dict[str, Any]:
    path = output_directory / DERIVED_NAME
    if not path.is_file():
        raise HurstResidualCampaignError("derived inputs are absent; finish phase 1 and reduce")
    actual = _load_control(path)
    expected = _derive_payload(config, plan, summaries)
    if actual != expected:
        raise HurstResidualCampaignError("derived inputs disagree with the summary receipts")
    return actual


def _command_for_loaded_shard(
    output_directory: Path,
    *,
    phase: str,
    index: int,
    config: Mapping[str, Any],
    plan: FixedShardPlan,
    derived: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    """Construct one argv from a setup snapshot already checked under lock."""

    shard = plan.shards[index]
    command = [
        str((output_directory / CAPTURED_RUNNER_NAME).resolve()),
        "--lower",
        str(shard.lower),
        "--upper",
        str(shard.upper - 1),
        "--segment-size",
        str(config["segment_size"]),
        "--mode",
        phase,
    ]
    if phase == "verify":
        if derived is None:
            raise HurstResidualCampaignError(
                "verify command requires derived incoming states"
            )
        entry = derived["entries"][index]
        incoming = _vector(entry["incoming"], "derived incoming")
        for flag, value in zip(
            (
                "--incoming-mertens",
                "--incoming-squarefree",
                "--incoming-little-lower",
                "--incoming-little-upper",
            ),
            incoming,
            strict=True,
        ):
            command.extend((flag, str(value)))
    return tuple(command)


def command_for_shard(
    output_directory: Path, *, phase: str, shard_index: int
) -> tuple[str, ...]:
    """Return an argv tuple suitable for a local or cluster shard worker."""

    config, plan = _validate_loaded_setup(output_directory)
    index = _plain_int(shard_index, "shard index", minimum=0)
    if index >= len(plan.shards):
        raise HurstResidualCampaignError("shard index is outside the fixed plan")
    if phase not in ("summary", "verify"):
        raise HurstResidualCampaignError("phase must be summary or verify")
    derived = None
    if phase == "verify":
        summaries = _load_phase_receipts(
            output_directory, "summary", config, plan
        )
        derived = _load_and_check_derived(
            output_directory, config, plan, summaries
        )
    return _command_for_loaded_shard(
        output_directory,
        phase=phase,
        index=index,
        config=config,
        plan=plan,
        derived=derived,
    )


def grouped_shard_indices(
    output_directory: Path, *, group_index: int, group_count: int
) -> tuple[int, ...]:
    """Return one deterministic disjoint strided group of fixed-plan leaves.

    Grouping reduces scheduler, attestation, and HSM overhead without changing
    the 10,000-leaf mathematical plan or receipt granularity.  The union of
    all groups is the complete plan, and no two groups share an index.
    """

    _, plan = _validate_loaded_setup(output_directory)
    count = _plain_int(group_count, "worker group count", minimum=1)
    index = _plain_int(group_index, "worker group index", minimum=0)
    if count > len(plan.shards):
        raise HurstResidualCampaignError(
            "worker group count cannot exceed the fixed-plan shard count"
        )
    if index >= count:
        raise HurstResidualCampaignError(
            "worker group index is outside the group count"
        )
    return tuple(range(index, len(plan.shards), count))


def _ingest_receipt_unlocked(
    output_directory: Path,
    *,
    phase: str,
    shard_index: int,
    raw: bytes,
) -> None:
    config, plan = _validate_loaded_setup(output_directory)
    index = _plain_int(shard_index, "shard index", minimum=0)
    if index >= len(plan.shards):
        raise HurstResidualCampaignError("shard index is outside the fixed plan")
    if phase not in ("summary", "verify"):
        raise HurstResidualCampaignError("phase must be summary or verify")
    summaries = _load_phase_receipts(output_directory, "summary", config, plan)
    derived = None
    if phase == "verify":
        derived = _load_and_check_derived(output_directory, config, plan, summaries)
    _validate_and_retain_receipt(
        output_directory,
        phase=phase,
        index=index,
        raw=raw,
        config=config,
        plan=plan,
        summaries=summaries,
        derived=derived,
    )


def _validate_and_retain_receipt(
    output_directory: Path,
    *,
    phase: str,
    index: int,
    raw: bytes,
    config: Mapping[str, Any],
    plan: FixedShardPlan,
    summaries: Mapping[int, tuple[dict[str, Any], bytes]],
    derived: Mapping[str, Any] | None,
) -> None:
    """Validate one leaf against an already authenticated phase snapshot."""

    expected_incoming = None
    if phase == "verify":
        if derived is None:
            raise HurstResidualCampaignError(
                "verify receipt requires derived incoming states"
            )
        expected_incoming = _vector(
            derived["entries"][index]["incoming"], "derived incoming"
        )
    report = _load_receipt_bytes(raw, f"incoming {phase} receipt {index}")
    shard = plan.shards[index]
    delta = validate_runner_receipt(
        report,
        phase=phase,
        shard_lower=shard.lower,
        shard_upper=shard.upper,
        segment_size=config["segment_size"],
        expected_incoming=expected_incoming,
    )
    if phase == "verify":
        summary_report = summaries[index][0]
        if delta != _vector(summary_report["delta"], "summary delta"):
            raise HurstResidualCampaignError("verify delta differs from summary delta")
        if report["row_sha256"] != summary_report["row_sha256"]:
            raise HurstResidualCampaignError("verify row SHA differs from summary row SHA")
    directory = output_directory / phase
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"receipt-{index:08d}.json"
    if destination.exists():
        existing = _read_bounded(destination, MAX_RECEIPT_BYTES, "retained receipt")
        if existing != raw:
            raise HurstResidualCampaignError("refusing to replace a retained receipt")
        return
    try:
        atomic_write_bytes(destination, raw)
    except CampaignIOError as exc:
        raise HurstResidualCampaignError(str(exc)) from exc


def _execute_shard(
    command: tuple[str, ...],
    *,
    timeout_seconds: int | None,
    runner_threads: int | None,
    runner_places: tuple[int, ...] | None,
    cancel_event: threading.Event,
) -> bytes:
    environment = None
    if runner_threads is not None or runner_places is not None:
        environment = os.environ.copy()
        environment["OMP_DYNAMIC"] = "FALSE"
        if runner_threads is not None:
            environment["OMP_NUM_THREADS"] = str(runner_threads)
        if runner_places is None:
            environment.setdefault("OMP_PROC_BIND", "spread")
        else:
            environment["OMP_PLACES"] = ",".join(
                f"{{{cpu}}}" for cpu in runner_places
            )
            environment["OMP_PROC_BIND"] = "close"
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        )
    except OSError as exc:
        raise HurstResidualCampaignError(
            f"runner invocation failed: {exc}"
        ) from exc

    stdout = bytearray()
    stderr = bytearray()
    deadline = (
        None
        if timeout_seconds is None
        else time.monotonic() + timeout_seconds
    )
    abort_reason: str | None = None
    try:
        assert process.stdout is not None
        assert process.stderr is not None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                if cancel_event.is_set():
                    abort_reason = (
                        "runner cancelled after another shard failed"
                    )
                    break
                timeout = 0.25
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        abort_reason = (
                            f"runner invocation timed out after "
                            f"{timeout_seconds} seconds"
                        )
                        break
                    timeout = min(timeout, remaining)
                events = selector.select(timeout)
                if not events:
                    continue
                for key, _ in events:
                    chunk = os.read(key.fd, 1 << 16)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    if key.data == "stdout":
                        stdout.extend(chunk)
                        if len(stdout) > MAX_RECEIPT_BYTES:
                            abort_reason = (
                                "runner emitted an oversized receipt"
                            )
                            break
                    elif len(stderr) < 4096:
                        stderr.extend(chunk[: 4096 - len(stderr)])
                if abort_reason is not None:
                    break
    except OSError as exc:
        abort_reason = f"runner output read failed: {exc}"
    finally:
        if abort_reason is not None and process.poll() is None:
            process.kill()
        for stream in (process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
        process.wait()

    if abort_reason is not None:
        raise HurstResidualCampaignError(abort_reason)
    if process.returncode != 0:
        diagnostic = bytes(stderr).decode(
            "utf-8", errors="replace"
        )
        raise HurstResidualCampaignError(
            f"runner returned {process.returncode}: {diagnostic}"
        )
    return bytes(stdout)


def ingest_receipt(
    output_directory: Path,
    *,
    phase: str,
    shard_index: int,
    receipt_path: Path,
) -> HurstResidualCampaignResult:
    """Strictly ingest one externally executed shard receipt."""

    raw = _read_bounded(receipt_path, MAX_RECEIPT_BYTES, "incoming receipt")
    try:
        with advisory_lock(output_directory / ".hurst-residual-campaign.lock"):
            _ingest_receipt_unlocked(
                output_directory, phase=phase, shard_index=shard_index, raw=raw
            )
            return _verify_campaign_unlocked(output_directory)
    except CampaignIOError as exc:
        raise HurstResidualCampaignError(str(exc)) from exc


def run_phase(
    output_directory: Path,
    *,
    phase: str,
    shard_indices: Sequence[int] | None = None,
    max_shards: int | None = None,
    workers: int = DEFAULT_LOCAL_WORKERS,
    runner_threads: int | None = None,
    timeout_seconds: int | None = None,
) -> HurstResidualCampaignResult:
    """Run missing shards with bounded parallel child processes.

    Independent Slurm workers may safely call this function for disjoint shard
    indices.  The lock protects setup validation and final ingestion only.  A
    same-index race either converges on byte-identical receipt bytes or fails
    closed when the runner's nonsemantic timing field makes the bytes differ.

    When more than one child is selected, each child defaults to one OpenMP
    thread.  This avoids multiplying a group-level process count by an
    inherited node-wide ``OMP_NUM_THREADS`` setting.  Callers may instead set
    ``runner_threads`` explicitly; the product is a resource policy, not a
    mathematical parameter or a certificate coarsening.
    """

    worker_count = _plain_int(workers, "workers", minimum=1)
    if runner_threads is not None:
        runner_thread_count = _plain_int(
            runner_threads, "runner threads", minimum=1
        )
    else:
        runner_thread_count = 1 if worker_count > 1 else None
    if max_shards is not None:
        _plain_int(max_shards, "max shards", minimum=1)
    if timeout_seconds is not None:
        _plain_int(timeout_seconds, "timeout seconds", minimum=1)
    try:
        with advisory_lock(output_directory / ".hurst-residual-campaign.lock"):
            config, plan = _validate_loaded_setup(output_directory)
            if phase not in ("summary", "verify"):
                raise HurstResidualCampaignError("phase must be summary or verify")
            if phase == "verify":
                summaries = _load_phase_receipts(output_directory, "summary", config, plan)
                derived = _load_and_check_derived(
                    output_directory, config, plan, summaries
                )
            else:
                summaries = _load_phase_receipts(
                    output_directory, "summary", config, plan
                )
                derived = None
            existing = _receipt_paths(output_directory, phase)
            if shard_indices is None:
                selected = [index for index in range(len(plan.shards)) if index not in existing]
            else:
                selected = []
                seen: set[int] = set()
                for raw_index in shard_indices:
                    index = _plain_int(raw_index, "shard index", minimum=0)
                    if index >= len(plan.shards):
                        raise HurstResidualCampaignError("shard index is outside the fixed plan")
                    if index in seen:
                        raise HurstResidualCampaignError("duplicate requested shard index")
                    seen.add(index)
                    if index not in existing:
                        selected.append(index)
            if max_shards is not None:
                selected = selected[:max_shards]
            commands = {
                index: _command_for_loaded_shard(
                    output_directory,
                    phase=phase,
                    index=index,
                    config=config,
                    plan=plan,
                    derived=derived,
                )
                for index in selected
            }

        if not selected:
            return verify_campaign(output_directory)
        effective_workers = min(worker_count, len(selected))
        worker_places: tuple[tuple[int, ...] | None, ...]
        if runner_thread_count is None:
            worker_places = (None,)
        else:
            try:
                available_cpus = tuple(sorted(os.sched_getaffinity(0)))
            except (AttributeError, OSError) as exc:
                raise HurstResidualCampaignError(
                    "explicit runner threads require CPU-affinity discovery"
                ) from exc
            required_cpus = effective_workers * runner_thread_count
            if required_cpus > len(available_cpus):
                raise HurstResidualCampaignError(
                    "workers times runner threads exceeds the available CPU affinity"
                )
            worker_places = tuple(
                available_cpus[
                    slot * runner_thread_count :
                    (slot + 1) * runner_thread_count
                ]
                for slot in range(effective_workers)
            )

        def submit_one(
            executor: ThreadPoolExecutor, index: int, slot: int
        ) -> Future[bytes]:
            return executor.submit(
                _execute_shard,
                commands[index],
                timeout_seconds=timeout_seconds,
                runner_threads=runner_thread_count,
                runner_places=worker_places[slot],
                cancel_event=cancel_event,
            )

        iterator = iter(selected)
        pending: dict[Future[bytes], tuple[int, int]] = {}
        cancel_event = threading.Event()
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            for slot in range(min(len(selected), effective_workers)):
                index = next(iterator, None)
                if index is None:
                    break
                pending[submit_one(executor, index, slot)] = (index, slot)
            while pending:
                completed, _ = wait(
                    pending, return_when=FIRST_COMPLETED
                )
                for future in completed:
                    index, slot = pending.pop(future)
                    try:
                        raw = future.result()
                        with advisory_lock(
                            output_directory
                            / ".hurst-residual-campaign.lock"
                        ):
                            _validate_and_retain_receipt(
                                output_directory,
                                phase=phase,
                                index=index,
                                raw=raw,
                                config=config,
                                plan=plan,
                                summaries=summaries,
                                derived=derived,
                            )
                    except BaseException:
                        cancel_event.set()
                        for other in pending:
                            other.cancel()
                        raise
                    following = next(iterator, None)
                    if following is not None:
                        pending[submit_one(executor, following, slot)] = (
                            following,
                            slot,
                        )
        return verify_campaign(output_directory)
    except CampaignIOError as exc:
        raise HurstResidualCampaignError(str(exc)) from exc


def _build_leaves(
    plan: FixedShardPlan,
    summaries: Mapping[int, tuple[dict[str, Any], bytes]],
    verifications: Mapping[int, tuple[dict[str, Any], bytes]],
    derived: Mapping[str, Any],
) -> tuple[AffineGuardLeaf, ...]:
    _require_complete_indices(summaries, plan, "summary")
    _require_complete_indices(verifications, plan, "verify")
    leaves: list[AffineGuardLeaf] = []
    for index, shard in enumerate(plan.shards):
        summary = summaries[index][0]
        verification = verifications[index][0]
        delta = _vector(summary["delta"], "summary delta")
        if _vector(verification["delta"], "verify delta") != delta:
            raise HurstResidualCampaignError("verify delta differs from summary delta")
        if verification["row_sha256"] != summary["row_sha256"]:
            raise HurstResidualCampaignError("verify row SHA differs from summary row SHA")
        incoming = _vector(derived["entries"][index]["incoming"], "derived incoming")
        transition = AffineGuardTransition(delta, incoming, incoming)
        # The singleton is a checked shard-boundary guard, represented in the
        # generic format by a synthetic boundary witness at the first row.
        witnesses = tuple(
            TightGuardWitness(row_index=shard.lower, prefix_delta=0, row_guard=value)
            for value in incoming
        )
        leaves.append(
            make_affine_guard_leaf(
                plan=plan,
                shard_index=index,
                row_root_sha256=summary["row_sha256"],
                transition=transition,
                lower_tight_witnesses=witnesses,
                upper_tight_witnesses=witnesses,
                exception_root_sha256=EMPTY_EXCEPTION_ROOT_SHA256,
            )
        )
    return tuple(leaves)


def _final_payload(
    config: Mapping[str, Any],
    plan: FixedShardPlan,
    derived: Mapping[str, Any],
    leaves: Sequence[AffineGuardLeaf],
    verifications: Mapping[int, tuple[dict[str, Any], bytes]],
) -> dict[str, Any]:
    try:
        checked = verify_affine_guard_certificate(
            plan=plan, root_state=(0, 0, 0, 0), leaves=leaves
        )
    except AffineGuardCertificateError as exc:
        raise HurstResidualCampaignError(f"affine certificate failed: {exc}") from exc
    full = config["mode"] == "full_source"
    verification_index = {
        "schema": "sparkinterval.tg.hurst-residual-verification-set.v1",
        "plan_sha256": plan.plan_sha256,
        "entries": [
            {
                "index": index,
                "receipt_sha256": sha256_bytes(verifications[index][1]),
                "row_sha256": verifications[index][0]["row_sha256"],
                "delta": verifications[index][0]["delta"],
                "incoming": derived["entries"][index]["incoming"],
            }
            for index in range(len(plan.shards))
        ],
    }
    return {
        "schema": FINAL_SCHEMA,
        "classification": "plan_bound_external_finite_computation_not_attestation_or_lean_proof",
        "certificate_scope": "one_common_certificate_for_all_four_atom_profiles",
        "guard_encoding": "root_derived_singleton_shard_boundary_v1",
        "atom_profiles": list(ATOM_PROFILES),
        "plan_sha256": plan.plan_sha256,
        "config_sha256": canonical_sha256(dict(config)),
        "runner_sha256": config["captured_runner_sha256"],
        "source_sha256": config["captured_source_sha256"],
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_manifest_sha256": config["upstream_manifest_sha256"],
        "summary_set_sha256": derived["summary_set_sha256"],
        "verification_set_sha256": canonical_sha256(verification_index),
        "row_replay_matches_summary": True,
        "singleton_guards_match_root_derived_inputs": True,
        "full_source_range": full,
        "source_residuals_replayed": full,
        "execution_attested": False,
        "lean_atoms_discharged": False,
        "generic_affine_certificate": checked.to_dict(),
    }


def finalize_campaign(output_directory: Path) -> HurstResidualCampaignResult:
    """Reject incomplete coverage and materialize the plan-bound Merkle leaves."""

    try:
        with advisory_lock(output_directory / ".hurst-residual-campaign.lock"):
            config, plan = _validate_loaded_setup(output_directory)
            summaries = _load_phase_receipts(output_directory, "summary", config, plan)
            derived = _load_and_check_derived(output_directory, config, plan, summaries)
            verifications = _load_phase_receipts(
                output_directory, "verify", config, plan, derived
            )
            leaves = _build_leaves(plan, summaries, verifications, derived)
            leaf_directory = output_directory / LEAF_DIRECTORY
            leaf_directory.mkdir(parents=True, exist_ok=True)
            existing_leaf_paths = list(leaf_directory.glob("leaf-*.json"))
            for path in existing_leaf_paths:
                match = _LEAF_NAME.fullmatch(path.name)
                if match is None or int(match.group(1)) >= len(leaves):
                    raise HurstResidualCampaignError(f"unexpected affine leaf {path.name}")
            for index, leaf in enumerate(leaves):
                write_immutable_json(
                    leaf_directory / f"leaf-{index:08d}.json", leaf.to_dict()
                )
            payload = _final_payload(config, plan, derived, leaves, verifications)
            write_immutable_json(output_directory / FINAL_NAME, payload)
            return _verify_campaign_unlocked(output_directory)
    except (CampaignIOError, AffineGuardCertificateError) as exc:
        raise HurstResidualCampaignError(str(exc)) from exc


def _verify_final(
    output_directory: Path,
    config: Mapping[str, Any],
    plan: FixedShardPlan,
    summaries: Mapping[int, tuple[dict[str, Any], bytes]],
    verifications: Mapping[int, tuple[dict[str, Any], bytes]],
    derived: Mapping[str, Any],
) -> tuple[str, tuple[int, int, int, int]]:
    leaves = _build_leaves(plan, summaries, verifications, derived)
    leaf_directory = output_directory / LEAF_DIRECTORY
    paths = {}
    if leaf_directory.is_dir():
        for path in leaf_directory.glob("leaf-*.json"):
            match = _LEAF_NAME.fullmatch(path.name)
            if match is None:
                raise HurstResidualCampaignError(f"malformed affine leaf {path.name}")
            paths[int(match.group(1))] = path
    if set(paths) != set(range(len(leaves))):
        raise HurstResidualCampaignError("affine leaf files are missing or duplicated")
    for index, expected in enumerate(leaves):
        try:
            actual = AffineGuardLeaf.from_dict(_load_control(paths[index]))
        except AffineGuardCertificateError as exc:
            raise HurstResidualCampaignError(f"malformed affine leaf {index}: {exc}") from exc
        if actual != expected:
            raise HurstResidualCampaignError(f"affine leaf {index} differs from replay")
    expected_payload = _final_payload(
        config, plan, derived, leaves, verifications
    )
    if _load_control(output_directory / FINAL_NAME) != expected_payload:
        raise HurstResidualCampaignError("final certificate differs from replayed receipts")
    generic = expected_payload["generic_affine_certificate"]
    root = _digest(generic["certificate_root_sha256"], "certificate root")
    final_state = _vector(generic["final_state"], "final state")
    return root, final_state


def _verify_campaign_unlocked(output_directory: Path) -> HurstResidualCampaignResult:
    config, plan = _validate_loaded_setup(output_directory)
    summaries = _load_phase_receipts(output_directory, "summary", config, plan)
    derived_path = output_directory / DERIVED_NAME
    derived = None
    if derived_path.exists():
        derived = _load_and_check_derived(output_directory, config, plan, summaries)
    verifications: dict[int, tuple[dict[str, Any], bytes]] = {}
    if _receipt_paths(output_directory, "verify"):
        if derived is None:
            raise HurstResidualCampaignError("verify receipts exist without derived inputs")
        verifications = _load_phase_receipts(
            output_directory, "verify", config, plan, derived
        )
        for index, (report, _) in verifications.items():
            summary = summaries.get(index)
            if summary is None:
                raise HurstResidualCampaignError("verify receipt has no summary receipt")
            if report["delta"] != summary[0]["delta"]:
                raise HurstResidualCampaignError("verify delta differs from summary delta")
            if report["row_sha256"] != summary[0]["row_sha256"]:
                raise HurstResidualCampaignError("verify row SHA differs from summary row SHA")
    certificate_path = output_directory / FINAL_NAME
    certificate_root = None
    final_state = None
    complete = certificate_path.is_file()
    if complete:
        if derived is None:
            raise HurstResidualCampaignError("final certificate has no derived inputs")
        _require_complete_indices(summaries, plan, "summary")
        _require_complete_indices(verifications, plan, "verify")
        certificate_root, final_state = _verify_final(
            output_directory, config, plan, summaries, verifications, derived
        )
    full = config["mode"] == "full_source"
    return HurstResidualCampaignResult(
        mode=config["mode"],
        plan_sha256=plan.plan_sha256,
        shard_count=len(plan.shards),
        summaries=len(summaries),
        derived_inputs_ready=derived is not None,
        verifications=len(verifications),
        complete=complete,
        full_source_range=full,
        certificate_root_sha256=certificate_root,
        final_state=final_state,
        runner_sha256=config["captured_runner_sha256"],
        source_sha256=config["captured_source_sha256"],
        upstream_commit=UPSTREAM_COMMIT,
        source_residuals_replayed=complete and full,
    )


def verify_campaign(output_directory: Path) -> HurstResidualCampaignResult:
    """Replay every retained control-plane and certificate relationship."""

    try:
        with advisory_lock(output_directory / ".hurst-residual-campaign.lock"):
            return _verify_campaign_unlocked(output_directory)
    except (CampaignIOError, AffineGuardCertificateError) as exc:
        raise HurstResidualCampaignError(str(exc)) from exc


def write_registered_result(
    output_directory: Path, output: Path
) -> tuple[HurstResidualCampaignResult, dict[str, Any]]:
    """Reverify the complete source campaign and exclusively emit ``true``.

    The output bytes are fixed by this module, not supplied by the caller.  A
    bounded test, incomplete campaign, absent certificate root/final state, or
    non-source replay is rejected before any file is created.  Exclusive
    creation prevents an older result from being confused with this replay.
    """

    try:
        with advisory_lock(output_directory / ".hurst-residual-campaign.lock"):
            result = _verify_campaign_unlocked(output_directory)
            if result.mode != "full_source" or not result.full_source_range:
                raise HurstResidualCampaignError(
                    "registered Hurst result requires the literal full-source plan"
                )
            if not result.complete or not result.source_residuals_replayed:
                raise HurstResidualCampaignError(
                    "registered Hurst result requires a complete source replay"
                )
            if result.certificate_root_sha256 is None or result.final_state is None:
                raise HurstResidualCampaignError(
                    "registered Hurst result requires the final root and prefix state"
                )
            output.parent.mkdir(parents=True, exist_ok=True)
            try:
                with output.open("xb") as stream:
                    stream.write(REGISTERED_RESULT)
            except FileExistsError as exc:
                raise HurstResidualCampaignError(
                    f"refusing to overwrite an existing Hurst result artifact: {output}"
                ) from exc
            return result, {
                "path": str(output.resolve()),
                "sha256": REGISTERED_RESULT_SHA256,
                "bytes": len(REGISTERED_RESULT),
                "format": "canonical_boolean_true_no_newline_v1",
            }
    except (CampaignIOError, AffineGuardCertificateError) as exc:
        raise HurstResidualCampaignError(str(exc)) from exc


__all__ = [
    "ATOM_PROFILES",
    "CAMPAIGN_ALGORITHM",
    "DEFAULT_SEGMENT_SIZE",
    "DEFAULT_SHARD_SPAN",
    "DEFAULT_WORKER_GROUPS",
    "HurstResidualCampaignError",
    "HurstResidualCampaignResult",
    "MIN_SEGMENT_SIZE",
    "REGISTERED_RESULT_SHA256",
    "SOURCE_UPPER_EXCLUSIVE",
    "UPSTREAM_COMMIT",
    "command_for_shard",
    "create_plan",
    "finalize_campaign",
    "grouped_shard_indices",
    "ingest_receipt",
    "initialize_campaign",
    "reduce_summaries",
    "run_phase",
    "validate_runner_receipt",
    "verify_campaign",
    "write_registered_result",
]
