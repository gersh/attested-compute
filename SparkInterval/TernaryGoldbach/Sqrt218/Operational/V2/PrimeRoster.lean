/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.FactorPairs
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.Pratt
import TGComputeContracts.Sqrt218.Kernel

/-!
# Efficient proof-carrying prime roster for Sqrt218 V2

The checker in this file is data-independent.  A prime row refers only to
earlier rows for the complete factorization of `p - 1`; the generic
Lucas/Pratt theorem therefore proves rows in one forward induction.  Explicit
factor pairs cover every value omitted between adjacent rows and every value
after the final row through `bound`.

Consequently, successful checking yields the exact
`TGComputeContracts.Sqrt218.PrimeRosterFacts` boundary without evaluating
`Nat.Prime` for every natural number through a production bound.  This module
contains no production certificate and importing it performs no long replay.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational.V2

/-- One V2 prime row.

`factorRefs` contains multiplicity and refers to earlier rows.  Thus the
values at those indices are the complete prime-factor list of `prime - 1`.
`gapPairs` contains one nontrivial factorization for every natural number
strictly between the preceding prime row (or `1` for the first row) and this
row. -/
structure PrimeRow where
  prime : Nat
  witness : Nat
  factorRefs : List Nat
  gapPairs : List FactorPair
  deriving Repr, DecidableEq, Inhabited

/-- A generic V2 prime-roster certificate.  `tailPairs` covers every value
strictly after the final row and at most the separately supplied bound. -/
structure PrimeRosterCertificate where
  rows : List PrimeRow
  tailPairs : List FactorPair
  deriving Repr, DecidableEq, Inhabited

namespace PrimeRosterCertificate

def count (certificate : PrimeRosterCertificate) : Nat :=
  certificate.rows.length

def rowAt (certificate : PrimeRosterCertificate) (index : Nat) : PrimeRow :=
  certificate.rows.getD index default

def primeAt (certificate : PrimeRosterCertificate) (index : Nat) : Nat :=
  (certificate.rowAt index).prime

def previousAt (certificate : PrimeRosterCertificate) (index : Nat) : Nat :=
  if index = 0 then 1 else certificate.primeAt (index - 1)

/-- Resolve a multiplicity-preserving list of earlier-row references. -/
def factorValuesAt
    (certificate : PrimeRosterCertificate) (index : Nat) : List Nat :=
  (certificate.rowAt index).factorRefs.map certificate.primeAt

end PrimeRosterCertificate

/-- Small reusable bounded Boolean loop.  Its proof is symbolic in `count`;
it never evaluates a production range while elaborating this module. -/
def checkRange (start count : Nat) (cell : Nat → Bool) : Bool :=
  (List.range count).all fun offset => cell (start + offset)

theorem checkRange_sound
    {start count : Nat} {cell : Nat → Bool}
    (hcheck : checkRange start count cell = true) :
    ∀ index, start ≤ index → index < start + count →
      cell index = true := by
  intro index hlower hupper
  unfold checkRange at hcheck
  rw [List.all_eq_true] at hcheck
  have hoffset : index - start ∈ List.range count := by
    simp only [List.mem_range]
    omega
  have hcell := hcheck (index - start) hoffset
  rw [Nat.add_sub_of_le hlower] at hcell
  exact hcell

/-! ## Per-row Pratt and gap checks -/

/-- Validate a row's Lucas/Pratt evidence.

The special row for `2` is fixed at index zero.  Every other factor reference
must be strictly earlier than the current row. -/
def primeRowCheck
    (certificate : PrimeRosterCertificate) (index : Nat) : Bool :=
  let row := certificate.rowAt index
  if row.prime = 2 then
    decide (
      index = 0 ∧
        row.witness = 0 ∧
        row.factorRefs = [])
  else
    decide (
      row.factorRefs ≠ [] ∧
        (∀ reference ∈ row.factorRefs, reference < index) ∧
        (certificate.factorValuesAt index).prod = row.prime - 1 ∧
        2 ≤ row.witness ∧
        row.witness < row.prime) &&
      lucasResidueCheck row.prime row.witness
        (certificate.factorValuesAt index).dedup

