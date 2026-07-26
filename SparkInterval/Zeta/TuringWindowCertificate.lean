/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.RatInterval

/-!
# Checked finite arithmetic for a Platt--Trudgian Turing window

This file reproduces the *finite* arithmetic at the end of
`zeta_arb/turing.c` from Platt's public source.  For a window `[a,b]`, the
source computes

```text
 C       = (-(a+b) log(pi) (b-a) / 4 + ImGammaIntegral) / pi
 qUpper  = ( SBound - NrightIntegral + C) / (b-a)
 qLower  = (-SBound - NleftIntegral  + C) / (b-a)
 maxN    = floor(qUpper) + 1
 minN    = ceil(qLower)  + 1.
```

`NleftIntegral` and `NrightIntegral` are the exact integer weights produced
by the source sign scan, multiplied by the lattice spacing.  The left weight
is nonpositive and the right weight is nonnegative.

All interval operations and comparisons below use exact rationals.  A
successful Boolean check proves that every real choice inside the supplied
component intervals has the advertised floor and ceiling.  The final theorem
also proves the source count closure: if the isolated brackets give the
matching multiplicity-count lower bound, the Turing endpoint bounds force
both endpoint counts to be exact.  It does not assume that zeros are simple.

The genuinely analytic inputs remain explicit:

* the intervals must really enclose `log pi`, the integrated Gamma phase, and
  the Trudgian `S(t)` bound;
* `AnalyticTuringBounds` is the Turing/argument-principle theorem connecting
  the two real quotients to multiplicity counts; and
* a separate interpolation theorem must show that the sign brackets enclose
  the actual Hardy function (including the joint Appendix-C C.1
  Weiss/non-bandlimited and corrected-C.3 omitted-tail errors).

Thus this module removes host floating-point floor/ceiling and count-gap
decisions from the trusted boundary without disguising an analytic theorem as
a finite computation.  It contains no axiom, `sorry`, or `native_decide`.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open SparkInterval.Certificate

/-- Untrusted source-shaped inputs for one Turing window. -/
structure TuringWindowInput where
  /-- Left and right physical ordinates. -/
  a : ℚ
  b : ℚ
  /-- Lattice spacing (`21/512` in the PT21 source). -/
  delta : ℚ
  /-- Enclosure of `0.059 * log(t) + 2.067`. -/
  sBound : RatInterval
  /-- Enclosure of `log pi`. -/
  logPi : RatInterval
  /-- Enclosure returned by the source's `im_int(a,b)`. -/
  imGammaIntegral : RatInterval
  /-- Positive enclosure of `pi`. -/
  pi : RatInterval
  /-- Integer coefficients returned by `Nleft_int` and `Nright_int`. -/
  leftWeight : ℤ
  rightWeight : ℤ
  deriving DecidableEq, Repr

namespace TuringWindowInput

/-- Exact interval for the window width. -/
def span (input : TuringWindowInput) : RatInterval :=
  RatInterval.point (input.b - input.a)

/-- Source `ln_term`: `-(a+b) log(pi) (b-a) / 4`. -/
def logTerm (input : TuringWindowInput) : RatInterval :=
  ((RatInterval.point (-(input.a + input.b) / 4)).mul input.logPi).mul input.span

/-- Exact interval for the left weighted lattice integral. -/
def leftIntegral (input : TuringWindowInput) : RatInterval :=
  RatInterval.point ((input.leftWeight : ℚ) * input.delta)

/-- Exact interval for the right weighted lattice integral. -/
def rightIntegral (input : TuringWindowInput) : RatInterval :=
  RatInterval.point ((input.rightWeight : ℚ) * input.delta)

/-- Evaluate the exact-rational analogue of `turing_min` and `turing_max`.
The pair is `(qLower,qUpper)`.  Division is fail-closed if a denominator
interval contains zero. -/
def evaluate? (input : TuringWindowInput) :
    Option (RatInterval × RatInterval) := do
  let common ← (input.logTerm.add input.imGammaIntegral).div? input.pi
  let lowerNumerator :=
    input.sBound.neg.sub input.leftIntegral |>.add common
  let upperNumerator :=
    input.sBound.sub input.rightIntegral |>.add common
  let lower ← lowerNumerator.div? input.span
  let upper ← upperNumerator.div? input.span
  pure (lower, upper)

