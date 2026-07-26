/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Algebra.Order.Ring.Defs

/-!
# Sound precision-independent hulls for PT21 endpoint replay

Rigorous interval evaluations of the same expression at two Arb precisions
need not be nested.  The PT21 stationary resolver must therefore not assume
that a higher-precision enclosure is a subset of a lower-precision one.

This file records the small architecture-independent replacement used by the
qualification path: retain both enclosures and use their outward hull.  If
either evaluation contains the source value, the hull contains it; if both
do, the same conclusion follows without any nesting premise.  A strict sign
check on the widened hull is sufficient for the enclosed value's sign.

The theorem proves only interval algebra.  It does not assert that FLINT/Arb
evaluated the source expression or connect native endpoint bytes to these
ordered values.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.PT21PrecisionHull

/-- A closed ordered interval.  Construction does not silently assume that
the endpoints are ordered; consumers state that guard explicitly. -/
structure ClosedInterval (α : Type*) where
  lower : α
  upper : α
deriving DecidableEq, Repr

def ClosedInterval.Contains {α : Type*} [LE α]
    (interval : ClosedInterval α) (value : α) : Prop :=
  interval.lower ≤ value ∧ value ≤ interval.upper

/-- Smallest endpoint-wise interval containing both supplied intervals. -/
def hull {α : Type*} [LinearOrder α]
    (first second : ClosedInterval α) : ClosedInterval α where
  lower := min first.lower second.lower
  upper := max first.upper second.upper

theorem first_contains_hull {α : Type*} [LinearOrder α]
    (first second : ClosedInterval α) {value : α}
    (contains : first.Contains value) :
    (hull first second).Contains value := by
  constructor
  · exact le_trans (min_le_left _ _) contains.1
  · exact le_trans contains.2 (le_max_left _ _)

theorem second_contains_hull {α : Type*} [LinearOrder α]
    (first second : ClosedInterval α) {value : α}
    (contains : second.Contains value) :
    (hull first second).Contains value := by
  constructor
  · exact le_trans (min_le_right _ _) contains.1
  · exact le_trans contains.2 (le_max_right _ _)

/-- No cross-precision nesting assumption is needed: two independently
sound evaluations imply that their outward hull is sound. -/
theorem contains_hull_of_both {α : Type*} [LinearOrder α]
    (first second : ClosedInterval α) {value : α}
    (firstContains : first.Contains value)
    (_secondContains : second.Contains value) :
    (hull first second).Contains value :=
  first_contains_hull first second firstContains

/-- A replay enclosure contained in either retained precision is also
contained in the retained hull. -/
theorem replay_contains_hull_of_subset_second
    {α : Type*} [LinearOrder α]
    (first second replay : ClosedInterval α)
    (lowerBound : second.lower ≤ replay.lower)
    (upperBound : replay.upper ≤ second.upper) :
    (hull first second).lower ≤ replay.lower ∧
      replay.upper ≤ (hull first second).upper := by
  constructor
  · exact le_trans (min_le_right _ _) lowerBound
  · exact le_trans upperBound (le_max_right _ _)

def StrictlyPositive {α : Type*} [Zero α] [LT α]
    (interval : ClosedInterval α) : Prop :=
  0 < interval.lower

def StrictlyNegative {α : Type*} [Zero α] [LT α]
    (interval : ClosedInterval α) : Prop :=
  interval.upper < 0

theorem positive_of_hull_contains
    {α : Type*} [LinearOrder α] [Zero α]
    {first second : ClosedInterval α} {value : α}
    (contains : (hull first second).Contains value)
    (positive : StrictlyPositive (hull first second)) :
    0 < value :=
  lt_of_lt_of_le positive contains.1

theorem negative_of_hull_contains
    {α : Type*} [LinearOrder α] [Zero α]
    {first second : ClosedInterval α} {value : α}
    (contains : (hull first second).Contains value)
    (negative : StrictlyNegative (hull first second)) :
    value < 0 :=
  lt_of_le_of_lt contains.2 negative

#print axioms first_contains_hull
#print axioms second_contains_hull
#print axioms contains_hull_of_both
#print axioms replay_contains_hull_of_subset_second
#print axioms positive_of_hull_contains
#print axioms negative_of_hull_contains

end SparkInterval.Zeta.PT21PrecisionHull