theorem primeRowCheck_sound
    {certificate : PrimeRosterCertificate} {index : Nat}
    (hcheck : primeRowCheck certificate index = true)
    (hprior :
      ∀ reference, reference < index →
        (certificate.primeAt reference).Prime) :
    (certificate.primeAt index).Prime := by
  by_cases htwo : certificate.primeAt index = 2
  · simpa [htwo] using Nat.prime_two
  · have hrowPrimeNe :
        (certificate.rowAt index).prime ≠ 2 := by
      simpa [PrimeRosterCertificate.primeAt] using htwo
    simp only [primeRowCheck, if_neg hrowPrimeNe, Bool.and_eq_true,
      decide_eq_true_eq] at hcheck
    apply prime_of_lucas_factor_list
      (certificate.primeAt index)
      (certificate.rowAt index).witness
      (certificate.factorValuesAt index)
    · simpa [PrimeRosterCertificate.primeAt] using hcheck.1.2.2.1
    · intro factor hfactor
      rw [PrimeRosterCertificate.factorValuesAt] at hfactor
      obtain ⟨reference, hreference, rfl⟩ :=
        List.mem_map.mp hfactor
      exact hprior reference (hcheck.1.2.1 reference hreference)
    · simpa [PrimeRosterCertificate.primeAt] using hcheck.2

/-- Validate the complete open interval preceding one row. -/
def primeGapCheck
    (certificate : PrimeRosterCertificate) (index : Nat) : Bool :=
  factorGapCheck
    (certificate.previousAt index)
    (certificate.primeAt index)
    (certificate.rowAt index).gapPairs

/-- Validate one row and its preceding composite gap. -/
def rowCheck
    (certificate : PrimeRosterCertificate) (index : Nat) : Bool :=
  primeRowCheck certificate index &&
    primeGapCheck certificate index

/-- Validate the nonempty condition and the complete composite tail through
`bound`.  The right endpoint is `bound + 1`, so the open interval includes
`bound` itself. -/
def tailCheck
    (bound : Nat) (certificate : PrimeRosterCertificate) : Bool :=
  decide (0 < certificate.count) &&
    factorGapCheck
      (certificate.primeAt (certificate.count - 1))
      (bound + 1)
      certificate.tailPairs

/-- Efficient generic V2 checker for an exact prime roster through `bound`. -/
def primeRosterCheck
    (bound : Nat) (certificate : PrimeRosterCertificate) : Bool :=
  checkRange 0 certificate.count (rowCheck certificate) &&
    tailCheck bound certificate

/-! ## Semantic soundness -/

private theorem strict_of_adjacent
    {count : Nat} {value : Nat → Nat}
    (hadjacent :
      ∀ index, index + 1 < count →
        value index < value (index + 1)) :
    ∀ left right, left < count → right < count → left < right →
      value left < value right := by
  intro left right hleft hright hlr
  induction right with
  | zero => omega
  | succ right inductionHypothesis =>
      by_cases hequal : left = right
      · subst left
        exact hadjacent right hright
      · exact
          (inductionHypothesis (by omega) (by omega)).trans
            (hadjacent right hright)

private theorem prime_covered_to
    {certificate : PrimeRosterCertificate}
    (hgap :
      ∀ index, index < certificate.count →
        primeGapCheck certificate index = true) :
    ∀ index, index < certificate.count →
      ∀ value, value.Prime → value ≤ certificate.primeAt index →
        ∃ rowIndex, rowIndex ≤ index ∧
          certificate.primeAt rowIndex = value := by
  intro index hindex
  induction index with
  | zero =>
      intro value hvaluePrime hvalueLe
      by_cases hequal : value = certificate.primeAt 0
      · exact ⟨0, le_rfl, hequal.symm⟩
      · have hvalueLt : value < certificate.primeAt 0 :=
          lt_of_le_of_ne hvalueLe hequal
        have hnotPrime :=
          factorGapCheck_sound (hgap 0 hindex) value
            (by
              simpa [primeGapCheck,
                PrimeRosterCertificate.previousAt] using
                hvaluePrime.one_lt)
            (by
              simpa [primeGapCheck] using hvalueLt)
        exact (hnotPrime hvaluePrime).elim
  | succ previous inductionHypothesis =>
      intro value hvaluePrime hvalueLe
      have hpreviousIndex : previous < certificate.count := by
        omega
      by_cases hbefore :
          value ≤ certificate.primeAt previous
      · obtain ⟨rowIndex, hrowIndex, hequal⟩ :=
          inductionHypothesis hpreviousIndex value hvaluePrime hbefore
        exact ⟨rowIndex, hrowIndex.trans (Nat.le_succ previous), hequal⟩
      · by_cases hequal :
          value = certificate.primeAt (previous + 1)
        · exact ⟨previous + 1, le_rfl, hequal.symm⟩
        · have hnotPrime :=
            factorGapCheck_sound
              (hgap (previous + 1) hindex) value
              (by
                simpa [primeGapCheck,
                  PrimeRosterCertificate.previousAt] using
                  (Nat.lt_of_not_ge hbefore))
              (by
                exact lt_of_le_of_ne hvalueLe hequal)
          exact (hnotPrime hvaluePrime).elim

