/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachWordOwnerSieve

namespace SparkInterval.Tests.GoldbachWordOwnerSieveTest

open TernaryGoldbach.GoldbachWordOwnerSieve

example :
    SplitClearedBy 7 [3, 5, 7, 11, 13] 121 ↔
      ClearedBy [3, 5, 7, 11, 13] 121 :=
  splitClearedBy_iff 7 [3, 5, 7, 11, 13] 121

example :
    (¬ SplitClearedBy 7 [3, 5, 7, 11, 13] 127) ↔
      ¬ ClearedBy [3, 5, 7, 11, 13] 127 :=
  survives_split_iff 7 [3, 5, 7, 11, 13] 127

example :
    ThreeTierClearedBy 7 11 [3, 5, 7, 11, 13, 17] 169 ↔
      ClearedBy [3, 5, 7, 11, 13, 17] 169 :=
  threeTierClearedBy_iff 7 11 [3, 5, 7, 11, 13, 17] 169

example :
    warpComposite 101 14 (laneOfIndex 1000) (1000 / 32) =
      101 + 14 * 1000 :=
  warpComposite_covers 101 14 1000

example :
    101 + 128 * oddWordIndex 101 1001 +
        2 * oddBitInWord 101 1001 =
      1001 :=
  odd_word_bit_reconstruct 101 1001 450 (by norm_num)

example : ¬ 2039 * 2039 ≤ 2039 :=
  square_guard_preserves_self (by norm_num)

end SparkInterval.Tests.GoldbachWordOwnerSieveTest
