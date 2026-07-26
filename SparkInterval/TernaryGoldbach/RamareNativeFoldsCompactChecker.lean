/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactClaimReceipt
import SparkInterval.Execution.CompactArchitectureRegistry
import SparkInterval.TernaryGoldbach.RamareNativeFoldContracts

/-!
# Compact checker for the Ramaré production folds

This checker is the one permitted compact fallback for the three live
`TGNativeCertificates.Ramare` native leaves.  It is deliberately separate
from the thirteen external/source atoms.

Acceptance has only three components:

1. the exact closed 100M/100M/140M campaign configuration;
2. the exact small success envelope; and
3. an existential `FiniteFoldEvidence` bundle.

`FiniteFoldEvidence` contains signed integer interval states and increments,
exact fold recurrences, local increment-realization facts, and integer guard
comparisons.  It has no final source-claim field.  Ordinary Lean derives all
three source claims in `sourceClaims_of_acceptance`.

The executable/compiler/loader obligation remains the explicit premise
`ArchitectureRefinesNativeChecker` of `sourceClaims_of_compactRun`.  A compact
receipt cannot manufacture that universal theorem, and no production data or
trace is replayed here.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.RamareNativeFoldsCompactChecker

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

namespace Contract

abbrev FiniteFoldEvidence :=
  RamareNativeFoldContracts.FiniteFoldEvidence

abbrev SourceClaims :=
  RamareNativeFoldContracts.SourceClaims

end Contract

/-- Exact small configuration for the three scans.  It contains no factor
table, fold state, or production transcript. -/
def canonicalInputText : String :=
  "{\"family\":\"TGNativeCertificates.Ramare\"," ++
    "\"first_mertens_limit\":100000000," ++
    "\"lemma71_limit\":100000000," ++
    "\"mstar_limit\":140000000," ++
    "\"version\":1}"

/-- Exact small native result.  The mathematical authority is the checked
low-level fold evidence, not this success string by itself. -/
def canonicalResultText : String :=
  "{\"contract\":\"ramare-production-folds-v1\",\"status\":\"accepted\"}"

def canonicalInputBytes : ByteArray :=
  canonicalInputText.toUTF8

def canonicalResultBytes : ByteArray :=
  canonicalResultText.toUTF8

/-- Closed semantic acceptance relation for the shared CPU checker.

The hidden witness is low-level fold evidence.  It is propositionally erased
and need not be materialized during a routine local build. -/
def Accepts (inputBytes resultBytes : ByteArray) : Prop :=
  inputBytes = canonicalInputBytes ∧
    resultBytes = canonicalResultBytes ∧
    Nonempty Contract.FiniteFoldEvidence

/-- Application-neutral checker selected by the native-family fallback. -/
def nativeChecker : NativeCheckerSemantics where
  checkerId :=
    "sparkinterval.ternary-goldbach.ramare-production-folds.compact.v1"
  accepts := Accepts

/-- Ordinary low-level-evidence-to-source theorem. -/
theorem sourceClaims_of_acceptance
    {inputBytes resultBytes : ByteArray}
    (accepted : nativeChecker.accepts inputBytes resultBytes) :
    Contract.SourceClaims := by
  rcases accepted.2.2 with ⟨evidence⟩
  exact
    RamareNativeFoldContracts.sourceClaims_of_finiteFoldEvidence
      evidence

/-- Universal claim-soundness field for compact receipt composition. -/
theorem acceptanceImpliesSourceClaims (result : MeasuredBlob) :
    AcceptanceImpliesClaim
      nativeChecker result Contract.SourceClaims := by
  intro inputBytes accepted
  exact sourceClaims_of_acceptance accepted

/-- Compose one opaque architecture run with ordinary executable and checker
soundness.  The executable refinement is intentionally not a receipt field.
-/
theorem sourceClaims_of_compactRun
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
    Contract.SourceClaims :=
  claim_of_compactInputReceipt'
    receipt executableRefinement
      (acceptanceImpliesSourceClaims result)

