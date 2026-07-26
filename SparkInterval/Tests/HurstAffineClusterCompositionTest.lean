/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.HurstAffineClusterComposition

namespace SparkInterval.Tests.HurstAffineClusterCompositionTest

open SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter
open SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction
open SparkInterval.TernaryGoldbach.HurstAffineClusterComposition

def firstRows : List PrefixMQ :=
  [ { mertens := 1, squarefree := 1 }
  , { mertens := -1, squarefree := 1 } ]

def secondRows : List PrefixMQ :=
  [ { mertens := 0, squarefree := 0 }
  , { mertens := 1, squarefree := 1 } ]

/-- Deliberately implausible and unequal proxies demonstrate that proxy guard
acceptance is not an input to candidate composition. -/
def sampleWorkers : List WorkerChunk :=
  [ { rows := firstRows
      proxy := { mertens := 999, squarefree := 50_000 } }
  , { rows := secondRows
      proxy := { mertens := -777, squarefree := 80_000 } } ]

def lowerBase (_ : Nat) : Int := 10
def upperBase (_ : Nat) : Int := 20

example :
    proxyNormalizedCandidates PrefixMQ.mertens lowerBase
        0 0 { mertens := 999, squarefree := 50_000 } firstRows =
      localCandidates PrefixMQ.mertens lowerBase 0 0 firstRows :=
  proxyNormalizedCandidates_eq_local
    mertensCoordinate_additive lowerBase 0 0
      { mertens := 999, squarefree := 50_000 } firstRows

/-- The two-worker maximum has a tie across workers.  Exact global source
orders retain the earlier first-worker endpoint. -/
example :
    composeWorkerMaximum PrefixMQ.mertens lowerBase upperBase
        0 0 0 PrefixMQ.zero sampleWorkers =
      some { value := 10, order := 2 } := by
  decide

example :
    composeWorkerMinimum PrefixMQ.mertens lowerBase upperBase
        0 0 0 PrefixMQ.zero sampleWorkers =
      some { value := 19, order := 0 } := by
  decide

/-- The real incoming scan starts at the CPU handoff, never at either
worker's proxy. -/
example :
    workerIncomingStates
        { mertens := 5, squarefree := 7 } sampleWorkers =
      [ { mertens := 5, squarefree := 7 }
      , { mertens := 5, squarefree := 9 } ] := by
  decide

example :
    workerFinalState
        { mertens := 5, squarefree := 7 } sampleWorkers =
      { mertens := 6, squarefree := 10 } := by
  decide

example :
    let lower : OrderedCandidate := { value := 4, order := 0 }
    let upper : OrderedCandidate := { value := 8, order := 1 }
    let handoff : PrefixMQ := { mertens := 5, squarefree := 7 }
    let cumulative : PrefixMQ := { mertens := 1, squarefree := 3 }
    let translatedLower :=
      shiftCandidate (-PrefixMQ.mertens cumulative) 17 lower
    let translatedUpper :=
      shiftCandidate (-PrefixMQ.mertens cumulative) 17 upper
    translatedLower.value ≤ PrefixMQ.mertens handoff ∧
        PrefixMQ.mertens handoff ≤ translatedUpper.value ↔
      lower.value ≤ PrefixMQ.mertens (handoff + cumulative) ∧
        PrefixMQ.mertens (handoff + cumulative) ≤ upper.value := by
  exact translatedGuard_contains_handoff_iff
    mertensCoordinate_additive _ _ _ _ _

/-- Direct use of the generic theorem at the production worker count. -/
example
    (workers : List WorkerChunk) (count : workers.length = 8) :
    composeWorkerMaximum PrefixMQ.mertens lowerBase upperBase
          0 0 0 PrefixMQ.zero workers =
        reduceMaximum
          (affineCandidatesFrom PrefixMQ.mertens lowerBase
            0 0 0 PrefixMQ.zero (workerRows workers)) ∧
      composeWorkerMinimum PrefixMQ.mertens lowerBase upperBase
          0 0 0 PrefixMQ.zero workers =
        reduceMinimum
          (affineCandidatesFrom PrefixMQ.mertens upperBase
            0 0 0 PrefixMQ.zero (workerRows workers)) :=
  eightWorkerComposition_eq_single
    mertensCoordinate_additive lowerBase upperBase 0 0 workers count

/-- The capstone right side is literally the pre-existing exact scan and
candidate-reduction API. -/
example :
    composeWorkerMaximum PrefixMQ.mertens lowerBase upperBase
          0 0 0 PrefixMQ.zero sampleWorkers =
        reduceMaximum
          (rowCandidates
            (fun index pfx =>
              lowerBase index - PrefixMQ.mertens pfx)
            0 (inclusiveInputScan (workerRows sampleWorkers))) ∧
      composeWorkerMinimum PrefixMQ.mertens lowerBase upperBase
          0 0 0 PrefixMQ.zero sampleWorkers =
        reduceMinimum
          (rowCandidates
            (fun index pfx =>
              upperBase index - PrefixMQ.mertens pfx)
            0 (inclusiveInputScan (workerRows sampleWorkers))) :=
  nWorkerComposition_eq_inclusiveInputScan
    mertensCoordinate_additive lowerBase upperBase 0 0 sampleWorkers

#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineClusterComposition.proxyNormalizedCandidates_eq_local
#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineClusterComposition.workerSummary_arithmetic_independent_of_proxy
#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineClusterComposition.workerIncomingStates_getElem
#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineClusterComposition.workerFinalState_eq_handoff_add_total
#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineClusterComposition.translatedGuard_contains_handoff_iff
#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineClusterComposition.nWorkerComposition_eq_single
#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineClusterComposition.nWorkerComposition_eq_inclusiveInputScan
#print axioms
  SparkInterval.TernaryGoldbach.HurstAffineClusterComposition.eightWorkerComposition_eq_single

end SparkInterval.Tests.HurstAffineClusterCompositionTest
