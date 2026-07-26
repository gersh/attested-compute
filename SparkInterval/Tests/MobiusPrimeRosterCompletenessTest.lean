/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusPrimeRosterCompletenessTest

open SparkInterval.TernaryGoldbach.MobiusFusedFinalization
open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
open SparkInterval.TernaryGoldbach.MobiusResidue235

private theorem rosterThirty :
    CompletePrimeRoster 30 [2, 3, 5] := by
  refine {
    numberPositive := by norm_num
    nodup := by decide
    entriesPrime := ?_
    completeThroughSqrt := ?_
  }
  · intro prime member
    simp only [List.mem_cons, List.not_mem_nil, or_false] at member
    rcases member with rfl | rfl | rfl <;> norm_num
  · intro prime primePrime primeSquareLe
    have primeLe : prime ≤ 5 := by
      nlinarith
    interval_cases prime <;> norm_num at primePrime
    all_goals simp

private theorem rosterSeventyTwo :
    CompletePrimeRoster 72 [2, 3, 5, 7] := by
  refine {
    numberPositive := by norm_num
    nodup := by decide
    entriesPrime := ?_
    completeThroughSqrt := ?_
  }
  · intro prime member
    simp only [List.mem_cons, List.not_mem_nil, or_false] at member
    rcases member with rfl | rfl | rfl | rfl <;> norm_num
  · intro prime primePrime primeSquareLe
    have primeLe : prime ≤ 8 := by
      nlinarith
    interval_cases prime <;> norm_num at primePrime
    all_goals simp

example :
    finalize 30 (foldSupport 30 [2, 3, 5]) =
      ArithmeticFunction.moebius 30 :=
  rosterThirty.finalize_foldSupport_eq_moebius

/-- Regression for a squareful row whose residual after selected primes is
composite: `72 / (2*3) = 12`. -/
example :
    finalize 72 (foldSupport 72 [2, 3, 5, 7]) =
      ArithmeticFunction.moebius 72 :=
  rosterSeventyTwo.finalize_foldSupport_eq_moebius

example :
    SourceRosterValid 72 [2, 3, 5, 7] :=
  rosterSeventyTwo.sourceRosterValid

#print axioms
  SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness.CompletePrimeRoster.sourceRosterValid
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness.PrimeRosterThrough.completePrimeRoster

end SparkInterval.Tests.MobiusPrimeRosterCompletenessTest
