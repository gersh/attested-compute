# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed planning and artifact checks for the PT21 H100 campaign.

This module deliberately separates *schedulable geometry* from *execution
readiness*.  It can enumerate immutable Azure shards now, but refuses to mark
the campaign runnable until the fused interpolation, three-stream event, and
paired-flank Turing stages have pinned implementations.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


PLAN_SCHEMA = "sparkinterval.tg.platt-pt21-h100-plan.v1"
BLOCK_SCHEMA = "sparkinterval.tg.platt-pt21-block-closure.v1"
RECEIPT_SCHEMA = "sparkinterval.tg.platt-pt21-h100-shard-receipt.v1"
PLAN_DOMAIN = b"sparkinterval/tg/platt-pt21-h100-plan/v1\0"
SOURCE_LOWER = 10_000_000_000
SOURCE_LOWER_CENTER = 10_000_000_504
SOURCE_HEIGHT = 3_000_175_332_800
FULL_BLOCK_COUNT = 2_966_443_783
FULL_COVERAGE_UPPER = 3_000_175_333_264
STEP = 1_008
DEFAULT_BLOCKS_PER_SHARD = 1 << 20
MAIN_RANGE = (-12_288, 12_288)
LEFT_RANGE = (-12_800, -12_288)
RIGHT_RANGE = (12_288, 12_800)
REQUIRED_RANGE = (-12_870, 12_870)
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class PlattH100CampaignError(RuntimeError):
    """A plan or artifact failed a fixed semantic gate."""


# These are implementation facts, not user-selectable planning assumptions.
CURRENT_CAPABILITIES: dict[str, dict[str, object]] = {
    "q192_dd_source_reanchor": {
        "status": "periodic_direct_reanchor_plus_fast_dd_accumulator_with_mpfr_kats",
        "all_window_shard_offsets": True,
        "phase_recurrence_implemented": True,
        "periodic_direct_reanchor_supported": True,
        "final_height_mpfr_spot_kat": True,
        "fast_dd_accumulator_algorithm": "bounded-fast-dd-center-l1-radius-v1",
        "fast_dd_accumulator_mpfr_differential_kat_cases": 24,
        "fast_dd_accumulator_mpfr_differential_kat_failures": 0,
        "fast_dd_accumulator_isolated_speedup": 2.8243,
        "measured_gb10_blocks_per_second_64_block_sample": 56.8761942,
        "previous_recurrence_and_legacy_accumulator_gb10_blocks_per_second": 21.514480073023694,
        "previous_every_block_reanchor_gb10_blocks_per_second": 15.372354929792206,
        "combined_accumulator_and_dd_transform_gb10_blocks_per_second": 9.5163,
        "required_region_ambiguities_after_fast_accumulator": 0,
        "physical_trace_refinement_proved": False,
    },
    "gamma_taylor_coefficients": {
        "status": "source_pinned_v1_and_two_limb_v2_streams_plus_bounded_cuda_synthesis",
        "all_window_stream": True,
        "fixed_record_bytes": 264,
        "v2_fixed_record_bytes": 312,
        "v2_coefficient_encoding": "complex_disk106",
        "v2_exact_gaussian_rational": "1/26912",
        "chunk_sha256": True,
        "complete_stream_sha256": True,
        "bounded_authenticated_chunk_iterator": True,
        "bounded_authenticated_cpp_consumer": True,
        "cpp_consumer_rejects_payload_and_footer_mutation": True,
        "cpp_consumer_requires_footer_before_final_acceptance": True,
        "gpu_chunk_consumer": True,
        "gpu_chunks_authenticated_before_use": True,
        "gpu_exact_shard_range_required": True,
        "gpu_footer_and_global_digest_required_before_acceptance": True,
        "gpu_rows_retained_device_resident": True,
        "gpu_cuda_graph_microbatch_records": 64,
        "measured_gb10_gpu_pipeline_records_per_second": 1_892.24,
        "measured_gb10_end_to_end_records_per_second": 1_828.93,
        "projected_single_gb10_full_source_elapsed_hours": 450.54,
        "projected_ideal_eight_gb10_full_source_elapsed_hours": 56.32,
        "v2_low_100000_records_per_second": 32_881.6020,
        "v2_terminal_100000_records_per_second": 42_966.7462,
        "v2_projected_single_cpu_full_source_hours_low_sample": 25.0600,
        "v2_projected_single_cpu_full_source_hours_terminal_sample": 19.1779,
        "v2_full_retained_payload_bytes": 925_530_460_296,
        "v2_seven_day_aggregate_fifo_bytes_per_second": 1_530_309,
        "h100_rate_measured": False,
        "flint_to_mathlib_realization_proved": False,
    },
    "dd_gamma_row": {
        "status": "authenticated_v2_two_limb_synthesizer_fused_through_required_transform",
        "all_window_gamma_row_synthesis": True,
        "authenticated_taylor_chunk_consumer": True,
        "device_resident_rows": True,
        "fused_accumulator_consumer": True,
        "device_transcendentals_used": False,
        "dd_exp_range_reduction_and_taylor_remainder": True,
        "dd_q192_phase_and_residual_trig": True,
        "full_first_row_direct_flint_containment_failures": 0,
        "full_terminal_row_direct_flint_containment_failures": 0,
        "first_row_maximum_radius": 4.4363041847913005e-25,
        "terminal_row_maximum_radius": 2.2206775699461235e-22,
        "source_wide_width_usefulness_proved": False,
    },
    "dd_required_region_transform": {
        "status": "persistent_device_api_plus_authenticated_fused_source_worker",
        "replayable_required_sign_packet": True,
        "persistent_source_geometry_workspace": True,
        "device_to_device_gamma_and_skn_inputs": True,
        "host_source_packet_required_between_accumulator_and_transform": False,
        "workspace_device_bytes": 195_429_312,
        "authenticated_gamma_accumulator_transform_stream": True,
        "historical_v1_fused_gb10_blocks_per_second_two_block_sample": 9.4754,
        "historical_v1_fused_sample_ambiguous_required_disks": 41,
        "v1_gamma_width_regression_against_direct_v2_packet": True,
        "v2_first_64_fused_gb10_blocks_per_second": 9.2043,
        "v2_terminal_64_fused_gb10_blocks_per_second": 9.1961,
        "v2_first_64_invalid_required_disks": 0,
        "v2_first_64_ambiguous_required_disks": 0,
        "v2_terminal_64_invalid_required_disks": 0,
        "v2_terminal_64_ambiguous_required_disks": 0,
        "v2_first_64_maximum_required_radius": 2.929562605879431e-12,
        "v2_terminal_64_maximum_required_radius": 4.0676286523638164e-10,
        "v2_strict_sm90_binary_builds": True,
        "all_window_fused_stream": False,
        "all_window_fused_stream_blocker": "source-wide width usefulness, stationary Gaussian-sinc resolution, and Turing acceptance have not run",
    },
    "gaussian_sinc_interpolation": {
        "status": "bounded_cpu_flint_stationary_resolver_not_fused",
        "source_terms_per_query": 140,
        "corrected_interpolation_error_applied": True,
        "independent_higher_precision_replay": True,
        "fused_event_root_binding": False,
        "measured_worker": False,
    },
    "main_zero_event_stream": {
        "status": "fused_device_scanner_with_authenticated_nonterminal_record",
        "exact_source_range": [-12_288, 12_288],
        "stable_compaction": True,
        "fused_source_emission": True,
        "event_record_magic": "PT21EVT1",
        "event_record_bytes": 192,
    },
    "left_turing_flank_event_stream": {
        "status": "fused_device_scanner_with_authenticated_nonterminal_record",
        "exact_source_range": [-12_800, -12_288],
        "stable_compaction": True,
        "fused_source_emission": True,
        "event_record_magic": "PT21EVT1",
        "event_record_bytes": 192,
    },
    "right_turing_flank_event_stream": {
        "status": "fused_device_scanner_with_authenticated_nonterminal_record",
        "exact_source_range": [12_288, 12_800],
        "stable_compaction": True,
        "fused_source_emission": True,
        "event_record_magic": "PT21EVT1",
        "event_record_bytes": 192,
    },
    "three_stream_event_scanner": {
        "status": "fused_cuda_stage_plus_independent_fixed_integer_host_replay_and_compact_wire",
        "strict_source_stat_pt": True,
        "shared_endpoints_checked": True,
        "stationary_candidates_certify_zero_slots": True,
        "malformed_ambiguous_and_overflow_fail_closed": True,
        "artifact_sha256_merkle_bound": True,
        "fused_after_v2_transform": True,
        "required_sign_packet_retained": False,
        "compact_record_terminal_authentication": True,
        "compact_record_python_independent_replay": True,
        "compact_record_lean_finite_checker": True,
        "compact_record_full_source_bytes_if_retained": 569_557_206_336,
        "production_design_streams_without_retention": True,
        "measured_gb10_scans_per_second": 254.163,
        "adaptive_stationary_resolution": False,
    },
    "paired_flank_turing_closure": {
        "status": "three_stream_finite_lean_checker_decoder_and_reference_finalizer_proved",
        "current_one_list_lean_contract_compatible": False,
        "separate_left_main_right_streams": True,
        "zero_simplicity_assumed": False,
        "source_artifact_decoder": True,
        "deterministic_required_packet_to_v2_artifact_finalizer": True,
        "stationary_dyadic_brackets_separate_from_multiplicity_two_cells": True,
        "turing_quotients_and_integer_roundings_independently_recomputed": True,
        "current_fused_producer_emits_artifact": False,
        "analytic_turing_realization": False,
    },
    "touching_bracket_lean_bridge": {
        "status": "exact_rational_checker_and_distinct_root_theorem",
        "producer_artifacts_may_touch": True,
        "closed_endpoint_touching_supported": True,
        "strict_signs_force_interior_roots": True,
        "zero_simplicity_assumed": False,
        "source_packet_decoder": True,
        "endpoint_enclosure_realization": False,
    },
    "global_count_finalizer": {"status": "cpu_transcript_only"},
    "compact_artifact_chain_finalizer": {
        "status": "native_fixed_width_streaming_v1_plus_validated_record_adapter_and_independent_python_full_replay",
        "gap_free_shard_and_campaign_chains": True,
        "block_and_shard_merkle_roots": True,
        "exact_source_height_count_recomputed": True,
        "production_scale_native_implementation": True,
        "retained_export_independent_replay": True,
        "bounded_memory_native_finalization": True,
        "bounded_memory_python_replay": True,
        "sparse_refinement_commitments_bound": True,
        "all_finite_failure_counters_must_be_zero": True,
        "every_record_bound_to_measured_worker": True,
        "source_height_count_linked_to_partial_block_slots": True,
        "canonical_record_adapter_implemented": True,
        "adapter_rechecks_required_packet_signs": True,
        "adapter_validates_stationary_replay_and_sparse_refinements": True,
        "adapter_validates_arb_turing_inputs": True,
        "adapter_rebuilds_exact_rational_block_artifact": True,
        "adapter_streams_gap_free_shard_manifests": True,
        "adapter_streams_records_directly_to_native_shard_finalizer": True,
        "adapter_terminal_manifest_authentication": True,
        "intermediate_native_record_spool_required": False,
        "adapter_source": "tg_verifier/platt_pt21_native_record_adapter.py",
        "measured_worker_emits_native_records": False,
    },
    "fused_measured_h100_worker": {
        "status": "required_transform_and_three_stream_event_record_emission_complete_stationary_and_turing_outputs_missing",
        "adapter_to_native_shard_stream_complete": True,
        "compact_nonterminal_event_record_emission": True,
        "compact_nonterminal_event_record_magic": "PT21EVT1",
        "compact_nonterminal_event_record_bytes": 192,
        "compact_nonterminal_event_record_terminal_authentication": True,
        "source_packet_retention_required": False,
        "direct_native_record_emission": False,
        "hardy_z_endpoint_realization_proved": False,
        "main_multiplicity_realization_proved": False,
        "analytic_turing_realization_proved": False,
        "lean_source_claim_ready": False,
    },
}

