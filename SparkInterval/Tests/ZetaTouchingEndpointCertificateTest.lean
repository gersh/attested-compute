import SparkInterval.Zeta.TouchingEndpointCertificate

/-! Kernel-checked regression tests for strict brackets sharing an endpoint. -/

set_option autoImplicit false

namespace SparkInterval.Tests.ZetaTouchingEndpointCertificate

open SparkInterval.Certificate
open SparkInterval.Zeta

private def left : RationalBracket := {
  lower := -2
  upper := 0
  lowerValue := ⟨3, 3⟩
  upperValue := ⟨-1, -1⟩
}

private def right : RationalBracket := {
  lower := 0
  upper := 2
  lowerValue := ⟨-1, -1⟩
  upperValue := ⟨3, 3⟩
}

private def touchingFamily : TouchingRationalBracketFamily 2 := {
  entries := ![left, right]
}

example : touchingFamily.check = true := by decide

example : not (({
    entries := ![left, right]
  } : RationalBracketFamily 2).check = true) := by decide

private def twoInteriorRoots (x : Real) : Real :=
  (x + 1) * (x - 1)

private theorem twoInteriorRoots_continuous : Continuous twoInteriorRoots := by
  unfold twoInteriorRoots
  fun_prop

example :
    exists certificate : TouchingZeroCertificate twoInteriorRoots 2,
      Nonempty certificate.RootSelection := by
  apply touchingFamily.exists_rootSelection
  · decide
  · intro i
    fin_cases i <;> constructor <;> constructor <;>
      norm_num [touchingFamily, left, right, twoInteriorRoots,
        RatInterval.ContainsReal]
  · exact twoInteriorRoots_continuous

end SparkInterval.Tests.ZetaTouchingEndpointCertificate
