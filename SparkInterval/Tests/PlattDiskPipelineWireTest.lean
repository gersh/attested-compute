/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PlattDiskPipelineWire

set_option autoImplicit false
set_option maxRecDepth 100000
set_option maxHeartbeats 2000000

namespace SparkInterval.Tests.PlattDiskPipelineWire

open SparkInterval.Zeta.PlattDiskPipeline.Wire

private def zero : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
private def one : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xf0, 0x3f]
private def two : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x40]
private def three : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x08, 0x40]
private def four : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10, 0x40]
private def minusOne : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xf0, 0xbf]
private def minusTwo : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xc0]
private def minusThree : List UInt8 :=
  [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x08, 0xc0]

private def disk (re im radius : List UInt8) : List UInt8 :=
  re ++ im ++ radius

private def mulCertificate
    (left right output error leftNorm rightNorm : List UInt8) : List UInt8 :=
  left ++ right ++ output ++ error ++ leftNorm ++ rightNorm

private def addCertificate
    (left right output error : List UInt8) : List UInt8 :=
  left ++ right ++ output ++ error

private def leftInput := disk one two zero
private def rightInput := disk three four zero
private def leftProjection := disk one zero zero
private def rightProjection := disk three zero zero
private def plusI := disk one one zero
private def minusI := disk one minusOne zero
private def leftProduct := disk one one zero
private def rightProduct := disk three minusThree zero
private def output := disk four minusTwo zero

private def fixture : List UInt8 :=
  leftInput ++ rightInput ++
    mulCertificate leftProjection plusI leftProduct zero one two ++
    mulCertificate rightProjection minusI rightProduct zero three two ++
    addCertificate leftProduct rightProduct output zero

private def zeroWord : Nat := 0x0000000000000000
private def oneWord : Nat := 0x3ff0000000000000
private def twoWord : Nat := 0x4000000000000000
private def threeWord : Nat := 0x4008000000000000
private def fourWord : Nat := 0x4010000000000000
private def minusOneWord : Nat := 0xbff0000000000000
private def minusTwoWord : Nat := 0xc000000000000000
private def minusThreeWord : Nat := 0xc008000000000000

private def rawDisk (re im radius : Nat) :
    SparkInterval.Certified.ComplexDisk.Raw :=
  ⟨re, im, radius⟩

private def rawFixture : RawEndpointCertificate := {
  leftInput := rawDisk oneWord twoWord zeroWord
  rightInput := rawDisk threeWord fourWord zeroWord
  leftMul := {
    left := rawDisk oneWord zeroWord zeroWord
    right := rawDisk oneWord oneWord zeroWord
    output := rawDisk oneWord oneWord zeroWord
    centerErrorBoundBits := zeroWord
    leftCenterNormBoundBits := oneWord
    rightCenterNormBoundBits := twoWord
  }
  rightMul := {
    left := rawDisk threeWord zeroWord zeroWord
    right := rawDisk oneWord minusOneWord zeroWord
    output := rawDisk threeWord minusThreeWord zeroWord
    centerErrorBoundBits := zeroWord
    leftCenterNormBoundBits := threeWord
    rightCenterNormBoundBits := twoWord
  }
  outputAdd := {
    left := rawDisk oneWord oneWord zeroWord
    right := rawDisk threeWord minusThreeWord zeroWord
    output := rawDisk fourWord minusTwoWord zeroWord
    centerErrorBoundBits := zeroWord
  }
}

theorem fixture_length : fixture.length = endpointCertificateByteSize := by
  rfl

theorem fixture_parse : parse fixture = some rawFixture := by
  rfl

private theorem rawFixture_check : rawFixture.check = true := by
  norm_num [rawFixture, rawDisk, zeroWord, oneWord, twoWord, threeWord,
    fourWord, minusOneWord, minusTwoWord, minusThreeWord,
    RawEndpointCertificate.check, RawEndpointCertificate.decode,
    SparkInterval.Zeta.PlattDiskPipeline.HermidftEndpointCertificate.check,
    SparkInterval.Zeta.PlattDiskPipeline.HermidftEndpointCertificate.IsValid,
    SparkInterval.Certified.ComplexDisk.Raw.decode,
    SparkInterval.Certified.ComplexDisk.RawMulCertificate.decode,
    SparkInterval.Certified.ComplexDisk.RawAddCertificate.decode,
    SparkInterval.Certified.ComplexDisk.MulCertificate.WellFormed,
    SparkInterval.Certified.ComplexDisk.AddCertificate.WellFormed,
    SparkInterval.Certified.ComplexDisk.centerNormSq,
    SparkInterval.Certified.ComplexDisk.productCenterErrorSq,
    SparkInterval.Certified.ComplexDisk.sumCenterErrorSq,
    SparkInterval.Certificate.Binary64.decodeFinite,
    SparkInterval.Certificate.Binary64.wordLimit,
    SparkInterval.Certificate.Binary64.exponentBits,
    SparkInterval.Certificate.Binary64.exponentModulus,
    SparkInterval.Certificate.Binary64.fractionModulus,
    SparkInterval.Certificate.Binary64.exponentAllOnes,
    SparkInterval.Certificate.Binary64.finiteValue,
    SparkInterval.Certificate.Binary64.fractionBits,
    SparkInterval.Certificate.Binary64.signBit,
    SparkInterval.Certificate.Binary64.signThreshold,
    SparkInterval.Zeta.PlattDiskPipeline.realProjectionDisk,
    SparkInterval.Zeta.PlattDiskPipeline.onePlusI,
    SparkInterval.Zeta.PlattDiskPipeline.oneMinusI]

theorem fixture_check : checkBytes fixture = true := by
  rw [checkBytes, fixture_parse]
  exact rawFixture_check

theorem truncated_rejected : checkBytes fixture.dropLast = false := by
  rfl

theorem trailing_rejected : checkBytes (fixture ++ [0x00]) = false := by
  rfl

#print axioms fixture_length
#print axioms fixture_parse
#print axioms fixture_check
#print axioms truncated_rejected
#print axioms trailing_rejected

end SparkInterval.Tests.PlattDiskPipelineWire
