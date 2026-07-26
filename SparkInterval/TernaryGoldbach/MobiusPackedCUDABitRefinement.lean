/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Data.Nat.Bitwise
import SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement

/-!
# Pure CUDA bit-expression refinement for packed Möbius support

`MobiusPackedSplitSquareRefinement` proves the arithmetic packed-word
algorithm.  The CUDA source spells the same operations with masks, shifts,
bitwise OR, and bitwise AND.  This file closes that additional pure
expression layer:

* the CUDA product/count/reserved/poison masks recover the arithmetic fields;
* the CUDA malformed-word guard is exactly `NativeStepAdmissible`;
* the bitwise desired-word assembly is exactly `pack`; and
* the complete product/count CAS expression preserves the same representation
  relation as the arithmetic split-square step.

These are unbounded `Nat` bit-expression theorems with explicit field bounds.
They do not identify compiled C++/CUDA instructions, atomics, memory order,
stream order, or a physical execution with the pure definitions.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusGuardedMachine
open SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
open SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement

/-! ## Exact native masks and field extraction -/

/-- The C++ expression `(2^width - 1) << shift`. -/
def shiftedMask (width shift : Nat) : Nat :=
  (2 ^ width - 1) <<< shift

def cudaProductMask : Nat := 2 ^ 54 - 1
def cudaCountMask : Nat := shiftedMask 5 54
def cudaSquarefulBit : Nat := 2 ^ 59
def cudaReservedMask : Nat := shiftedMask 3 60
def cudaPoisonBit : Nat := 2 ^ 63

@[simp] theorem cudaProductMask_eq_productMask :
    cudaProductMask = productMask := by
  rfl

@[simp] theorem cudaSquarefulBit_eq_squarefulRadix :
    cudaSquarefulBit = squarefulRadix := by
  rfl

@[simp] theorem cudaPoisonBit_eq_poisonRadix :
    cudaPoisonBit = poisonRadix := by
  rfl

/-- Masking a shifted finite-width field and shifting it back recovers the
corresponding arithmetic quotient and remainder. -/
theorem extract_shiftedMask_eq
    (word width shift : Nat) :
    (word &&& shiftedMask width shift) >>> shift =
      (word / 2 ^ shift) % 2 ^ width := by
  rw [← Nat.shiftRight_eq_div_pow word shift]
  rw [← Nat.and_two_pow_sub_one_eq_mod]
  apply Nat.eq_of_testBit_eq
  intro bit
  rw [Nat.testBit_shiftRight, Nat.testBit_land,
    Nat.testBit_land, Nat.testBit_shiftRight]
  simp [shiftedMask, Nat.testBit_shiftLeft,
    Nat.testBit_two_pow_sub_one]

/-- The unshifted masked word is the recovered field shifted back into its
native position. -/
theorem land_shiftedMask_eq
    (word width shift : Nat) :
    word &&& shiftedMask width shift =
      (((word / 2 ^ shift) % 2 ^ width) <<< shift) := by
  apply Nat.eq_of_testBit_eq
  intro bit
  rw [Nat.testBit_land]
  simp only [shiftedMask, Nat.testBit_shiftLeft,
    Nat.testBit_two_pow_sub_one]
  by_cases inFieldOrAbove : shift ≤ bit
  · have shiftSub : shift + (bit - shift) = bit :=
      Nat.add_sub_of_le inFieldOrAbove
    simp [inFieldOrAbove, ← Nat.shiftRight_eq_div_pow,
      Nat.testBit_shiftRight,
      ← Nat.and_two_pow_sub_one_eq_mod,
      Nat.testBit_two_pow_sub_one, shiftSub]
  · simp [inFieldOrAbove]

theorem cudaProduct_eq_unpackProduct (word : Nat) :
    word &&& cudaProductMask = unpackProduct word := by
  rw [cudaProductMask, Nat.and_two_pow_sub_one_eq_mod]
  rfl

theorem cudaCount_eq_unpackCount (word : Nat) :
    (word &&& cudaCountMask) >>> 54 =
      unpackCount word := by
  rw [cudaCountMask, extract_shiftedMask_eq]
  rfl

