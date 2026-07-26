# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Resumable full-source supervisor for exact CUDA R2Star chunks.

The supervisor captures one runner binary, launches a gap-free sequence of
bounded chunks, checks every source-shaped transition before retaining it, and
can resume only from the verified prefix.  Structural verification of a
retained campaign does not authenticate historical execution.  Production can
add a separately compiled, CPU-only pass which recomputes every retained row;
neither pass by itself realizes the analytic definition in Lean.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from typing import Any, Mapping, Sequence

from .campaign_io import (
    AZURE_MEASURED_WORKER_CHALLENGE_ENV,
    AZURE_MEASURED_WORKER_JOB_BINDING_ENV,
    MeasuredWorkerScopeError,
    advisory_lock,
    atomic_write_bytes,
    azure_measured_worker_environment,
    require_azure_measured_worker_for_workload,
)
from .evidence import EvidenceError, load_decimal_json_bytes
from .r2star import (
    R2STAR_ALGORITHM,
    R2STAR_ATOM,
    R2STAR_BOUND_DENOMINATOR,
    R2STAR_BOUND_NUMERATOR,
    R2STAR_CHUNK_SCHEMA_VERSION,
    R2STAR_FACTOR_SUPPORT_ENCODING,
    R2STAR_MAX_CHUNK_SPAN,
    R2STAR_SOURCE_LIMIT,
    R2StarChunk,
    ZERO_SHA256,
)


CAMPAIGN_ALGORITHM = "tg_r2star_cuda_campaign_v1"
CAPTURED_RUNNER_NAME = "captured-r2star-runner"
CONFIG_NAME = "campaign-config.json"
MANIFEST_NAME = "campaign-manifest.json"
REGISTERED_RESULT = b"true"
REGISTERED_RESULT_SHA256 = hashlib.sha256(REGISTERED_RESULT).hexdigest()
MAX_RUNNER_BYTES = 1 << 30
MAX_RECEIPT_BYTES = 4 << 20
MAX_ARITHMETIC_REPLAY_OUTPUT_BYTES = 4 << 10
MAX_ARITHMETIC_REPLAYER_BYTES = 256 << 20
DEFAULT_ARITHMETIC_REPLAY_SEGMENT_ROWS = 2_048
MAX_ARITHMETIC_REPLAY_SEGMENT_ROWS = R2STAR_MAX_CHUNK_SPAN
ARITHMETIC_REPLAY_PLAN_HEADER = (
    "sparkinterval-r2star-arithmetic-replay-plan-v1"
)
ARITHMETIC_REPLAY_BENCHMARK_PLAN_HEADER = (
    "sparkinterval-r2star-arithmetic-replay-benchmark-plan-v1"
)
_RECEIPT_NAME = re.compile(r"receipt-([0-9]{8})\.json")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_RECEIPT_FIELDS = {
    "ambiguous_log_rows",
    "chunk",
    "classification",
    "compute_capability",
    "cuda_driver_api_version",
    "cuda_runtime_version",
    "device_name",
    "directed_row_kernel_milliseconds",
    "directed_rows_sha256_le_v1",
    "exact_rational_fallback_rows",
    "factor_kernel_milliseconds",
    "factor_support_digest_producer",
    "factor_support_encoding",
    "full_source_range",
    "gpu_capped_factor_support_matches_host",
    "hash_chain_is_integrity_not_authentication",
    "independent_factor_check_milliseconds",
    "integer_overflow_rows",
    "kernel_milliseconds",
    "lean_atom_discharged",
    "log_algorithm",
    "parallel_transition_kernel_milliseconds",
    "prefix_implementation",
    "proves_any_external_atom",
    "python_contract_replay_required",
    "receipt_schema",
    "serial_cross_check_performed",
    "serial_reference_kernel_milliseconds",
}


class R2StarCampaignError(RuntimeError):
    """A campaign configuration, receipt, or execution failed closed."""


@dataclass(frozen=True)
class R2StarCampaignResult:
    endpoint: int
    completed_upper: int
    receipts: int
    complete: bool
    runner_sha256: str
    final_record_hash: str
    minimum_squared_slack: int | None
    minimum_slack_index: int | None
    exact_fallback_rows: int
    locally_supervised_execution: bool
    execution_attested: bool = False
    independent_rows_replayed: bool = False
    arithmetic_replayer_sha256: str | None = None
    lean_atom_discharged: bool = False

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def _read_bounded(path: Path, maximum: int, label: str) -> bytes:
    try:
        with path.open("rb") as source:
            raw = source.read(maximum + 1)
    except OSError as exc:
        raise R2StarCampaignError(f"cannot read {label} {path}: {exc}") from exc
    if len(raw) > maximum:
        raise R2StarCampaignError(f"{label} exceeds the {maximum}-byte limit")
    return raw


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _parse_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        return load_decimal_json_bytes(raw, label=label)
    except EvidenceError as exc:
        raise R2StarCampaignError(str(exc)) from exc


