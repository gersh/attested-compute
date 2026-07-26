/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.PsiEndpointArithmetic

/-!
# Exact source semantics for the CH25 Chebyshev-psi campaign

This file isolates the small, kernel-checked argument that turns directed Q64
prefix enclosures and exact integer endpoint guards into the real-variable
statement of CH25 Lemma 9.2.  The source-scale producer and independent replay
must still supply `SourceScaleEvidence`; no inhabitant is postulated here.

The lower guard is checked at the right side of each unit slab.  It is weak at
ordinary right endpoints, because every point inside the slab is strictly to
their left, and strict at the closed source endpoint.  The upper guard is
checked immediately after the jumps contributing to the current integral
prefix.  This is the same monotonic endpoint reduction used by the C++ worker.
-/

set_option autoImplicit false
set_option maxRecDepth 1000000

namespace SparkInterval.TernaryGoldbach.PsiSourceSemantics

open scoped Nat

/-- Directed Q64 enclosure of one integral Chebyshev-psi prefix. -/
structure State where
  lowerQ64 : Nat
  upperQ64 : Nat
  deriving Repr, DecidableEq

/-- The worker state encloses Mathlib's exact Chebyshev `psi` definition. -/
def PrefixRealization (n : Nat) (state : State) : Prop :=
  (state.lowerQ64 : Real) / scale ≤ Chebyshev.psi n ∧
    Chebyshev.psi n ≤ (state.upperQ64 : Real) / scale

/-- Endpoint obligations for the unit slab whose step-function value is the
prefix through `n`. -/
def SourceRowSafe (n : Nat) (state : State) : Prop :=
  UpperEndpointSafe n state.upperQ64 ∧
    (n < sourceLimit → LowerEndpointSafe (n + 1) false state.lowerQ64) ∧
    (n = sourceLimit → LowerEndpointSafe n true state.lowerQ64)

def SourceRowPredicate (n : Nat) (state : State) : Prop :=
  PrefixRealization n state ∧ SourceRowSafe n state

/-- Explicit source-scale premise supplied by the registered physical run.
It fixes every natural prefix used by the real step-function reduction. -/
structure SourceScaleEvidence where
  stateAt : Nat → State
  row : ∀ n, 1 ≤ n → n ≤ sourceLimit →
    SourceRowPredicate n (stateAt n)

/-- Source-shaped real proposition, with the paper's strict lower inequality
and the explicit outward rational upper enclosure. -/
def SourceClaim : Prop :=
  ∀ x : Real, 1 ≤ x → x ≤ sourceLimit →
    -(Real.sqrt 2) < (Chebyshev.psi x - x) / Real.sqrt x ∧
      (Chebyshev.psi x - x) / Real.sqrt x ≤
        (upperNumerator : Real) / upperDenominator

theorem lowerEndpointSafe_real
    {right lowerQ64 : Nat}
    (hsafe : LowerEndpointSafe right false lowerQ64) :
    (right : Real) - (lowerQ64 : Real) / scale ≤
      Real.sqrt (2 * right) := by
  simp only [LowerEndpointSafe, Bool.false_eq_true, ↓reduceIte] at hsafe
  by_cases hdNonpos : lowerDifference right lowerQ64 ≤ 0
  · have hdNonposReal : (lowerDifference right lowerQ64 : Real) ≤ 0 := by
      exact_mod_cast hdNonpos
    rw [lowerDifference_cast] at hdNonposReal
    have hsqrt : 0 ≤ Real.sqrt (2 * (right : Real)) := Real.sqrt_nonneg _
    have hscale := scale_pos
    apply le_trans ?_ hsqrt
    apply (sub_nonpos.mpr ?_)
    exact (le_div_iff₀ hscale).2 (by nlinarith)
  · have hsquare := hsafe.resolve_left hdNonpos
    have hdPos : 0 < lowerDifference right lowerQ64 := lt_of_not_ge hdNonpos
    have habsInt :
        ((lowerDifference right lowerQ64).natAbs : Int) =
          lowerDifference right lowerQ64 := Int.natAbs_of_nonneg hdPos.le
    have habsReal :
        ((lowerDifference right lowerQ64).natAbs : Real) =
          (lowerDifference right lowerQ64 : Real) := by
      calc
        ((lowerDifference right lowerQ64).natAbs : Real) =
            (((lowerDifference right lowerQ64).natAbs : Int) : Real) := by
              norm_num
        _ = (lowerDifference right lowerQ64 : Real) :=
          congrArg (fun value : Int ↦ (value : Real)) habsInt
    have hsquareReal :
        ((lowerDifference right lowerQ64).natAbs : Real) ^ 2 ≤
          2 * (right : Real) * (scale : Real) ^ 2 := by
      exact_mod_cast hsquare
    rw [habsReal] at hsquareReal
    have hscale := scale_pos
    have hdiff : 0 ≤ (lowerDifference right lowerQ64 : Real) := by
      exact_mod_cast hdPos.le
    have heq :
        (right : Real) - (lowerQ64 : Real) / scale =
          (lowerDifference right lowerQ64 : Real) / scale := by
      rw [lowerDifference_cast]
      field_simp
    rw [heq]
    apply (Real.le_sqrt (div_nonneg hdiff hscale.le) (by positivity)).2
    rw [div_pow]
    exact (div_le_iff₀ (sq_pos_of_pos hscale)).2 (by
      simpa [mul_assoc] using hsquareReal)

