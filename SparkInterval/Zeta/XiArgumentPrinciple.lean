/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import PrimeNumberTheoremAnd.RectangleArgumentPrinciple
import SparkInterval.Zeta.RiemannXi
import SparkInterval.Zeta.TuringMethod

/-!
# The argument principle for `ξ` on the critical rectangle

This file instantiates the generic rectangle argument principle
(`rectangleIntegral_logDeriv_eq_sum_meromorphicOrderAt`, vendored from the
PrimeNumberTheoremAnd project) at Riemann's `ξ`, and identifies its divisor sum
with the repository's canonical zero count `zetaMultCount`.

The conclusion is

```text
(1 / (2 pi i)) ∮_{∂([0,1] x [-T,T])} ξ'/ξ  =  zetaMultCount T ,
```

i.e. the total analytic multiplicity of the zeta zeros in the closed critical
rectangle of half height `T` is the boundary winding of `ξ`.  This is the
"argument principle for the completed zeta on a rectangle" that
`TuringAnalyticInput.counting_le` is owed; what remains after this file is the
*evaluation* of the boundary integral (Stirling for the `Γ`-factor plus the
`arg ζ` term), not the counting itself.

Three inputs make the instantiation work, all proved in
`SparkInterval.Zeta.RiemannXi`:

* `ξ` is entire and `ξ(1) = 1/2 ≠ 0`, so its order is finite everywhere and no
  degenerate divisor can appear;
* `ξ` has no zeros with `re ≤ 0` or `re ≥ 1`, so the two *vertical* sides of the
  rectangle are automatically free of zeros — no hypothesis is needed for them;
* inside the strip `ξ` and `ζ` have the same zeros *with the same
  multiplicities*, so the divisor sum is exactly `zetaMultCount`.

Only the two *horizontal* sides need a hypothesis, and it is exactly the
classical "good height" condition: `T` is not the ordinate of a zero.  The
companion file `SparkInterval.Zeta.TuringGoodHeights` shows that requiring the
counting identity only at good heights costs nothing, because the exceptional
set is countable and therefore null.

There is no axiom, `sorry`, or `native_decide` in this file.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open Complex Set

/-! ## The critical rectangle is a `Rectangle` -/

theorem rectangle_eq_criticalRectangle {T : ℝ} (hT : 0 ≤ T) :
    Rectangle (-(T : ℂ) * I) (1 + (T : ℂ) * I) = criticalRectangle T := by
  have hre1 : ((-(T : ℂ) * I)).re = 0 := by simp
  have him1 : ((-(T : ℂ) * I)).im = -T := by simp
  have hre2 : ((1 : ℂ) + (T : ℂ) * I).re = 1 := by simp
  have him2 : ((1 : ℂ) + (T : ℂ) * I).im = T := by simp
  rw [Rectangle, hre1, him1, hre2, him2, criticalRectangle,
    uIcc_of_le (by norm_num : (0 : ℝ) ≤ 1), uIcc_of_le (by linarith : -T ≤ T)]

/-! ## The divisor of `ξ` on the critical rectangle -/

theorem analyticOnNhd_riemannXi_on (S : Set ℂ) : AnalyticOnNhd ℂ riemannXi S :=
  fun s _ => analyticAt_riemannXi s

/-- The divisor of `ξ` is the analytic multiplicity, as an integer. -/
theorem divisor_riemannXi_apply {S : Set ℂ} {p : ℂ} (hp : p ∈ S) :
    (MeromorphicOn.divisor riemannXi S) p =
      ((analyticOrderAt riemannXi p).toNat : ℤ) := by
  obtain ⟨n, hn⟩ := WithTop.ne_top_iff_exists.mp (analyticOrderAt_riemannXi_ne_top p)
  rw [MeromorphicOn.AnalyticOnNhd.divisor_apply (analyticOnNhd_riemannXi_on S) hp, ← hn]
  rfl

theorem divisor_riemannXi_ne_zero_iff {S : Set ℂ} {p : ℂ} (hp : p ∈ S) :
    (MeromorphicOn.divisor riemannXi S) p ≠ 0 ↔ riemannXi p = 0 := by
  rw [divisor_riemannXi_apply hp]
  have hfin := analyticOrderAt_riemannXi_ne_top p
  have hstep : (((analyticOrderAt riemannXi p).toNat : ℤ) ≠ 0)
      ↔ analyticOrderAt riemannXi p ≠ 0 := by
    constructor
    · intro h h0
      exact h (by rw [h0]; rfl)
    · intro h h0
      have hz : (analyticOrderAt riemannXi p).toNat = 0 := by exact_mod_cast h0
      exact h ((ENat.toNat_eq_zero.mp hz).resolve_right hfin)
  rw [hstep]
  exact ⟨fun h => apply_eq_zero_of_analyticOrderAt_ne_zero h,
    fun h => (analyticAt_riemannXi p).analyticOrderAt_ne_zero.mpr h⟩

