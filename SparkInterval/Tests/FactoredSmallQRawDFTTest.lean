/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawDFT
import SparkInterval.Tests.FactoredSmallQDFTTest

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQRawDFT

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.FactoredSmallQRawDFT

def rawZero : ComplexDisk.Raw :=
  ⟨0x0000000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawOne : ComplexDisk.Raw :=
  ⟨0x3ff0000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawTwo : ComplexDisk.Raw :=
  ⟨0x4000000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawThree : ComplexDisk.Raw :=
  ⟨0x4008000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawFour : ComplexDisk.Raw :=
  ⟨0x4010000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawSix : ComplexDisk.Raw :=
  ⟨0x4018000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawTen : ComplexDisk.Raw :=
  ⟨0x4024000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawNegativeTwo : ComplexDisk.Raw :=
  ⟨0xc000000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawImaginaryUnit : ComplexDisk.Raw :=
  ⟨0x0000000000000000, 0x3ff0000000000000, 0x0000000000000000⟩
def rawNegativeTwoI : ComplexDisk.Raw :=
  ⟨0x0000000000000000, 0xc000000000000000, 0x0000000000000000⟩
def rawPositiveTwoI : ComplexDisk.Raw :=
  ⟨0x0000000000000000, 0x4000000000000000, 0x0000000000000000⟩
def rawNegativeTwoNegativeTwo : ComplexDisk.Raw :=
  ⟨0xc000000000000000, 0xc000000000000000, 0x0000000000000000⟩
def rawNegativeTwoPositiveTwo : ComplexDisk.Raw :=
  ⟨0xc000000000000000, 0x4000000000000000, 0x0000000000000000⟩
def rawNegativeThree : ComplexDisk.Raw :=
  ⟨0xc008000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawNegativeFour : ComplexDisk.Raw :=
  ⟨0xc010000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawNegativeSix : ComplexDisk.Raw :=
  ⟨0xc018000000000000, 0x0000000000000000, 0x0000000000000000⟩

def rawExactMul (left right output : ComplexDisk.Raw) :
    ComplexDisk.RawMulCertificate := {
  left
  right
  output
  centerErrorBoundBits := 0x0000000000000000
  leftCenterNormBoundBits := 0x4059000000000000
  rightCenterNormBoundBits := 0x4059000000000000
}

def rawExactAdd (left right output : ComplexDisk.Raw) :
    ComplexDisk.RawAddCertificate := {
  left
  right
  output
  centerErrorBoundBits := 0x0000000000000000
}

/- The subtraction witnesses spell exact centre negation explicitly, including
the canonical positive-zero representation for unchanged zero coordinates. -/
def rawStage0Row0 : RawButterflyCertificate := {
  stageExponent := 0
  stageLength := 2
  group := 0
  offset := 0
  leftIndex := 0
  rightIndex := 1
  twiddleTimesRight := rawExactMul rawThree rawOne rawThree
  addToLeft := rawExactAdd rawOne rawThree rawFour
  addNegToRight := rawExactAdd rawOne rawNegativeThree rawNegativeTwo
}

def rawStage0Row1 : RawButterflyCertificate := {
  stageExponent := 0
  stageLength := 2
  group := 1
  offset := 0
  leftIndex := 2
  rightIndex := 3
  twiddleTimesRight := rawExactMul rawFour rawOne rawFour
  addToLeft := rawExactAdd rawTwo rawFour rawSix
  addNegToRight := rawExactAdd rawTwo rawNegativeFour rawNegativeTwo
}

def rawStage1Row0 : RawButterflyCertificate := {
  stageExponent := 1
  stageLength := 4
  group := 0
  offset := 0
  leftIndex := 0
  rightIndex := 2
  twiddleTimesRight := rawExactMul rawSix rawOne rawSix
  addToLeft := rawExactAdd rawFour rawSix rawTen
  addNegToRight := rawExactAdd rawFour rawNegativeSix rawNegativeTwo
}

