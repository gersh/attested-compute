/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.HurstAffineBlockComposition

set_option autoImplicit false

namespace SparkInterval.Tests.HurstAffineBlockCompositionTest

open SparkInterval.TernaryGoldbach.HurstPrefixCandidateReduction
open SparkInterval.TernaryGoldbach.HurstAffineClusterComposition
open SparkInterval.TernaryGoldbach.HurstAffineBlockComposition

#check rightTile_translation_has_negative_sign_and_global_order
#check adjacentTileCandidates_eq_perRowCandidates
#check cudaAffineLaunchRow_decode
#check cudaAffineLaunchRow_decode_bounds
#check cudaAffineRowBlock_lt_summaryCount
#check cudaAffineSummaryCount_le_1526
#check cudaAffineLaunchRow_injective
#check cudaAffineLaunchIndex_and_order_fit_uint32
#check cudaBlockStripedScan_eq_inclusiveInputScan
#check cudaSummaryThread_machine_bounds
#check cudaOrderedTileComposition_eq_perRowInclusiveScan
#check cudaOrderedTileFinalDelta_eq_perRowTotal
#check cudaTileDelta_fits_int32_uint32
#check translatedMertensCandidate_fits_int64
#check translatedSquarefreeCandidate_fits_int64
#check translatedSquarefreeWitness_fits_uint32
#check summaryThreadCrossover_255_256_257
#check summaryCount257_partialFinalThread
#check cudaExtractedThreadChunks_cover
#check cudaExtractedChunksAndTree_refine_orderedFold
#check CudaAffineMqBoundCandidate
#check CudaAffineMqBlockSummary
#check translateCudaHurstCandidate_add
#check translateCudaSquarefreeCandidate_add
#check composeCudaAffineMqBlockSummary_assoc
#check cudaAffineMqSummaryTree_refines_orderedFold
#check cudaAffineMqSummaryOfRows
#check cudaAffineMqSummaryOfRows_append
#check prod_cudaAffineMqSummariesOfTiles
#check cudaAffineMqTileSummaryTree_eq_perRowSummary
#check cudaHurstSummaryOfRows_projects_to_perRowExtrema
#check cudaHurstTileTree_projects_to_workerComposition
#check validPrefixRows_imply_terminalMqGuards
#print axioms composeCudaAffineMqBlockSummary_assoc
#print axioms cudaSummaryThread_machine_bounds
#print axioms cudaAffineMqSummaryTree_refines_orderedFold
#print axioms cudaAffineMqSummaryOfRows_append
#print axioms cudaAffineMqTileSummaryTree_eq_perRowSummary
#print axioms cudaHurstTileTree_projects_to_workerComposition
#print axioms validPrefixRows_imply_terminalMqGuards

example :
    CudaTileShape
      [List.replicate 65_536
        ({ mertens := 1, squarefree := 1 } : PrefixMQ)]
      [{ mertens := -1, squarefree := 1 }] := by
  constructor
  · intro tile membership
    simp only [List.mem_singleton] at membership
    subst tile
    simp only [List.length_replicate, cudaAffineRowsPerBlock]
  · norm_num [cudaAffineRowsPerBlock]

example :
    (shiftCandidate (-17) 0
      { value := 23, order := 2 * 65_536 + 1 }).order =
        2 * 65_536 + 1 := by
  rfl

private def leftSummary : CudaAffineMqBlockSummary :=
  { delta := { mertens := 3, squarefree := 5 }
    hurstLower := none
    hurstUpper := none
    squarefreeLower := none
    squarefreeUpper := none }

private def rightSummary : CudaAffineMqBlockSummary :=
  { delta := { mertens := -2, squarefree := 7 }
    hurstLower :=
      some { value := 20, localSquarefree := 0, order := 131_072 }
    hurstUpper :=
      some { value := 30, localSquarefree := 0, order := 131_072 }
    squarefreeLower :=
      some { value := 40, localSquarefree := 7, order := 131_073 }
    squarefreeUpper :=
      some { value := 50, localSquarefree := 7, order := 131_073 } }

/-- Concrete sign/witness check: the right Hurst values lose `3`, the right
squarefree values lose `5`, the squarefree witnesses gain `5`, and global
orders do not move. -/
example :
    composeCudaAffineMqBlockSummary leftSummary rightSummary =
      { delta := { mertens := 1, squarefree := 12 }
        hurstLower :=
          some
            { value := 17
              localSquarefree := 0
              order := 131_072 }
        hurstUpper :=
          some
            { value := 27
              localSquarefree := 0
              order := 131_072 }
        squarefreeLower :=
          some
            { value := 35
              localSquarefree := 12
              order := 131_073 }
        squarefreeUpper :=
          some
            { value := 45
              localSquarefree := 12
              order := 131_073 } } := by
  decide

/-- Equal extrema retain the earliest global source order, independently of
the squarefree witness field. -/
example :
    mergeCudaAffineMaximum
      (some { value := 19, localSquarefree := 11, order := 8 })
      (some { value := 19, localSquarefree := 99, order := 6 }) =
        some { value := 19, localSquarefree := 99, order := 6 } := by
  decide

example (summaries : List CudaAffineMqBlockSummary) :
    (orderedTreeRounds 8
      ((cudaExtractedThreadChunks summaries).map List.prod)).prod =
        summaries.prod :=
  cudaAffineMqSummaryTree_refines_orderedFold summaries

example (bounds : CudaAffineMqRowBounds)
    (sourceOffset orderOffset : Nat)
    (left right : List PrefixMQ) :
    cudaAffineMqSummaryOfRows bounds sourceOffset orderOffset
        (left ++ right) =
      cudaAffineMqSummaryOfRows bounds sourceOffset orderOffset left *
        cudaAffineMqSummaryOfRows bounds
          (sourceOffset + left.length)
          (orderOffset + left.length) right :=
  cudaAffineMqSummaryOfRows_append bounds
    sourceOffset orderOffset left right

example :
    let rows : List PrefixMQ :=
      [{ mertens := -1, squarefree := 1 },
       { mertens := 0, squarefree := 0 },
       { mertens := 1, squarefree := 1 }]
    (inputTotal rows).squarefree ≤ rows.length ∧
      -((inputTotal rows).squarefree : Int) ≤
        (inputTotal rows).mertens ∧
      (inputTotal rows).mertens ≤
        ((inputTotal rows).squarefree : Int) ∧
      ((inputTotal rows).mertens +
        ((inputTotal rows).squarefree : Int)) % 2 = 0 := by
  decide

end SparkInterval.Tests.HurstAffineBlockCompositionTest
