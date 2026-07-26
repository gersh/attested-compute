/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQPostprocess

/-!
# Certified scaling, time-tail inflation, untilting, and strict sign

The reduced small-`q` output stream contains the source-height Fourier samples,
not final zero-isolation evidence.  For a Fourier value `F`, Platt's next
arithmetic steps have the simple form

```
completed = (F * (2 * pi / b) + timeTail) * exp(-pi * eta * t / 4).
```

This module checks exactly that operation order with the existing rational
complex-disk multiplication and radius-inflation certificates.  It then turns
the human-readable inequalities

```
radius < centre.re       or       centre.re < -radius
```

into a strict sign theorem for a completed value known analytically to be real.
The scale, time-tail bound, untilt factor, and reality statement remain
explicit premises.  No digest, GPU execution, or source formula is assigned
mathematical meaning here.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQCompletedSign

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQPostprocess

/-- The only two outcomes admitted by a strict nonzero sign certificate. -/
inductive StrictSign where
  | negative
  | positive
  deriving Repr, DecidableEq, BEq

namespace StrictSign

/-- Ordinary mathematical meaning of a strict sign. -/
def Holds : StrictSign → ℝ → Prop
  | .negative, value => value < 0
  | .positive, value => 0 < value

/-- A disk proves a strict sign when its complete real projection lies on one
side of zero.  Euclidean-disk containment makes these rational inequalities
sufficient without a square root in the checker. -/
def CertifiedBy : StrictSign → ComplexDisk → Prop
  | .negative, disk => 0 ≤ disk.radius ∧ disk.re < -disk.radius
  | .positive, disk => 0 ≤ disk.radius ∧ disk.radius < disk.re

instance (sign : StrictSign) (disk : ComplexDisk) :
    Decidable (sign.CertifiedBy disk) := by
  cases sign <;> simp only [CertifiedBy] <;> infer_instance

/-- A disk wholly on one side of the imaginary axis proves the corresponding
sign of every real complex value that it contains. -/
theorem holds_of_contains_real {sign : StrictSign} {disk : ComplexDisk}
    {value : ℝ} (hcertified : sign.CertifiedBy disk)
    (hcontains : disk.ContainsComplex (value : ℂ)) : sign.Holds value := by
  have hreNorm := Complex.abs_re_le_norm ((value : ℂ) - disk.center)
  have hre : |value - (disk.re : ℝ)| ≤ (disk.radius : ℝ) := by
    apply hreNorm.trans hcontains
  have hbounds := abs_le.mp hre
  cases sign with
  | negative =>
      simp only [CertifiedBy] at hcertified
      simp only [Holds]
      have hcertified' : (disk.re : ℝ) < -(disk.radius : ℝ) := by
        exact_mod_cast hcertified.2
      linarith
  | positive =>
      simp only [CertifiedBy] at hcertified
      simp only [Holds]
      have hcertified' : (disk.radius : ℝ) < (disk.re : ℝ) := by
        exact_mod_cast hcertified.2
      linarith

end StrictSign

/-- Exact mathematical value after the positive scale, time-periodization
perturbation, and positive untilt.  Multiplication order matches the producer. -/
def completedValue (fourier : ℂ) (scale : ℝ) (timeTail : ℂ)
    (untilt : ℝ) : ℂ :=
  (fourier * (scale : ℂ) + timeTail) * (untilt : ℂ)

/-! ## Source-shaped positive factors -/

/-- Platt/Booker positive Fourier scale, named exactly as it appears in the
reference computation. The denominator guard is kept at theorem use sites. -/
noncomputable def sourceScale (b : ℝ) : ℝ :=
  2 * Real.pi / b

/-- Positive factor that removes the Gaussian tilt at source height `t`. -/
noncomputable def sourceUntilt (eta t : ℝ) : ℝ :=
  Real.exp (-Real.pi * eta * t / 4)

/-- Completed source expression with the paper/reference factors expanded.
This is the human-readable analytic target of the checked operation chain. -/
noncomputable def sourceCompletedValue (fourier : ℂ) (b eta t : ℝ)
    (timeTail : ℂ) : ℂ :=
  completedValue fourier (sourceScale b) timeTail (sourceUntilt eta t)

