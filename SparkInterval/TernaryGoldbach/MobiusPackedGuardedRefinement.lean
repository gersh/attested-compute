/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusGuardedMachine

/-!
# Packed-word refinement for the guarded Möbius CAS update

The production CUDA kernel stores one row in a 64-bit word:

* bits `0..53` contain the product of the selected distinct primes;
* bits `54..58` contain their count;
* bit `59` is the square-divisibility flag;
* bits `60..62` are reserved and must remain zero; and
* bit `63` is an absorbing poison flag.

This file models the arithmetic performed between two successful atomic-CAS
linearization points.  The main theorem proves that, from every well-formed
packed support word, the guarded packed transition decodes to exactly
`MobiusGuardedMachine.step`.  Failed arithmetic guards set the poison bit;
successful guards preserve the mathematical prime update.

This is a word-level transition theorem, not yet a compiler, CUDA scheduler,
or atomic-memory-model theorem.  Those remain explicit refinement
obligations.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusFusedFinalization
open SparkInterval.TernaryGoldbach.MobiusGuardedMachine
open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
open SparkInterval.TernaryGoldbach.MobiusResidue235

def reservedRadix : Nat := 2 ^ 60
def poisonRadix : Nat := 2 ^ 63
def productMask : Nat := productRadix - 1

/-- The exact arithmetic encoding used for a valid support state. -/
def encodeSupport (support : Support) : Nat :=
  pack support.product support.distinctCount support.squareful

/-- Arithmetic test for the native poison bit. -/
def poisonSet (word : Nat) : Prop :=
  (word / poisonRadix) % 2 = 1

/-- Arithmetic test for the three reserved bits. -/
def reservedSet (word : Nat) : Prop :=
  (word / reservedRadix) % 8 ≠ 0

instance (word : Nat) : Decidable (poisonSet word) := by
  unfold poisonSet
  infer_instance

instance (word : Nat) : Decidable (reservedSet word) := by
  unfold reservedSet
  infer_instance

/-- Decode the native word into the abstract fail-closed state. -/
def decodeWord (word : Nat) : State :=
  if poisonSet word ∨ reservedSet word then
    .poison
  else
    .valid {
      product := unpackProduct word
      distinctCount := unpackCount word
      squareful := unpackSquareful word
    }

/-- Division guard used by the CUDA kernel before multiplying a product by a
prime.  It avoids overflow in the 54-bit product field. -/
def maximumProductGuard (product prime : Nat) : Prop :=
  product ≤ productMask / prime

instance (product prime : Nat) :
    Decidable (maximumProductGuard product prime) := by
  unfold maximumProductGuard
  infer_instance

/-- The native malformed-word checks, written in the order-independent
arithmetic form needed after the CAS load. -/
def NativeStepAdmissible (word prime : Nat) : Prop :=
  ¬ reservedSet word ∧
    unpackProduct word ≠ 0 ∧
    unpackCount word < 13 ∧
    2 ≤ prime ∧
    maximumProductGuard (unpackProduct word) prime

instance (word prime : Nat) :
    Decidable (NativeStepAdmissible word prime) := by
  unfold NativeStepAdmissible
  infer_instance

/-- One successful/poisoning packed-word CAS transition.

The surrounding CAS retry loop only determines which loaded `word` is the
linearization predecessor.  It does not change this pure desired-word
calculation. -/
def wordStep (number word prime : Nat) : Nat :=
  if poisonSet word then
    word
  else if NativeStepAdmissible word prime then
    pack
      (unpackProduct word * prime)
      (unpackCount word + 1)
      (unpackSquareful word ||
        decide (prime * prime ∣ number))
  else
    word + poisonRadix

theorem encodeSupport_lt_reservedRadix
    {support : Support}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    encodeSupport support < reservedRadix := by
  simpa [encodeSupport, reservedRadix] using
    pack_lt_two_pow_sixty
      (squareful := support.squareful) productFits countFits

@[simp] theorem poisonSet_encodeSupport
    {support : Support}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    ¬ poisonSet (encodeSupport support) := by
  have belowReserved :=
    encodeSupport_lt_reservedRadix productFits countFits
  have belowPoison :
      encodeSupport support < poisonRadix := by
    norm_num [reservedRadix, poisonRadix] at *
    omega
  simp [poisonSet, Nat.div_eq_of_lt belowPoison]

