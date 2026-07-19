import SparkInterval.PTX.CompilerDataflow
import SparkInterval.PTX.CompilerFiniteGuardRefinement
import SparkInterval.PTX.F64RegisterEffects
import SparkInterval.PTX.U64MemoryEffects

/-!
# Compiler body-extension and f64 write dataflow

This file isolates a syntactic invariant needed by whole-expression execution:
`compileExpr` only appends instructions, and every appended instruction that
writes an f64 register targets an index at or above the incoming f64 frontier.
The invariant includes constants, row loads, negation, finite guards, all
directed arithmetic temporaries, and natural-power multiplication loops.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- Every f64 write in `code` is at or above `frontier`. -/
def F64WritesAtOrAbove (frontier : Nat) (code : List Instruction) : Prop :=
  ∀ destination, destination ∈ Instruction.f64Destinations code →
    frontier ≤ destination

theorem F64WritesAtOrAbove.nil (frontier : Nat) :
    F64WritesAtOrAbove frontier [] := by
  simp [F64WritesAtOrAbove]

theorem F64WritesAtOrAbove.append {frontier : Nat}
    {first second : List Instruction}
    (hfirst : F64WritesAtOrAbove frontier first)
    (hsecond : F64WritesAtOrAbove frontier second) :
    F64WritesAtOrAbove frontier (first ++ second) := by
  intro destination hdestination
  rw [Instruction.f64Destinations_append] at hdestination
  rcases List.mem_append.mp hdestination with hfirstDestination | hsecondDestination
  · exact hfirst destination hfirstDestination
  · exact hsecond destination hsecondDestination

/-- A property established at a later frontier also holds at every earlier
frontier. -/
theorem F64WritesAtOrAbove.mono {earlier later : Nat} {code : List Instruction}
    (hfrontier : earlier ≤ later) (hwrites : F64WritesAtOrAbove later code) :
    F64WritesAtOrAbove earlier code := by
  intro destination hdestination
  exact Nat.le_trans hfrontier (hwrites destination hdestination)

/-- Every u64 write in `code` is at or above `frontier`. -/
def U64WritesAtOrAbove (frontier : Nat) (code : List Instruction) : Prop :=
  ∀ destination, destination ∈ Instruction.u64Destinations code →
    frontier ≤ destination

theorem U64WritesAtOrAbove.nil (frontier : Nat) :
    U64WritesAtOrAbove frontier [] := by
  simp [U64WritesAtOrAbove]

theorem U64WritesAtOrAbove.append {frontier : Nat}
    {first second : List Instruction}
    (hfirst : U64WritesAtOrAbove frontier first)
    (hsecond : U64WritesAtOrAbove frontier second) :
    U64WritesAtOrAbove frontier (first ++ second) := by
  intro destination hdestination
  rw [Instruction.u64Destinations_append] at hdestination
  rcases List.mem_append.mp hdestination with hleft | hright
  · exact hfirst destination hleft
  · exact hsecond destination hright

theorem U64WritesAtOrAbove.mono {earlier later : Nat} {code : List Instruction}
    (hfrontier : earlier ≤ later) (hwrites : U64WritesAtOrAbove later code) :
    U64WritesAtOrAbove earlier code := by
  intro destination hdestination
  exact Nat.le_trans hfrontier (hwrites destination hdestination)

/-- `after` is obtained by appending a slice to `before`, and that slice only
writes f64 registers at or above the fixed `frontier`. -/
def Builder.BodyF64SafeExtension (frontier : Nat)
    (before after : Builder) : Prop :=
  ∃ suffix,
    after.body.toList = before.body.toList ++ suffix ∧
      F64WritesAtOrAbove frontier suffix

theorem Builder.BodyF64SafeExtension.refl (frontier : Nat) (builder : Builder) :
    builder.BodyF64SafeExtension frontier builder := by
  exact ⟨[], by simp, F64WritesAtOrAbove.nil frontier⟩

theorem Builder.BodyF64SafeExtension.trans {frontier : Nat}
    {first middle final : Builder}
    (hfirst : first.BodyF64SafeExtension frontier middle)
    (hsecond : middle.BodyF64SafeExtension frontier final) :
    first.BodyF64SafeExtension frontier final := by
  rcases hfirst with ⟨firstCode, hfirstBody, hfirstWrites⟩
  rcases hsecond with ⟨secondCode, hsecondBody, hsecondWrites⟩
  refine ⟨firstCode ++ secondCode, ?_, hfirstWrites.append hsecondWrites⟩
  rw [hsecondBody, hfirstBody, List.append_assoc]

theorem Builder.BodyF64SafeExtension.mono {earlier later : Nat}
    {before after : Builder} (hfrontier : earlier ≤ later)
    (hextension : before.BodyF64SafeExtension later after) :
    before.BodyF64SafeExtension earlier after := by
  rcases hextension with ⟨code, hbody, hwrites⟩
  exact ⟨code, hbody, hwrites.mono hfrontier⟩

/-- Body extension carrying both the u64 freshness and store-free invariants
needed to preserve the prologue row pointer and input memory. -/
def Builder.BodyU64MemorySafeExtension (frontier : Nat)
    (before after : Builder) : Prop :=
  ∃ suffix,
    after.body.toList = before.body.toList ++ suffix ∧
      U64WritesAtOrAbove frontier suffix ∧
      GlobalMemoryWriteFree suffix

theorem Builder.BodyU64MemorySafeExtension.refl
    (frontier : Nat) (builder : Builder) :
    builder.BodyU64MemorySafeExtension frontier builder := by
  exact ⟨[], by simp, U64WritesAtOrAbove.nil frontier,
    GlobalMemoryWriteFree.nil⟩

theorem Builder.BodyU64MemorySafeExtension.trans {frontier : Nat}
    {first middle final : Builder}
    (hfirst : first.BodyU64MemorySafeExtension frontier middle)
    (hsecond : middle.BodyU64MemorySafeExtension frontier final) :
    first.BodyU64MemorySafeExtension frontier final := by
  rcases hfirst with ⟨firstCode, hfirstBody, hfirstU64, hfirstMemory⟩
  rcases hsecond with ⟨secondCode, hsecondBody, hsecondU64, hsecondMemory⟩
  refine ⟨firstCode ++ secondCode, ?_, hfirstU64.append hsecondU64,
    hfirstMemory.append hsecondMemory⟩
  rw [hsecondBody, hfirstBody, List.append_assoc]

