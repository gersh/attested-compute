import SparkInterval.Certified.Complex
import Mathlib.Analysis.SpecialFunctions.Complex.Log
import Mathlib.Analysis.SpecialFunctions.Pow.Complex

/-!
# Complex power of a positive rational base from real enclosures

The Dirichlet main sums and Euler-Maclaurin tails evaluate powers
`r ^ (-(c + i t))` for positive rational `r` and rational `c, t`.  This
file proves the decomposition

`r ^ (-(c + i t)) = exp (-c log r) * (cos (t log r) - i sin (t log r))`

and packages it as a containment rule: rational-interval enclosures of the
three real ingredients `exp (-c log r)`, `sin (t log r)`, `cos (t log r)`
yield a `ComplexRect` enclosure of the complex power.  The certified
elementary-function layer supplies those ingredient enclosures.
-/

set_option autoImplicit false

namespace SparkInterval.Certified

open SparkInterval.Certificate

/-- Decomposition of a complex power of a positive real base into real
exponential and trigonometric parts. -/
theorem cpow_neg_add_mul_I (r : ℝ) (hr : 0 < r) (c t : ℝ) :
    (r : ℂ) ^ (-((c : ℂ) + (t : ℂ) * Complex.I)) =
      ((Real.exp (-c * Real.log r) : ℝ) : ℂ) *
        (((Real.cos (t * Real.log r) : ℝ) : ℂ) -
          ((Real.sin (t * Real.log r) : ℝ) : ℂ) * Complex.I) := by
  have hr0 : (r : ℂ) ≠ 0 := by
    exact_mod_cast ne_of_gt hr
  rw [Complex.cpow_def_of_ne_zero hr0]
  rw [← Complex.ofReal_log hr.le]
  set L := Real.log r with hL
  have hexp : (L : ℂ) * -((c : ℂ) + (t : ℂ) * Complex.I) =
      ((-c * L : ℝ) : ℂ) + ((-(t * L) : ℝ) : ℂ) * Complex.I := by
    push_cast
    ring
  rw [hexp, Complex.exp_add, Complex.exp_mul_I]
  rw [← Complex.ofReal_exp]
  have hcos : Complex.cos ((-(t * L) : ℝ) : ℂ) =
      ((Real.cos (t * L) : ℝ) : ℂ) := by
    rw [← Complex.ofReal_cos]
    norm_num
  have hsin : Complex.sin ((-(t * L) : ℝ) : ℂ) =
      -((Real.sin (t * L) : ℝ) : ℂ) := by
    rw [← Complex.ofReal_sin]
    push_cast
    norm_num
  rw [hcos, hsin]
  ring

/-- Interval enclosures of the three real ingredients yield a rectangle
enclosure of `r ^ (-(c + i t))` for a positive rational base. -/
theorem contains_cpow_of_contains
    {r c t : ℚ} (hr : 0 < r)
    {A S C : RatInterval}
    (hA : A.ContainsReal (Real.exp (-(c : ℝ) * Real.log (r : ℝ))))
    (hS : S.ContainsReal (Real.sin ((t : ℝ) * Real.log (r : ℝ))))
    (hC : C.ContainsReal (Real.cos ((t : ℝ) * Real.log (r : ℝ)))) :
    (ComplexRect.scale A ⟨C, S.neg⟩).ContainsComplex
      (((r : ℚ) : ℂ) ^ (-(((c : ℚ) : ℂ) + ((t : ℚ) : ℂ) * Complex.I))) := by
  have hr' : (0 : ℝ) < (r : ℝ) := by exact_mod_cast hr
  have hcast : (((r : ℚ) : ℂ)) = (((r : ℚ) : ℝ) : ℂ) := by
    push_cast
    rfl
  have hcastc : (((c : ℚ) : ℂ)) = (((c : ℚ) : ℝ) : ℂ) := by
    push_cast
    rfl
  have hcastt : (((t : ℚ) : ℂ)) = (((t : ℚ) : ℝ) : ℂ) := by
    push_cast
    rfl
  rw [hcast, hcastc, hcastt, cpow_neg_add_mul_I (r : ℝ) hr' (c : ℝ) (t : ℝ)]
  apply ComplexRect.scale_containsComplex hA
  constructor
  · have hre :
        ((((Real.cos ((t : ℝ) * Real.log (r : ℝ))) : ℝ) : ℂ) -
          (((Real.sin ((t : ℝ) * Real.log (r : ℝ))) : ℝ) : ℂ) *
            Complex.I).re =
          Real.cos ((t : ℝ) * Real.log (r : ℝ)) := by
      simp [← Complex.ofReal_mul, Complex.cos_ofReal_re, Complex.sin_ofReal_im]
    rw [hre]
    exact hC
  · have him :
        ((((Real.cos ((t : ℝ) * Real.log (r : ℝ))) : ℝ) : ℂ) -
          (((Real.sin ((t : ℝ) * Real.log (r : ℝ))) : ℝ) : ℂ) *
            Complex.I).im =
          -Real.sin ((t : ℝ) * Real.log (r : ℝ)) := by
      simp [← Complex.ofReal_mul, Complex.cos_ofReal_im, Complex.sin_ofReal_re]
    rw [him]
    exact RatInterval.neg_containsReal hS

end SparkInterval.Certified
