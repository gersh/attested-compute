/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PlattLemmaC3

set_option autoImplicit false

namespace SparkInterval.Tests.PlattLemmaC3Test

open SparkInterval.Zeta.PlattLemmaC3

example : sourceA * sourceSpacing = 1 := sourceA_mul_spacing

example : 2 * sourceNs = 140 := source_sample_count

example : sourceDecimalBinary64 < sourceInterpolationBudget :=
  sourceDecimalBinary64_lt_budget

example : sourceInterpolationBudget ≤ correctedInterpolationBinary64 :=
  sourceInterpolationBudget_le_correctedBinary64

example (x : ℝ) (hx : x ≠ 0) :
    |normalizedSinc x| ≤ 1 / (Real.pi * |x|) :=
  abs_normalizedSinc_le_inv hx

example {x Ns : ℝ} (hNs : 0 < Ns) (hdistance : Ns ≤ |x|) :
    |normalizedSinc x| ≤ sourceA / (Real.pi * Ns) :=
  abs_normalizedSinc_le_paper_factor hNs hdistance sourceA_ge_one

example {W : ℝ → ℝ} {t0 value full finite weissBound : ℝ}
    (hc3 : HoldsAt W t0 sourceA sourceH sourceNs)
    (hweiss : |value - full| ≤ weissBound)
    (hdecomposition :
      full = finite +
        (∑' n : ℤ, tailTerm W t0 sourceA sourceNs n))
    (hbudget :
      weissBound + publishedTailBound t0 sourceA sourceH sourceNs ≤
        (sourceInterpolationBudget : ℝ)) :
    |value - finite| ≤ (sourceInterpolationBudget : ℝ) :=
  interpolation_error_le_sourceBudget hc3 hweiss hdecomposition hbudget

#print axioms abs_normalizedSinc_le_inv
#print axioms abs_normalizedSinc_le_paper_factor
#print axioms sourceInterpolationBudget_le_correctedBinary64
#print axioms holdsAt_of_summable_majorant
#print axioms interpolation_error_le_sourceBudget

end SparkInterval.Tests.PlattLemmaC3Test
