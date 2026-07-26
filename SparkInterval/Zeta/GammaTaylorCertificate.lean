/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.Complex
import Mathlib.Analysis.SpecialFunctions.Trigonometric.Basic

/-!
# Arithmetic composition for the Platt Gamma Taylor certificate

`reference/tg_platt_gamma_taylor.cpp` encloses coefficients of a polynomial
approximating the scaled logarithm

`log Gamma (1/4 + i (T+u)/2) + pi (T+u)/4`

on the source window `|u| <= 2688`.  The production kernel then adds the exact
Gaussian exponent `-u^2/(2*116^2)` and exponentiates.  This module proves the
finite composition step needed between those two operations:

* coefficient errors contribute at most
  `sum_i coefficientError_i * radius^i` to Horner/polynomial evaluation;
* an analytic Taylor remainder and the coefficient error add;
* a log-domain error `epsilon` contributes at most
  `exp (approximation.re) * epsilon * exp epsilon` after the nonpositive
  Gaussian and complex exponentiation; and
* a rational rectangle widened by any larger budget contains the exact
  exponentiated value.

The module does not assert that a particular FLINT transcript encloses
`log Gamma`; that source-specific analytic fact remains an explicit input.
Every result below is unconditional and contains no axiom, `sorry`, native
evaluation, or execution-trust boundary.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.GammaTaylorCertificate

open scoped BigOperators
open SparkInterval.Certified

/-! ## Source geometry -/

/-- Radius of the exact source window used by the Platt--Trudgian program. -/
def sourceRadius : ℝ := 2688

/-- Gaussian parameter `h` used by the source computation. -/
def sourceGaussianH : ℝ := 116

/-- Source sample spacing.  This definition records the exact rational value,
not a binary floating-point approximation. -/
noncomputable def sourceGridStep : ℝ := 21 / 128

/-- The exact Gaussian exponent added after the log-Gamma polynomial. -/
noncomputable def gaussianExponent (u h : ℝ) : ℝ := -(u ^ 2 / (2 * h ^ 2))

/-- A positive Gaussian parameter makes the exponent nonpositive. -/
theorem gaussianExponent_nonpos (u : ℝ) {h : ℝ} (hh : 0 < h) :
    gaussianExponent u h ≤ 0 := by
  unfold gaussianExponent
  apply neg_nonpos.mpr
  positivity

theorem sourceGaussianH_pos : 0 < sourceGaussianH := by
  norm_num [sourceGaussianH]

theorem sourceRadius_nonneg : 0 ≤ sourceRadius := by
  norm_num [sourceRadius]

theorem sourceGaussianExponent_nonpos (u : ℝ) :
    gaussianExponent u sourceGaussianH ≤ 0 :=
  gaussianExponent_nonpos u sourceGaussianH_pos

/-! ## Polynomial and coefficient-error arithmetic -/

/-- The degree-`d-1` polynomial represented by the emitted Taylor
coefficients.  The reference producer emits the coefficient of `u^i` in row
`i`, so this definition matches its transcript directly. -/
def taylorPolynomial {d : ℕ} (coefficient : Fin d → ℂ) (u : ℝ) : ℂ :=
  ∑ i : Fin d, coefficient i * (u : ℂ) ^ (i : ℕ)

/-- Worst-case polynomial error obtained from independent coefficient norm
bounds on a disk `|u| ≤ radius`. -/
def coefficientErrorBudget {d : ℕ} (error : Fin d → ℝ)
    (radius : ℝ) : ℝ :=
  ∑ i : Fin d, error i * radius ^ (i : ℕ)

