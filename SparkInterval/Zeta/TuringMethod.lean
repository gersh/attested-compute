/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.MeasureTheory.Integral.IntervalIntegral.Basic
import SparkInterval.Zeta.MultiplicityCount

/-!
# Turing's method: averaging, staircase subtraction, and integer pinning

Turing's method upgrades an *approximate* zero-counting formula into an *exact*
integer count.  Its three ingredients are

1. an exact counting formula `N(t) = F(t) + S(t)` with `F` explicit and smooth
   (Riemann-von Mangoldt / argument principle);
2. a bound on the *average* of the error term, `|∫_{t0}^{t0+h} S| ≤ B`
   (Turing/Lehman for `ζ`, Rumely for Dirichlet `L`) -- pointwise `S` is not
   small, only its mean is;
3. monotonicity of `N`, which converts the average bound into a pointwise bound
   at the left endpoint, sharpened by subtracting the staircase contributed by
   the zeros that have *already been located* in the averaging window.

Steps 2 and 3 are what this file proves.  Step 1 is the genuinely analytic
input and is kept as an explicit hypothesis (`TuringAnalyticInput`), never as
an axiom.

The point of the decomposition is that the analytic input is a statement about
one *smooth* function `F` and one *averaged* error bound, both of which are
citable or computable, whereas the combinatorial "which integer is it" step --
historically the place where a hand computation goes wrong -- is fully proved
here.

Nothing in this file assumes zeros are simple, and the zeta-side conclusion is
phrased with analytic multiplicity (`zetaZeroMultiplicityCount`), so a zero of
multiplicity two cannot be miscounted as one.

There is no axiom, `sorry`, or `native_decide` in this file.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open MeasureTheory Set

/-! ## Step 3: monotone averaging with staircase subtraction -/

section Averaging

variable {N : ℝ → ℝ} {t0 h : ℝ}

/-- The elementary averaging inequality: a nondecreasing function is at most its
own mean over any window to the right. -/
theorem mul_le_intervalIntegral_of_monotone (hmono : Monotone N) (hh : 0 < h) :
    h * N t0 ≤ ∫ t in t0..(t0 + h), N t := by
  have hle : t0 ≤ t0 + h := by linarith
  have hconst : (∫ _t in t0..(t0 + h), N t0) = h * N t0 := by
    rw [intervalIntegral.integral_const, add_sub_cancel_left, smul_eq_mul]
  rw [← hconst]
  refine intervalIntegral.integral_mono_on hle
    (intervalIntegrable_const) (hmono.intervalIntegrable) ?_
  intro x hx
  exact hmono hx.1

/-- One step of the staircase, written as a difference of an `Iic`-indicator so
that the pointwise identity is exact at the jump point too. -/
theorem step_eq_sub_indicator (c m : ℝ) (t : ℝ) :
    (if c < t then m else 0) = m - Set.indicator {x : ℝ | x ≤ c} (fun _ => m) t := by
  simp only [Set.indicator_apply, Set.mem_setOf_eq]
  by_cases hc : c < t
  · rw [if_pos hc, if_neg (not_le.mpr hc)]; ring
  · rw [if_neg hc, if_pos (not_lt.mp hc)]; ring

theorem intervalIntegrable_indicator_Iic (c m : ℝ) :
    IntervalIntegrable (fun t => Set.indicator {x : ℝ | x ≤ c} (fun _ => m) t)
      volume t0 (t0 + h) := by
  have hms : MeasurableSet {x : ℝ | x ≤ c} := measurableSet_Iic
  exact ⟨(intervalIntegrable_const (μ := volume) (a := t0) (b := t0 + h)
      (c := m)).1.indicator hms,
    (intervalIntegrable_const (μ := volume) (a := t0) (b := t0 + h)
      (c := m)).2.indicator hms⟩

theorem intervalIntegrable_step (c m : ℝ) :
    IntervalIntegrable (fun t => if c < t then m else 0) volume t0 (t0 + h) := by
  have hrw : (fun t => if c < t then m else 0)
      = fun t => m - Set.indicator {x : ℝ | x ≤ c} (fun _ => m) t := by
    funext t; exact step_eq_sub_indicator c m t
  rw [hrw]
  exact intervalIntegrable_const.sub (intervalIntegrable_indicator_Iic c m)

