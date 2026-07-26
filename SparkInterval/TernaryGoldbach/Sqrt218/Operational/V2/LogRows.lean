/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.Operational.LogLadderRows
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.PrimeRoster

/-!
# Linear V2 logarithm-row certificate

The V2 native record keeps one fixed-point log box beside each prime row.
This checker validates the thirty small seeds once, then advances the proved
integer recurrence across successive prime gaps.  Its arithmetic work is
linear in the largest prime, not one transcendental evaluation per row.

The module is data-independent.  Compiling its proof never evaluates the
production ladder.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational.V2

open TGComputeContracts.Sqrt218
open SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate

namespace LogRows

abbrev LadderState :=
  SparkInterval.TernaryGoldbach.Sqrt218Operational.LogLadderRows.State

def initial : LadderState :=
  SparkInterval.TernaryGoldbach.Sqrt218Operational.LogLadderRows.initial

def advanceTo (state : LadderState) (target : Nat) : LadderState :=
  SparkInterval.TernaryGoldbach.Sqrt218Operational.LogLadderRows.advanceTo
    state target

/-- One V2 row.  Retaining `prime` makes alignment with the prime-roster
section an explicit checked condition rather than a convention of offsets. -/
structure Row where
  prime : Nat
  lower : Nat
  upper : Nat
  deriving Repr, DecidableEq, Inhabited

def Row.bounds (row : Row) : LogBounds :=
  ⟨row.lower, row.upper⟩

structure Certificate where
  rows : List Row
  deriving Repr, DecidableEq, Inhabited

namespace Certificate

def count (certificate : Certificate) : Nat :=
  certificate.rows.length

def rowAt (certificate : Certificate) (index : Nat) : Row :=
  certificate.rows.getD index default

def logLowerAt (certificate : Certificate) (index : Nat) : Nat :=
  (certificate.rowAt index).lower

def logUpperAt (certificate : Certificate) (index : Nat) : Nat :=
  (certificate.rowAt index).upper

end Certificate

/-- Advance once through the ordered row list. -/
def checkRows : LadderState → List Row → Bool
  | _, [] => true
  | state, row :: rest =>
      if state.position < row.prime then
        let nextState := advanceTo state row.prime
        decide (row.bounds = nextState.bounds) &&
          checkRows nextState rest
      else
        false

private theorem checkRows_sound
    (seeds : SeedCertificate)
    {state : LadderState} {rows : List Row}
    (hposition : 1 ≤ state.position)
    (hvalid : state.bounds.Valid state.position)
    (hcheck : checkRows state rows = true) :
    ∀ row, row ∈ rows → row.bounds.Valid row.prime := by
  induction rows generalizing state with
  | nil =>
      simp
  | cons first rest inductionHypothesis =>
      have hlt : state.position < first.prime := by
        by_contra hnot
        simp [checkRows, hnot] at hcheck
      simp only [checkRows, if_pos hlt, Bool.and_eq_true,
        decide_eq_true_eq] at hcheck
      let nextState := advanceTo state first.prime
      have hnextValid : nextState.bounds.Valid nextState.position := by
        have hadvance :=
          SparkInterval.TernaryGoldbach.Sqrt218Operational.LogLadderRows.advance_valid
            seeds hposition hvalid
            (count := first.prime - state.position)
        have hle : state.position ≤ first.prime := hlt.le
        simpa [nextState, advanceTo,
          SparkInterval.TernaryGoldbach.Sqrt218Operational.LogLadderRows.advanceTo,
          Nat.add_sub_of_le hle] using hadvance
      intro row hmem
      rcases List.mem_cons.mp hmem with hfirst | hrest
      · subst row
        rw [hcheck.1]
        exact hnextValid
      · exact
          inductionHypothesis (state := nextState)
            (by
              simp [nextState, advanceTo,
                SparkInterval.TernaryGoldbach.Sqrt218Operational.LogLadderRows.advanceTo]
              omega)
            hnextValid hcheck.2 row hrest

