/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQCompletedSign

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQCompletedSign

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign

abbrev TailInflationCertificate :=
  SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate

def pointDisk (re im : ℚ) : ComplexDisk := ⟨re, im, 0⟩
def diskSixHalf : ComplexDisk := ⟨6, 0, 1 / 2⟩
def diskTwelveOne : ComplexDisk := ⟨12, 0, 1⟩

def scaleProduct : ComplexDisk.MulCertificate := {
  left := pointDisk 2 0
  right := pointDisk 3 0
  output := pointDisk 6 0
  centerErrorBound := 0
  leftCenterNormBound := 2
  rightCenterNormBound := 3
}

def timeTail : TailInflationCertificate := {
  input := pointDisk 6 0
  tailBound := 1 / 2
  output := diskSixHalf
}

def untiltProduct : ComplexDisk.MulCertificate := {
  left := diskSixHalf
  right := pointDisk 2 0
  output := diskTwelveOne
  centerErrorBound := 0
  leftCenterNormBound := 6
  rightCenterNormBound := 2
}

def sample : SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate := {
  scaleTimesFourier := scaleProduct
  timeTailInflation := timeTail
  untiltTimesPeriodized := untiltProduct
  sign := .positive
}

theorem point_contains (value : ℚ) :
    (pointDisk value 0).ContainsComplex (value : ℂ) := by
  unfold ComplexDisk.ContainsComplex
  have hcenter : (pointDisk value 0).center = (value : ℂ) := by
    apply Complex.ext <;>
      norm_num [pointDisk, ComplexDisk.center]
  rw [hcenter]
  norm_num [pointDisk]

