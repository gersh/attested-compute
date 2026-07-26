/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.Factor8Postprocess

/-!
# Exact conductor phase on the completed-L source grid

For the completed function, the conductor factor contains
`(q / π)^((s + a) / 2)`. On the critical line its varying exponent is
therefore half the source `t` coordinate. This module records that factor of
one half over exact rationals. It is intentionally separate from
`TMajorFactorRecurrence`, whose experimental recurrence is for the full
`q⁻ˢ` factor and therefore advances by the full source step.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.CompletedConductorPhase

/-- Exact exponent increment in the completed-function conductor phase. -/
def exponentStep : ℚ :=
  Factor8Postprocess.sourceStep / 2

/-- Exact conductor-phase exponent coordinate after `sampleOffset` source
samples, relative to a caller-supplied initial exponent. -/
def exponentAt (initial : ℚ) (sampleOffset : ℕ) : ℚ :=
  initial + (sampleOffset : ℚ) * exponentStep

/-- Exact varying conductor exponent at one global source-grid index. -/
def sourceExponentAt (tIndex : ℕ) : ℚ :=
  (tIndex : ℚ) * exponentStep

/-- On the source `5/64` lattice the completed conductor exponent advances by
exactly `5/128`. -/
theorem exponentStep_eq : exponentStep = 5 / 128 := by
  norm_num [exponentStep, Factor8Postprocess.sourceStep]

/-- Moving from one source sample to the next applies exactly one completed
conductor phase step. -/
theorem exponentAt_succ (initial : ℚ) (sampleOffset : ℕ) :
    exponentAt initial (sampleOffset + 1) =
      exponentAt initial sampleOffset + exponentStep := by
  simp only [exponentAt, Nat.cast_add, Nat.cast_one]
  ring

/-- Starting a local recurrence at a global source index preserves the exact
global coordinate. This is the arithmetic used by the Arb checkpoint
producer. -/
theorem exponentAt_sourceExponentAt
    (firstTIndex sampleOffset : ℕ) :
    exponentAt (sourceExponentAt firstTIndex) sampleOffset =
      sourceExponentAt (firstTIndex + sampleOffset) := by
  simp only [exponentAt, sourceExponentAt, Nat.cast_add]
  ring

/-- Expanded form of the source-index exponent used in an Arb checkpoint. -/
theorem sourceExponentAt_eq (tIndex : ℕ) :
    sourceExponentAt tIndex = (5 * tIndex : ℚ) / 128 := by
  rw [sourceExponentAt, exponentStep_eq]
  ring

/-- Applying the completed conductor phase step twice per source sample has
the wrong exact exponent increment. -/
theorem doubledExponentStep_ne :
    2 * exponentStep ≠ exponentStep := by
  norm_num [exponentStep, Factor8Postprocess.sourceStep]

end SparkInterval.Dirichlet.CompletedConductorPhase