/-- Real values whose enclosures are supplied by a campaign. -/
structure Realization (input : TuringWindowInput) where
  sBound : ℝ
  logPi : ℝ
  imGammaIntegral : ℝ
  pi : ℝ
  sBound_mem : input.sBound.ContainsReal sBound
  logPi_mem : input.logPi.ContainsReal logPi
  imGammaIntegral_mem : input.imGammaIntegral.ContainsReal imGammaIntegral
  pi_mem : input.pi.ContainsReal pi

/-- Real source `ln_term` for a realization. -/
def Realization.logTerm {input : TuringWindowInput}
    (values : input.Realization) : ℝ :=
  ((-(input.a + input.b) / 4 : ℚ) : ℝ) * values.logPi *
    ((input.b - input.a : ℚ) : ℝ)

/-- Shared Gamma/log-pi term in the two Turing quotients. -/
noncomputable def Realization.common {input : TuringWindowInput}
    (values : input.Realization) : ℝ :=
  (values.logTerm + values.imGammaIntegral) / values.pi

/-- Real quotient rounded upward by `turing_max`. -/
noncomputable def Realization.upperQuotient {input : TuringWindowInput}
    (values : input.Realization) : ℝ :=
  (values.sBound -
      (((input.rightWeight : ℤ) : ℚ) * input.delta : ℚ) +
      values.common) /
    ((input.b - input.a : ℚ) : ℝ)

/-- Real quotient rounded downward by `turing_min`. -/
noncomputable def Realization.lowerQuotient {input : TuringWindowInput}
    (values : input.Realization) : ℝ :=
  (-values.sBound -
      (((input.leftWeight : ℤ) : ℚ) * input.delta : ℚ) +
      values.common) /
    ((input.b - input.a : ℚ) : ℝ)

/-- Soundness of the complete finite interval evaluation. -/
theorem evaluate?_containsReal {input : TuringWindowInput}
    (values : input.Realization) {lower upper : RatInterval}
    (hresult : input.evaluate? = some (lower, upper)) :
    lower.ContainsReal values.lowerQuotient ∧
      upper.ContainsReal values.upperQuotient := by
  unfold evaluate? at hresult
  cases hcommon : (input.logTerm.add input.imGammaIntegral).div? input.pi with
  | none => simp [hcommon] at hresult
  | some common =>
      let lowerNumerator := input.sBound.neg.sub input.leftIntegral |>.add common
      let upperNumerator := input.sBound.sub input.rightIntegral |>.add common
      cases hlower : lowerNumerator.div? input.span with
      | none => simp [hcommon, lowerNumerator, hlower] at hresult
      | some lower' =>
          cases hupper : upperNumerator.div? input.span with
          | none =>
              simp [hcommon, lowerNumerator, upperNumerator, hlower, hupper] at hresult
          | some upper' =>
              simp [hcommon, lowerNumerator, upperNumerator, hlower, hupper] at hresult
              obtain ⟨rfl, rfl⟩ := hresult
              have hspan : input.span.ContainsReal
                  (((input.b - input.a : ℚ) : ℝ)) := by
                exact RatInterval.point_containsReal _
              have hlogCoefficient :
                  (RatInterval.point (-(input.a + input.b) / 4)).ContainsReal
                    (((-(input.a + input.b) / 4 : ℚ) : ℝ)) := by
                exact RatInterval.point_containsReal _
              have hlogTerm : input.logTerm.ContainsReal values.logTerm := by
                exact RatInterval.mul_containsReal
                  (RatInterval.mul_containsReal hlogCoefficient values.logPi_mem)
                  hspan
              have hcommonValue : common.ContainsReal values.common := by
                exact RatInterval.div?_containsReal
                  (RatInterval.add_containsReal hlogTerm values.imGammaIntegral_mem)
                  values.pi_mem hcommon
              have hleft : input.leftIntegral.ContainsReal
                  (((((input.leftWeight : ℤ) : ℚ) * input.delta : ℚ) : ℝ)) := by
                exact RatInterval.point_containsReal _
              have hright : input.rightIntegral.ContainsReal
                  (((((input.rightWeight : ℤ) : ℚ) * input.delta : ℚ) : ℝ)) := by
                exact RatInterval.point_containsReal _
              constructor
              · apply RatInterval.div?_containsReal _ hspan hlower
                exact RatInterval.add_containsReal
                  (RatInterval.sub_containsReal
                    (RatInterval.neg_containsReal values.sBound_mem) hleft)
                  hcommonValue
              · apply RatInterval.div?_containsReal _ hspan hupper
                exact RatInterval.add_containsReal
                  (RatInterval.sub_containsReal values.sBound_mem hright)
                  hcommonValue

