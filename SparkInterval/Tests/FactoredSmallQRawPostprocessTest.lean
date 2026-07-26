/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawPostprocess
import SparkInterval.Tests.FactoredSmallQRawGaussianSumTest

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQRawPostprocess

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQGaussianSum
open SparkInterval.Dirichlet.FactoredSmallQRawGaussianSum
open SparkInterval.Dirichlet.FactoredSmallQPostprocess
open SparkInterval.Dirichlet.FactoredSmallQRawPostprocess

def pointValue (re im : ℚ) : ℂ :=
  ⟨(re : ℝ), (im : ℝ)⟩

def pointDisk (re im : ℚ) : ComplexDisk :=
  ⟨re, im, 0⟩

theorem pointDisk_contains (re im : ℚ) :
    (pointDisk re im).ContainsComplex (pointValue re im) := by
  unfold ComplexDisk.ContainsComplex
  have hcenter : (pointDisk re im).center = pointValue re im := by
    apply Complex.ext <;>
      norm_num [pointDisk, pointValue, ComplexDisk.center]
  rw [hcenter]
  simp [pointDisk]

def rawOneOne : ComplexDisk.Raw :=
  ⟨0x3ff0000000000000, 0x3ff0000000000000,
    0x0000000000000000⟩

def rawEightySixEightySix : ComplexDisk.Raw :=
  ⟨0x4055800000000000, 0x4055800000000000,
    0x0000000000000000⟩

def rawEightySixNegativeEightySix : ComplexDisk.Raw :=
  ⟨0x4055800000000000, 0xc055800000000000,
    0x0000000000000000⟩

def rawEightySixNegativeEightySixHalf : ComplexDisk.Raw :=
  ⟨0x4055800000000000, 0xc055800000000000,
    0x3fe0000000000000⟩

def rawSixSix : ComplexDisk.Raw :=
  ⟨0x4018000000000000, 0x4018000000000000,
    0x0000000000000000⟩

def rawPrefactorTimesSum : ComplexDisk.RawMulCertificate := {
  left := rawOneOne
  right := SparkInterval.Tests.FactoredSmallQRawGaussianSum.rawEightySix
  output := rawEightySixEightySix
  centerErrorBoundBits := 0x0000000000000000
  leftCenterNormBoundBits := 0x4000000000000000
  rightCenterNormBoundBits := 0x4055800000000000
}

def typedPrefactorTimesSum : ComplexDisk.MulCertificate := {
  left := pointDisk 1 1
  right := pointDisk 86 0
  output := pointDisk 86 86
  centerErrorBound := 0
  leftCenterNormBound := 2
  rightCenterNormBound := 86
}

def rawTail : RawTailInflationCertificate := {
  input := rawEightySixNegativeEightySix
  tailBoundBits := 0x3fe0000000000000
  output := rawEightySixNegativeEightySixHalf
}

def typedTail : TailInflationCertificate := {
  input := pointDisk 86 (-86)
  tailBound := 1 / 2
  output := ⟨86, -86, 1 / 2⟩
}

def rawSample : RawCertificate := {
  finiteSum := SparkInterval.Tests.FactoredSmallQRawGaussianSum.rawSample
  prefactor := rawOneOne
  prefactorTimesSum := rawPrefactorTimesSum
  negativeFrequency := true
  tailInflation := rawTail
}

def typedSample : Certificate := {
  finiteSum := SparkInterval.Tests.FactoredSmallQRawGaussianSum.typedSample
  prefactor := pointDisk 1 1
  prefactorTimesSum := typedPrefactorTimesSum
  negativeFrequency := true
  tailInflation := typedTail
}

