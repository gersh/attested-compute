/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQGaussianSum

/-!
# Typed postprocessing for a factored small-`q` Gaussian sum

The CUDA finite-Gaussian kernel performs these operations, in this order:

1. multiply the prefactor disk by the accumulated finite-sum disk;
2. for a negative frequency, negate the imaginary coordinate of the result;
3. add the nonnegative analytic-tail bound to the result radius.

This file gives that postprocessing sequence an exact-rational certificate
checker and a complex-disk containment theorem.  Conjugation is exact: it
changes only the sign of the centre's imaginary coordinate and leaves the
radius unchanged.  Radius inflation permits an output radius greater than the
exact rational sum, which models an upward-rounded binary64 addition after
the words have been decoded.

The result is an arithmetic theorem about typed certificates.  It does not
claim that a raw frame was decoded, that a CUDA execution produced these
values, or that the analytic tail premise holds for a particular source
formula.
-/

set_option autoImplicit false

open scoped ComplexConjugate

namespace SparkInterval.Dirichlet.FactoredSmallQPostprocess

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQGaussianSum

/-- Exact effect of the CUDA negative-frequency branch on a disk. -/
def conjugateDisk (disk : ComplexDisk) : ComplexDisk :=
  ⟨disk.re, -disk.im, disk.radius⟩

@[simp] theorem conjugateDisk_re (disk : ComplexDisk) :
    (conjugateDisk disk).re = disk.re := rfl

@[simp] theorem conjugateDisk_im (disk : ComplexDisk) :
    (conjugateDisk disk).im = -disk.im := rfl

@[simp] theorem conjugateDisk_radius (disk : ComplexDisk) :
    (conjugateDisk disk).radius = disk.radius := rfl

@[simp] theorem conjugateDisk_center (disk : ComplexDisk) :
    (conjugateDisk disk).center = conj disk.center := by
  apply Complex.ext <;>
    simp [conjugateDisk, ComplexDisk.center]

/-- Conjugating the centre of a Euclidean disk and preserving its radius
contains the conjugate of every value in the original disk. -/
theorem conjugateDisk_contains {disk : ComplexDisk} {value : ℂ}
    (hcontains : disk.ContainsComplex value) :
    (conjugateDisk disk).ContainsComplex (conj value) := by
  rw [ComplexDisk.ContainsComplex, conjugateDisk_center]
  rw [← map_sub, Complex.norm_conj]
  exact hcontains

/-- Apply the exact sign branch used after prefactor multiplication. -/
def applyFrequencySign (negativeFrequency : Bool)
    (disk : ComplexDisk) : ComplexDisk :=
  if negativeFrequency then conjugateDisk disk else disk

/-- Mathematical value corresponding to `applyFrequencySign`. -/
def applyFrequencySignValue (negativeFrequency : Bool) (value : ℂ) : ℂ :=
  if negativeFrequency then conj value else value

/-- The exact sign branch preserves disk containment. -/
theorem applyFrequencySign_contains {negativeFrequency : Bool}
    {disk : ComplexDisk} {value : ℂ}
    (hcontains : disk.ContainsComplex value) :
    (applyFrequencySign negativeFrequency disk).ContainsComplex
      (applyFrequencySignValue negativeFrequency value) := by
  cases negativeFrequency with
  | false => simpa [applyFrequencySign, applyFrequencySignValue] using hcontains
  | true =>
      simpa [applyFrequencySign, applyFrequencySignValue] using
        (conjugateDisk_contains hcontains)

/-! ## Analytic-tail radius inflation -/

/-- A proposed radius-only update.  The centre must be unchanged, and the
new radius must dominate the exact sum of the old radius and tail bound. -/
structure TailInflationCertificate where
  input : ComplexDisk
  tailBound : ℚ
  output : ComplexDisk
  deriving Repr, DecidableEq, BEq

namespace TailInflationCertificate

def WellFormed (certificate : TailInflationCertificate) : Prop :=
  0 ≤ certificate.input.radius ∧
  0 ≤ certificate.tailBound ∧
  0 ≤ certificate.output.radius ∧
  certificate.output.re = certificate.input.re ∧
  certificate.output.im = certificate.input.im ∧
  certificate.input.radius + certificate.tailBound ≤
    certificate.output.radius

instance instDecidableWellFormed (certificate : TailInflationCertificate) :
    Decidable certificate.WellFormed := by
  unfold WellFormed
  infer_instance

def check (certificate : TailInflationCertificate) : Bool :=
  decide certificate.WellFormed

theorem check_sound {certificate : TailInflationCertificate}
    (hcheck : certificate.check = true) : certificate.WellFormed :=
  of_decide_eq_true hcheck

/-- Inflating a disk radius by `tailBound` contains every additive complex
perturbation whose norm is at most that bound. -/
theorem output_contains_add_tail {certificate : TailInflationCertificate}
    {value delta : ℂ}
    (hcheck : certificate.check = true)
    (hvalue : certificate.input.ContainsComplex value)
    (hdelta : ‖delta‖ ≤ (certificate.tailBound : ℝ)) :
    certificate.output.ContainsComplex (value + delta) := by
  rcases check_sound hcheck with
    ⟨_, _, _, hre, him, hradius⟩
  have hcenter : certificate.output.center = certificate.input.center := by
    apply Complex.ext <;>
      simp [ComplexDisk.center, hre, him]
  have hvalue' :
      ‖value - certificate.input.center‖ ≤
        (certificate.input.radius : ℝ) := hvalue
  rw [ComplexDisk.ContainsComplex, hcenter]
  calc
    ‖value + delta - certificate.input.center‖ =
        ‖(value - certificate.input.center) + delta‖ := by ring_nf
    _ ≤ ‖value - certificate.input.center‖ + ‖delta‖ :=
      norm_add_le _ _
    _ ≤ (certificate.input.radius : ℝ) + certificate.tailBound := by
      linarith
    _ ≤ (certificate.output.radius : ℝ) := by
      exact_mod_cast hradius

