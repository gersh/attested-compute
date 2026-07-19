import SparkInterval.PTX.MachineSemantics

/-!
# Floating-point register effects of typed PTX code

This module records the sole binary64 register destination, when one exists,
for every constructor of `Instruction`.  It then proves that successful
single-instruction and structured-slice execution preserves any binary64
register which is absent from those destinations.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- The binary64 register written by an instruction, if any.  Every typed
instruction constructor is listed explicitly so additions to the AST make
this definition visibly incomplete until it is updated. -/
def Instruction.f64Destination? : Instruction → Option Nat
  | .loadParamU64 .. => none
  | .movByte .. => none
  | .movSpecialU32 .. => none
  | .mulWideU32 .. => none
  | .cvtU64U32 .. => none
  | .addU64 .. => none
  | .addU64Immediate .. => none
  | .mulLoU64Immediate .. => none
  | .cvtaGlobalU64 .. => none
  | .loadGlobalF64 dst .. => some dst.index
  | .storeGlobalF64 .. => none
  | .storeGlobalByte .. => none
  | .movF64Bits dst .. => some dst.index
  | .xorF64Sign dst .. => some dst.index
  | .exponentBits .. => none
  | .setpEqExponentMask .. => none
  | .setpGeU64 .. => none
  | .branchIf .. => none
  | .branch .. => none
  | .label .. => none
  | .binaryF64 _ _ dst .. => some dst.index
  | .minimumF64 dst .. => some dst.index
  | .maximumF64 dst .. => some dst.index
  | .ret => none

/-- Binary64 destination indices of a lexical instruction list, in execution
order (including destinations after branches, whether or not they run). -/
def Instruction.f64Destinations : List Instruction → List Nat
  | [] => []
  | instruction :: rest =>
      instruction.f64Destination?.toList ++ f64Destinations rest

@[simp] theorem Instruction.f64Destinations_nil :
    Instruction.f64Destinations [] = [] := rfl

@[simp] theorem Instruction.f64Destinations_cons
    (instruction : Instruction) (rest : List Instruction) :
    Instruction.f64Destinations (instruction :: rest) =
      instruction.f64Destination?.toList ++
        Instruction.f64Destinations rest := rfl

@[simp] theorem Instruction.f64Destinations_append
    (first second : List Instruction) :
    Instruction.f64Destinations (first ++ second) =
      Instruction.f64Destinations first ++
        Instruction.f64Destinations second := by
  induction first with
  | nil => rfl
  | cons instruction rest induction =>
      simp [induction, List.append_assoc]

/-- A successful instruction step preserves every binary64 register other
than its declared binary64 destination. -/
theorem executeInstruction_preserves_f64_read
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (instruction : Instruction) (initial final : MachineState) (index : Nat)
    (hindex : instruction.f64Destination? ≠ some index)
    (hexecute : executeInstruction module parameters thread instruction initial =
      some final) :
    final.f64.read index = initial.f64.read index := by
  cases instruction <;>
    simp only [Instruction.f64Destination?] at hindex <;>
    simp_all [executeInstruction, MachineState.advance, MachineState.writePred,
      MachineState.writeByte, MachineState.writeU32, MachineState.writeU64,
      MachineState.writeF64, RegisterFile.read,
      Option.bind_eq_some_iff] <;>
    aesop (add simp [RegisterFile.write])

/-- Every successful structured-code outcome preserves a binary64 register
whose index is absent from all lexical binary64 destinations.  The result is
uniform in the control outcome: fallthrough, jump, and return are all covered.
-/
theorem executeCode_preserves_f64_read
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial : MachineState)
    (execution : CodeExecution) (index : Nat)
    (hindex : index ∉ Instruction.f64Destinations code)
    (hexecute : executeCode module parameters thread code initial =
      some execution) :
    execution.state.f64.read index = initial.f64.read index := by
  induction code generalizing initial execution with
  | nil =>
      simp [executeCode] at hexecute
      subst execution
      rfl
  | cons instruction rest induction =>
      have hparts :
          instruction.f64Destination? ≠ some index ∧
            index ∉ Instruction.f64Destinations rest := by
        simpa [Instruction.f64Destinations] using hindex
      rcases hparts with ⟨hhead, hrest⟩
      cases instruction <;> simp only [executeCode] at hexecute
      case branchIf condition target =>
        cases hread : initial.pred.read condition.index with
        | none => simp [hread] at hexecute
        | some takeBranch =>
            cases takeBranch with
            | false =>
                simp [hread] at hexecute
                simpa using induction
                  { initial with pc := initial.pc + 1 } execution hrest hexecute
            | true =>
                simp [hread] at hexecute
                subst execution
                rfl
      case branch target =>
        simp at hexecute
        subst execution
        rfl
      case label label =>
        simpa using induction
          { initial with pc := initial.pc + 1 } execution hrest hexecute
      case ret =>
        simp at hexecute
        subst execution
        rfl
      all_goals
        obtain ⟨middle, hstep, htail⟩ :=
          Option.bind_eq_some_iff.mp hexecute
        calc
          execution.state.f64.read index = middle.f64.read index :=
            induction middle execution hrest htail
          _ = initial.f64.read index :=
            executeInstruction_preserves_f64_read module parameters thread _
              initial middle index hhead hstep

/-- Fallthrough specialization of `executeCode_preserves_f64_read`. -/
theorem executeCode_fallthrough_preserves_f64_read
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial final : MachineState) (index : Nat)
    (hindex : index ∉ Instruction.f64Destinations code)
    (hexecute : executeCode module parameters thread code initial =
      some { control := .fallthrough, state := final }) :
    final.f64.read index = initial.f64.read index :=
  executeCode_preserves_f64_read module parameters thread code initial
    { control := .fallthrough, state := final } index hindex hexecute

/-- Jump specialization of `executeCode_preserves_f64_read`. -/
theorem executeCode_jump_preserves_f64_read
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial final : MachineState)
    (target : Label) (index : Nat)
    (hindex : index ∉ Instruction.f64Destinations code)
    (hexecute : executeCode module parameters thread code initial =
      some { control := .jump target, state := final }) :
    final.f64.read index = initial.f64.read index :=
  executeCode_preserves_f64_read module parameters thread code initial
    { control := .jump target, state := final } index hindex hexecute

/-- Return specialization of `executeCode_preserves_f64_read`. -/
theorem executeCode_returned_preserves_f64_read
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial final : MachineState) (index : Nat)
    (hindex : index ∉ Instruction.f64Destinations code)
    (hexecute : executeCode module parameters thread code initial =
      some { control := .returned, state := final }) :
    final.f64.read index = initial.f64.read index :=
  executeCode_preserves_f64_read module parameters thread code initial
    { control := .returned, state := final } index hindex hexecute

end SparkInterval.PTX
