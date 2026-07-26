/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.DirectedComplexInterval
import SparkInterval.Dirichlet.FactoredSmallQDFT

/-!
# Directed complex-interval radix-2 FFT containment

This module lifts the exact radix-2 stage graph from `FactoredSmallQDFT` to
rectangular complex intervals.  It uses the abstract directed operations from
`DirectedComplexInterval`; consequently the proof needs only the defining
lower/upper enclosure laws of `DirectedRound`.

The graph is intentionally source-shaped:

* the right input is multiplied by the stage twiddle;
* the left output is `left + right * twiddle`;
* the right output is `left - right * twiddle`;
* stage indices, output-side selection, and stage iteration are exactly the
  definitions used by `FactoredSmallQDFT.exactStage`.

The main theorem proves pointwise containment through any bounded suffix of
the staged network.  A corollary covers the complete positive-sign radix-2
transform from a bit-reversed input.

This is a mathematical interval-arithmetic theorem.  It does not claim that
IEEE binary64 or CUDA instructions realize a chosen `DirectedRound`, that a
root generator encloses the exact twiddles, that a flat device-memory trace
implements this graph, or that a compiled program was physically executed.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.DirectedIntervalFFT

open SparkInterval
open SparkInterval.Dirichlet.FactoredSmallQDFT

/-- A rectangular complex-interval line of source-owned power-of-two length. -/
structure IntervalState (logLength : Nat) where
  value : Fin (2 ^ logLength) → ComplexInterval

/-- Pointwise enclosure of an exact complex state. -/
def StateContains {logLength : Nat}
    (intervals : IntervalState logLength)
    (exact : ExactState logLength) : Prop :=
  ∀ index, (intervals.value index).Contains (exact.value index)

/-- The two interval outputs of one directed radix-2 butterfly. -/
structure ButterflyOutput where
  left : ComplexInterval
  right : ComplexInterval

/-- One butterfly in the operation order used by the exact staged graph. -/
noncomputable def directedButterfly
    (rounding : DirectedRound)
    (left right twiddle : ComplexInterval) : ButterflyOutput :=
  let product := ComplexInterval.directedMul rounding right twiddle
  ⟨ComplexInterval.directedAdd rounding left product,
    ComplexInterval.directedSub rounding left product⟩

/-- Abstract directed arithmetic encloses both exact butterfly outputs. -/
theorem directedButterfly_contains
    (rounding : DirectedRound)
    {leftBox rightBox twiddleBox : ComplexInterval}
    {left right twiddle : ℂ}
    (hleft : leftBox.Contains left)
    (hright : rightBox.Contains right)
    (htwiddle : twiddleBox.Contains twiddle) :
    (directedButterfly rounding leftBox rightBox twiddleBox).left.Contains
        (ButterflyCertificate.exactLeft left right twiddle) ∧
      (directedButterfly rounding leftBox rightBox twiddleBox).right.Contains
        (ButterflyCertificate.exactRight left right twiddle) := by
  have hproduct :
      (ComplexInterval.directedMul rounding rightBox twiddleBox).Contains
        (right * twiddle) :=
    ComplexInterval.directedMul_contains rounding hright htwiddle
  constructor
  · simpa [directedButterfly, ButterflyCertificate.exactLeft] using
      (ComplexInterval.directedAdd_contains rounding hleft hproduct)
  · simpa [directedButterfly, ButterflyCertificate.exactRight] using
      (ComplexInterval.directedSub_contains rounding hleft hproduct)

/-- Interval twiddle table encloses an exact table at every stage coordinate
that can be queried by a `logLength`-stage transform. -/
def TwiddlesContain {logLength : Nat}
    (twiddleBoxes : Nat → Nat → ComplexInterval)
    (twiddles : Nat → Nat → ℂ) : Prop :=
  ∀ stage, stage < logLength →
    ∀ offset, offset < halfLength stage →
      (twiddleBoxes stage offset).Contains (twiddles stage offset)

/-- A complete directed interval stage with the same index graph and branch
selection as `FactoredSmallQDFT.exactStage`. -/
noncomputable def directedStage {logLength : Nat}
    (rounding : DirectedRound)
    (expectedStage : Nat)
    (twiddleBoxes : Nat → Nat → ComplexInterval)
    (current : IntervalState logLength) : IntervalState logLength :=
  ⟨fun index =>
    let group := groupAt expectedStage index.val
    let offset := offsetAt expectedStage index.val
    let left := current.value (finIndex logLength
      (scheduledLeft expectedStage group offset))
    let right := current.value (finIndex logLength
      (scheduledRight expectedStage group offset))
    let output := directedButterfly rounding left right
      (twiddleBoxes expectedStage offset)
    if isLeftOutput expectedStage index.val then
      output.left
    else
      output.right⟩

