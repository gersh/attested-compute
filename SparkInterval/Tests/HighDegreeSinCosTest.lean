/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.HighDegreeSinCos

set_option autoImplicit false

namespace SparkInterval.Tests.HighDegreeSinCos

open SparkInterval.Certificate
open SparkInterval.Certified

example (x : ℚ) :
    (sinCosTaylorState x 14).cosine = cosTaylorSumQ 14 x :=
  cosTaylorQ_eq_sum 14 x

example {x : ℚ} (hx : |x| ≤ 2 ^ 4) :
    (sinCosTaylorSmall 14 4 160 x).1.ContainsReal (Real.sin (x : ℝ)) ∧
    (sinCosTaylorSmall 14 4 160 x).2.ContainsReal (Real.cos (x : ℝ)) :=
  sinCosTaylorSmall_containsReal (by norm_num) 4 160 hx

#guard
  (sinCosTaylorInterval 14 4 160
    ⟨314159265358979323846 / 10 ^ 20,
      314159265358979323847 / 10 ^ 20⟩).isSome

#guard
  (sinCosTaylorBoundedInterval 13 9 192
    ⟨314159265358979323846 / 10 ^ 20,
      314159265358979323847 / 10 ^ 20⟩).isSome

#print axioms imaginaryPowerQ_toComplex
#print axioms sinCosTaylorState_spec
#print axioms sinCosTaylorBase_containsReal
#print axioms sinCosTaylorInterval_containsReal
#print axioms sinCosTaylorBoundedInterval_containsReal

end SparkInterval.Tests.HighDegreeSinCos
