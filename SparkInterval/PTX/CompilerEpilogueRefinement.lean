import SparkInterval.PTX.CompilerOutputRefinement
import SparkInterval.PTX.CodeComposition
import SparkInterval.PTX.F64RegisterEffects

/-!
# Concrete generated-epilogue refinement

This module exposes the exact registers and instruction slices selected by
`emitEpilogue`.  It then composes the output-record refinement with the
structured code semantics for the normal and shared whole-interval paths.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- Status byte emitted after ordinary expression fallthrough. -/
def epilogueOkStatus : Fin 256 := ⟨0, by decide⟩

/-- Status byte emitted by the shared nonfinite path. -/
def epilogueNonfiniteStatus : Fin 256 := ⟨2, by decide⟩

/-- Every register allocated directly by `emitEpilogue`. -/
structure EpilogueCompilerRegisters where
  normalStatus : Reg .byte
  normalZero : Reg .byte
  negativeInfinity : Reg .f64
  positiveInfinity : Reg .f64
  wholeStatus : Reg .byte
  wholeZero : Reg .byte
  deriving Repr, Inhabited

/-- Exact register allocation selected from the incoming compiler frontiers. -/
def epilogueCompilerRegisters (builder : Builder) :
    EpilogueCompilerRegisters := {
  normalStatus := ⟨builder.nextByte⟩
  normalZero := ⟨builder.nextByte + 1⟩
  negativeInfinity := ⟨builder.nextF64⟩
  positiveInfinity := ⟨builder.nextF64 + 1⟩
  wholeStatus := ⟨builder.nextByte + 2⟩
  wholeZero := ⟨builder.nextByte + 3⟩
}

def EpilogueCompilerRegisters.whole
    (registers : EpilogueCompilerRegisters) : IntervalRegisters := {
  lo := registers.negativeInfinity
  hi := registers.positiveInfinity
}

/-- A proof-facing builder used only to select the second output slice's byte
registers.  `compiledOutputInstructions` consults `nextByte` and no other
field of this value. -/
def epilogueWholeOutputSeed (builder : Builder) : Builder :=
  { builder with nextByte := builder.nextByte + 2 }

/-- The ordinary-result output record followed by its branch to `doneLabel`. -/
def compiledNormalEpiloguePrefix (outputBase : Reg .u64)
    (result : IntervalRegisters) (builder : Builder) : List Instruction :=
  compiledOutputInstructions outputBase result epilogueOkStatus builder ++
    [.branch doneLabel]

/-- Label and raw-bit moves that materialize the two whole-interval endpoints. -/
def compiledWholeMaterialization (builder : Builder) : List Instruction :=
  let registers := epilogueCompilerRegisters builder
  [.label wholeLabel,
   .movF64Bits registers.negativeInfinity 0xfff0000000000000,
   .movF64Bits registers.positiveInfinity 0x7ff0000000000000]

/-- The common done label and return at the end of the generated kernel. -/
def compiledEpilogueReturnTail : List Instruction :=
  [.label doneLabel, .ret]

/-- The shared whole-interval label, infinity materialization, status-2 output
record, done label, and return. -/
def compiledWholeEpilogueSuffix (outputBase : Reg .u64)
    (builder : Builder) : List Instruction :=
  let registers := epilogueCompilerRegisters builder
  compiledWholeMaterialization builder ++
  compiledOutputInstructions outputBase registers.whole
    epilogueNonfiniteStatus (epilogueWholeOutputSeed builder) ++
  compiledEpilogueReturnTail

/-- The exact thirty-instruction slice appended by `emitEpilogue`. -/
def compiledEpilogueInstructions (outputBase : Reg .u64)
    (result : IntervalRegisters) (builder : Builder) : List Instruction :=
  compiledNormalEpiloguePrefix outputBase result builder ++
    compiledWholeEpilogueSuffix outputBase builder