def rawStage1Row1 : RawButterflyCertificate := {
  stageExponent := 1
  stageLength := 4
  group := 0
  offset := 1
  leftIndex := 1
  rightIndex := 3
  twiddleTimesRight :=
    rawExactMul rawNegativeTwo rawImaginaryUnit rawNegativeTwoI
  addToLeft :=
    rawExactAdd rawNegativeTwo rawNegativeTwoI rawNegativeTwoNegativeTwo
  addNegToRight :=
    rawExactAdd rawNegativeTwo rawPositiveTwoI rawNegativeTwoPositiveTwo
}

def rawStage0 : RawStageCertificate :=
  ⟨0, [rawStage0Row0, rawStage0Row1]⟩

def rawStage1 : RawStageCertificate :=
  ⟨1, [rawStage1Row0, rawStage1Row1]⟩

def sample : RawCertificate 2 := {
  input := [rawOne, rawThree, rawTwo, rawFour]
  twiddleRows := [[rawOne], [rawOne, rawImaginaryUnit]]
  stages := [rawStage0, rawStage1]
  output := [rawTen, rawNegativeTwoNegativeTwo, rawNegativeTwo,
    rawNegativeTwoPositiveTwo]
}

def bounds : Bounds := ⟨2, 4, 15⟩

theorem sample_shape : CanonicalShape (logLength := 2)
    sample.input sample.output sample.twiddleRows sample.stages := by
  refine ⟨rfl, rfl, rfl, rfl, ?_⟩
  intro stage hstage
  have hstageLt : stage < 2 := List.mem_range.mp hstage
  interval_cases stage <;>
    norm_num [sample, rawStage0, rawStage1, StageShape, lineLength,
      butterflyRowsPerStage, halfLength]

def decodedStage0 : StageCertificate 2 :=
  ⟨0, butterflyTable 0
    [SparkInterval.Tests.FactoredSmallQDFT.stage0Row0,
      SparkInterval.Tests.FactoredSmallQDFT.stage0Row1]⟩

def decodedStage1 : StageCertificate 2 :=
  ⟨1, butterflyTable 1
    [SparkInterval.Tests.FactoredSmallQDFT.stage1Row0,
      SparkInterval.Tests.FactoredSmallQDFT.stage1Row1]⟩

def decodedSample : DecodedCertificate 2 := {
  inputValues :=
    [SparkInterval.Tests.FactoredSmallQDFT.pointDisk 1 0,
      SparkInterval.Tests.FactoredSmallQDFT.pointDisk 3 0,
      SparkInterval.Tests.FactoredSmallQDFT.pointDisk 2 0,
      SparkInterval.Tests.FactoredSmallQDFT.pointDisk 4 0]
  twiddleValues :=
    [[SparkInterval.Tests.FactoredSmallQDFT.one],
      [SparkInterval.Tests.FactoredSmallQDFT.one,
        SparkInterval.Tests.FactoredSmallQDFT.imagUnit]]
  stageValues := [decodedStage0, decodedStage1]
  outputValues :=
    [SparkInterval.Tests.FactoredSmallQDFT.pointDisk 10 0,
      SparkInterval.Tests.FactoredSmallQDFT.pointDisk (-2) (-2),
      SparkInterval.Tests.FactoredSmallQDFT.pointDisk (-2) 0,
      SparkInterval.Tests.FactoredSmallQDFT.pointDisk (-2) 2]
}

