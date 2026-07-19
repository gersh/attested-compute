import SparkInterval.PTX.GeneratedKernelStructuredRefinement
import SparkInterval.PTX.GeneratedKernelOutOfRangeRefinement
import SparkInterval.PTX.RunJumpRefinement
import SparkInterval.PTX.RunCompositionRefinement

/-!
# Whole-module refinement of generated in-range rows

This module lifts the structured in-range execution theorem to the public
fuel-bounded whole-module `run` interface.  Semantic evaluation and output
construction remain in `GeneratedKernelStructuredRefinement`; the proof here
uses exact module segments to account for program counters, taken labels, the
common return tail, and the uniform full-body fuel bound.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- **Whole-module in-range refinement for the exact production module.**

For an in-range safe thread whose selected input row is represented in global
memory, running the exact generated module with its full body size as fuel
returns successfully.  The public output-row observer exists in the returned
memory and represents the same result as `PolynomialExpr.evalKernel`.

The proof follows the generated control flow.  The normal case falls through
the prologue and expression, jumps from the ordinary output prefix to the
common done label, and executes the memory-preserving return tail.  The
nonfinite case resolves the expression jump to the whole label and executes
the whole suffix through `ret`. -/
theorem runBuildModule_inRange
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
  let initial := MachineState.initial memory
  rcases executeBuildModuleStructured_inRange batch parameters thread memory
      rows environment result hthread hlayout hin hmemory hrow heval with
    ⟨prologueState, expressionExecution, hprologue, hexpression, houtcome⟩
  have hinitialNotReturned : initial.returned = false := by
    rfl
  have hprologueSegment :
      ModuleBodySegmentAt (buildModule batch) initial.pc
        (generatedPrologueCode batch) := by
    simpa [initial, MachineState.initial] using
      buildModule_prologue_segment batch
  have hprologuePc : prologueState.pc = 17 := by
    have hpc := executeCode_fallthrough_pc (buildModule batch) parameters thread
      (generatedPrologueCode batch) initial prologueState hprologue
    simpa [initial, MachineState.initial] using hpc
  have hprologueNotReturned : prologueState.returned = false := by
    have hreturned := executeCode_fallthrough_returned (buildModule batch)
      parameters thread (generatedPrologueCode batch) initial prologueState
      hprologue
    exact hreturned.trans hinitialNotReturned
  have hexpressionSegment :
      ModuleBodySegmentAt (buildModule batch) prologueState.pc
        (generatedExpressionCode batch) := by
    rw [hprologuePc]
    exact buildModule_expression_segment batch
  cases houtcome with
  | normal _hstatus hexpressionControl outputState observed hepilogue hobserve
      hrepresents =>
      have hexpressionFallthrough :
          executeCode (buildModule batch) parameters thread
              (generatedExpressionCode batch) prologueState =
            some { control := .fallthrough, state := expressionExecution.state } := by
        rw [← hexpressionControl]
        exact hexpression
      have hexpressionPc : expressionExecution.state.pc =
          batch.expression.compiledInstructionCount + 17 := by
        have hpc := executeCode_fallthrough_pc (buildModule batch) parameters
          thread (generatedExpressionCode batch) prologueState
          expressionExecution.state hexpressionFallthrough
        rw [hprologuePc] at hpc
        simp at hpc
        omega
      have hexpressionNotReturned :
          expressionExecution.state.returned = false := by
        have hreturned := executeCode_fallthrough_returned (buildModule batch)
          parameters thread (generatedExpressionCode batch) prologueState
          expressionExecution.state hexpressionFallthrough
        exact hreturned.trans hprologueNotReturned
      have hnormalSegment :
          ModuleBodySegmentAt (buildModule batch) expressionExecution.state.pc
            (generatedNormalEpiloguePrefix batch) := by
        rw [hexpressionPc]
        exact buildModule_normalEpiloguePrefix_segment batch
      have houtputNotReturned : outputState.returned = false := by
        have hreturned := executeCode_jump_preserves_returned
          (buildModule batch) parameters thread
          (generatedNormalEpiloguePrefix batch) expressionExecution.state
          outputState doneLabel hepilogue
        exact hreturned.trans hexpressionNotReturned
      let donePc := batch.expression.compiledInstructionCount + 45
      let jumped : MachineState := { outputState with pc := donePc }
      let returnedFinal := generatedReturnState jumped
      rcases buildModule_doneLabel_segment batch with
        ⟨hdonePosition, hreturnSegmentAtDone⟩
      have hdoneTarget :
          labelPosition? (buildModule batch) doneLabel = some donePc := by
        simpa [donePc] using hdonePosition
      have hjumpedNotReturned : jumped.returned = false := by
        simpa [jumped] using houtputNotReturned
      have hreturnSegment :
          ModuleBodySegmentAt (buildModule batch) jumped.pc
            generatedReturnTail := by
        simpa [jumped, donePc] using hreturnSegmentAtDone
      rcases executeGeneratedReturnTail (buildModule batch) parameters thread
          jumped with ⟨hreturnExecutionRaw, hreturnMemoryRaw⟩
      have hreturnExecution :
          executeCode (buildModule batch) parameters thread generatedReturnTail
              jumped =
            some { control := .returned, state := returnedFinal } := by
        simpa [returnedFinal] using hreturnExecutionRaw
      have hreturnRun :
          run (buildModule batch) parameters thread generatedReturnTail.length
              jumped = some returnedFinal :=
        executeCode_returned_run_of_runStepCompatible_segment
          (buildModule batch) parameters thread generatedReturnTail jumped
          returnedFinal generatedReturnTail_runStepCompatible hreturnSegment
          hjumpedNotReturned hreturnExecution
      have hreturnedMemory : returnedFinal.memory = outputState.memory := by
        calc
          returnedFinal.memory = jumped.memory := by
            simpa [returnedFinal] using hreturnMemoryRaw
          _ = outputState.memory := by simp [jumped]
      have hreturnedObserve :
          observeOutput returnedFinal.memory parameters.outputs
              (thread.ctaidX * thread.ntidX + thread.tidX) = some observed := by
        rw [hreturnedMemory]
        exact hobserve
      rcases executeCode_jump_run_compose_of_runStepCompatible_segment
          (buildModule batch) parameters thread
          (generatedNormalEpiloguePrefix batch) expressionExecution.state
          outputState returnedFinal doneLabel donePc generatedReturnTail.length
          (generatedNormalEpiloguePrefix_runStepCompatible batch)
          hnormalSegment hexpressionNotReturned hdoneTarget hepilogue
          (by simpa [jumped] using hreturnRun) with
        ⟨normalSteps, _hnormalPositive, hnormalBound, hnormalRun⟩
      have hexpressionAndRestRun :
          run (buildModule batch) parameters thread
              ((generatedExpressionCode batch).length +
                (normalSteps + generatedReturnTail.length)) prologueState =
            some returnedFinal :=
        executeCode_fallthrough_run_compose_of_runStepCompatible_segment
          (buildModule batch) parameters thread (generatedExpressionCode batch)
          (normalSteps + generatedReturnTail.length) prologueState
          expressionExecution.state returnedFinal
          (generatedExpressionCode_runStepCompatible batch) hexpressionSegment
          hprologueNotReturned hexpressionFallthrough hnormalRun
      have hshortRun :
          run (buildModule batch) parameters thread
              ((generatedPrologueCode batch).length +
                ((generatedExpressionCode batch).length +
                  (normalSteps + generatedReturnTail.length))) initial =
            some returnedFinal :=
        executeCode_fallthrough_run_compose_of_runStepCompatible_segment
          (buildModule batch) parameters thread (generatedPrologueCode batch)
          ((generatedExpressionCode batch).length +
            (normalSteps + generatedReturnTail.length))
          initial prologueState returnedFinal
          (generatedPrologueCode_runStepCompatible batch) hprologueSegment
          hinitialNotReturned hprologue hexpressionAndRestRun
      have hnormalBound' : normalSteps ≤ 13 := by
        simpa using hnormalBound
      have hfuelBound :
          (generatedPrologueCode batch).length +
              ((generatedExpressionCode batch).length +
                (normalSteps + generatedReturnTail.length)) ≤
            (buildModule batch).body.size := by
        rw [buildModule_body_size]
        simp
        omega
      have huniformRun :
          run (buildModule batch) parameters thread
              (buildModule batch).body.size initial = some returnedFinal :=
        run_mono_of_eq_some (buildModule batch) parameters thread initial
          returnedFinal hfuelBound hshortRun
      refine ⟨returnedFinal, observed, ?_, hreturnedObserve, hrepresents⟩
      simpa [initial] using huniformRun
  | whole _hstatus hexpressionControl wholeFinal observed hepilogue _hnegative
      _hpositive hobserve hrepresents =>
      have hexpressionJump :
          executeCode (buildModule batch) parameters thread
              (generatedExpressionCode batch) prologueState =
            some {
              control := .jump wholeLabel
              state := expressionExecution.state
            } := by
        rw [← hexpressionControl]
        exact hexpression
      have hexpressionStateNotReturned :
          expressionExecution.state.returned = false := by
        have hreturned := executeCode_jump_preserves_returned
          (buildModule batch) parameters thread (generatedExpressionCode batch)
          prologueState expressionExecution.state wholeLabel hexpressionJump
        exact hreturned.trans hprologueNotReturned
      let wholePc := batch.expression.compiledInstructionCount + 30
      let jumped : MachineState :=
        { expressionExecution.state with pc := wholePc }
      rcases buildModule_wholeLabel_segment batch with
        ⟨hwholePosition, hwholeSegmentAtLabel⟩
      have hwholeTarget :
          labelPosition? (buildModule batch) wholeLabel = some wholePc := by
        simpa [wholePc] using hwholePosition
      have hjumpedNotReturned : jumped.returned = false := by
        simpa [jumped] using hexpressionStateNotReturned
      have hwholeSegment :
          ModuleBodySegmentAt (buildModule batch) jumped.pc
            (generatedWholeEpilogueSuffix batch) := by
        simpa [jumped, wholePc] using hwholeSegmentAtLabel
      have hwholeExecution :
          executeCode (buildModule batch) parameters thread
              (generatedWholeEpilogueSuffix batch) jumped =
            some { control := .returned, state := wholeFinal } := by
        simpa [jumped, wholePc] using hepilogue
      have hwholeRun :
          run (buildModule batch) parameters thread
              (generatedWholeEpilogueSuffix batch).length jumped =
            some wholeFinal :=
        executeCode_returned_run_of_runStepCompatible_segment
          (buildModule batch) parameters thread
          (generatedWholeEpilogueSuffix batch) jumped wholeFinal
          (generatedWholeEpilogueSuffix_runStepCompatible batch) hwholeSegment
          hjumpedNotReturned hwholeExecution
      rcases executeCode_jump_run_compose_of_runStepCompatible_segment
          (buildModule batch) parameters thread (generatedExpressionCode batch)
          prologueState expressionExecution.state wholeFinal wholeLabel wholePc
          (generatedWholeEpilogueSuffix batch).length
          (generatedExpressionCode_runStepCompatible batch) hexpressionSegment
          hprologueNotReturned hwholeTarget hexpressionJump
          (by simpa [jumped] using hwholeRun) with
        ⟨expressionSteps, _hexpressionPositive, hexpressionBound,
          hexpressionRun⟩
      have hshortRun :
          run (buildModule batch) parameters thread
              ((generatedPrologueCode batch).length +
                (expressionSteps +
                  (generatedWholeEpilogueSuffix batch).length)) initial =
            some wholeFinal :=
        executeCode_fallthrough_run_compose_of_runStepCompatible_segment
          (buildModule batch) parameters thread (generatedPrologueCode batch)
          (expressionSteps + (generatedWholeEpilogueSuffix batch).length)
          initial prologueState wholeFinal
          (generatedPrologueCode_runStepCompatible batch) hprologueSegment
          hinitialNotReturned hprologue hexpressionRun
      have hexpressionBound' : expressionSteps ≤
          batch.expression.compiledInstructionCount := by
        simpa using hexpressionBound
      have hfuelBound :
          (generatedPrologueCode batch).length +
              (expressionSteps +
                (generatedWholeEpilogueSuffix batch).length) ≤
            (buildModule batch).body.size := by
        rw [buildModule_body_size]
        simp
        omega
      have huniformRun :
          run (buildModule batch) parameters thread
              (buildModule batch).body.size initial = some wholeFinal :=
        run_mono_of_eq_some (buildModule batch) parameters thread initial
          wholeFinal hfuelBound hshortRun
      refine ⟨wholeFinal, observed, ?_, hobserve, hrepresents⟩
      simpa [initial] using huniformRun

