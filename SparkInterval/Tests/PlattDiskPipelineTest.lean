/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PlattDiskPipeline

set_option autoImplicit false

namespace SparkInterval.Tests.PlattDiskPipeline

open SparkInterval.Certified
open SparkInterval.Zeta.PlattDiskPipeline

private def left : ComplexDisk := ⟨1, 2, 0⟩
private def right : ComplexDisk := ⟨3, 4, 0⟩

private def leftProjection : ComplexDisk := realProjectionDisk left
private def rightProjection : ComplexDisk := realProjectionDisk right

private def leftProduct : ComplexDisk := ⟨1, 1, 0⟩
private def rightProduct : ComplexDisk := ⟨3, -3, 0⟩
private def output : ComplexDisk := ⟨4, -2, 0⟩

private def leftMul : ComplexDisk.MulCertificate := {
  left := leftProjection
  right := onePlusI
  output := leftProduct
  centerErrorBound := 0
  leftCenterNormBound := 1
  rightCenterNormBound := 2
}

private def rightMul : ComplexDisk.MulCertificate := {
  left := rightProjection
  right := oneMinusI
  output := rightProduct
  centerErrorBound := 0
  leftCenterNormBound := 3
  rightCenterNormBound := 2
}

private def outputAdd : ComplexDisk.AddCertificate := {
  left := leftProduct
  right := rightProduct
  output := output
  centerErrorBound := 0
}

private def endpoint : HermidftEndpointCertificate := {
  leftInput := left
  rightInput := right
  leftMul := leftMul
  rightMul := rightMul
  outputAdd := outputAdd
}

private theorem endpoint_check : endpoint.check = true := by
  rw [HermidftEndpointCertificate.check_eq_true]
  norm_num [HermidftEndpointCertificate.IsValid, endpoint, leftMul, rightMul,
    outputAdd, leftProjection, rightProjection, leftProduct, rightProduct,
    output, left, right, realProjectionDisk, onePlusI, oneMinusI,
    ComplexDisk.MulCertificate.WellFormed,
    ComplexDisk.AddCertificate.WellFormed, ComplexDisk.centerNormSq,
    ComplexDisk.productCenterErrorSq, ComplexDisk.sumCenterErrorSq]

private theorem left_contains : left.ContainsComplex
    (1 + 2 * Complex.I) := by
  have hcenter : left.center = 1 + 2 * Complex.I := by
    apply Complex.ext <;> norm_num [left, ComplexDisk.center]
  rw [ComplexDisk.ContainsComplex, hcenter, sub_self, norm_zero]
  norm_num [left]

private theorem right_contains : right.ContainsComplex
    (3 + 4 * Complex.I) := by
  have hcenter : right.center = 3 + 4 * Complex.I := by
    apply Complex.ext <;> norm_num [right, ComplexDisk.center]
  rw [ComplexDisk.ContainsComplex, hcenter, sub_self, norm_zero]
  norm_num [right]

example : output.ContainsComplex (hermidftEndpoint (1 + 2 * Complex.I)
    (3 + 4 * Complex.I)) := by
  exact endpoint.output_contains endpoint_check
    (by simpa [endpoint] using left_contains)
    (by simpa [endpoint] using right_contains)

example : (timesIDisk left).ContainsComplex
    (Complex.I * (1 + 2 * Complex.I)) := by
  exact timesIDisk_contains left_contains

end SparkInterval.Tests.PlattDiskPipeline
