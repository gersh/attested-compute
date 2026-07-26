/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusPackedCUDAWidthSafety

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusPackedCUDAWidthSafetyTest

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusPackedCUDAWidthSafety
open SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement
open SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement

def initial : Support where
  product := 30
  distinctCount := 3
  squareful := false

example :
    cudaDistinctWordStep (encodeSupport initial) 7 <
      uint64Radix := by
  exact cudaDistinctWordStep_encodeSupport_lt_uint64Radix
    7
    (by norm_num [initial, productRadix])
    (by norm_num [initial, countRadix])

#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedCUDAWidthSafety.nextProduct_lt_productRadix
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedCUDAWidthSafety.admittedAssembly_lt_uint64Radix
#print axioms
  SparkInterval.TernaryGoldbach.MobiusPackedCUDAWidthSafety.cudaDistinctWordStep_encodeSupport_lt_uint64Radix

end SparkInterval.Tests.MobiusPackedCUDAWidthSafetyTest