theorem sample_decode : sample.decode = some decodedSample := by
  rw [RawCertificate.decode]
  simp only [if_pos sample_shape]
  norm_num [sample, rawStage0, rawStage1, rawStage0Row0,
    rawStage0Row1, rawStage1Row0, rawStage1Row1, rawNegativeThree,
    rawNegativeFour, rawNegativeSix, rawNegativeTwoNegativeTwo,
    rawNegativeTwoPositiveTwo, rawNegativeTwoI, rawPositiveTwoI,
    rawImaginaryUnit, rawNegativeTwo, rawTen, rawSix, rawFour, rawThree,
    rawTwo, rawOne, rawExactMul, rawExactAdd, decodedSample,
    decodedStage0, decodedStage1,
    SparkInterval.Tests.FactoredSmallQDFT.stage0Row0,
    SparkInterval.Tests.FactoredSmallQDFT.stage0Row1,
    SparkInterval.Tests.FactoredSmallQDFT.stage1Row0,
    SparkInterval.Tests.FactoredSmallQDFT.stage1Row1,
    SparkInterval.Tests.FactoredSmallQDFT.mkButterfly,
    SparkInterval.Tests.FactoredSmallQDFT.exactMul,
    SparkInterval.Tests.FactoredSmallQDFT.exactAdd,
    SparkInterval.Tests.FactoredSmallQDFT.exactProduct,
    SparkInterval.Tests.FactoredSmallQDFT.exactSum,
    SparkInterval.Tests.FactoredSmallQDFT.pointDisk,
    SparkInterval.Tests.FactoredSmallQDFT.one,
    SparkInterval.Tests.FactoredSmallQDFT.imagUnit,
    decodeDisks, decodeDiskRows, decodeStages, decodeButterflies, decodeList,
    RawStageCertificate.decode, RawButterflyCertificate.decode,
    ComplexDisk.RawMulCertificate.decode,
    ComplexDisk.RawAddCertificate.decode, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold, negateDisk, width, halfLength,
    scheduledLeft, scheduledRight]

theorem decoded_stage0_accepted :
    decodedStage0.Accepted 0 decodedSample.certificate.input
      decodedSample.certificate.twiddleDisks := by
  refine ⟨rfl, by omega, ?_⟩
  intro index hindex
  have hindexLt : index < 4 := List.mem_range.mp hindex
  interval_cases index <;>
    norm_num [decodedStage0, decodedSample,
      DecodedCertificate.certificate, diskStateOfList, diskTableOfRows,
      diskAt, butterflyTable, fallbackButterfly, fallbackMul, fallbackAdd,
      fallbackDisk, SparkInterval.Tests.FactoredSmallQDFT.stage0Row0,
      SparkInterval.Tests.FactoredSmallQDFT.stage0Row1,
      SparkInterval.Tests.FactoredSmallQDFT.mkButterfly,
      SparkInterval.Tests.FactoredSmallQDFT.exactMul,
      SparkInterval.Tests.FactoredSmallQDFT.exactAdd,
      SparkInterval.Tests.FactoredSmallQDFT.exactProduct,
      SparkInterval.Tests.FactoredSmallQDFT.exactSum,
      SparkInterval.Tests.FactoredSmallQDFT.pointDisk,
      SparkInterval.Tests.FactoredSmallQDFT.one,
      StageCertificate.rowAt, ButterflyCertificate.WellFormed,
      groupAt, offsetAt, finIndex, scheduledLeft, scheduledRight,
      halfLength, width, negateDisk,
      ComplexDisk.MulCertificate.check,
      ComplexDisk.MulCertificate.WellFormed,
      ComplexDisk.AddCertificate.check,
      ComplexDisk.AddCertificate.WellFormed,
      ComplexDisk.productCenterErrorSq, ComplexDisk.sumCenterErrorSq,
      ComplexDisk.centerNormSq]

theorem decoded_stage1_accepted :
    decodedStage1.Accepted 1 (decodedStage0.output 0)
      decodedSample.certificate.twiddleDisks := by
  refine ⟨rfl, by omega, ?_⟩
  intro index hindex
  have hindexLt : index < 4 := List.mem_range.mp hindex
  interval_cases index <;>
    norm_num [decodedStage1, decodedStage0, decodedSample,
      DecodedCertificate.certificate, diskTableOfRows, diskAt,
      butterflyTable, fallbackButterfly, fallbackMul, fallbackAdd,
      fallbackDisk, StageCertificate.output, StageCertificate.rowAt,
      SparkInterval.Tests.FactoredSmallQDFT.stage0Row0,
      SparkInterval.Tests.FactoredSmallQDFT.stage0Row1,
      SparkInterval.Tests.FactoredSmallQDFT.stage1Row0,
      SparkInterval.Tests.FactoredSmallQDFT.stage1Row1,
      SparkInterval.Tests.FactoredSmallQDFT.mkButterfly,
      SparkInterval.Tests.FactoredSmallQDFT.exactMul,
      SparkInterval.Tests.FactoredSmallQDFT.exactAdd,
      SparkInterval.Tests.FactoredSmallQDFT.exactProduct,
      SparkInterval.Tests.FactoredSmallQDFT.exactSum,
      SparkInterval.Tests.FactoredSmallQDFT.pointDisk,
      SparkInterval.Tests.FactoredSmallQDFT.one,
      SparkInterval.Tests.FactoredSmallQDFT.imagUnit,
      ButterflyCertificate.WellFormed, isLeftOutput, groupAt, offsetAt,
      finIndex, scheduledLeft, scheduledRight, halfLength, width,
      negateDisk, ComplexDisk.MulCertificate.check,
      ComplexDisk.MulCertificate.WellFormed,
      ComplexDisk.AddCertificate.check,
      ComplexDisk.AddCertificate.WellFormed,
      ComplexDisk.productCenterErrorSq, ComplexDisk.sumCenterErrorSq,
      ComplexDisk.centerNormSq]

