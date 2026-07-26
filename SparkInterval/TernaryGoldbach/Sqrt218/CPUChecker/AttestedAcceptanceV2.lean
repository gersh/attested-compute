/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.AttestedAcceptance
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.V2Adapter
import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.Wire

/-!
# Fixed-width Sqrt218 native-to-V2 acceptance bridge

This module is separate from the low-level attestation contract so importing
that contract does not load the complete V2 proof closure.  It supplies the
second implementation arrow:

`native acceptance → architecture-neutral V2 reference acceptance`.

The arrow requires the existing explicit
`V2Adapter.NativeAcceptanceRefinesV2` premise.  Only after that premise is
applied do `completeCheck` and the package-neutral source claim appear.
Neither is stored in the historical token, architecture-execution relation,
or exact receipt binding.  No theorem here uses the registry's formal
execution relation.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.V2Adapter
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.Wire

/-- Explicit reference-level consequence of accepting the same bytes and
result. -/
def V2ReferenceAcceptance
    (inputBytes : ByteArray)
    (result : ArithmeticResult) : Prop :=
  ∃ image : ArchiveImage,
    decodeCanonicalArchiveBytes inputBytes = .ok image ∧
      completeRun image = .ok result

/-- An accepted reference outcome exposes the exact decoded image and complete
V2 reference execution. -/
theorem v2ReferenceAcceptance_of_outcome
    {inputBytes : ByteArray}
    {result : ArithmeticResult}
    (haccepted :
      referenceV2Outcome decodeCanonicalArchiveBytes inputBytes =
        .accepted result) :
    V2ReferenceAcceptance inputBytes result := by
  unfold referenceV2Outcome at haccepted
  cases hdecode :
      decodeCanonicalArchiveBytes inputBytes with
  | error reason =>
      simp only [hdecode] at haccepted
      contradiction
  | ok image =>
      simp only [hdecode] at haccepted
      cases hrun : completeRun image with
      | error reason =>
          simp only [hrun] at haccepted
          contradiction
      | ok actual =>
          simp only [hrun] at haccepted
          have hresult : actual = result :=
            NativeOutcome.accepted.inj haccepted
          subst actual
          exact ⟨image, hdecode, hrun⟩

/-- A successful complete reference run necessarily passed the complete V2
Boolean checker for the same image and result. -/
theorem completeCheck_eq_true_of_completeRun
    {image : ArchiveImage}
    {result : ArithmeticResult}
    (hrun : completeRun image = .ok result) :
    completeCheck image result = true := by
  unfold completeRun at hrun
  cases harithmetic : runArithmetic image with
  | error reason =>
      rw [harithmetic] at hrun
      change Except.error reason = Except.ok result at hrun
      contradiction
  | ok actual =>
      rw [harithmetic] at hrun
      change
        (if completeCheck image actual = true then
          Except.ok actual
        else
          Except.error Reject.arithmeticMismatch) =
            Except.ok result at hrun
      split at hrun
      next hcheck =>
        have hresult : actual = result :=
          Except.ok.inj hrun
        subst actual
        exact hcheck
      next _hcheck =>
        contradiction

/-- Reference acceptance implies the package-neutral source claim. -/
theorem V2ReferenceAcceptance.sourceClaim
    {inputBytes : ByteArray}
    {result : ArithmeticResult}
    (accepted : V2ReferenceAcceptance inputBytes result) :
    TGComputeContracts.Sqrt218.SourceClaim := by
  rcases accepted with ⟨_image, _decoded, checked⟩
  exact sourceClaim_of_completeCheck
    (completeCheck_eq_true_of_completeRun checked)

/-- No-replay semantic acceptance for an already supplied native result.

