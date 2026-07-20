from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "SparkInterval" / "Blueprint.lean"

ATTRIBUTE_RE = re.compile(
    r"attribute\s+\[blueprint(?P<body>.*?)\]\s+"
    r"(?P<target>SparkInterval(?:\.[A-Za-z_][A-Za-z0-9_]*)+)",
    re.DOTALL,
)


def annotated_declarations(text: str) -> set[str]:
    """Return declaration targets of post-hoc LeanArchitect attributes."""
    return set(annotation_bodies(text))


def annotation_bodies(text: str) -> dict[str, str]:
    """Map each annotated declaration to its raw Blueprint options."""
    return {
        match.group("target"): match.group("body")
        for match in ATTRIBUTE_RE.finditer(text)
    }


class BlueprintIntegrationTests(unittest.TestCase):
    def test_architect_import_is_isolated_to_metadata_registry(self) -> None:
        importers = [
            path.relative_to(ROOT)
            for path in sorted((ROOT / "SparkInterval").rglob("*.lean"))
            if "import Architect" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(importers, [Path("SparkInterval/Blueprint.lean")])

    def test_registry_marks_the_single_execution_axiom_as_trust_axiom(self) -> None:
        text = REGISTRY.read_text(encoding="utf-8")
        bodies = annotation_bodies(text)
        axiom = "SparkInterval.Execution.Trusted.accepted_run_certificate_sound"
        checker = "SparkInterval.Execution.RunCertificate.check"
        body = bodies[axiom]
        self.assertIn("TRUST AXIOM", body)
        self.assertIn("hasProof := false", body)
        self.assertIn(checker, body)
        self.assertEqual(
            [target for target, raw in bodies.items() if "TRUST AXIOM" in raw],
            [axiom],
        )
        checker_body = bodies[checker]
        self.assertIn("SparkInterval.Execution.checkDGXOperatorSignature", checker_body)
        self.assertIn("SparkInterval.Execution.checkH100Attestation", checker_body)

    def test_registry_exposes_nvidia_transcription_and_refinement(self) -> None:
        text = REGISTRY.read_text(encoding="utf-8")
        targets = annotated_declarations(text)
        expected = {
            # Pinned source, citation map, and independent transcription.
            "SparkInterval.PTX.NvidiaPTX90.sourcePin",
            "SparkInterval.PTX.NvidiaPTX90.Clause.reference",
            "SparkInterval.PTX.NvidiaPTX90.opcodeClause",
            "SparkInterval.PTX.NvidiaPTX90.allowedOpcode_has_pinned_clause",
            "SparkInterval.PTX.NvidiaPTX90.evalFinite",
            "SparkInterval.Binary64Rounding.roundDown_le",
            "SparkInterval.Binary64Rounding.le_roundUp",
            "SparkInterval.PTX.NvidiaPTX90.minimum",
            "SparkInterval.PTX.NvidiaPTX90.maximum",
            "SparkInterval.PTX.NvidiaPTX90.dgxSparkProfile",
            "SparkInterval.PTX.NvidiaPTX90.division_not_in_current_allowlist",
            "SparkInterval.PTX.F64Value.minimum",
            "SparkInterval.PTX.F64Value.maximum",
            # Refinement from the library's typed arithmetic and machine step.
            "SparkInterval.PTX.NvidiaPTX90.directedBinary_finite_refines",
            "SparkInterval.PTX.NvidiaPTX90.minimum_nonNaN_refines",
            "SparkInterval.PTX.NvidiaPTX90.maximum_nonNaN_refines",
            "SparkInterval.PTX.NvidiaPTX90.executeInstruction_binaryF64_finite_refines",
            "SparkInterval.PTX.NvidiaPTX90.executeInstruction_minimumF64_nonNaN_refines",
            "SparkInterval.PTX.NvidiaPTX90.executeInstruction_maximumF64_nonNaN_refines",
            # Honest aggregate: useful evidence, explicitly not full conformance.
            "SparkInterval.PTX.NvidiaPTX90.GeneratedModulePartialPTX90Evidence",
            "SparkInterval.PTX.NvidiaPTX90.buildModule_has_partial_ptx90_evidence",
        }
        self.assertEqual(expected - targets, set())
        self.assertIn("import SparkInterval.PTX.NvidiaPTXRefinement", text)

    def test_registry_declares_json_visible_nvidia_proof_edges(self) -> None:
        bodies = annotation_bodies(REGISTRY.read_text(encoding="utf-8"))
        expected_edges = {
            "SparkInterval.PTX.NvidiaPTX90.evalFinite_towardNegative_le": (
                "SparkInterval.PTX.NvidiaPTX90.evalFinite",
                "SparkInterval.Binary64Rounding.roundDown_le",
            ),
            "SparkInterval.PTX.NvidiaPTX90.le_evalFinite_towardPositive": (
                "SparkInterval.PTX.NvidiaPTX90.evalFinite",
                "SparkInterval.Binary64Rounding.le_roundUp",
            ),
            "SparkInterval.PTX.NvidiaPTX90.directedBinary_finite_refines": (
                "SparkInterval.PTX.directedBinary",
                "SparkInterval.PTX.NvidiaPTX90.evalFinite",
            ),
            "SparkInterval.PTX.NvidiaPTX90.minimum_nonNaN_refines": (
                "SparkInterval.PTX.F64Value.minimum",
                "SparkInterval.PTX.NvidiaPTX90.minimum",
            ),
            "SparkInterval.PTX.NvidiaPTX90.maximum_nonNaN_refines": (
                "SparkInterval.PTX.F64Value.maximum",
                "SparkInterval.PTX.NvidiaPTX90.maximum",
            ),
            "SparkInterval.PTX.NvidiaPTX90.executeInstruction_binaryF64_finite_refines": (
                "SparkInterval.PTX.executeInstruction",
                "SparkInterval.PTX.NvidiaPTX90.evalFinite",
                "SparkInterval.PTX.NvidiaPTX90.directedBinary_finite_refines",
            ),
            "SparkInterval.PTX.NvidiaPTX90.buildModule_has_partial_ptx90_evidence": (
                "SparkInterval.PTX.NvidiaPTX90.GeneratedModulePartialPTX90Evidence",
                "SparkInterval.PTX.NvidiaPTX90.renderUnchecked_startsWith_dgxSparkProfile",
                "SparkInterval.PTX.NvidiaPTX90.buildModule_opcodeTrace_all_have_pinned_clauses",
                "SparkInterval.PTX.NvidiaPTX90.directedBinary_finite_refines",
                "SparkInterval.PTX.NvidiaPTX90.minimum_nonNaN_refines",
                "SparkInterval.PTX.NvidiaPTX90.maximum_nonNaN_refines",
            ),
            "SparkInterval.PTX.NvidiaPTX90.division_not_in_current_allowlist": (
                "SparkInterval.PTX.NvidiaPTX90.opcodeClause",
            ),
        }
        for target, dependencies in expected_edges.items():
            with self.subTest(target=target):
                body = bodies[target]
                for dependency in dependencies:
                    self.assertIn(dependency, body)

    def test_registry_declares_json_visible_result_proof_edges(self) -> None:
        bodies = annotation_bodies(REGISTRY.read_text(encoding="utf-8"))
        expected_proof_edges = {
            "SparkInterval.PTX.addFragmentResult_contains": (
                "SparkInterval.Binary64Rounding.roundDown_le",
                "SparkInterval.Binary64Rounding.le_roundUp",
            ),
            "SparkInterval.PTX.subFragmentResult_contains": (
                "SparkInterval.Binary64Rounding.roundDown_le",
                "SparkInterval.Binary64Rounding.le_roundUp",
            ),
            "SparkInterval.PTX.mulFragmentResult_contains": (
                "SparkInterval.Binary64Rounding.roundDown_le",
                "SparkInterval.Binary64Rounding.le_roundUp",
            ),
            "SparkInterval.PTX.guardedBinary_contains": (
                "SparkInterval.PTX.addFragmentResult_contains",
                "SparkInterval.PTX.subFragmentResult_contains",
                "SparkInterval.PTX.mulFragmentResult_contains",
            ),
            "SparkInterval.PTX.PolynomialExpr.evalKernel_sound": (
                "SparkInterval.PTX.guardedBinary_contains",
            ),
            "SparkInterval.PTX.runBuildModule_inRange": (
                "SparkInterval.PTX.executeBuildModuleStructured_inRange",
            ),
            "SparkInterval.PTX.runBuildModule_inRange_containsReal": (
                "SparkInterval.PTX.PolynomialExpr.evalKernel_sound",
                "SparkInterval.PTX.runBuildModule_inRange",
            ),
            "SparkInterval.Execution.SignedResultCertificate.checkUpperBound_sound": (
                "SparkInterval.Execution.Trusted.accepted_run_certificate_sound",
                "SparkInterval.Execution.SignedResultCertificate.resultBindingCheck_sound",
                "SparkInterval.Certificate.impliesTheorem",
            ),
            "SparkInterval.Execution.SignedResultCertificate.outcomeCheck_sound": (
                "SparkInterval.Execution.Trusted.accepted_run_certificate_sound",
                "SparkInterval.Execution.SignedResultCertificate.resultBindingCheck_sound",
            ),
            "SparkInterval.Execution.SignedResultCertificate.outcomeCheckForAlgorithm_sound": (
                "SparkInterval.Execution.SignedResultCertificate.executableIdentityCheck_sound",
                "SparkInterval.Execution.SignedResultCertificate.outcomeCheck_sound",
            ),
            "SparkInterval.Execution.SignedResultCertificate.checkSumUpperBound_sound": (
                "SparkInterval.Execution.Trusted.accepted_run_certificate_sound",
                "SparkInterval.Execution.SignedResultCertificate.resultBindingCheck_sound",
                "SparkInterval.Certificate.impliesSumTheorem",
            ),
            "SparkInterval.Execution.SignedResultCertificate.checkUpperBoundForAlgorithm_sound": (
                "SparkInterval.Execution.SignedResultCertificate.executableIdentityCheck_sound",
                "SparkInterval.Execution.SignedResultCertificate.checkUpperBound_sound",
            ),
            "SparkInterval.Execution.SignedResultCertificate.checkSumUpperBoundForAlgorithm_sound": (
                "SparkInterval.Execution.SignedResultCertificate.executableIdentityCheck_sound",
                "SparkInterval.Execution.SignedResultCertificate.checkSumUpperBound_sound",
            ),
        }
        for target, dependencies in expected_proof_edges.items():
            with self.subTest(target=target):
                body = bodies[target]
                self.assertIn("proofUses :=", body)
                for dependency in dependencies:
                    self.assertIn(dependency, body)

    def test_registry_exposes_signed_exact_algorithm_composition(self) -> None:
        text = REGISTRY.read_text(encoding="utf-8")
        targets = annotated_declarations(text)
        expected = {
            "SparkInterval.Execution.SignedResultCertificate.resultBindingCheck_sound",
            "SparkInterval.Execution.SignedResultCertificate.resultBindingCheck",
            "SparkInterval.Execution.SignedResultCertificate.outcomeCheck_sound",
            "SparkInterval.Execution.SignedResultCertificate.outcomeCheck",
            "SparkInterval.Execution.SignedResultCertificate.outcomeCheckForAlgorithm_sound",
            "SparkInterval.Execution.SignedResultCertificate.executableIdentityCheck_sound",
            "SparkInterval.Execution.SignedResultCertificate.executableIdentityCheck",
            "SparkInterval.Execution.SignedResultCertificate.checkUpperBound_sound",
            "SparkInterval.Execution.SignedResultCertificate.checkSumUpperBound_sound",
            "SparkInterval.Execution.SignedResultCertificate.checkUpperBoundForAlgorithm_sound",
            "SparkInterval.Execution.SignedResultCertificate.checkSumUpperBoundForAlgorithm_sound",
            "SparkInterval.PTX.runBuildModule_inRange_containsReal",
            "SparkInterval.Blueprint.executableIdentityToFormalArtifactGap",
        }
        self.assertEqual(expected - targets, set())
        self.assertIn(
            "import SparkInterval.Execution.SignedResultCertificateComposition",
            text,
        )
        self.assertIn(
            'title := "Pinned algorithm ID/hash, signed execution, and checked row bounds"',
            text,
        )
        self.assertIn(
            'title := "Pinned algorithm ID/hash, signed execution, and checked sum bound"',
            text,
        )
        self.assertRegex(
            text,
            re.compile(
                r'blueprint "gap:executable-identity-to-formal-artifact"'
                r'.*?\(notReady := true\).*?\]\s+'
                r'SparkInterval\.Blueprint\.executableIdentityToFormalArtifactGap',
                re.DOTALL,
            ),
        )
        bodies = annotation_bodies(text)
        self.assertIn(
            "SparkInterval.Execution.SignedResultCertificate.resultBindingCheck",
            bodies[
                "SparkInterval.Execution.SignedResultCertificate.resultBindingCheck_sound"
            ],
        )
        self.assertIn(
            "SparkInterval.Execution.SignedResultCertificate.executableIdentityCheck",
            bodies[
                "SparkInterval.Execution.SignedResultCertificate.executableIdentityCheck_sound"
            ],
        )

    def test_registry_exposes_high_bound_zeta_composition(self) -> None:
        text = REGISTRY.read_text(encoding="utf-8")
        bodies = annotation_bodies(text)
        expected = {
            "SparkInterval.Execution.SignedZetaEndpointPayload.payloadCheck",
            "SparkInterval.Execution.SignedZetaEndpointPayload.batchBindingCheck_sound",
            "SparkInterval.Execution.SignedZetaEndpointPayload.check_sound",
            "SparkInterval.Execution.SignedZetaEndpointPayload.CheckedPayload.enclosesEndpoints",
            "SparkInterval.Execution.SignedZetaEndpointPayload.verifyFiniteHeight",
            "SparkInterval.Execution.SignedZetaEndpointPayload.verifyFiniteHeightFromCheckedRows",
            "SparkInterval.Execution.SignedZetaEndpointPayload.verifyFiniteHeightFromPositiveCount",
            "SparkInterval.Execution.SignedZetaEndpointPayload.verifyFiniteHeightFromPositiveRows",
            "SparkInterval.Execution.SignedResultCertificate.certifyCompactFiniteHeightZeta",
            "SparkInterval.Zeta.zetaZeroMultiplicityCount_partition",
            "SparkInterval.Zeta.ZetaConjugationMultiplicitySymmetry.negative_eq_positive",
            "SparkInterval.Zeta.PositiveZetaMultiplicityCountUpperBound.toZetaMultiplicityCountUpperBound",
            "SparkInterval.Zeta.runEndpointChunk_append",
            "SparkInterval.Zeta.checkEndpointStream_isValid",
            "SparkInterval.Zeta.runEndpointChunkStream_append",
            "SparkInterval.Zeta.verifyEndpointChunkStream",
            "SparkInterval.Blueprint.hardyZRiemannSiegelGap",
            "SparkInterval.Blueprint.turingCountGap",
            "SparkInterval.Blueprint.streamingZetaCheckerGap",
        }
        self.assertEqual(expected - set(bodies), set())
        self.assertIn("import SparkInterval.Execution.SignedZetaVerifier", text)
        self.assertIn("import SparkInterval.Zeta.SymmetricCount", text)
        self.assertIn("import SparkInterval.Zeta.StreamingEndpointCertificate", text)
        self.assertIn("import SparkInterval.Zeta.StreamingChunkVerifier", text)
        self.assertIn("import SparkInterval.Zeta.EvenReflectionCertificate", text)
        self.assertIn("import SparkInterval.Execution.CompactAttestedVerifier", text)

        enclosure_body = bodies[
            "SparkInterval.Execution.SignedZetaEndpointPayload.CheckedPayload.enclosesEndpoints"
        ]
        self.assertIn(
            "SparkInterval.Certificate.FullCertificate.check_sound", enclosure_body
        )
        positive_body = bodies[
            "SparkInterval.Execution.SignedZetaEndpointPayload.verifyFiniteHeightFromPositiveCount"
        ]
        self.assertIn(
            "SparkInterval.Zeta.PositiveZetaMultiplicityCountUpperBound", positive_body
        )
        self.assertIn(
            "SparkInterval.Zeta.ZetaConjugationMultiplicitySymmetry", positive_body
        )
        streaming_gap = bodies[
            "SparkInterval.Blueprint.streamingZetaCheckerGap"
        ]
        self.assertIn("notReady := true", streaming_gap)
        self.assertIn("SparkInterval.Zeta.runEndpointChunk_append", streaming_gap)
        self.assertIn("SparkInterval.Zeta.verifyEndpointChunkStream", streaming_gap)

    def test_leanarchitect_revision_matches_toolchain_release(self) -> None:
        lakefile = (ROOT / "lakefile.toml").read_text(encoding="utf-8")
        toolchain = (ROOT / "lean-toolchain").read_text(encoding="utf-8")
        self.assertEqual(toolchain.strip(), "leanprover/lean4:v4.32.0-rc1")
        self.assertIn(
            'rev = "d9013cc08bd2b5483e837368dfa4cc7ead92a5c2"',
            lakefile,
        )
        self.assertLess(
            lakefile.index('name = "LeanArchitect"'),
            lakefile.index('name = "mathlib"'),
        )


if __name__ == "__main__":
    unittest.main()
