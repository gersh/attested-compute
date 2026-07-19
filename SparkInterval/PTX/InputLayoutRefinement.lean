import SparkInterval.PTX.PrologueRefinement
import SparkInterval.PTX.U64MemoryEffects

/-!
# Row-indexed input-layout refinement

This module connects the public row-major `MemoryEncodesRows` relation to the
single-row address computed by the production prologue.  The resulting
`GlobalMemory.EncodesEnvironmentAt` relation is the input contract consumed by
expression-level load refinement; it does not depend on expression execution.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- One decoded interval environment is present at a computed row-base
address.  Column `i` occupies the two binary64 cells at offsets `16*i` and
`16*i+8`, exactly matching the production variable-load ABI. -/
def GlobalMemory.EncodesEnvironmentAt (memory : GlobalMemory)
    (rowAddress : Nat) (environment : Array F64Interval) : Prop :=
  ∀ column interval,
    environment[column]? = some interval →
    memory.loadF64 (globalAddress rowAddress (column * 16)) =
        some interval.lo ∧
      memory.loadF64 (globalAddress rowAddress (column * 16 + 8)) =
        some interval.hi

/-- Modular global addresses reassociate without any no-wrap premise. -/
theorem globalAddress_reassociate (base first second : Nat) :
    globalAddress (globalAddress base first) second =
      globalAddress base (first + second) := by
  unfold globalAddress wrapU64
  rw [Nat.mod_add_mod, Nat.add_assoc]

/-- Selecting one row from `MemoryEncodesRows` yields the reusable single-row
relation at the modular row address. -/
theorem MemoryEncodesRows.encodesEnvironmentAt_globalAddress
    {memory : GlobalMemory} {rowsBase variableCount row : Nat}
    {rows : Array (Array F64Interval)} {environment : Array F64Interval}
    (hmemory : MemoryEncodesRows memory rowsBase variableCount rows)
    (hrow : rows[row]? = some environment) :
    memory.EncodesEnvironmentAt
      (globalAddress rowsBase (row * (variableCount * 16))) environment := by
  intro column interval hcolumn
  have hcells := hmemory row column environment interval hrow hcolumn
  constructor
  · rw [globalAddress_reassociate]
    exact hcells.1
  · rw [globalAddress_reassociate]
    simpa [Nat.add_assoc] using hcells.2

/-- Under the kernel layout bounds, the modular selected-row relation is at
the ordinary natural-number row address returned by the exact prologue
refinement. -/
theorem MemoryEncodesRows.encodesEnvironmentAt_exactRowAddress
    {memory : GlobalMemory} {parameters : KernelParameters}
    {variableCount row : Nat} {rows : Array (Array F64Interval)}
    {environment : Array F64Interval}
    (hmemory : MemoryEncodesRows memory parameters.rows variableCount rows)
    (hrow : rows[row]? = some environment)
    (hlayout : SafeKernelLayout parameters variableCount)
    (hin : row < parameters.rowCount) :
    memory.EncodesEnvironmentAt
      (parameters.rows + row * (variableCount * 16)) environment := by
  have hoffsetLe :
      row * (variableCount * 16) ≤
        parameters.rowCount * (variableCount * 16) :=
    Nat.mul_le_mul_right _ (Nat.le_of_lt hin)
  have haddress :
      parameters.rows + row * (variableCount * 16) < 2 ^ 64 := by
    rcases hlayout with ⟨_, _, _, _, _, hrowsEnd, _, _⟩
    exact Nat.lt_of_le_of_lt
      (Nat.add_le_add_left hoffsetLe parameters.rows) hrowsEnd
  have hbase :
      globalAddress parameters.rows (row * (variableCount * 16)) =
        parameters.rows + row * (variableCount * 16) :=
    globalAddress_eq_of_lt haddress
  rw [← hbase]
  exact hmemory.encodesEnvironmentAt_globalAddress hrow

/-- The production prologue contains no global-memory store. -/
theorem prologueInstructions_memoryWriteFree (variableCount : Nat)
    (builder : Builder) :
    GlobalMemoryWriteFree (prologueInstructions variableCount builder).toList := by
  simp [GlobalMemoryWriteFree, prologueInstructions, prologueRegisters,
    Instruction.writesGlobalMemory]

/-- An in-range production prologue exposes the selected decoded environment
through its concrete `rowBase` register, while leaving the input memory
unchanged.

This composes the exact natural-number prologue refinement, the row-major
layout bridge, and the shared store-free execution theorem. -/
theorem executePrologue_inRange_exposesEnvironment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (variableCount : Nat) (builder : Builder)
    (rows : Array (Array F64Interval)) (environment : Array F64Interval)
    (hthread : thread.Safe)
    (hlayout : SafeKernelLayout parameters variableCount)
    (hin : thread.ctaidX * thread.ntidX + thread.tidX < parameters.rowCount)
    (hmemory : MemoryEncodesRows state.memory parameters.rows variableCount rows)
    (hrow : rows[thread.ctaidX * thread.ntidX + thread.tidX]? =
      some environment) :
    let registers := prologueRegisters builder
    let index := thread.ctaidX * thread.ntidX + thread.tidX
    let rowAddress := parameters.rows + index * (variableCount * 16)
    ∃ final,
      executeCode module parameters thread
          (prologueInstructions variableCount builder).toList state =
        some { control := .fallthrough, state := final } ∧
      final.u64.read registers.rowBase.index = some rowAddress ∧
      final.memory = state.memory ∧
      final.memory.EncodesEnvironmentAt rowAddress environment := by
  let index := thread.ctaidX * thread.ntidX + thread.tidX
  let rowAddress := parameters.rows + index * (variableCount * 16)
  rcases executePrologue_inRange_exactNat module parameters thread state
      variableCount builder hthread hlayout hin with
    ⟨final, hexecute, _, hrowBase, _, _⟩
  have hmemoryPreserved : final.memory = state.memory :=
    executeCode_preserves_globalMemory module parameters thread
      (prologueInstructions variableCount builder).toList state
      { control := .fallthrough, state := final }
      (prologueInstructions_memoryWriteFree variableCount builder) hexecute
  have henvironment :
      state.memory.EncodesEnvironmentAt rowAddress environment := by
    apply hmemory.encodesEnvironmentAt_exactRowAddress hrow hlayout
    exact hin
  refine ⟨final, hexecute, ?_, hmemoryPreserved, ?_⟩
  · simpa [index, rowAddress] using hrowBase
  · simpa [hmemoryPreserved] using henvironment

end SparkInterval.PTX
