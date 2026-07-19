import SparkInterval.PTX.Generator

/-!
# Exact structural specification of generated PTX

`buildModule_opcodeTrace` fixes every executable opcode, but deliberately
forgets operands and labels.  This file defines a second, proof-facing
compiler whose state contains only allocation counters and the typed
instruction array.  It does not call the production compiler.  The main
theorem proves that the production `buildModule` is exactly the module built
by this structural specification, including register numbers, operands,
immediates, labels, branch targets, and output stores.

This is a source-compiler theorem.  It does not claim that PTX text parsing,
`ptxas`, SASS execution, the CUDA driver, or GPU hardware preserves this AST.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

namespace StructuralCompilerSpec

/-- Minimal state for the independent structural compiler specification. -/
structure State where
  nextPred : Nat := 0
  nextByte : Nat := 0
  nextU32 : Nat := 0
  nextU64 : Nat := 0
  nextF64 : Nat := 0
  body : Array Instruction := #[]
  deriving Inhabited

def State.initial : State := {}

def State.emit (state : State) (instruction : Instruction) : State :=
  { state with body := state.body.push instruction }

def State.freshPred (state : State) : Reg .pred × State :=
  (⟨state.nextPred⟩, { state with nextPred := state.nextPred + 1 })

def State.freshByte (state : State) : Reg .byte × State :=
  (⟨state.nextByte⟩, { state with nextByte := state.nextByte + 1 })

def State.freshU32 (state : State) : Reg .u32 × State :=
  (⟨state.nextU32⟩, { state with nextU32 := state.nextU32 + 1 })

def State.freshU64 (state : State) : Reg .u64 × State :=
  (⟨state.nextU64⟩, { state with nextU64 := state.nextU64 + 1 })

def State.freshF64 (state : State) : Reg .f64 × State :=
  (⟨state.nextF64⟩, { state with nextF64 := state.nextF64 + 1 })

def State.freshInterval (state : State) : IntervalRegisters × State :=
  let (lo, state) := state.freshF64
  let (hi, state) := state.freshF64
  ({ lo, hi }, state)

def emitFiniteGuard (value : IntervalRegisters) (state : State) : State :=
  let (loExponent, state) := state.freshU64
  let (loNonfinite, state) := state.freshPred
  let state := state.emit (.exponentBits loExponent value.lo)
  let state := state.emit (.setpEqExponentMask loNonfinite loExponent)
  let state := state.emit (.branchIf loNonfinite wholeLabel)
  let (hiExponent, state) := state.freshU64
  let (hiNonfinite, state) := state.freshPred
  let state := state.emit (.exponentBits hiExponent value.hi)
  let state := state.emit (.setpEqExponentMask hiNonfinite hiExponent)
  state.emit (.branchIf hiNonfinite wholeLabel)

/-- Structural add specification, spelling out all operands independently of
`addArithmeticFragment`. -/
def compileAdd (left right : IntervalRegisters) (state : State) :
    IntervalRegisters × State :=
  let state := emitFiniteGuard left state
  let state := emitFiniteGuard right state
  let (result, state) := state.freshInterval
  let instructions : Array Instruction :=
    #[.binaryF64 .add .down result.lo left.lo right.lo,
      .binaryF64 .add .up result.hi left.hi right.hi]
  let state := instructions.foldl (fun state instruction => state.emit instruction) state
  (result, state)

/-- Structural subtraction specification, including the crossed bounds. -/
def compileSub (left right : IntervalRegisters) (state : State) :
    IntervalRegisters × State :=
  let state := emitFiniteGuard left state
  let state := emitFiniteGuard right state
  let (result, state) := state.freshInterval
  let instructions : Array Instruction :=
    #[.binaryF64 .sub .down result.lo left.lo right.hi,
      .binaryF64 .sub .up result.hi left.hi right.lo]
  let state := instructions.foldl (fun state instruction => state.emit instruction) state
  (result, state)

/-- Structural multiplication specification, spelling out all eight rounded
corner products and the exact min/max reduction tree. -/
structure MulAllocation where
  temporaries : MulArithmeticTemporaries
  result : IntervalRegisters
  state : State

def allocateMulRegisters (state : State) : MulAllocation :=
  let (down0, state) := state.freshF64
  let (down1, state) := state.freshF64
  let (down2, state) := state.freshF64
  let (down3, state) := state.freshF64
  let (up0, state) := state.freshF64
  let (up1, state) := state.freshF64
  let (up2, state) := state.freshF64
  let (up3, state) := state.freshF64
  let (down01, state) := state.freshF64
  let (down23, state) := state.freshF64
  let (up01, state) := state.freshF64
  let (up23, state) := state.freshF64
  let (result, state) := state.freshInterval
  {
    temporaries := {
      down0, down1, down2, down3, up0, up1, up2, up3,
      down01, down23, up01, up23
    }
    result
    state
  }

def mulInstructions (result left right : IntervalRegisters)
    (tmp : MulArithmeticTemporaries) : Array Instruction :=
  #[.binaryF64 .mul .down tmp.down0 left.lo right.lo,
    .binaryF64 .mul .down tmp.down1 left.lo right.hi,
    .binaryF64 .mul .down tmp.down2 left.hi right.lo,
    .binaryF64 .mul .down tmp.down3 left.hi right.hi,
    .binaryF64 .mul .up tmp.up0 left.lo right.lo,
    .binaryF64 .mul .up tmp.up1 left.lo right.hi,
    .binaryF64 .mul .up tmp.up2 left.hi right.lo,
    .binaryF64 .mul .up tmp.up3 left.hi right.hi,
    .minimumF64 tmp.down01 tmp.down0 tmp.down1,
    .minimumF64 tmp.down23 tmp.down2 tmp.down3,
    .minimumF64 result.lo tmp.down01 tmp.down23,
    .maximumF64 tmp.up01 tmp.up0 tmp.up1,
    .maximumF64 tmp.up23 tmp.up2 tmp.up3,
    .maximumF64 result.hi tmp.up01 tmp.up23]

