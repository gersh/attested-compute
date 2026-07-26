/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.DirectedComplexInterval
import SparkInterval.Dirichlet.FactoredSmallQDFT

/-!
# Directed-interval recurrence for radix-2 DFT roots

Within one FFT stage the positive twiddles are consecutive powers of a single
root:

```
r 0       = 1
r (j + 1) = r j * r 1.
```

This module proves the exact identity and the corresponding abstract
directed-interval recurrence, including restart from an arbitrary certified
anchor.  A producer can therefore replace one transcendental call per
twiddle with periodic anchors and one directed complex multiplication per
intermediate entry.

Concrete MPFR arithmetic, binary64 conversion, compiler output, and physical
execution remain separate refinement obligations.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.DFTRootRecurrence

open SparkInterval
open SparkInterval.Dirichlet.FactoredSmallQDFT

theorem unitRoot_succ
    {order : Nat} (_horder : 0 < order) (exponent : Nat) :
    unitRoot order (exponent + 1) =
      unitRoot order exponent * unitRoot order 1 := by
  exact unitRoot_add order exponent 1

/-- One directed interval update by the fixed stage root. -/
noncomputable def directedNext
    (rounding : DirectedRound)
    (unitStep current : ComplexInterval) : ComplexInterval :=
  ComplexInterval.directedMul rounding current unitStep

theorem directedNext_contains
    (rounding : DirectedRound)
    {unitStep current : ComplexInterval}
    {exactStep exactCurrent : ℂ}
    (hstep : unitStep.Contains exactStep)
    (hcurrent : current.Contains exactCurrent) :
    (directedNext rounding unitStep current).Contains
      (exactCurrent * exactStep) := by
  exact ComplexInterval.directedMul_contains rounding hcurrent hstep

/-- Iterate the same directed stage-root multiplication. -/
noncomputable def runDirected
    (rounding : DirectedRound) (unitStep : ComplexInterval) :
    Nat → ComplexInterval → ComplexInterval
  | 0, current => current
  | count + 1, current =>
      directedNext rounding unitStep
        (runDirected rounding unitStep count current)

/-- A recurrence block may restart from any independently certified twiddle.
Every later interval in the block contains the corresponding exact DFT
root. -/
theorem runDirected_from_contains
    (rounding : DirectedRound)
    {order start : Nat}
    {unitStep initial : ComplexInterval}
    (horder : 0 < order)
    (hstep : unitStep.Contains (unitRoot order 1))
    (hinitial : initial.Contains (unitRoot order start)) :
    ∀ count : Nat,
      (runDirected rounding unitStep count initial).Contains
        (unitRoot order (start + count))
  | 0 => by
      simpa [runDirected] using hinitial
  | count + 1 => by
      have hprevious :=
        runDirected_from_contains rounding horder hstep hinitial count
      have hnext :=
        directedNext_contains rounding hstep hprevious
      have hindex :
          start + (count + 1) = (start + count) + 1 := by omega
      rw [hindex, unitRoot_succ horder]
      simpa [runDirected] using hnext

/-- Initializing at the exact root `1` proves the ordinary stage table. -/
theorem runDirected_contains
    (rounding : DirectedRound)
    {order : Nat}
    {unitStep initial : ComplexInterval}
    (horder : 0 < order)
    (hstep : unitStep.Contains (unitRoot order 1))
    (hinitial : initial.Contains (unitRoot order 0))
    (exponent : Nat) :
    (runDirected rounding unitStep exponent initial).Contains
      (unitRoot order exponent) := by
  simpa using
    (runDirected_from_contains rounding
      (start := 0) horder hstep hinitial exponent)

end SparkInterval.Dirichlet.DFTRootRecurrence
