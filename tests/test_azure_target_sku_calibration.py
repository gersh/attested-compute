# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

from tg_verifier import azure_target_sku_calibration as calibration
from tg_verifier.azure_production_sizing import (
    ProductionSizingError,
    build_sizing_report,
)
from tg_verifier.campaign_io import canonical_json_bytes


CAMPAIGN_ID = "ch25-a7-boundary"
ROUTE_ID = "ch25-a7-boundary:dc96-cpu"


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def body() -> dict[str, object]:
    profiles = calibration.REVIEWED_TARGET_BINDINGS["dc96_cpu"]
    return {
        "authority": dict(calibration.AUTHORITY_BLOCK),
        "evidence": {
            "attestation_appraisal_sha256": digest("appraisal"),
            "measured_run_receipt_sha256": digest("receipt"),
        },
        "identity": {
            "artifact_closure": {
                "file_count": 3,
                "manifest_sha256": digest("closure"),
                "total_size_bytes": 3072,
            },
            "campaign_id": CAMPAIGN_ID,
            "executable": {
                "sha256": digest("executable"),
                "size_bytes": 1024,
            },
            "resource_class": "dc96_cpu",
            "route_id": ROUTE_ID,
        },
        "kind": calibration.MANIFEST_KIND,
        "measurement": {
            "classification": calibration.MEASUREMENT_CLASSIFICATION,
            "full_source_execution_measured": False,
            "target_sku_timings_measured": True,
        },
        "profiles": {
            "target_profile_id": profiles["target_profile_id"],
            "target_profile_sha256": profiles["target_profile_sha256"],
            "trust_profile_id": profiles["trust_profile_id"],
            "trust_profile_sha256": profiles["trust_profile_sha256"],
        },
        "projection": {
            "classification": calibration.PROJECTION_CLASSIFICATION,
            "conservative_high_node_hours": {
                "denominator": 1000,
                "numerator": 1,
            },
            "endpoint_is_projection_not_measurement": True,
            "safety_factor": {"denominator": 1, "numerator": 2},
            "source_effective_work_items": 16_191,
            "source_effective_work_unit": "boundary_leaves",
        },
        "sample": {
            "dimensions": [
                {"count": 64, "name": "leaves", "unit": "boundary_leaves"}
            ],
            "effective_work_items": 64,
            "effective_work_unit": "boundary_leaves",
            "geometry_id": "a7-source-shaped-64-leaf-kat",
            "scope": "source_shaped_bounded",
        },
        "schema_version": calibration.SCHEMA_VERSION,
        "target": {
            "node_count": 1,
            "provider": "azure",
            "region": "eastus2",
            "sku": profiles["sku"],
        },
        "timings": {
            "end_to_end_nanoseconds": [1_000_000, 950_000, 975_000],
            "input_io_nanoseconds": [100_000, 90_000, 95_000],
            "output_io_nanoseconds": [100_000, 90_000, 95_000],
            "producer_nanoseconds": [400_000, 390_000, 395_000],
            "repetitions": 3,
            "replay_nanoseconds": [300_000, 290_000, 295_000],
            "unit": "nanoseconds",
        },
    }


