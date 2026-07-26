/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Data.List.Defs
import Mathlib.Tactic

/-!
# Cutoff independence of the Goldbach word-owner sieve

The hardened GoldbachGPU implementation divides one complete list of base
primes between two kernels:

* primes at most `cutoff` are applied by a race-free one-thread-per-word
  kernel; and
* primes above `cutoff` are applied by a global-atomic tail kernel.

The cutoff is a performance parameter, not a mathematical parameter.  This
file proves the small equation needed by the cutoff autotuner: filtering the
same base-prime list into the two complementary ranges and clearing a
candidate in either range is exactly equivalent to clearing it with the
unsplit list.  The theorem is independent of primality generation; the
producer must still show that `basePrimes` is the complete required list and
that each physical kernel implements `ClearedBy`.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.GoldbachWordOwnerSieve

/-- A candidate is cleared when one retained base prime divides it at or above
that prime's square.  The square guard preserves the base prime itself. -/
def ClearedBy (basePrimes : List Nat) (candidate : Nat) : Prop :=
  ∃ prime ∈ basePrimes, prime ∣ candidate ∧ prime * prime ≤ candidate

/-- Logical result of the physical word-owner/tail-kernel split. -/
def SplitClearedBy
    (cutoff : Nat) (basePrimes : List Nat) (candidate : Nat) : Prop :=
  ClearedBy (basePrimes.filter (· ≤ cutoff)) candidate ∨
    ClearedBy (basePrimes.filter (cutoff < ·)) candidate

/-- The two cutoff ranges are complementary, so the split sieve clears exactly
the candidates cleared by the complete base-prime list. -/
theorem splitClearedBy_iff
    (cutoff : Nat) (basePrimes : List Nat) (candidate : Nat) :
    SplitClearedBy cutoff basePrimes candidate ↔
      ClearedBy basePrimes candidate := by
  constructor
  · rintro (⟨prime, hprime, hdiv, hsquare⟩ |
      ⟨prime, hprime, hdiv, hsquare⟩)
    · exact ⟨prime, (List.mem_filter.mp hprime).1, hdiv, hsquare⟩
    · exact ⟨prime, (List.mem_filter.mp hprime).1, hdiv, hsquare⟩
  · rintro ⟨prime, hprime, hdiv, hsquare⟩
    by_cases hsmall : prime ≤ cutoff
    · exact Or.inl
        ⟨prime, List.mem_filter.mpr ⟨hprime, by simpa using hsmall⟩,
          hdiv, hsquare⟩
    · exact Or.inr
        ⟨prime, List.mem_filter.mpr
          ⟨hprime, by simpa using Nat.lt_of_not_ge hsmall⟩,
          hdiv, hsquare⟩

/-- Consequently, changing only the cutoff cannot change which candidates
survive, provided both physical kernels implement their `ClearedBy` range. -/
theorem survives_split_iff
    (cutoff : Nat) (basePrimes : List Nat) (candidate : Nat) :
    (¬ SplitClearedBy cutoff basePrimes candidate) ↔
      ¬ ClearedBy basePrimes candidate := by
  rw [splitClearedBy_iff]

/-- Three-tier performance split used by the warp-per-prime prototype:
word-owned prefix, warp-parallel middle, and one-thread-per-prime tail. -/
def ThreeTierClearedBy
    (ownerCutoff warpCutoff : Nat)
    (basePrimes : List Nat) (candidate : Nat) : Prop :=
  ClearedBy (basePrimes.filter (· ≤ ownerCutoff)) candidate ∨
    ClearedBy
      (basePrimes.filter
        (fun prime => decide (ownerCutoff < prime ∧ prime ≤ warpCutoff)))
      candidate ∨
    ClearedBy (basePrimes.filter (warpCutoff < ·)) candidate

