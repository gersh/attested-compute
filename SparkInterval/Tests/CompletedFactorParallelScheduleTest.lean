/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CompletedFactorParallelSchedule

set_option autoImplicit false

namespace SparkInterval.Tests.CompletedFactorParallelSchedule

open SparkInterval.Dirichlet.CompletedConductorPhase
open SparkInterval.Dirichlet.CompletedFactorParallelSchedule

example : chunkSize 4_096 = 16 := by
  norm_num [chunkSize, threadsPerBlock]

example : chunkSize 1_012 = 4 := by
  norm_num [chunkSize, threadsPerBlock]

example :
    threadOwner 4_096 4_095 = 255 ∧
      threadOffset 4_096 4_095 = 15 := by
  norm_num [threadOwner, threadOffset, chunkSize, threadsPerBlock]

example :
    threadStart 4_096 (threadOwner 4_096 4_095) = 4_080 ∧
      threadStop 4_096 (threadOwner 4_096 4_095) = 4_096 := by
  norm_num [threadStart, threadStop, threadOwner, chunkSize,
    threadsPerBlock]

example :
    exponentAt (7 / 11) 4_095 =
      exponentAt (7 / 11)
          (threadStart 4_096 (threadOwner 4_096 4_095)) +
        (threadOffset 4_096 4_095 : ℚ) * exponentStep := by
  exact conductorExponentAt_thread (7 / 11) (by norm_num) (by norm_num)

#print axioms chunkSize_positive
#print axioms span_le_thread_capacity
#print axioms threadOwner_lt
#print axioms sample_mem_owner
#print axioms threadStart_add_offset
#print axioms thread_eq_owner
#print axioms conductorExponentAt_thread

end SparkInterval.Tests.CompletedFactorParallelSchedule
