/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.WindowedRadix2

set_option autoImplicit false

namespace SparkInterval.Tests.WindowedRadix2Test

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Zeta.WindowedRadix2

example : conjugateDisk (⟨3, 4, 5⟩ : ComplexDisk) = ⟨3, -4, 5⟩ := rfl

example {logLength : Nat} (source : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    negativeDFT source frequency =
      starRingEnd ℂ (positiveDFT (conjugateExactState source) frequency) :=
  negativeDFT_eq_conjugate_positiveDFT source frequency

end SparkInterval.Tests.WindowedRadix2Test
