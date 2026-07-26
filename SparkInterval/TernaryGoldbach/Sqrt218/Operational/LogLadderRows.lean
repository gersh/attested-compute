/-
Copyright (c) 2026 Gershon Bialer. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: Gershon Bialer
-/
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.Archive
import SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate

/-!
# Single-pass logarithm-row checker for Sqrt218

This checker advances the exact Python scale-`2^48` ladder once across the
gaps between consecutive archive primes.  It checks the thirty fixed seeds
once and uses only integer recurrence steps thereafter.  Thus a production
implementation is linear in the largest prime, rather than running a
transcendental enclosure independently for every prime row.

The theorem is generic and evaluates no production archive.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational

namespace LogLadderRows

open TGComputeContracts.Sqrt218
open SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate

def rowLogBounds (row : PrimeRow) : LogBounds :=
  ⟨row.logLower, row.logUpper⟩

def archivePrimeCount (archive : Archive) : Nat :=
  archive.primes.length

def archivePrimeAt (archive : Archive) (index : Nat) : Nat :=
  (archive.primes.getD index default).prime

def archiveLogLowerAt (archive : Archive) (index : Nat) : Nat :=
  (archive.primes.getD index default).logLower

def archiveLogUpperAt (archive : Archive) (index : Nat) : Nat :=
  (archive.primes.getD index default).logUpper

/-- One Python-compatible ladder step.  Before 30 it selects the next fixed
seed; from 30 onward it uses the proved integer recurrence. -/
def next (position : Nat) (bounds : LogBounds) : LogBounds :=
  if position < seedAt then
    seed (position + 1)
  else
    bounds.next position

theorem next_valid
    (seeds : SeedCertificate)
    {position : Nat} {bounds : LogBounds}
    (hposition : 1 ≤ position) (hvalid : bounds.Valid position) :
    (next position bounds).Valid (position + 1) := by
  by_cases hseed : position < seedAt
  · simp only [next, if_pos hseed]
    exact seeds.seed_valid (by omega) (by omega)
  · simp only [next, if_neg hseed]
    exact hvalid.next (by
      norm_num [seedAt] at hseed
      omega)

/-- Advance a state through `count` consecutive natural numbers. -/
def advance : Nat → Nat → LogBounds → LogBounds
  | 0, _, bounds => bounds
  | count + 1, position, bounds =>
      advance count (position + 1) (next position bounds)

theorem advance_valid
    (seeds : SeedCertificate)
    {count position : Nat} {bounds : LogBounds}
    (hposition : 1 ≤ position) (hvalid : bounds.Valid position) :
    (advance count position bounds).Valid (position + count) := by
  induction count generalizing position bounds with
  | zero =>
      simpa [advance] using hvalid
  | succ count inductionHypothesis =>
      rw [advance]
      have hnext := next_valid seeds hposition hvalid
      have hresult :=
        inductionHypothesis (position := position + 1)
          (bounds := next position bounds) (by omega) hnext
      simpa [Nat.add_assoc, Nat.add_comm 1 count] using hresult

structure State where
  position : Nat
  bounds : LogBounds
  deriving Repr, DecidableEq

def initial : State := ⟨1, seed 1⟩

def advanceTo (state : State) (target : Nat) : State := {
  position := target
  bounds := advance (target - state.position) state.position state.bounds
}

/-- Check archive rows in their existing order, advancing the ladder across
each gap exactly once. -/
def checkRows : State → List PrimeRow → Bool
  | _, [] => true
  | state, row :: rest =>
      if state.position < row.prime then
        let nextState := advanceTo state row.prime
        decide (rowLogBounds row = nextState.bounds) &&
          checkRows nextState rest
      else
        false

private theorem checkRows_sound
    (seeds : SeedCertificate)
    {state : State} {rows : List PrimeRow}
    (hposition : 1 ≤ state.position)
    (hvalid : state.bounds.Valid state.position)
    (hcheck : checkRows state rows = true) :
    ∀ row, row ∈ rows → (rowLogBounds row).Valid row.prime := by
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
          advance_valid seeds hposition hvalid
            (count := first.prime - state.position)
        have hle : state.position ≤ first.prime := hlt.le
        simpa [nextState, advanceTo, Nat.add_sub_of_le hle] using
          hadvance
      intro row hmem
      rcases List.mem_cons.mp hmem with hfirst | hrest
      · subst row
        rw [hcheck.1]
        exact hnextValid
      · exact
          inductionHypothesis (state := nextState)
            (by
              simp [nextState, advanceTo]
              omega)
            hnextValid hcheck.2 row hrest

/-- Exact executable row check: validate the fixed seed table once, then
stream through all prime rows. -/
def check (archive : Archive) : Bool :=
  SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate.seedTableCheck &&
    checkRows initial archive.primes

/-- Successful single-pass ladder checking supplies all directed prime-log
facts required by the generic certificate. -/
theorem check_sound {archive : Archive}
    (hcheck : check archive = true) :
    PrimeLogFacts (archivePrimeCount archive) (archivePrimeAt archive)
      (archiveLogLowerAt archive) (archiveLogUpperAt archive) := by
  simp only [check, Bool.and_eq_true] at hcheck
  have seeds :=
    SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate.seedTableCheck_sound
      hcheck.1
  have hinitial : (initial.bounds).Valid initial.position := by
    simpa [initial] using
      seeds.seed_valid (n := 1) (by norm_num) (by norm_num [seedAt])
  have hrows :=
    checkRows_sound seeds (state := initial)
      (by norm_num [initial]) hinitial hcheck.2
  constructor
  · intro i hi
    have hi' : i < archive.primes.length := by
      simpa [archivePrimeCount] using hi
    have hrow :
        archive.primes.getD i default = archive.primes[i] :=
      List.getD_eq_getElem _ _ hi'
    have hget :=
      hrows archive.primes[i] (List.getElem_mem hi')
    change
      ((archive.primes.getD i default).logLower : Real) ≤
        scale * Real.log (archive.primes.getD i default).prime
    rw [hrow]
    exact hget.1
  · intro i hi
    have hi' : i < archive.primes.length := by
      simpa [archivePrimeCount] using hi
    have hrow :
        archive.primes.getD i default = archive.primes[i] :=
      List.getD_eq_getElem _ _ hi'
    have hget :=
      hrows archive.primes[i] (List.getElem_mem hi')
    change
      scale * Real.log (archive.primes.getD i default).prime ≤
        ((archive.primes.getD i default).logUpper : Real)
    rw [hrow]
    exact hget.2

end LogLadderRows

end SparkInterval.TernaryGoldbach.Sqrt218Operational

end
