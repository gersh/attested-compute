/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing
import SparkInterval.TernaryGoldbach.MobiusResidue235711

/-!
# Parametric two-dimensional CUDA schedule for dense Möbius events

The production Möbius kernel currently flattens a `primeCount × 512`
rectangle and recovers the prime and slot with division and remainder.  A
qualification candidate can instead launch the same rectangle as

```text
grid.x = slotsPerPrime
grid.y = primeCount
prime = blockIdx.y
slot  = blockIdx.x
```

This file proves the architecture-independent schedule for an arbitrary
positive slot count.  In particular, it covers the exact safe rectangular
widths 147 after the `2·3·5` seed, 94 after the `2·3·5·7` seed, and 79 after
the `2·3·5·7·11` seed.  Every admitted multiple ordinal has exactly one
prime/slot/thread/iteration owner.

The theorem does not identify CUDA registers, instructions, or launch
execution with these definitions.  Those remain an explicit compiled-code
and runtime boundary.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule

open SparkInterval.TernaryGoldbach.MobiusDenseSchedule
open SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing

/-- Largest `grid.y` dimension admitted by the CUDA execution contract. -/
def maximumGridY : Nat := 65_535

/-- The literal slot/thread/iteration coordinate within one prime row of a
two-dimensional dense-event launch. -/
def VisitsMultiblockEventWithSlots
    (slots event : Nat) (coordinate : MultiblockEventCoordinate) : Prop :=
  coordinate.slot < slots ∧
    coordinate.thread < threadsPerBlock ∧
    coordinate.iteration < iterationsPerThread ∧
    coordinate.event = event

/-- The canonical event owner is independent of the selected rectangular
width.  The width only determines whether that owner is admitted. -/
theorem multiblockEventWithSlots_complete_duplicateFree
    {slots event : Nat}
    (inCapacity : event < slots * eventsPerBlock) :
    ∃! coordinate,
      VisitsMultiblockEventWithSlots slots event coordinate := by
  have ownerSlot :
      (multiblockEventOwner event).slot < slots := by
    change eventOwner event < slots
    rw [eventOwner, Nat.div_lt_iff_lt_mul]
    · exact inCapacity
    · norm_num [eventsPerBlock, threadsPerBlock,
        iterationsPerThread]
  have ownerThread :
      (multiblockEventOwner event).thread < threadsPerBlock := by
    exact threadOwner_lt (eventLocal event)
  have localInRange :
      eventLocal event < eventsPerBlock :=
    Nat.mod_lt _ (by
      norm_num [eventsPerBlock, threadsPerBlock,
        iterationsPerThread])
  have ownerIteration :
      (multiblockEventOwner event).iteration <
        iterationsPerThread := by
    exact iterationOwner_lt localInRange
  refine ⟨multiblockEventOwner event,
    ⟨ownerSlot, ownerThread, ownerIteration,
      multiblockEventOwner_event event⟩, ?_⟩
  intro coordinate visits
  have coordinateLocal :
      coordinate.iteration * threadsPerBlock +
          coordinate.thread < eventsPerBlock := by
    have iterationBound := visits.2.2.1
    have threadBound := visits.2.1
    norm_num [eventsPerBlock, threadsPerBlock,
      iterationsPerThread] at iterationBound threadBound ⊢
    omega
  have coordinateBegin :
      eventBegin coordinate.slot ≤ event := by
    rw [← visits.2.2.2]
    simp only [eventBegin, MultiblockEventCoordinate.event]
    omega
  have coordinateStop :
      event <
        eventBegin coordinate.slot + eventsPerBlock := by
    rw [← visits.2.2.2]
    simp only [eventBegin, MultiblockEventCoordinate.event]
    omega
  have slotEq :
      coordinate.slot = (multiblockEventOwner event).slot := by
    exact block_eq_eventOwner coordinateBegin coordinateStop
  have localEq :
      coordinate.iteration * threadsPerBlock +
          coordinate.thread =
        (multiblockEventOwner event).iteration * threadsPerBlock +
          (multiblockEventOwner event).thread := by
    have eventEq := visits.2.2.2.trans
      (multiblockEventOwner_event event).symm
    simp only [MultiblockEventCoordinate.event, slotEq] at eventEq
    exact Nat.add_left_cancel eventEq
  have innerEq :
      ThreadCoordinate.mk coordinate.iteration coordinate.thread =
        ThreadCoordinate.mk
          (multiblockEventOwner event).iteration
          (multiblockEventOwner event).thread := by
    apply globalIndex_injective visits.2.1 ownerThread
    simpa [ThreadCoordinate.globalIndex] using localEq
  have threadEq :
      coordinate.thread = (multiblockEventOwner event).thread :=
    congrArg ThreadCoordinate.thread innerEq
  have iterationEq :
      coordinate.iteration = (multiblockEventOwner event).iteration :=
    congrArg ThreadCoordinate.block innerEq
  cases coordinate with
  | mk slot thread iteration =>
      rw [MultiblockEventCoordinate.mk.injEq]
      exact ⟨slotEq, threadEq, iterationEq⟩

