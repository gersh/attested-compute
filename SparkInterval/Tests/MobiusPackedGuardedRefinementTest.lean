/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusPackedGuardedRefinementTest

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusGuardedMachine
open SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
open SparkInterval.TernaryGoldbach.MobiusResidue235

private def initial : Support where
  product := 1
  distinctCount := 0
  squareful := false

private def thirteenFactors : Support where
  product := 1
  distinctCount := 13
  squareful := false

private def overflowingProduct : Support where
  product := productRadix / 2
  distinctCount := 0
  squareful := false

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

#guard
  decodeWord (wordStep 12 (encodeSupport initial) 2) =
    .valid {
      product := 2
      distinctCount := 1
      squareful := true
    }

#guard
  decodeWord (wordStep 12 (encodeSupport initial) 1) =
    State.poison

#guard
  decodeWord
      (wordStep 77 (encodeSupport thirteenFactors) 7) =
    State.poison

#guard
  decodeWord
      (wordStep 10 (encodeSupport overflowingProduct) 2) =
    State.poison

#guard
  decodeWord
      (wordFold 12 [2, 3] (encodeSupport initial)) =
    .valid {
      product := 6
      distinctCount := 2
      squareful := true
    }

#guard
  decodeWord
      (wordFold 12 [2, 1, 3] (encodeSupport initial)) =
    State.poison

example :
    decodeWord (wordStep 12 (encodeSupport initial) 2) =
      step 12 (.valid initial) 2 :=
  decodeWord_wordStep_encodeSupport 12 2
    (by norm_num [initial, productRadix])
    (by norm_num [initial, countRadix])

example :
    output 30
        (decodeWord (packedRunResidueSeeded 30 [])) =
      ArithmeticFunction.moebius 30 :=
  output_decodeWord_packedRunResidueSeeded_eq_moebius
    rosterThirty (by decide)

#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement.decodeWord_wordStep_encodeSupport
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement.decodeWord_wordFold_encodeSupport
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement.output_decodeWord_packedRunResidueSeeded_eq_moebius

end SparkInterval.Tests.MobiusPackedGuardedRefinementTest
