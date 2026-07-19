import SparkInterval.PTX.CompilerModuleLayout
import SparkInterval.PTX.ExpressionExecutionRefinement
import SparkInterval.PTX.RunControlRefinement

/-!
# Canonical generated-module body segments

This module replaces the existential expression suffix in the structural
module layout with `compileExprAppendedCode`, the canonical suffix proved equal
to the production compiler body.  It then records the exact module-body
segments needed to move structured execution into whole-module `stepN` and
`run` proofs.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-! ## Canonical production slices -/

def generatedPrologueResult (batch : ReferenceBatch) : PrologueResult :=
  emitPrologue batch.variableCount Builder.initial

def generatedExpressionCompilation (batch : ReferenceBatch) :
    IntervalRegisters × Builder :=
  let prologue := generatedPrologueResult batch
  compileExpr prologue.rowBase batch.expression prologue.builder

def generatedPrologueCode (batch : ReferenceBatch) : List Instruction :=
  (prologueInstructions batch.variableCount Builder.initial).toList

def generatedExpressionCode (batch : ReferenceBatch) : List Instruction :=
  let prologue := generatedPrologueResult batch
  compileExprAppendedCode prologue.rowBase batch.expression prologue.builder

def generatedNormalEpiloguePrefix (batch : ReferenceBatch) :
    List Instruction :=
  let prologue := generatedPrologueResult batch
  let compiled := generatedExpressionCompilation batch
  compiledNormalEpiloguePrefix prologue.outputBase compiled.1 compiled.2

def generatedWholeMaterialization (batch : ReferenceBatch) :
    List Instruction :=
  compiledWholeMaterialization (generatedExpressionCompilation batch).2

def generatedWholeOutputCode (batch : ReferenceBatch) : List Instruction :=
  let prologue := generatedPrologueResult batch
  let compiled := generatedExpressionCompilation batch
  let registers := epilogueCompilerRegisters compiled.2
  compiledOutputInstructions prologue.outputBase registers.whole
    epilogueNonfiniteStatus (epilogueWholeOutputSeed compiled.2)

def generatedWholeEpilogueSuffix (batch : ReferenceBatch) :
    List Instruction :=
  let prologue := generatedPrologueResult batch
  let compiled := generatedExpressionCompilation batch
  compiledWholeEpilogueSuffix prologue.outputBase compiled.2

def generatedReturnTail : List Instruction := compiledEpilogueReturnTail

/-- The canonical expression-code name is exactly the suffix appended by the
production expression compiler in this batch. -/
theorem generatedExpressionCompilation_body (batch : ReferenceBatch) :
    (generatedExpressionCompilation batch).2.body.toList =
      (generatedPrologueResult batch).builder.body.toList ++
        generatedExpressionCode batch := by
  exact compileExpr_body_toList
    (generatedPrologueResult batch).rowBase batch.expression
    (generatedPrologueResult batch).builder

/-- Canonical, non-existential decomposition of the exact production module. -/
theorem buildModule_body_canonical (batch : ReferenceBatch) :
    (buildModule batch).body.toList =
      generatedPrologueCode batch ++
        generatedExpressionCode batch ++
        generatedNormalEpiloguePrefix batch ++
        generatedWholeEpilogueSuffix batch := by
  rcases buildModule_body_layout batch with
    ⟨expressionCode, hbody, hexpressionBody, _, _, _, _, _⟩
  have hcanonical := generatedExpressionCompilation_body batch
  have hcode : expressionCode = generatedExpressionCode batch :=
    List.append_cancel_left (hexpressionBody.symm.trans hcanonical)
  subst expressionCode
  simpa [generatedPrologueCode, generatedPrologueResult,
    generatedExpressionCompilation, generatedExpressionCode,
    generatedNormalEpiloguePrefix, generatedWholeEpilogueSuffix,
    compiledEpilogueInstructions, List.append_assoc] using hbody

/-- Fully expanded canonical decomposition used to isolate the final return
tail inside the whole-path suffix. -/
theorem buildModule_body_canonical_expanded (batch : ReferenceBatch) :
    (buildModule batch).body.toList =
      generatedPrologueCode batch ++
        generatedExpressionCode batch ++
        generatedNormalEpiloguePrefix batch ++
        generatedWholeMaterialization batch ++
        generatedWholeOutputCode batch ++ generatedReturnTail := by
  rw [buildModule_body_canonical]
  simp [generatedWholeEpilogueSuffix, generatedWholeMaterialization,
    generatedWholeOutputCode, generatedReturnTail,
    generatedPrologueResult, generatedExpressionCompilation,
    compiledWholeEpilogueSuffix, List.append_assoc]

@[simp] theorem generatedPrologueCode_length (batch : ReferenceBatch) :
    (generatedPrologueCode batch).length = 17 := by
  simp [generatedPrologueCode]