EXECUTION_BLOCKERS = (
    "dd_required_region_transform.all_window_fused_stream",
    "gaussian_sinc_interpolation.measured_worker",
    "paired_flank_turing_closure.current_fused_producer_emits_artifact",
    "paired_flank_turing_closure.analytic_turing_realization",
    "touching_bracket_lean_bridge.endpoint_enclosure_realization",
    "compact_artifact_chain_finalizer.measured_worker_emits_native_records",
    "fused_measured_h100_worker.status",
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + _canonical(value)).hexdigest()


def current_readiness() -> dict[str, object]:
    return {
        "schema": "sparkinterval.tg.platt-pt21-h100-readiness.v1",
        "azure_geometry_schedulable": True,
        "azure_proof_execution_ready": False,
        "lean_source_claim_ready": False,
        "capabilities": CURRENT_CAPABILITIES,
        "blocking_gates": list(EXECUTION_BLOCKERS),
        "formal_contract_blockers": [
            "the three-stream finite Turing closure, v2 compact decoder, and deterministic exact-rational reference finalizer are proved, but the measured all-window H100 producer does not yet emit the required source trace and the analytic Turing realization is not implemented",
            "the touching-bracket theorem and exact-rational decoder are proved, but actual Hardy-Z endpoint-enclosure and multiplicity-slot realizations are not implemented",
        ],
    }


