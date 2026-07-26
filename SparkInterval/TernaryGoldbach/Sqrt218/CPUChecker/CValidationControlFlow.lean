/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CAnchorRefinement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CCompleteValidationRefinement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CResultEncoderRefinement

/-!
# Successful C validation-wrapper control flow for Sqrt218 V2

This module models the successful source-call paths of the static
`tg_sq218_validate_all_v2` function and the public
`tg_sq218_validate_bytes_v2` wrapper.

The fields of `CValidateAllV2Accepted` are deliberately written in source
call order:

1. the five literal production-header comparisons;
2. roster validation;
3. power-layout validation;
4. logarithm-ladder validation;
5. the complete event scan;
6. the endpoint anchor;
7. assignment of the completed local result to `*out`; and
8. return of status zero.

Each called stage retains its returned numeric status and an equality to
zero.  The bytes wrapper additionally retains successful view opening,
canonical source parsing, and its direct forwarding of the validation
status.

This is an architecture-neutral relation over successful source calls.  It
does not claim C compiler, ABI, pointer, or machine semantics, and it does
not evaluate a production archive.
-/

set_option autoImplicit false

namespace
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CValidationControlFlow

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CAnchorRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CArchiveRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CArithmeticRefinement
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CCompleteValidationRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CLogLadderRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPowerLayoutRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CRosterRefinement
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CResultEncoderRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CStepRefinement

/-! ## Literal source constants and zero-status stages -/

def cProductionBound : Nat := 2_000_000
def cProductionReusedBound : Nat := 1_517_397
def cProductionLogSeedAt : Nat := 30
def cProductionLogScale : Nat := 281_474_976_710_656
def cProductionReciprocalScale : Nat := 1_073_741_824

/-- The five comparisons in the first rejection guard of
`tg_sq218_validate_all_v2`. -/
structure CProductionHeaderGuards (image : ArchiveImage) : Prop where
  bound :
    image.header.bound = cProductionBound
  reusedBound :
    image.header.reusedPrimeBound = cProductionReusedBound
  logSeedAt :
    image.header.logSeedAt = cProductionLogSeedAt
  logScale :
    image.header.logScale = cProductionLogScale
  reciprocalScale :
    image.header.reciprocalScale = cProductionReciprocalScale

/-- One source call whose returned `tg_sq218_status` is exactly
`TG_SQ218_OK = 0`, together with the successful-stage evidence. -/
structure CZeroStatusStage (evidence : Prop) : Type where
  status : Nat
  statusZero : status = 0
  accepted : evidence

abbrev CRosterStageEvidence (image : ArchiveImage) : Prop :=
  ∃ nextFactor nextGap previous,
    CRosterAccepted image nextFactor nextGap previous

abbrev CPowerLayoutStageEvidence (image : ArchiveImage) : Prop :=
  ∃ nextPowerRef previousValue,
    CPowerLayoutAccepted image nextPowerRef previousValue

abbrev CScanStageEvidence
    (image : ArchiveImage) (result : CValidationResult) : Prop :=
  ∃ count,
    CScanTrace image count ScanState.initial
        result.arithmeticResult.state ∧
      result.arithmeticResult.state.nextEvent =
        image.header.eventCount

abbrev CAnchorStageEvidence
    (image : ArchiveImage) (result : CValidationResult) : Prop :=
  ∃ root reciprocals,
    CAnchorAccepted
      image
      result.arithmeticResult.state
      result.arithmeticResult.anchorSlack
      root
      reciprocals

/-! ## `tg_sq218_validate_all_v2` -/

/-- Exact successful source-call trace through
`tg_sq218_validate_all_v2`.

Typed Lean inputs represent the successful non-null pointer branch.  The
relation begins with the already-opened view invariant, then records every
source guard and called stage in literal order.  `localResult` is the C local
`result`; `resultAssigned` is the final `*out = result` assignment. -/
structure CValidateAllV2Accepted
    (image : ArchiveImage) (out : CValidationResult) : Type where
  viewHeader :
    headerCheck image = true
  productionGuards :
    CProductionHeaderGuards image
  localResult :
    CValidationResult
  roster :
    CZeroStatusStage (CRosterStageEvidence image)
  powerLayout :
    CZeroStatusStage (CPowerLayoutStageEvidence image)
  logLadder :
    CZeroStatusStage (CLogLadderAccepted image)
  scan :
    CZeroStatusStage
      (CScanStageEvidence image localResult)
  anchor :
    CZeroStatusStage
      (CAnchorStageEvidence image localResult)
  resultAssigned :
    out = localResult
  returnStatus :
    Nat
  returnStatusZero :
    returnStatus = 0

