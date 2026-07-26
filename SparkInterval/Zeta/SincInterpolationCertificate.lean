/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.RatInterval
import Mathlib.Analysis.SpecialFunctions.Trigonometric.Basic

/-!
# Checked Gaussian--sinc interpolation certificates

This module checks the finite interpolation arithmetic used by
Platt--Trudgian's `zeta_arb/inter.c`.  The source evaluates 70 samples on each
side of a query, with

* lattice spacing `21/512`;
* Gaussian parameter `H = 13/64`; and
* the joint Appendix-C interpolation allowance `2.45 * 10^-40`.

The checker fixes all 140 source indices and distances, checks exact rational
interval products for every sample/Gaussian/sinc row, folds the terms, and
widens the result by the joint allowance.  Its soundness theorem applies
to an arbitrary real function.  The analytic realization record makes the
remaining obligations explicit: sample intervals must contain the function,
the transcendental intervals must contain the mathematical Gaussian and sinc,
and the combined Weiss/non-bandlimited error (C.1) plus omitted sampling tail
(corrected C.3) must fit the advertised allowance.

This separation is intentional.  The retained Arb source initializes
`intererr` but the `inter.c` evaluation path does not add it to `f_res`.
Production evidence accepted through this module must include the widening;
it cannot inherit that omission silently.

There are no axioms, `sorry`, `native_decide`, unsafe definitions, or host
floating-point decisions in this file.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open SparkInterval.Certificate

namespace SincInterpolationCertificate

/-! ## Exact source parameters -/

/-- Output spacing `one_over_A` in `zeta_arb/parameters.h`. -/
def sourceSpacing : ℚ := 21 / 512

/-- Gaussian parameter `H` in `zeta_arb/parameters.h`. -/
def sourceGaussianH : ℚ := 13 / 64

/-- Number of points taken on each side of the interpolation query. -/
def sourcePointsPerSide : ℕ := 70

/-- Total number of terms evaluated by `arb_inter_t`. -/
def sourceTermCount : ℕ := 2 * sourcePointsPerSide

/-- Total Appendix-C interpolation allowance `2.45e-40`, represented exactly.
It budgets both the C.1 Weiss/non-bandlimited error and corrected-C.3 omitted
sampling tail; it is not a bound for C.3 alone. -/
def sourceInterpolationError : ℚ := 245 / (10 ^ 42 : ℚ)

theorem sourceSpacing_pos : 0 < sourceSpacing := by
  norm_num [sourceSpacing]

theorem sourceGaussianH_pos : 0 < sourceGaussianH := by
  norm_num [sourceGaussianH]

theorem sourceInterpolationError_nonneg : 0 ≤ sourceInterpolationError := by
  norm_num [sourceInterpolationError]

/-! ## Mathematical interpolation kernel -/

/-- The Gaussian factor computed by `inter_gaussian`. -/
noncomputable def gaussian (distance h : ℝ) : ℝ :=
  Real.exp (-(distance ^ 2 / (2 * h ^ 2)))

/-- The continuously extended normalized sinc factor.  Source interpolation
queries are non-lattice points, so the nonzero branch is the executed one;
the value at zero records the mathematical continuous extension. -/
noncomputable def normalizedSinc (distance spacing : ℝ) : ℝ :=
  if distance = 0 then 1
  else Real.sin (Real.pi * distance / spacing) /
    (Real.pi * distance / spacing)

/-! ## Untrusted row and certificate data -/

/-- One retained source-shaped interpolation term. -/
structure Row where
  /-- Index into the source lattice. -/
  index : ℤ
  /-- Exact physical displacement `(index-queryIndex)*spacing`. -/
  distance : ℚ
  /-- Enclosure of the real source sample. -/
  sample : RatInterval
  /-- Enclosure of `exp(-distance^2/(2H^2))`. -/
  gaussian : RatInterval
  /-- Enclosure of `sinc(pi*distance/spacing)`. -/
  sinc : RatInterval
  /-- Exact interval product `sample * gaussian * sinc`. -/
  term : RatInterval
  deriving DecidableEq, Repr

/-- The source always uses the 70 lattice indices immediately to the right,
then the 70 indices at or to the left of `floor(queryIndex)`.  This is the
common set and order of both branches in `arb_inter_t`. -/
def expectedIndex (queryIndex : ℚ) (slot : ℕ) : ℤ :=
  if slot < sourcePointsPerSide then
    ⌊queryIndex⌋ + 1 + (slot : ℤ)
  else
    ⌊queryIndex⌋ - ((slot - sourcePointsPerSide : ℕ) : ℤ)

/-- Exact source displacement for a row slot. -/
def expectedDistance (queryIndex spacing : ℚ) (slot : ℕ) : ℚ :=
  ((expectedIndex queryIndex slot : ℤ) : ℚ) * spacing -
    queryIndex * spacing

/-- Finite interval fold.  The recursive order matches repeated `arb_add`. -/
def evaluateRows : List Row → RatInterval
  | [] => RatInterval.point 0
  | row :: rows => row.term.add (evaluateRows rows)

