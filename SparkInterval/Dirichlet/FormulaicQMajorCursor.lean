/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Tactic

/-!
# Arithmetic proof for the formulaic q-major cursor

The production Dirichlet cursor divides each modulus's exact ordinate roster
into consecutive batches of at most 64.  This module proves the arithmetic
facts needed by that cursor without enumerating a source-scale roster:

* every ordinate below the declared row count belongs to its quotient batch;
* that batch is unique;
* every emitted batch is nonempty and contains at most 64 ordinates;
* the number of nonempty batches is `ceil (n / 64)`; and
* a 64-aligned t-major lane boundary is never crossed by a batch.

These are discrete schedule theorems.  They do not identify a q roster,
authenticate lattice bytes, refine a CUDA executable, or establish any
analytic or zero-completeness claim.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FormulaicQMajorCursor

def batchSize : ℕ := 64

def batchFirst (batchIndex : ℕ) : ℕ :=
  batchIndex * batchSize

def batchStop (rowCount batchIndex : ℕ) : ℕ :=
  min rowCount (batchFirst batchIndex + batchSize)

def InBatch (rowCount batchIndex tIndex : ℕ) : Prop :=
  batchFirst batchIndex ≤ tIndex ∧
    tIndex < batchStop rowCount batchIndex

/-- The canonical target record mirrored by the Python/C++ cursor. -/
structure Target where
  executionQIndex : ℕ
  q : ℕ
  laneIndex : ℕ
  firstTIndex : ℕ
  tIndexStopExclusive : ℕ
  batchCount : ℕ
  deriving DecidableEq, Repr

def canonicalTarget (executionQIndex q laneIndex rowCount batchIndex : ℕ) :
    Target :=
  { executionQIndex := executionQIndex
    q := q
    laneIndex := laneIndex
    firstTIndex := batchFirst batchIndex
    tIndexStopExclusive := batchStop rowCount batchIndex
    batchCount :=
      batchStop rowCount batchIndex - batchFirst batchIndex }

/-- Every in-range ordinate belongs to the batch selected by division by 64. -/
theorem member_quotient_batch (rowCount tIndex : ℕ)
    (h : tIndex < rowCount) :
    InBatch rowCount (tIndex / batchSize) tIndex := by
  simp only [InBatch, batchFirst, batchStop, batchSize]
  constructor <;> omega

/-- No two canonical 64-wide batches can contain the same ordinate. -/
theorem batchIndex_eq_div_of_mem (rowCount batchIndex tIndex : ℕ)
    (h : InBatch rowCount batchIndex tIndex) :
    batchIndex = tIndex / batchSize := by
  norm_num [InBatch, batchFirst, batchStop, batchSize] at h ⊢
  omega

theorem batch_unique (rowCount firstBatch secondBatch tIndex : ℕ)
    (hfirst : InBatch rowCount firstBatch tIndex)
    (hsecond : InBatch rowCount secondBatch tIndex) :
    firstBatch = secondBatch := by
  rw [batchIndex_eq_div_of_mem rowCount firstBatch tIndex hfirst,
    batchIndex_eq_div_of_mem rowCount secondBatch tIndex hsecond]

/-- A batch whose first ordinate is in range has positive length. -/
theorem batch_nonempty (rowCount batchIndex : ℕ)
    (h : batchFirst batchIndex < rowCount) :
    batchFirst batchIndex < batchStop rowCount batchIndex := by
  simp only [batchFirst, batchStop, batchSize] at h ⊢
  omega

theorem batchStop_le_rowCount (rowCount batchIndex : ℕ) :
    batchStop rowCount batchIndex ≤ rowCount := by
  simp [batchStop]

/-- The final partial batch is permitted, but no target contains over 64 rows. -/
theorem batchCount_le (rowCount batchIndex : ℕ) :
    batchStop rowCount batchIndex - batchFirst batchIndex ≤ batchSize := by
  simp only [batchFirst, batchStop, batchSize]
  omega

/-- Exactly `ceil (rowCount / 64)` batch indices are nonempty. -/
theorem batch_nonempty_index_iff (rowCount batchIndex : ℕ) :
    batchFirst batchIndex < rowCount ↔
      batchIndex < (rowCount + (batchSize - 1)) / batchSize := by
  norm_num [batchFirst, batchSize]
  omega

/-- If lane `laneBatch` begins on a 64-row boundary, every earlier batch ends
at or before that boundary.  Hence a target need never span two lane files. -/
theorem batch_does_not_cross_aligned_lane
    (rowCount batchIndex laneBatch : ℕ)
    (h : batchIndex < laneBatch) :
    batchStop rowCount batchIndex ≤ batchFirst laneBatch := by
  simp only [batchFirst, batchStop, batchSize]
  omega

theorem canonicalTarget_firstTIndex
    (executionQIndex q laneIndex rowCount batchIndex : ℕ) :
    (canonicalTarget executionQIndex q laneIndex rowCount batchIndex).firstTIndex =
      batchFirst batchIndex := rfl

theorem canonicalTarget_stopTIndex
    (executionQIndex q laneIndex rowCount batchIndex : ℕ) :
    (canonicalTarget executionQIndex q laneIndex rowCount batchIndex).tIndexStopExclusive =
      batchStop rowCount batchIndex := rfl

theorem canonicalTarget_batchCount_le
    (executionQIndex q laneIndex rowCount batchIndex : ℕ) :
    (canonicalTarget executionQIndex q laneIndex rowCount batchIndex).batchCount ≤
      batchSize := by
  exact batchCount_le rowCount batchIndex

theorem canonicalTarget_nonempty
    (executionQIndex q laneIndex rowCount batchIndex : ℕ)
    (h : batchFirst batchIndex < rowCount) :
    0 <
      (canonicalTarget executionQIndex q laneIndex rowCount batchIndex).batchCount := by
  simp only [canonicalTarget]
  have := batch_nonempty rowCount batchIndex h
  omega

end SparkInterval.Dirichlet.FormulaicQMajorCursor
