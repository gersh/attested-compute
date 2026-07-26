/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PT21Tile9Schedule

/-!
# PT21 fused bit-reversal and stages-1..9 tile schedule

The qualification kernel reads natural-order input position
`reverseBits logLength p` directly into shared-memory destination `p`, then
executes the already verified stages-1..9 tile.  These theorems identify that
load with the source's separate bit-reversal scatter and compose it with the
existing PT21 tile schedule.

This is architecture-independent index and exact-butterfly algebra.  It does
not prove CUDA execution, binary64/DD refinement, compiler correctness, or a
performance claim.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.PT21BitreverseTile9Schedule

open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.BluesteinFFTConvolution
open SparkInterval.Dirichlet.BluesteinCUDADataflow
open SparkInterval.Zeta.WindowedRadix2
open SparkInterval.Zeta.PT21Tile9Schedule

/-- The literal 32-bit CUDA shift is the 15-bit reversal used by each
32,768-point PT21 row. -/
theorem row_cuda_brev_eq (position : Fin (2 ^ 15)) :
    cudaBrevShift 15 position.val = reverseBits 15 position.val :=
  cudaBrevShift_eq_reverseBits (by omega) (by omega) position.isLt

/-- The literal 32-bit CUDA shift is the 16-bit reversal used by the final
65,536-point PT21 transform. -/
theorem final_cuda_brev_eq (position : Fin (2 ^ 16)) :
    cudaBrevShift 16 position.val = reverseBits 16 position.val :=
  cudaBrevShift_eq_reverseBits (by omega) (by omega) position.isLt

/-- A fused row-kernel load at destination `position` reads exactly the value
present after the old separate bit-reversal scatter. -/
theorem fused_row_load (natural : ExactState 15)
    (position : Fin (2 ^ 15)) :
    (bitReverseScatter natural).value position =
      natural.value
        (finIndex 15 (cudaBrevShift 15 position.val)) := by
  rw [row_cuda_brev_eq]
  rfl

/-- Final-transform counterpart of `fused_row_load`. -/
theorem fused_final_load (natural : ExactState 16)
    (position : Fin (2 ^ 16)) :
    (bitReverseScatter natural).value position =
      natural.value
        (finIndex 16 (cudaBrevShift 16 position.val)) := by
  rw [final_cuda_brev_eq]
  rfl

/-- Distinct row destinations read distinct natural-order inputs. -/
theorem fused_row_load_injective :
    Function.Injective (@bitReverseIndex 15) :=
  bitReverseIndex_injective

/-- Distinct final-transform destinations read distinct natural-order
inputs. -/
theorem fused_final_load_injective :
    Function.Injective (@bitReverseIndex 16) :=
  bitReverseIndex_injective

/-- Every natural-order row input is read by exactly one fused destination.
This is the coverage fact needed to compare the fused kernel's atomic
malformed-input flag with the old complete bit-reversal pass. -/
theorem fused_row_unique_source_coverage
    (source : Fin (2 ^ 15)) :
    ∃! destination : Fin (2 ^ 15),
      bitReverseIndex destination = source := by
  refine ⟨bitReverseIndex source, bitReverseIndex_involutive source, ?_⟩
  intro destination hdestination
  have h := congrArg bitReverseIndex hdestination
  simpa using h

/-- Every natural-order final-transform input is read by exactly one fused
destination. -/
theorem fused_final_unique_source_coverage
    (source : Fin (2 ^ 16)) :
    ∃! destination : Fin (2 ^ 16),
      bitReverseIndex destination = source := by
  refine ⟨bitReverseIndex source, bitReverseIndex_involutive source, ?_⟩
  intro destination hdestination
  have h := congrArg bitReverseIndex hdestination
  simpa using h

/-- OR-reducing any row-input predicate over fused destinations detects
exactly the same condition as OR-reducing it over natural-order inputs. -/
theorem fused_row_malformed_or_iff
    (malformed : Fin (2 ^ 15) → Prop) :
    (∃ destination, malformed (bitReverseIndex destination)) ↔
      ∃ source, malformed source := by
  constructor
  · rintro ⟨destination, hmalformed⟩
    exact ⟨bitReverseIndex destination, hmalformed⟩
  · rintro ⟨source, hmalformed⟩
    refine ⟨bitReverseIndex source, ?_⟩
    simpa using hmalformed

