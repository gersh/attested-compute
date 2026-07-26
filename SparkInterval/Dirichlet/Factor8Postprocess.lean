/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.RatInterval

/-!
# Exact arithmetic boundary for routine factor-eight interpolation

Platt's routine Dirichlet computation starts with real completed-`L`
enclosures on the `5/64` lattice and evaluates the seven nonaligned phases of
an eight-times finer lattice with forty consecutive Gaussian--sinc weights.

This module checks one target entirely over exact rationals.  It fixes the
source and coefficient-table indices, checks all forty interval products and
their fold, and requires a symmetric widening of at least `8.6e-8`.  The
soundness theorem deliberately takes a separate analytic realization:

* source intervals contain the completed-`L` values;
* coefficient intervals contain the mathematical Gaussian--sinc weights; and
* the true target differs from the forty-term sum by at most the retained
  interpolation allowance.

Thus the executable checker proves the finite interval arithmetic without
pretending to prove the external uniform interpolation estimate, the upstream
completed values, zero isolation, multiplicity, or Turing completeness.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.Factor8Postprocess

open SparkInterval.Certificate

def upsampleFactor : ℕ := 8

def sourceStep : ℚ := 5 / 64

def fineStep : ℚ := sourceStep / upsampleFactor

def truncation : ℕ := 20

def tapCount : ℕ := 2 * truncation

def interpolatedPhaseCount : ℕ := upsampleFactor - 1

def coefficientCount : ℕ := interpolatedPhaseCount * tapCount

def firstTapOffset : ℤ := -19

def sourceInterpolationError : ℚ := 86 / (10 ^ 9 : ℚ)

theorem sourceStep_eq : sourceStep = 5 / 64 := rfl

theorem fineStep_eq : fineStep = 5 / 512 := by
  norm_num [fineStep, sourceStep, upsampleFactor]

theorem sourceStep_pos : 0 < sourceStep := by
  norm_num [sourceStep]

theorem fineStep_pos : 0 < fineStep := by
  norm_num [fineStep, sourceStep, upsampleFactor]

theorem sourceInterpolationError_nonneg :
    0 ≤ sourceInterpolationError := by
  norm_num [sourceInterpolationError]

/-- Integer source offset represented by one retained interpolation row. -/
def tapOffset (slot : ℕ) : ℤ :=
  firstTapOffset + (slot : ℤ)

/-- Source-lattice index used by one of the forty consecutive taps. -/
def expectedSourceIndex (fineIndex slot : ℕ) : ℤ :=
  ((fineIndex / upsampleFactor : ℕ) : ℤ) +
    tapOffset slot

/-- Position in the canonical phase-major `7 × 40` coefficient table. -/
def expectedCoefficientIndex (fineIndex slot : ℕ) : ℕ :=
  (fineIndex % upsampleFactor - 1) * tapCount + slot

/-- Physical source-lattice coordinate relative to a caller-supplied origin. -/
noncomputable def sourceCoordinate (origin : ℝ) (sourceIndex : ℤ) : ℝ :=
  origin + (sourceIndex : ℝ) * (sourceStep : ℝ)

/-- Physical factor-eight coordinate relative to the same origin. -/
noncomputable def fineCoordinate (origin : ℝ) (fineIndex : ℕ) : ℝ :=
  origin + (fineIndex : ℝ) * (fineStep : ℝ)

/-- Turn a completed real-valued function into the integer-indexed source
samples used by the finite arithmetic theorem. -/
noncomputable def completedSamples (origin : ℝ)
    (completedValue : ℝ → ℝ) : ℤ → ℝ :=
  fun sourceIndex ↦ completedValue (sourceCoordinate origin sourceIndex)

/-- Signed source-grid displacement from a retained tap to its target.

The dimensionless factor is `phase / 8 - tapOffset`; multiplying by `5/64`
puts the displacement in the source variable's units. -/
def sourceDisplacement (fineIndex slot : ℕ) : ℚ :=
  (((fineIndex % upsampleFactor : ℕ) : ℚ) / upsampleFactor -
      (tapOffset slot : ℚ)) * sourceStep