/-- Full physical coordinate of one event in a two-dimensional CUDA grid. -/
structure RectangularEventCoordinate where
  prime : Nat
  inner : MultiblockEventCoordinate
deriving DecidableEq, Repr

/-- A coordinate visits the requested prime/event pair exactly when its
`blockIdx.y` prime is in range and its inner
`blockIdx.x`/thread/iteration coordinate visits the event. -/
def VisitsRectangularEvent
    (primeCount slots prime event : Nat)
    (coordinate : RectangularEventCoordinate) : Prop :=
  coordinate.prime < primeCount ∧
    coordinate.prime = prime ∧
    VisitsMultiblockEventWithSlots slots event coordinate.inner

/-- A two-dimensional rectangular launch has one and only one physical owner
for every in-range prime and every event below the selected slot capacity. -/
theorem rectangularEvent_complete_duplicateFree
    {primeCount slots prime event : Nat}
    (primeInRange : prime < primeCount)
    (eventInCapacity : event < slots * eventsPerBlock) :
    ∃! coordinate,
      VisitsRectangularEvent
        primeCount slots prime event coordinate := by
  rcases multiblockEventWithSlots_complete_duplicateFree eventInCapacity with
    ⟨innerOwner, innerVisits, innerUnique⟩
  refine ⟨⟨prime, innerOwner⟩,
    ⟨primeInRange, rfl, innerVisits⟩, ?_⟩
  intro coordinate visits
  have primeEq : coordinate.prime = prime := visits.2.1
  have innerEq : coordinate.inner = innerOwner :=
    innerUnique coordinate.inner visits.2.2
  cases coordinate
  simp_all

/-- Explicit host-side dimension guards for the proposed two-dimensional
qualification grid. -/
def RectangularGridAdmissible (primeCount slots : Nat) : Prop :=
  slots ≤ maximumGridX ∧ primeCount ≤ maximumGridY

/-- Exact number of block slots needed for the worst event stream in a
positive-width suffix whose primes are at least `minimumPrime`.

For a nonempty segment the worst stream has
`1 + (count - 1) / minimumPrime` events.  Dividing its zero-based final
ordinal by `eventsPerBlock` therefore gives the exact last occupied slot.
The empty segment uses no slots. -/
def requiredSlotsPerPrime (count minimumPrime : Nat) : Nat :=
  if count = 0 then 0
  else 1 + ((count - 1) / minimumPrime) / eventsPerBlock

