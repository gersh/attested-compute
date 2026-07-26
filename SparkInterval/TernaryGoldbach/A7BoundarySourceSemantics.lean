/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.NumberTheory.LSeries.RiemannZeta

/-!
# Exact source semantics for the CH25 Lemma A.7 boundary computation

The retained FLINT/Arb computation covers the frontier of
`(-3,5) + i(-4,4)` and bounds the paper's raw regularized logarithmic
derivative by `349 / 250`.  This module states that source claim directly and
separates it from a finite rational-box certificate.

The arithmetic implication is proved in ordinary Lean: if every frontier
point is covered by a retained leaf, the leaf's rational box contains the
value of the raw function, and the exact rational guard succeeds, then the
source claim follows.  In particular, neither the final norm estimate nor the
source claim itself needs to be asserted by a trusted-compute receipt.

The remaining producer/refinement obligation is intentionally visible as
`BoundaryEvidence.realizes`: it is the FLINT/Arb analytic statement that each
reported output box contains Mathlib's `riemannZeta` expression throughout
the corresponding input segment.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics

open Complex Set

/-- The exact open rectangle in CH25 Lemma A.7. -/
def sourceRectangle : Set ℂ :=
  Set.Ioo (-3 : ℝ) 5 ×ℂ Set.Ioo (-4 : ℝ) 4

/-- The raw function evaluated by the FLINT/Arb boundary computation. -/
noncomputable def rawG (s : ℂ) : ℂ :=
  -(deriv riemannZeta s / riemannZeta s) - 1 / (s - 1) + 1 / (s + 2)

/-- Exact source-shaped boundary claim. -/
def SourceClaim : Prop :=
  ∀ s ∈ frontier sourceRectangle, ‖rawG s‖ ≤ (349 : ℝ) / 250

/-- A rectangular complex enclosure whose endpoints and absolute-component
bounds are exact rationals.  The wire decoder may obtain these rationals from
Arb dyadics or binary64 values without trusting floating-point arithmetic. -/
structure RationalComplexBox where
  reLower : ℚ
  reUpper : ℚ
  imLower : ℚ
  imUpper : ℚ
  reAbsBound : ℚ
  imAbsBound : ℚ
  deriving Repr, DecidableEq, BEq

namespace RationalComplexBox

/-- Pointwise semantics of the exact rational rectangle. -/
def Contains (box : RationalComplexBox) (z : ℂ) : Prop :=
  (box.reLower : ℝ) ≤ z.re ∧ z.re ≤ (box.reUpper : ℝ) ∧
    (box.imLower : ℝ) ≤ z.im ∧ z.im ≤ (box.imUpper : ℝ)

/-- Fully decidable rational guard turning component enclosures into a norm
bound.  Supplying component bounds explicitly keeps the checker small and
avoids any trusted square-root operation. -/
def Guard (box : RationalComplexBox) (target : ℚ) : Prop :=
  box.reLower ≤ box.reUpper ∧
    box.imLower ≤ box.imUpper ∧
    0 ≤ target ∧
    0 ≤ box.reAbsBound ∧
    0 ≤ box.imAbsBound ∧
    -box.reAbsBound ≤ box.reLower ∧
    box.reUpper ≤ box.reAbsBound ∧
    -box.imAbsBound ≤ box.imLower ∧
    box.imUpper ≤ box.imAbsBound ∧
    box.reAbsBound ^ 2 + box.imAbsBound ^ 2 ≤ target ^ 2

instance instDecidableGuard (box : RationalComplexBox) (target : ℚ) :
    Decidable (box.Guard target) := by
  unfold Guard
  infer_instance

private theorem norm_le_of_sq_le_sq {z : ℂ} {bound : ℝ}
    (hbound : 0 ≤ bound) (hsq : ‖z‖ ^ 2 ≤ bound ^ 2) :
    ‖z‖ ≤ bound := by
  nlinarith [norm_nonneg z]

