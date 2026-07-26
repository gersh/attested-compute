/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusCASRetryTrace

set_option autoImplicit false

namespace SparkInterval.Tests.MobiusCASRetryTraceTest

open SparkInterval.TernaryGoldbach.MobiusCASRetryTrace
open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
open SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement
open SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization

def initial : Support where
  product := 30
  distinctCount := 3
  squareful := false

def event7 : SplitEvent where
  prime := 7
  dividesSquare := false

def event11 : SplitEvent where
  prime := 11
  dividesSquare := false

def trace : List CASAttempt :=
  [⟨event7, false⟩, ⟨event11, true⟩,
    ⟨event7, false⟩, ⟨event7, true⟩]

example : committedEvents trace = [event11, event7] := by
  decide

example :
    cudaAttemptRun (encodeSupport initial) trace <
      SparkInterval.TernaryGoldbach.MobiusPackedCUDAWidthSafety.uint64Radix := by
  exact cudaAttemptRun_lt_uint64Radix trace
    (SplitRepresents.valid initial
      (by norm_num [initial, productRadix])
      (by norm_num [initial, countRadix]))

#print axioms
  SparkInterval.TernaryGoldbach.MobiusCASRetryTrace.stateAttemptRun_eq_distinctStateRun
#print axioms
  SparkInterval.TernaryGoldbach.MobiusCASRetryTrace.cudaAttemptRun_splitRepresents
#print axioms
  SparkInterval.TernaryGoldbach.MobiusCASRetryTrace.decode_cudaAttemptRun_eq_valid_of_committed_perm

end SparkInterval.Tests.MobiusCASRetryTraceTest
