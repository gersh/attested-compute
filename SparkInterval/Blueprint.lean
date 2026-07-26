import Architect
import SparkInterval.Audit.TrustedComputeCertificates
import SparkInterval.Certificate.Format
import SparkInterval.Certificate.SHA256
import SparkInterval.Certified.ComplexDiskWire
import SparkInterval.Certified.HighDegreeSinCos
import SparkInterval.Certified.HighPrecisionPi
import SparkInterval.ComplexInterval
import SparkInterval.SignQuadrantIntervalMul
import SparkInterval.DirectedComplexInterval
import SparkInterval.Dirichlet.Factor8Postprocess
import SparkInterval.Dirichlet.FormulaicQMajorCursor
import SparkInterval.Dirichlet.ResidentQMajorPhases
import SparkInterval.Dirichlet.PhaseSignState
import SparkInterval.Dirichlet.PhaseSignFold
import SparkInterval.Dirichlet.PhaseDenseWire
import SparkInterval.Dirichlet.FactoredSmallQCampaign
import SparkInterval.Dirichlet.FactoredSmallQCompletedSign
import SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign
import SparkInterval.Dirichlet.FactoredSmallQDFT
import SparkInterval.Dirichlet.FactoredSmallQDFTCorrectness
import SparkInterval.Dirichlet.FactoredSmallQDFTComposition
import SparkInterval.Dirichlet.BluesteinDFT
import SparkInterval.Dirichlet.BluesteinFFTConvolution
import SparkInterval.Dirichlet.BluesteinCUDADataflow
import SparkInterval.Dirichlet.BluesteinChirpRecurrence
import SparkInterval.Dirichlet.DirectedIntervalFFT
import SparkInterval.Dirichlet.DirectedIntervalBluestein
import SparkInterval.Dirichlet.CertifiedRootTable
import SparkInterval.Dirichlet.CertifiedBluesteinRootBridge
import SparkInterval.Dirichlet.CertifiedRootWire
import SparkInterval.Dirichlet.CertifiedChirpStateWire
import SparkInterval.Dirichlet.CertifiedFFTRootTableWire
import SparkInterval.Dirichlet.CertifiedBasisOneOutputWire
import SparkInterval.Dirichlet.DFTRootRecurrence
import SparkInterval.Dirichlet.LargeQCompositionDFT
import SparkInterval.Dirichlet.FactoredSmallQRawDFT
import SparkInterval.Dirichlet.FactoredSmallQRawDFTComposition
import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign
import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign
import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign
import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign
import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign
import SparkInterval.Dirichlet.FactoredSmallQZeroBracket
import SparkInterval.Dirichlet.FactoredSmallQGaussianSum
import SparkInterval.Dirichlet.FactoredSmallQGRHBridge
import SparkInterval.Dirichlet.FactoredSmallQModulusCampaign
import SparkInterval.Dirichlet.FactoredSmallQPostprocess
import SparkInterval.Dirichlet.FactoredSmallQRawCampaign
import SparkInterval.Dirichlet.FactoredSmallQRawGaussianSum
import SparkInterval.Dirichlet.FactoredSmallQRawPostprocess
import SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign
import SparkInterval.Dirichlet.FactoredSmallQRawPostprocessModulusCampaign
import SparkInterval.Dirichlet.FactoredSmallQRawSumCampaign
import SparkInterval.Dirichlet.FactoredSmallQRawTrace
import SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign
import SparkInterval.Dirichlet.FactoredSmallQSourceRealization
import SparkInterval.Dirichlet.FactoredSmallQTrace
import SparkInterval.Dirichlet.FactoredSmallQRosterGRHBridge
import SparkInterval.Dirichlet.PlattTheorem71Contract
import SparkInterval.Dirichlet.TMajorFactorRecurrence
import SparkInterval.Dirichlet.CompletedConductorPhase
import SparkInterval.Dirichlet.TMajorCheckpointLayout
import SparkInterval.Dirichlet.CompletedFactorParallelSchedule
import SparkInterval.Dirichlet.CompletedFactorStreamingWire
import SparkInterval.Dirichlet.QOrderManifestWire
import SparkInterval.Dirichlet.QOrderManifestStreamingWire
import SparkInterval.Execution.FormalPTXProgram
import SparkInterval.Execution.CompactAttestedVerifier
import SparkInterval.Execution.RegisteredA7BoundaryCertificate
import SparkInterval.Execution.RegisteredCDEMAbelCertificate
import SparkInterval.Execution.RegisteredCubicSumCertificate
import SparkInterval.Execution.RegisteredGoldbachCertificate
import SparkInterval.Execution.RegisteredH100FormalPtxPilot
import SparkInterval.Execution.RegisteredHurstSharedCertificate
import SparkInterval.Execution.RegisteredPsiLemma92Certificate
import SparkInterval.Execution.RegisteredPlattTheorem71Certificate
import SparkInterval.Execution.RegisteredZetaHeadCertificate
import SparkInterval.Execution.RegisteredZetaRHCertificate
import SparkInterval.Execution.SignedResultCertificateComposition
import SparkInterval.Execution.SignedZetaVerifier
import SparkInterval.Execution.Trusted.RunCertificate
import SparkInterval.PTX.GeneratedKernelRunRefinement
import SparkInterval.PTX.NvidiaPTXRefinement
import SparkInterval.PTX.PowSchedule
import SparkInterval.PTX.StructuralCompilerCorrect
import SparkInterval.Zeta.EndpointCertificate
import SparkInterval.Zeta.EvenReflectionCertificate
import SparkInterval.Zeta.HardyZContract
import SparkInterval.Zeta.MultiplicityCount
import SparkInterval.Zeta.PairedTuringClosureCertificate
import SparkInterval.Zeta.PT21ArtifactBinding
import SparkInterval.Zeta.PT21PairedWindowGeometry
import SparkInterval.Zeta.PT21PrecisionHull
import SparkInterval.Zeta.SincInterpolationEndpointBridge
import SparkInterval.Zeta.StreamingEndpointCertificate
import SparkInterval.Zeta.StreamingChunkVerifier
import SparkInterval.Zeta.SymmetricCount
import SparkInterval.Zeta.TuringGridEventCertificate
import SparkInterval.Zeta.TuringWindowCertificate
import SparkInterval.Zeta.TouchingEndpointCertificate
import SparkInterval.Zeta.TouchingVerifier
import SparkInterval.Zeta.Verifier
import SparkInterval.TernaryGoldbach.HurstAffineCertificate
import SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter
import SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction
import SparkInterval.TernaryGoldbach.HurstAffineClusterComposition
import SparkInterval.TernaryGoldbach.HurstAffineBlockComposition
import SparkInterval.TernaryGoldbach.HurstAffineTerminalInvariants
import SparkInterval.TernaryGoldbach.MobiusFusedSupport
import SparkInterval.TernaryGoldbach.MobiusFusedFinalization
import SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
import SparkInterval.TernaryGoldbach.MobiusPrimeRosterCertificateBridge
import SparkInterval.TernaryGoldbach.MobiusSegmentedSieveRoster
import SparkInterval.TernaryGoldbach.MobiusGuardedMachine
import SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
import SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization
import SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement
import SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement
import SparkInterval.TernaryGoldbach.MobiusPackedCUDAWidthSafety
import SparkInterval.TernaryGoldbach.MobiusPackedCUDARosterPreflight
import SparkInterval.TernaryGoldbach.MobiusCASRetryTrace
import SparkInterval.TernaryGoldbach.MobiusSquareOffsetHelper
import SparkInterval.TernaryGoldbach.MobiusSegmentEventEnumeration
import SparkInterval.TernaryGoldbach.MobiusDenseVisitRealization
import SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing
import SparkInterval.TernaryGoldbach.MobiusCUDALaunchWidthSafety
import SparkInterval.TernaryGoldbach.HurstGpuRowRealization
import SparkInterval.TernaryGoldbach.HurstPackedPrefixInput
import SparkInterval.TernaryGoldbach.MobiusDenseSchedule
import SparkInterval.TernaryGoldbach.MobiusResidue235
import SparkInterval.TernaryGoldbach.MobiusResidue2357
import SparkInterval.TernaryGoldbach.MobiusResidue235711
import SparkInterval.TernaryGoldbach.MobiusQualificationSeededRefinement
import SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule
import SparkInterval.TernaryGoldbach.MobiusRectangularVisitRealization
import SparkInterval.TernaryGoldbach.MobiusResidualGCD
import SparkInterval.TernaryGoldbach.GoldbachPrimePrefixReuse
import SparkInterval.TernaryGoldbach.GoldbachTailProgression
import SparkInterval.TernaryGoldbach.GoldbachWarpLaunchIndexing
import SparkInterval.TernaryGoldbach.GoldbachOptimizedSourceRefinement
import SparkInterval.TernaryGoldbach.PsiAffineChildCertificate
import SparkInterval.TernaryGoldbach.PsiAffineGuards
import SparkInterval.TernaryGoldbach.PsiLowerFilter
import SparkInterval.TernaryGoldbach.R2StarReplaySegmentation
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CPureEntryComposition

/-!
# LeanArchitect proof and trust map

This module adds documentation metadata after importing the declarations it
describes.  The mathematical, compiler, machine, certificate, and execution
modules do not import `Architect`, so blueprint tooling is not part of their
logical implementation or trusted computing base.

LeanArchitect infers theorem dependencies when producing its TeX artifacts.
This registry also records the important high-level `uses` and `proofUses`
edges explicitly so they remain present in LeanArchitect's raw JSON export.
The manually added edges from the PTX transcription and citation table to the
exact NVIDIA document pin are traceability metadata: they are not Lean proofs
that English prose was transcribed correctly, that `ptxas` preserves PTX
semantics, or that SASS and physical hardware implement the model.

The sole external-execution axiom is titled `TRUST AXIOM` deliberately.  A
generated graph must never present it as a kernel-proved fact.
-/

set_option autoImplicit false

/-! ## Reusable packed-byte certificate primitives -/

attribute [blueprint "thm:sha256-packed-byte-stream-refinement"
  (title := "Packed and virtual-slice SHA-256 equals the list reference")
  (uses := [
    SparkInterval.Certificate.SHA256.hashSource_eq_hashBytes_of_realizes,
    SparkInterval.Certificate.SHA256.digestByteArray_eq_reference])
  (statement := /--
    The packed Lean SHA-256 implementation walks a byte array, or a virtual
    prefix-plus-slice composition, in consecutive 64-byte blocks without
    constructing a linked list of the message. Lean proves its digest exactly
    equal to the deliberately simple list-based reference for every byte
    array. This is an equality between two Lean algorithms, not a formal
    refinement to the FIPS document. Using a digest as an identity commitment
    also relies on SHA-256 collision and second-preimage resistance outside
    Lean.
  -/)] SparkInterval.Certificate.SHA256.digestPrefixSlice_eq_digestByteArray_append_extract

attribute [blueprint "thm:sqrt218-c-source-sha256-refinement"
  (title := "The live Sqrt218 source trace supplies the exact SHA-256 digest")
  (uses := [
    SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CSHA256Refinement.cReadWord_toNat,
    SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CSHA256Refinement.cDigestByteArray_refines])
  (proofUses := [
    SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CSHA256Refinement.digest_correct_of_concreteExecution])
  (statement := /--
    The independent pure Lean model of the Sqrt218 C SHA-256 schedule,
    compression, padding, and big-endian output refines the packed Lean digest
    for every byte array. The live successful-pure-entry trace derives its
    exact digest condition only after supplying the explicit
    `ConcreteExecutionMatchesSource` field. This theorem does not establish
    that a compiler, ELF/x86 execution, or physical CPU produces that field;
    those remain separate compiler/ISA refinement obligations.
  -/)]
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPureEntryComposition.CSuccessfulPureEntryTrace.sha256Correct

/-! ## Verified finite-replay optimizations -/

attribute [blueprint "thm:r2star-ordered-segment-fold"
  (title := "Ordered parallel R2Star segments have the serial terminal state")
  (uses := [
    SparkInterval.TernaryGoldbach.R2StarReplaySegmentation.foldRows_append])
  (statement := /--
    Flattening the exact source-ordered row segments and folding them serially
    gives the same directed state as folding each segment and then merging the
    segments in order.  This proves the architecture-independent arithmetic
    identity used by the parallel CPU replay.  Exact C++ partition contents,
    hashes, and machine execution remain physical refinement obligations.
  -/)] SparkInterval.TernaryGoldbach.R2StarReplaySegmentation.foldSegments_eq_foldRows_flatten

attribute [blueprint "thm:hurst-lower-candidate-threshold"
  (title := "The complete one-unit threshold contains every exact lower maximizer")
  (uses := [
    SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.lower_outside_threshold_strictly_below])
  (statement := /--
    If an inward squarefree lower candidate can move down by at most one
    integer unit under exact replay, every exact maximizer lies between the
    approximate maximum minus one and the approximate maximum.  A GPU
    optimization may therefore revisit that complete threshold set, but an
    arbitrary fixed number of tied rows is not sufficient.
  -/)] SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.exact_maximizer_inside_lower_threshold

attribute [blueprint "thm:hurst-upper-candidate-threshold"
  (title := "The complete one-unit threshold contains every exact upper minimizer")
  (uses := [
    SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.upper_outside_threshold_strictly_above])
  (statement := /--
    If an inward squarefree upper candidate can move up by at most one integer
    unit under exact replay, every exact minimizer lies between the
    approximate minimum and that minimum plus one.  The theorem justifies a
    complete second-pass threshold filter independently of GPU architecture.
  -/)] SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.exact_minimizer_inside_upper_threshold

attribute [blueprint "thm:hurst-affine-hierarchical-reduction"
  (title := "Affine extrema admit deterministic hierarchical GPU reduction")
  (uses := [
    SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.lowerKey_injective,
    SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.upperKey_injective,
    SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.lowerKey_min_comm,
    SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.lowerKey_min_idem,
    SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.upperKey_min_assoc,
    SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.upperKey_min_comm,
    SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.upperKey_min_idem])
  (statement := /--
    Encoding a maximum candidate as `(-value, sourceOrder)` and a minimum
    candidate as `(value, sourceOrder)` turns both deterministic tie-breaking
    rules into lexicographic minimum.  Associativity, commutativity, and
    idempotence therefore permit thread, block, device, and host reductions
    to be regrouped without changing the selected value or earliest witness.
    A CUDA implementation still requires a separate native-refinement proof.
  -/)] SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter.lowerKey_min_assoc

attribute [blueprint "thm:hurst-direct-prefix-scan"
  (title := "Direct packed rows have exact prefix scans and deterministic extrema")
  (uses := [
    SparkInterval.TernaryGoldbach.HurstPackedPrefixInput.packedPrefixInputs_valid_of_totalPoisonCount_zero,
    SparkInterval.TernaryGoldbach.HurstPackedPrefixInput.packedPoisonCountTotal_fits_uint32,
    SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.inclusiveInputScan_getElem,
    SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.inputScanFrom_append,
    SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.inputPrefixAt_fits_machine_words,
    SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.inputScanReducers_return_winners,
    SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.inclusiveInputScan_map_rowDelta])
  (statement := /--
    A complete prime roster plus the receipt's aggregate zero poison count
    turns every terminal
    packed support word directly into the exact pair `{μ, μ ≠ 0}`. For the
    declared leaf cap, every inclusive Mertens/squarefree prefix fits the
    native signed/unsigned 32-bit fields, and the per-leaf aggregate poison
    counter cannot wrap its `uint32` field. Maximum and minimum reductions
    select the global value with the earliest source-order tie, and the scan
    composes exactly across consecutive chunks. The retained signed-byte
    qualification route initializes exactly the same input pairs.

    This closes the pure row-finalization, scan, width, and reduction
    algorithms. The compiled direct finalizer, atomic poison counter, CUB
    scan, CUDA reductions, and device execution still require physical
    refinement.
  -/)] SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.inputScanAndCandidateReduction_sound

attribute [blueprint "thm:hurst-affine-cluster-composition"
  (title := "Independent affine workers compose to the single exact scan")
  (uses := [
    SparkInterval.TernaryGoldbach.HurstAffineClusterComposition.proxyNormalizedCandidates_eq_local,
    SparkInterval.TernaryGoldbach.HurstAffineClusterComposition.workerIncomingStates_getElem,
    SparkInterval.TernaryGoldbach.HurstAffineClusterComposition.workerFinalState_eq_handoff_add_total,
    SparkInterval.TernaryGoldbach.HurstAffineClusterComposition.translatedGuard_contains_handoff_iff,
    SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.reduceMaximum_sound,
    SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.reduceMinimum_sound])
  (statement := /--
    For any ordered list of consecutive H100 worker chunks, exact local
    Mertens or squarefree extrema can be computed against arbitrary recorded
    proxy states and normalized back to the same zero-based summaries.  An
    exclusive scan of exact chunk deltas derives each real incoming state
    from the CPU handoff.  Translating local extrema by the cumulative delta
    and their global row offset, then reducing with earliest-source-order
    ties, equals one `inclusiveInputScan` and candidate reduction over all
    concatenated rows.  The theorem is generic in the worker count and has an
    eight-worker specialization.  It does not assume that a proxy satisfies
    its worker guard.

    This closes the pure distributed affine scan/translation/reduction
    algorithm.  Python bundle parsing, worker-range and digest binding,
    compiled CUB/CUDA refinement, and attested device execution remain
    separate boundaries.
  -/)] SparkInterval.TernaryGoldbach.HurstAffineClusterComposition.nWorkerComposition_eq_inclusiveInputScan

attribute [blueprint "thm:hurst-affine-block-composition"
  (title := "Ordered CUDA block summaries equal the exact per-row affine scan")
  (uses := [
    SparkInterval.TernaryGoldbach.HurstAffineBlockComposition.cudaAffineLaunchRow_decode,
    SparkInterval.TernaryGoldbach.HurstAffineBlockComposition.cudaAffineLaunchRow_injective,
    SparkInterval.TernaryGoldbach.HurstAffineBlockComposition.cudaBlockStripedScan_eq_inclusiveInputScan,
    SparkInterval.TernaryGoldbach.HurstAffineBlockComposition.composeCudaAffineMqBlockSummary_assoc,
    SparkInterval.TernaryGoldbach.HurstAffineBlockComposition.cudaAffineMqSummaryOfRows_append,
    SparkInterval.TernaryGoldbach.HurstAffineBlockComposition.cudaAffineMqTileSummaryTree_eq_perRowSummary,
    SparkInterval.TernaryGoldbach.HurstAffineBlockComposition.validPrefixRows_imply_terminalMqGuards])
  (statement := /--
    In the selected 256-by-256 qualification geometry, every live row has one
    unique block/stripe/thread coordinate and the 256 carried stripe scans are
    one exact inclusive scan.  A block retains its exact `{M,Q}` delta and
    four affine extrema, including global source order and the squarefree
    prefix witness.  The native left-to-right translation law is associative;
    the 256 consecutive thread chunks and eight adjacent tree rounds therefore
    equal the ordered fold of all block summaries.  Summarizing consecutive
    row tiles and composing them is exactly the same concrete summary as
    scanning every row, and the Hurst fields project to the earlier
    worker-composition theorem with identical earliest-tie winners.

    The CUDA source uses this equation and native differential tests compare
    it with the old global CUB scan.  Refinement of compiled CUB instructions,
    CUDA scheduling, and physical execution remains an explicit external
    boundary; this theorem does not make the qualification executable a
    production receipt.
  -/)] SparkInterval.TernaryGoldbach.HurstAffineBlockComposition.cudaHurstTileTree_projects_to_workerComposition

attribute [blueprint "thm:hurst-affine-terminal-sanity"
  (title := "Exact Möbius rows imply every cheap affine receipt sanity check")
  (uses := [
    SparkInterval.TernaryGoldbach.HurstAffineTerminalInvariants.rowCandidate_order_lt_twice_actual_length,
    SparkInterval.TernaryGoldbach.HurstAffineTerminalInvariants.pairedEndpointCandidate_order_lt_twice_actual_length,
    SparkInterval.TernaryGoldbach.HurstAffineTerminalInvariants.inputPrefixAt_squarefree_le_inputTotal])
  (statement := /--
    For an actual leaf, the terminal squarefree count is at most the row
    count, the Mertens delta lies between its negative and positive, and the
    two deltas have the same parity.  Every retained integer/right-limit
    source order is strictly below twice the actual leaf length, and every
    local squarefree witness is bounded by the terminal count.  The host
    finalizer checks these necessary invariants before hashing a receipt.
    They reject impossible device summaries but do not replace the compiled
    computation refinement.
  -/)] SparkInterval.TernaryGoldbach.HurstAffineTerminalInvariants.inputTotal_host_sanity_checks

attribute [blueprint "thm:mobius-fused-support-layout"
  (title := "The fused Möbius support layout is lossless below the source bound")
  (uses := [
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.divisor_lt_productRadix,
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.pack_lt_wordLimit,
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.unpackProduct_pack,
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.unpackCount_pack,
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.unpackSquareful_pack])
  (statement := /--
    On rows through 10^16, a retained divisor product fits below 2^54.
    Subject to the explicit five-bit distinct-factor-count guard, the proposed
    product/count/squareful encoding is injective and occupies fewer than 64
    bits.  This proves the arithmetic layout only; a native CUDA CAS loop must
    still establish those guards and refine this natural-number model.
  -/)] SparkInterval.TernaryGoldbach.MobiusFusedSupport.pack_injective

attribute [blueprint "thm:mobius-fused-update-order"
  (title := "Fused distinct-prime updates are order independent")
  (uses := [
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.unpackProduct_pack_update,
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.unpackCount_pack_update,
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.unpackSquareful_pack_update])
  (statement := /--
    Multiplying a new distinct prime, incrementing the factor count, and
    monotonically setting the squareful flag commutes with every other such
    update. Any linearization of the guarded native CAS operations therefore
    has the same mathematical state. This does not itself prove that the CUDA
    operations are linearizable or refine the model.
  -/)] SparkInterval.TernaryGoldbach.MobiusFusedSupport.update_comm

attribute [blueprint "thm:mobius-split-square-pass"
  (title := "The production split-square packed Möbius pass is exact")
  (uses := [
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.update_eq_markSquareful_updateProductCount,
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.markSquareful_updateProductCount_comm,
    SparkInterval.TernaryGoldbach.MobiusSquareOffsetHelper.firstSquareOffset_eq_some_iff_unique_least,
    SparkInterval.TernaryGoldbach.MobiusSquareOffsetHelper.returned_offset_dvd_iff_existsUnique_loop_event,
    SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization.prime_sq_dvd_iff_existsUnique_squareVisit,
    SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization.splitRun_perm,
    SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization.splitRun_eq_inlineRun,
    SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement.encodeSupport_lor_squarefulRadix,
    SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement.distinctWordStep_splitRepresents,
    SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement.squareWordStep_splitRepresents,
    SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement.cudaStepAdmissible_iff_nativeStepAdmissible,
    SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement.cudaAssembleFromWord_eq_pack,
    SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement.cudaDistinctWordStep_splitRepresents,
    SparkInterval.TernaryGoldbach.MobiusPackedCUDAWidthSafety.admittedAssembly_lt_uint64Radix,
    SparkInterval.TernaryGoldbach.MobiusPackedCUDAWidthSafety.cudaDistinctWordStep_encodeSupport_lt_uint64Radix,
    SparkInterval.TernaryGoldbach.MobiusPackedCUDARosterPreflight.invalidFlag_implies_all_initialized_rows_poison,
    SparkInterval.TernaryGoldbach.MobiusPackedCUDARosterPreflight.valid_of_deviceRosterInvalid_eq_false,
    SparkInterval.TernaryGoldbach.MobiusCASRetryTrace.cudaAttemptRun_splitRepresents,
    SparkInterval.TernaryGoldbach.MobiusCASRetryTrace.decode_cudaAttemptRun_eq_valid_of_committed_perm,
    SparkInterval.TernaryGoldbach.MobiusCUDALaunchWidthSafety.sourceNumber_lt_wordLimit,
    SparkInterval.TernaryGoldbach.MobiusCUDALaunchWidthSafety.primeSquare_lt_wordLimit,
    SparkInterval.TernaryGoldbach.MobiusCUDALaunchWidthSafety.squareStride_lt_wordLimit,
    SparkInterval.TernaryGoldbach.MobiusCUDALaunchWidthSafety.divisorLoopIncrement_lt_wordLimit,
    SparkInterval.TernaryGoldbach.MobiusCUDALaunchWidthSafety.squareLoopIncrement_lt_wordLimit,
    SparkInterval.TernaryGoldbach.MobiusCUDALaunchWidthSafety.multipleOffset_lt_wordLimit])
  (statement := /--
    The production suffix-prime sieve first performs guarded product/count
    CAS updates at every `p` multiple and then installs bit 59 at every `p²`
    multiple. Lean proves that the dense block/thread coordinates enumerate
    each square event exactly once, that both phases are invariant under their
    concurrent serializations, and that moving every square mark to the later
    phase is exactly the original inline mathematical fold.

    At the packed-word level, Lean separately proves that the live
    remainder-based first-offset helper returns the unique least in-segment
    square multiple with safe production widths; the exact CUDA masks,
    shifts, reserved/poison guards, and desired-word bitwise expression equal
    the arithmetic model; every admitted multiply, shift, successful desired
    word, and poison word is nonwrapping in `uint64`; and an explicit CAS
    retry trace proves failed races stutter while winners reduce to any
    permutation of the authenticated event roster. A separate structural
    preflight model proves that an unsafe, misordered, or wrong-prefix device
    roster poisons every initialized row before divisor arithmetic, while a
    clear flag exposes the exact `2,3,5` prefix and `2 ≤ p ≤ 10^8` machine
    guards. The modulo-free CAS therefore refines the guarded product/count
    transition;
    `atomicOr(1 << 59)` refines the square mark and preserves poison; and any
    nonpoison residue-seeded result from a complete prime roster finalizes to
    Mathlib's Möbius function. Lean also proves the admitted source endpoint,
    prime square, divisor and square strides, event product, and complete
    multiple-offset expression are all below `2^64`. Five alternating
    100-million-row qualification
    pairs measured a 1.64% sieve-only improvement, effectively tied complete
    device work, and 100 MB less allocation; H100 performance remains
    unmeasured.

    The remaining native obligations are to identify compiled fixed-width
    operations and CUDA
    roster pointers, `atomicExch`/`atomicCAS` winners, and same-stream launch
    order with the modeled lists and trace, prove that every launched roster
    event commits exactly once, refine the compiled CUDA/CUB code, and bind
    an attested device execution.
  -/)] SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement.output_decodeWord_packedSplitRunResidueSeeded_eq_moebius

attribute [blueprint "thm:mobius-residual-gcd-square-test"
  (title := "A residual GCD exactly detects repeated prime factors")
  (uses := [
    SparkInterval.TernaryGoldbach.MobiusResidualGCD.squarefree_product_residual_iff_gcd_eq_one,
    SparkInterval.TernaryGoldbach.MobiusResidualGCD.one_lt_gcd_iff_exists_product_prime_square_dvd,
    SparkInterval.TernaryGoldbach.MobiusResidualGCD.cardDistinctFactors_parity_product_residual])
  (statement := /--
    If `n = P * R`, the retained distinct-prime product and residual are
    squarefree, and the roster places every source prime divisor in `P`, then
    `gcd(P,R) > 1` exactly when some prime square divides `n`. When the GCD is
    one, `R > 1` contributes exactly one additional distinct-factor parity
    bit. This justifies an experimental final per-row GCD in place of a square
    test at every prime event. Complete-roster native realization, compiler
    refinement, and the performance comparison remain separate.
  -/)] SparkInterval.TernaryGoldbach.MobiusResidualGCD.one_lt_gcd_iff_exists_prime_square_dvd

attribute [blueprint "thm:mobius-dense-schedule"
  (title := "The load-balanced dense-prime schedule is an exact partition")
  (uses := [
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.update_comm,
    SparkInterval.TernaryGoldbach.MobiusDenseSchedule.flatBlock_decode,
    SparkInterval.TernaryGoldbach.MobiusDenseSchedule.primeIndex_lt,
    SparkInterval.TernaryGoldbach.MobiusDenseSchedule.event_block_thread_decode,
    SparkInterval.TernaryGoldbach.MobiusDenseSchedule.threadOwner_lt,
    SparkInterval.TernaryGoldbach.MobiusDenseSchedule.iterationOwner_lt,
    SparkInterval.TernaryGoldbach.MobiusDenseSchedule.event_mem_owner,
    SparkInterval.TernaryGoldbach.MobiusDenseSchedule.block_eq_eventOwner,
    SparkInterval.TernaryGoldbach.MobiusDenseSchedule.eventOwner_lt_slots,
    SparkInterval.TernaryGoldbach.MobiusDenseSchedule.multipleEventCount_le_capacity,
    SparkInterval.TernaryGoldbach.MobiusDenseSchedule.residueMinimumSlots_sufficient_at_public_cap,
    SparkInterval.TernaryGoldbach.MobiusDenseSchedule.residuePreviousSlotCount_insufficient,
    SparkInterval.TernaryGoldbach.MobiusDenseSchedule.residueMultipleEventCount_le_minimumCapacity,
    SparkInterval.TernaryGoldbach.MobiusDenseSchedule.multipleOffset_lt_count,
    SparkInterval.TernaryGoldbach.MobiusDenseSchedule.event_lt_multipleEventCount,
    SparkInterval.TernaryGoldbach.MobiusSegmentEventEnumeration.dvd_iff_existsUnique_event,
    SparkInterval.TernaryGoldbach.MobiusDenseVisitRealization.dvd_iff_existsUnique_denseVisit,
    SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing.rowLaunch_complete_duplicateFree,
    SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing.sparsePrimeLaunch_complete_duplicateFree,
    SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing.eventGridStride_complete_duplicateFree,
    SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing.multiblockEvent_complete_duplicateFree,
    SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing.denseFlatBlock_encode_injective])
  (statement := /--
    The optimized sieve's flat block grid decodes uniquely into a dense-prime
    index and one of 512 block slots. Each multiple ordinal belongs to one
    and only one contiguous `256 * 4096`-event span. For the declared
    1,073,741,824-row launch cap and every prime at least two, Lean proves the
    complete event roster fits those slots. Lean also proves that the
    native remainder/first-offset formula enumerates each divisible segment
    row exactly once.  More strongly, every divisible row has exactly one
    legal `(block, thread, loop-iteration)` visit in the residue-seeded
    147-slot schedule; Lean also checks the literal production launch
    arithmetic for rounded row grids, sparse-prime threads, one-block
    grid-stride loops, and the complete 512-slot
    `(prime, slot, iteration, thread)` rectangle. Commutativity then makes
    concurrent update order irrelevant to the mathematical support state.
    After the modulo-900 seed removes 2, 3, and 5, Lean also proves that 147
    slots are the exact safe minimum for the suffix beginning at 7: 147
    suffices throughout the same public domain and 146 fails at the endpoint.
    The native path retains the measured 512-slot schedule because reducing
    it did not produce a material benchmark improvement.
    The remaining boundary is refinement from compiled CUDA launch builtins,
    fixed-width indices, pointers, loops, and successful kernel execution to
    these natural-number formulas.
  -/)] SparkInterval.TernaryGoldbach.MobiusDenseVisitRealization.dvd_iff_existsUnique_denseVisit

attribute [blueprint "thm:mobius-residue-235-seed"
  (title := "The modulo-900 seed exactly replaces the 2, 3, and 5 event passes")
  (uses := [
    SparkInterval.TernaryGoldbach.MobiusResidue235.blockLocalResidue900_eq_sourceNumber_mod,
    SparkInterval.TernaryGoldbach.MobiusResidue235.seedPrime_dvd_residue_iff,
    SparkInterval.TernaryGoldbach.MobiusResidue235.seedPrime_sq_dvd_residue_iff,
    SparkInterval.TernaryGoldbach.MobiusResidue235.applyPrime_residue_eq,
    SparkInterval.TernaryGoldbach.MobiusResidue235.residueSeed_eq])
  (statement := /--
    Lean first proves that the production block-start residue plus physical
    thread, with its single conditional subtraction, is exactly the complete
    source row modulo 900. Because 900 is divisible by the squares of 2, 3,
    and 5, reducing a row
    modulo 900 preserves both divisibility and square-divisibility by each
    seeded prime. Lean proves that the resulting product/count/squareful seed,
    followed by any remaining prime roster, is exactly the ordinary full
    support fold. The compiled 900-entry table, its base-prime prefix check,
    and GPU execution remain separate native-refinement obligations.
  -/)] SparkInterval.TernaryGoldbach.MobiusResidue235.fold_prefix_suffix_eq_residueSeed

