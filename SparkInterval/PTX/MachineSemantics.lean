import SparkInterval.PTX.PolynomialSemantics

/-!
# Operational semantics for the generated PTX machine subset

This file models every constructor of `PTX.Instruction`, including the integer
address calculation, global memory, predicates, labels, branches, and return.
It is intentionally a semantics of the typed Lean PTX AST.  The separate
backend assumptions that connect emitted PTX, `ptxas`, cubin/SASS, the CUDA
driver, and physical hardware to this model are not collapsed into this
definition.

The floating-point component is numerical rather than bit-exact: finite
binary64 values are represented by their exact real values, while the two
infinities are distinguished.  This is sufficient for interval containment
and for the generated nonfinite guards.  It deliberately does not distinguish
the two signed zeros.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

open SparkInterval

/-- Reduction modulo the PTX unsigned 32-bit word size. -/
def wrapU32 (value : Nat) : Nat := value % (2 ^ 32)

/-- Reduction modulo the PTX unsigned 64-bit word size. -/
def wrapU64 (value : Nat) : Nat := value % (2 ^ 64)

/-- A partial typed register file.  Generated code may read only initialized
registers; an uninitialized read makes the machine step fail. -/
abbrev RegisterFile (α : Type) := Nat → Option α

namespace RegisterFile

def empty {α : Type} : RegisterFile α := fun _ => none

def read {α : Type} (registers : RegisterFile α) (index : Nat) : Option α :=
  registers index

def write {α : Type} (registers : RegisterFile α) (index : Nat) (value : α) :
    RegisterFile α :=
  fun current => if current = index then some value else registers current

@[simp] theorem read_write_same {α : Type} (registers : RegisterFile α)
    (index : Nat) (value : α) :
    (registers.write index value).read index = some value := by
  simp [read, write]

@[simp] theorem read_write_of_ne {α : Type} (registers : RegisterFile α)
    {written current : Nat} (hne : current ≠ written) (value : α) :
    (registers.write written value).read current = registers.read current := by
  simp [read, write, hne]

end RegisterFile

/-- Logical typed view of global memory used by the restricted kernel.

The two maps share byte addresses but expose only the aligned 64-bit cells and
individual bytes used by the ABI.  Layout hypotheses in compiler correctness
ensure that input cells, output endpoint cells, and output metadata bytes do
not alias. -/
structure GlobalMemory where
  f64 : Nat → Option F64Value
  byte : Nat → Option (Fin 256)

namespace GlobalMemory

def empty : GlobalMemory := {
  f64 := fun _ => none
  byte := fun _ => none
}

def loadF64 (memory : GlobalMemory) (address : Nat) : Option F64Value :=
  memory.f64 address

def loadByte (memory : GlobalMemory) (address : Nat) : Option (Fin 256) :=
  memory.byte address

def storeF64 (memory : GlobalMemory) (address : Nat) (value : F64Value) :
    GlobalMemory :=
  { memory with f64 := RegisterFile.write memory.f64 address value }

def storeByte (memory : GlobalMemory) (address : Nat) (value : Fin 256) :
    GlobalMemory :=
  { memory with byte := RegisterFile.write memory.byte address value }

@[simp] theorem loadF64_storeF64_same (memory : GlobalMemory)
    (address : Nat) (value : F64Value) :
    (memory.storeF64 address value).loadF64 address = some value := by
  simp [loadF64, storeF64, RegisterFile.write]

@[simp] theorem loadByte_storeByte_same (memory : GlobalMemory)
    (address : Nat) (value : Fin 256) :
    (memory.storeByte address value).loadByte address = some value := by
  simp [loadByte, storeByte, RegisterFile.write]

@[simp] theorem loadByte_storeF64 (memory : GlobalMemory)
    (address current : Nat) (value : F64Value) :
    (memory.storeF64 address value).loadByte current = memory.loadByte current := by
  rfl

@[simp] theorem loadF64_storeByte (memory : GlobalMemory)
    (address current : Nat) (value : Fin 256) :
    (memory.storeByte address value).loadF64 current = memory.loadF64 current := by
  rfl

end GlobalMemory

/-- Values supplied by the fixed generated-kernel parameter ABI. -/
structure KernelParameters where
  rows : Nat
  outputs : Nat
  rowCount : Nat

/-- Per-thread values of the three special u32 registers used by the kernel. -/
structure ThreadContext where
  ctaidX : Nat
  ntidX : Nat
  tidX : Nat

def KernelParameters.read : KernelParameters → ParameterU64 → Nat
  | parameters, .rows => wrapU64 parameters.rows
  | parameters, .outputs => wrapU64 parameters.outputs
  | parameters, .rowCount => wrapU64 parameters.rowCount

