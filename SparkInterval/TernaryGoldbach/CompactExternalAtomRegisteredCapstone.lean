/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.StaticCPUExecutableCertificate
import SparkInterval.TernaryGoldbach.CompactExternalAtomCapstone

/-!
# Closed physical-outcome capstone for the thirteen external atoms

`CompactExternalAtomCapstone` proves all thirteen source claims from ten
canonical checker acceptances.  This module supplies the missing
production-data-free layer immediately below it:

* ten exact registered `PhysicalOutcome`s, one per physical campaign; and
* ten ordinary, universal executable/compiler/loader/ISA refinements for the
  exact closed registry entries.

Together they imply every checker-derived mathematical claim.  No caller can
select a machine, executable, entry point, checker, or proposition: every
field below fixes one constructor of `RegisteredArchitectureInvocation` and
its corresponding checker.

This module does not assert that any outcome or refinement exists.  Every
`reviewedRun` branch remains `none`; the refinement fields are still open
proof obligations.  Once separately supplied, the physical outcomes come
through the project's existing single attested-execution axiom.  This file
adds no axiom and retains no production input or trace.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.TernaryGoldbach.CompactExternalAtomRegisteredCapstone

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

namespace Base

abbrev Atom :=
  TernaryGoldbachExternalAtom

abbrev Claim :=
  CompactExternalAtomCapstone.CheckerDerivedClaim

end Base

/-- One exact closed registered physical outcome, with its statement and
receipt hash existentially hidden. -/
def ClosedPhysicalOutcome
    (invocation : RegisteredArchitectureInvocation) : Prop :=
  ∃ (statement : RunStatement) (receiptHash : Digest),
    invocation.PhysicalOutcome statement receiptHash

/-- Universal executable refinement for one exact closed registry
constructor and one exact native checker.

The quantified `reviewed` value can only be the value installed by the closed
`reviewedRun` definition.  It is not a caller-selected replacement registry
entry. -/
def ClosedExecutableRefinement
    (invocation : RegisteredArchitectureInvocation)
    (checker : NativeCheckerSemantics) : Prop :=
  ∀ reviewed : ReviewedArchitectureRun invocation,
    invocation.reviewedRun = some reviewed →
      ArchitectureRefinesNativeChecker
        registeredSHA256MeasurementScheme reviewed.machine checker
        reviewed.executableArtifact reviewed.compactPins.entryPoint

/-! ## Reusable static-CPU certificate route -/

namespace StaticCPU

open
  SparkInterval.Execution.Architecture.StaticCPUExecutableCertificate

/-- The ten external campaigns whose proof-authorizing terminal registered
architecture is an Azure confidential CPU.

The Ramaré--Zúñiga, Goldbach, and Dirichlet campaigns may use H100 child
producers.  Their registered terminal process is nevertheless the measured
CPU finalizer which authenticates and verifies every child artifact. -/
inductive FixedCampaign where
  | ch25A7Boundary
  | ch25PsiLemma92
  | plattHead2e4
  | plattTrudgianRH3e12
  | helfgottProp1224
  | hurstSharedFourResidual
  | cdemTableAbel
  | ramareZunigaLemma62
  | helfgottPlattTheorem41
  | plattDirichletTheorem71
  deriving Repr, DecidableEq, BEq

namespace FixedCampaign

/-- Exact closed registry constructor for each static-CPU candidate. -/
def invocation :
    FixedCampaign → RegisteredArchitectureInvocation
  | .ch25A7Boundary => .ch25A7BoundaryProductionV1
  | .ch25PsiLemma92 => .ch25PsiLemma92ProductionV1
  | .plattHead2e4 => .plattHead2e4ProductionV1
  | .plattTrudgianRH3e12 => .plattTrudgianFiniteRHProductionV1
  | .helfgottProp1224 => .helfgottProp1224ProductionV1
  | .hurstSharedFourResidual => .hurstSharedFourResidualProductionV2
  | .cdemTableAbel => .cdemTableAbelProductionV2
  | .ramareZunigaLemma62 => .ramareZunigaLemma62ProductionV1
  | .helfgottPlattTheorem41 => .helfgottPlattGoldbachProductionV1
  | .plattDirichletTheorem71 =>
      .plattDirichletTheorem71ProductionV1

