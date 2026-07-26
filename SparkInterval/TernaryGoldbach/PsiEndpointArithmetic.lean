/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.NumberTheory.Chebyshev

/-!
# Exact endpoint arithmetic for the CH25 psi certificate

The C++ worker evaluates these predicates with arbitrary-precision integers.
This module proves once that an accepted integer guard implies the corresponding
directed real inequality.  Keeping it separate makes the source-scale
step-function proof small and prevents certificate consumers from expanding
the large normalization proof.
-/

set_option autoImplicit false
set_option maxRecDepth 1000000

namespace SparkInterval.TernaryGoldbach.PsiSourceSemantics

def scale : Nat := 2 ^ 64
def sourceLimit : Nat := 10_000_000_000_000
def upperNumerator : Nat := 19_764_819
def upperDenominator : Nat := 25_000_000

def lowerDifference (right : Nat) (lowerQ64 : Nat) : Int :=
  (right : Int) * scale - lowerQ64

def upperDifference (left : Nat) (upperQ64 : Nat) : Int :=
  (upperQ64 : Int) - (left : Int) * scale

def LowerEndpointSafe (right : Nat) (strict : Bool) (lowerQ64 : Nat) : Prop :=
  let difference := lowerDifference right lowerQ64
  difference ≤ 0 ∨
    if strict then
      difference.natAbs ^ 2 < 2 * right * scale ^ 2
    else
      difference.natAbs ^ 2 ≤ 2 * right * scale ^ 2

def UpperEndpointSafe (left : Nat) (upperQ64 : Nat) : Prop :=
  let difference := upperDifference left upperQ64
  difference ≤ 0 ∨
    difference.natAbs ^ 2 * upperDenominator ^ 2 ≤
      upperNumerator ^ 2 * left * scale ^ 2

theorem scale_pos : (0 : Real) < scale := by
  norm_num [scale]

theorem lowerDifference_cast
    (right lowerQ64 : Nat) :
    (lowerDifference right lowerQ64 : Real) =
      (right : Real) * scale - lowerQ64 := by
  norm_num [lowerDifference]

theorem upperDifference_cast
    (left upperQ64 : Nat) :
    (upperDifference left upperQ64 : Real) =
      (upperQ64 : Real) - (left : Real) * scale := by
  norm_num [upperDifference]

