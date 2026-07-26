/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.PlattTheorem71CompactChecker
import SparkInterval.Execution.CompactArchitectureRegistry
import SparkInterval.TernaryGoldbach.A7BoundaryCompactChecker
import SparkInterval.TernaryGoldbach.CDEMAbelCompactChecker
import SparkInterval.TernaryGoldbach.GoldbachCompactChecker
import SparkInterval.TernaryGoldbach.HurstCompactChecker
import SparkInterval.TernaryGoldbach.Prop1224CompactChecker
import SparkInterval.TernaryGoldbach.PsiCompactChecker
import SparkInterval.TernaryGoldbach.R2StarCompactChecker
import SparkInterval.TernaryGoldbach.ZetaHeadCompactChecker
import SparkInterval.TernaryGoldbach.ZetaRHCompactChecker

/-!
# Compact checker capstone for every ternary-Goldbach external atom

This file is the small, production-data-free application adapter promised by
`CompactArchitectureRegistry`.  It maps all thirteen closed external-atom
constructors to mathematical propositions and proves those propositions from
the ten exact compact checker acceptances.

The four Hurst atoms are genuine projections of one
`TGComputeContracts.HurstV2.RealSourceClaims` value.  The other source claims
are the proposition types exported by their checker/source-semantics modules.
No declaration name string is used to obtain a theorem.

There is one deliberately visible mismatch.  The Platt-head checker proves
`CommittedSourceClaim`: some table with the reviewed commitment has the
source property.  The current downstream theorem names one particular exact
Q128 table.  A digest equality alone cannot identify those tables in Lean,
and this file does not assume that SHA-256 is injective.  Consequently
`ZetaHeadTableIdentificationObligation targetTable` is an explicit premise
of the exact-table downstream capstone.

This module imports no generated table or production receipt and defines no
axiom.  Its hypotheses say only that the ten native checkers accepted their
exact canonical input/result pairs.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.TernaryGoldbach.CompactExternalAtomCapstone

open SparkInterval.Execution.Architecture

/-! ## Exact field-level claims of the shared Hurst result -/

/-- The two source-normal squarefree fields consumed by the single
`cdem-squarefree` external atom. -/
abbrev CDEMSquarefreeClaim : Prop :=
  (∀ x : Real, (9_243 : Real) < x →
      x ≤ TGComputeContracts.HurstV2.sourceLimit →
      |TGComputeContracts.HurstV2.squarefreeStep x -
          (6 / Real.pi ^ 2) * x| ≤
        (151 / 2_000 : Real) * Real.sqrt x) ∧
    (∀ x : Real, (438_429 : Real) < x →
      x ≤ TGComputeContracts.HurstV2.sourceLimit →
      |TGComputeContracts.HurstV2.squarefreeStep x -
          (6 / Real.pi ^ 2) * x| ≤
        (57 / 2_000 : Real) * Real.sqrt x)

/-- Hurst's source-normal Mertens field. -/
abbrev MertensHurstClaim : Prop :=
  ∀ x : Real, 33 ≤ x → x ≤ TGComputeContracts.HurstV2.sourceLimit →
    |TGComputeContracts.HurstV2.mertensStep x| ≤
      ((571 : Real) / 1_000) * Real.sqrt x

/-- Platt--Lambov equation (2.11), as projected from the shared Hurst run. -/
abbrev PlattLittleMertens211Claim : Prop :=
  ∀ x : Real, 1 ≤ x → x ≤ TGComputeContracts.HurstV2.little211Limit →
    |TGComputeContracts.HurstV2.littleMertensStep x| ≤
      Real.sqrt (2 / x)

/-- Platt's stronger finite little-Mertens range. -/
abbrev PlattLittleMertensStrongerClaim : Prop :=
  ∀ x : Real, 3 ≤ x →
    x ≤ TGComputeContracts.HurstV2.littleStrongerLimit →
    |TGComputeContracts.HurstV2.littleMertensStep x| ≤
      1 / (2 * Real.sqrt x)

/-! ## Closed atom-to-proposition map -/

/-- The exact mathematical proposition obtained from each compact checker.