/-- Exact native checker fixed for each static-CPU candidate. -/
def checker : FixedCampaign → NativeCheckerSemantics
  | .ch25A7Boundary =>
      A7BoundaryCompactChecker.nativeChecker
  | .ch25PsiLemma92 =>
      PsiCompactChecker.nativeChecker
  | .plattHead2e4 =>
      ZetaHeadCompactChecker.nativeChecker
  | .plattTrudgianRH3e12 =>
      ZetaRHCompactChecker.nativeChecker
  | .helfgottProp1224 =>
      Prop1224CompactChecker.nativeChecker
  | .hurstSharedFourResidual =>
      HurstCompactChecker.nativeChecker
  | .cdemTableAbel =>
      CDEMAbelCompactChecker.nativeChecker
  | .ramareZunigaLemma62 =>
      R2StarCompactChecker.nativeChecker
  | .helfgottPlattTheorem41 =>
      GoldbachCompactChecker.nativeChecker
  | .plattDirichletTheorem71 =>
      SparkInterval.Dirichlet.PlattTheorem71CompactChecker.nativeChecker

/-- Closed roster of all ten terminal CPU campaigns. -/
def all : List FixedCampaign :=
  [.ch25A7Boundary, .ch25PsiLemma92, .plattHead2e4,
    .plattTrudgianRH3e12, .helfgottProp1224,
    .hurstSharedFourResidual, .cdemTableAbel,
    .ramareZunigaLemma62,
    .helfgottPlattTheorem41, .plattDirichletTheorem71]

/-- Every constructor in this roster really has the CPU terminal target. -/
theorem terminalTarget (campaign : FixedCampaign) :
    campaign.invocation.terminalTarget = .azureSEVSNPCPU := by
  cases campaign <;>
    rfl

/-- Candidate static-CPU certificate for one concrete reviewed value.

This type is useful before receipt installation, but it cannot by itself
prove the closed refinement: the reviewed value must subsequently be
installed by the closed registry selector. -/
abbrev CandidateCertificate
    (campaign : FixedCampaign)
    (reviewed : ReviewedArchitectureRun campaign.invocation) : Type 1 :=
  StaticCPUExecutableCertificate.Certificate
    campaign.invocation reviewed campaign.checker

/-- Non-vacuous certificate for the actual value installed in one fixed CPU
campaign. -/
abbrev InstalledCertificate
    (campaign : FixedCampaign) : Type 1 :=
  StaticCPUExecutableCertificate.InstalledCertificate
    campaign.invocation campaign.checker

/-- The generic static-CPU certificate supplies exactly the
`ClosedExecutableRefinement` expected by the registered external-atom
capstone. -/
theorem closedExecutableRefinement
    (campaign : FixedCampaign)
    (certificate : InstalledCertificate campaign) :
    ClosedExecutableRefinement
      campaign.invocation campaign.checker :=
  certificate.closedRefinement

end FixedCampaign

/-! ### Smallest real campaign: explicit pre-installation boundary -/

/-- The smallest real external CPU campaign is the CH25 A7 boundary replay.
Its current implementation is a Python/FLINT process, not yet a static
pure-entry ELF with a formal x86 semantics.  This alias records the exact
certificate type required once a reviewed static runner value exists. -/
abbrev A7BoundaryCandidateCertificate
    (reviewed :
      ReviewedArchitectureRun
        .ch25A7BoundaryProductionV1) : Type 1 :=
  FixedCampaign.CandidateCertificate .ch25A7Boundary reviewed

/-- A real installed A7 certificate must exhibit an installed reviewed run;
it cannot be constructed merely because the current registry branch is
`none`. -/
abbrev A7BoundaryInstalledCertificate : Type 1 :=
  FixedCampaign.InstalledCertificate .ch25A7Boundary

/-- Exact closed A7 refinement obtained after, and only after, constructing
the non-vacuous installed static-CPU certificate. -/
theorem a7BoundaryClosedExecutableRefinement
    (certificate : A7BoundaryInstalledCertificate) :
    ClosedExecutableRefinement
      .ch25A7BoundaryProductionV1
      A7BoundaryCompactChecker.nativeChecker :=
  FixedCampaign.closedExecutableRefinement
    .ch25A7Boundary certificate

/-- First physical availability gate for the A7 static-CPU route.

This proposition alone proves no checker refinement.  A full
`A7BoundaryInstalledCertificate` additionally needs exact ELF validation and
the universal instruction/block/compiler/source theorems. -/
def A7BoundaryReviewedRunAvailable : Prop :=
  ∃ reviewed :
      ReviewedArchitectureRun .ch25A7BoundaryProductionV1,
    RegisteredArchitectureInvocation.ch25A7BoundaryProductionV1.reviewedRun =
      some reviewed

/-- Any installed A7 static-CPU certificate necessarily crosses the explicit
reviewed-run availability gate. -/
theorem a7BoundaryReviewedRunAvailable
    (certificate : A7BoundaryInstalledCertificate) :
    A7BoundaryReviewedRunAvailable :=
  certificate.installedRunExists

