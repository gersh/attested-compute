/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CArithmeticRefinement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CArchiveRefinement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CLogLadderRefinement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CPowerLayoutRefinement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CRosterRefinement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CSourceLoopRefinement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.V2Adapter

/-!
# Complete successful C-source validation refines the V2 semantic check

This module composes the successful source traces for the five mathematical
passes in `tg_sq218_validate_all_v2`:

1. the production header guard;
2. the prime roster;
3. the prime-power layout;
4. the logarithm ladder;
5. the event scan and endpoint anchor.

The theorem is symbolic in an arbitrary decoded image and result.  It never
opens a production archive and never evaluates the production event fold.
The fixed thirty-row logarithm seed table is discharged by its separate
ordinary Lean theorem; it is never conflated with the archive-sized trace.
-/

set_option autoImplicit false

namespace
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CCompleteValidationRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CArithmeticRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CArchiveRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CLogLadderRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPowerLayoutRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CRosterRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CStepRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.V2Adapter
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2
open SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate

/-- Literal `TG_SQ218_PRODUCTION_REUSED_BOUND` source constant. The V2
mathematical kernel does not need this field, but the successful C control
flow checks it and the source trace retains that stronger guard. -/
def productionReusedPrimeBound : Nat := 1_517_397

/-- The exact successful mathematical path through
`tg_sq218_validate_all_v2`.

All archive-sized loops are represented by inductive source traces.  A proof
of this proposition is supplied by source/compiler/architecture refinement,
not by replaying those traces during an ordinary Lean build. -/
structure CCompleteValidationAccepted
    (image : ArchiveImage) (result : ArithmeticResult) : Prop where
  productionBound :
    image.header.bound = TGComputeContracts.Sqrt218.sourceCutoff
  productionReusedPrimeBound :
    image.header.reusedPrimeBound =
      CCompleteValidationRefinement.productionReusedPrimeBound
  header :
    headerCheck image = true
  roster :
    ∃ nextFactor nextGap previous,
      CRosterAccepted image nextFactor nextGap previous
  powerLayout :
    ∃ nextPowerRef previousValue,
      CPowerLayoutAccepted image nextPowerRef previousValue
  logLadder :
    CLogLadderAccepted image
  scan :
    ∃ count,
      CScanTrace image count ScanState.initial result.state
  scanComplete :
    result.state.nextEvent = image.header.eventCount
  weightedUpperValid :
    result.state.weightedUpper.Valid
  psiLowerValid :
    result.state.psiLower.Valid
  anchor :
    cAnchorArithmetic
        result.state.weightedUpper
        result.state.psiLower
        (TGComputeContracts.Sqrt218.reciprocalLower
          image.header.bound (Nat.sqrt image.header.bound))
        (Nat.sqrt image.header.bound)
        image.header.logScale
        image.header.reciprocalScale =
      some result.anchorSlack

private theorem v2HeaderCheck
    {image : ArchiveImage} {result : ArithmeticResult}
    (accepted : CCompleteValidationAccepted image result) :
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.headerCheck
        (V2.archive image result) =
      true := by
  have hheader := accepted.header
  simp only
    [SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.headerCheck,
      decide_eq_true_eq] at hheader
  simp only
    [SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.headerCheck,
      headerCheckAt, V2.archive, decide_eq_true_eq]
  exact
    ⟨True.intro, hheader.1, accepted.productionBound,
      hheader.2.2.2.2.1,
      hheader.2.2.2.2.2.1,
      hheader.2.2.2.2.2.2.1⟩

private theorem v2EventAt_eq_kernelEventAt (image : ArchiveImage) :
    (V2.layout image).eventAt = kernelEventAt image := by
  funext index
  rw [CPowerLayoutRefinement.layout_eventAt]
  rfl

private theorem v2LogLowerAt_eq_kernelLogLowerAt (image : ArchiveImage) :
    (V2.logs image).logLowerAt = kernelLogLowerAt image := by
  funext index
  unfold V2.logs LogRows.Certificate.logLowerAt
    LogRows.Certificate.rowAt kernelLogLowerAt
  change
    ((image.primes.map V2.logRow).getD index default).lower =
      (image.primes.getD index default).logLower
  rw [show (default : LogRows.Row) = V2.logRow default by rfl]
  rw [List.getD_map]
  rfl

private theorem v2LogUpperAt_eq_kernelLogUpperAt (image : ArchiveImage) :
    (V2.logs image).logUpperAt = kernelLogUpperAt image := by
  funext index
  unfold V2.logs LogRows.Certificate.logUpperAt
    LogRows.Certificate.rowAt kernelLogUpperAt
  change
    ((image.primes.map V2.logRow).getD index default).upper =
      (image.primes.getD index default).logUpper
  rw [show (default : LogRows.Row) = V2.logRow default by rfl]
  rw [List.getD_map]
  rfl

