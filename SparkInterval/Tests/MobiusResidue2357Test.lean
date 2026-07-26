/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusResidue2357

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusResidue2357Test

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusDenseSchedule
open SparkInterval.TernaryGoldbach.MobiusResidue235
open SparkInterval.TernaryGoldbach.MobiusResidue2357

example :
    blockLocalResidue49 10_000_000_000_000_000 17 255 =
      (10_000_000_000_000_000 + 17 * 256 + 255) % 49 := by
  exact blockLocalResidue49_eq_sourceNumber_mod _ _ _

example :
    blockLocalResidue49 1 0 48 = 0 ∧
      blockLocalResidue49 1 0 6 % 7 = 0 := by
  norm_num [blockLocalResidue49, threadsPerBlock, sevenSquareModulus]

example : seedPrimes2357 = [2, 3, 5, 7] := by
  decide

example : sevenSquareModulus = 7 ^ 2 := by
  norm_num [sevenSquareModulus]

example : residue2357SuffixMinimumPrime = 11 := by
  rfl

example : residue2357MinimumBlockSlotsPerPrime = 94 := by
  exact residue2357MinimumBlockSlotsPerPrime_eq

example {count firstOffset prime : Nat}
    (hcount : count ≤
      SparkInterval.TernaryGoldbach.MobiusDenseSchedule.maximumSegmentRows)
    (hprime : 11 ≤ prime) :
    multipleEventCount count firstOffset prime ≤
      94 * eventsPerBlock := by
  simpa [residue2357SuffixMinimumPrime,
    residue2357MinimumBlockSlotsPerPrime] using
    residue2357MultipleEventCount_le_minimumCapacity
      hcount hprime

example :
    93 * eventsPerBlock <
      multipleEventCount
        SparkInterval.TernaryGoldbach.MobiusDenseSchedule.maximumSegmentRows
        0 11 := by
  simpa [residue2357SuffixMinimumPrime,
    residue2357MinimumBlockSlotsPerPrime] using
    residue2357PreviousSlotCount_insufficient

example : residueSeed2357 210 =
    { product := 210, distinctCount := 4, squareful := false } := by
  decide

example : residueSeed2357 490 =
    { product := 70, distinctCount := 3, squareful := true } := by
  decide

example : residueSeed2357 901 = initialSupport := by
  decide

example (n : Nat) :
    foldSupport n ([2, 3, 5, 7] ++ [11, 13]) =
      [11, 13].foldl (applyPrime n) (residueSeed2357 n) := by
  simpa [seedPrimes2357, seedPrimes] using
    fold_prefix_suffix_eq_residueSeed2357 n [11, 13]

example (n : Nat) :
    unpackProduct (residueSeed2357Word n) ≤ 210 := by
  rw [unpackProduct_residueSeed2357Word]
  exact residueSeed2357_product_le_twoHundredTen n

example (n : Nat) :
    unpackCount (residueSeed2357Word n) ≤ 4 := by
  rw [unpackCount_residueSeed2357Word]
  exact residueSeed2357_count_le_four n

example (n : Nat) :
    unpackSquareful (residueSeed2357Word n) =
      ((residueSeed n).squareful || decide (49 ∣ n)) := by
  rw [unpackSquareful_residueSeed2357Word,
    residueSeed2357_squareful_eq]

#print axioms applySeven_mod49_eq
#print axioms blockLocalResidue49_eq_sourceNumber_mod
#print axioms blockLocalResidue49_mod_seven_eq_zero_iff
#print axioms blockLocalResidue49_eq_zero_iff
#print axioms residueSeed2357_eq_fold
#print axioms fold_prefix_suffix_eq_residueSeed2357
#print axioms residue2357MultipleEventCount_le_minimumCapacity
#print axioms residue2357PreviousSlotCount_insufficient
#print axioms residueSeed2357_product_lt_productRadix
#print axioms residueSeed2357_count_lt_countRadix
#print axioms residueSeed2357Word_lt_two_pow_sixty
#print axioms residueSeed2357Word_lt_wordLimit
#print axioms unpackProduct_residueSeed2357Word
#print axioms unpackCount_residueSeed2357Word
#print axioms unpackSquareful_residueSeed2357Word

end SparkInterval.Tests.MobiusResidue2357Test
