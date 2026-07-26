# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Persistent large-q composition/FFT/completed-L pipeline supervisor.

The supervisor launches exactly three long-lived processes for one modulus
shard.  It never interprets process success as Platt's theorem: its receipt
only proves that the bounded component streams and their hashes line up.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Mapping, NoReturn, Sequence

from tg_verifier.dirichlet_residue_composition import (
    FRAMED_REQUEST_SCHEMA,
    canonical_json_bytes,
    load_job,
)
from tg_verifier.dirichlet_allchars_stage import canonical_component_orders
from tg_verifier.dirichlet_root_number_stage import (
    ROOT_ALGORITHM_ID,
    read_root_artifact,
)
from tg_verifier.dirichlet_stream_zero_consumer import (
    COMPACT_EVENT_STORAGE_MODE,
    RAW_EVENT_STORAGE_MODE,
    validate_control,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-dirichlet-largeq-persistent-pipeline-v1"
RECEIPT_SCHEMA = "sparkinterval.tg.dirichlet_largeq_pipeline.receipt.v1"
MAX_CONTROL_BYTES = 256 * 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024


class DirichletLargeQPipelineError(RuntimeError):
    """A control, child process, or cross-stage binding failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletLargeQPipelineError(message)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _canonical_line(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletLargeQPipelineError(f"invalid {label}") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail(f"{label} is not one canonical JSON line")
    return value


def _bounded_read(path: Path, bound: int, *, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        _fail(f"{label} is missing or is not a regular file")
    size = path.stat().st_size
    if size <= 0 or size > bound:
        _fail(f"{label} size is outside 1..{bound}")
    return path.read_bytes()


def _load_json(path: Path, *, label: str, canonical: bool) -> dict[str, Any]:
    raw = _bounded_read(path, MAX_JSON_BYTES, label=label)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletLargeQPipelineError(f"invalid {label} JSON") from error
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    if canonical and canonical_json_bytes(value) != raw:
        _fail(f"{label} is not canonical JSON")
    return value


@dataclass(frozen=True)
class ControlInventory:
    q: int
    frame_count: int
    slice_count: int
    value_count: int
    first_t_numerator: int
    t_denominator: int
    t_step_numerator: int
    stop_t_numerator: int
    composition_sha256: str
    consumer_sha256: str


def validate_control_alignment(
    composition_control_path: Path,
    consumer_control_path: Path,
    *,
    base: Path,
    maximum_batch_count: int,
    allow_synthetic_kat: bool = False,
) -> ControlInventory:
    """Bind every composition request to the corresponding consumer frame."""

    if maximum_batch_count <= 0:
        _fail("maximum batch count must be positive")
    composition_raw = _bounded_read(
        composition_control_path, MAX_CONTROL_BYTES, label="composition controls"
    )
    consumer_raw = _bounded_read(
        consumer_control_path, MAX_CONTROL_BYTES, label="consumer controls"
    )
    composition_lines = composition_raw.splitlines(keepends=True)
    consumer_lines = consumer_raw.splitlines(keepends=True)
    if not composition_lines or len(composition_lines) != len(consumer_lines):
        _fail("composition and consumer control frame counts differ")

    q: int | None = None
    next_numerator: int | None = None
    denominator: int | None = None
    step: int | None = None
    slices = 0
    values = 0
    first_numerator: int | None = None
    receipt_paths: set[Path] = set()
    for index, (composition_line, consumer_line) in enumerate(
        zip(composition_lines, consumer_lines)
    ):
        request = _canonical_line(
            composition_line, label=f"composition control {index}"
        )
        if set(request) != {"schema", "schema_version", "job", "receipt"} or (
            request.get("schema") != FRAMED_REQUEST_SCHEMA
            or request.get("schema_version") != 1
        ):
            _fail(f"composition control {index} schema differs")
        job_raw = request.get("job")
        receipt_raw = request.get("receipt")
        if not isinstance(job_raw, str) or not isinstance(receipt_raw, str):
            _fail(f"composition control {index} paths are malformed")
        job_path = Path(job_raw)
        receipt_path = Path(receipt_raw)
        if not job_path.is_absolute():
            job_path = base / job_path
        if not receipt_path.is_absolute():
            receipt_path = base / receipt_path
        receipt_path = receipt_path.resolve()
        if receipt_path in receipt_paths:
            _fail("composition receipt paths are not unique")
        receipt_paths.add(receipt_path)
        job = load_job(
            job_path,
            allow_synthetic_kat=allow_synthetic_kat,
            max_batch_count=maximum_batch_count,
        )
        control = validate_control(
            _canonical_line(consumer_line, label=f"consumer control {index}"),
            expected_frame_index=index,
            expected_root_number_mode=ROOT_ALGORITHM_ID,
        )
        identity = (
            job.q,
            len(job.frames),
            job.first_t_numerator,
            job.t_denominator,
            job.t_step_numerator,
        )
        consumer_identity = (
            control["q"],
            control["batch_count"],
            control["first_t_numerator"],
            control["t_denominator"],
            control["t_step_numerator"],
        )
        if identity != consumer_identity:
            _fail(f"consumer control {index} differs from its composition job")
        if q is None:
            q = job.q
            denominator = job.t_denominator
            step = job.t_step_numerator
            first_numerator = job.first_t_numerator
        elif (
            job.q != q
            or job.t_denominator != denominator
            or job.t_step_numerator != step
            or job.first_t_numerator != next_numerator
        ):
            _fail("composition controls are not one contiguous modulus shard")
        next_numerator = (
            job.first_t_numerator + len(job.frames) * job.t_step_numerator
        )
        slices += len(job.frames)
        values += len(job.frames) * math.prod(canonical_component_orders(job.q))
    assert q is not None
    assert first_numerator is not None
    assert denominator is not None
    assert step is not None
    assert next_numerator is not None
    return ControlInventory(
        q=q,
        frame_count=len(composition_lines),
        slice_count=slices,
        value_count=values,
        first_t_numerator=first_numerator,
        t_denominator=denominator,
        t_step_numerator=step,
        stop_t_numerator=next_numerator,
        composition_sha256=sha256_bytes(composition_raw),
        consumer_sha256=sha256_bytes(consumer_raw),
    )


def _artifact_record(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        _fail(f"unsafe or missing artifact: {path}")
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        _fail(f"refusing to replace immutable pipeline receipt: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(canonical_json_bytes(dict(value)))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _terminate(processes: Sequence[subprocess.Popen[bytes]]) -> None:
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
    for process in reversed(processes):
        if process.poll() is None:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def _self_hash(value: Mapping[str, Any], field: str, *, label: str) -> None:
    body = dict(value)
    claimed = body.pop(field, None)
    if claimed != sha256_bytes(canonical_json_bytes(body)):
        _fail(f"{label} self-hash differs")


def run_pipeline(
    *,
    composition_controls: Path,
    consumer_controls: Path,
    control_base: Path,
    composer_python: Path,
    composer_tool: Path,
    allchars_runner: Path,
    consumer_python: Path,
    consumer_tool: Path,
    root_artifact: Path,
    root_receipt: Path,
    output_directory: Path,
    pipeline_receipt: Path,
    maximum_batch_count: int = 64,
    device: int = 0,
    precision: int = 192,
    allow_synthetic_kat: bool = False,
    environment: Mapping[str, str] | None = None,
    consumer_timing_output: Path | None = None,
    maximum_event_bytes: int | None = None,
    event_storage_mode: str = RAW_EVENT_STORAGE_MODE,
) -> dict[str, Any]:
    """Run one q shard through three persistent, back-pressured processes."""

    inventory = validate_control_alignment(
        composition_controls,
        consumer_controls,
        base=control_base,
        maximum_batch_count=maximum_batch_count,
        allow_synthetic_kat=allow_synthetic_kat,
    )
    root_receipt_value = _load_json(
        root_receipt, label="root receipt", canonical=True
    )
    try:
        root_metadata, _roots = read_root_artifact(root_artifact, root_receipt_value)
    except Exception as error:
        raise DirichletLargeQPipelineError(
            f"root artifact failed validation: {error}"
        ) from error
    if root_metadata["q"] != inventory.q:
        _fail("root artifact q differs from the pipeline controls")

    if output_directory.exists():
        if not output_directory.is_dir() or any(output_directory.iterdir()):
            _fail("pipeline output directory must be absent or empty")
    output_directory.mkdir(parents=True, exist_ok=True)
    composer_summary_path = output_directory / "composer-summary.json"
    transform_summary_path = output_directory / "transform-summary.json"
    if event_storage_mode not in {
        RAW_EVENT_STORAGE_MODE,
        COMPACT_EVENT_STORAGE_MODE,
    }:
        _fail("unsupported event storage mode")
    events_path = output_directory / (
        "events.ndjson"
        if event_storage_mode == RAW_EVENT_STORAGE_MODE
        else "events-summary.json"
    )
    consumer_receipt_path = output_directory / "consumer-receipt.json"
    composer_stderr_path = output_directory / "composer.stderr"
    transform_stderr_path = output_directory / "transform.stderr"
    consumer_stderr_path = output_directory / "consumer.stderr"
    consumer_stdout_path = output_directory / "consumer.stdout"

    composer_command = [
        # Do not collapse a virtual-environment interpreter symlink to the
        # system Python: that silently discards the pinned site-packages used
        # by the FLINT consumer.
        str(composer_python.absolute()),
        str(composer_tool.resolve()),
        "--max-batch-count",
        str(maximum_batch_count),
        "framed-produce",
        str(composer_summary_path),
        "--base",
        str(control_base.resolve()),
    ]
    if allow_synthetic_kat:
        composer_command.append("--allow-synthetic-kat")
    transform_command = [
        str(allchars_runner.resolve()),
        "--framed-service",
        str(inventory.q),
        str(maximum_batch_count),
        str(transform_summary_path),
        str(device),
    ]
    consumer_command = [
        str(consumer_python.absolute()),
        str(consumer_tool.resolve()),
        "consume",
        str(consumer_controls.resolve()),
        "-",
        str(events_path),
        str(consumer_receipt_path),
        "--precision",
        str(precision),
        "--root-artifact",
        str(root_artifact.resolve()),
        "--root-receipt",
        str(root_receipt.resolve()),
    ]
    if consumer_timing_output is not None:
        if consumer_timing_output.exists():
            _fail("consumer diagnostic timing output already exists")
        consumer_command.extend(
            ["--timing-output", str(consumer_timing_output.resolve())]
        )
    if maximum_event_bytes is not None:
        if (
            isinstance(maximum_event_bytes, bool)
            or not isinstance(maximum_event_bytes, int)
            or maximum_event_bytes <= 0
        ):
            _fail("maximum event bytes must be a positive integer")
        consumer_command.extend(
            ["--maximum-event-bytes", str(maximum_event_bytes)]
        )
    consumer_command.extend(
        ["--event-storage-mode", event_storage_mode]
    )

    processes: list[subprocess.Popen[bytes]] = []
    child_environment = dict(os.environ if environment is None else environment)
    with (
        composition_controls.open("rb") as controls,
        composer_stderr_path.open("wb") as composer_stderr,
        transform_stderr_path.open("wb") as transform_stderr,
        consumer_stderr_path.open("wb") as consumer_stderr,
        consumer_stdout_path.open("wb") as consumer_stdout,
    ):
        try:
            composer = subprocess.Popen(
                composer_command,
                stdin=controls,
                stdout=subprocess.PIPE,
                stderr=composer_stderr,
                cwd=control_base,
                env=child_environment,
            )
            processes.append(composer)
            assert composer.stdout is not None
            transform = subprocess.Popen(
                transform_command,
                stdin=composer.stdout,
                stdout=subprocess.PIPE,
                stderr=transform_stderr,
                cwd=control_base,
                env=child_environment,
            )
            processes.append(transform)
            composer.stdout.close()
            assert transform.stdout is not None
            consumer = subprocess.Popen(
                consumer_command,
                stdin=transform.stdout,
                stdout=consumer_stdout,
                stderr=consumer_stderr,
                cwd=control_base,
                env=child_environment,
            )
            processes.append(consumer)
            transform.stdout.close()
            consumer_code = consumer.wait()
            transform_code = transform.wait()
            composer_code = composer.wait()
        except BaseException:
            _terminate(processes)
            raise
    return_codes = {
        "composer": composer_code,
        "transform": transform_code,
        "consumer": consumer_code,
    }
    if any(code != 0 for code in return_codes.values()):
        _fail(f"persistent pipeline process failed: {return_codes}")

    composer_summary = _load_json(
        composer_summary_path, label="composer summary", canonical=True
    )
    _self_hash(composer_summary, "summary_sha256", label="composer summary")
    transform_summary = _load_json(
        transform_summary_path, label="transform summary", canonical=False
    )
    consumer_receipt_value = _load_json(
        consumer_receipt_path, label="consumer receipt", canonical=True
    )
    _self_hash(consumer_receipt_value, "receipt_sha256", label="consumer receipt")
    if (
        composer_summary.get("q") != inventory.q
        or transform_summary.get("q") != inventory.q
        or composer_summary.get("frame_count") != inventory.frame_count
        or transform_summary.get("frame_count") != inventory.frame_count
        or consumer_receipt_value.get("frame_count") != inventory.frame_count
        or composer_summary.get("slice_count") != inventory.slice_count
        or transform_summary.get("slice_count") != inventory.slice_count
        or composer_summary.get("value_count") != inventory.value_count
        or composer_summary.get("value_count") != transform_summary.get("value_count")
        or transform_summary.get("value_count") != consumer_receipt_value.get("value_count")
    ):
        _fail("persistent pipeline coverage counters differ")
    if (
        composer_summary.get("control_jsonl_sha256")
        != inventory.composition_sha256
        or consumer_receipt_value.get("control_stream_sha256")
        != inventory.consumer_sha256
        or composer_summary.get("TGDAFFI1_stream_sha256")
        != transform_summary.get("input_stream_sha256")
        or transform_summary.get("output_stream_sha256")
        != consumer_receipt_value.get("transform_stream_sha256")
    ):
        _fail("persistent pipeline cross-stage stream hashes differ")
    if (
        consumer_receipt_value.get("root_number_mode") != ROOT_ALGORITHM_ID
        or consumer_receipt_value.get("root_number_artifact_supplied") is not True
        or consumer_receipt_value.get("source_performance_ready") is not True
        or consumer_receipt_value.get("external_atom_discharged") is not False
    ):
        _fail("consumer root-artifact or claim boundary differs")

    receipt: dict[str, Any] = {
        "algorithm_id": ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "author": AUTHOR,
        "classification": "persistent_component_pipeline_not_zero_or_grh_closure",
        "component_processes_persistent": True,
        "external_atom_discharged": False,
        "frame_count": inventory.frame_count,
        "full_source_campaign_run": False,
        "kind": RECEIPT_SCHEMA,
        "maximum_batch_count": maximum_batch_count,
        "process_return_codes": return_codes,
        "q": inventory.q,
        "ordinate_grid": {
            "first_t_numerator": inventory.first_t_numerator,
            "stop_t_numerator_exclusive": inventory.stop_t_numerator,
            "t_denominator": inventory.t_denominator,
            "t_step_numerator": inventory.t_step_numerator,
            "slice_count": inventory.slice_count,
        },
        "controls": {
            "composition": _artifact_record(composition_controls),
            "consumer": _artifact_record(consumer_controls),
        },
        "root_artifact": _artifact_record(root_artifact),
        "root_receipt": _artifact_record(root_receipt),
        "source_performance_ready_for_wired_components": True,
        "summaries": {
            "composer": _artifact_record(composer_summary_path),
            "consumer": _artifact_record(consumer_receipt_path),
            "events": _artifact_record(events_path),
            "transform": _artifact_record(transform_summary_path),
        },
        "stream_bindings_verified": True,
        "zero_completeness_claimed": False,
    }
    receipt["receipt_sha256"] = sha256_bytes(canonical_json_bytes(receipt))
    _atomic_json(pipeline_receipt, receipt)
    return receipt


def capability() -> dict[str, Any]:
    return {
        "algorithm_id": ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "classification": "production_process_graph_capability_not_external_evidence",
        "external_atom_discharged": False,
        "implemented": [
            "one persistent framed residue composer per q shard",
            "one persistent q-specific CUDA all-character transform plan",
            "one persistent completed-L consumer using TGDRNRO1",
            "OS-pipe backpressure with no campaign-wide transform materialization",
            "failure propagation and immutable stderr/stdout diagnostics",
            "cross-stage input/output SHA-256 and coverage-counter binding",
        ],
        "production_component_graph_ready": True,
        "source_t_major_schedule_contract_implemented": True,
        "source_root_catalog_contract_implemented": True,
        "typed_fft_pipeline_receipt_bundle_validator_implemented": True,
        "t_major_typed_bundle_admission_adapter_implemented": True,
        "typed_bundle_lattice_payload_to_cache_row_binding_implemented": True,
        "t_major_shared_row_spool_and_fixed_q_roster_implemented": True,
        "t_major_row_resident_seeded_cuda_component_implemented": True,
        "t_major_direct_MPFR_factor_and_exact_tail_source_implemented": True,
        "fixed_q_pipeline_executor_consumes_spool_format": False,
        "typed_fft_pipeline_receipt_bundle_integrated_into_t_major_lane": False,
        "source_t_major_graph_integrated": False,
        "remaining": [
            (
                "populate the lattice/recovery/root inputs, connect the "
                "implemented row-resident CUDA TGDAFFI1 stream to the "
                "persistent multi-q FFT/typed-bundle lane, and implement the "
                "zero-state adapters"
            ),
            "exception refinement, zero isolation, and accepted Turing completeness",
            "full independent campaign replay and Lean evidence bridge",
        ],
        "zero_completeness_claimed": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "ControlInventory",
    "DirichletLargeQPipelineError",
    "capability",
    "run_pipeline",
    "validate_control_alignment",
]
