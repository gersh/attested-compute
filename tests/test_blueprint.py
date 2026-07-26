from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "SparkInterval" / "Blueprint.lean"

ATTRIBUTE_RE = re.compile(
    r"attribute\s+\[blueprint(?P<body>.*?)\]\s+"
    r"(?P<target>SparkInterval(?:\.[A-Za-z_][A-Za-z0-9_?]*)+)",
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
        self.assertIn("SparkInterval.Execution.checkTrustedCompute", checker_body)
        self.assertNotIn("SparkInterval.Execution.checkDGXOperatorSignature", checker_body)
        self.assertNotIn("SparkInterval.Execution.checkH100Attestation", checker_body)

    def test_registry_exposes_the_closed_h100_pilot_theorems(self) -> None:
        targets = annotated_declarations(REGISTRY.read_text(encoding="utf-8"))
        self.assertIn(
            "SparkInterval.Execution.h100FormalPtxConstantOnePTX_eq_formalEmitter",
            targets,
        )
        self.assertIn(
            "SparkInterval.Execution.SignedResultCertificate."
            "certifyH100FormalPtxConstantOne",
            targets,
        )

    def test_registry_exposes_verified_finite_replay_optimizations(self) -> None:
        text = REGISTRY.read_text(encoding="utf-8")
        bodies = annotation_bodies(text)
        expected = {
            "SparkInterval.Certificate.SHA256."
            "digestPrefixSlice_eq_digestByteArray_append_extract": (
                "SHA256.hashSource_eq_hashBytes_of_realizes",
                "SHA256.digestByteArray_eq_reference",
            ),
            "SparkInterval.TernaryGoldbach.Sqrt218CPUChecker."
            "CPureEntryComposition.CSuccessfulPureEntryTrace.sha256Correct": (
                "CSHA256Refinement.cReadWord_toNat",
                "CSHA256Refinement.cDigestByteArray_refines",
                "CSHA256Refinement.digest_correct_of_concreteExecution",
            ),
            "SparkInterval.TernaryGoldbach.R2StarReplaySegmentation."
            "foldSegments_eq_foldRows_flatten": (
                "R2StarReplaySegmentation.foldRows_append",
            ),
            "SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter."
            "exact_maximizer_inside_lower_threshold": (
                "HurstAffineCandidateFilter."
                "lower_outside_threshold_strictly_below",
            ),
            "SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter."
            "exact_minimizer_inside_upper_threshold": (
                "HurstAffineCandidateFilter."
                "upper_outside_threshold_strictly_above",
            ),
            "SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter."
            "lowerKey_min_assoc": (
                "HurstAffineCandidateFilter.lowerKey_injective",
                "HurstAffineCandidateFilter.upperKey_injective",
                "HurstAffineCandidateFilter.lowerKey_min_comm",
                "HurstAffineCandidateFilter.lowerKey_min_idem",
                "HurstAffineCandidateFilter.upperKey_min_assoc",
                "HurstAffineCandidateFilter.upperKey_min_comm",
                "HurstAffineCandidateFilter.upperKey_min_idem",
            ),
            "SparkInterval.TernaryGoldbach.MobiusFusedSupport."
            "pack_injective": (
                "MobiusFusedSupport.divisor_lt_productRadix",
                "MobiusFusedSupport.pack_lt_wordLimit",
                "MobiusFusedSupport.unpackProduct_pack",
                "MobiusFusedSupport.unpackCount_pack",
                "MobiusFusedSupport.unpackSquareful_pack",
            ),
            "SparkInterval.TernaryGoldbach.MobiusFusedSupport."
            "update_comm": (
                "MobiusFusedSupport.unpackProduct_pack_update",
                "MobiusFusedSupport.unpackCount_pack_update",
                "MobiusFusedSupport.unpackSquareful_pack_update",
            ),
            "SparkInterval.TernaryGoldbach.MobiusFusedSupport."
            "update_eq_markSquareful_updateProductCount": (
                "MobiusFusedSupport."
                "markSquareful_updateProductCount_comm",
                "MobiusFusedSupport.markSquareful_markSquareful_comm",
            ),
            "SparkInterval.TernaryGoldbach.MobiusResidualGCD."
            "one_lt_gcd_iff_exists_prime_square_dvd": (
                "MobiusResidualGCD."
                "squarefree_product_residual_iff_gcd_eq_one",
                "MobiusResidualGCD."
                "one_lt_gcd_iff_exists_product_prime_square_dvd",
                "MobiusResidualGCD."
                "cardDistinctFactors_parity_product_residual",
            ),
            "SparkInterval.TernaryGoldbach.MobiusDenseSchedule."
            "multipleOffset_injective": (
                "MobiusFusedSupport.update_comm",
                "MobiusDenseSchedule.flatBlock_decode",
                "MobiusDenseSchedule.primeIndex_lt",
                "MobiusDenseSchedule.event_block_thread_decode",
                "MobiusDenseSchedule.threadOwner_lt",
                "MobiusDenseSchedule.iterationOwner_lt",
                "MobiusDenseSchedule.event_mem_owner",
                "MobiusDenseSchedule.block_eq_eventOwner",
                "MobiusDenseSchedule.eventOwner_lt_slots",
                "MobiusDenseSchedule.multipleEventCount_le_capacity",
                "MobiusDenseSchedule."
                "residueMinimumSlots_sufficient_at_public_cap",
                "MobiusDenseSchedule."
                "residuePreviousSlotCount_insufficient",
                "MobiusDenseSchedule."
                "residueMultipleEventCount_le_minimumCapacity",
                "MobiusDenseSchedule.multipleOffset_lt_count",
                "MobiusDenseSchedule.event_lt_multipleEventCount",
            ),
            "SparkInterval.TernaryGoldbach.MobiusResidue235."
            "fold_prefix_suffix_eq_residueSeed": (
                "MobiusResidue235.seedPrime_dvd_residue_iff",
                "MobiusResidue235.seedPrime_sq_dvd_residue_iff",
                "MobiusResidue235.applyPrime_residue_eq",
                "MobiusResidue235.residueSeed_eq",
            ),
            "SparkInterval.Dirichlet.PhaseSignState.State.combine_assoc": (
                "PhaseSignState.State.combine_boundaryValid",
            ),
            "SparkInterval.Dirichlet.PhaseSignState.AmbiguityRunState."
            "combine_assoc": (
                "PhaseSignState.AmbiguityRunState.combine_countValid",
            ),
            "SparkInterval.Dirichlet.PhaseSignFold."
            "summarize_eq_reference": (
                "PhaseSignFold.decisionTransitionCount_eq_filtered",
                "PhaseSignFold.summarize_append",
            ),
            "SparkInterval.Dirichlet.PhaseSignFold.Ambiguity."
            "summarize_rangeCount_eq_maximal": (
                "PhaseSignFold.Ambiguity.summarize_countValid",
                "PhaseSignFold.Ambiguity.summarize_append",
            ),
            "SparkInterval.Dirichlet.PhaseDenseWire."
            "recordAt_packRecords": (
                "PhaseDenseWire.decode_encode",
                "PhaseDenseWire.transitionCount_lt_capacity",
                "PhaseDenseWire.encode_lt_recordCapacity",
                "PhaseDenseWire.packedAt_packValues",
            ),
            "SparkInterval.Dirichlet.LargeQCompositionDFT."
            "positiveDFT_compose": (
                "LargeQCompositionDFT.positiveDFT_add",
                "LargeQCompositionDFT.positiveDFT_scale",
                "LargeQCompositionDFT.naive_deferred_counterexample",
            ),
            "SparkInterval.RealInterval."
            "directedSignQuadrantMul_contains": (
                "RealInterval.signQuadrantMulLo_eq_mul_lo",
                "RealInterval.signQuadrantMulHi_eq_mul_hi",
                "RealInterval.signQuadrantMul_eq_mul",
                "RealInterval.directedSignQuadrantMulLo_le",
                "RealInterval.le_directedSignQuadrantMulHi",
            ),
            "SparkInterval.ComplexInterval."
            "directedMul_contains": (
                "RealInterval.directedAdd_contains",
                "RealInterval.directedSub_contains",
                "RealInterval.directedMul_contains",
            ),
            "SparkInterval.Dirichlet.DirectedIntervalFFT."
            "directedPositiveRadix2Transform_contains_positiveDFT": (
                "DirectedIntervalFFT.directedButterfly_contains",
                "DirectedIntervalFFT.directedStage_contains_exactStage",
                "DirectedIntervalFFT.runDirectedStages_contains",
                "DirectedIntervalFFT."
                "directedPositiveRadix2Transform_contains",
            ),
            "SparkInterval.Dirichlet.DirectedIntervalBluestein."
            "directedBluesteinLineValue_contains_positiveDFT": (
                "DirectedIntervalBluestein."
                "directedPaddedInputNatural_contains",
                "DirectedIntervalBluestein."
                "bitReverseScatterInterval_contains",
                "DirectedIntervalBluestein."
                "directedNegativeFFTFromBitReversed_contains",
                "DirectedIntervalBluestein."
                "directedPositiveFFTFromBitReversed_contains",
                "DirectedIntervalBluestein."
                "directedPointwiseBitReverseCopy_contains",
                "DirectedIntervalBluestein.directedGatherOutput_contains",
                "DirectedIntervalBluestein."
                "directedBluesteinLineValue_contains_cudaSourceLine",
                "BluesteinCUDADataflow."
                "cudaBluesteinSourceLineValue_eq_positiveDFT",
            ),
            "SparkInterval.Dirichlet.CertifiedRootTable."
            "rootRectConfigured?_containsComplex": (
                "Certified.sinCosTaylorState_spec",
                "Certified.sinCosTaylorBase_containsReal",
                "Certified.sinCosTaylorBoundedInterval_containsReal",
                "Certified.machinPiInterval_containsReal",
                "Certified.rootTwoPiInterval_containsReal",
                "CertifiedRootTable.phaseIntervalReduced_containsReal",
                "CertifiedRootTable.unitRoot_mod",
                "CertifiedRootTable.exactQuarterRoot?_containsComplex",
            ),
            "SparkInterval.Dirichlet.CertifiedRootTable."
            "rootRectFast?_containsComplex": (
                "CertifiedRootTable.rootRectConfigured?_containsComplex",
            ),
            "SparkInterval.Certified.rootPiInterval_containsReal": (
                "Certified.atanSmall_containsReal",
                "Certified.machinPiInterval_containsReal",
            ),
            "SparkInterval.Certified."
            "sinCosTaylorBoundedInterval_containsReal": (
                "Certified.sinCosTaylorState_spec",
                "Certified.sinCosTaylorBase_containsReal",
                "Certified.sinCosTaylorSmall_containsReal",
            ),
            "SparkInterval.Dirichlet.CertifiedRootWire."
            "checked_box_contains": (
                "RawInterval.decodeFinite_isValid",
                "CertifiedRootTable.rootRectFast?_containsComplex",
                "CertifiedRootWire.check_sound",
                "CertifiedBluesteinRootBridge."
                "fastRootCertificate_contains",
            ),
            "SparkInterval.Dirichlet.CertifiedChirpStateWire."
            "checkPositiveDump_root_containments": (
                "CertifiedRootWire.checked_box_contains",
                "CertifiedChirpStateWire.checkPositiveRow_chirp_sound",
                "CertifiedChirpStateWire.checkPositiveRow_oddStep_sound",
                "CertifiedChirpStateWire.checkPositiveDump_rows",
            ),
            "SparkInterval.Dirichlet.CertifiedFFTRootTableWire."
            "checkPositiveDump_source_stage_root_containment": (
                "CertifiedRootWire.checked_box_contains",
                "CertifiedFFTRootTableWire."
                "specAtFlatIndex_source_order",
                "CertifiedFFTRootTableWire.checkPositiveRoot_sound",
                "CertifiedFFTRootTableWire.checkPositiveDump_geometry",
                "CertifiedFFTRootTableWire.checkPositiveDump_rows",
                "CertifiedFFTRootTableWire."
                "checkPositiveDump_root_containments",
            ),
            "SparkInterval.Dirichlet.CertifiedBasisOneOutputWire."
            "checkMaximumOrderDeltaOneArtifact_basisOne_dft_containments": (
                "BluesteinDFT.positiveDFT_basisOne_eq_unitRoot",
                "CertifiedRootWire.checked_box_contains",
                "CertifiedBasisOneOutputWire.checkPositiveRow_sound",
                "CertifiedBasisOneOutputWire.checkArtifact_components",
                "CertifiedBasisOneOutputWire."
                "checkArtifact_basisOne_dft_containments",
                "CertifiedBasisOneOutputWire."
                "checkMaximumOrderDeltaOneArtifact_header",
            ),
            "SparkInterval.Dirichlet.CertifiedBluesteinRootBridge."
            "certifiedRoots_directedBluestein_contains_positiveDFT": (
                "CertifiedRootTable.rootRectFast?_containsComplex",
                "CertifiedBluesteinRootBridge.contains_of_enclosesRect",
                "CertifiedBluesteinRootBridge."
                "positiveTwiddlesContain_of_certificates",
                "CertifiedBluesteinRootBridge."
                "negativeTwiddlesContain_of_positive_certificates",
                "CertifiedBluesteinRootBridge."
                "inputChirpsContain_of_certificates",
                "CertifiedBluesteinRootBridge."
                "kernelContains_of_positive_chirp_certificates",
                "DirectedIntervalBluestein."
                "directedBluesteinLineValue_contains_positiveDFT",
            ),
            "SparkInterval.Dirichlet.BluesteinChirpRecurrence."
            "runDirected_from_chirp_contains": (
                "BluesteinChirpRecurrence.halfRoot_add",
                "BluesteinChirpRecurrence.halfRoot_two_mul",
                "BluesteinChirpRecurrence.exactStateAt_spec",
                "BluesteinChirpRecurrence.directedNext_contains",
                "BluesteinChirpRecurrence.runDirected_from_contains",
            ),
            "SparkInterval.Dirichlet.DFTRootRecurrence."
            "runDirected_from_contains": (
                "DFTRootRecurrence.unitRoot_succ",
                "DFTRootRecurrence.directedNext_contains",
            ),
            "SparkInterval.Dirichlet.CompletedConductorPhase."
            "exponentAt_succ": (
                "Factor8Postprocess.sourceStep_eq",
                "CompletedConductorPhase.exponentStep_eq",
                "CompletedConductorPhase.sourceExponentAt_eq",
                "CompletedConductorPhase.exponentAt_sourceExponentAt",
                "CompletedConductorPhase.doubledExponentStep_ne",
            ),
            "SparkInterval.Dirichlet.TMajorCheckpointLayout."
            "conductorExponentAt_checkpoint": (
                "CompletedConductorPhase.exponentAt_succ",
                "TMajorCheckpointLayout.checkpointOwner_lt_count",
                "TMajorCheckpointLayout.checkpointStart_lt_sampleCount",
                "TMajorCheckpointLayout.sampleCount_le_checkpointCount_mul",
                "TMajorCheckpointLayout.checkpoint_eq_owner",
            ),
            "SparkInterval.Dirichlet.CompletedFactorParallelSchedule."
            "conductorExponentAt_thread": (
                "CompletedFactorParallelSchedule.chunkSize_positive",
                "CompletedFactorParallelSchedule."
                "span_le_thread_capacity",
                "CompletedFactorParallelSchedule.threadOwner_lt",
                "CompletedFactorParallelSchedule.sample_mem_owner",
                "CompletedFactorParallelSchedule.threadStart_add_offset",
                "CompletedFactorParallelSchedule.thread_eq_owner",
            ),
            "SparkInterval.Dirichlet.CompletedFactorWire."
            "checkFullSourceBundle_exactRoster": (
                "CompletedFactorWire.distinctNats_iff_nodup",
                "CompletedFactorWire.parseGammaArtifact_sound",
                "CompletedFactorWire.parseStepArtifact_sound",
                "CompletedFactorWire.parseCheckpointArtifact_sound",
                "CompletedFactorWire.checkFullSourceBundle_sound",
            ),
            "SparkInterval.Dirichlet.BluesteinDFT."
            "paddedBluesteinValue_eq_positiveDFT": (
                "BluesteinDFT.bluestein_kernel_identity",
                "BluesteinDFT.centeredIndex_circularIndex",
                "BluesteinDFT."
                "paddedCyclicConvolutionValue_eq_wrappedConvolutionValue",
                "BluesteinDFT."
                "wrappedConvolutionValue_eq_bluesteinConvolutionValue",
                "BluesteinDFT.bluesteinValue_eq_positiveDFT",
            ),
            "SparkInterval.Dirichlet.BluesteinDFT."
            "positiveDFT_basisOne_eq_unitRoot": (),
            "SparkInterval.Dirichlet.BluesteinFFTConvolution."
            "cuda_fft_pointwise_ifft_bluestein_eq_positiveDFT": (
                "BluesteinFFTConvolution.negativeDFT_eq_dft",
                "BluesteinFFTConvolution."
                "normalizedPositiveRadix2_negativeRadix2",
                "BluesteinFFTConvolution.negativeDFT_cyclicConvolution",
                "BluesteinFFTConvolution."
                "normalizedPositiveRadix2_pointwise_negativeRadix2",
                "BluesteinFFTConvolution.circularIndex_mem_kernel_wings",
                "BluesteinFFTConvolution.cyclicConvolution_zeroPaddedKernel",
                "BluesteinDFT.paddedBluesteinValue_eq_positiveDFT",
            ),
            "SparkInterval.Dirichlet.BluesteinCUDADataflow."
            "cudaBluesteinSourceLineValue_eq_positiveDFT": (
                "BluesteinCUDADataflow.cudaBrevShift_eq_reverseBits",
                "BluesteinCUDADataflow."
                "bitReversedWorkspaceIndex_injective",
                "BluesteinCUDADataflow.tensorAddress_lt_total",
                "BluesteinCUDADataflow."
                "initializeA_write_to_bit_reversed_address",
                "BluesteinCUDADataflow.pointwiseBitReverseCopy_write",
                "BluesteinCUDADataflow.negativeSharedLaunch_eq_full",
                "BluesteinCUDADataflow.positiveSharedLaunch_eq_full",
                "BluesteinCUDADataflow."
                "gatherOutputValue_eq_postChirp_normalized",
                "BluesteinFFTConvolution."
                "cuda_fft_pointwise_ifft_bluestein_eq_positiveDFT",
            ),
            "SparkInterval.Dirichlet.CompletedFactorStreamingWire."
            "checkFullSourceBundle_exactRoster": (
                "CompletedFactorStreamingWire.checkDiskWindow_sound",
                "CompletedFactorStreamingWire.scanCheckpointRows_sound",
                "CompletedFactorStreamingWire.checkRosterFresh_sound",
                "CompletedFactorStreamingWire.scanRosterTotals_sound",
                "CompletedFactorStreamingWire."
                "fullSourceExpectations_valid_of_streaming_scans",
                "CompletedFactorStreamingWire.checkFullSourceBundle_sound",
            ),
            "SparkInterval.Dirichlet.QOrderManifestWire."
            "checkScheduledFullSourceBundle_exactRoster": (
                "QOrderManifestWire.parseManifest_sound",
                "QOrderManifestWire.checkFullSourceManifest_sound",
                "QOrderManifestWire.checkScheduledFullSourceBundle_sound",
                "CompletedFactorWire.checkFullSourceBundle_exactRoster",
            ),
            "SparkInterval.Dirichlet.QOrderManifestStreamingWire."
            "checkScheduledFullSourceBundle_exactRoster": (
                "QOrderManifestStreamingWire."
                "buildFormulaicSourceBodyAux_toList",
                "QOrderManifestStreamingWire.formulaicSourceSHA256_eq_spec",
                "QOrderManifestStreamingWire.executionOrderSHA256_eq_spec",
                "QOrderManifestStreamingWire.checkFullSourceManifest_sound",
                "QOrderManifestStreamingWire.checked_formulaic_record_iff",
                "QOrderManifestStreamingWire."
                "checkScheduledFullSourceBundle_sound",
                "QOrderManifestStreamingWire."
                "checked_full_source_exact_phase_roster",
            ),
            "SparkInterval.TernaryGoldbach.PsiLowerFilter."
            "strict_accept_square_iff": (
                "PsiLowerFilter.square_lt_iff_sqrt_boundary",
                "PsiLowerFilter.square_le_iff_le_sqrt",
            ),
            "SparkInterval.TernaryGoldbach.PsiAffineGuards."
            "all_radius_safe_of_folds": (
                "PsiAffineGuards.lowerRadiusQ64_sq_le",
                "PsiAffineGuards.strictLowerRadiusQ64_sq_lt",
                "PsiAffineGuards.upperRadiusQ64_sq_le",
                "PsiAffineGuards.all_lower_safe_of_minimumIncoming",
                "PsiAffineGuards.all_upper_safe_of_maximumIncoming",
            ),
        }
        for target, dependencies in expected.items():
            with self.subTest(target=target):
                body = bodies[target]
                for dependency in dependencies:
                    self.assertIn(dependency, body)

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

    def test_registry_exposes_raw_dirichlet_arithmetic_to_grh_chain(self) -> None:
        text = REGISTRY.read_text(encoding="utf-8")
        bodies = annotation_bodies(text)
        expected = {
            "SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign.requested_modulus_sample_has_raw_source_sign",
            "SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign.decodedCells_bracket_check",
            "SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign.decodedCells_checkedRationalBracket_of_sourceRealizes",
            "SparkInterval.Dirichlet.FactoredSmallQSourceRealization.PrimitiveRosterRealization",
            "SparkInterval.Dirichlet.FactoredSmallQSourceRealization.CharacterInputsRealize",
            "SparkInterval.Dirichlet.FactoredSmallQSourceRealization.SourceEvaluatorRealizes",
            "SparkInterval.Dirichlet.FactoredSmallQSourceRealization.SourceEvaluatorFamilyRealizes.completedValuesReal",
            "SparkInterval.Dirichlet.FactoredSmallQSourceRealization.requested_source_sample_has_character_and_evaluator",
            "SparkInterval.Dirichlet.FactoredSmallQZeroBracket.CompletedSignBracketFamily.exists_zeroCertificate",
            "SparkInterval.Dirichlet.DirichletHardyModel.verifyCompletedSignBracketFamily",
            "SparkInterval.Dirichlet.FactoredSmallQRosterGRHBridge.grhVerifiedForModulus_of_primitiveRosterCompletedSignBracketFamilies",
            "SparkInterval.Dirichlet.plattTheorem71_of_modulus_verification",
            "SparkInterval.Blueprint.plattTheorem71VerifierRealizationGap",
        }
        self.assertEqual(expected - set(bodies), set())
        gap = bodies[
            "SparkInterval.Blueprint.plattTheorem71VerifierRealizationGap"
        ]
        for dependency in expected - {
            "SparkInterval.Blueprint.plattTheorem71VerifierRealizationGap"
        }:
            self.assertIn(dependency, text)
        self.assertIn(
            "SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign.decodedCells_bracket_check",
            gap,
        )
        self.assertIn(
            "SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign.decodedCells_checkedRationalBracket_of_sourceRealizes",
            gap,
        )
        self.assertIn(
            "SparkInterval.Dirichlet.DirichletHardyModel.verifyCompletedSignBracketFamily",
            gap,
        )
        self.assertIn(
            "SparkInterval.Dirichlet.FactoredSmallQSourceRealization.requested_source_sample_has_character_and_evaluator",
            gap,
        )
        self.assertIn(
            "SparkInterval.Dirichlet.FactoredSmallQRosterGRHBridge.grhVerifiedForModulus_of_primitiveRosterCompletedSignBracketFamilies",
            gap,
        )
        self.assertIn("notReady := true", gap)

    def test_leanarchitect_revision_matches_toolchain_release(self) -> None:
        lakefile = (ROOT / "lakefile.toml").read_text(encoding="utf-8")
        toolchain = (ROOT / "lean-toolchain").read_text(encoding="utf-8")
        self.assertEqual(toolchain.strip(), "leanprover/lean4:v4.32.0")
        self.assertIn(
            'rev = "3810ba48f2e5bbd83b32623d21fc059b279dbf81"',
            lakefile,
        )
        self.assertLess(
            lakefile.index('name = "LeanArchitect"'),
            lakefile.index('name = "mathlib"'),
        )


if __name__ == "__main__":
    unittest.main()
