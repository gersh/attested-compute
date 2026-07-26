/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PT21PrecisionHull
import Mathlib.Tactic.NormNum

set_option autoImplicit false

namespace SparkInterval.Tests.PT21PrecisionHullTest

open SparkInterval.Zeta.PT21PrecisionHull

/-- Two rigorous enclosures can overlap without either containing the other;
their hull remains rigorous. -/
example :
    (hull (⟨0, 3⟩ : ClosedInterval ℚ)
      (⟨1, 4⟩ : ClosedInterval ℚ)).Contains 2 := by
  exact contains_hull_of_both
    (first := (⟨0, 3⟩ : ClosedInterval ℚ))
    (second := (⟨1, 4⟩ : ClosedInterval ℚ))
    (by norm_num [ClosedInterval.Contains])
    (by norm_num [ClosedInterval.Contains])

/-- Strict sign is checked after widening, so it applies to every enclosed
source value. -/
example :
    (0 : ℚ) < 5 / 2 := by
  apply positive_of_hull_contains
    (first := (⟨1, 3⟩ : ClosedInterval ℚ))
    (second := (⟨2, 4⟩ : ClosedInterval ℚ))
  · norm_num [hull, ClosedInterval.Contains]
  · norm_num [hull, StrictlyPositive]

#print axioms SparkInterval.Zeta.PT21PrecisionHull.contains_hull_of_both
#print axioms SparkInterval.Zeta.PT21PrecisionHull.positive_of_hull_contains

end SparkInterval.Tests.PT21PrecisionHullTest
