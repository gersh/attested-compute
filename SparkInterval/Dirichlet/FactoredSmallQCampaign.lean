/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Data.List.Defs

/-!
# Exact campaign coverage for factored small-`q` certificates

This module isolates the finite indexing obligation from numerical arithmetic.
A production campaign is split into character batches.  Every batch contains
one payload for every frequency of every character assigned to that batch.
The executable checker proves the deliberately simple global equation

```
accepted keys = roster.flatMap (fun chi => (List.range N).map (chi, .))
```

together with exact batch ordinals and character offsets.  Consequently a
missing, duplicated, reordered, or substituted `(character, frequency)` cell
fails closed.  The payload checker is supplied by the arithmetic layer; this
file neither trusts hashes nor gives physical execution a mathematical
meaning.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQCampaign

/-- Human-readable identity of one arithmetic result. -/
structure CellKey where
  characterId : Nat
  frequency : Nat
  deriving Repr, DecidableEq, BEq

/-- A payload tagged by the identity that its arithmetic checker must prove. -/
structure Cell (Payload : Type) where
  key : CellKey
  payload : Payload

/-- One bounded character batch from a persistent modulus plan. -/
structure Batch (Payload : Type) where
  ordinal : Nat
  characterStart : Nat
  characters : List Nat
  cells : List (Cell Payload)

/-- A complete single-modulus campaign. -/
structure Certificate (Payload : Type) where
  q : Nat
  roster : List Nat
  transformLength : Nat
  batches : List (Batch Payload)

/-- Application-owned source domain.  This is an argument to the checker,
not data whose meaning the untrusted certificate may choose. -/
structure Spec where
  q : Nat
  roster : List Nat
  transformLength : Nat
  deriving Repr, DecidableEq, BEq

def Spec.WellFormed (spec : Spec) : Prop :=
  3 ≤ spec.q ∧ spec.roster ≠ [] ∧ spec.roster.Nodup ∧
  0 < spec.transformLength

instance (spec : Spec) : Decidable spec.WellFormed := by
  unfold Spec.WellFormed
  infer_instance

/-- The exact row-major Cartesian product required by the source algorithm. -/
def expectedKeys (roster : List Nat) (transformLength : Nat) : List CellKey :=
  roster.flatMap fun characterId =>
    (List.range transformLength).map fun frequency =>
      ⟨characterId, frequency⟩

/-- Exact ordinal and half-open character-offset chain for split batches. -/
def BatchChain {Payload : Type} : Nat → Nat → List (Batch Payload) → Prop
  | _, _, [] => True
  | nextOrdinal, nextCharacter, batch :: rest =>
      batch.ordinal = nextOrdinal ∧
      batch.characterStart = nextCharacter ∧
      BatchChain (nextOrdinal + 1)
        (nextCharacter + batch.characters.length) rest

instance instDecidableBatchChain {Payload : Type}
    (nextOrdinal nextCharacter : Nat) (batches : List (Batch Payload)) :
    Decidable (BatchChain nextOrdinal nextCharacter batches) := by
  induction batches generalizing nextOrdinal nextCharacter with
  | nil => exact isTrue trivial
  | cons batch rest inductionHypothesis =>
      rw [BatchChain]
      letI := inductionHypothesis
        (nextOrdinal + 1) (nextCharacter + batch.characters.length)
      infer_instance

/-- Each physical batch carries exactly its own character/frequency product;
the global equation below is therefore not obtainable by moving cells across
batch boundaries. -/
def BatchCellsValid {Payload : Type} (transformLength : Nat) :
    List (Batch Payload) → Prop
  | [] => True
  | batch :: rest =>
      batch.cells.map Cell.key =
        expectedKeys batch.characters transformLength ∧
      BatchCellsValid transformLength rest

instance instDecidableBatchCellsValid {Payload : Type}
    (transformLength : Nat) (batches : List (Batch Payload)) :
    Decidable (BatchCellsValid transformLength batches) := by
  induction batches with
  | nil => exact isTrue trivial
  | cons batch rest inductionHypothesis =>
      rw [BatchCellsValid]
      letI := inductionHypothesis
      infer_instance

/-- The compact, human-auditable coverage proposition. -/
def Certificate.CoverageValid {Payload : Type} (spec : Spec)
    (certificate : Certificate Payload) : Prop :=
  spec.WellFormed ∧
  certificate.q = spec.q ∧
  certificate.roster = spec.roster ∧
  certificate.transformLength = spec.transformLength ∧
  BatchChain 0 0 certificate.batches ∧
  BatchCellsValid spec.transformLength certificate.batches ∧
  certificate.batches.flatMap (fun batch => batch.characters) =
    spec.roster ∧
  certificate.batches.flatMap (fun batch => batch.cells.map Cell.key) =
    expectedKeys spec.roster spec.transformLength

instance {Payload : Type} (spec : Spec) (certificate : Certificate Payload) :
    Decidable (certificate.CoverageValid spec) := by
  unfold Certificate.CoverageValid
  letI : Decidable (BatchChain 0 0 certificate.batches) :=
    instDecidableBatchChain 0 0 certificate.batches
  letI : Decidable
      (BatchCellsValid spec.transformLength certificate.batches) :=
    instDecidableBatchCellsValid spec.transformLength certificate.batches
  infer_instance