@[simp] theorem generatedExpressionCode_length (batch : ReferenceBatch) :
    (generatedExpressionCode batch).length =
      batch.expression.compiledInstructionCount := by
  have hbody := generatedExpressionCompilation_body batch
  have hlengths := congrArg List.length hbody
  have hcompileLength :
      (generatedExpressionCompilation batch).2.body.toList.length =
        (generatedPrologueResult batch).builder.body.toList.length +
          batch.expression.compiledInstructionCount := by
    simpa [generatedExpressionCompilation] using
      compileExpr_body_length (generatedPrologueResult batch).rowBase
        batch.expression (generatedPrologueResult batch).builder
  rw [hcompileLength] at hlengths
  simp at hlengths
  omega

@[simp] theorem generatedNormalEpiloguePrefix_length
    (batch : ReferenceBatch) :
    (generatedNormalEpiloguePrefix batch).length = 13 := by
  simp [generatedNormalEpiloguePrefix]

@[simp] theorem generatedWholeMaterialization_length
    (batch : ReferenceBatch) :
    (generatedWholeMaterialization batch).length = 3 := by
  simp [generatedWholeMaterialization, compiledWholeMaterialization]

@[simp] theorem generatedWholeOutputCode_length (batch : ReferenceBatch) :
    (generatedWholeOutputCode batch).length = 12 := by
  simp [generatedWholeOutputCode]

@[simp] theorem generatedWholeEpilogueSuffix_length
    (batch : ReferenceBatch) :
    (generatedWholeEpilogueSuffix batch).length = 17 := by
  simp [generatedWholeEpilogueSuffix]

@[simp] theorem generatedReturnTail_length : generatedReturnTail.length = 2 := by
  simp [generatedReturnTail, compiledEpilogueReturnTail]

/-! ## Exact module-body segments -/

/-- Turning an exact three-part body decomposition into the segment relation
used by whole-module execution.  Keeping this lemma independent of the
compiler also makes the program-counter arithmetic below transparent. -/
theorem moduleBodySegmentAt_of_body_eq (module : Module)
    (leading code trailing : List Instruction)
    (hbody : module.body.toList = leading ++ code ++ trailing) :
    ModuleBodySegmentAt module leading.length code := by
  refine ⟨trailing, ?_⟩
  rw [hbody]
  simp

/-- The generated prologue is the module slice beginning at entry PC zero. -/
theorem buildModule_prologue_segment (batch : ReferenceBatch) :
    ModuleBodySegmentAt (buildModule batch) 0
      (generatedPrologueCode batch) := by
  have hbody : (buildModule batch).body.toList =
      ([] : List Instruction) ++ generatedPrologueCode batch ++
        (generatedExpressionCode batch ++
          generatedNormalEpiloguePrefix batch ++
          generatedWholeEpilogueSuffix batch) := by
    simpa [List.append_assoc] using buildModule_body_canonical batch
  simpa using moduleBodySegmentAt_of_body_eq (buildModule batch)
    [] (generatedPrologueCode batch)
    (generatedExpressionCode batch ++
      generatedNormalEpiloguePrefix batch ++
      generatedWholeEpilogueSuffix batch) hbody

/-- The canonical expression suffix begins immediately after the
17-instruction generated prologue. -/
theorem buildModule_expression_segment (batch : ReferenceBatch) :
    ModuleBodySegmentAt (buildModule batch) 17
      (generatedExpressionCode batch) := by
  have hbody : (buildModule batch).body.toList =
      generatedPrologueCode batch ++ generatedExpressionCode batch ++
        (generatedNormalEpiloguePrefix batch ++
          generatedWholeEpilogueSuffix batch) := by
    simpa [List.append_assoc] using buildModule_body_canonical batch
  simpa using moduleBodySegmentAt_of_body_eq (buildModule batch)
    (generatedPrologueCode batch) (generatedExpressionCode batch)
    (generatedNormalEpiloguePrefix batch ++
      generatedWholeEpilogueSuffix batch) hbody

/-- The ordinary-result output and its branch begin after the prologue and
canonical expression suffix. -/
theorem buildModule_normalEpiloguePrefix_segment (batch : ReferenceBatch) :
    ModuleBodySegmentAt (buildModule batch)
      (batch.expression.compiledInstructionCount + 17)
      (generatedNormalEpiloguePrefix batch) := by
  have hbody : (buildModule batch).body.toList =
      (generatedPrologueCode batch ++ generatedExpressionCode batch) ++
        generatedNormalEpiloguePrefix batch ++
        generatedWholeEpilogueSuffix batch := by
    simpa [List.append_assoc] using buildModule_body_canonical batch
  have hsegment := moduleBodySegmentAt_of_body_eq (buildModule batch)
    (generatedPrologueCode batch ++ generatedExpressionCode batch)
    (generatedNormalEpiloguePrefix batch)
    (generatedWholeEpilogueSuffix batch) hbody
  have hpc :
      (generatedPrologueCode batch ++ generatedExpressionCode batch).length =
        batch.expression.compiledInstructionCount + 17 := by
    simp
    omega
  rw [← hpc]
  exact hsegment

