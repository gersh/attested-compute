import SparkInterval.PTX.CompilerBodyDataflow
import SparkInterval.PTX.PrologueRefinement
import SparkInterval.PTX.CompilerEpilogueRefinement

/-!
# Production module body and branch-label layout

This module decomposes the exact `buildModule` instruction body into its
production prologue, the actual suffix appended by `compileExpr`, and its
production epilogue.  A compositional label-free invariant for expression
code then makes the two generated label positions independent of expression
shape except for the expression instruction count.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-! ## Label-free lexical slices -/

/-- Proposition-valued test used when scanning compiler slices for labels. -/
def Instruction.IsNotLabel : Instruction → Prop
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
  | .label _ => False
  | .binaryF64 .. => True
  | .minimumF64 .. => True
  | .maximumF64 .. => True
  | .ret => True

/-- No instruction in a lexical slice is a label. -/
def LabelFree (code : List Instruction) : Prop :=
  ∀ instruction, instruction ∈ code → instruction.IsNotLabel

namespace LabelFree

theorem nil : LabelFree [] := by
  simp [LabelFree]

theorem append {first second : List Instruction}
    (hfirst : LabelFree first) (hsecond : LabelFree second) :
    LabelFree (first ++ second) := by
  intro instruction hinstruction
  rcases List.mem_append.mp hinstruction with hleft | hright
  · exact hfirst instruction hleft
  · exact hsecond instruction hright

theorem tail {instruction : Instruction} {rest : List Instruction}
    (hfree : LabelFree (instruction :: rest)) : LabelFree rest := by
  intro current hcurrent
  exact hfree current (by simp [hcurrent])

end LabelFree

theorem labelPositionFrom_cons_of_isNotLabel
    (instruction : Instruction) (rest : List Instruction)
    (target : Label) (position : Nat)
    (hnotLabel : instruction.IsNotLabel) :
    labelPositionFrom (instruction :: rest) target position =
      labelPositionFrom rest target (position + 1) := by
  cases instruction <;>
    simp [Instruction.IsNotLabel, labelPositionFrom] at hnotLabel ⊢

/-- A label-free prefix can be skipped while adding its length to the program
counter used by the label scan. -/
theorem labelPositionFrom_append_of_labelFree
    (leading trailing : List Instruction) (target : Label) (position : Nat)
    (hleading : LabelFree leading) :
    labelPositionFrom (leading ++ trailing) target position =
      labelPositionFrom trailing target (position + leading.length) := by
  induction leading generalizing position with
  | nil => simp
  | cons instruction rest induction =>
      have hinstruction : instruction.IsNotLabel :=
        hleading instruction (by simp)
      have hrest : LabelFree rest := hleading.tail
      rw [List.cons_append,
        labelPositionFrom_cons_of_isNotLabel instruction (rest ++ trailing)
          target position hinstruction,
        induction (position := position + 1) hrest]
      simp [Nat.add_comm, Nat.add_left_comm]

/-! ## Label-free invariants of production expression compilation -/

/-- `after` appends a label-free slice to `before`. -/
def Builder.BodyLabelFreeExtension (before after : Builder) : Prop :=
  ∃ suffix,
    after.body.toList = before.body.toList ++ suffix ∧ LabelFree suffix

namespace Builder.BodyLabelFreeExtension

theorem refl (builder : Builder) : builder.BodyLabelFreeExtension builder := by
  exact ⟨[], by simp, LabelFree.nil⟩

theorem trans {first middle final : Builder}
    (hfirst : first.BodyLabelFreeExtension middle)
    (hsecond : middle.BodyLabelFreeExtension final) :
    first.BodyLabelFreeExtension final := by
  rcases hfirst with ⟨firstCode, hfirstBody, hfirstLabels⟩
  rcases hsecond with ⟨secondCode, hsecondBody, hsecondLabels⟩
  refine ⟨firstCode ++ secondCode, ?_, hfirstLabels.append hsecondLabels⟩
  rw [hsecondBody, hfirstBody, List.append_assoc]

end Builder.BodyLabelFreeExtension

theorem compileConstAppendedCode_labelFree
    (value : IntervalBits) (builder : Builder) :
    LabelFree (compileConstAppendedCode value builder) := by
  simp [LabelFree, Instruction.IsNotLabel, compileConstAppendedCode]

