/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.WindowedRadix2

/-!
# Complex-disk primitives for the Platt source-semantic transform

`WindowedRadix2` already proves both signs of the disk FFT from checked
butterfly traces.  This module supplies the remaining exact unary operations
used by the CUDA disk prototype and a checked composition for the exceptional
endpoint in Platt's literal `hermidft` preprocessing.

Addition and multiplication are not re-axiomatized: every nontrivial binary
operation is a `ComplexDisk.AddCertificate` or `MulCertificate`, whose exact
rational checker and containment theorem already live in
`Certified/ComplexDisk.lean`.

The physical CUDA program remains a producer.  A production bridge must bind
its binary64 words and instruction trace (or an independently replayed trace)
to these rational certificate values.  This file proves the mathematical
pipeline once that binding is supplied; it does not assert that an arbitrary
GPU execution realizes it.  There is no axiom, `sorry`, or `native_decide`.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.PlattDiskPipeline

open SparkInterval.Certified

/-- Exact disk negation. -/
def negateDisk (disk : ComplexDisk) : ComplexDisk :=
  ⟨-disk.re, -disk.im, disk.radius⟩

@[simp] theorem negateDisk_center (disk : ComplexDisk) :
    (negateDisk disk).center = -disk.center := by
  apply Complex.ext <;> simp [negateDisk, ComplexDisk.center]

theorem negateDisk_contains {disk : ComplexDisk} {value : ℂ}
    (hcontains : disk.ContainsComplex value) :
    (negateDisk disk).ContainsComplex (-value) := by
  rw [ComplexDisk.ContainsComplex, negateDisk_center]
  calc
    ‖-value - -disk.center‖ = ‖value - disk.center‖ := by
      rw [neg_sub_neg]
      exact norm_sub_rev disk.center value
    _ ≤ (disk.radius : ℝ) := hcontains

/-- Exact multiplication by `i`. -/
def timesIDisk (disk : ComplexDisk) : ComplexDisk :=
  ⟨-disk.im, disk.re, disk.radius⟩

@[simp] theorem timesIDisk_center (disk : ComplexDisk) :
    (timesIDisk disk).center = Complex.I * disk.center := by
  apply Complex.ext <;>
    simp [timesIDisk, ComplexDisk.center, Complex.mul_re, Complex.mul_im]

theorem timesIDisk_contains {disk : ComplexDisk} {value : ℂ}
    (hcontains : disk.ContainsComplex value) :
    (timesIDisk disk).ContainsComplex (Complex.I * value) := by
  rw [ComplexDisk.ContainsComplex, timesIDisk_center]
  have hfactor : Complex.I * value - Complex.I * disk.center =
      Complex.I * (value - disk.center) := by ring
  rw [hfactor, Complex.norm_mul, Complex.norm_I, one_mul]
  exact hcontains

/-- Project a complex disk onto its real coordinate, retaining the original
radius.  This is conservative because coordinate error is at most Euclidean
error. -/
def realProjectionDisk (disk : ComplexDisk) : ComplexDisk :=
  ⟨disk.re, 0, disk.radius⟩

@[simp] theorem realProjectionDisk_center (disk : ComplexDisk) :
    (realProjectionDisk disk).center = (disk.re : ℂ) := by
  apply Complex.ext <;> simp [realProjectionDisk, ComplexDisk.center]

theorem realProjectionDisk_contains {disk : ComplexDisk} {value : ℂ}
    (hcontains : disk.ContainsComplex value) :
    (realProjectionDisk disk).ContainsComplex (value.re : ℂ) := by
  rw [ComplexDisk.ContainsComplex, realProjectionDisk_center]
  simp only [realProjectionDisk]
  have hsub : (value.re : ℂ) - (disk.re : ℂ) =
      ((value.re - (disk.re : ℝ) : ℝ) : ℂ) := by
    apply Complex.ext <;> simp
  rw [hsub, Complex.norm_real, Real.norm_eq_abs]
  have hre := Complex.abs_re_le_norm (value - disk.center)
  simpa only [Complex.sub_re, ComplexDisk.center_re] using hre.trans hcontains

/-- Increase only the Euclidean radius by an exact rational budget. -/
def widenDisk (budget : ℚ) (disk : ComplexDisk) : ComplexDisk :=
  ⟨disk.re, disk.im, disk.radius + budget⟩

@[simp] theorem widenDisk_center (budget : ℚ) (disk : ComplexDisk) :
    (widenDisk budget disk).center = disk.center := rfl