end TailInflationCertificate

/-! ## Linked postprocessing certificate -/

/-- Typed witness for the complete post-Gaussian sequence.  Link equalities
ensure that individually valid multiplication and inflation witnesses cannot
be substituted or reordered. -/
structure Certificate where
  finiteSum : SumTraceCertificate
  prefactor : ComplexDisk
  prefactorTimesSum : ComplexDisk.MulCertificate
  negativeFrequency : Bool
  tailInflation : TailInflationCertificate
  deriving Repr, DecidableEq, BEq

namespace Certificate

def output (certificate : Certificate) : ComplexDisk :=
  certificate.tailInflation.output

/-- Exact arithmetic and state-link obligations in CUDA operation order. -/
def Accepted (certificate : Certificate) (maxTerms : ℕ) : Prop :=
  certificate.finiteSum.check maxTerms = true ∧
  certificate.prefactorTimesSum.check = true ∧
  certificate.prefactorTimesSum.left = certificate.prefactor ∧
  certificate.prefactorTimesSum.right = certificate.finiteSum.output ∧
  certificate.tailInflation.check = true ∧
  certificate.tailInflation.input =
    applyFrequencySign certificate.negativeFrequency
      certificate.prefactorTimesSum.output

instance instDecidableAccepted (certificate : Certificate) (maxTerms : ℕ) :
    Decidable (certificate.Accepted maxTerms) := by
  unfold Accepted
  infer_instance

/-- Kernel-reducible checker over exact rationals and structural links. -/
def check (certificate : Certificate) (maxTerms : ℕ) : Bool :=
  decide (certificate.Accepted maxTerms)

theorem checker_sound {certificate : Certificate} {maxTerms : ℕ}
    (hcheck : certificate.check maxTerms = true) :
    certificate.Accepted maxTerms :=
  of_decide_eq_true hcheck

/-- Compositional arithmetic theorem when containment of the finite sum is
already available.  This isolates postprocessing from the Gaussian trace. -/
theorem output_contains_from_finite_sum
    {certificate : Certificate} {maxTerms : ℕ}
    {finiteSum prefactor delta : ℂ}
    (hcheck : certificate.check maxTerms = true)
    (hsum : certificate.finiteSum.output.ContainsComplex finiteSum)
    (hprefactor : certificate.prefactor.ContainsComplex prefactor)
    (hdelta : ‖delta‖ ≤ (certificate.tailInflation.tailBound : ℝ)) :
    certificate.output.ContainsComplex
      (applyFrequencySignValue certificate.negativeFrequency
          (prefactor * finiteSum) + delta) := by
  rcases checker_sound hcheck with
    ⟨_, hmulCheck, hmulLeft, hmulRight, htailCheck, htailInput⟩
  have hleft :
      certificate.prefactorTimesSum.left.ContainsComplex prefactor := by
    rw [hmulLeft]
    exact hprefactor
  have hright :
      certificate.prefactorTimesSum.right.ContainsComplex finiteSum := by
    rw [hmulRight]
    exact hsum
  have hproduct := ComplexDisk.MulCertificate.output_contains_mul
    hmulCheck hleft hright
  have hsigned := applyFrequencySign_contains
    (negativeFrequency := certificate.negativeFrequency) hproduct
  have htailInputContains :
      certificate.tailInflation.input.ContainsComplex
        (applyFrequencySignValue certificate.negativeFrequency
          (prefactor * finiteSum)) := by
    rw [htailInput]
    exact hsigned
  exact TailInflationCertificate.output_contains_add_tail
    htailCheck htailInputContains hdelta

/-- End-to-end typed arithmetic theorem.  It composes the checked Gaussian
sum, prefactor multiplication, optional negative-frequency conjugation, and
analytic-tail inflation. -/
theorem output_contains_exact_finite_sum
    {certificate : Certificate} {maxTerms : ℕ}
    {characters : List ℂ} {w prefactor delta : ℂ}
    (hcheck : certificate.check maxTerms = true)
    (hbase : certificate.finiteSum.seed.base.ContainsComplex w)
    (hcharacters : ContainsCharacters certificate.finiteSum.rows characters)
    (hprefactor : certificate.prefactor.ContainsComplex prefactor)
    (hdelta : ‖delta‖ ≤ (certificate.tailInflation.tailBound : ℝ)) :
    characters.length = certificate.finiteSum.truncation ∧
      certificate.output.ContainsComplex
        (applyFrequencySignValue certificate.negativeFrequency
            (prefactor * exactFiniteSum certificate.finiteSum.oddParity
              w characters) + delta) := by
  have haccepted := checker_sound hcheck
  have hfinite := SumTraceCertificate.output_contains_exact_finite_sum
    haccepted.1 hbase hcharacters
  exact ⟨hfinite.1,
    output_contains_from_finite_sum hcheck hfinite.2 hprefactor hdelta⟩

end Certificate

end SparkInterval.Dirichlet.FactoredSmallQPostprocess