theorem sample_check : sample.check (pointDisk 2 0) = true := by
  norm_num [sample,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.Accepted,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.output,
    scaleProduct, timeTail, untiltProduct, pointDisk,
    diskSixHalf, diskTwelveOne, StrictSign.CertifiedBy,
    ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.check,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

theorem quarter_tail : ‖(1 / 4 : ℂ)‖ ≤ ((1 / 2 : ℚ) : ℝ) := by
  norm_num

theorem completed_is_real :
    (completedValue (2 : ℂ) 3 (1 / 4 : ℂ) 2).im = 0 := by
  norm_num [completedValue]

theorem sample_positive :
    StrictSign.positive.Holds
      (completedValue (2 : ℂ) 3 (1 / 4 : ℂ) 2).re := by
  exact SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.accepted_sign
    sample_check (point_contains 2)
    (point_contains 3) quarter_tail (point_contains 2) completed_is_real

theorem sample_factors_positive : 0 < (3 : ℝ) ∧ 0 < (2 : ℝ) := by
  exact SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.accepted_factors_positive
    sample_check (point_contains 3) (point_contains 2)

/-- A negative "radius" cannot certify a sign merely because it makes the
one-sided inequality syntactically easy. -/
def negativeRadiusDisk : ComplexDisk := ⟨1, 0, -1⟩

theorem negative_radius_sign_fails_closed :
    ¬ StrictSign.positive.CertifiedBy negativeRadiusDisk := by
  norm_num [StrictSign.CertifiedBy, negativeRadiusDisk]

/-! A satisfiable source-shaped fixture: `b = 2*pi/3` gives scale `3`,
`eta = 0` gives untilt `1`, and the completed value is the positive real
number `25/4`. -/

def sourceUntiltProduct : ComplexDisk.MulCertificate := {
  left := diskSixHalf
  right := pointDisk 1 0
  output := diskSixHalf
  centerErrorBound := 0
  leftCenterNormBound := 6
  rightCenterNormBound := 1
}

def sourceSample :
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate := {
  scaleTimesFourier := scaleProduct
  timeTailInflation := timeTail
  untiltTimesPeriodized := sourceUntiltProduct
  sign := .positive
}

noncomputable def sourceB : ℝ := 2 * Real.pi / 3
def sourceEta : ℝ := 0
def sourceT : ℝ := 1

theorem source_b_pos : 0 < sourceB := by
  unfold sourceB
  positivity

theorem source_scale_eq : sourceScale sourceB = 3 := by
  unfold sourceScale sourceB
  field_simp [ne_of_gt Real.pi_pos]

theorem source_untilt_eq : sourceUntilt sourceEta sourceT = 1 := by
  simp [sourceUntilt, sourceEta, sourceT]

theorem source_sample_check : sourceSample.check (pointDisk 2 0) = true := by
  norm_num [sourceSample,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.Accepted,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.output,
    scaleProduct, timeTail, sourceUntiltProduct, pointDisk,
    diskSixHalf, StrictSign.CertifiedBy,
    ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.check,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

theorem source_completed_real :
    (sourceCompletedValue (2 : ℂ) sourceB sourceEta sourceT
      (1 / 4 : ℂ)).im = 0 := by
  unfold sourceCompletedValue
  rw [show sourceScale sourceB = 3 from source_scale_eq,
    show sourceUntilt sourceEta sourceT = 1 from source_untilt_eq]
  norm_num [completedValue]

theorem source_sample_positive :
    StrictSign.positive.Holds
      (sourceCompletedValue (2 : ℂ) sourceB sourceEta sourceT
        (1 / 4 : ℂ)).re := by
  exact (SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.accepted_source_sign
      source_b_pos source_sample_check (point_contains 2)
      (by
        change (pointDisk 3 0).ContainsComplex (sourceScale sourceB : ℂ)
        rw [source_scale_eq]
        exact point_contains 3)
      quarter_tail
      (by
        change (pointDisk 1 0).ContainsComplex
          (sourceUntilt sourceEta sourceT : ℂ)
        rw [source_untilt_eq]
        convert point_contains 1 using 1
        norm_num)
      source_completed_real).2

/- A pair of negative factors would leave the final sign unchanged, so all
disk arithmetic below is otherwise consistent.  It must nevertheless fail
because the source algorithm's scale and untilt factors are positive. -/
def diskNegativeSixHalf : ComplexDisk := ⟨-6, 0, 1 / 2⟩

def negativeScaleProduct : ComplexDisk.MulCertificate := {
  left := pointDisk 2 0
  right := pointDisk (-3) 0
  output := pointDisk (-6) 0
  centerErrorBound := 0
  leftCenterNormBound := 2
  rightCenterNormBound := 3
}

def negativeTimeTail : TailInflationCertificate := {
  input := pointDisk (-6) 0
  tailBound := 1 / 2
  output := diskNegativeSixHalf
}

def negativeUntiltProduct : ComplexDisk.MulCertificate := {
  left := diskNegativeSixHalf
  right := pointDisk (-2) 0
  output := diskTwelveOne
  centerErrorBound := 0
  leftCenterNormBound := 6
  rightCenterNormBound := 2
}

def nonpositiveFactors :
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate := {
  scaleTimesFourier := negativeScaleProduct
  timeTailInflation := negativeTimeTail
  untiltTimesPeriodized := negativeUntiltProduct
  sign := .positive
}

theorem nonpositive_factors_fail_closed :
    nonpositiveFactors.check (pointDisk 2 0) = false := by
  norm_num [nonpositiveFactors,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.Accepted,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.output,
    negativeScaleProduct, negativeTimeTail, negativeUntiltProduct,
    pointDisk, diskNegativeSixHalf, diskTwelveOne, StrictSign.CertifiedBy,
    ComplexDisk.MulCertificate.check, ComplexDisk.MulCertificate.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.check,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

def wrongSign :
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate :=
  { sample with sign := .negative }

theorem wrong_sign_fails_closed :
    wrongSign.check (pointDisk 2 0) = false := by
  norm_num [wrongSign, sample,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.Accepted,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.output,
    scaleProduct, timeTail, untiltProduct, pointDisk,
    diskSixHalf, diskTwelveOne, StrictSign.CertifiedBy,
    ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.check,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

#print axioms StrictSign.holds_of_contains_real
#print axioms SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.output_contains_completedValue
#print axioms SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.accepted_sign
#print axioms SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.accepted_source_sign
#print axioms SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.accepted_factors_positive
#print axioms sample_positive
#print axioms sample_factors_positive
#print axioms negative_radius_sign_fails_closed
#print axioms source_sample_positive
#print axioms nonpositive_factors_fail_closed
#print axioms wrong_sign_fails_closed

end SparkInterval.Tests.FactoredSmallQCompletedSign
