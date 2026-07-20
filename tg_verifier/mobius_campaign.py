# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Resumable local campaigns for exact CUDA Möbius-family receipts.

The supervisor captures one runner executable, executes consecutive segments,
and validates every receipt before atomically retaining it.  This is a local
execution record, not remote attestation and not a Lean realization theorem.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Mapping

from .campaign_io import CampaignIOError, advisory_lock
from .evidence import EvidenceError, load_decimal_json_bytes
from .mobius_cuda import (
    LITTLE_MERTENS_2_11_LIMIT,
    LITTLE_MERTENS_STRONGER_LIMIT,
    RUNNER_MAX_RECORD_COUNT,
    SOURCE_LIMIT,
    ZERO_DIGEST,
    MobiusChainResult,
    MobiusReceiptError,
    verify_mobius_receipt,
    verify_mobius_receipt_chain,
)


CAMPAIGN_ALGORITHM = "tg_mobius_exact_campaign_v1"
CAPTURED_RUNNER_NAME = "captured-mobius-runner"
CONFIG_NAME = "campaign-config.json"
MANIFEST_NAME = "campaign-manifest.json"
MAX_RUNNER_BYTES = 1 << 30
MAX_RECEIPT_BYTES = 1 << 20
_RECEIPT_NAME = re.compile(r"receipt-([0-9]{8})\.json")
TARGET_ENDPOINTS = {
    "stronger": LITTLE_MERTENS_STRONGER_LIMIT,
    "2-11": LITTLE_MERTENS_2_11_LIMIT,
    "both": LITTLE_MERTENS_2_11_LIMIT,
    "hurst": SOURCE_LIMIT,
    "squarefree": SOURCE_LIMIT,
}


class MobiusCampaignError(RuntimeError):
    """A campaign configuration, execution, or receipt failed closed."""


