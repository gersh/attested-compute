/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.Factor8Postprocess

set_option autoImplicit false

namespace SparkInterval.Tests.Factor8PostprocessTest

open SparkInterval.Certificate
open SparkInterval.Dirichlet.Factor8Postprocess

private def row (fine slot : ℕ) : Row :=
  { sourceIndex := expectedSourceIndex fine slot
    coefficientIndex := expectedCoefficientIndex fine slot
    sample := RatInterval.point 1
    coefficient := RatInterval.point 1
    term := RatInterval.point 1 }

private def rowsFrom (fine slot : ℕ) : ℕ → List Row
  | 0 => []
  | count + 1 => row fine slot :: rowsFrom fine (slot + 1) count

private def rows : List Row := rowsFrom 81 0 tapCount

private def validCertificate : Certificate :=
  { fineIndex := 81
    interpolationError := sourceInterpolationError
    rows := rows
    finiteSum := evaluateRows rows
    output := widen sourceInterpolationError (evaluateRows rows) }

private theorem rowsFrom_length (fine slot count : ℕ) :
    (rowsFrom fine slot count).length = count := by
  induction count generalizing slot with
  | zero => rfl
  | succ count ih =>
      simp [rowsFrom, ih]

private theorem evaluateRows_rowsFrom (fine slot count : ℕ) :
    evaluateRows (rowsFrom fine slot count) =
      RatInterval.point count := by
  induction count generalizing slot with
  | zero => rfl
  | succ count ih =>
      simp [rowsFrom, evaluateRows, row, ih, RatInterval.add,
        RatInterval.point]
      ring

private theorem row_valid (slot : ℕ) :
    validCertificate.RowValidAt slot (row 81 slot) := by
  simp [Certificate.RowValidAt, validCertificate, row, RatInterval.IsValid,
    RatInterval.ExcludesZero, RatInterval.point, RatInterval.mul]

private theorem rows_valid (slot count : ℕ) :
    validCertificate.RowsValidFrom slot (rowsFrom 81 slot count) := by
  induction count generalizing slot with
  | zero => simp [rowsFrom, Certificate.RowsValidFrom]
  | succ count ih =>
      simp only [rowsFrom, Certificate.RowsValidFrom]
      exact ⟨row_valid slot, ih (slot + 1)⟩

private theorem validCertificate_valid : validCertificate.IsValid := by
  refine ⟨?_, le_rfl, ?_, ?_, rfl, rfl⟩
  · norm_num [validCertificate, upsampleFactor]
  · simpa [validCertificate, rows, tapCount] using
      rowsFrom_length 81 0 tapCount
  · simpa [validCertificate, rows] using rows_valid 0 tapCount

example : validCertificate.check = true :=
  Certificate.check_eq_true.mpr validCertificate_valid

example :
    (expectedSourceIndex 81 0, expectedSourceIndex 81 39) = (-9, 30) := by
  norm_num [expectedSourceIndex, tapOffset, upsampleFactor, firstTapOffset]

example :
    (expectedCoefficientIndex 81 0,
      expectedCoefficientIndex 81 39) = (0, 39) := by
  norm_num [expectedCoefficientIndex, upsampleFactor, tapCount, truncation]

example :
    (expectedCoefficientIndex 87 0,
      expectedCoefficientIndex 87 39) = (240, 279) := by
  norm_num [expectedCoefficientIndex, upsampleFactor, tapCount, truncation]

example : coefficientCount = 280 := by
  norm_num [coefficientCount, interpolatedPhaseCount, upsampleFactor,
    tapCount, truncation]

example : sourceStep = 5 / 64 := sourceStep_eq

example : fineStep = 5 / 512 := fineStep_eq

example (origin : ℝ) :
    fineCoordinate origin 87 -
        sourceCoordinate origin (expectedSourceIndex 87 0) =
      (sourceDisplacement 87 0 : ℝ) :=
  fineCoordinate_sub_sourceCoordinate_expectedSourceIndex origin 87 0

example : validCertificate.finiteSum = RatInterval.point 40 := by
  simpa [validCertificate, rows, tapCount, truncation] using
    evaluateRows_rowsFrom 81 0 tapCount

example :
    validCertificate.output =
      ⟨40 - sourceInterpolationError,
        40 + sourceInterpolationError⟩ := by
  simp [validCertificate, rows, evaluateRows_rowsFrom, tapCount, truncation,
    widen, RatInterval.add, RatInterval.point, sub_eq_add_neg]

private def understated : Certificate :=
  { validCertificate with
    interpolationError := 0
    output := widen 0 validCertificate.finiteSum }

example : understated.check = false := by
  cases hcheck : understated.check with
  | false => rfl
  | true =>
      have hvalid := Certificate.check_eq_true.mp hcheck
      have herror := hvalid.2.1
      norm_num [understated, sourceInterpolationError] at herror

private def aligned : AlignedCertificate :=
  { fineIndex := 80
    sourceIndex := 10
    sample := ⟨-1, 2⟩
    output := ⟨-1, 2⟩ }

example : aligned.check = true := by rfl

#print axioms
  SparkInterval.Dirichlet.Factor8Postprocess.fineCoordinate_sub_sourceCoordinate_expectedSourceIndex
#print axioms
  SparkInterval.Dirichlet.Factor8Postprocess.expectedCoefficientIndex_div_tapCount
#print axioms
  SparkInterval.Dirichlet.Factor8Postprocess.expectedCoefficientIndex_mod_tapCount
#print axioms
  SparkInterval.Dirichlet.Factor8Postprocess.Certificate.output_contains
#print axioms
  SparkInterval.Dirichlet.Factor8Postprocess.Certificate.output_contains_source
#print axioms
  SparkInterval.Dirichlet.Factor8Postprocess.Certificate.negative_of_checked_output
#print axioms
  SparkInterval.Dirichlet.Factor8Postprocess.Certificate.positive_of_checked_output
#print axioms
  SparkInterval.Dirichlet.Factor8Postprocess.Certificate.negative_of_checked_source
#print axioms
  SparkInterval.Dirichlet.Factor8Postprocess.Certificate.positive_of_checked_source
#print axioms
  SparkInterval.Dirichlet.Factor8Postprocess.AlignedCertificate.output_contains
#print axioms
  SparkInterval.Dirichlet.Factor8Postprocess.AlignedCertificate.output_contains_source

end SparkInterval.Tests.Factor8PostprocessTest
