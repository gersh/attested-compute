/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactArchitectureReceipt

/-!
# Compact architecture receipt to mathematical claim

This module is the application-neutral final composition for a production
computation whose input is too large to retain or replay locally.

The three inputs remain separate:

1. `CompactInputReceiptExecutionFact` is the sole per-run physical fact.  It
   retains the small reviewed executable and result, while the production
   input and architecture trace remain existential and opaque.
2. `ArchitectureRefinesNativeChecker` is an ordinary universal theorem about
   the exact executable and every possible input.
3. `AcceptanceImpliesClaim` is an ordinary application theorem saying that
   acceptance of any input by that checker establishes one fixed mathematical
   proposition.

Their composition inspects no production byte, hashes no production input,
and traverses no machine trace.  The trusted receipt boundary must still
select the measurement scheme, architecture semantics, pins, executable, and
result from a closed invocation catalog; this theorem does not make those
choices authoritative.

Multi-node CPU/GPU campaigns use the same pattern after their closed campaign
execution relation has been refined to the final checker acceptance relation.
That graph refinement is a separate ordinary proof: a signed finalizer result
must not silently turn unproved child executions into mathematics.

This module introduces no axiom.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Architecture

/-- Application-level soundness of one native checker result.

The input remains universally quantified.  Consequently a caller never needs
to materialize the production input in Lean merely to apply the theorem. -/
def AcceptanceImpliesClaim
    (checker : NativeCheckerSemantics)
    (result : MeasuredBlob)
    (Claim : Prop) : Prop :=
  ∀ inputBytes : ByteArray,
    checker.accepts inputBytes result.bytes →
      Claim

/-- Complete ordinary proof package above the one compact physical-run fact.

Neither field contains attestation evidence.  `executableRefinement` is the
machine/compiler/loader theorem, while `claimSoundness` is the
checker-to-mathematics theorem. -/
structure CompactClaimRefinement
    (scheme : MeasurementScheme)
    (machine : ArchitectureSemantics)
    (checker : NativeCheckerSemantics)
    (pins : CompactRunPins)
    (executable result : MeasuredBlob)
    (Claim : Prop) : Prop where
  executableRefinement :
    ArchitectureRefinesNativeChecker
      scheme machine checker executable pins.entryPoint
  claimSoundness :
    AcceptanceImpliesClaim checker result Claim

/-- A compact, opaque physical execution plus the two universal refinement
theorems proves the fixed mathematical claim.

The proof performs only existential elimination and theorem application.
It does not reduce the measurement function, checker, architecture step
relation, or the hidden input. -/
theorem claim_of_compactInputReceipt
    {receiptHash : Digest}
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {checker : NativeCheckerSemantics}
    {pins : CompactRunPins}
    {executable result : MeasuredBlob}
    {Claim : Prop}
    (receipt :
      CompactInputReceiptExecutionFact
        receiptHash scheme machine pins executable result)
    (refinement :
      CompactClaimRefinement
        scheme machine checker pins executable result Claim) :
    Claim := by
  rcases
      nativeAcceptance_of_compactInputReceipt
        receipt refinement.executableRefinement with
    ⟨inputBytes, _executed, accepted⟩
  exact refinement.claimSoundness inputBytes accepted

/-- Curried form convenient for campaign-specific adapters. -/
theorem claim_of_compactInputReceipt'
    {receiptHash : Digest}
    {scheme : MeasurementScheme}
    {machine : ArchitectureSemantics}
    {checker : NativeCheckerSemantics}
    {pins : CompactRunPins}
    {executable result : MeasuredBlob}
    {Claim : Prop}
    (receipt :
      CompactInputReceiptExecutionFact
        receiptHash scheme machine pins executable result)
    (executableRefinement :
      ArchitectureRefinesNativeChecker
        scheme machine checker executable pins.entryPoint)
    (claimSoundness :
      AcceptanceImpliesClaim checker result Claim) :
    Claim :=
  claim_of_compactInputReceipt receipt {
    executableRefinement
    claimSoundness
  }

end SparkInterval.Execution.Architecture