private theorem v2FixedRunCheck
    {image : ArchiveImage} {result : ArithmeticResult}
    (accepted : CCompleteValidationAccepted image result) :
    fixedRunCheck (V2.archive image result) = true := by
  rcases accepted.scan with ⟨count, trace⟩
  have hrun :=
    trace.complete_refines_fixedEvents
      accepted.header accepted.scanComplete
  simp only [fixedRunCheck, decide_eq_true_eq]
  simp only [V2.archive, Archive.eventCount, Archive.eventAt,
    Archive.logLowerAt, Archive.logUpperAt,
    CPowerLayoutRefinement.layout_eventCount,
    v2EventAt_eq_kernelEventAt,
    v2LogLowerAt_eq_kernelLogLowerAt,
    v2LogUpperAt_eq_kernelLogUpperAt]
  exact hrun

private theorem v2AnchorCheck
    {image : ArchiveImage} {result : ArithmeticResult}
    (accepted : CCompleteValidationAccepted image result) :
    anchorCheck (V2.archive image result) = true := by
  have hanchor :=
    cAnchorArithmetic_implies_anchorOK
      accepted.header
      accepted.weightedUpperValid
      accepted.psiLowerValid
      accepted.anchor
  simpa [anchorCheck, V2.archive, ScanState.toFixedState] using hanchor

/-- Complete successful C-source validation supplies the exact no-replay V2
Boolean needed by the theorem bridge. -/
theorem CCompleteValidationAccepted.suppliesCompleteCheck
    {image : ArchiveImage} {result : ArithmeticResult}
    (accepted : CCompleteValidationAccepted image result) :
    completeCheck image result = true := by
  rcases accepted.roster with
    ⟨nextFactor, nextGap, previous, roster⟩
  rcases accepted.powerLayout with
    ⟨nextPowerRef, previousValue, powerLayout⟩
  have hroster := roster.refines_primeRosterCheck
  have hlayout := powerLayout.refines_powerLayoutCheck
  have hlogs :=
    accepted.logLadder.refines_logRowsCheck
  have hfixed := v2FixedRunCheck accepted
  have hanchor := v2AnchorCheck accepted
  change
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.run
        (V2.archive image result) =
      true
  simp only
    [SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.run,
      runAt, Bool.and_eq_true]
  exact
    ⟨v2HeaderCheck accepted, hroster, hlayout, hlogs, hfixed, hanchor⟩

/-- The composed source acceptance immediately yields the package-neutral
finite analytic claim; no production computation is performed in Lean. -/
theorem CCompleteValidationAccepted.sourceClaim
    {image : ArchiveImage} {result : ArithmeticResult}
    (accepted : CCompleteValidationAccepted image result) :
    TGComputeContracts.Sqrt218.SourceClaim :=
  sourceClaim_of_completeCheck accepted.suppliesCompleteCheck

/-! ## Exact byte-level handoff -/

/-- Successful source parsing plus all successful mathematical source
passes, for the exact bytes and result returned by the native checker. -/
structure CRawCompleteValidationAccepted
    (raw : ByteArray) (result : ArithmeticResult) : Prop where
  archive :
    CArchiveIterationAccepted raw
  validation :
    CCompleteValidationAccepted (cDecodedArchive raw) result

/-- The exact raw source acceptance supplies a canonical decoded image and
the already checked result.  This is the one-run, no-replay form needed by
the architecture bridge. -/
theorem CRawCompleteValidationAccepted.suppliesV2Check
    {raw : ByteArray} {result : ArithmeticResult}
    (accepted : CRawCompleteValidationAccepted raw result) :
    ∃ image : ArchiveImage,
      Wire.decodeCanonicalArchiveBytes raw = .ok image ∧
        completeCheck image result = true := by
  exact
    ⟨cDecodedArchive raw,
      accepted.archive.decodeCanonicalArchiveBytes,
      accepted.validation.suppliesCompleteCheck⟩

/-- Source/architecture refinement obligation for all accepting native
executions.

The implication is relational: proving it from a compiler/ISA execution does
not evaluate the archive in Lean.  A rejecting execution carries no theorem
authority and therefore needs no exact rejection-code correspondence. -/
def NativeAcceptanceRefinesCCompleteValidation
    (nativeRun : ByteArray → NativeOutcome) : Prop :=
  ∀ raw result,
    nativeRun raw = .accepted result →
      CRawCompleteValidationAccepted raw result

/-- The complete C-source acceptance relation discharges the generic
no-replay V2 acceptance interface used by attested execution. -/
theorem NativeAcceptanceRefinesCCompleteValidation.suppliesV2Check
    {nativeRun : ByteArray → NativeOutcome}
    (hrefines :
      NativeAcceptanceRefinesCCompleteValidation nativeRun) :
    NativeAcceptanceSuppliesV2Check
      Wire.decodeCanonicalArchiveBytes nativeRun := by
  intro raw result haccepted
  exact (hrefines raw result haccepted).suppliesV2Check

end
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CCompleteValidationRefinement