def create_plan(
    *,
    worker_sha256: str,
    worker_size: int,
    blocks_per_shard: int = DEFAULT_BLOCKS_PER_SHARD,
    block_count: int = FULL_BLOCK_COUNT,
    allow_bounded_test: bool = False,
) -> dict[str, Any]:
    if not SHA256_RE.fullmatch(worker_sha256) or worker_size < 1:
        raise PlattH100CampaignError("worker identity is malformed")
    if blocks_per_shard < 1 or block_count < 1:
        raise PlattH100CampaignError("campaign geometry must be positive")
    if block_count != FULL_BLOCK_COUNT and not allow_bounded_test:
        raise PlattH100CampaignError("bounded geometry requires allow_bounded_test")
    if block_count > FULL_BLOCK_COUNT:
        raise PlattH100CampaignError("campaign exceeds the fixed source range")
    shard_count = (block_count + blocks_per_shard - 1) // blocks_per_shard
    value: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "mode": "full" if block_count == FULL_BLOCK_COUNT else "bounded_test",
        "worker": {"sha256": worker_sha256, "size_bytes": worker_size},
        "geometry": {
            "source_lower": SOURCE_LOWER,
            "source_lower_center": SOURCE_LOWER_CENTER,
            "source_height": SOURCE_HEIGHT,
            "step": STEP,
            "block_count": block_count,
            "coverage_upper": SOURCE_LOWER + block_count * STEP,
            "blocks_per_shard": blocks_per_shard,
            "shard_count": shard_count,
            "required_sample_offsets": list(REQUIRED_RANGE),
            "main_sample_offsets": list(MAIN_RANGE),
            "left_flank_sample_offsets": list(LEFT_RANGE),
            "right_flank_sample_offsets": list(RIGHT_RANGE),
        },
        "event_stream_contract": {
            "streams": ["main", "left_flank", "right_flank"],
            "touching_bracket_endpoints_allowed": True,
            "interior_overlap_allowed": False,
            "block_boundary_endpoints_allowed": True,
            "shared_endpoint_must_have_one_nonzero_sign": True,
        },
        "turing_contract": {
            "lower_count_source": "left_flank_only",
            "isolated_count_source": "main_only",
            "upper_count_source": "right_flank_only",
            "required_equation": "lower_count + main_isolated_slots = upper_count",
        },
        "execution": {
            "azure_geometry_schedulable": True,
            "azure_proof_execution_ready": False,
            "blocking_gates": list(EXECUTION_BLOCKERS),
            "partial_or_preempted_shard_accepted": False,
        },
        "allow_bounded_test": allow_bounded_test,
    }
    value["plan_sha256"] = _digest(PLAN_DOMAIN, value)
    return value


def validate_plan(plan: dict[str, Any]) -> None:
    digest = plan.get("plan_sha256")
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if plan.get("schema") != PLAN_SCHEMA or digest != _digest(PLAN_DOMAIN, body):
        raise PlattH100CampaignError("H100 plan schema or digest differs")
    rebuilt = create_plan(
        worker_sha256=plan["worker"]["sha256"],
        worker_size=plan["worker"]["size_bytes"],
        blocks_per_shard=plan["geometry"]["blocks_per_shard"],
        block_count=plan["geometry"]["block_count"],
        allow_bounded_test=plan["allow_bounded_test"],
    )
    if rebuilt != plan:
        raise PlattH100CampaignError("H100 plan values differ from fixed geometry")