theorem lowerEndpointSafe_strict_real
    {right lowerQ64 : Nat} (hright : 0 < right)
    (hsafe : LowerEndpointSafe right true lowerQ64) :
    (right : Real) - (lowerQ64 : Real) / scale <
      Real.sqrt (2 * right) := by
  simp only [LowerEndpointSafe, ↓reduceIte] at hsafe
  by_cases hdNonpos : lowerDifference right lowerQ64 ≤ 0
  · have hdNonposReal : (lowerDifference right lowerQ64 : Real) ≤ 0 := by
      exact_mod_cast hdNonpos
    rw [lowerDifference_cast] at hdNonposReal
    have hsqrt : 0 < Real.sqrt (2 * (right : Real)) := Real.sqrt_pos.2 (by
      positivity)
    have hscale := scale_pos
    apply lt_of_le_of_lt ?_ hsqrt
    apply (sub_nonpos.mpr ?_)
    exact (le_div_iff₀ hscale).2 (by nlinarith)
  · have hsquare := hsafe.resolve_left hdNonpos
    have hdPos : 0 < lowerDifference right lowerQ64 := lt_of_not_ge hdNonpos
    have habsInt :
        ((lowerDifference right lowerQ64).natAbs : Int) =
          lowerDifference right lowerQ64 := Int.natAbs_of_nonneg hdPos.le
    have habsReal :
        ((lowerDifference right lowerQ64).natAbs : Real) =
          (lowerDifference right lowerQ64 : Real) := by
      calc
        ((lowerDifference right lowerQ64).natAbs : Real) =
            (((lowerDifference right lowerQ64).natAbs : Int) : Real) := by
              norm_num
        _ = (lowerDifference right lowerQ64 : Real) :=
          congrArg (fun value : Int ↦ (value : Real)) habsInt
    have hsquareReal :
        ((lowerDifference right lowerQ64).natAbs : Real) ^ 2 <
          2 * (right : Real) * (scale : Real) ^ 2 := by
      exact_mod_cast hsquare
    rw [habsReal] at hsquareReal
    have hscale := scale_pos
    have hdiff : 0 ≤ (lowerDifference right lowerQ64 : Real) := by
      exact_mod_cast hdPos.le
    have heq :
        (right : Real) - (lowerQ64 : Real) / scale =
          (lowerDifference right lowerQ64 : Real) / scale := by
      rw [lowerDifference_cast]
      field_simp
    rw [heq]
    apply (Real.lt_sqrt (div_nonneg hdiff hscale.le)).2
    rw [div_pow]
    exact (div_lt_iff₀ (sq_pos_of_pos hscale)).2 (by
      simpa [mul_assoc] using hsquareReal)

private theorem floor_upper {x : Real} {limit : Nat}
    (hx0 : 0 ≤ x) (hx : x ≤ limit) : ⌊x⌋₊ ≤ limit := by
  exact_mod_cast (Nat.floor_le hx0).trans hx

/-- The function `x - sqrt (2*x)` is strictly increasing on `[1, ∞)`.
This algebraic two-point form avoids importing a differentiability argument. -/
theorem lowerBarrier_strict
    {x right lower : Real}
    (hx : 1 ≤ x) (hxr : x < right)
    (hright : right - lower ≤ Real.sqrt (2 * right)) :
    x - lower < Real.sqrt (2 * x) := by
  let a := Real.sqrt (2 * x)
  let b := Real.sqrt (2 * right)
  have hx0 : 0 ≤ 2 * x := by positivity
  have hrightPos : 0 < right := by nlinarith
  have hright0 : 0 ≤ 2 * right := by positivity
  have ha0 : 0 ≤ a := Real.sqrt_nonneg _
  have hb0 : 0 ≤ b := Real.sqrt_nonneg _
  have haSq : a ^ 2 = 2 * x := Real.sq_sqrt hx0
  have hbSq : b ^ 2 = 2 * right := Real.sq_sqrt hright0
  have hab : a < b := Real.sqrt_lt_sqrt hx0 (by nlinarith)
  have haOne : 1 < a := by
    rw [Real.lt_sqrt (by norm_num : (0 : Real) ≤ 1)]
    nlinarith
  have hdelta : b - a < right - x := by
    have hdeltaPos : 0 < b - a := by linarith
    have hsum : 2 < b + a := by nlinarith
    have hproduct : 2 * (b - a) < (b + a) * (b - a) :=
      mul_lt_mul_of_pos_right hsum hdeltaPos
    have hidentity : (b + a) * (b - a) = 2 * (right - x) := by
      nlinarith [haSq, hbSq]
    by_contra hnot
    have hle : right - x ≤ b - a := le_of_not_gt hnot
    nlinarith
  dsimp [a, b] at hdelta
  nlinarith

