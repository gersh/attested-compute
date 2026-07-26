/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusResidue235711

/-!
# Exact extension of the residue-235711 seed by the prime 13

The qualification-only CUDA candidate retains the exact `[2,3,5,7,11]`
initializer and derives the contribution of `13` from the source row modulo
`13² = 169`.  This module proves the pure support refinement, the literal
block-local residue calculation (including its `UInt32` realization), packed
word safety, and the exact suffix-capacity bound.

This is base-trio arithmetic.  It neither proves compiler/GPU refinement nor
promotes the qualification candidate into the production receipt identity.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusResidue23571113

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusDenseSchedule
open SparkInterval.TernaryGoldbach.MobiusResidue235
open SparkInterval.TernaryGoldbach.MobiusResidue2357
open SparkInterval.TernaryGoldbach.MobiusResidue235711

/-- Modulus determining both `13 ∣ n` and `13² ∣ n`. -/
def thirteenSquareModulus : Nat := 169

/-- Exact seed roster represented by the qualification initializer. -/
def seedPrimes23571113 : List Nat := seedPrimes235711 ++ [13]

/-- Smallest suffix prime after `[2,3,5,7,11,13]`. -/
def residue23571113SuffixMinimumPrime : Nat := 17

/-- Exact minimum event-block capacity at the unchanged maximum row count. -/
def residue23571113MinimumBlockSlotsPerPrime : Nat := 61

/-- Apply the `p = 13` update using only the row residue modulo 169. -/
def residueSeed23571113 (n : Nat) : Support :=
  applyPrime (n % thirteenSquareModulus) (residueSeed235711 n) 13

/-- Packed word emitted by the pure p13 initializer. -/
def residueSeed23571113Word (n : Nat) : Nat :=
  pack
    (residueSeed23571113 n).product
    (residueSeed23571113 n).distinctCount
    (residueSeed23571113 n).squareful

/-- Literal source-shaped block-local residue calculation. -/
def blockLocalResidue169 (lower block thread : Nat) : Nat :=
  ((lower + block * threadsPerBlock) % thirteenSquareModulus + thread) %
    thirteenSquareModulus

theorem blockLocalResidue169_eq_sourceNumber_mod
    (lower block thread : Nat) :
    blockLocalResidue169 lower block thread =
      (lower + block * threadsPerBlock + thread) %
        thirteenSquareModulus := by
  norm_num [blockLocalResidue169, threadsPerBlock,
    thirteenSquareModulus]

theorem blockLocalResidue169_mod_thirteen_eq_zero_iff
    (lower block thread : Nat) :
    blockLocalResidue169 lower block thread % 13 = 0 ↔
      13 ∣ lower + block * threadsPerBlock + thread := by
  rw [← Nat.dvd_iff_mod_eq_zero,
    blockLocalResidue169_eq_sourceNumber_mod]
  exact Nat.dvd_mod_iff (by norm_num [thirteenSquareModulus])

theorem blockLocalResidue169_eq_zero_iff
    (lower block thread : Nat) :
    blockLocalResidue169 lower block thread = 0 ↔
      13 * 13 ∣ lower + block * threadsPerBlock + thread := by
  rw [blockLocalResidue169_eq_sourceNumber_mod]
  norm_num [thirteenSquareModulus]
  exact Nat.dvd_iff_mod_eq_zero.symm

/-- Literal unsigned-64 expression used by thread zero before reducing the
source row modulo 169. -/
def blockFirstNumberUInt64 (lower block : Nat) : UInt64 :=
  UInt64.ofNat lower +
    UInt64.ofNat block * UInt64.ofNat threadsPerBlock

/-- Literal unsigned-64 `% 169` computation used by thread zero. -/
def blockFirstResidue169UInt64 (lower block : Nat) : UInt64 :=
  blockFirstNumberUInt64 lower block %
    UInt64.ofNat thirteenSquareModulus

/-- In the live source and launch domain, the source-row address computed by
thread zero is strictly below the unsigned-64 radix. -/
theorem blockFirstNumber_lt_uint64Radix
    {lower block : Nat}
    (hlower : lower ≤ 10_000_000_000_000_000)
    (hoffset :
      block * threadsPerBlock <
        MobiusDenseSchedule.maximumSegmentRows) :
    lower + block * threadsPerBlock < 2 ^ 64 := by
  norm_num [threadsPerBlock,
    MobiusDenseSchedule.maximumSegmentRows, blockSlotsPerPrime,
    eventsPerBlock, iterationsPerThread] at hoffset ⊢
  omega

