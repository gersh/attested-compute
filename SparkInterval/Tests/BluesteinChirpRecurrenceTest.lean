/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.BluesteinChirpRecurrence

set_option autoImplicit false

namespace SparkInterval.Tests.BluesteinChirpRecurrenceTest

open SparkInterval
open SparkInterval.Dirichlet.BluesteinDFT
open SparkInterval.Dirichlet.BluesteinChirpRecurrence

noncomputable def exactRounding : DirectedRound where
  down := id
  up := id
  down_le := by simp
  le_up := by simp

noncomputable def pointInitial (order : Nat) : IntervalState where
  chirp := ComplexInterval.point (halfRoot order 0)
  oddStep := ComplexInterval.point (halfRoot order 1)

theorem pointInitial_contains (order : Nat) :
    StateContains (pointInitial order) (exactInitial order) := by
  exact
    ⟨ComplexInterval.point_contains _,
      ComplexInterval.point_contains _⟩

example (order n : Nat) :
    (exactStateAt order n).chirp =
      halfRoot order ((n : Int) ^ 2) :=
  exactStateAt_chirp order n

/-- A non-vacuous exact-rounding instance of the optimized recurrence. -/
example (order n : Nat) :
    (runDirected exactRounding
      (ComplexInterval.point (signedUnitRoot order 1))
      n (pointInitial order)).chirp.Contains
        (halfRoot order ((n : Int) ^ 2)) :=
  runDirected_chirp_contains exactRounding
    (ComplexInterval.point_contains _)
    (pointInitial_contains order)

/-- The recurrence may be restarted from any exact anchor. -/
example (order start count : Nat) :
    (runDirected exactRounding
      (ComplexInterval.point (signedUnitRoot order 1))
      count
      { chirp :=
          ComplexInterval.point (exactStateAt order start).chirp
        oddStep :=
          ComplexInterval.point (exactStateAt order start).oddStep }).chirp.Contains
      (halfRoot order (((start + count : Nat) : Int) ^ 2)) := by
  apply runDirected_from_chirp_contains exactRounding
  · exact ComplexInterval.point_contains _
  · exact
      ⟨ComplexInterval.point_contains _,
        ComplexInterval.point_contains _⟩

#print axioms halfRoot_add
#print axioms halfRoot_two_mul
#print axioms exactStateAt_spec
#print axioms directedNext_contains
#print axioms runDirected_contains
#print axioms runDirected_from_contains
#print axioms runDirected_from_chirp_contains
#print axioms runDirected_chirp_contains

end SparkInterval.Tests.BluesteinChirpRecurrenceTest
