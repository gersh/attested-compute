/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.Atan

/-!
# A reusable high-precision rational enclosure of pi

The decimal bounds in mathlib are intentionally small and are sufficient for
many analytic estimates, but not for checking tight binary64 root boxes.  This
module instead uses Machin's identity

```
pi = 16 * arctan (1 / 5) - 4 * arctan (1 / 239)
```

and the proved exact-rational arctangent remainder bound from
`SparkInterval.Certified.Atan`.  No decimal citation, native evaluator, or
external transcendental library participates in the enclosure.
-/

set_option autoImplicit false

namespace SparkInterval.Certified

open SparkInterval.Certificate

/-- Exact-rational Machin enclosure with a caller-selected number of
arctangent-series terms. -/
def machinPiInterval (terms : Nat) : RatInterval :=
  ((RatInterval.point 16).mul (atanSmall terms (1 / 5))).sub
    ((RatInterval.point 4).mul (atanSmall terms (1 / 239)))

theorem machinPiInterval_containsReal (terms : Nat) :
    (machinPiInterval terms).ContainsReal Real.pi := by
  have h5 :
      (atanSmall terms (1 / 5)).ContainsReal
        (Real.arctan (((1 / 5 : ℚ) : ℝ))) :=
    atanSmall_containsReal (by norm_num)
  have h239 :
      (atanSmall terms (1 / 239)).ContainsReal
        (Real.arctan (((1 / 239 : ℚ) : ℝ))) :=
    atanSmall_containsReal (by norm_num)
  have hcombined :=
    RatInterval.sub_containsReal
      (RatInterval.mul_containsReal
        (RatInterval.point_containsReal (16 : ℚ)) h5)
      (RatInterval.mul_containsReal
        (RatInterval.point_containsReal (4 : ℚ)) h239)
  have hmachin :=
    Real.four_mul_arctan_inv_5_sub_arctan_inv_239
  have hvalue :
      (((16 : ℚ) : ℝ) *
          Real.arctan (((1 / 5 : ℚ) : ℝ))) -
        (((4 : ℚ) : ℝ) *
          Real.arctan (((1 / 239 : ℚ) : ℝ))) =
        Real.pi := by
    norm_num only [Rat.cast_ofNat, Rat.cast_div, Rat.cast_one,
      Nat.cast_ofNat]
    norm_num only [one_div] at hmachin
    linarith
  rwa [hvalue] at hcombined

/-- The one-time proof of the root-checker constant uses enough Machin terms
that the arctangent remainder is far below the retained decimal interval. -/
def rootPiTerms : Nat := 64

/-- Lower endpoint of the checked 128-bit dyadic enclosure.  This is a
runtime constant; the theorem below derives it from `machinPiInterval`. -/
def rootPiLoQ : ℚ :=
  1069028584064966747859680373161870783300 / 2 ^ 128

/-- Upper endpoint of the checked 128-bit dyadic enclosure. -/
def rootPiHiQ : ℚ :=
  1069028584064966747859680373161870783301 / 2 ^ 128

/-- High-precision, constant-time exact-rational enclosure of `pi` used for
DFT roots. -/
def rootPiInterval : RatInterval := ⟨rootPiLoQ, rootPiHiQ⟩

theorem rootPiInterval_containsReal :
    rootPiInterval.ContainsReal Real.pi := by
  have hmachin := machinPiInterval_containsReal rootPiTerms
  constructor
  · exact
      (Rat.cast_le.mpr (by
        norm_num [rootPiInterval, rootPiLoQ, machinPiInterval,
          rootPiTerms, atanSmall, atanPartialSum, atanErr, widen,
          RatInterval.point, RatInterval.mul, RatInterval.sub])).trans
        hmachin.1
  · exact
      hmachin.2.trans
        (Rat.cast_le.mpr (by
          norm_num [rootPiInterval, rootPiHiQ, machinPiInterval,
            rootPiTerms, atanSmall, atanPartialSum, atanErr, widen,
            RatInterval.point, RatInterval.mul, RatInterval.sub]))

/-- High-precision exact-rational enclosure of `2*pi`. -/
def rootTwoPiInterval : RatInterval :=
  (RatInterval.point 2).mul rootPiInterval

theorem rootTwoPiInterval_containsReal :
    rootTwoPiInterval.ContainsReal (2 * Real.pi) := by
  exact RatInterval.mul_containsReal
    (RatInterval.point_containsReal (2 : ℚ))
    rootPiInterval_containsReal

end SparkInterval.Certified
