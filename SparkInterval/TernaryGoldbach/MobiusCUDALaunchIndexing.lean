/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusDenseSchedule

/-!
# CUDA launch indexing for the production split-square Möbius pass

This file models the finite launch arithmetic used by
`launch_tg_mobius_fused_support_multiblock_dense_residue_235_split_square`.
The production path uses 256 threads per block and the following formulas.

* Row initialization and finalization use
  `index = blockIdx.x * 256 + threadIdx.x` with
  `1 + (count - 1) / 256` blocks.
* A one-block dense prime stream uses the event ordinal
  `event = iteration * 256 + threadIdx.x`.  Its row offset is then
  `firstOffset + event * p` for the distinct-divisor pass and
  `firstSquareOffset + event * p^2` for the square pass.
* The 512-slot multiblock prefix decodes
  `primeIndex = blockIdx.x / 512` and
  `blockOrdinal = blockIdx.x % 512`; its event ordinal is
  `blockOrdinal * 1_048_576 + iteration * 256 + threadIdx.x`.
* A sparse-prime launch uses
  `primeIndex = firstPrimeIndex + blockIdx.x * 256 + threadIdx.x`.
  That one thread enumerates the selected prime's event ordinals serially.

The host rejects a launch whose computed grid exceeds `0x7fffffff`.  It also
requires a positive row count no larger than `maximumSegmentRows`; later
prime suffixes use the zero-aware ceil-division formula modeled below.

The theorems prove the architecture-independent integer fact required by all
of those launches: every admitted finite row or prime index has exactly one
block/thread owner, and every event ordinal has exactly one thread/iteration
owner.  They do not identify CUDA registers or compiled control flow with
these definitions.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing

open SparkInterval.TernaryGoldbach.MobiusDenseSchedule

/-- Largest one-dimensional grid accepted by the native host wrapper. -/
def maximumGridX : Nat := 0x7fffffff

/-- Exact zero-aware ceil-division used for sparse-prime launches.  On the
positive row path this reduces to the source expression
`1 + (itemCount - 1) / 256`. -/
def blocksFor (itemCount : Nat) : Nat :=
  if itemCount = 0 then 0
  else 1 + (itemCount - 1) / threadsPerBlock

/-- A physical coordinate in a one-dimensional CUDA launch. -/
structure ThreadCoordinate where
  block : Nat
  thread : Nat
deriving DecidableEq, Repr

/-- CUDA's one-dimensional global thread index. -/
def ThreadCoordinate.globalIndex
    (coordinate : ThreadCoordinate) : Nat :=
  coordinate.block * threadsPerBlock + coordinate.thread

/-- Canonical block/thread owner of one finite item index. -/
def ownerCoordinate (index : Nat) : ThreadCoordinate where
  block := index / threadsPerBlock
  thread := index % threadsPerBlock

/-- A launched thread is the active owner of `index`.  Threads in the rounded
last block whose global index is outside the item range are deliberately not
active: the CUDA kernels return at their range guard. -/
def OwnsIndex
    (itemCount index : Nat) (coordinate : ThreadCoordinate) : Prop :=
  coordinate.block < blocksFor itemCount ∧
    coordinate.thread < threadsPerBlock ∧
    coordinate.globalIndex = index

theorem blocksFor_eq_positiveFormula
    {itemCount : Nat} (positive : 0 < itemCount) :
    blocksFor itemCount =
      1 + (itemCount - 1) / threadsPerBlock := by
  rw [blocksFor, if_neg (Nat.ne_of_gt positive)]

@[simp] theorem ownerCoordinate_globalIndex (index : Nat) :
    (ownerCoordinate index).globalIndex = index := by
  simpa [ownerCoordinate, ThreadCoordinate.globalIndex, Nat.mul_comm] using
    Nat.div_add_mod index threadsPerBlock

theorem ownerCoordinate_thread_lt (index : Nat) :
    (ownerCoordinate index).thread < threadsPerBlock := by
  exact Nat.mod_lt _ (by norm_num [threadsPerBlock])

theorem ownerCoordinate_block_lt
    {itemCount index : Nat} (inRange : index < itemCount) :
    (ownerCoordinate index).block < blocksFor itemCount := by
  have positive : 0 < itemCount := lt_of_le_of_lt (Nat.zero_le index) inRange
  have indexLe : index ≤ itemCount - 1 := by omega
  rw [blocksFor_eq_positiveFormula positive]
  exact lt_of_le_of_lt
    (Nat.div_le_div_right indexLe)
    (by omega)

