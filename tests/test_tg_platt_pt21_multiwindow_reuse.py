# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "gpu/include/sparkinterval/tg_platt_dd_transform.hpp"
SOURCE = (
    ROOT
    / "reference/tg_platt_pt21_multiwindow_reuse_qualification.cu"
)
NEGATIVE_SUMMARY = (
    ROOT
    / "tests/fixtures/pt21_multiwindow_negative_qualification.json"
)
RUNNER_ENV = "TG_PLATT_PT21_MULTIWINDOW_REUSE"
STREAM_ENV = "TG_PLATT_PT21_MULTIWINDOW_STREAM"
STREAM_SHA_ENV = "TG_PLATT_PT21_MULTIWINDOW_STREAM_SHA256"
CENTER_ENV = "TG_PLATT_PT21_MULTIWINDOW_CENTER"
RESOLVER_SHA_ENV = "TG_PLATT_PT21_MULTIWINDOW_RESOLVER_SHA256"
FLINT_SHA_ENV = "TG_PLATT_PT21_MULTIWINDOW_FLINT_SHA256"
OWNED_DELTAS_ENV = "TG_PLATT_PT21_MULTIWINDOW_OWNED_DELTAS"


class PlattPT21MultiwindowReuseTest(unittest.TestCase):
    def _runner(self) -> Path:
        value = os.environ.get(RUNNER_ENV)
        if not value:
            self.skipTest(f"set {RUNNER_ENV} to run qualification KAT")
        runner = Path(value)
        if not runner.is_file():
            self.skipTest(f"multiwindow runner is missing: {runner}")
        return runner

    def test_contract_is_bounds_checked_and_nonproduction(self) -> None:
        header = HEADER.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        for token in (
            "kSourceBlockSampleShift = 24'576",
            "QualificationRequiredSampleView",
            "qualification_required_begin_for_delta",
            "device_qualification_required_samples",
        ):
            self.assertIn(token, header)
        for token in (
            "fixed_2176_bit_host_replay_complete",
            "release_performance_build",
            "finite_event_semantics_identity",
            "stationary_resolution_semantics_identity",
            "whole_pipeline_speedup_claimed",
            "hardy_z_endpoint_realization_proved",
            "source_claim_ready",
            "production_ready",
            "pt21_atom_discharged",
        ):
            self.assertIn(token, source)
        self.assertNotIn(
            "h100_tg_platt_fused_source_worker_v2.cu", source
        )

    def test_bounds_self_test_rejects_every_out_of_allocation_delta(
        self,
    ) -> None:
        completed = subprocess.run(
            [str(self._runner()), "--bounds-self-test"],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertTrue(result["test_success"])
        self.assertTrue(result["qualification_only"])
        self.assertEqual(result["sample_shift"], 24_576)
        self.assertEqual(result["required_count"], 25_741)
        self.assertEqual(result["accepted_deltas"], [-2, -1, 0, 1, 2])
        self.assertEqual(
            result["accepted_begins"],
            [3_514, 28_090, 52_666, 77_242, 101_818],
        )
        self.assertEqual(
            result["rejected_deltas"],
            [-3, 3, -(2**31), 2**31 - 1],
        )
        self.assertFalse(result["hardy_z_realization_proved"])
        self.assertFalse(result["source_claim_ready"])
        self.assertFalse(result["production_ready"])

    def test_curated_negative_summary_preserves_fail_closed_invariants(
        self,
    ) -> None:
        result = json.loads(NEGATIVE_SUMMARY.read_text(encoding="utf-8"))
        self.assertEqual(
            result["schema"],
            "sparkinterval.tg.platt-pt21-multiwindow-negative-"
            "qualification-summary.v1",
        )
        self.assertTrue(result["qualification_only"])
        self.assertTrue(result["measurement_artifact_not_certificate"])
        self.assertFalse(result["curation"]["raw_runner_output_included"])
        self.assertFalse(result["curation"]["source_streams_included"])
        self.assertFalse(result["curation"]["runner_binary_sha256_recorded"])

        profile = result["build_profile"]
        self.assertEqual(profile["cmake_build_config"], "Release")
        self.assertTrue(profile["ndebug_defined"])
        self.assertTrue(profile["release_performance_build"])
        self.assertEqual(profile["cuda_architecture"], "sm_121")

        lowercase_sha256 = re.compile(r"^[0-9a-f]{64}$")
        identities = result["identity_labels"]
        for key in ("resolver_sha256", "flint_sha256"):
            self.assertRegex(identities[key], lowercase_sha256)
        self.assertFalse(identities["resolver_sha256_self_verified"])
        self.assertFalse(identities["flint_sha256_self_verified"])
        self.assertTrue(
            identities["external_manifest_or_attestation_required"]
        )

        required = result["required_sample_count"]
        self.assertEqual(required, 25_741)
        runs = {run["name"]: run for run in result["runs"]}
        self.assertEqual(
            set(runs), {"interior-center-2", "terminal-residual-center"}
        )
        for run in runs.values():
            self.assertRegex(
                run["authenticated_stream_sha256"], lowercase_sha256
            )
            self.assertFalse(run["accepted"])
            self.assertEqual(run["process_exit_code"], 3)
            self.assertEqual(
                run["geometric_eligible_view_count"],
                sum(
                    not view["campaign_boundary_rejected"]
                    for view in run["views"]
                ),
            )
            owned = [
                view
                for view in run["views"]
                if not view["campaign_boundary_rejected"]
                and view["roster_owned"]
            ]
            self.assertEqual(run["roster_owned_view_count"], len(owned))
            self.assertAlmostEqual(
                run["measured_transform_invocation_reduction_fraction"],
                1.0 - 1.0 / len(owned),
            )
            self.assertTrue(
                math.isclose(
                    run["transform_only_ratio"],
                    len(owned),
                    rel_tol=0.01,
                )
            )
            for view in run["views"]:
                if view["campaign_boundary_rejected"]:
                    self.assertEqual(set(view), {
                        "delta", "campaign_boundary_rejected"
                    })
                    continue
                self.assertEqual(view["reuse_invalid_disks"], 0)
                self.assertEqual(view["ordinary_invalid_disks"], 0)
                self.assertEqual(view["ordinary_ambiguous_disks"], 0)
                self.assertTrue(view["ordinary_junction_accepted"])
                self.assertEqual(
                    view["reuse_certified_sign_count"]
                    + view["reuse_ambiguous_disks"],
                    required,
                )
                self.assertEqual(
                    view["certified_overlap_sign_mismatches"], 0
                )
                self.assertGreaterEqual(view["reuse_maximum_radius"], 0.0)
                if view["delta"] == 0:
                    self.assertEqual(view["reuse_ambiguous_disks"], 0)
                    self.assertTrue(view["reuse_junction_accepted"])
                    self.assertTrue(view["finite_event_semantics_identity"])
                    self.assertTrue(
                        view["stationary_resolution_semantics_identity"]
                    )
                    self.assertTrue(
                        view["finite_nleft_nright_semantics_identity"]
                    )
                    self.assertEqual(view["disk_interval_disjoint_count"], 0)
                    self.assertEqual(
                        2 * view["stationary_candidates"],
                        view["resolved_multiplicity_slots"],
                    )
                else:
                    self.assertGreater(view["reuse_ambiguous_disks"], 0)
                    self.assertFalse(view["reuse_junction_accepted"])
                    self.assertFalse(view["finite_event_semantics_identity"])
                    self.assertFalse(
                        view["stationary_resolution_semantics_identity"]
                    )
                    self.assertFalse(
                        view["finite_nleft_nright_semantics_identity"]
                    )

        interior = runs["interior-center-2"]
        self.assertEqual(
            [view["delta"] for view in interior["views"]
             if view["roster_owned"]],
            [-2, -1, 0, 1, 2],
        )
        terminal = runs["terminal-residual-center"]
        self.assertEqual(
            [view["delta"] for view in terminal["views"]
             if not view["campaign_boundary_rejected"]
             and view["roster_owned"]],
            [-1, 0, 1],
        )
        self.assertFalse(terminal["views"][0]["roster_owned"])
        self.assertTrue(terminal["views"][-1]["campaign_boundary_rejected"])

        status = result["semantic_status"]
        self.assertTrue(
            status.pop(
                "observed_only_delta_zero_viable_with_current_enclosure"
            )
        )
        self.assertTrue(all(value is False for value in status.values()))

    def test_optional_genuine_stream_exact_event_comparison(self) -> None:
        stream = os.environ.get(STREAM_ENV)
        stream_sha = os.environ.get(STREAM_SHA_ENV)
        center = os.environ.get(CENTER_ENV)
        resolver_sha = os.environ.get(RESOLVER_SHA_ENV)
        flint_sha = os.environ.get(FLINT_SHA_ENV)
        if (
            not stream
            or not stream_sha
            or center is None
            or not resolver_sha
            or not flint_sha
        ):
            self.skipTest(
                f"set {STREAM_ENV}, {STREAM_SHA_ENV}, {CENTER_ENV}, "
                f"{RESOLVER_SHA_ENV}, and {FLINT_SHA_ENV}"
            )
        arguments = [
            str(self._runner()),
            stream,
            center,
            f"--expected-stream-sha256={stream_sha}",
            f"--resolver-sha256={resolver_sha}",
            f"--flint-sha256={flint_sha}",
        ]
        owned_deltas = os.environ.get(OWNED_DELTAS_ENV)
        if owned_deltas:
            arguments.append(f"--owned-deltas={owned_deltas}")
        completed = subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0 if result["accepted"] else 3)
        self.assertTrue(result["qualification_only"])
        profile = result["build_profile"]
        self.assertIn(profile["cmake_build_config"], {
            "Debug", "MinSizeRel", "RelWithDebInfo", "Release", "unreported"
        })
        self.assertEqual(
            profile["release_performance_build"],
            profile["cmake_build_config"] == "Release"
            and profile["ndebug_defined"],
        )
        self.assertTrue(result["bounds_checked_transform_accessor"])
        self.assertTrue(result["fixed_2176_bit_host_replay_complete"])
        for view in result["views"]:
            if view["campaign_boundary_rejected"]:
                continue
            self.assertEqual(view["reuse_invalid_disks"], 0)
            self.assertEqual(view["ordinary_invalid_disks"], 0)
            self.assertEqual(view["ordinary_ambiguous_disks"], 0)
            self.assertTrue(view["ordinary_junction_accepted"])
            if view["reuse_ambiguous_disks"] == 0:
                self.assertTrue(view["reuse_junction_accepted"])
                self.assertTrue(view["sign_output_byte_identity"])
                self.assertTrue(view["finite_event_semantics_identity"])
                self.assertTrue(
                    view["stationary_resolution_semantics_identity"]
                )
                self.assertTrue(
                    view["finite_nleft_nright_semantics_identity"]
                )
            else:
                self.assertFalse(view["reuse_junction_accepted"])
                self.assertFalse(view["finite_event_semantics_identity"])
        self.assertFalse(result["whole_pipeline_speedup_claimed"])
        self.assertFalse(result["accumulator_stride_skip_implemented"])
        self.assertFalse(result["hardy_z_endpoint_realization_proved"])
        self.assertFalse(result["source_claim_ready"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["pt21_atom_discharged"])


if __name__ == "__main__":
    unittest.main()