end StaticCPU

/-- The ten physical campaigns serving the thirteen named external atoms. -/
structure RegisteredPhysicalOutcomes : Prop where
  ch25A7Boundary :
    ClosedPhysicalOutcome
      .ch25A7BoundaryProductionV1
  ch25PsiLemma92 :
    ClosedPhysicalOutcome
      .ch25PsiLemma92ProductionV1
  plattHead2e4 :
    ClosedPhysicalOutcome
      .plattHead2e4ProductionV1
  plattTrudgianRH3e12 :
    ClosedPhysicalOutcome
      .plattTrudgianFiniteRHProductionV1
  helfgottProp1224 :
    ClosedPhysicalOutcome
      .helfgottProp1224ProductionV1
  hurstSharedFourResidual :
    ClosedPhysicalOutcome
      .hurstSharedFourResidualProductionV2
  cdemTableAbel :
    ClosedPhysicalOutcome
      .cdemTableAbelProductionV2
  ramareZunigaLemma62 :
    ClosedPhysicalOutcome
      .ramareZunigaLemma62ProductionV1
  helfgottPlattTheorem41 :
    ClosedPhysicalOutcome
      .helfgottPlattGoldbachProductionV1
  plattDirichletTheorem71 :
    ClosedPhysicalOutcome
      .plattDirichletTheorem71ProductionV1

/-- The ten still-open universal binary/compiler/loader/ISA theorems.

The shared Hurst refinement is intentionally one field: its one physical
campaign supplies four distinct source atoms. -/
structure ClosedExecutableRefinements : Prop where
  ch25A7Boundary :
    ClosedExecutableRefinement
      .ch25A7BoundaryProductionV1
      A7BoundaryCompactChecker.nativeChecker
  ch25PsiLemma92 :
    ClosedExecutableRefinement
      .ch25PsiLemma92ProductionV1
      PsiCompactChecker.nativeChecker
  plattHead2e4 :
    ClosedExecutableRefinement
      .plattHead2e4ProductionV1
      ZetaHeadCompactChecker.nativeChecker
  plattTrudgianRH3e12 :
    ClosedExecutableRefinement
      .plattTrudgianFiniteRHProductionV1
      ZetaRHCompactChecker.nativeChecker
  helfgottProp1224 :
    ClosedExecutableRefinement
      .helfgottProp1224ProductionV1
      Prop1224CompactChecker.nativeChecker
  hurstSharedFourResidual :
    ClosedExecutableRefinement
      .hurstSharedFourResidualProductionV2
      HurstCompactChecker.nativeChecker
  cdemTableAbel :
    ClosedExecutableRefinement
      .cdemTableAbelProductionV2
      CDEMAbelCompactChecker.nativeChecker
  ramareZunigaLemma62 :
    ClosedExecutableRefinement
      .ramareZunigaLemma62ProductionV1
      R2StarCompactChecker.nativeChecker
  helfgottPlattTheorem41 :
    ClosedExecutableRefinement
      .helfgottPlattGoldbachProductionV1
      GoldbachCompactChecker.nativeChecker
  plattDirichletTheorem71 :
    ClosedExecutableRefinement
      .plattDirichletTheorem71ProductionV1
      SparkInterval.Dirichlet.PlattTheorem71CompactChecker.nativeChecker