/-- A norm-bounded perturbation of a contained value is contained after
radius widening. -/
theorem widenDisk_contains_of_norm_sub_le
    {disk : ComplexDisk} {budget : ℚ} {main target : ℂ}
    (hmain : disk.ContainsComplex main)
    (herror : ‖target - main‖ ≤ (budget : ℝ)) :
    (widenDisk budget disk).ContainsComplex target := by
  rw [ComplexDisk.ContainsComplex, widenDisk_center]
  have hdecomp : target - disk.center =
      (target - main) + (main - disk.center) := by ring
  rw [hdecomp]
  calc
    ‖(target - main) + (main - disk.center)‖ ≤
        ‖target - main‖ + ‖main - disk.center‖ := norm_add_le _ _
    _ ≤ (budget : ℝ) + (disk.radius : ℝ) := add_le_add herror hmain
    _ = ((disk.radius + budget : ℚ) : ℝ) := by push_cast; ring

/-- A coordinate square `[-e,e] + i[-e,e]` fits a Euclidean budget whose
square is at least `2e^2`.  The CUDA producer computes such a budget with an
upward stable hypotenuse; Lean checks only this exact rational inequality. -/
theorem norm_le_of_coordinate_square
    {delta : ℂ} {coordinateBudget diskBudget : ℚ}
    (hcoordinate : 0 ≤ coordinateBudget)
    (hdisk : 0 ≤ diskBudget)
    (hre : |delta.re| ≤ (coordinateBudget : ℝ))
    (him : |delta.im| ≤ (coordinateBudget : ℝ))
    (hsquare : 2 * coordinateBudget ^ 2 ≤ diskBudget ^ 2) :
    ‖delta‖ ≤ (diskBudget : ℝ) := by
  have hcoordinateR : (0 : ℝ) ≤ (coordinateBudget : ℝ) := by
    exact_mod_cast hcoordinate
  have hdiskR : (0 : ℝ) ≤ (diskBudget : ℝ) := by
    exact_mod_cast hdisk
  have hsquareR : 2 * (coordinateBudget : ℝ) ^ 2 ≤
      (diskBudget : ℝ) ^ 2 := by exact_mod_cast hsquare
  have hreSq : delta.re ^ 2 ≤ (coordinateBudget : ℝ) ^ 2 := by
    calc
      delta.re ^ 2 = |delta.re| ^ 2 := (sq_abs delta.re).symm
      _ ≤ (coordinateBudget : ℝ) ^ 2 :=
        pow_le_pow_left₀ (abs_nonneg delta.re) hre 2
  have himSq : delta.im ^ 2 ≤ (coordinateBudget : ℝ) ^ 2 := by
    calc
      delta.im ^ 2 = |delta.im| ^ 2 := (sq_abs delta.im).symm
      _ ≤ (coordinateBudget : ℝ) ^ 2 :=
        pow_le_pow_left₀ (abs_nonneg delta.im) him 2
  have hnormSq : ‖delta‖ ^ 2 ≤ (diskBudget : ℝ) ^ 2 := by
    rw [Complex.sq_norm, Complex.normSq_apply]
    nlinarith
  nlinarith [norm_nonneg delta]

/-- Source-style Cartesian error widening, represented by one disk budget. -/
theorem widenDisk_contains_coordinate_error
    {disk : ComplexDisk} {coordinateBudget diskBudget : ℚ}
    {main target : ℂ}
    (hcoordinate : 0 ≤ coordinateBudget)
    (hdisk : 0 ≤ diskBudget)
    (hmain : disk.ContainsComplex main)
    (hre : |(target - main).re| ≤ (coordinateBudget : ℝ))
    (him : |(target - main).im| ≤ (coordinateBudget : ℝ))
    (hsquare : 2 * coordinateBudget ^ 2 ≤ diskBudget ^ 2) :
    (widenDisk diskBudget disk).ContainsComplex target :=
  widenDisk_contains_of_norm_sub_le hmain
    (norm_le_of_coordinate_square hcoordinate hdisk hre him hsquare)

/-- Exact disks for the two constants used by Platt's exceptional Hermitian
endpoint: `(1+i) Re x + (1-i) Re y`. -/
def onePlusI : ComplexDisk := ⟨1, 1, 0⟩
def oneMinusI : ComplexDisk := ⟨1, -1, 0⟩

theorem onePlusI_contains : onePlusI.ContainsComplex (1 + Complex.I) := by
  have hcenter : onePlusI.center = 1 + Complex.I := by
    apply Complex.ext <;>
      norm_num [onePlusI, ComplexDisk.center]
  rw [ComplexDisk.ContainsComplex, hcenter, sub_self, norm_zero]
  norm_num [onePlusI]

