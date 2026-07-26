/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.DirectedIntervalFFT

set_option autoImplicit false

namespace SparkInterval.Tests.DirectedIntervalFFTTest

open SparkInterval
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.DirectedIntervalFFT

/-- Exact real arithmetic is a satisfiable instance of the abstract directed
rounding interface. -/
noncomputable def exactRounding : DirectedRound where
  down := id
  up := id
  down_le := by simp
  le_up := by simp

noncomputable def pointState {logLength : Nat}
    (state : ExactState logLength) : IntervalState logLength :=
  ⟨fun index => ComplexInterval.point (state.value index)⟩

noncomputable def pointTwiddles
    (twiddles : Nat → Nat → ℂ) : Nat → Nat → ComplexInterval :=
  fun stage offset => ComplexInterval.point (twiddles stage offset)

theorem pointState_contains {logLength : Nat}
    (state : ExactState logLength) :
    StateContains (pointState state) state := by
  intro index
  exact ComplexInterval.point_contains _

theorem pointTwiddles_contain {logLength : Nat}
    (twiddles : Nat → Nat → ℂ) :
    TwiddlesContain (logLength := logLength)
      (pointTwiddles twiddles) twiddles := by
  intro stage _ offset _
  exact ComplexInterval.point_contains _

/-- Symbolic one-butterfly specialization. -/
example (rounding : DirectedRound)
    {leftBox rightBox twiddleBox : ComplexInterval}
    {left right twiddle : ℂ}
    (hleft : leftBox.Contains left)
    (hright : rightBox.Contains right)
    (htwiddle : twiddleBox.Contains twiddle) :
    (directedButterfly rounding leftBox rightBox twiddleBox).left.Contains
        (ButterflyCertificate.exactLeft left right twiddle) ∧
      (directedButterfly rounding leftBox rightBox twiddleBox).right.Contains
        (ButterflyCertificate.exactRight left right twiddle) :=
  directedButterfly_contains rounding hleft hright htwiddle

/-- A bounded middle suffix of the length-eight graph. -/
example (rounding : DirectedRound)
    (twiddleBoxes : Nat → Nat → ComplexInterval)
    (twiddles : Nat → Nat → ℂ)
    (current : IntervalState 3)
    (exact : ExactState 3)
    (hcurrent : StateContains current exact)
    (htwiddles : TwiddlesContain (logLength := 3)
      twiddleBoxes twiddles) :
    StateContains
      (runDirectedStages rounding twiddleBoxes 2 1 current)
      (runExactStages twiddles 2 1 exact) :=
  runDirectedStages_contains rounding (by omega) hcurrent htwiddles

/-- The complete length-eight positive transform is a non-vacuous instance:
singleton input and twiddle rectangles satisfy every visible premise. -/
example (source : ExactState 3) :
    StateContains
      (directedPositiveRadix2Transform exactRounding
        (pointTwiddles positiveTwiddle)
        (pointState (bitReversed source)))
      (positiveRadix2Transform source) :=
  directedPositiveRadix2Transform_contains exactRounding
    (pointState_contains _) (pointTwiddles_contain _)

/-- The interval result composes transparently with the separate pure
radix-2/direct-DFT algebra theorem. -/
example (source : ExactState 3)
    (hRadix2 : Radix2CorrectFor source) :
    ∀ frequency,
      ((directedPositiveRadix2Transform exactRounding
        (pointTwiddles positiveTwiddle)
        (pointState (bitReversed source))).value frequency).Contains
        (positiveDFT source frequency) :=
  directedPositiveRadix2Transform_contains_positiveDFT exactRounding
    (pointState_contains _) (pointTwiddles_contain _) hRadix2

#print axioms directedButterfly_contains
#print axioms directedStage_contains_exactStage
#print axioms runDirectedStages_contains
#print axioms directedPositiveRadix2Transform_contains
#print axioms directedPositiveRadix2Transform_contains_positiveDFT

end SparkInterval.Tests.DirectedIntervalFFTTest