end TuringWindowInput

/-- Untrusted finite certificate around one evaluated source window. -/
structure TuringWindowCertificate where
  input : TuringWindowInput
  lowerQuotient : RatInterval
  upperQuotient : RatInterval
  /-- Advertised `ceil(qLower)+1` and `floor(qUpper)+1`. -/
  lowerCount : Nat
  upperCount : Nat
  /-- Number of isolated multiplicity slots in `[a,b]`. -/
  isolatedCount : Nat
  /-- Strict endpoint signs, used for the source parity sanity check. -/
  leftPositive : Bool
  rightPositive : Bool
  deriving DecidableEq, Repr

namespace TuringWindowCertificate

/-- The integer expected from `ceil(qLower)`. -/
def lowerCeilTarget (certificate : TuringWindowCertificate) : ℤ :=
  (certificate.lowerCount : ℤ) - 1

/-- The integer expected from `floor(qUpper)`. -/
def upperFloorTarget (certificate : TuringWindowCertificate) : ℤ :=
  (certificate.upperCount : ℤ) - 1

/-- Exact source-shaped proposition reflected by `check`.

The open/closed endpoints in the two rounding cells are intentional:
`ceil q = k` iff `k-1 < q <= k`, whereas `floor q = k` iff
`k <= q < k+1`. -/
def IsValid (certificate : TuringWindowCertificate) : Prop :=
  certificate.input.a < certificate.input.b ∧
    0 < certificate.input.delta ∧
    certificate.input.sBound.IsValid ∧
    certificate.input.logPi.IsValid ∧
    certificate.input.imGammaIntegral.IsValid ∧
    certificate.input.pi.IsValid ∧
    0 ≤ certificate.input.sBound.lo ∧
    0 < certificate.input.pi.lo ∧
    certificate.input.leftWeight ≤ 0 ∧
    0 ≤ certificate.input.rightWeight ∧
    certificate.input.evaluate? =
      some (certificate.lowerQuotient, certificate.upperQuotient) ∧
    (((certificate.lowerCeilTarget : ℚ) - 1) <
      certificate.lowerQuotient.lo ∧
      certificate.lowerQuotient.hi ≤ (certificate.lowerCeilTarget : ℚ)) ∧
    ((certificate.upperFloorTarget : ℚ) ≤
      certificate.upperQuotient.lo ∧
      certificate.upperQuotient.hi <
        ((certificate.upperFloorTarget : ℚ) + 1)) ∧
    0 < certificate.lowerCount ∧
    certificate.lowerCount + certificate.isolatedCount = certificate.upperCount ∧
    ((certificate.leftPositive = certificate.rightPositive) ↔
      certificate.isolatedCount % 2 = 0)

set_option maxRecDepth 1000 in
instance (certificate : TuringWindowCertificate) :
    Decidable certificate.IsValid := by
  unfold IsValid RatInterval.IsValid
  infer_instance

/-- Kernel-reducible exact-rational checker. -/
def check (certificate : TuringWindowCertificate) : Bool :=
  decide (certificate.input.a < certificate.input.b) &&
  decide (0 < certificate.input.delta) &&
  certificate.input.sBound.isValid &&
  certificate.input.logPi.isValid &&
  certificate.input.imGammaIntegral.isValid &&
  certificate.input.pi.isValid &&
  decide (0 ≤ certificate.input.sBound.lo) &&
  decide (0 < certificate.input.pi.lo) &&
  decide (certificate.input.leftWeight ≤ 0) &&
  decide (0 ≤ certificate.input.rightWeight) &&
  decide (certificate.input.evaluate? =
    some (certificate.lowerQuotient, certificate.upperQuotient)) &&
  decide (((certificate.lowerCeilTarget : ℚ) - 1) <
    certificate.lowerQuotient.lo) &&
  decide (certificate.lowerQuotient.hi ≤
    (certificate.lowerCeilTarget : ℚ)) &&
  decide ((certificate.upperFloorTarget : ℚ) ≤
    certificate.upperQuotient.lo) &&
  decide (certificate.upperQuotient.hi <
    ((certificate.upperFloorTarget : ℚ) + 1)) &&
  decide (0 < certificate.lowerCount) &&
  decide (certificate.lowerCount + certificate.isolatedCount =
    certificate.upperCount) &&
  decide ((certificate.leftPositive = certificate.rightPositive) ↔
    certificate.isolatedCount % 2 = 0)

@[simp] theorem check_eq_true {certificate : TuringWindowCertificate} :
    certificate.check = true ↔ certificate.IsValid := by
  simp [check, IsValid, RatInterval.IsValid]
  tauto

@[simp] theorem check_eq_false {certificate : TuringWindowCertificate} :
    certificate.check = false ↔ ¬certificate.IsValid := by
  simp [check, IsValid, RatInterval.IsValid]

/-- Successful checking proves the exact source floor decision for every
realization inside the input intervals. -/
theorem floor_upperQuotient_eq (certificate : TuringWindowCertificate)
    (hcheck : certificate.check = true)
    (values : certificate.input.Realization) :
    ⌊values.upperQuotient⌋ = certificate.upperFloorTarget := by
  have hvalid := certificate.check_eq_true.mp hcheck
  obtain ⟨_ha, _hdelta, _hsValid, _hlogValid, _himValid, _hpiValid,
    _hsNonneg, _hpiPos, _hleft, _hright, heval, _hlowerCell,
    hupperCell, _hcountPositive, _hgap, _hparity⟩ := hvalid
  have hcontains := certificate.input.evaluate?_containsReal values heval
  apply Int.floor_eq_iff.mpr
  constructor
  · have hlo : (((certificate.upperFloorTarget : ℚ) : ℝ)) ≤
        values.upperQuotient := by
      apply (show (((certificate.upperFloorTarget : ℚ) : ℝ)) ≤
        (certificate.upperQuotient.lo : ℝ) by exact_mod_cast hupperCell.1) |>.trans
      exact hcontains.2.1
    simpa using hlo
  · have hhi : values.upperQuotient <
        ((((certificate.upperFloorTarget : ℚ) + 1 : ℚ) : ℝ)) := by
      apply hcontains.2.2.trans_lt
      exact_mod_cast hupperCell.2
    simpa using hhi

/-- Successful checking proves the exact source ceiling decision for every
realization inside the input intervals. -/
theorem ceil_lowerQuotient_eq (certificate : TuringWindowCertificate)
    (hcheck : certificate.check = true)
    (values : certificate.input.Realization) :
    ⌈values.lowerQuotient⌉ = certificate.lowerCeilTarget := by
  have hvalid := certificate.check_eq_true.mp hcheck
  obtain ⟨_ha, _hdelta, _hsValid, _hlogValid, _himValid, _hpiValid,
    _hsNonneg, _hpiPos, _hleft, _hright, heval, hlowerCell,
    _hupperCell, _hcountPositive, _hgap, _hparity⟩ := hvalid
  have hcontains := certificate.input.evaluate?_containsReal values heval
  apply Int.ceil_eq_iff.mpr
  constructor
  · have hlo :
        (((certificate.lowerCeilTarget : ℚ) - 1 : ℚ) : ℝ) <
          values.lowerQuotient := by
      apply (show
        (((certificate.lowerCeilTarget : ℚ) - 1 : ℚ) : ℝ) <
          (certificate.lowerQuotient.lo : ℝ) by
            exact_mod_cast hlowerCell.1) |>.trans_le
      exact hcontains.1.1
    simpa using hlo
  · have hhi : values.lowerQuotient ≤
        (((certificate.lowerCeilTarget : ℚ) : ℝ)) := by
      apply hcontains.1.2.trans
      exact_mod_cast hlowerCell.2
    simpa using hhi

/-- The accepted count gap is exactly the isolated count. -/
theorem lowerCount_add_isolatedCount_eq_upperCount
    (certificate : TuringWindowCertificate)
    (hcheck : certificate.check = true) :
    certificate.lowerCount + certificate.isolatedCount = certificate.upperCount :=
  by
    obtain ⟨_ha, _hdelta, _hsValid, _hlogValid, _himValid, _hpiValid,
      _hsNonneg, _hpiPos, _hleft, _hright, _heval, _hlowerCell,
      _hupperCell, _hcountPositive, hgap, _hparity⟩ :=
        certificate.check_eq_true.mp hcheck
    exact hgap

