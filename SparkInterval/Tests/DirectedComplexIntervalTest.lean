/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.DirectedComplexInterval

set_option autoImplicit false

namespace SparkInterval.Tests.DirectedComplexInterval

open SparkInterval

example
    (rounding : DirectedRound)
    {X Y : ComplexInterval} {x y : ℂ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (X.directedAdd rounding Y).Contains (x + y) :=
  ComplexInterval.directedAdd_contains rounding hx hy

example
    (rounding : DirectedRound)
    {X Y : ComplexInterval} {x y : ℂ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (X.directedSub rounding Y).Contains (x - y) :=
  ComplexInterval.directedSub_contains rounding hx hy

example
    (rounding : DirectedRound)
    {X Y : ComplexInterval} {x y : ℂ}
    (hx : X.Contains x) (hy : Y.Contains y) :
    (X.directedMul rounding Y).Contains (x * y) :=
  ComplexInterval.directedMul_contains rounding hx hy

#print axioms RealInterval.directedAdd_contains
#print axioms RealInterval.directedSub_contains
#print axioms RealInterval.directedMul_contains
#print axioms ComplexInterval.directedAdd_contains
#print axioms ComplexInterval.directedSub_contains
#print axioms ComplexInterval.directedMul_contains

end SparkInterval.Tests.DirectedComplexInterval
