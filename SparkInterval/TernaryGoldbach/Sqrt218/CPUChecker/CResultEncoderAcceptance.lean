/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.ArchitectureExecutionAdapter
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CResultEncoderRefinement

/-!
# Strict acceptance of the Sqrt218 C result record

This module is the thin composition layer between the source-level model of
`tg_sq218_encode_result_v2` and `StrictNativeAcceptance`.

It deliberately does not run the checker.  The expensive checker result,
agreement of the C SHA-256 implementation with pure Lean SHA-256, and the
architecture execution remain explicit premises.  The theorem here only
discharges the canonical 120-byte record and envelope parsing obligations.

The successful-wrapper guards name the pointer, disjointness, `size_t`
round-trip, and SHA output-width conditions checked by
`tg_sq218_verify_snapshot_v2` and
`tg_sq218_validate_snapshot_to_record_v2`.  Keeping them in the source-facing
predicate prevents a source refinement from silently assuming that a C call
reached the encoder.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CResultEncoderAcceptance

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance.ArchitectureExecutionAdapter
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CResultEncoderRefinement
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire

/-- The half-open interval overlap test used by
`tg_pointer_ranges_overlap`, stated over mathematical naturals after the
source's representability and no-wrap guards have succeeded. -/
def cPointerRangesDisjoint
    (leftStart leftLength rightStart rightLength : Nat) : Prop :=
  ¬(leftStart < rightStart + rightLength ∧
    rightStart < leftStart + leftLength)

/-- Pointer facts required for a successful call to
`tg_sq218_validate_snapshot_to_record_v2`.

`pointerMax` represents `UINTPTR_MAX`; the three endpoint fields model the
source checks `UINTPTR_MAX - start < width`; and the representability fields
model the checked `size_t`-to-`uintptr_t` conversions.

The width of the C enum object is explicit instead of being assumed to be
four bytes. -/
structure CWrapperPointerGuards (inputByteLength : Nat) : Type where
  pointerMax : Nat
  snapshotAddress : Nat
  recordAddress : Nat
  checkerStatusAddress : Nat
  checkerStatusByteLength : Nat
  snapshotNonNull : snapshotAddress ≠ 0
  recordNonNull : recordAddress ≠ 0
  checkerStatusNonNull : checkerStatusAddress ≠ 0
  checkerStatusByteLengthPositive : 0 < checkerStatusByteLength
  snapshotAddressRepresentable : snapshotAddress ≤ pointerMax
  recordAddressRepresentable : recordAddress ≤ pointerMax
  checkerStatusAddressRepresentable :
    checkerStatusAddress ≤ pointerMax
  snapshotLengthRepresentable : inputByteLength ≤ pointerMax
  recordLengthRepresentable : nativeResultByteWidth ≤ pointerMax
  checkerStatusLengthRepresentable :
    checkerStatusByteLength ≤ pointerMax
  snapshotEndpointNoWrap :
    inputByteLength ≤ pointerMax - snapshotAddress
  recordEndpointNoWrap :
    nativeResultByteWidth ≤ pointerMax - recordAddress
  checkerStatusEndpointNoWrap :
    checkerStatusByteLength ≤ pointerMax - checkerStatusAddress
  snapshotRecordDisjoint :
    cPointerRangesDisjoint
      snapshotAddress inputByteLength
      recordAddress nativeResultByteWidth
  snapshotCheckerStatusDisjoint :
    cPointerRangesDisjoint
      snapshotAddress inputByteLength
      checkerStatusAddress checkerStatusByteLength
  recordCheckerStatusDisjoint :
    cPointerRangesDisjoint
      recordAddress nativeResultByteWidth
      checkerStatusAddress checkerStatusByteLength

/-- Additional pointer guards in the outer flat
`tg_sq218_verify_snapshot_v2` ABI.  Its public status output is exactly one
`uint32_t`; the inner enum status object remains represented by the inherited
guards above. -/
structure CFlatWrapperPointerGuards
    (inputByteLength : Nat) : Type
    extends CWrapperPointerGuards inputByteLength where
  statusOutAddress : Nat
  statusOutNonNull : statusOutAddress ≠ 0
  statusOutAddressRepresentable : statusOutAddress ≤ pointerMax
  statusOutLengthRepresentable : 4 ≤ pointerMax
  statusOutEndpointNoWrap : 4 ≤ pointerMax - statusOutAddress
  snapshotStatusOutDisjoint :
    cPointerRangesDisjoint
      snapshotAddress inputByteLength statusOutAddress 4
  recordStatusOutDisjoint :
    cPointerRangesDisjoint
      recordAddress nativeResultByteWidth statusOutAddress 4

