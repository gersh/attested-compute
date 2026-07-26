/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusSplitSquareRealizationTest

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization

example :
    7 * 7 ∣ 10_000 + 45 ↔
      ∃! visit, SquareVisits 10_000 100 7 45 visit :=
  prime_sq_dvd_iff_existsUnique_squareVisit (by decide) (by decide)

def events : List SplitEvent := [
  { prime := 7, dividesSquare := false },
  { prime := 11, dividesSquare := true },
  { prime := 13, dividesSquare := false }
]

example :
    splitRun { product := 30, distinctCount := 3, squareful := false }
        events =
      inlineRun
        { product := 30, distinctCount := 3, squareful := false }
        events :=
  splitRun_eq_inlineRun _ _

example :
    splitRun { product := 30, distinctCount := 3, squareful := false }
        events =
      splitRun
        { product := 30, distinctCount := 3, squareful := false }
        events.reverse :=
  splitRun_perm _ (List.reverse_perm events).symm

#print axioms
  SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization.prime_sq_dvd_iff_existsUnique_squareVisit
#print axioms
  SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization.splitRun_eq_inlineRun
#print axioms
  SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization.splitRun_perm
#print axioms
  SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization.finalize_splitRun_residueSeeded_eq_moebius

end SparkInterval.Tests.MobiusSplitSquareRealizationTest
