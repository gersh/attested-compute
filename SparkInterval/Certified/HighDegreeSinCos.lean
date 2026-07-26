/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.SinCos

/-!
# Higher-degree certified rational sine and cosine

The original evaluator in `Certified.SinCos` deliberately starts from a very
small two-term Taylor base.  That is a useful simple reference construction,
but producing binary64-width roots requires many double-angle steps.

This module supplies a higher-degree base obtained from the first `terms`
terms of the complex exponential series.  Its two rational coordinates are
computed exactly.  `Complex.exp_bound` supplies the factorial tail bound, so
the executable result remains fully checked by Lean's kernel.
-/

set_option autoImplicit false

namespace SparkInterval.Certified

open SparkInterval.Certificate

/-! ## Exact rational coordinates of powers of `x * I` -/

/-- Real and imaginary coordinates of `(x * I) ^ n`, represented over `ℚ`. -/
def imaginaryPowerQ (x : ℚ) : ℕ → ℚ × ℚ
  | 0 => (1, 0)
  | n + 1 =>
      let previous := imaginaryPowerQ x n
      (-previous.2 * x, previous.1 * x)

/-- Embed a pair of rational coordinates into `ℂ`. -/
def rationalPairToComplex (p : ℚ × ℚ) : ℂ :=
  (((p.1 : ℚ) : ℝ) : ℂ) + (((p.2 : ℚ) : ℝ) : ℂ) * Complex.I

theorem imaginaryPowerQ_toComplex (x : ℚ) (n : ℕ) :
    rationalPairToComplex (imaginaryPowerQ x n) =
      (((x : ℝ) : ℂ) * Complex.I) ^ n := by
  induction n with
  | zero =>
      simp [imaginaryPowerQ, rationalPairToComplex]
  | succ n ih =>
      rw [pow_succ, ← ih]
      simp only [imaginaryPowerQ, rationalPairToComplex]
      push_cast
      ring_nf
      rw [Complex.I_sq]
      ring

theorem imaginaryPowerQ_fst_cast (x : ℚ) (n : ℕ) :
    (((imaginaryPowerQ x n).1 : ℚ) : ℝ) =
      ((((x : ℝ) : ℂ) * Complex.I) ^ n).re := by
  have h := congrArg Complex.re (imaginaryPowerQ_toComplex x n)
  simpa [rationalPairToComplex] using h

theorem imaginaryPowerQ_snd_cast (x : ℚ) (n : ℕ) :
    (((imaginaryPowerQ x n).2 : ℚ) : ℝ) =
      ((((x : ℝ) : ℂ) * Complex.I) ^ n).im := by
  have h := congrArg Complex.im (imaginaryPowerQ_toComplex x n)
  simpa [rationalPairToComplex] using h

/-! ## Truncated exponential coordinates and exact tail -/

/-- Specification sum for the real coordinate of the first `terms`
complex-exponential terms at `x*I`. -/
def cosTaylorSumQ (terms : ℕ) (x : ℚ) : ℚ :=
  ∑ m ∈ Finset.range terms, (imaginaryPowerQ x m).1 / (m.factorial : ℚ)

/-- Specification sum for the imaginary coordinate of the first `terms`
complex-exponential terms at `x*I`. -/
def sinTaylorSumQ (terms : ℕ) (x : ℚ) : ℚ :=
  ∑ m ∈ Finset.range terms, (imaginaryPowerQ x m).2 / (m.factorial : ℚ)

/-- Single-pass state for the executable exponential polynomial. -/
structure SinCosTaylorState where
  power : ℚ × ℚ
  factorial : Nat
  cosine : ℚ
  sine : ℚ
  deriving Repr

