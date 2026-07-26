/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusFusedFinalization

/-!
# A short completeness contract for the fused Möbius prime roster

The abstract finalizer consumes `SourceRosterValid`, whose fields spell out
the exact product, factor-count, residual, and square-event facts used for one
row.  A native roster should not have to carry those facts independently.

This file derives all of them from the conventional segmented-sieve
condition:

* the roster has no duplicates;
* every roster entry is prime; and
* every prime `p` with `p * p ≤ number` occurs in the roster.

The last condition is precisely enough.  It detects every repeated prime
factor, and on a squarefree row it leaves at most one prime in the residual.
No bound-specific computation or native-execution claim occurs here.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness

open SparkInterval.TernaryGoldbach.MobiusFusedFinalization
open SparkInterval.TernaryGoldbach.MobiusResidue235

/-- Largest prime needed by the production `10^16` source domain. -/
def productionPrimeBound : Nat := 100_000_000

@[simp] theorem productionPrimeBound_square :
    productionPrimeBound * productionPrimeBound =
      SparkInterval.TernaryGoldbach.MobiusFusedSupport.sourceLimit := by
  norm_num [productionPrimeBound,
    SparkInterval.TernaryGoldbach.MobiusFusedSupport.sourceLimit]

/-- Minimal mathematical contract for a complete segmented-sieve roster at
one positive source row. -/
structure CompletePrimeRoster
    (number : Nat) (primes : List Nat) : Prop where
  numberPositive : 0 < number
  nodup : primes.Nodup
  entriesPrime : ∀ prime ∈ primes, Nat.Prime prime
  completeThroughSqrt :
    ∀ prime, Nat.Prime prime → prime * prime ≤ number →
      prime ∈ primes

/-- One authenticated roster certificate shared by every row through a fixed
prime bound. -/
structure PrimeRosterThrough
    (bound : Nat) (primes : List Nat) : Prop where
  nodup : primes.Nodup
  entriesPrime : ∀ prime ∈ primes, Nat.Prime prime
  complete :
    ∀ prime, Nat.Prime prime → prime ≤ bound → prime ∈ primes

namespace PrimeRosterThrough

variable {bound number : Nat} {primes : List Nat}

/-- A bounded roster is complete for every positive row at most the square
of its bound.  This is the global-to-row bridge used by a source campaign. -/
theorem completePrimeRoster
    (valid : PrimeRosterThrough bound primes)
    (numberPositive : 0 < number)
    (numberLeSquare : number ≤ bound * bound) :
    CompletePrimeRoster number primes where
  numberPositive := numberPositive
  nodup := valid.nodup
  entriesPrime := valid.entriesPrime
  completeThroughSqrt := by
    intro prime primePrime primeSquareLeNumber
    have primeLeBound : prime ≤ bound :=
      nonneg_le_nonneg_of_sq_le_sq (Nat.zero_le bound)
        (primeSquareLeNumber.trans numberLeSquare)
    exact valid.complete prime primePrime primeLeBound

end PrimeRosterThrough

namespace CompletePrimeRoster

variable {number : Nat} {primes : List Nat}

private theorem selectedNodup
    (valid : CompletePrimeRoster number primes) :
    (selectedDivisors number primes).Nodup := by
  exact valid.nodup.filter _

private theorem selectedPrime
    (valid : CompletePrimeRoster number primes) :
    ∀ prime ∈ selectedDivisors number primes, Nat.Prime prime := by
  intro prime member
  exact valid.entriesPrime prime (List.mem_of_mem_filter member)

private theorem selectedDivides
    {prime : Nat}
    (member : prime ∈ selectedDivisors number primes) :
    prime ∣ number := by
  exact of_decide_eq_true (List.mem_filter.mp member).2

private theorem selectedSubsetPrimeFactors
    (valid : CompletePrimeRoster number primes) :
    (selectedDivisors number primes).toFinset ⊆
      number.primeFactors := by
  intro prime member
  have listMember :
      prime ∈ selectedDivisors number primes :=
    List.mem_toFinset.mp member
  exact
    (valid.selectedPrime prime listMember).mem_primeFactors
      (selectedDivides listMember)
      (Nat.ne_of_gt valid.numberPositive)

private theorem selectedProductPositive
    (valid : CompletePrimeRoster number primes) :
    0 < (selectedDivisors number primes).prod := by
  apply List.prod_pos
  intro prime member
  exact (valid.selectedPrime prime member).pos

