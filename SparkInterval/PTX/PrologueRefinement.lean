import SparkInterval.PTX.CodeComposition
import SparkInterval.PTX.Generator

/-!
# Production prologue refinement

This file exposes the exact register allocation and instruction slice produced
by `emitPrologue`, then gives an operational refinement of that slice.  The
theorems use the production generator definitions directly: changing an
operand, allocation order, or instruction order in `emitPrologue` invalidates
the structural equality proved below.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- The exact typed registers allocated by one call to `emitPrologue`. -/
structure PrologueRegisters where
  ctaid : Reg .u32
  ntid : Reg .u32
  tid : Reg .u32
  blockBase : Reg .u64
  tid64 : Reg .u64
  rowIndex : Reg .u64
  rowCount : Reg .u64
  outOfRange : Reg .pred
  rowsParameter : Reg .u64
  outputsParameter : Reg .u64
  rowsGlobal : Reg .u64
  outputsGlobal : Reg .u64
  rowOffset : Reg .u64
  rowBase : Reg .u64
  outputOffset : Reg .u64
  outputBase : Reg .u64
  deriving Repr, Inhabited

/-- Register indices selected by `emitPrologue` from an arbitrary builder. -/
def prologueRegisters (builder : Builder) : PrologueRegisters := {
  ctaid := ⟨builder.nextU32⟩
  ntid := ⟨builder.nextU32 + 1⟩
  tid := ⟨builder.nextU32 + 2⟩
  blockBase := ⟨builder.nextU64⟩
  tid64 := ⟨builder.nextU64 + 1⟩
  rowIndex := ⟨builder.nextU64 + 2⟩
  rowCount := ⟨builder.nextU64 + 3⟩
  outOfRange := ⟨builder.nextPred⟩
  rowsParameter := ⟨builder.nextU64 + 4⟩
  outputsParameter := ⟨builder.nextU64 + 5⟩
  rowsGlobal := ⟨builder.nextU64 + 6⟩
  outputsGlobal := ⟨builder.nextU64 + 7⟩
  rowOffset := ⟨builder.nextU64 + 8⟩
  rowBase := ⟨builder.nextU64 + 9⟩
  outputOffset := ⟨builder.nextU64 + 10⟩
  outputBase := ⟨builder.nextU64 + 11⟩
}

/-- The exact 17-instruction production prologue, with concrete operands. -/
def prologueInstructions (variableCount : Nat) (builder : Builder) :
    Array Instruction :=
  let registers := prologueRegisters builder
  #[.movSpecialU32 registers.ctaid .ctaidX,
    .movSpecialU32 registers.ntid .ntidX,
    .mulWideU32 registers.blockBase registers.ctaid registers.ntid,
    .movSpecialU32 registers.tid .tidX,
    .cvtU64U32 registers.tid64 registers.tid,
    .addU64 registers.rowIndex registers.blockBase registers.tid64,
    .loadParamU64 registers.rowCount .rowCount,
    .setpGeU64 registers.outOfRange registers.rowIndex registers.rowCount,
    .branchIf registers.outOfRange doneLabel,
    .loadParamU64 registers.rowsParameter .rows,
    .loadParamU64 registers.outputsParameter .outputs,
    .cvtaGlobalU64 registers.rowsGlobal registers.rowsParameter,
    .cvtaGlobalU64 registers.outputsGlobal registers.outputsParameter,
    .mulLoU64Immediate registers.rowOffset registers.rowIndex (variableCount * 16),
    .addU64 registers.rowBase registers.rowsGlobal registers.rowOffset,
    .mulLoU64Immediate registers.outputOffset registers.rowIndex 24,
    .addU64 registers.outputBase registers.outputsGlobal registers.outputOffset]

/-- The row address computed by the modeled prologue, including u64 wrapping. -/
def prologueRowBase (parameters : KernelParameters) (thread : ThreadContext)
    (variableCount : Nat) : Nat :=
  wrapU64 (parameters.read .rows +
    wrapU64 (thread.globalIndex * (variableCount * 16)))

/-- The output-record address computed by the modeled prologue. -/
def prologueOutputBase (parameters : KernelParameters) (thread : ThreadContext) :
    Nat :=
  wrapU64 (parameters.read .outputs + wrapU64 (thread.globalIndex * 24))

@[simp] private theorem wrapU32_threadRead (thread : ThreadContext)
    (source : SpecialU32) :
    wrapU32 (thread.read source) = thread.read source := by
  cases source <;> simp [ThreadContext.read, wrapU32]