attribute [blueprint "thm:mobius-residue-2357-qualification-seed"
  (title := "The qualification modulo-49 extension exactly seeds prime 7")
  (uses := [
    SparkInterval.TernaryGoldbach.MobiusResidue2357.blockLocalResidue49_eq_sourceNumber_mod,
    SparkInterval.TernaryGoldbach.MobiusResidue2357.blockLocalResidue49_mod_seven_eq_zero_iff,
    SparkInterval.TernaryGoldbach.MobiusResidue2357.blockLocalResidue49_eq_zero_iff,
    SparkInterval.TernaryGoldbach.MobiusResidue2357.applySeven_mod49_eq,
    SparkInterval.TernaryGoldbach.MobiusResidue2357.residueSeed2357_eq_fold,
    SparkInterval.TernaryGoldbach.MobiusResidue2357.residue2357MultipleEventCount_le_minimumCapacity,
    SparkInterval.TernaryGoldbach.MobiusResidue2357.residue2357PreviousSlotCount_insufficient,
    SparkInterval.TernaryGoldbach.MobiusResidue2357.residueSeed2357Word_lt_wordLimit])
  (statement := /--
    The qualification initializer reconstructs each physical row's exact
    residue modulo 49 from its block-start residue and local thread. Its
    literal `% 7 == 0` and `== 0` branches therefore detect exactly
    divisibility by 7 and 49. Applying that update after the production
    modulo-900 table is exactly the ordinary `[2,3,5,7]` support fold, stays
    within the packed word, and leaves a suffix beginning at 11 for which 94
    event slots are exactly sufficient at the public row cap. The separate
    API, differential/sanitizer evidence, qualification receipt identity, and
    target-H100 benchmark do not yet promote this optimization to production.
  -/)] SparkInterval.TernaryGoldbach.MobiusResidue2357.fold_prefix_suffix_eq_residueSeed2357

attribute [blueprint "thm:mobius-residue-235711-qualification-seed"
  (title := "The qualification modulo-121 extension exactly seeds prime 11")
  (uses := [
    SparkInterval.TernaryGoldbach.MobiusResidue235711.blockLocalResidue121_eq_sourceNumber_mod,
    SparkInterval.TernaryGoldbach.MobiusResidue235711.blockLocalResidue121_mod_eleven_eq_zero_iff,
    SparkInterval.TernaryGoldbach.MobiusResidue235711.blockLocalResidue121_eq_zero_iff,
    SparkInterval.TernaryGoldbach.MobiusResidue235711.applyEleven_mod121_eq,
    SparkInterval.TernaryGoldbach.MobiusResidue235711.residueSeed235711_eq_fold,
    SparkInterval.TernaryGoldbach.MobiusResidue235711.residue235711MultipleEventCount_le_minimumCapacity,
    SparkInterval.TernaryGoldbach.MobiusResidue235711.residue235711PreviousSlotCount_insufficient,
    SparkInterval.TernaryGoldbach.MobiusResidue235711.residueSeed235711Word_lt_wordLimit,
    SparkInterval.TernaryGoldbach.MobiusPackedCUDARosterPreflight.valid235711_of_deviceRosterInvalidFor_eq_false])
  (statement := /--
    The proposed initializer reconstructs each physical row's exact residue
    modulo 121. Its `% 11 == 0` and `== 0` branches detect exactly divisibility
    by 11 and 121, so extending the residue-2357 seed is exactly the ordinary
    `[2,3,5,7,11]` support fold. The packed result is safe, the suffix starts
    at 13, and 79 event slots are exactly sufficient at the public row cap.
    Lean also gives this candidate a distinct fail-closed roster mode. A
    qualification-only flat-512 native selector now implements the candidate
    behind a distinct algorithm/receipt identity and has passed bounded
    independent-CPU comparisons, generic/H100 compilation, and CUDA
    sanitizer checks. This is not target-H100 timing, compiled-code
    refinement, source-scale evidence, or production admission.
  -/)] SparkInterval.TernaryGoldbach.MobiusResidue235711.fold_prefix_suffix_eq_residueSeed235711

attribute [blueprint "thm:mobius-qualification-seeded-packed-refinement"
  (title := "The p7- and p11-seeded packed algorithms compute Möbius")
  (uses := [
    SparkInterval.TernaryGoldbach.MobiusResidue2357.fold_prefix_suffix_eq_residueSeed2357,
    SparkInterval.TernaryGoldbach.MobiusResidue235711.fold_prefix_suffix_eq_residueSeed235711,
    SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement.decodeWord_packedSplitRun_eq_valid_of_ne_poison,
    SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization.splitRun_eq_inlineRun,
    SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization.inlineRun_rowSplitEvents,
    SparkInterval.TernaryGoldbach.MobiusQualificationSeededRefinement.output_decodeWord_packedSplitRunResidue2357Seeded_eq_moebius])
  (statement := /--
    For either qualification seed, Lean now verifies the complete pure packed
    split-square algorithm rather than only its initializer. Given the
    explicit complete-prime-roster invariant and a nonpoison packed result,
    decoding and finalizing the 2·3·5·7 or 2·3·5·7·11 run produces exactly
    Mathlib's Möbius function. Compiled CUDA realization, roster
    authentication, and successful runtime execution remain the separately
    named native boundary.
  -/)] SparkInterval.TernaryGoldbach.MobiusQualificationSeededRefinement.output_decodeWord_packedSplitRunResidue235711Seeded_eq_moebius

attribute [blueprint "thm:mobius-rectangular-cuda-schedule"
  (title := "Parametric two-dimensional Möbius launch is an exact event partition")
  (uses := [
    SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule.multiblockEventWithSlots_complete_duplicateFree,
    SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule.rectangularEvent_complete_duplicateFree,
    SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule.multipleEventCount_le_requiredSlotsCapacity,
    SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule.previousRequiredSlotCount_insufficient,
    SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule.qualificationGrid_admissible,
    SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule.residue235_requiredSlots_le_minimumWidth,
    SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule.residue2357_requiredSlots_le_minimumWidth,
    SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule.residue235711_requiredSlots_le_minimumWidth,
    SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule.residue235RectangularEvent_complete_duplicateFree,
    SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule.residue2357RectangularEvent_complete_duplicateFree,
    SparkInterval.TernaryGoldbach.MobiusSegmentEventEnumeration.dvd_iff_existsUnique_event,
    SparkInterval.TernaryGoldbach.MobiusRectangularVisitRealization.dvd_iff_existsUnique_rectangularVisit,
    SparkInterval.TernaryGoldbach.MobiusRectangularVisitRealization.residue235_dvd_iff_existsUnique_countExactVisit,
    SparkInterval.TernaryGoldbach.MobiusRectangularVisitRealization.residue2357_dvd_iff_existsUnique_countExactVisit])
  (statement := /--
    For a qualification launch with `blockIdx.y = prime` and
    `blockIdx.x = slot`, Lean proves that every admitted prime/multiple pair
    has exactly one slot, thread, and loop-iteration owner. The proof is
    parametric in the rectangular width and specializes to the exact safe
    widths 147, 94, and 79 after the 2·3·5, 2·3·5·7, and
    2·3·5·7·11 seeds. Lean also proves the runtime formula
    `1 + (((count - 1) / minimumPrime) / 1,048,576)` is sufficient and
    minimal: at 100 million rows it selects 14, 9, and 8 slots respectively.
    Composing the event partition with the native arithmetic-progression
    theorem strengthens this to a source-facing equation: an in-segment row
    is divisible by its suffix prime if and only if exactly one
    `(prime, slot, thread, iteration)` coordinate visits it. This holds for
    the literal count-exact p5, p7, and p11 widths, not just the public-cap
    maxima.
    At most 200 prime rows and at most 512 slots fit the explicit CUDA
    grid-x/grid-y bounds. This removes division/remainder from the 2D
    kernel's per-block schedule model. The separate native implementation,
    executable receipt bindings, boundary KATs, and target-device benchmark
    remain qualification obligations before selecting that kernel.
  -/)] SparkInterval.TernaryGoldbach.MobiusRectangularVisitRealization.residue235711_dvd_iff_existsUnique_countExactVisit

attribute [blueprint "thm:mobius-fused-finalization"
  (title := "The fused CUDA support finalizes to Mathlib's Möbius function")
  (uses := [
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.update_comm,
    SparkInterval.TernaryGoldbach.MobiusResidue235.fold_prefix_suffix_eq_residueSeed,
    SparkInterval.TernaryGoldbach.MobiusResidualGCD.cardDistinctFactors_product_residual,
    SparkInterval.TernaryGoldbach.MobiusFusedFinalization.foldSupport_perm,
    SparkInterval.TernaryGoldbach.MobiusFusedFinalization.foldSupport_product,
    SparkInterval.TernaryGoldbach.MobiusFusedFinalization.foldSupport_distinctCount,
    SparkInterval.TernaryGoldbach.MobiusFusedFinalization.foldSupport_squareful,
    SparkInterval.TernaryGoldbach.MobiusFusedFinalization.sourceRowSupportValid_foldSupport,
    SparkInterval.TernaryGoldbach.MobiusFusedFinalization.signedParity_eq_negOnePow,
    SparkInterval.TernaryGoldbach.MobiusFusedFinalization.finalize_eq_moebius,
    SparkInterval.TernaryGoldbach.MobiusFusedFinalization.finalize_foldSupport_eq_moebius])
  (statement := /--
    Conditional prime events commute, so every serialization of the CUDA
    atomic updates has the same folded support.  Given the explicit
    complete-roster invariant—distinct divisor product, exact factor count,
    one-or-prime residual, and a multiplicity-preserving squareful bit—the
    native zero/parity finalizer equals Mathlib's Möbius function exactly.
    The modulo-900 seed is included in the same theorem chain.  Proving that
    the exact cubin, prime roster, CAS/CUB execution, and compiler realize
    this invariant remains the architecture-refinement obligation.
  -/)] SparkInterval.TernaryGoldbach.MobiusFusedFinalization.finalize_residueSeeded_eq_moebius

attribute [blueprint "thm:mobius-prime-roster-completeness"
  (title := "A prime roster through 10^8 is complete for every row through 10^16")
  (uses := [
    SparkInterval.TernaryGoldbach.MobiusFusedFinalization.finalize_foldSupport_eq_moebius,
    SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness.PrimeRosterThrough.completePrimeRoster,
    SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness.CompletePrimeRoster.sourceRosterValid])
  (statement := /--
    Lean derives the selected divisor product, exact distinct-factor count,
    square event, and one-or-prime residual from a short global contract:
    the roster is duplicate-free, every entry is prime, and it contains every
    prime through `10^8`.  Since `(10^8)^2 = 10^16`, this one certificate is
    sufficient for every production row.  The roster bytes still need a
    data-only primality/completeness certificate and machine binding.
  -/)] SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness.CompletePrimeRoster.finalize_foldSupport_eq_moebius

attribute [blueprint "thm:mobius-prime-roster-certificate-bridge"
  (title := "The reusable Pratt/gap checker supplies the Möbius roster contract")
  (uses := [
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.primeRosterCheck_sound,
    SparkInterval.TernaryGoldbach.MobiusPrimeRosterCertificateBridge.rosterBindingCheck_sound,
    SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness.PrimeRosterThrough.completePrimeRoster])
  (statement := /--
    The existing generic V2 checker verifies Lucas/Pratt evidence for every
    listed prime and explicit nontrivial factors for every omitted value.
    Its indexed exact-prime theorem is converted to the duplicate-free list
    contract used by the fused kernel, while a second Boolean check binds it
    to the exact decoded CUDA roster.  A production `10^8` certificate and
    its raw-byte decoder still have to be materialized and authenticated.
  -/)] SparkInterval.TernaryGoldbach.MobiusPrimeRosterCertificateBridge.productionPrimeRosterThrough_of_checkedBoundCertificate

attribute [blueprint "thm:mobius-segmented-sieve-roster"
  (title := "A linear-work sieve certificate proves the exact 10^8 prime roster")
  (uses := [
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.primeRosterCheck_sound,
    SparkInterval.TernaryGoldbach.MobiusSegmentedSieveRoster.witnessCheck_sound,
    SparkInterval.TernaryGoldbach.MobiusSegmentedSieveRoster.coverageCheck_sound,
    SparkInterval.TernaryGoldbach.MobiusSegmentedSieveRoster.rosterBindingCheck_sound,
    SparkInterval.TernaryGoldbach.MobiusSegmentedSieveRoster.factorCodeBytesBindingCheck_sound,
    SparkInterval.TernaryGoldbach.MobiusSegmentedSieveRoster.rosterBytesBindingCheck_sound])
  (statement := /--
    A short V2 certificate establishes only the 1,229 base primes through
    `10^4`.  The production artifact then stores one factor code for every
    integer from `2` through `10^8`.  Lean checks that every nonzero code is a
    genuine proper base-prime divisor and that every required sieve strike is
    nonzero.  Those two directions prove that zero-code survivors are exactly
    the primes, while canonical byte checks bind both packed factor codes and
    the ascending `u32le` roster.  The short base certificate is materialized
    in an optional generated module; proving the packed executable refines
    this source checker remains the execution-boundary obligation.
  -/)] SparkInterval.TernaryGoldbach.MobiusSegmentedSieveRoster.productionCertifiedRosterCheck_sound

attribute [blueprint "thm:mobius-guarded-machine-fail-closed"
  (title := "Every nonpoison fused event run is the exact Möbius fold")
  (uses := [
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.update_comm,
    SparkInterval.TernaryGoldbach.MobiusResidue235.fold_prefix_suffix_eq_residueSeed,
    SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness.CompletePrimeRoster.finalize_foldSupport_eq_moebius])
  (statement := /--
    The guarded state machine mirrors the native poison policy. Poison is
    absorbing and maps to sentinel `2`; otherwise every committed event is
    exactly the mathematical product/count/square update. Therefore a
    complete roster plus a zero poison count yields Mathlib's Möbius value
    without trusting per-row semantic assertions. The physical event
    enumeration and native execution still have to refine this guarded
    machine.
  -/)] SparkInterval.TernaryGoldbach.MobiusGuardedMachine.output_runResidueSeeded_eq_moebius

attribute [blueprint "thm:mobius-packed-guarded-refinement"
  (title := "The guarded packed-word update refines one mathematical event")
  (uses := [
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.unpackProduct_pack,
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.unpackCount_pack,
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.unpackSquareful_pack,
    SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement.maximumProductGuard_iff,
    SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement.nativeStepAdmissible_encodeSupport_iff,
    SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement.decodeWord_packedRunResidueSeeded])
  (statement := /--
    For every well-formed packed support word, the exact product-mask,
    five-bit-count, reserved-bit, overflow-division, squareful, and poison
    calculation used between successful CUDA CAS linearization points
    decodes to one transition of the abstract guarded machine. A rejected
    guard sets the poison bit; an accepted guard is the exact mathematical
    prime update. The theorem is lifted to every arbitrary serialized event
    list, including absorbing poison behavior. What remains native is
    atomic-CAS linearizability, physical register/loop realization, compiled
    instruction refinement, and authenticated execution—not the packed
    arithmetic or sequential fold itself.
  -/)] SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement.output_decodeWord_packedRunResidueSeeded_eq_moebius

attribute [blueprint "thm:psi-square-filter-equivalence"
  (title := "The square-only CH25 psi filter equals its square-root form")
  (uses := [
    SparkInterval.TernaryGoldbach.PsiLowerFilter.square_lt_iff_sqrt_boundary,
    SparkInterval.TernaryGoldbach.PsiLowerFilter.square_le_iff_le_sqrt,
    SparkInterval.TernaryGoldbach.PsiLowerFilter.sqrt_lt_iff_bound_lt_square])
  (statement := /--
    The optimized lower-endpoint fast path compares exact natural-number
    squares instead of computing an integer square root.  Both non-strict and
    strict decisions are unchanged, including the nonzero fixed-point
    remainder and perfect-square boundary cases.  The theorem does not by
    itself refine machine u128 multiplication to unbounded natural arithmetic.
  -/)] SparkInterval.TernaryGoldbach.PsiLowerFilter.strict_accept_square_iff

attribute [blueprint "thm:psi-affine-incoming-rectangle"
  (title := "One-pass CH25 psi shard guards are valid on an incoming-state rectangle")
  (uses := [
    SparkInterval.TernaryGoldbach.PsiAffineGuards.lowerRadiusQ64_sq_le,
    SparkInterval.TernaryGoldbach.PsiAffineGuards.strictLowerRadiusQ64_sq_lt,
    SparkInterval.TernaryGoldbach.PsiAffineGuards.upperRadiusQ64_sq_le,
    SparkInterval.TernaryGoldbach.PsiAffineGuards.lowerEndpointSafe_of_radius,
    SparkInterval.TernaryGoldbach.PsiAffineGuards.upperEndpointSafe_of_radius,
    SparkInterval.TernaryGoldbach.PsiAffineGuards.all_lower_safe_of_minimumIncoming,
    SparkInterval.TernaryGoldbach.PsiAffineGuards.all_upper_safe_of_maximumIncoming])
  (statement := /--
    A shard may summarize its exact Q16 square-root radii as conservative Q64
    lower and upper incoming-state bounds.  Taking the maximum of every lower
    requirement and the minimum of every upper allowance proves all endpoint
    guards for a root-derived state inside the retained rectangle.  The
    equality-triggered one-Q64-unit correction preserves the strict terminal
    inequality.  Native event enumeration, fixed-width arithmetic, and source
    execution remain separate physical refinement obligations.
  -/)] SparkInterval.TernaryGoldbach.PsiAffineGuards.all_radius_safe_of_folds

attribute [blueprint "thm:psi-affine-child-certificate"
  (title := "The ordered one-pass psi child scan is checked in Lean")
  (uses := [
    SparkInterval.TernaryGoldbach.PsiAffineGuards.all_radius_safe_of_folds])
  (statement := /--
    A kernel-reducible checker validates the zero root, exact child order and
    range chain, incoming affine rectangles, additive Q64 transitions, u128
    safety, final state, and the source plan geometry and event total.  Given
    a separate `RadiusRealized` premise connecting every compact child to its
    complete mathematical row lists, the checked chain proves every
    represented endpoint guard.  Neither the checker nor this conditional
    theorem proves native-row/source refinement, SHA-256 semantics, or
    physical execution.
  -/)] SparkInterval.TernaryGoldbach.PsiAffineChildCertificate.Certificate.checked_semantic_run_safe

/-! ## Goldbach prime-table prefix reuse -/

attribute [blueprint "thm:goldbach-prime-prefix-reuse"
  (title := "A completed larger prime table has the exact smaller prefix")
  (statement := /--
    Filtering the complete prime table through `smallHigh` at a smaller
    phase-2 bound gives exactly the table obtained by a fresh complete sieve
    through that bound. This is the mathematical equality behind the
    unpromoted v2 initialization optimization; it does not connect CUDA or a
    compiled binary to the model.
  -/)] SparkInterval.TernaryGoldbach.GoldbachPrimePrefixReuse.filter_primeTable_eq

/-! ## Formulaic q-major source schedule -/

attribute [blueprint "thm:dirichlet-formulaic-qmajor-exact-partition"
  (title := "Canonical 64-row targets uniquely partition each q roster")
  (uses := [
    SparkInterval.Dirichlet.FormulaicQMajorCursor.member_quotient_batch,
    SparkInterval.Dirichlet.FormulaicQMajorCursor.batchIndex_eq_div_of_mem])
  (statement := /--
    Every ordinate below a modulus's exact row count belongs to the batch
    selected by division by 64, and membership determines that quotient
    uniquely. This proves the discrete no-gap/no-overlap rule without
    materializing the 56,981,100 source targets.
  -/)] SparkInterval.Dirichlet.FormulaicQMajorCursor.batch_unique

attribute [blueprint "thm:dirichlet-formulaic-qmajor-bounded-target"
  (title := "Every canonical q-major target is nonempty and has at most 64 rows")
  (uses := [
    SparkInterval.Dirichlet.FormulaicQMajorCursor.batch_nonempty,
    SparkInterval.Dirichlet.FormulaicQMajorCursor.batchCount_le])
  (statement := /--
    For any batch whose first ordinate is in range, the formulaic target has
    positive length and never exceeds the fixed 64-row execution bound.
  -/)] SparkInterval.Dirichlet.FormulaicQMajorCursor.canonicalTarget_nonempty

attribute [blueprint "thm:dirichlet-formulaic-qmajor-lane-boundary"
  (title := "Canonical targets do not cross aligned t-major lane boundaries")
  (uses := [
    SparkInterval.Dirichlet.FormulaicQMajorCursor.batchCount_le])
  (statement := /--
    A target beginning before a 64-aligned lane boundary ends at or before
    it. The eight source archives may therefore be selected formulaically
    without splitting or duplicating a q/ordinate target.
  -/)] SparkInterval.Dirichlet.FormulaicQMajorCursor.batch_does_not_cross_aligned_lane

/-! ## Resident q-major source phases -/

attribute [blueprint "thm:dirichlet-resident-qmajor-exact-cover"
  (title := "Ten resident phases cover every source row exactly once")
  (uses := [
    SparkInterval.Dirichlet.ResidentQMajorPhases.inPhase_unique])
  (statement := /--
    Every source row below 127,988 belongs to exactly one of the ten
    resident q-major phases. The phase partition therefore neither omits nor
    duplicates a source row. This is a scheduling theorem only: it does not
    establish execution, interval containment, zero completeness, or
    attestation.
  -/)] SparkInterval.Dirichlet.ResidentQMajorPhases.source_row_exists_unique_phase

attribute [blueprint "thm:dirichlet-resident-qmajor-memory-bound"
  (title := "Every resident phase contains at most 39,488 source rows")
  (statement := /--
    Each phase's half-open row range contains no more than 39,488 rows. At
    one MiB per source row this is 38.5625 GiB. Together with the currently
    modeled work buffers this leaves 23 GiB of nominal H100 headroom, but is
    not a physical whole-device fit proof.
  -/)] SparkInterval.Dirichlet.ResidentQMajorPhases.phase_row_count_le

attribute [blueprint "thm:dirichlet-resident-qmajor-work-accounting"
  (title := "The eight slot workloads sum to the exact source total")
  (uses := [
    SparkInterval.Dirichlet.ResidentQMajorPhases.slot_work_le,
    SparkInterval.Dirichlet.ResidentQMajorPhases.phase_work_by_slot])
  (statement := /--
    The pinned per-slot butterfly counts sum to 15,334,965,882,246,056 and
    every slot stays below 1,998,670,835,119,088 butterflies. This proves
    the integer accounting used by the resource plan, not the projected
    runtime of a particular GPU implementation.
  -/)] SparkInterval.Dirichlet.ResidentQMajorPhases.slot_work_sum

attribute [blueprint "thm:dirichlet-phase-sign-state-associative"
  (title := "Ordered Dirichlet phase sign-state merging is associative")
  (uses := [
    SparkInterval.Dirichlet.PhaseSignState.State.combine_boundaryValid])
  (statement := /--
    A phase retains its first and last determinate signs and its internal
    transition count. Joining adjacent phases adds exactly one boundary
    transition when their strict signs differ. The merge is associative for
    well-formed states, so the ten resident phases may be reduced in any
    parenthesization without reordering them. Interval classification,
    ambiguity records, multiplicity, Turing closure, and execution remain
    separate obligations.
  -/)] SparkInterval.Dirichlet.PhaseSignState.State.combine_assoc

attribute [blueprint "thm:dirichlet-phase-ambiguity-runs-associative"
  (title := "Sparse Dirichlet ambiguity-run merging is associative")
  (uses := [
    SparkInterval.Dirichlet.PhaseSignState.AmbiguityRunState.combine_countValid])
  (statement := /--
    Maximal ambiguity ranges concatenate in order, except that a trailing
    ambiguous range and a leading ambiguous range meeting at the same phase
    boundary coalesce once. The signed count law is associative, and
    realizable nonnegative counts remain nonnegative. This verifies the
    compact boundary arithmetic; coordinates, CUDA implementation, and sparse
    wire parsing remain separate obligations.
  -/)] SparkInterval.Dirichlet.PhaseSignState.AmbiguityRunState.combine_assoc

attribute [blueprint "thm:dirichlet-phase-sign-fold-exact"
  (title := "Compact phase reduction equals the sequential sign scan")
  (uses := [
    SparkInterval.Dirichlet.PhaseSignFold.decisionTransitionCount_eq_filtered,
    SparkInterval.Dirichlet.PhaseSignFold.summarize_append])
  (statement := /--
    For every concrete three-way sign sequence, the compact state records its
    exact sample and ambiguity counts, its first and last determinate signs,
    and the number of changes after ambiguous samples are removed. Combining
    summaries of adjacent lists equals summarizing their concatenation. This
    verifies arbitrary ordered reduction trees against a direct list
    specification; classification, CUDA refinement, and physical execution
    remain separate obligations.
  -/)] SparkInterval.Dirichlet.PhaseSignFold.summarize_eq_reference

attribute [blueprint "thm:dirichlet-phase-ambiguity-fold-exact"
  (title := "Sparse phase reduction counts exact maximal ambiguity runs")
  (uses := [
    SparkInterval.Dirichlet.PhaseSignFold.Ambiguity.summarize_countValid,
    SparkInterval.Dirichlet.PhaseSignFold.Ambiguity.summarize_append])
  (statement := /--
    Folding concrete ambiguity decisions with the compact boundary operation
    produces exactly the natural number of maximal ambiguous runs. The
    signed internal counter is nonnegative on every realizable list, and
    adjacent-list summaries compose exactly. This verifies the sparse range
    count independently of CUDA packing and coordinate serialization.
  -/)] SparkInterval.Dirichlet.PhaseSignFold.Ambiguity.summarize_rangeCount_eq_maximal

attribute [blueprint "thm:dirichlet-phase-dense-wire-roundtrip"
  (title := "TGDCSB03 dense pages round-trip at the minimal exact width")
  (uses := [
    SparkInterval.Dirichlet.PhaseDenseWire.decode_encode,
    SparkInterval.Dirichlet.PhaseDenseWire.transitionCount_lt_capacity,
    SparkInterval.Dirichlet.PhaseDenseWire.encode_lt_recordCapacity,
    SparkInterval.Dirichlet.PhaseDenseWire.packedAt_packValues])
  (statement := /--
    The four canonical flags occupy bits zero through three and the
    transition count begins at bit four. A count below the sample count fits
    in `bit_length(sampleCount - 1)` bits (with the one-bit small-count
    convention), and consecutive fixed-width records decode exactly even
    when they cross byte boundaries. This verifies the arithmetic wire
    layout; native byte writes, parsing, CUDA refinement, and execution
    remain separate obligations.
  -/)] SparkInterval.Dirichlet.PhaseDenseWire.recordAt_packRecords

attribute [blueprint "thm:dirichlet-bluestein-dft-exact"
  (title := "Zero-padded Bluestein convolution equals the direct DFT")
  (uses := [
    SparkInterval.Dirichlet.BluesteinDFT.bluestein_kernel_identity,
    SparkInterval.Dirichlet.BluesteinDFT.centeredIndex_circularIndex,
    SparkInterval.Dirichlet.BluesteinDFT.paddedCyclicConvolutionValue_eq_wrappedConvolutionValue,
    SparkInterval.Dirichlet.BluesteinDFT.wrappedConvolutionValue_eq_bluesteinConvolutionValue,
    SparkInterval.Dirichlet.BluesteinDFT.bluesteinValue_eq_positiveDFT])
  (statement := /--
    For every positive transform length `N`, zero-padding to a cyclic
    convolution of length at least `2N-1`, applying both signed chirp wings,
    and post-multiplying by the output chirp gives the direct positive-sign
    DFT exactly. Lean checks the negative centered index, the no-alias guard,
    and every zero tail contribution. Proving that the staged interval
    FFT/IFFT trace computes this convolution, enclosing its transcendental
    roots, and refining the CUDA binary remain explicit downstream edges.
  -/)] SparkInterval.Dirichlet.BluesteinDFT.paddedBluesteinValue_eq_positiveDFT

attribute [blueprint "thm:dirichlet-basis-vector-dft"
  (title := "A basis-vector DFT is the corresponding row of unit roots")
  (statement := /--
    For any transform length and supported index `n`, the positive-sign DFT
    of the vector that is one at `n` and zero elsewhere is exactly
    `exp(2π i n k / N)` at frequency `k`.  The `n=1` instance is the
    independently checkable semantic oracle used by the maximum-order CUDA
    qualification; unlike the all-ones output of `n=0`, it exercises every
    nontrivial output root.
  -/)] SparkInterval.Dirichlet.BluesteinDFT.positiveDFT_basisOne_eq_unitRoot

attribute [blueprint "thm:dirichlet-bluestein-radix2-exact"
  (title := "The CUDA-sign radix-2 Bluestein network computes the direct DFT")
  (uses := [
    SparkInterval.Dirichlet.BluesteinFFTConvolution.negativeDFT_eq_dft,
    SparkInterval.Dirichlet.BluesteinFFTConvolution.normalizedPositiveRadix2_negativeRadix2,
    SparkInterval.Dirichlet.BluesteinFFTConvolution.negativeDFT_cyclicConvolution,
    SparkInterval.Dirichlet.BluesteinFFTConvolution.normalizedPositiveRadix2_pointwise_negativeRadix2,
    SparkInterval.Dirichlet.BluesteinFFTConvolution.circularIndex_mem_kernel_wings,
    SparkInterval.Dirichlet.BluesteinFFTConvolution.cyclicConvolution_zeroPaddedKernel,
    SparkInterval.Dirichlet.BluesteinDFT.paddedBluesteinValue_eq_positiveDFT])
  (statement := /--
    For every positive order and every power-of-two allocation at least
    `2N-1`, the exact network matching the CUDA sign convention—two
    negative-sign radix-2 transforms, pointwise multiplication, one
    normalized positive-sign inverse, and the post-chirp—equals the direct
    arbitrary-length positive DFT. The proof also shows that the CUDA
    kernel's literal-zero middle cannot affect any requested output.
    Directed interval containment for chirp and twiddle tables, refinement
    of fused CUDA operations, compilation, and physical execution remain
    separate obligations.
  -/)] SparkInterval.Dirichlet.BluesteinFFTConvolution.cuda_fft_pointwise_ifft_bluestein_eq_positiveDFT

attribute [blueprint "thm:dirichlet-bluestein-cuda-source-dataflow"
  (title := "The exact CUDA Bluestein source layout computes the direct DFT")
  (uses := [
    SparkInterval.Dirichlet.BluesteinCUDADataflow.cudaBrevShift_eq_reverseBits,
    SparkInterval.Dirichlet.BluesteinCUDADataflow.bitReversedWorkspaceIndex_injective,
    SparkInterval.Dirichlet.BluesteinCUDADataflow.tensorAddress_lt_total,
    SparkInterval.Dirichlet.BluesteinCUDADataflow.initializeA_write_to_bit_reversed_address,
    SparkInterval.Dirichlet.BluesteinCUDADataflow.pointwiseBitReverseCopy_write,
    SparkInterval.Dirichlet.BluesteinCUDADataflow.negativeSharedLaunch_eq_full,
    SparkInterval.Dirichlet.BluesteinCUDADataflow.positiveSharedLaunch_eq_full,
    SparkInterval.Dirichlet.BluesteinCUDADataflow.gatherOutputValue_eq_postChirp_normalized,
    SparkInterval.Dirichlet.BluesteinFFTConvolution.cuda_fft_pointwise_ifft_bluestein_eq_positiveDFT])
  (statement := /--
    Under the source guards `2 ≤ logLength ≤ 20` and `2N-1 ≤ 2^logLength`,
    the exact dataflow of `initializeA`, kernel bit-reversal, two
    negative-sign forward transforms, the fused pointwise/inverse scatter,
    the shared-memory prefix plus global suffix, the positive inverse, and
    gather's sole normalization equals the direct arbitrary-length positive
    DFT. Lean also proves the flattened scatter destinations are collision
    free and the source tensor addresses stay in allocation. Directed
    interval, CUDA execution, compiler, and physical-run refinement remain
    separate obligations.
  -/)] SparkInterval.Dirichlet.BluesteinCUDADataflow.cudaBluesteinSourceLineValue_eq_positiveDFT