/-- Value-level guards required before the C wrapper reaches validation and
the result encoder.

The exact equality is the two checked casts
`uint64_t -> size_t -> uint64_t`, expressed at the mathematical-value level.
The bit-length guard is the source check needed before multiplying the input
length by eight in SHA-256. -/
structure CSuccessfulWrapperGuards
    (inputBytes : ByteArray)
    (encodedInputByteLength : UInt64)
    (snapshotSHA256 : ByteArray) : Type
    extends CFlatWrapperPointerGuards inputBytes.size where
  sizeTMax : Nat
  inputFitsSizeT : inputBytes.size ≤ sizeTMax
  inputLengthRoundTrip :
    encodedInputByteLength.toNat = inputBytes.size
  sha256BitLengthGuard :
    encodedInputByteLength.toNat ≤ (2 ^ 64 - 1) / 8
  sha256OutputWidth : snapshotSHA256.size = 32

/-- Explicit source-level SHA premise.

This is intentionally not a field of `StrictNativeAcceptance` and is not
proved by the record encoder refinement.  A separate refinement of the C
`tg_sha256` routine must supply it. -/
def CSourceSHA256Correct
    (inputBytes snapshotSHA256 : ByteArray) : Prop :=
  byteArrayLowerHex snapshotSHA256 =
    SparkInterval.Certificate.SHA256.digestByteArray inputBytes

/-- A successful, status-zero C result record satisfies the complete strict
native acceptance relation.

The expensive `nativeRun` fact and the correctness of the C SHA-256 bytes are
visible premises.  This theorem performs no certificate replay. -/
theorem strictNativeAcceptance_of_cResultV2
    (nativeRun : ByteArray → NativeOutcome)
    (inputBytes : ByteArray)
    (encodedInputByteLength : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray)
    (guards :
      CSuccessfulWrapperGuards
        inputBytes encodedInputByteLength snapshotSHA256)
    (sha256Correct :
      CSourceSHA256Correct inputBytes snapshotSHA256)
    (nativeAccepted :
      nativeRun inputBytes =
        .accepted
          (expectedRecord
            0 encodedInputByteLength result snapshotSHA256).arithmeticResult) :
    StrictNativeAcceptance nativeRun inputBytes
      (cEncodeResultV2
        0 encodedInputByteLength result snapshotSHA256) := by
  let record :=
    expectedRecord 0 encodedInputByteLength result snapshotSHA256
  refine ⟨record, ?_, ?_, ?_, ?_, ?_⟩
  · apply decodeResultEnvelope_encode_of_decodeNative
    exact decodeNativeResultBytes_cEncodeResultV2
      0 encodedInputByteLength result snapshotSHA256
        guards.sha256OutputWidth (by norm_num)
  · simp [record, acceptedResultCheck, expectedRecord]
  · simpa [record, expectedRecord] using
      guards.inputLengthRoundTrip
  · simpa [record, expectedRecord, CSourceSHA256Correct] using
      sha256Correct
  · simpa [record] using nativeAccepted

/-- Source-facing specialization of `strictNativeAcceptance_of_cResultV2`.

The successful C validation structure is interpreted once by
`CValidationResult.arithmeticResult`; the result-encoder theorem proves that
the exact 120-byte record denotes that same value. -/
theorem strictNativeAcceptance_of_successful_cResultV2
    (nativeRun : ByteArray → NativeOutcome)
    (inputBytes : ByteArray)
    (encodedInputByteLength : UInt64)
    (result : CValidationResult)
    (snapshotSHA256 : ByteArray)
    (guards :
      CSuccessfulWrapperGuards
        inputBytes encodedInputByteLength snapshotSHA256)
    (sha256Correct :
      CSourceSHA256Correct inputBytes snapshotSHA256)
    (nativeAccepted :
      nativeRun inputBytes = .accepted result.arithmeticResult) :
    StrictNativeAcceptance nativeRun inputBytes
      (cEncodeResultV2
        0 encodedInputByteLength result snapshotSHA256) := by
  apply strictNativeAcceptance_of_cResultV2
    nativeRun inputBytes encodedInputByteLength result snapshotSHA256
      guards sha256Correct
  simpa using nativeAccepted

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CResultEncoderAcceptance
