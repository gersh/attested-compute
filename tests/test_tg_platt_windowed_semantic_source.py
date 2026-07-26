# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "gpu/platform/h100/h100_tg_platt_windowed_semantic.cu"
KAT = ROOT / "tests/tg_platt_windowed_semantic_known_answers.py"
DOC = ROOT / "docs/algorithms/PLATT_WINDOWED_SEMANTIC_TRANSFORMS.md"


class PlattWindowedSemanticSourceTest(unittest.TestCase):
    def test_source_pins_upstream_and_refuses_atom_level_claim(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("42b21426718e542daa2b006dc05ea2d7f26426e6", source)
        self.assertIn(
            "source_semantic_transform_from_certified_input_boxes_not_a_zeta_certificate",
            source,
        )
        self.assertIn('<< ",\\\"actual_zeta_inputs\\\":false"', source)
        self.assertNotIn("external_atom_discharged\\\":true", source)

    def test_all_four_transform_signs_and_hermidft_are_explicit(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        for required in (
            "build_gamma_rows",
            "postprocess_G",
            "pointwise_products",
            "normalize_and_taylor_sum",
            "initialize_half_spectrum",
            "hermidft_preprocess",
            "interleave_hermidft_output",
        ):
            self.assertIn(required, source)
        self.assertEqual(source.count("transform(d_G_positive, d_G_negative"), 1)
        self.assertEqual(source.count("transform(d_G_negative, d_G_positive"), 1)
        self.assertEqual(source.count("transform(d_skn, d_S_positive"), 1)
        self.assertEqual(source.count("transform(d_products, d_convolutions"), 1)
        self.assertEqual(source.count("transform(d_hermi_pre, d_hermi_fft"), 1)

    def test_source_geometry_operation_counts(self) -> None:
        n1 = 32_768
        k = 23
        batched = 4 * k * (n1 // 2) * 15
        final = (2 * n1 // 2) * 16
        self.assertEqual(batched, 22_609_920)
        self.assertEqual(final, 524_288)
        self.assertEqual(batched + final, 23_134_208)
        self.assertEqual(k * n1, 753_664)

    def test_published_error_disks_and_dyadic_root_path_are_literal(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        for literal in (
            "1.83e-44",
            "1.0e-307",
            "3.26e-33",
            "6.73e-33",
            "3.93e-245",
            "mpfr_sinpi",
            "mpfr_cospi",
            "21.0 / 128.0",
        ):
            self.assertIn(literal, source)
        self.assertNotIn("__ddiv_", source)

    def test_auditor_and_document_are_present(self) -> None:
        self.assertTrue(KAT.is_file())
        document = DOC.read_text(encoding="utf-8")
        self.assertIn("Binary64 usefulness result", document)
        self.assertIn("not an actual zeta window", document)


if __name__ == "__main__":
    unittest.main()
