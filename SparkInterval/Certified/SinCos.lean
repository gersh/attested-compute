import SparkInterval.Certified.Rounding

/-!
# Certified rational-interval enclosures of `Real.sin` and `Real.cos`

This file provides executable, fully proved rational-interval enclosures of
`Real.sin` and `Real.cos` at rational arguments.  The construction has three
layers:

* **Base** (`sinCosBase`): for `|x| ≤ 1`, the two-term Taylor polynomials
  widened by the Mathlib remainder bound `|x|^4 * (5/96)`
  (`Real.sin_bound` / `Real.cos_bound`).
* **Climb** (`sinCosSmall`): for `|x| ≤ 2 ^ depth`, evaluate the base layer at
  `x / 2 ^ depth` and apply the interval double-angle recurrences
  `sin (2y) = 2 sin y cos y` and `cos (2y) = 2 cos y ^ 2 - 1` `depth` times,
  outward-rounding to `prec` dyadic bits at each step.
* **Reduction** (`sinCosQ`): reduce the argument modulo `2π` using the 20-digit
  pi bounds `Real.pi_gt_d20` / `Real.pi_lt_d20`, evaluate `sinCosSmall` at the
  lower endpoint of the reduced interval, and widen by its width using that
  `sin` and `cos` are 1-Lipschitz.

`sinCosInterval` extends `sinCosQ` to rational-interval arguments, again via
the Lipschitz bound.  Every computation is executable exact rational
arithmetic; no axioms, `sorry`, or `native_decide` are used.
-/

set_option autoImplicit false

namespace SparkInterval.Certified

open SparkInterval.Certificate

/-! ## Layer A: base enclosure for `|x| ≤ 1` -/

/-- Two-term Taylor enclosures of `sin x` and `cos x`, sound for `|x| ≤ 1`.
The remainder budget `x ^ 4 * (5 / 96)` is an exact rational equal to
`|x| ^ 4 * (5 / 96)`. -/
def sinCosBase (x : ℚ) : RatInterval × RatInterval :=
  (⟨x - x ^ 3 / 6 - x ^ 4 * (5 / 96), x - x ^ 3 / 6 + x ^ 4 * (5 / 96)⟩,
   ⟨1 - x ^ 2 / 2 - x ^ 4 * (5 / 96), 1 - x ^ 2 / 2 + x ^ 4 * (5 / 96)⟩)

theorem sinCosBase_fst_containsReal {x : ℚ} (hx : |x| ≤ 1) :
    (sinCosBase x).1.ContainsReal (Real.sin (x : ℝ)) := by
  have hxR : |(x : ℝ)| ≤ 1 := by exact_mod_cast hx
  have h := Real.sin_bound hxR
  have habs : |(x : ℝ)| ^ 4 = (x : ℝ) ^ 4 := by
    rw [pow_abs, abs_of_nonneg (by positivity : (0 : ℝ) ≤ (x : ℝ) ^ 4)]
  rw [habs] at h
  obtain ⟨h1, h2⟩ := abs_le.mp h
  constructor
  · show ((x - x ^ 3 / 6 - x ^ 4 * (5 / 96) : ℚ) : ℝ) ≤ Real.sin (x : ℝ)
    push_cast
    linarith
  · show Real.sin (x : ℝ) ≤ ((x - x ^ 3 / 6 + x ^ 4 * (5 / 96) : ℚ) : ℝ)
    push_cast
    linarith

theorem sinCosBase_snd_containsReal {x : ℚ} (hx : |x| ≤ 1) :
    (sinCosBase x).2.ContainsReal (Real.cos (x : ℝ)) := by
  have hxR : |(x : ℝ)| ≤ 1 := by exact_mod_cast hx
  have h := Real.cos_bound hxR
  have habs : |(x : ℝ)| ^ 4 = (x : ℝ) ^ 4 := by
    rw [pow_abs, abs_of_nonneg (by positivity : (0 : ℝ) ≤ (x : ℝ) ^ 4)]
  rw [habs] at h
  obtain ⟨h1, h2⟩ := abs_le.mp h
  constructor
  · show ((1 - x ^ 2 / 2 - x ^ 4 * (5 / 96) : ℚ) : ℝ) ≤ Real.cos (x : ℝ)
    push_cast
    linarith
  · show Real.cos (x : ℝ) ≤ ((1 - x ^ 2 / 2 + x ^ 4 * (5 / 96) : ℚ) : ℝ)
    push_cast
    linarith

