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


def _scan_brackets(
    character: object,
    configuration: dict[str, int],
    t0: Fraction,
    stop: Fraction,
    *,
    step: Fraction = Fraction(5, 64),
    refine_to: Fraction | None = None,
) -> list[dict[str, object]]:
    """Return ordered strict Hardy-Z sign-change brackets inside ``[t0,stop)``.

    ``refine_to`` optionally bisects every bracket down to that width.  The
    Turing identity check needs tight ordinates; the coarse scan alone leaves a
    staircase uncertainty far larger than Rumely's envelope.
    """

    from tools import tg_dirichlet_flint_backend as backend

    cache: dict[Fraction, int] = {}

    def sign(point: Fraction) -> int:
        if point not in cache:
            cache[point] = backend._hardy_sign(character, point, configuration)[0]
        return cache[point]

    points = [t0]
    point = t0 + step
    while point < stop:
        points.append(point)
        point += step
    points.append(stop)
    raw: list[tuple[Fraction, Fraction]] = []
    for lower, upper in zip(points, points[1:]):
        if sign(lower) != sign(upper):
            raw.append((lower, upper))
    brackets: list[dict[str, object]] = []
    for lower, upper in raw:
        if refine_to is not None:
            while upper - lower > refine_to:
                middle = (lower + upper) / 2
                if sign(lower) == sign(middle):
                    lower = middle
                else:
                    upper = middle
        brackets.append(
            {
                "lower": post.fraction_json(lower),
                "upper": post.fraction_json(upper),
                "multiplicity": 1,
            }
        )
    return brackets


def _q3_turing_request() -> dict[str, object]:
    from tools import tg_dirichlet_flint_backend as backend

    character = backend.dirichlet_char(3, 2)
    configuration = backend.configuration()
    t0 = Fraction(60)
    h = Fraction(100)
    brackets = _scan_brackets(character, configuration, t0, t0 + h)
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


# Every case is a real primitive character.  ``t0`` and ``t0+h`` are shifted by
# 1/64 so the argument-principle contour never runs through a zero, which is the
# same convention the direct FLINT backend uses.  The table covers both
# parities, real and genuinely complex conjugate pairs, and two different window
# shapes, so no single additive or multiplicative fudge can satisfy all rows.
_TURING_IDENTITY_CASES = (
    # q, conrey, conjugate conrey, parity, t0, h
    (3, 2, 2, 1, Fraction(3841, 64), Fraction(100)),
    (3, 2, 2, 1, Fraction(7681, 64), Fraction(40)),
    (4, 3, 3, 1, Fraction(3841, 64), Fraction(40)),
    (5, 4, 4, 0, Fraction(3841, 64), Fraction(40)),
    (7, 2, 4, 0, Fraction(3841, 64), Fraction(40)),
    (7, 3, 5, 1, Fraction(3841, 64), Fraction(40)),
)


