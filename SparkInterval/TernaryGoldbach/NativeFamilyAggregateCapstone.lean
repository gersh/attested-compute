/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.FixedDecisionChecker
import SparkInterval.TernaryGoldbach.NativeFamilyArchitectureCatalog

/-!
# Closed aggregate receipt composition for native-generated families

This module supplies the common physical layer for all 15 historically
native-generated ternary-Goldbach families.  It deliberately does not name a
mathematical proposition.  A downstream family module must fix its exact
source-decision bundle, checker identifier, and result encoding, then prove
the universal executable/compiler/loader/ISA refinement.

The only opaque premise is a physical outcome for the single closed
`nativeGeneratedAggregateProductionV1` registry constructor.  The proposition
is not stored in a receipt and is not an argument to the trusted axiom.  A
caller-selected proposition remains harmless here because obtaining it also
requires an ordinary proof that the one fixed reviewed executable refines the
corresponding decision checker.  Public production adapters should close all
parameters so reviewers see one theorem per exact family bundle.

No production input or trace is retained or replayed, and this module
introduces no axiom.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.NativeFamilyAggregateCapstone

open SparkInterval.Execution
open SparkInterval.Execution.Architecture

namespace Registry

/-- The sole aggregate physical invocation used by every native family. -/
abbrev invocation : RegisteredArchitectureInvocation :=
  .nativeGeneratedAggregateProductionV1

/-- An existentially hidden signed statement and receipt for the exact closed
aggregate invocation. -/
def PhysicalOutcome : Prop :=
  ∃ (statement : RunStatement) (receiptHash : Digest),
    invocation.PhysicalOutcome statement receiptHash

end Registry

/-- Universal executable refinement for a family-specific fixed decision
bundle and the actual value installed by the closed aggregate registry.

The `reviewedRun = some reviewed` hypothesis is essential: while the registry
branch is `none`, this proposition is vacuously true but cannot be combined
with `Registry.PhysicalOutcome`, which is provably unavailable. -/
def ClosedDecisionRefinement
    (Claim : Prop) [Decidable Claim]
    (checkerId : String)
    (successResult : ByteArray) : Prop :=
  ∀ reviewed : ReviewedArchitectureRun Registry.invocation,
    Registry.invocation.reviewedRun = some reviewed →
      ArchitectureRefinesNativeChecker
        registeredSHA256MeasurementScheme reviewed.machine
        (FixedDecisionChecker.nativeChecker
          Claim checkerId successResult)
        reviewed.executableArtifact reviewed.compactPins.entryPoint

/-- One exact aggregate physical outcome plus the ordinary universal
architecture refinement proves the fixed decidable family bundle.

The proof only eliminates existential receipt witnesses and composes existing
ordinary theorems.  It does not evaluate `decide Claim`, hash a production
input, or traverse an architecture trace. -/
theorem claim_of_physicalOutcome
    (Claim : Prop) [Decidable Claim]
    (checkerId : String)
    (successResult : ByteArray)
    (outcome : Registry.PhysicalOutcome)
    (refinement :
      ClosedDecisionRefinement Claim checkerId successResult) :
    Claim := by
  rcases outcome with
    ⟨_statement, _receiptHash, reviewed, installed, _hashEq,
      _statementBound, execution⟩
  exact
    FixedDecisionChecker.claim_of_compactRun
      Claim checkerId successResult execution
      (refinement reviewed installed)

/-- Before a reviewed aggregate run is installed, ordinary Lean proves that
the physical premise required above is unavailable. -/
theorem no_current_physicalOutcome :
    ¬ Registry.PhysicalOutcome := by
  rintro ⟨statement, receiptHash, outcome⟩
  exact
    RegisteredArchitectureInvocation.not_physicalOutcome_of_reviewedRun_eq_none
      (show Registry.invocation.reviewedRun = none by rfl)
      outcome

end SparkInterval.TernaryGoldbach.NativeFamilyAggregateCapstone