@[simp] theorem reservedSet_encodeSupport
    {support : Support}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    ¬ reservedSet (encodeSupport support) := by
  have belowReserved :=
    encodeSupport_lt_reservedRadix productFits countFits
  simp [reservedSet, Nat.div_eq_of_lt belowReserved]

@[simp] theorem decodeWord_encodeSupport
    {support : Support}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    decodeWord (encodeSupport support) = .valid support := by
  have noPoison :=
    poisonSet_encodeSupport productFits countFits
  have noReserved :=
    reservedSet_encodeSupport productFits countFits
  rw [decodeWord, if_neg (by
    exact fun invalid => invalid.elim noPoison noReserved)]
  simp [encodeSupport, unpackProduct_pack productFits,
    unpackCount_pack productFits countFits,
    unpackSquareful_pack productFits countFits]

theorem maximumProductGuard_iff
    {product prime : Nat}
    (primePositive : 0 < prime) :
    maximumProductGuard product prime ↔
      product * prime < productRadix := by
  rw [maximumProductGuard, Nat.le_div_iff_mul_le primePositive]
  norm_num [productMask, productRadix]
  omega

theorem nativeStepAdmissible_encodeSupport_iff
    {support : Support} {prime : Nat}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    NativeStepAdmissible (encodeSupport support) prime ↔
      StepAdmissible support prime := by
  have productDecoded :
      unpackProduct (encodeSupport support) = support.product := by
    exact unpackProduct_pack productFits
  have countDecoded :
      unpackCount (encodeSupport support) =
        support.distinctCount := by
    exact unpackCount_pack productFits countFits
  constructor
  · rintro ⟨_, productNonzero, countBound, primeBound,
      productBound⟩
    rw [productDecoded] at productNonzero productBound
    rw [countDecoded] at countBound
    refine ⟨Nat.pos_of_ne_zero productNonzero, countBound,
      primeBound, ?_⟩
    exact (maximumProductGuard_iff (by omega)).mp productBound
  · rintro ⟨productPositive, countBound, primeBound, productBound⟩
    refine ⟨reservedSet_encodeSupport productFits countFits,
      ?_, ?_, primeBound, ?_⟩
    · simpa [productDecoded] using Nat.ne_of_gt productPositive
    · simpa [countDecoded] using countBound
    · rw [productDecoded]
      exact (maximumProductGuard_iff (by omega)).mpr productBound

theorem poisonSet_add_encodeSupport
    {support : Support}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    poisonSet (encodeSupport support + poisonRadix) := by
  have belowPoison :
      encodeSupport support < poisonRadix := by
    have belowReserved :=
      encodeSupport_lt_reservedRadix productFits countFits
    norm_num [reservedRadix, poisonRadix] at *
    omega
  rw [poisonSet, Nat.add_div_right _ (by
    norm_num [poisonRadix])]
  simp [Nat.div_eq_of_lt belowPoison]

@[simp] theorem decodeWord_add_poison_encodeSupport
    {support : Support}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    decodeWord (encodeSupport support + poisonRadix) = .poison := by
  simp [decodeWord, poisonSet_add_encodeSupport productFits countFits]