theorem compileVarAppendedCode_labelFree (rowBase : Reg .u64)
    (index : Nat) (builder : Builder) :
    LabelFree (compileVarAppendedCode rowBase index builder) := by
  simp [LabelFree, Instruction.IsNotLabel, compileVarAppendedCode]

theorem compileNegAppendedCode_labelFree (argument : IntervalRegisters)
    (builder : Builder) :
    LabelFree (compileNegAppendedCode argument builder) := by
  simp [LabelFree, Instruction.IsNotLabel, compileNegAppendedCode]

theorem compileAddAppendedCode_labelFree (left right : IntervalRegisters)
    (builder : Builder) :
    LabelFree (compileAddAppendedCode left right builder) := by
  simp [LabelFree, Instruction.IsNotLabel, compileAddAppendedCode,
    compiledFiniteGuardInstructions, finiteGuardCompilerRegisters,
    finiteGuardInstructions, addArithmeticFragment]

theorem compileSubAppendedCode_labelFree (left right : IntervalRegisters)
    (builder : Builder) :
    LabelFree (compileSubAppendedCode left right builder) := by
  simp [LabelFree, Instruction.IsNotLabel, compileSubAppendedCode,
    compiledFiniteGuardInstructions, finiteGuardCompilerRegisters,
    finiteGuardInstructions, subArithmeticFragment]

theorem compileMulAppendedCode_labelFree (left right : IntervalRegisters)
    (builder : Builder) :
    LabelFree (compileMulAppendedCode left right builder) := by
  simp [LabelFree, Instruction.IsNotLabel, compileMulAppendedCode,
    compiledFiniteGuardInstructions, finiteGuardCompilerRegisters,
    finiteGuardInstructions, mulArithmeticFragment]

theorem compileConst_body_labelFree (value : IntervalBits) (builder : Builder) :
    builder.BodyLabelFreeExtension (compileConst value builder).2 := by
  exact ⟨compileConstAppendedCode value builder,
    compileConst_body_toList value builder,
    compileConstAppendedCode_labelFree value builder⟩

theorem compileExpr_var_body_labelFree (rowBase : Reg .u64) (index : Nat)
    (builder : Builder) :
    builder.BodyLabelFreeExtension
      (compileExpr rowBase (.var index) builder).2 := by
  exact ⟨compileVarAppendedCode rowBase index builder,
    compileExpr_var_body_toList rowBase index builder,
    compileVarAppendedCode_labelFree rowBase index builder⟩

theorem compileExpr_neg_tail_body_labelFree
    (argument : IntervalRegisters) (builder : Builder) :
    let fresh := builder.freshInterval
    let afterLo := fresh.2.emit (.xorF64Sign fresh.1.lo argument.hi)
    let final := afterLo.emit (.xorF64Sign fresh.1.hi argument.lo)
    builder.BodyLabelFreeExtension final := by
  dsimp only
  exact ⟨compileNegAppendedCode argument builder,
    compileExpr_neg_tail_body_toList argument builder,
    compileNegAppendedCode_labelFree argument builder⟩

theorem compileAdd_body_labelFree (left right : IntervalRegisters)
    (builder : Builder) :
    builder.BodyLabelFreeExtension (compileAdd left right builder).2 := by
  exact ⟨compileAddAppendedCode left right builder,
    compileAdd_body_toList left right builder,
    compileAddAppendedCode_labelFree left right builder⟩

theorem compileSub_body_labelFree (left right : IntervalRegisters)
    (builder : Builder) :
    builder.BodyLabelFreeExtension (compileSub left right builder).2 := by
  exact ⟨compileSubAppendedCode left right builder,
    compileSub_body_toList left right builder,
    compileSubAppendedCode_labelFree left right builder⟩

theorem compileMul_body_labelFree (left right : IntervalRegisters)
    (builder : Builder) :
    builder.BodyLabelFreeExtension (compileMul left right builder).2 := by
  exact ⟨compileMulAppendedCode left right builder,
    compileMul_body_toList left right builder,
    compileMulAppendedCode_labelFree left right builder⟩