def compileMul (left right : IntervalRegisters) (state : State) :
    IntervalRegisters × State :=
  let state := emitFiniteGuard left state
  let state := emitFiniteGuard right state
  let allocation := allocateMulRegisters state
  let tmp := allocation.temporaries
  let result := allocation.result
  let instructions := mulInstructions result left right tmp
  let state := instructions.foldl (fun state instruction => state.emit instruction)
    allocation.state
  (result, state)

def compileConst (value : IntervalBits) (state : State) :
    IntervalRegisters × State :=
  let (result, state) := state.freshInterval
  let state := state.emit (.movF64Bits result.lo value.lo.value)
  let state := state.emit (.movF64Bits result.hi value.hi.value)
  (result, state)

def compilePowLoop (base : IntervalRegisters) :
    Nat → IntervalRegisters → State → IntervalRegisters × State
  | 0, result, state => (result, state)
  | count + 1, result, state =>
      let (result, state) := compileMul result base state
      compilePowLoop base count result state

/-- Independent recursive structural specification of expression lowering. -/
def compileExpr (rowBase : Reg .u64) : PolynomialExpr → State →
    IntervalRegisters × State
  | .const value, state => compileConst value state
  | .var index, state =>
      let (result, state) := state.freshInterval
      let state := state.emit (.loadGlobalF64 result.lo rowBase (index * 16))
      let state := state.emit (.loadGlobalF64 result.hi rowBase (index * 16 + 8))
      (result, state)
  | .neg argument, state =>
      let (argument, state) := compileExpr rowBase argument state
      let (result, state) := state.freshInterval
      let state := state.emit (.xorF64Sign result.lo argument.hi)
      let state := state.emit (.xorF64Sign result.hi argument.lo)
      (result, state)
  | .add left right, state =>
      let (left, state) := compileExpr rowBase left state
      let (right, state) := compileExpr rowBase right state
      compileAdd left right state
  | .sub left right, state =>
      let (left, state) := compileExpr rowBase left state
      let (right, state) := compileExpr rowBase right state
      compileSub left right state
  | .mul left right, state =>
      let (left, state) := compileExpr rowBase left state
      let (right, state) := compileExpr rowBase right state
      compileMul left right state
  | .powNat argument exponent, state =>
      let (base, state) := compileExpr rowBase argument state
      let one : IntervalBits := {
        lo := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
        hi := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
      }
      let (initial, state) := compileConst one state
      compilePowLoop base exponent initial state

def emitOutput (outputBase : Reg .u64) (result : IntervalRegisters)
    (status : Fin 256) (state : State) : State :=
  let (statusRegister, state) := state.freshByte
  let (zeroRegister, state) := state.freshByte
  let state := state.emit (.movByte statusRegister status)
  let state := state.emit (.movByte zeroRegister ⟨0, by decide⟩)
  let state := state.emit (.storeGlobalF64 outputBase 0 result.lo)
  let state := state.emit (.storeGlobalF64 outputBase 8 result.hi)
  let state := state.emit (.storeGlobalByte outputBase 16 statusRegister)
  (List.range 7).foldl
    (fun state index => state.emit
      (.storeGlobalByte outputBase (17 + index) zeroRegister)) state

structure PrologueResult where
  rowBase : Reg .u64
  outputBase : Reg .u64
  state : State

/-- Exact structural prologue specification. -/
def emitPrologue (variableCount : Nat) (state : State) : PrologueResult :=
  let (ctaid, state) := state.freshU32
  let (ntid, state) := state.freshU32
  let (tid, state) := state.freshU32
  let (blockBase, state) := state.freshU64
  let (tid64, state) := state.freshU64
  let (rowIndex, state) := state.freshU64
  let (rowCount, state) := state.freshU64
  let (outOfRange, state) := state.freshPred
  let (rowsParameter, state) := state.freshU64
  let (outputsParameter, state) := state.freshU64
  let (rowsGlobal, state) := state.freshU64
  let (outputsGlobal, state) := state.freshU64
  let (rowOffset, state) := state.freshU64
  let (rowBase, state) := state.freshU64
  let (outputOffset, state) := state.freshU64
  let (outputBase, state) := state.freshU64
  let state := state.emit (.movSpecialU32 ctaid .ctaidX)
  let state := state.emit (.movSpecialU32 ntid .ntidX)
  let state := state.emit (.mulWideU32 blockBase ctaid ntid)
  let state := state.emit (.movSpecialU32 tid .tidX)
  let state := state.emit (.cvtU64U32 tid64 tid)
  let state := state.emit (.addU64 rowIndex blockBase tid64)
  let state := state.emit (.loadParamU64 rowCount .rowCount)
  let state := state.emit (.setpGeU64 outOfRange rowIndex rowCount)
  let state := state.emit (.branchIf outOfRange doneLabel)
  let state := state.emit (.loadParamU64 rowsParameter .rows)
  let state := state.emit (.loadParamU64 outputsParameter .outputs)
  let state := state.emit (.cvtaGlobalU64 rowsGlobal rowsParameter)
  let state := state.emit (.cvtaGlobalU64 outputsGlobal outputsParameter)
  let state := state.emit
    (.mulLoU64Immediate rowOffset rowIndex (variableCount * 16))
  let state := state.emit (.addU64 rowBase rowsGlobal rowOffset)
  let state := state.emit (.mulLoU64Immediate outputOffset rowIndex 24)
  let state := state.emit (.addU64 outputBase outputsGlobal outputOffset)
  { rowBase, outputBase, state }

