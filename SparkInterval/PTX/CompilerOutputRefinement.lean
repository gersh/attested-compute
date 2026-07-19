import SparkInterval.PTX.CodeComposition
import SparkInterval.PTX.CompilerDataflow

/-!
# Concrete output-record compiler refinement

This file exposes the byte registers and exact twelve instructions selected by
`emitOutput`, then executes that slice in the typed machine.  The theorem
records the exact global-memory transformation; address-layout corollaries can
subsequently connect it to `observeOutput` under `SafeKernelLayout`.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- The two byte registers allocated by one production output record. -/
structure OutputCompilerRegisters where
  status : Reg .byte
  zero : Reg .byte
  deriving Repr, Inhabited

def outputCompilerRegisters (builder : Builder) : OutputCompilerRegisters := {
  status := ⟨builder.nextByte⟩
  zero := ⟨builder.nextByte + 1⟩
}

/-- The literal instruction slice appended by `emitOutput`. -/
def compiledOutputInstructions (outputBase : Reg .u64)
    (result : IntervalRegisters) (status : Fin 256) (builder : Builder) :
    List Instruction :=
  let registers := outputCompilerRegisters builder
  [.movByte registers.status status,
   .movByte registers.zero ⟨0, by decide⟩,
   .storeGlobalF64 outputBase 0 result.lo,
   .storeGlobalF64 outputBase 8 result.hi,
   .storeGlobalByte outputBase 16 registers.status,
   .storeGlobalByte outputBase 17 registers.zero,
   .storeGlobalByte outputBase 18 registers.zero,
   .storeGlobalByte outputBase 19 registers.zero,
   .storeGlobalByte outputBase 20 registers.zero,
   .storeGlobalByte outputBase 21 registers.zero,
   .storeGlobalByte outputBase 22 registers.zero,
   .storeGlobalByte outputBase 23 registers.zero]

/-- Exact memory transformation performed by one output-record slice. -/
def writeOutputMemory (memory : GlobalMemory) (base : Nat)
    (interval : F64Interval) (status : Fin 256) : GlobalMemory :=
  let memory := memory.storeF64 (globalAddress base 0) interval.lo
  let memory := memory.storeF64 (globalAddress base 8) interval.hi
  let memory := memory.storeByte (globalAddress base 16) status
  let zero : Fin 256 := ⟨0, by decide⟩
  let memory := memory.storeByte (globalAddress base 17) zero
  let memory := memory.storeByte (globalAddress base 18) zero
  let memory := memory.storeByte (globalAddress base 19) zero
  let memory := memory.storeByte (globalAddress base 20) zero
  let memory := memory.storeByte (globalAddress base 21) zero
  let memory := memory.storeByte (globalAddress base 22) zero
  memory.storeByte (globalAddress base 23) zero

/-- Direct cell-level observation of the generated 24-byte output record. -/
def MemoryContainsOutputRecord (memory : GlobalMemory) (base : Nat)
    (interval : F64Interval) (status : Fin 256) : Prop :=
  memory.loadF64 (globalAddress base 0) = some interval.lo ∧
  memory.loadF64 (globalAddress base 8) = some interval.hi ∧
  memory.loadByte (globalAddress base 16) = some status ∧
  memory.loadByte (globalAddress base 17) = some ⟨0, by decide⟩ ∧
  memory.loadByte (globalAddress base 18) = some ⟨0, by decide⟩ ∧
  memory.loadByte (globalAddress base 19) = some ⟨0, by decide⟩ ∧
  memory.loadByte (globalAddress base 20) = some ⟨0, by decide⟩ ∧
  memory.loadByte (globalAddress base 21) = some ⟨0, by decide⟩ ∧
  memory.loadByte (globalAddress base 22) = some ⟨0, by decide⟩ ∧
  memory.loadByte (globalAddress base 23) = some ⟨0, by decide⟩

def expectedObservedOutput (interval : F64Interval)
    (status : Fin 256) : ObservedOutput := {
  interval
  status
  reserved := ⟨#[0, 0, 0, 0, 0, 0, 0], by decide⟩
}

@[simp] theorem expectedObservedOutput_ok_represents
    (interval : F64Interval) :
    OutputRepresents (expectedObservedOutput interval ⟨0, by decide⟩)
      { interval := interval, status := .ok } := by
  simp [OutputRepresents, expectedObservedOutput]

@[simp] theorem expectedObservedOutput_nonfinite_represents :
    OutputRepresents
      (expectedObservedOutput F64Interval.whole ⟨2, by decide⟩)
      KernelResult.whole := by
  simp [OutputRepresents, expectedObservedOutput, KernelResult.whole]

