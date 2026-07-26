/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQGaussianSum

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQGaussianSum

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQTrace
open SparkInterval.Dirichlet.FactoredSmallQGaussianSum

def realDisk (x : ℚ) : ComplexDisk := ⟨x, 0, 0⟩

theorem realDisk_contains (x : ℚ) :
    (realDisk x).ContainsComplex (x : ℂ) := by
  unfold ComplexDisk.ContainsComplex
  have hcenter : (realDisk x).center = (x : ℂ) := by
    apply Complex.ext <;>
      norm_num [realDisk, ComplexDisk.center]
  rw [hcenter]
  simp [realDisk]

/-- Exact witness for multiplication of two nonnegative real point disks. -/
def exactMul (left right : ℚ) : ComplexDisk.MulCertificate := {
  left := realDisk left
  right := realDisk right
  output := realDisk (left * right)
  centerErrorBound := 0
  leftCenterNormBound := left
  rightCenterNormBound := right
}

/-- Exact witness for addition of two real point disks. -/
def exactAdd (left right : ℚ) : ComplexDisk.AddCertificate := {
  left := realDisk left
  right := realDisk right
  output := realDisk (left + right)
  centerErrorBound := 0
}

/-- `w = 2`: square `4`, initial ratio `8`, and no pre-applied steps. -/
def seed : TraceCertificate := {
  base := realDisk 2
  square := exactMul 2 2
  cube := exactMul 4 2
  steps := []
}

def advanceAfterOne : StepCertificate :=
  ⟨exactMul 2 8, exactMul 8 4⟩

/-- Even row one: `3 * 2^(1^2) = 6`. -/
def evenRowOne : RowCertificate := {
  ordinal := 1
  character := realDisk 3
  characterTimesZ := exactMul 3 2
  oddScale := none
  addToSum := exactAdd 0 6
  advance := some advanceAfterOne
}

/-- Even row two: `5 * 2^(2^2) = 80`. -/
def evenRowTwo : RowCertificate := {
  ordinal := 2
  character := realDisk 5
  characterTimesZ := exactMul 5 16
  oddScale := none
  addToSum := exactAdd 6 80
  advance := none
}

def evenSample : SumTraceCertificate := {
  oddParity := false
  truncation := 2
  seed := seed
  initialSum := zeroDisk
  rows := [evenRowOne, evenRowTwo]
}

theorem even_sample_check : evenSample.check 2 = true := by
  norm_num [evenSample, evenRowOne, evenRowTwo, advanceAfterOne, seed,
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

theorem even_characters :
    ContainsCharacters evenSample.rows [(3 : ℂ), (5 : ℂ)] := by
  simpa [ContainsCharacters, evenSample, evenRowOne, evenRowTwo] using
    (show (realDisk 3).ContainsComplex (3 : ℂ) ∧
        (realDisk 5).ContainsComplex (5 : ℂ) from
      ⟨realDisk_contains 3, realDisk_contains 5⟩)

/-- The nontrivial base detects a mistaken linear exponent recurrence:
`3*2 + 5*16 = 86`. -/
example : evenSample.output.ContainsComplex (86 : ℂ) := by
  have h := (SumTraceCertificate.output_contains_exact_finite_sum
    even_sample_check (realDisk_contains 2) even_characters).2
  norm_num [evenSample, exactFiniteSum, exactSumFrom, exactTerm] at h
  exact h

/-- Odd rows add the exact factor `n`: the second term is `2*5*16`. -/
def oddRowOne : RowCertificate := {
  evenRowOne with
  oddScale := some (exactMul 6 1)
}

def oddRowTwo : RowCertificate := {
  ordinal := 2
  character := realDisk 5
  characterTimesZ := exactMul 5 16
  oddScale := some (exactMul 80 2)
  addToSum := exactAdd 6 160
  advance := none
}

def oddSample : SumTraceCertificate := {
  oddParity := true
  truncation := 2
  seed := seed
  initialSum := zeroDisk
  rows := [oddRowOne, oddRowTwo]
}

theorem odd_sample_check : oddSample.check 2 = true := by
  norm_num [oddSample, oddRowOne, oddRowTwo, evenRowOne, advanceAfterOne,
    seed, exactMul, exactAdd, realDisk, zeroDisk, ordinalDisk,
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

theorem odd_characters :
    ContainsCharacters oddSample.rows [(3 : ℂ), (5 : ℂ)] := by
  simpa [ContainsCharacters, oddSample, oddRowOne, oddRowTwo, evenRowOne] using
    (show (realDisk 3).ContainsComplex (3 : ℂ) ∧
        (realDisk 5).ContainsComplex (5 : ℂ) from
      ⟨realDisk_contains 3, realDisk_contains 5⟩)

example : oddSample.output.ContainsComplex (166 : ℂ) := by
  have h := (SumTraceCertificate.output_contains_exact_finite_sum
    odd_sample_check (realDisk_contains 2) odd_characters).2
  norm_num [oddSample, exactFiniteSum, exactSumFrom, exactTerm] at h
  exact h

/-- Exact row ordinals are checked, not inferred from list length alone. -/
def wrongOrdinal : SumTraceCertificate :=
  { evenSample with
    rows := [evenRowOne, { evenRowTwo with ordinal := 3 }] }

theorem wrong_ordinal_fails_closed : wrongOrdinal.check 2 = false := by
  norm_num [wrongOrdinal, evenSample, evenRowOne, evenRowTwo,
    advanceAfterOne, seed, exactMul, exactAdd, realDisk, zeroDisk, ordinalDisk,
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

/-- A two-row prefix cannot claim a three-term truncation. -/
def wrongTruncation : SumTraceCertificate :=
  { evenSample with truncation := 3 }

theorem wrong_truncation_fails_closed : wrongTruncation.check 3 = false := by
  norm_num [wrongTruncation, evenSample, SumTraceCertificate.check]

/-- Odd parity cannot omit the exact ordinal multiplication. -/
def missingOddScale : SumTraceCertificate :=
  { oddSample with rows := [evenRowOne, oddRowTwo] }

theorem missing_odd_scale_fails_closed : missingOddScale.check 2 = false := by
  norm_num [missingOddScale, oddSample, evenRowOne, oddRowTwo,
    advanceAfterOne, seed, exactMul, exactAdd, realDisk, zeroDisk, ordinalDisk,
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

/-- A recurrence transition is mandatory between two rows. -/
def missingAdvance : SumTraceCertificate :=
  { evenSample with rows := [{ evenRowOne with advance := none }, evenRowTwo] }

theorem missing_advance_fails_closed : missingAdvance.check 2 = false := by
  norm_num [missingAdvance, evenSample, evenRowOne, evenRowTwo,
    advanceAfterOne, seed, exactMul, exactAdd, realDisk, zeroDisk, ordinalDisk,
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

#print axioms RowCertificate.checkCore_sound
#print axioms RowCertificate.output_contains_term
#print axioms checkRows_sound
#print axioms runRows_contains_sum
#print axioms SumTraceCertificate.checker_sound
#print axioms SumTraceCertificate.output_contains_exact_finite_sum
#print axioms even_sample_check
#print axioms odd_sample_check
#print axioms wrong_ordinal_fails_closed
#print axioms wrong_truncation_fails_closed
#print axioms missing_odd_scale_fails_closed
#print axioms missing_advance_fails_closed

end SparkInterval.Tests.FactoredSmallQGaussianSum
