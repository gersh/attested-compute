/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Data.Nat.Bitwise
import SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
import SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization

/-!
# Packed-word refinement of the split-square Möbius schedule

The optimized CUDA path performs two different atomic transitions:

1. a guarded CAS updates only the product and distinct-factor fields; then
2. a later `atomicOr` installs bit 59 for every authenticated `p²` strike.

This file proves the corresponding pure packed-word algorithm.  It includes
the bit-level fact used by the `atomicOr`, preserves poison through the square
phase, and shows that every nonpoison result decodes to the exact abstract
split-square run.

The theorem is deliberately below the compiler boundary.  It does not claim
that a particular CUDA binary, stream launch, or device execution realizes
these pure word transitions.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusGuardedMachine
open SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
open SparkInterval.TernaryGoldbach.MobiusPrimeRosterCompleteness
open SparkInterval.TernaryGoldbach.MobiusResidue235
open SparkInterval.TernaryGoldbach.MobiusSplitSquareRealization

/-! ## The bit-59 `atomicOr` -/

/-- Setting the first bit above a number is ordinary addition. -/
theorem lor_two_pow_eq_add_of_lt
    {number bit : Nat} (below : number < 2 ^ bit) :
    number ||| 2 ^ bit = number + 2 ^ bit := by
  induction bit generalizing number with
  | zero =>
      have numberZero : number = 0 := by
        norm_num at below
        omega
      subst number
      decide
  | succ bit inductionHypothesis =>
      have dividedBelow : number.div2 < 2 ^ bit := by
        rw [Nat.div2]
        apply Nat.div_lt_of_lt_mul
        simpa [pow_succ, Nat.mul_comm, Nat.mul_left_comm,
          Nat.mul_assoc] using below
      rw [← Nat.bit_bodd_div2 number]
      rw [show 2 ^ (bit + 1) = Nat.bit false (2 ^ bit) by
        simp [pow_succ, Nat.mul_comm]]
      rw [Nat.lor_bit, inductionHypothesis dividedBelow]
      cases number.bodd <;>
        simp [Nat.mul_add, Nat.mul_comm, Nat.add_assoc, Nat.add_comm]

/-- A packing with bit 59 clear lies strictly below bit 59. -/
theorem lowPack_lt_squarefulRadix
    {product distinctCount : Nat}
    (productFits : product < productRadix)
    (countFits : distinctCount < countRadix) :
    pack product distinctCount false < squarefulRadix := by
  norm_num [pack, productRadix, countRadix, squarefulRadix] at *
  omega

theorem pack_true_eq_pack_false_add_squarefulRadix
    (product distinctCount : Nat) :
    pack product distinctCount true =
      pack product distinctCount false + squarefulRadix := by
  simp [pack, productRadix, countRadix, squarefulRadix]
  omega

/-- Native `atomicOr(word, 1 << 59)` realizes the abstract square mark on
every canonical support word. -/
theorem encodeSupport_lor_squarefulRadix
    {support : Support}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    encodeSupport support ||| squarefulRadix =
      encodeSupport (markSquareful support true) := by
  cases support with
  | mk product distinctCount squareful =>
      cases squareful with
      | false =>
          change
            pack product distinctCount false ||| squarefulRadix =
              pack product distinctCount true
          have lowBound :
              pack product distinctCount false < squarefulRadix :=
            lowPack_lt_squarefulRadix
              (by simpa using productFits)
              (by simpa using countFits)
          rw [show squarefulRadix = 2 ^ 59 by rfl] at lowBound ⊢
          rw [lor_two_pow_eq_add_of_lt lowBound]
          simpa [squarefulRadix] using
            (pack_true_eq_pack_false_add_squarefulRadix
              product distinctCount).symm
      | true =>
          have lowBound :
              pack product distinctCount false < squarefulRadix :=
            lowPack_lt_squarefulRadix
              (by simpa using productFits)
              (by simpa using countFits)
          have lowOr :
              pack product distinctCount false ||| squarefulRadix =
                pack product distinctCount false + squarefulRadix := by
            rw [show squarefulRadix = 2 ^ 59 by rfl] at lowBound ⊢
            exact lor_two_pow_eq_add_of_lt lowBound
          have packTrue :
              pack product distinctCount true =
                pack product distinctCount false |||
                  squarefulRadix := by
            rw [lowOr]
            exact
              pack_true_eq_pack_false_add_squarefulRadix
                product distinctCount
          change
            pack product distinctCount true ||| squarefulRadix =
              pack product distinctCount true
          rw [packTrue, Nat.lor_assoc, Nat.or_self]

