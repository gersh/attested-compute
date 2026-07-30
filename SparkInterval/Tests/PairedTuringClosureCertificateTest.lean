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

/-- Exact-rational `turing_min` certificate for the left flank. -/
private def lowerWindow : LowerTuringCertificate := {
  input := windowInput
  quotient := RatInterval.point 0
  count := 1
}

/-- Exact-rational `turing_max` certificate for the right flank. -/
private def upperWindow : UpperTuringCertificate := {
  input := windowInput
  quotient := RatInterval.point 0
  count := 1
}

private def accepted : PairedTuringClosureCertificate := {
  mainStream := mainStream
  leftFlankStream := leftFlankStream
  rightFlankStream := rightFlankStream
  lowerWindow := lowerWindow
  upperWindow := upperWindow
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
    mainEvents, leftFlankStream, leftFlankEvents, rightFlankStream,
    lowerWindow, upperWindow, windowInput,
    TuringGridEventCertificate.IsValid,
    TuringGridEventsValidFrom, TuringGridEvent.IsValid,
    turingGridTotalMultiplicity, turingGridLeftWeight,
    turingGridRightWeight, TuringGridEvent.leftMagnitude,
    TuringGridEvent.rightMagnitude,
    LowerTuringCertificate.IsValid, LowerTuringCertificate.ceilTarget,
    UpperTuringCertificate.IsValid, UpperTuringCertificate.floorTarget,
    TuringWindowInput.evaluateLower?, TuringWindowInput.evaluateUpper?,
    TuringWindowInput.evaluate?,
    TuringWindowInput.logTerm, TuringWindowInput.span,
    TuringWindowInput.leftIntegral, TuringWindowInput.rightIntegral,
    RatInterval.IsValid, RatInterval.point, RatInterval.add, RatInterval.sub,
    RatInterval.neg, RatInterval.mul, RatInterval.div?]

example : accepted.check = true := accepted_check

/-- A left-flank weight that no longer matches the checked `turing_min`
input is rejected: the checker is not vacuously true. -/
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
    accepted.lowerWindow.input.leftWeight =
      turingGridLeftWeight accepted.leftFlankStream.events ∧
    accepted.upperWindow.input.rightWeight =
      turingGridRightWeight accepted.rightFlankStream.spanSteps
        accepted.rightFlankStream.events :=
  accepted.binds_stream_arithmetic accepted_check

example (lowerValues : accepted.lowerWindow.input.Realization)
    (upperValues : accepted.upperWindow.input.Realization)
    (analytic : accepted.AnalyticTuringBounds lowerValues upperValues 1 1) :
    (1 : Nat) = accepted.lowerCount ∧
      (1 : Nat) = accepted.upperCount ∧
      1 + accepted.mainIsolatedSlots = 1 :=
  accepted.exact_endpoint_counts accepted_check lowerValues upperValues
    analytic ⟨by decide⟩

end SparkInterval.Tests.PairedTuringClosureCertificate
