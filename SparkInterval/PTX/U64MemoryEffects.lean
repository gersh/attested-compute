import SparkInterval.PTX.MachineSemantics

/-!
# Unsigned-register and global-memory effects of typed PTX code

This module is the shared effect model for the non-f64 state needed by
expression execution.  It exhaustively records u64 destinations and global
memory stores for every typed instruction constructor, then proves preservation
for successful single-instruction and structured-slice execution.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- The u64 register written by an instruction, if any. -/
def Instruction.u64Destination? : Instruction → Option Nat
  | .loadParamU64 dst .. => some dst.index
  | .movByte .. => none
  | .movSpecialU32 .. => none
  | .mulWideU32 dst .. => some dst.index
  | .cvtU64U32 dst .. => some dst.index
  | .addU64 dst .. => some dst.index
  | .addU64Immediate dst .. => some dst.index
  | .mulLoU64Immediate dst .. => some dst.index
  | .cvtaGlobalU64 dst .. => some dst.index
  | .loadGlobalF64 .. => none
  | .storeGlobalF64 .. => none
  | .storeGlobalByte .. => none
  | .movF64Bits .. => none
  | .xorF64Sign .. => none
  | .exponentBits dst .. => some dst.index
  | .setpEqExponentMask .. => none
  | .setpGeU64 .. => none
  | .branchIf .. => none
  | .branch .. => none
  | .label .. => none
  | .binaryF64 .. => none
  | .minimumF64 .. => none
  | .maximumF64 .. => none
  | .ret => none

/-- u64 destination indices of a lexical instruction list. -/
def Instruction.u64Destinations : List Instruction → List Nat
  | [] => []
  | instruction :: rest =>
      instruction.u64Destination?.toList ++ u64Destinations rest

@[simp] theorem Instruction.u64Destinations_nil :
    Instruction.u64Destinations [] = [] := rfl

@[simp] theorem Instruction.u64Destinations_cons
    (instruction : Instruction) (rest : List Instruction) :
    Instruction.u64Destinations (instruction :: rest) =
      instruction.u64Destination?.toList ++
        Instruction.u64Destinations rest := rfl

@[simp] theorem Instruction.u64Destinations_append
    (first second : List Instruction) :
    Instruction.u64Destinations (first ++ second) =
      Instruction.u64Destinations first ++
        Instruction.u64Destinations second := by
  induction first with
  | nil => rfl
  | cons instruction rest induction =>
      simp [induction, List.append_assoc]

/-- Whether an instruction writes either typed view of global memory. -/
def Instruction.writesGlobalMemory : Instruction → Bool
  | .loadParamU64 .. => false
  | .movByte .. => false
  | .movSpecialU32 .. => false
  | .mulWideU32 .. => false
  | .cvtU64U32 .. => false
  | .addU64 .. => false
  | .addU64Immediate .. => false
  | .mulLoU64Immediate .. => false
  | .cvtaGlobalU64 .. => false
  | .loadGlobalF64 .. => false
  | .storeGlobalF64 .. => true
  | .storeGlobalByte .. => true
  | .movF64Bits .. => false
  | .xorF64Sign .. => false
  | .exponentBits .. => false
  | .setpEqExponentMask .. => false
  | .setpGeU64 .. => false
  | .branchIf .. => false
  | .branch .. => false
  | .label .. => false
  | .binaryF64 .. => false
  | .minimumF64 .. => false
  | .maximumF64 .. => false
  | .ret => false

/-- A lexical slice contains no global-memory store. -/
def GlobalMemoryWriteFree (code : List Instruction) : Prop :=
  ∀ instruction, instruction ∈ code →
    instruction.writesGlobalMemory = false

theorem GlobalMemoryWriteFree.nil : GlobalMemoryWriteFree [] := by
  simp [GlobalMemoryWriteFree]

theorem GlobalMemoryWriteFree.append {first second : List Instruction}
    (hfirst : GlobalMemoryWriteFree first)
    (hsecond : GlobalMemoryWriteFree second) :
    GlobalMemoryWriteFree (first ++ second) := by
  intro instruction hinstruction
  rcases List.mem_append.mp hinstruction with hleft | hright
  · exact hfirst instruction hleft
  · exact hsecond instruction hright

/-- A successful instruction preserves every u64 register other than its
declared u64 destination. -/
theorem executeInstruction_preserves_u64_read
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (instruction : Instruction) (initial final : MachineState) (index : Nat)
    (hindex : instruction.u64Destination? ≠ some index)
    (hexecute : executeInstruction module parameters thread instruction initial =
      some final) :
    final.u64.read index = initial.u64.read index := by
  cases instruction <;>
    simp only [Instruction.u64Destination?] at hindex <;>
    simp_all [executeInstruction, MachineState.advance, MachineState.writePred,
      MachineState.writeByte, MachineState.writeU32, MachineState.writeU64,
      MachineState.writeF64, RegisterFile.read,
      Option.bind_eq_some_iff] <;>
    aesop (add simp [RegisterFile.write])

/-- A successful instruction classified as store-free preserves global
memory. -/
theorem executeInstruction_preserves_globalMemory
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (instruction : Instruction) (initial final : MachineState)
    (hwrite : instruction.writesGlobalMemory = false)
    (hexecute : executeInstruction module parameters thread instruction initial =
      some final) :
    final.memory = initial.memory := by
  cases instruction <;>
    simp only [Instruction.writesGlobalMemory] at hwrite <;>
    simp_all [executeInstruction, MachineState.advance, MachineState.writePred,
      MachineState.writeByte, MachineState.writeU32, MachineState.writeU64,
      MachineState.writeF64, Option.bind_eq_some_iff] <;>
    aesop

/-- Structured execution preserves every u64 index absent from the lexical
u64 destination list. -/
theorem executeCode_preserves_u64_read
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial : MachineState)
    (execution : CodeExecution) (index : Nat)
    (hindex : index ∉ Instruction.u64Destinations code)
    (hexecute : executeCode module parameters thread code initial =
      some execution) :
    execution.state.u64.read index = initial.u64.read index := by
  induction code generalizing initial execution with
  | nil =>
      simp [executeCode] at hexecute
      subst execution
      rfl
  | cons instruction rest induction =>
      have hparts :
          instruction.u64Destination? ≠ some index ∧
            index ∉ Instruction.u64Destinations rest := by
        simpa [Instruction.u64Destinations] using hindex
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
          execution.state.u64.read index = middle.u64.read index :=
            induction middle execution hrest htail
          _ = initial.u64.read index :=
            executeInstruction_preserves_u64_read module parameters thread _
              initial middle index hhead hstep

/-- Store-free structured execution preserves the complete global memory. -/
theorem executeCode_preserves_globalMemory
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial : MachineState)
    (execution : CodeExecution)
    (hwrite : GlobalMemoryWriteFree code)
    (hexecute : executeCode module parameters thread code initial =
      some execution) :
    execution.state.memory = initial.memory := by
  induction code generalizing initial execution with
  | nil =>
      simp [executeCode] at hexecute
      subst execution
      rfl
  | cons instruction rest induction =>
      have hhead : instruction.writesGlobalMemory = false :=
        hwrite instruction (by simp)
      have hrest : GlobalMemoryWriteFree rest := by
        intro current hcurrent
        exact hwrite current (by simp [hcurrent])
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
          execution.state.memory = middle.memory :=
            induction middle execution hrest htail
          _ = initial.memory :=
            executeInstruction_preserves_globalMemory module parameters thread _
              initial middle hhead hstep

end SparkInterval.PTX
