/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.CDEMAbelReplayAlgorithm

/-!
Focused, non-production tests for the typed CDEM replay algorithm.

The fixture has two symbolic events.  It does not evaluate the production
Möbius sum or materialize any production certificate.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.CDEMAbelReplayAlgorithm

open SparkInterval.TernaryGoldbach
open CDEMAbelReplayAlgorithm

def fixtureRequest : ReplayRequest where
  low := 1
  high := 2
  before := 0

def fixtureData : ReplayKernelData where
  divisorJump :=
    CDEMAbelRecurrenceCertificate.floorJump
  sqrtWeight :=
    fun _ => CDEMAbelSource.weightScale

theorem fixtureData_valid :
    fixtureData.ValidFor fixtureRequest := by
  intro n hn
  constructor
  · rfl
  · have hnOne : 1 ≤ n :=
      (Finset.mem_Ico.mp hn).1
    change
      CDEMAbelSource.weightScale *
          CDEMAbelSource.weightScale ≤
        CDEMAbelSource.weightScale *
          CDEMAbelSource.weightScale * n
    have hmul :=
      Nat.mul_le_mul_left
        (CDEMAbelSource.weightScale *
          CDEMAbelSource.weightScale) hnOne
    simpa [Nat.mul_assoc] using hmul

theorem fixture_accepts :
    Accepts fixtureRequest
      (replayOutput fixtureRequest fixtureData) := by
  refine ⟨by norm_num [fixtureRequest, ReplayRequest.WellFormed,
    CDEMAbelRecurrenceCertificate.sourcePast,
    CDEMAbelSource.indexUpper], fixtureData, fixtureData_valid, rfl⟩

theorem fixture_locallyRealizes :
    (returnedChunk fixtureRequest
      (replayOutput fixtureRequest fixtureData)).LocallyRealizes :=
  locallyRealizes_of_accepts fixture_accepts

#print axioms CDEMAbelReplayAlgorithm.scanSteps_prefixInvariant
#print axioms CDEMAbelReplayAlgorithm.locallyRealizes_of_accepts
#print axioms CDEMAbelReplayAlgorithm.Supervisor.localEvidence_of_acceptance
#print axioms CDEMAbelReplayAlgorithm.Supervisor.sourceClaim_of_acceptance
#print axioms CDEMAbelReplayAlgorithm.sourceClaim_of_native_acceptance

end SparkInterval.Tests.CDEMAbelReplayAlgorithm