/-- Parameterized integer-to-real normalization.  Keeping the Q64 scale and
the rational constant abstract prevents the kernel proof term from expanding
their large decimal numerals. -/
theorem upperEndpointSafe_real_generic
    {left upperQ64 scaleN numerator denominator : Nat}
    (hscaleNat : 0 < scaleN) (hnumNat : 0 < numerator)
    (hdenNat : 0 < denominator)
    (hsafe :
      let difference : Int :=
        (upperQ64 : Int) - (left : Int) * scaleN
      difference ≤ 0 ∨
        difference.natAbs ^ 2 * denominator ^ 2 ≤
          numerator ^ 2 * left * scaleN ^ 2) :
    (upperQ64 : Real) / scaleN - left ≤
      ((numerator : Real) / denominator) * Real.sqrt left := by
  let difference : Int := (upperQ64 : Int) - (left : Int) * scaleN
  change difference ≤ 0 ∨
      difference.natAbs ^ 2 * denominator ^ 2 ≤
        numerator ^ 2 * left * scaleN ^ 2 at hsafe
  have hdifferenceCast : (difference : Real) =
      (upperQ64 : Real) - (left : Real) * scaleN := by
    dsimp [difference]
    norm_num
  have hscale : (0 : Real) < scaleN := by exact_mod_cast hscaleNat
  have hnum : (0 : Real) < numerator := by exact_mod_cast hnumNat
  have hden : (0 : Real) < denominator := by exact_mod_cast hdenNat
  by_cases hdNonpos : difference ≤ 0
  · have hdNonposReal : (difference : Real) ≤ 0 := by
      exact_mod_cast hdNonpos
    rw [hdifferenceCast] at hdNonposReal
    have hleft : (upperQ64 : Real) / scaleN - left ≤ 0 := by
      apply sub_nonpos.mpr
      exact (div_le_iff₀ hscale).2 (by nlinarith)
    exact hleft.trans (mul_nonneg (by positivity) (Real.sqrt_nonneg _))
  · have hsquare := hsafe.resolve_left hdNonpos
    have hdPos : 0 < difference := lt_of_not_ge hdNonpos
    have habsInt : (difference.natAbs : Int) = difference :=
      Int.natAbs_of_nonneg hdPos.le
    have habsReal : (difference.natAbs : Real) = (difference : Real) := by
      calc
        (difference.natAbs : Real) = ((difference.natAbs : Int) : Real) := by
          norm_num
        _ = (difference : Real) :=
          congrArg (fun value : Int ↦ (value : Real)) habsInt
    have hsquareReal :
        (difference.natAbs : Real) ^ 2 * (denominator : Real) ^ 2 ≤
          (numerator : Real) ^ 2 * (left : Real) * (scaleN : Real) ^ 2 := by
      have hcast :
          ((difference.natAbs ^ 2 * denominator ^ 2 : Nat) : Real) ≤
            ((numerator ^ 2 * left * scaleN ^ 2 : Nat) : Real) :=
        (Nat.cast_le (α := Real)).2 hsquare
      norm_num only [Nat.cast_mul, Nat.cast_pow] at hcast
      exact hcast
    rw [habsReal] at hsquareReal
    have hdiff : 0 ≤ (difference : Real) := by exact_mod_cast hdPos.le
    let normalized : Real :=
      (difference : Real) / scaleN * denominator / numerator
    have hnormalized : 0 ≤ normalized := by
      dsimp [normalized]
      positivity
    have hnormalizedSq : normalized ^ 2 ≤ (left : Real) := by
      have hdenominator :
          0 < (scaleN : Real) ^ 2 * (numerator : Real) ^ 2 :=
        mul_pos (sq_pos_of_pos hscale) (sq_pos_of_pos hnum)
      have hdiv :
          (difference : Real) ^ 2 * (denominator : Real) ^ 2 /
                ((scaleN : Real) ^ 2 * (numerator : Real) ^ 2) ≤
              (left : Real) := by
        apply (div_le_iff₀ hdenominator).2
        calc
          (difference : Real) ^ 2 * (denominator : Real) ^ 2 ≤
              (numerator : Real) ^ 2 * (left : Real) *
                (scaleN : Real) ^ 2 := hsquareReal
          _ = (left : Real) *
              ((scaleN : Real) ^ 2 * (numerator : Real) ^ 2) := by ring
      calc
        normalized ^ 2 =
            (difference : Real) ^ 2 * (denominator : Real) ^ 2 /
              ((scaleN : Real) ^ 2 * (numerator : Real) ^ 2) := by
                dsimp [normalized]
                field_simp
        _ ≤ (left : Real) := hdiv
    have hnormalizedLe : normalized ≤ Real.sqrt left :=
      (Real.le_sqrt hnormalized (by positivity)).2 hnormalizedSq
    have heq :
        (upperQ64 : Real) / scaleN - left =
          (difference : Real) / scaleN := by
      rw [hdifferenceCast]
      field_simp
    rw [heq]
    calc
      (difference : Real) / scaleN =
          ((numerator : Real) / denominator) * normalized := by
            dsimp [normalized]
            field_simp
      _ ≤ ((numerator : Real) / denominator) * Real.sqrt left :=
        mul_le_mul_of_nonneg_left hnormalizedLe (by positivity)

/-- Literal Q64 specialization used by the CH25 source campaign. -/
theorem upperEndpointSafe_real
    {left upperQ64 : Nat}
    (hsafe : UpperEndpointSafe left upperQ64) :
    (upperQ64 : Real) / scale - left ≤
      ((upperNumerator : Real) / upperDenominator) * Real.sqrt left := by
  apply upperEndpointSafe_real_generic
    (scaleN := scale) (numerator := upperNumerator)
    (denominator := upperDenominator)
  · norm_num [scale]
  · norm_num [upperNumerator]
  · norm_num [upperDenominator]
  · simpa [UpperEndpointSafe, upperDifference] using hsafe

end SparkInterval.TernaryGoldbach.PsiSourceSemantics
