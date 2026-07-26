/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachWordOwnerSieve
import Mathlib.Data.Nat.Bitwise
import Mathlib.Tactic

/-!
# Arithmetic semantics of the through-23 Goldbach word-owner wheel

This file models the proposed odd-index wheel initializer through 23.  The
table has one bit for each residue modulo `111546435`, stores the survival of
the represented odd value `2 * residue + 1`, and has 64 duplicated head bits
so one owner word can read a contiguous 64-bit window across the wrap.

The main result proves that the table lookup, followed by explicit restoration
of the eight wheel primes, is extensionally equal to applying the original
divisibility and `p * p ≤ candidate` guards.  Applying every remaining prime
therefore gives the same logical word.

This is an exact natural-number and Boolean model.  It does not prove that a
CUDA implementation builds or loads this table, that machine address
arithmetic is in bounds, that a compiler preserves these operations, or that
PTX/SASS and hardware execute them correctly.  Those are separate refinement
and execution obligations.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.GoldbachWordOwnerWheel23

open GoldbachWordOwnerSieve

/-- The exact small-prime roster encoded by the candidate wheel. -/
def wheelPrimes : List Nat :=
  [3, 5, 7, 11, 13, 17, 19, 23]

/-- Product of the eight odd wheel primes, hence the odd-index period. -/
def wheelModulus : Nat :=
  111_546_435

/-- A table index represents this odd natural number. -/
def tableOddValue (phase : Nat) : Nat :=
  2 * (phase % wheelModulus) + 1

/-- Divisibility predicate encoded by a zero table bit. -/
def WheelDivisible (candidate : Nat) : Prop :=
  ∃ prime ∈ wheelPrimes, prime ∣ candidate

/-- Executable finite form of `WheelDivisible`. -/
def wheelDivisibleBool (candidate : Nat) : Bool :=
  wheelPrimes.any fun prime => decide (prime ∣ candidate)

theorem wheelDivisibleBool_eq_true_iff (candidate : Nat) :
    wheelDivisibleBool candidate = true ↔
      WheelDivisible candidate := by
  simp [wheelDivisibleBool, WheelDivisible, List.any_eq_true]

/-- One logical bit of the base table. `true` means that no wheel prime
divides its represented odd value. -/
def wheelTableBit (phase : Nat) : Bool :=
  !wheelDivisibleBool (tableOddValue phase)

/-- Functional model of the table after appending 64 copies of its head.
Only indices below `wheelModulus + 64` model allocated storage. -/
def duplicatedWheelTableBit (index : Nat) : Bool :=
  if index < wheelModulus then
    wheelTableBit index
  else
    wheelTableBit (index - wheelModulus)

/-- Exact odd candidate addressed by one owner-word bit. -/
def wordCandidate (qLow wordIndex bit : Nat) : Nat :=
  qLow + 128 * wordIndex + 2 * bit

/-- Natural semantics of the source's unsigned right shift by one. -/
def cudaHalf (qLow : Nat) : Nat :=
  qLow >>> 1

/-- Starting wheel phase for one 64-bit owner word. -/
def cudaWordPhase (qLow wordIndex : Nat) : Nat :=
  (cudaHalf qLow % wheelModulus +
      ((wordIndex % wheelModulus) * 64) % wheelModulus) %
    wheelModulus

/-- Wheel phase selected for one live bit.  The `bit < 64` launch guard is
carried explicitly by the correctness theorems below. -/
def cudaPhase (qLow wordIndex bit : Nat) : Nat :=
  (cudaHalf qLow % wheelModulus +
      ((wordIndex % wheelModulus) * 64) % wheelModulus +
      bit) %
    wheelModulus

/-! ## Exact constants and finite roster facts -/

theorem wheelModulus_eq_product :
    wheelModulus = wheelPrimes.prod := by
  norm_num [wheelModulus, wheelPrimes]

theorem wheelModulus_pos :
    0 < wheelModulus := by
  norm_num [wheelModulus]

theorem wheelPrime_dvd_modulus
    {prime : Nat} (member : prime ∈ wheelPrimes) :
    prime ∣ wheelModulus := by
  simp only [wheelPrimes, List.mem_cons, List.not_mem_nil, or_false] at member
  rcases member with
      rfl | rfl | rfl | rfl | rfl | rfl | rfl | rfl <;>
    norm_num [wheelModulus]

