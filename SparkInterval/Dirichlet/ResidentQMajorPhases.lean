/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Tactic

/-!
# Resident q-major phase partition

The source Hurwitz lattice has `127988` one-MiB rows.  The first seven
work-balanced phases fit easily in H100 memory.  The final work-balanced
range is split at the batch-aligned indices `49088` and `88512`, producing
three sequential phases for GPU slot seven.  This file proves the resulting
ten ranges cover every source row exactly once, preserve 64-row batch
boundaries, stay below `39488` resident rows, and retain the pinned
eight-slot work accounting.

These are finite scheduling/resource facts only.  They do not prove a wire
format, CUDA execution, analytic containment, zero completeness, attestation,
or Platt's Theorem 7.1.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.ResidentQMajorPhases

def sourceTStop : Nat := 127988
def phaseCount : Nat := 10
def gpuSlotCount : Nat := 8
def maximumResidentRows : Nat := 39488
def totalBatchedButterflies : Nat := 15334965882246056
def maximumSlotBatchedButterflies : Nat := 1998670835119088

def phaseFirst (i : Fin phaseCount) : Nat :=
  match i.val with
  | 0 => 0
  | 1 => 768
  | 2 => 1600
  | 3 => 2368
  | 4 => 3200
  | 5 => 4032
  | 6 => 5568
  | 7 => 9600
  | 8 => 49088
  | _ => 88512

def phaseStop (i : Fin phaseCount) : Nat :=
  match i.val with
  | 0 => 768
  | 1 => 1600
  | 2 => 2368
  | 3 => 3200
  | 4 => 4032
  | 5 => 5568
  | 6 => 9600
  | 7 => 49088
  | 8 => 88512
  | _ => sourceTStop

def phaseSlot (i : Fin phaseCount) : Fin gpuSlotCount :=
  match i.val with
  | 0 => ⟨0, by norm_num [gpuSlotCount]⟩
  | 1 => ⟨1, by norm_num [gpuSlotCount]⟩
  | 2 => ⟨2, by norm_num [gpuSlotCount]⟩
  | 3 => ⟨3, by norm_num [gpuSlotCount]⟩
  | 4 => ⟨4, by norm_num [gpuSlotCount]⟩
  | 5 => ⟨5, by norm_num [gpuSlotCount]⟩
  | 6 => ⟨6, by norm_num [gpuSlotCount]⟩
  | _ => ⟨7, by norm_num [gpuSlotCount]⟩

def InPhase (i : Fin phaseCount) (t : Nat) : Prop :=
  phaseFirst i ≤ t ∧ t < phaseStop i

theorem phase_nonempty (i : Fin phaseCount) :
    phaseFirst i < phaseStop i := by
  fin_cases i <;>
    norm_num [phaseCount, phaseFirst, phaseStop, sourceTStop]

theorem phase_row_count_le (i : Fin phaseCount) :
    phaseStop i - phaseFirst i ≤ maximumResidentRows := by
  fin_cases i <;>
    norm_num [phaseCount, phaseFirst, phaseStop, sourceTStop,
      maximumResidentRows]

/-- Every per-character source sample counter and every leading/trailing
ambiguity counter fits in the native unsigned 32-bit fields. -/
theorem sourceTStop_lt_uint32 :
    sourceTStop < 2 ^ 32 := by
  norm_num [sourceTStop]

/-- Every resident phase counter separately fits in the same native field. -/
theorem maximumResidentRows_lt_uint32 :
    maximumResidentRows < 2 ^ 32 := by
  norm_num [maximumResidentRows]

/-- The exact source ordinate numerator `5 * tIndex` fits in unsigned 64-bit
coordinates, including the final half-open endpoint. -/
theorem sourceStopNumerator_lt_uint64 :
    sourceTStop * 5 < 2 ^ 64 := by
  norm_num [sourceTStop]

theorem phase_first_batch_aligned (i : Fin phaseCount) :
    phaseFirst i % 64 = 0 := by
  fin_cases i <;> norm_num [phaseCount, phaseFirst]

theorem phase_stop_batch_aligned_of_internal
    (i : Fin phaseCount) (hi : i.val < 9) :
    phaseStop i % 64 = 0 := by
  have h :
      phaseStop i % 64 = 0 ∨ i.val = 9 := by
    fin_cases i <;> norm_num [phaseCount, phaseStop]
  exact h.resolve_right (by omega)

theorem inPhase_unique {t : Nat} {i j : Fin phaseCount}
    (hi : InPhase i t) (hj : InPhase j t) :
    i = j := by
  fin_cases i <;> fin_cases j <;>
    simp only [InPhase, phaseCount, phaseFirst, phaseStop, sourceTStop]
      at hi hj ⊢ <;>
    omega

