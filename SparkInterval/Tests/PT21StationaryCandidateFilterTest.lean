/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PT21StationaryCandidateFilter

set_option autoImplicit false

namespace SparkInterval.Tests.PT21StationaryCandidateFilterTest

open SparkInterval.Zeta.PT21StationaryCandidateFilter

def first : Interval := ⟨3, 4⟩
def middle : Interval := ⟨1, 2⟩
def right : Interval := ⟨5, 6⟩

example : StrictStationary true first middle right := by
  norm_num [StrictStationary, first, middle, right]

example : ¬ StrictStationary true middle middle right := by
  apply equal_middle_rejects
  · norm_num [Interval.IsValid, middle]
  · exact Or.inl rfl

example : 0 < middle.lo := by
  apply certified_positive (outer := middle) (exact := middle)
  · exact ⟨le_rfl, le_rfl⟩
  · norm_num [middle]

example : (⟨-4, -3⟩ : Interval).hi < 0 := by
  apply certified_negative
    (outer := (⟨-4, -3⟩ : Interval))
    (exact := (⟨-4, -3⟩ : Interval))
  · exact ⟨le_rfl, le_rfl⟩
  · norm_num

end SparkInterval.Tests.PT21StationaryCandidateFilterTest