theorem Builder.BodyU64MemorySafeExtension.mono {earlier later : Nat}
    {before after : Builder} (hfrontier : earlier ≤ later)
    (hextension : before.BodyU64MemorySafeExtension later after) :
    before.BodyU64MemorySafeExtension earlier after := by
  rcases hextension with ⟨code, hbody, hu64, hmemory⟩
  exact ⟨code, hbody, hu64.mono hfrontier, hmemory⟩

/-- Folding `Builder.emit` over a list appends that list verbatim. -/
theorem listFoldEmit_body_toList (instructions : List Instruction)
    (builder : Builder) :
    (instructions.foldl (fun next instruction => next.emit instruction)
      builder).body.toList = builder.body.toList ++ instructions := by
  induction instructions generalizing builder with
  | nil => simp
  | cons instruction rest induction =>
      rw [List.foldl_cons, induction]
      simp [Builder.emit, List.append_assoc]

/-- Array form used by the production arithmetic fragments. -/
theorem arrayFoldEmit_body_toList (instructions : Array Instruction)
    (builder : Builder) :
    (instructions.foldl (fun next instruction => next.emit instruction)
      builder).body.toList = builder.body.toList ++ instructions.toList := by
  rw [← Array.foldl_toList]
  exact listFoldEmit_body_toList instructions.toList builder

/-- Emitting a guard is f64-write-free, at any chosen baseline frontier. -/
theorem emitFiniteGuard_body_f64Safe (frontier : Nat)
    (value : IntervalRegisters) (builder : Builder) :
    builder.BodyF64SafeExtension frontier (emitFiniteGuard value builder) := by
  refine ⟨compiledFiniteGuardInstructions value builder,
    emitFiniteGuard_body_toList value builder, ?_⟩
  simp [F64WritesAtOrAbove, Instruction.f64Destinations,
    compiledFiniteGuardInstructions, finiteGuardCompilerRegisters,
    finiteGuardInstructions, Instruction.f64Destination?]

/-! ## Exact node-local appended slices -/

def compileConstAppendedCode (value : IntervalBits) (builder : Builder) :
    List Instruction :=
  let result := builder.freshInterval.1
  [.movF64Bits result.lo value.lo.value,
   .movF64Bits result.hi value.hi.value]

def compileVarAppendedCode (rowBase : Reg .u64) (index : Nat)
    (builder : Builder) : List Instruction :=
  let result := builder.freshInterval.1
  [.loadGlobalF64 result.lo rowBase (index * 16),
   .loadGlobalF64 result.hi rowBase (index * 16 + 8)]

def compileNegAppendedCode (argument : IntervalRegisters) (builder : Builder) :
    List Instruction :=
  let result := builder.freshInterval.1
  [.xorF64Sign result.lo argument.hi,
   .xorF64Sign result.hi argument.lo]

def compileAddAppendedCode (left right : IntervalRegisters) (builder : Builder) :
    List Instruction :=
  let afterLeftGuard := emitFiniteGuard left builder
  let afterRightGuard := emitFiniteGuard right afterLeftGuard
  let result := afterRightGuard.freshInterval.1
  compiledFiniteGuardInstructions left builder ++
    compiledFiniteGuardInstructions right afterLeftGuard ++
    (addArithmeticFragment result left right).toList

def compileSubAppendedCode (left right : IntervalRegisters) (builder : Builder) :
    List Instruction :=
  let afterLeftGuard := emitFiniteGuard left builder
  let afterRightGuard := emitFiniteGuard right afterLeftGuard
  let result := afterRightGuard.freshInterval.1
  compiledFiniteGuardInstructions left builder ++
    compiledFiniteGuardInstructions right afterLeftGuard ++
    (subArithmeticFragment result left right).toList

def compileMulAppendedCode (left right : IntervalRegisters) (builder : Builder) :
    List Instruction :=
  let afterLeftGuard := emitFiniteGuard left builder
  let afterRightGuard := emitFiniteGuard right afterLeftGuard
  let allocation := allocateMulRegisters afterRightGuard
  compiledFiniteGuardInstructions left builder ++
    compiledFiniteGuardInstructions right afterLeftGuard ++
    (mulArithmeticFragment allocation.result left right
      allocation.temporaries).toList

theorem compileConst_body_toList (value : IntervalBits) (builder : Builder) :
    (compileConst value builder).2.body.toList =
      builder.body.toList ++ compileConstAppendedCode value builder := by
  simp [compileConst, compileConstAppendedCode, Builder.freshInterval,
    Builder.freshF64, Builder.emit, List.append_assoc]

theorem compileExpr_var_body_toList (rowBase : Reg .u64) (index : Nat)
    (builder : Builder) :
    (compileExpr rowBase (.var index) builder).2.body.toList =
      builder.body.toList ++ compileVarAppendedCode rowBase index builder := by
  simp [compileExpr, compileVarAppendedCode, Builder.freshInterval,
    Builder.freshF64, Builder.emit, List.append_assoc]

theorem compileExpr_neg_tail_body_toList (argument : IntervalRegisters)
    (builder : Builder) :
    let fresh := builder.freshInterval
    let afterLo := fresh.2.emit (.xorF64Sign fresh.1.lo argument.hi)
    let final := afterLo.emit (.xorF64Sign fresh.1.hi argument.lo)
    final.body.toList =
      builder.body.toList ++ compileNegAppendedCode argument builder := by
  simp [compileNegAppendedCode, Builder.freshInterval, Builder.freshF64,
    Builder.emit, List.append_assoc]

theorem compileAdd_body_toList (left right : IntervalRegisters)
    (builder : Builder) :
    (compileAdd left right builder).2.body.toList =
      builder.body.toList ++ compileAddAppendedCode left right builder := by
  simp [compileAdd, compileAddAppendedCode, arrayFoldEmit_body_toList,
    emitFiniteGuard_body_toList, Builder.freshInterval, Builder.freshF64,
    List.append_assoc]