/-- Exact Q64 rows through the source endpoint imply the complete
real-variable CH25 Lemma 9.2 proposition. -/
theorem sourceClaim_of_evidence (evidence : SourceScaleEvidence) :
    SourceClaim := by
  intro x hxLower hxUpper
  have hx : 0 < x := lt_of_lt_of_le (by norm_num) hxLower
  let n := ⌊x⌋₊
  have hnLower : 1 ≤ n := Nat.le_floor
    (show ((1 : Nat) : Real) ≤ x by simpa using hxLower)
  have hnUpper : n ≤ sourceLimit := floor_upper hx.le hxUpper
  have hnCast : (n : Real) ≤ x := Nat.floor_le hx.le
  have hnx : Chebyshev.psi x = Chebyshev.psi n :=
    Chebyshev.psi_eq_psi_coe_floor x
  rcases evidence.row n hnLower hnUpper with ⟨hprefix, hsafe⟩
  have hsqrt : 0 < Real.sqrt x := Real.sqrt_pos.2 hx
  constructor
  · have hlower : x - Chebyshev.psi x < Real.sqrt (2 * x) := by
      by_cases hnTerminal : n = sourceLimit
      · have hxEq : x = sourceLimit := by
          have hnEqReal : (n : Real) = sourceLimit := by
            exact_mod_cast hnTerminal
          nlinarith
        have hterminal := lowerEndpointSafe_strict_real
          (show 0 < n by omega) (hsafe.2.2 hnTerminal)
        simp only [hnTerminal] at hterminal
        have hprefixLower := hprefix.1
        simp only [hnTerminal] at hprefixLower
        rw [hnx, hxEq, hnTerminal]
        apply lt_of_le_of_lt ?_ hterminal
        linarith
      · have hnLt : n < sourceLimit := lt_of_le_of_ne hnUpper hnTerminal
        have hright := lowerEndpointSafe_real (hsafe.2.1 hnLt)
        refine lowerBarrier_strict
          (right := ((n + 1 : Nat) : Real))
          (lower := Chebyshev.psi x) hxLower ?_ ?_
        · simpa [n] using Nat.lt_floor_add_one x
        · calc
            ((n + 1 : Nat) : Real) - Chebyshev.psi x ≤
                ((n + 1 : Nat) : Real) -
                  (evidence.stateAt n).lowerQ64 / scale := by
                    rw [hnx]
                    linarith [hprefix.1]
            _ ≤ Real.sqrt (2 * ((n + 1 : Nat) : Real)) := hright
    have hsqrtMul : Real.sqrt (2 * x) = Real.sqrt 2 * Real.sqrt x := by
      exact Real.sqrt_mul (by norm_num : (0 : Real) ≤ 2) x
    rw [hsqrtMul] at hlower
    exact (lt_div_iff₀ hsqrt).2 (by nlinarith)
  · have hupperEndpoint := upperEndpointSafe_real hsafe.1
    have hcoefficient :
        (0 : Real) ≤ (upperNumerator : Real) / upperDenominator := by
      positivity
    have hsqrtMono : Real.sqrt n ≤ Real.sqrt x := by gcongr
    apply (div_le_iff₀ hsqrt).2
    calc
      Chebyshev.psi x - x = Chebyshev.psi n - x := by rw [hnx]
      _ ≤ (evidence.stateAt n).upperQ64 / scale - x := by
        linarith [hprefix.2]
      _ ≤ (evidence.stateAt n).upperQ64 / scale - n := by
        linarith
      _ ≤ ((upperNumerator : Real) / upperDenominator) * Real.sqrt n :=
        hupperEndpoint
      _ ≤ ((upperNumerator : Real) / upperDenominator) * Real.sqrt x :=
        mul_le_mul_of_nonneg_left hsqrtMono hcoefficient

end SparkInterval.TernaryGoldbach.PsiSourceSemantics