def shard_task(plan: dict[str, Any], shard_index: int) -> dict[str, object]:
    validate_plan(plan)
    shard_count = plan["geometry"]["shard_count"]
    if shard_index < 0 or shard_index >= shard_count:
        raise PlattH100CampaignError("shard index is outside the plan")
    span = plan["geometry"]["blocks_per_shard"]
    first = shard_index * span
    upper = min(first + span, plan["geometry"]["block_count"])
    return {
        "schema": "sparkinterval.tg.platt-pt21-h100-azure-task.v1",
        "plan_sha256": plan["plan_sha256"],
        "shard_index": shard_index,
        "first_block": first,
        "upper_block_exclusive": upper,
        "block_count": upper - first,
        "height_lower": SOURCE_LOWER + first * STEP,
        "height_upper": SOURCE_LOWER + upper * STEP,
        "window_center_first": SOURCE_LOWER_CENTER + first * STEP,
        "checkpoint_after_complete_block_only": True,
        "spot_retry_discards_partial_attempt": True,
        "azure_geometry_schedulable": True,
        "azure_proof_execution_ready": False,
        "gamma_taylor_input": {
            "schema": "sparkinterval.tg.platt-gamma-taylor-stream.v2",
            "first_block": first,
            "block_count": upper - first,
            "record_bytes": 312,
            "chunk_records": 4096,
            "expected_stream_sha256_required_by_worker": True,
            "producer_command_template": [
                "PINNED_GAMMA_TAYLOR_V2_PRODUCER",
                "--stream-first-block",
                str(first),
                "--stream-blocks",
                str(upper - first),
                "--stream-chunk-records",
                "4096",
                "--stream-audit-stride",
                "1048576",
                "--audit-samples",
                "9",
                "--stream-output",
                "GAMMA_TAYLOR_STREAM",
            ],
            "gpu_chunk_consumer_implemented": True,
        },
        "command_template": [
            "PINNED_FUSED_WORKER",
            "--pt21-h100-shard",
            f"--first-block={first}",
            f"--block-count={upper - first}",
            "--require-all-stage-gates",
            "--emit-measured-shard-receipt=OUTPUT",
        ],
        "blocking_gates": list(EXECUTION_BLOCKERS),
    }


def _integer_sign(value: object, label: str) -> int:
    if not isinstance(value, int) or value not in (-1, 1):
        raise PlattH100CampaignError(f"{label} must be -1 or 1")
    return value


def _validate_stream(name: str, stream: dict[str, Any], fixed_range: tuple[int, int]) -> int:
    if stream.get("sample_range") != list(fixed_range):
        raise PlattH100CampaignError(f"{name} sample range differs")
    brackets = stream.get("brackets")
    if not isinstance(brackets, list):
        raise PlattH100CampaignError(f"{name} brackets must be a list")
    previous: dict[str, Any] | None = None
    for index, bracket in enumerate(brackets):
        if not isinstance(bracket, dict) or set(bracket) != {
            "lower_sample",
            "upper_sample",
            "lower_sign",
            "upper_sign",
            "resolver",
        }:
            raise PlattH100CampaignError(f"{name} bracket {index} shape differs")
        lower = bracket["lower_sample"]
        upper = bracket["upper_sample"]
        if (
            not isinstance(lower, int)
            or not isinstance(upper, int)
            or lower < fixed_range[0]
            or upper > fixed_range[1]
            or lower >= upper
        ):
            raise PlattH100CampaignError(f"{name} bracket {index} range is invalid")
        lower_sign = _integer_sign(bracket["lower_sign"], "lower_sign")
        upper_sign = _integer_sign(bracket["upper_sign"], "upper_sign")
        if lower_sign == upper_sign:
            raise PlattH100CampaignError(f"{name} bracket {index} lacks a sign change")
        if bracket["resolver"] not in {
            "direct",
            "stationary_left",
            "stationary_right",
            "pinned_arb_fallback",
        }:
            raise PlattH100CampaignError(f"{name} bracket resolver is unknown")
        if previous is not None:
            if previous["upper_sample"] > lower:
                raise PlattH100CampaignError(f"{name} bracket interiors overlap")
            if (
                previous["upper_sample"] == lower
                and previous["upper_sign"] != lower_sign
            ):
                raise PlattH100CampaignError(
                    f"{name} touching brackets disagree at the shared endpoint"
                )
        previous = bracket
    if stream.get("slot_count") != len(brackets):
        raise PlattH100CampaignError(f"{name} slot count differs")
    weight = stream.get("turing_weight")
    if not isinstance(weight, dict) or set(weight) != {"numerator", "denominator"}:
        raise PlattH100CampaignError(f"{name} Turing weight is malformed")
    if not isinstance(weight["numerator"], int) or not isinstance(
        weight["denominator"], int
    ) or weight["denominator"] <= 0:
        raise PlattH100CampaignError(f"{name} Turing weight is not rational")
    return len(brackets)