/-- Independent coefficient errors propagate through polynomial evaluation by
the usual weighted sum.  This is the theorem used to turn the producer's
coefficient rectangles (or their binary64 projections) into one log-domain
radius. -/
theorem norm_taylorPolynomial_sub_le {d : ℕ}
    {exact approximate : Fin d → ℂ} {error : Fin d → ℝ}
    {u radius : ℝ} (_hradius : 0 ≤ radius) (hu : |u| ≤ radius)
    (herror_nonneg : ∀ i, 0 ≤ error i)
    (hcoefficient : ∀ i, ‖exact i - approximate i‖ ≤ error i) :
    ‖taylorPolynomial exact u - taylorPolynomial approximate u‖ ≤
      coefficientErrorBudget error radius := by
  rw [taylorPolynomial, taylorPolynomial, ← Finset.sum_sub_distrib]
  refine (norm_sum_le Finset.univ fun i : Fin d ↦
    exact i * (u : ℂ) ^ (i : ℕ) -
      approximate i * (u : ℂ) ^ (i : ℕ)).trans ?_
  rw [coefficientErrorBudget]
  refine Finset.sum_le_sum fun i _ ↦ ?_
  have hpow : |u| ^ (i : ℕ) ≤ radius ^ (i : ℕ) :=
    pow_le_pow_left₀ (abs_nonneg u) hu (i : ℕ)
  calc
    ‖exact i * (u : ℂ) ^ (i : ℕ) -
        approximate i * (u : ℂ) ^ (i : ℕ)‖ =
        ‖exact i - approximate i‖ * |u| ^ (i : ℕ) := by
          rw [← sub_mul, norm_mul, Complex.norm_pow, Complex.norm_real,
            Real.norm_eq_abs]
    _ ≤ error i * radius ^ (i : ℕ) :=
      mul_le_mul (hcoefficient i) hpow (pow_nonneg (abs_nonneg u) _)
        (herror_nonneg i)

/-- Add an analytic Taylor remainder to independently certified coefficient
errors. -/
theorem norm_log_sub_approximation_le {d : ℕ}
    {logValue : ℂ} {exact approximate : Fin d → ℂ}
    {coefficientError : Fin d → ℝ}
    {u radius analyticError : ℝ}
    (hradius : 0 ≤ radius) (hu : |u| ≤ radius)
    (hcoefficientError_nonneg : ∀ i, 0 ≤ coefficientError i)
    (hcoefficient : ∀ i,
      ‖exact i - approximate i‖ ≤ coefficientError i)
    (hanalytic :
      ‖logValue - taylorPolynomial exact u‖ ≤ analyticError) :
    ‖logValue - taylorPolynomial approximate u‖ ≤
      analyticError + coefficientErrorBudget coefficientError radius := by
  calc
    ‖logValue - taylorPolynomial approximate u‖ =
        ‖(logValue - taylorPolynomial exact u) +
          (taylorPolynomial exact u - taylorPolynomial approximate u)‖ := by
            congr 1
            abel
    _ ≤ ‖logValue - taylorPolynomial exact u‖ +
          ‖taylorPolynomial exact u - taylorPolynomial approximate u‖ :=
      norm_add_le _ _
    _ ≤ analyticError + coefficientErrorBudget coefficientError radius :=
      add_le_add hanalytic
        (norm_taylorPolynomial_sub_le hradius hu
          hcoefficientError_nonneg hcoefficient)

/-! ## Log error through exponentiation and the Gaussian -/

