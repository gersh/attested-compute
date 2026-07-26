/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusDenseSchedule
import SparkInterval.TernaryGoldbach.MobiusResidue235

/-!
# Exact extension of the residue-235 seed by the prime 7

The current production initializer loads the exact contribution of `2, 3, 5`
from `n % 900`. A separate qualification candidate removes the `p = 7`
distinct-factor and square-strike event streams without replacing that small
table: after loading it, the initializer uses `n % 49` to apply the exact
contribution of `7`.

This module proves the pure arithmetic refinement and exact suffix-capacity
bound only. It does not claim that CUDA computes the block-local modulo-49
residue or promote the candidate into the production runner.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusResidue2357

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusDenseSchedule
open SparkInterval.TernaryGoldbach.MobiusResidue235

/-- The separate residue modulus needed for both `7 ∣ n` and `7² ∣ n`. -/
def sevenSquareModulus : Nat := 49

/-- Prime prefix represented by the old table followed by the modulo-49
extension. -/
def seedPrimes2357 : List Nat := seedPrimes ++ [7]

/-- Smallest possible suffix prime after the exact `[2,3,5,7]` prefix.
The native structural preflight enforces this lower bound even though
primality and roster completeness remain authenticated-host obligations. -/
def residue2357SuffixMinimumPrime : Nat := 11

/-- Exact minimum number of native event blocks needed per suffix prime at
the unchanged public segment cap. -/
def residue2357MinimumBlockSlotsPerPrime : Nat := 94

/-- Exact proposed initializer: load the current residue-235 support, then
apply the `p = 7` update using only the row's residue modulo 49. -/
def residueSeed2357 (n : Nat) : Support :=
  applyPrime (n % sevenSquareModulus) (residueSeed n) 7

/-- Packed word emitted by the pure proposed initializer. -/
def residueSeed2357Word (n : Nat) : Nat :=
  pack
    (residueSeed2357 n).product
    (residueSeed2357 n).distinctCount
    (residueSeed2357 n).squareful

/-- Literal block-local modulo-49 calculation in the qualification CUDA
initializer. Thread 0 first computes the block's source residue and every
thread advances it by its local index. -/
def blockLocalResidue49
    (lower block thread : Nat) : Nat :=
  ((lower + block * threadsPerBlock) % sevenSquareModulus + thread) %
    sevenSquareModulus

/-- The block-local reconstruction is the exact residue of the physical
source row `lower + block*256 + thread`. -/
theorem blockLocalResidue49_eq_sourceNumber_mod
    (lower block thread : Nat) :
    blockLocalResidue49 lower block thread =
      (lower + block * threadsPerBlock + thread) %
        sevenSquareModulus := by
  norm_num [blockLocalResidue49, threadsPerBlock, sevenSquareModulus]

/-- The initializer's literal `residue49 % 7 == 0` branch fires exactly on
rows divisible by seven. -/
theorem blockLocalResidue49_mod_seven_eq_zero_iff
    (lower block thread : Nat) :
    blockLocalResidue49 lower block thread % 7 = 0 ↔
      7 ∣ lower + block * threadsPerBlock + thread := by
  rw [← Nat.dvd_iff_mod_eq_zero,
    blockLocalResidue49_eq_sourceNumber_mod]
  exact Nat.dvd_mod_iff (by norm_num [sevenSquareModulus])

/-- The nested literal `residue49 == 0` square branch fires exactly on rows
divisible by `7²`. -/
theorem blockLocalResidue49_eq_zero_iff
    (lower block thread : Nat) :
    blockLocalResidue49 lower block thread = 0 ↔
      7 * 7 ∣ lower + block * threadsPerBlock + thread := by
  rw [blockLocalResidue49_eq_sourceNumber_mod]
  norm_num [sevenSquareModulus]
  exact Nat.dvd_iff_mod_eq_zero.symm

