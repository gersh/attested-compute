/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusPackedCUDABitRefinementTest

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusGuardedMachine
open SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement
open SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
open SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement

def initial : Support where
  product := 30
  distinctCount := 3
  squareful := false

example :
    cudaDistinctWordStep (encodeSupport initial) 7 =
      distinctWordStep (encodeSupport initial) 7 := by
  exact cudaDistinctWordStep_encodeSupport_eq 7
    (by norm_num [initial, productRadix])
    (by norm_num [initial, countRadix])

example :
    cudaAssemble 210 4 true =
      pack 210 4 true := by
  exact cudaAssemble_eq_pack
    (by norm_num [productRadix])
    (by norm_num [countRadix])

#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement.cudaProduct_eq_unpackProduct
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement.cudaCount_eq_unpackCount
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement.cudaStepAdmissible_iff_nativeStepAdmissible
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement.cudaAssembleFromWord_eq_pack
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement.cudaDistinctWordStep_splitRepresents

end SparkInterval.Tests.MobiusPackedCUDABitRefinementTest
