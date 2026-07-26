/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign
import SparkInterval.Tests.FactoredSmallQRawCompletedSignTest
import SparkInterval.Tests.FactoredSmallQRawDFTCompositionTest

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQRawCompletedSignPayloadCampaign

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign
open SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign

abbrev RawSignCertificate :=
  SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign.RawCertificate

abbrev RawTailInflationCertificate :=
  SparkInterval.Dirichlet.FactoredSmallQRawPostprocess.RawTailInflationCertificate

def fullSpec : Spec := ⟨3, [2], 1⟩
def sourceSpec : SourceSampleSpec := ⟨3, [2], 1⟩

def rawFourier : ComplexDisk.Raw :=
  SparkInterval.Tests.FactoredSmallQRawPostprocess.rawTail.output

def typedFourier : ComplexDisk :=
  SparkInterval.Tests.FactoredSmallQRawPostprocess.typedTail.output

def rawOne : ComplexDisk.Raw :=
  SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawOne

def pointDisk (re im : ℚ) : ComplexDisk := ⟨re, im, 0⟩

def rawScale : ComplexDisk.RawMulCertificate := {
  left := rawFourier
  right := rawOne
  output := rawFourier
  centerErrorBoundBits := 0
  leftCenterNormBoundBits := 0x4060000000000000
  rightCenterNormBoundBits := 0x3ff0000000000000
}

def typedScale : ComplexDisk.MulCertificate := {
  left := typedFourier
  right := pointDisk 1 0
  output := typedFourier
  centerErrorBound := 0
  leftCenterNormBound := 128
  rightCenterNormBound := 1
}

def rawTimeTail : RawTailInflationCertificate := {
  input := rawFourier
  tailBoundBits := 0
  output := rawFourier
}

def typedTimeTail :
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate := {
  input := typedFourier
  tailBound := 0
  output := typedFourier
}

def rawUntilt : ComplexDisk.RawMulCertificate := rawScale
def typedUntilt : ComplexDisk.MulCertificate := typedScale

def rawPayload : RawSignCertificate := {
  scaleTimesFourier := rawScale
  timeTailInflation := rawTimeTail
  untiltTimesPeriodized := rawUntilt
  signCode := 1
}

def typedPayload : Certificate := {
  scaleTimesFourier := typedScale
  timeTailInflation := typedTimeTail
  untiltTimesPeriodized := typedUntilt
  sign := .positive
}

theorem rawFourier_decode : rawFourier.decode = some typedFourier := by
  exact SparkInterval.Tests.FactoredSmallQRawDFTComposition.final_word_decode

