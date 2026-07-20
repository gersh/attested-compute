import SparkInterval.Zeta.MultiplicityCount

/-!
# Symmetric and positive-ordinate zeta-zero counts

The verifier's target region is the closed symmetric rectangle
`0 <= re z <= 1`, `-height <= im z <= height`.  Standard
Riemann--von Mangoldt and Turing-method statements instead count zeros with
positive ordinate, usually using the convention `0 < im z <= height`.

This file gives the finite-set bookkeeping between those conventions.  The
total multiplicity splits unconditionally into positive, negative, and
real-axis contributions.  Complex conjugation preserves the rectangle by
elementary complex arithmetic, but the Mathlib API imported here does not
provide the required conjugation theorem for `riemannZeta`.  We therefore make
both zero preservation and analytic-multiplicity preservation explicit in
`ZetaConjugationMultiplicitySymmetry`; no instance of that structure is
asserted here.

Under that explicit symmetry contract the positive and negative counts agree.
An additional, explicit no-real-axis-zero premise then identifies the symmetric
count with twice the usual positive-ordinate count.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open Set
open scoped BigOperators
open scoped ComplexConjugate

/-! ## The three parts of the closed symmetric rectangle -/

/-- Zeta zeros in the closed critical rectangle with positive ordinate.
Because the ambient rectangle is closed, this uses the standard convention
`0 < im z <= height`. -/
noncomputable def positiveZetaZerosFinset (height : ℝ) : Finset ℂ :=
  (zetaZerosFinset height).filter fun z => 0 < z.im

/-- Zeta zeros in the closed critical rectangle with negative ordinate.  Its
ordinate convention is `-height <= im z < 0`. -/
noncomputable def negativeZetaZerosFinset (height : ℝ) : Finset ℂ :=
  (zetaZerosFinset height).filter fun z => z.im < 0

/-- Zeta zeros in the closed critical rectangle on the real axis. -/
noncomputable def realAxisZetaZerosFinset (height : ℝ) : Finset ℂ :=
  (zetaZerosFinset height).filter fun z => z.im = 0

@[simp] theorem mem_positiveZetaZerosFinset {height : ℝ} {z : ℂ} :
    z ∈ positiveZetaZerosFinset height ↔
      z ∈ zetaZerosIn (criticalRectangle height) ∧ 0 < z.im := by
  classical
  simp [positiveZetaZerosFinset]

@[simp] theorem mem_negativeZetaZerosFinset {height : ℝ} {z : ℂ} :
    z ∈ negativeZetaZerosFinset height ↔
      z ∈ zetaZerosIn (criticalRectangle height) ∧ z.im < 0 := by
  classical
  simp [negativeZetaZerosFinset]

@[simp] theorem mem_realAxisZetaZerosFinset {height : ℝ} {z : ℂ} :
    z ∈ realAxisZetaZerosFinset height ↔
      z ∈ zetaZerosIn (criticalRectangle height) ∧ z.im = 0 := by
  classical
  simp [realAxisZetaZerosFinset]

/-- Positive-ordinate zeta-zero count with analytic multiplicity. -/
noncomputable def positiveZetaZeroMultiplicityCount (height : ℝ) : ℕ∞ :=
  ∑ z ∈ positiveZetaZerosFinset height, zetaZeroMultiplicity z

/-- Negative-ordinate zeta-zero count with analytic multiplicity. -/
noncomputable def negativeZetaZeroMultiplicityCount (height : ℝ) : ℕ∞ :=
  ∑ z ∈ negativeZetaZerosFinset height, zetaZeroMultiplicity z

/-- Real-axis zeta-zero count with analytic multiplicity. -/
noncomputable def realAxisZetaZeroMultiplicityCount (height : ℝ) : ℕ∞ :=
  ∑ z ∈ realAxisZetaZerosFinset height, zetaZeroMultiplicity z