private theorem selectedProductDivides
    (valid : CompletePrimeRoster number primes) :
    (selectedDivisors number primes).prod ∣ number := by
  let selected := selectedDivisors number primes
  have subset :
      selected.toFinset ⊆ number.primeFactors :=
    valid.selectedSubsetPrimeFactors
  have finsetProductDivides :
      (∏ prime ∈ selected.toFinset, prime) ∣
        ∏ prime ∈ number.primeFactors, prime :=
    Finset.prod_dvd_prod_of_subset
      selected.toFinset number.primeFactors id subset
  have radicalDivides :
      (∏ prime ∈ number.primeFactors, prime) ∣ number :=
    Nat.prod_primeFactors_dvd number
  have selectedProduct :
      (∏ prime ∈ selected.toFinset, prime) = selected.prod := by
    simpa using List.prod_toFinset id valid.selectedNodup
  rw [selectedProduct] at finsetProductDivides
  exact finsetProductDivides.trans radicalDivides

private theorem selectedPairwiseCoprime
    (valid : CompletePrimeRoster number primes) :
    ((selectedDivisors number primes).toFinset : Set Nat).Pairwise
      (Function.onFun Nat.Coprime id) := by
  intro first firstMember second secondMember distinct
  have firstList :
      first ∈ selectedDivisors number primes :=
    List.mem_toFinset.mp firstMember
  have secondList :
      second ∈ selectedDivisors number primes :=
    List.mem_toFinset.mp secondMember
  exact
    (Nat.coprime_primes
      (valid.selectedPrime first firstList)
      (valid.selectedPrime second secondList)).mpr distinct

private theorem selectedProductSquarefree
    (valid : CompletePrimeRoster number primes) :
    Squarefree (selectedDivisors number primes).prod := by
  let selected := selectedDivisors number primes
  have pairwiseIsRelPrime :
      (selected.toFinset : Set Nat).Pairwise
        (Function.onFun IsRelPrime id) := by
    intro first firstMember second secondMember distinct
    change IsRelPrime first second
    rw [← Nat.coprime_iff_isRelPrime]
    exact valid.selectedPairwiseCoprime
      firstMember secondMember distinct
  have finsetSquarefree :
      Squarefree (∏ prime ∈ selected.toFinset, prime) := by
    apply Finset.squarefree_prod_of_pairwise_isCoprime
      pairwiseIsRelPrime
    intro prime member
    exact
      (valid.selectedPrime prime
        (List.mem_toFinset.mp member)).squarefree
  have selectedProduct :
      (∏ prime ∈ selected.toFinset, prime) = selected.prod := by
    simpa using List.prod_toFinset id valid.selectedNodup
  simpa [selectedProduct] using finsetSquarefree

private theorem selectedDistinctCount
    (valid : CompletePrimeRoster number primes) :
    (selectedDivisors number primes).length =
      ArithmeticFunction.cardDistinctFactors
        (selectedDivisors number primes).prod := by
  let selected := selectedDivisors number primes
  change selected.length =
    ArithmeticFunction.cardDistinctFactors selected.prod
  have countProduct :=
    ArithmeticFunction.cardDistinctFactors_prod
      (s := selected.toFinset) (f := id)
      valid.selectedPairwiseCoprime
  have selectedProduct :
      (∏ prime ∈ selected.toFinset, prime) = selected.prod := by
    simpa using List.prod_toFinset id valid.selectedNodup
  have countSum :
      (∑ prime ∈ selected.toFinset,
          ArithmeticFunction.cardDistinctFactors prime) =
        selected.toFinset.card := by
    calc
      (∑ prime ∈ selected.toFinset,
          ArithmeticFunction.cardDistinctFactors prime) =
          ∑ _prime ∈ selected.toFinset, 1 := by
            apply Finset.sum_congr rfl
            intro prime member
            exact
              ArithmeticFunction.cardDistinctFactors_apply_prime
                (valid.selectedPrime prime
                  (List.mem_toFinset.mp member))
      _ = selected.toFinset.card := by simp
  simp only [id_eq] at countProduct
  rw [selectedProduct, countSum] at countProduct
  rw [← List.toFinset_card_of_nodup valid.selectedNodup]
  exact countProduct.symm

