/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.TuringWindowCertificate

set_option autoImplicit false

namespace SparkInterval.Tests.TuringWindowCertificate

open SparkInterval.Certificate
open SparkInterval.Zeta

private def zeroWindowInput : TuringWindowInput := {
  a := 10
  b := 12
  delta := 1
  sBound := RatInterval.point 0
  logPi := RatInterval.point 0
  imGammaIntegral := RatInterval.point 0
  pi := RatInterval.point 1
  leftWeight := 0
  rightWeight := 0
}

private def accepted : TuringWindowCertificate := {
  input := zeroWindowInput
  lowerQuotient := RatInterval.point 0
  upperQuotient := RatInterval.point 0
  lowerCount := 1
  upperCount := 1
  isolatedCount := 0
  leftPositive := true
  rightPositive := true
}

private def badParity : TuringWindowCertificate := {
  accepted with rightPositive := false
}

private theorem accepted_check : accepted.check = true := by
  rw [TuringWindowCertificate.check_eq_true]
  norm_num [TuringWindowCertificate.IsValid, accepted, zeroWindowInput,
    TuringWindowCertificate.lowerCeilTarget,
    TuringWindowCertificate.upperFloorTarget,
    TuringWindowInput.evaluate?, TuringWindowInput.logTerm,
    TuringWindowInput.span, TuringWindowInput.leftIntegral,
    TuringWindowInput.rightIntegral, RatInterval.IsValid, RatInterval.point,
    RatInterval.add, RatInterval.sub, RatInterval.neg, RatInterval.mul,
    RatInterval.div?]

example : accepted.check = true := accepted_check
example : badParity.check = false := by
  rw [TuringWindowCertificate.check_eq_false]
  norm_num [TuringWindowCertificate.IsValid, badParity, accepted, zeroWindowInput,
    TuringWindowCertificate.lowerCeilTarget,
    TuringWindowCertificate.upperFloorTarget,
    TuringWindowInput.evaluate?, TuringWindowInput.logTerm,
    TuringWindowInput.span, TuringWindowInput.leftIntegral,
    TuringWindowInput.rightIntegral, RatInterval.IsValid, RatInterval.point,
    RatInterval.add, RatInterval.sub, RatInterval.neg, RatInterval.mul,
    RatInterval.div?]

private def zeroRealization : zeroWindowInput.Realization := {
  sBound := 0
  logPi := 0
  imGammaIntegral := 0
  pi := 1
  sBound_mem := by simp [zeroWindowInput, RatInterval.ContainsReal, RatInterval.point]
  logPi_mem := by simp [zeroWindowInput, RatInterval.ContainsReal, RatInterval.point]
  imGammaIntegral_mem := by
    simp [zeroWindowInput, RatInterval.ContainsReal, RatInterval.point]
  pi_mem := by simp [zeroWindowInput, RatInterval.ContainsReal, RatInterval.point]
}

example : ⌊zeroRealization.upperQuotient⌋ = 0 := by
  exact accepted.floor_upperQuotient_eq accepted_check zeroRealization

example : ⌈zeroRealization.lowerQuotient⌉ = 0 := by
  exact accepted.ceil_lowerQuotient_eq accepted_check zeroRealization

example (analytic : accepted.AnalyticTuringBounds zeroRealization 1 1) :
    (1 : Nat) = accepted.lowerCount ∧
      (1 : Nat) = accepted.upperCount ∧
      1 + accepted.isolatedCount = 1 := by
  exact accepted.exact_endpoint_counts accepted_check zeroRealization analytic (by decide)

end SparkInterval.Tests.TuringWindowCertificate
