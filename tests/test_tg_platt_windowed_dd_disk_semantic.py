#!/usr/bin/env python3
"""Static and optional CUDA checks for the two-limb Platt diagnostic."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "gpu/platform/h100/h100_tg_platt_windowed_dd_disk_semantic.cu"


class PlattWindowedDoubleDoubleDiskSemanticTest(unittest.TestCase):
    def test_source_is_fail_honest_about_claim_and_refinement(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("physical_trace_refinement_proved\\\":false", text)
        self.assertIn("not_a_zeta_certificate", text)
        self.assertIn("two_limb_triangle_lower_bound_fails_closed", text)
        self.assertIn("source_packet_radii_discarded_for_diagnostic", text)
        self.assertIn("required_sign_packet_exported", text)
        self.assertIn("zero_isolation_events_constructed\\\":false", text)

    def test_source_uses_error_free_primitives_and_all_transform_stages(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("dd_two_sum", text)
        self.assertIn("fma(a, b, -product)", text)
        self.assertIn("kDDFloor", text)
        for stage in (
            "dd_build_gamma_rows",
            "dd_postprocess_G",
            "dd_pointwise_products",
            "dd_normalize_and_taylor_sum",
            "dd_initialize_half_spectrum",
            "dd_hermidft_preprocess",
            "dd_extract_samples",
        ):
            self.assertIn(stage, text)
        # Five transforms in the standalone diagnostic and the same five in
        # the reusable persistent-workspace path, plus the definition.
        self.assertEqual(text.count("dd_transform("), 11)

    def test_power_of_two_index_rewrite_matches_division_model(self) -> None:
        # The production FFT lengths are powers of two.  Exhaustively compare
        # the shift/mask address calculation with the former division/modulo
        # formulas on small transforms, then cover every stage and all
        # boundary positions on both source transform lengths.
        for transform_log in range(3, 9):
            length = 1 << transform_log
            maximum_log = transform_log + 1
            for lines in (1, 3, 23):
                for stage_log in range(1, transform_log + 1):
                    stage_length = 1 << stage_log
                    half = stage_length // 2
                    root_stride = 1 << (maximum_log - stage_log)
                    for flat in range(lines * length // 2):
                        old_line = flat // (length // 2)
                        old_local = flat % (length // 2)
                        old_group = old_local // half
                        old_offset = old_local % half
                        new_line = flat >> (transform_log - 1)
                        new_local = flat & (length // 2 - 1)
                        new_group = new_local >> (stage_log - 1)
                        new_offset = new_local & (half - 1)
                        self.assertEqual(
                            (
                                new_line,
                                new_group,
                                new_offset,
                                new_offset * root_stride,
                            ),
                            (
                                old_line,
                                old_group,
                                old_offset,
                                old_offset
                                * ((1 << maximum_log) // stage_length),
                            ),
                        )
        for transform_log in (15, 16):
            length = 1 << transform_log
            for stage_log in range(1, transform_log + 1):
                half = 1 << (stage_log - 1)
                for flat in (
                    0,
                    1,
                    half - 1,
                    half,
                    length // 2 - 1,
                    22 * length // 2,
                    23 * length // 2 - 1,
                ):
                    self.assertEqual(
                        (
                            flat >> (transform_log - 1),
                            (flat & (length // 2 - 1))
                            >> (stage_log - 1),
                            (flat & (length // 2 - 1)) & (half - 1),
                        ),
                        (
                            flat // (length // 2),
                            (flat % (length // 2)) // half,
                            (flat % (length // 2)) % half,
                        ),
                    )

    def test_two_stage_kernel_matches_consecutive_radix2_indexing(self) -> None:
        # One paired thread must own exactly the four cells produced by two
        # ordinary stages and select the identical three root offsets.
        for transform_log in range(2, 9):
            length = 1 << transform_log
            maximum_log = transform_log + 1
            for lines in (1, 3, 23):
                for first_stage_log in range(1, transform_log):
                    first_half = 1 << (first_stage_log - 1)
                    second_half = 1 << first_stage_log
                    pair_length = 1 << (first_stage_log + 1)
                    first_stride = 1 << (maximum_log - first_stage_log)
                    second_stride = 1 << (
                        maximum_log - first_stage_log - 1
                    )
                    covered: set[int] = set()
                    for flat in range(lines * length // 4):
                        line = flat >> (transform_log - 2)
                        local = flat & (length // 4 - 1)
                        group = local >> (first_stage_log - 1)
                        offset = local & (first_half - 1)
                        base = (
                            line * length
                            + group * pair_length
                            + offset
                        )
                        indices = (
                            base,
                            base + first_half,
                            base + second_half,
                            base + second_half + first_half,
                        )
                        self.assertEqual(
                            (
                                offset * first_stride,
                                offset * second_stride,
                                (offset + first_half) * second_stride,
                            ),
                            (
                                # First-stage root is shared by the two
                                # adjacent first-stage groups.
                                offset
                                * ((1 << maximum_log)
                                   // (2 * first_half)),
                                offset
                                * ((1 << maximum_log)
                                   // pair_length),
                                (offset + first_half)
                                * ((1 << maximum_log)
                                   // pair_length),
                            ),
                        )
                        for index in indices:
                            self.assertNotIn(index, covered)
                            covered.add(index)
                    self.assertEqual(
                        covered,
                        set(range(lines * length)),
                    )

    def test_root_norm_cache_is_one_time_directed_state(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("dd_disk_mul_known_y_norm", text)
        self.assertIn("dd_initialize_root_center_norms", text)
        self.assertIn("root_center_norms[index] =", text)
        self.assertIn("CUDA_CHECK(cudaDeviceSynchronize())", text)

    def test_two_radix2_stages_share_one_global_round_trip(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("__global__ void dd_radix2_stage_pair", text)
        self.assertIn("__shared__ DDDisk stage_values[512]", text)
        self.assertIn("__syncthreads()", text)
        self.assertIn("paired_tile_values = 512U", text)
        self.assertIn(
            "not a different radix-4 rounding",
            text,
        )

    def test_fft_l1_bounds_replace_hot_path_square_roots(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("dd_l1_norm_upper", text)
        self.assertIn("dd_disk_add_l1", text)
        self.assertIn("dd_disk_sub_l1", text)
        self.assertIn("const double local_error = __dadd_ru(re.error, im.error);", text)
        self.assertIn(
            "const double nx = dd_l1_norm_upper(x.real, x.imaginary);",
            text,
        )
        for x, y in (
            (0.0, 0.0),
            (1.0, -2.0),
            (-1.0e-300, 1.0e-300),
            (1.0e150, -1.0e150),
        ):
            self.assertLessEqual(math.hypot(x, y), abs(x) + abs(y))

    def test_required_region_packet_fails_closed(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("write_required_sign_packet", text)
        self.assertIn("required-sign packet refuses an ambiguous sample", text)
        self.assertIn("source_region_sign_ambiguous != 0U", text)
        self.assertIn("loaded_packet106.complete_terms", text)
        self.assertIn("source_packet_radii_for_diagnostic", text)

    def test_runtime_small_kat_when_binary_is_supplied(self) -> None:
        binary = os.environ.get("TG_PLATT_DD_DISK_BINARY")
        if not binary:
            self.skipTest("set TG_PLATT_DD_DISK_BINARY to exercise the CUDA KAT")
        completed = subprocess.run(
            [binary, "--length=8", "--stages=3", "--no-source-errors"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual(
            result["schema"],
            "sparkinterval.tg.platt-windowed-dd-disk-semantic.v1",
        )
        self.assertTrue(result["all_output_disks_finite"])
        self.assertTrue(result["small_long_double_kat_contained"])
        self.assertEqual(result["sign_ambiguous_samples"], 0)
        self.assertEqual(result["output_fnv1a64"], "072fe1068a2d8367")
        self.assertFalse(result["physical_trace_refinement_proved"])


if __name__ == "__main__":
    unittest.main()
