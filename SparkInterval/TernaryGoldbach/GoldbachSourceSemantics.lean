/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Data.Nat.Prime.Basic
import Mathlib.Tactic

/-!
# Exact finite Helfgott--Platt source semantics

The historical computation has two independent components:

1. binary Goldbach for every even integer in `[4,4*10^18]`; and
2. a certified odd-prime ladder whose translated intervals
   `[p+4,p+4*10^18]` cover every odd target through the source endpoint.

This file makes that boundary explicit.  `PrimeLadder.Valid` is a finite-list
contract with separate primality and interval-union clauses, while
`BinaryGoldbachClaim` is the exact binary prerequisite.  Ordinary Lean proves
that their conjunction implies the paper's three-prime theorem, including all
parity and natural-subtraction details.

The theorem does not claim that a Merkle root, a process exit code, or an
attestation proves either semantic premise.  Production certificate parsers
must construct these two contracts from the retained witness streams.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.GoldbachSourceSemantics

/-- Endpoint of the binary Goldbach prerequisite and maximum ladder radius. -/
def binaryLimit : Nat := 4_000_000_000_000_000_000

/-- Exact endpoint in Helfgott--Platt Theorem 4.1. -/
def sourceLimit : Nat := 8_875_694_145_621_773_516_800_000_000_000

/-- The source endpoint is exactly the paper's 492,700 ranges of width
`2^54 * 10^9`. -/
theorem sourceLimit_eq_range_product :
    sourceLimit = 492_700 * (2 ^ 54 * 10 ^ 9) := by
  norm_num [sourceLimit]

/-- Portable proposition-level meaning of a three-prime representation. -/
def IsThreePrimeSum (n : Nat) : Prop :=
  ∃ p q r : Nat, p.Prime ∧ q.Prime ∧ r.Prime ∧ p + q + r = n

/-- Exact binary prerequisite used by the ladder reduction. -/
def BinaryGoldbachClaim : Prop :=
  ∀ e : Nat, Even e → 4 ≤ e → e ≤ binaryLimit →
    ∃ q r : Nat, q.Prime ∧ r.Prime ∧ q + r = e

/-- A retained finite prime ladder.  Its entries may use any sound primality
certificate; the list semantics is independent of the producer format. -/
structure PrimeLadder where
  rungs : List Nat

namespace PrimeLadder

/-- Decidable adjacent translated-interval coverage.  The `+2` is exact: all
relevant interval endpoints are odd, so two consecutive odd endpoints leave
no odd target between them. -/
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

/-- Small finite arithmetic/primality contract emitted by the ladder replay.
Unlike `Valid`, this proposition contains no universal target-range claim. -/
def ArithmeticValid (ladder : PrimeLadder) : Prop :=
  ladder.rungs.head? = some 3 ∧
    (∀ p, p ∈ ladder.rungs → p.Prime ∧ 2 < p) ∧
    AdjacentCovered ladder.rungs ∧
    ∃ last, ladder.rungs.getLast? = some last ∧
      sourceLimit ≤ last + binaryLimit

instance instDecidableArithmeticValid (ladder : PrimeLadder) :
    Decidable ladder.ArithmeticValid := by
  unfold ArithmeticValid
  infer_instance

def check (ladder : PrimeLadder) : Bool :=
  decide ladder.ArithmeticValid

theorem check_sound {ladder : PrimeLadder}
    (hcheck : ladder.check = true) : ladder.ArithmeticValid :=
  of_decide_eq_true hcheck

/-- Exact semantic conditions replayed from the ladder:

* every retained rung is an odd prime; and
* the union of its translated binary-Goldbach intervals covers every source
  target.  Stating the interval union directly preserves the important
  parity/off-by-two boundary checked by the production replay. -/
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
            q + 4 ≤ p + binaryLimit + 2 ∧
              AdjacentCovered (q :: tail) := by
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

/-- The executable first/adjacent/last conditions imply the universal ladder
coverage contract.  This theorem accounts for the parity-sensitive `+2`
overlap convention used by the production replay. -/
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
        obtain ⟨last, hlast, hsource⟩ := harithmetic.2.2.2
        exact ⟨last, by simpa [hrungs] using hlast, hnUpper.trans hsource⟩
      exact cover_from_chain 3 rest n hallOdd hadjacent hlast hnOdd (by omega)

theorem valid_of_check {ladder : PrimeLadder}
    (hcheck : ladder.check = true) : ladder.Valid :=
  valid_of_arithmeticValid (check_sound hcheck)

end PrimeLadder

/-- Exact source-shaped finite ternary Goldbach claim. -/
def SourceClaim : Prop :=
  ∀ n : Nat, Odd n → 7 ≤ n → n ≤ sourceLimit →
    IsThreePrimeSum n

/-- Binary Goldbach plus the independently checked prime-ladder union implies
the complete source theorem. -/
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

/-- One source-scale evidence package with the two independent semantic
components kept visibly separate. -/
structure SourceEvidence where
  ladder : PrimeLadder
  binary : BinaryGoldbachClaim
  ladderValid : ladder.Valid

theorem sourceClaim_of_evidence (evidence : SourceEvidence) : SourceClaim :=
  sourceClaim_of_binary_and_ladder evidence.binary evidence.ladderValid

/-- Worker-shaped package: the ladder's universal coverage is derived from a
decidable exact check rather than carried as trusted semantic data. -/
structure CheckedSourceEvidence where
  ladder : PrimeLadder
  binary : BinaryGoldbachClaim
  ladderCheck : ladder.check = true

theorem sourceClaim_of_checked_evidence
    (evidence : CheckedSourceEvidence) : SourceClaim :=
  sourceClaim_of_binary_and_ladder evidence.binary
    (PrimeLadder.valid_of_check evidence.ladderCheck)

end SparkInterval.TernaryGoldbach.GoldbachSourceSemantics