theorem epilogueCompilerRegisters_indices (builder : Builder) :
    let registers := epilogueCompilerRegisters builder
    registers.normalStatus.index = builder.nextByte ∧
      registers.normalZero.index = builder.nextByte + 1 ∧
      registers.negativeInfinity.index = builder.nextF64 ∧
      registers.positiveInfinity.index = builder.nextF64 + 1 ∧
      registers.wholeStatus.index = builder.nextByte + 2 ∧
      registers.wholeZero.index = builder.nextByte + 3 := by
  simp [epilogueCompilerRegisters]

/-- The output-slice register selectors agree exactly with the registers
exposed above for both output records. -/
theorem epilogue_outputCompilerRegisters (builder : Builder) :
    outputCompilerRegisters builder = {
      status := (epilogueCompilerRegisters builder).normalStatus
      zero := (epilogueCompilerRegisters builder).normalZero
    } ∧
    outputCompilerRegisters (epilogueWholeOutputSeed builder) = {
      status := (epilogueCompilerRegisters builder).wholeStatus
      zero := (epilogueCompilerRegisters builder).wholeZero
    } := by
  constructor <;>
    simp [outputCompilerRegisters, epilogueCompilerRegisters,
      epilogueWholeOutputSeed]

private theorem foldOutputReserved_nextF64 (indices : List Nat)
    (outputBase : Reg .u64) (zero : Reg .byte) (builder : Builder) :
    (indices.foldl (fun next index =>
      next.emit (.storeGlobalByte outputBase (17 + index) zero))
      builder).nextF64 = builder.nextF64 := by
  induction indices generalizing builder with
  | nil => rfl
  | cons index rest induction =>
      rw [List.foldl_cons, induction]
      rfl

private theorem foldOutputReserved_nextPred (indices : List Nat)
    (outputBase : Reg .u64) (zero : Reg .byte) (builder : Builder) :
    (indices.foldl (fun next index =>
      next.emit (.storeGlobalByte outputBase (17 + index) zero))
      builder).nextPred = builder.nextPred := by
  induction indices generalizing builder with
  | nil => rfl
  | cons index rest induction =>
      rw [List.foldl_cons, induction]
      rfl

private theorem foldOutputReserved_nextU32 (indices : List Nat)
    (outputBase : Reg .u64) (zero : Reg .byte) (builder : Builder) :
    (indices.foldl (fun next index =>
      next.emit (.storeGlobalByte outputBase (17 + index) zero))
      builder).nextU32 = builder.nextU32 := by
  induction indices generalizing builder with
  | nil => rfl
  | cons index rest induction =>
      rw [List.foldl_cons, induction]
      rfl

private theorem foldOutputReserved_nextU64 (indices : List Nat)
    (outputBase : Reg .u64) (zero : Reg .byte) (builder : Builder) :
    (indices.foldl (fun next index =>
      next.emit (.storeGlobalByte outputBase (17 + index) zero))
      builder).nextU64 = builder.nextU64 := by
  induction indices generalizing builder with
  | nil => rfl
  | cons index rest induction =>
      rw [List.foldl_cons, induction]
      rfl

@[simp] private theorem emitOutput_nextF64 (outputBase : Reg .u64)
    (result : IntervalRegisters) (status : Fin 256) (builder : Builder) :
    (emitOutput outputBase result status builder).nextF64 = builder.nextF64 := by
  unfold emitOutput
  rw [foldOutputReserved_nextF64]
  rfl

@[simp] private theorem emitOutput_nextPred (outputBase : Reg .u64)
    (result : IntervalRegisters) (status : Fin 256) (builder : Builder) :
    (emitOutput outputBase result status builder).nextPred = builder.nextPred := by
  unfold emitOutput
  rw [foldOutputReserved_nextPred]
  rfl

@[simp] private theorem emitOutput_nextU32 (outputBase : Reg .u64)
    (result : IntervalRegisters) (status : Fin 256) (builder : Builder) :
    (emitOutput outputBase result status builder).nextU32 = builder.nextU32 := by
  unfold emitOutput
  rw [foldOutputReserved_nextU32]
  rfl

