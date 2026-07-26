/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.NumberTheory.ArithmeticFunction.Moebius
import SparkInterval.TernaryGoldbach.MobiusResidualGCD
import SparkInterval.TernaryGoldbach.MobiusResidue235

/-!
# End-to-end mathematical finalization of the fused Möbius state

The CUDA sieve accumulates a product of distinct enumerated prime divisors,
their count, and a squareful bit.  It then accounts for the residual
`n / product`, which is one or one unenumerated prime on a complete source
roster.

This file proves two architecture-independent facts needed by the native
refinement:

* prime-event updates may occur in any serialization, so an atomic/CUDA
  schedule cannot change the mathematical folded support; and
* once the folded support satisfies the explicit source-row invariant, the
  native parity finalizer is exactly Mathlib's Möbius function.

The invariant is deliberately stated without a CUDA, compiler, or receipt
assumption.  A future machine-refinement theorem must prove it for the exact
native prime roster and execution.  This file does not claim that such an
execution occurred.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusFusedFinalization

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusResidue235
open SparkInterval.TernaryGoldbach.MobiusResidualGCD

/-! ## Schedule independence -/

/-- Conditional prime-event updates commute for every row.

This is the mathematical linearization law needed by the native CAS loop:
regardless of which two distinct-prime events win their atomic operations
first, the resulting support is identical.  The statement is intentionally
stronger than the production roster requirement and does not need primality
or distinctness assumptions. -/
theorem applyPrime_right_comm (n : Nat) :
    RightCommutative (applyPrime n) := by
  constructor
  intro support firstPrime secondPrime
  unfold applyPrime
  by_cases hfirst : firstPrime ∣ n <;>
    by_cases hsecond : secondPrime ∣ n <;>
    simp only [hfirst, hsecond, if_true, if_false]
  exact update_comm support firstPrime secondPrime
    (decide (firstPrime * firstPrime ∣ n))
    (decide (secondPrime * secondPrime ∣ n))

/-- Any permutation of the prime-event roster yields the same support. -/
theorem foldSupport_perm
    (n : Nat) {first second : List Nat}
    (permutation : first.Perm second) :
    foldSupport n first = foldSupport n second := by
  letI : RightCommutative (applyPrime n) :=
    applyPrime_right_comm n
  exact permutation.foldl_eq initialSupport

/-! ## Fold realization -/

/-- Prime events from a roster which actually divide the current row. -/
def selectedDivisors (number : Nat) (primes : List Nat) : List Nat :=
  primes.filter fun prime => prime ∣ number

/-- Whether the roster contains a square-divisor event for this row.

The divisibility conjunct mirrors the native control flow: a square test is
consumed only inside a prime-divisor event. -/
def hasSquareEvent (number : Nat) (primes : List Nat) : Bool :=
  primes.any fun prime =>
    decide (prime ∣ number ∧ prime * prime ∣ number)

/-- Product accumulated by an arbitrary initial support and prime roster. -/
theorem foldl_applyPrime_product
    (number : Nat) (primes : List Nat) (support : Support) :
    (primes.foldl (applyPrime number) support).product =
      support.product * (selectedDivisors number primes).prod := by
  induction primes generalizing support with
  | nil =>
      simp [selectedDivisors]
  | cons prime rest inductionHypothesis =>
      rw [List.foldl_cons, inductionHypothesis]
      by_cases divides : prime ∣ number
      · simp [selectedDivisors, applyPrime, divides, update,
          Nat.mul_assoc]
      · simp [selectedDivisors, applyPrime, divides]

/-- Distinct-event count accumulated by the same fold. -/
theorem foldl_applyPrime_distinctCount
    (number : Nat) (primes : List Nat) (support : Support) :
    (primes.foldl (applyPrime number) support).distinctCount =
      support.distinctCount +
        (selectedDivisors number primes).length := by
  induction primes generalizing support with
  | nil =>
      simp [selectedDivisors]
  | cons prime rest inductionHypothesis =>
      rw [List.foldl_cons, inductionHypothesis]
      by_cases divides : prime ∣ number
      · simp [selectedDivisors, applyPrime, divides, update,
          Nat.add_assoc, Nat.add_comm]
      · simp [selectedDivisors, applyPrime, divides]

/-- The folded squareful bit is exactly the disjunction of the initial bit
and all roster square events. -/
theorem foldl_applyPrime_squareful
    (number : Nat) (primes : List Nat) (support : Support) :
    (primes.foldl (applyPrime number) support).squareful =
      (support.squareful || hasSquareEvent number primes) := by
  induction primes generalizing support with
  | nil =>
      simp [hasSquareEvent]
  | cons prime rest inductionHypothesis =>
      rw [List.foldl_cons, inductionHypothesis]
      by_cases divides : prime ∣ number
      · by_cases dividesSquare : prime * prime ∣ number
        · simp [hasSquareEvent, applyPrime, update, divides,
            dividesSquare]
        · simp [hasSquareEvent, applyPrime, update, divides,
            dividesSquare]
      · have notDividesSquare : ¬prime * prime ∣ number := by
          intro squareDivides
          exact divides ((dvd_mul_right prime prime).trans squareDivides)
        simp [hasSquareEvent, applyPrime, divides, notDividesSquare]

