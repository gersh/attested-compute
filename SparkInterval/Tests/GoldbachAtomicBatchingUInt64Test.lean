/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachAtomicBatchingUInt64

namespace SparkInterval.Tests.GoldbachAtomicBatchingUInt64Test

open TernaryGoldbach.GoldbachAtomicClears
open TernaryGoldbach.GoldbachAtomicBatching
open TernaryGoldbach.GoldbachAtomicBatchingUInt64

private def allOnes : Word :=
  fun _ => true

private def bitThree : Fin 64 :=
  ⟨3, by norm_num⟩

private def bitFour : Fin 64 :=
  ⟨4, by norm_num⟩

private def bitSixtyThree : Fin 64 :=
  ⟨63, by norm_num⟩

example :
    (clearBitMask64 bitThree).testBit bitThree = false := by
  simpa using testBit_clearBitMask64 bitThree bitThree

example :
    (clearBitMask64 bitThree).testBit bitFour = true := by
  simpa [bitThree, bitFour] using
    testBit_clearBitMask64 bitThree bitFour

example :
    (nativeClearBitMask64 bitSixtyThree).toNat =
      clearBitMask64 bitSixtyThree :=
  nativeClearBitMask64_toNat bitSixtyThree

example :
    encodeUInt64 (atomicClear allOnes bitThree) =
      encodeUInt64 allOnes &&& nativeClearBitMask64 bitThree :=
  encodeUInt64_atomicClear allOnes bitThree

example :
    nativeAccumulatedClearMask [bitThree, bitThree, bitFour] =
      UInt64.ofNat
        (encodeWord (clearMask [bitThree, bitThree, bitFour])) :=
  nativeAccumulatedClearMask_eq_encoded _

example :
    encodeUInt64 allOnes &&&
        nativeAccumulatedClearMask [bitThree, bitThree, bitFour] =
      encodeUInt64
        (applyClearMask allOnes [bitThree, bitThree, bitFour]) :=
  nativeFlush_eq_applyClearMask _ _

example :
    sourceSegmentWordCount = 3_132_813 :=
  sourceSegmentWordCount_eq

example :
    (sourceSegmentOddCount - 1) / 64 = 3_132_812 := by
  norm_num [sourceSegmentOddCount]

example :
    (sourceSegmentOddCount - 1) / 64 ≠ uint64Max := by
  apply sourceLiveBit_wordKey_ne_emptyKey
  norm_num [sourceSegmentOddCount]

example :
    tableHash512 3_132_812 = 124 := by
  rw [tableHash512_eq_mod]
  norm_num [tableHashMultiplier, maximumTableSlots]

example :
    (nativeTableHash512 (UInt64.ofNat 3_132_812)).toNat = 124 := by
  rw [nativeTableHash512_toNat, UInt64.toNat_ofNat']
  rw [Nat.mod_eq_of_lt (by norm_num : 3_132_812 < 2 ^ 64)]
  rw [tableHash512_eq_mod]
  norm_num [tableHashMultiplier, maximumTableSlots]

example :
    probeSlot 9 500 20 = 8 := by
  rw [probeSlot_eq_mod]
  norm_num

example :
    (nativeProbeSlot512 (UInt32.ofNat 500) (UInt32.ofNat 20)).toNat = 8 := by
  rw [nativeProbeSlot512_toNat]
  · rw [probeSlot_eq_mod]
    norm_num
  · norm_num [maximumTableSlots]
  · norm_num [maximumTableSlots]

example :
    511 + 511 < 2 ^ 32 := by
  exact maximumProbeAdd_lt_uint32
    (by norm_num [maximumTableSlots])
    (by norm_num [maximumTableSlots])

end SparkInterval.Tests.GoldbachAtomicBatchingUInt64Test