theorem intervalIntegral_step (c m : ℝ) (_hh : 0 < h) (hc : c ∈ Icc t0 (t0 + h)) :
    (∫ t in t0..(t0 + h), (if c < t then m else 0)) = m * (t0 + h - c) := by
  have hrw : ∀ t : ℝ, (if c < t then m else 0)
      = m - Set.indicator {x : ℝ | x ≤ c} (fun _ => m) t := step_eq_sub_indicator c m
  simp only [hrw]
  rw [intervalIntegral.integral_sub intervalIntegrable_const
      (intervalIntegrable_indicator_Iic (t0 := t0) (h := h) c m),
    intervalIntegral.integral_indicator hc, intervalIntegral.integral_const,
    intervalIntegral.integral_const, add_sub_cancel_left, smul_eq_mul, smul_eq_mul]
  ring

theorem intervalIntegrable_staircase {n : ℕ} (gamma : Fin n → ℝ) (mult : Fin n → ℝ) :
    IntervalIntegrable
      (fun t => N t0 + ∑ i, (if gamma i < t then mult i else 0)) volume t0 (t0 + h) := by
  classical
  refine intervalIntegrable_const.add ?_
  have hsum : (fun t : ℝ => ∑ i, (if gamma i < t then mult i else 0))
      = ∑ i : Fin n, fun t : ℝ => (if gamma i < t then mult i else 0) := by
    funext t
    simp [Finset.sum_apply]
  rw [hsum]
  exact IntervalIntegrable.sum _ fun i _ => intervalIntegrable_step (gamma i) (mult i)

/-- The staircase minorant of a monotone counting function integrates to the
explicit partial-staircase sum. -/
theorem intervalIntegral_staircase {n : ℕ} (gamma : Fin n → ℝ) (mult : Fin n → ℝ)
    (hh : 0 < h) (hmem : ∀ i, gamma i ∈ Icc t0 (t0 + h)) :
    (∫ t in t0..(t0 + h),
        (N t0 + ∑ i, (if gamma i < t then mult i else 0))) =
      h * N t0 + ∑ i, mult i * (t0 + h - gamma i) := by
  classical
  rw [intervalIntegral.integral_add intervalIntegrable_const ?_]
  · rw [intervalIntegral.integral_const, add_sub_cancel_left, smul_eq_mul]
    congr 1
    rw [intervalIntegral.integral_finsetSum
      (fun i _ => intervalIntegrable_step (gamma i) (mult i))]
    exact Finset.sum_congr rfl fun i _ =>
      intervalIntegral_step (gamma i) (mult i) hh (hmem i)
  · have := intervalIntegrable_staircase (N := N) (t0 := t0) (h := h) gamma mult
    exact (this.sub intervalIntegrable_const).congr (by intro t _; ring)

/-- **Turing's averaging step with staircase subtraction.**

If `N` is nondecreasing, already known to have gained `mult i` by the time the
ordinate passes each located zero `gamma i`, and its mean over `[t0, t0+h]` is
at most `mainIntegral`, then

```text
N t0 ≤ (mainIntegral - Σ mult i (t0 + h - gamma i)) / h.
```

The located zeros enter with a minus sign, so an *incomplete* list of located
zeros, or ordinate enclosures taken at their left ends, only weakens the
conclusion.  That is the safe direction. -/
theorem turing_upper_bound {n : ℕ} (hmono : Monotone N) (hh : 0 < h)
    (gamma : Fin n → ℝ) (mult : Fin n → ℝ)
    (hmem : ∀ i, gamma i ∈ Icc t0 (t0 + h))
    (hstair : ∀ t ∈ Icc t0 (t0 + h),
      N t0 + ∑ i, (if gamma i < t then mult i else 0) ≤ N t)
    {mainIntegral : ℝ}
    (hint : (∫ t in t0..(t0 + h), N t) ≤ mainIntegral) :
    N t0 ≤ (mainIntegral - ∑ i, mult i * (t0 + h - gamma i)) / h := by
  classical
  have hle : t0 ≤ t0 + h := by linarith
  have hlower :
      h * N t0 + ∑ i, mult i * (t0 + h - gamma i) ≤ ∫ t in t0..(t0 + h), N t := by
    rw [← intervalIntegral_staircase (N := N) gamma mult hh hmem]
    exact intervalIntegral.integral_mono_on hle
      (intervalIntegrable_staircase gamma mult) hmono.intervalIntegrable hstair
  rw [le_div_iff₀ hh]
  nlinarith [hlower.trans hint]

end Averaging

/-! ## Step 1+2 packaged: the analytic input -/

