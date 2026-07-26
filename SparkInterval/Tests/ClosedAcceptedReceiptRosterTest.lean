/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.ClosedAcceptedReceiptRoster

set_option autoImplicit false

namespace SparkInterval.Tests.ClosedAcceptedReceiptRoster

open SparkInterval.Execution.Architecture
open SparkInterval.TernaryGoldbach.ClosedAcceptedReceiptRoster

example :
    ¬ RequiredRoster :=
  no_current_requiredRoster

example (roster : RequiredRoster) :
    SparkInterval.TernaryGoldbach.CompactExternalAtomRegisteredCapstone.RegisteredPhysicalOutcomes :=
  roster.externalPhysicalOutcomes

example (roster : RequiredRoster) :
    ∃ statement receiptHash,
      RegisteredArchitectureInvocation.nativeGeneratedAggregateProductionV1.PhysicalOutcome
        statement receiptHash :=
  roster.nativeAggregatePhysicalOutcome

#print axioms ReceiptOutcome.physicalOutcome
#print axioms RequiredRoster.externalPhysicalOutcomes
#print axioms RequiredRoster.nativeAggregatePhysicalOutcome
#print axioms no_current_requiredRoster

end SparkInterval.Tests.ClosedAcceptedReceiptRoster
