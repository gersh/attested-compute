/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.X86ELFPureEntry

/-!
# Deterministic byte-program boundary for certificate finalizers

This module is the small source-program layer between a mathematical checker
contract and any future compiler/loader/ISA proof.  A `Program` is a total,
deterministic function from the complete input byte string to either:

* an explicit rejection code; or
* the complete output byte string returned by the finalizer.

`RefinesNativeChecker` is the ordinary Lean obligation that every successful
program result satisfies one *fixed* `NativeCheckerSemantics`.  It has no
application proposition, receipt, architecture state, executable image, or
trusted field.  In particular, defining a program does not prove that any C,
x86-64, PTX, SASS, CPU, or GPU implementation executes it.

The final theorem has exactly the behavior-refinement shape used for the
source-facing field of `StaticCPUExecutableCertificate`.  A future
compiler/loader/ISA chain must still prove that its concrete implementation
refines `Program.successBehavior`; nothing in this module supplies that
theorem.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Architecture.DeterministicFinalizerIR

open X86ELF

/-- Complete result of one deterministic source-level finalizer run.

Rejection codes are program data only.  They carry no mathematical
proposition and have no acceptance semantics. -/
inductive Outcome where
  | rejected (code : Nat)
  | returned (outputBytes : ByteArray)

/-- A total deterministic byte program.

`contractId` is bound to the selected native checker by
`RefinesNativeChecker`; it is not a receipt-selected claim tag. -/
structure Program where
  contractId : String
  run : ByteArray → Outcome

namespace Program

/-- Exact input/output behavior of successful executions of the source
program. -/
def successBehavior (program : Program) : IOBehavior :=
  fun inputBytes outputBytes =>
    program.run inputBytes = .returned outputBytes

/-- A deterministic program cannot return two different output byte strings
for the same complete input. -/
theorem output_unique
    (program : Program)
    {inputBytes firstOutput secondOutput : ByteArray}
    (first :
      program.successBehavior inputBytes firstOutput)
    (second :
      program.successBehavior inputBytes secondOutput) :
    firstOutput = secondOutput := by
  simp only [successBehavior] at first second
  rw [first] at second
  exact Outcome.returned.inj second

/-- A rejected execution is never a successful output behavior. -/
theorem rejected_not_successful
    (program : Program)
    {inputBytes outputBytes : ByteArray}
    {code : Nat}
    (rejected : program.run inputBytes = .rejected code) :
    ¬ program.successBehavior inputBytes outputBytes := by
  intro returned
  simp only [successBehavior] at returned
  rw [rejected] at returned
  cases returned

end Program

/-- Ordinary program-level proof for one fixed native checker.

The contract identifier equality prevents a program proof reviewed for one
named checker from being silently relabeled as another.  `successful` is
universal in the complete input and output byte strings. -/
structure RefinesNativeChecker
    (program : Program)
    (checker : NativeCheckerSemantics) : Prop where
  contractId : program.contractId = checker.checkerId
  successful :
    ∀ {inputBytes outputBytes : ByteArray},
      program.successBehavior inputBytes outputBytes →
        checker.accepts inputBytes outputBytes

namespace RefinesNativeChecker

/-- A successful program run satisfies its fixed native-checker relation. -/
theorem accepts
    {program : Program}
    {checker : NativeCheckerSemantics}
    (refinement : RefinesNativeChecker program checker)
    {inputBytes outputBytes : ByteArray}
    (returned :
      program.run inputBytes = .returned outputBytes) :
    checker.accepts inputBytes outputBytes :=
  refinement.successful returned

/-- The program proof is exactly the source-to-checker behavior refinement
required by the existing static executable certificate chain. -/
theorem behaviorRefinement
    {program : Program}
    {checker : NativeCheckerSemantics}
    (refinement : RefinesNativeChecker program checker) :
    BehaviorRefines program.successBehavior checker.accepts :=
  refinement.successful

/-- Compose a separately proved implementation-to-program theorem with the
program-to-checker theorem.

This theorem is deliberately behavior-only.  It does not assert that a
compiler, executable, loader, or architecture supplies `lowerToProgram`. -/
theorem of_lowerBehavior
    {program : Program}
    {checker : NativeCheckerSemantics}
    {lowerBehavior : IOBehavior}
    (lowerToProgram :
      BehaviorRefines lowerBehavior program.successBehavior)
    (programToChecker :
      RefinesNativeChecker program checker) :
    BehaviorRefines lowerBehavior checker.accepts :=
  lowerToProgram.trans programToChecker.behaviorRefinement

end RefinesNativeChecker

/-- A concrete deterministic program together with its ordinary proof for a
fixed checker.  This is source code/proof data, not an executable or receipt
certificate. -/
structure Certificate (checker : NativeCheckerSemantics) : Type where
  program : Program
  refinement : RefinesNativeChecker program checker

namespace Certificate

/-- Project a source-to-checker behavior theorem in the form consumed by the
existing compiler chain. -/
theorem sourceToChecker
    {checker : NativeCheckerSemantics}
    (certificate : Certificate checker) :
    BehaviorRefines
      certificate.program.successBehavior checker.accepts :=
  certificate.refinement.behaviorRefinement

/-- Successful evaluation of the certified deterministic program satisfies
the fixed checker. -/
theorem accepts
    {checker : NativeCheckerSemantics}
    (certificate : Certificate checker)
    {inputBytes outputBytes : ByteArray}
    (returned :
      certificate.program.run inputBytes = .returned outputBytes) :
    checker.accepts inputBytes outputBytes :=
  certificate.refinement.accepts returned

end Certificate

end SparkInterval.Execution.Architecture.DeterministicFinalizerIR
