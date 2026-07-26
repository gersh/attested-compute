/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.R2StarSourceSemantics

set_option autoImplicit false

namespace SparkInterval.Tests.R2StarSourceSemanticsTest

open SparkInterval.TernaryGoldbach.R2StarSourceSemantics

private def sampleChunk : Chunk := {
  lower := 1
  upper := 4
  incoming := State.zero
  outgoing := State.zero
  minimumSquaredSlack := 0
  minimumSlackIndex := 3
}

private def sampleCertificate : Certificate := {
  sourceLower := 1
  sourceUpper := 4
  rootState := State.zero
  finalState := State.zero
  chunks := [sampleChunk]
}

example : sampleCertificate.check = true := by native_decide

example : sampleCertificate.ArithmeticValid :=
  Certificate.checker_sound (by native_decide)

example (n : Nat) :
    r2Star (n + 1) = r2Star n + r2Coeff (n + 1) := r2Star_succ n

#print axioms Certificate.checker_sound
#print axioms r2Star_succ
#print axioms sourceClaim_of_checked_certificate

end SparkInterval.Tests.R2StarSourceSemanticsTest

