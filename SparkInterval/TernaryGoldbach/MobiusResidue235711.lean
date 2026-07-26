/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.MobiusResidue2357

/-!
# Exact extension of the residue-2357 seed by the prime 11

The qualification residue-2357 initializer represents the exact contribution
of `2, 3, 5, 7`.  A further qualification candidate can remove the `p = 11`
distinct-factor and square-strike event streams by applying the contribution
of eleven from the row residue modulo `11² = 121`.

This module proves the source-shaped block-local residue arithmetic, the pure
support-fold refinement, packed-word safety, and the exact suffix-capacity
bound.  It does not claim that a CUDA kernel implements this candidate or
promote it into the production runner.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.MobiusResidue235711

open SparkInterval.TernaryGoldbach.MobiusFusedSupport
open SparkInterval.TernaryGoldbach.MobiusDenseSchedule
open SparkInterval.TernaryGoldbach.MobiusResidue235
open SparkInterval.TernaryGoldbach.MobiusResidue2357

/-- The residue modulus that determines both `11 ∣ n` and `11² ∣ n`. -/
def elevenSquareModulus : Nat := 121

/-- Prime prefix represented by the residue-2357 seed followed by the
modulo-121 extension. -/
def seedPrimes235711 : List Nat := seedPrimes2357 ++ [11]

/-- Smallest possible suffix prime after the exact `[2,3,5,7,11]` prefix. -/
def residue235711SuffixMinimumPrime : Nat := 13

/-- Exact minimum number of event block slots needed per suffix prime at the
unchanged maximum segment-row count. -/
def residue235711MinimumBlockSlotsPerPrime : Nat := 79

/-- Exact qualification initializer: load the residue-2357 support, then
apply the `p = 11` contribution using only the row residue modulo 121. -/
def residueSeed235711 (n : Nat) : Support :=
  applyPrime (n % elevenSquareModulus) (residueSeed2357 n) 11

/-- Packed word emitted by the pure qualification initializer. -/
def residueSeed235711Word (n : Nat) : Nat :=
  pack
    (residueSeed235711 n).product
    (residueSeed235711 n).distinctCount
    (residueSeed235711 n).squareful

/-- Source-shaped block-local modulo-121 reconstruction.  Thread zero obtains
the source number at the start of the block and each thread adds its local
index before reducing modulo 121. -/
def blockLocalResidue121
    (lower block thread : Nat) : Nat :=
  ((lower + block * threadsPerBlock) % elevenSquareModulus + thread) %
    elevenSquareModulus

/-- The block-local reconstruction is exactly the residue of the physical
source row `lower + block*256 + thread`. -/
theorem blockLocalResidue121_eq_sourceNumber_mod
    (lower block thread : Nat) :
    blockLocalResidue121 lower block thread =
      (lower + block * threadsPerBlock + thread) %
        elevenSquareModulus := by
  norm_num [blockLocalResidue121, threadsPerBlock,
    elevenSquareModulus]

/-- The literal `residue121 % 11 == 0` branch fires exactly on rows divisible
by eleven. -/
theorem blockLocalResidue121_mod_eleven_eq_zero_iff
    (lower block thread : Nat) :
    blockLocalResidue121 lower block thread % 11 = 0 ↔
      11 ∣ lower + block * threadsPerBlock + thread := by
  rw [← Nat.dvd_iff_mod_eq_zero,
    blockLocalResidue121_eq_sourceNumber_mod]
  exact Nat.dvd_mod_iff (by norm_num [elevenSquareModulus])

/-- The literal `residue121 == 0` square branch fires exactly on rows
divisible by `11²`. -/
theorem blockLocalResidue121_eq_zero_iff
    (lower block thread : Nat) :
    blockLocalResidue121 lower block thread = 0 ↔
      11 * 11 ∣ lower + block * threadsPerBlock + thread := by
  rw [blockLocalResidue121_eq_sourceNumber_mod]
  norm_num [elevenSquareModulus]
  exact Nat.dvd_iff_mod_eq_zero.symm

theorem eleven_dvd_mod121_iff (n : Nat) :
    11 ∣ n % elevenSquareModulus ↔ 11 ∣ n := by
  exact Nat.dvd_mod_iff (by norm_num [elevenSquareModulus])

theorem elevenSquare_dvd_mod121_iff (n : Nat) :
    11 * 11 ∣ n % elevenSquareModulus ↔ 11 * 11 ∣ n := by
  exact Nat.dvd_mod_iff (by norm_num [elevenSquareModulus])

