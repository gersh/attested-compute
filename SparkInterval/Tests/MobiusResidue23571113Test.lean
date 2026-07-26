/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusResidue23571113

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusResidue23571113Test

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusDenseSchedule
open SparkInterval.TernaryGoldbach.MobiusResidue235
open SparkInterval.TernaryGoldbach.MobiusResidue2357
open SparkInterval.TernaryGoldbach.MobiusResidue235711
open SparkInterval.TernaryGoldbach.MobiusResidue23571113

example : seedPrimes23571113 = [2, 3, 5, 7, 11, 13] := by
  decide

example : thirteenSquareModulus = 13 ^ 2 := by
  norm_num [thirteenSquareModulus]

example :
    blockLocalResidue169 10_000_000_000_000_000 17 255 =
      (10_000_000_000_000_000 + 17 * 256 + 255) % 169 := by
  exact blockLocalResidue169_eq_sourceNumber_mod _ _ _

example :
    blockLocalResidue169UInt32 (168 : UInt32) (255 : UInt32) =
      (85 : UInt32) := by
  decide

example :
    (blockLocalResidue169UInt32 (168 : UInt32) (255 : UInt32)).toNat =
      (168 + 255) % 169 := by
  apply blockLocalResidue169UInt32_toNat
  · norm_num [UInt32.toNat_ofNat, thirteenSquareModulus]
  · norm_num [UInt32.toNat_ofNat, threadsPerBlock]

example :
    (blockFirstResidue169UInt64
        10_000_000_000_000_000 1_000_000).toNat =
      (10_000_000_000_000_000 + 1_000_000 * 256) % 169 := by
  apply blockFirstResidue169UInt64_toNat
  norm_num [threadsPerBlock]

example :
    (blockLocalResidue169Machine
        10_000_000_000_000_000 17 (255 : UInt32)).toNat =
      blockLocalResidue169
        10_000_000_000_000_000 17 255 := by
  apply blockLocalResidue169Machine_toNat
  · norm_num
  · norm_num [threadsPerBlock,
      SparkInterval.TernaryGoldbach.MobiusDenseSchedule.maximumSegmentRows,
      blockSlotsPerPrime, eventsPerBlock, iterationsPerThread]
  · norm_num [UInt32.toNat_ofNat, threadsPerBlock]

example : residue23571113SuffixMinimumPrime = 17 := by
  rfl

example : residue23571113MinimumBlockSlotsPerPrime = 61 := by
  exact residue23571113MinimumBlockSlotsPerPrime_eq

example :
    60 * eventsPerBlock <
      multipleEventCount
        SparkInterval.TernaryGoldbach.MobiusDenseSchedule.maximumSegmentRows
        0 17 := by
  simpa [residue23571113SuffixMinimumPrime,
    residue23571113MinimumBlockSlotsPerPrime] using
    residue23571113PreviousSlotCount_insufficient

example : residueSeed23571113 30_030 =
    { product := 30_030, distinctCount := 6, squareful := false } := by
  decide

example : residueSeed23571113 1_690 =
    { product := 130, distinctCount := 3, squareful := true } := by
  decide

example : residueSeed23571113 30_029 = initialSupport := by
  decide

example (n : Nat) :
    foldSupport n ([2, 3, 5, 7, 11, 13] ++ [17, 19]) =
      [17, 19].foldl (applyPrime n) (residueSeed23571113 n) := by
  simpa [seedPrimes23571113, seedPrimes235711, seedPrimes2357,
    seedPrimes] using
    fold_prefix_suffix_eq_residueSeed23571113 n [17, 19]

#print axioms blockLocalResidue169UInt32_toNat
#print axioms blockFirstNumberUInt64_toNat
#print axioms blockFirstResidue169UInt64_toNat
#print axioms blockFirstResidue169UInt32_toNat
#print axioms blockLocalResidue169Machine_toNat
#print axioms applyThirteen_mod169_eq
#print axioms residueSeed23571113_eq_fold
#print axioms fold_prefix_suffix_eq_residueSeed23571113
#print axioms residue23571113MultipleEventCount_le_minimumCapacity
#print axioms residue23571113PreviousSlotCount_insufficient
#print axioms residueSeed23571113Word_lt_two_pow_sixty
#print axioms residueSeed23571113Word_lt_wordLimit

end SparkInterval.Tests.MobiusResidue23571113Test
