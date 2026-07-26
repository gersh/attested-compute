/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.PhaseSignState

/-!
# Exact list semantics for compact Dirichlet sign states

`PhaseSignState` proves that the compact phase merge is associative.  This
module connects that algebraic operation to an ordinary list of strict-sign
decisions:

* `none` is one ambiguous sample;
* `some false` and `some true` are determinate negative and positive samples;
* transitions are counted after ambiguous samples are removed.

Thus an ordered tree reduction of phase states has exactly the same dense
summary as a sequential scan of the underlying decisions.  The result is
architecture-independent: it does not claim that a particular CUDA kernel
or packed wire implements these definitions.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.PhaseSignFold

open PhaseSignState

/-- The compact state of one three-way sign decision. -/
def singleton : Option StrictSign → State
  | none =>
      { sampleCount := 1
        ambiguityCount := 1
        firstDeterminate := none
        lastDeterminate := none
        transitionCount := 0 }
  | some sign =>
      { sampleCount := 1
        ambiguityCount := 0
        firstDeterminate := some sign
        lastDeterminate := some sign
        transitionCount := 0 }

/-- Sequential reference scan, expressed using the same ordered merge that
is used by a reduction tree. -/
def summarize : List (Option StrictSign) → State
  | [] => State.empty
  | decision :: decisions =>
      State.combine (singleton decision) (summarize decisions)

/-- Remove ambiguous samples from a three-way sign sequence. -/
def determinateSigns (decisions : List (Option StrictSign)) :
    List StrictSign :=
  decisions.filterMap id

/-- Number of changes in an ordinary list of determinate signs. -/
def strictTransitionCount : List StrictSign → Nat
  | [] => 0
  | [_] => 0
  | first :: second :: rest =>
      (if first = second then 0 else 1) +
        strictTransitionCount (second :: rest)

/-- First determinate decision in source order. -/
def firstDeterminate : List (Option StrictSign) → Option StrictSign
  | [] => none
  | none :: decisions => firstDeterminate decisions
  | some sign :: _ => some sign

/-- Last determinate decision in source order. -/
def lastDeterminate : List (Option StrictSign) → Option StrictSign
  | [] => none
  | decision :: decisions =>
      PhaseSignState.chooseLast decision (lastDeterminate decisions)

/-- Direct transition scan on three-way decisions.  An ambiguous sample is
discarded; a determinate sample is compared with the next determinate sample
in source order. -/
def decisionTransitionCount :
    List (Option StrictSign) → Nat
  | [] => 0
  | none :: decisions => decisionTransitionCount decisions
  | some sign :: decisions =>
      decisionTransitionCount decisions +
        PhaseSignState.boundaryTransition
          (some sign) (firstDeterminate decisions)

@[simp] theorem firstDeterminate_eq_head
    (decisions : List (Option StrictSign)) :
    firstDeterminate decisions =
      (determinateSigns decisions).head? := by
  induction decisions with
  | nil =>
      rfl
  | cons decision decisions induction =>
      cases decision <;>
        simp [firstDeterminate, determinateSigns, induction]

@[simp] theorem lastDeterminate_eq_getLast
    (decisions : List (Option StrictSign)) :
    lastDeterminate decisions =
      (determinateSigns decisions).getLast? := by
  induction decisions with
  | nil =>
      rfl
  | cons decision decisions induction =>
      cases decision with
      | none =>
          change
            PhaseSignState.chooseLast none
                (lastDeterminate decisions) =
              (determinateSigns decisions).getLast?
          rw [induction]
          cases (determinateSigns decisions).getLast? <;>
            rfl
      | some sign =>
          change
            PhaseSignState.chooseLast (some sign)
                (lastDeterminate decisions) =
              (sign :: determinateSigns decisions).getLast?
          rw [induction, List.getLast?_cons]
          cases hlast : (determinateSigns decisions).getLast? <;>
            simp [PhaseSignState.chooseLast]