theorem wheelPrime_prime
    {prime : Nat} (member : prime ∈ wheelPrimes) :
    Nat.Prime prime := by
  simp only [wheelPrimes, List.mem_cons, List.not_mem_nil, or_false] at member
  rcases member with
      rfl | rfl | rfl | rfl | rfl | rfl | rfl | rfl <;>
    norm_num

theorem wheelPrime_three_le
    {prime : Nat} (member : prime ∈ wheelPrimes) :
    3 ≤ prime := by
  simp only [wheelPrimes, List.mem_cons, List.not_mem_nil, or_false] at member
  omega

theorem wheelPrime_le_twentyThree
    {prime : Nat} (member : prime ∈ wheelPrimes) :
    prime ≤ 23 := by
  simp only [wheelPrimes, List.mem_cons, List.not_mem_nil, or_false] at member
  omega

theorem prime_mem_wheelPrimes_of_three_le_of_le_twentyThree
    {prime : Nat} (primePrime : Nat.Prime prime)
    (lower : 3 ≤ prime) (upper : prime ≤ 23) :
    prime ∈ wheelPrimes := by
  interval_cases prime <;> norm_num [wheelPrimes] at *

/-! ## Phase and duplicated-head addressing -/

theorem wordCandidate_eq_oddIndex
    (qLow wordIndex bit : Nat) (qLowOdd : Odd qLow) :
    wordCandidate qLow wordIndex bit =
      2 * (cudaHalf qLow + 64 * wordIndex + bit) + 1 := by
  rcases qLowOdd with ⟨half, rfl⟩
  have halfShift :
      (2 * half + 1) >>> 1 = half := by
    rw [Nat.shiftRight_eq_div_pow]
    norm_num only [pow_one]
    rw [Nat.mul_add_div (by norm_num) half 1]
    norm_num
  rw [show cudaHalf (2 * half + 1) = half by
    simpa [cudaHalf] using halfShift]
  simp only [wordCandidate]
  ring

theorem wordCandidate_odd
    (qLow wordIndex bit : Nat) (qLowOdd : Odd qLow) :
    Odd (wordCandidate qLow wordIndex bit) := by
  rw [wordCandidate_eq_oddIndex qLow wordIndex bit qLowOdd]
  exact ⟨cudaHalf qLow + 64 * wordIndex + bit, rfl⟩

theorem wordCandidate_pos
    (qLow wordIndex bit : Nat) (qLowOdd : Odd qLow) :
    0 < wordCandidate qLow wordIndex bit := by
  have qLowPositive := qLowOdd.pos
  simp only [wordCandidate]
  omega

theorem cudaWordPhase_lt
    (qLow wordIndex : Nat) :
    cudaWordPhase qLow wordIndex < wheelModulus := by
  exact Nat.mod_lt _ wheelModulus_pos

theorem cudaPhase_eq_wordPhase_add_mod
    (qLow wordIndex bit : Nat) :
    cudaPhase qLow wordIndex bit =
      (cudaWordPhase qLow wordIndex + bit) % wheelModulus := by
  simp [cudaPhase, cudaWordPhase, Nat.add_mod]

theorem cudaPhase_eq_oddIndex_mod
    (qLow wordIndex bit : Nat) :
    cudaPhase qLow wordIndex bit =
      (cudaHalf qLow + 64 * wordIndex + bit) % wheelModulus := by
  simp [cudaPhase, Nat.add_mod, Nat.mul_mod, Nat.mul_comm]

/-- The source phase is the wheel residue of the exact addressed candidate's
odd index.  Odd alignment and the live-bit guard are explicit hypotheses. -/
theorem cudaPhase_addresses_wordCandidate
    (qLow wordIndex bit : Nat)
    (qLowOdd : Odd qLow) (_bitLive : bit < 64) :
    cudaPhase qLow wordIndex bit =
      (wordCandidate qLow wordIndex bit >>> 1) % wheelModulus := by
  rw [cudaPhase_eq_oddIndex_mod]
  rw [wordCandidate_eq_oddIndex qLow wordIndex bit qLowOdd]
  let index := cudaHalf qLow + 64 * wordIndex + bit
  have indexShift :
      (2 * index + 1) >>> 1 = index := by
    rw [Nat.shiftRight_eq_div_pow]
    norm_num only [pow_one]
    rw [Nat.mul_add_div (by norm_num) index 1]
    norm_num
  simpa [index] using congrArg (· % wheelModulus) indexShift.symm

