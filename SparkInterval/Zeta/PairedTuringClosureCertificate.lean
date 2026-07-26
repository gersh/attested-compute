/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.TuringGridEventCertificate

/-!
# Source-shaped paired-flank Turing closure

The Platt--Trudgian zeta scan does not obtain all of its finite Turing data
from one event list.  For a main block it retains three independent streams:

* a left flank supplies the signed weight used by the lower ceiling;
* the main stream supplies the isolated multiplicity slots and the signs at
  the two main-block endpoints; and
* a right flank supplies the signed weight used by the upper floor.

`TuringGridEventCertificate.binds_window` intentionally represents the
simpler one-stream case.  This module provides the source-shaped adapter.  It
checks all three streams independently, binds only the appropriate one-sided
weight from each flank, binds the main multiplicity slots and endpoint signs,
and checks the shared endpoint signs between adjacent streams.  The advertised
source counts are bound to two exact-rational certificates: the lower
`turing_min` call on `[a-21,a]` and the upper `turing_max` call on `[b,b+21]`.

The finite theorem proves

```text
lowerCount + mainIsolatedSlots = upperCount
```

directly from those checked bindings.  A second theorem composes the same
certificate with the explicit analytic Turing inequalities and an explicit
multiplicity-count lower bound.  No zero-simplicity premise appears: an event
may contribute two slots, and the analytic lower-bound premise is stated in
terms of total multiplicity-count increase.

This file does not assert that a machine event is a real Hardy-Z zero, prove
the analytic Turing inequalities, decode a production artifact, or bind the
three lattice ranges to physical ordinates.  Those remain explicit upstream
obligations.  There is no axiom, `sorry`, or `native_decide` here.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

open SparkInterval.Certificate

namespace TuringWindowInput

/-- The lower one-sided quotient used by `turing_min`.  In PT21 this input is
the left flank `[a-21,a]`, not the main block `[a,b]`. -/
def evaluateLower? (input : TuringWindowInput) : Option RatInterval :=
  input.evaluate?.map Prod.fst

/-- The upper one-sided quotient used by `turing_max`.  In PT21 this input is
the right flank `[b,b+21]`, not the main block `[a,b]`. -/
def evaluateUpper? (input : TuringWindowInput) : Option RatInterval :=
  input.evaluate?.map Prod.snd

theorem evaluateLower?_containsReal {input : TuringWindowInput}
    (values : input.Realization) {lower : RatInterval}
    (hresult : input.evaluateLower? = some lower) :
    lower.ContainsReal values.lowerQuotient := by
  unfold evaluateLower? at hresult
  cases hevaluate : input.evaluate? with
  | none => simp [hevaluate] at hresult
  | some pair =>
      rcases pair with ⟨actualLower, actualUpper⟩
      simp only [hevaluate, Option.map_some] at hresult
      cases hresult
      exact (input.evaluate?_containsReal values hevaluate).1

theorem evaluateUpper?_containsReal {input : TuringWindowInput}
    (values : input.Realization) {upper : RatInterval}
    (hresult : input.evaluateUpper? = some upper) :
    upper.ContainsReal values.upperQuotient := by
  unfold evaluateUpper? at hresult
  cases hevaluate : input.evaluate? with
  | none => simp [hevaluate] at hresult
  | some pair =>
      rcases pair with ⟨actualLower, actualUpper⟩
      simp only [hevaluate, Option.map_some] at hresult
      cases hresult
      exact (input.evaluate?_containsReal values hevaluate).2

end TuringWindowInput

/-- Exact finite certificate for the source `turing_min` call on the left
21-unit flank.  The unused right weight is fixed to zero. -/
structure LowerTuringCertificate where
  input : TuringWindowInput
  quotient : RatInterval
  count : Nat
  deriving DecidableEq, Repr

namespace LowerTuringCertificate

def ceilTarget (certificate : LowerTuringCertificate) : ℤ :=
  (certificate.count : ℤ) - 1

