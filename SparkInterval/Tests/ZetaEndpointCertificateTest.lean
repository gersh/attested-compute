import SparkInterval.Zeta.EndpointCertificate

/-! Kernel-checked regression tests for executable endpoint-sign data. -/

set_option autoImplicit false

namespace SparkInterval.Tests.ZetaEndpointCertificate

open SparkInterval.Certificate
open SparkInterval.Zeta

private def identityBracket : RationalBracket := {
  lower := -1
  upper := 1
  lowerValue := ⟨-1, -1⟩
  upperValue := ⟨1, 1⟩
}

private def identityFamily : RationalBracketFamily 1 := {
  entries := fun _ => identityBracket
}

example : identityBracket.check = true := by decide

example : identityFamily.check = true := by decide

example : identityBracket.EnclosesEndpoints (fun x : ℝ => x) := by
  constructor <;> constructor <;> norm_num [identityBracket, RatInterval.ContainsReal]

example :
    ∃ certificate : ZeroCertificate (fun x : ℝ => x) 1,
      Nonempty certificate.RootSelection := by
  apply identityFamily.exists_rootSelection
  · decide
  · intro i
    fin_cases i
    constructor <;> constructor <;>
      norm_num [identityFamily, identityBracket, RatInterval.ContainsReal]
  · exact continuous_id

end SparkInterval.Tests.ZetaEndpointCertificate