/-- Computing the eleven update from `n % 121` is exactly the same update as
computing it from the complete source row. -/
theorem applyEleven_mod121_eq (n : Nat) (support : Support) :
    applyPrime (n % elevenSquareModulus) support 11 =
      applyPrime n support 11 := by
  unfold applyPrime
  by_cases heleven : 11 ∣ n
  · have helevenResidue : 11 ∣ n % elevenSquareModulus :=
      (eleven_dvd_mod121_iff n).mpr heleven
    by_cases hsquare : 11 * 11 ∣ n
    · have hsquareResidue :
          11 * 11 ∣ n % elevenSquareModulus :=
        (elevenSquare_dvd_mod121_iff n).mpr hsquare
      simp [heleven, helevenResidue, hsquare, hsquareResidue]
    · have hsquareResidue :
          ¬ 11 * 11 ∣ n % elevenSquareModulus :=
        fun contradiction =>
          hsquare ((elevenSquare_dvd_mod121_iff n).mp contradiction)
      simp [heleven, helevenResidue, hsquare, hsquareResidue]
  · have helevenResidue : ¬ 11 ∣ n % elevenSquareModulus :=
      fun contradiction =>
        heleven ((eleven_dvd_mod121_iff n).mp contradiction)
    simp [heleven, helevenResidue]

/-- The extended initializer is exactly the ordinary support fold over
`[2,3,5,7,11]`. -/
theorem residueSeed235711_eq_fold (n : Nat) :
    residueSeed235711 n = foldSupport n seedPrimes235711 := by
  rw [residueSeed235711, applyEleven_mod121_eq]
  rw [seedPrimes235711, foldSupport, List.foldl_append]
  simp only [List.foldl_cons, List.foldl_nil]
  change
    applyPrime n (residueSeed2357 n) 11 =
      applyPrime n (foldSupport n seedPrimes2357) 11
  rw [residueSeed2357_eq_fold]

/-- Replacing the first five event streams by the proposed initializer
preserves the complete support state for every subsequent suffix. -/
theorem fold_prefix_suffix_eq_residueSeed235711
    (n : Nat) (suffix : List Nat) :
    foldSupport n (seedPrimes235711 ++ suffix) =
      suffix.foldl (applyPrime n) (residueSeed235711 n) := by
  rw [foldSupport, List.foldl_append, ← foldSupport,
    ← residueSeed235711_eq_fold]

theorem residue235711MinimumBlockSlotsPerPrime_eq :
    residue235711MinimumBlockSlotsPerPrime = 79 := by
  rfl

/-- At the maximum segment-row count, every suffix value admitted by the
strengthened structural preflight fits the exact 79-slot event rectangle. -/
theorem residue235711MultipleEventCount_le_minimumCapacity
    {count firstOffset prime : Nat}
    (hcount : count ≤ MobiusDenseSchedule.maximumSegmentRows)
    (hprime : residue235711SuffixMinimumPrime ≤ prime) :
    multipleEventCount count firstOffset prime ≤
      residue235711MinimumBlockSlotsPerPrime * eventsPerBlock := by
  unfold multipleEventCount
  split
  · simp
  · let capacity :=
      residue235711MinimumBlockSlotsPerPrime * eventsPerBlock
    have hcapacityPos : 0 < capacity := by
      norm_num [capacity, residue235711MinimumBlockSlotsPerPrime,
        eventsPerBlock, threadsPerBlock, iterationsPerThread]
    have hmaximumBound :
        MobiusDenseSchedule.maximumSegmentRows ≤
          residue235711SuffixMinimumPrime * capacity := by
      norm_num [MobiusDenseSchedule.maximumSegmentRows,
        residue235711SuffixMinimumPrime,
        capacity, residue235711MinimumBlockSlotsPerPrime,
        blockSlotsPerPrime, eventsPerBlock, threadsPerBlock,
        iterationsPerThread]
    have hnumerator :
        count - 1 - firstOffset <
          residue235711SuffixMinimumPrime * capacity := by
      omega
    have hscaled :
        residue235711SuffixMinimumPrime * capacity ≤
          capacity * prime := by
      simpa [Nat.mul_comm] using
        Nat.mul_le_mul_left capacity hprime
    have hquotient :
        (count - 1 - firstOffset) / prime < capacity := by
      have hprimePos : 0 < prime :=
        lt_of_lt_of_le
          (by norm_num [residue235711SuffixMinimumPrime]) hprime
      apply (Nat.div_lt_iff_lt_mul hprimePos).2
      exact lt_of_lt_of_le hnumerator hscaled
    omega

/-- At the maximum count, the zero-offset `p=13` event stream does not fit
78 slots, so 79 is the exact minimum rather than merely sufficient. -/
theorem residue235711PreviousSlotCount_insufficient :
    (residue235711MinimumBlockSlotsPerPrime - 1) * eventsPerBlock <
      multipleEventCount MobiusDenseSchedule.maximumSegmentRows 0
        residue235711SuffixMinimumPrime := by
  norm_num [multipleEventCount, MobiusDenseSchedule.maximumSegmentRows,
    residue235711SuffixMinimumPrime,
    residue235711MinimumBlockSlotsPerPrime, blockSlotsPerPrime,
    eventsPerBlock, threadsPerBlock, iterationsPerThread]

/-- Exact product field of the extended initializer. -/
theorem residueSeed235711_product_eq (n : Nat) :
    (residueSeed235711 n).product =
      if 11 ∣ n then (residueSeed2357 n).product * 11
      else (residueSeed2357 n).product := by
  rw [residueSeed235711, applyEleven_mod121_eq]
  by_cases heleven : 11 ∣ n <;>
    simp [applyPrime, heleven, update]

