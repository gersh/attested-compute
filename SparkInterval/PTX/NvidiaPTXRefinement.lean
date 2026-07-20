import SparkInterval.PTX.MachineSemantics
import SparkInterval.PTX.Emitter
import SparkInterval.PTX.NvidiaPTXSpec

/-!
# Refinement to the pinned PTX 9.0 transcription

These theorems connect the library's existing numeric and one-thread machine
semantics to `NvidiaPTX90`.  They do not connect emitted PTX to ptxas, SASS,
the CUDA driver, or hardware; those remain explicit trust/refinement layers.
-/

set_option autoImplicit false

namespace SparkInterval.PTX.NvidiaPTX90

/-- Pinned module profile selected by each target of the typed emitter. -/
def emitterModuleProfile : EmitterTarget → ModuleProfile
  | .sm90 => h100Profile
  | .sm121 => dgxSparkProfile

/-- The actual total emitter starts every module with the three directives of
the pinned DGX Spark profile. -/
theorem renderUnchecked_startsWith_dgxSparkProfile (module : Module) :
    (renderUnchecked module).startsWith dgxSparkProfile.directivePrefix = true := by
  have h64 : Nat.toDigits 10 64 = ['6', '4'] := by decide
  apply String.startsWith_string_iff.mpr
  simp [renderUnchecked, renderUncheckedFor, ModuleProfile.directivePrefix,
    dgxSparkProfile, TargetProfile.token, EmitterTarget.token, h64]

/-- The H100 rendering starts with the pinned `sm_90` PTX 9.0 profile. -/
theorem renderUncheckedH100_startsWith_h100Profile (module : Module) :
    (renderUncheckedH100 module).startsWith h100Profile.directivePrefix = true := by
  have h64 : Nat.toDigits 10 64 = ['6', '4'] := by decide
  apply String.startsWith_string_iff.mpr
  simp [renderUncheckedH100, renderUncheckedFor, ModuleProfile.directivePrefix,
    h100Profile, TargetProfile.token, EmitterTarget.token, h64]

/-- The target-parameterized emitter starts with exactly the corresponding
pinned PTX 9.0 architecture profile. -/
theorem renderUncheckedFor_startsWith_emitterModuleProfile
    (target : EmitterTarget) (module : Module) :
    (renderUncheckedFor target module).startsWith
      (emitterModuleProfile target).directivePrefix = true := by
  cases target with
  | sm90 =>
      change (renderUncheckedH100 module).startsWith
        h100Profile.directivePrefix = true
      exact renderUncheckedH100_startsWith_h100Profile module
  | sm121 =>
      change (renderUnchecked module).startsWith
        dgxSparkProfile.directivePrefix = true
      exact renderUnchecked_startsWith_dgxSparkProfile module

/-- Every opcode in a compiler-produced module has a primary normative clause
in the pinned PTX 9.0 source. -/
theorem buildModule_opcodeTrace_all_have_pinned_clauses
    (batch : ReferenceBatch) {opcode : Opcode}
    (hopcode : opcode ∈ opcodeTrace (buildModule batch).body) :
    ∃ clause, opcodeClause opcode = clause ∧ clause.reference.source = sourcePin := by
  apply allowedOpcode_has_pinned_clause
  unfold opcodeTrace at hopcode
  simp only [List.mem_filterMap] at hopcode
  rcases hopcode with ⟨instruction, _hinstructions, hinstruction⟩
  exact Instruction.opcode_mem_allowed hinstruction

/-- Existing directed arithmetic is exactly the pinned finite-input
transcription after converting its rounded result to the machine model. -/
theorem directedBinary_finite_refines (op : F64BinaryOp)
    (rounding : DirectedRounding) (left right : Real) :
    directedBinary op rounding (.finite left) (.finite right) =
      some (F64Value.ofExt
        (evalFinite (BinaryOp.ofTyped op) (RoundingMode.ofTyped rounding) left right)) := by
  cases op <;> cases rounding <;> rfl

/-- Existing non-NaN minimum agrees with the pinned PTX numeric transcription. -/
theorem minimum_nonNaN_refines (left right : F64Value) :
    F64Value.minimum left right =
      (minimum (NumericValue.ofModel left) (NumericValue.ofModel right)).toModel := by
  cases left <;> cases right <;> rfl

/-- Existing non-NaN maximum agrees with the pinned PTX numeric transcription. -/
theorem maximum_nonNaN_refines (left right : F64Value) :
    F64Value.maximum left right =
      (maximum (NumericValue.ofModel left) (NumericValue.ofModel right)).toModel := by
  cases left <;> cases right <;> rfl

/-- A typed binary-f64 machine step with finite operands produces exactly the
result specified by the pinned PTX arithmetic transcription. -/
theorem executeInstruction_binaryF64_finite_refines
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (op : F64BinaryOp) (rounding : DirectedRounding)
    (dst leftReg rightReg : Reg .f64) (left right : Real)
    (hleft : state.f64.read leftReg.index = some (.finite left))
    (hright : state.f64.read rightReg.index = some (.finite right)) :
    executeInstruction module parameters thread
        (.binaryF64 op rounding dst leftReg rightReg) state =
      some ((state.writeF64 dst
        (F64Value.ofExt
          (evalFinite (BinaryOp.ofTyped op) (RoundingMode.ofTyped rounding)
            left right))).advance) := by
  simp [executeInstruction, hleft, hright, directedBinary_finite_refines]