/-- The whole-result suffix begins at `wholeLabel`, at the independently
proved whole-label program counter. -/
theorem buildModule_wholeEpilogueSuffix_segment (batch : ReferenceBatch) :
    ModuleBodySegmentAt (buildModule batch)
      (batch.expression.compiledInstructionCount + 30)
      (generatedWholeEpilogueSuffix batch) := by
  have hbody : (buildModule batch).body.toList =
      (generatedPrologueCode batch ++ generatedExpressionCode batch ++
        generatedNormalEpiloguePrefix batch) ++
        generatedWholeEpilogueSuffix batch ++ [] := by
    simpa [List.append_assoc] using buildModule_body_canonical batch
  have hsegment := moduleBodySegmentAt_of_body_eq (buildModule batch)
    (generatedPrologueCode batch ++ generatedExpressionCode batch ++
      generatedNormalEpiloguePrefix batch)
    (generatedWholeEpilogueSuffix batch) [] hbody
  have hpc :
      (generatedPrologueCode batch ++ generatedExpressionCode batch ++
        generatedNormalEpiloguePrefix batch).length =
        batch.expression.compiledInstructionCount + 30 := by
    simp
    omega
  rw [← hpc]
  exact hsegment

/-- The final done label and return form the module slice at the independently
proved done-label program counter. -/
theorem buildModule_returnTail_segment (batch : ReferenceBatch) :
    ModuleBodySegmentAt (buildModule batch)
      (batch.expression.compiledInstructionCount + 45) generatedReturnTail := by
  have hbody : (buildModule batch).body.toList =
      (generatedPrologueCode batch ++ generatedExpressionCode batch ++
        generatedNormalEpiloguePrefix batch ++
        generatedWholeMaterialization batch ++
        generatedWholeOutputCode batch) ++ generatedReturnTail ++ [] := by
    simpa [List.append_assoc] using buildModule_body_canonical_expanded batch
  have hsegment := moduleBodySegmentAt_of_body_eq (buildModule batch)
    (generatedPrologueCode batch ++ generatedExpressionCode batch ++
      generatedNormalEpiloguePrefix batch ++
      generatedWholeMaterialization batch ++
      generatedWholeOutputCode batch)
    generatedReturnTail [] hbody
  have hpc :
      (generatedPrologueCode batch ++ generatedExpressionCode batch ++
        generatedNormalEpiloguePrefix batch ++
        generatedWholeMaterialization batch ++
        generatedWholeOutputCode batch).length =
        batch.expression.compiledInstructionCount + 45 := by
    simp
    omega
  rw [← hpc]
  exact hsegment

/-- The structural suffix fact and label scan agree on the whole-path entry
program counter. -/
theorem buildModule_wholeLabel_segment (batch : ReferenceBatch) :
    labelPosition? (buildModule batch) wholeLabel =
        some (batch.expression.compiledInstructionCount + 30) ∧
      ModuleBodySegmentAt (buildModule batch)
        (batch.expression.compiledInstructionCount + 30)
        (generatedWholeEpilogueSuffix batch) := by
  exact ⟨buildModule_wholeLabel_position batch,
    buildModule_wholeEpilogueSuffix_segment batch⟩

/-- The structural tail fact and label scan agree on the common return entry
program counter. -/
theorem buildModule_doneLabel_segment (batch : ReferenceBatch) :
    labelPosition? (buildModule batch) doneLabel =
        some (batch.expression.compiledInstructionCount + 45) ∧
      ModuleBodySegmentAt (buildModule batch)
        (batch.expression.compiledInstructionCount + 45)
        generatedReturnTail := by
  exact ⟨buildModule_doneLabel_position batch,
    buildModule_returnTail_segment batch⟩

/-! ## Whole-machine stepping coverage -/

/-- `Instruction.IsRunStepCompatible` has a positive case for every
instruction constructor currently represented by the PTX model.  Consequently
every generated slice, and indeed every current instruction list, is covered
by the whole-machine stepping relation.  If a new instruction constructor is
added, this exhaustive proof deliberately becomes a new proof obligation. -/
theorem runStepCompatible_allCurrentInstructions (code : List Instruction) :
    RunStepCompatible code := by
  intro instruction _
  cases instruction <;> trivial

theorem generatedPrologueCode_runStepCompatible (batch : ReferenceBatch) :
    RunStepCompatible (generatedPrologueCode batch) :=
  runStepCompatible_allCurrentInstructions _

theorem generatedExpressionCode_runStepCompatible (batch : ReferenceBatch) :
    RunStepCompatible (generatedExpressionCode batch) :=
  runStepCompatible_allCurrentInstructions _

theorem generatedNormalEpiloguePrefix_runStepCompatible
    (batch : ReferenceBatch) :
    RunStepCompatible (generatedNormalEpiloguePrefix batch) :=
  runStepCompatible_allCurrentInstructions _

theorem generatedWholeEpilogueSuffix_runStepCompatible
    (batch : ReferenceBatch) :
    RunStepCompatible (generatedWholeEpilogueSuffix batch) :=
  runStepCompatible_allCurrentInstructions _

theorem generatedReturnTail_runStepCompatible :
    RunStepCompatible generatedReturnTail :=
  runStepCompatible_allCurrentInstructions _

theorem buildModule_body_runStepCompatible (batch : ReferenceBatch) :
    RunStepCompatible (buildModule batch).body.toList :=
  runStepCompatible_allCurrentInstructions _

end SparkInterval.PTX
