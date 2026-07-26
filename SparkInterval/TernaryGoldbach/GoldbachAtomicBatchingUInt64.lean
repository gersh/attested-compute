/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachAtomicBatching
import Batteries.Data.Nat.Lemmas
import Mathlib.Data.Nat.Bitwise
import Mathlib.Tactic

/-!
# Unsigned-64 arithmetic for Goldbach atomic batching

`GoldbachAtomicBatching` proves the architecture-independent batching
equation over logical 64-bit words.  This file proves the next, still
source-level, arithmetic layer:

* `Nat.ofBits` encodes a logical word in the low 64 bits without loss;
* Lean's actual `UInt64` complement, shift, and AND operations realize the
  logical one-bit clear and combined-mask operations;
* every live word key in the source-shaped 200,500,000-odd-value terminal
  geometry is strictly below the `UINT64_MAX` empty-key sentinel; and
* masking a power-of-two table index is exactly reduction modulo its slot
  count, including after the source's wrapping 64-bit hash multiplication.

The 200,500,000 bound and 512-slot table are the literal constants in
`h100_tg_goldbach_tail_combiner_qualification.cu`.  Nothing here promotes
that qualification-only kernel or proves CUDA/PTX/SASS refinement,
atomic linearizability, barrier visibility, event coverage, or execution.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.GoldbachAtomicBatchingUInt64

open GoldbachAtomicClears
open GoldbachAtomicBatching

/-! ## Exact logical-word encoding -/

def uint64Width : Nat := 64
def uint64Radix : Nat := 2 ^ uint64Width
def uint64Max : Nat := uint64Radix - 1

/-- Little-bit-numbered natural encoding of the logical packed word. -/
def encodeWord (word : Word) : Nat :=
  Nat.ofBits word

theorem encodeWord_lt_uint64Radix (word : Word) :
    encodeWord word < uint64Radix := by
  simpa [encodeWord, uint64Radix, uint64Width] using
    Nat.ofBits_lt_two_pow word

@[simp] theorem testBit_encodeWord
    (word : Word) (bit : Fin 64) :
    (encodeWord word).testBit bit = word bit := by
  simp [encodeWord]

theorem encodeWord_injective : Function.Injective encodeWord := by
  intro first second equality
  funext bit
  have bitEquality :=
    congrArg (fun value : Nat => value.testBit bit) equality
  simpa using bitEquality

/-- Encoding commutes with exact bitwise AND. -/
theorem encodeWord_and (first second : Word) :
    encodeWord (fun bit => first bit && second bit) =
      encodeWord first &&& encodeWord second := by
  apply Nat.eq_of_testBit_eq
  intro index
  rw [Nat.testBit_land]
  simp only [encodeWord, Nat.testBit_ofBits]
  split <;> simp_all

/-- The logical word embedded in Lean's actual unsigned-64 type. -/
def encodeUInt64 (word : Word) : UInt64 :=
  UInt64.ofNat (encodeWord word)

