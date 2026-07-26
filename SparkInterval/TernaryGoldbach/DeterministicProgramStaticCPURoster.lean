/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.DeterministicProgramStaticCPUCertificate
import SparkInterval.TernaryGoldbach.DeterministicProgramObligationRoster

/-!
# Closed static-CPU certificate roster for all Goldbach campaigns

Every constructor of `RegisteredArchitectureInvocation` has the common
`azureSEVSNPCPU` terminal target.  This module records the exact next layer
above `DeterministicProgramObligationRoster.ClosedRoster`: for each of its
twelve deterministic source-program obligations, an `InstalledRoster`
requires a non-vacuous installed static-CPU certificate whose source-program
parameter is definitionally that exact obligation.

The selector is exhaustive over the closed invocation type, and the final
theorem supplies the universal architecture-to-checker refinement for every
constructor.  No roster inhabitant, reviewed run, receipt, executable,
architecture trace, or axiom is declared here.
-/

set_option autoImplicit false

namespace
  SparkInterval.TernaryGoldbach.DeterministicProgramStaticCPURoster

open SparkInterval.Execution.Architecture
open
  SparkInterval.Execution.Architecture.DeterministicProgramStaticCPUCertificate
open SparkInterval.TernaryGoldbach.DeterministicProgramObligationRoster

abbrev Invocation :=
  RegisteredArchitectureInvocation

/-- Exact checker selected by the source-program roster for one invocation. -/
abbrev Checker
    (AggregateClaim : Prop) [Decidable AggregateClaim]
    (aggregateCheckerId : String)
    (aggregateSuccessResult : ByteArray)
    (invocation : Invocation) : NativeCheckerSemantics :=
  checker AggregateClaim aggregateCheckerId aggregateSuccessResult invocation

/-- The installed certificate type for exactly the source-program obligation
selected by `roster` at `invocation`. -/
abbrev InstalledFor
    {AggregateClaim : Prop} [Decidable AggregateClaim]
    {aggregateCheckerId : String}
    {aggregateSuccessResult : ByteArray}
    (roster :
      ClosedRoster AggregateClaim aggregateCheckerId aggregateSuccessResult)
    (invocation : Invocation) : Type 1 :=
  InstalledCertificate invocation
    (Checker AggregateClaim aggregateCheckerId aggregateSuccessResult invocation)
    (roster.obligation invocation)

/-- Non-vacuous installed static-CPU evidence for all twelve exact
deterministic-program obligations.

Each field is tied to `roster.obligation` at a literal closed invocation.
There is no field permitting a caller-selected checker or source program. -/
structure InstalledRoster
    (AggregateClaim : Prop) [Decidable AggregateClaim]
    (aggregateCheckerId : String)
    (aggregateSuccessResult : ByteArray)
    (roster :
      ClosedRoster AggregateClaim aggregateCheckerId
        aggregateSuccessResult) : Type 1 where
  ch25A7Boundary :
    InstalledFor roster .ch25A7BoundaryProductionV1
  ch25PsiLemma92 :
    InstalledFor roster .ch25PsiLemma92ProductionV1
  plattHead2e4 :
    InstalledFor roster .plattHead2e4ProductionV1
  plattTrudgianRH3e12 :
    InstalledFor roster .plattTrudgianFiniteRHProductionV1
  helfgottProp1224 :
    InstalledFor roster .helfgottProp1224ProductionV1
  hurstSharedFourResidual :
    InstalledFor roster .hurstSharedFourResidualProductionV2
  cdemTableAbel :
    InstalledFor roster .cdemTableAbelProductionV2
  ramareZunigaLemma62 :
    InstalledFor roster .ramareZunigaLemma62ProductionV1
  helfgottPlattTheorem41 :
    InstalledFor roster .helfgottPlattGoldbachProductionV1
  plattDirichletTheorem71 :
    InstalledFor roster .plattDirichletTheorem71ProductionV1
  nativeGeneratedAggregate :
    InstalledFor roster .nativeGeneratedAggregateProductionV1
  ramareProductionFolds :
    InstalledFor roster .ramareProductionFoldsCompactV1

namespace InstalledRoster

/-- Exhaustively select the installed certificate tied to exactly
`roster.obligation invocation`. -/
def select
    {AggregateClaim : Prop} [Decidable AggregateClaim]
    {aggregateCheckerId : String}
    {aggregateSuccessResult : ByteArray}
    {roster :
      ClosedRoster AggregateClaim aggregateCheckerId
        aggregateSuccessResult}
    (installed :
      InstalledRoster AggregateClaim aggregateCheckerId
        aggregateSuccessResult roster) :
    (invocation : Invocation) → InstalledFor roster invocation
  | .ch25A7BoundaryProductionV1 =>
      installed.ch25A7Boundary
  | .ch25PsiLemma92ProductionV1 =>
      installed.ch25PsiLemma92
  | .plattHead2e4ProductionV1 =>
      installed.plattHead2e4
  | .plattTrudgianFiniteRHProductionV1 =>
      installed.plattTrudgianRH3e12
  | .helfgottProp1224ProductionV1 =>
      installed.helfgottProp1224
  | .hurstSharedFourResidualProductionV2 =>
      installed.hurstSharedFourResidual
  | .cdemTableAbelProductionV2 =>
      installed.cdemTableAbel
  | .ramareZunigaLemma62ProductionV1 =>
      installed.ramareZunigaLemma62
  | .helfgottPlattGoldbachProductionV1 =>
      installed.helfgottPlattTheorem41
  | .plattDirichletTheorem71ProductionV1 =>
      installed.plattDirichletTheorem71
  | .nativeGeneratedAggregateProductionV1 =>
      installed.nativeGeneratedAggregate
  | .ramareProductionFoldsCompactV1 =>
      installed.ramareProductionFolds

/-- Exact closed-refinement proposition for the checker selected at every
one of the twelve invocations. -/
def UniversalClosedRefinement
    (AggregateClaim : Prop) [Decidable AggregateClaim]
    (aggregateCheckerId : String)
    (aggregateSuccessResult : ByteArray) : Prop :=
  ∀ (invocation : Invocation)
      (reviewed : ReviewedArchitectureRun invocation),
    invocation.reviewedRun = some reviewed →
      ArchitectureRefinesNativeChecker
        registeredSHA256MeasurementScheme reviewed.machine
        (Checker AggregateClaim aggregateCheckerId
          aggregateSuccessResult invocation)
        reviewed.executableArtifact reviewed.compactPins.entryPoint

/-- An installed all-campaign roster supplies the universal closed
architecture refinement, using the exact selected source-program certificate
in every branch. -/
theorem universalClosedRefinement
    {AggregateClaim : Prop} [Decidable AggregateClaim]
    {aggregateCheckerId : String}
    {aggregateSuccessResult : ByteArray}
    {roster :
      ClosedRoster AggregateClaim aggregateCheckerId
        aggregateSuccessResult}
    (installed :
      InstalledRoster AggregateClaim aggregateCheckerId
        aggregateSuccessResult roster) :
    UniversalClosedRefinement AggregateClaim aggregateCheckerId
      aggregateSuccessResult := by
  intro invocation reviewed selected
  exact (installed.select invocation).closedRefinement reviewed selected

end InstalledRoster

end SparkInterval.TernaryGoldbach.DeterministicProgramStaticCPURoster