/-- Final-transform counterpart of `fused_row_malformed_or_iff`. -/
theorem fused_final_malformed_or_iff
    (malformed : Fin (2 ^ 16) → Prop) :
    (∃ destination, malformed (bitReverseIndex destination)) ↔
      ∃ source, malformed source := by
  constructor
  · rintro ⟨destination, hmalformed⟩
    exact ⟨bitReverseIndex destination, hmalformed⟩
  · rintro ⟨source, hmalformed⟩
    refine ⟨bitReverseIndex source, ?_⟩
    simpa using hmalformed

/-- The row kernel has exactly 64 512-value chunks per line. -/
theorem row_chunk_count : 2 ^ (15 - 9) = 64 := by norm_num

/-- The final kernel has exactly 128 512-value chunks. -/
theorem final_chunk_count : 2 ^ (16 - 9) = 128 := by norm_num

/-- Literal ownership of the two shared slots loaded by one CUDA thread:
`half = 0` owns `thread`, and `half = 1` owns `thread + 256`. -/
def fusedThreadSlot : Fin 2 × Fin 256 ≃ Fin 512 :=
  finProdFinEquiv

@[simp] theorem fusedThreadSlot_val
    (coordinate : Fin 2 × Fin 256) :
    (fusedThreadSlot coordinate).val =
      coordinate.2.val + 256 * coordinate.1.val := rfl

/-- The 256 threads and their two literal loads cover every shared tile slot
exactly once. -/
theorem fusedThreadSlot_bijective :
    Function.Bijective fusedThreadSlot :=
  fusedThreadSlot.bijective

theorem fusedThreadSlot_unique_coverage (slot : Fin 512) :
    ∃! coordinate : Fin 2 × Fin 256,
      fusedThreadSlot coordinate = slot := by
  refine ⟨fusedThreadSlot.symm slot,
    fusedThreadSlot.apply_symm_apply slot, ?_⟩
  intro coordinate hcoordinate
  exact fusedThreadSlot.injective
    (hcoordinate.trans (fusedThreadSlot.apply_symm_apply slot).symm)

/-- Literal row-kernel `blockIdx.x / 64` and `blockIdx.x % 64`
decomposition. -/
def rowBlockCoordinate (lines : Nat) :
    Fin (lines * 64) ≃ Fin lines × Fin 64 :=
  finProdFinEquiv.symm

@[simp] theorem rowBlockCoordinate_line_val {lines : Nat}
    (block : Fin (lines * 64)) :
    (rowBlockCoordinate lines block).1.val = block.val / 64 := rfl

@[simp] theorem rowBlockCoordinate_chunk_val {lines : Nat}
    (block : Fin (lines * 64)) :
    (rowBlockCoordinate lines block).2.val = block.val % 64 := rfl

/-- Every row `(line, chunk)` pair belongs to exactly one flattened CUDA
block. -/
theorem rowBlockCoordinate_unique_coverage {lines : Nat}
    (coordinate : Fin lines × Fin 64) :
    ∃! block : Fin (lines * 64),
      rowBlockCoordinate lines block = coordinate := by
  refine ⟨(rowBlockCoordinate lines).symm coordinate,
    (rowBlockCoordinate lines).apply_symm_apply coordinate, ?_⟩
  intro block hblock
  exact (rowBlockCoordinate lines).injective
    (hblock.trans
      ((rowBlockCoordinate lines).apply_symm_apply coordinate).symm)

/-- Literal final-kernel `blockIdx.x / 128` and `blockIdx.x % 128`
decomposition. The source call uses `lines = 1`; the generic statement also
records the host helper's line-count contract. -/
def finalBlockCoordinate (lines : Nat) :
    Fin (lines * 128) ≃ Fin lines × Fin 128 :=
  finProdFinEquiv.symm

@[simp] theorem finalBlockCoordinate_line_val {lines : Nat}
    (block : Fin (lines * 128)) :
    (finalBlockCoordinate lines block).1.val = block.val / 128 := rfl

@[simp] theorem finalBlockCoordinate_chunk_val {lines : Nat}
    (block : Fin (lines * 128)) :
    (finalBlockCoordinate lines block).2.val = block.val % 128 := rfl

/-- Every final-transform `(line, chunk)` pair belongs to exactly one
flattened CUDA block. -/
theorem finalBlockCoordinate_unique_coverage {lines : Nat}
    (coordinate : Fin lines × Fin 128) :
    ∃! block : Fin (lines * 128),
      finalBlockCoordinate lines block = coordinate := by
  refine ⟨(finalBlockCoordinate lines).symm coordinate,
    (finalBlockCoordinate lines).apply_symm_apply coordinate, ?_⟩
  intro block hblock
  exact (finalBlockCoordinate lines).injective
    (hblock.trans
      ((finalBlockCoordinate lines).apply_symm_apply coordinate).symm)