attribute [blueprint "thm:dirichlet-largeq-composition-dft"
  (title := "The large-q DFT keeps finite recovery outside q to the minus s")
  (uses := [
    SparkInterval.Dirichlet.LargeQCompositionDFT.positiveDFT_add,
    SparkInterval.Dirichlet.LargeQCompositionDFT.positiveDFT_scale,
    SparkInterval.Dirichlet.LargeQCompositionDFT.naive_deferred_counterexample])
  (statement := /--
    The source-shaped residue is `q⁻ˢ * ζ_M + R_M`. Linearity sends its
    transform to `q⁻ˢ * DFT(ζ_M) + DFT(R_M)`: the finite-recovery transform
    is not multiplied by `q⁻ˢ`. Pulling one common factor through the
    production FFT would therefore require first multiplying every recovery
    residue by the inverse factor, or computing a separate recovery transform.
    This exact algebraic boundary prevents an unsound apparent optimization;
    interval FFT refinement and physical execution remain separate.
  -/)] SparkInterval.Dirichlet.LargeQCompositionDFT.positiveDFT_compose

attribute [blueprint "thm:dirichlet-sign-quadrant-interval-product"
  (title := "The optimized sign-quadrant product preserves every enclosure")
  (uses := [
    SparkInterval.RealInterval.signQuadrantMulLo_eq_mul_lo,
    SparkInterval.RealInterval.signQuadrantMulHi_eq_mul_hi,
    SparkInterval.RealInterval.signQuadrantMul_eq_mul,
    SparkInterval.RealInterval.directedSignQuadrantMulLo_le,
    SparkInterval.RealInterval.le_directedSignQuadrantMulHi])
  (statement := /--
    The nine-branch endpoint-selection tree used by the large-q CUDA
    multiplier is exactly the tight four-corner real interval product.
    Moreover, if each selected lower product is rounded downward and each
    selected upper product upward, the result still contains every exact
    product of values in the input intervals. This proves the arithmetic
    optimization for abstract directed-rounding functions; comparison,
    binary64-intrinsic, CUDA, compiler, and physical-execution refinement
    remain separate obligations.
  -/)] SparkInterval.RealInterval.directedSignQuadrantMul_contains

attribute [blueprint "thm:dirichlet-directed-complex-interval-product"
  (title := "Directed complex interval operations preserve exact arithmetic")
  (uses := [
    SparkInterval.RealInterval.directedAdd_contains,
    SparkInterval.RealInterval.directedSub_contains,
    SparkInterval.RealInterval.directedMul_contains])
  (statement := /--
    Rectangular complex addition, subtraction, and multiplication in the
    production CUDA operation order preserve enclosure whenever the supplied
    lower and upper rounding operations are outward. The real products use
    the verified nine-branch sign-quadrant implementation. This proves the
    abstract interval-arithmetic layer; showing that concrete binary64
    instructions, generated PTX/SASS, and a physical run realize those
    operations remains an explicit downstream refinement obligation.
  -/)] SparkInterval.ComplexInterval.directedMul_contains

attribute [blueprint "thm:dirichlet-directed-interval-radix2"
  (title := "The directed interval radix-2 graph encloses its exact DFT")
  (uses := [
    SparkInterval.Dirichlet.DirectedIntervalFFT.directedButterfly_contains,
    SparkInterval.Dirichlet.DirectedIntervalFFT.directedStage_contains_exactStage,
    SparkInterval.Dirichlet.DirectedIntervalFFT.runDirectedStages_contains,
    SparkInterval.Dirichlet.DirectedIntervalFFT.directedPositiveRadix2Transform_contains])
  (statement := /--
    Starting from bit-reversed input rectangles and a table of enclosing
    twiddle rectangles, every directed butterfly in the source-shaped
    radix-2 graph preserves pointwise containment. Induction over the exact
    `groupAt`, `offsetAt`, and output-side schedule gives the complete
    positive-sign transform and, with the separate pure radix-2 identity,
    the direct DFT. Root generation, binary64/CUDA realization, flat device
    memory, compilation, and physical execution remain explicit downstream
    obligations.
  -/)] SparkInterval.Dirichlet.DirectedIntervalFFT.directedPositiveRadix2Transform_contains_positiveDFT

attribute [blueprint "thm:dirichlet-directed-interval-bluestein"
  (title := "The complete directed CUDA-shaped Bluestein line encloses its DFT")
  (uses := [
    SparkInterval.Dirichlet.DirectedIntervalBluestein.directedPaddedInputNatural_contains,
    SparkInterval.Dirichlet.DirectedIntervalBluestein.bitReverseScatterInterval_contains,
    SparkInterval.Dirichlet.DirectedIntervalBluestein.directedNegativeFFTFromBitReversed_contains,
    SparkInterval.Dirichlet.DirectedIntervalBluestein.directedPositiveFFTFromBitReversed_contains,
    SparkInterval.Dirichlet.DirectedIntervalBluestein.directedPointwiseBitReverseCopy_contains,
    SparkInterval.Dirichlet.DirectedIntervalBluestein.directedGatherOutput_contains,
    SparkInterval.Dirichlet.DirectedIntervalBluestein.directedBluesteinLineValue_contains_cudaSourceLine,
    SparkInterval.Dirichlet.BluesteinCUDADataflow.cudaBluesteinSourceLineValue_eq_positiveDFT])
  (statement := /--
    Given explicit rectangles enclosing every source value, input and output
    chirp, padded kernel coefficient, forward and inverse twiddle, and the
    sole `1/L` normalization, the complete directed-arithmetic line matching
    the production CUDA dataflow contains the corresponding direct
    arbitrary-length positive DFT coefficient. The theorem covers
    pre-chirp, literal zero padding, source bit-reversal, both forward
    transforms, fused pointwise/inverse scatter, the inverse transform,
    post-chirp, and normalization. Concrete root production, binary64
    instruction refinement, compilation, and physical execution remain
    explicit downstream obligations.
  -/)] SparkInterval.Dirichlet.DirectedIntervalBluestein.directedBluesteinLineValue_contains_positiveDFT

attribute [blueprint "thm:high-precision-machin-pi"
  (title := "Machin's identity certifies the root checker's dyadic pi interval")
  (uses := [
    SparkInterval.Certified.atanSmall_containsReal,
    SparkInterval.Certified.machinPiInterval_containsReal])
  (statement := /--
    Exact rational alternating-series bounds for `arctan(1/5)` and
    `arctan(1/239)`, combined through Machin's identity, prove that the
    fixed adjacent 128-bit dyadic endpoints contain `π`. The long series is
    evaluated only while checking this theorem; root checks use the small
    proved constant. No decimal citation or native transcendental evaluator
    is trusted.
  -/)] SparkInterval.Certified.rootPiInterval_containsReal

attribute [blueprint "thm:bounded-high-degree-sincos"
  (title := "The nonreducing rational sine/cosine evaluator encloses a bounded interval")
  (uses := [
    SparkInterval.Certified.sinCosTaylorState_spec,
    SparkInterval.Certified.sinCosTaylorBase_containsReal,
    SparkInterval.Certified.sinCosTaylorSmall_containsReal])
  (statement := /--
    For an already-reduced rational interval whose lower endpoint is within
    the scale-and-climb domain, the checker evaluates an exact rational
    exponential Taylor recurrence, applies the proved factorial tail, and
    widens for the interval diameter. It deliberately performs no second
    period reduction, avoiding an unrelated lower-precision `2π` widening.
    A successful option contains both `sin y` and `cos y` for every real
    `y` in the supplied interval.
  -/)] SparkInterval.Certified.sinCosTaylorBoundedInterval_containsReal

attribute [blueprint "thm:dirichlet-configured-certified-root"
  (title := "Every positive-term configured rational generator encloses the DFT root")
  (uses := [
    SparkInterval.Certified.sinCosTaylorState_spec,
    SparkInterval.Certified.sinCosTaylorBase_containsReal,
    SparkInterval.Certified.sinCosTaylorBoundedInterval_containsReal,
    SparkInterval.Certified.machinPiInterval_containsReal,
    SparkInterval.Certified.rootTwoPiInterval_containsReal,
    SparkInterval.Dirichlet.CertifiedRootTable.phaseIntervalReduced_containsReal,
    SparkInterval.Dirichlet.CertifiedRootTable.unitRoot_mod,
    SparkInterval.Dirichlet.CertifiedRootTable.exactQuarterRoot?_containsComplex])
  (statement := /--
    For every positive order, the exponent is first reduced modulo the order.
    A 128-bit dyadic enclosure of `π` is derived once from Machin's identity
    and a proved exact-rational arctangent tail. Any positive number of terms
    of the exact rational complex-exponential series, with its
    `Complex.exp_bound` factorial tail, can be paired with any number of
    certified double-angle steps. A successful result,
    rounded outward to the requested dyadic grid, contains the exact positive
    DFT root. The four axis roots are recognized exactly, so exact binary64
    singleton boxes for `±1` and `±i` are accepted without introducing an
    avoidable finite-width `π` enclosure. Order zero fails closed. This
    theorem verifies the mathematical root generator; native code, MPFR,
    CUDA, compilation, and physical execution remain separate refinement
    edges.
  -/)] SparkInterval.Dirichlet.CertifiedRootTable.rootRectConfigured?_containsComplex

attribute [blueprint "thm:dirichlet-fast-certified-root"
  (title := "The qualified fast generator encloses every positive DFT root")
  (uses := [
    SparkInterval.Dirichlet.CertifiedRootTable.rootRectConfigured?_containsComplex])
  (statement := /--
    The production wrapper instantiates the general checked generator with
    thirteen exact exponential-series terms and nine certified double-angle
    steps. This configuration accepted all 799,976 chirp and odd-step roots
    in the maximum source-order recurrence dump at work precision 192 and
    output precision 128. The exhaustive replay qualifies performance and
    production-box compatibility; mathematical root containment follows
    directly from the general kernel-checked theorem.
  -/)] SparkInterval.Dirichlet.CertifiedRootTable.rootRectFast?_containsComplex

attribute [blueprint "thm:dirichlet-raw-binary64-root-certificate"
  (title := "A total raw-word checker proves a production root box")
  (uses := [
    SparkInterval.Certificate.RawInterval.decodeFinite_isValid,
    SparkInterval.Dirichlet.CertifiedRootTable.rootRectFast?_containsComplex,
    SparkInterval.Dirichlet.CertifiedRootWire.check_sound,
    SparkInterval.Dirichlet.CertifiedBluesteinRootBridge.fastRootCertificate_contains])
  (statement := /--
    Four raw binary64 endpoint words are decoded to exact rationals. NaNs,
    infinities, out-of-range words, and reversed coordinate intervals are
    rejected. The total checker runs the certified rational root generator
    and checks four rational endpoint inequalities. A successful `Bool`
    proves that the decoded production rectangle contains the exact positive
    DFT root. No runtime `Float`, MPFR, native evaluator, CUDA operation, or
    external oracle participates in this certificate check.
  -/)] SparkInterval.Dirichlet.CertifiedRootWire.checked_box_contains

attribute [blueprint "thm:dirichlet-positive-chirp-dump-certificate"
  (title := "One total checker certifies every root in a positive chirp-state dump")
  (uses := [
    SparkInterval.Dirichlet.CertifiedRootWire.checked_box_contains,
    SparkInterval.Dirichlet.CertifiedChirpStateWire.checkPositiveRow_chirp_sound,
    SparkInterval.Dirichlet.CertifiedChirpStateWire.checkPositiveRow_oddStep_sound,
    SparkInterval.Dirichlet.CertifiedChirpStateWire.checkPositiveDump_rows])
  (statement := /--
    A positive production chirp-state artifact is exactly `N` 64-byte rows,
    each holding raw binary64 endpoints for `exp(π i n²/N)` and
    `exp(π i (2n+1)/N)`. The checker rejects zero length, malformed words,
    truncation, trailing bytes, reversed intervals, and the first failed
    rational endpoint comparison. Acceptance proves that every row decodes
    and that both decoded boxes contain their exact roots. This is a
    mathematical file-checker theorem, not a compiler refinement, execution
    attestation, or discharge of an analytic external atom.
  -/)] SparkInterval.Dirichlet.CertifiedChirpStateWire.checkPositiveDump_root_containments

attribute [blueprint "thm:dirichlet-positive-fft-root-table-certificate"
  (title := "One total checker certifies every root in a flattened positive radix-2 table")
  (uses := [
    SparkInterval.Dirichlet.CertifiedRootWire.checked_box_contains,
    SparkInterval.Dirichlet.CertifiedFFTRootTableWire.specAtFlatIndex_source_order,
    SparkInterval.Dirichlet.CertifiedFFTRootTableWire.checkPositiveRoot_sound,
    SparkInterval.Dirichlet.CertifiedFFTRootTableWire.checkPositiveDump_geometry,
    SparkInterval.Dirichlet.CertifiedFFTRootTableWire.checkPositiveDump_rows,
    SparkInterval.Dirichlet.CertifiedFFTRootTableWire.checkPositiveDump_root_containments])
  (statement := /--
    A positive production radix-2 table for source convolution length `L`
    is exactly `L-1` 32-byte raw-binary64 rectangles. The literal layout
    concatenates stages `s=2,4,...,L`; stage `s` begins at offset `s/2-1`,
    and its row `j` must contain `unitRoot s j`. The checker accepts only the
    19 source powers `4,...,2^20` and rejects unsupported geometry, malformed
    words, truncation, trailing bytes, reversed intervals, and the first
    failed rational endpoint comparison. Acceptance proves every selected
    layout row decodes and contains its exact positive root. This is a
    mathematical file-checker theorem, not compiler refinement, execution
    attestation, or discharge of an analytic external atom.
  -/)] SparkInterval.Dirichlet.CertifiedFFTRootTableWire.checkPositiveDump_source_stage_root_containment

attribute [blueprint "thm:dirichlet-maximum-order-basis-one-output-certificate"
  (title := "A total checker identifies every maximum-order basis-one DFT output")
  (uses := [
    SparkInterval.Dirichlet.BluesteinDFT.positiveDFT_basisOne_eq_unitRoot,
    SparkInterval.Dirichlet.CertifiedRootWire.checked_box_contains,
    SparkInterval.Dirichlet.CertifiedBasisOneOutputWire.checkPositiveRow_sound,
    SparkInterval.Dirichlet.CertifiedBasisOneOutputWire.checkArtifact_components,
    SparkInterval.Dirichlet.CertifiedBasisOneOutputWire.checkArtifact_basisOne_dft_containments,
    SparkInterval.Dirichlet.CertifiedBasisOneOutputWire.checkMaximumOrderDeltaOneArtifact_header])
  (statement := /--
    The complete standard `TGDAFFO1` frame is parsed in its literal 56-byte
    little-endian layout. Acceptance pins magic, version one, q 399989, one
    component, one batch, group order and value count 399988, and 31,457,280
    radix-2 butterflies; only measured elapsed nanoseconds may vary. Exactly
    399,988 following raw-binary64 rectangles are then checked in source
    order, with truncation, trailing bytes, malformed endpoints, reversed
    intervals, and failed rational comparisons rejected. For every output
    index `k`, acceptance proves that its decoded box contains the exact
    positive DFT of the vector supported at input index one, using the proved
    equality `DFT(delta_1)[k] = unitRoot 399988 k`.

    The native wrapper hashes all header and payload bytes and labels its
    result unattested. The theorem checks artifact semantics; it does not
    prove CUDA/compiler refinement, physical execution, artifact provenance,
    or an analytic external atom.
  -/)] SparkInterval.Dirichlet.CertifiedBasisOneOutputWire.checkMaximumOrderDeltaOneArtifact_basisOne_dft_containments

attribute [blueprint "thm:dirichlet-certified-root-bluestein-capstone"
  (title := "Checked rational roots discharge every Bluestein root premise")
  (uses := [
    SparkInterval.Dirichlet.CertifiedRootTable.rootRectFast?_containsComplex,
    SparkInterval.Dirichlet.CertifiedBluesteinRootBridge.contains_of_enclosesRect,
    SparkInterval.Dirichlet.CertifiedBluesteinRootBridge.positiveTwiddlesContain_of_certificates,
    SparkInterval.Dirichlet.CertifiedBluesteinRootBridge.negativeTwiddlesContain_of_positive_certificates,
    SparkInterval.Dirichlet.CertifiedBluesteinRootBridge.inputChirpsContain_of_certificates,
    SparkInterval.Dirichlet.CertifiedBluesteinRootBridge.kernelContains_of_positive_chirp_certificates,
    SparkInterval.Dirichlet.DirectedIntervalBluestein.directedBluesteinLineValue_contains_positiveDFT])
  (statement := /--
    If each supplied production chirp and positive-twiddle box contains the
    exact rational rectangle returned by the checked fast root generator,
    then those finite endpoint comparisons discharge the complete directed
    Bluestein theorem. Negative twiddles and both kernel wings are obtained by
    proved complex conjugation, the middle is literal zero, and `1/L` is an
    exact singleton. The resulting line rectangle contains the direct DFT
    coefficient. Concrete endpoint decoding, directed binary64 instructions,
    compilation, and physical execution remain explicit downstream edges.
  -/)] SparkInterval.Dirichlet.CertifiedBluesteinRootBridge.certifiedRoots_directedBluestein_contains_positiveDFT

attribute [blueprint "thm:dirichlet-bluestein-chirp-recurrence"
  (title := "Two directed products generate every enclosed Bluestein chirp")
  (uses := [
    SparkInterval.Dirichlet.BluesteinChirpRecurrence.halfRoot_add,
    SparkInterval.Dirichlet.BluesteinChirpRecurrence.halfRoot_two_mul,
    SparkInterval.Dirichlet.BluesteinChirpRecurrence.exactStateAt_spec,
    SparkInterval.Dirichlet.BluesteinChirpRecurrence.directedNext_contains,
    SparkInterval.Dirichlet.BluesteinChirpRecurrence.runDirected_from_contains])
  (statement := /--
    From enclosures of the initial chirp, the initial odd phase, and the
    constant `exp(2πi/N)` update root, two directed complex products per
    index enclose `exp(πi n²/N)` for every natural index. This replaces an
    independent transcendental evaluation at every chirp entry and permits
    periodic certified restarts when a width policy requires them. Concrete
    fixed-point/CUDA realization and a qualified restart cadence remain
    explicit downstream obligations.
  -/)] SparkInterval.Dirichlet.BluesteinChirpRecurrence.runDirected_from_chirp_contains

attribute [blueprint "thm:dirichlet-dft-root-recurrence"
  (title := "Directed multiplication generates every enclosed DFT stage root")
  (uses := [
    SparkInterval.Dirichlet.DFTRootRecurrence.unitRoot_succ,
    SparkInterval.Dirichlet.DFTRootRecurrence.directedNext_contains])
  (statement := /--
    Starting from any independently certified DFT root and a certified
    enclosure of the unit stage step, repeated abstract directed complex
    multiplication encloses each successive exact root. The theorem supports
    periodic certified anchors while avoiding one transcendental evaluation
    per twiddle. Concrete binary64 instructions, the native producer,
    compilation, and physical execution remain separate refinement edges.
  -/)] SparkInterval.Dirichlet.DFTRootRecurrence.runDirected_from_contains

/-! ## Experimental t-major factor recurrence -/

attribute [blueprint "thm:dirichlet-tmajor-factor-recurrence"
  (title := "A checked complex-disk chain encloses repeated multiplication")
  (uses := [
    SparkInterval.Certified.ComplexDisk.MulCertificate.output_contains_mul])
  (statement := /--
    If every linked multiplication certificate is accepted, the final disk
    contains the seed multiplied by the fixed phase-step value once per
    certificate. This proves the recurrence arithmetic in ordinary Lean.
    The bounded downstream qualification found about 2.2-fold median
    widening after the all-character transform, so this experimental path is
    not promoted into the production algorithm.
  -/)] SparkInterval.Dirichlet.TMajorFactorRecurrence.output_contains_pow

attribute [blueprint "thm:dirichlet-completed-conductor-phase-step"
  (title := "The completed conductor phase advances by exactly 5/128")
  (uses := [
    SparkInterval.Dirichlet.Factor8Postprocess.sourceStep_eq,
    SparkInterval.Dirichlet.CompletedConductorPhase.exponentStep_eq,
    SparkInterval.Dirichlet.CompletedConductorPhase.sourceExponentAt_eq,
    SparkInterval.Dirichlet.CompletedConductorPhase.exponentAt_sourceExponentAt,
    SparkInterval.Dirichlet.CompletedConductorPhase.doubledExponentStep_ne])
  (statement := /--
    The completed-function conductor exponent is half the source `t`
    coordinate. Lean derives its `5/128` increment from the exact `5/64`
    source step, proves that each successor sample adds the increment once,
    and proves that the former double-step behavior is unequal.
  -/)] SparkInterval.Dirichlet.CompletedConductorPhase.exponentAt_succ

attribute [blueprint "thm:dirichlet-tmajor-checkpoint-layout"
  (title := "Checkpoint restarts preserve the exact conductor exponent")
  (uses := [
    SparkInterval.Dirichlet.CompletedConductorPhase.exponentAt_succ,
    SparkInterval.Dirichlet.TMajorCheckpointLayout.checkpointOwner_lt_count,
    SparkInterval.Dirichlet.TMajorCheckpointLayout.checkpointStart_lt_sampleCount,
    SparkInterval.Dirichlet.TMajorCheckpointLayout.sampleCount_le_checkpointCount_mul,
    SparkInterval.Dirichlet.TMajorCheckpointLayout.checkpoint_eq_owner])
  (statement := /--
    For positive sample and span bounds, division and remainder assign every
    source sample to exactly one half-open checkpoint span.  Lean proves that
    restarting at that checkpoint and applying the `5/128` conductor step
    once per in-span offset reaches exactly the same rational exponent as an
    uninterrupted recurrence.  Checkpoint disk realization and machine-code
    execution remain explicit downstream boundaries.
  -/)] SparkInterval.Dirichlet.TMajorCheckpointLayout.conductorExponentAt_checkpoint

attribute [blueprint "thm:dirichlet-completed-factor-parallel-schedule"
  (title := "The parallel checkpoint recurrence preserves every sample exponent")
  (uses := [
    SparkInterval.Dirichlet.CompletedFactorParallelSchedule.chunkSize_positive,
    SparkInterval.Dirichlet.CompletedFactorParallelSchedule.span_le_thread_capacity,
    SparkInterval.Dirichlet.CompletedFactorParallelSchedule.threadOwner_lt,
    SparkInterval.Dirichlet.CompletedFactorParallelSchedule.sample_mem_owner,
    SparkInterval.Dirichlet.CompletedFactorParallelSchedule.threadStart_add_offset,
    SparkInterval.Dirichlet.CompletedFactorParallelSchedule.thread_eq_owner])
  (statement := /--
    The optimized checkpoint kernel's 256 threads partition each positive
    span into clipped contiguous chunks. Lean proves complete, unique sample
    ownership and shows that the block-prefix exponent at a thread start plus
    its sequential local offset is exactly the uninterrupted `5/128`
    conductor exponent. Directed-disk containment and machine execution are
    kept as separate checked boundaries.
  -/)] SparkInterval.Dirichlet.CompletedFactorParallelSchedule.conductorExponentAt_thread

attribute [blueprint "thm:dirichlet-completed-factor-full-source-wire"
  (title := "Completed-factor artifacts retain the exact phase roster")
  (uses := [
    SparkInterval.Dirichlet.CompletedFactorWire.distinctNats_iff_nodup,
    SparkInterval.Dirichlet.CompletedFactorWire.parseGammaArtifact_sound,
    SparkInterval.Dirichlet.CompletedFactorWire.parseStepArtifact_sound,
    SparkInterval.Dirichlet.CompletedFactorWire.parseCheckpointArtifact_sound,
    SparkInterval.Dirichlet.CompletedFactorWire.checkFullSourceBundle_sound])
  (statement := /--
    The total gamma, conductor-step, and checkpoint parsers accept only finite
    binary64 disks with nonnegative radii and their exact source-shaped
    headers. The full-source bundle checker then requires the decoded
    checkpoint records to equal the complete ordered runtime phase roster,
    not merely its aggregate counts, and binds every cross-artifact digest.
    Arb containment, source execution, and attestation remain separate.
  -/)] SparkInterval.Dirichlet.CompletedFactorWire.checkFullSourceBundle_exactRoster

attribute [blueprint "thm:dirichlet-completed-factor-streaming-wire"
  (title := "The production completed-factor checker does not retain body rows")
  (uses := [
    SparkInterval.Dirichlet.CompletedFactorStreamingWire.checkDiskWindow_sound,
    SparkInterval.Dirichlet.CompletedFactorStreamingWire.scanCheckpointRows_sound,
    SparkInterval.Dirichlet.CompletedFactorStreamingWire.checkRosterFresh_sound,
    SparkInterval.Dirichlet.CompletedFactorStreamingWire.scanRosterTotals_sound,
    SparkInterval.Dirichlet.CompletedFactorStreamingWire.fullSourceExpectations_valid_of_streaming_scans,
    SparkInterval.Dirichlet.CompletedFactorStreamingWire.checkFullSourceBundle_sound])
  (statement := /--
    The production checker walks every gamma, step, and checkpoint disk once,
    validates the exact ordered `(q,sampleCount)` roster, and derives the
    original source-shaped expectation proposition. Its executable path does
    not materialize disk or checkpoint-record lists and does not run a list
    sort, generic `Nodup` decision, or recursive `List.sum`. Acceptance still
    proves every disk valid and every expected row present in order. Arb
    containment, source execution, attestation, and native-binary refinement
    remain separate boundaries.
  -/)] SparkInterval.Dirichlet.CompletedFactorStreamingWire.checkFullSourceBundle_exactRoster

attribute [blueprint "thm:dirichlet-qorder-factor-handoff"
  (title := "The canonical q-order manifest supplies the factor phase roster")
  (uses := [
    SparkInterval.Dirichlet.QOrderManifestWire.parseManifest_sound,
    SparkInterval.Dirichlet.QOrderManifestWire.checkFullSourceManifest_sound,
    SparkInterval.Dirichlet.QOrderManifestWire.checkScheduledFullSourceBundle_sound,
    SparkInterval.Dirichlet.CompletedFactorWire.checkFullSourceBundle_exactRoster])
  (statement := /--
    Lean parses the exact `TGDQORD1` wire, checks its complete source roster,
    formulaic ordinate counts, ordered-record hashes, and canonical file pin,
    and projects that same execution order onto a selected resident phase.
    Any accepted completed-factor bundle has exactly that projected
    `(q,sampleCount)` roster. A metadata-only substitute cannot enter at this
    handoff.
  -/)] SparkInterval.Dirichlet.QOrderManifestWire.checkScheduledFullSourceBundle_exactRoster

attribute [blueprint "thm:dirichlet-qorder-streaming-factor-handoff"
  (title := "The production q-order checker streams the exact factor roster")
  (uses := [
    SparkInterval.Dirichlet.QOrderManifestStreamingWire.buildFormulaicSourceBodyAux_toList,
    SparkInterval.Dirichlet.QOrderManifestStreamingWire.formulaicSourceSHA256_eq_spec,
    SparkInterval.Dirichlet.QOrderManifestStreamingWire.executionOrderSHA256_eq_spec,
    SparkInterval.Dirichlet.QOrderManifestStreamingWire.checkFullSourceManifest_sound,
    SparkInterval.Dirichlet.QOrderManifestStreamingWire.checked_formulaic_record_iff,
    SparkInterval.Dirichlet.QOrderManifestStreamingWire.checkScheduledFullSourceBundle_sound,
    SparkInterval.Dirichlet.QOrderManifestStreamingWire.checked_full_source_exact_phase_roster])
  (statement := /--
    The production `TGDQORD1` checker validates all 292,500 formulaic rows,
    their exact sample total and range coverage, uniqueness, source-order
    digest, execution-order digest, and full-file pin in linear passes. It
    retains the execution-order list needed downstream but creates no sorted
    copy and performs no generic list `Nodup` or `List.sum` decision.
    Successful composition walks the completed-factor checkpoints against
    exactly the selected phase projection. SHA-256 collision resistance,
    source provenance, native-binary refinement, attestation, and the
    analytic theorem remain separate boundaries.
  -/)] SparkInterval.Dirichlet.QOrderManifestStreamingWire.checkScheduledFullSourceBundle_exactRoster

/-! ## Pinned NVIDIA transcription and typed-machine refinement -/

attribute [blueprint "spec:nvidia-ptx-isa-9.0"
  (title := "NVIDIA PTX ISA 9.0 (external normative source)")
  (hasProof := false)
  (statement := /--
    Exact publisher, ISA version, CUDA archive, HTML/PDF URLs, and PDF SHA-256
    reviewed for this transcription.  This node records provenance; Lean
    cannot prove a natural-language vendor document was transcribed faithfully.
  -/)] SparkInterval.PTX.NvidiaPTX90.sourcePin

attribute [blueprint "def:nvidia-ptx-clause-map"
  (title := "Total NVIDIA PTX clause citation map")
  (uses := [SparkInterval.PTX.NvidiaPTX90.sourcePin])
  (statement := /--
    Maps every PTX clause used by this library to a section number and stable
    anchor in the pinned NVIDIA source.  Coverage is bibliographic
    traceability, not semantic refinement for every opcode.
  -/)] SparkInterval.PTX.NvidiaPTX90.Clause.reference

attribute [blueprint "def:nvidia-ptx-opcode-clause"
  (title := "Allowlisted opcodes map to NVIDIA PTX clauses")
  (uses := [SparkInterval.PTX.NvidiaPTX90.sourcePin,
    SparkInterval.PTX.NvidiaPTX90.Clause.reference])
  (statement := /--
    Assigns the primary normative clause in the pinned PTX document to every
    opcode admitted by the typed instruction language.
  -/)] SparkInterval.PTX.NvidiaPTX90.opcodeClause

attribute [blueprint "thm:allowed-opcodes-have-nvidia-citations"
  (title := "Every allowlisted opcode has a pinned NVIDIA clause")
  (uses := [SparkInterval.PTX.NvidiaPTX90.opcodeClause,
    SparkInterval.PTX.NvidiaPTX90.Clause.reference,
    SparkInterval.PTX.NvidiaPTX90.sourcePin])]
  SparkInterval.PTX.NvidiaPTX90.allowedOpcode_has_pinned_clause

attribute [blueprint "thm:typed-instructions-have-nvidia-citations"
  (title := "Every typed instruction has a pinned NVIDIA clause")
  (uses := [SparkInterval.PTX.NvidiaPTX90.opcodeClause,
    SparkInterval.PTX.NvidiaPTX90.Clause.reference,
    SparkInterval.PTX.NvidiaPTX90.sourcePin])]
  SparkInterval.PTX.NvidiaPTX90.acceptedInstruction_has_pinned_clause

attribute [blueprint "def:nvidia-finite-directed-arithmetic"
  (title := "PTX 9.0 finite directed-f64 transcription")
  (uses := [SparkInterval.PTX.NvidiaPTX90.sourcePin])
  (statement := /--
    Lean transcription of the finite-operand numeric clauses for f64 add,
    subtract, and multiply under round-toward-negative and
    round-toward-positive.  The source edge records a reviewed correspondence.
  -/)] SparkInterval.PTX.NvidiaPTX90.evalFinite

attribute [blueprint "thm:binary64-round-down-contained"
  (title := "Mathematical binary64 round-down is a lower bound")]
  SparkInterval.Binary64Rounding.roundDown_le

attribute [blueprint "thm:binary64-round-up-contained"
  (title := "Mathematical binary64 round-up is an upper bound")]
  SparkInterval.Binary64Rounding.le_roundUp

attribute [blueprint "thm:nvidia-round-down-contained"
  (title := "Transcribed PTX round-down result is a lower bound")
  (uses := [SparkInterval.PTX.NvidiaPTX90.evalFinite])
  (proofUses := [SparkInterval.Binary64Rounding.roundDown_le])]
  SparkInterval.PTX.NvidiaPTX90.evalFinite_towardNegative_le

attribute [blueprint "thm:nvidia-round-up-contained"
  (title := "Transcribed PTX round-up result is an upper bound")
  (uses := [SparkInterval.PTX.NvidiaPTX90.evalFinite])
  (proofUses := [SparkInterval.Binary64Rounding.le_roundUp])]
  SparkInterval.PTX.NvidiaPTX90.le_evalFinite_towardPositive

attribute [blueprint "def:nvidia-ptx-minimum"
  (title := "PTX 9.0 non-NaN minimum transcription")
  (uses := [SparkInterval.PTX.NvidiaPTX90.sourcePin])
  (statement := /--
    Lean transcription of `min.f64` on the model's non-NaN numeric domain.
  -/)] SparkInterval.PTX.NvidiaPTX90.minimum