@[simp] private theorem emitOutput_nextU64 (outputBase : Reg .u64)
    (result : IntervalRegisters) (status : Fin 256) (builder : Builder) :
    (emitOutput outputBase result status builder).nextU64 = builder.nextU64 := by
  unfold emitOutput
  rw [foldOutputReserved_nextU64]
  rfl

@[simp] private theorem Builder.emit_nextByte_epilogue (builder : Builder)
    (instruction : Instruction) :
    (builder.emit instruction).nextByte = builder.nextByte := rfl

@[simp] private theorem Builder.freshF64_nextByte (builder : Builder) :
    builder.freshF64.2.nextByte = builder.nextByte := rfl

@[simp] theorem emitEpilogue_nextByte (outputBase : Reg .u64)
    (result : IntervalRegisters) (builder : Builder) :
    (emitEpilogue outputBase result builder).nextByte =
      builder.nextByte + 4 := by
  simp [emitEpilogue]

@[simp] theorem emitEpilogue_nextF64 (outputBase : Reg .u64)
    (result : IntervalRegisters) (builder : Builder) :
    (emitEpilogue outputBase result builder).nextF64 =
      builder.nextF64 + 2 := by
  simp [emitEpilogue, emitOutput_nextF64, Builder.freshF64, Builder.emit]

/-- Complete register-frontier effect of the production epilogue.  It
allocates only the four exposed byte registers and two exposed f64 registers. -/
theorem emitEpilogue_registerFrontiers (outputBase : Reg .u64)
    (result : IntervalRegisters) (builder : Builder) :
    (emitEpilogue outputBase result builder).nextPred = builder.nextPred ∧
      (emitEpilogue outputBase result builder).nextByte =
        builder.nextByte + 4 ∧
      (emitEpilogue outputBase result builder).nextU32 = builder.nextU32 ∧
      (emitEpilogue outputBase result builder).nextU64 = builder.nextU64 ∧
      (emitEpilogue outputBase result builder).nextF64 =
        builder.nextF64 + 2 := by
  simp [emitEpilogue, Builder.freshF64, Builder.emit]

@[simp] theorem compiledNormalEpiloguePrefix_length (outputBase : Reg .u64)
    (result : IntervalRegisters) (builder : Builder) :
    (compiledNormalEpiloguePrefix outputBase result builder).length = 13 := by
  simp [compiledNormalEpiloguePrefix]

@[simp] theorem compiledWholeEpilogueSuffix_length (outputBase : Reg .u64)
    (builder : Builder) :
    (compiledWholeEpilogueSuffix outputBase builder).length = 17 := by
  simp [compiledWholeEpilogueSuffix, compiledWholeMaterialization,
    compiledEpilogueReturnTail]

@[simp] theorem compiledEpilogueInstructions_length (outputBase : Reg .u64)
    (result : IntervalRegisters) (builder : Builder) :
    (compiledEpilogueInstructions outputBase result builder).length = 30 := by
  simp [compiledEpilogueInstructions]

/-- Production `emitEpilogue` appends exactly the exposed instruction slice. -/
theorem emitEpilogue_body (outputBase : Reg .u64)
    (result : IntervalRegisters) (builder : Builder) :
    (emitEpilogue outputBase result builder).body =
      builder.body ++
        (compiledEpilogueInstructions outputBase result builder).toArray := by
  rw [← Array.toList_inj]
  simp [emitEpilogue, emitOutput_body, compiledEpilogueInstructions,
    compiledNormalEpiloguePrefix, compiledWholeEpilogueSuffix,
    compiledWholeMaterialization, compiledEpilogueReturnTail,
    compiledOutputInstructions, outputCompilerRegisters,
    epilogueOkStatus, epilogueNonfiniteStatus,
    epilogueCompilerRegisters, EpilogueCompilerRegisters.whole,
    epilogueWholeOutputSeed,
    Builder.freshF64, Builder.emit, List.append_assoc]