The exact input bytes must decode, and the exact accepted result must pass
the complete V2 Boolean checker.  In contrast to `V2ReferenceAcceptance`,
this proposition does not ask Lean to recompute `runArithmetic image` or
`completeRun image`. -/
def V2CheckedAcceptance
    (inputBytes : ByteArray)
    (result : ArithmeticResult) : Prop :=
  ∃ image : ArchiveImage,
    decodeCanonicalArchiveBytes inputBytes = .ok image ∧
      completeCheck image result = true

/-- The no-replay checked-result boundary is sufficient for the
package-neutral Sqrt218 source claim. -/
theorem V2CheckedAcceptance.sourceClaim
    {inputBytes : ByteArray}
    {result : ArithmeticResult}
    (accepted : V2CheckedAcceptance inputBytes result) :
    TGComputeContracts.Sqrt218.SourceClaim := by
  rcases accepted with ⟨_image, _decoded, checked⟩
  exact sourceClaim_of_completeCheck checked

/-- Native acceptance plus the independently proved native-to-V2 refinement
gives reference acceptance. -/
theorem v2ReferenceAcceptance_of_nativeAcceptance
    {implementation : NativeImplementation}
    {inputBytes : ByteArray}
    {result : ArithmeticResult}
    (nativeAccepted :
      implementation.run inputBytes = .accepted result)
    (implementationRefines :
      NativeAcceptanceRefinesV2
        decodeCanonicalArchiveBytes implementation.run) :
    V2ReferenceAcceptance inputBytes result :=
  v2ReferenceAcceptance_of_outcome
    (accepted_native_run_is_v2_reference
      implementationRefines nativeAccepted)

/-- Native acceptance plus the weaker checked-result refinement gives the
semantic fact needed for the source theorem, without a second arithmetic
replay. -/
theorem v2CheckedAcceptance_of_nativeAcceptance
    {implementation : NativeImplementation}
    {inputBytes : ByteArray}
    {result : ArithmeticResult}
    (nativeAccepted :
      implementation.run inputBytes = .accepted result)
    (implementationChecks :
      NativeAcceptanceSuppliesV2Check
        decodeCanonicalArchiveBytes implementation.run) :
    V2CheckedAcceptance inputBytes result := by
  simpa [V2CheckedAcceptance] using
    implementationChecks inputBytes result nativeAccepted

/-- Preferred future composition when the execution boundary supplies the
low-level architecture fact directly, without the historical-token bridge. -/
theorem v2ReferenceAcceptance_of_architectureExecution
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
    (implementationRefines :
      NativeAcceptanceRefinesV2
        decodeCanonicalArchiveBytes implementation.run) :
    V2ReferenceAcceptance inputBytes result :=
  v2ReferenceAcceptance_of_nativeAcceptance
    (nativeAcceptance_of_architectureExecution
      statementBound receiptBound architectureExecuted
        architectureRefinement)
    implementationRefines

/-- Preferred future source-claim handoff from a directly attested
architecture execution. -/
theorem sourceClaim_of_architectureExecution
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
    (implementationRefines :
      NativeAcceptanceRefinesV2
        decodeCanonicalArchiveBytes implementation.run) :
    TGComputeContracts.Sqrt218.SourceClaim :=
  (v2ReferenceAcceptance_of_architectureExecution
    statementBound receiptBound architectureExecuted
      architectureRefinement implementationRefines).sourceClaim

/-- Preferred no-local-replay handoff from exact architecture execution to
the source claim.

The implementation boundary supplies the decoded-image `completeCheck` fact
for the result already returned by the native checker.  This route does not
require `completeRun` or a second execution of `runArithmetic` in Lean. -/
theorem v2CheckedAcceptance_of_architectureExecution
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
    (implementationChecks :
      NativeAcceptanceSuppliesV2Check
        decodeCanonicalArchiveBytes implementation.run) :
    V2CheckedAcceptance inputBytes result :=
  v2CheckedAcceptance_of_nativeAcceptance
    (nativeAcceptance_of_architectureExecution
      statementBound receiptBound architectureExecuted
        architectureRefinement)
    implementationChecks

/-- Source-claim composition through the no-replay checked-result boundary.

All expensive execution is represented by the architecture and semantic
refinement premises; this theorem itself is a small symbolic composition. -/
theorem sourceClaim_of_architectureExecution_viaV2Check
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
    (implementationChecks :
      NativeAcceptanceSuppliesV2Check
        decodeCanonicalArchiveBytes implementation.run) :
    TGComputeContracts.Sqrt218.SourceClaim :=
  (v2CheckedAcceptance_of_architectureExecution
    statementBound receiptBound architectureExecuted
      architectureRefinement implementationChecks).sourceClaim

/-- Full conditional composition from the historical token through the
transitional physical bridge, architecture refinement, and native-to-V2
refinement. -/
theorem v2ReferenceAcceptance_of_algorithmReturned
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
    (returned :
      SparkInterval.Execution.AlgorithmReturned statement resultEnvelope)
    (historicalBridge :
      HistoricalReturnedBridgesArchitecture implementation)
    (architectureRefinement :
      ArchitectureExecutionRefinesNative implementation)
    (implementationRefines :
      NativeAcceptanceRefinesV2
        decodeCanonicalArchiveBytes implementation.run) :
    V2ReferenceAcceptance inputBytes result :=
  v2ReferenceAcceptance_of_nativeAcceptance
    (nativeAcceptance_of_algorithmReturned
      statementBound receiptBound returned historicalBridge
        architectureRefinement)
    implementationRefines

/-- Ordinary-Lean source theorem after every explicit boundary has been
discharged. -/
theorem sourceClaim_of_algorithmReturned
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
    (returned :
      SparkInterval.Execution.AlgorithmReturned statement resultEnvelope)
    (historicalBridge :
      HistoricalReturnedBridgesArchitecture implementation)
    (architectureRefinement :
      ArchitectureExecutionRefinesNative implementation)
    (implementationRefines :
      NativeAcceptanceRefinesV2
        decodeCanonicalArchiveBytes implementation.run) :
    TGComputeContracts.Sqrt218.SourceClaim :=
  (v2ReferenceAcceptance_of_algorithmReturned
    statementBound receiptBound returned historicalBridge
      architectureRefinement implementationRefines).sourceClaim

/-- Historical-token composition through the no-replay checked-result
boundary.  `historicalBridge` remains visibly separate because the historical
token itself does not contain architecture semantics. -/
theorem v2CheckedAcceptance_of_algorithmReturned
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
    (returned :
      SparkInterval.Execution.AlgorithmReturned statement resultEnvelope)
    (historicalBridge :
      HistoricalReturnedBridgesArchitecture implementation)
    (architectureRefinement :
      ArchitectureExecutionRefinesNative implementation)
    (implementationChecks :
      NativeAcceptanceSuppliesV2Check
        decodeCanonicalArchiveBytes implementation.run) :
    V2CheckedAcceptance inputBytes result :=
  v2CheckedAcceptance_of_nativeAcceptance
    (nativeAcceptance_of_algorithmReturned
      statementBound receiptBound returned historicalBridge
        architectureRefinement)
    implementationChecks

/-- Current historical-token source-claim route that consumes a supplied V2
check fact instead of replaying `completeRun` locally. -/
theorem sourceClaim_of_algorithmReturned_viaV2Check
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
    (returned :
      SparkInterval.Execution.AlgorithmReturned statement resultEnvelope)
    (historicalBridge :
      HistoricalReturnedBridgesArchitecture implementation)
    (architectureRefinement :
      ArchitectureExecutionRefinesNative implementation)
    (implementationChecks :
      NativeAcceptanceSuppliesV2Check
        decodeCanonicalArchiveBytes implementation.run) :
    TGComputeContracts.Sqrt218.SourceClaim :=
  (v2CheckedAcceptance_of_algorithmReturned
    statementBound receiptBound returned historicalBridge
      architectureRefinement implementationChecks).sourceClaim

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.AttestedAcceptance
