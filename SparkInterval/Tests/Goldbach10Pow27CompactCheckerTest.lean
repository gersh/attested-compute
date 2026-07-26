/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Goldbach10Pow27CompactChecker

/-! Axiom audit for the lowered finite-Goldbach compact adapter. -/

set_option autoImplicit false

namespace SparkInterval.Tests.Goldbach10Pow27CompactChecker

open SparkInterval.TernaryGoldbach

#print axioms Goldbach10Pow27CompactChecker.sourceClaim_of_acceptance
#print axioms Goldbach10Pow27CompactChecker.acceptanceImpliesSourceClaim
#print axioms Goldbach10Pow27CompactChecker.sourceClaim_of_compactRun

end SparkInterval.Tests.Goldbach10Pow27CompactChecker
