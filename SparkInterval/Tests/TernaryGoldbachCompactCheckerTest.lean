/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.A7BoundaryCompactChecker
import SparkInterval.TernaryGoldbach.PsiCompactChecker
import SparkInterval.TernaryGoldbach.Prop1224CompactChecker
import SparkInterval.TernaryGoldbach.R2StarCompactChecker

/-! Axiom audit for compact checker-to-source-claim adapters. -/

set_option autoImplicit false

#print axioms SparkInterval.TernaryGoldbach.A7BoundaryCompactChecker.sourceClaim_of_compactRun
#print axioms SparkInterval.TernaryGoldbach.PsiCompactChecker.sourceClaim_of_compactRun
#print axioms SparkInterval.TernaryGoldbach.Prop1224CompactChecker.sourceClaim_of_compactRun
#print axioms SparkInterval.TernaryGoldbach.R2StarCompactChecker.sourceClaim_of_compactRun
