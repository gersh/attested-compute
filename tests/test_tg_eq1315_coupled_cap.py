#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Focused tests for the disabled equation-(13.15) cell verifier."""

from __future__ import annotations

import ast
from dataclasses import replace
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys
import unittest

import tg_verifier.eq1315_coupled_cap as eq1315
from tg_verifier.eq1315_coupled_cap import (
    Eq1315CertificateError,
    EvalConfig,
    N_LOWER,
    N_UPPER,
    SCHEMA,
    TruncatedCellCertificate,
    capability_report,
    check_production_certificate,
    check_truncated_certificate,
    classify_branch,
    exact_totient_ratio_upper,
    geometric_panels,
    global_q_upper,
    global_u_domain,
    issue_truncated_certificate,
    make_cell_box,
    verify_production_certificate,
    verify_truncated_certificate,
)
from tg_verifier.prop1224_directed import RationalInterval


CONFIG = EvalConfig(bits=144, terms=32)
ROOT = Path(__file__).resolve().parents[1]


def narrow_lower_u() -> RationalInterval:
    domain = global_u_domain(CONFIG)
    return RationalInterval(domain.lower, domain.lower + Fraction(1, 1 << 50))


class DomainAndGuardTests(unittest.TestCase):
    def test_verifier_contains_no_native_float_literals(self) -> None:
        source = Path(eq1315.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        floats = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        ]
        self.assertEqual(floats, [])

    def test_capability_is_disabled_and_names_the_exact_boundary(self) -> None:
        report = capability_report(CONFIG)
        self.assertFalse(report["enabled"])
        self.assertFalse(report["production_tail_checker"])
        self.assertFalse(report["source_upper_model_lean_realization"])
        self.assertFalse(report["full_artifact_present"])
        self.assertIsNone(report["registered_invocation"])
        self.assertEqual(report["n_lower"], N_LOWER)
        self.assertEqual(report["n_upper"], N_UPPER)
        self.assertIn(
            "PaperEq1315DirectEndpointAwareLowerBandCoupledCap",
            report["lean_theorem"],
        )
        self.assertEqual(report["q_upper_safe"], global_q_upper(CONFIG))
        self.assertGreater(report["q_upper_safe"], 231_000_000)
        self.assertLess(report["q_upper_safe"], 233_000_000)

    def test_disabled_specification_matches_the_runtime_gate(self) -> None:
        specification = json.loads(
            (
                ROOT
                / "specifications"
                / "TG_EQ1315_COUPLED_CAP_DISABLED.json"
            ).read_text(encoding="utf-8")
        )
        report = capability_report(CONFIG)
        self.assertEqual(
            specification["algorithm_id"], report["algorithm_id"]
        )
        self.assertFalse(specification["enabled"])
        self.assertFalse(specification["receipt_eligible"])
        self.assertEqual(
            specification["cell_coordinates"][
                "global_q_enumeration_ceiling"
            ],
            report["q_upper_safe"],
        )
        self.assertEqual(
            specification["finite_checker"]["schema"], SCHEMA
        )
        self.assertEqual(
            specification["production_gate"][
                "supported_tail_witness_schemas"
            ],
            [],
        )
        self.assertEqual(
            specification["production_gate"]["acceptance"],
            "always_refused",
        )

    def test_exact_t_guard_and_q_lower_guard_fail_closed(self) -> None:
        u = narrow_lower_u()
        for bad_t in (
            RationalInterval(Fraction(-1, 100), Fraction(1, 2)),
            RationalInterval(Fraction(0), Fraction(101, 100)),
        ):
            with self.subTest(t=bad_t):
                box = make_cell_box(
                    u=u,
                    t=bad_t,
                    q_lower=510_510,
                    q_upper=510_510,
                    parity="even",
                    config=CONFIG,
                )
                with self.assertRaisesRegex(
                    Eq1315CertificateError, r"t in \[0, 1\]"
                ):
                    issue_truncated_certificate(
                        box,
                        geometric_panels(box, stop=Fraction(1)),
                        config=CONFIG,
                    )

        box = make_cell_box(
            u=u,
            t=RationalInterval.exact(0),
            q_lower=150_000,
            q_upper=150_000,
            parity="even",
            config=CONFIG,
        )
        with self.assertRaisesRegex(Eq1315CertificateError, "q lower"):
            issue_truncated_certificate(
                box,
                geometric_panels(box, stop=Fraction(1)),
                config=CONFIG,
            )

        # The global roster ceiling is valid only near the top of the u
        # domain.  A low-u cell must prove its own exact q upper guard.
        too_large_at_low_u = make_cell_box(
            u=u,
            t=RationalInterval.exact(0),
            q_lower=global_q_upper(CONFIG),
            q_upper=global_q_upper(CONFIG),
            parity="even",
            config=CONFIG,
        )
        with self.assertRaisesRegex(
            Eq1315CertificateError, "exact q upper guard"
        ):
            issue_truncated_certificate(
                too_large_at_low_u,
                geometric_panels(too_large_at_low_u, stop=Fraction(1)),
                config=CONFIG,
            )

    def test_piecewise_branch_is_derived_not_caller_selected(self) -> None:
        low = narrow_lower_u()
        self.assertEqual(
            classify_branch(low, 510_510, 510_510, CONFIG), "q_le_r1"
        )
        self.assertEqual(
            classify_branch(low, 2_000_001, 2_000_001, CONFIG), "q_gt_r1"
        )
        whole = global_u_domain(CONFIG)
        self.assertEqual(
            classify_branch(whole, 2_000_000, 2_000_001, CONFIG), "split"
        )

        valid = make_cell_box(
            u=low,
            t=RationalInterval.exact(0),
            q_lower=510_510,
            q_upper=510_510,
            parity="even",
            config=CONFIG,
        )
        stale = replace(valid, branch="q_gt_r1")
        with self.assertRaisesRegex(Eq1315CertificateError, "branch tag"):
            issue_truncated_certificate(
                stale,
                geometric_panels(stale, stop=Fraction(1)),
                config=CONFIG,
            )

    def test_parity_separated_totient_envelopes_are_exactly_recomputed(self) -> None:
        even, even_count = exact_totient_ratio_upper(10, 20, "even")
        odd, odd_count = exact_totient_ratio_upper(10, 20, "odd")
        self.assertEqual(even_count, 6)
        self.assertEqual(odd_count, 5)
        self.assertEqual(even, Fraction(3))  # q=12 or 18
        self.assertEqual(odd, Fraction(15, 8))

        before = eq1315._exact_totient_ratio_envelopes.cache_info()
        exact_totient_ratio_upper(12_340, 12_350, "even")
        exact_totient_ratio_upper(12_340, 12_350, "odd")
        after = eq1315._exact_totient_ratio_envelopes.cache_info()
        self.assertEqual(after.misses - before.misses, 1)
        self.assertGreaterEqual(after.hits - before.hits, 1)


