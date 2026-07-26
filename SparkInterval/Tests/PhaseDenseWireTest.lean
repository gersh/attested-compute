/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.PhaseDenseWire

set_option autoImplicit false

namespace SparkInterval.Tests.PhaseDenseWireTest

open SparkInterval.Dirichlet.PhaseDenseWire

def first : Record :=
  { hasDeterminate := true
    firstPositive := false
    lastPositive := true
    hasSparse := false
    transitionCount := 3 }

def second : Record :=
  { hasDeterminate := false
    firstPositive := false
    lastPositive := false
    hasSparse := true
    transitionCount := 0 }

def third : Record :=
  { hasDeterminate := true
    firstPositive := true
    lastPositive := true
    hasSparse := true
    transitionCount := 7 }

example : encode first = 53 := by rfl
example : decode 53 = first := by rfl
example : recordWidth 8 = 7 := by
  norm_num [recordWidth, countWidth, Nat.log]

-- Seven-bit records deliberately cross byte boundaries.
example : packedAt 7 0 (packValues 7 [53, 8, 127]) = 53 := by rfl
example : packedAt 7 1 (packValues 7 [53, 8, 127]) = 8 := by rfl
example : packedAt 7 2 (packValues 7 [53, 8, 127]) = 127 := by rfl

example :
    recordAt 8 2 (packRecords 8 [first, second, third]) = third := by
  apply recordAt_packRecords
  · norm_num
  · intro record hrecord
    simp only [List.mem_cons, List.not_mem_nil, or_false] at hrecord
    rcases hrecord with rfl | rfl | rfl <;>
      simp [Canonical, first, second, third]
  · intro record hrecord
    simp only [List.mem_cons, List.not_mem_nil, or_false] at hrecord
    rcases hrecord with rfl | rfl | rfl <;>
      norm_num [first, second, third]
  · norm_num

end SparkInterval.Tests.PhaseDenseWireTest