/-- With no u64 wrap inside the 24-byte record, the exact memory
transformation makes every ABI cell independently observable. -/
theorem writeOutputMemory_contains (memory : GlobalMemory) (base : Nat)
    (interval : F64Interval) (status : Fin 256)
    (hsafe : base + 23 < 2 ^ 64) :
    MemoryContainsOutputRecord
      (writeOutputMemory memory base interval status) base interval status := by
  have h0 : globalAddress base 0 = base + 0 :=
    globalAddress_eq_of_lt (by omega)
  have h8 : globalAddress base 8 = base + 8 :=
    globalAddress_eq_of_lt (by omega)
  have h16 : globalAddress base 16 = base + 16 :=
    globalAddress_eq_of_lt (by omega)
  have h17 : globalAddress base 17 = base + 17 :=
    globalAddress_eq_of_lt (by omega)
  have h18 : globalAddress base 18 = base + 18 :=
    globalAddress_eq_of_lt (by omega)
  have h19 : globalAddress base 19 = base + 19 :=
    globalAddress_eq_of_lt (by omega)
  have h20 : globalAddress base 20 = base + 20 :=
    globalAddress_eq_of_lt (by omega)
  have h21 : globalAddress base 21 = base + 21 :=
    globalAddress_eq_of_lt (by omega)
  have h22 : globalAddress base 22 = base + 22 :=
    globalAddress_eq_of_lt (by omega)
  have h23 : globalAddress base 23 = base + 23 :=
    globalAddress_eq_of_lt hsafe
  simp [MemoryContainsOutputRecord, writeOutputMemory, h0, h8, h16, h17,
    h18, h19, h20, h21, h22, h23, GlobalMemory.loadF64,
    GlobalMemory.loadByte, GlobalMemory.storeF64, GlobalMemory.storeByte,
    RegisterFile.write]

/-- The cell-level relation agrees with the public output observer for record
zero at `base`. -/
theorem MemoryContainsOutputRecord.observeOutput
    (memory : GlobalMemory) (base : Nat) (interval : F64Interval)
    (status : Fin 256) (hsafe : base + 23 < 2 ^ 64)
    (hrecord : MemoryContainsOutputRecord memory base interval status) :
    observeOutput memory base 0 =
      some (expectedObservedOutput interval status) := by
  rcases hrecord with
    ⟨hlo, hhi, hstatus, h17, h18, h19, h20, h21, h22, h23⟩
  have hbase : globalAddress base 0 = base := by
    simpa using globalAddress_eq_of_lt (base := base) (offset := 0) (by omega)
  rw [hbase] at hlo
  unfold SparkInterval.PTX.observeOutput
  simp [readReserved, expectedObservedOutput, hbase, hlo, hhi, hstatus,
    h17, h18, h19, h20, h21, h22, h23]

theorem outputCompilerRegisters_indices (builder : Builder) :
    (outputCompilerRegisters builder).status.index = builder.nextByte ∧
      (outputCompilerRegisters builder).zero.index = builder.nextByte + 1 := by
  simp [outputCompilerRegisters]

private theorem foldOutputReserved_nextByte (indices : List Nat)
    (outputBase : Reg .u64) (zero : Reg .byte) (builder : Builder) :
    (indices.foldl (fun next index =>
      next.emit (.storeGlobalByte outputBase (17 + index) zero))
      builder).nextByte = builder.nextByte := by
  induction indices generalizing builder with
  | nil => rfl
  | cons index rest induction =>
      rw [List.foldl_cons, induction]
      rfl

private theorem foldOutputReserved_body (indices : List Nat)
    (outputBase : Reg .u64) (zero : Reg .byte) (builder : Builder) :
    (indices.foldl (fun next index =>
      next.emit (.storeGlobalByte outputBase (17 + index) zero))
      builder).body.toList =
      builder.body.toList ++ indices.map (fun index =>
        .storeGlobalByte outputBase (17 + index) zero) := by
  induction indices generalizing builder with
  | nil => simp
  | cons index rest induction =>
      rw [List.foldl_cons, induction]
      simp [Builder.emit, List.append_assoc]

@[simp] theorem emitOutput_nextByte (outputBase : Reg .u64)
    (result : IntervalRegisters) (status : Fin 256) (builder : Builder) :
    (emitOutput outputBase result status builder).nextByte =
      builder.nextByte + 2 := by
  unfold emitOutput
  rw [foldOutputReserved_nextByte]
  simp [Builder.freshByte, Builder.emit]

