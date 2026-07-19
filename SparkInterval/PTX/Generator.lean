import SparkInterval.PTX.Emitter
import SparkInterval.PTX.ReferenceBatch

/-!
# Phase 5 polynomial interval kernel generator

The compiler specializes one PTX kernel to one validated expression.  Every
intermediate interval is represented by two binary64 registers.  Addition,
subtraction, and all four multiplication corners use explicit `rm`/`rp`
instructions.  A nonfinite operand to a later arithmetic node takes the shared
whole-interval path, matching the executable reference's conservative policy.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

structure IntervalRegisters where
  lo : Reg .f64
  hi : Reg .f64
  deriving Repr, Inhabited

/-- The two arithmetic instructions emitted for interval addition.  Keeping
this fragment public lets the Phase 6 semantics refer to the exact typed
instructions used by the generator, rather than to a second hand-written
opcode list.  Finite guards are emitted separately by `compileAdd`. -/
def addArithmeticFragment (result left right : IntervalRegisters) :
    Array Instruction :=
  #[.binaryF64 .add .down result.lo left.lo right.lo,
    .binaryF64 .add .up result.hi left.hi right.hi]

/-- The two arithmetic instructions emitted for interval subtraction. -/
def subArithmeticFragment (result left right : IntervalRegisters) :
    Array Instruction :=
  #[.binaryF64 .sub .down result.lo left.lo right.hi,
    .binaryF64 .sub .up result.hi left.hi right.lo]

/-- Fresh registers used to collect and reduce the four lower and four upper
corner products of an interval multiplication. -/
structure MulArithmeticTemporaries where
  down0 : Reg .f64
  down1 : Reg .f64
  down2 : Reg .f64
  down3 : Reg .f64
  up0 : Reg .f64
  up1 : Reg .f64
  up2 : Reg .f64
  up3 : Reg .f64
  down01 : Reg .f64
  down23 : Reg .f64
  up01 : Reg .f64
  up23 : Reg .f64
  deriving Repr, Inhabited

/-- The exact directed-rounding/minimum/maximum instruction fragment emitted
for interval multiplication.  Finite guards are outside this fragment. -/
def mulArithmeticFragment (result left right : IntervalRegisters)
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

private structure Builder where
  nextPred : Nat := 0
  nextByte : Nat := 0
  nextU32 : Nat := 0
  nextU64 : Nat := 0
  nextF64 : Nat := 0
  body : Array Instruction := #[]
  deriving Inhabited

private def Builder.emit (builder : Builder) (instruction : Instruction) : Builder :=
  { builder with body := builder.body.push instruction }

private def Builder.freshPred (builder : Builder) : Reg .pred × Builder :=
  (⟨builder.nextPred⟩, { builder with nextPred := builder.nextPred + 1 })

private def Builder.freshByte (builder : Builder) : Reg .byte × Builder :=
  (⟨builder.nextByte⟩, { builder with nextByte := builder.nextByte + 1 })

private def Builder.freshU32 (builder : Builder) : Reg .u32 × Builder :=
  (⟨builder.nextU32⟩, { builder with nextU32 := builder.nextU32 + 1 })

private def Builder.freshU64 (builder : Builder) : Reg .u64 × Builder :=
  (⟨builder.nextU64⟩, { builder with nextU64 := builder.nextU64 + 1 })

private def Builder.freshF64 (builder : Builder) : Reg .f64 × Builder :=
  (⟨builder.nextF64⟩, { builder with nextF64 := builder.nextF64 + 1 })

private def Builder.freshInterval (builder : Builder) : IntervalRegisters × Builder :=
  let (lo, builder) := builder.freshF64
  let (hi, builder) := builder.freshF64
  ({ lo, hi }, builder)

private def wholeLabel : Label := ⟨0⟩
private def doneLabel : Label := ⟨1⟩

private def emitFiniteGuard (value : IntervalRegisters) (builder : Builder) : Builder :=
  let (loExponent, builder) := builder.freshU64
  let (loNonfinite, builder) := builder.freshPred
  let builder := builder.emit (.exponentBits loExponent value.lo)
  let builder := builder.emit (.setpEqExponentMask loNonfinite loExponent)
  let builder := builder.emit (.branchIf loNonfinite wholeLabel)
  let (hiExponent, builder) := builder.freshU64
  let (hiNonfinite, builder) := builder.freshPred
  let builder := builder.emit (.exponentBits hiExponent value.hi)
  let builder := builder.emit (.setpEqExponentMask hiNonfinite hiExponent)
  builder.emit (.branchIf hiNonfinite wholeLabel)