theorem seven_dvd_mod49_iff (n : Nat) :
    7 ∣ n % sevenSquareModulus ↔ 7 ∣ n := by
  exact Nat.dvd_mod_iff (by norm_num [sevenSquareModulus])

theorem sevenSquare_dvd_mod49_iff (n : Nat) :
    7 * 7 ∣ n % sevenSquareModulus ↔ 7 * 7 ∣ n := by
  exact Nat.dvd_mod_iff (by norm_num [sevenSquareModulus])

/-- Computing the seventh-prime update from `n % 49` is exactly the same
update as computing it from `n`. -/
theorem applySeven_mod49_eq (n : Nat) (support : Support) :
    applyPrime (n % sevenSquareModulus) support 7 =
      applyPrime n support 7 := by
  unfold applyPrime
  by_cases hseven : 7 ∣ n
  · have hsevenResidue : 7 ∣ n % sevenSquareModulus :=
      (seven_dvd_mod49_iff n).mpr hseven
    by_cases hsquare : 7 * 7 ∣ n
    · have hsquareResidue :
          7 * 7 ∣ n % sevenSquareModulus :=
        (sevenSquare_dvd_mod49_iff n).mpr hsquare
      simp [hseven, hsevenResidue, hsquare, hsquareResidue]
    · have hsquareResidue :
          ¬ 7 * 7 ∣ n % sevenSquareModulus :=
        fun contradiction =>
          hsquare ((sevenSquare_dvd_mod49_iff n).mp contradiction)
      simp [hseven, hsevenResidue, hsquare, hsquareResidue]
  · have hsevenResidue : ¬ 7 ∣ n % sevenSquareModulus :=
      fun contradiction =>
        hseven ((seven_dvd_mod49_iff n).mp contradiction)
    simp [hseven, hsevenResidue]

/-- The proposed two-residue initializer is exactly the ordinary support fold
over the prefix `[2, 3, 5, 7]`. -/
theorem residueSeed2357_eq_fold (n : Nat) :
    residueSeed2357 n = foldSupport n seedPrimes2357 := by
  rw [residueSeed2357, applySeven_mod49_eq]
  rw [seedPrimes2357, foldSupport, List.foldl_append]
  simp only [List.foldl_cons, List.foldl_nil]
  change
    applyPrime n (residueSeed n) 7 =
      applyPrime n (foldSupport n seedPrimes) 7
  rw [residueSeed_eq]

/-- Replacing the first four event streams by the proposed initializer
preserves the complete support state for every subsequent suffix. -/
theorem fold_prefix_suffix_eq_residueSeed2357
    (n : Nat) (suffix : List Nat) :
    foldSupport n (seedPrimes2357 ++ suffix) =
      suffix.foldl (applyPrime n) (residueSeed2357 n) := by
  rw [foldSupport, List.foldl_append, ← foldSupport,
    ← residueSeed2357_eq_fold]

theorem residue2357MinimumBlockSlotsPerPrime_eq :
    residue2357MinimumBlockSlotsPerPrime = 94 := by
  rfl

/-- At the unchanged public row cap, every suffix value admitted by the
strengthened native preflight fits the exact 94-slot event rectangle. -/
theorem residue2357MultipleEventCount_le_minimumCapacity
    {count firstOffset prime : Nat}
    (hcount : count ≤ MobiusDenseSchedule.maximumSegmentRows)
    (hprime : residue2357SuffixMinimumPrime ≤ prime) :
    multipleEventCount count firstOffset prime ≤
      residue2357MinimumBlockSlotsPerPrime * eventsPerBlock := by
  unfold multipleEventCount
  split
  · simp
  · let capacity :=
      residue2357MinimumBlockSlotsPerPrime * eventsPerBlock
    have hcapacityPos : 0 < capacity := by
      norm_num [capacity, residue2357MinimumBlockSlotsPerPrime,
        eventsPerBlock, threadsPerBlock, iterationsPerThread]
    have hmaximumBound :
        MobiusDenseSchedule.maximumSegmentRows ≤
          residue2357SuffixMinimumPrime * capacity := by
      norm_num [MobiusDenseSchedule.maximumSegmentRows,
        residue2357SuffixMinimumPrime,
        capacity, residue2357MinimumBlockSlotsPerPrime,
        blockSlotsPerPrime, eventsPerBlock, threadsPerBlock,
        iterationsPerThread]
    have hnumerator :
        count - 1 - firstOffset <
          residue2357SuffixMinimumPrime * capacity := by
      omega
    have hscaled :
        residue2357SuffixMinimumPrime * capacity ≤
          capacity * prime := by
      simpa [Nat.mul_comm] using
        Nat.mul_le_mul_left capacity hprime
    have hquotient :
        (count - 1 - firstOffset) / prime < capacity := by
      have hprimePos : 0 < prime :=
        lt_of_lt_of_le
          (by norm_num [residue2357SuffixMinimumPrime]) hprime
      apply (Nat.div_lt_iff_lt_mul hprimePos).2
      exact lt_of_lt_of_le hnumerator hscaled
    omega

