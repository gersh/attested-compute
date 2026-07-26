/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusResidue235

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusResidue235

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusDenseSchedule
open SparkInterval.TernaryGoldbach.MobiusResidue235

example :
    blockLocalResidue900 10_000_000_000_000_000 17 255 =
      (10_000_000_000_000_000 + 17 * 256 + 255) % 900 := by
  exact blockLocalResidue900_eq_sourceNumber_mod
    (by norm_num [threadsPerBlock])

example : residueModulus = 2 ^ 2 * 3 ^ 2 * 5 ^ 2 := by
  norm_num [residueModulus]

example : residueSeed 0 =
    { product := 30, distinctCount := 3, squareful := true } := by
  decide

example : residueSeed 30 =
    { product := 30, distinctCount := 3, squareful := false } := by
  decide

example : residueSeed 901 = initialSupport := by
  decide

example (n : ℕ) :
    foldSupport n ([2, 3, 5] ++ [7, 11, 13]) =
      [7, 11, 13].foldl (applyPrime n) (residueSeed n) := by
  exact fold_prefix_suffix_eq_residueSeed n [7, 11, 13]

#print axioms seedPrime_dvd_residue_iff
#print axioms blockLocalResidue900_eq_sourceNumber_mod
#print axioms seedPrime_sq_dvd_residue_iff
#print axioms applyPrime_residue_eq
#print axioms residueSeed_eq
#print axioms fold_prefix_suffix_eq_residueSeed

end SparkInterval.Tests.MobiusResidue235