/-- A square mark preserves the field bounds of a canonical support. -/
theorem markSquareful_product_fits
    {support : Support} {mark : Bool}
    (productFits : support.product < productRadix) :
    (markSquareful support mark).product < productRadix := by
  exact productFits

theorem markSquareful_count_fits
    {support : Support} {mark : Bool}
    (countFits : support.distinctCount < countRadix) :
    (markSquareful support mark).distinctCount < countRadix := by
  exact countFits

/-- Pure packed-word model of one conditional square strike.  False events
are mathematical no-ops and need not be launched by the native schedule. -/
def squareWordStep (word : Nat) (mark : Bool) : Nat :=
  if mark then word ||| squarefulRadix else word

/-- Abstract decoded transition corresponding to one conditional square
strike. -/
def squareStateStep : State → Bool → State
  | .poison, _ => .poison
  | .valid support, mark =>
      .valid (markSquareful support mark)

theorem squareWordStep_encodeSupport
    {support : Support} (mark : Bool)
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    squareWordStep (encodeSupport support) mark =
      encodeSupport (markSquareful support mark) := by
  cases mark with
  | false =>
      cases support with
      | mk product distinctCount squareful =>
          cases squareful <;> rfl
  | true =>
      exact
        encodeSupport_lor_squarefulRadix productFits countFits

/-! ## The modulo-free guarded CAS -/

/-- Abstract fail-closed transition for the product/count-only phase. -/
def distinctStateStep : State → Nat → State
  | .poison, _ => .poison
  | .valid support, prime =>
      if StepAdmissible support prime then
        .valid (updateProductCount support prime)
      else
        .poison

/-- Pure desired-word calculation in the optimized product/count CAS loop. -/
def distinctWordStep (word prime : Nat) : Nat :=
  if poisonSet word then
    word
  else if NativeStepAdmissible word prime then
    pack
      (unpackProduct word * prime)
      (unpackCount word + 1)
      (unpackSquareful word)
  else
    word + poisonRadix

/-- From a canonical word, the modulo-free CAS transition decodes to exactly
the abstract guarded product/count transition. -/
theorem decodeWord_distinctWordStep_encodeSupport
    (prime : Nat) {support : Support}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    decodeWord (distinctWordStep (encodeSupport support) prime) =
      distinctStateStep (.valid support) prime := by
  by_cases admissible : StepAdmissible support prime
  · have native :
        NativeStepAdmissible (encodeSupport support) prime :=
      (nativeStepAdmissible_encodeSupport_iff
        productFits countFits).mpr admissible
    have nextProductFits := admissible.2.2.2
    have nextCountFits :
        support.distinctCount + 1 < countRadix := by
      have countBound := admissible.2.1
      norm_num [countRadix] at *
      omega
    have noPoison :=
      poisonSet_encodeSupport productFits countFits
    have productDecoded :
        unpackProduct (encodeSupport support) =
          support.product :=
      unpackProduct_pack productFits
    have countDecoded :
        unpackCount (encodeSupport support) =
          support.distinctCount :=
      unpackCount_pack productFits countFits
    have squarefulDecoded :
        unpackSquareful (encodeSupport support) =
          support.squareful :=
      unpackSquareful_pack productFits countFits
    simp only [distinctWordStep, noPoison, if_false,
      native, if_true]
    rw [productDecoded, countDecoded, squarefulDecoded]
    rw [distinctStateStep, if_pos admissible]
    simpa [encodeSupport, updateProductCount] using
      (decodeWord_encodeSupport
        (support := updateProductCount support prime)
        nextProductFits nextCountFits)
  · have notNative :
        ¬ NativeStepAdmissible (encodeSupport support) prime :=
      mt (nativeStepAdmissible_encodeSupport_iff
        productFits countFits).mp admissible
    have noPoison :=
      poisonSet_encodeSupport productFits countFits
    simp only [distinctWordStep, noPoison, if_false,
      notNative]
    rw [distinctStateStep, if_neg admissible]
    exact decodeWord_add_poison_encodeSupport
      productFits countFits

/-! ## A representation closed under both native phases -/

/-- Split execution words are either canonical valid packings or a canonical
packing with the poison bit installed.  Retaining the underlying support in
the poison constructor makes preservation by a later bit-59 OR explicit. -/
inductive SplitRepresents : Nat → State → Prop where
  | valid (support : Support)
      (productFits : support.product < productRadix)
      (countFits : support.distinctCount < countRadix) :
      SplitRepresents (encodeSupport support) (.valid support)
  | poison (support : Support)
      (productFits : support.product < productRadix)
      (countFits : support.distinctCount < countRadix) :
      SplitRepresents
        (encodeSupport support + poisonRadix) .poison

