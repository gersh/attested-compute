/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQGRHBridge
import SparkInterval.Dirichlet.FactoredSmallQSourceRealization

/-!
# Roster-indexed completed-sign families as finite-GRH evidence

The arithmetic campaign names primitive characters by opaque natural-number
identifiers, whereas `GRHVerifiedForModulus` quantifies over mathematical
Dirichlet characters.  This module crosses exactly that boundary using a
`PrimitiveRosterRealization`: completeness chooses the unique roster identifier
for an arbitrary primitive character, and `characterOf` identifies the family
belonging to it.

All analytic and provenance inputs remain explicit.  In particular, the caller
must provide the Hardy model, endpoint links, height bounds, checked family,
total-zero upper bound, and the equality `family.characterId = id` separately
for every identifier in the realized roster.  The identifier equality is an
auditable source-binding invariant; the evaluator links and Hardy model are the
semantic bridge from those source-keyed endpoints to the mathematical
character.

This file introduces no trust declaration and uses neither `sorry` nor
`native_decide`.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQRosterGRHBridge

open DirichletCharacter
open SparkInterval.Certified
open SparkInterval.Dirichlet
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQSourceRealization
open SparkInterval.Dirichlet.FactoredSmallQZeroBracket

variable {q : Nat} [NeZero q]
variable {roster : List Nat}

/-- A checked roster family really carries its roster identifier down to every
lower and upper source key.  This is the finite provenance consequence of the
explicit family-header binding and the ordinary family check. -/
theorem checked_family_entry_characterIds
    {count : Nat} {id : Nat}
    {family : CompletedSignBracketFamily count}
    {fourierDisks : CellKey → ComplexDisk}
    (hcharacterId : family.characterId = id)
    (hcheck : family.check fourierDisks = true) :
    ∀ i,
      (family.entries i).lower.key.characterId = id ∧
      (family.entries i).upper.key.characterId = id := by
  intro i
  have hvalid := CompletedSignBracketFamily.check_eq_true.mp hcheck
  have hlower : (family.entries i).lower.key.characterId = id :=
    (hvalid.2.1 i).2.1.trans hcharacterId
  have hbracket := (hvalid.2.1 i).2.2
  exact ⟨hlower, hbracket.2.1.symm.trans hlower⟩

/-- Use a complete opaque-ID roster to assemble one checked completed-sign
family per primitive character into `GRHVerifiedForModulus`.

Nothing analytic is inferred from the finite family check.  The Hardy model,
endpoint links, interval bounds, and total L-zero count are independent
arguments indexed by every roster identifier. -/
theorem grhVerifiedForModulus_of_primitiveRosterCompletedSignBracketFamilies
    {lo hi : ℝ}
    (realization : PrimitiveRosterRealization q roster)
    (counts : Nat → Nat)
    (evaluators : Nat → ℝ → ℝ)
    (families : ∀ id, CompletedSignBracketFamily (counts id))
    (fourierDisks : Nat → CellKey → ComplexDisk)
    (hnontrivial : ∀ id, id ∈ roster →
      realization.characterOf id ≠ 1)
    (models : ∀ id, id ∈ roster →
      DirichletHardyModel (realization.characterOf id)
        (evaluators id) lo hi)
    (hfamilyCharacterIds : ∀ id, id ∈ roster →
      (families id).characterId = id)
    (hchecks : ∀ id, id ∈ roster →
      (families id).check (fourierDisks id) = true)
    (hlinks : ∀ id (_hid : id ∈ roster) (i : Fin (counts id)),
      ((families id).entries i).lower.EvaluatorLink
          (evaluators (families id).characterId) ∧
      ((families id).entries i).upper.EvaluatorLink
          (evaluators (families id).characterId))
    (hlower : ∀ id (_hid : id ∈ roster) (i : Fin (counts id)),
      lo ≤ (((families id).entries i).lower.time : ℝ))
    (hupper : ∀ id (_hid : id ∈ roster) (i : Fin (counts id)),
      (((families id).entries i).upper.time : ℝ) ≤ hi)
    (totalUpper : ∀ id, id ∈ roster →
      LZeroCountUpperBound (realization.characterOf id) lo hi (counts id)) :
    GRHVerifiedForModulus q lo hi := by
  apply grhVerifiedForModulus_of_characters
  intro χ hprimitive
  rcases realization.existsUnique_id hprimitive with
    ⟨id, ⟨hid, hcharacter⟩, _hunique⟩
  subst χ
  have hfamilyCharacterId := hfamilyCharacterIds id hid
  have _hsourceKeys := checked_family_entry_characterIds hfamilyCharacterId
    (hchecks id hid)
  have hlinksForId : ∀ i,
      ((families id).entries i).lower.EvaluatorLink (evaluators id) ∧
      ((families id).entries i).upper.EvaluatorLink (evaluators id) := by
    intro i
    simpa [hfamilyCharacterId] using hlinks id hid i
  exact (models id hid).verifyCompletedSignBracketFamily
    (hnontrivial id hid) (families id) (fourierDisks id)
    (hchecks id hid) hlinksForId (hlower id hid) (hupper id hid)
    (totalUpper id hid)

/-- For `q ≥ 2`, primitive characters are automatically nontrivial, so the
roster theorem needs no separate nontriviality argument.  Every other finite
and analytic premise remains unchanged and explicit. -/
theorem grhVerifiedForModulus_of_primitiveRosterCompletedSignBracketFamilies_of_two_le
    {lo hi : ℝ}
    (hq : 2 ≤ q)
    (realization : PrimitiveRosterRealization q roster)
    (counts : Nat → Nat)
    (evaluators : Nat → ℝ → ℝ)
    (families : ∀ id, CompletedSignBracketFamily (counts id))
    (fourierDisks : Nat → CellKey → ComplexDisk)
    (models : ∀ id, id ∈ roster →
      DirichletHardyModel (realization.characterOf id)
        (evaluators id) lo hi)
    (hfamilyCharacterIds : ∀ id, id ∈ roster →
      (families id).characterId = id)
    (hchecks : ∀ id, id ∈ roster →
      (families id).check (fourierDisks id) = true)
    (hlinks : ∀ id (_hid : id ∈ roster) (i : Fin (counts id)),
      ((families id).entries i).lower.EvaluatorLink
          (evaluators (families id).characterId) ∧
      ((families id).entries i).upper.EvaluatorLink
          (evaluators (families id).characterId))
    (hlower : ∀ id (_hid : id ∈ roster) (i : Fin (counts id)),
      lo ≤ (((families id).entries i).lower.time : ℝ))
    (hupper : ∀ id (_hid : id ∈ roster) (i : Fin (counts id)),
      (((families id).entries i).upper.time : ℝ) ≤ hi)
    (totalUpper : ∀ id, id ∈ roster →
      LZeroCountUpperBound (realization.characterOf id) lo hi (counts id)) :
    GRHVerifiedForModulus q lo hi :=
  grhVerifiedForModulus_of_primitiveRosterCompletedSignBracketFamilies
    realization counts evaluators families fourierDisks
    (fun _id hid ↦ ne_one_of_isPrimitive hq
      (realization.character_primitive hid))
    models hfamilyCharacterIds hchecks hlinks hlower hupper totalUpper

end SparkInterval.Dirichlet.FactoredSmallQRosterGRHBridge