theorem oneMinusI_contains : oneMinusI.ContainsComplex (1 - Complex.I) := by
  have hcenter : oneMinusI.center = 1 - Complex.I := by
    apply Complex.ext <;>
      norm_num [oneMinusI, ComplexDisk.center]
  rw [ComplexDisk.ContainsComplex, hcenter, sub_self, norm_zero]
  norm_num [oneMinusI]

/-- Complex value assigned to index zero by `arb_fft.h::hermidft`. -/
def hermidftEndpoint (left right : ℂ) : ℂ :=
  ⟨left.re + right.re, left.re - right.re⟩

theorem hermidftEndpoint_eq (left right : ℂ) :
    hermidftEndpoint left right =
      (left.re : ℂ) * (1 + Complex.I) +
        (right.re : ℂ) * (1 - Complex.I) := by
  apply Complex.ext
  · simp [hermidftEndpoint, Complex.mul_re]
  · simp [hermidftEndpoint, Complex.mul_im]
    ring

/-- Three checked binary operations implementing the exceptional endpoint.
The linking equalities prevent valid but unrelated Add/Mul witnesses from
being substituted. -/
structure HermidftEndpointCertificate where
  leftInput : ComplexDisk
  rightInput : ComplexDisk
  leftMul : ComplexDisk.MulCertificate
  rightMul : ComplexDisk.MulCertificate
  outputAdd : ComplexDisk.AddCertificate
  deriving Repr, DecidableEq

namespace HermidftEndpointCertificate

def IsValid (certificate : HermidftEndpointCertificate) : Prop :=
  certificate.leftMul.left = realProjectionDisk certificate.leftInput ∧
    certificate.leftMul.right = onePlusI ∧
    certificate.rightMul.left = realProjectionDisk certificate.rightInput ∧
    certificate.rightMul.right = oneMinusI ∧
    certificate.outputAdd.left = certificate.leftMul.output ∧
    certificate.outputAdd.right = certificate.rightMul.output ∧
    certificate.leftMul.WellFormed ∧
    certificate.rightMul.WellFormed ∧
    certificate.outputAdd.WellFormed

instance (certificate : HermidftEndpointCertificate) :
    Decidable certificate.IsValid := by
  unfold IsValid
  infer_instance

def check (certificate : HermidftEndpointCertificate) : Bool :=
  decide certificate.IsValid

@[simp] theorem check_eq_true {certificate : HermidftEndpointCertificate} :
    certificate.check = true ↔ certificate.IsValid := by
  simp [check]

/-- The checked endpoint disk contains the literal upstream endpoint value. -/
theorem output_contains
    {certificate : HermidftEndpointCertificate} {left right : ℂ}
    (hcheck : certificate.check = true)
    (hleft : certificate.leftInput.ContainsComplex left)
    (hright : certificate.rightInput.ContainsComplex right) :
    certificate.outputAdd.output.ContainsComplex
      (hermidftEndpoint left right) := by
  rcases certificate.check_eq_true.mp hcheck with
    ⟨hleftInput, hleftConstant, hrightInput, hrightConstant,
      haddLeft, haddRight, hleftMul, hrightMul, hadd⟩
  have hleftProduct : certificate.leftMul.output.ContainsComplex
      ((left.re : ℂ) * (1 + Complex.I)) := by
    apply ComplexDisk.MulCertificate.output_contains_mul
      (certificate := certificate.leftMul) (decide_eq_true hleftMul)
    · rw [hleftInput]
      exact realProjectionDisk_contains hleft
    · rw [hleftConstant]
      exact onePlusI_contains
  have hrightProduct : certificate.rightMul.output.ContainsComplex
      ((right.re : ℂ) * (1 - Complex.I)) := by
    apply ComplexDisk.MulCertificate.output_contains_mul
      (certificate := certificate.rightMul) (decide_eq_true hrightMul)
    · rw [hrightInput]
      exact realProjectionDisk_contains hright
    · rw [hrightConstant]
      exact oneMinusI_contains
  rw [hermidftEndpoint_eq]
  apply ComplexDisk.AddCertificate.output_contains_add
    (certificate := certificate.outputAdd) (decide_eq_true hadd)
  · rw [haddLeft]
    exact hleftProduct
  · rw [haddRight]
    exact hrightProduct

end HermidftEndpointCertificate

end SparkInterval.Zeta.PlattDiskPipeline