/-- Ten exact physical outcomes plus ten universal executable refinements
prove all thirteen checker-derived mathematical claims. -/
theorem checkerDerivedClaim_of_registeredPhysicalOutcomes
    (outcomes : RegisteredPhysicalOutcomes)
    (refinements : ClosedExecutableRefinements) :
    ∀ atom : Base.Atom, Base.Claim atom := by
  intro atom
  cases atom with
  | ch25A7Boundary =>
      rcases outcomes.ch25A7Boundary with
        ⟨_statement, _receiptHash, reviewed, installed, _hashEq,
          _statementBound, execution⟩
      exact A7BoundaryCompactChecker.sourceClaim_of_compactRun
        execution (refinements.ch25A7Boundary reviewed installed)
  | ch25Psi1e13 =>
      rcases outcomes.ch25PsiLemma92 with
        ⟨_statement, _receiptHash, reviewed, installed, _hashEq,
          _statementBound, execution⟩
      exact PsiCompactChecker.sourceClaim_of_compactRun
        execution (refinements.ch25PsiLemma92 reviewed installed)
  | plattHead2e4 =>
      rcases outcomes.plattHead2e4 with
        ⟨_statement, _receiptHash, reviewed, installed, _hashEq,
          _statementBound, execution⟩
      exact ZetaHeadCompactChecker.committedSourceClaim_of_compactRun
        execution (refinements.plattHead2e4 reviewed installed)
  | plattTrudgianRH3e12 =>
      rcases outcomes.plattTrudgianRH3e12 with
        ⟨_statement, _receiptHash, reviewed, installed, _hashEq,
          _statementBound, execution⟩
      exact ZetaRHCompactChecker.sourceClaim_of_compactRun
        execution (refinements.plattTrudgianRH3e12 reviewed installed)
  | helfgottProp1224 =>
      rcases outcomes.helfgottProp1224 with
        ⟨_statement, _receiptHash, reviewed, installed, _hashEq,
          _statementBound, execution⟩
      exact Prop1224CompactChecker.sourceClaim_of_compactRun
        execution (refinements.helfgottProp1224 reviewed installed)
  | cdemSquarefree =>
      rcases outcomes.hurstSharedFourResidual with
        ⟨_statement, _receiptHash, reviewed, installed, _hashEq,
          _statementBound, execution⟩
      let claims :=
        HurstCompactChecker.realClaims_of_compactRun
          execution
          (refinements.hurstSharedFourResidual reviewed installed)
      exact ⟨claims.squarefreeB1, claims.squarefreeB2⟩
  | cdemTableAbel =>
      rcases outcomes.cdemTableAbel with
        ⟨_statement, _receiptHash, reviewed, installed, _hashEq,
          _statementBound, execution⟩
      exact CDEMAbelCompactChecker.sourceClaim_of_compactRun
        execution (refinements.cdemTableAbel reviewed installed)
  | mertensHurst =>
      rcases outcomes.hurstSharedFourResidual with
        ⟨_statement, _receiptHash, reviewed, installed, _hashEq,
          _statementBound, execution⟩
      exact
        (HurstCompactChecker.realClaims_of_compactRun
          execution
          (refinements.hurstSharedFourResidual reviewed installed)).hurst
  | ramareZunigaLemma62 =>
      rcases outcomes.ramareZunigaLemma62 with
        ⟨_statement, _receiptHash, reviewed, installed, _hashEq,
          _statementBound, execution⟩
      exact R2StarCompactChecker.sourceClaim_of_compactRun
        execution (refinements.ramareZunigaLemma62 reviewed installed)
  | helfgottPlattTheorem41 =>
      rcases outcomes.helfgottPlattTheorem41 with
        ⟨_statement, _receiptHash, reviewed, installed, _hashEq,
          _statementBound, execution⟩
      exact GoldbachCompactChecker.sourceClaim_of_compactRun
        execution (refinements.helfgottPlattTheorem41 reviewed installed)
  | plattDirichletTheorem71 =>
      rcases outcomes.plattDirichletTheorem71 with
        ⟨_statement, _receiptHash, reviewed, installed, _hashEq,
          _statementBound, execution⟩
      exact
        SparkInterval.Dirichlet.PlattTheorem71CompactChecker.sourceClaim_of_compactRun
          execution
          (refinements.plattDirichletTheorem71 reviewed installed)
  | plattLittleMertens211 =>
      rcases outcomes.hurstSharedFourResidual with
        ⟨_statement, _receiptHash, reviewed, installed, _hashEq,
          _statementBound, execution⟩
      exact
        (HurstCompactChecker.realClaims_of_compactRun
          execution
          (refinements.hurstSharedFourResidual reviewed installed)).little211
  | plattLittleMertensStronger =>
      rcases outcomes.hurstSharedFourResidual with
        ⟨_statement, _receiptHash, reviewed, installed, _hashEq,
          _statementBound, execution⟩
      exact
        (HurstCompactChecker.realClaims_of_compactRun
          execution
          (refinements.hurstSharedFourResidual reviewed installed)).littleStronger

/-- The registered physical layer reaches the exact-table downstream claims
once the separate Platt-head table-identity theorem is supplied. -/
theorem exactTableDownstreamClaim_of_registeredPhysicalOutcomes
    (targetTable : ZetaHeadSourceSemantics.Q128CellTable)
    (outcomes : RegisteredPhysicalOutcomes)
    (refinements : ClosedExecutableRefinements)
    (identify :
      CompactExternalAtomCapstone.ZetaHeadTableIdentificationObligation
        targetTable) :
    ∀ atom : Base.Atom,
      CompactExternalAtomCapstone.ExactTableDownstreamClaim targetTable atom := by
  intro atom
  exact
    CompactExternalAtomCapstone.exactTableDownstreamClaim_of_checkerDerivedClaim
      targetTable identify atom
      (checkerDerivedClaim_of_registeredPhysicalOutcomes
        outcomes refinements atom)

end SparkInterval.TernaryGoldbach.CompactExternalAtomRegisteredCapstone

end
