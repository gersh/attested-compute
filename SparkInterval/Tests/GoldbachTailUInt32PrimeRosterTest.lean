/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachTailUInt32PrimeRoster

namespace SparkInterval.Tests.GoldbachTailUInt32PrimeRosterTest

open TernaryGoldbach.GoldbachTailUInt32PrimeRoster

example : sourceLaunchBlocks = 38_504 :=
  sourceLaunchBlocks_eq

example : sourceTailPrimeLimit ^ 2 ≤ sourceQHigh ∧
    sourceQHigh < (sourceTailPrimeLimit + 1) ^ 2 :=
  sourceTailPrimeLimit_is_floorSqrt

example :
    compactPrimeLoad sourceTailHighestPrime =
      widePrimeLoad sourceTailHighestPrime :=
  qualifiedPrime_compactLoad_eq sourceTailHighestPrime_le_limit

example (qLow qHigh : UInt64) :
    tailPrimeMachineHead qLow qHigh
        (compactPrimeLoad sourceTailHighestPrime) =
      tailPrimeMachineHead qLow qHigh
        (widePrimeLoad sourceTailHighestPrime) :=
  compactTailPrimeMachineHead_eq
    qLow qHigh sourceTailHighestPrime_le_limit

example :
    compactRosterBytes sourceTailPrimeCount = 39_427_696 :=
  sourceCompactRosterBytes_eq

example :
    wideRosterBytes sourceTailPrimeCount = 78_855_392 :=
  sourceWideRosterBytes_eq

example :
    (compactByteOffsetUInt64 (sourceTailPrimeCount - 1)).toNat <
      compactRosterBytes sourceTailPrimeCount := by
  apply compactMachineByteOffset_lt
  norm_num [sourceTailPrimeCount]

end SparkInterval.Tests.GoldbachTailUInt32PrimeRosterTest
