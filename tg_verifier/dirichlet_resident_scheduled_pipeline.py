# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded direct resident-q-major/FFT/completed-L process graph.

This supervisor is the no-materialization counterpart of
``dirichlet_scheduled_largeq_pipeline``.  It replaces that pipeline's
file-oriented composition producer with the source-shaped resident q-major
CUDA producer, while retaining the existing scheduled all-character service
and the existing Arb completed-L/sign consumer.

The first implementation intentionally accepts only a bounded TGDQORD1 whose
entire t-range is covered by one resident phase.  A source campaign is split
across ten t-major phases, whereas the current scheduled consumer requires one
uninterrupted t=0-through-terminal stream for every q.  Carrying its
multiplicity-preserving sign state across those phase boundaries is a separate
explicit seam; this module does not pretend that a single bounded run closes
it.

No TGDAFFI1 or TGDAFFO1 regular file is created.  The producer, transform, and
consumer are joined by OS pipes; their independently computed ordered stream
digests, exact counts, immutable TGDQORD1 digest, phase-plan digest, sidecar
target root, and root-catalog root are checked after all children exit.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping, NoReturn

from tg_verifier.dirichlet_allchars_q_scheduler import (
    BOUNDED_CLASSIFICATION,
    ParsedScheduleManifest,
    parse_schedule_manifest,
    phase_schedule_projection,
    validate_phase_scheduled_multiq_framed_summary_commitments,
    validate_scheduled_multiq_framed_summary_commitments,
)
from tg_verifier.dirichlet_allchars_stage import (
    COMPLEX_INTERVAL,
    OUTPUT_HEADER,
)
from tg_verifier.dirichlet_resident_qmajor_stream import (
    BOUNDED_PROJECTION_COVERAGE,
    SCHEDULE_CLASSIFICATION_BOUNDED,
    ParsedRowArtifact,
    ParsedSidecarArtifact,
    StreamPlan,
    iter_stream_targets,
    replay_row_artifact,
    replay_sidecar_artifact,
    validate_streamed_cuda_summary,
)
from tg_verifier.dirichlet_root_number_stage import ROOT_ALGORITHM_ID
from tg_verifier.dirichlet_scheduled_largeq_pipeline import (
    DEFAULT_BOUNDED_PROCESS_TIMEOUT_SECONDS,
    MAX_CONTROL_BYTES,
    MAX_DIAGNOSTIC_BYTES,
    MAX_JSON_BYTES,
    _artifact_record,
    _atomic_json,
    _bounded_optional_read,
    _bounded_read,
    _canonical_line,
    _canonical_object,
    _invocation_artifact_record,
    _prepare_empty_output_directory,
    _schedule_binding,
    _self_hash,
    _terminate,
    _validate_consumer_event_binding,
    _validate_root_catalog_for_schedule,
    _wait_fail_fast,
    sha256_bytes,
)
from tg_verifier.dirichlet_stream_zero_consumer import (
    MAX_EVENT_OUTPUT_BYTES,
    PHASE_COMPACT_BUNDLE_STORAGE_MODE,
    RAW_EVENT_STORAGE_MODE,
    validate_control,
    validate_phase_compact_state_bundle,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = (
    "platt-dirichlet-resident-qmajor-scheduled-direct-pipeline-v1"
)
RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_resident_scheduled_pipeline.receipt.v1"
)
CONTROL_TARGET_DOMAIN = (
    b"TG_DIRICHLET_RESIDENT_SCHEDULED_CONTROL_TARGET_V1"
)


