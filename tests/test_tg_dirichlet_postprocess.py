# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tg_verifier.dirichlet_postprocess as post  # noqa: E402


PINNED_FLINT = (
    post.FLINT_IMPORT_ERROR is None
    and post.flint.__version__ == "0.9.0"
    and post.flint.__FLINT_VERSION__ == "3.6.0"
)


def _completed_q5_request() -> dict[str, object]:
    post.ctx.prec = 192
    q = 5
    conrey = 2
    parity = 1
    t = post.arb("5/4")
    character = post.dirichlet_char(q, conrey)
    l_value = character.l_function(post.acb(post.arb("1/2"), t))
    gauss = post.acb(0)
    order = character.order()
    for residue in range(1, q + 1):
        exponent = character.chi_exponent(residue)
        if exponent is None:
            continue
        chi = post.acb(0, 2 * post.arb.pi() * exponent / order).exp()
        additive = post.acb(0, 2 * post.arb.pi() * residue / q).exp()
        gauss += chi * additive
    root_number = gauss / (post.acb(0, 1) ** parity * post.arb(q).sqrt())
    return {
        "kind": post.COMPLETED_SCHEMA,
        "q": q,
        "conrey_number": conrey,
        "primitive_character_ordinal": 0,
        "parity": parity,
        "ordinate": post.fraction_json(Fraction(5, 4)),
        "q_minus_s_factor_applied": True,
        "finite_dirichlet_term_addback_applied": True,
        "primitive_frequency_conrey_identity_checked": True,
        "root_number_certified_from_character": True,
        "all_character_stage_receipt_sha256": "1" * 64,
        "lattice_and_tail_receipt_sha256": "2" * 64,
        "finite_addback_receipt_sha256": "3" * 64,
        "root_number_receipt_sha256": "4" * 64,
        "l_value": post.rectangle_json(l_value),
        "root_number": post.rectangle_json(root_number),
    }


def _q3_turing_request() -> dict[str, object]:
    from tools import tg_dirichlet_flint_backend as backend

    character = backend.dirichlet_char(3, 2)
    configuration = backend.configuration()
    t0 = Fraction(60)
    h = Fraction(100)
    stop = t0 + h
    step = Fraction(5, 64)
    points = [t0]
    point = t0 + step
    while point < stop:
        points.append(point)
        point += step
    points.append(stop)
    brackets: list[dict[str, object]] = []
    previous = points[0]
    previous_sign = backend._hardy_sign(character, previous, configuration)[0]
    for point in points[1:]:
        sign = backend._hardy_sign(character, point, configuration)[0]
        if sign != previous_sign:
            brackets.append(
                {
                    "lower": post.fraction_json(previous),
                    "upper": post.fraction_json(point),
                    "multiplicity": 1,
                }
            )
        previous = point
        previous_sign = sign
    return {
        "kind": post.TURING_SCHEMA,
        "q": 3,
        "conrey_number": 2,
        "conjugate_conrey_number": 2,
        "parity": 1,
        "t0": post.fraction_json(t0),
        "h": post.fraction_json(h),
        "endpoints_zero_free": True,
        "window_bracket_multiplicity_lower_bounds_certified": True,
        "negative_window_reflected_to_conjugate_certified": True,
        "chi_window_zeros": brackets,
        "conjugate_window_zeros": brackets,
        "isolated_count_below_t0": 44,
        "isolated_below_t0_certified": True,
    }


class DirichletPostprocessStructuralTests(unittest.TestCase):
    def test_capability_separates_source_domain_from_production(self) -> None:
        report = post.capability_report()
        self.assertFalse(report["production_ready"])
        self.assertTrue(report["full_source"]["input_domain_supported"])
        self.assertFalse(report["full_source"]["campaign_run_completed"])
        self.assertIn("ordinary_upsampling", report["work_units"])
        self.assertIn("exception_path", report["work_units"])
        self.assertIn("turing_path", report["work_units"])


