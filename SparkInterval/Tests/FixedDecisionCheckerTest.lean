/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.FixedDecisionChecker

/-!
# Fixed decision checker tests

These symbolic tests contain no production receipt or architecture trace.
They check that the result is fixed, decidable reflection is axiom-free, and
the compact composition requires the exact architecture refinement.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.FixedDecisionChecker

open SparkInterval.Execution
open SparkInterval.Execution.Architecture
open SparkInterval.Execution.Architecture.FixedDecisionChecker

private def closedClaim : Prop :=
  6 * 7 = 42

private instance : Decidable closedClaim := by
  unfold closedClaim
  infer_instance

private def checkerId : String :=
  "sparkinterval.tests.fixed-decision.v1"

private def successResult : ByteArray :=
  "success".toUTF8

example
    {inputBytes resultBytes : ByteArray}
    (accepted :
      (nativeChecker closedClaim checkerId successResult).accepts
        inputBytes resultBytes) :
    resultBytes = successResult :=
  result_eq_success
    closedClaim checkerId successResult inputBytes resultBytes accepted

example
    {inputBytes resultBytes : ByteArray}
    (accepted :
      (nativeChecker closedClaim checkerId successResult).accepts
        inputBytes resultBytes) :
    closedClaim :=
  claim_of_acceptance
    closedClaim checkerId successResult inputBytes resultBytes accepted

/-- The application claim is not present in any receipt field.  It enters
only through the fixed checker named in the exact refinement premise. -/
example
    {receiptHash : Digest}
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {pins : CompactRunPins}
    {executable result : MeasuredBlob}
    (receipt :
      CompactInputReceiptExecutionFact
        receiptHash scheme machine pins executable result)
    (refinement :
      ArchitectureRefinesNativeChecker
        scheme machine
        (nativeChecker closedClaim checkerId successResult)
        executable pins.entryPoint) :
    closedClaim :=
  claim_of_compactRun
    closedClaim checkerId successResult receipt refinement

#print axioms result_eq_success
#print axioms claim_of_acceptance
#print axioms acceptanceImpliesClaim
#print axioms claim_of_compactRun

end SparkInterval.Tests.FixedDecisionChecker