def IsValid (certificate : LowerTuringCertificate) : Prop :=
  certificate.input.a < certificate.input.b ∧
    0 < certificate.input.delta ∧
    certificate.input.sBound.IsValid ∧
    certificate.input.logPi.IsValid ∧
    certificate.input.imGammaIntegral.IsValid ∧
    certificate.input.pi.IsValid ∧
    0 ≤ certificate.input.sBound.lo ∧
    0 < certificate.input.pi.lo ∧
    certificate.input.leftWeight ≤ 0 ∧
    certificate.input.rightWeight = 0 ∧
    certificate.input.evaluateLower? = some certificate.quotient ∧
    (((certificate.ceilTarget : ℚ) - 1) < certificate.quotient.lo ∧
      certificate.quotient.hi ≤ (certificate.ceilTarget : ℚ)) ∧
    0 < certificate.count

instance (certificate : LowerTuringCertificate) : Decidable certificate.IsValid := by
  unfold IsValid RatInterval.IsValid
  infer_instance

def check (certificate : LowerTuringCertificate) : Bool :=
  decide certificate.IsValid

@[simp] theorem check_eq_true {certificate : LowerTuringCertificate} :
    certificate.check = true ↔ certificate.IsValid := by
  simp [check]

theorem ceil_quotient_eq (certificate : LowerTuringCertificate)
    (hcheck : certificate.check = true)
    (values : certificate.input.Realization) :
    ⌈values.lowerQuotient⌉ = certificate.ceilTarget := by
  have hvalid := certificate.check_eq_true.mp hcheck
  have hcontains := certificate.input.evaluateLower?_containsReal values
    hvalid.2.2.2.2.2.2.2.2.2.2.1
  have hcell := hvalid.2.2.2.2.2.2.2.2.2.2.2.1
  apply Int.ceil_eq_iff.mpr
  constructor
  · have hlo :
        (((certificate.ceilTarget : ℚ) - 1 : ℚ) : ℝ) <
          values.lowerQuotient := by
      apply (show
        (((certificate.ceilTarget : ℚ) - 1 : ℚ) : ℝ) <
          (certificate.quotient.lo : ℝ) by exact_mod_cast hcell.1) |>.trans_le
      exact hcontains.1
    simpa using hlo
  · have hhi : values.lowerQuotient ≤
        (((certificate.ceilTarget : ℚ) : ℝ)) := by
      apply hcontains.2.trans
      exact_mod_cast hcell.2
    simpa using hhi

end LowerTuringCertificate

/-- Exact finite certificate for the source `turing_max` call on the right
21-unit flank.  The unused left weight is fixed to zero. -/
structure UpperTuringCertificate where
  input : TuringWindowInput
  quotient : RatInterval
  count : Nat
  deriving DecidableEq, Repr

namespace UpperTuringCertificate

def floorTarget (certificate : UpperTuringCertificate) : ℤ :=
  (certificate.count : ℤ) - 1

def IsValid (certificate : UpperTuringCertificate) : Prop :=
  certificate.input.a < certificate.input.b ∧
    0 < certificate.input.delta ∧
    certificate.input.sBound.IsValid ∧
    certificate.input.logPi.IsValid ∧
    certificate.input.imGammaIntegral.IsValid ∧
    certificate.input.pi.IsValid ∧
    0 ≤ certificate.input.sBound.lo ∧
    0 < certificate.input.pi.lo ∧
    certificate.input.leftWeight = 0 ∧
    0 ≤ certificate.input.rightWeight ∧
    certificate.input.evaluateUpper? = some certificate.quotient ∧
    ((certificate.floorTarget : ℚ) ≤ certificate.quotient.lo ∧
      certificate.quotient.hi < ((certificate.floorTarget : ℚ) + 1)) ∧
    0 < certificate.count

instance (certificate : UpperTuringCertificate) : Decidable certificate.IsValid := by
  unfold IsValid RatInterval.IsValid
  infer_instance

def check (certificate : UpperTuringCertificate) : Bool :=
  decide certificate.IsValid

@[simp] theorem check_eq_true {certificate : UpperTuringCertificate} :
    certificate.check = true ↔ certificate.IsValid := by
  simp [check]

