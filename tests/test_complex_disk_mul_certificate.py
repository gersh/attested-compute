#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact producer/checker tests for Lean complex-disk witnesses."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from reference import exact_binary64 as binary64
from tg_verifier.complex_disk_mul_certificate import (
    ComplexDiskCertificateError,
    RawComplexDisk,
    check_raw_mul_certificate,
    generate_raw_mul_certificate,
    minimal_binary64_sqrt_upper_bound_bits,
    render_lean_literal,
    render_lean_source,
    verify_minimal_auxiliary_bounds,
    verify_raw_mul_certificate,
)


ROOT = Path(__file__).resolve().parents[1]


def sample_disks() -> tuple[RawComplexDisk, RawComplexDisk, RawComplexDisk]:
    """Return a nonzero-error variant of the hand-auditable Lean sample."""

    return (
        RawComplexDisk(
            0x3FF0000000000000,  # 1
            0x4000000000000000,  # 2
            0x3FC0000000000000,  # 1/8
        ),
        RawComplexDisk(
            0x4008000000000000,  # 3
            0x4010000000000000,  # 4
            0x3FD0000000000000,  # 1/4
        ),
        RawComplexDisk(
            0xC014000000000001,  # next binary64 below -5
            0x4024000000000000,  # 10
            0x3FF6800000000000,  # 45/32
        ),
    )


class ExactBoundTests(unittest.TestCase):
    def test_minimal_sqrt_upper_bound_uses_exact_fraction_comparisons(self) -> None:
        bound = minimal_binary64_sqrt_upper_bound_bits(Fraction(5))
        self.assertEqual(bound, 0x4001E3779B97F4A8)
        value = binary64.decode_finite(bound)
        previous = binary64.decode_finite(bound - 1)
        self.assertGreaterEqual(value * value, 5)
        self.assertLess(previous * previous, 5)

        self.assertEqual(minimal_binary64_sqrt_upper_bound_bits(0), 0)
        maximum_sq = binary64.MAX_FINITE_VALUE * binary64.MAX_FINITE_VALUE
        self.assertEqual(
            minimal_binary64_sqrt_upper_bound_bits(maximum_sq),
            binary64.MAX_FINITE,
        )

    def test_invalid_or_unrepresentable_targets_fail_closed(self) -> None:
        maximum_sq = binary64.MAX_FINITE_VALUE * binary64.MAX_FINITE_VALUE
        for target in (-1, maximum_sq + 1):
            with self.subTest(target=target), self.assertRaises(
                ComplexDiskCertificateError
            ):
                minimal_binary64_sqrt_upper_bound_bits(target)
        for target in (True, 1.0, "1"):
            with self.subTest(target=target), self.assertRaises(
                ComplexDiskCertificateError
            ):
                minimal_binary64_sqrt_upper_bound_bits(target)  # type: ignore[arg-type]


class CertificateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.left, self.right, self.output = sample_disks()
        self.certificate = generate_raw_mul_certificate(
            self.left, self.right, self.output
        )

    def test_generator_is_minimal_and_all_lean_inequalities_hold(self) -> None:
        self.assertEqual(
            self.certificate.center_error_bound_bits, 0x3CD0000000000000
        )
        self.assertEqual(
            self.certificate.left_center_norm_bound_bits,
            0x4001E3779B97F4A8,
        )
        self.assertEqual(
            self.certificate.right_center_norm_bound_bits,
            0x4014000000000000,
        )
        decoded = verify_raw_mul_certificate(self.certificate)
        self.assertTrue(check_raw_mul_certificate(self.certificate))
        verify_minimal_auxiliary_bounds(self.certificate)

        self.assertEqual(
            decoded.product_center_error_sq,
            Fraction(1, 1 << 100),
        )
        self.assertLessEqual(
            decoded.product_center_error_sq,
            decoded.center_error_bound * decoded.center_error_bound,
        )
        self.assertLessEqual(
            decoded.left.center_norm_sq,
            decoded.left_center_norm_bound * decoded.left_center_norm_bound,
        )
        self.assertLessEqual(
            decoded.right.center_norm_sq,
            decoded.right_center_norm_bound * decoded.right_center_norm_bound,
        )
        self.assertLessEqual(
            decoded.required_output_radius, decoded.output.radius
        )

        # Minimality is a producer invariant, while Lean intentionally accepts
        # any safe bound.  Keep those two contracts visibly distinct.
        safe_but_loose = replace(
            self.certificate,
            left_center_norm_bound_bits=(
                self.certificate.left_center_norm_bound_bits + 1
            ),
        )
        self.assertTrue(check_raw_mul_certificate(safe_but_loose))
        with self.assertRaisesRegex(ComplexDiskCertificateError, "not minimal"):
            verify_minimal_auxiliary_bounds(safe_but_loose)

    def test_tampering_each_decisive_field_fails_closed(self) -> None:
        too_small_bounds = (
            replace(
                self.certificate,
                center_error_bound_bits=(
                    self.certificate.center_error_bound_bits - 1
                ),
            ),
            replace(
                self.certificate,
                left_center_norm_bound_bits=(
                    self.certificate.left_center_norm_bound_bits - 1
                ),
            ),
            replace(
                self.certificate,
                right_center_norm_bound_bits=(
                    self.certificate.right_center_norm_bound_bits - 1
                ),
            ),
        )
        for tampered in too_small_bounds:
            with self.subTest(tampered=tampered):
                self.assertFalse(check_raw_mul_certificate(tampered))

        mutations = (
            replace(
                self.certificate,
                output=replace(self.certificate.output, radius_bits=0),
            ),
            replace(
                self.certificate,
                left=replace(
                    self.certificate.left,
                    radius_bits=self.certificate.left.radius_bits
                    | binary64.SIGN_MASK,
                ),
            ),
            replace(
                self.certificate,
                output=replace(
                    self.certificate.output,
                    re_bits=binary64.POSITIVE_INFINITY,
                ),
            ),
            replace(
                self.certificate,
                center_error_bound_bits=binary64.POSITIVE_INFINITY,
            ),
            replace(self.certificate, center_error_bound_bits=-1),
            replace(
                self.certificate,
                center_error_bound_bits=binary64.WORD_LIMIT,
            ),
            replace(self.certificate, center_error_bound_bits=True),
        )
        for tampered in mutations:
            with self.subTest(tampered=tampered):
                self.assertFalse(check_raw_mul_certificate(tampered))
        self.assertFalse(check_raw_mul_certificate(object()))

    def test_generator_rejects_an_output_disk_too_narrow_for_the_formula(self) -> None:
        too_narrow = replace(self.output, radius_bits=0)
        with self.assertRaisesRegex(
            ComplexDiskCertificateError, "exceeds output.radius"
        ):
            generate_raw_mul_certificate(self.left, self.right, too_narrow)

    def test_lean_rendering_is_deterministic_and_validates_before_rendering(
        self,
    ) -> None:
        first = render_lean_literal(
            self.certificate, declaration="sampleCertificate"
        )
        second = render_lean_literal(
            self.certificate, declaration="sampleCertificate"
        )
        self.assertEqual(first, second)
        self.assertIn("0xc014000000000001", first)
        self.assertIn("centerErrorBoundBits := 0x3cd0000000000000", first)

        source = render_lean_source(
            self.certificate, declaration="sampleCertificate"
        )
        self.assertNotIn("native_decide", source)
        self.assertIn("norm_num", source)
        self.assertIn("RawMulCertificate.check_sound", source)
        self.assertIn("#print axioms sampleCertificate_validated", source)
        self.assertIn("theorem sampleCertificate_output_contains_mul", source)
        self.assertIn(
            "#print axioms sampleCertificate_output_contains_mul", source
        )

        with self.assertRaisesRegex(ComplexDiskCertificateError, "identifier"):
            render_lean_literal(self.certificate, declaration="bad; #check False")
        with self.assertRaises(ComplexDiskCertificateError):
            render_lean_literal(
                replace(
                    self.certificate,
                    center_error_bound_bits=(
                        self.certificate.center_error_bound_bits - 1
                    ),
                )
            )

    @unittest.skipUnless(shutil.which("lake"), "lake is not installed")
    def test_rendered_witness_compiles_with_ordinary_lean(self) -> None:
        source = render_lean_source(
            self.certificate, declaration="sampleCertificate"
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GeneratedComplexDiskCertificate.lean"
            path.write_text(source, encoding="utf-8")
            completed = subprocess.run(
                ["lake", "env", "lean", str(path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("sorryAx", completed.stdout)
        self.assertIn(
            "depends on axioms: [propext,", completed.stdout
        )


if __name__ == "__main__":
    unittest.main()
