/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.ArchitectureExecution
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.AttestedAcceptance

/-!
# Generic architecture-execution adapter for fixed-width Sqrt218

This module connects the application-neutral architecture boundary to the
fixed-width Sqrt218 native-checker boundary.  It keeps the following arrows
separate:

* an exact formal-machine execution of one measured executable, entry point,
  input byte string, and output byte string;
* an ordinary `ArchitectureRefinesNativeChecker` proof for that executable;
* strict decoding of the complete Sqrt218 result bytes; and
* the exact accepted `ArithmeticResult` required by
  `ArchitectureExecutionRefinesNative`.

The adapter does not construct an architecture execution.  In particular, it
does not reinterpret `AlgorithmReturned` as a trace and does not discharge
`HistoricalReturnedBridgesArchitecture`.  That transitional physical-trust
premise remains separate in `AttestedAcceptance`.

No production bytes or receipts occur in this module.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance

open SparkInterval.Execution
open SparkInterval.Execution.Architecture
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2.ResultWire

namespace ArchitectureExecutionAdapter

/-- The exact pure-Lean SHA-256 measurement function used by Sqrt218 run
statements.  The identifier names the function; all measured blobs also retain
their complete bytes. -/
def sha256MeasurementScheme : MeasurementScheme where
  schemeId := "sparkinterval.sha256-byte-array.v1"
  digestBytes := SparkInterval.Certificate.SHA256.digestByteArray

/-- A byte string measured with its actual length and pure-Lean SHA-256
digest. -/
def measuredBlob (bytes : ByteArray) : MeasuredBlob where
  bytes := bytes
  byteLength := bytes.size
  digest := SparkInterval.Certificate.SHA256.digestByteArray bytes

/-- The constructed measured blob is exact by construction. -/
theorem measuredBlob_exact (bytes : ByteArray) :
    (measuredBlob bytes).Exact sha256MeasurementScheme := by
  exact ⟨rfl, rfl⟩

/-- The exact architecture run used at the native Sqrt218 checker boundary.

The executable, input, and output fields retain their complete byte strings;
the formal machine fixes the semantics identifier and target; and
`entryPoint` fixes the native entry symbol. -/
def measuredRun
    (machine : ArchitectureSemantics)
    (executableBytes : ByteArray)
    (entryPoint : String)
    (inputBytes outputBytes : ByteArray) : MeasuredRun where
  measurementSchemeId := sha256MeasurementScheme.schemeId
  semanticsId := machine.semanticsId
  target := machine.target
  entryPoint := entryPoint
  executable := measuredBlob executableBytes
  input := measuredBlob inputBytes
  output := measuredBlob outputBytes

/-- Every byte field of `measuredRun` has the advertised exact measurement. -/
theorem measuredRun_exactMeasurements
    (machine : ArchitectureSemantics)
    (executableBytes : ByteArray)
    (entryPoint : String)
    (inputBytes outputBytes : ByteArray) :
    MeasuredRun.ExactMeasurements sha256MeasurementScheme
      (measuredRun machine executableBytes entryPoint
        inputBytes outputBytes) := by
  exact {
    schemeId := rfl
    executable := measuredBlob_exact executableBytes
    input := measuredBlob_exact inputBytes
    output := measuredBlob_exact outputBytes
  }

/-- Strict Sqrt218 native-checker acceptance on complete byte strings.

The output must round-trip through the canonical `ResultWire` envelope, have
accepted status, bind the complete input length and SHA-256 digest, and denote
the exact arithmetic result accepted by the abstract native run. -/
def StrictNativeAcceptance
    (nativeRun : ByteArray → NativeOutcome)
    (inputBytes outputBytes : ByteArray) : Prop :=
  ∃ nativeResult : NativeResultRecord,
    decodeResultEnvelope (encodeResultEnvelope outputBytes) =
        .ok (outputBytes, nativeResult) ∧
      acceptedResultCheck nativeResult = true ∧
      nativeResult.inputByteLength = inputBytes.size ∧
      nativeResult.inputSHA256 =
        SparkInterval.Certificate.SHA256.digestByteArray inputBytes ∧
      nativeRun inputBytes = .accepted nativeResult.arithmeticResult

/-- Architecture-neutral checker relation used by the generic refinement
core. -/
def strictNativeChecker
    (implementation : NativeImplementation) : NativeCheckerSemantics where
  checkerId := implementation.identity.neutralContractId
  accepts := StrictNativeAcceptance implementation.run

/-- Exact binding of an existing Sqrt218 implementation relation to one
formal architecture machine and executable image.

