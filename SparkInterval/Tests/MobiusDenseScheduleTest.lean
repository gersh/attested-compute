/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusDenseSchedule

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusDenseSchedule

open SparkInterval.TernaryGoldbach.MobiusDenseSchedule

example : eventsPerBlock = 1_048_576 :=
  eventsPerBlock_eq

example : maximumSegmentRows = 1_073_741_824 :=
  maximumSegmentRows_eq

example : multiblockGrid = 102_400 :=
  multiblockGrid_eq

example : residueMinimumBlockSlotsPerPrime = 147 :=
  residueMinimumBlockSlotsPerPrime_eq

example :
    multipleEventCount maximumSegmentRows 0
        residueSuffixMinimumPrime ≤
      residueMinimumBlockSlotsPerPrime * eventsPerBlock :=
  residueMinimumSlots_sufficient_at_public_cap

example :
    (residueMinimumBlockSlotsPerPrime - 1) * eventsPerBlock <
      multipleEventCount maximumSegmentRows 0
        residueSuffixMinimumPrime :=
  residuePreviousSlotCount_insufficient

example : primeIndex (17 * 512 + 23) = 17 := by
  norm_num [primeIndex, blockSlotsPerPrime]

example : blockOrdinal (17 * 512 + 23) = 23 := by
  norm_num [blockOrdinal, blockSlotsPerPrime]

example :
    eventBegin (eventOwner 500_000_000) ≤ 500_000_000 ∧
      500_000_000 <
        eventStop 500_000_001 (eventOwner 500_000_000) := by
  exact event_mem_owner (by norm_num)

#print axioms primeIndex_lt
#print axioms event_block_thread_decode
#print axioms threadOwner_lt
#print axioms iterationOwner_lt
#print axioms event_mem_owner
#print axioms block_eq_eventOwner
#print axioms eventOwner_lt_slots
#print axioms multipleEventCount_le_capacity
#print axioms residueMinimumSlots_sufficient_at_public_cap
#print axioms residuePreviousSlotCount_insufficient
#print axioms residueMultipleEventCount_le_minimumCapacity
#print axioms multipleOffset_lt_count
#print axioms event_lt_multipleEventCount
#print axioms multipleOffset_injective

end SparkInterval.Tests.MobiusDenseSchedule
