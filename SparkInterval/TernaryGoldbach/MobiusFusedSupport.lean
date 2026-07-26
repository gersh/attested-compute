/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Tactic

/-!
# Lossless 64-bit support layout for the segmented Möbius sieve

For `n ≤ 10^16`, a product of distinct prime divisors of `n` is below
`2^54`.  The optimized CUDA prototype can therefore store:

* the product in bits `0..53`;
* a five-bit distinct-prime count in bits `54..58`; and
* the squareful flag in bit `59`.

The theorems here prove the arithmetic layout is injective and below `2^60`
under the explicit field bounds.  They do not claim that a CUDA CAS loop
implements this model or that the runtime count bound has been established;
those remain separate native-refinement obligations.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusFusedSupport

def productRadix : Nat := 2 ^ 54
def countRadix : Nat := 32
def squarefulRadix : Nat := 2 ^ 59
def wordLimit : Nat := 2 ^ 64
def sourceLimit : Nat := 10_000_000_000_000_000
def maximumSegmentRows : Nat := 100_000_000

/-- Mathematical state accumulated by the fused segmented-sieve updates. -/
structure Support where
  product : Nat
  distinctCount : Nat
  squareful : Bool
  deriving DecidableEq

/-- Arithmetic meaning of the proposed packed support word. -/
def pack (product distinctCount : Nat) (squareful : Bool) : Nat :=
  product +
    productRadix *
      (distinctCount + countRadix * if squareful then 1 else 0)

/-- One mathematical distinct-prime update.  The native CAS loop is intended
to linearize exactly this operation. -/
def update (support : Support) (prime : Nat)
    (dividesSquare : Bool) : Support where
  product := support.product * prime
  distinctCount := support.distinctCount + 1
  squareful := support.squareful || dividesSquare

/-- Product/count portion of a distinct-prime update.  This is the
mathematical operation performed by the proposed modulo-free divisor pass. -/
def updateProductCount (support : Support) (prime : Nat) : Support where
  product := support.product * prime
  distinctCount := support.distinctCount + 1
  squareful := support.squareful

/-- Idempotent square-divisibility mark used by a separate `p²`-multiple
pass. -/
def markSquareful (support : Support) (dividesSquare : Bool) : Support where
  product := support.product
  distinctCount := support.distinctCount
  squareful := support.squareful || dividesSquare

/-- Splitting one update into a divisor pass and a square pass is exact. -/
theorem update_eq_markSquareful_updateProductCount
    (support : Support) (prime : Nat) (dividesSquare : Bool) :
    update support prime dividesSquare =
      markSquareful (updateProductCount support prime) dividesSquare := by
  cases support
  rfl

/-- A square mark commutes with every product/count update.  Hence all
square marks may be moved to a later kernel without changing the support
state, provided both passes enumerate the same mathematical events. -/
theorem markSquareful_updateProductCount_comm
    (support : Support) (prime : Nat) (dividesSquare : Bool) :
    markSquareful (updateProductCount support prime) dividesSquare =
      updateProductCount (markSquareful support dividesSquare) prime := by
  cases support
  rfl

/-- Square marks are associative and order-independent. -/
theorem markSquareful_markSquareful_comm
    (support : Support) (first second : Bool) :
    markSquareful (markSquareful support first) second =
      markSquareful (markSquareful support second) first := by
  cases support with
  | mk product distinctCount squareful =>
      cases squareful <;> cases first <;> cases second <;>
        rfl

/-- Product field recovered by the native low-bit mask. -/
def unpackProduct (word : Nat) : Nat :=
  word % productRadix

/-- Distinct-factor count recovered after shifting away the product field. -/
def unpackCount (word : Nat) : Nat :=
  (word / productRadix) % countRadix

/-- Squareful bit recovered after shifting away the lower 59 bits. -/
def unpackSquareful (word : Nat) : Bool :=
  (word / squarefulRadix) % 2 == 1

/-- A positive divisor of a source-domain row fits in the 54-bit product
field. -/
theorem divisor_lt_productRadix
    {product n : Nat}
    (hnPositive : 0 < n)
    (hdivides : product ∣ n)
    (hn : n ≤ sourceLimit) :
    product < productRadix := by
  have hle : product ≤ n := Nat.le_of_dvd hnPositive hdivides
  norm_num [sourceLimit, productRadix] at *
  omega

/-- Every well-formed support triple occupies at most 60 bits. -/
theorem pack_lt_two_pow_sixty
    {product distinctCount : Nat} {squareful : Bool}
    (hproduct : product < productRadix)
    (hcount : distinctCount < countRadix) :
    pack product distinctCount squareful < 2 ^ 60 := by
  cases squareful <;>
    norm_num [pack, productRadix, countRadix] at *
  all_goals omega

/-- In particular, the packed support word fits in `UInt64`. -/
theorem pack_lt_wordLimit
    {product distinctCount : Nat} {squareful : Bool}
    (hproduct : product < productRadix)
    (hcount : distinctCount < countRadix) :
    pack product distinctCount squareful < wordLimit := by
  have h60 :=
    pack_lt_two_pow_sixty
      (squareful := squareful) hproduct hcount
  norm_num [wordLimit] at *
  omega

/-- Distinct-prime updates commute.  Consequently every serialization of the
native CAS operations has the same mathematical support state. -/
theorem update_comm
    (support : Support) (firstPrime secondPrime : Nat)
    (firstSquareful secondSquareful : Bool) :
    update (update support firstPrime firstSquareful)
        secondPrime secondSquareful =
      update (update support secondPrime secondSquareful)
        firstPrime firstSquareful := by
  cases support with
  | mk product distinctCount squareful =>
      cases squareful <;>
        cases firstSquareful <;>
        cases secondSquareful <;>
        simp [update, Nat.mul_comm, Nat.mul_left_comm,
          Nat.add_comm, Nat.add_left_comm]

