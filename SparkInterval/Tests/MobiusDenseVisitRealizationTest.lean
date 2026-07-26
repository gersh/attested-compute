/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusDenseVisitRealization

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusDenseVisitRealizationTest

open SparkInterval.TernaryGoldbach.MobiusDenseSchedule
open SparkInterval.TernaryGoldbach.MobiusSegmentEventEnumeration
open SparkInterval.TernaryGoldbach.MobiusDenseVisitRealization

/-- In `[10, 30)`, the unique dense-schedule visit for the first multiple of
seven is block zero, thread zero, iteration zero. -/
example :
    ∃! visit,
      Visits 20 (firstOffset 10 7) 7 4 visit := by
  exact
    (dvd_iff_existsUnique_denseVisit
      (by norm_num [maximumSegmentRows, blockSlotsPerPrime,
        eventsPerBlock, threadsPerBlock, iterationsPerThread])
      (by norm_num [residueSuffixMinimumPrime])
      (by norm_num)).mp (by norm_num)

/-- The theorem exposes the exact public-cap launch condition without a
native decision procedure or project axiom. -/
example {lower count offset prime : Nat}
    (countBound : count ≤ maximumSegmentRows)
    (primeBound : residueSuffixMinimumPrime ≤ prime)
    (offsetInSegment : offset < count) :
    prime ∣ lower + offset ↔
      ∃! visit,
        Visits count (firstOffset lower prime) prime offset visit :=
  dvd_iff_existsUnique_denseVisit
    countBound primeBound offsetInSegment

#print axioms
  SparkInterval.TernaryGoldbach.MobiusDenseVisitRealization.dvd_iff_existsUnique_denseVisit

end SparkInterval.Tests.MobiusDenseVisitRealizationTest