/-- Arithmetic presentation of the uniform in-range fuel bound. -/
theorem runBuildModule_inRange_compiledInstructionCount
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
      run (buildModule batch) parameters thread
          (batch.expression.compiledInstructionCount + 47)
          (MachineState.initial memory) = some final ∧
        observeOutput final.memory parameters.outputs
            (thread.ctaidX * thread.ntidX + thread.tidX) = some observed ∧
        OutputRepresents observed result := by
  rw [← buildModule_body_size]
  exact runBuildModule_inRange batch parameters thread memory rows environment
    result hthread hlayout hin hmemory hrow heval

/-! ## Public exact-real consequence -/

/-- **Exact-real containment of the public generated-kernel output.**

If the selected interval environment corresponds pointwise to exact real
inputs and the source polynomial realizes `value` on those inputs, then the
interval observed from the successfully returned generated kernel contains
`value`.  This is the public composition point between whole-module execution,
the bounded-arithmetic theorem, and the output ABI representation. -/
theorem runBuildModule_inRange_containsReal
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
  have hcontains : result.interval.ContainsReal value :=
    PolynomialExpr.evalKernel_sound henvironments hrealizes heval
  rcases runBuildModule_inRange batch parameters thread memory rows environment
      result hthread hlayout hin hmemory hrow heval with
    ⟨final, observed, hrun, hobserve, hrepresents⟩
  refine ⟨final, observed, hrun, hobserve, ?_⟩
  rw [hrepresents.1]
  exact hcontains

end SparkInterval.PTX