/-- Positive-root fused row prefix: direct bit-reversed loads followed by
the shared tile equal the separate scatter followed by global stages 1..9. -/
theorem positive_row_fused_prefix
    (natural : ExactState 15)
    (tile : Fin (2 ^ (15 - 9))) (slot : Fin (2 ^ 9)) :
    (initialStagesInTile (by omega : 9 ≤ 15)
        (bitReverseScatter natural) tile).value slot =
      (runExactStages positiveTwiddle 9 0
        (bitReversed natural)).value
          (tileGlobalIndex (by omega : 9 ≤ 15) tile slot) := by
  rw [bitReverseScatter_eq_bitReversed]
  exact (positive_row_prefix (bitReversed natural) tile slot).symm

/-- Negative-root counterpart of `positive_row_fused_prefix`. -/
theorem negative_row_fused_prefix
    (natural : ExactState 15)
    (tile : Fin (2 ^ (15 - 9))) (slot : Fin (2 ^ 9)) :
    (negativeInitialStagesInTile (by omega : 9 ≤ 15)
        (bitReverseScatter natural) tile).value slot =
      (runExactStages negativeTwiddle 9 0
        (bitReversed natural)).value
          (tileGlobalIndex (by omega : 9 ≤ 15) tile slot) := by
  rw [bitReverseScatter_eq_bitReversed]
  exact (negative_row_prefix (bitReversed natural) tile slot).symm

/-- Positive-root fused prefix for the final transform. -/
theorem positive_final_fused_prefix
    (natural : ExactState 16)
    (tile : Fin (2 ^ (16 - 9))) (slot : Fin (2 ^ 9)) :
    (initialStagesInTile (by omega : 9 ≤ 16)
        (bitReverseScatter natural) tile).value slot =
      (runExactStages positiveTwiddle 9 0
        (bitReversed natural)).value
          (tileGlobalIndex (by omega : 9 ≤ 16) tile slot) := by
  rw [bitReverseScatter_eq_bitReversed]
  exact (positive_final_prefix (bitReversed natural) tile slot).symm

/-- Negative-root fused prefix for the final transform. -/
theorem negative_final_fused_prefix
    (natural : ExactState 16)
    (tile : Fin (2 ^ (16 - 9))) (slot : Fin (2 ^ 9)) :
    (negativeInitialStagesInTile (by omega : 9 ≤ 16)
        (bitReverseScatter natural) tile).value slot =
      (runExactStages negativeTwiddle 9 0
        (bitReversed natural)).value
          (tileGlobalIndex (by omega : 9 ≤ 16) tile slot) := by
  rw [bitReverseScatter_eq_bitReversed]
  exact (negative_final_prefix (bitReversed natural) tile slot).symm

/-- Complete positive-root row schedule after fusing the scatter into the
tile load. -/
theorem positive_row_fused_full_schedule (natural : ExactState 15) :
    positiveSharedLaunch (by omega : 9 ≤ 15)
        (bitReverseScatter natural) =
      runExactStages positiveTwiddle 15 0 (bitReversed natural) := by
  rw [bitReverseScatter_eq_bitReversed]
  exact positive_row_full_schedule (bitReversed natural)

/-- Complete negative-root row schedule after fusion. -/
theorem negative_row_fused_full_schedule (natural : ExactState 15) :
    negativeSharedLaunch (by omega : 9 ≤ 15)
        (bitReverseScatter natural) =
      runExactStages negativeTwiddle 15 0 (bitReversed natural) := by
  rw [bitReverseScatter_eq_bitReversed]
  exact negative_row_full_schedule (bitReversed natural)

/-- Complete positive-root final-transform schedule after fusion. -/
theorem positive_final_fused_full_schedule (natural : ExactState 16) :
    positiveSharedLaunch (by omega : 9 ≤ 16)
        (bitReverseScatter natural) =
      runExactStages positiveTwiddle 16 0 (bitReversed natural) := by
  rw [bitReverseScatter_eq_bitReversed]
  exact positive_final_full_schedule (bitReversed natural)

/-- Complete negative-root final-transform schedule after fusion. -/
theorem negative_final_fused_full_schedule (natural : ExactState 16) :
    negativeSharedLaunch (by omega : 9 ≤ 16)
        (bitReverseScatter natural) =
      runExactStages negativeTwiddle 16 0 (bitReversed natural) := by
  rw [bitReverseScatter_eq_bitReversed]
  exact negative_final_full_schedule (bitReversed natural)

end SparkInterval.Zeta.PT21BitreverseTile9Schedule
