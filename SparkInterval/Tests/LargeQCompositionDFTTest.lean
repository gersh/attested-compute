/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.LargeQCompositionDFT

set_option autoImplicit false

namespace SparkInterval.Tests.LargeQCompositionDFTTest

open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.LargeQCompositionDFT

example {logLength : Nat}
    (factor : ℂ) (taylor recovery : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    positiveDFT (composeState factor taylor recovery) frequency =
      factor * positiveDFT taylor frequency +
        positiveDFT recovery frequency :=
  positiveDFT_compose factor taylor recovery frequency

example {logLength : Nat}
    (factor : ℂ) (hfactor : factor ≠ 0)
    (taylor recovery : ExactState logLength)
    (frequency : Fin (2 ^ logLength)) :
    positiveDFT (composeState factor taylor recovery) frequency =
      factor *
        positiveDFT (addState taylor (scaleState factor⁻¹ recovery))
          frequency :=
  positiveDFT_compose_as_deferred factor hfactor taylor recovery frequency

#print axioms
  SparkInterval.Dirichlet.LargeQCompositionDFT.positiveDFT_compose
#print axioms
  SparkInterval.Dirichlet.LargeQCompositionDFT.positiveDFT_compose_as_deferred
#print axioms
  SparkInterval.Dirichlet.LargeQCompositionDFT.naive_deferred_counterexample

end SparkInterval.Tests.LargeQCompositionDFTTest