/-- The exact epilogue adds thirty typed instructions. -/
theorem emitEpilogue_body_size (outputBase : Reg .u64)
    (result : IntervalRegisters) (builder : Builder) :
    (emitEpilogue outputBase result builder).body.size =
      builder.body.size + 30 := by
  rw [emitEpilogue_body, Array.size_append]
  simp

theorem decodeEpilogueNegativeInfinity :
    decodeF64Bits 0xfff0000000000000 = some .negInf := by
  rw [decodeF64Bits_of_infinite _ (by decide)]
  norm_num [Binary64Bits.signBit, Binary64Bits.signThreshold]

theorem decodeEpiloguePositiveInfinity :
    decodeF64Bits 0x7ff0000000000000 = some .posInf := by
  rw [decodeF64Bits_of_infinite _ (by decide)]
  norm_num [Binary64Bits.signBit, Binary64Bits.signThreshold]

/-- Execute the label and two raw-bit moves which initialize the concrete
whole-interval registers.  Unrelated output-address state and memory are
preserved. -/
theorem executeCompiledWholeMaterialization
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (outputBase : Reg .u64) (builder : Builder) :
    let registers := epilogueCompilerRegisters builder
    ∃ final,
      executeCode module parameters thread
          (compiledWholeMaterialization builder) state =
        some { control := .fallthrough, state := final } ∧
      final.u64.read outputBase.index = state.u64.read outputBase.index ∧
      final.f64.read registers.negativeInfinity.index = some .negInf ∧
      final.f64.read registers.positiveInfinity.index = some .posInf ∧
      final.memory = state.memory := by
  let registers := epilogueCompilerRegisters builder
  let afterLabel : MachineState := { state with pc := state.pc + 1 }
  let afterNegative :=
    (afterLabel.writeF64 registers.negativeInfinity .negInf).advance
  let final :=
    (afterNegative.writeF64 registers.positiveInfinity .posInf).advance
  refine ⟨final, ?_, ?_, ?_, ?_, ?_⟩
  · simp [compiledWholeMaterialization, executeCode, executeInstruction,
      decodeEpilogueNegativeInfinity, decodeEpiloguePositiveInfinity,
      registers, afterLabel, afterNegative, final]
  · rfl
  · simp [final, afterNegative, MachineState.advance,
      MachineState.writeF64, RegisterFile.read, RegisterFile.write,
      registers, epilogueCompilerRegisters]
  · change (afterNegative.f64.write registers.positiveInfinity.index
      F64Value.posInf).read registers.positiveInfinity.index =
        some F64Value.posInf
    simp
  · rfl

/-- The ordinary path emits a complete status-zero record and then reports
the production branch to `doneLabel`. -/
theorem executeCompiledNormalEpiloguePrefix
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (outputBase : Reg .u64)
    (result : IntervalRegisters) (builder : Builder)
    (base : Nat) (interval : F64Interval)
    (hbase : state.u64.read outputBase.index = some base)
    (hlo : state.f64.read result.lo.index = some interval.lo)
    (hhi : state.f64.read result.hi.index = some interval.hi) :
    ∃ final,
      executeCode module parameters thread
          (compiledNormalEpiloguePrefix outputBase result builder) state =
        some { control := .jump doneLabel, state := final } ∧
      final.memory =
        writeOutputMemory state.memory base interval epilogueOkStatus := by
  rcases executeCompiledOutput module parameters thread state outputBase result
    epilogueOkStatus builder base interval hbase hlo hhi with
    ⟨final, houtput, hmemory⟩
  refine ⟨final, ?_, hmemory⟩
  unfold compiledNormalEpiloguePrefix
  rw [executeCode_append_fallthrough module parameters thread _ _ _ _ houtput]
  rfl