theorem decodeWord_of_splitRepresents
    {word : Nat} {state : State}
    (represents : SplitRepresents word state) :
    decodeWord word = state := by
  cases represents with
  | valid support productFits countFits =>
      exact decodeWord_encodeSupport productFits countFits
  | poison support productFits countFits =>
      exact decodeWord_add_poison_encodeSupport
        productFits countFits

/-- The guarded product/count CAS preserves the split representation. -/
theorem distinctWordStep_splitRepresents
    (prime : Nat) {word : Nat} {state : State}
    (represents : SplitRepresents word state) :
    SplitRepresents
      (distinctWordStep word prime)
      (distinctStateStep state prime) := by
  cases represents with
  | poison support productFits countFits =>
      have poisoned :=
        poisonSet_add_encodeSupport productFits countFits
      simpa [distinctWordStep, poisoned, distinctStateStep] using
        (SplitRepresents.poison support productFits countFits)
  | valid support productFits countFits =>
      have noPoison :=
        poisonSet_encodeSupport productFits countFits
      have productDecoded :
          unpackProduct (encodeSupport support) =
            support.product :=
        unpackProduct_pack productFits
      have countDecoded :
          unpackCount (encodeSupport support) =
            support.distinctCount :=
        unpackCount_pack productFits countFits
      have squarefulDecoded :
          unpackSquareful (encodeSupport support) =
            support.squareful :=
        unpackSquareful_pack productFits countFits
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
            distinctWordStep (encodeSupport support) prime =
              encodeSupport (updateProductCount support prime) := by
          simp only [distinctWordStep, noPoison, if_false,
            native, if_true]
          rw [productDecoded, countDecoded, squarefulDecoded]
          rfl
        rw [wordEq, distinctStateStep, if_pos admissible]
        exact SplitRepresents.valid
          (updateProductCount support prime)
          nextProductFits nextCountFits
      · have notNative :
          ¬ NativeStepAdmissible
              (encodeSupport support) prime :=
          mt (nativeStepAdmissible_encodeSupport_iff
            productFits countFits).mp admissible
        have wordEq :
            distinctWordStep (encodeSupport support) prime =
              encodeSupport support + poisonRadix := by
          simp [distinctWordStep, noPoison, notNative]
        rw [wordEq, distinctStateStep, if_neg admissible]
        exact SplitRepresents.poison
          support productFits countFits

theorem encodeSupport_add_poison_lor_squarefulRadix
    {support : Support}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    (encodeSupport support + poisonRadix) ||| squarefulRadix =
      encodeSupport (markSquareful support true) + poisonRadix := by
  have supportBelowPoison :
      encodeSupport support < poisonRadix := by
    have belowReserved :=
      encodeSupport_lt_reservedRadix productFits countFits
    norm_num [reservedRadix, poisonRadix] at *
    omega
  have markedProductFits :
      (markSquareful support true).product < productRadix :=
    markSquareful_product_fits productFits
  have markedCountFits :
      (markSquareful support true).distinctCount < countRadix :=
    markSquareful_count_fits countFits
  have markedBelowPoison :
      encodeSupport (markSquareful support true) < poisonRadix := by
    have belowReserved :=
      encodeSupport_lt_reservedRadix
        markedProductFits markedCountFits
    norm_num [reservedRadix, poisonRadix] at *
    omega
  have supportPoisonOr :
      encodeSupport support ||| poisonRadix =
        encodeSupport support + poisonRadix := by
    rw [show poisonRadix = 2 ^ 63 by rfl] at supportBelowPoison ⊢
    exact lor_two_pow_eq_add_of_lt supportBelowPoison
  have markedPoisonOr :
      encodeSupport (markSquareful support true) ||| poisonRadix =
        encodeSupport (markSquareful support true) + poisonRadix := by
    rw [show poisonRadix = 2 ^ 63 by rfl] at markedBelowPoison ⊢
    exact lor_two_pow_eq_add_of_lt markedBelowPoison
  rw [← supportPoisonOr, Nat.lor_assoc,
    Nat.lor_comm poisonRadix squarefulRadix,
    ← Nat.lor_assoc,
    encodeSupport_lor_squarefulRadix productFits countFits,
    markedPoisonOr]