/-! ## Closed registry adapter -/

/-- The still-missing universal binary/compiler/loader theorem for the exact
review-installed Ramaré invocation.

The registration selector is an argument only as a hypothesis to the
universal theorem; it does not permit a caller to install a different
machine, executable, or entry point. -/
def ClosedExecutableRefinement : Prop :=
  ∀ reviewed :
      ReviewedArchitectureRun
        RegisteredArchitectureInvocation.ramareProductionFoldsCompactV1,
    RegisteredArchitectureInvocation.ramareProductionFoldsCompactV1.reviewedRun =
        some reviewed →
      ArchitectureRefinesNativeChecker
        registeredSHA256MeasurementScheme reviewed.machine nativeChecker
        reviewed.executableArtifact reviewed.compactPins.entryPoint

/-- Use the same sole registered physical-outcome projection as the external
campaigns.  The physical outcome supplies only the opaque execution; the
closed executable refinement remains a separate ordinary premise. -/
theorem sourceClaims_of_registeredPhysicalOutcome
    {statement : RunStatement}
    {receiptHash : Digest}
    (outcome :
      RegisteredArchitectureInvocation.ramareProductionFoldsCompactV1.PhysicalOutcome
        statement receiptHash)
    (executableRefinement : ClosedExecutableRefinement) :
    Contract.SourceClaims := by
  rcases outcome with
    ⟨reviewed, installed, _receipt, _statementBound, execution⟩
  exact sourceClaims_of_compactRun
    execution (executableRefinement reviewed installed)

/-! ## Aggregate native-family registry adapter

The same fixed evidence checker can also be one component of the closed
all-native-family aggregate finalizer.  This does not weaken or replace the
specialized Ramaré invocation above: each route has its own exact executable
refinement and reviewed receipt. -/

/-- Exact universal refinement obligation when the three-fold checker is
served by the all-native-family aggregate invocation. -/
def ClosedAggregateExecutableRefinement : Prop :=
  ∀ reviewed :
      ReviewedArchitectureRun
        RegisteredArchitectureInvocation.nativeGeneratedAggregateProductionV1,
    RegisteredArchitectureInvocation.nativeGeneratedAggregateProductionV1.reviewedRun =
        some reviewed →
      ArchitectureRefinesNativeChecker
        registeredSHA256MeasurementScheme reviewed.machine nativeChecker
        reviewed.executableArtifact reviewed.compactPins.entryPoint

/-- The fixed aggregate physical outcome plus its independent exact
executable refinement yields the same three source claims. -/
theorem sourceClaims_of_aggregatePhysicalOutcome
    {statement : RunStatement}
    {receiptHash : Digest}
    (outcome :
      RegisteredArchitectureInvocation.nativeGeneratedAggregateProductionV1.PhysicalOutcome
        statement receiptHash)
    (executableRefinement : ClosedAggregateExecutableRefinement) :
    Contract.SourceClaims := by
  rcases outcome with
    ⟨reviewed, installed, _receipt, _statementBound, execution⟩
  exact sourceClaims_of_compactRun
    execution (executableRefinement reviewed installed)

/-- Individual first-Mertens projection for the eventual `claude_math`
provider replacement. -/
theorem finite100MSourceClaim_of_compactRun
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
    RamareNativeFoldContracts.Finite100MSourceClaim :=
  (sourceClaims_of_compactRun
    receipt executableRefinement).finite100M

/-- Individual Lemma 7.1 table projection. -/
theorem lemma71SourceClaim_of_compactRun
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
    RamareNativeFoldContracts.Lemma71SourceClaim :=
  (sourceClaims_of_compactRun
    receipt executableRefinement).lemma71

/-- Individual `m★` range projection. -/
theorem mStar140MSourceClaim_of_compactRun
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
    RamareNativeFoldContracts.MStar140MSourceClaim :=
  (sourceClaims_of_compactRun
    receipt executableRefinement).mStar140M

end SparkInterval.TernaryGoldbach.RamareNativeFoldsCompactChecker
