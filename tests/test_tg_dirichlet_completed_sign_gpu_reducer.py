# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import unittest

from tg_verifier.dirichlet_completed_sign_gpu_reducer import (
    DirichletCompletedSignReducerError,
    _canonical_json,
    capability,
    dense_pack_model,
    factor_checkpoint_model,
    source_dense_pack_projection,
    source_memory_model,
    validate_qualification_result,
)


class DirichletCompletedSignGpuReducerTest(unittest.TestCase):
    def test_resident_memory_model_has_no_status_or_raw_stream(self) -> None:
        model = source_memory_model(
            frame_characters=400_000,
            frame_samples=64,
            ambiguity_ranges=1_000,
        )
        self.assertEqual(model["already_resident_fft_bytes"], 819_200_000)
        self.assertEqual(model["per_value_status_bytes"], 0)
        self.assertEqual(model["dense_phase_state_bytes"], 35_200_000)
        self.assertEqual(model["sparse_range_bytes"], 16_000)
        self.assertEqual(
            model["sparse_range_primitive_ordinal_bytes"], 8_000
        )
        self.assertEqual(
            model["source_raw_transform_bytes_avoided"],
            8_534_327_608_475_136,
        )
        self.assertEqual(
            model["source_raw_two_bit_code_bytes_avoided"],
            66_674_434_441_212,
        )
        self.assertFalse(model["raw_completed_l_stream_materialized"])
        self.assertFalse(model["source_admission"])

    def test_dense_pack_model_matches_exhaustive_cuda_fixture(self) -> None:
        model = dense_pack_model(
            character_count=6561,
            sample_count=8,
        )
        self.assertEqual(model["transition_count_width_bits"], 3)
        self.assertEqual(model["record_width_bits"], 7)
        self.assertEqual(model["page_count"], 2)
        self.assertEqual(model["page_stride_bytes"], 3584)
        self.assertEqual(model["device_staging_bytes"], 7168)
        self.assertEqual(model["canonical_dense_bytes"], 5741)
        self.assertEqual(model["internal_phase_state_bytes"], 577368)
        self.assertFalse(model["phase_states_cross_device_boundary"])
        self.assertFalse(model["source_admission"])

    def test_source_dense_projection_keeps_internal_states_on_gpu(
        self,
    ) -> None:
        model = source_dense_pack_projection()
        self.assertEqual(
            model["internal_phase_state_bytes_not_transported"],
            2_600_175_312_152,
        )
        self.assertEqual(
            model["exact_dense_byte_floor_without_q_or_page_padding"],
            62_259_950_420,
        )
        self.assertEqual(
            model["exact_canonical_wire_bytes_without_ambiguity_ranges"],
            62_968_524_843,
        )
        self.assertGreater(model["internal_to_dense_floor_ratio"], 41.7)
        self.assertFalse(model["source_execution"])
        self.assertFalse(model["source_admission"])

    def test_factor_checkpoint_projection_is_explicitly_unqualified(
        self,
    ) -> None:
        model = factor_checkpoint_model(
            t_rows=127_988,
            checkpoint_span=4096,
        )
        self.assertEqual(model["gamma_scaled_disk_bytes"], 6_143_424)
        self.assertEqual(
            model["conductor_checkpoint_count"],
            9_360_000,
        )
        self.assertEqual(
            model["conductor_checkpoint_disk_bytes"],
            224_640_000,
        )
        self.assertEqual(model["conductor_step_t_numerator"], 5)
        self.assertEqual(model["conductor_step_t_denominator"], 128)
        self.assertEqual(
            model["conductor_step_applications_per_sample"], 1
        )
        self.assertTrue(
            model["bounded_q5_initial_and_terminal_4096_step_replay"]
        )
        self.assertFalse(
            model["checkpoint_enclosure_usefulness_measured"]
        )
        self.assertFalse(model["source_ready"])

    def test_capability_does_not_promote_the_trust_boundary(self) -> None:
        value = capability()
        self.assertTrue(value["in_process_resident_device_pointer_api"])
        self.assertTrue(value["scheduled_allchars_writeall_bypass_required"])
        self.assertTrue(value["completed_imaginary_must_contain_zero"])
        self.assertTrue(value["exact_tgdcsb03_dense_device_pack"])
        self.assertFalse(value["phase_states_cross_device_boundary"])
        self.assertFalse(value["raw_transform_stream_materialized"])
        self.assertFalse(value["raw_sign_stream_production_path"])
        self.assertFalse(value["factor_checkpoint_source_qualification_complete"])
        self.assertFalse(value["allchars_device_integration_complete"])
        self.assertFalse(value["source_scale_run_completed"])
        self.assertFalse(value["external_atom_discharged"])

    def test_qualification_validator_rejects_false_determinate(self) -> None:
        body = {
            "schema": (
                "sparkinterval.tg.dirichlet_completed_sign_gpu_reducer."
                "arb_differential.v1"
            ),
            "false_determinate": 0,
            "opposite_determinate": 0,
            "conductor_step_t_numerator": 5,
            "conductor_step_t_denominator": 128,
            "conductor_step_applications_per_sample": 1,
            "raw_codes_production_path": False,
            "source_scale_run_completed": False,
            "compiler_refinement_proved": False,
            "trusted_execution_attested": False,
            "zero_completeness_claimed": False,
            "external_atom_discharged": False,
        }
        valid = dict(body)
        valid["qualification_sha256"] = hashlib.sha256(
            _canonical_json(body)
        ).hexdigest()
        validate_qualification_result(valid)
        attacked = copy.deepcopy(valid)
        attacked["false_determinate"] = 1
        attacked_body = dict(attacked)
        attacked_body.pop("qualification_sha256")
        attacked["qualification_sha256"] = hashlib.sha256(
            _canonical_json(attacked_body)
        ).hexdigest()
        with self.assertRaises(DirichletCompletedSignReducerError):
            validate_qualification_result(attacked)
        attacked = copy.deepcopy(valid)
        attacked["conductor_step_applications_per_sample"] = 2
        attacked_body = dict(attacked)
        attacked_body.pop("qualification_sha256")
        attacked["qualification_sha256"] = hashlib.sha256(
            _canonical_json(attacked_body)
        ).hexdigest()
        with self.assertRaises(DirichletCompletedSignReducerError):
            validate_qualification_result(attacked)


if __name__ == "__main__":
    unittest.main()
