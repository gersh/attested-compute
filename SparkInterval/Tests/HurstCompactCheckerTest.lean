/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.HurstCompactChecker

/-!
The compact Hurst handoff is ordinary Lean glue.  This audit does not
construct or replay a source-scale certificate.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.HurstCompactChecker

open SparkInterval.TernaryGoldbach

#print axioms HurstCompactChecker.realClaims_of_acceptance
#print axioms HurstCompactChecker.acceptanceImpliesRealClaims
#print axioms HurstCompactChecker.realClaims_of_compactRun

end SparkInterval.Tests.HurstCompactChecker
