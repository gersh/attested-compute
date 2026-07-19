import SparkInterval.PTX.GeneratedModuleSegments
import SparkInterval.PTX.OutputLayoutRefinement

/-!
# Structured execution of one generated in-range row

This module composes the production prologue, the recursive expression
execution theorem, and both generated epilogue paths.  It deliberately uses
`executeCode` slices rather than whole-module `run`: the exact module-body
segments and program counters are supplied by `GeneratedModuleSegments`, and
the subsequent phase can use this theorem to discharge the semantic work
while concentrating on jump resolution and fuel.

The result is entirely compositional.  In particular, expression code is
proved to preserve the prologue's output-base register because all of its u64
destinations are at or above the post-prologue register frontier.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-! ## Canonical status-aware evaluator results -/

/-- Every result that can be emitted by the polynomial evaluator is either a
normal result or the single canonical conservative whole-interval result. -/
def KernelResult.Canonical (result : KernelResult) : Prop :=
  result.status = .ok ∨ result = KernelResult.whole

private theorem guardedBinary_canonical (operation : F64BinaryOp)
    (left right : KernelResult) :
    (guardedBinary operation left right).Canonical := by
  cases hleftStatus : left.status <;> cases hrightStatus : right.status
  · cases hleftBounds : left.interval.finiteBounds? with
    | none =>
        simp [KernelResult.Canonical, guardedBinary, hleftStatus,
          hrightStatus, hleftBounds, KernelResult.whole]
    | some leftBounds =>
        rcases leftBounds with ⟨leftLo, leftHi⟩
        cases hrightBounds : right.interval.finiteBounds? with
        | none =>
            simp [KernelResult.Canonical, guardedBinary, hleftStatus,
              hrightStatus, hleftBounds, hrightBounds, KernelResult.whole]
        | some rightBounds =>
            rcases rightBounds with ⟨rightLo, rightHi⟩
            simp [KernelResult.Canonical, guardedBinary, hleftStatus,
              hrightStatus, hleftBounds, hrightBounds]
  · simp [KernelResult.Canonical, guardedBinary, hleftStatus,
      hrightStatus, KernelResult.whole]
  · simp [KernelResult.Canonical, guardedBinary, hleftStatus,
      hrightStatus, KernelResult.whole]
  · simp [KernelResult.Canonical, guardedBinary, hleftStatus,
      hrightStatus, KernelResult.whole]

private theorem powLoop_canonical (exponent : Nat) (base accumulator : KernelResult)
    (haccumulator : accumulator.Canonical) :
    (powLoop exponent base accumulator).Canonical := by
  induction exponent generalizing accumulator with
  | zero => simpa [powLoop] using haccumulator
  | succ exponent induction =>
      simpa [powLoop] using
        induction (guardedBinary .mul accumulator base)
          (guardedBinary_canonical .mul accumulator base)

