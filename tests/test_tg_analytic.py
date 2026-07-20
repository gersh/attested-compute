# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import base64
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tg_verifier import analytic
from tg_verifier import a7_flint


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def rational(value: int | Fraction) -> dict[str, str]:
    fraction = Fraction(value)
    return {
        "numerator": str(fraction.numerator),
        "denominator": str(fraction.denominator),
    }


def positive_base64url(value: int) -> str:
    width = max(1, (value.bit_length() + 7) // 8)
    return base64.urlsafe_b64encode(value.to_bytes(width, "big")).decode().rstrip("=")


def a7_fixture() -> dict[str, object]:
    leaves = [
        [edge_id, 0, 0, positive_base64url(1), 0, positive_base64url(1), 0]
        for edge_id in range(4)
    ]
    return {
        "schema": "ch25-a7-boundary-v1",
        "author": "Gershon Bialer",
        "claim": {
            "function": "-zeta'(s)/zeta(s)-1/(s-1)+1/(s+2)",
            "rectangle": {
                "real": ["-3", "5"],
                "imag": ["-4", "4"],
                "locus": "all four closed edges",
            },
            "norm_bound": rational(Fraction(349, 250)),
            "norm_sq_bound": rational(Fraction(121_801, 62_500)),
        },
        "arithmetic": {
            "python_flint_version": "0.9.0",
            "flint_version": "3.6.0",
            "flint_release": 30600,
            "precision_bits": 192,
            "series_length": 2,
            "series_cap": 4,
            "threads": 1,
            "subdivision": "exact dyadic midpoint",
            "acceptance": "exact upper(normSq(G(box))) < (349/250)^2",
        },
        "guards": {"max_depth": 0, "max_work": 4},
        "edges": [
            {
                "name": "left",
                "varying_coordinate": "imag",
                "start": rational(-4),
                "end": rational(4),
                "fixed_coordinate": rational(-3),
            },
            {
                "name": "right",
                "varying_coordinate": "imag",
                "start": rational(-4),
                "end": rational(4),
                "fixed_coordinate": rational(5),
            },
            {
                "name": "bottom",
                "varying_coordinate": "real",
                "start": rational(-3),
                "end": rational(5),
                "fixed_coordinate": rational(-4),
            },
            {
                "name": "top",
                "varying_coordinate": "real",
                "start": rational(-3),
                "end": rational(5),
                "fixed_coordinate": rational(4),
            },
        ],
        "leaf_encoding": {
            "fields": [
                "edge_id",
                "depth",
                "index",
                "norm_sq_upper_mantissa_base64url",
                "norm_sq_upper_exponent",
                "zeta_abs_lower_mantissa_base64url",
                "zeta_abs_lower_exponent",
            ],
            "value_rule": "mantissa * 2^exponent",
            "mantissa_encoding": (
                "unsigned big-endian, unpadded RFC 4648 base64url"
            ),
            "edge_id_rule": "zero-based index into edges",
            "interval_rule": (
                "[start + index*(end-start)/2^depth, "
                "start + (index+1)*(end-start)/2^depth]"
            ),
        },
        "leaves": leaves,
        "summary": {
            "leaf_count": 4,
            "leaf_counts_by_edge": {
                "left": 1,
                "right": 1,
                "bottom": 1,
                "top": 1,
            },
            "work_count": 4,
            "max_depth": 0,
            "rejection_counts": {},
            "max_norm_sq_upper": rational(1),
            "margin_norm_sq": rational(Fraction(59_301, 62_500)),
            "min_zeta_abs_lower": rational(1),
            "max_leaf": {
                "edge": "left",
                "depth": 0,
                "index": 0,
                "lo": rational(-4),
                "hi": rational(4),
            },
            "max_norm_upper_decimal_outward": "1." + "0" * 45,
            "margin_norm_lower_decimal_outward": "0.396" + "0" * 42,
            "leaves_sha256": hashlib.sha256(canonical(leaves)[:-1]).hexdigest(),
        },
    }


class A7FlintDependencyTests(unittest.TestCase):
    def test_missing_flint_dependency_fails_with_pinned_requirement(self) -> None:
        with mock.patch.object(
            a7_flint.importlib, "import_module", side_effect=ImportError("missing")
        ):
            with self.assertRaisesRegex(
                a7_flint.A7FlintReplayError, "python-flint==0.9.0"
            ):
                a7_flint._load_flint()

    def test_replay_binds_structure_and_flint_to_one_file_read(self) -> None:
        raw = canonical(a7_fixture())
        file_handle = mock.mock_open(read_data=raw)
        with mock.patch.object(Path, "open", file_handle):
            with mock.patch.object(
                a7_flint,
                "_load_flint",
                side_effect=a7_flint.A7FlintReplayError("stop before FLINT"),
            ):
                with self.assertRaisesRegex(
                    a7_flint.A7FlintReplayError, "stop before FLINT"
                ):
                    a7_flint.replay_a7_flint(
                        Path("replaceable-a7.json"),
                        require_retained_identity=False,
                    )
        file_handle.assert_called_once_with("rb")


PROP77_COMPLETENESS = (
    "N(20000) is exactly 22491 counting all nontrivial zeros with "
    "multiplicity. The first 22491 returned critical-line zero balls are "
    "positive, pairwise disjoint, and lie below the cutoff, so they account "
    "for at least 22491 multiplicity units. Equality forces each ball to "
    "contain multiplicity exactly one and leaves no additional on-line or "
    "off-line zero below the cutoff. The 22492nd ball lies strictly above "
    "the cutoff."
)

PROP77_TRUST_BOUNDARY = (
    "This deterministic artifact is independently recomputed by FLINT/Arb "
    "outside Lean. It depends on the reviewed FLINT implementation and the "
    "host toolchain; it is not an ordinary-kernel Lean proof."
)


def interval(
    lower: Fraction | int,
    upper: Fraction | int,
    *,
    lower_decimal: str,
    upper_decimal: str,
) -> dict[str, object]:
    return {
        "lower": rational(lower),
        "upper": rational(upper),
        "lower_decimal_outward": lower_decimal,
        "upper_decimal_outward": upper_decimal,
    }


def prop77_fixture() -> dict[str, object]:
    reciprocal_lower = Fraction(
        51_098_783_911_951_127_688_836_996_529,
        9_903_520_314_283_042_199_192_993_792,
    )
    reciprocal_upper = Fraction(
        51_098_783_911_951_127_688_837_033_741,
        9_903_520_314_283_042_199_192_993_792,
    )
    reciprocal_target = Fraction(257_983, 50_000)  # 5.15966
    margin = reciprocal_target - reciprocal_upper
    last_lower = Fraction(
        24_177_640_671_911_141_806_505_384_581,
        1_208_925_819_614_629_174_706_176,
    )
    last_upper = Fraction(
        24_177_640_671_911_141_806_505_384_583,
        1_208_925_819_614_629_174_706_176,
    )
    first_lower = Fraction(
        48_357_342_669_352_285_050_954_892_913,
        2_417_851_639_229_258_349_412_352,
    )
    first_upper = Fraction(
        48_357_342_669_352_285_050_954_892_917,
        2_417_851_639_229_258_349_412_352,
    )
    last = interval(
        last_lower,
        last_upper,
        lower_decimal="19999.27562107845389378733172219040043103501121113385607",
        upper_decimal="19999.27562107845389378733172384476165614106656087667347",
    )
    first = interval(
        first_lower,
        first_upper,
        lower_decimal="20000.12816533574278571958675998181977503346130192740659",
        upper_decimal="20000.12816533574278571958676163618100013951665167022398",
    )
    return {
        "author": "Gershon Bialer",
        "claim": {
            "height_cutoff": "20000",
            "multiplicity_count": 22_491,
            "proved": True,
            "reciprocal_sum": "sum_{0 < gamma <= 20000} 1/gamma",
            "strict_upper_bound": "5.15966",
        },
        "completeness_and_multiplicity_argument": PROP77_COMPLETENESS,
        "configuration": {
            "precision_bits": 96,
            "requested_zero_indices": [1, 22_492],
            "threads": 1,
        },
        "isolation": {
            "all_consecutive_ordinate_balls_disjoint": True,
            "all_ordinates_positive": True,
            "all_real_parts_exact": True,
            "critical_line_real_part": rational(Fraction(1, 2)),
            "first_excluded": {
                "certifies": "20000 < lower",
                "index": 22_492,
                "lower_reused": rational(first_lower),
                "ordinate": first,
                "upper_reused": rational(first_upper),
            },
            "last_included": {
                "certifies": "upper <= 20000",
                "index": 22_491,
                "lower_reused": rational(last_lower),
                "ordinate": last,
                "upper_reused": rational(last_upper),
            },
            "minimum_consecutive_gap": rational(
                Fraction(
                    85_367_864_744_089_810_742_239,
                    2_417_851_639_229_258_349_412_352,
                )
            ),
            "minimum_gap_after_index": 18_859,
            "ordinate_intervals_sha256": (
                "9a3b89e580d50514690488dcea35ba6b24ff4180eb72378bba52216b0e1143ff"
            ),
            "reciprocal_sum": {
                "arb_lower": rational(reciprocal_lower),
                "arb_upper": rational(reciprocal_upper),
                "certified_margin_lower": rational(margin),
                "certified_margin_lower_decimal_outward": (
                    "0.000001384643245901937836848064140367392318910306158417922173"
                ),
                "lower_decimal_outward": (
                    "5.159658615356754098062159394484082981818394308094690055288555"
                ),
                "proved_strict_upper_bound": True,
                "strict_target": rational(reciprocal_target),
                "strict_target_decimal": "5.15966",
                "terms": 22_491,
                "upper_decimal_outward": (
                    "5.159658615356754098062163151935859632607681089693841582077827"
                ),
            },
            "requested_indices": [1, 22_492],
            "returned_records": 22_492,
        },
        "provenance": {
            "ch25_proposition": "https://arxiv.org/abs/2512.15709v1",
            "flint_3_6_source": (
                "https://github.com/flintlib/flint/tree/v3.6.0/src/acb_dirichlet"
            ),
            "flint_documentation": (
                "https://flintlib.org/doc/acb_dirichlet.html#riemann-zeta-function-zeros"
            ),
            "flint_requirement": "FLINT==3.6.0",
            "python_flint_requirement": "python-flint==0.9.0",
        },
        "schema": "ch25-prop77-flint-head-v1",
        "trust_boundary": PROP77_TRUST_BOUNDARY,
        "versions": {
            "flint": "3.6.0",
            "flint_release": 30600,
            "python_flint": "0.9.0",
        },
        "zero_count": {
            "arb_result_exact": True,
            "count": 22_491,
            "counting_convention": (
                "nontrivial zeta zeros with 0 < Im(rho) <= 20000, counted "
                "according to multiplicity"
            ),
            "height": "20000",
        },
    }


class A7BoundaryArtifactTests(unittest.TestCase):
    def test_small_exact_cover_is_accepted_with_narrow_scope(self) -> None:
        receipt = analytic.verify_a7_boundary_bytes(canonical(a7_fixture()))
        self.assertTrue(receipt["accepted"])
        self.assertEqual(receipt["leaf_count"], 4)
        self.assertTrue(receipt["four_edge_dyadic_cover_verified"])
        self.assertTrue(receipt["leaf_digest_contents_verified"])
        self.assertTrue(receipt["stored_norm_square_inequalities_verified"])
        self.assertFalse(receipt["flint_box_evaluations_recomputed"])
        self.assertFalse(receipt["zeta_enclosures_verified"])
        self.assertFalse(receipt["zeta_derivative_enclosures_verified"])
        self.assertFalse(receipt["analytic_claim_proved"])
        self.assertTrue(receipt["external_semantics_required"])

    def test_file_entry_point_checks_the_same_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a7.json"
            path.write_bytes(canonical(a7_fixture()))
            receipt = analytic.verify_a7_boundary_file(path)
        self.assertEqual(receipt["artifact_kind"], "ch25_a7_boundary")
        self.assertFalse(receipt["artifact_bytes_match_pinned_sha256"])

    def test_retained_identity_mode_rejects_a_valid_synthetic_cover(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a7.json"
            path.write_bytes(canonical(a7_fixture()))
            with self.assertRaisesRegex(
                analytic.AnalyticArtifactError, "pinned retained"
            ):
                analytic.verify_a7_boundary_file(
                    path, require_retained_identity=True
                )

    def test_noncanonical_or_duplicate_json_is_rejected(self) -> None:
        pretty = json.dumps(a7_fixture(), indent=2).encode("ascii") + b"\n"
        with self.assertRaisesRegex(analytic.AnalyticArtifactError, "canonical"):
            analytic.verify_a7_boundary_bytes(pretty)
        with self.assertRaisesRegex(analytic.AnalyticArtifactError, "duplicate"):
            analytic.verify_a7_boundary_bytes(b'{"schema":1,"schema":2}\n')

    def test_file_reader_rejects_growth_past_the_byte_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.json"
            path.write_bytes(b"x" * 17)
            with mock.patch.object(analytic, "_MAX_JSON_BYTES", 16):
                with self.assertRaisesRegex(
                    analytic.AnalyticArtifactError, "16-byte local limit"
                ):
                    analytic.verify_a7_boundary_file(path)

    def test_gap_is_rejected_even_when_digest_is_recomputed(self) -> None:
        artifact = a7_fixture()
        artifact["guards"]["max_depth"] = 1  # type: ignore[index]
        artifact["leaves"][1][1:3] = [1, 0]  # type: ignore[index]
        artifact["summary"]["max_depth"] = 1  # type: ignore[index]
        artifact["summary"]["leaves_sha256"] = hashlib.sha256(  # type: ignore[index]
            canonical(artifact["leaves"])[:-1]
        ).hexdigest()
        with self.assertRaisesRegex(analytic.AnalyticArtifactError, "complete endpoint range"):
            analytic.verify_a7_boundary_bytes(canonical(artifact))

    def test_leaf_digest_tampering_is_rejected(self) -> None:
        artifact = a7_fixture()
        artifact["summary"]["leaves_sha256"] = "00" * 32  # type: ignore[index]
        with self.assertRaisesRegex(analytic.AnalyticArtifactError, "does not match"):
            analytic.verify_a7_boundary_bytes(canonical(artifact))

    def test_non_strict_norm_square_leaf_is_rejected(self) -> None:
        artifact = a7_fixture()
        artifact["leaves"][0][3] = positive_base64url(3)  # type: ignore[index]
        with self.assertRaisesRegex(analytic.AnalyticArtifactError, "norm_sq_upper"):
            analytic.verify_a7_boundary_bytes(canonical(artifact))

    def test_edge_metadata_tampering_is_rejected(self) -> None:
        artifact = a7_fixture()
        artifact["edges"][0]["fixed_coordinate"] = rational(-2)  # type: ignore[index]
        with self.assertRaisesRegex(analytic.AnalyticArtifactError, "canonical left edge"):
            analytic.verify_a7_boundary_bytes(canonical(artifact))


class Prop77FlintSummaryTests(unittest.TestCase):
    def test_pinned_retained_summary_is_accepted_with_narrow_scope(self) -> None:
        receipt = analytic.verify_prop77_flint_bytes(canonical(prop77_fixture()))
        self.assertTrue(receipt["accepted"])
        self.assertEqual(
            receipt["accepted_as"],
            "pinned retained summary only; not an analytic certificate",
        )
        self.assertEqual(receipt["stored_claim_multiplicity_count"], 22_491)
        self.assertEqual(
            receipt["artifact_sha256"],
            "60bbfe8268722320a45e264c17f9b4132cccbf135f63b5b9a8d4fc8ae2ec952a",
        )
        self.assertTrue(receipt["artifact_bytes_match_pinned_sha256"])
        self.assertTrue(receipt["stored_configuration_matches_pinned_value"])
        self.assertTrue(receipt["ordinate_digest_matches_pinned_value"])
        self.assertTrue(receipt["stored_count_fields_internally_consistent"])
        self.assertTrue(
            receipt["stored_cutoff_endpoint_fractions_internally_consistent"]
        )
        self.assertTrue(
            receipt["stored_reciprocal_endpoints_arithmetically_below_target"]
        )
        self.assertFalse(receipt["ordinate_digest_preimage_verified"])
        self.assertFalse(receipt["flint_replay_performed"])
        self.assertFalse(receipt["self_reported_flint_boolean_semantics_verified"])
        self.assertFalse(receipt["minimum_gap_preimage_verified"])
        self.assertFalse(receipt["reciprocal_sum_semantics_verified"])
        self.assertFalse(receipt["zeta_zero_isolation_semantics_verified"])
        self.assertFalse(receipt["zeta_zero_count_semantics_verified"])
        self.assertFalse(receipt["semantic_verification_performed"])
        self.assertFalse(receipt["analytic_claim_proved"])
        self.assertTrue(receipt["external_semantics_required"])

    def test_count_mismatch_is_rejected(self) -> None:
        artifact = prop77_fixture()
        artifact["zero_count"]["count"] = 22_490  # type: ignore[index]
        with self.assertRaisesRegex(analytic.AnalyticArtifactError, "zero_count.count"):
            analytic.verify_prop77_flint_bytes(canonical(artifact))

    def test_cutoff_crossing_is_rejected(self) -> None:
        artifact = prop77_fixture()
        last = artifact["isolation"]["last_included"]  # type: ignore[index]
        last["ordinate"]["upper"] = rational(20_001)
        last["ordinate"]["upper_decimal_outward"] = "20001.0"
        last["upper_reused"] = rational(20_001)
        with self.assertRaisesRegex(analytic.AnalyticArtifactError, "at or below"):
            analytic.verify_prop77_flint_bytes(canonical(artifact))

    def test_reused_endpoint_tampering_is_rejected(self) -> None:
        artifact = prop77_fixture()
        artifact["isolation"]["first_excluded"]["lower_reused"] = rational(20_003)  # type: ignore[index]
        with self.assertRaisesRegex(analytic.AnalyticArtifactError, "lower_reused"):
            analytic.verify_prop77_flint_bytes(canonical(artifact))

    def test_reciprocal_bound_is_strict(self) -> None:
        artifact = prop77_fixture()
        reciprocal = artifact["isolation"]["reciprocal_sum"]  # type: ignore[index]
        reciprocal["arb_upper"] = rational(Fraction(257_983, 50_000))
        reciprocal["upper_decimal_outward"] = "5.15966"
        reciprocal["certified_margin_lower"] = rational(0)
        reciprocal["certified_margin_lower_decimal_outward"] = "0.0"
        with self.assertRaisesRegex(analytic.AnalyticArtifactError, "strictly below"):
            analytic.verify_prop77_flint_bytes(canonical(artifact))

    def test_malformed_digest_is_rejected(self) -> None:
        artifact = prop77_fixture()
        artifact["isolation"]["ordinate_intervals_sha256"] = "AB" * 32  # type: ignore[index]
        with self.assertRaisesRegex(analytic.AnalyticArtifactError, "lowercase hexadecimal"):
            analytic.verify_prop77_flint_bytes(canonical(artifact))

    def test_well_formed_but_different_digest_is_rejected(self) -> None:
        artifact = prop77_fixture()
        artifact["isolation"]["ordinate_intervals_sha256"] = "cd" * 32  # type: ignore[index]
        with self.assertRaisesRegex(
            analytic.AnalyticArtifactError, "pinned retained interval digest"
        ):
            analytic.verify_prop77_flint_bytes(canonical(artifact))

    def test_changed_replay_configuration_is_rejected(self) -> None:
        artifact = prop77_fixture()
        artifact["configuration"]["precision_bits"] = 128  # type: ignore[index]
        with self.assertRaisesRegex(
            analytic.AnalyticArtifactError, "configuration.precision_bits"
        ):
            analytic.verify_prop77_flint_bytes(canonical(artifact))

    def test_fabricated_self_consistent_summary_is_not_a_retained_artifact(self) -> None:
        artifact = prop77_fixture()
        reciprocal = artifact["isolation"]["reciprocal_sum"]  # type: ignore[index]
        fabricated_upper = Fraction(128_991, 25_000)  # 5.15964
        target = Fraction(257_983, 50_000)
        reciprocal["arb_lower"] = rational(5)
        reciprocal["arb_upper"] = rational(fabricated_upper)
        reciprocal["lower_decimal_outward"] = "5.0"
        reciprocal["upper_decimal_outward"] = "5.15964"
        reciprocal["certified_margin_lower"] = rational(target - fabricated_upper)
        reciprocal["certified_margin_lower_decimal_outward"] = "0.00002"
        with self.assertRaisesRegex(
            analytic.AnalyticArtifactError, "pinned retained artifact SHA-256"
        ):
            analytic.verify_prop77_flint_bytes(canonical(artifact))

    def test_false_external_summary_flag_is_rejected(self) -> None:
        artifact = deepcopy(prop77_fixture())
        artifact["isolation"]["all_real_parts_exact"] = False  # type: ignore[index]
        with self.assertRaisesRegex(analytic.AnalyticArtifactError, "must be true"):
            analytic.verify_prop77_flint_bytes(canonical(artifact))


if __name__ == "__main__":
    unittest.main()
