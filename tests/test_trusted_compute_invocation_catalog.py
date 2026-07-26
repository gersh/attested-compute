# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import create_run_bundle as bundles  # noqa: E402
import generate_production_deployment_candidate as deployment_candidate  # noqa: E402
import generate_trusted_compute_lean as lean_generator  # noqa: E402
import generate_trusted_compute_registry as registry_generator  # noqa: E402
from tg_verifier import sqrt218_fixed_v2_receipt as fixed_v2  # noqa: E402


FIXTURE = ROOT / "tests/fixtures/trusted_compute_cpu_receipt.json"
REGISTERED_ALGORITHM = ROOT / "SparkInterval/Execution/RegisteredAlgorithm.lean"


def lean_registered_invocations() -> tuple[str, ...]:
    """Read the closed constructor catalog that defines Lean run semantics."""

    source = REGISTERED_ALGORITHM.read_text(encoding="utf-8")
    try:
        block = source.split("inductive RegisteredInvocation where", 1)[1]
        block = block.split("deriving Repr, DecidableEq, BEq", 1)[0]
    except IndexError as error:
        raise AssertionError("cannot locate Lean RegisteredInvocation catalog") from error
    constructors = tuple(
        re.findall(r"^\s*\|\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", block, re.MULTILINE)
    )
    if not constructors:
        raise AssertionError("Lean RegisteredInvocation catalog is empty")
    return constructors