theorem source_row_exists_unique_phase (t : Nat) (ht : t < sourceTStop) :
    ∃! i : Fin phaseCount, InPhase i t := by
  change t < 127988 at ht
  have finish (i : Fin phaseCount) (hi : InPhase i t) :
      ∃! j : Fin phaseCount, InPhase j t := by
    refine ⟨i, hi, ?_⟩
    intro j hj
    exact inPhase_unique hj hi
  by_cases h0 : t < 768
  · exact finish ⟨0, by norm_num [phaseCount]⟩
      (by simp [InPhase, phaseFirst, phaseStop]; omega)
  by_cases h1 : t < 1600
  · exact finish ⟨1, by norm_num [phaseCount]⟩
      (by simp [InPhase, phaseFirst, phaseStop]; omega)
  by_cases h2 : t < 2368
  · exact finish ⟨2, by norm_num [phaseCount]⟩
      (by simp [InPhase, phaseFirst, phaseStop]; omega)
  by_cases h3 : t < 3200
  · exact finish ⟨3, by norm_num [phaseCount]⟩
      (by simp [InPhase, phaseFirst, phaseStop]; omega)
  by_cases h4 : t < 4032
  · exact finish ⟨4, by norm_num [phaseCount]⟩
      (by simp [InPhase, phaseFirst, phaseStop]; omega)
  by_cases h5 : t < 5568
  · exact finish ⟨5, by norm_num [phaseCount]⟩
      (by simp [InPhase, phaseFirst, phaseStop]; omega)
  by_cases h6 : t < 9600
  · exact finish ⟨6, by norm_num [phaseCount]⟩
      (by simp [InPhase, phaseFirst, phaseStop]; omega)
  by_cases h7 : t < 49088
  · exact finish ⟨7, by norm_num [phaseCount]⟩
      (by simp [InPhase, phaseFirst, phaseStop]; omega)
  by_cases h8 : t < 88512
  · exact finish ⟨8, by norm_num [phaseCount]⟩
      (by simp [InPhase, phaseFirst, phaseStop]; omega)
  · exact finish ⟨9, by norm_num [phaseCount]⟩
      (by
        simp [InPhase, phaseFirst, phaseStop, sourceTStop]
        omega)

def slotBatchedButterflies (slot : Fin gpuSlotCount) : Nat :=
  match slot.val with
  | 0 => 1844926924725312
  | 1 => 1998670835119088
  | 2 => 1844926924725312
  | 3 => 1998670835119088
  | 4 => 1899471145527012
  | 5 => 1967010083383448
  | 6 => 1886569668387388
  | _ => 1894719465259408

/-- Exact batch-aware butterfly accounting for each resident phase. -/
def phaseBatchedButterflies (phase : Fin phaseCount) : Nat :=
  match phase.val with
  | 0 => 1844926924725312
  | 1 => 1998670835119088
  | 2 => 1844926924725312
  | 3 => 1998670835119088
  | 4 => 1899471145527012
  | 5 => 1967010083383448
  | 6 => 1886569668387388
  | 7 => 1745552940214384
  | 8 => 129013705688052
  | _ => 20152819356972

theorem slot_work_le (slot : Fin gpuSlotCount) :
    slotBatchedButterflies slot ≤ maximumSlotBatchedButterflies := by
  fin_cases slot <;>
    norm_num [gpuSlotCount, slotBatchedButterflies,
      maximumSlotBatchedButterflies]

theorem slot_work_sum :
    ∑ slot : Fin gpuSlotCount, slotBatchedButterflies slot =
      totalBatchedButterflies := by
  decide

/-- The ten phase costs aggregate to the same eight slot costs used by the
work-balancing plan. -/
theorem phase_work_by_slot (slot : Fin gpuSlotCount) :
    (∑ phase : Fin phaseCount,
        if phaseSlot phase = slot then phaseBatchedButterflies phase else 0) =
      slotBatchedButterflies slot := by
  fin_cases slot <;> decide

/-- Splitting slot seven for memory safety does not change the exact source
butterfly total. -/
theorem phase_work_sum :
    ∑ phase : Fin phaseCount, phaseBatchedButterflies phase =
      totalBatchedButterflies := by
  decide

#print axioms phase_nonempty
#print axioms phase_row_count_le
#print axioms sourceTStop_lt_uint32
#print axioms maximumResidentRows_lt_uint32
#print axioms sourceStopNumerator_lt_uint64
#print axioms phase_first_batch_aligned
#print axioms phase_stop_batch_aligned_of_internal
#print axioms source_row_exists_unique_phase
#print axioms slot_work_le
#print axioms slot_work_sum
#print axioms phase_work_by_slot
#print axioms phase_work_sum

end SparkInterval.Dirichlet.ResidentQMajorPhases
