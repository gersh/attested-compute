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

/-- Drop labels and expose the lexical opcode of every executable typed
instruction in program order. -/
def opcodeTrace (instructions : Array Instruction) : List Opcode :=
  instructions.toList.filterMap Instruction.opcode

private theorem instructionTrace_push (body : Array Instruction)
    (instruction : Instruction) :
    opcodeTrace (body.push instruction) =
      opcodeTrace body ++ instruction.opcode.toList := by
  unfold opcodeTrace
  cases hopcode : instruction.opcode <;> simp [hopcode]

/-- Proof-facing state of the deterministic compiler.  It is public so the
operand/dataflow correctness layer can state invariants of the actual compiler
rather than a duplicate implementation. -/
structure Builder where
  nextPred : Nat := 0
  nextByte : Nat := 0
  nextU32 : Nat := 0
  nextU64 : Nat := 0
  nextF64 : Nat := 0
  body : Array Instruction := #[]
  opcodeLog : List Opcode := []
  trace_eq : opcodeTrace body = opcodeLog := by rfl
  deriving Inhabited

def Builder.initial : Builder := {}

def Builder.emit (builder : Builder) (instruction : Instruction) : Builder :=
  { builder with
    body := builder.body.push instruction
    opcodeLog := builder.opcodeLog ++ instruction.opcode.toList
    trace_eq := by rw [instructionTrace_push, builder.trace_eq] }

def Builder.freshPred (builder : Builder) : Reg .pred × Builder :=
  (⟨builder.nextPred⟩, { builder with nextPred := builder.nextPred + 1 })

def Builder.freshByte (builder : Builder) : Reg .byte × Builder :=
  (⟨builder.nextByte⟩, { builder with nextByte := builder.nextByte + 1 })

def Builder.freshU32 (builder : Builder) : Reg .u32 × Builder :=
  (⟨builder.nextU32⟩, { builder with nextU32 := builder.nextU32 + 1 })

def Builder.freshU64 (builder : Builder) : Reg .u64 × Builder :=
  (⟨builder.nextU64⟩, { builder with nextU64 := builder.nextU64 + 1 })

def Builder.freshF64 (builder : Builder) : Reg .f64 × Builder :=
  (⟨builder.nextF64⟩, { builder with nextF64 := builder.nextF64 + 1 })

def Builder.freshInterval (builder : Builder) : IntervalRegisters × Builder :=
  let (lo, builder) := builder.freshF64
  let (hi, builder) := builder.freshF64
  ({ lo, hi }, builder)

def wholeLabel : Label := ⟨0⟩
def doneLabel : Label := ⟨1⟩

def emitFiniteGuard (value : IntervalRegisters) (builder : Builder) : Builder :=
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

def compileAdd (left right : IntervalRegisters) (builder : Builder) :
    IntervalRegisters × Builder :=
  let builder := emitFiniteGuard left builder
  let builder := emitFiniteGuard right builder
  let (result, builder) := builder.freshInterval
  let builder := (addArithmeticFragment result left right).foldl
    (fun builder instruction => builder.emit instruction) builder
  (result, builder)

def compileSub (left right : IntervalRegisters) (builder : Builder) :
    IntervalRegisters × Builder :=
  let builder := emitFiniteGuard left builder
  let builder := emitFiniteGuard right builder
  let (result, builder) := builder.freshInterval
  let builder := (subArithmeticFragment result left right).foldl
    (fun builder instruction => builder.emit instruction) builder
  (result, builder)

/-- Registers allocated for the multiplication reduction tree. -/
structure MulRegisterAllocation where
  temporaries : MulArithmeticTemporaries
  result : IntervalRegisters
  builder : Builder

/-- Allocate the multiplication temporaries without emitting instructions.
Factoring this pure allocation step keeps structural compiler proofs compact. -/
def allocateMulRegisters (builder : Builder) : MulRegisterAllocation :=
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
  {
    temporaries := {
      down0, down1, down2, down3, up0, up1, up2, up3,
      down01, down23, up01, up23
    }
    result
    builder
  }

def compileMul (left right : IntervalRegisters) (builder : Builder) :
    IntervalRegisters × Builder :=
  let builder := emitFiniteGuard left builder
  let builder := emitFiniteGuard right builder
  let allocation := allocateMulRegisters builder
  let builder := (mulArithmeticFragment allocation.result left right
    allocation.temporaries).foldl
      (fun builder instruction => builder.emit instruction) allocation.builder
  (allocation.result, builder)

def compileConst (value : IntervalBits) (builder : Builder) :
    IntervalRegisters × Builder :=
  let (result, builder) := builder.freshInterval
  let builder := builder.emit (.movF64Bits result.lo value.lo.value)
  let builder := builder.emit (.movF64Bits result.hi value.hi.value)
  (result, builder)