/-- At the maximum count, the zero-offset `p=11` event stream does not fit
93 slots, so 94 is the exact minimum rather than merely a sufficient bound. -/
theorem residue2357PreviousSlotCount_insufficient :
    (residue2357MinimumBlockSlotsPerPrime - 1) * eventsPerBlock <
      multipleEventCount MobiusDenseSchedule.maximumSegmentRows 0
        residue2357SuffixMinimumPrime := by
  norm_num [multipleEventCount, MobiusDenseSchedule.maximumSegmentRows,
    residue2357SuffixMinimumPrime,
    residue2357MinimumBlockSlotsPerPrime, blockSlotsPerPrime,
    eventsPerBlock, threadsPerBlock, iterationsPerThread]

theorem residueSeed_product_le_thirty (n : Nat) :
    (residueSeed n).product ≤ 30 := by
  by_cases dividesTwo : 2 ∣ n % residueModulus <;>
    by_cases dividesThree : 3 ∣ n % residueModulus <;>
    by_cases dividesFive : 5 ∣ n % residueModulus <;>
    simp [residueSeed, foldSupport, seedPrimes, applyPrime,
      initialSupport, update, dividesTwo, dividesThree, dividesFive]

theorem residueSeed_count_le_three (n : Nat) :
    (residueSeed n).distinctCount ≤ 3 := by
  by_cases dividesTwo : 2 ∣ n % residueModulus <;>
    by_cases dividesThree : 3 ∣ n % residueModulus <;>
    by_cases dividesFive : 5 ∣ n % residueModulus <;>
    simp [residueSeed, foldSupport, seedPrimes, applyPrime,
      initialSupport, update, dividesTwo, dividesThree, dividesFive]

/-- Exact product field of the extended initializer. -/
theorem residueSeed2357_product_eq (n : Nat) :
    (residueSeed2357 n).product =
      if 7 ∣ n then (residueSeed n).product * 7
      else (residueSeed n).product := by
  rw [residueSeed2357, applySeven_mod49_eq]
  by_cases hseven : 7 ∣ n <;>
    simp [applyPrime, hseven, update]

/-- Exact distinct-factor-count field of the extended initializer. -/
theorem residueSeed2357_count_eq (n : Nat) :
    (residueSeed2357 n).distinctCount =
      if 7 ∣ n then (residueSeed n).distinctCount + 1
      else (residueSeed n).distinctCount := by
  rw [residueSeed2357, applySeven_mod49_eq]
  by_cases hseven : 7 ∣ n <;>
    simp [applyPrime, hseven, update]

/-- Exact squareful field.  Divisibility by 49 already implies divisibility
by 7, so this is an unconditional OR with the old seed flag. -/
theorem residueSeed2357_squareful_eq (n : Nat) :
    (residueSeed2357 n).squareful =
      ((residueSeed n).squareful || decide (7 * 7 ∣ n)) := by
  rw [residueSeed2357, applySeven_mod49_eq]
  by_cases hseven : 7 ∣ n
  · simp [applyPrime, hseven, update]
  · have hsquare : ¬ 7 * 7 ∣ n := by
      intro squareDivides
      exact hseven (dvd_trans (by norm_num) squareDivides)
    simp [applyPrime, hseven, hsquare]

