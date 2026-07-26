/-
Copyright (c) 2026 Gershon Bialer. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: Gershon Bialer

This file extracts the data-independent logarithm-increment proof from the
project-owned `Rs62Certificates/RS62LadderEngine.lean`.
-/
import TGComputeContracts.Sqrt218.Kernel

/-!
# Integer logarithm-ladder increments for the Sqrt218 contract

The production producer advances its scale-`2^48` logarithm bounds with one
floor/ceiling integer recurrence per natural number.  This module proves the
recurrence sound for arbitrary inputs.  It contains no seed table, prime
roster, production row, receipt, or closed long reduction.
-/

set_option autoImplicit false

noncomputable section

namespace TGComputeContracts.Sqrt218

/-- Denominator in the rational enclosure for `log (1 + 1 / n)`. -/
def logIncrementDenominator (n : Nat) : Nat :=
  2 * n * n * (n - 1)

/-- Directed-downward scale-`2^48` increment. -/
def logIncrementLower (n : Nat) : Nat :=
  scale * (2 * n * n - 3 * n - 1) / logIncrementDenominator n

/-- Directed-upward scale-`2^48` increment. -/
def logIncrementUpper (n : Nat) : Nat :=
  (scale * (2 * n * n - 3 * n + 3) +
      (logIncrementDenominator n - 1)) /
    logIncrementDenominator n

private theorem natDiv_le_real (a b : Nat) :
    ((a / b : Nat) : Real) ≤ (a : Real) / (b : Real) := by
  rcases Nat.eq_zero_or_pos b with hb | hb
  · subst hb
    simp
  · exact_mod_cast Nat.cast_div_le