def emitEpilogue (outputBase : Reg .u64) (result : IntervalRegisters)
    (state : State) : State :=
  let state := emitOutput outputBase result ⟨0, by decide⟩ state
  let state := state.emit (.branch doneLabel)
  let state := state.emit (.label wholeLabel)
  let (negativeInfinity, state) := state.freshF64
  let (positiveInfinity, state) := state.freshF64
  let state := state.emit (.movF64Bits negativeInfinity 0xfff0000000000000)
  let state := state.emit (.movF64Bits positiveInfinity 0x7ff0000000000000)
  let whole := { lo := negativeInfinity, hi := positiveInfinity }
  let state := emitOutput outputBase whole ⟨2, by decide⟩ state
  let state := state.emit (.label doneLabel)
  state.emit .ret

def buildState (batch : ReferenceBatch) : State :=
  let prologue := emitPrologue batch.variableCount State.initial
  let (result, state) := compileExpr prologue.rowBase batch.expression prologue.state
  emitEpilogue prologue.outputBase result state

/-- The complete independently specified typed module. -/
def expectedModule (batch : ReferenceBatch) : Module :=
  let state := buildState batch
  {
    entryName := "sparkinterval_generated"
    variableCount := batch.variableCount
    registers := {
      pred := state.nextPred
      byte := state.nextByte
      u32 := state.nextU32
      u64 := state.nextU64
      f64 := state.nextF64
    }
    body := state.body
  }

end StructuralCompilerSpec

namespace StructuralCompilerCorrect

open StructuralCompilerSpec

/-- Forget the production builder's ghost opcode log and its proof. -/
def eraseBuilder (builder : Builder) : StructuralCompilerSpec.State := {
  nextPred := builder.nextPred
  nextByte := builder.nextByte
  nextU32 := builder.nextU32
  nextU64 := builder.nextU64
  nextF64 := builder.nextF64
  body := builder.body
}

private theorem emit_erases (builder : Builder) (instruction : Instruction) :
    eraseBuilder (builder.emit instruction) =
      (eraseBuilder builder).emit instruction := by
  rfl

private theorem freshPred_erases (builder : Builder) :
    (builder.freshPred).1 = ((eraseBuilder builder).freshPred).1 ∧
    eraseBuilder (builder.freshPred).2 = ((eraseBuilder builder).freshPred).2 := by
  exact ⟨rfl, rfl⟩

private theorem freshByte_erases (builder : Builder) :
    (builder.freshByte).1 = ((eraseBuilder builder).freshByte).1 ∧
    eraseBuilder (builder.freshByte).2 = ((eraseBuilder builder).freshByte).2 := by
  exact ⟨rfl, rfl⟩

private theorem freshU32_erases (builder : Builder) :
    (builder.freshU32).1 = ((eraseBuilder builder).freshU32).1 ∧
    eraseBuilder (builder.freshU32).2 = ((eraseBuilder builder).freshU32).2 := by
  exact ⟨rfl, rfl⟩

private theorem freshU64_erases (builder : Builder) :
    (builder.freshU64).1 = ((eraseBuilder builder).freshU64).1 ∧
    eraseBuilder (builder.freshU64).2 = ((eraseBuilder builder).freshU64).2 := by
  exact ⟨rfl, rfl⟩

private theorem freshF64_erases (builder : Builder) :
    (builder.freshF64).1 = ((eraseBuilder builder).freshF64).1 ∧
    eraseBuilder (builder.freshF64).2 = ((eraseBuilder builder).freshF64).2 := by
  exact ⟨rfl, rfl⟩

private theorem freshInterval_erases (builder : Builder) :
    (builder.freshInterval).1 = ((eraseBuilder builder).freshInterval).1 ∧
    eraseBuilder (builder.freshInterval).2 =
      ((eraseBuilder builder).freshInterval).2 := by
  exact ⟨rfl, rfl⟩

private theorem emitFiniteGuard_erases
    (value : IntervalRegisters) (builder : Builder) :
    eraseBuilder (SparkInterval.PTX.emitFiniteGuard value builder) =
      StructuralCompilerSpec.emitFiniteGuard value (eraseBuilder builder) := by
  rfl

private def Matches (builder : Builder)
    (state : StructuralCompilerSpec.State) : Prop :=
  eraseBuilder builder = state

private theorem emit_preserves {builder : Builder}
    {state : StructuralCompilerSpec.State} (hmatch : Matches builder state)
    (instruction : Instruction) :
    Matches (builder.emit instruction) (state.emit instruction) := by
  unfold Matches at hmatch ⊢
  rw [emit_erases, hmatch]

private theorem finiteGuard_preserves {builder : Builder}
    {state : StructuralCompilerSpec.State} (hmatch : Matches builder state)
    (value : IntervalRegisters) :
    Matches (SparkInterval.PTX.emitFiniteGuard value builder)
      (StructuralCompilerSpec.emitFiniteGuard value state) := by
  unfold Matches at hmatch ⊢
  rw [emitFiniteGuard_erases, hmatch]

private theorem freshInterval_preserves {builder : Builder}
    {state : StructuralCompilerSpec.State} (hmatch : Matches builder state) :
    builder.freshInterval.1 = state.freshInterval.1 ∧
      Matches builder.freshInterval.2 state.freshInterval.2 := by
  subst state
  exact freshInterval_erases builder