/-- The checked integer source index denotes exactly the physical tap whose
displacement is used by the phase-major coefficient table. -/
theorem fineCoordinate_sub_sourceCoordinate_expectedSourceIndex
    (origin : ℝ) (fineIndex slot : ℕ) :
    fineCoordinate origin fineIndex -
        sourceCoordinate origin (expectedSourceIndex fineIndex slot) =
      (sourceDisplacement fineIndex slot : ℝ) := by
  have hdivNat : fineIndex % upsampleFactor +
      upsampleFactor * (fineIndex / upsampleFactor) = fineIndex :=
    Nat.mod_add_div fineIndex upsampleFactor
  have hdiv : (fineIndex : ℝ) =
      ((fineIndex % upsampleFactor : ℕ) : ℝ) +
        (upsampleFactor : ℝ) *
          ((fineIndex / upsampleFactor : ℕ) : ℝ) := by
    exact_mod_cast hdivNat.symm
  have hsourceCast :
      ((expectedSourceIndex fineIndex slot : ℤ) : ℝ) =
        ((fineIndex / upsampleFactor : ℕ) : ℝ) +
          (firstTapOffset : ℝ) + (slot : ℝ) := by
    simp only [expectedSourceIndex, tapOffset, Int.cast_add, Int.cast_natCast]
    ring
  unfold fineCoordinate sourceCoordinate
  rw [hsourceCast, hdiv]
  norm_num [sourceDisplacement, tapOffset, fineStep, sourceStep,
    upsampleFactor, firstTapOffset]
  ring

/-- Phase-major table lookup recovers the target's phase. -/
theorem expectedCoefficientIndex_div_tapCount
    (fineIndex slot : ℕ)
    (hphase : fineIndex % upsampleFactor ≠ 0)
    (hslot : slot < tapCount) :
    expectedCoefficientIndex fineIndex slot / tapCount + 1 =
      fineIndex % upsampleFactor := by
  norm_num [expectedCoefficientIndex, upsampleFactor, tapCount, truncation]
    at hphase hslot ⊢
  have hmod : fineIndex % 8 < 8 := Nat.mod_lt _ (by omega)
  omega

/-- Phase-major table lookup recovers the tap slot within its block. -/
theorem expectedCoefficientIndex_mod_tapCount
    (fineIndex slot : ℕ) (hslot : slot < tapCount) :
    expectedCoefficientIndex fineIndex slot % tapCount = slot := by
  norm_num [expectedCoefficientIndex, upsampleFactor, tapCount, truncation]
    at hslot ⊢
  omega

/-- Every checked row index lies in the complete `7 × 40` table. -/
theorem expectedCoefficientIndex_lt_coefficientCount
    (fineIndex slot : ℕ) (hslot : slot < tapCount) :
    expectedCoefficientIndex fineIndex slot < coefficientCount := by
  norm_num [expectedCoefficientIndex, coefficientCount,
    interpolatedPhaseCount, upsampleFactor, tapCount, truncation] at hslot ⊢
  have hmod : fineIndex % 8 < 8 := Nat.mod_lt _ (by omega)
  omega

/-- One source interval, coefficient interval, and their exact product hull. -/
structure Row where
  sourceIndex : ℤ
  coefficientIndex : ℕ
  sample : RatInterval
  coefficient : RatInterval
  term : RatInterval
  deriving DecidableEq, Repr

/-- Exact recursive order used for the retained interval sum. -/
def evaluateRows : List Row → RatInterval
  | [] => RatInterval.point 0
  | row :: rows => row.term.add (evaluateRows rows)

/-- Symmetric interpolation-error widening. -/
def widen (error : ℚ) (interval : RatInterval) : RatInterval :=
  interval.add ⟨-error, error⟩

/-- One nonaligned factor-eight interpolation certificate. -/
structure Certificate where
  fineIndex : ℕ
  interpolationError : ℚ
  rows : List Row
  finiteSum : RatInterval
  output : RatInterval
  deriving DecidableEq, Repr

namespace Certificate

def RowValidAt (certificate : Certificate) (slot : ℕ) (row : Row) : Prop :=
  row.sourceIndex = expectedSourceIndex certificate.fineIndex slot ∧
    row.coefficientIndex =
      expectedCoefficientIndex certificate.fineIndex slot ∧
    row.sample.IsValid ∧
    row.coefficient.IsValid ∧
    row.coefficient.ExcludesZero ∧
    row.term = row.sample.mul row.coefficient

def RowsValidFrom (certificate : Certificate) : ℕ → List Row → Prop
  | _, [] => True
  | slot, row :: rows =>
      certificate.RowValidAt slot row ∧
        certificate.RowsValidFrom (slot + 1) rows

def IsValid (certificate : Certificate) : Prop :=
  certificate.fineIndex % upsampleFactor ≠ 0 ∧
    sourceInterpolationError ≤ certificate.interpolationError ∧
    certificate.rows.length = tapCount ∧
    certificate.RowsValidFrom 0 certificate.rows ∧
    certificate.finiteSum = evaluateRows certificate.rows ∧
    certificate.output =
      widen certificate.interpolationError certificate.finiteSum