private def compileAdd (left right : IntervalRegisters) (builder : Builder) :
    IntervalRegisters × Builder :=
  let builder := emitFiniteGuard left builder
  let builder := emitFiniteGuard right builder
  let (result, builder) := builder.freshInterval
  let builder := (addArithmeticFragment result left right).foldl
    (fun builder instruction => builder.emit instruction) builder
  (result, builder)

private def compileSub (left right : IntervalRegisters) (builder : Builder) :
    IntervalRegisters × Builder :=
  let builder := emitFiniteGuard left builder
  let builder := emitFiniteGuard right builder
  let (result, builder) := builder.freshInterval
  let builder := (subArithmeticFragment result left right).foldl
    (fun builder instruction => builder.emit instruction) builder
  (result, builder)

private def compileMul (left right : IntervalRegisters) (builder : Builder) :
    IntervalRegisters × Builder :=
  let builder := emitFiniteGuard left builder
  let builder := emitFiniteGuard right builder
  let (down0, builder) := builder.freshF64
  let (down1, builder) := builder.freshF64
  let (down2, builder) := builder.freshF64
  let (down3, builder) := builder.freshF64
  let (up0, builder) := builder.freshF64
  let (up1, builder) := builder.freshF64
  let (up2, builder) := builder.freshF64
  let (up3, builder) := builder.freshF64
  let (down01, builder) := builder.freshF64
  let (down23, builder) := builder.freshF64
  let (up01, builder) := builder.freshF64
  let (up23, builder) := builder.freshF64
  let (result, builder) := builder.freshInterval
  let temporaries : MulArithmeticTemporaries := {
    down0, down1, down2, down3, up0, up1, up2, up3,
    down01, down23, up01, up23
  }
  let builder := (mulArithmeticFragment result left right temporaries).foldl
    (fun builder instruction => builder.emit instruction) builder
  (result, builder)

private def compileConst (value : IntervalBits) (builder : Builder) :
    IntervalRegisters × Builder :=
  let (result, builder) := builder.freshInterval
  let builder := builder.emit (.movF64Bits result.lo value.lo.value)
  let builder := builder.emit (.movF64Bits result.hi value.hi.value)
  (result, builder)

private partial def compileExpr (rowBase : Reg .u64) : PolynomialExpr → Builder →
    IntervalRegisters × Builder
  | .const value, builder => compileConst value builder
  | .var index, builder =>
      let (result, builder) := builder.freshInterval
      let builder := builder.emit (.loadGlobalF64 result.lo rowBase (index * 16))
      let builder := builder.emit (.loadGlobalF64 result.hi rowBase (index * 16 + 8))
      (result, builder)
  | .neg arg, builder =>
      let (arg, builder) := compileExpr rowBase arg builder
      let (result, builder) := builder.freshInterval
      let builder := builder.emit (.xorF64Sign result.lo arg.hi)
      let builder := builder.emit (.xorF64Sign result.hi arg.lo)
      (result, builder)
  | .add left right, builder =>
      let (left, builder) := compileExpr rowBase left builder
      let (right, builder) := compileExpr rowBase right builder
      compileAdd left right builder
  | .sub left right, builder =>
      let (left, builder) := compileExpr rowBase left builder
      let (right, builder) := compileExpr rowBase right builder
      compileSub left right builder
  | .mul left right, builder =>
      let (left, builder) := compileExpr rowBase left builder
      let (right, builder) := compileExpr rowBase right builder
      compileMul left right builder
  | .powNat arg exponent, builder =>
      let (base, builder) := compileExpr rowBase arg builder
      let one : IntervalBits := {
        lo := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
        hi := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
      }
      let (initial, builder) := compileConst one builder
      let rec loop : Nat → IntervalRegisters → Builder → IntervalRegisters × Builder
        | 0, result, builder => (result, builder)
        | count + 1, result, builder =>
            let (result, builder) := compileMul result base builder
            loop count result builder
      loop exponent initial builder