/-- The arithmetic predicate is deliberately supplied by the caller. -/
def Certificate.PayloadsValid {Payload : Type}
    (certificate : Certificate Payload)
    (payloadCheck : CellKey → Payload → Bool) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells → payloadCheck cell.key cell.payload = true

/-- Executable campaign checker.  The producer controls data, never the
predicate checked for that data. -/
def Certificate.check {Payload : Type} (spec : Spec)
    (certificate : Certificate Payload)
    (payloadCheck : CellKey → Payload → Bool) : Bool :=
  decide (certificate.CoverageValid spec) &&
  certificate.batches.all fun batch =>
    batch.cells.all fun cell => payloadCheck cell.key cell.payload

private theorem all_payloads_sound
    {Payload : Type}
    {certificate : Certificate Payload}
    {payloadCheck : CellKey → Payload → Bool}
    (hcheck : certificate.batches.all (fun batch =>
      batch.cells.all fun cell => payloadCheck cell.key cell.payload) = true) :
    certificate.PayloadsValid payloadCheck := by
  intro batch hbatch cell hcell
  have hbatchCheck :
      batch.cells.all (fun item => payloadCheck item.key item.payload) = true :=
    (List.all_eq_true.mp hcheck) batch hbatch
  exact (List.all_eq_true.mp hbatchCheck) cell hcell

/-- Soundness of both the exact coverage equation and every payload check. -/
theorem Certificate.checker_sound
    {Payload : Type}
    {spec : Spec}
    {certificate : Certificate Payload}
    {payloadCheck : CellKey → Payload → Bool}
    (hcheck : certificate.check spec payloadCheck = true) :
    certificate.CoverageValid spec ∧
      certificate.PayloadsValid payloadCheck := by
  simp only [Certificate.check, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  exact ⟨hcheck.1, all_payloads_sound hcheck.2⟩

/-- Every requested source key occurs in the accepted flattened campaign. -/
theorem Certificate.requested_key_mem
    {Payload : Type}
    {spec : Spec}
    {certificate : Certificate Payload}
    (hcoverage : certificate.CoverageValid spec)
    {characterId frequency : Nat}
    (hcharacter : characterId ∈ spec.roster)
    (hfrequency : frequency < spec.transformLength) :
    ⟨characterId, frequency⟩ ∈
      certificate.batches.flatMap (fun batch => batch.cells.map Cell.key) := by
  rw [hcoverage.2.2.2.2.2.2.2]
  simp [expectedKeys, hcharacter, hfrequency]

/-- Constructive lookup form used by arithmetic application theorems. -/
theorem Certificate.exists_cell_for_requested_key
    {Payload : Type}
    {spec : Spec}
    {certificate : Certificate Payload}
    (hcoverage : certificate.CoverageValid spec)
    {characterId frequency : Nat}
    (hcharacter : characterId ∈ spec.roster)
    (hfrequency : frequency < spec.transformLength) :
    ∃ batch, batch ∈ certificate.batches ∧
      ∃ cell, cell ∈ batch.cells ∧
        cell.key = ⟨characterId, frequency⟩ := by
  have hkey := certificate.requested_key_mem
    hcoverage hcharacter hfrequency
  rcases List.mem_flatMap.mp hkey with ⟨batch, hbatch, hkeyInBatch⟩
  rcases List.mem_map.mp hkeyInBatch with ⟨cell, hcell, hcellKey⟩
  exact ⟨batch, hbatch, cell, hcell, hcellKey⟩

@[simp] theorem expectedKeys_length (roster : List Nat)
    (transformLength : Nat) :
    (expectedKeys roster transformLength).length =
      roster.length * transformLength := by
  induction roster with
  | nil => simp [expectedKeys]
  | cons character rest inductionHypothesis =>
      change
        ((List.range transformLength).map
          (fun frequency =>
            ({ characterId := character, frequency := frequency } : CellKey)) ++
          expectedKeys rest transformLength).length =
        (rest.length + 1) * transformLength
      simp only [List.length_append, List.length_map, List.length_range]
      rw [inductionHypothesis]
      rw [Nat.add_mul]
      simp only [Nat.one_mul]
      exact Nat.add_comm _ _

/-- Exact cardinality follows from the same equation; it is not a separately
trusted campaign summary. -/
theorem Certificate.accepted_cell_count
    {Payload : Type}
    {spec : Spec}
    {certificate : Certificate Payload}
    (hcoverage : certificate.CoverageValid spec) :
    (certificate.batches.flatMap (fun batch => batch.cells)).length =
      spec.roster.length * spec.transformLength := by
  calc
    (certificate.batches.flatMap (fun batch => batch.cells)).length =
        (certificate.batches.flatMap
          (fun batch => batch.cells.map Cell.key)).length := by simp
    _ = (expectedKeys spec.roster spec.transformLength).length :=
      congrArg List.length hcoverage.2.2.2.2.2.2.2
    _ = spec.roster.length * spec.transformLength :=
      expectedKeys_length _ _

end SparkInterval.Dirichlet.FactoredSmallQCampaign