/-- A local sum of at most one hundred million Möbius values fits exactly in
the signed 32-bit field used by the optimized CUB prefix scan. -/
theorem localMertens_fits_int32
    {count : Nat} {delta : Int}
    (hcount : count ≤ maximumSegmentRows)
    (hlower : -(count : Int) ≤ delta)
    (hupper : delta ≤ count) :
    -(2 ^ 31 : Int) ≤ delta ∧ delta < 2 ^ 31 := by
  norm_num [maximumSegmentRows] at hcount ⊢
  omega

/-- A local squarefree count from the same segment fits exactly in the
unsigned 32-bit field used by the optimized CUB prefix scan. -/
theorem localSquarefree_fits_uint32
    {count squarefree : Nat}
    (hcount : count ≤ maximumSegmentRows)
    (hsquarefree : squarefree ≤ count) :
    squarefree < 2 ^ 32 := by
  norm_num [maximumSegmentRows] at hcount ⊢
  omega

/-- The layout has no collisions inside its declared field bounds. -/
theorem pack_injective
    {product₁ product₂ count₁ count₂ : Nat}
    {squareful₁ squareful₂ : Bool}
    (hproduct₁ : product₁ < productRadix)
    (hproduct₂ : product₂ < productRadix)
    (hcount₁ : count₁ < countRadix)
    (hcount₂ : count₂ < countRadix)
    (hequality :
      pack product₁ count₁ squareful₁ =
        pack product₂ count₂ squareful₂) :
    product₁ = product₂ ∧
      count₁ = count₂ ∧
      squareful₁ = squareful₂ := by
  cases squareful₁ <;> cases squareful₂ <;>
    norm_num [pack, productRadix, countRadix] at *
  all_goals omega

/-- The low 54 bits decode the original divisor product. -/
@[simp] theorem unpackProduct_pack
    {product distinctCount : Nat} {squareful : Bool}
    (hproduct : product < productRadix) :
    unpackProduct (pack product distinctCount squareful) = product := by
  cases squareful <;>
    norm_num [unpackProduct, pack, productRadix, countRadix] at *
  all_goals omega

/-- The following five bits decode the original distinct-factor count. -/
@[simp] theorem unpackCount_pack
    {product distinctCount : Nat} {squareful : Bool}
    (hproduct : product < productRadix)
    (hcount : distinctCount < countRadix) :
    unpackCount (pack product distinctCount squareful) = distinctCount := by
  cases squareful <;>
    norm_num [unpackCount, pack, productRadix, countRadix] at *
  all_goals omega

/-- Bit 59 decodes the original squareful flag. -/
@[simp] theorem unpackSquareful_pack
    {product distinctCount : Nat} {squareful : Bool}
    (hproduct : product < productRadix)
    (hcount : distinctCount < countRadix) :
    unpackSquareful (pack product distinctCount squareful) = squareful := by
  cases squareful <;>
    norm_num [unpackSquareful, squarefulRadix, pack, productRadix,
      countRadix] at *
  all_goals omega

/-- Packing a well-formed updated state and decoding it recovers the exact
updated product. -/
@[simp] theorem unpackProduct_pack_update
    {support : Support} {prime : Nat} {dividesSquare : Bool}
    (hproduct : support.product * prime < productRadix) :
    unpackProduct
        (pack (update support prime dividesSquare).product
          (update support prime dividesSquare).distinctCount
          (update support prime dividesSquare).squareful) =
      support.product * prime := by
  exact unpackProduct_pack hproduct

/-- Packing a well-formed updated state and decoding it recovers the exact
updated distinct-factor count. -/
@[simp] theorem unpackCount_pack_update
    {support : Support} {prime : Nat} {dividesSquare : Bool}
    (hproduct : support.product * prime < productRadix)
    (hcount : support.distinctCount + 1 < countRadix) :
    unpackCount
        (pack (update support prime dividesSquare).product
          (update support prime dividesSquare).distinctCount
          (update support prime dividesSquare).squareful) =
      support.distinctCount + 1 := by
  exact unpackCount_pack hproduct hcount

/-- Packing a well-formed updated state and decoding it recovers the monotone
squareful flag. -/
@[simp] theorem unpackSquareful_pack_update
    {support : Support} {prime : Nat} {dividesSquare : Bool}
    (hproduct : support.product * prime < productRadix)
    (hcount : support.distinctCount + 1 < countRadix) :
    unpackSquareful
        (pack (update support prime dividesSquare).product
          (update support prime dividesSquare).distinctCount
          (update support prime dividesSquare).squareful) =
      (support.squareful || dividesSquare) := by
  exact unpackSquareful_pack hproduct hcount

#print axioms divisor_lt_productRadix
#print axioms pack_lt_two_pow_sixty
#print axioms pack_lt_wordLimit
#print axioms update_comm
#print axioms update_eq_markSquareful_updateProductCount
#print axioms markSquareful_updateProductCount_comm
#print axioms markSquareful_markSquareful_comm
#print axioms localMertens_fits_int32
#print axioms localSquarefree_fits_uint32
#print axioms pack_injective
#print axioms unpackProduct_pack
#print axioms unpackCount_pack
#print axioms unpackSquareful_pack
#print axioms unpackProduct_pack_update
#print axioms unpackCount_pack_update
#print axioms unpackSquareful_pack_update

end SparkInterval.TernaryGoldbach.MobiusFusedSupport
