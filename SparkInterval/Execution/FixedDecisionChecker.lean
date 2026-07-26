/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactClaimReceipt

/-!
# Fixed decidable-claim native checker

This module is a small, application-neutral adapter for a native executable
which implements one *fixed* decidable Lean proposition.  Its native-checker
acceptance relation requires both:

* the exact, fixed success-result bytes; and
* `decide Claim = true` for the proposition captured by the checker.

The proposition is a Lean parameter of `nativeChecker`; it is not decoded
from receipt, input, or result bytes.  Consequently a receipt cannot select a
proposition.  `claim_of_compactRun` composes only:

1. a `CompactInputReceiptExecutionFact` for retained executable/result bytes;
2. an exact `ArchitectureRefinesNativeChecker` theorem for this checker; and
3. the ordinary theorem `of_decide_eq_true`.

This generic module defines no axiom.  A production use is reviewable only
through a closed downstream adapter which fixes `Claim`, its decision
procedure, checker identifier, success bytes, measurement scheme, formal
machine, compact pins, executable, entry point, and receipt authority.
In particular, a trusted receipt importer must not expose any of these as
caller-selected authority.  Merely instantiating this generic theorem with a
proposition and an invented architecture semantics does not establish a
physical computation.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Architecture.FixedDecisionChecker

/-- Native semantics for one fixed decidable proposition and one fixed
success result.

The input is intentionally opaque to this final adapter.  Its interpretation
belongs in the exact executable-to-checker refinement theorem. -/
def nativeChecker
    (Claim : Prop) [Decidable Claim]
    (checkerId : String)
    (successResult : ByteArray) :
    NativeCheckerSemantics where
  checkerId := checkerId
  accepts := fun _inputBytes resultBytes =>
    resultBytes = successResult ∧ decide Claim = true

/-- Acceptance exposes the exact success-result equality. -/
theorem result_eq_success
    (Claim : Prop) [Decidable Claim]
    (checkerId : String)
    (successResult inputBytes resultBytes : ByteArray)
    (accepted :
      (nativeChecker Claim checkerId successResult).accepts
        inputBytes resultBytes) :
    resultBytes = successResult :=
  accepted.1

/-- Acceptance of the fixed checker implies its fixed proposition.

This is ordinary decidable reflection; no receipt or architecture premise is
used at this layer. -/
theorem claim_of_acceptance
    (Claim : Prop) [Decidable Claim]
    (checkerId : String)
    (successResult inputBytes resultBytes : ByteArray)
    (accepted :
      (nativeChecker Claim checkerId successResult).accepts
        inputBytes resultBytes) :
    Claim :=
  of_decide_eq_true accepted.2

/-- Universal checker-to-claim theorem in the form consumed by compact
receipt composition. -/
theorem acceptanceImpliesClaim
    (Claim : Prop) [Decidable Claim]
    (checkerId : String)
    (successResult : ByteArray)
    (result : MeasuredBlob) :
    AcceptanceImpliesClaim
      (nativeChecker Claim checkerId successResult) result Claim := by
  intro inputBytes accepted
  exact
    claim_of_acceptance
      Claim checkerId successResult inputBytes result.bytes accepted

/-- Compose one opaque compact-input execution with the exact executable
refinement for the fixed decision checker.

`Claim` is fixed when the checker is constructed; it is not a field of
`CompactInputReceiptExecutionFact`.  Production code should expose this
generic theorem only through a closed application adapter. -/
theorem claim_of_compactRun
    (Claim : Prop) [Decidable Claim]
    (checkerId : String)
    (successResult : ByteArray)
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
        scheme machine
        (nativeChecker Claim checkerId successResult)
        executable pins.entryPoint) :
    Claim :=
  claim_of_compactInputReceipt'
    receipt executableRefinement
    (acceptanceImpliesClaim Claim checkerId successResult result)

end SparkInterval.Execution.Architecture.FixedDecisionChecker
