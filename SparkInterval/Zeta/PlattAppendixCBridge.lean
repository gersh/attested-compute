/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PlattLemmaC3
import SparkInterval.Zeta.SincInterpolationCertificate

/-!
# Appendix C realization for the finite sinc certificate

`SincInterpolationCertificate` checks the 140 retained terms and asks for one
total bound between the true target value and that finite sum.  Appendix C of
Platt's paper obtains that total bound in two stages: the Weiss/non-bandlimited
error (Lemma C.1) and the omitted infinite-sum tail (corrected Lemma C.3).

This module proves the exact handoff.  It is separate from the finite checker
so the latter remains reusable, while a caller can no longer accidentally
present C.3 alone as the whole `Realization.totalInterpolationError`
obligation.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.PlattAppendixCBridge

/-- The two independently defined exact rational radii coincide. -/
theorem sourceErrorBudget_eq :
    SincInterpolationCertificate.sourceInterpolationError =
      PlattLemmaC3.sourceInterpolationBudget := by
  norm_num [SincInterpolationCertificate.sourceInterpolationError,
    PlattLemmaC3.sourceInterpolationBudget]

/-- Construct the finite checker's analytic realization from separate
Appendix C.1 and corrected-C.3 evidence.

`full` is the infinite sinc series.  `hweiss` controls the true-value to
infinite-series discrepancy, while `hdecomposition` identifies the difference
between `full` and the checked 140-term fold with the corrected C.3 tail.
-/
theorem realization_of_appendixC
    (certificate : SincInterpolationCertificate.Certificate)
    (function W : ℝ → ℝ)
    (hcheck : certificate.check = true)
    (hsample : ∀ row ∈ certificate.rows,
      row.sample.ContainsReal (function (certificate.sampleOrdinate row)))
    (hgaussian : ∀ row ∈ certificate.rows,
      row.gaussian.ContainsReal
        (SincInterpolationCertificate.gaussian (row.distance : ℝ)
          (certificate.gaussianH : ℝ)))
    (hsinc : ∀ row ∈ certificate.rows,
      row.sinc.ContainsReal
        (SincInterpolationCertificate.normalizedSinc (row.distance : ℝ)
          (certificate.spacing : ℝ)))
    {full weissBound : ℝ}
    (hc3 : PlattLemmaC3.HoldsAt W certificate.queryOrdinate
      PlattLemmaC3.sourceA PlattLemmaC3.sourceH PlattLemmaC3.sourceNs)
    (hweiss : |function certificate.queryOrdinate - full| ≤ weissBound)
    (hdecomposition :
      full = certificate.exactSum function certificate.rows +
        (∑' n : ℤ, PlattLemmaC3.tailTerm W certificate.queryOrdinate
          PlattLemmaC3.sourceA PlattLemmaC3.sourceNs n))
    (hbudget :
      weissBound + PlattLemmaC3.publishedTailBound certificate.queryOrdinate
          PlattLemmaC3.sourceA PlattLemmaC3.sourceH PlattLemmaC3.sourceNs ≤
        (PlattLemmaC3.sourceInterpolationBudget : ℝ)) :
    certificate.Realization function := by
  have hvalid := SincInterpolationCertificate.Certificate.check_eq_true.mp hcheck
  refine
    { sample := hsample
      gaussian := hgaussian
      sinc := hsinc
      totalInterpolationError := ?_ }
  have htotal :
      |function certificate.queryOrdinate -
          certificate.exactSum function certificate.rows| ≤
        (PlattLemmaC3.sourceInterpolationBudget : ℝ) :=
    PlattLemmaC3.interpolation_error_le_sourceBudget
      hc3 hweiss hdecomposition hbudget
  rw [hvalid.2.2.1, sourceErrorBudget_eq]
  exact htotal

end SparkInterval.Zeta.PlattAppendixCBridge