/-- **The divisor support of `ξ` in the critical rectangle is exactly the set of
zeta zeros there.** -/
theorem divisor_riemannXi_support {T : ℝ} :
    (MeromorphicOn.divisor riemannXi (criticalRectangle T)).support =
      zetaZerosIn (criticalRectangle T) := by
  ext p
  constructor
  · intro hp
    have hpmem : p ∈ criticalRectangle T :=
      (MeromorphicOn.divisor riemannXi (criticalRectangle T)).supportWithinDomain hp
    have hne : (MeromorphicOn.divisor riemannXi (criticalRectangle T)) p ≠ 0 := by
      simpa [Function.mem_support] using hp
    have hxi : riemannXi p = 0 := (divisor_riemannXi_ne_zero_iff hpmem).mp hne
    have hmem := mem_criticalRectangle.mp hpmem
    refine ⟨hpmem, ?_⟩
    exact (riemannXi_eq_zero_iff_riemannZeta hmem.1 hmem.2.1).mp hxi
  · rintro ⟨hpmem, hzero⟩
    have hmem := mem_criticalRectangle.mp hpmem
    have hxi : riemannXi p = 0 :=
      (riemannXi_eq_zero_iff_riemannZeta hmem.1 hmem.2.1).mpr hzero
    have := (divisor_riemannXi_ne_zero_iff hpmem).mpr hxi
    simpa [Function.mem_support] using this

/-! ## No zeros on the boundary -/

/-- A "good height": `T` is not the ordinate of a zeta zero.  Only the two
horizontal sides of the rectangle need this; the vertical sides are free of
zeros unconditionally, because `ξ` has none outside the open strip. -/
def GoodHeight (T : ℝ) : Prop :=
  ∀ z : ℂ, riemannZeta z = 0 → 0 ≤ z.re → z.re ≤ 1 → z.im ≠ T ∧ z.im ≠ -T

/-- The zeta zeros in the closed critical strip form a countable set: the strip is
the countable union of the compact rectangles of integer half height, and each of
those contains only finitely many zeros. -/
theorem countable_zetaZeros_strip :
    {z : ℂ | riemannZeta z = 0 ∧ 0 ≤ z.re ∧ z.re ≤ 1}.Countable := by
  have hcover : {z : ℂ | riemannZeta z = 0 ∧ 0 ≤ z.re ∧ z.re ≤ 1} ⊆
      ⋃ n : ℕ, zetaZerosIn (criticalRectangle (n : ℝ)) := by
    intro z hz
    obtain ⟨hzero, hre0, hre1⟩ := hz
    obtain ⟨n, hn⟩ := exists_nat_ge |z.im|
    refine Set.mem_iUnion.mpr ⟨n, ?_, hzero⟩
    rw [mem_criticalRectangle]
    refine ⟨hre0, hre1, ?_, ?_⟩
    · linarith [neg_abs_le z.im, hn]
    · linarith [le_abs_self z.im, hn]
  refine Set.Countable.mono hcover ?_
  exact Set.countable_iUnion fun n =>
    (zetaZerosIn_finite (isCompact_criticalRectangle (n : ℝ))).countable

/-- **Almost every height is a good height.**  The exceptional set is countable,
which is exactly the hypothesis `turingAnalyticInput_of_good_heights` consumes:
requiring the counting identity only at good heights costs nothing, because a
countable set of ordinates is Lebesgue null. -/
theorem countable_not_goodHeight : {T : ℝ | ¬ GoodHeight T}.Countable := by
  classical
  set Z : Set ℂ := {z : ℂ | riemannZeta z = 0 ∧ 0 ≤ z.re ∧ z.re ≤ 1} with hZ
  have hsub : {T : ℝ | ¬ GoodHeight T} ⊆
      (fun z : ℂ => z.im) '' Z ∪ (fun z : ℂ => -z.im) '' Z := by
    intro T hT
    rw [Set.mem_setOf_eq, GoodHeight] at hT
    push_neg at hT
    obtain ⟨z, hzero, hre0, hre1, him⟩ := hT
    have hmemZ : z ∈ Z := ⟨hzero, hre0, hre1⟩
    by_cases h : z.im = T
    · exact Or.inl ⟨z, hmemZ, h⟩
    · refine Or.inr ⟨z, hmemZ, ?_⟩
      have := him h
      linarith
  exact Set.Countable.mono hsub
    ((countable_zetaZeros_strip.image _).union (countable_zetaZeros_strip.image _))