attribute [blueprint "def:nvidia-ptx-maximum"
  (title := "PTX 9.0 non-NaN maximum transcription")
  (uses := [SparkInterval.PTX.NvidiaPTX90.sourcePin])
  (statement := /--
    Lean transcription of `max.f64` on the model's non-NaN numeric domain.
  -/)] SparkInterval.PTX.NvidiaPTX90.maximum

attribute [blueprint "def:ptx-directed-binary"
  (title := "Library directed binary64 arithmetic")
  (statement := /--
    Arithmetic used by the library's typed machine before relating it to the
    independent pinned-source transcription.
  -/)] SparkInterval.PTX.directedBinary

attribute [blueprint "def:ptx-numeric-minimum"
  (title := "Library typed non-NaN minimum semantics")]
  SparkInterval.PTX.F64Value.minimum

attribute [blueprint "def:ptx-numeric-maximum"
  (title := "Library typed non-NaN maximum semantics")]
  SparkInterval.PTX.F64Value.maximum

attribute [blueprint "thm:typed-arithmetic-refines-nvidia-transcription"
  (title := "Typed finite arithmetic equals the PTX 9.0 transcription")
  (uses := [SparkInterval.PTX.directedBinary,
    SparkInterval.PTX.NvidiaPTX90.evalFinite])]
  SparkInterval.PTX.NvidiaPTX90.directedBinary_finite_refines

attribute [blueprint "thm:typed-min-refines-nvidia-transcription"
  (title := "Typed non-NaN minimum equals the PTX 9.0 transcription")
  (uses := [SparkInterval.PTX.F64Value.minimum,
    SparkInterval.PTX.NvidiaPTX90.minimum])]
  SparkInterval.PTX.NvidiaPTX90.minimum_nonNaN_refines

attribute [blueprint "thm:typed-max-refines-nvidia-transcription"
  (title := "Typed non-NaN maximum equals the PTX 9.0 transcription")
  (uses := [SparkInterval.PTX.F64Value.maximum,
    SparkInterval.PTX.NvidiaPTX90.maximum])]
  SparkInterval.PTX.NvidiaPTX90.maximum_nonNaN_refines

attribute [blueprint "thm:ptx-directed-down-contained"
  (title := "Library round-down result is a lower bound")
  (uses := [SparkInterval.PTX.directedBinary])
  (proofUses := [SparkInterval.Binary64Rounding.roundDown_le])]
  SparkInterval.PTX.directedBinary_down_le

attribute [blueprint "thm:ptx-directed-up-contained"
  (title := "Library round-up result is an upper bound")
  (uses := [SparkInterval.PTX.directedBinary])
  (proofUses := [SparkInterval.Binary64Rounding.le_roundUp])]
  SparkInterval.PTX.le_directedBinary_up

attribute [blueprint "def:typed-ptx-instruction-execution"
  (title := "Typed PTX instruction execution")
  (statement := /--
    One-step semantics for every instruction constructor admitted by the
    generated-kernel AST.  This is a typed virtual-machine model, not a SASS
    interpreter and not a model of an NVIDIA processor.
  -/)] SparkInterval.PTX.executeInstruction

attribute [blueprint "thm:typed-step-refines-nvidia-arithmetic"
  (title := "Typed finite arithmetic step refines the PTX transcription")
  (uses := [SparkInterval.PTX.executeInstruction,
    SparkInterval.PTX.NvidiaPTX90.evalFinite])
  (proofUses := [
    SparkInterval.PTX.NvidiaPTX90.directedBinary_finite_refines])]
  SparkInterval.PTX.NvidiaPTX90.executeInstruction_binaryF64_finite_refines

attribute [blueprint "thm:typed-min-step-refines-nvidia-arithmetic"
  (title := "Typed minimum step refines the PTX transcription")
  (uses := [SparkInterval.PTX.executeInstruction,
    SparkInterval.PTX.NvidiaPTX90.minimum])
  (proofUses := [SparkInterval.PTX.NvidiaPTX90.minimum_nonNaN_refines])]
  SparkInterval.PTX.NvidiaPTX90.executeInstruction_minimumF64_nonNaN_refines

attribute [blueprint "thm:typed-max-step-refines-nvidia-arithmetic"
  (title := "Typed maximum step refines the PTX transcription")
  (uses := [SparkInterval.PTX.executeInstruction,
    SparkInterval.PTX.NvidiaPTX90.maximum])
  (proofUses := [SparkInterval.PTX.NvidiaPTX90.maximum_nonNaN_refines])]
  SparkInterval.PTX.NvidiaPTX90.executeInstruction_maximumF64_nonNaN_refines

attribute [blueprint "thm:typed-opcodes-closed"
  (title := "Typed instructions stay inside the opcode allowlist")]
  SparkInterval.PTX.Instruction.opcode_mem_allowed

/-! ## Compiler, emitter, and generated modeled run -/

attribute [blueprint "def:nvidia-dgx-spark-ptx-profile"
  (title := "Pinned DGX Spark PTX module profile")
  (uses := [SparkInterval.PTX.NvidiaPTX90.sourcePin])
  (statement := /--
    Formal `.version 9.0`, `.target sm_121`, and 64-bit address profile used
    by the DGX Spark emitter.  The source edge is transcription traceability.
  -/)] SparkInterval.PTX.NvidiaPTX90.dgxSparkProfile

attribute [blueprint "thm:emitter-pins-ptx-profile"
  (title := "Emitted module starts with PTX 9.0 / sm_121 / 64-bit profile")
  (uses := [SparkInterval.PTX.NvidiaPTX90.dgxSparkProfile])]
  SparkInterval.PTX.NvidiaPTX90.renderUnchecked_startsWith_dgxSparkProfile

attribute [blueprint "def:target-parameterized-ptx-profile"
  (title := "DGX and H100 emitter targets select pinned PTX profiles")
  (uses := [SparkInterval.PTX.NvidiaPTX90.dgxSparkProfile,
    SparkInterval.PTX.NvidiaPTX90.h100Profile])]
  SparkInterval.PTX.NvidiaPTX90.emitterModuleProfile

attribute [blueprint "thm:target-emitter-pins-ptx-profile"
  (title := "Every target-specific emission has its selected PTX 9.0 profile")
  (uses := [SparkInterval.PTX.NvidiaPTX90.emitterModuleProfile,
    SparkInterval.PTX.NvidiaPTX90.sourcePin])]
  SparkInterval.PTX.NvidiaPTX90.renderUncheckedFor_startsWith_emitterModuleProfile

attribute [blueprint "thm:h100-emitter-pins-sm90-profile"
  (title := "H100 rendering starts with the pinned sm_90 profile")
  (proofUses := [
    SparkInterval.PTX.NvidiaPTX90.renderUncheckedFor_startsWith_emitterModuleProfile])]
  SparkInterval.PTX.NvidiaPTX90.renderUncheckedH100_startsWith_h100Profile

attribute [blueprint "thm:generated-opcodes-have-nvidia-citations"
  (title := "Every generated opcode has a pinned NVIDIA clause")
  (uses := [SparkInterval.PTX.NvidiaPTX90.opcodeClause])
  (proofUses := [
    SparkInterval.PTX.NvidiaPTX90.allowedOpcode_has_pinned_clause,
    SparkInterval.PTX.Instruction.opcode_mem_allowed])]
  SparkInterval.PTX.NvidiaPTX90.buildModule_opcodeTrace_all_have_pinned_clauses

attribute [blueprint "def:generated-module-partial-ptx90-evidence"
  (title := "Scope of the generated module's partial PTX 9.0 evidence")
  (uses := [SparkInterval.PTX.NvidiaPTX90.dgxSparkProfile,
    SparkInterval.PTX.NvidiaPTX90.opcodeClause,
    SparkInterval.PTX.directedBinary,
    SparkInterval.PTX.NvidiaPTX90.evalFinite,
    SparkInterval.PTX.F64Value.minimum,
    SparkInterval.PTX.NvidiaPTX90.minimum,
    SparkInterval.PTX.F64Value.maximum,
    SparkInterval.PTX.NvidiaPTX90.maximum])
  (statement := /--
    Bundles the emitted profile, opcode citations, and finite/non-NaN
    arithmetic equalities.  It does not model all instruction semantics or
    connect PTX to ptxas, SASS, the driver, or physical hardware.
  -/)] SparkInterval.PTX.NvidiaPTX90.GeneratedModulePartialPTX90Evidence

attribute [blueprint "thm:generated-module-has-partial-ptx90-evidence"
  (title := "Generated modules carry the proved partial PTX 9.0 evidence")
  (uses := [
    SparkInterval.PTX.NvidiaPTX90.GeneratedModulePartialPTX90Evidence])
  (proofUses := [
    SparkInterval.PTX.NvidiaPTX90.renderUnchecked_startsWith_dgxSparkProfile,
    SparkInterval.PTX.NvidiaPTX90.buildModule_opcodeTrace_all_have_pinned_clauses,
    SparkInterval.PTX.NvidiaPTX90.directedBinary_finite_refines,
    SparkInterval.PTX.NvidiaPTX90.minimum_nonNaN_refines,
    SparkInterval.PTX.NvidiaPTX90.maximum_nonNaN_refines])
  (statement := /--
    Every module produced by `buildModule` satisfies the explicitly partial
    evidence bundle.  This theorem composes the pinned profile, citation, and
    arithmetic refinements; it is not whole-kernel hardware conformance.
  -/)] SparkInterval.PTX.NvidiaPTX90.buildModule_has_partial_ptx90_evidence

attribute [blueprint "thm:target-generated-module-has-partial-ptx90-evidence"
  (title := "DGX and H100 modules carry the proved partial PTX 9.0 evidence")
  (uses := [SparkInterval.PTX.NvidiaPTX90.emitterModuleProfile])
  (proofUses := [
    SparkInterval.PTX.NvidiaPTX90.renderUncheckedFor_startsWith_emitterModuleProfile,
    SparkInterval.PTX.NvidiaPTX90.buildModule_opcodeTrace_all_have_pinned_clauses,
    SparkInterval.PTX.NvidiaPTX90.directedBinary_finite_refines,
    SparkInterval.PTX.NvidiaPTX90.minimum_nonNaN_refines,
    SparkInterval.PTX.NvidiaPTX90.maximum_nonNaN_refines])
  (statement := /--
    The same deliberately partial source-level evidence is available for the
    `sm_121` and `sm_90` renderings.  It remains distinct from ptxas, SASS,
    driver, and physical-hardware conformance.
  -/)] SparkInterval.PTX.NvidiaPTX90.buildModule_has_partial_ptx90_evidenceFor

attribute [blueprint "thm:compiler-opcode-trace"
  (title := "Generated module has the prescribed opcode trace")]
  SparkInterval.PTX.buildModule_opcodeTrace

attribute [blueprint "thm:compiler-exact-structure"
  (title := "Generated module equals the structural compiler model")]
  SparkInterval.PTX.StructuralCompilerCorrect.buildModule_eq_expectedModule

attribute [blueprint "thm:deterministic-ptx-emission"
  (title := "Successful PTX emission is deterministic")
  (statement := /--
    A successful emitter call returns exactly the rendering of the validated
    typed module.  This theorem does not prove a text parser, ptxas lowering,
    SASS semantics, driver behavior, or physical execution.
  -/)] SparkInterval.PTX.emit_success

attribute [blueprint "thm:generated-add-fragment-contained"
  (title := "Generated directed-add fragment contains every exact sum")
  (proofUses := [SparkInterval.Binary64Rounding.roundDown_le,
    SparkInterval.Binary64Rounding.le_roundUp])]
  SparkInterval.PTX.addFragmentResult_contains

attribute [blueprint "thm:generated-sub-fragment-contained"
  (title := "Generated directed-subtract fragment contains every exact difference")
  (proofUses := [SparkInterval.Binary64Rounding.roundDown_le,
    SparkInterval.Binary64Rounding.le_roundUp])]
  SparkInterval.PTX.subFragmentResult_contains

attribute [blueprint "thm:generated-mul-fragment-contained"
  (title := "Generated directed-multiply fragment contains every exact product")
  (proofUses := [SparkInterval.Binary64Rounding.roundDown_le,
    SparkInterval.Binary64Rounding.le_roundUp])]
  SparkInterval.PTX.mulFragmentResult_contains

attribute [blueprint "thm:generated-arithmetic-node-contained"
  (title := "A guarded generated arithmetic node contains its exact result")
  (proofUses := [SparkInterval.PTX.addFragmentResult_contains,
    SparkInterval.PTX.subFragmentResult_contains,
    SparkInterval.PTX.mulFragmentResult_contains])]
  SparkInterval.PTX.guardedBinary_contains

attribute [blueprint "thm:generated-polynomial-arithmetic-contained"
  (title := "The complete generated polynomial arithmetic model is bounded")
  (proofUses := [SparkInterval.PTX.guardedBinary_contains])
  (statement := /--
    Structural induction over the supported polynomial language proves exact
    real containment for constants, variables, negation, add/subtract,
    multiply, natural powers, and the conservative nonfinite path.
  -/)] SparkInterval.PTX.PolynomialExpr.evalKernel_sound

attribute [blueprint "thm:generated-structured-module-executes"
  (title := "The exact generated module has a structured in-range execution")
  (uses := [SparkInterval.PTX.executeInstruction])]
  SparkInterval.PTX.executeBuildModuleStructured_inRange

attribute [blueprint "thm:generated-whole-module-executes"
  (title := "The exact generated module completes an in-range modeled run")
  (proofUses := [SparkInterval.PTX.executeBuildModuleStructured_inRange])]
  SparkInterval.PTX.runBuildModule_inRange

attribute [blueprint "thm:generated-modeled-run-contained"
  (title := "Generated modeled run contains the exact real result")
  (proofUses := [SparkInterval.PTX.PolynomialExpr.evalKernel_sound,
    SparkInterval.PTX.runBuildModule_inRange])]
  SparkInterval.PTX.runBuildModule_inRange_containsReal

attribute [blueprint "thm:division-not-yet-in-typed-compiler"
  (title := "The current typed opcode allowlist has no PTX division")
  (uses := [SparkInterval.PTX.NvidiaPTX90.opcodeClause])]
  SparkInterval.PTX.NvidiaPTX90.division_not_in_current_allowlist

attribute [blueprint "gap:directed-f64-division"
  (title := "GAP: directed-f64 division for the zeta compiler")
  (hasProof := false)
  (uses := [SparkInterval.PTX.NvidiaPTX90.sourcePin])
  (statement := /--
    PTX 9.0 specifies directed f64 division, but the current typed polynomial
    compiler has no division opcode or whole-kernel refinement theorem.  This
    citation node keeps that zeta-relevant gap visible.
  -/)] SparkInterval.PTX.NvidiaPTX90.directedF64DivisionRequirement

/-! ## Performance foundations and exact formal-program identity -/

attribute [blueprint "def:binary-power-schedule"
  (title := "Logarithmic multiplication schedule for natural powers")]
  SparkInterval.PTX.powSchedule

attribute [blueprint "thm:binary-power-schedule-denotes"
  (title := "The binary schedule denotes the requested exponent")
  (uses := [SparkInterval.PTX.powSchedule])]
  SparkInterval.PTX.powSchedule_denotes

attribute [blueprint "thm:binary-power-schedule-correct"
  (title := "Executing the binary schedule equals exact natural power")
  (uses := [SparkInterval.PTX.powSchedule])
  (proofUses := [SparkInterval.PTX.powSchedule_denotes])
  (statement := /--
    Algebraic correctness in every monoid.  A versioned interval compiler may
    lower each step through the existing proved multiplication fragment; the
    current version-one GPU compiler has not yet changed evaluation order.
  -/)] SparkInterval.PTX.runPowSchedule_eq_pow

attribute [blueprint "def:complex-rectangle-arithmetic"
  (title := "Complex rectangles lower to proved real interval operations")]
  SparkInterval.ComplexInterval

attribute [blueprint "thm:complex-rectangle-multiplication-contained"
  (title := "Complex rectangle multiplication contains exact products")
  (proofUses := [SparkInterval.RealInterval.mul_contains,
    SparkInterval.RealInterval.add_contains,
    SparkInterval.RealInterval.sub_contains])]
  SparkInterval.ComplexInterval.mul_contains

attribute [blueprint "thm:complex-rectangle-power-contained"
  (title := "Repeated complex rectangle powers contain exact powers")
  (proofUses := [SparkInterval.ComplexInterval.mul_contains])]
  SparkInterval.ComplexInterval.powNat_contains

attribute [blueprint "def:formal-emitted-ptx-program"
  (title := "Canonical-input/deployment-bound formal generated-PTX program")]
  SparkInterval.Execution.FormalPTXProgram

attribute [blueprint "def:formal-ptx-statement-check"
  (title := "Run statement binds validated PTX and canonical deployment identity")
  (uses := [SparkInterval.Execution.FormalPTXProgram,
    SparkInterval.PTX.emitFor])]
  SparkInterval.Execution.FormalPTXProgram.statementCheck

attribute [blueprint "thm:formal-ptx-statement-bound"
  (title := "Checked statement binds emitted PTX, input, domain, profile, and artifacts")
  (uses := [SparkInterval.Execution.FormalPTXProgram.statementCheck])]
  SparkInterval.Execution.FormalPTXProgram.statementCheck_sound

attribute [blueprint "thm:formal-ptx-emitted-text-identity"
  (title := "Successful formal emission equals deterministic typed rendering")
  (proofUses := [SparkInterval.PTX.emitFor_success])]
  SparkInterval.Execution.FormalPTXProgram.emitted_eq_renderUnchecked

attribute [blueprint "thm:formal-ptx-certified-outcome"
  (title := "Exact formal PTX identity composes with the one run axiom")
  (proofUses := [
    SparkInterval.Execution.FormalPTXProgram.statementCheck_sound,
    SparkInterval.Execution.SignedResultCertificate.outcomeCheck_sound])]
  SparkInterval.Execution.SignedResultCertificate.outcomeCheckForFormalPTX_sound

/-! ## Signed evidence and explicit trust boundaries -/

attribute [blueprint "def:registered-algorithm-registry"
  (title := "Closed registry of library-defined algorithm semantics")
  (statement := /--
    Every constructor fixes its identity, canonical encoding, and execution
    meaning in library code.  There is deliberately no constructor carrying a
    caller-selected proposition or semantics function.
  -/)] SparkInterval.Execution.RegisteredAlgorithm

attribute [blueprint "def:registered-algorithm-runs"
  (title := "Registry-fixed complete algorithm execution relation")
  (uses := [
    SparkInterval.Execution.RegisteredAlgorithm,
    SparkInterval.Execution.RegisteredAlgorithm.cubicSumDivThreeMachine])]
  SparkInterval.Execution.RegisteredAlgorithm.Runs

attribute [blueprint "def:registered-cubic-numerator-loop"
  (title := "Executable natural-number cube accumulator")]
  SparkInterval.Execution.RegisteredAlgorithm.cubicNumeratorLoop

attribute [blueprint "def:registered-cubic-operational-machine"
  (title := "Registered accumulator followed by one exact natural division")
  (uses := [
    SparkInterval.Execution.RegisteredAlgorithm.cubicNumeratorLoop])]
  SparkInterval.Execution.RegisteredAlgorithm.cubicSumDivThreeMachine

attribute [blueprint "thm:registered-cubic-loop-refines-sum"
  (title := "Operational numerator loop equals the exact rational cube sum")
  (uses := [
    SparkInterval.Execution.RegisteredAlgorithm.cubicNumeratorLoop])]
  SparkInterval.Execution.RegisteredAlgorithm.cubicNumeratorLoop_cast

attribute [blueprint "thm:registered-cubic-machine-result"
  (title := "Operational machine computes the exact registered output")
  (uses := [
    SparkInterval.Execution.RegisteredAlgorithm.cubicSumDivThreeMachine])
  (proofUses := [
    SparkInterval.Execution.RegisteredAlgorithm.cubicNumeratorLoop_cast,
    SparkInterval.Execution.RegisteredAlgorithm.sumCubes_eq_closedForm])]
  SparkInterval.Execution.RegisteredAlgorithm.cubicSumDivThreeMachine_20000

attribute [blueprint "thm:registered-cubic-loop-u64-bound"
  (title := "Every registered accumulator value fits uint64")
  (uses := [
    SparkInterval.Execution.RegisteredAlgorithm.cubicNumeratorLoop])]
  SparkInterval.Execution.RegisteredAlgorithm.cubicNumeratorLoop_lt_u64

attribute [blueprint "thm:registered-cubic-cube-u64-bound"
  (title := "Every registered cube operand fits uint64")]
  SparkInterval.Execution.RegisteredAlgorithm.cube_lt_u64

attribute [blueprint "thm:registered-cubic-square-u64-bound"
  (title := "Every registered intermediate square fits uint64")]
  SparkInterval.Execution.RegisteredAlgorithm.square_lt_u64

attribute [blueprint "thm:registered-cubic-step-u64-bound"
  (title := "Every registered accumulator addition avoids uint64 wraparound")
  (uses := [
    SparkInterval.Execution.RegisteredAlgorithm.cubicNumeratorLoop,
    SparkInterval.Execution.RegisteredAlgorithm.cube_lt_u64])
  (proofUses := [
    SparkInterval.Execution.RegisteredAlgorithm.cubicNumeratorLoop_lt_u64])]
  SparkInterval.Execution.RegisteredAlgorithm.cubicNumeratorStep_lt_u64

attribute [blueprint "thm:registered-cubic-result-u64-bound"
  (title := "The registered quotient fits uint64")
  (proofUses := [
    SparkInterval.Execution.RegisteredAlgorithm.cubicSumDivThreeMachine_20000])]
  SparkInterval.Execution.RegisteredAlgorithm.cubicSumDivThreeMachine_lt_u64

attribute [blueprint "thm:registered-cubic-machine-refines-specification"
  (title := "Operational registered result equals the exact rational specification")
  (uses := [
    SparkInterval.Execution.RegisteredAlgorithm.cubicSumDivThreeMachine,
    SparkInterval.Execution.RegisteredAlgorithm.cubicSumDivThree])
  (proofUses := [
    SparkInterval.Execution.RegisteredAlgorithm.cubicSumDivThreeMachine_20000,
    SparkInterval.Execution.RegisteredAlgorithm.cubicSumDivThree_20000])]
  SparkInterval.Execution.RegisteredAlgorithm.cubicSumDivThreeMachine_sound_20000

attribute [blueprint "def:registered-invocation"
  (title := "Closed versioned invocations with audited canonical inputs")
  (uses := [SparkInterval.Execution.RegisteredAlgorithm])]
  SparkInterval.Execution.RegisteredInvocation

attribute [blueprint "def:registered-invocation-statement-check"
  (title := "Exact statement binding for a closed registered invocation")
  (uses := [
    SparkInterval.Execution.RegisteredInvocation,
    SparkInterval.Execution.RegisteredAlgorithm])
  (statement := /--
    The Boolean check binds algorithm ID, formal-definition digest, canonical
    input digest, parameter digest, domain digest, and the constructor's
    explicit canonical result language.  It cannot be populated with
    caller-chosen execution semantics.
  -/)] SparkInterval.Execution.RegisteredInvocation.statementCheck

attribute [blueprint "def:registered-invocation-result-check"
  (title := "Canonical result-language guard for a registered invocation")
  (uses := [SparkInterval.Execution.RegisteredInvocation])
  (statement := /--
    Before fixed execution semantics can be selected, the result must belong
    to the invocation's explicit finite result language.  The axiom-free
    `resultAllowed_of_runs` theorem proves that the guard admits every
    legitimate `Runs` output.
  -/)] SparkInterval.Execution.RegisteredInvocation.resultCheck

attribute [blueprint "thm:registered-invocation-result-check-conservative"
  (title := "Every registered execution result passes its result-language guard")
  (uses := [
    SparkInterval.Execution.RegisteredInvocation.resultCheck,
    SparkInterval.Execution.RegisteredInvocation.Runs])]
  SparkInterval.Execution.RegisteredInvocation.resultAllowed_of_runs

attribute [blueprint "thm:registered-invocation-statement-check-unique"
  (title := "A statement selects at most one registered invocation")
  (uses := [SparkInterval.Execution.RegisteredInvocation.statementCheck])
  (statement := /--
    The proof enumerates every constructor pair, so adding an invocation must
    re-establish disjoint statement identity before the registry compiles.
  -/)] SparkInterval.Execution.RegisteredInvocation.statementCheck_unique

attribute [blueprint "thm:registered-invocation-runs-satisfiable"
  (title := "Every closed registered Runs relation has a concrete witness")
  (uses := [SparkInterval.Execution.RegisteredInvocation.Runs])
  (statement := /--
    Constructor-by-constructor witnesses give every registry entry at least
    one safe result.  For source computations the witness is the explicit
    `false` branch; this axiom-free guard does not establish that the
    success branch is inhabited.
  -/)] SparkInterval.Execution.RegisteredInvocation.runs_satisfiable

attribute [blueprint "def:registered-invocation-runs"
  (title := "Closed invocation-specific execution proposition")
  (uses := [
    SparkInterval.Execution.RegisteredInvocation,
    SparkInterval.Execution.RegisteredAlgorithm.Runs,
    SparkInterval.Execution.RegisteredAlgorithm.cubicSumDivThreeMachine])]
  SparkInterval.Execution.RegisteredInvocation.Runs

attribute [blueprint "def:dgx-operator-signature-policy"
  (title := "DGX operator-signature structural policy")]
  SparkInterval.Execution.checkDGXOperatorSignature

attribute [blueprint "def:h100-attestation-policy"
  (title := "H100 hardware-attestation structural policy")]
  SparkInterval.Execution.checkH100Attestation

attribute [blueprint "def:accepted-run-certificate-check"
  (title := "Unified external-run certificate checker")
  (uses := [SparkInterval.Execution.checkTrustedCompute])]
  SparkInterval.Execution.RunCertificate.check

attribute [blueprint "def:accepted-run-produced-outcome"
  (title := "Historical, physical, and compatibility facts at the trust boundary")
  (uses := [
    SparkInterval.Execution.Architecture.RegisteredArchitectureOutcomes,
    SparkInterval.Execution.RegisteredInvocation.statementCheck,
    SparkInterval.Execution.RegisteredInvocation.Runs])
  (statement := /--
    The outcome retains the exact historical return fact, a compact physical
    projection using the trusted-compute attestation's own receipt hash, and a
    temporary compatibility projection exposing the fixed `Runs` relation of
    a matching closed invocation. It contains no caller-provided execution
    predicate, formal machine, or pin bundle.
  -/)] SparkInterval.Execution.RunCertificate.ProducedOutcome

attribute [blueprint "def:accepted-run-historical-projection"
  (title := "Accepted outcome records the exact historical returned bytes")
  (uses := [SparkInterval.Execution.RunCertificate.ProducedOutcome])]
  SparkInterval.Execution.RunCertificate.ProducedOutcome.historical

attribute [blueprint "def:accepted-run-registered-projection"
  (title := "Accepted outcome exposes matching registry-fixed Runs semantics")
  (uses := [
    SparkInterval.Execution.RunCertificate.ProducedOutcome,
    SparkInterval.Execution.RegisteredInvocation.statementCheck,
    SparkInterval.Execution.RegisteredInvocation.Runs])]
  SparkInterval.Execution.RunCertificate.ProducedOutcome.registered

attribute [blueprint "def:accepted-run-architecture-projection"
  (title := "Accepted outcome exposes the exact registered physical run")
  (uses := [
    SparkInterval.Execution.RunCertificate.ProducedOutcome,
    SparkInterval.Execution.Architecture.RegisteredArchitectureOutcomes])]
  SparkInterval.Execution.RunCertificate.ProducedOutcome.registeredArchitecture

attribute [blueprint "axiom:accepted-run-certificate"
  (title := "TRUST AXIOM: accepted evidence yields exact physical run facts")
  (hasProof := false)
  (uses := [
    SparkInterval.Execution.RunCertificate.check,
    SparkInterval.Execution.RunCertificate.ProducedOutcome])
  (statement := /--
    This sole project trust axiom converts a source-admitted trusted-compute
    certificate into the exact historical returned-bytes fact, the closed
    physical architecture outcome for its own receipt hash, and a temporary
    compatibility `Runs` projection. It is the per-run trusted bridge across
    evidence verification, artifact measurement, backend behavior, and
    physical execution. It does not prove a general architecture-refinement
    theorem; algorithm soundness and result mathematics remain downstream.
  -/)] SparkInterval.Execution.Trusted.accepted_run_certificate_sound

attribute [blueprint "thm:receipt-attributed-accepted-run"
  (title := "Concrete receipt hash labels one accepted-run axiom use")
  (uses := [SparkInterval.Execution.RunCertificate.check])
  (proofUses := [
    SparkInterval.Execution.Trusted.accepted_run_certificate_sound])
  (statement := /--
    This ordinary theorem keeps the literal receipt SHA-256 and its equality
    with the certificate attestation visible in the proof term.  The
    `#print certificates` and `#audit certificates` commands use this node to
    report concrete instantiations without adding another axiom.
  -/)] SparkInterval.Execution.Trusted.acceptedRunCertificateForReceipt

attribute [blueprint "thm:accepted-registered-run"
  (title := "Accepted matching invocation yields its fixed Runs proposition")
  (uses := [
    SparkInterval.Execution.RegisteredInvocation.statementCheck,
    SparkInterval.Execution.RegisteredInvocation.Runs])
  (proofUses := [
    SparkInterval.Execution.Trusted.accepted_run_certificate_sound,
    SparkInterval.Execution.RunCertificate.ProducedOutcome.registered])]
  SparkInterval.Execution.Trusted.accepted_registered_run_sound

attribute [blueprint "thm:accepted-registered-architecture-outcomes"
  (title := "Accepted receipt yields its fixed physical architecture outcome")
  (uses := [
    SparkInterval.Execution.Architecture.RegisteredArchitectureOutcomes])
  (proofUses := [
    SparkInterval.Execution.Trusted.accepted_run_certificate_sound,
    SparkInterval.Execution.RunCertificate.ProducedOutcome.registeredArchitecture])]
  SparkInterval.Execution.Trusted.accepted_registered_architecture_outcomes

/-! ## Independently checked result certificates -/

attribute [blueprint "thm:full-result-certificate"
  (title := "A checked full certificate proves every row bound")]
  SparkInterval.Certificate.impliesTheorem

attribute [blueprint "thm:full-result-certificate-sum"
  (title := "A checked full certificate proves the finite-sum bound")]
  SparkInterval.Certificate.impliesSumTheorem

attribute [blueprint "def:signed-result-certificate"
  (title := "Operator-signed run plus exact full result certificate")]
  SparkInterval.Execution.SignedResultCertificate

attribute [blueprint "def:signed-result-binding-check"
  (title := "Executable result text/digest binding check")]
  SparkInterval.Execution.SignedResultCertificate.resultBindingCheck

attribute [blueprint "thm:signed-result-binding"
  (title := "The executable result binding proves exact text and hash equality")
  (uses := [
    SparkInterval.Execution.SignedResultCertificate.resultBindingCheck])]
  SparkInterval.Execution.SignedResultCertificate.resultBindingCheck_sound

attribute [blueprint "def:run-result-outcome-check"
  (title := "Accepted run plus exact returned-certificate binding")
  (uses := [SparkInterval.Execution.RunCertificate.check,
    SparkInterval.Execution.SignedResultCertificate.resultBindingCheck])]
  SparkInterval.Execution.SignedResultCertificate.outcomeCheck

attribute [blueprint "thm:run-result-outcome"
  (title := "The named computation returned the exact certificate bytes")
  (proofUses := [
    SparkInterval.Execution.Trusted.accepted_run_certificate_sound,
    SparkInterval.Execution.SignedResultCertificate.resultBindingCheck_sound])]
  SparkInterval.Execution.SignedResultCertificate.outcomeCheck_sound

attribute [blueprint "def:registered-run-result-outcome-check"
  (title := "Accepted exact result bound to a closed registered invocation")
  (uses := [
    SparkInterval.Execution.RegisteredInvocation.statementCheck,
    SparkInterval.Execution.SignedResultCertificate.outcomeCheck])]
  SparkInterval.Execution.SignedResultCertificate.outcomeCheckForRegisteredInvocation

attribute [blueprint "thm:registered-run-result-outcome"
  (title := "Closed invocation check yields identity, provenance, and fixed Runs")
  (uses := [
    SparkInterval.Execution.SignedResultCertificate.outcomeCheckForRegisteredInvocation])
  (proofUses := [
    SparkInterval.Execution.SignedResultCertificate.outcomeCheck_sound,
    SparkInterval.Execution.RunCertificate.ProducedOutcome.registered,
    SparkInterval.Execution.RegisteredInvocation.statementCheck_sound])]
  SparkInterval.Execution.SignedResultCertificate.outcomeCheckForRegisteredInvocation_sound