/-- The analytic half of Turing's method for a counting function `N` on the
averaging window `[t0, t0+h]`.

`F` is the explicit smooth main term of the counting formula (for `ζ`, twice
`θ(t)/π + 1`; for Dirichlet `L`, the reflected `Φ`-term), and `S` is the
oscillating error.  Only an upper bound on the *mean* of `S` is required.

Nothing here is assumed about how `F` and the bound are obtained: a rigorous
argument-principle proof plus a cited averaged bound (Turing/Lehman, Rumely)
must construct this structure. -/
structure TuringAnalyticInput (N : ℝ → ℝ) (t0 h : ℝ) where
  /-- Explicit main term of the counting formula. -/
  F : ℝ → ℝ
  /-- Oscillating error term of the counting formula. -/
  S : ℝ → ℝ
  F_integrable : IntervalIntegrable F volume t0 (t0 + h)
  S_integrable : IntervalIntegrable S volume t0 (t0 + h)
  /-- Riemann-von Mangoldt / argument principle, in the direction actually
  used.  Equality holds off the finite set of zero ordinates. -/
  counting_le : ∀ t ∈ Icc t0 (t0 + h), N t ≤ F t + S t
  /-- The averaged error bound (Turing/Lehman for `ζ`, Rumely for `L`). -/
  sBound : ℝ
  s_integral_le : (∫ t in t0..(t0 + h), S t) ≤ sBound

namespace TuringAnalyticInput

variable {N : ℝ → ℝ} {t0 h : ℝ}

/-- The analytic input bounds the mean of the counting function. -/
theorem integral_le (input : TuringAnalyticInput N t0 h) (hmono : Monotone N)
    (hh : 0 < h) :
    (∫ t in t0..(t0 + h), N t) ≤ (∫ t in t0..(t0 + h), input.F t) + input.sBound := by
  have hle : t0 ≤ t0 + h := by linarith
  calc
    (∫ t in t0..(t0 + h), N t) ≤ ∫ t in t0..(t0 + h), (input.F t + input.S t) :=
      intervalIntegral.integral_mono_on hle hmono.intervalIntegrable
        (input.F_integrable.add input.S_integrable) input.counting_le
    _ = (∫ t in t0..(t0 + h), input.F t) + ∫ t in t0..(t0 + h), input.S t :=
      intervalIntegral.integral_add input.F_integrable input.S_integrable
    _ ≤ (∫ t in t0..(t0 + h), input.F t) + input.sBound := by
      linarith [input.s_integral_le]

end TuringAnalyticInput

/-! ## Step 4: integer pinning against the zeta multiplicity count -/

/-- A real-valued function dominating the analytic-multiplicity zero count of
`riemannZeta` in the closed critical rectangle of half height `t`.

`dominates` is stated against arbitrary naturals so that the `ℕ∞` value `⊤`
(which a locally-zero function would produce) cannot be silently truncated: if
the multiplicity count were infinite, no real `N t` could dominate it, and the
hypothesis would be unsatisfiable rather than vacuously true. -/
structure SymmetricCountFunction (N : ℝ → ℝ) : Prop where
  mono : Monotone N
  dominates : ∀ (t : ℝ) (m : ℕ),
    (m : ℕ∞) ≤ zetaZeroMultiplicityCount t → (m : ℝ) ≤ N t

/-- **Integer pinning.**  A strict real upper bound below `bound + 1` on a
dominating counting function pins the integer multiplicity count. -/
theorem zetaMultiplicityCountUpperBound_of_lt {N : ℝ → ℝ}
    (hN : SymmetricCountFunction N) {height : ℝ} {bound : ℕ}
    (hlt : N height < (bound : ℝ) + 1) :
    ZetaMultiplicityCountUpperBound height bound := by
  refine ⟨?_⟩
  by_contra hcon
  have hgt : (bound : ℕ∞) < zetaZeroMultiplicityCount height := lt_of_not_ge hcon
  have hsucc : ((bound + 1 : ℕ) : ℕ∞) ≤ zetaZeroMultiplicityCount height := by
    have : (bound : ℕ∞) + 1 ≤ zetaZeroMultiplicityCount height :=
      Order.add_one_le_of_lt hgt
    simpa using this
  have hreal : ((bound + 1 : ℕ) : ℝ) ≤ N height := hN.dominates height (bound + 1) hsucc
  push_cast at hreal
  linarith

/-! ## Non-vacuity: the canonical distinct-zero counting function