theorem sourceScale_pos {b : ℝ} (hb : 0 < b) :
    0 < sourceScale b := by
  unfold sourceScale
  positivity

theorem sourceUntilt_pos (eta t : ℝ) :
    0 < sourceUntilt eta t := by
  exact Real.exp_pos _

/-- Typed certificate for the complete post-DFT operation sequence. -/
structure Certificate where
  /-- Despite the noun order in this historical field name, the checked left
  operand is the Fourier disk and the right operand is the positive scale,
  exactly matching `transformed[index] * scale` in the Python reference. -/
  scaleTimesFourier : ComplexDisk.MulCertificate
  timeTailInflation : TailInflationCertificate
  /-- The checked left operand is the periodized disk and the right operand is
  the positive untilt factor, matching `f_value * untilt`. -/
  untiltTimesPeriodized : ComplexDisk.MulCertificate
  sign : StrictSign
  deriving Repr, DecidableEq, BEq

namespace Certificate

def output (certificate : Certificate) : ComplexDisk :=
  certificate.untiltTimesPeriodized.output

/-- Exact arithmetic links from a named Fourier disk to the final signed disk. -/
def Accepted (certificate : Certificate) (fourierDisk : ComplexDisk) : Prop :=
  certificate.scaleTimesFourier.check = true ∧
  certificate.scaleTimesFourier.left = fourierDisk ∧
  StrictSign.positive.CertifiedBy
    certificate.scaleTimesFourier.right ∧
  certificate.timeTailInflation.check = true ∧
  certificate.timeTailInflation.input =
    certificate.scaleTimesFourier.output ∧
  certificate.untiltTimesPeriodized.check = true ∧
  certificate.untiltTimesPeriodized.left =
    certificate.timeTailInflation.output ∧
  StrictSign.positive.CertifiedBy
    certificate.untiltTimesPeriodized.right ∧
  certificate.sign.CertifiedBy certificate.output

instance (certificate : Certificate) (fourierDisk : ComplexDisk) :
    Decidable (certificate.Accepted fourierDisk) := by
  unfold Accepted
  infer_instance

def check (certificate : Certificate) (fourierDisk : ComplexDisk) : Bool :=
  decide (certificate.Accepted fourierDisk)

theorem checker_sound {certificate : Certificate} {fourierDisk : ComplexDisk}
    (hcheck : certificate.check fourierDisk = true) :
    certificate.Accepted fourierDisk :=
  of_decide_eq_true hcheck

/-- The linked final disk encloses the exact completed value.  Transcendental
and analytic facts enter only through the four explicit containment/bound
premises. -/
theorem output_contains_completedValue
    {certificate : Certificate} {fourierDisk : ComplexDisk}
    {fourier : ℂ} {scale untilt : ℝ} {timeTail : ℂ}
    (hcheck : certificate.check fourierDisk = true)
    (hfourier : fourierDisk.ContainsComplex fourier)
    (hscale : certificate.scaleTimesFourier.right.ContainsComplex
      (scale : ℂ))
    (htimeTail : ‖timeTail‖ ≤
      (certificate.timeTailInflation.tailBound : ℝ))
    (huntilt : certificate.untiltTimesPeriodized.right.ContainsComplex
      (untilt : ℂ)) :
    certificate.output.ContainsComplex
      (completedValue fourier scale timeTail untilt) := by
  rcases checker_sound hcheck with
    ⟨hscaleCheck, hscaleLeft, _, htailCheck, htailInput,
      huntiltCheck, huntiltLeft, _, _⟩
  have hfourier' :
      certificate.scaleTimesFourier.left.ContainsComplex fourier := by
    rw [hscaleLeft]
    exact hfourier
  have hscaled := ComplexDisk.MulCertificate.output_contains_mul
    hscaleCheck hfourier' hscale
  have htailInputContains :
      certificate.timeTailInflation.input.ContainsComplex
        (fourier * (scale : ℂ)) := by
    rw [htailInput]
    exact hscaled
  have hperiodized := TailInflationCertificate.output_contains_add_tail
    htailCheck htailInputContains htimeTail
  have huntiltLeftContains :
      certificate.untiltTimesPeriodized.left.ContainsComplex
        (fourier * (scale : ℂ) + timeTail) := by
    rw [huntiltLeft]
    exact hperiodized
  simpa [output, completedValue] using
    (ComplexDisk.MulCertificate.output_contains_mul
      huntiltCheck huntiltLeftContains huntilt)

