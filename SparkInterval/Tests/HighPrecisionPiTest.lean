/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.HighPrecisionPi

set_option autoImplicit false

namespace SparkInterval.Tests.HighPrecisionPiTest

open SparkInterval.Certificate
open SparkInterval.Certified

example : rootPiInterval.ContainsReal Real.pi :=
  rootPiInterval_containsReal

example : rootTwoPiInterval.ContainsReal (2 * Real.pi) :=
  rootTwoPiInterval_containsReal

#guard
  rootPiInterval.hi - rootPiInterval.lo <
    (1 : ℚ) / 2 ^ 127

#print axioms machinPiInterval_containsReal
#print axioms rootPiInterval_containsReal
#print axioms rootTwoPiInterval_containsReal

end SparkInterval.Tests.HighPrecisionPiTest