theorem unpackSquareful_eq_testBit (word : Nat) :
    unpackSquareful word = word.testBit 59 := by
  simp [unpackSquareful, squarefulRadix, Nat.testBit,
    Nat.shiftRight_eq_div_pow, Nat.one_and_eq_mod_two]

theorem cudaSquareMask_eq (word : Nat) :
    word &&& cudaSquarefulBit =
      if unpackSquareful word then cudaSquarefulBit else 0 := by
  rw [cudaSquarefulBit]
  rw [Nat.and_two_pow]
  rw [← unpackSquareful_eq_testBit]
  cases unpackSquareful word <;> rfl

theorem cudaReserved_nonzero_iff (word : Nat) :
    (word &&& cudaReservedMask) ≠ 0 ↔ reservedSet word := by
  rw [cudaReservedMask, land_shiftedMask_eq]
  simp [reservedSet, reservedRadix, Nat.shiftLeft_eq]

theorem cudaPoison_nonzero_iff (word : Nat) :
    (word &&& cudaPoisonBit) ≠ 0 ↔ poisonSet word := by
  have maskIdentity :
      cudaPoisonBit = shiftedMask 1 63 := by
    norm_num [cudaPoisonBit, shiftedMask, Nat.shiftLeft_eq]
  rw [maskIdentity, land_shiftedMask_eq]
  simp [poisonSet, poisonRadix, Nat.shiftLeft_eq]

/-! ## Exact native guard -/

/-- Positive form of the checks guarded by `if (!malformed)` in the CUDA
product/count CAS loop. -/
def CUDAStepAdmissible (word prime : Nat) : Prop :=
  word &&& cudaReservedMask = 0 ∧
    word &&& cudaProductMask ≠ 0 ∧
    (word &&& cudaCountMask) >>> 54 < 13 ∧
    2 ≤ prime ∧
    word &&& cudaProductMask ≤ cudaProductMask / prime

instance (word prime : Nat) :
    Decidable (CUDAStepAdmissible word prime) := by
  unfold CUDAStepAdmissible
  infer_instance

/-- The exact mask/shift guard is the arithmetic packed-word guard. -/
theorem cudaStepAdmissible_iff_nativeStepAdmissible
    (word prime : Nat) :
    CUDAStepAdmissible word prime ↔
      NativeStepAdmissible word prime := by
  rw [CUDAStepAdmissible, NativeStepAdmissible]
  rw [cudaProduct_eq_unpackProduct,
    cudaCount_eq_unpackCount,
    cudaProductMask_eq_productMask]
  constructor
  · rintro ⟨reservedZero, productNonzero, countBound,
      primeBound, productBound⟩
    exact ⟨
      (cudaReserved_nonzero_iff word).not.mp
        (not_ne_iff.mpr reservedZero),
      productNonzero, countBound, primeBound, productBound⟩
  · rintro ⟨reservedClear, productNonzero, countBound,
      primeBound, productBound⟩
    exact ⟨
      not_ne_iff.mp
        ((cudaReserved_nonzero_iff word).not.mpr reservedClear),
      productNonzero, countBound, primeBound, productBound⟩

/-! ## Exact desired-word assembly -/

/-- A low field and an arbitrary field shifted above it combine by bitwise OR
as ordinary addition. -/
theorem lor_mul_two_pow_eq_add_of_lt
    {low high shift : Nat} (below : low < 2 ^ shift) :
    low ||| high * 2 ^ shift =
      low + high * 2 ^ shift := by
  induction shift generalizing low with
  | zero =>
      have lowZero : low = 0 := by
        norm_num at below
        omega
      subst low
      simp
  | succ shift inductionHypothesis =>
      have dividedBelow : low.div2 < 2 ^ shift := by
        rw [Nat.div2]
        apply Nat.div_lt_of_lt_mul
        simpa [pow_succ, Nat.mul_comm, Nat.mul_left_comm,
          Nat.mul_assoc] using below
      rw [← Nat.bit_bodd_div2 low]
      rw [show high * 2 ^ (shift + 1) =
          Nat.bit false (high * 2 ^ shift) by
        simp [pow_succ, Nat.mul_comm, Nat.mul_left_comm]]
      rw [Nat.lor_bit, inductionHypothesis dividedBelow]
      cases low.bodd <;>
        simp [Nat.mul_add, Nat.mul_comm, Nat.mul_left_comm,
          Nat.add_assoc, Nat.add_comm]