/-- Global complex-exponential perturbation bound.  Unlike a local derivative
estimate, this is valid for every error size. -/
theorem norm_exp_sub_exp_le_of_norm_sub_le
    {exactLog approximateLog : ℂ} {epsilon : ℝ}
    (hepsilon : 0 ≤ epsilon)
    (hlog : ‖exactLog - approximateLog‖ ≤ epsilon) :
    ‖Complex.exp exactLog - Complex.exp approximateLog‖ ≤
      Real.exp approximateLog.re * (epsilon * Real.exp epsilon) := by
  let delta : ℂ := exactLog - approximateLog
  have hidentity :
      Complex.exp exactLog - Complex.exp approximateLog =
        Complex.exp approximateLog * (Complex.exp delta - 1) := by
    rw [mul_sub, mul_one, ← Complex.exp_add]
    congr 2
    dsimp [delta]
    abel
  have hexpError :
      ‖Complex.exp delta - 1‖ ≤ ‖delta‖ * Real.exp ‖delta‖ := by
    simpa using Complex.norm_exp_sub_sum_le_norm_mul_exp delta 1
  have hdelta : ‖delta‖ ≤ epsilon := by
    simpa [delta] using hlog
  rw [hidentity, norm_mul, Complex.norm_exp]
  apply mul_le_mul_of_nonneg_left _ (Real.exp_nonneg _)
  calc
    ‖Complex.exp delta - 1‖ ≤ ‖delta‖ * Real.exp ‖delta‖ :=
      hexpError
    _ ≤ epsilon * Real.exp epsilon := by
      exact mul_le_mul hdelta (Real.exp_le_exp.mpr hdelta)
        (Real.exp_nonneg _) hepsilon

/-- Adding an exact real Gaussian preserves the log difference.  This version
keeps the exact Gaussian attenuation factor. -/
theorem norm_exp_add_gaussian_sub_le
    {exactLog approximateLog : ℂ} {epsilon u h : ℝ}
    (hepsilon : 0 ≤ epsilon)
    (hlog : ‖exactLog - approximateLog‖ ≤ epsilon) :
    ‖Complex.exp (exactLog + (gaussianExponent u h : ℂ)) -
        Complex.exp (approximateLog + (gaussianExponent u h : ℂ))‖ ≤
      Real.exp (approximateLog.re + gaussianExponent u h) *
        (epsilon * Real.exp epsilon) := by
  have hshifted :
      ‖(exactLog + (gaussianExponent u h : ℂ)) -
          (approximateLog + (gaussianExponent u h : ℂ))‖ ≤ epsilon := by
    simpa only [add_sub_add_right_eq_sub] using hlog
  simpa using
    (norm_exp_sub_exp_le_of_norm_sub_le hepsilon hshifted)

/-- For the positive source Gaussian parameter, the Gaussian cannot amplify
the error.  The resulting budget depends only on the polynomial's real part
and the total log-domain error. -/
theorem norm_sourceValue_sub_approximation_le
    {exactLog approximateLog : ℂ} {epsilon u : ℝ}
    (hepsilon : 0 ≤ epsilon)
    (hlog : ‖exactLog - approximateLog‖ ≤ epsilon) :
    ‖Complex.exp (exactLog + (gaussianExponent u sourceGaussianH : ℂ)) -
        Complex.exp
          (approximateLog + (gaussianExponent u sourceGaussianH : ℂ))‖ ≤
      Real.exp approximateLog.re * (epsilon * Real.exp epsilon) := by
  refine (norm_exp_add_gaussian_sub_le hepsilon hlog).trans ?_
  apply mul_le_mul_of_nonneg_right
    (Real.exp_le_exp.mpr (add_le_of_nonpos_right
      (sourceGaussianExponent_nonpos u)))
  exact mul_nonneg hepsilon (Real.exp_nonneg _)

/-! ## End-to-end finite composition -/

