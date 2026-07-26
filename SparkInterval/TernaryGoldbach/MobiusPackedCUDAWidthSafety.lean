/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement

/-!
# Width safety for the packed Möbius CUDA transition

`MobiusPackedCUDABitRefinement` identifies the masks, shifts, and bitwise
assembly in the CUDA product/count CAS with the arithmetic packed transition.
This file proves the complementary machine-width facts.  On every admitted
transition:

* the divisor is nonzero before the native `maximum / prime` expression;
* `product * prime` remains below the 54-bit product radix;
* the incremented count remains below the five-bit count radix;
* the shifted count and complete desired word remain below `2^64`; and
* installing the poison bit on a canonical word also remains below `2^64`.

These results rule out unsigned wrap in the pure expressions.  They do not
identify a compiled instruction sequence or prove the CUDA memory model.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusPackedCUDAWidthSafety

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusGuardedMachine
open SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
open SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement
open SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement

/-- Modulus of the native unsigned 64-bit packed word. -/
def uint64Radix : Nat := 2 ^ 64

/-- An admitted divisor can safely be used as the denominator of the native
`maximum_product = productMask / prime` expression. -/
theorem prime_pos_of_cudaStepAdmissible
    {word prime : Nat}
    (admissible : CUDAStepAdmissible word prime) :
    0 < prime := by
  rcases admissible with ⟨_, _, _, primeBound, _⟩
  omega

/-- The admitted native multiplication cannot overflow even the 54-bit
product field, hence in particular cannot overflow `uint64`. -/
theorem nextProduct_lt_productRadix
    {word prime : Nat}
    (admissible : CUDAStepAdmissible word prime) :
    (word &&& cudaProductMask) * prime < productRadix := by
  rcases admissible with
    ⟨_, _, _, primeBound, productBound⟩
  have primePositive : 0 < prime := by omega
  rw [Nat.le_div_iff_mul_le primePositive] at productBound
  norm_num [cudaProductMask, productRadix] at productBound ⊢
  omega

/-- The increment performed by the CAS remains in the five-bit count field. -/
theorem nextCount_lt_countRadix
    {word prime : Nat}
    (admissible : CUDAStepAdmissible word prime) :
    ((word &&& cudaCountMask) >>> 54) + 1 < countRadix := by
  rcases admissible with ⟨_, _, countBound, _, _⟩
  norm_num [countRadix] at countBound ⊢
  omega

/-- Shifting the admitted incremented count by 54 stays strictly below bit
59, before it is combined with the product and squareful flag. -/
theorem shiftedNextCount_lt_squarefulRadix
    {word prime : Nat}
    (admissible : CUDAStepAdmissible word prime) :
    ((((word &&& cudaCountMask) >>> 54) + 1) <<< 54) <
      squarefulRadix := by
  have countFits := nextCount_lt_countRadix admissible
  norm_num [Nat.shiftLeft_eq, countRadix, squarefulRadix] at countFits ⊢
  omega

/-- The successful desired-word expression is representable in `uint64`.
In fact it remains below the reserved-field radix `2^60`. -/
theorem admittedAssembly_lt_reservedRadix
    {word prime : Nat}
    (admissible : CUDAStepAdmissible word prime) :
    cudaAssembleFromWord word
        ((word &&& cudaProductMask) * prime)
        (((word &&& cudaCountMask) >>> 54) + 1) <
      reservedRadix := by
  have productFits := nextProduct_lt_productRadix admissible
  have countFits := nextCount_lt_countRadix admissible
  rw [cudaAssembleFromWord_eq_pack
    (word := word)
    (productFits := productFits)
    (countFits := countFits)]
  cases unpackSquareful word <;>
    norm_num [pack, productRadix, countRadix, reservedRadix] at productFits countFits ⊢ <;>
    omega

theorem admittedAssembly_lt_uint64Radix
    {word prime : Nat}
    (admissible : CUDAStepAdmissible word prime) :
    cudaAssembleFromWord word
        ((word &&& cudaProductMask) * prime)
        (((word &&& cudaCountMask) >>> 54) + 1) <
      uint64Radix := by
  have belowReserved :=
    admittedAssembly_lt_reservedRadix admissible
  norm_num [reservedRadix, uint64Radix] at belowReserved ⊢
  omega

/-- A canonical valid support word occupies only the low 60 bits. -/
theorem encodeSupport_lt_uint64Radix
    {support : Support}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    encodeSupport support < uint64Radix := by
  have belowReserved :=
    encodeSupport_lt_reservedRadix productFits countFits
  norm_num [reservedRadix, uint64Radix] at belowReserved ⊢
  omega

/-- Installing bit 63 on a canonical support word is ordinary, nonwrapping
addition and remains a valid unsigned 64-bit value. -/
theorem poisonedEncodeSupport_lt_uint64Radix
    {support : Support}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    encodeSupport support + poisonRadix < uint64Radix := by
  have belowReserved :=
    encodeSupport_lt_reservedRadix productFits countFits
  norm_num [reservedRadix, poisonRadix, uint64Radix] at belowReserved ⊢
  omega

/-- Starting from a canonical support word, the complete pure CUDA
transition—success, poison, or already-poisoned early return—never wraps a
64-bit word. -/
theorem cudaDistinctWordStep_encodeSupport_lt_uint64Radix
    (prime : Nat) {support : Support}
    (productFits : support.product < productRadix)
    (countFits : support.distinctCount < countRadix) :
    cudaDistinctWordStep (encodeSupport support) prime <
      uint64Radix := by
  rw [cudaDistinctWordStep_encodeSupport_eq
    prime productFits countFits]
  have noPoison :=
    poisonSet_encodeSupport productFits countFits
  by_cases admissible : StepAdmissible support prime
  · have native :
        NativeStepAdmissible (encodeSupport support) prime :=
      (nativeStepAdmissible_encodeSupport_iff
        productFits countFits).mpr admissible
    have nextProductFits := admissible.2.2.2
    have nextCountFits :
        support.distinctCount + 1 < countRadix := by
      have countBound := admissible.2.1
      norm_num [countRadix] at countBound ⊢
      omega
    simp only [distinctWordStep, noPoison, if_false,
      native, if_true]
    simp only [encodeSupport,
      unpackProduct_pack productFits,
      unpackCount_pack productFits countFits,
      unpackSquareful_pack productFits countFits]
    change
      encodeSupport (updateProductCount support prime) <
        uint64Radix
    exact encodeSupport_lt_uint64Radix
      (support := updateProductCount support prime)
      nextProductFits nextCountFits
  · have notNative :
        ¬ NativeStepAdmissible
            (encodeSupport support) prime :=
      mt (nativeStepAdmissible_encodeSupport_iff
        productFits countFits).mp admissible
    simp only [distinctWordStep, noPoison, if_false, notNative]
    exact poisonedEncodeSupport_lt_uint64Radix
      productFits countFits

#print axioms prime_pos_of_cudaStepAdmissible
#print axioms nextProduct_lt_productRadix
#print axioms nextCount_lt_countRadix
#print axioms shiftedNextCount_lt_squarefulRadix
#print axioms admittedAssembly_lt_uint64Radix
#print axioms poisonedEncodeSupport_lt_uint64Radix
#print axioms cudaDistinctWordStep_encodeSupport_lt_uint64Radix

end SparkInterval.TernaryGoldbach.MobiusPackedCUDAWidthSafety