/-- Exact rational box arithmetic implies the claimed complex norm bound. -/
theorem norm_le_of_contains_guard {box : RationalComplexBox} {target : ℚ}
    {z : ℂ} (hcontains : box.Contains z) (hguard : box.Guard target) :
    ‖z‖ ≤ (target : ℝ) := by
  rcases hcontains with ⟨hreLower, hreUpper, himLower, himUpper⟩
  rcases hguard with
    ⟨_, _, htarget, hreAbs, himAbs, hreBoxLower, hreBoxUpper,
      himBoxLower, himBoxUpper, hsum⟩
  have htarget' : (0 : ℝ) ≤ (target : ℝ) := by
    exact_mod_cast htarget
  have hreAbs' : (0 : ℝ) ≤ (box.reAbsBound : ℝ) := by
    exact_mod_cast hreAbs
  have himAbs' : (0 : ℝ) ≤ (box.imAbsBound : ℝ) := by
    exact_mod_cast himAbs
  have hreLower' : -(box.reAbsBound : ℝ) ≤ z.re := by
    have h : (-(box.reAbsBound) : ℚ) ≤ box.reLower := hreBoxLower
    exact (by exact_mod_cast h : -(box.reAbsBound : ℝ) ≤
      (box.reLower : ℝ)).trans hreLower
  have hreUpper' : z.re ≤ (box.reAbsBound : ℝ) := by
    have h : (box.reUpper : ℝ) ≤ (box.reAbsBound : ℝ) := by
      exact_mod_cast hreBoxUpper
    exact hreUpper.trans h
  have himLower' : -(box.imAbsBound : ℝ) ≤ z.im := by
    have h : (-(box.imAbsBound) : ℚ) ≤ box.imLower := himBoxLower
    exact (by exact_mod_cast h : -(box.imAbsBound : ℝ) ≤
      (box.imLower : ℝ)).trans himLower
  have himUpper' : z.im ≤ (box.imAbsBound : ℝ) := by
    have h : (box.imUpper : ℝ) ≤ (box.imAbsBound : ℝ) := by
      exact_mod_cast himBoxUpper
    exact himUpper.trans h
  have hsum' :
      (box.reAbsBound : ℝ) ^ 2 + (box.imAbsBound : ℝ) ^ 2 ≤
        (target : ℝ) ^ 2 := by
    exact_mod_cast hsum
  apply norm_le_of_sq_le_sq htarget'
  rw [Complex.sq_norm, Complex.normSq_apply]
  have hreSq : z.re ^ 2 ≤ (box.reAbsBound : ℝ) ^ 2 := by
    nlinarith
  have himSq : z.im ^ 2 ≤ (box.imAbsBound : ℝ) ^ 2 := by
    nlinarith
  linarith

end RationalComplexBox

/-- The four oriented sides of the rectangle. -/
inductive Edge where
  | left
  | right
  | bottom
  | top
  deriving Repr, DecidableEq, BEq

/-- One retained boundary subdivision with an exact rational input interval
and output box. -/
structure Leaf where
  edge : Edge
  lower : ℚ
  upper : ℚ
  output : RationalComplexBox
  deriving Repr, DecidableEq, BEq

namespace Leaf

/-- Exact geometric meaning of a retained leaf. -/
def InputContains (leaf : Leaf) (s : ℂ) : Prop :=
  match leaf.edge with
  | .left =>
      s.re = -3 ∧ (leaf.lower : ℝ) ≤ s.im ∧
        s.im ≤ (leaf.upper : ℝ)
  | .right =>
      s.re = 5 ∧ (leaf.lower : ℝ) ≤ s.im ∧
        s.im ≤ (leaf.upper : ℝ)
  | .bottom =>
      s.im = -4 ∧ (leaf.lower : ℝ) ≤ s.re ∧
        s.re ≤ (leaf.upper : ℝ)
  | .top =>
      s.im = 4 ∧ (leaf.lower : ℝ) ≤ s.re ∧
        s.re ≤ (leaf.upper : ℝ)

end Leaf

/-- Exact target represented in rational certificate arithmetic. -/
def sourceTarget : ℚ := 349 / 250

/-- Finite semantic evidence emitted by the boundary campaign.  Coverage and
all guards are finite.  `realizes` isolates the one analytic refinement edge:
the reported Arb box encloses Mathlib's raw zeta expression throughout the
corresponding input segment. -/
structure BoundaryEvidence where
  leaves : List Leaf
  coverage : ∀ s ∈ frontier sourceRectangle,
    ∃ leaf, leaf ∈ leaves ∧ leaf.InputContains s
  realizes : ∀ leaf, leaf ∈ leaves → ∀ s,
    leaf.InputContains s → leaf.output.Contains (rawG s)
  guards : ∀ leaf, leaf ∈ leaves → leaf.output.Guard sourceTarget

/-- A complete finite rational-box certificate proves the source-shaped
boundary estimate in ordinary Lean. -/
theorem sourceClaim_of_boundary_evidence
    (evidence : BoundaryEvidence) : SourceClaim := by
  intro s hs
  obtain ⟨leaf, hleaf, hsLeaf⟩ := evidence.coverage s hs
  have hcontains := evidence.realizes leaf hleaf s hsLeaf
  have hguard := evidence.guards leaf hleaf
  have hnorm := RationalComplexBox.norm_le_of_contains_guard hcontains hguard
  simpa [sourceTarget] using hnorm

end SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics
