/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics

namespace SparkInterval.Tests.ZetaHeadSourceSemanticsTest

open SparkInterval.TernaryGoldbach.ZetaHeadSourceSemantics

example {table : CellTable} (evidence : CheckedHeadEvidence table) :
    SourceClaim table :=
  sourceClaim_of_checked_head_evidence evidence

example {table : Q128CellTable} {commitment : String}
    (evidence : CheckedQ128HeadEvidence table commitment) :
    Q128SourceClaim table :=
  q128SourceClaim_of_checked_evidence evidence

#print axioms sourceBand_finite
#print axioms sourceBand_multiplicity_pos
#print axioms sourceClaim_of_checked_head_evidence
#print axioms Q128Cell.lower_cast_toCell
#print axioms Q128Cell.upper_cast_toCell
#print axioms q128SourceClaim_of_checked_evidence

end SparkInterval.Tests.ZetaHeadSourceSemanticsTest