@[simp] theorem encodeUInt64_toNat (word : Word) :
    (encodeUInt64 word).toNat = encodeWord word := by
  rw [encodeUInt64, UInt64.toNat_ofNat']
  exact Nat.mod_eq_of_lt (encodeWord_lt_uint64Radix word)

/-! ## Literal complement, shift, and AND -/

/-- Natural value of source `1ULL << bit`, with the shift guard in the type. -/
def shiftedOne64 (bit : Fin 64) : Nat :=
  1 <<< (bit : Nat)

@[simp] theorem shiftedOne64_eq_two_pow (bit : Fin 64) :
    shiftedOne64 bit = 2 ^ (bit : Nat) := by
  simp [shiftedOne64, Nat.shiftLeft_eq]

theorem shiftedOne64_lt_uint64Radix (bit : Fin 64) :
    shiftedOne64 bit < uint64Radix := by
  rw [shiftedOne64_eq_two_pow]
  exact Nat.pow_lt_pow_right (by norm_num) bit.isLt

/-- Natural value of the unsigned-64 complement
`~(1ULL << bit)`. -/
def clearBitMask64 (bit : Fin 64) : Nat :=
  uint64Max ^^^ shiftedOne64 bit

/-- The literal operation used by the CUDA source, represented in Lean's
actual `UInt64` type. -/
def nativeClearBitMask64 (bit : Fin 64) : UInt64 :=
  ~~~((1 : UInt64) <<< UInt64.ofNat bit)

theorem nativeShiftedOne_toNat (bit : Fin 64) :
    (((1 : UInt64) <<< UInt64.ofNat bit).toNat) =
      shiftedOne64 bit := by
  simp only [UInt64.toNat_shiftLeft, UInt64.toNat_ofNat,
    UInt64.toNat_ofNat']
  rw [Nat.mod_eq_of_lt (by norm_num : 1 < 2 ^ 64)]
  rw [Nat.mod_eq_of_lt
    (lt_trans bit.isLt (by norm_num : 64 < 2 ^ 64))]
  rw [Nat.mod_eq_of_lt (by norm_num : (bit : Nat) < 64)]
  change shiftedOne64 bit % 2 ^ 64 = shiftedOne64 bit
  rw [Nat.mod_eq_of_lt (by
    simpa [uint64Radix, uint64Width] using
      shiftedOne64_lt_uint64Radix bit)]

@[simp] theorem nativeClearBitMask64_toNat (bit : Fin 64) :
    (nativeClearBitMask64 bit).toNat = clearBitMask64 bit := by
  rw [show nativeClearBitMask64 bit =
      (-1 : UInt64) ^^^
        ((1 : UInt64) <<< UInt64.ofNat bit) by
    simp [nativeClearBitMask64]]
  rw [UInt64.toNat_xor, nativeShiftedOne_toNat]
  have allOnes :
      (-1 : UInt64).toNat = uint64Max := by
    rw [← UInt64.not_zero, UInt64.toNat_not]
    norm_num [uint64Max, uint64Radix, uint64Width]
  rw [allOnes]
  rfl

theorem clearBitMask64_lt_uint64Radix (bit : Fin 64) :
    clearBitMask64 bit < uint64Radix := by
  apply Nat.xor_lt_two_pow
  · norm_num [uint64Max, uint64Radix, uint64Width]
  · exact shiftedOne64_lt_uint64Radix bit

theorem testBit_clearBitMask64
    (cleared current : Fin 64) :
    (clearBitMask64 cleared).testBit current =
      decide (current ≠ cleared) := by
  have allOnes :
      uint64Max.testBit current = true := by
    rw [uint64Max, uint64Radix, uint64Width,
      Nat.testBit_two_pow_sub_one]
    simp [current.isLt]
  rw [clearBitMask64, Nat.testBit_xor, allOnes,
    shiftedOne64_eq_two_pow, Nat.testBit_two_pow]
  by_cases same : current = cleared
  · subst current
    simp
  · have valuesDiffer : (cleared : Nat) ≠ (current : Nat) := by
      intro equality
      exact same (Fin.ext equality.symm)
    simp [same, valuesDiffer]

/-- A singleton logical clear mask is exactly the CUDA complement/shift
mask, including its 64-bit truncation. -/
theorem encodeWord_clearMask_singleton (bit : Fin 64) :
    encodeWord (clearMask [bit]) = clearBitMask64 bit := by
  apply Nat.eq_of_testBit_eq
  intro index
  by_cases inRange : index < 64
  · let current : Fin 64 := ⟨index, inRange⟩
    have logical :
        (encodeWord (clearMask [bit])).testBit index =
          clearMask [bit] current := by
      simpa [current] using
        testBit_encodeWord (clearMask [bit]) current
    rw [logical]
    simpa [clearMask, current] using
      (testBit_clearBitMask64 bit current).symm
  · have above : 64 ≤ index := Nat.le_of_not_gt inRange
    rw [show encodeWord (clearMask [bit]) =
        Nat.ofBits (clearMask [bit]) by rfl]
    rw [Nat.testBit_ofBits_ge (clearMask [bit]) index above]
    exact (Nat.testBit_lt_two_pow
      (lt_of_lt_of_le
        (by
          simpa [uint64Radix, uint64Width] using
            clearBitMask64_lt_uint64Radix bit)
        (Nat.pow_le_pow_right (by norm_num) above))).symm

theorem encodeUInt64_clearMask_singleton (bit : Fin 64) :
    UInt64.ofNat (encodeWord (clearMask [bit])) =
      nativeClearBitMask64 bit := by
  rw [← UInt64.toNat_inj]
  rw [UInt64.toNat_ofNat']
  rw [Nat.mod_eq_of_lt (by
    simpa [uint64Radix, uint64Width] using
      encodeWord_lt_uint64Radix (clearMask [bit]))]
  rw [nativeClearBitMask64_toNat, encodeWord_clearMask_singleton]

/-- Logical combined-mask application is exactly native unsigned-64 AND. -/
theorem encodeUInt64_applyClearMask
    (word : Word) (bits : List (Fin 64)) :
    encodeUInt64 (applyClearMask word bits) =
      encodeUInt64 word &&&
        UInt64.ofNat (encodeWord (clearMask bits)) := by
  rw [← UInt64.toNat_inj]
  simp only [encodeUInt64_toNat, UInt64.toNat_and, UInt64.toNat_ofNat']
  rw [Nat.mod_eq_of_lt (by
    simpa [uint64Radix, uint64Width] using
      encodeWord_lt_uint64Radix (clearMask bits))]
  exact encodeWord_and word (clearMask bits)

/-- One literal native clear realizes the logical atomic-clear operation. -/
theorem encodeUInt64_atomicClear
    (word : Word) (bit : Fin 64) :
    encodeUInt64 (atomicClear word bit) =
      encodeUInt64 word &&& nativeClearBitMask64 bit := by
  rw [← encodeUInt64_clearMask_singleton]
  have logicalEquality :
      atomicClear word bit = applyClearMask word [bit] := by
    funext current
    by_cases same : current = bit
    · subst current
      simp [atomicClear, applyClearMask, clearMask]
    · simp [atomicClear, applyClearMask, clearMask, same]
  rw [logicalEquality]
  exact encodeUInt64_applyClearMask word [bit]

/-! ## Repeated native mask accumulation -/

/-- Sequential semantics of one linearization of literal unsigned-64 clear
masks.  This models only the arithmetic of a shared or global `atomicAnd`
serialization; it does not assert that a CUDA execution supplies one. -/
def nativeRunClears : UInt64 → List (Fin 64) → UInt64
  | word, [] => word
  | word, bit :: rest =>
      nativeRunClears (word &&& nativeClearBitMask64 bit) rest

theorem nativeRunClears_encode
    (word : Word) (bits : List (Fin 64)) :
    nativeRunClears (encodeUInt64 word) bits =
      encodeUInt64 (runClears word bits) := by
  induction bits generalizing word with
  | nil => rfl
  | cons bit rest inductionHypothesis =>
      simp only [nativeRunClears, runClears]
      rw [← encodeUInt64_atomicClear]
      exact inductionHypothesis (atomicClear word bit)

/-- Logical all-ones word used to model source initialization `~0ULL`. -/
def allOnesWord : Word :=
  fun _ => true

theorem encodeWord_allOnes :
    encodeWord allOnesWord = uint64Max := by
  apply Nat.eq_of_testBit_eq
  intro index
  simp only [encodeWord, Nat.testBit_ofBits, allOnesWord]
  change (if _ : index < 64 then true else false) =
    (2 ^ 64 - 1).testBit index
  rw [Nat.testBit_two_pow_sub_one]
  by_cases live : index < 64 <;> simp [live]

theorem uint64NegOne_toNat :
    (-1 : UInt64).toNat = uint64Max := by
  rw [← UInt64.not_zero, UInt64.toNat_not]
  norm_num [uint64Max, uint64Radix, uint64Width]

theorem encodeUInt64_allOnes :
    encodeUInt64 allOnesWord = (-1 : UInt64) := by
  rw [← UInt64.toNat_inj, encodeUInt64_toNat, encodeWord_allOnes,
    uint64NegOne_toNat]

theorem runClears_allOnes_eq_clearMask (bits : List (Fin 64)) :
    runClears allOnesWord bits = clearMask bits := by
  funext bit
  rw [runClears_apply]
  by_cases member : bit ∈ bits
  · simp [clearMask, member]
  · simp [allOnesWord, clearMask, member]

/-- Literal shared-mask initialization followed by one native AND per
contribution. -/
def nativeAccumulatedClearMask (bits : List (Fin 64)) : UInt64 :=
  nativeRunClears (-1 : UInt64) bits

theorem nativeAccumulatedClearMask_eq_encoded
    (bits : List (Fin 64)) :
    nativeAccumulatedClearMask bits =
      UInt64.ofNat (encodeWord (clearMask bits)) := by
  rw [nativeAccumulatedClearMask, ← encodeUInt64_allOnes,
    nativeRunClears_encode, runClears_allOnes_eq_clearMask]
  rfl

/-- Flushing the accumulated literal shared mask has exactly the logical
combined-batch effect on an arbitrary pre-existing word. -/
theorem nativeFlush_eq_applyClearMask
    (word : Word) (bits : List (Fin 64)) :
    encodeUInt64 word &&& nativeAccumulatedClearMask bits =
      encodeUInt64 (applyClearMask word bits) := by
  rw [nativeAccumulatedClearMask_eq_encoded]
  exact (encodeUInt64_applyClearMask word bits).symm

/-! ## Empty-key exclusion for the source-shaped terminal geometry -/

/-- Literal number of odd values in the source-height terminal qualifier. -/
def sourceSegmentOddCount : Nat := 200_500_000

/-- Literal number of 64-bit packed words allocated for those odd values. -/
def sourceSegmentWordCount : Nat :=
  (sourceSegmentOddCount + 63) / 64

theorem sourceSegmentWordCount_eq :
    sourceSegmentWordCount = 3_132_813 := by
  norm_num [sourceSegmentWordCount, sourceSegmentOddCount]

theorem sourceLiveBit_wordKey_lt_wordCount
    {bit : Nat} (live : bit < sourceSegmentOddCount) :
    bit / 64 < sourceSegmentWordCount := by
  norm_num [sourceSegmentOddCount, sourceSegmentWordCount] at live ⊢
  omega

theorem sourceLiveWordKey_lt_emptyKey
    {wordKey : Nat} (live : wordKey < sourceSegmentWordCount) :
    wordKey < uint64Max := by
  norm_num [sourceSegmentWordCount, sourceSegmentOddCount,
    uint64Max, uint64Radix, uint64Width] at live ⊢
  omega

theorem sourceLiveWordKey_ne_emptyKey
    {wordKey : Nat} (live : wordKey < sourceSegmentWordCount) :
    wordKey ≠ uint64Max :=
  Nat.ne_of_lt (sourceLiveWordKey_lt_emptyKey live)

theorem sourceLiveBit_wordKey_ne_emptyKey
    {bit : Nat} (live : bit < sourceSegmentOddCount) :
    bit / 64 ≠ uint64Max :=
  sourceLiveWordKey_ne_emptyKey
    (sourceLiveBit_wordKey_lt_wordCount live)

/-! ## Power-of-two hash and probe indexing -/

def maximumTableSlots : Nat := 512
def tableHashMultiplier : Nat := 11_400_714_819_323_198_485

/-- Exact natural semantics of unsigned-64 multiplication. -/
def uint64Mul (first second : Nat) : Nat :=
  (first * second) % uint64Radix

/-- Low-bit masking after wrapping multiplication is insensitive to the
wrap whenever the requested power-of-two width is at most 64. -/
theorem uint64Mul_mask_eq_unbounded_mod
    (first second width : Nat) (widthFits : width ≤ 64) :
    uint64Mul first second &&& (2 ^ width - 1) =
      (first * second) % 2 ^ width := by
  rw [Nat.and_two_pow_sub_one_eq_mod]
  exact Nat.mod_mod_of_dvd _
    (Nat.pow_dvd_pow 2 widthFits)

/-- Literal 512-slot normal-path hash from the qualification source. -/
def tableHash512 (wordKey : Nat) : Nat :=
  uint64Mul wordKey tableHashMultiplier &&& (maximumTableSlots - 1)

/-- The 64-bit multiply-and-mask expression evaluated by the source before
its narrowing cast to `unsigned`. -/
def nativeTableHash512Raw (wordKey : UInt64) : UInt64 :=
  (wordKey * UInt64.ofNat tableHashMultiplier) &&&
    UInt64.ofNat (maximumTableSlots - 1)

/-- The source's narrowing cast of the masked hash result to `unsigned`. -/
def nativeTableHash512 (wordKey : UInt64) : UInt32 :=
  UInt32.ofNat (nativeTableHash512Raw wordKey).toNat

theorem tableHash512_eq_mod (wordKey : Nat) :
    tableHash512 wordKey =
      (wordKey * tableHashMultiplier) % maximumTableSlots := by
  simpa [tableHash512, maximumTableSlots] using
    uint64Mul_mask_eq_unbounded_mod
      wordKey tableHashMultiplier 9 (by norm_num)

theorem tableHash512_lt (wordKey : Nat) :
    tableHash512 wordKey < maximumTableSlots := by
  rw [tableHash512_eq_mod]
  exact Nat.mod_lt _ (by norm_num [maximumTableSlots])

theorem nativeTableHash512Raw_toNat (wordKey : UInt64) :
    (nativeTableHash512Raw wordKey).toNat =
      tableHash512 wordKey.toNat := by
  simp only [nativeTableHash512Raw, UInt64.toNat_and, UInt64.toNat_mul,
    UInt64.toNat_ofNat']
  rw [Nat.mod_eq_of_lt (by
    norm_num [tableHashMultiplier] : tableHashMultiplier < 2 ^ 64)]
  rw [Nat.mod_eq_of_lt (by
    norm_num [maximumTableSlots] : maximumTableSlots - 1 < 2 ^ 64)]
  rfl

theorem nativeTableHash512_toNat (wordKey : UInt64) :
    (nativeTableHash512 wordKey).toNat =
      tableHash512 wordKey.toNat := by
  rw [nativeTableHash512, UInt32.toNat_ofNat']
  rw [nativeTableHash512Raw_toNat]
  rw [Nat.mod_eq_of_lt (lt_trans (tableHash512_lt wordKey.toNat)
    (by norm_num [maximumTableSlots] : maximumTableSlots < 2 ^ 32))]

/-- Literal power-of-two probe-slot expression after the first hash. -/
def probeSlot (width firstSlot probe : Nat) : Nat :=
  (firstSlot + probe) &&& (2 ^ width - 1)

theorem probeSlot_eq_mod (width firstSlot probe : Nat) :
    probeSlot width firstSlot probe =
      (firstSlot + probe) % 2 ^ width := by
  simp [probeSlot, Nat.and_two_pow_sub_one_eq_mod]

theorem probeSlot_lt
    {width firstSlot probe : Nat} :
    probeSlot width firstSlot probe < 2 ^ width := by
  rw [probeSlot_eq_mod]
  exact Nat.mod_lt _ (Nat.two_pow_pos width)

/-- The source's 32-bit `firstSlot + probe` cannot wrap for the admitted
512-slot table. -/
theorem maximumProbeAdd_lt_uint32
    {firstSlot probe : Nat}
    (firstInRange : firstSlot < maximumTableSlots)
    (probeInRange : probe < maximumTableSlots) :
    firstSlot + probe < 2 ^ 32 := by
  norm_num [maximumTableSlots] at firstInRange probeInRange ⊢
  omega

/-- Exact `unsigned` addition-and-mask expression used by the 512-slot
production probe loop. -/
def nativeProbeSlot512 (firstSlot probe : UInt32) : UInt32 :=
  (firstSlot + probe) &&&
    UInt32.ofNat (maximumTableSlots - 1)

theorem nativeProbeSlot512_toNat
    (firstSlot probe : UInt32)
    (firstInRange : firstSlot.toNat < maximumTableSlots)
    (probeInRange : probe.toNat < maximumTableSlots) :
    (nativeProbeSlot512 firstSlot probe).toNat =
      probeSlot 9 firstSlot.toNat probe.toNat := by
  simp only [nativeProbeSlot512, UInt32.toNat_and, UInt32.toNat_add,
    UInt32.toNat_ofNat']
  rw [Nat.mod_eq_of_lt
    (maximumProbeAdd_lt_uint32 firstInRange probeInRange)]
  norm_num [probeSlot, maximumTableSlots]

#print axioms encodeWord_and
#print axioms nativeClearBitMask64_toNat
#print axioms encodeWord_clearMask_singleton
#print axioms encodeUInt64_applyClearMask
#print axioms encodeUInt64_atomicClear
#print axioms nativeRunClears_encode
#print axioms nativeAccumulatedClearMask_eq_encoded
#print axioms nativeFlush_eq_applyClearMask
#print axioms sourceLiveWordKey_ne_emptyKey
#print axioms sourceLiveBit_wordKey_ne_emptyKey
#print axioms uint64Mul_mask_eq_unbounded_mod
#print axioms tableHash512_eq_mod
#print axioms nativeTableHash512_toNat
#print axioms probeSlot_eq_mod
#print axioms maximumProbeAdd_lt_uint32
#print axioms nativeProbeSlot512_toNat

end SparkInterval.TernaryGoldbach.GoldbachAtomicBatchingUInt64
