/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachCompactChecker

/-!
The compact Helfgott--Platt handoff is ordinary Lean glue.  This audit does
not construct or replay either production branch.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.GoldbachCompactChecker

open SparkInterval.TernaryGoldbach

#print axioms GoldbachCompactChecker.sourceClaim_of_acceptance
#print axioms GoldbachCompactChecker.acceptanceImpliesSourceClaim
#print axioms GoldbachCompactChecker.sourceClaim_of_compactRun

end SparkInterval.Tests.GoldbachCompactChecker
