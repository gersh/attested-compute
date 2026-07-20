import SparkInterval.Zeta.HardyZContract

/-! Type-level regression tests for the Hardy-Z zero-equivalence contract. -/

set_option autoImplicit false

namespace SparkInterval.Tests.ZetaHardyZContract

open SparkInterval.Zeta

example {f : ℝ → ℝ} {height : ℝ} (model : HardyZModel f height) :
    CriticalLineZeroBridge f height :=
  model.criticalLineZeroBridge

example {f : ℝ → ℝ} {height : ℝ} (model : HardyZModel f height)
    {t : ℝ} (ht : t ∈ heightDomain height) :
    f t = 0 ↔ riemannZeta (criticalPoint t) = 0 :=
  model.zero_iff ht

example {f : ℝ → ℝ} {height : ℝ} {count : Nat}
    (model : HardyZModel f height)
    (family : RationalBracketFamily count)
    (hcheck : family.check = true)
    (hencloses : ∀ i, (family.entries i).EnclosesEndpoints f)
    (hlower : ∀ i, -height ≤ ((family.entries i).lower : ℝ))
    (hupper : ∀ i, ((family.entries i).upper : ℝ) ≤ height)
    (totalUpper : ZetaZeroCountUpperBound height count) :
    ∀ z ∈ criticalRectangle height,
      riemannZeta z = 0 → z.re = (1 : ℝ) / 2 :=
  model.verifyEndpointFamily family hcheck hencloses hlower hupper totalUpper

end SparkInterval.Tests.ZetaHardyZContract
