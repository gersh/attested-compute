/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactClaimReceipt
import SparkInterval.TernaryGoldbach.Goldbach10Pow27CampaignSemantics

/-!
# Compact native-checker boundary for finite Goldbach below `10^27`

This is the lowered finite endpoint used by the analytic capstone.  It is
distinct from the historical Helfgott--Platt range, although both campaigns
share binary-Goldbach and prime-ladder proof components.

The native acceptance relation contains the exact closed finalizer input,
the four-byte successful result, and the low-level checked binary/ladder
evidence.  It does not contain `SourceClaim`.  The parity-sensitive
binary-plus-ladder reduction remains the ordinary theorem
`Goldbach10Pow27CampaignSemantics.sourceClaim`.

This campaign is a multi-branch DAG.  Its future
`ArchitectureRefinesNativeChecker` proof must establish that the measured
CPU finalizer authenticates and checks every H100 binary leaf and every CPU
ladder child.  One ordinary finalizer process receipt cannot silently
manufacture those child executions.

This module defines no axiom and replays no production data.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Goldbach10Pow27CompactChecker

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

/-- Exact logical input selected by the registered lowered finalizer. -/
def canonicalInputText : String :=
  "{\"binary_artifact_kind\":\"sparkinterval.goldbach-gpu-aggregate.v1\"," ++
  "\"binary_campaign\":" ++
    "\"goldbach-gpu-analytic-10pow27-production-65536-leaf-v1\"," ++
  "\"binary_source_identity_sha256\":" ++
    "\"9727bb9c4f2c1e1fed9ed164ed756734c2e16ce2d338aedda858aad964ecdd55\"," ++
  "\"campaign\":\"ternary-goldbach-finite-below-10pow27-v1\"," ++
  "\"combined_artifact_kind\":" ++
    "\"tg_goldbach_10pow27_gpu_plus_ladder_result_v1\"," ++
  "\"ladder_artifact_kind\":" ++
    "\"tg_goldbach_ladder_parallel_aggregate_v1\"," ++
  "\"ladder_campaign\":\"analytic_10pow27\"," ++
  "\"semantic_target_inclusive\":1000000000000000000000000000}"

def canonicalInputBytes : ByteArray :=
  canonicalInputText.toUTF8

def canonicalResultBytes : ByteArray :=
  "true".toUTF8

/-- Low-level semantic acceptance of the exact lowered campaign.

`CheckedCampaignEvidence` retains the exact word-indexed binary campaign and
the ladder branch with its decidable arithmetic check, not either derived
Goldbach claim. -/
def Accepts (inputBytes resultBytes : ByteArray) : Prop :=
  inputBytes = canonicalInputBytes ∧
    resultBytes = canonicalResultBytes ∧
    Nonempty Goldbach10Pow27CampaignSemantics.CheckedCampaignEvidence

def nativeChecker : NativeCheckerSemantics where
  checkerId :=
    "sparkinterval.ternary-goldbach.finite-below-10pow27.compact.v1"
  accepts := Accepts

/-- Ordinary checked-evidence-to-source-claim theorem. -/
theorem sourceClaim_of_acceptance
    {inputBytes resultBytes : ByteArray}
    (accepted : nativeChecker.accepts inputBytes resultBytes) :
    Goldbach10Pow27SourceSemantics.SourceClaim := by
  rcases accepted with ⟨_input, _result, ⟨evidence⟩⟩
  exact
    Goldbach10Pow27CampaignSemantics.sourceClaim evidence

theorem acceptanceImpliesSourceClaim (result : MeasuredBlob) :
    AcceptanceImpliesClaim nativeChecker result
      Goldbach10Pow27SourceSemantics.SourceClaim := by
  intro inputBytes accepted
  exact sourceClaim_of_acceptance accepted

/-- Compact composition after the separate universal machine/DAG
refinement has been proved. -/
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
    Goldbach10Pow27SourceSemantics.SourceClaim :=
  claim_of_compactInputReceipt'
    receipt executableRefinement (acceptanceImpliesSourceClaim result)

end SparkInterval.TernaryGoldbach.Goldbach10Pow27CompactChecker
