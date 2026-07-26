# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Plan-bound receipts for the rigorous C++/MPFR Proposition 12.2.4 runner."""

from __future__ import annotations

import hashlib
import json
from math import isfinite
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping, Sequence

from .affine_guard_certificate import (
    EMPTY_EXCEPTION_ROOT_SHA256,
    AffineGuardLeaf,
    AffineGuardTransition,
    AffineGuardVerification,
    FixedShardPlan,
    TightGuardWitness,
    make_affine_guard_leaf,
    verify_affine_guard_certificate,
)
from .campaign_io import canonical_json_bytes, hash_file_once
from .prop1224_factor_plan import (
    PRODUCTION_LEAF_ROWS,
    PRODUCTION_RANK_END,
    make_factor_plan,
    q_at_rank,
)


RUNNER_ALGORITHM = "prop1224-mpfr-directed-independent-q-shard-v1"
RUNNER_CLASSIFICATION = "directed-external-computation-not-lean-proof"
RECEIPT_SCHEMA = "sparkinterval.tg.prop1224-mpfr-shard-receipt.v1"
PLAN_ALGORITHM_BASE = "prop1224-mpfr-directed-fixed-plan-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_HEX_FLOAT_RE = re.compile(r"^0x[0-9a-f]+(?:\.[0-9a-f]+)?p[+-]?[0-9]+$")
_REPORT_KEYS = frozenset(
    {
        "algorithm",
        "classification",
        "rank_lower",
        "rank_upper",
        "work_count",
        "first_q",
        "next_q",
        "precision_bits",
        "segment_size",
        "empty_q_rows",
        "nonempty_q_rows",
        "r_steps",
        "conservative_k_rows_checked",
        "minimum_margin_lower_hex",
        "row_root_sha256",
        "mpfr_version",
        "elapsed_seconds",
        "rows_per_second",
        "execution_attested",
        "lean_realization_proved",
        "lean_atom_discharged",
    }
)
_ARITHMETIC_REPORT_KEYS = _REPORT_KEYS - {"elapsed_seconds", "rows_per_second"}
_RECEIPT_KEYS = frozenset(
    {
        "receipt_schema",
        "plan_sha256",
        "shard_index",
        "runner_source_sha256",
        "runner_executable_sha256",
        "elapsed_milliseconds",
        "arithmetic_report",
        "receipt_hash",
    }
)


class Prop1224MpfrCampaignError(RuntimeError):
    """An MPFR runner, immutable plan, or receipt failed closed."""


def _runner_source_path() -> Path:
    return Path(__file__).resolve().parents[1] / "reference" / "tg_prop1224_mpfr_shard.cpp"


def runner_source_sha256() -> str:
    return hash_file_once(_runner_source_path())[0]


def make_mpfr_plan(
    *,
    precision_bits: int = 192,
    mpfr_version: str = "4.2.1",
    rank_lower: int = 0,
    rank_upper: int = PRODUCTION_RANK_END,
    leaf_rows: int = PRODUCTION_LEAF_ROWS,
) -> FixedShardPlan:
    """Make a plan whose identity binds arithmetic precision, MPFR, and source."""

    if isinstance(precision_bits, bool) or not isinstance(precision_bits, int):
        raise Prop1224MpfrCampaignError("precision_bits must be an integer")
    if not 128 <= precision_bits <= 4096:
        raise Prop1224MpfrCampaignError("precision_bits must lie in [128,4096]")
    if not isinstance(mpfr_version, str) or re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", mpfr_version) is None:
        raise Prop1224MpfrCampaignError("mpfr_version is malformed")
    shape = make_factor_plan(
        rank_lower=rank_lower,
        rank_upper=rank_upper,
        leaf_rows=leaf_rows,
    )
    algorithm = (
        f"{PLAN_ALGORITHM_BASE}/precision-{precision_bits}/mpfr-{mpfr_version}/"
        f"source-{runner_source_sha256()}"
    )
    return FixedShardPlan.from_ranges(
        algorithm=algorithm,
        state_dimension=1,
        ranges=[(shard.lower, shard.upper) for shard in shape.shards],
    )