/-- Under the within-record address bound, the ordinary path leaves every ABI
cell observable before taking its branch to `doneLabel`. -/
theorem executeCompiledNormalEpiloguePrefix_contains
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (outputBase : Reg .u64)
    (result : IntervalRegisters) (builder : Builder)
    (base : Nat) (interval : F64Interval)
    (hbase : state.u64.read outputBase.index = some base)
    (hlo : state.f64.read result.lo.index = some interval.lo)
    (hhi : state.f64.read result.hi.index = some interval.hi)
    (hsafe : base + 23 < 2 ^ 64) :
    ∃ final,
      executeCode module parameters thread
          (compiledNormalEpiloguePrefix outputBase result builder) state =
        some { control := .jump doneLabel, state := final } ∧
      MemoryContainsOutputRecord final.memory base interval epilogueOkStatus := by
  rcases executeCompiledNormalEpiloguePrefix module parameters thread state
    outputBase result builder base interval hbase hlo hhi with
    ⟨final, hexecute, hmemory⟩
  refine ⟨final, hexecute, ?_⟩
  rw [hmemory]
  exact writeOutputMemory_contains state.memory base interval
    epilogueOkStatus hsafe

/-- Public-observer form of the normal status-zero path. -/
theorem executeCompiledNormalEpiloguePrefix_observe
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (outputBase : Reg .u64)
    (result : IntervalRegisters) (builder : Builder)
    (base : Nat) (interval : F64Interval)
    (hbase : state.u64.read outputBase.index = some base)
    (hlo : state.f64.read result.lo.index = some interval.lo)
    (hhi : state.f64.read result.hi.index = some interval.hi)
    (hsafe : base + 23 < 2 ^ 64) :
    ∃ final,
      executeCode module parameters thread
          (compiledNormalEpiloguePrefix outputBase result builder) state =
        some { control := .jump doneLabel, state := final } ∧
      observeOutput final.memory base 0 =
        some (expectedObservedOutput interval epilogueOkStatus) := by
  rcases executeCompiledNormalEpiloguePrefix_contains module parameters thread
    state outputBase result builder base interval hbase hlo hhi hsafe with
    ⟨final, hexecute, hrecord⟩
  exact ⟨final, hexecute,
    MemoryContainsOutputRecord.observeOutput final.memory base interval
      epilogueOkStatus hsafe hrecord⟩

