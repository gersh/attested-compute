/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawSumCampaign

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQRawGaussianSum

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQTrace
open SparkInterval.Dirichlet.FactoredSmallQRawTrace
open SparkInterval.Dirichlet.FactoredSmallQGaussianSum
open SparkInterval.Dirichlet.FactoredSmallQRawGaussianSum

def realDisk (x : ℚ) : ComplexDisk := ⟨x, 0, 0⟩

theorem realDisk_contains (x : ℚ) :
    (realDisk x).ContainsComplex (x : ℂ) := by
  unfold ComplexDisk.ContainsComplex
  have hcenter : (realDisk x).center = (x : ℂ) := by
    apply Complex.ext <;> norm_num [realDisk, ComplexDisk.center]
  rw [hcenter]
  simp [realDisk]

def exactMul (left right : ℚ) : ComplexDisk.MulCertificate := {
  left := realDisk left
  right := realDisk right
  output := realDisk (left * right)
  centerErrorBound := 0
  leftCenterNormBound := left
  rightCenterNormBound := right
}

def exactAdd (left right : ℚ) : ComplexDisk.AddCertificate := {
  left := realDisk left
  right := realDisk right
  output := realDisk (left + right)
  centerErrorBound := 0
}

def typedSeed : TraceCertificate := {
  base := realDisk 2
  square := exactMul 2 2
  cube := exactMul 4 2
  steps := []
}

def typedAdvance : StepCertificate :=
  ⟨exactMul 2 8, exactMul 8 4⟩

def typedRowOne : RowCertificate := {
  ordinal := 1
  character := realDisk 3
  characterTimesZ := exactMul 3 2
  oddScale := none
  addToSum := exactAdd 0 6
  advance := some typedAdvance
}

def typedRowTwo : RowCertificate := {
  ordinal := 2
  character := realDisk 5
  characterTimesZ := exactMul 5 16
  oddScale := none
  addToSum := exactAdd 6 80
  advance := none
}

def typedSample : SumTraceCertificate := {
  oddParity := false
  truncation := 2
  seed := typedSeed
  initialSum := zeroDisk
  rows := [typedRowOne, typedRowTwo]
}

def rawZero : ComplexDisk.Raw :=
  ⟨0x0000000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawTwo : ComplexDisk.Raw :=
  ⟨0x4000000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawThree : ComplexDisk.Raw :=
  ⟨0x4008000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawFour : ComplexDisk.Raw :=
  ⟨0x4010000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawFive : ComplexDisk.Raw :=
  ⟨0x4014000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawSix : ComplexDisk.Raw :=
  ⟨0x4018000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawEight : ComplexDisk.Raw :=
  ⟨0x4020000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawSixteen : ComplexDisk.Raw :=
  ⟨0x4030000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawThirtyTwo : ComplexDisk.Raw :=
  ⟨0x4040000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawEighty : ComplexDisk.Raw :=
  ⟨0x4054000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawEightySix : ComplexDisk.Raw :=
  ⟨0x4055800000000000, 0x0000000000000000, 0x0000000000000000⟩

def rawExactMul (left right output : ComplexDisk.Raw)
    (leftNormBits rightNormBits : ℕ) :
    ComplexDisk.RawMulCertificate := {
  left, right, output
  centerErrorBoundBits := 0x0000000000000000
  leftCenterNormBoundBits := leftNormBits
  rightCenterNormBoundBits := rightNormBits
}

def rawExactAdd (left right output : ComplexDisk.Raw) :
    ComplexDisk.RawAddCertificate := {
  left, right, output
  centerErrorBoundBits := 0x0000000000000000
}

def rawSeed : RawTraceCertificate := {
  base := rawTwo
  square := rawExactMul rawTwo rawTwo rawFour
    0x4000000000000000 0x4000000000000000
  cube := rawExactMul rawFour rawTwo rawEight
    0x4010000000000000 0x4000000000000000
  steps := []
}

def rawAdvance : RawStepCertificate :=
  ⟨rawExactMul rawTwo rawEight rawSixteen
      0x4000000000000000 0x4020000000000000,
    rawExactMul rawEight rawFour rawThirtyTwo
      0x4020000000000000 0x4010000000000000⟩

def rawRowOne : RawRowCertificate := {
  ordinal := 1
  character := rawThree
  characterTimesZ := rawExactMul rawThree rawTwo rawSix
    0x4008000000000000 0x4000000000000000
  oddScale := none
  addToSum := rawExactAdd rawZero rawSix rawSix
  advance := some rawAdvance
}

def rawRowTwo : RawRowCertificate := {
  ordinal := 2
  character := rawFive
  characterTimesZ := rawExactMul rawFive rawSixteen rawEighty
    0x4014000000000000 0x4030000000000000
  oddScale := none
  addToSum := rawExactAdd rawSix rawEighty rawEightySix
  advance := none
}