def validate_block_artifact(value: dict[str, Any]) -> dict[str, object]:
    if value.get("schema") != BLOCK_SCHEMA:
        raise PlattH100CampaignError("block artifact schema differs")
    block = value.get("block")
    if not isinstance(block, int) or block < 0 or block >= FULL_BLOCK_COUNT:
        raise PlattH100CampaignError("block index is outside the campaign")
    expected_lower = SOURCE_LOWER + block * STEP
    if value.get("height_lower") != expected_lower or value.get(
        "height_upper"
    ) != expected_lower + STEP:
        raise PlattH100CampaignError("block heights differ from the fixed grid")
    if not SHA256_RE.fullmatch(str(value.get("required_sign_packet_sha256", ""))):
        raise PlattH100CampaignError("required-sign packet digest is malformed")
    streams = value.get("streams")
    if not isinstance(streams, dict) or set(streams) != {
        "main",
        "left_flank",
        "right_flank",
    }:
        raise PlattH100CampaignError("three distinct event streams are required")
    main_slots = _validate_stream("main", streams["main"], MAIN_RANGE)
    _validate_stream("left_flank", streams["left_flank"], LEFT_RANGE)
    _validate_stream("right_flank", streams["right_flank"], RIGHT_RANGE)
    turing = value.get("paired_turing")
    required_turing = {
        "lower_count",
        "upper_count",
        "main_isolated_slots",
        "left_ceiling_unique",
        "right_floor_unique",
        "endpoint_parity_matches",
        "closure_equation_holds",
    }
    if not isinstance(turing, dict) or set(turing) != required_turing:
        raise PlattH100CampaignError("paired Turing artifact shape differs")
    if turing["main_isolated_slots"] != main_slots:
        raise PlattH100CampaignError("main isolated slot count differs")
    if not all(
        turing[key] is True
        for key in (
            "left_ceiling_unique",
            "right_floor_unique",
            "endpoint_parity_matches",
            "closure_equation_holds",
        )
    ):
        raise PlattH100CampaignError("paired Turing decision is not unique and closed")
    lower_count = turing["lower_count"]
    upper_count = turing["upper_count"]
    if (
        not isinstance(lower_count, int)
        or not isinstance(upper_count, int)
        or lower_count + main_slots != upper_count
    ):
        raise PlattH100CampaignError("paired Turing count equation differs")
    policy = value.get("producer_bracket_policy")
    if policy != {
        "touching_endpoints_allowed": True,
        "interior_overlap_allowed": False,
        "block_boundary_endpoints_allowed": True,
    }:
        raise PlattH100CampaignError("producer bracket policy differs")
    lean = value.get("lean_conversion")
    if not isinstance(lean, dict) or lean.get("available") is not False:
        raise PlattH100CampaignError(
            "current artifacts must not claim the missing Lean conversion"
        )
    required_blockers = {
        "enriched_endpoint_enclosure_packet_missing",
        "analytic_realization_missing",
    }
    if set(lean.get("blockers", [])) != required_blockers:
        raise PlattH100CampaignError("Lean conversion blockers differ")
    return {
        "accepted": True,
        "computation_artifact_valid": True,
        "main_isolated_slots": main_slots,
        "lower_count": lower_count,
        "upper_count": upper_count,
        "three_event_streams_distinct": True,
        "touching_brackets_checked": True,
        "lean_wire_bridge_implemented": True,
        "lean_conversion_available": False,
        "lean_source_claim_ready": False,
    }


__all__ = [
    "BLOCK_SCHEMA",
    "CURRENT_CAPABILITIES",
    "DEFAULT_BLOCKS_PER_SHARD",
    "FULL_BLOCK_COUNT",
    "PlattH100CampaignError",
    "create_plan",
    "current_readiness",
    "shard_task",
    "validate_block_artifact",
    "validate_plan",
]
