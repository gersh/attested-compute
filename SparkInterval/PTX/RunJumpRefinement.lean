import SparkInterval.PTX.RunControlRefinement

/-!
# Taken-jump refinement for structured PTX slices

`executeCode` reports a taken branch without resolving its label, whereas the
whole-module `step` function resolves that label and installs its program
counter.  This module connects those two views for a structured slice placed
at its actual module-body position.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- Successful structured fallthrough advances by exactly the lexical slice
length and preserves the returned flag.  This theorem is independent of
module placement because a fallthrough outcome rules out every taken branch
and return; every constructor is nevertheless inspected explicitly. -/
theorem executeCode_fallthrough_pc_and_returned
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial final : MachineState)
    (hexecute : executeCode module parameters thread code initial =
      some { control := .fallthrough, state := final }) :
    final.pc = initial.pc + code.length ∧
      final.returned = initial.returned := by
  induction code generalizing initial with
  | nil =>
      simp [executeCode] at hexecute
      subst final
      simp
  | cons instruction rest induction =>
      have ordinaryCase (hordinary : instruction.IsRunOrdinary) :
          final.pc = initial.pc + (instruction :: rest).length ∧
            final.returned = initial.returned := by
        have hcode := hexecute
        rw [executeCode_cons_of_isRunOrdinary module parameters thread
          instruction rest initial hordinary] at hcode
        obtain ⟨middle, hstepInstruction, htailExecution⟩ :=
          Option.bind_eq_some_iff.mp hcode
        rcases executeInstruction_runOrdinary_control module parameters thread
            instruction initial middle hordinary hstepInstruction with
          ⟨hmiddlePc, hmiddleReturned⟩
        rcases induction middle htailExecution with
          ⟨hfinalPc, hfinalReturned⟩
        constructor
        · simp only [List.length_cons]
          omega
        · exact hfinalReturned.trans hmiddleReturned
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
      case branchIf condition target =>
          simp only [executeCode] at hexecute
          cases hread : initial.pred.read condition.index with
          | none => simp [hread] at hexecute
          | some takeBranch =>
              cases takeBranch with
              | false =>
                  simp [hread] at hexecute
                  rcases induction { initial with pc := initial.pc + 1 }
                      hexecute with
                    ⟨hfinalPc, hfinalReturned⟩
                  constructor
                  · simp only [List.length_cons]
                    change final.pc = initial.pc + 1 + rest.length at hfinalPc
                    omega
                  · simpa using hfinalReturned
              | true => simp [hread] at hexecute
      case branch target => simp [executeCode] at hexecute
      case label label =>
          simp only [executeCode] at hexecute
          rcases induction { initial with pc := initial.pc + 1 } hexecute with
            ⟨hfinalPc, hfinalReturned⟩
          constructor
          · simp only [List.length_cons]
            change final.pc = initial.pc + 1 + rest.length at hfinalPc
            omega
          · simpa using hfinalReturned
      case binaryF64 => exact ordinaryCase (by trivial)
      case minimumF64 => exact ordinaryCase (by trivial)
      case maximumF64 => exact ordinaryCase (by trivial)
      case ret => simp [executeCode] at hexecute

/-- Program-counter projection of `executeCode_fallthrough_pc_and_returned`. -/
theorem executeCode_fallthrough_pc
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial final : MachineState)
    (hexecute : executeCode module parameters thread code initial =
      some { control := .fallthrough, state := final }) :
    final.pc = initial.pc + code.length :=
  (executeCode_fallthrough_pc_and_returned module parameters thread code
    initial final hexecute).1

/-- Returned-flag projection of `executeCode_fallthrough_pc_and_returned`. -/
theorem executeCode_fallthrough_returned
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial final : MachineState)
    (hexecute : executeCode module parameters thread code initial =
      some { control := .fallthrough, state := final }) :
    final.returned = initial.returned :=
  (executeCode_fallthrough_pc_and_returned module parameters thread code
    initial final hexecute).2

/-- General taken-jump bridge.  If structured execution reports a jump, exact
whole-module stepping reaches the same branch-point state with its program
counter replaced by the resolved label position.

The witness is the number of lexical instructions through the taken branch.
It is positive and no larger than the supplied slice.  Prefix labels,
ordinary instructions, and non-taken conditional branches are all supported. -/
theorem executeCode_jumpExecution_stepN_of_runStepCompatible_segment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial : MachineState)
    (execution : CodeExecution) (target : Label) (targetPc : Nat)
    (hopcodes : RunStepCompatible code)
    (hsegment : ModuleBodySegmentAt module initial.pc code)
    (hnotReturned : initial.returned = false)
    (hcontrol : execution.control = .jump target)
    (htarget : labelPosition? module target = some targetPc)
    (hexecute : executeCode module parameters thread code initial =
      some execution) :
    ∃ count,
      0 < count ∧ count ≤ code.length ∧
        stepN module parameters thread count initial =
          some { execution.state with pc := targetPc } := by
  induction code generalizing initial execution target targetPc with
  | nil =>
      simp [executeCode] at hexecute
      subst execution
      simp at hcontrol
  | cons instruction rest induction =>
      have hhead : instruction.IsRunStepCompatible :=
        hopcodes instruction (by simp)
      have hrestOpcodes : RunStepCompatible rest := hopcodes.tail
      have hfetch : module.body[initial.pc]? = some instruction :=
        hsegment.fetch_head
      have htailSegment :
          ModuleBodySegmentAt module (initial.pc + 1) rest :=
        hsegment.tail
      have ordinaryCase (hordinary : instruction.IsRunOrdinary) :
          ∃ count,
            0 < count ∧ count ≤ (instruction :: rest).length ∧
              stepN module parameters thread count initial =
                some { execution.state with pc := targetPc } := by
        have hcode := hexecute
        rw [executeCode_cons_of_isRunOrdinary module parameters thread
          instruction rest initial hordinary] at hcode
        obtain ⟨middle, hstepInstruction, htailExecution⟩ :=
          Option.bind_eq_some_iff.mp hcode
        rcases executeInstruction_runOrdinary_control module parameters thread
            instruction initial middle hordinary hstepInstruction with
          ⟨hmiddlePc, hmiddleReturned⟩
        have hmiddleNotReturned : middle.returned = false := by
          rw [hmiddleReturned, hnotReturned]
        have hmiddleSegment :
            ModuleBodySegmentAt module middle.pc rest := by
          rw [hmiddlePc]
          exact htailSegment
        rcases induction middle execution target targetPc hrestOpcodes
            hmiddleSegment hmiddleNotReturned hcontrol htarget htailExecution with
          ⟨count, hpositive, hbound, htailSteps⟩
        have hmachineStep :
            step module parameters thread initial = some middle := by
          simp [step, hnotReturned, hfetch, hstepInstruction]
        refine ⟨count + 1, by omega, by simpa using Nat.succ_le_succ hbound, ?_⟩
        simpa [stepN, hmachineStep] using htailSteps
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
                  rcases induction
                      { initial with pc := initial.pc + 1 } execution target
                      targetPc hrestOpcodes htailSegment
                      (by simpa using hnotReturned) hcontrol htarget hexecute with
                    ⟨count, hpositive, hbound, htailSteps⟩
                  have hmachineStep :
                      step module parameters thread initial =
                        some { initial with pc := initial.pc + 1 } := by
                    simp [step, hnotReturned, hfetch, executeInstruction, hread,
                      MachineState.advance]
                  refine ⟨count + 1, by omega,
                    by simpa using Nat.succ_le_succ hbound, ?_⟩
                  simpa [stepN, hmachineStep] using htailSteps
              | true =>
                  simp [hread] at hexecute
                  subst execution
                  simp at hcontrol
                  subst target
                  refine ⟨1, by omega, by simp, ?_⟩
                  simp [stepN, step, hnotReturned, hfetch, executeInstruction,
                    hread, htarget]
      case branch branchTarget =>
          simp [executeCode] at hexecute
          subst execution
          simp at hcontrol
          subst target
          refine ⟨1, by omega, by simp, ?_⟩
          simp [stepN, step, hnotReturned, hfetch, executeInstruction, htarget]
      case label label =>
          simp only [executeCode] at hexecute
          rcases induction { initial with pc := initial.pc + 1 } execution target
              targetPc hrestOpcodes htailSegment
              (by simpa using hnotReturned) hcontrol htarget hexecute with
            ⟨count, hpositive, hbound, htailSteps⟩
          have hmachineStep :
              step module parameters thread initial =
                some { initial with pc := initial.pc + 1 } := by
            simp [step, hnotReturned, hfetch, executeInstruction,
              MachineState.advance]
          refine ⟨count + 1, by omega,
            by simpa using Nat.succ_le_succ hbound, ?_⟩
          simpa [stepN, hmachineStep] using htailSteps
      case binaryF64 => exact ordinaryCase (by trivial)
      case minimumF64 => exact ordinaryCase (by trivial)
      case maximumF64 => exact ordinaryCase (by trivial)
      case ret =>
          simp [executeCode] at hexecute
          subst execution
          simp at hcontrol

