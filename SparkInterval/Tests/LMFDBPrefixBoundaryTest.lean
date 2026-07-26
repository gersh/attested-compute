/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.LMFDBPrefixBoundary

namespace SparkInterval.Tests.LMFDBPrefixBoundaryTest

open SparkInterval.Zeta.LMFDBPrefixBoundary

example : publicEvidence.check = true := publicEvidence_check

example : 32_130_155_617 + 2_698 = 32_130_158_315 :=
  public_count_equation

example :
    publicEvidence.predecessorMidpointScaled + 1 <
        publicEvidence.targetHeight * scale ∧
      publicEvidence.targetHeight * scale + 1 ≤
        publicEvidence.successorMidpointScaled :=
  public_target_separated

#print axioms BoundaryEvidence.check_sound
#print axioms BoundaryEvidence.checked_cut
#print axioms publicEvidence_check
#print axioms public_target_separated

end SparkInterval.Tests.LMFDBPrefixBoundaryTest
