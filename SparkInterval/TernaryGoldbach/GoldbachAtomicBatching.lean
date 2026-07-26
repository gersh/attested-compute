/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachAtomicClears

/-!
# Exact packed-word batching for the Goldbach atomic tail

The expensive Goldbach tail kernel emits many idempotent bit-clear events.
A qualification-only CUDA candidate may collect events that address the same
packed word, AND their masks together in shared memory, and issue one global
`atomicAnd` for the collected entry.  Events that cannot be inserted in the
bounded table take the unchanged global-atomic fallback.

This file proves the source-independent equation needed by that candidate:

* one combined clear mask has exactly the semantics of its list of individual
  clears;
* applying a list of keyed mask entries has exactly the semantics of expanding
  every entry back into individual addressed events; and
* the entries followed by the fallback are equivalent to an arbitrary
  original event order whenever their expansion is a permutation of that
  original stream.

Consequently, a CUDA qualifier may establish either an exact
coverage/permutation certificate for a ghost event trace or exact membership
equivalence for the idempotent physical clear set.  A dropped distinct event,
a wrong word key, or a wrong bit cannot satisfy either premise.  Repeating an
already present identical clear is harmless and is intentionally accepted by
the membership-equivalence theorem.

The physical boundary remains explicit.  This theorem does not establish
CUDA/PTX/SASS refinement, shared-table synchronization, or linearizability of
the physical 64-bit `atomicAnd`.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.GoldbachAtomicBatching

open GoldbachAtomicClears

/-- Logical state of the unbounded packed-word array. -/
abbrev PackedState := Nat → Word

/-- One source-level tail event, before any same-word batching. -/
structure AddressedClear where
  wordIndex : Nat
  bit : Fin 64
deriving DecidableEq, Repr

/-- One linearizable clear at its exact packed-word address. -/
def atomicClearAddressed
    (state : PackedState) (event : AddressedClear) : PackedState :=
  fun wordIndex =>
    if wordIndex = event.wordIndex then
      atomicClear (state wordIndex) event.bit
    else
      state wordIndex

/-- Sequential semantics of one physical linearization of addressed clears. -/
def runAddressed : PackedState → List AddressedClear → PackedState
  | state, [] => state
  | state, event :: rest =>
      runAddressed (atomicClearAddressed state event) rest