/-- The count-exact width covers every event for every suffix prime at least
`minimumPrime`, independently of the first in-segment multiple. -/
theorem multipleEventCount_le_requiredSlotsCapacity
    {count firstOffset minimumPrime prime : Nat}
    (minimumPrimePositive : 0 < minimumPrime)
    (primeBound : minimumPrime ≤ prime) :
    multipleEventCount count firstOffset prime ≤
      requiredSlotsPerPrime count minimumPrime * eventsPerBlock := by
  unfold multipleEventCount
  split
  · simp [requiredSlotsPerPrime]
  · have countPositive : 0 < count := by omega
    have numeratorBound :
        count - 1 - firstOffset ≤ count - 1 :=
      Nat.sub_le _ _
    have sameDenominatorBound :
        (count - 1 - firstOffset) / prime ≤
          (count - 1) / prime :=
      Nat.div_le_div_right numeratorBound
    have denominatorBound :
        (count - 1) / prime ≤
          (count - 1) / minimumPrime :=
      Nat.div_le_div_left primeBound minimumPrimePositive
    let q := (count - 1) / minimumPrime
    have quotientBound :
        (count - 1 - firstOffset) / prime ≤ q :=
      sameDenominatorBound.trans denominatorBound
    have remainderBound :
        q % eventsPerBlock < eventsPerBlock :=
      Nat.mod_lt _ (by
        norm_num [eventsPerBlock, threadsPerBlock,
          iterationsPerThread])
    have quotientDecomposition :
        q / eventsPerBlock * eventsPerBlock +
            q % eventsPerBlock = q := by
      simpa [Nat.mul_comm] using Nat.div_add_mod q eventsPerBlock
    simp only [requiredSlotsPerPrime, if_neg (Nat.ne_of_gt countPositive)]
    norm_num [eventsPerBlock, threadsPerBlock,
      iterationsPerThread] at remainderBound quotientDecomposition ⊢
    omega

/-- For a nonempty segment, one fewer block slot fails for the zero-offset
stream at exactly `minimumPrime`.  Thus `requiredSlotsPerPrime` is minimal,
not merely a safe count-dependent upper bound. -/
theorem previousRequiredSlotCount_insufficient
    {count minimumPrime : Nat}
    (countPositive : 0 < count)
    (minimumPrimePositive : 0 < minimumPrime) :
    (requiredSlotsPerPrime count minimumPrime - 1) *
        eventsPerBlock <
      multipleEventCount count 0 minimumPrime := by
  have _minimumPrimeNonzero : minimumPrime ≠ 0 :=
    Nat.ne_of_gt minimumPrimePositive
  let q := (count - 1) / minimumPrime
  have quotientProductBound :
      q / eventsPerBlock * eventsPerBlock ≤ q :=
    Nat.div_mul_le_self q eventsPerBlock
  simp only [requiredSlotsPerPrime, if_neg (Nat.ne_of_gt countPositive),
    multipleEventCount]
  have zeroBelowCount : ¬0 ≥ count := by omega
  simp only [zeroBelowCount, if_false, Nat.sub_zero]
  norm_num [eventsPerBlock, threadsPerBlock,
    iterationsPerThread] at quotientProductBound ⊢
  omega

/-- Every candidate considered here is far inside both CUDA dimension
limits. -/
theorem qualificationGrid_admissible
    {primeCount slots : Nat}
    (primeCountBound : primeCount ≤ multiblockPrimeCount)
    (slotBound : slots ≤ blockSlotsPerPrime) :
    RectangularGridAdmissible primeCount slots := by
  constructor
  · exact le_trans slotBound (by
      norm_num [blockSlotsPerPrime, maximumGridX])
  · exact le_trans primeCountBound (by
      norm_num [multiblockPrimeCount, maximumGridY])

