/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CompletedConductorPhase

/-!
# Exact block-parallel completed-factor recurrence schedule

The optimized CUDA factor builder assigns one block to each conductor
checkpoint span.  Its 256 threads split that span into contiguous chunks;
an inclusive block prefix supplies each thread with the conductor power at
the start of its chunk, after which the thread advances in sample order.

This module proves the integer schedule independently of CUDA: every sample
in a positive span has one in-range thread owner, lies in exactly that
thread's clipped half-open chunk, and has the same exact conductor exponent
as an uninterrupted recurrence.  It does not assert that a GPU executed the
schedule or that a supplied disk encloses the corresponding transcendental.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.CompletedFactorParallelSchedule

open SparkInterval.Dirichlet.CompletedConductorPhase

/-- Threads in the production checkpoint-recurrence block. -/
def threadsPerBlock : ℕ := 256

/-- Ceiling of `span / 256`, written without an unchecked denominator. -/
def chunkSize (span : ℕ) : ℕ :=
  1 + (span - 1) / threadsPerBlock

/-- First relative sample assigned to a thread, clipped at the span end. -/
def threadStart (span thread : ℕ) : ℕ :=
  min (thread * chunkSize span) span

/-- Exclusive relative sample stop assigned to a thread. -/
def threadStop (span thread : ℕ) : ℕ :=
  min (threadStart span thread + chunkSize span) span

/-- Unique thread owning an in-span relative sample. -/
def threadOwner (span sample : ℕ) : ℕ :=
  sample / chunkSize span

/-- Offset of a sample within its owning thread's sequential loop. -/
def threadOffset (span sample : ℕ) : ℕ :=
  sample % chunkSize span

theorem chunkSize_positive {span : ℕ} (_hspan : 0 < span) :
    0 < chunkSize span := by
  simp [chunkSize]

/-- The 256 chunks cover a positive span completely. -/
theorem span_le_thread_capacity {span : ℕ} (hspan : 0 < span) :
    span ≤ threadsPerBlock * chunkSize span := by
  have hremainder :
      (span - 1) % threadsPerBlock < threadsPerBlock :=
    Nat.mod_lt _ (by norm_num [threadsPerBlock])
  have hdecomposition :
      ((span - 1) / threadsPerBlock) * threadsPerBlock +
          (span - 1) % threadsPerBlock =
        span - 1 := by
    simpa [Nat.mul_comm] using
      Nat.div_add_mod (span - 1) threadsPerBlock
  norm_num [threadsPerBlock] at hremainder hdecomposition
  simp [chunkSize, threadsPerBlock, Nat.mul_add]
  omega

theorem threadOwner_lt
    {span sample : ℕ}
    (hspan : 0 < span)
    (hsample : sample < span) :
    threadOwner span sample < threadsPerBlock := by
  have hcapacity := span_le_thread_capacity hspan
  rw [threadOwner, Nat.div_lt_iff_lt_mul (chunkSize_positive hspan)]
  simpa [Nat.mul_comm] using lt_of_lt_of_le hsample hcapacity

theorem owner_unclippedStart_le
    {span sample : ℕ} (_hspan : 0 < span) :
    threadOwner span sample * chunkSize span ≤ sample := by
  exact Nat.div_mul_le_self _ _

theorem sample_lt_owner_unclippedStop
    {span sample : ℕ} (hspan : 0 < span) :
    sample <
      threadOwner span sample * chunkSize span + chunkSize span := by
  have hremainder :
      sample % chunkSize span < chunkSize span :=
    Nat.mod_lt _ (chunkSize_positive hspan)
  have hdecomposition :
      threadOwner span sample * chunkSize span +
          sample % chunkSize span =
        sample := by
    simpa [threadOwner, Nat.mul_comm] using
      Nat.div_add_mod sample (chunkSize span)
  omega

/-- Every in-span sample lies in its owner's clipped chunk. -/
theorem sample_mem_owner
    {span sample : ℕ}
    (hspan : 0 < span)
    (hsample : sample < span) :
    threadStart span (threadOwner span sample) ≤ sample ∧
      sample < threadStop span (threadOwner span sample) := by
  have hstart :=
    owner_unclippedStart_le (span := span) (sample := sample) hspan
  have hstop :=
    sample_lt_owner_unclippedStop
      (span := span) (sample := sample) hspan
  have hunclipped :
      threadStart span (threadOwner span sample) =
        threadOwner span sample * chunkSize span := by
    rw [threadStart, Nat.min_eq_left]
    exact le_trans hstart (Nat.le_of_lt hsample)
  constructor
  · simpa [hunclipped] using hstart
  · rw [threadStop, Nat.lt_min]
    exact ⟨by simpa [hunclipped] using hstop, hsample⟩

/-- The owner start plus the per-thread loop offset reconstructs the sample. -/
theorem threadStart_add_offset
    {span sample : ℕ}
    (hspan : 0 < span)
    (hsample : sample < span) :
    threadStart span (threadOwner span sample) +
        threadOffset span sample =
      sample := by
  have hstart :=
    owner_unclippedStart_le (span := span) (sample := sample) hspan
  rw [threadStart, Nat.min_eq_left
    (le_trans hstart (Nat.le_of_lt hsample))]
  simpa [threadOwner, threadOffset, Nat.mul_comm] using
    Nat.div_add_mod sample (chunkSize span)

/-- The half-open chunk bounds determine the owning thread uniquely. -/
theorem thread_eq_owner
    {span thread sample : ℕ}
    (_hspan : 0 < span)
    (hstart : thread * chunkSize span ≤ sample)
    (hstop : sample < thread * chunkSize span + chunkSize span) :
    thread = threadOwner span sample := by
  apply Eq.symm
  apply Nat.div_eq_of_lt_le
  · exact hstart
  · simpa [Nat.add_mul] using hstop

/-- The block-prefix start exponent plus the sequential in-thread offset is
exactly the uninterrupted exponent for that checkpoint-relative sample. -/
theorem conductorExponentAt_thread
    (checkpointExponent : ℚ)
    {span sample : ℕ}
    (hspan : 0 < span)
    (hsample : sample < span) :
    exponentAt checkpointExponent sample =
      exponentAt checkpointExponent
          (threadStart span (threadOwner span sample)) +
        (threadOffset span sample : ℚ) * exponentStep := by
  have hdecomposition :=
    threadStart_add_offset
      (span := span) (sample := sample) hspan hsample
  simp only [exponentAt]
  have hdecompositionQ :
      (threadStart span (threadOwner span sample) : ℚ) +
          (threadOffset span sample : ℚ) =
        (sample : ℚ) := by
    exact_mod_cast hdecomposition
  rw [← hdecompositionQ]
  ring

end SparkInterval.Dirichlet.CompletedFactorParallelSchedule