/-- Bounded thread coordinates are recovered uniquely from their global
index.  No block bound is needed for this arithmetic injectivity result. -/
theorem globalIndex_injective
    {first second : ThreadCoordinate}
    (firstThread : first.thread < threadsPerBlock)
    (secondThread : second.thread < threadsPerBlock)
    (sameIndex : first.globalIndex = second.globalIndex) :
    first = second := by
  have threadEq : first.thread = second.thread := by
    have reduced :=
      congrArg (fun value => value % threadsPerBlock) sameIndex
    simpa [ThreadCoordinate.globalIndex, Nat.add_mod, Nat.mul_mod,
      Nat.mod_eq_of_lt firstThread, Nat.mod_eq_of_lt secondThread] using
      reduced
  have blockProducts :
      first.block * threadsPerBlock =
        second.block * threadsPerBlock := by
    rw [ThreadCoordinate.globalIndex, threadEq] at sameIndex
    exact Nat.add_right_cancel sameIndex
  have blockEq : first.block = second.block :=
    Nat.mul_right_cancel
      (by norm_num [threadsPerBlock]) blockProducts
  cases first
  cases second
  simp_all

/-- Exact completeness and duplicate-freedom theorem for an active finite
one-dimensional launch. -/
theorem existsUnique_ownerCoordinate
    {itemCount index : Nat} (inRange : index < itemCount) :
    ∃! coordinate, OwnsIndex itemCount index coordinate := by
  refine ⟨ownerCoordinate index, ?_, ?_⟩
  · exact ⟨ownerCoordinate_block_lt inRange,
      ownerCoordinate_thread_lt index, ownerCoordinate_globalIndex index⟩
  · intro coordinate owns
    exact globalIndex_injective owns.2.1
      (ownerCoordinate_thread_lt index)
      (owns.2.2.trans (ownerCoordinate_globalIndex index).symm)

/-- The public row cap implies the explicit native grid-x guard. -/
theorem rowGrid_fits
    {count : Nat}
    (positive : 0 < count)
    (countBound : count ≤ maximumSegmentRows) :
    blocksFor count ≤ maximumGridX := by
  have quotientBound :
      (count - 1) / threadsPerBlock ≤ count - 1 :=
    Nat.div_le_self _ _
  rw [blocksFor_eq_positiveFormula positive]
  have maximumRowsValue : maximumSegmentRows = 1_073_741_824 :=
    maximumSegmentRows_eq
  norm_num [maximumGridX] at maximumRowsValue ⊢
  omega

/-- Row initialization/finalization has one and only one active CUDA thread
for every row admitted by the positive public-count host guard. -/
theorem rowLaunch_complete_duplicateFree
    {count index : Nat}
    (positive : 0 < count)
    (countBound : count ≤ maximumSegmentRows)
    (inRange : index < count) :
    blocksFor count ≤ maximumGridX ∧
      ∃! coordinate, OwnsIndex count index coordinate := by
  exact ⟨rowGrid_fits positive countBound,
    existsUnique_ownerCoordinate inRange⟩

/-- Prime roster index selected by a sparse-launch thread. -/
def sparsePrimeIndex
    (firstPrimeIndex : Nat) (coordinate : ThreadCoordinate) : Nat :=
  firstPrimeIndex + coordinate.globalIndex

/-- A sparse launch coordinate is the active owner of one suffix-prime
index.  `totalPrimeCount - firstPrimeIndex` is the exact host item count. -/
def OwnsSparsePrime
    (firstPrimeIndex totalPrimeCount primeIndex : Nat)
    (coordinate : ThreadCoordinate) : Prop :=
  OwnsIndex (totalPrimeCount - firstPrimeIndex)
      (primeIndex - firstPrimeIndex) coordinate ∧
    sparsePrimeIndex firstPrimeIndex coordinate = primeIndex

