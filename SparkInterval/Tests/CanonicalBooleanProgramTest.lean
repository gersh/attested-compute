/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CanonicalBooleanProgram

set_option autoImplicit false

namespace SparkInterval.Tests.CanonicalBooleanProgram

open SparkInterval.Execution.Architecture
open
  SparkInterval.Execution.Architecture.CanonicalBooleanProgram
open
  SparkInterval.Execution.Architecture.DeterministicFinalizerIR

private def inputBytes : ByteArray :=
  "input".toUTF8

private def resultBytes : ByteArray :=
  "accepted".toUTF8

private def checker : NativeCheckerSemantics where
  checkerId := "sparkinterval.tests.canonical-boolean-program.v1"
  accepts := fun input result =>
    input = inputBytes ∧ result = resultBytes

private theorem trueCheckSound :
    true = true →
      checker.accepts inputBytes resultBytes := by
  intro _checked
  exact ⟨rfl, rfl⟩

example :
    (certificate checker inputBytes resultBytes true
      trueCheckSound).program.run inputBytes =
        .returned resultBytes := by
  simp [certificate, program, run]

example :
    (certificate checker inputBytes resultBytes true
      trueCheckSound).program.run "wrong".toUTF8 =
        .rejected inputRejectedCode := by
  have different : "wrong".toUTF8 ≠ inputBytes := by
    unfold inputBytes
    decide
  change
    run inputBytes resultBytes true "wrong".toUTF8 =
      .rejected inputRejectedCode
  simp only [run, different, if_false]

example (arbitraryInput : ByteArray) :
    run inputBytes resultBytes false arbitraryInput ≠
      .returned resultBytes := by
  by_cases canonical : arbitraryInput = inputBytes <;>
    simp [run, canonical]

#print axioms returned_iff
#print axioms refinesNativeChecker
#print axioms certificate

end SparkInterval.Tests.CanonicalBooleanProgram
