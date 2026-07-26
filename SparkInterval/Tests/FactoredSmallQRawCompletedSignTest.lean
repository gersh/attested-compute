/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQRawCompletedSign

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign
open SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign

abbrev TailInflationCertificate :=
  SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate

abbrev RawTailInflationCertificate :=
  SparkInterval.Dirichlet.FactoredSmallQRawPostprocess.RawTailInflationCertificate

def pointDisk (re im : ℚ) : ComplexDisk := ⟨re, im, 0⟩
def diskSixHalf : ComplexDisk := ⟨6, 0, 1 / 2⟩
def diskNegativeSixHalf : ComplexDisk := ⟨-6, 0, 1 / 2⟩

def rawPoint (reBits imBits : Nat) : ComplexDisk.Raw :=
  ⟨reBits, imBits, 0⟩

def rawTwo : ComplexDisk.Raw :=
  rawPoint 0x4000000000000000 0

def rawThree : ComplexDisk.Raw :=
  rawPoint 0x4008000000000000 0

def rawNegativeThree : ComplexDisk.Raw :=
  rawPoint 0xc008000000000000 0

def rawOne : ComplexDisk.Raw :=
  rawPoint 0x3ff0000000000000 0

def rawSix : ComplexDisk.Raw :=
  rawPoint 0x4018000000000000 0

def rawNegativeSix : ComplexDisk.Raw :=
  rawPoint 0xc018000000000000 0

def rawSixHalf : ComplexDisk.Raw :=
  ⟨0x4018000000000000, 0, 0x3fe0000000000000⟩

def rawNegativeSixHalf : ComplexDisk.Raw :=
  ⟨0xc018000000000000, 0, 0x3fe0000000000000⟩

def rawScaleProduct : ComplexDisk.RawMulCertificate := {
  left := rawTwo
  right := rawThree
  output := rawSix
  centerErrorBoundBits := 0
  leftCenterNormBoundBits := 0x4000000000000000
  rightCenterNormBoundBits := 0x4008000000000000
}

def typedScaleProduct : ComplexDisk.MulCertificate := {
  left := pointDisk 2 0
  right := pointDisk 3 0
  output := pointDisk 6 0
  centerErrorBound := 0
  leftCenterNormBound := 2
  rightCenterNormBound := 3
}

def rawTail : RawTailInflationCertificate := {
  input := rawSix
  tailBoundBits := 0x3fe0000000000000
  output := rawSixHalf
}

def typedTail : TailInflationCertificate := {
  input := pointDisk 6 0
  tailBound := 1 / 2
  output := diskSixHalf
}

def rawUntiltProduct : ComplexDisk.RawMulCertificate := {
  left := rawSixHalf
  right := rawOne
  output := rawSixHalf
  centerErrorBoundBits := 0
  leftCenterNormBoundBits := 0x4018000000000000
  rightCenterNormBoundBits := 0x3ff0000000000000
}

def typedUntiltProduct : ComplexDisk.MulCertificate := {
  left := diskSixHalf
  right := pointDisk 1 0
  output := diskSixHalf
  centerErrorBound := 0
  leftCenterNormBound := 6
  rightCenterNormBound := 1
}

def rawSample : RawCertificate := {
  scaleTimesFourier := rawScaleProduct
  timeTailInflation := rawTail
  untiltTimesPeriodized := rawUntiltProduct
  signCode := 1
}

def typedSample : Certificate := {
  scaleTimesFourier := typedScaleProduct
  timeTailInflation := typedTail
  untiltTimesPeriodized := typedUntiltProduct
  sign := .positive
}