/-- Every index in a guarded suffix has one and only one sparse-launch
thread.  This applies both to the distinct-divisor sparse suffix and to the
separately partitioned square-prime sparse suffix. -/
theorem sparsePrimeLaunch_complete_duplicateFree
    {firstPrimeIndex totalPrimeCount primeIndex : Nat}
    (firstLeTotal : firstPrimeIndex ≤ totalPrimeCount)
    (firstLeIndex : firstPrimeIndex ≤ primeIndex)
    (indexLtTotal : primeIndex < totalPrimeCount)
    (gridBound :
      blocksFor (totalPrimeCount - firstPrimeIndex) ≤ maximumGridX) :
    firstPrimeIndex ≤ totalPrimeCount ∧
      blocksFor (totalPrimeCount - firstPrimeIndex) ≤ maximumGridX ∧
      ∃! coordinate,
        OwnsSparsePrime firstPrimeIndex totalPrimeCount primeIndex
          coordinate := by
  have localInRange :
      primeIndex - firstPrimeIndex <
        totalPrimeCount - firstPrimeIndex :=
    (Nat.sub_lt_sub_iff_right firstLeIndex).2 indexLtTotal
  rcases existsUnique_ownerCoordinate localInRange with
    ⟨owner, ownerFacts, ownerUnique⟩
  refine ⟨firstLeTotal, gridBound, owner, ⟨ownerFacts, ?_⟩, ?_⟩
  · simp only [sparsePrimeIndex]
    rw [ownerFacts.2.2]
    omega
  · intro coordinate coordinateFacts
    exact ownerUnique coordinate coordinateFacts.1

/-- One coordinate in a single-block grid-stride prime-event loop. -/
structure GridStrideCoordinate where
  thread : Nat
  iteration : Nat
deriving DecidableEq, Repr

/-- Exact event ordinal `iteration * 256 + threadIdx.x`. -/
def GridStrideCoordinate.event
    (coordinate : GridStrideCoordinate) : Nat :=
  coordinate.iteration * threadsPerBlock + coordinate.thread

/-- Canonical owner of a prime-event ordinal. -/
def gridStrideOwner (event : Nat) : GridStrideCoordinate where
  thread := event % threadsPerBlock
  iteration := event / threadsPerBlock

/-- A one-block prime-event coordinate visits an ordinal exactly when its
thread is in the physical block and its grid-stride formula equals it. -/
def VisitsEvent
    (event : Nat) (coordinate : GridStrideCoordinate) : Prop :=
  coordinate.thread < threadsPerBlock ∧ coordinate.event = event

@[simp] theorem gridStrideOwner_event (event : Nat) :
    (gridStrideOwner event).event = event := by
  simpa [gridStrideOwner, GridStrideCoordinate.event, Nat.mul_comm] using
    Nat.div_add_mod event threadsPerBlock

/-- A one-block dense divisor or square stream enumerates every finite event
ordinal exactly once.  The loop's `event < eventEnd` guard selects the finite
prefix required by a particular prime. -/
theorem eventGridStride_complete_duplicateFree (event : Nat) :
    ∃! coordinate, VisitsEvent event coordinate := by
  refine ⟨gridStrideOwner event,
    ⟨Nat.mod_lt _ (by norm_num [threadsPerBlock]),
      gridStrideOwner_event event⟩, ?_⟩
  intro coordinate coordinateFacts
  have asThreadCoordinate :
      ThreadCoordinate.mk coordinate.iteration coordinate.thread =
        ThreadCoordinate.mk
          (gridStrideOwner event).iteration
          (gridStrideOwner event).thread := by
    apply globalIndex_injective
      coordinateFacts.1
      (Nat.mod_lt _ (by norm_num [threadsPerBlock]))
    simpa [ThreadCoordinate.globalIndex,
      GridStrideCoordinate.event] using
      coordinateFacts.2.trans (gridStrideOwner_event event).symm
  cases coordinate
  simp_all

/-! ## Complete multiblock event coordinates -/

/-- Physical slot/thread/iteration coordinate in one dense-prime rectangle. -/
structure MultiblockEventCoordinate where
  slot : Nat
  thread : Nat
  iteration : Nat
deriving DecidableEq, Repr

/-- Exact multiblock event expression evaluated by the dense CUDA loop. -/
def MultiblockEventCoordinate.event
    (coordinate : MultiblockEventCoordinate) : Nat :=
  coordinate.slot * eventsPerBlock +
    (coordinate.iteration * threadsPerBlock + coordinate.thread)

/-- Canonical slot, thread, and loop iteration for one event ordinal. -/
def multiblockEventOwner (event : Nat) :
    MultiblockEventCoordinate where
  slot := eventOwner event
  thread := threadOwner (eventLocal event)
  iteration := iterationOwner (eventLocal event)