For `plattHead2e4` this is intentionally the table-opaque committed
existential, not the separately materialized downstream-table proposition. -/
def CheckerDerivedClaim :
    TernaryGoldbachExternalAtom → Prop
  | .ch25A7Boundary =>
      A7BoundarySourceSemantics.SourceClaim
  | .ch25Psi1e13 =>
      PsiSourceSemantics.SourceClaim
  | .plattHead2e4 =>
      ZetaHeadCompactChecker.CommittedSourceClaim
  | .plattTrudgianRH3e12 =>
      ZetaRHSourceSemantics.SourceClaim
  | .helfgottProp1224 =>
      Prop1224SourceSemantics.SourceClaim
  | .cdemSquarefree =>
      CDEMSquarefreeClaim
  | .cdemTableAbel =>
      CDEMAbelSource.SourceClaim
  | .mertensHurst =>
      MertensHurstClaim
  | .ramareZunigaLemma62 =>
      R2StarSourceSemantics.SourceClaim
  | .helfgottPlattTheorem41 =>
      GoldbachSourceSemantics.SourceClaim
  | .plattDirichletTheorem71 =>
      SparkInterval.Dirichlet.PlattTheorem71DirichletVerification
  | .plattLittleMertens211 =>
      PlattLittleMertens211Claim
  | .plattLittleMertensStronger =>
      PlattLittleMertensStrongerClaim

/-- Downstream proposition map after choosing the exact Platt-head table.

All branches are definitionally the checker-derived proposition except the
Platt head, whose downstream proposition names `targetTable` exactly. -/
def ExactTableDownstreamClaim
    (targetTable : ZetaHeadSourceSemantics.Q128CellTable) :
    TernaryGoldbachExternalAtom → Prop
  | .plattHead2e4 =>
      ZetaHeadSourceSemantics.Q128SourceClaim targetTable
  | atom =>
      CheckerDerivedClaim atom

/-- The one remaining Platt-head identification obligation.

This is stated as the exact implication actually needed by the downstream
proof.  It is not derived from digest equality.  A full-table integration may
prove it by retaining the exact table witness (or by an ordinary row-identity
proof) before the witness is erased behind the compact existential. -/
def ZetaHeadTableIdentificationObligation
    (targetTable : ZetaHeadSourceSemantics.Q128CellTable) : Prop :=
  ZetaHeadCompactChecker.CommittedSourceClaim →
    ZetaHeadSourceSemantics.Q128SourceClaim targetTable

/-! ## Ten physical checker acceptances -/

/-- Exact semantic acceptances for the ten physical campaigns serving all
thirteen atoms.

This record contains no receipt, signature, attestation, architecture trace,
or source claim.  A future architecture-refinement layer obtains these fields
from the corresponding exact measured executions. -/
structure CanonicalCheckerAcceptances : Prop where
  ch25A7Boundary :
    A7BoundaryCompactChecker.nativeChecker.accepts
      A7BoundaryCompactChecker.canonicalInputBytes
      A7BoundaryCompactChecker.canonicalResultBytes
  ch25PsiLemma92 :
    PsiCompactChecker.nativeChecker.accepts
      PsiCompactChecker.canonicalInputBytes
      PsiCompactChecker.canonicalResultBytes
  plattHead2e4 :
    ZetaHeadCompactChecker.nativeChecker.accepts
      ZetaHeadCompactChecker.canonicalInputBytes
      ZetaHeadCompactChecker.canonicalResultBytes
  plattTrudgianRH3e12 :
    ZetaRHCompactChecker.nativeChecker.accepts
      ZetaRHCompactChecker.canonicalInputBytes
      ZetaRHCompactChecker.canonicalResultBytes
  helfgottProp1224 :
    Prop1224CompactChecker.nativeChecker.accepts
      Prop1224CompactChecker.canonicalInputBytes
      Prop1224CompactChecker.canonicalResultBytes
  hurstSharedFourResidual :
    HurstCompactChecker.nativeChecker.accepts
      HurstCompactChecker.canonicalInputBytes
      HurstCompactChecker.canonicalResultBytes
  cdemTableAbel :
    CDEMAbelCompactChecker.nativeChecker.accepts
      CDEMAbelCompactChecker.canonicalInputBytes
      CDEMAbelCompactChecker.canonicalResultBytes
  ramareZunigaLemma62 :
    R2StarCompactChecker.nativeChecker.accepts
      R2StarCompactChecker.canonicalInputBytes
      R2StarCompactChecker.canonicalResultBytes
  helfgottPlattTheorem41 :
    GoldbachCompactChecker.nativeChecker.accepts
      GoldbachCompactChecker.canonicalInputBytes
      GoldbachCompactChecker.canonicalResultBytes
  plattDirichletTheorem71 :
    SparkInterval.Dirichlet.PlattTheorem71CompactChecker.nativeChecker.accepts
      SparkInterval.Dirichlet.PlattTheorem71CompactChecker.canonicalInputBytes
      SparkInterval.Dirichlet.PlattTheorem71CompactChecker.canonicalResultBytes

