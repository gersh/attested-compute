/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.CDEMAbelReplayAlgorithm

/-!
# Closed data-only replay for the CDEM Abel certificate

`CDEMAbelReplayAlgorithm` proves the source theorem from a typed replay whose
divisor and square-root tables satisfy their mathematical specifications.
This file closes those two table choices:

* the divisor entry is the already-defined exact `floorJump`; and
* the square-root entry is the least integer square above
  `ceil(weightScale² / n)`.

The resulting checker is a total `Bool` over a data-only recurrence
certificate.  It recomputes every event in every retained chunk.  This is the
small, obvious reference finalizer, not a performance claim: evaluating it at
the five-billion-event source scale is intentionally left to a separately
proved optimized CPU implementation.

There is no axiom, `native_decide`, proposition-valued runtime input, or
receipt in this module.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.CDEMAbelClosedReplay

open SparkInterval.TernaryGoldbach.CDEMAbelReplayAlgorithm

namespace Recurrence

abbrev Certificate :=
  CDEMAbelRecurrenceCertificate.Certificate

abbrev Chunk :=
  CDEMAbelRecurrenceCertificate.Chunk

abbrev sourcePast :=
  CDEMAbelRecurrenceCertificate.sourcePast

abbrev floorJump :=
  CDEMAbelRecurrenceCertificate.floorJump

abbrev ceilDiv :=
  CDEMAbelRecurrenceCertificate.ceilDiv

abbrev SqrtWeightValid :=
  CDEMAbelRecurrenceCertificate.SqrtWeightValid

abbrev weightScale :=
  CDEMAbelSource.weightScale

end Recurrence

/-! ## Closed square-root and divisor kernels -/

/-- Least natural number whose square is at least `value`.

The branch avoids an unnecessary successor for perfect squares; the
soundness theorem below needs only the upper-square property. -/
def ceilSqrt (value : Nat) : Nat :=
  let root := Nat.sqrt value
  if root * root = value then root else root + 1

theorem le_ceilSqrt_sq (value : Nat) :
    value ≤ ceilSqrt value * ceilSqrt value := by
  by_cases hsquare : Nat.sqrt value * Nat.sqrt value = value
  · simp [ceilSqrt, hsquare]
  · simpa [ceilSqrt, hsquare] using (Nat.lt_succ_sqrt value).le

/-- Directed reciprocal-square-root integer used by the closed replay. -/
def sqrtWeight (n : Nat) : Nat :=
  ceilSqrt
    (Recurrence.ceilDiv
      (Recurrence.weightScale * Recurrence.weightScale) n)

theorem sqrtWeight_valid (n : Nat) (hn : 0 < n) :
    Recurrence.SqrtWeightValid n (sqrtWeight n) := by
  let required :=
    Recurrence.ceilDiv
      (Recurrence.weightScale * Recurrence.weightScale) n
  have hscale :
      Recurrence.weightScale * Recurrence.weightScale ≤ required * n :=
    CDEMAbelRecurrenceCertificate.le_ceilDiv_mul
      (Recurrence.weightScale * Recurrence.weightScale) n hn
  have hrequired : required ≤ sqrtWeight n * sqrtWeight n := by
    exact le_ceilSqrt_sq required
  change
    Recurrence.weightScale * Recurrence.weightScale ≤
      sqrtWeight n * sqrtWeight n * n
  exact hscale.trans (Nat.mul_le_mul_right n hrequired)

/-- Closed mathematical table construction used by the reference replay. -/
def kernelData : ReplayKernelData where
  divisorJump := Recurrence.floorJump
  sqrtWeight := sqrtWeight

theorem kernelData_validFor
    (request : ReplayRequest)
    (hlow : 0 < request.low) :
    kernelData.ValidFor request := by
  intro n hn
  have hnLower : request.low ≤ n := (Finset.mem_Ico.mp hn).1
  exact ⟨rfl, sqrtWeight_valid n (hlow.trans_le hnLower)⟩

/-! ## Total Boolean chunk and campaign checks -/

/-- Replay one retained chunk against the closed table construction.

All fields are plain `Nat`, `Int`, and lists.  The test is deliberately
written as a Boolean rather than as an invocation of the propositional
`Accepts` relation. -/
def checkChunk (chunk : Recurrence.Chunk) : Bool :=
  let request := Supervisor.requestOfChunk chunk
  let output := Supervisor.outputOfChunk chunk
  decide request.WellFormed &&
    (decide (0 < request.low) &&
      decide (replayOutput request kernelData = output))

theorem checkChunk_sound
    {chunk : Recurrence.Chunk}
    (checked : checkChunk chunk = true) :
    CDEMAbelReplayAlgorithm.Accepts
      (Supervisor.requestOfChunk chunk)
      (Supervisor.outputOfChunk chunk) := by
  simp only [checkChunk, Bool.and_eq_true, decide_eq_true_eq] at checked
  exact ⟨checked.1, kernelData,
    kernelData_validFor _ checked.2.1, checked.2.2⟩

/-- Complete data-only CDEM finalizer.

Besides the source recurrence check, this fixes both target numerators and
requires a successful closed replay for every retained chunk. -/
def check (certificate : Recurrence.Certificate) : Bool :=
  certificate.check &&
    (decide
      (certificate.signedNumerator = CDEMAbelSource.signedTarget) &&
    (decide
      (certificate.absoluteNumerator = CDEMAbelSource.absoluteTarget) &&
      certificate.chunks.all checkChunk))

private theorem all_checkChunk
    {chunks : List Recurrence.Chunk}
    (checked : chunks.all checkChunk = true) :
    ∀ chunk, chunk ∈ chunks → checkChunk chunk = true := by
  intro chunk hmem
  exact List.all_eq_true.mp checked chunk hmem

/-- A successful closed Boolean check supplies exactly the typed supervisor
acceptance used by the ordinary CDEM source theorem. -/
theorem supervisor_accepts_of_check
    {certificate : Recurrence.Certificate}
    (checked : check certificate = true) :
    Supervisor.Accepts
      Supervisor.canonicalInputBytes Supervisor.canonicalResultBytes := by
  simp only [check, Bool.and_eq_true, decide_eq_true_eq] at checked
  refine ⟨rfl, rfl, certificate, checked.1, checked.2.1,
    checked.2.2.1, ?_⟩
  intro chunk hmem
  exact checkChunk_sound
    (all_checkChunk checked.2.2.2 chunk hmem)

/-- End-to-end ordinary theorem from the total Boolean to the literal source
claim. -/
theorem sourceClaim_of_check
    {certificate : Recurrence.Certificate}
    (checked : check certificate = true) :
    CDEMAbelSource.SourceClaim :=
  Supervisor.sourceClaim_of_acceptance
    (supervisor_accepts_of_check checked)

end SparkInterval.TernaryGoldbach.CDEMAbelClosedReplay