private theorem real_le_ceilDiv (a b : Nat) (hb : 0 < b) :
    (a : Real) / (b : Real) ≤
      (((a + (b - 1)) / b : Nat) : Real) := by
  have hkey : a ≤ b * ((a + (b - 1)) / b) := by
    have hmod := Nat.div_add_mod (a + (b - 1)) b
    have hlt : (a + (b - 1)) % b < b := Nat.mod_lt _ hb
    omega
  have hb' : (0 : Real) < (b : Real) := by
    exact_mod_cast hb
  rw [div_le_iff₀ hb']
  calc
    (a : Real) ≤ ((b * ((a + (b - 1)) / b) : Nat) : Real) := by
      exact_mod_cast hkey
    _ = (((a + (b - 1)) / b : Nat) : Real) * (b : Real) := by
      push_cast
      ring

/-- Second-order Maclaurin enclosure used by both integer increments. -/
theorem log_one_add_inv_enclosure {n : Nat} (hn : 2 ≤ n) :
    |Real.log (1 + 1 / (n : Real)) -
        (1 / (n : Real) - 1 / (2 * (n : Real) ^ 2))| ≤
      1 / ((n : Real) ^ 2 * ((n : Real) - 1)) := by
  have hn2 : (2 : Real) ≤ (n : Real) := by
    exact_mod_cast hn
  have hn0 : (0 : Real) < (n : Real) := by linarith
  have hne : (n : Real) ≠ 0 := hn0.ne'
  have hne1 : (n : Real) - 1 ≠ 0 := by
    intro h
    nlinarith
  have habs : |(-(1 / (n : Real)))| < 1 := by
    rw [abs_neg, abs_of_pos (by positivity)]
    rw [div_lt_one hn0]
    linarith
  have h := Real.abs_log_sub_add_sum_range_le habs 2
  have hsum :
      (∑ i ∈ Finset.range 2,
          (-(1 / (n : Real))) ^ (i + 1) / ((i : Nat) + 1)) =
        -(1 / (n : Real)) + (1 / (n : Real)) ^ 2 / 2 := by
    rw [Finset.sum_range_succ, Finset.sum_range_succ,
      Finset.sum_range_zero]
    push_cast
    ring
  rw [hsum] at h
  rw [show (1 : Real) - -(1 / (n : Real)) =
      1 + 1 / (n : Real) by ring] at h
  rw [abs_neg, abs_of_pos
    (show (0 : Real) < 1 / (n : Real) by positivity)] at h
  have hpos1 : (0 : Real) < 1 - 1 / (n : Real) := by
    rw [sub_pos, div_lt_one hn0]
    linarith
  have hpos2 :
      (0 : Real) < (n : Real) ^ 2 * ((n : Real) - 1) := by
    nlinarith
  have htail :
      (1 / (n : Real)) ^ (2 + 1) / (1 - 1 / (n : Real)) =
        1 / ((n : Real) ^ 2 * ((n : Real) - 1)) := by
    have hxp : (1 / (n : Real)) ^ (2 + 1) = 1 / (n : Real) ^ 3 := by
      rw [one_div, one_div, inv_pow]
    rw [hxp, div_eq_div_iff hpos1.ne' hpos2.ne']
    field_simp
  rw [htail] at h
  have hshape :
      Real.log (1 + 1 / (n : Real)) -
          (1 / (n : Real) - 1 / (2 * (n : Real) ^ 2)) =
        (-(1 / (n : Real)) + (1 / (n : Real)) ^ 2 / 2) +
          Real.log (1 + 1 / (n : Real)) := by
    field_simp
    ring
  rw [hshape]
  exact h

theorem log_succ_sub_log (n : Nat) (hn : 0 < n) :
    Real.log ((n : Real) + 1) - Real.log n =
      Real.log (1 + 1 / (n : Real)) := by
  have hn0 : (0 : Real) < (n : Real) := by
    exact_mod_cast hn
  rw [← Real.log_div (by linarith) (by linarith)]
  congr 1
  field_simp

/-- The floor increment preserves a directed lower logarithm bound. -/
theorem logIncrementLower_sound {n lower : Nat} (hn : 2 ≤ n)
    (h : (lower : Real) ≤ scale * Real.log n) :
    ((logIncrementLower n + lower : Nat) : Real) ≤
      scale * Real.log (n + 1) := by
  have hn2 : (2 : Real) ≤ (n : Real) := by
    exact_mod_cast hn
  have hne : (n : Real) ≠ 0 := by linarith
  have hne1 : (n : Real) - 1 ≠ 0 := by
    intro hzero
    nlinarith
  have henc := log_one_add_inv_enclosure hn
  have hlog := log_succ_sub_log n (by omega)
  have hnum :
      ((2 * n * n - 3 * n - 1 : Nat) : Real) =
        2 * (n : Real) ^ 2 - 3 * (n : Real) - 1 := by
    have h1 : 3 * n + 1 ≤ 2 * n * n := by nlinarith
    have h2 : 3 * n ≤ 2 * n * n := by nlinarith
    push_cast [Nat.cast_sub h2,
      Nat.cast_sub (by omega : 1 ≤ 2 * n * n - 3 * n)]
    ring
  have hden :
      ((logIncrementDenominator n : Nat) : Real) =
        2 * (n : Real) ^ 2 * ((n : Real) - 1) := by
    simp only [logIncrementDenominator]
    push_cast [Nat.cast_sub (by omega : 1 ≤ n)]
    ring
  have hlower :
      (2 * (n : Real) ^ 2 - 3 * (n : Real) - 1) /
          (2 * (n : Real) ^ 2 * ((n : Real) - 1)) ≤
        Real.log (1 + 1 / (n : Real)) := by
    have hleft := (abs_le.mp henc).1
    have hexp :
        (2 * (n : Real) ^ 2 - 3 * (n : Real) - 1) /
            (2 * (n : Real) ^ 2 * ((n : Real) - 1)) =
          (1 / (n : Real) - 1 / (2 * (n : Real) ^ 2)) -
            1 / ((n : Real) ^ 2 * ((n : Real) - 1)) := by
      field_simp [hne, hne1]
      ring
    rw [hexp]
    linarith
  have hstep :
      ((logIncrementLower n : Nat) : Real) ≤
        scale * Real.log ((n : Real) + 1) - scale * Real.log n := by
    unfold logIncrementLower
    calc
      ((scale * (2 * n * n - 3 * n - 1) /
          logIncrementDenominator n : Nat) : Real) ≤
          ((scale * (2 * n * n - 3 * n - 1) : Nat) : Real) /
            ((logIncrementDenominator n : Nat) : Real) :=
        natDiv_le_real _ _
      _ = (scale : Real) *
          ((2 * (n : Real) ^ 2 - 3 * (n : Real) - 1) /
            (2 * (n : Real) ^ 2 * ((n : Real) - 1))) := by
        rw [Nat.cast_mul, hnum, hden]
        ring
      _ ≤ (scale : Real) * Real.log (1 + 1 / (n : Real)) :=
        mul_le_mul_of_nonneg_left hlower
          (by exact_mod_cast (Nat.zero_le scale))
      _ = scale * Real.log ((n : Real) + 1) -
          scale * Real.log n := by
        rw [← hlog]
        ring
  push_cast
  linarith

/-- The ceiling increment preserves a directed upper logarithm bound. -/
theorem logIncrementUpper_sound {n upper : Nat} (hn : 2 ≤ n)
    (h : (scale : Real) * Real.log n ≤ upper) :
    (scale : Real) * Real.log (n + 1) ≤
      ((logIncrementUpper n + upper : Nat) : Real) := by
  have hn2 : (2 : Real) ≤ (n : Real) := by
    exact_mod_cast hn
  have hne : (n : Real) ≠ 0 := by linarith
  have hne1 : (n : Real) - 1 ≠ 0 := by
    intro hzero
    nlinarith
  have henc := log_one_add_inv_enclosure hn
  have hlog := log_succ_sub_log n (by omega)
  have hnum :
      ((2 * n * n - 3 * n + 3 : Nat) : Real) =
        2 * (n : Real) ^ 2 - 3 * (n : Real) + 3 := by
    have h2 : 3 * n ≤ 2 * n * n := by nlinarith
    push_cast [Nat.cast_sub h2]
    ring
  have hden :
      ((logIncrementDenominator n : Nat) : Real) =
        2 * (n : Real) ^ 2 * ((n : Real) - 1) := by
    simp only [logIncrementDenominator]
    push_cast [Nat.cast_sub (by omega : 1 ≤ n)]
    ring
  have hdposn : 0 < logIncrementDenominator n := by
    simp only [logIncrementDenominator]
    have h1 : 1 ≤ n - 1 := by omega
    positivity
  have hupper :
      Real.log (1 + 1 / (n : Real)) ≤
        (2 * (n : Real) ^ 2 - 3 * (n : Real) + 3) /
          (2 * (n : Real) ^ 2 * ((n : Real) - 1)) := by
    have hright := (abs_le.mp henc).2
    have hexp :
        (2 * (n : Real) ^ 2 - 3 * (n : Real) + 3) /
            (2 * (n : Real) ^ 2 * ((n : Real) - 1)) =
          (1 / (n : Real) - 1 / (2 * (n : Real) ^ 2)) +
            1 / ((n : Real) ^ 2 * ((n : Real) - 1)) := by
      field_simp [hne, hne1]
      ring
    rw [hexp]
    linarith
  have hstep :
      scale * Real.log ((n : Real) + 1) - scale * Real.log n ≤
        ((logIncrementUpper n : Nat) : Real) := by
    unfold logIncrementUpper
    have hceil :=
      real_le_ceilDiv
        (scale * (2 * n * n - 3 * n + 3))
        (logIncrementDenominator n) hdposn
    calc
      (scale : Real) * Real.log ((n : Real) + 1) -
          scale * Real.log n =
          (scale : Real) * Real.log (1 + 1 / (n : Real)) := by
        rw [← hlog]
        ring
      _ ≤ (scale : Real) *
          ((2 * (n : Real) ^ 2 - 3 * (n : Real) + 3) /
            (2 * (n : Real) ^ 2 * ((n : Real) - 1))) :=
        mul_le_mul_of_nonneg_left hupper
          (by exact_mod_cast (Nat.zero_le scale))
      _ = ((scale * (2 * n * n - 3 * n + 3) : Nat) : Real) /
          ((logIncrementDenominator n : Nat) : Real) := by
        rw [Nat.cast_mul, hnum, hden]
        ring
      _ ≤ (((scale * (2 * n * n - 3 * n + 3) +
          (logIncrementDenominator n - 1)) /
            logIncrementDenominator n : Nat) : Real) :=
        hceil
  push_cast
  linarith

/-- A pair of scale-`2^48` integer endpoints. -/
structure LogBounds where
  lower : Nat
  upper : Nat
  deriving Repr, DecidableEq

/-- Real meaning of a pair of fixed-point logarithm endpoints. -/
def LogBounds.Valid (n : Nat) (bounds : LogBounds) : Prop :=
  (bounds.lower : Real) ≤ scale * Real.log n ∧
    scale * Real.log n ≤ (bounds.upper : Real)

/-- One recurrence transition, with no seed special case. -/
def LogBounds.next (n : Nat) (bounds : LogBounds) : LogBounds := {
  lower := bounds.lower + logIncrementLower n
  upper := bounds.upper + logIncrementUpper n
}

theorem LogBounds.Valid.next {n : Nat} {bounds : LogBounds}
    (hn : 2 ≤ n) (h : bounds.Valid n) :
    (bounds.next n).Valid (n + 1) := by
  constructor
  · simpa [LogBounds.next, add_comm] using
      logIncrementLower_sound hn h.1
  · simpa [LogBounds.next, add_comm] using
      logIncrementUpper_sound hn h.2

end TGComputeContracts.Sqrt218

end