@[simp] private theorem wrapU64_parameterRead (parameters : KernelParameters)
    (parameter : ParameterU64) :
    wrapU64 (parameters.read parameter) = parameters.read parameter := by
  cases parameter <;> simp [KernelParameters.read, wrapU64]

@[simp] private theorem wrapU64_threadRead (thread : ThreadContext)
    (source : SpecialU32) :
    wrapU64 (thread.read source) = thread.read source := by
  cases source <;> unfold ThreadContext.read <;>
    apply wrapU64_eq_of_lt <;>
    exact Nat.lt_trans (Nat.mod_lt _ (by norm_num)) (by norm_num)

private theorem wrappedThreadIndex_eq (thread : ThreadContext) :
    wrapU64
        (wrapU64 (thread.read .ctaidX * thread.read .ntidX) +
          thread.read .tidX) =
      thread.globalIndex := by
  simp [ThreadContext.globalIndex, wrapU64, Nat.add_mod]

/-- `emitPrologue` allocates the exposed registers, appends exactly the exposed
instruction array, and changes only the register counters it consumes. -/
theorem emitPrologue_exact (variableCount : Nat) (builder : Builder) :
    let registers := prologueRegisters builder
    let result := emitPrologue variableCount builder
    result.rowBase = registers.rowBase ∧
      result.outputBase = registers.outputBase ∧
      result.builder.body = builder.body ++ prologueInstructions variableCount builder ∧
      result.builder.nextPred = builder.nextPred + 1 ∧
      result.builder.nextByte = builder.nextByte ∧
      result.builder.nextU32 = builder.nextU32 + 3 ∧
      result.builder.nextU64 = builder.nextU64 + 12 ∧
      result.builder.nextF64 = builder.nextF64 := by
  simp [emitPrologue, prologueRegisters, prologueInstructions,
    Builder.freshPred, Builder.freshU32, Builder.freshU64, Builder.emit,
    Array.push]

/-- An index at or beyond the wrapped row count takes the production
`doneLabel` branch.  The returned state records both the computed index and
the true comparison predicate at the point of the jump. -/
theorem executePrologue_outOfRange
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (variableCount : Nat) (builder : Builder)
    (hout : parameters.read .rowCount ≤ thread.globalIndex) :
    let registers := prologueRegisters builder
    ∃ final,
      executeCode module parameters thread
          (prologueInstructions variableCount builder).toList state =
        some { control := .jump doneLabel, state := final } ∧
      final.u64.read registers.rowIndex.index = some thread.globalIndex ∧
      final.pred.read registers.outOfRange.index = some true := by
  simp [prologueInstructions, prologueRegisters, executeCode,
    executeInstruction, MachineState.writeU32, MachineState.writeU64,
    MachineState.writePred, MachineState.advance, RegisterFile.read,
    RegisterFile.write, wrappedThreadIndex_eq, hout]

/-- An index below the wrapped row count falls through the whole production
prologue.  Its public result registers contain the modeled row-major input and
24-byte output-record addresses. -/
theorem executePrologue_inRange
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (variableCount : Nat) (builder : Builder)
    (hin : thread.globalIndex < parameters.read .rowCount) :
    let registers := prologueRegisters builder
    ∃ final,
      executeCode module parameters thread
          (prologueInstructions variableCount builder).toList state =
        some { control := .fallthrough, state := final } ∧
      final.u64.read registers.rowIndex.index = some thread.globalIndex ∧
      final.u64.read registers.rowBase.index =
        some (prologueRowBase parameters thread variableCount) ∧
      final.u64.read registers.outputBase.index =
        some (prologueOutputBase parameters thread) ∧
      final.pred.read registers.outOfRange.index = some false := by
  simp [prologueInstructions, prologueRegisters, executeCode,
    executeInstruction, MachineState.writeU32, MachineState.writeU64,
    MachineState.writePred, MachineState.advance, RegisterFile.read,
    RegisterFile.write, wrappedThreadIndex_eq, prologueRowBase,
    prologueOutputBase, Nat.not_le.mpr hin]