/-- A successful V2 check proves that the rows are exactly the primes through
the generic bound.  This is the sole roster boundary required by the
architecture-neutral Sqrt218 contract. -/
theorem primeRosterCheck_sound
    {bound : Nat} {certificate : PrimeRosterCertificate}
    (hcheck : primeRosterCheck bound certificate = true) :
    TGComputeContracts.Sqrt218.PrimeRosterFacts
      bound certificate.count certificate.primeAt := by
  simp only [primeRosterCheck, Bool.and_eq_true] at hcheck
  have hrows :
      ∀ index, index < certificate.count →
        rowCheck certificate index = true := by
    intro index hindex
    exact checkRange_sound hcheck.1 index (by omega) (by simpa using hindex)
  have hprime :
      ∀ index, index < certificate.count →
        (certificate.primeAt index).Prime := by
    intro index
    induction index using Nat.strong_induction_on with
    | h index inductionHypothesis =>
        intro hindex
        apply primeRowCheck_sound
        · have hrow := hrows index hindex
          simp only [rowCheck, Bool.and_eq_true] at hrow
          exact hrow.1
        · intro reference hreference
          exact
            inductionHypothesis reference hreference
              (hreference.trans hindex)
  have hgaps :
      ∀ index, index < certificate.count →
        primeGapCheck certificate index = true := by
    intro index hindex
    have hrow := hrows index hindex
    simp only [rowCheck, Bool.and_eq_true] at hrow
    exact hrow.2
  simp only [tailCheck, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  have hcountPositive : 0 < certificate.count :=
    hcheck.2.1
  have hlastIndex :
      certificate.count - 1 < certificate.count := by
    omega
  have hadjacent :
      ∀ index, index + 1 < certificate.count →
        certificate.primeAt index <
          certificate.primeAt (index + 1) := by
    intro index hindex
    have hgap :=
      previous_lt_current_of_factorGapCheck
        (hgaps (index + 1) hindex)
    simpa [primeGapCheck,
      PrimeRosterCertificate.previousAt] using hgap
  have hstrict :
      ∀ left right,
        left < certificate.count →
        right < certificate.count →
        left < right →
        certificate.primeAt left < certificate.primeAt right :=
    strict_of_adjacent hadjacent
  have hlastLe :
      certificate.primeAt (certificate.count - 1) ≤ bound := by
    have htailLt :=
      previous_lt_current_of_factorGapCheck hcheck.2.2
    omega
  have hvalueLe :
      ∀ index, index < certificate.count →
        certificate.primeAt index ≤ bound := by
    intro index hindex
    by_cases hequal : index = certificate.count - 1
    · simpa [hequal] using hlastLe
    · have hlt : index < certificate.count - 1 := by
        omega
      exact
        (hstrict index (certificate.count - 1)
          hindex hlastIndex hlt).le.trans hlastLe
  refine {
    count_pos := hcountPositive
    prime := hprime
    value_le := hvalueLe
    strictMono := hstrict
    cover := ?_
  }
  intro value hvaluePrime hvalueBound
  by_cases hbefore :
      value ≤ certificate.primeAt (certificate.count - 1)
  · obtain ⟨index, hindex, hequal⟩ :=
      prime_covered_to hgaps
        (certificate.count - 1) hlastIndex
        value hvaluePrime hbefore
    exact ⟨index, hindex.trans_lt hlastIndex, hequal⟩
  · have hnotPrime :=
      factorGapCheck_sound hcheck.2.2 value
        (Nat.lt_of_not_ge hbefore)
        (by omega)
    exact (hnotPrime hvaluePrime).elim

end SparkInterval.TernaryGoldbach.Sqrt218Operational.V2
