# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from decimal import Decimal
import unittest

from tg_verifier.azure_production_sizing import (
    ATOM_IDS,
    CPU_SKU,
    PHYSICAL_CAMPAIGN_IDS,
    ProductionSizingError,
    build_sizing_report,
    parse_retail_prices,
    retail_prices_url,
)
from tg_verifier.azure_backend_optimizer import (
    BackendOptimizationError,
    CampaignRoute,
    ResourceDemand,
    optimize_backend_catalog,
)
from tg_verifier.dirichlet_allchars_stage import source_work as allchars_source_work
from tg_verifier.dirichlet_tmajor_cuda_block import (
    source_projection as tmajor_source_projection,
)


class AzureProductionSizingTests(unittest.TestCase):
    def test_backend_optimizer_covers_eleven_physical_campaigns_and_fails_closed(self) -> None:
        optimizer = build_sizing_report()["backend_optimizer"]
        self.assertEqual(optimizer["physical_campaign_count"], 11)
        self.assertEqual(
            tuple(optimizer["physical_campaign_ids"]), PHYSICAL_CAMPAIGN_IDS
        )
        self.assertEqual(len(optimizer["route_matrix"]), 35)
        self.assertEqual(len(optimizer["calibration_evidence"]), 11)
        self.assertFalse(optimizer["complete_portfolio_optimization_available"])
        self.assertEqual(
            optimizer["complete_portfolio_blockers"],
            [
                "ramare-zuniga-lemma-6-2",
                "helfgott-platt-goldbach-gpu-v1",
                "platt-dirichlet-theorem-7-1",
                "ternary-goldbach-finite-below-10pow27-v1",
            ],
        )
        for row in optimizer["route_matrix"]:
            if row["optimizer_eligible"]:
                self.assertEqual(row["readiness"], "eligible")
                self.assertTrue(all(item["calibrated"] for item in row["demands"]))
            if row["readiness"] == "sensitivity_only":
                self.assertFalse(row["optimizer_eligible"])
                self.assertIsNotNone(row["cost_usd"])
        mixed = optimizer["configuration_comparison"]["mixed_flexible"]
        self.assertFalse(mixed["pay_as_you_go"]["available"])
        self.assertIsNone(
            mixed["pay_as_you_go"]["optimized_complete_portfolio_cost_usd"]
        )
        self.assertEqual(mixed["pay_as_you_go"]["covered_campaign_count"], 7)
        self.assertFalse(
            optimizer["selection_policy"]["sensitivity_only_routes_selected"]
        )
        affine = next(
            row
            for row in optimizer["route_matrix"]
            if row["route_id"]
            == "hurst-four-residuals-v1:dc96-affine-one-pass-sensitivity"
        )
        self.assertEqual(affine["readiness"], "sensitivity_only")
        self.assertFalse(affine["optimizer_eligible"])
        self.assertTrue(affine["demands"][0]["calibrated"])
        h100_affine = next(
            row
            for row in optimizer["route_matrix"]
            if row["route_id"]
            == (
                "hurst-four-residuals-v1:"
                "h100-eight-worker-affine-gb10-sensitivity"
            )
        )
        self.assertEqual(h100_affine["readiness"], "sensitivity_only")
        self.assertFalse(h100_affine["optimizer_eligible"])
        self.assertEqual(
            h100_affine["demands"][0]["node_hours_low"],
            "432.9670873983739837398373984",
        )
        self.assertEqual(h100_affine["demands"][0]["default_nodes"], 8)
        self.assertEqual(h100_affine["demands"][0]["parallelism_cap"], 8)
        self.assertFalse(h100_affine["demands"][0]["calibrated"])
        self.assertFalse(h100_affine["demands"][0]["target_sku_measured"])
        self.assertEqual(
            h100_affine["schedule"]["branches"][0]["nodes_required"],
            {"low_work": 8, "high_work": 8},
        )
        self.assertEqual(
            Decimal(
                h100_affine["schedule"]["ideal_route_wall_hours"]["high"]
            ),
            Decimal("54.1208859247967479674796748"),
        )
        self.assertEqual(
            h100_affine["cost_usd"],
            {
                "pay_as_you_go": {"low": "3022.11", "high": "3022.11"},
                "spot": {"low": "614.40", "high": "614.40"},
            },
        )
        self.assertTrue(
            h100_affine["production_gate"]["time_budget_feasible"]
        )
        self.assertEqual(
            h100_affine["production_gate"]["blockers"],
            [
                "route_not_source_closed_and_calibrated",
                "target_sku_not_measured",
            ],
        )
        self.assertFalse(
            h100_affine["production_gate"]["production_ready"][
                "pay_as_you_go"
            ]
        )
        hurst_evidence = next(
            row
            for row in optimizer["calibration_evidence"]
            if row["campaign_id"] == "hurst-four-residuals-v1"
        )
        self.assertEqual(
            hurst_evidence["h100_affine_sensitivity"]["measurement"][
                "complete_device_work_milliseconds"
            ],
            "191.737",
        )
        self.assertFalse(
            hurst_evidence["h100_affine_sensitivity"][
                "production_gate"
            ]["complete_hybrid_campaign_eta_available"]
        )
        r2star = next(
            row
            for row in optimizer["route_matrix"]
            if row["route_id"]
            == "ramare-zuniga-lemma-6-2:h100-sensitivity"
        )
        self.assertEqual(r2star["readiness"], "sensitivity_only")
        self.assertEqual(
            r2star["demands"][0]["parallelism_cap"],
            1,
        )
        self.assertEqual(
            (
                r2star["demands"][0]["node_hours_low"],
                r2star["demands"][0]["node_hours_high"],
            ),
            ("1", "8"),
        )
        self.assertFalse(r2star["demands"][0]["target_sku_measured"])
        r2star_cpu = next(
            row
            for row in optimizer["route_matrix"]
            if row["route_id"] == "ramare-zuniga-lemma-6-2:cpu_only"
        )
        self.assertIn(
            "checker",
            r2star_cpu["unavailable_reason"],
        )
        cdem_evidence = next(
            row
            for row in optimizer["calibration_evidence"]
            if row["campaign_id"] == "cdem-table-abel"
        )
        self.assertEqual(
            cdem_evidence["transcript_sha256"],
            "2a1d551dee2f5e8997e8e2a77a587cb6cf53b93b32854f943591163db2460123",
        )
        self.assertEqual(
            cdem_evidence["scope"],
            "full_source_local_aarch64_not_azure_attestation",
        )
        cdem = next(
            row
            for row in optimizer["route_matrix"]
            if row["route_id"] == "cdem-table-abel:dc96-cpu"
        )
        self.assertEqual(
            cdem["demands"][0]["evidence_id"],
            "cdem-table-abel-full-run-20260723",
        )
        self.assertFalse(cdem["demands"][0]["target_sku_measured"])
        self.assertFalse(
            cdem["production_gate"]["production_ready"]["pay_as_you_go"]
        )

    def test_backend_optimizer_applies_deadline_to_high_work_endpoint(self) -> None:
        optimizer = build_sizing_report(
            deadline_hours=Decimal("8766"),
            max_cpu_nodes=64,
            max_h100_nodes=8,
        )["backend_optimizer"]
        zeta_cpu = next(
            row
            for row in optimizer["route_matrix"]
            if row["route_id"] == "platt-trudgian-rh-3e12:dc96-cpu"
        )
        self.assertTrue(zeta_cpu["deadline_feasible"])
        self.assertEqual(
            zeta_cpu["schedule"]["branches"][0]["nodes_required"],
            {"low_work": 45, "high_work": 45},
        )
        zeta_ncc = next(
            row
            for row in optimizer["route_matrix"]
            if row["route_id"] == "platt-trudgian-rh-3e12:ncc-host-cpu"
        )
        self.assertFalse(zeta_ncc["deadline_feasible"])
        h100_only = optimizer["configuration_comparison"]["h100_only"]
        self.assertIn(
            "platt-trudgian-rh-3e12",
            [
                item["campaign_id"]
                for item in h100_only["pay_as_you_go"]["blockers"]
            ],
        )

    def test_optimizer_rejects_eligible_route_with_uncalibrated_demand(self) -> None:
        campaign = "campaign"
        bad = CampaignRoute(
            campaign,
            "bad",
            "cpu_only",
            "eligible",
            (
                ResourceDemand(
                    "dc96_cpu",
                    Decimal("1"),
                    Decimal("2"),
                    1,
                    1,
                    "missing-target-pilot",
                    False,
                    "uncalibrated",
                    False,
                    "guessed work",
                ),
            ),
            "must be rejected",
        )
        unavailable = (
            CampaignRoute(
                campaign,
                "h100-missing",
                "h100_only",
                "unavailable",
                (),
                "missing",
                "missing",
            ),
            CampaignRoute(
                campaign,
                "mixed-missing",
                "mixed",
                "unavailable",
                (),
                "missing",
                "missing",
            ),
        )
        with self.assertRaisesRegex(BackendOptimizationError, "uncalibrated"):
            optimize_backend_catalog(
                physical_campaign_ids=(campaign,),
                routes=(bad, *unavailable),
                h100_prices={
                    "pay_as_you_go": Decimal("2"),
                    "spot": Decimal("1"),
                },
                cpu_prices={
                    "pay_as_you_go": Decimal("1"),
                    "spot": Decimal("0.5"),
                },
            )

    def test_production_gate_is_hard_capped_at_one_week_and_ten_thousand(self) -> None:
        optimizer = build_sizing_report()["backend_optimizer"]
        self.assertEqual(
            optimizer["production_budget"],
            {
                "hard_max_wall_hours": "168",
                "hard_max_cost_usd": "10000",
                "limits_may_only_be_tightened": True,
                "route_readiness_field": "route_matrix[].production_gate.production_ready",
                "high_endpoints_control": True,
            },
        )
        zeta = next(
            row
            for row in optimizer["route_matrix"]
            if row["route_id"] == "platt-trudgian-rh-3e12:dc96-cpu"
        )
        self.assertFalse(zeta["production_gate"]["time_budget_feasible"])
        self.assertFalse(
            zeta["production_gate"]["budget_feasible"]["pay_as_you_go"]
        )
        self.assertFalse(
            zeta["production_gate"]["production_ready"]["spot"]
        )
        mixed = optimizer["configuration_comparison"]["mixed_flexible"]
        self.assertFalse(
            mixed["pay_as_you_go"]["production_gate"]["production_ready"]
        )

    def test_small_measured_route_can_pass_but_limits_cannot_be_relaxed(self) -> None:
        campaign = "small"
        measured = CampaignRoute(
            campaign,
            "small:cpu",
            "cpu_only",
            "eligible",
            (
                ResourceDemand(
                    "dc96_cpu",
                    Decimal("1"),
                    Decimal("2"),
                    1,
                    1,
                    "full-run",
                    True,
                    "full_source",
                    True,
                    "complete target measurement",
                ),
            ),
            "complete route",
        )
        unavailable = (
            CampaignRoute(campaign, "small:h100", "h100_only", "unavailable", (), "missing", "missing"),
            CampaignRoute(campaign, "small:mixed", "mixed", "unavailable", (), "missing", "missing"),
        )
        kwargs = {
            "physical_campaign_ids": (campaign,),
            "routes": (measured, *unavailable),
            "h100_prices": {
                "pay_as_you_go": Decimal("2"),
                "spot": Decimal("1"),
            },
            "cpu_prices": {
                "pay_as_you_go": Decimal("1"),
                "spot": Decimal("0.5"),
            },
        }
        report = optimize_backend_catalog(**kwargs)
        row = report["route_matrix"][0]
        self.assertTrue(
            row["production_gate"]["production_ready"]["pay_as_you_go"]
        )
        self.assertTrue(
            report["configuration_comparison"]["cpu_only"]["pay_as_you_go"]
            ["production_gate"]["production_ready"]
        )
        with self.assertRaisesRegex(BackendOptimizationError, "at most 168"):
            optimize_backend_catalog(
                **kwargs, production_max_wall_hours=Decimal("169")
            )
        with self.assertRaisesRegex(BackendOptimizationError, "at most 10000"):
            optimize_backend_catalog(
                **kwargs, production_max_cost_usd=Decimal("10001")
            )

    def test_production_cost_gate_uses_unrounded_high_endpoint(self) -> None:
        campaign = "rounding-boundary"
        route = CampaignRoute(
            campaign,
            "rounding-boundary:cpu",
            "cpu_only",
            "eligible",
            (
                ResourceDemand(
                    "dc96_cpu",
                    Decimal("10000.004"),
                    Decimal("10000.004"),
                    64,
                    64,
                    "exact-cost-boundary",
                    True,
                    "full_source",
                    True,
                    "exact cost is just above the hard cap",
                ),
            ),
            "the display rounds to 10000.00 but the gate must reject it",
        )
        unavailable = (
            CampaignRoute(campaign, "rounding-boundary:h100", "h100_only", "unavailable", (), "missing", "missing"),
            CampaignRoute(campaign, "rounding-boundary:mixed", "mixed", "unavailable", (), "missing", "missing"),
        )
        report = optimize_backend_catalog(
            physical_campaign_ids=(campaign,),
            routes=(route, *unavailable),
            h100_prices={
                "pay_as_you_go": Decimal("1"),
                "spot": Decimal("1"),
            },
            cpu_prices={
                "pay_as_you_go": Decimal("1"),
                "spot": Decimal("1"),
            },
        )
        row = report["route_matrix"][0]
        self.assertEqual(row["cost_usd"]["pay_as_you_go"]["high"], "10000.00")
        self.assertEqual(
            row["production_gate"]["high_cost_usd_unrounded"]["pay_as_you_go"],
            "10000.004",
        )
        self.assertFalse(
            row["production_gate"]["budget_feasible"]["pay_as_you_go"]
        )
        self.assertIn(
            "high_cost_endpoint_exceeds_cost_limit",
            row["production_gate"]["blockers_by_price"]["pay_as_you_go"],
        )

    def test_dominant_campaign_review_refuses_partial_public_artifacts(self) -> None:
        review = build_sizing_report()["dominant_campaign_budget_review"]
        self.assertEqual(
            review["hard_limits"],
            {
                "wall_hours": "168",
                "cost_usd": "10000",
                "high_endpoints_control": True,
            },
        )
        self.assertEqual(
            set(review["campaigns"]),
            {
                "platt-trudgian-rh-3e12",
                "helfgott-platt-goldbach-gpu-v1",
                "platt-dirichlet-theorem-7-1",
                "ternary-goldbach-finite-below-10pow27-v1",
            },
        )
        zeta = review["campaigns"]["platt-trudgian-rh-3e12"]
        self.assertEqual(
            zeta["claim_scope"]["multiplicity_counted_zeros"],
            12_363_153_437_138,
        )
        self.assertEqual(zeta["artifact_replay"]["status"], "insufficient_scope")
        self.assertFalse(
            zeta["artifact_replay"]["bounded_or_partial_artifact_can_promote"]
        )
        goldbach = review["campaigns"]["helfgott-platt-goldbach-gpu-v1"]
        self.assertEqual(
            goldbach["artifact_replay"]["status"],
            "aggregate_status_not_replay_certificate",
        )
        handoff = goldbach["analytic_10pow27_handoff"]
        self.assertEqual(
            handoff["status"],
            "implemented_unrun_h100_calibration_required",
        )
        self.assertEqual(handoff["binary_even_count"], "15624999999999999")
        self.assertEqual(handoff["ladder_range_count"], 7_106)
        self.assertFalse(handoff["h100_calibration_passed"])
        lowered = review["campaigns"][
            "ternary-goldbach-finite-below-10pow27-v1"
        ]
        self.assertTrue(lowered["fresh_compute"]["source_closed"])
        self.assertTrue(
            lowered["fresh_compute"]["measured_job_factories_complete"]
        )
        self.assertFalse(lowered["fresh_compute"]["production_receipts_present"])
        dirichlet = review["campaigns"]["platt-dirichlet-theorem-7-1"]
        self.assertFalse(dirichlet["fresh_compute"]["source_closed"])
        self.assertEqual(
            dirichlet["claim_scope"]["primitive_character_count"],
            29_565_923_837,
        )
        self.assertEqual(
            review["all_three_production_ready"],
            {"pay_as_you_go": False, "spot": False},
        )

    def test_report_covers_all_atoms_and_refuses_complete_eta(self) -> None:
        report = build_sizing_report()
        self.assertEqual(
            tuple(row["atom_id"] for row in report["campaigns"]), ATOM_IDS
        )
        self.assertFalse(report["complete_portfolio_prediction_available"])
        self.assertEqual(
            report["optimized_engine_blockers"],
            ["platt-dirichlet-theorem-7-1"],
        )
        envelopes = report["planning_envelopes"]
        practical = envelopes["practical_10_logical_atoms"]
        self.assertEqual(
            practical["optimistic_cpu_gpu_overlap_wall_hours"],
            {"low": "48", "high": "528"},
        )
        self.assertEqual(
            practical["serialized_on_one_eight_node_pool_wall_hours"],
            {"low": "50.1204", "high": "541.441"},
        )
        self.assertEqual(
            practical["shared_campaign_aliases"]["mertens-hurst"],
            [
                "cdem-squarefree",
                "platt-little-mertens-2-11",
                "platt-little-mertens-stronger",
            ],
        )
        zeta = envelopes["literal_zeta_rh_campaign_alone"]
        self.assertEqual(zeta["literal_flint_process_hours"], "37580948")
        self.assertEqual(
            Decimal(zeta["four_dc96as_v6_wall_hours"]),
            Decimal("37580948") / Decimal(384),
        )
        goldbach = envelopes["goldbach_binary_h100_sensitivity"]
        self.assertEqual(goldbach["benchmark"]["sample_even_count"], "600000000")
        self.assertEqual(goldbach["benchmark"]["sample_seconds_median"], "0.779701")
        self.assertEqual(goldbach["production_checkpoint_leaf_count"], 65_536)
        self.assertEqual(
            [row["equal_throughput_factor_vs_measured_gpu"] for row in goldbach["rows"]],
            ["1", "2", "5", "10", "14.3"],
        )
        self.assertEqual(goldbach["benchmark"]["production_profile"], "analytic_10pow27")
        self.assertEqual(goldbach["rows"][0]["cluster_wall_hours"], "705.024775752315")
        self.assertEqual(goldbach["rows"][-1]["cluster_wall_hours"], "49.302431870791")
        self.assertFalse(goldbach["calibration_gate"]["passed"])
        historical_goldbach = envelopes["goldbach_historical_source_comparison"]
        self.assertEqual(
            historical_goldbach["rows"][0]["cluster_wall_hours"],
            "90243.171296296296",
        )
        self.assertEqual(
            historical_goldbach["rows"][-1]["cluster_wall_hours"],
            "6310.711279461279",
        )
        ladder = envelopes["goldbach_prime_ladder_cpu_boundary"]
        self.assertEqual(ladder["range_count"], 7_106)
        self.assertEqual(
            ladder["models"]["paper_report_scaled_by_range_count"]["core_hours"],
            "576.9027805967119951288816724",
        )
        hurst_affine = envelopes["hurst_affine_guard_alternative"]
        self.assertTrue(
            hurst_affine["retained_benchmarks"][
                "byte_semantic_receipts_equal_after_elapsed_time_removed"
            ]
        )
        self.assertGreater(
            Decimal(hurst_affine["ideal_four_dc96as_v6_wall_hours"]["low"]),
            Decimal("7990"),
        )
        self.assertLess(
            Decimal(hurst_affine["ideal_four_dc96as_v6_wall_hours"]["high"]),
            Decimal("8250"),
        )
        self.assertFalse(hurst_affine["production_two_pass_route_replaced"])
        self.assertTrue(
            hurst_affine["one_pass_campaign_schema_and_replay_implemented"]
        )
        self.assertFalse(hurst_affine["included_in_practical_or_portfolio_totals"])
        hurst_h100 = envelopes[
            "hurst_h100_affine_eight_worker_sensitivity"
        ]
        self.assertEqual(
            hurst_h100["measurement"][
                "complete_device_work_milliseconds"
            ],
            "191.737",
        )
        self.assertEqual(
            hurst_h100["exact_affine_composition"]["worker_count"],
            8,
        )
        self.assertEqual(
            hurst_h100["exact_affine_composition"]["algorithm"],
            "hurst-h100-eight-way-independent-affine-scan-v1",
        )
        self.assertEqual(
            Decimal(
                hurst_h100["h100_sensitivity"][
                    "eight_worker_wall_hours"
                ]
            ),
            Decimal("54.1208859247967479674796748"),
        )
        self.assertEqual(
            hurst_h100["eight_ncc_compute_cost_usd"],
            {
                "pay_as_you_go": {"low": "3022.11", "high": "3022.11"},
                "spot": {"low": "614.40", "high": "614.40"},
            },
        )
        self.assertFalse(
            hurst_h100["h100_sensitivity"]["target_h100_measured"]
        )
        self.assertEqual(
            hurst_h100["projection_scope"],
            "terminal_h100_stage_only",
        )
        self.assertFalse(
            hurst_h100["complete_hybrid_campaign_eta_available"]
        )
        self.assertFalse(hurst_h100["production_ready"])
        self.assertEqual(
            len(envelopes["conditional_known_work_before_dirichlet"]["rows"]),
            5,
        )
        procurement = envelopes["procurement_working_band_before_dirichlet"]
        self.assertEqual(
            [row["goldbach_equal_throughput_factor_vs_gb10"] for row in procurement["rows"]],
            ["2", "5"],
        )
        self.assertEqual(
            [row["balanced_dc96as_v6_nodes"] for row in procurement["rows"]],
            [1111, 2777],
        )
        self.assertIn("not_complete_portfolio_eta", procurement["classification"])
        component_band = envelopes[
            "conditional_all13_component_engineering_sensitivity"
        ]
        self.assertEqual(len(component_band["rows"]), 5)
        self.assertIn(
            "not_complete_portfolio_eta", component_band["classification"]
        )
        self.assertGreater(
            Decimal(component_band["dirichlet_literal_cpu_reference_serial_wall_hours"]),
            Decimal("6000"),
        )
        self.assertLess(
            Decimal(component_band["dirichlet_literal_cpu_reference_serial_wall_hours"]),
            Decimal("6100"),
        )
        self.assertFalse(envelopes["all_13_logical_atoms"]["available"])
        self.assertTrue(
            envelopes["dirichlet_grh_boundary"][
                "optimized_all_character_engine_available"
            ]
        )
        self.assertFalse(
            envelopes["dirichlet_grh_boundary"][
                "optimized_end_to_end_pipeline_available"
            ]
        )
        self.assertEqual(
            envelopes["dirichlet_grh_boundary"][
                "large_q_all_character_transform"
            ]["batch64_butterflies"],
            "15334965882246056",
        )
        self.assertIn("not_execution", report["classification"])

    def test_dirichlet_revision_has_exact_work_and_honest_boundaries(self) -> None:
        report = build_sizing_report()
        envelopes = report["planning_envelopes"]
        boundary = envelopes["dirichlet_grh_boundary"]
        allchars = allchars_source_work()
        tmajor = tmajor_source_projection()
        self.assertEqual(
            boundary["large_q_all_character_transform"]["batch64_butterflies"],
            str(allchars["batched_radix2_butterflies"]),
        )
        self.assertEqual(
            boundary["large_q_all_character_transform"]["batch64_invocations"],
            str(allchars["batch_invocations"]),
        )
        self.assertEqual(
            boundary["large_q_residue_composition"]["residue_compositions"],
            str(allchars["input_group_values"]),
        )
        self.assertEqual(
            boundary["large_q_seeded_fused_batch_current"][
                "direct_t_major_cuda_input_bytes"
            ],
            str(tmajor["input_bytes"]["total"]),
        )
        component_rows = boundary["quantified_component_rows"]
        self.assertEqual(
            [row["component_id"] for row in component_rows],
            [
                "large-q-all-character-framed-transform",
                "large-q-persistent-residue-composition",
                "large-q-fused-certified-box-batch-alternative",
                "large-q-root-additive-input",
                "large-q-root-primitive-normalization",
                "large-q-root-all-character-transform",
                "small-q-v3-factored-cuda-finite-plus-dft",
                "small-q-v3-independent-factored-family-replay",
            ],
        )
        self.assertEqual(
            [row["source_work"] for row in component_rows],
            [
                "15334965882246056",
                "266697737764848",
                "266697737764848",
                "40503165302",
                "29547446729",
                "2645418549056",
                "1238529267288000",
                "49174802484",
            ],
        )
        self.assertFalse(component_rows[6]["source_work_is_exact"])
        self.assertFalse(component_rows[-1]["producer_generation_included"])

        fused = boundary["large_q_fused_certified_box_batch_alternative"]
        self.assertEqual(
            fused["arithmetic_roster_version"],
            "primitive-dirichlet-moduli-q-mod-4-ne-2-v2",
        )
        self.assertIn(
            "legacy-v1",
            fused["literal_certified_input_boundary_roster_version"],
        )
        self.assertEqual(fused["old_one_ordinate_jobs"], "3637613167")
        self.assertEqual(fused["fused_batch_invocations"], "56981100")
        self.assertEqual(
            fused["fused_taylor_and_composition_values"], "266697737764848"
        )
        self.assertEqual(
            fused["literal_certified_input_boundary"],
            {
                "repeated_hurwitz_lattice_bytes": "5139124740685824",
                "tail_plus_finite_recovery_box_bytes": "13083568251320320",
                "total_bytes_including_descriptors_factors_and_headers": (
                    "18263933424590240"
                ),
            },
        )
        self.assertGreater(
            Decimal(fused["ideal_eight_equal_gb10_wall_hours"]),
            Decimal("135"),
        )
        self.assertLess(
            Decimal(fused["ideal_eight_equal_gb10_wall_hours"]),
            Decimal("136"),
        )
        self.assertFalse(fused["included_in_component_revision_totals"])
        self.assertFalse(fused["source_performance_ready"])
        self.assertFalse(fused["h100_measurement_available"])

        seeded = boundary["large_q_seeded_fused_batch_current"]
        self.assertIn(
            "legacy-v1", seeded["logical_input_boundary_roster_version"]
        )
        self.assertEqual(
            seeded["direct_t_major_roster_version"],
            "primitive-dirichlet-moduli-q-mod-4-ne-2-v2",
        )
        self.assertEqual(
            seeded["retained_gb10_benchmark"]["measured_values_per_second"],
            "19424914",
        )
        self.assertTrue(
            seeded["retained_gb10_benchmark"][
                "includes_directed_finite_recovery_recurrence"
            ]
        )
        self.assertEqual(seeded["logical_input_boundary_bytes"], "5180404381680112")
        self.assertEqual(seeded["finite_recovery_seed_artifact_bytes"], "96008016")
        self.assertGreater(
            Decimal(seeded["ideal_eight_equal_gb10_wall_hours"]),
            Decimal("476"),
        )
        self.assertLess(
            Decimal(seeded["ideal_eight_equal_gb10_wall_hours"]),
            Decimal("477"),
        )
        self.assertTrue(
            seeded["full_seed_generation_and_320_bit_replay_completed_locally"]
        )
        self.assertTrue(
            seeded["t_major_hurwitz_lattice_cache_contract_implemented"]
        )
        self.assertTrue(
            seeded["t_major_hurwitz_lattice_replay_repacker_implemented"]
        )
        self.assertEqual(
            seeded["t_major_hurwitz_lattice_payload_bytes"], "134205145088"
        )
        self.assertEqual(
            seeded["t_major_compact_total_input_bytes"], "41413846139376"
        )
        self.assertTrue(
            seeded["t_major_hurwitz_lattice_cache_broadcast_implemented"]
        )
        self.assertEqual(
            seeded["direct_t_major_cuda_input_bytes"], "286556459000"
        )
        self.assertTrue(
            seeded["t_major_typed_bundle_admission_adapter_implemented"]
        )
        self.assertTrue(
            seeded[
                "typed_bundle_lattice_payload_to_cache_row_binding_implemented"
            ]
        )
        self.assertFalse(seeded["source_performance_ready"])
        self.assertFalse(seeded["h100_measurement_available"])

        framed = boundary["large_q_all_character_transform"][
            "persistent_framed_service"
        ]
        self.assertTrue(framed["implemented"])
        self.assertEqual(
            framed["legacy_rolling_child_process_launches_avoided"],
            "113962200",
        )
        self.assertFalse(framed["arithmetic_projection_changed"])
        self.assertTrue(framed["component_process_graph_wired"])
        self.assertFalse(framed["full_source_supervisor_wired"])

        small = boundary["small_q_factored_disk_dft_v3"]
        self.assertEqual(
            small["legacy_v2_character_frequency_seeds"],
            "7078844301312",
        )
        self.assertEqual(
            small["factored_v3_shared_frequency_records"], "16385441792"
        )
        self.assertEqual(
            small["factored_v3_minimum_logical_bytes"], "2459841190828"
        )
        self.assertEqual(
            small["factored_v3_service_physical_bytes"], "2459842579084"
        )
        self.assertEqual(small["factored_v3_service_batch_count"], "8971")
        self.assertEqual(
            small["literal_service_output_bytes"], "339784527970104"
        )
        self.assertEqual(
            small["source_sample_only_service_output_bytes"],
            "226995959255448",
        )
        self.assertTrue(small["streaming_integrity_reducer"]["implemented"])
        self.assertEqual(
            small["streaming_integrity_reducer"]["persistent_raw_output_bytes"],
            "0",
        )
        single_stream_hours = Decimal(
            small["streaming_integrity_reducer"][
                "single_stream_reduced_output_projection_hours"
            ]
        )
        eight_stream_hours = Decimal(
            small["streaming_integrity_reducer"][
                "ideal_eight_independent_stream_projection_hours"
            ]
        )
        self.assertGreater(single_stream_hours, Decimal("41"))
        self.assertLess(single_stream_hours, Decimal("42"))
        self.assertEqual(eight_stream_hours * 8, single_stream_hours)
        self.assertFalse(
            small["streaming_integrity_reducer"]["eight_stream_scaling_measured"]
        )
        compact = small["source_streaming_compact_v3"]
        self.assertTrue(compact["implemented"])
        self.assertFalse(compact["raw_disk_stream_persisted"])
        self.assertFalse(compact["packed_sign_family_persisted"])
        self.assertEqual(compact["primitive_character_count"], 29_547_446_729)
        self.assertEqual(
            compact["primitive_character_sample_count"],
            191_701_043_433_012,
        )
        self.assertEqual(
            compact["final_dense_byte_floor_without_q_or_page_padding"],
            62_259_950_420,
        )
        self.assertEqual(
            compact[
                "final_canonical_wire_bytes_without_ambiguity_ranges"
            ],
            62_968_524_843,
        )
        self.assertEqual(
            compact["eight_lane_dense_byte_floor_total"],
            313_234_007_491,
        )
        self.assertEqual(
            compact[
                "eight_lane_canonical_wire_byte_total_without_ambiguity_ranges"
            ],
            317_542_970_540,
        )
        self.assertFalse(compact["ambiguity_density_measured"])
        self.assertFalse(compact["source_scale_storage_admitted"])
        self.assertGreater(
            Decimal(small["payload_reduction_ratio"]), Decimal("253")
        )
        self.assertGreater(
            Decimal(small["seed_cardinality_reduction_ratio"]), Decimal("432")
        )
        self.assertEqual(small["independent_family_work"], "49174802484")
        self.assertEqual(
            small["retained_q997_factored_seed_benchmark"][
                "independent_checker_seconds"
            ],
            "3.272058564",
        )
        retained_rate = Decimal(
            small["retained_q997_factored_seed_benchmark"][
                "independent_checker_families_per_second"
            ]
        )
        source_rate = Decimal(
            small["source_parameter_q997_service_benchmark"][
                "independent_checker_families_per_second"
            ]
        )
        self.assertGreater(retained_rate, Decimal("60091"))
        self.assertLess(retained_rate, Decimal("60092"))
        self.assertGreater(source_rate, Decimal("49794"))
        self.assertLess(source_rate, Decimal("49795"))
        self.assertEqual(
            small["retained_q997_factored_cuda_benchmark"][
                "finite_plus_dft_seconds"
            ],
            "0.014160607",
        )
        self.assertEqual(
            small["source_parameter_q997_service_benchmark"][
                "independent_checker_seconds"
            ],
            "126.369121963",
        )
        replay_hours = Decimal(
            small["independent_checker_source_projection"][
                "ideal_four_dc96as_v6_wall_hours"
            ]
        )
        self.assertGreater(replay_hours, Decimal("0.71"))
        self.assertLess(replay_hours, Decimal("0.72"))
        self.assertTrue(small["factored_cuda_consumer_implemented"])
        self.assertTrue(small["q_persistent_source_service_implemented"])
        self.assertTrue(small["compact_downstream_reducer_implemented"])
        self.assertTrue(small["semantic_time_tail_sign_reducer_implemented"])
        self.assertEqual(
            small["semantic_time_tail_control_records"], "8116121626"
        )
        self.assertEqual(
            small["semantic_time_tail_control_bytes"], "129858785904"
        )
        self.assertEqual(
            small["semantic_two_bit_sign_artifact_bytes"], "1182271755191"
        )
        self.assertFalse(small["semantic_reducer_cuda_fused"])
        self.assertFalse(
            small["semantic_reducer_multiplicity_inference_performed"]
        )
        self.assertFalse(small["source_wide_post_dft_width_usefulness_proved"])
        self.assertFalse(small["external_atom_discharged"])

        v2 = boundary["small_q_certified_disk_dft_v2"]
        self.assertFalse(v2["active_component_model"])
        self.assertEqual(v2["superseded_by"], "small_q_factored_disk_dft_v3")
        self.assertEqual(v2["minimum_seed_payload_bytes"], "622938298515456")
        self.assertGreater(
            Decimal(
                v2["independent_arb_seed_replay"][
                    "ideal_four_dc96as_v6_wall_hours"
                ]
            ),
            Decimal("151"),
        )

        composition = boundary["large_q_residue_composition"]
        self.assertEqual(composition["residue_compositions"], "266697737764848")
        self.assertEqual(composition["batch64_invocations"], "56981100")
        self.assertEqual(
            composition["materialized_transform_input_bytes_avoided_by_streaming"],
            "10466854601056256",
        )
        self.assertTrue(composition["persistent_framed_producer_ready"])
        self.assertFalse(composition["source_scale_performance_validated"])

        root = boundary["large_q_root_number_stage"]
        self.assertEqual(root["active_moduli"], "292500")
        self.assertEqual(root["unit_group_input_rectangles"], "40503165302")
        self.assertEqual(root["primitive_root_records"], "29547446729")
        self.assertEqual(root["radix2_butterflies"], "2645418549056")
        self.assertEqual(root["unstreamed_root_bytes"], "945546375328")
        self.assertTrue(root["persistent_bounded_protocol_ready"])
        self.assertTrue(root["consumer_artifact_integration_ready"])
        self.assertFalse(root["source_performance_ready"])
        self.assertIn("not_h100_measurement", root["classification"])

        revision = envelopes["conditional_all13_component_engineering_sensitivity"][
            "dirichlet_component_model_revision"
        ]
        before = revision["before_certified_v2_and_stream_components"]
        after_v2 = revision["after_certified_v2_and_stream_components"]
        after = revision["after_factored_v3_and_stream_components"]
        fused_alternative = revision["alternative_fused_large_q_arithmetic"]
        self.assertFalse(
            fused_alternative["substituted_into_before_or_after_totals"]
        )
        self.assertEqual(
            fused_alternative["literal_certified_input_bytes"],
            "18263933424590240",
        )
        self.assertGreater(
            Decimal(before["cpu_384_core_serial_wall_hours"]["low"]),
            Decimal("25900"),
        )
        self.assertLess(
            Decimal(after["cpu_384_core_serial_wall_hours"]["high"]),
            Decimal("18700"),
        )
        self.assertGreater(
            Decimal(after["gpu_8_device_five_to_ten_x_sensitivity_wall_hours"]["low"]),
            Decimal("122"),
        )
        self.assertEqual(
            after_v2["compute_cost_usd"]["pay_as_you_go"],
            {"low": "115116.57", "high": "119578.92"},
        )
        self.assertEqual(
            after_v2["active_component_model"], False
        )
        self.assertEqual(
            after_v2["classification"],
            "superseded_v2_conditional_component_model_for_comparison_only",
        )
        self.assertEqual(
            after["compute_cost_usd"]["pay_as_you_go"],
            {"low": "112396.91", "high": "116772.26"},
        )
        self.assertEqual(
            after["conditional_compute_cost_reduction_vs_before_usd"]["spot"],
            {"low": "63225.95", "high": "64732.75"},
        )
        self.assertEqual(
            revision["after_certified_v2_and_stream_components"][
                "compute_cost_usd"
            ]["spot"],
            {"low": "21418.24", "high": "22319.83"},
        )
        self.assertEqual(
            after_v2.get("conditional_compute_cost_reduction_vs_before_usd"),
            None,
        )
        self.assertTrue(after["active_component_model"])
        self.assertIn(
            "v2", revision["comparison_scope"]
        )
        self.assertEqual(
            revision["after_factored_v3_and_stream_components"][
                "conditional_compute_cost_reduction_vs_v2_usd"
            ]["spot"],
            {"low": "-379.70", "high": "1405.79"},
        )
        factor8 = boundary["routine_factor8_postprocess"]
        self.assertEqual(
            factor8["factor8_target_grid_samples"], "1571337544104271"
        )
        self.assertEqual(
            factor8["nonaligned_interpolated_targets"], "1374907418218169"
        )
        self.assertEqual(
            factor8["forty_tap_interval_products"], "54996296728726760"
        )
        self.assertEqual(
            factor8["retained_gb10_benchmark"][
                "signed_coefficient_fused_median_target_samples_per_second"
            ],
            "350576167.565935",
        )
        self.assertIn(
            "dimensionally_invalid",
            factor8["retired_cpu_sensitivity"]["classification"],
        )
        self.assertFalse(factor8["h100_measurement_available"])
        self.assertFalse(factor8["production_ready"])
        self.assertFalse(factor8["external_atom_discharged"])
        self.assertFalse(envelopes["all_13_logical_atoms"]["available"])

    def test_price_costs_are_eight_node_products(self) -> None:
        report = build_sizing_report(
            prices={"pay_as_you_go": Decimal("2"), "spot": Decimal("1")},
            cpu_prices={"pay_as_you_go": Decimal("1"), "spot": Decimal("0.5")},
        )
        costs = report["cost_formula"]
        self.assertEqual(costs["eight_node_usd_per_wall_hour"]["pay_as_you_go"], "16.00")
        self.assertEqual(costs["eight_node_usd_per_wall_day"]["spot"], "192.00")
        self.assertEqual(
            costs["four_cpu_node_usd_per_wall_hour"]["pay_as_you_go"],
            "4.00",
        )
        practical = report["planning_envelopes"]["practical_10_logical_atoms"]
        self.assertEqual(
            practical["optimistic_cpu_gpu_overlap_cost_usd"]["pay_as_you_go"],
            {"low": "768.00", "high": "8448.00"},
        )
        goldbach = report["planning_envelopes"][
            "goldbach_binary_h100_sensitivity"
        ]
        one_x_hours = Decimal(goldbach["rows"][0]["cluster_wall_hours"])
        self.assertEqual(
            goldbach["rows"][0]["eight_ncc_compute_cost_usd"][
                "pay_as_you_go"
            ],
            {
                "low": str((one_x_hours * 16).quantize(Decimal("0.01"))),
                "high": str((one_x_hours * 16).quantize(Decimal("0.01"))),
            },
        )

    def test_parse_prices_ignores_windows_devtest_and_low_priority(self) -> None:
        base = {
            "armSkuName": "Standard_NCC40ads_H100_v5",
            "armRegionName": "eastus2",
            "currencyCode": "USD",
            "type": "Consumption",
            "unitOfMeasure": "1 Hour",
            "productName": "Virtual Machines NCCadsv5 Srs",
            "effectiveStartDate": "2026-07-01T00:00:00Z",
        }
        items = [
            {**base, "skuName": "NCC40adsH100v5", "retailPrice": 6.98},
            {**base, "skuName": "NCC40adsH100v5 Spot", "retailPrice": 1.419034},
            {
                **base,
                "productName": "Virtual Machines NCCadsv5 Srs Win",
                "skuName": "NCC40adsH100v5",
                "retailPrice": 8.82,
            },
            {
                **base,
                "skuName": "NCC40adsH100v5 Low Priority",
                "retailPrice": 1.396,
            },
            {
                **base,
                "type": "DevTestConsumption",
                "skuName": "NCC40adsH100v5",
                "retailPrice": 1,
            },
        ]
        self.assertEqual(
            parse_retail_prices({"Items": items}),
            {"pay_as_you_go": Decimal("6.98"), "spot": Decimal("1.419034")},
        )

    def test_missing_price_class_fails_closed(self) -> None:
        with self.assertRaisesRegex(ProductionSizingError, "PAYG and spot"):
            parse_retail_prices({"Items": []})

    def test_cpu_sku_prices_are_parsed_separately(self) -> None:
        base = {
            "armSkuName": CPU_SKU,
            "armRegionName": "eastus2",
            "currencyCode": "USD",
            "type": "Consumption",
            "unitOfMeasure": "1 Hour",
            "productName": "Virtual Machines DCasv6 series",
            "effectiveStartDate": "2025-09-01T00:00:00Z",
        }
        self.assertEqual(
            parse_retail_prices(
                {
                    "Items": [
                        {**base, "skuName": "DC96asv6", "retailPrice": 4.358},
                        {
                            **base,
                            "skuName": "DC96asv6 Spot",
                            "retailPrice": 0.805358,
                        },
                    ]
                },
                sku=CPU_SKU,
            ),
            {
                "pay_as_you_go": Decimal("4.358"),
                "spot": Decimal("0.805358"),
            },
        )
        self.assertIn("Standard_DC96as_v6", retail_prices_url(CPU_SKU))


if __name__ == "__main__":
    unittest.main()
