/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQDFTCorrectness

/-!
# Reusable signed radix-2 transforms for the windowed zeta campaign

Platt's windowed computation uses both signs of the complex DFT.  The generic
directed-disk radix-2 certificate already proves the positive-sign transform.
This module derives the negative-sign transform by conjugating the input,
running that proved network, and conjugating the output.  No new floating-point
or FFT axiom is introduced.

This is the arithmetic transform boundary only.  It does not yet prove that a
physical CUDA trace realizes the certificate, nor the analytic Platt error
bounds, Hardy-Z interpolation, zero isolation, or Turing completeness.
-/

set_option autoImplicit false

open scoped BigOperators

namespace SparkInterval.Zeta.WindowedRadix2

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQDFT

/-- Exact disk conjugation: negate the imaginary centre and retain the radius. -/
def conjugateDisk (disk : ComplexDisk) : ComplexDisk :=
  ⟨disk.re, -disk.im, disk.radius⟩

@[simp] theorem conjugateDisk_center (disk : ComplexDisk) :
    (conjugateDisk disk).center = starRingEnd ℂ disk.center := by
  apply Complex.ext
  · simp [conjugateDisk, ComplexDisk.center]
  · simp [conjugateDisk, ComplexDisk.center]

/-- Complex conjugation is an isometry, so it transports disk containment. -/
theorem conjugateDisk_contains {disk : ComplexDisk} {value : ℂ}
    (hcontains : disk.ContainsComplex value) :
    (conjugateDisk disk).ContainsComplex (starRingEnd ℂ value) := by
  rw [ComplexDisk.ContainsComplex, conjugateDisk_center]
  rw [← map_sub, Complex.norm_conj]
  exact hcontains

/-- Pointwise conjugation of an exact transform line. -/
noncomputable def conjugateExactState {logLength : Nat}
    (source : ExactState logLength) : ExactState logLength :=
  ⟨fun index => starRingEnd ℂ (source.value index)⟩

/-- Pointwise conjugation of a rational-disk transform line. -/
def conjugateDiskState {logLength : Nat}
    (source : DiskState logLength) : DiskState logLength :=
  ⟨fun index => conjugateDisk (source.value index)⟩

/-- Direct negative-sign DFT, with no normalization. -/
noncomputable def negativeDFT {logLength : Nat}
    (source : ExactState logLength) (frequency : Fin (2 ^ logLength)) : ℂ :=
  ∑ input : Fin (2 ^ logLength), source.value input *
    starRingEnd ℂ (unitRoot (2 ^ logLength) (input.val * frequency.val))

/-- The negative transform is conjugate-positive-conjugate. -/
theorem negativeDFT_eq_conjugate_positiveDFT {logLength : Nat}
    (source : ExactState logLength) (frequency : Fin (2 ^ logLength)) :
    negativeDFT source frequency =
      starRingEnd ℂ (positiveDFT (conjugateExactState source) frequency) := by
  simp only [negativeDFT, positiveDFT, conjugateExactState]
  rw [map_sum]
  apply Finset.sum_congr rfl
  intro input _hinput
  simp

/-- Conjugating every rational disk transports pointwise state containment. -/
theorem conjugateDiskState_contains {logLength : Nat}
    {disks : DiskState logLength} {exact : ExactState logLength}
    (hcontains : StateContains disks exact) :
    StateContains (conjugateDiskState disks) (conjugateExactState exact) := by
  intro index
  exact conjugateDisk_contains (hcontains index)

/-- A checked positive-sign network on conjugated inputs encloses the direct
negative-sign DFT after exact output-disk conjugation. -/
theorem output_contains_negativeDFT {logLength : Nat}
    {certificate : Certificate logLength}
    {source : ExactState logLength}
    (hcheck : certificate.check = true)
    (hbitReverse :
      StateContains certificate.input (bitReversed (conjugateExactState source)))
    (hroots : TwiddlesContain (logLength := logLength)
      certificate.twiddleDisks positiveTwiddle) :
    ∀ frequency,
      ((conjugateDiskState certificate.output).value frequency).ContainsComplex
        (negativeDFT source frequency) := by
  intro frequency
  have hpositive :=
    Certificate.output_contains_positiveDFT_unconditional
      hcheck hbitReverse hroots frequency
  have hconjugate := conjugateDisk_contains hpositive
  rw [negativeDFT_eq_conjugate_positiveDFT]
  exact hconjugate

end SparkInterval.Zeta.WindowedRadix2
