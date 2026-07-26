/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusCUDALaunchIndexingTest

open SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing
open SparkInterval.TernaryGoldbach.MobiusDenseSchedule

/-- The rounded third block has the unique active owner of row 512. -/
example :
    ∃! coordinate, OwnsIndex 513 512 coordinate :=
  existsUnique_ownerCoordinate (by norm_num)

example :
    ownerCoordinate 512 = { block := 2, thread := 0 } := by
  norm_num [ownerCoordinate, threadsPerBlock]

/-- The public maximum row launch is strictly inside the host grid limit. -/
example :
    blocksFor maximumSegmentRows ≤ maximumGridX :=
  rowGrid_fits
    (by norm_num [maximumSegmentRows, blockSlotsPerPrime, eventsPerBlock,
      threadsPerBlock, iterationsPerThread])
    (by rfl)

/-- A suffix beginning at roster index 200 assigns its 513th prime to the
unique thread `(block=2, thread=0)`. -/
example :
    ∃! coordinate, OwnsSparsePrime 200 713 712 coordinate := by
  exact
    (sparsePrimeLaunch_complete_duplicateFree
      (by norm_num) (by norm_num) (by norm_num) (by
        norm_num [blocksFor, maximumGridX, threadsPerBlock])).2.2

/-- Event 1025 is generated only by thread one on its fourth iteration. -/
example :
    gridStrideOwner 1025 = { thread := 1, iteration := 4 } := by
  norm_num [gridStrideOwner, threadsPerBlock]

example :
    ∃! coordinate, VisitsEvent 1025 coordinate :=
  eventGridStride_complete_duplicateFree 1025

/-- The first event in slot one is thread zero, iteration zero there. -/
example :
    multiblockEventOwner eventsPerBlock =
      { slot := 1, thread := 0, iteration := 0 } := by
  norm_num [multiblockEventOwner, eventOwner, eventLocal,
    threadOwner, iterationOwner, eventsPerBlock, threadsPerBlock,
    iterationsPerThread]

example :
    ∃! coordinate, VisitsMultiblockEvent
      (blockSlotsPerPrime * eventsPerBlock - 1) coordinate := by
  apply multiblockEvent_complete_duplicateFree
  norm_num [blockSlotsPerPrime, eventsPerBlock, threadsPerBlock,
    iterationsPerThread]

/-- Flat dense block 8,727 is exactly prime slot `(17,23)`. -/
example :
    primeIndex 8_727 = 17 ∧ blockOrdinal 8_727 = 23 := by
  norm_num [primeIndex, blockOrdinal, blockSlotsPerPrime]

#print axioms
  SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing.existsUnique_ownerCoordinate
#print axioms
  SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing.rowLaunch_complete_duplicateFree
#print axioms
  SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing.sparsePrimeLaunch_complete_duplicateFree
#print axioms
  SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing.eventGridStride_complete_duplicateFree
#print axioms
  SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing.multiblockEvent_complete_duplicateFree
#print axioms
  SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing.denseFlatBlock_encode_decode
#print axioms
  SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing.denseFlatBlock_encode_injective

end SparkInterval.Tests.MobiusCUDALaunchIndexingTest