/-! ## Layer B: double-angle climb -/

private theorem point_two_containsReal :
    (RatInterval.point 2).ContainsReal (2 : ℝ) := by
  simpa using RatInterval.point_containsReal (2 : ℚ)

private theorem point_one_containsReal :
    (RatInterval.point 1).ContainsReal (1 : ℝ) := by
  simpa using RatInterval.point_containsReal (1 : ℚ)

/-- One interval double-angle step: from enclosures of `(sin y, cos y)` to
enclosures of `(sin (2y), cos (2y))`, outward-rounded to `prec` dyadic bits. -/
def doubleStep (prec : ℕ) (SC : RatInterval × RatInterval) :
    RatInterval × RatInterval :=
  (roundOut prec (((RatInterval.point 2).mul SC.1).mul SC.2),
   roundOut prec
     (((RatInterval.point 2).mul (SC.2.powNat 2)).sub (RatInterval.point 1)))

theorem doubleStep_containsReal {prec : ℕ} {SC : RatInterval × RatInterval}
    {y : ℝ} (hS : SC.1.ContainsReal (Real.sin y))
    (hC : SC.2.ContainsReal (Real.cos y)) :
    (doubleStep prec SC).1.ContainsReal (Real.sin (2 * y)) ∧
    (doubleStep prec SC).2.ContainsReal (Real.cos (2 * y)) := by
  constructor
  · rw [Real.sin_two_mul]
    exact roundOut_containsReal
      (RatInterval.mul_containsReal
        (RatInterval.mul_containsReal point_two_containsReal hS) hC)
  · rw [Real.cos_two_mul]
    exact roundOut_containsReal
      (RatInterval.sub_containsReal
        (RatInterval.mul_containsReal point_two_containsReal
          (RatInterval.powNat_containsReal hC 2)) point_one_containsReal)

/-- Iterate `doubleStep` `n` times. -/
def climb (prec : ℕ) : ℕ → RatInterval × RatInterval → RatInterval × RatInterval
  | 0, SC => SC
  | n + 1, SC => doubleStep prec (climb prec n SC)

theorem climb_containsReal (prec : ℕ) {y : ℝ} :
    ∀ (n : ℕ) (SC : RatInterval × RatInterval),
      SC.1.ContainsReal (Real.sin y) → SC.2.ContainsReal (Real.cos y) →
      (climb prec n SC).1.ContainsReal (Real.sin (2 ^ n * y)) ∧
      (climb prec n SC).2.ContainsReal (Real.cos (2 ^ n * y))
  | 0, SC, hS, hC => by
      simpa [climb] using And.intro hS hC
  | n + 1, SC, hS, hC => by
      have ih := climb_containsReal prec n SC hS hC
      have h2 : (2 : ℝ) ^ (n + 1) * y = 2 * ((2 : ℝ) ^ n * y) := by ring
      rw [h2]
      exact doubleStep_containsReal ih.1 ih.2

/-- Enclosures of `sin x` and `cos x`, sound for `|x| ≤ 2 ^ depth`:
evaluate the base layer at `x / 2 ^ depth` and double the angle `depth`
times, rounding outward to `prec` dyadic bits at each step. -/
def sinCosSmall (depth prec : ℕ) (x : ℚ) : RatInterval × RatInterval :=
  climb prec depth (sinCosBase (x / 2 ^ depth))

