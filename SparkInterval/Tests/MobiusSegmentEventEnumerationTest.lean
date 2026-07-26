/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusSegmentEventEnumeration

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusSegmentEventEnumerationTest

open SparkInterval.TernaryGoldbach.MobiusDenseSchedule
open SparkInterval.TernaryGoldbach.MobiusSegmentEventEnumeration

#guard firstOffset 10 7 == 4
#guard multipleEventCount 20 (firstOffset 10 7) 7 == 3
#guard multipleOffset (firstOffset 10 7) 7 0 == 4
#guard multipleOffset (firstOffset 10 7) 7 1 == 11
#guard multipleOffset (firstOffset 10 7) 7 2 == 18

example :
    7 ∣ 10 + 11 ↔
      ∃! event,
        event < multipleEventCount 20 (firstOffset 10 7) 7 ∧
          multipleOffset (firstOffset 10 7) 7 event = 11 :=
  dvd_iff_existsUnique_event (by norm_num) (by norm_num)

#print axioms
  SparkInterval.TernaryGoldbach.MobiusSegmentEventEnumeration.dvd_iff_existsUnique_event

end SparkInterval.Tests.MobiusSegmentEventEnumerationTest