/-! ## Axiom-free composition -/

/-- The ten exact checker acceptances project to every one of the thirteen
checker-derived mathematical claims. -/
theorem checkerDerivedClaim_of_canonicalAcceptances
    (accepted : CanonicalCheckerAcceptances) :
    ∀ atom : TernaryGoldbachExternalAtom, CheckerDerivedClaim atom := by
  intro atom
  cases atom with
  | ch25A7Boundary =>
      exact A7BoundaryCompactChecker.sourceClaim_of_acceptance
        accepted.ch25A7Boundary
  | ch25Psi1e13 =>
      exact PsiCompactChecker.sourceClaim_of_acceptance
        accepted.ch25PsiLemma92
  | plattHead2e4 =>
      exact ZetaHeadCompactChecker.committedSourceClaim_of_acceptance
        accepted.plattHead2e4
  | plattTrudgianRH3e12 =>
      exact ZetaRHCompactChecker.sourceClaim_of_acceptance
        accepted.plattTrudgianRH3e12
  | helfgottProp1224 =>
      exact Prop1224CompactChecker.sourceClaim_of_acceptance
        accepted.helfgottProp1224
  | cdemSquarefree =>
      let claims :=
        HurstCompactChecker.realClaims_of_acceptance
          accepted.hurstSharedFourResidual
      exact ⟨claims.squarefreeB1, claims.squarefreeB2⟩
  | cdemTableAbel =>
      exact CDEMAbelCompactChecker.sourceClaim_of_acceptance
        accepted.cdemTableAbel
  | mertensHurst =>
      exact
        (HurstCompactChecker.realClaims_of_acceptance
          accepted.hurstSharedFourResidual).hurst
  | ramareZunigaLemma62 =>
      exact R2StarCompactChecker.sourceClaim_of_acceptance
        accepted.ramareZunigaLemma62
  | helfgottPlattTheorem41 =>
      exact GoldbachCompactChecker.sourceClaim_of_acceptance
        accepted.helfgottPlattTheorem41
  | plattDirichletTheorem71 =>
      exact
        SparkInterval.Dirichlet.PlattTheorem71CompactChecker.sourceClaim_of_acceptance
          accepted.plattDirichletTheorem71
  | plattLittleMertens211 =>
      exact
        (HurstCompactChecker.realClaims_of_acceptance
          accepted.hurstSharedFourResidual).little211
  | plattLittleMertensStronger =>
      exact
        (HurstCompactChecker.realClaims_of_acceptance
          accepted.hurstSharedFourResidual).littleStronger

/-- Checker-derived claims become the exact-table downstream claims precisely
after supplying the separate Platt-head table-identification theorem. -/
theorem exactTableDownstreamClaim_of_checkerDerivedClaim
    (targetTable : ZetaHeadSourceSemantics.Q128CellTable)
    (identify : ZetaHeadTableIdentificationObligation targetTable) :
    ∀ atom : TernaryGoldbachExternalAtom,
      CheckerDerivedClaim atom → ExactTableDownstreamClaim targetTable atom := by
  intro atom claim
  cases atom <;> first
    | exact identify claim
    | exact claim

/-- Full thirteen-atom exact-table capstone from the ten canonical checker
acceptances and the one honest table-identification obligation. -/
theorem exactTableDownstreamClaim_of_canonicalAcceptances
    (targetTable : ZetaHeadSourceSemantics.Q128CellTable)
    (accepted : CanonicalCheckerAcceptances)
    (identify : ZetaHeadTableIdentificationObligation targetTable) :
    ∀ atom : TernaryGoldbachExternalAtom,
      ExactTableDownstreamClaim targetTable atom := by
  intro atom
  exact
    exactTableDownstreamClaim_of_checkerDerivedClaim targetTable identify atom
      (checkerDerivedClaim_of_canonicalAcceptances accepted atom)

end SparkInterval.TernaryGoldbach.CompactExternalAtomCapstone

end