/-- The closed symmetric count is the sum of its positive, negative, and
real-axis parts.  This is finite-set bookkeeping and uses no zeta symmetry. -/
theorem zetaZeroMultiplicityCount_partition (height : ℝ) :
    zetaZeroMultiplicityCount height =
      positiveZetaZeroMultiplicityCount height +
        negativeZetaZeroMultiplicityCount height +
          realAxisZetaZeroMultiplicityCount height := by
  classical
  let s := zetaZerosFinset height
  let multiplicity : ℂ → ℕ∞ := zetaZeroMultiplicity
  have hnegative :
      ((s.filter fun z => ¬0 < z.im).filter fun z => z.im < 0) =
        s.filter fun z => z.im < 0 := by
    ext z
    simp only [Finset.mem_filter]
    constructor
    · rintro ⟨⟨hz, _⟩, hnegative⟩
      exact ⟨hz, hnegative⟩
    · rintro ⟨hz, hnegative⟩
      exact ⟨⟨hz, not_lt.mpr hnegative.le⟩, hnegative⟩
  have haxis :
      ((s.filter fun z => ¬0 < z.im).filter fun z => ¬z.im < 0) =
        s.filter fun z => z.im = 0 := by
    ext z
    simp only [Finset.mem_filter]
    constructor
    · rintro ⟨⟨hz, hnonpositive⟩, hnonnegative⟩
      exact ⟨hz, le_antisymm (not_lt.mp hnonpositive) (not_lt.mp hnonnegative)⟩
    · rintro ⟨hz, him⟩
      exact ⟨
        ⟨hz, not_lt.mpr (by simp [him])⟩,
        not_lt.mpr (by simp [him])⟩
  have hnonpositive :
      (∑ z ∈ s.filter (fun z => ¬0 < z.im), multiplicity z) =
        (∑ z ∈ s.filter (fun z => z.im < 0), multiplicity z) +
          ∑ z ∈ s.filter (fun z => z.im = 0), multiplicity z := by
    calc
      (∑ z ∈ s.filter (fun z => ¬0 < z.im), multiplicity z) =
          (∑ z ∈ (s.filter fun z => ¬0 < z.im).filter
              (fun z => z.im < 0), multiplicity z) +
            ∑ z ∈ (s.filter fun z => ¬0 < z.im).filter
              (fun z => ¬z.im < 0), multiplicity z :=
        (Finset.sum_filter_add_sum_filter_not
          (s.filter fun z => ¬0 < z.im) (fun z => z.im < 0) multiplicity).symm
      _ = (∑ z ∈ s.filter (fun z => z.im < 0), multiplicity z) +
            ∑ z ∈ s.filter (fun z => z.im = 0), multiplicity z := by
        rw [hnegative, haxis]
  change (∑ z ∈ s, multiplicity z) =
    (∑ z ∈ s.filter (fun z => 0 < z.im), multiplicity z) +
      (∑ z ∈ s.filter (fun z => z.im < 0), multiplicity z) +
        ∑ z ∈ s.filter (fun z => z.im = 0), multiplicity z
  calc
    (∑ z ∈ s, multiplicity z) =
        (∑ z ∈ s.filter (fun z => 0 < z.im), multiplicity z) +
          ∑ z ∈ s.filter (fun z => ¬0 < z.im), multiplicity z :=
      (Finset.sum_filter_add_sum_filter_not
        s (fun z => 0 < z.im) multiplicity).symm
    _ = (∑ z ∈ s.filter (fun z => 0 < z.im), multiplicity z) +
          ((∑ z ∈ s.filter (fun z => z.im < 0), multiplicity z) +
            ∑ z ∈ s.filter (fun z => z.im = 0), multiplicity z) := by
      rw [hnonpositive]
    _ = (∑ z ∈ s.filter (fun z => 0 < z.im), multiplicity z) +
          (∑ z ∈ s.filter (fun z => z.im < 0), multiplicity z) +
            ∑ z ∈ s.filter (fun z => z.im = 0), multiplicity z := by
      rw [add_assoc]

/-! ## Explicit analytic symmetry boundary -/

/-- Analytic input needed to identify the two half-rectangle counts.

The first field says that zeta zeros are closed under complex conjugation; the
second says their analytic orders agree.  These facts are intentionally
premises: this module does not assert that the current Mathlib zeta API proves
them. -/
structure ZetaConjugationMultiplicitySymmetry : Prop where
  zero_iff (z : ℂ) :
    riemannZeta (conj z) = 0 ↔ riemannZeta z = 0
  multiplicity_eq (z : ℂ) :
    zetaZeroMultiplicity (conj z) = zetaZeroMultiplicity z