/-- Widen a finite result by a symmetric exact rational error. -/
def widen (error : ℚ) (value : RatInterval) : RatInterval :=
  value.add ⟨-error, error⟩

/-- Complete untrusted certificate for one interpolation query.  `origin` is
the physical ordinate represented by source lattice index zero. -/
structure Certificate where
  origin : ℚ
  queryIndex : ℚ
  spacing : ℚ
  gaussianH : ℚ
  /-- Joint C.1 plus corrected-C.3 interpolation error budget. -/
  interpolationError : ℚ
  rows : List Row
  finiteSum : RatInterval
  output : RatInterval
  deriving DecidableEq, Repr

namespace Certificate

/-- Exact rational coordinate represented by the query. -/
def queryRational (certificate : Certificate) : ℚ :=
  certificate.origin + certificate.queryIndex * certificate.spacing

/-- Exact physical ordinate at which interpolation is requested. -/
def queryOrdinate (certificate : Certificate) : ℝ :=
  (certificate.queryRational : ℝ)

/-- Exact physical ordinate of a retained lattice sample. -/
def sampleOrdinate (certificate : Certificate) (row : Row) : ℝ :=
  ((certificate.origin + (row.index : ℚ) * certificate.spacing : ℚ) : ℝ)

/-- Mathematical value represented by a retained row. -/
noncomputable def rowValue (certificate : Certificate)
    (function : ℝ → ℝ) (row : Row) : ℝ :=
  function (certificate.sampleOrdinate row) *
    gaussian (row.distance : ℝ) (certificate.gaussianH : ℝ) *
    normalizedSinc (row.distance : ℝ) (certificate.spacing : ℝ)

/-- Mathematical finite interpolation sum, in the same recursive order as
the interval fold. -/
noncomputable def exactSum (certificate : Certificate)
    (function : ℝ → ℝ) : List Row → ℝ
  | [] => 0
  | row :: rows => certificate.rowValue function row +
      certificate.exactSum function rows

/-- Source-shaped validity of one row at a particular slot. -/
def RowValidAt (certificate : Certificate) (slot : ℕ) (row : Row) : Prop :=
  row.index = expectedIndex certificate.queryIndex slot ∧
    row.distance = expectedDistance certificate.queryIndex certificate.spacing slot ∧
    row.distance ≠ 0 ∧
    row.sample.IsValid ∧
    row.gaussian.IsValid ∧
    row.sinc.IsValid ∧
    row.term = (row.sample.mul row.gaussian).mul row.sinc

/-- Recursive row validity with an explicit source slot counter. -/
def RowsValidFrom (certificate : Certificate) : ℕ → List Row → Prop
  | _, [] => True
  | slot, row :: rows =>
      certificate.RowValidAt slot row ∧
        certificate.RowsValidFrom (slot + 1) rows

/-- Exact proposition reflected by `check`. -/
def IsValid (certificate : Certificate) : Prop :=
  certificate.spacing = sourceSpacing ∧
    certificate.gaussianH = sourceGaussianH ∧
    certificate.interpolationError = sourceInterpolationError ∧
    certificate.rows.length = sourceTermCount ∧
    certificate.RowsValidFrom 0 certificate.rows ∧
    certificate.finiteSum = evaluateRows certificate.rows ∧
    certificate.output =
      widen certificate.interpolationError certificate.finiteSum

/-- Executable row checker. -/
def checkRowsFrom (certificate : Certificate) : ℕ → List Row → Bool
  | _, [] => true
  | slot, row :: rows =>
      decide (row.index = expectedIndex certificate.queryIndex slot) &&
      decide (row.distance =
        expectedDistance certificate.queryIndex certificate.spacing slot) &&
      decide (row.distance ≠ 0) &&
      row.sample.isValid &&
      row.gaussian.isValid &&
      row.sinc.isValid &&
      decide (row.term = (row.sample.mul row.gaussian).mul row.sinc) &&
      certificate.checkRowsFrom (slot + 1) rows

@[simp] theorem checkRowsFrom_eq_true (certificate : Certificate)
    (slot : ℕ) (rows : List Row) :
    certificate.checkRowsFrom slot rows = true ↔
      certificate.RowsValidFrom slot rows := by
  induction rows generalizing slot with
  | nil => simp [checkRowsFrom, RowsValidFrom]
  | cons row rows ih =>
      simp [checkRowsFrom, RowsValidFrom, RowValidAt, ih]
      tauto

/-- Kernel-reducible exact certificate checker. -/
def check (certificate : Certificate) : Bool :=
  decide (certificate.spacing = sourceSpacing) &&
  decide (certificate.gaussianH = sourceGaussianH) &&
  decide (certificate.interpolationError = sourceInterpolationError) &&
  decide (certificate.rows.length = sourceTermCount) &&
  certificate.checkRowsFrom 0 certificate.rows &&
  decide (certificate.finiteSum = evaluateRows certificate.rows) &&
  decide (certificate.output =
    widen certificate.interpolationError certificate.finiteSum)

@[simp] theorem check_eq_true {certificate : Certificate} :
    certificate.check = true ↔ certificate.IsValid := by
  simp [check, IsValid, checkRowsFrom_eq_true]
  tauto