/-- One directed interval stage preserves pointwise enclosure of the exact
stage.  The stage bound is explicit, so the twiddle premise is used only in
its declared transform range. -/
theorem directedStage_contains_exactStage {logLength : Nat}
    (rounding : DirectedRound)
    {expectedStage : Nat}
    {twiddleBoxes : Nat → Nat → ComplexInterval}
    {twiddles : Nat → Nat → ℂ}
    {current : IntervalState logLength}
    {exact : ExactState logLength}
    (hstage : expectedStage < logLength)
    (hcurrent : StateContains current exact)
    (htwiddles : TwiddlesContain (logLength := logLength)
      twiddleBoxes twiddles) :
    StateContains
      (directedStage rounding expectedStage twiddleBoxes current)
      (exactStage expectedStage twiddles exact) := by
  intro index
  have hoffset :
      offsetAt expectedStage index.val < halfLength expectedStage :=
    Nat.mod_lt _ (Nat.pow_pos (by omega))
  have houtputs :=
    directedButterfly_contains rounding
      (hcurrent (finIndex logLength
        (scheduledLeft expectedStage
          (groupAt expectedStage index.val)
          (offsetAt expectedStage index.val))))
      (hcurrent (finIndex logLength
        (scheduledRight expectedStage
          (groupAt expectedStage index.val)
          (offsetAt expectedStage index.val))))
      (htwiddles expectedStage hstage
        (offsetAt expectedStage index.val) hoffset)
  by_cases hside : isLeftOutput expectedStage index.val = true
  · simpa [directedStage, exactStage, hside] using houtputs.1
  · have hfalse : isLeftOutput expectedStage index.val = false :=
      Bool.eq_false_of_not_eq_true hside
    simpa [directedStage, exactStage, hfalse] using houtputs.2

/-- Iterate `count` directed stages beginning at `expectedStage`. -/
noncomputable def runDirectedStages {logLength : Nat}
    (rounding : DirectedRound)
    (twiddleBoxes : Nat → Nat → ComplexInterval) :
    Nat → Nat → IntervalState logLength → IntervalState logLength
  | 0, _, current => current
  | count + 1, expectedStage, current =>
      runDirectedStages rounding twiddleBoxes count (expectedStage + 1)
        (directedStage rounding expectedStage twiddleBoxes current)

/-- Staged induction: every directed butterfly in a bounded stage suffix
preserves pointwise containment of the corresponding exact network. -/
theorem runDirectedStages_contains {logLength : Nat}
    (rounding : DirectedRound)
    {twiddleBoxes : Nat → Nat → ComplexInterval}
    {twiddles : Nat → Nat → ℂ}
    {count expectedStage : Nat}
    {current : IntervalState logLength}
    {exact : ExactState logLength}
    (hbound : expectedStage + count ≤ logLength)
    (hcurrent : StateContains current exact)
    (htwiddles : TwiddlesContain (logLength := logLength)
      twiddleBoxes twiddles) :
    StateContains
      (runDirectedStages rounding twiddleBoxes count expectedStage current)
      (runExactStages twiddles count expectedStage exact) := by
  induction count generalizing expectedStage current exact with
  | zero =>
      simpa [runDirectedStages, runExactStages] using hcurrent
  | succ count ih =>
      have hstage : expectedStage < logLength := by omega
      have hnext :
          StateContains
            (directedStage rounding expectedStage twiddleBoxes current)
            (exactStage expectedStage twiddles exact) :=
        directedStage_contains_exactStage rounding
          hstage hcurrent htwiddles
      have htail :=
        ih (expectedStage := expectedStage + 1)
          (current :=
            directedStage rounding expectedStage twiddleBoxes current)
          (exact := exactStage expectedStage twiddles exact)
          (by omega) hnext
      simpa [runDirectedStages, runExactStages] using htail

/-- Complete positive-sign directed radix-2 network.  Its input is expected
to enclose the source after the exact bit-reversal permutation. -/
noncomputable def directedPositiveRadix2Transform {logLength : Nat}
    (rounding : DirectedRound)
    (twiddleBoxes : Nat → Nat → ComplexInterval)
    (bitReversedInput : IntervalState logLength) : IntervalState logLength :=
  runDirectedStages rounding twiddleBoxes logLength 0 bitReversedInput

/-- The full directed interval network encloses the exact positive-sign
radix-2 transform, conditional only on the visible input and root enclosures. -/
theorem directedPositiveRadix2Transform_contains {logLength : Nat}
    (rounding : DirectedRound)
    {twiddleBoxes : Nat → Nat → ComplexInterval}
    {bitReversedInput : IntervalState logLength}
    {source : ExactState logLength}
    (hinput : StateContains bitReversedInput (bitReversed source))
    (hroots : TwiddlesContain (logLength := logLength)
      twiddleBoxes positiveTwiddle) :
    StateContains
      (directedPositiveRadix2Transform rounding twiddleBoxes
        bitReversedInput)
      (positiveRadix2Transform source) := by
  simpa [directedPositiveRadix2Transform, positiveRadix2Transform] using
    (runDirectedStages_contains (logLength := logLength) rounding
      (twiddleBoxes := twiddleBoxes)
      (twiddles := positiveTwiddle)
      (count := logLength)
      (expectedStage := 0)
      (current := bitReversedInput)
      (exact := bitReversed source)
      (by omega) hinput hroots)

/-- Pointwise direct-DFT corollary.  The pure radix-2 identity is kept as an
explicit premise here so this interval layer remains independent of its
companion algebra proof. -/
theorem directedPositiveRadix2Transform_contains_positiveDFT
    {logLength : Nat}
    (rounding : DirectedRound)
    {twiddleBoxes : Nat → Nat → ComplexInterval}
    {bitReversedInput : IntervalState logLength}
    {source : ExactState logLength}
    (hinput : StateContains bitReversedInput (bitReversed source))
    (hroots : TwiddlesContain (logLength := logLength)
      twiddleBoxes positiveTwiddle)
    (hRadix2 : Radix2CorrectFor source) :
    ∀ frequency,
      ((directedPositiveRadix2Transform rounding twiddleBoxes
        bitReversedInput).value frequency).Contains
        (positiveDFT source frequency) := by
  have htransform :=
    directedPositiveRadix2Transform_contains rounding hinput hroots
  intro frequency
  rw [← hRadix2 frequency]
  exact htransform frequency

end SparkInterval.Dirichlet.DirectedIntervalFFT