/-- The count-exact width after the production `2·3·5` initializer never
exceeds its independently proved worst-case width 147. -/
theorem residue235_requiredSlots_le_minimumWidth
    {count : Nat} (countBound : count ≤ maximumSegmentRows) :
    requiredSlotsPerPrime count residueSuffixMinimumPrime ≤
      residueMinimumBlockSlotsPerPrime := by
  by_cases countZero : count = 0
  · simp [requiredSlotsPerPrime, countZero]
  · have numeratorBound :
        count - 1 ≤ maximumSegmentRows - 1 :=
      Nat.sub_le_sub_right countBound 1
    have primeQuotientBound :
        (count - 1) / residueSuffixMinimumPrime ≤
          (maximumSegmentRows - 1) / residueSuffixMinimumPrime :=
      Nat.div_le_div_right numeratorBound
    have blockQuotientBound :
        ((count - 1) / residueSuffixMinimumPrime) / eventsPerBlock ≤
          ((maximumSegmentRows - 1) /
              residueSuffixMinimumPrime) / eventsPerBlock :=
      Nat.div_le_div_right primeQuotientBound
    simp only [requiredSlotsPerPrime, countZero, if_false]
    norm_num [maximumSegmentRows, blockSlotsPerPrime,
      residueSuffixMinimumPrime, residueMinimumBlockSlotsPerPrime,
      eventsPerBlock, threadsPerBlock, iterationsPerThread] at blockQuotientBound ⊢
    omega

/-- The count-exact width after the qualification `2·3·5·7` initializer
never exceeds its independently proved worst-case width 94. -/
theorem residue2357_requiredSlots_le_minimumWidth
    {count : Nat} (countBound : count ≤ maximumSegmentRows) :
    requiredSlotsPerPrime count
        MobiusResidue2357.residue2357SuffixMinimumPrime ≤
      MobiusResidue2357.residue2357MinimumBlockSlotsPerPrime := by
  by_cases countZero : count = 0
  · simp [requiredSlotsPerPrime, countZero]
  · have numeratorBound :
        count - 1 ≤ maximumSegmentRows - 1 :=
      Nat.sub_le_sub_right countBound 1
    have primeQuotientBound :
        (count - 1) /
            MobiusResidue2357.residue2357SuffixMinimumPrime ≤
          (maximumSegmentRows - 1) /
            MobiusResidue2357.residue2357SuffixMinimumPrime :=
      Nat.div_le_div_right numeratorBound
    have blockQuotientBound :
        ((count - 1) /
            MobiusResidue2357.residue2357SuffixMinimumPrime) /
              eventsPerBlock ≤
          ((maximumSegmentRows - 1) /
            MobiusResidue2357.residue2357SuffixMinimumPrime) /
              eventsPerBlock :=
      Nat.div_le_div_right primeQuotientBound
    simp only [requiredSlotsPerPrime, countZero, if_false]
    norm_num [maximumSegmentRows, blockSlotsPerPrime,
      MobiusResidue2357.residue2357SuffixMinimumPrime,
      MobiusResidue2357.residue2357MinimumBlockSlotsPerPrime,
      eventsPerBlock, threadsPerBlock, iterationsPerThread] at blockQuotientBound ⊢
    omega

/-- The count-exact width after the qualification `2·3·5·7·11`
initializer never exceeds its independently proved worst-case width 79. -/
theorem residue235711_requiredSlots_le_minimumWidth
    {count : Nat} (countBound : count ≤ maximumSegmentRows) :
    requiredSlotsPerPrime count
        MobiusResidue235711.residue235711SuffixMinimumPrime ≤
      MobiusResidue235711.residue235711MinimumBlockSlotsPerPrime := by
  by_cases countZero : count = 0
  · simp [requiredSlotsPerPrime, countZero]
  · have numeratorBound :
        count - 1 ≤ maximumSegmentRows - 1 :=
      Nat.sub_le_sub_right countBound 1
    have primeQuotientBound :
        (count - 1) /
            MobiusResidue235711.residue235711SuffixMinimumPrime ≤
          (maximumSegmentRows - 1) /
            MobiusResidue235711.residue235711SuffixMinimumPrime :=
      Nat.div_le_div_right numeratorBound
    have blockQuotientBound :
        ((count - 1) /
            MobiusResidue235711.residue235711SuffixMinimumPrime) /
              eventsPerBlock ≤
          ((maximumSegmentRows - 1) /
            MobiusResidue235711.residue235711SuffixMinimumPrime) /
              eventsPerBlock :=
      Nat.div_le_div_right primeQuotientBound
    simp only [requiredSlotsPerPrime, countZero, if_false]
    norm_num [maximumSegmentRows, blockSlotsPerPrime,
      MobiusResidue235711.residue235711SuffixMinimumPrime,
      MobiusResidue235711.residue235711MinimumBlockSlotsPerPrime,
      eventsPerBlock, threadsPerBlock, iterationsPerThread] at blockQuotientBound ⊢
    omega