/-- Pure expression corresponding to the native field assembly, with the
old squareful state represented as a Boolean. -/
def cudaAssemble
    (product count : Nat) (squareful : Bool) : Nat :=
  product ||| (count <<< 54) |||
    (if squareful then cudaSquarefulBit else 0)

theorem cudaAssemble_eq_pack
    {product count : Nat} {squareful : Bool}
    (productFits : product < productRadix)
    (countFits : count < countRadix) :
    cudaAssemble product count squareful =
      pack product count squareful := by
  have productOrCount :
      product ||| count * 2 ^ 54 =
        product + count * 2 ^ 54 :=
    lor_mul_two_pow_eq_add_of_lt (by
      simpa [productRadix] using productFits)
  have lowBound :
      product + count * 2 ^ 54 < 2 ^ 59 := by
    norm_num [productRadix, countRadix] at productFits countFits ⊢
    omega
  cases squareful with
  | false =>
      rw [cudaAssemble, if_neg (by decide),
        Nat.shiftLeft_eq, Nat.or_zero, productOrCount]
      simp [pack, productRadix, countRadix]
      omega
  | true =>
      rw [cudaAssemble, if_pos (by decide),
        Nat.shiftLeft_eq, productOrCount]
      rw [show cudaSquarefulBit = 2 ^ 59 by rfl] at ⊢
      rw [lor_two_pow_eq_add_of_lt lowBound]
      simp [pack, productRadix, countRadix]
      omega

/-- The CUDA desired word uses the old word's masked square bit directly. -/
def cudaAssembleFromWord
    (word product count : Nat) : Nat :=
  product ||| (count <<< 54) |||
    (word &&& cudaSquarefulBit)

theorem cudaAssembleFromWord_eq_pack
    (word : Nat) {product count : Nat}
    (productFits : product < productRadix)
    (countFits : count < countRadix) :
    cudaAssembleFromWord word product count =
      pack product count (unpackSquareful word) := by
  rw [cudaAssembleFromWord, cudaSquareMask_eq]
  exact cudaAssemble_eq_pack productFits countFits

/-! ## Complete pure CUDA product/count step -/

/-- Exact pure expression of `mark_one_fused_distinct_divisor` between a
successful CAS load and its desired-word calculation. -/
def cudaDistinctWordStep (word prime : Nat) : Nat :=
  if word &&& cudaPoisonBit ≠ 0 then
    word
  else if CUDAStepAdmissible word prime then
    cudaAssembleFromWord word
      ((word &&& cudaProductMask) * prime)
      (((word &&& cudaCountMask) >>> 54) + 1)
  else
    word ||| cudaPoisonBit

