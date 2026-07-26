/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CompletedConductorPhase

set_option autoImplicit false

namespace SparkInterval.Tests.CompletedConductorPhase

open SparkInterval.Dirichlet.CompletedConductorPhase

example : exponentStep = 5 / 128 :=
  exponentStep_eq

example :
    exponentAt (3 / 7) 11 =
      3 / 7 + (11 : ℚ) * (5 / 128) := by
  norm_num [exponentAt, exponentStep_eq]

example :
    exponentAt (3 / 7) 12 =
      exponentAt (3 / 7) 11 + exponentStep := by
  simpa using exponentAt_succ (3 / 7) 11

example : 2 * exponentStep ≠ exponentStep :=
  doubledExponentStep_ne

example :
    exponentAt (sourceExponentAt 123_892) 4095 =
      sourceExponentAt (123_892 + 4095) :=
  exponentAt_sourceExponentAt 123_892 4095

example :
    sourceExponentAt 123_892 = (5 * 123_892 : ℚ) / 128 :=
  sourceExponentAt_eq 123_892

#print axioms exponentStep_eq
#print axioms exponentAt_succ
#print axioms exponentAt_sourceExponentAt
#print axioms sourceExponentAt_eq
#print axioms doubledExponentStep_ne

end SparkInterval.Tests.CompletedConductorPhase