def alignmentCellCheck
    (primeAt : Nat → Nat) (certificate : Certificate) (index : Nat) : Bool :=
  decide ((certificate.rowAt index).prime = primeAt index)

/-- Exact V2 log check: fixed seeds once, exact row count and prime alignment,
then one sequential ladder. -/
def check
    (primeCount : Nat) (primeAt : Nat → Nat)
    (certificate : Certificate) : Bool :=
  SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate.seedTableCheck &&
    (decide (certificate.count = primeCount) &&
      (checkRange 0 primeCount
          (alignmentCellCheck primeAt certificate) &&
        checkRows initial certificate.rows))

/-- A successful V2 log pass supplies the directed real logarithm facts used
by the generic certificate contract. -/
theorem check_sound
    {bound primeCount : Nat} {primeAt : Nat → Nat}
    {certificate : Certificate}
    (_hroster : PrimeRosterFacts bound primeCount primeAt)
    (hcheck : check primeCount primeAt certificate = true) :
    PrimeLogFacts primeCount primeAt
      certificate.logLowerAt certificate.logUpperAt := by
  simp only [check, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  have seeds :=
    SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate.seedTableCheck_sound
      hcheck.1
  have hinitial : initial.bounds.Valid initial.position := by
    simpa [initial,
      SparkInterval.TernaryGoldbach.Sqrt218Operational.LogLadderRows.initial]
      using seeds.seed_valid (n := 1) (by norm_num)
        (by norm_num [seedAt])
  have hrows :=
    checkRows_sound seeds (state := initial)
      (by
        simp [initial,
          SparkInterval.TernaryGoldbach.Sqrt218Operational.LogLadderRows.initial])
      hinitial hcheck.2.2.2
  have halignment :
      ∀ index, index < primeCount →
        (certificate.rowAt index).prime = primeAt index := by
    intro index hindex
    have hcell :=
      checkRange_sound hcheck.2.2.1 index
        (by omega) (by simpa using hindex)
    simpa [alignmentCellCheck, decide_eq_true_eq] using hcell
  constructor
  · intro index hindex
    have hrowsLength : certificate.rows.length = primeCount := by
      simpa [Certificate.count] using hcheck.2.1
    have hindexRows : index < certificate.rows.length := by
      simpa [hrowsLength] using hindex
    have hrowEq :
        certificate.rows.getD index default = certificate.rows[index] :=
      List.getD_eq_getElem _ _ hindexRows
    have hvalid :=
      hrows certificate.rows[index] (List.getElem_mem hindexRows)
    have halignGet :
        certificate.rows[index].prime = primeAt index := by
      have halign := halignment index hindex
      change
        (certificate.rows.getD index default).prime = primeAt index
        at halign
      rw [hrowEq] at halign
      exact halign
    change
      ((certificate.rows.getD index default).lower : Real) ≤
        scale * Real.log (primeAt index)
    rw [hrowEq]
    rw [← halignGet]
    simpa [Row.bounds] using hvalid.1
  · intro index hindex
    have hrowsLength : certificate.rows.length = primeCount := by
      simpa [Certificate.count] using hcheck.2.1
    have hindexRows : index < certificate.rows.length := by
      simpa [hrowsLength] using hindex
    have hrowEq :
        certificate.rows.getD index default = certificate.rows[index] :=
      List.getD_eq_getElem _ _ hindexRows
    have hvalid :=
      hrows certificate.rows[index] (List.getElem_mem hindexRows)
    have halignGet :
        certificate.rows[index].prime = primeAt index := by
      have halign := halignment index hindex
      change
        (certificate.rows.getD index default).prime = primeAt index
        at halign
      rw [hrowEq] at halign
      exact halign
    change
      scale * Real.log (primeAt index) ≤
        ((certificate.rows.getD index default).upper : Real)
    rw [hrowEq]
    rw [← halignGet]
    simpa [Row.bounds] using hvalid.2

end LogRows

end SparkInterval.TernaryGoldbach.Sqrt218Operational.V2

end
