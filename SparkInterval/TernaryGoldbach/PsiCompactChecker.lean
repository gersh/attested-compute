/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactClaimReceipt
import SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate

/-!
# Compact native-checker boundary for CH25 Lemma 9.2

Acceptance contains the event-gap coverage, directed prime-log enclosures,
and integer endpoint guards emitted by the physical campaign.  It contains
neither `Chebyshev.psi` prefix rows nor the final real-variable inequality.
Those follow in ordinary Lean from
`PsiPrimePowerCertificate.sourceClaim_of_gap_evidence`.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.PsiCompactChecker

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

def canonicalInputText : String :=
  "{\"campaign\":\"ch25-psi-lemma-9-2-v1\"," ++
  "\"source_lower\":1,\"source_upper\":10000000000000}"

def canonicalInputBytes : ByteArray := canonicalInputText.toUTF8
def canonicalResultBytes : ByteArray := "true".toUTF8

def Accepts (inputBytes resultBytes : ByteArray) : Prop :=
  inputBytes = canonicalInputBytes ∧
    resultBytes = canonicalResultBytes ∧
    Nonempty PsiPrimePowerCertificate.GapSourceScaleEvidence

def nativeChecker : NativeCheckerSemantics where
  checkerId := "sparkinterval.ternary-goldbach.ch25-psi-lemma-9-2.compact.v1"
  accepts := Accepts

theorem sourceClaim_of_acceptance
    {inputBytes resultBytes : ByteArray}
    (accepted : nativeChecker.accepts inputBytes resultBytes) :
    PsiSourceSemantics.SourceClaim := by
  rcases accepted.2.2 with ⟨evidence⟩
  exact PsiPrimePowerCertificate.sourceClaim_of_gap_evidence evidence

theorem acceptanceImpliesSourceClaim (result : MeasuredBlob) :
    AcceptanceImpliesClaim
      nativeChecker result PsiSourceSemantics.SourceClaim := by
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
    PsiSourceSemantics.SourceClaim :=
  claim_of_compactInputReceipt'
    receipt executableRefinement (acceptanceImpliesSourceClaim result)

end SparkInterval.TernaryGoldbach.PsiCompactChecker