def compilePowLoop (base : IntervalRegisters) :
    Nat → IntervalRegisters → Builder → IntervalRegisters × Builder
  | 0, result, builder => (result, builder)
  | count + 1, result, builder =>
      let (result, builder) := compileMul result base builder
      compilePowLoop base count result builder

def compileExpr (rowBase : Reg .u64) : PolynomialExpr → Builder →
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
      compilePowLoop base exponent initial builder

def emitOutput (outputBase : Reg .u64) (result : IntervalRegisters)
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

structure PrologueResult where
  rowBase : Reg .u64
  outputBase : Reg .u64
  builder : Builder

def emitPrologue (variableCount : Nat) (builder : Builder) : PrologueResult :=
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
    (.mulLoU64Immediate rowOffset rowIndex (variableCount * 16))
  let builder := builder.emit (.addU64 rowBase rowsGlobal rowOffset)
  let builder := builder.emit (.mulLoU64Immediate outputOffset rowIndex 24)
  let builder := builder.emit (.addU64 outputBase outputsGlobal outputOffset)
  { rowBase, outputBase, builder }

def emitEpilogue (outputBase : Reg .u64) (result : IntervalRegisters)
    (builder : Builder) : Builder :=
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
  builder.emit .ret

def buildBuilder (batch : ReferenceBatch) : Builder :=
  let prologue := emitPrologue batch.variableCount Builder.initial
  let (result, builder) :=
    compileExpr prologue.rowBase batch.expression prologue.builder
  emitEpilogue prologue.outputBase result builder

/-- Construct the exact typed PTX module before deterministic text emission.
This is public so the compiler-correctness layer can state properties of the
actual module consumed by `emit`; callers still use `generateFromCanonicalBatch`
for validation and serialization. -/
def buildModule (batch : ReferenceBatch) : Module :=
  let builder := buildBuilder batch
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

/-! ## Exact opcode trace of the compiler

The following independent trace specification is derived only from the source
expression constructors.  `buildModule_opcodeTrace` proves that the complete
typed module built above contains exactly this opcode sequence.  This is
stronger than allowlist membership: a missing rounding direction, guard,
corner product, output store, or control instruction changes the theorem's
right-hand side.
-/

private def finiteGuardOpcodeTrace : List Opcode :=
  [.andB64, .setpEqU64, .bra, .andB64, .setpEqU64, .bra]

private def guardedAddOpcodeTrace : List Opcode :=
  finiteGuardOpcodeTrace ++ finiteGuardOpcodeTrace ++ [.addRmF64, .addRpF64]

private def guardedSubOpcodeTrace : List Opcode :=
  finiteGuardOpcodeTrace ++ finiteGuardOpcodeTrace ++ [.subRmF64, .subRpF64]

private def guardedMulOpcodeTrace : List Opcode :=
  finiteGuardOpcodeTrace ++ finiteGuardOpcodeTrace ++
    [.mulRmF64, .mulRmF64, .mulRmF64, .mulRmF64,
     .mulRpF64, .mulRpF64, .mulRpF64, .mulRpF64,
     .minF64, .minF64, .minF64, .maxF64, .maxF64, .maxF64]

private def repeatOpcodeTrace : Nat → List Opcode → List Opcode
  | 0, _ => []
  | count + 1, trace => trace ++ repeatOpcodeTrace count trace

/-- Opcode sequence required for one compiled expression, excluding the
thread/memory prologue and final output paths. -/
def PolynomialExpr.expectedOpcodeTrace : PolynomialExpr → List Opcode
  | .const _ => [.movB64, .movB64]
  | .var _ => [.ldGlobalF64, .ldGlobalF64]
  | .neg argument => argument.expectedOpcodeTrace ++ [.xorB64, .xorB64]
  | .add left right =>
      left.expectedOpcodeTrace ++ right.expectedOpcodeTrace ++ guardedAddOpcodeTrace
  | .sub left right =>
      left.expectedOpcodeTrace ++ right.expectedOpcodeTrace ++ guardedSubOpcodeTrace
  | .mul left right =>
      left.expectedOpcodeTrace ++ right.expectedOpcodeTrace ++ guardedMulOpcodeTrace
  | .powNat argument exponent =>
      argument.expectedOpcodeTrace ++ [.movB64, .movB64] ++
        repeatOpcodeTrace exponent guardedMulOpcodeTrace

private def kernelPrologueOpcodeTrace : List Opcode :=
  [.movU32, .movU32, .mulWideU32, .movU32, .cvtU64U32, .addU64,
   .ldParamU64, .setpGeU64, .bra, .ldParamU64, .ldParamU64,
   .cvtaGlobalU64, .cvtaGlobalU64, .mulLoU64, .addU64,
   .mulLoU64, .addU64]

