/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Data.Nat.Prime.Basic

/-!
# Explicit composite runs for the Sqrt218 V2 prime roster

One nontrivial factor pair is supplied for each integer omitted between
consecutive prime rows and after the final row.  The definitions are generic
and contain no production certificate.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational.V2

structure FactorPair where
  left : Nat
  right : Nat
  deriving Repr, DecidableEq, Inhabited

def factorPairCheck (value : Nat) (pair : FactorPair) : Bool :=
  decide (
    1 < pair.left ∧
      1 < pair.right ∧
      value = pair.left * pair.right)

theorem not_prime_of_factorPairCheck
    {value : Nat} {pair : FactorPair}
    (hcheck : factorPairCheck value pair = true) :
    ¬value.Prime := by
  simp only [factorPairCheck, decide_eq_true_eq] at hcheck
  apply Nat.not_prime_of_dvd_of_lt (m := pair.left)
  · exact ⟨pair.right, hcheck.2.2⟩
  · exact hcheck.1
  · calc
      pair.left = pair.left * 1 := (Nat.mul_one pair.left).symm
      _ < pair.left * pair.right :=
        Nat.mul_lt_mul_of_pos_left hcheck.2.1
          (Nat.zero_lt_of_lt hcheck.1)
      _ = value := hcheck.2.2.symm

/-- Check consecutive values beginning at `start`. -/
def factorRunCheck : Nat → List FactorPair → Bool
  | _, [] => true
  | value, pair :: rest =>
      factorPairCheck value pair &&
        factorRunCheck (value + 1) rest

theorem factorRunCheck_sound
    {start : Nat} {pairs : List FactorPair}
    (hcheck : factorRunCheck start pairs = true) :
    ∀ value, start ≤ value → value < start + pairs.length →
      ¬value.Prime := by
  induction pairs generalizing start with
  | nil =>
      intro value hlower hupper
      simp only [List.length_nil, Nat.add_zero] at hupper
      omega
  | cons pair rest inductionHypothesis =>
      simp only [factorRunCheck, Bool.and_eq_true] at hcheck
      intro value hlower hupper
      by_cases hequal : value = start
      · subst value
        exact not_prime_of_factorPairCheck hcheck.1
      · apply inductionHypothesis hcheck.2 value
        · omega
        · simp only [List.length_cons] at hupper
          omega

/-- Check that `pairs` covers precisely the open interval
`(previous, current)`. -/
def factorGapCheck
    (previous current : Nat) (pairs : List FactorPair) : Bool :=
  decide (previous + pairs.length + 1 = current) &&
    factorRunCheck (previous + 1) pairs

theorem factorGapCheck_sound
    {previous current : Nat} {pairs : List FactorPair}
    (hcheck : factorGapCheck previous current pairs = true) :
    ∀ value, previous < value → value < current →
      ¬value.Prime := by
  simp only [factorGapCheck, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  intro value hlower hupper
  apply factorRunCheck_sound hcheck.2 value
  · omega
  · rw [← hcheck.1] at hupper
    omega

theorem previous_lt_current_of_factorGapCheck
    {previous current : Nat} {pairs : List FactorPair}
    (hcheck : factorGapCheck previous current pairs = true) :
    previous < current := by
  simp only [factorGapCheck, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  omega

end SparkInterval.TernaryGoldbach.Sqrt218Operational.V2