`SymmetricCountFunction` is a hypothesis about an object whose existence is not
obvious, so this section exhibits a concrete monotone counting function for the
same rectangles -- the number of *distinct* zeta zeros of half height `t`,
which Mathlib's compactness/discreteness theorem already makes finite.

The Turing machinery is therefore not vacuous: it applies verbatim to
`zetaDistinctCount`, at the cost that the analytic input must then be a bound
on the distinct count rather than on the multiplicity count.  An
argument-principle proof naturally produces the multiplicity version, which is
the stronger one, so the multiplicity interface above is the intended target;
this section exists to show the shape is inhabited. -/

/-- The number of distinct zeta zeros in the closed critical rectangle of half
height `t`, as a real number. -/
noncomputable def zetaDistinctCount (t : ℝ) : ℝ :=
  ((zetaZerosIn (criticalRectangle t)).ncard : ℝ)

theorem criticalRectangle_mono {a b : ℝ} (hab : a ≤ b) :
    criticalRectangle a ⊆ criticalRectangle b := by
  intro z hz
  rw [mem_criticalRectangle] at hz ⊢
  refine ⟨hz.1, hz.2.1, ?_, ?_⟩ <;> linarith [hz.2.2.1, hz.2.2.2]

theorem zetaDistinctCount_monotone : Monotone zetaDistinctCount := by
  intro a b hab
  have hsub : zetaZerosIn (criticalRectangle a) ⊆ zetaZerosIn (criticalRectangle b) :=
    Set.inter_subset_inter_left _ (criticalRectangle_mono hab)
  have hle := Set.ncard_le_ncard hsub (zetaZerosIn_finite (isCompact_criticalRectangle b))
  unfold zetaDistinctCount
  exact_mod_cast hle

/-- Integer pinning against the distinct-zero count. -/
theorem zetaZeroCountUpperBound_of_lt_distinct {N : ℝ → ℝ}
    (hdom : ∀ t, zetaDistinctCount t ≤ N t) {height : ℝ} {bound : ℕ}
    (hlt : N height < (bound : ℝ) + 1) :
    ZetaZeroCountUpperBound height bound := by
  refine ⟨?_⟩
  have hreal : ((zetaZerosIn (criticalRectangle height)).ncard : ℝ) < (bound : ℝ) + 1 :=
    lt_of_le_of_lt (hdom height) hlt
  have hnat : (zetaZerosIn (criticalRectangle height)).ncard < bound + 1 := by
    exact_mod_cast hreal
  omega

/-! ## The canonical multiplicity counting function

The multiplicity count is finite, because `riemannZeta` does not vanish on any
open set, so the canonical real counting function below actually satisfies
`SymmetricCountFunction`.  The analytic input of a Turing window may therefore
be stated about the genuine zeta zero count rather than about an unspecified
dominating function. -/

/-- `riemannZeta` has finite analytic order at every point other than its pole:
it does not vanish on any neighbourhood, by the identity theorem on the
connected set `{1}ᶜ` together with `ζ(2) ≠ 0`. -/
theorem analyticOrderAt_riemannZeta_ne_top {z : ℂ} (hz : z ≠ 1) :
    analyticOrderAt riemannZeta z ≠ ⊤ := by
  intro htop
  have hev : ∀ᶠ w in nhds z, riemannZeta w = 0 := analyticOrderAt_eq_top.mp htop
  have hmem : z ∈ ({(1 : ℂ)}ᶜ : Set ℂ) := by simpa using hz
  have heq : Set.EqOn riemannZeta 0 ({(1 : ℂ)}ᶜ : Set ℂ) :=
    analyticOn_riemannZeta.eqOn_zero_of_preconnected_of_eventuallyEq_zero
      (isConnected_compl_singleton_of_one_lt_rank (by simp) 1).isPreconnected hmem
      (by filter_upwards [hev] with w hw using hw)
  have h2 : riemannZeta 2 = 0 := by
    have := heq (show (2 : ℂ) ∈ ({(1 : ℂ)}ᶜ : Set ℂ) by norm_num)
    simpa using this
  exact riemannZeta_ne_zero_of_one_le_re (by norm_num) h2

theorem zetaZeroMultiplicityCount_ne_top (t : ℝ) :
    zetaZeroMultiplicityCount t ≠ ⊤ := by
  classical
  rw [zetaZeroMultiplicityCount]
  refine WithTop.sum_ne_top.mpr ?_
  intro z hz
  have hzero : riemannZeta z = 0 := (mem_zetaZerosFinset.mp hz).2
  have hne : z ≠ 1 := by
    intro h
    rw [h] at hzero
    exact riemannZeta_one_ne_zero hzero
  exact analyticOrderAt_riemannZeta_ne_top hne