def ThreadContext.read : ThreadContext → SpecialU32 → Nat
  | context, .ctaidX => wrapU32 context.ctaidX
  | context, .ntidX => wrapU32 context.ntidX
  | context, .tidX => wrapU32 context.tidX

/-- Complete state of one logical PTX thread. -/
structure MachineState where
  pred : RegisterFile Bool := RegisterFile.empty
  byte : RegisterFile (Fin 256) := RegisterFile.empty
  u32 : RegisterFile Nat := RegisterFile.empty
  u64 : RegisterFile Nat := RegisterFile.empty
  f64 : RegisterFile F64Value := RegisterFile.empty
  memory : GlobalMemory := GlobalMemory.empty
  pc : Nat := 0
  returned : Bool := false

namespace MachineState

def initial (memory : GlobalMemory) : MachineState :=
  { ({} : MachineState) with memory := memory }

def advance (state : MachineState) : MachineState :=
  { state with pc := state.pc + 1 }

def writePred (state : MachineState) (dst : Reg .pred) (value : Bool) :
    MachineState :=
  { state with pred := state.pred.write dst.index value }

def writeByte (state : MachineState) (dst : Reg .byte) (value : Fin 256) :
    MachineState :=
  { state with byte := state.byte.write dst.index value }

def writeU32 (state : MachineState) (dst : Reg .u32) (value : Nat) :
    MachineState :=
  { state with u32 := state.u32.write dst.index (wrapU32 value) }

def writeU64 (state : MachineState) (dst : Reg .u64) (value : Nat) :
    MachineState :=
  { state with u64 := state.u64.write dst.index (wrapU64 value) }

def writeF64 (state : MachineState) (dst : Reg .f64) (value : F64Value) :
    MachineState :=
  { state with f64 := state.f64.write dst.index value }

end MachineState

/-- The generated exponent-mask test only needs to distinguish finite values
from infinities.  NaNs cannot enter a validated input batch or be produced by
the guarded arithmetic model. -/
def F64Value.exponentFieldMask : F64Value → Nat
  | .finite _ => 0
  | .negInf | .posInf => 0x7ff0000000000000

/-- Scan a lexical instruction list for a target label, counting positions
from an explicit starting program counter.  This is public so compiler-layout
proofs can calculate branch targets compositionally across appended slices. -/
def labelPositionFrom : List Instruction → Label → Nat → Option Nat
  | [], _, _ => none
  | instruction :: rest, target, position =>
      match instruction with
      | .label found =>
          if found = target then some position
          else labelPositionFrom rest target (position + 1)
      | _ => labelPositionFrom rest target (position + 1)

/-- Resolve a branch target to the position of its typed label instruction. -/
def labelPosition? (module : Module) (target : Label) : Option Nat :=
  labelPositionFrom module.body.toList target 0

/-- Address arithmetic performed by PTX u64 global-memory operands. -/
def globalAddress (base offset : Nat) : Nat := wrapU64 (base + offset)

@[simp] theorem wrapU32_eq_of_lt {value : Nat} (hvalue : value < 2 ^ 32) :
    wrapU32 value = value := by
  exact Nat.mod_eq_of_lt hvalue

@[simp] theorem wrapU64_eq_of_lt {value : Nat} (hvalue : value < 2 ^ 64) :
    wrapU64 value = value := by
  exact Nat.mod_eq_of_lt hvalue

theorem globalAddress_eq_of_lt {base offset : Nat}
    (haddress : base + offset < 2 ^ 64) :
    globalAddress base offset = base + offset := by
  exact wrapU64_eq_of_lt haddress

/-- Global thread index computed by the generated prologue. -/
def ThreadContext.globalIndex (thread : ThreadContext) : Nat :=
  wrapU64 (thread.read .ctaidX * thread.read .ntidX + thread.read .tidX)

/-- Bounds under which the mathematical CUDA thread index does not wrap. -/
def ThreadContext.Safe (thread : ThreadContext) : Prop :=
  thread.ctaidX < 2 ^ 32 ∧ thread.ntidX < 2 ^ 32 ∧
    thread.tidX < 2 ^ 32 ∧
    thread.ctaidX * thread.ntidX + thread.tidX < 2 ^ 64

theorem ThreadContext.globalIndex_eq (thread : ThreadContext)
    (hsafe : thread.Safe) :
    thread.globalIndex = thread.ctaidX * thread.ntidX + thread.tidX := by
  rcases hsafe with ⟨hctaid, hntid, htid, hindex⟩
  unfold ThreadContext.globalIndex
  simp only [ThreadContext.read]
  rw [wrapU32_eq_of_lt hctaid, wrapU32_eq_of_lt hntid,
    wrapU32_eq_of_lt htid, wrapU64_eq_of_lt hindex]

/-- Execute exactly one typed PTX instruction.

