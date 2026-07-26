/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusSquareOffsetHelper

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusSquareOffsetHelperTest

open SparkInterval.TernaryGoldbach.MobiusDenseSchedule
open SparkInterval.TernaryGoldbach.MobiusSquareOffsetHelper

#guard cudaFirst 100 25 == 0
#guard firstSquareOffset 100 7 25 == some 0
#guard firstSquareOffset 10 39 49 == none
#guard firstSquareOffset 10 40 49 == some 39
#guard firstSquareOffset 10 20 7 == some 4

example :
    firstSquareOffset 10 20 7 = some 4 ↔
      4 < 20 ∧
        7 ∣ 10 + 4 ∧
        ∀ earlier, earlier < 4 → ¬ 7 ∣ 10 + earlier :=
  firstSquareOffset_eq_some_iff_unique_least (by norm_num)

example :
    firstSquareOffset 10 3 7 = none ↔
      ∀ offset, offset < 3 → ¬ 7 ∣ 10 + offset :=
  firstSquareOffset_eq_none_iff_no_dvd (by norm_num)

example :
    7 ∣ 10 + 18 ↔
      ∃! event,
        event < multipleEventCount 20 4 7 ∧
          multipleOffset 4 7 event = 18 :=
  returned_offset_dvd_iff_existsUnique_loop_event
    (by norm_num)
    (by norm_num [firstSquareOffset, cudaFirst])
    (by norm_num)

example : ProductionGuards
    10_000_000_000_000_000 100_000_000
      10_000_000_000_000_000 := by
  constructor <;> norm_num [productionSourceLimit, productionSegmentLimit]

#print axioms
  SparkInterval.TernaryGoldbach.MobiusSquareOffsetHelper.firstSquareOffset_eq_some_iff_unique_least
#print axioms
  SparkInterval.TernaryGoldbach.MobiusSquareOffsetHelper.firstSquareOffset_eq_none_iff_no_dvd
#print axioms
  SparkInterval.TernaryGoldbach.MobiusSquareOffsetHelper.returned_offset_dvd_iff_existsUnique_loop_event
#print axioms
  SparkInterval.TernaryGoldbach.MobiusSquareOffsetHelper.loop_increment_le_uint64Max

end SparkInterval.Tests.MobiusSquareOffsetHelperTest
