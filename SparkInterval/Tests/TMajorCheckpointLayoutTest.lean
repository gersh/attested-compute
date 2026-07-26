/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.TMajorCheckpointLayout

set_option autoImplicit false

namespace SparkInterval.Tests.TMajorCheckpointLayout

open SparkInterval.Dirichlet.CompletedConductorPhase
open SparkInterval.Dirichlet.TMajorCheckpointLayout

example : checkpointCount 8 4 = 2 := by
  norm_num [checkpointCount]

example : checkpointOwner 4 7 = 1 := by
  norm_num [checkpointOwner]

example : checkpointOffset 4 7 = 3 := by
  norm_num [checkpointOffset]

example :
    checkpointStart 4 (checkpointOwner 4 7) +
      checkpointOffset 4 7 = 7 := by
  exact checkpointStart_add_offset (by norm_num)

example :
    exponentAt (3 / 7) 7 =
      exponentAt (3 / 7)
        (checkpointStart 4 (checkpointOwner 4 7)) +
        (checkpointOffset 4 7 : ℚ) * exponentStep := by
  exact conductorExponentAt_checkpoint (3 / 7) (by norm_num)

#print axioms checkpointOwner_lt_count
#print axioms checkpointStart_lt_sampleCount
#print axioms sampleCount_le_checkpointCount_mul
#print axioms checkpoint_eq_owner
#print axioms conductorExponentAt_checkpoint

end SparkInterval.Tests.TMajorCheckpointLayout