def _integer(name: str, value: object, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise Prop1224MpfrCampaignError(f"{name} must be an integer >= {minimum}")
    return value


def validate_runner_report(
    report: Mapping[str, Any],
    *,
    lower: int,
    upper: int,
    precision_bits: int,
    mpfr_version: str,
) -> None:
    if not isinstance(report, Mapping) or set(report) != _REPORT_KEYS:
        raise Prop1224MpfrCampaignError("MPFR runner report has the wrong fields")
    if report.get("algorithm") != RUNNER_ALGORITHM:
        raise Prop1224MpfrCampaignError("MPFR runner algorithm changed")
    if report.get("classification") != RUNNER_CLASSIFICATION:
        raise Prop1224MpfrCampaignError("MPFR runner classification changed")
    expected = {
        "rank_lower": lower,
        "rank_upper": upper,
        "work_count": upper - lower,
        "first_q": q_at_rank(lower),
        "next_q": q_at_rank(upper),
        "precision_bits": precision_bits,
        "mpfr_version": mpfr_version,
        "execution_attested": False,
        "lean_realization_proved": False,
        "lean_atom_discharged": False,
    }
    for name, wanted in expected.items():
        if report.get(name) != wanted:
            raise Prop1224MpfrCampaignError(
                f"MPFR runner {name} changed: expected {wanted!r}, "
                f"found {report.get(name)!r}"
            )
    empty = _integer("empty_q_rows", report.get("empty_q_rows"))
    nonempty = _integer("nonempty_q_rows", report.get("nonempty_q_rows"))
    if empty + nonempty != upper - lower:
        raise Prop1224MpfrCampaignError("MPFR runner did not classify every q row")
    r_steps = _integer("r_steps", report.get("r_steps"))
    k_rows = _integer(
        "conservative_k_rows_checked",
        report.get("conservative_k_rows_checked"),
    )
    if k_rows > r_steps:
        raise Prop1224MpfrCampaignError("MPFR runner checks more k rows than r steps")
    minimum = report.get("minimum_margin_lower_hex")
    if k_rows == 0:
        if minimum is not None:
            raise Prop1224MpfrCampaignError("empty margin report stores a minimum")
    elif not isinstance(minimum, str) or _HEX_FLOAT_RE.fullmatch(minimum) is None:
        raise Prop1224MpfrCampaignError("minimum margin is not canonical positive hex")
    row_root = report.get("row_root_sha256")
    if not isinstance(row_root, str) or _SHA256_RE.fullmatch(row_root) is None:
        raise Prop1224MpfrCampaignError("MPFR row root is malformed")
    _integer("segment_size", report.get("segment_size"), minimum=1)
    for name in ("elapsed_seconds", "rows_per_second"):
        value = report.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise Prop1224MpfrCampaignError(f"{name} is not numeric")
        if not isfinite(float(value)) or value < 0:
            raise Prop1224MpfrCampaignError(f"{name} is negative or nonfinite")


def _normalized_report(report: Mapping[str, Any]) -> dict[str, Any]:
    return {name: report[name] for name in sorted(_ARITHMETIC_REPORT_KEYS)}


def run_mpfr_shard(
    *,
    runner: Path,
    plan: FixedShardPlan,
    shard_index: int,
    precision_bits: int = 192,
    mpfr_version: str = "4.2.1",
    segment_size: int = 250_000,
) -> dict[str, Any]:
    """Run one fixed leaf and return a canonical-JSON-safe receipt."""

    shard_index = _integer("shard_index", shard_index)
    if shard_index >= len(plan.shards):
        raise Prop1224MpfrCampaignError("shard_index is outside the plan")
    shard = plan.shards[shard_index]
    completed = subprocess.run(
        [
            str(runner),
            "--rank-lower",
            str(shard.lower),
            "--rank-upper",
            str(shard.upper),
            "--precision-bits",
            str(precision_bits),
            "--segment-size",
            str(segment_size),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise Prop1224MpfrCampaignError(
            f"MPFR runner failed for shard {shard_index}: {completed.stderr.strip()}"
        )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise Prop1224MpfrCampaignError("MPFR runner emitted invalid JSON") from exc
    validate_runner_report(
        report,
        lower=shard.lower,
        upper=shard.upper,
        precision_bits=precision_bits,
        mpfr_version=mpfr_version,
    )
    runner_sha = hash_file_once(runner.resolve())[0]
    body: dict[str, Any] = {
        "receipt_schema": RECEIPT_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "shard_index": shard_index,
        "runner_source_sha256": runner_source_sha256(),
        "runner_executable_sha256": runner_sha,
        "elapsed_milliseconds": max(0, int(float(report["elapsed_seconds"]) * 1_000)),
        "arithmetic_report": _normalized_report(report),
    }
    return {
        **body,
        "receipt_hash": hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    }


def validate_receipt(
    receipt: Mapping[str, Any],
    *,
    plan: FixedShardPlan,
    precision_bits: int,
    mpfr_version: str,
) -> None:
    if not isinstance(receipt, Mapping) or set(receipt) != _RECEIPT_KEYS:
        raise Prop1224MpfrCampaignError("MPFR receipt has the wrong fields")
    if receipt.get("receipt_schema") != RECEIPT_SCHEMA:
        raise Prop1224MpfrCampaignError("MPFR receipt schema changed")
    if receipt.get("plan_sha256") != plan.plan_sha256:
        raise Prop1224MpfrCampaignError("MPFR receipt is bound to another plan")
    index = _integer("shard_index", receipt.get("shard_index"))
    if index >= len(plan.shards):
        raise Prop1224MpfrCampaignError("MPFR receipt shard is outside the plan")
    for name in ("runner_source_sha256", "runner_executable_sha256", "receipt_hash"):
        value = receipt.get(name)
        if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
            raise Prop1224MpfrCampaignError(f"{name} is malformed")
    if receipt["runner_source_sha256"] != runner_source_sha256():
        raise Prop1224MpfrCampaignError("MPFR runner source changed")
    _integer("elapsed_milliseconds", receipt.get("elapsed_milliseconds"))
    arithmetic = receipt.get("arithmetic_report")
    if not isinstance(arithmetic, Mapping) or set(arithmetic) != _ARITHMETIC_REPORT_KEYS:
        raise Prop1224MpfrCampaignError("receipt arithmetic report has wrong fields")
    synthetic = {**arithmetic, "elapsed_seconds": 0, "rows_per_second": 0}
    shard = plan.shards[index]
    validate_runner_report(
        synthetic,
        lower=shard.lower,
        upper=shard.upper,
        precision_bits=precision_bits,
        mpfr_version=mpfr_version,
    )
    body = {name: receipt[name] for name in receipt if name != "receipt_hash"}
    if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != receipt["receipt_hash"]:
        raise Prop1224MpfrCampaignError("MPFR receipt hash is invalid")


def leaf_from_receipt(
    receipt: Mapping[str, Any],
    *,
    plan: FixedShardPlan,
    precision_bits: int = 192,
    mpfr_version: str = "4.2.1",
) -> AffineGuardLeaf:
    validate_receipt(
        receipt,
        plan=plan,
        precision_bits=precision_bits,
        mpfr_version=mpfr_version,
    )
    index = receipt["shard_index"]
    shard = plan.shards[index]
    transition = AffineGuardTransition(
        delta=(shard.work_count,),
        lower_guard=(shard.lower,),
        upper_guard=(shard.lower,),
    )
    witness = TightGuardWitness(shard.lower, 0, shard.lower)
    return make_affine_guard_leaf(
        plan=plan,
        shard_index=index,
        row_root_sha256=receipt["arithmetic_report"]["row_root_sha256"],
        transition=transition,
        lower_tight_witnesses=(witness,),
        upper_tight_witnesses=(witness,),
        exception_root_sha256=EMPTY_EXCEPTION_ROOT_SHA256,
    )


def verify_receipts(
    receipts: Sequence[Mapping[str, Any]],
    *,
    plan: FixedShardPlan,
    precision_bits: int = 192,
    mpfr_version: str = "4.2.1",
) -> AffineGuardVerification:
    if len(receipts) != len(plan.shards):
        raise Prop1224MpfrCampaignError("MPFR campaign is missing fixed-plan receipts")
    leaves = tuple(
        leaf_from_receipt(
            receipt,
            plan=plan,
            precision_bits=precision_bits,
            mpfr_version=mpfr_version,
        )
        for receipt in receipts
    )
    executable_hashes = {receipt["runner_executable_sha256"] for receipt in receipts}
    if len(executable_hashes) != 1:
        raise Prop1224MpfrCampaignError("MPFR campaign mixed runner executables")
    return verify_affine_guard_certificate(
        plan=plan,
        root_state=(plan.domain_lower,),
        leaves=leaves,
    )


__all__ = [
    "PLAN_ALGORITHM_BASE",
    "Prop1224MpfrCampaignError",
    "RECEIPT_SCHEMA",
    "leaf_from_receipt",
    "make_mpfr_plan",
    "run_mpfr_shard",
    "runner_source_sha256",
    "validate_receipt",
    "validate_runner_report",
    "verify_receipts",
]