/-- A bit-59 `atomicOr` preserves poison and realizes an ordinary square mark
on every valid word. -/
theorem squareWordStep_splitRepresents
    (mark : Bool) {word : Nat} {state : State}
    (represents : SplitRepresents word state) :
    SplitRepresents
      (squareWordStep word mark)
      (squareStateStep state mark) := by
  cases represents with
  | valid support productFits countFits =>
      rw [squareWordStep_encodeSupport mark
        productFits countFits]
      exact SplitRepresents.valid
        (markSquareful support mark)
        (markSquareful_product_fits productFits)
        (markSquareful_count_fits countFits)
  | poison support productFits countFits =>
      cases mark with
      | false =>
          change
            SplitRepresents
              (encodeSupport support + poisonRadix) .poison
          exact SplitRepresents.poison support
            productFits countFits
      | true =>
          rw [squareWordStep,
            if_pos (by decide),
            encodeSupport_add_poison_lor_squarefulRadix
              productFits countFits]
          exact SplitRepresents.poison
            (markSquareful support true)
            (markSquareful_product_fits productFits)
            (markSquareful_count_fits countFits)

/-! ## End-to-end packed split folds -/

def distinctWordRun : Nat → List SplitEvent → Nat
  | word, [] => word
  | word, event :: events =>
      distinctWordRun
        (distinctWordStep word event.prime) events

def distinctStateRun : State → List SplitEvent → State
  | state, [] => state
  | state, event :: events =>
      distinctStateRun
        (distinctStateStep state event.prime) events

def squareWordRun : Nat → List SplitEvent → Nat
  | word, [] => word
  | word, event :: events =>
      squareWordRun
        (squareWordStep word event.dividesSquare) events

def squareStateRun : State → List SplitEvent → State
  | state, [] => state
  | state, event :: events =>
      squareStateRun
        (squareStateStep state event.dividesSquare)
        events

def packedSplitRun
    (support : Support) (events : List SplitEvent) : Nat :=
  squareWordRun
    (distinctWordRun (encodeSupport support) events) events

def guardedSplitRun
    (support : Support) (events : List SplitEvent) : State :=
  squareStateRun
    (distinctStateRun (.valid support) events) events

theorem distinctWordRun_splitRepresents
    (events : List SplitEvent) {word : Nat} {state : State}
    (represents : SplitRepresents word state) :
    SplitRepresents
      (distinctWordRun word events)
      (distinctStateRun state events) := by
  induction events generalizing word state with
  | nil =>
      simpa [distinctWordRun, distinctStateRun] using represents
  | cons event events inductionHypothesis =>
      simp only [distinctWordRun, distinctStateRun]
      exact inductionHypothesis
        (distinctWordStep_splitRepresents event.prime represents)

theorem squareWordRun_splitRepresents
    (events : List SplitEvent) {word : Nat} {state : State}
    (represents : SplitRepresents word state) :
    SplitRepresents
      (squareWordRun word events)
      (squareStateRun state events) := by
  induction events generalizing word state with
  | nil =>
      simpa [squareWordRun, squareStateRun] using represents
  | cons event events inductionHypothesis =>
      simp only [squareWordRun, squareStateRun]
      exact inductionHypothesis
        (squareWordStep_splitRepresents
          event.dividesSquare represents)

theorem packedSplitRun_splitRepresents
    {support : Support} (events : List SplitEvent)
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    SplitRepresents
      (packedSplitRun support events)
      (guardedSplitRun support events) := by
  exact squareWordRun_splitRepresents events
    (distinctWordRun_splitRepresents events
      (SplitRepresents.valid support productFits countFits))

@[simp] theorem distinctStateRun_poison
    (events : List SplitEvent) :
    distinctStateRun .poison events = .poison := by
  induction events with
  | nil =>
      rfl
  | cons event events inductionHypothesis =>
      simpa [distinctStateRun, distinctStateStep] using
        inductionHypothesis

/-- The guarded distinct phase either poisons or produces exactly the
unguarded product/count phase. -/
theorem distinctStateRun_eq_poison_or_valid
    (support : Support) (events : List SplitEvent) :
    distinctStateRun (.valid support) events = .poison ∨
      distinctStateRun (.valid support) events =
        .valid (distinctRun support events) := by
  induction events generalizing support with
  | nil =>
      exact Or.inr rfl
  | cons event events inductionHypothesis =>
      by_cases admissible :
          StepAdmissible support event.prime
      · simpa [distinctStateRun, distinctStateStep, admissible,
          distinctRun, applyDistinctEvent] using
          inductionHypothesis
            (updateProductCount support event.prime)
      · exact Or.inl (by
          simp [distinctStateRun, distinctStateStep, admissible])

