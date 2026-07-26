/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Prop1224SourceSemantics

set_option autoImplicit false

namespace SparkInterval.Tests.Prop1224SourceSemanticsTest

open SparkInterval.TernaryGoldbach.Prop1224SourceSemantics

example : qAtRank 0 = 1 := by
  norm_num [qAtRank, denseRankEnd]

example : qAtRank (denseRankEnd - 1) = 3_299_999_999 := by
  norm_num [qAtRank, denseRankEnd]

example : qAtRank denseRankEnd = firstExtensionQ := by
  norm_num [qAtRank, denseRankEnd, firstExtensionQ]

example : qAtRank (sourceRankCount - 1) = 21_999_999_840 := by
  norm_num [qAtRank, denseRankEnd, firstExtensionQ, extensionDivisor,
    sourceRankCount]

private def fullSingleShard : Certificate := {
  sourceLower := 0
  sourceUpper := sourceRankCount
  shards := [{ lower := 0, upper := sourceRankCount }]
}

example : fullSingleShard.check = true := by
  native_decide

#print axioms citeRange_has_rank
#print axioms Certificate.checker_sound
#print axioms sourceClaim_of_checked_certificate

end SparkInterval.Tests.Prop1224SourceSemanticsTest
