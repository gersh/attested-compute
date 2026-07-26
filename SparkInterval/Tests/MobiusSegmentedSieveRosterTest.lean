/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusSegmentedSieveRoster

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusSegmentedSieveRosterTest

open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
open SparkInterval.TernaryGoldbach.MobiusSegmentedSieveRoster

def basePrimes : List Nat := [2, 3, 5]

def factorCodesThrough30 : Array Nat := #[
  0, 0, 2, 0, 2, 0, 2, 3, 2, 0,
  2, 0, 2, 3, 2, 0, 2, 0, 2, 3,
  2, 0, 2, 5, 2, 3, 2, 0, 2
]

def primesThrough30 : List Nat :=
  [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]

theorem basePrimes_valid : PrimeRosterThrough 6 basePrimes := by
  refine {
    nodup := by decide
    entriesPrime := ?_
    complete := ?_
  }
  · intro prime member
    simp [basePrimes] at member
    rcases member with rfl | rfl | rfl
    · norm_num
    · norm_num
    · norm_num
  · intro prime primePrime primeLe
    have primeLower : 2 ≤ prime := primePrime.two_le
    interval_cases prime <;> norm_num [basePrimes] at *

#guard sieveRosterCheck 6 30 basePrimes factorCodesThrough30
#guard rosterBindingCheck 30 factorCodesThrough30 primesThrough30

example :
    PrimeRosterThrough 30
      (rosterList 30 factorCodesThrough30) :=
  sieveRosterCheck_sound basePrimes_valid (by decide)

example
    (binding :
      rosterBindingCheck 30 factorCodesThrough30
        primesThrough30 = true) :
    PrimeRosterThrough 30 primesThrough30 :=
  boundRosterCheck_sound basePrimes_valid (by decide) binding

-- Marking the composite `9` as a survivor violates strike coverage.
def missingNine : Array Nat :=
  factorCodesThrough30.set! (9 - 2) 0

#guard witnessCheck 30 basePrimes missingNine
#guard !(coverageCheck 30 basePrimes missingNine)
#guard !(sieveRosterCheck 6 30 basePrimes missingNine)

-- Marking the prime `7` with a fake factor violates witness soundness.
def falseSeven : Array Nat :=
  factorCodesThrough30.set! (7 - 2) 2

#guard !(witnessCheck 30 basePrimes falseSeven)
#guard coverageCheck 30 basePrimes falseSeven
#guard !(sieveRosterCheck 6 30 basePrimes falseSeven)

-- A nondividing base-prime code is rejected.
def wrongFactorForNine : Array Nat :=
  factorCodesThrough30.set! (9 - 2) 2

#guard !(witnessCheck 30 basePrimes wrongFactorForNine)

-- The exact interval length is part of the accepted artifact shape.
def truncated : Array Nat :=
  factorCodesThrough30.pop

#guard !(shapeCheck 6 30 truncated)
#guard !(sieveRosterCheck 6 30 basePrimes truncated)

#guard !(rosterBindingCheck 30 factorCodesThrough30
  [2, 3, 5, 7, 11, 13, 17, 19, 23])

example :
    rosterBytesBindingCheck
      (encodeRosterU32LE primesThrough30) primesThrough30 = true := by
  simp [rosterBytesBindingCheck]

#guard factorCodeBytesBindingCheck
  (encodeFactorCodesU16LE factorCodesThrough30)
  factorCodesThrough30

example :
    (encodeFactorCodesU16LE factorCodesThrough30).size =
      2 * factorCodesThrough30.size := by
  simp

end SparkInterval.Tests.MobiusSegmentedSieveRosterTest