/-- The production fold starts from product one and therefore accumulates
exactly the selected divisor product. -/
@[simp] theorem foldSupport_product
    (number : Nat) (primes : List Nat) :
    (foldSupport number primes).product =
      (selectedDivisors number primes).prod := by
  simpa [foldSupport, initialSupport] using
    foldl_applyPrime_product number primes initialSupport

/-- The production distinct-count field is the number of selected divisor
events. -/
@[simp] theorem foldSupport_distinctCount
    (number : Nat) (primes : List Nat) :
    (foldSupport number primes).distinctCount =
      (selectedDivisors number primes).length := by
  simpa [foldSupport, initialSupport] using
    foldl_applyPrime_distinctCount number primes initialSupport

/-- The production squareful field is exactly the roster square-event bit. -/
@[simp] theorem foldSupport_squareful
    (number : Nat) (primes : List Nat) :
    (foldSupport number primes).squareful =
      hasSquareEvent number primes := by
  simpa [foldSupport, initialSupport] using
    foldl_applyPrime_squareful number primes initialSupport

/-! ## Exact native finalizer -/

/-- The signed parity emitted for a squarefree row. -/
def signedParity (factorCount : Nat) : Int :=
  if factorCount % 2 = 0 then 1 else -1

/-- Native mathematical finalization of one fused support state.

The squareful branch is checked first.  Otherwise the residual contributes
one additional distinct prime precisely when it is greater than one. -/
def finalize (number : Nat) (support : Support) : Int :=
  if support.squareful then
    0
  else
    signedParity
      (support.distinctCount +
        if 1 < number / support.product then 1 else 0)

/-- Exact source-row invariant expected after the complete prime roster.

`residualOneOrPrime` is the usual segmented-sieve residual theorem.  The
squareful bit is tied to the source integer itself, rather than merely to an
implementation-local flag.  The count field is tied to the mathematical
distinct-factor count of the accumulated product.
-/
structure SourceRowSupportValid
    (number : Nat) (support : Support) : Prop where
  numberPositive : 0 < number
  productPositive : 0 < support.product
  productDivides : support.product ∣ number
  productSquarefree : Squarefree support.product
  distinctCount :
    support.distinctCount =
      ArithmeticFunction.cardDistinctFactors support.product
  residualOneOrPrime :
    Squarefree number →
      number / support.product = 1 ∨
        Nat.Prime (number / support.product)
  squareful :
    support.squareful = decide (¬Squarefree number)

/-- Roster-level form of the source invariant.

Unlike `SourceRowSupportValid`, this structure talks only about the input
prime roster and ordinary list operations.  The fold-realization theorems
above then construct the support-level invariant automatically.  This is the
preferred boundary for a future proof that the authenticated native roster
and event schedule are complete. -/
structure SourceRosterValid
    (number : Nat) (primes : List Nat) : Prop where
  numberPositive : 0 < number
  productPositive :
    0 < (selectedDivisors number primes).prod
  productDivides :
    (selectedDivisors number primes).prod ∣ number
  productSquarefree :
    Squarefree (selectedDivisors number primes).prod
  distinctCount :
    (selectedDivisors number primes).length =
      ArithmeticFunction.cardDistinctFactors
        (selectedDivisors number primes).prod
  residualOneOrPrime :
    Squarefree number →
      number / (selectedDivisors number primes).prod = 1 ∨
        Nat.Prime
          (number / (selectedDivisors number primes).prod)
  squareful :
    hasSquareEvent number primes =
      decide (¬Squarefree number)

/-- Exact prime-roster properties imply the support invariant after the
mathematical event fold. -/
theorem sourceRowSupportValid_foldSupport
    {number : Nat} {primes : List Nat}
    (valid : SourceRosterValid number primes) :
    SourceRowSupportValid number (foldSupport number primes) := by
  refine {
    numberPositive := valid.numberPositive
    productPositive := ?_
    productDivides := ?_
    productSquarefree := ?_
    distinctCount := ?_
    residualOneOrPrime := ?_
    squareful := ?_
  }
  · simpa using valid.productPositive
  · simpa using valid.productDivides
  · simpa using valid.productSquarefree
  · simpa using valid.distinctCount
  · simpa using valid.residualOneOrPrime
  · simpa using valid.squareful

theorem signedParity_eq_negOnePow (factorCount : Nat) :
    signedParity factorCount = (-1 : Int) ^ factorCount := by
  rcases Nat.mod_two_eq_zero_or_one factorCount with heven | hodd
  · simp [signedParity, heven, neg_one_pow_eq_pow_mod_two]
  · simp [signedParity, hodd, neg_one_pow_eq_pow_mod_two]