/-- A successful source-level kernel evaluation has a canonical status/result
pair.  This is a semantic fact about `evalKernel`, independent of execution. -/
theorem PolynomialExpr.evalKernel_canonical
    (expression : PolynomialExpr) (environment : Array F64Interval)
    (result : KernelResult)
    (heval : expression.evalKernel environment = some result) :
    result.Canonical := by
  cases expression with
  | const value =>
      cases hdecoded : value.decodeF64Interval? with
      | none => simp [PolynomialExpr.evalKernel, hdecoded] at heval
      | some interval =>
          simp [PolynomialExpr.evalKernel, hdecoded] at heval
          subst result
          exact Or.inl rfl
  | var index =>
      cases hget : environment[index]? with
      | none => simp [PolynomialExpr.evalKernel, hget] at heval
      | some interval =>
          simp [PolynomialExpr.evalKernel, hget] at heval
          subst result
          exact Or.inl rfl
  | neg argument =>
      cases hargument : argument.evalKernel environment with
      | none => simp [PolynomialExpr.evalKernel, hargument] at heval
      | some argumentResult =>
          simp [PolynomialExpr.evalKernel, hargument] at heval
          subst result
          cases hstatus : argumentResult.status with
          | ok =>
              exact Or.inl (by simp [KernelResult.negate, hstatus])
          | nonfiniteIntermediate =>
              exact Or.inr (by simp [KernelResult.negate, hstatus])
  | add left right =>
      cases hleft : left.evalKernel environment with
      | none => simp [PolynomialExpr.evalKernel, hleft] at heval
      | some leftResult =>
          cases hstatus : leftResult.status with
          | nonfiniteIntermediate =>
              simp [PolynomialExpr.evalKernel, hleft, hstatus] at heval
              subst result
              exact Or.inr rfl
          | ok =>
              cases hright : right.evalKernel environment with
              | none =>
                  simp [PolynomialExpr.evalKernel, hleft, hstatus, hright] at heval
              | some rightResult =>
                  simp [PolynomialExpr.evalKernel, hleft, hstatus, hright] at heval
                  subst result
                  exact guardedBinary_canonical .add leftResult rightResult
  | sub left right =>
      cases hleft : left.evalKernel environment with
      | none => simp [PolynomialExpr.evalKernel, hleft] at heval
      | some leftResult =>
          cases hstatus : leftResult.status with
          | nonfiniteIntermediate =>
              simp [PolynomialExpr.evalKernel, hleft, hstatus] at heval
              subst result
              exact Or.inr rfl
          | ok =>
              cases hright : right.evalKernel environment with
              | none =>
                  simp [PolynomialExpr.evalKernel, hleft, hstatus, hright] at heval
              | some rightResult =>
                  simp [PolynomialExpr.evalKernel, hleft, hstatus, hright] at heval
                  subst result
                  exact guardedBinary_canonical .sub leftResult rightResult
  | mul left right =>
      cases hleft : left.evalKernel environment with
      | none => simp [PolynomialExpr.evalKernel, hleft] at heval
      | some leftResult =>
          cases hstatus : leftResult.status with
          | nonfiniteIntermediate =>
              simp [PolynomialExpr.evalKernel, hleft, hstatus] at heval
              subst result
              exact Or.inr rfl
          | ok =>
              cases hright : right.evalKernel environment with
              | none =>
                  simp [PolynomialExpr.evalKernel, hleft, hstatus, hright] at heval
              | some rightResult =>
                  simp [PolynomialExpr.evalKernel, hleft, hstatus, hright] at heval
                  subst result
                  exact guardedBinary_canonical .mul leftResult rightResult
  | powNat argument exponent =>
      cases hargument : argument.evalKernel environment with
      | none => simp [PolynomialExpr.evalKernel, hargument] at heval
      | some base =>
          cases hstatus : base.status with
          | nonfiniteIntermediate =>
              simp [PolynomialExpr.evalKernel, hargument, hstatus] at heval
              subst result
              exact Or.inr rfl
          | ok =>
              let one : KernelResult := {
                interval := { lo := .finite 1, hi := .finite 1 }
                status := .ok
              }
              have hone : one.Canonical := Or.inl rfl
              simp [PolynomialExpr.evalKernel, hargument, hstatus] at heval
              subst result
              exact powLoop_canonical exponent base one hone

/-- Status `nonfiniteIntermediate` in a successful evaluation determines the
entire result, not just its status field. -/
theorem PolynomialExpr.evalKernel_nonfinite_eq_whole
    (expression : PolynomialExpr) (environment : Array F64Interval)
    (result : KernelResult)
    (heval : expression.evalKernel environment = some result)
    (hstatus : result.status = .nonfiniteIntermediate) :
    result = KernelResult.whole := by
  rcases expression.evalKernel_canonical environment result heval with
    hok | hwhole
  · simp [hok] at hstatus
  · exact hwhole

/-! ## Production prologue and preserved output base -/

@[simp] theorem generatedPrologueResult_rowBase_lt_nextU64
    (batch : ReferenceBatch) :
    (generatedPrologueResult batch).rowBase.index <
      (generatedPrologueResult batch).builder.nextU64 := by
  rcases emitPrologue_exact batch.variableCount Builder.initial with
    ⟨hrowBase, _, _, _, _, _, hnextU64, _⟩
  change (emitPrologue batch.variableCount Builder.initial).rowBase.index <
    (emitPrologue batch.variableCount Builder.initial).builder.nextU64
  rw [hrowBase, hnextU64]
  simp [prologueRegisters, Builder.initial]

@[simp] theorem generatedPrologueResult_outputBase_lt_nextU64
    (batch : ReferenceBatch) :
    (generatedPrologueResult batch).outputBase.index <
      (generatedPrologueResult batch).builder.nextU64 := by
  rcases emitPrologue_exact batch.variableCount Builder.initial with
    ⟨_, houtputBase, _, _, _, _, hnextU64, _⟩
  change (emitPrologue batch.variableCount Builder.initial).outputBase.index <
    (emitPrologue batch.variableCount Builder.initial).builder.nextU64
  rw [houtputBase, hnextU64]
  simp [prologueRegisters, Builder.initial]

