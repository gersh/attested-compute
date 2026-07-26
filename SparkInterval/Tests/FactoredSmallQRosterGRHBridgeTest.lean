/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRosterGRHBridge

/-! Type-level regression tests for the opaque-roster finite-GRH bridge. -/

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQRosterGRHBridge

open DirichletCharacter
open SparkInterval.Certified
open SparkInterval.Dirichlet
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQSourceRealization
open SparkInterval.Dirichlet.FactoredSmallQZeroBracket
open SparkInterval.Dirichlet.FactoredSmallQRosterGRHBridge

example {q : Nat} [NeZero q] {roster : List Nat} {lo hi : ℝ}
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
    GRHVerifiedForModulus q lo hi :=
  grhVerifiedForModulus_of_primitiveRosterCompletedSignBracketFamilies
    realization counts evaluators families fourierDisks hnontrivial models
    hfamilyCharacterIds hchecks hlinks hlower hupper totalUpper

example {q : Nat} [NeZero q] {roster : List Nat} {lo hi : ℝ}
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
  grhVerifiedForModulus_of_primitiveRosterCompletedSignBracketFamilies_of_two_le
    hq realization counts evaluators families fourierDisks models
    hfamilyCharacterIds hchecks hlinks hlower hupper totalUpper

#print axioms checked_family_entry_characterIds
#print axioms
  grhVerifiedForModulus_of_primitiveRosterCompletedSignBracketFamilies
#print axioms
  grhVerifiedForModulus_of_primitiveRosterCompletedSignBracketFamilies_of_two_le

end SparkInterval.Tests.FactoredSmallQRosterGRHBridge
