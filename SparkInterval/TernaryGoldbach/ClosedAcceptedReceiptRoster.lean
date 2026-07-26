/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactArchitectureRegistry
import SparkInterval.TernaryGoldbach.CompactExternalAtomRegisteredCapstone

/-!
# Closed accepted-receipt roster for the complete Goldbach boundary

The ternary-Goldbach proof has eleven proof-authorizing physical campaigns:

* ten campaigns serve the thirteen named external/source atoms; and
* one aggregate campaign serves all fifteen historically native-generated
  families.

This module gives those eleven campaigns one closed receipt shape.  A
`ReceiptOutcome` fixes a registry constructor and a literal receipt hash,
retains the architecture projection of the checked run, and proves that the
same statement and hash select the reviewed run installed for that
constructor.  Its ordinary projection yields the exact `PhysicalOutcome`
used by the source-claim capstones.

The stronger Ramaré three-fold campaign is represented separately as an
optional fallback; it is not another trust root of `ternary_goldbach`.

No accepted receipt is declared here.  The registry currently installs no
reviewed run, so none of these records has a production inhabitant.  A future
generated receipt declaration must obtain `architectureOutcomes` by
projecting a `RunCertificate.ProducedOutcome` constructed with
`Trusted.acceptedRunCertificateForReceipt` at a literal hash.  That
production-only module may import the heavier receipt policy; this
production-data-free roster deliberately does not.  The project certificate
audit can then list the hash and reject any uncovered direct use of the
trusted-execution axiom.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.ClosedAcceptedReceiptRoster

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

/-- One exact imported outcome for one closed architecture invocation.

`architectureOutcomes` is deliberately an exact low-level execution
projection rather than an acceptance Boolean or mathematical claim.  A
concrete generated declaration must obtain it from the one receipt wrapper at
a literal hash. -/
structure ReceiptOutcome
    (invocation : RegisteredArchitectureInvocation)
    (receiptHash : Digest) : Type where
  statement : RunStatement
  selected :
    invocation.ReceiptSelected statement receiptHash
  architectureOutcomes :
    RegisteredArchitectureOutcomes statement receiptHash

namespace ReceiptOutcome

/-- Project the preferred compact architecture outcome.  The legacy
application-level `ProducedOutcome.registered` field is not used. -/
theorem physicalOutcome
    {invocation : RegisteredArchitectureInvocation}
    {receiptHash : Digest}
    (receipt : ReceiptOutcome invocation receiptHash) :
    invocation.PhysicalOutcome receipt.statement receiptHash :=
  receipt.architectureOutcomes.physicalOutcome invocation receipt.selected

end ReceiptOutcome

/-- Existentially hide only the literal receipt hash.  The selected
invocation remains fixed in the type. -/
def ImportedOutcome
    (invocation : RegisteredArchitectureInvocation) : Prop :=
  ∃ receiptHash : Digest, Nonempty (ReceiptOutcome invocation receiptHash)

/-- The eleven receipts which can eventually discharge every current
non-foundational root of `ternary_goldbach`.

The four Hurst claims share one field because they share one exact physical
campaign.  No caller can add a campaign or redirect a claim to another
constructor. -/
structure RequiredRoster : Prop where
  ch25A7Boundary :
    ImportedOutcome .ch25A7BoundaryProductionV1
  ch25PsiLemma92 :
    ImportedOutcome .ch25PsiLemma92ProductionV1
  plattHead2e4 :
    ImportedOutcome .plattHead2e4ProductionV1
  plattTrudgianRH3e12 :
    ImportedOutcome .plattTrudgianFiniteRHProductionV1
  helfgottProp1224 :
    ImportedOutcome .helfgottProp1224ProductionV1
  hurstSharedFourResidual :
    ImportedOutcome .hurstSharedFourResidualProductionV2
  cdemTableAbel :
    ImportedOutcome .cdemTableAbelProductionV2
  ramareZunigaLemma62 :
    ImportedOutcome .ramareZunigaLemma62ProductionV1
  helfgottPlattTheorem41 :
    ImportedOutcome .helfgottPlattGoldbachProductionV1
  plattDirichletTheorem71 :
    ImportedOutcome .plattDirichletTheorem71ProductionV1
  nativeGeneratedAggregate :
    ImportedOutcome .nativeGeneratedAggregateProductionV1

namespace RequiredRoster