theorem compileSub_body_toList (left right : IntervalRegisters)
    (builder : Builder) :
    (compileSub left right builder).2.body.toList =
      builder.body.toList ++ compileSubAppendedCode left right builder := by
  simp [compileSub, compileSubAppendedCode, arrayFoldEmit_body_toList,
    emitFiniteGuard_body_toList, Builder.freshInterval, Builder.freshF64,
    List.append_assoc]

theorem compileMul_body_toList (left right : IntervalRegisters)
    (builder : Builder) :
    (compileMul left right builder).2.body.toList =
      builder.body.toList ++ compileMulAppendedCode left right builder := by
  simp [compileMul, compileMulAppendedCode, arrayFoldEmit_body_toList,
    emitFiniteGuard_body_toList, allocateMulRegisters,
    Builder.freshInterval, Builder.freshF64, List.append_assoc]

/-! ## Exact node-local f64 destination traces -/

@[simp] theorem compiledFiniteGuardInstructions_f64Destinations
    (value : IntervalRegisters) (builder : Builder) :
    Instruction.f64Destinations
        (compiledFiniteGuardInstructions value builder) = [] := by
  simp [compiledFiniteGuardInstructions, finiteGuardCompilerRegisters,
    finiteGuardInstructions, Instruction.f64Destinations,
    Instruction.f64Destination?]

@[simp] theorem addArithmeticFragment_f64Destinations
    (result left right : IntervalRegisters) :
    Instruction.f64Destinations
        (addArithmeticFragment result left right).toList =
      [result.lo.index, result.hi.index] := by
  simp [addArithmeticFragment, Instruction.f64Destinations,
    Instruction.f64Destination?]

@[simp] theorem subArithmeticFragment_f64Destinations
    (result left right : IntervalRegisters) :
    Instruction.f64Destinations
        (subArithmeticFragment result left right).toList =
      [result.lo.index, result.hi.index] := by
  simp [subArithmeticFragment, Instruction.f64Destinations,
    Instruction.f64Destination?]

@[simp] theorem mulArithmeticFragment_f64Destinations
    (result left right : IntervalRegisters) (tmp : MulArithmeticTemporaries) :
    Instruction.f64Destinations
        (mulArithmeticFragment result left right tmp).toList =
      mulArithmeticDestinationIndices result tmp := by
  simp [mulArithmeticFragment, mulArithmeticDestinationIndices,
    Instruction.f64Destinations, Instruction.f64Destination?]

theorem compileConstAppendedCode_f64Destinations
    (value : IntervalBits) (builder : Builder) :
    Instruction.f64Destinations (compileConstAppendedCode value builder) =
      [builder.nextF64, builder.nextF64 + 1] := by
  simp [compileConstAppendedCode, Builder.freshInterval, Builder.freshF64,
    Instruction.f64Destinations, Instruction.f64Destination?]

theorem compileVarAppendedCode_f64Destinations
    (rowBase : Reg .u64) (index : Nat) (builder : Builder) :
    Instruction.f64Destinations
        (compileVarAppendedCode rowBase index builder) =
      [builder.nextF64, builder.nextF64 + 1] := by
  simp [compileVarAppendedCode, Builder.freshInterval, Builder.freshF64,
    Instruction.f64Destinations, Instruction.f64Destination?]

theorem compileNegAppendedCode_f64Destinations
    (argument : IntervalRegisters) (builder : Builder) :
    Instruction.f64Destinations (compileNegAppendedCode argument builder) =
      [builder.nextF64, builder.nextF64 + 1] := by
  simp [compileNegAppendedCode, Builder.freshInterval, Builder.freshF64,
    Instruction.f64Destinations, Instruction.f64Destination?]

theorem compileAddAppendedCode_f64Destinations
    (left right : IntervalRegisters) (builder : Builder) :
    Instruction.f64Destinations (compileAddAppendedCode left right builder) =
      [builder.nextF64, builder.nextF64 + 1] := by
  simp [compileAddAppendedCode, Builder.freshInterval, Builder.freshF64]

theorem compileSubAppendedCode_f64Destinations
    (left right : IntervalRegisters) (builder : Builder) :
    Instruction.f64Destinations (compileSubAppendedCode left right builder) =
      [builder.nextF64, builder.nextF64 + 1] := by
  simp [compileSubAppendedCode, Builder.freshInterval, Builder.freshF64]

theorem compileMulAppendedCode_f64Destinations
    (left right : IntervalRegisters) (builder : Builder) :
    Instruction.f64Destinations (compileMulAppendedCode left right builder) =
      (compileMulAllocation left right builder).destinationIndices := by
  simp [compileMulAppendedCode, compileMulAllocation,
    MulRegisterAllocation.destinationIndices,
    mulArithmeticDestinationIndices]

/-! ## Exact node-local u64 and memory effects -/

@[simp] theorem compiledFiniteGuardInstructions_u64Destinations
    (value : IntervalRegisters) (builder : Builder) :
    Instruction.u64Destinations
        (compiledFiniteGuardInstructions value builder) =
      [builder.nextU64, builder.nextU64 + 1] := by
  simp [compiledFiniteGuardInstructions, finiteGuardCompilerRegisters,
    finiteGuardInstructions, Instruction.u64Destinations,
    Instruction.u64Destination?]

theorem compileConstAppendedCode_u64Destinations
    (value : IntervalBits) (builder : Builder) :
    Instruction.u64Destinations (compileConstAppendedCode value builder) = [] := by
  simp [compileConstAppendedCode, Builder.freshInterval, Builder.freshF64,
    Instruction.u64Destinations, Instruction.u64Destination?]

theorem compileVarAppendedCode_u64Destinations
    (rowBase : Reg .u64) (index : Nat) (builder : Builder) :
    Instruction.u64Destinations
        (compileVarAppendedCode rowBase index builder) = [] := by
  simp [compileVarAppendedCode, Builder.freshInterval, Builder.freshF64,
    Instruction.u64Destinations, Instruction.u64Destination?]

theorem compileNegAppendedCode_u64Destinations
    (argument : IntervalRegisters) (builder : Builder) :
    Instruction.u64Destinations (compileNegAppendedCode argument builder) = [] := by
  simp [compileNegAppendedCode, Builder.freshInterval, Builder.freshF64,
    Instruction.u64Destinations, Instruction.u64Destination?]