/-- Exact-width schedule after the production `2·3·5` initializer. -/
theorem residue235RectangularEvent_complete_duplicateFree
    {primeCount primeIndex count firstOffset prime event : Nat}
    (primeIndexInRange : primeIndex < primeCount)
    (countBound : count ≤ maximumSegmentRows)
    (primeBound : residueSuffixMinimumPrime ≤ prime)
    (eventInRange :
      event < multipleEventCount count firstOffset prime) :
    ∃! coordinate,
      VisitsRectangularEvent
        primeCount residueMinimumBlockSlotsPerPrime
        primeIndex event coordinate := by
  apply rectangularEvent_complete_duplicateFree primeIndexInRange
  exact lt_of_lt_of_le eventInRange
    (residueMultipleEventCount_le_minimumCapacity
      countBound primeBound)

/-- Exact-width schedule after the qualification `2·3·5·7` initializer. -/
theorem residue2357RectangularEvent_complete_duplicateFree
    {primeCount primeIndex count firstOffset prime event : Nat}
    (primeIndexInRange : primeIndex < primeCount)
    (countBound : count ≤ maximumSegmentRows)
    (primeBound :
      MobiusResidue2357.residue2357SuffixMinimumPrime ≤ prime)
    (eventInRange :
      event < multipleEventCount count firstOffset prime) :
    ∃! coordinate,
      VisitsRectangularEvent
        primeCount
        MobiusResidue2357.residue2357MinimumBlockSlotsPerPrime
        primeIndex event coordinate := by
  apply rectangularEvent_complete_duplicateFree primeIndexInRange
  exact lt_of_lt_of_le eventInRange
    (MobiusResidue2357.residue2357MultipleEventCount_le_minimumCapacity
      countBound primeBound)

/-- Exact-width schedule after the qualification `2·3·5·7·11`
initializer. -/
theorem residue235711RectangularEvent_complete_duplicateFree
    {primeCount primeIndex count firstOffset prime event : Nat}
    (primeIndexInRange : primeIndex < primeCount)
    (countBound : count ≤ maximumSegmentRows)
    (primeBound :
      MobiusResidue235711.residue235711SuffixMinimumPrime ≤ prime)
    (eventInRange :
      event < multipleEventCount count firstOffset prime) :
    ∃! coordinate,
      VisitsRectangularEvent
        primeCount
        MobiusResidue235711.residue235711MinimumBlockSlotsPerPrime
        primeIndex event coordinate := by
  apply rectangularEvent_complete_duplicateFree primeIndexInRange
  exact lt_of_lt_of_le eventInRange
    (MobiusResidue235711.residue235711MultipleEventCount_le_minimumCapacity
      countBound primeBound)

#print axioms multiblockEventWithSlots_complete_duplicateFree
#print axioms rectangularEvent_complete_duplicateFree
#print axioms multipleEventCount_le_requiredSlotsCapacity
#print axioms previousRequiredSlotCount_insufficient
#print axioms qualificationGrid_admissible
#print axioms residue235_requiredSlots_le_minimumWidth
#print axioms residue2357_requiredSlots_le_minimumWidth
#print axioms residue235711_requiredSlots_le_minimumWidth
#print axioms residue235RectangularEvent_complete_duplicateFree
#print axioms residue2357RectangularEvent_complete_duplicateFree
#print axioms residue235711RectangularEvent_complete_duplicateFree

end SparkInterval.TernaryGoldbach.MobiusRectangularCUDASchedule