/-- Complex conjugation preserves the verifier's closed symmetric rectangle. -/
@[simp] theorem conj_mem_criticalRectangle_iff {height : ℝ} {z : ℂ} :
    conj z ∈ criticalRectangle height ↔
      z ∈ criticalRectangle height := by
  rw [mem_criticalRectangle, mem_criticalRectangle]
  simp only [Complex.conj_re, Complex.conj_im]
  constructor
  · rintro ⟨hreLower, hreUpper, himLower, himUpper⟩
    exact ⟨hreLower, hreUpper, by linarith, by linarith⟩
  · rintro ⟨hreLower, hreUpper, himLower, himUpper⟩
    exact ⟨hreLower, hreUpper, by linarith, by linarith⟩

namespace ZetaConjugationMultiplicitySymmetry

/-- Under the explicit analytic contract, conjugation preserves membership in
the zeta-zero set restricted to the symmetric rectangle. -/
theorem conj_mem_zetaZerosIn_iff
    (symmetry : ZetaConjugationMultiplicitySymmetry)
    {height : ℝ} {z : ℂ} :
    conj z ∈ zetaZerosIn (criticalRectangle height) ↔
      z ∈ zetaZerosIn (criticalRectangle height) := by
  change (conj z ∈ criticalRectangle height ∧
      conj z ∈ riemannZetaZeros) ↔
    (z ∈ criticalRectangle height ∧ z ∈ riemannZetaZeros)
  constructor
  · rintro ⟨hrectangle, hzero⟩
    exact ⟨
      conj_mem_criticalRectangle_iff.mp hrectangle,
      mem_riemannZetaZeros.mpr
        ((symmetry.zero_iff z).mp (mem_riemannZetaZeros.mp hzero))
    ⟩
  · rintro ⟨hrectangle, hzero⟩
    exact ⟨
      conj_mem_criticalRectangle_iff.mpr hrectangle,
      mem_riemannZetaZeros.mpr
        ((symmetry.zero_iff z).mpr (mem_riemannZetaZeros.mp hzero))
    ⟩

theorem conj_mem_negativeZetaZerosFinset_iff
    (symmetry : ZetaConjugationMultiplicitySymmetry)
    {height : ℝ} {z : ℂ} :
    conj z ∈ negativeZetaZerosFinset height ↔
      z ∈ positiveZetaZerosFinset height := by
  rw [mem_negativeZetaZerosFinset, mem_positiveZetaZerosFinset]
  constructor
  · rintro ⟨hzero, him⟩
    exact ⟨symmetry.conj_mem_zetaZerosIn_iff.mp hzero, by
      simpa only [Complex.conj_im, neg_lt_zero] using him⟩
  · rintro ⟨hzero, him⟩
    exact ⟨symmetry.conj_mem_zetaZerosIn_iff.mpr hzero, by
      simpa only [Complex.conj_im, neg_lt_zero] using him⟩

theorem conj_mem_positiveZetaZerosFinset_iff
    (symmetry : ZetaConjugationMultiplicitySymmetry)
    {height : ℝ} {z : ℂ} :
    conj z ∈ positiveZetaZerosFinset height ↔
      z ∈ negativeZetaZerosFinset height := by
  rw [mem_positiveZetaZerosFinset, mem_negativeZetaZerosFinset]
  constructor
  · rintro ⟨hzero, him⟩
    exact ⟨symmetry.conj_mem_zetaZerosIn_iff.mp hzero, by
      simpa only [Complex.conj_im, neg_pos] using him⟩
  · rintro ⟨hzero, him⟩
    exact ⟨symmetry.conj_mem_zetaZerosIn_iff.mpr hzero, by
      simpa only [Complex.conj_im, neg_pos] using him⟩

/-- Conjugation is a multiplicity-preserving bijection from the negative
half-rectangle to the positive half-rectangle. -/
theorem negative_eq_positive
    (symmetry : ZetaConjugationMultiplicitySymmetry) (height : ℝ) :
    negativeZetaZeroMultiplicityCount height =
      positiveZetaZeroMultiplicityCount height := by
  classical
  unfold negativeZetaZeroMultiplicityCount positiveZetaZeroMultiplicityCount
  refine Finset.sum_nbij' conj conj ?_ ?_ ?_ ?_ ?_
  · intro z hz
    exact symmetry.conj_mem_positiveZetaZerosFinset_iff.mpr hz
  · intro z hz
    exact symmetry.conj_mem_negativeZetaZerosFinset_iff.mpr hz
  · intro z _hz
    exact Complex.conj_conj z
  · intro z _hz
    exact Complex.conj_conj z
  · intro z _hz
    exact (symmetry.multiplicity_eq z).symm

