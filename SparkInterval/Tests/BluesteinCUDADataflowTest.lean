/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.BluesteinCUDADataflow

namespace SparkInterval.Tests.BluesteinCUDADataflowTest

open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.BluesteinFFTConvolution
open SparkInterval.Dirichlet.BluesteinCUDADataflow

/-- The literal 32-bit source expression gives the four-bit reversal. -/
example : cudaBrevShift 4 3 = 12 := by
  norm_num [cudaBrevShift, reverseBits]

/-- The source and gather tensor addresses agree on a nontrivial stride. -/
example :
    tensorAddress 5 7 (3 * 7 + 2) 4 =
      3 * 5 * 7 + 4 * 7 + 2 := by
  exact tensorAddress_outer_inner (by omega) (by omega)

/-- `initializeA` really stores the natural chirped value at the reversed
destination. -/
example (source : Fin 5 → ℂ) (position : Fin (2 ^ 4)) :
    (initializeAWorkspace 5 4 source).value
        (bitReverseIndex position) =
      SparkInterval.Dirichlet.BluesteinDFT.paddedChirpedInput
        5 (2 ^ 4) source position :=
  initializeA_write_to_bit_reversed_address source position

/-- The same property holds at the exact flattened batched address used by
the grid-stride CUDA kernel. -/
example (source : Fin 3 → Fin 5 → ℂ)
    (line : Fin 3) (position : Fin (2 ^ 4)) :
    initializeABatchWorkspace 3 5 4 source
        (bitReversedWorkspaceIndex line position) =
      SparkInterval.Dirichlet.BluesteinDFT.paddedChirpedInput
        5 (2 ^ 4) (source line) position :=
  initializeABatch_write_to_flat_address source line position

/-- The fused source kernel writes exactly one natural-frequency product to
the inverse transform's bit-reversed input address. -/
example (values multiplier : ExactState 4)
    (position : Fin (2 ^ 4)) :
    (pointwiseBitReverseCopy values multiplier).value
        (bitReverseIndex position) =
      values.value position * multiplier.value position :=
  pointwiseBitReverseCopy_write values multiplier position

/-- At the source tile size `1024`, the last grouped stage remains wholly
inside the tile. -/
example (tile slot : Nat) (hslot : slot < 2 ^ 10) :
    tile * 2 ^ 10 ≤
        scheduledLeft 9
          (groupAt 9 (tile * 2 ^ 10 + slot))
          (offsetAt 9 (tile * 2 ^ 10 + slot)) ∧
      scheduledLeft 9
          (groupAt 9 (tile * 2 ^ 10 + slot))
          (offsetAt 9 (tile * 2 ^ 10 + slot)) <
        (tile + 1) * 2 ^ 10 ∧
      tile * 2 ^ 10 ≤
        scheduledRight 9
          (groupAt 9 (tile * 2 ^ 10 + slot))
          (offsetAt 9 (tile * 2 ^ 10 + slot)) ∧
      scheduledRight 9
          (groupAt 9 (tile * 2 ^ 10 + slot))
          (offsetAt 9 (tile * 2 ^ 10 + slot)) <
        (tile + 1) * 2 ^ 10 :=
  stage_addresses_mem_aligned_tile (by omega) hslot

/-- The shared prefix has the same positive-root global stage semantics. -/
example (state : ExactState 12)
    (tile : Fin (2 ^ (12 - 10))) (slot : Fin (2 ^ 10)) :
    (runExactStages positiveTwiddle 10 0 state).value
        (tileGlobalIndex (by omega) tile slot) =
      (initialStagesInTile (by omega) state tile).value slot :=
  initialStages_grouped_by_tile (by omega) state tile slot

/-- The shared prefix has the same negative-root global stage semantics. -/
example (state : ExactState 12)
    (tile : Fin (2 ^ (12 - 10))) (slot : Fin (2 ^ 10)) :
    (runExactStages negativeTwiddle 10 0 state).value
        (tileGlobalIndex (by omega) tile slot) =
      (negativeInitialStagesInTile (by omega) state tile).value slot :=
  negativeInitialStages_grouped_by_tile (by omega) state tile slot

/-- End-to-end source-layout smoke theorem for a padded length-five line. -/
example (source : Fin 5 → ℂ) (frequency : Fin 5) :
    cudaBluesteinLineValue 5 4 source frequency (by omega) =
      SparkInterval.Dirichlet.BluesteinDFT.positiveDFT
        5 source frequency :=
  cudaBluesteinLineValue_eq_positiveDFT
    (by omega) (by omega) source frequency

/-- The strongest theorem includes the source's grouped shared-memory
prefix. -/
example (source : Fin 5 → ℂ) (frequency : Fin 5) :
    cudaBluesteinSharedLineValue 5 4 4 (by omega)
        source frequency (by omega) =
      SparkInterval.Dirichlet.BluesteinDFT.positiveDFT
        5 source frequency :=
  cudaBluesteinSharedLineValue_eq_positiveDFT
    (by omega) (by omega) (by omega) source frequency

/-- Production `min(length, 1024)` tile selection is also in the capstone. -/
example (source : Fin 5 → ℂ) (frequency : Fin 5) :
    cudaBluesteinSourceLineValue 5 4 source frequency (by omega) =
      SparkInterval.Dirichlet.BluesteinDFT.positiveDFT
        5 source frequency :=
  cudaBluesteinSourceLineValue_eq_positiveDFT
    (by omega) (by omega) source frequency

#print axioms cudaBrevShift_eq_reverseBits
#print axioms bitReverseScatter_write
#print axioms initializeA_write_to_bit_reversed_address
#print axioms initializeABatch_write_to_flat_address
#print axioms pointwiseBitReverseCopy_write
#print axioms pointwiseBitReverseCopyBatch_write_to_flat_address
#print axioms runExactStages_negative_eq_conjugate_positive
#print axioms stage_addresses_mem_aligned_tile
#print axioms initialStages_grouped_by_tile
#print axioms negativeInitialStages_grouped_by_tile
#print axioms positiveSharedLaunch_eq_full
#print axioms negativeSharedLaunch_eq_full
#print axioms gatherOutputValue_eq_postChirp_normalized
#print axioms cudaBluesteinLineValue_eq_positiveDFT
#print axioms cudaBluesteinSharedLineValue_eq_positiveDFT
#print axioms cudaBluesteinSourceLineValue_eq_positiveDFT

end SparkInterval.Tests.BluesteinCUDADataflowTest