theorem zetaZeroMultiplicityCount_monotone : Monotone zetaZeroMultiplicityCount := by
  classical
  intro a b hab
  refine Finset.sum_le_sum_of_subset ?_
  intro z hz
  rw [mem_zetaZerosFinset] at hz ⊢
  exact ⟨criticalRectangle_mono hab hz.1, hz.2⟩

/-- The canonical counting function: total analytic multiplicity of the zeta
zeros in the closed critical rectangle of half height `t`, as a real number. -/
noncomputable def zetaMultCount (t : ℝ) : ℝ :=
  ((zetaZeroMultiplicityCount t).toNat : ℝ)

/-- **The Turing interface is inhabited by the genuine zeta multiplicity
count.** -/
theorem symmetricCountFunction_zetaMultCount :
    SymmetricCountFunction zetaMultCount := by
  constructor
  · intro a b hab
    have hnat : (zetaZeroMultiplicityCount a).toNat ≤ (zetaZeroMultiplicityCount b).toNat :=
      ENat.toNat_le_toNat (zetaZeroMultiplicityCount_monotone hab)
        (zetaZeroMultiplicityCount_ne_top b)
    unfold zetaMultCount
    exact_mod_cast hnat
  · intro t m hm
    have hnat : m ≤ (zetaZeroMultiplicityCount t).toNat := by
      have := ENat.toNat_le_toNat hm (zetaZeroMultiplicityCount_ne_top t)
      simpa using this
    unfold zetaMultCount
    exact_mod_cast hnat

/-! ## The assembled Turing window -/

/-- Everything a Turing window must supply to pin the zeta zero count at height
`t0`: the analytic counting formula on `[t0, t0+h]`, the located zeros with
their certified multiplicities, and the final strict arithmetic comparison.

`gamma` are the certified ordinates of zeros located in the averaging window
and `mult` their certified multiplicity lower bounds; `hstair` says the
counting function has really gained them.  Everything else is proved. -/
theorem zetaMultiplicityCountUpperBound_of_turing {N : ℝ → ℝ}
    (hN : SymmetricCountFunction N) {t0 h : ℝ} (hh : 0 < h)
    (input : TuringAnalyticInput N t0 h)
    {n : ℕ} (gamma : Fin n → ℝ) (mult : Fin n → ℝ)
    (hmem : ∀ i, gamma i ∈ Icc t0 (t0 + h))
    (hstair : ∀ t ∈ Icc t0 (t0 + h),
      N t0 + ∑ i, (if gamma i < t then mult i else 0) ≤ N t)
    {bound : ℕ}
    (hpin :
      ((∫ t in t0..(t0 + h), input.F t) + input.sBound -
        ∑ i, mult i * (t0 + h - gamma i)) / h < (bound : ℝ) + 1) :
    ZetaMultiplicityCountUpperBound t0 bound :=
  zetaMultiplicityCountUpperBound_of_lt hN
    (lt_of_le_of_lt
      (turing_upper_bound hN.mono hh gamma mult hmem hstair
        (input.integral_le hN.mono hh))
      hpin)

/-- The same conclusion in the form the finite-height verifier consumes. -/
theorem zetaZeroCountUpperBound_of_turing {N : ℝ → ℝ}
    (hN : SymmetricCountFunction N) {t0 h : ℝ} (hh : 0 < h)
    (input : TuringAnalyticInput N t0 h)
    {n : ℕ} (gamma : Fin n → ℝ) (mult : Fin n → ℝ)
    (hmem : ∀ i, gamma i ∈ Icc t0 (t0 + h))
    (hstair : ∀ t ∈ Icc t0 (t0 + h),
      N t0 + ∑ i, (if gamma i < t then mult i else 0) ≤ N t)
    {bound : ℕ}
    (hpin :
      ((∫ t in t0..(t0 + h), input.F t) + input.sBound -
        ∑ i, mult i * (t0 + h - gamma i)) / h < (bound : ℝ) + 1) :
    ZetaZeroCountUpperBound t0 bound :=
  (zetaMultiplicityCountUpperBound_of_turing hN hh input gamma mult hmem hstair
    hpin).toZetaZeroCountUpperBound

end SparkInterval.Zeta