/-- The direct three-way scan counts exactly the changes in the list obtained
after deleting all ambiguous samples. -/
theorem decisionTransitionCount_eq_filtered
    (decisions : List (Option StrictSign)) :
    decisionTransitionCount decisions =
      strictTransitionCount (determinateSigns decisions) := by
  induction decisions with
  | nil =>
      rfl
  | cons decision decisions induction =>
      cases decision with
      | none =>
          simpa [decisionTransitionCount, determinateSigns] using induction
      | some sign =>
          rw [decisionTransitionCount, induction,
            firstDeterminate_eq_head]
          change
            strictTransitionCount (determinateSigns decisions) +
                PhaseSignState.boundaryTransition
                  (some sign) (determinateSigns decisions).head? =
              strictTransitionCount
                (sign :: determinateSigns decisions)
          cases hsigns : determinateSigns decisions with
          | nil =>
              simp [strictTransitionCount,
                PhaseSignState.boundaryTransition]
          | cons next rest =>
              simp [strictTransitionCount,
                PhaseSignState.boundaryTransition, Nat.add_comm]

/-- A direct, implementation-independent specification of the dense state. -/
def reference (decisions : List (Option StrictSign)) : State :=
  { sampleCount := decisions.length
    ambiguityCount := decisions.countP Option.isNone
    firstDeterminate := firstDeterminate decisions
    lastDeterminate := lastDeterminate decisions
    transitionCount := decisionTransitionCount decisions }

@[simp] theorem singleton_boundaryValid
    (decision : Option StrictSign) :
    (singleton decision).BoundaryValid := by
  cases decision <;> simp [singleton, State.BoundaryValid]

@[simp] theorem summarize_boundaryValid
    (decisions : List (Option StrictSign)) :
    (summarize decisions).BoundaryValid := by
  induction decisions with
  | nil =>
      simp [summarize, State.empty, State.BoundaryValid]
  | cons decision decisions induction =>
      exact State.combine_boundaryValid _ _
        (singleton_boundaryValid decision) induction

/-- Reducing two adjacent sign lists and then combining their states is
exactly the same as scanning their concatenation. -/
theorem summarize_append
    (left right : List (Option StrictSign)) :
    summarize (left ++ right) =
      State.combine (summarize left) (summarize right) := by
  induction left with
  | nil =>
      simp [summarize]
  | cons decision decisions induction =>
      simp only [List.cons_append, summarize, induction]
      exact (State.combine_assoc
        (singleton decision) (summarize decisions) (summarize right)
        (singleton_boundaryValid decision)
        (summarize_boundaryValid decisions)
        (summarize_boundaryValid right)).symm

/-- The reduction-tree state is the direct list specification: samples and
ambiguities are counted, boundary signs are the first and last determinate
samples, and transitions are changes in the ambiguity-filtered sign list. -/
theorem summarize_eq_reference
    (decisions : List (Option StrictSign)) :
    summarize decisions = reference decisions := by
  induction decisions with
  | nil =>
      rfl
  | cons decision decisions induction =>
      rw [summarize, induction]
      cases decision with
      | none =>
          simp [reference, singleton, State.combine,
            PhaseSignState.chooseFirst, PhaseSignState.chooseLast,
            PhaseSignState.boundaryTransition, firstDeterminate,
            lastDeterminate, decisionTransitionCount, Nat.add_comm]
      | some sign =>
          simp [reference, singleton, State.combine,
            PhaseSignState.chooseFirst, PhaseSignState.chooseLast,
            firstDeterminate, lastDeterminate,
            decisionTransitionCount, Nat.add_comm]

#print axioms singleton_boundaryValid
#print axioms firstDeterminate_eq_head
#print axioms lastDeterminate_eq_getLast
#print axioms decisionTransitionCount_eq_filtered
#print axioms summarize_boundaryValid
#print axioms summarize_append
#print axioms summarize_eq_reference

/-! ## Exact list fold for maximal ambiguity runs -/

namespace Ambiguity

open PhaseSignState.AmbiguityRunState

/-- One concrete ambiguity decision. -/
def singleton (ambiguous : Bool) :
    AmbiguityRunState.State :=
  { sampleCount := 1
    firstAmbiguous := some ambiguous
    lastAmbiguous := some ambiguous
    rangeCount := if ambiguous then 1 else 0 }

/-- Sequential maximal-run summary of a concrete ambiguity sequence. -/
def summarize : List Bool → AmbiguityRunState.State
  | [] => AmbiguityRunState.empty
  | ambiguous :: ambiguities =>
      AmbiguityRunState.combine
        (singleton ambiguous) (summarize ambiguities)

