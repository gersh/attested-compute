/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Goldbach10Pow27SourceSemantics

namespace SparkInterval.Tests.Goldbach10Pow27SourceSemanticsTest

open SparkInterval.TernaryGoldbach.Goldbach10Pow27SourceSemantics

example (evidence : CheckedSourceEvidence) : SourceClaim :=
  sourceClaim_of_checked_evidence evidence

#print axioms scheduledEndpoint_eq_range_product
#print axioms sourceLimit_le_scheduledEndpoint
#print axioms PrimeLadder.valid_of_arithmeticValid
#print axioms sourceClaim_of_binary_and_ladder
#print axioms sourceClaim_of_checked_evidence

end SparkInterval.Tests.Goldbach10Pow27SourceSemanticsTest