attribute [blueprint "thm:registered-cubic-sum-end-to-end"
  (title := "Accepted registered cubic-sum run yields its exact Lean result")
  (uses := [
    SparkInterval.Execution.cubicSumDivThree20000Invocation,
    SparkInterval.Execution.cubicSumDivThree20000Output,
    SparkInterval.Execution.RegisteredAlgorithm.cubicSumDivThreeMachine_sound_20000,
    SparkInterval.Execution.RegisteredAlgorithm.cubicNumeratorLoop_lt_u64,
    SparkInterval.Execution.RegisteredAlgorithm.square_lt_u64,
    SparkInterval.Execution.RegisteredAlgorithm.cube_lt_u64,
    SparkInterval.Execution.RegisteredAlgorithm.cubicNumeratorStep_lt_u64,
    SparkInterval.Execution.RegisteredAlgorithm.cubicSumDivThreeMachine_lt_u64])
  (proofUses := [
    SparkInterval.Execution.SignedResultCertificate.outcomeCheckForRegisteredInvocation_sound,
    SparkInterval.Execution.RegisteredInvocation.cubicSumDivThree20000V1_result])
  (statement := /--
    The sole trust axiom supplies the fixed per-run execution relation.  Exact
    output decoding, operational-loop refinement, symbolic sum-of-cubes
    identity, and uint64 no-wrap bounds are ordinary Lean proofs and require
    neither a 20,001-row certificate nor `native_decide`.  The uint64 theorems
    describe the registered machine model; the separate general deployment
    backend gap remains open.
  -/)] SparkInterval.Execution.SignedResultCertificate.certifyCubicSumDivThree20000

attribute [blueprint "def:cdem-abel-source-claim"
  (title := "Exact source-shaped CDEM replacement-table Abel claim")
  (statement := /--
    The two finite real inequalities use the exact replacement-table support,
    coefficients, floor-error sequence, range through five billion, and
    directed numerators of the live ternary-Goldbach source atom.  This is not
    the later coarse endpoint-inclusive consumer bound.
  -/)] SparkInterval.TernaryGoldbach.CDEMAbelSource.SourceClaim

attribute [blueprint "thm:cdem-abel-scaled-output-implies-source"
  (title := "Directed scaled CDEM numerators imply the exact source claim")
  (uses := [
    SparkInterval.TernaryGoldbach.CDEMAbelSource.ScaledOutputClaim,
    SparkInterval.TernaryGoldbach.CDEMAbelSource.SourceClaim])]
  SparkInterval.TernaryGoldbach.CDEMAbelSource.sourceClaim_of_scaledOutput

attribute [blueprint "thm:cdem-abel-local-recurrence-implies-global"
  (title := "Checked local CDEM recurrence evidence yields global source folds")
  (uses := [
    SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.Certificate,
    SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.LocalSourceScaleEvidence,
    SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.SourceScaleEvidence])
  (proofUses := [
    SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.floorState_jump,
    SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.Chunk.localFloorState_eq_floorState,
    SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.chain_realizes_of_local])
  (statement := /--
    A local witness starts from each retained `before` state, advances only by
    the closed divisor-marker recurrence, binds `after` to the resulting
    terminal state, and folds consecutive local error increments.  Checked
    initial-state and adjacency fields make those local states equal the
    global Möbius floor state.  No final real inequality is assumed.
  -/)]
  SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.sourceScaleEvidence_of_local

attribute [blueprint "thm:cdem-abel-local-certificate-implies-scaled-output"
  (title := "Checked local CDEM certificate implies the scaled source claim")
  (uses := [
    SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.LocalSourceScaleEvidence,
    SparkInterval.TernaryGoldbach.CDEMAbelSource.ScaledOutputClaim])
  (proofUses := [
    SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.sourceScaleEvidence_of_local])]
  SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.scaledOutputClaim_of_checked_local_certificate

attribute [blueprint "thm:registered-cdem-abel-output-implies-source"
  (title := "The closed CDEM invocation output yields the source claim")
  (uses := [
    SparkInterval.Execution.RegisteredInvocation.Runs,
    SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.Certificate,
    SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.LocalSourceScaleEvidence,
    SparkInterval.Generated.CDEMAbelProduction.certificate,
    SparkInterval.TernaryGoldbach.CDEMAbelSource.SourceClaim])
  (proofUses := [
    SparkInterval.Generated.CDEMAbelProduction.certificate_check,
    SparkInterval.TernaryGoldbach.CDEMAbelRecurrenceCertificate.scaledOutputClaim_of_checked_local_certificate,
    SparkInterval.TernaryGoldbach.CDEMAbelSource.sourceClaim_of_scaledOutput])]
  SparkInterval.Execution.RegisteredInvocation.cdemTableAbelProductionV2_sourceClaim

attribute [blueprint "thm:registered-cdem-abel-end-to-end"
  (title := "Accepted registered CDEM Abel run yields the exact source claim")
  (uses := [
    SparkInterval.Execution.cdemTableAbelProductionInvocation,
    SparkInterval.Execution.CertifiedCDEMTableAbel,
    SparkInterval.TernaryGoldbach.CDEMAbelSource.SourceClaim])
  (proofUses := [
    SparkInterval.Execution.SignedResultCertificate.outcomeCheckForRegisteredInvocation_sound,
    SparkInterval.Execution.RegisteredInvocation.cdemTableAbelProductionV2_sourceClaim])
  (statement := /--
    The one disclosed execution axiom supplies the closed `Runs` fact.
    A successful numeric output also supplies a checked gap-free integer
    recurrence certificate and physical `LocalSourceScaleEvidence`; it does
    not assume global source folds or the final real inequalities.  The local
    interface starts at each `before` field, advances by `floorJump`, binds
    `after` to the resulting terminal state, and folds consecutive local
    increments.  Checked initial-state and adjacency fields derive the global
    source states and folds.  The local fold realization itself remains
    physical evidence; endpoints alone cannot recover weighted internal
    totals.  The old global `SourceScaleEvidence` conversion is an off-path
    compatibility API.  Canonical decimal parsing, injective `Nat.pair`
    decoding, directed-rounding projection, and conversion to the exact
    rational inequalities are ordinary Lean proofs.  A
    definition-by-definition import theorem in the downstream ternary-
    Goldbach repository remains a separate obligation.
  -/)] SparkInterval.Execution.SignedResultCertificate.certifyCDEMTableAbel

attribute [blueprint "thm:registered-h100-formal-ptx-identity"
  (title := "Registered H100 pilot PTX is exactly the formal emitter output")
  (uses := [
    SparkInterval.Execution.h100FormalPtxConstantOneBatch,
    SparkInterval.Execution.RegisteredAlgorithm.h100FormalPtxConstantOnePTX])]
  SparkInterval.Execution.h100FormalPtxConstantOnePTX_eq_formalEmitter

attribute [blueprint "thm:registered-h100-pilot-end-to-end"
  (title := "Accepted registered H100 pilot yields its exact Lean result")
  (uses := [
    SparkInterval.Execution.h100FormalPtxConstantOneInvocation,
    SparkInterval.Execution.CertifiedH100FormalPtxConstantOne])
  (proofUses := [
    SparkInterval.Execution.SignedResultCertificate.outcomeCheckForRegisteredInvocation_sound,
    SparkInterval.Execution.h100FormalPtxConstantOnePTX_eq_formalEmitter])
  (statement := /--
    After the sole trust axiom supplies the fixed per-run execution relation,
    ordinary Lean reasoning recovers the exact compact result, proves both
    binary64 endpoint words decode to rational one, and identifies the
    registered `sm_90` PTX with the formal target-selected emitter.  This is a
    deliberately small deployment pilot rather than a zeta computation.
  -/)] SparkInterval.Execution.SignedResultCertificate.certifyH100FormalPtxConstantOne

attribute [blueprint "thm:exact-algorithm-run-result-outcome"
  (title := "The caller-pinned computation returned the exact certificate bytes")
  (proofUses := [
    SparkInterval.Execution.SignedResultCertificate.executableIdentityCheck_sound,
    SparkInterval.Execution.SignedResultCertificate.outcomeCheck_sound])]
  SparkInterval.Execution.SignedResultCertificate.outcomeCheckForAlgorithm_sound

attribute [blueprint "def:signed-executable-identity-check"
  (title := "Expected algorithm ID/hash equality check")]
  SparkInterval.Execution.SignedResultCertificate.executableIdentityCheck

attribute [blueprint "thm:signed-executable-identity-binding"
  (title := "The signed statement equals the expected algorithm ID/hash")
  (uses := [
    SparkInterval.Execution.SignedResultCertificate.executableIdentityCheck])
  (statement := /--
    A pure Boolean check yields literal equalities for the expected algorithm
    ID and executable-definition digest.  This is statement identity pinning,
    not a proof that a cubin was compiled from the formal PTX module.
  -/)] SparkInterval.Execution.SignedResultCertificate.executableIdentityCheck_sound

namespace SparkInterval.Blueprint

/-- Documentation-only target for the missing theorem relating the signed
executable identity to a formal PTX module and a compiled cubin.  `Unit` keeps
this marker axiom-free; its Blueprint metadata, rather than its value, records
the open proof obligation. -/
def executableIdentityToFormalArtifactGap : Unit := ()

/-- Documentation-only marker for the missing checked Hardy-Z and
Riemann-Siegel analytic evaluator. -/
def hardyZRiemannSiegelGap : Unit := ()

/-- Documentation-only marker for the missing total zero-count theorem. -/
def turingCountGap : Unit := ()

/-- Documentation-only marker for the analytic Platt interpolation
realization: Hardy-Z sample containment and the combined Lemmas C.1/C.3 tail
bound.  The 140-term rational interval fold and endpoint binding are proved. -/
def plattSincAnalyticRealizationGap : Unit := ()

/-- Documentation-only marker for an executable bounded-memory parser and
checker corresponding to the theorem-level chunk composition. -/
def streamingZetaCheckerGap : Unit := ()

/-- Documentation-only marker for the absent PT21 source-scale evidence
materializer, practical full campaign, and attested successful receipt. -/
def pt21FiniteRHSourceEvidenceGap : Unit := ()

/-- Documentation-only marker for the absent FLINT/Hardy-Z/count evidence,
downstream source-table identity bridge, and successful height-20,000 receipt. -/
def plattHead2e4SourceEvidenceGap : Unit := ()

/-- Documentation-only marker for the absent full Goldbach branch evidence,
transitive receipt provenance, and CPU finalizer materialization. -/
def finiteGoldbachSourceEvidenceGap : Unit := ()

/-- Documentation-only marker for the absent retained source-scale Hurst
producer realization. -/
def hurstPhysicalSourceEvidenceGap : Unit := ()

/-- Documentation-only marker for the absent retained, gap-free CH25 psi
prime-power/Q64 source evidence. -/
def psiPhysicalSourceEvidenceGap : Unit := ()

/-- Documentation-only marker for the absent theorem connecting the retained
FLINT/Arb A.7 boxes to Mathlib's exact zeta expression. -/
def a7FlintMathlibRealizationGap : Unit := ()

/-- Documentation-only marker for the three production edges deliberately
outside the typed factored small-`q` arithmetic trace theorem. -/
def factoredSmallQWholeFrameGap : Unit := ()

/-- Documentation-only marker for the analytic and artifact premises outside
the exact routine factor-eight postprocessing checker. -/
def dirichletFactor8AnalyticRealizationGap : Unit := ()

/-- Documentation-only marker for the remaining source-wide roster,
zero-isolation, conjugation, Hardy-model, and total-count obligations before
the exact Platt Theorem 7.1 handoff can be instantiated. -/
def plattTheorem71VerifierRealizationGap : Unit := ()

end SparkInterval.Blueprint

attribute [blueprint "gap:executable-identity-to-formal-artifact"
  (title := "GAP: formal emitted PTX to measured cubin/H100 backend")
  (hasProof := false)
  (notReady := true)
  (uses := [
    SparkInterval.Execution.SignedResultCertificate.executableIdentityCheck_sound,
    SparkInterval.Execution.FormalPTXProgram.statementCheck_sound,
    SparkInterval.Execution.FormalPTXProgram.emitted_eq_renderUnchecked,
    SparkInterval.PTX.StructuralCompilerCorrect.buildModule_eq_expectedModule])
  (statement := /--
    Documentation-only open obligation.  The dedicated formal-program check
    now derives the emitted-PTX digest from the exact typed batch and binds the
    canonical input, parameter, domain, target-profile, and artifact hashes.
    Its cubin and other deployment hashes remain caller-selected identities:
    no current Lean theorem proves that the named cubin was produced from that
    PTX or proves the ptxas/SASS/driver/physical-H100 steps between them.
  -/)] SparkInterval.Blueprint.executableIdentityToFormalArtifactGap

attribute [blueprint "thm:signed-certificate-upper-bound"
  (title := "Signed execution and checked certificate yield the combined result")
  (proofUses := [
    SparkInterval.Execution.Trusted.accepted_run_certificate_sound,
    SparkInterval.Execution.SignedResultCertificate.resultBindingCheck_sound,
    SparkInterval.Certificate.impliesTheorem])
  (statement := /--
    A successful combined checker yields an explicitly trusted execution
    claim, a proved byte-and-digest binding, and the independently proved full
    result-certificate theorem.  The arithmetic conclusion does not rely on
    the execution axiom.
  -/)] SparkInterval.Execution.SignedResultCertificate.checkUpperBound_sound

attribute [blueprint "thm:signed-certificate-sum-bound"
  (title := "Signed execution and checked certificate yield the sum result")
  (proofUses := [
    SparkInterval.Execution.Trusted.accepted_run_certificate_sound,
    SparkInterval.Execution.SignedResultCertificate.resultBindingCheck_sound,
    SparkInterval.Certificate.impliesSumTheorem])]
  SparkInterval.Execution.SignedResultCertificate.checkSumUpperBound_sound

attribute [blueprint "thm:signed-certificate-exact-algorithm-upper-bound"
  (title := "Pinned algorithm ID/hash, signed execution, and checked row bounds")
  (proofUses := [
    SparkInterval.Execution.SignedResultCertificate.executableIdentityCheck_sound,
    SparkInterval.Execution.SignedResultCertificate.checkUpperBound_sound])]
  SparkInterval.Execution.SignedResultCertificate.checkUpperBoundForAlgorithm_sound

attribute [blueprint "thm:signed-certificate-exact-algorithm-sum-bound"
  (title := "Pinned algorithm ID/hash, signed execution, and checked sum bound")
  (proofUses := [
    SparkInterval.Execution.SignedResultCertificate.executableIdentityCheck_sound,
    SparkInterval.Execution.SignedResultCertificate.checkSumUpperBound_sound])]
  SparkInterval.Execution.SignedResultCertificate.checkSumUpperBoundForAlgorithm_sound

/-! ## Finite-height zeta-zero verification -/

attribute [blueprint "def:platt-sinc-interpolation-checker"
  (title := "Exact 140-term Platt Gaussian--sinc checker")
  (statement := /--
    Checks the exact `21/512` spacing, `13/64` Gaussian parameter, all 70
    samples on either side, rational interval products and sum, and an
    explicit `2.45e-40` tail widening.  This deliberately repairs the retained
    split-source path that initializes but does not apply `intererr`.
  -/)]
  SparkInterval.Zeta.SincInterpolationCertificate.Certificate.check

attribute [blueprint "thm:platt-sinc-interpolation-sound"
  (title := "Checked interpolation contains the realized function value")
  (uses := [
    SparkInterval.Zeta.SincInterpolationCertificate.Certificate.check])]
  SparkInterval.Zeta.SincInterpolationCertificate.Certificate.output_contains

attribute [blueprint "thm:platt-sinc-bracket-sound"
  (title := "Two checked interpolations supply a zero bracket")
  (uses := [
    SparkInterval.Zeta.SincInterpolationCertificate.Certificate.check,
    SparkInterval.Zeta.RationalBracket.check])
  (proofUses := [
    SparkInterval.Zeta.SincInterpolationCertificate.Certificate.output_contains,
    SparkInterval.Zeta.RationalBracket.strictSignChange,
    SparkInterval.Zeta.Bracket.exists_zero])]
  SparkInterval.Zeta.SincInterpolationBracket.Certificate.exists_zero

attribute [blueprint "def:platt-turing-window-checker"
  (title := "Exact Platt Turing quotient and rounding checker")]
  SparkInterval.Zeta.TuringWindowCertificate.check

attribute [blueprint "def:platt-turing-grid-event-checker"
  (title := "Multiplicity-safe Platt Turing event-weight checker")]
  SparkInterval.Zeta.TuringGridEventCertificate.check

attribute [blueprint "thm:platt-turing-exact-count-closure"
  (title := "Turing bounds and isolated multiplicities force exact counts")
  (uses := [
    SparkInterval.Zeta.TuringWindowCertificate.check,
    SparkInterval.Zeta.TuringGridEventCertificate.check])]
  SparkInterval.Zeta.TuringWindowCertificate.exact_endpoint_counts

attribute [blueprint "def:platt-paired-flank-turing-checker"
  (title := "Three-stream Platt paired-flank Turing checker")
  (uses := [
    SparkInterval.Zeta.TuringWindowCertificate.check,
    SparkInterval.Zeta.TuringGridEventCertificate.check])]
  SparkInterval.Zeta.PairedTuringClosureCertificate.check

attribute [blueprint "thm:platt-paired-flank-finite-closure"
  (title := "Checked left/main/right streams force the source count equation")
  (uses := [SparkInterval.Zeta.PairedTuringClosureCertificate.check])]
  SparkInterval.Zeta.PairedTuringClosureCertificate.closure_equation

attribute [blueprint "thm:platt-paired-flank-analytic-closure"
  (title := "Paired Turing bounds and main multiplicity slots force exact endpoint counts")
  (uses := [SparkInterval.Zeta.PairedTuringClosureCertificate.check])
  (proofUses := [SparkInterval.Zeta.TuringWindowCertificate.exact_endpoint_counts])]
  SparkInterval.Zeta.PairedTuringClosureCertificate.exact_endpoint_counts

attribute [blueprint "gap:platt-sinc-analytic-realization"
  (title := "GAP: Hardy-Z samples and Platt Lemmas C.1/C.3 realization")
  (hasProof := false)
  (notReady := true)
  (uses := [
    SparkInterval.Zeta.SincInterpolationCertificate.Certificate.output_contains])
  (statement := /--
    The finite source geometry, interval composition, tail widening, endpoint
    binding, and zero-bracket composition are kernel proved.  Production still
    needs a proof that the source samples enclose Hardy Z and that the omitted
    interpolation tail obeys the combined published C.1/C.3 allowance.
  -/)] SparkInterval.Blueprint.plattSincAnalyticRealizationGap

attribute [blueprint "thm:sign-change-bracket-has-zero"
  (title := "Continuity and endpoint signs produce a bracketed real zero")]
  SparkInterval.Zeta.Bracket.exists_zero

attribute [blueprint "thm:ordered-zero-certificate-lower-bound"
  (title := "Separated brackets select distinct real zeros")
  (proofUses := [SparkInterval.Zeta.Bracket.exists_zero,
    SparkInterval.Zeta.OrderedBrackets.carrier_disjoint])]
  SparkInterval.Zeta.ZeroCertificate.exists_rootSelection

attribute [blueprint "def:executable-endpoint-sign-check"
  (title := "Linear adjacent-order exact-rational endpoint checker")]
  SparkInterval.Zeta.RationalBracketFamily.check

attribute [blueprint "thm:executable-endpoint-sign-check-sound"
  (title := "Checked endpoint data constructs an ordered zero certificate")
  (uses := [SparkInterval.Zeta.RationalBracketFamily.check])
  (proofUses := [SparkInterval.Zeta.RationalBracket.strictSignChange])]
  SparkInterval.Zeta.RationalBracketFamily.exists_zeroCertificate

attribute [blueprint "def:touching-endpoint-sign-check"
  (title := "Exact-rational strict bracket checker allowing shared endpoints")]
  SparkInterval.Zeta.TouchingRationalBracketFamily.check

attribute [blueprint "thm:touching-endpoint-roots-distinct"
  (title := "Touching strict brackets select distinct interior roots")
  (uses := [SparkInterval.Zeta.TouchingRationalBracketFamily.check])
  (proofUses := [
    SparkInterval.Zeta.Bracket.exists_zero_interior,
    SparkInterval.Zeta.RationalBracket.strictSignChange])]
  SparkInterval.Zeta.TouchingZeroCertificate.exists_rootSelection

attribute [blueprint "thm:touching-endpoint-check-sound"
  (title := "Checked touching endpoint data constructs a strict zero certificate")
  (uses := [SparkInterval.Zeta.TouchingRationalBracketFamily.check])
  (proofUses := [SparkInterval.Zeta.RationalBracket.strictSignChange])]
  SparkInterval.Zeta.TouchingRationalBracketFamily.exists_touchingZeroCertificate

attribute [blueprint "thm:touching-zero-certificate-complete-from-count"
  (title := "Touching strict brackets plus a matching count give exact coverage")
  (proofUses := [
    SparkInterval.Zeta.TouchingZeroCertificate.exists_rootSelection,
    SparkInterval.Zeta.TouchingZeroCertificate.RootSelection.exact_count_of_upperBound,
    SparkInterval.Zeta.TouchingZeroCertificate.RootSelection.complete_of_upperBound])]
  SparkInterval.Zeta.TouchingZeroCertificate.complete_of_count_upperBound

attribute [blueprint "thm:touching-endpoint-finite-height-zeta-verifier"
  (title := "Touching strict brackets and a global count prove the finite-height zeta result")
  (uses := [
    SparkInterval.Zeta.TouchingRationalBracketFamily.check,
    SparkInterval.Zeta.CriticalLineZeroBridge,
    SparkInterval.Zeta.ZetaZeroCountUpperBound])
  (proofUses := [
    SparkInterval.Zeta.TouchingZeroCertificate.complete_of_count_upperBound,
    SparkInterval.Zeta.all_zeros_to_height_on_criticalLine])]
  SparkInterval.Zeta.TouchingZetaVerifierEvidence.all_zeros_on_criticalLine

attribute [blueprint "thm:zero-certificate-complete-from-count"
  (title := "Matching lower and upper zero counts give exact coverage")
  (proofUses := [
    SparkInterval.Zeta.ZeroCertificate.exists_rootSelection,
    SparkInterval.Zeta.ZeroCertificate.RootSelection.exact_count_of_upperBound,
    SparkInterval.Zeta.ZeroCertificate.RootSelection.complete_of_upperBound])]
  SparkInterval.Zeta.ZeroCertificate.complete_of_count_upperBound

attribute [blueprint "def:chunked-zero-certificate"
  (title := "Independent ordered chunks of real zero brackets")]
  SparkInterval.Zeta.ChunkCertificate

attribute [blueprint "thm:chunked-zero-count-is-additive"
  (title := "Chunk-local bracket counts sum to a global zero lower bound")
  (proofUses := [SparkInterval.Zeta.ChunkCertificate.carrier_disjoint])]
  SparkInterval.Zeta.ChunkCertificate.RootSelection.sum_counts_le_zerosOn

attribute [blueprint "thm:chunked-zero-certificate-complete-from-count"
  (title := "Matching count makes chunked brackets exhaustive")
  (proofUses := [
    SparkInterval.Zeta.ChunkCertificate.exists_rootSelection,
    SparkInterval.Zeta.ChunkCertificate.RootSelection.exact_count_of_upperBound,
    SparkInterval.Zeta.ChunkCertificate.RootSelection.complete_of_upperBound])]
  SparkInterval.Zeta.ChunkCertificate.complete_of_count_upperBound

attribute [blueprint "def:finite-height-critical-rectangle"
  (title := "Closed finite-height critical-strip rectangle")]
  SparkInterval.Zeta.criticalRectangle

attribute [blueprint "thm:finite-height-zeta-target"
  (title := "Equal counts put every finite-height zeta zero on the line")
  (proofUses := [
    SparkInterval.Zeta.zetaZerosIn_finite,
    SparkInterval.Zeta.zetaZerosIn_eq_criticalLine_of_ncard_eq])]
  SparkInterval.Zeta.all_zeros_to_height_on_criticalLine

attribute [blueprint "def:zeta-zero-analytic-multiplicity"
  (title := "Analytic order of a zeta zero in ENat")]
  SparkInterval.Zeta.zetaZeroMultiplicity

attribute [blueprint "def:zeta-zero-multiplicity-count"
  (title := "Finite-rectangle sum of analytic zeta-zero multiplicities")
  (uses := [SparkInterval.Zeta.zetaZeroMultiplicity])]
  SparkInterval.Zeta.zetaZeroMultiplicityCount

attribute [blueprint "thm:distinct-zeta-zeros-le-multiplicity-count"
  (title := "Distinct zeta-zero count is at most analytic multiplicity count")
  (uses := [SparkInterval.Zeta.zetaZeroMultiplicityCount])
  (proofUses := [
    SparkInterval.Zeta.one_le_zetaZeroMultiplicity,
    SparkInterval.Zeta.card_zetaZerosFinset])]
  SparkInterval.Zeta.coe_ncard_le_zetaZeroMultiplicityCount

attribute [blueprint "def:zeta-multiplicity-count-upper-bound"
  (title := "Explicit analytic multiplicity-count upper-bound contract")
  (uses := [SparkInterval.Zeta.zetaZeroMultiplicityCount])]
  SparkInterval.Zeta.ZetaMultiplicityCountUpperBound

attribute [blueprint "thm:multiplicity-bound-controls-distinct-zero-count"
  (title := "Analytic multiplicity bound controls distinct zeta-zero count")
  (uses := [SparkInterval.Zeta.ZetaMultiplicityCountUpperBound])
  (proofUses := [
    SparkInterval.Zeta.coe_ncard_le_zetaZeroMultiplicityCount])]
  SparkInterval.Zeta.ZetaMultiplicityCountUpperBound.distinctCount_le

attribute [blueprint "thm:multiplicity-bound-supplies-verifier-upper-bound"
  (title := "Multiplicity upper bound supplies the zeta verifier contract")
  (proofUses := [
    SparkInterval.Zeta.ZetaMultiplicityCountUpperBound.distinctCount_le])]
  SparkInterval.Zeta.ZetaMultiplicityCountUpperBound.toZetaZeroCountUpperBound

attribute [blueprint "def:zeta-multiplicity-count-arithmetic-check"
  (title := "Exact arithmetic check on claimed and requested count bounds")]
  SparkInterval.Zeta.ZetaMultiplicityCountCertificate.check

attribute [blueprint "thm:checked-multiplicity-bound-supplies-verifier-upper-bound"
  (title := "Checked arithmetic plus analytic premise supplies verifier bound")
  (uses := [
    SparkInterval.Zeta.ZetaMultiplicityCountCertificate.check,
    SparkInterval.Zeta.ZetaMultiplicityCountUpperBound])
  (proofUses := [
    SparkInterval.Zeta.ZetaMultiplicityCountUpperBound.toZetaZeroCountUpperBound])]
  SparkInterval.Zeta.ZetaMultiplicityCountCertificate.check_sound

attribute [blueprint "def:critical-line-zero-bridge"
  (title := "Real evaluator zeros agree with critical-line zeta zeros")]
  SparkInterval.Zeta.CriticalLineZeroBridge

attribute [blueprint "def:hardy-z-model-contract"
  (title := "Continuous real Hardy-Z evaluator with nonvanishing phase")]
  SparkInterval.Zeta.HardyZModel

attribute [blueprint "thm:hardy-z-model-supplies-zero-bridge"
  (title := "A proved Hardy-Z representation supplies critical-line zero equivalence")
  (uses := [SparkInterval.Zeta.HardyZModel])]
  SparkInterval.Zeta.HardyZModel.criticalLineZeroBridge

attribute [blueprint "thm:hardy-z-endpoint-family-verifier"
  (title := "Checked endpoints plus analytic/count premises prove zeta result")
  (uses := [SparkInterval.Zeta.RationalBracketFamily.check,
    SparkInterval.Zeta.HardyZModel])
  (proofUses := [
    SparkInterval.Zeta.RationalBracketFamily.exists_zeroCertificate,
    SparkInterval.Zeta.HardyZModel.continuousOnBrackets,
    SparkInterval.Zeta.HardyZModel.criticalLineZeroBridge,
    SparkInterval.Zeta.ZetaVerifierEvidence.all_zeros_on_criticalLine])]
  SparkInterval.Zeta.HardyZModel.verifyEndpointFamily

/-! ## Signed zeta payload and final composition -/

attribute [blueprint "def:signed-zeta-endpoint-payload"
  (title := "Signed run paired with an exact typed full endpoint certificate")]
  SparkInterval.Execution.SignedZetaEndpointPayload

attribute [blueprint "def:signed-zeta-endpoint-shape-check"
  (title := "Exactly two singleton finite endpoint rows per bracket")]
  SparkInterval.Execution.SignedZetaEndpointPayload.endpointViewShapeCheck

attribute [blueprint "def:signed-zeta-pure-payload-check"
  (title := "Canonical parser, full arithmetic, shape, and family checks")
  (uses := [
    SparkInterval.Certificate.parseCanonicalFullCertificate,
    SparkInterval.Certificate.FullCertificate.check,
    SparkInterval.Execution.SignedZetaEndpointPayload.endpointViewShapeCheck,
    SparkInterval.Zeta.RationalBracketFamily.check])]
  SparkInterval.Execution.SignedZetaEndpointPayload.payloadCheck

attribute [blueprint "def:signed-zeta-batch-binding-check"
  (title := "Returned full-certificate batch binds to the formal input digest")
  (uses := [
    SparkInterval.Execution.FormalPTXProgram.statementCheck,
    SparkInterval.Certificate.parseCanonicalFullCertificate])]
  SparkInterval.Execution.SignedZetaEndpointPayload.batchBindingCheck

attribute [blueprint "thm:signed-zeta-batch-binding-check-sound"
  (title := "Accepted batch binding exposes both exact digest equalities")
  (uses := [SparkInterval.Execution.SignedZetaEndpointPayload.batchBindingCheck])]
  SparkInterval.Execution.SignedZetaEndpointPayload.batchBindingCheck_sound

attribute [blueprint "thm:signed-zeta-pure-payload-check-sound"
  (title := "Payload check exposes parsing, arithmetic, shape, and family facts")
  (uses := [
    SparkInterval.Execution.SignedZetaEndpointPayload.payloadCheck])
  (proofUses := [
    SparkInterval.Execution.SignedZetaEndpointPayload.parseBindingCheck_sound])]
  SparkInterval.Execution.SignedZetaEndpointPayload.payloadCheck_sound

attribute [blueprint "def:signed-zeta-endpoint-row-realization"
  (title := "Checked expression realizes the selected evaluator at endpoint rows")]
  SparkInterval.Execution.SignedZetaEndpointPayload.EndpointRowsRealize

attribute [blueprint "thm:checked-zeta-rows-supply-endpoint-enclosures"
  (title := "Full arithmetic soundness derives endpoint enclosures from row realization")
  (uses := [
    SparkInterval.Execution.SignedZetaEndpointPayload.EndpointRowsRealize])
  (proofUses := [
    SparkInterval.Certificate.FullCertificate.check_sound])]
  SparkInterval.Execution.SignedZetaEndpointPayload.CheckedPayload.enclosesEndpoints

attribute [blueprint "def:signed-zeta-formal-program-payload-check"
  (title := "Formal PTX outcome plus independently checked endpoint payload")
  (uses := [
    SparkInterval.Execution.SignedResultCertificate.outcomeCheckForFormalPTX,
    SparkInterval.Execution.SignedZetaEndpointPayload.batchBindingCheck,
    SparkInterval.Execution.SignedZetaEndpointPayload.payloadCheck])]
  SparkInterval.Execution.SignedZetaEndpointPayload.check

attribute [blueprint "thm:signed-zeta-formal-program-payload-check-sound"
  (title := "Accepted historical outcome and pure endpoint facts remain separate")
  (proofUses := [
    SparkInterval.Execution.SignedResultCertificate.outcomeCheckForFormalPTX_sound,
    SparkInterval.Execution.SignedZetaEndpointPayload.batchBindingCheck_sound,
    SparkInterval.Execution.SignedZetaEndpointPayload.payloadCheck_sound])
  (statement := /--
    Only the nested historical execution proposition crosses the sole project
    run-certificate axiom.  Canonical parsing, exact payload equality, full
    arithmetic checking, endpoint shape, and family signs/order are proved by
    ordinary checks.
  -/)] SparkInterval.Execution.SignedZetaEndpointPayload.check_sound

