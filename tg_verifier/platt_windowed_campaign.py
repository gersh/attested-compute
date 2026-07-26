# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed campaign for Platt's source windowed Arb/Turing verifier.

This engine covers the expensive interval from ``10^10`` through a grid point
strictly above the PT21 endpoint.  It intentionally does not claim the lower
prefix: a separate accepted prefix artifact is still required before the Lean
finite-RH atom can be discharged.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
from typing import Any


SCHEMA = "sparkinterval.tg.platt-pt21-windowed-campaign.v1"
RECEIPT_SCHEMA = "sparkinterval.tg.platt-pt21-windowed-shard.v1"
FINAL_SCHEMA = "sparkinterval.tg.platt-pt21-windowed-final.v1"
SOURCE_COMMIT = "42b21426718e542daa2b006dc05ea2d7f26426e6"
SOURCE_SET_SHA256 = "9a748490b327b102d53506e390a42afac796a5b42b42060fe82aa8f5744bb152"
SOURCE_LOWER = 10_000_000_000
SOURCE_LOWER_COUNT = 32_130_158_315
SOURCE_HEIGHT = 3_000_175_332_800
SOURCE_COUNT = 12_363_153_437_138
SOURCE_MAXIMUM = 3_010_000_000_000
STEP = 1_008
PRECISION_BITS = 128
DEFAULT_BLOCKS_PER_SHARD = 16_384
FULL_BLOCK_COUNT = (SOURCE_HEIGHT - SOURCE_LOWER + STEP - 1) // STEP
FULL_COVERAGE_UPPER = SOURCE_LOWER + FULL_BLOCK_COUNT * STEP
PLAN_NAME = "campaign.json"
FINAL_NAME = "final.json"
PLAN_DOMAIN = b"sparkinterval/tg/platt-pt21-windowed-plan/v1\0"
RECEIPT_DOMAIN = b"sparkinterval/tg/platt-pt21-windowed-receipt/v1\0"
MERKLE_LEAF_DOMAIN = b"sparkinterval/tg/platt-pt21-windowed-leaf/v1\0"
MERKLE_NODE_DOMAIN = b"sparkinterval/tg/platt-pt21-windowed-node/v1\0"

LOOKING_RE = re.compile(r"^looking for ([0-9]+)-([0-9]+)=([0-9]+) zeros$")
SUCCESS_RE = re.compile(
    r"^All ([0-9]+) zeros found in region "
    r"([0-9]+)\.000000 to ([0-9]+)\.000000 using stat points\.$"
)
FORBIDDEN_OUTPUT = (
    "unknown",
    "missed",
    "problem",
    "failed",
    "exiting",
    "did not bracket",
    "outside limits",
    "must be",
)