Failure means an uninitialized register, absent input cell, NaN literal,
undefined label, or program-counter error.  Every `Instruction` constructor is
handled explicitly; there is no unknown-opcode case. -/
noncomputable def executeInstruction (module : Module)
    (parameters : KernelParameters) (thread : ThreadContext)
    (instruction : Instruction) (state : MachineState) : Option MachineState :=
  let next := state.advance
  match instruction with
  | .loadParamU64 dst parameter =>
      some <| (state.writeU64 dst (parameters.read parameter)).advance
  | .movByte dst value =>
      some <| (state.writeByte dst value).advance
  | .movSpecialU32 dst source =>
      some <| (state.writeU32 dst (thread.read source)).advance
  | .mulWideU32 dst left right => do
      let leftValue ← state.u32.read left.index
      let rightValue ← state.u32.read right.index
      pure <| (state.writeU64 dst (leftValue * rightValue)).advance
  | .cvtU64U32 dst source => do
      let value ← state.u32.read source.index
      pure <| (state.writeU64 dst value).advance
  | .addU64 dst left right => do
      let leftValue ← state.u64.read left.index
      let rightValue ← state.u64.read right.index
      pure <| (state.writeU64 dst (leftValue + rightValue)).advance
  | .addU64Immediate dst left right => do
      let leftValue ← state.u64.read left.index
      pure <| (state.writeU64 dst (leftValue + right)).advance
  | .mulLoU64Immediate dst left right => do
      let leftValue ← state.u64.read left.index
      pure <| (state.writeU64 dst (leftValue * right)).advance
  | .cvtaGlobalU64 dst source => do
      let value ← state.u64.read source.index
      pure <| (state.writeU64 dst value).advance
  | .loadGlobalF64 dst base offset => do
      let baseValue ← state.u64.read base.index
      let value ← state.memory.loadF64 (globalAddress baseValue offset)
      pure <| (state.writeF64 dst value).advance
  | .storeGlobalF64 base offset source => do
      let baseValue ← state.u64.read base.index
      let value ← state.f64.read source.index
      pure <| { next with
        memory := state.memory.storeF64 (globalAddress baseValue offset) value }
  | .storeGlobalByte base offset source => do
      let baseValue ← state.u64.read base.index
      let value ← state.byte.read source.index
      pure <| { next with
        memory := state.memory.storeByte (globalAddress baseValue offset) value }
  | .movF64Bits dst bits => do
      let value ← decodeF64Bits bits
      pure <| (state.writeF64 dst value).advance
  | .xorF64Sign dst source => do
      let value ← state.f64.read source.index
      pure <| (state.writeF64 dst value.negate).advance
  | .exponentBits dst source => do
      let value ← state.f64.read source.index
      pure <| (state.writeU64 dst value.exponentFieldMask).advance
  | .setpEqExponentMask dst source => do
      let value ← state.u64.read source.index
      pure <| (state.writePred dst
        (value = 0x7ff0000000000000)).advance
  | .setpGeU64 dst left right => do
      let leftValue ← state.u64.read left.index
      let rightValue ← state.u64.read right.index
      pure <| (state.writePred dst (rightValue ≤ leftValue)).advance
  | .branchIf condition target => do
      let takeBranch ← state.pred.read condition.index
      if takeBranch then
        let targetPosition ← labelPosition? module target
        pure { state with pc := targetPosition }
      else
        pure next
  | .branch target => do
      let targetPosition ← labelPosition? module target
      pure { state with pc := targetPosition }
  | .label _ => some next
  | .binaryF64 op rounding dst left right => do
      let leftValue ← state.f64.read left.index
      let rightValue ← state.f64.read right.index
      let value ← directedBinary op rounding leftValue rightValue
      pure <| (state.writeF64 dst value).advance
  | .minimumF64 dst left right => do
      let leftValue ← state.f64.read left.index
      let rightValue ← state.f64.read right.index
      pure <| (state.writeF64 dst (F64Value.minimum leftValue rightValue)).advance
  | .maximumF64 dst left right => do
      let leftValue ← state.f64.read left.index
      let rightValue ← state.f64.read right.index
      pure <| (state.writeF64 dst (F64Value.maximum leftValue rightValue)).advance
  | .ret => some { state with returned := true }

/-- Control result of executing a compiler-produced instruction slice.  This
structured form makes expression-level compiler induction possible before the
slice is placed at its final program counter. -/
inductive CodeControl where
  | fallthrough
  | jump (target : Label)
  | returned
  deriving BEq, DecidableEq, Repr

structure CodeExecution where
  control : CodeControl
  state : MachineState