/-- The canonical generated expression slice cannot overwrite the output-base
register allocated by the production prologue.  This holds for either normal
fallthrough or a jump to `wholeLabel`. -/
theorem executeGeneratedExpressionCode_preservesOutputBase
    (batch : ReferenceBatch) (parameters : KernelParameters)
    (thread : ThreadContext) (initial : MachineState)
    (execution : CodeExecution)
    (hexecute : executeCode (buildModule batch) parameters thread
      (generatedExpressionCode batch) initial = some execution) :
    execution.state.u64.read
        (generatedPrologueResult batch).outputBase.index =
      initial.u64.read (generatedPrologueResult batch).outputBase.index := by
  let prologue := generatedPrologueResult batch
  have hu64 := (compileExprAppendedCode_u64MemorySafe prologue.rowBase
    batch.expression prologue.builder).1
  apply executeCode_preservesU64_below (buildModule batch) parameters thread
    (generatedExpressionCode batch) initial execution
    prologue.builder.nextU64 prologue.outputBase.index
  · simpa [generatedExpressionCode, prologue] using hu64
  · simp [prologue]
  · exact hexecute

/-- The in-range production prologue exposes the selected input environment
and its public-row output address in the exact registers returned by
`emitPrologue`. -/
theorem executeGeneratedPrologue_inRange
    (batch : ReferenceBatch) (parameters : KernelParameters)
    (thread : ThreadContext) (memory : GlobalMemory)
    (rows : Array (Array F64Interval)) (environment : Array F64Interval)
    (hthread : thread.Safe)
    (hlayout : SafeKernelLayout parameters batch.variableCount)
    (hin : thread.ctaidX * thread.ntidX + thread.tidX < parameters.rowCount)
    (hmemory : MemoryEncodesRows memory parameters.rows batch.variableCount rows)
    (hrow : rows[thread.ctaidX * thread.ntidX + thread.tidX]? =
      some environment) :
    let index := thread.ctaidX * thread.ntidX + thread.tidX
    let rowAddress := parameters.rows + index * (batch.variableCount * 16)
    ∃ final,
      executeCode (buildModule batch) parameters thread
          (generatedPrologueCode batch) (MachineState.initial memory) =
        some { control := .fallthrough, state := final } ∧
      final.ContainsIntervalEnvironment
        (generatedPrologueResult batch).rowBase rowAddress environment ∧
      final.u64.read (generatedPrologueResult batch).outputBase.index =
        some (prologueOutputBase parameters thread) ∧
      final.memory = memory := by
  let index := thread.ctaidX * thread.ntidX + thread.tidX
  let rowAddress := parameters.rows + index * (batch.variableCount * 16)
  rcases executePrologue_inRange_exposesEnvironment (buildModule batch)
      parameters thread (MachineState.initial memory) batch.variableCount
      Builder.initial rows environment hthread hlayout hin
      (by simpa [MachineState.initial] using hmemory) hrow with
    ⟨final, hexecute, hrowBase, hmemoryPreserved, henvironment⟩
  rcases executePrologue_inRange_exactNat (buildModule batch) parameters thread
      (MachineState.initial memory) batch.variableCount Builder.initial
      hthread hlayout hin with
    ⟨exactFinal, hexact, _, _, houtputBase, _⟩
  have hexecutions :
      ({ control := .fallthrough, state := final } : CodeExecution) =
        { control := .fallthrough, state := exactFinal } := by
    exact Option.some.inj (hexecute.symm.trans hexact)
  have hfinal : final = exactFinal := by
    injection hexecutions
  have hglobalIndex : thread.globalIndex = index := by
    simpa [index] using ThreadContext.globalIndex_eq thread hthread
  have hinGlobal : thread.globalIndex < parameters.rowCount := by
    simpa [hglobalIndex, index] using hin
  have houtputAddress : prologueOutputBase parameters thread =
      parameters.outputs + index * 24 := by
    simpa [hglobalIndex, index] using
      prologueOutputBase_eq_of_safeLayout parameters thread batch.variableCount
        hlayout hinGlobal
  rcases emitPrologue_exact batch.variableCount Builder.initial with
    ⟨hresultRowBase, hresultOutputBase, _, _, _, _, _, _⟩
  refine ⟨final, ?_, ?_, ?_, ?_⟩
  · simpa [generatedPrologueCode] using hexecute
  · constructor
    · simpa [generatedPrologueResult, hresultRowBase] using hrowBase
    · exact henvironment
  · simpa [generatedPrologueResult, hresultOutputBase, hfinal,
      houtputAddress, index] using houtputBase
  · simpa [MachineState.initial] using hmemoryPreserved

