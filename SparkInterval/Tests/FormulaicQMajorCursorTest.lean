/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FormulaicQMajorCursor

set_option autoImplicit false

namespace SparkInterval.Tests.FormulaicQMajorCursorTest

open SparkInterval.Dirichlet.FormulaicQMajorCursor

example : batchFirst 2 = 128 := by
  norm_num [batchFirst, batchSize]

example : batchStop 129 2 = 129 := by
  norm_num [batchStop, batchFirst, batchSize]

example : InBatch 129 2 128 := by
  norm_num [InBatch, batchFirst, batchStop, batchSize]

example : ¬ InBatch 129 1 128 := by
  norm_num [InBatch, batchFirst, batchStop, batchSize]

example : (129 + (batchSize - 1)) / batchSize = 3 := by
  norm_num [batchSize]

example :
    (canonicalTarget 7 10001 2 129 2).batchCount = 1 := by
  norm_num [canonicalTarget, batchStop, batchFirst, batchSize]

example (rowCount tIndex : ℕ) (h : tIndex < rowCount) :
    InBatch rowCount (tIndex / batchSize) tIndex :=
  member_quotient_batch rowCount tIndex h

example (rowCount firstBatch secondBatch tIndex : ℕ)
    (hfirst : InBatch rowCount firstBatch tIndex)
    (hsecond : InBatch rowCount secondBatch tIndex) :
    firstBatch = secondBatch :=
  batch_unique rowCount firstBatch secondBatch tIndex hfirst hsecond

example (rowCount batchIndex : ℕ) :
    batchStop rowCount batchIndex - batchFirst batchIndex ≤ 64 := by
  simpa [batchSize] using batchCount_le rowCount batchIndex

example (rowCount batchIndex : ℕ) (h : batchIndex < 14) :
    batchStop rowCount batchIndex ≤ 896 := by
  simpa [batchFirst, batchSize] using
    batch_does_not_cross_aligned_lane rowCount batchIndex 14 h

end SparkInterval.Tests.FormulaicQMajorCursorTest