/-- On every canonical valid word, the exact CUDA bit expression equals the
arithmetic packed split-square transition. -/
theorem cudaDistinctWordStep_encodeSupport_eq
    (prime : Nat) {support : Support}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    cudaDistinctWordStep (encodeSupport support) prime =
      distinctWordStep (encodeSupport support) prime := by
  have noPoison :
      ¬ poisonSet (encodeSupport support) :=
    poisonSet_encodeSupport productFits countFits
  have cudaNoPoison :
      ¬ (encodeSupport support &&& cudaPoisonBit ≠ 0) :=
    mt (cudaPoison_nonzero_iff _).mp noPoison
  have productDecoded :
      encodeSupport support &&& cudaProductMask =
        support.product := by
    rw [cudaProduct_eq_unpackProduct]
    exact unpackProduct_pack productFits
  have countDecoded :
      (encodeSupport support &&& cudaCountMask) >>> 54 =
        support.distinctCount := by
    rw [cudaCount_eq_unpackCount]
    exact unpackCount_pack productFits countFits
  have squarefulDecoded :
      unpackSquareful (encodeSupport support) =
        support.squareful :=
    unpackSquareful_pack productFits countFits
  have arithmeticProductDecoded :
      unpackProduct (encodeSupport support) =
        support.product :=
    unpackProduct_pack productFits
  have arithmeticCountDecoded :
      unpackCount (encodeSupport support) =
        support.distinctCount :=
    unpackCount_pack productFits countFits
  by_cases admissible : StepAdmissible support prime
  · have native :
        NativeStepAdmissible (encodeSupport support) prime :=
      (nativeStepAdmissible_encodeSupport_iff
        productFits countFits).mpr admissible
    have cuda :
        CUDAStepAdmissible
            (encodeSupport support) prime :=
      (cudaStepAdmissible_iff_nativeStepAdmissible _ _).mpr
        native
    have nextProductFits := admissible.2.2.2
    have nextCountFits :
        support.distinctCount + 1 < countRadix := by
      have countBound := admissible.2.1
      norm_num [countRadix] at *
      omega
    simp only [cudaDistinctWordStep, cudaNoPoison,
      if_false, cuda, if_true, distinctWordStep,
      noPoison, native]
    rw [productDecoded, countDecoded,
      cudaAssembleFromWord_eq_pack
        (productFits := nextProductFits)
        (countFits := nextCountFits),
      squarefulDecoded, arithmeticProductDecoded,
      arithmeticCountDecoded]
  · have notNative :
        ¬ NativeStepAdmissible
            (encodeSupport support) prime :=
      mt (nativeStepAdmissible_encodeSupport_iff
        productFits countFits).mp admissible
    have notCuda :
        ¬ CUDAStepAdmissible
            (encodeSupport support) prime :=
      mt (cudaStepAdmissible_iff_nativeStepAdmissible _ _).mp
        notNative
    have belowPoison :
        encodeSupport support < poisonRadix := by
      have belowReserved :=
        encodeSupport_lt_reservedRadix productFits countFits
      norm_num [reservedRadix, poisonRadix] at *
      omega
    have poisonOr :
        encodeSupport support ||| cudaPoisonBit =
          encodeSupport support + poisonRadix := by
      rw [show cudaPoisonBit = 2 ^ 63 by rfl]
      rw [show poisonRadix = 2 ^ 63 by rfl] at belowPoison ⊢
      exact lor_two_pow_eq_add_of_lt belowPoison
    simp only [cudaDistinctWordStep, cudaNoPoison, if_false,
      notCuda, distinctWordStep, noPoison, notNative]
    exact poisonOr

/-- The exact CUDA bit expression preserves the same valid/poison
representation as the arithmetic packed algorithm. -/
theorem cudaDistinctWordStep_splitRepresents
    (prime : Nat) {word : Nat} {state : State}
    (represents : SplitRepresents word state) :
    SplitRepresents
      (cudaDistinctWordStep word prime)
      (distinctStateStep state prime) := by
  cases represents with
  | valid support productFits countFits =>
      rw [cudaDistinctWordStep_encodeSupport_eq
        prime productFits countFits]
      exact distinctWordStep_splitRepresents prime
        (SplitRepresents.valid support productFits countFits)
  | poison support productFits countFits =>
      have poisoned :
          poisonSet (encodeSupport support + poisonRadix) :=
        poisonSet_add_encodeSupport productFits countFits
      have cudaPoisoned :
          (encodeSupport support + poisonRadix) &&&
              cudaPoisonBit ≠ 0 :=
        (cudaPoison_nonzero_iff _).mpr poisoned
      change
        SplitRepresents
          (cudaDistinctWordStep
            (encodeSupport support + poisonRadix) prime)
          .poison
      rw [cudaDistinctWordStep, if_pos cudaPoisoned]
      exact SplitRepresents.poison support
        productFits countFits

#print axioms extract_shiftedMask_eq
#print axioms land_shiftedMask_eq
#print axioms cudaProduct_eq_unpackProduct
#print axioms cudaCount_eq_unpackCount
#print axioms cudaReserved_nonzero_iff
#print axioms cudaPoison_nonzero_iff
#print axioms cudaStepAdmissible_iff_nativeStepAdmissible
#print axioms cudaAssemble_eq_pack
#print axioms cudaAssembleFromWord_eq_pack
#print axioms cudaDistinctWordStep_encodeSupport_eq
#print axioms cudaDistinctWordStep_splitRepresents

end SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement
