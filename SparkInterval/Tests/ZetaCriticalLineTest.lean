import SparkInterval.Zeta.CriticalLine

/-! Type-level regression tests for the finite-height zeta target theorem. -/

set_option autoImplicit false

namespace SparkInterval.Tests.ZetaCriticalLine

open SparkInterval.Zeta

example (height : ℝ) : IsCompact (criticalRectangle height) :=
  isCompact_criticalRectangle height

example {height : ℝ}
    (hcount :
      (criticalLineZerosIn (criticalRectangle height)).ncard =
        (zetaZerosIn (criticalRectangle height)).ncard) :
    ∀ z ∈ criticalRectangle height,
      riemannZeta z = 0 → z.re = (1 : ℝ) / 2 :=
  all_zeros_to_height_on_criticalLine hcount

end SparkInterval.Tests.ZetaCriticalLine
