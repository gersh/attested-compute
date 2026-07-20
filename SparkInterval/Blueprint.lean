import Architect
import SparkInterval.Certificate.Format
import SparkInterval.ComplexInterval
import SparkInterval.Execution.FormalPTXProgram
import SparkInterval.Execution.CompactAttestedVerifier
import SparkInterval.Execution.RegisteredCubicSumCertificate
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
import SparkInterval.Zeta.StreamingEndpointCertificate
import SparkInterval.Zeta.StreamingChunkVerifier
import SparkInterval.Zeta.SymmetricCount
import SparkInterval.Zeta.Verifier

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
    input digest, parameter digest, and domain digest.  It cannot be populated
    with caller-chosen execution semantics.
  -/)] SparkInterval.Execution.RegisteredInvocation.statementCheck

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
  (uses := [SparkInterval.Execution.checkDGXOperatorSignature,
    SparkInterval.Execution.checkH100Attestation])]
  SparkInterval.Execution.RunCertificate.check

attribute [blueprint "def:accepted-run-produced-outcome"
  (title := "Historical and closed-registry facts supplied at the trust boundary")
  (uses := [
    SparkInterval.Execution.RegisteredInvocation.statementCheck,
    SparkInterval.Execution.RegisteredInvocation.Runs])
  (statement := /--
    The outcome retains the original exact historical return fact and a second
    projection that exposes only the fixed `Runs` relation of a matching closed
    invocation.  It contains no caller-provided execution predicate.
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

attribute [blueprint "axiom:accepted-run-certificate"
  (title := "TRUST AXIOM: accepted evidence yields exact and registered run facts")
  (hasProof := false)
  (uses := [
    SparkInterval.Execution.RunCertificate.check,
    SparkInterval.Execution.RunCertificate.ProducedOutcome])
  (statement := /--
    This sole project trust axiom converts a certificate accepted under one of
    the supported imported-evidence policies into both the exact historical
    returned-bytes fact and the fixed formal `Runs` relation for a matching
    closed invocation.  It is the per-run trusted bridge across evidence
    verification, artifact measurement, backend behavior, and physical
    execution.  It does not prove a general PTX/backend refinement theorem;
    algorithm soundness and result mathematics remain downstream proofs.
  -/)] SparkInterval.Execution.Trusted.accepted_run_certificate_sound

attribute [blueprint "thm:accepted-registered-run"
  (title := "Accepted matching invocation yields its fixed Runs proposition")
  (uses := [
    SparkInterval.Execution.RegisteredInvocation.statementCheck,
    SparkInterval.Execution.RegisteredInvocation.Runs])
  (proofUses := [
    SparkInterval.Execution.Trusted.accepted_run_certificate_sound,
    SparkInterval.Execution.RunCertificate.ProducedOutcome.registered])]
  SparkInterval.Execution.Trusted.accepted_registered_run_sound

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

/-- Documentation-only marker for an executable bounded-memory parser and
checker corresponding to the theorem-level chunk composition. -/
def streamingZetaCheckerGap : Unit := ()

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
