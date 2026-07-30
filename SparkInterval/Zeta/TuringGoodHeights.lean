/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.TuringMethod

/-!
# Good heights: from an almost-everywhere counting formula to a Turing window

The Riemann-von Mangoldt formula `N(t) = F(t) + S(t)` is proved by the argument
principle applied to a rectangular contour whose top edge sits at height `t`.
The contour must avoid the zeros, so the proof only produces the identity at a
*good height*: an ordinate `t` which is not the imaginary part of a zero.  The
excluded ordinates form a countable set, because the zeros of a nonzero
holomorphic function are countable.

`TuringAnalyticInput`, however, asks for its counting inequality at *every*
point of the averaging window `[t0, t0+h]`, including the bad ordinates.  This
file bridges that gap.

The bridge rests on two observations.

* The exceptional set is Lebesgue null (a countable set of reals has measure
  zero), so the almost-everywhere identity already determines the integral of
  the error term.  That is the only place the error term is ever used.
* The split of a counting function into "main term plus error" is a
  presentational device, not a constraint: taking the error to be literally
  `N - F` makes the pointwise counting inequality an identity, valid at every
  `t` with no exceptions at all.  All the mathematical content then sits in the
  averaged bound `∫ (N - F) ≤ sBound`, which is exactly what the
  almost-everywhere identity transfers from the citable error term `Sfun`.

So a user only ever has to prove `N t = F t + Sfun t` off a countable set, plus
the averaged bound on `Sfun`; the pointwise behaviour of `N` at the bad
ordinates is irrelevant, and in particular no assumption is made that `N` is
right-continuous, left-continuous, or that its jumps line up with the zeros.

Monotonicity of `N` is used only to integrate it: a monotone function is
interval integrable, which is what makes `N - F` an admissible error term.

There is no axiom, `sorry`, or `native_decide` in this file.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open MeasureTheory Set

/-! ## The null-set transfer -/

/-- Two functions that agree off a countable set have the same interval
integral: a countable set of reals is Lebesgue null. -/
theorem intervalIntegral_congr_of_countable_exceptional {f g : ℝ → ℝ} {a b : ℝ}
    (hbad : {t : ℝ | f t ≠ g t}.Countable) :
    (∫ t in a..b, f t) = ∫ t in a..b, g t := by
  refine intervalIntegral.integral_congr_ae ?_
  have hae : ∀ᵐ t ∂(volume : Measure ℝ), f t = g t :=
    MeasureTheory.ae_iff.mpr (hbad.measure_zero volume)
  filter_upwards [hae] with t ht _ using ht

/-! ## The bridge -/

/-- **From an almost-everywhere counting formula to a Turing analytic input.**

Given a monotone counting function `N`, an integrable main term `F`, an
integrable error term `Sfun` with `N t - F t = Sfun t` off a countable set, and
an upper bound `sBound` for the averaged error `∫ Sfun`, we obtain a genuine
`TuringAnalyticInput` on the window `[t0, t0+h]`.

The constructed input uses `S := N - F`, which makes `counting_le` an equality
holding at *every* point of the window, bad ordinates included.  The exceptional
set is absorbed entirely into `s_integral_le`, where it is harmless because a
countable set is Lebesgue null. -/
def turingAnalyticInput_of_countable_exceptional
    {N F Sfun : ℝ → ℝ} {t0 h sBound : ℝ}
    (hmono : Monotone N)
    (hF : IntervalIntegrable F MeasureTheory.volume t0 (t0 + h))
    (hSfun : IntervalIntegrable Sfun MeasureTheory.volume t0 (t0 + h))
    (hbad : {t : ℝ | N t - F t ≠ Sfun t}.Countable)
    (hbound : (∫ t in t0..(t0 + h), Sfun t) ≤ sBound) :
    TuringAnalyticInput N t0 h where
  F := F
  S := fun t => N t - F t
  F_integrable := hF
  S_integrable := hmono.intervalIntegrable.sub hF
  counting_le := by
    intro t _
    show N t ≤ F t + (N t - F t)
    linarith
  sBound := sBound
  s_integral_le := by
    have hcongr :
        (∫ t in t0..(t0 + h), (N t - F t)) = ∫ t in t0..(t0 + h), Sfun t :=
      intervalIntegral_congr_of_countable_exceptional
        (f := fun t => N t - F t) (g := Sfun) hbad
    show (∫ t in t0..(t0 + h), (N t - F t)) ≤ sBound
    rw [hcongr]
    exact hbound