theorem decoded_certificate_check :
    decodedSample.certificate.check = true := by
  have hstage0 : decodedStage0.check 0 decodedSample.certificate.input
      decodedSample.certificate.twiddleDisks = true :=
    decide_eq_true decoded_stage0_accepted
  have hstage1 : decodedStage1.check 1 (decodedStage0.output 0)
      decodedSample.certificate.twiddleDisks = true :=
    decide_eq_true decoded_stage1_accepted
  have hlinked : checkLinkedStages
      decodedSample.certificate.twiddleDisks 0
      decodedSample.certificate.input decodedSample.certificate.stages =
        true := by
    rw [show decodedSample.certificate.stages =
      [decodedStage0, decodedStage1] by rfl]
    simp only [checkLinkedStages]
    rw [hstage0, hstage1]
    rfl
  unfold Certificate.check
  rw [hlinked]
  norm_num [decodedSample, DecodedCertificate.certificate]

theorem decoded_output_linked : decodedSample.OutputLinked := by
  intro frequency
  fin_cases frequency <;>
    norm_num [decodedSample, DecodedCertificate.OutputLinked,
      DecodedCertificate.claimedOutput, DecodedCertificate.certificate,
      Certificate.output, runStages, diskStateOfList, diskTableOfRows,
      diskAt, decodedStage0, decodedStage1, StageCertificate.output,
      StageCertificate.rowAt, butterflyTable, fallbackButterfly,
      SparkInterval.Tests.FactoredSmallQDFT.stage0Row0,
      SparkInterval.Tests.FactoredSmallQDFT.stage0Row1,
      SparkInterval.Tests.FactoredSmallQDFT.stage1Row0,
      SparkInterval.Tests.FactoredSmallQDFT.stage1Row1,
      SparkInterval.Tests.FactoredSmallQDFT.mkButterfly,
      SparkInterval.Tests.FactoredSmallQDFT.exactMul,
      SparkInterval.Tests.FactoredSmallQDFT.exactAdd,
      SparkInterval.Tests.FactoredSmallQDFT.exactProduct,
      SparkInterval.Tests.FactoredSmallQDFT.exactSum,
      SparkInterval.Tests.FactoredSmallQDFT.pointDisk,
      SparkInterval.Tests.FactoredSmallQDFT.one,
      SparkInterval.Tests.FactoredSmallQDFT.imagUnit,
      isLeftOutput, groupAt, offsetAt, halfLength, width, negateDisk]

theorem decoded_table_radii_nonnegative :
    decodedSample.TableRadiiNonnegative := by
  norm_num [DecodedCertificate.TableRadiiNonnegative, decodedSample,
    SparkInterval.Tests.FactoredSmallQDFT.pointDisk,
    SparkInterval.Tests.FactoredSmallQDFT.one,
    SparkInterval.Tests.FactoredSmallQDFT.imagUnit]

theorem sample_check : sample.check bounds = true := by
  have hbounds : sample.boundsCheck bounds = true := by
    norm_num [sample, bounds, rawStage0, rawStage1,
      RawCertificate.boundsCheck,
      RawCertificate.recordCount, lineLength]
  have hlink : decide decodedSample.OutputLinked = true :=
    decide_eq_true decoded_output_linked
  have hradii : decide decodedSample.TableRadiiNonnegative = true :=
    decide_eq_true decoded_table_radii_nonnegative
  simp [RawCertificate.check, hbounds, sample_decode,
    decoded_certificate_check, hlink, hradii]