private theorem validationResult_weightedUpper_valid
    (result : CValidationResult) :
    result.arithmeticResult.state.weightedUpper.Valid := by
  constructor
  · simpa [CValidationResult.arithmeticResult, limbBase] using
      UInt64.toNat_lt result.weightedUpperHigh
  · simpa [CValidationResult.arithmeticResult, limbBase] using
      UInt64.toNat_lt result.weightedUpperLow

private theorem validationResult_psiLower_valid
    (result : CValidationResult) :
    result.arithmeticResult.state.psiLower.Valid := by
  constructor
  · simpa [CValidationResult.arithmeticResult, limbBase] using
      UInt64.toNat_lt result.psiLowerHigh
  · simpa [CValidationResult.arithmeticResult, limbBase] using
      UInt64.toNat_lt result.psiLowerLow

/-- The exact successful wrapper control flow constructs the existing
mathematical-pass aggregation, specialized to the arithmetic meaning of the
source result record.  This theorem only rearranges source evidence; it does
not invoke the V2 capstone. -/
theorem CValidateAllV2Accepted.toCompleteValidation
    {image : ArchiveImage} {out : CValidationResult}
    (trace : CValidateAllV2Accepted image out) :
    CCompleteValidationAccepted image out.arithmeticResult := by
  rw [trace.resultAssigned]
  rcases trace.scan.accepted with
    ⟨count, scanTrace, scanComplete⟩
  rcases trace.anchor.accepted with
    ⟨root, reciprocals, anchorAccepted⟩
  have hboundFits : image.header.bound < limbBase := by
    rw [trace.productionGuards.bound]
    norm_num [cProductionBound, limbBase]
  have hscale :
      image.header.reciprocalScale =
        TGComputeContracts.Sqrt218.reciprocalScale := by
    simpa [cProductionReciprocalScale,
      TGComputeContracts.Sqrt218.reciprocalScale] using
      trace.productionGuards.reciprocalScale
  exact {
    productionBound := by
      simpa [cProductionBound,
        TGComputeContracts.Sqrt218.sourceCutoff] using
        trace.productionGuards.bound
    productionReusedPrimeBound := by
      simpa [cProductionReusedBound,
        CCompleteValidationRefinement.productionReusedPrimeBound] using
        trace.productionGuards.reusedBound
    header := trace.viewHeader
    roster := trace.roster.accepted
    powerLayout := trace.powerLayout.accepted
    logLadder := trace.logLadder.accepted
    scan := ⟨count, scanTrace⟩
    scanComplete := scanComplete
    weightedUpperValid :=
      validationResult_weightedUpper_valid trace.localResult
    psiLowerValid :=
      validationResult_psiLower_valid trace.localResult
    anchor :=
      anchorAccepted.refines_cAnchorArithmetic hboundFits hscale
  }

/-! ## `tg_sq218_validate_bytes_v2` -/

/-- Exact successful source-call trace through the bytes wrapper.

The view-open call returns zero, `archive` retains the exact canonical parser
and accessor facts for that view, and the public wrapper returns the status
received directly from `tg_sq218_validate_all_v2`. -/
structure CValidateBytesV2Accepted
    (raw : ByteArray) (out : CValidationResult) : Type where
  viewOpenStatus :
    Nat
  viewOpenStatusZero :
    viewOpenStatus = 0
  archive :
    CArchiveIterationAccepted raw
  validateAll :
    CValidateAllV2Accepted (cDecodedArchive raw) out
  returnedStatus :
    Nat
  returnsValidateAllStatus :
    returnedStatus = validateAll.returnStatus

theorem CValidateBytesV2Accepted.returnedStatusZero
    {raw : ByteArray} {out : CValidationResult}
    (trace : CValidateBytesV2Accepted raw out) :
    trace.returnedStatus = 0 :=
  trace.returnsValidateAllStatus.trans
    trace.validateAll.returnStatusZero

/-- Successful byte-wrapper control flow constructs the existing canonical
raw validation relation for the exact arithmetic value assigned to `*out`. -/
theorem CValidateBytesV2Accepted.toRawCompleteValidation
    {raw : ByteArray} {out : CValidationResult}
    (trace : CValidateBytesV2Accepted raw out) :
    CRawCompleteValidationAccepted raw out.arithmeticResult := by
  exact {
    archive := trace.archive
    validation := trace.validateAll.toCompleteValidation
  }

end
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CValidationControlFlow