/-- The pure desired-word calculation in the guarded CUDA CAS update refines
one transition of the abstract fail-closed machine. -/
theorem decodeWord_wordStep_encodeSupport
    (number prime : Nat) {support : Support}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    decodeWord
        (wordStep number (encodeSupport support) prime) =
      step number (.valid support) prime := by
  by_cases admissible : StepAdmissible support prime
  · have native :
        NativeStepAdmissible (encodeSupport support) prime :=
      (nativeStepAdmissible_encodeSupport_iff
        productFits countFits).mpr admissible
    have productPositive := admissible.1
    have countBound := admissible.2.1
    have primeBound := admissible.2.2.1
    have nextProductFits := admissible.2.2.2
    have nextCountFits :
        support.distinctCount + 1 < countRadix := by
      norm_num [countRadix] at *
      omega
    have noPoison :=
      poisonSet_encodeSupport productFits countFits
    have productDecoded :
        unpackProduct (encodeSupport support) = support.product := by
      exact unpackProduct_pack productFits
    have countDecoded :
        unpackCount (encodeSupport support) =
          support.distinctCount := by
      exact unpackCount_pack productFits countFits
    have squarefulDecoded :
        unpackSquareful (encodeSupport support) =
          support.squareful := by
      exact unpackSquareful_pack productFits countFits
    simp only [wordStep, noPoison, if_false, native, if_true]
    rw [productDecoded, countDecoded, squarefulDecoded]
    rw [step, if_pos admissible]
    simpa [encodeSupport, mathematicalStep, update] using
      (decodeWord_encodeSupport
        (support := mathematicalStep number support prime)
        nextProductFits nextCountFits)
  · have notNative :
        ¬ NativeStepAdmissible
          (encodeSupport support) prime :=
      mt (nativeStepAdmissible_encodeSupport_iff
        productFits countFits).mp admissible
    have noPoison :=
      poisonSet_encodeSupport productFits countFits
    simp only [wordStep, noPoison, if_false, notNative]
    rw [step, if_neg admissible]
    exact decodeWord_add_poison_encodeSupport
      productFits countFits

/-- A word represents an abstract state when it is either the canonical
well-formed packing of a valid support or carries the native poison bit. -/
inductive Represents : Nat → State → Prop where
  | valid (support : Support)
      (productFits : support.product < productRadix)
      (countFits : support.distinctCount < countRadix) :
      Represents (encodeSupport support) (.valid support)
  | poison {word : Nat} (poisoned : poisonSet word) :
      Represents word .poison

theorem decodeWord_of_represents
    {word : Nat} {state : State}
    (represents : Represents word state) :
    decodeWord word = state := by
  cases represents with
  | valid support productFits countFits =>
      exact decodeWord_encodeSupport productFits countFits
  | poison poisoned =>
      simp [decodeWord, poisoned]

/-- One packed transition preserves the representation relation and realizes
the corresponding abstract guarded transition. -/
theorem wordStep_represents_step
    (number prime : Nat) {word : Nat} {state : State}
    (represents : Represents word state) :
    Represents
      (wordStep number word prime)
      (step number state prime) := by
  cases represents with
  | poison poisoned =>
      simpa [wordStep, poisoned, step] using
        (Represents.poison poisoned)
  | valid support productFits countFits =>
      have noPoison :=
        poisonSet_encodeSupport productFits countFits
      have productDecoded :
          unpackProduct (encodeSupport support) =
            support.product := by
        exact unpackProduct_pack productFits
      have countDecoded :
          unpackCount (encodeSupport support) =
            support.distinctCount := by
        exact unpackCount_pack productFits countFits
      have squarefulDecoded :
          unpackSquareful (encodeSupport support) =
            support.squareful := by
        exact unpackSquareful_pack productFits countFits
      by_cases admissible : StepAdmissible support prime
      · have native :
            NativeStepAdmissible
              (encodeSupport support) prime :=
          (nativeStepAdmissible_encodeSupport_iff
            productFits countFits).mpr admissible
        have nextProductFits := admissible.2.2.2
        have nextCountFits :
            support.distinctCount + 1 < countRadix := by
          have countBound := admissible.2.1
          norm_num [countRadix] at *
          omega
        have wordEq :
            wordStep number (encodeSupport support) prime =
              encodeSupport
                (mathematicalStep number support prime) := by
          simp only [wordStep, noPoison, if_false, native, if_true]
          rw [productDecoded, countDecoded, squarefulDecoded]
          rfl
        rw [wordEq, step, if_pos admissible]
        exact Represents.valid
          (mathematicalStep number support prime)
          nextProductFits nextCountFits
      · have notNative :
            ¬ NativeStepAdmissible
              (encodeSupport support) prime :=
          mt (nativeStepAdmissible_encodeSupport_iff
            productFits countFits).mp admissible
        have wordEq :
            wordStep number (encodeSupport support) prime =
              encodeSupport support + poisonRadix := by
          simp [wordStep, noPoison, notNative]
        rw [wordEq, step, if_neg admissible]
        exact Represents.poison
          (poisonSet_add_encodeSupport productFits countFits)

