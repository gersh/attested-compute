/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.FixedPhase

set_option autoImplicit false

namespace SparkInterval.Tests.FixedPhaseTest

open SparkInterval.Zeta.FixedPhase

example {alpha q height : ℝ} (hheight : 0 ≤ height)
    (hnearest : |alpha * q192Scale - q| ≤ 1 / 2) :
    |Real.sin (2 * Real.pi * height * alpha) -
        Real.sin (2 * Real.pi * height * (q / q192Scale))| ≤
      Real.pi * height / q192Scale :=
  sin_fixedPoint_error q192Scale_pos hheight hnearest

end SparkInterval.Tests.FixedPhaseTest
