/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule
import SparkInterval.TernaryGoldbach.MobiusSegmentEventEnumeration

/-!
# Divisible-row realization by the rectangular CUDA schedule

`MobiusSegmentEventEnumeration` proves that one prime's native arithmetic
progression enumerates every divisible segment row exactly once.
`MobiusRectangularCUDASchedule` independently proves that every admitted
prime-event ordinal has exactly one
`(blockIdx.y, blockIdx.x, threadIdx.x, iteration)` owner.

This file composes those two results.  For an arbitrary safe positive slot
width, an in-segment row is divisible by the supplied prime if and only if
exactly one legal rectangular CUDA coordinate visits it.  Count-exact
corollaries instantiate the literal native width formula after the p5, p7,
and p11 residue seeds.

The theorem remains architecture-independent.  It identifies the natural
number launch model with the source divisibility predicate, not NVCC output,
SASS instructions, CUDA atomics, or physical GPU execution.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusRectangularVisitRealization

open SparkInterval.TernaryGoldbach.MobiusDenseSchedule
open SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing
open SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule
open SparkInterval.TernaryGoldbach.MobiusSegmentEventEnumeration

/-- A physical rectangular coordinate visits `offset` when it owns an
admitted event for the selected prime and that event's arithmetic progression
lands on the row. -/
def VisitsRectangularRow
    (primeCount slots primeIndex count first prime offset : Nat)
    (coordinate : RectangularEventCoordinate) : Prop :=
  VisitsRectangularEvent primeCount slots primeIndex
      coordinate.inner.event coordinate ∧
    coordinate.inner.event <
      multipleEventCount count first prime ∧
    multipleOffset first prime coordinate.inner.event = offset

/-- Generic composition theorem for any positive prime and any rectangular
width which covers its event roster. -/
theorem dvd_iff_existsUnique_rectangularVisit
    {primeCount slots primeIndex lower count offset prime : Nat}
    (primeIndexInRange : primeIndex < primeCount)
    (primePositive : 0 < prime)
    (offsetInSegment : offset < count)
    (capacity :
      multipleEventCount count (firstOffset lower prime) prime ≤
        slots * eventsPerBlock) :
    prime ∣ lower + offset ↔
      ∃! coordinate,
        VisitsRectangularRow
          primeCount slots primeIndex count
          (firstOffset lower prime) prime offset coordinate := by
  constructor
  · intro divides
    rcases
        (dvd_iff_existsUnique_event primePositive offsetInSegment).mp
          divides with
      ⟨event, eventFacts, eventUnique⟩
    have eventInCapacity :
        event < slots * eventsPerBlock :=
      lt_of_lt_of_le eventFacts.1 capacity
    rcases
        rectangularEvent_complete_duplicateFree
          primeIndexInRange eventInCapacity with
      ⟨owner, ownerVisits, ownerUnique⟩
    have ownerEventEq : owner.inner.event = event :=
      ownerVisits.2.2.2.2.2
    refine ⟨owner, ⟨?_, ?_, ?_⟩, ?_⟩
    · simpa [ownerEventEq] using ownerVisits
    · simpa [ownerEventEq] using eventFacts.1
    · simpa [ownerEventEq] using eventFacts.2
    intro coordinate coordinateVisits
    have coordinateEventEq :
        coordinate.inner.event = event :=
      multipleOffset_injective primePositive
        (coordinateVisits.2.2.trans eventFacts.2.symm)
    apply ownerUnique coordinate
    simpa [coordinateEventEq] using coordinateVisits.1
  · rintro ⟨coordinate, coordinateVisits, _⟩
    rw [← coordinateVisits.2.2]
    exact dvd_multipleOffset lower
      (firstOffset lower prime) prime coordinate.inner.event
      (firstOffset_dvd lower primePositive)

/-- Count-exact rectangular realization after the `2·3·5` residue seed. -/
theorem residue235_dvd_iff_existsUnique_countExactVisit
    {primeCount primeIndex lower count offset prime : Nat}
    (primeCountBound : primeCount ≤ multiblockPrimeCount)
    (primeIndexInRange : primeIndex < primeCount)
    (countBound : count ≤ maximumSegmentRows)
    (primeBound : residueSuffixMinimumPrime ≤ prime)
    (offsetInSegment : offset < count) :
    RectangularGridAdmissible primeCount
        (requiredSlotsPerPrime count residueSuffixMinimumPrime) ∧
      (prime ∣ lower + offset ↔
        ∃! coordinate,
          VisitsRectangularRow primeCount
            (requiredSlotsPerPrime count residueSuffixMinimumPrime)
            primeIndex count (firstOffset lower prime) prime offset
            coordinate) := by
  have minimumPrimePositive : 0 < residueSuffixMinimumPrime := by
    norm_num [residueSuffixMinimumPrime]
  have primePositive : 0 < prime := lt_of_lt_of_le
    minimumPrimePositive primeBound
  constructor
  · apply qualificationGrid_admissible primeCountBound
    exact (residue235_requiredSlots_le_minimumWidth countBound).trans
      (by
        norm_num [residueMinimumBlockSlotsPerPrime,
          blockSlotsPerPrime])
  · apply dvd_iff_existsUnique_rectangularVisit
      primeIndexInRange primePositive offsetInSegment
    exact multipleEventCount_le_requiredSlotsCapacity
      minimumPrimePositive primeBound