theorem decoded_initial_contains :
    StateContains decodedSample.certificate.input
      SparkInterval.Tests.FactoredSmallQDFT.exactPreBitReversed := by
  intro index
  have h := SparkInterval.Tests.FactoredSmallQDFT.initial_contains index
  fin_cases index <;>
    simpa [decodedSample, DecodedCertificate.certificate, diskStateOfList,
      diskAt, SparkInterval.Tests.FactoredSmallQDFT.preBitReversed,
      SparkInterval.Tests.FactoredSmallQDFT.exactPreBitReversed] using h

theorem decoded_twiddles_contain :
    TwiddlesContain (logLength := 2)
      decodedSample.certificate.twiddleDisks
      SparkInterval.Tests.FactoredSmallQDFT.exactTwiddles := by
  intro stage hstage offset hoffset
  interval_cases stage
  · have hoffset' : offset = 0 := by
      norm_num [halfLength] at hoffset
      omega
    subst offset
    simpa [decodedSample, DecodedCertificate.certificate, diskTableOfRows,
      diskAt, SparkInterval.Tests.FactoredSmallQDFT.exactTwiddles,
      SparkInterval.Tests.FactoredSmallQDFT.one] using
      SparkInterval.Tests.FactoredSmallQDFT.pointDisk_contains 1 0
  · norm_num [halfLength] at hoffset
    interval_cases offset
    · simpa [decodedSample, DecodedCertificate.certificate,
        diskTableOfRows, diskAt,
        SparkInterval.Tests.FactoredSmallQDFT.exactTwiddles,
        SparkInterval.Tests.FactoredSmallQDFT.one] using
        SparkInterval.Tests.FactoredSmallQDFT.pointDisk_contains 1 0
    · simpa [decodedSample, DecodedCertificate.certificate,
        diskTableOfRows, diskAt,
        SparkInterval.Tests.FactoredSmallQDFT.exactTwiddles,
        SparkInterval.Tests.FactoredSmallQDFT.imagUnit] using
        SparkInterval.Tests.FactoredSmallQDFT.pointDisk_contains 0 1

/-- End-to-end length-four raw-word theorem: every literal output word is
linked to a disk enclosing the corresponding exact two-stage transform. -/
theorem sample_output_words_contain :
    ∀ frequency,
      ∃ rawDisk : ComplexDisk.Raw,
        sample.output[frequency.val]? = some rawDisk ∧
        rawDisk.decode = some
          (decodedSample.claimedOutput.value frequency) ∧
        (decodedSample.claimedOutput.value frequency).ContainsComplex
          ((runExactStages
            SparkInterval.Tests.FactoredSmallQDFT.exactTwiddles 2 0
            SparkInterval.Tests.FactoredSmallQDFT.exactPreBitReversed).value
              frequency) := by
  exact RawCertificate.output_words_contain_transform
    sample_check sample_decode decoded_initial_contains
      decoded_twiddles_contain

/-! Fail-closed cases cover every boundary added by the raw bridge. -/

def missingInput : RawCertificate 2 :=
  { sample with input := [rawOne, rawThree, rawTwo] }

theorem missing_input_fails_closed : missingInput.check bounds = false := by
  norm_num [missingInput, sample, bounds, RawCertificate.check,
    RawCertificate.boundsCheck, RawCertificate.recordCount,
    RawCertificate.decode, CanonicalShape, lineLength]

def nonfiniteInput : RawCertificate 2 :=
  { sample with input :=
      [⟨0x7ff0000000000000, 0, 0⟩, rawThree, rawTwo, rawFour] }

theorem nonfinite_input_fails_closed :
    nonfiniteInput.check bounds = false := by
  norm_num [nonfiniteInput, sample, bounds, rawStage0, rawStage1,
    RawCertificate.check, RawCertificate.boundsCheck,
    RawCertificate.recordCount, RawCertificate.decode, CanonicalShape,
    StageShape, lineLength, butterflyRowsPerStage, decodeDisks, decodeList,
    ComplexDisk.Raw.decode, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes]

