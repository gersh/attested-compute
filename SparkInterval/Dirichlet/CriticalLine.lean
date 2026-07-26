import SparkInterval.Dirichlet.LZeros
import SparkInterval.Zeta.CriticalLine

/-!
# Finite-strip Dirichlet L-function zero target

Dirichlet analogue of `SparkInterval.Zeta.CriticalLine`, stated for the
source-faithful nontrivial strip `(0, 1) x [lo, hi]` with explicit lower and
upper ordinates.  Platt's GRH computation (arXiv:1305.3087) scans `t ∈ [0, t₀]`
for every primitive character and covers negative ordinates through the
conjugate character, so the verified region is naturally one-sided per
character; the aggregate over a conjugation-closed character family then
covers the symmetric strip.

The open strip is not compact.  Its zero set is nevertheless finite because
it is a subset of the zero set in the closed compact envelope
`[0, 1] x [lo, hi]`.  Equality between the number of distinct zeros in the
nontrivial strip and the number of those zeros on the critical line then
forces every nontrivial zero onto the critical line.  The deduction is
axiom-free; the count equality is the analytic obligation of a future
Turing-method checker.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet

open Set DirichletCharacter

variable {N : ℕ} [NeZero N]

/-- Closed compact envelope `[0,1] x [lo,hi]` used only to prove finiteness. -/
def criticalStripEnvelope (lo hi : ℝ) : Set ℂ :=
  Set.Icc (0 : ℝ) 1 ×ℂ Set.Icc lo hi

@[simp] theorem mem_criticalStripEnvelope {lo hi : ℝ} {z : ℂ} :
    z ∈ criticalStripEnvelope lo hi ↔
      0 ≤ z.re ∧ z.re ≤ 1 ∧ lo ≤ z.im ∧ z.im ≤ hi := by
  simp [criticalStripEnvelope, Complex.mem_reProdIm, and_assoc]

theorem isCompact_criticalStripEnvelope (lo hi : ℝ) :
    IsCompact (criticalStripEnvelope lo hi) :=
  isCompact_Icc.reProdIm isCompact_Icc

/-- The source-faithful nontrivial critical-strip rectangle
`(0,1) x [lo,hi]`.  The real-part inequalities are strict, exactly as in
Platt Theorem 7.1 and in the downstream ternary-Goldbach source atom. -/
def nontrivialCriticalStrip (lo hi : ℝ) : Set ℂ :=
  Set.Ioo (0 : ℝ) 1 ×ℂ Set.Icc lo hi

@[simp] theorem mem_nontrivialCriticalStrip {lo hi : ℝ} {z : ℂ} :
    z ∈ nontrivialCriticalStrip lo hi ↔
      0 < z.re ∧ z.re < 1 ∧ lo ≤ z.im ∧ z.im ≤ hi := by
  simp [nontrivialCriticalStrip, Complex.mem_reProdIm, and_assoc]

theorem nontrivialCriticalStrip_subset_envelope (lo hi : ℝ) :
    nontrivialCriticalStrip lo hi ⊆ criticalStripEnvelope lo hi := by
  intro z hz
  rw [mem_nontrivialCriticalStrip] at hz
  rw [mem_criticalStripEnvelope]
  exact ⟨hz.1.le, hz.2.1.le, hz.2.2⟩

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

/-- Although the nontrivial strip is open in the real direction, its zero set
is finite because it lies in the closed compact envelope. -/
theorem LZerosIn_nontrivialCriticalStrip_finite
    {χ : DirichletCharacter ℂ N} (hχ : χ ≠ 1) (lo hi : ℝ) :
    (LZerosIn χ (nontrivialCriticalStrip lo hi)).Finite := by
  apply (LZerosIn_finite hχ (isCompact_criticalStripEnvelope lo hi)).subset
  intro z hz
  exact ⟨nontrivialCriticalStrip_subset_envelope lo hi hz.1, hz.2⟩

theorem criticalLineLZerosIn_subset (χ : DirichletCharacter ℂ N)
    (region : Set ℂ) :
    criticalLineLZerosIn χ region ⊆ LZerosIn χ region :=
  Set.inter_subset_left

/-- Equal distinct-zero counts force every zero in a region with finite zero
set onto the critical line. -/
theorem LZerosIn_eq_criticalLine_of_ncard_eq
    {χ : DirichletCharacter ℂ N} {region : Set ℂ}
    (hfinite : (LZerosIn χ region).Finite)
    (hcount :
      (criticalLineLZerosIn χ region).ncard = (LZerosIn χ region).ncard) :
    LZerosIn χ region = criticalLineLZerosIn χ region := by
  symm
  exact Set.eq_of_subset_of_ncard_le
    (criticalLineLZerosIn_subset χ region) hcount.symm.le
    hfinite

/-- Pointwise finite-region GRH consequence of the checked count equality. -/
theorem all_region_zeros_on_criticalLine_of_ncard_eq
    {χ : DirichletCharacter ℂ N} {region : Set ℂ}
    (hfinite : (LZerosIn χ region).Finite)
    (hcount :
      (criticalLineLZerosIn χ region).ncard = (LZerosIn χ region).ncard) :
    ∀ z ∈ region, χ.LFunction z = 0 → z.re = (1 : ℝ) / 2 := by
  have heq := LZerosIn_eq_criticalLine_of_ncard_eq hfinite hcount
  intro z hzregion hzero
  have hz : z ∈ LZerosIn χ region := ⟨hzregion, hzero⟩
  rw [heq] at hz
  exact hz.2

/-- The explicit source-faithful finite-strip GRH target theorem for one
nontrivial character. -/
theorem all_zeros_in_nontrivialStrip_on_criticalLine
    {χ : DirichletCharacter ℂ N} (hχ : χ ≠ 1) {lo hi : ℝ}
    (hcount :
      (criticalLineLZerosIn χ (nontrivialCriticalStrip lo hi)).ncard =
        (LZerosIn χ (nontrivialCriticalStrip lo hi)).ncard) :
    ∀ z ∈ nontrivialCriticalStrip lo hi,
      χ.LFunction z = 0 → z.re = (1 : ℝ) / 2 :=
  all_region_zeros_on_criticalLine_of_ncard_eq
    (LZerosIn_nontrivialCriticalStrip_finite hχ lo hi) hcount

end SparkInterval.Dirichlet