@[simp] theorem addArithmeticFragment_u64Destinations
    (result left right : IntervalRegisters) :
    Instruction.u64Destinations
        (addArithmeticFragment result left right).toList = [] := by
  simp [addArithmeticFragment, Instruction.u64Destinations,
    Instruction.u64Destination?]

@[simp] theorem subArithmeticFragment_u64Destinations
    (result left right : IntervalRegisters) :
    Instruction.u64Destinations
        (subArithmeticFragment result left right).toList = [] := by
  simp [subArithmeticFragment, Instruction.u64Destinations,
    Instruction.u64Destination?]

theorem compileAddAppendedCode_u64Destinations
    (left right : IntervalRegisters) (builder : Builder) :
    Instruction.u64Destinations (compileAddAppendedCode left right builder) =
      [builder.nextU64, builder.nextU64 + 1,
       builder.nextU64 + 2, builder.nextU64 + 3] := by
  simp [compileAddAppendedCode, emitFiniteGuard_nextU64]

theorem compileSubAppendedCode_u64Destinations
    (left right : IntervalRegisters) (builder : Builder) :
    Instruction.u64Destinations (compileSubAppendedCode left right builder) =
      [builder.nextU64, builder.nextU64 + 1,
       builder.nextU64 + 2, builder.nextU64 + 3] := by
  simp [compileSubAppendedCode, emitFiniteGuard_nextU64]

theorem compileMulAppendedCode_u64Destinations
    (left right : IntervalRegisters) (builder : Builder) :
    Instruction.u64Destinations (compileMulAppendedCode left right builder) =
      [builder.nextU64, builder.nextU64 + 1,
       builder.nextU64 + 2, builder.nextU64 + 3] := by
  simp [compileMulAppendedCode, emitFiniteGuard_nextU64,
    mulArithmeticFragment, Instruction.u64Destinations,
    Instruction.u64Destination?]

theorem compiledFiniteGuardInstructions_memoryWriteFree
    (value : IntervalRegisters) (builder : Builder) :
    GlobalMemoryWriteFree (compiledFiniteGuardInstructions value builder) := by
  simp [GlobalMemoryWriteFree, compiledFiniteGuardInstructions,
    finiteGuardCompilerRegisters, finiteGuardInstructions,
    Instruction.writesGlobalMemory]

theorem compileConstAppendedCode_memoryWriteFree
    (value : IntervalBits) (builder : Builder) :
    GlobalMemoryWriteFree (compileConstAppendedCode value builder) := by
  simp [GlobalMemoryWriteFree, compileConstAppendedCode,
    Builder.freshInterval, Builder.freshF64, Instruction.writesGlobalMemory]

theorem compileVarAppendedCode_memoryWriteFree
    (rowBase : Reg .u64) (index : Nat) (builder : Builder) :
    GlobalMemoryWriteFree (compileVarAppendedCode rowBase index builder) := by
  simp [GlobalMemoryWriteFree, compileVarAppendedCode,
    Builder.freshInterval, Builder.freshF64, Instruction.writesGlobalMemory]

theorem compileNegAppendedCode_memoryWriteFree
    (argument : IntervalRegisters) (builder : Builder) :
    GlobalMemoryWriteFree (compileNegAppendedCode argument builder) := by
  simp [GlobalMemoryWriteFree, compileNegAppendedCode,
    Builder.freshInterval, Builder.freshF64, Instruction.writesGlobalMemory]

theorem compileAddAppendedCode_memoryWriteFree
    (left right : IntervalRegisters) (builder : Builder) :
    GlobalMemoryWriteFree (compileAddAppendedCode left right builder) := by
  simp [GlobalMemoryWriteFree, compileAddAppendedCode,
    compiledFiniteGuardInstructions, finiteGuardCompilerRegisters,
    finiteGuardInstructions, addArithmeticFragment,
    Instruction.writesGlobalMemory]

theorem compileSubAppendedCode_memoryWriteFree
    (left right : IntervalRegisters) (builder : Builder) :
    GlobalMemoryWriteFree (compileSubAppendedCode left right builder) := by
  simp [GlobalMemoryWriteFree, compileSubAppendedCode,
    compiledFiniteGuardInstructions, finiteGuardCompilerRegisters,
    finiteGuardInstructions, subArithmeticFragment,
    Instruction.writesGlobalMemory]

theorem compileMulAppendedCode_memoryWriteFree
    (left right : IntervalRegisters) (builder : Builder) :
    GlobalMemoryWriteFree (compileMulAppendedCode left right builder) := by
  simp [GlobalMemoryWriteFree, compileMulAppendedCode,
    compiledFiniteGuardInstructions, finiteGuardCompilerRegisters,
    finiteGuardInstructions, mulArithmeticFragment,
    Instruction.writesGlobalMemory]

/-! ## Node-local u64/memory safe-extension theorems -/

theorem compileConst_body_u64MemorySafe
    (value : IntervalBits) (builder : Builder) :
    builder.BodyU64MemorySafeExtension builder.nextU64
      (compileConst value builder).2 := by
  refine ⟨compileConstAppendedCode value builder,
    compileConst_body_toList value builder, ?_,
    compileConstAppendedCode_memoryWriteFree value builder⟩
  intro destination hdestination
  rw [compileConstAppendedCode_u64Destinations] at hdestination
  simp at hdestination

theorem compileExpr_var_body_u64MemorySafe
    (rowBase : Reg .u64) (index : Nat) (builder : Builder) :
    builder.BodyU64MemorySafeExtension builder.nextU64
      (compileExpr rowBase (.var index) builder).2 := by
  refine ⟨compileVarAppendedCode rowBase index builder,
    compileExpr_var_body_toList rowBase index builder, ?_,
    compileVarAppendedCode_memoryWriteFree rowBase index builder⟩
  intro destination hdestination
  rw [compileVarAppendedCode_u64Destinations] at hdestination
  simp at hdestination

theorem compileExpr_neg_tail_body_u64MemorySafe
    (argument : IntervalRegisters) (builder : Builder) :
    let fresh := builder.freshInterval
    let afterLo := fresh.2.emit (.xorF64Sign fresh.1.lo argument.hi)
    let final := afterLo.emit (.xorF64Sign fresh.1.hi argument.lo)
    builder.BodyU64MemorySafeExtension builder.nextU64 final := by
  dsimp only
  refine ⟨compileNegAppendedCode argument builder,
    compileExpr_neg_tail_body_toList argument builder, ?_,
    compileNegAppendedCode_memoryWriteFree argument builder⟩
  intro destination hdestination
  rw [compileNegAppendedCode_u64Destinations] at hdestination
  simp at hdestination