/-- The actual unsigned-64 add/multiply expression does not wrap in the live
domain. -/
theorem blockFirstNumberUInt64_toNat
    {lower block : Nat}
    (hsource : lower + block * threadsPerBlock < 2 ^ 64) :
    (blockFirstNumberUInt64 lower block).toNat =
      lower + block * threadsPerBlock := by
  have hlower : lower < 2 ^ 64 := by omega
  have hblock : block < 2 ^ 64 := by
    norm_num [threadsPerBlock] at hsource ⊢
    omega
  have hproduct : block * threadsPerBlock < 2 ^ 64 := by
    omega
  simp only [blockFirstNumberUInt64, UInt64.toNat_add,
    UInt64.toNat_mul, UInt64.toNat_ofNat']
  rw [Nat.mod_eq_of_lt hlower, Nat.mod_eq_of_lt hblock]
  norm_num [threadsPerBlock] at hproduct hsource ⊢
  exact hsource

/-- The thread-zero unsigned-64 residue is the natural source residue. -/
theorem blockFirstResidue169UInt64_toNat
    {lower block : Nat}
    (hsource : lower + block * threadsPerBlock < 2 ^ 64) :
    (blockFirstResidue169UInt64 lower block).toNat =
      (lower + block * threadsPerBlock) %
        thirteenSquareModulus := by
  simp only [blockFirstResidue169UInt64, UInt64.toNat_mod]
  rw [blockFirstNumberUInt64_toNat hsource]
  change
    (lower + block * threadsPerBlock) %
        (thirteenSquareModulus % 2 ^ 64) =
      (lower + block * threadsPerBlock) %
        thirteenSquareModulus
  rw [Nat.mod_eq_of_lt
    (by norm_num [thirteenSquareModulus] :
      thirteenSquareModulus < 2 ^ 64)]

/-- Literal cast from the `% 169` unsigned-64 value to shared unsigned-32
storage. -/
def blockFirstResidue169UInt32 (lower block : Nat) : UInt32 :=
  (blockFirstResidue169UInt64 lower block).toUInt32

/-- Because the residue is below 169, the literal unsigned-64-to-unsigned-32
cast is exact. -/
theorem blockFirstResidue169UInt32_toNat
    {lower block : Nat}
    (hsource : lower + block * threadsPerBlock < 2 ^ 64) :
    (blockFirstResidue169UInt32 lower block).toNat =
      (lower + block * threadsPerBlock) %
        thirteenSquareModulus := by
  simp only [blockFirstResidue169UInt32, UInt64.toNat_toUInt32]
  rw [blockFirstResidue169UInt64_toNat hsource]
  have hresidue :
      (lower + block * threadsPerBlock) %
          thirteenSquareModulus < 2 ^ 32 := by
    have :=
      Nat.mod_lt
        (lower + block * threadsPerBlock)
        (by norm_num [thirteenSquareModulus] :
          0 < thirteenSquareModulus)
    norm_num [thirteenSquareModulus] at this ⊢
    omega
  rw [Nat.mod_eq_of_lt hresidue]

/-- Literal 32-bit add/mod expression used after thread zero has placed the
block's modulo-169 source residue in shared memory. -/
def blockLocalResidue169UInt32
    (blockFirstResidue thread : UInt32) : UInt32 :=
  (blockFirstResidue + thread) % (169 : UInt32)

/-- The actual unsigned-32 add/mod expression has no wrap in the live
`blockFirstResidue < 169`, `thread < 256` regime and refines the natural
residue expression. -/
theorem blockLocalResidue169UInt32_toNat
    (blockFirstResidue thread : UInt32)
    (hfirst : blockFirstResidue.toNat < thirteenSquareModulus)
    (hthread : thread.toNat < threadsPerBlock) :
    (blockLocalResidue169UInt32 blockFirstResidue thread).toNat =
      (blockFirstResidue.toNat + thread.toNat) %
        thirteenSquareModulus := by
  have hsum :
      blockFirstResidue.toNat + thread.toNat < 2 ^ 32 := by
    norm_num [thirteenSquareModulus] at hfirst
    norm_num [threadsPerBlock] at hthread
    omega
  simp only [blockLocalResidue169UInt32, UInt32.toNat_mod,
    UInt32.toNat_add]
  rw [UInt32.toNat_ofNat]
  norm_num [thirteenSquareModulus]
  norm_num at hsum
  rw [Nat.mod_eq_of_lt hsum]

/-- Complete literal machine expression for one CUDA initializer thread. -/
def blockLocalResidue169Machine
    (lower block : Nat) (thread : UInt32) : UInt32 :=
  blockLocalResidue169UInt32
    (blockFirstResidue169UInt32 lower block) thread

/-- The complete unsigned-64 source address, modulo, narrowing cast, and
unsigned-32 local add/mod path refines `blockLocalResidue169`. -/
theorem blockLocalResidue169Machine_toNat
    {lower block : Nat} (thread : UInt32)
    (hlower : lower ≤ 10_000_000_000_000_000)
    (hoffset :
      block * threadsPerBlock <
        MobiusDenseSchedule.maximumSegmentRows)
    (hthread : thread.toNat < threadsPerBlock) :
    (blockLocalResidue169Machine lower block thread).toNat =
      blockLocalResidue169 lower block thread.toNat := by
  have hsource :=
    blockFirstNumber_lt_uint64Radix hlower hoffset
  have hfirst :
      (blockFirstResidue169UInt32 lower block).toNat <
        thirteenSquareModulus := by
    rw [blockFirstResidue169UInt32_toNat hsource]
    exact Nat.mod_lt _ (by norm_num [thirteenSquareModulus])
  rw [blockLocalResidue169Machine,
    blockLocalResidue169UInt32_toNat _ _ hfirst hthread,
    blockFirstResidue169UInt32_toNat hsource]
  rfl

theorem thirteen_dvd_mod169_iff (n : Nat) :
    13 ∣ n % thirteenSquareModulus ↔ 13 ∣ n := by
  exact Nat.dvd_mod_iff (by norm_num [thirteenSquareModulus])

theorem thirteenSquare_dvd_mod169_iff (n : Nat) :
    13 * 13 ∣ n % thirteenSquareModulus ↔ 13 * 13 ∣ n := by
  exact Nat.dvd_mod_iff (by norm_num [thirteenSquareModulus])

/-- The modulo-169 update is exactly the full-source-row update. -/
theorem applyThirteen_mod169_eq (n : Nat) (support : Support) :
    applyPrime (n % thirteenSquareModulus) support 13 =
      applyPrime n support 13 := by
  unfold applyPrime
  by_cases hthirteen : 13 ∣ n
  · have hthirteenResidue : 13 ∣ n % thirteenSquareModulus :=
      (thirteen_dvd_mod169_iff n).mpr hthirteen
    by_cases hsquare : 13 * 13 ∣ n
    · have hsquareResidue :
          13 * 13 ∣ n % thirteenSquareModulus :=
        (thirteenSquare_dvd_mod169_iff n).mpr hsquare
      simp [hthirteen, hthirteenResidue, hsquare, hsquareResidue]
    · have hsquareResidue :
          ¬ 13 * 13 ∣ n % thirteenSquareModulus :=
        fun contradiction =>
          hsquare ((thirteenSquare_dvd_mod169_iff n).mp contradiction)
      simp [hthirteen, hthirteenResidue, hsquare, hsquareResidue]
  · have hthirteenResidue : ¬ 13 ∣ n % thirteenSquareModulus :=
      fun contradiction =>
        hthirteen ((thirteen_dvd_mod169_iff n).mp contradiction)
    simp [hthirteen, hthirteenResidue]

theorem residueSeed23571113_eq_fold (n : Nat) :
    residueSeed23571113 n = foldSupport n seedPrimes23571113 := by
  rw [residueSeed23571113, applyThirteen_mod169_eq]
  rw [seedPrimes23571113, foldSupport, List.foldl_append]
  simp only [List.foldl_cons, List.foldl_nil]
  change
    applyPrime n (residueSeed235711 n) 13 =
      applyPrime n (foldSupport n seedPrimes235711) 13
  rw [residueSeed235711_eq_fold]

/-- Replacing the first six event streams by the initializer preserves the
complete support state for every suffix roster. -/
theorem fold_prefix_suffix_eq_residueSeed23571113
    (n : Nat) (suffix : List Nat) :
    foldSupport n (seedPrimes23571113 ++ suffix) =
      suffix.foldl (applyPrime n) (residueSeed23571113 n) := by
  rw [foldSupport, List.foldl_append, ← foldSupport,
    ← residueSeed23571113_eq_fold]

theorem residue23571113MinimumBlockSlotsPerPrime_eq :
    residue23571113MinimumBlockSlotsPerPrime = 61 := by
  rfl

/-- Every suffix divisor stream fits 61 event blocks at the maximum count. -/
theorem residue23571113MultipleEventCount_le_minimumCapacity
    {count firstOffset prime : Nat}
    (hcount : count ≤ MobiusDenseSchedule.maximumSegmentRows)
    (hprime : residue23571113SuffixMinimumPrime ≤ prime) :
    multipleEventCount count firstOffset prime ≤
      residue23571113MinimumBlockSlotsPerPrime * eventsPerBlock := by
  unfold multipleEventCount
  split
  · simp
  · let capacity :=
      residue23571113MinimumBlockSlotsPerPrime * eventsPerBlock
    have hcapacityPos : 0 < capacity := by
      norm_num [capacity, residue23571113MinimumBlockSlotsPerPrime,
        eventsPerBlock, threadsPerBlock, iterationsPerThread]
    have hmaximumBound :
        MobiusDenseSchedule.maximumSegmentRows ≤
          residue23571113SuffixMinimumPrime * capacity := by
      norm_num [MobiusDenseSchedule.maximumSegmentRows,
        residue23571113SuffixMinimumPrime,
        capacity, residue23571113MinimumBlockSlotsPerPrime,
        blockSlotsPerPrime, eventsPerBlock, threadsPerBlock,
        iterationsPerThread]
    have hnumerator :
        count - 1 - firstOffset <
          residue23571113SuffixMinimumPrime * capacity := by
      omega
    have hscaled :
        residue23571113SuffixMinimumPrime * capacity ≤
          capacity * prime := by
      simpa [Nat.mul_comm] using
        Nat.mul_le_mul_left capacity hprime
    have hquotient :
        (count - 1 - firstOffset) / prime < capacity := by
      have hprimePos : 0 < prime :=
        lt_of_lt_of_le
          (by norm_num [residue23571113SuffixMinimumPrime]) hprime
      apply (Nat.div_lt_iff_lt_mul hprimePos).2
      exact lt_of_lt_of_le hnumerator hscaled
    omega

/-- Sixty slots are insufficient for the zero-offset p=17 stream. -/
theorem residue23571113PreviousSlotCount_insufficient :
    (residue23571113MinimumBlockSlotsPerPrime - 1) * eventsPerBlock <
      multipleEventCount MobiusDenseSchedule.maximumSegmentRows 0
        residue23571113SuffixMinimumPrime := by
  norm_num [multipleEventCount, MobiusDenseSchedule.maximumSegmentRows,
    residue23571113SuffixMinimumPrime,
    residue23571113MinimumBlockSlotsPerPrime, blockSlotsPerPrime,
    eventsPerBlock, threadsPerBlock, iterationsPerThread]

theorem residueSeed23571113_product_eq (n : Nat) :
    (residueSeed23571113 n).product =
      if 13 ∣ n then (residueSeed235711 n).product * 13
      else (residueSeed235711 n).product := by
  rw [residueSeed23571113, applyThirteen_mod169_eq]
  by_cases hthirteen : 13 ∣ n <;>
    simp [applyPrime, hthirteen, update]

theorem residueSeed23571113_count_eq (n : Nat) :
    (residueSeed23571113 n).distinctCount =
      if 13 ∣ n then (residueSeed235711 n).distinctCount + 1
      else (residueSeed235711 n).distinctCount := by
  rw [residueSeed23571113, applyThirteen_mod169_eq]
  by_cases hthirteen : 13 ∣ n <;>
    simp [applyPrime, hthirteen, update]

theorem residueSeed23571113_squareful_eq (n : Nat) :
    (residueSeed23571113 n).squareful =
      ((residueSeed235711 n).squareful ||
        decide (13 * 13 ∣ n)) := by
  rw [residueSeed23571113, applyThirteen_mod169_eq]
  by_cases hthirteen : 13 ∣ n
  · simp [applyPrime, hthirteen, update]
  · have hsquare : ¬ 13 * 13 ∣ n := by
      intro squareDivides
      exact hthirteen (dvd_trans (by norm_num) squareDivides)
    simp [applyPrime, hthirteen, hsquare]

theorem residueSeed23571113_product_le_thirtyThousandThirty
    (n : Nat) :
    (residueSeed23571113 n).product ≤ 30_030 := by
  rw [residueSeed23571113_product_eq]
  have oldBound :=
    residueSeed235711_product_le_twoThousandThreeHundredTen n
  split <;> omega

theorem residueSeed23571113_count_le_six (n : Nat) :
    (residueSeed23571113 n).distinctCount ≤ 6 := by
  rw [residueSeed23571113_count_eq]
  have oldBound := residueSeed235711_count_le_five n
  split <;> omega

theorem residueSeed23571113_product_lt_productRadix (n : Nat) :
    (residueSeed23571113 n).product < productRadix := by
  have bound :=
    residueSeed23571113_product_le_thirtyThousandThirty n
  norm_num [productRadix] at *
  omega

theorem residueSeed23571113_count_lt_countRadix (n : Nat) :
    (residueSeed23571113 n).distinctCount < countRadix := by
  have bound := residueSeed23571113_count_le_six n
  norm_num [countRadix] at *
  omega

theorem residueSeed23571113Word_lt_two_pow_sixty (n : Nat) :
    residueSeed23571113Word n < 2 ^ 60 := by
  exact pack_lt_two_pow_sixty
    (residueSeed23571113_product_lt_productRadix n)
    (residueSeed23571113_count_lt_countRadix n)

theorem residueSeed23571113Word_lt_wordLimit (n : Nat) :
    residueSeed23571113Word n < wordLimit := by
  exact pack_lt_wordLimit
    (residueSeed23571113_product_lt_productRadix n)
    (residueSeed23571113_count_lt_countRadix n)

@[simp] theorem unpackProduct_residueSeed23571113Word (n : Nat) :
    unpackProduct (residueSeed23571113Word n) =
      (residueSeed23571113 n).product := by
  exact unpackProduct_pack
    (residueSeed23571113_product_lt_productRadix n)

@[simp] theorem unpackCount_residueSeed23571113Word (n : Nat) :
    unpackCount (residueSeed23571113Word n) =
      (residueSeed23571113 n).distinctCount := by
  exact unpackCount_pack
    (residueSeed23571113_product_lt_productRadix n)
    (residueSeed23571113_count_lt_countRadix n)

@[simp] theorem unpackSquareful_residueSeed23571113Word (n : Nat) :
    unpackSquareful (residueSeed23571113Word n) =
      (residueSeed23571113 n).squareful := by
  exact unpackSquareful_pack
    (residueSeed23571113_product_lt_productRadix n)
    (residueSeed23571113_count_lt_countRadix n)

#print axioms blockLocalResidue169_eq_sourceNumber_mod
#print axioms blockLocalResidue169_mod_thirteen_eq_zero_iff
#print axioms blockLocalResidue169_eq_zero_iff
#print axioms blockFirstNumber_lt_uint64Radix
#print axioms blockFirstNumberUInt64_toNat
#print axioms blockFirstResidue169UInt64_toNat
#print axioms blockFirstResidue169UInt32_toNat
#print axioms blockLocalResidue169UInt32_toNat
#print axioms blockLocalResidue169Machine_toNat
#print axioms applyThirteen_mod169_eq
#print axioms residueSeed23571113_eq_fold
#print axioms fold_prefix_suffix_eq_residueSeed23571113
#print axioms residue23571113MultipleEventCount_le_minimumCapacity
#print axioms residue23571113PreviousSlotCount_insufficient
#print axioms residueSeed23571113Word_lt_wordLimit
#print axioms unpackProduct_residueSeed23571113Word
#print axioms unpackCount_residueSeed23571113Word
#print axioms unpackSquareful_residueSeed23571113Word

end SparkInterval.TernaryGoldbach.MobiusResidue23571113
