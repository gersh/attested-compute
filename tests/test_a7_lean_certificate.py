# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import base64
from dataclasses import replace
from fractions import Fraction
import hashlib
from pathlib import Path
import tempfile
import unittest

from tests.test_tg_analytic import a7_fixture, canonical, rational
from tg_verifier.a7_lean_certificate import (
    A7LeanCertificateError,
    ExactDyadic,
    certificate_from_transcript_bytes,
    certificate_from_transcript_file,
    render_lean_source,
)


def positive_base64url(value: int) -> str:
    width = max(1, (value.bit_length() + 7) // 8)
    return (
        base64.urlsafe_b64encode(value.to_bytes(width, "big"))
        .decode("ascii")
        .rstrip("=")
    )


def split_left_fixture() -> dict[str, object]:
    """A five-leaf KAT with equivalent but distinct dyadic encodings."""

    artifact = a7_fixture()
    leaves = artifact["leaves"]
    assert isinstance(leaves, list)
    leaves[0:1] = [
        [
            0,
            1,
            0,
            positive_base64url(3),
            -2,
            positive_base64url(5),
            -3,
        ],
        [
            0,
            1,
            1,
            positive_base64url(6),
            -3,
            positive_base64url(10),
            -4,
        ],
    ]
    summary = artifact["summary"]
    assert isinstance(summary, dict)
    summary.update(
        {
            "leaf_count": 5,
            "leaf_counts_by_edge": {
                "left": 2,
                "right": 1,
                "bottom": 1,
                "top": 1,
            },
            "work_count": 6,
            "max_depth": 1,
            "rejection_counts": {"bound_not_strict": 1},
            "min_zeta_abs_lower": rational(Fraction(5, 8)),
            "max_leaf": {
                "edge": "right",
                "depth": 0,
                "index": 0,
                "lo": rational(-4),
                "hi": rational(4),
            },
            "leaves_sha256": hashlib.sha256(canonical(leaves)[:-1]).hexdigest(),
        }
    )
    guards = artifact["guards"]
    assert isinstance(guards, dict)
    guards.update({"max_depth": 1, "max_work": 6})
    return artifact


class A7LeanCertificateTests(unittest.TestCase):
    def test_exact_seven_field_capture_preserves_raw_and_rational_values(self) -> None:
        raw = canonical(split_left_fixture())
        certificate = certificate_from_transcript_bytes(
            raw, require_retained_identity=False
        )
        self.assertEqual(certificate.transcript_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(certificate.transcript_size_bytes, len(raw))
        self.assertEqual(len(certificate.leaves), 5)
        self.assertEqual(certificate.max_depth, 1)

        first, second = certificate.leaves[:2]
        self.assertEqual((first.edge_id, first.depth, first.index), (0, 1, 0))
        self.assertEqual((second.edge_id, second.depth, second.index), (0, 1, 1))
        self.assertEqual(
            (
                first.norm_sq_upper.mantissa,
                first.norm_sq_upper.exponent,
                first.norm_sq_upper.value,
            ),
            (3, -2, Fraction(3, 4)),
        )
        self.assertEqual(
            (
                second.norm_sq_upper.mantissa,
                second.norm_sq_upper.exponent,
                second.norm_sq_upper.value,
            ),
            (6, -3, Fraction(3, 4)),
        )
        self.assertEqual(first.zeta_abs_lower.value, Fraction(5, 8))
        self.assertEqual(second.zeta_abs_lower.value, Fraction(5, 8))

    def test_render_is_deterministic_and_contains_every_exact_literal(self) -> None:
        certificate = certificate_from_transcript_bytes(
            canonical(split_left_fixture()), require_retained_identity=False
        )
        first = render_lean_source(certificate)
        second = render_lean_source(certificate)
        self.assertEqual(first, second)
        self.assertEqual(
            hashlib.sha256(first.encode("utf-8")).hexdigest(),
            "cde0c953aaafe980757543f61f21131942dabc7093e11228d27fb36f740ad11b",
        )
        self.assertIn(
            "import SparkInterval.TernaryGoldbach."
            "A7BoundaryCertificate",
            first,
        )
        self.assertEqual(first.count("    { edgeId :="), 5)
        self.assertIn(
            """\
    { edgeId := 0
      depth := 1
      index := 0
      normSqUpperMantissa := 3
      normSqUpperExponent := (-2)
      zetaAbsLowerMantissa := 5
      zetaAbsLowerExponent := (-3) }""",
            first,
        )
        self.assertIn(
            """\
    { edgeId := 0
      depth := 1
      index := 1
      normSqUpperMantissa := 6
      normSqUpperExponent := (-3)
      zetaAbsLowerMantissa := 10
      zetaAbsLowerExponent := (-4) }""",
            first,
        )
        self.assertIn("theorem certificate_check", first)
        self.assertIn("#print axioms certificate_check", first)
        self.assertNotIn("/home/", first)

    def test_safe_default_rejects_a_synthetic_fixture(self) -> None:
        with self.assertRaisesRegex(
            A7LeanCertificateError, "pinned retained"
        ):
            certificate_from_transcript_bytes(canonical(a7_fixture()))

    def test_file_entry_point_reads_a_tiny_snapshot(self) -> None:
        raw = canonical(split_left_fixture())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tiny-a7.json"
            path.write_bytes(raw)
            certificate = certificate_from_transcript_file(
                path, require_retained_identity=False
            )
        self.assertEqual(certificate.transcript_sha256, hashlib.sha256(raw).hexdigest())

    def test_configured_max_depth_may_strictly_exceed_deepest_leaf(self) -> None:
        artifact = a7_fixture()
        guards = artifact["guards"]
        assert isinstance(guards, dict)
        guards["max_depth"] = 24
        certificate = certificate_from_transcript_bytes(
            canonical(artifact), require_retained_identity=False
        )
        self.assertEqual(certificate.max_depth, 24)
        self.assertTrue(all(leaf.depth == 0 for leaf in certificate.leaves))
        self.assertIn(
            "maxDepth := 24",
            render_lean_source(certificate),
        )

    def test_noncanonical_and_wrong_width_transcripts_fail_closed(self) -> None:
        raw = canonical(a7_fixture())
        with self.assertRaisesRegex(A7LeanCertificateError, "canonical"):
            certificate_from_transcript_bytes(
                raw + b"\n", require_retained_identity=False
            )

        artifact = a7_fixture()
        leaves = artifact["leaves"]
        assert isinstance(leaves, list)
        assert isinstance(leaves[0], list)
        leaves[0].append(0)
        with self.assertRaisesRegex(A7LeanCertificateError, "seven fields"):
            certificate_from_transcript_bytes(
                canonical(artifact), require_retained_identity=False
            )

    def test_tampered_topology_or_encoding_fails_closed(self) -> None:
        artifact = split_left_fixture()
        leaves = artifact["leaves"]
        assert isinstance(leaves, list)
        assert isinstance(leaves[1], list)
        leaves[1][2] = 0
        summary = artifact["summary"]
        assert isinstance(summary, dict)
        summary["leaves_sha256"] = hashlib.sha256(canonical(leaves)[:-1]).hexdigest()
        with self.assertRaisesRegex(A7LeanCertificateError, "overlap"):
            certificate_from_transcript_bytes(
                canonical(artifact), require_retained_identity=False
            )

        artifact = a7_fixture()
        leaves = artifact["leaves"]
        assert isinstance(leaves, list)
        assert isinstance(leaves[0], list)
        leaves[0][3] = "AAE"
        summary = artifact["summary"]
        assert isinstance(summary, dict)
        summary["leaves_sha256"] = hashlib.sha256(canonical(leaves)[:-1]).hexdigest()
        with self.assertRaisesRegex(A7LeanCertificateError, "minimal positive"):
            certificate_from_transcript_bytes(
                canonical(artifact), require_retained_identity=False
            )

    def test_bool_and_summary_tampering_fail_closed(self) -> None:
        artifact = a7_fixture()
        leaves = artifact["leaves"]
        assert isinstance(leaves, list)
        assert isinstance(leaves[0], list)
        leaves[0][0] = False
        summary = artifact["summary"]
        assert isinstance(summary, dict)
        summary["leaves_sha256"] = hashlib.sha256(canonical(leaves)[:-1]).hexdigest()
        with self.assertRaisesRegex(A7LeanCertificateError, "must be an integer"):
            certificate_from_transcript_bytes(
                canonical(artifact), require_retained_identity=False
            )

        artifact = a7_fixture()
        summary = artifact["summary"]
        assert isinstance(summary, dict)
        summary["leaves_sha256"] = "00" * 32
        with self.assertRaisesRegex(A7LeanCertificateError, "does not match"):
            certificate_from_transcript_bytes(
                canonical(artifact), require_retained_identity=False
            )

    def test_replaced_python_record_cannot_bypass_renderer_checks(self) -> None:
        certificate = certificate_from_transcript_bytes(
            canonical(split_left_fixture()), require_retained_identity=False
        )
        leaf = certificate.leaves[0]
        bad_dyadic = replace(
            leaf.norm_sq_upper,
            value=Fraction(7, 8),
        )
        changed_leaf = replace(leaf, norm_sq_upper=bad_dyadic)
        changed = replace(
            certificate,
            leaves=(changed_leaf,) + certificate.leaves[1:],
        )
        with self.assertRaisesRegex(A7LeanCertificateError, "exact dyadic"):
            render_lean_source(changed)

        digest_changed_dyadic = ExactDyadic(
            encoded_mantissa=positive_base64url(7),
            mantissa=7,
            exponent=-3,
            value=Fraction(7, 8),
        )
        changed_leaf = replace(leaf, norm_sq_upper=digest_changed_dyadic)
        changed = replace(
            certificate,
            leaves=(changed_leaf,) + certificate.leaves[1:],
        )
        with self.assertRaisesRegex(A7LeanCertificateError, "leaves_sha256"):
            render_lean_source(changed)

    def test_namespace_injection_fails_closed(self) -> None:
        certificate = certificate_from_transcript_bytes(
            canonical(a7_fixture()), require_retained_identity=False
        )
        with self.assertRaisesRegex(A7LeanCertificateError, "namespace"):
            render_lean_source(certificate, namespace="Safe\n#eval attacker")


if __name__ == "__main__":
    unittest.main()
