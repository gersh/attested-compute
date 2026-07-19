import SparkInterval.PTX.GeneratedModuleSegments
import SparkInterval.PTX.RunJumpRefinement
import SparkInterval.PTX.U64MemoryEffects

/-!
# Whole-module refinement of the generated out-of-range path

An out-of-range CUDA thread takes the production prologue branch directly to
`doneLabel`.  This module composes the structured prologue theorem, canonical
module segments, label resolution, the whole-machine jump bridge, and the
two-instruction return tail.  No expression or output-store instruction is
executed on this path.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- The generated prologue has no global-memory store. -/
theorem generatedPrologueCode_globalMemoryWriteFree (batch : ReferenceBatch) :
    GlobalMemoryWriteFree (generatedPrologueCode batch) := by
  simp [GlobalMemoryWriteFree, generatedPrologueCode, prologueInstructions,
    Instruction.writesGlobalMemory]

/-- The common done-label/return tail has no global-memory store. -/
theorem generatedReturnTail_globalMemoryWriteFree :
    GlobalMemoryWriteFree generatedReturnTail := by
  simp [GlobalMemoryWriteFree, generatedReturnTail,
    compiledEpilogueReturnTail, Instruction.writesGlobalMemory]

/-- A structured jump outcome cannot have passed through `ret`, so it
preserves the incoming returned flag.  Every instruction constructor is
handled explicitly. -/
theorem executeCode_jump_preserves_returned
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial final : MachineState) (target : Label)
    (hexecute : executeCode module parameters thread code initial =
      some { control := .jump target, state := final }) :
    final.returned = initial.returned := by
  induction code generalizing initial with
  | nil => simp [executeCode] at hexecute
  | cons instruction rest induction =>
      have ordinaryCase (hordinary : instruction.IsRunOrdinary) :
          final.returned = initial.returned := by
        have hcode := hexecute
        rw [executeCode_cons_of_isRunOrdinary module parameters thread
          instruction rest initial hordinary] at hcode
        obtain ⟨middle, hstepInstruction, htailExecution⟩ :=
          Option.bind_eq_some_iff.mp hcode
        have hmiddleReturned :=
          (executeInstruction_runOrdinary_control module parameters thread
            instruction initial middle hordinary hstepInstruction).2
        exact (induction middle htailExecution).trans hmiddleReturned
      cases instruction
      case loadParamU64 => exact ordinaryCase (by trivial)
      case movByte => exact ordinaryCase (by trivial)
      case movSpecialU32 => exact ordinaryCase (by trivial)
      case mulWideU32 => exact ordinaryCase (by trivial)
      case cvtU64U32 => exact ordinaryCase (by trivial)
      case addU64 => exact ordinaryCase (by trivial)
      case addU64Immediate => exact ordinaryCase (by trivial)
      case mulLoU64Immediate => exact ordinaryCase (by trivial)
      case cvtaGlobalU64 => exact ordinaryCase (by trivial)
      case loadGlobalF64 => exact ordinaryCase (by trivial)
      case storeGlobalF64 => exact ordinaryCase (by trivial)
      case storeGlobalByte => exact ordinaryCase (by trivial)
      case movF64Bits => exact ordinaryCase (by trivial)
      case xorF64Sign => exact ordinaryCase (by trivial)
      case exponentBits => exact ordinaryCase (by trivial)
      case setpEqExponentMask => exact ordinaryCase (by trivial)
      case setpGeU64 => exact ordinaryCase (by trivial)
      case branchIf condition branchTarget =>
          simp only [executeCode] at hexecute
          cases hread : initial.pred.read condition.index with
          | none => simp [hread] at hexecute
          | some takeBranch =>
              cases takeBranch with
              | false =>
                  simp [hread] at hexecute
                  simpa using induction
                    { initial with pc := initial.pc + 1 } hexecute
              | true =>
                  simp [hread] at hexecute
                  exact (congrArg (fun state => state.returned)
                    hexecute.2).symm
      case branch branchTarget =>
          simp [executeCode] at hexecute
          exact (congrArg (fun state => state.returned) hexecute.2).symm
      case label label =>
          exact induction { initial with pc := initial.pc + 1 } hexecute
      case binaryF64 => exact ordinaryCase (by trivial)
      case minimumF64 => exact ordinaryCase (by trivial)
      case maximumF64 => exact ordinaryCase (by trivial)
      case ret => simp [executeCode] at hexecute

/-- State produced by executing the common done label followed by `ret`. -/
def generatedReturnState (state : MachineState) : MachineState :=
  { state with pc := state.pc + 1, returned := true }

/-- Exact structured execution of the generated return tail. -/
theorem executeGeneratedReturnTail
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) :
    executeCode module parameters thread generatedReturnTail state =
        some { control := .returned, state := generatedReturnState state } ∧
      (generatedReturnState state).memory = state.memory := by
  constructor
  · simp [generatedReturnTail, compiledEpilogueReturnTail,
      generatedReturnState, executeCode]
  · rfl

