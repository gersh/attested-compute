/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQPostprocess

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQPostprocess

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQTrace
open SparkInterval.Dirichlet.FactoredSmallQGaussianSum
open SparkInterval.Dirichlet.FactoredSmallQPostprocess

def pointValue (re im : ℚ) : ℂ :=
  ⟨(re : ℝ), (im : ℝ)⟩

def pointDisk (re im : ℚ) : ComplexDisk :=
  ⟨re, im, 0⟩

def realDisk (value : ℚ) : ComplexDisk :=
  pointDisk value 0

theorem pointDisk_contains (re im : ℚ) :
    (pointDisk re im).ContainsComplex (pointValue re im) := by
  unfold ComplexDisk.ContainsComplex
  have hcenter : (pointDisk re im).center = pointValue re im := by
    apply Complex.ext <;>
      norm_num [pointDisk, pointValue, ComplexDisk.center]
  rw [hcenter]
  simp [pointDisk]

theorem realDisk_contains (value : ℚ) :
    (realDisk value).ContainsComplex (value : ℂ) := by
  have hvalue : pointValue value 0 = (value : ℂ) := by
    apply Complex.ext <;>
      norm_num [pointValue]
  rw [← hvalue]
  exact pointDisk_contains value 0

/-- Exact witness for multiplication of nonnegative real point disks. -/
def exactRealMul (left right : ℚ) : ComplexDisk.MulCertificate := {
  left := realDisk left
  right := realDisk right
  output := realDisk (left * right)
  centerErrorBound := 0
  leftCenterNormBound := left
  rightCenterNormBound := right
}

def exactRealAdd (left right : ℚ) : ComplexDisk.AddCertificate := {
  left := realDisk left
  right := realDisk right
  output := realDisk (left + right)
  centerErrorBound := 0
}

/-- One checked Gaussian row gives the exact finite sum `3 * 2 = 6`. -/
def seed : TraceCertificate := {
  base := realDisk 2
  square := exactRealMul 2 2
  cube := exactRealMul 4 2
  steps := []
}

def row : RowCertificate := {
  ordinal := 1
  character := realDisk 3
  characterTimesZ := exactRealMul 3 2
  oddScale := none
  addToSum := exactRealAdd 0 6
  advance := none
}

def finiteSum : SumTraceCertificate := {
  oddParity := false
  truncation := 1
  seed := seed
  initialSum := zeroDisk
  rows := [row]
}

/-- `(1 + i) * 6 = 6 + 6i`, with deliberately loose but valid centre-norm
bounds. -/
def prefactorTimesSum : ComplexDisk.MulCertificate := {
  left := pointDisk 1 1
  right := realDisk 6
  output := pointDisk 6 6
  centerErrorBound := 0
  leftCenterNormBound := 2
  rightCenterNormBound := 6
}

/-- The negative-frequency branch conjugates `6 + 6i`, then an upward radius
update encloses a tail of norm at most `1/2`. -/
def negativeSample : Certificate := {
  finiteSum := finiteSum
  prefactor := pointDisk 1 1
  prefactorTimesSum := prefactorTimesSum
  negativeFrequency := true
  tailInflation := {
    input := pointDisk 6 (-6)
    tailBound := 1 / 2
    output := ⟨6, -6, 1 / 2⟩
  }
}

theorem negative_sample_check : negativeSample.check 1 = true := by
  norm_num [negativeSample, finiteSum, row, seed, prefactorTimesSum,
    exactRealMul, exactRealAdd, realDisk, pointDisk, zeroDisk, ordinalDisk,
    Certificate.check, Certificate.Accepted,
    TailInflationCertificate.check, TailInflationCertificate.WellFormed,
    applyFrequencySign, conjugateDisk,
    SumTraceCertificate.check, SumTraceCertificate.initialState,
    SumTraceCertificate.output, runRows,
    checkRows, RowCertificate.checkCore, RowCertificate.CoreWellFormed,
    RowCertificate.WeightWellFormed, RowCertificate.weightedOutput,
    TraceCertificate.check, TraceCertificate.InitialWellFormed,
    TraceCertificate.initialState, Linked, checkLinked,
    ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.AddCertificate.check,
    ComplexDisk.AddCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.sumCenterErrorSq,
    ComplexDisk.centerNormSq]

theorem sample_characters :
    ContainsCharacters negativeSample.finiteSum.rows [(3 : ℂ)] := by
  simpa [ContainsCharacters, negativeSample, finiteSum, row] using
    (show (realDisk 3).ContainsComplex (3 : ℂ) from realDisk_contains 3)

theorem quarter_tail :
    ‖(1 / 4 : ℂ)‖ ≤
      (negativeSample.tailInflation.tailBound : ℝ) := by
  norm_num [negativeSample]

/-- A non-real prefactor, negative-frequency branch, and nonzero tail all
participate in this application of the composed theorem. -/
theorem negative_sample_contains :
    negativeSample.output.ContainsComplex (pointValue (25 / 4) (-6)) := by
  have h := (Certificate.output_contains_exact_finite_sum
    negative_sample_check (realDisk_contains 2) sample_characters
    (pointDisk_contains 1 1) quarter_tail).2
  change negativeSample.output.ContainsComplex
    (applyFrequencySignValue true
        (pointValue 1 1 * exactFiniteSum false (2 : ℂ) [(3 : ℂ)]) +
      (1 / 4 : ℂ)) at h
  have hexact :
      applyFrequencySignValue true
          (pointValue 1 1 * exactFiniteSum false (2 : ℂ) [(3 : ℂ)]) +
          (1 / 4 : ℂ) = pointValue (25 / 4) (-6) := by
    apply Complex.ext <;>
      norm_num [applyFrequencySignValue, exactFiniteSum, exactSumFrom,
        exactTerm, pointValue, Complex.mul_re, Complex.mul_im]
  rw [hexact] at h
  exact h

