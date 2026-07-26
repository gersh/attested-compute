/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CCompleteValidationRefinement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CResultEncoderAcceptance
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CSHA256Refinement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CValidationControlFlow

/-!
# Successful pure C entry composition for Sqrt218

This module packages the successful source-facing obligations of
`tg_sq218_verify_snapshot_v2` without evaluating the checker:

* pointer, width, and non-aliasing guards;
* exact source SHA-256;
* canonical parsing and successful mathematical validation;
* the source validation result and its receipt-level arithmetic meaning; and
* the exact 120-byte source result encoder.

A compiler/ISA proof should construct this trace from an accepting execution.
The theorems below only project and compose its fields.
-/

set_option autoImplicit false

namespace
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPureEntryComposition

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance.ArchitectureExecutionAdapter
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CCompleteValidationRefinement
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CResultEncoderAcceptance
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CResultEncoderRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CSHA256Refinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CValidationControlFlow
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.V2Adapter

/-- All successful source-level facts for one pure-entry invocation.

This is intentionally a relation, not an executable Lean checker. Constructing
it from machine execution is the compiler/architecture proof obligation and
does not entail local replay of the production archive. -/
structure CSuccessfulPureEntryTrace
    (inputBytes : ByteArray)
    (encodedInputByteLength : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 outputBytes : ByteArray) : Type where
  guards :
    CSuccessfulWrapperGuards
      inputBytes encodedInputByteLength snapshotSHA256
  sha256Execution :
    ConcreteExecutionMatchesSource inputBytes snapshotSHA256
  validation :
    CValidateBytesV2Accepted inputBytes result
  resultEncoderExecution :
    outputBytes =
      cEncodeResultV2
        0 encodedInputByteLength result snapshotSHA256

/-- Exact source relation to use as the `NativeCheckerSemantics` target of
the VST/CompCert/ELF/x86 proof chain. -/
def successfulPureEntryChecker
    (checkerId : String) :
    SparkInterval.Execution.Architecture.NativeCheckerSemantics where
  checkerId := checkerId
  accepts := fun inputBytes outputBytes =>
    ∃ encodedInputByteLength : UInt64,
      ∃ result : CValidationResult,
      ∃ snapshotSHA256 : ByteArray,
        Nonempty
          (CSuccessfulPureEntryTrace inputBytes
            encodedInputByteLength result snapshotSHA256 outputBytes)

namespace CSuccessfulPureEntryTrace

/-- The sole source-to-concrete SHA execution fact, combined with the generic
source-algorithm refinement, supplies the wrapper's exact digest premise. -/
theorem sha256Correct
    {inputBytes : ByteArray}
    {encodedInputByteLength : UInt64}
    {result : CValidationResult}
    {snapshotSHA256 outputBytes : ByteArray}
    (trace :
      CSuccessfulPureEntryTrace inputBytes
        encodedInputByteLength result snapshotSHA256 outputBytes) :
    CSourceSHA256Correct inputBytes snapshotSHA256 := by
  simpa [CSourceSHA256Correct] using
    digest_correct_of_concreteExecution
      inputBytes snapshotSHA256 trace.sha256Execution

/-- The successful pure entry's exact encoded bytes satisfy strict native
result acceptance. -/
theorem strictNativeAcceptance
    {nativeRun : ByteArray → NativeOutcome}
    {inputBytes : ByteArray}
    {encodedInputByteLength : UInt64}
    {result : CValidationResult}
    {snapshotSHA256 outputBytes : ByteArray}
    (trace :
      CSuccessfulPureEntryTrace inputBytes
        encodedInputByteLength result snapshotSHA256 outputBytes)
    (nativeAccepted :
      nativeRun inputBytes = .accepted result.arithmeticResult) :
    StrictNativeAcceptance nativeRun inputBytes outputBytes := by
  rw [trace.resultEncoderExecution]
  exact
    strictNativeAcceptance_of_successful_cResultV2
      nativeRun inputBytes encodedInputByteLength result snapshotSHA256
        trace.guards trace.sha256Correct nativeAccepted

