/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusRectangularCUDAScheduleTest

open SparkInterval.TernaryGoldbach.MobiusDenseSchedule
open SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing
open SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule

/-- The last event admitted by the 79-slot p11-seeded rectangle has one
physical owner. -/
example :
    ∃! coordinate,
      VisitsRectangularEvent
        200 79 199 (79 * eventsPerBlock - 1) coordinate := by
  apply rectangularEvent_complete_duplicateFree
  · norm_num
  · norm_num [eventsPerBlock, threadsPerBlock, iterationsPerThread]

/-- That last p11-seeded event is owned by slot 78, thread 255, on iteration
4095. -/
example :
    multiblockEventOwner (79 * eventsPerBlock - 1) =
      { slot := 78, thread := 255, iteration := 4095 } := by
  norm_num [multiblockEventOwner, eventOwner, eventLocal,
    threadOwner, iterationOwner, eventsPerBlock, threadsPerBlock,
    iterationsPerThread]

/-- The largest candidate rectangular grid fits the explicit CUDA x/y
dimension contract. -/
example : RectangularGridAdmissible 200 512 :=
  qualificationGrid_admissible (by rfl) (by rfl)

/-- Runtime count-exact qualification widths for the 100-million-row
benchmark: 14 after p5, 9 after p7, and 8 after p11. -/
example : requiredSlotsPerPrime 100_000_000 7 = 14 := by
  norm_num [requiredSlotsPerPrime, eventsPerBlock, threadsPerBlock,
    iterationsPerThread]

example : requiredSlotsPerPrime 100_000_000 11 = 9 := by
  norm_num [requiredSlotsPerPrime, eventsPerBlock, threadsPerBlock,
    iterationsPerThread]

example : requiredSlotsPerPrime 100_000_000 13 = 8 := by
  norm_num [requiredSlotsPerPrime, eventsPerBlock, threadsPerBlock,
    iterationsPerThread]

/-- The existing multi-slot p13 boundary KAT needs exactly two slots, and
the general capacity theorem covers its complete event stream. -/
example :
    requiredSlotsPerPrime (13 * eventsPerBlock + 1) 13 = 2 := by
  norm_num [requiredSlotsPerPrime, eventsPerBlock, threadsPerBlock,
    iterationsPerThread]

example :
    multipleEventCount (13 * eventsPerBlock + 1) 0 13 ≤
      requiredSlotsPerPrime (13 * eventsPerBlock + 1) 13 *
        eventsPerBlock :=
  multipleEventCount_le_requiredSlotsCapacity (by norm_num) (by norm_num)

/-- At the public row cap, the last p=13 event has exactly one owner in the
minimal 79-slot p11-seeded schedule. -/
example :
    ∃! coordinate,
      VisitsRectangularEvent
        200 79 0
        (multipleEventCount maximumSegmentRows 0 13 - 1)
        coordinate := by
  apply residue235711RectangularEvent_complete_duplicateFree
      (primeCount := 200) (primeIndex := 0)
      (count := maximumSegmentRows) (firstOffset := 0)
      (prime := 13)
  · norm_num
  · exact le_rfl
  · norm_num [
      SparkInterval.TernaryGoldbach.MobiusResidue235711.residue235711SuffixMinimumPrime]
  · have positive :
        0 <
          multipleEventCount maximumSegmentRows 0 13 := by
      norm_num [multipleEventCount, maximumSegmentRows,
        blockSlotsPerPrime, eventsPerBlock, threadsPerBlock,
        iterationsPerThread]
    omega

#print axioms multiblockEventWithSlots_complete_duplicateFree
#print axioms rectangularEvent_complete_duplicateFree
#print axioms multipleEventCount_le_requiredSlotsCapacity
#print axioms previousRequiredSlotCount_insufficient
#print axioms qualificationGrid_admissible
#print axioms residue235711RectangularEvent_complete_duplicateFree

end SparkInterval.Tests.MobiusRectangularCUDAScheduleTest
