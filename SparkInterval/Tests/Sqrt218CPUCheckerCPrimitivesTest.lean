/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CPrimitives

/-!
# Tiny source-level C primitive tests for Sqrt218

These examples exercise carry, borrow, overflow, the four-`u32` wide product,
and big-endian decoding.  They are constant-size KATs, not certificate replay.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.Sqrt218CPUCheckerCPrimitives

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPrimitives

#guard
  readBE64 0x01 0x23 0x45 0x67 0x89 0xab 0xcd 0xef =
    0x0123456789abcdef

#guard
  wordAdd (limbBase - 1) 1 = 0

#guard
  addCarry (limbBase - 1) 1 = 1

#guard
  wordSub 0 1 = limbBase - 1

#guard
  mulWide32 0xffffffffffffffff 0xffffffffffffffff =
    { high := 0xfffffffffffffffe, low := 1 }

private def oneBelowCarry : U128 :=
  ⟨0, limbBase - 1⟩

private def one : U128 := ⟨0, 1⟩

private def oneLimbBase : U128 := ⟨1, 0⟩

#guard addChecked oneBelowCarry one = some oneLimbBase
#guard subChecked oneLimbBase one = some oneBelowCarry

#guard
  mulWordChecked
      (U128.mk 0 0xffffffffffffffff)
      0xffffffffffffffff =
    some (U128.mk 0xfffffffffffffffe 1)

#guard
  addChecked
      (U128.mk 0xffffffffffffffff 0xffffffffffffffff)
      one =
    none

#guard
  mulWordChecked
      (U128.mk 0xffffffffffffffff 0xffffffffffffffff)
      2 =
    none

end SparkInterval.Tests.Sqrt218CPUCheckerCPrimitives
