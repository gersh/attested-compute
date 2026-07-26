/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.SignQuadrantIntervalMul

set_option autoImplicit false

namespace SparkInterval.Tests.SignQuadrantIntervalMul

open SparkInterval

example (X Y : RealInterval) :
    RealInterval.signQuadrantMul X Y = X.mul Y :=
  RealInterval.signQuadrantMul_eq_mul X Y

example {X Y : RealInterval} {x y : ℝ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (RealInterval.signQuadrantMul X Y).Contains (x * y) :=
  RealInterval.signQuadrantMul_contains hx hy

example
    (roundDown roundUp : ℝ → ℝ)
    (hdown : ∀ value, roundDown value ≤ value)
    (hup : ∀ value, value ≤ roundUp value)
    {X Y : RealInterval} {x y : ℝ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (RealInterval.directedSignQuadrantMul
      roundDown roundUp hdown hup X Y).Contains (x * y) :=
  RealInterval.directedSignQuadrantMul_contains
    roundDown roundUp hdown hup hx hy

#print axioms RealInterval.signQuadrantMulLo_eq_mul_lo
#print axioms RealInterval.signQuadrantMulHi_eq_mul_hi
#print axioms RealInterval.signQuadrantMul_eq_mul
#print axioms RealInterval.signQuadrantMul_contains
#print axioms RealInterval.directedSignQuadrantMulLo_le
#print axioms RealInterval.le_directedSignQuadrantMulHi
#print axioms RealInterval.directedSignQuadrantMul_contains

end SparkInterval.Tests.SignQuadrantIntervalMul
