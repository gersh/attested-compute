/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.DeterministicFinalizerIR
import SparkInterval.Execution.FixedDecisionChecker

/-!
# Deterministic program for one fixed decidable proposition

This module gives the first concrete source-program certificate for the
deterministic-finalizer layer.  The program fixes one proposition, its
`Decidable` instance, checker identifier, and success bytes.  On every input
it:

* returns exactly the fixed success bytes when `decide Claim = true`; and
* otherwise returns an explicit rejection.

The refinement proof is symbolic.  It splits on `decide Claim = true` and
never evaluates the selected decision procedure.  Thus instantiating this
program with a large finite computation does not replay that computation
during elaboration.

This is only a source-level `DeterministicFinalizerIR.Certificate`.  It
contains no executable image, compiler theorem, loader theorem, ISA theorem,
architecture claim, receipt, signature, or axiom.
-/

set_option autoImplicit false

namespace
  SparkInterval.Execution.Architecture.FixedDecisionProgram

open DeterministicFinalizerIR

/-- Stable rejection code used when the fixed proposition decides to false. -/
def decisionRejectedCode : Nat :=
  1

/-- Total byte-program evaluation for one fixed decidable proposition.

The input bytes are intentionally ignored because
`FixedDecisionChecker.nativeChecker` also treats them as opaque.  Checkers
whose source contract requires a canonical input need a separate
input-decoding program and proof. -/
def run
    (Claim : Prop) [Decidable Claim]
    (successResult : ByteArray)
    (_inputBytes : ByteArray) :
    Outcome :=
  if decide Claim then
    .returned successResult
  else
    .rejected decisionRejectedCode

/-- The deterministic source program, bound to the same identifier as its
fixed native checker. -/
def program
    (Claim : Prop) [Decidable Claim]
    (checkerId : String)
    (successResult : ByteArray) :
    Program where
  contractId := checkerId
  run := run Claim successResult

/-- The true decision branch returns exactly the fixed success bytes. -/
theorem run_of_decide_eq_true
    (Claim : Prop) [Decidable Claim]
    (successResult inputBytes : ByteArray)
    (accepted : decide Claim = true) :
    run Claim successResult inputBytes =
      .returned successResult := by
  simp [run, accepted]

/-- The false decision branch rejects with the fixed rejection code. -/
theorem run_of_decide_ne_true
    (Claim : Prop) [Decidable Claim]
    (successResult inputBytes : ByteArray)
    (rejected : decide Claim ≠ true) :
    run Claim successResult inputBytes =
      .rejected decisionRejectedCode := by
  simp [run, rejected]

/-- Exact symbolic characterization of every successful program result. -/
theorem returned_iff
    (Claim : Prop) [Decidable Claim]
    (successResult inputBytes outputBytes : ByteArray) :
    run Claim successResult inputBytes = .returned outputBytes ↔
      decide Claim = true ∧ outputBytes = successResult := by
  by_cases decided : decide Claim = true
  · simp [run, decided, eq_comm]
  · simp [run, decided]

/-- Ordinary source-program refinement for the fixed decision checker.

This proof does not evaluate `decide Claim`: the two decision branches are
handled propositionally. -/
theorem refinesNativeChecker
    (Claim : Prop) [Decidable Claim]
    (checkerId : String)
    (successResult : ByteArray) :
    RefinesNativeChecker
      (program Claim checkerId successResult)
      (FixedDecisionChecker.nativeChecker
        Claim checkerId successResult) := by
  refine
    { contractId := rfl
      successful := ?_ }
  intro inputBytes outputBytes returned
  change outputBytes = successResult ∧ decide Claim = true
  have exactResult :
      decide Claim = true ∧ outputBytes = successResult := by
    exact
      (returned_iff
        Claim successResult inputBytes outputBytes).mp returned
  exact ⟨exactResult.2, exactResult.1⟩

/-- A concrete deterministic-program certificate for every fixed decidable
claim checker.

Constructing this value is constant-time symbolic elaboration even when the
selected `Decidable` procedure represents a large finite computation. -/
def certificate
    (Claim : Prop) [Decidable Claim]
    (checkerId : String)
    (successResult : ByteArray) :
    Certificate
      (FixedDecisionChecker.nativeChecker
        Claim checkerId successResult) where
  program := program Claim checkerId successResult
  refinement :=
    refinesNativeChecker Claim checkerId successResult

/-- A successful run of the certified program exposes the fixed claim via
the existing checker reflection theorem. -/
theorem claim_of_returned
    (Claim : Prop) [Decidable Claim]
    (checkerId : String)
    (successResult inputBytes outputBytes : ByteArray)
    (returned :
      (certificate Claim checkerId successResult).program.run
        inputBytes = .returned outputBytes) :
    Claim :=
  FixedDecisionChecker.claim_of_acceptance
    Claim checkerId successResult inputBytes outputBytes
      ((certificate Claim checkerId successResult).accepts returned)

end SparkInterval.Execution.Architecture.FixedDecisionProgram