@[simp] theorem check_eq_false {certificate : Certificate} :
    certificate.check = false ↔ ¬certificate.IsValid := by
  constructor
  · intro hfalse hvalid
    have htrue : certificate.check = true := check_eq_true.mpr hvalid
    rw [hfalse] at htrue
    contradiction
  · intro hnot
    cases hcheck : certificate.check with
    | false => rfl
    | true =>
        exact False.elim (hnot (check_eq_true.mp hcheck))

/-! ## Analytic realization and soundness -/

/-- The explicit analytic obligations not discharged by rational arithmetic.
`totalInterpolationError` is the complete true-value-to-140-term bound.  For
Platt's source it must be derived from the C.1 Weiss/non-bandlimited error and
the corrected-C.3 omitted-sum tail; C.3 alone is insufficient. -/
structure Realization (certificate : Certificate) (function : ℝ → ℝ) : Prop where
  sample : ∀ row ∈ certificate.rows,
    row.sample.ContainsReal (function (certificate.sampleOrdinate row))
  gaussian : ∀ row ∈ certificate.rows,
    row.gaussian.ContainsReal
      (SincInterpolationCertificate.gaussian (row.distance : ℝ)
        (certificate.gaussianH : ℝ))
  sinc : ∀ row ∈ certificate.rows,
    row.sinc.ContainsReal
      (normalizedSinc (row.distance : ℝ) (certificate.spacing : ℝ))
  totalInterpolationError : |function certificate.queryOrdinate -
      certificate.exactSum function certificate.rows| ≤
    (certificate.interpolationError : ℝ)

/-- Checked row products enclose their mathematical values. -/
theorem row_contains (certificate : Certificate) (function : ℝ → ℝ)
    (realization : certificate.Realization function)
    {row : Row} (hrow : row ∈ certificate.rows)
    {slot : ℕ} (hvalid : certificate.RowValidAt slot row) :
    row.term.ContainsReal (certificate.rowValue function row) := by
  rw [hvalid.2.2.2.2.2.2]
  exact RatInterval.mul_containsReal
    (RatInterval.mul_containsReal
      (realization.sample row hrow)
      (realization.gaussian row hrow))
    (realization.sinc row hrow)

/-- Every successful row check gives finite-sum containment. -/
theorem evaluateRows_contains (certificate : Certificate)
    (function : ℝ → ℝ) (realization : certificate.Realization function)
    {slot : ℕ} {rows : List Row}
    (hsub : ∀ row ∈ rows, row ∈ certificate.rows)
    (hvalid : certificate.RowsValidFrom slot rows) :
    (evaluateRows rows).ContainsReal (certificate.exactSum function rows) := by
  induction rows generalizing slot with
  | nil =>
      simpa [evaluateRows, exactSum] using RatInterval.point_containsReal 0
  | cons row rows ih =>
      obtain ⟨hrowValid, hrowsValid⟩ := hvalid
      have hrowMember : row ∈ certificate.rows := hsub row (by simp)
      have htailSub : ∀ tailRow ∈ rows, tailRow ∈ certificate.rows := by
        intro tailRow htailRow
        exact hsub tailRow (by simp [htailRow])
      exact RatInterval.add_containsReal
        (certificate.row_contains function realization hrowMember hrowValid)
        (ih htailSub hrowsValid)

/-- Symmetric widening transports a finite enclosure across an absolute error
bound. -/
theorem widen_contains_of_abs_sub_le {value target : ℝ}
    {interval : RatInterval} {error : ℚ}
    (hvalue : interval.ContainsReal value)
    (herror : |target - value| ≤ (error : ℝ)) :
    (widen error interval).ContainsReal target := by
  have hlower : -(error : ℝ) ≤ target - value :=
    (abs_le.mp herror).1
  have hupper : target - value ≤ (error : ℝ) :=
    (abs_le.mp herror).2
  have hdelta : (RatInterval.mk (-error) error).ContainsReal (target - value) := by
    simpa only [RatInterval.ContainsReal, Rat.cast_neg] using ⟨hlower, hupper⟩
  have hadd := RatInterval.add_containsReal hvalue hdelta
  rw [show target = value + (target - value) by ring]
  exact hadd

/-- Main certificate theorem: successful exact checking plus the visibly
separate analytic realization imply that the emitted interval contains the
true interpolated value. -/
theorem output_contains (certificate : Certificate)
    (function : ℝ → ℝ) (hcheck : certificate.check = true)
    (realization : certificate.Realization function) :
    certificate.output.ContainsReal (function certificate.queryOrdinate) := by
  have hvalid := certificate.check_eq_true.mp hcheck
  obtain ⟨_hspacing, _hH, _htail, _hlength, hrows, hsum, houtput⟩ := hvalid
  have hfinite : certificate.finiteSum.ContainsReal
      (certificate.exactSum function certificate.rows) := by
    rw [hsum]
    exact certificate.evaluateRows_contains function realization
      (fun _ h ↦ h) hrows
  rw [houtput]
  exact widen_contains_of_abs_sub_le hfinite
    realization.totalInterpolationError

end Certificate

end SincInterpolationCertificate

end SparkInterval.Zeta