/-- Forget the imported-certificate packaging and obtain the ten exact
physical outcomes consumed by the external-atom registered capstone. -/
theorem externalPhysicalOutcomes
    (roster : RequiredRoster) :
    CompactExternalAtomRegisteredCapstone.RegisteredPhysicalOutcomes where
  ch25A7Boundary := by
    rcases roster.ch25A7Boundary with ⟨receiptHash, ⟨receipt⟩⟩
    exact ⟨receipt.statement, receiptHash,
      receipt.physicalOutcome⟩
  ch25PsiLemma92 := by
    rcases roster.ch25PsiLemma92 with ⟨receiptHash, ⟨receipt⟩⟩
    exact ⟨receipt.statement, receiptHash,
      receipt.physicalOutcome⟩
  plattHead2e4 := by
    rcases roster.plattHead2e4 with ⟨receiptHash, ⟨receipt⟩⟩
    exact ⟨receipt.statement, receiptHash,
      receipt.physicalOutcome⟩
  plattTrudgianRH3e12 := by
    rcases roster.plattTrudgianRH3e12 with ⟨receiptHash, ⟨receipt⟩⟩
    exact ⟨receipt.statement, receiptHash,
      receipt.physicalOutcome⟩
  helfgottProp1224 := by
    rcases roster.helfgottProp1224 with ⟨receiptHash, ⟨receipt⟩⟩
    exact ⟨receipt.statement, receiptHash,
      receipt.physicalOutcome⟩
  hurstSharedFourResidual := by
    rcases roster.hurstSharedFourResidual with ⟨receiptHash, ⟨receipt⟩⟩
    exact ⟨receipt.statement, receiptHash,
      receipt.physicalOutcome⟩
  cdemTableAbel := by
    rcases roster.cdemTableAbel with ⟨receiptHash, ⟨receipt⟩⟩
    exact ⟨receipt.statement, receiptHash,
      receipt.physicalOutcome⟩
  ramareZunigaLemma62 := by
    rcases roster.ramareZunigaLemma62 with ⟨receiptHash, ⟨receipt⟩⟩
    exact ⟨receipt.statement, receiptHash,
      receipt.physicalOutcome⟩
  helfgottPlattTheorem41 := by
    rcases roster.helfgottPlattTheorem41 with ⟨receiptHash, ⟨receipt⟩⟩
    exact ⟨receipt.statement, receiptHash,
      receipt.physicalOutcome⟩
  plattDirichletTheorem71 := by
    rcases roster.plattDirichletTheorem71 with ⟨receiptHash, ⟨receipt⟩⟩
    exact ⟨receipt.statement, receiptHash,
      receipt.physicalOutcome⟩

/-- Exact aggregate physical outcome, retaining its statement and receipt
hash as existential witnesses. -/
theorem nativeAggregatePhysicalOutcome
    (roster : RequiredRoster) :
  ∃ (statement : RunStatement) (receiptHash : Digest),
      RegisteredArchitectureInvocation.nativeGeneratedAggregateProductionV1.PhysicalOutcome
        statement receiptHash := by
  rcases roster.nativeGeneratedAggregate with ⟨receiptHash, ⟨receipt⟩⟩
  exact ⟨receipt.statement, receiptHash,
    receipt.physicalOutcome⟩

end RequiredRoster

/-- Optional imported receipt for the stronger Ramaré finite-fold fallback.
The complete theorem does not need this in addition to the aggregate native
campaign. -/
def RamareFallbackOutcome : Prop :=
  ImportedOutcome .ramareProductionFoldsCompactV1

/-- Before registration, ordinary Lean proves that no receipt outcome can be
installed for any closed invocation. -/
theorem no_current_importedOutcome
    (invocation : RegisteredArchitectureInvocation) :
    ¬ ImportedOutcome invocation := by
  rintro ⟨_receiptHash, ⟨receipt⟩⟩
  exact
    RegisteredArchitectureInvocation.not_receiptSelected_of_reviewedRun_eq_none
      (RegisteredArchitectureInvocation.reviewedRun_currently_none invocation)
      receipt.selected

/-- Consequently the complete eleven-receipt roster is currently
uninhabited. -/
theorem no_current_requiredRoster :
    ¬ RequiredRoster := by
  intro roster
  exact no_current_importedOutcome
    .ch25A7BoundaryProductionV1 roster.ch25A7Boundary

end SparkInterval.TernaryGoldbach.ClosedAcceptedReceiptRoster