/-- Nontrivial exact fixture: `3 * 2^(1^2) + 5 * 2^(2^2) = 86`. -/
def rawSample : RawSumTraceCertificate := {
  oddParity := false
  truncation := 2
  seed := rawSeed
  initialSum := rawZero
  rows := [rawRowOne, rawRowTwo]
}

theorem rawSample_decode : rawSample.decode = some typedSample := by
  norm_num [rawSample, rawRowOne, rawRowTwo, rawAdvance, rawSeed,
    typedSample, typedRowOne, typedRowTwo, typedAdvance, typedSeed,
    rawExactMul, rawExactAdd, exactMul, exactAdd, realDisk, zeroDisk,
    rawZero, rawTwo, rawThree, rawFour, rawFive, rawSix, rawEight,
    rawSixteen, rawThirtyTwo, rawEighty, rawEightySix,
    RawSumTraceCertificate.decode, decodeRows, RawRowCertificate.decode,
    decodeOptionalMul, decodeOptionalStep, RawTraceCertificate.decode,
    SparkInterval.Dirichlet.FactoredSmallQRawTrace.decodeSteps,
    RawStepCertificate.decode, ComplexDisk.RawMulCertificate.decode,
    ComplexDisk.RawAddCertificate.decode, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem typedSample_check : typedSample.check 2 = true := by
  norm_num [typedSample, typedRowOne, typedRowTwo, typedAdvance, typedSeed,
    exactMul, exactAdd, realDisk, zeroDisk, ordinalDisk,
    SumTraceCertificate.check, SumTraceCertificate.initialState,
    checkRows, RowCertificate.checkCore, RowCertificate.CoreWellFormed,
    RowCertificate.WeightWellFormed, RowCertificate.weightedOutput,
    TraceCertificate.check, TraceCertificate.InitialWellFormed,
    TraceCertificate.initialState, Linked, checkLinked,
    StepCertificate.check, StepCertificate.WellFormed,
    StepCertificate.output, ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.AddCertificate.check, ComplexDisk.AddCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.sumCenterErrorSq,
    ComplexDisk.centerNormSq]

theorem rawSample_check : rawSample.check 2 = true := by
  rw [RawSumTraceCertificate.check]
  have hbound : decide (rawSample.rows.length ≤ 2) = true := by
    norm_num [rawSample]
  rw [hbound]
  simp only [Bool.true_and]
  rw [rawSample_decode]
  exact typedSample_check

theorem rawTwo_decode : rawTwo.decode = some (realDisk 2) := by
  norm_num [rawTwo, realDisk, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem rawThree_decode : rawThree.decode = some (realDisk 3) := by
  norm_num [rawThree, realDisk, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem rawFive_decode : rawFive.decode = some (realDisk 5) := by
  norm_num [rawFive, realDisk, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem raw_characters :
    RawContainsCharacters rawSample.rows [(3 : ℂ), (5 : ℂ)] := by
  simp only [RawContainsCharacters, rawSample, rawRowOne, rawRowTwo]
  exact List.Forall₂.cons ⟨realDisk 3, rawThree_decode,
      realDisk_contains 3⟩
    (List.Forall₂.cons ⟨realDisk 5, rawFive_decode,
      realDisk_contains 5⟩ List.Forall₂.nil)

example :
    ∃ certificate : SumTraceCertificate,
      rawSample.decode = some certificate ∧
      [(3 : ℂ), (5 : ℂ)].length = rawSample.truncation ∧
      certificate.output.ContainsComplex (86 : ℂ) := by
  have h :=
    RawSumTraceCertificate.accepted_output_contains_exact_finite_sum_of_base_decode
      rawSample_check rawTwo_decode (realDisk_contains 2) raw_characters
  rcases h with ⟨certificate, hdecode, hlength, hcontains⟩
  refine ⟨certificate, hdecode, hlength, ?_⟩
  norm_num [rawSample, exactFiniteSum, exactSumFrom, exactTerm] at hcontains
  exact hcontains

/-! A mathematically valid addition witness with the wrong left state is
rejected by the typed link checker after exact decoding. -/

def rawTamperedRowTwo : RawRowCertificate := {
  rawRowTwo with addToSum := rawExactAdd rawZero rawEighty rawEighty
}

def rawTampered : RawSumTraceCertificate :=
  { rawSample with rows := [rawRowOne, rawTamperedRowTwo] }

theorem raw_tampered_link_fails_closed : rawTampered.check 2 = false := by
  norm_num [rawTampered, rawTamperedRowTwo, rawSample, rawRowOne, rawRowTwo,
    rawAdvance, rawSeed, rawExactMul, rawExactAdd, rawZero, rawTwo,
    rawThree, rawFour, rawFive, rawSix, rawEight, rawSixteen,
    rawThirtyTwo, rawEighty, rawEightySix,
    RawSumTraceCertificate.check, RawSumTraceCertificate.decode, decodeRows,
    RawRowCertificate.decode, decodeOptionalMul, decodeOptionalStep,
    RawTraceCertificate.decode,
    SparkInterval.Dirichlet.FactoredSmallQRawTrace.decodeSteps,
    RawStepCertificate.decode, ComplexDisk.RawMulCertificate.decode,
    ComplexDisk.RawAddCertificate.decode, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold,
    SumTraceCertificate.check, SumTraceCertificate.initialState, checkRows,
    RowCertificate.checkCore, RowCertificate.CoreWellFormed,
    RowCertificate.WeightWellFormed, RowCertificate.weightedOutput,
    TraceCertificate.check, TraceCertificate.InitialWellFormed,
    TraceCertificate.initialState, Linked, checkLinked,
    StepCertificate.check, StepCertificate.WellFormed,
    StepCertificate.output, ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.AddCertificate.check, ComplexDisk.AddCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.sumCenterErrorSq,
    ComplexDisk.centerNormSq]

def rawInfinity : ComplexDisk.Raw :=
  ⟨0x7ff0000000000000, 0x0000000000000000, 0x0000000000000000⟩

def rawNonfinite : RawSumTraceCertificate :=
  { rawSample with
    rows := [{ rawRowOne with character := rawInfinity }, rawRowTwo] }

theorem raw_nonfinite_fails_closed : rawNonfinite.check 2 = false := by
  norm_num [rawNonfinite, rawInfinity, rawSample, rawRowOne, rawRowTwo,
    RawSumTraceCertificate.check, RawSumTraceCertificate.decode, decodeRows,
    RawRowCertificate.decode, ComplexDisk.Raw.decode, Binary64.decodeFinite,
    Binary64.wordLimit, Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes]

def rawWrongCount : RawSumTraceCertificate :=
  { rawSample with truncation := 3 }

theorem raw_wrong_count_fails_closed : rawWrongCount.check 3 = false := by
  rw [RawSumTraceCertificate.check]
  have hbound : decide (rawWrongCount.rows.length ≤ 3) = true := by
    norm_num [rawWrongCount, rawSample]
  rw [hbound]
  simp only [Bool.true_and]
  have hdecode : rawWrongCount.decode =
      some { typedSample with truncation := 3 } := by
    norm_num [rawWrongCount, rawSample, rawRowOne, rawRowTwo, rawAdvance,
      rawSeed, typedSample, typedRowOne, typedRowTwo, typedAdvance,
      typedSeed, rawExactMul, rawExactAdd, exactMul, exactAdd, realDisk,
      zeroDisk, rawZero, rawTwo, rawThree, rawFour, rawFive, rawSix,
      rawEight, rawSixteen, rawThirtyTwo, rawEighty, rawEightySix,
      RawSumTraceCertificate.decode, decodeRows, RawRowCertificate.decode,
      decodeOptionalMul, decodeOptionalStep, RawTraceCertificate.decode,
      SparkInterval.Dirichlet.FactoredSmallQRawTrace.decodeSteps,
      RawStepCertificate.decode, ComplexDisk.RawMulCertificate.decode,
      ComplexDisk.RawAddCertificate.decode, ComplexDisk.Raw.decode,
      Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
      Binary64.exponentModulus, Binary64.fractionModulus,
      Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
      Binary64.signBit, Binary64.signThreshold]
  rw [hdecode]
  norm_num [SumTraceCertificate.check, typedSample]

theorem raw_over_bound_fails_before_decode : rawSample.check 1 = false := by
  norm_num [RawSumTraceCertificate.check, rawSample]

#print axioms decodeRows_length
#print axioms decodeRows_containsCharacters
#print axioms RawSumTraceCertificate.rows_length_eq
#print axioms RawSumTraceCertificate.checker_sound
#print axioms RawSumTraceCertificate.decoded_output_contains_exact_finite_sum
#print axioms RawSumTraceCertificate.accepted_output_contains_exact_finite_sum_of_base_decode
#print axioms rawSample_check
#print axioms raw_tampered_link_fails_closed
#print axioms raw_nonfinite_fails_closed
#print axioms raw_wrong_count_fails_closed
#print axioms raw_over_bound_fails_before_decode
#print axioms SparkInterval.Dirichlet.FactoredSmallQRawSumCampaign.checker_sound
#print axioms SparkInterval.Dirichlet.FactoredSmallQRawSumCampaign.requested_output_contains_exact_finite_sum

end SparkInterval.Tests.FactoredSmallQRawGaussianSum
