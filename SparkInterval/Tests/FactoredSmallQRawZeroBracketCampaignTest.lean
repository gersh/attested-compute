/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign
import SparkInterval.Tests.FactoredSmallQRawCompletedSignTest

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQRawZeroBracketCampaign

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign
open SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign
open SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign
open SparkInterval.Dirichlet.FactoredSmallQRawZeroBracketCampaign
open SparkInterval.Dirichlet.FactoredSmallQZeroBracket

abbrev RawTailInflationCertificate :=
  SparkInterval.Dirichlet.FactoredSmallQRawPostprocess.RawTailInflationCertificate

abbrev TailInflationCertificate :=
  SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate

def pointDisk (re im : ℚ) : ComplexDisk := ⟨re, im, 0⟩

def rawNegativeTwo : ComplexDisk.Raw :=
  ⟨0xc000000000000000, 0, 0⟩

def typedNegativeTwo : ComplexDisk := pointDisk (-2) 0

def rawOne : ComplexDisk.Raw :=
  SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawOne

def rawNegativeScale : ComplexDisk.RawMulCertificate := {
  left := rawNegativeTwo
  right := rawOne
  output := rawNegativeTwo
  centerErrorBoundBits := 0
  leftCenterNormBoundBits := 0x4000000000000000
  rightCenterNormBoundBits := 0x3ff0000000000000
}

def typedNegativeScale : ComplexDisk.MulCertificate := {
  left := typedNegativeTwo
  right := pointDisk 1 0
  output := typedNegativeTwo
  centerErrorBound := 0
  leftCenterNormBound := 2
  rightCenterNormBound := 1
}

def rawNegativeTail : RawTailInflationCertificate := {
  input := rawNegativeTwo
  tailBoundBits := 0
  output := rawNegativeTwo
}

def typedNegativeTail : TailInflationCertificate := {
  input := typedNegativeTwo
  tailBound := 0
  output := typedNegativeTwo
}

def rawNegativeUntilt : ComplexDisk.RawMulCertificate := rawNegativeScale
def typedNegativeUntilt : ComplexDisk.MulCertificate := typedNegativeScale

def rawNegativePayload : RawCertificate := {
  scaleTimesFourier := rawNegativeScale
  timeTailInflation := rawNegativeTail
  untiltTimesPeriodized := rawNegativeUntilt
  signCode := -1
}

def typedNegativePayload : Certificate := {
  scaleTimesFourier := typedNegativeScale
  timeTailInflation := typedNegativeTail
  untiltTimesPeriodized := typedNegativeUntilt
  sign := .negative
}

def rawPositiveTwo : ComplexDisk.Raw :=
  SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawTwo

def typedPositiveTwo : ComplexDisk := pointDisk 2 0

def rawPositiveScale : ComplexDisk.RawMulCertificate := {
  left := rawPositiveTwo
  right := rawOne
  output := rawPositiveTwo
  centerErrorBoundBits := 0
  leftCenterNormBoundBits := 0x4000000000000000
  rightCenterNormBoundBits := 0x3ff0000000000000
}

def typedPositiveScale : ComplexDisk.MulCertificate := {
  left := typedPositiveTwo
  right := pointDisk 1 0
  output := typedPositiveTwo
  centerErrorBound := 0
  leftCenterNormBound := 2
  rightCenterNormBound := 1
}

def rawPositiveTail : RawTailInflationCertificate := {
  input := rawPositiveTwo
  tailBoundBits := 0
  output := rawPositiveTwo
}

def typedPositiveTail : TailInflationCertificate := {
  input := typedPositiveTwo
  tailBound := 0
  output := typedPositiveTwo
}

def rawPositiveUntilt : ComplexDisk.RawMulCertificate := rawPositiveScale
def typedPositiveUntilt : ComplexDisk.MulCertificate := typedPositiveScale