def checkRowsFrom (certificate : Certificate) : ℕ → List Row → Bool
  | _, [] => true
  | slot, row :: rows =>
      decide (row.sourceIndex =
        expectedSourceIndex certificate.fineIndex slot) &&
      decide (row.coefficientIndex =
        expectedCoefficientIndex certificate.fineIndex slot) &&
      row.sample.isValid &&
      row.coefficient.isValid &&
      row.coefficient.excludesZero &&
      decide (row.term = row.sample.mul row.coefficient) &&
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

/-- Kernel-reducible exact-rational checker for one nonaligned target. -/
def check (certificate : Certificate) : Bool :=
  decide (certificate.fineIndex % upsampleFactor ≠ 0) &&
  decide (sourceInterpolationError ≤ certificate.interpolationError) &&
  decide (certificate.rows.length = tapCount) &&
  certificate.checkRowsFrom 0 certificate.rows &&
  decide (certificate.finiteSum = evaluateRows certificate.rows) &&
  decide (certificate.output =
    widen certificate.interpolationError certificate.finiteSum)

@[simp] theorem check_eq_true {certificate : Certificate} :
    certificate.check = true ↔ certificate.IsValid := by
  simp [check, IsValid, checkRowsFrom_eq_true]
  tauto

/-- Mathematical value represented by a retained row. -/
noncomputable def rowValue (samples : ℤ → ℝ) (coefficients : ℕ → ℝ)
    (row : Row) : ℝ :=
  samples row.sourceIndex * coefficients row.coefficientIndex

/-- Mathematical forty-term fold in exactly the certificate's row order. -/
noncomputable def exactSum (samples : ℤ → ℝ) (coefficients : ℕ → ℝ) :
    List Row → ℝ
  | [] => 0
  | row :: rows =>
      rowValue samples coefficients row + exactSum samples coefficients rows

/-- Analytic and upstream obligations intentionally outside the finite
checker. -/
structure Realization (certificate : Certificate)
    (samples : ℤ → ℝ) (coefficients : ℕ → ℝ) (target : ℝ) : Prop where
  sample : ∀ row ∈ certificate.rows,
    row.sample.ContainsReal (samples row.sourceIndex)
  coefficient : ∀ row ∈ certificate.rows,
    row.coefficient.ContainsReal (coefficients row.coefficientIndex)
  interpolation : |target -
      exactSum samples coefficients certificate.rows| ≤
    (certificate.interpolationError : ℝ)

/-- Source-shaped realization of the generic arithmetic premises.

The target is the completed function at the exact factor-eight coordinate,
and each retained sample is the same function at the checked `5/64` source
coordinate.  Coefficient values remain a separate input because proving that
the 280 generated intervals contain the transcendental Gaussian--sinc table
is an independent analytic/artifact obligation. -/
structure SourceRealization (certificate : Certificate)
    (origin : ℝ) (completedValue : ℝ → ℝ)
    (coefficients : ℕ → ℝ) : Prop where
  sample : ∀ row ∈ certificate.rows,
    row.sample.ContainsReal
      (completedValue (sourceCoordinate origin row.sourceIndex))
  coefficient : ∀ row ∈ certificate.rows,
    row.coefficient.ContainsReal (coefficients row.coefficientIndex)
  interpolation :
    |completedValue (fineCoordinate origin certificate.fineIndex) -
        exactSum (completedSamples origin completedValue) coefficients
          certificate.rows| ≤
      (certificate.interpolationError : ℝ)

/-- Forgetting the explicit lattice coordinates gives the generic arithmetic
realization without adding any premise. -/
theorem SourceRealization.toRealization
    {certificate : Certificate} {origin : ℝ}
    {completedValue : ℝ → ℝ} {coefficients : ℕ → ℝ}
    (realization :
      certificate.SourceRealization origin completedValue coefficients) :
    certificate.Realization
      (completedSamples origin completedValue) coefficients
      (completedValue (fineCoordinate origin certificate.fineIndex)) := by
  exact {
    sample := realization.sample
    coefficient := realization.coefficient
    interpolation := realization.interpolation
  }