/-- Count-exact rectangular realization after the `2·3·5·7` residue seed. -/
theorem residue2357_dvd_iff_existsUnique_countExactVisit
    {primeCount primeIndex lower count offset prime : Nat}
    (primeCountBound : primeCount ≤ multiblockPrimeCount)
    (primeIndexInRange : primeIndex < primeCount)
    (countBound : count ≤ maximumSegmentRows)
    (primeBound :
      MobiusResidue2357.residue2357SuffixMinimumPrime ≤ prime)
    (offsetInSegment : offset < count) :
    RectangularGridAdmissible primeCount
        (requiredSlotsPerPrime count
          MobiusResidue2357.residue2357SuffixMinimumPrime) ∧
      (prime ∣ lower + offset ↔
        ∃! coordinate,
          VisitsRectangularRow primeCount
            (requiredSlotsPerPrime count
              MobiusResidue2357.residue2357SuffixMinimumPrime)
            primeIndex count (firstOffset lower prime) prime offset
            coordinate) := by
  have minimumPrimePositive :
      0 < MobiusResidue2357.residue2357SuffixMinimumPrime := by
    norm_num [MobiusResidue2357.residue2357SuffixMinimumPrime]
  have primePositive : 0 < prime := lt_of_lt_of_le
    minimumPrimePositive primeBound
  constructor
  · apply qualificationGrid_admissible primeCountBound
    exact (residue2357_requiredSlots_le_minimumWidth countBound).trans
      (by
        norm_num
          [MobiusResidue2357.residue2357MinimumBlockSlotsPerPrime,
           blockSlotsPerPrime])
  · apply dvd_iff_existsUnique_rectangularVisit
      primeIndexInRange primePositive offsetInSegment
    exact multipleEventCount_le_requiredSlotsCapacity
      minimumPrimePositive primeBound

/-- Count-exact rectangular realization after the `2·3·5·7·11` residue
seed. -/
theorem residue235711_dvd_iff_existsUnique_countExactVisit
    {primeCount primeIndex lower count offset prime : Nat}
    (primeCountBound : primeCount ≤ multiblockPrimeCount)
    (primeIndexInRange : primeIndex < primeCount)
    (countBound : count ≤ maximumSegmentRows)
    (primeBound :
      MobiusResidue235711.residue235711SuffixMinimumPrime ≤ prime)
    (offsetInSegment : offset < count) :
    RectangularGridAdmissible primeCount
        (requiredSlotsPerPrime count
          MobiusResidue235711.residue235711SuffixMinimumPrime) ∧
      (prime ∣ lower + offset ↔
        ∃! coordinate,
          VisitsRectangularRow primeCount
            (requiredSlotsPerPrime count
              MobiusResidue235711.residue235711SuffixMinimumPrime)
            primeIndex count (firstOffset lower prime) prime offset
            coordinate) := by
  have minimumPrimePositive :
      0 < MobiusResidue235711.residue235711SuffixMinimumPrime := by
    norm_num [MobiusResidue235711.residue235711SuffixMinimumPrime]
  have primePositive : 0 < prime := lt_of_lt_of_le
    minimumPrimePositive primeBound
  constructor
  · apply qualificationGrid_admissible primeCountBound
    exact (residue235711_requiredSlots_le_minimumWidth countBound).trans
      (by
        norm_num
          [MobiusResidue235711.residue235711MinimumBlockSlotsPerPrime,
           blockSlotsPerPrime])
  · apply dvd_iff_existsUnique_rectangularVisit
      primeIndexInRange primePositive offsetInSegment
    exact multipleEventCount_le_requiredSlotsCapacity
      minimumPrimePositive primeBound

#print axioms dvd_iff_existsUnique_rectangularVisit
#print axioms residue235_dvd_iff_existsUnique_countExactVisit
#print axioms residue2357_dvd_iff_existsUnique_countExactVisit
#print axioms residue235711_dvd_iff_existsUnique_countExactVisit

end SparkInterval.TernaryGoldbach.MobiusRectangularVisitRealization
