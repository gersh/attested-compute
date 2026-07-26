/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.TuringWindowCertificate

/-!
# Exact grid-event weights for the Platt--Trudgian Turing scan

The functions `Nleft_int` and `Nright_int` in Platt's `zeta_arb/turing.c`
convert isolated zero events on a uniform lattice into two signed integer
weights.  A sign change between steps `l` and `r` contributes

```text
 -(l)                 to Nleft_int,
  (spanSteps - r)     to Nright_int.
```

A resolved stationary point contributes two roots with the same conservative
outer cell, hence the same formula with multiplicity two.  Multiplying the
integer results by the lattice spacing gives the two real integrals consumed
by `TuringWindowCertificate`.

This module checks the event cells, their ordering, their source multiplicity
(one for a sign change, two for a resolved stationary cell), the two derived
weights, the total isolated count, and the
endpoint-sign parity.  The producer can no longer provide an isolated count
and unrelated Turing weights.  What remains outside this finite checker is
the evaluator-specific proof that each event really contains the stated
number of Hardy-Z zeros.  In production that proof is built from the strict
endpoint brackets (including the two brackets returned by
`resolve_stat_point`), without assuming zero simplicity.

No axiom, `sorry`, or `native_decide` occurs here.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

/-- A conservative lattice cell containing one or more isolated roots.
`leftStep` and `rightStep` are offsets from the left endpoint of the Turing
window. -/
structure TuringGridEvent where
  leftStep : Nat
  rightStep : Nat
  multiplicity : Nat
  deriving DecidableEq, Repr

namespace TuringGridEvent

/-- Local source-shaped validity inside a lattice window. -/
def IsValid (spanSteps : Nat) (event : TuringGridEvent) : Prop :=
  event.leftStep < event.rightStep ∧
    event.rightStep ≤ spanSteps ∧
    (event.multiplicity = 1 ∨ event.multiplicity = 2)

instance (spanSteps : Nat) (event : TuringGridEvent) :
    Decidable (event.IsValid spanSteps) := by
  unfold IsValid
  infer_instance

def check (spanSteps : Nat) (event : TuringGridEvent) : Bool :=
  decide (event.leftStep < event.rightStep) &&
    decide (event.rightStep ≤ spanSteps) &&
    decide (event.multiplicity = 1 ∨ event.multiplicity = 2)

@[simp] theorem check_eq_true {spanSteps : Nat} {event : TuringGridEvent} :
    event.check spanSteps = true ↔ event.IsValid spanSteps := by
  simp [check, IsValid]
  tauto

/-- Unsigned magnitude of this event's contribution to `Nleft_int`. -/
def leftMagnitude (event : TuringGridEvent) : Nat :=
  event.multiplicity * event.leftStep

/-- Unsigned contribution to `Nright_int`.  This is used only for a locally
valid event, where truncated subtraction agrees with ordinary subtraction. -/
def rightMagnitude (spanSteps : Nat) (event : TuringGridEvent) : Nat :=
  event.multiplicity * (spanSteps - event.rightStep)

end TuringGridEvent

/-- Recursive event-stream validity.  Consecutive conservative cells may
touch but may not cross or overlap.  A double zero resolved inside one coarse
cell is represented by one event of multiplicity two. -/
def TuringGridEventsValidFrom (spanSteps : Nat) :
    Option Nat → List TuringGridEvent → Prop
  | _, [] => True
  | previousRight, event :: rest =>
      event.IsValid spanSteps ∧
        (match previousRight with
          | none => True
          | some previous => previous ≤ event.leftStep) ∧
        TuringGridEventsValidFrom spanSteps (some event.rightStep) rest

/-- Executable one-pass event-stream check. -/
def checkTuringGridEventsFrom (spanSteps : Nat) :
    Option Nat → List TuringGridEvent → Bool
  | _, [] => true
  | previousRight, event :: rest =>
      event.check spanSteps &&
        (match previousRight with
          | none => true
          | some previous => decide (previous ≤ event.leftStep)) &&
        checkTuringGridEventsFrom spanSteps (some event.rightStep) rest

theorem checkTuringGridEventsFrom_eq_true
    (spanSteps : Nat) (previousRight : Option Nat)
    (events : List TuringGridEvent) :
    checkTuringGridEventsFrom spanSteps previousRight events = true ↔
      TuringGridEventsValidFrom spanSteps previousRight events := by
  induction events generalizing previousRight with
  | nil => simp [checkTuringGridEventsFrom, TuringGridEventsValidFrom]
  | cons event rest induction =>
      cases previousRight with
      | none =>
          simp [checkTuringGridEventsFrom, TuringGridEventsValidFrom, induction]
      | some previous =>
          simp [checkTuringGridEventsFrom, TuringGridEventsValidFrom, induction]
          tauto

/-- Total number of roots represented by the event stream. -/
def turingGridTotalMultiplicity (events : List TuringGridEvent) : Nat :=
  (events.map (fun event => event.multiplicity)).sum

/-- Exact signed coefficient returned by the conservative left assignment. -/
def turingGridLeftWeight (events : List TuringGridEvent) : Int :=
  -((events.map TuringGridEvent.leftMagnitude).sum : Int)