theorem rawTwo_decode : rawTwo.decode = some (pointDisk 2 0) := by
  norm_num [rawTwo, rawPoint, pointDisk, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem rawThree_decode : rawThree.decode = some (pointDisk 3 0) := by
  norm_num [rawThree, rawPoint, pointDisk, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem rawOne_decode : rawOne.decode = some (pointDisk 1 0) := by
  norm_num [rawOne, rawPoint, pointDisk, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem rawScaleProduct_decode :
    rawScaleProduct.decode = some typedScaleProduct := by
  norm_num [rawScaleProduct, typedScaleProduct, rawTwo, rawThree, rawSix,
    rawPoint, pointDisk, ComplexDisk.RawMulCertificate.decode,
    ComplexDisk.Raw.decode, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem rawTail_decode : rawTail.decode = some typedTail := by
  norm_num [rawTail, typedTail, rawSix, rawSixHalf, rawPoint, pointDisk,
    diskSixHalf,
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocess.RawTailInflationCertificate.decode,
    ComplexDisk.Raw.decode, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem rawUntiltProduct_decode :
    rawUntiltProduct.decode = some typedUntiltProduct := by
  norm_num [rawUntiltProduct, typedUntiltProduct, rawSixHalf, rawOne,
    rawPoint, pointDisk, diskSixHalf,
    ComplexDisk.RawMulCertificate.decode, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem rawSample_decode : rawSample.decode = some typedSample := by
  simp [rawSample, typedSample, RawCertificate.decode,
    rawScaleProduct_decode, rawTail_decode, rawUntiltProduct_decode,
    decodeStrictSign]

theorem typedSample_check :
    typedSample.check (pointDisk 2 0) = true := by
  norm_num [typedSample, typedScaleProduct, typedTail,
    typedUntiltProduct, pointDisk, diskSixHalf,
    Certificate.check, Certificate.Accepted, Certificate.output,
    StrictSign.CertifiedBy,
    ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.check,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

theorem rawSample_check : rawSample.check rawTwo = true := by
  rw [RawCertificate.check]
  have hattached :
      decide (rawSample.scaleTimesFourier.left = rawTwo) = true := by
    rfl
  rw [hattached]
  simp only [Bool.true_and]
  rw [rawTwo_decode, rawSample_decode]
  exact typedSample_check

theorem point_contains (value : ℚ) :
    (pointDisk value 0).ContainsComplex (value : ℂ) := by
  unfold ComplexDisk.ContainsComplex
  have hcenter : (pointDisk value 0).center = (value : ℂ) := by
    apply Complex.ext <;>
      norm_num [pointDisk, ComplexDisk.center]
  rw [hcenter]
  norm_num [pointDisk]

theorem rawHalf_decode :
    Binary64.decodeFinite 0x3fe0000000000000 = some (1 / 2 : ℚ) := by
  norm_num [Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem quarter_tail : ‖(1 / 4 : ℂ)‖ ≤ ((1 / 2 : ℚ) : ℝ) := by
  norm_num

noncomputable def sourceB : ℝ := 2 * Real.pi / 3

theorem source_guards : RawCertificate.SourceGuards sourceB 0 0 := by
  norm_num [RawCertificate.SourceGuards, sourceB]
  positivity

theorem source_scale_eq_three : sourceScale sourceB = 3 := by
  unfold sourceScale sourceB
  have hpi : Real.pi ≠ 0 := ne_of_gt Real.pi_pos
  field_simp

theorem source_scale_contains :
    (pointDisk 3 0).ContainsComplex (sourceScale sourceB : ℂ) := by
  rw [source_scale_eq_three]
  exact point_contains 3

theorem source_untilt_contains :
    (pointDisk 1 0).ContainsComplex (sourceUntilt 0 0 : ℂ) := by
  simpa [sourceUntilt] using (point_contains 1)

theorem source_completed_real :
    (sourceCompletedValue (2 : ℂ) sourceB 0 0 (1 / 4 : ℂ)).im = 0 := by
  change
    (completedValue (2 : ℂ) (sourceScale sourceB) (1 / 4 : ℂ)
      (sourceUntilt 0 0)).im = 0
  rw [source_scale_eq_three]
  norm_num [completedValue, sourceUntilt]

theorem raw_sample_source_sign :
    ∃ certificate : Certificate,
      rawSample.scaleTimesFourier.left = rawTwo ∧
      rawSample.decode = some certificate ∧
      decodeStrictSign rawSample.signCode = some certificate.sign ∧
      rawSample.untiltTimesPeriodized.output.decode = some certificate.output ∧
      RawCertificate.SourceGuards sourceB 0 0 ∧
      certificate.sign.Holds
        (sourceCompletedValue (2 : ℂ) sourceB 0 0 (1 / 4 : ℂ)).re := by
  exact RawCertificate.accepted_source_sign source_guards rawSample_check
    rawTwo_decode (point_contains 2) rawThree_decode source_scale_contains
    rawHalf_decode quarter_tail rawOne_decode source_untilt_contains
    source_completed_real

/-! ## Fail-closed adversarial fixtures -/

def invalidSignCode : RawCertificate := { rawSample with signCode := 2 }

theorem invalid_sign_code_fails_closed :
    invalidSignCode.check rawTwo = false := by
  rw [RawCertificate.check]
  have hattached :
      decide (invalidSignCode.scaleTimesFourier.left = rawTwo) = true := by
    rfl
  rw [hattached]
  simp only [Bool.true_and]
  rw [rawTwo_decode]
  have hdecode : invalidSignCode.decode = none := by
    simp [invalidSignCode, rawSample, RawCertificate.decode,
      rawScaleProduct_decode, rawTail_decode, rawUntiltProduct_decode,
      decodeStrictSign]
  rw [hdecode]

def zeroSignCode : RawCertificate := { rawSample with signCode := 0 }

theorem zero_sign_code_fails_closed :
    zeroSignCode.check rawTwo = false := by
  rw [RawCertificate.check]
  have hattached :
      decide (zeroSignCode.scaleTimesFourier.left = rawTwo) = true := by
    rfl
  rw [hattached]
  simp only [Bool.true_and]
  rw [rawTwo_decode]
  have hdecode : zeroSignCode.decode = none := by
    simp [zeroSignCode, rawSample, RawCertificate.decode,
      rawScaleProduct_decode, rawTail_decode, rawUntiltProduct_decode,
      decodeStrictSign]
  rw [hdecode]

def wrongSign : RawCertificate := { rawSample with signCode := -1 }

def wrongSignTyped : Certificate := { typedSample with sign := .negative }

theorem wrongSign_decode : wrongSign.decode = some wrongSignTyped := by
  simp [wrongSign, wrongSignTyped, rawSample, typedSample,
    RawCertificate.decode, rawScaleProduct_decode, rawTail_decode,
    rawUntiltProduct_decode, decodeStrictSign]

theorem wrong_sign_fails_closed : wrongSign.check rawTwo = false := by
  rw [RawCertificate.check]
  have hattached :
      decide (wrongSign.scaleTimesFourier.left = rawTwo) = true := by
    rfl
  rw [hattached]
  simp only [Bool.true_and]
  rw [rawTwo_decode, wrongSign_decode]
  norm_num [wrongSignTyped, typedSample, typedScaleProduct, typedTail,
    typedUntiltProduct, pointDisk, diskSixHalf, Certificate.check,
    Certificate.Accepted, Certificate.output, StrictSign.CertifiedBy,
    ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.check,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

theorem detached_fourier_fails_closed :
    rawSample.check rawThree = false := by
  norm_num [RawCertificate.check, rawSample, rawScaleProduct, rawTwo,
    rawThree, rawPoint]

/-- Signed zero has the same exact rational decode, but a different literal
wire spelling.  The attachment check rejects that alias before arithmetic
decoding, leaving canonical-zero enforcement to the byte parser. -/
def rawTwoNegativeZeroImaginary : ComplexDisk.Raw :=
  ⟨0x4000000000000000, 0x8000000000000000, 0⟩

theorem negative_zero_alias_decodes_equal :
    rawTwoNegativeZeroImaginary.decode = some (pointDisk 2 0) := by
  norm_num [rawTwoNegativeZeroImaginary, pointDisk,
    ComplexDisk.Raw.decode, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem negative_zero_alias_fails_attachment :
    rawSample.check rawTwoNegativeZeroImaginary = false := by
  norm_num [RawCertificate.check, rawSample, rawScaleProduct, rawTwo,
    rawTwoNegativeZeroImaginary, rawPoint]

def rawInfinity : ComplexDisk.Raw :=
  ⟨0x7ff0000000000000, 0, 0⟩

def nonfiniteScaleProduct : ComplexDisk.RawMulCertificate :=
  { rawScaleProduct with right := rawInfinity }

def nonfiniteFactor : RawCertificate :=
  { rawSample with scaleTimesFourier := nonfiniteScaleProduct }

theorem nonfinite_factor_fails_closed :
    nonfiniteFactor.check rawTwo = false := by
  norm_num [RawCertificate.check, RawCertificate.decode, nonfiniteFactor,
    nonfiniteScaleProduct, rawSample, rawScaleProduct, rawInfinity,
    rawTwo, rawPoint, ComplexDisk.RawMulCertificate.decode,
    ComplexDisk.Raw.decode, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes]

def negativeRadiusDisk : ComplexDisk.Raw :=
  ⟨0x4018000000000000, 0, 0xbfe0000000000000⟩

def negativeRadiusUntilt : ComplexDisk.RawMulCertificate :=
  { rawUntiltProduct with output := negativeRadiusDisk }

def negativeRadius : RawCertificate :=
  { rawSample with untiltTimesPeriodized := negativeRadiusUntilt }

theorem negative_radius_fails_closed :
    negativeRadius.check rawTwo = false := by
  norm_num [RawCertificate.check, RawCertificate.decode, negativeRadius,
    negativeRadiusUntilt, rawSample, rawUntiltProduct,
    negativeRadiusDisk, rawScaleProduct, rawTail, rawTwo, rawThree,
    rawSix, rawSixHalf, rawOne, rawPoint,
    ComplexDisk.RawMulCertificate.decode,
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocess.RawTailInflationCertificate.decode,
    ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold,
    Certificate.check, Certificate.Accepted, Certificate.output,
    StrictSign.CertifiedBy, ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

def rawNegativeScaleProduct : ComplexDisk.RawMulCertificate := {
  left := rawTwo
  right := rawNegativeThree
  output := rawNegativeSix
  centerErrorBoundBits := 0
  leftCenterNormBoundBits := 0x4000000000000000
  rightCenterNormBoundBits := 0x4008000000000000
}

def rawNegativeTail : RawTailInflationCertificate := {
  input := rawNegativeSix
  tailBoundBits := 0x3fe0000000000000
  output := rawNegativeSixHalf
}

def rawNegativeUntilt : ComplexDisk.RawMulCertificate := {
  left := rawNegativeSixHalf
  right := rawOne
  output := rawNegativeSixHalf
  centerErrorBoundBits := 0
  leftCenterNormBoundBits := 0x4018000000000000
  rightCenterNormBoundBits := 0x3ff0000000000000
}

def nonpositiveFactor : RawCertificate := {
  scaleTimesFourier := rawNegativeScaleProduct
  timeTailInflation := rawNegativeTail
  untiltTimesPeriodized := rawNegativeUntilt
  signCode := -1
}

theorem nonpositive_factor_fails_closed :
    nonpositiveFactor.check rawTwo = false := by
  norm_num [RawCertificate.check, RawCertificate.decode,
    nonpositiveFactor, rawNegativeScaleProduct, rawNegativeTail,
    rawNegativeUntilt, rawTwo, rawNegativeThree, rawNegativeSix,
    rawNegativeSixHalf, rawOne, rawPoint,
    ComplexDisk.RawMulCertificate.decode,
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocess.RawTailInflationCertificate.decode,
    ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold,
    Certificate.check, Certificate.Accepted, Certificate.output,
    StrictSign.CertifiedBy, ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.check,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq,
    decodeStrictSign]

#print axioms rawMul_disk_decodes
#print axioms RawCertificate.checker_sound
#print axioms RawCertificate.accepted_source_sign
#print axioms raw_sample_source_sign
#print axioms invalid_sign_code_fails_closed
#print axioms zero_sign_code_fails_closed
#print axioms wrong_sign_fails_closed
#print axioms detached_fourier_fails_closed
#print axioms negative_zero_alias_decodes_equal
#print axioms negative_zero_alias_fails_attachment
#print axioms nonfinite_factor_fails_closed
#print axioms negative_radius_fails_closed
#print axioms nonpositive_factor_fails_closed

end SparkInterval.Tests.FactoredSmallQRawCompletedSign
