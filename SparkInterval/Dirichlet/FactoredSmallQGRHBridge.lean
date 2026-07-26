/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQZeroBracket
import SparkInterval.Dirichlet.GRHVerification

/-!
# Completed small-q bracket families as finite-GRH evidence

This module is the final, proposition-level composition boundary between the
factored small-q arithmetic checker and the finite-strip Dirichlet GRH
verifier.  It deliberately does not package any analytic premises into an
opaque existential: the endpoint/evaluator links, interval containment,
nontriviality, Hardy model, and global L-zero count upper bound are all
arguments of the theorem.

The proof first projects the checked completed-sign family to the established
`RationalBracketFamily` interface and then calls
`DirichletHardyModel.verifyEndpointFamily`.  Consequently this file adds no
new trust assumption and uses neither `native_decide` nor `sorry`.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet

open DirichletCharacter
open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQZeroBracket

variable {N : ℕ} [NeZero N]

namespace DirichletHardyModel

/-- Feed a checked family of completed small-q sign brackets directly into
the finite-strip GRH verifier for one character.  Every analytic/model premise
remains visible at this boundary. -/
theorem verifyCompletedSignBracketFamily
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
      χ.LFunction z = 0 → z.re = (1 : ℝ) / 2 := by
  apply model.verifyEndpointFamily hχ
    family.toRationalBracketFamily
    (CompletedSignBracketFamily.toRationalBracketFamily_check hcheck)
  · intro i
    exact CompletedSignBracket.toRationalBracket_enclosesEndpoints
      (hlinks i).1 (hlinks i).2
  · intro i
    exact hlower i
  · intro i
    exact hupper i
  · exact totalUpper

end DirichletHardyModel

/-- Assemble the same explicit completed-sign-family verification data for
every primitive character into the modulus-level finite-GRH statement.

The data functions are indexed by every character so that their types do not
hide proof-dependent witnesses.  Only primitive characters are required to
satisfy the checking and analytic premises. -/
theorem grhVerifiedForModulus_of_completedSignBracketFamilies
    {lo hi : ℝ}
    (counts : DirichletCharacter ℂ N → Nat)
    (evaluators : DirichletCharacter ℂ N → ℝ → ℝ)
    (families : ∀ χ, CompletedSignBracketFamily (counts χ))
    (fourierDisks : DirichletCharacter ℂ N → CellKey → ComplexDisk)
    (hnontrivial : ∀ χ : DirichletCharacter ℂ N,
      χ.IsPrimitive → χ ≠ 1)
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
    GRHVerifiedForModulus N lo hi := by
  apply grhVerifiedForModulus_of_characters
  intro χ hprimitive
  exact (models χ hprimitive).verifyCompletedSignBracketFamily
    (hnontrivial χ hprimitive) (families χ) (fourierDisks χ)
    (hchecks χ hprimitive) (hlinks χ hprimitive)
    (hlower χ hprimitive) (hupper χ hprimitive)
    (totalUpper χ hprimitive)

/-- For moduli at least two, primitivity itself supplies the explicit
nontriviality premise needed by the preceding assembly theorem. -/
theorem grhVerifiedForModulus_of_completedSignBracketFamilies_of_two_le
    {lo hi : ℝ}
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
  grhVerifiedForModulus_of_completedSignBracketFamilies counts evaluators
    families fourierDisks (fun _χ hprimitive ↦
      ne_one_of_isPrimitive hN hprimitive) models hchecks hlinks hlower hupper
    totalUpper

end SparkInterval.Dirichlet