/-- Giving each prime in the middle range 32 progression lanes changes only
work allocation: the three complementary ranges still clear exactly the
complete base-prime list. -/
theorem threeTierClearedBy_iff
    (ownerCutoff warpCutoff : Nat)
    (basePrimes : List Nat) (candidate : Nat) :
    ThreeTierClearedBy ownerCutoff warpCutoff basePrimes candidate ↔
      ClearedBy basePrimes candidate := by
  constructor
  · rintro (⟨prime, hprime, hdiv, hsquare⟩ |
      ⟨prime, hprime, hdiv, hsquare⟩ |
      ⟨prime, hprime, hdiv, hsquare⟩)
    · exact ⟨prime, (List.mem_filter.mp hprime).1, hdiv, hsquare⟩
    · exact ⟨prime, (List.mem_filter.mp hprime).1, hdiv, hsquare⟩
    · exact ⟨prime, (List.mem_filter.mp hprime).1, hdiv, hsquare⟩
  · rintro ⟨prime, hprime, hdiv, hsquare⟩
    by_cases howner : prime ≤ ownerCutoff
    · exact Or.inl
        ⟨prime, List.mem_filter.mpr ⟨hprime, by simpa using howner⟩,
          hdiv, hsquare⟩
    · by_cases hwarp : prime ≤ warpCutoff
      · exact Or.inr (Or.inl
          ⟨prime, List.mem_filter.mpr
            ⟨hprime, by
              simp only [decide_eq_true_eq]
              exact ⟨Nat.lt_of_not_ge howner, hwarp⟩⟩,
            hdiv, hsquare⟩)
      · exact Or.inr (Or.inr
          ⟨prime, List.mem_filter.mpr
            ⟨hprime, by simpa using Nat.lt_of_not_ge hwarp⟩,
            hdiv, hsquare⟩)

/-! ## The 32-lane progression equation -/

/-- Natural-number model of the composite assigned to one warp lane and
round.  The physical kernel separately guards every `UInt64` addition. -/
def warpComposite
    (first step : Nat) (lane : Fin 32) (round : Nat) : Nat :=
  first + step * ((lane : Nat) + 32 * round)

/-- Euclidean division assigns every progression index to a valid lane. -/
def laneOfIndex (index : Nat) : Fin 32 :=
  ⟨index % 32, Nat.mod_lt _ (by norm_num)⟩

/-- The lane/round pair is an exact decomposition, not a sampled schedule. -/
theorem lane_round_decomposition (index : Nat) :
    (laneOfIndex index : Nat) + 32 * (index / 32) = index := by
  exact Nat.mod_add_div index 32

/-- Therefore the union of the 32 lane progressions contains every term of
the original one-thread-per-prime progression. -/
theorem warpComposite_covers
    (first step index : Nat) :
    warpComposite first step (laneOfIndex index) (index / 32) =
      first + step * index := by
  simp only [warpComposite]
  rw [lane_round_decomposition]

/-! ## Packed odd-window address equation -/

/-- Bit index of an odd candidate in an odd-number window. -/
def oddBitIndex (qLow candidate : Nat) : Nat :=
  (candidate - qLow) / 2

/-- Exact 64-bit word containing an odd-window candidate. -/
def oddWordIndex (qLow candidate : Nat) : Nat :=
  oddBitIndex qLow candidate / 64

/-- Exact bit within the containing 64-bit word. -/
def oddBitInWord (qLow candidate : Nat) : Nat :=
  oddBitIndex qLow candidate % 64

/-- Reconstruct the represented odd number from its word and bit indices.
The hypothesis is the explicit parity/alignment invariant established by the
host before either CUDA sieve kernel is launched. -/
theorem odd_word_bit_reconstruct
    (qLow candidate sourceIndex : Nat)
    (halign : candidate = qLow + 2 * sourceIndex) :
    qLow + 128 * oddWordIndex qLow candidate +
        2 * oddBitInWord qLow candidate =
      candidate := by
  have hbit : oddBitIndex qLow candidate = sourceIndex := by
    simp only [oddBitIndex]
    omega
  have hsplit := Nat.mod_add_div sourceIndex 64
  simp only [oddWordIndex, oddBitInWord, hbit]
  omega

/-- The `candidate >= p^2` guard keeps an odd base prime from clearing its own
bit. -/
theorem square_guard_preserves_self {prime : Nat} (hprime : 2 ≤ prime) :
    ¬ prime * prime ≤ prime := by
  nlinarith

#print axioms splitClearedBy_iff
#print axioms survives_split_iff
#print axioms threeTierClearedBy_iff
#print axioms lane_round_decomposition
#print axioms warpComposite_covers
#print axioms odd_word_bit_reconstruct
#print axioms square_guard_preserves_self

end SparkInterval.TernaryGoldbach.GoldbachWordOwnerSieve