attribute [blueprint "thm:signed-statement-result-parses-as-endpoint-payload"
  (title := "The exact returned statement result parses to the typed payload")
  (proofUses := [
    SparkInterval.Execution.SignedZetaEndpointPayload.check_sound,
    SparkInterval.Execution.SignedResultCertificate.resultBindingCheck_sound])]
  SparkInterval.Execution.SignedZetaEndpointPayload.CertifiedForFormalPTX.statementResult_parses

attribute [blueprint "thm:signed-zeta-payload-supplies-zero-certificate"
  (title := "Checked payload plus explicit enclosures supplies zero brackets")
  (uses := [
    SparkInterval.Execution.SignedZetaEndpointPayload.check])
  (proofUses := [
    SparkInterval.Execution.SignedZetaEndpointPayload.check_sound,
    SparkInterval.Zeta.RationalBracketFamily.exists_zeroCertificate])
  (statement := /--
    The evaluator-specific `EnclosesEndpoints` theorem is an explicit premise;
    neither attestation nor payload arithmetic checking manufactures it.
  -/)] SparkInterval.Execution.SignedZetaEndpointPayload.check_exists_zeroCertificate

attribute [blueprint "def:certified-signed-zeta-verification"
  (title := "Historical provenance paired with finite-height zeta mathematics")
  (statement := /--
    The historical field contains the sole execution-axiom dependency.  The
    mathematical field is derived from independently checked payload facts and
    explicit analytic premises.
  -/)] SparkInterval.Execution.CertifiedZetaVerification

attribute [blueprint "thm:signed-zeta-finite-height-verification"
  (title := "Signed payload, Hardy model, enclosures, and multiplicity bound prove zeta result")
  (uses := [
    SparkInterval.Execution.SignedZetaEndpointPayload.check,
    SparkInterval.Zeta.HardyZModel,
    SparkInterval.Zeta.ZetaMultiplicityCountUpperBound])
  (proofUses := [
    SparkInterval.Execution.SignedZetaEndpointPayload.check_sound,
    SparkInterval.Zeta.HardyZModel.verifyEndpointFamily,
    SparkInterval.Zeta.ZetaMultiplicityCountUpperBound.toZetaZeroCountUpperBound])]
  SparkInterval.Execution.SignedZetaEndpointPayload.verifyFiniteHeight

attribute [blueprint "thm:signed-zeta-checked-rows-finite-height-verification"
  (title := "Checked rows plus realization semantics prove signed zeta result")
  (uses := [
    SparkInterval.Execution.SignedZetaEndpointPayload.EndpointRowsRealize,
    SparkInterval.Zeta.HardyZModel,
    SparkInterval.Zeta.ZetaMultiplicityCountUpperBound])
  (proofUses := [
    SparkInterval.Execution.SignedZetaEndpointPayload.check_sound,
    SparkInterval.Execution.SignedZetaEndpointPayload.CheckedPayload.enclosesEndpoints,
    SparkInterval.Execution.SignedZetaEndpointPayload.verifyFiniteHeight])]
  SparkInterval.Execution.SignedZetaEndpointPayload.verifyFiniteHeightFromCheckedRows

attribute [blueprint "thm:signed-zeta-checked-count-finite-height-verification"
  (title := "Checked count arithmetic plus analytic bound proves signed zeta result")
  (uses := [
    SparkInterval.Execution.SignedZetaEndpointPayload.check,
    SparkInterval.Zeta.ZetaMultiplicityCountCertificate.check])
  (proofUses := [
    SparkInterval.Execution.SignedZetaEndpointPayload.check_sound,
    SparkInterval.Zeta.ZetaMultiplicityCountCertificate.check_sound,
    SparkInterval.Zeta.HardyZModel.verifyEndpointFamily])]
  SparkInterval.Execution.SignedZetaEndpointPayload.verifyFiniteHeightWithCountCertificate

/-! ## Symmetric and positive-ordinate count handoff -/

attribute [blueprint "thm:symmetric-zeta-multiplicity-count-partition"
  (title := "Symmetric count partitions into positive, negative, and real-axis parts")]
  SparkInterval.Zeta.zetaZeroMultiplicityCount_partition

attribute [blueprint "def:zeta-conjugation-multiplicity-symmetry"
  (title := "Explicit zeta conjugation and multiplicity symmetry contract")]
  SparkInterval.Zeta.ZetaConjugationMultiplicitySymmetry

attribute [blueprint "thm:conjugation-equates-positive-negative-counts"
  (title := "Explicit conjugation symmetry equates half-rectangle counts")
  (uses := [SparkInterval.Zeta.ZetaConjugationMultiplicitySymmetry])]
  SparkInterval.Zeta.ZetaConjugationMultiplicitySymmetry.negative_eq_positive

attribute [blueprint "def:no-real-axis-zeta-zeros"
  (title := "Explicit no-real-axis-zero boundary premise")]
  SparkInterval.Zeta.NoRealAxisZetaZeros

attribute [blueprint "thm:symmetric-count-is-double-positive-count"
  (title := "Symmetry and no-axis-zero premises double the positive count")
  (uses := [
    SparkInterval.Zeta.ZetaConjugationMultiplicitySymmetry,
    SparkInterval.Zeta.NoRealAxisZetaZeros])
  (proofUses := [
    SparkInterval.Zeta.zetaZeroMultiplicityCount_partition,
    SparkInterval.Zeta.ZetaConjugationMultiplicitySymmetry.negative_eq_positive,
    SparkInterval.Zeta.NoRealAxisZetaZeros.realAxisMultiplicityCount_eq_zero])]
  SparkInterval.Zeta.zetaZeroMultiplicityCount_eq_two_mul_positive

attribute [blueprint "def:positive-zeta-multiplicity-upper-bound"
  (title := "Conventional positive-ordinate analytic upper-bound contract")]
  SparkInterval.Zeta.PositiveZetaMultiplicityCountUpperBound

attribute [blueprint "thm:positive-count-supplies-symmetric-multiplicity-bound"
  (title := "Positive upper bound and symmetry supply doubled symmetric bound")
  (uses := [
    SparkInterval.Zeta.PositiveZetaMultiplicityCountUpperBound,
    SparkInterval.Zeta.ZetaConjugationMultiplicitySymmetry,
    SparkInterval.Zeta.NoRealAxisZetaZeros])
  (proofUses := [
    SparkInterval.Zeta.zetaZeroMultiplicityCount_eq_two_mul_positive])]
  SparkInterval.Zeta.PositiveZetaMultiplicityCountUpperBound.toZetaMultiplicityCountUpperBound

attribute [blueprint "thm:positive-count-supplies-distinct-zero-bound"
  (title := "Positive multiplicity bound supplies doubled verifier upper bound")
  (proofUses := [
    SparkInterval.Zeta.PositiveZetaMultiplicityCountUpperBound.toZetaMultiplicityCountUpperBound,
    SparkInterval.Zeta.ZetaMultiplicityCountUpperBound.toZetaZeroCountUpperBound])]
  SparkInterval.Zeta.PositiveZetaMultiplicityCountUpperBound.toZetaZeroCountUpperBound

attribute [blueprint "thm:signed-zeta-positive-count-finite-height-verification"
  (title := "Checked rows and explicit positive-count symmetry prove zeta result")
  (uses := [
    SparkInterval.Execution.SignedZetaEndpointPayload.EndpointRowsRealize,
    SparkInterval.Zeta.PositiveZetaMultiplicityCountUpperBound,
    SparkInterval.Zeta.ZetaConjugationMultiplicitySymmetry,
    SparkInterval.Zeta.NoRealAxisZetaZeros])
  (proofUses := [
    SparkInterval.Execution.SignedZetaEndpointPayload.verifyFiniteHeightFromCheckedRows,
    SparkInterval.Zeta.PositiveZetaMultiplicityCountUpperBound.toZetaMultiplicityCountUpperBound])]
  SparkInterval.Execution.SignedZetaEndpointPayload.verifyFiniteHeightFromPositiveCount

attribute [blueprint "def:positive-endpoint-family-reflection"
  (title := "Reverse reflected negative brackets followed by positive brackets")]
  SparkInterval.Zeta.RationalBracketFamily.reflectPositive

attribute [blueprint "thm:positive-endpoint-family-reflection-sound"
  (title := "Even evaluator reflects valid positive endpoint certificates")
  (uses := [SparkInterval.Zeta.RationalBracketFamily.reflectPositive])
  (proofUses := [
    SparkInterval.Zeta.RationalBracket.reflect_isValid_iff,
    SparkInterval.Zeta.RationalBracket.reflect_enclosesEndpoints])]
  SparkInterval.Zeta.RationalBracketFamily.reflectPositive_isValid

attribute [blueprint "thm:signed-zeta-positive-rows-finite-height-verification"
  (title := "Positive-only checked rows reflect to the symmetric zeta verifier")
  (uses := [
    SparkInterval.Zeta.RationalBracketFamily.reflectPositive,
    SparkInterval.Zeta.HardyZModel,
    SparkInterval.Zeta.PositiveZetaMultiplicityCountUpperBound])
  (proofUses := [
    SparkInterval.Execution.SignedZetaEndpointPayload.check_sound,
    SparkInterval.Execution.SignedZetaEndpointPayload.CheckedPayload.enclosesEndpoints,
    SparkInterval.Zeta.RationalBracketFamily.reflectPositive_isValid,
    SparkInterval.Zeta.RationalBracketFamily.reflectPositive_enclosesEndpoints,
    SparkInterval.Zeta.HardyZModel.verifyEndpointFamily])]
  SparkInterval.Execution.SignedZetaEndpointPayload.verifyFiniteHeightFromPositiveRows

/-! ## Resumable one-pass endpoint-family checker -/

attribute [blueprint "def:endpoint-stream-state"
  (title := "Constant-size logical state retaining the previous bracket")]
  SparkInterval.Zeta.EndpointStreamState

attribute [blueprint "def:endpoint-stream-transition"
  (title := "Local validity and predecessor-order transition")
  (uses := [SparkInterval.Zeta.RationalBracket.check])]
  SparkInterval.Zeta.EndpointStreamState.step?

attribute [blueprint "def:endpoint-stream-chunk-runner"
  (title := "Resumable one-pass list-chunk runner")
  (uses := [SparkInterval.Zeta.EndpointStreamState.step?])]
  SparkInterval.Zeta.runEndpointChunk

attribute [blueprint "thm:endpoint-stream-chunk-append"
  (title := "Resuming chunks equals checking their concatenation")
  (uses := [SparkInterval.Zeta.runEndpointChunk])]
  SparkInterval.Zeta.runEndpointChunk_append

attribute [blueprint "def:endpoint-stream-check"
  (title := "Fresh one-pass endpoint-stream checker")
  (uses := [SparkInterval.Zeta.runEndpointChunk])]
  SparkInterval.Zeta.checkEndpointStream

attribute [blueprint "thm:endpoint-stream-global-family-sound"
  (title := "One-pass predecessor checks imply global family validity")
  (uses := [SparkInterval.Zeta.checkEndpointStream])
  (proofUses := [
    SparkInterval.Zeta.checkEndpointStream_sound,
    SparkInterval.Zeta.checkEndpointStream_checkCondition,
    SparkInterval.Zeta.RationalBracketFamily.isValid_iff_checkCondition])]
  SparkInterval.Zeta.checkEndpointStream_isValid

attribute [blueprint "thm:endpoint-stream-implies-family-check"
  (title := "One-pass stream acceptance implies existing family checker acceptance")
  (proofUses := [SparkInterval.Zeta.checkEndpointStream_isValid])]
  SparkInterval.Zeta.checkEndpointStream_familyCheck

/-! ## Independently checked endpoint-chunk stream -/

attribute [blueprint "def:endpoint-chunk-stream-state"
  (title := "Constant-size boundary state between endpoint chunks")]
  SparkInterval.Zeta.EndpointChunkStreamState

attribute [blueprint "def:endpoint-chunk-stream-check"
  (title := "Resumable exact-rational endpoint-chunk checker")
  (uses := [
    SparkInterval.Zeta.RationalEndpointChunk.check,
    SparkInterval.Zeta.checkEndpointStream])]
  SparkInterval.Zeta.checkEndpointChunkStream

attribute [blueprint "thm:endpoint-chunk-stream-resumption"
  (title := "Resuming chunk sequences equals concatenated checking")
  (uses := [SparkInterval.Zeta.runEndpointChunkStream])]
  SparkInterval.Zeta.runEndpointChunkStream_append

attribute [blueprint "thm:endpoint-chunk-stream-certificate-composition"
  (title := "Checked chunks compose into an additive chunk certificate")
  (uses := [SparkInterval.Zeta.checkEndpointChunkStream])
  (proofUses := [
    SparkInterval.Zeta.RationalEndpointChunk.exists_zeroChunk,
    SparkInterval.Zeta.EndpointChunkStreamValidFrom.orderedSpans,
    SparkInterval.Zeta.EndpointChunkStreamValidFrom.contiguousSpans])]
  SparkInterval.Zeta.exists_checkedEndpointChunkCertificate

attribute [blueprint "thm:endpoint-chunk-stream-finite-height-verification"
  (title := "Checked endpoint chunks plus analytic premises prove zeta result")
  (uses := [
    SparkInterval.Zeta.checkEndpointChunkStream,
    SparkInterval.Zeta.HardyZModel,
    SparkInterval.Zeta.ZetaZeroCountUpperBound])
  (proofUses := [
    SparkInterval.Zeta.exists_checkedEndpointChunkCertificate,
    SparkInterval.Zeta.ChunkedZetaVerifierEvidence.all_zeros_on_criticalLine])]
  SparkInterval.Zeta.verifyEndpointChunkStream

/-! ## Compact attested server-side verifier composition -/

attribute [blueprint "def:compact-attested-verifier-contract"
  (title := "Legacy FormalPTX compact contract with explicit execution semantics")
  (statement := /--
    This generic FormalPTX-only interface is retained for compatibility.  Its
    execution relation is caller-supplied and therefore still requires the
    separate `ExecutionRefines` premise below.  It is not the preferred closed-
    registry route.
  -/)]
  SparkInterval.Execution.CompactVerifierContract

attribute [blueprint "gap:compact-execution-refines-formal-semantics"
  (title := "LEGACY GAP: FormalPTX outcome refines caller-supplied compact semantics")
  (hasProof := false)
  (notReady := true)
  (uses := [
    SparkInterval.Execution.SignedResultCertificate.CertifiedFormalPTXOutcome,
    SparkInterval.Execution.CompactVerifierContract])
  (statement := /--
    `FormalPTXProgram` is not a closed `RegisteredInvocation`.  Consequently
    this legacy route still needs a separate theorem connecting its historical
    outcome to the contract's caller-supplied semantics.  The preferred
    registered path below does not consume this premise.  Neither path closes
    the independent general emitted-PTX/cubin/SASS/hardware refinement gap.
  -/)] SparkInterval.Execution.CompactVerifierContract.ExecutionRefines

attribute [blueprint "thm:compact-attested-zeta-composition"
  (title := "Legacy FormalPTX compact zeta composition with explicit refinement")
  (uses := [
    SparkInterval.Execution.CompactVerifierContract.ExecutionRefines,
    SparkInterval.Execution.compactFiniteHeightZetaContract])
  (proofUses := [
    SparkInterval.Execution.SignedResultCertificate.outcomeCheckForFormalPTX_sound,
    SparkInterval.Execution.SignedResultCertificate.certifyCompactVerifierOutcome])]
  SparkInterval.Execution.SignedResultCertificate.certifyCompactFiniteHeightZeta

attribute [blueprint "def:registered-compact-verifier-contract"
  (title := "Compact claim contract over closed registered execution semantics")
  (uses := [SparkInterval.Execution.RegisteredInvocation.Runs])
  (statement := /--
    The decoder and mathematical claim remain application data, but soundness
    must be proved from the closed invocation's library-defined `Runs`
    proposition.  No caller-selected physical execution relation is present.
  -/)] SparkInterval.Execution.RegisteredCompactVerifierContract

attribute [blueprint "def:registered-compact-verifier-soundness"
  (title := "Registered Runs plus decoding implies the compact claim")
  (uses := [
    SparkInterval.Execution.RegisteredCompactVerifierContract,
    SparkInterval.Execution.RegisteredInvocation.Runs])]
  SparkInterval.Execution.RegisteredCompactVerifierContract.Sound

attribute [blueprint "thm:registered-compact-verifier-outcome"
  (title := "Registered run and pure soundness yield a compact theorem")
  (uses := [
    SparkInterval.Execution.SignedResultCertificate.outcomeCheckForRegisteredInvocation,
    SparkInterval.Execution.RegisteredCompactVerifierContract.Sound])
  (proofUses := [
    SparkInterval.Execution.SignedResultCertificate.outcomeCheckForRegisteredInvocation_sound])
  (statement := /--
    This is the preferred small-download composition.  The accepted certificate
    supplies the fixed per-run semantics through the sole trust axiom; the
    remaining implication from those semantics to the decoded claim is an
    ordinary Lean theorem.
  -/)] SparkInterval.Execution.SignedResultCertificate.certifyRegisteredCompactVerifierOutcome

attribute [blueprint "thm:registered-compact-zeta-composition"
  (title := "Registered compact zeta composition without a second execution premise")
  (uses := [
    SparkInterval.Execution.RegisteredInvocation.Runs,
    SparkInterval.Execution.registeredCompactFiniteHeightZetaContract])
  (proofUses := [
    SparkInterval.Execution.SignedResultCertificate.certifyRegisteredCompactVerifierOutcome])
  (statement := /--
    This theorem removes the legacy `ExecutionRefines` argument, but remains
    conditional on a registered zeta-verifier constructor and an ordinary
    proof that its fixed execution semantics establishes the finite-height
    claim.  The Hardy-Z and analytic zero-count obligations below remain open.
  -/)] SparkInterval.Execution.SignedResultCertificate.certifyRegisteredCompactFiniteHeightZeta

attribute [blueprint "thm:critical-line-bridge-preserves-zero-count"
  (title := "Critical-line parametrization preserves distinct-zero count")
  (uses := [SparkInterval.Zeta.CriticalLineZeroBridge])]
  SparkInterval.Zeta.CriticalLineZeroBridge.criticalLineZerosIn_ncard_eq_zerosOn_ncard

attribute [blueprint "thm:finite-height-zeta-verifier-sound"
  (title := "Brackets plus a total count prove the finite-height zeta result")
  (proofUses := [
    SparkInterval.Zeta.ZeroCertificate.complete_of_count_upperBound,
    SparkInterval.Zeta.CriticalLineZeroBridge.criticalLineZerosIn_ncard_eq_zerosOn_ncard,
    SparkInterval.Zeta.all_zeros_to_height_on_criticalLine])]
  SparkInterval.Zeta.ZetaVerifierEvidence.all_zeros_on_criticalLine

attribute [blueprint "thm:chunked-finite-height-zeta-verifier-sound"
  (title := "Chunked brackets plus a total count prove the zeta result")
  (proofUses := [
    SparkInterval.Zeta.ChunkCertificate.complete_of_count_upperBound,
    SparkInterval.Zeta.CriticalLineZeroBridge.criticalLineZerosIn_ncard_eq_zerosOn_ncard,
    SparkInterval.Zeta.all_zeros_to_height_on_criticalLine])]
  SparkInterval.Zeta.ChunkedZetaVerifierEvidence.all_zeros_on_criticalLine

attribute [blueprint "gap:hardy-z-riemann-siegel"
  (title := "GAP: checked Hardy-Z / Riemann-Siegel interval evaluator")
  (hasProof := false)
  (notReady := true)
  (uses := [SparkInterval.Zeta.CriticalLineZeroBridge,
    SparkInterval.PTX.NvidiaPTX90.directedF64DivisionRequirement])
  (statement := /--
    A production instance still needs certified theta, logarithm,
    trigonometric/range-reduction, square-root, Riemann-Siegel remainder, and
    adaptive interval evaluation theorems connected to the emitted program.
  -/)] SparkInterval.Blueprint.hardyZRiemannSiegelGap

attribute [blueprint "gap:turing-zero-count"
  (title := "GAP: checked analytic multiplicity upper bound")
  (hasProof := false)
  (notReady := true)
  (uses := [SparkInterval.Zeta.ZetaMultiplicityCountUpperBound,
    SparkInterval.Zeta.ZetaMultiplicityCountCertificate.check_sound])
  (statement := /--
    The distinct-count-to-multiplicity bridge is proved.  The remaining
    analytic obligation is a formal Turing, Riemann--von Mangoldt, or
    argument-principle checker that constructs
    `ZetaMultiplicityCountUpperBound` from checked evidence with the required
    contour-boundary and height conventions.  For a conventional
    positive-ordinate proof, the separate zeta conjugation/multiplicity
    symmetry and no-real-axis-zero premises must also be discharged.  The
    small arithmetic certificate does not construct any of these premises.
  -/)] SparkInterval.Blueprint.turingCountGap

attribute [blueprint "gap:streaming-zeta-certificate-checker"
  (title := "GAP: byte-level resource-bounded streaming integration")
  (hasProof := false)
  (notReady := true)
  (uses := [SparkInterval.Zeta.RationalBracketFamily.check,
    SparkInterval.Execution.SignedZetaEndpointPayload.payloadCheck,
    SparkInterval.Zeta.runEndpointChunk_append,
    SparkInterval.Zeta.checkEndpointStream_isValid,
    SparkInterval.Zeta.runEndpointChunkStream_append,
    SparkInterval.Zeta.verifyEndpointChunkStream,
    SparkInterval.Zeta.ChunkCertificate])
  (statement := /--
    The endpoint and chunk transitions are resumable and the chunk path now
    composes exact local checks into the final finite-height theorem while
    retaining only the preceding logical boundary.  The remaining integration
    is a byte parser, rolling
    digest, explicit allocation/work limits, file or network I/O loop, and a
    theorem relating that runtime to the logical transition and chunk
    composition.
  -/)] SparkInterval.Blueprint.streamingZetaCheckerGap

/-! ## Platt zero head through 20,000 exact registered slice -/

attribute [blueprint "def:platt-head-q128-table-commitment"
  (title := "The literal Q128 table computes its canonical row commitment")
  (uses := [SparkInterval.Certificate.SHA256.digestString])]
  SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics.Q128CellTable.commitment

attribute [blueprint "thm:platt-head-q128-checked-source"
  (title := "Checked Q128 head evidence proves multiplicity-preserving enumeration")
  (uses := [
    SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics.Q128CellTable.commitment,
    SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics.sourceClaim_of_checked_head_evidence])
  (statement := /--
    One literal 22,491-row table whose computed commitment equals the reviewed
    included-row digest, together with the Hardy-Z endpoint and exact analytic
    slot-count evidence, yields its exact source claim. No zero-simplicity
    assumption occurs.
  -/)] SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics.q128SourceClaim_of_checked_evidence

attribute [blueprint "thm:platt-head-2e4-registered-capstone"
  (title := "A successful registered Platt-head CPU run exposes the Q128 table")
  (uses := [
    SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics.q128SourceClaim_of_checked_evidence])
  (statement := /--
    The closed invocation pins height 20,000, multiplicity count 22,491,
    FLINT 3.6.0 at 96 bits, the 22,492-row sentinel-inclusive digest, the
    distinct 22,491-row included-table commitment, and CPU/SEV-SNP deployment.
    Success is evidence for the checked-in named literal table itself and
    returns its computed included-row commitment and source claim. It cannot
    select an arbitrary table with a matching digest.
  -/)] SparkInterval.Execution.RegisteredInvocation.plattHead2e4ProductionV1_sourceClaim

attribute [blueprint "thm:platt-head-2e4-signed-capstone"
  (title := "One accepted Platt-head CPU receipt exposes the committed source result")
  (uses := [
    SparkInterval.Execution.RegisteredInvocation.plattHead2e4ProductionV1_sourceClaim])]
  SparkInterval.Execution.SignedResultCertificate.certifyPlattHead2e4

attribute [blueprint "gap:platt-head-2e4-source-evidence"
  (title := "GAP: materialize the literal Q128 head and analytic realization")
  (hasProof := false)
  (notReady := true)
  (uses := [
    SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics.q128SourceClaim_of_checked_evidence,
    SparkInterval.Execution.RegisteredInvocation.plattHead2e4ProductionV1_sourceClaim])
  (statement := /--
    The external full replay has been exercised and its exact literal included
    table is generated into Lean, but no `CheckedQ128HeadEvidence` or accepted
    receipt is admitted. The FLINT
    endpoint enclosures still need a reviewed Hardy-Z/Mathlib realization and
    the FLINT count must construct the exact multiplicity-slot equality. A
    downstream bridge must also identify this named literal table with the
    consumer's committed table. The success relation itself names the table,
    so SHA collision resistance is not used as a kernel table-identity proof.
    The semantic row stays disabled and
    all binding fields stay null.
  -/)] SparkInterval.Blueprint.plattHead2e4SourceEvidenceGap

/-! ## Platt--Trudgian finite-RH exact registered slice -/

attribute [blueprint "def:pt21-compact-block-artifact"
  (title := "Compact PT21 artifact with rational brackets and conservative Turing cells")
  (uses := [
    SparkInterval.Zeta.TouchingRationalBracketFamily,
    SparkInterval.Zeta.PairedTuringClosureCertificate])]
  SparkInterval.Zeta.PT21ArtifactBinding.BlockArtifact

attribute [blueprint "def:pt21-compact-block-check"
  (title := "Fail-closed PT21 geometry, stream, and Turing wire checker")
  (uses := [
    SparkInterval.Zeta.TouchingRationalBracketFamily.check,
    SparkInterval.Zeta.PairedTuringClosureCertificate.check])]
  SparkInterval.Zeta.PT21ArtifactBinding.BlockArtifact.check

attribute [blueprint "thm:pt21-compact-source-coordinates"
  (title := "Checked PT21 offsets are exactly the main and two flank ranges")
  (proofUses := [
    SparkInterval.Zeta.PT21ArtifactBinding.BlockArtifact.geometry_of_check])]
  SparkInterval.Zeta.PT21ArtifactBinding.BlockArtifact.source_range_coordinates

attribute [blueprint "thm:pt21-compact-touching-certificate"
  (title := "Realized PT21 endpoint records yield distinct touching-bracket roots")
  (uses := [
    SparkInterval.Zeta.PT21ArtifactBinding.BlockArtifact.EndpointRealization])
  (proofUses := [
    SparkInterval.Zeta.TouchingRationalBracketFamily.exists_touchingZeroCertificate])]
  SparkInterval.Zeta.PT21ArtifactBinding.BlockArtifact.touchingCertificateFromRealization

attribute [blueprint "thm:pt21-compact-exact-endpoint-counts"
  (title := "Paired PT21 streams and explicit analytic premises fix both counts")
  (uses := [
    SparkInterval.Zeta.TuringWindowInput.Realization,
    SparkInterval.Zeta.PairedTuringClosureCertificate.MainMultiplicitySlotLowerBound])
  (proofUses := [
    SparkInterval.Zeta.PairedTuringClosureCertificate.exact_endpoint_counts])]
  SparkInterval.Zeta.PT21ArtifactBinding.BlockArtifact.exactEndpointCounts

attribute [blueprint "thm:pt21-cross-precision-outward-hull"
  (title := "PT21 cross-precision replay uses a sound outward hull, not a nesting assumption")
  (uses := [
    SparkInterval.Zeta.PT21PrecisionHull.first_contains_hull,
    SparkInterval.Zeta.PT21PrecisionHull.second_contains_hull,
    SparkInterval.Zeta.PT21PrecisionHull.replay_contains_hull_of_subset_second,
    SparkInterval.Zeta.PT21PrecisionHull.positive_of_hull_contains,
    SparkInterval.Zeta.PT21PrecisionHull.negative_of_hull_contains])
  (statement := /--
    Rigorous Arb evaluations at 128 and 192 bits need not be nested. The
    qualification resolver therefore retains both endpoint enclosures and
    widens to their endpoint-wise outward hull. Lean proves, without a
    cross-precision nesting premise, that any value enclosed by either input
    remains enclosed by the hull and that a strict sign recheck on the widened
    hull applies to the source value. Native Arb-to-ordered-value realization
    remains outside this interval-algebra theorem.
  -/)] SparkInterval.Zeta.PT21PrecisionHull.contains_hull_of_both

attribute [blueprint "thm:pt21-multiwindow-transform-geometry"
  (title := "One PT21 transform grid exactly contains five neighbouring required views")
  (uses := [
    SparkInterval.Zeta.PT21PairedWindowGeometry.relative_sample_reindex,
    SparkInterval.Zeta.PT21PairedWindowGeometry.five_window_required_index_fits,
    SparkInterval.Zeta.PT21PairedWindowGeometry.campaign_five_window_accounting,
    SparkInterval.Zeta.PT21PairedWindowGeometry.campaign_five_window_unique_partition,
    SparkInterval.Zeta.PT21PairedWindowGeometry.campaign_five_window_center_roster])
  (statement := /--
    Adjacent PT21 centres differ by exactly `24576` samples of width `21/512`.
    A transform centred at one logical block therefore contains, by exact
    integer reindexing, the complete `25741`-sample required views for that
    block and its two neighbours on either side. The campaign consequently
    has a gap-free, non-overlapping roster of complete five-window groups
    centred at `5*k+2`, plus the final three-window group centred at
    `5*fiveWindowGroupCount+1`. This is an optimization theorem only: each
    shifted native disk must still pass the full invalid/ambiguity scan,
    independent event replay, and stationary-resolution comparison. The
    theorem neither supplies a stride-capable source accumulator nor derives
    a CUDA-to-Hardy-Z realization from the index arithmetic.
  -/)] SparkInterval.Zeta.PT21PairedWindowGeometry.five_window_required_view_fits

attribute [blueprint "thm:pt21-finite-rh-source-specialization"
  (title := "Chunked zeta evidence implies the exact PT21 finite-RH claim")
  (uses := [SparkInterval.Zeta.ChunkedZetaVerifierEvidence.all_zeros_on_criticalLine])
  (statement := /--
    At the literal endpoint `3000175332800`, the stronger symmetric closed-
    rectangle verifier theorem specializes to the positive-height open-strip
    proposition used by the ternary-Goldbach source atom. The theorem is
    ordinary Lean and preserves every analytic premise inside `SourceEvidence`.
  -/)] SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics.sourceClaim_of_evidence

attribute [blueprint "thm:pt21-finite-rh-registered-capstone"
  (title := "A successful registered PT21 CPU run returns the source claim")
  (uses := [
    SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics.sourceClaim_of_evidence])]
  SparkInterval.Execution.RegisteredInvocation.plattTrudgianFiniteRHProductionV1_sourceClaim

attribute [blueprint "thm:pt21-finite-rh-signed-capstone"
  (title := "One accepted PT21 CPU receipt exposes the exact source claim")
  (uses := [
    SparkInterval.Execution.RegisteredInvocation.plattTrudgianFiniteRHProductionV1_sourceClaim])
  (statement := /--
    This conditional theorem checks the closed campaign, height, multiplicity
    count, FLINT identity and CPU/SEV-SNP deployment before adding exactly the
    disclosed accepted-run axiom.
  -/)] SparkInterval.Execution.SignedResultCertificate.certifyPlattTrudgianFiniteRH

attribute [blueprint "gap:pt21-finite-rh-source-evidence"
  (title := "GAP: PT21 endpoint/Hardy-Z/count realization and source-scale run")
  (hasProof := false)
  (notReady := true)
  (uses := [
    SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics.sourceClaim_of_evidence,
    SparkInterval.Execution.RegisteredInvocation.plattTrudgianFiniteRHProductionV1_sourceClaim])
  (statement := /--
    The v2 compact block decoder, the source's exact main/left/right lattice
    geometry, dyadic stationary brackets, separate multiplicity-two
    conservative Turing cells, and the two distinct 21-unit `turing_min` and
    `turing_max` flank calls are now kernel checked.  An independent
    exact-rational Python reference finalizer reconstructs direct events,
    Turing quotients/roundings, gap-free shard chains, Merkle roots, and the
    exact source-height count from canonical traces.  No Lean term yet proves that the emitted
    endpoint intervals enclose the actual Hardy-Z evaluator, realizes the
    main stream as a multiplicity-count lower bound, or proves the analytic
    Turing inputs and inequalities.  The measured production-scale fused H100
    producer/native finalizer, prefix evidence, terminal materializer, and
    successful attested receipt are also absent. The Azure semantic row
    therefore remains disabled.
  -/)] SparkInterval.Blueprint.pt21FiniteRHSourceEvidenceGap

/-! ## Helfgott--Platt finite Goldbach exact registered slice -/

