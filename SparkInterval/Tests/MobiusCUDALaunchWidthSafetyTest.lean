/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusCUDALaunchWidthSafety

namespace SparkInterval.Tests.MobiusCUDALaunchWidthSafetyTest

open TernaryGoldbach.MobiusDenseSchedule
open TernaryGoldbach.MobiusCUDALaunchWidthSafety

example :
    10_000_000_000_000_000 + 0 < uint64Radix := by
  exact sourceNumber_lt_wordLimit
    (lower := 10_000_000_000_000_000)
    (count := 1) (index := 0)
    (by rfl) (by norm_num)
    (by norm_num [sourceLimit]) (by norm_num)

example :
    256 * (100_000_000 * 100_000_000) < uint64Radix := by
  exact squareStride_lt_wordLimit
    (prime := 100_000_000) (by rfl)

example :
    1_073_741_823 + 256 * (100_000_000 * 100_000_000) <
      uint64Radix := by
  exact squareLoopIncrement_lt_wordLimit
    (count :=
      TernaryGoldbach.MobiusDenseSchedule.maximumSegmentRows)
    (offset := 1_073_741_823) (prime := 100_000_000)
    (by rfl)
    (by norm_num [TernaryGoldbach.MobiusDenseSchedule.maximumSegmentRows,
      blockSlotsPerPrime, eventsPerBlock, threadsPerBlock,
      iterationsPerThread])
    (by rfl)

example :
    multipleOffset 0 7 153_391_688 < uint64Radix := by
  apply multipleOffset_lt_wordLimit
    (count :=
      TernaryGoldbach.MobiusDenseSchedule.maximumSegmentRows)
  · exact le_rfl
  · norm_num [TernaryGoldbach.MobiusDenseSchedule.maximumSegmentRows,
      blockSlotsPerPrime, eventsPerBlock, threadsPerBlock,
      iterationsPerThread]
  · norm_num [multipleEventCount,
      TernaryGoldbach.MobiusDenseSchedule.maximumSegmentRows,
      blockSlotsPerPrime, eventsPerBlock, threadsPerBlock,
      iterationsPerThread]

#print axioms sourceNumber_lt_wordLimit
#print axioms primeSquare_lt_wordLimit
#print axioms squareStride_lt_wordLimit
#print axioms squareLoopIncrement_lt_wordLimit
#print axioms eventProduct_lt_wordLimit
#print axioms multipleOffset_lt_wordLimit

end SparkInterval.Tests.MobiusCUDALaunchWidthSafetyTest
