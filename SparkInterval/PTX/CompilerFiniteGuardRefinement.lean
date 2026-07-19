import SparkInterval.PTX.CompilerDataflow
import SparkInterval.PTX.InstructionRefinement

/-!
# Concrete compiler finite-guard refinement

This file exposes the registers selected by the production `emitFiniteGuard`,
proves the exact six instructions appended to the compiler body and the exact
register-frontier changes, and instantiates the instruction-level finite-guard
semantics with those compiler-selected registers.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- Proof-facing names for the four registers allocated by one production
finite guard. -/
structure FiniteGuardCompilerRegisters where
  loExponent : Reg .u64
  hiExponent : Reg .u64
  loNonfinite : Reg .pred
  hiNonfinite : Reg .pred
  deriving Repr, Inhabited

/-- The exact registers selected by `emitFiniteGuard` from its incoming u64
and predicate frontiers. -/
def finiteGuardCompilerRegisters (builder : Builder) :
    FiniteGuardCompilerRegisters := {
  loExponent := ⟨builder.nextU64⟩
  hiExponent := ⟨builder.nextU64 + 1⟩
  loNonfinite := ⟨builder.nextPred⟩
  hiNonfinite := ⟨builder.nextPred + 1⟩
}

/-- The six instructions associated with the concrete compiler-selected guard
registers. -/
def compiledFiniteGuardInstructions (value : IntervalRegisters)
    (builder : Builder) : List Instruction :=
  let registers := finiteGuardCompilerRegisters builder
  finiteGuardInstructions value registers.loExponent registers.hiExponent
    registers.loNonfinite registers.hiNonfinite

/-- Exact indices of all four registers selected by the production guard. -/
theorem finiteGuardCompilerRegisters_indices (builder : Builder) :
    (finiteGuardCompilerRegisters builder).loExponent.index = builder.nextU64 ∧
      (finiteGuardCompilerRegisters builder).hiExponent.index =
        builder.nextU64 + 1 ∧
      (finiteGuardCompilerRegisters builder).loNonfinite.index =
        builder.nextPred ∧
      (finiteGuardCompilerRegisters builder).hiNonfinite.index =
        builder.nextPred + 1 := by
  simp [finiteGuardCompilerRegisters]

/-- The production guard advances the u64 frontier by exactly two. -/
@[simp] theorem emitFiniteGuard_nextU64 (value : IntervalRegisters)
    (builder : Builder) :
    (emitFiniteGuard value builder).nextU64 = builder.nextU64 + 2 := by
  simp [emitFiniteGuard, Builder.freshU64, Builder.freshPred, Builder.emit]

/-- The production guard advances the predicate frontier by exactly two. -/
@[simp] theorem emitFiniteGuard_nextPred (value : IntervalRegisters)
    (builder : Builder) :
    (emitFiniteGuard value builder).nextPred = builder.nextPred + 2 := by
  simp [emitFiniteGuard, Builder.freshU64, Builder.freshPred, Builder.emit]

/-- The production guard appends exactly the six proof-facing instructions to
the existing typed instruction body, in execution order. -/
theorem emitFiniteGuard_body_toList (value : IntervalRegisters)
    (builder : Builder) :
    (emitFiniteGuard value builder).body.toList =
      builder.body.toList ++ compiledFiniteGuardInstructions value builder := by
  simp [emitFiniteGuard, compiledFiniteGuardInstructions,
    finiteGuardCompilerRegisters, finiteGuardInstructions,
    Builder.freshU64, Builder.freshPred, Builder.emit]

/-- Array-level form of `emitFiniteGuard_body_toList`: the production builder
body is literally the incoming body followed by the concrete guard array. -/
theorem emitFiniteGuard_body (value : IntervalRegisters) (builder : Builder) :
    (emitFiniteGuard value builder).body =
      builder.body ++ (compiledFiniteGuardInstructions value builder).toArray := by
  rw [← Array.toList_inj]
  rw [emitFiniteGuard_body_toList, Array.toList_append]

/-- The concrete production guard contains exactly six instructions. -/
@[simp] theorem compiledFiniteGuardInstructions_length
    (value : IntervalRegisters) (builder : Builder) :
    (compiledFiniteGuardInstructions value builder).length = 6 := by
  simp [compiledFiniteGuardInstructions, finiteGuardCompilerRegisters,
    finiteGuardInstructions]

/-- Consequently, `emitFiniteGuard` grows the typed body by exactly six. -/
theorem emitFiniteGuard_body_size (value : IntervalRegisters)
    (builder : Builder) :
    (emitFiniteGuard value builder).body.size = builder.body.size + 6 := by
  rw [emitFiniteGuard_body, Array.size_append]
  simp

/-! ## Concrete execution instantiations -/

/-- A finite interval falls through the exact guard emitted from `builder`. -/
theorem executeCompiledFiniteGuard_fallthrough
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (value : IntervalRegisters) (builder : Builder)
    (lo hi : ℝ)
    (hlo : state.f64.read value.lo.index = some (.finite lo))
    (hhi : state.f64.read value.hi.index = some (.finite hi)) :
    ∃ final,
      executeCode module parameters thread
        (compiledFiniteGuardInstructions value builder) state =
      some { control := .fallthrough, state := final } := by
  let registers := finiteGuardCompilerRegisters builder
  exact executeFiniteGuard_fallthrough module parameters thread state value
    registers.loExponent registers.hiExponent registers.loNonfinite
    registers.hiNonfinite lo hi hlo hhi

/-- A nonfinite lower endpoint jumps to the whole-interval path in the exact
guard emitted from `builder`. -/
theorem executeCompiledFiniteGuard_lowerNonfinite
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (value : IntervalRegisters) (builder : Builder)
    (lo : F64Value) (hloKind : lo = .negInf ∨ lo = .posInf)
    (hlo : state.f64.read value.lo.index = some lo) :
    ∃ final,
      executeCode module parameters thread
        (compiledFiniteGuardInstructions value builder) state =
      some { control := .jump wholeLabel, state := final } := by
  let registers := finiteGuardCompilerRegisters builder
  exact executeFiniteGuard_lowerNonfinite module parameters thread state value
    registers.loExponent registers.hiExponent registers.loNonfinite
    registers.hiNonfinite lo hloKind hlo

/-- With a finite lower endpoint, a nonfinite upper endpoint jumps to the
whole-interval path in the exact guard emitted from `builder`. -/
theorem executeCompiledFiniteGuard_upperNonfinite
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (value : IntervalRegisters) (builder : Builder)
    (lo : ℝ) (hi : F64Value) (hhiKind : hi = .negInf ∨ hi = .posInf)
    (hlo : state.f64.read value.lo.index = some (.finite lo))
    (hhi : state.f64.read value.hi.index = some hi) :
    ∃ final,
      executeCode module parameters thread
        (compiledFiniteGuardInstructions value builder) state =
      some { control := .jump wholeLabel, state := final } := by
  let registers := finiteGuardCompilerRegisters builder
  exact executeFiniteGuard_upperNonfinite module parameters thread state value
    registers.loExponent registers.hiExponent registers.loNonfinite
    registers.hiNonfinite lo hi hhiKind hlo hhi

end SparkInterval.PTX
