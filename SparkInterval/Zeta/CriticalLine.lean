import Mathlib.NumberTheory.LSeries.ZetaZeros

/-!
# Finite-height Riemann-zeta zero target

This file states the exact downstream theorem a future checked Hardy-Z/Turing
certificate must establish.  Mathlib already proves that zeta zeros in every
compact region form a finite set.  Consequently, equality between the number
of distinct zeros in a compact region and the number lying on the critical
line forces every zero in that region onto the critical line.

The theorem is axiom-free.  It does not manufacture the count equality: that
is the still-missing analytic soundness theorem for the executable zero
certificate.  It also counts distinct points, not analytic multiplicity.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open Set

/-- Zeros of Mathlib's `riemannZeta` restricted to an explicit region. -/
def zetaZerosIn (region : Set ℂ) : Set ℂ :=
  region ∩ riemannZetaZeros

/-- The critical line `re s = 1/2`. -/
def criticalLine : Set ℂ :=
  {z | z.re = (1 : ℝ) / 2}

/-- Zeros in a region that lie on the critical line. -/
def criticalLineZerosIn (region : Set ℂ) : Set ℂ :=
  zetaZerosIn region ∩ criticalLine

/-- The closed critical-strip rectangle through absolute height `height`.  It
is compact for every real height; for negative height it is simply empty. -/
def criticalRectangle (height : ℝ) : Set ℂ :=
  Set.Icc (0 : ℝ) 1 ×ℂ Set.Icc (-height) height

@[simp] theorem mem_criticalRectangle {height : ℝ} {z : ℂ} :
    z ∈ criticalRectangle height ↔
      0 ≤ z.re ∧ z.re ≤ 1 ∧ -height ≤ z.im ∧ z.im ≤ height := by
  simp [criticalRectangle, Complex.mem_reProdIm, and_assoc]

theorem isCompact_criticalRectangle (height : ℝ) :
    IsCompact (criticalRectangle height) := by
  exact isCompact_Icc.reProdIm isCompact_Icc

/-- Mathlib's discreteness theorem makes the zeta-zero set finite in every
compact certificate region. -/
theorem zetaZerosIn_finite {region : Set ℂ} (hregion : IsCompact region) :
    (zetaZerosIn region).Finite := by
  exact hregion.inter_riemannZetaZeros_finite

theorem criticalLineZerosIn_subset (region : Set ℂ) :
    criticalLineZerosIn region ⊆ zetaZerosIn region :=
  Set.inter_subset_left

/-- Equal distinct-zero counts force all zeros in the compact region onto the
critical line.  The future Turing/argument-principle checker must provide
`hcount`; the finite-set deduction itself is completely proved here. -/
theorem zetaZerosIn_eq_criticalLine_of_ncard_eq
    {region : Set ℂ} (hregion : IsCompact region)
    (hcount :
      (criticalLineZerosIn region).ncard = (zetaZerosIn region).ncard) :
    zetaZerosIn region = criticalLineZerosIn region := by
  symm
  exact Set.eq_of_subset_of_ncard_le
    (criticalLineZerosIn_subset region) hcount.symm.le
    (zetaZerosIn_finite hregion)

/-- Pointwise finite-region Riemann-hypothesis consequence of the checked count
equality. -/
theorem all_region_zeros_on_criticalLine_of_ncard_eq
    {region : Set ℂ} (hregion : IsCompact region)
    (hcount :
      (criticalLineZerosIn region).ncard = (zetaZerosIn region).ncard) :
    ∀ z ∈ region, riemannZeta z = 0 → z.re = (1 : ℝ) / 2 := by
  have heq := zetaZerosIn_eq_criticalLine_of_ncard_eq hregion hcount
  intro z hzregion hzero
  have hz : z ∈ zetaZerosIn region := ⟨hzregion, hzero⟩
  rw [heq] at hz
  exact hz.2

/-- The explicit high-bound target theorem for the closed critical rectangle. -/
theorem all_zeros_to_height_on_criticalLine
    {height : ℝ}
    (hcount :
      (criticalLineZerosIn (criticalRectangle height)).ncard =
        (zetaZerosIn (criticalRectangle height)).ncard) :
    ∀ z ∈ criticalRectangle height,
      riemannZeta z = 0 → z.re = (1 : ℝ) / 2 :=
  all_region_zeros_on_criticalLine_of_ncard_eq
    (isCompact_criticalRectangle height) hcount

end SparkInterval.Zeta