/-- The extended seed product is at most `2·3·5·7 = 210`. -/
theorem residueSeed2357_product_le_twoHundredTen (n : Nat) :
    (residueSeed2357 n).product ≤ 210 := by
  rw [residueSeed2357_product_eq]
  have oldBound := residueSeed_product_le_thirty n
  split <;> omega

/-- The extended seed represents at most four distinct factors. -/
theorem residueSeed2357_count_le_four (n : Nat) :
    (residueSeed2357 n).distinctCount ≤ 4 := by
  rw [residueSeed2357_count_eq]
  have oldBound := residueSeed_count_le_three n
  split <;> omega

theorem residueSeed2357_product_lt_productRadix (n : Nat) :
    (residueSeed2357 n).product < productRadix := by
  have bound := residueSeed2357_product_le_twoHundredTen n
  norm_num [productRadix] at *
  omega

theorem residueSeed2357_count_lt_countRadix (n : Nat) :
    (residueSeed2357 n).distinctCount < countRadix := by
  have bound := residueSeed2357_count_le_four n
  norm_num [countRadix] at *
  omega

/-- The packed initializer cannot reach the reserved or poison bits: every
valid extended seed occupies fewer than 60 bits. -/
theorem residueSeed2357Word_lt_two_pow_sixty (n : Nat) :
    residueSeed2357Word n < 2 ^ 60 := by
  exact pack_lt_two_pow_sixty
    (residueSeed2357_product_lt_productRadix n)
    (residueSeed2357_count_lt_countRadix n)

theorem residueSeed2357Word_lt_wordLimit (n : Nat) :
    residueSeed2357Word n < wordLimit := by
  exact pack_lt_wordLimit
    (residueSeed2357_product_lt_productRadix n)
    (residueSeed2357_count_lt_countRadix n)

@[simp] theorem unpackProduct_residueSeed2357Word (n : Nat) :
    unpackProduct (residueSeed2357Word n) =
      (residueSeed2357 n).product := by
  exact unpackProduct_pack
    (residueSeed2357_product_lt_productRadix n)

@[simp] theorem unpackCount_residueSeed2357Word (n : Nat) :
    unpackCount (residueSeed2357Word n) =
      (residueSeed2357 n).distinctCount := by
  exact unpackCount_pack
    (residueSeed2357_product_lt_productRadix n)
    (residueSeed2357_count_lt_countRadix n)

@[simp] theorem unpackSquareful_residueSeed2357Word (n : Nat) :
    unpackSquareful (residueSeed2357Word n) =
      (residueSeed2357 n).squareful := by
  exact unpackSquareful_pack
    (residueSeed2357_product_lt_productRadix n)
    (residueSeed2357_count_lt_countRadix n)

#print axioms applySeven_mod49_eq
#print axioms blockLocalResidue49_eq_sourceNumber_mod
#print axioms blockLocalResidue49_mod_seven_eq_zero_iff
#print axioms blockLocalResidue49_eq_zero_iff
#print axioms residueSeed2357_eq_fold
#print axioms fold_prefix_suffix_eq_residueSeed2357
#print axioms residue2357MultipleEventCount_le_minimumCapacity
#print axioms residue2357PreviousSlotCount_insufficient
#print axioms residueSeed2357_product_eq
#print axioms residueSeed2357_count_eq
#print axioms residueSeed2357_squareful_eq
#print axioms residueSeed2357Word_lt_wordLimit
#print axioms unpackProduct_residueSeed2357Word
#print axioms unpackCount_residueSeed2357Word
#print axioms unpackSquareful_residueSeed2357Word

end SparkInterval.TernaryGoldbach.MobiusResidue2357
