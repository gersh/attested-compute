/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawTrace

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQRawTrace

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQSeed
open SparkInterval.Dirichlet.FactoredSmallQTrace
open SparkInterval.Dirichlet.FactoredSmallQRawTrace

def oneDisk : ComplexDisk := ⟨1, 0, 0⟩

def oneMul : ComplexDisk.MulCertificate := {
  left := oneDisk
  right := oneDisk
  output := oneDisk
  centerErrorBound := 0
  leftCenterNormBound := 1
  rightCenterNormBound := 1
}

def oneStep : StepCertificate := ⟨oneMul, oneMul⟩

def typedSample : TraceCertificate := {
  base := oneDisk
  square := oneMul
  cube := oneMul
  steps := [oneStep, oneStep]
}

def rawOneDisk : ComplexDisk.Raw :=
  ⟨0x3ff0000000000000, 0x0000000000000000, 0x0000000000000000⟩

def rawOneMul : ComplexDisk.RawMulCertificate := {
  left := rawOneDisk
  right := rawOneDisk
  output := rawOneDisk
  centerErrorBoundBits := 0x0000000000000000
  leftCenterNormBoundBits := 0x3ff0000000000000
  rightCenterNormBoundBits := 0x3ff0000000000000
}

def rawOneStep : RawStepCertificate := ⟨rawOneMul, rawOneMul⟩

def rawSample : RawTraceCertificate := {
  base := rawOneDisk
  square := rawOneMul
  cube := rawOneMul
  steps := [rawOneStep, rawOneStep]
}

