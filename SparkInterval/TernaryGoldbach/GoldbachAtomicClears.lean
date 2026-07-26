/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachWheelFilter
import SparkInterval.TernaryGoldbach.GoldbachShiftedBitset

/-!
# Linearizable packed-word clears in the Goldbach sieve

The CUDA sieve represents 64 odd candidates in one word.  Every composite
event performs a linearizable `atomicAnd` that can only clear its addressed
bit.  This file proves the concurrency equation independently of CUDA:

* the final word is independent of the serialization order;
* deleting clear events is exact when their bits were already cleared by the
  word-owner initializer; and
* a filtered schedule therefore has the same final word as an unfiltered
  schedule once the wheel theorem supplies that redundancy premise.

The physical boundary remains explicit: CUDA/PTX/SASS must refine
`atomicClear`, and the hardware atomic operations must be linearizable.  No
claim about compilation or execution is made here.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.GoldbachAtomicClears

open GoldbachWordOwnerSieve GoldbachWheelFilter

/-- Logical contents of one packed 64-bit word. -/
abbrev Word := Fin 64 → Bool

/-- One atomic event clears exactly one bit and cannot set any other bit. -/
def atomicClear (word : Word) (cleared : Fin 64) : Word :=
  fun bit => if bit = cleared then false else word bit

/-- Sequential semantics of one linearization of the atomic events. -/
def runClears : Word → List (Fin 64) → Word
  | word, [] => word
  | word, cleared :: rest => runClears (atomicClear word cleared) rest

/-- Exact bit-level result of any serialized clear schedule. -/
theorem runClears_apply (word : Word) (events : List (Fin 64))
    (bit : Fin 64) :
    runClears word events bit =
      if bit ∈ events then false else word bit := by
  induction events generalizing word with
  | nil => simp [runClears]
  | cons cleared rest ih =>
      simp only [runClears, ih, List.mem_cons]
      by_cases hsame : bit = cleared
      · simp [hsame, atomicClear]
      · simp [hsame, atomicClear]

/-- Atomic serialization order cannot affect the final packed word. -/
theorem runClears_eq_of_perm (word : Word)
    {first second : List (Fin 64)} (hperm : first.Perm second) :
    runClears word first = runClears word second := by
  funext bit
  rw [runClears_apply, runClears_apply]
  have hmem : bit ∈ first ↔ bit ∈ second := hperm.mem_iff
  by_cases hfirst : bit ∈ first
  · simp [hfirst, hmem.mp hfirst]
  · have hsecond : bit ∉ second := by
      intro h
      exact hfirst (hmem.mpr h)
    simp [hfirst, hsecond]

/-- Clears that target bits already absent from the initialized word are
idempotent and may be omitted. -/
theorem append_redundant_clears
    (initial : Word) (kept skipped : List (Fin 64))
    (halready : ∀ bit ∈ skipped, initial bit = false) :
    runClears initial (kept ++ skipped) = runClears initial kept := by
  funext bit
  rw [runClears_apply, runClears_apply]
  by_cases hkept : bit ∈ kept
  · simp [hkept]
  · by_cases hskipped : bit ∈ skipped
    · simp [hkept, hskipped, halready bit hskipped]
    · simp [hkept, hskipped]

/-- The form used for a concurrent kernel: an arbitrary linearization of the
unfiltered events is equivalent to retaining only the useful events when all
skipped events target word-owner-cleared bits. -/
theorem filtered_schedule_eq
    (initial : Word) (unfiltered kept skipped : List (Fin 64))
    (hpartition : unfiltered.Perm (kept ++ skipped))
    (halready : ∀ bit ∈ skipped, initial bit = false) :
    runClears initial unfiltered = runClears initial kept := by
  rw [runClears_eq_of_perm initial hpartition]
  exact append_redundant_clears initial kept skipped halready

/-- Representation contract for the word-owner initializer: every candidate
in its mathematical clear set has a zero bit at the packed address selected by
the host geometry. -/
def WordOwnerRealizes
    (initial : Word) (basePrimes : List Nat)
    (bitOfCandidate : Nat → Fin 64) : Prop :=
  ∀ candidate, ClearedBy basePrimes candidate →
    initial (bitOfCandidate candidate) = false

/-- Direct connection from the wheel arithmetic theorem to the redundant-bit
premise used by `filtered_schedule_eq`.  Only the packed-address realization
contract remains as a physical initializer obligation. -/
theorem wheelRejected_alreadyClear
    (initial : Word) (basePrimes : List Nat)
    (bitOfCandidate : Nat → Fin 64)
    (hrealizes : WordOwnerRealizes initial basePrimes bitOfCandidate)
    (tailPrime cofactor : Nat)
    (htail : 2039 < tailPrime)
    (hcofactor : 0 < cofactor)
    (hbase : ∀ prime ∈ filterPrimes, prime ∈ basePrimes)
    (hrejected : ¬ FilterSurvives cofactor) :
    initial (bitOfCandidate (tailPrime * cofactor)) = false :=
  hrealizes _ (rejected_tail_event_already_cleared
    basePrimes tailPrime cofactor htail hcofactor hbase hrejected)

#print axioms runClears_apply
#print axioms runClears_eq_of_perm
#print axioms append_redundant_clears
#print axioms filtered_schedule_eq
#print axioms wheelRejected_alreadyClear

end SparkInterval.TernaryGoldbach.GoldbachAtomicClears
