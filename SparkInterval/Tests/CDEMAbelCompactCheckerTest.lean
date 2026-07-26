/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.CDEMAbelCompactChecker

/-!
The CDEM compact handoff is an ordinary theorem.  These declarations are
kept as an axiom audit without constructing or replaying a production scan.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.CDEMAbelCompactChecker

open SparkInterval.TernaryGoldbach

#print axioms CDEMAbelCompactChecker.sourceClaim_of_acceptance
#print axioms CDEMAbelCompactChecker.acceptanceImpliesSourceClaim
#print axioms CDEMAbelCompactChecker.sourceClaim_of_compactRun

end SparkInterval.Tests.CDEMAbelCompactChecker