class DirichletResidentScheduledPipelineError(RuntimeError):
    """A resident producer/FFT/consumer graph invariant failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletResidentScheduledPipelineError(message)


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} is not lowercase SHA-256")
    return value


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(f"{label} must be a positive integer")
    return value


@dataclass(frozen=True)
class ResidentControlInventory:
    """Exact correspondence between canonical controls and resident targets."""

    schedule: ParsedScheduleManifest
    frame_count: int
    slice_count: int
    value_count: int
    first_q: int
    last_q: int
    control_sha256: str
    control_target_chain_sha256: str


def validate_resident_control_alignment(
    consumer_control_path: Path,
    *,
    schedule_manifest_path: Path,
    plan: StreamPlan,
) -> ResidentControlInventory:
    """Match every canonical consumer record to one resident stream target."""

    return _validate_resident_control_alignment(
        consumer_control_path,
        schedule_manifest_path=schedule_manifest_path,
        plan=plan,
        require_complete_schedule=True,
    )


def validate_resident_phase_control_alignment(
    consumer_control_path: Path,
    *,
    schedule_manifest_path: Path,
    plan: StreamPlan,
) -> ResidentControlInventory:
    """Match controls for one bounded fixed-q t-phase.

    Unlike :func:`validate_resident_control_alignment`, this intentionally
    permits a positive t start and partial TGDQORD1 row coverage.  It requires
    exactly one active q so the existing fixed-q compact sign-state consumer
    can emit a restart state at phase EOF.
    """

    return _validate_resident_control_alignment(
        consumer_control_path,
        schedule_manifest_path=schedule_manifest_path,
        plan=plan,
        require_complete_schedule=False,
        require_fixed_q=True,
    )


def validate_resident_multiq_phase_control_alignment(
    consumer_control_path: Path,
    *,
    schedule_manifest_path: Path,
    plan: StreamPlan,
) -> ResidentControlInventory:
    """Match every control to one exact partial-t multi-q resident target."""

    return _validate_resident_control_alignment(
        consumer_control_path,
        schedule_manifest_path=schedule_manifest_path,
        plan=plan,
        require_complete_schedule=False,
        require_fixed_q=False,
    )


def _validate_resident_control_alignment(
    consumer_control_path: Path,
    *,
    schedule_manifest_path: Path,
    plan: StreamPlan,
    require_complete_schedule: bool,
    require_fixed_q: bool = False,
) -> ResidentControlInventory:
    if (
        not isinstance(require_complete_schedule, bool)
        or not isinstance(require_fixed_q, bool)
        or (require_complete_schedule and require_fixed_q)
    ):
        _fail("resident control coverage mode is malformed")

    try:
        schedule = parse_schedule_manifest(schedule_manifest_path)
    except RuntimeError as error:
        raise DirichletResidentScheduledPipelineError(
            f"TGDQORD1 validation failed: {error}"
        ) from error
    if schedule.classification != BOUNDED_CLASSIFICATION:
        _fail(
            "resident direct integration currently requires a bounded "
            "single-phase TGDQORD1"
        )
    common_valid = (
        plan.schedule_classification == SCHEDULE_CLASSIFICATION_BOUNDED
        and plan.coverage_mode == BOUNDED_PROJECTION_COVERAGE
        and plan.target_count > 0
    )
    complete_valid = (
        plan.start_execution_q_index == 0
        and plan.stop_execution_q_index
        == len(schedule.execution_records)
        and plan.loaded_first_t_index == 0
        and plan.active_q_count == schedule.q_count
        and plan.target_row_reference_count == schedule.t_row_count
        and all(
            record.t_index_count <= plan.loaded_t_index_stop_exclusive
            for record in schedule.execution_records
        )
    )
    phase_valid = (
        plan.active_q_count == 1
        if require_fixed_q
        else plan.active_q_count > 0
    )
    if not common_valid or (
        require_complete_schedule and not complete_valid
    ) or (not require_complete_schedule and not phase_valid):
        _fail(
            (
                "resident plan does not exactly cover the bounded "
                "TGDQORD1 from t=0"
                if require_complete_schedule
                else (
                    "resident phase plan is not one active fixed-q slice"
                    if require_fixed_q
                    else "resident multi-q phase plan has no active target"
                )
            )
        )
    if not require_complete_schedule and not require_fixed_q:
        try:
            projection = phase_schedule_projection(
                schedule_manifest_path,
                phase_plan_sha256=plan.phase_plan_sha256,
                first_t_index=plan.loaded_first_t_index,
                t_index_stop_exclusive=(
                    plan.loaded_t_index_stop_exclusive
                ),
                start_execution_q_index=(
                    plan.start_execution_q_index
                ),
                stop_execution_q_index=plan.stop_execution_q_index,
            )
        except RuntimeError as error:
            raise DirichletResidentScheduledPipelineError(
                f"resident phase projection failed: {error}"
            ) from error
        if (
            projection.active_modulus_count != plan.active_q_count
            or projection.t_index_row_count
            != plan.target_row_reference_count
        ):
            _fail("resident multi-q phase projection and plan counts differ")

    raw = _bounded_read(
        consumer_control_path,
        MAX_CONTROL_BYTES,
        label="resident consumer controls",
    )
    lines = raw.splitlines(keepends=True)
    targets = tuple(iter_stream_targets(schedule, plan))
    if not lines or len(lines) != len(targets):
        _fail("resident controls and q-major target counts differ")

    chain = hashlib.sha256(CONTROL_TARGET_DOMAIN)
    chain.update(bytes.fromhex(schedule.manifest_sha256))
    chain.update(bytes.fromhex(plan.phase_plan_sha256))
    slice_count = 0
    for frame_index, (line, target) in enumerate(
        zip(lines, targets, strict=True)
    ):
        try:
            control = validate_control(
                _canonical_line(
                    line, label=f"resident consumer control {frame_index}"
                ),
                expected_frame_index=frame_index,
                expected_root_number_mode=ROOT_ALGORITHM_ID,
            )
        except RuntimeError as error:
            raise DirichletResidentScheduledPipelineError(
                f"resident consumer control {frame_index} failed: {error}"
            ) from error
        expected = (
            target.q,
            target.batch_count,
            target.first_t_index * 5,
            64,
            5,
        )
        observed = (
            control["q"],
            control["batch_count"],
            control["first_t_numerator"],
            control["t_denominator"],
            control["t_step_numerator"],
        )
        if observed != expected:
            _fail(
                f"resident consumer control {frame_index} differs from "
                "its q-major target"
            )
        chain.update(target.packed())
        chain.update(hashlib.sha256(line).digest())
        slice_count += target.batch_count

    return ResidentControlInventory(
        schedule=schedule,
        frame_count=len(targets),
        slice_count=slice_count,
        value_count=plan.value_count,
        first_q=targets[0].q,
        last_q=targets[-1].q,
        control_sha256=sha256_bytes(raw),
        control_target_chain_sha256=chain.hexdigest(),
    )


def _validate_transform_summary(
    value: Mapping[str, Any],
    *,
    inventory: ResidentControlInventory,
    plan: StreamPlan,
    maximum_batch_count: int,
) -> None:
    """Validate the metadata available without retaining either raw stream."""

    del plan
    try:
        validate_scheduled_multiq_framed_summary_commitments(
            value,
            manifest=inventory.schedule.raw,
            maximum_batch_count=maximum_batch_count,
            input_stream_sha256=_digest(
                value.get("input_stream_sha256"),
                "resident transform input stream",
            ),
            output_stream_sha256=_digest(
                value.get("output_stream_sha256"),
                "resident transform output stream",
            ),
        )
    except RuntimeError as error:
        raise DirichletResidentScheduledPipelineError(
            f"resident transform commitment replay failed: {error}"
        ) from error


def run_resident_scheduled_pipeline(
    *,
    consumer_controls: Path,
    schedule_manifest: Path,
    plan: StreamPlan,
    recovery_seed_artifact: Path,
    recovery_seed_sha256: str,
    row_artifact: Path,
    row_artifact_sha256: str,
    sidecar_artifact: Path,
    sidecar_artifact_sha256: str,
    resident_runner: Path,
    allchars_runner: Path,
    consumer_python: Path,
    consumer_tool: Path,
    root_catalog: Path,
    root_catalog_sha256: str,
    root_catalog_directory: Path,
    output_directory: Path,
    pipeline_receipt: Path,
    maximum_batch_count: int = 64,
    device: int = 0,
    precision: int = 192,
    process_timeout_seconds: float = (
        DEFAULT_BOUNDED_PROCESS_TIMEOUT_SECONDS
    ),
    allow_prefix_kat: bool = False,
    qualification_phase_bundle: bool = False,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run the bounded direct-pipe resident/FFT/completed-L graph."""

    if (
        isinstance(maximum_batch_count, bool)
        or not isinstance(maximum_batch_count, int)
        or maximum_batch_count != 64
    ):
        _fail("resident q-major target protocol requires batch bound 64")
    if (
        isinstance(device, bool)
        or not isinstance(device, int)
        or device < 0
    ):
        _fail("device must be a nonnegative integer")
    if (
        isinstance(precision, bool)
        or not isinstance(precision, int)
        or precision <= 0
    ):
        _fail("precision must be a positive integer")
    if (
        isinstance(process_timeout_seconds, bool)
        or not isinstance(process_timeout_seconds, (int, float))
        or not 0.0 < float(process_timeout_seconds) < float("inf")
    ):
        _fail("process timeout must be positive and finite")
    if not isinstance(qualification_phase_bundle, bool):
        _fail("qualification phase mode must be boolean")

    inventory = (
        validate_resident_multiq_phase_control_alignment(
            consumer_controls,
            schedule_manifest_path=schedule_manifest,
            plan=plan,
        )
        if qualification_phase_bundle
        else validate_resident_control_alignment(
            consumer_controls,
            schedule_manifest_path=schedule_manifest,
            plan=plan,
        )
    )
    schedule = inventory.schedule
    phase_projection = (
        phase_schedule_projection(
            schedule_manifest,
            phase_plan_sha256=plan.phase_plan_sha256,
            first_t_index=plan.loaded_first_t_index,
            t_index_stop_exclusive=(
                plan.loaded_t_index_stop_exclusive
            ),
            start_execution_q_index=plan.start_execution_q_index,
            stop_execution_q_index=plan.stop_execution_q_index,
        )
        if qualification_phase_bundle
        else None
    )
    try:
        rows: ParsedRowArtifact = replay_row_artifact(
            row_artifact,
            schedule,
            plan,
            expected_input_sha256=_digest(
                row_artifact_sha256, "row artifact"
            ),
        )
        sidecars: ParsedSidecarArtifact = replay_sidecar_artifact(
            sidecar_artifact,
            schedule,
            plan,
            rows,
            expected_input_sha256=_digest(
                sidecar_artifact_sha256, "sidecar artifact"
            ),
        )
    except RuntimeError as error:
        raise DirichletResidentScheduledPipelineError(
            f"resident input replay failed: {error}"
        ) from error
    seed_sha256 = _digest(
        recovery_seed_sha256, "recovery seed artifact"
    )
    seed_record = _artifact_record(recovery_seed_artifact)
    if (
        seed_record["sha256"] != seed_sha256
        or rows.recovery_seed_sha256 != seed_sha256
        or sidecars.recovery_seed_sha256 != seed_sha256
    ):
        _fail("resident seed/row/sidecar binding differs")
    row_record = _artifact_record(row_artifact)
    sidecar_record = _artifact_record(sidecar_artifact)
    if (
        row_record["sha256"] != rows.input_sha256
        or sidecar_record["sha256"] != sidecars.input_sha256
    ):
        _fail("resident input artifact digest differs after replay")
    schedule_record = _artifact_record(schedule_manifest)
    control_record = _artifact_record(consumer_controls)
    root_catalog_record = _artifact_record(root_catalog)
    if (
        schedule_record["sha256"] != schedule.manifest_sha256
        or control_record["sha256"] != inventory.control_sha256
        or root_catalog_record["sha256"] != root_catalog_sha256
    ):
        _fail("resident schedule, controls, or root catalog digest differs")

    try:
        catalog_audit = _validate_root_catalog_for_schedule(
            schedule,
            root_catalog_path=root_catalog,
            root_catalog_sha256=_digest(
                root_catalog_sha256, "root catalog"
            ),
            root_catalog_directory=root_catalog_directory,
            require_full_source=False,
            # The pinned consumer process performs the FLINT parse and exact
            # receipt revalidation.  The supervisor itself may intentionally
            # run under a small Python environment without python-flint.
            revalidate_artifacts=False,
        )
    except RuntimeError as error:
        raise DirichletResidentScheduledPipelineError(str(error)) from error
    _prepare_empty_output_directory(output_directory)

    producer_summary_path = output_directory / "producer-summary.json"
    transform_summary_path = output_directory / "transform-summary.json"
    events_path = output_directory / "events.ndjson"
    consumer_receipt_path = output_directory / "consumer-receipt.json"
    consumer_stdout_path = output_directory / "consumer.stdout"
    stderr_paths = {
        name: output_directory / f"{name}.stderr"
        for name in ("producer", "transform", "consumer")
    }
    component_invocations = {
        "resident_runner": _invocation_artifact_record(
            resident_runner.resolve(), label="resident q-major runner"
        ),
        "allchars_runner": _invocation_artifact_record(
            allchars_runner.resolve(), label="all-character runner"
        ),
        "consumer_python": _invocation_artifact_record(
            consumer_python, label="consumer Python"
        ),
        "consumer_tool": _invocation_artifact_record(
            consumer_tool.resolve(), label="consumer tool"
        ),
    }

    producer_command = [
        str(resident_runner.resolve()),
        str(recovery_seed_artifact.resolve()),
        seed_sha256,
        str(schedule_manifest.resolve()),
        plan.phase_plan_sha256,
        str(row_artifact.resolve()),
        rows.input_sha256,
        str(sidecar_artifact.resolve()),
        sidecars.input_sha256,
        str(producer_summary_path),
        str(device),
    ]
    if allow_prefix_kat:
        producer_command.append("--allow-prefix-kat")
    if qualification_phase_bundle:
        assert phase_projection is not None
        transform_command = [
            str(allchars_runner.resolve()),
            "--bounded-phase-scheduled-multiq-framed-service",
            str(maximum_batch_count),
            "512",
            str(schedule_manifest.resolve()),
            phase_projection.phase_plan_sha256,
            str(phase_projection.first_t_index),
            str(phase_projection.t_index_stop_exclusive),
            str(phase_projection.start_execution_q_index),
            str(phase_projection.stop_execution_q_index),
            str(transform_summary_path),
            str(device),
        ]
    else:
        transform_command = [
            str(allchars_runner.resolve()),
            "--bounded-scheduled-multiq-framed-service",
            str(maximum_batch_count),
            "512",
            str(schedule_manifest.resolve()),
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
        "--schedule-manifest",
        str(schedule_manifest.resolve()),
        "--root-catalog",
        str(root_catalog.resolve()),
        "--root-catalog-sha256",
        str(root_catalog_sha256),
        "--root-catalog-directory",
        str(root_catalog_directory.resolve()),
        "--event-storage-mode",
        (
            PHASE_COMPACT_BUNDLE_STORAGE_MODE
            if qualification_phase_bundle
            else RAW_EVENT_STORAGE_MODE
        ),
    ]
    if qualification_phase_bundle:
        assert phase_projection is not None
        consumer_command.extend(
            [
                "--maximum-event-bytes",
                str(MAX_EVENT_OUTPUT_BYTES),
                "--phase-plan-sha256",
                phase_projection.phase_plan_sha256,
                "--phase-first-t-index",
                str(phase_projection.first_t_index),
                "--phase-stop-t-index-exclusive",
                str(phase_projection.t_index_stop_exclusive),
                "--phase-execution-q-start-index",
                str(phase_projection.start_execution_q_index),
                "--phase-execution-q-stop-index",
                str(phase_projection.stop_execution_q_index),
            ]
        )

    child_environment = dict(os.environ if environment is None else environment)
    processes: list[subprocess.Popen[bytes]] = []
    named_processes: list[tuple[str, subprocess.Popen[bytes]]] = []
    opened: list[Any] = []
    try:
        consumer_stdout = consumer_stdout_path.open("xb")
        opened.append(consumer_stdout)

        def stderr(name: str):
            handle = stderr_paths[name].open("xb")
            opened.append(handle)
            return handle

        producer = subprocess.Popen(
            producer_command,
            stdout=subprocess.PIPE,
            stderr=stderr("producer"),
            env=child_environment,
            start_new_session=True,
        )
        processes.append(producer)
        named_processes.append(("producer", producer))
        assert producer.stdout is not None

        transform = subprocess.Popen(
            transform_command,
            stdin=producer.stdout,
            stdout=subprocess.PIPE,
            stderr=stderr("transform"),
            env=child_environment,
            start_new_session=True,
        )
        producer.stdout.close()
        processes.append(transform)
        named_processes.append(("transform", transform))
        assert transform.stdout is not None

        consumer = subprocess.Popen(
            consumer_command,
            stdin=transform.stdout,
            stdout=consumer_stdout,
            stderr=stderr("consumer"),
            env=child_environment,
            start_new_session=True,
        )
        transform.stdout.close()
        processes.append(consumer)
        named_processes.append(("consumer", consumer))
        return_codes = _wait_fail_fast(
            named_processes,
            timeout_seconds=float(process_timeout_seconds),
            isolated_process_groups=True,
        )
    except BaseException:
        _terminate(processes, isolated_process_groups=True)
        raise
    finally:
        for handle in reversed(opened):
            handle.close()

    for name, path in stderr_paths.items():
        _bounded_optional_read(
            path,
            MAX_DIAGNOSTIC_BYTES,
            label=f"resident {name} stderr",
        )
    _bounded_optional_read(
        consumer_stdout_path,
        MAX_JSON_BYTES,
        label="resident consumer stdout",
    )

    rebound_invocations = {
        "resident_runner": _invocation_artifact_record(
            resident_runner.resolve(), label="resident q-major runner"
        ),
        "allchars_runner": _invocation_artifact_record(
            allchars_runner.resolve(), label="all-character runner"
        ),
        "consumer_python": _invocation_artifact_record(
            consumer_python, label="consumer Python"
        ),
        "consumer_tool": _invocation_artifact_record(
            consumer_tool.resolve(), label="consumer tool"
        ),
    }
    if rebound_invocations != component_invocations:
        _fail("resident pipeline invocation artifact changed during execution")

    transform_raw = _bounded_read(
        transform_summary_path,
        MAX_JSON_BYTES,
        label="resident transform summary",
    )
    try:
        transform_summary = json.loads(transform_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletResidentScheduledPipelineError(
            "invalid resident transform summary"
        ) from error
    if not isinstance(transform_summary, dict):
        _fail("resident transform summary is not an object")
    try:
        if phase_projection is None:
            _validate_transform_summary(
                transform_summary,
                inventory=inventory,
                plan=plan,
                maximum_batch_count=maximum_batch_count,
            )
        else:
            validate_phase_scheduled_multiq_framed_summary_commitments(
                transform_summary,
                projection=phase_projection,
                maximum_batch_count=maximum_batch_count,
                input_stream_sha256=_digest(
                    transform_summary.get("input_stream_sha256"),
                    "resident phase transform input stream",
                ),
                output_stream_sha256=_digest(
                    transform_summary.get("output_stream_sha256"),
                    "resident phase transform output stream",
                ),
            )
    except RuntimeError as error:
        raise DirichletResidentScheduledPipelineError(
            f"resident transform commitment replay failed: {error}"
        ) from error
    try:
        producer_summary = validate_streamed_cuda_summary(
            producer_summary_path,
            schedule,
            rows,
            sidecars,
            output_sha256=_digest(
                transform_summary.get("input_stream_sha256"),
                "transform input stream",
            ),
            output_size_bytes=(
                plan.target_count * 72
                + plan.value_count * COMPLEX_INTERVAL.size
            ),
        )
    except RuntimeError as error:
        raise DirichletResidentScheduledPipelineError(
            f"resident producer summary failed: {error}"
        ) from error

    consumer_receipt = _canonical_object(
        consumer_receipt_path, label="resident consumer receipt"
    )
    _self_hash(
        consumer_receipt,
        "receipt_sha256",
        label="resident consumer receipt",
    )
    _schedule_binding(consumer_receipt, schedule, label="resident consumer")
    events_record = _validate_consumer_event_binding(
        consumer_receipt, events_path
    )
    phase_bundle: dict[str, Any] | None = None
    if phase_projection is not None:
        phase_bundle = _canonical_line(
            _bounded_read(
                events_path,
                MAX_EVENT_OUTPUT_BYTES,
                label="resident phase compact state bundle",
            ),
            label="resident phase compact state bundle",
        )
        try:
            bundle_events, bundle_signs, bundle_ambiguities = (
                validate_phase_compact_state_bundle(
                    phase_bundle,
                    projection=phase_projection,
                )
            )
        except RuntimeError as error:
            raise DirichletResidentScheduledPipelineError(
                f"resident phase compact state bundle failed: {error}"
            ) from error
        if (
            consumer_receipt.get("event_count") != bundle_events
            or consumer_receipt.get("candidate_bracket_count")
            != bundle_signs
            or consumer_receipt.get("indeterminate_sample_count")
            != bundle_ambiguities
        ):
            _fail("resident phase bundle and consumer event totals differ")
    output_size = (
        plan.target_count * OUTPUT_HEADER.size
        + plan.value_count * COMPLEX_INTERVAL.size
    )
    common_receipt_valid = not (
        producer_summary["output_sha256"]
        != transform_summary["input_stream_sha256"]
        or transform_summary["output_stream_sha256"]
        != consumer_receipt.get("transform_stream_sha256")
        or consumer_receipt.get("control_stream_sha256")
        != inventory.control_sha256
        or consumer_receipt.get("frame_count") != inventory.frame_count
        or consumer_receipt.get("value_count") != plan.value_count
        or consumer_receipt.get("root_catalog_sha256")
        != catalog_audit["catalog"]["sha256"]
        or consumer_receipt.get("root_catalog_entry_chain_sha256")
        != catalog_audit["entry_chain_sha256"]
        or consumer_receipt.get("root_catalog_artifacts_revalidated")
        is not True
        or consumer_receipt.get("root_number_artifact_supplied") is not True
        or consumer_receipt.get("external_atom_discharged") is not False
        or consumer_receipt.get("zero_completeness_claimed") is not False
    )
    if phase_projection is None:
        coverage_valid = not (
            consumer_receipt.get("scheduled_modulus_count")
            != schedule.q_count
            or consumer_receipt.get("scheduled_t_index_rows")
            != schedule.t_row_count
            or consumer_receipt.get("TGDQORD1_exact_coverage") is not True
            or consumer_receipt.get("source_performance_ready") is not True
            or consumer_receipt.get("event_storage_mode")
            != RAW_EVENT_STORAGE_MODE
        )
    else:
        coverage_valid = not (
            consumer_receipt.get("scheduled_modulus_count")
            != phase_projection.active_modulus_count
            or consumer_receipt.get("scheduled_t_index_rows")
            != phase_projection.t_index_row_count
            or consumer_receipt.get("TGDQORD1_exact_coverage") is not False
            or consumer_receipt.get("TGDQORD1_parent_manifest_bound")
            is not True
            or consumer_receipt.get("phase_schedule_exact_coverage")
            is not True
            or consumer_receipt.get("phase_schedule_sha256")
            != phase_projection.phase_schedule_sha256
            or consumer_receipt.get("event_storage_mode")
            != PHASE_COMPACT_BUNDLE_STORAGE_MODE
            or consumer_receipt.get(
                "phase_compact_bundle_qualification_only"
            )
            is not True
            or consumer_receipt.get("source_performance_ready") is not False
            or consumer_receipt.get("same_cuda_address_space_reduction")
            is not False
            or consumer_receipt.get("production_accept") is not False
        )
    if not common_receipt_valid or not coverage_valid:
        _fail("resident cross-stage digest, coverage, or root binding differs")
    _positive_integer(output_size, "transform output size")

    rebound_inputs = {
        "recovery_seed": _artifact_record(recovery_seed_artifact),
        "rows": _artifact_record(row_artifact),
        "sidecars": _artifact_record(sidecar_artifact),
        "schedule": _artifact_record(schedule_manifest),
        "controls": _artifact_record(consumer_controls),
        "root_catalog": _artifact_record(root_catalog),
    }
    expected_inputs = {
        "recovery_seed": seed_record,
        "rows": row_record,
        "sidecars": sidecar_record,
        "schedule": schedule_record,
        "controls": control_record,
        "root_catalog": root_catalog_record,
    }
    if rebound_inputs != expected_inputs:
        _fail("resident pipeline input artifact changed during execution")

    summaries = {
        "producer": _artifact_record(producer_summary_path),
        "transform": _artifact_record(transform_summary_path),
        "consumer": _artifact_record(consumer_receipt_path),
        "events": events_record,
    }
    if (
        summaries["producer"]["sha256"]
        != sha256_bytes(
            _bounded_read(
                producer_summary_path,
                MAX_JSON_BYTES,
                label="resident producer summary rebound",
            )
        )
        or summaries["transform"]["sha256"] != sha256_bytes(transform_raw)
        or summaries["consumer"]["sha256"]
        != sha256_bytes(
            _bounded_read(
                consumer_receipt_path,
                MAX_JSON_BYTES,
                label="resident consumer receipt rebound",
            )
        )
        or _artifact_record(events_path) != events_record
    ):
        _fail("resident pipeline output artifact changed after validation")

    receipt: dict[str, Any] = {
        "kind": RECEIPT_SCHEMA,
        "algorithm_id": ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "author": AUTHOR,
        "classification": (
            "bounded_arb_multiq_phase_qualification_oracle_not_source_"
            "production"
            if phase_projection is not None
            else (
                "bounded_direct_pipe_algorithm_integration_not_source_or_"
                "zero_closure"
            )
        ),
        "schedule_manifest_sha256": schedule.manifest_sha256,
        "schedule_source_roster_sha256": schedule.source_roster_sha256,
        "schedule_execution_order_sha256": (
            schedule.execution_order_sha256
        ),
        "phase_plan_sha256": plan.phase_plan_sha256,
        "lane_partition_sha256": plan.lane_partition_sha256,
        "row_chain_sha256": rows.row_chain_sha256,
        "target_chain_sha256": sidecars.target_chain_sha256,
        "lane_chain_sha256": sidecars.lane_chain_sha256,
        "control_target_chain_sha256": (
            inventory.control_target_chain_sha256
        ),
        "root_catalog_sha256": catalog_audit["catalog"]["sha256"],
        "root_catalog_entry_chain_sha256": (
            catalog_audit["entry_chain_sha256"]
        ),
        "frame_count": inventory.frame_count,
        "slice_count": inventory.slice_count,
        "value_count": plan.value_count,
        "TGDAFFI1_stream_sha256": producer_summary["output_sha256"],
        "TGDAFFI1_stream_size_bytes": producer_summary[
            "output_size_bytes"
        ],
        "TGDAFFO1_stream_sha256": transform_summary[
            "output_stream_sha256"
        ],
        "TGDAFFO1_stream_size_bytes": output_size,
        "TGDAFFO1_device_to_host_bytes": output_size,
        "process_return_codes": return_codes,
        "process_graph_backpressured": True,
        "fail_fast_sibling_cancellation": True,
        "isolated_process_groups": True,
        "raw_transform_streams_materialized": False,
        "bounded_stream_capture_or_tee_used": False,
        "component_invocations": component_invocations,
        "inputs": rebound_inputs,
        "summaries": summaries,
        "TGDQORD1_exact_coverage": phase_projection is None,
        "TGDQORD1_parent_manifest_bound": True,
        "phase_schedule_exact_coverage": phase_projection is not None,
        "phase_schedule_sha256": (
            None
            if phase_projection is None
            else phase_projection.phase_schedule_sha256
        ),
        "phase_active_modulus_count": (
            None
            if phase_projection is None
            else phase_projection.active_modulus_count
        ),
        "phase_t_index_row_count": (
            None
            if phase_projection is None
            else phase_projection.t_index_row_count
        ),
        "root_catalog_exact_roster_bound": True,
        "producer_transform_digest_crosscheck": True,
        "transform_consumer_digest_crosscheck": True,
        "bounded_independent_raw_stream_replay_completed": False,
        "arb_differential_qualification_oracle": (
            phase_projection is not None
        ),
        "phase_compact_state_bundle_validated": phase_bundle is not None,
        "same_cuda_address_space_reduction": False,
        "source_performance_ready": False,
        "source_phase_execution_completed": False,
        "source_scale_run_completed": False,
        "production_run_completed": False,
        "trusted_execution_attested": False,
        "completed_l_zero_state_validated": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }
    receipt["receipt_sha256"] = sha256_bytes(
        (
            json.dumps(
                receipt,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
            + "\n"
        ).encode("ascii")
    )
    try:
        _atomic_json(pipeline_receipt, receipt)
    except RuntimeError as error:
        raise DirichletResidentScheduledPipelineError(str(error)) from error
    return receipt


def capability() -> dict[str, Any]:
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_resident_scheduled_pipeline."
            "capability.v1"
        ),
        "algorithm_id": ALGORITHM_ID,
        "resident_qmajor_to_persistent_allchars_direct_pipe": True,
        "persistent_allchars_to_completed_l_sign_direct_pipe": True,
        "bounded_single_phase_exact_TGDQORD1_coverage": True,
        "canonical_control_target_synchronization": True,
        "root_catalog_exact_roster_binding": True,
        "producer_transform_consumer_digest_crosschecks": True,
        "process_group_fail_fast": True,
        "raw_transform_stream_materialization_required": False,
        "persistent_multiq_phase_arb_oracle_integrated": True,
        "phase_compact_state_bundle_validated": True,
        "phase_arb_oracle_is_source_production": False,
        "same_cuda_address_space_completed_l_reduction_integrated": False,
        "TGDAFFO1_host_transfer_prohibited_in_source_production": True,
        "full_source_t_phase_state_carry_integrated": False,
        "full_source_formulaic_control_stream_integrated": False,
        "bounded_independent_raw_stream_replay_completed": False,
        "source_phase_execution_completed": False,
        "source_scale_run_completed": False,
        "production_run_completed": False,
        "trusted_execution_attested": False,
        "completed_l_zero_state_validated": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
        "remaining_source_seam": (
            "launch completed-L evaluation, strict sign classification, "
            "ambiguity extraction, and compact-state reduction directly on "
            "the transformed device pointer before any host write; then "
            "carry and merge that multiplicity-preserving state across the "
            "ten t-major phase streams"
        ),
    }


__all__ = [
    "ALGORITHM_ID",
    "CONTROL_TARGET_DOMAIN",
    "DirichletResidentScheduledPipelineError",
    "RECEIPT_SCHEMA",
    "ResidentControlInventory",
    "capability",
    "run_resident_scheduled_pipeline",
    "validate_resident_control_alignment",
    "validate_resident_multiq_phase_control_alignment",
    "validate_resident_phase_control_alignment",
]