def wrongOutputLink : RawCertificate 2 :=
  { sample with output :=
      [rawSix, rawNegativeTwoNegativeTwo, rawNegativeTwo,
        rawNegativeTwoPositiveTwo] }

theorem wrong_output_link_fails_closed :
    wrongOutputLink.check bounds = false := by
  let wrongDecoded : DecodedCertificate 2 :=
    { decodedSample with outputValues :=
        [SparkInterval.Tests.FactoredSmallQDFT.pointDisk 6 0,
          SparkInterval.Tests.FactoredSmallQDFT.pointDisk (-2) (-2),
          SparkInterval.Tests.FactoredSmallQDFT.pointDisk (-2) 0,
          SparkInterval.Tests.FactoredSmallQDFT.pointDisk (-2) 2] }
  have hshape : CanonicalShape (logLength := 2)
      wrongOutputLink.input wrongOutputLink.output
        wrongOutputLink.twiddleRows wrongOutputLink.stages := by
    refine ⟨rfl, rfl, rfl, rfl, ?_⟩
    intro stage hstage
    have hstageLt : stage < 2 := List.mem_range.mp hstage
    interval_cases stage <;>
      norm_num [wrongOutputLink, sample, rawStage0, rawStage1, StageShape,
        lineLength, butterflyRowsPerStage, halfLength]
  have hdecode : wrongOutputLink.decode = some wrongDecoded := by
    rw [RawCertificate.decode]
    simp only [if_pos hshape]
    norm_num [wrongOutputLink, sample, rawStage0, rawStage1,
      rawStage0Row0, rawStage0Row1, rawStage1Row0, rawStage1Row1,
      rawNegativeThree, rawNegativeFour, rawNegativeSix,
      rawNegativeTwoNegativeTwo, rawNegativeTwoPositiveTwo,
      rawNegativeTwoI, rawPositiveTwoI, rawImaginaryUnit, rawNegativeTwo,
      rawTen, rawSix, rawFour, rawThree, rawTwo, rawOne, rawExactMul,
      rawExactAdd, wrongDecoded, decodedSample, decodedStage0, decodedStage1,
      SparkInterval.Tests.FactoredSmallQDFT.stage0Row0,
      SparkInterval.Tests.FactoredSmallQDFT.stage0Row1,
      SparkInterval.Tests.FactoredSmallQDFT.stage1Row0,
      SparkInterval.Tests.FactoredSmallQDFT.stage1Row1,
      SparkInterval.Tests.FactoredSmallQDFT.mkButterfly,
      SparkInterval.Tests.FactoredSmallQDFT.exactMul,
      SparkInterval.Tests.FactoredSmallQDFT.exactAdd,
      SparkInterval.Tests.FactoredSmallQDFT.exactProduct,
      SparkInterval.Tests.FactoredSmallQDFT.exactSum,
      SparkInterval.Tests.FactoredSmallQDFT.pointDisk,
      SparkInterval.Tests.FactoredSmallQDFT.one,
      SparkInterval.Tests.FactoredSmallQDFT.imagUnit,
      decodeDisks, decodeDiskRows, decodeStages, decodeButterflies,
      decodeList, RawStageCertificate.decode,
      RawButterflyCertificate.decode, ComplexDisk.RawMulCertificate.decode,
      ComplexDisk.RawAddCertificate.decode, ComplexDisk.Raw.decode,
      Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
      Binary64.exponentModulus, Binary64.fractionModulus,
      Binary64.exponentAllOnes, Binary64.finiteValue,
      Binary64.fractionBits, Binary64.signBit, Binary64.signThreshold,
      negateDisk, width, halfLength, scheduledLeft, scheduledRight]
  have htyped : wrongDecoded.certificate.check = true := by
    have hcertificate : wrongDecoded.certificate =
        decodedSample.certificate := by
      rfl
    rw [hcertificate]
    exact decoded_certificate_check
  have hnotLinked : ¬ wrongDecoded.OutputLinked := by
    intro hlinked
    have hzero := hlinked (0 : Fin 4)
    norm_num [wrongDecoded, decodedSample,
      DecodedCertificate.OutputLinked, DecodedCertificate.claimedOutput,
      DecodedCertificate.certificate, Certificate.output, runStages,
      diskStateOfList, diskTableOfRows, diskAt, decodedStage0,
      decodedStage1, StageCertificate.output, StageCertificate.rowAt,
      butterflyTable, fallbackButterfly,
      SparkInterval.Tests.FactoredSmallQDFT.stage0Row0,
      SparkInterval.Tests.FactoredSmallQDFT.stage0Row1,
      SparkInterval.Tests.FactoredSmallQDFT.stage1Row0,
      SparkInterval.Tests.FactoredSmallQDFT.stage1Row1,
      SparkInterval.Tests.FactoredSmallQDFT.mkButterfly,
      SparkInterval.Tests.FactoredSmallQDFT.exactMul,
      SparkInterval.Tests.FactoredSmallQDFT.exactAdd,
      SparkInterval.Tests.FactoredSmallQDFT.exactProduct,
      SparkInterval.Tests.FactoredSmallQDFT.exactSum,
      SparkInterval.Tests.FactoredSmallQDFT.pointDisk,
      SparkInterval.Tests.FactoredSmallQDFT.one,
      SparkInterval.Tests.FactoredSmallQDFT.imagUnit,
      isLeftOutput, groupAt, offsetAt, halfLength, width, negateDisk] at hzero
  have hbounds : wrongOutputLink.boundsCheck bounds = true := by
    norm_num [wrongOutputLink, sample, bounds, rawStage0, rawStage1,
      RawCertificate.boundsCheck,
      RawCertificate.recordCount, lineLength]
  have hlink : decide wrongDecoded.OutputLinked = false :=
    decide_eq_false hnotLinked
  simp [RawCertificate.check, hbounds, hdecode, htyped, hlink]