@[simp] theorem squareStateRun_poison
    (events : List SplitEvent) :
    squareStateRun .poison events = .poison := by
  induction events with
  | nil =>
      rfl
  | cons event events inductionHypothesis =>
      simpa [squareStateRun, squareStateStep] using
        inductionHypothesis

theorem squareStateRun_valid
    (support : Support) (events : List SplitEvent) :
    squareStateRun (.valid support) events =
      .valid (squareRun support events) := by
  induction events generalizing support with
  | nil =>
      rfl
  | cons event events inductionHypothesis =>
      simpa [squareStateRun, squareStateStep,
        squareRun, applySquareEvent] using
        inductionHypothesis
          (markSquareful support event.dividesSquare)

/-- The guarded split run is either poison or exactly the unguarded
mathematical split run. -/
theorem guardedSplitRun_eq_poison_or_valid
    (support : Support) (events : List SplitEvent) :
    guardedSplitRun support events = .poison ∨
      guardedSplitRun support events =
        .valid (splitRun support events) := by
  rcases distinctStateRun_eq_poison_or_valid support events with
    poisoned | valid
  · exact Or.inl (by
      simp [guardedSplitRun, poisoned])
  · exact Or.inr (by
      rw [guardedSplitRun, valid,
        squareStateRun_valid, splitRun])

/-- A nonpoison packed result is exactly the optimized abstract split run. -/
theorem decodeWord_packedSplitRun_eq_valid_of_ne_poison
    {support : Support} (events : List SplitEvent)
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix)
    (notPoison :
      decodeWord (packedSplitRun support events) ≠ .poison) :
    decodeWord (packedSplitRun support events) =
      .valid (splitRun support events) := by
  have decoded :
      decodeWord (packedSplitRun support events) =
        guardedSplitRun support events :=
    decodeWord_of_splitRepresents
      (packedSplitRun_splitRepresents events
        productFits countFits)
  rw [decoded] at notPoison ⊢
  rcases guardedSplitRun_eq_poison_or_valid support events with
    poisoned | exact
  · exact (notPoison poisoned).elim
  · exact exact

/-- Production-shaped packed split execution from the exact modulo-900
residue seed. -/
def packedSplitRunResidueSeeded
    (number : Nat) (suffix : List Nat) : Nat :=
  packedSplitRun (residueSeed number)
    (rowSplitEvents number suffix)

/-- End-to-end pure packed-word theorem for the optimized split-square
algorithm.  A complete roster and a nonpoison decoded result suffice. -/
theorem output_decodeWord_packedSplitRunResidueSeeded_eq_moebius
    {number : Nat} {suffix : List Nat}
    (roster :
      CompletePrimeRoster number (seedPrimes ++ suffix))
    (notPoison :
      decodeWord
        (packedSplitRunResidueSeeded number suffix) ≠ .poison) :
    output number
        (decodeWord
          (packedSplitRunResidueSeeded number suffix)) =
      ArithmeticFunction.moebius number := by
  have decoded :
      decodeWord
          (packedSplitRunResidueSeeded number suffix) =
        .valid
          (splitRun (residueSeed number)
            (rowSplitEvents number suffix)) := by
    simpa [packedSplitRunResidueSeeded] using
      (decodeWord_packedSplitRun_eq_valid_of_ne_poison
        (support := residueSeed number)
        (rowSplitEvents number suffix)
        (residueSeed_product_lt_productRadix number)
        (residueSeed_count_lt_countRadix number)
        notPoison)
  rw [decoded, output,
    splitRun_residueSeeded_eq_suffixFold,
    ← fold_prefix_suffix_eq_residueSeed]
  exact roster.finalize_foldSupport_eq_moebius

#print axioms lor_two_pow_eq_add_of_lt
#print axioms encodeSupport_lor_squarefulRadix
#print axioms decodeWord_distinctWordStep_encodeSupport
#print axioms distinctWordStep_splitRepresents
#print axioms encodeSupport_add_poison_lor_squarefulRadix
#print axioms squareWordStep_splitRepresents
#print axioms packedSplitRun_splitRepresents
#print axioms decodeWord_packedSplitRun_eq_valid_of_ne_poison
#print axioms
  output_decodeWord_packedSplitRunResidueSeeded_eq_moebius

end SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement
