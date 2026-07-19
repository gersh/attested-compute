import SparkInterval.PTX.CodeComposition

/-!
# Fuel and structured-slice control refinement

This module separates exact machine stepping from the public fuel-bounded
`run` interface.  It also connects step-compatible structured execution to
whole-module stepping when the structured slice is the lexical module-body segment
at the initial program counter.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-! ## Exact iteration and fuel -/

/-- Execute exactly `count` calls to the whole-module `step` function.

Unlike `run`, this iterator does not require the final state to have returned.
Calls after a returned state are harmless because `step` fixes such states. -/
noncomputable def stepN (module : Module) (parameters : KernelParameters)
    (thread : ThreadContext) : Nat → MachineState → Option MachineState
  | 0, state => some state
  | count + 1, state => do
      let next ← step module parameters thread state
      stepN module parameters thread count next

/-- Exact stepping composes by addition of step counts. -/
theorem stepN_add (module : Module) (parameters : KernelParameters)
    (thread : ThreadContext) (first second : Nat) (state : MachineState) :
    stepN module parameters thread (first + second) state =
      (stepN module parameters thread first state).bind
        (stepN module parameters thread second) := by
  induction first generalizing state with
  | zero => simp [stepN]
  | succ first induction =>
      simp [stepN, Nat.succ_add, induction, Option.bind_assoc]

/-- Whole-module stepping fixes a state that has already returned. -/
theorem step_of_returned (module : Module) (parameters : KernelParameters)
    (thread : ThreadContext) (state : MachineState)
    (hreturned : state.returned = true) :
    step module parameters thread state = some state := by
  simp [step, hreturned]

/-- Any exact number of further steps fixes a returned state. -/
theorem stepN_of_returned (module : Module) (parameters : KernelParameters)
    (thread : ThreadContext) (count : Nat) (state : MachineState)
    (hreturned : state.returned = true) :
    stepN module parameters thread count state = some state := by
  induction count with
  | zero => rfl
  | succ count induction =>
      simp [stepN, step_of_returned module parameters thread state hreturned,
        induction]

/-- The final check made by `run` after exact fuel consumption. -/
def requireReturned (state : MachineState) : Option MachineState :=
  if state.returned then some state else none

/-- `run` is exact iteration followed by the returned-state check.

This equation also covers early return: `stepN_of_returned` explains why all
remaining exact steps leave the first returned state unchanged. -/
theorem run_eq_stepN_bind_requireReturned
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (fuel : Nat) (state : MachineState) :
    run module parameters thread fuel state =
      (stepN module parameters thread fuel state).bind requireReturned := by
  induction fuel generalizing state with
  | zero => rfl
  | succ fuel induction =>
      by_cases hreturned : state.returned = true
      · simp [run, hreturned, requireReturned,
          stepN_of_returned module parameters thread (fuel + 1) state hreturned]
      · have hnotReturned : state.returned = false :=
          Bool.eq_false_of_not_eq_true hreturned
        simp [run, stepN, hnotReturned, induction, Option.bind_assoc]

/-- Successful `run` is exactly successful exact stepping to a returned
state. -/
theorem run_eq_some_iff_stepN_eq_some_and_returned
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (fuel : Nat) (initial final : MachineState) :
    run module parameters thread fuel initial = some final ↔
      stepN module parameters thread fuel initial = some final ∧
        final.returned = true := by
  rw [run_eq_stepN_bind_requireReturned]
  simp [requireReturned, Option.bind_eq_some_iff]

/-- Once `run` succeeds, any additional fuel returns the same state. -/
theorem run_add_of_eq_some
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (fuel extra : Nat) (initial final : MachineState)
    (hrun : run module parameters thread fuel initial = some final) :
    run module parameters thread (fuel + extra) initial = some final := by
  rcases (run_eq_some_iff_stepN_eq_some_and_returned module parameters thread
      fuel initial final).mp hrun with ⟨hsteps, hreturned⟩
  apply (run_eq_some_iff_stepN_eq_some_and_returned module parameters thread
    (fuel + extra) initial final).2
  constructor
  · rw [stepN_add, hsteps]
    exact stepN_of_returned module parameters thread extra final hreturned
  · exact hreturned

/-- Monotone-fuel form of `run_add_of_eq_some`. -/
theorem run_mono_of_eq_some
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    {fuel larger : Nat} (initial final : MachineState) (hle : fuel ≤ larger)
    (hrun : run module parameters thread fuel initial = some final) :
    run module parameters thread larger initial = some final := by
  obtain ⟨extra, rfl⟩ := Nat.exists_eq_add_of_le hle
  exact run_add_of_eq_some module parameters thread fuel extra initial final hrun

/-! ## Step-compatible module-body slices -/

/-- Exhaustive opcode coverage used by the run-control bridge.  Every current
constructor is supported, including labels, branches, and returns; their
distinct control behavior is handled explicitly below.  Keeping the match
exhaustive forces future AST constructors to receive an intentional case. -/
def Instruction.IsRunStepCompatible : Instruction → Prop
  | .loadParamU64 .. => True
  | .movByte .. => True
  | .movSpecialU32 .. => True
  | .mulWideU32 .. => True
  | .cvtU64U32 .. => True
  | .addU64 .. => True
  | .addU64Immediate .. => True
  | .mulLoU64Immediate .. => True
  | .cvtaGlobalU64 .. => True
  | .loadGlobalF64 .. => True
  | .storeGlobalF64 .. => True
  | .storeGlobalByte .. => True
  | .movF64Bits .. => True
  | .xorF64Sign .. => True
  | .exponentBits .. => True
  | .setpEqExponentMask .. => True
  | .setpGeU64 .. => True
  | .branchIf .. => True
  | .branch .. => True
  | .label _ => True
  | .binaryF64 .. => True
  | .minimumF64 .. => True
  | .maximumF64 .. => True
  | .ret => True

/-- Every instruction in a structured run slice has an explicitly supported
whole-machine stepping case. -/
def RunStepCompatible (code : List Instruction) : Prop :=
  ∀ instruction, instruction ∈ code → instruction.IsRunStepCompatible

namespace RunStepCompatible

theorem tail {instruction : Instruction} {rest : List Instruction}
    (hcompatible : RunStepCompatible (instruction :: rest)) :
    RunStepCompatible rest := by
  intro current hcurrent
  exact hcompatible current (by simp [hcurrent])

end RunStepCompatible

/-- Exhaustive classification of instructions whose `executeCode` clause is
the ordinary `executeInstruction`-then-tail clause. -/
def Instruction.IsRunOrdinary : Instruction → Prop
  | .loadParamU64 .. => True
  | .movByte .. => True
  | .movSpecialU32 .. => True
  | .mulWideU32 .. => True
  | .cvtU64U32 .. => True
  | .addU64 .. => True
  | .addU64Immediate .. => True
  | .mulLoU64Immediate .. => True
  | .cvtaGlobalU64 .. => True
  | .loadGlobalF64 .. => True
  | .storeGlobalF64 .. => True
  | .storeGlobalByte .. => True
  | .movF64Bits .. => True
  | .xorF64Sign .. => True
  | .exponentBits .. => True
  | .setpEqExponentMask .. => True
  | .setpGeU64 .. => True
  | .branchIf .. => False
  | .branch .. => False
  | .label _ => False
  | .binaryF64 .. => True
  | .minimumF64 .. => True
  | .maximumF64 .. => True
  | .ret => False

/-- Ordinary structured execution is exactly instruction execution followed
by structured execution of the lexical tail. -/
theorem executeCode_cons_of_isRunOrdinary
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (instruction : Instruction) (rest : List Instruction)
    (state : MachineState) (hordinary : instruction.IsRunOrdinary) :
    executeCode module parameters thread (instruction :: rest) state =
      (executeInstruction module parameters thread instruction state).bind
        (executeCode module parameters thread rest) := by
  cases instruction <;>
    simp [Instruction.IsRunOrdinary, executeCode] at hordinary ⊢

/-- A successful ordinary instruction advances one lexical position and
preserves the returned flag. -/
theorem executeInstruction_runOrdinary_control
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (instruction : Instruction) (initial final : MachineState)
    (hordinary : instruction.IsRunOrdinary)
    (hexecute : executeInstruction module parameters thread instruction initial =
      some final) :
    final.pc = initial.pc + 1 ∧ final.returned = initial.returned := by
  cases instruction <;>
    simp only [Instruction.IsRunOrdinary] at hordinary <;>
    simp_all [executeInstruction, MachineState.advance, MachineState.writePred,
      MachineState.writeByte, MachineState.writeU32, MachineState.writeU64,
      MachineState.writeF64, Option.bind_eq_some_iff] <;>
    aesop

/-- `code` is exactly the next lexical segment of the module body at `pc`.
The existential suffix makes the relation useful for slices in the middle of
a generated module. -/
def ModuleBodySegmentAt (module : Module) (pc : Nat)
    (code : List Instruction) : Prop :=
  ∃ suffix, module.body.toList.drop pc = code ++ suffix

/-- The head of a nonempty module-body segment is the machine instruction
fetched at that segment's program counter. -/
theorem ModuleBodySegmentAt.fetch_head
    {module : Module} {pc : Nat} {instruction : Instruction}
    {rest : List Instruction}
    (hsegment : ModuleBodySegmentAt module pc (instruction :: rest)) :
    module.body[pc]? = some instruction := by
  rcases hsegment with ⟨suffix, hsegment⟩
  have hhead := congrArg List.head? hsegment
  simpa using hhead

/-- Dropping the fetched head advances a module-body segment by one program
counter position. -/
theorem ModuleBodySegmentAt.tail
    {module : Module} {pc : Nat} {instruction : Instruction}
    {rest : List Instruction}
    (hsegment : ModuleBodySegmentAt module pc (instruction :: rest)) :
    ModuleBodySegmentAt module (pc + 1) rest := by
  rcases hsegment with ⟨suffix, hsegment⟩
  refine ⟨suffix, ?_⟩
  calc
    module.body.toList.drop (pc + 1) =
        (module.body.toList.drop pc).tail :=
      (List.tail_drop (l := module.body.toList) (i := pc)).symm
    _ = (instruction :: (rest ++ suffix)).tail := by
      rw [hsegment, List.cons_append]
    _ = rest ++ suffix := rfl

/-- Structured controls whose final state is reproduced by lexical exact
stepping.  A reported jump is excluded because whole-module `step` resolves
its target and changes the program counter. -/
def CodeControl.StepNCompatible : CodeControl → Prop
  | .fallthrough => True
  | .jump _ => False
  | .returned => True

/-- A successful step-compatible structured slice with a fallthrough or returned
outcome is reproduced by exactly its lexical length in whole-module steps.

The assumptions are explicit: the initial state has not returned, the slice
is the body segment at its initial `pc`, and reported jumps are excluded.
Conditional branches are nevertheless supported whenever their actual
structured outcome continues through the slice. -/
theorem executeCode_stepN_of_runStepCompatible_segment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial : MachineState)
    (execution : CodeExecution)
    (hopcodes : RunStepCompatible code)
    (hsegment : ModuleBodySegmentAt module initial.pc code)
    (hnotReturned : initial.returned = false)
    (hcompatible : execution.control.StepNCompatible)
    (hexecute : executeCode module parameters thread code initial =
      some execution) :
    stepN module parameters thread code.length initial =
      some execution.state := by
  induction code generalizing initial execution with
  | nil =>
      simp [executeCode] at hexecute
      subst execution
      rfl
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
          stepN module parameters thread (instruction :: rest).length initial =
            some execution.state := by
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
        have htailSteps := induction middle execution hrestOpcodes hmiddleSegment
          hmiddleNotReturned hcompatible htailExecution
        have hmachineStep :
            step module parameters thread initial = some middle := by
          simp [step, hnotReturned, hfetch, hstepInstruction]
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
      case branchIf condition target =>
          simp only [executeCode] at hexecute
          cases hread : initial.pred.read condition.index with
          | none => simp [hread] at hexecute
          | some takeBranch =>
              cases takeBranch with
              | false =>
                  simp [hread] at hexecute
                  have htailSteps := induction
                    { initial with pc := initial.pc + 1 } execution hrestOpcodes
                    htailSegment (by simpa using hnotReturned) hcompatible
                    hexecute
                  have hmachineStep :
                      step module parameters thread initial =
                        some { initial with pc := initial.pc + 1 } := by
                    simp [step, hnotReturned, hfetch, executeInstruction, hread,
                      MachineState.advance]
                  simpa [stepN, hmachineStep] using htailSteps
              | true =>
                  simp [hread] at hexecute
                  subst execution
                  simp [CodeControl.StepNCompatible] at hcompatible
      case branch target =>
          simp [executeCode] at hexecute
          subst execution
          simp [CodeControl.StepNCompatible] at hcompatible
      case label label =>
          simp only [executeCode] at hexecute
          have htailSteps := induction
            { initial with pc := initial.pc + 1 } execution hrestOpcodes
            htailSegment (by simpa using hnotReturned) hcompatible hexecute
          have hmachineStep :
              step module parameters thread initial =
                some { initial with pc := initial.pc + 1 } := by
            simp [step, hnotReturned, hfetch, executeInstruction,
              MachineState.advance]
          simpa [stepN, hmachineStep] using htailSteps
      case binaryF64 => exact ordinaryCase (by trivial)
      case minimumF64 => exact ordinaryCase (by trivial)
      case maximumF64 => exact ordinaryCase (by trivial)
      case ret =>
          simp [executeCode] at hexecute
          subst execution
          have hmachineStep :
              step module parameters thread initial =
                some { initial with returned := true } := by
            simp [step, hnotReturned, hfetch, executeInstruction]
          have hremaining := stepN_of_returned module parameters thread
            rest.length { initial with returned := true } (by rfl)
          simpa [stepN, hmachineStep] using hremaining