/-- The source endpoint-sign parity sanity check is retained exactly. -/
theorem endpointSigns_eq_iff_even_isolatedCount
    (certificate : TuringWindowCertificate)
    (hcheck : certificate.check = true) :
    (certificate.leftPositive = certificate.rightPositive) ↔
      certificate.isolatedCount % 2 = 0 := by
  obtain ⟨_ha, _hdelta, _hsValid, _hlogValid, _himValid, _hpiValid,
    _hsNonneg, _hpiPos, _hleft, _hright, _heval, _hlowerCell,
    _hupperCell, _hcountPositive, _hgap, hparity⟩ :=
      certificate.check_eq_true.mp hcheck
  exact hparity

/-- The genuinely analytic conclusion of Turing's method.  It counts zeros
with multiplicity at the two endpoints and uses exactly the two real
quotients evaluated above. -/
structure AnalyticTuringBounds (certificate : TuringWindowCertificate)
    (values : certificate.input.Realization)
    (countAtLeft countAtRight : Nat) : Prop where
  lower : ⌈values.lowerQuotient⌉ + 1 ≤ (countAtLeft : ℤ)
  upper : (countAtRight : ℤ) ≤ ⌊values.upperQuotient⌋ + 1

/-- Checked rounding turns the analytic Turing inequalities into the claimed
natural-number endpoint bounds. -/
theorem endpoint_bounds (certificate : TuringWindowCertificate)
    (hcheck : certificate.check = true)
    (values : certificate.input.Realization)
    {countAtLeft countAtRight : Nat}
    (analytic : certificate.AnalyticTuringBounds values countAtLeft countAtRight) :
    certificate.lowerCount ≤ countAtLeft ∧
      countAtRight ≤ certificate.upperCount := by
  have hvalid := certificate.check_eq_true.mp hcheck
  obtain ⟨_ha, _hdelta, _hsValid, _hlogValid, _himValid, _hpiValid,
    _hsNonneg, _hpiPos, _hleft, _hright, _heval, _hlowerCell,
    _hupperCell, hlowerPositive, _hgap, _hparity⟩ := hvalid
  have hlowerTarget : certificate.lowerCeilTarget + 1 =
      (certificate.lowerCount : ℤ) := by
    unfold lowerCeilTarget
    omega
  have hupperTarget : certificate.upperFloorTarget + 1 =
      (certificate.upperCount : ℤ) := by
    unfold upperFloorTarget
    omega
  constructor
  · exact_mod_cast (show (certificate.lowerCount : ℤ) ≤
        (countAtLeft : ℤ) by
      rw [← hlowerTarget, ← certificate.ceil_lowerQuotient_eq hcheck values]
      exact analytic.lower)
  · exact_mod_cast (show (countAtRight : ℤ) ≤
        (certificate.upperCount : ℤ) by
      rw [← hupperTarget, ← certificate.floor_upperQuotient_eq hcheck values]
      exact analytic.upper)

/-- Source count closure.  `isolatedLower` is supplied by disjoint certified
sign brackets, interpreted as a lower bound on the multiplicity-count
increase.  Matching it to the Turing gap forces both endpoints and the window
increment to be exact.  Multiple zeros are allowed: they merely contribute
more than one to the analytic increment. -/
theorem exact_endpoint_counts (certificate : TuringWindowCertificate)
    (hcheck : certificate.check = true)
    (values : certificate.input.Realization)
    {countAtLeft countAtRight : Nat}
    (analytic : certificate.AnalyticTuringBounds values countAtLeft countAtRight)
    (isolatedLower : countAtLeft + certificate.isolatedCount ≤ countAtRight) :
    countAtLeft = certificate.lowerCount ∧
      countAtRight = certificate.upperCount ∧
      countAtLeft + certificate.isolatedCount = countAtRight := by
  have hbounds := certificate.endpoint_bounds hcheck values analytic
  have hgap := certificate.lowerCount_add_isolatedCount_eq_upperCount hcheck
  omega

end TuringWindowCertificate

end SparkInterval.Zeta