theorem compileAdd_body_u64MemorySafe (left right : IntervalRegisters)
    (builder : Builder) :
    builder.BodyU64MemorySafeExtension builder.nextU64
      (compileAdd left right builder).2 := by
  refine ⟨compileAddAppendedCode left right builder,
    compileAdd_body_toList left right builder, ?_,
    compileAddAppendedCode_memoryWriteFree left right builder⟩
  intro destination hdestination
  rw [compileAddAppendedCode_u64Destinations] at hdestination
  simp at hdestination
  omega

theorem compileSub_body_u64MemorySafe (left right : IntervalRegisters)
    (builder : Builder) :
    builder.BodyU64MemorySafeExtension builder.nextU64
      (compileSub left right builder).2 := by
  refine ⟨compileSubAppendedCode left right builder,
    compileSub_body_toList left right builder, ?_,
    compileSubAppendedCode_memoryWriteFree left right builder⟩
  intro destination hdestination
  rw [compileSubAppendedCode_u64Destinations] at hdestination
  simp at hdestination
  omega

theorem compileMul_body_u64MemorySafe (left right : IntervalRegisters)
    (builder : Builder) :
    builder.BodyU64MemorySafeExtension builder.nextU64
      (compileMul left right builder).2 := by
  refine ⟨compileMulAppendedCode left right builder,
    compileMul_body_toList left right builder, ?_,
    compileMulAppendedCode_memoryWriteFree left right builder⟩
  intro destination hdestination
  rw [compileMulAppendedCode_u64Destinations] at hdestination
  simp at hdestination
  omega

/-! ## Node-local safe-extension theorems -/

theorem compileConst_body_f64Safe (value : IntervalBits) (builder : Builder) :
    builder.BodyF64SafeExtension builder.nextF64
      (compileConst value builder).2 := by
  refine ⟨compileConstAppendedCode value builder,
    compileConst_body_toList value builder, ?_⟩
  intro destination hdestination
  rw [compileConstAppendedCode_f64Destinations] at hdestination
  simp at hdestination
  omega

theorem compileExpr_var_body_f64Safe (rowBase : Reg .u64) (index : Nat)
    (builder : Builder) :
    builder.BodyF64SafeExtension builder.nextF64
      (compileExpr rowBase (.var index) builder).2 := by
  refine ⟨compileVarAppendedCode rowBase index builder,
    compileExpr_var_body_toList rowBase index builder, ?_⟩
  intro destination hdestination
  rw [compileVarAppendedCode_f64Destinations] at hdestination
  simp at hdestination
  omega

theorem compileExpr_neg_tail_body_f64Safe (argument : IntervalRegisters)
    (builder : Builder) :
    let fresh := builder.freshInterval
    let afterLo := fresh.2.emit (.xorF64Sign fresh.1.lo argument.hi)
    let final := afterLo.emit (.xorF64Sign fresh.1.hi argument.lo)
    builder.BodyF64SafeExtension builder.nextF64 final := by
  dsimp only
  refine ⟨compileNegAppendedCode argument builder,
    compileExpr_neg_tail_body_toList argument builder, ?_⟩
  intro destination hdestination
  rw [compileNegAppendedCode_f64Destinations] at hdestination
  simp at hdestination
  omega

theorem compileAdd_body_f64Safe (left right : IntervalRegisters)
    (builder : Builder) :
    builder.BodyF64SafeExtension builder.nextF64
      (compileAdd left right builder).2 := by
  refine ⟨compileAddAppendedCode left right builder,
    compileAdd_body_toList left right builder, ?_⟩
  intro destination hdestination
  rw [compileAddAppendedCode_f64Destinations] at hdestination
  simp at hdestination
  omega

theorem compileSub_body_f64Safe (left right : IntervalRegisters)
    (builder : Builder) :
    builder.BodyF64SafeExtension builder.nextF64
      (compileSub left right builder).2 := by
  refine ⟨compileSubAppendedCode left right builder,
    compileSub_body_toList left right builder, ?_⟩
  intro destination hdestination
  rw [compileSubAppendedCode_f64Destinations] at hdestination
  simp at hdestination
  omega

theorem compileMul_body_f64Safe (left right : IntervalRegisters)
    (builder : Builder) :
    builder.BodyF64SafeExtension builder.nextF64
      (compileMul left right builder).2 := by
  refine ⟨compileMulAppendedCode left right builder,
    compileMul_body_toList left right builder, ?_⟩
  intro destination hdestination
  rw [compileMulAppendedCode_f64Destinations] at hdestination
  exact allocateMulRegisters_destination_ge _ hdestination

/-! ## Recursive composition -/

/-- Each guarded arithmetic node allocates two exponent temporaries per
operand and therefore advances the u64 frontier by four. -/
@[simp] theorem compileAdd_nextU64 (left right : IntervalRegisters)
    (builder : Builder) :
    (compileAdd left right builder).2.nextU64 = builder.nextU64 + 4 := by
  simp [compileAdd, emitFiniteGuard_nextU64, Builder.freshInterval,
    Builder.freshF64, Builder.emit, addArithmeticFragment]

@[simp] theorem compileSub_nextU64 (left right : IntervalRegisters)
    (builder : Builder) :
    (compileSub left right builder).2.nextU64 = builder.nextU64 + 4 := by
  simp [compileSub, emitFiniteGuard_nextU64, Builder.freshInterval,
    Builder.freshF64, Builder.emit, subArithmeticFragment]

@[simp] theorem compileMul_nextU64 (left right : IntervalRegisters)
    (builder : Builder) :
    (compileMul left right builder).2.nextU64 = builder.nextU64 + 4 := by
  simp [compileMul, emitFiniteGuard_nextU64, allocateMulRegisters,
    Builder.freshInterval, Builder.freshF64, Builder.emit,
    mulArithmeticFragment]

