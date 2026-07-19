import SparkInterval.PTX.Emitter
import SparkInterval.PTX.Generator
import SparkInterval.PTX.MachineSemantics
import SparkInterval.PTX.CodeComposition
import SparkInterval.PTX.F64RegisterEffects
import SparkInterval.PTX.ExpressionInstructionRefinement
import SparkInterval.PTX.CompilerFiniteGuardRefinement
import SparkInterval.PTX.CompilerNodeRefinement
import SparkInterval.PTX.CompilerOutputRefinement
import SparkInterval.PTX.PrologueRefinement
import SparkInterval.PTX.OutputLayoutRefinement
import SparkInterval.PTX.StructuralCompilerCorrect
import SparkInterval.PTX.GeneratedKernelRunRefinement

/-!
# PTX compiler-correctness regression tests

These tests keep the six proof boundaries used by the generated-kernel trust
argument connected in one compile-time target:

* whole-expression bounded arithmetic;
* the complete typed-instruction machine model;
* exact compiler register freshness and arithmetic-node execution;
* the source-derived opcode contract for generated modules;
* deterministic, validated emission of the same typed module; and
* whole-module execution, output-ABI representation, and real containment.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.PTXCompilerCorrectness

open SparkInterval
open SparkInterval.PTX

private def sampleExpression : PolynomialExpr :=
  .add (.var 0) (.neg (.var 1))

private def sampleBatch : ReferenceBatch := {
  variableCount := 2
  expression := sampleExpression
  rowCount := 3
}

/-- The concrete generated module is tied to the independent source-expression
opcode specification, not merely to membership in an opcode allowlist. -/
example : opcodeTrace (buildModule sampleBatch).body =
    sampleBatch.expectedKernelOpcodeTrace := by
  exact buildModule_opcodeTrace sampleBatch

/-- Operand, register, immediate, offset, and label identity is covered by the
independent whole-source structural compiler specification. -/
example : buildModule sampleBatch =
    StructuralCompilerSpec.expectedModule sampleBatch := by
  exact StructuralCompilerCorrect.buildModule_eq_expectedModule sampleBatch

/-- The same representative generated module passes the structural validator
that gates the production emitter. -/
example : validate (buildModule sampleBatch) = .ok () := by
  native_decide

/-- The expression-level trace exposes the expected load, sign-bit operation,
finite guards, branches, and both directed additions. -/
example : sampleExpression.expectedOpcodeTrace =
    [.ldGlobalF64, .ldGlobalF64,
     .ldGlobalF64, .ldGlobalF64, .xorB64, .xorB64,
     .andB64, .setpEqU64, .bra, .andB64, .setpEqU64, .bra,
     .andB64, .setpEqU64, .bra, .andB64, .setpEqU64, .bra,
     .addRmF64, .addRpF64] := by
  rfl

/-- Exercise the whole-expression containment theorem at its public API. -/
example
    {realEnvironment : Array ℝ} {intervalEnvironment : Array F64Interval}
    (henvironments : PolynomialEnvironmentsCorrespond
      realEnvironment intervalEnvironment)
    {value : ℝ} {result : KernelResult}
    (hrealizes : sampleExpression.Realizes realEnvironment value)
    (heval : sampleExpression.evalKernel intervalEnvironment = some result) :
    result.interval.ContainsReal value := by
  exact PolynomialExpr.evalKernel_sound henvironments hrealizes heval

/-- The public in-range API composes the exact production module through
return and exposes an output record representing the evaluator result. -/
example
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
    ∃ final observed,
      run (buildModule batch) parameters thread (buildModule batch).body.size
          (MachineState.initial memory) = some final ∧
        observeOutput final.memory parameters.outputs
            (thread.ctaidX * thread.ntidX + thread.tidX) = some observed ∧
        OutputRepresents observed result := by
  exact runBuildModule_inRange batch parameters thread memory rows environment
    result hthread hlayout hin hmemory hrow heval

/-- The public out-of-range API reaches return without changing global
memory, so a rejected thread cannot write an output row. -/
example
    (batch : ReferenceBatch) (parameters : KernelParameters)
    (thread : ThreadContext) (memory : GlobalMemory)
    (hout : parameters.read .rowCount ≤ thread.globalIndex) :
    ∃ final,
      run (buildModule batch) parameters thread (buildModule batch).body.size
          (MachineState.initial memory) = some final ∧
        final.memory = memory := by
  exact runBuildModule_outOfRange batch parameters thread memory hout