/-- Active-coordinate predicate for the production 512-slot rectangle. -/
def VisitsMultiblockEvent
    (event : Nat) (coordinate : MultiblockEventCoordinate) : Prop :=
  coordinate.slot < blockSlotsPerPrime ∧
    coordinate.thread < threadsPerBlock ∧
    coordinate.iteration < iterationsPerThread ∧
    coordinate.event = event

@[simp] theorem multiblockEventOwner_event (event : Nat) :
    (multiblockEventOwner event).event = event := by
  change eventOwner event * eventsPerBlock +
      (iterationOwner (eventLocal event) * threadsPerBlock +
        threadOwner (eventLocal event)) = event
  simpa only [eventBegin] using event_block_thread_decode event

/-- Every event below the exact 512-slot capacity has one and only one
slot/thread/iteration owner.  This joins the flat-block and inner-loop
arguments into the literal multiblock kernel coordinate. -/
theorem multiblockEvent_complete_duplicateFree
    {event : Nat}
    (inCapacity : event < blockSlotsPerPrime * eventsPerBlock) :
    ∃! coordinate, VisitsMultiblockEvent event coordinate := by
  have ownerSlot :
      (multiblockEventOwner event).slot < blockSlotsPerPrime := by
    exact eventOwner_lt_slots (le_refl _) inCapacity
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

/-- The dense multiblock launch's flat block formula reconstructs every
prime-slot pair. -/
theorem denseFlatBlock_encode_decode
    {primeCount prime slot : Nat}
    (primeInRange : prime < primeCount)
    (slotInRange : slot < blockSlotsPerPrime) :
    let flatBlock := prime * blockSlotsPerPrime + slot
    flatBlock < primeCount * blockSlotsPerPrime ∧
      primeIndex flatBlock = prime ∧
      blockOrdinal flatBlock = slot := by
  dsimp
  constructor
  · nlinarith
  constructor
  · have formula := Nat.add_mul_div_left slot prime
      (show 0 < blockSlotsPerPrime by norm_num [blockSlotsPerPrime])
    rw [Nat.div_eq_of_lt slotInRange] at formula
    simpa [primeIndex, Nat.add_comm, Nat.mul_comm] using formula
  · simpa [blockOrdinal, Nat.add_mod,
      Nat.mod_eq_of_lt slotInRange, blockSlotsPerPrime]

/-- Distinct in-range `(prime, slot)` pairs cannot name the same flat block
in the production 512-slot dense grid. -/
theorem denseFlatBlock_encode_injective
    {firstPrime firstSlot secondPrime secondSlot : Nat}
    (firstSlotInRange : firstSlot < blockSlotsPerPrime)
    (secondSlotInRange : secondSlot < blockSlotsPerPrime)
    (sameFlatBlock :
      firstPrime * blockSlotsPerPrime + firstSlot =
        secondPrime * blockSlotsPerPrime + secondSlot) :
    firstPrime = secondPrime ∧ firstSlot = secondSlot := by
  have decode (prime slot : Nat)
      (slotInRange : slot < blockSlotsPerPrime) :
      (prime * blockSlotsPerPrime + slot) / blockSlotsPerPrime =
        prime := by
    have formula := Nat.add_mul_div_left slot prime
      (show 0 < blockSlotsPerPrime by norm_num [blockSlotsPerPrime])
    rw [Nat.div_eq_of_lt slotInRange] at formula
    simpa [Nat.add_comm, Nat.mul_comm] using formula
  have primeEq : firstPrime = secondPrime := by
    calc
      firstPrime =
          (firstPrime * blockSlotsPerPrime + firstSlot) /
            blockSlotsPerPrime :=
        (decode firstPrime firstSlot firstSlotInRange).symm
      _ =
          (secondPrime * blockSlotsPerPrime + secondSlot) /
            blockSlotsPerPrime := by rw [sameFlatBlock]
      _ = secondPrime :=
        decode secondPrime secondSlot secondSlotInRange
  refine ⟨primeEq, ?_⟩
  rw [primeEq] at sameFlatBlock
  exact Nat.add_left_cancel sameFlatBlock

#print axioms existsUnique_ownerCoordinate
#print axioms rowLaunch_complete_duplicateFree
#print axioms sparsePrimeLaunch_complete_duplicateFree
#print axioms eventGridStride_complete_duplicateFree
#print axioms multiblockEvent_complete_duplicateFree
#print axioms denseFlatBlock_encode_decode
#print axioms denseFlatBlock_encode_injective

end SparkInterval.TernaryGoldbach.MobiusCUDALaunchIndexing