private theorem allocateMulRegisters_preserves {builder : Builder}
    {state : StructuralCompilerSpec.State} (hmatch : Matches builder state) :
    let actual := SparkInterval.PTX.allocateMulRegisters builder
    let expected := StructuralCompilerSpec.allocateMulRegisters state
    actual.temporaries = expected.temporaries ∧
      actual.result = expected.result ∧
      Matches actual.builder expected.state := by
  subst state
  exact ⟨rfl, rfl, rfl⟩

private theorem listFoldEmit_preserves (instructions : List Instruction)
    {builder : Builder} {state : StructuralCompilerSpec.State}
    (hmatch : Matches builder state) :
    Matches
      (instructions.foldl (fun next instruction => next.emit instruction) builder)
      (instructions.foldl (fun next instruction => next.emit instruction) state) := by
  induction instructions generalizing builder state with
  | nil => exact hmatch
  | cons instruction rest induction =>
      exact induction (emit_preserves hmatch instruction)

private theorem arrayFoldEmit_preserves (instructions : Array Instruction)
    {builder : Builder} {state : StructuralCompilerSpec.State}
    (hmatch : Matches builder state) :
    Matches
      (instructions.foldl (fun next instruction => next.emit instruction) builder)
      (instructions.foldl (fun next instruction => next.emit instruction) state) := by
  rw [← Array.foldl_toList, ← Array.foldl_toList]
  exact listFoldEmit_preserves instructions.toList hmatch

private theorem compileAdd_erases (left right : IntervalRegisters)
    (builder : Builder) :
    (SparkInterval.PTX.compileAdd left right builder).1 =
        (StructuralCompilerSpec.compileAdd left right (eraseBuilder builder)).1 ∧
    eraseBuilder (SparkInterval.PTX.compileAdd left right builder).2 =
        (StructuralCompilerSpec.compileAdd left right (eraseBuilder builder)).2 := by
  let actualLeft := SparkInterval.PTX.emitFiniteGuard left builder
  let expectedLeft := StructuralCompilerSpec.emitFiniteGuard left (eraseBuilder builder)
  have hleft : Matches actualLeft expectedLeft :=
    finiteGuard_preserves (by rfl) left
  let actualRight := SparkInterval.PTX.emitFiniteGuard right actualLeft
  let expectedRight := StructuralCompilerSpec.emitFiniteGuard right expectedLeft
  have hright : Matches actualRight expectedRight :=
    finiteGuard_preserves hleft right
  obtain ⟨hresult, hfresh⟩ := freshInterval_preserves hright
  let actualFresh := actualRight.freshInterval
  let expectedFresh := expectedRight.freshInterval
  let instructions := addArithmeticFragment actualFresh.1 left right
  let expectedInstructions : Array Instruction :=
    #[.binaryF64 .add .down expectedFresh.1.lo left.lo right.lo,
      .binaryF64 .add .up expectedFresh.1.hi left.hi right.hi]
  have hinstructions : instructions = expectedInstructions := by
    unfold instructions expectedInstructions addArithmeticFragment
    rw [hresult]
  have hfold := arrayFoldEmit_preserves instructions hfresh
  constructor
  · calc
      (SparkInterval.PTX.compileAdd left right builder).1 = actualFresh.1 := rfl
      _ = expectedFresh.1 := hresult
      _ = (StructuralCompilerSpec.compileAdd left right
          (eraseBuilder builder)).1 := rfl
  · calc
      eraseBuilder (SparkInterval.PTX.compileAdd left right builder).2 =
          eraseBuilder (instructions.foldl
            (fun next instruction => next.emit instruction) actualFresh.2) := by rfl
      _ = (instructions.foldl
            (fun next instruction => next.emit instruction) expectedFresh.2) := hfold
      _ = (expectedInstructions.foldl
            (fun next instruction => next.emit instruction) expectedFresh.2) := by
              rw [hinstructions]
      _ = (StructuralCompilerSpec.compileAdd left right
          (eraseBuilder builder)).2 := by rfl

private theorem compileSub_erases (left right : IntervalRegisters)
    (builder : Builder) :
    (SparkInterval.PTX.compileSub left right builder).1 =
        (StructuralCompilerSpec.compileSub left right (eraseBuilder builder)).1 ∧
    eraseBuilder (SparkInterval.PTX.compileSub left right builder).2 =
        (StructuralCompilerSpec.compileSub left right (eraseBuilder builder)).2 := by
  let actualLeft := SparkInterval.PTX.emitFiniteGuard left builder
  let expectedLeft := StructuralCompilerSpec.emitFiniteGuard left (eraseBuilder builder)
  have hleft : Matches actualLeft expectedLeft :=
    finiteGuard_preserves (by rfl) left
  let actualRight := SparkInterval.PTX.emitFiniteGuard right actualLeft
  let expectedRight := StructuralCompilerSpec.emitFiniteGuard right expectedLeft
  have hright : Matches actualRight expectedRight :=
    finiteGuard_preserves hleft right
  obtain ⟨hresult, hfresh⟩ := freshInterval_preserves hright
  let actualFresh := actualRight.freshInterval
  let expectedFresh := expectedRight.freshInterval
  let instructions := subArithmeticFragment actualFresh.1 left right
  let expectedInstructions : Array Instruction :=
    #[.binaryF64 .sub .down expectedFresh.1.lo left.lo right.hi,
      .binaryF64 .sub .up expectedFresh.1.hi left.hi right.lo]
  have hinstructions : instructions = expectedInstructions := by
    unfold instructions expectedInstructions subArithmeticFragment
    rw [hresult]
  have hfold := arrayFoldEmit_preserves instructions hfresh
  constructor
  · calc
      (SparkInterval.PTX.compileSub left right builder).1 = actualFresh.1 := rfl
      _ = expectedFresh.1 := hresult
      _ = (StructuralCompilerSpec.compileSub left right
          (eraseBuilder builder)).1 := rfl
  · calc
      eraseBuilder (SparkInterval.PTX.compileSub left right builder).2 =
          eraseBuilder (instructions.foldl
            (fun next instruction => next.emit instruction) actualFresh.2) := by rfl
      _ = (instructions.foldl
            (fun next instruction => next.emit instruction) expectedFresh.2) := hfold
      _ = (expectedInstructions.foldl
            (fun next instruction => next.emit instruction) expectedFresh.2) := by
              rw [hinstructions]
      _ = (StructuralCompilerSpec.compileSub left right
          (eraseBuilder builder)).2 := by rfl

private theorem compileMul_erases (left right : IntervalRegisters)
    (builder : Builder) :
    (SparkInterval.PTX.compileMul left right builder).1 =
        (StructuralCompilerSpec.compileMul left right (eraseBuilder builder)).1 ∧
    eraseBuilder (SparkInterval.PTX.compileMul left right builder).2 =
        (StructuralCompilerSpec.compileMul left right (eraseBuilder builder)).2 := by
  let actualLeft := SparkInterval.PTX.emitFiniteGuard left builder
  let expectedLeft := StructuralCompilerSpec.emitFiniteGuard left (eraseBuilder builder)
  have hleft : Matches actualLeft expectedLeft :=
    finiteGuard_preserves (by rfl) left
  let actualRight := SparkInterval.PTX.emitFiniteGuard right actualLeft
  let expectedRight := StructuralCompilerSpec.emitFiniteGuard right expectedLeft
  have hright : Matches actualRight expectedRight :=
    finiteGuard_preserves hleft right
  obtain ⟨htemporaries, hresult, hallocation⟩ :=
    allocateMulRegisters_preserves hright
  let actualAllocation := SparkInterval.PTX.allocateMulRegisters actualRight
  let expectedAllocation := StructuralCompilerSpec.allocateMulRegisters expectedRight
  let instructions := mulArithmeticFragment actualAllocation.result left right
    actualAllocation.temporaries
  let expectedInstructions := StructuralCompilerSpec.mulInstructions
    expectedAllocation.result left right expectedAllocation.temporaries
  have hinstructions : instructions = expectedInstructions := by
    unfold instructions expectedInstructions mulArithmeticFragment
      StructuralCompilerSpec.mulInstructions
    rw [htemporaries, hresult]
  have hfold := arrayFoldEmit_preserves instructions hallocation
  constructor
  · calc
      (SparkInterval.PTX.compileMul left right builder).1 =
          actualAllocation.result := rfl
      _ = expectedAllocation.result := hresult
      _ = (StructuralCompilerSpec.compileMul left right
          (eraseBuilder builder)).1 := rfl
  · calc
      eraseBuilder (SparkInterval.PTX.compileMul left right builder).2 =
          eraseBuilder (instructions.foldl
            (fun next instruction => next.emit instruction)
            actualAllocation.builder) := by rfl
      _ = (instructions.foldl
            (fun next instruction => next.emit instruction)
            expectedAllocation.state) := hfold
      _ = (expectedInstructions.foldl
            (fun next instruction => next.emit instruction)
            expectedAllocation.state) := by rw [hinstructions]
      _ = (StructuralCompilerSpec.compileMul left right
          (eraseBuilder builder)).2 := by rfl

private theorem compileConst_erases (value : IntervalBits) (builder : Builder) :
    (SparkInterval.PTX.compileConst value builder).1 =
        (StructuralCompilerSpec.compileConst value (eraseBuilder builder)).1 ∧
    eraseBuilder (SparkInterval.PTX.compileConst value builder).2 =
        (StructuralCompilerSpec.compileConst value (eraseBuilder builder)).2 := by
  exact ⟨rfl, rfl⟩

private theorem compileAdd_preserves (left right : IntervalRegisters)
    {builder : Builder} {state : StructuralCompilerSpec.State}
    (hmatch : Matches builder state) :
    (SparkInterval.PTX.compileAdd left right builder).1 =
        (StructuralCompilerSpec.compileAdd left right state).1 ∧
      Matches (SparkInterval.PTX.compileAdd left right builder).2
        (StructuralCompilerSpec.compileAdd left right state).2 := by
  unfold Matches at hmatch ⊢
  subst state
  exact compileAdd_erases left right builder

private theorem compileSub_preserves (left right : IntervalRegisters)
    {builder : Builder} {state : StructuralCompilerSpec.State}
    (hmatch : Matches builder state) :
    (SparkInterval.PTX.compileSub left right builder).1 =
        (StructuralCompilerSpec.compileSub left right state).1 ∧
      Matches (SparkInterval.PTX.compileSub left right builder).2
        (StructuralCompilerSpec.compileSub left right state).2 := by
  unfold Matches at hmatch ⊢
  subst state
  exact compileSub_erases left right builder

private theorem compileMul_preserves (left right : IntervalRegisters)
    {builder : Builder} {state : StructuralCompilerSpec.State}
    (hmatch : Matches builder state) :
    (SparkInterval.PTX.compileMul left right builder).1 =
        (StructuralCompilerSpec.compileMul left right state).1 ∧
      Matches (SparkInterval.PTX.compileMul left right builder).2
        (StructuralCompilerSpec.compileMul left right state).2 := by
  unfold Matches at hmatch ⊢
  subst state
  exact compileMul_erases left right builder

private theorem compileConst_preserves (value : IntervalBits)
    {builder : Builder} {state : StructuralCompilerSpec.State}
    (hmatch : Matches builder state) :
    (SparkInterval.PTX.compileConst value builder).1 =
        (StructuralCompilerSpec.compileConst value state).1 ∧
      Matches (SparkInterval.PTX.compileConst value builder).2
        (StructuralCompilerSpec.compileConst value state).2 := by
  unfold Matches at hmatch ⊢
  subst state
  exact compileConst_erases value builder

private theorem compileAdd_preserves_of_eq
    {actualLeft expectedLeft actualRight expectedRight : IntervalRegisters}
    (hleft : actualLeft = expectedLeft) (hright : actualRight = expectedRight)
    {builder : Builder} {state : StructuralCompilerSpec.State}
    (hmatch : Matches builder state) :
    (SparkInterval.PTX.compileAdd actualLeft actualRight builder).1 =
        (StructuralCompilerSpec.compileAdd expectedLeft expectedRight state).1 ∧
      Matches (SparkInterval.PTX.compileAdd actualLeft actualRight builder).2
        (StructuralCompilerSpec.compileAdd expectedLeft expectedRight state).2 := by
  subst expectedLeft
  subst expectedRight
  exact compileAdd_preserves actualLeft actualRight hmatch

private theorem compileSub_preserves_of_eq
    {actualLeft expectedLeft actualRight expectedRight : IntervalRegisters}
    (hleft : actualLeft = expectedLeft) (hright : actualRight = expectedRight)
    {builder : Builder} {state : StructuralCompilerSpec.State}
    (hmatch : Matches builder state) :
    (SparkInterval.PTX.compileSub actualLeft actualRight builder).1 =
        (StructuralCompilerSpec.compileSub expectedLeft expectedRight state).1 ∧
      Matches (SparkInterval.PTX.compileSub actualLeft actualRight builder).2
        (StructuralCompilerSpec.compileSub expectedLeft expectedRight state).2 := by
  subst expectedLeft
  subst expectedRight
  exact compileSub_preserves actualLeft actualRight hmatch

private theorem compileMul_preserves_of_eq
    {actualLeft expectedLeft actualRight expectedRight : IntervalRegisters}
    (hleft : actualLeft = expectedLeft) (hright : actualRight = expectedRight)
    {builder : Builder} {state : StructuralCompilerSpec.State}
    (hmatch : Matches builder state) :
    (SparkInterval.PTX.compileMul actualLeft actualRight builder).1 =
        (StructuralCompilerSpec.compileMul expectedLeft expectedRight state).1 ∧
      Matches (SparkInterval.PTX.compileMul actualLeft actualRight builder).2
        (StructuralCompilerSpec.compileMul expectedLeft expectedRight state).2 := by
  subst expectedLeft
  subst expectedRight
  exact compileMul_preserves actualLeft actualRight hmatch

private theorem compilePowLoop_erases (base : IntervalRegisters) (count : Nat)
    (current : IntervalRegisters) (builder : Builder) :
    (SparkInterval.PTX.compilePowLoop base count current builder).1 =
        (StructuralCompilerSpec.compilePowLoop base count current
          (eraseBuilder builder)).1 ∧
    eraseBuilder (SparkInterval.PTX.compilePowLoop base count current builder).2 =
        (StructuralCompilerSpec.compilePowLoop base count current
          (eraseBuilder builder)).2 := by
  induction count generalizing current builder with
  | zero => exact ⟨rfl, rfl⟩
  | succ count induction =>
      simp only [SparkInterval.PTX.compilePowLoop,
        StructuralCompilerSpec.compilePowLoop]
      obtain ⟨hresult, _⟩ := compileMul_erases current base builder
      simp only [hresult]
      exact induction _ _

private theorem compilePowLoop_preserves (base : IntervalRegisters) (count : Nat)
    (current : IntervalRegisters) {builder : Builder}
    {state : StructuralCompilerSpec.State} (hmatch : Matches builder state) :
    (SparkInterval.PTX.compilePowLoop base count current builder).1 =
        (StructuralCompilerSpec.compilePowLoop base count current state).1 ∧
      Matches (SparkInterval.PTX.compilePowLoop base count current builder).2
        (StructuralCompilerSpec.compilePowLoop base count current state).2 := by
  induction count generalizing current builder state with
  | zero => exact ⟨rfl, hmatch⟩
  | succ count induction =>
      obtain ⟨hresult, hstate⟩ := compileMul_preserves current base hmatch
      simpa only [SparkInterval.PTX.compilePowLoop,
        StructuralCompilerSpec.compilePowLoop, hresult] using
        induction (StructuralCompilerSpec.compileMul current base state).1 hstate

private theorem compilePowLoop_preserves_of_eq
    {actualBase expectedBase actualCurrent expectedCurrent : IntervalRegisters}
    (hbase : actualBase = expectedBase) (hcurrent : actualCurrent = expectedCurrent)
    (count : Nat) {builder : Builder} {state : StructuralCompilerSpec.State}
    (hmatch : Matches builder state) :
    (SparkInterval.PTX.compilePowLoop actualBase count actualCurrent builder).1 =
        (StructuralCompilerSpec.compilePowLoop expectedBase count expectedCurrent state).1 ∧
      Matches
        (SparkInterval.PTX.compilePowLoop actualBase count actualCurrent builder).2
        (StructuralCompilerSpec.compilePowLoop expectedBase count expectedCurrent state).2 := by
  subst expectedBase
  subst expectedCurrent
  exact compilePowLoop_preserves actualBase count actualCurrent hmatch