theorem sinCosSmall_containsReal (depth prec : ℕ) {x : ℚ}
    (hx : |x| ≤ 2 ^ depth) :
    (sinCosSmall depth prec x).1.ContainsReal (Real.sin (x : ℝ)) ∧
    (sinCosSmall depth prec x).2.ContainsReal (Real.cos (x : ℝ)) := by
  have h2 : (0 : ℚ) < 2 ^ depth := by positivity
  have hsmall : |x / 2 ^ depth| ≤ 1 := by
    rw [abs_div, abs_of_pos h2, div_le_one h2]
    exact hx
  have h := climb_containsReal prec depth (sinCosBase (x / 2 ^ depth))
    (sinCosBase_fst_containsReal hsmall) (sinCosBase_snd_containsReal hsmall)
  have hy : (2 : ℝ) ^ depth * ((x / 2 ^ depth : ℚ) : ℝ) = (x : ℝ) := by
    push_cast
    field_simp
  rw [hy] at h
  exact h

/-! ## Layer C: reduction modulo `2π` -/

/-- Exact rational lower bound of `π` (20 correct digits). -/
def piLoQ : ℚ := 314159265358979323846 / 10 ^ 20

/-- Exact rational upper bound of `π` (20 correct digits). -/
def piHiQ : ℚ := 314159265358979323847 / 10 ^ 20

theorem piLoQ_lt_pi : (piLoQ : ℝ) < Real.pi := by
  have h : ((piLoQ : ℚ) : ℝ) = (3.14159265358979323846 : ℝ) := by
    norm_num [piLoQ]
  rw [h]
  exact Real.pi_gt_d20

theorem pi_lt_piHiQ : Real.pi < (piHiQ : ℝ) := by
  have h : ((piHiQ : ℚ) : ℝ) = (3.14159265358979323847 : ℝ) := by
    norm_num [piHiQ]
  rw [h]
  exact Real.pi_lt_d20

/-- A rational interval enclosing `2 * π`. -/
def twoPiInterval : RatInterval := ⟨2 * piLoQ, 2 * piHiQ⟩

theorem twoPiInterval_containsReal :
    twoPiInterval.ContainsReal (2 * Real.pi) := by
  constructor
  · show ((2 * piLoQ : ℚ) : ℝ) ≤ 2 * Real.pi
    push_cast
    have := piLoQ_lt_pi
    linarith
  · show 2 * Real.pi ≤ ((2 * piHiQ : ℚ) : ℝ)
    push_cast
    have := pi_lt_piHiQ
    linarith

/-- Executable estimate of the number of turns to subtract.  No soundness
property about the choice of `k` is needed: any integer yields a valid
reduction. -/
def reduceK (x : ℚ) : ℤ := round (x / (2 * piLoQ))

/-- A rational interval enclosing the real number `x - reduceK x * (2π)`,
computed with proved interval operations so that the sign of `reduceK x` is
handled automatically. -/
def reduceInterval (x : ℚ) : RatInterval :=
  (RatInterval.point x).sub
    ((RatInterval.point (reduceK x : ℚ)).mul twoPiInterval)

theorem reduceInterval_containsReal (x : ℚ) :
    (reduceInterval x).ContainsReal
      ((x : ℝ) - (reduceK x : ℝ) * (2 * Real.pi)) := by
  have hk : (RatInterval.point (reduceK x : ℚ)).ContainsReal
      ((reduceK x : ℤ) : ℝ) := by
    simpa using RatInterval.point_containsReal ((reduceK x : ℤ) : ℚ)
  exact RatInterval.sub_containsReal (RatInterval.point_containsReal x)
    (RatInterval.mul_containsReal hk twoPiInterval_containsReal)

/-! ## Lipschitz widening -/