private def outputOpcodeTrace : List Opcode :=
  [.movU16, .movU16, .stGlobalF64, .stGlobalF64,
   .stGlobalU8, .stGlobalU8, .stGlobalU8, .stGlobalU8,
   .stGlobalU8, .stGlobalU8, .stGlobalU8, .stGlobalU8]

/-- Complete opcode contract for one generated module. -/
def ReferenceBatch.expectedKernelOpcodeTrace (batch : ReferenceBatch) : List Opcode :=
  kernelPrologueOpcodeTrace ++ batch.expression.expectedOpcodeTrace ++
    outputOpcodeTrace ++ [.bra, .movB64, .movB64] ++ outputOpcodeTrace ++ [.ret]

private theorem emitFiniteGuard_opcodeLog
    (value : IntervalRegisters) (builder : Builder) :
    (emitFiniteGuard value builder).opcodeLog =
      builder.opcodeLog ++ finiteGuardOpcodeTrace := by
  simp [emitFiniteGuard, Builder.freshU64, Builder.freshPred, Builder.emit,
    finiteGuardOpcodeTrace, Instruction.opcode, List.append_assoc]

private theorem compileAdd_opcodeLog
    (left right : IntervalRegisters) (builder : Builder) :
    (compileAdd left right builder).2.opcodeLog =
      builder.opcodeLog ++ guardedAddOpcodeTrace := by
  simp [compileAdd, emitFiniteGuard_opcodeLog, addArithmeticFragment,
    Builder.freshInterval, Builder.freshF64, Builder.emit,
    guardedAddOpcodeTrace, finiteGuardOpcodeTrace, Instruction.opcode,
    List.append_assoc]

private theorem compileSub_opcodeLog
    (left right : IntervalRegisters) (builder : Builder) :
    (compileSub left right builder).2.opcodeLog =
      builder.opcodeLog ++ guardedSubOpcodeTrace := by
  simp [compileSub, emitFiniteGuard_opcodeLog, subArithmeticFragment,
    Builder.freshInterval, Builder.freshF64, Builder.emit,
    guardedSubOpcodeTrace, finiteGuardOpcodeTrace, Instruction.opcode,
    List.append_assoc]

private theorem compileMul_opcodeLog
    (left right : IntervalRegisters) (builder : Builder) :
    (compileMul left right builder).2.opcodeLog =
      builder.opcodeLog ++ guardedMulOpcodeTrace := by
  simp [compileMul, emitFiniteGuard_opcodeLog, mulArithmeticFragment,
    allocateMulRegisters, Builder.freshInterval, Builder.freshF64, Builder.emit,
    guardedMulOpcodeTrace, finiteGuardOpcodeTrace, Instruction.opcode,
    List.append_assoc]

private theorem compileConst_opcodeLog
    (value : IntervalBits) (builder : Builder) :
    (compileConst value builder).2.opcodeLog =
      builder.opcodeLog ++ [.movB64, .movB64] := by
  simp [compileConst, Builder.freshInterval, Builder.freshF64, Builder.emit,
    Instruction.opcode, List.append_assoc]

private theorem compilePowLoop_opcodeLog (base : IntervalRegisters)
    (count : Nat) (current : IntervalRegisters) (builder : Builder) :
    (compilePowLoop base count current builder).2.opcodeLog =
      builder.opcodeLog ++ repeatOpcodeTrace count guardedMulOpcodeTrace := by
  induction count generalizing current builder with
  | zero => simp [compilePowLoop, repeatOpcodeTrace]
  | succ count induction =>
      rw [compilePowLoop]
      rw [induction]
      rw [compileMul_opcodeLog]
      simp [repeatOpcodeTrace, List.append_assoc]