/-- Exact-state specialization of the general taken-jump bridge. -/
theorem executeCode_jump_stepN_of_runStepCompatible_segment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial branchState : MachineState)
    (target : Label) (targetPc : Nat)
    (hopcodes : RunStepCompatible code)
    (hsegment : ModuleBodySegmentAt module initial.pc code)
    (hnotReturned : initial.returned = false)
    (htarget : labelPosition? module target = some targetPc)
    (hexecute : executeCode module parameters thread code initial =
      some { control := .jump target, state := branchState }) :
    ∃ count,
      0 < count ∧ count ≤ code.length ∧
        stepN module parameters thread count initial =
          some { branchState with pc := targetPc } :=
  executeCode_jumpExecution_stepN_of_runStepCompatible_segment module
    parameters thread code initial
    { control := .jump target, state := branchState } target targetPc hopcodes
    hsegment hnotReturned rfl htarget hexecute

/-- Exact stepping after the resolved jump composes with an arbitrary number
of steps at the branch target. -/
theorem executeCode_jump_stepN_add_of_runStepCompatible_segment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial branchState : MachineState)
    (target : Label) (targetPc continuation : Nat)
    (hopcodes : RunStepCompatible code)
    (hsegment : ModuleBodySegmentAt module initial.pc code)
    (hnotReturned : initial.returned = false)
    (htarget : labelPosition? module target = some targetPc)
    (hexecute : executeCode module parameters thread code initial =
      some { control := .jump target, state := branchState }) :
    ∃ count,
      0 < count ∧ count ≤ code.length ∧
        stepN module parameters thread (count + continuation) initial =
          stepN module parameters thread continuation
            { branchState with pc := targetPc } := by
  rcases executeCode_jump_stepN_of_runStepCompatible_segment module parameters
      thread code initial branchState target targetPc hopcodes hsegment
      hnotReturned htarget hexecute with
    ⟨count, hpositive, hbound, hjumpSteps⟩
  refine ⟨count, hpositive, hbound, ?_⟩
  rw [stepN_add, hjumpSteps]
  rfl

/-- If execution from the resolved target succeeds under `run`, prefixing it
with the structured taken-branch slice also succeeds. -/
theorem executeCode_jump_run_compose_of_runStepCompatible_segment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial branchState final : MachineState)
    (target : Label) (targetPc continuation : Nat)
    (hopcodes : RunStepCompatible code)
    (hsegment : ModuleBodySegmentAt module initial.pc code)
    (hnotReturned : initial.returned = false)
    (htarget : labelPosition? module target = some targetPc)
    (hexecute : executeCode module parameters thread code initial =
      some { control := .jump target, state := branchState })
    (hcontinuation : run module parameters thread continuation
      { branchState with pc := targetPc } = some final) :
    ∃ count,
      0 < count ∧ count ≤ code.length ∧
        run module parameters thread (count + continuation) initial =
          some final := by
  rcases executeCode_jump_stepN_of_runStepCompatible_segment module parameters
      thread code initial branchState target targetPc hopcodes hsegment
      hnotReturned htarget hexecute with
    ⟨count, hpositive, hbound, hjumpSteps⟩
  rcases (run_eq_some_iff_stepN_eq_some_and_returned module parameters thread
      continuation { branchState with pc := targetPc } final).mp
      hcontinuation with
    ⟨hcontinuationSteps, hfinalReturned⟩
  refine ⟨count, hpositive, hbound, ?_⟩
  apply (run_eq_some_iff_stepN_eq_some_and_returned module parameters thread
    (count + continuation) initial final).2
  constructor
  · rw [stepN_add, hjumpSteps]
    exact hcontinuationSteps
  · exact hfinalReturned

end SparkInterval.PTX
