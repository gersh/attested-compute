import SparkInterval.Zeta.MultiplicityCount

/-! Regression tests for multiplicity-aware finite-height count handoff. -/

set_option autoImplicit false

namespace SparkInterval.Tests.ZetaMultiplicityCount

open SparkInterval.Zeta

example {z : ℂ} (hz : z ∈ riemannZetaZeros) :
    (1 : ℕ∞) ≤ zetaZeroMultiplicity z :=
  one_le_zetaZeroMultiplicity hz

example (height : ℝ) :
    ((zetaZerosIn (criticalRectangle height)).ncard : ℕ∞) ≤
      zetaZeroMultiplicityCount height :=
  coe_ncard_le_zetaZeroMultiplicityCount height

example {height : ℝ} {bound : Nat}
    (upper : ZetaMultiplicityCountUpperBound height bound) :
    ZetaZeroCountUpperBound height bound :=
  upper.toZetaZeroCountUpperBound

private def acceptedCertificate : ZetaMultiplicityCountCertificate := {
  claimedMultiplicityCount := 10
  upperBound := 12
}

private def rejectedCertificate : ZetaMultiplicityCountCertificate := {
  claimedMultiplicityCount := 13
  upperBound := 12
}

example : acceptedCertificate.check = true := by
  decide

example : rejectedCertificate.check = false := by
  decide

example {height : ℝ}
    (analyticUpper : ZetaMultiplicityCountUpperBound height 10) :
    ZetaZeroCountUpperBound height 12 := by
  exact acceptedCertificate.check_sound (by decide) analyticUpper

end SparkInterval.Tests.ZetaMultiplicityCount
