/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQTrace

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQTrace

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQTrace

def oneDisk : ComplexDisk := ⟨1, 0, 0⟩

/-- Exact witness for `(1 + 0i) * (1 + 0i)`. -/
def oneMul : ComplexDisk.MulCertificate := {
  left := oneDisk
  right := oneDisk
  output := oneDisk
  centerErrorBound := 0
  leftCenterNormBound := 1
  rightCenterNormBound := 1
}

def oneStep : StepCertificate :=
  ⟨oneMul, oneMul⟩

/-- Two linked rows, representing recurrence indices zero through two. -/
def sample : TraceCertificate := {
  base := oneDisk
  square := oneMul
  cube := oneMul
  steps := [oneStep, oneStep]
}

theorem sample_check : sample.check 2 = true := by
  norm_num [sample, oneStep, oneMul, oneDisk, TraceCertificate.check,
    TraceCertificate.InitialWellFormed, TraceCertificate.initialState,
    checkLinked, StepCertificate.output, StepCertificate.check,
    StepCertificate.WellFormed, ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

theorem oneDisk_contains_one : oneDisk.ContainsComplex (1 : ℂ) := by
  unfold ComplexDisk.ContainsComplex
  have hcenter : oneDisk.center = (1 : ℂ) := by
    apply Complex.ext <;> norm_num [oneDisk, ComplexDisk.center]
  rw [hcenter]
  norm_num [oneDisk]

example : sample.output.z.ContainsComplex
    ((1 : ℂ) ^ ((sample.steps.length + 1) ^ 2)) :=
  (TraceCertificate.output_contains_powers
    sample_check oneDisk_contains_one).1

example : sample.output.ratio.ContainsComplex
    (SparkInterval.Dirichlet.FactoredSmallQSeed.ExactGaussianState.after
      (1 : ℂ) sample.steps.length).ratio :=
  (TraceCertificate.output_contains_exact_after
    sample_check oneDisk_contains_one).2

/-- This multiplication is arithmetically valid, but it cannot be substituted
for the first `z * ratio` row because its left disk is not the current `z`. -/
def zeroDisk : ComplexDisk := ⟨0, 0, 0⟩

def zeroMul : ComplexDisk.MulCertificate := {
  left := zeroDisk
  right := oneDisk
  output := zeroDisk
  centerErrorBound := 0
  leftCenterNormBound := 0
  rightCenterNormBound := 1
}

def brokenLinkStep : StepCertificate :=
  ⟨zeroMul, oneMul⟩

def brokenLink : TraceCertificate :=
  { sample with steps := [brokenLinkStep] }

theorem broken_link_fails_closed : brokenLink.check 1 = false := by
  norm_num [brokenLink, brokenLinkStep, sample, zeroMul, zeroDisk, oneMul,
    oneDisk, TraceCertificate.check, TraceCertificate.InitialWellFormed,
    TraceCertificate.initialState, checkLinked, StepCertificate.output,
    StepCertificate.check, StepCertificate.WellFormed,
    ComplexDisk.MulCertificate.check, ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

/-- The explicit caller bound is part of acceptance, independently of the
validity of every arithmetic row. -/
theorem over_bound_fails_closed : sample.check 1 = false := by
  norm_num [sample, oneStep, oneMul, oneDisk, TraceCertificate.check,
    TraceCertificate.InitialWellFormed, TraceCertificate.initialState,
    checkLinked, StepCertificate.output, StepCertificate.check,
    StepCertificate.WellFormed, ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

/-- A locally linked row with an invalid output radius also fails closed. -/
def negativeRadiusMul : ComplexDisk.MulCertificate :=
  { oneMul with output := ⟨1, 0, -1⟩ }

def brokenArithmeticStep : StepCertificate :=
  ⟨negativeRadiusMul, oneMul⟩

def brokenArithmetic : TraceCertificate :=
  { sample with steps := [brokenArithmeticStep] }

theorem broken_arithmetic_fails_closed :
    brokenArithmetic.check 1 = false := by
  norm_num [brokenArithmetic, brokenArithmeticStep, negativeRadiusMul, sample,
    oneMul, oneDisk, TraceCertificate.check,
    TraceCertificate.InitialWellFormed, TraceCertificate.initialState,
    checkLinked, StepCertificate.output, StepCertificate.check,
    StepCertificate.WellFormed, ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

#print axioms StepCertificate.check_sound
#print axioms StepCertificate.output_contains_powers
#print axioms checkLinked_sound
#print axioms TraceCertificate.checker_sound
#print axioms TraceCertificate.output_contains_powers
#print axioms TraceCertificate.output_contains_exact_after
#print axioms sample_check
#print axioms broken_link_fails_closed
#print axioms over_bound_fails_closed
#print axioms broken_arithmetic_fails_closed

end SparkInterval.Tests.FactoredSmallQTrace
