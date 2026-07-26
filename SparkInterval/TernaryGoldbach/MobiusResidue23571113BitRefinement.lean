/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement
import SparkInterval.TernaryGoldbach.MobiusResidue23571113

/-!
# Literal p13 initializer bit-expression refinement

This module models the exact product/count masks, shifts, field assembly,
and conditional square-bit OR used by the qualification-only p13 CUDA
initializer.  It proves that applying that expression to the canonical p11
word gives `residueSeed23571113Word`.

The theorem is pure base-trio arithmetic.  It does not prove that CUDA source,
a compiler, a launch with `blockDim.x = 256`, or physical GPU execution
implements the expression.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusResidue23571113BitRefinement

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusPackedGuardedRefinement
open SparkInterval.TernaryGoldbach.MobiusPackedSplitSquareRefinement
open SparkInterval.TernaryGoldbach.MobiusPackedCUDABitRefinement
open SparkInterval.TernaryGoldbach.MobiusResidue235
open SparkInterval.TernaryGoldbach.MobiusResidue235711
open SparkInterval.TernaryGoldbach.MobiusResidue23571113

/-- Exact mask/shift/OR expression used to extend a canonical p11 word by
the p=13 contribution. -/
def cudaThirteenInitializerStep (n word : Nat) : Nat :=
  let residue := n % thirteenSquareModulus
  if residue % 13 = 0 then
    let product := (word &&& cudaProductMask) * 13
    let count := ((word &&& cudaCountMask) >>> 54) + 1
    let assembled := cudaAssembleFromWord word product count
    if residue = 0 then
      assembled ||| cudaSquarefulBit
    else
      assembled
  else
    word

/-- On a canonical p11 initializer word, the literal p13 mask/shift/OR
expression is exactly the canonical p13 initializer word. -/
theorem cudaThirteenInitializerStep_p11_eq
    (n : Nat) :
    cudaThirteenInitializerStep n (residueSeed235711Word n) =
      residueSeed23571113Word n := by
  let oldSupport := residueSeed235711 n
  let oldWord := residueSeed235711Word n
  have oldProduct :
      oldWord &&& cudaProductMask = oldSupport.product := by
    rw [cudaProduct_eq_unpackProduct]
    exact unpackProduct_residueSeed235711Word n
  have oldCount :
      (oldWord &&& cudaCountMask) >>> 54 =
        oldSupport.distinctCount := by
    rw [cudaCount_eq_unpackCount]
    exact unpackCount_residueSeed235711Word n
  have oldSquare :
      unpackSquareful oldWord = oldSupport.squareful := by
    exact unpackSquareful_residueSeed235711Word n
  have newProductFits :
      oldSupport.product * 13 < productRadix := by
    have := residueSeed235711_product_le_twoThousandThreeHundredTen n
    simp only [oldSupport]
    norm_num [productRadix] at this ⊢
    omega
  have newCountFits :
      oldSupport.distinctCount + 1 < countRadix := by
    have := residueSeed235711_count_le_five n
    simp only [oldSupport]
    norm_num [countRadix] at this ⊢
    omega
  have assembled :
      cudaAssembleFromWord oldWord
          (oldSupport.product * 13)
          (oldSupport.distinctCount + 1) =
        encodeSupport
          { product := oldSupport.product * 13
            distinctCount := oldSupport.distinctCount + 1
            squareful := oldSupport.squareful } := by
    rw [cudaAssembleFromWord_eq_pack oldWord
      newProductFits newCountFits, oldSquare]
    rfl
  have marked :
      encodeSupport
          { product := oldSupport.product * 13
            distinctCount := oldSupport.distinctCount + 1
            squareful := oldSupport.squareful } |||
          cudaSquarefulBit =
        encodeSupport
          { product := oldSupport.product * 13
            distinctCount := oldSupport.distinctCount + 1
            squareful := true } := by
    rw [cudaSquarefulBit_eq_squarefulRadix]
    simpa [markSquareful] using
      (encodeSupport_lor_squarefulRadix
        (support :=
          { product := oldSupport.product * 13
            distinctCount := oldSupport.distinctCount + 1
            squareful := oldSupport.squareful })
        newProductFits newCountFits)
  rw [cudaThirteenInitializerStep]
  change
    (if n % thirteenSquareModulus % 13 = 0 then
      let product := (oldWord &&& cudaProductMask) * 13
      let count := ((oldWord &&& cudaCountMask) >>> 54) + 1
      let assembled := cudaAssembleFromWord oldWord product count
      if n % thirteenSquareModulus = 0 then
        assembled ||| cudaSquarefulBit
      else assembled
    else oldWord) =
      residueSeed23571113Word n
  by_cases hdiv : 13 ∣ n
  · have hbranch :
        n % thirteenSquareModulus % 13 = 0 := by
      rw [← Nat.dvd_iff_mod_eq_zero]
      exact (thirteen_dvd_mod169_iff n).mpr hdiv
    rw [if_pos hbranch, oldProduct, oldCount]
    by_cases hsquare : 13 * 13 ∣ n
    · have hzero :
          n % thirteenSquareModulus = 0 := by
        have hsquare' : thirteenSquareModulus ∣ n := by
          simpa [thirteenSquareModulus] using hsquare
        exact Nat.dvd_iff_mod_eq_zero.mp hsquare'
      rw [if_pos hzero, assembled, marked]
      unfold residueSeed23571113Word
      rw [residueSeed23571113_product_eq,
        residueSeed23571113_count_eq,
        residueSeed23571113_squareful_eq]
      simp [hdiv, hsquare, encodeSupport, oldSupport]
    · have hzero :
          n % thirteenSquareModulus ≠ 0 := by
        intro zero
        apply hsquare
        have hsquare' : thirteenSquareModulus ∣ n :=
          Nat.dvd_iff_mod_eq_zero.mpr zero
        simpa [thirteenSquareModulus] using hsquare'
      rw [if_neg hzero, assembled]
      unfold residueSeed23571113Word
      rw [residueSeed23571113_product_eq,
        residueSeed23571113_count_eq,
        residueSeed23571113_squareful_eq]
      simp [hdiv, hsquare, encodeSupport, oldSupport]
  · have hbranch :
        n % thirteenSquareModulus % 13 ≠ 0 := by
      intro zero
      apply hdiv
      exact (thirteen_dvd_mod169_iff n).mp
        (Nat.dvd_iff_mod_eq_zero.mpr zero)
    rw [if_neg hbranch]
    have hsquare : ¬ 13 * 13 ∣ n := by
      intro square
      exact hdiv (dvd_trans (by norm_num) square)
    unfold residueSeed23571113Word
    rw [residueSeed23571113_product_eq,
      residueSeed23571113_count_eq,
      residueSeed23571113_squareful_eq]
    simp [hdiv, hsquare, oldWord,
      residueSeed235711Word]

#print axioms cudaThirteenInitializerStep_p11_eq

end SparkInterval.TernaryGoldbach.MobiusResidue23571113BitRefinement