theorem duplicatedLookup_index_lt
    (qLow wordIndex bit : Nat) (bitLive : bit < 64) :
    cudaWordPhase qLow wordIndex + bit < wheelModulus + 64 := by
  have phaseLive := cudaWordPhase_lt qLow wordIndex
  omega

/-- The 64 duplicated head bits make the contiguous physical lookup equal to
the logical modular lookup, including a single end-of-table wrap. -/
theorem duplicatedWheelTableBit_eq_mod
    (phase bit : Nat)
    (phaseLive : phase < wheelModulus) (bitLive : bit < 64) :
    duplicatedWheelTableBit (phase + bit) =
      wheelTableBit ((phase + bit) % wheelModulus) := by
  by_cases noWrap : phase + bit < wheelModulus
  · simp [duplicatedWheelTableBit, noWrap, Nat.mod_eq_of_lt noWrap]
  · have wraps : wheelModulus ≤ phase + bit :=
      Nat.le_of_not_gt noWrap
    have belowTwoPeriods : phase + bit - wheelModulus < wheelModulus := by
      norm_num [wheelModulus] at phaseLive bitLive ⊢
      omega
    rw [duplicatedWheelTableBit, if_neg noWrap]
    rw [Nat.mod_eq_sub_mod wraps, Nat.mod_eq_of_lt belowTwoPeriods]

theorem duplicatedWheelTableBit_cudaWordPhase
    (qLow wordIndex bit : Nat) (bitLive : bit < 64) :
    duplicatedWheelTableBit
        (cudaWordPhase qLow wordIndex + bit) =
      wheelTableBit (cudaPhase qLow wordIndex bit) := by
  rw [duplicatedWheelTableBit_eq_mod
    (cudaWordPhase qLow wordIndex) bit
    (cudaWordPhase_lt qLow wordIndex) bitLive]
  rw [cudaPhase_eq_wordPhase_add_mod]

/-! ## Table divisibility semantics -/

theorem tableOddValue_dvd_iff
    {prime index : Nat} (member : prime ∈ wheelPrimes) :
    prime ∣ tableOddValue index ↔
      prime ∣ 2 * index + 1 := by
  have indexModEq :
      index % wheelModulus ≡ index [MOD prime] := by
    exact Nat.mod_mod_of_dvd index (wheelPrime_dvd_modulus member)
  have valueModEq :
      2 * (index % wheelModulus) + 1 ≡
        2 * index + 1 [MOD prime] :=
    (indexModEq.mul_left 2).add_right 1
  constructor
  · intro tableDivides
    apply Nat.dvd_of_mod_eq_zero
    rw [← valueModEq]
    exact Nat.mod_eq_zero_of_dvd
      (by simpa [tableOddValue] using tableDivides)
  · intro candidateDivides
    apply Nat.dvd_of_mod_eq_zero
    change (2 * (index % wheelModulus) + 1) % prime = 0
    rw [valueModEq]
    exact Nat.mod_eq_zero_of_dvd candidateDivides

theorem odd_eq_two_shiftRight_add_one
    {candidate : Nat} (candidateOdd : Odd candidate) :
    2 * (candidate >>> 1) + 1 = candidate := by
  rcases candidateOdd with ⟨half, rfl⟩
  rw [Nat.shiftRight_eq_div_pow]
  norm_num only [pow_one]
  rw [Nat.mul_add_div (by norm_num) half 1]
  norm_num

/-- For every one of the exact eight wheel primes, table divisibility is
equivalent to divisibility of the addressed live candidate. -/
theorem tableOddValue_cudaPhase_dvd_iff_wordCandidate
    {prime : Nat} (member : prime ∈ wheelPrimes)
    (qLow wordIndex bit : Nat)
    (qLowOdd : Odd qLow) (bitLive : bit < 64) :
    prime ∣ tableOddValue (cudaPhase qLow wordIndex bit) ↔
      prime ∣ wordCandidate qLow wordIndex bit := by
  rw [cudaPhase_addresses_wordCandidate
    qLow wordIndex bit qLowOdd bitLive]
  have generic :=
    tableOddValue_dvd_iff
      (prime := prime)
      (index := wordCandidate qLow wordIndex bit >>> 1)
      member
  simpa [tableOddValue, Nat.mod_mod,
    odd_eq_two_shiftRight_add_one
      (wordCandidate_odd qLow wordIndex bit qLowOdd)] using generic

