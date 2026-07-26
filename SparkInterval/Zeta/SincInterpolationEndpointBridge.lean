/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.EndpointCertificate
import SparkInterval.Zeta.SincInterpolationCertificate

/-!
# Gaussian--sinc interpolation to zero-bracket certificates

This module binds two checked source-shaped interpolation evaluations to the
existing `RationalBracket` zero-isolation layer.  Exact rational checks ensure
that the interpolation coordinates and output intervals are literally the
bracket endpoints and endpoint values.  Consequently a proved interpolation
realization supplies `RationalBracket.EnclosesEndpoints`; continuity and the
existing bracket theorem then produce a real zero.

This closes a formerly informal handoff between Platt's stationary-point
interpolation and the multiplicity-safe zero-event machinery.  The joint
Appendix-C bound (C.1 Weiss/non-bandlimited plus corrected-C.3 omitted tail)
and the Hardy-Z sample realization remain explicit fields of the two
interpolation realizations.  No new trust assumption is introduced.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

namespace SincInterpolationBracket

open SincInterpolationCertificate

/-- Two interpolation certificates bound to one rational sign bracket. -/
structure Certificate where
  bracket : RationalBracket
  lower : SincInterpolationCertificate.Certificate
  upper : SincInterpolationCertificate.Certificate
  deriving DecidableEq, Repr

namespace Certificate

/-- Exact source-shaped binding proposition. -/
def IsValid (certificate : Certificate) : Prop :=
  certificate.bracket.IsValid ∧
    certificate.lower.IsValid ∧
    certificate.upper.IsValid ∧
    certificate.lower.queryRational = certificate.bracket.lower ∧
    certificate.upper.queryRational = certificate.bracket.upper ∧
    certificate.lower.output = certificate.bracket.lowerValue ∧
    certificate.upper.output = certificate.bracket.upperValue

/-- Executable binding and arithmetic checker. -/
def check (certificate : Certificate) : Bool :=
  certificate.bracket.check &&
    certificate.lower.check &&
    certificate.upper.check &&
    decide (certificate.lower.queryRational = certificate.bracket.lower) &&
    decide (certificate.upper.queryRational = certificate.bracket.upper) &&
    decide (certificate.lower.output = certificate.bracket.lowerValue) &&
    decide (certificate.upper.output = certificate.bracket.upperValue)

@[simp] theorem check_eq_true {certificate : Certificate} :
    certificate.check = true ↔ certificate.IsValid := by
  simp [check, IsValid]
  tauto

@[simp] theorem check_eq_false {certificate : Certificate} :
    certificate.check = false ↔ ¬certificate.IsValid := by
  constructor
  · intro hfalse hvalid
    have htrue := check_eq_true.mpr hvalid
    rw [hfalse] at htrue
    contradiction
  · intro hnot
    cases hcheck : certificate.check with
    | false => rfl
    | true => exact False.elim (hnot (check_eq_true.mp hcheck))

/-- Analytic realization of both bound interpolation calls. -/
structure Realization (certificate : Certificate) (function : ℝ → ℝ) : Prop where
  lower : certificate.lower.Realization function
  upper : certificate.upper.Realization function

/-- Successful checking turns the two interpolation theorems into exactly the
endpoint-enclosure contract consumed by `RationalBracket`. -/
theorem enclosesEndpoints (certificate : Certificate)
    (function : ℝ → ℝ) (hcheck : certificate.check = true)
    (realization : certificate.Realization function) :
    certificate.bracket.EnclosesEndpoints function := by
  have hvalid := certificate.check_eq_true.mp hcheck
  have hlower := certificate.lower.output_contains function
    (SincInterpolationCertificate.Certificate.check_eq_true.mpr hvalid.2.1)
    realization.lower
  have hupper := certificate.upper.output_contains function
    (SincInterpolationCertificate.Certificate.check_eq_true.mpr hvalid.2.2.1)
    realization.upper
  constructor
  · rw [← hvalid.2.2.2.2.2.1]
    simpa [SincInterpolationCertificate.Certificate.queryOrdinate,
      hvalid.2.2.2.1] using hlower
  · rw [← hvalid.2.2.2.2.2.2]
    simpa [SincInterpolationCertificate.Certificate.queryOrdinate,
      hvalid.2.2.2.2.1] using hupper

/-- Continuity plus a checked pair of interpolated endpoint signs produces a
real root in the exact rational bracket. -/
theorem exists_zero (certificate : Certificate)
    (function : ℝ → ℝ) (hcheck : certificate.check = true)
    (realization : certificate.Realization function)
    (continuous : Continuous function) :
    ∃ x ∈ Set.Icc (certificate.bracket.lower : ℝ)
        (certificate.bracket.upper : ℝ), function x = 0 := by
  have hvalid := certificate.check_eq_true.mp hcheck
  let bracket : Bracket :=
    { lower := (certificate.bracket.lower : ℝ)
      upper := (certificate.bracket.upper : ℝ)
      lower_lt_upper := by exact_mod_cast hvalid.1.1 }
  have hchange : bracket.StrictSignChange function := by
    simpa [bracket, Bracket.StrictSignChange] using
      certificate.bracket.strictSignChange hvalid.1
        (certificate.enclosesEndpoints function hcheck realization)
  obtain ⟨x, hx, hzero⟩ :=
    bracket.exists_zero continuous.continuousOn hchange.signChange
  refine ⟨x, ?_, hzero⟩
  simpa [Bracket.carrier, bracket] using hx

end Certificate

end SincInterpolationBracket

end SparkInterval.Zeta