@dataclass(frozen=True)
class MobiusCampaignResult:
    target: str
    endpoint: int
    completed_upper: int
    receipts: int
    complete: bool
    runner_sha256: str
    receipt_chain_sha256: str
    endpoint_reached: bool
    target_predicate_structurally_passed: bool
    structurally_reports_no_hurst_failure: bool
    structurally_reports_no_cdem_b1_failure: bool
    structurally_reports_no_cdem_b2_failure: bool
    structurally_claims_full_hurst_range: bool
    structurally_claims_full_squarefree_range: bool
    structurally_reports_no_little_mertens_2_11_failure: bool
    structurally_reports_no_little_mertens_stronger_failure: bool
    locally_supervised_execution: bool
    execution_attested: bool = False
    lean_atoms_discharged: bool = False

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def _read_bounded(path: Path, maximum: int, label: str) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise MobiusCampaignError(f"{label} is not a regular file")
            chunks: list[bytes] = []
            remaining = maximum + 1
            while remaining > 0:
                chunk = os.read(descriptor, min(1 << 20, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise MobiusCampaignError(f"cannot read {label} {path}: {exc}") from exc
    if len(raw) > maximum:
        raise MobiusCampaignError(f"{label} exceeds the {maximum}-byte limit")
    return raw


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _atomic_write(path: Path, raw: bytes, *, mode: int = 0o600) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        mode,
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _parse_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        return load_decimal_json_bytes(raw, label=label)
    except EvidenceError as exc:
        raise MobiusCampaignError(str(exc)) from exc


def _expected_config(
    *,
    target: str,
    segment_count: int,
    device: int,
    allow_other_device: bool,
    runner_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "algorithm": CAMPAIGN_ALGORITHM,
        "classification": (
            "resumable_local_execution_not_attestation_or_lean_proof"
        ),
        "target": target,
        "endpoint": TARGET_ENDPOINTS[target],
        "segment_count": segment_count,
        "device": device,
        "allow_other_device": allow_other_device,
        "captured_runner_sha256": runner_sha256,
    }


def _validate_config(config: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "algorithm",
        "classification",
        "target",
        "endpoint",
        "segment_count",
        "device",
        "allow_other_device",
        "captured_runner_sha256",
    }
    if set(config) != required:
        raise MobiusCampaignError("campaign config fields changed")
    target = config.get("target")
    if not isinstance(target, str) or target not in TARGET_ENDPOINTS:
        raise MobiusCampaignError("campaign config has an unknown target")
    _validate_parameters(
        target,
        config.get("segment_count"),
        config.get("device"),
        None,
    )
    if type(config.get("endpoint")) is not int:
        raise MobiusCampaignError("campaign endpoint must be an integer")
    if not isinstance(config.get("allow_other_device"), bool):
        raise MobiusCampaignError("allow_other_device must be a bool")
    runner_sha256 = config.get("captured_runner_sha256")
    if not isinstance(runner_sha256, str) or re.fullmatch(
        r"[0-9a-f]{64}", runner_sha256
    ) is None:
        raise MobiusCampaignError("captured runner digest is malformed")
    expected = _expected_config(
        target=target,
        segment_count=config["segment_count"],
        device=config["device"],
        allow_other_device=config["allow_other_device"],
        runner_sha256=runner_sha256,
    )
    if dict(config) != expected:
        raise MobiusCampaignError("campaign config values changed")


def _validate_parameters(
    target: str, segment_count: int, device: int, max_chunks: int | None
) -> None:
    if target not in TARGET_ENDPOINTS:
        raise MobiusCampaignError(f"unknown campaign target {target!r}")
    if type(segment_count) is not int or not (
        1 <= segment_count <= RUNNER_MAX_RECORD_COUNT
    ):
        raise MobiusCampaignError(
            f"segment_count must lie in [1, {RUNNER_MAX_RECORD_COUNT}]"
        )
    if type(device) is not int or device < 0:
        raise MobiusCampaignError("device must be a nonnegative integer")
    if max_chunks is not None and (
        isinstance(max_chunks, bool)
        or not isinstance(max_chunks, int)
        or max_chunks < 1
    ):
        raise MobiusCampaignError("max_chunks must be a positive integer or null")


def _initialize_or_check_campaign(
    *,
    runner: Path,
    output_directory: Path,
    target: str,
    segment_count: int,
    device: int,
    allow_other_device: bool,
) -> tuple[Path, dict[str, Any]]:
    if output_directory.exists() and not output_directory.is_dir():
        raise MobiusCampaignError("campaign output path is not a directory")
    output_directory.mkdir(parents=True, exist_ok=True)
    captured_path = output_directory / CAPTURED_RUNNER_NAME
    config_path = output_directory / CONFIG_NAME
    runner_raw = _read_bounded(runner, MAX_RUNNER_BYTES, "runner")
    runner_sha256 = _sha256(runner_raw)
    expected = _expected_config(
        target=target,
        segment_count=segment_count,
        device=device,
        allow_other_device=allow_other_device,
        runner_sha256=runner_sha256,
    )
    if config_path.exists() or captured_path.exists():
        if not (config_path.is_file() and captured_path.is_file()):
            raise MobiusCampaignError("campaign runner/config initialization is partial")
        config = _parse_object(
            _read_bounded(config_path, MAX_RECEIPT_BYTES, "campaign config"),
            str(config_path),
        )
        _validate_config(config)
        if config != expected:
            raise MobiusCampaignError("resume configuration does not match campaign")
        captured_raw = _read_bounded(
            captured_path, MAX_RUNNER_BYTES, "captured runner"
        )
        if _sha256(captured_raw) != runner_sha256 or captured_raw != runner_raw:
            raise MobiusCampaignError("captured runner identity changed")
    else:
        _atomic_write(captured_path, runner_raw, mode=0o700)
        _atomic_write(config_path, _json_bytes(expected))
    try:
        captured_path.chmod(
            stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP
        )
    except OSError as exc:
        raise MobiusCampaignError(f"cannot make captured runner executable: {exc}") from exc
    return captured_path, expected


def _receipt_paths(output_directory: Path) -> list[Path]:
    indexed: list[tuple[int, Path]] = []
    for path in output_directory.glob("receipt-*.json"):
        match = _RECEIPT_NAME.fullmatch(path.name)
        if match is None:
            raise MobiusCampaignError(f"malformed campaign receipt path {path.name!r}")
        indexed.append((int(match.group(1)), path))
    indexed.sort()
    if [index for index, _ in indexed] != list(range(len(indexed))):
        raise MobiusCampaignError("campaign receipt indices are not consecutive")
    return [path for _, path in indexed]


def _load_receipts(output_directory: Path) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in _receipt_paths(output_directory):
        report = _parse_object(
            _read_bounded(path, MAX_RECEIPT_BYTES, "receipt"), str(path)
        )
        try:
            verify_mobius_receipt(report)
        except MobiusReceiptError as exc:
            raise MobiusCampaignError(f"invalid receipt {path.name}: {exc}") from exc
        reports.append(report)
    return reports


def _validate_reports_against_config(
    reports: list[dict[str, Any]], config: Mapping[str, Any]
) -> MobiusChainResult | None:
    if not reports:
        return None
    try:
        chain = verify_mobius_receipt_chain(reports)
    except MobiusReceiptError as exc:
        raise MobiusCampaignError(f"receipt chain is invalid: {exc}") from exc
    runner_sha256 = config["captured_runner_sha256"]
    endpoint = config["endpoint"]
    segment_count = config["segment_count"]
    for index, report in enumerate(reports):
        if report.get("executable_sha256") != runner_sha256:
            raise MobiusCampaignError("receipt executable does not match captured runner")
        if report.get("record_count") != min(
            segment_count, endpoint - report["lower"] + 1
        ):
            raise MobiusCampaignError("receipt uses the wrong campaign segment size")
        if report["upper"] > endpoint:
            raise MobiusCampaignError("receipt exceeds the campaign endpoint")
        if index + 1 < len(reports) and report["record_count"] != segment_count:
            raise MobiusCampaignError("a nonfinal campaign receipt is short")
    return chain


def _result(
    config: Mapping[str, Any],
    reports: list[dict[str, Any]],
    chain: MobiusChainResult | None,
    *,
    locally_supervised_execution: bool,
) -> MobiusCampaignResult:
    upper = 0 if chain is None else chain.upper
    endpoint = int(config["endpoint"])
    target = str(config["target"])
    endpoint_reached = upper == endpoint
    no_hurst = False if chain is None else chain.structurally_reports_no_hurst_failure
    no_b1 = False if chain is None else chain.structurally_reports_no_cdem_b1_failure
    no_b2 = False if chain is None else chain.structurally_reports_no_cdem_b2_failure
    full_hurst = endpoint_reached and endpoint == SOURCE_LIMIT and no_hurst
    full_squarefree = endpoint_reached and endpoint == SOURCE_LIMIT and no_b1 and no_b2
    if target == "hurst":
        target_passed = full_hurst
    elif target == "squarefree":
        target_passed = full_squarefree
    elif target == "stronger":
        target_passed = bool(
            chain is not None
            and chain.structurally_claims_full_little_mertens_stronger_range
        )
    elif target == "2-11":
        target_passed = bool(
            chain is not None
            and chain.structurally_claims_full_little_mertens_2_11_range
        )
    else:
        target_passed = bool(
            chain is not None
            and chain.structurally_claims_full_little_mertens_2_11_range
            and chain.structurally_claims_full_little_mertens_stronger_range
        )
    return MobiusCampaignResult(
        target=target,
        endpoint=endpoint,
        completed_upper=upper,
        receipts=len(reports),
        complete=endpoint_reached and target_passed,
        runner_sha256=str(config["captured_runner_sha256"]),
        receipt_chain_sha256=(
            ZERO_DIGEST if not reports else str(reports[-1]["receipt_chain_sha256"])
        ),
        endpoint_reached=endpoint_reached,
        target_predicate_structurally_passed=target_passed,
        structurally_reports_no_hurst_failure=no_hurst,
        structurally_reports_no_cdem_b1_failure=no_b1,
        structurally_reports_no_cdem_b2_failure=no_b2,
        structurally_claims_full_hurst_range=full_hurst,
        structurally_claims_full_squarefree_range=full_squarefree,
        structurally_reports_no_little_mertens_2_11_failure=(
            False
            if chain is None
            else chain.structurally_reports_no_little_mertens_2_11_failure
        ),
        structurally_reports_no_little_mertens_stronger_failure=(
            False
            if chain is None
            else chain.structurally_reports_no_little_mertens_stronger_failure
        ),
        locally_supervised_execution=locally_supervised_execution,
    )


def _target_failure(report: Mapping[str, Any], target: str) -> str | None:
    fields: tuple[str, ...]
    if target == "hurst":
        fields = ("hurst_first_failure",)
    elif target == "squarefree":
        fields = (
            "cdem_b1_first_not_proved_safe",
            "cdem_b2_first_not_proved_safe",
        )
    elif target == "stronger":
        fields = ("little_mertens_stronger_first_not_proved_safe",)
    elif target == "2-11":
        fields = ("little_mertens_2_11_first_not_proved_safe",)
    else:
        fields = (
            "little_mertens_2_11_first_not_proved_safe",
            "little_mertens_stronger_first_not_proved_safe",
        )
    for field in fields:
        if report.get(field) is not None:
            return field
    return None


def _verify_campaign_unlocked(output_directory: Path) -> MobiusCampaignResult:
    """Verify the captured runner, immutable configuration, and receipt chain."""

    config_path = output_directory / CONFIG_NAME
    captured_path = output_directory / CAPTURED_RUNNER_NAME
    config = _parse_object(
        _read_bounded(config_path, MAX_RECEIPT_BYTES, "campaign config"),
        str(config_path),
    )
    _validate_config(config)
    captured_raw = _read_bounded(captured_path, MAX_RUNNER_BYTES, "captured runner")
    if _sha256(captured_raw) != config["captured_runner_sha256"]:
        raise MobiusCampaignError("captured runner hash does not match config")
    reports = _load_receipts(output_directory)
    chain = _validate_reports_against_config(reports, config)
    result = _result(
        config, reports, chain, locally_supervised_execution=False
    )
    manifest_path = output_directory / MANIFEST_NAME
    if manifest_path.exists():
        manifest = _parse_object(
            _read_bounded(manifest_path, MAX_RECEIPT_BYTES, "campaign manifest"),
            str(manifest_path),
        )
        # This validates what the live supervisor wrote without treating the
        # self-asserted bit as later authentication of that execution.
        expected_manifest = result.as_json()
        expected_manifest["locally_supervised_execution"] = True
        if manifest != expected_manifest:
            raise MobiusCampaignError("campaign manifest disagrees with receipts")
    return result


def verify_campaign(output_directory: Path) -> MobiusCampaignResult:
    """Verify a stable retained campaign while excluding a concurrent writer."""

    try:
        with advisory_lock(output_directory / ".campaign.lock"):
            return _verify_campaign_unlocked(output_directory)
    except CampaignIOError as exc:
        raise MobiusCampaignError(str(exc)) from exc


def _run_campaign_unlocked(
    *,
    runner: Path,
    output_directory: Path,
    target: str,
    segment_count: int,
    device: int = 0,
    allow_other_device: bool = False,
    max_chunks: int | None = None,
    chunk_timeout_seconds: int | None = None,
) -> MobiusCampaignResult:
    """Run or resume a gap-free campaign, retaining each checked receipt."""

    _validate_parameters(target, segment_count, device, max_chunks)
    if chunk_timeout_seconds is not None and (
        isinstance(chunk_timeout_seconds, bool)
        or not isinstance(chunk_timeout_seconds, int)
        or chunk_timeout_seconds < 1
    ):
        raise MobiusCampaignError(
            "chunk_timeout_seconds must be a positive integer or null"
        )
    captured_runner, config = _initialize_or_check_campaign(
        runner=runner,
        output_directory=output_directory,
        target=target,
        segment_count=segment_count,
        device=device,
        allow_other_device=allow_other_device,
    )
    reports = _load_receipts(output_directory)
    chain = _validate_reports_against_config(reports, config)
    for retained_report in reports:
        failed_field = _target_failure(retained_report, target)
        if failed_field is not None:
            raise MobiusCampaignError(
                f"cannot resume: retained target failure in {failed_field}"
            )
    endpoint = TARGET_ENDPOINTS[target]
    chunks_run = 0
    while (chain is None or chain.upper < endpoint) and (
        max_chunks is None or chunks_run < max_chunks
    ):
        lower = 1 if chain is None else chain.upper + 1
        count = min(segment_count, endpoint - lower + 1)
        command = [
            str(captured_runner.resolve()),
            "--lower",
            str(lower),
            "--count",
            str(count),
            "--device",
            str(device),
        ]
        if allow_other_device:
            command.append("--allow-other-device")
        if reports:
            previous = reports[-1]
            command.extend(
                [
                    "--incoming-mertens",
                    str(previous["outgoing_mertens"]),
                    "--incoming-squarefree",
                    str(previous["outgoing_squarefree"]),
                    "--incoming-little-mertens-lower",
                    str(previous["outgoing_little_mertens_lower"]),
                    "--incoming-little-mertens-upper",
                    str(previous["outgoing_little_mertens_upper"]),
                    "--previous-receipt-sha256",
                    str(previous["receipt_chain_sha256"]),
                ]
            )
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=chunk_timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise MobiusCampaignError(f"campaign runner failed: {exc}") from exc
        if completed.returncode != 0:
            diagnostic = completed.stderr[:4096].decode("utf-8", errors="replace")
            raise MobiusCampaignError(
                f"campaign runner returned {completed.returncode}: {diagnostic}"
            )
        if len(completed.stdout) > MAX_RECEIPT_BYTES:
            raise MobiusCampaignError("campaign runner emitted an oversized receipt")
        report = _parse_object(completed.stdout, "campaign runner stdout")
        try:
            verify_mobius_receipt(report)
        except MobiusReceiptError as exc:
            raise MobiusCampaignError(f"campaign runner emitted an invalid receipt: {exc}") from exc
        if report.get("lower") != lower or report.get("record_count") != count:
            raise MobiusCampaignError("campaign runner returned the wrong range")
        if report.get("executable_sha256") != config["captured_runner_sha256"]:
            raise MobiusCampaignError("executed runner identity does not match capture")
        receipt_path = output_directory / f"receipt-{len(reports):08d}.json"
        _atomic_write(receipt_path, completed.stdout)
        reports.append(report)
        chain = _validate_reports_against_config(reports, config)
        failed_field = _target_failure(report, target)
        if failed_field is not None:
            result = _result(
                config, reports, chain, locally_supervised_execution=True
            )
            _atomic_write(
                output_directory / MANIFEST_NAME, _json_bytes(result.as_json())
            )
            raise MobiusCampaignError(
                f"target predicate failed in {failed_field}; receipt retained"
            )
        chunks_run += 1

    result = _result(config, reports, chain, locally_supervised_execution=True)
    _atomic_write(output_directory / MANIFEST_NAME, _json_bytes(result.as_json()))
    if _sha256(_read_bounded(captured_runner, MAX_RUNNER_BYTES, "captured runner")) != (
        config["captured_runner_sha256"]
    ):
        raise MobiusCampaignError("captured runner changed during campaign")
    return result


def run_campaign(
    *,
    runner: Path,
    output_directory: Path,
    target: str,
    segment_count: int,
    device: int = 0,
    allow_other_device: bool = False,
    max_chunks: int | None = None,
    chunk_timeout_seconds: int | None = None,
) -> MobiusCampaignResult:
    """Run or resume a campaign under one directory-wide writer lock."""

    try:
        with advisory_lock(output_directory / ".campaign.lock"):
            return _run_campaign_unlocked(
                runner=runner,
                output_directory=output_directory,
                target=target,
                segment_count=segment_count,
                device=device,
                allow_other_device=allow_other_device,
                max_chunks=max_chunks,
                chunk_timeout_seconds=chunk_timeout_seconds,
            )
    except CampaignIOError as exc:
        raise MobiusCampaignError(str(exc)) from exc