/-- Starting at the production whole label, the generated suffix materializes
`[-∞,+∞]`, writes the status-two record (including reserved zeros), and
reaches returned control. -/
theorem executeCompiledWholeEpilogueSuffix
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (outputBase : Reg .u64) (builder : Builder)
    (base : Nat)
    (hbase : state.u64.read outputBase.index = some base) :
    let registers := epilogueCompilerRegisters builder
    ∃ final,
      executeCode module parameters thread
          (compiledWholeEpilogueSuffix outputBase builder) state =
        some { control := .returned, state := final } ∧
      final.f64.read registers.negativeInfinity.index = some .negInf ∧
      final.f64.read registers.positiveInfinity.index = some .posInf ∧
      final.memory = writeOutputMemory state.memory base F64Interval.whole
        epilogueNonfiniteStatus := by
  let registers := epilogueCompilerRegisters builder
  change ∃ final,
    executeCode module parameters thread
        (compiledWholeEpilogueSuffix outputBase builder) state =
      some { control := .returned, state := final } ∧
    final.f64.read registers.negativeInfinity.index = some .negInf ∧
    final.f64.read registers.positiveInfinity.index = some .posInf ∧
    final.memory = writeOutputMemory state.memory base F64Interval.whole
      epilogueNonfiniteStatus
  rcases executeCompiledWholeMaterialization module parameters thread state
    outputBase builder with
    ⟨loaded, hmaterialize, hbasePreserved, hnegative, hpositive,
      hloadMemory⟩
  have hloadedBase : loaded.u64.read outputBase.index = some base :=
    hbasePreserved.trans hbase
  have hloadedNegative :
      loaded.f64.read registers.whole.lo.index =
        some F64Interval.whole.lo := by
    simpa [EpilogueCompilerRegisters.whole, F64Interval.whole] using hnegative
  have hloadedPositive :
      loaded.f64.read registers.whole.hi.index =
        some F64Interval.whole.hi := by
    simpa [EpilogueCompilerRegisters.whole, F64Interval.whole] using hpositive
  rcases executeCompiledOutput module parameters thread loaded outputBase
    registers.whole epilogueNonfiniteStatus
    (epilogueWholeOutputSeed builder) base F64Interval.whole hloadedBase
    hloadedNegative hloadedPositive with ⟨written, houtput, hwriteMemory⟩
  let final : MachineState := {
    written with pc := written.pc + 1, returned := true
  }
  have htail :
      executeCode module parameters thread compiledEpilogueReturnTail written =
        some { control := .returned, state := final } := by
    simp [compiledEpilogueReturnTail, executeCode, final]
  let rest :=
    compiledOutputInstructions outputBase registers.whole
      epilogueNonfiniteStatus (epilogueWholeOutputSeed builder) ++
      compiledEpilogueReturnTail
  have hrest :
      executeCode module parameters thread rest loaded =
        some { control := .returned, state := final } := by
    unfold rest
    rw [executeCode_append_fallthrough module parameters thread _ _ _ _ houtput]
    exact htail
  have hnegativeFresh :
      registers.negativeInfinity.index ∉
        Instruction.f64Destinations rest := by
    simp [rest, compiledOutputInstructions, compiledEpilogueReturnTail,
      Instruction.f64Destination?, Instruction.f64Destinations]
  have hpositiveFresh :
      registers.positiveInfinity.index ∉
        Instruction.f64Destinations rest := by
    simp [rest, compiledOutputInstructions, compiledEpilogueReturnTail,
      Instruction.f64Destination?, Instruction.f64Destinations]
  have hfinalNegative :=
    executeCode_returned_preserves_f64_read module parameters thread rest
      loaded final registers.negativeInfinity.index hnegativeFresh
      hrest
  have hfinalPositive :=
    executeCode_returned_preserves_f64_read module parameters thread rest
      loaded final registers.positiveInfinity.index hpositiveFresh
      hrest
  refine ⟨final, ?_, hfinalNegative.trans hnegative,
    hfinalPositive.trans hpositive, ?_⟩
  · unfold compiledWholeEpilogueSuffix
    change executeCode module parameters thread
      (compiledWholeMaterialization builder ++ rest) state =
        some { control := .returned, state := final }
    rw [executeCode_append_fallthrough module parameters thread _ _ _ _
      hmaterialize]
    exact hrest
  · change written.memory =
      writeOutputMemory state.memory base F64Interval.whole
        epilogueNonfiniteStatus
    rw [hwriteMemory, hloadMemory]

/-- Safe-layout corollary for the returned whole-interval path. -/
theorem executeCompiledWholeEpilogueSuffix_contains
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (outputBase : Reg .u64) (builder : Builder)
    (base : Nat)
    (hbase : state.u64.read outputBase.index = some base)
    (hsafe : base + 23 < 2 ^ 64) :
    let registers := epilogueCompilerRegisters builder
    ∃ final,
      executeCode module parameters thread
          (compiledWholeEpilogueSuffix outputBase builder) state =
        some { control := .returned, state := final } ∧
      final.f64.read registers.negativeInfinity.index = some .negInf ∧
      final.f64.read registers.positiveInfinity.index = some .posInf ∧
      MemoryContainsOutputRecord final.memory base F64Interval.whole
        epilogueNonfiniteStatus := by
  rcases executeCompiledWholeEpilogueSuffix module parameters thread state
    outputBase builder base hbase with
    ⟨final, hexecute, hnegative, hpositive, hmemory⟩
  refine ⟨final, hexecute, hnegative, hpositive, ?_⟩
  rw [hmemory]
  exact writeOutputMemory_contains state.memory base F64Interval.whole
    epilogueNonfiniteStatus hsafe