theorem row_contains (certificate : Certificate)
    (samples : ℤ → ℝ) (coefficients : ℕ → ℝ)
    {target : ℝ}
    (realization : certificate.Realization samples coefficients target)
    {row : Row} (hrow : row ∈ certificate.rows)
    {slot : ℕ} (hvalid : certificate.RowValidAt slot row) :
    row.term.ContainsReal
      (rowValue samples coefficients row) := by
  rw [hvalid.2.2.2.2.2]
  exact RatInterval.mul_containsReal
    (realization.sample row hrow)
    (realization.coefficient row hrow)

theorem evaluateRows_contains (certificate : Certificate)
    (samples : ℤ → ℝ) (coefficients : ℕ → ℝ)
    {target : ℝ}
    (realization : certificate.Realization samples coefficients target)
    {slot : ℕ} {rows : List Row}
    (hsub : ∀ row ∈ rows, row ∈ certificate.rows)
    (hvalid : certificate.RowsValidFrom slot rows) :
    (evaluateRows rows).ContainsReal
      (exactSum samples coefficients rows) := by
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
        (certificate.row_contains samples coefficients realization
          hrowMember hrowValid)
        (ih htailSub hrowsValid)

theorem widen_contains_of_abs_sub_le {value target : ℝ}
    {interval : RatInterval} {error : ℚ}
    (hvalue : interval.ContainsReal value)
    (herror : |target - value| ≤ (error : ℝ)) :
    (widen error interval).ContainsReal target := by
  have hlower : -(error : ℝ) ≤ target - value :=
    (abs_le.mp herror).1
  have hupper : target - value ≤ (error : ℝ) :=
    (abs_le.mp herror).2
  have hdelta : (RatInterval.mk (-error) error).ContainsReal
      (target - value) := by
    simpa only [RatInterval.ContainsReal, Rat.cast_neg] using
      And.intro hlower hupper
  have hadd := RatInterval.add_containsReal hvalue hdelta
  rw [show target = value + (target - value) by ring]
  exact hadd

/-- A successful check plus the explicit realization proves containment of
the true target value. -/
theorem output_contains (certificate : Certificate)
    (samples : ℤ → ℝ) (coefficients : ℕ → ℝ) (target : ℝ)
    (hcheck : certificate.check = true)
    (realization : certificate.Realization samples coefficients target) :
    certificate.output.ContainsReal target := by
  have hvalid := certificate.check_eq_true.mp hcheck
  obtain ⟨_hphase, _herror, _hlength, hrows, hsum, houtput⟩ := hvalid
  have hfinite : certificate.finiteSum.ContainsReal
      (exactSum samples coefficients certificate.rows) := by
    rw [hsum]
    exact certificate.evaluateRows_contains samples coefficients realization
      (fun _ h ↦ h) hrows
  rw [houtput]
  exact widen_contains_of_abs_sub_le hfinite realization.interpolation

/-- Source-shaped containment conclusion at the exact `5/512` target
coordinate. -/
theorem output_contains_source (certificate : Certificate)
    (origin : ℝ) (completedValue : ℝ → ℝ)
    (coefficients : ℕ → ℝ)
    (hcheck : certificate.check = true)
    (realization :
      certificate.SourceRealization origin completedValue coefficients) :
    certificate.output.ContainsReal
      (completedValue (fineCoordinate origin certificate.fineIndex)) := by
  exact certificate.output_contains
    (completedSamples origin completedValue) coefficients
    (completedValue (fineCoordinate origin certificate.fineIndex))
    hcheck realization.toRealization

theorem negative_of_checked_output {certificate : Certificate}
    {samples : ℤ → ℝ} {coefficients : ℕ → ℝ} {target : ℝ}
    (hcheck : certificate.check = true)
    (realization : certificate.Realization samples coefficients target)
    (hnegative : certificate.output.hi < 0) :
    target < 0 := by
  have hcontains :=
    certificate.output_contains samples coefficients target hcheck realization
  have hnegativeReal : (certificate.output.hi : ℝ) < 0 := by
    exact_mod_cast hnegative
  exact hcontains.2.trans_lt hnegativeReal

theorem positive_of_checked_output {certificate : Certificate}
    {samples : ℤ → ℝ} {coefficients : ℕ → ℝ} {target : ℝ}
    (hcheck : certificate.check = true)
    (realization : certificate.Realization samples coefficients target)
    (hpositive : 0 < certificate.output.lo) :
    0 < target := by
  have hcontains :=
    certificate.output_contains samples coefficients target hcheck realization
  have hpositiveReal : 0 < (certificate.output.lo : ℝ) := by
    exact_mod_cast hpositive
  exact hpositiveReal.trans_le hcontains.1