/-- Final strict-sign theorem.  The functional-equation fact that the
completed value is real is deliberately visible instead of being inferred
from a disk that merely overlaps the real axis. -/
theorem accepted_sign
    {certificate : Certificate} {fourierDisk : ComplexDisk}
    {fourier : ℂ} {scale untilt : ℝ} {timeTail : ℂ}
    (hcheck : certificate.check fourierDisk = true)
    (hfourier : fourierDisk.ContainsComplex fourier)
    (hscale : certificate.scaleTimesFourier.right.ContainsComplex
      (scale : ℂ))
    (htimeTail : ‖timeTail‖ ≤
      (certificate.timeTailInflation.tailBound : ℝ))
    (huntilt : certificate.untiltTimesPeriodized.right.ContainsComplex
      (untilt : ℂ))
    (hreal : (completedValue fourier scale timeTail untilt).im = 0) :
    certificate.sign.Holds
      (completedValue fourier scale timeTail untilt).re := by
  have hcontains := output_contains_completedValue hcheck hfourier hscale
    htimeTail huntilt
  have heq :
      ((completedValue fourier scale timeTail untilt).re : ℂ) =
        completedValue fourier scale timeTail untilt := by
    apply Complex.ext
    · simp
    · simpa using hreal.symm
  rw [← heq] at hcontains
  exact StrictSign.holds_of_contains_real
    (checker_sound hcheck).2.2.2.2.2.2.2.2 hcontains

/-- Source-shaped strict-sign corollary.  It is deliberately derived from the
generic disk theorem: the stronger reusable checker is unchanged, while a
reader sees the exact `2*pi/b` and `exp(-pi*eta*t/4)` factors used by the
analytic source.  All numerical containments, the complex-norm time-tail
bound, and functional-equation reality remain explicit premises. -/
theorem accepted_source_sign
    {certificate : Certificate} {fourierDisk : ComplexDisk}
    {fourier timeTail : ℂ} {b eta t : ℝ}
    (hb : 0 < b)
    (hcheck : certificate.check fourierDisk = true)
    (hfourier : fourierDisk.ContainsComplex fourier)
    (hscale : certificate.scaleTimesFourier.right.ContainsComplex
      (sourceScale b : ℂ))
    (htimeTail : ‖timeTail‖ ≤
      (certificate.timeTailInflation.tailBound : ℝ))
    (huntilt : certificate.untiltTimesPeriodized.right.ContainsComplex
      (sourceUntilt eta t : ℂ))
    (hreal : (sourceCompletedValue fourier b eta t timeTail).im = 0) :
    0 < b ∧ certificate.sign.Holds
      (sourceCompletedValue fourier b eta t timeTail).re := by
  refine ⟨hb, ?_⟩
  simpa [sourceCompletedValue] using
    (accepted_sign hcheck hfourier hscale htimeTail huntilt hreal)

/-- The two rational factor disks checked by an accepted certificate lie
strictly in the positive real half-plane.  Consequently the exact real scale
and untilt values supplied to the containment theorem are positive.  This is
the arithmetic fact needed to match Python's positive `2*pi/b` and
`exp(-pi*eta*t/4)` factors, rather than merely accepting arbitrary real
multipliers. -/
theorem accepted_factors_positive
    {certificate : Certificate} {fourierDisk : ComplexDisk}
    {scale untilt : ℝ}
    (hcheck : certificate.check fourierDisk = true)
    (hscale : certificate.scaleTimesFourier.right.ContainsComplex
      (scale : ℂ))
    (huntilt : certificate.untiltTimesPeriodized.right.ContainsComplex
      (untilt : ℂ)) :
    0 < scale ∧ 0 < untilt := by
  have haccepted := checker_sound hcheck
  constructor
  · exact StrictSign.holds_of_contains_real haccepted.2.2.1 hscale
  · exact StrictSign.holds_of_contains_real
      haccepted.2.2.2.2.2.2.2.1 huntilt

end Certificate

end SparkInterval.Dirichlet.FactoredSmallQCompletedSign