/-- Direct maximal-run count.  Every ambiguous singleton contributes one
range and exactly one is removed when it touches an ambiguous first sample
of the suffix. -/
def maximalRangeCount : List Bool → Nat
  | [] => 0
  | ambiguous :: ambiguities =>
      (if ambiguous then 1 else 0) +
          maximalRangeCount ambiguities -
        (if ambiguous = true ∧ ambiguities.head? = some true
          then 1 else 0)

@[simp] theorem summarize_sampleCount (ambiguities : List Bool) :
    (summarize ambiguities).sampleCount = ambiguities.length := by
  induction ambiguities with
  | nil =>
      rfl
  | cons ambiguous ambiguities induction =>
      simp [summarize, AmbiguityRunState.combine, singleton, induction,
        Nat.add_comm]

@[simp] theorem summarize_firstAmbiguous (ambiguities : List Bool) :
    (summarize ambiguities).firstAmbiguous = ambiguities.head? := by
  cases ambiguities <;>
    simp [summarize, AmbiguityRunState.empty,
      AmbiguityRunState.combine, singleton,
      PhaseSignState.chooseFirst]

@[simp] theorem summarize_lastAmbiguous (ambiguities : List Bool) :
    (summarize ambiguities).lastAmbiguous = ambiguities.getLast? := by
  induction ambiguities with
  | nil =>
      rfl
  | cons ambiguous ambiguities induction =>
      simp only [summarize, AmbiguityRunState.combine, singleton]
      rw [induction, List.getLast?_cons]
      cases hlast : ambiguities.getLast? <;>
        simp [PhaseSignState.chooseLast]

/-- The signed counter used to make merge associativity algebraically simple
is exactly the natural number of maximal ambiguity runs on every realizable
decision list. -/
theorem summarize_rangeCount_eq_maximal
    (ambiguities : List Bool) :
    (summarize ambiguities).rangeCount =
      (maximalRangeCount ambiguities : Int) := by
  induction ambiguities with
  | nil =>
      rfl
  | cons ambiguous ambiguities induction =>
      rw [summarize]
      simp only [AmbiguityRunState.combine, singleton]
      rw [induction, summarize_firstAmbiguous]
      cases ambiguous <;>
        cases ambiguities with
        | nil =>
            simp [maximalRangeCount,
              AmbiguityRunState.boundaryCoalescence]
        | cons first rest =>
            cases first <;>
              simp [maximalRangeCount,
                AmbiguityRunState.boundaryCoalescence]

@[simp] theorem singleton_countValid (ambiguous : Bool) :
    AmbiguityRunState.CountValid (singleton ambiguous) := by
  cases ambiguous <;>
    simp [singleton, AmbiguityRunState.CountValid,
      AmbiguityRunState.Valid]

@[simp] theorem summarize_countValid (ambiguities : List Bool) :
    AmbiguityRunState.CountValid (summarize ambiguities) := by
  induction ambiguities with
  | nil =>
      simp [summarize, AmbiguityRunState.empty,
        AmbiguityRunState.CountValid, AmbiguityRunState.Valid]
  | cons ambiguous ambiguities induction =>
      exact AmbiguityRunState.combine_countValid _ _
        (singleton_countValid ambiguous) induction

/-- Any ordered reduction tree counts the same maximal ambiguity runs as a
sequential scan of the concatenated decisions. -/
theorem summarize_append (left right : List Bool) :
    summarize (left ++ right) =
      AmbiguityRunState.combine
        (summarize left) (summarize right) := by
  induction left with
  | nil =>
      simp [summarize]
  | cons ambiguous ambiguities induction =>
      simp only [List.cons_append, summarize, induction]
      exact (AmbiguityRunState.combine_assoc
        (singleton ambiguous) (summarize ambiguities) (summarize right)
        (singleton_countValid ambiguous).1
        (summarize_countValid ambiguities).1
        (summarize_countValid right).1).symm

/-- A realizable folded ambiguity-range count cannot underflow. -/
theorem summarize_rangeCount_nonnegative
    (ambiguities : List Bool) :
    0 ≤ (summarize ambiguities).rangeCount :=
  (summarize_countValid ambiguities).2

#print axioms singleton_countValid
#print axioms summarize_sampleCount
#print axioms summarize_firstAmbiguous
#print axioms summarize_lastAmbiguous
#print axioms summarize_rangeCount_eq_maximal
#print axioms summarize_countValid
#print axioms summarize_append
#print axioms summarize_rangeCount_nonnegative

end Ambiguity

end SparkInterval.Dirichlet.PhaseSignFold