@[simp] theorem turingAnalyticInput_of_countable_exceptional_F
    {N F Sfun : ℝ → ℝ} {t0 h sBound : ℝ}
    (hmono : Monotone N)
    (hF : IntervalIntegrable F MeasureTheory.volume t0 (t0 + h))
    (hSfun : IntervalIntegrable Sfun MeasureTheory.volume t0 (t0 + h))
    (hbad : {t : ℝ | N t - F t ≠ Sfun t}.Countable)
    (hbound : (∫ t in t0..(t0 + h), Sfun t) ≤ sBound) :
    (turingAnalyticInput_of_countable_exceptional hmono hF hSfun hbad hbound).F = F :=
  rfl

@[simp] theorem turingAnalyticInput_of_countable_exceptional_sBound
    {N F Sfun : ℝ → ℝ} {t0 h sBound : ℝ}
    (hmono : Monotone N)
    (hF : IntervalIntegrable F MeasureTheory.volume t0 (t0 + h))
    (hSfun : IntervalIntegrable Sfun MeasureTheory.volume t0 (t0 + h))
    (hbad : {t : ℝ | N t - F t ≠ Sfun t}.Countable)
    (hbound : (∫ t in t0..(t0 + h), Sfun t) ≤ sBound) :
    (turingAnalyticInput_of_countable_exceptional hmono hF hSfun hbad hbound).sBound = sBound :=
  rfl

/-- The same bridge in the shape an argument-principle theorem actually has: a
predicate `Good` singling out the ordinates at which the contour argument is
legitimate, a proof that its complement is countable, and the counting identity
at every good height. -/
def turingAnalyticInput_of_good_heights
    {N F Sfun : ℝ → ℝ} {t0 h sBound : ℝ} {Good : ℝ → Prop}
    (hmono : Monotone N)
    (hF : IntervalIntegrable F MeasureTheory.volume t0 (t0 + h))
    (hSfun : IntervalIntegrable Sfun MeasureTheory.volume t0 (t0 + h))
    (hbadCountable : {t : ℝ | ¬ Good t}.Countable)
    (hidentity : ∀ t, Good t → N t = F t + Sfun t)
    (hbound : (∫ t in t0..(t0 + h), Sfun t) ≤ sBound) :
    TuringAnalyticInput N t0 h :=
  turingAnalyticInput_of_countable_exceptional hmono hF hSfun
    (hbadCountable.mono (by
      intro t ht
      simp only [mem_setOf_eq] at ht ⊢
      intro hgood
      exact ht (by rw [hidentity t hgood]; ring)))
    hbound

@[simp] theorem turingAnalyticInput_of_good_heights_F
    {N F Sfun : ℝ → ℝ} {t0 h sBound : ℝ} {Good : ℝ → Prop}
    (hmono : Monotone N)
    (hF : IntervalIntegrable F MeasureTheory.volume t0 (t0 + h))
    (hSfun : IntervalIntegrable Sfun MeasureTheory.volume t0 (t0 + h))
    (hbadCountable : {t : ℝ | ¬ Good t}.Countable)
    (hidentity : ∀ t, Good t → N t = F t + Sfun t)
    (hbound : (∫ t in t0..(t0 + h), Sfun t) ≤ sBound) :
    (turingAnalyticInput_of_good_heights hmono hF hSfun hbadCountable hidentity hbound).F = F :=
  rfl

@[simp] theorem turingAnalyticInput_of_good_heights_sBound
    {N F Sfun : ℝ → ℝ} {t0 h sBound : ℝ} {Good : ℝ → Prop}
    (hmono : Monotone N)
    (hF : IntervalIntegrable F MeasureTheory.volume t0 (t0 + h))
    (hSfun : IntervalIntegrable Sfun MeasureTheory.volume t0 (t0 + h))
    (hbadCountable : {t : ℝ | ¬ Good t}.Countable)
    (hidentity : ∀ t, Good t → N t = F t + Sfun t)
    (hbound : (∫ t in t0..(t0 + h), Sfun t) ≤ sBound) :
    (turingAnalyticInput_of_good_heights hmono hF hSfun hbadCountable hidentity
      hbound).sBound = sBound :=
  rfl

