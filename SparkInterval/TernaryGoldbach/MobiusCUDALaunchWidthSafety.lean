/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing
import SparkInterval.TernaryGoldbach.MobiusSegmentEventEnumeration

/-!
# Fixed-width bounds for the production Möbius CUDA launch arithmetic

`MobiusCUDALaunchIndexing` proves the natural-number ownership formulas used
by the split-square CUDA path.  This module checks the corresponding
production constants fit the unsigned 64-bit arithmetic used for source
numbers, prime squares, strides, event ordinals, and row offsets.

These are integer range theorems.  They do not identify C++ `size_t`, CUDA
builtins, pointer arithmetic, or compiled instructions with the modeled
natural numbers.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusCUDALaunchWidthSafety

open SparkInterval.TernaryGoldbach.MobiusDenseSchedule
open SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing
open SparkInterval.TernaryGoldbach.MobiusSegmentEventEnumeration

/-- Cardinality of the native unsigned 64-bit word type. -/
def uint64Radix : Nat := 2 ^ 64

/-- Largest source integer admitted by the native Möbius path. -/
def sourceLimit : Nat := 10_000_000_000_000_000

/-- Largest prime admitted by the device roster preflight. -/
def maximumPrime : Nat := 100_000_000

theorem sourceLimit_lt_wordLimit :
    sourceLimit < uint64Radix := by
  norm_num [sourceLimit, uint64Radix]

theorem maximumSegmentRows_lt_wordLimit :
    MobiusDenseSchedule.maximumSegmentRows < uint64Radix := by
  norm_num [MobiusDenseSchedule.maximumSegmentRows, blockSlotsPerPrime,
    eventsPerBlock, threadsPerBlock, iterationsPerThread, uint64Radix]

/-- The host endpoint subtraction guard makes every active `lower + index`
source number nonwrapping. -/
theorem sourceNumber_lt_wordLimit
    {lower count index : Nat}
    (lowerBound : lower ≤ sourceLimit)
    (countPositive : 0 < count)
    (endpointGuard : count - 1 ≤ sourceLimit - lower)
    (indexInRange : index < count) :
    lower + index < uint64Radix := by
  have endpointLe : lower + (count - 1) ≤ sourceLimit := by
    have := Nat.add_le_add_left endpointGuard lower
    rw [Nat.add_sub_of_le lowerBound] at this
    exact this
  have indexLe : index ≤ count - 1 := by omega
  exact lt_of_le_of_lt
    (le_trans (Nat.add_le_add_left indexLe lower) endpointLe)
    sourceLimit_lt_wordLimit

/-- A machine-safe prime square is exact in `uint64_t`. -/
theorem primeSquare_lt_wordLimit
    {prime : Nat}
    (primeBound : prime ≤ maximumPrime) :
    prime * prime < uint64Radix := by
  norm_num [maximumPrime, uint64Radix] at primeBound ⊢
  nlinarith

/-- The one-block distinct-divisor stride `256 * p` is nonwrapping. -/
theorem divisorStride_lt_wordLimit
    {prime : Nat}
    (primeBound : prime ≤ maximumPrime) :
    threadsPerBlock * prime < uint64Radix := by
  norm_num [threadsPerBlock, maximumPrime, uint64Radix] at primeBound ⊢
  omega

/-- Even the largest square-strike stride `256 * p²` is nonwrapping. -/
theorem squareStride_lt_wordLimit
    {prime : Nat}
    (primeBound : prime ≤ maximumPrime) :
    threadsPerBlock * (prime * prime) < uint64Radix := by
  norm_num [threadsPerBlock, maximumPrime, uint64Radix] at primeBound ⊢
  nlinarith

