/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement
import SparkInterval.TernaryGoldbach.MobiusResidue235
import SparkInterval.TernaryGoldbach.MobiusResidue2357
import SparkInterval.TernaryGoldbach.MobiusResidue235711

/-!
# Structural roster preflight for the packed Möbius CUDA path

The split-square CUDA launch currently has two source modes. Production seeds
`[2,3,5]`; the qualification-only residue-2357 path seeds `[2,3,5,7]`.
This model also reserves an explicit residue-235711 qualification mode for a
source candidate that would seed `[2,3,5,7,11]`.  Each mode rejects a roster
shorter than its seeded prefix and runs a structural preflight before
initializing any support row. The preflight checks:

* the exact prefix selected by the source mode;
* the machine-safe range `2 ≤ p ≤ 10^8` for every entry;
* strict increase of the roster; and
* the mode-specific source lower bound (`7`, `11`, or `13`) after the prefix.

The native validator combines failures with `atomicExch(flag, 1)`.  This file
models the resulting Boolean flag, rather than the parallel implementation of
that reduction.  It also models the initializer's bit expression and proves
the fail-closed consequence: if the flag is set, every initialized packed row
has the poison bit set.

This is a pure model.  It does not identify a device pointer with a Lean list,
prove CUDA atomics or stream ordering, or prove that compiled machine code
implements these definitions.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusPackedCUDARosterPreflight

open SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement
open SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
open SparkInterval.TernaryGoldbach.MobiusResidue235
open SparkInterval.TernaryGoldbach.MobiusResidue2357
open SparkInterval.TernaryGoldbach.MobiusResidue235711

/-- Compile-time seed mode.  The first two constructors correspond to the
current native split-square launches; `residue235711` is deliberately a
separate qualification candidate, so it cannot accidentally reuse the
residue-2357 prefix or receipt identity. -/
inductive ResidueSeedMode where
  | residue235
  | residue2357
  | residue235711
  deriving Repr, DecidableEq

/-- Exact interpretation of the current native
`require_seven_seed` parameter. -/
def sourceResidueSeedMode (requireSevenSeed : Bool) :
    ResidueSeedMode :=
  if requireSevenSeed then .residue2357 else .residue235

@[simp] theorem sourceResidueSeedMode_false :
    sourceResidueSeedMode false = .residue235 := by
  rfl

@[simp] theorem sourceResidueSeedMode_true :
    sourceResidueSeedMode true = .residue2357 := by
  rfl

/-- Exact authenticated roster prefix consumed by the selected initializer. -/
def seededPrimePrefix : ResidueSeedMode → List Nat
  | .residue235 => seedPrimes
  | .residue2357 => seedPrimes2357
  | .residue235711 => seedPrimes235711

/-- First value admitted to the event-driven suffix by the device validator. -/
def suffixMinimumPrime : ResidueSeedMode → Nat
  | .residue235 => 7
  | .residue2357 => residue2357SuffixMinimumPrime
  | .residue235711 => residue235711SuffixMinimumPrime

/-- Largest divisor admitted before the CUDA code performs division,
remainder, or square arithmetic.  Its square is the source limit `10^16`. -/
def maximumMachinePrime : Nat := 100_000_000

/-- The per-entry range check performed by the device preflight. -/
def MachineSafePrime (prime : Nat) : Prop :=
  2 ≤ prime ∧ prime ≤ maximumMachinePrime

instance (prime : Nat) : Decidable (MachineSafePrime prime) := by
  unfold MachineSafePrime
  infer_instance

/-- Mathematical normal form of the mode-dependent launch count guard and all
device roster checks. `Pairwise (· < ·)` is the transitive normal form of the
kernel's adjacent `current > previous` checks. -/
def StructuralRosterValidFor
    (mode : ResidueSeedMode) (roster : List Nat) : Prop :=
  (seededPrimePrefix mode).length ≤ roster.length ∧
    roster.take (seededPrimePrefix mode).length =
      seededPrimePrefix mode ∧
    (∀ prime ∈ roster, MachineSafePrime prime) ∧
    roster.Pairwise (· < ·) ∧
    ∀ prime ∈ roster.drop (seededPrimePrefix mode).length,
      suffixMinimumPrime mode ≤ prime

