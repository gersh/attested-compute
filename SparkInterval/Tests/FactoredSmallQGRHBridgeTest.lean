/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQGRHBridge

/-! Type-level regression tests for the completed-sign-family GRH bridge. -/

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQGRHBridge

open DirichletCharacter
open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQZeroBracket

example {N : ℕ} [NeZero N]
    {χ : DirichletCharacter ℂ N} {f : ℝ → ℝ} {lo hi : ℝ}
    {count : Nat}
    (hχ : χ ≠ 1)
    (model : DirichletHardyModel χ f lo hi)
    (family : CompletedSignBracketFamily count)
    (fourierDisks : CellKey → ComplexDisk)
    (hcheck : family.check fourierDisks = true)
    (hlinks : ∀ i,
      (family.entries i).lower.EvaluatorLink f ∧
      (family.entries i).upper.EvaluatorLink f)
    (hlower : ∀ i, lo ≤ ((family.entries i).lower.time : ℝ))
    (hupper : ∀ i, ((family.entries i).upper.time : ℝ) ≤ hi)
    (totalUpper : LZeroCountUpperBound χ lo hi count) :
    ∀ z ∈ nontrivialCriticalStrip lo hi,
      χ.LFunction z = 0 → z.re = (1 : ℝ) / 2 :=
  model.verifyCompletedSignBracketFamily hχ family fourierDisks hcheck
    hlinks hlower hupper totalUpper

example {N : ℕ} [NeZero N] {lo hi : ℝ}
    (hN : 2 ≤ N)
    (counts : DirichletCharacter ℂ N → Nat)
    (evaluators : DirichletCharacter ℂ N → ℝ → ℝ)
    (families : ∀ χ, CompletedSignBracketFamily (counts χ))
    (fourierDisks : DirichletCharacter ℂ N → CellKey → ComplexDisk)
    (models : ∀ (χ : DirichletCharacter ℂ N), χ.IsPrimitive →
      DirichletHardyModel χ (evaluators χ) lo hi)
    (hchecks : ∀ (χ : DirichletCharacter ℂ N) (_hprimitive : χ.IsPrimitive),
      (families χ).check (fourierDisks χ) = true)
    (hlinks : ∀ (χ : DirichletCharacter ℂ N) (_hprimitive : χ.IsPrimitive)
      (i : Fin (counts χ)),
      ((families χ).entries i).lower.EvaluatorLink (evaluators χ) ∧
      ((families χ).entries i).upper.EvaluatorLink (evaluators χ))
    (hlower : ∀ (χ : DirichletCharacter ℂ N) (_hprimitive : χ.IsPrimitive)
      (i : Fin (counts χ)),
      lo ≤ (((families χ).entries i).lower.time : ℝ))
    (hupper : ∀ (χ : DirichletCharacter ℂ N) (_hprimitive : χ.IsPrimitive)
      (i : Fin (counts χ)),
      (((families χ).entries i).upper.time : ℝ) ≤ hi)
    (totalUpper : ∀ (χ : DirichletCharacter ℂ N)
      (_hprimitive : χ.IsPrimitive),
      LZeroCountUpperBound χ lo hi (counts χ)) :
    GRHVerifiedForModulus N lo hi :=
  grhVerifiedForModulus_of_completedSignBracketFamilies_of_two_le hN counts
    evaluators families fourierDisks models hchecks hlinks hlower hupper
    totalUpper

#print axioms DirichletHardyModel.verifyCompletedSignBracketFamily
#print axioms grhVerifiedForModulus_of_completedSignBracketFamilies
#print axioms grhVerifiedForModulus_of_completedSignBracketFamilies_of_two_le

end SparkInterval.Tests.FactoredSmallQGRHBridge