theorem disjoint_rectangleBorder_divisor {T : ℝ} (hT : 0 ≤ T) (hgood : GoodHeight T) :
    Disjoint (RectangleBorder (-(T : ℂ) * I) (1 + (T : ℂ) * I))
      (MeromorphicOn.divisor riemannXi
        (Rectangle (-(T : ℂ) * I) (1 + (T : ℂ) * I))).support := by
  rw [rectangle_eq_criticalRectangle hT, Set.disjoint_left]
  intro p hborder hsupport
  rw [divisor_riemannXi_support] at hsupport
  obtain ⟨hpmem, hzero⟩ := hsupport
  have hmem := mem_criticalRectangle.mp hpmem
  -- the zero is interior to the strip
  have hxi : riemannXi p = 0 :=
    (riemannXi_eq_zero_iff_riemannZeta hmem.1 hmem.2.1).mpr hzero
  obtain ⟨hre0, hre1⟩ := re_mem_Ioo_of_riemannXi_eq_zero hxi
  obtain ⟨him1, him2⟩ := hgood p hzero hmem.1 hmem.2.1
  -- and it is not on any of the four sides
  have hre1' : ((-(T : ℂ) * I)).re = 0 := by simp
  have him1' : ((-(T : ℂ) * I)).im = -T := by simp
  have hre2' : ((1 : ℂ) + (T : ℂ) * I).re = 1 := by simp
  have him2' : ((1 : ℂ) + (T : ℂ) * I).im = T := by simp
  rw [RectangleBorder, hre1', him1', hre2', him2'] at hborder
  simp only [Set.mem_union, Complex.mem_reProdIm, Set.mem_singleton_iff] at hborder
  rcases hborder with ((h | h) | h) | h
  · exact him2 h.2
  · exact absurd h.1 (ne_of_gt hre0)
  · exact him1 h.2
  · exact absurd h.1 (ne_of_lt hre1)

/-! ## The multiplicity bookkeeping -/

theorem toNat_zetaZeroMultiplicityCount (T : ℝ) :
    (zetaZeroMultiplicityCount T).toNat =
      ∑ z ∈ zetaZerosFinset T, (analyticOrderAt riemannZeta z).toNat := by
  classical
  rw [zetaZeroMultiplicityCount]
  refine ENat.toNat_sum ?_
  intro z hz
  have hzero : riemannZeta z = 0 := (mem_zetaZerosFinset.mp hz).2
  have hne : z ≠ 1 := by
    intro h; rw [h] at hzero; exact riemannZeta_one_ne_zero hzero
  exact analyticOrderAt_riemannZeta_ne_top hne

/-! ## The argument principle for `ξ` -/

/-- **The argument principle for `ξ` on the critical rectangle.**

The normalized boundary integral of `ξ'/ξ` over `∂([0,1] × [-T,T])` equals the
total analytic multiplicity of the zeta zeros inside, i.e. the canonical
counting function `zetaMultCount`.

The only hypothesis beyond `0 ≤ T` is that `T` is a *good height*: no zeta zero
in the strip has ordinate `±T`.  Nothing is assumed about zero simplicity. -/
theorem rectangleIntegral_logDeriv_riemannXi {T : ℝ} (hT : 0 ≤ T)
    (hgood : GoodHeight T) :
    RectangleIntegral' (logDeriv riemannXi) (-(T : ℂ) * I) (1 + (T : ℂ) * I) =
      (zetaMultCount T : ℂ) := by
  classical
  set z : ℂ := -(T : ℂ) * I with hz
  set w : ℂ := 1 + (T : ℂ) * I with hw
  have hzre : z.re ≤ w.re := by simp [hz, hw]
  have hzim : z.im ≤ w.im := by
    have h1 : z.im = -T := by simp [hz]
    have h2 : w.im = T := by simp [hw]
    rw [h1, h2]; linarith
  have hf : MeromorphicOn riemannXi (Rectangle z w) := meromorphicOn_riemannXi _
  have hlog : MeromorphicOn (logDeriv riemannXi) (Rectangle z w) :=
    meromorphicOn_logDeriv_riemannXi _
  have hord : ∀ p ∈ Rectangle z w, meromorphicOrderAt riemannXi p ≠ ⊤ :=
    fun p _ => meromorphicOrderAt_riemannXi_ne_top p
  have hbd := disjoint_rectangleBorder_divisor hT hgood
  rw [rectangleIntegral_logDeriv_eq_sum_meromorphicOrderAt hzre hzim hf hlog hord hbd]
  -- identify the divisor sum with the multiplicity count
  have hrect : Rectangle z w = criticalRectangle T := rectangle_eq_criticalRectangle hT
  have hsupp :
      ((divisor_support_rectangle_finite riemannXi z w).toFinset : Finset ℂ) =
        zetaZerosFinset T := by
    ext p
    rw [Set.Finite.mem_toFinset, mem_zetaZerosFinset, hrect, divisor_riemannXi_support]
  rw [hsupp]
  have hterm : ∀ p ∈ zetaZerosFinset T,
      (((MeromorphicOn.divisor riemannXi (Rectangle z w)) p : ℤ) : ℂ) =
        (((analyticOrderAt riemannZeta p).toNat : ℕ) : ℂ) := by
    intro p hp
    obtain ⟨hpmem, hzero⟩ := mem_zetaZerosFinset.mp hp
    have hpmem' : p ∈ Rectangle z w := by rw [hrect]; exact hpmem
    have hmem := mem_criticalRectangle.mp hpmem
    have hxi : riemannXi p = 0 :=
      (riemannXi_eq_zero_iff_riemannZeta hmem.1 hmem.2.1).mpr hzero
    rw [divisor_riemannXi_apply hpmem', analyticOrderAt_riemannXi_of_eq_zero hxi]
    push_cast
    ring
  rw [Finset.sum_congr rfl hterm, zetaMultCount, toNat_zetaZeroMultiplicityCount]
  push_cast
  ring

end SparkInterval.Zeta
