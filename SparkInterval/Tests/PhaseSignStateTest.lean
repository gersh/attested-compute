/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.PhaseSignState

set_option autoImplicit false

namespace SparkInterval.Tests.PhaseSignStateTest

open SparkInterval.Dirichlet.PhaseSignState

def negativeChunk : State :=
  ⟨2, 0, some false, some false, 0⟩

def positiveChunk : State :=
  ⟨3, 1, some true, some true, 0⟩

example :
    (State.combine negativeChunk positiveChunk).transitionCount = 1 := by
  decide

example :
    State.combine
        (State.combine negativeChunk State.empty)
        positiveChunk =
      State.combine negativeChunk
        (State.combine State.empty positiveChunk) := by
  exact State.combine_assoc _ _ _
    (by simp [negativeChunk, State.BoundaryValid])
    (by simp [State.empty, State.BoundaryValid])
    (by simp [positiveChunk, State.BoundaryValid])

def trailingAmbiguity : AmbiguityRunState.State :=
  ⟨4, some false, some true, 1⟩

def leadingAmbiguity : AmbiguityRunState.State :=
  ⟨5, some true, some false, 1⟩

example :
    (AmbiguityRunState.combine trailingAmbiguity
      leadingAmbiguity).rangeCount = 1 := by
  decide

example :
    AmbiguityRunState.combine
        (AmbiguityRunState.combine trailingAmbiguity
          AmbiguityRunState.empty)
        leadingAmbiguity =
      AmbiguityRunState.combine trailingAmbiguity
        (AmbiguityRunState.combine AmbiguityRunState.empty
          leadingAmbiguity) := by
  exact AmbiguityRunState.combine_assoc _ _ _
    (by simp [trailingAmbiguity, AmbiguityRunState.Valid])
    (by simp [AmbiguityRunState.empty, AmbiguityRunState.Valid])
    (by simp [leadingAmbiguity, AmbiguityRunState.Valid])

#print axioms
  SparkInterval.Dirichlet.PhaseSignState.State.combine_boundaryValid
#print axioms
  SparkInterval.Dirichlet.PhaseSignState.State.combine_assoc
#print axioms
  SparkInterval.Dirichlet.PhaseSignState.AmbiguityRunState.combine_assoc

end SparkInterval.Tests.PhaseSignStateTest