/-- Every production thread whose wrapped index is at least the wrapped row
count returns successfully under the uniform full-module fuel bound, without
changing global memory.  In particular, no row-output store executes. -/
theorem runBuildModule_outOfRange
    (batch : ReferenceBatch) (parameters : KernelParameters)
    (thread : ThreadContext) (memory : GlobalMemory)
    (hout : parameters.read .rowCount ≤ thread.globalIndex) :
    ∃ final,
      run (buildModule batch) parameters thread (buildModule batch).body.size
          (MachineState.initial memory) = some final ∧
        final.memory = memory := by
  let initial := MachineState.initial memory
  rcases executePrologue_outOfRange (buildModule batch) parameters thread
      initial batch.variableCount Builder.initial hout with
    ⟨prologueFinal, hprologue, _, _⟩
  have hprologueExecution :
      executeCode (buildModule batch) parameters thread
          (generatedPrologueCode batch) initial =
        some { control := .jump doneLabel, state := prologueFinal } := by
    simpa [generatedPrologueCode] using hprologue
  have hprologueMemory : prologueFinal.memory = memory := by
    have hpreserved := executeCode_preserves_globalMemory
      (buildModule batch) parameters thread (generatedPrologueCode batch)
      initial { control := .jump doneLabel, state := prologueFinal }
      (generatedPrologueCode_globalMemoryWriteFree batch) hprologueExecution
    simpa [initial, MachineState.initial] using hpreserved
  have hprologueNotReturned : prologueFinal.returned = false := by
    have hpreserved := executeCode_jump_preserves_returned
      (buildModule batch) parameters thread (generatedPrologueCode batch)
      initial prologueFinal doneLabel hprologueExecution
    simpa [initial, MachineState.initial] using hpreserved
  let donePc := batch.expression.compiledInstructionCount + 45
  rcases buildModule_doneLabel_segment batch with
    ⟨hdonePosition, hreturnSegment⟩
  let jumped : MachineState := { prologueFinal with pc := donePc }
  let final := generatedReturnState jumped
  have hjumpedNotReturned : jumped.returned = false := by
    simpa [jumped] using hprologueNotReturned
  have hreturnSegmentAt :
      ModuleBodySegmentAt (buildModule batch) jumped.pc generatedReturnTail := by
    simpa [jumped, donePc] using hreturnSegment
  have hreturnExecution :
      executeCode (buildModule batch) parameters thread generatedReturnTail
          jumped = some { control := .returned, state := final } := by
    simpa [final] using
      (executeGeneratedReturnTail (buildModule batch) parameters thread jumped).1
  have hreturnRun :
      run (buildModule batch) parameters thread generatedReturnTail.length
          jumped = some final :=
    executeCode_returned_run_of_runStepCompatible_segment
      (buildModule batch) parameters thread generatedReturnTail jumped final
      generatedReturnTail_runStepCompatible hreturnSegmentAt
      hjumpedNotReturned hreturnExecution
  have htarget : labelPosition? (buildModule batch) doneLabel = some donePc := by
    simpa [donePc] using hdonePosition
  have hprologueSegment :
      ModuleBodySegmentAt (buildModule batch) initial.pc
        (generatedPrologueCode batch) := by
    simpa [initial, MachineState.initial] using buildModule_prologue_segment batch
  rcases executeCode_jump_run_compose_of_runStepCompatible_segment
      (buildModule batch) parameters thread (generatedPrologueCode batch)
      initial prologueFinal final doneLabel donePc generatedReturnTail.length
      (generatedPrologueCode_runStepCompatible batch) hprologueSegment
      (by simp [initial, MachineState.initial]) htarget hprologueExecution
      (by simpa [jumped] using hreturnRun) with
    ⟨branchSteps, _, hbranchBound, hshortRun⟩
  have hfuelBound :
      branchSteps + generatedReturnTail.length ≤
        (buildModule batch).body.size := by
    have hbranchBound' : branchSteps ≤ 17 := by
      simpa using hbranchBound
    rw [buildModule_body_size]
    simp
    omega
  have huniformRun :
      run (buildModule batch) parameters thread (buildModule batch).body.size
          initial = some final :=
    run_mono_of_eq_some (buildModule batch) parameters thread initial final
      hfuelBound hshortRun
  refine ⟨final, ?_, ?_⟩
  · simpa [initial] using huniformRun
  · simp [final, generatedReturnState, jumped, hprologueMemory]

/-- Arithmetic presentation of the same uniform fuel bound. -/
theorem runBuildModule_outOfRange_compiledInstructionCount
    (batch : ReferenceBatch) (parameters : KernelParameters)
    (thread : ThreadContext) (memory : GlobalMemory)
    (hout : parameters.read .rowCount ≤ thread.globalIndex) :
    ∃ final,
      run (buildModule batch) parameters thread
          (batch.expression.compiledInstructionCount + 47)
          (MachineState.initial memory) = some final ∧
        final.memory = memory := by
  rw [← buildModule_body_size]
  exact runBuildModule_outOfRange batch parameters thread memory hout

end SparkInterval.PTX