/-- Production `emitOutput` appends exactly the proof-facing twelve
instructions, including all seven reserved-byte stores. -/
theorem emitOutput_body (outputBase : Reg .u64) (result : IntervalRegisters)
    (status : Fin 256) (builder : Builder) :
    (emitOutput outputBase result status builder).body =
      builder.body ++
        (compiledOutputInstructions outputBase result status builder).toArray := by
  rw [← Array.toList_inj]
  unfold emitOutput
  rw [foldOutputReserved_body]
  have hrange : List.range 7 = [0, 1, 2, 3, 4, 5, 6] := by decide
  rw [hrange]
  simp [compiledOutputInstructions, outputCompilerRegisters,
    Builder.freshByte, Builder.emit, List.append_assoc]

@[simp] theorem compiledOutputInstructions_length (outputBase : Reg .u64)
    (result : IntervalRegisters) (status : Fin 256) (builder : Builder) :
    (compiledOutputInstructions outputBase result status builder).length = 12 := by
  simp [compiledOutputInstructions]

theorem emitOutput_body_size (outputBase : Reg .u64)
    (result : IntervalRegisters) (status : Fin 256) (builder : Builder) :
    (emitOutput outputBase result status builder).body.size =
      builder.body.size + 12 := by
  rw [emitOutput_body, Array.size_append]
  simp

/-- Execute the exact output slice selected by the production compiler.

The result states the exact memory transformation without prematurely assuming
that wrapped addresses are distinct.  `SafeKernelLayout` supplies that fact
when this slice is composed with the prologue and `observeOutput`. -/
theorem executeCompiledOutput
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (outputBase : Reg .u64)
    (result : IntervalRegisters) (status : Fin 256) (builder : Builder)
    (base : Nat) (interval : F64Interval)
    (hbase : state.u64.read outputBase.index = some base)
    (hlo : state.f64.read result.lo.index = some interval.lo)
    (hhi : state.f64.read result.hi.index = some interval.hi) :
    ∃ final,
      executeCode module parameters thread
          (compiledOutputInstructions outputBase result status builder) state =
        some { control := .fallthrough, state := final } ∧
      final.memory = writeOutputMemory state.memory base interval status := by
  unfold RegisterFile.read at hbase hlo hhi
  let registers := outputCompilerRegisters builder
  let bytes := (state.byte.write registers.status.index status).write
    registers.zero.index ⟨0, by decide⟩
  let final : MachineState := {
    state with
    byte := bytes
    memory := writeOutputMemory state.memory base interval status
    pc := state.pc + 12
  }
  refine ⟨final, ?_, rfl⟩
  simp [compiledOutputInstructions, outputCompilerRegisters, registers, bytes,
    final, executeCode, executeInstruction, hbase, hlo, hhi,
    writeOutputMemory, MachineState.advance, MachineState.writeByte,
    RegisterFile.read, RegisterFile.write]

/-- Safe-layout corollary: successful execution leaves a complete observable
24-byte output record. -/
theorem executeCompiledOutput_contains
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (outputBase : Reg .u64)
    (result : IntervalRegisters) (status : Fin 256) (builder : Builder)
    (base : Nat) (interval : F64Interval)
    (hbase : state.u64.read outputBase.index = some base)
    (hlo : state.f64.read result.lo.index = some interval.lo)
    (hhi : state.f64.read result.hi.index = some interval.hi)
    (hsafe : base + 23 < 2 ^ 64) :
    ∃ final,
      executeCode module parameters thread
          (compiledOutputInstructions outputBase result status builder) state =
        some { control := .fallthrough, state := final } ∧
      MemoryContainsOutputRecord final.memory base interval status := by
  rcases executeCompiledOutput module parameters thread state outputBase result
    status builder base interval hbase hlo hhi with ⟨final, hexec, hmemory⟩
  refine ⟨final, hexec, ?_⟩
  rw [hmemory]
  exact writeOutputMemory_contains state.memory base interval status hsafe

/-- Public-observer form of the safe output-slice theorem. -/
theorem executeCompiledOutput_observe
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (state : MachineState) (outputBase : Reg .u64)
    (result : IntervalRegisters) (status : Fin 256) (builder : Builder)
    (base : Nat) (interval : F64Interval)
    (hbase : state.u64.read outputBase.index = some base)
    (hlo : state.f64.read result.lo.index = some interval.lo)
    (hhi : state.f64.read result.hi.index = some interval.hi)
    (hsafe : base + 23 < 2 ^ 64) :
    ∃ final,
      executeCode module parameters thread
          (compiledOutputInstructions outputBase result status builder) state =
        some { control := .fallthrough, state := final } ∧
      observeOutput final.memory base 0 =
        some (expectedObservedOutput interval status) := by
  rcases executeCompiledOutput_contains module parameters thread state
      outputBase result status builder base interval hbase hlo hhi hsafe with
    ⟨final, hexecute, hrecord⟩
  exact ⟨final, hexecute,
    MemoryContainsOutputRecord.observeOutput final.memory base interval status
      hsafe hrecord⟩

end SparkInterval.PTX
