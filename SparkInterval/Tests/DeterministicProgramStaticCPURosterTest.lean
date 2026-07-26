/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.DeterministicProgramStaticCPURoster

/-!
# Tiny tests for the closed deterministic-program static-CPU roster

These tests are conditional on an `InstalledRoster`; they construct no
reviewed run, receipt, executable certificate, or roster inhabitant.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.DeterministicProgramStaticCPURosterTest

open SparkInterval.Execution.Architecture
open SparkInterval.TernaryGoldbach.DeterministicProgramObligationRoster
open SparkInterval.TernaryGoldbach.DeterministicProgramStaticCPURoster

example
    {AggregateClaim : Prop} [Decidable AggregateClaim]
    {aggregateCheckerId : String}
    {aggregateSuccessResult : ByteArray}
    {roster :
      ClosedRoster AggregateClaim aggregateCheckerId
        aggregateSuccessResult}
    (installed :
      InstalledRoster AggregateClaim aggregateCheckerId
        aggregateSuccessResult roster) :
    InstalledFor roster .nativeGeneratedAggregateProductionV1 :=
  installed.select .nativeGeneratedAggregateProductionV1

example
    {AggregateClaim : Prop} [Decidable AggregateClaim]
    {aggregateCheckerId : String}
    {aggregateSuccessResult : ByteArray}
    {roster :
      ClosedRoster AggregateClaim aggregateCheckerId
        aggregateSuccessResult}
    (installed :
      InstalledRoster AggregateClaim aggregateCheckerId
        aggregateSuccessResult roster) :
    InstalledRoster.UniversalClosedRefinement
      AggregateClaim aggregateCheckerId aggregateSuccessResult :=
  installed.universalClosedRefinement

example (invocation : RegisteredArchitectureInvocation) :
    invocation.terminalTarget = .azureSEVSNPCPU :=
  invocation.terminalTarget_eq_azureSEVSNPCPU

#print axioms InstalledRoster.select
#print axioms InstalledRoster.universalClosedRefinement

end SparkInterval.Tests.DeterministicProgramStaticCPURosterTest