theorem wheelDivisible_table_iff_wordCandidate
    (qLow wordIndex bit : Nat)
    (qLowOdd : Odd qLow) (bitLive : bit < 64) :
    WheelDivisible (tableOddValue (cudaPhase qLow wordIndex bit)) ↔
      WheelDivisible (wordCandidate qLow wordIndex bit) := by
  constructor
  · rintro ⟨prime, member, divides⟩
    exact ⟨prime, member,
      (tableOddValue_cudaPhase_dvd_iff_wordCandidate
        member qLow wordIndex bit qLowOdd bitLive).mp divides⟩
  · rintro ⟨prime, member, divides⟩
    exact ⟨prime, member,
      (tableOddValue_cudaPhase_dvd_iff_wordCandidate
        member qLow wordIndex bit qLowOdd bitLive).mpr divides⟩

theorem wheelTableBit_cudaPhase
    (qLow wordIndex bit : Nat)
    (qLowOdd : Odd qLow) (bitLive : bit < 64) :
    wheelTableBit (cudaPhase qLow wordIndex bit) =
      !wheelDivisibleBool (wordCandidate qLow wordIndex bit) := by
  have divisibleBoolEquality :
      wheelDivisibleBool
          (tableOddValue (cudaPhase qLow wordIndex bit)) =
        wheelDivisibleBool (wordCandidate qLow wordIndex bit) := by
    apply Bool.eq_iff_iff.mpr
    rw [wheelDivisibleBool_eq_true_iff,
      wheelDivisibleBool_eq_true_iff]
    exact wheelDivisible_table_iff_wordCandidate
      qLow wordIndex bit qLowOdd bitLive
  exact congrArg (fun value => !value) divisibleBoolEquality

/-! ## Prime restoration and square-guard equivalence -/

theorem wheelPrime_not_cleared
    {candidate : Nat} (member : candidate ∈ wheelPrimes) :
    ¬ ClearedBy wheelPrimes candidate := by
  intro cleared
  rcases cleared with ⟨divisor, divisorMember, divides, square⟩
  rcases (wheelPrime_prime member).eq_one_or_self_of_dvd divisor divides with
    divisorOne | divisorSelf
  · have divisorLower := wheelPrime_three_le divisorMember
    omega
  · subst divisor
    have candidateLower := wheelPrime_three_le member
    exact square_guard_preserves_self
      (by omega : 2 ≤ candidate) square

/-- Apart from the wheel primes themselves, every positive odd multiple
cleared by the raw wheel also satisfies a legitimate square-guard clear. -/
theorem clearedBy_of_wheelDivisible_of_not_mem
    {candidate : Nat}
    (candidatePositive : 0 < candidate) (candidateOdd : Odd candidate)
    (divisible : WheelDivisible candidate)
    (notWheelPrime : candidate ∉ wheelPrimes) :
    ClearedBy wheelPrimes candidate := by
  rcases divisible with ⟨prime, primeMember, primeDivides⟩
  by_cases square : prime * prime ≤ candidate
  · exact ⟨prime, primeMember, primeDivides, square⟩
  · rcases primeDivides with ⟨quotient, rfl⟩
    have primePositive : 0 < prime := by
      have := wheelPrime_three_le primeMember
      omega
    have quotientPositive : 0 < quotient :=
      Nat.pos_of_mul_pos_left candidatePositive
    have quotientNotOne : quotient ≠ 1 := by
      intro quotientOne
      subst quotient
      apply notWheelPrime
      simpa using primeMember
    have quotient_lt_prime : quotient < prime := by
      apply (Nat.mul_lt_mul_left primePositive).mp
      exact Nat.lt_of_not_ge square
    rcases Nat.exists_prime_and_dvd quotientNotOne with
      ⟨smallPrime, smallPrimePrime, smallPrimeDivides⟩
    have smallPrime_le_quotient :
        smallPrime ≤ quotient :=
      Nat.le_of_dvd quotientPositive smallPrimeDivides
    have smallPrimeDividesCandidate :
        smallPrime ∣ prime * quotient :=
      dvd_mul_of_dvd_right smallPrimeDivides prime
    have smallPrime_ne_two :
        smallPrime ≠ 2 :=
      candidateOdd.ne_two_of_dvd_nat smallPrimeDividesCandidate
    have smallPrime_three_le : 3 ≤ smallPrime := by
      have := smallPrimePrime.two_le
      omega
    have smallPrime_le_prime : smallPrime ≤ prime :=
      le_trans smallPrime_le_quotient
        (Nat.le_of_lt quotient_lt_prime)
    have smallPrime_le_twentyThree : smallPrime ≤ 23 :=
      le_trans smallPrime_le_prime
        (wheelPrime_le_twentyThree primeMember)
    have smallPrimeMember : smallPrime ∈ wheelPrimes :=
      prime_mem_wheelPrimes_of_three_le_of_le_twentyThree
        smallPrimePrime smallPrime_three_le smallPrime_le_twentyThree
    exact ⟨smallPrime, smallPrimeMember, smallPrimeDividesCandidate,
      Nat.mul_le_mul smallPrime_le_prime smallPrime_le_quotient⟩