attribute [blueprint "thm:finite-goldbach-tail-progression"
  (title := "The bounded optimized tail kernels enumerate every target")
  (uses := [
    SparkInterval.TernaryGoldbach.GoldbachTailProgression.cudaTailStart_eq_some_of_bounded_candidate,
    SparkInterval.TernaryGoldbach.GoldbachTailProgression.bitmaskOne_eq_zero_iff_even,
    SparkInterval.TernaryGoldbach.GoldbachTailProgression.boundedTail_complete,
    SparkInterval.TernaryGoldbach.GoldbachTailProgression.boundedWarpTail_complete,
    SparkInterval.TernaryGoldbach.GoldbachWarpLaunchIndexing.sourceLaunchBlocks_eq_launchBlocks,
    SparkInterval.TernaryGoldbach.GoldbachWarpLaunchIndexing.bitmask31_eq_mod32,
    SparkInterval.TernaryGoldbach.GoldbachWarpLaunchIndexing.existsUnique_sourceOwnerCoordinate,
    SparkInterval.TernaryGoldbach.GoldbachWarpLaunchIndexing.productionLaunch_widthSafe,
    SparkInterval.TernaryGoldbach.GoldbachWheelFilter.rejected_tail_event_already_cleared])
  (statement := /--
    For an odd retained prime and an odd divisible candidate between the
    inclusive segment endpoints and above `p²`, Lean models the literal CUDA
    ceiling, parity adjustment, square replacement, and upper early-return
    guards. Lean also proves the source `(first & 1) == 0` test is precisely
    the model's evenness branch. The accepted start is the least relevant odd
    multiple; both the
    sequential and 32-lane warp progressions reach the target before their
    subtraction guards can stop; and the exact packed-bit index is live.
    The launch theorem models the literal 256-thread grid and proves every
    retained `(primeIndex,lane)` has one unique active CUDA block/thread
    owner, including the rounded final block. Its host grid arithmetic and
    every launched global index fit in 32 bits, hence also the source's
    64-bit temporaries. The start and 64-prime warp stride are below `2^64`.
    The wheel theorem separately proves every deliberately filtered cofactor
    was already cleared by a word-owner prime.

    Lean also proves source `threadIdx.x & 31` equals arithmetic remainder.
    Remaining native obligations are compiler/register/instruction
    realization, authenticated prime-buffer identity, physical bit
    addressing, and atomic linearizability.
  -/)] SparkInterval.TernaryGoldbach.GoldbachTailProgression.boundedWarpTail_complete

attribute [blueprint "thm:finite-goldbach-complete-sieve-prime"
  (title := "A survivor of the complete prime roster is prime")
  (statement := /--
    If the source roster contains every prime whose square is at most a
    candidate, then a candidate at least two that is not cleared by the
    source's exact square-guarded divisibility predicate is prime. This
    isolates prime-table completeness from CUDA realization.
  -/)] SparkInterval.TernaryGoldbach.GoldbachOptimizedSourceRefinement.prime_of_completeRoster_not_cleared

attribute [blueprint "thm:finite-goldbach-packed-campaign-sound"
  (title := "Complete packed output rows imply historical binary Goldbach")
  (uses := [
    SparkInterval.TernaryGoldbach.GoldbachOptimizedSourceRefinement.prime_of_completeRoster_not_cleared])
  (statement := /--
    One literal packed output row at every formulaic 64-even word index, with
    the two-load shifted OR equation and exact live-tail mask, constructs the
    existing gap-free campaign evidence and hence the historical binary
    Goldbach claim. No sample or maximum-index shortcut is admitted.
  -/)] SparkInterval.TernaryGoldbach.GoldbachOptimizedSourceRefinement.historicalBinaryClaim

attribute [blueprint "thm:finite-goldbach-packed-zero-reduction"
  (title := "A zero packed missing count supplies every row mask equation")
  (uses := [
    SparkInterval.TernaryGoldbach.GoldbachOptimizedSourceRefinement.missingWordCount_lt_uint32])
  (statement := /--
    The fixed 200,000,000-even segment gives at most 3,125,000 packed words,
    so 64 missing bits per word cannot wrap `uint32_t`. Assuming physical
    popcount zero reflection, a zero masked missing-bit sum proves the literal
    mask equation for every retained row.
  -/)] SparkInterval.TernaryGoldbach.GoldbachOptimizedSourceRefinement.maskAccepted_of_missingWordCount_eq_zero

attribute [blueprint "thm:finite-goldbach-ladder-check-sound"
  (title := "The finite ladder check implies parity-sensitive source coverage")
  (statement := /--
    The first-rung, primality, adjacent-overlap and last-rung checks imply the
    universal union-of-intervals property, including the exact `+2` odd-target
    convention.
  -/)] SparkInterval.TernaryGoldbach.GoldbachSourceSemantics.PrimeLadder.valid_of_check

attribute [blueprint "thm:finite-goldbach-checked-source"
  (title := "Binary Goldbach plus a checked prime ladder proves the source claim")
  (uses := [
    SparkInterval.TernaryGoldbach.GoldbachSourceSemantics.PrimeLadder.valid_of_check])
  (statement := /--
    At the exact source endpoint, a binary representation for each even number
    through `4·10^18` and the checked finite prime ladder yield a three-prime
    representation of every odd target in the cited finite range.
  -/)] SparkInterval.TernaryGoldbach.GoldbachSourceSemantics.sourceClaim_of_checked_evidence

attribute [blueprint "thm:finite-goldbach-registered-capstone"
  (title := "A successful registered Goldbach finalizer returns the source claim")
  (uses := [
    SparkInterval.TernaryGoldbach.GoldbachSourceSemantics.sourceClaim_of_checked_evidence])]
  SparkInterval.Execution.RegisteredInvocation.helfgottPlattGoldbachProductionV1_sourceClaim

attribute [blueprint "thm:finite-goldbach-signed-capstone"
  (title := "One accepted CPU finalizer receipt exposes finite Goldbach")
  (uses := [
    SparkInterval.Execution.RegisteredInvocation.helfgottPlattGoldbachProductionV1_sourceClaim])
  (statement := /--
    The closed identity pins the binary-H100 and CPU-ladder campaign/source-
    artifact formats and the exact source bounds. The conditional theorem adds
    exactly the disclosed accepted-run axiom.
  -/)] SparkInterval.Execution.SignedResultCertificate.certifyHelfgottPlattGoldbach

attribute [blueprint "gap:finite-goldbach-source-evidence"
  (title := "GAP: full branch evidence and transitive confidential provenance")
  (hasProof := false)
  (notReady := true)
  (uses := [
    SparkInterval.TernaryGoldbach.GoldbachSourceSemantics.sourceClaim_of_checked_evidence,
    SparkInterval.Execution.RegisteredInvocation.helfgottPlattGoldbachProductionV1_sourceClaim])
  (statement := /--
    The exact optimized source now has a 65,536-leaf plan/run/aggregate/checker
    path and a domain-separated unregistered binary-plus-ladder combiner, but
    neither that binary campaign nor the 492,700-range ladder has completed.
    The registered v1 Azure terminal remains pinned to the base source, and no
    materializer constructs `CheckedSourceEvidence`. Moreover,
    the current `Runs` result does not expose a Lean-checkable transitive chain
    proving that the final CPU receipt verified the pinned H100 branch receipts
    and CPU-ladder receipt/artifact hashes. That provenance premise, branch
    runs, finalizer and successful attested receipt remain absent, so the Azure
    semantic binding stays disabled and null.
  -/)] SparkInterval.Blueprint.finiteGoldbachSourceEvidenceGap

/-! ## CH25 Lemma A.7 rational boundary arithmetic and FLINT edge -/

attribute [blueprint "thm:a7-rational-box-norm-bound"
  (title := "Exact rational component guards imply the A.7 norm bound")
  (statement := /--
    Rational endpoint and absolute-component bounds, together with one exact
    squared inequality, prove `‖z‖ ≤ 349/250` in ordinary Lean. No FLINT or
    trusted-execution premise occurs in this arithmetic step.
  -/)] SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics.RationalComplexBox.norm_le_of_contains_guard

attribute [blueprint "thm:a7-boundary-evidence-source-claim"
  (title := "A complete rational leaf cover proves the A.7 source claim")
  (uses := [
    SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics.RationalComplexBox.norm_le_of_contains_guard])
  (statement := /--
    Four-edge coverage, exact output-box containment and rational guards imply
    the literal Mathlib-zeta frontier estimate. `BoundaryEvidence.realizes`
    remains the explicit analytic refinement from FLINT/Arb boxes.
  -/)] SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics.sourceClaim_of_boundary_evidence

attribute [blueprint "thm:a7-registered-source-capstone"
  (title := "A successful registered A.7 replay returns the source claim")
  (uses := [
    SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics.sourceClaim_of_boundary_evidence])]
  SparkInterval.Execution.RegisteredInvocation.ch25A7BoundaryProductionV1_sourceClaim

attribute [blueprint "thm:a7-signed-source-capstone"
  (title := "One accepted A.7 CPU receipt exposes the exact source claim")
  (uses := [
    SparkInterval.Execution.RegisteredInvocation.ch25A7BoundaryProductionV1_sourceClaim])
  (statement := /--
    This end-to-end conditional theorem adds exactly the disclosed accepted-
    run axiom. The rectangle, finite cover and rational norm arithmetic remain
    kernel checked.
  -/)] SparkInterval.Execution.SignedResultCertificate.certifyCH25A7Boundary

attribute [blueprint "gap:a7-flint-mathlib-realization"
  (title := "GAP: FLINT/Arb boxes realize Mathlib's zeta expression")
  (hasProof := false)
  (notReady := true)
  (uses := [
    SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics.sourceClaim_of_boundary_evidence,
    SparkInterval.Execution.RegisteredInvocation.ch25A7BoundaryProductionV1_sourceClaim])
  (statement := /--
    The retained 16,191-leaf replay is externally complete, and a closed
    measured terminal materializer/writer emits the exact registered result
    after a pinned replay. However, no Lean term yet constructs
    `BoundaryEvidence.realizes`, no reviewed production deployment pin is
    installed, and the source-admitted trusted-compute registry remains empty.
    The Azure semantic row is therefore fully staged but disabled.
  -/)] SparkInterval.Blueprint.a7FlintMathlibRealizationGap

/-! ## Hurst affine arithmetic certificate and explicit physical edge -/

attribute [blueprint "thm:hurst-affine-arithmetic-checker-sound"
  (title := "Checked Hurst blocks have exact prefix and guard semantics")
  (statement := /--
    The Boolean checker proves contiguous half-open geometry, exact additive
    four-coordinate prefix transitions, guard membership, and the final state.
    It does not prove that a physical producer emitted the encoded rows.
  -/)] SparkInterval.TernaryGoldbach.HurstAffineCertificate.Certificate.checker_sound

attribute [blueprint "thm:hurst-affine-physical-composition"
  (title := "Checked arithmetic plus explicit row evidence proves row safety")
  (uses := [
    SparkInterval.TernaryGoldbach.HurstAffineCertificate.Certificate.checker_sound])
  (statement := /--
    Composition is an ordinary Lean theorem, but its
    `ExternalBlockRealization` argument remains an explicit premise.
  -/)] SparkInterval.TernaryGoldbach.HurstAffineCertificate.checked_physical_run_sound

attribute [blueprint "thm:hurst-affine-source-scale-composition"
  (title := "The older global-predicate Hurst interface composes")
  (uses := [
    SparkInterval.TernaryGoldbach.HurstAffineCertificate.checked_physical_run_sound])]
  SparkInterval.TernaryGoldbach.HurstAffineCertificate.checked_source_scale_sound

attribute [blueprint "thm:hurst-local-replay-source-composition"
  (title := "Primitive Hurst rows reconstruct the exact global source prefixes")
  (uses := [
    SparkInterval.TernaryGoldbach.HurstAffineCertificate.Certificate.checker_sound,
    SparkInterval.TernaryGoldbach.HurstSourceSemantics.prefixRealization_add_sourceRowDelta])
  (statement := /--
    Production evidence supplies a zero root, literal full-range geometry,
    primitive Möbius/squarefree/directed-Q96 row deltas, and local integer
    guard decisions.  Ordinary Lean transports the row recurrence along the
    one checked chain and derives `PrefixRealization` at every actual source
    row.  It never asks every state in a broad incoming guard to be the unique
    global prefix.
  -/)] SparkInterval.TernaryGoldbach.HurstSourceSemantics.checked_full_source_claims_of_local

attribute [blueprint "thm:hurst-gpu-terminal-row-realization"
  (title := "A complete fused Möbius roster realizes one terminal Hurst row")
  (uses := [
    SparkInterval.TernaryGoldbach.MobiusFusedFinalization.finalize_foldSupport_eq_moebius,
    SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness.CompletePrimeRoster.sourceRosterValid,
    SparkInterval.TernaryGoldbach.MobiusGuardedMachine.output_runResidueSeeded_eq_moebius,
    SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement.output_decodeWord_packedRunResidueSeeded_eq_moebius,
    SparkInterval.TernaryGoldbach.HurstPackedPrefixInput.packedPrefixInputs_valid_of_totalPoisonCount_zero,
    SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction.inputScanAndCandidateReduction_sound,
    SparkInterval.TernaryGoldbach.HurstSourceSemantics.prefixRealization_add_sourceRowDelta])
  (statement := /--
    Above the frozen little-Mertens split at `10^12`, the terminal GPU row
    contains exactly Mathlib's Möbius value, its zero/nonzero squarefree
    indicator, and two zero directed-Q96 increments.  A single duplicate-free
    prime roster complete through `10^8` plus the native zero-poison result
    supplies the row invariant uniformly through `10^16`; no per-row semantic
    assertion is trusted. The packed desired-word arithmetic, exact
    divisor-event/block-thread enumeration, direct `{μ, μ ≠ 0}` input rows,
    prefix sums, width bounds, and deterministic reductions are proved.
    Atomic-CAS linearizability, compiled register/loop and CUB realization,
    device execution, and receipt authentication remain the
    machine-refinement obligations.
  -/)] SparkInterval.TernaryGoldbach.HurstGpuRowRealization.packedTerminalDelta_productionPrimeRoster_sourceRowDelta

attribute [blueprint "thm:hurst-v2-real-source-capstone"
  (title := "Checked Hurst V2 evidence proves all four real source atoms")
  (uses := [
    SparkInterval.TernaryGoldbach.HurstSourceSemantics.checked_full_source_claims_of_local])
  (statement := /--
    Exact prefix realization and V2 fallback guards imply the Hurst bound,
    both little-Mertens bounds, and both strict-real squarefree inequalities.
    The proof includes the directed `6/π²` enclosure and literal finite-sum
    normal forms used by the downstream definitions.  It has no project axiom
    or `native_decide`; physical full-range evidence remains its premise.
  -/)] SparkInterval.TernaryGoldbach.HurstSourceSemantics.checked_real_source_claims_of_local

attribute [blueprint "thm:hurst-v2-registered-real-source-capstone"
  (title := "A successful registered Hurst V2 run returns the real capstone")
  (uses := [
    SparkInterval.TernaryGoldbach.HurstSourceSemantics.checked_real_source_claims_of_local])]
  SparkInterval.Execution.RegisteredInvocation.hurstSharedFourResidualProductionV2_realClaims

attribute [blueprint "thm:hurst-v2-signed-real-source-capstone"
  (title := "One accepted signed V2 receipt exposes the real Hurst claims")
  (uses := [
    SparkInterval.Execution.RegisteredInvocation.hurstSharedFourResidualProductionV2_realClaims])
  (statement := /--
    This is the end-to-end signed composition.  Its only project-specific
    logical boundary is `accepted_run_certificate_sound`; all finite and real
    arithmetic after that boundary is kernel checked.
  -/)] SparkInterval.Execution.SignedResultCertificate.certifyHurstSharedFourResidual

attribute [blueprint "gap:hurst-physical-source-evidence"
  (title := "GAP: retained Hurst rows and literal full-source coverage")
  (hasProof := false)
  (notReady := true)
  (uses := [
    SparkInterval.TernaryGoldbach.HurstAffineCertificate.Certificate.checker_sound,
    SparkInterval.TernaryGoldbach.HurstSourceSemantics.checked_full_source_claims_of_local,
    SparkInterval.Execution.RegisteredInvocation.hurstSharedFourResidualProductionV2_realClaims])
  (statement := /--
    No retained signed receipt supplies `LocalSourceScaleEvidence`.  A
    completed V2 campaign must bind retained row commitments to every
    primitive Möbius/Q96 block recurrence, establish the zero root and literal
    interval `[1, 10^16 + 1)`, and prove the local integer guard decision for
    every replayed row before the registered wrapper applies.  That last
    physical premise is intentionally broad over guard-admissible incoming
    states (the production two-pass guards are singletons), but it contains no
    global-prefix assertion.  The older global `SourceScaleEvidence` API is
    not on this registered path.
  -/)] SparkInterval.Blueprint.hurstPhysicalSourceEvidenceGap

/-! ## CH25 Lemma 9.2 psi endpoint arithmetic and physical edge -/

attribute [blueprint "thm:psi-q64-upper-endpoint-safe"
  (title := "The exact Q64 upper guard implies the CH25 real endpoint bound")
  (uses := [
    SparkInterval.TernaryGoldbach.PsiSourceSemantics.UpperEndpointSafe])
  (statement := /--
    Integer cross-multiplication at scale `2^64` yields the exact rational
    upper bound `19764819 / 25000000`; no floating-point evaluation or
    project axiom occurs in this reduction.
  -/)] SparkInterval.TernaryGoldbach.PsiSourceSemantics.upperEndpointSafe_real

attribute [blueprint "thm:psi-source-evidence-implies-source-claim"
  (title := "Gap-free Q64 psi evidence proves the paper-shaped source claim")
  (uses := [
    SparkInterval.TernaryGoldbach.PsiSourceSemantics.SourceScaleEvidence,
    SparkInterval.TernaryGoldbach.PsiSourceSemantics.SourceClaim])
  (statement := /--
    Exact prefix realization against Mathlib's `Chebyshev.psi`, both endpoint
    guards for every integer slab through `10^13`, and the strict in-slab
    monotonicity argument imply both real inequalities for every source `x`.
  -/)] SparkInterval.TernaryGoldbach.PsiSourceSemantics.sourceClaim_of_evidence

attribute [blueprint "thm:psi-prime-power-fold-realizes-mathlib-psi"
  (title := "Directed prime-power folds enclose Mathlib's Chebyshev psi")
  (uses := [
    SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate.primePowerLowerQ64_eq_canonicalLowerQ64,
    SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate.primePowerUpperQ64_eq_canonicalUpperQ64,
    Chebyshev.psi_eq_sum_mul_log_prime])
  (statement := /--
    One directed Q64 logarithm interval is added for each prime-power event.
    Mathlib's `p.log n` counts exactly those exponents, so the event fold is
    the canonical prime sum and encloses `Chebyshev.psi n`.  The proof uses no
    project axiom or native evaluator.
  -/)] SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate.canonicalState_prefixRealization

attribute [blueprint "thm:psi-canonical-certificate-implies-source-claim"
  (title := "Prime-log semantics and integer guards prove CH25 Lemma 9.2")
  (uses := [
    SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate.canonicalState_prefixRealization,
    SparkInterval.TernaryGoldbach.PsiSourceSemantics.sourceClaim_of_evidence])]
  SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate.sourceClaim_of_canonical_evidence

attribute [blueprint "thm:psi-event-gap-certificate-implies-source-claim"
  (title := "Prime-power event-boundary guards control every source slab")
  (uses := [
    SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate.canonicalState_prefixRealization,
    SparkInterval.TernaryGoldbach.PsiSourceSemantics.lowerBarrier_strict,
    SparkInterval.TernaryGoldbach.PsiSourceSemantics.upperEndpointSafe_real])
  (statement := /--
    The worker checks the upper guard just after a prime-power jump and the
    lower guard just before the next jump.  Exact finite gap coverage and
    constancy of the canonical state let ordinary Lean propagate those two
    checks to every real point in the gap, including the strict terminal edge.
  -/)] SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate.sourceClaim_of_gap_evidence

attribute [blueprint "thm:psi-registered-source-capstone"
  (title := "A successful registered CH25 psi run returns the source claim")
  (uses := [
    SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate.sourceClaim_of_gap_evidence])]
  SparkInterval.Execution.RegisteredInvocation.ch25PsiLemma92ProductionV1_sourceClaim

attribute [blueprint "thm:psi-signed-source-capstone"
  (title := "One accepted CH25 psi receipt exposes the exact source claim")
  (uses := [
    SparkInterval.Execution.RegisteredInvocation.ch25PsiLemma92ProductionV1_sourceClaim])
  (statement := /--
    The signed wrapper uses only the disclosed accepted-run axiom; all Q64,
    integer-slab, square-root, and Chebyshev-psi reasoning is ordinary Lean.
  -/)] SparkInterval.Execution.SignedResultCertificate.certifyCH25PsiLemma92

attribute [blueprint "gap:psi-physical-source-evidence"
  (title := "GAP: retained CH25 psi source rows and two-pass coverage")
  (hasProof := false)
  (notReady := true)
  (uses := [
    SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate.sourceClaim_of_gap_evidence,
    SparkInterval.Execution.RegisteredInvocation.ch25PsiLemma92ProductionV1_sourceClaim])
  (statement := /--
    No retained Azure receipt currently supplies
    `GapSourceScaleEvidence`.  The source-scale two-pass producer must
    bind every prime-power update to its canonical prime/log table, establish
    directed CRlibm-to-Q64 log realization, check the integer endpoint rows
    through `10^13`, independently replay the leaf commitments, and return
    the registered Boolean success.
  -/)] SparkInterval.Blueprint.psiPhysicalSourceEvidenceGap

/-! ## Routine factor-eight Dirichlet postprocessing -/

attribute [blueprint "thm:dirichlet-factor8-coordinate-map"
  (title := "Factor-eight row indices denote the exact 5/64 lattice taps")
  (statement := /--
    The source lattice has exact rational step `5/64`, the fine lattice has
    step `5/512`, and the checked source index
    `floor(fineIndex/8) - 19 + slot` has displacement
    `(phase/8 - (-19 + slot)) * 5/64` from the fine target.  This is an
    algebraic coordinate identity, not an analytic interpolation estimate.
  -/)] SparkInterval.Dirichlet.Factor8Postprocess.fineCoordinate_sub_sourceCoordinate_expectedSourceIndex

attribute [blueprint "thm:dirichlet-factor8-phase-major-map"
  (title := "Factor-eight coefficient indices decode to phase and tap")
  (uses := [
    SparkInterval.Dirichlet.Factor8Postprocess.expectedCoefficientIndex_mod_tapCount,
    SparkInterval.Dirichlet.Factor8Postprocess.expectedCoefficientIndex_lt_coefficientCount])
  (statement := /--
    For the seven nonzero phases and forty slots, the exact index
    `(phase - 1) * 40 + slot` lies in the 280-entry table and division and
    remainder by 40 recover the original phase and slot.
  -/)] SparkInterval.Dirichlet.Factor8Postprocess.expectedCoefficientIndex_div_tapCount

attribute [blueprint "def:dirichlet-factor8-rational-check"
  (title := "Exact-rational routine factor-eight target checker")
  (uses := [
    SparkInterval.Dirichlet.Factor8Postprocess.fineCoordinate_sub_sourceCoordinate_expectedSourceIndex,
    SparkInterval.Dirichlet.Factor8Postprocess.expectedCoefficientIndex_div_tapCount])
  (statement := /--
    Rejects phase zero, interpolation allowances below `86/10^9`, row lists
    other than forty entries, wrong source or phase-major coefficient
    indices, malformed or zero-crossing coefficient intervals, incorrect
    four-corner products, incorrect exact rational folds, and incorrect
    symmetric widening.
  -/)] SparkInterval.Dirichlet.Factor8Postprocess.Certificate.check

attribute [blueprint "thm:dirichlet-factor8-source-containment"
  (title := "Checked factor-eight output contains the named fine-grid value")
  (uses := [
    SparkInterval.Dirichlet.Factor8Postprocess.Certificate.check,
    SparkInterval.Dirichlet.Factor8Postprocess.fineCoordinate_sub_sourceCoordinate_expectedSourceIndex])
  (proofUses := [
    SparkInterval.Dirichlet.Factor8Postprocess.Certificate.output_contains])
  (statement := /--
    Conditional on the explicit source-shaped realization—each interval
    contains the completed function at its checked `5/64` coordinate, each
    coefficient interval contains the separately named table value, and the
    true `5/512` target differs from the forty-term sum by no more than the
    retained allowance—the final interval contains that target.  All interval
    products, additions, and widening are exact rational Lean computations.
  -/)] SparkInterval.Dirichlet.Factor8Postprocess.Certificate.output_contains_source

attribute [blueprint "thm:dirichlet-factor8-aligned-source-containment"
  (title := "Aligned factor-eight targets reuse the exact source enclosure")
  (uses := [
    SparkInterval.Dirichlet.Factor8Postprocess.AlignedCertificate.check,
    SparkInterval.Dirichlet.Factor8Postprocess.fineCoordinate_eq_sourceCoordinate_of_aligned])]
  SparkInterval.Dirichlet.Factor8Postprocess.AlignedCertificate.output_contains_source

attribute [blueprint "gap:dirichlet-factor8-analytic-realization"
  (title := "GAP: factor-eight analytic and physical realization")
  (hasProof := false)
  (notReady := true)
  (uses := [
    SparkInterval.Dirichlet.Factor8Postprocess.Certificate.output_contains_source])
  (statement := /--
    The finite Lean checker does not establish that the retained binary64
    source intervals contain the completed Dirichlet-L values, that the 280
    generated coefficient intervals contain the mathematical Gaussian--sinc
    weights, or that the uniform interpolation remainder is at most
    `86/10^9`.  It also does not prove that the CUDA FMA kernel refines the
    exact rational certificate, provide source-scale zero isolation and
    multiplicity-preserving Turing closure, or supply an attested production
    run.  Those are the explicit realization boundary; the external atom is
    not discharged by this checker.
  -/)] SparkInterval.Blueprint.dirichletFactor8AnalyticRealizationGap

/-! ## Factored small-`q` disk arithmetic and explicit production boundary -/

attribute [blueprint "def:complex-disk-multiplication-check"
  (title := "Exact-rational complex-disk multiplication checker")
  (statement := /--
    Checks nonnegative radii and exact squared rational inequalities for one
    proposed disk product.  It begins with typed rational values and does not
    identify any serialized record or physical arithmetic instruction.
  -/)] SparkInterval.Certified.ComplexDisk.MulCertificate.check

attribute [blueprint "thm:complex-disk-multiplication-sound"
  (title := "Accepted disk multiplication encloses every exact product")
  (uses := [SparkInterval.Certified.ComplexDisk.MulCertificate.check])]
  SparkInterval.Certified.ComplexDisk.MulCertificate.output_contains_mul

attribute [blueprint "thm:complex-disk-l1-centre-bound"
  (title := "The L1 centre bound certifies the Euclidean norm")
  (statement := /--
    Over exact rationals,
    `re^2 + im^2 ≤ (|re| + |im|)^2`.  The optimized PT21 FFT may therefore
    use a directed L1 upper bound without evaluating a square root and still
    satisfy the existing complex-disk multiplication checker.  This theorem
    does not assert that a CUDA instruction trace produced the bound.
  -/)] SparkInterval.Certified.ComplexDisk.centerNormSq_le_centerL1Bound_sq

attribute [blueprint "thm:complex-disk-l1-product-error-bound"
  (title := "The L1 product-error bound certifies Euclidean disk error")
  (uses := [
    SparkInterval.Certified.ComplexDisk.centerNormSq_le_centerL1Bound_sq])]
  SparkInterval.Certified.ComplexDisk.productCenterErrorSq_le_productCenterErrorL1Bound_sq

attribute [blueprint "thm:complex-disk-l1-sum-error-bound"
  (title := "The L1 sum-error bound certifies Euclidean disk error")
  (uses := [
    SparkInterval.Certified.ComplexDisk.centerNormSq_le_centerL1Bound_sq])]
  SparkInterval.Certified.ComplexDisk.sumCenterErrorSq_le_sumCenterErrorL1Bound_sq

attribute [blueprint "def:factored-smallq-trace-check"
  (title := "Bounded linked factored small-q trace checker")
  (uses := [SparkInterval.Certified.ComplexDisk.MulCertificate.check])
  (statement := /--
    Rechecks the shared square and cube, every pair of recurrence products,
    exact row-to-row disk links, and an explicit caller-supplied step bound.
  -/)] SparkInterval.Dirichlet.FactoredSmallQTrace.TraceCertificate.check

attribute [blueprint "thm:factored-smallq-trace-check-sound"
  (title := "Accepted trace rows form a well-linked bounded certificate")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQTrace.TraceCertificate.check,
    SparkInterval.Certified.ComplexDisk.MulCertificate.output_contains_mul])]
  SparkInterval.Dirichlet.FactoredSmallQTrace.TraceCertificate.checker_sound

attribute [blueprint "thm:factored-smallq-trace-exact-powers"
  (title := "Accepted factored trace encloses the exact Gaussian recurrence")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQTrace.TraceCertificate.checker_sound,
    SparkInterval.Certified.ComplexDisk.MulCertificate.output_contains_mul])
  (statement := /--
    Given only that the typed base disk contains `w`, the checked final disks
    contain the exact recurrence state and hence the powers
    `w^((N+1)^2)` and `w^(2(N+1)+1)` after `N` rows.
  -/)] SparkInterval.Dirichlet.FactoredSmallQTrace.TraceCertificate.output_contains_exact_after

attribute [blueprint "def:factored-smallq-raw-trace-check"
  (title := "Fail-closed raw binary64 factored trace checker")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQTrace.TraceCertificate.check,
    SparkInterval.Certified.ComplexDisk.RawMulCertificate.check])
  (statement := /--
    Decodes already-selected binary64 `Nat` words exactly, rejects nonfinite
    or oversized values, and then rechecks every typed arithmetic obligation
    and row link under an explicit maximum step count.  This is not a
    little-endian byte parser, and signed-zero bit-pattern canonicalization is
    outside this checker.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawTrace.RawTraceCertificate.check

attribute [blueprint "thm:factored-smallq-raw-term-count-exact-powers"
  (title := "Raw trace with an exact nonempty term count encloses the recurrence")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawTrace.RawTraceCertificate.check,
    SparkInterval.Dirichlet.FactoredSmallQTrace.TraceCertificate.output_contains_exact_after])
  (statement := /--
    A successful raw check preserves row count and, for `T > 0`, requires
    exactly `T - 1` recurrence updates.  Conditional on the decoded base disk
    containing `w`, the final disks contain
    `ExactGaussianState.after w (T - 1)`.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawTrace.RawTraceCertificate.term_count_output_contains_exact_after_of_base_decode

attribute [blueprint "def:factored-smallq-source-owned-campaign-check"
  (title := "Source-owned character/frequency campaign checker")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawTrace.RawTraceCertificate.check])
  (statement := /--
    The application supplies the modulus, exact ordered character roster,
    transform length, and per-cell term count.  The certificate must equal
    that domain, its batches must have exact ordinal/offset metadata, and its
    flattened cell keys must equal the literal row-major Cartesian product.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawCampaign.check

attribute [blueprint "thm:factored-smallq-requested-cell-arithmetic"
  (title := "Every requested campaign cell has an exact raw recurrence proof")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawCampaign.check,
    SparkInterval.Dirichlet.FactoredSmallQRawTrace.RawTraceCertificate.term_count_output_contains_exact_after_of_base_decode])
  (statement := /--
    For every character in the application-owned roster and every frequency
    below the application-owned transform length, an accepted campaign yields
    the actual raw payload, its exact-rational decoding, and enclosure of the
    recurrence at the application-owned truncation.  Base exponential
    containment remains an explicit analytic premise.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawCampaign.requested_output_contains_exact_after

attribute [blueprint "thm:complex-disk-canonical-byte-multiplication"
  (title := "Canonical little-endian disk bytes imply exact multiplication containment")
  (uses := [SparkInterval.Certified.ComplexDisk.RawMulCertificate.output_contains_mul])
  (statement := /--
    The standalone 96-byte primitive parser fixes little-endian field order,
    exact length, no trailing bytes, and a unique positive-zero spelling.  A
    successful byte check composes directly with the exact-rational disk
    multiplication theorem.  This is not yet the larger v3 frame parser.
  -/)] SparkInterval.Certified.ComplexDisk.Wire.checkedBytes_output_contains_mul

attribute [blueprint "thm:factored-smallq-typed-finite-gaussian-sum"
  (title := "Checked Gaussian rows enclose the exact finite sum")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQTrace.TraceCertificate.output_contains_exact_after,
    SparkInterval.Certified.ComplexDisk.MulCertificate.output_contains_mul,
    SparkInterval.Certified.ComplexDisk.AddCertificate.output_contains_add])
  (statement := /--
    Exact one-based ordinals, character multiplication, optional odd scaling,
    linked addition, and recurrence advancement are checked for exactly the
    declared truncation.  Conditional only on the explicit character/base
    containment inputs, the output disk contains the complete finite Gaussian
    sum.
  -/)] SparkInterval.Dirichlet.FactoredSmallQGaussianSum.SumTraceCertificate.output_contains_exact_finite_sum