/-- A typed `min.f64` machine step agrees with the pinned non-NaN semantics. -/
theorem executeInstruction_minimumF64_nonNaN_refines
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (dst leftReg rightReg : Reg .f64)
    (left right : F64Value)
    (hleft : state.f64.read leftReg.index = some left)
    (hright : state.f64.read rightReg.index = some right) :
    executeInstruction module parameters thread
        (.minimumF64 dst leftReg rightReg) state =
      some ((state.writeF64 dst
        (minimum (NumericValue.ofModel left) (NumericValue.ofModel right)).toModel).advance) := by
  simp [executeInstruction, hleft, hright, minimum_nonNaN_refines]

/-- A typed `max.f64` machine step agrees with the pinned non-NaN semantics. -/
theorem executeInstruction_maximumF64_nonNaN_refines
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (dst leftReg rightReg : Reg .f64)
    (left right : F64Value)
    (hleft : state.f64.read leftReg.index = some left)
    (hright : state.f64.read rightReg.index = some right) :
    executeInstruction module parameters thread
        (.maximumF64 dst leftReg rightReg) state =
      some ((state.writeF64 dst
        (maximum (NumericValue.ofModel left) (NumericValue.ofModel right)).toModel).advance) := by
  simp [executeInstruction, hleft, hright, maximum_nonNaN_refines]

/-- Partial PTX-source evidence for an actual compiler-produced module.

This bundles the emitted directive prefix, primary clause coverage for the
opcode trace, and the finite/non-NaN arithmetic equalities proved here.  It
does not give semantics to the structural, memory, or control opcodes, does not
prove that rendered instruction text has the cited meaning, and is not a PTX,
toolchain, SASS, driver, or hardware conformance theorem. -/
structure GeneratedModulePartialPTX90Evidence (batch : ReferenceBatch) : Prop where
  emitterProfile :
    (renderUnchecked (buildModule batch)).startsWith
      dgxSparkProfile.directivePrefix = true
  opcodeCitations :
    ∀ {opcode : Opcode}, opcode ∈ opcodeTrace (buildModule batch).body ->
      ∃ clause, opcodeClause opcode = clause ∧ clause.reference.source = sourcePin
  directedArithmetic :
    ∀ (op : F64BinaryOp) (rounding : DirectedRounding) (left right : Real),
      directedBinary op rounding (.finite left) (.finite right) =
        some (F64Value.ofExt
          (evalFinite (BinaryOp.ofTyped op) (RoundingMode.ofTyped rounding)
            left right))
  minimumReduction :
    ∀ left right : F64Value,
      F64Value.minimum left right =
        (minimum (NumericValue.ofModel left) (NumericValue.ofModel right)).toModel
  maximumReduction :
    ∀ left right : F64Value,
      F64Value.maximum left right =
        (maximum (NumericValue.ofModel left) (NumericValue.ofModel right)).toModel

/-- The generated module carries the partial PTX-source evidence above. -/
theorem buildModule_has_partial_ptx90_evidence (batch : ReferenceBatch) :
    GeneratedModulePartialPTX90Evidence batch := by
  refine {
    emitterProfile := renderUnchecked_startsWith_dgxSparkProfile _
    opcodeCitations := ?_
    directedArithmetic := directedBinary_finite_refines
    minimumReduction := minimum_nonNaN_refines
    maximumReduction := maximum_nonNaN_refines
  }
  intro opcode hopcode
  exact buildModule_opcodeTrace_all_have_pinned_clauses batch hopcode

/-- Target-parameterized partial PTX-source evidence.  This makes the same
limited arithmetic/citation statement for both the DGX `sm_121` and H100
`sm_90` renderings; it still does not cross the PTX-to-hardware boundary. -/
structure GeneratedModulePartialPTX90EvidenceFor
    (target : EmitterTarget) (batch : ReferenceBatch) : Prop where
  emitterProfile :
    (renderUncheckedFor target (buildModule batch)).startsWith
      (emitterModuleProfile target).directivePrefix = true
  opcodeCitations :
    ∀ {opcode : Opcode}, opcode ∈ opcodeTrace (buildModule batch).body ->
      ∃ clause, opcodeClause opcode = clause ∧ clause.reference.source = sourcePin
  directedArithmetic :
    ∀ (op : F64BinaryOp) (rounding : DirectedRounding) (left right : Real),
      directedBinary op rounding (.finite left) (.finite right) =
        some (F64Value.ofExt
          (evalFinite (BinaryOp.ofTyped op) (RoundingMode.ofTyped rounding)
            left right))
  minimumReduction :
    ∀ left right : F64Value,
      F64Value.minimum left right =
        (minimum (NumericValue.ofModel left) (NumericValue.ofModel right)).toModel
  maximumReduction :
    ∀ left right : F64Value,
      F64Value.maximum left right =
        (maximum (NumericValue.ofModel left) (NumericValue.ofModel right)).toModel

/-- Every target-specific rendering of a compiler-produced module carries the
proved partial PTX 9.0 evidence. -/
theorem buildModule_has_partial_ptx90_evidenceFor
    (target : EmitterTarget) (batch : ReferenceBatch) :
    GeneratedModulePartialPTX90EvidenceFor target batch := by
  refine {
    emitterProfile := renderUncheckedFor_startsWith_emitterModuleProfile target _
    opcodeCitations := ?_
    directedArithmetic := directedBinary_finite_refines
    minimumReduction := minimum_nonNaN_refines
    maximumReduction := maximum_nonNaN_refines
  }
  intro opcode hopcode
  exact buildModule_opcodeTrace_all_have_pinned_clauses batch hopcode

end SparkInterval.PTX.NvidiaPTX90
