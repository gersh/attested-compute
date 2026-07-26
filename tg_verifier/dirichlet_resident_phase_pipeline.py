# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fixed-q resident phase to compact completed-L sign-state pipeline.

One source t phase cannot satisfy the scheduled consumer's whole-q coverage
contract.  This module uses the existing fixed-q all-character service and
compact event consumer instead.  Its output is the existing associative
per-character restart state, which can be joined to the exactly adjacent
phase with ``combine_compact_state_summaries``.

The stream remains direct and bounded: neither TGDAFFI1 nor TGDAFFO1 is
materialized.  This is an algorithm-integration boundary only.  It does not
claim that the analytic input disks are useful, that ambiguities have been
refined, that every sign transition preserves zero multiplicity, that Turing
upper counts are realized, or that any source/attested run occurred.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping, NoReturn

from tg_verifier.dirichlet_allchars_stage import (
    ALGORITHM_ID as TRANSFORM_ALGORITHM_ID,
    COMPLEX_INTERVAL,
    OUTPUT_HEADER,
    canonical_component_orders,
    modulus_butterflies,
)
from tg_verifier.dirichlet_resident_qmajor_stream import (
    ParsedRowArtifact,
    ParsedSidecarArtifact,
    StreamPlan,
    iter_stream_targets,
    replay_row_artifact,
    replay_sidecar_artifact,
    validate_streamed_cuda_summary,
)
from tg_verifier.dirichlet_resident_scheduled_pipeline import (
    DirichletResidentScheduledPipelineError,
    ResidentControlInventory,
    validate_resident_phase_control_alignment,
)
from tg_verifier.dirichlet_scheduled_largeq_pipeline import (
    DEFAULT_BOUNDED_PROCESS_TIMEOUT_SECONDS,
    MAX_DIAGNOSTIC_BYTES,
    MAX_JSON_BYTES,
    _artifact_record,
    _atomic_json,
    _bounded_optional_read,
    _bounded_read,
    _canonical_object,
    _invocation_artifact_record,
    _prepare_empty_output_directory,
    _self_hash,
    _terminate,
    _validate_consumer_event_binding,
    _wait_fail_fast,
    sha256_bytes,
)
from tg_verifier.dirichlet_stream_zero_consumer import (
    COMPACT_EVENT_STORAGE_MODE,
    canonical_json_bytes,
    compact_state_from_event_summary,
    validate_compact_state_summary,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-dirichlet-resident-fixed-q-phase-state-v1"
RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_resident_phase_pipeline.receipt.v1"
)
TRANSFORM_SUMMARY_KIND = (
    "sparkinterval.tg.dirichlet_allchars.framed_service.v1"
)