/-- Exact signed coefficient returned by the conservative right assignment. -/
def turingGridRightWeight
    (spanSteps : Nat) (events : List TuringGridEvent) : Int :=
  ((events.map (TuringGridEvent.rightMagnitude spanSteps)).sum : Int)

/-- Untrusted finite certificate binding a zero-event stream to all integers
consumed by a Turing window. -/
structure TuringGridEventCertificate where
  spanSteps : Nat
  events : List TuringGridEvent
  isolatedCount : Nat
  leftWeight : Int
  rightWeight : Int
  leftPositive : Bool
  rightPositive : Bool
  deriving DecidableEq, Repr

namespace TuringGridEventCertificate

def IsValid (certificate : TuringGridEventCertificate) : Prop :=
  0 < certificate.spanSteps ∧
    TuringGridEventsValidFrom certificate.spanSteps none certificate.events ∧
    certificate.isolatedCount =
      turingGridTotalMultiplicity certificate.events ∧
    certificate.leftWeight = turingGridLeftWeight certificate.events ∧
    certificate.rightWeight =
      turingGridRightWeight certificate.spanSteps certificate.events ∧
    ((certificate.leftPositive = certificate.rightPositive) ↔
      certificate.isolatedCount % 2 = 0)

def check (certificate : TuringGridEventCertificate) : Bool :=
  decide (0 < certificate.spanSteps) &&
    checkTuringGridEventsFrom certificate.spanSteps none certificate.events &&
    decide (certificate.isolatedCount =
      turingGridTotalMultiplicity certificate.events) &&
    decide (certificate.leftWeight =
      turingGridLeftWeight certificate.events) &&
    decide (certificate.rightWeight =
      turingGridRightWeight certificate.spanSteps certificate.events) &&
    decide ((certificate.leftPositive = certificate.rightPositive) ↔
      certificate.isolatedCount % 2 = 0)

@[simp] theorem check_eq_true {certificate : TuringGridEventCertificate} :
    certificate.check = true ↔ certificate.IsValid := by
  simp [check, IsValid, checkTuringGridEventsFrom_eq_true]
  tauto

/-- A checked event stream has the source sign convention for its weights. -/
theorem weight_signs (certificate : TuringGridEventCertificate)
    (hcheck : certificate.check = true) :
    certificate.leftWeight ≤ 0 ∧ 0 ≤ certificate.rightWeight := by
  have hvalid := certificate.check_eq_true.mp hcheck
  rw [hvalid.2.2.2.1, hvalid.2.2.2.2.1]
  constructor
  · simp only [turingGridLeftWeight, neg_nonpos]
    exact Int.natCast_nonneg _
  · simp only [turingGridRightWeight]
    exact Int.natCast_nonneg _

/-- Checked values bind exactly to the corresponding fields of a finite
Turing arithmetic input. -/
def MatchesWindowInput (certificate : TuringGridEventCertificate)
    (input : TuringWindowInput) : Prop :=
  input.leftWeight = certificate.leftWeight ∧
    input.rightWeight = certificate.rightWeight

instance (certificate : TuringGridEventCertificate)
    (input : TuringWindowInput) :
    Decidable (certificate.MatchesWindowInput input) := by
  unfold MatchesWindowInput
  infer_instance

def matchesWindowInput (certificate : TuringGridEventCertificate)
    (input : TuringWindowInput) : Bool :=
  decide (certificate.MatchesWindowInput input)

@[simp] theorem matchesWindowInput_eq_true
    {certificate : TuringGridEventCertificate} {input : TuringWindowInput} :
    certificate.matchesWindowInput input = true ↔
      certificate.MatchesWindowInput input := by
  simp [matchesWindowInput]

/-- A checked event certificate matching a checked Turing window forces the
window's isolated count and endpoint signs to be the event-stream values as
well as its weights. -/
theorem binds_window (certificate : TuringGridEventCertificate)
    (window : TuringWindowCertificate)
    (hevents : certificate.check = true)
    (hinput : certificate.matchesWindowInput window.input = true)
    (hcount : window.isolatedCount = certificate.isolatedCount)
    (hleftSign : window.leftPositive = certificate.leftPositive)
    (hrightSign : window.rightPositive = certificate.rightPositive) :
    window.input.leftWeight = turingGridLeftWeight certificate.events ∧
      window.input.rightWeight =
        turingGridRightWeight certificate.spanSteps certificate.events ∧
      window.isolatedCount = turingGridTotalMultiplicity certificate.events ∧
      ((window.leftPositive = window.rightPositive) ↔
        window.isolatedCount % 2 = 0) := by
  have heventValid := certificate.check_eq_true.mp hevents
  have hmatches := certificate.matchesWindowInput_eq_true.mp hinput
  have heventParity := heventValid.2.2.2.2.2
  constructor
  · rw [hmatches.1, heventValid.2.2.2.1]
  constructor
  · rw [hmatches.2, heventValid.2.2.2.2.1]
  constructor
  · rw [hcount, heventValid.2.2.1]
  · simpa only [hleftSign, hrightSign, hcount] using heventParity

end TuringGridEventCertificate

end SparkInterval.Zeta
