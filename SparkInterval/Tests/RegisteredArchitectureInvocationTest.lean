/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.CompactArchitectureRegistry

/-!
# Tiny tests for the closed ternary-Goldbach architecture catalog

These tests reduce only closed constructor tables.  They contain no
production bytes, generated certificate tables, native execution, or trace
replay.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.RegisteredArchitectureInvocation

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

example :
    TernaryGoldbachExternalAtom.all.length = 13 := by
  rfl

example :
    RegisteredArchitectureInvocation.externalCampaigns.length = 10 := by
  rfl

example :
    RegisteredArchitectureInvocation.nativeFamilyFallbacks.length = 1 := by
  rfl

example :
    RegisteredArchitectureInvocation.nativeAggregateCampaigns.length = 1 := by
  rfl

example :
    RegisteredArchitectureInvocation.all.length = 12 := by
  rfl

example :
    TernaryGoldbachExternalAtom.cdemSquarefree.physicalInvocation =
      .hurstSharedFourResidualProductionV2 := by
  rfl

example :
    TernaryGoldbachExternalAtom.mertensHurst.physicalInvocation =
      TernaryGoldbachExternalAtom.plattLittleMertens211.physicalInvocation := by
  rfl

example :
    TernaryGoldbachExternalAtom.plattLittleMertens211.physicalInvocation =
      TernaryGoldbachExternalAtom.plattLittleMertensStronger.physicalInvocation := by
  rfl

example (atom : TernaryGoldbachExternalAtom) :
    atom ∈ atom.physicalInvocation.claims :=
  atom.mem_claims_physicalInvocation

example :
    RegisteredArchitectureInvocation.ramareZunigaLemma62ProductionV1.placement =
      .h100ProducersAzureCPUFinalizer := by
  rfl

example :
    RegisteredArchitectureInvocation.helfgottPlattGoldbachProductionV1.placement =
      .h100ProducersAzureCPUFinalizer := by
  rfl

example :
    RegisteredArchitectureInvocation.plattDirichletTheorem71ProductionV1.placement =
      .h100ProducersAzureCPUFinalizer := by
  rfl

example :
    RegisteredArchitectureInvocation.ramareZunigaLemma62ProductionV1.terminalTarget =
      .azureSEVSNPCPU := by
  rfl

example :
    RegisteredArchitectureInvocation.helfgottPlattGoldbachProductionV1.terminalTarget =
      .azureSEVSNPCPU := by
  rfl

example :
    RegisteredArchitectureInvocation.ramareProductionFoldsCompactV1.claimKind =
      .nativeFamilyFallback := by
  rfl

example :
    RegisteredArchitectureInvocation.nativeGeneratedAggregateProductionV1.claimKind =
      .nativeGeneratedAggregate := by
  rfl

example :
    RegisteredArchitectureInvocation.nativeGeneratedAggregateProductionV1.claims =
      [] := by
  rfl

example :
    RegisteredArchitectureInvocation.nativeGeneratedAggregateProductionV1.placement =
      .h100ProducersAzureCPUFinalizer := by
  rfl

example :
    RegisteredArchitectureInvocation.nativeGeneratedAggregateProductionV1.terminalTarget =
      .azureSEVSNPCPU := by
  rfl

example :
    RegisteredArchitectureInvocation.ramareProductionFoldsCompactV1.claims =
      [] := by
  rfl

example :
    RegisteredArchitectureInvocation.ramareProductionFoldsCompactV1.placement =
      .azureConfidentialCPU := by
  rfl

example
    (invocation : RegisteredArchitectureInvocation)
    (statement : RunStatement)
    (receiptHash : Digest) :
    ¬ invocation.ReceiptSelected statement receiptHash :=
  RegisteredArchitectureInvocation.not_receiptSelected_of_reviewedRun_eq_none
    (RegisteredArchitectureInvocation.reviewedRun_currently_none invocation)

example
    (invocation : RegisteredArchitectureInvocation)
    (statement : RunStatement)
    (receiptHash : Digest) :
    ¬ invocation.PhysicalOutcome statement receiptHash :=
  RegisteredArchitectureInvocation.not_physicalOutcome_of_reviewedRun_eq_none
    (RegisteredArchitectureInvocation.reviewedRun_currently_none invocation)

end SparkInterval.Tests.RegisteredArchitectureInvocation