theorem floor_quotient_eq (certificate : UpperTuringCertificate)
    (hcheck : certificate.check = true)
    (values : certificate.input.Realization) :
    ⌊values.upperQuotient⌋ = certificate.floorTarget := by
  have hvalid := certificate.check_eq_true.mp hcheck
  have hcontains := certificate.input.evaluateUpper?_containsReal values
    hvalid.2.2.2.2.2.2.2.2.2.2.1
  have hcell := hvalid.2.2.2.2.2.2.2.2.2.2.2.1
  apply Int.floor_eq_iff.mpr
  constructor
  · have hlo : (((certificate.floorTarget : ℚ) : ℝ)) ≤
        values.upperQuotient := by
      apply (show (((certificate.floorTarget : ℚ) : ℝ)) ≤
        (certificate.quotient.lo : ℝ) by exact_mod_cast hcell.1) |>.trans
      exact hcontains.1
    simpa using hlo
  · have hhi : values.upperQuotient <
        ((((certificate.floorTarget : ℚ) + 1 : ℚ) : ℝ)) := by
      apply hcontains.2.trans_lt
      exact_mod_cast hcell.2
    simpa using hhi

end UpperTuringCertificate

/-- A source-shaped PT21 block certificate with three named event streams.

The three fields are deliberately not replaced by a concatenated event list:
their lattice origins and their roles in the Turing arithmetic differ.  It is
valid for two streams to have equal *values* (for example, two empty flanks),
so source-level distinctness means separate named artifacts rather than a
spurious list-inequality condition. -/
structure PairedTuringClosureCertificate where
  mainStream : TuringGridEventCertificate
  leftFlankStream : TuringGridEventCertificate
  rightFlankStream : TuringGridEventCertificate
  /-- Source `turing_min` arithmetic on `[mainLeft-21,mainLeft]`. -/
  lowerWindow : LowerTuringCertificate
  /-- Source `turing_max` arithmetic on `[mainRight,mainRight+21]`. -/
  upperWindow : UpperTuringCertificate
  /-- Source-advertised count at the main block's left endpoint. -/
  lowerCount : Nat
  /-- Source-advertised isolated multiplicity slots in the main block. -/
  mainIsolatedSlots : Nat
  /-- Source-advertised count at the main block's right endpoint. -/
  upperCount : Nat
  deriving DecidableEq, Repr

namespace PairedTuringClosureCertificate

/-- Exact proposition reflected by `check`.

Only the left weight of `leftFlankStream` and the right weight of
`rightFlankStream` are consumed.  The main stream supplies the gap and the
main endpoint signs.  The last two equalities make the shared grid endpoints
agree across the three independently checked streams. -/
def IsValid (certificate : PairedTuringClosureCertificate) : Prop :=
  certificate.mainStream.IsValid ∧
    certificate.leftFlankStream.IsValid ∧
    certificate.rightFlankStream.IsValid ∧
    certificate.lowerWindow.IsValid ∧
    certificate.upperWindow.IsValid ∧
    certificate.lowerCount = certificate.lowerWindow.count ∧
    certificate.mainIsolatedSlots = certificate.mainStream.isolatedCount ∧
    certificate.upperCount = certificate.upperWindow.count ∧
    certificate.lowerWindow.input.leftWeight =
      certificate.leftFlankStream.leftWeight ∧
    certificate.upperWindow.input.rightWeight =
      certificate.rightFlankStream.rightWeight ∧
    certificate.lowerCount + certificate.mainIsolatedSlots =
      certificate.upperCount ∧
    certificate.leftFlankStream.rightPositive =
      certificate.mainStream.leftPositive ∧
    certificate.mainStream.rightPositive =
      certificate.rightFlankStream.leftPositive

/-- Kernel-reducible checker for all finite stream and Turing bindings. -/
def check (certificate : PairedTuringClosureCertificate) : Bool :=
  certificate.mainStream.check &&
    certificate.leftFlankStream.check &&
    certificate.rightFlankStream.check &&
    certificate.lowerWindow.check &&
    certificate.upperWindow.check &&
    decide (certificate.lowerCount = certificate.lowerWindow.count) &&
    decide (certificate.mainIsolatedSlots =
      certificate.mainStream.isolatedCount) &&
    decide (certificate.upperCount = certificate.upperWindow.count) &&
    decide (certificate.lowerWindow.input.leftWeight =
      certificate.leftFlankStream.leftWeight) &&
    decide (certificate.upperWindow.input.rightWeight =
      certificate.rightFlankStream.rightWeight) &&
    decide (certificate.lowerCount + certificate.mainIsolatedSlots =
      certificate.upperCount) &&
    decide (certificate.leftFlankStream.rightPositive =
      certificate.mainStream.leftPositive) &&
    decide (certificate.mainStream.rightPositive =
      certificate.rightFlankStream.leftPositive)