private theorem compileExpr_preserves (rowBase : Reg .u64)
    (expression : PolynomialExpr) {builder : Builder}
    {state : StructuralCompilerSpec.State} (hmatch : Matches builder state) :
    (SparkInterval.PTX.compileExpr rowBase expression builder).1 =
        (StructuralCompilerSpec.compileExpr rowBase expression
          state).1 ∧
    Matches (SparkInterval.PTX.compileExpr rowBase expression builder).2
        (StructuralCompilerSpec.compileExpr rowBase expression
          state).2 := by
    induction expression generalizing builder state with
    | const value => exact compileConst_preserves value hmatch
    | var index =>
        obtain ⟨hresult, hstate⟩ := freshInterval_preserves hmatch
        let actualFresh := builder.freshInterval
        let expectedFresh := state.freshInterval
        change actualFresh.1 = expectedFresh.1 at hresult
        change Matches actualFresh.2 expectedFresh.2 at hstate
        have hloadLo := emit_preserves hstate
          (.loadGlobalF64 actualFresh.1.lo rowBase (index * 16))
        have hloadLo' : Matches
            (actualFresh.2.emit
              (.loadGlobalF64 actualFresh.1.lo rowBase (index * 16)))
            (expectedFresh.2.emit
              (.loadGlobalF64 expectedFresh.1.lo rowBase (index * 16))) := by
          simpa only [hresult] using hloadLo
        have hloadHi := emit_preserves hloadLo'
          (.loadGlobalF64 actualFresh.1.hi rowBase (index * 16 + 8))
        have hloadHi' : Matches
            ((actualFresh.2.emit
              (.loadGlobalF64 actualFresh.1.lo rowBase (index * 16))).emit
              (.loadGlobalF64 actualFresh.1.hi rowBase (index * 16 + 8)))
            ((expectedFresh.2.emit
              (.loadGlobalF64 expectedFresh.1.lo rowBase (index * 16))).emit
              (.loadGlobalF64 expectedFresh.1.hi rowBase (index * 16 + 8))) := by
          simpa only [hresult] using hloadHi
        exact ⟨hresult, hloadHi'⟩
    | neg argument induction =>
        obtain ⟨hargument, hargumentState⟩ :=
          induction (builder := builder) (state := state) hmatch
        obtain ⟨hresult, hfresh⟩ := freshInterval_preserves hargumentState
        let actualArgument := SparkInterval.PTX.compileExpr rowBase argument builder
        let expectedArgument := StructuralCompilerSpec.compileExpr rowBase argument state
        let actualFresh := actualArgument.2.freshInterval
        let expectedFresh := expectedArgument.2.freshInterval
        change actualArgument.1 = expectedArgument.1 at hargument
        change actualFresh.1 = expectedFresh.1 at hresult
        change Matches actualFresh.2 expectedFresh.2 at hfresh
        have hlo := emit_preserves hfresh
          (.xorF64Sign actualFresh.1.lo actualArgument.1.hi)
        have hlo' : Matches
            (actualFresh.2.emit (.xorF64Sign actualFresh.1.lo actualArgument.1.hi))
            (expectedFresh.2.emit
              (.xorF64Sign expectedFresh.1.lo expectedArgument.1.hi)) := by
          simpa only [hargument, hresult] using hlo
        have hhi := emit_preserves hlo'
          (.xorF64Sign actualFresh.1.hi actualArgument.1.lo)
        have hhi' : Matches
            ((actualFresh.2.emit
              (.xorF64Sign actualFresh.1.lo actualArgument.1.hi)).emit
              (.xorF64Sign actualFresh.1.hi actualArgument.1.lo))
            ((expectedFresh.2.emit
              (.xorF64Sign expectedFresh.1.lo expectedArgument.1.hi)).emit
              (.xorF64Sign expectedFresh.1.hi expectedArgument.1.lo)) := by
          simpa only [hargument, hresult] using hhi
        exact ⟨hresult, hhi'⟩
    | add left right leftInduction rightInduction =>
        obtain ⟨hleft, hleftState⟩ :=
          leftInduction (builder := builder) (state := state) hmatch
        obtain ⟨hright, hrightState⟩ := rightInduction
          (builder := (SparkInterval.PTX.compileExpr rowBase left builder).2)
          (state := (StructuralCompilerSpec.compileExpr rowBase left state).2)
          hleftState
        simpa only [SparkInterval.PTX.compileExpr,
          StructuralCompilerSpec.compileExpr] using
          compileAdd_preserves_of_eq hleft hright hrightState
    | sub left right leftInduction rightInduction =>
        obtain ⟨hleft, hleftState⟩ :=
          leftInduction (builder := builder) (state := state) hmatch
        obtain ⟨hright, hrightState⟩ := rightInduction
          (builder := (SparkInterval.PTX.compileExpr rowBase left builder).2)
          (state := (StructuralCompilerSpec.compileExpr rowBase left state).2)
          hleftState
        simpa only [SparkInterval.PTX.compileExpr,
          StructuralCompilerSpec.compileExpr] using
          compileSub_preserves_of_eq hleft hright hrightState
    | mul left right leftInduction rightInduction =>
        obtain ⟨hleft, hleftState⟩ :=
          leftInduction (builder := builder) (state := state) hmatch
        obtain ⟨hright, hrightState⟩ := rightInduction
          (builder := (SparkInterval.PTX.compileExpr rowBase left builder).2)
          (state := (StructuralCompilerSpec.compileExpr rowBase left state).2)
          hleftState
        simpa only [SparkInterval.PTX.compileExpr,
          StructuralCompilerSpec.compileExpr] using
          compileMul_preserves_of_eq hleft hright hrightState
    | powNat argument exponent induction =>
        obtain ⟨hbase, hbaseState⟩ :=
          induction (builder := builder) (state := state) hmatch
        let one : IntervalBits := {
          lo := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
          hi := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
        }
        obtain ⟨hinitialResult, hinitialState⟩ :=
          compileConst_preserves one hbaseState
        simpa only [SparkInterval.PTX.compileExpr,
          StructuralCompilerSpec.compileExpr, one] using
          compilePowLoop_preserves_of_eq hbase hinitialResult exponent hinitialState

