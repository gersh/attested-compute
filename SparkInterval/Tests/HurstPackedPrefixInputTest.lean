/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.HurstPackedPrefixInput

set_option autoImplicit false

namespace SparkInterval.Tests.HurstPackedPrefixInputTest

open SparkInterval.TernaryGoldbach.HurstPackedPrefixInput
open SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction
open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
open SparkInterval.TernaryGoldbach.MobiusResidue235

/-- A concrete residue-seeded row reaches the direct `{μ, μ≠0}` input
without an intermediate byte. -/
example : packedPrefixInput 30 [7] =
    { mertens := -1, squarefree := 1 } := by
  decide

example : packedPoisonCount 30 [7] = 0 := by
  decide

example : packedPoisonCountTotal [30, 31, 32] [7] = 0 := by
  decide

example :
    packedPoisonCountTotal [30, 31, 32] [7] < 2 ^ 32 :=
  packedPoisonCountTotal_fits_uint32 (by decide)

/-- Whole-leaf validity is a pointwise consequence of the one global roster
and the explicit zero-poison observations. -/
example {numbers suffix : List Nat}
    (roster :
      ∀ number ∈ numbers,
        CompletePrimeRoster number (seedPrimes ++ suffix))
    (poisonFree :
      ∀ number ∈ numbers,
        packedPoisonCount number suffix = 0) :
    PrefixInputRowsValid (packedPrefixInputs numbers suffix) :=
  packedPrefixInputs_valid roster poisonFree

/-- The production receipt's single aggregate zero field supplies the same
whole-leaf validity fact. -/
example {numbers suffix : List Nat}
    (roster :
      ∀ number ∈ numbers,
        CompletePrimeRoster number (seedPrimes ++ suffix))
    (totalZero : packedPoisonCountTotal numbers suffix = 0) :
    PrefixInputRowsValid (packedPrefixInputs numbers suffix) :=
  packedPrefixInputs_valid_of_totalPoisonCount_zero roster totalZero

#print axioms
  SparkInterval.TernaryGoldbach.HurstPackedPrefixInput.packedPrefixInput_eq_moebius
#print axioms
  SparkInterval.TernaryGoldbach.HurstPackedPrefixInput.packedPoisonCountTotal_fits_uint32
#print axioms
  SparkInterval.TernaryGoldbach.HurstPackedPrefixInput.packedPrefixInputs_valid
#print axioms
  SparkInterval.TernaryGoldbach.HurstPackedPrefixInput.packedPrefixInputs_valid_of_totalPoisonCount_zero

end SparkInterval.Tests.HurstPackedPrefixInputTest