end ZetaConjugationMultiplicitySymmetry

/-! ## Removing the real-axis boundary contribution -/

/-- Explicit boundary premise needed to double a strictly positive-ordinate
count.  It says that the closed verifier rectangle contains no zeta zero on
the real axis. -/
def NoRealAxisZetaZeros (height : ℝ) : Prop :=
  ∀ z ∈ zetaZerosIn (criticalRectangle height), z.im ≠ 0

namespace NoRealAxisZetaZeros

theorem realAxisMultiplicityCount_eq_zero {height : ℝ}
    (noRealAxis : NoRealAxisZetaZeros height) :
    realAxisZetaZeroMultiplicityCount height = 0 := by
  classical
  unfold realAxisZetaZeroMultiplicityCount
  apply Finset.sum_eq_zero
  intro z hz
  exfalso
  have hmem := mem_realAxisZetaZerosFinset.mp hz
  exact noRealAxis z hmem.1 hmem.2

end NoRealAxisZetaZeros

/-- With the analytic conjugation contract and no zeros on the real-axis
boundary, the symmetric count is two copies of the positive-ordinate count. -/
theorem zetaZeroMultiplicityCount_eq_positive_add_positive
    {height : ℝ}
    (symmetry : ZetaConjugationMultiplicitySymmetry)
    (noRealAxis : NoRealAxisZetaZeros height) :
    zetaZeroMultiplicityCount height =
      positiveZetaZeroMultiplicityCount height +
        positiveZetaZeroMultiplicityCount height := by
  rw [zetaZeroMultiplicityCount_partition,
    symmetry.negative_eq_positive,
    noRealAxis.realAxisMultiplicityCount_eq_zero,
    add_zero]

theorem zetaZeroMultiplicityCount_eq_two_mul_positive
    {height : ℝ}
    (symmetry : ZetaConjugationMultiplicitySymmetry)
    (noRealAxis : NoRealAxisZetaZeros height) :
    zetaZeroMultiplicityCount height =
      2 * positiveZetaZeroMultiplicityCount height := by
  simpa only [two_mul] using
    zetaZeroMultiplicityCount_eq_positive_add_positive symmetry noRealAxis

/-! ## Positive Riemann--von Mangoldt/Turing count handoff -/

/-- Analytic upper bound in the conventional positive-ordinate region
`0 < im z <= height`, counting zeros with multiplicity. -/
structure PositiveZetaMultiplicityCountUpperBound
    (height : ℝ) (bound : Nat) : Prop where
  count_le : positiveZetaZeroMultiplicityCount height ≤ (bound : ℕ∞)

namespace PositiveZetaMultiplicityCountUpperBound

/-- Convert a positive-ordinate analytic bound to the symmetric bound consumed
by the finite-height verifier.  The factor of two and the no-real-axis premise
are visible in the theorem's type. -/
theorem toZetaMultiplicityCountUpperBound
    {height : ℝ} {bound : Nat}
    (upper : PositiveZetaMultiplicityCountUpperBound height bound)
    (symmetry : ZetaConjugationMultiplicitySymmetry)
    (noRealAxis : NoRealAxisZetaZeros height) :
    ZetaMultiplicityCountUpperBound height (2 * bound) := by
  refine ⟨?_⟩
  rw [zetaZeroMultiplicityCount_eq_two_mul_positive symmetry noRealAxis]
  have hdoubled := add_le_add upper.count_le upper.count_le
  simpa only [two_mul, ENat.coe_add] using hdoubled

/-- Direct handoff from a conventional positive count to the verifier's
distinct-zero upper-bound contract. -/
theorem toZetaZeroCountUpperBound
    {height : ℝ} {bound : Nat}
    (upper : PositiveZetaMultiplicityCountUpperBound height bound)
    (symmetry : ZetaConjugationMultiplicitySymmetry)
    (noRealAxis : NoRealAxisZetaZeros height) :
    ZetaZeroCountUpperBound height (2 * bound) :=
  ZetaMultiplicityCountUpperBound.toZetaZeroCountUpperBound
    (upper.toZetaMultiplicityCountUpperBound symmetry noRealAxis)

end PositiveZetaMultiplicityCountUpperBound

end SparkInterval.Zeta
