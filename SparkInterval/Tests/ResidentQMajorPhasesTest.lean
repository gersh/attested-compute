/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.ResidentQMajorPhases

namespace SparkInterval.Tests.ResidentQMajorPhasesTest

open Dirichlet.ResidentQMajorPhases

example : sourceTStop < 2 ^ 32 :=
  sourceTStop_lt_uint32

example : sourceTStop * 5 < 2 ^ 64 :=
  sourceStopNumerator_lt_uint64

example (t : Nat) (ht : t < 127988) :
    ∃! phase : Fin 10, InPhase phase t := by
  exact source_row_exists_unique_phase t ht

example (phase : Fin 10) :
    phaseStop phase - phaseFirst phase ≤ 39488 := by
  exact phase_row_count_le phase

example :
    ∑ slot : Fin 8, slotBatchedButterflies slot =
      15334965882246056 := by
  exact slot_work_sum

example :
    ∑ phase : Fin 10, phaseBatchedButterflies phase =
      15334965882246056 := by
  exact phase_work_sum

example (slot : Fin 8) :
    (∑ phase : Fin 10,
        if phaseSlot phase = slot then phaseBatchedButterflies phase else 0) =
      slotBatchedButterflies slot := by
  exact phase_work_by_slot slot

end SparkInterval.Tests.ResidentQMajorPhasesTest
