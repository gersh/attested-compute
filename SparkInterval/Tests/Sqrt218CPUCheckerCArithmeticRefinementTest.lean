/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CArithmeticRefinement

/-!
# Tiny C arithmetic-composition KATs for Sqrt218

These constant-size examples cover the head product, one accepted and one
rejected strict event guard, and both endpoint-anchor branches.  They do not
read an archive or replay any production computation.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.Sqrt218CPUCheckerCArithmeticRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CArithmeticRefinement

private def word128 (value : Nat) : U128 := ⟨0, value⟩

#guard cHeadRight 2 3 5 = some (word128 75_030)
#guard specHeadRight 2 3 5 = some (word128 75_030)

private def directIRHeader : Header := {
  version := 0
  flags := 0
  bound := 2
  reusedPrimeBound := 0
  logSeedAt := 0
  logScale := 3
  reciprocalScale := 5
  primeCount := 0
  factorRefCount := 0
  factorPairCount := 0
  eventCount := 0
  powerRefCount := 0
  primesOffset := 0
  factorRefsOffset := 0
  factorPairsOffset := 0
  eventsOffset := 0
  powerRefsOffset := 0
  archiveBytes := 0
}

private def directIRImage : ArchiveImage := {
  byteLength := 0
  header := directIRHeader
  primes := []
  factorRefs := []
  factorPairs := []
  events := []
  powerRefs := []
}

/- The now-public IR helper returns the identical successful value. -/
#guard headRight directIRImage 2 = .ok (word128 75_030)

private def acceptedEvent : EventArithmeticResult := {
  weighted := word128 6
  psi := word128 2
  left := word128 7_500
  right := word128 75_030
}

#guard
  cEventArithmetic U128.zero U128.zero
      2 2 3 2 3 5 =
    some acceptedEvent

#guard
  specEventArithmetic U128.zero U128.zero
      2 2 3 2 3 5 =
    some acceptedEvent

/- `21 * 3 * 1250 = 78750`, so the same head rejects it strictly. -/
#guard
  cEventArithmetic U128.zero U128.zero
      21 2 3 2 3 5 =
    none

/- Nonnegative endpoint branch:
   correction = 1*2, difference = 10-2, left = 8*2500. -/
#guard
  cAnchorArithmetic (word128 10) (word128 1)
      2 2 3 5 =
    some (word128 55_030)

#guard
  specAnchorArithmetic (word128 10) (word128 1)
      2 2 3 5 =
    some (word128 55_030)

/- Negative endpoint branch:
   correction = 2 > weighted = 0, so slack = 75030 + 2*2500. -/
#guard
  cAnchorArithmetic U128.zero (word128 1)
      2 2 3 5 =
    some (word128 80_030)

#guard
  specAnchorArithmetic U128.zero (word128 1)
      2 2 3 5 =
    some (word128 80_030)

private def directIRAnchorState : ScanState := {
  nextEvent := 0
  lastEventValue := 0
  weightedUpper := word128 1
  psiLower := U128.zero
}

/- At bound 2 the exact IR lower reciprocal multiplies zero, while the
   nonnegative branch returns `37515 - 2500 = 35015`. -/
#guard
  anchorSlack directIRImage directIRAnchorState =
    .ok (word128 35_015)

/- The positive branch still rejects when the strict endpoint guard fails. -/
#guard
  cAnchorArithmetic (word128 33) (word128 1)
      2 2 3 5 =
    none

end SparkInterval.Tests.Sqrt218CPUCheckerCArithmeticRefinement