/-- Fallthrough specialization of the generic structured-slice bridge. -/
theorem executeCode_fallthrough_stepN_of_runStepCompatible_segment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial final : MachineState)
    (hopcodes : RunStepCompatible code)
    (hsegment : ModuleBodySegmentAt module initial.pc code)
    (hnotReturned : initial.returned = false)
    (hexecute : executeCode module parameters thread code initial =
      some { control := .fallthrough, state := final }) :
    stepN module parameters thread code.length initial = some final :=
  executeCode_stepN_of_runStepCompatible_segment module parameters thread code
    initial { control := .fallthrough, state := final } hopcodes hsegment
    hnotReturned (by trivial) hexecute

/-- Returned specialization of the generic structured-slice bridge. -/
theorem executeCode_returned_stepN_of_runStepCompatible_segment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial final : MachineState)
    (hopcodes : RunStepCompatible code)
    (hsegment : ModuleBodySegmentAt module initial.pc code)
    (hnotReturned : initial.returned = false)
    (hexecute : executeCode module parameters thread code initial =
      some { control := .returned, state := final }) :
    stepN module parameters thread code.length initial = some final :=
  executeCode_stepN_of_runStepCompatible_segment module parameters thread code
    initial { control := .returned, state := final } hopcodes hsegment
    hnotReturned (by trivial) hexecute

/-- A returned structured outcome always carries a state whose returned bit
is set, independently of module placement. -/
theorem executeCode_returned_state_returned
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial final : MachineState)
    (hexecute : executeCode module parameters thread code initial =
      some { control := .returned, state := final }) :
    final.returned = true := by
  induction code generalizing initial with
  | nil => simp [executeCode] at hexecute
  | cons instruction rest induction =>
      cases instruction <;> simp only [executeCode] at hexecute
      case branchIf condition target =>
        cases hread : initial.pred.read condition.index with
        | none => simp [hread] at hexecute
        | some takeBranch =>
            cases takeBranch with
            | false =>
                simp [hread] at hexecute
                exact induction _ hexecute
            | true => simp [hread] at hexecute
      case branch target => simp at hexecute
      case label label => exact induction _ hexecute
      case ret =>
        simp at hexecute
        subst final
        rfl
      all_goals
        obtain ⟨middle, _, htail⟩ := Option.bind_eq_some_iff.mp hexecute
        exact induction middle htail

/-- A returned structured module-body slice therefore makes `run` succeed
with exactly the slice length as fuel. -/
theorem executeCode_returned_run_of_runStepCompatible_segment
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial final : MachineState)
    (hopcodes : RunStepCompatible code)
    (hsegment : ModuleBodySegmentAt module initial.pc code)
    (hnotReturned : initial.returned = false)
    (hexecute : executeCode module parameters thread code initial =
      some { control := .returned, state := final }) :
    run module parameters thread code.length initial = some final := by
  apply (run_eq_some_iff_stepN_eq_some_and_returned module parameters thread
    code.length initial final).2
  exact ⟨executeCode_returned_stepN_of_runStepCompatible_segment module parameters
    thread code initial final hopcodes hsegment hnotReturned hexecute,
    executeCode_returned_state_returned module parameters thread code initial
      final hexecute⟩

end SparkInterval.PTX