/-! ## Structured normal and conservative outcomes -/

/-- Case-split evidence produced after the prologue and expression slices.
The normal constructor records the exact branch to `doneLabel`; the whole
constructor records execution of the entire shared whole suffix through
`ret`.  Both constructors expose the public row observer and its semantic
`OutputRepresents` relation. -/
inductive GeneratedKernelStructuredOutcome
    (batch : ReferenceBatch) (parameters : KernelParameters)
    (thread : ThreadContext) (result : KernelResult)
    (expressionExecution : CodeExecution) : Prop where
  | normal
      (hstatus : result.status = .ok)
      (hexpressionControl : expressionExecution.control = .fallthrough)
      (final : MachineState) (observed : ObservedOutput)
      (hepilogue : executeCode (buildModule batch) parameters thread
          (generatedNormalEpiloguePrefix batch) expressionExecution.state =
        some { control := .jump doneLabel, state := final })
      (hobserve : observeOutput final.memory parameters.outputs
          (thread.ctaidX * thread.ntidX + thread.tidX) = some observed)
      (hrepresents : OutputRepresents observed result) :
      GeneratedKernelStructuredOutcome batch parameters thread result
        expressionExecution
  | whole
      (hstatus : result.status = .nonfiniteIntermediate)
      (hexpressionControl : expressionExecution.control = .jump wholeLabel)
      (final : MachineState) (observed : ObservedOutput)
      (hepilogue : executeCode (buildModule batch) parameters thread
          (generatedWholeEpilogueSuffix batch)
          { expressionExecution.state with
            pc := batch.expression.compiledInstructionCount + 30 } =
        some { control := .returned, state := final })
      (hnegative : final.f64.read
          (epilogueCompilerRegisters
            (generatedExpressionCompilation batch).2).negativeInfinity.index =
        some .negInf)
      (hpositive : final.f64.read
          (epilogueCompilerRegisters
            (generatedExpressionCompilation batch).2).positiveInfinity.index =
        some .posInf)
      (hobserve : observeOutput final.memory parameters.outputs
          (thread.ctaidX * thread.ntidX + thread.tidX) = some observed)
      (hrepresents : OutputRepresents observed result) :
      GeneratedKernelStructuredOutcome batch parameters thread result
        expressionExecution

/-- **Structured in-range refinement for the exact production module.**

Starting from user-supplied row memory, this theorem gives concrete successful
executions of the generated prologue and recursive expression code.  It then
gives the status-selected generated epilogue execution and a public ABI
observation representing the same `evalKernel` result.

