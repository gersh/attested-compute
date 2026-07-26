/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactClaimReceipt
import SparkInterval.TernaryGoldbach.ZetaRHSourceSemantics

/-!
# Compact native-checker boundary for the Platt--Trudgian zeta campaign

The native relation exposes the chunked Hardy-Z/Turing evidence, including
multiplicity-aware global counting.  The finite-RH statement itself is
derived in ordinary Lean and is not part of the receipt payload.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.ZetaRHCompactChecker

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

def canonicalInputText : String :=
  "{\"campaign\":\"platt-trudgian-rh-3e12\"," ++
  "\"multiplicity_count\":12363153437138," ++
  "\"source_height\":3000175332800}"

def canonicalInputBytes : ByteArray := canonicalInputText.toUTF8
def canonicalResultBytes : ByteArray := "true".toUTF8

def Accepts (inputBytes resultBytes : ByteArray) : Prop :=
  inputBytes = canonicalInputBytes ∧
    resultBytes = canonicalResultBytes ∧
    Nonempty ZetaRHSourceSemantics.SourceEvidence

def nativeChecker : NativeCheckerSemantics where
  checkerId :=
    "sparkinterval.ternary-goldbach.platt-trudgian-rh-3e12.compact.v1"
  accepts := Accepts

theorem sourceClaim_of_acceptance
    {inputBytes resultBytes : ByteArray}
    (accepted : nativeChecker.accepts inputBytes resultBytes) :
    ZetaRHSourceSemantics.SourceClaim := by
  rcases accepted.2.2 with ⟨evidence⟩
  exact ZetaRHSourceSemantics.sourceClaim_of_evidence evidence

theorem acceptanceImpliesSourceClaim (result : MeasuredBlob) :
    AcceptanceImpliesClaim
      nativeChecker result ZetaRHSourceSemantics.SourceClaim := by
  intro inputBytes accepted
  exact sourceClaim_of_acceptance accepted

theorem sourceClaim_of_compactRun
    {receiptHash : Digest}
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {pins : CompactRunPins}
    {executable result : MeasuredBlob}
    (receipt :
      CompactInputReceiptExecutionFact
        receiptHash scheme machine pins executable result)
    (executableRefinement :
      ArchitectureRefinesNativeChecker
        scheme machine nativeChecker executable pins.entryPoint) :
    ZetaRHSourceSemantics.SourceClaim :=
  claim_of_compactInputReceipt'
    receipt executableRefinement (acceptanceImpliesSourceClaim result)

end SparkInterval.TernaryGoldbach.ZetaRHCompactChecker
