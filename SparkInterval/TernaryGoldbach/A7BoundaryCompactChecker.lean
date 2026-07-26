/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactClaimReceipt
import SparkInterval.TernaryGoldbach.A7BoundarySuccessEvidence

/-!
# Compact native-checker boundary for CH25 Lemma A.7

The accepted native result exposes a checked rational/dyadic boundary
transcript and its FLINT/Arb-to-Mathlib analytic realization.  It does not
expose the final zeta inequality.  Ordinary Lean derives that inequality via
`A7BoundarySuccessEvidence.sourceClaim_of_successEvidence`.

The executable refinement remains a separate universal architecture theorem;
the compact receipt supplies only one opaque execution.  No retained
subdivision or instruction trace is replayed here.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.A7BoundaryCompactChecker

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

def canonicalInputText : String :=
  "{\"campaign\":\"ch25-a7-boundary-v1\"," ++
  "\"retained_artifact_sha256\":" ++
  "\"ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29\"}"

def canonicalInputBytes : ByteArray := canonicalInputText.toUTF8
def canonicalResultBytes : ByteArray := "true".toUTF8

def Accepts (inputBytes resultBytes : ByteArray) : Prop :=
  inputBytes = canonicalInputBytes ∧
    resultBytes = canonicalResultBytes ∧
    A7BoundarySuccessEvidence.SuccessEvidence

def nativeChecker : NativeCheckerSemantics where
  checkerId := "sparkinterval.ternary-goldbach.ch25-a7-boundary.compact.v1"
  accepts := Accepts

theorem sourceClaim_of_acceptance
    {inputBytes resultBytes : ByteArray}
    (accepted : nativeChecker.accepts inputBytes resultBytes) :
    A7BoundarySourceSemantics.SourceClaim :=
  A7BoundarySuccessEvidence.sourceClaim_of_successEvidence accepted.2.2

theorem acceptanceImpliesSourceClaim (result : MeasuredBlob) :
    AcceptanceImpliesClaim
      nativeChecker result A7BoundarySourceSemantics.SourceClaim := by
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
    A7BoundarySourceSemantics.SourceClaim :=
  claim_of_compactInputReceipt'
    receipt executableRefinement (acceptanceImpliesSourceClaim result)

end SparkInterval.TernaryGoldbach.A7BoundaryCompactChecker