theorem rawScale_decode : rawScale.decode = some typedScale := by
  norm_num [rawScale, typedScale, rawFourier, typedFourier, rawOne,
    pointDisk,
    SparkInterval.Tests.FactoredSmallQRawPostprocess.rawTail,
    SparkInterval.Tests.FactoredSmallQRawPostprocess.typedTail,
    SparkInterval.Tests.FactoredSmallQRawPostprocess.rawEightySixNegativeEightySix,
    SparkInterval.Tests.FactoredSmallQRawPostprocess.rawEightySixNegativeEightySixHalf,
    SparkInterval.Tests.FactoredSmallQRawPostprocess.pointDisk,
    SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawOne,
    SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawPoint,
    ComplexDisk.RawMulCertificate.decode, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem rawTimeTail_decode :
    rawTimeTail.decode = some typedTimeTail := by
  have hzeroExponent : Binary64.exponentBits 0 = 0 := by
    norm_num [Binary64.exponentBits, Binary64.fractionModulus,
      Binary64.exponentModulus]
  have hzeroFraction : Binary64.fractionBits 0 = 0 := by
    norm_num [Binary64.fractionBits, Binary64.fractionModulus]
  have hzeroSign : Binary64.signBit 0 = false := by
    norm_num [Binary64.signBit, Binary64.signThreshold]
  have hzero : Binary64.decodeFinite 0 = some (0 : ℚ) := by
    rw [Binary64.decodeFinite_eq_some_iff]
    refine ⟨by norm_num [Binary64.wordLimit], ?_, ?_⟩
    · norm_num [hzeroExponent, Binary64.exponentAllOnes]
    · unfold Binary64.finiteValue
      simp only [hzeroExponent, hzeroFraction, if_pos, Nat.cast_zero,
        zero_mul, hzeroSign, Bool.false_eq_true, if_false]
  simp [rawTimeTail, typedTimeTail,
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocess.RawTailInflationCertificate.decode,
    rawFourier_decode, hzero]

theorem rawPayload_decode : rawPayload.decode = some typedPayload := by
  simp [rawPayload, typedPayload,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign.RawCertificate.decode,
    rawScale_decode, rawTimeTail_decode, rawUntilt, typedUntilt,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign.decodeStrictSign]

theorem typedPayload_check : typedPayload.check typedFourier = true := by
  norm_num [typedPayload, typedScale, typedTimeTail, typedUntilt,
    typedFourier, pointDisk,
    SparkInterval.Tests.FactoredSmallQRawPostprocess.typedTail,
    SparkInterval.Tests.FactoredSmallQRawPostprocess.pointDisk,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.Accepted,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.output,
    StrictSign.CertifiedBy, ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.check,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

theorem rawPayload_check : rawPayload.check rawFourier = true := by
  rw [SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign.RawCertificate.check]
  have hattached :
      decide (rawPayload.scaleTimesFourier.left = rawFourier) = true := by
    rfl
  rw [hattached]
  simp only [Bool.true_and]
  rw [rawFourier_decode, rawPayload_decode]
  exact typedPayload_check

def batch : Batch RawSignCertificate :=
  ⟨0, 0, [2], [⟨⟨2, 0⟩, rawPayload⟩]⟩

def campaign : RawSignCampaignCertificate := {
  q := 3
  roster := [2]
  transformLength := 1
  batches := [batch]
}

def rawTransforms (_ : Nat) :
    SparkInterval.Dirichlet.FactoredSmallQRawDFT.RawCertificate 0 :=
  SparkInterval.Tests.FactoredSmallQRawDFTComposition.rawTransform

theorem payload_ok :
    payloadCheck rawTransforms ⟨2, 0⟩ rawPayload = true := by
  simpa [payloadCheck, rawTransforms,
    SparkInterval.Tests.FactoredSmallQRawDFTComposition.rawTransform,
    rawFourier] using rawPayload_check

theorem campaign_check :
    check fullSpec sourceSpec rawTransforms campaign = true := by
  simp [check,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.SourceDFTAgreement,
    fullSpec, sourceSpec, campaign, batch,
    SparkInterval.Dirichlet.FactoredSmallQRawDFT.lineLength,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.CoverageValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchChain,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchCellsValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.expectedKeys,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign.SourceSampleSpec.toCampaignSpec,
    payload_ok]

/-! ## Fail-closed campaign boundaries -/

def missingOutputTransform :
    SparkInterval.Dirichlet.FactoredSmallQRawDFT.RawCertificate 0 :=
  { SparkInterval.Tests.FactoredSmallQRawDFTComposition.rawTransform with
    output := [] }

def missingOutputTransforms (_ : Nat) := missingOutputTransform

theorem missing_output_fails_closed :
    check fullSpec sourceSpec missingOutputTransforms campaign = false := by
  simp [check,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.SourceDFTAgreement,
    fullSpec, sourceSpec, campaign, batch,
    SparkInterval.Dirichlet.FactoredSmallQRawDFT.lineLength,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.CoverageValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchChain,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchCellsValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.expectedKeys,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign.SourceSampleSpec.toCampaignSpec,
    payloadCheck, missingOutputTransforms, missingOutputTransform]

def detachedBatch : Batch RawSignCertificate :=
  ⟨0, 0, [2], [⟨⟨2, 0⟩,
    SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawSample⟩]⟩

def detachedCampaign : RawSignCampaignCertificate :=
  { campaign with batches := [detachedBatch] }

theorem detached_word_fails_closed :
    check fullSpec sourceSpec rawTransforms detachedCampaign = false := by
  simp [check,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.SourceDFTAgreement,
    fullSpec, sourceSpec, detachedCampaign, campaign, detachedBatch,
    SparkInterval.Dirichlet.FactoredSmallQRawDFT.lineLength,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.CoverageValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchChain,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchCellsValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.expectedKeys,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign.SourceSampleSpec.toCampaignSpec,
    payloadCheck, rawTransforms,
    SparkInterval.Tests.FactoredSmallQRawDFTComposition.rawTransform,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign.RawCertificate.check,
    SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawSample,
    SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawScaleProduct,
    SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawTwo,
    SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawPoint,
    SparkInterval.Tests.FactoredSmallQRawPostprocess.rawTail,
    SparkInterval.Tests.FactoredSmallQRawPostprocess.rawEightySixNegativeEightySixHalf]

def wrongSignPayload : RawSignCertificate :=
  { rawPayload with signCode := -1 }

def wrongSignBatch : Batch RawSignCertificate :=
  ⟨0, 0, [2], [⟨⟨2, 0⟩, wrongSignPayload⟩]⟩

def wrongSignCampaign : RawSignCampaignCertificate :=
  { campaign with batches := [wrongSignBatch] }

theorem wrong_sign_fails_closed :
    check fullSpec sourceSpec rawTransforms wrongSignCampaign = false := by
  have hdecode : wrongSignPayload.decode =
      some { typedPayload with sign := .negative } := by
    simp [wrongSignPayload, rawPayload, typedPayload,
      SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign.RawCertificate.decode,
      rawScale_decode, rawTimeTail_decode, rawUntilt, typedUntilt,
      SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign.decodeStrictSign]
  have hwrong : wrongSignPayload.check rawFourier = false := by
    rw [SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign.RawCertificate.check]
    have hattached :
        decide (wrongSignPayload.scaleTimesFourier.left = rawFourier) = true := by
      rfl
    rw [hattached]
    simp only [Bool.true_and]
    rw [rawFourier_decode, hdecode]
    norm_num [typedPayload, typedScale, typedTimeTail, typedUntilt,
      typedFourier, pointDisk,
      SparkInterval.Tests.FactoredSmallQRawPostprocess.typedTail,
      SparkInterval.Tests.FactoredSmallQRawPostprocess.pointDisk,
      SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.check,
      SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.Accepted,
      SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.output,
      StrictSign.CertifiedBy, ComplexDisk.MulCertificate.check,
      ComplexDisk.MulCertificate.WellFormed,
      SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.check,
      SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.WellFormed,
      ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]
  have hwrongTail : wrongSignPayload.check
      SparkInterval.Tests.FactoredSmallQRawPostprocess.rawTail.output = false := by
    simpa [rawFourier] using hwrong
  simp [check,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.SourceDFTAgreement,
    fullSpec, sourceSpec, wrongSignCampaign, campaign, wrongSignBatch,
    SparkInterval.Dirichlet.FactoredSmallQRawDFT.lineLength,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.CoverageValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchChain,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchCellsValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.expectedKeys,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign.SourceSampleSpec.toCampaignSpec,
    payloadCheck, rawTransforms,
    SparkInterval.Tests.FactoredSmallQRawDFTComposition.rawTransform,
    hwrongTail]

def oversizedSourceSpec : SourceSampleSpec := ⟨3, [2], 2⟩

theorem source_length_fails_closed :
    check fullSpec oversizedSourceSpec rawTransforms campaign = false := by
  norm_num [check,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.SourceDFTAgreement,
    fullSpec, oversizedSourceSpec,
    SparkInterval.Dirichlet.FactoredSmallQRawDFT.lineLength]

#print axioms checker_sound
#print axioms requested_source_sample_has_raw_source_sign
#print axioms campaign_check
#print axioms missing_output_fails_closed
#print axioms detached_word_fails_closed
#print axioms wrong_sign_fails_closed
#print axioms source_length_fails_closed

end SparkInterval.Tests.FactoredSmallQRawCompletedSignPayloadCampaign
