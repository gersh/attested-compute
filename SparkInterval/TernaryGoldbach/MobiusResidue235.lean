/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusDenseSchedule

/-!
# Exact residue-table seed for the primes 2, 3, and 5

The production Möbius kernel initializes each row from a 900-entry table and
then starts the concurrent prime-event passes at 7.  Since
`900 = 2² * 3² * 5²`, the residue of `n` modulo 900 determines both `p ∣ n`
and `p² ∣ n` for each seeded prime `p ∈ {2,3,5}`.

This module proves that the table seed followed by an arbitrary suffix of
prime updates is exactly the same mathematical `Support` fold as processing
`2,3,5` and that suffix normally.  It does not claim that CUDA loaded this
table or that a native base-prime pointer has the required prefix; those are
separate machine-refinement and runtime-validation boundaries.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusResidue235

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusDenseSchedule

/-- Small-prime modulus used by the native constant table. -/
def residueModulus : ℕ := 900

/-- Exact prime prefix represented by the residue table. -/
def seedPrimes : List ℕ := [2, 3, 5]

/-- Empty mathematical state before any prime-divisor event. -/
def initialSupport : Support where
  product := 1
  distinctCount := 0
  squareful := false

/-- Apply one distinct-prime event exactly when the prime divides the row. -/
def applyPrime (n : ℕ) (support : Support) (prime : ℕ) : Support :=
  if prime ∣ n then
    update support prime (decide (prime * prime ∣ n))
  else
    support

/-- Mathematical support fold for an explicitly ordered prime roster. -/
def foldSupport (n : ℕ) (primes : List ℕ) : Support :=
  primes.foldl (applyPrime n) initialSupport

/-- State decoded from the 900-entry seed table for row `n`. -/
def residueSeed (n : ℕ) : Support :=
  foldSupport (n % residueModulus) seedPrimes

/-- Literal production initializer's block-local table-index formula. The
single conditional subtraction is sufficient because a physical thread is
below 256 while the block-start residue is below 900. -/
def blockLocalResidue900
    (lower block thread : Nat) : Nat :=
  let candidate :=
    (lower + block * threadsPerBlock) % residueModulus + thread
  if residueModulus ≤ candidate then candidate - residueModulus
  else candidate

/-- Every physical thread in a 256-thread block indexes the same table row
as reducing its complete source number modulo 900. -/
theorem blockLocalResidue900_eq_sourceNumber_mod
    {lower block thread : Nat}
    (threadBound : thread < threadsPerBlock) :
    blockLocalResidue900 lower block thread =
      (lower + block * threadsPerBlock + thread) % residueModulus := by
  norm_num [blockLocalResidue900, threadsPerBlock, residueModulus] at threadBound ⊢
  split <;> omega

/-- Every residue-table product fits comfortably in the 54-bit field. -/
theorem residueSeed_product_lt_productRadix (n : Nat) :
    (residueSeed n).product < productRadix := by
  by_cases dividesTwo : 2 ∣ n % residueModulus <;>
    by_cases dividesThree : 3 ∣ n % residueModulus <;>
    by_cases dividesFive : 5 ∣ n % residueModulus <;>
    simp [residueSeed, foldSupport, seedPrimes, applyPrime,
      initialSupport, update, dividesTwo, dividesThree, dividesFive,
      productRadix]

/-- Every residue-table distinct-prime count fits in the five-bit field. -/
theorem residueSeed_count_lt_countRadix (n : Nat) :
    (residueSeed n).distinctCount < countRadix := by
  by_cases dividesTwo : 2 ∣ n % residueModulus <;>
    by_cases dividesThree : 3 ∣ n % residueModulus <;>
    by_cases dividesFive : 5 ∣ n % residueModulus <;>
    simp [residueSeed, foldSupport, seedPrimes, applyPrime,
      initialSupport, update, dividesTwo, dividesThree, dividesFive,
      countRadix]

theorem seedPrime_cases {prime : ℕ} (hprime : prime ∈ seedPrimes) :
    prime = 2 ∨ prime = 3 ∨ prime = 5 := by
  simpa [seedPrimes] using hprime

/-- Divisibility by a seeded prime is determined by the residue modulo 900. -/
theorem seedPrime_dvd_residue_iff
    {n prime : ℕ} (hprime : prime ∈ seedPrimes) :
    prime ∣ n % residueModulus ↔ prime ∣ n := by
  rcases seedPrime_cases hprime with rfl | rfl | rfl <;>
    exact Nat.dvd_mod_iff (by norm_num [residueModulus])

/-- Square-divisibility by a seeded prime is also determined by the residue. -/
theorem seedPrime_sq_dvd_residue_iff
    {n prime : ℕ} (hprime : prime ∈ seedPrimes) :
    prime * prime ∣ n % residueModulus ↔ prime * prime ∣ n := by
  rcases seedPrime_cases hprime with rfl | rfl | rfl <;>
    exact Nat.dvd_mod_iff (by norm_num [residueModulus])

/-- One seeded-prime update computed from the table residue equals the update
computed from the original row. -/
theorem applyPrime_residue_eq
    (n : ℕ) (support : Support) {prime : ℕ}
    (hprime : prime ∈ seedPrimes) :
    applyPrime (n % residueModulus) support prime =
      applyPrime n support prime := by
  have hdiv := seedPrime_dvd_residue_iff
    (n := n) hprime
  have hsquare := seedPrime_sq_dvd_residue_iff
    (n := n) hprime
  unfold applyPrime
  by_cases hp : prime ∣ n
  · have hpr : prime ∣ n % residueModulus := hdiv.mpr hp
    by_cases hsq : prime * prime ∣ n
    · have hsqr : prime * prime ∣ n % residueModulus :=
        hsquare.mpr hsq
      simp [hp, hpr, hsq, hsqr]
    · have hsqr : ¬ prime * prime ∣ n % residueModulus :=
        fun contradiction => hsq (hsquare.mp contradiction)
      simp [hp, hpr, hsq, hsqr]
  · have hpr : ¬ prime ∣ n % residueModulus := by
      exact fun contradiction => hp (hdiv.mp contradiction)
    rw [if_neg hp, if_neg hpr]

/-- The 900-entry seed is exactly the ordinary fold over `2,3,5`. -/
theorem residueSeed_eq (n : ℕ) :
    residueSeed n = foldSupport n seedPrimes := by
  simp only [residueSeed, foldSupport, seedPrimes, List.foldl_cons,
    List.foldl_nil]
  rw [applyPrime_residue_eq n initialSupport (by simp [seedPrimes])]
  rw [applyPrime_residue_eq n
    (applyPrime n initialSupport 2) (by simp [seedPrimes])]
  rw [applyPrime_residue_eq n
    (applyPrime n (applyPrime n initialSupport 2) 3)
    (by simp [seedPrimes])]

/-- Replacing the first three event passes by the residue seed preserves the
complete support state for every subsequent roster, without an ordering or
primality assumption on that suffix. -/
theorem fold_prefix_suffix_eq_residueSeed
    (n : ℕ) (suffix : List ℕ) :
    foldSupport n (seedPrimes ++ suffix) =
      suffix.foldl (applyPrime n) (residueSeed n) := by
  rw [foldSupport, List.foldl_append, ← foldSupport, ← residueSeed_eq]

#print axioms residueSeed_product_lt_productRadix
#print axioms residueSeed_count_lt_countRadix
#print axioms blockLocalResidue900_eq_sourceNumber_mod

end SparkInterval.TernaryGoldbach.MobiusResidue235
