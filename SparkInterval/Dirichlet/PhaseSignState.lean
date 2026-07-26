/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib

/-!
# Associative boundary state for Dirichlet sign phases

The source-scale Dirichlet schedule is split into adjacent ordinate phases.
Each phase retains its first and last determinate sign and its internal
transition count.  Combining two phases adds one transition exactly when both
have a determinate endpoint and their boundary signs differ.

This file proves that operation associative, so the ten source phases may be
merged in any parenthesization while preserving their order.  It models the
small arithmetic core of the native compact-state merger.  Parsing, interval
classification, ambiguity ranges, multiplicity, Turing bounds, and physical
execution remain separate obligations.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.PhaseSignState

/-- One strict sign; `false` denotes negative and `true` positive. -/
abbrev StrictSign := Bool

def chooseFirst (left right : Option StrictSign) :
    Option StrictSign :=
  match left with
  | some value => some value
  | none => right

def chooseLast (left right : Option StrictSign) :
    Option StrictSign :=
  match right with
  | some value => some value
  | none => left

/-- The possible extra transition at an adjacent phase boundary. -/
def boundaryTransition
    (leftLast rightFirst : Option StrictSign) : Nat :=
  match leftLast, rightFirst with
  | some left, some right => if left = right then 0 else 1
  | _, _ => 0

/-- Compact arithmetic state retained for one ordered sign chunk. -/
structure State where
  sampleCount : Nat
  ambiguityCount : Nat
  firstDeterminate : Option StrictSign
  lastDeterminate : Option StrictSign
  transitionCount : Nat
  deriving Repr, DecidableEq

namespace State

def empty : State :=
  ⟨0, 0, none, none, 0⟩

/-- First and last are simultaneously present or absent. -/
def BoundaryValid (state : State) : Prop :=
  state.firstDeterminate.isSome =
    state.lastDeterminate.isSome

/-- Ordered concatenation of two adjacent phase states. -/
def combine (left right : State) : State where
  sampleCount := left.sampleCount + right.sampleCount
  ambiguityCount := left.ambiguityCount + right.ambiguityCount
  firstDeterminate :=
    chooseFirst left.firstDeterminate right.firstDeterminate
  lastDeterminate :=
    chooseLast left.lastDeterminate right.lastDeterminate
  transitionCount :=
    left.transitionCount + right.transitionCount +
      boundaryTransition left.lastDeterminate right.firstDeterminate

@[simp] theorem empty_combine (state : State) :
    combine empty state = state := by
  rcases state with
    ⟨samples, ambiguities, first, last, transitions⟩
  cases first <;> cases last <;>
    simp [combine, empty, chooseFirst, chooseLast,
      boundaryTransition]

@[simp] theorem combine_empty (state : State) :
    combine state empty = state := by
  rcases state with
    ⟨samples, ambiguities, first, last, transitions⟩
  cases first <;> cases last <;>
    simp [combine, empty, chooseFirst, chooseLast,
      boundaryTransition]

/-- Concatenation preserves simultaneous presence of the two boundary signs. -/
theorem combine_boundaryValid
    (left right : State)
    (hleft : left.BoundaryValid)
    (hright : right.BoundaryValid) :
    (combine left right).BoundaryValid := by
  rcases left with
    ⟨leftSamples, leftAmbiguities, leftFirst, leftLast,
      leftTransitions⟩
  rcases right with
    ⟨rightSamples, rightAmbiguities, rightFirst, rightLast,
      rightTransitions⟩
  cases leftFirst <;> cases leftLast <;>
    cases rightFirst <;> cases rightLast <;>
    simp [BoundaryValid] at hleft hright ⊢ <;>
    simp_all [combine, chooseFirst, chooseLast]

/-- Adjacent phase merging is associative for well-formed states.  The order
of the phases is not commuted. -/
theorem combine_assoc
    (first second third : State)
    (hfirst : first.BoundaryValid)
    (hsecond : second.BoundaryValid)
    (hthird : third.BoundaryValid) :
    combine (combine first second) third =
      combine first (combine second third) := by
  rcases first with
    ⟨firstSamples, firstAmbiguities, firstFirst, firstLast,
      firstTransitions⟩
  rcases second with
    ⟨secondSamples, secondAmbiguities, secondFirst, secondLast,
      secondTransitions⟩
  rcases third with
    ⟨thirdSamples, thirdAmbiguities, thirdFirst, thirdLast,
      thirdTransitions⟩
  cases firstFirst <;> cases firstLast <;>
    cases secondFirst <;> cases secondLast <;>
    cases thirdFirst <;> cases thirdLast <;>
    simp [BoundaryValid] at hfirst hsecond hthird <;>
    simp_all [combine, chooseFirst, chooseLast, boundaryTransition,
      Nat.add_assoc, Nat.add_left_comm, Nat.add_comm]