theorem negative_of_checked_source {certificate : Certificate}
    {origin : ℝ} {completedValue : ℝ → ℝ}
    {coefficients : ℕ → ℝ}
    (hcheck : certificate.check = true)
    (realization :
      certificate.SourceRealization origin completedValue coefficients)
    (hnegative : certificate.output.hi < 0) :
    completedValue (fineCoordinate origin certificate.fineIndex) < 0 := by
  exact negative_of_checked_output hcheck realization.toRealization hnegative

theorem positive_of_checked_source {certificate : Certificate}
    {origin : ℝ} {completedValue : ℝ → ℝ}
    {coefficients : ℕ → ℝ}
    (hcheck : certificate.check = true)
    (realization :
      certificate.SourceRealization origin completedValue coefficients)
    (hpositive : 0 < certificate.output.lo) :
    0 < completedValue
      (fineCoordinate origin certificate.fineIndex) := by
  exact positive_of_checked_output hcheck realization.toRealization hpositive

end Certificate

/-! ## Aligned phase -/

/-- On phase zero the uniform fine-grid coordinate is exactly the reused
source-grid coordinate. -/
theorem fineCoordinate_eq_sourceCoordinate_of_aligned
    (origin : ℝ) (fineIndex : ℕ)
    (haligned : fineIndex % upsampleFactor = 0) :
    fineCoordinate origin fineIndex =
      sourceCoordinate origin
        ((fineIndex / upsampleFactor : ℕ) : ℤ) := by
  have hdivNat :
      upsampleFactor * (fineIndex / upsampleFactor) = fineIndex := by
    have h := Nat.mod_add_div fineIndex upsampleFactor
    simpa [haligned] using h
  have hdiv : (fineIndex : ℝ) =
      (upsampleFactor : ℝ) *
        ((fineIndex / upsampleFactor : ℕ) : ℝ) := by
    exact_mod_cast hdivNat.symm
  have hsourceCast :
      (((fineIndex / upsampleFactor : ℕ) : ℤ) : ℝ) =
        ((fineIndex / upsampleFactor : ℕ) : ℝ) := by
    simp only [Int.cast_natCast]
  unfold fineCoordinate sourceCoordinate
  rw [hsourceCast, hdiv]
  norm_num [fineStep, sourceStep, upsampleFactor]
  ring

/-- At phase zero the implementation reuses the source enclosure exactly. -/
structure AlignedCertificate where
  fineIndex : ℕ
  sourceIndex : ℤ
  sample : RatInterval
  output : RatInterval
  deriving DecidableEq, Repr

namespace AlignedCertificate

def IsValid (certificate : AlignedCertificate) : Prop :=
  certificate.fineIndex % upsampleFactor = 0 ∧
    certificate.sourceIndex =
      ((certificate.fineIndex / upsampleFactor : ℕ) : ℤ) ∧
    certificate.sample.IsValid ∧
    certificate.output = certificate.sample

def check (certificate : AlignedCertificate) : Bool :=
  decide (certificate.fineIndex % upsampleFactor = 0) &&
  decide (certificate.sourceIndex =
    ((certificate.fineIndex / upsampleFactor : ℕ) : ℤ)) &&
  certificate.sample.isValid &&
  decide (certificate.output = certificate.sample)

@[simp] theorem check_eq_true {certificate : AlignedCertificate} :
    certificate.check = true ↔ certificate.IsValid := by
  simp [check, IsValid]
  tauto

theorem output_contains {certificate : AlignedCertificate}
    {value : ℝ} (hcheck : certificate.check = true)
    (hvalue : certificate.sample.ContainsReal value) :
    certificate.output.ContainsReal value := by
  rw [(certificate.check_eq_true.mp hcheck).2.2.2]
  exact hvalue

/-- Phase-zero containment stated at the same source-shaped completed-function
coordinate used by the nonaligned theorem. -/
theorem output_contains_source {certificate : AlignedCertificate}
    {origin : ℝ} {completedValue : ℝ → ℝ}
    (hcheck : certificate.check = true)
    (hvalue : certificate.sample.ContainsReal
      (completedValue
        (sourceCoordinate origin certificate.sourceIndex))) :
    certificate.output.ContainsReal
      (completedValue
        (fineCoordinate origin certificate.fineIndex)) := by
  have hvalid := certificate.check_eq_true.mp hcheck
  rw [fineCoordinate_eq_sourceCoordinate_of_aligned
    origin certificate.fineIndex hvalid.1]
  rw [← hvalid.2.1]
  exact certificate.output_contains hcheck hvalue

end AlignedCertificate

end SparkInterval.Dirichlet.Factor8Postprocess
