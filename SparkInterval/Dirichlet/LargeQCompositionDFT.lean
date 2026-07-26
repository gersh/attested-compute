/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQDFT

/-!
# Algebraic boundary for large-q residue composition and the DFT

The large-q producer supplies, at each unit residue,

```
q⁻ˢ * ζ_M(s, a / q) + R_M(s; q, a).
```

The finite-recovery term is outside the common `q⁻ˢ` factor.  This module
records the exact linearity available to an optimized implementation.  In
particular, a producer may transform the Taylor and recovery states
separately and combine their transforms, but it may not pull `q⁻ˢ` through a
single transform of their unscaled sum without first rescaling the recovery
state.

These are exact complex-algebra identities.  They make no interval-arithmetic,
FFT-refinement, source-enclosure, or physical-execution claim.
-/

set_option autoImplicit false

open scoped BigOperators

namespace SparkInterval.Dirichlet.LargeQCompositionDFT

open FactoredSmallQDFT

/-- Pointwise sum of two exact transform inputs. -/
noncomputable def addState {logLength : Nat}
    (left right : ExactState logLength) : ExactState logLength :=
  ⟨fun index => left.value index + right.value index⟩

/-- Pointwise multiplication by one common complex scalar. -/
noncomputable def scaleState {logLength : Nat}
    (factor : ℂ) (source : ExactState logLength) : ExactState logLength :=
  ⟨fun index => factor * source.value index⟩

/-- Source-shaped large-q residue composition. -/
noncomputable def composeState {logLength : Nat}
    (qToTheMinusS : ℂ)
    (taylor recovery : ExactState logLength) : ExactState logLength :=
  addState (scaleState qToTheMinusS taylor) recovery

/-- The direct positive-sign DFT is additive. -/
theorem positiveDFT_add {logLength : Nat}
    (left right : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    positiveDFT (addState left right) frequency =
      positiveDFT left frequency + positiveDFT right frequency := by
  simp only [positiveDFT, addState, add_mul, Finset.sum_add_distrib]

/-- A common input scalar can be applied after the direct DFT. -/
theorem positiveDFT_scale {logLength : Nat}
    (factor : ℂ) (source : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    positiveDFT (scaleState factor source) frequency =
      factor * positiveDFT source frequency := by
  simp only [positiveDFT, scaleState, mul_assoc, Finset.mul_sum]

/--
The exact transform of the production composition has two terms.  The
finite-recovery transform is not multiplied by `qToTheMinusS`.
-/
theorem positiveDFT_compose {logLength : Nat}
    (qToTheMinusS : ℂ)
    (taylor recovery : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    positiveDFT (composeState qToTheMinusS taylor recovery) frequency =
      qToTheMinusS * positiveDFT taylor frequency +
        positiveDFT recovery frequency := by
  rw [composeState, positiveDFT_add, positiveDFT_scale]

/--
Pulling the common factor through one transform is valid only after the
recovery input has been multiplied pointwise by its inverse.  This identity
exposes the per-residue work that a deferred-scaling optimization would still
have to perform.
-/
theorem positiveDFT_compose_as_deferred {logLength : Nat}
    (qToTheMinusS : ℂ) (hfactor : qToTheMinusS ≠ 0)
    (taylor recovery : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    positiveDFT (composeState qToTheMinusS taylor recovery) frequency =
      qToTheMinusS *
        positiveDFT
          (addState taylor (scaleState qToTheMinusS⁻¹ recovery))
          frequency := by
  rw [positiveDFT_compose, positiveDFT_add, positiveDFT_scale]
  field_simp

/--
An exact source-range counterexample to the naive rewrite.  At `q = 101²`
and `t = 0`, `q⁻ˢ = 1/101`; taking one Taylor value `2` and one recovery
value `3` distinguishes the production expression from multiplication of the
unscaled sum.  A length-one DFT is the identity, so this counterexample is
independent of Fourier convention.
-/
theorem naive_deferred_counterexample :
    (1 / 101 : ℂ) * 2 + 3 ≠ (1 / 101 : ℂ) * (2 + 3) := by
  norm_num

end SparkInterval.Dirichlet.LargeQCompositionDFT