@[simp] theorem check_eq_true
    {certificate : PairedTuringClosureCertificate} :
    certificate.check = true ↔ certificate.IsValid := by
  simp [check, IsValid]
  tauto

@[simp] theorem check_eq_false
    {certificate : PairedTuringClosureCertificate} :
    certificate.check = false ↔ ¬certificate.IsValid := by
  rw [Bool.eq_false_iff]
  exact not_congr check_eq_true

/-- Each of the three named event streams and the exact-rational Turing
window has passed its own checker. -/
theorem component_checks (certificate : PairedTuringClosureCertificate)
    (hcheck : certificate.check = true) :
    certificate.mainStream.check = true ∧
      certificate.leftFlankStream.check = true ∧
      certificate.rightFlankStream.check = true ∧
      certificate.lowerWindow.check = true ∧
      certificate.upperWindow.check = true := by
  have hvalid := certificate.check_eq_true.mp hcheck
  exact ⟨TuringGridEventCertificate.check_eq_true.mpr hvalid.1,
    TuringGridEventCertificate.check_eq_true.mpr hvalid.2.1,
    TuringGridEventCertificate.check_eq_true.mpr hvalid.2.2.1,
    LowerTuringCertificate.check_eq_true.mpr hvalid.2.2.2.1,
    UpperTuringCertificate.check_eq_true.mpr hvalid.2.2.2.2.1⟩

/-- The checked main slot count is exactly the sum of source multiplicities,
while the two consumed Turing weights are derived from the corresponding
flank event streams. -/
theorem binds_stream_arithmetic
    (certificate : PairedTuringClosureCertificate)
    (hcheck : certificate.check = true) :
    certificate.mainIsolatedSlots =
        turingGridTotalMultiplicity certificate.mainStream.events ∧
      certificate.lowerWindow.input.leftWeight =
        turingGridLeftWeight certificate.leftFlankStream.events ∧
      certificate.upperWindow.input.rightWeight =
        turingGridRightWeight certificate.rightFlankStream.spanSteps
          certificate.rightFlankStream.events := by
  rcases certificate.check_eq_true.mp hcheck with
    ⟨hmain, hleft, hright, _hlowerWindow, _hupperWindow, _hlowerCount,
      hmainSlots, _hupperCount, hleftWeight, hrightWeight, _hgap,
      _hleftShared, _hrightShared⟩
  constructor
  · exact hmainSlots.trans hmain.2.2.1
  constructor
  · exact hleftWeight.trans hleft.2.2.2.1
  · exact hrightWeight.trans hright.2.2.2.2.1

/-- The adjacent flank streams agree with the main stream at both shared
endpoints. -/
theorem binds_endpoint_signs
    (certificate : PairedTuringClosureCertificate)
    (hcheck : certificate.check = true) :
    certificate.leftFlankStream.rightPositive =
        certificate.mainStream.leftPositive ∧
      certificate.mainStream.rightPositive =
        certificate.rightFlankStream.leftPositive := by
  rcases certificate.check_eq_true.mp hcheck with
    ⟨_hmain, _hleft, _hright, _hlowerWindow, _hupperWindow, _hlowerCount,
      _hmainSlots, _hupperCount, _hleftWeight, _hrightWeight, _hgap,
      hleftShared, hrightShared⟩
  exact ⟨hleftShared, hrightShared⟩

/-- Successful finite checking proves the source-shaped closure equation.

The slot count is a sum of recorded multiplicities, not a count of events, so
the proof makes no zero-simplicity assumption. -/
theorem closure_equation (certificate : PairedTuringClosureCertificate)
    (hcheck : certificate.check = true) :
    certificate.lowerCount + certificate.mainIsolatedSlots =
      certificate.upperCount := by
  rcases certificate.check_eq_true.mp hcheck with
    ⟨_hmain, _hleft, _hright, _hlowerWindow, _hupperWindow, _hlowerCount,
      _hmainSlots, _hupperCount, _hleftWeight, _hrightWeight, hgap,
      _hleftShared, _hrightShared⟩
  exact hgap