attribute [blueprint "thm:factored-smallq-raw-sum-campaign"
  (title := "Every source-owned campaign cell has a raw exact finite-sum proof")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawSumCampaign.check,
    SparkInterval.Dirichlet.FactoredSmallQGaussianSum.SumTraceCertificate.output_contains_exact_finite_sum])
  (statement := /--
    The application fixes the modulus, ordered roster, transform length,
    per-cell parity, and exact term count.  Every requested cell is tied to a
    fully decoded raw multiplication/addition/recurrence trace whose result
    encloses its exact finite Gaussian sum.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawSumCampaign.requested_output_contains_exact_finite_sum

attribute [blueprint "thm:factored-smallq-postprocess"
  (title := "Prefactor, sign, and analytic-tail postprocessing preserve containment")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQGaussianSum.SumTraceCertificate.output_contains_exact_finite_sum,
    SparkInterval.Certified.ComplexDisk.MulCertificate.output_contains_mul])
  (statement := /--
    In CUDA order, the checker validates prefactor multiplication, optional
    negative-frequency conjugation, and nonnegative analytic-tail inflation.
    The output contains the exact signed prefactored sum plus every perturbation
    whose norm is bounded by the named tail.
  -/)] SparkInterval.Dirichlet.FactoredSmallQPostprocess.Certificate.output_contains_exact_finite_sum

attribute [blueprint "thm:factored-smallq-raw-postprocess-campaign"
  (title := "Every source-owned cell has a linked raw final-disk proof")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign.check,
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocess.RawCertificate.accepted_output_contains_exact_finite_sum,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.checker_sound])
  (statement := /--
    The application fixes each truncation, parity, and frequency-sign branch.
    Every raw final disk remains linked to the same finite-sum rows, prefactor,
    and decoded tail bound, conditional on the explicitly named analytic
    containment premises.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign.requested_output_contains_exact_postprocessed_sum

attribute [blueprint "thm:factored-smallq-positive-radix2-arithmetic"
  (title := "Checked positive-sign radix-2 stages preserve containment")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQDFT.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQDFT.ButterflyCertificate.outputs_contain])
  (statement := /--
    Exact stage, group, offset, left/right index, state, and twiddle links are
    checked for every output index of every stage.  Given the explicit
    bit-reversed input and root-disk containment premises, the final disks
    enclose the source positive-sign radix-2 algorithm.
  -/)] SparkInterval.Dirichlet.FactoredSmallQDFT.Certificate.output_contains_positiveRadix2

attribute [blueprint "thm:factored-smallq-cells-to-radix2-line"
  (title := "Raw postprocessed cells compose into bit-reversed transform lines")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign.requested_output_contains_exact_postprocessed_sum,
    SparkInterval.Dirichlet.FactoredSmallQDFT.Certificate.output_contains_positiveRadix2])
  (statement := /--
    Exact raw-output decoding and natural-to-bit-reversed disk equations turn
    the source-owned per-cell containment theorem into the DFT input invariant.
    The resulting final disks enclose the complete positive-sign radix-2
    transform for every requested character.
  -/)] SparkInterval.Dirichlet.FactoredSmallQDFTComposition.output_contains_positiveRadix2

attribute [blueprint "thm:factored-smallq-bounded-raw-dft-certificate"
  (title := "Bounded raw DFT certificates realize the typed checker")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawDFT.RawCertificate.boundsCheck,
    SparkInterval.Dirichlet.FactoredSmallQRawDFT.RawCertificate.decode,
    SparkInterval.Dirichlet.FactoredSmallQDFT.Certificate.check])
  (statement := /--
    Before any nested binary64 decoding, the raw checker bounds transform
    length, line length, and total records. It then checks exact canonical list
    shapes, decodes every disk and butterfly witness in order, explicitly
    rejects negative radii in all input/twiddle/output tables, invokes the typed
    radix-2 checker, and checks the separately supplied final output pointwise
    against the state derived from the complete trace.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawDFT.RawCertificate.checker_sound

attribute [blueprint "thm:factored-smallq-raw-dft-word-endpoint"
  (title := "Literal raw DFT output words enclose the exact staged transform")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawDFT.RawCertificate.checker_sound,
    SparkInterval.Dirichlet.FactoredSmallQDFT.Certificate.output_contains_transform])
  (statement := /--
    At every source-owned frequency the theorem returns the literal raw disk
    from the certificate output list, its exact rational decoding, and a proof
    that this decoded disk contains the exact staged transform. Root-disk and
    input containment remain explicit mathematical premises; no byte-parser or
    execution claim is hidden in this endpoint.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawDFT.RawCertificate.output_words_contain_transform

attribute [blueprint "thm:factored-smallq-raw-cells-to-raw-dft-words"
  (title := "Raw postprocessed cells compose to raw DFT output words")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQDFTComposition.input_contains_bitReversed,
    SparkInterval.Dirichlet.FactoredSmallQRawDFT.RawCertificate.output_words_contain_positiveRadix2])
  (statement := /--
    Exact source-owned postprocessing cells are linked to the decoded natural
    table, the raw input is linked to its bit reversal, and every requested
    character has a bounded accepted raw DFT trace. The conclusion names each
    literal raw output word and proves containment of the exact positive-sign
    radix-2 transform of the complete postprocessed source line.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawDFTComposition.output_words_contain_postprocessed_radix2

attribute [blueprint "thm:factored-smallq-completed-strict-sign"
  (title := "Scaled, time-inflated, untilted disks prove strict completed signs")
  (uses := [
    SparkInterval.Certified.ComplexDisk.MulCertificate.output_contains_mul,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.output_contains_add_tail,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.accepted_factors_positive])
  (statement := /--
    A checked Fourier disk is multiplied by the explicit positive `2*pi/b`
    scale, inflated by the named time-periodization bound, and multiplied by
    the explicit untilt factor.  If the analytically named completed value is
    real, either rational inequality `radius < re` or `re < -radius` proves
    its strict sign.
  -/)] SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.accepted_sign

attribute [blueprint "thm:factored-smallq-completed-source-sign"
  (title := "Source-shaped scale and untilt factors prove a strict sign")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.sourceScale_pos,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.sourceUntilt_pos,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.accepted_sign])
  (statement := /--
    With `0 < b` explicit, the reusable completed-value theorem is
    instantiated at the source formulas `2*pi/b` and
    `exp(-pi*eta*t/4)`. Fourier and factor containment, the complex-norm
    time-tail bound, and functional-equation reality remain named premises.
  -/)] SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.accepted_source_sign

attribute [blueprint "thm:factored-smallq-raw-completed-source-sign"
  (title := "Raw binary64 arithmetic proves a source-shaped completed sign")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign.RawCertificate.checker_sound,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.accepted_source_sign])
  (statement := /--
    Literal binary64 disks decode to the two multiplication witnesses and the
    time-tail inflation in the exact producer order
    `(fourier * scale + timeTail) * untilt`. The checker attaches the first
    raw operand literally to the supplied Fourier word and accepts only the
    producer-compatible strict-sign codes `-1` and `+1`. The conclusion keeps
    the exact decodes, source guards, `2*pi/b` and exponential untilt factors,
    and strict sign; all analytic containment and reality premises are
    explicit.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign.RawCertificate.accepted_source_sign

attribute [blueprint "thm:factored-smallq-source-sample-sign-coverage"
  (title := "Every retained source sample has a checked strict sign")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign.sourceCheck_sound,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.accepted_sign])
  (statement := /--
    `SourceSampleSpec` names the retained `sampleCount` separately from the
    full guard-length DFT and the checker proves `sampleCount <= fullDFTLength`.
    Exact roster-times-sample coverage composes with completed-value arithmetic
    at every requested character and returns the bound needed to construct the
    corresponding full-DFT index.
  -/)] SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign.requested_source_sample_has_sign

attribute [blueprint "thm:factored-smallq-raw-word-to-direct-dft-sign"
  (title := "Raw DFT words compose to strict signs of exact direct DFT values")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawDFTComposition.output_words_contain_postprocessed_radix2,
    SparkInterval.Dirichlet.FactoredSmallQDFT.radix2CorrectFor,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.accepted_sign,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.bridgeCheck_sound])
  (statement := /--
    A finite bridge checker aligns modulus, ordered roster, full power-of-two
    line length, retained sample count, and every retained Fourier disk. For
    each requested source sample, the theorem returns its literal binary64 raw
    output word, exact rational disk decoding, containment of the exact direct
    positive DFT of the postprocessed source line, and the completed value's
    strict sign. Every analytic containment and reality fact remains explicit.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.requested_source_sample_has_direct_sign

attribute [blueprint "thm:factored-smallq-raw-word-to-source-sign"
  (title := "Raw DFT words compose to source-shaped completed signs")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.requested_source_sample_has_direct_sign,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.accepted_source_sign])
  (statement := /--
    Header-wide source parameters `a`, `b`, and `eta` cannot drift between
    retained keys. The grid guard proves `0<a`, `0<b`, `-1<eta<1`, derives
    `t=sample/a`, and checks `b=fullDFTLength/a`; the production constant is
    separately named `bookerA=64/5`. The raw-word bridge concludes the checked
    strict sign using the explicit source scale and untilt formulas.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.requested_source_sample_has_source_sign

attribute [blueprint "thm:factored-smallq-raw-dft-word-to-raw-source-sign"
  (title := "Each raw sign payload consumes its exact raw DFT output word")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawDFTComposition.output_words_contain_postprocessed_radix2,
    SparkInterval.Dirichlet.FactoredSmallQDFT.radix2CorrectFor,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign.RawCertificate.accepted_source_sign,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign.checker_sound])
  (statement := /--
    The source-sample campaign looks up the literal raw DFT output word at the
    source-owned character/sample coordinate and passes that word directly to
    the raw completed-sign checker. Missing output, a detached spelling, or a
    wrong sign therefore fails before the application theorem. Every
    requested sample returns that same raw word, its exact direct positive-DFT
    enclosure, all source guards, and the strict source-formula sign.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign.requested_source_sample_has_raw_source_sign

attribute [blueprint "thm:factored-smallq-completed-signs-to-zero-certificate"
  (title := "Checked completed signs produce exact rational zero brackets")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.checker_sound,
    SparkInterval.Zeta.RationalBracketFamily.exists_zeroCertificate])
  (statement := /--
    Two completed-value disks attached to one character and the exact rational
    source grid are projected onto the real axis.  Positive sampling rate,
    increasing samples and times, exact `time = sample/a`, opposite strict
    signs, and global bracket separation are checked with rational arithmetic.
    Explicit containment/reality/evaluator equalities then turn the checked
    family into the existing zero-certificate interface.  No evaluator fact
    is inferred from certificate metadata alone.
  -/)] SparkInterval.Dirichlet.FactoredSmallQZeroBracket.CompletedSignBracketFamily.exists_zeroCertificate

attribute [blueprint "thm:factored-smallq-raw-cells-to-checked-bracket"
  (title := "Literal raw sign cells produce a checked rational bracket")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign.checker_sound,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign.RawCertificate.checker_sound,
    SparkInterval.Dirichlet.FactoredSmallQZeroBracket.CompletedSignBracket.toRationalBracket_check])
  (statement := /--
    A typed endpoint is admitted only as the deterministic decode of an actual
    source-campaign cell.  The endpoint checker uses the disk decoded from the
    literal raw DFT word at that same character/sample coordinate.  Positive
    exact rational sampling rate, common character, increasing samples, and
    opposite decoded signs then give a checked rational bracket.  The exact
    rational/real `sample/a` cast, including Booker's `a=64/5`, is proved
    separately; evaluator realization remains an explicit analytic premise.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign.decodedCells_bracket_check

attribute [blueprint "thm:factored-smallq-raw-cells-to-evaluator-bracket"
  (title := "Raw-backed brackets enclose an explicitly realized evaluator")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign.decodedCells_bracket_check,
    SparkInterval.Dirichlet.FactoredSmallQZeroBracket.CompletedSignBracket.checkedRationalBracket_of_sourceRealizes])
  (statement := /--
    The finite raw campaign proves bracket acceptance.  Two separately stated
    `SourceRealizes` premises—containing the Fourier and factor enclosures,
    tail bounds, functional-equation reality, and exact evaluator equalities—
    prove that the projected endpoint intervals enclose one named real
    function.  No semantic fact is inferred from raw bytes or metadata.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign.decodedCells_checkedRationalBracket_of_sourceRealizes

attribute [blueprint "def:factored-smallq-primitive-roster-realization"
  (title := "Opaque source IDs exactly enumerate primitive characters")
  (statement := /--
    A supplied noduplicated roster maps every listed opaque identifier to a
    primitive Dirichlet character, and every primitive character has exactly
    one listed identifier. This is an exact mathematical bijection contract;
    it does not assert that the identifiers are Conrey numbers or prove a
    concrete source enumeration.
  -/)] SparkInterval.Dirichlet.FactoredSmallQSourceRealization.PrimitiveRosterRealization

attribute [blueprint "def:factored-smallq-modulus-roster-realization"
  (title := "Arithmetic modulus and source roster match the primitive roster")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQSourceRealization.PrimitiveRosterRealization])
  (statement := /--
    The arithmetic modulus is the mathematical modulus and the full and
    retained source rosters are the same exact list interpreted by the
    primitive-character bijection.
  -/)] SparkInterval.Dirichlet.FactoredSmallQSourceRealization.ModulusRosterRealization

attribute [blueprint "def:factored-smallq-character-input-realization"
  (title := "Application rows and parity realize one fixed Dirichlet character")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQSourceRealization.ModulusRosterRealization])
  (statement := /--
    At every in-domain arithmetic key, the application row is exactly
    `[chi(1), ..., chi(termCount)]` for the roster character selected by that
    key, and the Boolean branch proves the odd or even parity of the same
    character. Frequency-dependent character substitution is excluded.
  -/)] SparkInterval.Dirichlet.FactoredSmallQSourceRealization.CharacterInputsRealize

attribute [blueprint "def:factored-smallq-source-evaluator-realization"
  (title := "The exact source expression equals a named real evaluator")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQSourceRealization.ModulusRosterRealization])
  (statement := /--
    For one roster identifier, the source sampling rate is exactly Booker's
    `64/5` and one complex equality identifies the factored/direct-DFT source
    expression with a fixed real evaluator at every retained sample. The
    proposition is an explicit analytic obligation, not an asserted source
    fact or an identification with a completed L-function by itself.
  -/)] SparkInterval.Dirichlet.FactoredSmallQSourceRealization.SourceEvaluatorRealizes

attribute [blueprint "thm:factored-smallq-source-realization-supplies-reality"
  (title := "Source evaluator equations supply the raw sign reality premise")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign.cell_key_in_source_domain,
    SparkInterval.Dirichlet.FactoredSmallQSourceRealization.SourceEvaluatorRealizes.value_im_eq_zero])
  (statement := /--
    Campaign acceptance proves every raw sign cell lies in the source domain;
    a family of the exact complex evaluator equations therefore discharges
    precisely `SourceCompletedValuesReal`. It does not construct the
    equations, a bracket family, a Hardy model, or a total-zero count.
  -/)] SparkInterval.Dirichlet.FactoredSmallQSourceRealization.SourceEvaluatorFamilyRealizes.completedValuesReal

attribute [blueprint "thm:factored-smallq-requested-cell-character-evaluator"
  (title := "One raw source cell is tied to its character and evaluator")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign.requested_source_sample_has_raw_source_sign,
    SparkInterval.Dirichlet.FactoredSmallQSourceRealization.CharacterInputsRealize,
    SparkInterval.Dirichlet.FactoredSmallQSourceRealization.SourceEvaluatorFamilyRealizes.completedValuesReal,
    SparkInterval.Dirichlet.FactoredSmallQSourceRealization.CharacterEvaluatorInputsRealize.decodedCellAt_character_and_evaluator])
  (statement := /--
    The complete finite postprocess and raw DFT proof returns a literal output
    word and its direct-DFT enclosure. At the same deterministically decoded
    sign cell, the combined source contract exposes the exact mathematical
    character row and parity and proves the endpoint `EvaluatorLink` at the
    rational Booker time `sample/(64/5)`. All source equations and analytic
    disk, tail, and root containments remain named theorem premises.
  -/)] SparkInterval.Dirichlet.FactoredSmallQSourceRealization.requested_source_sample_has_character_and_evaluator

attribute [blueprint "thm:factored-smallq-all-moduli-raw-word-to-direct-sign"
  (title := "Ordered modulus bundles compose raw DFT words to direct-value signs")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign.Certificate.checker_sound,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.requested_source_sample_has_direct_sign])
  (statement := /--
    A source-owned nonempty list with unique modulus identifiers is matched in
    exact order and length to complete raw postprocess, raw DFT, and sign
    bundles.  The decoded transform is the canonical projection of each raw
    certificate, and an accepted raw check proves that its fallback branch is
    unreachable.  Every requested modulus, character, and retained sample
    therefore returns its literal raw word, direct positive-DFT enclosure, and
    strict completed sign, with all analytic premises aligned to that same
    modulus rather than supplied globally.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign.requested_modulus_sample_has_direct_sign

attribute [blueprint "thm:factored-smallq-all-moduli-raw-word-to-source-sign"
  (title := "Ordered source headers give source-shaped signs for every modulus")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign.SourceApplicationInputsAligned.headers_aligned,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign.requested_modulus_sample_has_direct_sign,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.requested_source_sample_has_source_sign])
  (statement := /--
    One header-wide `a`, `b`, `eta`, and time-tail function is paired with each
    exact modulus bundle by the same ordered relation as the finite
    certificates.  The endpoint exposes the positive denominator guards,
    eta range, exact grid equation, literal raw word, direct DFT enclosure,
    and strict sign of the exact source expression with `t = sample / a`.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign.requested_modulus_sample_has_source_sign

attribute [blueprint "thm:factored-smallq-all-moduli-raw-payload-to-source-sign"
  (title := "Every modulus uses its exact raw DFT word in its raw sign payload")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign.Certificate.checker_sound,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign.requested_source_sample_has_raw_source_sign])
  (statement := /--
    Each ordered modulus bundle contains both its raw DFT certificates and its
    raw completed-sign campaign.  The checker indexes the exact source-owned
    character/sample coordinate and gives the literal DFT output word to the
    corresponding raw sign checker. Exact ordered relations align the finite
    bundles, source headers, and analytic premises, so omission, reordering,
    duplicate modulus identifiers, or detached words fail closed.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign.requested_modulus_sample_has_raw_source_sign

attribute [blueprint "thm:platt-theorem-7-1-source-handoff"
  (title := "Per-modulus finite GRH results imply Platt Theorem 7.1")
  (uses := [
    SparkInterval.Dirichlet.GRHVerifiedForModulus,
    SparkInterval.Dirichlet.grhVerifiedForModulus_of_characters,
    SparkInterval.Dirichlet.plattTheorem71EvenHeight,
    SparkInterval.Dirichlet.plattTheorem71OddHeight])
  (statement := /--
    Symmetric finite-GRH results for every primitive character and every
    conductor through 400000, at the exact parity-dependent heights printed
    in Platt Theorem 7.1, imply the expanded source proposition used by the
    ternary-Goldbach development. This theorem is the clean final application
    boundary; it does not manufacture the per-modulus verification premises.
  -/)] SparkInterval.Dirichlet.plattTheorem71_of_modulus_verification

attribute [blueprint "thm:platt-theorem-7-1-source-evidence"
  (title := "The exact two parity branches package the Platt source result")
  (uses := [
    SparkInterval.Dirichlet.plattTheorem71_of_modulus_verification])
  (statement := /--
    A single source-evidence value retains the universal per-modulus finite-GRH
    result separately for even and odd conductors at the exact source heights.
    Constructing the value remains the physical campaign obligation.
  -/)] SparkInterval.Dirichlet.plattTheorem71_of_source_evidence

attribute [blueprint "thm:platt-theorem-7-1-registered-capstone"
  (title := "A successful registered Dirichlet finalizer returns Platt Theorem 7.1")
  (uses := [
    SparkInterval.Dirichlet.plattTheorem71_of_source_evidence])
  (statement := /--
    The closed CPU/SEV-SNP invocation pins the full conductor range, both
    parity-dependent heights, the exact q=2..400000 primitive-character count,
    and the separate q=1 zeta source campaign. Result `true` requires the exact
    universal two-branch source evidence; result `false` proves nothing.
  -/)] SparkInterval.Execution.RegisteredInvocation.plattDirichletTheorem71ProductionV1_sourceClaim

attribute [blueprint "thm:platt-theorem-7-1-signed-capstone"
  (title := "One accepted Dirichlet finalizer receipt exposes the source theorem")
  (uses := [
    SparkInterval.Execution.RegisteredInvocation.plattDirichletTheorem71ProductionV1_sourceClaim])]
  SparkInterval.Execution.SignedResultCertificate.certifyPlattDirichletTheorem71

attribute [blueprint "thm:dirichlet-endpoint-family-to-finite-grh"
  (title := "Dirichlet endpoint brackets and a total count prove finite GRH")
  (uses := [
    SparkInterval.Zeta.RationalBracketFamily.exists_zeroCertificate,
    SparkInterval.Dirichlet.DirichletHardyModel.criticalLineZeroBridge,
    SparkInterval.Dirichlet.LZeroCountUpperBound])
  (statement := /--
    For one nontrivial character, a proved real completed-L model turns a
    checked family of ordered strict-sign brackets into critical-line zeros.
    A matching upper bound for all zeros in the source-faithful open strip
    `(0,1) x [lo,hi]` then forces every nontrivial zero there onto the critical
    line. Finiteness comes from containment in the closed compact envelope;
    endpoint enclosures and the analytic total-count bound remain explicit.
  -/)] SparkInterval.Dirichlet.DirichletHardyModel.verifyEndpointFamily

attribute [blueprint "thm:factored-smallq-completed-brackets-to-finite-grh"
  (title := "Completed small-q brackets compose directly to finite GRH")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQZeroBracket.CompletedSignBracketFamily.exists_zeroCertificate,
    SparkInterval.Dirichlet.DirichletHardyModel.verifyEndpointFamily])
  (statement := /--
    For one primitive character, the checked completed-sign bracket family is
    projected into the established rational endpoint interface.  The
    completed-L Hardy model, endpoint evaluator links, enclosing height
    bounds, character nontriviality, and complete L-zero upper count remain
    explicit arguments.  The per-modulus corollary repeats these obligations
    for every primitive character instead of hiding them in a receipt.
  -/)] SparkInterval.Dirichlet.DirichletHardyModel.verifyCompletedSignBracketFamily

attribute [blueprint "thm:factored-smallq-primitive-roster-to-finite-grh"
  (title := "Opaque roster families assemble into modulus-level finite GRH")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQSourceRealization.PrimitiveRosterRealization,
    SparkInterval.Dirichlet.FactoredSmallQZeroBracket.CompletedSignBracketFamily.check,
    SparkInterval.Dirichlet.DirichletHardyModel.verifyCompletedSignBracketFamily])
  (statement := /--
    Completeness of the primitive-character roster selects the unique source
    identifier for any primitive mathematical character. A checked bracket
    family whose header is explicitly equal to that identifier, together with
    its Hardy model, endpoint evaluator links, height bounds, and total-zero
    upper count, yields `GRHVerifiedForModulus`. The family-header equality is
    used to rewrite the source-indexed evaluator, rather than retained as
    unused metadata.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRosterGRHBridge.grhVerifiedForModulus_of_primitiveRosterCompletedSignBracketFamilies

attribute [blueprint "thm:dirichlet-per-character-finite-grh"
  (title := "Exact critical-line and total counts force all Dirichlet zeros onto the line")
  (uses := [
    SparkInterval.Dirichlet.GRHVerifierEvidence.exact_criticalLine_count,
    SparkInterval.Dirichlet.GRHVerifierEvidence.exact_total_count])
  (statement := /--
    The bracket count and global upper bound collapse to equality between the
    distinct critical-line zero set and the complete nontrivial-zero set in
    `(0,1) x [lo,hi]`. The latter is finite by containment in `[0,1] x
    [lo,hi]`. Multiplicity is not discarded by assumption: a production
    Turing or argument-principle layer must justify the total upper bound it
    supplies.
  -/)] SparkInterval.Dirichlet.GRHVerifierEvidence.all_zeros_on_criticalLine

attribute [blueprint "gap:platt-theorem-7-1-verifier-realization"
  (title := "GAP: realize every Platt modulus, character, bracket, and total count")
  (hasProof := false)
  (notReady := true)
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign.requested_modulus_sample_has_raw_source_sign,
    SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign.decodedCells_bracket_check,
    SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign.decodedCells_checkedRationalBracket_of_sourceRealizes,
    SparkInterval.Dirichlet.FactoredSmallQSourceRealization.PrimitiveRosterRealization,
    SparkInterval.Dirichlet.FactoredSmallQSourceRealization.ModulusRosterRealization,
    SparkInterval.Dirichlet.FactoredSmallQSourceRealization.CharacterInputsRealize,
    SparkInterval.Dirichlet.FactoredSmallQSourceRealization.SourceEvaluatorRealizes,
    SparkInterval.Dirichlet.FactoredSmallQSourceRealization.SourceEvaluatorFamilyRealizes.completedValuesReal,
    SparkInterval.Dirichlet.FactoredSmallQSourceRealization.requested_source_sample_has_character_and_evaluator,
    SparkInterval.Dirichlet.FactoredSmallQZeroBracket.CompletedSignBracketFamily.exists_zeroCertificate,
    SparkInterval.Dirichlet.DirichletHardyModel.verifyCompletedSignBracketFamily,
    SparkInterval.Dirichlet.FactoredSmallQRosterGRHBridge.grhVerifiedForModulus_of_primitiveRosterCompletedSignBracketFamilies,
    SparkInterval.Dirichlet.grhVerifiedForModulus_of_completedSignBracketFamilies,
    SparkInterval.Dirichlet.grhVerifiedForModulus_of_characters,
    SparkInterval.Dirichlet.plattTheorem71_of_modulus_verification,
    SparkInterval.Execution.RegisteredInvocation.plattDirichletTheorem71ProductionV1_sourceClaim])
  (statement := /--
    The final source proposition now has an exact Lean handoff. Closing it
    now states the primitive-roster, exact character-row/parity, and single
    complex source/evaluator contracts explicitly, but no concrete campaign
    inhabits them yet. Closing the gap still requires proving those contracts
    for the actual source data, constructing complete checked bracket families
    (including upsampling and exceptions), identifying each named evaluator
    with the corresponding completed-L Hardy model, conjugation coverage,
    the separate `q=1` zeta case, and a certified Turing or argument-principle
    upper count for every conductor through 400000. The executable Turing
    candidate now reflects the negative window to the conjugate character,
    retains the source `+2/pi`, and scales the elementary terms by `1/(h*pi)`
    but the zero staircase and `S` terms by `1/h`; that derivation and its
    multiplicity-to-distinct-count consequence are not yet Lean theorems. The
    physical byte/checker tie-in remains the separate small-q frame gap. No source-evidence
    materializer, completed physical campaign, or successful receipt is
    admitted, so the Azure semantic binding remains disabled with null
    theorem, realization, and invocation fields.
  -/)] SparkInterval.Blueprint.plattTheorem71VerifierRealizationGap

attribute [blueprint "thm:factored-smallq-radix2-direct-dft"
  (title := "The generic radix-2 network equals the direct positive DFT")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQDFT.exactStage_blockTransform,
    SparkInterval.Dirichlet.FactoredSmallQDFT.reverseBits_involutive,
    SparkInterval.Dirichlet.FactoredSmallQDFT.blockTransform_full_eq_directDFT])
  (statement := /--
    A block-transform invariant proves every radix-2 stage, the bit-reversal
    permutation is proved involutive, and the full block sum is reindexed to
    the direct positive-sign DFT. Thus `Radix2CorrectFor source` is a theorem
    for every transform length and source, with no analytic or execution
    premise.
  -/)] SparkInterval.Dirichlet.FactoredSmallQDFT.radix2CorrectFor

attribute [blueprint "thm:factored-smallq-outer-modulus-coverage"
  (title := "Every source-owned modulus and cell has an accepted payload")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQModulusCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.checker_sound])
  (statement := /--
    The application supplies the complete ordered list of modulus
    specifications.  Unique modulus identifiers, exact list length/order, and
    every nested character/frequency product are checked, so an accepted
    certificate cannot omit or substitute a requested cell.  Showing that the
    supplied rosters enumerate precisely the paper's primitive characters is
    intentionally a separate source-realization theorem.
  -/)] SparkInterval.Dirichlet.FactoredSmallQModulusCampaign.exists_payload_for_requested_cell

attribute [blueprint "thm:factored-smallq-all-moduli-postprocessed-arithmetic"
  (title := "Every requested modulus cell encloses its exact postprocessed sum")
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQModulusCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign.requested_output_contains_exact_postprocessed_sum])
  (statement := /--
    The exact ordered outer modulus list and the nested character/frequency
    products are composed with the raw finite-sum, prefactor, sign, and tail
    checker.  Analytic containment hypotheses are aligned by the same
    `Forall₂` relation as the source/certificate list, so evidence for one
    modulus cannot be silently reused for another.
  -/)] SparkInterval.Dirichlet.FactoredSmallQRawPostprocessModulusCampaign.requested_output_contains_exact_postprocessed_sum

attribute [blueprint "gap:factored-smallq-whole-frame-physical-full-range"
  (title := "GAP: small-q frame decoding, source realization, and physical execution")
  (hasProof := false)
  (notReady := true)
  (uses := [
    SparkInterval.Dirichlet.FactoredSmallQRawSumCampaign.check,
    SparkInterval.Dirichlet.FactoredSmallQRawSumCampaign.requested_output_contains_exact_finite_sum,
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign.requested_output_contains_exact_postprocessed_sum,
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocessModulusCampaign.requested_output_contains_exact_postprocessed_sum,
    SparkInterval.Dirichlet.FactoredSmallQDFTComposition.output_contains_positiveRadix2,
    SparkInterval.Dirichlet.FactoredSmallQRawDFTComposition.output_words_contain_postprocessed_radix2,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign.requested_sample_has_sign,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.requested_source_sample_has_direct_sign,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign.requested_source_sample_has_raw_source_sign,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign.requested_modulus_sample_has_source_sign,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign.requested_modulus_sample_has_raw_source_sign,
    SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign.decodedCells_bracket_check,
    SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign.decodedCells_checkedRationalBracket_of_sourceRealizes,
    SparkInterval.Dirichlet.FactoredSmallQZeroBracket.CompletedSignBracketFamily.exists_zeroCertificate,
    SparkInterval.Dirichlet.FactoredSmallQModulusCampaign.exists_payload_for_requested_cell])
  (statement := /--
    The arithmetic theorem now starts from already-selected binary64 `Nat`
    words.  Production use still requires (1) a bounded little-endian byte
    parser, including any required signed-zero canonicalization, that relates
    every version-3 frame/sidecar field to those words and constructs the
    checked application-owned campaign (the standalone multiplication parser
    is already proved), (2) a refinement theorem from
    the measured CUDA/PTX/SASS or CPU program to the checked row semantics,
    (3) a deterministic sidecar generator or whole-frame parser that supplies
    the already-proved bounded raw DFT certificate (including its complete
    butterfly trace) from physical output, and (4) a theorem
    realizing the application-owned modulus/roster list as exactly the source
    paper's primitive-character domain, followed by the final useful-width /
    zero-count predicate.
    Character/frequency batch coverage, exact recurrence term counts, the full
    finite Gaussian sum, raw prefactor/sign/tail postprocessing, bounded raw
    staged radix-2 arithmetic with literal output-word linkage, source-owned
    ordered outer-modulus postprocessed and source-shaped sign arithmetic,
    and conditional scale/time-tail/untilt strict-sign coverage are now
    checked; the remaining edges above are not.
    This node does not claim that any ternary-Goldbach external atom is thereby
    closed.
  -/)] SparkInterval.Blueprint.factoredSmallQWholeFrameGap
