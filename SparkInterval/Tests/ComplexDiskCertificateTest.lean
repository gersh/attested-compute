/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.ComplexDisk

set_option autoImplicit false

namespace SparkInterval.Tests.ComplexDiskCertificate

open SparkInterval.Certified
open SparkInterval.Certified.ComplexDisk
open SparkInterval.Certificate

/-- A closed rational witness: `(1+2i) * (3+4i) = -5+10i`, with deliberately
loose centre-norm bounds and nonzero input radii. -/
def sample : MulCertificate := {
  left := ⟨1, 2, 1 / 10⟩
  right := ⟨3, 4, 1 / 5⟩
  output := ⟨-5, 10, 28 / 25⟩
  centerErrorBound := 0
  leftCenterNormBound := 3
  rightCenterNormBound := 5
}

theorem sample_check : sample.check = true := by
  norm_num [sample, MulCertificate.check, MulCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

example :
    sample.left.centerNormSq ≤ sample.left.centerL1Bound ^ 2 :=
  ComplexDisk.centerNormSq_le_centerL1Bound_sq sample.left

example :
    ComplexDisk.productCenterErrorSq sample.left sample.right sample.output ≤
      ComplexDisk.productCenterErrorL1Bound
          sample.left sample.right sample.output ^ 2 :=
  ComplexDisk.productCenterErrorSq_le_productCenterErrorL1Bound_sq
    sample.left sample.right sample.output

example : sample.output.ContainsComplex
    ((sample.left.center) * sample.right.center) := by
  apply MulCertificate.output_contains_mul sample_check
  · norm_num [sample, ComplexDisk.ContainsComplex]
  · norm_num [sample, ComplexDisk.ContainsComplex]

/-- Same shape using exact binary64 wire words. -/
def wireSample : MulCertificate := {
  left := ⟨1, 2, 1 / 8⟩
  right := ⟨3, 4, 1 / 4⟩
  output := ⟨-5, 10, 45 / 32⟩
  centerErrorBound := 0
  leftCenterNormBound := 3
  rightCenterNormBound := 5
}

def rawSample : RawMulCertificate := {
  left := ⟨0x3ff0000000000000, 0x4000000000000000, 0x3fc0000000000000⟩
  right := ⟨0x4008000000000000, 0x4010000000000000, 0x3fd0000000000000⟩
  output := ⟨0xc014000000000000, 0x4024000000000000, 0x3ff6800000000000⟩
  centerErrorBoundBits := 0x0000000000000000
  leftCenterNormBoundBits := 0x4008000000000000
  rightCenterNormBoundBits := 0x4014000000000000
}

theorem rawSample_decode : rawSample.decode = some wireSample := by
  norm_num [rawSample, wireSample, RawMulCertificate.decode, Raw.decode,
    Binary64.decodeFinite, Binary64.wordLimit, Binary64.exponentBits,
    Binary64.exponentModulus, Binary64.fractionModulus,
    Binary64.exponentAllOnes, Binary64.finiteValue, Binary64.fractionBits,
    Binary64.signBit, Binary64.signThreshold]

theorem rawSample_check : rawSample.check = true := by
  rw [RawMulCertificate.check, rawSample_decode]
  norm_num [wireSample, MulCertificate.check, MulCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

example : wireSample.output.ContainsComplex
    (wireSample.left.center * wireSample.right.center) := by
  apply RawMulCertificate.output_contains_mul rawSample_check rawSample_decode
  · norm_num [wireSample, ComplexDisk.ContainsComplex]
  · norm_num [wireSample, ComplexDisk.ContainsComplex]

def wireAddSample : AddCertificate := {
  left := ⟨1, 2, 1 / 8⟩
  right := ⟨3, 4, 1 / 4⟩
  output := ⟨4, 6, 3 / 8⟩
  centerErrorBound := 0
}

def rawAddSample : RawAddCertificate := {
  left := rawSample.left
  right := rawSample.right
  output := ⟨0x4010000000000000, 0x4018000000000000, 0x3fd8000000000000⟩
  centerErrorBoundBits := 0x0000000000000000
}

theorem rawAddSample_decode : rawAddSample.decode = some wireAddSample := by
  norm_num [rawAddSample, rawSample, wireAddSample, RawAddCertificate.decode,
    Raw.decode, Binary64.decodeFinite, Binary64.wordLimit,
    Binary64.exponentBits, Binary64.exponentModulus,
    Binary64.fractionModulus, Binary64.exponentAllOnes,
    Binary64.finiteValue, Binary64.fractionBits, Binary64.signBit,
    Binary64.signThreshold]

theorem rawAddSample_check : rawAddSample.check = true := by
  rw [RawAddCertificate.check, rawAddSample_decode]
  norm_num [wireAddSample, AddCertificate.check, AddCertificate.WellFormed,
    ComplexDisk.sumCenterErrorSq]

example :
    ComplexDisk.sumCenterErrorSq
        wireAddSample.left wireAddSample.right wireAddSample.output ≤
      ComplexDisk.sumCenterErrorL1Bound
          wireAddSample.left wireAddSample.right wireAddSample.output ^ 2 :=
  ComplexDisk.sumCenterErrorSq_le_sumCenterErrorL1Bound_sq
    wireAddSample.left wireAddSample.right wireAddSample.output

example : wireAddSample.output.ContainsComplex
    (wireAddSample.left.center + wireAddSample.right.center) := by
  apply RawAddCertificate.output_contains_add rawAddSample_check
    rawAddSample_decode
  · norm_num [wireAddSample, ComplexDisk.ContainsComplex]
  · norm_num [wireAddSample, ComplexDisk.ContainsComplex]

#print axioms AddCertificate.check_sound
#print axioms AddCertificate.output_contains_add
#print axioms MulCertificate.check_sound
#print axioms MulCertificate.output_contains_mul
#print axioms RawAddCertificate.check_sound
#print axioms RawAddCertificate.output_contains_add
#print axioms RawMulCertificate.check_sound
#print axioms RawMulCertificate.output_contains_mul
#print axioms ComplexDisk.centerNormSq_le_centerL1Bound_sq
#print axioms ComplexDisk.productCenterErrorSq_le_productCenterErrorL1Bound_sq
#print axioms ComplexDisk.sumCenterErrorSq_le_sumCenterErrorL1Bound_sq
#print axioms sample_check
#print axioms rawAddSample_check
#print axioms rawSample_check

end SparkInterval.Tests.ComplexDiskCertificate