/-- Evaluate all Taylor terms in one pass.  State `n` carries `(x*I)^n`,
`n!`, and the coordinate sums for indices `< n`; unlike the specification
sums it never recomputes an earlier power. -/
def sinCosTaylorState (x : ℚ) : Nat → SinCosTaylorState
  | 0 =>
      { power := (1, 0)
        factorial := 1
        cosine := 0
        sine := 0 }
  | n + 1 =>
      let state := sinCosTaylorState x n
      { power := (-state.power.2 * x, state.power.1 * x)
        factorial := state.factorial * (n + 1)
        cosine := state.cosine + state.power.1 / (state.factorial : ℚ)
        sine := state.sine + state.power.2 / (state.factorial : ℚ) }

theorem sinCosTaylorState_spec (x : ℚ) (n : Nat) :
    (sinCosTaylorState x n).power = imaginaryPowerQ x n ∧
    (sinCosTaylorState x n).factorial = n.factorial ∧
    (sinCosTaylorState x n).cosine = cosTaylorSumQ n x ∧
    (sinCosTaylorState x n).sine = sinTaylorSumQ n x := by
  induction n with
  | zero =>
      simp [sinCosTaylorState, imaginaryPowerQ, cosTaylorSumQ, sinTaylorSumQ]
  | succ n ih =>
      rcases ih with ⟨hpower, hfactorial, hcosine, hsine⟩
      simp only [sinCosTaylorState]
      rw [hpower, hfactorial, hcosine, hsine]
      constructor
      · simp [imaginaryPowerQ]
      constructor
      · simp [Nat.factorial_succ, Nat.mul_comm]
      constructor
      · simp [cosTaylorSumQ, Finset.sum_range_succ]
      · simp [sinTaylorSumQ, Finset.sum_range_succ]

/-- Real coordinate of the first `terms` exponential terms, computed by the
single-pass recurrence. -/
def cosTaylorQ (terms : ℕ) (x : ℚ) : ℚ :=
  (sinCosTaylorState x terms).cosine

/-- Imaginary coordinate of the first `terms` exponential terms, computed by
the single-pass recurrence. -/
def sinTaylorQ (terms : ℕ) (x : ℚ) : ℚ :=
  (sinCosTaylorState x terms).sine

theorem cosTaylorQ_eq_sum (terms : Nat) (x : ℚ) :
    cosTaylorQ terms x = cosTaylorSumQ terms x :=
  (sinCosTaylorState_spec x terms).2.2.1

theorem sinTaylorQ_eq_sum (terms : Nat) (x : ℚ) :
    sinTaylorQ terms x = sinTaylorSumQ terms x :=
  (sinCosTaylorState_spec x terms).2.2.2

/-- Exact rational form of the `Complex.exp_bound` remainder. -/
def sinCosTaylorSlack (terms : ℕ) (x : ℚ) : ℚ :=
  |x| ^ terms * ((terms : ℚ) + 1) /
    ((terms.factorial : ℚ) * (terms : ℚ))

theorem cosTaylorQ_cast (terms : ℕ) (x : ℚ) :
    ((cosTaylorQ terms x : ℚ) : ℝ) =
      (∑ m ∈ Finset.range terms,
        ((((x : ℝ) : ℂ) * Complex.I) ^ m / (m.factorial : ℂ))).re := by
  rw [cosTaylorQ_eq_sum]
  unfold cosTaylorSumQ
  push_cast
  rw [Complex.re_sum]
  apply Finset.sum_congr rfl
  intro m hm
  rw [imaginaryPowerQ_fst_cast]
  simp

theorem sinTaylorQ_cast (terms : ℕ) (x : ℚ) :
    ((sinTaylorQ terms x : ℚ) : ℝ) =
      (∑ m ∈ Finset.range terms,
        ((((x : ℝ) : ℂ) * Complex.I) ^ m / (m.factorial : ℂ))).im := by
  rw [sinTaylorQ_eq_sum]
  unfold sinTaylorSumQ
  push_cast
  rw [Complex.im_sum]
  apply Finset.sum_congr rfl
  intro m hm
  rw [imaginaryPowerQ_snd_cast]
  simp

