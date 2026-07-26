/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.ComplexInterval
import SparkInterval.SignQuadrantIntervalMul

/-!
# Abstract directed-rounding complex intervals

This module mirrors the arithmetic shape used by the large-q Dirichlet CUDA
code while keeping the machine boundary explicit.  A `DirectedRound` supplies
mathematical lower and upper rounding functions together with only their
defining enclosure inequalities.  Real addition, subtraction, and the
production sign-quadrant multiplication are then lifted to rectangular
complex addition, subtraction, and multiplication.

The resulting theorems apply to IEEE binary64 directed operations once a
separate PTX/CUDA refinement proves that those instructions realize the
rounding functions.  No runtime `Float`, FFI, compiler, or hardware fact is
assumed here.
-/

set_option autoImplicit false

namespace SparkInterval

/-- The only properties of directed rounding needed by interval arithmetic. -/
structure DirectedRound where
  down : ℝ → ℝ
  up : ℝ → ℝ
  down_le : ∀ value, down value ≤ value
  le_up : ∀ value, value ≤ up value

namespace RealInterval

noncomputable def directedAdd
    (rounding : DirectedRound) (X Y : RealInterval) : RealInterval where
  lo := rounding.down (X.lo + Y.lo)
  hi := rounding.up (X.hi + Y.hi)
  valid := by
    exact
      (rounding.down_le _).trans
        ((add_le_add X.valid Y.valid).trans (rounding.le_up _))

noncomputable def directedSub
    (rounding : DirectedRound) (X Y : RealInterval) : RealInterval where
  lo := rounding.down (X.lo - Y.hi)
  hi := rounding.up (X.hi - Y.lo)
  valid := by
    exact
      (rounding.down_le _).trans
        ((sub_le_sub X.valid Y.valid).trans (rounding.le_up _))

noncomputable def directedMul
    (rounding : DirectedRound) (X Y : RealInterval) : RealInterval :=
  directedSignQuadrantMul
    rounding.down rounding.up rounding.down_le rounding.le_up X Y

theorem directedAdd_contains
    (rounding : DirectedRound)
    {X Y : RealInterval} {x y : ℝ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (directedAdd rounding X Y).Contains (x + y) := by
  constructor
  · exact
      (rounding.down_le _).trans
        (add_le_add hx.1 hy.1)
  · exact
      (add_le_add hx.2 hy.2).trans
        (rounding.le_up _)

theorem directedSub_contains
    (rounding : DirectedRound)
    {X Y : RealInterval} {x y : ℝ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (directedSub rounding X Y).Contains (x - y) := by
  constructor
  · exact
      (rounding.down_le _).trans
        (sub_le_sub hx.1 hy.2)
  · exact
      (sub_le_sub hx.2 hy.1).trans
        (rounding.le_up _)

theorem directedMul_contains
    (rounding : DirectedRound)
    {X Y : RealInterval} {x y : ℝ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (directedMul rounding X Y).Contains (x * y) := by
  exact
    directedSignQuadrantMul_contains
      rounding.down rounding.up rounding.down_le rounding.le_up hx hy

end RealInterval

namespace ComplexInterval

noncomputable def directedAdd
    (rounding : DirectedRound)
    (X Y : ComplexInterval) : ComplexInterval where
  re := X.re.directedAdd rounding Y.re
  im := X.im.directedAdd rounding Y.im

noncomputable def directedSub
    (rounding : DirectedRound)
    (X Y : ComplexInterval) : ComplexInterval where
  re := X.re.directedSub rounding Y.re
  im := X.im.directedSub rounding Y.im

/-- Production operation order:

`re := sub (mul X.re Y.re) (mul X.im Y.im)`

`im := add (mul X.re Y.im) (mul X.im Y.re)`.
-/
noncomputable def directedMul
    (rounding : DirectedRound)
    (X Y : ComplexInterval) : ComplexInterval where
  re :=
    (X.re.directedMul rounding Y.re).directedSub rounding
      (X.im.directedMul rounding Y.im)
  im :=
    (X.re.directedMul rounding Y.im).directedAdd rounding
      (X.im.directedMul rounding Y.re)

theorem directedAdd_contains
    (rounding : DirectedRound)
    {X Y : ComplexInterval} {x y : ℂ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (directedAdd rounding X Y).Contains (x + y) := by
  exact
    ⟨RealInterval.directedAdd_contains rounding hx.1 hy.1,
      RealInterval.directedAdd_contains rounding hx.2 hy.2⟩

theorem directedSub_contains
    (rounding : DirectedRound)
    {X Y : ComplexInterval} {x y : ℂ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (directedSub rounding X Y).Contains (x - y) := by
  exact
    ⟨RealInterval.directedSub_contains rounding hx.1 hy.1,
      RealInterval.directedSub_contains rounding hx.2 hy.2⟩

theorem directedMul_contains
    (rounding : DirectedRound)
    {X Y : ComplexInterval} {x y : ℂ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (directedMul rounding X Y).Contains (x * y) := by
  constructor
  · exact
      RealInterval.directedSub_contains rounding
        (RealInterval.directedMul_contains rounding hx.1 hy.1)
        (RealInterval.directedMul_contains rounding hx.2 hy.2)
  · exact
      RealInterval.directedAdd_contains rounding
        (RealInterval.directedMul_contains rounding hx.1 hy.2)
        (RealInterval.directedMul_contains rounding hx.2 hy.1)

end ComplexInterval

end SparkInterval