private theorem compileExpr_opcodeLog (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    (compileExpr rowBase expression builder).2.opcodeLog =
      builder.opcodeLog ++ expression.expectedOpcodeTrace := by
  induction expression generalizing builder with
  | const value =>
      simpa [compileExpr, PolynomialExpr.expectedOpcodeTrace] using
        compileConst_opcodeLog value builder
  | var index =>
      simp [compileExpr, Builder.freshInterval, Builder.freshF64, Builder.emit,
        PolynomialExpr.expectedOpcodeTrace, Instruction.opcode, List.append_assoc]
  | neg argument induction =>
      simp [compileExpr, Builder.freshInterval, Builder.freshF64, Builder.emit,
        PolynomialExpr.expectedOpcodeTrace, Instruction.opcode,
        induction builder, List.append_assoc]
  | add left right leftInduction rightInduction =>
      rw [compileExpr, compileAdd_opcodeLog,
        rightInduction (compileExpr rowBase left builder).2,
        leftInduction builder]
      simp [PolynomialExpr.expectedOpcodeTrace, List.append_assoc]
  | sub left right leftInduction rightInduction =>
      rw [compileExpr, compileSub_opcodeLog,
        rightInduction (compileExpr rowBase left builder).2,
        leftInduction builder]
      simp [PolynomialExpr.expectedOpcodeTrace, List.append_assoc]
  | mul left right leftInduction rightInduction =>
      rw [compileExpr, compileMul_opcodeLog,
        rightInduction (compileExpr rowBase left builder).2,
        leftInduction builder]
      simp [PolynomialExpr.expectedOpcodeTrace, List.append_assoc]
  | powNat argument exponent induction =>
      rw [compileExpr, compilePowLoop_opcodeLog, compileConst_opcodeLog,
        induction builder]
      simp [PolynomialExpr.expectedOpcodeTrace, List.append_assoc]

private theorem foldStoreGlobalByte_opcodeLog (indices : List Nat)
    (outputBase : Reg .u64) (zeroRegister : Reg .byte) (builder : Builder) :
    (indices.foldl (fun next index =>
      next.emit (.storeGlobalByte outputBase (17 + index) zeroRegister))
      builder).opcodeLog =
      builder.opcodeLog ++ List.replicate indices.length .stGlobalU8 := by
  induction indices generalizing builder with
  | nil => simp
  | cons index rest induction =>
      simp only [List.foldl_cons, List.length_cons, List.replicate_succ]
      rw [induction]
      simp [Builder.emit, Instruction.opcode, List.append_assoc]

private theorem emitOutput_opcodeLog
    (outputBase : Reg .u64) (result : IntervalRegisters)
    (status : Fin 256) (builder : Builder) :
    (emitOutput outputBase result status builder).opcodeLog =
      builder.opcodeLog ++ outputOpcodeTrace := by
  unfold emitOutput
  rw [foldStoreGlobalByte_opcodeLog]
  simp [Builder.freshByte, Builder.emit, outputOpcodeTrace,
    Instruction.opcode, List.append_assoc]

private theorem emitPrologue_opcodeLog (variableCount : Nat) (builder : Builder) :
    (emitPrologue variableCount builder).builder.opcodeLog =
      builder.opcodeLog ++ kernelPrologueOpcodeTrace := by
  simp [emitPrologue, Builder.freshU32, Builder.freshU64, Builder.freshPred,
    Builder.emit, kernelPrologueOpcodeTrace, Instruction.opcode,
    List.append_assoc]

private theorem emitEpilogue_opcodeLog (outputBase : Reg .u64)
    (result : IntervalRegisters) (builder : Builder) :
    (emitEpilogue outputBase result builder).opcodeLog =
      builder.opcodeLog ++ outputOpcodeTrace ++ [.bra, .movB64, .movB64] ++
        outputOpcodeTrace ++ [.ret] := by
  simp [emitEpilogue, emitOutput_opcodeLog, Builder.freshF64, Builder.emit,
    Instruction.opcode, List.append_assoc]

private theorem buildBuilder_opcodeLog (batch : ReferenceBatch) :
    (buildBuilder batch).opcodeLog = batch.expectedKernelOpcodeTrace := by
  rw [buildBuilder, emitEpilogue_opcodeLog, compileExpr_opcodeLog,
    emitPrologue_opcodeLog]
  simp [Builder.initial, ReferenceBatch.expectedKernelOpcodeTrace,
    List.append_assoc]

/-- The actual typed module contains exactly the independently specified
source-derived opcode sequence. -/
theorem buildModule_opcodeTrace (batch : ReferenceBatch) :
    opcodeTrace (buildModule batch).body = batch.expectedKernelOpcodeTrace := by
  change opcodeTrace (buildBuilder batch).body =
    batch.expectedKernelOpcodeTrace
  rw [(buildBuilder batch).trace_eq]
  exact buildBuilder_opcodeLog batch

/-- Generate deterministic PTX for an explicitly selected deployment target
from a canonical reference batch.  Parsing and typed-module construction are
shared; only the reviewed emitter profile differs between targets. -/
def generateFromCanonicalBatchFor (target : EmitterTarget)
    (text : String) : Except String String := do
  let batch ← parseCanonicalReferenceBatch text
  emitFor target (buildModule batch)

/-- Backwards-compatible library entry point for DGX Spark `sm_121` PTX.
Command-line callers use `generateFromCanonicalBatchFor` through an explicit
fail-closed target option. -/
def generateFromCanonicalBatch (text : String) : Except String String :=
  generateFromCanonicalBatchFor .sm121 text

end SparkInterval.PTX