/-- If `I` encloses `a` and `|b - a| ≤ w`, then widening `I` by `w`
encloses `b`. -/
theorem widen_containsReal_of_abs_le {I : RatInterval} {w : ℚ} {a b : ℝ}
    (hI : I.ContainsReal a) (hab : |b - a| ≤ (w : ℝ)) :
    (widen w I).ContainsReal b := by
  obtain ⟨h1, h2⟩ := hI
  obtain ⟨h3, h4⟩ := abs_le.mp hab
  constructor
  · show ((I.lo - w : ℚ) : ℝ) ≤ b
    push_cast
    linarith
  · show b ≤ ((I.hi + w : ℚ) : ℝ)
    push_cast
    linarith

/-- Widen both components of a `(sin, cos)` enclosure pair. -/
def widenPair (w : ℚ) (SC : RatInterval × RatInterval) :
    RatInterval × RatInterval :=
  (widen w SC.1, widen w SC.2)

/-! ## Main entry points -/

/-- Certified enclosures of `sin x` and `cos x` for a rational argument `x`.

The argument is reduced modulo `2π`, `sinCosSmall` is evaluated at the lower
endpoint of the reduced interval, and both results are widened by the interval
width using that `sin` and `cos` are 1-Lipschitz.  Returns `none` only if the
reduced argument fails the (executable) guard `|·| ≤ 2 ^ depth`, which cannot
happen for `depth ≥ 3` and reasonable inputs. -/
def sinCosQ (depth prec : ℕ) (x : ℚ) : Option (RatInterval × RatInterval) :=
  if |(reduceInterval x).lo| ≤ 2 ^ depth then
    some (widenPair ((reduceInterval x).hi - (reduceInterval x).lo)
      (sinCosSmall depth prec (reduceInterval x).lo))
  else
    none

theorem sinCosQ_containsReal {depth prec : ℕ} {x : ℚ} {S C : RatInterval}
    (h : sinCosQ depth prec x = some (S, C)) :
    S.ContainsReal (Real.sin (x : ℝ)) ∧ C.ContainsReal (Real.cos (x : ℝ)) := by
  unfold sinCosQ at h
  split_ifs at h with hguard
  simp only [widenPair, Option.some.injEq, Prod.mk.injEq] at h
  obtain ⟨hS, hC⟩ := h
  subst hS
  subst hC
  have hJr := reduceInterval_containsReal x
  have hsmall := sinCosSmall_containsReal depth prec hguard
  have hd : |((x : ℝ) - (reduceK x : ℝ) * (2 * Real.pi)) -
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

/-- Certified enclosures of `sin` and `cos` over a rational interval
argument: evaluate at `I.lo` and widen by the interval width via the
1-Lipschitz bound. -/
def sinCosInterval (depth prec : ℕ) (I : RatInterval) :
    Option (RatInterval × RatInterval) :=
  Option.map (widenPair (I.hi - I.lo)) (sinCosQ depth prec I.lo)

theorem sinCosInterval_containsReal {depth prec : ℕ} {I : RatInterval}
    {S C : RatInterval} {y : ℝ}
    (h : sinCosInterval depth prec I = some (S, C))
    (hy : I.ContainsReal y) :
    S.ContainsReal (Real.sin y) ∧ C.ContainsReal (Real.cos y) := by
  rcases hq : sinCosQ depth prec I.lo with _ | ⟨S₀, C₀⟩
  · simp [sinCosInterval, hq] at h
  · simp only [sinCosInterval, hq, Option.map_some, widenPair,
      Option.some.injEq, Prod.mk.injEq] at h
    obtain ⟨hS, hC⟩ := h
    subst hS
    subst hC
    have hbase := sinCosQ_containsReal hq
    have hd : |y - ((I.lo : ℚ) : ℝ)| ≤ ((I.hi - I.lo : ℚ) : ℝ) := by
      have h1 := hy.1
      have h2 := hy.2
      rw [abs_le]
      push_cast
      constructor <;> linarith
    exact ⟨widen_containsReal_of_abs_le hbase.1
        ((Real.abs_sin_sub_sin_le _ _).trans hd),
      widen_containsReal_of_abs_le hbase.2
        ((Real.abs_cos_sub_cos_le _ _).trans hd)⟩

end SparkInterval.Certified