def _certified_symmetric_count(
    q: int, conrey: int, parity: int, height: Fraction, configuration: dict[str, int]
) -> int:
    """Argument-principle count of zeros with ``|Im s| <= height``.

    The contour is the counterclockwise rectangle ``[-1/2,3/2] x [-T,T]``.  A
    primitive nonprincipal ``L`` has no pole, and the only trivial zero inside
    that rectangle is the simple zero at ``s=0`` for an even character.
    """

    from tools import tg_dirichlet_flint_backend as backend

    result = backend.certified_winding_count(
        backend.dirichlet_char(q, conrey), height, configuration
    )
    return result["zero_count_with_trivial_zeros"] - (1 if parity == 0 else 0)


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
        # The decision is "strictly below the next integer".  The bound must
        # not certainly exclude the true count either, which is exactly the
        # module's own consistency gate.
        self.assertTrue(completion_upper < 45)
        self.assertFalse(completion_upper < 44)
        self.assertFalse(result["source_2h_constant_included_in_bound"])
        # The source's extra "+2h" is retained only as an audit quantity.
        two_over_pi = post.interval_arb(
            "two_over_pi", result["source_two_over_pi_contribution"]
        )
        self.assertTrue(two_over_pi > post.arb("0.6366"))
        self.assertTrue(two_over_pi < post.arb("0.6367"))
        released = post.interval_arb(
            "released", result["platt_released_code_upper_bound"]
        )
        self.assertTrue(released > completion_upper)
        self.assertTrue(released < 45)
        literal = post.interval_arb(
            "literal", result["literal_arxiv_v1_typeset_interval"]
        )
        self.assertFalse(literal.contains(44))
        self.assertTrue(literal > 86)
        self.assertTrue(literal < 87)

    def test_source_height_max_branch_is_exercised_on_both_sides(self) -> None:
        # The campaign height is max(10^8/q, 200 + c/q) with c = 37.5e6 for odd
        # q and 75e6 for even q.  The branches cross at q = 312500 (odd) and
        # q = 125000 (even).  Both sides must be reproduced exactly.
        from tools import tg_dirichlet_flint_backend as backend

        for q, expected in (
            (3, Fraction(100_000_000, 3)),
            (5, Fraction(100_000_000, 5)),
            (312_499, Fraction(100_000_000, 312_499)),
            (312_501, Fraction(200) + Fraction(37_500_000, 312_501)),
            (124_998, Fraction(100_000_000, 124_998)),
            (125_002, Fraction(200) + Fraction(75_000_000, 125_002)),
            (400_000, Fraction(200) + Fraction(75_000_000, 400_000)),
        ):
            self.assertEqual(backend._source_height(q), expected, msg=f"q={q}")
        # The crossing conductors are far beyond the direct Arb backend's
        # reach, so the Turing identity rows below stay at small conductors.
        self.assertGreater(312_501, 400)

    def test_turing_identity_holds_and_refutes_the_source_2h_constant(self) -> None:
        # For each row: certify N_chi(t0) and N_chi(t0+h) by two independent
        # argument-principle winding counts, certify that the retained bracket
        # lists are complete by matching their total against the winding
        # difference, then check the corrected identity against Rumely's
        # Theorem 3.3 envelope.  Adding the source's "+2h" (i.e. +2/pi) must
        # push the implied paired S integral outside that envelope.
        from tools import tg_dirichlet_flint_backend as backend

        configuration = backend.configuration()
        for q, conrey, conjugate, parity, t0, h in _TURING_IDENTITY_CASES:
            with self.subTest(q=q, conrey=conrey, t0=str(t0), h=str(h)):
                stop = t0 + h
                below = _certified_symmetric_count(q, conrey, parity, t0, configuration)
                above = _certified_symmetric_count(
                    q, conrey, parity, stop, configuration
                )
                chi_rows = _scan_brackets(
                    backend.dirichlet_char(q, conrey),
                    configuration,
                    t0,
                    stop,
                    refine_to=Fraction(1, 1 << 20),
                )
                conjugate_rows = _scan_brackets(
                    backend.dirichlet_char(q, conjugate),
                    configuration,
                    t0,
                    stop,
                    refine_to=Fraction(1, 1 << 20),
                )
                # Completeness: the two positive windows together account for
                # every zero the contour found between the two heights.
                self.assertEqual(len(chi_rows) + len(conjugate_rows), above - below)
                request = {
                    "kind": post.TURING_SCHEMA,
                    "q": q,
                    "conrey_number": conrey,
                    "conjugate_conrey_number": conjugate,
                    "parity": parity,
                    "t0": post.fraction_json(t0),
                    "h": post.fraction_json(h),
                    "endpoints_zero_free": True,
                    "window_bracket_multiplicity_lower_bounds_certified": True,
                    "negative_window_reflected_to_conjugate_certified": True,
                    "window_complete_and_count_exact_certified": True,
                    "chi_window_zeros": chi_rows,
                    "conjugate_window_zeros": conjugate_rows,
                    "isolated_count_below_t0": below,
                    "isolated_below_t0_certified": True,
                }
                result = post.paired_turing(request, precision=192)
                self.assertEqual(
                    result["certified_multiplicity_count_below_t0"], below
                )
                envelope = post.interval_arb(
                    "envelope", result["paired_rumely_bound_over_h"]
                )
                residual = post.interval_arb(
                    "residual", result["identity_residual_interval"]
                )
                # The corrected identity: the residual is the paired S integral
                # over h, and Theorem 3.3 bounds it.
                self.assertTrue(residual < envelope)
                self.assertTrue(residual > -envelope)
                # The source's "+2h" would move the residual by -2/pi.  It must
                # break the same envelope at every row.
                shifted = residual - 2 / post.arb.pi()
                self.assertTrue(shifted < -envelope)
                # The decision itself still resolves to the certified integer.
                upper = post.interval_arb(
                    "completion", result["completion_upper_bound"]
                )
                self.assertTrue(upper < below + 1)
                self.assertFalse(upper < below)

    def test_identity_residual_check_fails_closed_on_a_wrong_count(self) -> None:
        # Same q=3 row as the identity table, with bisected ordinates so the
        # residual is resolved to about 1e-6.  Only the true count 44 survives.
        from tools import tg_dirichlet_flint_backend as backend

        configuration = backend.configuration()
        t0 = Fraction(3841, 64)
        h = Fraction(100)
        rows = _scan_brackets(
            backend.dirichlet_char(3, 2),
            configuration,
            t0,
            t0 + h,
            refine_to=Fraction(1, 1 << 20),
        )
        request = {
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
            "window_complete_and_count_exact_certified": True,
            "chi_window_zeros": rows,
            "conjugate_window_zeros": rows,
            "isolated_count_below_t0": 44,
            "isolated_below_t0_certified": True,
        }
        accepted = post.paired_turing(dict(request), precision=192)
        self.assertEqual(accepted["certified_multiplicity_count_below_t0"], 44)
        for wrong in (43, 45):
            with self.subTest(count=wrong):
                broken = dict(request)
                broken["isolated_count_below_t0"] = wrong
                with self.assertRaisesRegex(
                    post.DirichletPostprocessError, "escapes Rumely Theorem 3.3"
                ):
                    post.paired_turing(broken, precision=192)
        # A coarse bracket list cannot resolve the residual, so the same
        # assertion must be refused rather than silently accepted.
        coarse = dict(request)
        coarse["chi_window_zeros"] = _scan_brackets(
            backend.dirichlet_char(3, 2), configuration, t0, t0 + h
        )
        coarse["conjugate_window_zeros"] = coarse["chi_window_zeros"]
        with self.assertRaisesRegex(
            post.DirichletPostprocessError, "escapes Rumely Theorem 3.3"
        ):
            post.paired_turing(coarse, precision=192)

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
