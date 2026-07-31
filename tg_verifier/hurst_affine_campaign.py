# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""One-pass affine-guard campaign for the four Hurst residual atoms.

Each worker sieves one fixed shard exactly once and returns:

* the four-coordinate additive state delta;
* a commitment to the local Mobius rows; and
* one exact incoming-state guard for each of the four residual profiles.

The source-wide supervisor never trusts a worker-supplied incoming state.  It
derives every shard input by an exclusive scan from the literal zero root,
checks that input against all four guards, intersects those guards, and binds
the ordered transitions to the fixed gap-free plan.

This module independently replays those retained *certificate relationships*.
It deliberately does not claim to reconstruct the Mobius rows from a receipt,
attest execution, or discharge a Lean atom.  A measured execution or a
data-only row-realization checker remains the boundary connecting each worker
receipt to the mathematical row predicates.
"""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from decimal import Decimal
import os
from pathlib import Path
import re
import stat
import threading
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
from .hurst_residual_campaign import (
    ATOM_PROFILES,
    DEFAULT_LOCAL_WORKERS,
    DEFAULT_SEGMENT_SIZE,
    DEFAULT_SHARD_SPAN,
    DEFAULT_WORKER_GROUPS,
    EXACT_FALLBACK_FIELDS,
    MAX_FULL_SOURCE_SHARD_SPAN,
    MAX_RECEIPT_BYTES,
    MAX_RUNNER_BYTES,
    MAX_SEGMENT_SIZE,
    MAX_SOURCE_BYTES,
    MIN_SEGMENT_SIZE,
    RUNNER_ALGORITHM,
    RUNNER_CLASSIFICATION,
    SOURCE_LOWER,
    SOURCE_UPPER_EXCLUSIVE,
    STATE_COMPONENTS,
    UPSTREAM_COMMIT,
    HurstResidualCampaignError,
    _execute_shard,
)


CAMPAIGN_SCHEMA = "sparkinterval.tg.hurst-affine-onepass-campaign.v1"
FINAL_SCHEMA = "sparkinterval.tg.hurst-affine-onepass-certificate.v1"
SCAN_SCHEMA = "sparkinterval.tg.hurst-affine-onepass-scan.v1"
RECEIPT_SET_SCHEMA = "sparkinterval.tg.hurst-affine-onepass-receipt-set.v1"
LEAF_BUNDLE_SCHEMA = "sparkinterval.tg.hurst-affine-onepass-leaf-bundle.v1"
CAMPAIGN_ALGORITHM = (
    "hurst-segmented-mobius-affine-four-residual-campaign-v1"
)
CLASSIFICATION = (
    "plan_bound_external_finite_computation_not_attestation_or_lean_proof"
)

CAPTURED_RUNNER_NAME = "captured-hurst-residual-runner"
CAPTURED_SOURCE_NAME = "captured-hurst-residual-shard.cpp"
CAPTURED_UPSTREAM_NAME = "captured-hurst-upstream-manifest.json"
CONFIG_NAME = "affine-campaign-config.json"
PLAN_NAME = "affine-shard-plan.json"
RECEIPT_DIRECTORY = "affine-receipts"
LEAF_BUNDLE_NAME = "affine-leaves.json"
SCAN_NAME = "affine-scan.json"
FINAL_NAME = "affine-certificate.json"
LOCK_NAME = ".hurst-affine-onepass-campaign.lock"

_RECEIPT_NAME = re.compile(r"receipt-([0-9]{8})\.json\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")

WIDE_I64_LOWER = -4_000_000_000_000_000_000
WIDE_I64_UPPER = 4_000_000_000_000_000_000
WIDE_I128 = 1 << 120
SIGNED_I128_LOWER = -(1 << 127)
SIGNED_I128_UPPER = (1 << 127) - 1
SIGNED_I64_LOWER = -(1 << 63)
SIGNED_I64_UPPER = (1 << 63) - 1

_WIDE_LOWER = (WIDE_I64_LOWER, WIDE_I64_LOWER, -WIDE_I128, -WIDE_I128)
_WIDE_UPPER = (WIDE_I64_UPPER, WIDE_I64_UPPER, WIDE_I128, WIDE_I128)
_ACTIVE_COMPONENTS = {
    "mertens-hurst": (0,),
    "cdem-squarefree": (1,),
    "platt-little-mertens-2-11": (2, 3),
    "platt-little-mertens-stronger": (2, 3),
}
_ALLOWED_SIDES = {
    "mertens-hurst": frozenset({"none", "integer"}),
    "cdem-squarefree": frozenset({"none", "integer", "right_limit"}),
    "platt-little-mertens-2-11": frozenset({"none", "right_limit"}),
    "platt-little-mertens-stronger": frozenset({"none", "right_limit"}),
}
_RECEIPT_FIELDS = frozenset(
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


class HurstAffineCampaignError(HurstResidualCampaignError):
    """A one-pass affine campaign artifact failed closed."""


@dataclass(frozen=True)
class HurstAffineCampaignResult:
    mode: str
    plan_sha256: str
    shard_count: int
    affine_receipts: int
    complete: bool
    full_source_range: bool
    certificate_root_sha256: str | None
    final_state: tuple[int, int, int, int] | None
    all_root_derived_inputs_in_all_atom_guards: bool
    runner_sha256: str
    source_sha256: str
    upstream_commit: str
    source_rows_replayed_independently: bool = False
    physical_row_realization_pending: bool = True
    execution_attested: bool = False
    lean_atoms_discharged: bool = False

    def as_json(self) -> dict[str, Any]:
        value = asdict(self)
        if self.final_state is not None:
            value["final_state"] = list(self.final_state)
        return value


def _plain_int(value: object, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HurstAffineCampaignError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise HurstAffineCampaignError(f"{name} must be at least {minimum}")
    return value


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise HurstAffineCampaignError(
            f"{name} must be a lowercase 64-digit SHA-256 digest"
        )
    return value


def _vector(value: object, name: str) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise HurstAffineCampaignError(f"{name} must be a four-integer array")
    result = tuple(
        _plain_int(item, f"{name}[{index}]")
        for index, item in enumerate(value)
    )
    return result  # type: ignore[return-value]


def _load_control(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except CampaignIOError as exc:
        raise HurstAffineCampaignError(str(exc)) from exc
    if not isinstance(value, dict):
        raise HurstAffineCampaignError(f"control artifact must be an object: {path}")
    return value


def _read_bounded(path: Path, maximum: int, label: str) -> bytes:
    try:
        return read_bytes_once(path, limit=maximum)
    except CampaignIOError as exc:
        raise HurstAffineCampaignError(f"cannot read {label}: {exc}") from exc


def _load_receipt_bytes(raw: bytes, label: str) -> dict[str, Any]:
    if len(raw) > MAX_RECEIPT_BYTES:
        raise HurstAffineCampaignError("runner receipt exceeds the byte limit")
    try:
        value = load_decimal_json_bytes(raw, label=label)
    except EvidenceError as exc:
        raise HurstAffineCampaignError(str(exc)) from exc
    if not isinstance(value, dict):
        raise HurstAffineCampaignError("runner receipt must be an object")
    return value


def _validate_upstream_manifest(raw: bytes) -> None:
    try:
        value = parse_json_bytes(raw, label="upstream manifest")
    except CampaignIOError as exc:
        raise HurstAffineCampaignError(
            "upstream manifest is not valid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise HurstAffineCampaignError("upstream manifest must be an object")
    if value.get("kind") != "sparkinterval.pinned_upstream_source.v1":
        raise HurstAffineCampaignError("unexpected upstream manifest kind")
    if value.get("commit") != UPSTREAM_COMMIT:
        raise HurstAffineCampaignError(
            "upstream manifest has the wrong pinned commit"
        )
    files = value.get("files")
    if not isinstance(files, list) or not files:
        raise HurstAffineCampaignError("upstream manifest has no pinned files")
    for index, item in enumerate(files):
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "sha256", "size_bytes"}
            or not isinstance(item["path"], str)
            or not item["path"]
        ):
            raise HurstAffineCampaignError(
                f"upstream manifest file {index} is malformed"
            )
        _digest(item["sha256"], "upstream file digest")
        _plain_int(item["size_bytes"], "upstream file size", minimum=1)


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
    """Create the literal gap-free half-open affine campaign plan."""

    upper = _plain_int(domain_upper_exclusive, "domain upper", minimum=2)
    span = _plain_int(shard_span, "shard span", minimum=1)
    if upper > SOURCE_UPPER_EXCLUSIVE:
        raise HurstAffineCampaignError("campaign exceeds the source endpoint")
    full = upper == SOURCE_UPPER_EXCLUSIVE
    if not full and not allow_bounded_test:
        raise HurstAffineCampaignError(
            "a shortened domain requires explicit allow_bounded_test=True"
        )
    if full and span > MAX_FULL_SOURCE_SHARD_SPAN:
        raise HurstAffineCampaignError(
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
        raise HurstAffineCampaignError(str(exc)) from exc


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
        "classification": (
            "external_finite_computation_not_attestation_or_lean_proof"
        ),
        "strategy": "one_pass_exact_affine_guards",
        "mode": "full_source" if full else "bounded_test",
        "domain_lower": plan.domain_lower,
        "domain_upper_exclusive": plan.domain_upper,
        "shard_span": shard_span,
        "shard_count": len(plan.shards),
        "segment_size": segment_size,
        "state_components": list(STATE_COMPONENTS),
        "atom_profiles": list(ATOM_PROFILES),
        "root_state": [0, 0, 0, 0],
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
) -> HurstAffineCampaignResult:
    """Capture immutable binary/source identities and the fixed affine plan."""

    span = _plain_int(shard_span, "shard span", minimum=1)
    segment = _plain_int(segment_size, "segment size", minimum=MIN_SEGMENT_SIZE)
    if segment > MAX_SEGMENT_SIZE:
        raise HurstAffineCampaignError("segment size exceeds the runner limit")
    runner_raw = _read_bounded(runner, MAX_RUNNER_BYTES, "runner")
    source_raw = _read_bounded(runner_source, MAX_SOURCE_BYTES, "runner source")
    upstream_raw = _read_bounded(
        upstream_manifest, MAX_SOURCE_BYTES, "upstream manifest"
    )
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
        raise HurstAffineCampaignError("campaign output path is not a directory")
    output_directory.mkdir(parents=True, exist_ok=True)
    try:
        with advisory_lock(output_directory / LOCK_NAME):
            captures = (
                (CAPTURED_RUNNER_NAME, runner_raw),
                (CAPTURED_SOURCE_NAME, source_raw),
                (CAPTURED_UPSTREAM_NAME, upstream_raw),
            )
            control_paths = (
                output_directory / CONFIG_NAME,
                output_directory / PLAN_NAME,
            )
            any_existing = any(
                (output_directory / name).exists() for name, _ in captures
            ) or any(path.exists() for path in control_paths)
            if any_existing:
                expected = [
                    *(output_directory / name for name, _ in captures),
                    *control_paths,
                ]
                if not all(path.is_file() for path in expected):
                    raise HurstAffineCampaignError(
                        "affine campaign initialization is partial"
                    )
                for name, raw in captures:
                    if (
                        _read_bounded(
                            output_directory / name, max(len(raw), 1), name
                        )
                        != raw
                    ):
                        raise HurstAffineCampaignError(
                            f"captured identity changed: {name}"
                        )
                if _load_control(output_directory / CONFIG_NAME) != config:
                    raise HurstAffineCampaignError(
                        "affine resume configuration changed"
                    )
                if _load_control(output_directory / PLAN_NAME) != plan.to_dict():
                    raise HurstAffineCampaignError("fixed affine plan changed")
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
                raise HurstAffineCampaignError(
                    f"cannot make captured runner executable: {exc}"
                ) from exc
            return _verify_campaign_unlocked(output_directory)
    except CampaignIOError as exc:
        raise HurstAffineCampaignError(str(exc)) from exc


def _validate_loaded_setup(
    output_directory: Path,
) -> tuple[dict[str, Any], FixedShardPlan]:
    config = _load_control(output_directory / CONFIG_NAME)
    placeholder = FixedShardPlan.from_ranges(
        algorithm="placeholder", state_dimension=4, ranges=((1, 2),)
    )
    expected_fields = set(
        _expected_config(
            plan=placeholder,
            shard_span=1,
            segment_size=MIN_SEGMENT_SIZE,
            runner_sha256="0" * 64,
            runner_size=1,
            source_sha256="0" * 64,
            source_size=1,
            upstream_manifest_sha256="0" * 64,
        )
    )
    if set(config) != expected_fields:
        raise HurstAffineCampaignError("affine campaign config fields changed")
    if (
        config.get("schema") != CAMPAIGN_SCHEMA
        or config.get("algorithm") != CAMPAIGN_ALGORITHM
        or config.get("runner_algorithm") != RUNNER_ALGORITHM
        or config.get("classification")
        != "external_finite_computation_not_attestation_or_lean_proof"
        or config.get("strategy") != "one_pass_exact_affine_guards"
    ):
        raise HurstAffineCampaignError(
            "unsupported or unsafe affine campaign configuration"
        )
    if (
        config.get("state_components") != list(STATE_COMPONENTS)
        or config.get("atom_profiles") != list(ATOM_PROFILES)
        or config.get("root_state") != [0, 0, 0, 0]
        or config.get("upstream_commit") != UPSTREAM_COMMIT
    ):
        raise HurstAffineCampaignError("affine campaign semantics changed")
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
        raise HurstAffineCampaignError("unknown affine campaign mode")
    if config["domain_lower"] != SOURCE_LOWER or not (
        2 <= config["domain_upper_exclusive"] <= SOURCE_UPPER_EXCLUSIVE
    ):
        raise HurstAffineCampaignError("affine campaign domain is invalid")
    full = config["domain_upper_exclusive"] == SOURCE_UPPER_EXCLUSIVE
    if (mode == "full_source") != full:
        raise HurstAffineCampaignError("campaign mode mislabels its domain")
    if full and config["shard_span"] > MAX_FULL_SOURCE_SHARD_SPAN:
        raise HurstAffineCampaignError(
            "full-source checkpoint span exceeds the reviewed maximum"
        )
    if not MIN_SEGMENT_SIZE <= config["segment_size"] <= MAX_SEGMENT_SIZE:
        raise HurstAffineCampaignError("segment size exceeds runner limits")
    try:
        plan = FixedShardPlan.from_dict(
            _load_control(output_directory / PLAN_NAME)
        )
    except AffineGuardCertificateError as exc:
        raise HurstAffineCampaignError(f"invalid affine plan: {exc}") from exc
    if (
        plan.plan_sha256 != config["plan_sha256"]
        or plan.state_dimension != 4
        or (
            plan.domain_lower,
            plan.domain_upper,
            len(plan.shards),
        )
        != (
            config["domain_lower"],
            config["domain_upper_exclusive"],
            config["shard_count"],
        )
    ):
        raise HurstAffineCampaignError(
            "affine plan differs from its configuration"
        )
    expected_identity = _plan_algorithm_identity(
        runner_sha256=config["captured_runner_sha256"],
        source_sha256=config["captured_source_sha256"],
        upstream_manifest_sha256=config["upstream_manifest_sha256"],
    )
    if plan.algorithm != expected_identity:
        raise HurstAffineCampaignError(
            "affine plan is not bound to captured identities"
        )
    for path, digest_name, size_name, maximum in (
        (
            output_directory / CAPTURED_RUNNER_NAME,
            "captured_runner_sha256",
            "captured_runner_size",
            MAX_RUNNER_BYTES,
        ),
        (
            output_directory / CAPTURED_SOURCE_NAME,
            "captured_source_sha256",
            "captured_source_size",
            MAX_SOURCE_BYTES,
        ),
    ):
        try:
            digest, size = hash_file_once(path, limit=maximum)
        except CampaignIOError as exc:
            raise HurstAffineCampaignError(str(exc)) from exc
        if (digest, size) != (config[digest_name], config[size_name]):
            raise HurstAffineCampaignError(
                f"captured file identity changed: {path.name}"
            )
    upstream_raw = _read_bounded(
        output_directory / CAPTURED_UPSTREAM_NAME,
        MAX_SOURCE_BYTES,
        "captured upstream manifest",
    )
    _validate_upstream_manifest(upstream_raw)
    if sha256_bytes(upstream_raw) != config["upstream_manifest_sha256"]:
        raise HurstAffineCampaignError(
            "captured upstream manifest identity changed"
        )
    return config, plan


def _validate_state(state: Sequence[int], name: str) -> tuple[int, int, int, int]:
    vector = tuple(state)
    if len(vector) != 4 or any(type(value) is not int for value in vector):
        raise HurstAffineCampaignError(f"{name} must have four integer coordinates")
    if not SIGNED_I64_LOWER <= vector[0] <= SIGNED_I64_UPPER:
        raise HurstAffineCampaignError(f"{name} M coordinate exceeds int64")
    if not 0 <= vector[1] <= SOURCE_UPPER_EXCLUSIVE - SOURCE_LOWER:
        raise HurstAffineCampaignError(f"{name} Q coordinate is outside source bounds")
    if any(
        not SIGNED_I128_LOWER <= value <= SIGNED_I128_UPPER
        for value in vector
    ):
        raise HurstAffineCampaignError(f"{name} exceeds signed 128-bit range")
    if vector[2] > vector[3]:
        raise HurstAffineCampaignError(
            f"{name} little-Mertens interval is reversed"
        )
    return vector  # type: ignore[return-value]


def _validate_witness_position(
    *,
    atom: str,
    side: str,
    n: int,
    shard_lower: int,
    shard_upper: int,
) -> None:
    if side == "none":
        if n != 0:
            raise HurstAffineCampaignError(
                f"{atom} absent witness must use n=0"
            )
        return
    if atom == "mertens-hurst":
        valid = (
            side == "integer"
            and max(shard_lower, 33) <= n < shard_upper
        )
    elif atom == "cdem-squarefree":
        if side == "integer":
            valid = max(shard_lower, 9_243) <= n < shard_upper
        else:
            valid = (
                side == "right_limit"
                and max(shard_lower + 1, 9_244) <= n <= shard_upper
                and n <= SOURCE_UPPER_EXCLUSIVE - 1
            )
    elif atom == "platt-little-mertens-2-11":
        valid = (
            side == "right_limit"
            and max(shard_lower, 1) <= n <= min(shard_upper, 10**12)
        )
    else:
        # platt-little-mertens-stronger.  The upper endpoint 7_727_068_587 is
        # EXCLUSIVE: the closed statement is false there, so the last row that
        # carries a stronger-range witness is 7_727_068_586, guarding the right
        # endpoint 7_727_068_587.  See TGComputeContracts.HurstV2 and
        # reference/tg_hurst_residual_shard.cpp.
        valid = (
            side == "right_limit"
            and max(shard_lower, 3) <= n
            <= min(shard_upper, 7_727_068_586)
        )
    if not valid:
        raise HurstAffineCampaignError(
            f"{atom} {side} witness is outside its shard/source regime"
        )


def _validate_atom_guard(
    atom: str,
    raw: object,
    *,
    shard_lower: int,
    shard_upper: int,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    if (
        not isinstance(raw, dict)
        or set(raw) != {"lower", "upper", "witnesses"}
    ):
        raise HurstAffineCampaignError(f"affine guard for {atom} is malformed")
    lower = _vector(raw["lower"], f"{atom} lower guard")
    upper = _vector(raw["upper"], f"{atom} upper guard")
    for coordinate, (lo, hi) in enumerate(zip(lower, upper, strict=True)):
        if (
            not SIGNED_I128_LOWER <= lo <= SIGNED_I128_UPPER
            or not SIGNED_I128_LOWER <= hi <= SIGNED_I128_UPPER
            or lo > hi
        ):
            raise HurstAffineCampaignError(
                f"{atom} guard coordinate {coordinate} is invalid"
            )
    active = _ACTIVE_COMPONENTS[atom]
    for coordinate in range(4):
        if coordinate not in active and (
            lower[coordinate] != _WIDE_LOWER[coordinate]
            or upper[coordinate] != _WIDE_UPPER[coordinate]
        ):
            raise HurstAffineCampaignError(
                f"{atom} unexpectedly constrains state component {coordinate}"
            )
        if coordinate in active and (
            lower[coordinate] < _WIDE_LOWER[coordinate]
            or upper[coordinate] > _WIDE_UPPER[coordinate]
        ):
            raise HurstAffineCampaignError(
                f"{atom} active guard exceeds the reviewed wide sentinel"
            )
    witnesses = raw["witnesses"]
    if not isinstance(witnesses, list) or len(witnesses) != len(active):
        raise HurstAffineCampaignError(
            f"{atom} guard has the wrong witness arity"
        )
    for expected_component, witness in zip(active, witnesses, strict=True):
        fields = {
            "component",
            "lower_n",
            "lower_side",
            "upper_n",
            "upper_side",
        }
        if not isinstance(witness, dict) or set(witness) != fields:
            raise HurstAffineCampaignError(
                f"{atom} witness for component {expected_component} is malformed"
            )
        if witness["component"] != expected_component:
            raise HurstAffineCampaignError(
                f"{atom} witness component order changed"
            )
        for bound_name, sentinel in (
            ("lower", _WIDE_LOWER[expected_component]),
            ("upper", _WIDE_UPPER[expected_component]),
        ):
            side = witness[f"{bound_name}_side"]
            n = witness[f"{bound_name}_n"]
            if not isinstance(side, str) or side not in _ALLOWED_SIDES[atom]:
                raise HurstAffineCampaignError(
                    f"{atom} {bound_name} witness side changed"
                )
            _plain_int(n, f"{atom} {bound_name} witness n", minimum=0)
            _validate_witness_position(
                atom=atom,
                side=side,
                n=n,
                shard_lower=shard_lower,
                shard_upper=shard_upper,
            )
            if side == "none" and (
                (lower if bound_name == "lower" else upper)[
                    expected_component
                ]
                != sentinel
            ):
                raise HurstAffineCampaignError(
                    f"{atom} missing {bound_name} witness for a tightened guard"
                )
    return lower, upper


def validate_affine_runner_receipt(
    report: Mapping[str, Any],
    *,
    shard_lower: int,
    shard_upper: int,
    segment_size: int,
) -> tuple[int, int, int, int]:
    """Strictly validate one exact affine-mode worker receipt."""

    if not isinstance(report, Mapping) or set(report) != _RECEIPT_FIELDS:
        actual = set(report) if isinstance(report, Mapping) else set()
        raise HurstAffineCampaignError(
            "affine runner receipt fields changed; "
            f"missing={sorted(_RECEIPT_FIELDS - actual)}, "
            f"extra={sorted(actual - _RECEIPT_FIELDS)}"
        )
    if (
        report.get("algorithm") != RUNNER_ALGORITHM
        or report.get("mode") != "affine"
        or report.get("classification") != RUNNER_CLASSIFICATION
        or report.get("upstream_commit") != UPSTREAM_COMMIT
    ):
        raise HurstAffineCampaignError(
            "affine runner identity, mode, or classification changed"
        )
    if (
        report.get("lower"),
        report.get("upper_exclusive"),
        report.get("work_count"),
        report.get("segment_size"),
    ) != (
        shard_lower,
        shard_upper,
        shard_upper - shard_lower,
        segment_size,
    ):
        raise HurstAffineCampaignError(
            "affine receipt range/config differs from the plan"
        )
    expected_segments = (
        shard_upper - shard_lower + segment_size - 1
    ) // segment_size
    if report.get("segments") != expected_segments:
        raise HurstAffineCampaignError(
            "affine receipt has the wrong segment count"
        )
    if (
        report.get("row_encoding") != "mu-plus-one-block-sha256-v1"
        or report.get("squarefree_threshold_endpoint_policy")
        != "inclusive-value-and-right-limit-v2"
        or report.get("reduction_block_rows") != 1_048_576
        or report.get("state_components") != list(STATE_COMPONENTS)
    ):
        raise HurstAffineCampaignError(
            "affine receipt arithmetic/encoding semantics changed"
        )
    _digest(report.get("row_sha256"), "row_sha256")
    delta = _vector(report.get("delta"), "delta")
    work_count = shard_upper - shard_lower
    if not -work_count <= delta[0] <= work_count:
        raise HurstAffineCampaignError("Mertens delta exceeds its row count")
    if not 0 <= delta[1] <= work_count:
        raise HurstAffineCampaignError("squarefree delta exceeds its row count")
    if any(
        not SIGNED_I128_LOWER <= coordinate <= SIGNED_I128_UPPER
        for coordinate in delta
    ):
        raise HurstAffineCampaignError("affine delta exceeds signed 128-bit range")
    if delta[2] > delta[3]:
        raise HurstAffineCampaignError(
            "little-Mertens directed delta is reversed"
        )
    guards = report.get("guards")
    if not isinstance(guards, dict) or set(guards) != set(ATOM_PROFILES):
        raise HurstAffineCampaignError("affine receipt atom guard set changed")
    for atom in ATOM_PROFILES:
        _validate_atom_guard(
            atom,
            guards[atom],
            shard_lower=shard_lower,
            shard_upper=shard_upper,
        )
    fallbacks = report.get("exact_fallbacks")
    if (
        not isinstance(fallbacks, dict)
        or set(fallbacks) != EXACT_FALLBACK_FIELDS
        or any(type(value) is not int or value != 0 for value in fallbacks.values())
    ):
        raise HurstAffineCampaignError(
            "affine guard production must not report verify fallback counters"
        )
    elapsed = report.get("elapsed_seconds")
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, Decimal))
        or elapsed < 0
    ):
        raise HurstAffineCampaignError(
            "elapsed_seconds must be a nonnegative decimal"
        )
    if (
        report.get("accepted") is not True
        or report.get("execution_attested") is not False
        or report.get("lean_atom_discharged") is not False
    ):
        raise HurstAffineCampaignError(
            "affine runner rejected or made an unsafe boundary claim"
        )
    return delta


def _receipt_paths(output_directory: Path) -> dict[int, Path]:
    directory = output_directory / RECEIPT_DIRECTORY
    if not directory.exists():
        return {}
    if not directory.is_dir():
        raise HurstAffineCampaignError(
            "affine receipt path is not a directory"
        )
    indexed: dict[int, Path] = {}
    for path in directory.iterdir():
        if path.name.startswith(".") and path.name.endswith(".lock"):
            target_name = path.name[1:-5]
            if (
                _RECEIPT_NAME.fullmatch(target_name) is not None
                and path.is_file()
                and (directory / target_name).is_file()
            ):
                continue
            raise HurstAffineCampaignError(
                f"orphan or malformed affine receipt lock {path.name!r}"
            )
        match = _RECEIPT_NAME.fullmatch(path.name)
        if match is None or not path.is_file():
            raise HurstAffineCampaignError(
                f"malformed affine receipt path {path.name!r}"
            )
        index = int(match.group(1))
        if index in indexed:
            raise HurstAffineCampaignError(
                f"duplicate affine receipt index {index}"
            )
        indexed[index] = path
    return indexed


def _load_receipts(
    output_directory: Path,
    config: Mapping[str, Any],
    plan: FixedShardPlan,
) -> dict[int, tuple[dict[str, Any], bytes]]:
    result: dict[int, tuple[dict[str, Any], bytes]] = {}
    for index, path in _receipt_paths(output_directory).items():
        if index >= len(plan.shards):
            raise HurstAffineCampaignError(
                "affine receipt index is outside the plan"
            )
        raw = _read_bounded(path, MAX_RECEIPT_BYTES, "affine receipt")
        report = _load_receipt_bytes(raw, str(path))
        shard = plan.shards[index]
        validate_affine_runner_receipt(
            report,
            shard_lower=shard.lower,
            shard_upper=shard.upper,
            segment_size=config["segment_size"],
        )
        result[index] = (report, raw)
    return result


def _require_complete_indices(
    receipts: Mapping[int, object], plan: FixedShardPlan
) -> None:
    wanted = set(range(len(plan.shards)))
    actual = set(receipts)
    if actual != wanted:
        missing = sorted(wanted - actual)
        extra = sorted(actual - wanted)
        preview = missing[:8]
        raise HurstAffineCampaignError(
            "affine receipts are incomplete "
            f"(missing={preview}{'...' if len(missing) > len(preview) else ''}, "
            f"extra={extra})"
        )


def command_for_shard(
    output_directory: Path, *, shard_index: int
) -> tuple[str, ...]:
    """Return the exact affine worker argv for one fixed-plan shard."""

    config, plan = _validate_loaded_setup(output_directory)
    index = _plain_int(shard_index, "shard index", minimum=0)
    if index >= len(plan.shards):
        raise HurstAffineCampaignError("shard index is outside the fixed plan")
    shard = plan.shards[index]
    return (
        str((output_directory / CAPTURED_RUNNER_NAME).resolve()),
        "--lower",
        str(shard.lower),
        "--upper",
        str(shard.upper - 1),
        "--segment-size",
        str(config["segment_size"]),
        "--mode",
        "affine",
    )


def grouped_shard_indices(
    output_directory: Path, *, group_index: int, group_count: int
) -> tuple[int, ...]:
    """Partition the exact leaf plan into disjoint strided worker groups."""

    _, plan = _validate_loaded_setup(output_directory)
    count = _plain_int(group_count, "worker group count", minimum=1)
    index = _plain_int(group_index, "worker group index", minimum=0)
    if count > len(plan.shards):
        raise HurstAffineCampaignError(
            "worker group count cannot exceed the shard count"
        )
    if index >= count:
        raise HurstAffineCampaignError(
            "worker group index is outside the group count"
        )
    return tuple(range(index, len(plan.shards), count))


def _retain_receipt_unlocked(
    output_directory: Path,
    *,
    index: int,
    raw: bytes,
    config: Mapping[str, Any],
    plan: FixedShardPlan,
) -> None:
    report = _load_receipt_bytes(raw, f"incoming affine receipt {index}")
    shard = plan.shards[index]
    validate_affine_runner_receipt(
        report,
        shard_lower=shard.lower,
        shard_upper=shard.upper,
        segment_size=config["segment_size"],
    )
    directory = output_directory / RECEIPT_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"receipt-{index:08d}.json"
    if destination.exists():
        existing = _read_bounded(
            destination, MAX_RECEIPT_BYTES, "retained affine receipt"
        )
        if existing != raw:
            raise HurstAffineCampaignError(
                "refusing to replace a retained affine receipt"
            )
        return
    atomic_write_bytes(destination, raw)


def ingest_receipt(
    output_directory: Path,
    *,
    shard_index: int,
    receipt_path: Path,
) -> HurstAffineCampaignResult:
    """Strictly ingest one externally executed affine receipt."""

    raw = _read_bounded(receipt_path, MAX_RECEIPT_BYTES, "incoming receipt")
    try:
        with advisory_lock(output_directory / LOCK_NAME):
            config, plan = _validate_loaded_setup(output_directory)
            index = _plain_int(shard_index, "shard index", minimum=0)
            if index >= len(plan.shards):
                raise HurstAffineCampaignError(
                    "shard index is outside the fixed plan"
                )
            _retain_receipt_unlocked(
                output_directory,
                index=index,
                raw=raw,
                config=config,
                plan=plan,
            )
            return _verify_campaign_unlocked(output_directory)
    except CampaignIOError as exc:
        raise HurstAffineCampaignError(str(exc)) from exc


def run_shards(
    output_directory: Path,
    *,
    shard_indices: Sequence[int] | None = None,
    max_shards: int | None = None,
    workers: int = DEFAULT_LOCAL_WORKERS,
    runner_threads: int | None = None,
    timeout_seconds: int | None = None,
) -> HurstAffineCampaignResult:
    """Run missing affine shards with bounded process/thread parallelism."""

    worker_count = _plain_int(workers, "workers", minimum=1)
    runner_thread_count = (
        None
        if runner_threads is None
        else _plain_int(runner_threads, "runner threads", minimum=1)
    )
    if runner_thread_count is None and worker_count > 1:
        runner_thread_count = 1
    if max_shards is not None:
        _plain_int(max_shards, "max shards", minimum=1)
    if timeout_seconds is not None:
        _plain_int(timeout_seconds, "timeout seconds", minimum=1)
    try:
        with advisory_lock(output_directory / LOCK_NAME):
            config, plan = _validate_loaded_setup(output_directory)
            existing = _receipt_paths(output_directory)
            if shard_indices is None:
                selected = [
                    index
                    for index in range(len(plan.shards))
                    if index not in existing
                ]
            else:
                selected = []
                seen: set[int] = set()
                for raw_index in shard_indices:
                    index = _plain_int(raw_index, "shard index", minimum=0)
                    if index >= len(plan.shards):
                        raise HurstAffineCampaignError(
                            "shard index is outside the fixed plan"
                        )
                    if index in seen:
                        raise HurstAffineCampaignError(
                            "duplicate requested shard index"
                        )
                    seen.add(index)
                    if index not in existing:
                        selected.append(index)
            if max_shards is not None:
                selected = selected[:max_shards]
            commands = {
                index: (
                    str((output_directory / CAPTURED_RUNNER_NAME).resolve()),
                    "--lower",
                    str(plan.shards[index].lower),
                    "--upper",
                    str(plan.shards[index].upper - 1),
                    "--segment-size",
                    str(config["segment_size"]),
                    "--mode",
                    "affine",
                )
                for index in selected
            }
        if not selected:
            return verify_campaign(output_directory)
        effective_workers = min(worker_count, len(selected))
        if runner_thread_count is None:
            worker_places: tuple[tuple[int, ...] | None, ...] = (None,)
        else:
            try:
                available = tuple(sorted(os.sched_getaffinity(0)))
            except (AttributeError, OSError) as exc:
                raise HurstAffineCampaignError(
                    "explicit runner threads require CPU-affinity discovery"
                ) from exc
            required = effective_workers * runner_thread_count
            if required > len(available):
                raise HurstAffineCampaignError(
                    "workers times runner threads exceeds available CPU affinity"
                )
            worker_places = tuple(
                available[
                    slot * runner_thread_count : (slot + 1) * runner_thread_count
                ]
                for slot in range(effective_workers)
            )
        cancel_event = threading.Event()

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
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            for slot in range(effective_workers):
                index = next(iterator, None)
                if index is None:
                    break
                pending[submit_one(executor, index, slot)] = (index, slot)
            while pending:
                completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in completed:
                    index, slot = pending.pop(future)
                    try:
                        raw = future.result()
                        with advisory_lock(output_directory / LOCK_NAME):
                            checked_config, checked_plan = _validate_loaded_setup(
                                output_directory
                            )
                            if (
                                checked_config != config
                                or checked_plan != plan
                            ):
                                raise HurstAffineCampaignError(
                                    "campaign setup changed during execution"
                                )
                            _retain_receipt_unlocked(
                                output_directory,
                                index=index,
                                raw=raw,
                                config=config,
                                plan=plan,
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
        raise HurstAffineCampaignError(str(exc)) from exc


def _guard_vectors(
    report: Mapping[str, Any], atom: str
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    guard = report["guards"][atom]
    return (
        _vector(guard["lower"], f"{atom} lower guard"),
        _vector(guard["upper"], f"{atom} upper guard"),
    )


def _accepts(
    state: Sequence[int],
    lower: Sequence[int],
    upper: Sequence[int],
) -> bool:
    return all(
        lo <= value <= hi
        for value, lo, hi in zip(state, lower, upper, strict=True)
    )


def _intersect_guards(
    report: Mapping[str, Any],
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    pairs = [_guard_vectors(report, atom) for atom in ATOM_PROFILES]
    lower = tuple(max(pair[0][coordinate] for pair in pairs) for coordinate in range(4))
    upper = tuple(min(pair[1][coordinate] for pair in pairs) for coordinate in range(4))
    if any(lo > hi for lo, hi in zip(lower, upper, strict=True)):
        raise HurstAffineCampaignError(
            "intersection of the four affine guards is empty"
        )
    return lower, upper  # type: ignore[return-value]


def _add_state(
    state: Sequence[int], delta: Sequence[int], name: str
) -> tuple[int, int, int, int]:
    return _validate_state(
        tuple(left + right for left, right in zip(state, delta, strict=True)),
        name,
    )


def _build_replay(
    config: Mapping[str, Any],
    plan: FixedShardPlan,
    receipts: Mapping[int, tuple[dict[str, Any], bytes]],
) -> tuple[dict[str, Any], tuple[AffineGuardLeaf, ...], dict[str, Any]]:
    _require_complete_indices(receipts, plan)
    current = _validate_state((0, 0, 0, 0), "root state")
    entries: list[dict[str, Any]] = []
    leaves: list[AffineGuardLeaf] = []
    receipt_index: list[dict[str, Any]] = []
    for index, shard in enumerate(plan.shards):
        report, raw = receipts[index]
        delta = _vector(report["delta"], "affine delta")
        atom_guard_hashes: dict[str, str] = {}
        for atom in ATOM_PROFILES:
            lower, upper = _guard_vectors(report, atom)
            if not _accepts(current, lower, upper):
                raise HurstAffineCampaignError(
                    f"root-derived incoming state violates {atom} guard "
                    f"at shard {index}"
                )
            atom_guard_hashes[atom] = canonical_sha256(report["guards"][atom])
        combined_lower, combined_upper = _intersect_guards(report)
        transition = AffineGuardTransition(
            delta=delta,
            lower_guard=combined_lower,
            upper_guard=combined_upper,
        )
        # These are structural witnesses for the generic guard/Merkle format.
        # The worker's algorithm-specific witnesses remain in the raw receipt;
        # this encoding does not claim to replay their row facts.
        lower_witnesses = tuple(
            TightGuardWitness(
                row_index=shard.lower,
                prefix_delta=0,
                row_guard=value,
            )
            for value in combined_lower
        )
        upper_witnesses = tuple(
            TightGuardWitness(
                row_index=shard.lower,
                prefix_delta=0,
                row_guard=value,
            )
            for value in combined_upper
        )
        leaf = make_affine_guard_leaf(
            plan=plan,
            shard_index=index,
            row_root_sha256=report["row_sha256"],
            transition=transition,
            lower_tight_witnesses=lower_witnesses,
            upper_tight_witnesses=upper_witnesses,
            exception_root_sha256=EMPTY_EXCEPTION_ROOT_SHA256,
        )
        outgoing = _add_state(current, delta, f"outgoing state for shard {index}")
        receipt_sha = sha256_bytes(raw)
        entries.append(
            {
                "index": index,
                "lower": shard.lower,
                "upper": shard.upper,
                "receipt_sha256": receipt_sha,
                "row_sha256": report["row_sha256"],
                "delta": list(delta),
                "incoming": list(current),
                "outgoing": list(outgoing),
                "atom_guard_sha256": atom_guard_hashes,
                "combined_lower_guard": list(combined_lower),
                "combined_upper_guard": list(combined_upper),
                "all_atom_guards_accept": True,
                "leaf_sha256": leaf.leaf_sha256,
            }
        )
        receipt_index.append(
            {
                "index": index,
                "receipt_sha256": receipt_sha,
                "row_sha256": report["row_sha256"],
                "delta": list(delta),
                "guards_sha256": canonical_sha256(report["guards"]),
            }
        )
        leaves.append(leaf)
        current = outgoing
    scan = {
        "schema": SCAN_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "config_sha256": canonical_sha256(dict(config)),
        "root_state": [0, 0, 0, 0],
        "entries": entries,
        "final_state": list(current),
    }
    receipt_set = {
        "schema": RECEIPT_SET_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "entries": receipt_index,
    }
    scan["receipt_set_sha256"] = canonical_sha256(receipt_set)
    scan["scan_sha256"] = canonical_sha256(scan)
    try:
        checked = verify_affine_guard_certificate(
            plan=plan,
            root_state=(0, 0, 0, 0),
            leaves=leaves,
        )
    except AffineGuardCertificateError as exc:
        raise HurstAffineCampaignError(
            f"generic affine certificate failed: {exc}"
        ) from exc
    if (
        checked.incoming_states
        != tuple(tuple(entry["incoming"]) for entry in entries)
        or checked.final_state != current
    ):
        raise HurstAffineCampaignError(
            "generic affine scan differs from the algorithm-specific scan"
        )
    full = config["mode"] == "full_source"
    leaf_bundle = {
        "schema": LEAF_BUNDLE_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "leaf_count": len(leaves),
        "leaves": [leaf.to_dict() for leaf in leaves],
    }
    final = {
        "schema": FINAL_SCHEMA,
        "algorithm": CAMPAIGN_ALGORITHM,
        "classification": CLASSIFICATION,
        "certificate_scope": "one_common_certificate_for_all_four_atom_profiles",
        "guard_encoding": "worker_exact_per_atom_intersection_v1",
        "generic_tight_witness_semantics": (
            "structural_guard_encoding_only_not_algorithm_specific_row_replay"
        ),
        "atom_profiles": list(ATOM_PROFILES),
        "plan_sha256": plan.plan_sha256,
        "config_sha256": canonical_sha256(dict(config)),
        "runner_sha256": config["captured_runner_sha256"],
        "source_sha256": config["captured_source_sha256"],
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_manifest_sha256": config["upstream_manifest_sha256"],
        "scan_sha256": scan["scan_sha256"],
        "receipt_set_sha256": scan["receipt_set_sha256"],
        "leaf_bundle_sha256": canonical_sha256(leaf_bundle),
        "exact_shard_coverage": True,
        "full_source_range": full,
        "all_root_derived_inputs_in_all_atom_guards": True,
        "row_commitments_retained": True,
        "worker_affine_guards_retained": True,
        "source_rows_replayed_independently": False,
        "physical_row_realization_pending": True,
        "execution_attested": False,
        "lean_atoms_discharged": False,
        "implication_scope": (
            "conditional_on_each_retained_worker_receipt_realizing_its_committed_"
            "mobius_rows_deltas_and_exact_per_atom_guards"
        ),
        "generic_affine_certificate": checked.to_dict(),
    }
    return scan, tuple(leaves), final


def _leaf_bundle(
    plan: FixedShardPlan, leaves: Sequence[AffineGuardLeaf]
) -> dict[str, Any]:
    return {
        "schema": LEAF_BUNDLE_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "leaf_count": len(leaves),
        "leaves": [leaf.to_dict() for leaf in leaves],
    }


def finalize_campaign(output_directory: Path) -> HurstAffineCampaignResult:
    """Build the one-pass scan, generic leaves, and conditional certificate."""

    try:
        with advisory_lock(output_directory / LOCK_NAME):
            config, plan = _validate_loaded_setup(output_directory)
            receipts = _load_receipts(output_directory, config, plan)
            scan, leaves, final = _build_replay(config, plan, receipts)
            write_immutable_json(output_directory / SCAN_NAME, scan)
            write_immutable_json(
                output_directory / LEAF_BUNDLE_NAME,
                _leaf_bundle(plan, leaves),
            )
            write_immutable_json(output_directory / FINAL_NAME, final)
            return _verify_campaign_unlocked(output_directory)
    except (CampaignIOError, AffineGuardCertificateError) as exc:
        raise HurstAffineCampaignError(str(exc)) from exc


def _verify_final(
    output_directory: Path,
    config: Mapping[str, Any],
    plan: FixedShardPlan,
    receipts: Mapping[int, tuple[dict[str, Any], bytes]],
) -> tuple[str, tuple[int, int, int, int]]:
    expected_scan, expected_leaves, expected_final = _build_replay(
        config, plan, receipts
    )
    if _load_control(output_directory / SCAN_NAME) != expected_scan:
        raise HurstAffineCampaignError(
            "affine scan differs from independent receipt replay"
        )
    bundle = _load_control(output_directory / LEAF_BUNDLE_NAME)
    expected_bundle = _leaf_bundle(plan, expected_leaves)
    if bundle != expected_bundle:
        raise HurstAffineCampaignError(
            "affine leaf bundle differs from independent replay"
        )
    if _load_control(output_directory / FINAL_NAME) != expected_final:
        raise HurstAffineCampaignError(
            "final affine certificate differs from independent replay"
        )
    generic = expected_final["generic_affine_certificate"]
    return (
        _digest(generic["certificate_root_sha256"], "certificate root"),
        _validate_state(generic["final_state"], "final state"),
    )


def _verify_campaign_unlocked(
    output_directory: Path,
) -> HurstAffineCampaignResult:
    config, plan = _validate_loaded_setup(output_directory)
    receipts = _load_receipts(output_directory, config, plan)
    final_path = output_directory / FINAL_NAME
    scan_path = output_directory / SCAN_NAME
    leaf_bundle_path = output_directory / LEAF_BUNDLE_NAME
    complete = final_path.is_file()
    if not complete and (scan_path.exists() or leaf_bundle_path.exists()):
        raise HurstAffineCampaignError(
            "affine finalization artifacts are partial; rerun finalize"
        )
    certificate_root = None
    final_state = None
    if complete:
        if not scan_path.is_file():
            raise HurstAffineCampaignError(
                "final affine certificate has no scan artifact"
            )
        if not leaf_bundle_path.is_file():
            raise HurstAffineCampaignError(
                "final affine certificate has no leaf bundle"
            )
        _require_complete_indices(receipts, plan)
        certificate_root, final_state = _verify_final(
            output_directory, config, plan, receipts
        )
    full = config["mode"] == "full_source"
    return HurstAffineCampaignResult(
        mode=config["mode"],
        plan_sha256=plan.plan_sha256,
        shard_count=len(plan.shards),
        affine_receipts=len(receipts),
        complete=complete,
        full_source_range=full,
        certificate_root_sha256=certificate_root,
        final_state=final_state,
        all_root_derived_inputs_in_all_atom_guards=complete,
        runner_sha256=config["captured_runner_sha256"],
        source_sha256=config["captured_source_sha256"],
        upstream_commit=UPSTREAM_COMMIT,
    )


def verify_campaign(output_directory: Path) -> HurstAffineCampaignResult:
    """Independently replay every retained one-pass certificate relationship."""

    try:
        with advisory_lock(output_directory / LOCK_NAME):
            return _verify_campaign_unlocked(output_directory)
    except (CampaignIOError, AffineGuardCertificateError) as exc:
        raise HurstAffineCampaignError(str(exc)) from exc


def verify_campaign_readonly(
    output_directory: Path,
) -> HurstAffineCampaignResult:
    """Replay an immutable/read-only extracted campaign without creating a lock.

    Callers must supply a private snapshot that cannot change concurrently,
    such as a freshly extracted content-addressed measured-run archive.
    """

    try:
        return _verify_campaign_unlocked(output_directory)
    except (CampaignIOError, AffineGuardCertificateError) as exc:
        raise HurstAffineCampaignError(str(exc)) from exc


__all__ = [
    "CAMPAIGN_ALGORITHM",
    "CAMPAIGN_SCHEMA",
    "CONFIG_NAME",
    "DEFAULT_LOCAL_WORKERS",
    "DEFAULT_SEGMENT_SIZE",
    "DEFAULT_SHARD_SPAN",
    "DEFAULT_WORKER_GROUPS",
    "FINAL_NAME",
    "HurstAffineCampaignError",
    "HurstAffineCampaignResult",
    "MIN_SEGMENT_SIZE",
    "PLAN_NAME",
    "RECEIPT_DIRECTORY",
    "SOURCE_UPPER_EXCLUSIVE",
    "UPSTREAM_COMMIT",
    "command_for_shard",
    "create_plan",
    "finalize_campaign",
    "grouped_shard_indices",
    "ingest_receipt",
    "initialize_campaign",
    "run_shards",
    "validate_affine_runner_receipt",
    "verify_campaign",
    "verify_campaign_readonly",
]
