/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib

/-!
# Source-shaped CDEM replacement-table Abel claim

This file restates, without a weakened consumer constant, the two finite
inequalities in
`MathExtras.CohenDressElMarraki.ReproducibleTableAbelVerifierOutput` from the
ternary-Goldbach development.  It deliberately includes the complete finite
table definitions so the trusted-compute registry cannot attach the returned
numbers to a caller-selected proposition.

The registered external result carries two natural numerators.  Its formal
meaning is `ScaledOutputClaim`: multiplication by the positive scale bounds
the two exact real sums below.  `sourceClaim_of_scaledOutput` is the ordinary
Lean theorem which specializes those numerators to the production values and
recovers the exact source proposition.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.CDEMAbelSource

open Finset
open scoped BigOperators

/-- Möbius-prefix endpoint used by the replacement table. -/
def prefixUpper : Nat := 199330

/-- Inclusive endpoint of both Abel sums. -/
def indexUpper : Nat := 5000000000

/-- The inactive periodizing denominator. -/
def periodizer : Nat := indexUpper + 1

/-- Fixed integer scale used for both directed upper numerators. -/
def weightScale : Nat := 1000000000000000000

/-- Production signed-increment numerator. -/
def signedTarget : Nat := 324880457633740

/-- Production absolute square-root-weighted numerator. -/
def absoluteTarget : Nat := 48710223109607260068028

/-- `S_K = sum_(1 <= d <= K) mu(d)/d`, exactly as a real finite sum. -/
noncomputable def mobiusPrefixReciprocal : Real :=
  ∑ d ∈ Finset.Icc 1 prefixUpper,
    (ArithmeticFunction.moebius d : Real) / d

/-- Denominator support of the repository replacement table. -/
def support : Finset Nat := Finset.Icc 1 prefixUpper ∪ {periodizer}

/-- Prefix coefficients and the single affine-cancelling periodizer. -/
noncomputable def coefficient (d : Nat) : Real :=
  if d = periodizer then
    -(periodizer : Real) * mobiusPrefixReciprocal
  else
    (ArithmeticFunction.moebius d : Real)

/-- Every support label is its real denominator. -/
noncomputable def denominator (d : Nat) : Real := d

/-- The finite CDEM floor sum used by the source claim. -/
noncomputable def floorSum (y : Real) : Real :=
  ∑ d ∈ support,
    coefficient d * (⌊y / denominator d⌋₊ : Real)

/-- The source convention overrides the otherwise nonzero value at index 0. -/
noncomputable def errorSequence (k : Nat) : Real :=
  if k = 0 then 0 else |1 - floorSum k|

/-- Signed pre-endpoint Abel increment appearing in the live source atom. -/
noncomputable def signedIncrement : Real :=
  ∑ k ∈ Finset.Icc 1 indexUpper,
    (errorSequence k - errorSequence (k - 1)) / (k : Real)

/-- Absolute square-root-weighted pre-endpoint Abel increment appearing in
the live source atom. -/
noncomputable def absoluteIncrement : Real :=
  ∑ k ∈ Finset.Icc 1 indexUpper,
    |errorSequence k - errorSequence (k - 1)| / Real.sqrt k

/-- Strong integer-scaled output meaning used by the registered algorithm.

This is not a caller-provided proposition.  Both real sums and their scale are
the closed definitions above; the returned naturals are only their directed
upper numerators. -/
def ScaledOutputClaim (signedNumerator absoluteNumerator : Nat) : Prop :=
  (weightScale : Real) * signedIncrement ≤ signedNumerator ∧
  (weightScale : Real) * absoluteIncrement ≤ absoluteNumerator

/-- Exact two-conjunct proposition trusted by the current `claude_math`
source atom, with no endpoint term or downstream weakening. -/
def SourceClaim : Prop :=
  signedIncrement ≤ (signedTarget : Real) / weightScale ∧
  absoluteIncrement ≤ (absoluteTarget : Real) / weightScale

/-- The production scaled numerators imply the exact source-shaped claim. -/
theorem sourceClaim_of_scaledOutput
    (h : ScaledOutputClaim signedTarget absoluteTarget) : SourceClaim := by
  rcases h with ⟨hsigned, habsolute⟩
  constructor
  · apply (le_div_iff₀
      (by norm_num [weightScale] : (0 : Real) < weightScale)).2
    simpa [mul_comm] using hsigned
  · apply (le_div_iff₀
      (by norm_num [weightScale] : (0 : Real) < weightScale)).2
    simpa [mul_comm] using habsolute

/-- Conversely, the source-shaped claim is exactly the production scaled
claim.  This makes the bridge suitable for a downstream definition-by-
definition comparison rather than a merely one-way numerical weakening. -/
theorem scaledOutput_iff_sourceClaim :
    ScaledOutputClaim signedTarget absoluteTarget ↔ SourceClaim := by
  constructor
  · exact sourceClaim_of_scaledOutput
  · intro h
    rcases h with ⟨hsigned, habsolute⟩
    constructor
    · simpa [mul_comm] using (le_div_iff₀
        (by norm_num [weightScale] : (0 : Real) < weightScale)).1 hsigned
    · simpa [mul_comm] using (le_div_iff₀
        (by norm_num [weightScale] : (0 : Real) < weightScale)).1 habsolute

/-- The output relation is non-vacuous independently of the production
numerators: every pair of finite real sums has some natural scaled upper
numerators.  This prevents the sole execution axiom from becoming explosive
merely because a registered relation was accidentally defined as `False`. -/
theorem exists_scaledOutputClaim :
    ∃ signedNumerator absoluteNumerator : Nat,
      ScaledOutputClaim signedNumerator absoluteNumerator := by
  obtain ⟨signedNumerator, hsigned⟩ :=
    exists_nat_ge ((weightScale : Real) * signedIncrement)
  obtain ⟨absoluteNumerator, habsolute⟩ :=
    exists_nat_ge ((weightScale : Real) * absoluteIncrement)
  exact ⟨signedNumerator, absoluteNumerator, hsigned, habsolute⟩

end SparkInterval.TernaryGoldbach.CDEMAbelSource