class TrustedComputeInvocationCatalogTests(unittest.TestCase):
    def fixture_for(self, invocation: str) -> dict:
        receipt = copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))
        backend = lean_generator.registered_invocation_backend(invocation)
        if backend is not None:
            receipt["backend"] = backend
        receipt["claim"].update(
            lean_generator.registered_invocation_expected(invocation)
        )
        core = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        return receipt

    def fixed_v2_fixture(self) -> tuple[dict, dict]:
        """Build a tiny receipt/pin identity without any certificate replay."""

        receipt = copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))
        certificate_sha256 = "42" * 32
        certificate_size_bytes = 160
        native_result = bytearray(fixed_v2.NATIVE_RESULT_BYTES)
        native_result[0:8] = b"SQ218R2\x00"
        native_result[8:10] = (1).to_bytes(2, "big")
        native_result[10:12] = fixed_v2.NATIVE_RESULT_BYTES.to_bytes(2, "big")
        native_result[12:16] = (0).to_bytes(4, "big")
        native_result[16:24] = certificate_size_bytes.to_bytes(8, "big")
        native_result[88:120] = bytes.fromhex(certificate_sha256)
        result = fixed_v2.encode_result_envelope(bytes(native_result))

        pins = {
            "algorithm_hash": (
                "cefa3f3eccfc3505923d1c37f6007661"
                "27473a1a8a097b2e9097cede014011d6"
            ),
            "algorithm_id": fixed_v2.ALGORITHM_ID,
            "certificate_sha256": certificate_sha256,
            "certificate_size_bytes": certificate_size_bytes,
            "checker_executable_sha256": receipt["claim"]["artifacts"][
                "host_executable_hash"
            ],
            "device_cubin_sha256": receipt["claim"]["artifacts"][
                "device_cubin_hash"
            ],
            "domain_hash": (
                "e27ff5ea0864cfbaa3a2618bcc6e79ff"
                "82ad0767c74473e8f88bef9670d6ecc9"
            ),
            "execution_closure_sha256": receipt["claim"]["artifacts"][
                "kernel_manifest_hash"
            ],
            "kind": fixed_v2.REVIEWED_PINS_KIND,
            "parameters_hash": (
                "11a8b0f784e4846b10c46669d04d349b"
                "a13640c08ba782fe0ac1450246ab379f"
            ),
            "receipt_sha256": "11" * 32,
            "schema_version": 1,
            "source_tree_hash": receipt["claim"]["artifacts"][
                "source_tree_hash"
            ],
            "target_profile_hash": receipt["claim"]["target_profile_hash"],
            "trust_profile_hash": receipt["claim"]["trust_profile_hash"],
            "verifier_artifact_sha256": receipt["verifier"][
                "artifact_sha256"
            ],
            "verifier_key_id": receipt["verifier"]["key_id"],
            "verifier_policy_sha256": receipt["verifier"]["policy_sha256"],
            "wire_statement_sha256": receipt["bindings"][
                "wire_statement_sha256"
            ],
        }
        expected = lean_generator.registered_invocation_expected(
            lean_generator.SQRT218_FIXED_V2_INVOCATION,
            sqrt218_fixed_v2_reviewed_pins=pins,
        )
        receipt["claim"].update(expected)
        receipt["claim"]["result"] = result
        receipt["claim"]["output_hash"] = hashlib.sha256(
            result.encode("utf-8")
        ).hexdigest()
        core = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        receipt["receipt_sha256"] = bundles.canonical_sha256(core)
        pins["receipt_sha256"] = receipt["receipt_sha256"]
        return receipt, pins

    def test_python_importer_is_complete_for_the_closed_lean_catalog(self) -> None:
        lean_catalog = lean_registered_invocations()
        self.assertEqual(lean_generator.REGISTERED_INVOCATIONS, lean_catalog)

        for invocation in lean_catalog:
            with self.subTest(invocation=invocation):
                if invocation == lean_generator.SQRT218_FIXED_V2_INVOCATION:
                    receipt, pins = self.fixed_v2_fixture()
                else:
                    receipt = self.fixture_for(invocation)
                    pins = None
                self.assertEqual(
                    lean_generator.validate_source_admitted_registered_invocation(
                        receipt,
                        sqrt218_fixed_v2_reviewed_pins=pins,
                    ),
                    invocation,
                )
                source = lean_generator.generate(
                    receipt,
                    "CatalogCompleteness",
                    invocation,
                    sqrt218_fixed_v2_reviewed_pins=pins,
                )
                self.assertIn(
                    f"RegisteredInvocation.{invocation}.Runs", source
                )
                if invocation != "cubicSumDivThree20000V1":
                    self.assertIn(
                        "import SparkInterval.Execution.Registered", source
                    )
                self.assertIn("theorem applicationResult", source)
                self.assertIn("theorem exactMathematicalResult", source)

    def test_fixed_v2_generation_uses_exact_dynamic_receipt_pins(self) -> None:
        invocation = lean_generator.SQRT218_FIXED_V2_INVOCATION
        receipt, pins = self.fixed_v2_fixture()
        expected = lean_generator.registered_invocation_expected(
            invocation,
            sqrt218_fixed_v2_reviewed_pins=pins,
        )
        self.assertEqual(
            expected,
            {
                "algorithm_id": fixed_v2.ALGORITHM_ID,
                "algorithm_hash": pins["algorithm_hash"],
                "input_hash": pins["certificate_sha256"],
                "parameters_hash": pins["parameters_hash"],
                "domain_hash": pins["domain_hash"],
                "target": "azure_sevsnp_cpu",
                "trust": "azure_sevsnp_confidential_compute",
            },
        )
        lean_generator.validate_bound_registered_results(
            receipt,
            sqrt218_fixed_v2_reviewed_pins=pins,
        )
        source = lean_generator.generate(
            receipt,
            "Sqrt218FixedV2MeasuredRun",
            invocation,
            sqrt218_fixed_v2_reviewed_pins=pins,
        )
        self.assertIn(
            "import SparkInterval.Execution."
            "RegisteredSqrt218FixedV2Certificate",
            source,
        )
        self.assertIn(
            "RegisteredInvocation.helfgottSqrt218FixedProductionV2.Runs",
            source,
        )
        self.assertIn(
            "reviewedSqrt218FixedV2DeploymentCheck",
            source,
        )
        self.assertIn(
            "helfgottSqrt218FixedProductionV2_sourceClaim",
            source,
        )
        self.assertNotIn("\n  native_decide", source)

    def test_fixed_v2_generation_fails_closed_on_missing_or_wrong_pins(
        self,
    ) -> None:
        invocation = lean_generator.SQRT218_FIXED_V2_INVOCATION
        receipt, pins = self.fixed_v2_fixture()
        with self.assertRaisesRegex(
            lean_generator.ReceiptError, "requires exact reviewed pins"
        ):
            lean_generator.generate(receipt, "MissingPins", invocation)

        mismatches = {
            "certificate_size_bytes": pins["certificate_size_bytes"] + 1,
            "receipt_sha256": "12" * 32,
            "source_tree_hash": "13" * 32,
            "verifier_policy_sha256": "14" * 32,
            "wire_statement_sha256": "15" * 32,
        }
        for field, value in mismatches.items():
            with self.subTest(field=field):
                changed_pins = copy.deepcopy(pins)
                changed_pins[field] = value
                with self.assertRaises(lean_generator.ReceiptError):
                    lean_generator.generate(
                        receipt,
                        "WrongPins",
                        invocation,
                        sqrt218_fixed_v2_reviewed_pins=changed_pins,
                    )

        malformed_result = copy.deepcopy(receipt)
        malformed_result["claim"]["result"] = (
            malformed_result["claim"]["result"][:-1] + "A"
        )
        with self.assertRaisesRegex(
            lean_generator.ReceiptError, "result envelope"
        ):
            lean_generator.validate_bound_registered_results(
                malformed_result,
                sqrt218_fixed_v2_reviewed_pins=pins,
            )

    def test_fixed_v2_registry_and_candidate_use_the_same_exact_fields(
        self,
    ) -> None:
        receipt, pins = self.fixed_v2_fixture()
        source = registry_generator.generate_registry(
            [receipt],
            admission_time="2026-07-21T12:00:00Z",
            sqrt218_fixed_v2_reviewed_pins=pins,
        )
        self.assertIn(
            "importedTrustedComputeRun_" + receipt["receipt_sha256"],
            source,
        )
        with self.assertRaises(lean_generator.ReceiptError):
            registry_generator.generate_registry([receipt])
        changed_pins = copy.deepcopy(pins)
        changed_pins["certificate_size_bytes"] += 1
        with self.assertRaises(lean_generator.ReceiptError):
            registry_generator.generate_registry(
                [receipt],
                sqrt218_fixed_v2_reviewed_pins=changed_pins,
            )

        self.assertEqual(
            deployment_candidate.fixed_v2_reviewed_pins_from_verified_receipt(
                receipt
            ),
            pins,
        )
        candidate_source = deployment_candidate.generate_candidate(receipt)
        self.assertIn(
            "Option ReviewedSqrt218FixedV2Deployment := some",
            candidate_source,
        )
        self.assertIn(
            f'certificateSHA256 := "{pins["certificate_sha256"]}"',
            candidate_source,
        )
        self.assertIn(
            f'certificateBytes := {pins["certificate_size_bytes"]}',
            candidate_source,
        )
        for value in (
            pins["receipt_sha256"],
            pins["target_profile_hash"],
            pins["trust_profile_hash"],
            pins["source_tree_hash"],
            pins["checker_executable_sha256"],
            pins["device_cubin_sha256"],
            pins["execution_closure_sha256"],
        ):
            self.assertIn(f'"{value}"', candidate_source)

        wrong_input = copy.deepcopy(receipt)
        wrong_input["claim"]["input_hash"] = "16" * 32
        with self.assertRaises(lean_generator.ReceiptError):
            deployment_candidate.generate_candidate(wrong_input)

    def test_fixed_v2_cli_loads_pins_only_after_receipt_verification(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt_path = root / "receipt.json"
            pins_path = root / "pins.json"
            output_path = root / "Registry.lean"
            receipt_path.write_text("{}", encoding="utf-8")
            pins_path.write_text("{}", encoding="utf-8")
            with mock.patch.object(
                registry_generator,
                "load_verified_receipt",
                side_effect=lean_generator.ReceiptError(
                    "signature/source-key verification failed"
                ),
            ), mock.patch.object(
                registry_generator.sqrt218_fixed_v2_receipt,
                "load_canonical_reviewed_pins",
                side_effect=AssertionError("pins loaded before receipt"),
            ), contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = registry_generator.main([
                    str(receipt_path),
                    "--sqrt218-fixed-v2-reviewed-pins",
                    str(pins_path),
                    "--out",
                    str(output_path),
                ])
            self.assertEqual(status, 2)
            self.assertIn("signature/source-key verification failed", stderr.getvalue())

    def test_malformed_fixed_v2_pin_files_fail_without_tracebacks(self) -> None:
        receipt, _pins = self.fixed_v2_fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pins_path = root / "bad-pins.json"
            pins_path.write_text("{}", encoding="utf-8")
            output_path = root / "Generated.lean"
            with mock.patch.object(
                lean_generator, "load_verified_receipt", return_value=receipt
            ), mock.patch.object(
                lean_generator, "require_production_verifier", return_value=None
            ), contextlib.redirect_stderr(io.StringIO()):
                lean_status = lean_generator.main([
                    "receipt.json",
                    "--namespace",
                    "BadPins",
                    "--registered-invocation",
                    lean_generator.SQRT218_FIXED_V2_INVOCATION,
                    "--sqrt218-fixed-v2-reviewed-pins",
                    str(pins_path),
                    "--out",
                    str(output_path),
                ])
            self.assertEqual(lean_status, 2)

            with mock.patch.object(
                registry_generator,
                "load_verified_receipt",
                return_value=receipt,
            ), contextlib.redirect_stderr(io.StringIO()):
                registry_status = registry_generator.main([
                    "receipt.json",
                    "--sqrt218-fixed-v2-reviewed-pins",
                    str(pins_path),
                    "--out",
                    str(output_path),
                ])
            self.assertEqual(registry_status, 2)

    def test_ramare_zuniga_receipt_identity_and_application_branch(self) -> None:
        invocation = "ramareZunigaLemma62ProductionV1"
        expected = lean_generator.registered_invocation_expected(invocation)
        self.assertEqual(
            expected,
            {
                "algorithm_id": (
                    "sparkinterval.ternary-goldbach."
                    "ramare-zuniga-lemma-6-2.v1"
                ),
                "algorithm_hash": (
                    "1c95ab10e8f25ed7f87739bc2ea13190b"
                    "b32e520272f05a3611d13b95e7f9d9c"
                ),
                "input_hash": (
                    "386168a18f1c8639736118a2beb057efe"
                    "0a1a53871561a9a7b54dafd50024c5c"
                ),
                "parameters_hash": (
                    "515707b2ec16c0ffa90cd4b36cb64353"
                    "e1da4f93a2c94dd21523fe42939407d5"
                ),
                "domain_hash": (
                    "9cafd963de87e0f4f36904a616a9191b"
                    "7fdf1b4ae29d05fe12a27bc60c6392f3"
                ),
                "result": "true",
                "output_hash": (
                    "b5bea41b6c623f7c09f1bf24dcae58e"
                    "bab3c0cdd90ad966bc43a45b44867e12b"
                ),
                "target": "nvidia_h100_sm90",
                "trust": "nvidia_h100_confidential_compute",
            },
        )
        self.assertEqual(
            lean_generator.registered_invocation_backend(invocation),
            "azure_ncc40ads_h100_v5",
        )

        source = lean_generator.generate(
            self.fixture_for(invocation), "RamareZunigaMeasuredRun", invocation
        )
        self.assertIn(
            "import SparkInterval.Execution.RegisteredR2StarCertificate", source
        )
        self.assertIn(
            "RegisteredInvocation.ramareZunigaLemma62ProductionV1.Runs", source
        )
        self.assertIn("R2StarSourceSemantics.SourceClaim", source)
        self.assertIn("ramareZunigaLemma62ProductionV1_sourceClaim", source)

    def test_a7_receipt_identity_and_application_branch(self) -> None:
        invocation = "ch25A7BoundaryProductionV1"
        expected = lean_generator.registered_invocation_expected(invocation)
        self.assertEqual(
            expected,
            {
                "algorithm_id": (
                    "sparkinterval.ternary-goldbach."
                    "ch25-lemma-a7-boundary.v1"
                ),
                "algorithm_hash": (
                    "340dc36f2ceb992ab16e34c534cd97b7"
                    "86d348ba057e159c295b3abd1328cdfa"
                ),
                "input_hash": (
                    "4e45410d2d26467dbd5f78f8ea536b1"
                    "a8bbf44f1cd5248e234b985bd1f595674"
                ),
                "parameters_hash": (
                    "f377fb7b8c8d8d033083a0759841411d"
                    "9bb955e919041f2a5b5be830ed69212e"
                ),
                "domain_hash": (
                    "629d9c7b3c084ef33f69d92abbe22b5"
                    "120bac210fc963191c4b1e8289ff1dea5"
                ),
                "result": "true",
                "output_hash": (
                    "b5bea41b6c623f7c09f1bf24dcae58e"
                    "bab3c0cdd90ad966bc43a45b44867e12b"
                ),
                "target": "azure_sevsnp_cpu",
                "trust": "azure_sevsnp_confidential_compute",
            },
        )
        self.assertEqual(
            lean_generator.registered_invocation_backend(invocation),
            "azure_sevsnp_cpu",
        )

        source = lean_generator.generate(
            self.fixture_for(invocation), "CH25A7MeasuredRun", invocation
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


if __name__ == "__main__":
    unittest.main()