def rawPositivePayload : RawCertificate := {
  scaleTimesFourier := rawPositiveScale
  timeTailInflation := rawPositiveTail
  untiltTimesPeriodized := rawPositiveUntilt
  signCode := 1
}

def typedPositivePayload : Certificate := {
  scaleTimesFourier := typedPositiveScale
  timeTailInflation := typedPositiveTail
  untiltTimesPeriodized := typedPositiveUntilt
  sign := .positive
}

theorem rawNegativeTwo_decode :
    rawNegativeTwo.decode = some typedNegativeTwo := by
  norm_num [rawNegativeTwo, typedNegativeTwo, pointDisk,
    ComplexDisk.Raw.decode, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem rawNegativeScale_decode :
    rawNegativeScale.decode = some typedNegativeScale := by
  norm_num [rawNegativeScale, typedNegativeScale, rawNegativeTwo,
    typedNegativeTwo, rawOne, pointDisk,
    SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawOne,
    SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawPoint,
    ComplexDisk.RawMulCertificate.decode, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue,
    Binary64.fractionBits, Binary64.signBit, Binary64.signThreshold]

theorem rawNegativeTail_decode :
    rawNegativeTail.decode = some typedNegativeTail := by
  norm_num [rawNegativeTail, typedNegativeTail, rawNegativeTwo,
    typedNegativeTwo, pointDisk,
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocess.RawTailInflationCertificate.decode,
    ComplexDisk.Raw.decode, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem rawNegativePayload_decode :
    rawNegativePayload.decode = some typedNegativePayload := by
  simp [rawNegativePayload, typedNegativePayload, RawCertificate.decode,
    rawNegativeScale_decode, rawNegativeTail_decode, rawNegativeUntilt,
    typedNegativeUntilt, decodeStrictSign]

theorem typedNegativePayload_check :
    typedNegativePayload.check typedNegativeTwo = true := by
  norm_num [typedNegativePayload, typedNegativeScale, typedNegativeTail,
    typedNegativeUntilt, typedNegativeTwo, pointDisk,
    FactoredSmallQCompletedSign.Certificate.check,
    FactoredSmallQCompletedSign.Certificate.Accepted,
    FactoredSmallQCompletedSign.Certificate.output, StrictSign.CertifiedBy,
    ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    FactoredSmallQPostprocess.TailInflationCertificate.check,
    FactoredSmallQPostprocess.TailInflationCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

theorem rawNegativePayload_check :
    rawNegativePayload.check rawNegativeTwo = true := by
  rw [RawCertificate.check]
  have hattached :
      decide (rawNegativePayload.scaleTimesFourier.left = rawNegativeTwo) =
        true := by
    rfl
  rw [hattached]
  simp only [Bool.true_and]
  rw [rawNegativeTwo_decode, rawNegativePayload_decode]
  exact typedNegativePayload_check

theorem rawPositiveTwo_decode :
    rawPositiveTwo.decode = some typedPositiveTwo := by
  simpa [rawPositiveTwo, typedPositiveTwo, pointDisk,
    SparkInterval.Tests.FactoredSmallQRawCompletedSign.pointDisk] using
      SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawTwo_decode

theorem rawPositiveScale_decode :
    rawPositiveScale.decode = some typedPositiveScale := by
  norm_num [rawPositiveScale, typedPositiveScale, rawPositiveTwo,
    typedPositiveTwo, rawOne, pointDisk,
    SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawTwo,
    SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawOne,
    SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawPoint,
    ComplexDisk.RawMulCertificate.decode, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue,
    Binary64.fractionBits, Binary64.signBit, Binary64.signThreshold]

theorem rawPositiveTail_decode :
    rawPositiveTail.decode = some typedPositiveTail := by
  norm_num [rawPositiveTail, typedPositiveTail, rawPositiveTwo,
    typedPositiveTwo, pointDisk,
    SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawTwo,
    SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawPoint,
    FactoredSmallQRawPostprocess.RawTailInflationCertificate.decode,
    ComplexDisk.Raw.decode, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem rawPositivePayload_decode :
    rawPositivePayload.decode = some typedPositivePayload := by
  simp [rawPositivePayload, typedPositivePayload, RawCertificate.decode,
    rawPositiveScale_decode, rawPositiveTail_decode, rawPositiveUntilt,
    typedPositiveUntilt, decodeStrictSign]

theorem typedPositivePayload_check :
    typedPositivePayload.check typedPositiveTwo = true := by
  norm_num [typedPositivePayload, typedPositiveScale, typedPositiveTail,
    typedPositiveUntilt, typedPositiveTwo, pointDisk,
    FactoredSmallQCompletedSign.Certificate.check,
    FactoredSmallQCompletedSign.Certificate.Accepted,
    FactoredSmallQCompletedSign.Certificate.output, StrictSign.CertifiedBy,
    ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    FactoredSmallQPostprocess.TailInflationCertificate.check,
    FactoredSmallQPostprocess.TailInflationCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

theorem rawPositivePayload_check :
    rawPositivePayload.check rawPositiveTwo = true := by
  rw [RawCertificate.check]
  have hattached :
      decide (rawPositivePayload.scaleTimesFourier.left = rawPositiveTwo) =
        true := by
    rfl
  rw [hattached]
  simp only [Bool.true_and]
  rw [rawPositiveTwo_decode, rawPositivePayload_decode]
  exact typedPositivePayload_check

/-! ## One literal two-sample campaign -/

def fullSpec : Spec := ⟨3, [2], 2⟩
def sourceSpec :
    FactoredSmallQRawZeroBracketCampaign.SourceSampleSpec := ⟨3, [2], 2⟩

def rawTransform : FactoredSmallQRawDFT.RawCertificate 1 := {
  input := []
  twiddleRows := []
  stages := []
  output := [rawNegativeTwo, rawPositiveTwo]
}

def rawTransforms (_characterId : Nat) := rawTransform

def negativeCell : Cell RawCertificate :=
  ⟨⟨2, 0⟩, rawNegativePayload⟩

def positiveCell : Cell RawCertificate :=
  ⟨⟨2, 1⟩, rawPositivePayload⟩

def batch : Batch RawCertificate :=
  ⟨0, 0, [2], [negativeCell, positiveCell]⟩

def campaign :
    FactoredSmallQRawZeroBracketCampaign.RawSignCampaignCertificate := {
  q := 3
  roster := [2]
  transformLength := 2
  batches := [batch]
}

theorem negative_payload_ok :
    payloadCheck rawTransforms ⟨2, 0⟩ rawNegativePayload = true := by
  simpa [payloadCheck, rawTransforms, rawTransform] using
    rawNegativePayload_check

theorem positive_payload_ok :
    payloadCheck rawTransforms ⟨2, 1⟩ rawPositivePayload = true := by
  simpa [payloadCheck, rawTransforms, rawTransform] using
    rawPositivePayload_check

theorem campaign_check :
    FactoredSmallQRawCompletedSignPayloadCampaign.check fullSpec sourceSpec
      rawTransforms campaign = true := by
  simp [FactoredSmallQRawCompletedSignPayloadCampaign.check,
    FactoredSmallQRawCompletedSignCampaign.SourceDFTAgreement,
    fullSpec, sourceSpec, campaign, batch, negativeCell, positiveCell,
    FactoredSmallQRawDFT.lineLength, FactoredSmallQCampaign.Certificate.check,
    FactoredSmallQCampaign.Certificate.CoverageValid, Spec.WellFormed,
    BatchChain, BatchCellsValid, expectedKeys,
    FactoredSmallQCompletedSignCampaign.SourceSampleSpec.toCampaignSpec,
    negative_payload_ok, positive_payload_ok]
  rfl

theorem negative_cell_at :
    DecodedCellAt campaign ⟨2, 0⟩ typedNegativePayload := by
  refine ⟨batch, by simp [campaign], negativeCell, by simp [batch], rfl, ?_⟩
  exact rawNegativePayload_decode

theorem positive_cell_at :
    DecodedCellAt campaign ⟨2, 1⟩ typedPositivePayload := by
  refine ⟨batch, by simp [campaign], positiveCell, by simp [batch], rfl, ?_⟩
  exact rawPositivePayload_decode

theorem negative_cell_in_source_domain :
    (2 : Nat) ∈ sourceSpec.roster ∧ 0 < sourceSpec.sampleCount :=
  DecodedCellAt.key_in_source_domain campaign_check negative_cell_at

theorem negative_endpoint_check :
    (mkEndpoint 1 ⟨2, 0⟩ typedNegativePayload).check
      (decodedOutputDisk rawTransforms) = true :=
  decodedCellAt_endpoint_check campaign_check negative_cell_at

theorem literal_words_check_bracket :
    (mkBracket 1 ⟨2, 0⟩ typedNegativePayload
      ⟨2, 1⟩ typedPositivePayload).check
        (decodedOutputDisk rawTransforms) = true := by
  apply decodedCells_bracket_check campaign_check negative_cell_at
    positive_cell_at
  · norm_num
  · rfl
  · norm_num
  · exact Or.inl ⟨rfl, rfl⟩

theorem literal_words_check_rational_bracket :
    (mkBracket 1 ⟨2, 0⟩ typedNegativePayload
      ⟨2, 1⟩ typedPositivePayload).toRationalBracket.check = true :=
  CompletedSignBracket.toRationalBracket_check literal_words_check_bracket

/-! ## Explicit semantic composition -/

theorem point_contains (value : ℚ) :
    (pointDisk value 0).ContainsComplex (value : ℂ) := by
  unfold ComplexDisk.ContainsComplex
  have hcenter : (pointDisk value 0).center = (value : ℂ) := by
    apply Complex.ext <;>
      norm_num [pointDisk, ComplexDisk.center]
  rw [hcenter]
  norm_num [pointDisk]

theorem decoded_negative_output :
    decodedOutputDisk rawTransforms ⟨2, 0⟩ = typedNegativeTwo := by
  apply decodedOutputDisk_eq_of_output_decode
  · rfl
  · exact rawNegativeTwo_decode

theorem decoded_positive_output :
    decodedOutputDisk rawTransforms ⟨2, 1⟩ = typedPositiveTwo := by
  apply decodedOutputDisk_eq_of_output_decode
  · rfl
  · exact rawPositiveTwo_decode

noncomputable def sourceB : ℝ := 2 * Real.pi

theorem sourceB_pos : 0 < sourceB := by
  unfold sourceB
  positivity

theorem sourceScale_sourceB : sourceScale sourceB = 1 := by
  unfold sourceScale sourceB
  have hpi : Real.pi ≠ 0 := ne_of_gt Real.pi_pos
  field_simp

def evaluator (t : ℝ) : ℝ := 4 * t - 2

/-- Every analytic fact is displayed in this named premise; none is recovered
from the raw checker. -/
theorem lower_source_realizes :
    (mkEndpoint 1 ⟨2, 0⟩ typedNegativePayload).SourceRealizes
      (decodedOutputDisk rawTransforms) evaluator (-2 : ℂ) 0 sourceB 0 := by
  refine ⟨sourceB_pos, by norm_num, by norm_num, ?_⟩
  refine ⟨?_, ?_, ?_, ?_, ?_, ?_⟩
  · change (decodedOutputDisk rawTransforms ⟨2, 0⟩).ContainsComplex (-2)
    rw [decoded_negative_output]
    simpa [typedNegativeTwo] using (point_contains (-2))
  · rw [sourceScale_sourceB]
    simpa [mkEndpoint, typedNegativePayload, typedNegativeScale] using
      (point_contains 1)
  · norm_num [mkEndpoint, typedNegativePayload, typedNegativeTail]
  · simpa [mkEndpoint, typedNegativePayload, typedNegativeUntilt,
      typedNegativeScale, sourceUntilt] using (point_contains 1)
  · norm_num [sourceScale_sourceB, sourceUntilt, completedValue]
  · norm_num [evaluator, mkEndpoint, SignedEndpoint.sourceTime,
      sourceScale_sourceB, sourceUntilt, completedValue]

theorem upper_source_realizes :
    (mkEndpoint 1 ⟨2, 1⟩ typedPositivePayload).SourceRealizes
      (decodedOutputDisk rawTransforms) evaluator (2 : ℂ) 0 sourceB 0 := by
  refine ⟨sourceB_pos, by norm_num, by norm_num, ?_⟩
  refine ⟨?_, ?_, ?_, ?_, ?_, ?_⟩
  · change (decodedOutputDisk rawTransforms ⟨2, 1⟩).ContainsComplex 2
    rw [decoded_positive_output]
    simpa [typedPositiveTwo] using (point_contains 2)
  · rw [sourceScale_sourceB]
    simpa [mkEndpoint, typedPositivePayload, typedPositiveScale] using
      (point_contains 1)
  · norm_num [mkEndpoint, typedPositivePayload, typedPositiveTail]
  · simpa [mkEndpoint, typedPositivePayload, typedPositiveUntilt,
      typedPositiveScale, sourceUntilt] using (point_contains 1)
  · norm_num [sourceScale_sourceB, sourceUntilt, completedValue]
  · norm_num [evaluator, mkEndpoint, SignedEndpoint.sourceTime,
      sourceScale_sourceB, sourceUntilt, completedValue]

theorem lower_evaluator_link :
    (mkEndpoint 1 ⟨2, 0⟩ typedNegativePayload).EvaluatorLink evaluator :=
  decodedCellAt_evaluatorLink_of_sourceRealizes campaign_check
    negative_cell_at lower_source_realizes

theorem literal_words_checked_with_source_realization :
    (mkBracket 1 ⟨2, 0⟩ typedNegativePayload
        ⟨2, 1⟩ typedPositivePayload).toRationalBracket.check = true ∧
      (mkBracket 1 ⟨2, 0⟩ typedNegativePayload
        ⟨2, 1⟩ typedPositivePayload).toRationalBracket.EnclosesEndpoints
          evaluator := by
  apply decodedCells_checkedRationalBracket_of_sourceRealizes campaign_check
    negative_cell_at positive_cell_at
  · norm_num
  · rfl
  · norm_num
  · exact Or.inl ⟨rfl, rfl⟩
  · exact lower_source_realizes
  · exact upper_source_realizes

/-! ## Exact source-grid cast -/

def genericParameters :
    FactoredSmallQRawZeroBracketCampaign.SourceParameters := ⟨1, 2, 0⟩

theorem generic_grid_time_alignment :
    ((SignedEndpoint.sourceTime 1 ⟨2, 1⟩ : ℚ) : ℝ) =
      genericParameters.t ⟨2, 1⟩ := by
  apply sourceTime_cast_eq_parameters_t
  norm_num [genericParameters]

noncomputable def bookerParameters :
    FactoredSmallQRawZeroBracketCampaign.SourceParameters :=
  ⟨FactoredSmallQRawCompletedSignCampaign.SourceParameters.bookerA, 2, 0⟩

theorem booker_grid_time_alignment :
    ((SignedEndpoint.sourceTime ((64 : ℚ) / 5) ⟨2, 1⟩ : ℚ) : ℝ) =
      bookerParameters.t ⟨2, 1⟩ := by
  apply booker_sourceTime_cast_eq_parameters_t
  rfl

/-! ## Literal attachment remains fail-closed -/

def detachedTransform : FactoredSmallQRawDFT.RawCertificate 1 :=
  { rawTransform with output := [rawPositiveTwo, rawPositiveTwo] }

def detachedTransforms (_characterId : Nat) := detachedTransform

theorem detached_lower_word_fails :
    FactoredSmallQRawCompletedSignPayloadCampaign.check fullSpec sourceSpec
      detachedTransforms campaign = false := by
  have hdetached : rawNegativePayload.check rawPositiveTwo = false := by
    norm_num [RawCertificate.check, rawNegativePayload, rawNegativeScale,
      rawNegativeTwo, rawPositiveTwo,
      SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawTwo,
      SparkInterval.Tests.FactoredSmallQRawCompletedSign.rawPoint]
  simp [FactoredSmallQRawCompletedSignPayloadCampaign.check,
    FactoredSmallQRawCompletedSignCampaign.SourceDFTAgreement,
    fullSpec, sourceSpec, campaign, batch, negativeCell, positiveCell,
    FactoredSmallQRawDFT.lineLength, FactoredSmallQCampaign.Certificate.check,
    FactoredSmallQCampaign.Certificate.CoverageValid, Spec.WellFormed,
    BatchChain, BatchCellsValid, expectedKeys,
    FactoredSmallQCompletedSignCampaign.SourceSampleSpec.toCampaignSpec,
    payloadCheck, detachedTransforms, detachedTransform, hdetached]

/-- The alias decodes to the same rational disk, but its signed-zero word is
not the literal word attached to the negative payload. -/
def rawNegativeTwoSignedZero : ComplexDisk.Raw :=
  ⟨0xc000000000000000, 0x8000000000000000, 0⟩

theorem signed_zero_alias_decodes_equal :
    rawNegativeTwoSignedZero.decode = some typedNegativeTwo := by
  norm_num [rawNegativeTwoSignedZero, typedNegativeTwo, pointDisk,
    ComplexDisk.Raw.decode, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

def signedZeroTransform : FactoredSmallQRawDFT.RawCertificate 1 :=
  { rawTransform with output := [rawNegativeTwoSignedZero, rawPositiveTwo] }

def signedZeroTransforms (_characterId : Nat) := signedZeroTransform

theorem signed_zero_alias_fails :
    FactoredSmallQRawCompletedSignPayloadCampaign.check fullSpec sourceSpec
      signedZeroTransforms campaign = false := by
  have halias : rawNegativePayload.check rawNegativeTwoSignedZero = false := by
    norm_num [RawCertificate.check, rawNegativePayload, rawNegativeScale,
      rawNegativeTwo, rawNegativeTwoSignedZero]
  simp [FactoredSmallQRawCompletedSignPayloadCampaign.check,
    FactoredSmallQRawCompletedSignCampaign.SourceDFTAgreement,
    fullSpec, sourceSpec, campaign, batch, negativeCell, positiveCell,
    FactoredSmallQRawDFT.lineLength, FactoredSmallQCampaign.Certificate.check,
    FactoredSmallQCampaign.Certificate.CoverageValid, Spec.WellFormed,
    BatchChain, BatchCellsValid, expectedKeys,
    FactoredSmallQCompletedSignCampaign.SourceSampleSpec.toCampaignSpec,
    payloadCheck, signedZeroTransforms, signedZeroTransform, halias]

#print axioms decodedOutputDisk_eq_of_output_decode
#print axioms DecodedCellAt.key_in_source_domain
#print axioms decodedCellAt_endpoint_check
#print axioms decodedCellAt_evaluatorLink_of_sourceRealizes
#print axioms sourceTime_cast_eq_parameters_t
#print axioms booker_sourceTime_cast_eq_parameters_t
#print axioms decodedCells_bracket_check
#print axioms decodedCells_checkedRationalBracket_of_sourceRealizes
#print axioms literal_words_check_rational_bracket
#print axioms literal_words_checked_with_source_realization
#print axioms detached_lower_word_fails
#print axioms signed_zero_alias_fails

end SparkInterval.Tests.FactoredSmallQRawZeroBracketCampaign
