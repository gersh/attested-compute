import SparkInterval.Certified.LambdaEval
import SparkInterval.Certified.Sqrt

/-! Type-level regression tests for the certified evaluation layer. -/

set_option autoImplicit false

namespace SparkInterval.Tests.CertifiedEval

open SparkInterval.Certified
open SparkInterval.Certificate

example (prec : ℕ) {x : ℚ} (hx : 0 ≤ x) :
    (sqrtInterval prec x).ContainsReal (Real.sqrt (x : ℝ)) :=
  sqrtInterval_containsReal prec hx

example {terms k prec : ℕ} (ht : 0 < terms) {x : ℚ} (hx : 0 < x)
    {I : RatInterval} (h : logInterval terms k prec x = some I) :
    I.ContainsReal (Real.log (x : ℝ)) :=
  logInterval_containsReal ht hx h

example {depth prec : ℕ} {x : ℚ} {S C : RatInterval}
    (h : sinCosQ depth prec x = some (S, C)) :
    S.ContainsReal (Real.sin (x : ℝ)) ∧ C.ContainsReal (Real.cos (x : ℝ)) :=
  sinCosQ_containsReal h

example {p : EvalParams} {r c t : ℚ} {R : ComplexRect}
    (h : rpowNegEval p r c t = some R) :
    R.ContainsComplex
      (((r : ℚ) : ℂ) ^ (-(((c : ℚ) : ℂ) + ((t : ℚ) : ℂ) * Complex.I))) :=
  rpowNegEval_containsComplex h

example {p : EvalParams} {α t : ℚ} {M : ℕ} {R : ComplexRect}
    (h : mainSumEval p α t M = some R) :
    R.ContainsComplex
      (hurwitzMain α M ((1 : ℂ) / 2 + ((t : ℚ) : ℂ) * Complex.I)) :=
  mainSumEval_containsComplex h

-- The analytic premises are consumable Props with the expected shapes.
example (hP1 : EulerMaclaurinHurwitzBound) (t : ℝ) :
    ‖HurwitzZeta.hurwitzZeta ((((1 : ℚ) / 4 : ℚ) : ℝ) : UnitAddCircle)
        (1 / 2 + t * Complex.I) -
      hurwitzMain (1 / 4) 64 (1 / 2 + t * Complex.I) -
      hurwitzTail (1 / 4) 64 10 (1 / 2 + t * Complex.I)‖ ≤
      hurwitzTailError (1 / 4) 64 10 (1 / 2 + t * Complex.I) :=
  hP1 (1 / 4) (by norm_num) (by norm_num) 64 10 (by norm_num) (by norm_num)
    (by norm_num) t

end SparkInterval.Tests.CertifiedEval