def _plain_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise R2StarCampaignError(f"{name} must be an integer")
    return value


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise R2StarCampaignError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _timing(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)) or value < 0:
        raise R2StarCampaignError(f"{name} must be a nonnegative JSON number")


def _expected_config(
    *,
    segment_count: int,
    device: int,
    allow_other_device: bool,
    cross_check_serial: bool,
    runner_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "algorithm": CAMPAIGN_ALGORITHM,
        "classification": "resumable_local_execution_not_attestation_or_lean_proof",
        "atom_id": R2STAR_ATOM,
        "endpoint": R2STAR_SOURCE_LIMIT,
        "segment_count": segment_count,
        "device": device,
        "allow_other_device": allow_other_device,
        "cross_check_serial": cross_check_serial,
        "captured_runner_sha256": runner_sha256,
    }


def _validate_parameters(
    segment_count: int, device: int, max_chunks: int | None
) -> None:
    if isinstance(segment_count, bool) or not (
        3 <= segment_count <= min(R2STAR_MAX_CHUNK_SPAN, 1_000_000)
    ):
        raise R2StarCampaignError("segment_count must lie in [3, 1000000]")
    if isinstance(device, bool) or not isinstance(device, int) or device < 0:
        raise R2StarCampaignError("device must be a nonnegative integer")
    if max_chunks is not None and (
        isinstance(max_chunks, bool)
        or not isinstance(max_chunks, int)
        or max_chunks < 1
    ):
        raise R2StarCampaignError("max_chunks must be positive or null")


def _initialize_or_check(
    *,
    runner: Path,
    output_directory: Path,
    segment_count: int,
    device: int,
    allow_other_device: bool,
    cross_check_serial: bool,
) -> tuple[Path, dict[str, Any]]:
    if output_directory.exists() and not output_directory.is_dir():
        raise R2StarCampaignError("campaign output path is not a directory")
    output_directory.mkdir(parents=True, exist_ok=True)
    runner_raw = _read_bounded(runner, MAX_RUNNER_BYTES, "runner")
    runner_sha256 = _sha256(runner_raw)
    expected = _expected_config(
        segment_count=segment_count,
        device=device,
        allow_other_device=allow_other_device,
        cross_check_serial=cross_check_serial,
        runner_sha256=runner_sha256,
    )
    captured = output_directory / CAPTURED_RUNNER_NAME
    config_path = output_directory / CONFIG_NAME
    if captured.exists() or config_path.exists():
        if not (captured.is_file() and config_path.is_file()):
            raise R2StarCampaignError("campaign initialization is partial")
        config = _parse_object(
            _read_bounded(config_path, MAX_RECEIPT_BYTES, "config"),
            str(config_path),
        )
        if config != expected:
            raise R2StarCampaignError("resume configuration changed")
        captured_raw = _read_bounded(captured, MAX_RUNNER_BYTES, "captured runner")
        if captured_raw != runner_raw or _sha256(captured_raw) != runner_sha256:
            raise R2StarCampaignError("captured runner identity changed")
    else:
        atomic_write_bytes(captured, runner_raw)
        atomic_write_bytes(config_path, _json_bytes(expected))
    try:
        captured.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)
    except OSError as exc:
        raise R2StarCampaignError(f"cannot make captured runner executable: {exc}") from exc
    return captured, expected


def _receipt_paths(output_directory: Path) -> list[Path]:
    indexed: list[tuple[int, Path]] = []
    for path in output_directory.glob("receipt-*.json"):
        match = _RECEIPT_NAME.fullmatch(path.name)
        if match is None or not path.is_file():
            raise R2StarCampaignError(f"malformed receipt path {path.name!r}")
        indexed.append((int(match.group(1)), path))
    indexed.sort()
    if [index for index, _ in indexed] != list(range(len(indexed))):
        raise R2StarCampaignError("receipt indices are not consecutive")
    return [path for _, path in indexed]