class PlattWindowedCampaignError(RuntimeError):
    """A plan, execution, transcript, or aggregate failed closed."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(path: Path) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise PlattWindowedCampaignError(f"not a regular file: {path}")
    raw = path.read_bytes()
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _digest(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + _canonical(value)).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PlattWindowedCampaignError(f"cannot load {path}: {error}") from error
    if not isinstance(value, dict):
        raise PlattWindowedCampaignError(f"JSON object required: {path}")
    return value


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _plan_without_digest(plan: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if key != "plan_sha256"}


def create_plan(
    *,
    runner_sha256: str,
    runner_size: int,
    source_manifest_sha256: str,
    source_manifest_size: int,
    blocks_per_shard: int = DEFAULT_BLOCKS_PER_SHARD,
    block_count: int = FULL_BLOCK_COUNT,
    allow_bounded_test: bool = False,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{64}", runner_sha256):
        raise PlattWindowedCampaignError("runner digest is malformed")
    if not re.fullmatch(r"[0-9a-f]{64}", source_manifest_sha256):
        raise PlattWindowedCampaignError("source manifest digest is malformed")
    if runner_size < 1 or source_manifest_size < 1:
        raise PlattWindowedCampaignError("runner and source manifest must be nonempty")
    if blocks_per_shard < 1 or block_count < 1:
        raise PlattWindowedCampaignError("campaign geometry must be positive")
    if block_count != FULL_BLOCK_COUNT and not allow_bounded_test:
        raise PlattWindowedCampaignError("bounded geometry requires allow_bounded_test")
    coverage_upper = SOURCE_LOWER + block_count * STEP
    if coverage_upper > SOURCE_MAXIMUM:
        raise PlattWindowedCampaignError("campaign exceeds the source parameter maximum")
    shard_count = (block_count + blocks_per_shard - 1) // blocks_per_shard
    plan: dict[str, Any] = {
        "schema": SCHEMA,
        "mode": "full_source_high_range" if block_count == FULL_BLOCK_COUNT else "bounded_test",
        "source": {
            "repository_commit": SOURCE_COMMIT,
            "reviewed_source_sha256": SOURCE_SET_SHA256,
            "manifest_sha256": source_manifest_sha256,
            "manifest_size_bytes": source_manifest_size,
            "license": "NOASSERTION",
            "redistribution": "not-authorized-by-this-manifest",
        },
        "runner": {"sha256": runner_sha256, "size_bytes": runner_size},
        "claim": {
            "source_height": SOURCE_HEIGHT,
            "source_multiplicity_count": SOURCE_COUNT,
            "windowed_lower": SOURCE_LOWER,
            "windowed_lower_multiplicity_count": SOURCE_LOWER_COUNT,
            "coverage_upper": coverage_upper,
            "lower_prefix_required": True,
        },
        "configuration": {
            "precision_bits": PRECISION_BITS,
            "step": STEP,
            "blocks_per_shard": blocks_per_shard,
        },
        "geometry": {"block_count": block_count, "shard_count": shard_count},
        "allow_bounded_test": allow_bounded_test,
    }
    plan["plan_sha256"] = _digest(PLAN_DOMAIN, plan)
    return plan


def validate_plan(plan: dict[str, Any]) -> None:
    expected_top = {
        "allow_bounded_test",
        "claim",
        "configuration",
        "geometry",
        "mode",
        "plan_sha256",
        "runner",
        "schema",
        "source",
    }
    if set(plan) != expected_top or plan.get("schema") != SCHEMA:
        raise PlattWindowedCampaignError("campaign plan shape changed")
    digest = plan.get("plan_sha256")
    if digest != _digest(PLAN_DOMAIN, _plan_without_digest(plan)):
        raise PlattWindowedCampaignError("campaign plan digest differs")
    rebuilt = create_plan(
        runner_sha256=plan["runner"]["sha256"],
        runner_size=plan["runner"]["size_bytes"],
        source_manifest_sha256=plan["source"]["manifest_sha256"],
        source_manifest_size=plan["source"]["manifest_size_bytes"],
        blocks_per_shard=plan["configuration"]["blocks_per_shard"],
        block_count=plan["geometry"]["block_count"],
        allow_bounded_test=plan["allow_bounded_test"],
    )
    if rebuilt != plan:
        raise PlattWindowedCampaignError("campaign plan values differ from fixed geometry")


def shard_block_range(plan: dict[str, Any], index: int) -> tuple[int, int]:
    validate_plan(plan)
    shard_count = plan["geometry"]["shard_count"]
    if index < 0 or index >= shard_count:
        raise PlattWindowedCampaignError("shard index is outside the fixed plan")
    span = plan["configuration"]["blocks_per_shard"]
    lower = index * span
    upper = min(lower + span, plan["geometry"]["block_count"])
    return lower, upper


def initialize_campaign(
    *,
    output_directory: Path,
    runner: Path,
    source_manifest: Path,
    blocks_per_shard: int = DEFAULT_BLOCKS_PER_SHARD,
    block_count: int = FULL_BLOCK_COUNT,
    allow_bounded_test: bool = False,
) -> dict[str, Any]:
    mode = runner.stat().st_mode if runner.exists() else 0
    if runner.is_symlink() or not stat.S_ISREG(mode) or not os.access(runner, os.X_OK):
        raise PlattWindowedCampaignError("runner must be an executable regular file")
    manifest = _load_json(source_manifest)
    if (
        manifest.get("kind") != "sparkinterval.pinned_platt_pt21_windowed_source.v1"
        or manifest.get("commit") != SOURCE_COMMIT
        or manifest.get("reviewed_source_sha256") != SOURCE_SET_SHA256
        or manifest.get("license") != "NOASSERTION"
    ):
        raise PlattWindowedCampaignError("source manifest does not match the reviewed pin")
    runner_sha, runner_size = _sha256(runner)
    manifest_sha, manifest_size = _sha256(source_manifest)
    plan = create_plan(
        runner_sha256=runner_sha,
        runner_size=runner_size,
        source_manifest_sha256=manifest_sha,
        source_manifest_size=manifest_size,
        blocks_per_shard=blocks_per_shard,
        block_count=block_count,
        allow_bounded_test=allow_bounded_test,
    )
    plan_path = output_directory / PLAN_NAME
    if output_directory.exists() and any(output_directory.iterdir()):
        raise PlattWindowedCampaignError("campaign output directory must be empty")
    output_directory.mkdir(parents=True, exist_ok=True)
    _atomic_write(plan_path, _canonical(plan) + b"\n")
    return plan


def load_plan(directory: Path) -> dict[str, Any]:
    plan = _load_json(directory / PLAN_NAME)
    validate_plan(plan)
    return plan


def _runner_identity(runner: Path, plan: dict[str, Any]) -> None:
    actual = _sha256(runner)
    expected = (plan["runner"]["sha256"], plan["runner"]["size_bytes"])
    if actual != expected:
        raise PlattWindowedCampaignError("runner identity differs from the plan")


def parse_transcript(
    output: str,
    *,
    first_block: int,
    block_count: int,
) -> dict[str, Any]:
    if not output or "\x00" in output:
        raise PlattWindowedCampaignError("runner transcript is empty or contains NUL")
    lowered = output.lower()
    for token in FORBIDDEN_OUTPUT:
        if token in lowered:
            raise PlattWindowedCampaignError(f"runner transcript contains failure token {token!r}")
    looking: list[tuple[int, int, int]] = []
    success: list[tuple[int, int, int]] = []
    for line in output.splitlines():
        match = LOOKING_RE.fullmatch(line)
        if match is not None:
            looking.append(tuple(int(value) for value in match.groups()))
        match = SUCCESS_RE.fullmatch(line)
        if match is not None:
            success.append(tuple(int(value) for value in match.groups()))
    if len(looking) != block_count or len(success) != block_count:
        raise PlattWindowedCampaignError("transcript has the wrong number of proof records")
    records: list[dict[str, int]] = []
    previous_maximum: int | None = None
    for offset, ((maximum, minimum, difference), (found, lower, upper)) in enumerate(
        zip(looking, success, strict=True)
    ):
        expected_lower = SOURCE_LOWER + (first_block + offset) * STEP
        expected_upper = expected_lower + STEP
        if (lower, upper) != (expected_lower, expected_upper):
            raise PlattWindowedCampaignError("transcript interval is not the fixed grid interval")
        if maximum < minimum or maximum - minimum != difference or found != difference:
            raise PlattWindowedCampaignError("Turing difference and isolated count disagree")
        if previous_maximum is not None and minimum != previous_maximum:
            raise PlattWindowedCampaignError("within-shard Turing counts are not contiguous")
        previous_maximum = maximum
        records.append(
            {
                "block": first_block + offset,
                "height_lower": lower,
                "height_upper": upper,
                "count_lower": minimum,
                "count_upper": maximum,
                "zero_count": found,
            }
        )
    return {
        "records": records,
        "first_count": records[0]["count_lower"],
        "last_count": records[-1]["count_upper"],
        "total_zero_count": sum(record["zero_count"] for record in records),
        "stdout_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
    }


def _execute_shard(
    runner: Path,
    plan: dict[str, Any],
    index: int,
    *,
    timeout_seconds: int | None,
) -> tuple[dict[str, Any], str]:
    first_block, upper_block = shard_block_range(plan, index)
    block_count = upper_block - first_block
    start = SOURCE_LOWER + first_block * STEP
    command = [
        str(runner.resolve()),
        str(PRECISION_BITS),
        str(start),
        str(block_count),
        str(STEP),
    ]
    before = time.monotonic_ns()
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            env={**os.environ, "LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PlattWindowedCampaignError(f"windowed checker could not complete: {error}") from error
    elapsed = time.monotonic_ns() - before
    if completed.returncode != 0:
        raise PlattWindowedCampaignError(
            f"windowed checker exited {completed.returncode}: {completed.stderr[-2000:]}"
        )
    if completed.stderr:
        raise PlattWindowedCampaignError("windowed checker wrote to stderr")
    parsed = parse_transcript(
        completed.stdout, first_block=first_block, block_count=block_count
    )
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "plan_sha256": plan["plan_sha256"],
        "shard_index": index,
        "first_block": first_block,
        "upper_block_exclusive": upper_block,
        "block_count": block_count,
        "height_lower": SOURCE_LOWER + first_block * STEP,
        "height_upper": SOURCE_LOWER + upper_block * STEP,
        "first_count": parsed["first_count"],
        "last_count": parsed["last_count"],
        "total_zero_count": parsed["total_zero_count"],
        "records_sha256": hashlib.sha256(_canonical(parsed["records"])).hexdigest(),
        "stdout_sha256": parsed["stdout_sha256"],
        "runner_sha256": plan["runner"]["sha256"],
        "reviewed_source_sha256": SOURCE_SET_SHA256,
        "precision_bits": PRECISION_BITS,
        "step": STEP,
        "elapsed_nanoseconds": elapsed,
        "all_blocks_proved_complete": True,
        "execution_attested": False,
        "lean_atom_discharged": False,
        "accepted": True,
    }
    semantic = {key: value for key, value in receipt.items() if key != "elapsed_nanoseconds"}
    receipt["receipt_sha256"] = _digest(RECEIPT_DOMAIN, semantic)
    return receipt, completed.stdout


def _receipt_path(directory: Path, index: int) -> Path:
    return directory / "receipts" / f"shard-{index:09d}.json"


def _log_path(directory: Path, index: int) -> Path:
    return directory / "logs" / f"shard-{index:09d}.log"


def validate_receipt(receipt: dict[str, Any], plan: dict[str, Any], index: int) -> None:
    first, upper = shard_block_range(plan, index)
    required = {
        "accepted",
        "all_blocks_proved_complete",
        "block_count",
        "elapsed_nanoseconds",
        "execution_attested",
        "first_block",
        "first_count",
        "height_lower",
        "height_upper",
        "last_count",
        "lean_atom_discharged",
        "plan_sha256",
        "precision_bits",
        "receipt_sha256",
        "records_sha256",
        "reviewed_source_sha256",
        "runner_sha256",
        "schema",
        "shard_index",
        "stdout_sha256",
        "step",
        "total_zero_count",
        "upper_block_exclusive",
    }
    if set(receipt) != required or receipt.get("schema") != RECEIPT_SCHEMA:
        raise PlattWindowedCampaignError("shard receipt shape changed")
    fixed = {
        "accepted": True,
        "all_blocks_proved_complete": True,
        "execution_attested": False,
        "lean_atom_discharged": False,
        "plan_sha256": plan["plan_sha256"],
        "precision_bits": PRECISION_BITS,
        "reviewed_source_sha256": SOURCE_SET_SHA256,
        "runner_sha256": plan["runner"]["sha256"],
        "shard_index": index,
        "step": STEP,
        "first_block": first,
        "upper_block_exclusive": upper,
        "block_count": upper - first,
        "height_lower": SOURCE_LOWER + first * STEP,
        "height_upper": SOURCE_LOWER + upper * STEP,
    }
    if any(receipt.get(key) != value for key, value in fixed.items()):
        raise PlattWindowedCampaignError("shard receipt fixed fields differ")
    if not isinstance(receipt["elapsed_nanoseconds"], int) or receipt["elapsed_nanoseconds"] < 0:
        raise PlattWindowedCampaignError("shard elapsed time is malformed")
    if receipt["last_count"] - receipt["first_count"] != receipt["total_zero_count"]:
        raise PlattWindowedCampaignError("shard aggregate count does not telescope")
    for key in ("records_sha256", "stdout_sha256", "receipt_sha256"):
        if not isinstance(receipt[key], str) or not re.fullmatch(r"[0-9a-f]{64}", receipt[key]):
            raise PlattWindowedCampaignError(f"malformed receipt digest: {key}")
    semantic = {
        key: value
        for key, value in receipt.items()
        if key not in ("elapsed_nanoseconds", "receipt_sha256")
    }
    if receipt["receipt_sha256"] != _digest(RECEIPT_DOMAIN, semantic):
        raise PlattWindowedCampaignError("shard receipt digest differs")


def run_shard(
    directory: Path,
    runner: Path,
    index: int,
    *,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    plan = load_plan(directory)
    _runner_identity(runner, plan)
    receipt_path = _receipt_path(directory, index)
    log_path = _log_path(directory, index)
    if receipt_path.exists() or log_path.exists():
        raise PlattWindowedCampaignError("shard output already exists")
    receipt, output = _execute_shard(
        runner, plan, index, timeout_seconds=timeout_seconds
    )
    _atomic_write(log_path, output.encode("utf-8"))
    _atomic_write(receipt_path, _canonical(receipt) + b"\n")
    return receipt


def replay_shard(
    directory: Path,
    runner: Path,
    index: int,
    *,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    plan = load_plan(directory)
    _runner_identity(runner, plan)
    retained = _load_json(_receipt_path(directory, index))
    validate_receipt(retained, plan, index)
    log = _log_path(directory, index)
    log_sha, _ = _sha256(log)
    if log_sha != retained["stdout_sha256"]:
        raise PlattWindowedCampaignError("retained transcript digest differs")
    fresh, _output = _execute_shard(
        runner, plan, index, timeout_seconds=timeout_seconds
    )
    stable_keys = (
        "block_count",
        "first_block",
        "first_count",
        "height_lower",
        "height_upper",
        "last_count",
        "plan_sha256",
        "precision_bits",
        "records_sha256",
        "reviewed_source_sha256",
        "runner_sha256",
        "shard_index",
        "step",
        "total_zero_count",
        "upper_block_exclusive",
    )
    if any(fresh[key] != retained[key] for key in stable_keys):
        raise PlattWindowedCampaignError("fresh semantic replay differs")
    return {
        "accepted": True,
        "shard_index": index,
        "semantic_replay_identical": True,
        "fresh_stdout_sha256": fresh["stdout_sha256"],
        "execution_attested": False,
        "lean_atom_discharged": False,
    }


def _merkle_root(leaves: list[str]) -> str:
    if not leaves:
        raise PlattWindowedCampaignError("cannot aggregate an empty receipt set")
    level = [hashlib.sha256(MERKLE_LEAF_DOMAIN + bytes.fromhex(leaf)).digest() for leaf in leaves]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(MERKLE_NODE_DOMAIN + level[index] + level[index + 1]).digest()
            for index in range(0, len(level), 2)
        ]
    return level[0].hex()


def campaign_status(directory: Path) -> dict[str, Any]:
    plan = load_plan(directory)
    shard_count = plan["geometry"]["shard_count"]
    completed = 0
    for index in range(shard_count):
        path = _receipt_path(directory, index)
        if not path.exists():
            continue
        validate_receipt(_load_json(path), plan, index)
        completed += 1
    return {
        "accepted": True,
        "mode": plan["mode"],
        "shard_count": shard_count,
        "completed_shards": completed,
        "complete": completed == shard_count,
        "coverage_upper": plan["claim"]["coverage_upper"],
        "source_height_covered": plan["claim"]["coverage_upper"] >= SOURCE_HEIGHT,
        "lower_prefix_required": True,
        "source_claim_ready": False,
        "execution_attested": False,
        "lean_atom_discharged": False,
    }


def finalize_campaign(directory: Path) -> dict[str, Any]:
    plan = load_plan(directory)
    if (directory / FINAL_NAME).exists():
        raise PlattWindowedCampaignError("final artifact already exists")
    shard_count = plan["geometry"]["shard_count"]
    receipts: list[dict[str, Any]] = []
    for index in range(shard_count):
        path = _receipt_path(directory, index)
        if not path.exists():
            raise PlattWindowedCampaignError(f"missing shard receipt {index}")
        receipt = _load_json(path)
        validate_receipt(receipt, plan, index)
        receipts.append(receipt)
    if receipts[0]["first_count"] != SOURCE_LOWER_COUNT:
        raise PlattWindowedCampaignError("first shard does not begin at N(10^10)")
    for left, right in zip(receipts, receipts[1:], strict=False):
        if (
            left["upper_block_exclusive"] != right["first_block"]
            or left["height_upper"] != right["height_lower"]
            or left["last_count"] != right["first_count"]
        ):
            raise PlattWindowedCampaignError("cross-shard height/count chain is not contiguous")
    total = sum(receipt["total_zero_count"] for receipt in receipts)
    if receipts[-1]["last_count"] - receipts[0]["first_count"] != total:
        raise PlattWindowedCampaignError("global count chain does not telescope")
    result: dict[str, Any] = {
        "schema": FINAL_SCHEMA,
        "plan_sha256": plan["plan_sha256"],
        "mode": plan["mode"],
        "shard_count": shard_count,
        "block_count": plan["geometry"]["block_count"],
        "height_lower": SOURCE_LOWER,
        "height_upper": plan["claim"]["coverage_upper"],
        "first_count": receipts[0]["first_count"],
        "last_count": receipts[-1]["last_count"],
        "total_zero_count": total,
        "receipt_merkle_root_sha256": _merkle_root(
            [receipt["receipt_sha256"] for receipt in receipts]
        ),
        "all_high_range_zeros_on_critical_line": True,
        "source_height_covered": plan["claim"]["coverage_upper"] >= SOURCE_HEIGHT,
        "lower_prefix_required": True,
        "source_claim_ready": False,
        "execution_attested": False,
        "lean_atom_discharged": False,
        "accepted": True,
    }
    result["final_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    _atomic_write(directory / FINAL_NAME, _canonical(result) + b"\n")
    return result


__all__ = [
    "DEFAULT_BLOCKS_PER_SHARD",
    "FULL_BLOCK_COUNT",
    "FULL_COVERAGE_UPPER",
    "PRECISION_BITS",
    "SOURCE_COUNT",
    "SOURCE_HEIGHT",
    "SOURCE_LOWER",
    "SOURCE_LOWER_COUNT",
    "STEP",
    "PlattWindowedCampaignError",
    "campaign_status",
    "create_plan",
    "finalize_campaign",
    "initialize_campaign",
    "load_plan",
    "parse_transcript",
    "replay_shard",
    "run_shard",
    "shard_block_range",
    "validate_plan",
    "validate_receipt",
]
