# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Two-pass, fixed-plan campaign for the source-scale CH25 psi runner.

Phase one runs every shard without a prefix and retains its exact additive
Q64 transition and event/row commitments.  Only a complete summary set may be
reduced; that exclusive scan derives every phase-two input from the single
root ``[0, 0]``.  Phase two independently reruns every shard and must reproduce
both commitments and the transition while accepting exactly its derived
singleton state.

The resulting affine/Merkle certificate is external finite-computation
evidence.  It is not hardware attestation and does not by itself discharge a
Lean atom.
"""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from decimal import Decimal
import os
from pathlib import Path
import re
import stat
import subprocess
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
    read_bytes_once,
    sha256_bytes,
    write_immutable_json,
)
from .evidence import EvidenceError, load_decimal_json_bytes


CAMPAIGN_SCHEMA = "sparkinterval.tg.psi-residual-campaign.v1"
DERIVED_SCHEMA = "sparkinterval.tg.psi-residual-derived-inputs.v1"
FINAL_SCHEMA = "sparkinterval.tg.psi-residual-certificate.v1"
RUNNER_ALGORITHM = "ch25-psi-prime-power-two-pass-v1"
CAMPAIGN_ALGORITHM = "ch25-psi-prime-power-affine-campaign-v1"
RUNNER_CLASSIFICATION = "source-scale-shard-not-lean-proof"
ATOM = "ch25-psi-1e13"
PRIMESIEVE_COMMIT = "4f85384851da23c36c01ec01ef85b5d9d246e556"
CRLIBM_COMMIT = "eb3063791aa75bc9705b49283bf14250465220a7"
PINNED_UPSTREAM_COMPONENTS: dict[str, dict[str, object]] = {
    "primesieve": {
        "name": "kimwalisch/primesieve segmented prime sieve",
        "repository": "https://github.com/kimwalisch/primesieve.git",
        "commit": PRIMESIEVE_COMMIT,
        "license": "BSD-2-Clause",
        "tracked_file_count": 159,
        "tracked_bytes": 1_496_122,
        "tree_sha256": (
            "f67523ec2a0985e2338dbddb0589ab47fe6eeb11a7d17583b8f0f113a9000f92"
        ),
    },
    "crlibm": {
        "name": "crlibm correctly rounded elementary functions",
        "repository": "https://github.com/taschini/crlibm.git",
        "commit": CRLIBM_COMMIT,
        "license": "LGPL-2.1-or-later",
        "tracked_file_count": 253,
        "tracked_bytes": 8_929_126,
        "tree_sha256": (
            "0eaccef04d464f8a827a27b044887df37717503d46cce45d064a5ca22840a76c"
        ),
    },
}

SOURCE_LOWER = 2
SOURCE_UPPER_EXCLUSIVE = 10_000_000_000_001
SOURCE_EVENT_COUNT = 346_065_767_406
DEFAULT_SHARD_SPAN = 100_000_000
DEFAULT_SIEVE_SIZE_KIB = 384
DEFAULT_WORKERS = max(1, os.cpu_count() or 1)
MAX_RUNNER_BYTES = 1 << 30
MAX_SOURCE_BYTES = 32 << 20
MAX_RECEIPT_BYTES = 4 << 20
REGISTERED_RESULT = b"true"
REGISTERED_RESULT_SHA256 = sha256_bytes(REGISTERED_RESULT)

STATE_COMPONENTS = ("psi_lower_q64", "psi_upper_q64")
FALLBACK_FIELDS = frozenset(
    {"lower_left_limit", "upper_post_jump", "terminal_lower"}
)
RECEIPT_FIELDS = frozenset(
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
        "guards",
        "incoming_state",
        "outgoing_state",
        "exact_fallbacks",
        "terminal_strict_lower_checked",
        "accepted",
        "elapsed_seconds",
        "execution_attested",
        "lean_atom_discharged",
    }
)

CAPTURED_RUNNER_NAME = "captured-psi-residual-runner"
CAPTURED_SOURCE_NAME = "captured-tg-psi-residual-shard.cpp"
CAPTURED_UPSTREAM_NAME = "captured-psi-upstreams.json"
CONFIG_NAME = "campaign-config.json"
PLAN_NAME = "shard-plan.json"
DERIVED_NAME = "derived-inputs.json"
FINAL_NAME = "certificate.json"
LEAF_DIRECTORY = "affine-leaves"
LOCK_NAME = ".psi-residual-campaign.lock"
_RECEIPT_NAME = re.compile(r"receipt-([0-9]{8})\.json\Z")
_LEAF_NAME = re.compile(r"leaf-([0-9]{8})\.json\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class PsiResidualCampaignError(RuntimeError):
    """A campaign identity, receipt, transition, or replay failed closed."""


@dataclass(frozen=True)
class PsiResidualCampaignResult:
    mode: str
    plan_sha256: str
    shard_count: int
    summaries: int
    derived_inputs_ready: bool
    verifications: int
    complete: bool
    full_source_range: bool
    certificate_root_sha256: str | None
    final_state: tuple[int, int] | None
    runner_sha256: str
    source_sha256: str
    source_atom_replayed: bool
    execution_attested: bool = False
    lean_atom_discharged: bool = False

    def as_json(self) -> dict[str, Any]:
        value = asdict(self)
        if self.final_state is not None:
            value["final_state"] = list(self.final_state)
        return value


def _integer(value: object, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PsiResidualCampaignError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise PsiResidualCampaignError(f"{name} must be at least {minimum}")
    return value


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PsiResidualCampaignError(
            f"{name} must be a lowercase 64-digit SHA-256 digest"
        )
    return value


def _vector(value: object, name: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise PsiResidualCampaignError(f"{name} must be a two-integer array")
    result = tuple(_integer(item, f"{name}[{index}]", minimum=0) for index, item in enumerate(value))
    return result  # type: ignore[return-value]


def _read(path: Path, maximum: int, label: str) -> bytes:
    try:
        return read_bytes_once(path, limit=maximum)
    except CampaignIOError as exc:
        raise PsiResidualCampaignError(f"cannot read {label}: {exc}") from exc


def _load_control(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except CampaignIOError as exc:
        raise PsiResidualCampaignError(str(exc)) from exc
    if not isinstance(value, dict):
        raise PsiResidualCampaignError(f"control artifact must be an object: {path}")
    return value


def _load_receipt(raw: bytes, label: str) -> dict[str, Any]:
    if len(raw) > MAX_RECEIPT_BYTES:
        raise PsiResidualCampaignError("runner receipt exceeds the byte limit")
    try:
        value = load_decimal_json_bytes(raw, label=label)
    except EvidenceError as exc:
        raise PsiResidualCampaignError(str(exc)) from exc
    if not isinstance(value, dict):
        raise PsiResidualCampaignError("runner receipt must be an object")
    return value


def _validate_upstream_manifest(raw: bytes) -> dict[str, Any]:
    try:
        value = load_decimal_json_bytes(raw, label="psi upstream manifest")
    except EvidenceError as exc:
        raise PsiResidualCampaignError(str(exc)) from exc
    if not isinstance(value, dict) or set(value) != {"kind", "components"}:
        raise PsiResidualCampaignError("psi upstream manifest fields changed")
    if value.get("kind") != "sparkinterval.pinned_upstream_bundle.v1":
        raise PsiResidualCampaignError("unsupported psi upstream manifest")
    components = value.get("components")
    if not isinstance(components, dict) or set(components) != {"primesieve", "crlibm"}:
        raise PsiResidualCampaignError("psi upstream component set changed")
    required = {
        "name",
        "repository",
        "commit",
        "license",
        "tracked_file_count",
        "tracked_bytes",
        "tree_sha256",
    }
    for name, expected in PINNED_UPSTREAM_COMPONENTS.items():
        component = components[name]
        if not isinstance(component, dict) or set(component) != required:
            raise PsiResidualCampaignError(f"{name} upstream pin fields changed")
        for field in ("name", "repository", "commit", "license"):
            if not isinstance(component.get(field), str) or not component[field]:
                raise PsiResidualCampaignError(f"{name} {field} is malformed")
        _integer(component.get("tracked_file_count"), f"{name} file count", minimum=1)
        _integer(component.get("tracked_bytes"), f"{name} tracked bytes", minimum=1)
        _digest(component.get("tree_sha256"), f"{name} tree SHA")
        if component != expected:
            raise PsiResidualCampaignError(
                f"{name} upstream source closure differs from the reviewed pin"
            )
    return value


def _plan_identity(
    *, runner_sha256: str, source_sha256: str, upstream_sha256: str,
    sieve_size_kib: int,
) -> str:
    return (
        f"{CAMPAIGN_ALGORITHM};runner={runner_sha256};source={source_sha256};"
        f"upstreams={upstream_sha256};sieve_kib={sieve_size_kib}"
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
    upper = _integer(domain_upper_exclusive, "domain upper", minimum=3)
    span = _integer(shard_span, "shard span", minimum=1)
    sieve = _integer(sieve_size_kib, "sieve size", minimum=16)
    if sieve > 8192:
        raise PsiResidualCampaignError("sieve size exceeds primesieve's limit")
    if upper > SOURCE_UPPER_EXCLUSIVE:
        raise PsiResidualCampaignError("campaign exceeds the source endpoint")
    full = upper == SOURCE_UPPER_EXCLUSIVE
    if not full and not allow_bounded_test:
        raise PsiResidualCampaignError(
            "a shortened psi domain requires explicit allow_bounded_test=True"
        )
    if full and span != DEFAULT_SHARD_SPAN:
        raise PsiResidualCampaignError(
            "the full-source psi plan requires fixed 100,000,000-integer shards"
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
                runner_sha256=runner_sha256,
                source_sha256=source_sha256,
                upstream_sha256=upstream_manifest_sha256,
                sieve_size_kib=sieve,
            ),
            state_dimension=2,
            ranges=ranges,
        )
    except AffineGuardCertificateError as exc:
        raise PsiResidualCampaignError(str(exc)) from exc


def _expected_config(
    *, plan: FixedShardPlan, shard_span: int, sieve_size_kib: int,
    runner_sha256: str, runner_size: int, source_sha256: str, source_size: int,
    upstream_manifest_sha256: str,
) -> dict[str, Any]:
    full = plan.domain_upper == SOURCE_UPPER_EXCLUSIVE
    return {
        "schema": CAMPAIGN_SCHEMA,
        "algorithm": CAMPAIGN_ALGORITHM,
        "runner_algorithm": RUNNER_ALGORITHM,
        "classification": "external_finite_computation_not_attestation_or_lean_proof",
        "mode": "full_source" if full else "bounded_test",
        "atom": ATOM,
        "domain_lower": plan.domain_lower,
        "domain_upper_exclusive": plan.domain_upper,
        "source_event_count": SOURCE_EVENT_COUNT,
        "shard_span": shard_span,
        "shard_count": len(plan.shards),
        "sieve_size_kib": sieve_size_kib,
        "state_components": list(STATE_COMPONENTS),
        "plan_sha256": plan.plan_sha256,
        "captured_runner_sha256": runner_sha256,
        "captured_runner_size": runner_size,
        "captured_source_sha256": source_sha256,
        "captured_source_size": source_size,
        "primesieve_commit": PRIMESIEVE_COMMIT,
        "crlibm_commit": CRLIBM_COMMIT,
        "upstream_manifest_sha256": upstream_manifest_sha256,
    }


def initialize_campaign(
    *, runner: Path, runner_source: Path, upstream_manifest: Path,
    output_directory: Path, shard_span: int = DEFAULT_SHARD_SPAN,
    sieve_size_kib: int = DEFAULT_SIEVE_SIZE_KIB,
    domain_upper_exclusive: int = SOURCE_UPPER_EXCLUSIVE,
    allow_bounded_test: bool = False,
) -> PsiResidualCampaignResult:
    """Capture immutable identities and materialize the fixed shard plan."""

    runner_raw = _read(runner, MAX_RUNNER_BYTES, "runner")
    source_raw = _read(runner_source, MAX_SOURCE_BYTES, "runner source")
    upstream_raw = _read(upstream_manifest, MAX_SOURCE_BYTES, "upstream manifest")
    _validate_upstream_manifest(upstream_raw)
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
        shard_span=shard_span,
        sieve_size_kib=sieve_size_kib,
        runner_sha256=runner_sha,
        runner_size=len(runner_raw),
        source_sha256=source_sha,
        source_size=len(source_raw),
        upstream_manifest_sha256=upstream_sha,
    )
    if output_directory.exists() and not output_directory.is_dir():
        raise PsiResidualCampaignError("campaign output path is not a directory")
    output_directory.mkdir(parents=True, exist_ok=True)
    try:
        with advisory_lock(output_directory / LOCK_NAME):
            captures = (
                (CAPTURED_RUNNER_NAME, runner_raw),
                (CAPTURED_SOURCE_NAME, source_raw),
                (CAPTURED_UPSTREAM_NAME, upstream_raw),
            )
            paths = [output_directory / name for name, _ in captures]
            paths += [output_directory / CONFIG_NAME, output_directory / PLAN_NAME]
            if any(path.exists() for path in paths):
                if not all(path.is_file() for path in paths):
                    raise PsiResidualCampaignError("campaign initialization is partial")
                for name, raw in captures:
                    if _read(output_directory / name, max(1, len(raw)), name) != raw:
                        raise PsiResidualCampaignError(f"captured identity changed: {name}")
                if _load_control(output_directory / CONFIG_NAME) != config:
                    raise PsiResidualCampaignError("resume configuration changed")
                if _load_control(output_directory / PLAN_NAME) != plan.to_dict():
                    raise PsiResidualCampaignError("fixed shard plan changed")
            else:
                for name, raw in captures:
                    atomic_write_bytes(output_directory / name, raw)
                write_immutable_json(output_directory / PLAN_NAME, plan.to_dict())
                write_immutable_json(output_directory / CONFIG_NAME, config)
            try:
                (output_directory / CAPTURED_RUNNER_NAME).chmod(
                    stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP
                )
            except OSError as exc:
                raise PsiResidualCampaignError(
                    f"cannot make captured runner executable: {exc}"
                ) from exc
            return _verify_campaign_unlocked(output_directory)
    except CampaignIOError as exc:
        raise PsiResidualCampaignError(str(exc)) from exc


def _validate_loaded_setup(
    output_directory: Path,
) -> tuple[dict[str, Any], FixedShardPlan]:
    config = _load_control(output_directory / CONFIG_NAME)
    required_config = {
        "schema", "algorithm", "runner_algorithm", "classification", "mode",
        "atom", "domain_lower", "domain_upper_exclusive", "source_event_count",
        "shard_span", "shard_count", "sieve_size_kib", "state_components",
        "plan_sha256", "captured_runner_sha256", "captured_runner_size",
        "captured_source_sha256", "captured_source_size", "primesieve_commit",
        "crlibm_commit", "upstream_manifest_sha256",
    }
    if set(config) != required_config:
        raise PsiResidualCampaignError("campaign config fields changed")
    if config.get("schema") != CAMPAIGN_SCHEMA or config.get("algorithm") != CAMPAIGN_ALGORITHM:
        raise PsiResidualCampaignError("unsupported psi campaign configuration")
    if config.get("runner_algorithm") != RUNNER_ALGORITHM:
        raise PsiResidualCampaignError("runner algorithm changed")
    if config.get("classification") != "external_finite_computation_not_attestation_or_lean_proof":
        raise PsiResidualCampaignError("unsafe campaign classification")
    if config.get("atom") != ATOM or config.get("state_components") != list(STATE_COMPONENTS):
        raise PsiResidualCampaignError("campaign atom or state order changed")
    if config.get("source_event_count") != SOURCE_EVENT_COUNT:
        raise PsiResidualCampaignError("source event count changed")
    if config.get("primesieve_commit") != PRIMESIEVE_COMMIT or config.get("crlibm_commit") != CRLIBM_COMMIT:
        raise PsiResidualCampaignError("campaign upstream commit changed")
    for name in (
        "plan_sha256", "captured_runner_sha256", "captured_source_sha256",
        "upstream_manifest_sha256",
    ):
        _digest(config.get(name), name)
    for name in (
        "domain_lower", "domain_upper_exclusive", "shard_span", "shard_count",
        "sieve_size_kib", "captured_runner_size", "captured_source_size",
    ):
        _integer(config.get(name), name, minimum=1)
    if config["domain_lower"] != SOURCE_LOWER or not (
        3 <= config["domain_upper_exclusive"] <= SOURCE_UPPER_EXCLUSIVE
    ):
        raise PsiResidualCampaignError("campaign domain is invalid")
    full = config["domain_upper_exclusive"] == SOURCE_UPPER_EXCLUSIVE
    if config.get("mode") not in ("full_source", "bounded_test") or (
        config["mode"] == "full_source"
    ) != full:
        raise PsiResidualCampaignError("campaign mode mislabels its domain")
    if full and config["shard_span"] != DEFAULT_SHARD_SPAN:
        raise PsiResidualCampaignError("full-source shard geometry changed")
    if not 16 <= config["sieve_size_kib"] <= 8192:
        raise PsiResidualCampaignError("campaign sieve size is invalid")

    try:
        plan = FixedShardPlan.from_dict(_load_control(output_directory / PLAN_NAME))
    except AffineGuardCertificateError as exc:
        raise PsiResidualCampaignError(f"invalid fixed plan: {exc}") from exc
    if plan.plan_sha256 != config["plan_sha256"]:
        raise PsiResidualCampaignError("plan digest differs from configuration")
    if (plan.domain_lower, plan.domain_upper, len(plan.shards), plan.state_dimension) != (
        config["domain_lower"], config["domain_upper_exclusive"],
        config["shard_count"], 2,
    ):
        raise PsiResidualCampaignError("plan domain/count differs from configuration")

    for path, digest_name, size_name, maximum in (
        (
            output_directory / CAPTURED_RUNNER_NAME,
            "captured_runner_sha256", "captured_runner_size", MAX_RUNNER_BYTES,
        ),
        (
            output_directory / CAPTURED_SOURCE_NAME,
            "captured_source_sha256", "captured_source_size", MAX_SOURCE_BYTES,
        ),
    ):
        try:
            digest, size = hash_file_once(path, limit=maximum)
        except CampaignIOError as exc:
            raise PsiResidualCampaignError(str(exc)) from exc
        if (digest, size) != (config[digest_name], config[size_name]):
            raise PsiResidualCampaignError(f"captured file identity changed: {path.name}")
    upstream_raw = _read(
        output_directory / CAPTURED_UPSTREAM_NAME,
        MAX_SOURCE_BYTES,
        "captured upstream manifest",
    )
    _validate_upstream_manifest(upstream_raw)
    if sha256_bytes(upstream_raw) != config["upstream_manifest_sha256"]:
        raise PsiResidualCampaignError("captured upstream manifest identity changed")
    expected_identity = _plan_identity(
        runner_sha256=config["captured_runner_sha256"],
        source_sha256=config["captured_source_sha256"],
        upstream_sha256=config["upstream_manifest_sha256"],
        sieve_size_kib=config["sieve_size_kib"],
    )
    if plan.algorithm != expected_identity:
        raise PsiResidualCampaignError("plan is not bound to captured identities")
    return config, plan


def _receipt_paths(output_directory: Path, phase: str) -> dict[int, Path]:
    directory = output_directory / phase
    if not directory.exists():
        return {}
    if not directory.is_dir():
        raise PsiResidualCampaignError(f"{phase} receipt path is not a directory")
    indexed: dict[int, Path] = {}
    for path in directory.glob("receipt-*.json"):
        match = _RECEIPT_NAME.fullmatch(path.name)
        if match is None or not path.is_file():
            raise PsiResidualCampaignError(f"malformed {phase} receipt path {path.name!r}")
        index = int(match.group(1))
        if index in indexed:
            raise PsiResidualCampaignError(f"duplicate {phase} receipt index {index}")
        indexed[index] = path
    return indexed


def validate_runner_receipt(
    report: Mapping[str, Any], *, phase: str, shard_lower: int,
    shard_upper: int, sieve_size_kib: int,
    expected_incoming: Sequence[int] | None = None,
    source_terminal: bool = False,
) -> tuple[int, int]:
    """Strictly validate one runner receipt against a fixed plan leaf."""

    if not isinstance(report, Mapping) or set(report) != RECEIPT_FIELDS:
        actual = set(report) if isinstance(report, Mapping) else set()
        raise PsiResidualCampaignError(
            "runner receipt fields changed; "
            f"missing={sorted(RECEIPT_FIELDS - actual)}, "
            f"extra={sorted(actual - RECEIPT_FIELDS)}"
        )
    if phase not in ("summary", "verify") or report.get("mode") != phase:
        raise PsiResidualCampaignError("runner receipt has the wrong phase")
    if report.get("algorithm") != RUNNER_ALGORITHM or report.get("atom") != ATOM:
        raise PsiResidualCampaignError("runner algorithm or atom changed")
    if report.get("classification") != RUNNER_CLASSIFICATION:
        raise PsiResidualCampaignError("runner classification changed")
    if report.get("primesieve_commit") != PRIMESIEVE_COMMIT or report.get("crlibm_commit") != CRLIBM_COMMIT:
        raise PsiResidualCampaignError("runner used the wrong upstream commit")
    work_count = shard_upper - shard_lower
    if (
        report.get("lower"), report.get("upper_exclusive"),
        report.get("work_count"), report.get("sieve_size_kib"),
    ) != (shard_lower, shard_upper, work_count, sieve_size_kib):
        raise PsiResidualCampaignError("runner receipt range/config differs from request")
    fixed_fields = {
        "scale_bits": 64,
        "log_interval_encoding": "crlibm-binary64-directed-to-q64-v1",
        "event_encoding": "u64be-value-u64be-prime-u32be-exponent-v1",
        "row_encoding": "u64be-value-u64be-prime-u32be-exponent-u128be-log-pair-v1",
        "state_components": list(STATE_COMPONENTS),
    }
    for name, expected in fixed_fields.items():
        if report.get(name) != expected:
            raise PsiResidualCampaignError(f"runner {name} changed")
    _digest(report.get("event_sha256"), "event_sha256")
    _digest(report.get("row_sha256"), "row_sha256")
    events = _integer(report.get("prime_power_events"), "prime-power events", minimum=0)
    primes = _integer(report.get("prime_events"), "prime events", minimum=0)
    powers = _integer(report.get("higher_power_events"), "higher-power events", minimum=0)
    if events != primes + powers or events > work_count:
        raise PsiResidualCampaignError("runner event counters are inconsistent")
    delta = _vector(report.get("delta"), "delta")
    if delta[0] > delta[1] or any(value >= 1 << 128 for value in delta):
        raise PsiResidualCampaignError("runner Q64 delta is reversed or out of range")
    # log(p) < 31 over the entire source range.  This is only a format sanity
    # bound; the independent verify pass and row commitment carry semantics.
    if delta[1] > events * 31 * (1 << 64):
        raise PsiResidualCampaignError("runner Q64 delta exceeds the event-count bound")
    fallbacks = report.get("exact_fallbacks")
    if not isinstance(fallbacks, dict) or set(fallbacks) != FALLBACK_FIELDS:
        raise PsiResidualCampaignError("runner fallback counters changed")
    for name, value in fallbacks.items():
        count = _integer(value, f"fallback counter {name}", minimum=0)
        maximum = 1 if name == "terminal_lower" else events
        if count > maximum:
            raise PsiResidualCampaignError(f"fallback counter {name} is impossible")
    elapsed = report.get("elapsed_seconds")
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, Decimal)) or elapsed < 0:
        raise PsiResidualCampaignError("elapsed_seconds must be nonnegative")
    if report.get("accepted") is not True:
        raise PsiResidualCampaignError("runner did not accept the shard")
    if report.get("execution_attested") is not False or report.get("lean_atom_discharged") is not False:
        raise PsiResidualCampaignError("runner made an unsafe trust-boundary claim")

    terminal = report.get("terminal_strict_lower_checked")
    if not isinstance(terminal, bool):
        raise PsiResidualCampaignError("terminal check flag must be Boolean")
    if phase == "summary":
        if report.get("guards") != {} or report.get("incoming_state") is not None or report.get("outgoing_state") is not None:
            raise PsiResidualCampaignError("summary receipt must not claim a prefix state")
        if any(fallbacks.values()) or terminal:
            raise PsiResidualCampaignError("summary receipt claims verification work")
    else:
        if expected_incoming is None:
            raise PsiResidualCampaignError("verify receipt needs a root-derived input")
        incoming = tuple(expected_incoming)
        if len(incoming) != 2 or any(type(value) is not int or value < 0 for value in incoming):
            raise PsiResidualCampaignError("derived input must have two natural coordinates")
        if _vector(report.get("incoming_state"), "reported incoming") != incoming:
            raise PsiResidualCampaignError("verify incoming differs from the root-derived input")
        expected_outgoing = (incoming[0] + delta[0], incoming[1] + delta[1])
        if _vector(report.get("outgoing_state"), "reported outgoing") != expected_outgoing:
            raise PsiResidualCampaignError("verify outgoing differs from incoming plus delta")
        guards = report.get("guards")
        if not isinstance(guards, dict) or set(guards) != {ATOM}:
            raise PsiResidualCampaignError("verify guard atom changed")
        guard = guards[ATOM]
        if not isinstance(guard, dict) or set(guard) != {"lower_guard", "upper_guard", "witnesses"}:
            raise PsiResidualCampaignError("verify singleton guard is malformed")
        if _vector(guard["lower_guard"], "lower guard") != incoming or _vector(guard["upper_guard"], "upper guard") != incoming or guard["witnesses"] != []:
            raise PsiResidualCampaignError("verify guard differs from the root-derived input")
        if terminal != source_terminal:
            raise PsiResidualCampaignError("verify terminal-check flag differs from the fixed plan")
    return delta


def _load_phase_receipts(
    output_directory: Path, phase: str, config: Mapping[str, Any],
    plan: FixedShardPlan, derived: Mapping[str, Any] | None = None,
) -> dict[int, tuple[dict[str, Any], bytes]]:
    result: dict[int, tuple[dict[str, Any], bytes]] = {}
    for index, path in _receipt_paths(output_directory, phase).items():
        if index >= len(plan.shards):
            raise PsiResidualCampaignError(f"{phase} receipt index is outside the plan")
        raw = _read(path, MAX_RECEIPT_BYTES, f"{phase} receipt")
        report = _load_receipt(raw, str(path))
        incoming = None
        if phase == "verify":
            if derived is None:
                raise PsiResidualCampaignError("verify receipts exist before derived inputs")
            entries = derived.get("entries")
            if not isinstance(entries, list) or index >= len(entries) or not isinstance(entries[index], dict):
                raise PsiResidualCampaignError("derived input table is malformed")
            incoming = _vector(entries[index].get("incoming"), "derived incoming")
        shard = plan.shards[index]
        validate_runner_receipt(
            report,
            phase=phase,
            shard_lower=shard.lower,
            shard_upper=shard.upper,
            sieve_size_kib=config["sieve_size_kib"],
            expected_incoming=incoming,
            source_terminal=shard.upper == SOURCE_UPPER_EXCLUSIVE,
        )
        result[index] = (report, raw)
    return result


def _require_complete(
    receipts: Mapping[int, object], plan: FixedShardPlan, phase: str
) -> None:
    wanted = set(range(len(plan.shards)))
    actual = set(receipts)
    if actual != wanted:
        missing = sorted(wanted - actual)
        extra = sorted(actual - wanted)
        preview = missing[:8]
        raise PsiResidualCampaignError(
            f"{phase} receipts are incomplete (missing={preview}"
            f"{'...' if len(missing) > len(preview) else ''}, extra={extra})"
        )


def _derive_payload(
    config: Mapping[str, Any], plan: FixedShardPlan,
    summaries: Mapping[int, tuple[dict[str, Any], bytes]],
) -> dict[str, Any]:
    _require_complete(summaries, plan, "summary")
    current = (0, 0)
    entries: list[dict[str, Any]] = []
    total_events = 0
    for index, shard in enumerate(plan.shards):
        report, raw = summaries[index]
        delta = _vector(report["delta"], "summary delta")
        outgoing = (current[0] + delta[0], current[1] + delta[1])
        total_events += report["prime_power_events"]
        entries.append(
            {
                "index": index,
                "lower": shard.lower,
                "upper": shard.upper,
                "summary_receipt_sha256": sha256_bytes(raw),
                "event_sha256": report["event_sha256"],
                "row_sha256": report["row_sha256"],
                "prime_power_events": report["prime_power_events"],
                "delta": list(delta),
                "incoming": list(current),
                "outgoing": list(outgoing),
            }
        )
        current = outgoing
    full = config["mode"] == "full_source"
    if full and total_events != SOURCE_EVENT_COUNT:
        raise PsiResidualCampaignError(
            "full-source summary event total differs from the pinned count"
        )
    content = {
        "schema": DERIVED_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "config_sha256": canonical_sha256(dict(config)),
        "root_state": [0, 0],
        "entries": entries,
        "total_prime_power_events": total_events,
        "source_event_count_matches": full and total_events == SOURCE_EVENT_COUNT,
        "final_state": list(current),
    }
    content["summary_set_sha256"] = canonical_sha256(content)
    return content


def reduce_summaries(output_directory: Path) -> dict[str, Any]:
    """Derive phase-two inputs only from a complete fixed summary set."""

    try:
        with advisory_lock(output_directory / LOCK_NAME):
            config, plan = _validate_loaded_setup(output_directory)
            summaries = _load_phase_receipts(output_directory, "summary", config, plan)
            derived = _derive_payload(config, plan, summaries)
            write_immutable_json(output_directory / DERIVED_NAME, derived)
            return derived
    except (CampaignIOError, AffineGuardCertificateError) as exc:
        raise PsiResidualCampaignError(str(exc)) from exc


def _load_derived(
    output_directory: Path, config: Mapping[str, Any], plan: FixedShardPlan,
    summaries: Mapping[int, tuple[dict[str, Any], bytes]],
) -> dict[str, Any]:
    path = output_directory / DERIVED_NAME
    if not path.is_file():
        raise PsiResidualCampaignError(
            "derived inputs are absent; finish phase one and reduce"
        )
    actual = _load_control(path)
    expected = _derive_payload(config, plan, summaries)
    if actual != expected:
        raise PsiResidualCampaignError(
            "derived inputs disagree with the summary receipts"
        )
    return actual


def _command(
    output_directory: Path, config: Mapping[str, Any], plan: FixedShardPlan,
    *, phase: str, shard_index: int, derived: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    shard = plan.shards[shard_index]
    command = [
        str((output_directory / CAPTURED_RUNNER_NAME).resolve()),
        "--lower", str(shard.lower),
        "--upper", str(shard.upper - 1),
        "--sieve-size-kib", str(config["sieve_size_kib"]),
        "--mode", phase,
    ]
    if phase == "verify":
        if derived is None:
            raise PsiResidualCampaignError("verify command requires derived inputs")
        incoming = _vector(
            derived["entries"][shard_index]["incoming"], "derived incoming"
        )
        command.extend(("--incoming-lower", str(incoming[0])))
        command.extend(("--incoming-upper", str(incoming[1])))
    return tuple(command)


def command_for_shard(
    output_directory: Path, *, phase: str, shard_index: int
) -> tuple[str, ...]:
    """Return the immutable captured-runner argv for one cluster worker."""

    config, plan = _validate_loaded_setup(output_directory)
    index = _integer(shard_index, "shard index", minimum=0)
    if index >= len(plan.shards):
        raise PsiResidualCampaignError("shard index is outside the fixed plan")
    if phase not in ("summary", "verify"):
        raise PsiResidualCampaignError("phase must be summary or verify")
    derived = None
    if phase == "verify":
        summaries = _load_phase_receipts(output_directory, "summary", config, plan)
        derived = _load_derived(output_directory, config, plan, summaries)
    return _command(
        output_directory, config, plan, phase=phase, shard_index=index, derived=derived
    )


def grouped_shard_indices(
    output_directory: Path, *, group_index: int, group_count: int
) -> tuple[int, ...]:
    """Return one deterministic disjoint strided group of fixed-plan leaves.

    This reduces scheduler launch overhead without changing the leaf plan or
    receipt granularity.  All groups together cover every shard index exactly
    once; each selected shard still produces its own immutable receipt.
    """

    _, plan = _validate_loaded_setup(output_directory)
    count = _integer(group_count, "worker group count", minimum=1)
    index = _integer(group_index, "worker group index", minimum=0)
    if count > len(plan.shards):
        raise PsiResidualCampaignError(
            "worker group count cannot exceed the fixed-plan shard count"
        )
    if index >= count:
        raise PsiResidualCampaignError("worker group index is outside the group count")
    return tuple(range(index, len(plan.shards), count))


def _validate_receipt_for_index(
    *, phase: str, index: int, raw: bytes, config: Mapping[str, Any],
    plan: FixedShardPlan, summaries: Mapping[int, tuple[dict[str, Any], bytes]],
    derived: Mapping[str, Any] | None,
) -> dict[str, Any]:
    report = _load_receipt(raw, f"incoming {phase} receipt {index}")
    shard = plan.shards[index]
    incoming = None
    if phase == "verify":
        if derived is None:
            raise PsiResidualCampaignError("verify receipt has no derived input table")
        incoming = _vector(derived["entries"][index]["incoming"], "derived incoming")
    delta = validate_runner_receipt(
        report,
        phase=phase,
        shard_lower=shard.lower,
        shard_upper=shard.upper,
        sieve_size_kib=config["sieve_size_kib"],
        expected_incoming=incoming,
        source_terminal=shard.upper == SOURCE_UPPER_EXCLUSIVE,
    )
    if phase == "verify":
        if index not in summaries:
            raise PsiResidualCampaignError("verify receipt has no summary receipt")
        summary = summaries[index][0]
        if delta != _vector(summary["delta"], "summary delta"):
            raise PsiResidualCampaignError("verify delta differs from summary delta")
        if report["event_sha256"] != summary["event_sha256"]:
            raise PsiResidualCampaignError("verify event SHA differs from summary event SHA")
        if report["row_sha256"] != summary["row_sha256"]:
            raise PsiResidualCampaignError("verify row SHA differs from summary row SHA")
        if report["prime_power_events"] != summary["prime_power_events"]:
            raise PsiResidualCampaignError("verify event count differs from summary")
    return report


def _retain_raw(
    output_directory: Path, *, phase: str, index: int, raw: bytes
) -> None:
    directory = output_directory / phase
    destination = directory / f"receipt-{index:08d}.json"
    try:
        with advisory_lock(output_directory / LOCK_NAME):
            directory.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                existing = _read(destination, MAX_RECEIPT_BYTES, "retained receipt")
                if existing != raw:
                    raise PsiResidualCampaignError(
                        "refusing to replace a retained receipt"
                    )
                return
            atomic_write_bytes(destination, raw)
    except CampaignIOError as exc:
        raise PsiResidualCampaignError(str(exc)) from exc


def _ingest_unlocked(
    output_directory: Path, *, phase: str, shard_index: int, raw: bytes
) -> None:
    config, plan = _validate_loaded_setup(output_directory)
    index = _integer(shard_index, "shard index", minimum=0)
    if index >= len(plan.shards):
        raise PsiResidualCampaignError("shard index is outside the fixed plan")
    if phase not in ("summary", "verify"):
        raise PsiResidualCampaignError("phase must be summary or verify")
    summaries = _load_phase_receipts(output_directory, "summary", config, plan)
    derived = None
    if phase == "verify":
        derived = _load_derived(output_directory, config, plan, summaries)
    _validate_receipt_for_index(
        phase=phase, index=index, raw=raw, config=config, plan=plan,
        summaries=summaries, derived=derived,
    )
    directory = output_directory / phase
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"receipt-{index:08d}.json"
    if destination.exists():
        if _read(destination, MAX_RECEIPT_BYTES, "retained receipt") != raw:
            raise PsiResidualCampaignError("refusing to replace a retained receipt")
        return
    atomic_write_bytes(destination, raw)


def ingest_receipt(
    output_directory: Path, *, phase: str, shard_index: int, receipt_path: Path
) -> PsiResidualCampaignResult:
    """Validate and immutably retain one externally executed cluster receipt."""

    raw = _read(receipt_path, MAX_RECEIPT_BYTES, "incoming receipt")
    try:
        with advisory_lock(output_directory / LOCK_NAME):
            _ingest_unlocked(
                output_directory, phase=phase, shard_index=shard_index, raw=raw
            )
            return _verify_campaign_unlocked(output_directory)
    except CampaignIOError as exc:
        raise PsiResidualCampaignError(str(exc)) from exc


def _execute(command: tuple[str, ...], timeout_seconds: int | None) -> bytes:
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PsiResidualCampaignError(f"runner invocation failed: {exc}") from exc
    if completed.returncode != 0:
        diagnostic = completed.stderr[:4096].decode("utf-8", errors="replace")
        raise PsiResidualCampaignError(
            f"runner returned {completed.returncode}: {diagnostic}"
        )
    if len(completed.stdout) > MAX_RECEIPT_BYTES:
        raise PsiResidualCampaignError("runner emitted an oversized receipt")
    return completed.stdout


def run_phase(
    output_directory: Path, *, phase: str,
    shard_indices: Sequence[int] | None = None, max_shards: int | None = None,
    workers: int = DEFAULT_WORKERS, timeout_seconds: int | None = None,
) -> PsiResidualCampaignResult:
    """Run and checkpoint missing shards with bounded parallel subprocesses."""

    worker_count = _integer(workers, "workers", minimum=1)
    if max_shards is not None:
        _integer(max_shards, "max shards", minimum=1)
    if timeout_seconds is not None:
        _integer(timeout_seconds, "timeout seconds", minimum=1)
    try:
        with advisory_lock(output_directory / LOCK_NAME):
            config, plan = _validate_loaded_setup(output_directory)
            if phase not in ("summary", "verify"):
                raise PsiResidualCampaignError("phase must be summary or verify")
            summaries = _load_phase_receipts(output_directory, "summary", config, plan)
            derived = None
            if phase == "verify":
                derived = _load_derived(output_directory, config, plan, summaries)
            existing = _receipt_paths(output_directory, phase)
        if shard_indices is None:
            selected = [index for index in range(len(plan.shards)) if index not in existing]
        else:
            selected = []
            seen: set[int] = set()
            for raw_index in shard_indices:
                index = _integer(raw_index, "shard index", minimum=0)
                if index >= len(plan.shards):
                    raise PsiResidualCampaignError("shard index is outside the fixed plan")
                if index in seen:
                    raise PsiResidualCampaignError("duplicate requested shard index")
                seen.add(index)
                if index not in existing:
                    selected.append(index)
        if max_shards is not None:
            selected = selected[:max_shards]

        def submit_one(executor: ThreadPoolExecutor, index: int) -> Future[bytes]:
            command = _command(
                output_directory, config, plan, phase=phase,
                shard_index=index, derived=derived,
            )
            return executor.submit(_execute, command, timeout_seconds)

        iterator = iter(selected)
        pending: dict[Future[bytes], int] = {}
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            for _ in range(min(len(selected), worker_count * 2)):
                index = next(iterator, None)
                if index is None:
                    break
                pending[submit_one(executor, index)] = index
            while pending:
                completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in completed:
                    index = pending.pop(future)
                    try:
                        raw = future.result()
                        _validate_receipt_for_index(
                            phase=phase, index=index, raw=raw, config=config,
                            plan=plan, summaries=summaries, derived=derived,
                        )
                        _retain_raw(
                            output_directory, phase=phase, index=index, raw=raw
                        )
                    except Exception:
                        for other in pending:
                            other.cancel()
                        raise
                    following = next(iterator, None)
                    if following is not None:
                        pending[submit_one(executor, following)] = following
        return verify_campaign(output_directory)
    except (CampaignIOError, AffineGuardCertificateError) as exc:
        raise PsiResidualCampaignError(str(exc)) from exc


def _build_leaves(
    plan: FixedShardPlan,
    summaries: Mapping[int, tuple[dict[str, Any], bytes]],
    verifications: Mapping[int, tuple[dict[str, Any], bytes]],
    derived: Mapping[str, Any],
) -> tuple[AffineGuardLeaf, ...]:
    _require_complete(summaries, plan, "summary")
    _require_complete(verifications, plan, "verify")
    leaves: list[AffineGuardLeaf] = []
    for index, shard in enumerate(plan.shards):
        summary = summaries[index][0]
        verification = verifications[index][0]
        delta = _vector(summary["delta"], "summary delta")
        if _vector(verification["delta"], "verify delta") != delta:
            raise PsiResidualCampaignError("verify delta differs from summary delta")
        for field in ("event_sha256", "row_sha256", "prime_power_events"):
            if verification[field] != summary[field]:
                raise PsiResidualCampaignError(f"verify {field} differs from summary")
        incoming = _vector(derived["entries"][index]["incoming"], "derived incoming")
        transition = AffineGuardTransition(delta, incoming, incoming)
        witnesses = tuple(
            TightGuardWitness(
                row_index=shard.lower, prefix_delta=0, row_guard=value
            )
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
    config: Mapping[str, Any], plan: FixedShardPlan,
    derived: Mapping[str, Any], leaves: Sequence[AffineGuardLeaf],
    verifications: Mapping[int, tuple[dict[str, Any], bytes]],
) -> dict[str, Any]:
    try:
        checked = verify_affine_guard_certificate(
            plan=plan, root_state=(0, 0), leaves=leaves
        )
    except AffineGuardCertificateError as exc:
        raise PsiResidualCampaignError(f"affine certificate failed: {exc}") from exc
    full = config["mode"] == "full_source"
    verification_index = {
        "schema": "sparkinterval.tg.psi-residual-verification-set.v1",
        "plan_sha256": plan.plan_sha256,
        "entries": [
            {
                "index": index,
                "receipt_sha256": sha256_bytes(verifications[index][1]),
                "event_sha256": verifications[index][0]["event_sha256"],
                "row_sha256": verifications[index][0]["row_sha256"],
                "prime_power_events": verifications[index][0]["prime_power_events"],
                "delta": verifications[index][0]["delta"],
                "incoming": derived["entries"][index]["incoming"],
                "terminal_strict_lower_checked": verifications[index][0][
                    "terminal_strict_lower_checked"
                ],
            }
            for index in range(len(plan.shards))
        ],
    }
    return {
        "schema": FINAL_SCHEMA,
        "classification": "plan_bound_external_finite_computation_not_attestation_or_lean_proof",
        "certificate_scope": ATOM,
        "guard_encoding": "root_derived_singleton_shard_boundary_v1",
        "atom": ATOM,
        "plan_sha256": plan.plan_sha256,
        "config_sha256": canonical_sha256(dict(config)),
        "runner_sha256": config["captured_runner_sha256"],
        "source_sha256": config["captured_source_sha256"],
        "primesieve_commit": PRIMESIEVE_COMMIT,
        "crlibm_commit": CRLIBM_COMMIT,
        "upstream_manifest_sha256": config["upstream_manifest_sha256"],
        "summary_set_sha256": derived["summary_set_sha256"],
        "verification_set_sha256": canonical_sha256(verification_index),
        "total_prime_power_events": derived["total_prime_power_events"],
        "source_event_count_matches": derived["source_event_count_matches"],
        "event_delta_and_row_replay_match_summary": True,
        "singleton_guards_match_root_derived_inputs": True,
        "source_terminal_strict_lower_checked":
            full and verifications[len(plan.shards) - 1][0]["terminal_strict_lower_checked"],
        "full_source_range": full,
        "source_atom_replayed": full,
        "execution_attested": False,
        "lean_atom_discharged": False,
        "generic_affine_certificate": checked.to_dict(),
    }


def finalize_campaign(output_directory: Path) -> PsiResidualCampaignResult:
    """Reject incomplete phases and materialize ordered affine/Merkle leaves."""

    try:
        with advisory_lock(output_directory / LOCK_NAME):
            config, plan = _validate_loaded_setup(output_directory)
            summaries = _load_phase_receipts(output_directory, "summary", config, plan)
            derived = _load_derived(output_directory, config, plan, summaries)
            verifications = _load_phase_receipts(
                output_directory, "verify", config, plan, derived
            )
            leaves = _build_leaves(plan, summaries, verifications, derived)
            leaf_directory = output_directory / LEAF_DIRECTORY
            leaf_directory.mkdir(parents=True, exist_ok=True)
            for path in leaf_directory.glob("leaf-*.json"):
                match = _LEAF_NAME.fullmatch(path.name)
                if match is None or int(match.group(1)) >= len(leaves):
                    raise PsiResidualCampaignError(f"unexpected affine leaf {path.name}")
            for index, leaf in enumerate(leaves):
                write_immutable_json(
                    leaf_directory / f"leaf-{index:08d}.json", leaf.to_dict()
                )
            write_immutable_json(
                output_directory / FINAL_NAME,
                _final_payload(config, plan, derived, leaves, verifications),
            )
            return _verify_campaign_unlocked(output_directory)
    except (CampaignIOError, AffineGuardCertificateError) as exc:
        raise PsiResidualCampaignError(str(exc)) from exc


def _verify_final(
    output_directory: Path, config: Mapping[str, Any], plan: FixedShardPlan,
    summaries: Mapping[int, tuple[dict[str, Any], bytes]],
    verifications: Mapping[int, tuple[dict[str, Any], bytes]],
    derived: Mapping[str, Any],
) -> tuple[str, tuple[int, int]]:
    leaves = _build_leaves(plan, summaries, verifications, derived)
    paths: dict[int, Path] = {}
    leaf_directory = output_directory / LEAF_DIRECTORY
    for path in leaf_directory.glob("leaf-*.json"):
        match = _LEAF_NAME.fullmatch(path.name)
        if match is None or not path.is_file():
            raise PsiResidualCampaignError(f"malformed affine leaf path {path.name}")
        paths[int(match.group(1))] = path
    if set(paths) != set(range(len(leaves))):
        raise PsiResidualCampaignError("affine leaf files are missing or duplicated")
    for index, expected in enumerate(leaves):
        try:
            actual = AffineGuardLeaf.from_dict(_load_control(paths[index]))
        except AffineGuardCertificateError as exc:
            raise PsiResidualCampaignError(f"malformed affine leaf {index}: {exc}") from exc
        if actual != expected:
            raise PsiResidualCampaignError(f"affine leaf {index} differs from replay")
    payload = _final_payload(config, plan, derived, leaves, verifications)
    if _load_control(output_directory / FINAL_NAME) != payload:
        raise PsiResidualCampaignError("final certificate differs from replayed receipts")
    generic = payload["generic_affine_certificate"]
    root = _digest(generic["certificate_root_sha256"], "certificate root")
    final = _vector(generic["final_state"], "final state")
    return root, final


def _verify_campaign_unlocked(output_directory: Path) -> PsiResidualCampaignResult:
    config, plan = _validate_loaded_setup(output_directory)
    summaries = _load_phase_receipts(output_directory, "summary", config, plan)
    derived = None
    if (output_directory / DERIVED_NAME).exists():
        derived = _load_derived(output_directory, config, plan, summaries)
    verifications: dict[int, tuple[dict[str, Any], bytes]] = {}
    if _receipt_paths(output_directory, "verify"):
        if derived is None:
            raise PsiResidualCampaignError("verify receipts exist without derived inputs")
        verifications = _load_phase_receipts(
            output_directory, "verify", config, plan, derived
        )
        for index, (report, _) in verifications.items():
            if index not in summaries:
                raise PsiResidualCampaignError("verify receipt has no summary")
            summary = summaries[index][0]
            for field in (
                "delta", "event_sha256", "row_sha256", "prime_power_events"
            ):
                if report[field] != summary[field]:
                    raise PsiResidualCampaignError(
                        f"verify {field} differs from summary"
                    )
    complete = (output_directory / FINAL_NAME).is_file()
    certificate_root = None
    final_state = None
    if complete:
        if derived is None:
            raise PsiResidualCampaignError("final certificate has no derived inputs")
        _require_complete(summaries, plan, "summary")
        _require_complete(verifications, plan, "verify")
        certificate_root, final_state = _verify_final(
            output_directory, config, plan, summaries, verifications, derived
        )
    full = config["mode"] == "full_source"
    return PsiResidualCampaignResult(
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
        source_atom_replayed=complete and full,
    )


def verify_campaign(output_directory: Path) -> PsiResidualCampaignResult:
    """Replay every captured identity, receipt, scan, leaf, and root."""

    try:
        with advisory_lock(output_directory / LOCK_NAME):
            return _verify_campaign_unlocked(output_directory)
    except (CampaignIOError, AffineGuardCertificateError) as exc:
        raise PsiResidualCampaignError(str(exc)) from exc


def write_registered_result(
    output_directory: Path, output: Path
) -> tuple[PsiResidualCampaignResult, dict[str, Any]]:
    """Reverify the complete source campaign and exclusively emit ``true``.

    The caller cannot provide result bytes.  A bounded test, incomplete
    campaign, absent certificate root/final state, or non-source replay is
    rejected before the closed-registry payload is created.  Exclusive
    creation prevents a pre-existing file from being mistaken for this run's
    terminal result.
    """

    try:
        with advisory_lock(output_directory / LOCK_NAME):
            result = _verify_campaign_unlocked(output_directory)
            if result.mode != "full_source" or not result.full_source_range:
                raise PsiResidualCampaignError(
                    "registered psi result requires the literal full-source plan"
                )
            if not result.complete or not result.source_atom_replayed:
                raise PsiResidualCampaignError(
                    "registered psi result requires a complete source replay"
                )
            if result.certificate_root_sha256 is None or result.final_state is None:
                raise PsiResidualCampaignError(
                    "registered psi result requires the final root and Q64 state"
                )
            output.parent.mkdir(parents=True, exist_ok=True)
            try:
                with output.open("xb") as stream:
                    stream.write(REGISTERED_RESULT)
            except FileExistsError as exc:
                raise PsiResidualCampaignError(
                    f"refusing to overwrite an existing psi result artifact: {output}"
                ) from exc
            return result, {
                "path": str(output.resolve()),
                "sha256": REGISTERED_RESULT_SHA256,
                "bytes": len(REGISTERED_RESULT),
                "format": "canonical_boolean_true_no_newline_v1",
            }
    except (CampaignIOError, AffineGuardCertificateError) as exc:
        raise PsiResidualCampaignError(str(exc)) from exc


__all__ = [
    "ATOM",
    "CRLIBM_COMMIT",
    "DEFAULT_SHARD_SPAN",
    "DEFAULT_SIEVE_SIZE_KIB",
    "DEFAULT_WORKERS",
    "PRIMESIEVE_COMMIT",
    "REGISTERED_RESULT_SHA256",
    "PsiResidualCampaignError",
    "PsiResidualCampaignResult",
    "SOURCE_UPPER_EXCLUSIVE",
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
