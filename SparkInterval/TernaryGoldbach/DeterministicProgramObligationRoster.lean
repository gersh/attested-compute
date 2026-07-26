/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.DeterministicFinalizerIR
import SparkInterval.Execution.FixedDecisionChecker
import SparkInterval.TernaryGoldbach.CompactExternalAtomCapstone
import SparkInterval.TernaryGoldbach.RamareNativeFoldsCompactChecker

/-!
# Closed deterministic-program obligations for all Goldbach campaigns

The ternary-Goldbach architecture registry has exactly twelve physical
campaigns:

* ten campaigns for the thirteen named external atoms;
* one aggregate finalizer for all fifteen historically native-generated
  families; and
* one independently deployable fallback for the three long Ramaré folds.

Before any compiler, linker, loader, x86-64, PTX, SASS, CPU, or GPU theorem
can close an architecture refinement, each campaign must supply a
deterministic byte program and an ordinary proof that successful evaluation
of that program refines its exact `NativeCheckerSemantics`.

`ClosedRoster` makes those twelve source-program obligations explicit.  The
aggregate proposition, decision procedure, checker identifier, and success
bytes are parameters because their exact source bundle lives in the
downstream `claude_math` package.  They are fixed for an instantiation and
the aggregate checker is definitionally the existing
`FixedDecisionChecker.nativeChecker`; they are not fields selectable by a
receipt or executable.

This module constructs no roster, architecture refinement, executable
certificate, or physical outcome.  It contains no axiom and no receipt data.
-/

set_option autoImplicit false

namespace
  SparkInterval.TernaryGoldbach.DeterministicProgramObligationRoster

open SparkInterval.Execution.Architecture
open
  SparkInterval.Execution.Architecture.DeterministicFinalizerIR

abbrev Invocation :=
  RegisteredArchitectureInvocation

/-- Exact fixed checker selected for each of the twelve registry
constructors.

The aggregate branch uses the fixed-decision adapter parameterized by the
one closed downstream all-native source bundle.  Every other branch is fully
closed in this package. -/
def checker
    (AggregateClaim : Prop) [Decidable AggregateClaim]
    (aggregateCheckerId : String)
    (aggregateSuccessResult : ByteArray) :
    Invocation → NativeCheckerSemantics
  | .ch25A7BoundaryProductionV1 =>
      A7BoundaryCompactChecker.nativeChecker
  | .ch25PsiLemma92ProductionV1 =>
      PsiCompactChecker.nativeChecker
  | .plattHead2e4ProductionV1 =>
      ZetaHeadCompactChecker.nativeChecker
  | .plattTrudgianFiniteRHProductionV1 =>
      ZetaRHCompactChecker.nativeChecker
  | .helfgottProp1224ProductionV1 =>
      Prop1224CompactChecker.nativeChecker
  | .hurstSharedFourResidualProductionV2 =>
      HurstCompactChecker.nativeChecker
  | .cdemTableAbelProductionV2 =>
      CDEMAbelCompactChecker.nativeChecker
  | .ramareZunigaLemma62ProductionV1 =>
      R2StarCompactChecker.nativeChecker
  | .helfgottPlattGoldbachProductionV1 =>
      GoldbachCompactChecker.nativeChecker
  | .plattDirichletTheorem71ProductionV1 =>
      SparkInterval.Dirichlet.PlattTheorem71CompactChecker.nativeChecker
  | .nativeGeneratedAggregateProductionV1 =>
      FixedDecisionChecker.nativeChecker
        AggregateClaim aggregateCheckerId aggregateSuccessResult
  | .ramareProductionFoldsCompactV1 =>
      RamareNativeFoldsCompactChecker.nativeChecker

/-- Source-program certificate required for one exact physical campaign. -/
abbrev Obligation
    (AggregateClaim : Prop) [Decidable AggregateClaim]
    (aggregateCheckerId : String)
    (aggregateSuccessResult : ByteArray)
    (invocation : Invocation) : Type :=
  Certificate
    (checker AggregateClaim aggregateCheckerId
      aggregateSuccessResult invocation)

/-- The twelve named, source-program-level proof obligations.

