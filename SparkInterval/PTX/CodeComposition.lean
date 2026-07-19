import SparkInterval.PTX.MachineSemantics

/-!
# Composition laws for structured PTX code slices

`executeCode` deliberately reports branches and returns to its caller.  These
lemmas let compiler-correctness proofs assemble small, operand-sensitive
instruction refinements without unfolding an entire generated kernel at once.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- Interpret the outcome of one structured slice when lexical code follows
it: only normal fallthrough starts the suffix. -/
noncomputable def continueCode
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (suffix : List Instruction) : CodeExecution → Option CodeExecution
  | { control := .fallthrough, state } =>
      executeCode module parameters thread suffix state
  | execution => some execution

/-- Master lexical-composition law for the structured interpreter. -/
theorem executeCode_append
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (firstCode suffix : List Instruction) (initial : MachineState) :
    executeCode module parameters thread (firstCode ++ suffix) initial =
      (executeCode module parameters thread firstCode initial).bind
        (continueCode module parameters thread suffix) := by
  induction firstCode generalizing initial with
  | nil => rfl
  | cons instruction rest induction =>
      cases instruction
      all_goals
        simp [executeCode, continueCode, induction, Option.bind_assoc]
      case branchIf condition target =>
        cases hread : initial.pred.read condition.index with
        | none => simp
        | some takeBranch =>
            cases takeBranch <;> simp

/-- A slice that falls through can be followed by another slice. -/
theorem executeCode_append_fallthrough
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (firstCode suffix : List Instruction) (initial middle : MachineState)
    (hfirst : executeCode module parameters thread firstCode initial =
      some { control := .fallthrough, state := middle }) :
    executeCode module parameters thread (firstCode ++ suffix) initial =
      executeCode module parameters thread suffix middle := by
  rw [executeCode_append, hfirst]
  rfl

/-- Once a prefix takes a branch, appending lexical instructions cannot make
them execute inside the same structured slice. -/
theorem executeCode_append_jump
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (firstCode suffix : List Instruction) (initial final : MachineState)
    (target : Label)
    (hfirst : executeCode module parameters thread firstCode initial =
      some { control := .jump target, state := final }) :
    executeCode module parameters thread (firstCode ++ suffix) initial =
      some { control := .jump target, state := final } := by
  rw [executeCode_append, hfirst]
  rfl

/-- Once a prefix returns, appending lexical instructions cannot make them
execute inside the same structured slice. -/
theorem executeCode_append_returned
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (firstCode suffix : List Instruction) (initial final : MachineState)
    (hfirst : executeCode module parameters thread firstCode initial =
      some { control := .returned, state := final }) :
    executeCode module parameters thread (firstCode ++ suffix) initial =
      some { control := .returned, state := final } := by
  rw [executeCode_append, hfirst]
  rfl

end SparkInterval.PTX