/-- Advancing a live distinct-divisor loop by its full block stride cannot
wrap, even when the increment leaves the segment and terminates the loop. -/
theorem divisorLoopIncrement_lt_wordLimit
    {count offset prime : Nat}
    (countBound :
      count ≤ MobiusDenseSchedule.maximumSegmentRows)
    (offsetInRange : offset < count)
    (primeBound : prime ≤ maximumPrime) :
    offset + threadsPerBlock * prime < uint64Radix := by
  norm_num [MobiusDenseSchedule.maximumSegmentRows, blockSlotsPerPrime,
    eventsPerBlock, threadsPerBlock, iterationsPerThread,
    maximumPrime, uint64Radix] at countBound primeBound ⊢
  omega

/-- The analogous `offset += 256 * p²` square-strike increment is also
nonwrapping at the largest admitted prime. -/
theorem squareLoopIncrement_lt_wordLimit
    {count offset prime : Nat}
    (countBound :
      count ≤ MobiusDenseSchedule.maximumSegmentRows)
    (offsetInRange : offset < count)
    (primeBound : prime ≤ maximumPrime) :
    offset + threadsPerBlock * (prime * prime) < uint64Radix := by
  norm_num [MobiusDenseSchedule.maximumSegmentRows, blockSlotsPerPrime,
    eventsPerBlock, threadsPerBlock, iterationsPerThread,
    maximumPrime, uint64Radix] at countBound primeBound ⊢
  nlinarith

/-- Every active multiblock event ordinal and its one-block exclusive stop
fit in `uint64_t`. -/
theorem multiblockEventStop_lt_wordLimit
    {slot : Nat}
    (slotInRange : slot < blockSlotsPerPrime) :
    eventBegin slot + eventsPerBlock < uint64Radix := by
  norm_num [eventBegin, blockSlotsPerPrime, eventsPerBlock,
    threadsPerBlock, iterationsPerThread, uint64Radix] at slotInRange ⊢
  omega

/-- Every admitted event's literal `event * p` product is already bounded by
its in-segment row offset, hence is nonwrapping independently of the source
endpoint. -/
theorem eventProduct_lt_wordLimit
    {count firstOffset prime event : Nat}
    (countBound :
      count ≤ MobiusDenseSchedule.maximumSegmentRows)
    (firstInRange : firstOffset < count)
    (eventInRange :
      event < multipleEventCount count firstOffset prime) :
    event * prime < uint64Radix := by
  have offsetInRange :
      multipleOffset firstOffset prime event < count :=
    multipleOffset_lt_count firstInRange eventInRange
  have productLeOffset :
      event * prime ≤ multipleOffset firstOffset prime event := by
    simp only [multipleOffset]
    omega
  exact lt_of_le_of_lt productLeOffset
    (lt_of_lt_of_le offsetInRange
      (le_trans countBound maximumSegmentRows_lt_wordLimit.le))

/-- The complete native offset expression fits in `uint64_t`. -/
theorem multipleOffset_lt_wordLimit
    {count firstOffset prime event : Nat}
    (countBound :
      count ≤ MobiusDenseSchedule.maximumSegmentRows)
    (firstInRange : firstOffset < count)
    (eventInRange :
      event < multipleEventCount count firstOffset prime) :
    multipleOffset firstOffset prime event < uint64Radix := by
  exact lt_of_lt_of_le
    (SparkInterval.TernaryGoldbach.MobiusDenseSchedule.multipleOffset_lt_count
      firstInRange eventInRange)
    (le_trans countBound maximumSegmentRows_lt_wordLimit.le)

#print axioms sourceNumber_lt_wordLimit
#print axioms primeSquare_lt_wordLimit
#print axioms divisorStride_lt_wordLimit
#print axioms squareStride_lt_wordLimit
#print axioms divisorLoopIncrement_lt_wordLimit
#print axioms squareLoopIncrement_lt_wordLimit
#print axioms multiblockEventStop_lt_wordLimit
#print axioms eventProduct_lt_wordLimit
#print axioms multipleOffset_lt_wordLimit

end SparkInterval.TernaryGoldbach.MobiusCUDALaunchWidthSafety
