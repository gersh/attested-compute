/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.R2StarReplaySegmentation

set_option autoImplicit false

namespace SparkInterval.Tests.R2StarReplaySegmentationTest

open SparkInterval.TernaryGoldbach.R2StarSourceSemantics
open SparkInterval.TernaryGoldbach.R2StarReplaySegmentation

private def a : State := ⟨1, 2⟩
private def b : State := ⟨-3, 5⟩
private def c : State := ⟨7, 11⟩

example :
    foldSegments State.zero [[a, b], [c]] =
      foldRows State.zero [a, b, c] := by
  exact foldSegments_eq_foldRows_flatten _ _

example :
    foldSegments State.zero [[a], [b, c]] =
      foldSegments State.zero [[a, b], [c]] := by
  apply foldSegments_eq_of_flatten_eq
  rfl

#print axioms foldRows_append
#print axioms foldSegments_eq_foldRows_flatten
#print axioms foldSegments_eq_of_flatten_eq

end SparkInterval.Tests.R2StarReplaySegmentationTest
