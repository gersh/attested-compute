# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import contextlib
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import create_run_bundle as bundles  # noqa: E402
import generate_trusted_compute_registry as registry  # noqa: E402
import generate_trusted_compute_lean as lean_generator  # noqa: E402
import trusted_compute_receipt as receipts  # noqa: E402


FIXTURE = ROOT / "tests/fixtures/trusted_compute_cpu_receipt.json"


class TrustedComputeRegistryTests(unittest.TestCase):
    def fixture(self) -> dict:
        return receipts.validate_receipt(
            bundles.parse_json_bytes(FIXTURE.read_bytes(), str(FIXTURE))
        )

    def registered_fixture(self) -> dict:
        receipt = copy.deepcopy(self.fixture())
        receipt["claim"].update(
            lean_generator.registered_invocation_expected(
                "cubicSumDivThree20000V1"
            )
        )
        core = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        return receipt

    def h100_registered_fixture(self) -> dict:
        receipt = copy.deepcopy(self.fixture())
        receipt["backend"] = "azure_ncc40ads_h100_v5"
        receipt["claim"].update(
            lean_generator.registered_invocation_expected(
                "h100FormalPtxConstantOneV1"
            )
        )
        receipt["claim"]["artifacts"]["device_cubin_hash"] = "12" * 32
        core = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        return receipt

    def cdem_registered_fixture(self) -> dict:
        receipt = copy.deepcopy(self.fixture())
        receipt["claim"].update(
            lean_generator.registered_invocation_expected(
                "cdemTableAbelProductionV2"
            )
        )
        core = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        return receipt

    def hurst_registered_fixture(self) -> dict:
        receipt = copy.deepcopy(self.fixture())
        receipt["claim"].update(
            lean_generator.registered_invocation_expected(
                "hurstSharedFourResidualProductionV2"
            )
        )
        core = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        return receipt

    def psi_registered_fixture(self) -> dict:
        receipt = copy.deepcopy(self.fixture())
        receipt["claim"].update(
            lean_generator.registered_invocation_expected(
                "ch25PsiLemma92ProductionV1"
            )
        )
        core = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        return receipt

    def prop1224_registered_fixture(self) -> dict:
        receipt = copy.deepcopy(self.fixture())
        receipt["claim"].update(
            lean_generator.registered_invocation_expected(
                "helfgottProp1224ProductionV1"
            )
        )
        core = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        return receipt

    def a7_registered_fixture(self) -> dict:
        receipt = copy.deepcopy(self.fixture())
        receipt["claim"].update(
            lean_generator.registered_invocation_expected(
                "ch25A7BoundaryProductionV1"
            )
        )
        core = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        return receipt

    def zeta_rh_registered_fixture(self) -> dict:
        receipt = copy.deepcopy(self.fixture())
        receipt["claim"].update(
            lean_generator.registered_invocation_expected(
                "plattTrudgianFiniteRHProductionV1"
            )
        )
        core = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        return receipt

    def zeta_head_registered_fixture(self) -> dict:
        receipt = copy.deepcopy(self.fixture())
        receipt["claim"].update(
            lean_generator.registered_invocation_expected(
                "plattHead2e4ProductionV1"
            )
        )
        core = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        return receipt

    def platt_dirichlet_registered_fixture(self) -> dict:
        receipt = copy.deepcopy(self.fixture())
        receipt["claim"].update(
            lean_generator.registered_invocation_expected(
                "plattDirichletTheorem71ProductionV1"
            )
        )
        core = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        return receipt

    def goldbach_registered_fixture(self) -> dict:
        receipt = copy.deepcopy(self.fixture())
        receipt["claim"].update(
            lean_generator.registered_invocation_expected(
                "helfgottPlattGoldbachProductionV1"
            )
        )
        core = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        return receipt

    def goldbach_10pow27_registered_fixture(self) -> dict:
        receipt = copy.deepcopy(self.fixture())
        receipt["claim"].update(
            lean_generator.registered_invocation_expected(
                "goldbach10Pow27ProductionV1"
            )
        )
        core = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        return receipt

    def test_duplicate_start_challenge_is_rejected(self) -> None:
        first = self.registered_fixture()
        replay = copy.deepcopy(first)
        replay["receipt_sha256"] = "11" * 32
        replay["bindings"]["run_bundle_sha256"] = "22" * 32
        replay["bindings"]["wire_statement_sha256"] = "33" * 32
        replay["bindings"]["result_binding_sha256"] = "44" * 32
        with self.assertRaisesRegex(
            receipts.ReceiptError, "duplicate trusted-compute start challenge"
        ):
            registry.generate_registry([first, replay])

    def test_duplicate_result_binding_is_rejected(self) -> None:
        first = self.registered_fixture()
        replay = copy.deepcopy(first)
        replay["receipt_sha256"] = "11" * 32
        replay["bindings"]["run_bundle_sha256"] = "22" * 32
        replay["bindings"]["wire_statement_sha256"] = "33" * 32
        replay["bindings"]["start_challenge_sha256"] = "44" * 32
        with self.assertRaisesRegex(
            receipts.ReceiptError, "duplicate trusted-compute result binding"
        ):
            registry.generate_registry([first, replay])

    def test_expired_receipt_cannot_enter_registry(self) -> None:
        receipt = self.registered_fixture()
        expiry = dt.datetime(2026, 7, 22, 12, tzinfo=dt.timezone.utc)
        with self.assertRaisesRegex(receipts.ReceiptError, "expired"):
            registry.validate_registry_admission(receipt, now=expiry)

    def test_write_mode_cannot_backdate_admission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "Registry.lean"
            with contextlib.redirect_stderr(io.StringIO()):
                status = registry.main(
                    [
                        "--allow-empty",
                        "--admission-time",
                        "2026-01-01T00:00:00Z",
                        "--out",
                        str(destination),
                    ]
                )
            self.assertEqual(status, 2)
            self.assertFalse(destination.exists())

    def test_registry_uses_full_hash_names_and_exact_signed_literals(self) -> None:
        receipt = self.registered_fixture()
        source = registry.generate_registry(
            [receipt], admission_time="2026-07-21T12:00:00Z"
        )
        entry = "importedTrustedComputeRun_" + receipt["receipt_sha256"]
        self.assertIn(f"def {entry} : TrustedComputeEvidence :=", source)
        self.assertIn(f"  {entry}\n]", source)
        self.assertIn(f"@[simp] theorem lookup_{entry} :", source)
        signature = receipt["signature"]["value_hex"]
        signature_certificate = lean_generator.canonical_hex_certificate_name(
            signature
        )
        self.assertIn(
            f"signatureHex := {signature_certificate}.value", source
        )
        for index in range(0, len(signature), registry.HEX_CHUNK_LENGTH):
            self.assertIn(
                lean_generator.lean_string(
                    signature[index : index + registry.HEX_CHUNK_LENGTH]
                ),
                source,
            )

    def test_consumer_uses_structural_registry_handoff(self) -> None:
        receipt = self.registered_fixture()
        source = lean_generator.generate(receipt, "StructuralReplay")
        entry = "importedTrustedComputeRun_" + receipt["receipt_sha256"]
        digest_certificate = lean_generator.canonical_hex_certificate_name(
            receipt["claim"]["algorithm_hash"]
        )
        signature_certificate = lean_generator.canonical_hex_certificate_name(
            receipt["signature"]["value_hex"]
        )
        self.assertIn(f"def evidence : TrustedComputeEvidence := {entry}", source)
        self.assertIn(
            f"theorem requiredDigest_{digest_certificate}", source
        )
        self.assertIn(
            f"{digest_certificate}.canonical (by rfl) (by rfl)", source
        )
        self.assertIn(f"exact {signature_certificate}.canonical", source)
        self.assertIn("theorem resultPayloadHashBound", source)
        self.assertIn("theorem challengeResultBindingBound", source)
        self.assertIn("  apply checkTrustedCompute_of_imported", source)
        self.assertIn(f"  · exact lookup_{entry}", source)
        self.assertIn("import SparkInterval.Audit.TrustedComputeCertificates", source)
        self.assertIn("acceptedRunCertificateForReceipt", source)
        self.assertIn(
            lean_generator.lean_string(receipt["receipt_sha256"]), source
        )
        self.assertIn("#audit certificates producedOutcome", source)
        self.assertNotIn("\n  decide_cbv", source)
        self.assertNotIn("\n  native_decide", source)

    def test_source_registry_rejects_unknown_algorithm_identity(self) -> None:
        with self.assertRaisesRegex(
            receipts.ReceiptError, "exactly one current closed registered invocation"
        ):
            lean_generator.validate_source_admitted_registered_invocation(
                self.fixture()
            )

    def test_source_registry_requires_registered_result_and_output_hash(self) -> None:
        receipt = self.fixture()
        expected = lean_generator.registered_invocation_expected(
            "cubicSumDivThree20000V1"
        )
        receipt["claim"].update(expected)
        self.assertEqual(
            lean_generator.validate_source_admitted_registered_invocation(receipt),
            "cubicSumDivThree20000V1",
        )
        for field in ("result", "output_hash"):
            with self.subTest(field=field):
                changed = copy.deepcopy(receipt)
                changed["claim"][field] = "wrong" if field == "result" else "12" * 32
                with self.assertRaisesRegex(
                    receipts.ReceiptError, f"wrong claim {field}"
                ):
                    lean_generator.validate_bound_registered_results(changed)

    def test_h100_pilot_mapping_is_closed_and_backend_specific(self) -> None:
        receipt = self.h100_registered_fixture()
        expected = lean_generator.registered_invocation_expected(
            "h100FormalPtxConstantOneV1"
        )
        self.assertEqual(
            expected["algorithm_hash"],
            "2ee3f3045a1ff97b07a697cea602b9bc9bba3278bd5494c50684f3ed29cad582",
        )
        self.assertEqual(
            expected["input_hash"],
            "724d074b5818f2cb1ef81b5b73635af38c8f5309826cfa3dcc40b5729d8fbb93",
        )
        self.assertEqual(
            lean_generator.validate_source_admitted_registered_invocation(receipt),
            "h100FormalPtxConstantOneV1",
        )
        changed = copy.deepcopy(receipt)
        changed["claim"]["result"] = "wrong"
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong claim result"):
            lean_generator.validate_bound_registered_results(changed)
        wrong_backend = copy.deepcopy(receipt)
        wrong_backend["backend"] = "azure_sevsnp_cpu"
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong backend"):
            lean_generator.validate_registered_invocation(
                wrong_backend, "h100FormalPtxConstantOneV1"
            )
        with self.assertRaisesRegex(
            receipts.ReceiptError, "exactly one current closed registered invocation"
        ):
            lean_generator.validate_source_admitted_registered_invocation(wrong_backend)

    def test_h100_generated_consumer_projects_registered_result(self) -> None:
        receipt = self.h100_registered_fixture()
        source = lean_generator.generate(
            receipt,
            "H100FormalPtxPilot",
            "h100FormalPtxConstantOneV1",
        )
        self.assertIn(
            "RegisteredInvocation.h100FormalPtxConstantOneV1.Runs", source
        )
        self.assertIn(
            "h100FormalPtxConstantOne_result_of_run registeredRun", source
        )
        self.assertIn("theorem exactMathematicalResult", source)
        self.assertIn(
            "import SparkInterval.Execution.RegisteredH100FormalPtxPilot", source
        )
        self.assertIn("theorem formalProgramIdentity", source)
        self.assertIn("theorem certifiedApplication", source)
        self.assertNotIn("\n  native_decide", source)
        self.assertNotIn("\n  decide_cbv", source)

    def test_cdem_mapping_and_generated_consumer_are_source_shaped(self) -> None:
        receipt = self.cdem_registered_fixture()
        expected = lean_generator.registered_invocation_expected(
            "cdemTableAbelProductionV2"
        )
        self.assertEqual(
            expected["algorithm_hash"],
            "f924a59b7569a9407b78bbbe5931c03fa76532b7dd88c64401263402ac4575b0",
        )
        self.assertEqual(
            expected["input_hash"],
            "f14d4dd60e39b2b4f655d3b82333659167d78246de8c5aab923db8a69347742a",
        )
        self.assertEqual(
            expected["parameters_hash"],
            "9c7ac1c656f2228f36b68095dba7ce1f317a024e51bfa49878434d616d97dca8",
        )
        self.assertEqual(
            expected["domain_hash"],
            "298811e1d0ab933c02ff8afb71eb21d715052d414d3b400473b3f36807969a76",
        )
        self.assertEqual(
            expected["result"],
            "2372685835387717172679029560108650251645442524",
        )
        self.assertEqual(
            expected["output_hash"],
            "84e7c2b56de45b48776e4239bfc82e80ef5c80940f232b83c85eefc44648b73c",
        )
        generated_certificate = (
            ROOT / "SparkInterval/Generated/CDEMAbelProduction.lean"
        )
        self.assertEqual(
            hashlib.sha256(generated_certificate.read_bytes()).hexdigest(),
            "c31fe5bdb3444d53b484dbc14592d1509f284378e75ba356a006d68b952f2ee9",
        )
        registry_source = (
            ROOT / "SparkInterval/Execution/RegisteredAlgorithm.lean"
        ).read_text(encoding="utf-8")
        cdem_runs = registry_source.split(
            "| .cdemTableAbelExactScanV2, input, output =>", 1
        )[1].split("| .hurstSharedFourResidualV2, input, output =>", 1)[0]
        self.assertIn(
            "SparkInterval.Generated.CDEMAbelProduction.certificate",
            cdem_runs,
        )
        self.assertIn("LocalSourceScaleEvidence", cdem_runs)
        self.assertNotIn(
            "CDEMAbelRecurrenceCertificate.SourceScaleEvidence", cdem_runs
        )
        self.assertNotIn("CDEMAbelSource.ScaledOutputClaim", cdem_runs)
        self.assertNotIn("∃ certificate", cdem_runs)
        self.assertIn(
            "CDEMAbelProduction.certificate_check", registry_source
        )
        self.assertIn(
            "scaledOutputClaim_of_checked_local_certificate", registry_source
        )
        self.assertEqual(
            lean_generator.validate_source_admitted_registered_invocation(receipt),
            "cdemTableAbelProductionV2",
        )
        source = lean_generator.generate(
            receipt,
            "CDEMTableAbelMeasuredRun",
            "cdemTableAbelProductionV2",
        )
        self.assertIn(
            "import SparkInterval.Execution.RegisteredCDEMAbelCertificate",
            source,
        )
        self.assertIn(
            "RegisteredInvocation.cdemTableAbelProductionV2.Runs", source
        )
        self.assertIn(
            "CDEMAbelSource.SourceClaim", source
        )
        self.assertIn(
            "cdemTableAbelProductionV2_sourceClaim", source
        )
        self.assertNotIn("\n  native_decide", source)

        wrong_backend = copy.deepcopy(receipt)
        wrong_backend["backend"] = "azure_ncc40ads_h100_v5"
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong backend"):
            lean_generator.validate_registered_invocation(
                wrong_backend, "cdemTableAbelProductionV2"
            )

    def test_cubic_generated_consumer_reduces_deployment_guard(self) -> None:
        source = lean_generator.generate(
            self.registered_fixture(),
            "CubicMeasuredRun",
            "cubicSumDivThree20000V1",
        )
        self.assertIn("RegisteredInvocation.deploymentCheck", source)
        self.assertIn(
            "RegisteredInvocation.cubicSumDivThree20000V1.Runs", source
        )

    def test_hurst_v2_mapping_and_generated_consumer_expose_real_claims(self) -> None:
        receipt = self.hurst_registered_fixture()
        expected = lean_generator.registered_invocation_expected(
            "hurstSharedFourResidualProductionV2"
        )
        self.assertEqual(
            expected["algorithm_hash"],
            "7ba331f8cc0457f3a19bbce0887be65b12ba005952ed480aeb5b98c86611a6cd",
        )
        self.assertEqual(
            expected["input_hash"],
            "84cad6505119c2498b1213c73c13e379ebcc0e8bbd2d445d1539d45ec06fc5b7",
        )
        self.assertEqual(
            expected["parameters_hash"],
            "78f8cf9ecdcac464c1711f877c57e31518dd66d6070882fb6de1d2a199068d1d",
        )
        self.assertEqual(
            expected["domain_hash"],
            "fbbe3abc2d158bebb2a9f9b06c0379c3fd9eff168c86c9900a7997172ec91f0a",
        )
        self.assertEqual(expected["result"], "true")
        self.assertEqual(
            expected["output_hash"],
            "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b",
        )
        registry_source = (
            ROOT / "SparkInterval/Execution/RegisteredAlgorithm.lean"
        ).read_text(encoding="utf-8")
        hurst_runs = registry_source.split(
            "| .hurstSharedFourResidualV2, input, output =>", 1
        )[1].split("| .ch25PsiLemma92V1, input, output =>", 1)[0]
        self.assertIn(
            "HurstSourceSemantics.LocalSourceScaleEvidence", hurst_runs
        )
        self.assertNotIn(
            "HurstAffineCertificate.SourceScaleEvidence", hurst_runs
        )
        self.assertNotIn("SourceRowPredicate", hurst_runs)
        self.assertEqual(
            lean_generator.validate_source_admitted_registered_invocation(receipt),
            "hurstSharedFourResidualProductionV2",
        )
        source = lean_generator.generate(
            receipt,
            "HurstSharedFourResidualMeasuredRun",
            "hurstSharedFourResidualProductionV2",
        )
        self.assertIn(
            "import SparkInterval.Execution.RegisteredHurstSharedCertificate",
            source,
        )
        self.assertIn(
            "RegisteredInvocation.hurstSharedFourResidualProductionV2.Runs",
            source,
        )
        self.assertIn("HurstSourceSemantics.RealSourceClaims", source)
        self.assertIn(
            "hurstSharedFourResidualProductionV2_realClaims", source
        )
        self.assertIn("theorem exactMathematicalResult", source)
        self.assertNotIn("\n  native_decide", source)

        wrong_result = copy.deepcopy(receipt)
        wrong_result["claim"]["result"] = "false"
        wrong_result["claim"]["output_hash"] = "12" * 32
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong claim result"):
            lean_generator.validate_bound_registered_results(wrong_result)

        wrong_backend = copy.deepcopy(receipt)
        wrong_backend["backend"] = "azure_ncc40ads_h100_v5"
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong backend"):
            lean_generator.validate_registered_invocation(
                wrong_backend, "hurstSharedFourResidualProductionV2"
            )

    def test_psi_v1_mapping_and_generated_consumer_expose_source_claim(self) -> None:
        receipt = self.psi_registered_fixture()
        expected = lean_generator.registered_invocation_expected(
            "ch25PsiLemma92ProductionV1"
        )
        self.assertEqual(
            expected["algorithm_hash"],
            "b16368f84ca70c2a3e7b9b9814c7e098e79c0c3bb137a51b85851cfd526753b0",
        )
        self.assertEqual(
            expected["input_hash"],
            "35368234a47ea3acdac04c55453f07cc5deb051fdf2238e865d683b17b11d3d8",
        )
        self.assertEqual(
            expected["parameters_hash"],
            "ddc632e84956e223e9df686d02aab167b52cd902dfcedf6ae3a7ccccdd0f6637",
        )
        self.assertEqual(
            expected["domain_hash"],
            "2a19d38cb3c36f9371c741701b7046b6c99dfba94f12185bd8625fad2e8f921f",
        )
        self.assertEqual(expected["result"], "true")
        self.assertEqual(
            expected["output_hash"],
            "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b",
        )
        self.assertEqual(
            lean_generator.validate_source_admitted_registered_invocation(receipt),
            "ch25PsiLemma92ProductionV1",
        )
        source = lean_generator.generate(
            receipt,
            "CH25PsiLemma92MeasuredRun",
            "ch25PsiLemma92ProductionV1",
        )
        self.assertIn(
            "import SparkInterval.Execution.RegisteredPsiLemma92Certificate",
            source,
        )
        self.assertIn(
            "RegisteredInvocation.ch25PsiLemma92ProductionV1.Runs", source
        )
        self.assertIn("PsiSourceSemantics.SourceClaim", source)
        self.assertIn("ch25PsiLemma92ProductionV1_sourceClaim", source)
        self.assertIn("theorem exactMathematicalResult", source)
        self.assertNotIn("\n  native_decide", source)

        wrong_result = copy.deepcopy(receipt)
        wrong_result["claim"]["result"] = "false"
        wrong_result["claim"]["output_hash"] = "12" * 32
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong claim result"):
            lean_generator.validate_bound_registered_results(wrong_result)

        wrong_backend = copy.deepcopy(receipt)
        wrong_backend["backend"] = "azure_ncc40ads_h100_v5"
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong backend"):
            lean_generator.validate_registered_invocation(
                wrong_backend, "ch25PsiLemma92ProductionV1"
            )

    def test_prop1224_mapping_and_generated_consumer_expose_source_claim(self) -> None:
        receipt = self.prop1224_registered_fixture()
        expected = lean_generator.registered_invocation_expected(
            "helfgottProp1224ProductionV1"
        )
        self.assertEqual(
            expected["algorithm_hash"],
            "184e8f8f60f511868d39a7a1ab7599a4b725415892e99c8fd84a35f8bf6c38a1",
        )
        self.assertEqual(
            expected["input_hash"],
            "ced1a63532a63b6e24290c51082ff8865ce38c75daae0d4f3439a63eef2444ec",
        )
        self.assertEqual(
            expected["parameters_hash"],
            "fac07cd6c76a9e2caf7e475107046d76683788426b1c9e26ac8d66aed8114853",
        )
        self.assertEqual(
            expected["domain_hash"],
            "effa0ec90992a66d497c13fba77923a9fb96996d93be9d8d6fd54b21a09e92a3",
        )
        self.assertEqual(expected["result"], "true")
        self.assertEqual(
            lean_generator.validate_source_admitted_registered_invocation(receipt),
            "helfgottProp1224ProductionV1",
        )
        source = lean_generator.generate(
            receipt,
            "HelfgottProp1224MeasuredRun",
            "helfgottProp1224ProductionV1",
        )
        self.assertIn(
            "import SparkInterval.Execution.RegisteredProp1224Certificate",
            source,
        )
        self.assertIn(
            "RegisteredInvocation.helfgottProp1224ProductionV1.Runs", source
        )
        self.assertIn("Prop1224SourceSemantics.SourceClaim", source)
        self.assertIn("helfgottProp1224ProductionV1_sourceClaim", source)
        self.assertIn("theorem exactMathematicalResult", source)
        self.assertNotIn("\n  native_decide", source)

        wrong_result = copy.deepcopy(receipt)
        wrong_result["claim"]["result"] = "false"
        wrong_result["claim"]["output_hash"] = "12" * 32
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong claim result"):
            lean_generator.validate_bound_registered_results(wrong_result)

        wrong_backend = copy.deepcopy(receipt)
        wrong_backend["backend"] = "azure_ncc40ads_h100_v5"
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong backend"):
            lean_generator.validate_registered_invocation(
                wrong_backend, "helfgottProp1224ProductionV1"
            )

    def test_a7_mapping_and_generated_consumer_expose_source_claim(self) -> None:
        receipt = self.a7_registered_fixture()
        expected = lean_generator.registered_invocation_expected(
            "ch25A7BoundaryProductionV1"
        )
        self.assertEqual(
            expected["algorithm_hash"],
            "340dc36f2ceb992ab16e34c534cd97b786d348ba057e159c295b3abd1328cdfa",
        )
        self.assertEqual(
            expected["input_hash"],
            "4e45410d2d26467dbd5f78f8ea536b1a8bbf44f1cd5248e234b985bd1f595674",
        )
        self.assertEqual(
            expected["parameters_hash"],
            "f377fb7b8c8d8d033083a0759841411d9bb955e919041f2a5b5be830ed69212e",
        )
        self.assertEqual(
            expected["domain_hash"],
            "629d9c7b3c084ef33f69d92abbe22b5120bac210fc963191c4b1e8289ff1dea5",
        )
        self.assertEqual(expected["result"], "true")
        self.assertEqual(
            lean_generator.validate_source_admitted_registered_invocation(receipt),
            "ch25A7BoundaryProductionV1",
        )
        source = lean_generator.generate(
            receipt,
            "CH25A7BoundaryMeasuredRun",
            "ch25A7BoundaryProductionV1",
        )
        self.assertIn(
            "import SparkInterval.Execution.RegisteredA7BoundaryCertificate",
            source,
        )
        self.assertIn(
            "RegisteredInvocation.ch25A7BoundaryProductionV1.Runs", source
        )
        self.assertIn("A7BoundarySourceSemantics.SourceClaim", source)
        self.assertIn("ch25A7BoundaryProductionV1_sourceClaim", source)
        self.assertIn("theorem exactMathematicalResult", source)
        self.assertNotIn("\n  native_decide", source)

        wrong_result = copy.deepcopy(receipt)
        wrong_result["claim"]["result"] = "false"
        wrong_result["claim"]["output_hash"] = "12" * 32
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong claim result"):
            lean_generator.validate_bound_registered_results(wrong_result)

        wrong_backend = copy.deepcopy(receipt)
        wrong_backend["backend"] = "azure_ncc40ads_h100_v5"
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong backend"):
            lean_generator.validate_registered_invocation(
                wrong_backend, "ch25A7BoundaryProductionV1"
            )

    def test_pt21_mapping_and_generated_consumer_expose_source_claim(self) -> None:
        receipt = self.zeta_rh_registered_fixture()
        expected = lean_generator.registered_invocation_expected(
            "plattTrudgianFiniteRHProductionV1"
        )
        self.assertEqual(
            expected["algorithm_hash"],
            "3f162d7b531d7bd1aca532f13ee8460c6e86cef315b38da6849b74b422906d5f",
        )
        self.assertEqual(
            expected["input_hash"],
            "0af73e082ef1673a90ca668e395b71166b0320d6e3a99b6cd2af6d09ea18adce",
        )
        self.assertEqual(
            expected["parameters_hash"],
            "be6cf9610adc9590ec746c28a48a6a3980d40ee9da1b01885167a309b5190672",
        )
        self.assertEqual(
            expected["domain_hash"],
            "e8d26bae0efc9c3acfa968e7b0e5a76d81902b9fb87ac7126605770f48e751fa",
        )
        self.assertEqual(expected["result"], "true")
        self.assertEqual(
            lean_generator.validate_source_admitted_registered_invocation(receipt),
            "plattTrudgianFiniteRHProductionV1",
        )
        source = lean_generator.generate(
            receipt,
            "PlattTrudgianFiniteRHMeasuredRun",
            "plattTrudgianFiniteRHProductionV1",
        )
        self.assertIn(
            "import SparkInterval.Execution.RegisteredZetaRHCertificate",
            source,
        )
        self.assertIn(
            "RegisteredInvocation.plattTrudgianFiniteRHProductionV1.Runs",
            source,
        )
        self.assertIn("ZetaRHSourceSemantics.SourceClaim", source)
        self.assertIn("plattTrudgianFiniteRHProductionV1_sourceClaim", source)
        self.assertIn("theorem exactMathematicalResult", source)
        self.assertNotIn("\n  native_decide", source)

        wrong_result = copy.deepcopy(receipt)
        wrong_result["claim"]["result"] = "false"
        wrong_result["claim"]["output_hash"] = "12" * 32
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong claim result"):
            lean_generator.validate_bound_registered_results(wrong_result)

        wrong_backend = copy.deepcopy(receipt)
        wrong_backend["backend"] = "azure_ncc40ads_h100_v5"
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong backend"):
            lean_generator.validate_registered_invocation(
                wrong_backend, "plattTrudgianFiniteRHProductionV1"
            )

    def test_platt_head_mapping_pins_both_tables_and_exposes_claim(self) -> None:
        receipt = self.zeta_head_registered_fixture()
        expected = lean_generator.registered_invocation_expected(
            "plattHead2e4ProductionV1"
        )
        self.assertEqual(
            expected["algorithm_hash"],
            "de33cb0d8db40a6b28c32605d9014ca8d593e446e4d1e3390402ea45c13f29ca",
        )
        self.assertEqual(
            expected["input_hash"],
            "a2409d869f3084fec413d4e7035f17749f4d2a572cd03f6f847f3352a78aca1d",
        )
        self.assertEqual(
            expected["parameters_hash"],
            "af039df434d373002440517fb4b4dd817a8e9fd5028116885df6f2466598986a",
        )
        self.assertEqual(
            expected["domain_hash"],
            "cfbcfeda2b76f99622befbf795d666b745ec45b82691f73bada7b04399464d11",
        )
        self.assertEqual(expected["result"], "true")
        self.assertEqual(
            lean_generator.validate_source_admitted_registered_invocation(receipt),
            "plattHead2e4ProductionV1",
        )
        source = lean_generator.generate(
            receipt,
            "PlattHead2e4MeasuredRun",
            "plattHead2e4ProductionV1",
        )
        self.assertIn(
            "import SparkInterval.Execution.RegisteredZetaHeadCertificate",
            source,
        )
        self.assertIn(
            "RegisteredInvocation.plattHead2e4ProductionV1.Runs", source
        )
        self.assertIn("SparkInterval.Generated.PlattHeadQ128.table", source)
        self.assertIn("plattHead2e4IncludedQ128RowsCommitment", source)
        self.assertIn("plattHead2e4ProductionV1_sourceClaim", source)
        self.assertIn("theorem exactMathematicalResult", source)
        self.assertNotIn("\n  native_decide", source)

        wrong_result = copy.deepcopy(receipt)
        wrong_result["claim"]["result"] = "false"
        wrong_result["claim"]["output_hash"] = "12" * 32
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong claim result"):
            lean_generator.validate_bound_registered_results(wrong_result)

        wrong_backend = copy.deepcopy(receipt)
        wrong_backend["backend"] = "azure_ncc40ads_h100_v5"
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong backend"):
            lean_generator.validate_registered_invocation(
                wrong_backend, "plattHead2e4ProductionV1"
            )

    def test_platt_dirichlet_mapping_exposes_exact_two_branch_claim(self) -> None:
        receipt = self.platt_dirichlet_registered_fixture()
        expected = lean_generator.registered_invocation_expected(
            "plattDirichletTheorem71ProductionV1"
        )
        self.assertEqual(
            expected["algorithm_hash"],
            "7b956d4a04403f9ba32fa2908a72cfa1483928991b3fa478d4bcfd79b089f33c",
        )
        self.assertEqual(
            expected["input_hash"],
            "42fe4b88a40a22d854292bf030a1eff009d32cf211e47085d43d79a6f2b8c8e9",
        )
        self.assertEqual(
            expected["parameters_hash"],
            "975b05caf3057f499a0d5673a438e74ff781702ceb0ffe8ca8f018f582c269f0",
        )
        self.assertEqual(
            expected["domain_hash"],
            "9b914c30a535b241a17b3180b52f759e3e52ed4424f2a93be4481323b627f31e",
        )
        self.assertEqual(expected["result"], "true")
        self.assertEqual(
            lean_generator.validate_source_admitted_registered_invocation(receipt),
            "plattDirichletTheorem71ProductionV1",
        )
        source = lean_generator.generate(
            receipt,
            "PlattDirichletTheorem71MeasuredRun",
            "plattDirichletTheorem71ProductionV1",
        )
        self.assertIn(
            "import SparkInterval.Execution.RegisteredPlattTheorem71Certificate",
            source,
        )
        self.assertIn(
            "RegisteredInvocation.plattDirichletTheorem71ProductionV1.Runs",
            source,
        )
        self.assertIn("PlattTheorem71DirichletVerification", source)
        self.assertIn(
            "plattDirichletTheorem71ProductionV1_sourceClaim", source
        )
        self.assertIn("theorem exactMathematicalResult", source)
        self.assertNotIn("\n  native_decide", source)

        wrong_result = copy.deepcopy(receipt)
        wrong_result["claim"]["result"] = "false"
        wrong_result["claim"]["output_hash"] = "12" * 32
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong claim result"):
            lean_generator.validate_bound_registered_results(wrong_result)

        wrong_backend = copy.deepcopy(receipt)
        wrong_backend["backend"] = "azure_ncc40ads_h100_v5"
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong backend"):
            lean_generator.validate_registered_invocation(
                wrong_backend, "plattDirichletTheorem71ProductionV1"
            )

    def test_goldbach_mapping_and_generated_consumer_expose_source_claim(self) -> None:
        receipt = self.goldbach_registered_fixture()
        expected = lean_generator.registered_invocation_expected(
            "helfgottPlattGoldbachProductionV1"
        )
        self.assertEqual(
            expected["algorithm_hash"],
            "93652e39a76fff96f8463f19f000ddaa15e2fafec4e0b5ea3a9870e2be8f8832",
        )
        self.assertEqual(
            expected["input_hash"],
            "19591d644a11591ac7aeffc9d507ded00f2f63993d68b2ceb7629c8ae62e0691",
        )
        self.assertEqual(
            expected["parameters_hash"],
            "dfafec3f7ed744b1e3fbc0e5f97aec1ec5540f106c896c7481329e6371ff0607",
        )
        self.assertEqual(
            expected["domain_hash"],
            "cf9cb3c9f1c3825c7ddfa3a91aa474f2f8cb03064570bad6d51cf7287bbdc47b",
        )
        self.assertEqual(expected["result"], "true")
        self.assertEqual(
            lean_generator.validate_source_admitted_registered_invocation(receipt),
            "helfgottPlattGoldbachProductionV1",
        )
        source = lean_generator.generate(
            receipt,
            "HelfgottPlattGoldbachMeasuredRun",
            "helfgottPlattGoldbachProductionV1",
        )
        self.assertIn(
            "import SparkInterval.Execution.RegisteredGoldbachCertificate",
            source,
        )
        self.assertIn(
            "RegisteredInvocation.helfgottPlattGoldbachProductionV1.Runs",
            source,
        )
        self.assertIn("GoldbachSourceSemantics.SourceClaim", source)
        self.assertIn("helfgottPlattGoldbachProductionV1_sourceClaim", source)
        self.assertIn("theorem exactMathematicalResult", source)
        self.assertNotIn("\n  native_decide", source)

        wrong_result = copy.deepcopy(receipt)
        wrong_result["claim"]["result"] = "false"
        wrong_result["claim"]["output_hash"] = "12" * 32
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong claim result"):
            lean_generator.validate_bound_registered_results(wrong_result)

        wrong_backend = copy.deepcopy(receipt)
        wrong_backend["backend"] = "azure_ncc40ads_h100_v5"
        with self.assertRaisesRegex(receipts.ReceiptError, "wrong backend"):
            lean_generator.validate_registered_invocation(
                wrong_backend, "helfgottPlattGoldbachProductionV1"
            )

    def test_goldbach_10pow27_mapping_is_distinct_and_exposes_exact_claim(self) -> None:
        receipt = self.goldbach_10pow27_registered_fixture()
        expected = lean_generator.registered_invocation_expected(
            "goldbach10Pow27ProductionV1"
        )
        self.assertEqual(
            expected["algorithm_hash"],
            "23ade6c8a6069feec88b20c24ad118a2ed8b93f16d673f20591caa7cbdf167c9",
        )
        self.assertEqual(
            expected["input_hash"],
            "5e34a58a14883600c91b891a78749cdcff1210ce48f64e41f7bf965f2331ad27",
        )
        self.assertEqual(
            expected["parameters_hash"],
            "ee334b42905942c4d3232007e2a67c27fee4e89a8143bbf6adb0d1957b0b8cb9",
        )
        self.assertEqual(
            expected["domain_hash"],
            "4a01f0bc8f042f6605fc42fca28c73416a694e7541759abb5e7fec04720f9fa7",
        )
        self.assertEqual(
            lean_generator.validate_source_admitted_registered_invocation(receipt),
            "goldbach10Pow27ProductionV1",
        )
        source = lean_generator.generate(
            receipt,
            "Goldbach10Pow27MeasuredRun",
            "goldbach10Pow27ProductionV1",
        )
        self.assertIn(
            "import SparkInterval.Execution.RegisteredGoldbach10Pow27Certificate",
            source,
        )
        self.assertIn(
            "RegisteredInvocation.goldbach10Pow27ProductionV1.Runs", source
        )
        self.assertIn("Goldbach10Pow27SourceSemantics.SourceClaim", source)
        self.assertIn("goldbach10Pow27ProductionV1_sourceClaim", source)
        self.assertNotIn("\n  native_decide", source)

    def test_key_manifest_and_lean_issuer_pins_are_synchronized(self) -> None:
        expected = lean_generator.render_lean_allowed_verifier_profiles()
        source = (
            ROOT / "SparkInterval/Execution/TrustedComputeKey.lean"
        ).read_text(encoding="utf-8")
        self.assertIn(expected, source)

    def test_source_key_rejects_any_issuer_tuple_substitution(self) -> None:
        mutations = (
            (("backend",), "azure_ncc40ads_h100_v5"),
            (("claim", "target_profile_hash"), "56" * 32),
            (("claim", "trust_profile_hash"), "78" * 32),
            (("verifier", "artifact_sha256"), "12" * 32),
            (("verifier", "policy_sha256"), "34" * 32),
        )
        for path_fields, value in mutations:
            with self.subTest(field=path_fields), tempfile.TemporaryDirectory() as temporary:
                receipt = self.fixture()
                if len(path_fields) == 1:
                    receipt[path_fields[0]] = value
                else:
                    receipt[path_fields[0]][path_fields[1]] = value
                core = {
                    key: item
                    for key, item in receipt.items()
                    if key != "receipt_sha256"
                }
                receipt["receipt_sha256"] = bundles.canonical_sha256(core)
                path = Path(temporary) / "receipt.json"
                path.write_bytes(bundles.canonical_json_bytes(receipt))
                with self.assertRaisesRegex(
                    receipts.ReceiptError,
                    "tuple is not source-approved|target/trust class",
                ):
                    lean_generator.load_verified_receipt(
                        path, allow_development_key=True
                    )

    def test_key_manifest_rejects_wildcard_or_empty_profile_allowlist(self) -> None:
        original = json.loads(
            lean_generator.DEFAULT_KEY_MANIFEST.read_text(encoding="utf-8")
        )
        cases = ([], [{
            "backend": "*",
            "target_profile_sha256": "56" * 32,
            "trust_profile_sha256": "78" * 32,
            "verifier_artifact_sha256": "12" * 32,
            "verifier_policy_sha256": "34" * 32,
        }])
        for profiles in cases:
            with self.subTest(profiles=profiles), tempfile.TemporaryDirectory() as temporary:
                manifest = copy.deepcopy(original)
                manifest["keys"][0]["allowed_verifier_profiles"] = profiles
                path = Path(temporary) / "keys.json"
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(receipts.ReceiptError):
                    lean_generator.load_key_manifest(path)

    def test_key_manifest_rejects_one_public_key_under_two_identities(self) -> None:
        original = json.loads(
            lean_generator.DEFAULT_KEY_MANIFEST.read_text(encoding="utf-8")
        )
        duplicate = copy.deepcopy(original["keys"][0])
        duplicate["key_id"] = "production-alias-of-development-key"
        duplicate["classification"] = "production"
        original["keys"].append(duplicate)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "keys.json"
            path.write_text(json.dumps(original), encoding="utf-8")
            with self.assertRaisesRegex(
                receipts.ReceiptError, "duplicate verifier public-key hash"
            ):
                lean_generator.load_key_manifest(path)

    def test_manifest_profile_hashes_match_tracked_canonical_profiles(self) -> None:
        profile_paths = {
            "azure_sevsnp_cpu": (
                ROOT / "profiles/targets/azure_sevsnp_cpu.json",
                ROOT / "profiles/trust/azure_sevsnp_hardware_attested.json",
                "27c1f9d99d4a2bafae009c09310eec8bd710663bcdc463f90244019da1f948d5",
                "dfec83fa16f6740346d6d9d79c02200e2bdd2757d30e6252b96e670c5b540e72",
            ),
            "azure_ncc40ads_h100_v5": (
                ROOT / "profiles/targets/azure_ncc40ads_h100_v5.json",
                ROOT / "profiles/trust/azure_ncc_sevsnp_vtpm_nvidia_cc_attested.json",
                "10302dda365aba07494b46ccc3454403b04d4160071d48ec91ebbf5c8ce17c52",
                "0efa3eb67122dfbcd8261ba6037564ee55b7693b0a02956baecdbbb70567b444",
            ),
        }
        recomputed: dict[str, tuple[str, str]] = {}
        for backend, (target_path, trust_path, target_expected, trust_expected) in (
            profile_paths.items()
        ):
            target = bundles.parse_json_bytes(target_path.read_bytes(), str(target_path))
            trust = bundles.parse_json_bytes(trust_path.read_bytes(), str(trust_path))
            target_hash = bundles.canonical_sha256(target)
            trust_hash = bundles.canonical_sha256(trust)
            self.assertEqual(target_hash, target_expected, backend)
            self.assertEqual(trust_hash, trust_expected, backend)
            recomputed[backend] = (target_hash, trust_hash)

        manifest = lean_generator.load_key_manifest(
            lean_generator.DEFAULT_KEY_MANIFEST
        )
        for key in manifest.values():
            for profile in key["allowed_verifier_profiles"]:
                with self.subTest(backend=profile["backend"]):
                    target_hash, trust_hash = recomputed[profile["backend"]]
                    self.assertEqual(
                        profile["target_profile_sha256"], target_hash
                    )
                    self.assertEqual(profile["trust_profile_sha256"], trust_hash)

    def test_key_manifest_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "keys.json"
            path.write_text(
                '{"schema_version":1,"schema_version":1,"keys":[]}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(receipts.ReceiptError, "duplicate JSON key"):
                lean_generator.load_key_manifest(path)

    def test_manifest_relative_public_key_cannot_escape_through_symlink(self) -> None:
        original = json.loads(
            lean_generator.DEFAULT_KEY_MANIFEST.read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original["keys"][0]["public_key_path"] = "escaped.pem"
            manifest = root / "keys.json"
            manifest.write_text(json.dumps(original), encoding="utf-8")
            target = (
                lean_generator.DEFAULT_KEY_MANIFEST.parent
                / "sparkinterval-bootstrap-rsa3072-2026-07-public.pem"
            )
            (root / "escaped.pem").symlink_to(target)
            with self.assertRaisesRegex(receipts.ReceiptError, "escapes through a symlink"):
                lean_generator.verified_public_key(
                    self.fixture(),
                    key_manifest=manifest,
                    public_key=None,
                    allow_development_key=True,
                )

    def test_lean_consumer_refuses_development_key_even_when_diagnostics_allow_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "DevelopmentConsumer.lean"
            with contextlib.redirect_stderr(io.StringIO()):
                status = lean_generator.main(
                    [
                        str(FIXTURE),
                        "--namespace",
                        "DevelopmentConsumer",
                        "--out",
                        str(destination),
                        "--allow-development-key",
                    ]
                )
            self.assertEqual(status, 2)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