Each field supplies actual deterministic program data and its universal
program-to-checker proof.  None of the fields contains an application
proposition, receipt, executable image, architecture trace, or arbitrary
claim theorem. -/
structure ClosedRoster
    (AggregateClaim : Prop) [Decidable AggregateClaim]
    (aggregateCheckerId : String)
    (aggregateSuccessResult : ByteArray) : Type where
  ch25A7Boundary :
    Obligation AggregateClaim aggregateCheckerId aggregateSuccessResult
      .ch25A7BoundaryProductionV1
  ch25PsiLemma92 :
    Obligation AggregateClaim aggregateCheckerId aggregateSuccessResult
      .ch25PsiLemma92ProductionV1
  plattHead2e4 :
    Obligation AggregateClaim aggregateCheckerId aggregateSuccessResult
      .plattHead2e4ProductionV1
  plattTrudgianRH3e12 :
    Obligation AggregateClaim aggregateCheckerId aggregateSuccessResult
      .plattTrudgianFiniteRHProductionV1
  helfgottProp1224 :
    Obligation AggregateClaim aggregateCheckerId aggregateSuccessResult
      .helfgottProp1224ProductionV1
  hurstSharedFourResidual :
    Obligation AggregateClaim aggregateCheckerId aggregateSuccessResult
      .hurstSharedFourResidualProductionV2
  cdemTableAbel :
    Obligation AggregateClaim aggregateCheckerId aggregateSuccessResult
      .cdemTableAbelProductionV2
  ramareZunigaLemma62 :
    Obligation AggregateClaim aggregateCheckerId aggregateSuccessResult
      .ramareZunigaLemma62ProductionV1
  helfgottPlattTheorem41 :
    Obligation AggregateClaim aggregateCheckerId aggregateSuccessResult
      .helfgottPlattGoldbachProductionV1
  plattDirichletTheorem71 :
    Obligation AggregateClaim aggregateCheckerId aggregateSuccessResult
      .plattDirichletTheorem71ProductionV1
  nativeGeneratedAggregate :
    Obligation AggregateClaim aggregateCheckerId aggregateSuccessResult
      .nativeGeneratedAggregateProductionV1
  ramareProductionFolds :
    Obligation AggregateClaim aggregateCheckerId aggregateSuccessResult
      .ramareProductionFoldsCompactV1

namespace ClosedRoster

/-- Select the exact deterministic-program proof for any closed registry
constructor.  Pattern matching is exhaustive over the twelve constructors,
so no physical campaign can be omitted. -/
def obligation
    {AggregateClaim : Prop} [Decidable AggregateClaim]
    {aggregateCheckerId : String}
    {aggregateSuccessResult : ByteArray}
    (roster :
      ClosedRoster AggregateClaim aggregateCheckerId aggregateSuccessResult) :
    (invocation : Invocation) →
      Obligation AggregateClaim aggregateCheckerId
        aggregateSuccessResult invocation
  | .ch25A7BoundaryProductionV1 =>
      roster.ch25A7Boundary
  | .ch25PsiLemma92ProductionV1 =>
      roster.ch25PsiLemma92
  | .plattHead2e4ProductionV1 =>
      roster.plattHead2e4
  | .plattTrudgianFiniteRHProductionV1 =>
      roster.plattTrudgianRH3e12
  | .helfgottProp1224ProductionV1 =>
      roster.helfgottProp1224
  | .hurstSharedFourResidualProductionV2 =>
      roster.hurstSharedFourResidual
  | .cdemTableAbelProductionV2 =>
      roster.cdemTableAbel
  | .ramareZunigaLemma62ProductionV1 =>
      roster.ramareZunigaLemma62
  | .helfgottPlattGoldbachProductionV1 =>
      roster.helfgottPlattTheorem41
  | .plattDirichletTheorem71ProductionV1 =>
      roster.plattDirichletTheorem71
  | .nativeGeneratedAggregateProductionV1 =>
      roster.nativeGeneratedAggregate
  | .ramareProductionFoldsCompactV1 =>
      roster.ramareProductionFolds

/-- Every campaign in a roster supplies the ordinary source-program
behavior theorem required before the compiler and architecture layers. -/
theorem sourceToChecker
    {AggregateClaim : Prop} [Decidable AggregateClaim]
    {aggregateCheckerId : String}
    {aggregateSuccessResult : ByteArray}
    (roster :
      ClosedRoster AggregateClaim aggregateCheckerId aggregateSuccessResult)
    (invocation : Invocation) :
    X86ELF.BehaviorRefines
      (roster.obligation invocation).program.successBehavior
      (checker AggregateClaim aggregateCheckerId
        aggregateSuccessResult invocation).accepts :=
  (roster.obligation invocation).sourceToChecker

end ClosedRoster

/-- The authoritative architecture registry contains exactly the twelve
program obligations named above. -/
theorem registeredCampaignCount :
    RegisteredArchitectureInvocation.all.length = 12 := by
  rfl

/-- Every registry constructor occurs in the closed twelve-campaign list. -/
theorem mem_registeredCampaigns (invocation : Invocation) :
    invocation ∈ RegisteredArchitectureInvocation.all := by
  cases invocation <;>
    simp [RegisteredArchitectureInvocation.all,
      RegisteredArchitectureInvocation.externalCampaigns,
      RegisteredArchitectureInvocation.nativeAggregateCampaigns,
      RegisteredArchitectureInvocation.nativeFamilyFallbacks]

end SparkInterval.TernaryGoldbach.DeterministicProgramObligationRoster
