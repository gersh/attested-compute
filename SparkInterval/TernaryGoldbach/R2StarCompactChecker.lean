/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactClaimReceipt
import SparkInterval.TernaryGoldbach.R2StarSourceSemantics

/-!
# Compact native-checker boundary for Ramaré--Zúñiga Lemma 6.2

Acceptance contains a checked chunk chain and exact factor-support/logarithm
realization evidence.  The source-shaped real inequality is an ordinary Lean
consequence and is not a field returned by the execution trust boundary.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.R2StarCompactChecker

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

def canonicalInputText : String :=
  "{\"campaign\":\"ramare-zuniga-lemma-6-2-v1\"," ++
  "\"source_lower\":1,\"source_upper_exclusive\":21000000001}"

def canonicalInputBytes : ByteArray := canonicalInputText.toUTF8
def canonicalResultBytes : ByteArray := "true".toUTF8

def Accepts (inputBytes resultBytes : ByteArray) : Prop :=
  inputBytes = canonicalInputBytes ∧
    resultBytes = canonicalResultBytes ∧
    ∃ certificate : R2StarSourceSemantics.Certificate,
      certificate.check = true ∧
        Nonempty (R2StarSourceSemantics.SourceScaleEvidence certificate)

def nativeChecker : NativeCheckerSemantics where
  checkerId :=
    "sparkinterval.ternary-goldbach.ramare-zuniga-lemma-6-2.compact.v1"
  accepts := Accepts

theorem sourceClaim_of_acceptance
    {inputBytes resultBytes : ByteArray}
    (accepted : nativeChecker.accepts inputBytes resultBytes) :
    R2StarSourceSemantics.SourceClaim := by
  rcases accepted.2.2 with ⟨certificate, hcheck, ⟨evidence⟩⟩
  exact
    R2StarSourceSemantics.sourceClaim_of_checked_certificate
      hcheck evidence

theorem acceptanceImpliesSourceClaim (result : MeasuredBlob) :
    AcceptanceImpliesClaim
      nativeChecker result R2StarSourceSemantics.SourceClaim := by
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
    R2StarSourceSemantics.SourceClaim :=
  claim_of_compactInputReceipt'
    receipt executableRefinement (acceptanceImpliesSourceClaim result)

end SparkInterval.TernaryGoldbach.R2StarCompactChecker
