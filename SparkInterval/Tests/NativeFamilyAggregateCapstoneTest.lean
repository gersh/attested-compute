/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.NativeFamilyAggregateCapstone

set_option autoImplicit false

namespace SparkInterval.Tests.NativeFamilyAggregateCapstone

open SparkInterval.Execution.Architecture
open SparkInterval.TernaryGoldbach.NativeFamilyAggregateCapstone

example :
    Registry.invocation.claimKind = .nativeGeneratedAggregate := by
  rfl

example :
    ¬ Registry.PhysicalOutcome :=
  no_current_physicalOutcome

/-- The generic composition is conditional on an exact executable
refinement; the current fail-closed registry cannot fabricate one physical
outcome. -/
example
    (Claim : Prop) [Decidable Claim]
    (checkerId : String)
    (successResult : ByteArray)
    (outcome : Registry.PhysicalOutcome)
    (refinement :
      ClosedDecisionRefinement Claim checkerId successResult) :
    Claim :=
  claim_of_physicalOutcome
    Claim checkerId successResult outcome refinement

end SparkInterval.Tests.NativeFamilyAggregateCapstone
