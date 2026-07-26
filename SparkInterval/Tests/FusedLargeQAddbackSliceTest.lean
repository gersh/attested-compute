import SparkInterval.SASS.FusedLargeQAddbackSlice

/-!
# Regression tests for the fused large-q post-compilation slice

The positive tests exercise the closed CUDA 13.0 artifact record and the
generic operand-commutation path.  Negative tests show that changing a
rounding mode or a source register makes the checker fail.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.FusedLargeQAddbackSlice

open SparkInterval.SASS.SM90

example : fusedLargeQFinalImaginaryAddbackCertificate.check = true :=
  fusedLargeQFinalImaginaryAddbackCertificate_check

example : fusedLargeQFinalImaginaryAddbackCertificate.canonicalExcerpt =
    "/*3840*/ DADD.RM R12, R12, R22 ;\n" ++
    "/*3850*/ DADD.RP R10, R10, R20 ;\n" := by
  rfl

example : fusedLargeQFinalImaginaryAddbackSlice.RefinesIntervalAdd :=
  fusedLargeQFinalImaginaryAddback_refinesIntervalAdd

/-- Commuting the two sources is accepted only when the certificate records
the commutation explicitly. -/
private def swappedSlice : AddSlice := {
  lowerOffset := "0010"
  upperOffset := "0020"
  instructions := [
    { offset := "0010", rounding := .rm, destination := 8,
      left := 4, right := 2 },
    { offset := "0020", rounding := .rp, destination := 10,
      left := 6, right := 12 }
  ]
  left := { lo := 2, hi := 6 }
  right := { lo := 4, hi := 12 }
  result := { lo := 8, hi := 10 }
  lowerOperandsSwapped := true
}

example : swappedSlice.check = true := by decide

example : swappedSlice.RefinesIntervalAdd :=
  AddSlice.check_refinesIntervalAdd (by decide)

private def wrongRounding : AddSlice := {
  fusedLargeQFinalImaginaryAddbackSlice with
  instructions := [
    { offset := "3840", rounding := .rm, destination := 12,
      left := 12, right := 22 },
    { offset := "3850", rounding := .rm, destination := 10,
      left := 10, right := 20 }
  ]
}

private def wrongOperand : AddSlice := {
  fusedLargeQFinalImaginaryAddbackSlice with
  instructions := [
    { offset := "3840", rounding := .rm, destination := 12,
      left := 12, right := 24 },
    { offset := "3850", rounding := .rp, destination := 10,
      left := 10, right := 20 }
  ]
}

example : wrongRounding.check = false := by decide
example : wrongOperand.check = false := by decide

#print axioms SparkInterval.SASS.SM90.AddSlice.check_refinesIntervalAdd
#print axioms SparkInterval.SASS.SM90.fusedLargeQFinalImaginaryAddbackCertificate_check
#print axioms SparkInterval.SASS.SM90.fusedLargeQFinalImaginaryAddback_refinesIntervalAdd
#print axioms SparkInterval.SASS.SM90.fusedLargeQFinalImaginaryAddback_contains
#print axioms SparkInterval.Execution.SignedResultCertificate.outcomeCheckForRegisteredInvocationAndFusedLargeQSlice_sound

end SparkInterval.Tests.FusedLargeQAddbackSlice