The executable, target, formal-machine digest, and entry point are all fixed
by the implementation identity.  The formal-machine digest is intentionally
not conflated with the neutral checker-contract digest.  The final
equivalence is the definition-level connection between Sqrt218's low-level
relation and the generic architecture core.

The historical `RunStatement` still has no dedicated formal-semantics or
entry-point fields.  The execution-closure verifier must bind these identity
fields to the signed closure; until that bridge exists, the separate
`HistoricalReturnedBridgesArchitecture` premise remains responsible for
connecting the physical token to this exact closed selection. -/
structure ExactArchitectureBinding
    (implementation : NativeImplementation) where
  machine : ArchitectureSemantics
  executableBytes : ByteArray
  executableLength :
    executableBytes.size =
      implementation.identity.executableByteLength
  executableIdentity :
    SparkInterval.Certificate.SHA256.digestByteArray executableBytes =
      implementation.identity.executableSHA256.value
  targetIdentity :
    machine.target = implementation.identity.target
  semanticsIdentity :
    machine.semanticsId =
      implementation.identity.formalArchitectureSemanticsSHA256.value
  architectureExecution :
    ∀ inputBytes outputBytes,
      implementation.architectureExecution inputBytes outputBytes ↔
        ArchitectureExecution sha256MeasurementScheme machine
          (measuredRun machine executableBytes implementation.identity.entryPoint
            inputBytes outputBytes)

/-- Strict decoding identifies the checker result with the exact result
retained by the receipt binding.

This theorem uses decoder functionality, rather than assuming that two
records describing the same output bytes are equal. -/
theorem exactNativeAcceptance_of_strictNativeAcceptance
    {implementation : NativeImplementation}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (receiptBound :
      ExactReceiptBinding inputBytes resultEnvelope result)
    (checked :
      StrictNativeAcceptance implementation.run
        inputBytes receiptBound.rawResultBytes) :
    implementation.run inputBytes = .accepted result := by
  rcases checked with
    ⟨nativeResult, decoded, _accepted, _inputLength, _inputDigest,
      nativeAccepted⟩
  have canonical :
      encodeResultEnvelope receiptBound.rawResultBytes = resultEnvelope :=
    decodeResultEnvelope_exact receiptBound.decodedResult
  have receiptDecodedAtCanonical :
      decodeResultEnvelope
          (encodeResultEnvelope receiptBound.rawResultBytes) =
        .ok (receiptBound.rawResultBytes, receiptBound.nativeResult) := by
    rw [canonical]
    exact receiptBound.decodedResult
  have unique :=
    decodeResultEnvelope_unique decoded receiptDecodedAtCanonical
  calc
    implementation.run inputBytes =
        .accepted nativeResult.arithmeticResult := nativeAccepted
    _ = .accepted receiptBound.nativeResult.arithmeticResult := by
      rw [unique.2]
    _ = .accepted result := by
      rw [receiptBound.resultSemantics]

/-- A generic executable-to-checker refinement proof supplies exactly the
Sqrt218 `ArchitectureExecutionRefinesNative` obligation.

This is an ordinary Lean theorem.  Its architecture-execution hypothesis is
not obtained from a receipt here, and the historical physical-token bridge
remains an independent premise at the caller. -/
theorem architectureExecutionRefinesNative
    {implementation : NativeImplementation}
    (binding : ExactArchitectureBinding implementation)
    (refinement :
      ArchitectureRefinesNativeChecker
        sha256MeasurementScheme binding.machine
        (strictNativeChecker implementation)
        (measuredBlob binding.executableBytes)
        implementation.identity.entryPoint) :
    ArchitectureExecutionRefinesNative implementation := by
  intro statement inputBytes resultEnvelope result
    _statementBound receiptBound architectureExecuted
  have genericExecution :
      ArchitectureExecution sha256MeasurementScheme binding.machine
        (measuredRun binding.machine binding.executableBytes
          implementation.identity.entryPoint inputBytes
            receiptBound.rawResultBytes) :=
    (binding.architectureExecution
      inputBytes receiptBound.rawResultBytes).mp architectureExecuted
  have checkerAccepted :=
    refinement.accepts_of_execution
      (run := measuredRun binding.machine binding.executableBytes
        implementation.identity.entryPoint inputBytes
          receiptBound.rawResultBytes)
      rfl rfl genericExecution
  apply exactNativeAcceptance_of_strictNativeAcceptance receiptBound
  simpa [strictNativeChecker, measuredRun, measuredBlob] using
    checkerAccepted

end ArchitectureExecutionAdapter

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance
