/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.AggregateTuringClosure

/-!
# Type-level regression tests for aggregate Dirichlet Turing closure

These checks keep the trusted joins visible: exact source-roster equivalence,
pointwise equality recovered from one finite-sum equality, and the final
`N ≥ 2` modulus theorem.  The separate `q = 1` zeta case is intentionally not
given a Dirichlet corollary here.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.AggregateTuringClosure

open SparkInterval.Dirichlet
open SparkInterval.Dirichlet.FactoredSmallQSourceRealization

noncomputable example {N : Nat} [NeZero N] {ids : List Nat}
    (realization : PrimitiveRosterRealization N ids) :
    Fin ids.length ≃
      {chi : DirichletCharacter Complex N // chi.IsPrimitive} :=
  realization.indexEquiv

example {ι : Type*} [Fintype ι]
    (evidence : AggregateTuringCountEvidence ι) (i : ι) :
    evidence.bracketCount i = evidence.turingCount i :=
  evidence.count_eq i

#print axioms PrimitiveRosterRealization.characterEquiv
#print axioms PrimitiveRosterRealization.indexEquiv
#print axioms AggregateTuringCountEvidence.count_eq
#print axioms AggregateTuringCountEvidence.zeroCountUpperBound_at_bracketCount
#print axioms grhVerifiedForModulus_of_completeRoster
#print axioms grhVerifiedForModulus_of_aggregateTuringEndpointFamilies
#print axioms
  grhVerifiedForModulus_of_sourceRoster_aggregateTuringEndpointFamilies

end SparkInterval.Tests.AggregateTuringClosure
