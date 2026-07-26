# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import create_run_bundle as bundles  # noqa: E402
import generate_production_deployment_candidate as candidate  # noqa: E402
import generate_trusted_compute_lean as lean_generator  # noqa: E402
import trusted_compute_receipt as receipts  # noqa: E402


FIXTURE = ROOT / "tests/fixtures/trusted_compute_cpu_receipt.json"


class ProductionDeploymentCandidateTests(unittest.TestCase):
    def receipt(self, invocation: str) -> dict:
        value = receipts.validate_receipt(
            json.loads(FIXTURE.read_text(encoding="utf-8"))
        )
        value = copy.deepcopy(value)
        value["claim"].update(
            lean_generator.registered_invocation_expected(invocation)
        )
        core = {
            key: field
            for key, field in value.items()
            if key != "receipt_sha256"
        }
        value["receipt_sha256"] = bundles.canonical_sha256(core)
        return value

    def test_candidate_binds_exact_receipt_profiles_and_artifacts(self) -> None:
        receipt = self.receipt("cdemTableAbelProductionV2")
        source = candidate.generate_candidate(receipt)
        self.assertIn(
            "def cdemTableAbelProductionDeployment :", source
        )
        self.assertIn(
            f'receiptHash := "{receipt["receipt_sha256"]}"', source
        )
        self.assertIn(
            f'targetProfileHash := "{receipt["claim"]["target_profile_hash"]}"',
            source,
        )
        for value in receipt["claim"]["artifacts"].values():
            self.assertIn(f'"{value}"', source)
        self.assertIn(
            "registry entry: importedTrustedComputeRun_"
            + receipt["receipt_sha256"],
            source,
        )

    def test_tutorial_has_no_production_candidate(self) -> None:
        receipt = self.receipt("cubicSumDivThree20000V1")
        with self.assertRaisesRegex(
            receipts.ReceiptError, "tutorial/pilot"
        ):
            candidate.generate_candidate(receipt)

    def test_every_nonpilot_registered_invocation_has_one_pin(self) -> None:
        self.assertEqual(
            set(candidate.DEPLOYMENT_DEFINITIONS),
            set(lean_generator.REGISTERED_INVOCATIONS)
            - {
                "cubicSumDivThree20000V1",
                "h100FormalPtxConstantOneV1",
            },
        )

    def test_generated_consumer_requires_exact_receipt_binding(self) -> None:
        receipt = self.receipt("cdemTableAbelProductionV2")
        source = lean_generator.generate(
            receipt,
            "ProductionReceiptBinding",
            "cdemTableAbelProductionV2",
        )
        self.assertIn(
            "RegisteredInvocation.certificateBindingCheck", source
        )
        self.assertIn("RegisteredInvocation.receiptCheck", source)
        self.assertIn("RegisteredInvocation.resultCheck", source)
        self.assertIn("RegisteredInvocation.ResultAllowed", source)
        self.assertIn(
            "RegisteredInvocation.sourceBindingDiagnosticCheck", source
        )
        self.assertIn(
            "RegisteredAlgorithm.algorithmHashDiagnosticCheck", source
        )
        self.assertIn(
            "RegisteredAlgorithm.metadataHashesDiagnosticCheck", source
        )
        receipt_value_theorem = (
            lean_generator.canonical_hex_certificate_name(
                receipt["receipt_sha256"]
            )
            + "_value"
        )
        self.assertIn(receipt_value_theorem, source)

    def test_a7_pin_rejects_profile_and_artifact_substitution(self) -> None:
        receipt = self.receipt("ch25A7BoundaryProductionV1")
        reviewed = candidate.deployment_binding_values(receipt)
        self.assertTrue(candidate.matches_deployment_binding(receipt, reviewed))

        substitutions = (
            ("target_profile_hash", None),
            ("trust_profile_hash", None),
            ("artifacts", "source_tree_hash"),
            ("artifacts", "host_executable_hash"),
            ("artifacts", "device_cubin_hash"),
            ("artifacts", "kernel_manifest_hash"),
        )
        for outer, inner in substitutions:
            with self.subTest(field=(outer, inner)):
                changed = copy.deepcopy(receipt)
                if inner is None:
                    changed["claim"][outer] = "12" * 32
                else:
                    changed["claim"][outer][inner] = "12" * 32
                core = {
                    key: value
                    for key, value in changed.items()
                    if key != "receipt_sha256"
                }
                changed["receipt_sha256"] = bundles.canonical_sha256(core)

                # The old reviewed pin rejects the different receipt and
                # different deployment field.
                self.assertFalse(
                    candidate.matches_deployment_binding(changed, reviewed)
                )

                # Merely changing the receipt-hash half of the pin is still
                # insufficient: profile/artifact equality remains mandatory.
                receipt_only_substitution = copy.deepcopy(reviewed)
                receipt_only_substitution["receipt_hash"] = changed[
                    "receipt_sha256"
                ]
                self.assertFalse(
                    candidate.matches_deployment_binding(
                        changed, receipt_only_substitution
                    )
                )

                # Conversely, changing only the field half cannot reuse the
                # originally reviewed receipt hash.
                fields_only_substitution = (
                    candidate.deployment_binding_values(changed)
                )
                fields_only_substitution["receipt_hash"] = receipt[
                    "receipt_sha256"
                ]
                self.assertFalse(
                    candidate.matches_deployment_binding(
                        changed, fields_only_substitution
                    )
                )

        pins_source = (
            ROOT / "SparkInterval/Execution/ProductionDeploymentPins.lean"
        ).read_text(encoding="utf-8")
        registered_source = (
            ROOT / "SparkInterval/Execution/RegisteredAlgorithm.lean"
        ).read_text(encoding="utf-8")
        for exact_guard in (
            "statement.targetProfileHash = expected.targetProfileHash",
            "statement.trustProfileHash = expected.trustProfileHash",
            "statement.artifacts = expected.artifacts",
            "receiptHash = expected.receiptHash",
        ):
            self.assertIn(exact_guard, pins_source)
        self.assertRegex(
            registered_source,
            r"\|\s+\.ch25A7BoundaryProductionV1\s+=>\s*"
            r"reviewedProductionDeploymentCheck\s+"
            r"ch25A7BoundaryProductionDeployment\s+statement",
        )
        self.assertRegex(
            registered_source,
            r"\|\s+\.ch25A7BoundaryProductionV1\s+=>\s*"
            r"reviewedProductionReceiptCheck\s+"
            r"ch25A7BoundaryProductionDeployment\s+attestation",
        )


if __name__ == "__main__":
    unittest.main()
