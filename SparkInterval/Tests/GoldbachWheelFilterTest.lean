/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachWheelFilter

namespace SparkInterval.Tests.GoldbachWheelFilterTest

open TernaryGoldbach.GoldbachWheelFilter
open TernaryGoldbach.GoldbachWordOwnerSieve

example : KernelFilterSurvives 53 ↔ FilterSurvives 53 :=
  kernelFilterSurvives_iff 53

example :
    32771 * 15 + 2 * 32771 = 32771 * (15 + 2) :=
  tail_cofactor_step 32771 15

example :
    (32771 : Nat) * 15 +
        (2 * 32771) * (((7 : Fin 32) : Nat) + 32 * 19) =
      32771 * (15 + 2 * ((7 : Fin 32) : Nat) + 64 * 19) :=
  warp_cofactor_equation 32771 15 7 19

example :
    ClearedBy
      [3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47]
      (32771 * 21) := by
  apply rejected_tail_event_already_cleared
  · norm_num
  · norm_num
  · intro prime hprime
    simpa [filterPrimes] using hprime
  · simp [FilterSurvives, filterPrimes]

end SparkInterval.Tests.GoldbachWheelFilterTest