/-- Strict decoding of the same exact raw output in a receipt fixes the
arithmetic result represented by the successful source trace. -/
theorem resultMeaning_of_receipt
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {expectedResult : ArithmeticResult}
    {encodedInputByteLength : UInt64}
    {result : CValidationResult}
    {snapshotSHA256 : ByteArray}
    (receiptBound :
      ExactReceiptBinding inputBytes resultEnvelope expectedResult)
    (trace :
      CSuccessfulPureEntryTrace inputBytes
        encodedInputByteLength result snapshotSHA256
          receiptBound.rawResultBytes) :
    result.arithmeticResult = expectedResult := by
  have decoded :
      SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.decodeResultEnvelope
          (SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.encodeResultEnvelope
            receiptBound.rawResultBytes) =
        .ok
          (receiptBound.rawResultBytes,
            expectedRecord
              0 encodedInputByteLength result snapshotSHA256) := by
    rw [trace.resultEncoderExecution]
    apply
      SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.decodeResultEnvelope_encode_of_decodeNative
    exact
      decodeNativeResultBytes_cEncodeResultV2
        0 encodedInputByteLength result snapshotSHA256
          trace.guards.sha256OutputWidth (by norm_num)
  have canonicalEnvelope :
      SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.encodeResultEnvelope
          receiptBound.rawResultBytes =
        resultEnvelope :=
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.decodeResultEnvelope_exact
      receiptBound.decodedResult
  have decodedSigned := decoded
  rw [canonicalEnvelope] at decodedSigned
  have recordEquality :=
    SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire.decodeResultEnvelope_unique
      decodedSigned receiptBound.decodedResult
  calc
    result.arithmeticResult =
        (expectedRecord
          0 encodedInputByteLength result snapshotSHA256).arithmeticResult := by
      simp
    _ = receiptBound.nativeResult.arithmeticResult := by
      rw [recordEquality.2]
    _ = expectedResult := receiptBound.resultSemantics

/-- A successful pure-entry trace supplies the exact decoded-image semantic
check for the result it returned. -/
theorem v2CheckedAcceptance
    {inputBytes : ByteArray}
    {encodedInputByteLength : UInt64}
    {result : CValidationResult}
    {snapshotSHA256 outputBytes : ByteArray}
    (trace :
      CSuccessfulPureEntryTrace inputBytes
        encodedInputByteLength result snapshotSHA256 outputBytes) :
    ∃ image : ArchiveImage,
      Wire.decodeCanonicalArchiveBytes inputBytes = .ok image ∧
        completeCheck image result.arithmeticResult = true :=
  trace.validation.toRawCompleteValidation.suppliesV2Check

/-- The successful pure-entry trace proves the package-neutral finite source
claim without a second execution of the checker. -/
theorem sourceClaim
    {inputBytes : ByteArray}
    {encodedInputByteLength : UInt64}
    {result : CValidationResult}
    {snapshotSHA256 outputBytes : ByteArray}
    (trace :
      CSuccessfulPureEntryTrace inputBytes
        encodedInputByteLength result snapshotSHA256 outputBytes) :
    TGComputeContracts.Sqrt218.SourceClaim :=
  trace.validation.toRawCompleteValidation.validation.sourceClaim

end CSuccessfulPureEntryTrace

namespace successfulPureEntryChecker

/-- The same target directly supplies the package-neutral source claim. -/
theorem sourceClaim
    {checkerId : String}
    {inputBytes outputBytes : ByteArray}
    (accepted :
      (successfulPureEntryChecker checkerId).accepts
        inputBytes outputBytes) :
    TGComputeContracts.Sqrt218.SourceClaim := by
  rcases accepted with
    ⟨encodedInputByteLength, result, snapshotSHA256, ⟨trace⟩⟩
  exact trace.sourceClaim

end successfulPureEntryChecker

end
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPureEntryComposition
