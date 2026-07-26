/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.AttestedAcceptanceV2
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CCompleteValidationRefinement
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CPureEntryComposition

/-!
# Sqrt218 C-source acceptance to attested architecture composition

This is the thin theorem-level join between:

* exact architecture execution of the measured bytes;
* architecture-to-source refinement for the pure C entry; and
* the successful C parser and mathematical source traces.

The result passes through `NativeAcceptanceSuppliesV2Check`.  Consequently
this module never asks Lean to replay `runArithmetic`, `completeRun`, or the
production event table.
-/

set_option autoImplicit false

namespace
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CArchitectureComposition

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance.ArchitectureExecutionAdapter
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CCompleteValidationRefinement
open
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPureEntryComposition
open SparkInterval.Execution.Architecture

/-- Direct future handoff from an exact architecture execution through the
proved C-source acceptance boundary to the package-neutral source claim. -/
theorem sourceClaim_of_architectureExecution_viaCComplete
    {implementation : NativeImplementation}
    {statement : SparkInterval.Execution.RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (statementBound :
      ClosedStatementBinding implementation statement
        inputBytes resultEnvelope)
    (receiptBound :
      ExactReceiptBinding inputBytes resultEnvelope result)
    (architectureExecuted :
      implementation.architectureExecution
        inputBytes receiptBound.rawResultBytes)
    (architectureRefinement :
      ArchitectureExecutionRefinesNative implementation)
    (sourceRefinement :
      NativeAcceptanceRefinesCCompleteValidation implementation.run) :
    TGComputeContracts.Sqrt218.SourceClaim :=
  sourceClaim_of_architectureExecution_viaV2Check
    statementBound receiptBound architectureExecuted
      architectureRefinement sourceRefinement.suppliesV2Check

/-- Single low-level refinement target for the actual pure entry.

For an exact statement/result binding and exact architecture execution, the
compiler/loader/ISA proof must recover the source `uint64_t` input length,
source validation result, and 32 digest bytes, and construct the complete
successful pure-entry trace for the exact measured output bytes. Exact result
meaning is then derived from the source encoder and the receipt decoder.

This proposition performs no execution. It is the precise theorem that a
future VST/CompCert/ELF/x86 development must establish. -/
def ArchitectureExecutionSuppliesSuccessfulPureEntry
    (implementation : NativeImplementation) : Prop :=
  ∀ {statement : SparkInterval.Execution.RunStatement}
      {inputBytes : ByteArray}
      {resultEnvelope : String}
      {result : ArithmeticResult},
    (_statementBound :
      ClosedStatementBinding implementation statement
        inputBytes resultEnvelope) →
      (receiptBound :
        ExactReceiptBinding inputBytes resultEnvelope result) →
      implementation.architectureExecution
          inputBytes receiptBound.rawResultBytes →
      ∃ encodedInputByteLength : UInt64,
        ∃ cResult : CResultEncoderRefinement.CValidationResult,
        ∃ snapshotSHA256 : ByteArray,
          Nonempty
            (CSuccessfulPureEntryTrace inputBytes
              encodedInputByteLength cResult snapshotSHA256
              receiptBound.rawResultBytes)

/-- A generic executable-to-source-checker refinement theorem supplies the
single Sqrt218 pure-entry architecture obligation. -/
theorem architectureExecutionSuppliesSuccessfulPureEntry_of_checkerRefinement
    {implementation : NativeImplementation}
    (binding : ExactArchitectureBinding implementation)
    (refinement :
      ArchitectureRefinesNativeChecker
        sha256MeasurementScheme binding.machine
        (successfulPureEntryChecker
          implementation.identity.neutralContractId)
        (measuredBlob binding.executableBytes)
        implementation.identity.entryPoint) :
    ArchitectureExecutionSuppliesSuccessfulPureEntry implementation := by
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
  simpa [successfulPureEntryChecker, measuredRun, measuredBlob] using
    checkerAccepted

/-- Direct architecture-to-source composition through the complete pure-entry
trace. This is the shortest final route once the compiler/ISA theorem above is
available. -/
theorem sourceClaim_of_architectureExecution_viaPureEntry
    {implementation : NativeImplementation}
    {statement : SparkInterval.Execution.RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (statementBound :
      ClosedStatementBinding implementation statement
        inputBytes resultEnvelope)
    (receiptBound :
      ExactReceiptBinding inputBytes resultEnvelope result)
    (architectureExecuted :
      implementation.architectureExecution
        inputBytes receiptBound.rawResultBytes)
    (refinement :
      ArchitectureExecutionSuppliesSuccessfulPureEntry implementation) :
    TGComputeContracts.Sqrt218.SourceClaim := by
  rcases refinement statementBound receiptBound architectureExecuted with
    ⟨encodedInputByteLength, cResult, snapshotSHA256,
      ⟨trace⟩⟩
  exact trace.sourceClaim

/-- Transitional historical-token composition.

This theorem keeps the temporary token-to-architecture bridge visible. A
future receipt authority returning the architecture fact directly removes
only that premise; it does not alter the source or arithmetic proof. -/
theorem sourceClaim_of_algorithmReturned_viaCComplete
    {implementation : NativeImplementation}
    {statement : SparkInterval.Execution.RunStatement}
    {inputBytes : ByteArray}
    {resultEnvelope : String}
    {result : ArithmeticResult}
    (statementBound :
      ClosedStatementBinding implementation statement
        inputBytes resultEnvelope)
    (receiptBound :
      ExactReceiptBinding inputBytes resultEnvelope result)
    (historicalBridge :
      HistoricalReturnedBridgesArchitecture implementation)
    (architectureRefinement :
      ArchitectureExecutionRefinesNative implementation)
    (sourceRefinement :
      NativeAcceptanceRefinesCCompleteValidation implementation.run)
    (returned :
      SparkInterval.Execution.AlgorithmReturned
        statement resultEnvelope) :
    TGComputeContracts.Sqrt218.SourceClaim :=
  sourceClaim_of_algorithmReturned_viaV2Check
    statementBound receiptBound returned historicalBridge
      architectureRefinement sourceRefinement.suppliesV2Check

end
  SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CArchitectureComposition
