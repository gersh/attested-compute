/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.DirectedComplexInterval
import SparkInterval.Dirichlet.BluesteinDFT

/-!
# Exact and directed-interval Bluestein chirp recurrence

Generating every chirp entry with an independent transcendental call is a
large source-scale preparation cost.  The identities

```
c n     = exp (π i n² / N)
d n     = exp (π i (2n+1) / N)
c (n+1) = c n * d n
d (n+1) = d n * exp (2π i / N)
```

replace that work by two complex multiplications per entry after two initial
roots have been enclosed.  This file proves both the exact recurrence and an
abstract directed-interval implementation.

The theorem is deliberately independent of a reset cadence: a producer may
restart from a fresh certified anchor whenever accumulated interval width
reaches its policy limit.  Choosing and benchmarking that cadence, and
refining concrete fixed-point/CUDA instructions to the abstract directed
operations, remain separate obligations.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.BluesteinChirpRecurrence

open SparkInterval
open SparkInterval.Dirichlet.BluesteinDFT

theorem halfRoot_zero (order : Nat) :
    halfRoot order 0 = 1 := by
  simp [halfRoot]

theorem halfRoot_add (order : Nat) (a b : Int) :
    halfRoot order (a + b) =
      halfRoot order a * halfRoot order b := by
  rw [halfRoot, halfRoot, halfRoot, ← Complex.exp_add]
  congr 1
  push_cast
  ring

theorem halfRoot_two_mul (order : Nat) (a : Int) :
    halfRoot order (2 * a) = signedUnitRoot order a := by
  unfold halfRoot signedUnitRoot
  congr 1
  push_cast
  ring

/-- Exact two-value recurrence state: current chirp and odd phase step. -/
structure ExactState where
  chirp : ℂ
  oddStep : ℂ

noncomputable def exactInitial (order : Nat) : ExactState where
  chirp := halfRoot order 0
  oddStep := halfRoot order 1

noncomputable def exactNext (order : Nat) (state : ExactState) : ExactState where
  chirp := state.chirp * state.oddStep
  oddStep := state.oddStep * signedUnitRoot order 1

noncomputable def exactStateAt (order : Nat) : Nat → ExactState
  | 0 => exactInitial order
  | n + 1 => exactNext order (exactStateAt order n)

theorem exactStateAt_spec (order : Nat) :
    ∀ n : Nat,
      (exactStateAt order n).chirp =
          halfRoot order ((n : Int) ^ 2) ∧
        (exactStateAt order n).oddStep =
          halfRoot order (2 * (n : Int) + 1)
  | 0 => by
      simp [exactStateAt, exactInitial]
  | n + 1 => by
      rcases exactStateAt_spec order n with ⟨hchirp, hstep⟩
      constructor
      · rw [exactStateAt, exactNext, hchirp, hstep, ← halfRoot_add]
        push_cast
        ring_nf
      · rw [exactStateAt, exactNext, hstep,
          ← halfRoot_two_mul order 1, ← halfRoot_add]
        congr 2

theorem exactStateAt_chirp (order n : Nat) :
    (exactStateAt order n).chirp =
      halfRoot order ((n : Int) ^ 2) :=
  (exactStateAt_spec order n).1

/-- Rectangular enclosure state for the same recurrence. -/
structure IntervalState where
  chirp : ComplexInterval
  oddStep : ComplexInterval

def StateContains (intervals : IntervalState) (exact : ExactState) : Prop :=
  intervals.chirp.Contains exact.chirp ∧
    intervals.oddStep.Contains exact.oddStep

noncomputable def directedNext
    (rounding : DirectedRound)
    (unitStep : ComplexInterval)
    (state : IntervalState) : IntervalState where
  chirp :=
    ComplexInterval.directedMul rounding state.chirp state.oddStep
  oddStep :=
    ComplexInterval.directedMul rounding state.oddStep unitStep

theorem directedNext_contains
    (rounding : DirectedRound)
    {unitStep : ComplexInterval} {exactUnitStep : ℂ}
    {intervals : IntervalState} {exact : ExactState}
    (hunit : unitStep.Contains exactUnitStep)
    (hstate : StateContains intervals exact) :
    StateContains
      (directedNext rounding unitStep intervals)
      { chirp := exact.chirp * exact.oddStep
        oddStep := exact.oddStep * exactUnitStep } := by
  exact
    ⟨ComplexInterval.directedMul_contains rounding hstate.1 hstate.2,
      ComplexInterval.directedMul_contains rounding hstate.2 hunit⟩

noncomputable def runDirected
    (rounding : DirectedRound)
    (unitStep : ComplexInterval) :
    Nat → IntervalState → IntervalState
  | 0, state => state
  | n + 1, state =>
      directedNext rounding unitStep
        (runDirected rounding unitStep n state)

theorem runDirected_contains
    (rounding : DirectedRound)
    {order : Nat}
    {unitStep : ComplexInterval}
    {initial : IntervalState}
    (hunit : unitStep.Contains (signedUnitRoot order 1))
    (hinitial : StateContains initial (exactInitial order)) :
    ∀ n : Nat,
      StateContains
        (runDirected rounding unitStep n initial)
        (exactStateAt order n)
  | 0 => by
      simpa [runDirected, exactStateAt] using hinitial
  | n + 1 => by
      have hprevious :=
        runDirected_contains rounding hunit hinitial n
      simpa [runDirected, exactStateAt, exactNext] using
        directedNext_contains rounding hunit hprevious

/-- The same induction can restart at an arbitrary certified index.  This is
the theorem used by a bounded-width block implementation. -/
theorem runDirected_from_contains
    (rounding : DirectedRound)
    {order start : Nat}
    {unitStep : ComplexInterval}
    {initial : IntervalState}
    (hunit : unitStep.Contains (signedUnitRoot order 1))
    (hinitial : StateContains initial (exactStateAt order start)) :
    ∀ count : Nat,
      StateContains
        (runDirected rounding unitStep count initial)
        (exactStateAt order (start + count))
  | 0 => by
      simpa [runDirected] using hinitial
  | count + 1 => by
      have hprevious :=
        runDirected_from_contains rounding hunit hinitial count
      have hnext :=
        directedNext_contains rounding hunit hprevious
      have hindex :
          start + (count + 1) = (start + count) + 1 := by omega
      rw [hindex, exactStateAt]
      simpa [runDirected, exactNext] using hnext

/-- Arbitrary-anchor chirp enclosure, suitable for a periodic reset policy. -/
theorem runDirected_from_chirp_contains
    (rounding : DirectedRound)
    {order start count : Nat}
    {unitStep : ComplexInterval}
    {initial : IntervalState}
    (hunit : unitStep.Contains (signedUnitRoot order 1))
    (hinitial : StateContains initial (exactStateAt order start)) :
    (runDirected rounding unitStep count initial).chirp.Contains
      (halfRoot order (((start + count : Nat) : Int) ^ 2)) := by
  have hstate :=
    (runDirected_from_contains rounding hunit hinitial count).1
  rwa [exactStateAt_chirp] at hstate

/-- Main chirp-enclosure result.  A producer needs only enclosing initial
`c₀`, initial odd step `d₀`, and the constant update root. -/
theorem runDirected_chirp_contains
    (rounding : DirectedRound)
    {order n : Nat}
    {unitStep : ComplexInterval}
    {initial : IntervalState}
    (hunit : unitStep.Contains (signedUnitRoot order 1))
    (hinitial : StateContains initial (exactInitial order)) :
    (runDirected rounding unitStep n initial).chirp.Contains
      (halfRoot order ((n : Int) ^ 2)) := by
  have hstate := (runDirected_contains rounding hunit hinitial n).1
  rwa [exactStateAt_chirp] at hstate

end SparkInterval.Dirichlet.BluesteinChirpRecurrence