theorem clearedBy_wheelPrimes_iff
    {candidate : Nat}
    (candidatePositive : 0 < candidate) (candidateOdd : Odd candidate) :
    ClearedBy wheelPrimes candidate ↔
      WheelDivisible candidate ∧ candidate ∉ wheelPrimes := by
  constructor
  · intro cleared
    rcases cleared with ⟨prime, member, divides, square⟩
    refine ⟨⟨prime, member, divides⟩, ?_⟩
    intro candidateMember
    exact wheelPrime_not_cleared candidateMember
      ⟨prime, member, divides, square⟩
  · rintro ⟨divisible, notWheelPrime⟩
    exact clearedBy_of_wheelDivisible_of_not_mem
      candidatePositive candidateOdd divisible notWheelPrime

/-- Logical 64-bit owner word. -/
abbrev WheelWord := Fin 64 → Bool

def allOnesWord : WheelWord :=
  fun _ => true

/-- Executable finite form of the original square-guard predicate. -/
def clearedByBool (basePrimes : List Nat) (candidate : Nat) : Bool :=
  basePrimes.any fun prime =>
    decide (prime ∣ candidate ∧ prime * prime ≤ candidate)

theorem clearedByBool_eq_true_iff
    (basePrimes : List Nat) (candidate : Nat) :
    clearedByBool basePrimes candidate = true ↔
      ClearedBy basePrimes candidate := by
  simp [clearedByBool, ClearedBy, List.any_eq_true]

/-- Apply the original square-guard clear predicate to one logical word. -/
def applySquareGuardClears
    (initial : WheelWord) (qLow wordIndex : Nat)
    (basePrimes : List Nat) : WheelWord :=
  fun bit =>
    !clearedByBool basePrimes
        (wordCandidate qLow wordIndex bit) &&
      initial bit

/-- Original through-23 word-owner result. -/
def squareGuardWheelInitializer
    (qLow wordIndex : Nat) : WheelWord :=
  applySquareGuardClears allOnesWord qLow wordIndex wheelPrimes

/-- Proposed table initializer with the eight source primes restored. -/
def restoredWheelInitializer
    (qLow wordIndex : Nat) : WheelWord :=
  fun bit =>
    let candidate := wordCandidate qLow wordIndex bit
    if candidate ∈ wheelPrimes then
      true
    else
      duplicatedWheelTableBit
        (cudaWordPhase qLow wordIndex + bit)