def rawNegativeRadius : ComplexDisk.Raw :=
  ⟨0x0000000000000000, 0x0000000000000000,
    0xbff0000000000000⟩

/-- With no stages, the typed transform checker and the output-link equality
alone cannot constrain a disk radius.  The explicit raw table-radius guard
must reject this otherwise linked fixture. -/
def negativeRadiusAtLogZero : RawCertificate 0 := {
  input := [rawNegativeRadius]
  twiddleRows := []
  stages := []
  output := [rawNegativeRadius]
}

def logZeroBounds : Bounds := ⟨0, 1, 2⟩

theorem negative_radius_at_log_zero_fails_closed :
    negativeRadiusAtLogZero.check logZeroBounds = false := by
  norm_num [negativeRadiusAtLogZero, rawNegativeRadius, logZeroBounds,
    RawCertificate.check, RawCertificate.boundsCheck,
    RawCertificate.recordCount, RawCertificate.decode, CanonicalShape,
    lineLength, decodeDisks, decodeDiskRows, decodeStages, decodeList,
    ComplexDisk.Raw.decode, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold, DecodedCertificate.certificate,
    DecodedCertificate.OutputLinked,
    DecodedCertificate.TableRadiiNonnegative,
    DecodedCertificate.claimedOutput, diskStateOfList, diskAt,
    Certificate.check, Certificate.output, checkLinkedStages, runStages]

def shortBounds : Bounds := ⟨1, 4, 15⟩

theorem log_bound_fails_closed : sample.check shortBounds = false := by
  norm_num [sample, shortBounds, RawCertificate.check,
    RawCertificate.boundsCheck]

#print axioms RawCertificate.checker_sound
#print axioms RawCertificate.boundsCheck_sound
#print axioms RawCertificate.output_word_decodes
#print axioms RawCertificate.decoded_output_contains_transform
#print axioms RawCertificate.output_words_contain_transform
#print axioms RawCertificate.output_words_contain_positiveDFT_unconditional
#print axioms sample_check
#print axioms sample_output_words_contain
#print axioms missing_input_fails_closed
#print axioms nonfinite_input_fails_closed
#print axioms wrong_output_link_fails_closed
#print axioms negative_radius_at_log_zero_fails_closed
#print axioms log_bound_fails_closed

end SparkInterval.Tests.FactoredSmallQRawDFT