/-- Exact distinct-factor-count field of the extended initializer. -/
theorem residueSeed235711_count_eq (n : Nat) :
    (residueSeed235711 n).distinctCount =
      if 11 ∣ n then (residueSeed2357 n).distinctCount + 1
      else (residueSeed2357 n).distinctCount := by
  rw [residueSeed235711, applyEleven_mod121_eq]
  by_cases heleven : 11 ∣ n <;>
    simp [applyPrime, heleven, update]

/-- Exact squareful field of the extended initializer. -/
theorem residueSeed235711_squareful_eq (n : Nat) :
    (residueSeed235711 n).squareful =
      ((residueSeed2357 n).squareful ||
        decide (11 * 11 ∣ n)) := by
  rw [residueSeed235711, applyEleven_mod121_eq]
  by_cases heleven : 11 ∣ n
  · simp [applyPrime, heleven, update]
  · have hsquare : ¬ 11 * 11 ∣ n := by
      intro squareDivides
      exact heleven (dvd_trans (by norm_num) squareDivides)
    simp [applyPrime, heleven, hsquare]

/-- The extended seed product is at most `2·3·5·7·11 = 2310`. -/
theorem residueSeed235711_product_le_twoThousandThreeHundredTen
    (n : Nat) :
    (residueSeed235711 n).product ≤ 2310 := by
  rw [residueSeed235711_product_eq]
  have oldBound := residueSeed2357_product_le_twoHundredTen n
  split <;> omega

/-- The extended seed represents at most five distinct prime factors. -/
theorem residueSeed235711_count_le_five (n : Nat) :
    (residueSeed235711 n).distinctCount ≤ 5 := by
  rw [residueSeed235711_count_eq]
  have oldBound := residueSeed2357_count_le_four n
  split <;> omega

theorem residueSeed235711_product_lt_productRadix (n : Nat) :
    (residueSeed235711 n).product < productRadix := by
  have bound :=
    residueSeed235711_product_le_twoThousandThreeHundredTen n
  norm_num [productRadix] at *
  omega

theorem residueSeed235711_count_lt_countRadix (n : Nat) :
    (residueSeed235711 n).distinctCount < countRadix := by
  have bound := residueSeed235711_count_le_five n
  norm_num [countRadix] at *
  omega

/-- The packed initializer cannot reach the reserved or poison bits: every
valid seed occupies fewer than 60 bits. -/
theorem residueSeed235711Word_lt_two_pow_sixty (n : Nat) :
    residueSeed235711Word n < 2 ^ 60 := by
  exact pack_lt_two_pow_sixty
    (residueSeed235711_product_lt_productRadix n)
    (residueSeed235711_count_lt_countRadix n)

theorem residueSeed235711Word_lt_wordLimit (n : Nat) :
    residueSeed235711Word n < wordLimit := by
  exact pack_lt_wordLimit
    (residueSeed235711_product_lt_productRadix n)
    (residueSeed235711_count_lt_countRadix n)

@[simp] theorem unpackProduct_residueSeed235711Word (n : Nat) :
    unpackProduct (residueSeed235711Word n) =
      (residueSeed235711 n).product := by
  exact unpackProduct_pack
    (residueSeed235711_product_lt_productRadix n)

@[simp] theorem unpackCount_residueSeed235711Word (n : Nat) :
    unpackCount (residueSeed235711Word n) =
      (residueSeed235711 n).distinctCount := by
  exact unpackCount_pack
    (residueSeed235711_product_lt_productRadix n)
    (residueSeed235711_count_lt_countRadix n)

@[simp] theorem unpackSquareful_residueSeed235711Word (n : Nat) :
    unpackSquareful (residueSeed235711Word n) =
      (residueSeed235711 n).squareful := by
  exact unpackSquareful_pack
    (residueSeed235711_product_lt_productRadix n)
    (residueSeed235711_count_lt_countRadix n)

#print axioms applyEleven_mod121_eq
#print axioms blockLocalResidue121_eq_sourceNumber_mod
#print axioms blockLocalResidue121_mod_eleven_eq_zero_iff
#print axioms blockLocalResidue121_eq_zero_iff
#print axioms residueSeed235711_eq_fold
#print axioms fold_prefix_suffix_eq_residueSeed235711
#print axioms residue235711MultipleEventCount_le_minimumCapacity
#print axioms residue235711PreviousSlotCount_insufficient
#print axioms residueSeed235711_product_eq
#print axioms residueSeed235711_count_eq
#print axioms residueSeed235711_squareful_eq
#print axioms residueSeed235711Word_lt_wordLimit
#print axioms unpackProduct_residueSeed235711Word
#print axioms unpackCount_residueSeed235711Word
#print axioms unpackSquareful_residueSeed235711Word

end SparkInterval.TernaryGoldbach.MobiusResidue235711
