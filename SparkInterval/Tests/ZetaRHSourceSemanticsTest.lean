/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics

namespace SparkInterval.Tests.ZetaRHSourceSemanticsTest

open SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics

example (evidence : SourceEvidence) : SourceClaim :=
  sourceClaim_of_evidence evidence

#print axioms sourceClaim_of_evidence

end SparkInterval.Tests.ZetaRHSourceSemanticsTest