/-- Pointwise source-shaped theorem: analytic Taylor remainder, coefficient
projection errors, exact Gaussian insertion, and exponentiation are composed
into one explicit output error. -/
theorem norm_sourceValue_sub_taylorValue_le {d : ℕ}
    {logValue : ℂ} {exact approximate : Fin d → ℂ}
    {coefficientError : Fin d → ℝ}
    {u radius analyticError : ℝ}
    (hradius : 0 ≤ radius) (hu : |u| ≤ radius)
    (hanalyticError : 0 ≤ analyticError)
    (hcoefficientError_nonneg : ∀ i, 0 ≤ coefficientError i)
    (hcoefficient : ∀ i,
      ‖exact i - approximate i‖ ≤ coefficientError i)
    (hanalytic :
      ‖logValue - taylorPolynomial exact u‖ ≤ analyticError) :
    ‖Complex.exp
          (logValue + (gaussianExponent u sourceGaussianH : ℂ)) -
        Complex.exp
          (taylorPolynomial approximate u +
            (gaussianExponent u sourceGaussianH : ℂ))‖ ≤
      Real.exp (taylorPolynomial approximate u).re *
        ((analyticError + coefficientErrorBudget coefficientError radius) *
          Real.exp
            (analyticError + coefficientErrorBudget coefficientError radius)) := by
  have hbudget_nonneg :
      0 ≤ coefficientErrorBudget coefficientError radius := by
    rw [coefficientErrorBudget]
    exact Finset.sum_nonneg fun i _ ↦
      mul_nonneg (hcoefficientError_nonneg i) (pow_nonneg hradius _)
  exact norm_sourceValue_sub_approximation_le
    (add_nonneg hanalyticError hbudget_nonneg)
    (norm_log_sub_approximation_le hradius hu
      hcoefficientError_nonneg hcoefficient hanalytic)

/-- The same composition theorem specialized to the producer's exact
`|u| ≤ 2688` source window. -/
theorem norm_sourceWindowValue_sub_taylorValue_le {d : ℕ}
    {logValue : ℂ} {exact approximate : Fin d → ℂ}
    {coefficientError : Fin d → ℝ}
    {u analyticError : ℝ} (hu : |u| ≤ sourceRadius)
    (hanalyticError : 0 ≤ analyticError)
    (hcoefficientError_nonneg : ∀ i, 0 ≤ coefficientError i)
    (hcoefficient : ∀ i,
      ‖exact i - approximate i‖ ≤ coefficientError i)
    (hanalytic :
      ‖logValue - taylorPolynomial exact u‖ ≤ analyticError) :
    ‖Complex.exp
          (logValue + (gaussianExponent u sourceGaussianH : ℂ)) -
        Complex.exp
          (taylorPolynomial approximate u +
            (gaussianExponent u sourceGaussianH : ℂ))‖ ≤
      Real.exp (taylorPolynomial approximate u).re *
        ((analyticError +
            coefficientErrorBudget coefficientError sourceRadius) *
          Real.exp
            (analyticError +
              coefficientErrorBudget coefficientError sourceRadius)) :=
  norm_sourceValue_sub_taylorValue_le sourceRadius_nonneg hu
    hanalyticError hcoefficientError_nonneg hcoefficient hanalytic

/-- Consumer-facing rectangle rule.  A rectangle enclosing the finite
polynomial/Gaussian evaluation, widened by a rational budget no smaller than
the proved exponential perturbation, contains the exact source value. -/
theorem widenedRect_contains_sourceValue {d : ℕ}
    {logValue : ℂ} {approximate : Fin d → ℂ}
    {u epsilon : ℝ} {outputError : ℚ} {Z : ComplexRect}
    (hepsilon : 0 ≤ epsilon)
    (hlog : ‖logValue - taylorPolynomial approximate u‖ ≤ epsilon)
    (happroximation : Z.ContainsComplex
      (Complex.exp
        (taylorPolynomial approximate u +
          (gaussianExponent u sourceGaussianH : ℂ))))
    (houtputError :
      Real.exp (taylorPolynomial approximate u).re *
          (epsilon * Real.exp epsilon) ≤ (outputError : ℝ)) :
    (ComplexRect.widenRect outputError Z).ContainsComplex
      (Complex.exp
        (logValue + (gaussianExponent u sourceGaussianH : ℂ))) := by
  apply ComplexRect.widen_contains_of_norm_le happroximation
  have hbound :=
    norm_sourceValue_sub_approximation_le (u := u) hepsilon hlog
  exact hbound.trans houtputError

end SparkInterval.Zeta.GammaTaylorCertificate