/-! ## Chaining to the integer pinning theorems

The two corollaries below are the whole Turing pipeline in one statement.  A
user supplies: a monotone dominating counting function, the counting identity at
good heights, an averaged error bound, the located zeros with their certified
multiplicities, and the final strict arithmetic comparison.  Everything else --
the averaging inequality, the staircase subtraction, the null-set transfer and
the integer pinning -- is proved. -/

/-- **The full Turing window from a good-heights counting formula**, concluding
the analytic-multiplicity bound. -/
theorem zetaMultiplicityCountUpperBound_of_good_heights {N : ℝ → ℝ}
    (hN : SymmetricCountFunction N) {t0 h : ℝ} (hh : 0 < h)
    {F Sfun : ℝ → ℝ} {sBound : ℝ} {Good : ℝ → Prop}
    (hF : IntervalIntegrable F MeasureTheory.volume t0 (t0 + h))
    (hSfun : IntervalIntegrable Sfun MeasureTheory.volume t0 (t0 + h))
    (hbadCountable : {t : ℝ | ¬ Good t}.Countable)
    (hidentity : ∀ t, Good t → N t = F t + Sfun t)
    (hbound : (∫ t in t0..(t0 + h), Sfun t) ≤ sBound)
    {n : ℕ} (gamma : Fin n → ℝ) (mult : Fin n → ℝ)
    (hmem : ∀ i, gamma i ∈ Icc t0 (t0 + h))
    (hstair : ∀ t ∈ Icc t0 (t0 + h),
      N t0 + ∑ i, (if gamma i < t then mult i else 0) ≤ N t)
    {bound : ℕ}
    (hpin :
      ((∫ t in t0..(t0 + h), F t) + sBound -
        ∑ i, mult i * (t0 + h - gamma i)) / h < (bound : ℝ) + 1) :
    ZetaMultiplicityCountUpperBound t0 bound :=
  zetaMultiplicityCountUpperBound_of_turing hN hh
    (turingAnalyticInput_of_good_heights hN.mono hF hSfun hbadCountable hidentity hbound)
    gamma mult hmem hstair hpin

/-- The same conclusion in the form the finite-height verifier consumes. -/
theorem zetaZeroCountUpperBound_of_good_heights {N : ℝ → ℝ}
    (hN : SymmetricCountFunction N) {t0 h : ℝ} (hh : 0 < h)
    {F Sfun : ℝ → ℝ} {sBound : ℝ} {Good : ℝ → Prop}
    (hF : IntervalIntegrable F MeasureTheory.volume t0 (t0 + h))
    (hSfun : IntervalIntegrable Sfun MeasureTheory.volume t0 (t0 + h))
    (hbadCountable : {t : ℝ | ¬ Good t}.Countable)
    (hidentity : ∀ t, Good t → N t = F t + Sfun t)
    (hbound : (∫ t in t0..(t0 + h), Sfun t) ≤ sBound)
    {n : ℕ} (gamma : Fin n → ℝ) (mult : Fin n → ℝ)
    (hmem : ∀ i, gamma i ∈ Icc t0 (t0 + h))
    (hstair : ∀ t ∈ Icc t0 (t0 + h),
      N t0 + ∑ i, (if gamma i < t then mult i else 0) ≤ N t)
    {bound : ℕ}
    (hpin :
      ((∫ t in t0..(t0 + h), F t) + sBound -
        ∑ i, mult i * (t0 + h - gamma i)) / h < (bound : ℝ) + 1) :
    ZetaZeroCountUpperBound t0 bound :=
  (zetaMultiplicityCountUpperBound_of_good_heights hN hh hF hSfun hbadCountable
    hidentity hbound gamma mult hmem hstair hpin).toZetaZeroCountUpperBound

/-! ## Non-vacuity