/-- The lower advertised endpoint count is the uniquely checked ceiling that
uses the left-flank weight, and the upper count is the uniquely checked floor
that uses the right-flank weight. -/
theorem rounded_endpoint_counts
    (certificate : PairedTuringClosureCertificate)
    (hcheck : certificate.check = true)
    (lowerValues : certificate.lowerWindow.input.Realization)
    (upperValues : certificate.upperWindow.input.Realization) :
    ⌈lowerValues.lowerQuotient⌉ + 1 = (certificate.lowerCount : Int) ∧
      ⌊upperValues.upperQuotient⌋ + 1 = (certificate.upperCount : Int) := by
  rcases certificate.check_eq_true.mp hcheck with
    ⟨_hmain, _hleft, _hright, _hlowerWindow, _hupperWindow, hlowerCount,
      _hmainSlots, hupperCount, _hleftWeight, _hrightWeight, _hgap,
      _hleftShared, _hrightShared⟩
  have checks := certificate.component_checks hcheck
  have hlower := certificate.lowerWindow.ceil_quotient_eq checks.2.2.2.1
    lowerValues
  have hupper := certificate.upperWindow.floor_quotient_eq checks.2.2.2.2
    upperValues
  constructor
  · rw [hlower]
    unfold LowerTuringCertificate.ceilTarget
    omega
  · rw [hupper]
    unfold UpperTuringCertificate.floorTarget
    omega

/-- The two genuinely analytic one-sided Turing inequalities.  The lower
flank bounds the count at the main left endpoint; the right flank bounds the
count at the main right endpoint. -/
structure AnalyticTuringBounds
    (certificate : PairedTuringClosureCertificate)
    (lowerValues : certificate.lowerWindow.input.Realization)
    (upperValues : certificate.upperWindow.input.Realization)
    (countAtLeft countAtRight : Nat) : Prop where
  lower : ⌈lowerValues.lowerQuotient⌉ + 1 ≤ (countAtLeft : ℤ)
  upper : (countAtRight : ℤ) ≤ ⌊upperValues.upperQuotient⌋ + 1

/-- Explicit semantic premise supplied by the main bracket realization.

`countAtLeft` and `countAtRight` are analytic counts with multiplicity.  The
premise says that the main stream's certified slots give a lower bound on the
multiplicity-count increase; it does not assert that any zero is simple. -/
structure MainMultiplicitySlotLowerBound
    (certificate : PairedTuringClosureCertificate)
    (countAtLeft countAtRight : Nat) : Prop where
  count_le : countAtLeft + certificate.mainIsolatedSlots ≤ countAtRight

/-- Compose the finite paired-flank checker with the two deliberately
explicit analytic obligations.  This identifies both analytic endpoint
counts and their exact multiplicity-count increment. -/
theorem exact_endpoint_counts
    (certificate : PairedTuringClosureCertificate)
    (hcheck : certificate.check = true)
    (lowerValues : certificate.lowerWindow.input.Realization)
    (upperValues : certificate.upperWindow.input.Realization)
    {countAtLeft countAtRight : Nat}
    (analytic : certificate.AnalyticTuringBounds lowerValues upperValues
      countAtLeft countAtRight)
    (mainLower : certificate.MainMultiplicitySlotLowerBound
      countAtLeft countAtRight) :
    countAtLeft = certificate.lowerCount ∧
      countAtRight = certificate.upperCount ∧
      countAtLeft + certificate.mainIsolatedSlots = countAtRight := by
  have hrounded := certificate.rounded_endpoint_counts hcheck
    lowerValues upperValues
  have hlower : certificate.lowerCount ≤ countAtLeft := by
    exact_mod_cast (show (certificate.lowerCount : ℤ) ≤
      (countAtLeft : ℤ) by rw [← hrounded.1]; exact analytic.lower)
  have hupper : countAtRight ≤ certificate.upperCount := by
    exact_mod_cast (show (countAtRight : ℤ) ≤
      (certificate.upperCount : ℤ) by rw [← hrounded.2]; exact analytic.upper)
  have hgap := certificate.closure_equation hcheck
  have hmain := mainLower.count_le
  omega

end PairedTuringClosureCertificate

end SparkInterval.Zeta