private theorem compileExpr_erases (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    (SparkInterval.PTX.compileExpr rowBase expression builder).1 =
        (StructuralCompilerSpec.compileExpr rowBase expression
          (eraseBuilder builder)).1 ∧
    eraseBuilder (SparkInterval.PTX.compileExpr rowBase expression builder).2 =
        (StructuralCompilerSpec.compileExpr rowBase expression
          (eraseBuilder builder)).2 := by
  exact compileExpr_preserves rowBase expression (by rfl)

private theorem emitOutput_erases (outputBase : Reg .u64)
    (result : IntervalRegisters) (status : Fin 256) (builder : Builder) :
    eraseBuilder (SparkInterval.PTX.emitOutput outputBase result status builder) =
      StructuralCompilerSpec.emitOutput outputBase result status
        (eraseBuilder builder) := by
  rfl

private theorem emitPrologue_erases (variableCount : Nat) (builder : Builder) :
    let actual := SparkInterval.PTX.emitPrologue variableCount builder
    let expected := StructuralCompilerSpec.emitPrologue variableCount
      (eraseBuilder builder)
    actual.rowBase = expected.rowBase ∧
      actual.outputBase = expected.outputBase ∧
      eraseBuilder actual.builder = expected.state := by
  exact ⟨rfl, rfl, rfl⟩

private theorem emitPrologue_preserves (variableCount : Nat)
    {builder : Builder} {state : StructuralCompilerSpec.State}
    (hmatch : Matches builder state) :
    let actual := SparkInterval.PTX.emitPrologue variableCount builder
    let expected := StructuralCompilerSpec.emitPrologue variableCount state
    actual.rowBase = expected.rowBase ∧
      actual.outputBase = expected.outputBase ∧
      Matches actual.builder expected.state := by
  unfold Matches at hmatch ⊢
  subst state
  exact emitPrologue_erases variableCount builder

private theorem emitEpilogue_erases (outputBase : Reg .u64)
    (result : IntervalRegisters) (builder : Builder) :
    eraseBuilder (SparkInterval.PTX.emitEpilogue outputBase result builder) =
      StructuralCompilerSpec.emitEpilogue outputBase result
        (eraseBuilder builder) := by
  rfl

private theorem emitEpilogue_preserves_of_eq
    {actualOutput expectedOutput : Reg .u64}
    {actualResult expectedResult : IntervalRegisters}
    (houtput : actualOutput = expectedOutput)
    (hresult : actualResult = expectedResult)
    {builder : Builder} {state : StructuralCompilerSpec.State}
    (hmatch : Matches builder state) :
    Matches
      (SparkInterval.PTX.emitEpilogue actualOutput actualResult builder)
      (StructuralCompilerSpec.emitEpilogue expectedOutput expectedResult state) := by
  subst expectedOutput
  subst expectedResult
  unfold Matches at hmatch ⊢
  subst state
  exact emitEpilogue_erases actualOutput actualResult builder

private theorem buildBuilder_erases (batch : ReferenceBatch) :
    eraseBuilder (buildBuilder batch) =
      StructuralCompilerSpec.buildState batch := by
  let actualPrologue := SparkInterval.PTX.emitPrologue
    batch.variableCount Builder.initial
  let expectedPrologue := StructuralCompilerSpec.emitPrologue
    batch.variableCount StructuralCompilerSpec.State.initial
  have hinitial : Matches Builder.initial StructuralCompilerSpec.State.initial := by
    rfl
  obtain ⟨hrow, houtput, hprologue⟩ :=
    emitPrologue_preserves batch.variableCount hinitial
  let actualExpression := SparkInterval.PTX.compileExpr actualPrologue.rowBase
    batch.expression actualPrologue.builder
  let expectedExpression := StructuralCompilerSpec.compileExpr expectedPrologue.rowBase
    batch.expression expectedPrologue.state
  have hexpression := compileExpr_preserves actualPrologue.rowBase
    batch.expression hprologue
  have hrowExpression :
      (SparkInterval.PTX.compileExpr actualPrologue.rowBase batch.expression
        actualPrologue.builder).1 = expectedExpression.1 := by
    rw [hrow]
    exact hexpression.1
  have hstateExpression : Matches
      (SparkInterval.PTX.compileExpr actualPrologue.rowBase batch.expression
        actualPrologue.builder).2 expectedExpression.2 := by
    rw [hrow]
    exact hexpression.2
  have hepilogue := emitEpilogue_preserves_of_eq houtput hrowExpression
    hstateExpression
  unfold Matches at hepilogue
  simpa only [buildBuilder, StructuralCompilerSpec.buildState,
    actualPrologue, expectedPrologue, actualExpression, expectedExpression]
    using hepilogue

/-- **Exact whole-source compiler theorem.**  The production module equals the
independently constructed structural module.  Equality covers module metadata,
all five register counts, the complete instruction array, every typed register
operand, every immediate and memory offset, and both labels/branch targets. -/
theorem buildModule_eq_expectedModule (batch : ReferenceBatch) :
    buildModule batch = StructuralCompilerSpec.expectedModule batch := by
  generalize hactual : buildBuilder batch = actual
  generalize hexpected : StructuralCompilerSpec.buildState batch = expected
  have hstate := buildBuilder_erases batch
  rw [hactual, hexpected] at hstate
  unfold buildModule StructuralCompilerSpec.expectedModule
  rw [hactual, hexpected]
  rw [← hstate]
  rfl

end StructuralCompilerCorrect

end SparkInterval.PTX
