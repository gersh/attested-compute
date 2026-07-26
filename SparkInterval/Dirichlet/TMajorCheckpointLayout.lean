/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CompletedConductorPhase

/-!
# Exact layout of the checkpointed conductor recurrence

The GPU completed-sign reducer restarts its conductor phase from an Arb disk
at fixed-size checkpoints.  This module records the corresponding indexing
algorithm over natural numbers and proves that every in-range sample has one
owner, lies inside that owner's span, and receives the same exact rational
exponent as an unbroken recurrence.

It does not assert that an external checkpoint disk encloses a transcendental
value or that CUDA executed this indexing algorithm.  Those are separate
artifact and machine-refinement boundaries.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.TMajorCheckpointLayout

open SparkInterval.Dirichlet.CompletedConductorPhase

/-- Number of nonempty checkpoint spans used for a positive sample count.
The live GPU entry point rejects zero sample counts and zero spans. -/
def checkpointCount (sampleCount checkpointSpan : ℕ) : ℕ :=
  1 + (sampleCount - 1) / checkpointSpan

/-- Checkpoint that owns a sample. -/
def checkpointOwner (checkpointSpan sample : ℕ) : ℕ :=
  sample / checkpointSpan

/-- Offset of a sample inside its checkpoint. -/
def checkpointOffset (checkpointSpan sample : ℕ) : ℕ :=
  sample % checkpointSpan

/-- First sample owned by a checkpoint. -/
def checkpointStart (checkpointSpan checkpoint : ℕ) : ℕ :=
  checkpoint * checkpointSpan

theorem checkpointOwner_lt_count
    {sampleCount checkpointSpan sample : ℕ}
    (hcount : 0 < sampleCount)
    (_hspan : 0 < checkpointSpan)
    (hsample : sample < sampleCount) :
    checkpointOwner checkpointSpan sample <
      checkpointCount sampleCount checkpointSpan := by
  have hsampleLe : sample ≤ sampleCount - 1 := by omega
  have hquotient :
      sample / checkpointSpan ≤
        (sampleCount - 1) / checkpointSpan :=
    Nat.div_le_div_right hsampleLe
  simp only [checkpointOwner, checkpointCount]
  omega

/-- Every checkpoint admitted by the canonical count owns at least one sample;
the roster has no trailing empty checkpoint. -/
theorem checkpointStart_lt_sampleCount
    {sampleCount checkpointSpan checkpoint : ℕ}
    (hcount : 0 < sampleCount)
    (_hspan : 0 < checkpointSpan)
    (hcheckpoint :
      checkpoint < checkpointCount sampleCount checkpointSpan) :
    checkpointStart checkpointSpan checkpoint < sampleCount := by
  have hcheckpointLe :
      checkpoint ≤ (sampleCount - 1) / checkpointSpan := by
    simp only [checkpointCount] at hcheckpoint
    omega
  have hscaled :
      checkpoint * checkpointSpan ≤
        ((sampleCount - 1) / checkpointSpan) * checkpointSpan :=
    Nat.mul_le_mul_right checkpointSpan hcheckpointLe
  have hquotient :
      ((sampleCount - 1) / checkpointSpan) * checkpointSpan ≤
        sampleCount - 1 :=
    Nat.div_mul_le_self _ _
  simp only [checkpointStart]
  omega

/-- The canonical checkpoint roster covers the final sample. -/
theorem sampleCount_le_checkpointCount_mul
    {sampleCount checkpointSpan : ℕ}
    (hcount : 0 < sampleCount)
    (hspan : 0 < checkpointSpan) :
    sampleCount ≤
      checkpointCount sampleCount checkpointSpan * checkpointSpan := by
  have hremainder :
      (sampleCount - 1) % checkpointSpan < checkpointSpan :=
    Nat.mod_lt _ hspan
  have hdecomposition :
      ((sampleCount - 1) / checkpointSpan) * checkpointSpan +
          (sampleCount - 1) % checkpointSpan =
        sampleCount - 1 :=
    by
      simpa [Nat.mul_comm] using
        Nat.div_add_mod (sampleCount - 1) checkpointSpan
  simp only [checkpointCount, Nat.add_mul]
  omega

theorem checkpointOffset_lt
    {checkpointSpan sample : ℕ}
    (hspan : 0 < checkpointSpan) :
    checkpointOffset checkpointSpan sample < checkpointSpan := by
  exact Nat.mod_lt _ hspan

theorem checkpointStart_add_offset
    {checkpointSpan sample : ℕ}
    (_hspan : 0 < checkpointSpan) :
    checkpointStart checkpointSpan
        (checkpointOwner checkpointSpan sample) +
      checkpointOffset checkpointSpan sample =
        sample := by
  simpa [checkpointStart, checkpointOwner, checkpointOffset,
    Nat.mul_comm] using Nat.div_add_mod sample checkpointSpan

theorem checkpointStart_le_sample
    {checkpointSpan sample : ℕ}
    (hspan : 0 < checkpointSpan) :
    checkpointStart checkpointSpan
        (checkpointOwner checkpointSpan sample) ≤ sample := by
  have h :=
    checkpointStart_add_offset (checkpointSpan := checkpointSpan)
      (sample := sample) hspan
  omega

theorem sample_lt_checkpointStop
    {checkpointSpan sample : ℕ}
    (hspan : 0 < checkpointSpan) :
    sample <
      checkpointStart checkpointSpan
          (checkpointOwner checkpointSpan sample) +
        checkpointSpan := by
  have hoffset := checkpointOffset_lt (sample := sample) hspan
  have hdecomposition :=
    checkpointStart_add_offset (checkpointSpan := checkpointSpan)
      (sample := sample) hspan
  omega

/-- The usual half-open span conditions determine the checkpoint owner
uniquely. -/
theorem checkpoint_eq_owner
    {checkpointSpan checkpoint sample : ℕ}
    (_hspan : 0 < checkpointSpan)
    (hstart :
      checkpointStart checkpointSpan checkpoint ≤ sample)
    (hstop :
      sample < checkpointStart checkpointSpan checkpoint + checkpointSpan) :
    checkpoint = checkpointOwner checkpointSpan sample := by
  apply Eq.symm
  apply Nat.div_eq_of_lt_le
  · simpa [checkpointStart] using hstart
  · simpa [checkpointStart, Nat.add_mul] using hstop

/-- Restarting from the exact exponent at a checkpoint and taking one step
per in-span sample gives the same exponent as the uninterrupted recurrence. -/
theorem conductorExponentAt_checkpoint
    (initial : ℚ) {checkpointSpan sample : ℕ}
    (hspan : 0 < checkpointSpan) :
    exponentAt initial sample =
      exponentAt initial
          (checkpointStart checkpointSpan
            (checkpointOwner checkpointSpan sample)) +
        (checkpointOffset checkpointSpan sample : ℚ) *
          exponentStep := by
  have hdecomposition :=
    checkpointStart_add_offset (checkpointSpan := checkpointSpan)
      (sample := sample) hspan
  simp only [exponentAt]
  have hdecompositionQ :
      (checkpointStart checkpointSpan
            (checkpointOwner checkpointSpan sample) : ℚ) +
          (checkpointOffset checkpointSpan sample : ℚ) =
        (sample : ℚ) := by
    exact_mod_cast hdecomposition
  rw [← hdecompositionQ]
  ring

end SparkInterval.Dirichlet.TMajorCheckpointLayout
