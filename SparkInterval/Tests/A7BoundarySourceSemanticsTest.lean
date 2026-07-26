/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics

namespace SparkInterval.Tests.A7BoundarySourceSemanticsTest

open SparkInterval.TernaryGoldbach.A7BoundarySourceSemantics

example (evidence : BoundaryEvidence) : SourceClaim :=
  sourceClaim_of_boundary_evidence evidence

#print axioms RationalComplexBox.norm_le_of_contains_guard
#print axioms sourceClaim_of_boundary_evidence

end SparkInterval.Tests.A7BoundarySourceSemanticsTest