/-- Exact bit-level result of any addressed-clear serialization. -/
theorem runAddressed_apply
    (state : PackedState) (events : List AddressedClear)
    (wordIndex : Nat) (bit : Fin 64) :
    runAddressed state events wordIndex bit =
      if { wordIndex := wordIndex, bit := bit } ∈ events then
        false
      else
        state wordIndex bit := by
  induction events generalizing state with
  | nil => simp [runAddressed]
  | cons event rest ih =>
      simp only [runAddressed, ih, List.mem_cons]
      by_cases hsame :
          ({ wordIndex := wordIndex, bit := bit } : AddressedClear) = event
      · cases hsame
        simp [atomicClearAddressed, atomicClear]
      · have hnotBoth :
          ¬(wordIndex = event.wordIndex ∧ bit = event.bit) := by
          intro h
          apply hsame
          cases event
          simp_all
        by_cases hword : wordIndex = event.wordIndex
        · subst wordIndex
          have hbit : bit ≠ event.bit := by
            intro h
            exact hnotBoth ⟨rfl, h⟩
          have hsame' :
              ({ wordIndex := event.wordIndex, bit := bit } :
                AddressedClear) ≠ event := by
            intro h
            exact hbit (congrArg AddressedClear.bit h)
          simp [hsame', atomicClearAddressed, atomicClear, hbit]
        · simp [hsame, atomicClearAddressed, hword]

/-- The final packed state is independent of the physical serialization
order. -/
theorem runAddressed_eq_of_perm
    (state : PackedState) {first second : List AddressedClear}
    (hperm : first.Perm second) :
    runAddressed state first = runAddressed state second := by
  funext wordIndex bit
  rw [runAddressed_apply, runAddressed_apply]
  have hmem :
      ({ wordIndex := wordIndex, bit := bit } : AddressedClear) ∈ first ↔
        { wordIndex := wordIndex, bit := bit } ∈ second :=
    hperm.mem_iff
  by_cases hfirst :
      ({ wordIndex := wordIndex, bit := bit } : AddressedClear) ∈ first
  · simp [hfirst, hmem.mp hfirst]
  · have hsecond :
        ({ wordIndex := wordIndex, bit := bit } : AddressedClear) ∉ second := by
      intro h
      exact hfirst (hmem.mpr h)
    simp [hfirst, hsecond]

/-- Idempotent clears need only the same addressed-event membership set.
Unlike `runAddressed_eq_of_perm`, this theorem deliberately forgets duplicate
multiplicity and therefore matches what can be recovered from a final
physical AND mask. -/
theorem runAddressed_eq_of_mem_iff
    (state : PackedState) {first second : List AddressedClear}
    (hmem : ∀ event, event ∈ first ↔ event ∈ second) :
    runAddressed state first = runAddressed state second := by
  funext wordIndex bit
  rw [runAddressed_apply, runAddressed_apply]
  exact if_congr
    (hmem { wordIndex := wordIndex, bit := bit }) rfl rfl

/-- Running two event streams in succession is the same as running their
concatenation. -/
theorem runAddressed_append
    (state : PackedState) (first second : List AddressedClear) :
    runAddressed state (first ++ second) =
      runAddressed (runAddressed state first) second := by
  induction first generalizing state with
  | nil => rfl
  | cons event rest ih =>
      simp only [List.cons_append, runAddressed]
      exact ih (atomicClearAddressed state event)

/-- Bitwise mask emitted by one occupied same-word table entry. -/
def clearMask (bits : List (Fin 64)) : Word :=
  fun bit => decide (bit ∉ bits)

/-- Logical 64-bit AND with a combined table-entry mask. -/
def applyClearMask (word : Word) (bits : List (Fin 64)) : Word :=
  fun bit => word bit && clearMask bits bit

/-- Combining same-word clear bits into one AND mask is exact. -/
theorem applyClearMask_eq_runClears
    (word : Word) (bits : List (Fin 64)) :
    applyClearMask word bits = runClears word bits := by
  funext bit
  rw [runClears_apply]
  by_cases hmem : bit ∈ bits
  · simp [applyClearMask, clearMask, hmem]
  · simp [applyClearMask, clearMask, hmem]

/-- One occupied bounded-table entry: its key is the packed-word index and
its value is the complete list of bits accumulated under that key. -/
structure PackedBatch where
  wordIndex : Nat
  bits : List (Fin 64)
deriving DecidableEq, Repr

/-- Expand a table entry back to the individual events whose masks it
combines. -/
def expandBatch (batch : PackedBatch) : List AddressedClear :=
  batch.bits.map fun bit =>
    { wordIndex := batch.wordIndex, bit := bit }

/-- Apply one occupied table entry as one logical combined mask. -/
def applyPackedBatch
    (state : PackedState) (batch : PackedBatch) : PackedState :=
  fun wordIndex =>
    if wordIndex = batch.wordIndex then
      applyClearMask (state wordIndex) batch.bits
    else
      state wordIndex

/-- A keyed combined mask is exactly its expanded individual clear stream. -/
theorem applyPackedBatch_eq_runAddressed_expand
    (state : PackedState) (batch : PackedBatch) :
    applyPackedBatch state batch =
      runAddressed state (expandBatch batch) := by
  funext wordIndex bit
  rw [runAddressed_apply]
  by_cases hword : wordIndex = batch.wordIndex
  · subst wordIndex
    by_cases hbit : bit ∈ batch.bits
    · have hevent :
          ({ wordIndex := batch.wordIndex, bit := bit } : AddressedClear) ∈
            expandBatch batch := by
        simp [expandBatch, hbit]
      rw [if_pos hevent]
      simp [applyPackedBatch, applyClearMask, clearMask, hbit]
    · have hevent :
          ({ wordIndex := batch.wordIndex, bit := bit } : AddressedClear) ∉
            expandBatch batch := by
        simp [expandBatch, hbit]
      rw [if_neg hevent]
      simp [applyPackedBatch, applyClearMask, clearMask, hbit]
  · have hevent :
        ({ wordIndex := wordIndex, bit := bit } : AddressedClear) ∉
          expandBatch batch := by
      intro hmem
      simp only [expandBatch, List.mem_map] at hmem
      rcases hmem with ⟨mappedBit, _, heq⟩
      apply hword
      exact (congrArg AddressedClear.wordIndex heq).symm
    rw [if_neg hevent]
    simp [applyPackedBatch, hword]

/-- Sequential application of every occupied table entry. -/
def runBatches : PackedState → List PackedBatch → PackedState
  | state, [] => state
  | state, batch :: rest =>
      runBatches (applyPackedBatch state batch) rest

/-- Expanded event stream represented by all occupied table entries. -/
def expandBatches (batches : List PackedBatch) : List AddressedClear :=
  batches.flatMap expandBatch

/-- Every list of combined table entries is exactly its full expansion. -/
theorem runBatches_eq_runAddressed_expand
    (state : PackedState) (batches : List PackedBatch) :
    runBatches state batches =
      runAddressed state (expandBatches batches) := by
  induction batches generalizing state with
  | nil => rfl
  | cons batch rest ih =>
      simp only [runBatches, expandBatches, List.flatMap_cons,
        runAddressed_append]
      rw [← applyPackedBatch_eq_runAddressed_expand]
      exact ih (applyPackedBatch state batch)

/-- Main qualification equation.  The occupied entries plus every fallback
event may be serialized differently from the original CUDA stream, but they
produce the identical packed state whenever the qualifier supplies the exact
coverage/permutation premise. -/
theorem partitioned_batch_schedule_eq
    (initial : PackedState)
    (original fallback : List AddressedClear)
    (batches : List PackedBatch)
    (hcoverage :
      original.Perm (expandBatches batches ++ fallback)) :
    runAddressed initial original =
      runAddressed (runBatches initial batches) fallback := by
  rw [runAddressed_eq_of_perm initial hcoverage, runAddressed_append,
    runBatches_eq_runAddressed_expand]

/-- Idempotence-aware qualification equation for a physical mask decoder.
The decoded occupied entries and fallback need only contain exactly the same
addressed clears as the original stream; duplicate equal events need not be
recoverable from the mask. -/
theorem partitioned_batch_schedule_eq_of_mem_iff
    (initial : PackedState)
    (original fallback : List AddressedClear)
    (batches : List PackedBatch)
    (hcoverage :
      ∀ event,
        event ∈ original ↔
          event ∈ expandBatches batches ++ fallback) :
    runAddressed initial original =
      runAddressed (runBatches initial batches) fallback := by
  rw [runAddressed_eq_of_mem_iff initial hcoverage, runAddressed_append,
    runBatches_eq_runAddressed_expand]

/-! ## Verified bounded-table algorithm

The following pure algorithm captures the semantic choices of an
open-addressed shared table.  It merges an event into an existing keyed entry
when possible, allocates a new singleton entry while capacity remains, and
otherwise records the event in the fallback.  Hashing and probe order do not
occur in the mathematical result: a physical implementation refines this
algorithm by proving that an exhaustive probe either finds the same key or an
empty slot, and that the exhausted-table branch emits the fallback exactly
once.
-/

/-- Merge one event into the first existing entry with the same packed-word
key.  `none` means that the table has no such key. -/
def insertIntoBatches
    (event : AddressedClear) :
    List PackedBatch → Option (List PackedBatch)
  | [] => none
  | batch :: rest =>
      if event.wordIndex = batch.wordIndex then
        some
          ({ wordIndex := event.wordIndex,
             bits := event.bit :: batch.bits } :: rest)
      else
        match insertIntoBatches event rest with
        | none => none
        | some updated => some (batch :: updated)

/-- A successful same-key insertion represents precisely the new event plus
the previous table contents. -/
theorem insertIntoBatches_sound
    {event : AddressedClear} {before after : List PackedBatch}
    (hinsert : insertIntoBatches event before = some after) :
    (expandBatches after).Perm
      (event :: expandBatches before) := by
  induction before generalizing after with
  | nil => simp [insertIntoBatches] at hinsert
  | cons batch rest ih =>
      simp only [insertIntoBatches] at hinsert
      by_cases hkey : event.wordIndex = batch.wordIndex
      · rw [if_pos hkey] at hinsert
        simp only [Option.some.injEq] at hinsert
        subst after
        have hevent :
            ({ wordIndex := batch.wordIndex, bit := event.bit } :
              AddressedClear) = event := by
          cases event
          simp_all
        simp only [expandBatches, List.flatMap_cons, expandBatch,
          List.map_cons]
        rw [hkey, hevent]
        exact .refl _
      · rw [if_neg hkey] at hinsert
        split at hinsert
        · simp at hinsert
        · rename_i updated hupdated
          simp only [Option.some.injEq] at hinsert
          subst after
          have hrest := ih hupdated
          simp only [expandBatches, List.flatMap_cons]
          exact
            (hrest.append_left (expandBatch batch)).trans
              List.perm_middle

/-- A successful same-key insertion does not allocate a new table entry. -/
theorem insertIntoBatches_length
    {event : AddressedClear} {before after : List PackedBatch}
    (hinsert : insertIntoBatches event before = some after) :
    after.length = before.length := by
  induction before generalizing after with
  | nil => simp [insertIntoBatches] at hinsert
  | cons batch rest ih =>
      simp only [insertIntoBatches] at hinsert
      split at hinsert
      · simp only [Option.some.injEq] at hinsert
        subst after
        simp
      · split at hinsert
        · simp at hinsert
        · rename_i updated hupdated
          simp only [Option.some.injEq] at hinsert
          subst after
          simp [ih hupdated]

/-- Complete abstract state of one bounded table epoch. -/
structure BatchAccumulator where
  batches : List PackedBatch
  fallback : List AddressedClear
deriving DecidableEq, Repr

/-- All individual events represented by the occupied entries and fallback. -/
def BatchAccumulator.represented
    (state : BatchAccumulator) : List AddressedClear :=
  expandBatches state.batches ++ state.fallback

/-- Insert one event into a bounded semantic table. -/
def insertBatched
    (capacity : Nat) (state : BatchAccumulator)
    (event : AddressedClear) : BatchAccumulator :=
  match insertIntoBatches event state.batches with
  | some updated =>
      { batches := updated, fallback := state.fallback }
  | none =>
      if state.batches.length < capacity then
        { batches :=
            { wordIndex := event.wordIndex, bits := [event.bit] } ::
              state.batches,
          fallback := state.fallback }
      else
        { batches := state.batches,
          fallback := event :: state.fallback }

/-- Every insertion contributes exactly one event to either an occupied entry
or the fallback; no drop or duplicate branch exists. -/
theorem insertBatched_sound
    (capacity : Nat) (state : BatchAccumulator)
    (event : AddressedClear) :
    (insertBatched capacity state event).represented.Perm
      (event :: state.represented) := by
  simp only [insertBatched]
  split
  · rename_i updated hinsert
    exact
      (insertIntoBatches_sound hinsert).append_right state.fallback
  · rename_i hnone
    split
    · simp [BatchAccumulator.represented, expandBatches, expandBatch]
    · simp only [BatchAccumulator.represented]
      exact List.perm_middle

/-- One insertion preserves the declared table-capacity invariant. -/
theorem insertBatched_capacity
    {capacity : Nat} {state : BatchAccumulator}
    (hcapacity : state.batches.length ≤ capacity)
    (event : AddressedClear) :
    (insertBatched capacity state event).batches.length ≤ capacity := by
  simp only [insertBatched]
  split
  · rename_i updated hinsert
    rw [insertIntoBatches_length hinsert]
    exact hcapacity
  · split
    · simp_all
    · exact hcapacity

/-- Process a complete table epoch. -/
def batchStream
    (capacity : Nat) :
    BatchAccumulator → List AddressedClear → BatchAccumulator
  | state, [] => state
  | state, event :: rest =>
      batchStream capacity (insertBatched capacity state event) rest

/-- The epoch result represents the reverse input stream followed by every
event represented by the initial state.  The reversal is only a convenient
induction order and is erased by permutation invariance. -/
theorem batchStream_sound
    (capacity : Nat) (state : BatchAccumulator)
    (events : List AddressedClear) :
    (batchStream capacity state events).represented.Perm
      (events.reverse ++ state.represented) := by
  induction events generalizing state with
  | nil => simp [batchStream]
  | cons event rest ih =>
      simpa [batchStream, List.reverse_cons, List.append_assoc] using
        (ih (insertBatched capacity state event)).trans
          ((insertBatched_sound capacity state event).append_left rest.reverse)

/-- A complete epoch begun with an empty table and fallback has exact
once-only coverage of its input events. -/
theorem batchStream_empty_coverage
    (capacity : Nat) (events : List AddressedClear) :
    events.Perm
      (batchStream capacity
        { batches := [], fallback := [] } events).represented := by
  have hsound :=
    batchStream_sound capacity
      ({ batches := [], fallback := [] } : BatchAccumulator) events
  have hsound' :
      (batchStream capacity
        { batches := [], fallback := [] } events).represented.Perm
          (events.reverse) := by
    simpa only [BatchAccumulator.represented, expandBatches,
      List.flatMap_nil, List.append_nil] using hsound
  exact (List.reverse_perm events).symm.trans hsound'.symm

/-- The verified bounded-table algorithm supplies the coverage premise of
`partitioned_batch_schedule_eq` itself. -/
theorem bounded_batch_schedule_eq
    (initial : PackedState) (capacity : Nat)
    (events : List AddressedClear) :
    let result :=
      batchStream capacity
        { batches := [], fallback := [] } events
    runAddressed initial events =
      runAddressed (runBatches initial result.batches) result.fallback := by
  dsimp only
  apply partitioned_batch_schedule_eq
  simpa [BatchAccumulator.represented] using
    batchStream_empty_coverage capacity events

/-- A complete epoch preserves the declared table-capacity invariant. -/
theorem batchStream_capacity
    {capacity : Nat} {state : BatchAccumulator}
    (hcapacity : state.batches.length ≤ capacity)
    (events : List AddressedClear) :
    (batchStream capacity state events).batches.length ≤ capacity := by
  induction events generalizing state with
  | nil => simpa [batchStream] using hcapacity
  | cons event rest ih =>
      simp only [batchStream]
      exact ih (insertBatched_capacity hcapacity event)

/-- In particular, the verified epoch begun with an empty table never
allocates more entries than its declared capacity. -/
theorem batchStream_empty_capacity
    (capacity : Nat) (events : List AddressedClear) :
    (batchStream capacity
      { batches := [], fallback := [] } events).batches.length ≤ capacity :=
  batchStream_capacity (by simp) events

#print axioms runAddressed_apply
#print axioms runAddressed_eq_of_perm
#print axioms runAddressed_eq_of_mem_iff
#print axioms applyClearMask_eq_runClears
#print axioms applyPackedBatch_eq_runAddressed_expand
#print axioms runBatches_eq_runAddressed_expand
#print axioms partitioned_batch_schedule_eq
#print axioms partitioned_batch_schedule_eq_of_mem_iff
#print axioms insertIntoBatches_sound
#print axioms insertBatched_sound
#print axioms batchStream_empty_coverage
#print axioms bounded_batch_schedule_eq
#print axioms batchStream_capacity
#print axioms batchStream_empty_capacity

end SparkInterval.TernaryGoldbach.GoldbachAtomicBatching