def verify_runner_receipt(report: Mapping[str, Any]) -> R2StarChunk:
    """Check one runner receipt without replaying its million source rows."""

    if not isinstance(report, Mapping):
        raise R2StarCampaignError("receipt must be an object")
    if set(report) != _RECEIPT_FIELDS:
        raise R2StarCampaignError(
            "receipt fields differ; "
            f"missing={sorted(_RECEIPT_FIELDS - set(report))}, "
            f"extra={sorted(set(report) - _RECEIPT_FIELDS)}"
        )
    if report.get("receipt_schema") != "sparkinterval.r2star-bounded-chunk.v1":
        raise R2StarCampaignError("unexpected R2Star receipt schema")
    if report.get("classification") != (
        "bounded_exact_python_contract_chunk_not_full_atom_proof"
    ):
        raise R2StarCampaignError("unexpected R2Star receipt classification")
    raw_chunk = report.get("chunk")
    if not isinstance(raw_chunk, dict):
        raise R2StarCampaignError("receipt chunk must be an object")
    try:
        chunk = R2StarChunk(**raw_chunk)
    except (TypeError, ValueError) as exc:
        raise R2StarCampaignError(f"malformed R2Star chunk: {exc}") from exc
    if chunk.schema_version != R2STAR_CHUNK_SCHEMA_VERSION:
        raise R2StarCampaignError("unsupported chunk schema")
    if not (1 <= chunk.lower < chunk.upper <= R2STAR_SOURCE_LIMIT + 1):
        raise R2StarCampaignError("chunk range is outside the source domain")
    if chunk.upper - chunk.lower > 1_000_000:
        raise R2StarCampaignError("chunk exceeds the runner's range guard")
    if chunk.bound_numerator != R2STAR_BOUND_NUMERATOR or (
        chunk.bound_denominator != R2STAR_BOUND_DENOMINATOR
    ):
        raise R2StarCampaignError("chunk changes the source bound")
    if (chunk.scale_bits, chunk.series_terms, chunk.harmonic_terms) != (
        32,
        20,
        100_000,
    ):
        raise R2StarCampaignError("chunk changes the fixed arithmetic configuration")
    if (chunk.gamma_lower, chunk.gamma_upper) != (2_479_051_107, 2_479_194_040):
        raise R2StarCampaignError("chunk changes the directed Euler-gamma interval")
    if chunk.incoming_lower > chunk.incoming_upper or (
        chunk.outgoing_lower > chunk.outgoing_upper
    ):
        raise R2StarCampaignError("chunk contains a reversed directed state")
    if chunk.minimum_squared_slack < 0 or not (
        max(3, chunk.lower) <= chunk.minimum_slack_index < chunk.upper
    ):
        raise R2StarCampaignError("chunk minimum-slack witness is invalid")
    if _digest(chunk.factor_support_digest, "factor_support_digest") == ZERO_SHA256:
        raise R2StarCampaignError("factor-support digest is zero")
    _digest(chunk.previous_hash, "previous_hash")
    if _digest(chunk.record_hash, "record_hash") != chunk.recomputed_hash():
        raise R2StarCampaignError("chunk canonical hash is invalid")
    if report.get("factor_support_encoding") != R2STAR_FACTOR_SUPPORT_ENCODING:
        raise R2StarCampaignError("factor-support encoding changed")
    if report.get("factor_support_digest_producer") != (
        "independent_host_segmented_exact_factorization_v1"
    ):
        raise R2StarCampaignError("segmented full-factor producer is absent")
    if report.get("log_algorithm") != (
        "q64_directed_atanh_with_exact_rational_host_fallback_v1"
    ) or report.get("prefix_implementation") != (
        "deterministic_blocked_exact_scan_v1"
    ):
        raise R2StarCampaignError("receipt arithmetic implementation changed")
    for field in (
        "gpu_capped_factor_support_matches_host",
        "python_contract_replay_required",
        "hash_chain_is_integrity_not_authentication",
    ):
        if report.get(field) is not True:
            raise R2StarCampaignError(f"receipt omits required true field {field}")
    for field in (
        "full_source_range",
        "lean_atom_discharged",
        "proves_any_external_atom",
    ):
        if report.get(field) is not False:
            raise R2StarCampaignError(f"unsafe receipt claim in {field}")
    fallback = _plain_int(report.get("exact_rational_fallback_rows"), "fallback rows")
    if fallback < 0 or report.get("ambiguous_log_rows") != fallback:
        raise R2StarCampaignError("fallback row accounting is inconsistent")
    if _plain_int(report.get("integer_overflow_rows"), "overflow rows") != 0:
        raise R2StarCampaignError("receipt reports an integer overflow")
    if not isinstance(report.get("serial_cross_check_performed"), bool):
        raise R2StarCampaignError("serial cross-check field must be Boolean")
    for name in ("device_name", "compute_capability"):
        if not isinstance(report.get(name), str) or not report[name]:
            raise R2StarCampaignError(f"{name} must be a nonempty string")
    for name in ("cuda_driver_api_version", "cuda_runtime_version"):
        if _plain_int(report.get(name), name) < 0:
            raise R2StarCampaignError(f"{name} must be nonnegative")
    _digest(report.get("directed_rows_sha256_le_v1"), "directed row digest")
    for field in (
        "kernel_milliseconds",
        "factor_kernel_milliseconds",
        "directed_row_kernel_milliseconds",
        "parallel_transition_kernel_milliseconds",
        "serial_reference_kernel_milliseconds",
        "independent_factor_check_milliseconds",
    ):
        _timing(report.get(field), field)
    return chunk


