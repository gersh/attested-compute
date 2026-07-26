/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.FixedDecisionProgram

/-!
# Symbolic fixed-decision program tests

These tests instantiate the reusable source program with small opaque
propositions.  The negative case confirms rejection; the positive case
confirms the exact output and claim reflection.  No architecture or receipt
boundary is imported.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.FixedDecisionProgram

open SparkInterval.Execution.Architecture
open
  SparkInterval.Execution.Architecture.DeterministicFinalizerIR
open
  SparkInterval.Execution.Architecture.FixedDecisionProgram

private def checkerId : String :=
  "sparkinterval.tests.fixed-decision-program.v1"

private def successResult : ByteArray :=
  "accepted".toUTF8

private def trueClaim : Prop :=
  6 * 7 = 42

private instance : Decidable trueClaim := by
  unfold trueClaim
  infer_instance

private def falseClaim : Prop :=
  6 * 7 = 41

private instance : Decidable falseClaim := by
  unfold falseClaim
  infer_instance

example (inputBytes : ByteArray) :
    run trueClaim successResult inputBytes =
      .returned successResult := by
  apply run_of_decide_eq_true
  decide

example (inputBytes : ByteArray) :
    run falseClaim successResult inputBytes =
      .rejected decisionRejectedCode := by
  apply run_of_decide_ne_true
  decide

example :
    Certificate
      (FixedDecisionChecker.nativeChecker
        trueClaim checkerId successResult) :=
  certificate trueClaim checkerId successResult

example (inputBytes : ByteArray) :
    trueClaim := by
  apply
    claim_of_returned trueClaim checkerId successResult
      inputBytes successResult
  exact run_of_decide_eq_true
    trueClaim successResult inputBytes (by decide)

#print axioms returned_iff
#print axioms refinesNativeChecker
#print axioms certificate
#print axioms claim_of_returned

end SparkInterval.Tests.FixedDecisionProgram