/-- If the represented source row is squarefree, the product and residual
are coprime. -/
theorem SourceRowSupportValid.productCoprimeResidual
    {number : Nat} {support : Support}
    (valid : SourceRowSupportValid number support)
    (squarefree : Squarefree number) :
    Nat.Coprime support.product (number / support.product) := by
  have decomposition :
      support.product * (number / support.product) = number :=
    Nat.mul_div_cancel' valid.productDivides
  have squarefreeProductResidual :
      Squarefree
        (support.product * (number / support.product)) := by
    simpa [decomposition] using squarefree
  exact (Nat.squarefree_mul_iff.mp squarefreeProductResidual).1

/-- The fused finalizer is exactly Mathlib's Möbius function.

This is the application-level correctness theorem for the abstract native
kernel.  It preserves square multiplicities: a nonsquarefree input takes the
zero branch, and only a proved squarefree input reaches the parity branch. -/
theorem finalize_eq_moebius
    {number : Nat} {support : Support}
    (valid : SourceRowSupportValid number support) :
    finalize number support = ArithmeticFunction.moebius number := by
  by_cases squarefree : Squarefree number
  · have squarefulFalse : support.squareful = false := by
      simpa [squarefree] using valid.squareful
    have numberNeZero : number ≠ 0 :=
      Nat.ne_of_gt valid.numberPositive
    have coprime :=
      valid.productCoprimeResidual squarefree
    have distinctFactors :=
      cardDistinctFactors_product_residual
        coprime (valid.residualOneOrPrime squarefree)
    have decomposition :
        support.product * (number / support.product) = number :=
      Nat.mul_div_cancel' valid.productDivides
    have distinctFactorCount :
        support.distinctCount +
            (if 1 < number / support.product then 1 else 0) =
          ArithmeticFunction.cardDistinctFactors number := by
      rw [valid.distinctCount, ← distinctFactors, decomposition]
    simp only [finalize, squarefulFalse, Bool.false_eq_true, if_false]
    rw [signedParity_eq_negOnePow, distinctFactorCount,
      ArithmeticFunction.moebius_apply_of_squarefree squarefree]
    have cardEquality :=
      (ArithmeticFunction.cardDistinctFactors_eq_cardFactors_iff_squarefree
        numberNeZero).2 squarefree
    rw [cardEquality]
  · have squarefulTrue : support.squareful = true := by
      simpa [squarefree] using valid.squareful
    simp only [finalize, squarefulTrue, if_true]
    exact
      (ArithmeticFunction.moebius_eq_zero_of_not_squarefree
        squarefree).symm

/-- Roster-level end-to-end correctness of the abstract fused kernel. -/
theorem finalize_foldSupport_eq_moebius
    {number : Nat} {primes : List Nat}
    (valid : SourceRosterValid number primes) :
    finalize number (foldSupport number primes) =
      ArithmeticFunction.moebius number :=
  finalize_eq_moebius (sourceRowSupportValid_foldSupport valid)

/-! ## Residue-seeded production composition -/

/-- Replacing the first three prime passes by the residue table leaves the
finalized Möbius value unchanged for every suffix. -/
theorem finalize_residueSeeded_eq_fullFold
    (number : Nat) (suffix : List Nat) :
    finalize number
        (suffix.foldl (applyPrime number) (residueSeed number)) =
      finalize number (foldSupport number (seedPrimes ++ suffix)) := by
  rw [fold_prefix_suffix_eq_residueSeed]

/-- End-to-end abstract correctness for the residue-seeded production fold,
conditional only on the explicit complete-roster source invariant. -/
theorem finalize_residueSeeded_eq_moebius
    (number : Nat) (suffix : List Nat)
    (valid :
      SourceRowSupportValid number
        (foldSupport number (seedPrimes ++ suffix))) :
    finalize number
        (suffix.foldl (applyPrime number) (residueSeed number)) =
      ArithmeticFunction.moebius number := by
  rw [finalize_residueSeeded_eq_fullFold]
  exact finalize_eq_moebius valid

#print axioms applyPrime_right_comm
#print axioms foldSupport_perm
#print axioms signedParity_eq_negOnePow
#print axioms foldl_applyPrime_product
#print axioms foldl_applyPrime_distinctCount
#print axioms foldl_applyPrime_squareful
#print axioms foldSupport_product
#print axioms foldSupport_distinctCount
#print axioms foldSupport_squareful
#print axioms sourceRowSupportValid_foldSupport
#print axioms SourceRowSupportValid.numberPositive
#print axioms SourceRowSupportValid.productCoprimeResidual
#print axioms finalize_eq_moebius
#print axioms finalize_foldSupport_eq_moebius
#print axioms finalize_residueSeeded_eq_fullFold
#print axioms finalize_residueSeeded_eq_moebius

end SparkInterval.TernaryGoldbach.MobiusFusedFinalization