@unittest.skipUnless(PINNED_FLINT, "requires pinned python-flint 0.9.0 / FLINT 3.6.0")
class DirichletPostprocessArbTests(unittest.TestCase):
    def test_completed_value_consumes_interval_l_and_root(self) -> None:
        result = post.completed_value(_completed_q5_request())
        self.assertTrue(result["upstream_l_value_consumed"])
        self.assertFalse(result["direct_flint_hardy_z_called"])
        self.assertNotEqual(result["strict_sign"], 0)

    def test_finite_sinc_has_separate_alias_and_tail_budgets(self) -> None:
        request = {
            "kind": post.UPSAMPLE_SCHEMA,
            "q": 3,
            "parity": 1,
            "bandwidth": post.fraction_json(Fraction(32, 5)),
            "gaussian_h": post.fraction_json(Fraction(2)),
            "target_ordinate": post.fraction_json(Fraction(1, 100)),
            "truncation_index": 4,
            # An unauthenticated request assertion must never promote the
            # stage to production acceptance.
            "lemma_6_7_large_enough_t0_obligation_discharged": True,
            "samples": [
                {
                    "index": index,
                    "completed_value": {
                        "lower": post.fraction_json(Fraction(1)),
                        "upper": post.fraction_json(Fraction(1)),
                    },
                }
                for index in range(-3, 5)
            ],
        }
        result = post.whittaker_shannon(request)
        self.assertEqual(result["finite_sample_count"], 8)
        self.assertIn("weiss_alias_budget", result)
        self.assertIn("truncation_budget", result)
        self.assertFalse(result["production_accept"])

    def test_accepted_manuscript_source_upsampling_parameters(self) -> None:
        # Platt's accepted manuscript, Section 9: A=64/5, h=7/32,
        # 20 samples on each side, claimed total error < 8.6e-8.
        bandwidth = Fraction(32, 5)  # 2B=A
        target = Fraction(100_000_000, 3)
        target_index = 2 * bandwidth * target
        floor_index = target_index.numerator // target_index.denominator
        zero = {
            "lower": post.fraction_json(Fraction(0)),
            "upper": post.fraction_json(Fraction(0)),
        }
        request = {
            "kind": post.UPSAMPLE_SCHEMA,
            "q": 3,
            "parity": 1,
            "bandwidth": post.fraction_json(bandwidth),
            "gaussian_h": post.fraction_json(Fraction(7, 32)),
            "target_ordinate": post.fraction_json(target),
            "truncation_index": 20,
            "lemma_6_7_large_enough_t0_obligation_discharged": False,
            "samples": [
                {"index": index, "completed_value": zero}
                for index in range(floor_index - 19, floor_index + 21)
            ],
        }
        result = post.whittaker_shannon(request, precision=128)
        total = post.interval_arb("total", result["total_enclosure"])
        self.assertTrue(total < post.arb("8.6e-8"))
        self.assertFalse(result["production_accept"])

    def test_q3_paired_turing_kat_preserves_multiplicity(self) -> None:
        result = post.paired_turing(_q3_turing_request(), precision=128)
        self.assertEqual(result["certified_multiplicity_count_below_t0"], 44)
        self.assertEqual(result["chi_window_multiplicity"], 63)
        self.assertEqual(result["conjugate_window_multiplicity"], 63)
        self.assertTrue(
            result["source_normalized_reflected_turing_candidate_executed"]
        )
        self.assertTrue(
            result["negative_window_reflected_to_conjugate_certified"]
        )
        self.assertFalse(result["literal_paper_theorem_3_2_accepted"])
        self.assertFalse(result["production_accept"])
        released = result["source_mapping"]["released_code"]
        self.assertEqual(released["commit"], post.RELEASED_CODE_COMMIT)
        self.assertEqual(released["functions"], ["ln_term", "turing_max"])
        completion_upper = post.interval_arb(
            "completion", result["completion_upper_bound"]
        )
        self.assertTrue(completion_upper > 44)
        self.assertTrue(completion_upper < 45)
        two_over_pi = post.interval_arb(
            "two_over_pi", result["source_two_over_pi_contribution"]
        )
        self.assertTrue(two_over_pi > post.arb("0.6366"))
        self.assertTrue(two_over_pi < post.arb("0.6367"))
        literal = post.interval_arb(
            "literal", result["literal_arxiv_v1_typeset_interval"]
        )
        self.assertFalse(literal.contains(44))

    def test_paired_turing_requires_negative_window_reflection(self) -> None:
        request = {
            "kind": post.TURING_SCHEMA,
            "q": 3,
            "conrey_number": 2,
            "conjugate_conrey_number": 2,
            "parity": 1,
            "t0": post.fraction_json(Fraction(60)),
            "h": post.fraction_json(Fraction(100)),
            "endpoints_zero_free": True,
            "window_bracket_multiplicity_lower_bounds_certified": True,
        }
        with self.assertRaisesRegex(
            post.DirichletPostprocessError, "negative chi window"
        ):
            post.paired_turing(request, precision=128)

    def test_role_separated_cli_freshly_replays_completed_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = root / "request.json"
            result = root / "result.json"
            receipt = root / "receipt.json"
            request.write_bytes(post.canonical_json_bytes(_completed_q5_request()))
            subprocess.run(
                [
                    sys.executable,
                    "tools/tg_dirichlet_postprocess.py",
                    "produce",
                    str(request),
                    str(result),
                ],
                cwd=ROOT,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            subprocess.run(
                [
                    sys.executable,
                    "tools/tg_dirichlet_postprocess.py",
                    "verify",
                    str(request),
                    str(result),
                    str(receipt),
                ],
                cwd=ROOT,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            value = json.loads(receipt.read_text(encoding="ascii"))
            self.assertTrue(value["accepted"])

    def test_checker_rejects_tampered_source_mapping(self) -> None:
        from tools import tg_dirichlet_postprocess as checker

        request = _completed_q5_request()
        retained = post.completed_value(request)
        retained["source_mapping"] = "tampered"
        with self.assertRaisesRegex(
            post.DirichletPostprocessError, "source mapping differs"
        ):
            checker.verify(request, retained, 256)


if __name__ == "__main__":
    unittest.main()
