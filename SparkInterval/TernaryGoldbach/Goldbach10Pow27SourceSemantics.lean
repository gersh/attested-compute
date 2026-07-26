/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachSourceSemantics

/-!
# Exact finite Goldbach semantics below the `10^27` analytic crossover

This is a distinct finite campaign, not a weakening or relabeling of the
historical Helfgott--Platt source computation.  Its two premises are:

1. binary Goldbach on every even integer in
   `[4, 31_250_000_000_000_000]`; and
2. a checked prime ladder scheduled for 7,106 ranges of width
   `2^47 * 10^9`, whose endpoint lies just above `10^27`.

Ordinary Lean proves that those premises imply the three-prime claim for every
odd target through `10^27`.  This file does not assert that either finite
premise has been run; no receipt is embedded here.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Goldbach10Pow27SourceSemantics

/-- Binary-Goldbach endpoint and maximum prime-ladder gap. -/
def binaryLimit : Nat := 31_250_000_000_000_000

/-- Inclusive endpoint handed to the analytic half of the proof. -/
def sourceLimit : Nat := 10 ^ 27

/-- Formulaic endpoint of the 7,106-range ladder schedule. -/
def scheduledEndpoint : Nat :=
  1_000_080_592_252_960_768_000_000_000

theorem scheduledEndpoint_eq_range_product :
    scheduledEndpoint = 7_106 * (2 ^ 47 * 10 ^ 9) := by
  norm_num [scheduledEndpoint]

theorem sourceLimit_le_scheduledEndpoint : sourceLimit ≤ scheduledEndpoint := by
  norm_num [sourceLimit, scheduledEndpoint]

abbrev IsThreePrimeSum := GoldbachSourceSemantics.IsThreePrimeSum

/-- Exact lowered binary prerequisite. -/
def BinaryGoldbachClaim : Prop :=
  ∀ e : Nat, Even e → 4 ≤ e → e ≤ binaryLimit →
    ∃ q r : Nat, q.Prime ∧ r.Prime ∧ q + r = e

structure PrimeLadder where
  rungs : List Nat

namespace PrimeLadder

def AdjacentCovered : List Nat → Prop
  | [] => True
  | [_p] => True
  | p :: q :: rest =>
      q + 4 ≤ p + binaryLimit + 2 ∧ AdjacentCovered (q :: rest)

instance instDecidableAdjacentCovered (rungs : List Nat) :
    Decidable (AdjacentCovered rungs) := by
  induction rungs with
  | nil =>
      change Decidable True
      exact inferInstance
  | cons p rest =>
      cases rest with
      | nil =>
          change Decidable True
          exact inferInstance
      | cons q tail =>
          simp only [AdjacentCovered]
          infer_instance

/-- Small certificate proposition checked directly from the retained ladder.
The last-rung guard deliberately covers the formulaic scheduled endpoint,
which is slightly stronger than covering `sourceLimit`. -/
def ArithmeticValid (ladder : PrimeLadder) : Prop :=
  ladder.rungs.head? = some 3 ∧
    (∀ p, p ∈ ladder.rungs → p.Prime ∧ 2 < p) ∧
    AdjacentCovered ladder.rungs ∧
    ∃ last, ladder.rungs.getLast? = some last ∧
      scheduledEndpoint ≤ last + binaryLimit

instance instDecidableArithmeticValid (ladder : PrimeLadder) :
    Decidable ladder.ArithmeticValid := by
  unfold ArithmeticValid
  infer_instance

def check (ladder : PrimeLadder) : Bool := decide ladder.ArithmeticValid

theorem check_sound {ladder : PrimeLadder}
    (hcheck : ladder.check = true) : ladder.ArithmeticValid :=
  of_decide_eq_true hcheck

def Valid (ladder : PrimeLadder) : Prop :=
  (∀ p, p ∈ ladder.rungs → p.Prime ∧ 2 < p) ∧
    ∀ n : Nat, Odd n → 7 ≤ n → n ≤ sourceLimit →
      ∃ p, p ∈ ladder.rungs ∧ p + 4 ≤ n ∧ n ≤ p + binaryLimit

