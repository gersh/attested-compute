/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.TuringGridEventCertificate

set_option autoImplicit false

namespace SparkInterval.Tests.TuringGridEventCertificate

open SparkInterval.Zeta

private def sourceEvents : List TuringGridEvent := [
  { leftStep := 2, rightStep := 3, multiplicity := 1 },
  { leftStep := 5, rightStep := 7, multiplicity := 2 }
]

private def accepted : TuringGridEventCertificate := {
  spanSteps := 10
  events := sourceEvents
  isolatedCount := 3
  leftWeight := -12
  rightWeight := 13
  leftPositive := true
  rightPositive := false
}

private def crossed : TuringGridEventCertificate := {
  accepted with
    events := [
      { leftStep := 2, rightStep := 6, multiplicity := 1 },
      { leftStep := 5, rightStep := 7, multiplicity := 2 }
    ]
}

private theorem accepted_check : accepted.check = true := by
  rw [TuringGridEventCertificate.check_eq_true]
  norm_num [TuringGridEventCertificate.IsValid, accepted, sourceEvents,
    TuringGridEventsValidFrom, TuringGridEvent.IsValid,
    turingGridTotalMultiplicity, turingGridLeftWeight,
    turingGridRightWeight, TuringGridEvent.leftMagnitude,
    TuringGridEvent.rightMagnitude]

example : accepted.check = true := accepted_check

example : crossed.check = false := by
  rw [Bool.eq_false_iff]
  intro h
  have hvalid := TuringGridEventCertificate.check_eq_true.mp h
  norm_num [TuringGridEventCertificate.IsValid, crossed, accepted,
    TuringGridEventsValidFrom, TuringGridEvent.IsValid] at hvalid

example : accepted.leftWeight ≤ 0 ∧ 0 ≤ accepted.rightWeight :=
  accepted.weight_signs accepted_check

example : accepted.isolatedCount = turingGridTotalMultiplicity sourceEvents := by
  have hvalid := TuringGridEventCertificate.check_eq_true.mp accepted_check
  exact hvalid.2.2.1

end SparkInterval.Tests.TuringGridEventCertificate
