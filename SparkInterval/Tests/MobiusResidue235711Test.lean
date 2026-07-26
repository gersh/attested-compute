/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusResidue235711

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusResidue235711Test

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusDenseSchedule
open SparkInterval.TernaryGoldbach.MobiusResidue235
open SparkInterval.TernaryGoldbach.MobiusResidue2357
open SparkInterval.TernaryGoldbach.MobiusResidue235711

example :
    blockLocalResidue121 10_000_000_000_000_000 17 255 =
      (10_000_000_000_000_000 + 17 * 256 + 255) % 121 := by
  exact blockLocalResidue121_eq_sourceNumber_mod _ _ _

example :
    blockLocalResidue121 1 0 120 = 0 ∧
      blockLocalResidue121 1 0 10 % 11 = 0 := by
  norm_num [blockLocalResidue121, threadsPerBlock,
    elevenSquareModulus]

example (lower block thread : Nat) :
    blockLocalResidue121 lower block thread % 11 = 0 ↔
      11 ∣ lower + block * threadsPerBlock + thread := by
  exact blockLocalResidue121_mod_eleven_eq_zero_iff _ _ _

example (lower block thread : Nat) :
    blockLocalResidue121 lower block thread = 0 ↔
      121 ∣ lower + block * threadsPerBlock + thread := by
  simpa using blockLocalResidue121_eq_zero_iff lower block thread

example : seedPrimes235711 = [2, 3, 5, 7, 11] := by
  decide

example : elevenSquareModulus = 11 ^ 2 := by
  norm_num [elevenSquareModulus]

example : residue235711SuffixMinimumPrime = 13 := by
  rfl

example : residue235711MinimumBlockSlotsPerPrime = 79 := by
  exact residue235711MinimumBlockSlotsPerPrime_eq

example {count firstOffset prime : Nat}
    (hcount : count ≤
      SparkInterval.TernaryGoldbach.MobiusDenseSchedule.maximumSegmentRows)
    (hprime : 13 ≤ prime) :
    multipleEventCount count firstOffset prime ≤
      79 * eventsPerBlock := by
  simpa [residue235711SuffixMinimumPrime,
    residue235711MinimumBlockSlotsPerPrime] using
    residue235711MultipleEventCount_le_minimumCapacity
      hcount hprime

example :
    78 * eventsPerBlock <
      multipleEventCount
        SparkInterval.TernaryGoldbach.MobiusDenseSchedule.maximumSegmentRows
        0 13 := by
  simpa [residue235711SuffixMinimumPrime,
    residue235711MinimumBlockSlotsPerPrime] using
    residue235711PreviousSlotCount_insufficient

example : residueSeed235711 2310 =
    { product := 2310, distinctCount := 5, squareful := false } := by
  decide

example : residueSeed235711 1210 =
    { product := 110, distinctCount := 3, squareful := true } := by
  decide

example : residueSeed235711 2309 = initialSupport := by
  decide

example (n : Nat) :
    foldSupport n ([2, 3, 5, 7, 11] ++ [13, 17]) =
      [13, 17].foldl (applyPrime n) (residueSeed235711 n) := by
  simpa [seedPrimes235711, seedPrimes2357, seedPrimes] using
    fold_prefix_suffix_eq_residueSeed235711 n [13, 17]

example (n : Nat) :
    unpackProduct (residueSeed235711Word n) ≤ 2310 := by
  rw [unpackProduct_residueSeed235711Word]
  exact residueSeed235711_product_le_twoThousandThreeHundredTen n

example (n : Nat) :
    unpackCount (residueSeed235711Word n) ≤ 5 := by
  rw [unpackCount_residueSeed235711Word]
  exact residueSeed235711_count_le_five n

example (n : Nat) :
    unpackSquareful (residueSeed235711Word n) =
      ((residueSeed2357 n).squareful || decide (121 ∣ n)) := by
  rw [unpackSquareful_residueSeed235711Word,
    residueSeed235711_squareful_eq]

#print axioms applyEleven_mod121_eq
#print axioms blockLocalResidue121_eq_sourceNumber_mod
#print axioms blockLocalResidue121_mod_eleven_eq_zero_iff
#print axioms blockLocalResidue121_eq_zero_iff
#print axioms residueSeed235711_eq_fold
#print axioms fold_prefix_suffix_eq_residueSeed235711
#print axioms residue235711MultipleEventCount_le_minimumCapacity
#print axioms residue235711PreviousSlotCount_insufficient
#print axioms residueSeed235711_product_lt_productRadix
#print axioms residueSeed235711_count_lt_countRadix
#print axioms residueSeed235711Word_lt_two_pow_sixty
#print axioms residueSeed235711Word_lt_wordLimit
#print axioms unpackProduct_residueSeed235711Word
#print axioms unpackCount_residueSeed235711Word
#print axioms unpackSquareful_residueSeed235711Word

end SparkInterval.Tests.MobiusResidue235711Test