class AzureTargetSKUCalibrationTests(unittest.TestCase):
    def test_valid_manifest_is_canonical_arithmetic_checked_and_non_authorizing(
        self,
    ) -> None:
        manifest = calibration.seal_manifest(body())
        raw = canonical_json_bytes(manifest)
        checked = calibration.validate_manifest_bytes(raw)
        summary = calibration.validation_summary(checked)

        self.assertTrue(summary["target_sku_calibration_manifest_valid"])
        self.assertEqual(
            summary["measurement_classification"],
            calibration.MEASUREMENT_CLASSIFICATION,
        )
        self.assertEqual(
            summary["conservative_high_node_hours"],
            {"numerator": 1, "denominator": 1000},
        )
        self.assertFalse(summary["named_artifact_bytes_validated"])
        self.assertFalse(summary["attestation_appraisal_replayed"])
        self.assertFalse(summary["authorizes_cloud_execution"])
        self.assertFalse(summary["authorizes_production_deployment"])
        self.assertFalse(summary["authorizes_lean_theorem"])

    def test_noncanonical_duplicate_and_self_hash_tampering_fail_closed(self) -> None:
        manifest = calibration.seal_manifest(body())
        with self.assertRaisesRegex(
            calibration.TargetSKUCalibrationError, "not canonical"
        ):
            calibration.validate_manifest_bytes(
                json.dumps(manifest, indent=2).encode("utf-8")
            )
        with self.assertRaisesRegex(
            calibration.TargetSKUCalibrationError, "duplicate JSON key"
        ):
            calibration.validate_manifest_bytes(
                b'{"schema_version":1,"schema_version":1}\n'
            )
        changed = copy.deepcopy(manifest)
        changed["manifest_sha256"] = digest("wrong self hash")
        with self.assertRaisesRegex(
            calibration.TargetSKUCalibrationError, "manifest_sha256"
        ):
            calibration.validate_manifest(changed)

    def test_measurement_cannot_be_relabelled_projection_or_local_trust(self) -> None:
        changed = copy.deepcopy(body())
        changed["measurement"]["classification"] = "projected-host-rate"
        with self.assertRaisesRegex(
            calibration.TargetSKUCalibrationError,
            "not target-SKU measurement evidence",
        ):
            calibration.seal_manifest(changed)

        changed = copy.deepcopy(body())
        changed["profiles"]["trust_profile_id"] = "local_unattested"
        with self.assertRaisesRegex(
            calibration.TargetSKUCalibrationError, "reviewed dc96_cpu profile"
        ):
            calibration.seal_manifest(changed)

    def test_timing_vectors_and_conservative_endpoint_are_checked(self) -> None:
        changed = copy.deepcopy(body())
        changed["timings"]["replay_nanoseconds"].pop()
        with self.assertRaisesRegex(
            calibration.TargetSKUCalibrationError, "exactly 3 entries"
        ):
            calibration.seal_manifest(changed)

        changed = copy.deepcopy(body())
        changed["timings"]["end_to_end_nanoseconds"][0] = 500_000
        with self.assertRaisesRegex(
            calibration.TargetSKUCalibrationError, "component sum"
        ):
            calibration.seal_manifest(changed)

        changed = copy.deepcopy(body())
        changed["projection"]["conservative_high_node_hours"] = {
            "numerator": 1,
            "denominator": 1_000_000_000,
        }
        with self.assertRaisesRegex(
            calibration.TargetSKUCalibrationError, "below the measured"
        ):
            calibration.seal_manifest(changed)

    def test_loader_reads_only_the_compact_manifest(self) -> None:
        raw = canonical_json_bytes(calibration.seal_manifest(body()))
        path = Path("/not-opened/calibration.json")
        with mock.patch.object(
            calibration, "read_bytes_once", return_value=raw
        ) as read:
            checked = calibration.load_manifest(path)
        read.assert_called_once_with(path, limit=calibration.MAX_MANIFEST_BYTES)
        self.assertEqual(checked["identity"]["executable"]["sha256"], digest("executable"))

    def test_sizing_defaults_to_no_target_sku_measurement(self) -> None:
        report = build_sizing_report()
        route = next(
            row
            for row in report["backend_optimizer"]["route_matrix"]
            if row["route_id"] == ROUTE_ID
        )
        self.assertFalse(route["demands"][0]["target_sku_measured"])
        self.assertEqual(
            report["backend_optimizer"][
                "target_sku_calibration_manifest_count"
            ],
            0,
        )
        self.assertEqual(
            report["backend_optimizer"]["target_sku_calibration_manifests"],
            [],
        )

    def test_explicit_exact_match_removes_only_target_measurement_false(self) -> None:
        manifest = calibration.seal_manifest(body())
        report = build_sizing_report(target_sku_calibrations=(manifest,))
        route = next(
            row
            for row in report["backend_optimizer"]["route_matrix"]
            if row["route_id"] == ROUTE_ID
        )
        demand = route["demands"][0]
        self.assertTrue(demand["target_sku_measured"])
        self.assertEqual(demand["evidence_id"], manifest["manifest_sha256"])
        self.assertEqual(
            report["backend_optimizer"][
                "target_sku_calibration_manifest_count"
            ],
            1,
        )
        summary = report["backend_optimizer"][
            "target_sku_calibration_manifests"
        ][0]
        self.assertFalse(summary["authorizes_production_deployment"])
        self.assertEqual(
            report["classification"],
            "planning_projection_not_execution_or_mathematical_evidence",
        )

    def test_sizing_rejects_unmatched_route_node_count_and_high_endpoint(self) -> None:
        changed = copy.deepcopy(body())
        changed["identity"]["route_id"] = "ch25-a7-boundary:no-such-route"
        with self.assertRaisesRegex(
            ProductionSizingError, "does not match an exact route resource"
        ):
            build_sizing_report(
                target_sku_calibrations=(calibration.seal_manifest(changed),)
            )

        changed = copy.deepcopy(body())
        changed["target"]["node_count"] = 2
        with self.assertRaisesRegex(
            ProductionSizingError, "node_count"
        ):
            build_sizing_report(
                target_sku_calibrations=(calibration.seal_manifest(changed),)
            )

        changed = copy.deepcopy(body())
        changed["projection"]["conservative_high_node_hours"] = {
            "numerator": 1,
            "denominator": 500,
        }
        with self.assertRaisesRegex(
            ProductionSizingError, "high node-hour endpoint"
        ):
            build_sizing_report(
                target_sku_calibrations=(calibration.seal_manifest(changed),)
            )

    def test_matching_goldbach_calibration_changes_measurement_not_route_authority(
        self,
    ) -> None:
        baseline = build_sizing_report()
        campaign_id = "ternary-goldbach-finite-below-10pow27-v1"
        route_id = (
            campaign_id + ":ncc-binary-and-host-ladder-sensitivity"
        )
        baseline_route = next(
            row
            for row in baseline["backend_optimizer"]["route_matrix"]
            if row["route_id"] == route_id
        )
        high = Decimal(baseline_route["demands"][0]["node_hours_high"])
        high_num, high_den = high.as_integer_ratio()
        source_work = int(
            baseline["planning_envelopes"][
                "goldbach_binary_h100_sensitivity"
            ]["benchmark"]["source_even_count"]
        )

        changed = copy.deepcopy(body())
        profiles = calibration.REVIEWED_TARGET_BINDINGS["ncc_h100"]
        changed["identity"]["campaign_id"] = campaign_id
        changed["identity"]["route_id"] = route_id
        changed["identity"]["resource_class"] = "ncc_h100"
        changed["profiles"] = {
            "target_profile_id": profiles["target_profile_id"],
            "target_profile_sha256": profiles["target_profile_sha256"],
            "trust_profile_id": profiles["trust_profile_id"],
            "trust_profile_sha256": profiles["trust_profile_sha256"],
        }
        changed["target"]["node_count"] = 8
        changed["target"]["sku"] = profiles["sku"]
        changed["sample"] = {
            "dimensions": [
                {"count": 64, "name": "evens", "unit": "even_inputs"}
            ],
            "effective_work_items": 64,
            "effective_work_unit": "even_inputs",
            "geometry_id": "goldbach-source-shaped-64-even-synthetic-kat",
            "scope": "source_shaped_bounded",
        }
        changed["projection"] = {
            "classification": calibration.PROJECTION_CLASSIFICATION,
            "conservative_high_node_hours": {
                "numerator": high_num,
                "denominator": high_den,
            },
            "endpoint_is_projection_not_measurement": True,
            "safety_factor": {"numerator": 1, "denominator": 1},
            "source_effective_work_items": source_work,
            "source_effective_work_unit": "even_inputs",
        }
        changed["timings"] = {
            "end_to_end_nanoseconds": [2, 2, 2],
            "input_io_nanoseconds": [0, 0, 0],
            "output_io_nanoseconds": [0, 0, 0],
            "producer_nanoseconds": [1, 1, 1],
            "repetitions": 3,
            "replay_nanoseconds": [1, 1, 1],
            "unit": "nanoseconds",
        }
        manifest = calibration.seal_manifest(changed)
        report = build_sizing_report(target_sku_calibrations=(manifest,))
        route = next(
            row
            for row in report["backend_optimizer"]["route_matrix"]
            if row["route_id"] == route_id
        )
        self.assertTrue(route["demands"][0]["target_sku_measured"])
        self.assertEqual(route["readiness"], "sensitivity_only")
        self.assertFalse(route["optimizer_eligible"])
        self.assertFalse(
            route["production_gate"]["production_ready"]["pay_as_you_go"]
        )
        self.assertTrue(
            report["planning_envelopes"][
                "goldbach_binary_h100_sensitivity"
            ]["calibration_gate"]["passed"]
        )
        handoff = report["dominant_campaign_budget_review"]["campaigns"][
            "helfgott-platt-goldbach-gpu-v1"
        ]["analytic_10pow27_handoff"]
        self.assertTrue(handoff["h100_calibration_passed"])


if __name__ == "__main__":
    unittest.main()