def _load_receipts(output_directory: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in _receipt_paths(output_directory):
        report = _parse_object(
            _read_bounded(path, MAX_RECEIPT_BYTES, "receipt"), str(path)
        )
        verify_runner_receipt(report)
        result.append(report)
    return result


def _check_chain(
    reports: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> None:
    previous: R2StarChunk | None = None
    endpoint = _plain_int(config.get("endpoint"), "endpoint")
    span = _plain_int(config.get("segment_count"), "segment_count")
    for index, report in enumerate(reports):
        chunk = verify_runner_receipt(report)
        expected_lower = 1 if previous is None else previous.upper
        if chunk.lower != expected_lower:
            raise R2StarCampaignError(f"receipt {index} breaks range coverage")
        expected_span = min(span, endpoint - chunk.lower + 1)
        if chunk.upper - chunk.lower != expected_span:
            raise R2StarCampaignError(f"receipt {index} has the wrong segment size")
        if previous is None:
            if (chunk.incoming_lower, chunk.incoming_upper) != (0, 0) or (
                chunk.previous_hash != ZERO_SHA256
            ):
                raise R2StarCampaignError("root receipt is not rooted at zero")
        elif (
            chunk.incoming_lower,
            chunk.incoming_upper,
            chunk.previous_hash,
        ) != (
            previous.outgoing_lower,
            previous.outgoing_upper,
            previous.record_hash,
        ):
            raise R2StarCampaignError(f"receipt {index} breaks state/hash linkage")
        if chunk.upper > endpoint + 1:
            raise R2StarCampaignError("receipt exceeds the source endpoint")
        previous = chunk


def _result(
    config: Mapping[str, Any],
    reports: Sequence[Mapping[str, Any]],
    *,
    locally_supervised_execution: bool,
) -> R2StarCampaignResult:
    chunks = [verify_runner_receipt(report) for report in reports]
    last = None if not chunks else chunks[-1]
    minimum_chunk = (
        None
        if not chunks
        else min(chunks, key=lambda chunk: (chunk.minimum_squared_slack, chunk.minimum_slack_index))
    )
    endpoint = _plain_int(config.get("endpoint"), "endpoint")
    completed = 0 if last is None else last.upper - 1
    return R2StarCampaignResult(
        endpoint=endpoint,
        completed_upper=completed,
        receipts=len(reports),
        complete=completed == endpoint,
        runner_sha256=_digest(config.get("captured_runner_sha256"), "runner digest"),
        final_record_hash=ZERO_SHA256 if last is None else last.record_hash,
        minimum_squared_slack=(
            None if minimum_chunk is None else minimum_chunk.minimum_squared_slack
        ),
        minimum_slack_index=(
            None if minimum_chunk is None else minimum_chunk.minimum_slack_index
        ),
        exact_fallback_rows=sum(
            _plain_int(report.get("exact_rational_fallback_rows"), "fallback rows")
            for report in reports
        ),
        locally_supervised_execution=locally_supervised_execution,
    )


def _load_and_validate_config(output_directory: Path) -> dict[str, Any]:
    config_path = output_directory / CONFIG_NAME
    captured = output_directory / CAPTURED_RUNNER_NAME
    config = _parse_object(
        _read_bounded(config_path, MAX_RECEIPT_BYTES, "config"), str(config_path)
    )
    required = set(
        _expected_config(
            segment_count=3,
            device=0,
            allow_other_device=False,
            cross_check_serial=False,
            runner_sha256=ZERO_SHA256,
        )
    )
    if set(config) != required:
        raise R2StarCampaignError("campaign config fields changed")
    _validate_parameters(config.get("segment_count"), config.get("device"), None)
    for name in ("allow_other_device", "cross_check_serial"):
        if not isinstance(config.get(name), bool):
            raise R2StarCampaignError(f"{name} must be Boolean")
    digest = _digest(config.get("captured_runner_sha256"), "runner digest")
    expected = _expected_config(
        segment_count=config["segment_count"],
        device=config["device"],
        allow_other_device=config["allow_other_device"],
        cross_check_serial=config["cross_check_serial"],
        runner_sha256=digest,
    )
    if config != expected:
        raise R2StarCampaignError("campaign config values changed")
    captured_raw = _read_bounded(captured, MAX_RUNNER_BYTES, "captured runner")
    if _sha256(captured_raw) != digest:
        raise R2StarCampaignError("captured runner hash differs from config")
    return config


def _verify_campaign_unlocked(output_directory: Path) -> R2StarCampaignResult:
    config = _load_and_validate_config(output_directory)
    reports = _load_receipts(output_directory)
    _check_chain(reports, config)
    result = _result(config, reports, locally_supervised_execution=False)
    manifest_path = output_directory / MANIFEST_NAME
    if manifest_path.exists():
        manifest = _parse_object(
            _read_bounded(manifest_path, MAX_RECEIPT_BYTES, "manifest"),
            str(manifest_path),
        )
        expected = result.as_json()
        expected["locally_supervised_execution"] = True
        if manifest not in (result.as_json(), expected):
            raise R2StarCampaignError("campaign manifest disagrees with receipts")
    return result


def verify_campaign(output_directory: Path) -> R2StarCampaignResult:
    """Verify the immutable setup and the complete retained transition prefix."""

    with advisory_lock(output_directory / ".r2star-campaign.lock"):
        return _verify_campaign_unlocked(output_directory)


def _arithmetic_replay_chunk_row(report: Mapping[str, Any]) -> str:
    """Encode one structurally checked receipt as a native replay row."""

    chunk = verify_runner_receipt(report)
    return "\t".join(
        (
            "chunk",
            str(chunk.lower),
            str(chunk.upper),
            str(chunk.incoming_lower),
            str(chunk.incoming_upper),
            str(chunk.outgoing_lower),
            str(chunk.outgoing_upper),
            str(chunk.minimum_squared_slack),
            str(chunk.minimum_slack_index),
            chunk.factor_support_digest,
            _digest(
                report.get("directed_rows_sha256_le_v1"),
                "directed row digest",
            ),
            str(
                _plain_int(
                    report.get("exact_rational_fallback_rows"),
                    "fallback rows",
                )
            ),
        )
    )


def _arithmetic_replay_plan(
    reports: Sequence[Mapping[str, Any]], *, expected_limit: int
) -> bytes:
    """Encode only retained commitments for the independent native replay."""

    if not reports:
        raise R2StarCampaignError(
            "independent row replay requires at least one receipt"
        )
    rows = [
        ARITHMETIC_REPLAY_PLAN_HEADER,
        f"expected_limit\t{expected_limit}",
        *(_arithmetic_replay_chunk_row(report) for report in reports),
    ]
    return ("\n".join(rows) + "\n").encode("ascii")


def arithmetic_replay_benchmark_plan(
    reports: Sequence[Mapping[str, Any]],
) -> bytes:
    """Encode a bounded, explicitly non-production replay benchmark.

    Unlike the production plan, this format may begin above one.  It exists
    only to calibrate the exact CPU row implementation at representative
    source ordinates.  The distinct header and native output classification
    prevent a bounded timing sample from being accepted by the source-scale
    registered-result path.
    """

    if not reports:
        raise R2StarCampaignError(
            "arithmetic replay benchmark requires at least one receipt"
        )
    chunks = [verify_runner_receipt(report) for report in reports]
    previous: R2StarChunk | None = None
    for index, chunk in enumerate(chunks):
        if previous is not None and (
            chunk.lower,
            chunk.incoming_lower,
            chunk.incoming_upper,
            chunk.previous_hash,
        ) != (
            previous.upper,
            previous.outgoing_lower,
            previous.outgoing_upper,
            previous.record_hash,
        ):
            raise R2StarCampaignError(
                f"benchmark receipt {index} breaks range/state/hash linkage"
            )
        previous = chunk
    lower = chunks[0].lower
    upper = chunks[-1].upper
    rows = [
        ARITHMETIC_REPLAY_BENCHMARK_PLAN_HEADER,
        f"source_range\t{lower}\t{upper}",
        *(_arithmetic_replay_chunk_row(report) for report in reports),
    ]
    return ("\n".join(rows) + "\n").encode("ascii")


def _verify_campaign_arithmetic_unlocked(
    output_directory: Path,
    *,
    arithmetic_replayer: Path,
    expected_arithmetic_replayer_sha256: str | None,
    replay_threads: int,
    replay_segment_rows: int | None,
    replay_timeout_seconds: int | None,
) -> R2StarCampaignResult:
    result = _verify_campaign_unlocked(output_directory)
    if not result.complete:
        raise R2StarCampaignError(
            "independent row replay requires the complete literal source range"
        )
    if isinstance(replay_threads, bool) or not (
        isinstance(replay_threads, int) and 1 <= replay_threads <= 64
    ):
        raise R2StarCampaignError("arithmetic replay threads must lie in [1,64]")
    if replay_segment_rows is not None and (
        isinstance(replay_segment_rows, bool)
        or not isinstance(replay_segment_rows, int)
        or not 1
        <= replay_segment_rows
        <= MAX_ARITHMETIC_REPLAY_SEGMENT_ROWS
    ):
        raise R2StarCampaignError(
            "arithmetic replay segment rows must lie in [1,1000000] "
            "or be null"
        )
    if replay_timeout_seconds is not None and (
        isinstance(replay_timeout_seconds, bool)
        or not isinstance(replay_timeout_seconds, int)
        or replay_timeout_seconds < 1
    ):
        raise R2StarCampaignError(
            "arithmetic replay timeout must be positive or null"
        )
    if expected_arithmetic_replayer_sha256 is not None:
        _digest(
            expected_arithmetic_replayer_sha256,
            "expected arithmetic replayer digest",
        )
    try:
        replay_path = arithmetic_replayer.resolve(strict=True)
        metadata = replay_path.stat()
    except OSError as exc:
        raise R2StarCampaignError(
            f"cannot resolve arithmetic replayer: {exc}"
        ) from exc
    if (
        arithmetic_replayer.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not os.access(replay_path, os.X_OK)
    ):
        raise R2StarCampaignError(
            "arithmetic replayer must be one executable, non-linked regular file"
        )
    replay_bytes = _read_bounded(
        replay_path,
        MAX_ARITHMETIC_REPLAYER_BYTES,
        "arithmetic replayer",
    )
    replay_sha256 = _sha256(replay_bytes)
    if (
        expected_arithmetic_replayer_sha256 is not None
        and replay_sha256 != expected_arithmetic_replayer_sha256
    ):
        raise R2StarCampaignError(
            "arithmetic replayer differs from the reviewed digest"
        )
    reports = _load_receipts(output_directory)
    _check_chain(
        reports,
        _load_and_validate_config(output_directory),
    )
    plan = _arithmetic_replay_plan(reports, expected_limit=result.endpoint)
    try:
        backend = require_azure_measured_worker_for_workload(
            exact_production=True,
            work_bounds=(result.endpoint,),
        )
        challenge = os.environ.get(AZURE_MEASURED_WORKER_CHALLENGE_ENV)
        job_binding = os.environ.get(
            AZURE_MEASURED_WORKER_JOB_BINDING_ENV
        )
        if (
            backend is None
            or not isinstance(challenge, str)
            or not isinstance(job_binding, str)
        ):
            raise MeasuredWorkerScopeError(
                "validated measured-worker binding is incomplete"
            )
        replay_environment = azure_measured_worker_environment(
            {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
            backend=backend,
            challenge_nonce=challenge,
            job_binding=job_binding,
        )
    except MeasuredWorkerScopeError as exc:
        raise R2StarCampaignError(
            f"independent row-arithmetic replay is cloud-only: {exc}"
        ) from exc
    with tempfile.TemporaryDirectory(
        prefix=".r2star-arithmetic-replay-"
    ) as temporary:
        captured_replayer = Path(temporary) / "captured-arithmetic-replayer"
        atomic_write_bytes(captured_replayer, replay_bytes)
        captured_replayer.chmod(0o500)
        plan_path = Path(temporary) / "plan.tsv"
        atomic_write_bytes(plan_path, plan)
        try:
            replay_command = [
                str(captured_replayer),
                "--plan",
                str(plan_path),
                "--threads",
                str(replay_threads),
            ]
            if replay_segment_rows is not None:
                replay_command.extend(
                    ("--segment-rows", str(replay_segment_rows))
                )
            completed = subprocess.run(
                replay_command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=replay_timeout_seconds,
                env=replay_environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise R2StarCampaignError(
                f"independent row-arithmetic replay failed: {exc}"
            ) from exc
    if completed.returncode != 0:
        diagnostic = completed.stderr[-4000:].decode("utf-8", "replace")
        raise R2StarCampaignError(
            "independent row-arithmetic replay rejected the campaign: "
            f"{diagnostic}"
        )
    if len(completed.stdout) > MAX_ARITHMETIC_REPLAY_OUTPUT_BYTES:
        raise R2StarCampaignError(
            "independent row-arithmetic replay emitted oversized output"
        )
    replay_report = _parse_object(
        completed.stdout, "independent row-arithmetic replay stdout"
    )
    expected_report = {
        "checked_chunks": len(reports),
        "checked_rows": result.endpoint,
        "classification": "independent_cpu_full_row_arithmetic_replay_v1",
        "expected_limit": result.endpoint,
        "status": "PASS",
    }
    if replay_report != expected_report:
        raise R2StarCampaignError(
            "independent row-arithmetic replay emitted the wrong exact report"
        )
    return replace(
        result,
        independent_rows_replayed=True,
        arithmetic_replayer_sha256=replay_sha256,
    )


def verify_campaign_arithmetic(
    output_directory: Path,
    *,
    arithmetic_replayer: Path,
    expected_arithmetic_replayer_sha256: str | None = None,
    replay_threads: int = 32,
    replay_segment_rows: int | None = (
        DEFAULT_ARITHMETIC_REPLAY_SEGMENT_ROWS
    ),
    replay_timeout_seconds: int | None = None,
) -> R2StarCampaignResult:
    """Recompute every retained row with the separate CPU implementation."""

    with advisory_lock(output_directory / ".r2star-campaign.lock"):
        return _verify_campaign_arithmetic_unlocked(
            output_directory,
            arithmetic_replayer=arithmetic_replayer,
            expected_arithmetic_replayer_sha256=(
                expected_arithmetic_replayer_sha256
            ),
            replay_threads=replay_threads,
            replay_segment_rows=replay_segment_rows,
            replay_timeout_seconds=replay_timeout_seconds,
        )


def write_registered_result(
    output_directory: Path,
    output: Path,
    *,
    arithmetic_replayer: Path | None = None,
    expected_arithmetic_replayer_sha256: str | None = None,
    replay_threads: int = 32,
    replay_segment_rows: int | None = (
        DEFAULT_ARITHMETIC_REPLAY_SEGMENT_ROWS
    ),
    replay_timeout_seconds: int | None = None,
) -> tuple[R2StarCampaignResult, dict[str, Any]]:
    """Reverify the literal source range and exclusively emit ``true``.

    This is the byte-level terminal expected by the closed Lean invocation.
    It requires an independent CPU reconstruction of every committed row, but
    does not itself prove either native implementation's refinement to Lean:
    that physical-to-formal step remains inside the registered trusted-compute
    execution boundary. Incomplete prefixes, bounded ranges, missing endpoint
    guards/replay, and pre-existing result files fail closed.
    """

    if arithmetic_replayer is None:
        raise R2StarCampaignError(
            "registered result requires the independent full-row arithmetic replayer"
        )
    with advisory_lock(output_directory / ".r2star-campaign.lock"):
        result = _verify_campaign_arithmetic_unlocked(
            output_directory,
            arithmetic_replayer=arithmetic_replayer,
            expected_arithmetic_replayer_sha256=(
                expected_arithmetic_replayer_sha256
            ),
            replay_threads=replay_threads,
            replay_segment_rows=replay_segment_rows,
            replay_timeout_seconds=replay_timeout_seconds,
        )
        if not result.independent_rows_replayed:
            raise R2StarCampaignError(
                "registered result requires full independent row replay"
            )
        if (
            expected_arithmetic_replayer_sha256 is not None
            and result.arithmetic_replayer_sha256
            != expected_arithmetic_replayer_sha256
        ):
            raise R2StarCampaignError(
                "registered result requires the reviewed arithmetic replayer"
            )
        if (
            not result.complete
            or result.endpoint != R2STAR_SOURCE_LIMIT
            or result.completed_upper != R2STAR_SOURCE_LIMIT
            or result.receipts < 1
        ):
            raise R2StarCampaignError(
                "registered R2Star result requires the complete literal source range"
            )
        if (
            result.final_record_hash == ZERO_SHA256
            or result.minimum_squared_slack is None
            or result.minimum_slack_index is None
        ):
            raise R2StarCampaignError(
                "registered R2Star result requires the final chain and endpoint guard"
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor: int | None = None
        try:
            descriptor = os.open(
                output,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | os.O_CLOEXEC
                | os.O_NOFOLLOW,
                0o400,
            )
            if os.write(descriptor, REGISTERED_RESULT) != len(REGISTERED_RESULT):
                raise R2StarCampaignError("short registered-result write")
            os.fsync(descriptor)
        except FileExistsError as exc:
            raise R2StarCampaignError(
                f"refusing to overwrite an existing R2Star result artifact: {output}"
            ) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
        return result, {
            "path": str(output.resolve()),
            "sha256": REGISTERED_RESULT_SHA256,
            "bytes": len(REGISTERED_RESULT),
            "format": "canonical_boolean_true_no_newline_v1",
            "refinement_scope": "independent_cpu_full_row_arithmetic_replay_v1",
            "arithmetic_replayer_sha256": (
                result.arithmetic_replayer_sha256
            ),
            "arithmetic_replay_threads": replay_threads,
            "arithmetic_replay_segment_rows": replay_segment_rows,
        }


def run_campaign(
    *,
    runner: Path,
    output_directory: Path,
    segment_count: int = 1_000_000,
    device: int = 0,
    allow_other_device: bool = False,
    cross_check_serial: bool = False,
    max_chunks: int | None = None,
    chunk_timeout_seconds: int | None = None,
) -> R2StarCampaignResult:
    """Start or resume the source-range campaign from its verified prefix."""

    _validate_parameters(segment_count, device, max_chunks)
    if chunk_timeout_seconds is not None and (
        isinstance(chunk_timeout_seconds, bool)
        or not isinstance(chunk_timeout_seconds, int)
        or chunk_timeout_seconds < 1
    ):
        raise R2StarCampaignError("chunk timeout must be positive or null")
    output_directory.mkdir(parents=True, exist_ok=True)
    with advisory_lock(output_directory / ".r2star-campaign.lock"):
        captured, config = _initialize_or_check(
            runner=runner,
            output_directory=output_directory,
            segment_count=segment_count,
            device=device,
            allow_other_device=allow_other_device,
            cross_check_serial=cross_check_serial,
        )
        reports = _load_receipts(output_directory)
        _check_chain(reports, config)
        chunks_run = 0
        while (
            not reports
            or verify_runner_receipt(reports[-1]).upper <= R2STAR_SOURCE_LIMIT
        ) and (max_chunks is None or chunks_run < max_chunks):
            previous = None if not reports else verify_runner_receipt(reports[-1])
            lower = 1 if previous is None else previous.upper
            if lower > R2STAR_SOURCE_LIMIT:
                break
            count = min(segment_count, R2STAR_SOURCE_LIMIT - lower + 1)
            command = [
                str(captured.resolve()),
                "--lower",
                str(lower),
                "--count",
                str(count),
                "--device",
                str(device),
            ]
            if allow_other_device:
                command.append("--allow-other-device")
            if cross_check_serial:
                command.append("--cross-check-serial")
            if previous is not None:
                command.extend(
                    [
                        "--incoming-lower",
                        str(previous.outgoing_lower),
                        "--incoming-upper",
                        str(previous.outgoing_upper),
                        "--previous-hash",
                        previous.record_hash,
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
                raise R2StarCampaignError(f"campaign runner failed: {exc}") from exc
            if completed.returncode != 0:
                diagnostic = completed.stderr[:4096].decode("utf-8", errors="replace")
                raise R2StarCampaignError(
                    f"campaign runner returned {completed.returncode}: {diagnostic}"
                )
            if len(completed.stdout) > MAX_RECEIPT_BYTES:
                raise R2StarCampaignError("campaign runner emitted an oversized receipt")
            report = _parse_object(completed.stdout, "runner stdout")
            chunk = verify_runner_receipt(report)
            if chunk.lower != lower or chunk.upper != lower + count:
                raise R2StarCampaignError("runner receipt range differs from request")
            expected_previous = ZERO_SHA256 if previous is None else previous.record_hash
            expected_state = (
                (0, 0)
                if previous is None
                else (previous.outgoing_lower, previous.outgoing_upper)
            )
            if chunk.previous_hash != expected_previous or (
                chunk.incoming_lower,
                chunk.incoming_upper,
            ) != expected_state:
                raise R2StarCampaignError("runner receipt does not use requested state")
            receipt_path = output_directory / f"receipt-{len(reports):08d}.json"
            if receipt_path.exists():
                raise R2StarCampaignError("refusing to replace a receipt")
            atomic_write_bytes(receipt_path, completed.stdout)
            reports.append(report)
            chunks_run += 1
        _check_chain(reports, config)
        result = _result(config, reports, locally_supervised_execution=True)
        atomic_write_bytes(output_directory / MANIFEST_NAME, _json_bytes(result.as_json()))
        return result