private def emitOutput (outputBase : Reg .u64) (result : IntervalRegisters)
    (status : Fin 256) (builder : Builder) : Builder :=
  let (statusRegister, builder) := builder.freshByte
  let (zeroRegister, builder) := builder.freshByte
  let builder := builder.emit (.movByte statusRegister status)
  let builder := builder.emit (.movByte zeroRegister ⟨0, by decide⟩)
  let builder := builder.emit (.storeGlobalF64 outputBase 0 result.lo)
  let builder := builder.emit (.storeGlobalF64 outputBase 8 result.hi)
  let builder := builder.emit (.storeGlobalByte outputBase 16 statusRegister)
  (List.range 7).foldl
    (fun builder index => builder.emit (.storeGlobalByte outputBase (17 + index) zeroRegister))
    builder

private def buildModule (batch : ReferenceBatch) : Module :=
  let builder : Builder := {}
  let (ctaid, builder) := builder.freshU32
  let (ntid, builder) := builder.freshU32
  let (tid, builder) := builder.freshU32
  let (blockBase, builder) := builder.freshU64
  let (tid64, builder) := builder.freshU64
  let (rowIndex, builder) := builder.freshU64
  let (rowCount, builder) := builder.freshU64
  let (outOfRange, builder) := builder.freshPred
  let (rowsParameter, builder) := builder.freshU64
  let (outputsParameter, builder) := builder.freshU64
  let (rowsGlobal, builder) := builder.freshU64
  let (outputsGlobal, builder) := builder.freshU64
  let (rowOffset, builder) := builder.freshU64
  let (rowBase, builder) := builder.freshU64
  let (outputOffset, builder) := builder.freshU64
  let (outputBase, builder) := builder.freshU64
  let builder := builder.emit (.movSpecialU32 ctaid .ctaidX)
  let builder := builder.emit (.movSpecialU32 ntid .ntidX)
  let builder := builder.emit (.mulWideU32 blockBase ctaid ntid)
  let builder := builder.emit (.movSpecialU32 tid .tidX)
  let builder := builder.emit (.cvtU64U32 tid64 tid)
  let builder := builder.emit (.addU64 rowIndex blockBase tid64)
  let builder := builder.emit (.loadParamU64 rowCount .rowCount)
  let builder := builder.emit (.setpGeU64 outOfRange rowIndex rowCount)
  let builder := builder.emit (.branchIf outOfRange doneLabel)
  let builder := builder.emit (.loadParamU64 rowsParameter .rows)
  let builder := builder.emit (.loadParamU64 outputsParameter .outputs)
  let builder := builder.emit (.cvtaGlobalU64 rowsGlobal rowsParameter)
  let builder := builder.emit (.cvtaGlobalU64 outputsGlobal outputsParameter)
  let builder := builder.emit
    (.mulLoU64Immediate rowOffset rowIndex (batch.variableCount * 16))
  let builder := builder.emit (.addU64 rowBase rowsGlobal rowOffset)
  let builder := builder.emit (.mulLoU64Immediate outputOffset rowIndex 24)
  let builder := builder.emit (.addU64 outputBase outputsGlobal outputOffset)
  let (result, builder) := compileExpr rowBase batch.expression builder
  let builder := emitOutput outputBase result ⟨0, by decide⟩ builder
  let builder := builder.emit (.branch doneLabel)
  let builder := builder.emit (.label wholeLabel)
  let (negativeInfinity, builder) := builder.freshF64
  let (positiveInfinity, builder) := builder.freshF64
  let builder := builder.emit (.movF64Bits negativeInfinity 0xfff0000000000000)
  let builder := builder.emit (.movF64Bits positiveInfinity 0x7ff0000000000000)
  let whole := { lo := negativeInfinity, hi := positiveInfinity }
  let builder := emitOutput outputBase whole ⟨2, by decide⟩ builder
  let builder := builder.emit (.label doneLabel)
  let builder := builder.emit .ret
  {
    entryName := "sparkinterval_generated"
    variableCount := batch.variableCount
    registers := {
      pred := builder.nextPred
      byte := builder.nextByte
      u32 := builder.nextU32
      u64 := builder.nextU64
      f64 := builder.nextF64
    }
    body := builder.body
  }

/-- Generate deterministic sm_121 PTX from a canonical reference batch. -/
def generateFromCanonicalBatch (text : String) : Except String String := do
  let batch ← parseCanonicalReferenceBatch text
  emit (buildModule batch)

end SparkInterval.PTX