@[simp] theorem compileConst_nextU64 (value : IntervalBits) (builder : Builder) :
    (compileConst value builder).2.nextU64 = builder.nextU64 := by
  simp [compileConst, Builder.freshInterval, Builder.freshF64, Builder.emit]

/-- Repeated multiplication allocates four guard u64 registers per
iteration. -/
theorem compilePowLoop_nextU64 (base : IntervalRegisters) (count : Nat)
    (current : IntervalRegisters) (builder : Builder) :
    (compilePowLoop base count current builder).2.nextU64 =
      builder.nextU64 + count * 4 := by
  induction count generalizing current builder with
  | zero => simp [compilePowLoop]
  | succ count induction =>
      rw [compilePowLoop, induction, compileMul_nextU64]
      omega

/-- Exact number of u64 exponent temporaries allocated by expression guards. -/
def PolynomialExpr.u64RegisterCost : PolynomialExpr → Nat
  | .const _ | .var _ => 0
  | .neg argument => argument.u64RegisterCost
  | .add left right | .sub left right | .mul left right =>
      left.u64RegisterCost + right.u64RegisterCost + 4
  | .powNat argument exponent =>
      argument.u64RegisterCost + exponent * 4

/-- Exact u64 frontier accounting for the recursive expression compiler. -/
theorem compileExpr_nextU64 (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    (compileExpr rowBase expression builder).2.nextU64 =
      builder.nextU64 + expression.u64RegisterCost := by
  induction expression generalizing builder with
  | const value =>
      simp [compileExpr, PolynomialExpr.u64RegisterCost]
  | var index =>
      simp [compileExpr, PolynomialExpr.u64RegisterCost,
        Builder.freshInterval, Builder.freshF64, Builder.emit]
  | neg argument induction =>
      simp [compileExpr, PolynomialExpr.u64RegisterCost,
        Builder.freshInterval, Builder.freshF64, Builder.emit, induction]
  | add left right leftInduction rightInduction =>
      rw [compileExpr, compileAdd_nextU64,
        rightInduction (compileExpr rowBase left builder).2,
        leftInduction builder]
      simp [PolynomialExpr.u64RegisterCost]
      omega
  | sub left right leftInduction rightInduction =>
      rw [compileExpr, compileSub_nextU64,
        rightInduction (compileExpr rowBase left builder).2,
        leftInduction builder]
      simp [PolynomialExpr.u64RegisterCost]
      omega
  | mul left right leftInduction rightInduction =>
      rw [compileExpr, compileMul_nextU64,
        rightInduction (compileExpr rowBase left builder).2,
        leftInduction builder]
      simp [PolynomialExpr.u64RegisterCost]
      omega
  | powNat argument exponent induction =>
      rw [compileExpr, compilePowLoop_nextU64, compileConst_nextU64,
        induction builder]
      simp [PolynomialExpr.u64RegisterCost]
      omega

/-- Compiling an expression never moves the u64 frontier backwards. -/
theorem compileExpr_nextU64_mono (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    builder.nextU64 ≤ (compileExpr rowBase expression builder).2.nextU64 := by
  rw [compileExpr_nextU64]
  exact Nat.le_add_right _ _

/-- Every multiplication iteration appends only fresh-frontier f64 writes. -/
theorem compilePowLoop_body_f64Safe (base : IntervalRegisters) (count : Nat)
    (current : IntervalRegisters) (builder : Builder) :
    builder.BodyF64SafeExtension builder.nextF64
      (compilePowLoop base count current builder).2 := by
  induction count generalizing current builder with
  | zero =>
      exact Builder.BodyF64SafeExtension.refl builder.nextF64 builder
  | succ count induction =>
      rw [compilePowLoop]
      apply (compileMul_body_f64Safe current base builder).trans
      apply (induction
        (compileMul current base builder).1
        (compileMul current base builder).2).mono
      exact Nat.le_trans (Nat.le_add_right builder.nextF64 14) (by
        rw [compileMul_nextF64])

/-- The complete recursive production expression compiler only appends code,
and every f64 destination in that appended slice is at or above the incoming
f64 frontier. -/
theorem compileExpr_body_f64Safe (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    builder.BodyF64SafeExtension builder.nextF64
      (compileExpr rowBase expression builder).2 := by
  induction expression generalizing builder with
  | const value =>
      exact compileConst_body_f64Safe value builder
  | var index =>
      exact compileExpr_var_body_f64Safe rowBase index builder
  | neg argument induction =>
      rw [compileExpr]
      apply (induction builder).trans
      apply (compileExpr_neg_tail_body_f64Safe
        (compileExpr rowBase argument builder).1
        (compileExpr rowBase argument builder).2).mono
      exact compileExpr_nextF64_mono rowBase argument builder
  | add left right leftInduction rightInduction =>
      rw [compileExpr]
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      have hleftFrontier : builder.nextF64 ≤ leftCompiled.2.nextF64 :=
        compileExpr_nextF64_mono rowBase left builder
      have hrightFrontier : builder.nextF64 ≤ rightCompiled.2.nextF64 :=
        Nat.le_trans hleftFrontier
          (compileExpr_nextF64_mono rowBase right leftCompiled.2)
      exact (leftInduction builder).trans <|
        ((rightInduction leftCompiled.2).mono hleftFrontier).trans <|
          (compileAdd_body_f64Safe leftCompiled.1 rightCompiled.1
            rightCompiled.2).mono hrightFrontier
  | sub left right leftInduction rightInduction =>
      rw [compileExpr]
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      have hleftFrontier : builder.nextF64 ≤ leftCompiled.2.nextF64 :=
        compileExpr_nextF64_mono rowBase left builder
      have hrightFrontier : builder.nextF64 ≤ rightCompiled.2.nextF64 :=
        Nat.le_trans hleftFrontier
          (compileExpr_nextF64_mono rowBase right leftCompiled.2)
      exact (leftInduction builder).trans <|
        ((rightInduction leftCompiled.2).mono hleftFrontier).trans <|
          (compileSub_body_f64Safe leftCompiled.1 rightCompiled.1
            rightCompiled.2).mono hrightFrontier
  | mul left right leftInduction rightInduction =>
      rw [compileExpr]
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      have hleftFrontier : builder.nextF64 ≤ leftCompiled.2.nextF64 :=
        compileExpr_nextF64_mono rowBase left builder
      have hrightFrontier : builder.nextF64 ≤ rightCompiled.2.nextF64 :=
        Nat.le_trans hleftFrontier
          (compileExpr_nextF64_mono rowBase right leftCompiled.2)
      exact (leftInduction builder).trans <|
        ((rightInduction leftCompiled.2).mono hleftFrontier).trans <|
          (compileMul_body_f64Safe leftCompiled.1 rightCompiled.1
            rightCompiled.2).mono hrightFrontier
  | powNat argument exponent induction =>
      rw [compileExpr]
      let argumentCompiled := compileExpr rowBase argument builder
      let one : IntervalBits := {
        lo := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
        hi := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
      }
      let initialCompiled := compileConst one argumentCompiled.2
      have hargumentFrontier :
          builder.nextF64 ≤ argumentCompiled.2.nextF64 :=
        compileExpr_nextF64_mono rowBase argument builder
      have hinitialFrontier :
          builder.nextF64 ≤ initialCompiled.2.nextF64 := by
        exact Nat.le_trans hargumentFrontier (by
          rw [compileConst_nextF64]
          exact Nat.le_add_right _ _)
      exact (induction builder).trans <|
        ((compileConst_body_f64Safe one argumentCompiled.2).mono
          hargumentFrontier).trans <|
          (compilePowLoop_body_f64Safe argumentCompiled.1 exponent
            initialCompiled.1 initialCompiled.2).mono hinitialFrontier

/-- Every multiplication iteration appends only fresh u64 guard writes and no
global-memory stores. -/
theorem compilePowLoop_body_u64MemorySafe (base : IntervalRegisters)
    (count : Nat) (current : IntervalRegisters) (builder : Builder) :
    builder.BodyU64MemorySafeExtension builder.nextU64
      (compilePowLoop base count current builder).2 := by
  induction count generalizing current builder with
  | zero =>
      exact Builder.BodyU64MemorySafeExtension.refl builder.nextU64 builder
  | succ count induction =>
      rw [compilePowLoop]
      apply (compileMul_body_u64MemorySafe current base builder).trans
      apply (induction
        (compileMul current base builder).1
        (compileMul current base builder).2).mono
      rw [compileMul_nextU64]
      exact Nat.le_add_right _ _

/-- The complete recursive expression slice writes only fresh u64 guard
temporaries and performs no global-memory store. -/
theorem compileExpr_body_u64MemorySafe (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    builder.BodyU64MemorySafeExtension builder.nextU64
      (compileExpr rowBase expression builder).2 := by
  induction expression generalizing builder with
  | const value =>
      exact compileConst_body_u64MemorySafe value builder
  | var index =>
      exact compileExpr_var_body_u64MemorySafe rowBase index builder
  | neg argument induction =>
      rw [compileExpr]
      apply (induction builder).trans
      apply (compileExpr_neg_tail_body_u64MemorySafe
        (compileExpr rowBase argument builder).1
        (compileExpr rowBase argument builder).2).mono
      exact compileExpr_nextU64_mono rowBase argument builder
  | add left right leftInduction rightInduction =>
      rw [compileExpr]
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      have hleftFrontier : builder.nextU64 ≤ leftCompiled.2.nextU64 :=
        compileExpr_nextU64_mono rowBase left builder
      have hrightFrontier : builder.nextU64 ≤ rightCompiled.2.nextU64 :=
        Nat.le_trans hleftFrontier
          (compileExpr_nextU64_mono rowBase right leftCompiled.2)
      exact (leftInduction builder).trans <|
        ((rightInduction leftCompiled.2).mono hleftFrontier).trans <|
          (compileAdd_body_u64MemorySafe leftCompiled.1 rightCompiled.1
            rightCompiled.2).mono hrightFrontier
  | sub left right leftInduction rightInduction =>
      rw [compileExpr]
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      have hleftFrontier : builder.nextU64 ≤ leftCompiled.2.nextU64 :=
        compileExpr_nextU64_mono rowBase left builder
      have hrightFrontier : builder.nextU64 ≤ rightCompiled.2.nextU64 :=
        Nat.le_trans hleftFrontier
          (compileExpr_nextU64_mono rowBase right leftCompiled.2)
      exact (leftInduction builder).trans <|
        ((rightInduction leftCompiled.2).mono hleftFrontier).trans <|
          (compileSub_body_u64MemorySafe leftCompiled.1 rightCompiled.1
            rightCompiled.2).mono hrightFrontier
  | mul left right leftInduction rightInduction =>
      rw [compileExpr]
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      have hleftFrontier : builder.nextU64 ≤ leftCompiled.2.nextU64 :=
        compileExpr_nextU64_mono rowBase left builder
      have hrightFrontier : builder.nextU64 ≤ rightCompiled.2.nextU64 :=
        Nat.le_trans hleftFrontier
          (compileExpr_nextU64_mono rowBase right leftCompiled.2)
      exact (leftInduction builder).trans <|
        ((rightInduction leftCompiled.2).mono hleftFrontier).trans <|
          (compileMul_body_u64MemorySafe leftCompiled.1 rightCompiled.1
            rightCompiled.2).mono hrightFrontier
  | powNat argument exponent induction =>
      rw [compileExpr]
      let argumentCompiled := compileExpr rowBase argument builder
      let one : IntervalBits := {
        lo := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
        hi := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
      }
      let initialCompiled := compileConst one argumentCompiled.2
      have hargumentFrontier :
          builder.nextU64 ≤ argumentCompiled.2.nextU64 :=
        compileExpr_nextU64_mono rowBase argument builder
      have hinitialFrontier :
          builder.nextU64 ≤ initialCompiled.2.nextU64 := by
        simpa [initialCompiled] using hargumentFrontier
      exact (induction builder).trans <|
        ((compileConst_body_u64MemorySafe one argumentCompiled.2).mono
          hargumentFrontier).trans <|
          (compilePowLoop_body_u64MemorySafe argumentCompiled.1 exponent
            initialCompiled.1 initialCompiled.2).mono hinitialFrontier

/-! ## Direct compiler corollaries -/

/-- Explicit append-only form of `compileExpr_body_f64Safe`. -/
theorem compileExpr_body_append_exists (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    ∃ suffix,
      (compileExpr rowBase expression builder).2.body.toList =
        builder.body.toList ++ suffix := by
  rcases compileExpr_body_f64Safe rowBase expression builder with
    ⟨suffix, hbody, _⟩
  exact ⟨suffix, hbody⟩

/-- Explicit combined append/destination contract for the production
expression compiler. -/
theorem compileExpr_body_append_destinations (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    ∃ suffix,
      (compileExpr rowBase expression builder).2.body.toList =
          builder.body.toList ++ suffix ∧
        ∀ destination, destination ∈ Instruction.f64Destinations suffix →
          builder.nextF64 ≤ destination := by
  exact compileExpr_body_f64Safe rowBase expression builder

/-- One concrete appended slice simultaneously satisfies the f64, u64, and
global-memory effect invariants. -/
theorem compileExpr_body_effectSafe (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    ∃ suffix,
      (compileExpr rowBase expression builder).2.body.toList =
          builder.body.toList ++ suffix ∧
        F64WritesAtOrAbove builder.nextF64 suffix ∧
        U64WritesAtOrAbove builder.nextU64 suffix ∧
        GlobalMemoryWriteFree suffix := by
  rcases compileExpr_body_f64Safe rowBase expression builder with
    ⟨f64Code, hf64Body, hf64Writes⟩
  rcases compileExpr_body_u64MemorySafe rowBase expression builder with
    ⟨u64Code, hu64Body, hu64Writes, hmemory⟩
  have hcode : f64Code = u64Code :=
    List.append_cancel_left (hf64Body.symm.trans hu64Body)
  subst u64Code
  exact ⟨f64Code, hf64Body, hf64Writes, hu64Writes, hmemory⟩

/-- Explicit append-only/store-free contract for expression code. -/
theorem compileExpr_body_append_storeFree (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    ∃ suffix,
      (compileExpr rowBase expression builder).2.body.toList =
          builder.body.toList ++ suffix ∧
        GlobalMemoryWriteFree suffix := by
  rcases compileExpr_body_effectSafe rowBase expression builder with
    ⟨suffix, hbody, _, _, hmemory⟩
  exact ⟨suffix, hbody, hmemory⟩

/-! ## Semantic preservation below the write frontier -/

/-- A slice whose writes are all at or above `frontier` preserves every f64
register strictly below `frontier`. -/
theorem executeCode_preservesF64_below
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial : MachineState)
    (execution : CodeExecution) (frontier index : Nat)
    (hwrites : F64WritesAtOrAbove frontier code)
    (hindex : index < frontier)
    (hexecute : executeCode module parameters thread code initial =
      some execution) :
    execution.state.f64.read index = initial.f64.read index := by
  apply executeCode_preserves_f64_read module parameters thread
    code initial execution index
  · intro hmember
    exact Nat.not_le_of_gt hindex (hwrites index hmember)
  · exact hexecute

/-- A slice whose u64 writes are all fresh preserves every earlier u64
register. -/
theorem executeCode_preservesU64_below
    (module : Module) (parameters : KernelParameters) (thread : ThreadContext)
    (code : List Instruction) (initial : MachineState)
    (execution : CodeExecution) (frontier index : Nat)
    (hwrites : U64WritesAtOrAbove frontier code)
    (hindex : index < frontier)
    (hexecute : executeCode module parameters thread code initial =
      some execution) :
    execution.state.u64.read index = initial.u64.read index := by
  apply executeCode_preserves_u64_read module parameters thread
    code initial execution index
  · intro hmember
    exact Nat.not_le_of_gt hindex (hwrites index hmember)
  · exact hexecute

/-- The actual slice appended by `compileExpr` can therefore be chosen so
that every successful execution preserves all pre-frontier f64 registers. -/
theorem compileExpr_appendedCode_preservesF64Below
    (rowBase : Reg .u64) (expression : PolynomialExpr) (builder : Builder) :
    ∃ suffix,
      (compileExpr rowBase expression builder).2.body.toList =
          builder.body.toList ++ suffix ∧
        F64WritesAtOrAbove builder.nextF64 suffix ∧
        ∀ (module : Module) (parameters : KernelParameters)
          (thread : ThreadContext) (initial : MachineState)
          (execution : CodeExecution) (index : Nat),
          index < builder.nextF64 →
          executeCode module parameters thread suffix initial = some execution →
          execution.state.f64.read index = initial.f64.read index := by
  rcases compileExpr_body_f64Safe rowBase expression builder with
    ⟨suffix, hbody, hwrites⟩
  refine ⟨suffix, hbody, hwrites, ?_⟩
  intro module parameters thread initial execution index hindex hexecute
  exact executeCode_preservesF64_below module parameters thread suffix initial
    execution builder.nextF64 index hwrites hindex hexecute

/-- If the prologue row-base register predates expression compilation, the
actual appended expression slice preserves both that pointer and the complete
global memory on every successful control outcome. -/
theorem compileExpr_appendedCode_preservesRowBaseAndMemory
    (rowBase : Reg .u64) (expression : PolynomialExpr) (builder : Builder)
    (hrowBase : rowBase.index < builder.nextU64) :
    ∃ suffix,
      (compileExpr rowBase expression builder).2.body.toList =
          builder.body.toList ++ suffix ∧
        F64WritesAtOrAbove builder.nextF64 suffix ∧
        U64WritesAtOrAbove builder.nextU64 suffix ∧
        GlobalMemoryWriteFree suffix ∧
        ∀ (module : Module) (parameters : KernelParameters)
          (thread : ThreadContext) (initial : MachineState)
          (execution : CodeExecution),
          executeCode module parameters thread suffix initial = some execution →
          execution.state.u64.read rowBase.index =
              initial.u64.read rowBase.index ∧
            execution.state.memory = initial.memory := by
  rcases compileExpr_body_effectSafe rowBase expression builder with
    ⟨suffix, hbody, hf64, hu64, hmemory⟩
  refine ⟨suffix, hbody, hf64, hu64, hmemory, ?_⟩
  intro module parameters thread initial execution hexecute
  constructor
  · exact executeCode_preservesU64_below module parameters thread suffix
      initial execution builder.nextU64 rowBase.index hu64 hrowBase hexecute
  · exact executeCode_preserves_globalMemory module parameters thread suffix
      initial execution hmemory hexecute

end SparkInterval.PTX
