/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib

/-!
# Sound outer-interval filter for PT21 stationary candidates

The optimized exact-rational replay first asks whether cheap outward binary64
boxes already decide the strict stationary predicate.  It accepts or rejects
only in the cases proved below and falls back to exact rationals otherwise.

This module proves the order-theoretic part of that optimization.  The
architecture-level fact that the two `nextafter` widenings enclose each
binary64 addition/subtraction remains part of the executable/IEEE refinement
boundary.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.PT21StationaryCandidateFilter

structure Interval where
  lo : ℚ
  hi : ℚ
  deriving DecidableEq

def Interval.IsValid (value : Interval) : Prop :=
  value.lo ≤ value.hi

def Encloses (outer exact : Interval) : Prop :=
  outer.lo ≤ exact.lo ∧ exact.hi ≤ outer.hi

def StrictStationary (positive : Bool)
    (first middle right : Interval) : Prop :=
  if positive then
    middle.hi < first.lo ∧ middle.hi < right.lo
  else
    first.hi < middle.lo ∧ right.hi < middle.lo

/-- A strictly positive lower endpoint of an enclosing box certifies the
exact interval's positive sign. -/
theorem certified_positive
    {outer exact : Interval}
    (hencloses : Encloses outer exact)
    (hpositive : 0 < outer.lo) :
    0 < exact.lo :=
  lt_of_lt_of_le hpositive hencloses.1

/-- A strictly negative upper endpoint of an enclosing box certifies the
exact interval's negative sign. -/
theorem certified_negative
    {outer exact : Interval}
    (hencloses : Encloses outer exact)
    (hnegative : outer.hi < 0) :
    exact.hi < 0 :=
  lt_of_le_of_lt hencloses.2 hnegative

/-- If outward boxes certify both strict comparisons, the exact intervals
satisfy the source stationary predicate. -/
theorem certified_true
    {positive : Bool}
    {firstOuter middleOuter rightOuter : Interval}
    {firstExact middleExact rightExact : Interval}
    (hfirst : Encloses firstOuter firstExact)
    (hmiddle : Encloses middleOuter middleExact)
    (hright : Encloses rightOuter rightExact)
    (hcertified : StrictStationary positive
      firstOuter middleOuter rightOuter) :
    StrictStationary positive firstExact middleExact rightExact := by
  cases positive <;>
    simp only [StrictStationary, ↓reduceIte] at hcertified ⊢
  · constructor
    · exact lt_of_le_of_lt hfirst.2
        (lt_of_lt_of_le hcertified.1 hmiddle.1)
    · exact lt_of_le_of_lt hright.2
        (lt_of_lt_of_le hcertified.2 hmiddle.1)
  · constructor
    · exact lt_of_le_of_lt hmiddle.2
        (lt_of_lt_of_le hcertified.1 hfirst.1)
    · exact lt_of_le_of_lt hmiddle.2
        (lt_of_lt_of_le hcertified.2 hright.1)

/-- A separated reverse comparison in an outward box soundly rejects the
positive-source stationary predicate. -/
theorem certified_false_positive
    {firstOuter middleOuter rightOuter : Interval}
    {firstExact middleExact rightExact : Interval}
    (hfirst : Encloses firstOuter firstExact)
    (hmiddle : Encloses middleOuter middleExact)
    (hright : Encloses rightOuter rightExact)
    (hfirstValid : firstExact.IsValid)
    (hmiddleValid : middleExact.IsValid)
    (hrightValid : rightExact.IsValid)
    (hrejected :
      firstOuter.hi ≤ middleOuter.lo ∨
        rightOuter.hi ≤ middleOuter.lo) :
    ¬ StrictStationary true firstExact middleExact rightExact := by
  simp only [StrictStationary, ↓reduceIte]
  intro hstrict
  rcases hrejected with hleft | hrightRejected
  · have hnot :
        firstExact.lo ≤ middleExact.hi := by
      calc
        firstExact.lo ≤ firstExact.hi := hfirstValid
        _ ≤ firstOuter.hi := hfirst.2
        _ ≤ middleOuter.lo := hleft
        _ ≤ middleExact.lo := hmiddle.1
        _ ≤ middleExact.hi := hmiddleValid
    exact (not_lt_of_ge hnot) hstrict.1
  · have hnot :
        rightExact.lo ≤ middleExact.hi := by
      calc
        rightExact.lo ≤ rightExact.hi := hrightValid
        _ ≤ rightOuter.hi := hright.2
        _ ≤ middleOuter.lo := hrightRejected
        _ ≤ middleExact.lo := hmiddle.1
        _ ≤ middleExact.hi := hmiddleValid
    exact (not_lt_of_ge hnot) hstrict.2

/-- A separated reverse comparison in an outward box soundly rejects the
negative-source stationary predicate. -/
theorem certified_false_negative
    {firstOuter middleOuter rightOuter : Interval}
    {firstExact middleExact rightExact : Interval}
    (hfirst : Encloses firstOuter firstExact)
    (hmiddle : Encloses middleOuter middleExact)
    (hright : Encloses rightOuter rightExact)
    (hfirstValid : firstExact.IsValid)
    (hmiddleValid : middleExact.IsValid)
    (hrightValid : rightExact.IsValid)
    (hrejected :
      middleOuter.hi ≤ firstOuter.lo ∨
        middleOuter.hi ≤ rightOuter.lo) :
    ¬ StrictStationary false firstExact middleExact rightExact := by
  simp only [StrictStationary, Bool.false_eq_true, ↓reduceIte]
  intro hstrict
  rcases hrejected with hleft | hrightRejected
  · have hnot :
        middleExact.lo ≤ firstExact.hi := by
      calc
        middleExact.lo ≤ middleExact.hi := hmiddleValid
        _ ≤ middleOuter.hi := hmiddle.2
        _ ≤ firstOuter.lo := hleft
        _ ≤ firstExact.lo := hfirst.1
        _ ≤ firstExact.hi := hfirstValid
    exact (not_lt_of_ge hnot) hstrict.1
  · have hnot :
        middleExact.lo ≤ rightExact.hi := by
      calc
        middleExact.lo ≤ middleExact.hi := hmiddleValid
        _ ≤ middleOuter.hi := hmiddle.2
        _ ≤ rightOuter.lo := hrightRejected
        _ ≤ rightExact.lo := hright.1
        _ ≤ rightExact.hi := hrightValid
    exact (not_lt_of_ge hnot) hstrict.2

/-- Exact equality with the middle interval is also an immediate sound
rejection, matching the optimized executable's common constant-run path. -/
theorem equal_middle_rejects
    {positive : Bool} {first middle right : Interval}
    (hmiddleValid : middle.IsValid)
    (hequal : first = middle ∨ right = middle) :
    ¬ StrictStationary positive first middle right := by
  cases positive <;>
    simp only [StrictStationary, ↓reduceIte]
  · intro hstrict
    rcases hequal with rfl | rfl
    · exact (not_lt_of_ge hmiddleValid) hstrict.1
    · exact (not_lt_of_ge hmiddleValid) hstrict.2
  · intro hstrict
    rcases hequal with rfl | rfl
    · exact (not_lt_of_ge hmiddleValid) hstrict.1
    · exact (not_lt_of_ge hmiddleValid) hstrict.2

#print axioms certified_true
#print axioms certified_positive
#print axioms certified_negative
#print axioms certified_false_positive
#print axioms certified_false_negative
#print axioms equal_middle_rejects

end SparkInterval.Zeta.PT21StationaryCandidateFilter