/-- The strongest public API combines whole-module execution with the proved
source arithmetic and yields exact-real containment in the observed row. -/
example
    (batch : ReferenceBatch) (parameters : KernelParameters)
    (thread : ThreadContext) (memory : GlobalMemory)
    (rows : Array (Array F64Interval)) (environment : Array F64Interval)
    (realEnvironment : Array ℝ) (value : ℝ) (result : KernelResult)
    (hthread : thread.Safe)
    (hlayout : SafeKernelLayout parameters batch.variableCount)
    (hin : thread.ctaidX * thread.ntidX + thread.tidX < parameters.rowCount)
    (hmemory : MemoryEncodesRows memory parameters.rows batch.variableCount rows)
    (hrow : rows[thread.ctaidX * thread.ntidX + thread.tidX]? =
      some environment)
    (henvironments : PolynomialEnvironmentsCorrespond realEnvironment
      environment)
    (hrealizes : batch.expression.Realizes realEnvironment value)
    (heval : batch.expression.evalKernel environment = some result) :
    ∃ final observed,
      run (buildModule batch) parameters thread (buildModule batch).body.size
          (MachineState.initial memory) = some final ∧
        observeOutput final.memory parameters.outputs
            (thread.ctaidX * thread.ntidX + thread.tidX) = some observed ∧
        observed.interval.ContainsReal value := by
  exact runBuildModule_inRange_containsReal batch parameters thread memory rows
    environment realEnvironment value result hthread hlayout hin hmemory hrow
    henvironments hrealizes heval

private def labelModule : Module := {
  entryName := "sparkinterval_generated"
  variableCount := 0
  registers := { pred := 1, byte := 1, u32 := 1, u64 := 1, f64 := 1 }
  body := #[.label ⟨7⟩, .ret]
}

private def zeroParameters : KernelParameters := {
  rows := 0
  outputs := 0
  rowCount := 0
}

private def zeroThread : ThreadContext := {
  ctaidX := 0
  ntidX := 1
  tidX := 0
}

private def labelModuleReturnedState : MachineState :=
  { MachineState.initial GlobalMemory.empty with pc := 1, returned := true }

/-- The full machine model resolves typed labels at instruction positions. -/
example : labelPosition? labelModule ⟨7⟩ = some 0 := by
  native_decide

/-- Fuel-bounded execution covers label fetch, program-counter advance, and
typed return for a complete miniature module. -/
example : run labelModule zeroParameters zeroThread 2
    (MachineState.initial GlobalMemory.empty) = some labelModuleReturnedState := by
  rfl

/-- A returned state is stable under the fuel-bounded runner. -/
example (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (hreturned : state.returned = true) :
    run labelModule parameters thread 0 state = some state := by
  simp [run, hreturned]

/-- The modeled CUDA global index agrees with natural arithmetic whenever the
documented word-size bounds rule out wrapping. -/
example (thread : ThreadContext) (hsafe : thread.Safe) :
    thread.globalIndex = thread.ctaidX * thread.ntidX + thread.tidX := by
  exact ThreadContext.globalIndex_eq thread hsafe

/-- The concrete multiplication allocator supplies fourteen unique write
destinations for the exact emitted arithmetic fragment. -/
example (left right : IntervalRegisters) (builder : Builder) :
    (compileMulAllocation left right builder).destinationIndices.Nodup := by
  exact compileMul_destinationIndices_nodup left right builder

/-- The production finite-guard compiler appends the same exact six typed
instructions used by its operational refinement theorem. -/
example (value : IntervalRegisters) (builder : Builder) :
    (emitFiniteGuard value builder).body =
      builder.body ++ (compiledFiniteGuardInstructions value builder).toArray := by
  exact emitFiniteGuard_body value builder

/-- One generated output operation is literally the compiler's twelve typed
record-writing instructions. -/
example (outputBase : Reg .u64) (result : IntervalRegisters)
    (status : Fin 256) (builder : Builder) :
    (emitOutput outputBase result status builder).body =
      builder.body ++
        (compiledOutputInstructions outputBase result status builder).toArray := by
  exact emitOutput_body outputBase result status builder

/-- Structured code-slice execution composes on normal fallthrough. -/
example (module : Module) (parameters : KernelParameters)
    (thread : ThreadContext) (firstCode suffix : List Instruction)
    (initial middle : MachineState)
    (hfirst : executeCode module parameters thread firstCode initial =
      some { control := .fallthrough, state := middle }) :
    executeCode module parameters thread (firstCode ++ suffix) initial =
      executeCode module parameters thread suffix middle := by
  exact executeCode_append_fallthrough module parameters thread firstCode
    suffix initial middle hfirst

/-- Successful text emission preserves validation and is exactly the
deterministic rendering of the same typed module. -/
example {module : Module} {text : String}
    (hemits : emit module = .ok text) :
    validate module = .ok () ∧ text = renderUnchecked module := by
  exact emit_success hemits

/-- Conversely, validation is sufficient for deterministic successful
emission; this rules out a second, untyped text-selection path. -/
example {module : Module} (hvalidate : validate module = .ok ()) :
    emit module = .ok (renderUnchecked module) := by
  exact emit_of_validate hvalidate

/-- End-to-end smoke test for validation plus deterministic emission of a
representative generated kernel. -/
example : emit (buildModule sampleBatch) =
    .ok (renderUnchecked (buildModule sampleBatch)) := by
  apply emit_of_validate
  native_decide

end SparkInterval.Tests.PTXCompilerCorrectness
