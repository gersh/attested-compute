# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest

from tg_verifier.platt_h100_campaign import (
    BLOCK_SCHEMA,
    FULL_BLOCK_COUNT,
    PlattH100CampaignError,
    create_plan,
    current_readiness,
    shard_task,
    validate_block_artifact,
    validate_plan,
)


def stream(sample_range: tuple[int, int], brackets: list[dict[str, object]]) -> dict[str, object]:
    return {
        "sample_range": list(sample_range),
        "brackets": brackets,
        "slot_count": len(brackets),
        "turing_weight": {"numerator": len(brackets), "denominator": 1},
    }


def block_artifact() -> dict[str, object]:
    return {
        "schema": BLOCK_SCHEMA,
        "block": 0,
        "height_lower": 10_000_000_000,
        "height_upper": 10_000_001_008,
        "required_sign_packet_sha256": "ab" * 32,
        "streams": {
            "main": stream(
                (-12_288, 12_288),
                [
                    {
                        "lower_sample": -1,
                        "upper_sample": 0,
                        "lower_sign": -1,
                        "upper_sign": 1,
                        "resolver": "stationary_left",
                    },
                    {
                        "lower_sample": 0,
                        "upper_sample": 1,
                        "lower_sign": 1,
                        "upper_sign": -1,
                        "resolver": "stationary_right",
                    },
                ],
            ),
            "left_flank": stream(
                (-12_800, -12_288),
                [
                    {
                        "lower_sample": -12_800,
                        "upper_sample": -12_799,
                        "lower_sign": -1,
                        "upper_sign": 1,
                        "resolver": "direct",
                    }
                ],
            ),
            "right_flank": stream(
                (12_288, 12_800),
                [
                    {
                        "lower_sample": 12_799,
                        "upper_sample": 12_800,
                        "lower_sign": 1,
                        "upper_sign": -1,
                        "resolver": "direct",
                    }
                ],
            ),
        },
        "paired_turing": {
            "lower_count": 100,
            "upper_count": 102,
            "main_isolated_slots": 2,
            "left_ceiling_unique": True,
            "right_floor_unique": True,
            "endpoint_parity_matches": True,
            "closure_equation_holds": True,
        },
        "producer_bracket_policy": {
            "touching_endpoints_allowed": True,
            "interior_overlap_allowed": False,
            "block_boundary_endpoints_allowed": True,
        },
        "lean_conversion": {
            "available": False,
            "blockers": [
                "enriched_endpoint_enclosure_packet_missing",
                "analytic_realization_missing",
            ],
        },
    }