/-- Public-observer form of the returned status-two whole-interval path. -/
theorem executeCompiledWholeEpilogueSuffix_observe
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (outputBase : Reg .u64) (builder : Builder)
    (base : Nat)
    (hbase : state.u64.read outputBase.index = some base)
    (hsafe : base + 23 < 2 ^ 64) :
    let registers := epilogueCompilerRegisters builder
    ∃ final,
      executeCode module parameters thread
          (compiledWholeEpilogueSuffix outputBase builder) state =
        some { control := .returned, state := final } ∧
      final.f64.read registers.negativeInfinity.index = some .negInf ∧
      final.f64.read registers.positiveInfinity.index = some .posInf ∧
      observeOutput final.memory base 0 = some
        (expectedObservedOutput F64Interval.whole
          epilogueNonfiniteStatus) := by
  rcases executeCompiledWholeEpilogueSuffix_contains module parameters thread
    state outputBase builder base hbase hsafe with
    ⟨final, hexecute, hnegative, hpositive, hrecord⟩
  exact ⟨final, hexecute, hnegative, hpositive,
    MemoryContainsOutputRecord.observeOutput final.memory base
      F64Interval.whole epilogueNonfiniteStatus hsafe hrecord⟩

/-- `SafeKernelLayout` implies that every in-range row's full 24-byte output
record lies below the u64 address modulus. -/
theorem outputRecordAddress_safe_of_safeKernelLayout
    (parameters : KernelParameters) (variableCount index : Nat)
    (hlayout : SafeKernelLayout parameters variableCount)
    (hindex : index < parameters.rowCount) :
    parameters.outputs + index * 24 + 23 < 2 ^ 64 := by
  rcases hlayout with
    ⟨_, _, _, _, _, _, houtputAddresses, _⟩
  have hnext : index + 1 ≤ parameters.rowCount := by omega
  have hrecords : (index + 1) * 24 ≤ parameters.rowCount * 24 :=
    Nat.mul_le_mul_right 24 hnext
  omega

/-- Full-layout form of the normal epilogue theorem at an in-range row. -/
theorem executeCompiledNormalEpiloguePrefix_safeLayout
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (outputBase : Reg .u64)
    (result : IntervalRegisters) (builder : Builder)
    (variableCount index : Nat) (interval : F64Interval)
    (hbase : state.u64.read outputBase.index =
      some (parameters.outputs + index * 24))
    (hlo : state.f64.read result.lo.index = some interval.lo)
    (hhi : state.f64.read result.hi.index = some interval.hi)
    (hlayout : SafeKernelLayout parameters variableCount)
    (hindex : index < parameters.rowCount) :
    ∃ final,
      executeCode module parameters thread
          (compiledNormalEpiloguePrefix outputBase result builder) state =
        some { control := .jump doneLabel, state := final } ∧
      MemoryContainsOutputRecord final.memory
        (parameters.outputs + index * 24) interval epilogueOkStatus := by
  exact executeCompiledNormalEpiloguePrefix_contains module parameters thread
    state outputBase result builder (parameters.outputs + index * 24) interval
    hbase hlo hhi
    (outputRecordAddress_safe_of_safeKernelLayout parameters variableCount
      index hlayout hindex)

/-- Full-layout form of the returned whole-interval epilogue theorem. -/
theorem executeCompiledWholeEpilogueSuffix_safeLayout
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (outputBase : Reg .u64) (builder : Builder)
    (variableCount index : Nat)
    (hbase : state.u64.read outputBase.index =
      some (parameters.outputs + index * 24))
    (hlayout : SafeKernelLayout parameters variableCount)
    (hindex : index < parameters.rowCount) :
    let registers := epilogueCompilerRegisters builder
    ∃ final,
      executeCode module parameters thread
          (compiledWholeEpilogueSuffix outputBase builder) state =
        some { control := .returned, state := final } ∧
      final.f64.read registers.negativeInfinity.index = some .negInf ∧
      final.f64.read registers.positiveInfinity.index = some .posInf ∧
      MemoryContainsOutputRecord final.memory
        (parameters.outputs + index * 24) F64Interval.whole
          epilogueNonfiniteStatus := by
  exact executeCompiledWholeEpilogueSuffix_contains module parameters thread
    state outputBase builder (parameters.outputs + index * 24) hbase
    (outputRecordAddress_safe_of_safeKernelLayout parameters variableCount
      index hlayout hindex)

end SparkInterval.PTX