instance (mode : ResidueSeedMode) (roster : List Nat) :
    Decidable (StructuralRosterValidFor mode roster) := by
  unfold StructuralRosterValidFor
  infer_instance

/-- Backwards-compatible production specialization. -/
def StructuralRosterValid (roster : List Nat) : Prop :=
  StructuralRosterValidFor .residue235 roster

instance (roster : List Nat) :
    Decidable (StructuralRosterValid roster) := by
  unfold StructuralRosterValid
  infer_instance

/-- Boolean abstraction of the device word changed from zero to one by any
failing validation thread. The mode-dependent launch count guard is included
in the structural predicate; natively, a short roster is rejected before
launch. -/
def deviceRosterInvalidFor
    (mode : ResidueSeedMode) (roster : List Nat) : Bool :=
  decide (¬ StructuralRosterValidFor mode roster)

/-- Backwards-compatible production specialization. -/
def deviceRosterInvalid (roster : List Nat) : Bool :=
  deviceRosterInvalidFor .residue235 roster

@[simp] theorem deviceRosterInvalidFor_eq_true_iff
    (mode : ResidueSeedMode) (roster : List Nat) :
    deviceRosterInvalidFor mode roster = true ↔
      ¬ StructuralRosterValidFor mode roster := by
  simp [deviceRosterInvalidFor]

@[simp] theorem deviceRosterInvalidFor_eq_false_iff
    (mode : ResidueSeedMode) (roster : List Nat) :
    deviceRosterInvalidFor mode roster = false ↔
      StructuralRosterValidFor mode roster := by
  simp [deviceRosterInvalidFor]

@[simp] theorem deviceRosterInvalid_eq_true_iff
    (roster : List Nat) :
    deviceRosterInvalid roster = true ↔
      ¬ StructuralRosterValid roster := by
  simp [deviceRosterInvalid, StructuralRosterValid]

@[simp] theorem deviceRosterInvalid_eq_false_iff
    (roster : List Nat) :
    deviceRosterInvalid roster = false ↔
      StructuralRosterValid roster := by
  simp [deviceRosterInvalid, StructuralRosterValid]

/-- Pure form of the initializer expression
`seed | (invalid ? poisonBit : 0)`. -/
def initializePackedWord (invalid : Bool) (seed : Nat) : Nat :=
  seed ||| if invalid then cudaPoisonBit else 0

/-- Initialize arbitrary residue-derived seed words after the selected
preflight. Production obtains a seed from the 900-entry table. Qualification
paths may apply the separately proved modulo-49 and modulo-121 extensions
before the same poison-bit OR. -/
def initializePackedRowsFor
    (mode : ResidueSeedMode) (roster : List Nat)
    (seeds : List Nat) : List Nat :=
  seeds.map
    (initializePackedWord (deviceRosterInvalidFor mode roster))

/-- Backwards-compatible production specialization. -/
def initializePackedRows
    (roster : List Nat) (seeds : List Nat) : List Nat :=
  initializePackedRowsFor .residue235 roster seeds

/-- Setting bit 63 by the exact CUDA OR expression makes the arithmetic poison
predicate true, independently of the lower seed bits. -/
theorem poisonSet_initializePackedWord_true (seed : Nat) :
    poisonSet (initializePackedWord true seed) := by
  rw [← cudaPoison_nonzero_iff]
  change ((seed ||| 2 ^ 63) &&& 2 ^ 63) ≠ 0
  rw [Nat.and_two_pow, Nat.testBit_lor]
  simp [Nat.testBit, Nat.shiftRight_eq_div_pow]

/-- Mode-generic fail-closed initializer theorem. In particular this closes
the previously unmodeled `require_seven_seed = true` source branch. -/
theorem invalidFlagFor_implies_all_initialized_rows_poison
    {mode : ResidueSeedMode} {roster seeds : List Nat}
    (invalid : deviceRosterInvalidFor mode roster = true) :
    ∀ word ∈ initializePackedRowsFor mode roster seeds,
      poisonSet word := by
  intro word wordMem
  rw [initializePackedRowsFor] at wordMem
  obtain ⟨seed, _, rfl⟩ := List.mem_map.mp wordMem
  simp only [initializePackedWord, invalid, if_true]
  exact poisonSet_initializePackedWord_true seed