/-- Pure packed-word execution of an arbitrary event serialization. -/
def wordFold (number : Nat) : List Nat → Nat → Nat
  | [], word => word
  | prime :: rest, word =>
      wordFold number rest (wordStep number word prime)

theorem wordFold_represents_foldEvents
    (number : Nat) (events : List Nat)
    {word : Nat} {state : State}
    (represents : Represents word state) :
    Represents
      (wordFold number events word)
      (foldEvents number events state) := by
  induction events generalizing word state with
  | nil =>
      simpa [wordFold, foldEvents] using represents
  | cons prime rest inductionHypothesis =>
      simp only [wordFold, foldEvents]
      exact inductionHypothesis
        (wordStep_represents_step number prime represents)

/-- End-to-end packed arithmetic theorem for any serialized event list.  No
per-event admissibility assumptions are required: a rejected transition is
represented by the same absorbing poison state on both sides. -/
theorem decodeWord_wordFold_encodeSupport
    (number : Nat) (events : List Nat) {support : Support}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    decodeWord
        (wordFold number events (encodeSupport support)) =
      foldEvents number events (.valid support) := by
  exact decodeWord_of_represents
    (wordFold_represents_foldEvents number events
      (Represents.valid support productFits countFits))

/-- Packed execution over precisely the divisor events selected from a prime
roster. -/
def packedRunSelectedFrom
    (number : Nat) (primes : List Nat) (support : Support) : Nat :=
  wordFold number (selectedDivisors number primes)
    (encodeSupport support)

theorem decodeWord_packedRunSelectedFrom
    (number : Nat) (primes : List Nat) {support : Support}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    decodeWord (packedRunSelectedFrom number primes support) =
      runSelectedFrom number primes support := by
  simpa [packedRunSelectedFrom, runSelectedFrom] using
    (decodeWord_wordFold_encodeSupport
      number (selectedDivisors number primes)
      productFits countFits)

/-- Production-shaped packed run beginning from the exact modulo-900 seed. -/
def packedRunResidueSeeded
    (number : Nat) (suffix : List Nat) : Nat :=
  packedRunSelectedFrom number suffix (residueSeed number)

theorem decodeWord_packedRunResidueSeeded
    (number : Nat) (suffix : List Nat) :
    decodeWord (packedRunResidueSeeded number suffix) =
      runResidueSeeded number suffix := by
  simpa [packedRunResidueSeeded, runResidueSeeded] using
    (decodeWord_packedRunSelectedFrom
      number suffix
      (residueSeed_product_lt_productRadix number)
      (residueSeed_count_lt_countRadix number))

/-- End-to-end packed arithmetic/finalizer theorem.  A complete roster and a
nonpoison decoded result make the packed residue-seeded run exactly Mathlib's
Möbius function. -/
theorem output_decodeWord_packedRunResidueSeeded_eq_moebius
    {number : Nat} {suffix : List Nat}
    (roster :
      CompletePrimeRoster number (seedPrimes ++ suffix))
    (notPoison :
      decodeWord (packedRunResidueSeeded number suffix) ≠ .poison) :
    output number
        (decodeWord (packedRunResidueSeeded number suffix)) =
      ArithmeticFunction.moebius number := by
  rw [decodeWord_packedRunResidueSeeded] at notPoison ⊢
  exact output_runResidueSeeded_eq_moebius roster notPoison

#print axioms encodeSupport_lt_reservedRadix
#print axioms decodeWord_encodeSupport
#print axioms maximumProductGuard_iff
#print axioms nativeStepAdmissible_encodeSupport_iff
#print axioms poisonSet_add_encodeSupport
#print axioms decodeWord_wordStep_encodeSupport
#print axioms decodeWord_of_represents
#print axioms wordStep_represents_step
#print axioms wordFold_represents_foldEvents
#print axioms decodeWord_wordFold_encodeSupport
#print axioms decodeWord_packedRunSelectedFrom
#print axioms decodeWord_packedRunResidueSeeded
#print axioms output_decodeWord_packedRunResidueSeeded_eq_moebius

end SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
