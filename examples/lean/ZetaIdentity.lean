import Mathlib.NumberTheory.LSeries.HurwitzZetaValues

/-!
Mathlib's exact identity is the mathematical endpoint used to sanity-check the
small `zeta(2)` tutorial. It does not connect the external GPU wire format to
Lean; that decoder/refinement bridge remains separate work.
-/

namespace SparkInterval.Examples

example : riemannZeta (2 : ℂ) = (Real.pi : ℂ) ^ 2 / 6 :=
  riemannZeta_two

end SparkInterval.Examples