private theorem cover_from_chain
    (p : Nat) (rest : List Nat) (n : Nat)
    (hallOdd : ∀ r, r ∈ p :: rest → Odd r)
    (hadjacent : AdjacentCovered (p :: rest))
    (hlast : ∃ last, (p :: rest).getLast? = some last ∧
      n ≤ last + binaryLimit)
    (hnOdd : Odd n) (hstart : p + 4 ≤ n) :
    ∃ r, r ∈ p :: rest ∧ r + 4 ≤ n ∧ n ≤ r + binaryLimit := by
  induction rest generalizing p with
  | nil =>
      obtain ⟨last, hlastValue, hnLast⟩ := hlast
      have hlastEq : last = p := by simpa using hlastValue.symm
      subst last
      exact ⟨p, by simp, hstart, hnLast⟩
  | cons q tail ih =>
      by_cases hpCovers : n ≤ p + binaryLimit
      · exact ⟨p, by simp, hstart, hpCovers⟩
      · have hadjacent' :
            q + 4 ≤ p + binaryLimit + 2 ∧ AdjacentCovered (q :: tail) := by
          simpa [AdjacentCovered] using hadjacent
        have hpOdd : Odd p := hallOdd p (by simp)
        have hlimitEven : Even binaryLimit := by
          norm_num [binaryLimit]
        have hnextOdd : p + binaryLimit + 2 ≤ n := by
          rcases hpOdd with ⟨a, ha⟩
          rcases hnOdd with ⟨b, hb⟩
          rcases hlimitEven with ⟨c, hc⟩
          omega
        have hcovered :
            ∃ r, r ∈ q :: tail ∧ r + 4 ≤ n ∧ n ≤ r + binaryLimit :=
          ih q (fun r hr => hallOdd r (by simp [hr])) hadjacent'.2
            (by simpa using hlast) (hadjacent'.1.trans hnextOdd)
        obtain ⟨r, hr, hrStart, hrEnd⟩ := hcovered
        exact ⟨r, List.mem_cons_of_mem p hr, hrStart, hrEnd⟩

theorem valid_of_arithmeticValid {ladder : PrimeLadder}
    (harithmetic : ladder.ArithmeticValid) : ladder.Valid := by
  refine ⟨harithmetic.2.1, ?_⟩
  intro n hnOdd hnLower hnUpper
  cases hrungs : ladder.rungs with
  | nil =>
      exfalso
      simpa [hrungs] using harithmetic.1
  | cons p rest =>
      have hp : p = 3 := by
        have := harithmetic.1
        simpa [hrungs] using this
      subst p
      have hallOdd : ∀ r, r ∈ 3 :: rest → Odd r := by
        intro r hr
        have hprime := harithmetic.2.1 r (by simpa [hrungs] using hr)
        exact hprime.1.odd_of_ne_two (by omega)
      have hadjacent : AdjacentCovered (3 :: rest) := by
        simpa [hrungs] using harithmetic.2.2.1
      have hlast : ∃ last, (3 :: rest).getLast? = some last ∧
          n ≤ last + binaryLimit := by
        obtain ⟨last, hlast, hschedule⟩ := harithmetic.2.2.2
        have hnSchedule : n ≤ scheduledEndpoint :=
          hnUpper.trans sourceLimit_le_scheduledEndpoint
        exact ⟨last, by simpa [hrungs] using hlast, hnSchedule.trans hschedule⟩
      exact cover_from_chain 3 rest n hallOdd hadjacent hlast hnOdd (by omega)

theorem valid_of_check {ladder : PrimeLadder}
    (hcheck : ladder.check = true) : ladder.Valid :=
  valid_of_arithmeticValid (check_sound hcheck)

end PrimeLadder

def SourceClaim : Prop :=
  ∀ n : Nat, Odd n → 7 ≤ n → n ≤ sourceLimit → IsThreePrimeSum n

theorem sourceClaim_of_binary_and_ladder
    (binary : BinaryGoldbachClaim)
    {ladder : PrimeLadder} (hladder : ladder.Valid) : SourceClaim := by
  intro n hodd hnLower hnUpper
  obtain ⟨p, hpMem, hpStart, hpEnd⟩ :=
    hladder.2 n hodd hnLower hnUpper
  obtain ⟨hpPrime, hpTwo⟩ := hladder.1 p hpMem
  have hpLe : p ≤ n := by omega
  have hpOdd : Odd p := hpPrime.odd_of_ne_two (by omega)
  have heEven : Even (n - p) := Nat.Odd.sub_odd hodd hpOdd
  have heLower : 4 ≤ n - p := by omega
  have heUpper : n - p ≤ binaryLimit := by omega
  obtain ⟨q, r, hqPrime, hrPrime, hsum⟩ :=
    binary (n - p) heEven heLower heUpper
  exact ⟨p, q, r, hpPrime, hqPrime, hrPrime, by omega⟩

structure CheckedSourceEvidence where
  ladder : PrimeLadder
  binary : BinaryGoldbachClaim
  ladderCheck : ladder.check = true

theorem sourceClaim_of_checked_evidence
    (evidence : CheckedSourceEvidence) : SourceClaim :=
  sourceClaim_of_binary_and_ladder evidence.binary
    (PrimeLadder.valid_of_check evidence.ladderCheck)

end SparkInterval.TernaryGoldbach.Goldbach10Pow27SourceSemantics
