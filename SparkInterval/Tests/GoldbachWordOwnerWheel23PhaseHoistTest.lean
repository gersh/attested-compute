/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachWordOwnerWheel23PhaseHoist

namespace SparkInterval.Tests.GoldbachWordOwnerWheel23PhaseHoistTest

open TernaryGoldbach.GoldbachWordOwnerWheel23

example : sourceSegmentWordCount = 3_132_813 :=
  sourceSegmentWordCount_eq

example : wheelPackedWordCount = 1_742_915 :=
  wheelPackedWordCount_eq

/-- The largest possible source-segment phase sum needs exactly two guarded
subtractions and remains far below the `UInt32` radix. -/
example :
    reduceWheelPhaseTwice
        ((wheelModulus - 1) +
          64 * (sourceSegmentWordCount - 1)) =
      88_953_532 := by
  norm_num [reduceWheelPhaseTwice, wheelModulus, sourceSegmentWordCount,
    sourceSegmentOddCount]

example :
    (fastSourceWordPhaseUInt32
        (wheelModulus - 1)
        (sourceSegmentWordCount - 1)).toNat =
      88_953_532 := by
  rw [fastSourceWordPhaseUInt32_toNat]
  · norm_num [wheelModulus, sourceSegmentWordCount, sourceSegmentOddCount]
  · norm_num [wheelModulus]
  · norm_num [sourceSegmentWordCount, sourceSegmentOddCount]

/-- The actual machine reducer agrees with the original generic phase at the
last live owner word of the historical terminal segment. -/
example :
    (fastSourceWordPhaseUInt32
        (cudaHalf 31_249_999_599_000_003 % wheelModulus)
        (sourceSegmentWordCount - 1)).toNat =
      cudaWordPhase
        31_249_999_599_000_003
        (sourceSegmentWordCount - 1) := by
  exact fastSourceWordPhaseUInt32_eq_cudaWordPhase
    (by norm_num [sourceSegmentWordCount, sourceSegmentOddCount])

/-- The host `UInt64` shift/modulo and device `UInt32` reducer compose at the
exact terminal source boundary. -/
example :
    (fastSourceWordPhaseUInt32
        (hostQHalfModUInt64 31_249_999_599_000_003).toNat
        (sourceSegmentWordCount - 1)).toNat =
      cudaWordPhase
        31_249_999_599_000_003
        (sourceSegmentWordCount - 1) := by
  exact hostAndDeviceFastPhase_eq_cudaWordPhase
    (by norm_num)
    (by norm_num [sourceSegmentWordCount, sourceSegmentOddCount])

example :
    let phase :=
      (fastSourceWordPhaseUInt32
        (cudaHalf 31_249_999_599_000_003 % wheelModulus)
        (sourceSegmentWordCount - 1)).toNat
    wheelLoadBase phase < wheelPackedWordCount ∧
      wheelLoadBase phase + 1 < wheelPackedWordCount := by
  exact sourceFastPhase_load_addresses_lt
    (by norm_num [sourceSegmentWordCount, sourceSegmentOddCount])

end SparkInterval.Tests.GoldbachWordOwnerWheel23PhaseHoistTest
