/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.SincInterpolationEndpointBridge

/-! Regression tests for the exact Gaussian--sinc interpolation checker. -/

set_option autoImplicit false

namespace SparkInterval.Tests.SincInterpolationCertificate

open SparkInterval.Certificate
open SparkInterval.Zeta.SincInterpolationCertificate

def queryIndex : ℚ := 1 / 2

def rowAt (slot : ℕ) : Row :=
  let one := RatInterval.point 1
  { index := expectedIndex queryIndex slot
    distance := expectedDistance queryIndex sourceSpacing slot
    sample := one
    gaussian := one
    sinc := one
    term := (one.mul one).mul one }

def rowsFrom (slot : ℕ) : ℕ → List Row
  | 0 => []
  | count + 1 => rowAt slot :: rowsFrom (slot + 1) count

def rows : List Row := rowsFrom 0 sourceTermCount

def finiteSum : RatInterval := evaluateRows rows

def validCertificate : Certificate :=
  { origin := 10 ^ 10
    queryIndex := queryIndex
    spacing := sourceSpacing
    gaussianH := sourceGaussianH
    interpolationError := sourceInterpolationError
    rows := rows
    finiteSum := finiteSum
    output := widen sourceInterpolationError finiteSum }

theorem expectedDistance_ne_zero (slot : ℕ) :
    expectedDistance queryIndex sourceSpacing slot ≠ 0 := by
  intro hzero
  have hproduct :
      ((((expectedIndex queryIndex slot : ℤ) : ℚ) - queryIndex) *
        sourceSpacing) = 0 := by
    simpa [expectedDistance, sub_mul] using hzero
  have hspacing : sourceSpacing ≠ 0 := ne_of_gt sourceSpacing_pos
  have hindex : (((expectedIndex queryIndex slot : ℤ) : ℚ)) = queryIndex := by
    exact sub_eq_zero.mp ((mul_eq_zero.mp hproduct).resolve_right hspacing)
  have htwiceQ :
      (2 : ℚ) * (((expectedIndex queryIndex slot : ℤ) : ℚ)) = 1 := by
    rw [hindex]
    norm_num [queryIndex]
  have htwiceZ : (2 : ℤ) * expectedIndex queryIndex slot = 1 := by
    exact_mod_cast htwiceQ
  omega

theorem rowAt_valid (slot : ℕ) :
    validCertificate.RowValidAt slot (rowAt slot) := by
  refine ⟨rfl, rfl, expectedDistance_ne_zero slot, ?_⟩
  norm_num [rowAt, RatInterval.IsValid, RatInterval.point, RatInterval.mul]

theorem rowsFrom_valid (slot count : ℕ) :
    validCertificate.RowsValidFrom slot (rowsFrom slot count) := by
  induction count generalizing slot with
  | zero => simp [rowsFrom, Certificate.RowsValidFrom]
  | succ count ih =>
      exact ⟨rowAt_valid slot, ih (slot + 1)⟩

theorem validCertificate_isValid : validCertificate.IsValid := by
  refine ⟨rfl, rfl, rfl, ?_, rowsFrom_valid 0 sourceTermCount, rfl, rfl⟩
  norm_num [validCertificate, rows, rowsFrom, sourceTermCount,
    sourcePointsPerSide]

example : validCertificate.check = true :=
  Certificate.check_eq_true.mpr validCertificate_isValid

def wrongInterpolationError : Certificate :=
  { validCertificate with interpolationError := 0 }

example : wrongInterpolationError.check = false := by
  apply Certificate.check_eq_false.mpr
  intro hvalid
  have herror := hvalid.2.2.1
  norm_num [wrongInterpolationError, validCertificate,
    sourceInterpolationError] at herror

def missingRow : Certificate :=
  { validCertificate with rows := validCertificate.rows.drop 1 }

example : missingRow.check = false := by
  apply Certificate.check_eq_false.mpr
  intro hvalid
  have hlength := hvalid.2.2.2.1
  norm_num [missingRow, validCertificate, rows, rowsFrom, sourceTermCount,
    sourcePointsPerSide] at hlength

/-- The public soundness theorem has only foundational dependencies. -/
theorem checked_toy_contains (function : ℝ → ℝ)
    (realization : validCertificate.Realization function) :
    validCertificate.output.ContainsReal
      (function validCertificate.queryOrdinate) := by
  apply validCertificate.output_contains function
  · exact Certificate.check_eq_true.mpr validCertificate_isValid
  · exact realization

#print axioms checked_toy_contains
#print axioms SparkInterval.Zeta.SincInterpolationCertificate.Certificate.output_contains

theorem checked_bracket_encloses
    (certificate : SparkInterval.Zeta.SincInterpolationBracket.Certificate)
    (function : ℝ → ℝ) (hcheck : certificate.check = true)
    (realization : certificate.Realization function) :
    certificate.bracket.EnclosesEndpoints function :=
  certificate.enclosesEndpoints function hcheck realization

#print axioms checked_bracket_encloses
#print axioms SparkInterval.Zeta.SincInterpolationBracket.Certificate.exists_zero

end SparkInterval.Tests.SincInterpolationCertificate
