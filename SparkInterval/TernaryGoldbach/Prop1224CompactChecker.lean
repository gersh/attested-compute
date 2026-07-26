/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactClaimReceipt
import SparkInterval.TernaryGoldbach.Prop1224SourceSemantics

/-!
# Compact native-checker boundary for Helfgott Proposition 12.2.4

The acceptance relation retains only a gap-free rank certificate and the
per-shard MPFR/GMP realization of the literal source rows.  The final
quantified proposition is derived by the existing ordinary Lean theorem.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Prop1224CompactChecker

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

def canonicalInputText : String :=
  "{\"campaign\":\"helfgott-prop-12-2-4-mpfr-v1\"," ++
  "\"rank_lower\":0,\"rank_upper\":3389047618}"

def canonicalInputBytes : ByteArray := canonicalInputText.toUTF8
def canonicalResultBytes : ByteArray := "true".toUTF8

def Accepts (inputBytes resultBytes : ByteArray) : Prop :=
  inputBytes = canonicalInputBytes ∧
    resultBytes = canonicalResultBytes ∧
    ∃ certificate : Prop1224SourceSemantics.Certificate,
      certificate.check = true ∧
        Nonempty
          (Prop1224SourceSemantics.SourceScaleEvidence certificate)

def nativeChecker : NativeCheckerSemantics where
  checkerId :=
    "sparkinterval.ternary-goldbach.helfgott-proposition-12-2-4.compact.v1"
  accepts := Accepts

theorem sourceClaim_of_acceptance
    {inputBytes resultBytes : ByteArray}
    (accepted : nativeChecker.accepts inputBytes resultBytes) :
    Prop1224SourceSemantics.SourceClaim := by
  rcases accepted.2.2 with ⟨certificate, hcheck, ⟨evidence⟩⟩
  exact
    Prop1224SourceSemantics.sourceClaim_of_checked_certificate
      hcheck evidence

theorem acceptanceImpliesSourceClaim (result : MeasuredBlob) :
    AcceptanceImpliesClaim
      nativeChecker result Prop1224SourceSemantics.SourceClaim := by
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
    Prop1224SourceSemantics.SourceClaim :=
  claim_of_compactInputReceipt'
    receipt executableRefinement (acceptanceImpliesSourceClaim result)

end SparkInterval.TernaryGoldbach.Prop1224CompactChecker
