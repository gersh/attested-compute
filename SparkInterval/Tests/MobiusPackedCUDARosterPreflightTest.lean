/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusPackedCUDARosterPreflight

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusPackedCUDARosterPreflightTest

open SparkInterval.TernaryGoldbach.MobiusPackedCUDARosterPreflight

example :
    deviceRosterInvalid [2, 3, 5, 7, 11] = false := by
  decide

example :
    deviceRosterInvalidFor .residue2357 [2, 3, 5, 7, 11] =
      false := by
  decide

example :
    deviceRosterInvalidFor .residue2357 [2, 3, 5, 11] =
      true := by
  decide

example :
    deviceRosterInvalidFor .residue2357 [2, 3, 5, 7, 9] =
      true := by
  decide

example :
    deviceRosterInvalidFor .residue235711 [2, 3, 5, 7, 11, 13] =
      false := by
  decide

example :
    deviceRosterInvalidFor .residue235711 [2, 3, 5, 7, 11] =
      false := by
  decide

example :
    deviceRosterInvalidFor .residue235711 [2, 3, 5, 7, 13] =
      true := by
  decide

example :
    deviceRosterInvalidFor .residue235711 [2, 3, 5, 7, 11, 12] =
      true := by
  decide

/-- The production structural mode deliberately leaves primality to the
authenticated host roster, so this list is structurally valid there but not
under the stronger seed-7 suffix boundary. -/
example :
    deviceRosterInvalid [2, 3, 5, 7, 9] = false := by
  decide

example :
    deviceRosterInvalid [2, 3, 7] = true := by
  decide

example :
    deviceRosterInvalid [2, 3, 5, 0] = true := by
  decide

example :
    deviceRosterInvalid [2, 3, 5, 11, 7] = true := by
  decide

example :
    deviceRosterInvalid [2, 3, 5, 100_000_001] = true := by
  decide

example :
    ∀ word ∈
        initializePackedRows [2, 3, 7] [1, 30, 59],
      SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement.poisonSet
        word := by
  exact invalidFlag_implies_all_initialized_rows_poison
    (by decide)

example :
    ∀ word ∈
        initializePackedRowsFor .residue2357
          [2, 3, 5, 11] [1, 210, 419],
      SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement.poisonSet
        word := by
  exact invalidFlagFor_implies_all_initialized_rows_poison
    (by decide)

example :
    ∀ word ∈
        initializePackedRowsFor .residue235711
          [2, 3, 5, 7, 13] [1, 2310, 4619],
      SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement.poisonSet
        word := by
  exact invalidFlagFor_implies_all_initialized_rows_poison
    (by decide)

#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedCUDARosterPreflight.deviceRosterInvalid_eq_false_iff
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedCUDARosterPreflight.invalidFlag_implies_all_initialized_rows_poison
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedCUDARosterPreflight.invalidFlagFor_implies_all_initialized_rows_poison
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedCUDARosterPreflight.valid2357_of_deviceRosterInvalidFor_eq_false
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedCUDARosterPreflight.valid235711_of_deviceRosterInvalidFor_eq_false
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedCUDARosterPreflight.maximumMachinePrime_square_eq_sourceLimit

end SparkInterval.Tests.MobiusPackedCUDARosterPreflightTest