theorem rawOneDisk_decode : rawOneDisk.decode = some oneDisk := by
  norm_num [rawOneDisk, oneDisk, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem rawOneMul_decode : rawOneMul.decode = some oneMul := by
  norm_num [rawOneMul, oneMul, rawOneDisk, oneDisk,
    ComplexDisk.RawMulCertificate.decode, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem rawSample_decode : rawSample.decode = some typedSample := by
  simp [rawSample, typedSample, RawTraceCertificate.decode, decodeSteps,
    rawOneStep, oneStep, RawStepCertificate.decode, rawOneMul_decode,
    rawOneDisk_decode]

theorem typedSample_check : typedSample.check 2 = true := by
  norm_num [typedSample, oneStep, oneMul, oneDisk, TraceCertificate.check,
    TraceCertificate.InitialWellFormed, TraceCertificate.initialState,
    checkLinked, StepCertificate.output, StepCertificate.check,
    StepCertificate.WellFormed, ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

theorem rawSample_check : rawSample.check 2 = true := by
  rw [RawTraceCertificate.check]
  have hbound : decide (rawSample.steps.length ≤ 2) = true := by
    norm_num [rawSample]
  rw [hbound]
  simp only [Bool.true_and]
  rw [rawSample_decode]
  exact typedSample_check

theorem oneDisk_contains_one : oneDisk.ContainsComplex (1 : ℂ) := by
  unfold ComplexDisk.ContainsComplex
  have hcenter : oneDisk.center = (1 : ℂ) := by
    apply Complex.ext <;> norm_num [oneDisk, ComplexDisk.center]
  rw [hcenter]
  norm_num [oneDisk]

example :
    ∃ certificate : TraceCertificate,
      rawSample.decode = some certificate ∧
      certificate.output.z.ContainsComplex
          (ExactGaussianState.after (1 : ℂ) rawSample.steps.length).z ∧
      certificate.output.ratio.ContainsComplex
          (ExactGaussianState.after (1 : ℂ) rawSample.steps.length).ratio := by
  exact RawTraceCertificate.accepted_output_contains_exact_after_of_base_decode
    rawSample_check rawOneDisk_decode oneDisk_contains_one

/-! A nontrivial unit-circle fixture exercises the exponent recurrence:
starting from `w = i`, one update changes `(z, ratio)` from `(i, -i)` to
`(1, i)`, agreeing with `(i^4, i^5)`. -/

def iDisk : ComplexDisk := ⟨0, 1, 0⟩
def negOneDisk : ComplexDisk := ⟨-1, 0, 0⟩
def negIDisk : ComplexDisk := ⟨0, -1, 0⟩

def exactUnitMul (left right output : ComplexDisk) :
    ComplexDisk.MulCertificate := {
  left, right, output
  centerErrorBound := 0
  leftCenterNormBound := 1
  rightCenterNormBound := 1
}

def typedISample : TraceCertificate := {
  base := iDisk
  square := exactUnitMul iDisk iDisk negOneDisk
  cube := exactUnitMul negOneDisk iDisk negIDisk
  steps := [
    ⟨exactUnitMul iDisk negIDisk oneDisk,
      exactUnitMul negIDisk negOneDisk iDisk⟩
  ]
}

def rawIDisk : ComplexDisk.Raw :=
  ⟨0x0000000000000000, 0x3ff0000000000000, 0x0000000000000000⟩
def rawNegOneDisk : ComplexDisk.Raw :=
  ⟨0xbff0000000000000, 0x0000000000000000, 0x0000000000000000⟩
def rawNegIDisk : ComplexDisk.Raw :=
  ⟨0x0000000000000000, 0xbff0000000000000, 0x0000000000000000⟩

def rawExactUnitMul (left right output : ComplexDisk.Raw) :
    ComplexDisk.RawMulCertificate := {
  left, right, output
  centerErrorBoundBits := 0x0000000000000000
  leftCenterNormBoundBits := 0x3ff0000000000000
  rightCenterNormBoundBits := 0x3ff0000000000000
}

def rawISample : RawTraceCertificate := {
  base := rawIDisk
  square := rawExactUnitMul rawIDisk rawIDisk rawNegOneDisk
  cube := rawExactUnitMul rawNegOneDisk rawIDisk rawNegIDisk
  steps := [
    ⟨rawExactUnitMul rawIDisk rawNegIDisk rawOneDisk,
      rawExactUnitMul rawNegIDisk rawNegOneDisk rawIDisk⟩
  ]
}

theorem rawIDisk_decode : rawIDisk.decode = some iDisk := by
  norm_num [rawIDisk, iDisk, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem rawISample_decode : rawISample.decode = some typedISample := by
  norm_num [rawISample, typedISample, rawExactUnitMul, exactUnitMul,
    rawIDisk, iDisk, rawNegOneDisk, negOneDisk, rawNegIDisk, negIDisk,
    rawOneDisk, oneDisk, RawTraceCertificate.decode, decodeSteps,
    RawStepCertificate.decode, ComplexDisk.RawMulCertificate.decode,
    ComplexDisk.Raw.decode, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem typedISample_check : typedISample.check 1 = true := by
  norm_num [typedISample, exactUnitMul, iDisk, negOneDisk, negIDisk,
    oneDisk, TraceCertificate.check, TraceCertificate.InitialWellFormed,
    TraceCertificate.initialState, checkLinked, StepCertificate.output,
    StepCertificate.check, StepCertificate.WellFormed,
    ComplexDisk.MulCertificate.check, ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

theorem rawISample_check : rawISample.check 1 = true := by
  rw [RawTraceCertificate.check]
  have hbound : decide (rawISample.steps.length ≤ 1) = true := by
    norm_num [rawISample]
  rw [hbound]
  simp only [Bool.true_and]
  rw [rawISample_decode]
  exact typedISample_check

theorem rawISample_term_count_check :
    rawISample.checkForTermCount 1 2 = true := by
  rw [RawTraceCertificate.checkForTermCount]
  have hpositive : decide (0 < (2 : ℕ)) = true := by norm_num
  have hcount : decide (rawISample.steps.length = 2 - 1) = true := by
    norm_num [rawISample]
  rw [hpositive, hcount]
  simpa using rawISample_check

theorem iDisk_contains_i : iDisk.ContainsComplex Complex.I := by
  unfold ComplexDisk.ContainsComplex
  have hcenter : iDisk.center = Complex.I := by
    apply Complex.ext <;> norm_num [iDisk, ComplexDisk.center]
  rw [hcenter]
  norm_num [iDisk]

theorem exact_after_i_one :
    (ExactGaussianState.after Complex.I 1).z = 1 ∧
      (ExactGaussianState.after Complex.I 1).ratio = Complex.I := by
  norm_num [ExactGaussianState.after, ExactGaussianState.initial,
    ExactGaussianState.step, pow_succ]

example :
    ∃ certificate : TraceCertificate,
      rawISample.decode = some certificate ∧
      certificate.output.z.ContainsComplex
          (ExactGaussianState.after Complex.I (2 - 1)).z ∧
      certificate.output.ratio.ContainsComplex
          (ExactGaussianState.after Complex.I (2 - 1)).ratio :=
  RawTraceCertificate.term_count_output_contains_exact_after_of_base_decode
    rawISample_term_count_check rawIDisk_decode iDisk_contains_i

/-! A valid zero product is used to tamper with the first row.  Its arithmetic
is sound in isolation, but its left input no longer links to the current
`z` disk, so the raw trace must be rejected. -/

def zeroDisk : ComplexDisk := ⟨0, 0, 0⟩

def zeroMul : ComplexDisk.MulCertificate := {
  left := zeroDisk
  right := oneDisk
  output := zeroDisk
  centerErrorBound := 0
  leftCenterNormBound := 0
  rightCenterNormBound := 1
}

def rawZeroDisk : ComplexDisk.Raw :=
  ⟨0x0000000000000000, 0x0000000000000000, 0x0000000000000000⟩

def rawZeroMul : ComplexDisk.RawMulCertificate := {
  left := rawZeroDisk
  right := rawOneDisk
  output := rawZeroDisk
  centerErrorBoundBits := 0x0000000000000000
  leftCenterNormBoundBits := 0x0000000000000000
  rightCenterNormBoundBits := 0x3ff0000000000000
}

def rawBrokenLinkStep : RawStepCertificate := ⟨rawZeroMul, rawOneMul⟩

def rawBrokenLink : RawTraceCertificate :=
  { rawSample with steps := [rawBrokenLinkStep] }

theorem rawZeroMul_decode : rawZeroMul.decode = some zeroMul := by
  norm_num [rawZeroMul, zeroMul, rawZeroDisk, zeroDisk, rawOneDisk, oneDisk,
    ComplexDisk.RawMulCertificate.decode, ComplexDisk.Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem raw_broken_link_fails_closed : rawBrokenLink.check 1 = false := by
  norm_num [rawBrokenLink, rawBrokenLinkStep, rawSample,
    RawTraceCertificate.check, RawTraceCertificate.decode, decodeSteps,
    RawStepCertificate.decode, rawZeroMul_decode, rawOneMul_decode,
    rawOneDisk_decode, TraceCertificate.check,
    TraceCertificate.InitialWellFormed, TraceCertificate.initialState,
    checkLinked, StepCertificate.output, StepCertificate.check,
    StepCertificate.WellFormed, zeroMul, zeroDisk, oneMul, oneDisk,
    ComplexDisk.MulCertificate.check, ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

/-! Infinity is rejected during raw binary64 decoding, before any typed
arithmetic proposition can be constructed. -/

def rawInfinityDisk : ComplexDisk.Raw :=
  ⟨0x7ff0000000000000, 0x0000000000000000, 0x0000000000000000⟩

def rawNonfinite : RawTraceCertificate :=
  { rawSample with base := rawInfinityDisk }

theorem raw_nonfinite_fails_closed : rawNonfinite.check 2 = false := by
  norm_num [rawNonfinite, rawInfinityDisk, rawSample,
    RawTraceCertificate.check, RawTraceCertificate.decode,
    ComplexDisk.Raw.decode, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes]

theorem raw_over_bound_fails_closed : rawSample.check 1 = false := by
  norm_num [RawTraceCertificate.check, rawSample]

theorem empty_term_count_fails_closed :
    rawSample.checkForTermCount 2 0 = false := by
  norm_num [RawTraceCertificate.checkForTermCount]

#print axioms RawTraceCertificate.checker_sound
#print axioms RawTraceCertificate.decoded_output_contains_exact_after
#print axioms RawTraceCertificate.accepted_output_contains_exact_after
#print axioms RawTraceCertificate.accepted_output_contains_exact_after_of_base_decode
#print axioms RawTraceCertificate.checkForTermCount_sound
#print axioms RawTraceCertificate.term_count_output_contains_exact_after_of_base_decode
#print axioms rawSample_check
#print axioms rawISample_term_count_check
#print axioms exact_after_i_one
#print axioms raw_broken_link_fails_closed
#print axioms raw_nonfinite_fails_closed
#print axioms raw_over_bound_fails_closed
#print axioms empty_term_count_fails_closed

end SparkInterval.Tests.FactoredSmallQRawTrace