The hypotheses above are satisfiable.  Two witnesses are exhibited: the trivial
one, and a genuine step function whose jump is a real exceptional point, so that
the countable-exception machinery is actually exercised rather than being
vacuously true with an empty bad set. -/

/-- Trivial witness: everything zero on `[0,1]`.  The exceptional set is empty. -/
def turingAnalyticInputZeroExample : TuringAnalyticInput (fun _ : ℝ => (0 : ℝ)) 0 1 :=
  turingAnalyticInput_of_countable_exceptional
    (N := fun _ : ℝ => (0 : ℝ)) (F := fun _ : ℝ => (0 : ℝ)) (Sfun := fun _ : ℝ => (0 : ℝ))
    (t0 := 0) (h := 1) (sBound := 0)
    monotone_const intervalIntegrable_const intervalIntegrable_const
    (by simp)
    (by simp)

/-- A unit jump at `t = 1`: the model of a counting function that increases by
one at a zero ordinate. -/
noncomputable def jumpCount (t : ℝ) : ℝ := if 1 ≤ t then 1 else 0

/-- The right-continuous companion, which is the "error term" a contour argument
would produce: it agrees with `jumpCount` at every ordinate except the jump
point `t = 1` itself, which is exactly the bad height. -/
noncomputable def jumpCountOpen (t : ℝ) : ℝ := if 1 < t then 1 else 0

theorem jumpCount_monotone : Monotone jumpCount := by
  intro a b hab
  unfold jumpCount
  split_ifs with ha hb hb
  · exact le_rfl
  · exact absurd (ha.trans hab) hb
  · norm_num
  · exact le_rfl

/-- The exceptional set of the pair `(jumpCount, jumpCountOpen)` is exactly the
singleton `{1}`: the counting function and the contour error term differ
precisely at the jump ordinate. -/
theorem jump_exceptional_set :
    {t : ℝ | jumpCount t - (fun _ : ℝ => (0 : ℝ)) t ≠ jumpCountOpen t} = {(1 : ℝ)} := by
  ext t
  simp only [mem_setOf_eq, mem_singleton_iff, jumpCount, jumpCountOpen, sub_zero]
  constructor
  · intro ht
    by_contra hne
    apply ht
    rcases lt_trichotomy t 1 with hlt | heq | hgt
    · rw [if_neg (not_le.mpr hlt), if_neg (not_lt.mpr hlt.le)]
    · exact absurd heq hne
    · rw [if_pos hgt.le, if_pos hgt]
  · intro ht
    subst ht
    norm_num

/-- Nontrivial witness on `[0,2]`: a genuine unit jump at `t = 1`, with the
counting identity failing exactly at that one bad ordinate.  The averaged error
bound is the exact value `∫_0^2 jumpCountOpen = 1`.

This is the smallest faithful caricature of the real situation: `N` jumps at a
zero ordinate, the argument principle only delivers the identity off that
ordinate, and the bridge still produces a Turing analytic input. -/
noncomputable def turingAnalyticInputJumpExample : TuringAnalyticInput jumpCount 0 2 :=
  turingAnalyticInput_of_countable_exceptional
    (N := jumpCount) (F := fun _ : ℝ => (0 : ℝ)) (Sfun := jumpCountOpen)
    (t0 := 0) (h := 2) (sBound := 1)
    jumpCount_monotone intervalIntegrable_const
    (intervalIntegrable_step (t0 := 0) (h := 2) 1 1)
    (by rw [jump_exceptional_set]; exact Set.countable_singleton 1)
    (by
      have := intervalIntegral_step (t0 := (0 : ℝ)) (h := 2) 1 1 (by norm_num)
        (by constructor <;> norm_num)
      show (∫ t in (0 : ℝ)..(0 + 2), jumpCountOpen t) ≤ 1
      unfold jumpCountOpen
      rw [this]
      norm_num)

/-- The nontrivial witness really does have a nonempty exceptional set. -/
theorem jump_exceptional_set_nonempty :
    {t : ℝ | jumpCount t - (fun _ : ℝ => (0 : ℝ)) t ≠ jumpCountOpen t}.Nonempty := by
  rw [jump_exceptional_set]
  exact ⟨1, rfl⟩

end SparkInterval.Zeta
