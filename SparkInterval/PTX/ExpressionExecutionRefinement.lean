import SparkInterval.PTX.CompilerBodyDataflow
import SparkInterval.PTX.CompilerNodeRefinement
import SparkInterval.PTX.ExpressionInstructionRefinement
import SparkInterval.PTX.CodeComposition
import SparkInterval.PTX.InputLayoutRefinement

/-!
# Recursive expression execution refinement

This module connects the instruction slices appended by the production
`compileExpr` compiler to the status-aware `PolynomialExpr.evalKernel` model.
The definitions in the first section give canonical, compositional names to
the exact suffixes appended by recursive expression and power compilation.
They are intentionally stated in terms of the production compiler and its
already-proved node-local suffixes.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- The exact instruction suffix appended by production `compilePowLoop`.
The builder and accumulator arguments evolve exactly as they do in the
production compiler. -/
def compilePowLoopAppendedCode (base : IntervalRegisters) :
    Nat → IntervalRegisters → Builder → List Instruction
  | 0, _, _ => []
  | count + 1, current, builder =>
      let next := compileMul current base builder
      compileMulAppendedCode current base builder ++
        compilePowLoopAppendedCode base count next.1 next.2

/-- Canonical recursive name for the exact instruction suffix appended by one
production `compileExpr` invocation. -/
def compileExprAppendedCode (rowBase : Reg .u64) :
    PolynomialExpr → Builder → List Instruction
  | .const value, builder => compileConstAppendedCode value builder
  | .var index, builder => compileVarAppendedCode rowBase index builder
  | .neg argument, builder =>
      let argumentCompiled := compileExpr rowBase argument builder
      compileExprAppendedCode rowBase argument builder ++
        compileNegAppendedCode argumentCompiled.1 argumentCompiled.2
  | .add left right, builder =>
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      compileExprAppendedCode rowBase left builder ++
        compileExprAppendedCode rowBase right leftCompiled.2 ++
        compileAddAppendedCode leftCompiled.1 rightCompiled.1 rightCompiled.2
  | .sub left right, builder =>
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      compileExprAppendedCode rowBase left builder ++
        compileExprAppendedCode rowBase right leftCompiled.2 ++
        compileSubAppendedCode leftCompiled.1 rightCompiled.1 rightCompiled.2
  | .mul left right, builder =>
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      compileExprAppendedCode rowBase left builder ++
        compileExprAppendedCode rowBase right leftCompiled.2 ++
        compileMulAppendedCode leftCompiled.1 rightCompiled.1 rightCompiled.2
  | .powNat argument exponent, builder =>
      let argumentCompiled := compileExpr rowBase argument builder
      let one : IntervalBits := {
        lo := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
        hi := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
      }
      let initialCompiled := compileConst one argumentCompiled.2
      compileExprAppendedCode rowBase argument builder ++
        compileConstAppendedCode one argumentCompiled.2 ++
        compilePowLoopAppendedCode argumentCompiled.1 exponent
          initialCompiled.1 initialCompiled.2

/-- `compilePowLoopAppendedCode` is not a model of the compiler: it is exactly
the suffix appended to the production builder. -/
theorem compilePowLoop_body_toList (base : IntervalRegisters) (count : Nat)
    (current : IntervalRegisters) (builder : Builder) :
    (compilePowLoop base count current builder).2.body.toList =
      builder.body.toList ++
        compilePowLoopAppendedCode base count current builder := by
  induction count generalizing current builder with
  | zero => simp [compilePowLoop, compilePowLoopAppendedCode]
  | succ count induction =>
      rw [compilePowLoop]
      rw [induction]
      rw [compileMul_body_toList]
      simp only [compilePowLoopAppendedCode]
      rw [List.append_assoc]

