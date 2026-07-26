/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactClaimReceipt
import SparkInterval.TernaryGoldbach.CDEMAbelReplayAlgorithm

/-!
# Compact native-checker boundary for the CDEM Abel campaign

This module removes the CDEM source claim from the trusted execution
boundary.  The native acceptance relation is now the typed operational
supervisor from `CDEMAbelReplayAlgorithm`.  It contains only:

* the closed campaign input and output encodings;
* one checked integer recurrence certificate with the fixed targets; and
* successful typed replay of every retained chunk.

`sourceClaim_of_acceptance` is an ordinary Lean theorem.  It transports the
serial replay invariant through `Chunk.LocallyRealizes` and then through
`CDEMAbelRecurrenceCertificate.sourceClaim_of_checked_local_production_certificate`.
The receipt axiom is not allowed to return either local evidence or
`CDEMAbelSource.SourceClaim` directly.

The remaining implementation obligation is deliberately explicit:
`ArchitectureRefinesNativeChecker ... nativeChecker ...`.  Proving that
obligation requires the exact CPU/GPU architecture, loader, executable, and
compiler/code refinement.  A production receipt supplies only the opaque
architecture execution.  Neither the five-billion-event scan nor its
instruction trace is replayed by the theorem below.

This file defines no axiom.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.CDEMAbelCompactChecker

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

namespace Recurrence

abbrev Certificate :=
  CDEMAbelRecurrenceCertificate.Certificate

abbrev LocalSourceScaleEvidence (certificate : Certificate) :=
  CDEMAbelRecurrenceCertificate.LocalSourceScaleEvidence certificate

end Recurrence

/-- Canonical closed input understood by the production executable. -/
def canonicalInputText : String :=
  "{\"K\":199330,\"N\":5000000000," ++
  "\"weight_scale\":1000000000000000000}"

/-- Canonical compact output.  Pairing is injective and avoids placing a JSON
parser in the mathematical handoff. -/
def canonicalResultText : String :=
  toString
    (Nat.pair CDEMAbelSource.signedTarget CDEMAbelSource.absoluteTarget)

def canonicalInputBytes : ByteArray :=
  canonicalInputText.toUTF8

def canonicalResultBytes : ByteArray :=
  canonicalResultText.toUTF8

/-- Typed operational acceptance of the exact CDEM campaign.

This is not an alias for a mathematical claim or for
`LocalSourceScaleEvidence`: it runs through the pure delta-table, square-
weight, serial-state, and fold model for every retained chunk. -/
def Accepts (inputBytes resultBytes : ByteArray) : Prop :=
  inputBytes = canonicalInputBytes ∧
    resultBytes = canonicalResultBytes ∧
    CDEMAbelReplayAlgorithm.Supervisor.Accepts inputBytes resultBytes

/-- Application-neutral native checker selected for this campaign. -/
def nativeChecker : NativeCheckerSemantics where
  checkerId := "sparkinterval.ternary-goldbach.cdem-table-abel.compact.v1"
  accepts := Accepts

/-- Ordinary checker-to-mathematics theorem. -/
theorem sourceClaim_of_acceptance
    {inputBytes resultBytes : ByteArray}
    (accepted : nativeChecker.accepts inputBytes resultBytes) :
    CDEMAbelSource.SourceClaim :=
  CDEMAbelReplayAlgorithm.Supervisor.sourceClaim_of_acceptance
    accepted.2.2

/-- Universal claim-soundness field used by the compact receipt
composition. -/
theorem acceptanceImpliesSourceClaim (result : MeasuredBlob) :
    AcceptanceImpliesClaim
      nativeChecker result CDEMAbelSource.SourceClaim := by
  intro inputBytes accepted
  exact sourceClaim_of_acceptance accepted

/-- Final compact composition for one CDEM run.

The only run-specific premise is the opaque architecture receipt.  The
architecture-to-checker refinement is an ordinary universal proof obligation
and cannot be replaced by attestation. -/
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
    CDEMAbelSource.SourceClaim :=
  claim_of_compactInputReceipt'
    receipt executableRefinement (acceptanceImpliesSourceClaim result)

end SparkInterval.TernaryGoldbach.CDEMAbelCompactChecker