theorem sinCosTaylorSlack_cast (terms : ℕ) (x : ℚ) :
    ((sinCosTaylorSlack terms x : ℚ) : ℝ) =
      |(x : ℝ)| ^ terms * ((terms.succ : ℝ) *
        ((terms.factorial : ℝ) * (terms : ℝ))⁻¹) := by
  unfold sinCosTaylorSlack
  push_cast
  ring

/-- Higher-degree Taylor enclosure, valid for `|x| ≤ 1` and `0 < terms`. -/
def sinCosTaylorBase (terms : ℕ) (x : ℚ) :
    RatInterval × RatInterval :=
  let slack := sinCosTaylorSlack terms x
  (⟨sinTaylorQ terms x - slack, sinTaylorQ terms x + slack⟩,
   ⟨cosTaylorQ terms x - slack, cosTaylorQ terms x + slack⟩)

theorem sinCosTaylorBase_containsReal {terms : ℕ} (hterms : 0 < terms)
    {x : ℚ} (hx : |x| ≤ 1) :
    (sinCosTaylorBase terms x).1.ContainsReal (Real.sin (x : ℝ)) ∧
    (sinCosTaylorBase terms x).2.ContainsReal (Real.cos (x : ℝ)) := by
  let z : ℂ := ((x : ℝ) : ℂ) * Complex.I
  let approximation : ℂ :=
    ∑ m ∈ Finset.range terms, z ^ m / (m.factorial : ℂ)
  have hxR : |(x : ℝ)| ≤ 1 := by exact_mod_cast hx
  have hnorm : ‖z‖ = |(x : ℝ)| := by
    simp [z]
  have htail :
      ‖Complex.exp z - approximation‖ ≤
        |(x : ℝ)| ^ terms * ((terms.succ : ℝ) *
          ((terms.factorial : ℝ) * (terms : ℝ))⁻¹) := by
    simpa [approximation, hnorm] using
      (Complex.exp_bound (x := z) (by simpa [hnorm] using hxR) hterms)
  have hre :
      |Real.cos (x : ℝ) - (cosTaylorQ terms x : ℝ)| ≤
        (sinCosTaylorSlack terms x : ℝ) := by
    have := (Complex.abs_re_le_norm (Complex.exp z - approximation)).trans htail
    have hexp :
        (Complex.exp z).re = Real.cos (x : ℝ) := by
      simpa [z] using Complex.exp_ofReal_mul_I_re (x : ℝ)
    rw [Complex.sub_re, hexp] at this
    rw [sinCosTaylorSlack_cast]
    simpa [z, approximation, cosTaylorQ_cast] using this
  have him :
      |Real.sin (x : ℝ) - (sinTaylorQ terms x : ℝ)| ≤
        (sinCosTaylorSlack terms x : ℝ) := by
    have := (Complex.abs_im_le_norm (Complex.exp z - approximation)).trans htail
    have hexp :
        (Complex.exp z).im = Real.sin (x : ℝ) := by
      simpa [z] using Complex.exp_ofReal_mul_I_im (x : ℝ)
    rw [Complex.sub_im, hexp] at this
    rw [sinCosTaylorSlack_cast]
    simpa [z, approximation, sinTaylorQ_cast] using this
  obtain ⟨hsinLo, hsinHi⟩ := abs_le.mp him
  obtain ⟨hcosLo, hcosHi⟩ := abs_le.mp hre
  constructor
  · constructor
    · show
        (((sinCosTaylorBase terms x).1.lo : ℚ) : ℝ) ≤ Real.sin (x : ℝ)
      simp only [sinCosTaylorBase]
      push_cast
      linarith
    · show
        Real.sin (x : ℝ) ≤ (((sinCosTaylorBase terms x).1.hi : ℚ) : ℝ)
      simp only [sinCosTaylorBase]
      push_cast
      linarith
  · constructor
    · show
        (((sinCosTaylorBase terms x).2.lo : ℚ) : ℝ) ≤ Real.cos (x : ℝ)
      simp only [sinCosTaylorBase]
      push_cast
      linarith
    · show
        Real.cos (x : ℝ) ≤ (((sinCosTaylorBase terms x).2.hi : ℚ) : ℝ)
      simp only [sinCosTaylorBase]
      push_cast
      linarith