/-- The sign link is checked: an unconjugated intermediate cannot be used for
a negative frequency, even though its disk is individually well formed. -/
def missingConjugation : Certificate := {
  negativeSample with
  tailInflation := {
    input := pointDisk 6 6
    tailBound := 1 / 2
    output := ⟨6, 6, 1 / 2⟩
  }
}

theorem missing_conjugation_fails_closed :
    missingConjugation.check 1 = false := by
  norm_num [missingConjugation, negativeSample, finiteSum, row, seed,
    prefactorTimesSum, exactRealMul, exactRealAdd, realDisk, pointDisk,
    zeroDisk, ordinalDisk, Certificate.check, Certificate.Accepted,
    TailInflationCertificate.check, TailInflationCertificate.WellFormed,
    applyFrequencySign, conjugateDisk,
    SumTraceCertificate.check, SumTraceCertificate.initialState,
    checkRows, RowCertificate.checkCore, RowCertificate.CoreWellFormed,
    RowCertificate.WeightWellFormed, RowCertificate.weightedOutput,
    TraceCertificate.check, TraceCertificate.InitialWellFormed,
    TraceCertificate.initialState, Linked, checkLinked,
    ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.AddCertificate.check,
    ComplexDisk.AddCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.sumCenterErrorSq,
    ComplexDisk.centerNormSq]

/-- An internally valid multiplication witness cannot be relabelled as a
different prefactor. -/
def wrongPrefactorLink : Certificate :=
  { negativeSample with prefactor := pointDisk 2 0 }

theorem wrong_prefactor_link_fails_closed :
    wrongPrefactorLink.check 1 = false := by
  norm_num [wrongPrefactorLink, negativeSample, finiteSum, row, seed,
    prefactorTimesSum, exactRealMul, exactRealAdd, realDisk, pointDisk,
    zeroDisk, ordinalDisk, Certificate.check, Certificate.Accepted,
    TailInflationCertificate.check, TailInflationCertificate.WellFormed,
    applyFrequencySign, conjugateDisk,
    SumTraceCertificate.check, SumTraceCertificate.initialState,
    checkRows, RowCertificate.checkCore, RowCertificate.CoreWellFormed,
    RowCertificate.WeightWellFormed, RowCertificate.weightedOutput,
    TraceCertificate.check, TraceCertificate.InitialWellFormed,
    TraceCertificate.initialState, Linked, checkLinked,
    ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.AddCertificate.check,
    ComplexDisk.AddCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.sumCenterErrorSq,
    ComplexDisk.centerNormSq]

/-- A radius smaller than `input.radius + tailBound` is rejected. -/
def understatedTail : Certificate := {
  negativeSample with
  tailInflation := {
    input := pointDisk 6 (-6)
    tailBound := 1 / 2
    output := ⟨6, -6, 1 / 4⟩
  }
}

theorem understated_tail_fails_closed : understatedTail.check 1 = false := by
  norm_num [understatedTail, negativeSample, finiteSum, row, seed,
    prefactorTimesSum, exactRealMul, exactRealAdd, realDisk, pointDisk,
    zeroDisk, ordinalDisk, Certificate.check, Certificate.Accepted,
    TailInflationCertificate.check, TailInflationCertificate.WellFormed,
    applyFrequencySign, conjugateDisk,
    SumTraceCertificate.check, SumTraceCertificate.initialState,
    checkRows, RowCertificate.checkCore, RowCertificate.CoreWellFormed,
    RowCertificate.WeightWellFormed, RowCertificate.weightedOutput,
    TraceCertificate.check, TraceCertificate.InitialWellFormed,
    TraceCertificate.initialState, Linked, checkLinked,
    ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.AddCertificate.check,
    ComplexDisk.AddCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.sumCenterErrorSq,
    ComplexDisk.centerNormSq]

/-- A negative purported analytic bound is rejected independently of the
chosen output disk. -/
def negativeTail : TailInflationCertificate := {
  input := pointDisk 6 (-6)
  tailBound := -1 / 2
  output := pointDisk 6 (-6)
}

theorem negative_tail_fails_closed : negativeTail.check = false := by
  norm_num [negativeTail, pointDisk, TailInflationCertificate.check,
    TailInflationCertificate.WellFormed]

#print axioms conjugateDisk_contains
#print axioms applyFrequencySign_contains
#print axioms TailInflationCertificate.check_sound
#print axioms TailInflationCertificate.output_contains_add_tail
#print axioms Certificate.checker_sound
#print axioms Certificate.output_contains_from_finite_sum
#print axioms Certificate.output_contains_exact_finite_sum
#print axioms negative_sample_check
#print axioms negative_sample_contains
#print axioms missing_conjugation_fails_closed
#print axioms wrong_prefactor_link_fails_closed
#print axioms understated_tail_fails_closed
#print axioms negative_tail_fails_closed

end SparkInterval.Tests.FactoredSmallQPostprocess
