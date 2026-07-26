/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactClaimReceipt
import SparkInterval.TernaryGoldbach.GoldbachSourceSemantics

/-!
# Compact native-checker boundary for Helfgott--Platt finite Goldbach

The native acceptance relation retains the exact closed finalizer input and
result together with `GoldbachSourceSemantics.CheckedSourceEvidence`.  That
worker-shaped evidence keeps the two finite branches separate:

* binary Goldbach through `4 * 10^18`; and
* a finite prime ladder whose first/adjacent/last arithmetic passes its
  decidable checker.

It does not contain the final ternary `SourceClaim`.  Ordinary Lean derives
the ladder's parity-sensitive interval coverage and then the three-prime
claim via `sourceClaim_of_checked_evidence`.

This is a multi-branch campaign.  Consequently a proof of
`ArchitectureRefinesNativeChecker ... nativeChecker ...` must establish that
the finalizer authenticates and checks both child artifact streams.  A signed
finalizer result by itself cannot manufacture `CheckedSourceEvidence`.

This file defines no axiom and performs no production replay.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.GoldbachCompactChecker

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

/-- Exact closed input of the source-height Helfgott--Platt finalizer.

The child source identities and artifact kinds are part of the mathematical
handoff rather than deployment-only metadata. -/
def canonicalInputText : String :=
  "{\"binary_artifact_kind\":\"sparkinterval.goldbach-gpu-aggregate.v1\"," ++
  "\"binary_campaign\":" ++
    "\"goldbach-gpu-hardened-production-65536-leaf-v2\"," ++
  "\"binary_source_identity_sha256\":" ++
    "\"9727bb9c4f2c1e1fed9ed164ed756734c2e16ce2d338aedda858aad964ecdd55\"," ++
  "\"campaign\":\"helfgott-platt-goldbach-gpu-v1\"," ++
  "\"combined_artifact_kind\":" ++
    "\"tg_goldbach_gpu_plus_ladder_result_v1\"," ++
  "\"ladder_artifact_kind\":" ++
    "\"tg_goldbach_ladder_parallel_aggregate_v1\"," ++
  "\"ladder_campaign\":\"tg_goldbach_ladder_parallel_campaign_v1\"," ++
  "\"ladder_native_source_sha256\":" ++
    "\"02ffa92bca580146af32c176f8e6014f2e88d61a5e1a190114ea3ad5a524cbf6\"}"

/-- The successful source finalizer emits exactly these four bytes. -/
def canonicalResultText : String := "true"

def canonicalInputBytes : ByteArray :=
  canonicalInputText.toUTF8

def canonicalResultBytes : ByteArray :=
  canonicalResultText.toUTF8

/-- Low-level semantic acceptance of the exact source-height campaign.

The evidence contains the checked binary and ladder branches, never their
derived ternary-Goldbach `SourceClaim`. -/
def Accepts (inputBytes resultBytes : ByteArray) : Prop :=
  inputBytes = canonicalInputBytes ∧
    resultBytes = canonicalResultBytes ∧
    Nonempty GoldbachSourceSemantics.CheckedSourceEvidence

/-- Application-neutral native checker selected for this campaign. -/
def nativeChecker : NativeCheckerSemantics where
  checkerId :=
    "sparkinterval.ternary-goldbach.helfgott-platt-goldbach.compact.v1"
  accepts := Accepts

/-- Ordinary checked-evidence-to-source-claim theorem. -/
theorem sourceClaim_of_acceptance
    {inputBytes resultBytes : ByteArray}
    (accepted : nativeChecker.accepts inputBytes resultBytes) :
    GoldbachSourceSemantics.SourceClaim := by
  rcases accepted with ⟨_input, _result, ⟨evidence⟩⟩
  exact GoldbachSourceSemantics.sourceClaim_of_checked_evidence evidence

/-- Universal checker-to-mathematics field used by compact receipt
composition. -/
theorem acceptanceImpliesSourceClaim (result : MeasuredBlob) :
    AcceptanceImpliesClaim nativeChecker result
      GoldbachSourceSemantics.SourceClaim := by
  intro inputBytes accepted
  exact sourceClaim_of_acceptance accepted

/-- Final compact composition for one Helfgott--Platt production run.

The receipt hides the large input and architecture trace.  The universal
executable refinement remains responsible for both authenticated child
branches and the finalizer's exact evidence construction. -/
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
    GoldbachSourceSemantics.SourceClaim :=
  claim_of_compactInputReceipt'
    receipt executableRefinement (acceptanceImpliesSourceClaim result)

end SparkInterval.TernaryGoldbach.GoldbachCompactChecker
