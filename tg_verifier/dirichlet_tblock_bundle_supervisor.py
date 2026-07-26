# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded protocol-v2 typed-bundle replay for the t-block supervisor.

The v1 t-block seam proves row transport and exact target accounting but never
receives the typed FFT bundles.  This bounded v2 seam receives the *actual*
canonical bundle bytes in length-framed records, stages them immutably, hashes
them itself, freshly invokes both ``replay_bundle`` (through the adapter) and
``TMajorTypedBundleLaneAdapter.accept_bundle``, and writes a checkpoint only
after every artifact in the request has passed admission.

This is intentionally not a production source campaign.  The adapter now has
an explicit block-major mode and a separately pinned bounded worker executes
actual composer/native-transform/FLINT-consumer arithmetic while switching q.
Production contracts remain rejected unconditionally because certified
inputs, compact source-scale storage, CUDA/attestation, and zero/Turing
closure are still absent.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import tempfile
from typing import Any, Mapping, Sequence

from tg_verifier.dirichlet_compact_state_binary import (
    DEFAULT_MAXIMUM_ARTIFACT_BYTES as MAXIMUM_COMPACT_STATE_BINARY_BYTES,
    DirichletCompactStateBinaryError,
    read_compact_state_binary,
    write_compact_state_binary,
)
from tg_verifier.dirichlet_fft_pipeline_bundle import MAXIMUM_JSON_BYTES
from tg_verifier.dirichlet_lattice_cache import canonical_json_bytes
from tg_verifier.dirichlet_lattice_stage import maximum_t_index
from tg_verifier.dirichlet_source_supervisor import (
    FFT_BATCH_SIZE,
    SOURCE_CONTRACT_CLASSIFICATION,
)
from tg_verifier.dirichlet_tblock_supervisor import (
    ATOM_ID,
    AUTHOR,
    CHECKPOINT_NAME_WIDTH,
    DirichletTBlockSupervisorError,
    INITIAL_CHECKPOINT_CHAIN_DOMAIN,
    _RosterIndex,
    _Worker,
    _atomic_json,
    _chain,
    _digest,
    _existing_checkpoint_paths,
    _fail,
    _integer,
    _read_regular_canonical,
    _request,
    _self_hash,
    extend_result_chain,
    initial_result_chain,
)
from tg_verifier.dirichlet_tmajor_adapter import (
    BLOCK_MAJOR_TARGET_ORDER,
    TMajorTypedBundleLaneAdapter,
)
from tg_verifier.dirichlet_tmajor_spool import (
    AuthenticatedQContiguousSpool,
)
from tg_verifier.dirichlet_stream_zero_consumer import (
    COMPACT_EVENT_STORAGE_MODE,
    DirichletStreamConsumerError,
    combine_compact_state_summaries,
    compact_state_from_event_summary,
)


ALGORITHM_ID = "platt-dirichlet-t-block-bundle-supervisor-v2"
WORKER_ALGORITHM_ID = "platt-dirichlet-t-block-bundle-worker-v2"
HANDSHAKE_SCHEMA = (
    "sparkinterval.tg.dirichlet_tblock_bundle_worker.handshake.v2"
)
REQUEST_SCHEMA = "sparkinterval.tg.dirichlet_tblock_bundle_worker.request.v2"
STREAM_SCHEMA = (
    "sparkinterval.tg.dirichlet_tblock_bundle_worker.stream.v2"
)
FRAME_SCHEMA = (
    "sparkinterval.tg.dirichlet_tblock_bundle_worker.frame.v2"
)
RESPONSE_SCHEMA = (
    "sparkinterval.tg.dirichlet_tblock_bundle_worker.response.v2"
)
CHECKPOINT_SCHEMA = (
    "sparkinterval.tg.dirichlet_tblock_bundle_supervisor.checkpoint.v2"
)
RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_tblock_bundle_supervisor.receipt.v2"
)

WORKER_CLASSIFICATION = (
    "bounded_typed_bundle_transport_kat_not_source_evidence"
)
NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION = (
    "bounded_actual_native_multi_q_plan_switch_kat_not_source_evidence"
)
RECEIPT_CLASSIFICATION = (
    "bounded_typed_bundle_replay_and_adapter_kat_not_source_evidence"
)

ARTIFACT_CHAIN_INITIAL_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tblock-bundle/artifact-initial/v2\0"
)
ARTIFACT_CHAIN_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tblock-bundle/artifact-chain/v2\0"
)
CHECKPOINT_CHAIN_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tblock-bundle/checkpoint-chain/v2\0"
)
FRAME_LENGTH = struct.Struct("<Q")
MAXIMUM_BUNDLE_BYTES = MAXIMUM_JSON_BYTES
MAXIMUM_BOUNDED_BUNDLES_PER_BLOCK = 64
MAXIMUM_BOUNDED_NESTED_EVENT_BYTES = 1024 * 1024 * 1024
MAXIMUM_BOUNDED_COMPACT_EVENT_SUMMARY_BYTES = 64 * 1024 * 1024
COMPACT_STATE_TRANSITION_SCHEMA = (
    "sparkinterval.tg.dirichlet_tblock_bundle_supervisor."
    "compact_state_transition.v2"
)
COMPACT_STATE_TRANSITION_CHAIN_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tblock-bundle/compact-state-transition/v2\0"
)


def _v2_request(
    spool: AuthenticatedQContiguousSpool,
    *,
    sequence_index: int,
    first_t_index: int,
    t_index_stop_exclusive: int,
    result_chain_before: str,
    roster_index: _RosterIndex,
) -> dict[str, Any]:
    """Reuse the exact v1 roster/row binding under an explicit v2 identity."""

    request = _request(
        spool,
        sequence_index=sequence_index,
        first_t_index=first_t_index,
        t_index_stop_exclusive=t_index_stop_exclusive,
        result_chain_before=result_chain_before,
        roster_index=roster_index,
    )
    request["schema"] = REQUEST_SCHEMA
    request["schema_version"] = 2
    request["algorithm_id"] = ALGORITHM_ID
    request["bundle_output_order"] = BLOCK_MAJOR_TARGET_ORDER
    body = dict(request)
    body.pop("request_sha256")
    request["request_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return request


def validate_bundle_worker_handshake(
    value: Mapping[str, Any],
    *,
    production_contract: bool,
    allow_structural_kat: bool,
    allow_native_plan_switch_kat: bool = False,
    expected_handshake_sha256: str | None = None,
    expected_implementation_sha256: str | None = None,
    expected_recipe_sha256: str | None = None,
    expected_runtime_artifacts_sha256: str | None = None,
) -> dict[str, Any]:
    """Admit only the bounded transport worker; production always stays shut."""

    handshake = dict(value)
    claimed = _self_hash(
        handshake, "handshake_sha256", label="v2 worker handshake"
    )
    common_required = {
        "schema",
        "schema_version",
        "author",
        "atom_id",
        "algorithm_id",
        "classification",
        "worker_id",
        "worker_implementation_sha256",
        "capabilities",
        "claims",
        "handshake_sha256",
    }
    classification = handshake.get("classification")
    required = (
        common_required | {"execution_profile"}
        if classification == NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION
        else common_required
    )
    if (
        set(handshake) != required
        or handshake.get("schema") != HANDSHAKE_SCHEMA
        or handshake.get("schema_version") != 2
        or handshake.get("author") != AUTHOR
        or handshake.get("atom_id") != ATOM_ID
        or handshake.get("algorithm_id") != WORKER_ALGORITHM_ID
        or classification
        not in {
            WORKER_CLASSIFICATION,
            NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION,
        }
        or not isinstance(handshake.get("worker_id"), str)
        or not handshake["worker_id"]
    ):
        _fail("v2 worker handshake identity or fields differ")
    implementation = _digest(
        handshake.get("worker_implementation_sha256"),
        "v2 worker implementation",
    )
    if (
        expected_handshake_sha256 is not None
        and claimed
        != _digest(
            expected_handshake_sha256, "expected v2 worker handshake"
        )
    ):
        _fail("v2 worker handshake differs from its external pin")
    if (
        expected_implementation_sha256 is not None
        and implementation
        != _digest(
            expected_implementation_sha256,
            "expected v2 worker implementation",
        )
    ):
        _fail("v2 worker implementation differs from its external pin")

    capabilities = handshake.get("capabilities")
    transport_capabilities = {
        "accepts_one_authenticated_t_block_payload": True,
        "derives_exact_active_q_roster_formulaically": True,
        "multi_q_target_iteration": True,
        "multi_q_plan_switching": False,
        "resumable_idempotent_outputs": True,
        "actual_residue_composer": False,
        "actual_all_character_transform": False,
        "actual_completed_l_consumer": False,
        "typed_bundle_emission": True,
        "adapter_compatible_output": True,
        "framed_typed_bundle_bytes_to_supervisor": True,
    }
    native_capabilities = {
        **transport_capabilities,
        "multi_q_plan_switching": True,
        "actual_residue_composer": True,
        "actual_all_character_transform": True,
        "actual_completed_l_consumer": True,
    }
    expected_claims = {
        "cuda_execution_attested": False,
        "completed_l_zero_completeness": False,
        "turing_completeness": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }
    if (
        capabilities
        != (
            native_capabilities
            if classification == NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION
            else transport_capabilities
        )
        or handshake.get("claims") != expected_claims
    ):
        _fail("v2 worker capability or claim boundary differs")
    if production_contract:
        _fail(
            "production admission is disabled: bounded v2 stages and replays "
            "typed bundles but is not a real multi-q worker, row-resident "
            "CUDA service, zero-completeness proof, or attested source run"
        )
    if classification == NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION:
        if not allow_native_plan_switch_kat:
            _fail(
                "actual native plan-switch worker requires explicit "
                "bounded-KAT authorization"
            )
        profile = handshake.get("execution_profile")
        if (
            not isinstance(profile, dict)
            or set(profile)
            != {
                "target_order",
                "recipe_sha256",
                "runtime_artifacts_sha256",
                "arithmetic_backend",
                "storage_policy",
                "source_scale_run",
            }
            or profile.get("target_order") != BLOCK_MAJOR_TARGET_ORDER
            or profile.get("arithmetic_backend")
            != "pinned_python_flint_composer_native_allchars_flint_consumer"
            or profile.get("source_scale_run") is not False
        ):
            _fail("native plan-switch execution profile differs")
        storage_policy = profile.get("storage_policy")
        if (
            not isinstance(storage_policy, dict)
            or set(storage_policy)
            != {
                "maximum_event_bytes_per_target",
                "maximum_retained_output_bytes",
                "event_storage_mode",
                "raw_event_streams_retained_for_typed_bundle_resume",
                "compact_event_summary_replayed_on_resume",
                "source_scale_storage_admitted",
            }
            or storage_policy.get("event_storage_mode")
            != "compact_associative_mmr_summary"
            or storage_policy.get(
                "raw_event_streams_retained_for_typed_bundle_resume"
            )
            is not False
            or storage_policy.get(
                "compact_event_summary_replayed_on_resume"
            )
            is not True
            or storage_policy.get("source_scale_storage_admitted") is not False
        ):
            _fail("native plan-switch storage policy differs")
        event_budget = _integer(
            storage_policy.get("maximum_event_bytes_per_target"),
            "native per-target event byte budget",
            minimum=1,
        )
        retained_budget = _integer(
            storage_policy.get("maximum_retained_output_bytes"),
            "native retained output byte budget",
            minimum=1,
        )
        if event_budget > retained_budget:
            _fail("native plan-switch event budget exceeds retained budget")
        if (
            expected_handshake_sha256 is None
            or expected_implementation_sha256 is None
            or expected_recipe_sha256 is None
            or expected_runtime_artifacts_sha256 is None
        ):
            _fail(
                "native plan-switch KAT requires external worker handshake, "
                "implementation, recipe, and runtime artifact digest pins"
            )
        if profile.get("recipe_sha256") != _digest(
            expected_recipe_sha256, "expected native plan-switch recipe"
        ):
            _fail("native plan-switch recipe differs from its external pin")
        if profile.get("runtime_artifacts_sha256") != _digest(
            expected_runtime_artifacts_sha256,
            "expected native plan-switch runtime artifacts",
        ):
            _fail(
                "native plan-switch runtime artifact set differs from its "
                "external pin"
            )
    if not allow_structural_kat:
        _fail("bounded v2 worker requires explicit structural-KAT authorization")
    return handshake


def _validate_stream_header(
    value: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
) -> int:
    header = dict(value)
    _self_hash(header, "stream_sha256", label="v2 bundle-stream header")
    required = {
        "schema",
        "schema_version",
        "author",
        "atom_id",
        "algorithm_id",
        "sequence_index",
        "request_sha256",
        "frame_count",
        "stream_sha256",
    }
    count = _integer(
        header.get("frame_count"),
        "v2 frame count",
        minimum=0,
        maximum=MAXIMUM_BOUNDED_BUNDLES_PER_BLOCK,
    )
    if (
        set(header) != required
        or header.get("schema") != STREAM_SCHEMA
        or header.get("schema_version") != 2
        or header.get("author") != AUTHOR
        or header.get("atom_id") != ATOM_ID
        or header.get("algorithm_id") != WORKER_ALGORITHM_ID
        or header.get("sequence_index") != request["sequence_index"]
        or header.get("request_sha256") != request["request_sha256"]
        or count != request["target_roster"]["active_q_count"]
    ):
        _fail("v2 bundle-stream identity or exact target count differs")
    return count


def _validate_frame_header(
    value: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    ordinal: int,
) -> tuple[int, str]:
    header = dict(value)
    _self_hash(header, "frame_header_sha256", label="v2 frame header")
    required = {
        "schema",
        "schema_version",
        "author",
        "atom_id",
        "algorithm_id",
        "sequence_index",
        "request_sha256",
        "ordinal",
        "size_bytes",
        "transport_sha256",
        "frame_header_sha256",
    }
    size = _integer(
        header.get("size_bytes"),
        "v2 typed-bundle frame size",
        minimum=1,
        maximum=MAXIMUM_BUNDLE_BYTES,
    )
    transport = _digest(
        header.get("transport_sha256"), "v2 typed-bundle transport"
    )
    if (
        set(header) != required
        or header.get("schema") != FRAME_SCHEMA
        or header.get("schema_version") != 2
        or header.get("author") != AUTHOR
        or header.get("atom_id") != ATOM_ID
        or header.get("algorithm_id") != WORKER_ALGORITHM_ID
        or header.get("sequence_index") != request["sequence_index"]
        or header.get("request_sha256") != request["request_sha256"]
        or header.get("ordinal") != ordinal
    ):
        _fail("v2 typed-bundle frame is substituted, skipped, or reordered")
    return size, transport


def _validate_response(
    value: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    payload_stream_sha256: str,
    frame_count: int,
    handshake: Mapping[str, Any],
) -> dict[str, Any]:
    response = dict(value)
    _self_hash(response, "response_sha256", label="v2 worker response")
    required = {
        "schema",
        "schema_version",
        "author",
        "atom_id",
        "algorithm_id",
        "status",
        "sequence_index",
        "request_sha256",
        "payload_stream_sha256",
        "active_q_count",
        "target_row_reference_count",
        "target_roster_formula_sha256",
        "framed_typed_bundle_count",
        "worker_services_executed",
        "claims",
        "response_sha256",
    }
    roster = request["target_roster"]
    transport_services = {
        "residue_composer": False,
        "all_character_transform": False,
        "completed_l_consumer": False,
        "typed_bundle_replay": False,
        "tmajor_adapter_admission": False,
    }
    services = response.get("worker_services_executed")
    if (
        handshake.get("classification")
        == NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION
    ):
        required.add("native_execution")
        if (
            not isinstance(services, dict)
            or set(services) != set(transport_services)
            or services.get("typed_bundle_replay") is not True
            or services.get("tmajor_adapter_admission") is not False
            or type(services.get("residue_composer")) is not bool
            or services.get("residue_composer")
            is not services.get("all_character_transform")
            or services.get("residue_composer")
            is not services.get("completed_l_consumer")
        ):
            _fail("native plan-switch worker service record differs")
        first = request["row_block"]["first_t_index"]
        q_sequence = [
            q
            for q in range(
                roster["q_start_inclusive"],
                roster["q_stop_inclusive"] + 1,
            )
            if first <= maximum_t_index(q)
        ]
        execution = response.get("native_execution")
        profile = handshake["execution_profile"]
        if (
            not isinstance(execution, dict)
            or set(execution)
            != {
                "target_order",
                "q_sequence",
                "plan_load_count",
                "plan_switch_count",
                "generated_target_count",
                "cached_target_count",
                "recipe_sha256",
                "runtime_artifacts_sha256",
                "actual_native_arithmetic_executed",
                "source_scale_run",
                "target_timings",
                "storage_accounting",
            }
            or execution.get("target_order") != BLOCK_MAJOR_TARGET_ORDER
            or execution.get("q_sequence") != q_sequence
            or execution.get("plan_load_count") != len(q_sequence)
            or execution.get("plan_switch_count")
            != max(0, len(q_sequence) - 1)
            or _integer(
                execution.get("generated_target_count"),
                "native generated target count",
                minimum=0,
                maximum=len(q_sequence),
            )
            + _integer(
                execution.get("cached_target_count"),
                "native cached target count",
                minimum=0,
                maximum=len(q_sequence),
            )
            != len(q_sequence)
            or execution.get("recipe_sha256") != profile["recipe_sha256"]
            or execution.get("runtime_artifacts_sha256")
            != profile["runtime_artifacts_sha256"]
            or execution.get("actual_native_arithmetic_executed")
            is not (execution.get("generated_target_count") > 0)
            or execution.get("source_scale_run") is not False
            or services.get("residue_composer")
            is not execution.get("actual_native_arithmetic_executed")
        ):
            _fail("native plan-switch execution record differs")
        timings = execution.get("target_timings")
        if (
            not isinstance(timings, list)
            or len(timings) != len(q_sequence)
        ):
            _fail("native plan-switch timing roster differs")
        timing_fields = {
            "q",
            "generated_this_invocation",
            "pipeline_wall_seconds",
            "composer_wall_seconds",
            "allchars_preparation_seconds",
            "allchars_execution_seconds",
            "flint_consumer_wall_seconds",
            "classification",
        }
        for q, timing in zip(q_sequence, timings):
            if (
                not isinstance(timing, dict)
                or set(timing) != timing_fields
                or timing.get("q") != q
                or type(timing.get("generated_this_invocation")) is not bool
                or timing.get("classification")
                != "diagnostic_timing_not_proof_evidence"
            ):
                _fail("native plan-switch target timing identity differs")
            for field in (
                "pipeline_wall_seconds",
                "composer_wall_seconds",
                "allchars_preparation_seconds",
                "allchars_execution_seconds",
                "flint_consumer_wall_seconds",
            ):
                number = timing.get(field)
                if (
                    isinstance(number, bool)
                    or not isinstance(number, (int, float))
                    or not math.isfinite(number)
                    or number < 0
                ):
                    _fail("native plan-switch diagnostic timing differs")
        if sum(
            int(timing["generated_this_invocation"])
            for timing in timings
        ) != execution["generated_target_count"]:
            _fail("native plan-switch timing/generated count differs")
        storage = execution.get("storage_accounting")
        if (
            not isinstance(storage, dict)
            or set(storage)
            != {
                "classification",
                "policy",
                "retained_output_bytes",
                "targets",
                "content_addressed_shared_row_inputs",
                "streamed_compact_event_resume",
                "source_scale_storage_admitted",
            }
            or storage.get("classification")
            != "exact_worker_filesystem_bytes_not_proof_evidence"
            or storage.get("policy") != profile["storage_policy"]
            or storage.get("content_addressed_shared_row_inputs") is not False
            or storage.get("streamed_compact_event_resume") is not True
            or storage.get("source_scale_storage_admitted") is not False
        ):
            _fail("native plan-switch storage accounting boundary differs")
        retained_output_bytes = _integer(
            storage.get("retained_output_bytes"),
            "native retained output bytes",
            minimum=0,
        )
        if (
            retained_output_bytes
            > profile["storage_policy"]["maximum_retained_output_bytes"]
        ):
            _fail("native retained output exceeds its pinned byte budget")
        storage_targets = storage.get("targets")
        if (
            not isinstance(storage_targets, list)
            or len(storage_targets) != len(q_sequence)
        ):
            _fail("native storage target roster differs")
        storage_target_fields = {
            "q",
            "event_artifact_bytes",
            "event_storage_mode",
            "pipeline_bytes",
            "typed_bundle_bytes",
            "target_output_bytes",
            "raw_event_stream_retained",
            "compact_event_summary_retained",
            "classification",
        }
        current_target_bytes = 0
        for q, target_storage in zip(q_sequence, storage_targets):
            if (
                not isinstance(target_storage, dict)
                or set(target_storage) != storage_target_fields
                or target_storage.get("q") != q
                or target_storage.get("event_storage_mode")
                != "compact_associative_mmr_summary"
                or target_storage.get("raw_event_stream_retained") is not False
                or target_storage.get("compact_event_summary_retained")
                is not True
                or target_storage.get("classification")
                != "exact_worker_filesystem_bytes_not_proof_evidence"
            ):
                _fail("native target storage identity differs")
            event_artifact_bytes = _integer(
                target_storage.get("event_artifact_bytes"),
                "native compact event artifact bytes",
                minimum=1,
            )
            pipeline_bytes = _integer(
                target_storage.get("pipeline_bytes"),
                "native pipeline bytes",
                minimum=event_artifact_bytes,
            )
            typed_bundle_bytes = _integer(
                target_storage.get("typed_bundle_bytes"),
                "native typed bundle bytes",
                minimum=1,
            )
            target_output_bytes = _integer(
                target_storage.get("target_output_bytes"),
                "native target output bytes",
                minimum=pipeline_bytes + typed_bundle_bytes,
            )
            if (
                event_artifact_bytes
                > profile["storage_policy"][
                    "maximum_event_bytes_per_target"
                ]
            ):
                _fail("native target event stream exceeds its pinned budget")
            current_target_bytes += target_output_bytes
        if current_target_bytes > retained_output_bytes:
            _fail("native target storage exceeds retained output accounting")
    elif services != transport_services:
        _fail("transport worker claimed unimplemented arithmetic services")
    expected_claims = {
        "cuda_execution_attested": False,
        "completed_l_zero_completeness": False,
        "turing_completeness": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }
    exact = {
        "sequence_index": request["sequence_index"],
        "request_sha256": request["request_sha256"],
        "payload_stream_sha256": payload_stream_sha256,
        "active_q_count": roster["active_q_count"],
        "target_row_reference_count": roster[
            "target_row_reference_count"
        ],
        "target_roster_formula_sha256": roster[
            "target_roster_formula_sha256"
        ],
        "framed_typed_bundle_count": frame_count,
        "worker_services_executed": services,
        "claims": expected_claims,
    }
    if (
        frame_count != roster["active_q_count"]
        or set(response) != required
        or response.get("schema") != RESPONSE_SCHEMA
        or response.get("schema_version") != 2
        or response.get("author") != AUTHOR
        or response.get("atom_id") != ATOM_ID
        or response.get("algorithm_id") != WORKER_ALGORITHM_ID
        or response.get("status") != "completed"
        or any(response.get(key) != expected for key, expected in exact.items())
    ):
        _fail(
            "v2 worker response differs or claims supervisor-only "
            "replay/admission work"
        )
    return response


def _artifact_initial(request_sha256: str) -> str:
    digest = hashlib.sha256(ARTIFACT_CHAIN_INITIAL_DOMAIN)
    digest.update(bytes.fromhex(_digest(request_sha256, "v2 request")))
    return digest.hexdigest()


def _artifact_extend(before: str, identity: Mapping[str, Any]) -> str:
    return _chain(ARTIFACT_CHAIN_DOMAIN, before, identity)


def _artifact_path(
    checkpoint_directory: Path,
    sequence_index: int,
    ordinal: int,
) -> Path:
    artifact_root = checkpoint_directory / "typed-bundles"
    if artifact_root.exists():
        if not artifact_root.is_dir() or artifact_root.is_symlink():
            _fail("v2 typed-bundle staging root is not a non-symlink directory")
    else:
        artifact_root.mkdir(parents=False)
    return (
        artifact_root
        / (
            f"block-{sequence_index:0{CHECKPOINT_NAME_WIDTH}d}"
            f"-bundle-{ordinal:08d}.json"
        )
    )


def _read_regular_bytes(
    path: Path,
    *,
    expected_size: int,
    expected_sha256: str,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletTBlockSupervisorError(
            f"cannot open staged typed bundle without following links: {path}"
        ) from error
    with os.fdopen(descriptor, "rb") as source:
        status = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(status.st_mode)
            or status.st_size != expected_size
        ):
            _fail("staged typed-bundle size or file type differs")
        raw = source.read()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        _fail("staged typed-bundle bytes differ from their checkpoint")
    return raw


def _nested_event_storage(
    parsed_bundle: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Recover event bytes from the receipt freshly replayed by the adapter."""

    record = parsed_bundle.get("pipeline_receipt_file")
    if (
        not isinstance(record, dict)
        or set(record) != {"path", "sha256", "size_bytes"}
    ):
        _fail("typed bundle pipeline-receipt artifact record differs")
    raw_path = record.get("path")
    if (
        not isinstance(raw_path, str)
        or not Path(raw_path).is_absolute()
        or str(Path(raw_path).resolve()) != raw_path
    ):
        _fail("typed bundle pipeline-receipt path differs")
    receipt_size = _integer(
        record.get("size_bytes"),
        "typed bundle pipeline-receipt size",
        minimum=1,
        maximum=MAXIMUM_JSON_BYTES,
    )
    receipt_raw = _read_regular_bytes(
        Path(raw_path),
        expected_size=receipt_size,
        expected_sha256=_digest(
            record.get("sha256"), "typed bundle pipeline receipt"
        ),
    )
    try:
        receipt = json.loads(receipt_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletTBlockSupervisorError(
            "typed bundle pipeline receipt is invalid JSON"
        ) from error
    if (
        not isinstance(receipt, dict)
        or canonical_json_bytes(receipt) != receipt_raw
    ):
        _fail("typed bundle pipeline receipt is not canonical JSON")
    summaries = receipt.get("summaries")
    events = summaries.get("events") if isinstance(summaries, dict) else None
    consumer = (
        summaries.get("consumer") if isinstance(summaries, dict) else None
    )
    if (
        not isinstance(events, dict)
        or set(events) != {"path", "sha256", "size_bytes"}
        or not isinstance(consumer, dict)
        or set(consumer) != {"path", "sha256", "size_bytes"}
    ):
        _fail("typed bundle consumer/event artifact record differs")
    event_bytes = _integer(
        events.get("size_bytes"),
        "typed bundle event artifact bytes",
        minimum=1,
    )
    event_path = events.get("path")
    if (
        not isinstance(event_path, str)
        or not Path(event_path).is_absolute()
        or str(Path(event_path).resolve()) != event_path
    ):
        _fail("typed bundle event artifact path differs")
    consumer_size = _integer(
        consumer.get("size_bytes"),
        "typed bundle consumer receipt size",
        minimum=1,
        maximum=MAXIMUM_JSON_BYTES,
    )
    consumer_raw = _read_regular_bytes(
        Path(consumer["path"]),
        expected_size=consumer_size,
        expected_sha256=_digest(
            consumer.get("sha256"), "typed bundle consumer receipt"
        ),
    )
    consumer_receipt = json.loads(consumer_raw)
    if (
        not isinstance(consumer_receipt, dict)
        or canonical_json_bytes(consumer_receipt) != consumer_raw
    ):
        _fail("typed bundle consumer receipt is not canonical JSON")
    event_storage_mode = consumer_receipt.get("event_storage_mode")
    compact = event_storage_mode == COMPACT_EVENT_STORAGE_MODE
    if event_storage_mode not in {
        "raw_ndjson",
        COMPACT_EVENT_STORAGE_MODE,
    }:
        _fail("typed bundle event storage mode differs")
    compact_state: dict[str, Any] | None = None
    if compact:
        if event_bytes > MAXIMUM_BOUNDED_COMPACT_EVENT_SUMMARY_BYTES:
            _fail(
                "bounded compact event summary exceeds its fixed JSON "
                "reconstruction limit"
            )
        event_raw = _read_regular_bytes(
            Path(event_path),
            expected_size=event_bytes,
            expected_sha256=_digest(
                events.get("sha256"),
                "typed bundle compact event summary",
            ),
        )
        try:
            event_summary = json.loads(event_raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DirichletTBlockSupervisorError(
                "typed bundle compact event summary is invalid JSON"
            ) from error
        if (
            not isinstance(event_summary, dict)
            or canonical_json_bytes(event_summary) != event_raw
        ):
            _fail("typed bundle compact event summary is not canonical JSON")
        try:
            compact_state = compact_state_from_event_summary(event_summary)
        except DirichletStreamConsumerError as error:
            raise DirichletTBlockSupervisorError(
                f"typed bundle compact event state replay failed: {error}"
            ) from error
        target = parsed_bundle.get("target")
        if not isinstance(target, dict):
            _fail("typed bundle target is absent from compact event state")
        q = _integer(target.get("q"), "compact event target q", minimum=3)
        first_t_index = _integer(
            target.get("first_t_index"),
            "compact event target first t index",
            minimum=0,
        )
        stop_t_index = _integer(
            target.get("t_index_stop_exclusive"),
            "compact event target t stop",
            minimum=first_t_index + 1,
        )
        context = compact_state["context"]
        if (
            context["q"] != q
            or context["first_t_numerator"] != 5 * first_t_index
            or context["stop_t_numerator"] != 5 * stop_t_index
        ):
            _fail(
                "compact event state q/grid differs from the exact typed "
                "bundle target"
            )
    nested = {
        "pipeline_receipt_size_bytes": receipt_size,
        "event_artifact_size_bytes": event_bytes,
        "event_artifact_sha256": _digest(
            events.get("sha256"), "typed bundle event artifact"
        ),
        "event_storage_mode": event_storage_mode,
        "raw_event_stream_retained_for_resume": not compact,
        "compact_event_resume_implemented": compact,
        "compact_state_leaf_reconstructed": compact,
        "compact_state_leaf_sha256": (
            compact_state["state_sha256"] if compact_state is not None else None
        ),
        "compact_state_q": (
            compact_state["context"]["q"] if compact_state is not None else None
        ),
        "compact_state_first_t_numerator": (
            compact_state["context"]["first_t_numerator"]
            if compact_state is not None
            else None
        ),
        "compact_state_stop_t_numerator": (
            compact_state["context"]["stop_t_numerator"]
            if compact_state is not None
            else None
        ),
    }
    return nested, compact_state


def _admit_raw_bundle(
    raw: bytes,
    *,
    checkpoint_directory: Path,
    sequence_index: int,
    ordinal: int,
    adapter: TMajorTypedBundleLaneAdapter,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Replay/admit a temporary file, then make its exact bytes immutable."""

    if not raw or len(raw) > MAXIMUM_BUNDLE_BYTES:
        _fail("v2 typed-bundle frame size is outside its fixed bound")
    file_sha256 = hashlib.sha256(raw).hexdigest()
    destination = _artifact_path(
        checkpoint_directory, sequence_index, ordinal
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        # The adapter calls replay_bundle freshly; no worker-supplied semantic
        # digest is trusted.
        try:
            parsed = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DirichletTBlockSupervisorError(
                "v2 typed-bundle frame is not JSON"
            ) from error
        if (
            not isinstance(parsed, dict)
            or canonical_json_bytes(parsed) != raw
        ):
            _fail("v2 typed-bundle frame is not one canonical JSON artifact")
        bundle_sha256 = _digest(
            parsed.get("bundle_sha256"), "v2 typed-bundle semantic digest"
        )
        try:
            admission = adapter.accept_bundle(
                temporary,
                expected_bundle_sha256=bundle_sha256,
            )
        except RuntimeError as error:
            raise DirichletTBlockSupervisorError(
                "v2 typed bundle failed fresh replay or deterministic "
                "adapter admission"
            ) from error
        nested_storage, compact_state = _nested_event_storage(parsed)
        try:
            os.link(temporary, destination)
            temporary.unlink()
        except FileExistsError:
            existing = _read_regular_bytes(
                destination,
                expected_size=len(raw),
                expected_sha256=file_sha256,
            )
            if existing != raw:
                _fail("orphaned staged typed bundle has substituted bytes")
            temporary.unlink()
        directory_descriptor = os.open(
            destination.parent,
            getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY,
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    identity = {
        "sequence_index": sequence_index,
        "ordinal": ordinal,
        "size_bytes": len(raw),
        "transport_sha256": file_sha256,
        "bundle_sha256": bundle_sha256,
        "admission_sha256": admission["admission_sha256"],
        "nested_storage_sha256": hashlib.sha256(
            canonical_json_bytes(nested_storage)
        ).hexdigest(),
    }
    artifact = {
        **identity,
        "path": str(destination.resolve()),
        "admission": admission,
        "nested_storage": nested_storage,
    }
    return artifact, compact_state


def _replay_staged_artifact(
    record: Mapping[str, Any],
    *,
    checkpoint_directory: Path,
    sequence_index: int,
    ordinal: int,
    adapter: TMajorTypedBundleLaneAdapter,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not isinstance(record, dict):
        _fail("checkpoint staged typed-bundle record is malformed")
    expected_path = _artifact_path(
        checkpoint_directory, sequence_index, ordinal
    ).resolve()
    if record.get("path") != str(expected_path):
        _fail("checkpoint staged typed-bundle path is substituted")
    size = _integer(
        record.get("size_bytes"),
        "checkpoint staged typed-bundle size",
        minimum=1,
        maximum=MAXIMUM_BUNDLE_BYTES,
    )
    transport = _digest(
        record.get("transport_sha256"),
        "checkpoint staged typed-bundle transport",
    )
    raw = _read_regular_bytes(
        expected_path,
        expected_size=size,
        expected_sha256=transport,
    )
    parsed = json.loads(raw)
    if not isinstance(parsed, dict) or canonical_json_bytes(parsed) != raw:
        _fail("checkpoint staged typed bundle is not canonical JSON")
    bundle_sha256 = _digest(
        parsed.get("bundle_sha256"),
        "checkpoint typed-bundle semantic digest",
    )
    if record.get("bundle_sha256") != bundle_sha256:
        _fail("checkpoint typed-bundle semantic digest differs")
    try:
        admission = adapter.accept_bundle(
            expected_path,
            expected_bundle_sha256=bundle_sha256,
        )
    except RuntimeError as error:
        raise DirichletTBlockSupervisorError(
            "resumed v2 typed bundle failed fresh replay or deterministic "
            "adapter admission"
        ) from error
    nested_storage, compact_state = _nested_event_storage(parsed)
    identity = {
        "sequence_index": sequence_index,
        "ordinal": ordinal,
        "size_bytes": size,
        "transport_sha256": transport,
        "bundle_sha256": bundle_sha256,
        "admission_sha256": admission["admission_sha256"],
        "nested_storage_sha256": hashlib.sha256(
            canonical_json_bytes(nested_storage)
        ).hexdigest(),
    }
    expected = {
        **identity,
        "path": str(expected_path),
        "admission": admission,
        "nested_storage": nested_storage,
    }
    if dict(record) != expected:
        _fail("checkpoint typed-bundle replay/admission record differs")
    return expected, compact_state


def _compact_state_path(
    checkpoint_directory: Path,
    sequence_index: int,
    ordinal: int,
    q: int,
) -> Path:
    directory = checkpoint_directory / "compact-states"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / (
        f"block-{sequence_index:0{CHECKPOINT_NAME_WIDTH}d}-"
        f"target-{ordinal:08d}-q-{q:06d}.bin"
    )


def _compact_state_transition(
    *,
    sequence_index: int,
    ordinal: int,
    leaf: Mapping[str, Any],
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any],
    state_after_binary: Mapping[str, Any],
) -> dict[str, Any]:
    context = after["context"]
    before_signs = before["sign_change_lower_bound"] if before else 0
    leaf_signs = leaf["sign_change_lower_bound"]
    inserted = (
        after["sign_change_lower_bound"] - before_signs - leaf_signs
    )
    if inserted < 0:
        _fail("compact state transition lost a sign-change lower bound")
    body: dict[str, Any] = {
        "schema": COMPACT_STATE_TRANSITION_SCHEMA,
        "schema_version": 2,
        "classification": (
            "bounded_q_major_restart_transition_not_zero_or_turing_evidence"
        ),
        "sequence_index": sequence_index,
        "ordinal": ordinal,
        "q": context["q"],
        "leaf_state_sha256": leaf["state_sha256"],
        "state_before_sha256": (
            before["state_sha256"] if before is not None else None
        ),
        "state_after_sha256": after["state_sha256"],
        "state_after_binary": dict(state_after_binary),
        "first_t_numerator": context["first_t_numerator"],
        "stop_t_numerator": context["stop_t_numerator"],
        "leaf_event_summary_count_after": after[
            "leaf_event_summary_count"
        ],
        "sign_change_lower_bound_after": after[
            "sign_change_lower_bound"
        ],
        "ambiguity_sample_count_after": after[
            "ambiguity_sample_count"
        ],
        "cross_boundary_sign_changes_inserted": inserted,
        "exact_q_roster_grid_and_adjacency_validated": True,
        "canonical_binary_state_replayed": True,
        "exact_ambiguity_ranges_retained": True,
        "ordered_bracket_records_retained": True,
        "refinement_artifacts_complete": False,
        "turing_completeness": False,
        "source_scale_state_encoding": False,
        "external_atom_discharged": False,
    }
    result = dict(body)
    result["transition_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def _reduce_compact_states(
    compact_states: dict[int, dict[str, Any]],
    compact_binary_heads: dict[int, dict[str, Any]],
    *,
    leaf_states: Sequence[Mapping[str, Any] | None],
    artifacts: Sequence[Mapping[str, Any]],
    checkpoint_directory: Path,
    sequence_index: int,
    expected_transitions: object | None = None,
) -> list[dict[str, Any]]:
    """Merge every compact leaf and materialize/replay canonical q state."""

    if len(leaf_states) != len(artifacts):
        _fail("compact state leaf/artifact roster differs")
    compact_count = sum(leaf is not None for leaf in leaf_states)
    if compact_count not in (0, len(leaf_states)):
        _fail("one v2 block mixes raw and compact event state")
    if expected_transitions is not None and not isinstance(
        expected_transitions, list
    ):
        _fail("checkpoint compact state transition roster is malformed")
    if compact_count == 0:
        if expected_transitions not in (None, []):
            _fail("raw-event checkpoint unexpectedly contains compact state")
        return []
    if (
        expected_transitions is not None
        and len(expected_transitions) != len(leaf_states)
    ):
        _fail("checkpoint compact state transition count differs")
    transitions: list[dict[str, Any]] = []
    for ordinal, (leaf_value, artifact) in enumerate(
        zip(leaf_states, artifacts)
    ):
        assert leaf_value is not None
        leaf = dict(leaf_value)
        context = leaf["context"]
        q = context["q"]
        target = artifact["admission"]["target"]
        nested = artifact["nested_storage"]
        if (
            target.get("q") != q
            or nested.get("compact_state_leaf_sha256")
            != leaf["state_sha256"]
            or nested.get("compact_state_q") != q
            or nested.get("compact_state_first_t_numerator")
            != context["first_t_numerator"]
            or nested.get("compact_state_stop_t_numerator")
            != context["stop_t_numerator"]
        ):
            _fail("compact state leaf differs from its admitted typed bundle")
        before = compact_states.get(q)
        try:
            after = (
                leaf
                if before is None
                else combine_compact_state_summaries(before, leaf)
            )
        except DirichletStreamConsumerError as error:
            raise DirichletTBlockSupervisorError(
                f"compact state q/grid/adjacency merge failed: {error}"
            ) from error
        state_path = _compact_state_path(
            checkpoint_directory, sequence_index, ordinal, q
        )
        try:
            if expected_transitions is None:
                state_record = write_compact_state_binary(
                    state_path,
                    after,
                    maximum_bytes=MAXIMUM_COMPACT_STATE_BINARY_BYTES,
                )
                replayed = read_compact_state_binary(
                    state_path,
                    expected_record=state_record,
                    maximum_bytes=MAXIMUM_COMPACT_STATE_BINARY_BYTES,
                )
            else:
                expected = expected_transitions[ordinal]
                if not isinstance(expected, dict):
                    _fail("checkpoint compact state transition is malformed")
                expected_record = expected.get("state_after_binary")
                if not isinstance(expected_record, dict):
                    _fail(
                        "checkpoint compact state binary record is malformed"
                    )
                replayed = read_compact_state_binary(
                    state_path,
                    expected_record=expected_record,
                    maximum_bytes=MAXIMUM_COMPACT_STATE_BINARY_BYTES,
                )
                state_record = dict(expected_record)
        except DirichletCompactStateBinaryError as error:
            raise DirichletTBlockSupervisorError(
                f"compact state binary replay failed: {error}"
            ) from error
        if replayed != after:
            _fail("compact state binary semantic replay differs from merge")
        transition = _compact_state_transition(
            sequence_index=sequence_index,
            ordinal=ordinal,
            leaf=leaf,
            before=before,
            after=after,
            state_after_binary=state_record,
        )
        if (
            expected_transitions is not None
            and expected_transitions[ordinal] != transition
        ):
            _fail("checkpoint compact state transition differs after replay")
        transitions.append(transition)
        compact_states[q] = replayed
        compact_binary_heads[q] = dict(state_record)
    return transitions


def _compact_transition_chain(
    request_sha256: str,
    transitions: Sequence[Mapping[str, Any]],
) -> str:
    digest = hashlib.sha256(COMPACT_STATE_TRANSITION_CHAIN_DOMAIN)
    digest.update(bytes.fromhex(_digest(request_sha256, "v2 request")))
    digest.update(len(transitions).to_bytes(8, "little"))
    for transition in transitions:
        digest.update(
            bytes.fromhex(
                _digest(
                    transition.get("transition_sha256"),
                    "compact state transition",
                )
            )
        )
    return digest.hexdigest()


def _supervisor_result(
    *,
    request: Mapping[str, Any],
    artifacts: Sequence[Mapping[str, Any]],
    compact_state_transitions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    event_artifact_bytes = sum(
        artifact["nested_storage"]["event_artifact_size_bytes"]
        for artifact in artifacts
    )
    chain = _artifact_initial(request["request_sha256"])
    for artifact in artifacts:
        identity = {
            key: artifact[key]
            for key in (
                "sequence_index",
                "ordinal",
                "size_bytes",
                "transport_sha256",
                "bundle_sha256",
                "admission_sha256",
                "nested_storage_sha256",
            )
        }
        chain = _artifact_extend(chain, identity)
    result_after = extend_result_chain(
        before=request["result_chain_before"],
        request_sha256=request["request_sha256"],
        payload_stream_sha256=request["_payload_stream_sha256"],
        typed_bundle_count=len(artifacts),
        typed_bundle_chain_sha256=chain,
    )
    return {
        "artifact_count": len(artifacts),
        "artifact_chain_sha256": chain,
        "result_chain_before": request["result_chain_before"],
        "result_chain_after": result_after,
        "all_artifact_hashes_computed_by_supervisor": True,
        "all_typed_bundles_freshly_replayed_by_supervisor": True,
        "all_typed_bundles_admitted_by_tmajor_adapter": True,
        "event_artifact_bytes_freshly_replayed": event_artifact_bytes,
        "compact_event_resume_implemented": all(
            artifact["nested_storage"]["compact_event_resume_implemented"]
            for artifact in artifacts
        ),
        "compact_state_transition_count": len(compact_state_transitions),
        "compact_state_transition_chain_sha256": _compact_transition_chain(
            request["request_sha256"], compact_state_transitions
        ),
        "compact_state_binary_reducer_replayed": (
            bool(artifacts)
            and len(compact_state_transitions) == len(artifacts)
        ),
        "exact_ambiguity_ranges_retained": True,
        "ordered_bracket_records_retained": True,
        "checkpoint_permitted_after_admission": True,
        "production_multi_q_worker_completed": False,
        "cuda_execution_attested": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }


def _checkpoint(
    *,
    request: Mapping[str, Any],
    response: Mapping[str, Any],
    artifacts: Sequence[Mapping[str, Any]],
    compact_state_transitions: Sequence[Mapping[str, Any]],
    supervisor_result: Mapping[str, Any],
    checkpoint_chain_before: str,
) -> dict[str, Any]:
    persisted_request = {
        key: value
        for key, value in request.items()
        if key != "_payload_stream_sha256"
    }
    body: dict[str, Any] = {
        "schema": CHECKPOINT_SCHEMA,
        "schema_version": 2,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "sequence_index": request["sequence_index"],
        "checkpoint_chain_before": checkpoint_chain_before,
        "request": persisted_request,
        "response": dict(response),
        "staged_typed_bundles": [dict(item) for item in artifacts],
        "compact_state_transitions": [
            dict(item) for item in compact_state_transitions
        ],
        "supervisor_result": dict(supervisor_result),
    }
    body["checkpoint_chain_after"] = _chain(
        CHECKPOINT_CHAIN_DOMAIN, checkpoint_chain_before, body
    )
    result = dict(body)
    result["checkpoint_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def _checkpoint_path(directory: Path, sequence_index: int) -> Path:
    return directory / (
        f"block-{sequence_index:0{CHECKPOINT_NAME_WIDTH}d}.checkpoint.json"
    )


def _checkpoint_initial(
    spool: AuthenticatedQContiguousSpool,
    handshake_sha256: str,
) -> str:
    digest = hashlib.sha256(INITIAL_CHECKPOINT_CHAIN_DOMAIN)
    digest.update(bytes.fromhex(spool.contract["contract_sha256"]))
    digest.update(bytes.fromhex(spool.receipt_sha256))
    digest.update(spool.lane_index.to_bytes(4, "little"))
    digest.update(bytes.fromhex(handshake_sha256))
    digest.update(b"protocol-v2-bundle-admission\0")
    return digest.hexdigest()


def _resume(
    checkpoint_directory: Path,
    *,
    spool: AuthenticatedQContiguousSpool,
    handshake: Mapping[str, Any],
    roster_index: _RosterIndex,
    adapter: TMajorTypedBundleLaneAdapter,
    expected_checkpoint_chain_sha256: str | None,
    maximum_nested_event_bytes: int,
) -> tuple[
    int,
    str,
    str,
    int,
    int,
    int,
    int,
    dict[int, dict[str, Any]],
    dict[int, dict[str, Any]],
]:
    checkpoint_chain = _checkpoint_initial(
        spool, handshake["handshake_sha256"]
    )
    result_chain = initial_result_chain(
        source_contract_sha256=spool.contract["contract_sha256"],
        spool_receipt_sha256=spool.receipt_sha256,
        lane_index=spool.lane_index,
        handshake_sha256=handshake["handshake_sha256"],
    )
    total_targets = 0
    total_references = 0
    total_nested_event_bytes = 0
    total_compact_state_transitions = 0
    compact_states: dict[int, dict[str, Any]] = {}
    compact_binary_heads: dict[int, dict[str, Any]] = {}
    paths = _existing_checkpoint_paths(checkpoint_directory)
    for sequence_index, path in enumerate(paths):
        value = _read_regular_canonical(
            path, label="v2 t-block checkpoint"
        )
        _self_hash(
            value,
            "checkpoint_sha256",
            label="v2 t-block checkpoint",
        )
        first = spool.lane_start + sequence_index * FFT_BATCH_SIZE
        if first >= spool.lane_stop:
            _fail("v2 checkpoint sequence extends beyond the exact lane")
        stop = min(spool.lane_stop, first + FFT_BATCH_SIZE)
        request = _v2_request(
            spool,
            sequence_index=sequence_index,
            first_t_index=first,
            t_index_stop_exclusive=stop,
            result_chain_before=result_chain,
            roster_index=roster_index,
        )
        observed_request = value.get("request")
        if observed_request != request:
            _fail("v2 checkpoint request is substituted, skipped, or reordered")
        response = value.get("response")
        artifacts = value.get("staged_typed_bundles")
        if not isinstance(response, dict) or not isinstance(artifacts, list):
            _fail("v2 checkpoint response or artifact roster is malformed")
        payload_sha = _digest(
            response.get("payload_stream_sha256"),
            "resumed v2 payload stream",
        )
        request_with_payload = dict(request)
        request_with_payload["_payload_stream_sha256"] = payload_sha
        replayed_pairs = [
            _replay_staged_artifact(
                record,
                checkpoint_directory=checkpoint_directory,
                sequence_index=sequence_index,
                ordinal=ordinal,
                adapter=adapter,
            )
            for ordinal, record in enumerate(artifacts)
        ]
        replayed = [pair[0] for pair in replayed_pairs]
        leaf_states = [pair[1] for pair in replayed_pairs]
        total_nested_event_bytes += sum(
            artifact["nested_storage"]["event_artifact_size_bytes"]
            for artifact in replayed
        )
        if total_nested_event_bytes > maximum_nested_event_bytes:
            _fail(
                "resumed v2 event artifacts exceed the externally "
                "supplied bounded byte budget"
            )
        transitions = _reduce_compact_states(
            compact_states,
            compact_binary_heads,
            leaf_states=leaf_states,
            artifacts=replayed,
            checkpoint_directory=checkpoint_directory,
            sequence_index=sequence_index,
            expected_transitions=value.get("compact_state_transitions"),
        )
        total_compact_state_transitions += len(transitions)
        _validate_response(
            response,
            request=request,
            payload_stream_sha256=payload_sha,
            frame_count=len(replayed),
            handshake=handshake,
        )
        supervisor_result = _supervisor_result(
            request=request_with_payload,
            artifacts=replayed,
            compact_state_transitions=transitions,
        )
        expected = _checkpoint(
            request=request_with_payload,
            response=response,
            artifacts=replayed,
            compact_state_transitions=transitions,
            supervisor_result=supervisor_result,
            checkpoint_chain_before=checkpoint_chain,
        )
        if value != expected:
            _fail("v2 checkpoint chain or post-admission body differs")
        checkpoint_chain = value["checkpoint_chain_after"]
        result_chain = supervisor_result["result_chain_after"]
        total_targets += request["target_roster"]["active_q_count"]
        total_references += request["target_roster"][
            "target_row_reference_count"
        ]
    if expected_checkpoint_chain_sha256 is not None:
        if checkpoint_chain != _digest(
            expected_checkpoint_chain_sha256,
            "expected resumed v2 checkpoint head",
        ):
            _fail("resumed v2 checkpoint head differs from its external pin")
    return (
        len(paths),
        checkpoint_chain,
        result_chain,
        total_targets,
        total_references,
        total_nested_event_bytes,
        total_compact_state_transitions,
        compact_states,
        compact_binary_heads,
    )


def run_bundle_supervisor_v2(
    output_receipt_path: Path,
    checkpoint_directory: Path,
    *,
    contract_path: Path,
    spool_receipt_path: Path,
    expected_spool_receipt_sha256: str,
    worker_command: Sequence[str],
    allow_structural_kat: bool = False,
    allow_native_plan_switch_kat: bool = False,
    expected_contract_sha256: str | None = None,
    expected_worker_handshake_sha256: str | None = None,
    expected_worker_implementation_sha256: str | None = None,
    expected_worker_recipe_sha256: str | None = None,
    expected_runtime_artifacts_sha256: str | None = None,
    expected_checkpoint_chain_sha256: str | None = None,
    stop_after_blocks: int | None = None,
    maximum_nested_event_bytes: int = MAXIMUM_BOUNDED_NESTED_EVENT_BYTES,
) -> dict[str, Any]:
    """Run the bounded v2 path with fresh replay before every checkpoint."""

    if output_receipt_path.exists():
        _fail("final v2 supervisor receipt already exists")
    if stop_after_blocks is not None:
        _integer(stop_after_blocks, "stop-after block count", minimum=1)
    _integer(
        maximum_nested_event_bytes,
        "maximum nested event bytes",
        minimum=1,
        maximum=MAXIMUM_BOUNDED_NESTED_EVENT_BYTES,
    )
    checkpoint_directory.mkdir(parents=True, exist_ok=True)
    worker: _Worker | None = None
    with AuthenticatedQContiguousSpool(
        spool_receipt_path,
        contract_path=contract_path,
        expected_receipt_sha256=expected_spool_receipt_sha256,
        allow_structural_kat=allow_structural_kat,
        expected_contract_sha256=expected_contract_sha256,
    ) as spool:
        production = (
            spool.contract["classification"]
            == SOURCE_CONTRACT_CLASSIFICATION
        )
        if production:
            _fail(
                "production admission is disabled before worker launch: "
                "bounded v2 is not a real multi-q worker, row-resident CUDA "
                "service, zero-completeness proof, attested source run, or "
                "external-atom discharge"
            )
        schedule = spool.contract["schedule"]
        total_blocks = (
            spool.lane_stop - spool.lane_start + FFT_BATCH_SIZE - 1
        ) // FFT_BATCH_SIZE
        roster_index = _RosterIndex.build(
            schedule["q_start_inclusive"], schedule["q_stop_inclusive"]
        )
        for first in range(
            spool.lane_start, spool.lane_stop, FFT_BATCH_SIZE
        ):
            stop = min(spool.lane_stop, first + FFT_BATCH_SIZE)
            active, _references = roster_index.block_counts(first, stop)
            if active > MAXIMUM_BOUNDED_BUNDLES_PER_BLOCK:
                _fail(
                    "bounded v2 active-target count exceeds its fixed "
                    f"{MAXIMUM_BOUNDED_BUNDLES_PER_BLOCK}-bundle KAT limit"
                )
        worker = _Worker(worker_command)
        try:
            handshake = validate_bundle_worker_handshake(
                worker.read_line(label="v2 worker handshake"),
                production_contract=production,
                allow_structural_kat=allow_structural_kat,
                allow_native_plan_switch_kat=allow_native_plan_switch_kat,
                expected_handshake_sha256=(
                    expected_worker_handshake_sha256
                ),
                expected_implementation_sha256=(
                    expected_worker_implementation_sha256
                ),
                expected_recipe_sha256=expected_worker_recipe_sha256,
                expected_runtime_artifacts_sha256=(
                    expected_runtime_artifacts_sha256
                ),
            )
            adapter = TMajorTypedBundleLaneAdapter(
                contract_path,
                lane_index=spool.lane_index,
                allow_structural_kat=allow_structural_kat,
                expected_contract_sha256=expected_contract_sha256,
                target_order=BLOCK_MAJOR_TARGET_ORDER,
            )
            adapter.authenticate_all_rows()
            (
                next_sequence,
                checkpoint_chain,
                result_chain,
                total_targets,
                total_references,
                total_nested_event_bytes,
                total_compact_state_transitions,
                compact_states,
                compact_binary_heads,
            ) = _resume(
                checkpoint_directory,
                spool=spool,
                handshake=handshake,
                roster_index=roster_index,
                adapter=adapter,
                expected_checkpoint_chain_sha256=(
                    expected_checkpoint_chain_sha256
                ),
                maximum_nested_event_bytes=maximum_nested_event_bytes,
            )
            processed_this_invocation = 0
            for sequence_index in range(next_sequence, total_blocks):
                if (
                    stop_after_blocks is not None
                    and processed_this_invocation >= stop_after_blocks
                ):
                    break
                first = spool.lane_start + sequence_index * FFT_BATCH_SIZE
                stop = min(spool.lane_stop, first + FFT_BATCH_SIZE)
                request = _v2_request(
                    spool,
                    sequence_index=sequence_index,
                    first_t_index=first,
                    t_index_stop_exclusive=stop,
                    result_chain_before=result_chain,
                    roster_index=roster_index,
                )
                try:
                    worker.input.write(canonical_json_bytes(request))
                    payload_stream = hashlib.sha256()
                    observed_rows = 0
                    for t_index, payload in spool.iter_block_rows(
                        first_t_index=first,
                        t_index_stop_exclusive=stop,
                    ):
                        expected_row = request["row_block"]["rows"][
                            observed_rows
                        ]
                        if t_index != expected_row["t_index"]:
                            _fail("v2 streamed block row roster differs")
                        worker.input.write(payload)
                        payload_stream.update(payload)
                        observed_rows += 1
                    if observed_rows != request["row_block"]["row_count"]:
                        _fail("v2 streamed block row count differs")
                    worker.input.flush()
                except (BrokenPipeError, OSError) as error:
                    raise DirichletTBlockSupervisorError(
                        "v2 worker input closed during a t-block request"
                    ) from error
                payload_sha = payload_stream.hexdigest()
                frame_count = _validate_stream_header(
                    worker.read_line(label="v2 bundle-stream header"),
                    request=request,
                )
                artifacts: list[dict[str, Any]] = []
                leaf_states: list[dict[str, Any] | None] = []
                for ordinal in range(frame_count):
                    size, claimed_transport = _validate_frame_header(
                        worker.read_line(label="v2 typed-bundle frame header"),
                        request=request,
                        ordinal=ordinal,
                    )
                    encoded_length = worker.read_exact(
                        FRAME_LENGTH.size,
                        label="v2 typed-bundle length prefix",
                    )
                    framed_size = FRAME_LENGTH.unpack(encoded_length)[0]
                    if framed_size != size:
                        _fail("v2 typed-bundle length prefix differs")
                    raw = worker.read_exact(
                        size, label="v2 typed-bundle bytes"
                    )
                    observed_transport = hashlib.sha256(raw).hexdigest()
                    if observed_transport != claimed_transport:
                        _fail("v2 typed-bundle transport bytes are substituted")
                    artifact, leaf_state = _admit_raw_bundle(
                        raw,
                        checkpoint_directory=checkpoint_directory,
                        sequence_index=sequence_index,
                        ordinal=ordinal,
                        adapter=adapter,
                    )
                    artifacts.append(artifact)
                    leaf_states.append(leaf_state)
                block_nested_event_bytes = sum(
                    artifact["nested_storage"][
                        "event_artifact_size_bytes"
                    ]
                    for artifact in artifacts
                )
                if (
                    total_nested_event_bytes + block_nested_event_bytes
                    > maximum_nested_event_bytes
                ):
                    _fail(
                        "v2 event artifacts exceed the externally "
                        "supplied bounded byte budget"
                    )
                transitions = _reduce_compact_states(
                    compact_states,
                    compact_binary_heads,
                    leaf_states=leaf_states,
                    artifacts=artifacts,
                    checkpoint_directory=checkpoint_directory,
                    sequence_index=sequence_index,
                )
                response = _validate_response(
                    worker.read_line(label="v2 worker response"),
                    request=request,
                    payload_stream_sha256=payload_sha,
                    frame_count=frame_count,
                    handshake=handshake,
                )
                request_with_payload = dict(request)
                request_with_payload["_payload_stream_sha256"] = payload_sha
                supervisor_result = _supervisor_result(
                    request=request_with_payload,
                    artifacts=artifacts,
                    compact_state_transitions=transitions,
                )
                checkpoint = _checkpoint(
                    request=request_with_payload,
                    response=response,
                    artifacts=artifacts,
                    compact_state_transitions=transitions,
                    supervisor_result=supervisor_result,
                    checkpoint_chain_before=checkpoint_chain,
                )
                # This is deliberately after every accept_bundle call above.
                _atomic_json(
                    _checkpoint_path(
                        checkpoint_directory, sequence_index
                    ),
                    checkpoint,
                )
                checkpoint_chain = checkpoint["checkpoint_chain_after"]
                result_chain = supervisor_result["result_chain_after"]
                total_targets += request["target_roster"]["active_q_count"]
                total_references += request["target_roster"][
                    "target_row_reference_count"
                ]
                total_nested_event_bytes += block_nested_event_bytes
                total_compact_state_transitions += len(transitions)
                processed_this_invocation += 1

            completed_blocks = next_sequence + processed_this_invocation
            completed = completed_blocks == total_blocks
            expected_targets, expected_references = roster_index.lane_counts(
                spool.lane_start, spool.lane_stop
            )
            if completed and (
                total_targets != expected_targets
                or total_references != expected_references
            ):
                _fail("completed v2 t-block coverage totals differ")
            lane_receipt = adapter.finish_lane() if completed else None
            worker.finish()
            worker = None
            compact_state_heads = [
                {
                    "q": q,
                    "state_sha256": state["state_sha256"],
                    "first_t_numerator": state["context"][
                        "first_t_numerator"
                    ],
                    "stop_t_numerator": state["context"][
                        "stop_t_numerator"
                    ],
                    "primitive_character_count": state["context"][
                        "primitive_character_count"
                    ],
                    "leaf_event_summary_count": state[
                        "leaf_event_summary_count"
                    ],
                    "sign_change_lower_bound": state[
                        "sign_change_lower_bound"
                    ],
                    "ambiguity_sample_count": state[
                        "ambiguity_sample_count"
                    ],
                    "state_after_binary": dict(compact_binary_heads[q]),
                    "exact_ambiguity_ranges_retained": True,
                    "ordered_bracket_records_retained": True,
                    "turing_completeness": False,
                    "external_atom_discharged": False,
                }
                for q, state in sorted(compact_states.items())
            ]
            native_compact = (
                handshake["classification"]
                == NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION
            )
            body: dict[str, Any] = {
                "schema": RECEIPT_SCHEMA,
                "schema_version": 2,
                "author": AUTHOR,
                "atom_id": ATOM_ID,
                "algorithm_id": ALGORITHM_ID,
                "classification": RECEIPT_CLASSIFICATION,
                "source_contract_sha256": spool.contract[
                    "contract_sha256"
                ],
                "spool_receipt_sha256": spool.receipt_sha256,
                "lane_index": spool.lane_index,
                "worker_handshake_sha256": handshake[
                    "handshake_sha256"
                ],
                "worker_classification": handshake["classification"],
                "bundle_output_order": BLOCK_MAJOR_TARGET_ORDER,
                "expected_block_count": total_blocks,
                "expected_active_q_target_count": expected_targets,
                "expected_target_row_reference_count": expected_references,
                "completed_block_count": completed_blocks,
                "active_q_target_count": total_targets,
                "target_row_reference_count": total_references,
                "maximum_nested_event_bytes": maximum_nested_event_bytes,
                "event_artifact_bytes_retained": (
                    total_nested_event_bytes
                ),
                "compact_state_transition_count": (
                    total_compact_state_transitions
                ),
                "compact_state_q_count": len(compact_state_heads),
                "compact_state_heads": compact_state_heads,
                "maximum_compact_state_binary_bytes_per_q": (
                    MAXIMUM_COMPACT_STATE_BINARY_BYTES
                ),
                "checkpoint_chain_sha256": checkpoint_chain,
                "worker_result_chain_sha256": result_chain,
                "adapter_lane_receipt": lane_receipt,
                "complete": completed,
                "decisions": {
                    "actual_length_framed_typed_bundle_bytes_received": True,
                    "all_artifact_hashes_computed_by_supervisor": completed,
                    "all_typed_bundles_freshly_replayed": completed,
                    "all_typed_bundles_admitted_by_existing_tmajor_adapter": (
                        completed
                    ),
                    "checkpoints_written_only_after_artifact_admission": True,
                    "bounded_fixed_q_or_one_block_ordering_only": False,
                    "block_major_t_then_q_order_reconciled_at_adapter": True,
                    "real_multi_q_plan_switch_worker_executed": (
                        handshake["classification"]
                        == NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION
                    ),
                    "real_multi_q_worker_implemented": (
                        handshake["classification"]
                        == NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION
                    ),
                    "native_kat_event_bytes_recipe_bounded": (
                        handshake["classification"]
                        == NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION
                    ),
                    "native_kat_retained_output_bytes_recipe_bounded": (
                        handshake["classification"]
                        == NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION
                    ),
                    "content_addressed_shared_row_inputs_integrated": False,
                    "streamed_compact_event_resume_integrated": (
                        native_compact
                    ),
                    "compact_q_state_binary_checkpoint_resume_integrated": (
                        native_compact
                        and total_compact_state_transitions == total_targets
                    ),
                    "compact_q_state_exact_roster_grid_adjacency_validated": (
                        native_compact
                        and total_compact_state_transitions == total_targets
                    ),
                    "exact_ambiguity_ranges_retained": True,
                    "ordered_bracket_records_retained": True,
                    "refinement_artifacts_complete": False,
                    "source_scale_binary_state_encoding": False,
                    "source_scale_storage_admitted": False,
                    "nested_event_bytes_independently_accounted": True,
                    "raw_events_retained_for_fresh_resume_replay": (
                        not native_compact
                    ),
                    "row_resident_cuda_kernel_implemented": False,
                    "cuda_execution_attested": False,
                    "certified_analytic_inputs": False,
                    "source_evidence_produced": False,
                    "discarded_composition_arithmetic_independently_replayed": (
                        False
                    ),
                    "discarded_fft_arithmetic_independently_replayed": False,
                    "turing_completeness_claimed": False,
                    "trusted_execution_attested": False,
                    "zero_completeness_claimed": False,
                    "external_atom_discharged": False,
                },
            }
            receipt = dict(body)
            receipt["receipt_sha256"] = hashlib.sha256(
                canonical_json_bytes(body)
            ).hexdigest()
            if completed:
                _atomic_json(output_receipt_path, receipt)
            return receipt
        except BaseException:
            if worker is not None:
                worker.cancel()
            raise


def capability() -> dict[str, Any]:
    return {
        "algorithm_id": ALGORITHM_ID,
        "protocol_version": 2,
        "actual_length_framed_typed_bundle_transport": True,
        "supervisor_computes_transport_and_semantic_hashes": True,
        "fresh_typed_bundle_replay_per_artifact": True,
        "existing_tmajor_adapter_admission_per_artifact": True,
        "immutable_artifact_staging_and_post_admission_checkpoint": True,
        "resume_freshly_replays_every_staged_artifact": True,
        "block_major_t_then_q_adapter_order_implemented": True,
        "maximum_bounded_bundles_per_block": (
            MAXIMUM_BOUNDED_BUNDLES_PER_BLOCK
        ),
        "bounded_actual_native_multi_q_plan_switch_worker_implemented": True,
        "native_kat_event_and_retained_output_byte_budgets_implemented": True,
        "content_addressed_chunk_store_implemented": True,
        "bounded_memory_event_semantic_admission_implemented": True,
        "content_addressed_shared_row_inputs_integrated": False,
        "streamed_compact_event_resume_integrated": True,
        "compact_q_state_binary_checkpoint_resume_integrated": True,
        "compact_q_state_exact_roster_grid_adjacency_validation": True,
        "maximum_compact_state_binary_bytes_per_q": (
            MAXIMUM_COMPACT_STATE_BINARY_BYTES
        ),
        "exact_ambiguity_ranges_retained": True,
        "ordered_bracket_records_retained": True,
        "refinement_artifacts_complete": False,
        "source_scale_binary_state_encoding": False,
        "source_scale_storage_admitted": False,
        "production_multi_q_worker_implemented": False,
        "row_resident_cuda_kernel_implemented": True,
        "row_resident_cuda_worker_integrated_with_bundle_protocol": False,
        "cuda_execution_attested": False,
        "certified_analytic_inputs": False,
        "source_evidence_produced": False,
        "discarded_composition_arithmetic_independently_replayed": False,
        "discarded_fft_arithmetic_independently_replayed": False,
        "turing_completeness_claimed": False,
        "trusted_execution_attested": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "CHECKPOINT_CHAIN_DOMAIN",
    "FRAME_LENGTH",
    "FRAME_SCHEMA",
    "HANDSHAKE_SCHEMA",
    "MAXIMUM_BUNDLE_BYTES",
    "MAXIMUM_BOUNDED_BUNDLES_PER_BLOCK",
    "MAXIMUM_BOUNDED_NESTED_EVENT_BYTES",
    "MAXIMUM_BOUNDED_COMPACT_EVENT_SUMMARY_BYTES",
    "COMPACT_STATE_TRANSITION_SCHEMA",
    "NATIVE_PLAN_SWITCH_WORKER_CLASSIFICATION",
    "REQUEST_SCHEMA",
    "RESPONSE_SCHEMA",
    "STREAM_SCHEMA",
    "WORKER_ALGORITHM_ID",
    "WORKER_CLASSIFICATION",
    "capability",
    "run_bundle_supervisor_v2",
    "validate_bundle_worker_handshake",
]
