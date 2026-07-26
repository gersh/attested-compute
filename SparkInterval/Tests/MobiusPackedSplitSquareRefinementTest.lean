/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusPackedSplitSquareRefinementTest

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusGuardedMachine
open SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
open SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement
open SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization

def initial : Support where
  product := 1
  distinctCount := 0
  squareful := false

def squareSeven : SplitEvent where
  prime := 7
  dividesSquare := true

example :
    decodeWord (packedSplitRun initial [squareSeven]) =
      .valid {
        product := 7
        distinctCount := 1
        squareful := true
      } := by
  decide

example :
    squareWordStep
        (encodeSupport initial + poisonRadix) true =
      encodeSupport (markSquareful initial true) +
        poisonRadix := by
  exact encodeSupport_add_poison_lor_squarefulRadix
    (by norm_num [initial, productRadix])
    (by norm_num [initial, countRadix])

#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement.encodeSupport_lor_squarefulRadix
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement.distinctWordStep_splitRepresents
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement.squareWordStep_splitRepresents
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement.output_decodeWord_packedSplitRunResidueSeeded_eq_moebius

end SparkInterval.Tests.MobiusPackedSplitSquareRefinementTest