/-- `compileExprAppendedCode` is exactly the suffix appended by the production
recursive expression compiler. -/
theorem compileExpr_body_toList (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    (compileExpr rowBase expression builder).2.body.toList =
      builder.body.toList ++
        compileExprAppendedCode rowBase expression builder := by
  induction expression generalizing builder with
  | const value =>
      exact compileConst_body_toList value builder
  | var index =>
      exact compileExpr_var_body_toList rowBase index builder
  | neg argument induction =>
      rw [compileExpr]
      let argumentCompiled := compileExpr rowBase argument builder
      have hargument := induction builder
      have htail := compileExpr_neg_tail_body_toList
        argumentCompiled.1 argumentCompiled.2
      rw [htail, hargument]
      simp only [compileExprAppendedCode]
      rw [List.append_assoc]
  | add left right leftInduction rightInduction =>
      rw [compileExpr]
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      rw [compileAdd_body_toList, rightInduction, leftInduction]
      simp only [compileExprAppendedCode]
      simp only [List.append_assoc]
  | sub left right leftInduction rightInduction =>
      rw [compileExpr]
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      rw [compileSub_body_toList, rightInduction, leftInduction]
      simp only [compileExprAppendedCode]
      simp only [List.append_assoc]
  | mul left right leftInduction rightInduction =>
      rw [compileExpr]
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      rw [compileMul_body_toList, rightInduction, leftInduction]
      simp only [compileExprAppendedCode]
      simp only [List.append_assoc]
  | powNat argument exponent induction =>
      rw [compileExpr]
      let argumentCompiled := compileExpr rowBase argument builder
      let one : IntervalBits := {
        lo := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
        hi := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
      }
      let initialCompiled := compileConst one argumentCompiled.2
      rw [compilePowLoop_body_toList, compileConst_body_toList, induction]
      simp only [compileExprAppendedCode]
      simp only [List.append_assoc]

/-! ## Canonical-suffix dataflow facts -/

/-- Every f64 destination in the canonical expression suffix is at or above
the incoming production allocator frontier. -/
theorem compileExprAppendedCode_f64WritesAtOrAbove (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    F64WritesAtOrAbove builder.nextF64
      (compileExprAppendedCode rowBase expression builder) := by
  rcases compileExpr_body_f64Safe rowBase expression builder with
    ⟨suffix, hbody, hwrites⟩
  have hsuffix : suffix = compileExprAppendedCode rowBase expression builder := by
    apply List.append_cancel_left
    rw [← hbody, compileExpr_body_toList]
  simpa [hsuffix] using hwrites

/-- Every f64 destination in the canonical power-loop suffix is fresh with
respect to the incoming frontier. -/
theorem compilePowLoopAppendedCode_f64WritesAtOrAbove
    (base : IntervalRegisters) (count : Nat) (current : IntervalRegisters)
    (builder : Builder) :
    F64WritesAtOrAbove builder.nextF64
      (compilePowLoopAppendedCode base count current builder) := by
  rcases compilePowLoop_body_f64Safe base count current builder with
    ⟨suffix, hbody, hwrites⟩
  have hsuffix : suffix =
      compilePowLoopAppendedCode base count current builder := by
    apply List.append_cancel_left
    rw [← hbody, compilePowLoop_body_toList]
  simpa [hsuffix] using hwrites

/-- The canonical expression suffix has the same u64-freshness and memory
store-freedom facts as the existential suffix exposed by compiler dataflow. -/
theorem compileExprAppendedCode_u64MemorySafe (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    U64WritesAtOrAbove builder.nextU64
        (compileExprAppendedCode rowBase expression builder) ∧
      GlobalMemoryWriteFree
        (compileExprAppendedCode rowBase expression builder) := by
  rcases compileExpr_body_u64MemorySafe rowBase expression builder with
    ⟨suffix, hbody, hu64, hmemory⟩
  have hsuffix : suffix = compileExprAppendedCode rowBase expression builder := by
    apply List.append_cancel_left
    rw [← hbody, compileExpr_body_toList]
  subst suffix
  exact ⟨hu64, hmemory⟩

/-- Power-loop specialization of the canonical u64/memory effect contract. -/
theorem compilePowLoopAppendedCode_u64MemorySafe
    (base : IntervalRegisters) (count : Nat) (current : IntervalRegisters)
    (builder : Builder) :
    U64WritesAtOrAbove builder.nextU64
        (compilePowLoopAppendedCode base count current builder) ∧
      GlobalMemoryWriteFree
        (compilePowLoopAppendedCode base count current builder) := by
  rcases compilePowLoop_body_u64MemorySafe base count current builder with
    ⟨suffix, hbody, hu64, hmemory⟩
  have hsuffix : suffix =
      compilePowLoopAppendedCode base count current builder := by
    apply List.append_cancel_left
    rw [← hbody, compilePowLoop_body_toList]
  subst suffix
  exact ⟨hu64, hmemory⟩

/-! ## Semantic interface -/

/-- A decoded interval environment is present at the row-base address used by
the expression compiler.  Expressing the relation at an already-computed row
base keeps it directly reusable after `executePrologue_inRange_exactNat`. -/
def MachineState.ContainsIntervalEnvironment (state : MachineState)
    (rowBase : Reg .u64) (rowAddress : Nat)
    (environment : Array F64Interval) : Prop :=
  state.u64.read rowBase.index = some rowAddress ∧
    state.memory.EncodesEnvironmentAt rowAddress environment

/-- The structured-machine outcome corresponding to one successful
`evalKernel` result.  A normal result is materialized in the compiler-selected
register pair; the conservative status is represented by the exact branch to
the shared `wholeLabel`. -/
def ExpressionCodeOutcome (registers : IntervalRegisters)
    (result : KernelResult) (execution : CodeExecution) : Prop :=
  match result.status with
  | .ok =>
      execution.control = .fallthrough ∧
        execution.state.RegistersContain registers result.interval
  | .nonfiniteIntermediate => execution.control = .jump wholeLabel

/-- Public recursive refinement result, including the non-f64 state facts
needed to execute later sibling expressions. -/
def ExpressionExecutionRefines (rowBase : Reg .u64)
    (initial : MachineState) (registers : IntervalRegisters)
    (result : KernelResult) (execution : CodeExecution) : Prop :=
  ExpressionCodeOutcome registers result execution ∧
    execution.state.u64.read rowBase.index =
      initial.u64.read rowBase.index ∧
    execution.state.memory = initial.memory

theorem MachineState.ContainsIntervalEnvironment.of_preserved
    {initial final : MachineState} {rowBase : Reg .u64} {rowAddress : Nat}
    {environment : Array F64Interval}
    (henvironment : initial.ContainsIntervalEnvironment
      rowBase rowAddress environment)
    (hrowBase : final.u64.read rowBase.index =
      initial.u64.read rowBase.index)
    (hmemory : final.memory = initial.memory) :
    final.ContainsIntervalEnvironment rowBase rowAddress environment := by
  rcases henvironment with ⟨hbase, hloads⟩
  constructor
  · simpa [hrowBase] using hbase
  · intro index interval hget
    simpa [hmemory] using hloads index interval hget

/-- Canonical expression-code form of the shared compiler effect theorem. -/
theorem executeCompileExprAppendedCode_preservesRowBaseAndMemory
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (initial : MachineState) (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder)
    (execution : CodeExecution)
    (hrowBase : rowBase.index < builder.nextU64)
    (hexecute : executeCode module parameters thread
      (compileExprAppendedCode rowBase expression builder) initial =
        some execution) :
    execution.state.u64.read rowBase.index =
        initial.u64.read rowBase.index ∧
      execution.state.memory = initial.memory := by
  rcases compileExprAppendedCode_u64MemorySafe rowBase expression builder with
    ⟨hu64, hmemory⟩
  constructor
  · exact executeCode_preservesU64_below module parameters thread
      (compileExprAppendedCode rowBase expression builder) initial execution
      builder.nextU64 rowBase.index hu64 hrowBase hexecute
  · exact executeCode_preserves_globalMemory module parameters thread
      (compileExprAppendedCode rowBase expression builder) initial execution
      hmemory hexecute

/-! ## Production-selected leaf and unary slices -/

theorem executeCompileConstAppendedCode
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (value : IntervalBits) (builder : Builder)
    (lo hi : F64Value)
    (hlo : decodeF64Bits value.lo.value = some lo)
    (hhi : decodeF64Bits value.hi.value = some hi) :
    ∃ final,
      executeCode module parameters thread
          (compileConstAppendedCode value builder) state =
        some { control := .fallthrough, state := final } ∧
      final.RegistersContain (compileConst value builder).1 { lo, hi } := by
  apply executeConstInstructions module parameters thread state
    (compileConst value builder).1 value.lo.value value.hi.value lo hi hlo hhi
  simp [compileConst, Builder.freshInterval, Builder.freshF64, Builder.emit]

theorem executeCompileVarAppendedCode
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (rowBase : Reg .u64) (index : Nat)
    (builder : Builder) (rowAddress : Nat) (interval : F64Interval)
    (hbase : state.u64.read rowBase.index = some rowAddress)
    (hlo : state.memory.loadF64
      (globalAddress rowAddress (index * 16)) = some interval.lo)
    (hhi : state.memory.loadF64
      (globalAddress rowAddress (index * 16 + 8)) = some interval.hi) :
    ∃ final,
      executeCode module parameters thread
          (compileVarAppendedCode rowBase index builder) state =
        some { control := .fallthrough, state := final } ∧
      final.RegistersContain
        (compileExpr rowBase (.var index) builder).1 interval := by
  apply executeLoadIntervalInstructions module parameters thread state
    (compileExpr rowBase (.var index) builder).1 rowBase rowAddress
    (index * 16) (index * 16 + 8) interval.lo interval.hi hbase hlo hhi
  simp [compileExpr, Builder.freshInterval, Builder.freshF64, Builder.emit]

theorem executeCompileNegAppendedCode
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (argument : IntervalRegisters) (builder : Builder)
    (interval : F64Interval)
    (hargumentBelow : argument.Below builder.nextF64)
    (hargument : state.RegistersContain argument interval) :
    ∃ final,
      executeCode module parameters thread
          (compileNegAppendedCode argument builder) state =
        some { control := .fallthrough, state := final } ∧
      final.RegistersContain
        (builder.freshInterval.1) interval.negate := by
  rcases hargument with ⟨hlo, hhi⟩
  apply executeNegInstructions module parameters thread state
    builder.freshInterval.1 argument interval.lo interval.hi hlo hhi
  · simp [Builder.freshInterval, Builder.freshF64]
  · unfold IntervalRegisters.Below at hargumentBelow
    simp [Builder.freshInterval, Builder.freshF64]
    omega

/-! ## Guarded binary slices -/

/-- A successful finite guard does not modify either the guarded interval or
an independently supplied interval.  This packages the f64 effect theorem in
the form needed by the two-guard arithmetic nodes. -/
private theorem executeCompiledFiniteGuard_fallthrough_preserves
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (value preserved : IntervalRegisters)
    (builder : Builder) (valueLo valueHi : ℝ)
    (preservedInterval : F64Interval)
    (hvalue : state.RegistersContain value
      { lo := .finite valueLo, hi := .finite valueHi })
    (hpreserved : state.RegistersContain preserved preservedInterval) :
    ∃ final,
      executeCode module parameters thread
          (compiledFiniteGuardInstructions value builder) state =
        some { control := .fallthrough, state := final } ∧
      final.RegistersContain value
          { lo := .finite valueLo, hi := .finite valueHi } ∧
        final.RegistersContain preserved preservedInterval := by
  rcases hvalue with ⟨hvalueLo, hvalueHi⟩
  rcases hpreserved with ⟨hpreservedLo, hpreservedHi⟩
  rcases executeCompiledFiniteGuard_fallthrough module parameters thread
    state value builder valueLo valueHi hvalueLo hvalueHi with
    ⟨final, hexecute⟩
  have hread (index : Nat) :
      final.f64.read index = state.f64.read index := by
    exact executeCode_fallthrough_preserves_f64_read module parameters thread
      (compiledFiniteGuardInstructions value builder) state final index
      (by simp) hexecute
  refine ⟨final, hexecute, ⟨?_, ?_⟩, ⟨?_, ?_⟩⟩
  · rw [hread]
    exact hvalueLo
  · rw [hread]
    exact hvalueHi
  · rw [hread]
    exact hpreservedLo
  · rw [hread]
    exact hpreservedHi

/-- Generic refinement of the guard/guard/arithmetic shape shared by the
production add, subtract, and multiply nodes.  The only operation-specific
premise is execution of the final arithmetic fragment on four finite source
endpoints. -/
theorem executeGuardedArithmeticCode
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (op : F64BinaryOp)
    (left right result : IntervalRegisters) (builder : Builder)
    (arithmetic : List Instruction)
    (leftInterval rightInterval : F64Interval)
    (hleft : state.RegistersContain left leftInterval)
    (hright : state.RegistersContain right rightInterval)
    (harithmetic : ∀ (arithmeticState : MachineState)
        (leftLo leftHi rightLo rightHi : ℝ),
      arithmeticState.RegistersContain left
          { lo := .finite leftLo, hi := .finite leftHi } →
      arithmeticState.RegistersContain right
          { lo := .finite rightLo, hi := .finite rightHi } →
      ∃ final,
        executeCode module parameters thread arithmetic arithmeticState =
          some { control := .fallthrough, state := final } ∧
        final.RegistersContain result
          (roundedBinaryInterval op leftLo leftHi rightLo rightHi)) :
    ∃ execution,
      executeCode module parameters thread
          (compiledFiniteGuardInstructions left builder ++
            compiledFiniteGuardInstructions right
              (emitFiniteGuard left builder) ++ arithmetic) state =
        some execution ∧
      ExpressionCodeOutcome result
        (guardedBinary op
          { interval := leftInterval, status := .ok }
          { interval := rightInterval, status := .ok }) execution := by
  rcases hleft with ⟨hleftLo, hleftHi⟩
  rcases hright with ⟨hrightLo, hrightHi⟩
  cases hlo : leftInterval.lo with
  | negInf =>
      rcases executeCompiledFiniteGuard_lowerNonfinite module parameters thread
        state left builder .negInf (by simp) (by simpa [hlo] using hleftLo) with
        ⟨afterLeft, hguard⟩
      let execution : CodeExecution := {
        control := .jump wholeLabel, state := afterLeft }
      refine ⟨execution, ?_, ?_⟩
      · exact executeCode_append_jump module parameters thread
          (compiledFiniteGuardInstructions left builder)
          (compiledFiniteGuardInstructions right (emitFiniteGuard left builder) ++
            arithmetic) state afterLeft wholeLabel hguard
      · simp [ExpressionCodeOutcome, guardedBinary,
          F64Interval.finiteBounds?, hlo, KernelResult.whole, execution]
  | posInf =>
      rcases executeCompiledFiniteGuard_lowerNonfinite module parameters thread
        state left builder .posInf (by simp) (by simpa [hlo] using hleftLo) with
        ⟨afterLeft, hguard⟩
      let execution : CodeExecution := {
        control := .jump wholeLabel, state := afterLeft }
      refine ⟨execution, ?_, ?_⟩
      · exact executeCode_append_jump module parameters thread
          (compiledFiniteGuardInstructions left builder)
          (compiledFiniteGuardInstructions right (emitFiniteGuard left builder) ++
            arithmetic) state afterLeft wholeLabel hguard
      · simp [ExpressionCodeOutcome, guardedBinary,
          F64Interval.finiteBounds?, hlo, KernelResult.whole, execution]
  | finite leftLo =>
      cases hhi : leftInterval.hi with
      | negInf =>
          rcases executeCompiledFiniteGuard_upperNonfinite module parameters thread
            state left builder leftLo .negInf (by simp)
              (by simpa [hlo] using hleftLo)
              (by simpa [hhi] using hleftHi) with
            ⟨afterLeft, hguard⟩
          let execution : CodeExecution := {
            control := .jump wholeLabel, state := afterLeft }
          refine ⟨execution, ?_, ?_⟩
          · exact executeCode_append_jump module parameters thread
              (compiledFiniteGuardInstructions left builder)
              (compiledFiniteGuardInstructions right
                (emitFiniteGuard left builder) ++ arithmetic)
              state afterLeft wholeLabel hguard
          · simp [ExpressionCodeOutcome, guardedBinary,
              F64Interval.finiteBounds?, hlo, hhi, KernelResult.whole,
              execution]
      | posInf =>
          rcases executeCompiledFiniteGuard_upperNonfinite module parameters thread
            state left builder leftLo .posInf (by simp)
              (by simpa [hlo] using hleftLo)
              (by simpa [hhi] using hleftHi) with
            ⟨afterLeft, hguard⟩
          let execution : CodeExecution := {
            control := .jump wholeLabel, state := afterLeft }
          refine ⟨execution, ?_, ?_⟩
          · exact executeCode_append_jump module parameters thread
              (compiledFiniteGuardInstructions left builder)
              (compiledFiniteGuardInstructions right
                (emitFiniteGuard left builder) ++ arithmetic)
              state afterLeft wholeLabel hguard
          · simp [ExpressionCodeOutcome, guardedBinary,
              F64Interval.finiteBounds?, hlo, hhi, KernelResult.whole,
              execution]
      | finite leftHi =>
          have hleftFinite : state.RegistersContain left
              { lo := .finite leftLo, hi := .finite leftHi } := by
            exact ⟨by simpa [hlo] using hleftLo,
              by simpa [hhi] using hleftHi⟩
          rcases executeCompiledFiniteGuard_fallthrough_preserves
            module parameters thread state left right builder leftLo leftHi
            rightInterval hleftFinite ⟨hrightLo, hrightHi⟩ with
            ⟨afterLeft, hleftGuard, hleftStill, hrightStill⟩
          rcases hrightStill with ⟨hrightLoStill, hrightHiStill⟩
          cases rlo : rightInterval.lo with
          | negInf =>
              rcases executeCompiledFiniteGuard_lowerNonfinite
                module parameters thread afterLeft right
                (emitFiniteGuard left builder) .negInf (by simp)
                (by simpa [rlo] using hrightLoStill) with
                ⟨afterRight, hrightGuard⟩
              have hrightAndArithmetic := executeCode_append_jump
                module parameters thread
                (compiledFiniteGuardInstructions right
                  (emitFiniteGuard left builder)) arithmetic
                afterLeft afterRight wholeLabel hrightGuard
              let execution : CodeExecution := {
                control := .jump wholeLabel, state := afterRight }
              refine ⟨execution, ?_, ?_⟩
              · exact executeCode_append_fallthrough module parameters thread
                  (compiledFiniteGuardInstructions left builder)
                  (compiledFiniteGuardInstructions right
                    (emitFiniteGuard left builder) ++ arithmetic)
                  state afterLeft hleftGuard |>.trans hrightAndArithmetic
              · simp [ExpressionCodeOutcome, guardedBinary,
                  F64Interval.finiteBounds?, hlo, hhi, rlo,
                  KernelResult.whole, execution]
          | posInf =>
              rcases executeCompiledFiniteGuard_lowerNonfinite
                module parameters thread afterLeft right
                (emitFiniteGuard left builder) .posInf (by simp)
                (by simpa [rlo] using hrightLoStill) with
                ⟨afterRight, hrightGuard⟩
              have hrightAndArithmetic := executeCode_append_jump
                module parameters thread
                (compiledFiniteGuardInstructions right
                  (emitFiniteGuard left builder)) arithmetic
                afterLeft afterRight wholeLabel hrightGuard
              let execution : CodeExecution := {
                control := .jump wholeLabel, state := afterRight }
              refine ⟨execution, ?_, ?_⟩
              · exact executeCode_append_fallthrough module parameters thread
                  (compiledFiniteGuardInstructions left builder)
                  (compiledFiniteGuardInstructions right
                    (emitFiniteGuard left builder) ++ arithmetic)
                  state afterLeft hleftGuard |>.trans hrightAndArithmetic
              · simp [ExpressionCodeOutcome, guardedBinary,
                  F64Interval.finiteBounds?, hlo, hhi, rlo,
                  KernelResult.whole, execution]
          | finite rightLo =>
              cases rhi : rightInterval.hi with
              | negInf =>
                  rcases executeCompiledFiniteGuard_upperNonfinite
                    module parameters thread afterLeft right
                    (emitFiniteGuard left builder) rightLo .negInf (by simp)
                    (by simpa [rlo] using hrightLoStill)
                    (by simpa [rhi] using hrightHiStill) with
                    ⟨afterRight, hrightGuard⟩
                  have hrightAndArithmetic := executeCode_append_jump
                    module parameters thread
                    (compiledFiniteGuardInstructions right
                      (emitFiniteGuard left builder)) arithmetic
                    afterLeft afterRight wholeLabel hrightGuard
                  let execution : CodeExecution := {
                    control := .jump wholeLabel, state := afterRight }
                  refine ⟨execution, ?_, ?_⟩
                  · exact executeCode_append_fallthrough module parameters thread
                      (compiledFiniteGuardInstructions left builder)
                      (compiledFiniteGuardInstructions right
                        (emitFiniteGuard left builder) ++ arithmetic)
                      state afterLeft hleftGuard |>.trans hrightAndArithmetic
                  · simp [ExpressionCodeOutcome, guardedBinary,
                      F64Interval.finiteBounds?, hlo, hhi, rlo, rhi,
                      KernelResult.whole, execution]
              | posInf =>
                  rcases executeCompiledFiniteGuard_upperNonfinite
                    module parameters thread afterLeft right
                    (emitFiniteGuard left builder) rightLo .posInf (by simp)
                    (by simpa [rlo] using hrightLoStill)
                    (by simpa [rhi] using hrightHiStill) with
                    ⟨afterRight, hrightGuard⟩
                  have hrightAndArithmetic := executeCode_append_jump
                    module parameters thread
                    (compiledFiniteGuardInstructions right
                      (emitFiniteGuard left builder)) arithmetic
                    afterLeft afterRight wholeLabel hrightGuard
                  let execution : CodeExecution := {
                    control := .jump wholeLabel, state := afterRight }
                  refine ⟨execution, ?_, ?_⟩
                  · exact executeCode_append_fallthrough module parameters thread
                      (compiledFiniteGuardInstructions left builder)
                      (compiledFiniteGuardInstructions right
                        (emitFiniteGuard left builder) ++ arithmetic)
                      state afterLeft hleftGuard |>.trans hrightAndArithmetic
                  · simp [ExpressionCodeOutcome, guardedBinary,
                      F64Interval.finiteBounds?, hlo, hhi, rlo, rhi,
                      KernelResult.whole, execution]
              | finite rightHi =>
                  have hrightFinite : afterLeft.RegistersContain right
                      { lo := .finite rightLo, hi := .finite rightHi } := by
                    exact ⟨by simpa [rlo] using hrightLoStill,
                      by simpa [rhi] using hrightHiStill⟩
                  rcases executeCompiledFiniteGuard_fallthrough_preserves
                    module parameters thread afterLeft right left
                    (emitFiniteGuard left builder) rightLo rightHi
                    { lo := .finite leftLo, hi := .finite leftHi }
                    hrightFinite hleftStill with
                    ⟨afterRight, hrightGuard, hrightFinal, hleftFinal⟩
                  rcases harithmetic afterRight leftLo leftHi rightLo rightHi
                    hleftFinal hrightFinal with
                    ⟨final, harithmeticExecute, hresult⟩
                  have hrightAndArithmetic := executeCode_append_fallthrough
                    module parameters thread
                    (compiledFiniteGuardInstructions right
                      (emitFiniteGuard left builder)) arithmetic
                    afterLeft afterRight hrightGuard |>.trans harithmeticExecute
                  let execution : CodeExecution := {
                    control := .fallthrough, state := final }
                  refine ⟨execution, ?_, ?_⟩
                  · exact executeCode_append_fallthrough module parameters thread
                      (compiledFiniteGuardInstructions left builder)
                      (compiledFiniteGuardInstructions right
                        (emitFiniteGuard left builder) ++ arithmetic)
                      state afterLeft hleftGuard |>.trans hrightAndArithmetic
                  · simp [ExpressionCodeOutcome, guardedBinary,
                      F64Interval.finiteBounds?, hlo, hhi, rlo, rhi,
                      execution, hresult]

/-- Full guarded addition slice selected by production `compileAdd`. -/
theorem executeCompileAddAppendedCode_guarded
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (left right : IntervalRegisters) (builder : Builder)
    (leftInterval rightInterval : F64Interval)
    (hleftBelow : left.Below builder.nextF64)
    (hrightBelow : right.Below builder.nextF64)
    (hleft : state.RegistersContain left leftInterval)
    (hright : state.RegistersContain right rightInterval) :
    ∃ execution,
      executeCode module parameters thread
          (compileAddAppendedCode left right builder) state = some execution ∧
      ExpressionCodeOutcome (compileAdd left right builder).1
        (guardedBinary .add
          { interval := leftInterval, status := .ok }
          { interval := rightInterval, status := .ok }) execution := by
  let result := (compileAdd left right builder).1
  have harithmetic : ∀ (arithmeticState : MachineState)
      (leftLo leftHi rightLo rightHi : ℝ),
      arithmeticState.RegistersContain left
          { lo := .finite leftLo, hi := .finite leftHi } →
      arithmeticState.RegistersContain right
          { lo := .finite rightLo, hi := .finite rightHi } →
      ∃ final,
        executeCode module parameters thread
            (addArithmeticFragment result left right).toList arithmeticState =
          some { control := .fallthrough, state := final } ∧
        final.RegistersContain result
          (roundedBinaryInterval .add leftLo leftHi rightLo rightHi) := by
    intro arithmeticState leftLo leftHi rightLo rightHi hleftState hrightState
    rcases hleftState with ⟨hleftLo, hleftHi⟩
    rcases hrightState with ⟨hrightLo, hrightHi⟩
    exact executeCompileAddArithmeticFragment module parameters thread
      arithmeticState left right builder leftLo leftHi rightLo rightHi
      hleftBelow hrightBelow hleftLo hleftHi hrightLo hrightHi
  simpa [compileAddAppendedCode, compileAdd, result] using
    executeGuardedArithmeticCode module parameters thread state .add left right
      result builder (addArithmeticFragment result left right).toList
      leftInterval rightInterval hleft hright harithmetic

/-- Full guarded subtraction slice selected by production `compileSub`. -/
theorem executeCompileSubAppendedCode_guarded
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (left right : IntervalRegisters) (builder : Builder)
    (leftInterval rightInterval : F64Interval)
    (hleftBelow : left.Below builder.nextF64)
    (hrightBelow : right.Below builder.nextF64)
    (hleft : state.RegistersContain left leftInterval)
    (hright : state.RegistersContain right rightInterval) :
    ∃ execution,
      executeCode module parameters thread
          (compileSubAppendedCode left right builder) state = some execution ∧
      ExpressionCodeOutcome (compileSub left right builder).1
        (guardedBinary .sub
          { interval := leftInterval, status := .ok }
          { interval := rightInterval, status := .ok }) execution := by
  let result := (compileSub left right builder).1
  have harithmetic : ∀ (arithmeticState : MachineState)
      (leftLo leftHi rightLo rightHi : ℝ),
      arithmeticState.RegistersContain left
          { lo := .finite leftLo, hi := .finite leftHi } →
      arithmeticState.RegistersContain right
          { lo := .finite rightLo, hi := .finite rightHi } →
      ∃ final,
        executeCode module parameters thread
            (subArithmeticFragment result left right).toList arithmeticState =
          some { control := .fallthrough, state := final } ∧
        final.RegistersContain result
          (roundedBinaryInterval .sub leftLo leftHi rightLo rightHi) := by
    intro arithmeticState leftLo leftHi rightLo rightHi hleftState hrightState
    rcases hleftState with ⟨hleftLo, hleftHi⟩
    rcases hrightState with ⟨hrightLo, hrightHi⟩
    exact executeCompileSubArithmeticFragment module parameters thread
      arithmeticState left right builder leftLo leftHi rightLo rightHi
      hleftBelow hrightBelow hleftLo hleftHi hrightLo hrightHi
  simpa [compileSubAppendedCode, compileSub, result] using
    executeGuardedArithmeticCode module parameters thread state .sub left right
      result builder (subArithmeticFragment result left right).toList
      leftInterval rightInterval hleft hright harithmetic

/-- Full guarded fourteen-instruction multiplication slice selected by
production `compileMul`. -/
theorem executeCompileMulAppendedCode_guarded
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (left right : IntervalRegisters) (builder : Builder)
    (leftInterval rightInterval : F64Interval)
    (hleftBelow : left.Below builder.nextF64)
    (hrightBelow : right.Below builder.nextF64)
    (hleft : state.RegistersContain left leftInterval)
    (hright : state.RegistersContain right rightInterval) :
    ∃ execution,
      executeCode module parameters thread
          (compileMulAppendedCode left right builder) state = some execution ∧
      ExpressionCodeOutcome (compileMul left right builder).1
        (guardedBinary .mul
          { interval := leftInterval, status := .ok }
          { interval := rightInterval, status := .ok }) execution := by
  let allocation := compileMulAllocation left right builder
  have harithmetic : ∀ (arithmeticState : MachineState)
      (leftLo leftHi rightLo rightHi : ℝ),
      arithmeticState.RegistersContain left
          { lo := .finite leftLo, hi := .finite leftHi } →
      arithmeticState.RegistersContain right
          { lo := .finite rightLo, hi := .finite rightHi } →
      ∃ final,
        executeCode module parameters thread
            (mulArithmeticFragment allocation.result left right
              allocation.temporaries).toList arithmeticState =
          some { control := .fallthrough, state := final } ∧
        final.RegistersContain allocation.result
          (roundedBinaryInterval .mul leftLo leftHi rightLo rightHi) := by
    intro arithmeticState leftLo leftHi rightLo rightHi hleftState hrightState
    rcases hleftState with ⟨hleftLo, hleftHi⟩
    rcases hrightState with ⟨hrightLo, hrightHi⟩
    exact executeCompileMulArithmeticFragment module parameters thread
      arithmeticState left right builder leftLo leftHi rightLo rightHi
      hleftBelow hrightBelow hleftLo hleftHi hrightLo hrightHi
  simpa [compileMulAppendedCode, compileMul, compileMulAllocation, allocation]
    using executeGuardedArithmeticCode module parameters thread state .mul
      left right allocation.result builder
      (mulArithmeticFragment allocation.result left right
        allocation.temporaries).toList
      leftInterval rightInterval hleft hright harithmetic

/-! ## Production natural-power loop -/

private theorem guardedBinary_eq_whole_of_nonfinite
    (op : F64BinaryOp) (left right : KernelResult)
    (hstatus : (guardedBinary op left right).status =
      .nonfiniteIntermediate) :
    guardedBinary op left right = KernelResult.whole := by
  unfold guardedBinary at hstatus ⊢
  split <;> simp_all
  all_goals split <;> simp_all

@[simp] theorem powLoop_whole (count : Nat) (base : KernelResult) :
    powLoop count base KernelResult.whole = KernelResult.whole := by
  induction count with
  | zero => rfl
  | succ count induction =>
      rw [powLoop]
      have hguard : guardedBinary .mul KernelResult.whole base =
          KernelResult.whole := by
        simp [guardedBinary, KernelResult.whole]
      rw [hguard]
      exact induction

theorem compileMulAppendedCode_f64WritesAtOrAbove
    (left right : IntervalRegisters) (builder : Builder) :
    F64WritesAtOrAbove builder.nextF64
      (compileMulAppendedCode left right builder) := by
  intro destination hdestination
  rw [compileMulAppendedCode_f64Destinations] at hdestination
  exact allocateMulRegisters_destination_ge _ hdestination

/-- Recursive execution theorem for the exact multiplication loop emitted by
`compilePowLoop`.  The base and current accumulator start as normal
`KernelResult`s.  A guard branch stops lexical execution and corresponds to
the conservative result for all remaining iterations. -/
theorem executeCompilePowLoopAppendedCode
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (base : IntervalRegisters) (count : Nat)
    (current : IntervalRegisters) (builder : Builder)
    (baseInterval currentInterval : F64Interval)
    (hbaseBelow : base.Below builder.nextF64)
    (hcurrentBelow : current.Below builder.nextF64)
    (hbase : state.RegistersContain base baseInterval)
    (hcurrent : state.RegistersContain current currentInterval) :
    ∃ execution,
      executeCode module parameters thread
          (compilePowLoopAppendedCode base count current builder) state =
        some execution ∧
      ExpressionCodeOutcome (compilePowLoop base count current builder).1
        (powLoop count
          { interval := baseInterval, status := .ok }
          { interval := currentInterval, status := .ok }) execution := by
  induction count generalizing state current builder currentInterval with
  | zero =>
      let execution : CodeExecution := { control := .fallthrough, state }
      refine ⟨execution, rfl, ?_⟩
      exact ⟨rfl, hcurrent⟩
  | succ count induction =>
      let next := compileMul current base builder
      let baseResult : KernelResult := {
        interval := baseInterval, status := .ok }
      let currentResult : KernelResult := {
        interval := currentInterval, status := .ok }
      let stepResult := guardedBinary .mul currentResult baseResult
      rcases executeCompileMulAppendedCode_guarded module parameters thread
        state current base builder currentInterval baseInterval
        hcurrentBelow hbaseBelow hcurrent hbase with
        ⟨stepExecution, hstepExecute, hstepOutcome⟩
      change ExpressionCodeOutcome next.1 stepResult stepExecution at hstepOutcome
      cases stepExecution with
      | mk stepControl stepState =>
          cases hstepStatus : stepResult.status with
          | nonfiniteIntermediate =>
              have hstepWhole : stepResult = KernelResult.whole :=
                guardedBinary_eq_whole_of_nonfinite .mul currentResult
                  baseResult hstepStatus
              have hcontrol : stepControl = .jump wholeLabel := by
                simpa [ExpressionCodeOutcome, stepResult, hstepStatus]
                  using hstepOutcome
              subst stepControl
              let execution : CodeExecution := {
                control := .jump wholeLabel, state := stepState }
              refine ⟨execution, ?_, ?_⟩
              · exact executeCode_append_jump module parameters thread
                  (compileMulAppendedCode current base builder)
                  (compilePowLoopAppendedCode base count next.1 next.2)
                  state stepState wholeLabel hstepExecute
              · have hpLoop : powLoop count baseResult stepResult =
                    KernelResult.whole := by
                  rw [hstepWhole]
                  exact powLoop_whole count baseResult
                change ExpressionCodeOutcome
                  (compilePowLoop base count next.1 next.2).1
                  (powLoop count baseResult stepResult) execution
                rw [hpLoop]
                rfl
          | ok =>
              have hstepFallthrough : stepControl = .fallthrough ∧
                  stepState.RegistersContain next.1 stepResult.interval := by
                simpa [ExpressionCodeOutcome, stepResult, hstepStatus, next]
                  using hstepOutcome
              rcases hstepFallthrough with ⟨hcontrol, hnext⟩
              subst stepControl
              have hstepEq : stepResult = {
                  interval := stepResult.interval, status := .ok } := by
                cases hvalue : stepResult with
                | mk interval status =>
                    simp only [hvalue] at hstepStatus ⊢
                    cases status <;> simp_all
              have hbasePreserved :
                  stepState.RegistersContain base baseInterval := by
                rcases hbase with ⟨hbaseLo, hbaseHi⟩
                constructor
                · rw [executeCode_preservesF64_below module parameters thread
                    (compileMulAppendedCode current base builder) state
                    { control := .fallthrough, state := stepState }
                    builder.nextF64 base.lo.index
                    (compileMulAppendedCode_f64WritesAtOrAbove
                      current base builder)
                    hbaseBelow.1 hstepExecute]
                  exact hbaseLo
                · rw [executeCode_preservesF64_below module parameters thread
                    (compileMulAppendedCode current base builder) state
                    { control := .fallthrough, state := stepState }
                    builder.nextF64 base.hi.index
                    (compileMulAppendedCode_f64WritesAtOrAbove
                      current base builder)
                    hbaseBelow.2 hstepExecute]
                  exact hbaseHi
              have hbaseNext : base.Below next.2.nextF64 :=
                hbaseBelow.mono (by
                  rw [compileMul_nextF64]
                  exact Nat.le_add_right _ _)
              have hnextBelow : next.1.Below next.2.nextF64 :=
                compileMul_result_below current base builder
              rcases induction stepState next.1 next.2 stepResult.interval
                hbaseNext hnextBelow hbasePreserved hnext with
                ⟨finalExecution, hrestExecute, hrestOutcome⟩
              refine ⟨finalExecution, ?_, ?_⟩
              · exact executeCode_append_fallthrough module parameters thread
                  (compileMulAppendedCode current base builder)
                  (compilePowLoopAppendedCode base count next.1 next.2)
                  state stepState hstepExecute |>.trans hrestExecute
              · change ExpressionCodeOutcome
                    (compilePowLoop base count next.1 next.2).1
                    (powLoop count baseResult stepResult) finalExecution
                rw [hstepEq]
                simpa [baseResult] using hrestOutcome

/-! ## Whole recursive expression compiler -/

private theorem registersContain_of_f64WritesAtOrAbove
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial : MachineState)
    (execution : CodeExecution) (frontier : Nat)
    (registers : IntervalRegisters) (interval : F64Interval)
    (hwrites : F64WritesAtOrAbove frontier code)
    (hbelow : registers.Below frontier)
    (hcontain : initial.RegistersContain registers interval)
    (hexecute : executeCode module parameters thread code initial =
      some execution) :
    execution.state.RegistersContain registers interval := by
  rcases hcontain with ⟨hlo, hhi⟩
  constructor
  · rw [executeCode_preservesF64_below module parameters thread code initial
      execution frontier registers.lo.index hwrites hbelow.1 hexecute]
    exact hlo
  · rw [executeCode_preservesF64_below module parameters thread code initial
      execution frontier registers.hi.index hwrites hbelow.2 hexecute]
    exact hhi

private theorem expressionExecutionRefines_of_outcome
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (initial : MachineState) (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder)
    (result : KernelResult) (execution : CodeExecution)
    (hrowBase : rowBase.index < builder.nextU64)
    (hexecute : executeCode module parameters thread
      (compileExprAppendedCode rowBase expression builder) initial =
        some execution)
    (houtcome : ExpressionCodeOutcome
      (compileExpr rowBase expression builder).1 result execution) :
    ExpressionExecutionRefines rowBase initial
      (compileExpr rowBase expression builder).1 result execution := by
  rcases executeCompileExprAppendedCode_preservesRowBaseAndMemory
    module parameters thread initial rowBase expression builder execution
    hrowBase hexecute with ⟨hrowBasePreserved, hmemory⟩
  exact ⟨houtcome, hrowBasePreserved, hmemory⟩

private theorem executeCompileExprConstAppendedCode_refines
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (rowBase : Reg .u64)
    (environment : Array F64Interval) (value : IntervalBits)
    (builder : Builder) (result : KernelResult)
    (hrowBase : rowBase.index < builder.nextU64)
    (heval : PolynomialExpr.evalKernel environment (.const value) =
      some result) :
    ∃ execution,
      executeCode module parameters thread
          (compileExprAppendedCode rowBase (.const value) builder) state =
        some execution ∧
      ExpressionExecutionRefines rowBase state
        (compileExpr rowBase (.const value) builder).1 result execution := by
  cases hlo : decodeF64Bits value.lo.value with
  | none =>
      simp [PolynomialExpr.evalKernel, IntervalBits.decodeF64Interval?, hlo]
        at heval
  | some lo =>
      cases hhi : decodeF64Bits value.hi.value with
      | none =>
          simp [PolynomialExpr.evalKernel, IntervalBits.decodeF64Interval?,
            hlo, hhi] at heval
      | some hi =>
          simp [PolynomialExpr.evalKernel, IntervalBits.decodeF64Interval?,
            hlo, hhi] at heval
          subst result
          rcases executeCompileConstAppendedCode module parameters thread state
            value builder lo hi hlo hhi with ⟨final, hexecute, hcontain⟩
          let execution : CodeExecution := {
            control := .fallthrough, state := final }
          have hexecute' : executeCode module parameters thread
              (compileExprAppendedCode rowBase (.const value) builder) state =
                some execution := by
            simpa [compileExprAppendedCode, execution] using hexecute
          refine ⟨execution, hexecute', ?_⟩
          apply expressionExecutionRefines_of_outcome module parameters thread
            state rowBase (.const value) builder
            { interval := { lo, hi }, status := .ok } execution
            hrowBase hexecute'
          simpa [ExpressionCodeOutcome, compileExpr, execution] using hcontain

private theorem executeCompileExprVarAppendedCode_refines
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (rowBase : Reg .u64) (rowAddress : Nat)
    (environment : Array F64Interval) (index : Nat) (builder : Builder)
    (result : KernelResult)
    (hrowBase : rowBase.index < builder.nextU64)
    (henvironment : state.ContainsIntervalEnvironment
      rowBase rowAddress environment)
    (heval : PolynomialExpr.evalKernel environment (.var index) =
      some result) :
    ∃ execution,
      executeCode module parameters thread
          (compileExprAppendedCode rowBase (.var index) builder) state =
        some execution ∧
      ExpressionExecutionRefines rowBase state
        (compileExpr rowBase (.var index) builder).1 result execution := by
  cases hget : environment[index]? with
  | none =>
      simp [PolynomialExpr.evalKernel, hget] at heval
  | some interval =>
      simp [PolynomialExpr.evalKernel, hget] at heval
      subst result
      have hloads := henvironment.2 index interval hget
      rcases executeCompileVarAppendedCode module parameters thread state
        rowBase index builder rowAddress interval henvironment.1
        hloads.1 hloads.2 with ⟨final, hexecute, hcontain⟩
      let execution : CodeExecution := {
        control := .fallthrough, state := final }
      have hexecute' : executeCode module parameters thread
          (compileExprAppendedCode rowBase (.var index) builder) state =
            some execution := by
        simpa [compileExprAppendedCode, execution] using hexecute
      refine ⟨execution, hexecute', ?_⟩
      apply expressionExecutionRefines_of_outcome module parameters thread
        state rowBase (.var index) builder
        { interval, status := .ok } execution hrowBase hexecute'
      simpa [ExpressionCodeOutcome, execution] using hcontain

private theorem executeCompileExprNegAppendedCode_refines
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (rowBase : Reg .u64)
    (argument : PolynomialExpr) (builder : Builder)
    (argumentResult result : KernelResult)
    (hrowBase : rowBase.index < builder.nextU64)
    (hresult : argumentResult.negate = result)
    (hargumentExecution : ∃ execution,
      executeCode module parameters thread
          (compileExprAppendedCode rowBase argument builder) state =
        some execution ∧
      ExpressionExecutionRefines rowBase state
        (compileExpr rowBase argument builder).1 argumentResult execution) :
    ∃ execution,
      executeCode module parameters thread
          (compileExprAppendedCode rowBase (.neg argument) builder) state =
        some execution ∧
      ExpressionExecutionRefines rowBase state
        (compileExpr rowBase (.neg argument) builder).1 result execution := by
  let argumentCompiled := compileExpr rowBase argument builder
  rcases hargumentExecution with
    ⟨argumentExecution, hargumentExecute, hargumentRefines⟩
  rcases hargumentRefines with
    ⟨hargumentOutcome, hargumentRowBase, hargumentMemory⟩
  cases argumentExecution with
  | mk argumentControl argumentState =>
      cases hstatus : argumentResult.status with
      | nonfiniteIntermediate =>
          have hcontrol : argumentControl = .jump wholeLabel := by
            simpa [ExpressionCodeOutcome, hstatus] using hargumentOutcome
          subst argumentControl
          let execution : CodeExecution := {
            control := .jump wholeLabel, state := argumentState }
          have hexecute : executeCode module parameters thread
              (compileExprAppendedCode rowBase (.neg argument) builder) state =
                some execution := by
            apply executeCode_append_jump module parameters thread
              (compileExprAppendedCode rowBase argument builder)
              (compileNegAppendedCode argumentCompiled.1 argumentCompiled.2)
              state argumentState wholeLabel hargumentExecute
          refine ⟨execution, hexecute, ?_⟩
          apply expressionExecutionRefines_of_outcome module parameters thread
            state rowBase (.neg argument) builder result execution hrowBase
            hexecute
          subst result
          rw [show argumentResult.negate = KernelResult.whole by
            simp [KernelResult.negate, hstatus]]
          rfl
      | ok =>
          have hfallthrough : argumentControl = .fallthrough ∧
              argumentState.RegistersContain argumentCompiled.1
                argumentResult.interval := by
            simpa [ExpressionCodeOutcome, hstatus, argumentCompiled]
              using hargumentOutcome
          rcases hfallthrough with ⟨hcontrol, hargumentContain⟩
          subst argumentControl
          rcases executeCompileNegAppendedCode module parameters thread
            argumentState argumentCompiled.1 argumentCompiled.2
            argumentResult.interval
            (compileExpr_result_below rowBase argument builder)
            hargumentContain with ⟨final, htailExecute, hcontain⟩
          let execution : CodeExecution := {
            control := .fallthrough, state := final }
          have hexecute : executeCode module parameters thread
              (compileExprAppendedCode rowBase (.neg argument) builder) state =
                some execution := by
            exact executeCode_append_fallthrough module parameters thread
              (compileExprAppendedCode rowBase argument builder)
              (compileNegAppendedCode argumentCompiled.1 argumentCompiled.2)
              state argumentState hargumentExecute |>.trans htailExecute
          refine ⟨execution, hexecute, ?_⟩
          apply expressionExecutionRefines_of_outcome module parameters thread
            state rowBase (.neg argument) builder result execution hrowBase
            hexecute
          subst result
          simpa [ExpressionCodeOutcome, KernelResult.negate, hstatus,
            compileExpr, argumentCompiled, execution] using hcontain

/-- Compose already-evaluated left and right children with one guarded parent
node.  The right child may itself branch; if it falls through, its fresh-write
contract recovers the earlier left result before invoking the node theorem. -/
private theorem executeOkBinaryChildren
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (initial leftState : MachineState) (rowBase : Reg .u64)
    (left right : PolynomialExpr) (builder : Builder)
    (leftResult rightResult : KernelResult)
    (op : F64BinaryOp) (nodeCode : List Instruction)
    (parentRegisters : IntervalRegisters)
    (hleftStatus : leftResult.status = .ok)
    (hleftExecute : executeCode module parameters thread
      (compileExprAppendedCode rowBase left builder) initial =
        some { control := .fallthrough, state := leftState })
    (hleftContain : leftState.RegistersContain
      (compileExpr rowBase left builder).1 leftResult.interval)
    (hrightExecution : ∃ execution,
      executeCode module parameters thread
          (compileExprAppendedCode rowBase right
            (compileExpr rowBase left builder).2) leftState = some execution ∧
      ExpressionExecutionRefines rowBase leftState
        (compileExpr rowBase right
          (compileExpr rowBase left builder).2).1 rightResult execution)
    (hnode : ∀ nodeState,
      rightResult.status = .ok →
      nodeState.RegistersContain (compileExpr rowBase left builder).1
          leftResult.interval →
      nodeState.RegistersContain
          (compileExpr rowBase right
            (compileExpr rowBase left builder).2).1 rightResult.interval →
      ∃ execution,
        executeCode module parameters thread nodeCode nodeState =
          some execution ∧
        ExpressionCodeOutcome parentRegisters
          (guardedBinary op leftResult rightResult) execution) :
    ∃ execution,
      executeCode module parameters thread
          (compileExprAppendedCode rowBase left builder ++
            compileExprAppendedCode rowBase right
              (compileExpr rowBase left builder).2 ++ nodeCode) initial =
        some execution ∧
      ExpressionCodeOutcome parentRegisters
        (guardedBinary op leftResult rightResult) execution := by
  let leftCompiled := compileExpr rowBase left builder
  let rightCompiled := compileExpr rowBase right leftCompiled.2
  rcases hrightExecution with ⟨rightExecution, hrightExecute, hrightRefines⟩
  rcases hrightRefines with ⟨hrightOutcome, _, _⟩
  cases rightExecution with
  | mk rightControl rightState =>
      cases hrightStatus : rightResult.status with
      | nonfiniteIntermediate =>
          have hcontrol : rightControl = .jump wholeLabel := by
            simpa [ExpressionCodeOutcome, hrightStatus, rightCompiled]
              using hrightOutcome
          subst rightControl
          have hrightAndNode := executeCode_append_jump module parameters thread
            (compileExprAppendedCode rowBase right leftCompiled.2) nodeCode
            leftState rightState wholeLabel hrightExecute
          let execution : CodeExecution := {
            control := .jump wholeLabel, state := rightState }
          refine ⟨execution, ?_, ?_⟩
          · simpa [List.append_assoc, leftCompiled, execution] using
              (executeCode_append_fallthrough module parameters thread
                (compileExprAppendedCode rowBase left builder)
                (compileExprAppendedCode rowBase right leftCompiled.2 ++ nodeCode)
                initial leftState hleftExecute |>.trans hrightAndNode)
          · have hwhole : guardedBinary op leftResult rightResult =
                KernelResult.whole := by
              simp [guardedBinary, hleftStatus, hrightStatus]
            rw [hwhole]
            rfl
      | ok =>
          have hrightFallthrough : rightControl = .fallthrough ∧
              rightState.RegistersContain rightCompiled.1
                rightResult.interval := by
            simpa [ExpressionCodeOutcome, hrightStatus, rightCompiled]
              using hrightOutcome
          rcases hrightFallthrough with ⟨hcontrol, hrightContain⟩
          subst rightControl
          have hleftPreserved : rightState.RegistersContain leftCompiled.1
              leftResult.interval := by
            exact registersContain_of_f64WritesAtOrAbove
              module parameters thread
              (compileExprAppendedCode rowBase right leftCompiled.2)
              leftState { control := .fallthrough, state := rightState }
              leftCompiled.2.nextF64 leftCompiled.1 leftResult.interval
              (compileExprAppendedCode_f64WritesAtOrAbove
                rowBase right leftCompiled.2)
              (compileExpr_result_below rowBase left builder)
              hleftContain hrightExecute
          rcases hnode rightState hrightStatus hleftPreserved hrightContain with
            ⟨nodeExecution, hnodeExecute, hnodeOutcome⟩
          have hrightAndNode := executeCode_append_fallthrough
            module parameters thread
            (compileExprAppendedCode rowBase right leftCompiled.2) nodeCode
            leftState rightState hrightExecute |>.trans hnodeExecute
          refine ⟨nodeExecution, ?_, hnodeOutcome⟩
          simpa [List.append_assoc, leftCompiled] using
            (executeCode_append_fallthrough module parameters thread
              (compileExprAppendedCode rowBase left builder)
              (compileExprAppendedCode rowBase right leftCompiled.2 ++ nodeCode)
              initial leftState hleftExecute |>.trans hrightAndNode)

/-- **Recursive production expression execution theorem.**

For the exact instruction suffix appended by `compileExpr`, every successful
`evalKernel` result has the same structured-machine control outcome.  Normal
results fall through with their interval in the compiler-selected registers;
the conservative result is an exact jump to `wholeLabel`.  The theorem also
preserves the prologue's row-base register and the complete input memory so
the result composes across sibling expressions. -/
theorem executeCompileExprAppendedCode
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (rowBase : Reg .u64) (rowAddress : Nat)
    (environment : Array F64Interval) (expression : PolynomialExpr)
    (builder : Builder) (result : KernelResult)
    (hrowBase : rowBase.index < builder.nextU64)
    (henvironment : state.ContainsIntervalEnvironment
      rowBase rowAddress environment)
    (heval : expression.evalKernel environment = some result) :
    ∃ execution,
      executeCode module parameters thread
          (compileExprAppendedCode rowBase expression builder) state =
        some execution ∧
      ExpressionExecutionRefines rowBase state
        (compileExpr rowBase expression builder).1 result execution := by
  induction expression generalizing state builder result with
  | const value =>
      exact executeCompileExprConstAppendedCode_refines module parameters thread
        state rowBase environment value builder result hrowBase heval
  | var index =>
      exact executeCompileExprVarAppendedCode_refines module parameters thread
        state rowBase rowAddress environment index builder result hrowBase
        henvironment heval
  | neg argument induction =>
      cases hargumentEval : argument.evalKernel environment with
      | none =>
          simp [PolynomialExpr.evalKernel, hargumentEval] at heval
      | some argumentResult =>
          have hresult : argumentResult.negate = result := by
            simpa [PolynomialExpr.evalKernel, hargumentEval] using heval
          apply executeCompileExprNegAppendedCode_refines module parameters
            thread state rowBase argument builder argumentResult result
            hrowBase hresult
          exact induction state builder argumentResult hrowBase henvironment
            hargumentEval
  | add left right leftInduction rightInduction =>
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      let nodeCode := compileAddAppendedCode
        leftCompiled.1 rightCompiled.1 rightCompiled.2
      cases hleftEval : left.evalKernel environment with
      | none =>
          simp [PolynomialExpr.evalKernel, hleftEval] at heval
      | some leftResult =>
          rcases leftInduction state builder leftResult hrowBase henvironment
            hleftEval with ⟨leftExecution, hleftExecute, hleftRefines⟩
          rcases hleftRefines with
            ⟨hleftOutcome, hleftRowBase, hleftMemory⟩
          cases leftExecution with
          | mk leftControl leftState =>
              cases hleftStatus : leftResult.status with
              | nonfiniteIntermediate =>
                  have hcontrol : leftControl = .jump wholeLabel := by
                    simpa [ExpressionCodeOutcome, hleftStatus, leftCompiled]
                      using hleftOutcome
                  subst leftControl
                  have hresultWhole : result = KernelResult.whole := by
                    simpa [PolynomialExpr.evalKernel, hleftEval, hleftStatus]
                      using heval.symm
                  subst result
                  let execution : CodeExecution := {
                    control := .jump wholeLabel, state := leftState }
                  have hexecute : executeCode module parameters thread
                      (compileExprAppendedCode rowBase (.add left right) builder)
                      state = some execution := by
                    simpa [compileExprAppendedCode, leftCompiled, rightCompiled,
                      nodeCode, List.append_assoc, execution] using
                      (executeCode_append_jump module parameters thread
                        (compileExprAppendedCode rowBase left builder)
                        (compileExprAppendedCode rowBase right leftCompiled.2 ++
                          nodeCode) state leftState wholeLabel hleftExecute)
                  refine ⟨execution, hexecute, ?_⟩
                  apply expressionExecutionRefines_of_outcome module parameters
                    thread state rowBase (.add left right) builder
                    KernelResult.whole execution hrowBase hexecute
                  rfl
              | ok =>
                  have hleftFallthrough : leftControl = .fallthrough ∧
                      leftState.RegistersContain leftCompiled.1
                        leftResult.interval := by
                    simpa [ExpressionCodeOutcome, hleftStatus, leftCompiled]
                      using hleftOutcome
                  rcases hleftFallthrough with ⟨hcontrol, hleftContain⟩
                  subst leftControl
                  have hleftEnvironment : leftState.ContainsIntervalEnvironment
                      rowBase rowAddress environment :=
                    henvironment.of_preserved hleftRowBase hleftMemory
                  have hrowBaseRight :
                      rowBase.index < leftCompiled.2.nextU64 :=
                    Nat.lt_of_lt_of_le hrowBase
                      (compileExpr_nextU64_mono rowBase left builder)
                  cases hrightEval : right.evalKernel environment with
                  | none =>
                      simp [PolynomialExpr.evalKernel, hleftEval, hleftStatus,
                        hrightEval] at heval
                  | some rightResult =>
                      have hsemantic :
                          guardedBinary .add leftResult rightResult = result := by
                        simpa [PolynomialExpr.evalKernel, hleftEval, hleftStatus,
                          hrightEval] using heval
                      have hrightExecution := rightInduction leftState
                        leftCompiled.2 rightResult hrowBaseRight hleftEnvironment
                        hrightEval
                      have hpair := compileExpr_pair_below rowBase left right builder
                      have hcomposed := executeOkBinaryChildren module parameters
                        thread state leftState rowBase left right builder
                        leftResult rightResult .add nodeCode
                        (compileAdd leftCompiled.1 rightCompiled.1
                          rightCompiled.2).1 hleftStatus hleftExecute
                        hleftContain hrightExecution (by
                          intro nodeState hrightStatus hleftNode hrightNode
                          simpa [nodeCode, guardedBinary, hleftStatus,
                            hrightStatus]
                            using executeCompileAddAppendedCode_guarded
                              module parameters thread nodeState
                              leftCompiled.1 rightCompiled.1 rightCompiled.2
                              leftResult.interval rightResult.interval
                              hpair.1 hpair.2 hleftNode hrightNode)
                      rcases hcomposed with
                        ⟨execution, hexecuteChildren, houtcome⟩
                      have hexecute : executeCode module parameters thread
                          (compileExprAppendedCode rowBase (.add left right)
                            builder) state = some execution := by
                        simpa [compileExprAppendedCode, leftCompiled,
                          rightCompiled, nodeCode] using hexecuteChildren
                      refine ⟨execution, hexecute, ?_⟩
                      apply expressionExecutionRefines_of_outcome module
                        parameters thread state rowBase (.add left right)
                        builder result execution hrowBase hexecute
                      rw [← hsemantic]
                      simpa [compileExpr, leftCompiled, rightCompiled, nodeCode]
                        using houtcome
  | sub left right leftInduction rightInduction =>
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      let nodeCode := compileSubAppendedCode
        leftCompiled.1 rightCompiled.1 rightCompiled.2
      cases hleftEval : left.evalKernel environment with
      | none =>
          simp [PolynomialExpr.evalKernel, hleftEval] at heval
      | some leftResult =>
          rcases leftInduction state builder leftResult hrowBase henvironment
            hleftEval with ⟨leftExecution, hleftExecute, hleftRefines⟩
          rcases hleftRefines with
            ⟨hleftOutcome, hleftRowBase, hleftMemory⟩
          cases leftExecution with
          | mk leftControl leftState =>
              cases hleftStatus : leftResult.status with
              | nonfiniteIntermediate =>
                  have hcontrol : leftControl = .jump wholeLabel := by
                    simpa [ExpressionCodeOutcome, hleftStatus, leftCompiled]
                      using hleftOutcome
                  subst leftControl
                  have hresultWhole : result = KernelResult.whole := by
                    simpa [PolynomialExpr.evalKernel, hleftEval, hleftStatus]
                      using heval.symm
                  subst result
                  let execution : CodeExecution := {
                    control := .jump wholeLabel, state := leftState }
                  have hexecute : executeCode module parameters thread
                      (compileExprAppendedCode rowBase (.sub left right) builder)
                      state = some execution := by
                    simpa [compileExprAppendedCode, leftCompiled, rightCompiled,
                      nodeCode, List.append_assoc, execution] using
                      (executeCode_append_jump module parameters thread
                        (compileExprAppendedCode rowBase left builder)
                        (compileExprAppendedCode rowBase right leftCompiled.2 ++
                          nodeCode) state leftState wholeLabel hleftExecute)
                  refine ⟨execution, hexecute, ?_⟩
                  apply expressionExecutionRefines_of_outcome module parameters
                    thread state rowBase (.sub left right) builder
                    KernelResult.whole execution hrowBase hexecute
                  rfl
              | ok =>
                  have hleftFallthrough : leftControl = .fallthrough ∧
                      leftState.RegistersContain leftCompiled.1
                        leftResult.interval := by
                    simpa [ExpressionCodeOutcome, hleftStatus, leftCompiled]
                      using hleftOutcome
                  rcases hleftFallthrough with ⟨hcontrol, hleftContain⟩
                  subst leftControl
                  have hleftEnvironment : leftState.ContainsIntervalEnvironment
                      rowBase rowAddress environment :=
                    henvironment.of_preserved hleftRowBase hleftMemory
                  have hrowBaseRight :
                      rowBase.index < leftCompiled.2.nextU64 :=
                    Nat.lt_of_lt_of_le hrowBase
                      (compileExpr_nextU64_mono rowBase left builder)
                  cases hrightEval : right.evalKernel environment with
                  | none =>
                      simp [PolynomialExpr.evalKernel, hleftEval, hleftStatus,
                        hrightEval] at heval
                  | some rightResult =>
                      have hsemantic :
                          guardedBinary .sub leftResult rightResult = result := by
                        simpa [PolynomialExpr.evalKernel, hleftEval, hleftStatus,
                          hrightEval] using heval
                      have hrightExecution := rightInduction leftState
                        leftCompiled.2 rightResult hrowBaseRight hleftEnvironment
                        hrightEval
                      have hpair := compileExpr_pair_below rowBase left right builder
                      have hcomposed := executeOkBinaryChildren module parameters
                        thread state leftState rowBase left right builder
                        leftResult rightResult .sub nodeCode
                        (compileSub leftCompiled.1 rightCompiled.1
                          rightCompiled.2).1 hleftStatus hleftExecute
                        hleftContain hrightExecution (by
                          intro nodeState hrightStatus hleftNode hrightNode
                          simpa [nodeCode, guardedBinary, hleftStatus,
                            hrightStatus]
                            using executeCompileSubAppendedCode_guarded
                              module parameters thread nodeState
                              leftCompiled.1 rightCompiled.1 rightCompiled.2
                              leftResult.interval rightResult.interval
                              hpair.1 hpair.2 hleftNode hrightNode)
                      rcases hcomposed with
                        ⟨execution, hexecuteChildren, houtcome⟩
                      have hexecute : executeCode module parameters thread
                          (compileExprAppendedCode rowBase (.sub left right)
                            builder) state = some execution := by
                        simpa [compileExprAppendedCode, leftCompiled,
                          rightCompiled, nodeCode] using hexecuteChildren
                      refine ⟨execution, hexecute, ?_⟩
                      apply expressionExecutionRefines_of_outcome module
                        parameters thread state rowBase (.sub left right)
                        builder result execution hrowBase hexecute
                      rw [← hsemantic]
                      simpa [compileExpr, leftCompiled, rightCompiled, nodeCode]
                        using houtcome
  | mul left right leftInduction rightInduction =>
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      let nodeCode := compileMulAppendedCode
        leftCompiled.1 rightCompiled.1 rightCompiled.2
      cases hleftEval : left.evalKernel environment with
      | none =>
          simp [PolynomialExpr.evalKernel, hleftEval] at heval
      | some leftResult =>
          rcases leftInduction state builder leftResult hrowBase henvironment
            hleftEval with ⟨leftExecution, hleftExecute, hleftRefines⟩
          rcases hleftRefines with
            ⟨hleftOutcome, hleftRowBase, hleftMemory⟩
          cases leftExecution with
          | mk leftControl leftState =>
              cases hleftStatus : leftResult.status with
              | nonfiniteIntermediate =>
                  have hcontrol : leftControl = .jump wholeLabel := by
                    simpa [ExpressionCodeOutcome, hleftStatus, leftCompiled]
                      using hleftOutcome
                  subst leftControl
                  have hresultWhole : result = KernelResult.whole := by
                    simpa [PolynomialExpr.evalKernel, hleftEval, hleftStatus]
                      using heval.symm
                  subst result
                  let execution : CodeExecution := {
                    control := .jump wholeLabel, state := leftState }
                  have hexecute : executeCode module parameters thread
                      (compileExprAppendedCode rowBase (.mul left right) builder)
                      state = some execution := by
                    simpa [compileExprAppendedCode, leftCompiled, rightCompiled,
                      nodeCode, List.append_assoc, execution] using
                      (executeCode_append_jump module parameters thread
                        (compileExprAppendedCode rowBase left builder)
                        (compileExprAppendedCode rowBase right leftCompiled.2 ++
                          nodeCode) state leftState wholeLabel hleftExecute)
                  refine ⟨execution, hexecute, ?_⟩
                  apply expressionExecutionRefines_of_outcome module parameters
                    thread state rowBase (.mul left right) builder
                    KernelResult.whole execution hrowBase hexecute
                  rfl
              | ok =>
                  have hleftFallthrough : leftControl = .fallthrough ∧
                      leftState.RegistersContain leftCompiled.1
                        leftResult.interval := by
                    simpa [ExpressionCodeOutcome, hleftStatus, leftCompiled]
                      using hleftOutcome
                  rcases hleftFallthrough with ⟨hcontrol, hleftContain⟩
                  subst leftControl
                  have hleftEnvironment : leftState.ContainsIntervalEnvironment
                      rowBase rowAddress environment :=
                    henvironment.of_preserved hleftRowBase hleftMemory
                  have hrowBaseRight :
                      rowBase.index < leftCompiled.2.nextU64 :=
                    Nat.lt_of_lt_of_le hrowBase
                      (compileExpr_nextU64_mono rowBase left builder)
                  cases hrightEval : right.evalKernel environment with
                  | none =>
                      simp [PolynomialExpr.evalKernel, hleftEval, hleftStatus,
                        hrightEval] at heval
                  | some rightResult =>
                      have hsemantic :
                          guardedBinary .mul leftResult rightResult = result := by
                        simpa [PolynomialExpr.evalKernel, hleftEval, hleftStatus,
                          hrightEval] using heval
                      have hrightExecution := rightInduction leftState
                        leftCompiled.2 rightResult hrowBaseRight hleftEnvironment
                        hrightEval
                      have hpair := compileExpr_pair_below rowBase left right builder
                      have hcomposed := executeOkBinaryChildren module parameters
                        thread state leftState rowBase left right builder
                        leftResult rightResult .mul nodeCode
                        (compileMul leftCompiled.1 rightCompiled.1
                          rightCompiled.2).1 hleftStatus hleftExecute
                        hleftContain hrightExecution (by
                          intro nodeState hrightStatus hleftNode hrightNode
                          simpa [nodeCode, guardedBinary, hleftStatus,
                            hrightStatus]
                            using executeCompileMulAppendedCode_guarded
                              module parameters thread nodeState
                              leftCompiled.1 rightCompiled.1 rightCompiled.2
                              leftResult.interval rightResult.interval
                              hpair.1 hpair.2 hleftNode hrightNode)
                      rcases hcomposed with
                        ⟨execution, hexecuteChildren, houtcome⟩
                      have hexecute : executeCode module parameters thread
                          (compileExprAppendedCode rowBase (.mul left right)
                            builder) state = some execution := by
                        simpa [compileExprAppendedCode, leftCompiled,
                          rightCompiled, nodeCode] using hexecuteChildren
                      refine ⟨execution, hexecute, ?_⟩
                      apply expressionExecutionRefines_of_outcome module
                        parameters thread state rowBase (.mul left right)
                        builder result execution hrowBase hexecute
                      rw [← hsemantic]
                      simpa [compileExpr, leftCompiled, rightCompiled, nodeCode]
                        using houtcome
  | powNat argument exponent induction =>
      cases hargumentEval : argument.evalKernel environment with
      | none =>
          simp [PolynomialExpr.evalKernel, hargumentEval] at heval
      | some argumentResult =>
          let argumentCompiled := compileExpr rowBase argument builder
          let one : IntervalBits := {
            lo := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
            hi := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
          }
          let initialCompiled := compileConst one argumentCompiled.2
          rcases induction state builder argumentResult hrowBase henvironment
            hargumentEval with
            ⟨argumentExecution, hargumentExecute, hargumentRefines⟩
          rcases hargumentRefines with
            ⟨hargumentOutcome, hargumentRowBase, hargumentMemory⟩
          cases argumentExecution with
          | mk argumentControl argumentState =>
              cases hargumentStatus : argumentResult.status with
              | nonfiniteIntermediate =>
                  have hcontrol : argumentControl = .jump wholeLabel := by
                    simpa [ExpressionCodeOutcome, hargumentStatus,
                      argumentCompiled] using hargumentOutcome
                  subst argumentControl
                  have hresultWhole : result = KernelResult.whole := by
                    simpa [PolynomialExpr.evalKernel, hargumentEval,
                      hargumentStatus] using heval.symm
                  subst result
                  let execution : CodeExecution := {
                    control := .jump wholeLabel, state := argumentState }
                  have hexecute : executeCode module parameters thread
                      (compileExprAppendedCode rowBase
                        (.powNat argument exponent) builder) state =
                        some execution := by
                    simpa [compileExprAppendedCode, argumentCompiled, one,
                      initialCompiled, List.append_assoc, execution] using
                      (executeCode_append_jump module parameters thread
                        (compileExprAppendedCode rowBase argument builder)
                        (compileConstAppendedCode one argumentCompiled.2 ++
                          compilePowLoopAppendedCode argumentCompiled.1 exponent
                            initialCompiled.1 initialCompiled.2)
                        state argumentState wholeLabel hargumentExecute)
                  refine ⟨execution, hexecute, ?_⟩
                  apply expressionExecutionRefines_of_outcome module parameters
                    thread state rowBase (.powNat argument exponent) builder
                    KernelResult.whole execution hrowBase hexecute
                  rfl
              | ok =>
                  have hargumentEq : argumentResult = {
                      interval := argumentResult.interval, status := .ok } := by
                    cases hvalue : argumentResult with
                    | mk interval status =>
                        simp only [hvalue] at hargumentStatus ⊢
                        cases status <;> simp_all
                  have hargumentFallthrough :
                      argumentControl = .fallthrough ∧
                        argumentState.RegistersContain argumentCompiled.1
                          argumentResult.interval := by
                    simpa [ExpressionCodeOutcome, hargumentStatus,
                      argumentCompiled] using hargumentOutcome
                  rcases hargumentFallthrough with
                    ⟨hcontrol, hargumentContain⟩
                  subst argumentControl
                  have honeDecode : decodeF64Bits one.lo.value =
                      some (.finite 1) := by
                    norm_num [one, decodeF64Bits, Binary64Bits.IsFinite,
                      Binary64Bits.exponentBits, Binary64Bits.fractionBits,
                      Binary64Bits.exponentAllOnes,
                      Binary64Bits.exponentModulus,
                      Binary64Bits.fractionModulus,
                      Binary64Finite.toReal, Binary64Finite.sign,
                      Binary64Finite.magnitude, Binary64Finite.significand,
                      Binary64Finite.exponent, Binary64Bits.signBit,
                      Binary64Bits.signThreshold]
                  have honeDecodeHi : decodeF64Bits one.hi.value =
                      some (.finite 1) := by
                    simpa [one] using honeDecode
                  rcases executeCompileConstAppendedCode module parameters thread
                    argumentState one argumentCompiled.2 (.finite 1) (.finite 1)
                    honeDecode honeDecodeHi with
                    ⟨initialState, hinitialExecute, hinitialContain⟩
                  have hbasePreserved : initialState.RegistersContain
                      argumentCompiled.1 argumentResult.interval := by
                    exact registersContain_of_f64WritesAtOrAbove
                      module parameters thread
                      (compileConstAppendedCode one argumentCompiled.2)
                      argumentState
                      { control := .fallthrough, state := initialState }
                      argumentCompiled.2.nextF64 argumentCompiled.1
                      argumentResult.interval
                      (by
                        intro destination hdestination
                        rw [compileConstAppendedCode_f64Destinations]
                          at hdestination
                        simp at hdestination
                        omega)
                      (compileExpr_result_below rowBase argument builder)
                      hargumentContain hinitialExecute
                  have hbaseBelow : argumentCompiled.1.Below
                      initialCompiled.2.nextF64 :=
                    (compileExpr_result_below rowBase argument builder).mono (by
                      rw [compileConst_nextF64]
                      exact Nat.le_add_right _ _)
                  have hinitialBelow : initialCompiled.1.Below
                      initialCompiled.2.nextF64 :=
                    compileConst_result_below one argumentCompiled.2
                  rcases executeCompilePowLoopAppendedCode module parameters
                    thread initialState argumentCompiled.1 exponent
                    initialCompiled.1 initialCompiled.2 argumentResult.interval
                    { lo := .finite 1, hi := .finite 1 }
                    hbaseBelow hinitialBelow hbasePreserved hinitialContain with
                    ⟨loopExecution, hloopExecute, hloopOutcome⟩
                  have hinitialAndLoop := executeCode_append_fallthrough
                    module parameters thread
                    (compileConstAppendedCode one argumentCompiled.2)
                    (compilePowLoopAppendedCode argumentCompiled.1 exponent
                      initialCompiled.1 initialCompiled.2)
                    argumentState initialState hinitialExecute |>.trans
                      hloopExecute
                  have hexecute : executeCode module parameters thread
                      (compileExprAppendedCode rowBase
                        (.powNat argument exponent) builder) state =
                        some loopExecution := by
                    simpa [compileExprAppendedCode, argumentCompiled, one,
                      initialCompiled, List.append_assoc] using
                      (executeCode_append_fallthrough module parameters thread
                        (compileExprAppendedCode rowBase argument builder)
                        (compileConstAppendedCode one argumentCompiled.2 ++
                          compilePowLoopAppendedCode argumentCompiled.1 exponent
                            initialCompiled.1 initialCompiled.2)
                        state argumentState hargumentExecute |>.trans
                          hinitialAndLoop)
                  have hsemantic : powLoop exponent argumentResult
                      { interval := { lo := .finite 1, hi := .finite 1 },
                        status := .ok } = result := by
                    simpa [PolynomialExpr.evalKernel, hargumentEval,
                      hargumentStatus] using heval
                  refine ⟨loopExecution, hexecute, ?_⟩
                  apply expressionExecutionRefines_of_outcome module parameters
                    thread state rowBase (.powNat argument exponent) builder
                    result loopExecution hrowBase hexecute
                  rw [← hsemantic]
                  rw [hargumentEq]
                  simpa [compileExpr, argumentCompiled, one, initialCompiled]
                    using hloopOutcome

end SparkInterval.PTX