theorem compilePowLoop_body_labelFree (base : IntervalRegisters)
    (count : Nat) (current : IntervalRegisters) (builder : Builder) :
    builder.BodyLabelFreeExtension
      (compilePowLoop base count current builder).2 := by
  induction count generalizing current builder with
  | zero => exact Builder.BodyLabelFreeExtension.refl builder
  | succ count induction =>
      rw [compilePowLoop]
      exact (compileMul_body_labelFree current base builder).trans
        (induction (compileMul current base builder).1
          (compileMul current base builder).2)

/-- The production recursive expression compiler never emits a label. -/
theorem compileExpr_body_labelFree (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    builder.BodyLabelFreeExtension
      (compileExpr rowBase expression builder).2 := by
  induction expression generalizing builder with
  | const value => exact compileConst_body_labelFree value builder
  | var index => exact compileExpr_var_body_labelFree rowBase index builder
  | neg argument induction =>
      rw [compileExpr]
      exact (induction builder).trans
        (compileExpr_neg_tail_body_labelFree
          (compileExpr rowBase argument builder).1
          (compileExpr rowBase argument builder).2)
  | add left right leftInduction rightInduction =>
      rw [compileExpr]
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      exact (leftInduction builder).trans <|
        (rightInduction leftCompiled.2).trans <|
          compileAdd_body_labelFree leftCompiled.1 rightCompiled.1
            rightCompiled.2
  | sub left right leftInduction rightInduction =>
      rw [compileExpr]
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      exact (leftInduction builder).trans <|
        (rightInduction leftCompiled.2).trans <|
          compileSub_body_labelFree leftCompiled.1 rightCompiled.1
            rightCompiled.2
  | mul left right leftInduction rightInduction =>
      rw [compileExpr]
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      exact (leftInduction builder).trans <|
        (rightInduction leftCompiled.2).trans <|
          compileMul_body_labelFree leftCompiled.1 rightCompiled.1
            rightCompiled.2
  | powNat argument exponent induction =>
      rw [compileExpr]
      let argumentCompiled := compileExpr rowBase argument builder
      let one : IntervalBits := {
        lo := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
        hi := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
      }
      let initialCompiled := compileConst one argumentCompiled.2
      exact (induction builder).trans <|
        (compileConst_body_labelFree one argumentCompiled.2).trans <|
          compilePowLoop_body_labelFree argumentCompiled.1 exponent
            initialCompiled.1 initialCompiled.2

/-! ## Exact expression instruction count -/

/-- Number of typed instructions appended by the production expression
compiler.  Labels belong only to the epilogue and are therefore not counted
by any expression constructor. -/
def PolynomialExpr.compiledInstructionCount : PolynomialExpr → Nat
  | .const _ => 2
  | .var _ => 2
  | .neg argument => argument.compiledInstructionCount + 2
  | .add left right | .sub left right =>
      left.compiledInstructionCount + right.compiledInstructionCount + 14
  | .mul left right =>
      left.compiledInstructionCount + right.compiledInstructionCount + 26
  | .powNat argument exponent =>
      argument.compiledInstructionCount + 2 + exponent * 26

@[simp] theorem compileConstAppendedCode_length
    (value : IntervalBits) (builder : Builder) :
    (compileConstAppendedCode value builder).length = 2 := by
  simp [compileConstAppendedCode]

@[simp] theorem compileVarAppendedCode_length (rowBase : Reg .u64)
    (index : Nat) (builder : Builder) :
    (compileVarAppendedCode rowBase index builder).length = 2 := by
  simp [compileVarAppendedCode]

@[simp] theorem compileNegAppendedCode_length
    (argument : IntervalRegisters) (builder : Builder) :
    (compileNegAppendedCode argument builder).length = 2 := by
  simp [compileNegAppendedCode]

@[simp] theorem compileAddAppendedCode_length
    (left right : IntervalRegisters) (builder : Builder) :
    (compileAddAppendedCode left right builder).length = 14 := by
  simp [compileAddAppendedCode, compiledFiniteGuardInstructions,
    finiteGuardInstructions, addArithmeticFragment]

@[simp] theorem compileSubAppendedCode_length
    (left right : IntervalRegisters) (builder : Builder) :
    (compileSubAppendedCode left right builder).length = 14 := by
  simp [compileSubAppendedCode, compiledFiniteGuardInstructions,
    finiteGuardInstructions, subArithmeticFragment]

@[simp] theorem compileMulAppendedCode_length
    (left right : IntervalRegisters) (builder : Builder) :
    (compileMulAppendedCode left right builder).length = 26 := by
  simp [compileMulAppendedCode, compiledFiniteGuardInstructions,
    finiteGuardInstructions, mulArithmeticFragment]

theorem compilePowLoop_body_length (base : IntervalRegisters)
    (count : Nat) (current : IntervalRegisters) (builder : Builder) :
    (compilePowLoop base count current builder).2.body.toList.length =
      builder.body.toList.length + count * 26 := by
  induction count generalizing current builder with
  | zero => simp [compilePowLoop]
  | succ count induction =>
      rw [compilePowLoop, induction,
        compileMul_body_toList current base builder]
      simp
      omega

/-- Exact body-length effect of the recursive production expression compiler. -/
theorem compileExpr_body_length (rowBase : Reg .u64)
    (expression : PolynomialExpr) (builder : Builder) :
    (compileExpr rowBase expression builder).2.body.toList.length =
      builder.body.toList.length + expression.compiledInstructionCount := by
  induction expression generalizing builder with
  | const value =>
      rw [compileExpr, compileConst_body_toList]
      simp [PolynomialExpr.compiledInstructionCount]
  | var index =>
      rw [compileExpr_var_body_toList]
      simp [PolynomialExpr.compiledInstructionCount]
  | neg argument induction =>
      rw [compileExpr]
      let argumentCompiled := compileExpr rowBase argument builder
      rw [compileExpr_neg_tail_body_toList argumentCompiled.1
        argumentCompiled.2]
      simp only [List.length_append]
      rw [induction builder]
      simp [PolynomialExpr.compiledInstructionCount]
      omega
  | add left right leftInduction rightInduction =>
      rw [compileExpr]
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      rw [compileAdd_body_toList]
      simp only [List.length_append]
      rw [rightInduction (compileExpr rowBase left builder).2,
        leftInduction builder]
      simp [PolynomialExpr.compiledInstructionCount]
      omega
  | sub left right leftInduction rightInduction =>
      rw [compileExpr]
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      rw [compileSub_body_toList]
      simp only [List.length_append]
      rw [rightInduction (compileExpr rowBase left builder).2,
        leftInduction builder]
      simp [PolynomialExpr.compiledInstructionCount]
      omega
  | mul left right leftInduction rightInduction =>
      rw [compileExpr]
      let leftCompiled := compileExpr rowBase left builder
      let rightCompiled := compileExpr rowBase right leftCompiled.2
      rw [compileMul_body_toList]
      simp only [List.length_append]
      rw [rightInduction (compileExpr rowBase left builder).2,
        leftInduction builder]
      simp [PolynomialExpr.compiledInstructionCount]
      omega
  | powNat argument exponent induction =>
      rw [compileExpr]
      let argumentCompiled := compileExpr rowBase argument builder
      let one : IntervalBits := {
        lo := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
        hi := { value := 0x3ff0000000000000, hex := "3ff0000000000000" }
      }
      let initialCompiled := compileConst one argumentCompiled.2
      rw [compilePowLoop_body_length, compileConst_body_toList]
      simp only [List.length_append]
      rw [induction builder]
      simp [PolynomialExpr.compiledInstructionCount]
      omega

/-! ## Complete production body decomposition -/

@[simp] theorem prologueInstructions_length (variableCount : Nat)
    (builder : Builder) :
    (prologueInstructions variableCount builder).toList.length = 17 := by
  simp [prologueInstructions]

@[simp] theorem prologueInstructions_size (variableCount : Nat)
    (builder : Builder) :
    (prologueInstructions variableCount builder).size = 17 := by
  simp [prologueInstructions]

theorem prologueInstructions_labelFree (variableCount : Nat)
    (builder : Builder) :
    LabelFree (prologueInstructions variableCount builder).toList := by
  simp [LabelFree, Instruction.IsNotLabel, prologueInstructions]

/-- Builder-level form of the exact production body decomposition.  The
witness is the literal suffix appended by the actual `compileExpr` call, and
all expression effect invariants refer to that same list. -/
theorem buildBuilder_body_layout (batch : ReferenceBatch) :
    let initial := Builder.initial
    let prologue := emitPrologue batch.variableCount initial
    let compiled := compileExpr prologue.rowBase batch.expression
      prologue.builder
    ∃ expressionCode,
      (buildBuilder batch).body.toList =
          (prologueInstructions batch.variableCount initial).toList ++
            expressionCode ++
            compiledEpilogueInstructions prologue.outputBase compiled.1
              compiled.2 ∧
        compiled.2.body.toList =
          prologue.builder.body.toList ++ expressionCode ∧
        expressionCode.length =
          batch.expression.compiledInstructionCount ∧
        LabelFree expressionCode ∧
        F64WritesAtOrAbove prologue.builder.nextF64 expressionCode ∧
        U64WritesAtOrAbove prologue.builder.nextU64 expressionCode ∧
        GlobalMemoryWriteFree expressionCode := by
  dsimp only
  let initial := Builder.initial
  let prologue := emitPrologue batch.variableCount initial
  let compiled := compileExpr prologue.rowBase batch.expression
    prologue.builder
  rcases compileExpr_body_effectSafe prologue.rowBase batch.expression
    prologue.builder with
    ⟨expressionCode, hexpressionBody, hf64, hu64, hmemory⟩
  rcases compileExpr_body_labelFree prologue.rowBase batch.expression
    prologue.builder with
    ⟨labelCode, hlabelBody, hlabelFree⟩
  have hcodes : labelCode = expressionCode :=
    List.append_cancel_left (hlabelBody.symm.trans hexpressionBody)
  subst labelCode
  have hlength : expressionCode.length =
      batch.expression.compiledInstructionCount := by
    have hlengths := congrArg List.length hexpressionBody
    rw [compileExpr_body_length] at hlengths
    simp at hlengths
    omega
  rcases emitPrologue_exact batch.variableCount initial with
    ⟨_, _, hprologueBody, _, _, _, _, _⟩
  have hprologueList : prologue.builder.body.toList =
      (prologueInstructions batch.variableCount initial).toList := by
    simpa [prologue, initial, Builder.initial] using
      congrArg Array.toList hprologueBody
  have hepilogueList :
      (emitEpilogue prologue.outputBase compiled.1 compiled.2).body.toList =
        compiled.2.body.toList ++
          compiledEpilogueInstructions prologue.outputBase compiled.1
            compiled.2 := by
    simpa using congrArg Array.toList
      (emitEpilogue_body prologue.outputBase compiled.1 compiled.2)
  refine ⟨expressionCode, ?_, hexpressionBody, hlength, hlabelFree,
    hf64, hu64, hmemory⟩
  change (emitEpilogue prologue.outputBase compiled.1 compiled.2).body.toList = _
  rw [hepilogueList, hexpressionBody, hprologueList, List.append_assoc]

/-- Exact `buildModule` body decomposition with the expression suffix's
write-frontier, store-free, and label-free invariants attached. -/
theorem buildModule_body_layout (batch : ReferenceBatch) :
    let initial := Builder.initial
    let prologue := emitPrologue batch.variableCount initial
    let compiled := compileExpr prologue.rowBase batch.expression
      prologue.builder
    ∃ expressionCode,
      (buildModule batch).body.toList =
          (prologueInstructions batch.variableCount initial).toList ++
            expressionCode ++
            compiledEpilogueInstructions prologue.outputBase compiled.1
              compiled.2 ∧
        compiled.2.body.toList =
          prologue.builder.body.toList ++ expressionCode ∧
        expressionCode.length =
          batch.expression.compiledInstructionCount ∧
        LabelFree expressionCode ∧
        F64WritesAtOrAbove prologue.builder.nextF64 expressionCode ∧
        U64WritesAtOrAbove prologue.builder.nextU64 expressionCode ∧
        GlobalMemoryWriteFree expressionCode := by
  change let initial := Builder.initial
    let prologue := emitPrologue batch.variableCount initial
    let compiled := compileExpr prologue.rowBase batch.expression
      prologue.builder
    ∃ expressionCode,
      (buildBuilder batch).body.toList =
          (prologueInstructions batch.variableCount initial).toList ++
            expressionCode ++
            compiledEpilogueInstructions prologue.outputBase compiled.1
              compiled.2 ∧
        compiled.2.body.toList =
          prologue.builder.body.toList ++ expressionCode ∧
        expressionCode.length =
          batch.expression.compiledInstructionCount ∧
        LabelFree expressionCode ∧
        F64WritesAtOrAbove prologue.builder.nextF64 expressionCode ∧
        U64WritesAtOrAbove prologue.builder.nextU64 expressionCode ∧
        GlobalMemoryWriteFree expressionCode
  exact buildBuilder_body_layout batch

/-! ## Exact generated label positions -/

theorem labelPositionFrom_compiledEpilogue_whole
    (outputBase : Reg .u64) (result : IntervalRegisters)
    (builder : Builder) (position : Nat) :
    labelPositionFrom
        (compiledEpilogueInstructions outputBase result builder)
        wholeLabel position = some (position + 13) := by
  simp [compiledEpilogueInstructions, compiledNormalEpiloguePrefix,
    compiledWholeEpilogueSuffix, compiledWholeMaterialization,
    compiledEpilogueReturnTail, compiledOutputInstructions,
    labelPositionFrom, wholeLabel, doneLabel]

theorem labelPositionFrom_compiledEpilogue_done
    (outputBase : Reg .u64) (result : IntervalRegisters)
    (builder : Builder) (position : Nat) :
    labelPositionFrom
        (compiledEpilogueInstructions outputBase result builder)
        doneLabel position = some (position + 28) := by
  simp [compiledEpilogueInstructions, compiledNormalEpiloguePrefix,
    compiledWholeEpilogueSuffix, compiledWholeMaterialization,
    compiledEpilogueReturnTail, compiledOutputInstructions,
    labelPositionFrom, wholeLabel, doneLabel]

/-- The first generated label starts the whole-interval path, after the
17-instruction prologue, expression slice, and 13-instruction normal prefix. -/
theorem buildModule_wholeLabel_position (batch : ReferenceBatch) :
    labelPosition? (buildModule batch) wholeLabel =
      some (batch.expression.compiledInstructionCount + 30) := by
  rcases buildModule_body_layout batch with
    ⟨expressionCode, hbody, _, hlength, hexpressionLabels, _, _, _⟩
  let initial := Builder.initial
  let prologue := emitPrologue batch.variableCount initial
  let compiled := compileExpr prologue.rowBase batch.expression
    prologue.builder
  have hprefix : LabelFree
      ((prologueInstructions batch.variableCount initial).toList ++
        expressionCode) :=
    (prologueInstructions_labelFree batch.variableCount initial).append
      hexpressionLabels
  unfold labelPosition?
  rw [hbody,
    labelPositionFrom_append_of_labelFree _ _ _ _ hprefix,
    labelPositionFrom_compiledEpilogue_whole]
  simp [hlength]
  omega

/-- The common done label is the penultimate epilogue instruction. -/
theorem buildModule_doneLabel_position (batch : ReferenceBatch) :
    labelPosition? (buildModule batch) doneLabel =
      some (batch.expression.compiledInstructionCount + 45) := by
  rcases buildModule_body_layout batch with
    ⟨expressionCode, hbody, _, hlength, hexpressionLabels, _, _, _⟩
  let initial := Builder.initial
  let prologue := emitPrologue batch.variableCount initial
  let compiled := compileExpr prologue.rowBase batch.expression
    prologue.builder
  have hprefix : LabelFree
      ((prologueInstructions batch.variableCount initial).toList ++
        expressionCode) :=
    (prologueInstructions_labelFree batch.variableCount initial).append
      hexpressionLabels
  unfold labelPosition?
  rw [hbody,
    labelPositionFrom_append_of_labelFree _ _ _ _ hprefix,
    labelPositionFrom_compiledEpilogue_done]
  simp [hlength]
  omega

/-- Total generated body length: 17 prologue instructions, the exact
expression cost, and 30 epilogue instructions. -/
theorem buildModule_body_size (batch : ReferenceBatch) :
    (buildModule batch).body.size =
      batch.expression.compiledInstructionCount + 47 := by
  rcases buildModule_body_layout batch with
    ⟨expressionCode, hbody, _, hlength, _, _, _, _⟩
  have hlengths := congrArg List.length hbody
  simp [hlength, prologueInstructions] at hlengths
  omega

end SparkInterval.PTX
