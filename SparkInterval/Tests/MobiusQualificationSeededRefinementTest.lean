/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusQualificationSeededRefinement

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusQualificationSeededRefinementTest

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusGuardedMachine
open SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
open SparkInterval.TernaryGoldbach.MobiusQualificationSeededRefinement

/-- A small concrete p11-seeded run decodes to the exact Möbius value. -/
example :
    output 13
        (decodeWord
          (packedSplitRunResidue235711Seeded 13 [13])) =
      ArithmeticFunction.moebius 13 := by
  apply
    output_decodeWord_packedSplitRunResidue235711Seeded_eq_moebius
  · refine
      { numberPositive := by norm_num
        nodup := by decide
        entriesPrime := ?_
        completeThroughSqrt := ?_ }
    · intro prime member
      simp only [
        SparkInterval.TernaryGoldbach.MobiusResidue235711.seedPrimes235711,
        SparkInterval.TernaryGoldbach.MobiusResidue2357.seedPrimes2357,
        SparkInterval.TernaryGoldbach.MobiusResidue235.seedPrimes,
        List.mem_append, List.mem_cons, List.not_mem_nil, or_false] at member
      rcases member with (((rfl | rfl | rfl) | rfl) | rfl) | rfl <;>
        norm_num
    · intro prime primePrime primeSquareLe
      have primeLe : prime ≤ 3 := by
        nlinarith
      interval_cases prime <;> norm_num at primePrime
      all_goals simp [
        SparkInterval.TernaryGoldbach.MobiusResidue235711.seedPrimes235711,
        SparkInterval.TernaryGoldbach.MobiusResidue2357.seedPrimes2357,
        SparkInterval.TernaryGoldbach.MobiusResidue235.seedPrimes]
  · decide

/-- A small concrete p13-seeded run decodes to the exact Möbius value. -/
example :
    output 17
        (decodeWord
          (packedSplitRunResidue23571113Seeded 17 [17])) =
      ArithmeticFunction.moebius 17 := by
  apply
    output_decodeWord_packedSplitRunResidue23571113Seeded_eq_moebius
  · refine
      { numberPositive := by norm_num
        nodup := by decide
        entriesPrime := ?_
        completeThroughSqrt := ?_ }
    · intro prime member
      simp only [
        SparkInterval.TernaryGoldbach.MobiusResidue23571113.seedPrimes23571113,
        SparkInterval.TernaryGoldbach.MobiusResidue235711.seedPrimes235711,
        SparkInterval.TernaryGoldbach.MobiusResidue2357.seedPrimes2357,
        SparkInterval.TernaryGoldbach.MobiusResidue235.seedPrimes,
        List.mem_append, List.mem_cons, List.not_mem_nil, or_false] at member
      rcases member with ((((rfl | rfl | rfl) | rfl) | rfl) | rfl) | rfl <;>
        norm_num
    · intro prime primePrime primeSquareLe
      have primeLe : prime ≤ 4 := by
        nlinarith
      interval_cases prime <;> norm_num at primePrime
      all_goals simp [
        SparkInterval.TernaryGoldbach.MobiusResidue23571113.seedPrimes23571113,
        SparkInterval.TernaryGoldbach.MobiusResidue235711.seedPrimes235711,
        SparkInterval.TernaryGoldbach.MobiusResidue2357.seedPrimes2357,
        SparkInterval.TernaryGoldbach.MobiusResidue235.seedPrimes]
  · decide

#print axioms
  output_decodeWord_packedSplitRunResidue2357Seeded_eq_moebius
#print axioms
  output_decodeWord_packedSplitRunResidue235711Seeded_eq_moebius
#print axioms
  output_decodeWord_packedSplitRunResidue23571113Seeded_eq_moebius

end SparkInterval.Tests.MobiusQualificationSeededRefinementTest