class PlattH100CampaignTest(unittest.TestCase):
    def test_plan_is_schedulable_but_not_ready(self) -> None:
        plan = create_plan(worker_sha256="12" * 32, worker_size=123)
        validate_plan(plan)
        self.assertEqual(plan["geometry"]["block_count"], FULL_BLOCK_COUNT)
        self.assertTrue(plan["execution"]["azure_geometry_schedulable"])
        self.assertFalse(plan["execution"]["azure_proof_execution_ready"])
        task = shard_task(plan, 0)
        self.assertEqual(task["first_block"], 0)
        self.assertEqual(task["block_count"], 1 << 20)
        self.assertEqual(task["gamma_taylor_input"]["first_block"], 0)
        self.assertEqual(task["gamma_taylor_input"]["block_count"], 1 << 20)
        self.assertEqual(
            task["gamma_taylor_input"]["schema"],
            "sparkinterval.tg.platt-gamma-taylor-stream.v2",
        )
        self.assertEqual(task["gamma_taylor_input"]["record_bytes"], 312)
        self.assertTrue(
            task["gamma_taylor_input"][
                "expected_stream_sha256_required_by_worker"
            ]
        )
        self.assertTrue(
            task["gamma_taylor_input"]["gpu_chunk_consumer_implemented"]
        )
        self.assertFalse(task["azure_proof_execution_ready"])
        self.assertFalse(current_readiness()["lean_source_claim_ready"])
        gamma = current_readiness()["capabilities"]["gamma_taylor_coefficients"]
        self.assertTrue(gamma["all_window_stream"])
        self.assertTrue(gamma["bounded_authenticated_chunk_iterator"])
        self.assertTrue(gamma["gpu_chunk_consumer"])
        self.assertNotIn(
            "dd_gamma_row.authenticated_taylor_chunk_consumer",
            current_readiness()["blocking_gates"],
        )
        self.assertTrue(
            current_readiness()["capabilities"]["dd_gamma_row"][
                "all_window_gamma_row_synthesis"
            ]
        )
        touching = current_readiness()["capabilities"]["touching_bracket_lean_bridge"]
        self.assertTrue(touching["closed_endpoint_touching_supported"])
        self.assertTrue(touching["source_packet_decoder"])
        self.assertFalse(touching["endpoint_enclosure_realization"])
        paired = current_readiness()["capabilities"]["paired_flank_turing_closure"]
        self.assertTrue(paired["separate_left_main_right_streams"])
        self.assertTrue(paired["source_artifact_decoder"])
        self.assertTrue(
            paired["deterministic_required_packet_to_v2_artifact_finalizer"]
        )
        self.assertTrue(
            paired["stationary_dyadic_brackets_separate_from_multiplicity_two_cells"]
        )
        self.assertFalse(paired["current_fused_producer_emits_artifact"])
        for capability in (
            "main_zero_event_stream",
            "left_turing_flank_event_stream",
            "right_turing_flank_event_stream",
        ):
            event_stream = current_readiness()["capabilities"][capability]
            self.assertTrue(event_stream["fused_source_emission"])
            self.assertEqual(event_stream["event_record_magic"], "PT21EVT1")
            self.assertNotIn(
                f"{capability}.fused_source_emission",
                current_readiness()["blocking_gates"],
            )
        scanner = current_readiness()["capabilities"][
            "three_stream_event_scanner"
        ]
        self.assertTrue(scanner["fused_after_v2_transform"])
        self.assertFalse(scanner["required_sign_packet_retained"])
        self.assertTrue(scanner["compact_record_terminal_authentication"])
        self.assertTrue(scanner["compact_record_lean_finite_checker"])
        self.assertFalse(scanner["adaptive_stationary_resolution"])
        finalizer = current_readiness()["capabilities"][
            "compact_artifact_chain_finalizer"
        ]
        self.assertTrue(finalizer["gap_free_shard_and_campaign_chains"])
        self.assertTrue(finalizer["production_scale_native_implementation"])
        self.assertTrue(finalizer["retained_export_independent_replay"])
        self.assertTrue(finalizer["bounded_memory_native_finalization"])
        self.assertTrue(finalizer["bounded_memory_python_replay"])
        self.assertTrue(finalizer["sparse_refinement_commitments_bound"])
        self.assertTrue(finalizer["every_record_bound_to_measured_worker"])
        self.assertTrue(
            finalizer["source_height_count_linked_to_partial_block_slots"]
        )
        self.assertTrue(finalizer["canonical_record_adapter_implemented"])
        self.assertTrue(finalizer["adapter_rechecks_required_packet_signs"])
        self.assertTrue(
            finalizer["adapter_validates_stationary_replay_and_sparse_refinements"]
        )
        self.assertTrue(finalizer["adapter_validates_arb_turing_inputs"])
        self.assertTrue(
            finalizer["adapter_rebuilds_exact_rational_block_artifact"]
        )
        self.assertTrue(finalizer["adapter_streams_gap_free_shard_manifests"])
        self.assertTrue(
            finalizer[
                "adapter_streams_records_directly_to_native_shard_finalizer"
            ]
        )
        self.assertTrue(
            finalizer["adapter_terminal_manifest_authentication"]
        )
        self.assertFalse(
            finalizer["intermediate_native_record_spool_required"]
        )
        self.assertFalse(finalizer["measured_worker_emits_native_records"])
        self.assertNotIn(
            "compact_artifact_chain_finalizer.production_scale_native_implementation",
            current_readiness()["blocking_gates"],
        )
        self.assertIn(
            "compact_artifact_chain_finalizer.measured_worker_emits_native_records",
            current_readiness()["blocking_gates"],
        )

    def test_three_stream_touching_artifact_is_valid_but_not_lean_ready(self) -> None:
        result = validate_block_artifact(block_artifact())
        self.assertTrue(result["computation_artifact_valid"])
        self.assertTrue(result["three_event_streams_distinct"])
        self.assertTrue(result["touching_brackets_checked"])
        self.assertTrue(result["lean_wire_bridge_implemented"])
        self.assertFalse(result["lean_conversion_available"])

    def test_touching_brackets_must_share_the_same_endpoint_sign(self) -> None:
        value = block_artifact()
        value["streams"]["main"]["brackets"][1]["lower_sign"] = -1
        value["streams"]["main"]["brackets"][1]["upper_sign"] = 1
        with self.assertRaisesRegex(PlattH100CampaignError, "shared endpoint"):
            validate_block_artifact(value)

    def test_one_event_list_cannot_impersonate_three_streams(self) -> None:
        value = block_artifact()
        value["streams"].pop("right_flank")
        with self.assertRaisesRegex(PlattH100CampaignError, "three distinct"):
            validate_block_artifact(value)


if __name__ == "__main__":
    unittest.main()