/-- Execute a list as a structured code slice.  A taken branch is reported to
the caller instead of resolving its target inside the slice.  Non-control
instructions use exactly `executeInstruction`; hence arithmetic, register,
and memory behavior is shared with the whole-module machine. -/
noncomputable def executeCode (module : Module)
    (parameters : KernelParameters) (thread : ThreadContext) :
    List Instruction → MachineState → Option CodeExecution
  | [], state => some { control := .fallthrough, state }
  | instruction :: rest, state =>
      match instruction with
      | .branchIf condition target => do
          let takeBranch ← state.pred.read condition.index
          if takeBranch then
            pure { control := .jump target, state }
          else
            executeCode module parameters thread rest
              { state with pc := state.pc + 1 }
      | .branch target => some { control := .jump target, state }
      | .ret => some { control := .returned, state := { state with returned := true } }
      | .label _ =>
          executeCode module parameters thread rest { state with pc := state.pc + 1 }
      | _ => do
          let state ← executeInstruction module parameters thread instruction state
          executeCode module parameters thread rest state

/-- Fetch and execute one instruction at the state's program counter. -/
noncomputable def step (module : Module) (parameters : KernelParameters)
    (thread : ThreadContext) (state : MachineState) : Option MachineState := do
  if state.returned then pure state
  else
    let instruction ← module.body[state.pc]?
    executeInstruction module parameters thread instruction state

/-- Fuel-bounded execution of one logical generated-kernel thread. -/
noncomputable def run (module : Module) (parameters : KernelParameters)
    (thread : ThreadContext) : Nat → MachineState → Option MachineState
  | 0, state => if state.returned then some state else none
  | fuel + 1, state =>
      if state.returned then some state
      else do
        let state ← step module parameters thread state
        run module parameters thread fuel state

/-- Numerical observation of one 24-byte output record. -/
structure ObservedOutput where
  interval : F64Interval
  status : Fin 256
  reserved : Vector (Fin 256) 7

/-- Read the seven reserved bytes of one output record.  This is public so
compiler/output refinement lemmas can connect cell-level stores to the public
`observeOutput` ABI operation. -/
def readReserved (memory : GlobalMemory) (base : Nat) :
    Option (Vector (Fin 256) 7) := do
  let b0 ← memory.loadByte (globalAddress base 17)
  let b1 ← memory.loadByte (globalAddress base 18)
  let b2 ← memory.loadByte (globalAddress base 19)
  let b3 ← memory.loadByte (globalAddress base 20)
  let b4 ← memory.loadByte (globalAddress base 21)
  let b5 ← memory.loadByte (globalAddress base 22)
  let b6 ← memory.loadByte (globalAddress base 23)
  pure ⟨#[b0, b1, b2, b3, b4, b5, b6], by simp⟩

/-- Read the output record for a row from the modeled global memory. -/
def observeOutput (memory : GlobalMemory) (outputsBase row : Nat) :
    Option ObservedOutput := do
  let base := globalAddress outputsBase (row * 24)
  let lo ← memory.loadF64 (globalAddress base 0)
  let hi ← memory.loadF64 (globalAddress base 8)
  let status ← memory.loadByte (globalAddress base 16)
  let reserved ← readReserved memory base
  pure { interval := { lo, hi }, status, reserved }

/-- The output ABI representation of the status-aware polynomial evaluator. -/
def OutputRepresents (observed : ObservedOutput) (result : KernelResult) : Prop :=
  observed.interval = result.interval ∧
    observed.status.val = (match result.status with
      | .ok => 0
      | .nonfiniteIntermediate => 2) ∧
    observed.reserved.toArray = #[0, 0, 0, 0, 0, 0, 0]

/-- Input-memory relation for the row-major interval layout consumed by the
generated kernel. -/
def MemoryEncodesRows (memory : GlobalMemory) (rowsBase variableCount : Nat)
    (rows : Array (Array F64Interval)) : Prop :=
  ∀ row column values interval,
    rows[row]? = some values → values[column]? = some interval →
    memory.loadF64 (globalAddress rowsBase (row * (variableCount * 16) + column * 16)) =
        some interval.lo ∧
      memory.loadF64
        (globalAddress rowsBase (row * (variableCount * 16) + column * 16 + 8)) =
        some interval.hi

/-- Arithmetic bounds that make the generated address calculation agree with
ordinary natural-number row-major addressing. -/
def SafeKernelLayout (parameters : KernelParameters) (variableCount : Nat) : Prop :=
  parameters.rows < 2 ^ 64 ∧
    parameters.outputs < 2 ^ 64 ∧
    parameters.rowCount < 2 ^ 64 ∧
    parameters.rowCount * (variableCount * 16) < 2 ^ 64 ∧
    parameters.rowCount * 24 < 2 ^ 64 ∧
    parameters.rows + parameters.rowCount * (variableCount * 16) < 2 ^ 64 ∧
    parameters.outputs + parameters.rowCount * 24 < 2 ^ 64 ∧
    (parameters.rows + parameters.rowCount * (variableCount * 16) ≤
        parameters.outputs ∨
      parameters.outputs + parameters.rowCount * 24 ≤ parameters.rows)

end SparkInterval.PTX
