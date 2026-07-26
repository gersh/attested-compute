/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.PhaseSignFold

set_option autoImplicit false

namespace SparkInterval.Tests.PhaseSignFoldTest

open SparkInterval.Dirichlet
open PhaseSignState
open PhaseSignFold

example :
    summarize
        [some false, none, some true, some true, none, some false] =
      { sampleCount := 6
        ambiguityCount := 2
        firstDeterminate := some false
        lastDeterminate := some false
        transitionCount := 2 } := by
  rfl

example :
    decisionTransitionCount
        [some false, none, some true, some true, none, some false] =
      strictTransitionCount [false, true, true, false] := by
  exact decisionTransitionCount_eq_filtered _

example :
    summarize
        ([some false, none, some true] ++
          [some true, none, some false]) =
      State.combine
        (summarize [some false, none, some true])
        (summarize [some true, none, some false]) := by
  exact summarize_append _ _

example :
    PhaseSignFold.Ambiguity.maximalRangeCount
        [true, true, false, true, false, false, true] = 3 := by
  rfl

example :
    (PhaseSignFold.Ambiguity.summarize
        [true, true, false, true, false, false, true]).rangeCount = 3 := by
  rfl

example :
    PhaseSignFold.Ambiguity.summarize
        ([true, true, false] ++ [true, false, false, true]) =
      AmbiguityRunState.combine
        (PhaseSignFold.Ambiguity.summarize [true, true, false])
        (PhaseSignFold.Ambiguity.summarize
          [true, false, false, true]) := by
  exact PhaseSignFold.Ambiguity.summarize_append _ _

end SparkInterval.Tests.PhaseSignFoldTest
