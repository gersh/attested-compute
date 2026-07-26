/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactArchitectureRegistry

/-!
# Compact architecture registry attack-surface regressions

These proofs exercise the dependent shape of the lightweight registry.  They
do not import a trusted receipt, production bytes, a generated certificate
table, or the execution axiom.

The important invariant is per-invocation uniqueness: once the closed
`reviewedRun` selector has selected a registration, a caller cannot substitute
either another receipt hash or another `RunStatement`.  Cross-invocation
non-aliasing remains a source-review obligation when registrations are
installed; it is deliberately not asserted here.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.CompactArchitectureAttackSurface

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

/-- Two successful selections of one closed invocation necessarily use the
same source-installed reviewed record. -/
private theorem selected_reviewed_unique
    {invocation : RegisteredArchitectureInvocation}
    {left right : ReviewedArchitectureRun invocation}
    (leftSelected : invocation.reviewedRun = some left)
    (rightSelected : invocation.reviewedRun = some right) :
    left = right := by
  rw [leftSelected] at rightSelected
  exact Option.some.inj rightSelected

/-- A caller cannot replace the receipt hash after selecting one closed
invocation. -/
theorem receipt_hash_unique
    {invocation : RegisteredArchitectureInvocation}
    {leftStatement rightStatement : RunStatement}
    {leftHash rightHash : Digest}
    (left :
      invocation.ReceiptSelected leftStatement leftHash)
    (right :
      invocation.ReceiptSelected rightStatement rightHash) :
    leftHash = rightHash := by
  rcases left with
    ⟨leftReviewed, leftSelected, leftReceipt, _leftStatement⟩
  rcases right with
    ⟨rightReviewed, rightSelected, rightReceipt, _rightStatement⟩
  have reviewedEq :=
    selected_reviewed_unique leftSelected rightSelected
  subst rightReviewed
  exact leftReceipt.trans rightReceipt.symm

/-- `StatementBound` covers every field of `RunStatement`, so a caller also
cannot use the same closed invocation with a different statement. -/
theorem statement_unique
    {invocation : RegisteredArchitectureInvocation}
    {leftStatement rightStatement : RunStatement}
    {leftHash rightHash : Digest}
    (left :
      invocation.ReceiptSelected leftStatement leftHash)
    (right :
      invocation.ReceiptSelected rightStatement rightHash) :
    leftStatement = rightStatement := by
  rcases left with
    ⟨leftReviewed, leftSelected, _leftReceipt, leftBound⟩
  rcases right with
    ⟨rightReviewed, rightSelected, _rightReceipt, rightBound⟩
  have reviewedEq :=
    selected_reviewed_unique leftSelected rightSelected
  subst rightReviewed
  rcases leftBound with
    ⟨leftAlgorithmId, leftAlgorithmHash, leftInputHash,
      leftParametersHash, leftDomainHash, leftResult, leftOutputHash,
      leftNonce, leftTarget, leftTargetProfile, leftTrust,
      leftTrustProfile, leftArtifacts⟩
  rcases rightBound with
    ⟨rightAlgorithmId, rightAlgorithmHash, rightInputHash,
      rightParametersHash, rightDomainHash, rightResult, rightOutputHash,
      rightNonce, rightTarget, rightTargetProfile, rightTrust,
      rightTrustProfile, rightArtifacts⟩
  cases leftStatement
  cases rightStatement
  simp_all

/-- A single complete statement cannot be aliased across two different
closed invocation constructors. -/
example
    {left right : RegisteredArchitectureInvocation}
    {statement : RunStatement}
    {leftHash rightHash : Digest}
    (leftSelected : left.ReceiptSelected statement leftHash)
    (rightSelected : right.ReceiptSelected statement rightHash) :
    left = right :=
  RegisteredArchitectureInvocation.invocation_eq_of_receiptSelected
    leftSelected rightSelected

/-- The public outcome structure does not bypass selection: extracting a
physical fact still requires the exact closed selector premise. -/
example
    {statement : RunStatement}
    {receiptHash : Digest}
    (outcomes : RegisteredArchitectureOutcomes statement receiptHash)
    (invocation : RegisteredArchitectureInvocation)
    (selected : invocation.ReceiptSelected statement receiptHash) :
    invocation.PhysicalOutcome statement receiptHash :=
  outcomes.physicalOutcome invocation selected

#print axioms receipt_hash_unique
#print axioms statement_unique
#print axioms
  RegisteredArchitectureInvocation.invocation_eq_of_receiptSelected

end SparkInterval.Tests.CompactArchitectureAttackSurface
