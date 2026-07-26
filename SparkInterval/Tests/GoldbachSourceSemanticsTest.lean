/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachSourceSemantics

namespace SparkInterval.Tests.GoldbachSourceSemanticsTest

open SparkInterval.TernaryGoldbach.GoldbachSourceSemantics

example (evidence : SourceEvidence) : SourceClaim :=
  sourceClaim_of_evidence evidence

example (evidence : CheckedSourceEvidence) : SourceClaim :=
  sourceClaim_of_checked_evidence evidence

#print axioms sourceLimit_eq_range_product
#print axioms sourceClaim_of_binary_and_ladder
#print axioms sourceClaim_of_evidence
#print axioms PrimeLadder.valid_of_arithmeticValid
#print axioms PrimeLadder.valid_of_check
#print axioms sourceClaim_of_checked_evidence

end SparkInterval.Tests.GoldbachSourceSemanticsTest