/-! ## Scale, evaluate, and climb -/

/-- Higher-degree sine/cosine evaluator.  Compared with `sinCosSmall`, the
caller can use a much smaller `depth` at binary64 target accuracy. -/
def sinCosTaylorSmall
    (terms depth prec : ℕ) (x : ℚ) : RatInterval × RatInterval :=
  climb prec depth (sinCosTaylorBase terms (x / 2 ^ depth))

theorem sinCosTaylorSmall_containsReal
    {terms : ℕ} (hterms : 0 < terms) (depth prec : ℕ) {x : ℚ}
    (hx : |x| ≤ 2 ^ depth) :
    (sinCosTaylorSmall terms depth prec x).1.ContainsReal
        (Real.sin (x : ℝ)) ∧
    (sinCosTaylorSmall terms depth prec x).2.ContainsReal
        (Real.cos (x : ℝ)) := by
  have h2 : (0 : ℚ) < 2 ^ depth := by positivity
  have hsmall : |x / 2 ^ depth| ≤ 1 := by
    rw [abs_div, abs_of_pos h2, div_le_one h2]
    exact hx
  have hbase := sinCosTaylorBase_containsReal hterms hsmall
  have h := climb_containsReal prec depth
    (sinCosTaylorBase terms (x / 2 ^ depth)) hbase.1 hbase.2
  have hy :
      (2 : ℝ) ^ depth * ((x / 2 ^ depth : ℚ) : ℝ) = (x : ℝ) := by
    push_cast
    field_simp
  rw [hy] at h
  exact h

/-! ## Period reduction and interval arguments -/

/-- Certified higher-degree enclosures of `sin x` and `cos x`.

The option is fail-closed: it returns `none` unless the reduced rational
argument is inside the scale-and-climb design range. -/
def sinCosTaylorQ
    (terms depth prec : ℕ) (x : ℚ) :
    Option (RatInterval × RatInterval) :=
  if |(reduceInterval x).lo| ≤ 2 ^ depth then
    some (widenPair ((reduceInterval x).hi - (reduceInterval x).lo)
      (sinCosTaylorSmall terms depth prec (reduceInterval x).lo))
  else
    none

theorem sinCosTaylorQ_containsReal
    {terms : ℕ} (hterms : 0 < terms)
    {depth prec : ℕ} {x : ℚ} {S C : RatInterval}
    (h : sinCosTaylorQ terms depth prec x = some (S, C)) :
    S.ContainsReal (Real.sin (x : ℝ)) ∧
    C.ContainsReal (Real.cos (x : ℝ)) := by
  unfold sinCosTaylorQ at h
  split_ifs at h with hguard
  simp only [widenPair, Option.some.injEq, Prod.mk.injEq] at h
  obtain ⟨hS, hC⟩ := h
  subst hS
  subst hC
  have hJr := reduceInterval_containsReal x
  have hsmall :=
    sinCosTaylorSmall_containsReal hterms depth prec hguard
  have hd :
      |((x : ℝ) - (reduceK x : ℝ) * (2 * Real.pi)) -
          ((reduceInterval x).lo : ℝ)| ≤
        (((reduceInterval x).hi - (reduceInterval x).lo : ℚ) : ℝ) := by
    have h1 := hJr.1
    have h2 := hJr.2
    rw [abs_le]
    push_cast
    constructor <;> linarith
  have hsin := widen_containsReal_of_abs_le hsmall.1
    ((Real.abs_sin_sub_sin_le _ _).trans hd)
  have hcos := widen_containsReal_of_abs_le hsmall.2
    ((Real.abs_cos_sub_cos_le _ _).trans hd)
  rw [Real.sin_sub_int_mul_two_pi] at hsin
  rw [Real.cos_sub_int_mul_two_pi] at hcos
  exact ⟨hsin, hcos⟩