class DirichletResidentPhasePipelineError(RuntimeError):
    """A fixed-q phase stream or terminal-state invariant failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletResidentPhasePipelineError(message)


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} is not lowercase SHA-256")
    return value


def _validate_transform_summary(
    value: object,
    *,
    q: int,
    plan: StreamPlan,
    inventory: ResidentControlInventory,
    maximum_batch_count: int,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("fixed-q transform summary is not an object")
    required = {
        "kind",
        "algorithm",
        "q",
        "maximum_batch_count",
        "frame_count",
        "slice_count",
        "value_count",
        "radix2_butterflies",
        "preparation_nanoseconds",
        "elapsed_nanoseconds",
        "retained_input_frames",
        "retained_output_frames",
        "input_stream_sha256",
        "output_stream_sha256",
    }
    targets = tuple(iter_stream_targets(inventory.schedule, plan))
    butterflies = sum(
        modulus_butterflies(q, batch_count=target.batch_count)
        for target in targets
    )
    expected = {
        "kind": TRANSFORM_SUMMARY_KIND,
        "algorithm": TRANSFORM_ALGORITHM_ID,
        "q": q,
        "maximum_batch_count": maximum_batch_count,
        "frame_count": inventory.frame_count,
        "slice_count": inventory.slice_count,
        "value_count": plan.value_count,
        "radix2_butterflies": butterflies,
        "retained_input_frames": 0,
        "retained_output_frames": 0,
    }
    if set(value) != required or any(
        value.get(key) != expected_value
        for key, expected_value in expected.items()
    ):
        _fail("fixed-q transform summary identity or counts differ")
    for key in ("preparation_nanoseconds", "elapsed_nanoseconds"):
        observed = value.get(key)
        if (
            isinstance(observed, bool)
            or not isinstance(observed, int)
            or observed < 0
        ):
            _fail(f"fixed-q transform summary {key} differs")
    _digest(value.get("input_stream_sha256"), "transform input stream")
    _digest(value.get("output_stream_sha256"), "transform output stream")
    return value


def run_resident_fixed_q_phase_pipeline(
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
    root_artifact: Path,
    root_receipt: Path,
    output_directory: Path,
    pipeline_receipt: Path,
    maximum_batch_count: int = 64,
    device: int = 0,
    precision: int = 192,
    process_timeout_seconds: float = (
        DEFAULT_BOUNDED_PROCESS_TIMEOUT_SECONDS
    ),
    allow_prefix_kat: bool = False,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run one bounded fixed-q t phase and publish restart state."""

    if (
        maximum_batch_count != 64
        or isinstance(maximum_batch_count, bool)
    ):
        _fail("resident phase protocol requires batch bound 64")
    if (
        isinstance(device, bool)
        or not isinstance(device, int)
        or device < 0
        or isinstance(precision, bool)
        or not isinstance(precision, int)
        or precision <= 0
        or isinstance(process_timeout_seconds, bool)
        or not isinstance(process_timeout_seconds, (int, float))
        or not math.isfinite(float(process_timeout_seconds))
        or process_timeout_seconds <= 0
    ):
        _fail("fixed-q phase numeric configuration differs")

    try:
        inventory = validate_resident_phase_control_alignment(
            consumer_controls,
            schedule_manifest_path=schedule_manifest,
            plan=plan,
        )
        rows: ParsedRowArtifact = replay_row_artifact(
            row_artifact,
            inventory.schedule,
            plan,
            expected_input_sha256=_digest(
                row_artifact_sha256, "row artifact"
            ),
        )
        sidecars: ParsedSidecarArtifact = replay_sidecar_artifact(
            sidecar_artifact,
            inventory.schedule,
            plan,
            rows,
            expected_input_sha256=_digest(
                sidecar_artifact_sha256, "sidecar artifact"
            ),
        )
    except RuntimeError as error:
        raise DirichletResidentPhasePipelineError(
            f"resident phase input replay failed: {error}"
        ) from error
    targets = tuple(iter_stream_targets(inventory.schedule, plan))
    q_values = {target.q for target in targets}
    if len(q_values) != 1:
        _fail("resident phase target stream is not fixed-q")
    q = next(iter(q_values))
    first_t_index = targets[0].first_t_index
    stop_t_index = targets[-1].t_index_stop_exclusive
    if (
        any(
            target.q != q
            or (
                index
                and target.first_t_index
                != targets[index - 1].t_index_stop_exclusive
            )
            for index, target in enumerate(targets)
        )
        or first_t_index != plan.loaded_first_t_index
        or stop_t_index
        != min(
            inventory.schedule.execution_records[
                targets[0].execution_q_index
            ].t_index_count,
            plan.loaded_t_index_stop_exclusive,
        )
    ):
        _fail("resident phase targets are not one contiguous fixed-q grid")

    seed_sha = _digest(recovery_seed_sha256, "recovery seed")
    input_records = {
        "recovery_seed": _artifact_record(recovery_seed_artifact),
        "rows": _artifact_record(row_artifact),
        "sidecars": _artifact_record(sidecar_artifact),
        "schedule": _artifact_record(schedule_manifest),
        "controls": _artifact_record(consumer_controls),
        "root_artifact": _artifact_record(root_artifact),
        "root_receipt": _artifact_record(root_receipt),
    }
    if (
        input_records["recovery_seed"]["sha256"] != seed_sha
        or rows.recovery_seed_sha256 != seed_sha
        or sidecars.recovery_seed_sha256 != seed_sha
        or input_records["rows"]["sha256"] != rows.input_sha256
        or input_records["sidecars"]["sha256"] != sidecars.input_sha256
        or input_records["schedule"]["sha256"]
        != inventory.schedule.manifest_sha256
        or input_records["controls"]["sha256"]
        != inventory.control_sha256
    ):
        _fail("resident phase immutable input binding differs")

    _prepare_empty_output_directory(output_directory)
    producer_summary_path = output_directory / "producer-summary.json"
    transform_summary_path = output_directory / "transform-summary.json"
    event_summary_path = output_directory / "events-summary.json"
    consumer_receipt_path = output_directory / "consumer-receipt.json"
    state_path = output_directory / "compact-state.json"
    consumer_stdout_path = output_directory / "consumer.stdout"
    stderr_paths = {
        name: output_directory / f"{name}.stderr"
        for name in ("producer", "transform", "consumer")
    }
    invocations = {
        "resident_runner": _invocation_artifact_record(
            resident_runner.resolve(), label="phase resident runner"
        ),
        "allchars_runner": _invocation_artifact_record(
            allchars_runner.resolve(), label="phase all-character runner"
        ),
        "consumer_python": _invocation_artifact_record(
            consumer_python, label="phase consumer Python"
        ),
        "consumer_tool": _invocation_artifact_record(
            consumer_tool.resolve(), label="phase consumer tool"
        ),
    }
    producer_command = [
        str(resident_runner.resolve()),
        str(recovery_seed_artifact.resolve()),
        seed_sha,
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
    transform_command = [
        str(allchars_runner.resolve()),
        "--framed-service",
        str(q),
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
        str(event_summary_path),
        str(consumer_receipt_path),
        "--precision",
        str(precision),
        "--root-artifact",
        str(root_artifact.resolve()),
        "--root-receipt",
        str(root_receipt.resolve()),
        "--event-storage-mode",
        COMPACT_EVENT_STORAGE_MODE,
    ]

    child_environment = dict(os.environ if environment is None else environment)
    processes: list[subprocess.Popen[bytes]] = []
    named: list[tuple[str, subprocess.Popen[bytes]]] = []
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
        named.append(("producer", producer))
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
        named.append(("transform", transform))
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
        named.append(("consumer", consumer))
        return_codes = _wait_fail_fast(
            named,
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
            label=f"resident phase {name} stderr",
        )
    _bounded_optional_read(
        consumer_stdout_path,
        MAX_JSON_BYTES,
        label="resident phase consumer stdout",
    )
    rebound_invocations = {
        "resident_runner": _invocation_artifact_record(
            resident_runner.resolve(), label="phase resident runner"
        ),
        "allchars_runner": _invocation_artifact_record(
            allchars_runner.resolve(), label="phase all-character runner"
        ),
        "consumer_python": _invocation_artifact_record(
            consumer_python, label="phase consumer Python"
        ),
        "consumer_tool": _invocation_artifact_record(
            consumer_tool.resolve(), label="phase consumer tool"
        ),
    }
    if rebound_invocations != invocations:
        _fail("resident phase invocation changed during execution")

    transform_raw = _bounded_read(
        transform_summary_path,
        MAX_JSON_BYTES,
        label="fixed-q transform summary",
    )
    try:
        transform_value = json.loads(transform_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletResidentPhasePipelineError(
            "invalid fixed-q transform summary"
        ) from error
    transform_summary = _validate_transform_summary(
        transform_value,
        q=q,
        plan=plan,
        inventory=inventory,
        maximum_batch_count=maximum_batch_count,
    )
    try:
        producer_summary = validate_streamed_cuda_summary(
            producer_summary_path,
            inventory.schedule,
            rows,
            sidecars,
            output_sha256=transform_summary["input_stream_sha256"],
            output_size_bytes=(
                plan.target_count * 72
                + plan.value_count * COMPLEX_INTERVAL.size
            ),
        )
    except RuntimeError as error:
        raise DirichletResidentPhasePipelineError(
            f"resident phase producer summary failed: {error}"
        ) from error
    consumer_receipt = _canonical_object(
        consumer_receipt_path, label="fixed-q phase consumer receipt"
    )
    _self_hash(
        consumer_receipt,
        "receipt_sha256",
        label="fixed-q phase consumer receipt",
    )
    events_record = _validate_consumer_event_binding(
        consumer_receipt, event_summary_path
    )
    if (
        producer_summary["output_sha256"]
        != transform_summary["input_stream_sha256"]
        or transform_summary["output_stream_sha256"]
        != consumer_receipt.get("transform_stream_sha256")
        or consumer_receipt.get("control_stream_sha256")
        != inventory.control_sha256
        or consumer_receipt.get("frame_count") != inventory.frame_count
        or consumer_receipt.get("value_count") != plan.value_count
        or consumer_receipt.get("event_storage_mode")
        != COMPACT_EVENT_STORAGE_MODE
        or consumer_receipt.get("raw_event_records_retained") is not False
        or consumer_receipt.get("root_number_artifact_supplied") is not True
        or consumer_receipt.get("external_atom_discharged") is not False
        or consumer_receipt.get("zero_completeness_claimed") is not False
    ):
        _fail("fixed-q phase cross-stage binding or claim boundary differs")
    event_summary = _canonical_object(
        event_summary_path, label="fixed-q compact event summary"
    )
    try:
        compact_state = compact_state_from_event_summary(event_summary)
        state_q, _signs, _ambiguities, _leaves = (
            validate_compact_state_summary(compact_state)
        )
    except RuntimeError as error:
        raise DirichletResidentPhasePipelineError(
            f"fixed-q compact state projection failed: {error}"
        ) from error
    context = compact_state["context"]
    if (
        state_q != q
        or context["frame_count"] != inventory.frame_count
        or context["first_t_numerator"] != first_t_index * 5
        or context["stop_t_numerator"] != stop_t_index * 5
        or context["t_denominator"] != 64
        or context["t_step_numerator"] != 5
    ):
        _fail("fixed-q compact phase state span differs")
    _atomic_json(state_path, compact_state)

    rebound_inputs = {
        name: _artifact_record(Path(record["path"]))
        for name, record in input_records.items()
    }
    if rebound_inputs != input_records:
        _fail("resident phase input changed during execution")
    summaries = {
        "producer": _artifact_record(producer_summary_path),
        "transform": _artifact_record(transform_summary_path),
        "consumer": _artifact_record(consumer_receipt_path),
        "events": events_record,
        "compact_state": _artifact_record(state_path),
    }
    if (
        summaries["transform"]["sha256"] != sha256_bytes(transform_raw)
        or summaries["compact_state"]["sha256"]
        != sha256_bytes(canonical_json_bytes(compact_state))
        or _artifact_record(event_summary_path) != events_record
    ):
        _fail("resident phase output changed after validation")

    output_size = (
        plan.target_count * OUTPUT_HEADER.size
        + plan.value_count * COMPLEX_INTERVAL.size
    )
    receipt: dict[str, Any] = {
        "kind": RECEIPT_SCHEMA,
        "algorithm_id": ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "author": AUTHOR,
        "classification": (
            "bounded_fixed_q_phase_restart_state_not_source_or_turing_"
            "closure"
        ),
        "q": q,
        "first_t_index": first_t_index,
        "t_index_stop_exclusive": stop_t_index,
        "phase_plan_sha256": plan.phase_plan_sha256,
        "target_chain_sha256": sidecars.target_chain_sha256,
        "control_target_chain_sha256": (
            inventory.control_target_chain_sha256
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
        "compact_state_sha256": compact_state["state_sha256"],
        "process_return_codes": return_codes,
        "process_graph_backpressured": True,
        "raw_transform_streams_materialized": False,
        "component_invocations": invocations,
        "inputs": input_records,
        "summaries": summaries,
        "strict_endpoint_signs_retained": True,
        "exact_maximal_ambiguity_ranges_retained": True,
        "ordered_bracket_records_retained": True,
        "multiplicity_lower_bound_only": True,
        "touching_vs_wide_unresolved_distinguished": False,
        "turing_counts_realized": False,
        "refinement_artifacts_complete": False,
        "source_phase_execution_completed": False,
        "source_scale_run_completed": False,
        "production_run_completed": False,
        "trusted_execution_attested": False,
        "completed_l_zero_state_validated": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }
    receipt["receipt_sha256"] = sha256_bytes(canonical_json_bytes(receipt))
    try:
        _atomic_json(pipeline_receipt, receipt)
    except RuntimeError as error:
        raise DirichletResidentPhasePipelineError(str(error)) from error
    return receipt


def capability() -> dict[str, Any]:
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_resident_phase_pipeline."
            "capability.v1"
        ),
        "algorithm_id": ALGORITHM_ID,
        "direct_resident_qmajor_to_fixed_q_fft_to_compact_state": True,
        "adjacent_state_merge_algorithm_reused": True,
        "raw_transform_stream_materialization_required": False,
        "strict_endpoint_signs_retained": True,
        "exact_maximal_ambiguity_ranges_retained": True,
        "ordered_bracket_records_retained_in_v2_kat_state": True,
        "production_v3_transition_counts_available": True,
        "touching_vs_wide_unresolved_distinguished": False,
        "turing_counts_realized": False,
        "multiplicity_preserving_zero_lower_bound_realized": False,
        "source_phase_execution_completed": False,
        "source_scale_run_completed": False,
        "production_run_completed": False,
        "trusted_execution_attested": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "DirichletResidentPhasePipelineError",
    "RECEIPT_SCHEMA",
    "capability",
    "run_resident_fixed_q_phase_pipeline",
]
