/-
Copyright (c) 2026 Gershon Bialer. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: Gershon Bialer
-/
import SparkInterval.Certified.Exp
import TGComputeContracts.Sqrt218.Kernel

/-!
# Executable logarithm certificates for the Sqrt218 contract

This file connects the generic rational `Real.log` checker to the directed
fixed-point logarithm facts used by the data-independent Sqrt218 kernel.

The certificate proposition contains only:

* the positive Taylor-term guard required by `logCheck_sound`; and
* one successful executable `primeLogRowCheck` result for each roster row.

It contains no production prime table or generated proof shards.  Positivity
of each checked input is obtained from the separately certified prime roster.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218LogCertificate

open TGComputeContracts.Sqrt218

/-- Check one pair of integer fixed-point endpoints against `Real.log p`.
The endpoints are interpreted with the Sqrt218 denominator `scale = 2^48`. -/
def primeLogRowCheck (terms k prec p lower upper : Nat) : Bool :=
  SparkInterval.Certified.logCheck terms k prec (p : ℚ)
    ((lower : ℚ) / (scale : ℚ))
    ((upper : ℚ) / (scale : ℚ))

/-- Data-independent aggregate certificate for all logarithm rows.

The functions may later be instantiated by a small local test vector or by
an attested production archive.  Merely importing this definition evaluates
neither one. -/
structure PrimeLogCheckCertificate
    (terms k prec primeCount : Nat)
    (primeAt logLowerAt logUpperAt : Nat → Nat) : Prop where
  terms_pos : 0 < terms
  checked :
    ∀ i, i < primeCount →
      primeLogRowCheck terms k prec
        (primeAt i) (logLowerAt i) (logUpperAt i) = true

private theorem cast_scaled_endpoint (endpoint : Nat) :
    (scale : ℝ) *
        (((endpoint : ℚ) / (scale : ℚ) : ℚ) : ℝ) =
      (endpoint : ℝ) := by
  rw [Rat.cast_div, Rat.cast_natCast, Rat.cast_natCast]
  have hscale : (scale : ℝ) ≠ 0 := by
    exact_mod_cast (ne_of_gt scale_pos)
  field_simp

/-- One successful row check yields the directed fixed-point inequalities
needed by `PrimeLogFacts`. -/
theorem primeLogRowCheck_sound
    {terms k prec p lower upper : Nat}
    (hterms : 0 < terms) (hp : 0 < p)
    (hcheck : primeLogRowCheck terms k prec p lower upper = true) :
    (lower : ℝ) ≤ (scale : ℝ) * Real.log p ∧
      (scale : ℝ) * Real.log p ≤ (upper : ℝ) := by
  have hpq : (0 : ℚ) < (p : ℚ) := by exact_mod_cast hp
  have hinterval :=
    SparkInterval.Certified.logCheck_sound hterms hpq hcheck
  have hscale_nonneg : (0 : ℝ) ≤ (scale : ℝ) := by
    exact_mod_cast (Nat.zero_le scale)
  constructor
  · have hmul := mul_le_mul_of_nonneg_left hinterval.1 hscale_nonneg
    rw [cast_scaled_endpoint] at hmul
    exact hmul
  · have hmul := mul_le_mul_of_nonneg_left hinterval.2 hscale_nonneg
    rw [cast_scaled_endpoint] at hmul
    exact hmul

/-- A complete prime roster plus successful executable log checks supplies
the generic Sqrt218 kernel's entire `PrimeLogFacts` field. -/
theorem PrimeLogCheckCertificate.sound
    {bound terms k prec primeCount : Nat}
    {primeAt logLowerAt logUpperAt : Nat → Nat}
    (certificate :
      PrimeLogCheckCertificate terms k prec primeCount
        primeAt logLowerAt logUpperAt)
    (roster : PrimeRosterFacts bound primeCount primeAt) :
    PrimeLogFacts primeCount primeAt logLowerAt logUpperAt := by
  constructor
  · intro i hi
    exact
      (primeLogRowCheck_sound certificate.terms_pos
        (roster.prime i hi).pos
        (certificate.checked i hi)).1
  · intro i hi
    exact
      (primeLogRowCheck_sound certificate.terms_pos
        (roster.prime i hi).pos
        (certificate.checked i hi)).2

end SparkInterval.TernaryGoldbach.Sqrt218LogCertificate