class DirectedFormulaKnownAnswerTests(unittest.TestCase):
    def test_even_direct_piece_encloses_independent_source_values(self) -> None:
        x = RationalInterval.exact(5 * 10**24)
        q = RationalInterval.exact(180_180)
        ratio = RationalInterval.exact(Fraction(180_180, 34_560))
        expected = {
            0: "0.0372690955357138839653864031745265288410242265",
            1: "0.0380109639752452616804132524029595799112415980",
            8: "0.0372986144242123518630373535694559422504443581",
            20: "0.0258417505094062578275175950799609792109894006",
        }
        for d, source_value in expected.items():
            with self.subTest(d=d):
                enclosure = eq1315._fixed_piece_upper(
                    x,
                    RationalInterval.exact(d),
                    q,
                    ratio,
                    "even",
                    CONFIG,
                )
                self.assertTrue(enclosure.contains(Fraction(source_value)))

    def test_odd_resonant_model_encloses_independent_source_value(self) -> None:
        enclosure = eq1315._p1_upper(
            RationalInterval.exact(5 * 10**24),
            RationalInterval.exact(8),
            RationalInterval.exact(200_003),
            RationalInterval.exact(Fraction(200_003, 200_002)),
            "odd",
            CONFIG,
        )
        self.assertTrue(
            enclosure.contains(
                Fraction(
                    "37534050849846270617.99328126762761953208898184"
                )
            )
        )

    def test_fresh_g_encloses_independent_source_value(self) -> None:
        enclosure = eq1315._g_unweighted_corrected(
            RationalInterval.exact(5 * 10**24),
            RationalInterval.exact(180_180),
            CONFIG,
        )
        self.assertTrue(
            enclosure.contains(
                Fraction(
                    "0.0396709086887883277730938317549629669482591999"
                )
            )
        )


class CertificateReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        u = narrow_lower_u()
        cls.even_box = make_cell_box(
            u=u,
            t=RationalInterval.exact(0),
            q_lower=510_510,
            q_upper=510_510,
            parity="even",
            config=CONFIG,
        )
        cls.even_certificate = issue_truncated_certificate(
            cls.even_box,
            geometric_panels(
                cls.even_box, stop=Fraction(1), subdivisions=1
            ),
            config=CONFIG,
        )

        cls.crossing_box = make_cell_box(
            u=u,
            t=RationalInterval(Fraction(63, 64), Fraction(1)),
            q_lower=510_511,
            q_upper=510_511,
            parity="odd",
            config=CONFIG,
        )
        cls.crossing_certificate = issue_truncated_certificate(
            cls.crossing_box,
            geometric_panels(
                cls.crossing_box, stop=Fraction(2), subdivisions=1
            ),
            config=CONFIG,
        )

    def test_finite_even_certificate_replays_and_has_positive_margin(self) -> None:
        result = verify_truncated_certificate(self.even_certificate)
        self.assertTrue(result.bounded_w_inequality_holds)
        self.assertEqual(result.branch, "q_le_r1")
        self.assertEqual(result.q_count, 1)
        self.assertEqual(result.selector_crossing_panels, 0)
        self.assertLess(result.integral_upper, result.target_lower)
        self.assertTrue(check_truncated_certificate(self.even_certificate))

    def test_odd_lane_keeps_the_selector_crossover_visible(self) -> None:
        result = verify_truncated_certificate(self.crossing_certificate)
        self.assertEqual(result.q_count, 1)
        self.assertEqual(result.selector_crossing_panels, 1)
        self.assertGreater(result.panel_count, 1)
        self.assertFalse(result.bounded_w_inequality_holds)
        self.assertFalse(check_truncated_certificate(self.crossing_certificate))

    def test_decisive_claims_and_coordinate_bindings_reject_tampering(self) -> None:
        certificate = self.even_certificate
        mutations: tuple[object, ...] = (
            replace(
                certificate,
                claimed_integral_upper=certificate.claimed_integral_upper
                - Fraction(1, 1 << 144),
            ),
            replace(
                certificate,
                claimed_target_lower=certificate.claimed_target_lower
                + Fraction(1, 1 << 144),
            ),
            replace(
                certificate,
                totient_ratio_upper=certificate.totient_ratio_upper
                - Fraction(1, 1_000_000),
            ),
            replace(
                certificate,
                claimed_selector_crossing_panels=1,
            ),
            replace(
                certificate,
                claimed_selector_crossing_panels=False,  # type: ignore[arg-type]
            ),
            replace(
                certificate,
                box=replace(
                    certificate.box,
                    v=RationalInterval(
                        certificate.box.v.lower + Fraction(1, 1 << 80),
                        certificate.box.v.upper + Fraction(1, 1 << 80),
                    ),
                ),
            ),
            replace(
                certificate,
                config=object(),  # type: ignore[arg-type]
            ),
            replace(
                certificate,
                box=replace(
                    certificate.box,
                    u=object(),  # type: ignore[arg-type]
                ),
            ),
            replace(
                certificate,
                panels=(object(),),  # type: ignore[arg-type]
            ),
            replace(certificate, schema="unknown"),
            object(),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assertFalse(check_truncated_certificate(mutation))

    def test_production_path_refuses_truncation_without_a_tail_witness(self) -> None:
        self.assertFalse(check_production_certificate(self.even_certificate))
        with self.assertRaisesRegex(
            Eq1315CertificateError, "no reviewed infinite Gaussian-tail"
        ):
            verify_production_certificate(self.even_certificate)

        # There is no hidden generic payload slot: the v1 dataclass only
        # admits None, and replay rejects a dynamically forged value.
        forged: TruncatedCellCertificate = replace(
            self.even_certificate,
            tail_witness="pretend-success",  # type: ignore[arg-type]
        )
        self.assertFalse(check_truncated_certificate(forged))
        self.assertFalse(check_production_certificate(forged))

        # Even an in-process mutation of the advertised registry cannot
        # reach success: v1 has no dispatch implementation after the gate.
        original_registry = eq1315.SUPPORTED_TAIL_WITNESS_SCHEMAS
        try:
            eq1315.SUPPORTED_TAIL_WITNESS_SCHEMAS = ("forged-schema",)
            self.assertFalse(
                check_production_certificate(self.even_certificate)
            )
        finally:
            eq1315.SUPPORTED_TAIL_WITNESS_SCHEMAS = original_registry


class BenchmarkContractTests(unittest.TestCase):
    def test_cli_labels_the_reference_scope_and_has_no_device_projection(
        self,
    ) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "benchmark_tg_eq1315_coupled_cap.py"),
                "--cells",
                "1",
                "--stop",
                "1",
                "--terms",
                "32",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(completed.stdout)
        self.assertEqual(
            report["scope"], "finite-w-directed-rational-reference-only"
        )
        self.assertFalse(report["production_accepted"])
        self.assertIsNone(report["accelerator_projection"]["cpu_seconds"])
        self.assertIsNone(report["accelerator_projection"]["h100_seconds"])
        self.assertEqual(report["sample"]["cells"], 1)
        self.assertEqual(report["totient_prepass"]["sample_rows"], 100_000)
        self.assertGreater(
            report["totient_prepass"]["sample_rows_per_second"], 0
        )


if __name__ == "__main__":
    unittest.main()
