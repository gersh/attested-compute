import SparkInterval.Dirichlet.LZeros
import SparkInterval.Zeta.CriticalLine

/-!
# Finite-strip Dirichlet L-function zero target

Dirichlet analogue of `SparkInterval.Zeta.CriticalLine`, stated for the
closed rectangle `[0, 1] x [lo, hi]` with explicit lower and upper
ordinates.  Platt's GRH computation (arXiv:1305.3087) scans `t ∈ [0, t₀]`
for every primitive character and covers negative ordinates through the
conjugate character, so the verified region is naturally one-sided per
character; the aggregate over a conjugation-closed character family then
covers the symmetric strip.

Equality between the number of distinct zeros in the compact rectangle and
the number of those zeros on the critical line forces every zero in the
rectangle onto the critical line.  The deduction is axiom-free; the count
equality is the analytic obligation of a future Turing-method checker.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet

open Set DirichletCharacter

variable {N : ℕ} [NeZero N]

/-- The closed critical-strip rectangle `[0,1] x [lo,hi]`. -/
def criticalStrip (lo hi : ℝ) : Set ℂ :=
  Set.Icc (0 : ℝ) 1 ×ℂ Set.Icc lo hi

@[simp] theorem mem_criticalStrip {lo hi : ℝ} {z : ℂ} :
    z ∈ criticalStrip lo hi ↔
      0 ≤ z.re ∧ z.re ≤ 1 ∧ lo ≤ z.im ∧ z.im ≤ hi := by
  simp [criticalStrip, Complex.mem_reProdIm, and_assoc]

theorem isCompact_criticalStrip (lo hi : ℝ) :
    IsCompact (criticalStrip lo hi) :=
  isCompact_Icc.reProdIm isCompact_Icc

/-- Zeros of `χ.LFunction` restricted to an explicit region. -/
def LZerosIn (χ : DirichletCharacter ℂ N) (region : Set ℂ) : Set ℂ :=
  region ∩ LZeros χ

/-- Zeros in a region that lie on the critical line. -/
def criticalLineLZerosIn (χ : DirichletCharacter ℂ N) (region : Set ℂ) :
    Set ℂ :=
  LZerosIn χ region ∩ Zeta.criticalLine

theorem LZerosIn_finite {χ : DirichletCharacter ℂ N} (hχ : χ ≠ 1)
    {region : Set ℂ} (hregion : IsCompact region) :
    (LZerosIn χ region).Finite :=
  inter_LZeros_finite hregion hχ

theorem criticalLineLZerosIn_subset (χ : DirichletCharacter ℂ N)
    (region : Set ℂ) :
    criticalLineLZerosIn χ region ⊆ LZerosIn χ region :=
  Set.inter_subset_left

/-- Equal distinct-zero counts force all zeros in the compact region onto
the critical line. -/
theorem LZerosIn_eq_criticalLine_of_ncard_eq
    {χ : DirichletCharacter ℂ N} (hχ : χ ≠ 1)
    {region : Set ℂ} (hregion : IsCompact region)
    (hcount :
      (criticalLineLZerosIn χ region).ncard = (LZerosIn χ region).ncard) :
    LZerosIn χ region = criticalLineLZerosIn χ region := by
  symm
  exact Set.eq_of_subset_of_ncard_le
    (criticalLineLZerosIn_subset χ region) hcount.symm.le
    (LZerosIn_finite hχ hregion)

/-- Pointwise finite-region GRH consequence of the checked count equality. -/
theorem all_region_zeros_on_criticalLine_of_ncard_eq
    {χ : DirichletCharacter ℂ N} (hχ : χ ≠ 1)
    {region : Set ℂ} (hregion : IsCompact region)
    (hcount :
      (criticalLineLZerosIn χ region).ncard = (LZerosIn χ region).ncard) :
    ∀ z ∈ region, χ.LFunction z = 0 → z.re = (1 : ℝ) / 2 := by
  have heq := LZerosIn_eq_criticalLine_of_ncard_eq hχ hregion hcount
  intro z hzregion hzero
  have hz : z ∈ LZerosIn χ region := ⟨hzregion, hzero⟩
  rw [heq] at hz
  exact hz.2

/-- The explicit finite-strip GRH target theorem for one nontrivial
character. -/
theorem all_zeros_in_strip_on_criticalLine
    {χ : DirichletCharacter ℂ N} (hχ : χ ≠ 1) {lo hi : ℝ}
    (hcount :
      (criticalLineLZerosIn χ (criticalStrip lo hi)).ncard =
        (LZerosIn χ (criticalStrip lo hi)).ncard) :
    ∀ z ∈ criticalStrip lo hi,
      χ.LFunction z = 0 → z.re = (1 : ℝ) / 2 :=
  all_region_zeros_on_criticalLine_of_ncard_eq hχ
    (isCompact_criticalStrip lo hi) hcount

end SparkInterval.Dirichlet
