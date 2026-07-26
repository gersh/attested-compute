/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.DeterministicFinalizerIR

/-!
# Canonical Boolean certificate-finalizer program

This module implements the common small finalizer used after a heavy cloud
producer has generated or checked campaign evidence.  The source program:

1. rejects every input except one exact canonical byte string;
2. evaluates one fixed Boolean certificate check;
3. returns one exact canonical result only when that check is true; and
4. rejects otherwise with distinct input/check failure codes.

`certificate` requires an ordinary theorem that a true Boolean check implies
acceptance by one fixed `NativeCheckerSemantics`.  Consequently the program
cannot turn a success byte, hash, receipt, or arbitrary proposition into a
checker acceptance.

The implementation and proof are source-level.  They do not assert that any
C, ELF, x86-64, CPU, PTX, SASS, or GPU implementation evaluates `check`, and
they introduce no receipt or execution axiom.
-/

set_option autoImplicit false

namespace
  SparkInterval.Execution.Architecture.CanonicalBooleanProgram

open DeterministicFinalizerIR

/-- Rejection code for a non-canonical complete input. -/
def inputRejectedCode : Nat :=
  1

/-- Rejection code for a canonical input whose certificate check failed. -/
def checkRejectedCode : Nat :=
  2

/-- Total deterministic finalizer for one exact Boolean check. -/
def run
    (canonicalInput canonicalResult : ByteArray)
    (check : Bool)
    (inputBytes : ByteArray) :
    Outcome :=
  if inputBytes = canonicalInput then
    if check then
      .returned canonicalResult
    else
      .rejected checkRejectedCode
  else
    .rejected inputRejectedCode

/-- Source program bound to the selected native checker's identifier. -/
def program
    (checker : NativeCheckerSemantics)
    (canonicalInput canonicalResult : ByteArray)
    (check : Bool) :
    Program where
  contractId := checker.checkerId
  run := run canonicalInput canonicalResult check

/-- Exact characterization of the only successful program behavior. -/
theorem returned_iff
    (canonicalInput canonicalResult : ByteArray)
    (check : Bool)
    (inputBytes outputBytes : ByteArray) :
    run canonicalInput canonicalResult check inputBytes =
        .returned outputBytes ↔
      inputBytes = canonicalInput ∧
        check = true ∧
        outputBytes = canonicalResult := by
  by_cases inputCanonical : inputBytes = canonicalInput
  · cases check <;>
      simp [run, inputCanonical, eq_comm]
  · simp [run, inputCanonical]

/-- Program-to-checker refinement from a campaign's ordinary Boolean
soundness theorem. -/
theorem refinesNativeChecker
    (checker : NativeCheckerSemantics)
    (canonicalInput canonicalResult : ByteArray)
    (check : Bool)
    (sound :
      check = true →
        checker.accepts canonicalInput canonicalResult) :
    RefinesNativeChecker
      (program checker canonicalInput canonicalResult check)
      checker := by
  refine
    { contractId := rfl
      successful := ?_ }
  intro inputBytes outputBytes returned
  have exactRun :=
    (returned_iff canonicalInput canonicalResult check
      inputBytes outputBytes).mp returned
  rcases exactRun with
    ⟨inputCanonical, checkSucceeded, outputCanonical⟩
  subst inputBytes
  subst outputBytes
  exact sound checkSucceeded

/-- Concrete source-program certificate assembled from a fixed Boolean
checker and its ordinary soundness theorem. -/
def certificate
    (checker : NativeCheckerSemantics)
    (canonicalInput canonicalResult : ByteArray)
    (check : Bool)
    (sound :
      check = true →
        checker.accepts canonicalInput canonicalResult) :
    Certificate checker where
  program :=
    program checker canonicalInput canonicalResult check
  refinement :=
    refinesNativeChecker
      checker canonicalInput canonicalResult check sound

end SparkInterval.Execution.Architecture.CanonicalBooleanProgram