#print axioms empty_combine
#print axioms combine_empty
#print axioms combine_boundaryValid
#print axioms combine_assoc

end State

/-! ## Sparse ambiguity-run boundary state

The production reducer stores only maximal ambiguity ranges.  When adjacent
chunks both meet their common boundary ambiguously, their last and first
ranges are one maximal range and the combined count is reduced by one.
The state below isolates that arithmetic from concrete coordinates and wire
formats.
-/

namespace AmbiguityRunState

/-- Boundary information and maximal ambiguity-range count for one chunk.
`none` denotes an empty chunk; `some true` denotes an ambiguous endpoint.
The count is modeled in `Int` so associativity is an ordinary additive law;
`CountValid` below proves that realizable/native states stay nonnegative. -/
structure State where
  sampleCount : Nat
  firstAmbiguous : Option Bool
  lastAmbiguous : Option Bool
  rangeCount : Int
  deriving Repr, DecidableEq

def empty : State :=
  ⟨0, none, none, 0⟩

/-- Both endpoints are present exactly for a nonempty chunk, and every
ambiguous boundary belongs to at least one retained maximal range. -/
def Valid (state : State) : Prop :=
  (state.sampleCount = 0 ↔
      state.firstAmbiguous = none ∧ state.lastAmbiguous = none) ∧
    state.firstAmbiguous.isSome = state.lastAmbiguous.isSome ∧
    (state.firstAmbiguous = some true → 0 < state.rangeCount) ∧
    (state.lastAmbiguous = some true → 0 < state.rangeCount)

def CountValid (state : State) : Prop :=
  Valid state ∧ 0 ≤ state.rangeCount

/-- One range disappears precisely when two boundary ambiguity runs touch. -/
def boundaryCoalescence
    (leftLast rightFirst : Option Bool) : Int :=
  if leftLast = some true ∧ rightFirst = some true then 1 else 0

def combine (left right : State) : State where
  sampleCount := left.sampleCount + right.sampleCount
  firstAmbiguous :=
    chooseFirst left.firstAmbiguous right.firstAmbiguous
  lastAmbiguous :=
    chooseLast left.lastAmbiguous right.lastAmbiguous
  rangeCount :=
    left.rangeCount + right.rangeCount -
      boundaryCoalescence left.lastAmbiguous right.firstAmbiguous

@[simp] theorem empty_combine (state : State) :
    combine empty state = state := by
  rcases state with ⟨samples, first, last, ranges⟩
  cases first <;> cases last <;>
    simp [combine, empty, chooseFirst, chooseLast,
      boundaryCoalescence]

@[simp] theorem combine_empty (state : State) :
    combine state empty = state := by
  rcases state with ⟨samples, first, last, ranges⟩
  cases first <;> cases last <;>
    simp [combine, empty, chooseFirst, chooseLast,
      boundaryCoalescence]

/-- A merge of two realizable nonnegative counts remains realizable and
nonnegative; the only subtraction is justified by an actual boundary range
on both sides. -/
theorem combine_countValid
    (left right : State)
    (hleft : CountValid left)
    (hright : CountValid right) :
    CountValid (combine left right) := by
  rcases left with
    ⟨leftSamples, leftFirst, leftLast, leftRanges⟩
  rcases right with
    ⟨rightSamples, rightFirst, rightLast, rightRanges⟩
  cases leftFirst <;> cases leftLast <;>
    cases rightFirst <;> cases rightLast <;>
    simp [CountValid, Valid] at hleft hright ⊢ <;>
    simp_all [combine, chooseFirst, chooseLast,
      boundaryCoalescence] <;>
    grind

/-- Ordered maximal-range merging is associative.  The positivity clauses in
`Valid` rule out saturating subtraction at a touching boundary. -/
theorem combine_assoc
    (first second third : State)
    (hfirst : Valid first)
    (hsecond : Valid second)
    (hthird : Valid third) :
    combine (combine first second) third =
      combine first (combine second third) := by
  rcases first with
    ⟨firstSamples, firstFirst, firstLast, firstRanges⟩
  rcases second with
    ⟨secondSamples, secondFirst, secondLast, secondRanges⟩
  rcases third with
    ⟨thirdSamples, thirdFirst, thirdLast, thirdRanges⟩
  cases firstFirst <;> cases firstLast <;>
    cases secondFirst <;> cases secondLast <;>
    cases thirdFirst <;> cases thirdLast <;>
    simp [Valid] at hfirst hsecond hthird <;>
    simp_all [combine, chooseFirst, chooseLast,
      boundaryCoalescence, Nat.add_left_comm, Nat.add_comm] <;>
    ring

#print axioms empty_combine
#print axioms combine_empty
#print axioms combine_countValid
#print axioms combine_assoc

end AmbiguityRunState

end SparkInterval.Dirichlet.PhaseSignState