Whole-module `run` is intentionally the next layer: the exact placement of
every slice used here is independently stated by `GeneratedModuleSegments`. -/
theorem executeBuildModuleStructured_inRange
    (batch : ReferenceBatch) (parameters : KernelParameters)
    (thread : ThreadContext) (memory : GlobalMemory)
    (rows : Array (Array F64Interval)) (environment : Array F64Interval)
    (result : KernelResult)
    (hthread : thread.Safe)
    (hlayout : SafeKernelLayout parameters batch.variableCount)
    (hin : thread.ctaidX * thread.ntidX + thread.tidX < parameters.rowCount)
    (hmemory : MemoryEncodesRows memory parameters.rows batch.variableCount rows)
    (hrow : rows[thread.ctaidX * thread.ntidX + thread.tidX]? =
      some environment)
    (heval : batch.expression.evalKernel environment = some result) :
    ∃ prologueState expressionExecution,
      executeCode (buildModule batch) parameters thread
          (generatedPrologueCode batch) (MachineState.initial memory) =
        some { control := .fallthrough, state := prologueState } ∧
      executeCode (buildModule batch) parameters thread
          (generatedExpressionCode batch) prologueState =
        some expressionExecution ∧
      GeneratedKernelStructuredOutcome batch parameters thread result
        expressionExecution := by
  let index := thread.ctaidX * thread.ntidX + thread.tidX
  let rowAddress := parameters.rows + index * (batch.variableCount * 16)
  let prologue := generatedPrologueResult batch
  let compiled := generatedExpressionCompilation batch
  rcases executeGeneratedPrologue_inRange batch parameters thread memory rows
      environment hthread hlayout hin hmemory hrow with
    ⟨prologueState, hprologue, henvironment, hprologueOutputBase, _⟩
  rcases executeCompileExprAppendedCode (buildModule batch) parameters thread
      prologueState prologue.rowBase rowAddress environment batch.expression
      prologue.builder result
      (by simp [prologue])
      (by simpa [prologue, index, rowAddress] using henvironment) heval with
    ⟨expressionExecution, hexpressionRaw, hrefines⟩
  have hexpression : executeCode (buildModule batch) parameters thread
      (generatedExpressionCode batch) prologueState =
        some expressionExecution := by
    simpa [generatedExpressionCode, prologue] using hexpressionRaw
  have houtcome : ExpressionCodeOutcome compiled.1 result
      expressionExecution := by
    simpa [compiled, generatedExpressionCompilation, prologue] using hrefines.1
  have houtputPreserved :=
    executeGeneratedExpressionCode_preservesOutputBase batch parameters thread
      prologueState expressionExecution hexpression
  have hexpressionOutputBase : expressionExecution.state.u64.read
      prologue.outputBase.index = some (prologueOutputBase parameters thread) := by
    calc
      expressionExecution.state.u64.read prologue.outputBase.index =
          prologueState.u64.read prologue.outputBase.index := by
            simpa [prologue] using houtputPreserved
      _ = some (prologueOutputBase parameters thread) := by
        simpa [prologue] using hprologueOutputBase
  have hsafe := prologueOutputBase_record_safe parameters thread
    batch.variableCount hthread hlayout hin
  refine ⟨prologueState, expressionExecution, hprologue, hexpression, ?_⟩
  cases hstatus : result.status with
  | ok =>
      have hnormal : expressionExecution.control = .fallthrough ∧
          expressionExecution.state.RegistersContain compiled.1
            result.interval := by
        simpa [ExpressionCodeOutcome, hstatus] using houtcome
      rcases hnormal.2 with ⟨hlo, hhi⟩
      rcases executeCompiledNormalEpiloguePrefix_observe
          (buildModule batch) parameters thread expressionExecution.state
          prologue.outputBase compiled.1 compiled.2
          (prologueOutputBase parameters thread) result.interval
          hexpressionOutputBase hlo hhi hsafe with
        ⟨final, hepilogueRaw, hobserveBase⟩
      let observed := expectedObservedOutput result.interval epilogueOkStatus
      have hobserve : observeOutput final.memory parameters.outputs index =
          some observed := by
        rw [observeOutput_eq_prologueOutputBase final.memory parameters thread
          batch.variableCount hthread hlayout hin]
        exact hobserveBase
      have hrepresents : OutputRepresents observed result := by
        cases result with
        | mk interval status =>
            cases status <;>
              simp_all [observed, OutputRepresents, expectedObservedOutput,
                epilogueOkStatus]
      apply GeneratedKernelStructuredOutcome.normal hstatus hnormal.1 final
        observed
      · simpa [generatedNormalEpiloguePrefix, prologue, compiled] using
          hepilogueRaw
      · simpa [index] using hobserve
      · exact hrepresents
  | nonfiniteIntermediate =>
      have hwholeResult := batch.expression.evalKernel_nonfinite_eq_whole
        environment result heval hstatus
      have hwholeControl :
          expressionExecution.control = .jump wholeLabel := by
        simpa [ExpressionCodeOutcome, hstatus] using houtcome
      have hwholeOutputBase :
          ({ expressionExecution.state with
              pc := batch.expression.compiledInstructionCount + 30 } :
            MachineState).u64.read prologue.outputBase.index =
            some (prologueOutputBase parameters thread) := by
        simpa using hexpressionOutputBase
      rcases executeCompiledWholeEpilogueSuffix_observe
          (buildModule batch) parameters thread
          { expressionExecution.state with
            pc := batch.expression.compiledInstructionCount + 30 }
          prologue.outputBase compiled.2
          (prologueOutputBase parameters thread) hwholeOutputBase hsafe with
        ⟨final, hepilogueRaw, hnegative, hpositive, hobserveBase⟩
      let observed := expectedObservedOutput F64Interval.whole
        epilogueNonfiniteStatus
      have hobserve : observeOutput final.memory parameters.outputs index =
          some observed := by
        rw [observeOutput_eq_prologueOutputBase final.memory parameters thread
          batch.variableCount hthread hlayout hin]
        exact hobserveBase
      have hrepresents : OutputRepresents observed result := by
        rw [hwholeResult]
        exact expectedObservedOutput_nonfinite_represents
      apply GeneratedKernelStructuredOutcome.whole hstatus hwholeControl final
        observed
      · simpa [generatedWholeEpilogueSuffix, prologue, compiled] using
          hepilogueRaw
      · simpa [compiled] using hnegative
      · simpa [compiled] using hpositive
      · simpa [index] using hobserve
      · exact hrepresents

end SparkInterval.PTX
