/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusRectangularVisitRealization

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusRectangularVisitRealizationTest

open SparkInterval.TernaryGoldbach.MobiusDenseSchedule
open SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule
open SparkInterval.TernaryGoldbach.MobiusRectangularVisitRealization
open SparkInterval.TernaryGoldbach.MobiusResidue235711
open SparkInterval.TernaryGoldbach.MobiusSegmentEventEnumeration

/-- In `[10,30)`, row offset three is the unique count-exact p11-suffix
rectangular visit for prime thirteen. -/
example :
    ∃! coordinate,
      VisitsRectangularRow 1
        (requiredSlotsPerPrime 20 13)
        0 20 (firstOffset 10 13) 13 3 coordinate := by
  exact
    (residue235711_dvd_iff_existsUnique_countExactVisit
      (by norm_num [multiblockPrimeCount])
      (by norm_num)
      (by
        norm_num [maximumSegmentRows, blockSlotsPerPrime,
          eventsPerBlock, threadsPerBlock, iterationsPerThread])
      (by norm_num [residue235711SuffixMinimumPrime])
      (by norm_num)).2.mp (by norm_num)

/-- The source equivalence is uniform in the segment and contains no project
axiom or native decision procedure. -/
example {primeCount primeIndex lower count offset prime : Nat}
    (primeCountBound : primeCount ≤ multiblockPrimeCount)
    (primeIndexInRange : primeIndex < primeCount)
    (countBound : count ≤ maximumSegmentRows)
    (primeBound :
      residue235711SuffixMinimumPrime ≤ prime)
    (offsetInSegment : offset < count) :
    RectangularGridAdmissible primeCount
        (requiredSlotsPerPrime count
          residue235711SuffixMinimumPrime) ∧
      (prime ∣ lower + offset ↔
        ∃! coordinate,
          VisitsRectangularRow primeCount
            (requiredSlotsPerPrime count
              residue235711SuffixMinimumPrime)
            primeIndex count (firstOffset lower prime) prime offset
            coordinate) :=
  residue235711_dvd_iff_existsUnique_countExactVisit primeCountBound
    primeIndexInRange countBound primeBound offsetInSegment

#print axioms SparkInterval.TernaryGoldbach.MobiusRectangularVisitRealization.dvd_iff_existsUnique_rectangularVisit
#print axioms SparkInterval.TernaryGoldbach.MobiusRectangularVisitRealization.residue235711_dvd_iff_existsUnique_countExactVisit

end SparkInterval.Tests.MobiusRectangularVisitRealizationTest