/-- Certified higher-degree sine/cosine enclosures over a rational interval. -/
def sinCosTaylorInterval
    (terms depth prec : ℕ) (I : RatInterval) :
    Option (RatInterval × RatInterval) :=
  Option.map (widenPair (I.hi - I.lo))
    (sinCosTaylorQ terms depth prec I.lo)

theorem sinCosTaylorInterval_containsReal
    {terms : ℕ} (hterms : 0 < terms)
    {depth prec : ℕ} {I : RatInterval}
    {S C : RatInterval} {y : ℝ}
    (h : sinCosTaylorInterval terms depth prec I = some (S, C))
    (hy : I.ContainsReal y) :
    S.ContainsReal (Real.sin y) ∧ C.ContainsReal (Real.cos y) := by
  rcases hq : sinCosTaylorQ terms depth prec I.lo with _ | ⟨S₀, C₀⟩
  · simp [sinCosTaylorInterval, hq] at h
  · simp only [sinCosTaylorInterval, hq, Option.map_some, widenPair,
      Option.some.injEq, Prod.mk.injEq] at h
    obtain ⟨hS, hC⟩ := h
    subst hS
    subst hC
    have hbase := sinCosTaylorQ_containsReal hterms hq
    have hd : |y - ((I.lo : ℚ) : ℝ)| ≤ ((I.hi - I.lo : ℚ) : ℝ) := by
      have h1 := hy.1
      have h2 := hy.2
      rw [abs_le]
      push_cast
      constructor <;> linarith
    exact
      ⟨widen_containsReal_of_abs_le hbase.1
          ((Real.abs_sin_sub_sin_le _ _).trans hd),
        widen_containsReal_of_abs_le hbase.2
          ((Real.abs_cos_sub_cos_le _ _).trans hd)⟩

/-! ## Already-reduced bounded interval arguments -/

/-- Certified higher-degree sine/cosine enclosures for an interval whose
lower endpoint is already in the scale-and-climb design range.

Unlike `sinCosTaylorInterval`, this entry point deliberately performs no
second period reduction. It is intended for callers that already constructed
a proved narrow interval for a period-reduced angle. Avoiding a second
reduction also avoids widening the result by an unrelated, lower-precision
enclosure of `2 * π`. -/
def sinCosTaylorBoundedInterval
    (terms depth prec : ℕ) (I : RatInterval) :
    Option (RatInterval × RatInterval) :=
  if |I.lo| ≤ 2 ^ depth then
    some (widenPair (I.hi - I.lo)
      (sinCosTaylorSmall terms depth prec I.lo))
  else
    none

theorem sinCosTaylorBoundedInterval_containsReal
    {terms : ℕ} (hterms : 0 < terms)
    {depth prec : ℕ} {I : RatInterval}
    {S C : RatInterval} {y : ℝ}
    (h :
      sinCosTaylorBoundedInterval terms depth prec I = some (S, C))
    (hy : I.ContainsReal y) :
    S.ContainsReal (Real.sin y) ∧ C.ContainsReal (Real.cos y) := by
  unfold sinCosTaylorBoundedInterval at h
  split at h
  next hguard =>
    simp only [widenPair, Option.some.injEq, Prod.mk.injEq] at h
    obtain ⟨hS, hC⟩ := h
    subst hS
    subst hC
    have hbase :=
      sinCosTaylorSmall_containsReal hterms depth prec hguard
    have hd :
        |y - ((I.lo : ℚ) : ℝ)| ≤
          (((I.hi - I.lo : ℚ) : ℝ)) := by
      have h1 := hy.1
      have h2 := hy.2
      rw [abs_le]
      push_cast
      constructor <;> linarith
    exact
      ⟨widen_containsReal_of_abs_le hbase.1
          ((Real.abs_sin_sub_sin_le _ _).trans hd),
        widen_containsReal_of_abs_le hbase.2
          ((Real.abs_cos_sub_cos_le _ _).trans hd)⟩
  next hguard =>
    simp at h

end SparkInterval.Certified