theorem rawOneOne_decode :
    rawOneOne.decode = some (pointDisk 1 1) := by
  norm_num [rawOneOne, pointDisk, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem rawPrefactorTimesSum_decode :
    rawPrefactorTimesSum.decode = some typedPrefactorTimesSum := by
  norm_num [rawPrefactorTimesSum, typedPrefactorTimesSum, rawOneOne,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.rawEightySix, rawEightySixEightySix, pointDisk,
    ComplexDisk.RawMulCertificate.decode, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem rawTail_decode : rawTail.decode = some typedTail := by
  norm_num [rawTail, typedTail, rawEightySixNegativeEightySix,
    rawEightySixNegativeEightySixHalf, pointDisk,
    RawTailInflationCertificate.decode, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem rawSample_decode : rawSample.decode = some typedSample := by
  simp [rawSample, typedSample, RawCertificate.decode,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.rawSample_decode, rawOneOne_decode,
    rawPrefactorTimesSum_decode, rawTail_decode]

theorem typedSample_check : typedSample.check 2 = true := by
  norm_num [typedSample, typedPrefactorTimesSum, typedTail, pointDisk,
    Certificate.check, Certificate.Accepted,
    TailInflationCertificate.check, TailInflationCertificate.WellFormed,
    applyFrequencySign, conjugateDisk,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.typedSample, SparkInterval.Tests.FactoredSmallQRawGaussianSum.typedRowOne,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.typedRowTwo, SparkInterval.Tests.FactoredSmallQRawGaussianSum.typedAdvance, SparkInterval.Tests.FactoredSmallQRawGaussianSum.typedSeed,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.exactMul, SparkInterval.Tests.FactoredSmallQRawGaussianSum.exactAdd, SparkInterval.Tests.FactoredSmallQRawGaussianSum.realDisk,
    zeroDisk, ordinalDisk, SumTraceCertificate.check,
    SumTraceCertificate.initialState, SumTraceCertificate.output, runRows,
    checkRows, RowCertificate.checkCore, RowCertificate.CoreWellFormed,
    RowCertificate.WeightWellFormed, RowCertificate.weightedOutput,
    SparkInterval.Dirichlet.FactoredSmallQTrace.TraceCertificate.check,
    SparkInterval.Dirichlet.FactoredSmallQTrace.TraceCertificate.InitialWellFormed,
    SparkInterval.Dirichlet.FactoredSmallQTrace.TraceCertificate.initialState,
    SparkInterval.Dirichlet.FactoredSmallQTrace.Linked,
    SparkInterval.Dirichlet.FactoredSmallQTrace.checkLinked,
    SparkInterval.Dirichlet.FactoredSmallQTrace.StepCertificate.check,
    SparkInterval.Dirichlet.FactoredSmallQTrace.StepCertificate.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQTrace.StepCertificate.output,
    ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.AddCertificate.check,
    ComplexDisk.AddCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.sumCenterErrorSq,
    ComplexDisk.centerNormSq]

theorem rawSample_check : rawSample.check 2 = true := by
  rw [RawCertificate.check]
  have hbound : decide (rawSample.finiteSum.rows.length ≤ 2) = true := by
    norm_num [rawSample, SparkInterval.Tests.FactoredSmallQRawGaussianSum.rawSample]
  rw [hbound]
  simp only [Bool.true_and]
  rw [rawSample_decode]
  exact typedSample_check

theorem typed_sum_output :
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.typedSample.output =
      pointDisk 86 0 := by
  norm_num [
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.typedSample,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.typedRowOne,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.typedRowTwo,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.typedAdvance,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.typedSeed,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.exactMul,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.exactAdd,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.realDisk,
    pointDisk, SumTraceCertificate.output, runRows]

theorem rawHalf_decode :
    Binary64.decodeFinite 0x3fe0000000000000 = some (1 / 2 : ℚ) := by
  norm_num [Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem quarter_tail :
    ‖(1 / 4 : ℂ)‖ ≤ (((1 / 2 : ℚ) : ℝ)) := by
  norm_num

/-- The raw theorem preserves both source rows and the exact raw final disk,
while proving the complete arithmetic value through postprocessing. -/
theorem raw_sample_contains :
    ∃ certificate : Certificate,
      rawSample.decode = some certificate ∧
      rawSample.finiteSum.decode = some certificate.finiteSum ∧
      rawSample.tailInflation.output.decode = some certificate.output ∧
      [(3 : ℂ), (5 : ℂ)].length = rawSample.finiteSum.truncation ∧
      certificate.output.ContainsComplex
        (pointValue (345 / 4) (-86)) := by
  have h := RawCertificate.accepted_output_contains_exact_finite_sum
    (characters := [(3 : ℂ), (5 : ℂ)])
    (w := (2 : ℂ)) (prefactor := pointValue 1 1)
    (delta := (1 / 4 : ℂ))
    rawSample_check SparkInterval.Tests.FactoredSmallQRawGaussianSum.rawTwo_decode
    (SparkInterval.Tests.FactoredSmallQRawGaussianSum.realDisk_contains 2) SparkInterval.Tests.FactoredSmallQRawGaussianSum.raw_characters
    rawOneOne_decode (pointDisk_contains 1 1) rawHalf_decode quarter_tail
  rcases h with
    ⟨certificate, hdecode, hsumDecode, houtputDecode, hlength,
      hcontains⟩
  refine ⟨certificate, hdecode, hsumDecode, houtputDecode, hlength, ?_⟩
  change certificate.output.ContainsComplex
    (applyFrequencySignValue true
        (pointValue 1 1 * exactFiniteSum false (2 : ℂ)
          [(3 : ℂ), (5 : ℂ)]) + (1 / 4 : ℂ)) at hcontains
  have hexact :
      applyFrequencySignValue true
          (pointValue 1 1 * exactFiniteSum false (2 : ℂ)
            [(3 : ℂ), (5 : ℂ)]) + (1 / 4 : ℂ) =
        pointValue (345 / 4) (-86) := by
    apply Complex.ext <;>
      norm_num [applyFrequencySignValue, exactFiniteSum, exactSumFrom,
        exactTerm, pointValue, Complex.mul_re, Complex.mul_im]
  rw [hexact] at hcontains
  exact hcontains

/-! A valid postprocessing witness for the smaller sum `6` cannot be attached
to the accepted raw finite sum `86`: the typed link equation fails. -/

def rawPrefactorTimesSix : ComplexDisk.RawMulCertificate := {
  left := rawOneOne
  right := SparkInterval.Tests.FactoredSmallQRawGaussianSum.rawSix
  output := rawSixSix
  centerErrorBoundBits := 0x0000000000000000
  leftCenterNormBoundBits := 0x4000000000000000
  rightCenterNormBoundBits := 0x4018000000000000
}

def typedPrefactorTimesSix : ComplexDisk.MulCertificate := {
  left := pointDisk 1 1
  right := pointDisk 6 0
  output := pointDisk 6 6
  centerErrorBound := 0
  leftCenterNormBound := 2
  rightCenterNormBound := 6
}

def rawTailAfterSix : RawTailInflationCertificate := {
  input := ⟨0x4018000000000000, 0xc018000000000000,
    0x0000000000000000⟩
  tailBoundBits := 0x3fe0000000000000
  output := ⟨0x4018000000000000, 0xc018000000000000,
    0x3fe0000000000000⟩
}

def typedTailAfterSix : TailInflationCertificate := {
  input := pointDisk 6 (-6)
  tailBound := 1 / 2
  output := ⟨6, -6, 1 / 2⟩
}

def detachedSum : RawCertificate := {
  rawSample with
  prefactorTimesSum := rawPrefactorTimesSix
  tailInflation := rawTailAfterSix
}

def detachedTyped : Certificate := {
  typedSample with
  prefactorTimesSum := typedPrefactorTimesSix
  tailInflation := typedTailAfterSix
}

theorem rawPrefactorTimesSix_decode :
    rawPrefactorTimesSix.decode = some typedPrefactorTimesSix := by
  norm_num [rawPrefactorTimesSix, typedPrefactorTimesSix, rawOneOne,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.rawSix, rawSixSix,
    pointDisk, ComplexDisk.RawMulCertificate.decode,
    ComplexDisk.Raw.decode, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem rawTailAfterSix_decode :
    rawTailAfterSix.decode = some typedTailAfterSix := by
  norm_num [rawTailAfterSix, typedTailAfterSix, pointDisk,
    RawTailInflationCertificate.decode, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem detachedSum_decode : detachedSum.decode = some detachedTyped := by
  simp [detachedSum, detachedTyped, rawSample, typedSample,
    RawCertificate.decode,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.rawSample_decode,
    rawOneOne_decode, rawPrefactorTimesSix_decode,
    rawTailAfterSix_decode]

theorem detached_sum_fails_closed : detachedSum.check 2 = false := by
  rw [RawCertificate.check]
  have hbound : decide (detachedSum.finiteSum.rows.length ≤ 2) = true := by
    norm_num [detachedSum, rawSample,
      SparkInterval.Tests.FactoredSmallQRawGaussianSum.rawSample]
  rw [hbound]
  simp only [Bool.true_and]
  rw [detachedSum_decode]
  norm_num [detachedTyped, typedSample, Certificate.check,
    Certificate.Accepted,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.typedSample_check,
    typedPrefactorTimesSix, typedTailAfterSix, typed_sum_output,
    pointDisk, ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq,
    TailInflationCertificate.check, TailInflationCertificate.WellFormed,
    applyFrequencySign, conjugateDisk]

/-- Non-finite prefactor words fail during exact decoding. -/
def nonfinitePrefactor : RawCertificate := {
  rawSample with prefactor := SparkInterval.Tests.FactoredSmallQRawGaussianSum.rawInfinity
}

theorem nonfinite_prefactor_fails_closed :
    nonfinitePrefactor.check 2 = false := by
  norm_num [nonfinitePrefactor, rawSample, SparkInterval.Tests.FactoredSmallQRawGaussianSum.rawInfinity,
    RawCertificate.check, RawCertificate.decode,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.rawSample_decode, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes]

#print axioms RawTailInflationCertificate.output_decode_eq
#print axioms RawCertificate.finiteSum_decode_eq
#print axioms RawCertificate.output_decode_eq
#print axioms RawCertificate.checker_sound
#print axioms RawCertificate.accepted_output_contains_exact_finite_sum
#print axioms rawSample_check
#print axioms raw_sample_contains
#print axioms detached_sum_fails_closed
#print axioms nonfinite_prefactor_fails_closed

end SparkInterval.Tests.FactoredSmallQRawPostprocess