private theorem residualOneOrPrime
    (valid : CompletePrimeRoster number primes)
    (squarefree : Squarefree number) :
    number / (selectedDivisors number primes).prod = 1 ∨
      Nat.Prime
        (number / (selectedDivisors number primes).prod) := by
  let product := (selectedDivisors number primes).prod
  let residual := number / product
  have productPositive : 0 < product :=
    valid.selectedProductPositive
  have productDivides : product ∣ number :=
    valid.selectedProductDivides
  have decomposition : product * residual = number := by
    exact Nat.mul_div_cancel' productDivides
  have residualPositive : 0 < residual := by
    have productLe : product ≤ number :=
      Nat.le_of_dvd valid.numberPositive productDivides
    exact Nat.div_pos productLe productPositive
  have productResidualSquarefree :
      Squarefree (product * residual) := by
    simpa [decomposition] using squarefree
  have productResidualCoprime : Nat.Coprime product residual :=
    (Nat.squarefree_mul_iff.mp productResidualSquarefree).1
  by_cases residualOne : residual = 1
  · exact Or.inl residualOne
  · apply Or.inr
    by_contra residualNotPrime
    let prime := Nat.minFac residual
    have primePrime : Nat.Prime prime :=
      Nat.minFac_prime residualOne
    have primeDividesResidual : prime ∣ residual :=
      Nat.minFac_dvd residual
    have primeSquareLeResidual : prime ^ 2 ≤ residual :=
      Nat.minFac_sq_le_self residualPositive residualNotPrime
    have residualLeNumber : residual ≤ number :=
      Nat.div_le_self number product
    have primeSquareLeNumber : prime * prime ≤ number := by
      simpa [pow_two] using
        primeSquareLeResidual.trans residualLeNumber
    have primeInRoster : prime ∈ primes :=
      valid.completeThroughSqrt prime primePrime
        primeSquareLeNumber
    have primeDividesNumber : prime ∣ number := by
      rw [← decomposition]
      exact dvd_mul_of_dvd_right primeDividesResidual product
    have primeSelected :
        prime ∈ selectedDivisors number primes := by
      exact List.mem_filter.mpr
        ⟨primeInRoster, decide_eq_true primeDividesNumber⟩
    have primeDividesProduct : prime ∣ product :=
      List.dvd_prod primeSelected
    exact
      (Nat.not_coprime_of_dvd_of_dvd
        primePrime.one_lt primeDividesProduct
        primeDividesResidual) productResidualCoprime

private theorem squarefulExact
    (valid : CompletePrimeRoster number primes) :
    hasSquareEvent number primes =
      decide (¬Squarefree number) := by
  by_cases squarefree : Squarefree number
  · have noEvent :
      hasSquareEvent number primes = false := by
      rw [hasSquareEvent, List.any_eq_false]
      intro prime member
      have primePrime := valid.entriesPrime prime member
      have noSquare :
          ¬prime * prime ∣ number :=
        (Nat.squarefree_iff_prime_squarefree.mp squarefree)
          prime primePrime
      simp [noSquare]
    simp [squarefree, noEvent]
  · have squareWitness :
        ∃ prime, Nat.Prime prime ∧
          prime * prime ∣ number := by
      rw [Nat.squarefree_iff_prime_squarefree] at squarefree
      push Not at squarefree
      exact squarefree
    obtain ⟨prime, primePrime, primeSquareDivides⟩ :=
      squareWitness
    have primeSquareLe :
        prime * prime ≤ number :=
      Nat.le_of_dvd valid.numberPositive primeSquareDivides
    have primeInRoster : prime ∈ primes :=
      valid.completeThroughSqrt prime primePrime primeSquareLe
    have primeDivides :
        prime ∣ number :=
      (dvd_mul_right prime prime).trans primeSquareDivides
    have eventTrue : hasSquareEvent number primes = true := by
      rw [hasSquareEvent, List.any_eq_true]
      refine ⟨prime, primeInRoster, ?_⟩
      simp [primeDivides, primeSquareDivides]
    simp [squarefree, eventTrue]

/-- The short conventional roster contract implies every explicit
source-row invariant consumed by the fused finalizer. -/
theorem sourceRosterValid
    (valid : CompletePrimeRoster number primes) :
    SourceRosterValid number primes where
  numberPositive := valid.numberPositive
  productPositive := valid.selectedProductPositive
  productDivides := valid.selectedProductDivides
  productSquarefree := valid.selectedProductSquarefree
  distinctCount := valid.selectedDistinctCount
  residualOneOrPrime := valid.residualOneOrPrime
  squareful := valid.squarefulExact

/-- End-to-end Möbius correctness from the minimal prime-roster contract. -/
theorem finalize_foldSupport_eq_moebius
    (valid : CompletePrimeRoster number primes) :
    finalize number (foldSupport number primes) =
      ArithmeticFunction.moebius number :=
  MobiusFusedFinalization.finalize_foldSupport_eq_moebius
    valid.sourceRosterValid

end CompletePrimeRoster

#print axioms CompletePrimeRoster.sourceRosterValid
#print axioms CompletePrimeRoster.finalize_foldSupport_eq_moebius
#print axioms PrimeRosterThrough.completePrimeRoster
#print axioms productionPrimeBound_square

end SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