/-- Production specialization retained for existing consumers. -/
theorem invalidFlag_implies_all_initialized_rows_poison
    {roster seeds : List Nat}
    (invalid : deviceRosterInvalid roster = true) :
    ∀ word ∈ initializePackedRows roster seeds, poisonSet word := by
  exact invalidFlagFor_implies_all_initialized_rows_poison invalid

/-- Expanded structural facts available whenever the device invalid flag is
clear.  This exposes the precise native arithmetic preconditions without
requiring consumers to unfold the model. -/
theorem valid_of_deviceRosterInvalid_eq_false
    {roster : List Nat}
    (valid : deviceRosterInvalid roster = false) :
    3 ≤ roster.length ∧
      roster.take 3 = seedPrimes ∧
      (∀ prime ∈ roster,
        2 ≤ prime ∧ prime ≤ maximumMachinePrime) ∧
      roster.Pairwise (· < ·) ∧
      ∀ prime ∈ roster.drop 3, 7 ≤ prime := by
  exact (deviceRosterInvalid_eq_false_iff roster).mp valid

/-- Expanded facts for the qualification-only `[2,3,5,7]` source mode. -/
theorem valid2357_of_deviceRosterInvalidFor_eq_false
    {roster : List Nat}
    (valid :
      deviceRosterInvalidFor .residue2357 roster = false) :
    4 ≤ roster.length ∧
      roster.take 4 = seedPrimes2357 ∧
      (∀ prime ∈ roster,
        2 ≤ prime ∧ prime ≤ maximumMachinePrime) ∧
      roster.Pairwise (· < ·) ∧
      ∀ prime ∈ roster.drop 4,
        residue2357SuffixMinimumPrime ≤ prime := by
  simpa [StructuralRosterValidFor, seededPrimePrefix,
    suffixMinimumPrime, seedPrimes2357, seedPrimes,
    MachineSafePrime] using
    (deviceRosterInvalidFor_eq_false_iff
      ResidueSeedMode.residue2357 roster).mp valid

/-- Expanded facts for the proposed `[2,3,5,7,11]` qualification mode. -/
theorem valid235711_of_deviceRosterInvalidFor_eq_false
    {roster : List Nat}
    (valid :
      deviceRosterInvalidFor .residue235711 roster = false) :
    5 ≤ roster.length ∧
      roster.take 5 = seedPrimes235711 ∧
      (∀ prime ∈ roster,
        2 ≤ prime ∧ prime ≤ maximumMachinePrime) ∧
      roster.Pairwise (· < ·) ∧
      ∀ prime ∈ roster.drop 5,
        residue235711SuffixMinimumPrime ≤ prime := by
  simpa [StructuralRosterValidFor, seededPrimePrefix,
    suffixMinimumPrime, seedPrimes235711, seedPrimes2357,
    seedPrimes, MachineSafePrime] using
    (deviceRosterInvalidFor_eq_false_iff
      ResidueSeedMode.residue235711 roster).mp valid

theorem maximumMachinePrime_square_eq_sourceLimit :
    maximumMachinePrime * maximumMachinePrime =
      10_000_000_000_000_000 := by
  norm_num [maximumMachinePrime]

#print axioms deviceRosterInvalid_eq_true_iff
#print axioms deviceRosterInvalid_eq_false_iff
#print axioms sourceResidueSeedMode_false
#print axioms sourceResidueSeedMode_true
#print axioms deviceRosterInvalidFor_eq_true_iff
#print axioms deviceRosterInvalidFor_eq_false_iff
#print axioms poisonSet_initializePackedWord_true
#print axioms invalidFlag_implies_all_initialized_rows_poison
#print axioms invalidFlagFor_implies_all_initialized_rows_poison
#print axioms valid_of_deviceRosterInvalid_eq_false
#print axioms valid2357_of_deviceRosterInvalidFor_eq_false
#print axioms valid235711_of_deviceRosterInvalidFor_eq_false
#print axioms maximumMachinePrime_square_eq_sourceLimit

end SparkInterval.TernaryGoldbach.MobiusPackedCUDARosterPreflight