/-- Raw table initialization plus explicit prime restoration is extensionally
equal to the original through-23 square-guard loop. -/
theorem restoredWheelInitializer_eq_squareGuard
    (qLow wordIndex : Nat) (qLowOdd : Odd qLow) :
    restoredWheelInitializer qLow wordIndex =
      squareGuardWheelInitializer qLow wordIndex := by
  funext bit
  let candidate := wordCandidate qLow wordIndex bit
  have candidatePositive :
      0 < candidate :=
    wordCandidate_pos qLow wordIndex bit qLowOdd
  have candidateOdd :
      Odd candidate :=
    wordCandidate_odd qLow wordIndex bit qLowOdd
  have tableEquality :
      duplicatedWheelTableBit
          (cudaWordPhase qLow wordIndex + bit) =
        !wheelDivisibleBool candidate := by
    rw [duplicatedWheelTableBit_cudaWordPhase
      qLow wordIndex bit bit.isLt]
    exact wheelTableBit_cudaPhase
      qLow wordIndex bit qLowOdd bit.isLt
  simp only [restoredWheelInitializer, squareGuardWheelInitializer,
    applySquareGuardClears, allOnesWord]
  change
    (if candidate ∈ wheelPrimes then true
      else duplicatedWheelTableBit
        (cudaWordPhase qLow wordIndex + bit)) =
      (!clearedByBool wheelPrimes candidate && true)
  rw [tableEquality]
  by_cases candidateMember : candidate ∈ wheelPrimes
  · have notCleared := wheelPrime_not_cleared candidateMember
    have notClearedBool :
        clearedByBool wheelPrimes candidate = false := by
      exact Bool.eq_false_iff.mpr fun clearedTrue =>
        notCleared
          ((clearedByBool_eq_true_iff
            wheelPrimes candidate).mp clearedTrue)
    simp [candidateMember, notClearedBool]
  · have clearedIff :
        ClearedBy wheelPrimes candidate ↔
          WheelDivisible candidate :=
        (clearedBy_wheelPrimes_iff
        candidatePositive candidateOdd).trans
        (and_iff_left candidateMember)
    rw [if_neg candidateMember]
    rw [Bool.and_true]
    apply congrArg (fun value => !value)
    apply Bool.eq_iff_iff.mpr
    rw [wheelDivisibleBool_eq_true_iff,
      clearedByBool_eq_true_iff]
    exact clearedIff.symm

theorem clearedBy_append_iff
    (first second : List Nat) (candidate : Nat) :
    ClearedBy (first ++ second) candidate ↔
      ClearedBy first candidate ∨ ClearedBy second candidate := by
  constructor
  · rintro ⟨prime, member, divides, square⟩
    rcases List.mem_append.mp member with firstMember | secondMember
    · exact Or.inl ⟨prime, firstMember, divides, square⟩
    · exact Or.inr ⟨prime, secondMember, divides, square⟩
  · rintro (⟨prime, member, divides, square⟩ |
      ⟨prime, member, divides, square⟩)
    · exact ⟨prime, List.mem_append.mpr (Or.inl member), divides, square⟩
    · exact ⟨prime, List.mem_append.mpr (Or.inr member), divides, square⟩

theorem applySquareGuardClears_append
    (initial : WheelWord) (qLow wordIndex : Nat)
    (first second : List Nat) :
    applySquareGuardClears
        (applySquareGuardClears initial qLow wordIndex first)
        qLow wordIndex second =
      applySquareGuardClears initial qLow wordIndex (first ++ second) := by
  funext bit
  simp [applySquareGuardClears, clearedByBool, List.any_append,
    Bool.not_or, Bool.and_assoc, Bool.and_comm]

/-- Replacing the original through-23 prefix by the restored wheel leaves
composition with an arbitrary remaining prime roster unchanged. -/
theorem restoredWheel_then_remaining_eq_original
    (qLow wordIndex : Nat) (qLowOdd : Odd qLow)
    (remainingPrimes : List Nat) :
    applySquareGuardClears
        (restoredWheelInitializer qLow wordIndex)
        qLow wordIndex remainingPrimes =
      applySquareGuardClears allOnesWord qLow wordIndex
        (wheelPrimes ++ remainingPrimes) := by
  rw [restoredWheelInitializer_eq_squareGuard qLow wordIndex qLowOdd]
  exact applySquareGuardClears_append
    allOnesWord qLow wordIndex wheelPrimes remainingPrimes

#print axioms wheelModulus_eq_product
#print axioms cudaPhase_addresses_wordCandidate
#print axioms duplicatedWheelTableBit_eq_mod
#print axioms tableOddValue_cudaPhase_dvd_iff_wordCandidate
#print axioms clearedBy_wheelPrimes_iff
#print axioms restoredWheelInitializer_eq_squareGuard
#print axioms restoredWheel_then_remaining_eq_original

end SparkInterval.TernaryGoldbach.GoldbachWordOwnerWheel23
