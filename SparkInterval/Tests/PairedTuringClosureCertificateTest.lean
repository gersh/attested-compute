/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PairedTuringClosureCertificate

/-! Kernel-checked examples for the three-stream PT21 Turing adapter. -/

set_option autoImplicit false

namespace SparkInterval.Tests.PairedTuringClosureCertificate

open SparkInterval.Certificate
open SparkInterval.Zeta

private def mainEvents : List TuringGridEvent := []

private def mainStream : TuringGridEventCertificate := {
  spanSteps := 3
  events := mainEvents
  isolatedCount := 0
  leftWeight := 0
  rightWeight := 0
  leftPositive := true
  rightPositive := true
}

private def leftFlankEvents : List TuringGridEvent := []

private def leftFlankStream : TuringGridEventCertificate := {
  spanSteps := 4
  events := leftFlankEvents
  isolatedCount := 0
  leftWeight := 0
  rightWeight := 0
  leftPositive := true
  rightPositive := true
}

private def rightFlankStream : TuringGridEventCertificate := {
  spanSteps := 4
  events := []
  isolatedCount := 0
  leftWeight := 0
  rightWeight := 0
  leftPositive := true
  rightPositive := true
}

private def windowInput : TuringWindowInput := {
  a := 10
  b := 11
  delta := 1
  sBound := RatInterval.point 0
  logPi := RatInterval.point 0
  imGammaIntegral := RatInterval.point 0
  pi := RatInterval.point 1
  leftWeight := 0
  rightWeight := 0
}

private def window : TuringWindowCertificate := {
  input := windowInput
  lowerQuotient := RatInterval.point 0
  upperQuotient := RatInterval.point 0
  lowerCount := 1
  upperCount := 1
  isolatedCount := 0
  leftPositive := true
  rightPositive := true
}

private def accepted : PairedTuringClosureCertificate := {
  mainStream := mainStream
  leftFlankStream := leftFlankStream
  rightFlankStream := rightFlankStream
  window := window
  lowerCount := 1
  mainIsolatedSlots := 0
  upperCount := 1
}

private def wrongLeftWeight : PairedTuringClosureCertificate := {
  accepted with
    leftFlankStream := { leftFlankStream with leftWeight := -2 }
}

private theorem accepted_check : accepted.check = true := by
  rw [PairedTuringClosureCertificate.check_eq_true]
  norm_num [PairedTuringClosureCertificate.IsValid, accepted, mainStream,
    mainEvents, leftFlankStream, leftFlankEvents, rightFlankStream, window,
    windowInput, TuringGridEventCertificate.IsValid,
    TuringGridEventsValidFrom, TuringGridEvent.IsValid,
    turingGridTotalMultiplicity, turingGridLeftWeight,
    turingGridRightWeight, TuringGridEvent.leftMagnitude,
    TuringGridEvent.rightMagnitude, TuringWindowCertificate.IsValid,
    TuringWindowCertificate.lowerCeilTarget,
    TuringWindowCertificate.upperFloorTarget, TuringWindowInput.evaluate?,
    TuringWindowInput.logTerm, TuringWindowInput.span,
    TuringWindowInput.leftIntegral, TuringWindowInput.rightIntegral,
    RatInterval.IsValid, RatInterval.point, RatInterval.add, RatInterval.sub,
    RatInterval.neg, RatInterval.mul, RatInterval.div?]

example : accepted.check = true := accepted_check

example : wrongLeftWeight.check = false := by
  rw [PairedTuringClosureCertificate.check_eq_false]
  intro hvalid
  have hleft := hvalid.2.1
  norm_num [wrongLeftWeight, accepted, leftFlankStream, leftFlankEvents,
    TuringGridEventCertificate.IsValid, TuringGridEventsValidFrom,
    TuringGridEvent.IsValid, turingGridTotalMultiplicity,
    turingGridLeftWeight, turingGridRightWeight,
    TuringGridEvent.leftMagnitude, TuringGridEvent.rightMagnitude] at hleft

example : accepted.lowerCount + accepted.mainIsolatedSlots =
    accepted.upperCount :=
  accepted.closure_equation accepted_check

example : accepted.mainIsolatedSlots =
      turingGridTotalMultiplicity accepted.mainStream.events ∧
    accepted.window.input.leftWeight =
      turingGridLeftWeight accepted.leftFlankStream.events ∧
    accepted.window.input.rightWeight =
      turingGridRightWeight accepted.rightFlankStream.spanSteps
        accepted.rightFlankStream.events :=
  accepted.binds_stream_arithmetic accepted_check

example (values : accepted.window.input.Realization)
    (analytic : accepted.window.AnalyticTuringBounds values 1 1) :
    (1 : Nat) = accepted.lowerCount ∧
      (1 : Nat) = accepted.upperCount ∧
      1 + accepted.mainIsolatedSlots = 1 := by
  exact accepted.exact_endpoint_counts accepted_check values analytic
    ⟨by decide⟩

end SparkInterval.Tests.PairedTuringClosureCertificate