/-- Layout bounds remove every u64 wrap from the in-range row address. -/
theorem prologueRowBase_eq_of_safeLayout
    (parameters : KernelParameters) (thread : ThreadContext)
    (variableCount : Nat)
    (hlayout : SafeKernelLayout parameters variableCount)
    (hin : thread.globalIndex < parameters.rowCount) :
    prologueRowBase parameters thread variableCount =
      parameters.rows + thread.globalIndex * (variableCount * 16) := by
  rcases hlayout with
    ⟨hrows, _, _, hrowOffsets, _, hrowAddresses, _, _⟩
  have hoffsetLe :
      thread.globalIndex * (variableCount * 16) ≤
        parameters.rowCount * (variableCount * 16) :=
    Nat.mul_le_mul_right _ (Nat.le_of_lt hin)
  have hoffset :
      thread.globalIndex * (variableCount * 16) < 2 ^ 64 :=
    Nat.lt_of_le_of_lt hoffsetLe hrowOffsets
  have haddress :
      parameters.rows + thread.globalIndex * (variableCount * 16) < 2 ^ 64 :=
    Nat.lt_of_le_of_lt (Nat.add_le_add_left hoffsetLe parameters.rows)
      hrowAddresses
  simp [prologueRowBase, KernelParameters.read, wrapU64_eq_of_lt hrows,
    wrapU64_eq_of_lt hoffset, wrapU64_eq_of_lt haddress]

/-- Layout bounds remove every u64 wrap from the in-range output address. -/
theorem prologueOutputBase_eq_of_safeLayout
    (parameters : KernelParameters) (thread : ThreadContext)
    (variableCount : Nat)
    (hlayout : SafeKernelLayout parameters variableCount)
    (hin : thread.globalIndex < parameters.rowCount) :
    prologueOutputBase parameters thread =
      parameters.outputs + thread.globalIndex * 24 := by
  rcases hlayout with
    ⟨_, houtputs, _, _, houtputOffsets, _, houtputAddresses, _⟩
  have hoffsetLe :
      thread.globalIndex * 24 ≤ parameters.rowCount * 24 :=
    Nat.mul_le_mul_right _ (Nat.le_of_lt hin)
  have hoffset : thread.globalIndex * 24 < 2 ^ 64 :=
    Nat.lt_of_le_of_lt hoffsetLe houtputOffsets
  have haddress :
      parameters.outputs + thread.globalIndex * 24 < 2 ^ 64 :=
    Nat.lt_of_le_of_lt (Nat.add_le_add_left hoffsetLe parameters.outputs)
      houtputAddresses
  simp [prologueOutputBase, KernelParameters.read, wrapU64_eq_of_lt houtputs,
    wrapU64_eq_of_lt hoffset, wrapU64_eq_of_lt haddress]

/-- Under the repository's thread and layout safety hypotheses, an ordinary
natural-number in-range index falls through and yields ordinary (unwrapped)
row-major addresses. -/
theorem executePrologue_inRange_exactNat
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (variableCount : Nat) (builder : Builder)
    (hthread : thread.Safe)
    (hlayout : SafeKernelLayout parameters variableCount)
    (hin : thread.ctaidX * thread.ntidX + thread.tidX < parameters.rowCount) :
    let registers := prologueRegisters builder
    let index := thread.ctaidX * thread.ntidX + thread.tidX
    ∃ final,
      executeCode module parameters thread
          (prologueInstructions variableCount builder).toList state =
        some { control := .fallthrough, state := final } ∧
      final.u64.read registers.rowIndex.index = some index ∧
      final.u64.read registers.rowBase.index =
        some (parameters.rows + index * (variableCount * 16)) ∧
      final.u64.read registers.outputBase.index =
        some (parameters.outputs + index * 24) ∧
      final.pred.read registers.outOfRange.index = some false := by
  have hindex := ThreadContext.globalIndex_eq thread hthread
  have hrowCount : parameters.read .rowCount = parameters.rowCount := by
    rcases hlayout with ⟨_, _, hrowCount, _⟩
    exact wrapU64_eq_of_lt hrowCount
  have hinWrapped : thread.globalIndex < parameters.read .rowCount := by
    simpa [hindex, hrowCount] using hin
  rcases executePrologue_inRange module parameters thread state variableCount
      builder hinWrapped with
    ⟨final, hexecute, hrowIndex, hrowBase, houtputBase, houtOfRange⟩
  have hrowAddress :=
    prologueRowBase_eq_of_safeLayout parameters thread variableCount hlayout
      (by simpa [hindex] using hin)
  have houtputAddress :=
    prologueOutputBase_eq_of_safeLayout parameters thread variableCount hlayout
      (by simpa [hindex] using hin)
  refine ⟨final, hexecute, ?_, ?_, ?_, houtOfRange⟩
  · simpa [hindex] using hrowIndex
  · simpa [hindex, hrowAddress] using hrowBase
  · simpa [hindex, houtputAddress] using houtputBase

end SparkInterval.PTX
